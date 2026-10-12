#!/usr/bin/env python3
"""Stage the files of the public 'Your paper' Hugging Face Space into one folder.

    python3 scripts/stage_hf_extractor_space.py /tmp/saranga_space
    cd /tmp/saranga_space && python3 app.py          # test locally on :7860
    # then push the folder to a Docker Space, e.g. RHCPP/saranga-yours (see deploy/hf_space_extractor/)

Only what the rule-based extractor and the page builder import is copied: the Space
is public, so its files are visible.
"""
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FILES = [
    "deploy/hf_space_extractor/app.py:app.py",
    "deploy/hf_space_extractor/Dockerfile:Dockerfile",
    "deploy/hf_space_extractor/README.md:README.md",
    "portal/yours.py", "portal/papers_yours.html",
    "src/extract_arxiv_funcs.py", "src/LLMVersion/config.py", "src/LLMVersion/extract_arxiv_funcs.py", "src/LLMVersion/latex_clean.py",
    "src/LLMVersion/match_modes.py", "src/LLMVersion/math_classes.py", "src/LLMVersion/math_paper_parser.py",
    "src/LLMVersion/rule_guard.py", "src/LLMVersion/unit_rules.py",
    "src/algorithm_lines.py", "src/latex_facts.py", "src/latex_macros.py", "src/node_similarity.py",
    "src/proof_structure.py", "src/prose_units.py", "src/config.py", "src/link_to_foundation.py",
    "src/visualize_annotation.py", "src/node_types.py", "src/edge_types.py",
    "src/graph_view/build.py", "src/graph_view/template.html", "src/graph_view/viewer.css",
    "src/graph_view/viewer.js",
]
DIRS = ["extractors/rules/silver_v6__sentence_rules_haiku__2026-10"]


def main(out):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    for spec in FILES:
        src, _, dst = spec.partition(":")
        s, d = REPO / src, out / (dst or src)
        if not s.exists():
            print("  (skip, missing)", src)
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    for sub in DIRS:
        shutil.copytree(REPO / sub, out / sub)
    n = sum(1 for p in out.rglob("*") if p.is_file())
    print(f"staged {n} files in {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/saranga_space")
