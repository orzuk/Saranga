<!-- CANONICAL: src/node_types.py and src/edge_types.py.
     This file is derivative; sync it whenever the canonical changes. -->

Extract a mathematics paper or chapter to JSON for the SARANGA project.

**What you are producing.** A typed directed graph of the paper's mathematical
content. Nodes are the paper's statements — theorems, definitions, proofs,
algorithms, and the Level-2 sub-steps that decompose proofs and algorithms —
each carrying a `statement` field copied verbatim from the source `.tex` plus
the structured fields listed under "Schema". Edges are typed dependencies
between nodes. The closed node-type and edge-type vocabularies are given in
the Schema section; read it before you begin.

This prompt is the **v6 EXTRACTION-ONLY** variant. It has TWO core rules.

**Core rule #1 — `statement` is a VERBATIM COPY** from the source `.tex`,
LaTeX preserved exactly. No paraphrase, no summary, no rewording.
A verbatim span can be located in the source and compared with any
other span; a paraphrase cannot, and the loss is silent.

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

## Two layers: LaTeX facts first, then your judgment

Part of this paper's structure is stated by LaTeX syntax, and a parser reads
it exactly. Run it before anything else:

    python3 /mnt/c/Code/Github/Saranga/src/latex_facts.py {TEX_SOURCE} --out <scratch>/facts.json

`facts.json` gives you:
- `source`: the CLEANED source (comments, `\iffalse`/`\if0` regions, `comment`
  environments and everything after `\end{document}` removed). Slice every
  verbatim field from this text, never from the raw `.tex`.
- `facts`: every theorem-like, proof, algorithm and labelled equation
  ENVIRONMENT, with its body span (`start`, `end`), the author's name for it
  (`display`) and the node type that name maps to (`type`, null when the name
  is not a standard one), its `\label`, its printed number, its section, and
  for proofs the result it proves where syntax says so (`proves`).
- `labels`, `refs`, `sections`: every `\label`, every `\ref`, every section.

For an environment fact, emit its node with exactly the fact's span. Confirm
or correct `type` (a `display` of "Fact" or "Property" is yours to classify,
and a cited result inside a theorem environment is still `origin: external`).

**The facts cover environments only.** Most definitions, remarks, claims and
problems in a paper are written in ordinary prose, with no environment, and
none of them is in `facts.json`. Finding them is your main job. Do not treat
the facts as the list of nodes; treat them as the part already done.

You do not fill `label` or `source_line_label`, and you do not add the
`uses` edges that a `\ref` states or the `proves` edges that syntax states:
the pipeline adds them in the last step (see Workflow). You add every
dependency that has no `\ref`.

## Schema

<!-- The prompt-builder substitutes the canonical schema block below at
     extraction time (see src/schema_for_prompts.py: render_prompt). Edit
     src/node_types.py / src/edge_types.py — NOT this file — to change the
     schema. -->
NODE TYPES (16 Level-1, 2 Level-2):

Theorem-like (6): theorem, lemma, proposition, corollary, claim, conjecture.
Carry assumptions and conclusions field splits.

Foundational (2): definition, proof.

Pedagogical (2): example, exercise.

Other content (6): problem, open_problem, assumption, equation, algorithm, remark.

Level-2 sub-block (optional, 2): proof_step, algorithm_step.

EDGE TYPES (7): uses, generalizes, specializes, proves, illustrates, tests, resolves.
Direction: A → B reads "B [edge] A" (B depends on A).

(See src/node_types.py for full per-type docstrings and tags vocabulary.)

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
- `rigor` — OPTIONAL, **default `formal`**. Omit it on any node whose
  statement is precise and whose justification is a rigorous proof.
  That is the common case, so most nodes carry NO `rigor` field. Add it
  only when the node departs from that:

  | value | when |
  |---|---|
  | `semi_formal` | precise statement, but a proof sketch or an appeal to "standard arguments" |
  | `heuristic` | believed true on physical or intuitive grounds, no proof offered |
  | `numerical` | supported by simulation or computation only |
  | `conjectural` | stated with no justification at all |

  Judge the **justification**, not the node's type or the paper's arXiv
  category. A `theorem` with a hand-waved proof is `semi_formal`; a
  `remark` carrying a full proof gets no `rigor` field. Do not infer
  rigor from the category: two papers in the same category can differ
  completely, so read each node's own justification.

  Emit `metadata.rigor_nonformal_count` = the number of nodes you gave a
  `rigor` field. `0` is a valid and meaningful answer: it records that
  you applied the rule and found everything formal. A MISSING key means
  you skipped the rule, which is not acceptable.
- `label` — the `\label{...}` key of the environment this node came
  from. Filled by the pipeline from `facts.json`; do not set it.
- `confidence` — REQUIRED on every node (float 0-1). How much *judgment* the
  node required — NOT how rigorous the maths is (that is `rigor`, above):

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

## CORE RULE #1 — `statement` IS A COPY, NOT A SUMMARY

For every node, the `statement` field must be the **verbatim text of
the corresponding block in the source `.tex`**, with LaTeX preserved
exactly. You are acting as a structured **extractor**, not as a writer,
editor, or summarizer.

The ONLY edits permitted to the source text are mechanical cleanup that
does not change wording:

- Collapse runs of whitespace and newlines into single spaces.
- Strip LaTeX comments (`% ...` to end of line), TeX-disabled regions
  (`\iffalse ... \fi`, `\if0 ... \fi`, `\begin{comment}`), and everything
  after `\end{document}`. `facts.json`'s `source` has already done this.
- Drop `\label{...}` and `\index{...}` commands.
- Keep `\ref{...}`, `\eqref{...}`, `\cite{...}` and their variants exactly as
  written: the pipeline turns each `\ref` into an edge.
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
derived and lossy, and is never the source of record. `statement` is
the source of record.

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
   the way THIS paper states the cited result. It may differ from the
   original source's phrasing; that is fine — record how THIS paper
   states it.

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

10. **ACYCLICITY, WITH BACKWARD EDGES FLAGGED.** A `uses` edge `A → B` reads
    "B uses A". Some real dependencies point against the paper's order: a
    proof that cites "Remark 5 below", or an induction step that applies the
    theorem itself at a smaller case. NEVER delete such an edge to avoid a
    cycle. Keep it and add `"backward": true`. The graph with the backward
    edges removed must be acyclic. No reciprocal `uses` edges between the
    same pair.

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

## Level-2 steps — proof_step and algorithm_step

Step decomposition is a **parallel structural extraction**, not a substitute for
the parent's body. The parent `proof` / `algorithm` `statement` MUST hold the
full verbatim body (core rule #1) AND the step nodes are emitted alongside it.

### When to emit a `proof_step`

A step is one move of the argument: an object is introduced, a case is opened, a
lemma or inequality is applied, a bound is established, an intermediate claim is
proved, or the conclusion is drawn. Most steps carry no marker ("Let", "By",
"Since", "Now"…); do not wait for one. Apply the rules below in order.

**1. Author labels (from `facts.json`).** Each proof fact carries
`structure.labels`: the places where the paper itself labels its structure,
already detected by the parser (anchored `Step N`, `Case N`, `Part N`, `(i)`/`(a)`
item labels, `1.` after `\smallskip`/`\par`/a blank line, prose items of a list
inside the proof, `\textbf{...}`/`\emph{...}` headings, Base case / Inductive step,
nested `\begin{proof}`). Every one of them starts a step; never merge two labels.
Keep the label token in the step's `statement` (strip only `\item`). The
post-pass checks this. A label body longer than 2 sentences gets CHILD steps
(`parent_id` = the label's step), segmented by the rules below. Text before the
first label is its own `setup` step.

**2. Steps end only at sentence ends.** A boundary falls after a `.`, `!`, `?` or
`:` outside math, or at a label. Never inside a display, at a comma, at `;`, or
before "where", "which", "because" continuing the same sentence. The post-pass
checks this.

**3. Paragraph breaks are a strong hint.** `structure.paragraph_breaks` lists the
breaks that follow a complete sentence. Such a break normally starts a new step;
merge across it only when the next paragraph plainly continues the same move.
(Blank lines around a displayed equation are layout, not structure, and are not
listed.)

**4. Introductions group.** A run of consecutive sentences that only introduce
objects (start with Let, Take, Consider, Define, Fix, Denote, Set, and contain no
`\ref`, `\cite`, display, or hence/so/then/thus) is ONE `introduce_variable`
step. A run of a single such sentence is joined to the step that follows it.

**5. Meta, reduction and recall form `setup` steps.** A sentence that starts with
or contains "it suffices to", "it is enough to", "it remains to", "we only need
to", "the proof is (similar|analogous) to", "is proven exactly as", "we will use",
"recall", "we have remarked" is a `setup` step. A contiguous restatement of a
definition or a cited theorem (including a theorem-like environment quoted inside
the proof) is ONE `setup` step; do not segment inside it.

**6. Immediate sentences never stand alone.** A sentence is immediate when it has
no display and no `\ref`/`\eqref`/`\cite`, and contains one of: clear(ly),
obvious(ly), trivial(ly), immediate(ly), at once, easy/easily, straightforward,
tautological, by inspection, similarly, a similar argument, the same argument, as
above, we can verify, left to the reader; or is a closing formula ("This
completes / finishes / proves the …", `\qed`). An unlabelled immediate sentence
is appended to the preceding step, or, if it comes first in the body or label,
prepended to the following step. A case opener (rule 8) is never immediate.

**7. Inline claims nest.** A sentence matching "We claim", "I claim", "Claim",
"Let us (show|prove|check)", "(First|Next|Now), we (show|prove|check)", "We show
this by" opens a parent step (`structure.claims` lists the ones the parser
found). The following sentences are its children, up to and including the first
sentence matching "(proves|completes|establishes) the claim", "This proves", "Now
that", "as claimed", or the end of the enclosing label. Nesting is REQUIRED when
at least 2 sentences follow the opener.

**8. Case splits.** A case opener is a sentence starting with (So )?(first
)?(Suppose|Assume|If|Let us assume) when a later sentence starts with "If
instead", "Otherwise", "For the case", "In the (other|remaining) case",
"Secondly, if", "Note that if". Each opener starts a `case_split` step. Add a
conclusion step only if a reunion sentence exists ("In (either|both|all)
case(s)", or Thus/Hence after the last case). Cases stated inside one sentence
("either …; or …") stay one step. "Without loss of generality" is `setup`, not
a case. Induction ("Base case: … Inductive step: …") gives at least two
`induction_step` steps.

**9. Short proofs.** Emit ZERO steps when the body has at most 2 sentences outside
displays and no label. Never emit exactly one step: a body that is one move gets
zero.

### When to emit an `algorithm_step`

As with theorem-likes, the source may or may not mark the structure for you.
Extract in both cases; only `confidence` differs.

*Marked up* — `\begin{algorithmic}`, a numbered `\begin{enumerate}`, a listing,
or any body whose lines the paper numbers. One step per line, including control
keywords the paper numbers (`\REPEAT`, `\ELSE`, `\ENDIF`), since prose cites
them ("by line 7"). A loop or branch header is its own step, separate from the
lines in its body. Skip comments, blank lines and the caption. `confidence`
0.9–1.0.

Do NOT fill `source_line_label` yourself. The printed line numbers are not in
the source; LaTeX computes them. Your builder script must call the pipeline's
line numberer before the final write:

    import sys; sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
    from algorithm_lines import fill_source_line_labels
    report = fill_source_line_labels(graph, tex_source)
    assert not report["merged"], report["merged"]

It sets `source_line_label` on every `algorithm_step` it can place (null where
the paper does not number its lines). A `merged` entry means one of your steps
spans several printed lines: split it into one step per line and re-run.

*Unmarked* — an `\begin{algorithm}` float containing prose, or a procedure
described in running text ("first we construct…, then for each component we…").
One step per operation the description performs; segment on operations, not on
sentences. `confidence` is 0.6–0.8, since the step boundaries are your judgment.

Unmarked procedures are at least as common as marked-up ones. Do NOT skip an
algorithm, or decline to decompose it, because it has no `\STATE` markers — an
unmarked procedure is still an algorithm, exactly as an unwrapped assertion is
still a theorem.

**Markup in a step's `statement`.** Copy the line's CONTENT, not its LaTeX
wrapper: for `\STATE {Initialize $v \leftarrow v_0$.}` the `statement` is
`Initialize $v \leftarrow v_0$.` Math and all other LaTeX inside the content are
preserved verbatim as always. The same applies to `\item` in an enumerated
procedure. Keep the control word itself when it IS the line
(`\WHILE{not converged}` -> `while not converged`), since that line carries the
loop condition.

### Verbatim requirement

Each step's `statement` is ALSO verbatim — copy the sentence(s) or pseudocode
line(s) from the source body that constitute that step. Each step's
`statement_short` is your compression of that step's role ("Set up induction on
$n$", "Apply Cauchy-Schwarz", "Conclude by Markov's inequality").

### Worked example — a labelled proof

Source body:

```
Part (1): By the definition of $d_i$, $f' L f = ...$ which yields
the quadratic form.
Part (2): The symmetry of $L$ follows directly from $W$ and $D$.
Positive semi-definiteness follows from Part (1).
Part (3): Obvious.
```

Required output: ONE `proof` node whose `statement` is the full verbatim body
(`statement_short` e.g. "Direct expansion + symmetry"), PLUS THREE `proof_step`
nodes, each with `statement` = the verbatim text of its "Part (N):" sentence(s),
`statement_short` = the step's role, `parent_id` pointing to the proof, and
`subclass` from the canonical set.

### Worked example — an unlabelled proof

Source body:

```
Take a vertex $v \in \cap_{n\geq 1} V(w_n)$. Let $P_n$ be the set of
paths of length $n$ ending at $v$. Since each $P_n$ is finite and
non-empty, Konig's lemma gives an infinite path. This path witnesses
the claim.
```

No `Part`, no `Case`, no `Step` — and it is still three moves: introduce $v$ and
$P_n$; apply Konig's lemma; conclude. Emit three `proof_step` nodes. A rule that
waited for a label would emit none, which is the common failure.

**Step-node fields:**
- `id` (e.g. `PSP5.1`, `ASP5.1` for paper 5 step 1)
- `type` (`proof_step` or `algorithm_step`)
- `parent_id` (id of the parent node — see NESTING below)
- `step_order` (1-based index within the IMMEDIATE parent)
- `source_line_label` (`algorithm_step` only; the line number the PDF
  prints for this line. Filled by `fill_source_line_labels` in your builder
  script, never by hand, and never derived from `step_order`.)
- `name` (a short descriptive label)
- `statement` (verbatim source span for this step)
- `statement_short` (LLM compression of the step's role)
- `subclass` (from the controlled vocabulary below)
- `tags[]` (optional, topical)

**NESTING — steps may parent other steps.** A step node MAY take
another step node as its `parent_id`, to any depth:
- `proof_step` — a label body longer than 2 sentences (rule 1), an
  inline claim with at least 2 following sentences (rule 7, REQUIRED),
  a `\begin{proof}` inside a proof, a "Proof of Claim N" block.
- `algorithm_step` — loop and branch bodies are CHILDREN, not
  siblings. A line inside a `\FOR` / `\WHILE` / `\IF` block takes
  that block's step as its `parent_id`, following the source's block
  structure.

`step_order` restarts at 1 within each parent, so an outer loop's
body is 1,2,3… not a continuation of the outer numbering.

**`subclass` controlled vocabulary.** The two vocabularies are
DISJOINT — never use a proof_step value on an algorithm_step or
the reverse.
- proof_step: `setup, introduce_variable, apply_lemma, case_split,
  induction_step, contradiction_setup, algebraic_manipulation,
  substitute, bound_estimate, invoke_identity, conclude, other`
  Glosses: `setup` = recall, reduction, meta-pointer, WLOG, text before the
  first label · `introduce_variable` = Let/Take/Define/Consider/construct,
  including a construction "as follows" inside a proof (which stays
  proof_steps, not an algorithm) · `case_split` = every step that opens a case ·
  `induction_step` = base case and inductive steps, including structural
  induction cases that use the hypothesis · `conclude` = only the last step of
  the body, of a label, or of a claim.
- algorithm_step — choose the most specific that applies:
  `initialize` set up state before the main body ·
  `loop` a `\FOR`/`\WHILE`/`\REPEAT` header ·
  `branch` an `\IF`/`\ELSE`/`\CASE` header ·
  `test` evaluate a condition or convergence criterion ·
  `compute` a calculation or assignment ·
  `select` choose or identify an element / index / candidate ·
  `filter` discard, prune, or restrict a set ·
  `solve` solve a subproblem, system, or optimisation ·
  `call` invoke another algorithm or named subroutine ·
  `update` modify existing state — use ONLY when none of the above
  fits. This is the easiest label to over-apply: a step that
  computes, selects, filters or solves is NOT an `update`. Reach
  for it last, not first. ·
  `return` output or terminate · `other` none of the above

Steps may reference Level-1 nodes outside the parent
(e.g. `proof_step uses Lemma 2.3`), but step-to-step edges across
different parents are NOT permitted.

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
score it, so a reader can filter on the score instead of trusting a
yes/no call:

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
| `illustrates` | any (the concept) | `example` | the example depends on the concept it shows |
| `tests` | any (the concept) | `exercise` | the exercise depends on the concept it tests |
| `resolves` | `problem` / `open_problem` / `conjecture` | theorem-like / `algorithm` | the theorem settles the question, or the algorithm solves the problem |

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
  `{"source": "PR1", "target": "AP1", "type": "resolves", "confidence": 0.9}`
- theorem TH2 resolving open problem OP1:
  `{"source": "OP1", "target": "TH2", "type": "resolves", "confidence": 0.8}`
- definition DF2 whose statement uses a term DF1 introduces, no explicit ref:
  `{"source": "DF1", "target": "DF2", "type": "uses", "confidence": 0.75}`

The graph without its `backward: true` edges must be a DAG: every other arrow
points from earlier/relied-upon to later/dependent.

**Theorem/definition → algorithm dependency:** when a paper introduces
a theorem (e.g. existence of a factorization) and an algorithm that
computes it, the theorem is a prerequisite of the algorithm:
`theorem → algorithm` with type `uses`. Same for definitions.

## Workflow

0. Run `latex_facts.py` (see "Two layers") and read `facts.json`.
1. Read the cleaned `source` (multiple Read calls with offsets if large).
2. Emit a node for every environment fact. Then find everything the facts
   do not cover: definitions, results, remarks, claims, problems and
   algorithms stated in prose.
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
5. Apply step extraction for proofs and algorithms (see "Level-2 steps").
6. Apply type-promotion (rule 7).
7. Build edges for logical dependencies that have no `\ref`. (Edges a `\ref`
   states are added by the pipeline in step 8.)
8. In your builder script, finish and check the graph before writing it:

       import sys; sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
       from extraction_finalize import finalize
       report = finalize(graph, raw_tex)
       assert not report["errors"], report["errors"]

   It fills `label` and `source_line_label`, writes the paper's full `\label`
   table to `metadata.labels` (so every `\ref` kept in a statement resolves),
   adds the `\ref`-stated `uses` edges and syntax-stated `proves` edges, and
   validates (verbatim spans,
   edge types and endpoints, acyclicity, step parents). Fix every error and
   re-run. A `\ref` that points backward is added with `"backward": true`;
   list `report["ref_backward"]` in your final report.
9. Write the JSON to OUTPUT_JSON:

   ```json
   {
     "metadata": {
       "title": "...",
       "paper_num": N,
       "annotator": "agent-extraction",
       "model": "{MODEL}",
       "effort": "{EFFORT}",
       "prompt_version": "v6",
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
