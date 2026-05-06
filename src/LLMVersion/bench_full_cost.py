#!/usr/bin/env python3
"""
Benchmark: parse 5 gold-standard papers with Opus, Sonnet, and manual (rule-based).
Measures time, token usage, and cost for each.

Usage: ANTHROPIC_API_KEY=... python bench_full_cost.py
"""
import time
import os
import sys
import json
import csv
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import anthropic

# 5 gold-standard papers (varied lengths)
PAPERS = {
    "1204.0109v1": Path(os.path.expanduser(
        "~/Datasets/big_data_project_52017/arxiv_data/full_papers/2012/03/31/tex/1204.0109v1.tex")),
    "1210.4634": Path(os.path.expanduser(
        "~/Datasets/big_data_project_52017/arxiv_data/full_papers/2013/06/17/tex/1210.4634.tex")),
    "1405.2464v2": Path(os.path.expanduser(
        "~/Datasets/big_data_project_52017/arxiv_data/full_papers/2015/03/16/tex/1405.2464v2.tex")),
    "2208.03112v1": Path(os.path.expanduser(
        "~/Datasets/big_data_project_52017/arxiv_data/full_papers/2022/08/05/tex/2208.03112v1.tex")),
    "2309.05826v1": Path(os.path.expanduser(
        "~/Datasets/big_data_project_52017/arxiv_data/full_papers/2023/09/11/tex/2309.05826v1.tex")),
}

# Structure types to extract (the common ones)
STRUCTURE_TYPES = ["definition", "theorem", "lemma", "proof", "proposition", "algorithm"]

# Pricing per million tokens
PRICING = {
    "claude-opus-4-20250514": {"input": 15, "output": 75},
    "claude-sonnet-4-20250514": {"input": 3, "output": 15},
}


def build_prompt(tex: str, structure_type: str) -> str:
    """Build extraction prompt (mirrors parser logic)."""
    return f"""You are analyzing a mathematical paper written in LaTeX. Extract ALL {structure_type}s.

For each {structure_type}, extract:
- id: sequential identifier
- name: the label/name if given
- latex: the raw LaTeX content
- clean_text: cleaned plain text version
- assumptions: any conditions/hypotheses
- conclusions: the main statement/claim

Return a JSON array. If none found, return [].

LaTeX text:

{tex}

Respond ONLY with a valid JSON array."""


def run_llm_extraction(client, model: str, paper_id: str, tex: str):
    """Run full extraction (all structure types) for one paper. Returns stats."""
    total_input = 0
    total_output = 0
    total_time = 0.0
    types_run = 0

    for stype in STRUCTURE_TYPES:
        prompt = build_prompt(tex, stype)

        start = time.time()
        try:
            with client.messages.stream(
                model=model,
                max_tokens=16384,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                message = stream.get_final_message()
            elapsed = time.time() - start

            total_input += message.usage.input_tokens
            total_output += message.usage.output_tokens
            total_time += elapsed
            types_run += 1
            print(f"    {stype}: {elapsed:.1f}s, {message.usage.input_tokens}+{message.usage.output_tokens} tokens")
        except Exception as e:
            elapsed = time.time() - start
            total_time += elapsed
            print(f"    {stype}: FAILED ({e})")

    pricing = PRICING[model]
    cost = (total_input * pricing["input"] + total_output * pricing["output"]) / 1_000_000

    return {
        "paper_id": paper_id,
        "model": model,
        "time_seconds": round(total_time, 1),
        "input_tokens": total_input,
        "output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "cost_usd": round(cost, 4),
        "types_extracted": types_run,
    }


def run_manual_extraction(paper_id: str, tex_path: Path):
    """Run rule-based extraction and measure time."""
    from math_paper_parser import PaperParser

    start = time.time()
    parser = PaperParser(paper_id=paper_id, extraction_mode="manual")
    parser.parse_file(str(tex_path))
    elapsed = time.time() - start

    return {
        "paper_id": paper_id,
        "model": "manual (rule-based)",
        "time_seconds": round(elapsed, 4),
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "types_extracted": len(STRUCTURE_TYPES),
    }


def main():
    client = anthropic.Anthropic()
    results = []

    # First: manual (fast)
    print("=" * 60)
    print("MANUAL (rule-based) extraction")
    print("=" * 60)
    for paper_id, path in PAPERS.items():
        tex = path.read_text(errors="replace")
        print(f"\n  {paper_id} ({len(tex):,} chars)")
        r = run_manual_extraction(paper_id, path)
        print(f"    Time: {r['time_seconds']}s")
        results.append(r)

    # Then: Sonnet
    print("\n" + "=" * 60)
    print("SONNET (claude-sonnet-4-20250514)")
    print("=" * 60)
    for paper_id, path in PAPERS.items():
        tex = path.read_text(errors="replace")
        print(f"\n  {paper_id} ({len(tex):,} chars)")
        r = run_llm_extraction(client, "claude-sonnet-4-20250514", paper_id, tex)
        print(f"    TOTAL: {r['time_seconds']}s, {r['total_tokens']} tokens, ${r['cost_usd']}")
        results.append(r)

    # Then: Opus
    print("\n" + "=" * 60)
    print("OPUS (claude-opus-4-20250514)")
    print("=" * 60)
    for paper_id, path in PAPERS.items():
        tex = path.read_text(errors="replace")
        print(f"\n  {paper_id} ({len(tex):,} chars)")
        r = run_llm_extraction(client, "claude-opus-4-20250514", paper_id, tex)
        print(f"    TOTAL: {r['time_seconds']}s, {r['total_tokens']} tokens, ${r['cost_usd']}")
        results.append(r)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for model_name in ["manual (rule-based)", "claude-sonnet-4-20250514", "claude-opus-4-20250514"]:
        model_results = [r for r in results if r["model"] == model_name]
        avg_time = sum(r["time_seconds"] for r in model_results) / len(model_results)
        total_cost = sum(r["cost_usd"] for r in model_results)
        avg_cost = total_cost / len(model_results)
        total_tokens = sum(r["total_tokens"] for r in model_results)

        print(f"\n  {model_name}:")
        print(f"    Avg time/paper:   {avg_time:.2f}s")
        print(f"    Avg cost/paper:   ${avg_cost:.4f}")
        print(f"    Total tokens:     {total_tokens:,}")
        print(f"    Total cost (5p):  ${total_cost:.4f}")

        # Extrapolations
        if avg_cost > 0:
            print(f"    --- Extrapolation ---")
            print(f"    1K papers:   {avg_time*1000/3600:.1f} hours, ${avg_cost*1000:.0f}")
            print(f"    100K papers: {avg_time*100000/3600:.0f} hours, ${avg_cost*100000:.0f}")

    # Save detailed results
    out_path = Path(__file__).parent / "bench_cost_results.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    print(f"\nDetailed results saved to: {out_path}")


if __name__ == "__main__":
    main()
