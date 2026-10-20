#!/usr/bin/env python3
"""Quality scan of the gold blueprints: one row per blueprint, with the problems that make it a weak gold.

    python3 scripts/gold_candidates/blueprint_quality.py   ->  corpus/gold_blueprints/quality.json (+ a table on stdout)

Per blueprint (human or mixed, built, with blueprint.tex): statements and proofs; the share with no text (under
15 characters once macros, braces and math delimiters are removed, or "No documentation."); placeholder proofs
("To do.", "Test.", "TODO", "sorry"); dependencies declared inside empty proofs; \\uses targets that are no
statement (dangling); duplicate labels; \\input/\\include files missing from the download; statements with no
dependency at all; size. Flags, in order of severity:
  drop      most statements have no text (a skeleton generated from the Lean code)
  nodeps    no declared dependency at all
  empty     most proofs have no text (score with empty proofs left out)
  partial   chapters missing from the download (input and gold are both partial: fair, but incomplete)
  sparse    under a third of the statements take part in any dependency
  dangling  over 5% of the dependencies point at no statement
  huge      over 300 KB of LaTeX
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "corpus/gold_blueprints"
PLACEHOLDER = re.compile(r"^\W*(to\s*do|todo|test|sorry|tbd|proof\s*omitted|see\s*lean|omitted)\W*$", re.I)


def clean(t):
    return re.sub(r"\\[a-zA-Z]+\*?(\{[^{}]*\})?|[\s{}$~]", "", t or "")


def empty(t):
    c = clean(t)
    return len(c) < 15 or "Nodocumentation" in c


def scan(x):
    d = ROOT / x["id"]
    g = json.loads((d / "graph.json").read_text())
    tex = (d / "all.tex").read_text(errors="replace")
    stm = [n for n in g["nodes"] if n["type"] != "proof"]
    prf = [n for n in g["nodes"] if n["type"] == "proof"]
    ids = {n["id"] for n in g["nodes"]}
    e_prf = {n["id"] for n in prf if empty(n.get("statement")) or PLACEHOLDER.match(re.sub(r"\s+", " ", n.get("statement") or ""))}
    deps = [e for e in g["edges"] if e.get("type") == "uses"]
    touched = {i for e in g["edges"] for i in (e["source"], e["target"])}
    labels = re.findall(r"\\label\{([^}]*)\}", tex)
    files = re.findall(r"^%%FILE (\S+)", tex, re.M)                  # all.tex holds every downloaded file
    inputs = [i for i in re.findall(r"^[^%\n]*\\(?:input|include)\{([^}]*)\}", tex, re.M)
              if not any(f.endswith((i, i + ".tex")) for f in files) and "\\" not in i and "#" not in i]
    r = {"id": x["id"], "provenance": x["provenance"], "area": x.get("area"), "kb": round((d / "blueprint.tex").stat().st_size / 1000),
         "statements": len(stm), "proofs": len(prf), "deps": len(deps),
         "empty_statements": sum(empty(n.get("statement")) for n in stm), "empty_proofs": len(e_prf),
         "deps_in_empty_proofs": sum(e["target"] in e_prf for e in deps),
         "dangling": sum(e["source"] not in ids or e["target"] not in ids for e in g["edges"]),
         "duplicate_labels": len(labels) - len(set(labels)), "missing_inputs": len(inputs),
         "isolated_statements": sum(n["id"] not in touched for n in stm)}
    s, p = max(1, r["statements"]), max(1, r["proofs"])
    r["flags"] = [f for f, c in (
        ("drop", r["empty_statements"] / s > 0.5),
        ("nodeps", r["deps"] == 0),
        ("empty", r["proofs"] and r["empty_proofs"] / p > 0.5),
        ("partial", r["missing_inputs"] > 0),
        ("sparse", (s - r["isolated_statements"]) / s < 1 / 3),
        ("dangling", r["dangling"] > 0.05 * max(1, len(g["edges"]))),
        ("huge", r["kb"] > 300)) if c]
    return r


def main():
    idx = json.loads((ROOT / "index.json").read_text())
    rows = [scan(x) for x in idx if x.get("built") and x["provenance"] in ("human", "mixed") and (ROOT / x["id"] / "blueprint.tex").is_file()]
    order = ["drop", "nodeps", "empty", "partial", "sparse", "dangling", "huge"]
    rows.sort(key=lambda r: (min([order.index(f) for f in r["flags"]] or [9]), r["id"]))
    (ROOT / "quality.json").write_text(json.dumps(rows, indent=1))
    from collections import Counter
    print(len(rows), "blueprints; flags:", dict(Counter(f for r in rows for f in r["flags"])), "; clean:", sum(not r["flags"] for r in rows))
    print(f"{'blueprint':48s} {'flags':22s} {'KB':>5s} {'stm':>4s} {'prf':>4s} {'dep':>5s} {'e.st':>5s} {'e.pr':>5s} {'dep@e':>5s} {'dang':>4s} {'miss':>4s} {'iso':>4s}")
    for r in rows:
        if r["flags"]:
            print(f"{r['id'][:48]:48s} {','.join(r['flags']):22s} {r['kb']:5d} {r['statements']:4d} {r['proofs']:4d} {r['deps']:5d} "
                  f"{r['empty_statements']:5d} {r['empty_proofs']:5d} {r['deps_in_empty_proofs']:5d} {r['dangling']:4d} {r['missing_inputs']:4d} {r['isolated_statements']:4d}")


if __name__ == "__main__":
    main()
