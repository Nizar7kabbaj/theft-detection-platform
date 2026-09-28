#!/usr/bin/env bash
set -euo pipefail

DEPENDENCIES=(docker kubectl awk date)
SCRIPT_NAME=$(basename "$0")
CLUSTER=theft-dev
CONTROL_PLANE="${CLUSTER}-control-plane"
WORKER="${CLUSTER}-worker"
REGISTRY=kind-registry
CONTEXT="kind-${CLUSTER}"
TIMEOUT=300
STOP_GRACE=60
DRAIN_TIMEOUT=180s

function usage() {
    cat <<EOM
start or stop the local kind cluster in dependency order.

usage: ${SCRIPT_NAME} <start|stop|status>

    start    boot each node, wait for its network pods, then let workloads schedule on it
    stop     drain the worker, then the control-plane, then power them off
    status   node containers, node scheduling state and pods that are not ready
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

function now_utc() {
    date -u +%Y-%m-%dT%H:%M:%SZ
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

function wait_for_node_network() {
    local node=$1 since=$2
    wait_for_pods kube-system k8s-app=kube-proxy "$since" "$node"
    wait_for_pods kube-system app=kindnet "$since" "$node"
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

function start() {
    local since
    docker start "$REGISTRY" >/dev/null
    since=$(now_utc)
    docker start "$CONTROL_PLANE" >/dev/null
    wait_for_api
    wait_for_lease "$CONTROL_PLANE" "$since"
    wait_for_node_network "$CONTROL_PLANE" "$since"
    k uncordon "$CONTROL_PLANE" >/dev/null
    wait_for_pods kube-system k8s-app=kube-dns "$since"
    since=$(now_utc)
    docker start "$WORKER" >/dev/null
    wait_for_lease "$WORKER" "$since"
    wait_for_node_network "$WORKER" "$since"
    k uncordon "$WORKER" >/dev/null
    wait_for_pods theft "" "$since"
    echo "cluster ready"
}

function stop() {
    k cordon "$CONTROL_PLANE" "$WORKER" >/dev/null
    drain "$WORKER"
    drain "$CONTROL_PLANE"
    docker stop -t "$STOP_GRACE" "$WORKER" >/dev/null
    stop_control_plane
    docker stop -t "$STOP_GRACE" "$CONTROL_PLANE" >/dev/null
    docker stop "$REGISTRY" >/dev/null
    echo "cluster stopped"
}

function status() {
    docker ps -a --filter "name=^(${CONTROL_PLANE}|${WORKER}|${REGISTRY})$" \
        --format 'table {{.Names}}\t{{.Status}}'
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
