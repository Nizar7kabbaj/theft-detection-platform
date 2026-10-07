#!/usr/bin/env bash
set -euo pipefail

DEPENDENCIES=(iptables iptables-restore systemctl install)
SCRIPT_NAME=$(basename "$0")
SCRIPT_PATH=$(readlink -f "$0")
CHAIN=THEFT-EGRESS
INSTALLED=/usr/local/sbin/theft-container-egress
UNIT=theft-container-egress.service
UNIT_PATH=/etc/systemd/system/${UNIT}
LIMITED_SUBNETS=(172.31.240.0/24 172.21.0.0/24)
PRIVATE_RANGES=(10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 127.0.0.0/8 169.254.0.0/16)
TELEGRAM_SOURCES=(172.21.0.20/32 172.21.0.21/32)
TELEGRAM_RANGES=(
    91.108.56.0/22 91.108.4.0/22 91.108.8.0/22 91.108.16.0/22 91.108.12.0/22
    149.154.160.0/20 91.105.192.0/23 91.108.20.0/22 185.76.151.0/24
)

function usage() {
    cat <<EOM
limit internet egress from the edge and observability container networks.
private ranges stay reachable, the notification worker and the telegram poller may resolve names and reach telegram on 443, everything else is rejected.

usage: sudo ${SCRIPT_NAME} <apply|remove|status|install>

    apply     load the ${CHAIN} chain atomically and jump to it from DOCKER-USER
    remove    drop the jump and the chain
    status    print the chain and whether DOCKER-USER jumps to it
    install   copy this script to ${INSTALLED} and enable ${UNIT} so the rules survive reboots and docker restarts
EOM
    exit 1
}

function check_deps() {
    local dep
    for dep in "${DEPENDENCIES[@]}"; do
        if ! command -v "${dep}" >/dev/null 2>&1; then
            echo "missing dependency: ${dep}" >&2
            exit 1
        fi
    done
}

function rules() {
    local range subnet source
    echo "*filter"
    echo ":${CHAIN} - [0:0]"
    echo "-A ${CHAIN} -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN"
    for source in "${TELEGRAM_SOURCES[@]}"; do
        for range in "${TELEGRAM_RANGES[@]}"; do
            echo "-A ${CHAIN} -s ${source} -d ${range} -p tcp --dport 443 -j RETURN"
        done
        echo "-A ${CHAIN} -s ${source} -p udp --dport 53 -j RETURN"
        echo "-A ${CHAIN} -s ${source} -p tcp --dport 53 -j RETURN"
    done
    for subnet in "${LIMITED_SUBNETS[@]}"; do
        echo "-A ${CHAIN} -s ${subnet} -p udp --dport 53 -j REJECT --reject-with icmp-port-unreachable"
        echo "-A ${CHAIN} -s ${subnet} -p tcp --dport 53 -j REJECT --reject-with tcp-reset"
        for range in "${PRIVATE_RANGES[@]}"; do
            echo "-A ${CHAIN} -s ${subnet} -d ${range} -j RETURN"
        done
        echo "-A ${CHAIN} -s ${subnet} -p tcp -j REJECT --reject-with tcp-reset"
        echo "-A ${CHAIN} -s ${subnet} -j REJECT --reject-with icmp-port-unreachable"
    done
    echo "COMMIT"
}

function apply() {
    if ! iptables -S DOCKER-USER >/dev/null 2>&1; then
        echo "DOCKER-USER chain not found, is docker running" >&2
        exit 1
    fi
    rules | iptables-restore --noflush
    if ! iptables -C DOCKER-USER -j "${CHAIN}" 2>/dev/null; then
        iptables -I DOCKER-USER 1 -j "${CHAIN}"
    fi
    iptables -C DOCKER-USER -j "${CHAIN}"
    echo "container egress limits applied ($(iptables -S "${CHAIN}" | grep -c '^-A') rules)"
}

function remove() {
    while iptables -C DOCKER-USER -j "${CHAIN}" 2>/dev/null; do
        iptables -D DOCKER-USER -j "${CHAIN}"
    done
    if iptables -S "${CHAIN}" >/dev/null 2>&1; then
        iptables -F "${CHAIN}"
        iptables -X "${CHAIN}"
    fi
    echo "container egress limits removed"
}

function status() {
    if iptables -C DOCKER-USER -j "${CHAIN}" 2>/dev/null; then
        echo "DOCKER-USER jumps to ${CHAIN}"
    else
        echo "DOCKER-USER does not jump to ${CHAIN}"
    fi
    iptables -S "${CHAIN}" 2>/dev/null || echo "${CHAIN} not loaded"
}

function install_unit() {
    install -m 0755 -o root -g root "${SCRIPT_PATH}" "${INSTALLED}"
    cat >"${UNIT_PATH}" <<EOF
[Unit]
Description=limit internet egress from theft-detection-platform container networks
After=docker.service
Requires=docker.service
PartOf=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=${INSTALLED} apply
ExecStop=${INSTALLED} remove

[Install]
WantedBy=docker.service
EOF
    systemctl daemon-reload
    systemctl enable "${UNIT}" >/dev/null 2>&1
    systemctl restart "${UNIT}"
    systemctl is-active --quiet "${UNIT}"
    echo "${UNIT} enabled and active"
}

function main() {
    [[ $# -eq 1 ]] || usage
    if [[ $1 == "-h" || $1 == "--help" ]]; then
        usage
    fi
    if [[ ${EUID} -ne 0 ]]; then
        echo "must run as root, use sudo" >&2
        exit 1
    fi
    check_deps
    case $1 in
        apply) apply ;;
        remove) remove ;;
        status) status ;;
        install) install_unit ;;
        *) echo "unknown command: $1" >&2; usage ;;
    esac
}

main "$@"
