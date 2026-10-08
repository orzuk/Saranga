#!/usr/bin/env python3
"""Render the v6 extraction prompt for one paper.

Fills the prompt's placeholders and the schema block, strips maintainer
comments, and refuses to write a prompt with a placeholder left unfilled.

    python3 scripts/render_v6_prompt.py 1705.02768v1 --out-dir corpus/silver/opus-5.5__v6 \
        --prompt-dir <scratch>/prompts --model claude-opus-5-5 --effort default
"""
import argparse
import csv
import hashlib
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from schema_for_prompts import render_prompt  # noqa: E402

PROMPT = REPO / "scripts" / "opus_extract_prompt_v6.md"
PLACEHOLDERS = ("BID", "TITLE", "AUTHORS", "YEAR", "TEX_SOURCE", "OUTPUT_JSON",
                "REPO", "MODEL", "EFFORT", "PROMPT_VERSION")


def paper_row(bid):
    for r in csv.DictReader(open(REPO / "corpus" / "silver" / "metadata.csv")):
        if bid in (r["paper_id"], r["arxiv_id"]) and r["has_tex"] == "yes":
            return r
    sys.exit(f"{bid}: not in corpus/silver/metadata.csv with a .tex")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("bids", nargs="+")
    ap.add_argument("--out-dir", required=True, help="where the extraction JSONs go")
    ap.add_argument("--prompt-dir", required=True, help="where the rendered prompts go")
    ap.add_argument("--model", required=True)
    ap.add_argument("--effort", required=True)
    a = ap.parse_args()
    template = render_prompt(PROMPT.read_text())
    Path(a.prompt_dir).mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(template.encode()).hexdigest()[:16]
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip() or "unknown"
    version = f"v6-{sha}-{commit}"             # the exact prompt and code of this run
    print(f"prompt sha256 {sha}  version {version}")
    for bid in a.bids:
        r = paper_row(bid)
        tex = REPO / r["tex_path"]
        values = {
            "BID": r["arxiv_id"] or bid,
            "TITLE": r["title"],
            "AUTHORS": "(see the source)",
            "YEAR": r["published"][:4] or "(see the source)",
            "TEX_SOURCE": str(tex),
            "OUTPUT_JSON": str((REPO / a.out_dir / f"{bid}.json").resolve()),
            "REPO": str(REPO),
            "MODEL": a.model,
            "EFFORT": a.effort,
            "PROMPT_VERSION": version,
        }
        text = template
        for k, v in values.items():
            text = text.replace("{" + k + "}", v)
        left = [k for k in PLACEHOLDERS if "{" + k + "}" in text]
        if left or "<!--" in text or "{{" in text:
            sys.exit(f"{bid}: unfilled {left or 'comment/schema block'}")
        if not tex.exists():
            sys.exit(f"{bid}: {tex} missing")
        out = Path(a.prompt_dir) / f"{bid}.md"
        out.write_text(text)
        print(f"{bid}\t{out}")


if __name__ == "__main__":
    main()
