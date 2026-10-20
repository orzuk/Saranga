#!/usr/bin/env python3
"""Add to each blueprint's macros.tex the macro files its root uses wherever they live (fetch_bp_macros.py
reads only blueprint/src/macros/{common,web,print}.tex; projects also keep them in preamble/, a .sty file or
elsewhere). From the repository tree (gh api): the .tex and .sty files in a blueprint root's folder (where
web.tex, print.tex or content.tex is) that define macros, state no result and are not in all.tex already.

    fetch_bp_macros_tree.py [--ids a,b] [--all-provenance]
"""
import argparse
import base64
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "corpus/gold_blueprints"
DEFINES = re.compile(r"\\(?:re)?newcommand|\\def\\|\\DeclareMathOperator|\\DeclarePairedDelimiter|\\NewDocumentCommand|\\let\\")
STATES = re.compile(r"\\begin\s*\{(?:theorem|lemma|definition|proposition|corollary)\*?\}")


def gh(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=120)
    return json.loads(r.stdout) if r.returncode == 0 else None


def fetch(repo, path):
    j = gh(f"repos/{repo}/contents/{path}")
    return base64.b64decode(j["content"]).decode("utf-8", "replace") if j and j.get("content") else None


def one(row):
    d = ROOT / row["id"]
    have = set(re.findall(r"^%%FILE (\S+)", (d / "all.tex").read_text(errors="replace"), re.M))
    mt = d / "macros.tex"
    old = mt.read_text(errors="replace") if mt.is_file() else ""
    have |= set(re.findall(r"^%%FILE (\S+)", old, re.M))
    tree = gh(f"repos/{row['repo']}/git/trees/HEAD?recursive=1")
    if not tree:
        return row["id"], "no tree"
    paths = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
    roots = {p.rsplit("/", 1)[0] for p in paths if re.search(r"(^|/)(web|print|content)\.tex$", p) and "/" in p}
    cands = [p for p in paths if p.endswith((".tex", ".sty")) and p not in have
             and any(p.startswith(r + "/") for r in roots) and not re.search(r"(^|/)(web|print|content)\.tex$", p)]
    add = []
    for p in cands:
        t = fetch(row["repo"], p)
        if t and DEFINES.search(t) and not STATES.search(t):
            add.append(f"%%FILE {p}\n{t}")
    if add:
        mt.write_text((old + "\n" if old else "") + "\n".join(add))
    return row["id"], f"+{len(add)} files ({len(cands)} candidates)"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ids", default="")
    ap.add_argument("--all-provenance", action="store_true")
    a = ap.parse_args()
    want = set(filter(None, a.ids.split(",")))
    for row in json.loads((ROOT / "index.json").read_text()):
        if not row.get("built") or (want and row["id"] not in want) or (
                not a.all_provenance and row["provenance"] not in ("human", "mixed")):
            continue
        print(*one(row), flush=True)


if __name__ == "__main__":
    main()
