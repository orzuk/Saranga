#!/usr/bin/env python3
"""Merge per-paper macro glossaries into each paper's `metadata.macros`.

The extractor writes `{metadata, nodes, edges}` and `build_macro_glossary.py`
writes a sibling glossary per paper. This joins the two so a consumer needs one
file, not two.

Macros are RECORDED, never expanded — see E143 in the v6 register: expanding
them collides (341 colliding expansions, 473 colliding names across the corpus),
and statements are verbatim spans of the *unexpanded* source, so expanding here
would break the verbatim audit.

Only `metadata.macros` is written. `n_macros`/`by_kind` from the glossary file
are deliberately NOT copied: both are derivable from the dict, and duplicating
them would create a second place for the same truth to drift.

Idempotent: re-running rewrites identical content. Writes are atomic (temp file
+ os.replace), and nodes/edges are asserted unchanged before the move.

  python3 scripts/merge_macros.py                 # merge all, in place
  python3 scripts/merge_macros.py --dry-run       # report only, write nothing
  python3 scripts/merge_macros.py --ids A,B       # a subset

Gold: the tier1 dirs share the silver schema and need no flag. The older
hand-built gold files have no metadata block, so they are skipped unless
--legacy-metadata is passed, which creates one.
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACT_DIR = os.path.join(REPO, "corpus", "silver", "opus-5__v5.1")
MACRO_DIR = os.path.join(REPO, "corpus", "silver", "macros")


def legacy_paper_id(doc):
    """Paper id for the older gold schemas, or None if this isn't one.

    Two shapes exist: `{paper_id, objects, relations}` (human__gold) and
    `{schema_version, paper: {paper_id}, ...}` (human__diagram).
    """
    if "objects" not in doc or "relations" not in doc:
        return None
    if isinstance(doc.get("paper_id"), str):
        return doc["paper_id"]
    paper = doc.get("paper")
    if isinstance(paper, dict) and isinstance(paper.get("paper_id"), str):
        return paper["paper_id"]
    return None


def merge_one(paper_path, macro_path, dry_run=False, legacy_metadata=False,
              macro_dir=None):
    """Returns (status, n_macros).

    status in {written, unchanged, missing_glossary, unsupported_schema}.
    """
    with open(paper_path, encoding="utf-8") as f:
        doc = json.load(f)

    # The corpus is not schema-uniform: the silver set and the tier1 gold
    # annotations are `{metadata, nodes, edges}`, but the older hand-built gold
    # files are `{paper_id, objects, relations}` with no metadata block at all.
    modern = (isinstance(doc.get("metadata"), dict)
              and "nodes" in doc and "edges" in doc)
    if not modern:
        pid = legacy_paper_id(doc)
        if pid is None or not legacy_metadata:
            return "unsupported_schema", 0
        # Opt-in: give the legacy file a metadata block, moving it toward the
        # unified shape. Its filename may not be the arxiv id (human__diagram
        # is `<id>_gold_from_diagram_and_tex.json`), so resolve by paper_id.
        if macro_dir:
            macro_path = os.path.join(macro_dir, pid + ".json")
        return _merge_legacy(paper_path, macro_path, doc, pid, dry_run)

    if not os.path.isfile(macro_path):
        return "missing_glossary", 0

    with open(macro_path, encoding="utf-8") as f:
        gloss = json.load(f)

    md = doc["metadata"]
    aid_paper = md.get("arxiv_id") or md.get("paper_id")
    aid_gloss = gloss.get("arxiv_id")
    if aid_paper and aid_gloss and aid_paper != aid_gloss:
        raise SystemExit(
            "id mismatch: %s has %r but glossary has %r"
            % (paper_path, aid_paper, aid_gloss)
        )

    macros = gloss.get("macros", {})
    if doc["metadata"].get("macros") == macros:
        return "unchanged", len(macros)
    if dry_run:
        return "written", len(macros)

    n_nodes, n_edges = len(doc["nodes"]), len(doc["edges"])
    doc["metadata"]["macros"] = macros

    tmp = paper_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)

    # Re-read what we are about to install: the merge must not touch the graph.
    with open(tmp, encoding="utf-8") as f:
        check = json.load(f)
    assert len(check["nodes"]) == n_nodes, "node count changed"
    assert len(check["edges"]) == n_edges, "edge count changed"
    assert check["metadata"]["macros"] == macros, "macros did not round-trip"
    os.replace(tmp, paper_path)
    return "written", len(macros)


def _merge_legacy(paper_path, macro_path, doc, pid, dry_run):
    """Add `metadata: {paper_id, macros}` to a legacy gold file.

    `objects`/`relations` are the annotation and are asserted untouched; the
    existing top-level keys are left exactly where they are.
    """
    if not os.path.isfile(macro_path):
        return "missing_glossary", 0
    with open(macro_path, encoding="utf-8") as f:
        macros = json.load(f).get("macros", {})

    existing = doc.get("metadata")
    if isinstance(existing, dict) and existing.get("macros") == macros:
        return "unchanged", len(macros)
    if dry_run:
        return "written", len(macros)

    n_obj, n_rel = len(doc["objects"]), len(doc["relations"])
    md = existing if isinstance(existing, dict) else {}
    md.setdefault("paper_id", pid)
    md["macros"] = macros
    # Put metadata first so the file reads like the unified schema.
    doc = {"metadata": md, **{k: v for k, v in doc.items() if k != "metadata"}}

    tmp = paper_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    with open(tmp, encoding="utf-8") as f:
        check = json.load(f)
    assert len(check["objects"]) == n_obj, "objects changed"
    assert len(check["relations"]) == n_rel, "relations changed"
    assert check["metadata"]["macros"] == macros, "macros did not round-trip"
    os.replace(tmp, paper_path)
    return "written", len(macros)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract-dir", default=EXTRACT_DIR)
    ap.add_argument("--macro-dir", default=MACRO_DIR)
    ap.add_argument("--ids", default=None, help="comma list; default = every paper")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--legacy-metadata", action="store_true",
                    help="for the older gold files ({paper_id, objects, "
                         "relations}), create a metadata block to hold macros")
    args = ap.parse_args()

    if args.ids:
        ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    else:
        ids = sorted(
            f[:-5] for f in os.listdir(args.extract_dir) if f.endswith(".json")
        )

    tally = {"written": 0, "unchanged": 0, "missing_glossary": 0,
             "unsupported_schema": 0}
    missing, unsupported, total_macros = [], [], 0
    for aid in ids:
        paper = os.path.join(args.extract_dir, aid + ".json")
        if not os.path.isfile(paper):
            print("  skip %s (no extraction)" % aid)
            continue
        status, n = merge_one(
            paper, os.path.join(args.macro_dir, aid + ".json"), args.dry_run,
            legacy_metadata=args.legacy_metadata, macro_dir=args.macro_dir
        )
        tally[status] += 1
        total_macros += n
        if status == "missing_glossary":
            missing.append(aid)
        elif status == "unsupported_schema":
            unsupported.append(aid)

    verb = "would write" if args.dry_run else "written"
    print("papers %-14s : %d" % (verb, tally["written"]))
    print("papers unchanged     : %d" % tally["unchanged"])
    print("papers w/o glossary  : %d" % tally["missing_glossary"])
    print("unsupported schema   : %d" % tally["unsupported_schema"])
    print("macros merged        : %d" % total_macros)
    if unsupported:
        print("\nNot {metadata, nodes, edges} — skipped, nothing written:")
        for aid in unsupported[:20]:
            print("   " + aid)
    if missing:
        print("\nNo glossary for these — run build_macro_glossary.py first:")
        for aid in missing[:20]:
            print("   " + aid)
    return 1 if (missing or unsupported) else 0


if __name__ == "__main__":
    sys.exit(main())
