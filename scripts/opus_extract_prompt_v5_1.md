<!-- CANONICAL: src/node_types.py and src/edge_types.py.
     This file is derivative; sync it whenever the canonical changes. -->

Extract a mathematics paper or chapter to JSON for the Authomathics project.

This prompt is the **v5 EXTRACTION-ONLY** variant. It has TWO core rules.

**Core rule #1 — `statement` is a VERBATIM COPY** from the source `.tex`,
LaTeX preserved exactly. No paraphrase, no summary, no rewording.
Verbatim is what enables alignment, plagiarism detection, and
cross-paper semantic match — the whole point of the dataset.

**Core rule #2 — `statement_short` is the LLM COMPRESSION**, populated
whenever a meaningful 1-sentence version exists. It is the place where
the LLM's intelligent summarization lives. For proofs especially,
`statement_short` should capture the strategy ("By induction on $n$",
"Density-increment iteration"). Consumers default to `statement` when
`statement_short` is null.

These two rules co-exist: `statement` carries the source truth,
`statement_short` carries the LLM's reading. Neither replaces the
other.

## Source

- BID: {BID}
- TITLE: {TITLE}
- AUTHORS: {AUTHORS}
- YEAR: {YEAR}
- TEX SOURCE: {TEX_SOURCE}
- OUTPUT JSON: {OUTPUT_JSON}

## CORE RULE #1 — `statement` IS A COPY, NOT A SUMMARY

For every node, the `statement` field must be the **verbatim text of
the corresponding block in the source `.tex`**, with LaTeX preserved
exactly. You are acting as a structured **extractor**, not as a writer,
editor, or summarizer.

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

| ❌ DO NOT (in `statement`) | ✅ DO (in `statement`) |
|---|---|
| Shorten a statement to fit a layout. | Copy the full body. Length is fine. |
| Rewrite "Let $X$ be a Banach space and $T:X\to X$ a bounded linear operator. Then ..." as "If $X$ is Banach and $T$ is bounded linear, then ...". | Keep the original "Let ... . Then ..." phrasing. |
| Translate math into prose ("$\arg\min_x f(x)$" → "the $x$ that minimizes $f$"). | Keep the math symbols exactly. |
| Replace a named object with a generic description ("Sinkhorn-Knopp algorithm" → "fixed-point iteration"). | Keep the canonical name. |
| "Clean up" notation ("$P^\lambda = \diag(u) K \diag(v)$" → "P = diag(u) K diag(v)"). | Keep the LaTeX exactly. |
| Merge two source sentences into one. | Preserve the source's sentence structure. |
| For a proof: replace the body with "By induction on $n$." in `statement`. | Copy the full proof body into `statement`. (Put "By induction on $n$" in `statement_short` instead.) |
| For an algorithm: replace the pseudocode with a 1-sentence summary in `statement`. | Copy the full pseudocode body into `statement`. (Put the summary in `statement_short`.) |
| Convert "$\sum_{i=1}^n a_i$" to "the sum of $a_i$". | Keep the sigma exactly. |
| Drop a hypothesis you think is "implied" or "obvious". | Copy every hypothesis. |
| Smooth out awkward phrasing. | Preserve awkward phrasing — it is part of the source. |

### Statement length

There is **no upper bound** on `statement` length. A 30-line algorithm
body or a multi-paragraph theorem statement is FINE — put the full
verbatim body in `statement`.

If a short display-friendly version is genuinely useful, put it in
`statement_short` (see core rule #2). `statement_short` is explicitly
derived and lossy; it is NEVER used as the source for alignment,
plagiarism, or any analytical task. `statement` is the canonical truth.

## CORE RULE #2 — `statement_short` IS THE LLM COMPRESSION

For every node, emit `statement_short` whenever the LLM can produce a
1-sentence compression that meaningfully adds value over `statement`.

**When to emit:**
- Proofs: ALWAYS emit. The 1-sentence strategy summary is the most
  valuable artifact ("By induction on $n$", "Density-increment
  iteration", "Apply Cauchy-Schwarz to bound LHS, then integrate").
- Algorithms: ALMOST ALWAYS emit. 1-sentence "what does this algorithm
  do" ("Spectral clustering via bottom-$k$ eigenvectors then $k$-means").
- Theorems / Lemmas / Propositions: emit when the verbatim statement
  is dense with notation and a plain-English compression is informative.
- Definitions: SKIP if the verbatim statement is already a short
  English sentence; emit when the definition is long, multi-clause, or
  notation-heavy.
- Remarks / examples: usually skip unless long.

**When to skip:** if `statement_short` would be nearly identical to
`statement` (i.e., no real compression value), leave `statement_short`
absent. Consumers default to `statement` when `statement_short` is null.

**Style:**
- Plain English, math symbols allowed where natural ($\delta$, $\Delta$, etc.).
- ≤ 1 sentence, ≤ ~150 characters as a soft target (no hard cap).
- Capture the IDEA, not all the technical conditions.
- For proofs: lead with the strategy/technique name; concrete first
  step is OK but optional.

**Worked example:**

```
statement (verbatim):
  "For $f, g: \mathbb{Z}_N \to \mathbb{C}$, $\sum_r |\hat{f}(r)|^2
   |\hat{g}(r)|^2 = N \sum_t |\sum_s f(s)\overline{g(s-t)}|^2$."

statement_short:
  "Parseval-type identity relating $\ell^2$ norms of Fourier coefficient
   products to autocorrelation."
```

## HARD RULES

1. **VERBATIM `statement`, COMPRESSED `statement_short`** (core rules
   above). Re-read both before writing each node.

2. **NO REGEX-SCRIPT SHORTCUT.** Read the `.tex` with the Read tool
   (with offsets for large files). Identify each result environment
   semantically, then COPY its body into the JSON node. Do NOT write a
   Python script that greps for `Theorem N.M` patterns.

3. **NO FABRICATION.** Every node `statement` must be text that
   LITERALLY APPEARS in the source `.tex`. Do not synthesize from
   general knowledge, external papers, or your own understanding of
   the result. If you cannot point to the exact span in the source
   that a `statement` was copied from, the node is invalid.
   `statement_short`, by contrast, is your OWN compression — you may
   write it freshly. Do not confuse the two.

4. **PRESERVE CANONICAL NAMES.** When the paper introduces a named
   object ("Sinkhorn-Knopp algorithm", "Markov's inequality", "PCA"),
   use that exact name in the `name` field. Do NOT abstract or
   generalize it. `name` is load-bearing for retrieval — it maps to
   canonical literature.

5. **PRESERVE LaTeX MATH EXACTLY** (in `statement`).
   - Wrap inline math in `$..$` exactly as in the source.
   - Keep every backslash command: `\Sigma`, `\sum`, `\int`, `\in`,
     `\subset`, `\mathbb`, `\mathcal`, `\langle`, `\rangle`, `\nabla`,
     `\defeq`, `\bar`, `\hat`, `\tilde`, `\frac`, etc.
   - Greek letters: `$\alpha, \beta, ..., \omega, \Gamma, \Delta, ..., \Omega$`.
   - Operators: `$\arg\min, \arg\max, \log, \exp, \min, \max, \sup, \inf$`.
   - Sets/spaces: `$\mathbb{R}, \mathbb{Z}, \mathbb{N}, \mathbb{P}$`.
   - Subscripts `_{ij}` and superscripts `^{T}` use braces when >1 char.
   - In JSON, escape backslashes properly: source `\Sigma` → JSON `"\\Sigma"`.
   - Display math (`\[ ... \]`, `\begin{equation} ... \end{equation}`)
     stays as display math inside the statement — preserve it.

6. **`origin` IS REQUIRED ON EVERY NODE.** Mathematical papers depend on
   prior work. Every node carries an `origin` field — no defaults, no
   omissions:

   - `"paper"` — node is a contribution introduced by THIS paper.
   - `"external"` — node is a CITED PRIOR RESULT the paper uses but
     does not establish (classical theorems invoked, foundational
     definitions imported, baseline algorithms compared against).

   For `origin: "external"` nodes, also set `origin_citation` to a
   short free-text identifier ("Brooks 1941", "Davis & Kahan; Stewart
   & Sun 1990", "Impagliazzo, Levin, Luby", etc.).

   The `statement` field for an external node is still verbatim — copy
   the way THIS paper states the cited result (which may differ from
   the original source's phrasing; that is fine, the canonical truth
   for our dataset is how THIS paper presents it).

   Trigger phrases: "by X", "as shown in [REF]", "we use the classical
   result of Y", "we compare against the baseline Z" → `origin: "external"`.

7. **CLOSED NODE TYPE VOCABULARY.** A node's `type` is determined by
   semantic CONTENT, not LaTeX environment, BUT the resulting type MUST
   come from this closed set:

   `definition, theorem, lemma, proposition, corollary, claim,
   conjecture, remark, example, open_problem, problem, algorithm,
   proof, proof_step, algorithm_step, equation, assumption`

   Do NOT invent new types (`fact`, `property`, `observation`, etc).
   Map non-standard `\newtheorem{...}` environments to the closest
   standard type — typically `proposition`, `remark`, or `claim`.

   Type-promotion within the closed set:
   - A `\begin{definition}` whose body is an OPTIMIZATION FORMULATION
     (e.g. `x^* = \arg\min_x f(x)`) → `type="problem"`, not `definition`.
   - A `\begin{definition}` whose body is a step-by-step procedure →
     `type="algorithm"`.
   - A `\begin{lemma}` whose body is a numerical bound used as
     scaffolding stays `lemma`.
   - A custom `\newtheorem{property}` or `\newtheorem{fact}` →
     `proposition` or `claim`.

8. **`problem` vs `open_problem` distinction:**
   - `problem` = a FORMALLY STATED computational/optimization/decision
     problem the paper studies (e.g. "$\maximize_\theta L(\theta)$
     s.t. $D_{KL}(\theta_{old},\theta) \le \delta$", "3-SAT").
   - `open_problem` = an UNRESOLVED mathematical question with no known
     solution ("It is unknown whether...", "An important open question
     is...").

9. **COMPLETENESS — DO NOT DROP THEOREM-LIKE RESULTS.** Every numbered
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
   **theorem** (existence/uniqueness statement).

   Count of theorem-like nodes you emit ≥ count of labeled theorem-like
   environments in the source.

10. **ACYCLICITY (DAG CONSTRAINT).** The within-paper graph must be a
    directed acyclic graph. A `uses` edge `A → B` reads "B uses A", so
    `A` must be logically prior to `B`. No reciprocal `uses` edges
    between the same pair.

11. **`tags[]` IS TOPICAL ONLY. `proof_strategy[]` IS FOR PROOF STRATEGY.**
    Do not mix the two.

    - `tags[]` on any node — topical/role labels:
      `existence, uniqueness, bound, identity, foundational, optimization,
      combinatorial, randomized, sampling, MM_algorithm, constrained_optimization,
      monotonic_improvement, ...` (open vocabulary, but semantically TOPICAL).
    - `proof_strategy[]` on `proof` nodes ONLY — the strategy of the
      proof, controlled vocabulary:
      `induction, strong_induction, contradiction, minimal_counterexample,
      construction, probabilistic, case_analysis, density_increment,
      direct, contrapositive, dual_argument, geometric, algebraic_manipulation,
      compactness, fixed_point, other`.

    **Wrong:** putting `"contradiction"` in `tags[]` of a proof node.
    **Right:** `tags: ["graph_coloring"]`, `proof_strategy: ["contradiction", "minimal_counterexample"]`.

12. **`section` IS PLAIN SECTION TITLE.** Do not include LaTeX labels,
    cross-reference identifiers, or parenthesized provenance markers.

    - **Wrong:** `"section": "3 Monotonic Improvement (alg:pialg)"`
    - **Wrong:** `"section": "1 (cited)"`
    - **Right:** `"section": "3 Monotonic Improvement"`
    - **Right:** `"section": "1 Introduction"` plus `"origin": "external"`
      on the cited node.

13. **LEVEL-2 STEP EXTRACTION (MANDATORY when triggers fire).**
    Step decomposition is a **parallel structural extraction**, not a
    substitute for the parent's verbatim body. The parent `proof` /
    `algorithm` `statement` MUST hold the full verbatim body
    (rule 1), AND step nodes MUST be emitted whenever ANY of the
    triggers below appears in the source. There is no editorial
    discretion: triggers fire → steps required.

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
      steps. One `algorithm_step` per numbered line.
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
    labels. A paragraph with 2-3 clear logical phases marked by "Now
    consider...", "Applying [lemma]...", "Therefore..." → emit one
    step per phase.

    **Zero-step justification.** You may emit ZERO step nodes only if
    the body is a single uninterrupted paragraph with no part labels,
    no enumerated lists, no case splits, no induction structure, and
    no signposted phase transitions.

    **Each step's `statement` is ALSO verbatim** — copy the sentence(s)
    or pseudocode line(s) from the source body that constitute that
    step. **Each step's `statement_short` is the LLM compression of
    that step's role** (e.g. "Set up induction on $n$", "Apply
    Cauchy-Schwarz", "Conclude by Markov's inequality").

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
    verbatim body above (and `statement_short` = e.g. "Direct
    expansion + symmetry"), PLUS THREE `proof_step` nodes, each with
    `statement` = the verbatim text of its "Part (N):" sentence(s),
    `statement_short` = LLM compression of that step's role,
    `parent_id` pointing to the proof, and `subclass` from the
    canonical set.

    **Step-node fields:**
    - `id` (e.g. `PSP5.1`, `ASP5.1` for paper 5 step 1)
    - `type` (`proof_step` or `algorithm_step`)
    - `parent_id` (id of the parent `proof` or `algorithm` node)
    - `step_order` (1-based sequential index within the parent)
    - `name` (a short descriptive label)
    - `statement` (verbatim source span for this step)
    - `statement_short` (LLM compression of the step's role)
    - `subclass` (from the controlled vocabulary below)
    - `tags[]` (optional, topical)

    **`subclass` controlled vocabulary:**
    - proof_step: `setup, introduce_variable, apply_lemma, case_split,
      induction_step, contradiction_setup, algebraic_manipulation,
      substitute, bound_estimate, invoke_identity, conclude, other`
    - algorithm_step: `initialize, loop, branch, update, return, other`

    Steps may reference Level-1 nodes outside the parent
    (e.g. `proof_step uses Lemma 2.3`), but step-to-step edges across
    different parents are NOT permitted.

## Schema

<!-- The prompt-builder substitutes the canonical schema block below at
     extraction time (see src/schema_for_prompts.py: render_prompt). Edit
     src/node_types.py / src/edge_types.py — NOT this file — to change the
     schema. -->
{{SCHEMA_BLOCK}}

### Required node fields (every node)

- `id` — compact ID (see convention below)
- `type` — from the closed vocabulary in rule 7
- `name` — display name (canonical name from paper, e.g. "Brooks'
  Theorem", "Leftover Hash Lemma", "Discrete Fourier Transform")
- `statement` — VERBATIM source body, math-preserved per rule 5.
  This is core rule #1.
- `section` — plain section title (per rule 12)
- `origin` — `"paper"` or `"external"` (per rule 6)

### Optional node fields

- `statement_short` — LLM compression per core rule #2. Always emit
  for proofs; almost always for algorithms; selectively for
  theorem-likes and definitions.
- `origin_citation` — required when `origin="external"`
- `assumptions[]`, `conclusions[]` — for theorem-like nodes
  (theorem/lemma/proposition/corollary/claim/conjecture). **Each
  element is a VERBATIM SPAN** from the source — not paraphrased.
  Required when the extractor can decompose; absent only when the
  statement structure resists clean decomposition. **NOT used for
  `definition` nodes** (definitions are stipulative, not if-then).
- `input[]`, `output[]` — for `algorithm` nodes. List of verbatim
  input/output description strings, one per element. Drop the
  `pseudocode` field — verbatim algorithm body lives in `statement`,
  decomposed steps live in `algorithm_step` children.
- `definiendum`, `genus`, `differentia[]` — for `definition` nodes only
  (see "Definition decomposition" below).
- `confidence` — REQUIRED on every node (float 0-1). How much *judgment* the
  node required — NOT how rigorous the maths is (that is `rigor`):

  | `confidence` | when |
  |---|---|
  | `1.0` | lifted from an explicit environment (`\begin{theorem}`, `\begin{definition}`) — no judgment |
  | `0.85`–`0.95` | explicitly labelled in prose ("Theorem 3 states that…", "We define X as…") |
  | `0.6`–`0.8` | **promoted from prose** — the content is genuinely asserted, but its type and span boundaries are your judgment |
  | below `0.6` | do not emit the node |

  Be honest here: prose promotions are the most useful thing this field
  records. Do not inflate them to 1.0.
- `parent_id`, `proves` — relational pointers
- `tags[]` — topical labels only (per rule 11)
- `proof_strategy[]` — proof strategy labels, on `proof` nodes only
  (per rule 11)
- `subclass` — on step nodes only, from controlled vocabulary

### Assumption / conclusion decomposition (theorem-likes)

When you split a verbatim statement into `assumptions[]` and
`conclusions[]`, you are **selecting spans from the verbatim text** —
not paraphrasing it. The union of the spans should reconstruct the
mathematical content of the statement; the wording must match the
source.

### Definition decomposition — definiendum / genus / differentia (definitions)

For `definition` nodes, optionally decompose the definition in the
classical (Aristotelian) way — this is the bridge to Mathlib concept
structure (genus = Lean base class, differentia = the mixin). All three
fields are **optional and best-effort**; emit them when the definition
has a clear "X is a Y that satisfies Z" shape, and omit any that do not
apply. They do **not** replace `statement` (which stays verbatim).

- `definiendum` — the term being defined (the head noun / name). Prefer a
  verbatim span; a canonicalized name is acceptable.
- `genus` — the parent category the definiendum belongs to. Prefer a
  verbatim span from the definition body.
- `differentia[]` — the distinguishing conditions that separate it within
  the genus, one per element, each a **verbatim span** where possible.

Examples:
- "A **field** is a **commutative ring** in which **every nonzero element
  is invertible**." → `definiendum="field"`, `genus="commutative ring"`,
  `differentia=["every nonzero element is invertible"]`.
- "A **Banach space** is a **normed vector space** that is **complete**."
  → `definiendum="Banach space"`, `genus="normed vector space"`,
  `differentia=["complete"]`.

When a definition is purely stipulative notation with no genus ("Let
$X := \{...\}$"), omit `genus`/`differentia` and keep only `statement`
(and `definiendum` if a name is introduced).

- **Regime A — explicit if/then.** Statement contains "if X, then Y"
  / "let X. Then Y" / "suppose X. Y". Copy the antecedent span(s) into
  `assumptions`, the consequent span(s) into `conclusions`.
  Example: *"If $X \sim \mathcal{N}(0,1)$ and $t > 0$, then $P(X > t)
  \le e^{-t^2/2}$."* →
  `assumptions: ["$X \sim \mathcal{N}(0,1)$", "$t > 0$"]`,
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

### Edge coverage — find the edges that exist, invent none

Two failure modes matter equally. Do not trade one for the other.

**Under-linking (the common failure).** Earlier runs left ~37% of nodes with
no edge at all, which makes the graph useless for dependency reasoning. This
was almost always laziness, not genuine isolation: in a mathematics paper a
definition that is never used anywhere is *rare*. So before you finish, sweep
every node and ask "does the paper actually relate this to something?" — in
particular:
  - each `definition`: which later statement or definition uses this concept?
    (definition chains are real structure: `flow → subflow → minimal flow`)
  - each `proof`: it MUST have a `proves` edge to what it proves;
  - each theorem-like node: which definitions/assumptions/lemmas does its
    statement invoke?
  - each `example`: what concept does it illustrate?

**Over-linking (the failure the sweep can cause).** Never invent a
relationship to make a node non-isolated. A node with no real relationship
should stay isolated — that is a correct output, not a defect. Do NOT treat
"every node has an edge" as a target to hit.

**Resolve the tension with `confidence`, not by guessing.** Emit the edge and
score it, so downstream consumers can filter instead of trusting a binary call:

| `confidence` | when |
|---|---|
| `0.9`–`1.0` | the text explicitly cross-references it (`by Lemma 3`, `\ref{}`), or it is a `proves`/`parent` structural fact |
| `0.7`–`0.85` | no explicit reference, but the logical dependency is clear-cut (the statement uses a term this definition introduces) |
| `0.5`–`0.65` | plausible but genuinely uncertain — emit only if you actually believe it |
| below `0.5` | do not emit |

Report your orphan count in the final summary, with a one-line reason for any
node you deliberately left isolated.

These are the ONLY valid edge types (canonical source: `src/edge_types.py`) —
do not invent others (e.g. there is no `defines` and no `special_case_of`; a
definition→user link is just `uses`, and "special case" is `specializes`).

**ONE RULE FOR EVERY EDGE — no exceptions:**

> The arrow points **from the thing that comes first / is relied upon**
> (`source`) **to the thing that relies on it** (`target`).
> Equivalently: `source` supports `target`; `target` depends on `source`.

Apply that single rule and the direction is always determined. The table gives
the required NODE TYPE at each endpoint so you can check yourself.

| Edge type | `source` (relied upon) | `target` (relies on source) | Reading |
|---|---|---|---|
| `uses` | any | any | target uses source (generic dependency, the default) |
| `specializes` | any (general) | any (specific) | target is a special case of source |
| `generalizes` | any (specific) | any (general) | target is a generalization of source |
| `proves` | `proof` | theorem-like | the theorem's validity rests on the proof |
| `solves` | `problem` | `algorithm` | the algorithm addresses the problem |
| `illustrates` | any (the concept) | `example` | the example depends on the concept it shows |
| `tests` | any (the concept) | `exercise` | the exercise depends on the concept it tests |
| `resolves` | `open_problem` / `conjecture` | theorem-like | the theorem settles the open problem |

(theorem-like = theorem, lemma, proposition, corollary, claim.)

**Every edge has exactly four fields: `source`, `target`, `type`, `confidence`.**
`confidence` is REQUIRED (float 0-1, scored per the table above) — it is how you
express uncertainty instead of silently dropping or inventing an edge.

**Worked examples — copy these shapes exactly:**
- definition DF1 used by theorem TH1, explicit `\ref` in the text:
  `{"source": "DF1", "target": "TH1", "type": "uses", "confidence": 0.95}`
- proof PP1 of theorem TH1 (structural fact):
  `{"source": "PP1", "target": "TH1", "type": "proves", "confidence": 1.0}`
- example EX1 illustrating definition DF1:
  `{"source": "DF1", "target": "EX1", "type": "illustrates", "confidence": 0.9}`
- algorithm AP1 solving problem PR1:
  `{"source": "PR1", "target": "AP1", "type": "solves", "confidence": 0.9}`
- theorem TH2 resolving open problem OP1:
  `{"source": "OP1", "target": "TH2", "type": "resolves", "confidence": 0.8}`
- definition DF2 whose statement uses a term DF1 introduces, no explicit ref:
  `{"source": "DF1", "target": "DF2", "type": "uses", "confidence": 0.75}`

The resulting graph must be a DAG: every arrow points from earlier/relied-upon
to later/dependent, so there can be no cycles.

**Theorem/definition → algorithm dependency:** when a paper introduces
a theorem (e.g. existence of a factorization) and an algorithm that
computes it, the theorem is a prerequisite of the algorithm:
`theorem → algorithm` with type `uses`. Same for definitions.

## Workflow

1. Read the `.tex` file (multiple Read calls with offsets if large).
2. Identify all definitions, theorems, lemmas, propositions,
   corollaries, algorithms, examples, problems, remarks.
3. Assign compact IDs in source order per type.
4. For each node:
   a. **COPY** the source body into `statement` (verbatim, LaTeX
      preserved, JSON-escaped). Core rule #1.
   b. **WRITE** a 1-sentence `statement_short` per core rule #2
      (always for proofs and algorithms; selectively elsewhere).
   c. Set `origin` ("paper" or "external"). Required.
   d. Set `name` to the canonical name from the paper.
   e. Set `section` to the plain section title (no labels, no parens).
   f. For theorem-likes, decompose into `assumptions[]`/`conclusions[]`
      (verbatim spans).
   g. For algorithms, populate `input[]`/`output[]` (verbatim spans).
   h. For proofs, populate `proof_strategy[]` from the controlled
      vocabulary.
   i. Populate `tags[]` with topical labels only.
5. Apply step extraction (rule 13) for proofs and algorithms.
6. Apply type-promotion (rule 7).
7. Build edges from explicit cross-references and clear logical
   dependencies.
8. Write the JSON to OUTPUT_JSON:

   ```json
   {
     "metadata": {
       "title": "...",
       "paper_num": N,
       "annotator": "agent-extraction",
       "model": "claude-opus-4-7",
       "prompt_version": "v5",
       "extraction_date": "YYYY-MM-DD"
     },
     "nodes": [...],
     "edges": [...]
   }
   ```

## Pre-output self-check (MANDATORY)

Before emitting the JSON, walk every node and verify:

1. **`statement` is verbatim.** Open the source `.tex` at the node's
   section, find the originating `\begin{X}...\end{X}` block (or
   surrounding prose), and confirm `statement` is the body of that
   block **verbatim**, with:
   - All math preserved (`$..$`, all backslashes, all subscripts).
   - All hypotheses preserved (no dropped "Let X be..." clauses).
   - All named objects preserved (no generic substitutions).
   - Only mechanical cleanup applied (whitespace, comments, `\label`).
2. **`statement_short`, when present, is meaningful compression** —
   NOT a copy-paste of `statement`, NOT longer than `statement`,
   captures the idea. For proof nodes, verify `statement_short`
   exists.
3. **`origin` is set on every node.** No nulls, no missing keys.
4. **`section` is clean** — plain title, no `\label`s, no `(cited)` /
   `(alg:...)` parens.
5. **`type` is in the closed vocabulary** (rule 7). No invented types.
6. **`tags[]` is topical only.** Strategy labels live in
   `proof_strategy[]` on proof nodes.
7. **Theorem-like nodes have `assumptions[]`/`conclusions[]`** unless
   the statement structure genuinely resists decomposition (rare).
   Definitions do NOT have these.

If you cannot point to the exact span in the source that a `statement`
was copied from, the node is invalid.

## Report (<200 words)

When complete, output:
- node count by type (e.g. "8 definition, 1 theorem, ...")
- **step counts per parent**: for each `proof` and `algorithm` node,
  report `<parent_id>: N steps` (e.g. `PP1.1: 4 steps`). If N=0,
  justify in one phrase ("single-paragraph body, no part/step labels").
- **`statement_short` coverage**: percentage of nodes that have a
  populated `statement_short`. Expected: 100% for proofs, ~80%+ for
  algorithms, 30–70% for theorem-likes, low for definitions/remarks.
- edge count by type
- count of `origin: "external"` nodes
- 3 sample node names (drawn from the body)
- any anomalies (missing names, ambiguous structure, source spans
  that were hard to copy verbatim — e.g. heavy macro use)
- confirmation: "All `statement` fields are verbatim copies of source
  spans; no paraphrasing applied to `statement`. `statement_short`,
  where populated, is LLM-derived compression."
