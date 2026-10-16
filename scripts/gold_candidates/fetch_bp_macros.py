#!/usr/bin/env python3
"""Fetch each blueprint's macro files (blueprint/src/macros/{common,web,print}.tex) from GitHub into
corpus/gold_blueprints/<id>/macros.tex, read by blueprint_to_graph (1 request per second)."""
import json, time, urllib.request
from pathlib import Path
O = Path("/mnt/c/Code/Github/Saranga/corpus/gold_blueprints")
n = got = 0
for row in json.loads((O / "index.json").read_text()):
    d = O / row["id"]
    if (d / "macros.tex").is_file():
        got += 1; continue
    parts = []
    for name in ("common", "web", "print"):
        try:
            u = f"https://raw.githubusercontent.com/{row['repo']}/HEAD/blueprint/src/macros/{name}.tex"
            parts.append(f"%%FILE blueprint/src/macros/{name}.tex\n" + urllib.request.urlopen(u, timeout=30).read().decode("utf-8", "replace"))
        except Exception:
            pass
        time.sleep(1)
    n += 1
    if parts:
        (d / "macros.tex").write_text("\n".join(parts)); got += 1
print(got, "of", len(json.loads((O / "index.json").read_text())), "blueprints have macro files")
