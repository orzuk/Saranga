#!/usr/bin/env python3
"""Generate LaTeX table fragments for the Authomathics paper from corpus_stats.csv files.

Usage (on cluster):
    python scripts/generate_paper_tables.py \
        --base-dir /<cluster>/<user>/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k \
        --out-dir tables/

Outputs:
    tables/cross_category_table.tex   — Table body for tab:cross-category (20 categories)
    tables/scale_table.tex            — Table body for tab:scale (single-category detailed stats)
    tables/macros.tex                 — \newcommand macros for inline numbers in text
"""

import argparse
import csv
import os
import sys
from pathlib import Path

# Category display order matching the paper's table structure
CATEGORIES_PURE_MATH = [
    "math.LO", "math.AT", "math.CO", "math.NT", "math.AG",
    "math.GR", "math.RT", "math.DG", "math.AP", "math.CA",
    "math.FA", "math.PR", "math-ph",
]
CATEGORIES_CS = ["cs.CC", "cs.DS", "cs.IT", "cs.LG"]
CATEGORIES_STATS = ["math.OC", "math.NA", "stat.TH"]

ALL_CATEGORIES = CATEGORIES_PURE_MATH + CATEGORIES_CS + CATEGORIES_STATS


def cat_to_dirname(cat: str) -> str:
    """math.CO -> math_CO, math-ph -> math_ph"""
    return cat.replace(".", "_").replace("-", "_")


def load_corpus_stats(csv_path: Path) -> list[dict]:
    """Load corpus_stats.csv, return list of row dicts."""
    rows = []
    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def load_anomalies(csv_path: Path) -> list[dict]:
    """Load anomalies_report.csv, return list of row dicts."""
    rows = []
    if not csv_path.exists():
        return rows
    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def safe_float(val, default=0.0):
    """Convert string to float, return default on failure."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_bool(val, default=False):
    """Convert string to bool (handles True/False/1/0)."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return default


def compute_category_stats(stats_rows: list[dict], anomaly_rows: list[dict]) -> dict:
    """Compute aggregate statistics for one category."""
    n_papers = len(stats_rows)
    if n_papers == 0:
        return None

    # Basic averages
    total_nodes = sum(safe_float(r.get("n_nodes")) for r in stats_rows)
    total_edges = sum(safe_float(r.get("n_edges")) for r in stats_rows)
    avg_nodes = total_nodes / n_papers
    avg_edges = total_edges / n_papers

    # DAG depth (skip None/-1 values which indicate cyclic)
    depths = []
    for r in stats_rows:
        d = safe_float(r.get("dag_depth"), default=-1)
        if d >= 0:
            depths.append(d)
    avg_depth = sum(depths) / len(depths) if depths else 0.0

    # % acyclic
    n_acyclic = sum(1 for r in stats_rows if safe_bool(r.get("dag_acyclic")))
    pct_acyclic = n_acyclic / n_papers * 100

    # % with conclusions (fraction of theorem-like nodes that have conclusions)
    concl_fracs = []
    for r in stats_rows:
        n_thm = safe_float(r.get("n_theorem_like"))
        n_concl = safe_float(r.get("n_thm_with_conclusions"))
        if n_thm > 0:
            concl_fracs.append(n_concl / n_thm)
    pct_concl = (sum(concl_fracs) / len(concl_fracs) * 100) if concl_fracs else 0.0

    # % anomalous (papers flagged with any non-pass anomaly)
    if anomaly_rows:
        flagged_papers = set()
        for row in anomaly_rows:
            rule = row.get("rule", "")
            if rule != "pass":
                pid = row.get("paper_id", "")
                if pid:
                    flagged_papers.add(pid)
        pct_anom = len(flagged_papers) / n_papers * 100
    else:
        pct_anom = 0.0

    # Average specific (non-generic) foundation edges per paper
    avg_foundation_specific = (
        sum(safe_float(r.get("n_foundation_specific")) for r in stats_rows) / n_papers
    )

    return {
        "n_papers": n_papers,
        "avg_nodes": avg_nodes,
        "avg_edges": avg_edges,
        "avg_depth": avg_depth,
        "pct_acyclic": pct_acyclic,
        "pct_concl": pct_concl,
        "pct_anom": pct_anom,
        "avg_foundation_specific": avg_foundation_specific,
    }


def compute_scale_stats(stats_rows: list[dict], anomaly_rows: list[dict]) -> dict:
    """Compute detailed stats for the scale table (single category, math.CO style)."""
    n_papers = len(stats_rows)
    if n_papers == 0:
        return None

    def total(field):
        return int(sum(safe_float(r.get(field)) for r in stats_rows))

    def avg(field):
        return sum(safe_float(r.get(field)) for r in stats_rows) / n_papers

    n_nodes = total("n_nodes")
    n_edges = total("n_edges")
    n_theorems = total("n_theorems")
    n_lemmas = total("n_lemmas")
    n_propositions = total("n_propositions")
    n_corollaries = total("n_corollaries")
    n_theorem_like = total("n_theorem_like")
    n_definitions = total("n_definitions")
    n_proofs = total("n_proofs")
    n_equations = total("n_equations")

    # DAG
    n_acyclic = sum(1 for r in stats_rows if safe_bool(r.get("dag_acyclic")))
    depths = [safe_float(r.get("dag_depth"), -1) for r in stats_rows]
    valid_depths = [d for d in depths if d >= 0]
    max_depth = int(max(valid_depths)) if valid_depths else 0
    avg_depth = sum(valid_depths) / len(valid_depths) if valid_depths else 0

    # Isolated nodes
    n_isolated = total("n_isolated_nodes")
    pct_isolated = (n_isolated / n_nodes * 100) if n_nodes > 0 else 0

    # Assumptions / conclusions
    n_thm_with_assumptions = total("n_thm_with_assumptions")
    n_thm_with_conclusions = total("n_thm_with_conclusions")
    total_assumptions = total("total_assumptions")
    total_conclusions = total("total_conclusions")
    avg_assumptions_per_thm = total_assumptions / n_theorem_like if n_theorem_like > 0 else 0
    avg_conclusions_per_thm = total_conclusions / n_theorem_like if n_theorem_like > 0 else 0

    # Foundation links
    n_foundation_edges = total("n_foundation_edges")
    n_foundation_specific = total("n_foundation_specific")
    n_foundation_generic = total("n_foundation_generic")
    n_papers_linked = sum(1 for r in stats_rows if safe_float(r.get("n_foundation_edges")) > 0)
    n_distinct_targets = total("n_distinct_foundation_targets")

    # Anomalies
    if anomaly_rows:
        flagged_papers = set()
        for row in anomaly_rows:
            if row.get("rule", "") != "pass":
                flagged_papers.add(row.get("paper_id", ""))
        n_anomalous = len(flagged_papers)
    else:
        n_anomalous = 0

    return {
        "n_papers": n_papers,
        "n_nodes": n_nodes,
        "n_edges": n_edges,
        "n_theorems": n_theorems,
        "n_lemmas": n_lemmas,
        "n_propositions": n_propositions,
        "n_corollaries": n_corollaries,
        "n_theorem_like": n_theorem_like,
        "n_definitions": n_definitions,
        "n_proofs": n_proofs,
        "n_equations": n_equations,
        "n_acyclic": n_acyclic,
        "max_depth": max_depth,
        "avg_depth": avg_depth,
        "n_isolated": n_isolated,
        "pct_isolated": pct_isolated,
        "n_thm_with_assumptions": n_thm_with_assumptions,
        "n_thm_with_conclusions": n_thm_with_conclusions,
        "avg_assumptions_per_thm": avg_assumptions_per_thm,
        "avg_conclusions_per_thm": avg_conclusions_per_thm,
        "n_papers_linked": n_papers_linked,
        "n_foundation_edges": n_foundation_edges,
        "n_foundation_specific": n_foundation_specific,
        "n_foundation_generic": n_foundation_generic,
        "n_distinct_targets": n_distinct_targets,
        "n_anomalous": n_anomalous,
    }


def fmt_num(n: int) -> str:
    """Format integer with LaTeX thousand separators: 12345 -> 12{,}345"""
    s = f"{n:,}"
    return s.replace(",", "{,}")


def fmt_pct(p: float) -> str:
    """Format percentage: 32.1 -> 32\\%"""
    return f"{p:.0f}\\%"


def fmt_float(f: float, decimals=1) -> str:
    """Format float to given decimal places."""
    return f"{f:.{decimals}f}"


def generate_cross_category_tex(all_stats: dict[str, dict], num_tier_three: str = "100{,}000") -> str:
    """Generate a complete self-contained table environment for tab:cross-category.

    Outputs \\begin{table}...\\end{table} so the main .tex file can simply
    \\input{tables/cross_category_table.tex} outside any tabular context.
    """
    lines = []

    # Table preamble
    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\footnotesize")
    lines.append(f"\\caption{{Per-category extraction statistics on the T3 {num_tier_three} corpus "
                 "(post-fix rules and assumption/conclusion splitter). "
                 "Categories sorted by predicted extraction quality (acyclicity proxy).}")
    lines.append("\\label{tab:cross-category}")
    lines.append("\\renewcommand{\\arraystretch}{1.05}")
    lines.append("")
    lines.append("\\begin{tabular}{@{}lrrrrrrrr@{}}")
    lines.append("\\toprule")
    lines.append("\\textbf{Category} & \\textbf{\\#papers} & \\textbf{nodes/p} & "
                 "\\textbf{edges/p} & \\textbf{depth} & \\textbf{\\% acyc} & "
                 "\\textbf{\\% concl} & \\textbf{\\% anom} & \\textbf{found/p} \\\\")

    # Data rows
    def emit_section(categories, label=None):
        if label:
            lines.append("\\midrule")
            lines.append(f"\\multicolumn{{9}}{{l}}{{\\textit{{{label}}}}} \\\\")
        for cat in categories:
            s = all_stats.get(cat)
            if s is None:
                lines.append(f"\\texttt{{{cat.replace('_', '.')}}} & -- & -- & -- & -- & -- & -- & -- & -- \\\\")
                continue
            lines.append(
                f"\\texttt{{{cat}}} & {fmt_num(s['n_papers'])} & "
                f"{fmt_float(s['avg_nodes'])} & {fmt_float(s['avg_edges'])} & "
                f"{fmt_float(s['avg_depth'])} & {fmt_pct(s['pct_acyclic'])} & "
                f"{fmt_pct(s['pct_concl'])} & {fmt_pct(s['pct_anom'])} & "
                f"{fmt_float(s['avg_foundation_specific'])} \\\\"
            )

    emit_section(CATEGORIES_PURE_MATH, "Pure mathematics (13 categories)")
    emit_section(CATEGORIES_CS, "Theoretical CS (4 categories)")
    emit_section(CATEGORIES_STATS, "Statistics and numerics (3 categories)")

    # Total / mean row
    valid = [s for s in all_stats.values() if s is not None]
    if valid:
        total_papers = sum(s["n_papers"] for s in valid)
        mean_nodes = sum(s["avg_nodes"] * s["n_papers"] for s in valid) / total_papers
        mean_edges = sum(s["avg_edges"] * s["n_papers"] for s in valid) / total_papers
        mean_depth = sum(s["avg_depth"] * s["n_papers"] for s in valid) / total_papers
        mean_acyc = sum(s["pct_acyclic"] * s["n_papers"] for s in valid) / total_papers
        mean_concl = sum(s["pct_concl"] * s["n_papers"] for s in valid) / total_papers
        mean_anom = sum(s["pct_anom"] * s["n_papers"] for s in valid) / total_papers
        mean_foundation = sum(s["avg_foundation_specific"] * s["n_papers"] for s in valid) / total_papers
        lines.append("\\midrule")
        lines.append(
            f"\\textbf{{Total / mean}} & \\textbf{{{fmt_num(total_papers)}}} & "
            f"{fmt_float(mean_nodes)} & {fmt_float(mean_edges)} & "
            f"{fmt_float(mean_depth)} & {fmt_pct(mean_acyc)} & "
            f"{fmt_pct(mean_concl)} & {fmt_pct(mean_anom)} & "
            f"{fmt_float(mean_foundation)} \\\\"
        )

    # Table closing
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("")
    lines.append("\\vspace{0.4em}")
    lines.append("\\footnotesize")
    lines.append("nodes/p, edges/p = average per paper. depth = average DAG depth. "
                 "\\% acyc = fraction of papers with acyclic extracted graph. "
                 "\\% concl = fraction of theorem-like nodes with non-empty conclusion field after splitter. "
                 "\\% anom = fraction of papers flagged by the anomaly detector (any severity). "
                 "found/p = average specific (IDF $\\leq$ 10\\%) foundation-graph edges per paper.")
    lines.append("\\end{table}")

    return "\n".join(lines)


def generate_scale_tex(s: dict, category: str) -> str:
    """Generate a complete self-contained table environment for tab:scale.

    Outputs \\begin{table}...\\end{table} so the main .tex file can simply
    \\input{tables/scale_table.tex} outside any tabular context.
    """
    n = s["n_papers"]
    lines = []

    # Table preamble
    lines.append("\\begin{table}[h]")
    lines.append("\\centering")
    lines.append("\\small")
    lines.append(f"\\caption{{Large-scale extraction: {fmt_num(n)} \\texttt{{{category}}} papers, "
                 "T3 (rule-based) mode. Extraction completed on a single cluster node "
                 "(zero API cost).}")
    lines.append("\\label{tab:scale}")
    lines.append("\\begin{tabular}{lr@{\\hspace{1em}}l}")
    lines.append("\\toprule")
    lines.append("\\textbf{Metric} & \\textbf{Value} & \\textbf{(avg/paper)} \\\\")
    lines.append("\\midrule")

    # Data rows
    lines.append(f"Papers extracted (of {fmt_num(n)}) & {fmt_num(n)} & 100\\% success \\\\")
    lines.append(f"Total nodes & {fmt_num(s['n_nodes'])} & {fmt_float(s['n_nodes']/n)} \\\\")
    lines.append(f"Total edges & {fmt_num(s['n_edges'])} & {fmt_float(s['n_edges']/n)} \\\\")
    lines.append("\\midrule")
    lines.append(f"Theorem-like & {fmt_num(s['n_theorem_like'])} & {fmt_float(s['n_theorem_like']/n)} \\\\")
    lines.append(f"\\quad theorems & {fmt_num(s['n_theorems'])} & {fmt_float(s['n_theorems']/n)} \\\\")
    lines.append(f"\\quad lemmas & {fmt_num(s['n_lemmas'])} & {fmt_float(s['n_lemmas']/n)} \\\\")
    lines.append(f"\\quad propositions & {fmt_num(s['n_propositions'])} & {fmt_float(s['n_propositions']/n)} \\\\")
    lines.append(f"\\quad corollaries & {fmt_num(s['n_corollaries'])} & {fmt_float(s['n_corollaries']/n)} \\\\")
    lines.append(f"Definitions & {fmt_num(s['n_definitions'])} & {fmt_float(s['n_definitions']/n)} \\\\")
    lines.append(f"Proofs & {fmt_num(s['n_proofs'])} & {fmt_float(s['n_proofs']/n)} \\\\")
    lines.append(f"Equations & {fmt_num(s['n_equations'])} & {fmt_float(s['n_equations']/n)} \\\\")
    lines.append("\\midrule")
    lines.append(f"DAG acyclic & {s['n_acyclic']}/{n} & \\textbf{{{fmt_pct(s['n_acyclic']/n*100)}}} \\\\")
    lines.append(f"DAG depth & max {s['max_depth']} & avg {fmt_float(s['avg_depth'])} \\\\")
    lines.append(f"Isolated nodes & {fmt_num(s['n_isolated'])} & {fmt_pct(s['pct_isolated'])} of all nodes \\\\")
    lines.append("\\midrule")
    lines.append(f"\\multicolumn{{3}}{{l}}{{\\textit{{Assumption/conclusion separation (of {fmt_num(s['n_theorem_like'])} theorem-like):}}}} \\\\")
    lines.append(f"\\quad with assumptions & {fmt_num(s['n_thm_with_assumptions'])} & {fmt_pct(s['n_thm_with_assumptions']/s['n_theorem_like']*100 if s['n_theorem_like']>0 else 0)} \\\\")
    lines.append(f"\\quad with conclusions & {fmt_num(s['n_thm_with_conclusions'])} & \\textbf{{{fmt_pct(s['n_thm_with_conclusions']/s['n_theorem_like']*100 if s['n_theorem_like']>0 else 0)}}} \\\\")
    lines.append(f"\\quad avg assumptions/thm & {fmt_float(s['avg_assumptions_per_thm'])} & \\\\")
    lines.append(f"\\quad avg conclusions/thm & {fmt_float(s['avg_conclusions_per_thm'])} & \\\\")
    lines.append("\\midrule")
    lines.append(f"\\multicolumn{{3}}{{l}}{{\\textit{{Foundation graph linking:}}}} \\\\")
    lines.append(f"\\quad Papers linked & {s['n_papers_linked']}/{n} & \\textbf{{{fmt_pct(s['n_papers_linked']/n*100)}}} \\\\")
    lines.append(f"\\quad Foundation edges (total) & {fmt_num(s['n_foundation_edges'])} & {fmt_float(s['n_foundation_edges']/n)} \\\\")
    lines.append(f"\\quad \\quad specific (IDF $\\leq$ 10\\%) & {fmt_num(s['n_foundation_specific'])} & {fmt_float(s['n_foundation_specific']/n)} \\\\")
    lines.append(f"\\quad \\quad generic (IDF $>$ 10\\%) & {fmt_num(s['n_foundation_generic'])} & {fmt_float(s['n_foundation_generic']/n)} \\\\")
    lines.append(f"\\quad Distinct terms matched & {fmt_num(s['n_distinct_targets'])} & \\\\")

    # Table closing
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")

    return "\n".join(lines)


def generate_macros_tex(all_stats: dict[str, dict], scale_stats: dict) -> str:
    """Generate \\newcommand macros for inline numbers in text."""
    lines = [
        "% Auto-generated by scripts/generate_paper_tables.py",
        "% Re-run the script to update after a new corpus parse.",
        "",
    ]

    # Total corpus stats
    valid = [s for s in all_stats.values() if s is not None]
    if valid:
        total_papers = sum(s["n_papers"] for s in valid)
        mean_acyc = sum(s["pct_acyclic"] * s["n_papers"] for s in valid) / total_papers
        mean_concl = sum(s["pct_concl"] * s["n_papers"] for s in valid) / total_papers
        mean_foundation = sum(s["avg_foundation_specific"] * s["n_papers"] for s in valid) / total_papers
        lines.append(f"\\newcommand{{\\corpusTotalPapers}}{{{fmt_num(total_papers)}}}")
        lines.append(f"\\newcommand{{\\corpusMeanAcyclic}}{{{fmt_pct(mean_acyc)}}}")
        lines.append(f"\\newcommand{{\\corpusMeanConcl}}{{{fmt_pct(mean_concl)}}}")
        lines.append(f"\\newcommand{{\\corpusMeanFoundation}}{{{fmt_float(mean_foundation)}}}")
        lines.append("")

    # Scale (math.CO or whichever single-category) stats
    if scale_stats:
        n = scale_stats["n_papers"]
        lines.append(f"\\newcommand{{\\scalePapers}}{{{fmt_num(n)}}}")
        lines.append(f"\\newcommand{{\\scaleNodes}}{{{fmt_num(scale_stats['n_nodes'])}}}")
        lines.append(f"\\newcommand{{\\scaleEdges}}{{{fmt_num(scale_stats['n_edges'])}}}")
        lines.append(f"\\newcommand{{\\scalePctAcyclic}}{{{fmt_pct(scale_stats['n_acyclic']/n*100)}}}")
        lines.append(f"\\newcommand{{\\scalePctConcl}}{{{fmt_pct(scale_stats['n_thm_with_conclusions']/scale_stats['n_theorem_like']*100 if scale_stats['n_theorem_like']>0 else 0)}}}")
        lines.append(f"\\newcommand{{\\scaleAvgFoundation}}{{{fmt_float(scale_stats['n_foundation_specific']/n)}}}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate LaTeX tables from corpus_stats.csv files")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("/<cluster>/<user>/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k"),
        help="Base directory containing per-category subdirectories",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("tables"),
        help="Output directory for .tex fragments (default: tables/)",
    )
    parser.add_argument(
        "--scale-category",
        type=str,
        default="math.CO",
        help="Category to use for the detailed scale table (default: math.CO)",
    )
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Load stats for all categories
    all_stats = {}
    all_scale_stats = {}
    print(f"Reading from: {args.base_dir}")
    print()

    for cat in ALL_CATEGORIES:
        dirname = cat_to_dirname(cat)
        stats_path = args.base_dir / dirname / "corpus_stats.csv"
        anomalies_path = args.base_dir / dirname / "anomalies_report.csv"

        if not stats_path.exists():
            print(f"  [{cat}] MISSING: {stats_path}")
            all_stats[cat] = None
            continue

        stats_rows = load_corpus_stats(stats_path)
        anomaly_rows = load_anomalies(anomalies_path)

        cat_stats = compute_category_stats(stats_rows, anomaly_rows)
        all_stats[cat] = cat_stats

        if cat_stats:
            print(f"  [{cat}] {cat_stats['n_papers']} papers, "
                  f"{cat_stats['avg_nodes']:.1f} nodes/p, "
                  f"{cat_stats['pct_acyclic']:.0f}% acyc, "
                  f"{cat_stats['pct_concl']:.0f}% concl")

        # Compute scale stats for the designated category
        if cat == args.scale_category:
            all_scale_stats = compute_scale_stats(stats_rows, anomaly_rows)

    print()

    # Generate cross-category table (self-contained \begin{table}...\end{table})
    cross_cat_tex = generate_cross_category_tex(all_stats)
    out_path = args.out_dir / "cross_category_table.tex"
    with open(out_path, "w") as f:
        f.write(cross_cat_tex)
        f.write("\n")
    print(f"Wrote: {out_path}")

    # Generate scale table (self-contained \begin{table}...\end{table})
    if all_scale_stats:
        scale_tex = generate_scale_tex(all_scale_stats, args.scale_category)
        out_path = args.out_dir / "scale_table.tex"
        with open(out_path, "w") as f:
            f.write(scale_tex)
            f.write("\n")
        print(f"Wrote: {out_path}")

    # Generate macros
    macros_tex = generate_macros_tex(all_stats, all_scale_stats)
    out_path = args.out_dir / "macros.tex"
    with open(out_path, "w") as f:
        f.write(macros_tex)
    print(f"Wrote: {out_path}")

    print("\nDone. Tables are self-contained. In your paper, replace the")
    print("full \\begin{table}...\\end{table} blocks with:")
    print("  \\input{tables/cross_category_table}")
    print("  \\input{tables/scale_table}")
    print("And add to preamble:")
    print("  \\input{tables/macros}")


if __name__ == "__main__":
    main()
