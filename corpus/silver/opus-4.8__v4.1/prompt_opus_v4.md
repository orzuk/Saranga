# Extraction prompt for `opus-4.8` (prompt version `v4.1`)

This is the verbatim prompt used to produce every JSON in this directory.
Source: `scripts/opus_extract_prompt_v4.md`.
Run in-session via `scripts/in_session_extract_prompt.md`, which renders this file.

---

<!-- CANONICAL: src/node_types.py and src/edge_types.py.
     This file is derivative; sync it whenever the canonical changes. -->

Extract a mathematics paper or chapter to JSON for the Authomathics project.

This prompt is the **v4 EXTRACTION-ONLY** variant. Its single most
important goal is **faithful verbatim extraction**. The `statement`
field of every node MUST be a literal copy of the corresponding text
in the source `.tex`, with LaTeX preserved exactly. Paraphrasing,
summarizing, "cleaning up", or rewriting destroys downstream alignment,
plagiarism detection, and cross-paper semantic-match analyses that
depend on exact source provenance — those tasks are the whole point of
the dataset. If you reword a statement, the node becomes useless for
its primary purpose.

## Source

- BID: {BID}
- TITLE: {TITLE}
- AUTHORS: {AUTHORS}
- YEAR: {YEAR}
- TEX SOURCE: {TEX_SOURCE}
- OUTPUT JSON: {OUTPUT_JSON}

## THE CORE RULE — READ THIS BEFORE ANYTHING ELSE

**`statement` IS A COPY, NOT A SUMMARY.**

For every node, the `statement` field must be the **verbatim text of
the corresponding block in the source `.tex`**, with LaTeX preserved
exactly. You are acting as a structured **extractor**, not as a
writer, editor, or summarizer.

The ONLY edits permitted to the source text are mechanical cleanup that
does not change wording:

- Collapse runs of whitespace and newlines into single spaces.
- Strip LaTeX comments (`% ...` to end of line).
- Drop `\label{...}` and `\index{...}` commands.
- Escape backslashes for JSON (`\Sigma` in source → `"\\Sigma"` in JSON).

Everything else — every word, every math symbol, every named object,
every qualifying clause, every "Let X be...", every "Suppose that..."
— stays.

### Anti-paraphrase catalogue (memorize this)

| ❌ DO NOT | ✅ DO |
|---|---|
| Shorten a statement to fit a layout. | Copy the full body. Length is fine. |
| Rewrite "Let $X$ be a Banach space and $T:X\to X$ a bounded linear operator. Then ..." as "If $X$ is Banach and $T$ is bounded linear, then ...". | Keep the original "Let ... . Then ..." phrasing. |
| Translate math into prose ("$\arg\min_x f(x)$" → "the $x$ that minimizes $f$"). | Keep the math symbols exactly. |
| Replace a named object with a generic description ("Sinkhorn-Knopp algorithm" → "fixed-point iteration"). | Keep the canonical name. |
| "Clean up" notation ("$P^\lambda = \diag(u) K \diag(v)$" → "P = diag(u) K diag(v)"). | Keep the LaTeX exactly. |
| Merge two source sentences into one. | Preserve the source's sentence structure. |
| For a proof: replace the body with "By induction on $n$." | Copy the full proof body into `statement`. (Decomposition into `proof_step` nodes is ADDITIONAL structure — it does not replace the parent's verbatim `statement`.) |
| For an algorithm: replace the pseudocode with a 1-sentence summary. | Copy the full pseudocode body into `statement`. |
| Convert "$\sum_{i=1}^n a_i$" to "the sum of $a_i$". | Keep the sigma exactly. |
| Drop a hypothesis you think is "implied" or "obvious". | Copy every hypothesis. |
| Smooth out awkward phrasing. | Preserve awkward phrasing — it is part of the source. |

### Statement length

There is **no upper bound** on `statement` length. A 30-line algorithm
body or a multi-paragraph theorem statement is FINE — put the full
verbatim body in `statement`.

If a short display-friendly version is genuinely needed for the
visualizer, put it in the OPTIONAL `statement_short` field (see
"Optional fields" below). `statement_short` is explicitly marked as
derived and lossy; it must NEVER be used as the source for alignment,
plagiarism, or any analytical task. `statement` is the canonical truth.

## HARD RULES

1. **VERBATIM EXTRACTION (above) IS RULE #1.** Re-read the core rule
   and the anti-paraphrase catalogue before writing each `statement`
   field.

2. **NO REGEX-SCRIPT SHORTCUT.** Read the `.tex` with the Read tool
   (with offsets for large files). Identify each result environment
   semantically, then COPY its body into the JSON node. Do NOT write a
   Python script that greps for `Theorem N.M` patterns.

3. **NO FABRICATION.** Every node statement must be text that
   LITERALLY APPEARS in the source `.tex`. Do not synthesize from
   general knowledge, external papers, or your own understanding of
   the result. If you cannot point to the exact span in the source
   that a `statement` was copied from, the node is invalid.

4. **PRESERVE CANONICAL NAMES.** When the paper introduces a named
   object ("Sinkhorn-Knopp algorithm", "Markov's inequality", "PCA"),
   use that exact name in the `name` field. Do NOT abstract or
   generalize it.

5. **PRESERVE LaTeX MATH EXACTLY.**
   - Wrap inline math in `$..$` exactly as in the source.
   - Keep every backslash command: `\Sigma`, `\sum`, `\int`, `\in`,
     `\subset`, `\mathbb`, `\mathcal`, `\langle`, `\rangle`, `\nabla`,
     `\defeq`, `\bar`, `\hat`, `\tilde`, `\frac`, etc.
   - Greek letters and capitals: `$\alpha, \beta, ..., \omega$` and
     `$\Gamma, \Delta, ..., \Omega$`.
   - Operators: `$\arg\min, \arg\max, \log, \exp, \min, \max, \sup,
     \inf$`.
   - Sets/spaces: `$\mathbb{R}, \mathbb{Z}, \mathbb{N}, \mathbb{P}$`.
   - Subscripts `_{ij}` and superscripts `^{T}` use braces when >1 char.
   - In JSON, escape backslashes properly: source `\Sigma` → JSON `"\\Sigma"`.
   - Display math (`\[ ... \]`, `\begin{equation} ... \end{equation}`)
     stays as display math inside the statement — preserve it.

6. **CITED PRIOR RESULTS — emit as `origin: "external"`.** Mathematical
   papers depend on prior work. EXTRACT the cited classical theorems,
   foundational definitions, and baseline algorithms that the paper
   INVOKES but does not ESTABLISH.

   Each node carries an `origin` field:
   - `"paper"` (default) — node is a contribution introduced by THIS paper.
   - `"external"` — node is a CITED PRIOR RESULT the paper uses but
     does not prove.

   For `origin: "external"` nodes, also set `origin_citation` to a
   short free-text identifier of the cited source. The `statement`
   field for an external node is still verbatim — copy the way THIS
   paper states the cited result (which may differ from the original
   source's phrasing; that is fine, the canonical truth for our
   dataset is how THIS paper presents it).

   Trigger phrases: "by X", "as shown in [REF]", "we use the classical
   result of Y", "we compare against the baseline Z" → `origin: "external"`.

7. **TYPE-PROMOTION — content trumps environment.** A node's `type` is
   determined by its semantic CONTENT, not the surrounding LaTeX
   environment. This is STRUCTURAL reasoning that does NOT change what
   goes into `statement` — the `statement` is still the verbatim body
   of the source block, regardless of what `type` you assign.

   - A `\begin{definition}` block whose body is an OPTIMIZATION
     FORMULATION (e.g. `x^* = \arg\min_x f(x)` subject to constraints,
     or a named problem with attached algorithms / complexity /
     hardness) MUST be emitted as `type="problem"` (typically
     `subclass="optimization"`), NOT `type="definition"`.
   - A `\begin{definition}` block whose body is a step-by-step
     procedure becomes `type="algorithm"`.
   - A `\begin{lemma}` / `\begin{proposition}` whose body is a
     numerical bound used as scaffolding remains a lemma / proposition.
   - A custom `\newtheorem{property}` / `\newtheorem{claim}` /
     `\newtheorem{fact}` etc. maps to the closest standard schema type
     — typically `proposition` or `claim`. Do NOT emit custom `type`
     values; the visualizer's color map only knows the schema's
     standard types.

8. **COMPLETENESS — DO NOT DROP THEOREM-LIKE RESULTS.** Every numbered
   or labeled stated result in the `.tex` source MUST produce a
   theorem-like node (type ∈ {theorem, lemma, proposition, corollary,
   claim}):

   - Every `\begin{theorem}` → `theorem` node
   - Every `\begin{lemma}` → `lemma` node
   - Every `\begin{proposition}` → `proposition` node
   - Every `\begin{corollary}` → `corollary` node
   - Every `\begin{claim}` → `claim` node
   - Every custom theorem-like env → mapped per rule 7

   **Do NOT demote a stated result to an `equation` node** even if the
   paper presents it inside `\begin{equation}...\end{equation}` blocks.
   If the prose says "the optimal $P^\lambda$ has the unique form
   $P^\lambda = \diag(u) K \diag(v)$ [Sinkhorn's theorem]" — that is a
   **theorem** (existence/uniqueness statement). Emit it as a theorem
   node with the verbatim sentence(s) as `statement`.

   Count of theorem-like nodes you emit ≥ count of labeled theorem-like
   environments in the source (greater if cited externals are added).

9. **ACYCLICITY (DAG CONSTRAINT).** The within-paper graph must be a
   directed acyclic graph. A `uses` edge `A → B` reads "B uses A", so
   `A` must be logically prior to `B`. No reciprocal `uses` edges
   between the same pair. The downstream validator runs cycle
   detection and flags violations.

10. **LEVEL-2 STEP EXTRACTION (MANDATORY when triggers fire).**
    Step decomposition is a **parallel structural extraction**, not a
    substitute for the parent's verbatim body. The parent `proof` /
    `algorithm` `statement` MUST hold the full verbatim body
    (rule 1), AND step nodes MUST be emitted whenever ANY of the
    triggers below appears in the source. There is no editorial
    discretion: triggers fire → steps required. Skipping steps because
    "the parent already has the content" is a RULE VIOLATION — the
    parent and steps capture different structure and downstream
    tooling depends on both.

    **Hard triggers — if you see any of these in a proof/algorithm
    body, emit one step node per division (no exceptions):**

    - **Explicit "Part (N):" or "Part N:" labels.** Source patterns:
      `Part (1):`, `Part 1:`, `Part \ref{...}:`. One step per part.
    - **Explicit "Step N" / "Step N:" labels.** Source patterns:
      `Step 1.`, `Step~1`, `\textbf{Step 1}`. One step per Step.
    - **Numbered cases.** Patterns: `Case 1:`, `Case (a):`,
      `\begin{enumerate}` inside the body where each item is a logical
      step of the argument.
    - **Algorithmic environments.** `\begin{algorithmic}`,
      `\begin{algorithm}`, `\begin{enumerate}` listing procedure
      steps (e.g. "1. Compute X. 2. Compute Y. 3. Output Z."), or
      itemized lists of inputs/operations/outputs. One
      `algorithm_step` per numbered line, including the inputs/outputs
      themselves if they have their own bullets.
    - **Phase prose with explicit transitions.** "First, we show...",
      "Next, we prove...", "It remains to show...", "Finally,...",
      "Combining the above,...", "We proceed in three parts:...".
      One step per phase.
    - **Induction structure.** "By induction on $n$. Base case: ...
      Inductive step: ...". At minimum two steps (base, inductive).
    - **Case split + reunion.** "Suppose first that ... . Otherwise
      ... . In either case, ...". One step per case + one for the
      conclusion.

    **Soft trigger (use judgment):** signposted prose without explicit
    labels. A paragraph that reads as one continuous argument with no
    transitions → zero steps. A paragraph with 2-3 clear logical
    phases marked by "Now consider...", "Applying [lemma]...",
    "Therefore..." → emit one step per phase.

    **Zero-step justification.** You may emit ZERO step nodes for a
    proof/algorithm ONLY if its body is a single uninterrupted
    paragraph with no part labels, no enumerated lists, no case
    splits, no induction structure, and no signposted phase
    transitions. If you emit zero steps, the body must visibly satisfy
    this — do not skip steps when the source contains "Part (1):" /
    "Case 1:" / numbered lists.

    **Each step's `statement` is ALSO verbatim** — copy the sentence(s)
    or pseudocode line(s) from the source body that constitute that
    step. The decomposition is structural; it is NOT a rephrasing.

    **Worked example — a proof with three parts:**

    Source body:
    ```
    Part (1): By the definition of $d_i$, $f' L f = ...$ which yields
    the quadratic form.
    Part (2): The symmetry of $L$ follows directly from $W$ and $D$.
    Positive semi-definiteness follows from Part (1).
    Part (3): Obvious.
    ```

    Required output: ONE `proof` node with `statement` = the full
    verbatim body above, PLUS THREE `proof_step` nodes (PSP*.1, PSP*.2,
    PSP*.3), each with `statement` = the verbatim text of its
    corresponding "Part (N):" sentence(s) and `parent_id` pointing to
    the proof.

    Step-node fields:
    - `id` (e.g. `PSP5.1`, `ASP5.1` for paper 5 step 1)
    - `type` (`proof_step` or `algorithm_step`)
    - `parent_id` (id of the parent `proof` or `algorithm` node)
    - `step_order` (1-based sequential index within the parent)
    - `name` (a short descriptive label — this CAN be a paraphrase
      since it is a label, not a statement; e.g. "Set up gluing
      matrix", "Inductive step on $n$")
    - `statement` (verbatim source span for this step)
    - `subclass` (optional structural role from controlled vocabulary:
      `setup`, `introduce_variable`, `apply_lemma`, `case_split`,
      `induction_step`, `contradiction_setup`, `algebraic_manipulation`,
      `substitute`, `bound_estimate`, `invoke_identity`, `conclude` for
      proof steps; `initialize`, `loop`, `branch`, `update`, `return`
      for algorithm steps)
    - `tags` (optional list)

    Steps form a sub-DAG via `uses` edges with the same `parent_id`.
    Steps may reference Level-1 nodes outside the parent
    (e.g. `proof_step uses Lemma 2.3`), but step-to-step edges across
    different parents are NOT permitted; cross-proof references must
    go through Level-1 nodes.

## Schema

<!-- The prompt-builder substitutes the canonical schema block below at
     extraction time (see src/schema_for_prompts.py: render_prompt). Edit
     src/node_types.py / src/edge_types.py — NOT this file — to change the
     schema. -->
{{SCHEMA_BLOCK}}

Important type splits:

- `problem` vs. `open_problem`:
  - `problem` = a NAMED OR FORMULATED FORMAL mathematical problem the
    paper studies (an optimization formulation, a named decision
    problem like 3-SAT, etc.).
  - `open_problem` = an UNSOLVED mathematical question with no known
    solution.
- `assumption` (Level 1 node) ≠ the per-theorem `assumptions` field.
  An `assumption` node is a `\begin{assumption}` block declaring
  standing assumptions for a section/theorem cluster.

### Required node fields

- `id` — compact ID (see convention below)
- `type` — from schema
- `name` — display name (canonical name from paper)
- `statement` — VERBATIM source body, math-preserved per rule 5.
  This is the #1 core rule.
- `section` — section label from paper

### Optional node fields

- `origin` — `"paper"` (default) or `"external"` (cited prior result —
  see rule 6)
- `origin_citation` — required when `origin="external"`
- `assumptions[]`, `conclusions[]` — for theorem-like nodes. **Each
  element must use the SAME WORDING as the source** — these fields
  decompose the verbatim statement into its antecedent/consequent
  spans, they do NOT rephrase. (See "Assumption / conclusion
  decomposition" below.)
- `input[]`, `output[]` — for algorithms. Copy each input/output
  description **verbatim** from the paper's algorithm block.
- `parent_id`, `proves` — relational pointers (legacy `parent_proof` /
  `parent_algorithm` still accepted)
- `tags[]` — optional `list[str]` of type-specific tags from the
  controlled vocabulary in `TAGS_VOCABULARY` in `src/node_types.py`.
- `statement_short` — OPTIONAL display field for the visualizer. A
  1-sentence human-friendly version, ≤250 chars. **DERIVED, LOSSY**:
  populate only when a short version is genuinely useful for layout.
  Never used as input to alignment, plagiarism, or semantic-match
  analysis. The `statement` field is the canonical truth.

### Assumption / conclusion decomposition

When you split a verbatim statement into `assumptions[]` and
`conclusions[]`, you are **selecting spans from the verbatim text** —
not paraphrasing it. The union of the spans should reconstruct the
mathematical content of the statement; the wording must match the
source.

- **Regime A — explicit if/then.** Statement contains "if X, then Y"
  / "let X. Then Y" / "suppose X. Y". Copy the antecedent span(s) into
  `assumptions`, the consequent span(s) into `conclusions`.
  Example source: *"If $X \sim \mathcal{N}(0,1)$ and $t > 0$, then
  $P(X > t) \le e^{-t^2/2}$."*
  → `assumptions: ["$X \sim \mathcal{N}(0,1)$", "$t > 0$"]`,
    `conclusions: ["$P(X > t) \le e^{-t^2/2}$"]`.

- **Regime B — bare statement with free variables.** Statement is a
  single inequality/equation with typed variables whose declarations
  live in surrounding text. Copy the declaration span from surrounding
  text into `assumptions` (verbatim), copy the asserted fact span into
  `conclusions`.

- **Regime C — pure identity.** Closed-form equality with no free
  variables. `assumptions: []`, `conclusions: ["..."]` (verbatim span).

Default to Regime B over Regime C — most theorems have implicit
declarations in surrounding text; recover them by quoting the relevant
span verbatim.

### Schema rule for `input` / `output` / `assumptions` / `conclusions`

These MUST be JSON **arrays of strings**, one bullet per element, NOT a
single concatenated string. Each element is a **verbatim span** from
the source.

```json
"input":  ["Cost matrix $M$", "Regularization parameter $\\lambda$",
           "Marginals $r$ and $c$"],
"output": ["Dual-Sinkhorn divergence $d_M^\\lambda(r,c)$",
           "Scaling vectors $u, v$ such that $P^\\lambda = \\mathrm{diag}(u)\\,K\\,\\mathrm{diag}(v)$"]
```

Do NOT write `"input": "Cost matrix M, regularization parameter ..."`
as one concatenated string.

### Compact ID convention

`{PREFIX}{paper_num}.{seq}`:

| Type | Prefix | Example |
|---|---|---|
| definition | DP | DP5.1 |
| theorem | TP | TP5.1 |
| lemma | LP | LP5.1 |
| proposition | PrP | PrP5.1 |
| corollary | CP | CP5.1 |
| proof | PP | PP5.1 |
| proof_step | PSP | PSP5.1 |
| algorithm | AP | AP5.1 |
| algorithm_step | ASP | ASP5.1 |
| equation | EP | EP5.1 |
| example | ExP | ExP5.1 |
| remark | RP | RP5.1 |
| problem | ProbP | ProbP5.1 |
| open_problem | OpenP | OpenP5.1 |
| assumption | AssumP | AssumP5.1 |
| claim | ClP | ClP5.1 |
| conjecture | CnjP | CnjP5.1 |

## Edge taxonomy — with direction conventions

Use the edge type that fits, but **do not force edges**. Emit an edge
only when the text explicitly cross-references the dependency or when
the logical dependency is clear-cut. A graph with 2 well-justified
edges beats one with 10 speculative ones.

Convention: edge `source → target` means "source is a prerequisite /
support for target".

| Edge type | Semantics | Direction |
|---|---|---|
| `uses` | Source is invoked by target as a prerequisite | prereq → user |
| `proves` | Source is the proof of the target theorem | proof → theorem |
| `solves` | Source algorithm computes/solves target problem | algorithm → problem |
| `defines` | Source definition introduces the object referenced in target | definition → user |
| `illustrates` | Source example illustrates target | algorithm/thm → example, NOT example → algorithm |
| `special_case_of` | Source is a special case of target | specific → general |
| `generalizes` | Source generalizes target | general → specific |
| `resolves` | Source open_problem/conjecture is settled by target theorem-like result | open_problem/conjecture → theorem-like |

**Critical direction rule for `illustrates`:** an example *demonstrates*
or *applies* an algorithm/theorem. The example is the **dependent**, the
algorithm/theorem is the **prerequisite**. Edges go
`algorithm → example`, NOT `example → algorithm`.

**Theorem/definition → algorithm dependency:** when a paper introduces
a theorem (e.g. existence of a factorization) and an algorithm that
computes it, the theorem is a prerequisite of the algorithm:
`theorem → algorithm` with type `uses`. Same for definitions.

## Workflow

1. Read the `.tex` file (multiple Read calls with offsets if large).
2. Identify all definitions, theorems, lemmas, propositions,
   corollaries, algorithms, examples, problems, remarks, equations.
3. Assign compact IDs in source order per type.
4. For each node, **COPY** the source body into `statement` (verbatim,
   LaTeX preserved, JSON-escaped). This is the rule that matters most.
5. Apply type-promotion (rule 7) — structural reasoning that does not
   change `statement`.
6. Build edges from explicit cross-references and clear logical
   dependencies.
7. Optionally populate `statement_short` per node for visualizer
   layout (clearly derived, lossy, never used downstream as truth).
8. Write the JSON to OUTPUT_JSON:

   ```json
   {
     "metadata": {
       "title": "...",
       "paper_num": N,
       "annotator": "agent-extraction",
       "model": "claude-opus-4-7",
       "prompt_version": "v4.1",
       "extraction_date": "YYYY-MM-DD"
     },
     "nodes": [...],
     "edges": [...]
   }
   ```

## Pre-output self-check (MANDATORY)

Before emitting the JSON, walk every node and verify:

1. Open the source `.tex` at the node's section.
2. Find the originating `\begin{X}...\end{X}` block (or the
   surrounding prose for prose-level results).
3. Confirm `statement` is the body of that block **verbatim**, with:
   - All math preserved (`$..$`, all backslashes, all subscripts).
   - All hypotheses preserved (no dropped "Let X be..." clauses).
   - All named objects preserved (no generic substitutions).
   - Only mechanical cleanup applied (whitespace, comments, `\label`).
4. If `statement` contains any word, phrase, or restructuring NOT
   present in the source body — STOP. Re-extract the verbatim source
   span. Do not ship a paraphrased node.

If you cannot point to the exact span in the source that a `statement`
was copied from, the node is invalid.

## Report (<200 words)

When complete, output:
- node count by type (e.g. "8 definition, 1 theorem, ...")
- **step counts per parent**: for each `proof` and `algorithm` node,
  report `<parent_id>: N steps` (e.g. `PP1.1: 4 steps`). If N=0,
  justify in one phrase ("single-paragraph body, no part/step labels").
- edge count by type
- 3 sample node names (drawn from the body)
- any anomalies (missing names, ambiguous structure, source spans
  that were hard to copy verbatim — e.g. heavy macro use)
- confirmation: "All `statement` fields are verbatim copies of source
  spans; no paraphrasing applied."
