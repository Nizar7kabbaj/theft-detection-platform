import json
import socket
import ssl
import sys
import urllib.error
import urllib.request

results = {}
for node in json.loads(sys.argv[-1]):
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        urllib.request.urlopen(f"https://{node}:9100/metrics", context=context, timeout=5)
        results[f"{node}:9100 no token"] = "200"
    except urllib.error.HTTPError as exc:
        results[f"{node}:9100 no token"] = str(exc.code)
    except OSError as exc:
        results[f"{node}:9100 no token"] = f"error {exc}"
    try:
        socket.create_connection((node, 8100), timeout=3).close()
        results[f"{node}:8100 raw"] = "open"
    except OSError:
        results[f"{node}:8100 raw"] = "closed"
print(json.dumps(results))
