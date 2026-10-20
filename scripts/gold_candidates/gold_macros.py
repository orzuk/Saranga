#!/usr/bin/env python3
"""Record each gold extraction's macro definitions in its metadata.macros, as merge_macros.py does for the silver.

The rule-based parser expands a paper's macros in its matching text but keeps raw_latex as written, and the viewer
(src/visualize_annotation.py) expands raw_latex only from metadata.macros: without them a page shows \\fhh, \\Nil
in red. The definitions come from the extraction's own input (read with latex_macros.read_definitions, as the
silver glossaries):

  author      corpus/gold_candidates/papers/<id>/{full,rules,tagger}.json   paper.tex and the authors' *.sty there
  blueprint   corpus/gold_blueprints/<id>/{rules,tagger}.json             blueprint.tex (with macros.tex's definitions)
              corpus/gold_blueprints/<id>/paper/full.json                 the paper's source folder (*.tex, *.sty)

    gold_macros.py [--sets author,blueprint] [--build]      (--build: rebuild the viewer pages of changed files)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src")]
import latex_macros as L                                   # noqa: E402

BUILD = REPO / "src" / "graph_view" / "build.py"


def definitions(files) -> dict:
    src = "\n".join(Path(f).read_text(encoding="utf-8", errors="replace") for f in files if Path(f).is_file())
    return L.read_definitions(src) if src else {}


def record(graph_file: Path, macros: dict) -> bool:
    """Write macros into graph_file's metadata.macros; True if the file changed."""
    if not graph_file.is_file():
        return False
    g = json.loads(graph_file.read_text())
    if (g.get("metadata") or {}).get("macros") == macros:
        return False
    g.setdefault("metadata", {})["macros"] = macros
    graph_file.write_text(json.dumps(g))
    return True


def author(d: Path) -> list:
    m = definitions([d / "paper.tex", *sorted(d.glob("*.sty"))])
    return [f for f in (d / "full.json", d / "rules.json", d / "tagger.json") if record(f, m)]


def blueprint(d: Path) -> list:
    out = [f for f in (d / "rules.json", d / "tagger.json") if record(f, definitions([d / "blueprint.tex"]))]
    src = d / "paper" / "source"
    if (d / "paper" / "full.json").is_file() and src.is_dir():
        if record(d / "paper" / "full.json", definitions(sorted(src.rglob("*.tex")) + sorted(src.rglob("*.sty")))):
            out.append(d / "paper" / "full.json")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sets", default="author,blueprint")
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    changed = []
    if "author" in a.sets:
        changed += [f for d in sorted((REPO / "corpus/gold_candidates/papers").iterdir()) if d.is_dir() for f in author(d)]
    if "blueprint" in a.sets:
        changed += [f for d in sorted((REPO / "corpus/gold_blueprints").iterdir())
                    if d.is_dir() and (d / "blueprint.tex").is_file() for f in blueprint(d)]
    print(len(changed), "files given macros")
    if a.build:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(6) as pool:
            list(pool.map(lambda f: subprocess.run([sys.executable, str(BUILD), str(f), "-o", str(f.parent), "--libs", "cdn"],
                                                   capture_output=True, timeout=600), changed))
        print("pages rebuilt")


if __name__ == "__main__":
    main()
