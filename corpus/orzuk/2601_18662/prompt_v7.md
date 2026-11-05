
Extract a mathematics paper or chapter to JSON for the SARANGA project.

**What you are producing.** A typed directed graph of the paper's mathematical
content. Each node is one statement of the paper (a definition, a
theorem or other result, a proof, a proof step, an equation, an algorithm, a
remark, ...), of exactly one type from the closed vocabulary under "Schema"
below, and carries a `statement` copied verbatim from the source plus the
fields listed there. Nodes nest: a node that lies inside another (a
proof step in its proof, an equation in a theorem, a lemma inside a proof) is
part of it, recorded by `parent_id`. Edges are typed dependencies between
nodes, from the closed edge vocabulary in "Schema". (In
these instructions, a *section* is always a section of the paper; parts of the
instructions are named by their headings in quotes.)

**Terms used below.**
- *Prepared source*: the paper's text as `latex_facts.py` delivers it in
  `facts.json` (see "Two layers"). Everything you copy comes from it.
- *Span*: one contiguous piece of the prepared source.
- *`latex_facts.py`*: a command in `/mnt/c/Code/Github/Saranga/src/` that you run first; it reads
  the LaTeX syntax and writes `facts.json` (see "Two layers").
- *Finishing step*: the function `finalize()` in `/mnt/c/Code/Github/Saranga/src/extraction_finalize.py`,
  which your build script calls last (Workflow step 7): it fills some fields
  and edges and checks your graph.
- *Environment node*: a node taken from an environment the facts report (`\begin{theorem}`...). 
  *Prose node*: a node you find in running text, whose boundaries are your judgment.
- *Level-2 nodes* are the steps, `proof_step` and `algorithm_step`; every other node is *Level-1*.
- *Result*: a node of type theorem, lemma, proposition, corollary or claim
  (what a proof proves). A `conjecture` is stated like a result but unproven;
  an `open_problem` is a question, not a statement. Both can be resolved by a result.
- *Hard rule N* is rule N under "HARD RULES"; *step rule N* is rule N under
  "When to emit a `proof_step`".
- *Orphan*: a node with no edge, no `parent_id` and no child (a step or a
  nested equation is tied to the graph by its parent, not by edges).

**Core rule #1 — `statement` is a verbatim copy** from the prepared source,
LaTeX preserved exactly.

**Core rule #2 — `statement_short` is your compression** (see "CORE RULE #2").

## This paper

The paper you extract in this run, and where its files are:

- ARXIV ID: 2601.18662
- TITLE: A Unique Inverse Decomposition of Positive Definite Matrices under Linear Constraints
- AUTHORS: Yan Dolinsky, Or Zuk
- YEAR: 2026
- LATEX SOURCE (input): /mnt/c/Code/Github/Saranga/corpus/orzuk/2601_18662/arxiv_src/revision.tex
- OUTPUT FILE (write your JSON here): /mnt/c/Code/Github/Saranga/corpus/orzuk/2601_18662/2601_18662.json
- CODE (the Saranga repository, with the tools below): /mnt/c/Code/Github/Saranga

## Two layers: LaTeX facts first, then your judgment

Part of this paper's structure is stated by LaTeX syntax, and a parser reads
it exactly. Run it before anything else (`<scratch>` is any scratch directory):

    python3 /mnt/c/Code/Github/Saranga/src/latex_facts.py /mnt/c/Code/Github/Saranga/corpus/orzuk/2601_18662/arxiv_src/revision.tex --out <scratch>/facts.json

`facts.json` gives you:
- `source`: the prepared source: `\input`/`\include` files inlined, the
  paper's own argument-free macros expanded (`\gr` becomes `\Gamma`), and
  comments, `\iffalse`/`\if0` regions, `comment` environments and everything
  after `\end{document}` removed. Slice every verbatim field from this text,
  never from the raw `.tex`: the finishing step checks statements against it.
- `facts`: every theorem-style environment (`\newtheorem` ones: theorem,
  lemma, definition, remark, ...), proof, algorithm and numbered equation, plus
  two things LaTeX states without an environment: a hand-written proof
  (`{\it Proof.}` ... `\qed`; `"manual": true`) and a hand-numbered display
  (`$$ ... \eqno(3) $$`). Each comes with its body span (`start`, `end`), the
  author's name for it (`display`) and the node type that name maps to (`type`:
  also for common synonyms such as "Fact" or "Main Result"; null when the name
  says nothing), its `\label`, its printed number, its section (an
  `id` in `sections`: the innermost heading of the paper, not one inside an
  environment; a node's `section` field is that entry's number and title, e.g.
  "3.2 Monotonic Improvement"), and
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
the paper can cite it as "(3.2)". A multi-line display (`align`, `gather`,
`eqnarray`) whose numbered rows each have their own left-hand side is given as one
fact per equation; a chain (`x &= y \\ &\le z`) stays one fact, whatever its
numbering. An unnumbered displayed equation (`\[...\]`, `$$...$$`,
`equation*`, `align*`) without a `\label` is not a fact and not a node of its own: like inline math, it is part
of the text of the node that contains it. Confirm or correct `type`
(a `display` of "Fact" or "Property" is classified by Hard rule 4; when `type` is null,
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

For a hand-written proof fact, confidence is `0.9` (its end is found by syntax).

The finishing step fills `label`, `display` (the author's environment word,
"Theorem", "Hauptsatz"), `number` (the number LaTeX prints, "3.2"), `cites` (the
bib keys `\cite`d in a statement), `source_line_label`, `backward`,
`metadata.labels` (the paper's whole `\label` table, so every `\ref` kept in a
statement resolves) and the `parent_id` of Level-1 nodes, and adds the `uses`
edges that a `\ref` states and the `proves` edges that syntax states, with their
`basis` (see "Edge basis"); leave these out. A `\ref` gives an edge into every
node whose statement contains it (a proof step, its parent steps and the proof;
not an `algorithm_step`), never one opposite to an edge already present. It also makes a proof's `proves` field and its `proves` edges agree,
adding the edge from the field or the field from the edge. You add every dependency that has no `\ref`.

**The graph is a hierarchy.** `parent_id` means "is part of": every node is
either top-level or has exactly one parent, the innermost node whose statement
contains its own. A proof step belongs to its proof (or to a parent step); an
equation to the theorem, proof, definition or step it sits in; a lemma stated
inside a proof to that proof (to the step of it that spans the lemma, when
the proof has steps), and so does that lemma's own proof. You set
`parent_id` only on steps (see "Nesting"); the finishing step computes it for
Level-1 nodes from their spans. Never draw a `uses` edge to express containment.

## HARD RULES

1. **You decide what is a node by reading; scripts only move text.** Read the
   prepared source with the Read tool (with offsets for large files) and decide
   each node, its type and its span by reading it. Scripts are for slicing the
   spans you chose out of the source, building the JSON, and running the
   finishing step. Never let a regex decide what is a node: do not write a
   script that greps for "Theorem N.M" or "we define" and emits whatever matches.
   (The exceptions: the environment facts, which `latex_facts.py` provides, and
   pseudocode steps, which `pseudocode_steps` builds.)

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
   `origin_citation: "standard (uncited)"`, also when the paper restates it in
   its own notation; a notion the paper introduces is `paper`. A result the paper attributes to
   others is `external` even if the paper re-proves it; that proof is `paper`. A
   hedge with no attribution ("probably well known", "this is folklore, we include a
   proof") does not make a result `external` when the paper proves it: it is `paper`.

   `external` marks a node that states a cited result ("Theorem 2.1 (Brooks
   [12]). Every connected graph ..."); a citation only applied inside an
   argument creates no node (see "A cited result that is only applied is not a
   node").

4. **Closed node type vocabulary.** A node's `type` is determined by
   semantic content, not LaTeX environment, but the resulting type must
   come from the closed set in the schema block under "Schema". Do not invent new types (`fact`, `property`, `observation`, etc).
   Map non-standard `\newtheorem{...}` environments to the closest
   standard type that fits its content. When the content and the author's word
   disagree (a remark that states a cited theorem, an example that defines the
   objects later results use, a definition that asserts an equivalence), the
   content decides `type`: the author's word is kept in `display` by the
   finishing step, so retyping loses nothing.

   Type-promotion within the closed set:
   - A `\begin{definition}` whose body is an optimization formulation
     (e.g. `x^* = \arg\min_x f(x)`) → `type="problem"`, not `definition`.
   - A `\begin{definition}` whose body is a step-by-step procedure →
     `type="algorithm"`.
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
   paper presents it inside `\begin{equation}...\end{equation}` blocks: a
   numbered equation becomes a result when the text names it as one (see
   "Two layers").
   If the prose says "the optimal $P^\lambda$ has the unique form
   $P^\lambda = \diag(u) K \diag(v)$ [Sinkhorn's theorem]" — that is a
   **theorem** with `origin: external`: the paper names it and states it in
   full (see "Type of a result stated in prose").

   Count of result nodes you emit ≥ count of numbered or labelled result
   environments in the source (not counting a restated copy, see "One node per
   repeated statement", or an environment whose content you retyped, Hard rule 4).

7. **No circular reasoning; mentions are marked.** A `uses` edge `A → B` reads
    "B uses A". No cycle may consist only of results and conjectures, where a
    proof counts as the result it proves, or only of definitions.
    - *Backward edges stay.* A proof that cites "Remark 5 below", or an induction
      step that applies the theorem itself at a smaller case, points against the
      paper's order; the finishing step marks it `"backward": true`.
    - *Mentions.* An edge whose target does not rely on the source gets
      `"mention": true`: the source is only referred to ("let $w$ be as in
      Theorem 1", "the lemma is used in the proof of Proposition 3"), or the
      target is about it without using it ("Theorem 2 is equivalent to
      Conjecture 1", "motivated by", "by analogy with", "the heuristic behind").
      When a `\ref` states a mention, add that edge yourself before the finishing
      step runs, confidence `0.95`, with `"mention": true` and no `basis` (the
      finishing step gives it `basis: "ref"` and does not add it again).
    - *Equivalence is not a dependency.* For "equivalent" results draw only the
      uses their proofs make; no reciprocal `uses` edges between the same pair.
    - *Second proofs.* A second proof of a result that has its own proof ("we
      give another proof", or Theorem 1 derived from Theorem 2 after its direct
      proof, closing the loop of two equivalent theorems) gets
      `"alternative": true` on its `proves` edge; the first proof keeps no flag.
    - *When the finishing step reports a cycle*, mark the edge on it that is only
      a mention. If none is, check every edge on the cycle against the text: an
      edge you inferred (`basis: "inferred"`) that the text does not state is the
      likely error; correct it. If the text states every edge, the cycle is a
      finding: keep the edges and add a `cycle` note (see "Extraction notes")
      with its `kind`: `wrong_ref` (a `\ref` pointing at the wrong result, a
      typo), `granularity` (the results use different parts of each other, too
      intertwined to be separate claims) or `circular` (the argument is
      circular). Never delete an edge, retype it, or change a node's span to
      remove a cycle.

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

9. **`section` is the plain section title,** taken from the facts entry
    (`sections`), never written by you. Do not include LaTeX labels,
    cross-reference identifiers, or parenthesized provenance markers.

    - **Wrong:** `"section": "3 Monotonic Improvement (alg:pialg)"`
    - **Wrong:** `"section": "1 (cited)"`
    - **Right:** `"section": "3 Monotonic Improvement"`
    - **Right:** `"section": "1 Introduction"` plus `"origin": "external"`
      on the cited node.

## Schema

NODE TYPES (16 Level-1, 2 Level-2):

Theorem-like (6): theorem, lemma, proposition, corollary, claim, conjecture.
Carry assumptions and conclusions field splits.

Foundational (2): definition, proof.

Pedagogical (2): example, exercise.

Other content (6): problem, open_problem, assumption, equation, algorithm, remark.

Level-2 sub-block (2; when to emit them: "Level-2 steps"): proof_step, algorithm_step.

EDGE TYPES (7): uses, generalizes, specializes, proves, illustrates, tests, resolves.
Direction: an edge A → B means that B depends on A (see "Direction" below).


### Required node fields (every node)

- `id` — compact ID (see convention below)
- `type` — from the closed vocabulary in the schema block above
- `name` — display name (canonical name from paper, e.g. "Brooks'
  Theorem", "Leftover Hash Lemma", "Discrete Fourier Transform")
- `statement` — the verbatim source span (core rule #1).
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
  statement structure resists clean decomposition. Not used for
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
  | `conjectural` | an asserted result the paper presents as expected but unproven ("we believe", "it is expected") |

  `rigor` belongs only on nodes that assert something true: results (not
  conjectures, whose type already says they are unproven), equations
  and remarks that assert a result. Never on definitions, assumptions,
  examples, exercises, problems, open problems, algorithms, proofs or steps,
  and never on `origin: external` nodes.
  Judge each node's own justification, not its type or the paper's arXiv
  category: a `theorem` with a hand-waved proof is `semi_formal`; a `remark`
  carrying a full proof gets no `rigor` field.

  Emit `metadata.rigor_nonformal_count` (in the output's `metadata`, Workflow
  step 8) = the number of nodes you gave a
  `rigor` field. Always emit it, `0` included: the finishing step rejects a
  graph without it.
- `parent_id` — "is part of": the innermost node containing this one (see "The
  graph is a hierarchy").
- `proves` — on a `proof` node, the id of the result it proves, the target of
  its `proves` edge. A proof that establishes several results (one argument for
  both (3.1) and (3.2)) has a `proves` edge to each; `proves` names the first.
- `tags[]` — topical labels only (per Hard rule 8)
- `proof_strategy[]` — proof strategy labels, on `proof` nodes only
  (per Hard rule 8)
- `subclass` — on step nodes only, from the `subclass` vocabulary (see "Level-2 steps")
- `also_stated_at[]` — on a node whose statement the paper gives twice or more:
  the verbatim spans of the other copies (see "One node per repeated statement").
- `equivalent_conditions[]` — on an "iff" / TFAE result or conjecture: the verbatim
  span of each side, at least two (see Regime D).
- `parts[]` — on a result or conjecture that states several implications: which
  assumptions give which conclusions (see Regime E).
- `main` — `true` on the paper's main results (results or algorithms): the ones its
  abstract or introduction announces as its contributions. Omit it elsewhere.
- `label`, `display`, `number`, `cites` — filled by the finishing step (see "Two
  layers"); never set them.

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
  statement's variables; if there are any, use Regime B and quote them verbatim.

- **Regime D — "iff" / "the following are equivalent".** The statement
  asserts that conditions coincide. `assumptions` = only the hypotheses
  shared by both directions ("Let $G$ be a bipartite graph"); the sides are
  not assumptions. `conclusions` = the whole biconditional span (for TFAE,
  the list). Add `equivalent_conditions` = the verbatim span of each side,
  one per element (for TFAE, each item (i), (ii), ...).
  Example: *"Let $G$ be bipartite. Then $G$ has a perfect matching if and
  only if $|N(S)| \ge |S|$ for all $S$."* →
  `assumptions: ["$G$ be bipartite"]`,
  `conclusions: ["$G$ has a perfect matching if and only if $|N(S)| \ge |S|$ for all $S$"]`,
  `equivalent_conditions: ["$G$ has a perfect matching", "$|N(S)| \ge |S|$ for all $S$"]`.
  A paper that states the two directions as two results gets two nodes, each
  in Regime A, and no edge between them (neither proof uses the other).

- **Regime E — several implications in one statement.** "If A, then B.
  Moreover, if also C, then D" is two implications, not "(A and C) give (B and
  D)". Fill `assumptions` and `conclusions` with every span as usual (A, C and B,
  D), and add `parts`, one entry per implication, each `{"assumptions": [...],
  "conclusions": [...]}` with verbatim spans; `"adds_to": k` when the part keeps
  the assumptions of part k (0-based) and adds its own ("if moreover", "if in
  addition", "if also"). Hypotheses shared by every part ("Let $G$ be a graph")
  stay only in the node's `assumptions`. Example: *"Let $A$ be symmetric. If
  $A$ is diagonally dominant, then $A$ is positive semidefinite. If moreover
  its diagonal is positive, then $A$ is positive definite."* →
  `parts: [{"assumptions": ["$A$ is diagonally dominant"], "conclusions": ["$A$ is positive semidefinite"]},
  {"adds_to": 0, "assumptions": ["its diagonal is positive"], "conclusions": ["$A$ is positive definite"]}]`.
  Without `parts`, a node means that all its assumptions together give all its
  conclusions. Two independent implications ("If A then B, and if C then D") are
  two parts with no `adds_to`. Parts proved separately and used separately are
  claims instead (see "Parts proved separately are claims").

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
$X := \{...\}$"), omit `genus`/`differentia`; `definiendum` is the
introduced symbol, written as `$...$` (see "Introduced terms and symbols are
definitions").

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

Do not paraphrase even slightly: the finishing step locates every `statement` in the
prepared source by exact match, and a statement it cannot find fails the
check.

The only edits permitted to the source text are mechanical cleanup that
does not change wording:

- Collapse runs of whitespace and newlines into single spaces.
- Use `facts.json`'s `source`, which has already removed comments and disabled
  regions, inlined `\input` files and expanded the paper's argument-free macros;
  do not undo the expansion.
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

Math is copied character for character too: every `$`, backslash command,
brace and subscript, displays as displays; never normalize or "fix" notation.

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
  (Checked by the finishing step.) One exception: a proof with no proof
  environment that fills a whole section ("5 Proof of Theorem 1.2", with
  subsections 5.1, 5.2, ...) is one `proof` node, from the section's first
  sentence to its end; each subsection is a step of it (a `setup` step for text
  before the first subsection), with child steps by the step rules. It may contain
  the headings of its own subsections, never one of its section's level.
- **One statement per node.** Two separate assumptions, definitions or results
  are two nodes, even in consecutive sentences: "The weights are assumed
  i.i.d. normal. I assume the inputs are i.i.d. with variance 1." is two
  `assumption` nodes, one on the weights and one on the inputs.
- **Introduced terms and symbols are definitions.** In running text outside
  proofs, a sentence that introduces a term or symbol ("Let $X$ be ...", "we
  denote", "we write", "is called", "$X := ...$") is a `definition` node when the
  term or symbol is used again in a later node; its `definiendum` is the term,
  or the symbol written as `$...$`. Each sentence that introduces a term or
  symbol is its own node, even in consecutive sentences. Not covered: a symbol
  used only within its own paragraph, which stays in the text that contains it;
  a "where ..." sentence completing a result (see "Minimal but
  self-contained"), which stays in that result's node; and such a sentence
  inside a proof, which is a step (step rule 4). One sentence that introduces
  several terms or symbols ("we write $X$, $Y$ and $Z$ for ...") is one node,
  with `definiendum` a list of them; nodes never split a sentence. A sentence
  that displays a numbered equation and continues with "where $a$ is ..." is one
  `definition` node when it introduces symbols used later and is not part of a
  result; the equation is nested in it. Never leave out a definition because
  nothing seems to use it: emit it, and let it be an orphan. The finishing step
  warns about some missed symbols (not terms, single letters or single commands);
  finding them is your job.
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
  `proof` node with zero steps. When that sentence leads into the result it
  justifies ("By Lemma 4.2, we see the following:"), the proof node ends at the
  colon; without a colon, the proof node is the whole sentence and the result
  starts at the next sentence. The deciding question: is there a
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
- **One node per repeated statement.** When the paper states the same result,
  definition or equation twice or more (in the abstract or introduction, then
  formally; restated in an appendix or before its proof; an equation displayed
  again), emit one node: the copy that is an environment if only one is, else the
  numbered one, else the fuller statement, else the first (never the abstract's
  copy when the body states it). The other copies get no node: put their verbatim text in the
  kept node's `also_stated_at`. The finishing step then resolves every `\ref` to
  a copy's `\label` to the kept node; add nothing by hand. A copy that differs
  in content (a special case, a weaker form) is not a repeat: it is its own node.
- **A proof sketch.** An informal sketch or "proof idea" of a result the paper
  proves in full elsewhere is a `proof` node with `rigor: semi_formal`, and its
  `proves` edge carries `alternative: true` (one node per part when the sketch is
  split across sections).
- **Parts proved separately are claims.** When the paper proves the parts of a
  result at different places (part (a) in Section 3, part (b) in Section 5) and
  other nodes rely on single parts, emit each part as a `claim` nested in the
  result, whose statement is that part's text; `proves` and `uses` edges go to
  the part they concern.
- **A result proved by other results.** A result with no proof of its own,
  established by results stated elsewhere ("the 'if' part is Proposition 2, the
  'only if' part is Proposition 3"), gets a `uses` edge from each of them. A
  sentence that says how they combine ("Theorem 3 follows from Propositions 2
  and 3") is a `proof` node with a `proves` edge to the result, as for any
  argument in running text.
- **A proof proves a result.** When a proof follows an example or a remark, the
  assertion it proves is a result: emit it as a `claim` nested in the example,
  whose statement is the sentence that asserts it, or retype as `claim` a remark
  whose content is that assertion. The proof's `proves` edge points to the claim.
- **No partial overlap.** Two nodes either do not overlap, or one contains the
  other (a `proof` containing an equation or a nested claim). Two nodes sharing
  some sentences but not others is an error. (Checked by the finishing step.)

## CORE RULE #2 — `statement_short` IS YOUR COMPRESSION

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
`statement`, leave it absent.

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

### Edge coverage — four passes

The finishing step adds only the edges a `\ref` states; every other dependency
is yours. Build the dependency edges in four passes:

1. **References in words.** For every phrase that names another node without a
   `\ref` ("by Lemma 3", "Theorem 2.1 gives", "as in the previous
   proposition"), add a `uses` edge from the named node, confidence `0.9`.
2. **Defined terms.** For each definition, search the prepared source for its
   `definiendum` and for the symbol it introduces, and add a `uses` edge from
   the definition to every later Level-1 node that uses it, confidence
   `0.7`–`0.85`. A use inside a proof gets one edge, to the proof, not one per
   step; a use inside an equation nested in a node gets one edge, to that node.
3. **Results built on results.** For each result and proof, add a `uses` edge
   from every result it applies, earlier or later.
4. **Inside a proof.** A step that relies on an earlier step's conclusion, in the
   same proof, gets a `uses` edge from that step.

**Where a dependency points: the statement or the proof.** A node the result's
*statement* needs (a definition it uses, a result its hypotheses refer to) gets
an edge into the result node. A node used only in the *argument* gets an edge
into the `proof` node (or the step that uses it), not into the result. Example:
Theorem 2 is stated with Definition 1 and proved with Lemma 3: `DP1 → TP2` and
`LP3 → PP2`, never `LP3 → TP2`.

**A result stated inside a proof is used inside it.** A lemma or claim placed in a
proof serves that proof. When a later node relies on it, check the edge's source:
it usually relies on the result the proof proves. Keep the edge only when the
paper really uses the inner result there (the finishing step lists such edges).

A node left without an edge must be one the paper relates to nothing. Never add
an edge to make a node non-isolated, and never drop a node to avoid an orphan. Each `proof` has its `proves` edge, and each
`example` is the target of an `illustrates` edge from the concept it shows.

**Score uncertain edges, do not guess.** Emit a borderline edge with its
`confidence` rather than deciding yes or no:

| `confidence` | when |
|---|---|
| `0.9`–`1.0` | the text explicitly cross-references it in words (`by Lemma 3`; edges a `\ref` states are added by the finishing step), or it is the `proves` edge of a `\begin{proof}` environment (a proof argued in prose: see "Where a prose node starts and ends", `0.6`–`0.95`) |
| `0.7`–`0.85` | no explicit reference, but the logical dependency is clear-cut (the statement uses a term this definition introduces) |
| `0.5`–`0.65` | plausible but genuinely uncertain — emit only if you actually believe it |
| below `0.5` | do not emit |

**Edge basis.** Every edge records how the dependency is known, in `basis`:

| `basis` | when | set by |
|---|---|---|
| `ref` | a `\ref`/`\eqref` in the target states it | the finishing step (also on a `mention` edge you add for a `\ref`) |
| `syntax` | a proof environment's position or its `[Proof of ...]` argument | the finishing step |
| `named` | the text names the source in words: "by Lemma 3", "Cauchy-Schwarz gives", "Proof of Theorem 2:" | you |
| `term` | the target uses a term or symbol the source defines (edge pass 2) | you |
| `inferred` | no marker in the text; you read the dependency from the mathematics | you |

Set `basis` on every edge you add; the finishing step warns about edges without
one. `basis` says how you know, `confidence` how sure you are (an `inferred`
edge is at most `0.8`).

**Direction.** The arrow points **from the thing relied upon** (`source`) **to
the thing that relies on it** (`target`).

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

These are the only edge types: there is no `defines` and no `special_case_of`; a
definition→user link is `uses`, and "special case" is `specializes`.

**Every edge has four required fields: `source`, `target`, `type`, `confidence`**,
plus `basis` (see "Edge basis"), `"backward": true`, which the finishing step sets
by position, and `"mention": true` and `"alternative": true` where Hard rule 7 says.
`confidence` is required (float 0-1, scored per the table above).

**Worked examples** (edges a `\ref` or a proof environment states are added by
the finishing step, so none is shown here):
- lemma LP1 used by theorem TP1, cited in words ("by Lemma 1") with no `\ref`:
  `{"source": "LP1", "target": "TP1", "type": "uses", "confidence": 0.9, "basis": "named"}`
- prose proof PP1 of theorem TP1, labelled "Proof of Theorem 1:" in the text:
  `{"source": "PP1", "target": "TP1", "type": "proves", "confidence": 0.9, "basis": "named"}`
- example ExP1 illustrating definition DP1:
  `{"source": "DP1", "target": "ExP1", "type": "illustrates", "confidence": 0.9, "basis": "named"}`
- algorithm AP1 solving problem ProbP1:
  `{"source": "ProbP1", "target": "AP1", "type": "resolves", "confidence": 0.9, "basis": "inferred"}`
- theorem TP2 resolving open problem OpenP1:
  `{"source": "OpenP1", "target": "TP2", "type": "resolves", "confidence": 0.8, "basis": "inferred"}`
- definition DP2 whose statement uses a term DP1 introduces, no explicit ref:
  `{"source": "DP1", "target": "DP2", "type": "uses", "confidence": 0.75, "basis": "term"}`

**Theorem/definition → algorithm dependency:** when a paper introduces
a theorem (e.g. existence of a factorization) and an algorithm that
computes it, the theorem is a prerequisite of the algorithm:
`theorem → algorithm` with type `uses`. Same for definitions.

## Level-2 steps — proof_step and algorithm_step

Steps do not replace their parent's body. The parent `proof` / `algorithm`
`statement` holds the full verbatim body (core rule #1), and the step nodes are
emitted alongside it.

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

### When to emit a `proof_step`

A step is one move of the argument: an object is introduced, a case is opened, a
lemma or inequality is applied, a bound is established, an intermediate claim is
proved, or the conclusion is drawn. A step need not carry a marker ("Let", "By",
"Since", "Now"…). First decide whether the proof gets steps at all (step rule
9); then apply the step rules below in order.

**1. Author labels (from `facts.json`).** For a proof in prose (no
environment), look for the same kinds of label yourself. Each proof fact carries
`structure.labels`: the places where the paper itself labels its structure,
already detected by the parser: `Step N`, `Case N`, `Part N` and "Case $x=0$:" at the
start of a line; item labels `(i)`/`(a)`/`$(1)$` and numbered items `1.` after
`\smallskip`/`\par`/a blank line/`\\`, when the proof has at least two; prose items of
a list inside the proof; headings `\textbf{...}`, `\emph{...}`, `{\bf ...}`, `{\it ...}`
(also with math, but not "Proof", "Remark" or "Note"); run-in labels "(Injectivity)";
implications "(i)$\Rightarrow$(ii)"; Base case / Inductive step.
Every one of them starts a step. (A nested `\begin{proof}` lies inside a `setup`
step: step rule 10.)
Keep the label token in the step's `statement` (strip only `\item`); the
finishing step checks that every author label starts a step. A label body longer than 2 sentences may get child steps
(`parent_id` = the label's step), segmented by the rules below; it gets none
when it is one move. Text before the
first label is its own `setup` step. A proof with a single label and no text
before it gets zero steps (step rule 9).

**2. Steps end only at sentence ends.** A boundary falls after a `.`, `!`, `?` or
`:` outside math, or at a label. Never inside a display, at a comma, at `;`, or
before "where", "which", "because" continuing the same sentence. The finishing
step checks that each step starts a sentence.

**3. Paragraph breaks.** `structure.paragraph_breaks` lists the breaks that
follow a complete sentence; blank lines around displayed math are not listed.
Such a break starts a new step unless the next paragraph plainly continues the
same move.

**4. Introductions group.** A run of consecutive sentences that only introduce
objects (start with Let, Take, Consider, Define, Fix, Denote, Set, Introduce, and contain no
`\ref`, `\cite`, displayed math, or hence/so/then/thus) is one `introduce_variable`
step. A run of a single such sentence is joined to the step that follows it.

**5. Meta, reduction and recall form `setup` steps.** A sentence that starts with
"it suffices to", "it is enough to", "it remains to", "we only need
to", "the proof is (similar|analogous) to", "is proven exactly as", "we will use",
"recall", "we have remarked" is a `setup` step. A contiguous restatement of a
definition or a cited theorem (including a theorem-style environment quoted inside
the proof) is one `setup` step.

**6. Immediate sentences never stand alone.** A sentence is immediate when it has
no displayed math and no `\ref`/`\eqref`/`\cite`, and contains one of: clear(ly),
obvious(ly), trivial(ly), immediate(ly), at once, easy/easily, straightforward,
tautological, by inspection, similarly, a similar argument, the same argument, as
above, we can verify, left to the reader ("non-trivial" is not "trivial"); or is a
closing formula ("This / That completes / finishes / proves / concludes the …",
`\qed`). An unlabelled immediate sentence
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
follow the opener. A claim the author numbers or names ("Claim 1",
`\begin{claim}`, "Assertion (A)") or cites later is a Level-1 `claim` node
instead, never also a step: its statement spans the claim and its argument (as
the parent step would), the argument's sentences are steps with the claim as
`parent_id`, and no separate `proof` node is made. Among the outer proof's steps
it is not repeated. (The finishing step merges a step that duplicates a claim's
span into the claim.)

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
displays and no label (text after a display that starts with a capital letter is
a new sentence, even when the display has no period). Never emit exactly one step: a body that is one move gets
zero. Likewise a step never has exactly one child.

**10. A proof interrupted by an inner result.** When a proof is interrupted by a
lemma or claim and its own proof, the outer `proof` statement spans the whole
text, inner result included. The inner result and its proof are their own nodes
(their `parent_id`, set by the finishing step, is the outer proof's `setup` step
that spans them). Among the outer
proof's steps the inner block is one `setup` step with no children; the inner
steps belong to the inner proof only.


### When to emit an `algorithm_step`

*Pseudocode* — an algorithm fact with `lines` (pseudocode in `algorithmic`,
`algpseudocode`, `algorithm2e`, or a numbered list in an algorithm float). Its
structure is syntax, so do not segment it yourself. In your build script call

    import sys; sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
    from extraction_finalize import pseudocode_steps
    steps = pseudocode_steps(facts, fact_id, algorithm_node, first_seq=next_free_ASP_number)

It returns one `algorithm_step` per printed line, with the verbatim `statement`
(a loop or branch line spans its body), `parent_id` (the enclosing loop or
branch, or the algorithm), `step_order`, a placeholder `name`, `confidence` 1.0,
and `subclass` for control lines. Then, per step: choose `subclass` where it is
None; write `statement_short` only where the line is not self-explanatory
(`$x \leftarrow x + 1$` needs none); improve `name` if you like. Drop a step only
when its line is not an operation (an algorithm title, an input declaration, or
an `\ENDFOR`/`end` line that the package prints); give a dropped line's children
its `parent_id` and renumber `step_order` within each parent. A line whose text describes several
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

Each step's `statement` is also verbatim: whole sentences for a proof step, the
span of one operation for an unmarked algorithm step, and the printed line for
pseudocode (`pseudocode_steps` gives it). A proof
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
`subclass` from the `subclass` vocabulary above.

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

**Step-node fields.** A step takes its parent's `section` and `origin`; its
`confidence` is `0.95` when it starts at an author label, `0.75` otherwise
(`1.0` for a pseudocode line, as returned; `0.6`–`0.8` for an unmarked algorithm
step). Besides these:
- `id` (e.g. `PSP1`, `ASP1`)
- `type` (`proof_step` or `algorithm_step`)
- `parent_id` (id of the parent node — see "Nesting" below)
- `step_order` (1-based index within the immediate parent)
- `source_line_label` (`algorithm_step` only; filled by the finishing step,
  never by hand)
- `name` (a short descriptive label)
- `statement` (verbatim source span for this step)
- `statement_short` (your compression of the step's role)
- `subclass` (from the controlled vocabulary above)
- `tags[]` (optional, topical)

**Nesting: steps may parent other steps.** A step node may take
another step node as its `parent_id`, to any depth:
- `proof_step` — a label body longer than 2 sentences (step rule 1), an
  inline claim with at least 2 following sentences (step rule 7, required). (A
  numbered or named claim is a Level-1 node with its argument as its steps, step
  rule 7; a `\begin{proof}` inside a proof belongs to its own result, step rule 10.)
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

Steps may reference Level-1 nodes outside their proof or algorithm
(e.g. `proof_step uses Lemma 2.3`), but an edge between steps of different
proofs or algorithms is not permitted.

## Extraction notes

Alongside the graph, record what was unusual about extracting this paper, in
`metadata.paper_style`, `metadata.extraction_notes` and
`metadata.extraction_comment`. Write them plainly and specifically. Add a note when the situation arises, not only at the end.

`paper_style` is how the paper establishes what it says: a list of one or two
of the values below, the dominant one first. Decide it after extracting, from
what you found. Judge the reasoning, not the
layout (a proof written in prose is still `theorem_proof`).
- `theorem_proof`: results stated and proved, including proofs that rest on a
  computer calculation;
- `formal`: results proved in a proof assistant (Lean, Coq, Isabelle, ...);
  the proofs are code listings rather than prose;
- `derivation`: results reached by calculation, approximation and physical or
  intuitive argument, not proved;
- `modeling`: a model, method or algorithm is specified and developed
  (equations of a biological or physical system, a statistical model with its
  likelihood and estimators, a learning method, a controller), with few or no
  theorems;
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
| `cycle` | a cycle the paper's own text states (Hard rule 7): `nodes` = the cycle in order, plus `"kind"` (`wrong_ref`, `granularity` or `circular`) and `"evidence"`: one verbatim quote per edge of the cycle, the words that state it |

Do not summarize the paper, and do not restate what the graph already records
(types, counts, confidence scores). If nothing was unusual, leave the list
empty; do not write a note just to have one.

`extraction_comment` is free text, at most 3 sentences, for something a reader of
this graph should know that fits none of the categories above. Use it only then;
otherwise leave it as an empty string.

## Workflow

0. Run `latex_facts.py` (see "Two layers") and read `facts.json`.
1. Read the prepared `source` (multiple Read calls with offsets if large).
2. Emit a node for every environment fact, except a restated copy (see "One
   node per repeated statement") and one with no mathematical content. Then find everything the facts
   do not cover: definitions, results, remarks, claims, problems and
   algorithms stated in prose, including introduced terms and symbols (see
   "Introduced terms and symbols are definitions") and a cited result the
   paper states in full.
3. Assign compact IDs as you create nodes (see "Compact ID convention").
4. For each node: decide its type (Hard rule 4, type-promotion included), copy
   its `statement` (core rule #1), write its `statement_short` (core rule #2)
   and fill its fields (see "Schema").
5. Apply step extraction for proofs and algorithms (see "Level-2 steps").
6. Build the dependency edges in the four passes of "Edge coverage". (Edges a
   `\ref` states are added by the finishing step in step 7.)
7. In the script you write to build the output (`graph` below is the output
   dict, with `metadata`, `nodes` and `edges`), finish and check it before
   writing it:

       import sys; sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
       from extraction_finalize import finalize
       from latex_facts import read_tex
       report = finalize(graph, read_tex("/mnt/c/Code/Github/Saranga/corpus/orzuk/2601_18662/arxiv_src/revision.tex"))
       assert not report["errors"], report["errors"]

   The graph must already carry its `metadata` (step 8): the finishing step
   checks `paper_style`, `rigor_nonformal_count` and the extraction-note
   categories. It fills the fields and edges listed under "Two layers" and
   validates (verbatim spans, edge types and endpoints, circular reasoning,
   step parents). Fix every error and re-run. Act on each warning, including: a
   defined term or symbol used with no edge (add each edge, unless the word is
   used there in another sense), an introduced symbol with no definition node,
   a definition node whose sentences introduce several symbols (split it), edges
   without a `basis`, and a result stated inside a proof but used outside it
   (check that edge's source).
8. Write the JSON to the output file, /mnt/c/Code/Github/Saranga/corpus/orzuk/2601_18662/2601_18662.json:

   ```json
   {
     "metadata": {
       "title": "...",
       "annotator": "agent-extraction",
       "model": "claude-opus-5-5",
       "effort": "default",
       "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
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

## Pre-output self-check

Before emitting the JSON, walk every node. The finishing step checks that
statements are verbatim, `origin` is set and types are in the vocabulary; it
cannot check these:

1. **Each prose node's span is the right one** (whole sentences, minimal but
   self-contained, no dropped hypothesis).
2. **`statement_short`, when present, is meaningful compression** —
   not a copy-paste of `statement`, not longer than `statement`,
   captures the idea. For proof nodes, verify `statement_short`
   exists.
3. **`origin: external` marks what the paper cites** (Hard rule 3).
4. **`type` follows the content** (Hard rule 4).
5. **`tags[]` is topical only** (Hard rule 8).
6. **Results and conjectures have `assumptions[]`/`conclusions[]`** where they
   decompose, plus `equivalent_conditions` for an "iff" and `parts` for several
   implications (see "Assumption / conclusion decomposition").

## Report

When complete, output:
- node count by type (e.g. "8 definition, 1 theorem, ..."), and how many nodes
  came from environment facts vs prose
- the finishing step's summary: labels filled, edges added, `\ref`s to later
  text (`report["ref_backward"]`), any warnings left
- orphan count, with a one-line reason for any node deliberately left isolated
- **step counts per parent**: for each `proof` and `algorithm` node,
  report `<parent_id>: N steps` (e.g. `PP1: 4 steps`). If N=0,
  justify in one phrase ("single-paragraph body, no part/step labels").
- **`statement_short` coverage**: percentage of nodes that have a
  populated `statement_short`, by type
- edge count by type
- count of `origin: "external"` nodes
- 3 sample node names (drawn from the body), and the nodes marked `main`
- `paper_style`, the extraction notes (one line each) and `extraction_comment`
