import gzip
import json
import re
import sys
from pathlib import Path

ROOT_MAIN_BUDGET_KB = 140.0
ROUTE_EXTRA_BUDGET_KB = 140.0
GZIP_LEVEL = 9
KB = 1024

BUILD = Path(__file__).resolve().parents[2] / "apps" / "web" / ".next"
APP_DIR = BUILD / "server" / "app"
MANIFEST_SUFFIX = "_client-reference-manifest.js"
CHUNK_PATTERN = re.compile(r"/_next/(static/chunks/[a-z0-9_-]+\.js)")


def gz_size(path: Path) -> int:
    return len(gzip.compress(path.read_bytes(), GZIP_LEVEL))


def gz_kb(relative: list[str] | set[str]) -> float:
    return sum(gz_size(BUILD / item) for item in relative) / KB


def route_of(manifest: Path) -> str:
    relative = manifest.relative_to(APP_DIR).as_posix()
    return relative.removesuffix(MANIFEST_SUFFIX).rstrip("/") or "/"


def main() -> int:
    build_manifest = json.loads((BUILD / "build-manifest.json").read_text(encoding="utf-8"))
    root_files = build_manifest["rootMainFiles"]
    root = gz_kb(root_files)
    poly = gz_kb(build_manifest["polyfillFiles"])
    total = sum(gz_size(chunk) for chunk in (BUILD / "static" / "chunks").glob("*.js")) / KB

    print(f"root main   {root:6.1f} KB gz  (budget {ROOT_MAIN_BUDGET_KB})")
    print(f"polyfills   {poly:6.1f} KB gz")
    print(f"all chunks  {total:6.1f} KB gz")
    print()

    failed = root > ROOT_MAIN_BUDGET_KB
    for manifest in sorted(APP_DIR.rglob(f"*{MANIFEST_SUFFIX}"), key=lambda p: p.as_posix()):
        chunks = set(CHUNK_PATTERN.findall(manifest.read_text(encoding="utf-8")))
        extra = gz_kb({chunk for chunk in chunks if chunk not in root_files})
        over = extra > ROUTE_EXTRA_BUDGET_KB
        failed = failed or over
        print(f"  {route_of(manifest):<32} +{extra:6.1f} KB gz  {'OVER' if over else 'ok'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
