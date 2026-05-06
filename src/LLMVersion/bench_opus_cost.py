#!/usr/bin/env python3
"""
Quick benchmark: parse one paper with Claude Opus 4.6, measure time + tokens.
"""
import time
import os
from pathlib import Path
import anthropic

TEX_PATH = Path(os.path.expanduser(
    "~/Datasets/arxiv_data/full_papers/2013/06/17/tex/1210.4634.tex"
))

def main():
    tex = TEX_PATH.read_text(errors="replace")
    print(f"Paper: 1210.4634")
    print(f"TeX length: {len(tex):,} chars")

    client = anthropic.Anthropic()
    # Test both models
    model = os.environ.get("BENCH_MODEL", "claude-sonnet-4-20250514")

    # Build a prompt similar to what the parser uses (definition extraction)
    structure_type = "definition"
    prompt = f"""You are analyzing a mathematical paper written in LaTeX. Extract ALL formal definitions.

Definition forms:
1. \\begin{{definition}} ... \\end{{definition}}
2. **Definition X.Y** (bold headers)
3. Inline: "We define X as..."
4. "Let X denote..."

For each definition, extract:
- id: ...
- name: ...
- latex: ...
- clean_text: ...
- assumptions: ...
- conclusions: ...

Return JSON array:
[
  {{"id": "...", "name": "...", "latex": "...", "clean_text": "...", "assumptions": "...", "conclusions": "..."}}
]

LaTeX text:

{tex}

Respond ONLY with JSON array."""

    print(f"\nPrompt length: {len(prompt):,} chars")
    print(f"Model: {model}")
    print(f"\nCalling Opus 4.6...")

    start = time.time()
    with client.messages.stream(
        model=model,
        max_tokens=16384,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()
    elapsed = time.time() - start

    input_tokens = message.usage.input_tokens
    output_tokens = message.usage.output_tokens

    # Pricing depends on model
    if "opus" in model:
        price_in, price_out = 15, 75
    else:  # sonnet
        price_in, price_out = 3, 15
    cost_input = input_tokens * price_in / 1_000_000
    cost_output = output_tokens * price_out / 1_000_000
    total_cost = cost_input + cost_output

    print(f"\n{'='*50}")
    print(f"RESULTS (single structure type: {structure_type})")
    print(f"{'='*50}")
    print(f"Time:          {elapsed:.1f} seconds")
    print(f"Input tokens:  {input_tokens:,}")
    print(f"Output tokens: {output_tokens:,}")
    print(f"Cost (input):  ${cost_input:.4f}")
    print(f"Cost (output): ${cost_output:.4f}")
    print(f"Cost (total):  ${total_cost:.4f}")

    print(f"\n--- Extrapolation (6 structure types per paper) ---")
    n_types = 6
    print(f"Per paper:  {elapsed * n_types:.0f}s, ${total_cost * n_types:.3f}")
    print(f"1K papers:  {elapsed * n_types * 1000 / 3600:.1f} hours, ${total_cost * n_types * 1000:.0f}")
    print(f"100K papers: {elapsed * n_types * 100000 / 3600:.0f} hours, ${total_cost * n_types * 100000:.0f}")

    print(f"\n--- vs T3 (rule-based) ---")
    t3_pph = 1600
    opus_pph = 3600 / (elapsed * n_types)
    print(f"T3:   {t3_pph} papers/hour, $0")
    print(f"Opus: {opus_pph:.1f} papers/hour, ${total_cost * n_types:.3f}/paper")
    print(f"Speed ratio: T3 is {t3_pph/opus_pph:.0f}x faster")
    print(f"Cost for T3-equivalent throughput: ${total_cost * n_types * t3_pph:.0f}/hour")


if __name__ == "__main__":
    main()
