import sys
from pathlib import Path

import yaml

source = Path(sys.argv[1])
target = Path(sys.argv[2])
document = yaml.safe_load(source.read_text())
for patch in document["spec"]["configPatches"]:
    config = patch["patch"]["value"].get("typed_config", {})
    for descriptor in config.get("descriptors", []):
        descriptor["token_bucket"] = {
            "max_tokens": 100000,
            "tokens_per_fill": 100000,
            "fill_interval": "1s",
        }
target.write_text(yaml.safe_dump(document, sort_keys=False))
print(f"edge profile written to {target}")
