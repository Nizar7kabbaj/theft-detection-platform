import ipaddress
import json
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
NAMESPACE = "theft"
OUTSIDER_NS = "np-test"
DATA_APPS = {"mongo", "redis", "redis-broker", "redis-stream"}
EDGE_CA = REPO / "config" / "traefik" / "certs" / "ca.crt"
ROUTES = ["/", "/auth/login", "/auth/", "/api/", "/ws/"]
AMBIENT = "istio.io/dataplane-mode"
PROMETHEUS_SELECTOR = "app.kubernetes.io/name=prometheus,app.kubernetes.io/component=server"


def tool(name):
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"missing tool: {name}")
    return path


KUBECTL = tool("kubectl")


def kubectl(*args, stdin=None):
    return subprocess.run(
        [KUBECTL, *args], check=True, capture_output=True, text=True, input=stdin
    ).stdout


def get_json(*args):
    return json.loads(kubectl("get", *args, "-o", "json"))


def word(allowed):
    return "allow" if allowed else "deny"


def view(item):
    labels = item["metadata"].get("labels", {})
    statuses = item["status"].get("containerStatuses", [])
    return {
        "name": item["metadata"]["name"],
        "ns": item["metadata"]["namespace"],
        "labels": labels,
        "sa": item["spec"].get("serviceAccountName", "default"),
        "ip": item["status"].get("podIP"),
        "ready": bool(statuses) and all(s.get("ready") for s in statuses),
        "container": item["spec"]["containers"][0]["name"],
        "image": item["spec"]["containers"][0]["image"],
        "ports": [
            (p["containerPort"], p.get("name", ""))
            for c in item["spec"]["containers"]
            for p in c.get("ports", [])
        ],
    }


def live(item):
    return item["status"].get("phase") == "Running" and not item["metadata"].get(
        "deletionTimestamp"
    )


def matches(selector, labels):
    if selector.get("matchExpressions"):
        raise SystemExit("matchExpressions are not handled")
    return all(labels.get(k) == v for k, v in selector.get("matchLabels", {}).items())


class Model:
    def __init__(self):
        self.ns_labels = {
            n["metadata"]["name"]: n["metadata"].get("labels", {})
            for n in get_json("namespaces")["items"]
        }
        self.policies = get_json("networkpolicies", "-A")["items"]
        self.authz = get_json("authorizationpolicies.security.istio.io", "-A")["items"]
        self.peerauth = get_json("peerauthentications.security.istio.io", "-A")["items"]
        mesh = yaml.safe_load(
            kubectl(
                "-n", "istio-system", "get", "configmap", "istio", "-o", "jsonpath={.data.mesh}"
            )
        )
        self.trust_domain = mesh["trustDomain"]

    def enrolled(self, pod):
        return (
            self.ns_labels[pod["ns"]].get(AMBIENT) == "ambient"
            and pod["labels"].get(AMBIENT) != "none"
        )

    def principal(self, pod):
        if not self.enrolled(pod):
            return None
        return f"{self.trust_domain}/ns/{pod['ns']}/sa/{pod['sa']}"

    def strict(self, ns):
        return any(
            p["metadata"]["namespace"] == ns
            and not p["spec"].get("selector")
            and p["spec"].get("mtls", {}).get("mode") == "STRICT"
            for p in self.peerauth
        )

    def peer_matches(self, peer, pod, policy_ns):
        if "ipBlock" in peer:
            return False
        ns_sel = peer.get("namespaceSelector")
        if ns_sel is None:
            ns_ok = pod["ns"] == policy_ns
        else:
            ns_ok = matches(ns_sel, self.ns_labels[pod["ns"]])
        pod_sel = peer.get("podSelector")
        return ns_ok and (pod_sel is None or matches(pod_sel, pod["labels"]))

    @staticmethod
    def port_ok(ports, port):
        if not ports:
            return True
        for entry in ports:
            if isinstance(entry.get("port"), str):
                raise SystemExit("named ports in policies are not handled")
            if entry.get("port") == port and entry.get("protocol", "TCP") == "TCP":
                return True
        return False

    def np_allowed(self, target, peer, port, direction):
        key, side = ("from", "ingress") if direction == "Ingress" else ("to", "egress")
        selecting = [
            p
            for p in self.policies
            if p["metadata"]["namespace"] == target["ns"]
            and direction in p["spec"].get("policyTypes", [])
            and matches(p["spec"].get("podSelector", {}), target["labels"])
        ]
        if not selecting:
            return True
        for policy in selecting:
            policy_ns = policy["metadata"]["namespace"]
            for rule in policy["spec"].get(side, []):
                peers = rule.get(key)
                peer_ok = peers is None or any(self.peer_matches(e, peer, policy_ns) for e in peers)
                if peer_ok and self.port_ok(rule.get("ports"), port):
                    return True
        return False

    @staticmethod
    def source_ok(source, principal, pod):
        checks = []
        for key, values in source.items():
            if key == "principals":
                checks.append(principal in values)
            elif key == "namespaces":
                checks.append(principal is not None and pod["ns"] in values)
            elif key == "ipBlocks":
                address = ipaddress.ip_address(pod["ip"])
                checks.append(any(address in ipaddress.ip_network(c) for c in values))
            else:
                raise SystemExit(f"authorization source field {key} is not handled")
        return all(checks)

    def selecting_authz(self, target):
        selecting = []
        for policy in self.authz:
            if policy["metadata"]["namespace"] != target["ns"]:
                continue
            spec = policy.get("spec") or {}
            if spec.get("action", "ALLOW") != "ALLOW":
                raise SystemExit(f"authorization action {spec.get('action')} is not handled")
            selector = spec.get("selector")
            if selector is None or matches(selector, target["labels"]):
                selecting.append(spec)
        return selecting

    def mesh_allowed(self, source, target, port):
        if not self.enrolled(target):
            return True
        principal = self.principal(source)
        if self.strict(target["ns"]) and principal is None:
            return False
        selecting = self.selecting_authz(target)
        if not selecting:
            return True
        for spec in selecting:
            for rule in spec.get("rules", []):
                froms, tos = rule.get("from"), rule.get("to")
                from_ok = not froms or any(
                    self.source_ok(f["source"], principal, source) for f in froms
                )
                to_ok = not tos or any(
                    not t["operation"].get("ports") or str(port) in t["operation"]["ports"]
                    for t in tos
                )
                if from_ok and to_ok:
                    return True
        return False

    def expected(self, source, target, port):
        return (
            self.np_allowed(source, target, port, "Egress")
            and self.np_allowed(target, source, port, "Ingress")
            and self.mesh_allowed(source, target, port)
        )


def is_source(pod):
    return (
        pod["labels"].get("app.kubernetes.io/name") not in DATA_APPS
        and "cnpg.io/cluster" not in pod["labels"]
    )


def ensure_outsider(image):
    subprocess.run(
        [KUBECTL, "create", "namespace", OUTSIDER_NS], capture_output=True, text=True, check=False
    )
    for label in ("enforce", "warn", "audit"):
        kubectl(
            "label",
            "namespace",
            OUTSIDER_NS,
            f"pod-security.kubernetes.io/{label}=restricted",
            "--overwrite",
        )
    manifest = (HERE / "outsider.json").read_text().replace("IMAGE", image)
    kubectl("apply", "-f", "-", stdin=manifest)
    kubectl("-n", OUTSIDER_NS, "wait", "--for=condition=Ready", "pod/outsider", "--timeout=120s")


def run_probes(source, checks):
    if source["labels"].get("app.kubernetes.io/name") == "web":
        script, command = (HERE / "probe.js").read_text(), ["node", "-"]
    else:
        script, command = (HERE / "probe.py").read_text(), ["python", "-"]
    out = kubectl(
        "exec",
        "-i",
        "-n",
        source["ns"],
        source["name"],
        "-c",
        source["container"],
        "--",
        *command,
        json.dumps(checks),
        stdin=script,
    )
    return json.loads(out.strip().splitlines()[-1])


def gateway_checks():
    context = ssl.create_default_context(cafile=str(EDGE_CA))
    failures = []
    for path in ROUTES:
        request = urllib.request.Request(f"https://localhost{path}", method="GET")
        try:
            status = urllib.request.urlopen(request, context=context, timeout=5).status
        except urllib.error.HTTPError as exc:
            status = exc.code
        except OSError as exc:
            status = f"error {exc}"
        ok = isinstance(status, int) and status not in (502, 503, 504)
        print(f"  gateway {path:<12} {status} {'ok' if ok else 'FAIL'}")
        if not ok:
            failures.append(path)
    return failures


def prometheus_checks():
    forward = subprocess.Popen(
        [KUBECTL, "-n", "monitoring", "port-forward", "svc/prometheus-server", "19090:80"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        forward.stdout.readline()
        url = "http://127.0.0.1:19090/api/v1/targets"
        with urllib.request.urlopen(url, timeout=10) as response:
            targets = json.load(response)["data"]["activeTargets"]
    finally:
        forward.terminate()
        forward.wait()
    down = [
        f"{t['labels'].get('job')} {t['scrapeUrl']} {t.get('lastError', '')}"
        for t in targets
        if t["health"] != "up"
    ]
    print(f"  prometheus targets up {len(targets) - len(down)}/{len(targets)}")
    for line in down:
        print(f"  FAIL {line}")
    return down


def node_exporter_checks():
    nodes = [
        a["address"]
        for n in get_json("nodes")["items"]
        for a in n["status"]["addresses"]
        if a["type"] == "InternalIP"
    ]
    script = (HERE / "node_exporter_check.py").read_text()
    out = kubectl(
        "exec",
        "-i",
        "-n",
        OUTSIDER_NS,
        "outsider",
        "--",
        "python",
        "-",
        json.dumps(nodes),
        stdin=script,
    )
    failures = []
    for key, value in sorted(json.loads(out).items()):
        want = "401" if key.endswith("no token") else "closed"
        ok = value == want
        print(f"  node-exporter {key:<26} {value} {'ok' if ok else 'FAIL'}")
        if not ok:
            failures.append(key)
    return failures


def check_source(model, source, targets):
    checks, expected = [], {}
    for target in targets:
        if target["name"] == source["name"]:
            continue
        for port, name in target["ports"]:
            check_id = f"{target['name']}:{port}"
            expected[check_id] = model.expected(source, target, port)
            checks.append(
                {
                    "id": check_id,
                    "host": target["ip"],
                    "port": port,
                    "kind": "h2c" if name == "health" else "tls",
                }
            )
    got = run_probes(source, checks)
    who = f"{source['ns']}/{source['name']}"
    passed = 0
    for check_id, want in sorted(expected.items()):
        if got.get(check_id) == want:
            passed += 1
        else:
            print(f"  FAIL {who} -> {check_id} expected {word(want)} got {word(got.get(check_id))}")
    allows = sum(1 for v in expected.values() if v)
    print(f"  {who}: {len(expected)} checks, {allows} expected allow")
    return passed, len(expected)


def main():
    theft = [view(p) for p in get_json("pods", "-n", NAMESPACE)["items"] if live(p)]
    prom_pods = get_json("pods", "-n", "monitoring", "-l", PROMETHEUS_SELECTOR)["items"]
    prom = [view(p) for p in prom_pods if live(p)]
    not_ready = [p["name"] for p in theft + prom if not p["ready"]]
    if not_ready or not prom:
        raise SystemExit(f"aborting, not ready: {not_ready or 'prometheus-server missing'}")

    backend = next(p for p in theft if p["labels"].get("app.kubernetes.io/name") == "backend")
    ensure_outsider(backend["image"])
    try:
        outsider = view(get_json("pod", "outsider", "-n", OUTSIDER_NS))
        model = Model()
        sources = [p for p in theft if is_source(p)] + [outsider]
        total = passed = 0
        for source in sources:
            ok, count = check_source(model, source, theft + prom)
            passed += ok
            total += count
        print("===== routes, scrapes and node metrics")
        extra = gateway_checks() + prometheus_checks() + node_exporter_checks()
    finally:
        subprocess.run(
            [KUBECTL, "delete", "namespace", OUTSIDER_NS, "--wait=false"],
            capture_output=True,
            check=False,
        )
    tail = f"routes, scrapes and node metrics {'ok' if not extra else 'FAIL'}"
    print(f"===== pod-to-pod {passed}/{total} passed, {tail}")
    sys.exit(0 if passed == total and not extra else 1)


if __name__ == "__main__":
    main()
