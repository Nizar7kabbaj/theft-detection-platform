import ipaddress
import json
import re
import shutil
import subprocess
import sys
from collections import Counter

HBONE_PORT = 15008
PROBE = "169.254.7.127"
HEADER = re.compile(
    r"^\d\d:\d\d:\d\d\.\d+ .*? IP (\d+\.\d+\.\d+\.\d+)\.(\d+) > (\d+\.\d+\.\d+\.\d+)\.(\d+):"
)


def tool(name):
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"missing tool: {name}")
    return path


KUBECTL = tool("kubectl")
SUDO = tool("sudo")
TCPDUMP = tool("tcpdump")


def kubectl_json(*args):
    out = subprocess.run(
        [KUBECTL, *args, "-o", "json"], check=True, capture_output=True, text=True
    ).stdout
    return json.loads(out)


def build_names():
    names = {PROBE: "kubelet-probe"}
    for node in kubectl_json("get", "nodes")["items"]:
        node_name = node["metadata"]["name"]
        for address in node["status"]["addresses"]:
            if address["type"] == "InternalIP":
                names[address["address"]] = f"node/{node_name}"
        cidr = node["spec"].get("podCIDR")
        if cidr:
            names[str(next(ipaddress.ip_network(cidr).hosts()))] = f"bridge/{node_name}"
    for pod in kubectl_json("get", "pods", "-A")["items"]:
        ip = pod["status"].get("podIP")
        if ip and not pod["spec"].get("hostNetwork"):
            names[ip] = f"{pod['metadata']['namespace']}/{pod['metadata']['name']}"
    for svc in kubectl_json("get", "services", "-A")["items"]:
        ip = svc["spec"].get("clusterIP")
        if ip and ip != "None":
            names[ip] = f"svc/{svc['metadata']['namespace']}/{svc['metadata']['name']}"
    return names


def kind(client, server, port):
    if port == HBONE_PORT:
        return "hbone"
    if "kubelet-probe" in (client, server):
        return "probe via snat"
    if client.startswith("bridge/"):
        return "probe from node"
    return "outside mesh"


def read_flows(pcap, names):
    raw = subprocess.run(
        [SUDO, "-n", TCPDUMP, "-r", pcap, "-nn", "-A"], check=True, capture_output=True
    )
    flows, http, current = Counter(), Counter(), None
    for line in raw.stdout.decode("utf-8", errors="replace").splitlines():
        match = HEADER.match(line)
        if match:
            a, a_port = match.group(1), int(match.group(2))
            b, b_port = match.group(3), int(match.group(4))
            client, server, port = (b, a, a_port) if a_port < b_port else (a, b, b_port)
            current = (names.get(client, client), names.get(server, server), port)
            flows[current] += 1
        elif current and "HTTP/1." in line:
            http[current] += 1
    return flows, http


def main():
    flows, http = read_flows(sys.argv[1], build_names())
    by_kind = Counter()
    rows = []
    for (client, server, port), packets in flows.items():
        k = kind(client, server, port)
        by_kind[k] += packets
        rows.append((k, client, server, port, packets, http[(client, server, port)]))

    print("===== packets by kind")
    for k, packets in sorted(by_kind.items()):
        print(f"  {k:<16} {packets}")
    print("===== conversations outside hbone")
    for k, client, server, port, packets, lines in sorted(rows, key=lambda r: (r[0], -r[4])):
        if k != "hbone":
            print(f"  {k:<16} {client} -> {server}:{port}  packets {packets}  http-lines {lines}")
    print("===== hbone conversations")
    for _, client, server, port, packets, lines in sorted(rows, key=lambda r: -r[4]):
        if port == HBONE_PORT:
            print(f"  {client} -> {server}:{port}  packets {packets}  http-lines {lines}")


if __name__ == "__main__":
    main()
