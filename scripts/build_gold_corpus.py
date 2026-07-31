#!/usr/bin/env python3
"""Consolidate research gold (human-annotated) papers into corpus/gold/, mirroring
the silver corpus layout.

Sources (research gold only -- the class_52017 student golds are intentionally
excluded):
    - root gold/<arxivid>.json                      (5 papers, objects/relations schema, human)
    - external <DATASET>/tier1/<arxivid>_<provider>.json
        provider = manual  -> human ground truth
                   anthropic/openai/rules -> baseline extractions of the same
                   gold papers (kept so model/prompt organization is visible)

Layout produced:
    corpus/gold/extractions/<group>/<paper_id>.json
        group = human__gold  | human__manual | anthropic__tier1 | openai__tier1 | rules__tier1
    corpus/gold/tex/<paper_id>.tex
    corpus/gold/manifest.csv        (same columns as silver, + role)

paper_id here IS the arXiv id (gold files are named by arXiv id), so no lookup
is needed. Idempotent; makes no network calls.
"""
import csv
import json
import os
import re
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.environ.get("SARANGA_DATA_ROOT", "/mnt/c/Datasets/Saranga_data")

GOLD_DIR = os.path.join(REPO, "gold")
TIER1_DIR = os.path.join(DATASET, "tier1")

OUT = os.path.join(REPO, "corpus/gold")   # model/prompt dirs live directly here
OUT_TEX = os.path.join(OUT, "tex")

PROVIDER_GROUP = {
    "manual": ("human", "manual", "gold"),
    "anthropic": ("anthropic", "tier1", "baseline"),
    "openai": ("openai", "tier1", "baseline"),
    "rules": ("rules", "tier1", "baseline"),
}

# short note written as prompt.md in each group dir (gold has no LLM prompt files)
GROUP_PROMPT_NOTE = {
    "human__gold": "Human manual annotation (root `gold/`, objects/relations schema). No LLM prompt.",
    "human__manual": "Human manual annotation (tier1 ground truth). No LLM prompt.",
    "anthropic__tier1": "Baseline Anthropic extraction of the tier1 gold papers. Exact prompt not recorded with the artifacts.",
    "openai__tier1": "Baseline OpenAI extraction of the tier1 gold papers. Exact prompt not recorded with the artifacts.",
    "rules__tier1": "Baseline rule-based extraction of the tier1 gold papers (regex rules, no LLM prompt).",
}

META_COLS = [
    "paper_id", "arxiv_id", "role", "model", "prompt_version", "annotator",
    "schema", "title", "n_nodes", "n_edges", "json_path", "tex_path", "has_tex",
]


def count_nodes_edges(doc):
    if "nodes" in doc or "edges" in doc:
        return len(doc.get("nodes", [])), len(doc.get("edges", [])), "nodes_edges"
    return len(doc.get("objects", [])), len(doc.get("relations", [])), "objects_relations"


def find_gold_tex(paper_id):
    """Search gold/tex/**/ for a tex whose name matches the arxiv id stem."""
    stem = paper_id.split("v")[0]
    tdir = os.path.join(GOLD_DIR, "tex")
    if not os.path.isdir(tdir):
        return None
    for root, _, files in os.walk(tdir):
        for fn in files:
            if fn.endswith(".tex") and (paper_id in fn or stem in fn):
                return os.path.join(root, fn)
    return None


def emit(rows, paper_id, arxiv_id, group, role, annotator, src_json, tex_src=None):
    model, prompt, _ = group
    sub = "%s__%s" % (model, prompt)
    dst_dir = os.path.join(OUT, sub)   # directly under corpus/gold/
    os.makedirs(dst_dir, exist_ok=True)
    pmd = os.path.join(dst_dir, "prompt.md")
    if not os.path.isfile(pmd):
        with open(pmd, "w", encoding="utf-8") as f:
            f.write("# Provenance for `%s`\n\n%s\n" % (
                sub, GROUP_PROMPT_NOTE.get(sub, "No prompt recorded.")))
    dst = os.path.join(dst_dir, paper_id + ".json")
    try:
        doc = json.load(open(src_json, encoding="utf-8"))
    except Exception as e:
        print("  SKIP %s: %s" % (src_json, e), file=sys.stderr)
        return
    shutil.copy2(src_json, dst)
    n_nodes, n_edges, schema = count_nodes_edges(doc)
    meta = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
    title = (meta.get("title") or "").strip()

    tex_rel = ""
    tex_out = os.path.join(OUT_TEX, paper_id + ".tex")
    if tex_src and os.path.isfile(tex_src) and not os.path.isfile(tex_out):
        shutil.copy2(tex_src, tex_out)
    if os.path.isfile(tex_out):
        tex_rel = os.path.relpath(tex_out, REPO)

    rows.append({
        "paper_id": paper_id, "arxiv_id": arxiv_id, "role": role,
        "model": model, "prompt_version": prompt, "annotator": annotator,
        "schema": schema, "title": title, "n_nodes": n_nodes, "n_edges": n_edges,
        "json_path": os.path.relpath(dst, REPO), "tex_path": tex_rel,
        "has_tex": "yes" if tex_rel else "no",
    })


def main():
    if os.path.isdir(OUT_TEX):
        shutil.rmtree(OUT_TEX)
    os.makedirs(OUT_TEX)
    legacy = os.path.join(OUT, "extractions")
    if os.path.isdir(legacy):
        shutil.rmtree(legacy)
    for name in os.listdir(OUT):
        p = os.path.join(OUT, name)
        if os.path.isdir(p) and "__" in name:
            shutil.rmtree(p)
    mp = os.path.join(OUT, "manifest.csv")
    if os.path.isfile(mp):
        os.remove(mp)
    rows = []

    # root gold/<arxivid>.json (skip templates / variants)
    for fn in sorted(os.listdir(GOLD_DIR)):
        if not fn.endswith(".json"):
            continue
        if "_manual_template" in fn or "_gold_from_diagram" in fn:
            continue
        pid = fn[:-5]
        arxiv = pid if re.match(r"^\d{4}\.\d{4,5}", pid) or "/" in pid else ""
        emit(rows, pid, arxiv, ("human", "gold", "gold"), "gold", "human",
             os.path.join(GOLD_DIR, fn), find_gold_tex(pid))

    # external tier1/<arxivid>_<provider>.json
    if os.path.isdir(TIER1_DIR):
        for fn in sorted(os.listdir(TIER1_DIR)):
            m = re.match(r"^(.+)_(manual|anthropic|openai|rules)\.json$", fn)
            if not m:
                continue
            arxiv, prov = m.group(1), m.group(2)
            group = PROVIDER_GROUP[prov]
            annotator = "human" if prov == "manual" else prov
            emit(rows, arxiv, arxiv, group, group[2], annotator,
                 os.path.join(TIER1_DIR, fn))
    else:
        print("  WARN tier1 dir missing: %s" % TIER1_DIR, file=sys.stderr)

    rows.sort(key=lambda r: (r["paper_id"], r["model"], r["prompt_version"]))
    with open(os.path.join(OUT, "metadata.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=META_COLS)
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    by_role = Counter(r["role"] for r in rows)
    by_sub = Counter("%s__%s" % (r["model"], r["prompt_version"]) for r in rows)
    print("rows: %d  distinct papers: %d" % (len(rows), len({r["paper_id"] for r in rows})))
    print("by role:", dict(by_role))
    print("by group:")
    for k, v in sorted(by_sub.items()):
        print("   %-24s %d" % (k, v))
    print("tex present: %d" % sum(1 for r in rows if r["has_tex"] == "yes"))


if __name__ == "__main__":
    main()
