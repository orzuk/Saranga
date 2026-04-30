# Annotation JSON Schema

<!-- CANONICAL: src/node_types.py and src/edge_types.py.
     This file is derivative; sync it whenever the canonical changes. -->

Unified format for mathematical knowledge graph annotations.
Used by all extractors (baseline, LLM, student submissions) and evaluation tools.

## Top-level structure

```json
{
  "metadata": { ... },
  "nodes": [ ... ],
  "edges": [ ... ]
}
```

### `metadata` (optional)

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Paper/chapter title |
| `paper_num` | int | Paper number in the course dataset |
| `paper_id` | string | arXiv ID (e.g., `"0711.0189"`) |
| `sections` | string | Section range covered |
| `annotator` | string | Who/what produced this annotation |

---

## Nodes

Each node is a mathematical object. Required fields are marked with **R**, optional with **O**.

### Common fields (all node types)

| Field | Req | Type | Description |
|-------|-----|------|-------------|
| `id` | **R** | string | Unique identifier. Convention: `<type_letter>P<paper>.<seq>` (e.g., `DP1.1`, `TP3.2`) or simple `T1`, `D2` |
| `type` | **R** | string | One of the types below |
| `name` | **R** | string or null | Descriptive name (e.g., "Markov's Inequality") |
| `section` | O | string | Section number (e.g., `"3.1"`) |
| `statement` | **R** | string | Clean 1-3 sentence summary |
| `raw_latex` | O | string | Original LaTeX source |
| `clean_text` | O | string | LaTeX with math replaced by `[MATH]` |
| `label` | O | string | LaTeX `\label{...}` value |
| `env_name` | O | string | LaTeX environment name (e.g., `"theorem"`, `"definition"`) |
| `index` | O | int | Running index per type (1-based) |
| `spans` | O | list | Fine-grained semantic spans (see below) |
| `origin` | O | string | Provenance: `"paper"` (default) or `"external"` (cited prior result the paper invokes but does not establish — see below) |
| `origin_citation` | O | string | For `origin: "external"` nodes only: free-text source identifier (e.g., `"Sinkhorn 1967"`, `"Cover & Thomas, Elements of Information Theory"`) |

### Origin attribution

Every node carries an optional `origin` field:

- `"paper"` (default; assumed when missing for backwards compatibility) —
  node represents a contribution introduced by the paper being extracted.
- `"external"` — node represents a cited prior result the paper invokes but
  does not establish: a classical theorem (e.g., "Sinkhorn 1967"), a
  baseline algorithm used for comparison, a foundational definition the
  paper depends on, etc.

External nodes additionally carry an `origin_citation` string identifying
the cited source. Both `paper`-origin and `external`-origin nodes use the
same node types — the distinction is preserved so that visualizations can
hide cited-prior nodes by default and so cross-paper analyses can identify
shared external dependencies. Constants `ORIGIN_PAPER`, `ORIGIN_EXTERNAL`,
and helper `normalize_origin()` live in `src/node_types.py`.

### Node types

18 types organized into Level 1 (paper-level, 16) and Level 2 (sub-block, 2).
Constants defined in `src/node_types.py`.

**Theorem-like** (state a claim with assumptions/conclusions) [Level 1]:

| Type | Description |
|------|-------------|
| `theorem` | Theorem |
| `lemma` | Lemma |
| `proposition` | Proposition |
| `corollary` | Corollary |
| `claim` | Informal claim, "Fact", "Observation" |
| `conjecture` | Explicitly unproven claim with a stated answer the author believes |

**Foundational** [Level 1]:

| Type | Description |
|------|-------------|
| `definition` | Mathematical definition of a named concept |
| `proof` | Proof of a theorem/lemma/proposition/corollary |

**Pedagogical** [Level 1] (primarily in textbooks):

| Type | Description |
|------|-------------|
| `example` | Worked example illustrating a concept |
| `exercise` | Pedagogical problem for the reader ("Show that...", "Compute...") |

**Other mathematical content** [Level 1]:

| Type | Description |
|------|-------------|
| `problem` | A *named or formulated formal mathematical problem*: optimization formulations ("argmin f(x) s.t. Ax<=b"), decision problems ("3-SAT"), named problems with attached algorithms / complexity / hardness ("the knapsack problem"). What the paper STUDIES. |
| `open_problem` | An unsolved mathematical *question* with no known solution. E.g. "Are there infinitely many odd perfect numbers?", "Is P = NP?", the Riemann Hypothesis posed as a question. Similar to `conjecture` semantically, but content-wise more like a question without a stated answer. |
| `equation` | Explicitly labeled/numbered equation referenced by number |
| `algorithm` | Pseudocode or step-by-step procedure |
| `remark` | Author's remark, note, observation |
| `assumption` | A `\begin{assumption}` block declaring standing assumptions for a section/theorem cluster ("(A1) f is convex; (A2) X is bounded"). Distinct from the per-theorem `assumptions` field. |

**Sub-block decomposition** [Level 2 — emitted only at fine-grained granularity]:

| Type | Description |
|------|-------------|
| `proof_step` | One logical move within a `proof`. **First-class node**, linked via `parent_id` (or legacy `parent_proof`) to its enclosing proof. |
| `algorithm_step` | One numbered line of pseudocode within an `algorithm` node. Linked via `parent_id` (or legacy `parent_algorithm`). |

**Note:** `exercise` ≠ `problem` ≠ `open_problem`. An exercise is pedagogical
(author knows the answer). A problem is a formally formulated mathematical
object the paper studies. An open_problem is an unsolved question with no
known solution.

**Optional `tags` field** (any node): a `list[str]` of type-specific tags
drawn from `TAGS_VOCABULARY` in `src/node_types.py`. Validators warn but
do not reject unknown tag values. Examples: `theorem` → `["existence",
"uniqueness", "bound"]`; `algorithm` → `["iterative", "approximation"]`.

### Extra fields by type

**Theorems, lemmas, corollaries, propositions, conjectures:**

| Field | Req | Type | Description |
|-------|-----|------|-------------|
| `assumptions` | O | list of strings | Conditions / hypotheses |
| `conclusions` | O | list of strings | What the theorem concludes |
| `assumption_spans` | O | list of Span | Fine-grained assumption structure |
| `statement_spans` | O | list of Span | Fine-grained statement structure |

**Proofs:**

| Field | Req | Type | Description |
|-------|-----|------|-------------|
| `proves` | **R** | string | ID of the theorem/lemma this proves |
| `proof_strategy` | O | string | Short tag: `"contradiction"`, `"induction"`, `"direct"`, etc. |
| `strategy_tags` | O | list of strings | Multiple strategy tags |

**Proof steps** [Level 2 — emitted only at `with_proof_steps` granularity]:

| Field | Req | Type | Description |
|-------|-----|------|-------------|
| `parent_id` | **R** | string | ID of the parent Level 1 `proof` node (preferred). Legacy field `parent_proof` is still accepted. |
| `step_order` | O | int | 1-based sequential index within the parent proof |
| `depends_on_step_ids` | O | list of strings | Other `proof_step` IDs in same proof this step uses |
| `uses_node_ids` | O | list of strings | External nodes (lemmas/defs) invoked in this step |
| `move_type` | O | string | Tag: `setup`, `introduce_variable`, `apply_lemma`, `case_split`, `induction_step`, `contradiction_setup`, `algebraic_manipulation`, `substitute`, `bound_estimate`, `invoke_identity`, `conclude`, `other` |

**Algorithm steps** [Level 2 — emitted only at fine-grained granularity]:

| Field | Req | Type | Description |
|-------|-----|------|-------------|
| `parent_id` | **R** | string | ID of the parent Level 1 `algorithm` node (preferred). Legacy field `parent_algorithm` is still accepted. |
| `step_order` | O | int | 1-based sequential index within the parent algorithm |
| `pseudocode` | O | string | The raw pseudocode line for this step |

**Design note:** proof steps are modeled as **first-class nodes** (with their own IDs, appearing in the top-level `nodes` list), not as a nested `steps[]` array inside the parent `proof`. This matches the course-chapter corpus convention and allows equations to reference a specific step via `parent_step`. The legacy nested `steps[]` form is deprecated — if encountered in older JSONs, migrate to first-class `proof_step` nodes.

**Universal `rigor` field** (available on ALL node types):

| Field | Req | Type | Description |
|-------|-----|------|-------------|
| `rigor` | O | string | How rigorous the justification is. Orthogonal to `type` (which reflects the author's label). |

| Value | Meaning | Typical fields |
|-------|---------|---------------|
| `formal` | Precise statement, rigorous proof | Pure math, CS theory |
| `semi_formal` | Precise statement, proof sketch | Math statistics |
| `heuristic` | Result justified by physical/intuitive argument | Theoretical physics |
| `numerical` | Supported by simulation/computation only | Applied ML, biology |
| `conjectural` | Stated without justification | Any field |

Example: a math "Claim 1" with a full proof → `type: "claim", rigor: "formal"`.
A physics result without rigorous proof → `type: "claim", rigor: "heuristic"`.
A physics paper that explicitly labels something "Theorem" → `type: "theorem", rigor: "heuristic"`.

**Universal `subclass` field** (available on ALL node types):

| Field | Req | Type | Description |
|-------|-----|------|-------------|
| `subclass` | O | string | Finer categorization within the node type. Valid values depend on `type`. |

Subclass values by type:

| Type | Valid subclass values |
|------|---------------------|
| `definition` | `concept`, `model`, `estimator`, `loss_function`, `metric`, `notation`, `space`, `operator` |
| `theorem` / `proposition` | `existence`, `uniqueness`, `convergence`, `bound`, `characterization`, `equivalence`, `impossibility` |
| `lemma` | `technical`, `auxiliary`, `key` |
| `corollary` | `consequence`, `special_case` |
| `conjecture` | `open`, `folklore` |
| `claim` | `existence`, `bound`, `convergence`, `characterization` |
| `proof` | `direct`, `contradiction`, `induction`, `construction`, `probabilistic`, `combinatorial`, `algebraic` |
| `proof_step` | `setup`, `introduce_variable`, `apply_lemma`, `case_split`, `induction_step`, `contradiction_setup`, `algebraic_manipulation`, `substitute`, `bound_estimate`, `invoke_identity`, `conclude`, `other` |
| `algorithm` | `exact`, `approximation`, `heuristic`, `randomized`, `online`, `greedy`, `iterative` |
| `problem` | `optimization`, `decision`, `search`, `counting`, `sampling`, `estimation` |
| `example` | `illustrative`, `counterexample`, `computational`, `applied` |
| `exercise` | `computational`, `theoretical`, `proof_exercise`, `programming` |
| `equation` | `identity`, `inequality`, `recursion`, `differential`, `bound` |
| `remark` | `historical`, `technical`, `motivational` |

Example: a statistical model is `type: "definition"` with `subclass: "model"`.
An optimization formulation is `type: "problem"` with `subclass: "optimization"`.

**Algorithms** (extra fields beyond subclass):

| Field | Req | Type | Description |
|-------|-----|------|-------------|
| `solves` | O | string | ID of the problem node this algorithm addresses |
| `approximation_ratio` | O | string | e.g. `"1.5"`, `"O(log n)"`. null if exact. |
| `complexity` | O | string | Time complexity: `"O(n^2)"`, `"O(m log m)"`, etc. |
| `space_complexity` | O | string | Space complexity (optional) |

**Problems** (extra fields beyond subclass):

| Field | Req | Type | Description |
|-------|-----|------|-------------|
| `complexity_class` | O | string | `"P"`, `"NP-hard"`, `"NP-complete"`, `"PSPACE"`, `"undecidable"` |
| `approximability` | O | string | `"PTAS"`, `"FPTAS"`, `"APX-hard"`, `"inapproximable"`, null |

**Definitions:**

| Field | Req | Type | Description |
|-------|-----|------|-------------|
| `definiendum` | O | Span | The thing being defined |
| `genus` | O | Span | What category it belongs to (e.g., "is a matrix") |
| `differentia` | O | list of Span | Distinguishing conditions |

**Algorithms:**

| Field | Req | Type | Description |
|-------|-----|------|-------------|
| `input` | O | list of strings | Input description |
| `output` | O | list of strings | Output description |
| `input_params` | O | list of AlgoParam | Structured input parameters |
| `output_params` | O | list of AlgoParam | Structured output parameters |
| `steps` | O | list | Algorithm steps |

### Span object (optional substructure)

```json
{
  "kind": "assumption",
  "text": "Let X be a random variable",
  "start": 42,
  "end": 71
}
```

---

## Edges

Each edge represents a dependency or relationship between nodes.

| Field | Req | Type | Description |
|-------|-----|------|-------------|
| `source` | **R** | string | ID of the supporting/source node |
| `target` | **R** | string | ID of the dependent/target node |
| `type` | O | string | Relationship type (default: `"dependency"`) |
| `note` | O | string | Free-text annotation about this edge |
| `confidence` | O | float | Confidence score (0-1) |

**Edge direction convention:** an edge from A to B means "B depends on A" or "A supports B".

### Edge types

**Direction convention:** Arrow from A to B means "A supports B" / "B depends on A."
Edge name reads as "B [name] A" (target's action on source).

**Dependency edges** (B depends on A):

| Type | "B [type] A" | Description |
|------|-------------|-------------|
| `uses` | "B uses A" | Generic dependency. B's statement or proof references A. Default when no specific semantic relationship applies. |
| `generalizes` | "B generalizes A" | B is more general than A (weaker assumptions or broader scope). Subtype of `uses`: implies dependency. |
| `specializes` | "B specializes A" | B is a special case of A (stronger assumptions). Subtype of `uses`: implies dependency. |

`generalizes` and `specializes` are subtypes of `uses`. To query all
dependencies: `type in {"uses", "generalizes", "specializes"}`.
Never create both `uses` and `generalizes` between the same pair — use the more specific type.

**Structural edges** (B is connected to A):

| Type | "B [type] A" | Description |
|------|-------------|-------------|
| `proves` | "B proves A" | B is a proof establishing theorem A. Each proof has exactly one `proves` edge. |
| `solves` | "B solves A" | B is an algorithm solving/addressing problem A. Parallels `proves`. |
| `illustrates` | "B illustrates A" | B is an example demonstrating concept A. |
| `tests` | "B tests A" | B is an exercise testing concept A. |

**External edges:**

| Type | Description |
|------|-------------|
| `grounded_to` | Paper node linked to a known result in the foundation graph (NaturalProofs/Mathlib). |

**Deprecated** (accepted on input, normalized internally):
`dependency` → `uses`, `follows_from` → `uses`, `equivalent_to` → two `generalizes` edges.

Extractors may output just `{"source": "A", "target": "B"}` (no type); defaults to `uses`.

---

## Student-facing (minimal) vs. research (full) format

The same JSON schema is used for both. The difference is which optional fields are populated:

**Student (minimal):** `id`, `type`, `name`, `statement`, `section`, `assumptions`, `conclusions`, `proves`, `proof_strategy`, plus edges with `source` and `target`.

**Research (full):** All of the above plus `raw_latex`, `clean_text`, `label`, `env_name`, `spans`, `definiendum`, `confidence`, edge `type`, etc.

To strip a full annotation to student format:

```python
from annotation_utils import strip_to_student_format
student_json = strip_to_student_format(full_json)
```

---

## Example: minimal (student) annotation

```json
{
  "metadata": {"title": "Example Paper"},
  "nodes": [
    {
      "id": "D1.1",
      "type": "definition",
      "name": "Graph Laplacian",
      "section": "2.1",
      "statement": "The graph Laplacian is L = D - W."
    },
    {
      "id": "T1.1",
      "type": "theorem",
      "name": "Properties of L",
      "section": "2.2",
      "statement": "L is positive semi-definite with smallest eigenvalue 0.",
      "assumptions": ["G is an undirected weighted graph"],
      "conclusions": ["L is positive semi-definite", "Smallest eigenvalue is 0"]
    },
    {
      "id": "P1.1",
      "type": "proof",
      "name": "Proof of Properties of L",
      "section": "2.2",
      "proves": "T1.1",
      "proof_strategy": "direct computation"
    }
  ],
  "edges": [
    {"source": "D1.1", "target": "T1.1"},
    {"source": "D1.1", "target": "P1.1"}
  ]
}
```

## Example: full (research) annotation

```json
{
  "metadata": {"title": "Example Paper", "paper_id": "0711.0189"},
  "nodes": [
    {
      "id": "D1.1",
      "type": "definition",
      "name": "Graph Laplacian",
      "section": "2.1",
      "statement": "The graph Laplacian is L = D - W.",
      "raw_latex": "\\begin{definition}[Graph Laplacian]\nThe \\emph{graph Laplacian} is $L = D - W$.\n\\end{definition}",
      "clean_text": "The graph Laplacian is [MATH].",
      "label": "def:laplacian",
      "env_name": "definition"
    },
    {
      "id": "T1.1",
      "type": "theorem",
      "name": "Properties of L",
      "section": "2.2",
      "statement": "L is positive semi-definite with smallest eigenvalue 0.",
      "assumptions": ["G is an undirected weighted graph"],
      "conclusions": ["L is positive semi-definite", "Smallest eigenvalue is 0"],
      "raw_latex": "\\begin{theorem}...",
      "label": "thm:laplacian-props",
      "env_name": "theorem"
    }
  ],
  "edges": [
    {"source": "D1.1", "target": "T1.1", "type": "uses", "confidence": 0.95},
    {"source": "D1.1", "target": "P1.1", "type": "uses"}
  ]
}
```
