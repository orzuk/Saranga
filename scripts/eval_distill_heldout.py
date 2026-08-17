#!/usr/bin/env python3
"""
Held-out distillation with k-fold alpha-tuning  (ROADMAP 7.4)
=============================================================

A **wrapper** around Yaron's distillation pipeline. It does not reimplement any
of it: rule generation is `silver_distillation_sequential.run_sequential`,
pruning is `distillation_analysis.prune_rules`, scoring is
`silver_distillation_sequential.evaluate_single_paper`. Nothing under
`src/LLMVersion/` is modified.

What it adds
------------
1. **k-fold cross-validation** to choose the FDR prune threshold **alpha**.
2. **Generate once, sweep alpha post-hoc.** The LLM cost is in rule
   *generation*; alpha only affects *pruning*, which is free CPU. So the
   candidate pool is built ONCE at ``alpha=1.0`` (nothing pruned), snapshotted,
   and then re-pruned at each alpha from that snapshot.
3. **A held-out test number**, replacing the current in-sample 17-paper figure.

Why the pool must be built at alpha=1
-------------------------------------
`run_sequential` decides what to send to the LLM by asking which dark-knowledge
items are *not already covered by the current rule set*. If pruning ran during
generation the pool would depend on alpha, and a post-hoc sweep would be
meaningless. At ``alpha=1.0`` the FDR gate keeps everything (FDR <= 1 always),
so the pool grows monotonically and is alpha-independent — the precondition the
whole design rests on.

Re-scoring, not filtering
-------------------------
For each alpha the rule subset ``R(alpha)`` is re-scored by actually re-running
the parser with that subset installed. A pure per-rule filter would miss rule
*interaction* (two rules that individually look clean can double-count spans).

Known limitation — read this before quoting CV numbers
------------------------------------------------------
By default the pool is generated once on the **full training set**, then folds
are used only for pruning + scoring (this is what ROADMAP 7.4 specifies, to stay
inside one API budget). That means each fold's validation papers *did*
contribute dark-knowledge during generation, so **CV F1 is optimistic** and is
fit for choosing alpha, not for reporting. The headline number must come from
the untouched ``--test-papers`` set, which is never seen by generation or by the
sweep. Pass ``--strict-cv`` to regenerate the pool per fold instead (k times the
API cost, no leakage).

Cost control
------------
``--skip-generation`` reuses an existing pool and makes the entire run
**zero-API-call** — the sweep, CV and test evaluation are pure CPU. Use it to
re-tune alpha or re-report without paying again. ``--dry-run`` validates wiring
and prints the plan without running anything.

Usage
-----
    # Full run (costs API for generation)
    python scripts/eval_distill_heldout.py \
        --structure-type definition \
        --train-papers paper001,paper002,...  --test-papers paper050,... \
        --tex-dir /path/to/papers --eval-dir src/LLMVersion/definition_eval_cv

    # Re-tune alpha on an existing pool — no API calls
    python scripts/eval_distill_heldout.py ... --skip-generation
"""

import argparse
import csv
import json
import os
import shutil
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))

import silver_distillation_sequential as seq          # noqa: E402
from silver_distillation_sequential import (          # noqa: E402
    FNAME_MAP,
    convert_t2_to_gold_csv,
    evaluate_single_paper,
    run_sequential,
)
from distillation_analysis import prune_rules         # noqa: E402

import silver_distillation_merged as mrg              # noqa: E402

POOL_SNAPSHOT = "distilled_rules.POOL.py"   # unpruned pool, alpha=1
RULES_FILE = "distilled_rules.py"           # what the parser actually loads


# ---------------------------------------------------------------------------
# merged-pipeline support
# ---------------------------------------------------------------------------
# This evaluator was built around silver_distillation_sequential, which distils
# ONE type per run into a single rules file. The pipeline actually shipped is
# silver_distillation_merged, which distils all 14 types into 5 base-method
# GROUPS sharing one rules file each (`theoremlike` alone covers 8 types). A
# per-type held-out number is therefore a proxy for a student we do not ship —
# a shared theoremlike rule is a different object from two per-type rules.
#
# The merged path below reuses the same design (generate the pool once at
# alpha=1.0, then re-prune per fold for free) but snapshots, prunes, and scores
# per GROUP. Nothing on the sequential path changes; --pipeline selects.


def _merged_groups(types):
    return mrg.base_method_groups(types)


def _group_rule_files(eval_dir: Path):
    """Every per-group rules file the merged run wrote."""
    return sorted((eval_dir / "groups").glob("*/" + RULES_FILE))


def generate_pool_merged(train_papers, args, eval_dir: Path):
    """Phase 1 (merged) — build the UNPRUNED pool across all groups.

    Delegates to silver_distillation_merged.run with prune_alpha=1.0 so the
    pool is alpha-independent, and skips every post-run report: finalize, the
    LLM FP-judge, and the metric ladder all cost time or tokens and are
    meaningless on an intentionally unpruned pool.
    """
    print("=" * 72)
    print(f"PHASE 1 (merged) — candidate pool on {len(train_papers)} paper(s), "
          f"alpha=1.0, types={args.structure_types}")
    print("=" * 72)
    ns = SimpleNamespace(
        structure_types=args.structure_types,
        pilot_papers=",".join(train_papers),
        t2_dir=str(args.t2_dir), tex_dir=str(args.tex_dir),
        eval_dir=str(eval_dir),
        model=args.model, threshold=args.threshold,
        batch_size=args.batch_size,
        origin_filter=args.origin_filter,
        match_metric=args.match_metric,
        match_mode=args.match_mode, cover=args.cover,
        prune_alpha=1.0,          # <-- the whole point: no pruning during generation
        # Distillation is cumulative, so processing order changes the pool. It
        # does NOT interfere with cross-validation: in pool-once mode generation
        # happens once over all train papers and the folds only re-prune, and
        # under --strict-cv each fold ranks its own subset. Set this to match
        # whatever production uses, so the evaluated student is the shipped one.
        order=args.order,
        resume=args.resume,
        metadata=None,
        # Train papers come from the caller's fold split; the split guard would
        # re-derive membership from metadata.csv and reject an intentional
        # arrangement, so it is bypassed here rather than fought.
        allow_test_papers=True,
        skip_finalize=True, skip_fp_judge=True, skip_ladder=True,
        ladder_prompt_version=args.prompt_version,
        max_rule_seconds=args.max_rule_seconds,
    )
    mrg.run(ns)
    snaps = snapshot_pool_merged(eval_dir)
    print(f"\n  pool snapshotted -> {len(snaps)} group file(s) "
          f"({count_active_rules_merged(eval_dir)} active rules)")
    return snaps


def snapshot_pool_merged(eval_dir: Path):
    files = _group_rule_files(eval_dir)
    if not files:
        raise FileNotFoundError(
            f"No groups/*/{RULES_FILE} under {eval_dir} — generation produced no rules")
    out = []
    for f in files:
        dst = f.with_name(POOL_SNAPSHOT)
        shutil.copy2(f, dst)
        out.append(dst)
    return out


def restore_pool_merged(eval_dir: Path):
    """Reset every group's rules file to its unpruned pool.

    prune_rules mutates in place, so without this each alpha would prune the
    already-pruned output of the previous one and the sweep would be nonsense.
    """
    snaps = sorted((eval_dir / "groups").glob("*/" + POOL_SNAPSHOT))
    if not snaps:
        raise FileNotFoundError(f"No group pool snapshots under {eval_dir}")
    for s in snaps:
        shutil.copy2(s, s.with_name(RULES_FILE))


def count_active_rules_merged(eval_dir: Path):
    total = 0
    for f in _group_rule_files(eval_dir):
        try:
            total += seq.count_compiled_patterns(f)
        except Exception:                           # noqa: BLE001
            return -1
    return total


def score_set_merged(papers, tex_dir: Path, types, gold_dir: Path,
                     threshold: float, eval_dir: Path):
    """Pooled P/R/F1 across ALL types, using the merged parser path.

    Pooled (micro) rather than a per-type macro, per the project convention:
    a macro over 14 types is dominated by the sparse ones.
    """
    gold_by_type = {t: mrg.load_gold_texts(gold_dir / FNAME_MAP[t]) for t in types}
    tp = fp = fn = 0
    per_paper, f1s = {}, []
    for pid in papers:
        try:
            buckets = mrg.parse_buckets(pid, Path(tex_dir), types, eval_dir=eval_dir)
        except Exception as e:                      # noqa: BLE001
            print(f"    WARNING: scoring {pid} failed: {e}")
            continue
        ptp = pfp = pfn = 0
        for t in types:
            m = mrg.metrics(buckets[t], gold_by_type[t].get(pid, []), threshold)
            ptp += m["tp"]; pfp += m["fp"]; pfn += m["fn"]
        tp += ptp; fp += pfp; fn += pfn
        p = ptp / (ptp + pfp) if (ptp + pfp) else 0.0
        r = ptp / (ptp + pfn) if (ptp + pfn) else 0.0
        f = 2 * p * r / (p + r) if (p + r) else 0.0
        per_paper[pid] = {"tp": ptp, "fp": pfp, "fn": pfn, "f1": f}
        f1s.append(f)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": prec, "recall": rec, "f1": f1,
            "macro_f1": statistics.mean(f1s) if f1s else 0.0,
            "n_papers": len(per_paper), "per_paper": per_paper}


def sweep_alpha_merged(alphas, prune_papers, score_papers, args, eval_dir: Path,
                       gold_dir: Path, tex_search_dirs, types, label=""):
    """Phase 3 (merged) — per alpha: restore every group, prune each, re-score.

    One prune_rules call PER GROUP, each with its group's gold, plus the
    all-types gold as m3's support set — mirroring what the merged runner does
    per paper. `prune_papers` supplies the FDR statistics; `score_papers` is the
    held-out set, which is what makes this a validation and not self-fitting.
    """
    groups = _merged_groups(types)
    all_gold = mrg.build_group_gold(gold_dir, "_alltypes", types)
    rows = []
    for a in alphas:
        restore_pool_merged(eval_dir)
        n_before = count_active_rules_merged(eval_dir)
        t0 = time.time()
        n_pruned = 0
        for gkey, gtypes in groups.items():
            gfile = eval_dir / "groups" / gkey / RULES_FILE
            if not gfile.exists():
                continue
            n_pruned += prune_rules(
                paper_ids=list(prune_papers), structure_type=gkey,
                gold_csv=str(mrg.build_group_gold(gold_dir, gkey, gtypes)),
                eval_dir=str(eval_dir / "groups" / gkey),
                threshold=args.threshold, max_fdr=a,
                tex_search_dirs=tex_search_dirs,
                # already time-guarded during generation; re-running the guard
                # per alpha would dominate sweep runtime for no benefit
                max_rule_seconds=None,
                match_mode=args.match_mode, cover=args.cover,
                support_gold_csv=str(all_gold),
            )
        n_after = count_active_rules_merged(eval_dir)
        m = score_set_merged(score_papers, args.tex_dir, types, gold_dir,
                             args.threshold, eval_dir=eval_dir)
        rows.append({
            "label": label, "alpha": a,
            "rules_before": n_before, "rules_pruned": n_pruned,
            "rules_after": n_after,
            "precision": m["precision"], "recall": m["recall"],
            "f1": m["f1"], "macro_f1": m["macro_f1"],
            "tp": m["tp"], "fp": m["fp"], "fn": m["fn"],
            "secs": round(time.time() - t0, 1),
        })
        print(f"    alpha={a:<5.2f} rules {n_before}->{n_after} "
              f"(-{n_pruned})  P={m['precision']:.3f} R={m['recall']:.3f} "
              f"F1={m['f1']:.3f}")
    return rows


# ---------------------------------------------------------------------------
# paper selection / folds
# ---------------------------------------------------------------------------

def papers_from_metadata(metadata_csv: Path, split: str, model_prefix=None):
    """Pull paper ids for a split out of corpus/silver/metadata.csv."""
    rows = list(csv.DictReader(open(metadata_csv, encoding="utf-8")))
    out = []
    for r in rows:
        if r.get("split") != split:
            continue
        if model_prefix and not (r.get("model") or "").startswith(model_prefix):
            continue
        out.append(r["paper_id"])
    # metadata.csv has one row per *extraction*; a paper re-extracted under
    # several prompts appears more than once. Dedupe, keep first-seen order.
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p); uniq.append(p)
    return uniq


def make_folds(papers, k, seed=0):
    """Deterministic k-fold partition (no numpy dependency).

    Round-robin over a seed-rotated list: keeps folds balanced to within one
    paper even for small k, and is stable across runs given the same seed.
    """
    if k < 2:
        raise ValueError("--folds must be >= 2")
    if k > len(papers):
        raise ValueError("--folds (%d) exceeds number of train papers (%d)"
                         % (k, len(papers)))
    ordered = sorted(papers)
    rot = seed % len(ordered)
    ordered = ordered[rot:] + ordered[:rot]
    folds = [[] for _ in range(k)]
    for i, p in enumerate(ordered):
        folds[i % k].append(p)
    return folds


# ---------------------------------------------------------------------------
# gold / scoring
# ---------------------------------------------------------------------------

def stage_flat_tex(papers, flat_dir: Path, staged_root: Path):
    """Adapt a FLAT tex directory to the ``<paper>/source/<paper>.tex`` layout.

    Both local tex stores are flat — ``portal/data/tier2_tex/paper001.tex`` and
    ``corpus/silver/tex_pool/<arxiv_id>.tex`` — but the distillation pipeline
    looks for ``<tex_dir>/<paper>/source/*.tex``. Rather than patch Yaron's
    loader, mirror the flat files into the expected shape. Symlink where the
    filesystem allows it, copy otherwise (WSL/NTFS often refuses symlinks).
    """
    staged_root.mkdir(parents=True, exist_ok=True)
    made, missing = 0, []
    for pid in papers:
        src = flat_dir / f"{pid}.tex"
        if not src.exists():                      # tolerate arxiv-style ids
            alt = flat_dir / f"{pid.replace('/', '_')}.tex"
            src = alt if alt.exists() else src
        if not src.exists():
            missing.append(pid)
            continue
        dst_dir = staged_root / pid / "source"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / f"{pid}.tex"
        if dst.exists() or dst.is_symlink():
            continue
        try:
            dst.symlink_to(src.resolve())
        except (OSError, NotImplementedError):
            shutil.copy2(src, dst)
        made += 1
    print(f"  staged {made} tex file(s) -> {staged_root}"
          + (f"   ({len(missing)} MISSING: {missing[:4]})" if missing else ""))
    return staged_root, missing


def ensure_gold(papers, t2_dir: Path, gold_dir: Path, structure_type: str,
                origin_filter=None):
    """Make sure the silver-gold CSV covers every paper in `papers`.

    run_sequential only converts its own pilot papers, so test-fold papers must
    be added explicitly before they can be scored.
    """
    gold_csv = gold_dir / FNAME_MAP[structure_type]
    have = set()
    if gold_csv.exists():
        with open(gold_csv, encoding="utf-8") as f:
            have = {r["paper_id"] for r in csv.DictReader(f)}
    added = 0
    for pid in papers:
        if pid in have:
            continue
        t2 = t2_dir / f"{pid}.json"
        if not t2.exists():
            print(f"    WARNING: no tier-2 JSON for {pid} ({t2}) — cannot score it")
            continue
        _, n = convert_t2_to_gold_csv(t2, structure_type, gold_dir,
                                      origin_filter=origin_filter)
        added += 1
    if added:
        print(f"    (+{added} paper(s) added to gold CSV)")
    return gold_csv


def score_set(papers, tex_dir: Path, structure_type: str, gold_csv: Path,
              threshold: float, eval_dir=None):
    """Aggregate P/R/F1 over a set of papers.

    Returns micro (pooled TP/FP/FN — the primary number) and macro (mean of
    per-paper F1). Micro is what to quote; macro is reported because a single
    large paper can dominate the pooled counts.
    """
    tp = fp = fn = 0
    per_paper, f1s = {}, []
    for pid in papers:
        try:
            m = evaluate_single_paper(pid, tex_dir, structure_type, gold_csv,
                                      threshold, eval_dir=eval_dir)
        except Exception as e:                      # noqa: BLE001
            print(f"    WARNING: scoring {pid} failed: {e}")
            continue
        tp += m["tp"]; fp += m["fp"]; fn += m["fn"]
        per_paper[pid] = m
        f1s.append(m["f1"])
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": prec, "recall": rec, "f1": f1,
        "macro_f1": statistics.mean(f1s) if f1s else 0.0,
        "n_papers": len(per_paper),
        "per_paper": per_paper,
    }


# ---------------------------------------------------------------------------
# pool snapshot / restore
# ---------------------------------------------------------------------------

def snapshot_pool(eval_dir: Path):
    src = eval_dir / RULES_FILE
    if not src.exists():
        raise FileNotFoundError(
            f"No {RULES_FILE} in {eval_dir} — generation produced no rules")
    dst = eval_dir / POOL_SNAPSHOT
    shutil.copy2(src, dst)
    return dst


def restore_pool(eval_dir: Path):
    """Reset distilled_rules.py to the unpruned pool.

    Essential: prune_rules mutates the file in place (commenting rules out with
    '# PRUNED'), so without a restore each alpha would prune the *already
    pruned* output of the previous alpha and the sweep would be nonsense.
    """
    snap = eval_dir / POOL_SNAPSHOT
    if not snap.exists():
        raise FileNotFoundError(f"No pool snapshot at {snap}")
    shutil.copy2(snap, eval_dir / RULES_FILE)


def count_active_rules(eval_dir: Path):
    try:
        return seq.count_compiled_patterns(eval_dir / RULES_FILE)
    except Exception:                               # noqa: BLE001
        return -1


# ---------------------------------------------------------------------------
# phases
# ---------------------------------------------------------------------------

def generate_pool(train_papers, args, eval_dir: Path):
    """Phase 1 — build the UNPRUNED candidate pool (alpha = 1.0).

    Delegates entirely to Yaron's run_sequential; the only thing we impose is
    prune_alpha=1.0 so the pool is alpha-independent.
    """
    print("=" * 72)
    print(f"PHASE 1 — generate candidate pool on {len(train_papers)} paper(s), alpha=1.0")
    print("=" * 72)
    ns = SimpleNamespace(
        structure_type=args.structure_type,
        pilot_papers=",".join(train_papers),
        t2_dir=str(args.t2_dir),
        tex_dir=str(args.tex_dir),
        eval_dir=str(eval_dir),
        model=args.model,
        threshold=args.threshold,
        origin_filter=args.origin_filter,
        match_metric=args.match_metric,
        prune_alpha=1.0,          # <-- the whole point: no pruning during generation
        resume=args.resume,
    )
    run_sequential(ns)
    snap = snapshot_pool(eval_dir)
    print(f"\n  pool snapshotted -> {snap.name} "
          f"({count_active_rules(eval_dir)} active rules)")
    return snap


def sweep_alpha(alphas, prune_papers, score_papers, args, eval_dir: Path,
                gold_csv: Path, tex_search_dirs, label=""):
    """Phase 3 — for each alpha: restore pool, prune, re-score.

    `prune_papers` supplies the TP/FP statistics that drive the FDR gate;
    `score_papers` is the held-out set the resulting rule set is scored on.
    Keeping them separate is what makes this a real validation rather than
    fitting alpha on its own training signal.
    """
    rows = []
    for a in alphas:
        restore_pool(eval_dir)
        n_before = count_active_rules(eval_dir)
        t0 = time.time()
        n_pruned = prune_rules(
            paper_ids=list(prune_papers),
            structure_type=args.structure_type,
            gold_csv=str(gold_csv),
            eval_dir=str(eval_dir),
            threshold=args.threshold,
            max_fdr=a,
            tex_search_dirs=tex_search_dirs,
            # the pool was already time-guarded during generation; re-running the
            # guard on every alpha would dominate sweep runtime for no benefit
            max_rule_seconds=None,
            # Without these the gate silently reverted to m1 no matter what
            # --match-mode said. One type means there is no all-types gold to
            # act as m3's support set, so its own gold serves — m3 then buys
            # nesting tolerance within the type but not across types.
            match_mode=args.match_mode, cover=args.cover,
            support_gold_csv=str(gold_csv),
        )
        n_after = count_active_rules(eval_dir)
        m = score_set(score_papers, args.tex_dir, args.structure_type, gold_csv,
                      args.threshold, eval_dir=eval_dir)
        rows.append({
            "label": label, "alpha": a,
            "rules_before": n_before, "rules_pruned": n_pruned,
            "rules_after": n_after,
            "precision": m["precision"], "recall": m["recall"],
            "f1": m["f1"], "macro_f1": m["macro_f1"],
            "tp": m["tp"], "fp": m["fp"], "fn": m["fn"],
            "secs": round(time.time() - t0, 1),
        })
        print(f"    alpha={a:<5.2f} rules {n_before}->{n_after} "
              f"(-{n_pruned})  P={m['precision']:.3f} R={m['recall']:.3f} "
              f"F1={m['f1']:.3f}")
    return rows


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Held-out distillation with k-fold alpha tuning (ROADMAP 7.4)",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--pipeline", default="sequential",
                   choices=["sequential", "merged"],
                   help="Which distillation pipeline to evaluate. 'sequential' "
                        "distils ONE type into one rules file (the historical "
                        "behaviour). 'merged' distils --structure-types into 5 "
                        "base-method GROUPS sharing a rules file each — this is "
                        "the pipeline actually shipped, so it is the one whose "
                        "held-out number describes the deployed student.")
    p.add_argument("--structure-type", default=None, choices=list(FNAME_MAP.keys()),
                   help="sequential only: the single type to distil")
    p.add_argument("--structure-types", default=",".join(mrg.ALL_SILVER_TYPES),
                   help="merged only: comma list of types (default: all 14)")
    p.add_argument("--tex-dir", required=True, type=Path,
                   help="Directory with <paper>/source/*.tex, OR a flat dir of "
                        "<paper>.tex when --flat-tex is given")
    p.add_argument("--flat-tex", action="store_true",
                   help="--tex-dir holds flat <paper>.tex files (as "
                        "portal/data/tier2_tex and corpus/silver/tex_pool do). "
                        "They are staged into the <paper>/source/ layout the "
                        "pipeline expects.")
    p.add_argument("--eval-dir", required=True, type=Path,
                   help="Working dir for gold CSV, rules, pool snapshot, report")
    p.add_argument("--t2-dir", type=Path, default=REPO / "portal/data/tier2",
                   help="Directory of tier-2 silver JSONs (<paper>.json)")

    src = p.add_argument_group("paper selection")
    src.add_argument("--train-papers", default=None, help="Comma-separated ids")
    src.add_argument("--test-papers", default=None, help="Comma-separated ids")
    src.add_argument("--metadata", type=Path, default=REPO / "corpus/silver/metadata.csv",
                     help="Used when --train-papers/--test-papers are omitted")
    src.add_argument("--train-split", default="train")
    src.add_argument("--test-split", default="test")
    src.add_argument("--model-prefix", default=None,
                     help="Restrict metadata rows to a model, e.g. 'opus-4.8'")
    src.add_argument("--limit-train", type=int, default=None)
    src.add_argument("--limit-test", type=int, default=None)

    cv = p.add_argument_group("cross-validation / alpha")
    cv.add_argument("--folds", type=int, default=5)
    cv.add_argument("--seed", type=int, default=0)
    cv.add_argument("--alphas", default="0.0,0.1,0.2,0.3,0.4,0.5,0.7,1.0",
                    help="Comma-separated alpha grid")
    cv.add_argument("--strict-cv", action="store_true",
                    help="Regenerate the pool per fold (k x API cost, no leakage). "
                         "Default reuses one pool built on all train papers, which "
                         "makes CV F1 optimistic — see module docstring.")

    run = p.add_argument_group("execution")
    run.add_argument("--skip-generation", action="store_true",
                     help="Reuse the existing pool snapshot. Makes the whole run "
                          "zero-API-call.")
    run.add_argument("--dry-run", action="store_true",
                     help="Print the plan and exit without running anything.")
    # See silver_distillation_sequential.py: the previous default
    # "claude-sonnet-4-5-20250514" is not a real model id and 404s.
    run.add_argument("--model", default="claude-sonnet-4-6")
    run.add_argument("--threshold", type=float, default=0.7)
    run.add_argument("--origin-filter", default=None)
    run.add_argument("--match-metric", default="jaccard",
                     choices=["jaccard", "containment"])
    run.add_argument("--resume", action="store_true")
    run.add_argument("--batch-size", type=int, default=8,
                     help="merged only: FNs per analyze LLM call")
    run.add_argument("--match-mode", default="m1", choices=["m1", "m3"],
                     help="prune-gate scoring, BOTH pipelines (see "
                          "match_modes.py). m1 = strict same-type 1:1; m3 = "
                          "nesting/label tolerant.")
    run.add_argument("--cover", type=float, default=0.7,
                     help="m3: fraction of a span that must be accounted for")
    run.add_argument("--max-rule-seconds", type=float, default=10.0,
                     help="merged only: time guard during pool generation")
    run.add_argument("--prompt-version", default="v5.1",
                     help="merged only: extraction config tag passed through")
    run.add_argument("--order", default="worst-first",
                     choices=["given", "worst-first"],
                     help="merged only: distillation order. Defaults to "
                          "'worst-first' (hard-example mining: rank papers by how "
                          "much the base parser misses and distil the worst "
                          "first) so the held-out number describes the student "
                          "production actually ships. Does not conflict with CV — "
                          "generation is per-pool, folds only re-prune. Pass "
                          "'given' to distil in the order supplied.")
    args = p.parse_args()

    # The two pipelines take different type arguments; catch the mismatch here
    # rather than letting it surface as a confusing failure mid-generation.
    if args.pipeline == "sequential" and not args.structure_type:
        p.error("--structure-type is required with --pipeline sequential")
    if args.pipeline == "merged" and args.structure_type:
        p.error("--structure-type is sequential-only; "
                "use --structure-types with --pipeline merged")

    # Configure matching BEFORE anything scores. This script previously took
    # --match-metric and never applied it: the merged path only used containment
    # because mrg.run() set it as a side effect during generation, so
    # --skip-generation silently scored the entire sweep on jaccard.
    seq.set_match_metric(args.match_metric)

    MERGED = args.pipeline == "merged"
    types = ([t.strip() for t in args.structure_types.split(",") if t.strip()]
             if MERGED else [args.structure_type])
    bad = [t for t in types if t not in FNAME_MAP]
    if bad:
        p.error(f"unknown structure type(s): {bad}")

    eval_dir = args.eval_dir.resolve()
    eval_dir.mkdir(parents=True, exist_ok=True)
    gold_dir = eval_dir / "silver_gold"
    gold_dir.mkdir(parents=True, exist_ok=True)
    alphas = [float(a) for a in args.alphas.split(",")]

    # ---- paper sets -------------------------------------------------------
    if args.train_papers:
        train = [x.strip() for x in args.train_papers.split(",") if x.strip()]
    else:
        train = papers_from_metadata(args.metadata, args.train_split, args.model_prefix)
    if args.test_papers:
        test = [x.strip() for x in args.test_papers.split(",") if x.strip()]
    else:
        test = papers_from_metadata(args.metadata, args.test_split, args.model_prefix)
    if args.limit_train:
        train = train[:args.limit_train]
    if args.limit_test:
        test = test[:args.limit_test]

    overlap = set(train) & set(test)
    if overlap:
        print(f"ERROR: {len(overlap)} paper(s) in BOTH train and test: "
              f"{sorted(overlap)[:5]}")
        sys.exit(1)
    if not train:
        print("ERROR: empty training set"); sys.exit(1)

    folds = make_folds(train, args.folds, args.seed)

    print("=" * 72)
    print("HELD-OUT DISTILLATION WITH ALPHA TUNING")
    print("=" * 72)
    print(f"  pipeline       : {args.pipeline}"
          + (f"  ({len(_merged_groups(types))} groups over {len(types)} types)"
             if MERGED else ""))
    print(f"  structure_type : {', '.join(types)}")
    print(f"  train          : {len(train)} papers")
    print(f"  test (held out): {len(test)} papers")
    print(f"  folds          : {args.folds}  sizes={[len(f) for f in folds]}")
    print(f"  alpha grid     : {alphas}")
    print(f"  eval_dir       : {eval_dir}")
    print(f"  generation     : {'SKIPPED (reusing pool)' if args.skip_generation else 'will run (API cost)'}")
    print(f"  cv mode        : {'strict (pool per fold)' if args.strict_cv else 'pool-once (CV F1 optimistic)'}")
    if not args.strict_cv:
        print("                   -> quote the TEST number, not CV F1")
    print()
    if args.dry_run:
        print("DRY RUN — nothing executed.")
        for i, f in enumerate(folds, 1):
            print(f"    fold {i}: val={len(f)} train={len(train)-len(f)}")
        return

    # Flat tex stores must be reshaped before anything can find the sources.
    if args.flat_tex:
        staged, missing = stage_flat_tex(train + test, args.tex_dir,
                                         eval_dir / "_tex_staged")
        args.tex_dir = staged
        if missing:
            # Papers with no .tex cannot be parsed; drop them rather than let
            # them silently score as all-FN and depress every metric.
            drop = set(missing)
            train = [p for p in train if p not in drop]
            test = [p for p in test if p not in drop]
            folds = make_folds(train, min(args.folds, len(train)), args.seed)
            print(f"  dropped {len(drop)} paper(s) with no .tex; "
                  f"train={len(train)} test={len(test)}")
            if not train:
                print("ERROR: no training papers left after dropping missing tex")
                sys.exit(1)

    tex_search_dirs = [str(args.tex_dir / p / "source") for p in train + test]

    # ---- Phase 1: pool ----------------------------------------------------
    if args.skip_generation:
        have = (bool(sorted((eval_dir / "groups").glob("*/" + POOL_SNAPSHOT)))
                if MERGED else (eval_dir / POOL_SNAPSHOT).exists())
        if not have:
            where = f"{eval_dir}/groups/*/{POOL_SNAPSHOT}" if MERGED \
                else f"{eval_dir / POOL_SNAPSHOT}"
            print(f"ERROR: --skip-generation but no pool snapshot at {where}.\n"
                  f"       Run once without --skip-generation to build it.")
            sys.exit(1)
        print("PHASE 1 — SKIPPED, reusing pool snapshot")
        if MERGED:
            restore_pool_merged(eval_dir)
            print(f"  pool has {count_active_rules_merged(eval_dir)} active rules\n")
        else:
            restore_pool(eval_dir)
            print(f"  pool has {count_active_rules(eval_dir)} active rules\n")
    elif MERGED:
        generate_pool_merged(train, args, eval_dir)
    else:
        generate_pool(train, args, eval_dir)

    # Gold for every type in scope. The merged path needs one CSV per type so
    # build_group_gold can assemble per-group and all-types views from them.
    gold_csv = None
    for t in types:
        c = ensure_gold(train + test, args.t2_dir, gold_dir, t, args.origin_filter)
        if t == types[0]:
            gold_csv = c

    # ---- baseline (manual rules only, no distilled rules) -----------------
    print("=" * 72)
    print("BASELINE — manual rules only")
    print("=" * 72)
    if not test:
        base_test = None
    elif MERGED:
        base_test = score_set_merged(test, args.tex_dir, types, gold_dir,
                                     args.threshold, eval_dir=None)
    else:
        base_test = score_set(test, args.tex_dir, args.structure_type, gold_csv,
                              args.threshold, eval_dir=None)
    if base_test:
        print(f"  TEST  P={base_test['precision']:.3f} R={base_test['recall']:.3f} "
              f"F1={base_test['f1']:.3f} (macro {base_test['macro_f1']:.3f})")
    print()

    # ---- Phase 3: CV alpha sweep -----------------------------------------
    print("=" * 72)
    print(f"PHASE 3 — {args.folds}-fold CV alpha sweep")
    print("=" * 72)
    all_rows = []
    for i, val in enumerate(folds, 1):
        tr = [p for p in train if p not in set(val)]
        print(f"\n  fold {i}/{args.folds}: prune-on={len(tr)} score-on={len(val)}")
        if args.strict_cv:
            # regenerate the pool using only this fold's training papers
            fold_dir = eval_dir / f"fold{i}"
            fold_dir.mkdir(parents=True, exist_ok=True)
            fold_gold_dir = fold_dir / "silver_gold"
            fold_gold = None
            for t in types:
                c = ensure_gold(tr + val, args.t2_dir, fold_gold_dir, t,
                                args.origin_filter)
                if t == types[0]:
                    fold_gold = c
            if MERGED:
                generate_pool_merged(tr, args, fold_dir)
                all_rows += sweep_alpha_merged(alphas, tr, val, args, fold_dir,
                                               fold_gold_dir, tex_search_dirs,
                                               types, label=f"fold{i}")
            else:
                generate_pool(tr, args, fold_dir)
                all_rows += sweep_alpha(alphas, tr, val, args, fold_dir, fold_gold,
                                        tex_search_dirs, label=f"fold{i}")
        elif MERGED:
            all_rows += sweep_alpha_merged(alphas, tr, val, args, eval_dir,
                                           gold_dir, tex_search_dirs, types,
                                           label=f"fold{i}")
        else:
            all_rows += sweep_alpha(alphas, tr, val, args, eval_dir, gold_csv,
                                    tex_search_dirs, label=f"fold{i}")

    # ---- pick alpha* ------------------------------------------------------
    by_alpha = {}
    for r in all_rows:
        by_alpha.setdefault(r["alpha"], []).append(r["f1"])
    cv_curve = [{"alpha": a,
                 "cv_f1_mean": statistics.mean(v),
                 "cv_f1_sd": statistics.pstdev(v) if len(v) > 1 else 0.0,
                 "n_folds": len(v)}
                for a, v in sorted(by_alpha.items())]
    best = max(cv_curve, key=lambda r: r["cv_f1_mean"])
    alpha_star = best["alpha"]

    print("\n" + "=" * 72)
    print("CV RESULT — F1 vs alpha")
    print("=" * 72)
    print(f"  {'alpha':>6} {'CV F1':>8} {'sd':>7}")
    for r in cv_curve:
        star = "  <-- alpha*" if r["alpha"] == alpha_star else ""
        print(f"  {r['alpha']:>6.2f} {r['cv_f1_mean']:>8.4f} {r['cv_f1_sd']:>7.4f}{star}")

    # --- diagnostics -------------------------------------------------------
    # Two very different failures both look like "a flat curve", and they need
    # different responses, so separate them explicitly.
    #
    #  (a) DEGENERATE: pruning never fired at any alpha. The sweep is a no-op
    #      and alpha* is arbitrary. Usually a plumbing fault, not a finding.
    #  (b) FLAT: pruning did fire, but F1 is insensitive to it. A real (and
    #      reportable) result: alpha does not matter on this data.
    # Ask whether alpha moved the surviving rule count WITHIN a fold.
    #
    # The previous version bucketed rules_after by alpha ACROSS folds and then
    # kept only buckets of size 1, so as soon as two folds disagreed at the same
    # alpha — the normal case, since folds hold different papers — every bucket
    # was discarded and the check reported "degenerate" on a perfectly healthy
    # sweep. Observed on a 3-fold run where pruning removed 10/6/5/3/2/0 rules
    # as alpha rose: unmistakably working, flagged as degenerate.
    rules_by_fold = {}
    for r in all_rows:
        rules_by_fold.setdefault(r["label"], {})[r["alpha"]] = r["rules_after"]
    alpha_moved_rules = any(len(set(d.values())) > 1 for d in rules_by_fold.values())
    total_pruned = sum(r["rules_pruned"] for r in all_rows)
    degenerate = (total_pruned == 0) or not alpha_moved_rules

    spread = max(r["cv_f1_mean"] for r in cv_curve) - min(r["cv_f1_mean"] for r in cv_curve)
    typical_sd = statistics.mean([r["cv_f1_sd"] for r in cv_curve]) if cv_curve else 0.0
    flat = spread <= typical_sd

    if degenerate:
        print("\n  " + "!" * 66)
        print("  DEGENERATE SWEEP — pruning removed 0 rules at EVERY alpha.")
        print("  alpha* below is arbitrary and must NOT be reported as tuned.")
        print("")
        print("  Most likely cause: FP-to-rule attribution failed, so no rule")
        print("  could be blamed for its false positives. Check the prune output")
        print("  above for '<unattributed>'. In distillation_analysis.prune_rules:")
        print("    - fast path needs EVERY result dict to carry 'rule_name';")
        print("      one missing value drops the whole run to the slow path;")
        print("    - the slow path only collects patterns whose variable name")
        print("      starts with '_', but generated rules are named like")
        print("      'P1_TEXTIT_IS' / 'ENV_NOTATION', so it can match nothing")
        print("      and silently attribute every FP to '<unattributed>'.")
        print("  Fix attribution before trusting any alpha result.")
        print("  " + "!" * 66)
    elif flat:
        print(f"\n  NOTE: pruning fired ({total_pruned} rule-removals across folds) "
              f"but the curve is flat\n        (spread {spread:.4f} <= mean fold sd "
              f"{typical_sd:.4f}). alpha is not identified by\n        this data — "
              f"report that finding rather than a tuned optimum.")

    # ---- Phase 5: final fit on all train, report on TEST ------------------
    print("\n" + "=" * 72)
    print(f"PHASE 5 — refit at alpha*={alpha_star:.2f} on all {len(train)} train papers, "
          f"report on TEST")
    print("=" * 72)
    if MERGED:
        restore_pool_merged(eval_dir)
        n_before = count_active_rules_merged(eval_dir)
        n_pruned = 0
        all_gold = mrg.build_group_gold(gold_dir, "_alltypes", types)
        for gkey, gtypes in _merged_groups(types).items():
            if not (eval_dir / "groups" / gkey / RULES_FILE).exists():
                continue
            n_pruned += prune_rules(
                paper_ids=train, structure_type=gkey,
                gold_csv=str(mrg.build_group_gold(gold_dir, gkey, gtypes)),
                eval_dir=str(eval_dir / "groups" / gkey),
                threshold=args.threshold, max_fdr=alpha_star,
                tex_search_dirs=tex_search_dirs, max_rule_seconds=None,
                match_mode=args.match_mode, cover=args.cover,
                support_gold_csv=str(all_gold))
        n_after = count_active_rules_merged(eval_dir)
    else:
        restore_pool(eval_dir)
        n_before = count_active_rules(eval_dir)
        n_pruned = prune_rules(
            paper_ids=train, structure_type=args.structure_type,
            gold_csv=str(gold_csv), eval_dir=str(eval_dir),
            threshold=args.threshold, max_fdr=alpha_star,
            tex_search_dirs=tex_search_dirs, max_rule_seconds=None,
            match_mode=args.match_mode, cover=args.cover,
            support_gold_csv=str(gold_csv))
        n_after = count_active_rules(eval_dir)
    print(f"  rules {n_before} -> {n_after} (pruned {n_pruned})")

    if not test:
        dist_test = None
    elif MERGED:
        dist_test = score_set_merged(test, args.tex_dir, types, gold_dir,
                                     args.threshold, eval_dir=eval_dir)
    else:
        dist_test = score_set(test, args.tex_dir, args.structure_type, gold_csv,
                              args.threshold, eval_dir=eval_dir)

    report = {
        "pipeline": args.pipeline,
        "structure_types": types,
        "groups": {g: ts for g, ts in _merged_groups(types).items()} if MERGED else None,
        "structure_type": args.structure_type,
        "alpha_star": alpha_star,
        "alpha_grid": alphas,
        "cv_curve": cv_curve,
        "cv_flat_warning": flat,
        "cv_degenerate": degenerate,
        "total_rules_pruned_across_folds": total_pruned,
        "folds": args.folds,
        "seed": args.seed,
        "strict_cv": args.strict_cv,
        "n_train": len(train), "n_test": len(test),
        "train_papers": train, "test_papers": test,
        "rules_pool": n_before, "rules_at_alpha_star": n_after,
        "baseline_test": {k: v for k, v in base_test.items() if k != "per_paper"} if base_test else None,
        "distilled_test": {k: v for k, v in dist_test.items() if k != "per_paper"} if dist_test else None,
        "fold_rows": all_rows,
    }
    (eval_dir / "heldout_alpha_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    with open(eval_dir / "alpha_curve.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader(); w.writerows(all_rows)

    print("\n" + "=" * 72)
    print("FINAL — held-out TEST")
    print("=" * 72)
    if base_test and dist_test:
        d = dist_test["f1"] - base_test["f1"]
        print(f"  {'stage':<12} {'P':>7} {'R':>7} {'F1':>7}")
        print(f"  {'base':<12} {base_test['precision']:>7.3f} {base_test['recall']:>7.3f} "
              f"{base_test['f1']:>7.3f}")
        print(f"  {'distilled':<12} {dist_test['precision']:>7.3f} {dist_test['recall']:>7.3f} "
              f"{dist_test['f1']:>7.3f}   (delta {d:+.3f})")
        print(f"\n  Reported on {dist_test['n_papers']} held-out papers, never seen by "
              f"generation or by the alpha sweep.")
        print("  The +LLM-judge stage is a DIFFERENT mechanism and is not included "
              "here —\n  report it separately, do not fold it into this delta.")
    else:
        print("  No test papers supplied — CV curve only.")
    print(f"\n  report -> {eval_dir/'heldout_alpha_report.json'}")
    print(f"  curve  -> {eval_dir/'alpha_curve.csv'}")


if __name__ == "__main__":
    main()
