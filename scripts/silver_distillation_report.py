#!/usr/bin/env python3
"""
Silver Distillation Report
===========================
Reads iteration_log.json produced by silver_distillation_sequential.py
and generates summary tables + matplotlib plots for:

  1. Sub-linearity (new FNs per paper, cumulative rules)
  2. Cost breakdown
  3. Time breakdown
  4. P/R/F1 progression (baseline → post-distillation)
  5. Already-covered ratio

Usage:
    python scripts/silver_distillation_report.py \
        --log src/LLMVersion/definition_eval_silver/iteration_log.json
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import matplotlib
    matplotlib.use('Agg')  # non-interactive backend
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


def load_log(path: str) -> list[dict]:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def print_summary_table(log: list[dict]):
    print(f"\n{'='*80}")
    print("SILVER DISTILLATION — SUMMARY TABLE")
    print(f"{'='*80}")
    print(f"{'#':<3} {'Paper':<12} {'FNs':>4} {'Covered':>8} {'New':>4} "
          f"{'Rules':>6} {'Cost($)':>8} {'Time(s)':>8} {'F1-pre':>7} {'F1-post':>8}")
    print("-" * 80)
    for e in log:
        print(f"{e['paper_idx']:<3} {e['paper_id']:<12} "
              f"{e['total_fns']:>4} {e['already_covered']:>8} "
              f"{e['new_fns_to_distill']:>4} {e['new_rules_in_file']:>6} "
              f"{e['total_cost_usd']:>8.4f} {e['wall_time_seconds']:>8.1f} "
              f"{e['baseline_f1']:>7.3f} {e['post_f1']:>8.3f}")

    total_cost = sum(e['total_cost_usd'] for e in log)
    avg_time = sum(e['wall_time_seconds'] for e in log) / len(log)
    print("-" * 80)
    print(f"{'':3} {'TOTAL/AVG':<12} "
          f"{sum(e['total_fns'] for e in log):>4} "
          f"{sum(e['already_covered'] for e in log):>8} "
          f"{sum(e['new_fns_to_distill'] for e in log):>4} "
          f"{log[-1]['cumulative_rules'] if log else 0:>6} "
          f"{total_cost:>8.4f} {avg_time:>8.1f} "
          f"{sum(e['baseline_f1'] for e in log)/len(log):>7.3f} "
          f"{sum(e['post_f1'] for e in log)/len(log):>8.3f}")


def print_cost_table(log: list[dict]):
    print(f"\n{'='*80}")
    print("COST BREAKDOWN")
    print(f"{'='*80}")
    print(f"{'#':<3} {'Paper':<12} {'Analyze$':>10} {'Aggr$':>10} "
          f"{'Total$':>10} {'Cumul$':>10} {'LLM Calls':>10}")
    print("-" * 70)
    for e in log:
        print(f"{e['paper_idx']:<3} {e['paper_id']:<12} "
              f"{e['analyze_cost_usd']:>10.4f} {e['aggregate_cost_usd']:>10.4f} "
              f"{e['total_cost_usd']:>10.4f} {e['cumulative_cost_usd']:>10.4f} "
              f"{e['analyze_llm_calls']:>10}")


def print_sublinearity(log: list[dict]):
    print(f"\n{'='*80}")
    print("SUB-LINEARITY ANALYSIS")
    print(f"{'='*80}")
    fns = [e['new_fns_to_distill'] for e in log]
    covered = [e['already_covered'] for e in log]
    for i, e in enumerate(log):
        cover_pct = (e['already_covered'] / (e['total_fns'] + e['already_covered']) * 100
                     if (e['total_fns'] + e['already_covered']) > 0 else 0)
        bar = '#' * e['new_fns_to_distill'] + '.' * e['already_covered']
        print(f"  Paper {e['paper_idx']}: new={e['new_fns_to_distill']:>3}  "
              f"covered={e['already_covered']:>3}  "
              f"coverage={cover_pct:>5.1f}%  |{bar}")

    if len(fns) >= 2:
        mid = len(fns) // 2
        first_half = sum(fns[:mid])
        second_half = sum(fns[mid:])
        ratio = second_half / first_half if first_half > 0 else float('inf')
        print(f"\n  First half sum:  {first_half}")
        print(f"  Second half sum: {second_half}")
        print(f"  Ratio: {ratio:.2f} {'(sub-linear)' if ratio < 1 else '(not sub-linear)'}")


def plot_all(log: list[dict], out_dir: Path):
    if not HAS_MPL:
        print("\n  [skip] matplotlib not available — no plots generated")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    papers = [e['paper_id'] for e in log]
    idxs = [e['paper_idx'] for e in log]

    # --- Plot 1: Sub-linearity (new FNs + already covered, stacked bar) ---
    fig, ax = plt.subplots(figsize=(10, 5))
    new_fns = [e['new_fns_to_distill'] for e in log]
    covered = [e['already_covered'] for e in log]
    ax.bar(idxs, new_fns, label='New FNs to distill', color='#e74c3c')
    ax.bar(idxs, covered, bottom=new_fns, label='Already covered', color='#2ecc71')
    ax.set_xlabel('Paper Index')
    ax.set_ylabel('Count')
    ax.set_title('Sub-linearity: New FNs vs Already Covered')
    ax.set_xticks(idxs)
    ax.set_xticklabels(papers, rotation=45, ha='right')
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / 'sublinearity_bars.png', dpi=150)
    plt.close(fig)

    # --- Plot 2: Cumulative rules (should be concave for sub-linearity) ---
    fig, ax = plt.subplots(figsize=(8, 5))
    cum_rules = [e['cumulative_rules'] for e in log]
    ax.plot(idxs, cum_rules, 'o-', color='#3498db', linewidth=2)
    ax.set_xlabel('Paper Index')
    ax.set_ylabel('Cumulative Compiled Patterns')
    ax.set_title('Cumulative Rules Growth')
    ax.set_xticks(idxs)
    ax.set_xticklabels(papers, rotation=45, ha='right')
    fig.tight_layout()
    fig.savefig(out_dir / 'cumulative_rules.png', dpi=150)
    plt.close(fig)

    # --- Plot 3: Cost per paper ---
    fig, ax = plt.subplots(figsize=(8, 5))
    analyze_cost = [e['analyze_cost_usd'] for e in log]
    agg_cost = [e['aggregate_cost_usd'] for e in log]
    ax.bar(idxs, analyze_cost, label='Analyze', color='#f39c12')
    ax.bar(idxs, agg_cost, bottom=analyze_cost, label='Aggregate', color='#9b59b6')
    ax.set_xlabel('Paper Index')
    ax.set_ylabel('Cost (USD)')
    ax.set_title('LLM Cost per Paper')
    ax.set_xticks(idxs)
    ax.set_xticklabels(papers, rotation=45, ha='right')
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / 'cost_per_paper.png', dpi=150)
    plt.close(fig)

    # --- Plot 4: F1 progression ---
    fig, ax = plt.subplots(figsize=(10, 5))
    baseline_f1 = [e['baseline_f1'] for e in log]
    post_f1 = [e['post_f1'] for e in log]
    x = range(len(papers))
    width = 0.35
    ax.bar([i - width/2 for i in x], baseline_f1, width, label='Baseline F1',
           color='#bdc3c7')
    ax.bar([i + width/2 for i in x], post_f1, width, label='Post-distill F1',
           color='#2ecc71')
    ax.set_xlabel('Paper')
    ax.set_ylabel('F1 Score')
    ax.set_title('F1 Before vs After Distillation')
    ax.set_xticks(list(x))
    ax.set_xticklabels(papers, rotation=45, ha='right')
    ax.legend()
    ax.set_ylim(0, 1.05)
    fig.tight_layout()
    fig.savefig(out_dir / 'f1_progression.png', dpi=150)
    plt.close(fig)

    # --- Plot 5: Time per paper ---
    fig, ax = plt.subplots(figsize=(8, 5))
    times = [e['wall_time_seconds'] for e in log]
    ax.bar(idxs, times, color='#1abc9c')
    ax.set_xlabel('Paper Index')
    ax.set_ylabel('Wall-clock time (s)')
    ax.set_title('Time per Paper')
    ax.set_xticks(idxs)
    ax.set_xticklabels(papers, rotation=45, ha='right')
    fig.tight_layout()
    fig.savefig(out_dir / 'time_per_paper.png', dpi=150)
    plt.close(fig)

    print(f"\n  Plots saved to {out_dir}/")


def main():
    p = argparse.ArgumentParser(description="Silver Distillation Report")
    p.add_argument("--log", required=True,
                   help="Path to iteration_log.json")
    p.add_argument("--out-dir", default=None,
                   help="Output dir for plots (default: same dir as log)")
    args = p.parse_args()

    log = load_log(args.log)
    if not log:
        print("Empty log — nothing to report.")
        sys.exit(0)

    out_dir = Path(args.out_dir) if args.out_dir else Path(args.log).parent / "silver_report"

    print_summary_table(log)
    print_cost_table(log)
    print_sublinearity(log)
    plot_all(log, out_dir)


if __name__ == "__main__":
    main()
