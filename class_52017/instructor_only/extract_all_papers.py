#!/usr/bin/env python3
"""Extract knowledge graphs from all research papers using Claude API.

Usage:
    python extract_all_papers.py --papers-dir ../cluster_package/papers --out-dir ../cluster_package/papers/gold
    python extract_all_papers.py --papers-dir ../cluster_package/papers --out-dir ../cluster_package/papers/gold --papers 1,2,3
    python extract_all_papers.py --papers-dir ../cluster_package/papers --out-dir ../cluster_package/papers/gold --force

For each paper:
  1. Read paperN.tex
  2. Send to Claude with gold-standard Ch2 as a few-shot example
  3. Parse JSON response
  4. Validate (DAG check)
  5. Generate DAG visualization PNG

Requires: ANTHROPIC_API_KEY environment variable set.
          pip install anthropic matplotlib networkx

Estimated cost: ~$0.20-0.80 per paper (Claude Sonnet), ~$5-10 total for 18 papers.
Estimated time: ~2-5 minutes per paper, ~45-90 minutes total.
Run locally (no cluster needed).
"""
import json
import sys
import time
import argparse
from pathlib import Path

anthropic = None  # lazy import — only needed when actually calling the API

# Try to import visualization from Authomathics if available, else inline fallback
VISUALIZE_AVAILABLE = False
VALIDATE_AVAILABLE = False

# Try multiple locations for visualization code
_possible_src = [
    Path(__file__).parent / ".." / ".." / ".." / "Code" / "Github" / "Authomathics" / "src",
    Path("/mnt/c/Code/Github/Authomathics/src"),
]
for src_path in _possible_src:
    if src_path.exists():
        sys.path.insert(0, str(src_path.resolve()))
        break

try:
    from visualize_annotation import draw_dag
    VISUALIZE_AVAILABLE = True
except ImportError:
    pass

try:
    from validate_annotation import validate
    VALIDATE_AVAILABLE = True
except ImportError:
    pass


# Paper metadata (from papers_metadata.csv)
PAPERS = {
    1:  "A Tutorial on Spectral Clustering (von Luxburg)",
    2:  "Compressed Sensing (Donoho)",
    3:  "Exact Recovery in the Stochastic Block Model (Abbe et al.)",
    4:  "Database-Friendly Random Projections (Achlioptas)",
    5:  "Sinkhorn Distances (Cuturi)",
    6:  "Communication-Efficient Distributed Optimization (Zhang et al.)",
    7:  "Pegasos: Sub-Gradient SVM (Shalev-Shwartz et al.)",
    8:  "Making Gradient Descent Optimal (Rakhlin et al.)",
    9:  "Non-Asymptotic Random Matrices (Vershynin)",
    10: "Reconciling Bias-Variance Trade-off (Belkin et al.)",
    11: "Beyond Locality-Sensitive Hashing (Andoni et al.)",
    12: "Denoising Diffusion Probabilistic Models (Ho et al.)",
    13: "Flow Matching for Generative Modeling (Lipman et al.)",
    14: "Auto-Encoding Variational Bayes (Kingma & Welling)",
    15: "Generative Adversarial Networks (Goodfellow et al.)",
    16: "Are Transformers Universal Approximators? (Yun et al.)",
    17: "Regret Analysis of Multi-Armed Bandits (Bubeck & Cesa-Bianchi)",
    18: "Conformal Prediction (Angelopoulos & Bates)",
}


SYSTEM_PROMPT = """\
You are a mathematical knowledge extraction system. Given a LaTeX research paper, \
extract a structured knowledge graph as JSON.

Output format: a JSON object with "metadata", "nodes", and "edges" arrays.

Node types: definition, theorem, lemma, corollary, proposition, proof, algorithm
Node fields:
- id: short ID using the pattern <type-letter>P<paper_num>.<seq>, e.g. DP1.1, TP1.2, LP1.1, CP1.1, PP1.2, AP1.1
  Type letters: D=definition, T=theorem, L=lemma, C=corollary, P=proof, A=algorithm
- type: one of the types above
- name: descriptive name (e.g. "Johnson-Lindenstrauss lemma") or null if unnamed
- section: section number (e.g. "3.2") or null if unclear
- statement: concise 1-3 sentence summary using MATH NOTATION. \
Use symbols like Prob(...), E(x), Var(x), |x|, <=, >=, R^d, exp(...), O(...). \
Keep it short and precise, similar to how you'd write on a cheat sheet.
- assumptions: list of strings (theorems/lemmas/corollaries only)
- conclusions: list of strings (theorems/lemmas/corollaries only)
- proves: ID of theorem it proves (proofs only, e.g. "TP1.2")
- proof_strategy: 1-3 short technique tags (proofs only, e.g. "induction", "union bound")
- input: list of strings (algorithms only)
- output: list of strings (algorithms only)

Edge fields:
- source: ID of supporting object (A supports B means A -> B)
- target: ID of object being supported
- type: "proves" | "uses" | "follows_from"

Rules:
- Arrow direction: source SUPPORTS target (foundations -> results)
- "proves": proof -> theorem
- "uses": definition/theorem used by another theorem's proof
- "follows_from": corollary from theorem
- The graph must be a DAG (no cycles)
- Skip exercises, examples, and remarks (only extract formal math objects)
- Keep statements concise but precise
- Use the paper's own numbering when available (e.g., Theorem 3.1 -> TP<N>.3 where N is the paper number)"""


# Example gold standard (from BHK Chapter 2) — truncated for prompt budget
GOLD_EXAMPLE = """{
  "metadata": {"title": "Ch. 2: High-Dimensional Space"},
  "nodes": [
    {"id": "D2.1", "type": "definition", "name": "Unit ball", "section": "2.3",
     "statement": "The unit ball S in d dimensions is the set of all points x in R^d with |x| <= 1."},
    {"id": "T2.1", "type": "theorem", "name": "Markov's inequality", "section": "2.2",
     "statement": "For a nonneg. random variable x and a > 0: Prob(x >= a) <= E(x)/a.",
     "assumptions": ["x is a nonnegative random variable", "a > 0"],
     "conclusions": ["Prob(x >= a) <= E(x) / a"]},
    {"id": "P2.1", "type": "proof", "name": null, "section": "2.2", "proves": "T2.1",
     "statement": "Split E(x) = integral from 0 to a + integral from a to infinity. Second part >= a * Prob(x >= a).",
     "proof_strategy": "direct computation, splitting integral at a"},
    {"id": "C2.2", "type": "corollary", "name": null, "section": "2.2",
     "statement": "Prob(x >= b*E(x)) <= 1/b for nonneg. x and b > 0.",
     "assumptions": ["x is a nonnegative random variable", "b > 0"],
     "conclusions": ["Prob(x >= b * E(x)) <= 1/b"]},
    {"id": "L2.12", "type": "lemma", "name": "Centroid minimizes sum of squared distances", "section": "2.8",
     "statement": "Sum of squared distances from n points to center mu is minimized when mu = (1/n)*sum(x_i)."}
  ],
  "edges": [
    {"source": "P2.1", "target": "T2.1", "type": "proves"},
    {"source": "T2.1", "target": "C2.2", "type": "follows_from"}
  ]
}"""


def build_prompt(paper_num, paper_title, latex_text):
    """Build the extraction prompt with few-shot example."""
    prompt = f"Extract a knowledge graph from Paper {paper_num}: \"{paper_title}\".\n\n"
    prompt += "Here is an example of the expected output format (from a textbook chapter):\n\n"
    prompt += f"```json\n{GOLD_EXAMPLE}\n```\n\n"
    prompt += f"For this paper, use IDs like DP{paper_num}.1, TP{paper_num}.1, LP{paper_num}.1, etc.\n\n"
    prompt += "Now extract the same structure for the following paper.\n\n"
    prompt += f"LaTeX source:\n\n```latex\n{latex_text}\n```\n\n"
    prompt += "Return ONLY valid JSON, no other text."
    return prompt


def call_api(client, prompt, model="claude-sonnet-4-20250514", max_retries=2):
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
    # Remove markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find outermost JSON object
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    pass
                start = None

    raise json.JSONDecodeError("No valid JSON object found", text, 0)


def truncate_for_context(latex_text, max_chars=150_000):
    """Truncate very long papers to fit context window, removing appendix/bibliography."""
    # Remove bibliography
    for marker in [r"\begin{thebibliography}", r"\bibliography{", r"\printbibliography"]:
        idx = latex_text.find(marker)
        if idx > 0:
            latex_text = latex_text[:idx]
            break

    # Remove appendix if still too long
    if len(latex_text) > max_chars:
        for marker in [r"\appendix", r"\section*{Appendix", r"\section{Appendix"]:
            idx = latex_text.find(marker)
            if idx > 0 and idx < len(latex_text) * 0.8:  # only if appendix is in last 20%
                latex_text = latex_text[:idx]
                break

    # Hard truncate if still too long
    if len(latex_text) > max_chars:
        latex_text = latex_text[:max_chars] + "\n\n[... truncated for context limits ...]"

    return latex_text


def process_paper(client, paper_num, papers_dir, out_dir, model="claude-sonnet-4-20250514",
                  skip_existing=True):
    """Process a single paper: extract JSON + generate PNG."""
    title = PAPERS.get(paper_num, f"Paper {paper_num}")
    tex_file = papers_dir / f"paper{paper_num}.tex"
    json_out = out_dir / f"paper{paper_num}_gold.json"
    png_out = out_dir / f"paper{paper_num}_graph.png"

    if skip_existing and json_out.exists():
        print(f"  [SKIP] {json_out.name} already exists. Use --force to re-extract.")
        # Still generate PNG if missing
        if not png_out.exists() and VISUALIZE_AVAILABLE:
            try:
                with open(json_out) as f:
                    data = json.load(f)
                draw_dag(data["nodes"], data["edges"], png_out, metadata=data.get("metadata"))
                print(f"  [PNG] {png_out.name}")
            except Exception as e:
                print(f"  [WARN] PNG failed: {e}")
        return True

    if not tex_file.exists():
        print(f"  [ERROR] {tex_file} not found. Skipping.")
        return False

    latex_text = tex_file.read_text(encoding="utf-8", errors="replace")
    orig_len = len(latex_text)
    print(f"  Reading {tex_file.name} ({orig_len:,} chars)")

    # Truncate for context limits
    latex_text = truncate_for_context(latex_text)
    if len(latex_text) < orig_len:
        print(f"  Truncated: {orig_len:,} -> {len(latex_text):,} chars")

    prompt = build_prompt(paper_num, title, latex_text)
    print(f"  Prompt: {len(prompt):,} chars. Calling {model}...")

    response_text, usage = call_api(client, prompt, model=model)
    print(f"  Response: {len(response_text):,} chars. "
          f"Tokens: {usage.input_tokens:,} in, {usage.output_tokens:,} out")

    # Parse JSON
    try:
        data = parse_json_response(response_text)
    except json.JSONDecodeError as e:
        print(f"  [ERROR] Failed to parse JSON: {e}")
        raw_out = out_dir / f"paper{paper_num}_raw_response.txt"
        raw_out.write_text(response_text, encoding="utf-8")
        print(f"  Raw response saved to {raw_out.name}")
        return False

    # Ensure metadata
    if "metadata" not in data:
        data["metadata"] = {}
    data["metadata"]["paper_num"] = paper_num
    data["metadata"]["title"] = title
    data["metadata"]["annotator"] = f"LLM ({model})"

    # Post-processing: filter invalid types, remove cycles
    VALID_TYPES = {"definition", "theorem", "lemma", "corollary", "proposition", "proof", "algorithm"}
    nodes = data.get("nodes", [])
    before = len(nodes)
    nodes = [n for n in nodes if n.get("type") in VALID_TYPES]
    if len(nodes) < before:
        print(f"  Filtered {before - len(nodes)} nodes with invalid types")

    # Remove empty statements
    nodes = [n for n in nodes if n.get("statement", "").strip()]

    # Dedup nodes by ID
    seen_ids = set()
    unique_nodes = []
    for n in nodes:
        nid = n.get("id", "")
        if nid and nid not in seen_ids:
            seen_ids.add(nid)
            unique_nodes.append(n)
    data["nodes"] = unique_nodes

    # Validate edges reference existing nodes
    node_ids = {n["id"] for n in data["nodes"]}
    data["edges"] = [e for e in data.get("edges", [])
                     if e.get("source") in node_ids and e.get("target") in node_ids]

    # Dedup edges
    seen_edges = set()
    unique_edges = []
    for e in data["edges"]:
        key = (e.get("source"), e.get("target"))
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)
    data["edges"] = unique_edges

    # Save JSON
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  [JSON] {json_out.name} ({len(data['nodes'])} nodes, {len(data['edges'])} edges)")

    # Validate
    if VALIDATE_AVAILABLE:
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
    if VISUALIZE_AVAILABLE:
        try:
            draw_dag(data["nodes"], data["edges"], png_out, metadata=data.get("metadata"))
            print(f"  [PNG] {png_out.name}")
        except Exception as e:
            print(f"  [WARN] PNG generation failed: {e}")

    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--papers-dir", required=True,
                        help="Directory containing paperN.tex files")
    parser.add_argument("--out-dir", required=True,
                        help="Output directory for gold JSON + PNG files")
    parser.add_argument("--model", default="claude-sonnet-4-20250514",
                        help="Anthropic model ID (default: claude-sonnet-4-20250514)")
    parser.add_argument("--papers", default=None,
                        help="Comma-separated paper numbers (default: all 1-18). E.g., '1,2,3'")
    parser.add_argument("--force", action="store_true",
                        help="Re-extract even if JSON already exists")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without calling the API")
    args = parser.parse_args()

    papers_dir = Path(args.papers_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Determine which papers to process
    if args.papers:
        paper_nums = [int(x.strip()) for x in args.papers.split(",")]
    else:
        paper_nums = sorted(PAPERS.keys())

    print(f"[INFO] Processing {len(paper_nums)} papers: {paper_nums}")
    print(f"[INFO] Output: {out_dir}")
    print(f"[INFO] Model: {args.model}")
    if not VISUALIZE_AVAILABLE:
        print("[WARN] visualize_annotation not found — PNG generation disabled")
    if not VALIDATE_AVAILABLE:
        print("[WARN] validate_annotation not found — validation disabled")

    if args.dry_run:
        for p in paper_nums:
            tex = papers_dir / f"paper{p}.tex"
            exists = tex.exists()
            size = tex.stat().st_size if exists else 0
            print(f"  Paper {p:2d}: {PAPERS.get(p, '?'):<55s} "
                  f"{'OK' if exists else 'MISSING':>7s} ({size:>7,d} bytes)")
        est_cost = len(paper_nums) * 0.50
        print(f"\nEstimated cost: ~${est_cost:.2f}")
        print(f"Estimated time: ~{len(paper_nums) * 4} minutes")
        return

    # Initialize API client
    global anthropic
    try:
        import anthropic as _anthropic
        anthropic = _anthropic
    except ImportError:
        print("ERROR: pip install anthropic")
        sys.exit(1)
    client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var

    total_ok = 0
    total_fail = 0
    t0 = time.time()

    for i, p in enumerate(paper_nums, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(paper_nums)}] Paper {p}: {PAPERS.get(p, '?')}")
        print(f"{'='*60}")

        ok = process_paper(
            client, p, papers_dir, out_dir,
            model=args.model,
            skip_existing=not args.force,
        )
        if ok:
            total_ok += 1
        else:
            total_fail += 1

        # Rate limiting
        if i < len(paper_nums):
            time.sleep(2)

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"DONE. {total_ok} succeeded, {total_fail} failed. Time: {elapsed/60:.1f} min")
    print(f"Output: {out_dir}")


if __name__ == "__main__":
    main()
