#!/usr/bin/env python3
"""
SOLUTION extractor for the Big Data Project (52017).
NOT for distribution to students.

Improvements over baseline:
  1. Section-by-section chunking (handles context limits, improves focus)
  2. Few-shot examples from gold standard (improves output style + Jaccard match)
  3. Concise math-notation style instructions
  4. JSON retry on parse failure (with simplified fallback prompt)
  5. Post-processing: dedup nodes, validate edges, remove cycles

Usage:
    python annotate_chapter_solution.py chapters/chapter4.tex -o chapter4_output.json
    python annotate_chapter_solution.py chapters/chapter4.tex -o out.json --model Qwen/Qwen2.5-7B-Instruct
"""

import argparse
import json
import re
import sys
import os
import time

# Import from cluster_package/scripts/
_scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "cluster_package", "scripts")
sys.path.insert(0, _scripts_dir)
from call_llm import call_llm, APPROVED_MODELS, DEFAULT_MODEL


SYSTEM_PROMPT = """\
You are a precise mathematical knowledge extraction system. You read LaTeX source \
and output ONLY valid JSON. Never include commentary, reasoning, or thinking \
outside the JSON object. Do not use <think> tags."""


EXTRACTION_PROMPT = """\
Extract all mathematical objects and their dependencies from the following LaTeX \
as a JSON knowledge graph.

## Node format
Each node represents one mathematical object. Fields:
- "id": short ID using the pattern <type-letter><chapter>.<seq>, e.g. D3.1, T3.2, L3.1, C3.1, P3.2, A3.1
  Type letters: D=definition, T=theorem, L=lemma, C=corollary, P=proof, A=algorithm
- "type": one of "definition", "theorem", "lemma", "corollary", "proof", "algorithm"
- "name": descriptive name (e.g. "Markov's inequality") or null if unnamed
- "section": section number (e.g. "3.2")
- "statement": concise 1-2 sentence summary using MATH NOTATION (not verbose English).
  Use symbols like Prob(...), E(x), Var(x), |x|, <=, >=, R^d, exp(...), O(...).
  Keep it short and precise, similar to how you'd write on a cheat sheet.

Additional fields by type:
- theorem/lemma/corollary: "assumptions" (list of strings), "conclusions" (list of strings).
  Carefully separate what is assumed from what is concluded.
- proof: "proves" (ID of the theorem/lemma proved, e.g. "T3.2"),
         "proof_strategy" (1-3 short tags, e.g. "induction", "contradiction", "union bound")

## Edge format
Each edge is a dependency. An edge from A to B means "A supports B" (B uses/needs A).
- "source": ID of the supporting object
- "target": ID of the object that depends on it

Direction examples:
- D3.1 -> T3.2: theorem uses definition in its statement
- T3.1 -> T3.5: theorem 3.5 builds on theorem 3.1
- P3.2 -> T3.2: proof establishes theorem
- D3.1 -> P3.2: proof uses definition

Only include direct dependencies (not transitive). The graph must be a DAG (no cycles).

## EXAMPLES (from Chapter 2 gold standard)

Here are example nodes showing the expected style and level of detail:

{"id": "D2.1", "type": "definition", "name": "Unit ball", "section": "2.3", \
"statement": "The unit ball S in d dimensions is the set of all points x in R^d with |x| <= 1."}

{"id": "T2.1", "type": "theorem", "name": "Markov's inequality", "section": "2.2", \
"statement": "For a nonneg. random variable x and a > 0: Prob(x >= a) <= E(x)/a.", \
"assumptions": ["x is a nonnegative random variable", "a > 0"], \
"conclusions": ["Prob(x >= a) <= E(x) / a"]}

{"id": "P2.1", "type": "proof", "name": null, "section": "2.2", "proves": "T2.1", \
"statement": "Split E(x) = integral from 0 to a + integral from a to infinity. The second part is >= a * Prob(x >= a).", \
"proof_strategy": "direct computation, splitting integral at a"}

{"id": "C2.2", "type": "corollary", "name": null, "section": "2.2", \
"statement": "Prob(x >= b*E(x)) <= 1/b for nonneg. x and b > 0.", \
"assumptions": ["x is a nonnegative random variable", "b > 0"], \
"conclusions": ["Prob(x >= b * E(x)) <= 1/b"]}

{"id": "L2.12", "type": "lemma", "name": "Centroid minimizes sum of squared distances", "section": "2.8", \
"statement": "The sum of squared distances from n points to a center mu is minimized when mu is the centroid (1/n)*sum(x_i)."}

Example edges: {"source": "P2.1", "target": "T2.1"}, {"source": "T2.1", "target": "C2.2"}

## Output
Return ONLY a JSON object (no commentary before or after):
{
  "metadata": {"title": "...", "sections": "..."},
  "nodes": [...],
  "edges": [...]
}

## LaTeX source (SECTION_LABEL):

"""

RETRY_PROMPT = """\
The previous response was not valid JSON. Please try again.
Extract mathematical objects from this LaTeX as a JSON knowledge graph.
Return ONLY a valid JSON object with "metadata", "nodes", and "edges" fields.
Use concise math notation in statements (e.g. "Prob(x >= a) <= E(x)/a").
No commentary, no thinking, just the JSON.

LaTeX source (SECTION_LABEL):

"""


def read_latex(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_json_from_response(response):
    """Extract JSON object from LLM response, handling markdown blocks and thinking tags."""
    if not response:
        return None
    # Strip <think>...</think> tags (Qwen3 reasoning), including unclosed tags
    response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
    response = re.sub(r'<think>.*', '', response, flags=re.DOTALL).strip()

    # Try markdown code block first
    match = re.search(r'```(?:json)?\s*\n?(.*?)```', response, re.DOTALL)
    if match:
        text = match.group(1).strip()
    else:
        text = response

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

    # Fallback: regex
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def split_into_sections(latex):
    """Split LaTeX into sections based on \\section or \\subsection headers."""
    # Find top-level section boundaries (section* or subsection* with X.Y numbering)
    pattern = r'(\\(?:sub)?section\*?\{(\d+\.\d+(?:\.\d+)?)\s+[^}]+\})'
    splits = list(re.finditer(pattern, latex))

    if len(splits) < 2:
        # Can't split meaningfully, return as single chunk
        return [("full", latex)]

    chunks = []
    for i, m in enumerate(splits):
        sec_num = m.group(2)
        start = m.start()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(latex)
        chunk_text = latex[start:end].strip()
        if len(chunk_text) > 200:  # skip tiny chunks
            # Skip exercise/bibliography sections (no math objects to extract)
            header_lower = m.group(1).lower()
            if "exercise" in header_lower or "bibliograph" in header_lower:
                continue
            chunks.append((sec_num, chunk_text))

    return chunks if chunks else [("full", latex)]


def merge_results(chunk_results):
    """Merge extraction results from multiple section chunks."""
    all_nodes = []
    all_edges = []
    seen_ids = set()

    for result in chunk_results:
        if not result:
            continue
        for node in result.get("nodes", []):
            nid = node.get("id", "")
            if nid and nid not in seen_ids:
                seen_ids.add(nid)
                all_nodes.append(node)
        for edge in result.get("edges", []):
            all_edges.append(edge)

    return all_nodes, all_edges


def remove_cycles(nodes, edges):
    """Remove edges that create cycles (keep the DAG property)."""
    node_ids = {n["id"] for n in nodes}
    # Filter edges to only reference existing nodes
    valid_edges = [e for e in edges
                   if e.get("source") in node_ids and e.get("target") in node_ids]

    # Kahn's algorithm: remove edges that create cycles
    from collections import defaultdict, deque
    adj = defaultdict(list)
    in_degree = defaultdict(int)
    for nid in node_ids:
        in_degree[nid] = 0
    for e in valid_edges:
        adj[e["source"]].append(e["target"])
        in_degree[e["target"]] += 1

    queue = deque([n for n in node_ids if in_degree[n] == 0])
    topo_order = []
    while queue:
        u = queue.popleft()
        topo_order.append(u)
        for v in adj[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    if len(topo_order) == len(node_ids):
        return valid_edges  # Already a DAG

    # There are cycles. Keep only edges consistent with partial topo order.
    order_map = {nid: i for i, nid in enumerate(topo_order)}
    dag_edges = []
    for e in valid_edges:
        s, t = e["source"], e["target"]
        if s in order_map and t in order_map and order_map[s] < order_map[t]:
            dag_edges.append(e)

    removed = len(valid_edges) - len(dag_edges)
    if removed:
        print(f"  Removed {removed} edges to ensure DAG property.")
    return dag_edges


def dedup_edges(edges):
    """Remove duplicate edges."""
    seen = set()
    unique = []
    for e in edges:
        key = (e.get("source"), e.get("target"))
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def call_llm_with_retry(text, label, model=DEFAULT_MODEL, max_retries=2):
    """Call LLM and retry with simpler prompt if JSON parsing fails."""
    for attempt in range(max_retries):
        if attempt == 0:
            prompt = EXTRACTION_PROMPT.replace("SECTION_LABEL", label) + text
        else:
            # Retry with shorter, simpler prompt (saves tokens, more likely to produce JSON)
            print(f"    Retry {attempt}/{max_retries-1} with simplified prompt...")
            prompt = RETRY_PROMPT.replace("SECTION_LABEL", label) + text

        try:
            response = call_llm(prompt, model=model, system_prompt=SYSTEM_PROMPT,
                               max_tokens=8192, temperature=0.0)
            result = extract_json_from_response(response)
            if result and result.get("nodes"):
                return result
            if attempt == 0:
                print(f"    -> Failed to parse JSON (attempt {attempt+1})")
        except Exception as ex:
            print(f"    -> API error: {ex}")
            if attempt < max_retries - 1:
                time.sleep(2)  # brief pause before retry

    return None


def annotate_chapter(latex_path, model=DEFAULT_MODEL):
    """Extract knowledge graph using section-by-section chunking."""
    latex = read_latex(latex_path)

    # Detect chapter number from content
    ch_match = re.search(r'\\section\*?\{(\d+)', latex)
    ch_num = ch_match.group(1) if ch_match else "?"

    # Detect title
    title_match = re.search(r'\\section\*?\{\d+\s+(.+?)\}', latex)
    title = title_match.group(1).strip() if title_match else "Unknown"

    # Split into sections
    chunks = split_into_sections(latex)
    print(f"  Split into {len(chunks)} section chunks")

    # If only 1 chunk or small enough, send as one call
    total_chars = sum(len(c) for _, c in chunks)
    MAX_SINGLE_CALL = 20_000  # chars (~6K tokens, safe for provider limits)

    if total_chars <= MAX_SINGLE_CALL or len(chunks) <= 1:
        # Single call
        prompt = EXTRACTION_PROMPT.replace("SECTION_LABEL", f"Chapter {ch_num}") + latex[:100_000]
        print(f"  Single call ({total_chars} chars) to {model}...")
        result = call_llm_with_retry(prompt, f"Chapter {ch_num}", model=model)
        if result is None:
            print(f"  ERROR: Could not parse JSON from response")
            return None
        nodes = result.get("nodes", [])
        edges = result.get("edges", [])
    else:
        # Chunk-by-chunk extraction
        # Group small consecutive sections into larger chunks
        grouped = []
        current_text = ""
        current_label = ""
        for sec_num, text in chunks:
            if len(current_text) + len(text) > MAX_SINGLE_CALL and current_text:
                grouped.append((current_label, current_text))
                current_text = text
                current_label = sec_num
            else:
                if not current_label:
                    current_label = sec_num
                current_text += "\n\n" + text
        if current_text:
            grouped.append((current_label, current_text))

        print(f"  Grouped into {len(grouped)} API calls")
        chunk_results = []
        for i, (label, text) in enumerate(grouped):
            print(f"  Chunk {i+1}/{len(grouped)} (section {label}, {len(text)} chars)...")
            result = call_llm_with_retry(text, f"Section {label}+", model=model)
            if result:
                chunk_results.append(result)
                n = len(result.get("nodes", []))
                e = len(result.get("edges", []))
                print(f"    -> {n} nodes, {e} edges")
            else:
                print(f"    -> Failed after retry")

        nodes, edges = merge_results(chunk_results)

    # Post-processing
    VALID_TYPES = {"definition", "theorem", "lemma", "corollary", "proof", "algorithm"}
    # Remove nodes with invalid types (e.g. "exercise", "example", "remark")
    before = len(nodes)
    nodes = [n for n in nodes if n.get("type") in VALID_TYPES]
    if len(nodes) < before:
        print(f"  Filtered {before - len(nodes)} nodes with invalid types")
    # Remove nodes with empty statements
    nodes = [n for n in nodes if n.get("statement", "").strip()]
    # Remove duplicate nodes (same ID from different chunks — keep first)
    seen_ids = set()
    unique_nodes = []
    for n in nodes:
        nid = n.get("id", "")
        if nid not in seen_ids:
            seen_ids.add(nid)
            unique_nodes.append(n)
    nodes = unique_nodes

    edges = dedup_edges(edges)
    edges = remove_cycles(nodes, edges)

    result = {
        "metadata": {
            "title": f"Ch. {ch_num}: {title}",
            "sections": f"{chunks[0][0]}--{chunks[-1][0]}" if len(chunks) > 1 else chunks[0][0],
        },
        "nodes": nodes,
        "edges": edges,
    }

    print(f"  Final: {len(nodes)} nodes, {len(edges)} edges")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Solution extractor: knowledge graph from LaTeX via LLM (with chunking).")
    parser.add_argument("input", help="Path to LaTeX file")
    parser.add_argument("-o", "--output", required=True, help="Output JSON file path")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"LLM model (default: {DEFAULT_MODEL})")
    args = parser.parse_args()

    print(f"Annotating: {args.input}")
    print(f"Model:      {args.model}")

    result = annotate_chapter(args.input, model=args.model)

    if result is None:
        print("Extraction failed.")
        sys.exit(1)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Output written to: {args.output}")


if __name__ == "__main__":
    main()
