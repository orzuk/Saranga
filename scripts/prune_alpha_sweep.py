#!/usr/bin/env python3
"""FDR prune-alpha sweep (no LLM).

Takes the FINAL distilled rule set (last snapshot), globally re-prunes it over
ALL papers at several --prune-alpha values, and re-evaluates each paper vs gold.
Shows whether tightening the FDR gate removes enough FP-heavy rules to flip the
net F1 vs the no-rules baseline. Pure regex + matching.

Usage:
    python scripts/prune_alpha_sweep.py \
        --eval-dir src/LLMVersion/merged_eval_silver_001_011 \
        --tex-dir /Users/yaronot/Datasets/Authomathics_data/alignment/papers \
        --alphas 0.5,0.3,0.1
"""
import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import silver_distillation_sequential as seq
import silver_distillation_merged as merged
from silver_distillation_merged import (FNAME_MAP, parse_buckets, metrics,
                                        load_gold_texts, build_group_gold,
                                        write_combined_importer,
                                        base_method_groups, count_compiled_patterns)
from distillation_analysis import prune_rules
from final_eval import overall


def _repair_until_valid(path, max_iters=400):
    """Complete any partially-commented prune block by commenting the orphaned
    trailing lines until the module parses. Returns True if valid."""
    lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
    for _ in range(max_iters):
        try:
            compile(''.join(lines), str(path), 'exec')
            path.write_text(''.join(lines), encoding='utf-8')
            return True
        except SyntaxError as e:
            ln = (e.lineno or 0) - 1
            if 0 <= ln < len(lines) and not lines[ln].lstrip().startswith('#'):
                lines[ln] = '# ' + lines[ln]
            else:
                return False
    return False


def _group_health(path, gkey):
    """Return True if the group module imports and its entry point runs."""
    try:
        ns = {'__name__': 'health'}
        exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), ns)
        fn = ns.get(f'extract_distilled_{gkey}')
        return callable(fn) and (fn("") == [] or isinstance(fn(""), list))
    except Exception:
        return False


def build_pruned(eval_dir, final_snap, groups, gold_dir, papers, tex_dir,
                 alpha, threshold):
    scratch = eval_dir / "sweep" / f"alpha_{alpha}"
    if scratch.exists():
        shutil.rmtree(scratch)
    (scratch / "groups").mkdir(parents=True)
    tex_dirs = [str(tex_dir / p / "source") for p in papers]
    n_rules = 0
    unhealthy = []
    for g in groups:
        src = final_snap / "groups" / g / "distilled_rules.py"
        gdst = scratch / "groups" / g
        gdst.mkdir(parents=True, exist_ok=True)
        if not src.exists():
            continue
        shutil.copy2(src, gdst / "distilled_rules.py")
        # The final snapshot may already be prune-corrupted (the bug we fixed);
        # complete the partial prune so it represents the correct alpha=0.5 set.
        _repair_until_valid(gdst / "distilled_rules.py")
        if alpha < 1.0:
            group_gold = build_group_gold(gold_dir, g, groups[g])
            prune_rules(paper_ids=papers, structure_type=g,
                        gold_csv=str(group_gold), eval_dir=str(gdst),
                        threshold=threshold, max_fdr=alpha, tex_search_dirs=tex_dirs)
            _repair_until_valid(gdst / "distilled_rules.py")
        if not _group_health(gdst / "distilled_rules.py", g):
            unhealthy.append(g)
        n_rules += count_compiled_patterns(gdst / "distilled_rules.py")
    write_combined_importer(scratch, groups)
    return scratch, n_rules, unhealthy


def eval_snap(snap, papers, tex_dir, types, gold, threshold):
    a9s, prs, def_fp = [], [], []
    for pid in papers:
        b = parse_buckets(pid, tex_dir, types, eval_dir=snap)
        pm = {t: metrics(b[t], gold[t].get(pid, []), threshold) for t in types}
        a9, pr = overall(pm)
        a9s.append(a9); prs.append(pr); def_fp.append(pm['definition']['fp'])
    n = len(papers)
    return sum(a9s) / n, sum(prs) / n, sum(def_fp) / n


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--eval-dir", required=True)
    p.add_argument("--tex-dir", required=True)
    p.add_argument("--alphas", default="0.5,0.3,0.1")
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--match-metric", default="containment")
    args = p.parse_args()

    eval_dir = Path(args.eval_dir).resolve()
    tex_dir = Path(args.tex_dir).resolve()
    gold_dir = eval_dir / "silver_gold"
    seq._MATCH_METRIC = args.match_metric
    types = list(FNAME_MAP.keys())
    groups = base_method_groups(types)
    import json
    papers = [e['paper_id'] for e in json.load(open(eval_dir / "iteration_log.json"))]
    gold = {t: load_gold_texts(gold_dir / FNAME_MAP[t]) for t in types}

    snaps = sorted((eval_dir / "snapshots").glob("step_*"))
    step00 = next(s for s in snaps if s.name.startswith("step_00"))
    final_snap = snaps[-1]
    alphas = [float(a) for a in args.alphas.split(",")]

    print(f"papers: {len(papers)}  final snapshot: {final_snap.name}  metric: {args.match_metric}\n")
    # baseline (no rules)
    b9, bp, bfp = eval_snap(step00, papers, tex_dir, types, gold, args.threshold)
    print(f"{'config':<18} {'rules':>5} {'mean all9':>10} {'mean present':>13} {'mean def FP':>12}")
    print("-" * 62)
    print(f"{'baseline (no rules)':<18} {'-':>5} {b9:>10.3f} {bp:>13.3f} {bfp:>12.2f}")
    for a in alphas:
        snap, nrules, unhealthy = build_pruned(eval_dir, final_snap, groups,
                                               gold_dir, papers, tex_dir, a,
                                               args.threshold)
        f9, fp, ffp = eval_snap(snap, papers, tex_dir, types, gold, args.threshold)
        tag = f"final @alpha={a}"
        warn = f"  ⚠ unhealthy groups: {unhealthy}" if unhealthy else ""
        print(f"{tag:<18} {nrules:>5} {f9:>10.3f} {fp:>13.3f} {ffp:>12.2f}"
              f"   (present Δ vs base {fp-bp:+.3f}){warn}")


if __name__ == "__main__":
    main()
