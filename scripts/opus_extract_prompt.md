<!-- CANONICAL: src/node_types.py and src/edge_types.py.
     This file is derivative; sync it whenever the canonical changes. -->

Extract a mathematics textbook or paper to JSON for the Authomathics project.

## Book / Paper

- book_id: {BID}
- title: {TITLE}
- authors: {AUTHORS}
- year: {YEAR}
- output_dir: /mnt/c/Code/Github/Authomathics/textbooks/extracted/{BID}_{SLUG}/
- PRE-EXTRACTED TEXT: /tmp/authomath_pdftxt/{BID}.txt
- MASTER CSV: /mnt/g/My Drive/Research/Automath/undergrad_textbooks.csv (23 cols — do NOT touch any other CSV)

## GRANULARITY / RESOLUTION — MUST be specified by caller

The caller MUST specify the extraction resolution in the parameters below.
If ANY of these are missing or empty, the extractor MUST pause and ASK
the user before launching. Do NOT pick a default silently.

### Proof granularity: {PROOF_GRANULARITY}

Must be one of:

- **`theorem_level`** (default, cheap, regex-feasible)
  - Proofs are single nodes with `id`, `type="proof"`, `proves_id`, `page`.
  - `steps[]` field is OMITTED or left empty.
  - Use this for: large-scale extraction (50K+ papers), rule-based baselines,
    quick dev passes.

- **`with_proof_steps`** (expensive, Opus-only, higher-granularity)
  - Each proof node additionally carries a `steps[]` array of logical moves.
  - Each step has: `{id, step_number, move_type, statement_clean,
    depends_on_step_ids[], uses_node_ids[]}`.
  - `move_type` ∈ {`setup`, `introduce_variable`, `apply_lemma`, `case_split`,
    `induction`, `contradiction_setup`, `algebraic_manipulation`,
    `substitute`, `bound_estimate`, `invoke_identity`, `conclude`, `other`}.
  - Aim for 3-15 steps per proof. Merge trivial algebraic steps; split
    distinct logical moves.
  - Steps form a DAG via `depends_on_step_ids` (typically linear, sometimes
    branches for case-splits).
  - Use this for: the 10 gold papers, proof-step-decomposition evaluation
    track, any request where the caller explicitly asks for detail.

### Equation granularity: {EQUATION_GRANULARITY}

Must be one of:

- **`omit`** (default for fast extraction)
  - Displayed equations are NOT extracted as separate nodes.
  - They may appear inline inside theorem `statement_latex`.

- **`as_nodes`** (full extraction)
  - Each numbered / displayed equation becomes a separate `EQUATION` node
    with `id`, `type="equation"`, `name` (if named), `statement_latex`
    (the equation itself), `referenced_by[]` (theorem/lemma nodes citing it),
    `page`.
  - Only for prominent displayed equations — not every inline `$x^2$`.

## NODE PROVENANCE — `origin` field (read this before extracting)

Every node carries an `origin` field with two values:

- `"paper"` (default) — node represents a contribution introduced by THIS
  paper/textbook.
- `"external"` — node represents a CITED PRIOR RESULT the paper invokes
  but does not establish (a classical theorem, a baseline algorithm cited
  for comparison, a foundational definition the paper depends on).

For `origin: "external"` nodes, also set `origin_citation` to a short
free-text source identifier (e.g. `"Sinkhorn 1967"`, `"Cover & Thomas,
Elements of Information Theory"`, `"[CT05, Thm 1]"`).

Why: a graph that captures only this paper's own contributions is missing
its scaffolding. Cited classical theorems and baseline algorithms are
genuine dependency nodes.

## TYPE-PROMOTION RULE (content trumps environment)

A node's type is determined by its semantic CONTENT, not the surrounding
LaTeX environment. Specifically:

- A `\begin{definition}` block whose body is an OPTIMIZATION FORMULATION
  (`x* = argmin f(x) s.t. Ax<=b`, or a named problem with attached
  algorithms / complexity / hardness) MUST be emitted as `type="problem"`,
  NOT `type="definition"`. Diagnostic: does the object accumulate
  problem-attachments (algorithms, complexity, dual, hardness)?
- A `\begin{definition}` block whose body is a step-by-step procedure
  becomes `type="algorithm"`.
- `\begin{lemma}` / `\begin{proposition}` whose body is a numerical bound
  used as scaffolding remain lemma / proposition.

See `Manuscript/node_types_appendix_draft.tex` ("Type-promotion rule")
for the canonical statement.

## HARD RULES (read carefully — prior agents drifted on these)

1. **NO REGEX-SCRIPT SHORTCUT.** You MUST read the text with the Read tool
   (with offsets for large files), understand each section semantically,
   and produce structured nodes from your reading. Do NOT write a Python
   script that scans for `Theorem N.M` patterns — that produces shallow
   output with no separated assumptions/conclusions and thin edges. If
   the source is large (>1 MB text), use Read with multiple offsets/chunks.

2. **NO FABRICATION.** Every node statement must correspond to text that
   appears in the source. If the pre-extracted text is TOC-only /
   bibliography-only / preface-only / frontmatter-only (<5% body prose),
   mark `extraction_failed_no_body_text` in CSV and exit. Do NOT
   synthesize content from general knowledge of the topic or from
   external papers cited in the book.

3. **FAIL-FAST ON SMALL OR BAD TEXT.** First action: `wc -c
   /tmp/authomath_pdftxt/{BID}.txt`. If file doesn't exist, mark
   `extraction_failed_pdf_unreadable`. If <5 KB of real body content,
   mark `extraction_failed_thin`. If the text is a different paper/book
   than metadata claims (title mismatch), mark
   `extraction_failed_wrong_pdf`.

4. **GRANULARITY PARAMETERS ARE MANDATORY.** If `{PROOF_GRANULARITY}` or
   `{EQUATION_GRANULARITY}` is unset/placeholder, STOP and ask the user
   before beginning extraction. Do NOT silently pick a default.

## Schema (L1/L2 textbook or paper)

<!-- The prompt-builder substitutes the canonical schema block below at
     extraction time (see src/schema_for_prompts.py: render_prompt). Edit
     src/node_types.py / src/edge_types.py — NOT this file — to change the
     schema. -->
{{SCHEMA_BLOCK}}

Optional `tags` field (any node): a `list[str]` of type-specific tags
from the controlled vocabulary in `src/node_types.py` (`TAGS_VOCABULARY`).
Validators warn on unknown tags but do NOT reject. Full vocabulary lives
in the schema spec; emit a tag only when confident.

Node-ID convention: `{TYPE_PREFIX}{BID}_chN_xxxNN` or for papers
`{PREFIX}P{NUM}.{SEQ}` where PREFIX ∈ {D, T, L, P, C, E, A, Pr, Q, OQ, R, As, PS, AS}.

Math in `$..$` inline LaTeX with proper `\commands`; escape backslashes
properly in JSON.

## Workflow with incremental checkpointing

1. `mkdir -p output_dir`
2. `wc -c` pre-extracted text; head -200 to verify body prose (not just
   TOC/preface).
3. If PROOF_GRANULARITY=unset or EQUATION_GRANULARITY=unset, STOP and ask.
4. Parse TOC region (first few KB) to identify chapters → save `toc.json`.
5. For each chapter:
   a. Read chapter's text slice via Read tool with offsets.
   b. Extract nodes semantically: full semantic separation — statement_latex
      verbatim, statement_clean as NL paraphrase, assumptions[] and
      conclusions[] as separate lists for theorem-like.
   c. If PROOF_GRANULARITY=with_proof_steps: for each proof, decompose
      into 3-15 steps as specified above.
   d. If EQUATION_GRANULARITY=as_nodes: create EQUATION nodes for
      displayed/numbered equations.
   e. Build `uses` edges from explicit "by Theorem X.Y" cross-refs.
   f. Save `chapter_N.json`.
   g. **Update `progress.json` IMMEDIATELY after each chapter** (survives
      timeout).
6. Merge → `book.json` with fields:
   - `layer` ∈ {L0, L1, L2}
   - `source_type` (e.g. real_analysis_textbook, arxiv_paper_math_CO)
   - `model_used` = claude-opus-4-7 (or whatever)
   - `proof_granularity` = {PROOF_GRANULARITY} (record in metadata)
   - `equation_granularity` = {EQUATION_GRANULARITY}
7. Update master CSV row for {BID}: extraction_status=extracted, nodes=N,
   edges=E, model_used=claude-opus-4-7, proof_granularity=X,
   equation_granularity=Y (if CSV has those columns — else skip).
8. Append to log: `[ISO] {BID} DONE nodes=N edges=E chapters=K
   proof_granularity=X equation_granularity=Y model=claude-opus-4-7`.

## Conventions

- Math in `$..$` inline LaTeX (escape backslashes properly in JSON).
- `statement_clean`: 1-sentence NL paraphrase.
- Unique node ids per book/paper: `{PREFIX}{BID}_chN_xxxNN` format.
- Every theorem SHOULD have separated assumptions and conclusions where
  the source makes that clear.

## Field-specific hints

{FIELD_HINTS}

## Report (<200 words)

When complete: chapter count, node count by type, edge count, proof step
count (if applicable), equation node count (if applicable), sample 3
theorem names (drawn from body text, not TOC entries), any anomalies
(mismatched titles, OCR corruption, frontmatter-only text, etc.).

## Parameter caller-checklist

Before launching an extraction agent, the caller MUST populate:

| Parameter | Required? | Example |
|---|---|---|
| BID | yes | `b042` or `paper404` |
| TITLE | yes | "Elements of Information Theory" |
| AUTHORS | yes | "Cover, Thomas" |
| YEAR | yes | "2006" |
| SLUG | yes | `covert_eit` |
| PROOF_GRANULARITY | **yes** | `theorem_level` or `with_proof_steps` |
| EQUATION_GRANULARITY | **yes** | `omit` or `as_nodes` |
| FIELD_HINTS | optional | "Focus on coding-theory theorems; merge ex 2.14..." |

If any required field is missing, DO NOT PROCEED — ask the user.
