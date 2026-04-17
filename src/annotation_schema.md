# Annotation JSON Schema

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

### Node types

13 types in 4 groups. Constants defined in `src/node_types.py`.

**Theorem-like** (state a claim with assumptions/conclusions):

| Type | Description |
|------|-------------|
| `theorem` | Theorem |
| `lemma` | Lemma |
| `proposition` | Proposition |
| `corollary` | Corollary |
| `claim` | Informal claim, "Fact", "Observation" |
| `conjecture` | Explicitly unproven claim |

**Foundational:**

| Type | Description |
|------|-------------|
| `definition` | Mathematical definition of a named concept |
| `proof` | Proof of a theorem/lemma/proposition/corollary |

**Pedagogical** (primarily in textbooks):

| Type | Description |
|------|-------------|
| `example` | Worked example illustrating a concept |
| `exercise` | Pedagogical problem for the reader ("Show that...", "Compute...") |

**Other mathematical content:**

| Type | Description |
|------|-------------|
| `problem` | A named mathematical problem being studied ("the knapsack problem", "the isoperimetric problem"). Semantically closer to `conjecture` than to `exercise`. |
| `equation` | Explicitly labeled/numbered equation referenced by number |
| `algorithm` | Pseudocode or step-by-step procedure |
| `remark` | Author's remark, note, observation |

**Note:** `exercise` ≠ `problem`. An exercise is pedagogical (the author knows the answer).
A problem is a mathematical object being studied (may be open/unsolved).

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
| `steps` | O | list of Span | Proof step decomposition |

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
