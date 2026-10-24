#!/usr/bin/env python3
"""Backfill metadata.provenance and metadata.bibliography (src/provenance.py) into unified JSONs written before
the extractors recorded them. Nodes and edges are not touched, nothing is re-extracted; each file keeps its
JSON formatting, so a diff shows only the two new fields.

    # LLM silver / gold / blueprint extractions (model, prompt version, date from their own metadata)
    stamp_provenance.py corpus/silver/opus-5.5__v7 corpus/silver/opus-5.5__v7_gold ...
    # rules extractions on the cluster (sources found in the arXiv tree by id)
    stamp_provenance.py <parsed_100k_v7> --extractor rules --tool parse_batch --arxiv-tree <all_arxiv_papers> \
        --note "100K v7 run of 2026-10-22, job 46497998"

Only the JSONs directly in each directory are read (not subfolders). A file that already has
metadata.provenance is skipped unless --force. --dry-run reports what would change.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import provenance as PV                                   # noqa: E402

TEX_TEMPLATES = ("corpus/silver/tex_staged/{id}/source/{id}.tex", "corpus/silver/tex_staged/{id}/source/*.tex",
                 "corpus/silver/tex_pool/{id}.tex", "corpus/silver/tex_pool/{base}.tex",
                 "corpus/gold_candidates/papers/{id}/paper.tex", "corpus/gold_candidates/papers/{base}/paper.tex",
                 "corpus/gold_blueprints/{id}/all.tex")


def paper_id(f: Path, d: dict) -> str:
    md = d.get("metadata") or {}
    pid = md.get("arxiv_id") or md.get("paper_id") or f.stem
    return re.sub(r"_(rules|llm|both)$|_[\w.+-]*(claude|gpt)[\w.+-]*$", "", str(pid))


def find_tex(pid: str, tree: dict | None):
    base = re.sub(r"v\d+$", "", pid)
    if tree is not None:
        d = tree.get(base)
        if d:
            hits = sorted(d.glob("*.tex"))
            return hits[0] if hits else None
        return None
    for t in TEX_TEMPLATES:
        hits = sorted(REPO.glob(t.format(id=pid, base=base)))
        if hits:
            return hits[0]
    return None


def fmt(raw: str, d: dict):
    """(indent, ensure_ascii, trailing newline) that reproduce raw, or the repo default."""
    for ind in (1, 2, None, 4):
        for ea in (False, True):
            s = json.dumps(d, indent=ind, ensure_ascii=ea)
            if raw in (s, s + "\n"):
                return ind, ea, raw.endswith("\n")
    return 1, False, True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--extractor", help="rules / llm / both (default: llm when the JSON names a model)")
    ap.add_argument("--tool", help="default: 'agent + extraction_finalize' for llm, else 'parse_batch'")
    ap.add_argument("--model")
    ap.add_argument("--prompt-version")
    ap.add_argument("--edge-model")
    ap.add_argument("--date", help="extraction date, when the JSON does not say")
    ap.add_argument("--note", help="free text kept in provenance.note (e.g. which run made these)")
    ap.add_argument("--arxiv-tree", help="find sources by arXiv id under this all_arxiv_papers tree")
    ap.add_argument("--src-cache", help="folder of <arXiv id>/ source folders (.tar.gz / .bbl / .bib), for papers "
                                        "whose source here is a flattened .tex without its bibliography")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    tree = PV.arxiv_source_dirs(a.arxiv_tree) if a.arxiv_tree else None
    if tree is not None:
        print(len(tree), "papers in the arXiv tree", flush=True)
    for root in a.dirs:
        n = {"stamped": 0, "skipped_has_provenance": 0, "no_source": 0, "unreadable": 0, "entries": 0}
        for f in sorted(Path(root).glob("*.json")):
            try:
                raw = f.read_text(encoding="utf-8")
                d = json.loads(raw)
            except (OSError, ValueError):
                n["unreadable"] += 1
                continue
            if not isinstance(d, dict) or "nodes" not in d:
                continue
            md = d.get("metadata") or {}
            if md.get("provenance") and not a.force:
                n["skipped_has_provenance"] += 1
                continue
            model = a.model or md.get("model")
            extractor = a.extractor or ("llm" if model else "unknown")
            tool = a.tool or ("agent + extraction_finalize" if extractor == "llm" else "parse_batch")
            pid = paper_id(f, d)
            tex = find_tex(pid, tree)
            base = re.sub(r"v\d+$", "", pid)
            src_dir = tree.get(base) if tree is not None else next(
                (Path(a.src_cache) / x for x in (pid, base) if a.src_cache and (Path(a.src_cache) / x).is_dir()), None)
            n["no_source"] += tex is None
            ind, ea, nl = fmt(raw, d)
            PV.stamp(d, tex, backfill=True, src_dir=src_dir, extractor=extractor, tool=tool, model=model,
                     prompt_version=a.prompt_version or md.get("prompt_version"), effort=md.get("effort"),
                     edge_model=a.edge_model, date=a.date or md.get("extraction_date"), note=a.note,
                     source=str(tex.relative_to(REPO)) if tex and REPO in tex.parents else (str(tex) if tex else None))
            n["entries"] += len(d["metadata"].get("bibliography") or {})
            n["stamped"] += 1
            if not a.dry_run:
                tmp = f.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(d, indent=ind, ensure_ascii=ea) + ("\n" if nl else ""), encoding="utf-8")
                os.replace(tmp, f)
        print(root, n, flush=True)


if __name__ == "__main__":
    main()
