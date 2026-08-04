"""T-OPEN — Erdős-problems coverage over the Saranga parsed corpus.

Question this answers
---------------------
Of the 1217 catalogued Erdős problems (statements + resolution status from
github.com/teorth/erdosproblems — the repo behind erdosproblems.com — committed
here as `erdos_problems.csv`; 1063 have statements long enough to match),

  1. which ones are actually PRESENT in our parsed corpus — i.e. some paper we
     parsed states that problem as an `open_problem` / `conjecture` node; and
  2. for the RESOLVED ones (proved/disproved/solved), did our T-OPEN sweep
     already surface a corpus theorem that plausibly resolves the matched node?

It is deliberately the *cheap, dependency-free* rung: the same math-aware
token-Jaccard the T-OPEN sweep uses (`shared.corpus.node_norm_text` +
`o1_retrieve._jaccard`). No API calls, no embeddings.

How matching works
------------------
* Corpus side: every `open_problem` / `conjecture` node (optionally also
  theorem-like nodes, `--match-theorems`) is turned into a normalized token set
  via `node_norm_text(prefer_raw=True)` — the exact substrate the sweep indexes.
* Erdős side: each CSV `statement` is normalized through the SAME pipeline
  (`clean_latex_to_text` -> `normalize_math_text`) so the two token sets are
  directly comparable.
* For each Erdős problem we keep the single best-scoring corpus node. A problem
  counts as "covered" when that best score >= `--threshold`.

Coverage is then reported split by resolution status (open vs solved), and for
covered problems we optionally cross-reference the T-OPEN run outputs
(`runs/o4_verdicts_all.csv`, `runs/triage_top_raw.csv`) to see whether the
matched corpus node already had a resolving-theorem candidate found.

IMPORTANT caveats (see ERDOS_COVERAGE.md for the long version)
--------------------------------------------------------------
* NO temporal gate is applied for the *coverage* match: an Erdős problem and the
  paper that states it can be any year. The sweep's `theorem.year >= problem.year`
  gate only matters for the *resolution* cross-reference, and most Erdős problems
  predate arXiv, so a genuine pre-arXiv resolution is invisible to the corpus.
* Token-Jaccard is a recall-oriented shortlister, not a judge. A match above
  threshold means "same problem is plausibly stated here", to be confirmed by a
  human / the O4 LLM judge — exactly as in the main sweep.

Runs locally and on the cluster unchanged — only `--corpus-dir` changes.

    # Local sanity run (bare test dirs need --accept-bare). The local corpus has
    # ~15 matchable nodes, so this validates the PATH, not the science:
    python discovery_suite/open_problems/erdos_coverage.py \
        --erdos-csv discovery_suite/open_problems/erdos_problems.csv \
        --corpus-dir portal/data/tier1 portal/data/tier2 \
        --accept-bare \
        --out discovery_suite/open_problems/runs/erdos_coverage_local.csv

    # Cluster (full 100k parsed corpus) — use the sbatch wrapper:
    export ROOT=/sci/labs/orzuk/.../parsed_100k_v4
    sbatch discovery_suite/open_problems/erdos_cluster.sh

READ THE PRINTED SCORE HISTOGRAM before believing any coverage number: the score
is a max over every corpus node, so the noise floor rises with corpus size and
`--threshold` MUST be recalibrated per corpus (see ERDOS_COVERAGE.md §2).
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterator, Optional

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _SUITE / "shared", _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import (  # noqa: E402
    DEFAULT_ROOT,
    normalize_math_text,
    node_norm_text,
    stream_papers,
)
from o1_retrieve import _jaccard  # noqa: E402  (identical Jaccard as the sweep)

# Same math-preserving LaTeX cleaner the corpus side uses (optional import).
try:
    from LLMVersion.latex_clean import clean_latex_to_text  # noqa: E402
except Exception:  # pragma: no cover
    clean_latex_to_text = None

# Node types treated as "the Erdős problem, as stated in a paper".
QUERY_TYPES = {"open_problem", "conjecture"}
THEOREM_TYPES = {"theorem", "lemma", "proposition", "corollary", "claim"}

# Which yaml_status values count as "resolved" (mirrors the scoping note:
# proved / disproved / solved, including the Lean-formalized variants).
# NOTE the real CSV spells the Lean variants "proved (lean)" — `_norm_status`
# folds that to the underscored form before this set is consulted.
RESOLVED_STATUSES = {
    "proved", "disproved", "solved",
    "proved_lean", "disproved_lean", "solved_lean",
    "proven", "resolved",
}

# Genuinely-unsolved. Everything else (falsifiable, decidable, verifiable,
# independent, "not provable", ...) is a logical-status label, neither open nor
# resolved, and is reported as "other" rather than silently inflating "open".
OPEN_STATUSES = {"open"}

_LEAN = re.compile(r"\s*\((?:lean)\)\s*$")


def _norm_status(raw: str) -> str:
    """Fold the CSV's status spellings onto the canonical keys.

    The export writes `proved (lean)` / `disproved (lean)` / `solved (lean)`
    (205 rows). Without this, those count as unresolved and the headline
    resolved/open split comes out 351/866 instead of the true 556/608."""
    s = (raw or "").strip().lower()
    return _LEAN.sub("_lean", s) if _LEAN.search(s) else s


# ── Erdős CSV ────────────────────────────────────────────────────────────────

# Status-banner boilerplate that erdosproblems.com renders BEFORE the actual
# problem text (captured by the scrape into the `statement` column). These
# shared phrases badly inflate token-Jaccard against every corpus node, so we
# strip them before tokenizing. Order-independent, case-insensitive.
_ERDOS_BOILERPLATE = re.compile(
    r"(?i)\((?:LEAN|Lean)\)\s*"
    r"|This has been (?:solved|proved|disproved)[^.]*\."
    r"|This is (?:open|solved|disproved)[^.]*\."
    r"|and the proof (?:has been )?verified in Lean\.?"
    r"|and cannot be resolved with a finite computation\.?"
    r"|in the (?:negative|affirmative)\.?"
    r"|-\s*\$\d[\d,]*"                    # prize markers like "- $1000"
)


def _strip_erdos_boilerplate(stmt: str) -> str:
    """Remove the status-banner boilerplate prepended to Erdős statements so the
    match is driven by the actual mathematical content, not shared banner words."""
    return _ERDOS_BOILERPLATE.sub(" ", stmt).strip()


def string_to_tokens(raw: str) -> frozenset:
    """Normalize a raw statement string to the SAME token substrate the corpus
    nodes use: clean_latex_to_text (math-preserving) then normalize_math_text.
    Falls back to normalize_math_text alone if the cleaner is unavailable."""
    if not raw:
        return frozenset()
    body = clean_latex_to_text(raw) if clean_latex_to_text is not None else raw
    return frozenset(normalize_math_text(body).split())


def load_erdos(csv_path: Path) -> list[dict]:
    """Read the Erdős CSV. Tolerant of column-name variation; keeps only rows
    that have a real (non-trivial) statement. Each record carries its tokenized
    statement so we tokenize once."""
    rows: list[dict] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        # The export carries ~841 stray NUL bytes; Python <= 3.10's csv module
        # hard-errors ("line contains NUL") on those, so strip them up front
        # rather than depend on the cluster's interpreter version.
        reader = csv.DictReader(l.replace("\x00", "") for l in fh)
        # normalize header lookup (case-insensitive)
        lower = {c.lower(): c for c in (reader.fieldnames or [])}

        def col(*names: str) -> Optional[str]:
            for n in names:
                if n in lower:
                    return lower[n]
            return None

        c_num = col("number", "id", "problem", "problem_number")
        c_status = col("yaml_status", "status")
        c_stmt = col("statement", "problem_statement", "text")
        c_prose = col("solving_prose", "solution", "resolution")
        c_cite = col("cite_keys", "citations", "cites")
        if c_stmt is None:
            raise SystemExit(
                f"[erdos] CSV {csv_path} has no 'statement' column "
                f"(saw: {reader.fieldnames})")

        for r in reader:
            stmt = _strip_erdos_boilerplate((r.get(c_stmt) or "").strip())
            toks = string_to_tokens(stmt)
            if len(toks) < 4:  # skip placeholder / empty statements
                continue
            status = _norm_status(r.get(c_status)) if c_status else ""
            rows.append({
                "number": (r.get(c_num) or "").strip() if c_num else str(len(rows)),
                "status": status,
                "resolved": status in RESOLVED_STATUSES,
                "open": status in OPEN_STATUSES,
                "statement": stmt,
                "solving_prose": (r.get(c_prose) or "").strip() if c_prose else "",
                "cite_keys": (r.get(c_cite) or "").strip() if c_cite else "",
                "toks": toks,
            })
    return rows


# ── Corpus loading (canonical + optional bare-json fallback) ─────────────────

def _bare_papers(root: Path) -> Iterator[dict]:
    """Yield {paper_id, nodes} for bare `*.json` files the canonical loader
    skips (no arXiv id / no `_rules`/`_manual` suffix). LOCAL PoC ONLY — the
    tier2/tier2_test test dirs use synthetic filenames (paper001.json). We do
    NOT re-glob the canonical tier3 corpus here; this path is reached only when
    --accept-bare is set, for the non-arXiv test dirs."""
    for fp in sorted(glob.glob(str(root / "**" / "*.json"), recursive=True)):
        name = Path(fp).name
        if name.endswith(("_rules.json", "_manual.json")):
            continue  # already handled by the canonical loader
        try:
            data = json.loads(Path(fp).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        nodes = data.get("nodes")
        if not isinstance(nodes, list):
            continue
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        pid = meta.get("paper_id") or Path(fp).stem
        yield {"paper_id": pid, "nodes": nodes}


def load_corpus_nodes(roots: list[Path], match_theorems: bool,
                      accept_bare: bool, min_words: int) -> list[dict]:
    """Return lean corpus node records: [{key, pid, type, toks, snip}].

    Canonical papers come through `shared.corpus.stream_papers` (the required
    corpus loader). When --accept-bare is set we ALSO ingest bare test-dir JSONs
    that stream_papers structurally cannot load (no arXiv id)."""
    keep = set(QUERY_TYPES)
    if match_theorems:
        keep |= THEOREM_TYPES
    out: list[dict] = []
    seen_pid_node: set[tuple] = set()

    def _add(pid: str, node: dict):
        t = (node.get("type") or "").lower()
        if t not in keep:
            return
        # de-dupe identical (pid, node-id) across extraction variants (tier1 has
        # _rules/_manual/anthropic/... copies of the same paper).
        sig = (pid, node.get("id"))
        if sig in seen_pid_node:
            return
        toks = frozenset(node_norm_text(node, prefer_raw=True).split())
        if len(toks) < min_words:
            return
        seen_pid_node.add(sig)
        out.append({
            "key": f"{pid}::{node.get('id')}",
            "pid": pid, "type": t, "toks": toks,
            "snip": node_norm_text(node, prefer_raw=True)[:160].replace("\n", " "),
        })

    for root in roots:
        for p in stream_papers(root=root):
            for n in p.nodes:
                _add(p.paper_id, n)
        if accept_bare:
            for bp in _bare_papers(root):
                for n in bp["nodes"]:
                    _add(bp["paper_id"], n)
    return out


# ── T-OPEN run cross-reference ───────────────────────────────────────────────

def load_run_index(runs_dir: Path) -> dict:
    """Index the T-OPEN sweep/verdict outputs by problem_key so we can tell,
    for a covered Erdős node, whether a resolving theorem was already found.
    Prefers o4_verdicts_all.csv (has an LLM verdict); falls back to triage."""
    idx: dict[str, dict] = {}
    verdicts = runs_dir / "o4_verdicts_all.csv"
    triage = runs_dir / "triage_top_raw.csv"
    src = verdicts if verdicts.exists() else triage
    if not src.exists():
        return idx
    with src.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            pk = r.get("problem_key")
            if not pk:
                continue
            # keep the highest-scoring row per problem_key
            score = float(r.get("score") or 0)
            if pk not in idx or score > idx[pk]["score"]:
                idx[pk] = {
                    "score": score,
                    "theorem_key": r.get("theorem_key", ""),
                    "verdict": r.get("verdict", ""),  # NO if triage-only
                    "same_object": r.get("same_object", ""),
                }
    return idx, str(src)


# ── score distribution ───────────────────────────────────────────────────────

def print_histogram(scores: list[float], threshold: float, bins: int = 20) -> None:
    """Print the best-match score distribution + percentiles.

    This is the instrument for retuning `--threshold` on a new corpus. Because
    each score is a max over every corpus node, the distribution's bulk is the
    null (problems not in the corpus at all) and it drifts upward as the corpus
    grows — which is exactly why a constant default cannot be trusted."""
    if not scores:
        return
    s = sorted(scores)
    n = len(s)

    def pct(p: float) -> float:
        return s[min(n - 1, int(p * n))]

    print("\n--- best-match score distribution (retune --threshold from this) ---",
          flush=True)
    marks = [("p50", 0.50), ("p90", 0.90), ("p95", 0.95), ("p99", 0.99),
             ("max", 1.0)]
    print("  " + "  ".join(f"{lbl}={pct(p) if p < 1.0 else s[-1]:.3f}"
                           for lbl, p in marks), flush=True)

    hi = s[-1] or 1.0
    width = hi / bins
    counts = Counter(min(bins - 1, int(v / width)) for v in s)
    peak = max(counts.values()) or 1
    for b in range(bins):
        lo_e, hi_e = b * width, (b + 1) * width
        c = counts.get(b, 0)
        bar = "#" * max(0, round(40 * c / peak))
        flag = " <- threshold" if lo_e <= threshold < hi_e else ""
        print(f"  [{lo_e:.3f},{hi_e:.3f})  {c:>5}  {bar}{flag}", flush=True)
    over = sum(1 for v in s if v >= threshold)
    print(f"  at --threshold {threshold}: {over} of {n} problems counted as "
          f"covered ({over/n:.1%})", flush=True)
    print("  NOTE p99 is still noise if most problems are absent from the "
          "corpus; prefer a cut above p99 and LLM-judge the band below it.",
          flush=True)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--erdos-csv", required=True, type=Path,
                    help="erdos_problems_extracted.csv (number,yaml_status,statement,...)")
    ap.add_argument("--corpus-dir", nargs="+", type=Path, default=[DEFAULT_ROOT],
                    help="one or more parsed-corpus roots (default: shared.corpus.DEFAULT_ROOT)")
    ap.add_argument("--out", type=Path,
                    default=_HERE / "runs" / "erdos_coverage.csv",
                    help="per-Erdős-problem best-match CSV")
    ap.add_argument("--threshold", type=float, default=0.25,
                    help="min token-Jaccard for a problem to count as 'covered'. "
                         "0.25 cleanly separates true matches (~0.4-0.8) from "
                         "generic-word noise (<=0.21) in the local PoC; lower it "
                         "(e.g. 0.15) to widen recall for LLM-judge review.")
    ap.add_argument("--min-words", type=int, default=6,
                    help="skip corpus nodes with fewer normalized tokens")
    ap.add_argument("--match-theorems", action="store_true",
                    help="also match against theorem-like nodes (widens recall, noisier)")
    ap.add_argument("--accept-bare", action="store_true",
                    help="also load bare *.json test dirs the canonical loader skips "
                         "(local PoC over tier2/tier2_test; unnecessary on the cluster)")
    ap.add_argument("--runs-dir", type=Path, default=_HERE / "runs",
                    help="T-OPEN sweep outputs to cross-reference for resolutions")
    ap.add_argument("--show", type=int, default=25,
                    help="print this many top matches to stdout")
    args = ap.parse_args()

    # 1. Erdős problems
    erdos = load_erdos(args.erdos_csv)
    n_res = sum(1 for e in erdos if e["resolved"])
    n_open = sum(1 for e in erdos if e["open"])
    n_other = len(erdos) - n_res - n_open
    print(f"[erdos] loaded {len(erdos)} problems with real statements "
          f"({n_res} resolved / {n_open} open / {n_other} other-status) "
          f"from {args.erdos_csv}", flush=True)

    # 2. Corpus nodes
    nodes = load_corpus_nodes(args.corpus_dir, args.match_theorems,
                              args.accept_bare, args.min_words)
    by_type = Counter(n["type"] for n in nodes)
    print(f"[erdos] corpus: {len(nodes)} candidate nodes from "
          f"{len(args.corpus_dir)} root(s) -> {dict(by_type)}", flush=True)
    if not nodes:
        print("[erdos] no corpus nodes loaded — check --corpus-dir / --accept-bare",
              flush=True)

    # 3. T-OPEN run index (for resolution cross-reference)
    run_idx: dict = {}
    run_src = ""
    ri = load_run_index(args.runs_dir)
    if isinstance(ri, tuple):
        run_idx, run_src = ri
    if run_idx:
        print(f"[erdos] cross-referencing {len(run_idx)} problem_keys from {run_src}",
              flush=True)

    # 4. Best match per Erdős problem (O(#erdos x #nodes) token-Jaccard).
    results = []
    for e in erdos:
        best_s, best_n = 0.0, None
        for n in nodes:
            s = _jaccard(e["toks"], n["toks"])
            if s > best_s:
                best_s, best_n = s, n
        covered = best_s >= args.threshold
        row = {
            "number": e["number"], "status": e["status"],
            "resolved": e["resolved"], "score": best_s, "covered": covered,
            "match_key": best_n["key"] if best_n else "",
            "match_type": best_n["type"] if best_n else "",
            "erdos_stmt": e["statement"][:200].replace("\n", " "),
            "match_snip": best_n["snip"] if best_n else "",
            "resolving_theorem": "", "resolution_verdict": "",
        }
        if covered and best_n and best_n["key"] in run_idx:
            v = run_idx[best_n["key"]]
            row["resolving_theorem"] = v["theorem_key"]
            row["resolution_verdict"] = v.get("verdict", "") or "(triage only)"
        results.append(row)

    results.sort(key=lambda r: -r["score"])

    # 5. Coverage summary
    covered = [r for r in results if r["covered"]]
    cov_res = sum(1 for r in covered if r["resolved"])
    cov_open = len(covered) - cov_res
    with_resolution = [r for r in covered if r["resolving_theorem"]]
    print("\n===== ERDŐS COVERAGE SUMMARY =====", flush=True)
    print(f"threshold (Jaccard) : {args.threshold}", flush=True)
    print(f"Erdős problems       : {len(erdos)}  "
          f"(resolved {n_res} / open {n_open} / other {n_other})", flush=True)
    print(f"COVERED in corpus    : {len(covered)}  "
          f"(resolved {cov_res} / open {cov_open})", flush=True)
    if erdos:
        print(f"coverage rate        : {len(covered)/len(erdos):.1%}", flush=True)
    print(f"covered + resolving  : {len(with_resolution)}  "
          f"(matched node had a T-OPEN theorem candidate)", flush=True)

    # Score distribution — retune --threshold FROM THIS, never from the default.
    # The reported score is a max over all corpus nodes, so the noise floor
    # RISES with corpus size: a threshold calibrated on a small corpus lets
    # through pure noise on a large one. Read the percentiles as the null: the
    # bulk of the 1217 problems are genuinely absent from the corpus, so p50/p90
    # ARE the noise distribution, and a defensible cut sits above p99.
    print_histogram([r["score"] for r in results], args.threshold)

    print(f"\n--- top {args.show} matches ---", flush=True)
    for r in results[:args.show]:
        tag = "COVERED" if r["covered"] else "       "
        res = f"  ->RESOLVE {r['resolving_theorem']} [{r['resolution_verdict']}]" \
            if r["resolving_theorem"] else ""
        print(f"{tag} s={r['score']:.3f} #{r['number']:<6} [{r['status'] or '?'}] "
              f"{r['match_key'] or '-'}{res}", flush=True)
        if r["covered"]:
            print(f"          erdos: {r['erdos_stmt'][:90]}", flush=True)
            print(f"          match: {r['match_snip'][:90]}", flush=True)

    # 6. Write full CSV
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["number", "status", "resolved", "score", "covered", "match_key",
            "match_type", "resolving_theorem", "resolution_verdict",
            "erdos_stmt", "match_snip"]
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in results:
            w.writerow({k: r[k] for k in cols})
    print(f"\n[erdos] wrote {len(results)} rows -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
