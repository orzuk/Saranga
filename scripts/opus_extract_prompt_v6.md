<!-- CANONICAL: src/node_types.py and src/edge_types.py.
     This file is derivative; sync it whenever the canonical changes. -->

Extract a mathematics paper or chapter to JSON for the SARANGA project.

**What you are producing.** A typed directed graph of the paper's mathematical
content. Each node is one statement of the paper (a definition, a
theorem or other result, a proof, a proof step, an equation, an algorithm, a
remark, ...), of exactly one type from the closed vocabulary under "Schema"
below, and carries a `statement` copied verbatim from the source plus the
fields listed there. Nodes nest: a node that lies inside another (a
proof step in its proof, an equation in a theorem, a lemma inside a proof) is
part of it, recorded by `parent_id`. Edges are typed dependencies between
nodes, from the closed edge vocabulary. Read "Schema" before you begin. (In
these instructions, a *section* is always a section of the paper; parts of the
instructions are named by their headings in quotes.)

**Terms used below.**
- *Prepared source*: the paper's text as `latex_facts.py` delivers it in
  `facts.json` (see "Two layers"). Everything you copy comes from it.
- *Span*: one contiguous piece of the prepared source.
- *`latex_facts.py`*: a command in `{REPO}/src/` that you run first; it reads
  the LaTeX syntax and writes `facts.json` (see "Two layers").
- *Finishing step*: the function `finalize()` in `{REPO}/src/extraction_finalize.py`,
  which your build script calls last (Workflow step 8): it fills some fields
  and edges and checks your graph.
- *Environment node*: a node taken from an environment the facts report (`\begin{theorem}`...). 
  *Prose node*: a node you find in running text, whose boundaries are your judgment.
- *Level-2 nodes* are the steps, `proof_step` and `algorithm_step`; every other node is *Level-1*.
- *Result*: a node of type theorem, lemma, proposition, corollary or claim
  (what a proof proves). A `conjecture` is stated like a result but unproven;
  an `open_problem` is a question, not a statement. Both can be resolved by a result.
- *Hard rule N* is rule N under "HARD RULES"; *step rule N* is rule N under
  "When to emit a `proof_step`".
- *Orphan*: a node with no edge and no `parent_id` (a step or a nested equation
  is tied to the graph by its parent, not by edges).

There are two core rules:

**Core rule #1 — `statement` is a verbatim copy** from the prepared source,
LaTeX preserved exactly.

**Core rule #2 — `statement_short` is your compression**, populated
whenever a meaningful short version exists: one sentence, or two for a long
proof or algorithm (see "CORE RULE #2"). For proofs especially,
`statement_short` should capture the strategy ("By induction on $n$",
"Density-increment iteration").

## This paper

The paper you extract in this run, and where its files are:

- ARXIV ID: {BID}
- TITLE: {TITLE}
- AUTHORS: {AUTHORS}
- YEAR: {YEAR}
- LATEX SOURCE (input): {TEX_SOURCE}
- OUTPUT FILE (write your JSON here): {OUTPUT_JSON}
- CODE (the Saranga repository, with the tools below): {REPO}

## Two layers: LaTeX facts first, then your judgment

Part of this paper's structure is stated by LaTeX syntax, and a parser reads
it exactly. Run it before anything else (`<scratch>` is any scratch directory):

    python3 {REPO}/src/latex_facts.py {TEX_SOURCE} --out <scratch>/facts.json

`facts.json` gives you:
- `source`: the prepared source: `\input`/`\include` files inlined, the
  paper's own argument-free macros expanded (`\gr` becomes `\Gamma`), and
  comments, `\iffalse`/`\if0` regions, `comment` environments and everything
  after `\end{document}` removed. Slice every verbatim field from this text,
  never from the raw `.tex`: the finishing step checks statements against it.
- `facts`: every theorem-style environment (`\newtheorem` ones: theorem,
  lemma, definition, remark, ...), proof, algorithm and numbered equation, 
  with its body span (`start`, `end`), the author's name for it
  (`display`) and the node type that name maps to (`type`, null when the name
  is not a standard one), its `\label`, its printed number, its section (an
  `id` in `sections`; a node's `section` field is that entry's number and
  title, e.g. "3 Monotonic Improvement"), and
  for proofs the result it proves where syntax says so (`proves`) and the
  proof's own structure (`structure`: the author's step labels, inline claims
  and paragraph breaks; see the step rules); for pseudocode algorithms, its
  printed lines (`lines`; see "When to emit an `algorithm_step`").
- `labels`, `refs`, `sections`: every `\label`, every `\ref`, every section
  heading (with `inside`: the environment it sits in, or null for a heading of
  the paper itself).

For an environment fact, emit its node with exactly the fact's span. That
includes every numbered equation (labelled or not), wherever it sits: inside a
theorem, a proof or a definition it is still its own `equation` node, because
the paper can cite it as "(3.2)". An unnumbered displayed equation (`\[...\]`, `$$...$$`,
`equation*`, `align*`) is not a node of its own: like inline math, it is part
of the text of the node that contains it. Confirm or correct `type`
(a `display` of "Fact" or "Property" is yours to classify; when `type` is null,
choose the type by content, Hard rule 4, and an environment with no
mathematical content, such as acknowledgements, gets no node; a cited result
inside a theorem environment is still `origin: external`, Hard rule 3). A numbered equation
stays `equation` unless the text names it as a result ("Weyl's relation", "the
Ehrenfest theorem"); then it takes that type (a cited result: `theorem`,
`origin: external`), confidence `0.9` (see `confidence` under Schema).

**The facts cover environments only.** Definitions, results, remarks and
problems stated in running text are not in `facts.json`. Read the whole paper
and find what it states in prose, however much or little that is.
Add the prose nodes that the rules under "Where a prose node starts and ends"
give, and only those.

The finishing step fills `label`, `source_line_label`, `backward` and the
`parent_id` of Level-1 nodes, and adds the `uses` edges that a `\ref` states
and the `proves` edges that syntax states; leave these out. You add every
dependency that has no `\ref`.

**The graph is a hierarchy.** `parent_id` means "is part of": every node is
either top-level or has exactly one parent, the innermost node whose statement
contains its own. A proof step belongs to its proof (or to a parent step); an
equation to the theorem, proof, definition or step it sits in; a lemma stated
inside a proof to that proof, and so does that lemma's own proof. For Level-1
nodes the finishing step computes `parent_id` from the spans; you set it only for
steps, by the nesting rules. Never draw a `uses` edge to express containment.

## HARD RULES

1. **You decide what is a node by reading; scripts only move text.** Read the
   prepared source with the Read tool (with offsets for large files) and decide
   each node, its type and its span by reading it. Scripts are for slicing the
   spans you chose out of the source, building the JSON, and running the
   finishing step. Never let a regex decide what is a node: do not write a
   script that greps for "Theorem N.M" or "we define" and emits whatever matches.
   (The environment facts are the one exception, and `latex_facts.py` provides them.)

2. **Preserve canonical names.** When the paper introduces a named
   object ("Sinkhorn-Knopp algorithm", "Markov's inequality", "PCA"),
   use that exact name in the `name` field: `name` is how the node is
   matched to the same result in other papers.

3. **`origin` is required on every node:**

   - `"paper"` — node is a contribution introduced by this paper.
   - `"external"` — node is a cited prior result the paper uses but
     does not establish (classical theorems invoked, foundational
     definitions imported, baseline algorithms compared against).

   For `origin: "external"` nodes, also set `origin_citation` to a
   short free-text identifier ("Brooks 1941", "Davis & Kahan; Stewart
   & Sun 1990", "Impagliazzo, Levin, Luby", etc.).

   The `statement` field for an external node is still verbatim — copy
   the way this paper states the cited result, even where it differs
   from the original's wording.

   An uncited standard notion or folklore result is `external` with
   `origin_citation: "standard (uncited)"`. A result the paper attributes to
   others is `external` even if the paper re-proves it; that proof is `paper`.

   `external` marks a node that states a cited result ("Theorem 2.1 (Brooks
   [12]). Every connected graph ...", "As shown in [REF], every $X$ is $Y$.").
   A citation used inside an argument ("by X", "applying [REF]") creates no
   node: it stays in the text of the node that uses it (see "Where a prose
   node starts and ends").

4. **Closed node type vocabulary.** A node's `type` is determined by
   semantic content, not LaTeX environment, but the resulting type must
   come from the closed set listed under "Schema". Do not invent new types (`fact`, `property`, `observation`, etc).
   Map non-standard `\newtheorem{...}` environments to the closest
   standard type that fits its content.

   Type-promotion within the closed set:
   - A `\begin{definition}` whose body is an optimization formulation
     (e.g. `x^* = \arg\min_x f(x)`) → `type="problem"`, not `definition`.
   - A `\begin{definition}` whose body is a step-by-step procedure →
     `type="algorithm"`.
   - A `\begin{lemma}` whose body is a numerical bound used as
     scaffolding stays `lemma`.
   - A custom `\newtheorem{property}` or `\newtheorem{fact}` → `theorem` with
     `origin: external` if it states a cited result, otherwise `claim`.

5. **`problem` vs `open_problem` distinction:**
   - `problem` = a formally stated computational/optimization/decision
     problem the paper studies (e.g. "$\maximize_\theta L(\theta)$
     s.t. $D_{KL}(\theta_{old},\theta) \le \delta$", "3-SAT").
   - `open_problem` = an unresolved mathematical question with no known
     solution ("It is unknown whether...", "An important open question
     is...").

6. **Completeness: do not drop results.** Every numbered
   or labelled stated result in the paper must produce a
   result node (theorem, lemma, proposition, corollary or claim).

   **Do not demote a stated result to an `equation` node** even if the
   paper presents it inside `\begin{equation}...\end{equation}` blocks.
   If the prose says "the optimal $P^\lambda$ has the unique form
   $P^\lambda = \diag(u) K \diag(v)$ [Sinkhorn's theorem]" — that is a
   **theorem** with `origin: external`: the paper names it and states it in
   full (see "Type of a result stated in prose").

   Count of result nodes you emit ≥ count of numbered or labelled result
   environments in the source.

7. **Acyclicity, with backward edges flagged.** A `uses` edge `A → B` reads
    "B uses A". Some real dependencies point against the paper's order: a
    proof that cites "Remark 5 below", or an induction step that applies the
    theorem itself at a smaller case. Never delete such an edge to avoid a
    cycle. The finishing step marks it `"backward": true` by position (its source
    comes after its target in the paper). The graph
    with the backward edges removed must be acyclic. No reciprocal `uses` edges between the
    same pair.

8. **`tags[]` is topical only; `proof_strategy[]` is for proof strategy.**

    - `tags[]` on any node — topical/role labels:
      `existence, uniqueness, bound, identity, foundational, optimization,
      combinatorial, randomized, sampling, constrained_optimization,
      monotonic_improvement, ...` (open vocabulary, but semantically TOPICAL).
    - `proof_strategy[]` on `proof` nodes only — the strategy of the
      proof, controlled vocabulary:
      `induction, strong_induction, contradiction, minimal_counterexample,
      construction, probabilistic, case_analysis, density_increment,
      direct, contrapositive, dual_argument, geometric, algebraic_manipulation,
      compactness, fixed_point, other`.

    **Wrong:** putting `"contradiction"` in `tags[]` of a proof node.
    **Right:** `tags: ["graph_coloring"]`, `proof_strategy: ["contradiction", "minimal_counterexample"]`.

9. **`section` is the plain section title.** Do not include LaTeX labels,
    cross-reference identifiers, or parenthesized provenance markers.

    - **Wrong:** `"section": "3 Monotonic Improvement (alg:pialg)"`
    - **Wrong:** `"section": "1 (cited)"`
    - **Right:** `"section": "3 Monotonic Improvement"`
    - **Right:** `"section": "1 Introduction"` plus `"origin": "external"`
      on the cited node.

## Schema

<!-- The prompt-builder substitutes the canonical schema block below at
     extraction time (see src/schema_for_prompts.py: render_prompt). Edit
     src/node_types.py / src/edge_types.py — NOT this file — to change the
     schema. -->
{{SCHEMA_BLOCK}}

### Required node fields (every node)

- `id` — compact ID (see convention below)
- `type` — from the closed vocabulary in Hard rule 4
- `name` — display name (canonical name from paper, e.g. "Brooks'
  Theorem", "Leftover Hash Lemma", "Discrete Fourier Transform")
- `statement` — verbatim source body, math-preserved per core rule #1 ("LaTeX math").
  This is core rule #1.
- `section` — plain section title (per Hard rule 9)
- `origin` — `"paper"` or `"external"` (per Hard rule 3)
- `confidence` — float 0-1. How much *judgment* the
  node required — not how rigorous the maths is (that is `rigor`, below):

  | `confidence` | when |
  |---|---|
  | `1.0` | lifted from an explicit environment whose name gives the type (`\begin{theorem}`, `\begin{definition}`) — no judgment |
  | `0.9` | an environment whose type you chose or corrected (a non-standard name, a retyped equation) |
  | `0.85`–`0.95` | explicitly labelled in prose ("Theorem 3 states that…", "We define X as…") |
  | `0.6`–`0.8` | promoted from prose — the content is genuinely asserted, but its type and span boundaries are your judgment |
  | below `0.6` | do not emit the node |

  Do not round a prose node up to `1.0`: `1.0` is how a reader tells an
  environment from a judgment call.

### Optional node fields

- `statement_short` — your compression (core rule #2).
- `origin_citation` — required when `origin="external"`
- `assumptions[]`, `conclusions[]` — for results and conjectures
  (theorem/lemma/proposition/corollary/claim/conjecture). Each
  element is a verbatim span from the source — not paraphrased.
  Required when you can decompose; absent only when the
  statement structure resists clean decomposition. not used for
  `definition` nodes (definitions are stipulative, not if-then).
- `input[]`, `output[]` — for `algorithm` nodes: the verbatim input and output
  descriptions. These and `assumptions[]`/`conclusions[]` are JSON arrays of
  strings, one verbatim span per element (`"input": ["Cost matrix $M$",
  "Marginals $r$ and $c$"]`), never one concatenated string. There is no
  `pseudocode` field: the verbatim algorithm body is the `statement`, and
  its steps are `algorithm_step` children.
- `definiendum`, `genus`, `differentia[]` — for `definition` nodes only
  (see "Definition decomposition" below).
- `rigor` — optional, default `formal`. Omit it on any node whose
  statement is precise and whose justification is a rigorous proof.
  Add it only when the node departs from that:

  | value | when |
  |---|---|
  | `semi_formal` | precise statement, but a proof sketch, an appeal to "standard arguments", or asserted as routine with no argument ("easy to check") |
  | `heuristic` | believed true on physical or intuitive grounds, no proof offered |
  | `numerical` | supported by simulation or computation only |
  | `conjectural` | presented as unproven: a belief, an expectation or a conjecture ("we believe", "it is expected") |

  `rigor` belongs only on nodes that assert something true: results (not
  conjectures, whose type already says they are unproven), equations
  and remarks that assert a result. Never on definitions, assumptions,
  examples, exercises, problems, open problems, algorithms, proofs or steps,
  and never on `origin: external` nodes.
  Judge the justification, not the node's type or the paper's arXiv
  category. A `theorem` with a hand-waved proof is `semi_formal`; a
  `remark` carrying a full proof gets no `rigor` field. Do not infer
  rigor from the category: two papers in the same category can differ
  completely, so read each node's own justification.

  Emit `metadata.rigor_nonformal_count` (in the output's `metadata`, Workflow
  step 9) = the number of nodes you gave a
  `rigor` field. Always emit it, `0` included: a missing key is read as
  "rule not applied".
- `label` — the `\label{...}` key of the environment this node came
  from. Filled by the finishing step from `facts.json`.
- `parent_id` — "is part of": the innermost node containing this one (see "The
  graph is a hierarchy"). You set it on steps; the finishing step sets it on Level-1
  nodes
- `proves` — on a `proof` node, the id of the result it proves; always the same
  as the target of its `proves` edge
- `tags[]` — topical labels only (per Hard rule 8)
- `proof_strategy[]` — proof strategy labels, on `proof` nodes only
  (per Hard rule 8)
- `subclass` — on step nodes only, from the `subclass` vocabulary (see "Level-2 steps")

### Assumption / conclusion decomposition (results and conjectures)

When you split a verbatim statement into `assumptions[]` and
`conclusions[]`, you are selecting spans from the verbatim text —
not paraphrasing it. The union of the spans should reconstruct the
mathematical content of the statement; the wording must match the
source.

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

Before choosing Regime C, check the surrounding text for declarations of the
statement's variables; if there are any, use Regime B and quote them
verbatim.

### Definition decomposition — definiendum / genus / differentia (definitions)

For `definition` nodes, optionally decompose the definition in the
classical way: the term, the category it belongs to, and the conditions
that single it out. All three fields are optional and best-effort; emit them when the definition
has a clear "X is a Y that satisfies Z" shape, and omit any that do not
apply. They do not replace `statement` (which stays verbatim).

- `definiendum` — the term being defined (the head noun / name). Prefer a
  verbatim span; a canonicalized name is acceptable.
- `genus` — the parent category the definiendum belongs to. Prefer a
  verbatim span from the definition body.
- `differentia[]` — the distinguishing conditions that separate it within
  the genus, one per element, each a verbatim span where possible.

Examples:
- "A field is a commutative ring in which every nonzero element
  is invertible." → `definiendum="field"`, `genus="commutative ring"`,
  `differentia=["every nonzero element is invertible"]`.
- "A Banach space is a normed vector space that is complete."
  → `definiendum="Banach space"`, `genus="normed vector space"`,
  `differentia=["complete"]`.

When a definition is purely stipulative notation with no genus ("Let
$X := \{...\}$"), omit `genus`/`differentia` and keep only `statement`
(and `definiendum` if a name is introduced).

### Compact ID convention

`{PREFIX}{seq}`: the type's prefix and a counter from 1 within each type, e.g.
`TP3` (source order preferred; never renumber).

| Type | Prefix | Example |
|---|---|---|
| definition | DP | DP1 |
| theorem | TP | TP1 |
| lemma | LP | LP1 |
| proposition | PrP | PrP1 |
| corollary | CP | CP1 |
| proof | PP | PP1 |
| proof_step | PSP | PSP1 |
| algorithm | AP | AP1 |
| algorithm_step | ASP | ASP1 |
| equation | EP | EP1 |
| example | ExP | ExP1 |
| exercise | ExerP | ExerP1 |
| remark | RP | RP1 |
| problem | ProbP | ProbP1 |
| open_problem | OpenP | OpenP1 |
| assumption | AssumP | AssumP1 |
| claim | ClP | ClP1 |
| conjecture | CnjP | CnjP1 |

## CORE RULE #1 — `statement` IS A COPY, NOT A SUMMARY

You are an extractor, not a writer, editor, or summarizer. Do not
paraphrase even slightly: the finishing step locates every `statement` in the
prepared source by exact match, and a statement it cannot find fails the
check.

The only edits permitted to the source text are mechanical cleanup that
does not change wording:

- Collapse runs of whitespace and newlines into single spaces.
- Strip LaTeX comments (`% ...` to end of line), TeX-disabled regions
  (`\iffalse ... \fi`, `\if0 ... \fi`, `\begin{comment}`), and everything
  after `\end{document}`; inline `\input` files and expand the paper's own
  argument-free macros. `facts.json`'s `source` has already done all of this;
  do not undo the macro expansion.
- Drop `\label{...}` and `\index{...}` commands.
- Keep `\ref{...}`, `\eqref{...}`, `\cite{...}` and their variants exactly as
  written: the finishing step turns each `\ref` into an edge.
- Build the output with a JSON library (`json.dump`), which escapes backslashes
  for you (`\Sigma` in the source becomes `"\\Sigma"` in the file). Never escape
  by hand: doing both doubles the backslashes.

Everything else stays: every word, math symbol, named object and qualifying
clause, including "Let X be..." and "Suppose that...".

### No fabrication

Every node `statement` must be text that
literally appears in the prepared source (`facts.json`'s `source`; the
permitted cleanup above aside). Do not synthesize from
general knowledge, external papers, or your own understanding of
the result. If you cannot point to the exact span in the source
that a `statement` was copied from, the node is invalid.
`statement_short`, by contrast, is your own compression — you may
write it freshly. Do not confuse the two.

### LaTeX math

Copy math exactly as the source writes it: every `$`, every backslash command
(`\Sigma`, `\mathbb`, `\frac`, ...), every brace and subscript, and display math
(`\[ ... \]`, `\begin{equation} ... \end{equation}`) as display math. Do not
rewrite, normalize or "fix" notation, not even to add missing braces: the
statement must match the source character for character. Let the JSON library
escape backslashes (see the cleanup list above).

### Anti-paraphrase catalogue

| ❌ DO NOT (in `statement`) | ✅ DO (in `statement`) |
|---|---|
| Rewrite "Let $X$ be a Banach space and $T:X\to X$ a bounded linear operator. Then ..." as "If $X$ is Banach and $T$ is bounded linear, then ...". | Keep the original "Let ... . Then ..." phrasing. |
| Replace a named object with a generic description ("Sinkhorn-Knopp algorithm" → "fixed-point iteration"). | Keep the canonical name. |
| Merge two source sentences into one. | Preserve the source's sentence structure. |
| Replace a proof or an algorithm body with a summary ("By induction on $n$."). | Copy the full body, however long; the summary goes in `statement_short`. |
| Drop a hypothesis you think is "implied" or "obvious". | Copy every hypothesis. |
| Smooth out awkward phrasing. | Preserve awkward phrasing — it is part of the source. |

### Where a prose node starts and ends

For a node that is not an environment fact (a result, definition, assumption,
remark or problem stated in running text), the `statement` is:

- **Whole sentences.** It starts at the beginning of a sentence and ends at the
  end of one. (Checked by the finishing step.)
- **Within one section.** It never crosses a section heading of the paper
  (`\section`, `\chapter`, `\subsection`, ...). A heading inside an environment,
  such as `\subsection{Step 1}` within a long proof, belongs to that environment
  and is not a boundary; `facts.json` marks it (`sections[].inside`).
  (Checked by the finishing step.)
- **One statement per node.** Two separate assumptions, definitions or results
  are two nodes, even in consecutive sentences: "The weights are assumed
  i.i.d. normal. I assume the inputs are i.i.d. with variance 1." is two
  `assumption` nodes, one on the weights and one on the inputs.
- **Minimal but self-contained.** The fewest whole sentences that state it on
  their own: include its hypotheses and a following "where ..." sentence that
  defines its symbols; leave out motivation before it ("Note that", "Recall
  that", "In this section we ...") and discussion after it.
- **The argument is not the claim.** If the paper states a result and argues
  for it in running text (no proof environment), before or after stating it
  ("By Lemma 4.2 ... we see the following"), the argument is not part of the result's node: it is a
  separate `proof` node with a `proves` edge to the result. Numbered equations
  inside it are `equation` nodes, nested inside the proof. Because the
  span and the proved result are your judgment, give such a proof node and its
  `proves` edge confidence `0.6`–`0.8`; use `0.85`–`0.95` when the paper labels
  the proof in prose (`\noindent{\it Proof.}`, "Proof of Theorem 2:"); `1.0`
  is for `\begin{proof}` environments only. A single justifying sentence is a
  `proof` node with zero steps. The deciding question: is there a
  separately stated result that this text justifies? If yes, `proof`. If no,
  it is not a proof: a paragraph that is a self-contained aside,
  arguing and concluding in one go with no separately stated claim ("By
  Gelfond's inequality ... Liouville's inequality then implies ... Combined
  with (3), this gives ... Must be irreducible."), is one `remark` node. Do not
  split it.
- **A proof continued elsewhere is one node per part.** When a proof stops and
  resumes in another section ("The rest of the proof is in Appendix C"), each
  part is its own `proof` node, inside its own section, with a `proves` edge to
  the result. Add a `uses` edge with the continuation as `source` and the first
  part as `target`: the first part relies on the rest.
- **A cited result that is only applied is not a node.** Create an
  `origin: external` node only when the paper states the external result. A
  sentence that applies one ("Liouville's inequality then implies that
  $|x_n - y| \gg n^{-2\delta-1}$") is part of the node that uses it; the
  `\cite` stays in its text.
- **Type of a result stated in prose: `claim` unless the paper names it.** A
  result stated in running text, outside any environment, without a name, is
  a `claim`. Use `theorem`, `lemma`, `proposition` or `corollary` only when the
  paper itself calls it so ("by Theorem 3.2 of [10], every ...", "the
  following lemma ...", "[Sinkhorn's theorem]"), or when it states a cited
  prior result in full ("ten Berge [tb00] proved that $\trank(p,n,m)=\{p\}$
  for these cases"): that is a `theorem` with `origin: external`. Do not
  choose between theorem, lemma and proposition by how important or how long
  the result looks; for an unnamed prose result, the answer is `claim`.
- **One node per repeated statement.** When the paper states the same result or
  definition twice (in the abstract or introduction, then formally), emit one
  node: the environment if there is one, else the fuller statement.
- **No partial overlap.** Two nodes either do not overlap, or one contains the
  other (a `proof` containing an equation or a nested claim). Two nodes sharing
  some sentences but not others is an error. (Checked by the finishing step.)

## CORE RULE #2 — `statement_short` IS YOUR COMPRESSION

For every node, emit `statement_short` whenever you can write a short
compression that meaningfully adds value over `statement`.

**When to emit:**
- Proofs: always emit. Give the strategy ("By induction on $n$",
  "Density-increment iteration", "Apply Cauchy-Schwarz to bound LHS, then
  integrate"). For a proof of 10 or more sentences whose argument turns on one
  key step, add a second sentence naming that step ("Induction on $n$. The
  inductive step applies a density increment on a progression of length
  $\sqrt{N}$.").
- Algorithms: always emit. Say what the algorithm does ("Spectral
  clustering via bottom-$k$ eigenvectors then $k$-means"); for one with 10 or
  more steps, a second sentence may name its key step.
- Theorems / Lemmas / Propositions: emit when the verbatim statement
  is dense with notation and a plain-English compression is informative.
- Definitions: skip if the verbatim statement is already a short
  English sentence; emit when the definition is long, multi-clause, or
  notation-heavy.
- Remarks / examples: emit only when long, multi-clause, or notation-heavy,
  as for definitions.

**When to skip:** if `statement_short` would be nearly identical to
`statement` (i.e., no real compression value), leave `statement_short`
absent.

**Style:**
- Plain English, math symbols allowed where natural ($\delta$, $\Delta$, etc.).
- One sentence, about 150 characters; two sentences, at most about 300
  characters, only for the proofs and algorithms above. Never a paraphrase of
  the whole argument: if a second sentence would only restate details, leave
  it out.
- Capture the idea, not all the technical conditions.
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

## Edge taxonomy — with direction conventions

### Edge coverage — find the edges that exist, invent none

**Find every real edge.** An isolated node deserves a second look: check
whether the paper relates it to something. Before you finish, sweep every
node and ask "does the paper actually relate this to something?" — in
particular:
  - each `definition`: which later statement or definition uses this concept?
    (definition chains are real structure: `flow → subflow → minimal flow`)
  - each `proof`: it must have a `proves` edge to what it proves;
  - each result or conjecture: which definitions/assumptions/lemmas does its
    statement invoke?
  - each `example`: what concept does it illustrate?

**Invent none.** A node with no real relationship stays isolated; that is
correct output. Do not
treat "every node has an edge" as a target to hit.

**Score uncertain edges, do not guess.** Emit a borderline edge with its
`confidence` rather than deciding yes or no:

| `confidence` | when |
|---|---|
| `0.9`–`1.0` | the text explicitly cross-references it in words (`by Lemma 3`; edges a `\ref` states are added by the finishing step), or it is the `proves` edge of a `\begin{proof}` environment (a proof argued in prose: see "Where a prose node starts and ends", `0.6`–`0.95`) |
| `0.7`–`0.85` | no explicit reference, but the logical dependency is clear-cut (the statement uses a term this definition introduces) |
| `0.5`–`0.65` | plausible but genuinely uncertain — emit only if you actually believe it |
| below `0.5` | do not emit |

Report your orphan count (nodes with no edge) in the final summary, with a one-line reason for any
node you deliberately left isolated.

These are the only valid edge types — do not invent others (e.g. there is no `defines` and no `special_case_of`; a
definition→user link is just `uses`, and "special case" is `specializes`).

**One rule for every edge, no exceptions:**

> The arrow points **from the thing that comes first / is relied upon**
> (`source`) **to the thing that relies on it** (`target`).
> Equivalently: `source` supports `target`; `target` depends on `source`.

The table gives the required node type at each endpoint.

| Edge type | `source` (relied upon) | `target` (relies on source) | Reading |
|---|---|---|---|
| `uses` | any | any | target uses source (generic dependency, the default) |
| `specializes` | any (general) | any (specific) | target is a special case of source |
| `generalizes` | any (specific) | any (general) | target is a generalization of source |
| `proves` | `proof` | result | the result's validity rests on the proof |
| `illustrates` | any (the concept) | `example` | the example depends on the concept it shows |
| `tests` | any (the concept) | `exercise` | the exercise depends on the concept it tests |
| `resolves` | `problem` / `open_problem` / `conjecture` | result / `algorithm` | the result settles the question, or the algorithm solves the problem |

**Every edge has four required fields: `source`, `target`, `type`, `confidence`**,
plus `"backward": true`, which the finishing step sets by position (Hard rule 7).
`confidence` is required (float 0-1, scored per the table above).

**Worked examples — copy these shapes exactly:**
- definition DP1 used by theorem TP1, explicit `\ref` in the text:
  `{"source": "DP1", "target": "TP1", "type": "uses", "confidence": 0.95}`
- proof PP1 of theorem TP1, a `\begin{proof}` environment:
  `{"source": "PP1", "target": "TP1", "type": "proves", "confidence": 1.0}`
- example ExP1 illustrating definition DP1:
  `{"source": "DP1", "target": "ExP1", "type": "illustrates", "confidence": 0.9}`
- algorithm AP1 solving problem ProbP1:
  `{"source": "ProbP1", "target": "AP1", "type": "resolves", "confidence": 0.9}`
- theorem TP2 resolving open problem OpenP1:
  `{"source": "OpenP1", "target": "TP2", "type": "resolves", "confidence": 0.8}`
- definition DP2 whose statement uses a term DP1 introduces, no explicit ref:
  `{"source": "DP1", "target": "DP2", "type": "uses", "confidence": 0.75}`

**Theorem/definition → algorithm dependency:** when a paper introduces
a theorem (e.g. existence of a factorization) and an algorithm that
computes it, the theorem is a prerequisite of the algorithm:
`theorem → algorithm` with type `uses`. Same for definitions.

## Level-2 steps — proof_step and algorithm_step

Steps do not replace their parent's body. The parent `proof` / `algorithm`
`statement` holds the full verbatim body (core rule #1), and the step nodes are
emitted alongside it.

### When to emit a `proof_step`

A step is one move of the argument: an object is introduced, a case is opened, a
lemma or inequality is applied, a bound is established, an intermediate claim is
proved, or the conclusion is drawn. A step need not carry a marker ("Let", "By",
"Since", "Now"…). Decide first by step rule 9 whether the
proof gets steps at all; then apply the step rules below in order.

**1. Author labels (from `facts.json`).** For a proof in prose (no
environment), look for the same kinds of label yourself. Each proof fact carries
`structure.labels`: the places where the paper itself labels its structure,
already detected by the parser (`Step N`, `Case N`, `Part N` at the start of a line, `(i)`/`(a)`
item labels, `1.` after `\smallskip`/`\par`/a blank line, prose items of a list
inside the proof, `\textbf{...}`/`\emph{...}` headings, Base case / Inductive step,
nested `\begin{proof}`). Every one of them starts a step.
Keep the label token in the step's `statement` (strip only `\item`). The
finishing step checks this. A label body longer than 2 sentences gets child steps
(`parent_id` = the label's step), segmented by the rules below. Text before the
first label is its own `setup` step.

**2. Steps end only at sentence ends.** A boundary falls after a `.`, `!`, `?` or
`:` outside math, or at a label. Never inside a display, at a comma, at `;`, or
before "where", "which", "because" continuing the same sentence. The finishing
step checks this.

**3. Paragraph breaks are a strong hint.** `structure.paragraph_breaks` lists the
breaks that follow a complete sentence. Such a break normally starts a new step;
merge across it only when the next paragraph plainly continues the same move.
(Blank lines around a displayed equation are layout, not structure, and are not
listed.)

**4. Introductions group.** A run of consecutive sentences that only introduce
objects (start with Let, Take, Consider, Define, Fix, Denote, Set, and contain no
`\ref`, `\cite`, display, or hence/so/then/thus) is one `introduce_variable`
step. A run of a single such sentence is joined to the step that follows it.

**5. Meta, reduction and recall form `setup` steps.** A sentence that starts with
"it suffices to", "it is enough to", "it remains to", "we only need
to", "the proof is (similar|analogous) to", "is proven exactly as", "we will use",
"recall", "we have remarked" is a `setup` step. A contiguous restatement of a
definition or a cited theorem (including a theorem-style environment quoted inside
the proof) is one `setup` step.

**6. Immediate sentences never stand alone.** A sentence is immediate when it has
no display and no `\ref`/`\eqref`/`\cite`, and contains one of: clear(ly),
obvious(ly), trivial(ly), immediate(ly), at once, easy/easily, straightforward,
tautological, by inspection, similarly, a similar argument, the same argument, as
above, we can verify, left to the reader; or is a closing formula ("This
completes / finishes / proves the …", `\qed`). An unlabelled immediate sentence
is appended to the preceding step, or, if it comes first in the body or label,
prepended to the following step. A case opener or an induction base case (step rule 8)
is never immediate; a closing formula is immediate even when it contains a
`\ref` ("The proof of Theorem \ref{t1} is complete").

**7. Inline claims nest.** A sentence matching "We claim", "I claim", "Claim",
"Let us (show|prove|check)", "(First|Next|Now), we (show|prove|check)", "We show
this by", "(We|we) (now )?(show|prove|check) that" opens a parent step (`structure.claims` lists the ones the parser
found). The following sentences are its children, up to and including the first
sentence matching "(proves|completes|establishes) the claim", "This proves", "Now
that", "as claimed", or the first sentence that restates the claim's conclusion
or says it follows, or the next paragraph break, or the end of the enclosing
label, whichever comes first. Nesting is required when at least 2 sentences
follow the opener. Only a numbered or later-cited inline claim is also a
Level-1 `claim` node (its statement is the claim sentence); its argument stays
as the steps under it, not a separate `proof` node.

**8. Case splits.** A case opener is a sentence starting with (So )?(first
)?(Suppose|Assume|If|Let us assume) when a later sentence starts with "If
instead", "Otherwise", "Else", "Conversely", "For the case", "In the
(other|remaining) case", "Secondly, if", "Note that if", "(Suppose|Assume) now",
"Now (suppose|assume)". Each opener starts a `case_split` step. Add a
conclusion step only if a reunion sentence exists ("In (either|both|all)
case(s)", or Thus/Hence after the last case). Cases stated inside one sentence
("either …; or …") stay one step. "Without loss of generality" is `setup`, not
a case. Induction ("Base case: … Inductive step: …") gives at least two
`induction_step` steps.

**9. Short proofs.** Emit zero steps when the body has at most 2 sentences outside
displays and no label. Never emit exactly one step: a body that is one move gets
zero. Likewise a step never has exactly one child.

**10. A proof interrupted by an inner result.** When a proof is interrupted by a
lemma or claim and its own proof, the outer `proof` statement spans the whole
text, inner result included. The inner result and its proof are their own nodes
(their `parent_id` is the outer proof, set by the finishing step). Among the outer
proof's steps the inner block is one `setup` step with no children; the inner
steps belong to the inner proof only.

**Step fields.** A step's `confidence` is `0.95` when it starts at an author
label, `0.75` otherwise. A step takes its parent's `section` and `origin`.

### When to emit an `algorithm_step`

*Pseudocode* — an algorithm fact with `lines` (pseudocode in `algorithmic`,
`algpseudocode`, `algorithm2e`, or a numbered list in an algorithm float). Its
structure is syntax, so do not segment it yourself. In your build script call

    from extraction_finalize import pseudocode_steps
    steps = pseudocode_steps(facts, fact_id, algorithm_node, first_seq=next_free_ASP_number)

It returns one `algorithm_step` per printed line, with the verbatim `statement`
(a loop or branch line spans its body), `parent_id` (the enclosing loop or
branch, or the algorithm), `step_order`, a placeholder `name`, `confidence` 1.0,
and `subclass` for control lines. Then, per step: choose `subclass` where it is
None; write `statement_short` only where the line is not self-explanatory
(`$x \leftarrow x + 1$` needs none); improve `name` if you like. Drop a step
only when its line is not an operation (an algorithm title or input declaration
that the package prints as a line). A line whose text describes several
operations in prose may get child steps of its own, segmented as for
unmarked procedures below. Keep `statement`, `parent_id` and `step_order` as returned;
the finishing step sets `source_line_label` from the line LaTeX prints.

*Unmarked* — an `\begin{algorithm}` float containing prose, or a procedure
described in running text ("first we construct…, then for each component we…").
One step per operation the description performs; segment on operations, not on
sentences. `confidence` is 0.6–0.8, since the step boundaries are your judgment.

Do not skip an algorithm, or decline to decompose it, because it has no
`\STATE` markers: an unmarked procedure is still an algorithm.

### Verbatim requirement

Each step's `statement` is also verbatim — the sentence(s) from the source body
that constitute that step (for pseudocode, `pseudocode_steps` gives it). A proof
step's `statement_short` is your compression of that step's role ("Set up
induction on $n$", "Apply Cauchy-Schwarz", "Conclude by Markov's inequality").

### Worked example — a labelled proof

Source body:

```
Part (1): By the definition of $d_i$, $f' L f = ...$ which yields
the quadratic form.
Part (2): The symmetry of $L$ follows directly from $W$ and $D$.
Positive semi-definiteness follows from Part (1).
Part (3): Obvious.
```

Required output: one `proof` node whose `statement` is the full verbatim body
(`statement_short` e.g. "Direct expansion + symmetry"), plus three `proof_step`
nodes, each with `statement` = the verbatim text of its "Part (N):" sentence(s),
`statement_short` = the step's role, `parent_id` pointing to the proof, and
`subclass` from the `subclass` vocabulary below.

### Worked example — an unlabelled proof

Source body:

```
Take a vertex $v \in \cap_{n\geq 1} V(w_n)$. Let $P_n$ be the set of
paths of length $n$ ending at $v$. Since each $P_n$ is finite and
non-empty, Konig's lemma gives an infinite path. This path witnesses
the claim.
```

No `Part`, no `Case`, no `Step` — and it is still three moves: introduce $v$ and
$P_n$; apply Konig's lemma; conclude. Emit three `proof_step` nodes.

**Step-node fields:**
- `id` (e.g. `PSP1`, `ASP1`)
- `type` (`proof_step` or `algorithm_step`)
- `parent_id` (id of the parent node — see "Nesting" below)
- `step_order` (1-based index within the immediate parent)
- `source_line_label` (`algorithm_step` only; filled by the finishing step,
  never by hand)
- `name` (a short descriptive label)
- `statement` (verbatim source span for this step)
- `statement_short` (your compression of the step's role)
- `subclass` (from the controlled vocabulary below)
- `tags[]` (optional, topical)

**Nesting: steps may parent other steps.** A step node may take
another step node as its `parent_id`, to any depth:
- `proof_step` — a label body longer than 2 sentences (step rule 1), an
  inline claim with at least 2 following sentences (step rule 7, required),
  a `\begin{proof}` inside a proof, a "Proof of Claim N" block.
- `algorithm_step` — loop and branch bodies are children, not
  siblings: a line inside a `\FOR` / `\WHILE` / `\IF` block takes that
  block's step as its `parent_id` (`pseudocode_steps` sets this for you).

`step_order` restarts at 1 within each parent, so an outer loop's
body is 1,2,3… not a continuation of the outer numbering.

**A step with children spans them.** Its `statement` runs from its own first
sentence through the end of its last child: a label step is the whole label
body; a claim step runs from the opener through the claim's last sentence; a
loop step covers its body. Do not end a parent step before its last child:
`parent_id` means "is part of", and the finishing step warns when a parent's statement
does not contain its child.

**`subclass` controlled vocabulary.** The two vocabularies are
disjoint — never use a proof_step value on an algorithm_step or
the reverse.
- proof_step: `setup, introduce_variable, apply_lemma, case_split,
  induction_step, contradiction_setup, algebraic_manipulation,
  substitute, bound_estimate, invoke_identity, conclude, other`
  Glosses: `setup` = recall, reduction, meta-pointer, WLOG, text before the
  first label · `introduce_variable` = Let/Take/Define/Consider/construct,
  including a construction "as follows" inside a proof (which stays
  proof_steps, not an algorithm) · `case_split` = every step that opens a case ·
  `induction_step` = base case and inductive steps, including structural
  induction cases that use the hypothesis · `conclude` = the step that draws
  its parent's conclusion (the last move of the body, a label or a claim) · a
  container step (a label or claim with children) takes its role, else `other`.
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
  `update` modify existing state — use only when none of the above
  fits: a step that computes, selects, filters or solves is not an
  `update`. ·
  `return` output or terminate · `other` none of the above

Steps may reference Level-1 nodes outside the parent
(e.g. `proof_step uses Lemma 2.3`), but step-to-step edges across
different parents are not permitted.

## Extraction notes

Alongside the graph, record what was unusual about extracting this paper, in
`metadata.paper_style`, `metadata.extraction_notes` and
`metadata.extraction_comment`. People read these to
filter papers and to improve these instructions, so write plainly and
specifically. Add a note when the situation arises, not only at the end.

`paper_style` is how the paper establishes what it says: a list of one or two
of the values below, the dominant one first. Decide it after extracting, from
what you found; it describes the paper and changes none of the rules above. Judge the reasoning, not the
layout (a proof written in prose is still `theorem_proof`).
- `theorem_proof`: results stated and proved, including proofs that rest on a
  computer calculation;
- `formal`: results proved in a proof assistant (Lean, Coq, Isabelle, ...);
  the proofs are code listings rather than prose;
- `derivation`: results reached by calculation, approximation and physical or
  intuitive argument, not proved (theoretical physics, much applied
  mathematics);
- `modeling`: a model, method or algorithm is specified and developed
  (equations of a biological or physical system, a statistical model with its
  likelihood and estimators, a learning method, a controller), with few or no
  theorems (much statistics, machine learning, mathematical biology,
  engineering);
- `computational`: simulations, numerics, computer searches, experiments on
  data or benchmarks are the main evidence;
- `problem_list`: mostly a collection of problems, open questions or
  conjectures;
- `expository`: mostly presents known results (a survey, lecture notes, a
  tutorial);
- `discursive`: mostly words, with little mathematics to extract (history,
  philosophy, a position paper, a description of software or data);
- `other`: say what in `extraction_comment` (e.g. an erratum, or a comment on
  another paper).

`extraction_notes` is a list of at most about 10 entries, each
`{"category": ..., "nodes": [ids], "note": "one or two sentences"}`. `nodes`
may be empty for a note about the whole paper.

| `category` | when |
|---|---|
| `type_uncertain` | you hesitated between two types: the node carries your choice, the note names the other and why ("lemma or remark: stated without proof, used once") |
| `boundary_uncertain` | you are unsure where a node starts or ends |
| `unexpected_construct` | content no node type or rule fits (a table of results, a diagrammatic argument, a computation spread over pages); say how you handled it |
| `rule_conflict` | two rules here disagreed, or a rule was unclear for this paper; say which, and what you did. Do not silently invent a rule |
| `source_problem` | the source made extraction hard: heavy macros, a missing `\input` file, content only in figures |
| `not_extracted` | content you deliberately left out, and why |

Do not summarize the paper, and do not restate what the graph already records
(types, counts, confidence scores). If nothing was unusual, leave the list
empty; do not write a note just to have one.

`extraction_comment` is free text, at most 3 sentences, for something a reader of
this graph should know that fits none of the categories above. Use it only then;
otherwise leave it as an empty string.

## Workflow

0. Run `latex_facts.py` (see "Two layers") and read `facts.json`.
1. Read the prepared `source` (multiple Read calls with offsets if large).
2. Emit a node for every environment fact. Then find everything the facts
   do not cover: definitions, results, remarks, claims, problems and
   algorithms stated in prose.
3. Assign compact IDs as you create nodes; source order within a type is
   preferred but not required (see "Compact ID convention").
4. For each node: copy its `statement` (core rule #1), write its
   `statement_short` (core rule #2) and fill its fields (see "Schema").
5. Apply step extraction for proofs and algorithms (see "Level-2 steps").
6. Apply type-promotion (Hard rule 4).
7. Build edges for logical dependencies that have no `\ref`. (Edges a `\ref`
   states are added by the finishing step in step 8.)
8. In the script you write to build the output (`graph` below is the output
   dict, with `metadata`, `nodes` and `edges`), finish and check it before
   writing it:

       import sys; sys.path.insert(0, "{REPO}/src")
       from extraction_finalize import finalize
       from latex_facts import read_tex
       report = finalize(graph, read_tex("{TEX_SOURCE}"))
       assert not report["errors"], report["errors"]

   It fills `label` and `source_line_label`, writes the paper's full `\label`
   table to `metadata.labels` (so every `\ref` kept in a statement resolves),
   adds the `\ref`-stated `uses` edges and syntax-stated `proves` edges, and
   validates (verbatim spans,
   edge types and endpoints, acyclicity, step parents). Fix every error and
   re-run. A `\ref` that points backward is added with `"backward": true`;
   list `report["ref_backward"]` in your final report.
9. Write the JSON to the output file, {OUTPUT_JSON}:

   ```json
   {
     "metadata": {
       "title": "...",
       "annotator": "agent-extraction",
       "model": "{MODEL}",
       "effort": "{EFFORT}",
       "prompt_version": "v6",
       "extraction_date": "YYYY-MM-DD",
       "rigor_nonformal_count": 0,
       "paper_style": ["theorem_proof"],
       "extraction_notes": [
         {"category": "type_uncertain", "nodes": ["RP3"],
          "note": "remark or lemma: stated without proof, used once in PP2"}
       ],
       "extraction_comment": ""
     },
     "nodes": [...],
     "edges": [...]
   }
   ```

## Pre-output self-check (MANDATORY)

Before emitting the JSON, walk every node and verify:

1. **`statement` is verbatim.** In the prepared source (`facts.json`), find
   the originating environment body or the whole sentences of prose it came
   from, and confirm `statement` is that span verbatim, with:
   - All math preserved (`$..$`, all backslashes, all subscripts).
   - All hypotheses preserved (no dropped "Let X be..." clauses).
   - All named objects preserved (no generic substitutions).
   - Only the permitted mechanical cleanup applied (whitespace, `\label`,
     `\index`; the prepared source has already removed comments and disabled
     text and expanded macros).
2. **`statement_short`, when present, is meaningful compression** —
   not a copy-paste of `statement`, not longer than `statement`,
   captures the idea. For proof nodes, verify `statement_short`
   exists.
3. **`origin` is set on every node.**
4. **`section` is clean** — plain title, no `\label`s, no `(cited)` /
   `(alg:...)` parens.
5. **`type` is in the closed vocabulary** (Hard rule 4).
6. **`tags[]` is topical only.** Strategy labels live in
   `proof_strategy[]` on proof nodes.
7. **Results and conjectures have `assumptions[]`/`conclusions[]`** unless
   the statement structure genuinely resists decomposition.
   Definitions do not have these.

## Report (<200 words)

When complete, output:
- node count by type (e.g. "8 definition, 1 theorem, ..."), and how many nodes
  came from environment facts vs prose
- the finishing step's summary: labels filled, edges added, backward `\ref`s,
  any warnings left
- orphan count, with a one-line reason for any node deliberately left isolated
- **step counts per parent**: for each `proof` and `algorithm` node,
  report `<parent_id>: N steps` (e.g. `PP1: 4 steps`). If N=0,
  justify in one phrase ("single-paragraph body, no part/step labels").
- **`statement_short` coverage**: percentage of nodes that have a
  populated `statement_short`, by type
- edge count by type
- count of `origin: "external"` nodes
- 3 sample node names (drawn from the body)
- `paper_style`, the extraction notes (one line each) and `extraction_comment`
