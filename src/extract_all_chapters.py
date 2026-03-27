#!/usr/bin/env python3
"""Extract knowledge graphs from all BHK textbook chapters using an LLM.

Usage:
    python extract_all_chapters.py --chapters-dir /path/to/BHK_chapters --out-dir /path/to/output

For each chapter:
  1. Read chapter_body.tex
  2. Send to Claude with the gold-standard Ch2 as a few-shot example
  3. Parse JSON response
  4. Validate (DAG check)
  5. Generate DAG visualization PNG

Requires: ANTHROPIC_API_KEY environment variable set.

Estimated cost: ~$0.20-0.50 per chapter (Claude Sonnet), ~$3-5 total for all 11 chapters.
Estimated time: ~2-4 minutes per chapter, ~30-45 minutes total.
Run locally (no cluster needed).
"""
import json
import sys
import os
import time
import argparse
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("ERROR: pip install anthropic")
    sys.exit(1)

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from visualize_annotation import draw_dag
from validate_annotation import validate


# Chapter metadata
CHAPTERS = {
    2:  "High-Dimensional Space",
    3:  "Best-Fit Subspaces and SVD",
    4:  "Random Walks and Markov Chains",
    5:  "Machine Learning",
    6:  "Streaming and Sketching",
    7:  "Clustering",
    8:  "Random Graphs",
    9:  "Topic Models, NMF, HMMs, and Graphical Models",
    10: "Other Topics",
    11: "Wavelets",
    12: "Appendix",
}

SYSTEM_PROMPT = """You are a mathematical knowledge extraction system. Given a LaTeX chapter from a mathematics textbook, extract a structured knowledge graph as JSON.

Output format: a JSON object with "metadata", "nodes", and "edges" arrays.

Node types: definition, theorem, lemma, corollary, proposition, proof, algorithm
Node fields:
- id: short ID matching the book's numbering (e.g., T4.3, D4.1, L4.5, P4.3, A4.1)
- type: one of the types above
- name: descriptive name or null
- section: section number (e.g., "4.3")
- statement: clean summary (1-3 sentences). Use $...$ for math (matplotlib-compatible: no \\big, \\Pr, \\boldsymbol; use \\mathrm{Pr}, \\mathbf instead)
- assumptions: list of strings (theorems/lemmas/corollaries only)
- conclusions: list of strings (theorems/lemmas/corollaries only)
- proves: ID of theorem it proves (proofs only)
- proof_strategy: 1-3 short technique tags (proofs only)
- input: list of strings (algorithms only)
- output: list of strings (algorithms only)

Edge fields:
- source: ID of supporting object (A supports B means A -> B)
- target: ID of object being supported
- type: "proves" | "uses" | "follows_from"
- note: optional brief explanation

Rules:
- Arrow direction: source SUPPORTS target (foundations -> results)
- "proves": proof -> theorem
- "uses": definition/theorem used by another theorem's proof
- "follows_from": corollary from theorem
- The graph must be a DAG (no cycles)
- Skip exercises
- Keep statements concise but precise
- Use book's theorem numbering (e.g., Theorem 4.3 -> T4.3)"""


def build_prompt(chapter_num, chapter_title, latex_text, gold_example_json=None):
    """Build the extraction prompt with optional few-shot example."""
    prompt = f"Extract a knowledge graph from Chapter {chapter_num}: \"{chapter_title}\".\n\n"

    if gold_example_json:
        prompt += "Here is a complete example of the expected output for Chapter 2:\n\n"
        prompt += f"```json\n{gold_example_json}\n```\n\n"
        prompt += "Now extract the same structure for the following chapter.\n\n"

    prompt += f"LaTeX source:\n\n```latex\n{latex_text}\n```\n\n"
    prompt += "Return ONLY valid JSON, no other text."
    return prompt


def call_llm(client, prompt, model="claude-sonnet-4-20250514", max_retries=2):
    """Call Claude API with retry logic."""
    for attempt in range(max_retries + 1):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=16384,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text, message.usage
        except Exception as e:
            if attempt < max_retries:
                print(f"  [WARN] API error (attempt {attempt+1}): {e}. Retrying in 10s...")
                time.sleep(10)
            else:
                raise


def parse_json_response(text):
    """Extract JSON from LLM response (may be wrapped in ```json ... ```)."""
    text = text.strip()
    if text.startswith("```"):
        # Remove markdown code fences
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)


def process_chapter(client, chapter_num, chapters_dir, out_dir, gold_json_str=None,
                    model="claude-sonnet-4-20250514", skip_existing=True):
    """Process a single chapter: extract JSON + generate PNG."""
    title = CHAPTERS.get(chapter_num, f"Chapter {chapter_num}")
    body_file = chapters_dir / f"chapter{chapter_num}_body.tex"
    json_out = out_dir / f"chapter{chapter_num}_extracted.json"
    png_out = out_dir / f"chapter{chapter_num}_graph.png"

    if skip_existing and json_out.exists():
        print(f"  [SKIP] {json_out.name} already exists. Use --force to re-extract.")
        # Still generate PNG if missing
        if not png_out.exists():
            with open(json_out) as f:
                data = json.load(f)
            draw_dag(data["nodes"], data["edges"], png_out, metadata=data.get("metadata"))
            print(f"  [PNG] {png_out.name}")
        return True

    if not body_file.exists():
        print(f"  [ERROR] {body_file} not found. Skipping.")
        return False

    latex_text = body_file.read_text(encoding="utf-8")
    print(f"  Reading {body_file.name} ({len(latex_text)} chars, {len(latex_text.split(chr(10)))} lines)")

    # For very long chapters (>50K chars), truncate exercises section
    exercise_markers = ["\\subsection*{Exercises}", "\\section*{Exercise"]
    for marker in exercise_markers:
        idx = latex_text.find(marker)
        if idx > 0:
            latex_text = latex_text[:idx]
            print(f"  Truncated exercises at char {idx}")
            break

    prompt = build_prompt(chapter_num, title, latex_text, gold_json_str)
    print(f"  Prompt: {len(prompt)} chars. Calling {model}...")

    response_text, usage = call_llm(client, prompt, model=model)
    print(f"  Response: {len(response_text)} chars. Tokens: {usage.input_tokens} in, {usage.output_tokens} out")

    # Parse JSON
    try:
        data = parse_json_response(response_text)
    except json.JSONDecodeError as e:
        print(f"  [ERROR] Failed to parse JSON: {e}")
        # Save raw response for debugging
        raw_out = out_dir / f"chapter{chapter_num}_raw_response.txt"
        raw_out.write_text(response_text, encoding="utf-8")
        print(f"  Raw response saved to {raw_out.name}")
        return False

    # Ensure metadata
    if "metadata" not in data:
        data["metadata"] = {}
    data["metadata"]["chapter"] = chapter_num
    data["metadata"]["chapter_title"] = title
    data["metadata"]["source"] = "Foundations of Data Science, BHK (2020)"
    data["metadata"]["annotator"] = f"LLM ({model})"

    # Save JSON
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  [JSON] {json_out.name} ({len(data.get('nodes', []))} nodes, {len(data.get('edges', []))} edges)")

    # Validate
    messages = validate(data)
    errors = [m for m in messages if m.startswith("ERROR")]
    if errors:
        print(f"  [WARN] Validation errors:")
        for e in errors:
            print(f"    {e}")
    else:
        info = [m for m in messages if m.startswith("INFO")]
        for i in info:
            print(f"    {i}")

    # Generate PNG
    try:
        draw_dag(data["nodes"], data["edges"], png_out, metadata=data.get("metadata"))
        print(f"  [PNG] {png_out.name}")
    except Exception as e:
        print(f"  [WARN] PNG generation failed: {e}")

    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--chapters-dir", required=True,
                        help="Directory containing chapterN_body.tex files")
    parser.add_argument("--out-dir", required=True,
                        help="Output directory for JSON + PNG files")
    parser.add_argument("--gold-json", default=None,
                        help="Path to gold standard JSON (Ch2) for few-shot prompting")
    parser.add_argument("--model", default="claude-sonnet-4-20250514",
                        help="Anthropic model ID (default: claude-sonnet-4-20250514)")
    parser.add_argument("--chapters", default=None,
                        help="Comma-separated chapter numbers (default: all). E.g., '3,4,5'")
    parser.add_argument("--force", action="store_true",
                        help="Re-extract even if JSON already exists")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without calling the API")
    args = parser.parse_args()

    chapters_dir = Path(args.chapters_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load gold standard for few-shot
    gold_json_str = None
    if args.gold_json:
        gold_path = Path(args.gold_json)
        if gold_path.exists():
            gold_json_str = gold_path.read_text(encoding="utf-8")
            # Truncate if very long (keep it under 5K chars for prompt budget)
            if len(gold_json_str) > 5000:
                gold_data = json.loads(gold_json_str)
                # Keep only first 5 nodes as example
                gold_data["nodes"] = gold_data["nodes"][:5]
                gold_data["edges"] = [e for e in gold_data["edges"]
                                      if e["source"] in {n["id"] for n in gold_data["nodes"]}
                                      and e["target"] in {n["id"] for n in gold_data["nodes"]}]
                gold_json_str = json.dumps(gold_data, indent=2)
            print(f"[INFO] Gold standard loaded ({len(gold_json_str)} chars)")

    # Determine which chapters to process
    if args.chapters:
        chapter_nums = [int(x.strip()) for x in args.chapters.split(",")]
    else:
        chapter_nums = sorted(CHAPTERS.keys())

    # Skip chapter 2 if we have its gold standard
    if args.gold_json and 2 in chapter_nums:
        chapter_nums.remove(2)
        print("[INFO] Skipping Ch2 (using as gold standard)")

    print(f"\n[INFO] Processing {len(chapter_nums)} chapters: {chapter_nums}")
    print(f"[INFO] Output: {out_dir}")
    print(f"[INFO] Model: {args.model}")

    if args.dry_run:
        for ch in chapter_nums:
            body = chapters_dir / f"chapter{ch}_body.tex"
            exists = body.exists()
            size = body.stat().st_size if exists else 0
            print(f"  Ch {ch:2d}: {CHAPTERS.get(ch, '?'):<45s} {'OK' if exists else 'MISSING':>7s} ({size:>6d} bytes)")
        print(f"\nEstimated cost: ~${len(chapter_nums) * 0.35:.2f}")
        print(f"Estimated time: ~{len(chapter_nums) * 3} minutes")
        return

    # Initialize API client
    client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var

    total_ok = 0
    total_fail = 0
    t0 = time.time()

    for i, ch in enumerate(chapter_nums, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(chapter_nums)}] Chapter {ch}: {CHAPTERS.get(ch, '?')}")
        print(f"{'='*60}")

        ok = process_chapter(
            client, ch, chapters_dir, out_dir,
            gold_json_str=gold_json_str,
            model=args.model,
            skip_existing=not args.force,
        )
        if ok:
            total_ok += 1
        else:
            total_fail += 1

        # Rate limiting: wait 2s between chapters
        if i < len(chapter_nums):
            time.sleep(2)

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"DONE. {total_ok} succeeded, {total_fail} failed. Time: {elapsed/60:.1f} min")
    print(f"Output: {out_dir}")


if __name__ == "__main__":
    main()
