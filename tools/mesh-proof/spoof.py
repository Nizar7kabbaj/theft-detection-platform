import json
import sys

from proof import HERE, PROMETHEUS_SELECTOR, Model, get_json, kubectl, live, run_probes, view

NAME = "spoof"


def word(allowed):
    return "allow" if allowed else "deny"


def main():
    theft = [view(p) for p in get_json("pods", "-n", "theft")["items"] if live(p)]
    prom_pods = get_json("pods", "-n", "monitoring", "-l", PROMETHEUS_SELECTOR)["items"]
    prom = [view(p) for p in prom_pods if live(p)]
    backend = next(p for p in theft if p["labels"].get("app.kubernetes.io/name") == "backend")
    labels = {k: v for k, v in backend["labels"].items() if k != "pod-template-hash"}
    manifest = json.loads((HERE / "outsider.json").read_text().replace("IMAGE", backend["image"]))
    manifest["metadata"] = {"name": NAME, "namespace": "theft", "labels": labels}
    kubectl("apply", "-f", "-", stdin=json.dumps(manifest))
    try:
        kubectl("-n", "theft", "wait", "--for=condition=Ready", f"pod/{NAME}", "--timeout=120s")
        spoof = view(get_json("pod", NAME, "-n", "theft"))
        model = Model()
        targets = [
            (t, port, name)
            for t in theft + prom
            if t["name"] != backend["name"]
            for port, name in t["ports"]
            if model.expected(backend, t, port)
        ]
        checks = [
            {
                "id": f"{t['name']}:{port}",
                "host": t["ip"],
                "port": port,
                "kind": "h2c" if name == "health" else "tls",
            }
            for t, port, name in targets
        ]
        np_open = all(
            model.np_allowed(spoof, t, port, "Egress")
            and model.np_allowed(t, spoof, port, "Ingress")
            for t, port, _ in targets
        )
        print(f"backend identity: {model.principal(backend)}")
        print(f"spoof identity:   {model.principal(spoof)}")
        print(f"networkpolicy opens all {len(checks)} backend flows to the spoof: {np_open}")
        real = run_probes(backend, checks)
        fake = run_probes(spoof, checks)
        failures = 0
        for check in checks:
            r, f = real[check["id"]], fake[check["id"]]
            status = "ok" if r and not f else "FAIL"
            failures += status == "FAIL"
            print(f"  {check['id']:<42} backend {word(r):<5}  spoof {word(f):<5}  {status}")
        denied = len(checks) - failures
        print(f"===== identity {denied}/{len(checks)}: allowed to backend, denied to the spoof")
        sys.exit(1 if failures or not np_open else 0)
    finally:
        kubectl("-n", "theft", "delete", "pod", NAME, "--wait=false")


if __name__ == "__main__":
    main()
