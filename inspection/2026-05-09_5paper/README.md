# 5-paper rules-vs-opus comparison (2026-05-09)

Inspection snapshot: 5 math.CO papers extracted by both the rule-based T3 extractor (`_rules.json`, parse_batch.py post-Fix-a/b/c/d) and Claude Opus 4.7 with the `v3_combined` prompt (`_opus.json`). Goal: ground the next round of T3 fixes in concrete failure cases beyond the ones already on the parser-improvement list (B1 / B3 / B5 / B4).

## How to view the HTML graphs

The repo is private, so the HTMLs in this directory cannot be viewed inline on github.com. Two options:

1. **Clone and open locally (recommended):**
   ```bash
   git clone https://github.com/orzuk/Saranga.git
   cd Saranga/inspection/2026-05-09_5paper/
   # Then either open the HTMLs directly:
   open 1003.3103v1_rules.html      # macOS
   xdg-open 1003.3103v1_rules.html  # Linux
   start 1003.3103v1_rules.html     # Windows / WSL via cmd
   # OR open this README in a Markdown previewer (VSCode, Typora, etc.)
   # — the per-paper links in the table below become clickable and
   # open the HTMLs in your default browser.
   ```
2. **Direct download from GitHub:** browse to the file in the GitHub UI, click "Raw", save as. Then open in browser. Slower than cloning the whole dir.

## Aggregate metrics (treating Opus as gold)

| paper | rules nodes | opus nodes | rules edges | opus edges | node F1 | edge F1 |
|---|---:|---:|---:|---:|---:|---:|
| 1001.2078v1 | 50 | 38 | 30 | 47 | 0.14 | 0.00 |
| 1001.3528v1 | 111 | 63 | 472 | 112 | 0.13 | 0.00 |
| 1001.4249v1 | 26 | 40 | 39 | 41 | 0.09 | 0.00 |
| 1003.0943v2 | 90 | 59 | 150 | 79 | 0.03 | 0.00 |
| 1003.3103v1 | 10 | 20 | 1 | 22 | 0.13 | 0.00 |

Edge F1 is ~0 across the board: rules emits keyword-matched edges that don't align with logical-dependency edges. Node F1 is in the 0.03–0.20 range — both significant FN (rules misses content) and FP (rules emits spurious nodes) are present.

## What to look at per paper

The `_rules.html` / `_opus.html` columns are relative links — they open the HTML graph in your browser when you've cloned this repo and view this README in a Markdown previewer (or click them directly in any text editor that resolves `.md` links).

| Paper | Source | T3 graph (rules) | Opus graph |
|---|---|---|---|
| 1001.2078v1 | [arxiv abs](https://arxiv.org/abs/1001.2078v1) / [pdf](https://arxiv.org/pdf/1001.2078v1) | [1001.2078v1_rules.html](./1001.2078v1_rules.html) | [1001.2078v1_opus.html](./1001.2078v1_opus.html) |
| 1001.3528v1 | [arxiv abs](https://arxiv.org/abs/1001.3528v1) / [pdf](https://arxiv.org/pdf/1001.3528v1) | [1001.3528v1_rules.html](./1001.3528v1_rules.html) | [1001.3528v1_opus.html](./1001.3528v1_opus.html) |
| 1001.4249v1 | [arxiv abs](https://arxiv.org/abs/1001.4249v1) / [pdf](https://arxiv.org/pdf/1001.4249v1) | [1001.4249v1_rules.html](./1001.4249v1_rules.html) | [1001.4249v1_opus.html](./1001.4249v1_opus.html) |
| 1003.0943v2 | [arxiv abs](https://arxiv.org/abs/1003.0943v2) / [pdf](https://arxiv.org/pdf/1003.0943v2) | [1003.0943v2_rules.html](./1003.0943v2_rules.html) | [1003.0943v2_opus.html](./1003.0943v2_opus.html) |
| 1003.3103v1 | [arxiv abs](https://arxiv.org/abs/1003.3103v1) / [pdf](https://arxiv.org/pdf/1003.3103v1) | [1003.3103v1_rules.html](./1003.3103v1_rules.html) | [1003.3103v1_opus.html](./1003.3103v1_opus.html) |

## Why each paper was picked (Or's first-pass impressions)

- **1001.4268v1** [excluded — French-language paper, replaced by 1003.3103v1]
- **1001.4268v1 → 1003.3103v1**: small paper, rules emit only definitions and one theorem with a wrong def→theorem arrow. Useful as a minimal failure case. (Or said this paper has "only definitions and one theorem with wrong arrow def→thm".)
- **1001.4268v1**: had `\usepackage[francais]{babel}` — the rule patterns are English-only and would mostly miss French definitions ("on définit X comme..."). Excluded from this round but flagged as a category to handle later.
- **1001.4249v1**: "json looks pretty good" per Or's first pass. The visualizer issue was math non-rendering plus text overflow — not a rule-extraction issue. The current visualizer (post-`6905ea7`) handles both better; HTML here uses the latest visualizer.
- **1001.2078v1**: "json looks bad — lots of text in the graph when viewed". Likely the [MATH] placeholder issue (B3) — long captured text inflated by failed math substitution.
- **1001.3528v1**: "shallow but lots of math not rendered". Now we see it's NOT shallow — rules emitted 111 nodes (vs 63 from Opus) including 472 edges. The "shallow" impression was probably the visualizer truncating a too-dense graph. Fixing math rendering would surface that the underlying graph is over-extracted, not under.
- **1003.0943v2**: "intersection and bad layout, but maybe too many definitions". 90 rule-nodes vs 59 Opus — confirms over-extraction.

## How to read the per-paper diff CSVs

Each `<paper_id>_diff.csv` has one row per node with three categories:

- `matched` — Opus and rules both have this node. Look at the `failure_mode` column for known issues per match (`type:opus=theorem vs rules=definition`, `[MATH] placeholder in rules statement`, `rules has no name`).
- `opus_only` — Opus emitted the node, rules missed it. **False negative for rules.** These are the most actionable: each row is a structure the rule extractor *should* have caught.
- `rules_only` — rules emitted the node, no Opus equivalent. **False positive for rules.** Either spurious match (rule fired on non-definitional text) or genuine content Opus also missed (rare — Opus is the comparison standard, not gold-true).

Sort by `failure_mode` to cluster patterns. Sort by `category` to focus on FN or FP separately.

## Existing fix list (already in `arxiv_revision_roadmap.txt §1` and the Yaron mail draft)

- **B1**: empty `name` field in 50–80% of T3 nodes. Populate from `\label{...}` or first 6 words.
- **B3**: `[MATH]` placeholders in `statement` field. Move to `clean_text`; keep real LaTeX in `statement` (or `raw_latex` → `statement`).
- **B4**: in-proof equations as top-level siblings instead of children of their parent proof.
- **B5**: `metadata` block has only `paper_id`. Populate `title`, `authors`, `arxiv_id`, `category`, `year` from the arxiv-metadata snapshot.

The diff CSVs here will surface additional failure modes beyond B1–B5 — those go into the next round of asks for parse_batch.py.

## Reproducing the HTMLs locally

If the HTMLs in this commit get stale, regenerate with:

```bash
python3 src/visualize_annotation.py --html-only inspection/2026-05-09_5paper/
```

Reproducing the Opus extractions requires API access (claude-opus-4-7) and the prompt at `_prompt_used.md` (which is the rendered version of `scripts/opus_extract_prompt_v3_combined.md` with `{{SCHEMA_BLOCK}}` substituted from `src/node_types.py` + `src/edge_types.py`).

Reproducing the rules JSONs requires running `parse_batch.py --extraction-mode rules` against the per-paper `.tex` source under `$SARANGA_DATA_ROOT/tier3/math_CO/tex/<paper_id>/source/`.

## Files in this directory

- `README.md` — this file
- `_summary.csv` — aggregate metrics, one row per paper
- `_prompt_used.md` — exact prompt sent to the 5 Opus extraction agents
- `<paper_id>_rules.json` — rule-based extraction (parse_batch.py output)
- `<paper_id>_opus.json` — Opus 4.7 extraction (treated as gold for comparison)
- `<paper_id>_eval.csv` — per-type P/R/F1 metrics
- `<paper_id>_diff.csv` — node-level alignment + failure-mode flags (the actionable artifact)
- `<paper_id>_rules.html` — visualizer output for the rules graph
- `<paper_id>_opus.html` — visualizer output for the Opus graph
