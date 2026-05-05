#!/usr/bin/env python3
"""
Build portal/data/manifest.json by walking data/{tier1,tier2,tier3-sample,pairs}/.

Pairs section now lists ALL master pairs (from
math_papers_pairs_enriched.csv), each tagged with a status:
    annotated  — alignment JSON exists in data/pairs/<pair_id>_alignment.json
    ready      — both papers extracted (tier1/tier2 JSONs), no alignment yet
    partial    — only one of the two papers extracted
    pending    — neither paper extracted

Each paper manifest entry also carries `appears_in_pairs` so the per-paper
view can show "Appears in pairs" cross-links.

For each paper JSON, extracts:
    paper_id, title, n_nodes, top_node_types, tier, appears_in_pairs
For each master pair, emits:
    pair_id, status, relation_type, paper_a {arxiv_id,title,paper_dir,extracted},
    paper_b {...}, alignment_available, n_matches, why_related, alignment_file

Tolerates both schema shapes:
    - Tier-1 / older: {"metadata": {...}, "nodes": [...], "edges": [...]}
    - v2 / silver:    {"title": ..., "blocks": [...], "relations": [...], ...}
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

# Master CSV + registry are in Or's GDrive Automath workspace. Read at
# build time only — not committed to the repo.
GDRIVE_AUTOMATH = Path("/mnt/g/My Drive/Research/Automath")
MASTER_PAIRS_CSV = GDRIVE_AUTOMATH / "math_papers_pairs_enriched.csv"
PAPER_REGISTRY_CSV = (GDRIVE_AUTOMATH /
                      "alignment_benchmark" / "paper_registry.csv")
PAPERS_GDRIVE = GDRIVE_AUTOMATH / "alignment_benchmark" / "papers"


# ---------------------------------------------------------------------------
# JSON I/O helpers
# ---------------------------------------------------------------------------

def _read_json(p: Path) -> dict[str, Any] | None:
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  warn: could not parse {p.name}: {e}")
        return None


# ---------------------------------------------------------------------------
# Paper-id ↔ arxiv-id mapping
# ---------------------------------------------------------------------------

def _pid_canonical(pid: str) -> str:
    """Registry stores 'paper1', tier2 dir uses 'paper001'. Normalize to
    the zero-padded form so they line up."""
    if pid and pid.startswith("paper") and pid[5:].isdigit():
        return f"paper{int(pid[5:]):03d}"
    return pid


def _norm_arxiv(s: str) -> str:
    """Canonicalize an arXiv id: strip 'arXiv:' prefix and any trailing
    version (v1, v2, ...). Preserves the cross-list category prefix
    (e.g. 'math/0307152')."""
    if not s:
        return ""
    s = s.strip()
    if s.lower().startswith("arxiv:"):
        s = s[len("arxiv:"):]
    # Strip trailing vN
    import re
    s = re.sub(r"v\d+$", "", s)
    return s


def load_registry() -> list[dict[str, Any]]:
    if not PAPER_REGISTRY_CSV.exists():
        print(f"  warn: registry CSV not found at {PAPER_REGISTRY_CSV}")
        return []
    with PAPER_REGISTRY_CSV.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # Canonicalize paper_id (paper1 -> paper001) so downstream lookups work
    # uniformly with the tier2 directory layout.
    for r in rows:
        r["paper_id_canonical"] = _pid_canonical(r.get("paper_id", ""))
    return rows


def build_pair_to_papers_from_registry(
        registry: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Use the registry's `appears_in_pairs` column (semicolon-delimited) to
    invert into pair_id -> [canonical paperNNN ...]. This is a robust
    fallback when the master CSV has empty paper-id columns (e.g. the
    NEG_pairs that are intentionally listed without titles)."""
    out: dict[str, list[str]] = {}
    for r in registry:
        aip = (r.get("appears_in_pairs") or "").strip()
        if not aip:
            continue
        pid = r["paper_id_canonical"]
        for raw in aip.split(";"):
            v = raw.strip()
            if v:
                out.setdefault(v, []).append(pid)
    return out


def build_paper_lookup(
        registry: list[dict[str, Any]],
        tier1_paths: list[Path],
        tier2_paths: list[Path]) -> dict[str, str]:
    """Return arxiv_id (canonical) -> paper-dir-stem (where the paper's JSON
    lives). The dir-stem encodes both location (tier1 uses raw arxiv-based
    stems; tier2 uses paperNNN). For tier1 we also include short_name and
    full_title fallbacks where possible (tier1 metadata.json has titles)."""

    lookup: dict[str, str] = {}
    title_lookup: dict[str, str] = {}
    short_lookup: dict[str, str] = {}

    # 1) Registry entries: arxiv_id -> paperNNN.
    for r in registry:
        arx = _norm_arxiv(r.get("arxiv_id") or "")
        pid = r["paper_id_canonical"]
        if arx and pid:
            lookup.setdefault(arx, pid)
        sn = (r.get("short_name") or "").strip().lower()
        if sn:
            short_lookup.setdefault(sn, pid)
        ft = (r.get("full_title") or "").strip().lower()
        if ft:
            title_lookup.setdefault(ft, pid)

    # 2) Tier1 papers — usually filename IS the arxiv id (with v-suffix).
    #    Map both raw and version-stripped to the file stem.
    for p in tier1_paths:
        stem = p.stem  # e.g. "1204.0109v1_claude"
        # Strip "_claude" / "_gold" suffix to get the arxiv-y core
        core = stem
        for suf in ("_claude", "_gold", "_silver"):
            if core.endswith(suf):
                core = core[: -len(suf)]
        norm = _norm_arxiv(core)
        if norm:
            lookup.setdefault(norm, stem)
        # also peek at metadata for titles
        d = _read_json(p)
        if d:
            meta = d.get("metadata", d)
            t = (meta.get("title") or "").strip().lower()
            if t:
                title_lookup.setdefault(t, stem)
            arx_meta = _norm_arxiv(meta.get("arxiv_id") or
                                   meta.get("paper_id") or "")
            if arx_meta:
                lookup.setdefault(arx_meta, stem)

    # 3) Tier2 paperNNN metadata may also carry titles — useful for
    #    short_name fallback when the registry lacks an arxiv_id.
    for p in tier2_paths:
        d = _read_json(p)
        if not d:
            continue
        meta = d.get("metadata", d)
        t = (meta.get("title") or "").strip().lower()
        if t:
            title_lookup.setdefault(t, p.stem)

    return {
        "by_arxiv": lookup,
        "by_short_name": short_lookup,
        "by_title": title_lookup,
    }


# ---------------------------------------------------------------------------
# Master pairs CSV
# ---------------------------------------------------------------------------

def read_master_pairs(csv_path: Path) -> list[dict[str, Any]]:
    """Parse math_papers_pairs_enriched.csv into a list of pair dicts with
    only the fields the portal cares about."""
    if not csv_path.exists():
        print(f"  warn: master pairs CSV not found: {csv_path}")
        return []
    out: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            why = (row.get("short_description") or "").strip()
            if not why:
                why = (row.get("notes") or "").strip()
            out.append({
                "pair_id": row.get("pair_id") or "",
                "relation_type": (row.get("relation_type") or "").strip(),
                "math_category": (row.get("math_category") or "").strip(),
                "paper_a": {
                    "arxiv_id": _norm_arxiv(row.get("paper1_arxiv_id") or ""),
                    "short_name": (row.get("paper1_short_name") or "").strip(),
                    "title": (row.get("paper1_full_title") or "").strip(),
                    "authors": (row.get("paper1_authors") or "").strip(),
                    "year": (row.get("paper1_year") or "").strip(),
                },
                "paper_b": {
                    "arxiv_id": _norm_arxiv(row.get("paper2_arxiv_id") or ""),
                    "short_name": (row.get("paper2_short_name") or "").strip(),
                    "title": (row.get("paper2_full_title") or "").strip(),
                    "authors": (row.get("paper2_authors") or "").strip(),
                    "year": (row.get("paper2_year") or "").strip(),
                },
                "why_related": why,
            })
    return out


def resolve_paper(side: dict[str, Any], lookup: dict[str, dict[str, str]],
                  extracted_stems: set[str]) -> tuple[str | None, bool]:
    """Try arxiv → registry mapping → tier2/tier1 stem; if absent, fall
    back to short_name / title match. Returns (paper_dir_stem | None,
    extracted: bool)."""
    arx = _norm_arxiv(side.get("arxiv_id") or "")
    if arx:
        stem = lookup["by_arxiv"].get(arx)
        if stem:
            return stem, stem in extracted_stems
    sn = (side.get("short_name") or "").strip().lower()
    if sn:
        stem = lookup["by_short_name"].get(sn)
        if stem:
            return stem, stem in extracted_stems
    t = (side.get("title") or "").strip().lower()
    if t:
        stem = lookup["by_title"].get(t)
        if stem:
            return stem, stem in extracted_stems
    return None, False


# ---------------------------------------------------------------------------
# Paper summarization (existing behaviour, unchanged outputs + new field)
# ---------------------------------------------------------------------------

def summarize_paper(path: Path, tier: int) -> dict[str, Any] | None:
    data = _read_json(path)
    if data is None:
        return None

    if "metadata" in data and isinstance(data["metadata"], dict):
        meta = data["metadata"]
        title = meta.get("title") or ""
        paper_id_raw = meta.get("paper_id") or meta.get("arxiv_id")
    else:
        title = data.get("title") or ""
        paper_id_raw = data.get("paper_id") or data.get("arxiv_id")

    paper_id = paper_id_raw or path.stem
    file_id = path.stem

    node_iter: list[dict[str, Any]] = []
    if isinstance(data.get("nodes"), list):
        node_iter = data["nodes"]
    elif isinstance(data.get("blocks"), list):
        node_iter = data["blocks"]

    type_counter: Counter[str] = Counter()
    for n in node_iter:
        t = n.get("type") if isinstance(n, dict) else None
        if t:
            type_counter[t] += 1

    BUCKETS = {
        "def":   {"definition"},
        "thm":   {"theorem", "lemma", "proposition", "corollary",
                  "claim", "conjecture"},
        "alg":   {"algorithm"},
        "pf":    {"proof"},
        "steps": {"proof_step", "algorithm_step"},
        "other": {"equation", "problem", "open_problem", "assumption",
                  "example", "remark"},
    }
    bucket_counts = {b: sum(type_counter.get(t, 0) for t in types)
                     for b, types in BUCKETS.items()}

    return {
        "paper_id": file_id,
        "display_id": str(paper_id),
        "title": title,
        "n_nodes": len(node_iter),
        "type_counts": dict(type_counter),
        "buckets": bucket_counts,
        "top_node_types": type_counter.most_common(6),
        "tier": tier,
        "appears_in_pairs": [],   # filled in after pair list is built
    }


def walk_papers(subdir: str, tier: int) -> list[dict[str, Any]]:
    d = DATA / subdir
    if not d.exists():
        print(f"  (skip: {subdir} does not exist)")
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json")):
        s = summarize_paper(p, tier)
        if s is not None:
            out.append(s)
    print(f"  {subdir}: {len(out)} papers")
    return out


# ---------------------------------------------------------------------------
# Pair manifest (master CSV ⊕ alignment JSONs in data/pairs/)
# ---------------------------------------------------------------------------

def read_alignment_index() -> dict[str, dict[str, Any]]:
    """Walk data/pairs/ and pick out files that are real pair-alignment
    schemas (have metadata.paper_a + metadata.paper_b). Skips
    paper_*_gold.json files which are single-paper extractions
    accidentally living in pairs/.

    Two filename conventions are recognized:
      * `<pair_id>_alignment_with_steps.json` — v2, references new-scheme
        (paperNNN-prefixed) node IDs. PREFERRED when present.
      * `<pair_id>_alignment.json`            — v1 (legacy), references the
        old gold_opus_4_7 abbreviated node-id scheme (e.g. DP_W2V.x). Kept
        for historical comparison; not compatible with the new graph viewer.

    For each pair_id we surface the v2 entry as the primary alignment and
    expose any v1 file under `legacy_*` keys.
    """
    d = DATA / "pairs"
    if not d.exists():
        return {}

    raw: dict[str, dict[str, dict[str, Any]]] = {}
    # raw[pid] = {"v1": {...} or None, "v2": {...} or None}
    for p in sorted(d.glob("*.json")):
        data = _read_json(p)
        if not isinstance(data, dict):
            continue
        meta = data.get("metadata") or {}
        if not (isinstance(meta.get("paper_a"), dict) and
                isinstance(meta.get("paper_b"), dict)):
            continue
        stem = p.stem
        if stem.endswith("_alignment_with_steps"):
            variant = "v2"
            pid = stem[: -len("_alignment_with_steps")]
        elif stem.endswith("_alignment"):
            variant = "v1"
            pid = stem[: -len("_alignment")]
        else:
            # Bare <pair_id>.json (no _alignment suffix). Treat as v1.
            variant = "v1"
            pid = stem
        matches = data.get("matches", [])
        entry = {
            "filename": p.name,
            "n_matches": len(matches) if isinstance(matches, list) else 0,
            "annotator": meta.get("annotator") or "",
            "scheme_version": meta.get("scheme_version") or "",
            "alignment_name": meta.get("alignment_name") or pid,
            "description": meta.get("description") or "",
            "metadata": meta,
        }
        raw.setdefault(pid, {"v1": None, "v2": None})[variant] = entry

    # Collapse: prefer v2; expose v1 under legacy_*.
    idx: dict[str, dict[str, Any]] = {}
    for pid, vs in raw.items():
        v2 = vs["v2"]
        v1 = vs["v1"]
        primary = v2 or v1
        if primary is None:
            continue
        primary = dict(primary)  # defensive copy
        primary["scheme"] = "with_steps_v2" if v2 else "legacy"
        if v2 and v1:
            primary["legacy_filename"] = v1["filename"]
            primary["legacy_annotator"] = v1["annotator"]
        elif v1 and not v2:
            # mark explicitly so the manifest carries a "legacy_*" status
            primary["legacy_only"] = True
        idx[pid] = primary
    return idx


def build_pairs_manifest(
        master_pairs: list[dict[str, Any]],
        alignment_idx: dict[str, dict[str, Any]],
        lookup: dict[str, dict[str, str]],
        extracted_stems: set[str],
        pair_to_papers: dict[str, list[str]]) -> tuple[
            list[dict[str, Any]], dict[str, list[str]]]:
    """Returns (pairs_list, paper_stem -> [pair_id...] reverse index)."""
    out: list[dict[str, Any]] = []
    appears: dict[str, list[str]] = {}

    for mp in master_pairs:
        a_stem, a_extracted = resolve_paper(mp["paper_a"], lookup,
                                            extracted_stems)
        b_stem, b_extracted = resolve_paper(mp["paper_b"], lookup,
                                            extracted_stems)

        # Registry-based fallback: if title/short_name lookups failed but
        # the registry knows two paper_ids appear in this pair_id, use
        # those. This rescues the NEG pairs (titles intentionally blank)
        # and any pair where the master CSV shipped without arxiv_ids.
        reg_papers = pair_to_papers.get(mp["pair_id"], [])
        if a_stem is None and len(reg_papers) >= 1:
            a_stem = reg_papers[0]
            a_extracted = a_stem in extracted_stems
        if b_stem is None and len(reg_papers) >= 2:
            b_stem = reg_papers[1]
            b_extracted = b_stem in extracted_stems

        align = alignment_idx.get(mp["pair_id"])
        if align is not None and align.get("scheme") == "with_steps_v2":
            status = "annotated"
        elif align is not None and align.get("legacy_only"):
            # Legacy v1 alignment exists but no v2; can't render with the
            # new graph viewer (incompatible node IDs).
            status = "legacy"
        elif a_extracted and b_extracted:
            status = "ready"
        elif a_extracted or b_extracted:
            status = "partial"
        else:
            status = "pending"

        # Prefer master CSV titles for display; fall back to alignment
        # JSON titles if the CSV is sparse.
        a_title = mp["paper_a"]["title"]
        b_title = mp["paper_b"]["title"]
        if align:
            am = align["metadata"].get("paper_a") or {}
            bm = align["metadata"].get("paper_b") or {}
            if not a_title:
                a_title = am.get("title") or ""
            if not b_title:
                b_title = bm.get("title") or ""

        entry = {
            "pair_id": mp["pair_id"],
            "status": status,
            "relation_type": mp["relation_type"],
            "math_category": mp["math_category"],
            "paper_a": {
                "arxiv_id": mp["paper_a"]["arxiv_id"],
                "title": a_title,
                "short_name": mp["paper_a"]["short_name"],
                "authors": mp["paper_a"]["authors"],
                "year": mp["paper_a"]["year"],
                "paper_dir": a_stem,
                "extracted": a_extracted,
                "tier": _stem_tier(a_stem) if a_extracted else None,
            },
            "paper_b": {
                "arxiv_id": mp["paper_b"]["arxiv_id"],
                "title": b_title,
                "short_name": mp["paper_b"]["short_name"],
                "authors": mp["paper_b"]["authors"],
                "year": mp["paper_b"]["year"],
                "paper_dir": b_stem,
                "extracted": b_extracted,
                "tier": _stem_tier(b_stem) if b_extracted else None,
            },
            # Surface the alignment file ONLY when it's a v2 with-steps file
            # (i.e. node IDs match the current new-scheme paper JSONs).
            # Pairs with only a legacy v1 file behave like "no alignment
            # yet" in the per-pair viewer; their v1 file is still on disk
            # for historical comparison but not exposed via this manifest.
            "alignment_available": (align is not None and
                                    align.get("scheme") == "with_steps_v2"),
            "alignment_file": (align["filename"]
                               if (align is not None and
                                   align.get("scheme") == "with_steps_v2")
                               else None),
            "alignment_scheme": (align.get("scheme")
                                 if (align is not None and
                                     align.get("scheme") == "with_steps_v2")
                                 else None),
            "legacy_alignment_file": (align.get("legacy_filename")
                                      if align else None),
            "n_matches": (align["n_matches"]
                          if (align is not None and
                              align.get("scheme") == "with_steps_v2")
                          else None),
            "annotator": (align["annotator"]
                          if (align is not None and
                              align.get("scheme") == "with_steps_v2")
                          else ""),
            "alignment_name": (align["alignment_name"] if align
                               else mp["pair_id"]),
            "why_related": mp["why_related"],
        }
        out.append(entry)

        for stem in (a_stem, b_stem):
            if stem:
                appears.setdefault(stem, []).append(mp["pair_id"])

    return out, appears


def _stem_tier(stem: str | None) -> int | None:
    """Decide which tier a paper-dir-stem lives in, by checking the file."""
    if not stem:
        return None
    if (DATA / "tier1" / f"{stem}.json").exists():
        return 1
    if (DATA / "tier2" / f"{stem}.json").exists():
        return 2
    if (DATA / "tier3-sample" / f"{stem}.json").exists():
        return 3
    return None


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Building manifest from {DATA} ...")

    tier1_paths = sorted((DATA / "tier1").glob("*.json")) \
        if (DATA / "tier1").exists() else []
    tier2_paths = sorted((DATA / "tier2").glob("*.json")) \
        if (DATA / "tier2").exists() else []
    tier3_paths = sorted((DATA / "tier3-sample").glob("*.json")) \
        if (DATA / "tier3-sample").exists() else []

    tier1 = walk_papers("tier1", 1)
    tier2 = walk_papers("tier2", 2)
    tier3 = walk_papers("tier3-sample", 3)

    extracted_stems = (
        {p["paper_id"] for p in tier1} |
        {p["paper_id"] for p in tier2} |
        {p["paper_id"] for p in tier3}
    )

    registry = load_registry()
    print(f"  registry rows: {len(registry)}")
    lookup = build_paper_lookup(registry, tier1_paths, tier2_paths)
    print(f"  arxiv→stem mappings: {len(lookup['by_arxiv'])}")
    print(f"  short_name→stem: {len(lookup['by_short_name'])}, "
          f"title→stem: {len(lookup['by_title'])}")
    pair_to_papers = build_pair_to_papers_from_registry(registry)
    print(f"  pair→papers from registry: {len(pair_to_papers)} pair_ids")

    master = read_master_pairs(MASTER_PAIRS_CSV)
    print(f"  master CSV pairs: {len(master)}")

    alignment_idx = read_alignment_index()
    print(f"  alignment JSONs (real pairs): {len(alignment_idx)}")

    pairs, appears = build_pairs_manifest(master, alignment_idx,
                                          lookup, extracted_stems,
                                          pair_to_papers)

    # Annotate paper entries with their pair memberships.
    for plist in (tier1, tier2, tier3):
        for p in plist:
            p["appears_in_pairs"] = sorted(set(appears.get(p["paper_id"], [])))

    # Status histogram
    counts = Counter(p["status"] for p in pairs)
    print(f"  pair status: {dict(counts)}")

    # Cross-check: alignment JSONs whose pair_id isn't in the master CSV
    # would otherwise be invisible. Surface them as orphaned-annotated rows.
    master_ids = {mp["pair_id"] for mp in master}
    orphans = [pid for pid in alignment_idx if pid not in master_ids]
    if orphans:
        print(f"  warn: {len(orphans)} alignment JSONs not in master CSV "
              f"(will append as 'annotated' orphans): {orphans[:5]}…")
        for pid in orphans:
            align = alignment_idx[pid]
            am = align["metadata"].get("paper_a") or {}
            bm = align["metadata"].get("paper_b") or {}
            a_arx = _norm_arxiv(am.get("arxiv_id") or "")
            b_arx = _norm_arxiv(bm.get("arxiv_id") or "")
            a_stem = lookup["by_arxiv"].get(a_arx) if a_arx else None
            b_stem = lookup["by_arxiv"].get(b_arx) if b_arx else None
            pairs.append({
                "pair_id": pid,
                "status": "annotated",
                "relation_type": align["metadata"].get("relation_type") or "",
                "math_category": "",
                "paper_a": {
                    "arxiv_id": a_arx, "title": am.get("title") or "",
                    "short_name": "", "authors": "", "year": "",
                    "paper_dir": a_stem,
                    "extracted": a_stem in extracted_stems if a_stem else False,
                    "tier": _stem_tier(a_stem),
                },
                "paper_b": {
                    "arxiv_id": b_arx, "title": bm.get("title") or "",
                    "short_name": "", "authors": "", "year": "",
                    "paper_dir": b_stem,
                    "extracted": b_stem in extracted_stems if b_stem else False,
                    "tier": _stem_tier(b_stem),
                },
                "alignment_available": True,
                "alignment_file": align["filename"],
                "n_matches": align["n_matches"],
                "annotator": align["annotator"],
                "alignment_name": align["alignment_name"],
                "why_related": align["description"],
            })
            for s in (a_stem, b_stem):
                if s:
                    for plist in (tier1, tier2, tier3):
                        for p in plist:
                            if p["paper_id"] == s and pid not in p["appears_in_pairs"]:
                                p["appears_in_pairs"].append(pid)

    # Diagnostics: how many master pairs have at least one paper we
    # couldn't locate?
    orphan_papers = [p["pair_id"] for p in pairs
                     if (not p["paper_a"]["paper_dir"]
                         and p["paper_a"]["arxiv_id"])
                     or (not p["paper_b"]["paper_dir"]
                         and p["paper_b"]["arxiv_id"])]
    if orphan_papers:
        print(f"  note: {len(orphan_papers)} master pairs reference an "
              f"arxiv_id the registry/tier dirs don't know about")

    manifest = {
        "papers": {"tier1": tier1, "tier2": tier2, "tier3": tier3},
        "pairs": pairs,
    }

    out_path = DATA / "manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    total_papers = sum(len(v) for v in manifest["papers"].values())
    print(f"Wrote {out_path}  "
          f"({total_papers} papers, {len(manifest['pairs'])} pairs)")


if __name__ == "__main__":
    main()
