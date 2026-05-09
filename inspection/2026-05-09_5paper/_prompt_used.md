<!-- CANONICAL: src/node_types.py and src/edge_types.py.
     This file is derivative; sync it whenever the canonical changes. -->

Extract a mathematics paper or chapter to JSON for the Authomathics project.

This prompt is the **terse + math-aware** variant: keeps the agent
discipline of `opus_extract_prompt.md`, adds explicit LaTeX-preservation
rules and a richer (but optional) edge taxonomy with direction conventions.

## Source

- BID: {BID}
- TITLE: {TITLE}
- AUTHORS: {AUTHORS}
- YEAR: {YEAR}
- TEX SOURCE: {TEX_SOURCE}
- OUTPUT JSON: {OUTPUT_JSON}

## HARD RULES (read carefully — prior agents drifted on these)

1. **NO REGEX-SCRIPT SHORTCUT.** Read the .tex with the Read tool (with
   offsets for large files), understand each section semantically, produce
   structured nodes from your reading. Do NOT write a Python script that
   greps for `Theorem N.M` patterns.

2. **NO FABRICATION.** Every node statement must correspond to text in the
   source. No synthesis from general knowledge or external papers.

3. **PRESERVE THE CANONICAL NAMES.** When a paper introduces a named
   object ("Sinkhorn-Knopp algorithm", "Markov's inequality", "PCA"), use
   that exact name. Do NOT rename it to a more abstract or general
   description ("fixed-point iteration", "moment inequality"). The named
   identity is part of the paper's contribution.

4. **PRESERVE LaTeX MATH.** This is essential.
   - Wrap inline math in `$..$` (e.g. `$\Sigma_d$`, not bare `Sigma_d`).
   - Keep all backslashes: `\Sigma`, `\sum`, `\int`, `\in`, `\subset`,
     `\mathbb`, `\mathcal`, `\langle`, `\rangle`, `\nabla`, `\defeq`,
     `\bar`, `\hat`, `\tilde`, `\frac`, etc.
   - Greek letters: `$\alpha, \beta, \gamma, \delta, \epsilon, \theta,
     \lambda, \mu, \pi, \rho, \sigma, \tau, \phi, \omega$` and capitals.
   - Operators: `$\arg\min, \arg\max, \log, \exp, \min, \max, \sup, \inf$`.
   - Sets/spaces: `$\mathbb{R}, \mathbb{Z}, \mathbb{N}, \mathbb{P}$`.
   - Subscripts `_{ij}` and superscripts `^{T}` use braces when >1 char.
   - In JSON, escape backslashes properly: `"\\Sigma"` produces `\Sigma`.

5. **statement_latex vs statement vs statement_clean.** Provide BOTH:
   - `statement_latex` (or `statement` — pick one and be consistent):
     full LaTeX-preserved statement, with `$..$` math.
   - `statement_clean`: optional 1-sentence English paraphrase, math-free
     where possible.

6. **KEEP `statement` SHORT.** Limit `statement` / `statement_latex` to
   ≤2 sentences (≤250 chars). The visualizer renders this in a small
   box — long bodies bloat the layout and crowd the DAG.
   - For ALGORITHMS specifically: `statement` is a 1-sentence summary
     ("Iterative matrix-scaling algorithm that computes
     $d_M^\\lambda$"), NOT the pseudocode. Put the actual procedure
     into the `input`, `output`, and (optionally) `pseudocode` fields.
     Do NOT dump multi-line `\textbf{Input}` / `\textbf{While}` /
     `\textbf{End while}` blocks into `statement` — they break math
     rendering AND visual layout.
   - For PROOFS: `statement` is the proof's strategy sentence
     ("By induction on $n$"), not the full proof. The proof body
     decomposes into `proof_step` nodes (Level 2; see rule 10) when
     the proof has clear semantic divisions.

7. **Map `\newtheorem{property}` and similar to standard types.** If the
   paper defines a custom `\newtheorem{X}{...}` environment with name
   "property", "claim", "fact", "principle", "observation", etc., map
   the node `type` to one of the standard schema types — typically
   `proposition` (for assertions) or `claim`. Do NOT emit a custom
   `type="property"` value — the visualizer color map only knows the
   schema's standard types.

7b. **TYPE-PROMOTION RULE — content trumps environment.** A node's type is
   determined by its semantic CONTENT, not the surrounding LaTeX environment.

   - A `\begin{definition}` block whose body is an OPTIMIZATION FORMULATION
     (e.g. `x^* = \arg\min_x f(x)` subject to constraints, or a named
     problem with attached algorithms / complexity / hardness) MUST be
     emitted as `type="problem"` (typically `subclass="optimization"`),
     NOT `type="definition"`.
     Diagnostic: does the object come with the recurring problem-attachments
     (algorithms that solve it, complexity bounds, dual formulation,
     hardness results)? If yes -> `problem`.
   - A `\begin{definition}` block whose body is a step-by-step procedure
     becomes `type="algorithm"`.
   - A `\begin{lemma}` / `\begin{proposition}` whose body is a numerical
     bound used as scaffolding remains a lemma / proposition (the
     environment captures the author's intent here).

   See `Manuscript/node_types_appendix_draft.tex` ("Type-promotion rule")
   for the canonical statement.

7c. **CITED PRIOR RESULTS — emit as `origin: "external"`.** Mathematical
   papers depend on prior work. A graph that captures only this paper's
   own contributions is missing its scaffolding. EXTRACT the cited
   classical theorems, foundational definitions, and baseline algorithms
   that the paper INVOKES but does not ESTABLISH.

   Each node carries an `origin` field:
   - `"paper"` (default) — node is a contribution introduced by THIS paper.
   - `"external"` — node is a CITED PRIOR RESULT the paper uses but does
     not prove (a classical theorem, a baseline algorithm, a foundational
     definition from a cited source).

   For `origin: "external"` nodes, also set `origin_citation` to a short
   free-text identifier of the cited source.

   Example 1 (cited classical theorem):

   ```json
   {
     "id": "TP5.3",
     "type": "theorem",
     "name": "Information-Theoretic Inequality",
     "section": "3.1 (cited)",
     "statement": "For all $r,c \\in \\Sigma_d$ and $P \\in U(r,c)$: $h(P) \\leq h(r) + h(c)$, with equality iff $P = rc^T$.",
     "origin": "external",
     "origin_citation": "Cover & Thomas, Elements of Information Theory"
   }
   ```

   Example 2 (baseline algorithm cited for comparison):

   ```json
   {
     "id": "AP5.2",
     "type": "algorithm",
     "name": "Network Simplex Method for OT",
     "section": "2.2 (cited)",
     "statement": "Combinatorial LP solver for optimal transportation with worst-case complexity $O(d^3 \\log d)$.",
     "origin": "external",
     "origin_citation": "Ahuja, Magnanti, Orlin 1993"
   }
   ```

   Trigger phrases: "by X", "as shown in [REF]", "we use the classical
   result of Y", "we compare against the baseline Z" -> `origin: "external"`.

8. **COMPLETENESS — DO NOT DROP THEOREM-LIKE RESULTS.** Every numbered
   or labeled stated result in the .tex source MUST produce a
   theorem-like node (type ∈ {theorem, lemma, proposition, corollary,
   claim}). Specifically:
   - Every `\begin{theorem}` → `theorem` node
   - Every `\begin{lemma}` → `lemma` node
   - Every `\begin{proposition}` → `proposition` node
   - Every `\begin{corollary}` → `corollary` node
   - Every `\begin{property}` (custom env) → `proposition` node
   - Every `\begin{claim}` → `claim` node

   **Do NOT demote a stated result to an `equation` node** even if the
   paper presents it inside `\begin{equation}...\end{equation}` blocks.
   If the text says "the optimal $P^\\lambda$ has the unique form
   $P^\\lambda = \\diag(u) K \\diag(v)$ ... [Sinkhorn's theorem]" — that
   is a **theorem** (existence/uniqueness statement), even though
   `P^\\lambda = \\diag(u) K \\diag(v)` looks like just an equation.
   Promote it to a `theorem` node and additionally emit the equation as
   an `equation` node if helpful, but the *result* must be a theorem.

   Same for cited-but-relied-on results: if the paper says "by
   Sinkhorn's theorem [reference], …", create a `theorem` node for that
   statement (mark in the `name`/`statement` that it is cited). The
   downstream graph uses these as prerequisites; encoding them as
   equations breaks dependency tracking.

   In short: count the labeled `\begin{X}...\end{X}` environments in
   the source; the number of theorem-like nodes you emit must be ≥ that
   count (it can be greater if cited-results are added).

9. **ACYCLICITY (DAG CONSTRAINT).** The within-paper graph must be a
   directed acyclic graph (DAG). Mathematical dependency cannot be
   circular: a theorem cannot depend on a result that itself depends
   on that theorem. When emitting a `uses` edge $A \to B$ (read "B
   uses A"), make sure $A$ is logically prior to $B$ in the paper's
   dependency order. If two nodes appear to cite each other in the
   text, pick the single direction that reflects the actual logical
   dependency (typically the one where the source is stated/proved
   later in the paper depends on the earlier-stated one). Reciprocal
   `uses` edges in both directions are NOT permitted; pick one. The
   downstream validator runs cycle detection and flags violations.

10. **LEVEL-2 STEP EXTRACTION (default-on, semantic-driven).** Decompose
    `proof` and `algorithm` nodes into Level-2 step nodes
    (`proof_step`, `algorithm_step`) WHEN the proof or algorithm has
    a clear semantic decomposition. Triggers:

    - **Explicit numbering**: "Step 1: …; Step 2: …; Step 3: …" or
      "We proceed in three parts…" or numbered cases ("Case 1: …;
      Case 2: …").
    - **Signposted prose** (even without explicit "Step N" labels):
      "First, we show …", "Now consider …", "Applying [lemma], …",
      "It remains to show …", "Combining the above, we conclude …",
      "Suppose for contradiction …", "By induction on $n$: base case …
      inductive step …".

    For short proofs without internal divisions (one paragraph, single
    argument), emit ZERO step nodes; the proof's `statement` field
    carries the whole content. Same for one-line algorithms.

    Each step node has:
    - `id` (e.g. `PSP5.1`, `ASP5.1` for paper 5 step 1)
    - `type` (`proof_step` or `algorithm_step`)
    - `parent_id` (id of the parent `proof` or `algorithm` node)
    - `step_order` (1-based sequential index within the parent)
    - `name` (a short descriptive label, e.g. "Set up gluing matrix",
      "Inductive step on $n$", "Initialize $u, v$")
    - `statement` (1–2 sentences of LaTeX-preserved content, OR for
      `algorithm_step`, the pseudocode line/block)
    - `subclass` (optional structural role from controlled vocabulary:
      `setup`, `introduce_variable`, `apply_lemma`, `case_split`,
      `induction_step`, `contradiction_setup`, `algebraic_manipulation`,
      `substitute`, `bound_estimate`, `invoke_identity`, `conclude`
      for proof steps; `initialize`, `loop`, `branch`, `update`,
      `return` for algorithm steps)
    - `tags` (optional list)

    **Steps form a sub-DAG.** Emit `uses` edges between steps with
    the same `parent_id` to capture intra-proof / intra-algorithm
    dependencies. Examples:
    - Linear: $\text{PSP5.1} \to \text{PSP5.2} \to \text{PSP5.3}$
    - Case analysis: $\text{PSP5.1} \to \text{PSP5.2a}$,
      $\text{PSP5.1} \to \text{PSP5.2b}$,
      $\text{PSP5.2a} \to \text{PSP5.3}$,
      $\text{PSP5.2b} \to \text{PSP5.3}$ (with `subclass=case_split`
      on PSP5.1 and `subclass=case` on PSP5.2a/b)
    - Induction: PSP5.1 (base) and PSP5.2 (IH) both feed into
      PSP5.3 (inductive step) via `uses` edges

    A step's `uses` edges may also point to Level-1 nodes outside
    its parent (e.g. proof_step uses Lemma 2.3 → edge from LP*.* to
    PSP*.*). Edges between steps of *different* parents are NOT
    permitted; cross-proof references must go through Level-1 nodes.

    **Loops** in algorithms are represented by a single
    `subclass=loop` step whose `statement` / `pseudocode` field
    describes the body; do NOT replicate the body as separate iteration
    nodes. Same for branches: a single `subclass=branch` step whose
    statement describes both alternatives, OR a branch step plus
    sibling case-step children if the alternatives are conceptually
    distinct.

    The parent `proof.statement` / `algorithm.pseudocode` field
    remains the verbatim content; steps capture the decomposition.

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

Important type splits:
- `problem` vs. `open_problem`:
  - `problem` = a NAMED OR FORMULATED FORMAL mathematical problem the
    paper studies. E.g. an optimization formulation
    "$x^* = \arg\min_x f(x)$ s.t. $Ax = b$", or a named decision
    problem like "3-SAT" or "the knapsack problem".
  - `open_problem` = an UNSOLVED mathematical question with no known
    solution. E.g. "Open problem: are there infinitely many odd
    perfect numbers?" Similar to `conjecture` semantically, but
    content-wise more like a question without a stated answer.
- `assumption` (Level 1 node) ≠ the per-theorem `assumptions` field.
  An `assumption` node is a `\begin{assumption}` block declaring
  standing assumptions for a section/theorem cluster
  (e.g. "(A1) f is convex; (A2) X is bounded").

Required node fields:
- `id`: compact ID (see below)
- `type`: from above list
- `name`: display name (canonical name from paper)
- `statement` (or `statement_latex`): the body, math-preserved per rule 4
- `section`: section label from paper

Optional node fields when applicable:
- `origin`: `"paper"` (default) or `"external"` (cited prior result —
  see rule 7c)
- `origin_citation`: free-text source identifier, required when
  `origin="external"` (e.g. `"Sinkhorn 1967"`)
- `assumptions[]`, `conclusions[]` (theorem-like, when source separates them)
- `parent_id`, `proves` (proofs and Level-2 sub-blocks; legacy
  `parent_proof` / `parent_algorithm` still accepted)
- `input[]`, `output[]` (algorithms — see schema rule below)
- `steps[]` (with_proof_steps mode only)
- `tags[]`: optional `list[str]` of type-specific tags from a controlled
  vocabulary (see `TAGS_VOCABULARY` in `src/node_types.py`). Validators
  warn but do NOT reject unknown tags. Examples: `theorem` →
  `["existence", "uniqueness", "bound"]`; `algorithm` →
  `["iterative", "approximation"]`. Emit only tags you are confident in.

**Schema rule for `assumptions` / `conclusions` on theorem-like nodes:**

A theorem-like node (theorem, lemma, proposition, corollary, claim) falls
into one of three regimes — populate `assumptions` and `conclusions`
accordingly. `conclusions` is **always** populated; `assumptions` may be
empty in Regime C.

- **Regime A — explicit if/then.** Statement contains "if X, then Y" or
  "let X. then Y" or "suppose X. Y". Put the antecedent(s) in
  `assumptions`, the consequent(s) in `conclusions`.
  Example: *"If $X \sim \mathcal{N}(0,1)$ and $t > 0$, then
  $P(X > t) \le e^{-t^2/2}$."*
  → `assumptions: ["$X \sim \mathcal{N}(0,1)$", "$t > 0$"]`,
    `conclusions: ["$P(X > t) \le e^{-t^2/2}$"]`.

- **Regime B — bare statement with free variables.** Statement is a
  single inequality / equation / claim, but has typed variables or
  objects whose declarations live in surrounding text. Recover the
  declarations from context and put them in `assumptions`; the asserted
  fact goes in `conclusions`.
  Example: *"Theorem. $\|x\|_1 \le \sqrt{n} \, \|x\|_2$."* (with
  surrounding text declaring $x \in \mathbb{R}^n$).
  → `assumptions: ["$x \in \mathbb{R}^n$"]`,
    `conclusions: ["$\|x\|_1 \le \sqrt{n} \, \|x\|_2$"]`.

- **Regime C — pure identity / unconditional fact.** Statement is a
  closed-form equality or universal fact with no free variables and no
  recoverable preconditions. `assumptions` may be empty.
  Example: *"Theorem. $e^{i\pi} + 1 = 0$."*
  → `assumptions: []`, `conclusions: ["$e^{i\pi} + 1 = 0$"]`.

Default to Regime B over Regime C: most theorems with free variables
have implicit declarations in surrounding text — recover them.

**Schema rule for `input` / `output` / `assumptions` / `conclusions`:**
these MUST be JSON **arrays of strings**, one bullet point per array
element, NOT a single concatenated string. Example for an algorithm:

```json
"input":  ["Cost matrix $M$", "Regularization parameter $\\lambda$",
           "Marginals $r$ and $c$"],
"output": ["Dual-Sinkhorn divergence $d_M^\\lambda(r,c)$",
           "Scaling vectors $u, v$ such that $P^\\lambda = \\mathrm{diag}(u)\\,K\\,\\mathrm{diag}(v)$"]
```

Do NOT write `"input": "Cost matrix M, regularization parameter ..."`
as one big string — the visualizer iterates each list element as a
bullet, and collapsing into a string makes it iterate character by
character.

Compact ID convention: `{PREFIX}{paper_num}.{seq}` where:

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

Use the edge type that fits, but **do not force edges**. Only emit an
edge when the text explicitly cross-references the dependency or when
the logical dependency is clear-cut. A graph with 2 well-justified edges
beats one with 10 speculative ones.

Convention: edge `source → target` means "source is a prerequisite /
support for target".

| Edge type | Semantics | Direction |
|---|---|---|
| `uses` | Source is invoked by target as a prerequisite | prereq → user |
| `proves` | Source is the proof of the target theorem | proof → theorem |
| `solves` | Source algorithm computes/solves target problem | algorithm → problem |
| `defines` | Source definition introduces the object referenced in target | definition → user |
| `illustrates` | Source example illustrates target | **algorithm/thm → example**, NOT example → algorithm. ALWAYS use this type (NOT `uses`) for algorithm-to-example edges. |
| `special_case_of` | Source is a special case of target | specific → general |
| `generalizes` | Source generalizes target | general → specific |
| `resolves` | Source open_problem/conjecture is settled by target theorem-like result | open_problem/conjecture → theorem-like (theorem, lemma, proposition, corollary, claim) |

**Critical direction rule for `illustrates`:** an example *demonstrates*
or *applies* an algorithm/theorem. The example is the **dependent**, the
algorithm/theorem is the **prerequisite**. So edges go
`algorithm → example`, NOT `example → algorithm`. If you write an edge
with an example as `source` and an algorithm as `target`, you are saying
"this example is required to define the algorithm" — which is virtually
never true.

**Theorem/definition → algorithm dependency:** when a paper introduces a
theorem (e.g. existence of a factorization) and an algorithm that
computes it, the theorem is a prerequisite of the algorithm. Edge:
`theorem → algorithm` with type `uses`. Same for definitions: the
definition specifies what the algorithm computes, so
`definition → algorithm` with type `uses`.

**Algorithm → example edges:** when a paper applies an algorithm to a
specific instance (MNIST experiment, random-simplex test, etc.), the
example is downstream of the algorithm. Edge: `algorithm → example`
with type **`illustrates`** (NOT `uses`). The relationship is "the
example illustrates the algorithm", not "the algorithm uses the
example".

## Workflow

1. Read the .tex file (use multiple Read calls with offsets if large).
2. Identify all definitions, theorems, lemmas, propositions, corollaries,
   algorithms, examples, problems, remarks, equations.
3. Assign compact IDs in source order per type.
4. For each node, write `statement` (or `statement_latex`) with full
   math preservation per rule 4. Be especially careful about backslashes
   in JSON encoding.
5. Build edges from explicit cross-references in the text ("by Theorem
   X.Y", "applying Lemma Z", "as illustrated in Example W") and from
   clear logical dependencies. Apply the direction conventions above.
6. Write the JSON to OUTPUT_JSON with this top-level structure:

   ```json
   {
     "metadata": {
       "title": "...",
       "paper_num": N,
       "annotator": "agent-extraction",
       "model": "claude-opus-4-7",
       "prompt_version": "v3_combined",
       "extraction_date": "YYYY-MM-DD"
     },
     "nodes": [...],
     "edges": [...]
   }
   ```

## Report (<200 words)

When complete, output:
- node count by type (e.g. "8 definition, 1 theorem, ...")
- edge count by type
- 3 sample node names (drawn from the body)
- any anomalies (missing names, ambiguous structure)

## Reference: a good extraction looks like this

For Cuturi 2013 ("Sinkhorn Distances"), the canonical structure has:
- 5–10 definitions (probability simplex, transportation polytope,
  entropy, Sinkhorn divergence, etc.)
- 1–3 theorems / propositions (Sinkhorn factorization existence)
- 1 algorithm: `AP5.1 = Sinkhorn-Knopp algorithm` (NOT
  "fixed-point iteration")
- 1–2 problems / examples
- Edges: `definition → algorithm (uses)`,
  `theorem → algorithm (uses)`, `algorithm → problem (solves)`,
  `algorithm → example (illustrates)` — examples DEMONSTRATE the
  algorithm, they do not feed into it.
