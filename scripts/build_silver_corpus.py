#!/usr/bin/env python3
"""Consolidate all silver (LLM-extracted) papers into one organized in-repo corpus.

Produces:
    corpus/silver/extractions/<model>__<prompt>/paperNNN.json   (organized by model+prompt)
    corpus/silver/tex/paperNNN.tex                              (source LaTeX, one per paper)
    corpus/silver/manifest.csv                                  (one row per extraction)

Sources (paperNNN is a stable paper identity; the SAME paper may be extracted
by several model/prompt combos -- those are separate rows, by design):
    - pool  : external old set  <DATASET>/tier2/paper*.json   (opus-4-7 / v3_combined)
    - train : portal/data/tier2/paper*.json                    (17, v4.1)
    - test  : portal/data/tier2_test/json/paper*.json          (60, v4.1)

arxiv_id is seeded from the test manifest and from valid ids already in the JSON
metadata; the rest are filled by a separate title->arXiv lookup pass
(build_silver_arxiv.py), which reads/writes .arxiv_cache.json.

Idempotent: rebuilds corpus/silver/{extractions,tex} from scratch each run.
Offline: makes NO network calls (arXiv lookup is a separate script).

NOT covered here: `corpus/silver/opus-5__v5.1/` (see AUTHORITATIVE_DIRS). It is
authoritative in place rather than mirrored, so this script neither wipes nor
indexes it. Because metadata.csv is rewritten from scratch, the required order
on a full rebuild is:

    python scripts/build_silver_corpus.py     # mirrors + metadata.csv (345 rows)
    python scripts/index_opus5_v51.py         # adds the 200 v5.1 rows back

Running this on a machine WITHOUT the external pool (POOL_DIR) silently drops
the 268 `pool` rows — it does not fail. Check the printed row count.
"""
import csv
import json
import os
import re
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.environ.get("SARANGA_DATA_ROOT", "/mnt/c/Datasets/Saranga_data")

POOL_DIR = os.path.join(DATASET, "tier2")
TRAIN_DIR = os.path.join(REPO, "portal/data/tier2")
TEST_DIR = os.path.join(REPO, "portal/data/tier2_test/json")
TEST_MANIFEST = os.path.join(REPO, "portal/data/tier2_test/manifest.csv")

TEX_SOURCES = [
    os.path.join(REPO, "portal/data/tier2_tex"),          # train
    os.path.join(REPO, "portal/data/tier2_test/tex"),     # test
]

OUT = os.path.join(REPO, "corpus/silver")   # model/prompt dirs live directly here
OUT_TEX = os.path.join(OUT, "tex")
CACHE = os.path.join(OUT, ".arxiv_cache.json")

# Extraction dirs this builder must NEVER wipe: they are authoritative in place,
# not mirrors of an external source. opus-5__v5.1 was produced by the agentic
# extraction campaign directly into corpus/silver/ and is the ONLY copy, so
# rmtree-ing it on a machine that lacks POOL_DIR would be unrecoverable data
# loss. It is indexed separately by scripts/index_opus5_v51.py, which is
# additive and does not touch rows this builder owns.
AUTHORITATIVE_DIRS = {"opus-5__v5.1"}

ARXIV_RE = re.compile(r"^(\d{4}\.\d{4,5}(v\d+)?|[a-z\-]+/\d{7}(v\d+)?)$", re.I)

# Minimum fuzzy title-match score to trust an arXiv title-search hit. Below this,
# leave arxiv_id blank rather than record a likely-wrong id (many old "pool"
# papers are pre-arXiv classics — Shannon 1948, EM 1977 — with no arXiv version,
# for which the search returns spurious matches).
ARXIV_MIN_SCORE = 0.90

META_COLS = [
    "paper_id", "arxiv_id", "arxiv_source", "arxiv_match_score",
    "split", "test_idx", "tier",
    "model", "prompt_version", "prompt_version_raw", "prompt_file",
    "extraction_date", "annotator",
    "primary_category", "all_categories", "published", "title",
    "short_name", "topic", "n_nodes", "n_edges",
    "json_path", "tex_path", "has_tex",
]

# raw metadata prompt_version -> canonical (folder) prompt_version.
# `v3_combined_with_steps` was only an early explicit label for the same
# step-decomposition config that later runs just tag `v3_combined`.
CANON_PROMPT = {
    "v3_combined_with_steps": "v3_combined",
}

# canonical prompt_version -> (source prompt file, in-dir filename).
PROMPT_SPEC = {
    "v4.1": ("scripts/opus_extract_prompt_v4.md", "prompt_opus_v4.md"),
    "v3_combined": ("scripts/opus_extract_prompt_v3_combined.md",
                    "prompt_opus_v3_combined.md"),
}


def norm_id(name):
    """paper20 / paper020.json / paper20.tex -> 'paper020'."""
    m = re.search(r"paper0*(\d+)", os.path.basename(name))
    if not m:
        return None
    return "paper%03d" % int(m.group(1))


def short_model(model):
    """'claude-opus-4-7' -> 'opus-4.7' (drop redundant vendor prefix, dot version)."""
    m = (model or "unknown_model").replace("/", "-")
    m = re.sub(r"^claude-", "", m)
    return re.sub(r"(?<=\d)-(?=\d)", ".", m)


def safe_dir(model, prompt):
    p = (prompt or "unknown_prompt").replace("/", "-")
    return "%s__%s" % (short_model(model), p)


def valid_arxiv(x):
    return bool(x) and bool(ARXIV_RE.match(str(x).strip()))


def count_nodes_edges(doc):
    if "nodes" in doc or "edges" in doc:
        return len(doc.get("nodes", [])), len(doc.get("edges", []))
    # legacy objects/relations schema
    return len(doc.get("objects", [])), len(doc.get("relations", []))


def write_prompt_md(dst_dir, model, prompt):
    """Copy the actual extraction prompt into the dir, named after its source file.
    Returns the in-dir filename (or None)."""
    spec = PROMPT_SPEC.get(prompt)
    if not spec:
        return None
    rel, fname = spec
    header = (
        "# Extraction prompt for `%s` (prompt version `%s`)\n\n"
        "This is the verbatim prompt used to produce every JSON in this directory.\n"
    ) % (short_model(model), prompt)
    body = ""
    if os.path.isfile(os.path.join(REPO, rel)):
        header += "Source: `%s`.\n" % rel
        if prompt == "v4.1" and os.path.isfile(os.path.join(REPO, "scripts/in_session_extract_prompt.md")):
            header += ("Run in-session via `scripts/in_session_extract_prompt.md`, "
                       "which renders this file.\n")
        body = open(os.path.join(REPO, rel), encoding="utf-8").read()
    else:
        header += "_(Source prompt file not found.)_\n"
    with open(os.path.join(dst_dir, fname), "w", encoding="utf-8") as f:
        f.write(header + "\n---\n\n" + body)
    return fname


def load_test_manifest():
    """paper_id -> dict(arxiv_id, test_idx, tier, topic, primary_category,
    all_categories, published, short_name)."""
    rows = {}
    with open(TEST_MANIFEST, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows[r["paper_id"]] = r
    return rows


def collect_source(src_dir, split):
    """Yield (paper_id, json_path) for every paperNNN.json in src_dir."""
    if not os.path.isdir(src_dir):
        print("  WARN missing source dir: %s" % src_dir, file=sys.stderr)
        return
    for fn in sorted(os.listdir(src_dir)):
        if not fn.endswith(".json") or not fn.startswith("paper"):
            continue
        pid = norm_id(fn)
        if pid:
            yield pid, os.path.join(src_dir, fn), split


def find_tex(pid):
    """Return an absolute tex path for a paper identity, or None."""
    for d in TEX_SOURCES:
        for cand in (pid + ".tex", pid.replace("paper", "paper") + ".tex"):
            p = os.path.join(d, cand)
            if os.path.isfile(p):
                return p
    # external per-paper source dir (filenames are unpadded: paper20.tex)
    n = int(pid.replace("paper", ""))
    for name in ("paper%03d" % n, "paper%d" % n):
        sd = os.path.join(POOL_DIR, name, "source")
        if os.path.isdir(sd):
            texs = [f for f in os.listdir(sd) if f.endswith(".tex")]
            if texs:
                # prefer a file whose stem matches the paper number
                texs.sort(key=lambda f: (0 if str(n) in f else 1, len(f)))
                return os.path.join(sd, texs[0])
    return None


def main():
    # wipe previously-generated content (tex/ + every model__prompt dir), but
    # keep README.md and the .arxiv_cache.json.
    if os.path.isdir(OUT_TEX):
        shutil.rmtree(OUT_TEX)
    os.makedirs(OUT_TEX)
    for name in os.listdir(OUT):
        p = os.path.join(OUT, name)
        if os.path.isdir(p) and "__" in name and name not in AUTHORITATIVE_DIRS:
            shutil.rmtree(p)
    legacy = os.path.join(OUT, "extractions")   # pre-flatten layout
    if os.path.isdir(legacy):
        shutil.rmtree(legacy)
    for stale in ("manifest.csv", "arxiv_resolution.csv"):
        sp = os.path.join(OUT, stale)
        if os.path.isfile(sp):
            os.remove(sp)

    prompt_copied = set()   # model__prompt dirs whose prompt.md is already written
    test_meta = load_test_manifest()
    cache = {}
    if os.path.isfile(CACHE):
        cache = json.load(open(CACHE))

    sources = (
        list(collect_source(POOL_DIR, "pool"))
        + list(collect_source(TRAIN_DIR, "train"))
        + list(collect_source(TEST_DIR, "test"))
    )

    rows = []
    tex_done = set()
    for pid, jpath, split in sources:
        try:
            doc = json.load(open(jpath, encoding="utf-8"))
        except Exception as e:
            print("  SKIP unreadable %s: %s" % (jpath, e), file=sys.stderr)
            continue
        meta = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        model = meta.get("model") or "unknown_model"
        prompt_raw = meta.get("prompt_version") or "unknown_prompt"
        prompt = CANON_PROMPT.get(prompt_raw, prompt_raw)   # fold _with_steps
        n_nodes, n_edges = count_nodes_edges(doc)

        # organize by model+prompt (dirs sit directly under corpus/silver/)
        sub = safe_dir(model, prompt)
        dst_dir = os.path.join(OUT, sub)
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, pid + ".json")
        shutil.copy2(jpath, dst)
        json_rel = os.path.relpath(dst, REPO)

        # drop the actual extraction prompt into each dir, once
        if sub not in prompt_copied:
            write_prompt_md(dst_dir, model, prompt)
            prompt_copied.add(sub)

        # tex (once per paper identity)
        tex_rel = ""
        if pid not in tex_done:
            tp = find_tex(pid)
            if tp:
                shutil.copy2(tp, os.path.join(OUT_TEX, pid + ".tex"))
                tex_done.add(pid)
        if os.path.isfile(os.path.join(OUT_TEX, pid + ".tex")):
            tex_rel = os.path.relpath(os.path.join(OUT_TEX, pid + ".tex"), REPO)

        # arxiv id + enrichment (record HOW it was resolved)
        tm = test_meta.get(pid, {})
        arxiv = ""
        arxiv_source = ""
        arxiv_score = ""
        primary = all_cats = published = ""
        if split == "test" and tm and tm.get("arxiv_id"):
            arxiv = tm.get("arxiv_id", "") or ""
            arxiv_source = "test_manifest"
            primary = tm.get("primary_category", "") or ""
            all_cats = tm.get("all_categories", "") or ""
            published = tm.get("published", "") or ""
        if not arxiv:
            for k in ("arxiv_id", "arxiv", "bid"):
                if valid_arxiv(meta.get(k)):
                    arxiv = str(meta[k]).strip()
                    arxiv_source = "json_metadata"
                    break
        if (not arxiv and pid in cache and valid_arxiv(cache[pid].get("arxiv_id"))
                and cache[pid].get("score", 0) >= ARXIV_MIN_SCORE):
            c = cache[pid]
            arxiv = c["arxiv_id"]
            arxiv_source = "title_search"
            arxiv_score = c.get("score", "")
            primary = primary or c.get("primary_category", "")
            all_cats = all_cats or c.get("all_categories", "")
            published = published or c.get("published", "")

        rows.append({
            "paper_id": pid,
            "arxiv_id": arxiv,
            "arxiv_source": arxiv_source,
            "arxiv_match_score": arxiv_score,
            "split": split,
            "test_idx": tm.get("test_idx", ""),
            "tier": tm.get("tier", ""),
            "model": short_model(model),
            "prompt_version": prompt,
            "prompt_version_raw": prompt_raw,
            "prompt_file": (PROMPT_SPEC.get(prompt) or ("", ""))[0],
            "extraction_date": meta.get("extraction_date", ""),
            "annotator": meta.get("annotator", ""),
            "primary_category": primary,
            "all_categories": all_cats,
            "published": published,
            "title": (meta.get("title") or tm.get("title") or "").strip(),
            "short_name": tm.get("short_name", ""),
            "topic": tm.get("topic", ""),
            "n_nodes": n_nodes,
            "n_edges": n_edges,
            "json_path": json_rel,
            "tex_path": tex_rel,
            "has_tex": "yes" if tex_rel else "no",
        })

    rows.sort(key=lambda r: (r["paper_id"], r["prompt_version"], r["model"]))
    # ONE combined metadata file (manifest + arXiv-resolution provenance).
    with open(os.path.join(OUT, "metadata.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=META_COLS)
        w.writeheader()
        w.writerows(rows)

    # summary
    from collections import Counter
    by_split = Counter(r["split"] for r in rows)
    by_sub = Counter(safe_dir(r["model"], r["prompt_version"]) for r in rows)
    have_arxiv = sum(1 for r in rows if r["arxiv_id"])
    have_tex = sum(1 for r in rows if r["has_tex"] == "yes")
    print("rows: %d  distinct papers: %d" % (len(rows), len({r["paper_id"] for r in rows})))
    print("by split:", dict(by_split))
    print("by model__prompt:")
    for k, v in sorted(by_sub.items()):
        print("   %-40s %d" % (k, v))
    print("arxiv_id present: %d/%d   tex present: %d papers" % (have_arxiv, len(rows), have_tex))

    # This builder owns only the dirs it mirrors, and it rewrites metadata.csv
    # from scratch — which drops the opus-5 v5.1 rows and the span_usable
    # column. Re-add them; the indexer is additive and idempotent.
    for d in sorted(AUTHORITATIVE_DIRS):
        if os.path.isdir(os.path.join(OUT, d)):
            print("\nNOTE %s is authoritative in place (not mirrored, not wiped)."
                  "\n     Its rows are NOT in the metadata.csv just written."
                  "\n     Run:  python scripts/index_opus5_v51.py" % d)
            break


if __name__ == "__main__":
    main()
