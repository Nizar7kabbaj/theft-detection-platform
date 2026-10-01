import json
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "rotation-probe"


def tool(name):
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"missing tool: {name}")
    return path


KUBECTL = tool("kubectl")
ISTIOCTL = tool("istioctl")


def kubectl(*args, stdin=None):
    return subprocess.run(
        [KUBECTL, *args], check=True, capture_output=True, text=True, input=stdin
    ).stdout


def check_istioctl():
    out = subprocess.run([ISTIOCTL, "version"], check=True, capture_output=True, text=True).stdout
    versions = {line.split(":", 1)[1].split()[0] for line in out.splitlines() if "version:" in line}
    if len(versions) != 1:
        raise SystemExit(f"istioctl and the mesh run different versions:\n{out.strip()}")


def ztunnel_on(node):
    return kubectl(
        "-n",
        "istio-dataplane",
        "get",
        "pods",
        "-l",
        "app=ztunnel",
        "--field-selector",
        f"spec.nodeName={node}",
        "-o",
        "jsonpath={.items[0].metadata.name}",
    )


def print_chain(ztunnel):
    for _ in range(20):
        table = subprocess.run(
            [ISTIOCTL, "ztunnel-config", "certificates", f"{ztunnel}.istio-dataplane"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        rows = [line.split() for line in table.splitlines() if f"sa/{NAME}" in line]
        if rows:
            for row in rows:
                print(f"  {row[1]:<13} {row[4]}")
            return
        time.sleep(3)
    raise SystemExit("no certificate issued for the probe identity")


def main():
    check_istioctl()
    image = kubectl(
        "-n",
        "theft",
        "get",
        "deploy",
        "backend",
        "-o",
        "jsonpath={.spec.template.spec.containers[0].image}",
    )
    manifest = json.loads((HERE / "outsider.json").read_text().replace("IMAGE", image))
    manifest["metadata"] = {
        "name": NAME,
        "namespace": "theft",
        "labels": {"app.kubernetes.io/name": NAME},
    }
    manifest["spec"]["serviceAccountName"] = NAME
    kubectl("-n", "theft", "create", "serviceaccount", NAME)
    try:
        kubectl("apply", "-f", "-", stdin=json.dumps(manifest))
        kubectl("-n", "theft", "wait", "--for=condition=Ready", f"pod/{NAME}", "--timeout=120s")
        node = kubectl("-n", "theft", "get", "pod", NAME, "-o", "jsonpath={.spec.nodeName}")
        print_chain(ztunnel_on(node))
    finally:
        kubectl("-n", "theft", "delete", "pod", NAME, "--wait=true")
        kubectl("-n", "theft", "delete", "serviceaccount", NAME)


if __name__ == "__main__":
    main()
