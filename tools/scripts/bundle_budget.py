import json, glob, gzip, os, re, sys

ROOT_MAIN_BUDGET_KB = 140.0
ROUTE_EXTRA_BUDGET_KB = 140.0

BUILD = os.path.join(os.path.dirname(__file__), "..", "..", "apps", "web", ".next")
m = json.load(open(os.path.join(BUILD, "build-manifest.json")))
def gz(p): return len(gzip.compress(open(os.path.join(BUILD, p), "rb").read(), 9))

root = sum(gz(p) for p in m["rootMainFiles"]) / 1024
poly = sum(gz(p) for p in m["polyfillFiles"]) / 1024
total = sum(len(gzip.compress(open(f, "rb").read(), 9)) for f in glob.glob(os.path.join(BUILD, "static/chunks/*.js"))) / 1024

print(f"root main   {root:6.1f} KB gz  (budget {ROOT_MAIN_BUDGET_KB})")
print(f"polyfills   {poly:6.1f} KB gz")
print(f"all chunks  {total:6.1f} KB gz")
print()

failed = root > ROOT_MAIN_BUDGET_KB
for man in sorted(glob.glob(os.path.join(BUILD, "server/app/**/*_client-reference-manifest.js"), recursive=True)):
    route = man.split("server/app/")[1].replace("_client-reference-manifest.js", "").rstrip("/") or "/"
    chunks = set(re.findall(r'/_next/(static/chunks/[a-z0-9_-]+\.js)', open(man).read()))
    extra = sum(gz(c) for c in chunks if c not in m["rootMainFiles"]) / 1024
    flag = "OVER" if extra > ROUTE_EXTRA_BUDGET_KB else "ok"
    if extra > ROUTE_EXTRA_BUDGET_KB:
        failed = True
    print(f"  {route:<32} +{extra:6.1f} KB gz  {flag}")

sys.exit(1 if failed else 0)
