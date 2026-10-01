#!/usr/bin/env bash
set -euo pipefail

DEPENDENCIES=(docker kubectl awk date)
SCRIPT_NAME=$(basename "$0")
CLUSTER=theft-dev
CONTROL_PLANE="${CLUSTER}-control-plane"
WORKER="${CLUSTER}-worker"
REGISTRY=kind-registry
NETWORK=kind
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/theft-kind"
CONTEXT="kind-${CLUSTER}"
TIMEOUT=300
STOP_GRACE=60
DRAIN_TIMEOUT=180s

function usage() {
    cat <<EOM
start or stop the local kind cluster in dependency order.

usage: ${SCRIPT_NAME} <start|stop|status>

    start    boot each node, check its address, wait for its network and mesh pods, then let workloads schedule on it
    stop     drain the worker, then the control-plane, power them off and pin their network addresses
    status   node containers with addresses, node scheduling state and pods that are not ready
EOM
    exit 1
}

function check_dependencies() {
    local missing=()
    for dep in "${DEPENDENCIES[@]}"; do
        command -v "$dep" >/dev/null 2>&1 || missing+=("$dep")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "missing dependencies: ${missing[*]}" >&2
        exit 1
    fi
}

function k() {
    kubectl --context "$CONTEXT" "$@"
}

function ipv4_only() {
    local value
    value=$(cat)
    if [[ "$value" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]]; then
        echo "$value"
    fi
}

function container_ip() {
    docker inspect -f "{{with index .NetworkSettings.Networks \"${NETWORK}\"}}{{.IPAddress}}{{end}}" "$1" | ipv4_only
}

function pinned_ip() {
    docker inspect -f "{{with index .NetworkSettings.Networks \"${NETWORK}\"}}{{with .IPAMConfig}}{{.IPv4Address}}{{end}}{{end}}" "$1" | ipv4_only
}

function pin_ip() {
    local name=$1 ip=$2
    docker network disconnect "$NETWORK" "$name" >/dev/null
    docker network connect --ip "$ip" "$NETWORK" "$name"
    echo "${name} pinned to ${ip}"
}

function record_pins() {
    local name ip
    mkdir -p "$STATE_DIR"
    for name in "$CONTROL_PLANE" "$WORKER" "$REGISTRY"; do
        ip=$(pinned_ip "$name")
        if [[ -n "$ip" ]]; then
            echo "$ip" >"${STATE_DIR}/${name}.ip"
        fi
    done
}

function attached() {
    docker inspect -f "{{with index .NetworkSettings.Networks \"${NETWORK}\"}}yes{{end}}" "$1"
}

function ensure_attached() {
    local name=$1 ip
    if [[ -n "$(attached "$name")" ]]; then
        return
    fi
    if [[ ! -s "${STATE_DIR}/${name}.ip" ]]; then
        echo "${name} is not attached to ${NETWORK} and no pinned address is recorded in ${STATE_DIR}" >&2
        exit 1
    fi
    ip=$(<"${STATE_DIR}/${name}.ip")
    docker network connect --ip "$ip" "$NETWORK" "$name"
    echo "${name} reattached to ${NETWORK} at ${ip}"
}

function release_moved() {
    local name ip
    for name in "$CONTROL_PLANE" "$WORKER" "$REGISTRY"; do
        [[ -s "${STATE_DIR}/${name}.ip" && -n "$(attached "$name")" ]] || continue
        ip=$(<"${STATE_DIR}/${name}.ip")
        [[ "$(pinned_ip "$name")" == "$ip" ]] && continue
        docker stop -t "$STOP_GRACE" "$name" >/dev/null
        docker network disconnect "$NETWORK" "$name" >/dev/null
        echo "${name} released, its address differs from the pin ${ip}"
    done
}

function started_at() {
    local ts
    ts=$(docker inspect -f '{{.State.StartedAt}}' "$1")
    echo "${ts%.*}Z"
}

function ensure_running() {
    local name=$1
    if [[ "$(docker inspect -f '{{.State.Running}}' "$name")" == "true" ]]; then
        echo "${name} already running"
    else
        docker start "$name" >/dev/null
        echo "${name} started"
    fi
}

function check_deadline() {
    local deadline=$1 what=$2
    if (( SECONDS >= deadline )); then
        echo "${what} not ready after ${TIMEOUT}s" >&2
        exit 1
    fi
}

function wait_for_api() {
    local deadline=$((SECONDS + TIMEOUT))
    until k get --raw=/readyz >/dev/null 2>&1; do
        check_deadline "$deadline" "api server"
        sleep 2
    done
    echo "api server ready"
}

function wait_for_lease() {
    local node=$1 since=$2 deadline=$((SECONDS + TIMEOUT)) renewed
    while :; do
        renewed=$(k -n kube-node-lease get lease "$node" -o jsonpath='{.spec.renewTime}' 2>/dev/null || true)
        if [[ -n "$renewed" && "${renewed%.*}" > "${since%Z}" ]]; then
            echo "${node} heartbeat fresh"
            return
        fi
        check_deadline "$deadline" "$node"
        sleep 2
    done
}

function wait_for_node_ip() {
    local node=$1 deadline=$((SECONDS + TIMEOUT)) want have
    want=$(container_ip "$node")
    while :; do
        have=$(k get node "$node" -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || true)
        if [[ -n "$want" && "$have" == "$want" ]]; then
            echo "${node} address ${want}"
            return
        fi
        check_deadline "$deadline" "${node} address (container ${want:-none}, node object ${have:-none})"
        sleep 2
    done
}

function wait_for_pods() {
    local namespace=$1 selector=$2 since=$3 node=${4:-}
    local deadline=$((SECONDS + TIMEOUT)) lines stale
    while :; do
        lines=$(k -n "$namespace" get pods ${selector:+-l "$selector"} \
            ${node:+--field-selector "spec.nodeName=${node}"} \
            -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.phase}{" "}{.status.containerStatuses[0].state.running.startedAt}{" "}{.status.containerStatuses[0].ready}{"\n"}{end}' \
            2>/dev/null || true)
        stale=$(awk -v since="$since" '
            $2 == "Succeeded" { next }
            NF < 4 || $4 != "true" || $3 < since { print $1 }
        ' <<<"$lines")
        if [[ -n "$lines" && -z "$stale" ]]; then
            echo "${namespace} ${selector:-all}${node:+ on ${node}} ready"
            return
        fi
        check_deadline "$deadline" "${namespace} pods (waiting on: ${stale//$'\n'/ })"
        sleep 3
    done
}

function wait_for_cni_range() {
    local node=$1 want conf have
    want=$(k get node "$node" -o jsonpath='{.spec.podCIDR}')
    for _ in $(seq 1 60); do
        conf=$(docker exec "$node" sh -c 'cat /etc/cni/net.d/*.conflist' 2>/dev/null || true)
        have=$(grep -m1 -oE '"subnet": *"[^"]+"' <<<"$conf" | cut -d'"' -f4 || true)
        if [[ -n "$want" && "$have" == "$want" ]]; then
            echo "${node} cni range ${want}"
            return
        fi
        sleep 2
    done
    echo "${node} cni range is ${have:-missing}, node expects ${want:-unknown}" >&2
    exit 1
}

function wait_for_node_network() {
    local node=$1 since=$2
    wait_for_pods kube-system k8s-app=kube-proxy "$since" "$node"
    wait_for_pods kube-system app=kindnet "$since" "$node"
    wait_for_cni_range "$node"
}

function mesh_installed() {
    k -n istio-dataplane get daemonset ztunnel >/dev/null 2>&1
}

function wait_for_mesh_agent() {
    local node=$1 since=$2
    if mesh_installed; then
        wait_for_pods istio-dataplane k8s-app=istio-cni-node "$since" "$node"
    fi
}

function wait_for_mesh_control() {
    local since=$1
    if mesh_installed; then
        wait_for_pods istio-system app=istiod "$since"
    fi
}

function wait_for_mesh_proxy() {
    local node=$1 since=$2
    if mesh_installed; then
        wait_for_pods istio-dataplane app=ztunnel "$since" "$node"
    fi
}

function heal_pod_addresses() {
    local stale ns name
    stale=$(
        {
            k get nodes -o jsonpath='{range .items[*]}N {.metadata.name} {.spec.podCIDR}{"\n"}{end}'
            k get pods -A -o jsonpath='{range .items[*]}P {.metadata.namespace} {.metadata.name} {.spec.nodeName} {.status.podIP} {.spec.hostNetwork}{"\n"}{end}'
        } | awk '
            function n(ip, a) { split(ip, a, "."); return ((a[1] * 256 + a[2]) * 256 + a[3]) * 256 + a[4] }
            function inside(ip, cidr, c) { split(cidr, c, "/"); return n(ip) >= n(c[1]) && n(ip) < n(c[1]) + 2 ^ (32 - c[2]) }
            $1 == "N" { range_of[$2] = $3; next }
            $1 == "P" && $5 ~ /^[0-9.]+$/ && $6 != "true" && ($4 in range_of) && !inside($5, range_of[$4]) { print $2, $3 }
        '
    )
    if [[ -z "$stale" ]]; then
        echo "pod addresses match node ranges"
        return
    fi
    while read -r ns name; do
        k -n "$ns" delete pod "$name" --wait=false >/dev/null
        echo "recreated ${ns}/${name}, address outside its node range"
    done <<<"$stale"
}

function drain() {
    local node=$1
    k cordon "$node" >/dev/null
    k drain "$node" --ignore-daemonsets --delete-emptydir-data --disable-eviction \
        --timeout="$DRAIN_TIMEOUT" >/dev/null
    echo "${node} drained"
}

function stop_control_plane() {
    local name
    local -a ids
    docker exec "$CONTROL_PLANE" systemctl stop kubelet
    for name in kube-controller-manager kube-scheduler kube-apiserver etcd; do
        mapfile -t ids < <(docker exec "$CONTROL_PLANE" crictl ps -q --name "^${name}$" 2>/dev/null || true)
        if [[ ${#ids[@]} -gt 0 && -n "${ids[0]}" ]]; then
            docker exec "$CONTROL_PLANE" crictl stop --timeout 30 "${ids[@]}" >/dev/null
        fi
        echo "${name} stopped"
    done
}

function disable_autorestart() {
    docker update --restart=no "$CONTROL_PLANE" "$WORKER" >/dev/null
}

function start() {
    local since
    disable_autorestart
    release_moved
    record_pins
    ensure_attached "$CONTROL_PLANE"
    ensure_attached "$WORKER"
    ensure_attached "$REGISTRY"
    ensure_running "$CONTROL_PLANE"
    since=$(started_at "$CONTROL_PLANE")
    wait_for_api
    wait_for_lease "$CONTROL_PLANE" "$since"
    wait_for_node_ip "$CONTROL_PLANE"
    wait_for_node_network "$CONTROL_PLANE" "$since"
    heal_pod_addresses
    wait_for_mesh_agent "$CONTROL_PLANE" "$since"
    k uncordon "$CONTROL_PLANE" >/dev/null
    wait_for_pods kube-system k8s-app=kube-dns "$since"
    wait_for_mesh_control "$since"
    wait_for_mesh_proxy "$CONTROL_PLANE" "$since"
    ensure_running "$WORKER"
    ensure_running "$REGISTRY"
    since=$(started_at "$WORKER")
    wait_for_lease "$WORKER" "$since"
    wait_for_node_ip "$WORKER"
    wait_for_node_network "$WORKER" "$since"
    heal_pod_addresses
    wait_for_mesh_agent "$WORKER" "$since"
    wait_for_mesh_proxy "$WORKER" "$since"
    k uncordon "$WORKER" >/dev/null
    wait_for_pods theft "" "$since"
    if k -n metrics-server get deployment metrics-server >/dev/null 2>&1; then
        wait_for_pods metrics-server app.kubernetes.io/name=metrics-server "$since"
        k wait --for=condition=Available apiservice/v1beta1.metrics.k8s.io --timeout=120s >/dev/null
        echo "metrics api available"
    fi
    echo "cluster ready"
}

function stop() {
    local name
    local -A unpinned=()
    for name in "$CONTROL_PLANE" "$WORKER" "$REGISTRY"; do
        if [[ -z "$(pinned_ip "$name")" && -n "$(container_ip "$name")" ]]; then
            unpinned[$name]=$(container_ip "$name")
        fi
    done
    disable_autorestart
    k cordon "$CONTROL_PLANE" "$WORKER" >/dev/null
    drain "$WORKER"
    drain "$CONTROL_PLANE"
    docker stop -t "$STOP_GRACE" "$WORKER" >/dev/null
    stop_control_plane
    docker stop -t "$STOP_GRACE" "$CONTROL_PLANE" >/dev/null
    docker stop "$REGISTRY" >/dev/null
    for name in "${!unpinned[@]}"; do
        pin_ip "$name" "${unpinned[$name]}"
    done
    record_pins
    echo "cluster stopped"
}

function status() {
    local name
    for name in "$CONTROL_PLANE" "$WORKER" "$REGISTRY"; do
        printf '%-26s %-8s ip=%-14s pinned=%s\n' "$name" \
            "$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || echo missing)" \
            "$(container_ip "$name" 2>/dev/null || true)" \
            "$(pinned_ip "$name" 2>/dev/null || true)"
    done
    k get nodes --no-headers 2>/dev/null | awk '{print $1, $2}' || true
    k get pods -A --no-headers 2>/dev/null \
        | awk '{ split($3, r, "/") } r[1] != r[2] && $4 != "Completed"' || true
}

function main() {
    [[ $# -eq 1 ]] || usage
    check_dependencies
    case $1 in
        start) start ;;
        stop) stop ;;
        status) status ;;
        -h|--help) usage ;;
        *) echo "unknown command: $1" >&2; usage ;;
    esac
}

main "$@"
