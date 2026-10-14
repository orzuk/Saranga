# v6 — proposed schema and prompt changes

**Status: PROPOSAL, for Or's review. Nothing here is applied.**
Drafted 2026-08-23 after reading Theo (`2606.31134v3`) and Numina-Lean-Agent
(`2601.14027`) — see `docs/related/theo_beyond_the_library.md`.

Inputs: the 150-item register in `docs/opus_extract_prompt_v6_TODO.md`
(issue detail and measurements live there; this file is only the decision), the
canonical schema in `src/node_types.py` / `src/edge_types.py` /
`src/annotation_schema.md`, and the frozen prompt
`scripts/opus_extract_prompt_v5_1.md` (sha `100e6cf6fdbb3aea`).

---

## 0. The governing constraint

Two things make v6 expensive in ways that are easy to miss.

**The paper hardcodes the schema size.** `saranga_common.tex` carries
`\schemenodes{18}`, `\schemenodesLone{16}`, `\schemeedges{7}`, and the
schema was locked on 2026-04-30 (`7d9e5b7`). Any new node or edge type changes
the abstract, intro contribution 1, §3, the schema appendix, the released
dataset version, the portal, and the Croissant metadata.

**Fields only an LLM can fill widen the gap NtRED has to close.** T2 is the
distillation target. A field that makes T2 richer but that no regex can produce
lowers measured T3-vs-T2 agreement — it makes the paper's central claim look
worse while making the corpus better. That is the wrong trade *this cycle*.

So every proposal below is scored on two axes: **does it change the type
counts**, and **can a regex learn it**.

---

## 1. Schema changes

### 1.1 No new node or edge types. Counts stay at 16 + 2 = 18 and 7.

Deferred to a v2 dataset release, not because they are wrong but because each
breaks §0: `notation` as a Level-1 type (A3, currently a `definition` subclass),
`table` / `figure` (E3/E6/E42), `motivates` / `context` edge (A2), `restates`
(E142), `contains` (B1).

### 1.2 Fields already declared — sync or delete, do not invent

| field | canonical state | corpus | decision |
|---|---|---|---|
| `label` | `LABEL_FIELD` in `node_types.py:174`, in `annotation_schema.md` from the start | **0 / 25,162 nodes** | **Require it.** No schema change; it already exists. |
| `rigor` | `RIGOR_LEVELS` in `node_types.py:122`, declared universal | 600 nodes (5.0 %), in 6 papers | **Decide, do not leave.** Either require with a rubric, or delete the L401 parenthetical and drop the field. |

`rigor` at 5 % concentrated in 6 papers is worse than absent: it looks like data
and is unusable (n=6, confounded with which agent noticed the parenthetical).
My recommendation is **delete** it this cycle — a five-value judgement with no
rubric is the same shape that will bite again, and nothing downstream consumes
it. Requiring it is defensible but then it needs a rubric and a re-extraction
justification of its own.

### 1.3 One vocabulary fix: `solves` (E113)

Four sources disagree today:

| source | lists `solves`? |
|---|---|
| `edge_types.py` — `SOLVES` constant, line 25 | defined |
| `edge_types.py` — `ALL_EDGE_TYPES` | **excluded** |
| `schema_for_prompts._EDGE_ORDER` | **excluded** |
| v5.1 prompt L366 "EDGE TYPES (7)" | **excluded** |
| v5.1 prompt L571 direction table (8 rows) | **listed** |
| the paper's §3 | **excluded** |
| the corpus | 24 edges / 9,134 |

**Decision needed.** Either (a) `solves` is canonical → add to `ALL_EDGE_TYPES`
and `_EDGE_ORDER`, count becomes 8, paper macros change; or (b) it is not →
delete the constant and the prompt's direction-table row, and the 24 existing
edges get migrated to `uses`. **Recommend (b)** — it keeps the count at 7, and
`problem → algorithm` is expressible as `uses` with no loss for discovery.

### 1.4 One clarifying extension, no new field

`origin` / `origin_citation` are declared universal but the prompt only exercises
them on Level-1 nodes. State explicitly that they apply to `proof_step` too, so a
step that invokes a cited result is marked rather than looking paper-original.
Costs nothing; both Theo and Numina treat "cited from prior work" as a
first-class distinction (Theo admits such lemmas as Lean axioms).

### 1.5 Explicitly deferred: §F offset spans

`spans`, `span_source`, `span_canon` remain the right design and remain out of
v6. They are a *pipeline* change — the model emits text, a deterministic resolver
converts text → offsets and fails loudly — not a prompt change. Theo's byte-exact
Claim Check is independent evidence that immutable, positionally-pinned
statements are the right invariant. Schedule after the current submission.

---

## 2. Prompt changes (v5.1 → v6)

### P1. Capture `label` — the highest-value single line in v6

Add to the required-field list, for every node from a labelled environment:

> `label` — the `\label{...}` key of the environment this node came from,
> verbatim, without the backslash or braces (`thm:main`, not
> `\label{thm:main}`). Omit (or null) when the environment carries no `\label`.
> Do not invent one, do not normalise case or punctuation, and do not
> deduplicate — two environments sharing a key is a source defect worth seeing.

Read it from the **environment header before span excision** — `\label` often
sits in the region the verbatim rule strips (interacts with E144).

Why it is worth a re-extraction on its own: the corpus carries **26,102
`\ref`/`\eqref` across 187 of 200 papers**, nearly all pointing at another node
in the same graph, and with no label recorded there is nothing to point at.
Positional recovery was implemented and measured — 43 % coverage, and on the
type-named subset only **40 % land on a node of the matching type**, worse than a
coin flip — so it cannot be back-filled.

**Follow-on, separate pass, not a prompt change:** once labels exist, resolving
`\ref{K}` to a `uses` edge is deterministic post-processing. Do it in the same
cycle but validate label capture on its own first.

### P2. Proof-step nesting — allow depth

`parent_id` already permits a `proof_step` to parent another one. The prompt's
worked example is a flat "Part (1)/(2)/(3)" list and the corpus obeys it: 7,332
steps over 2,383 proofs, ≈ 3.1 per proof, essentially depth 1.

Add: a `proof_step` may take another `proof_step` as `parent_id` when the source
nests one argument inside another — a claim proved inline and then used, a
`\begin{proof}` inside a proof, a "Proof of Claim N" block. `step_order` is
1-based **within the immediate parent**. Keep the existing prohibition on
step→step edges across different parents.

No schema change. This is the single largest structural gain available in v6, and
it is what both reference papers actually build.

### P3. A granularity policy — say when to decompose

Currently unspecified, and it shows: `proof_step` is our **largest** node type
(7,332, ~29 % of all nodes) and our **least confident** (0.889 mean; per-paper
means down to 0.650). Both reference systems needed an explicit policy and got it
from a verifier we do not have — Numina revises its blueprint when Lean feedback
shows a step "split at an unsuitable granularity"; Theo scores leaf-or-recurse.

Theo's score uses four signals, and two are **textual cues in the source**: a
step the paper calls *immediate* versus one to which it devotes a full section.
Those are visible to a regex. Proposed rubric, phrased for a reader with no
verifier:

> Emit a `proof_step` for a move the paper itself marks as a move: a numbered or
> named part (`Part (1)`, `Case 2`, `Step 3`, `Claim 4.1`), a paragraph opening
> with a discourse marker (`First`, `Next`, `It remains to show`, `We claim
> that`, `Conversely`), or an inline sub-proof.
> Do **not** emit a step for a sentence the paper presents as immediate
> (`clearly`, `trivially`, `it follows at once`, `by inspection`) unless it is
> itself named.
> Recurse — a `proof_step` inside a `proof_step` — when a step is itself given a
> named sub-argument or its own environment.

Every trigger there is lexical, which is the point: it is learnable by the rule
student, not just by the teacher.

### P4. `origin: external` on steps that cite

State that a `proof_step` whose span contains a `\cite{}` to a result it *invokes*
(rather than merely mentions) carries `origin: external` + `origin_citation`.
`\cite{}` inside the span is a hard lexical signal — cleanly distillable.

### P5. `solves` / `resolves` — one vocabulary

Whichever way §1.3 goes, make prompt L366, the L571 direction table,
`_EDGE_ORDER`, `edge_types.py` and the paper agree. Under recommendation (b),
delete the `solves` row from the direction table.

### P6. `rigor` — remove the parenthetical

Under the §1.2 recommendation, delete the L401 mention so the field is not
half-signalled. If Or prefers to keep `rigor`, it needs a rubric anchored to
observable facts, in the required-field list, not a parenthetical.

### Keep unchanged

Contiguous-verbatim spans and the three permitted removals; the self-check that
catches non-contiguous stitching (v5.1 already fixed the `paper462` case); and
register §D "source-defect handling (working well)" — preserving source typos,
excluding `\if0`/`\iffalse`/`comment` regions, breaking presentational
circularities — which should be promoted from emergent behaviour to named
guidance.

---

## 3. Distillability — what Yaron's rules can actually learn

The column that decides whether a change helps or hurts the NtRED claim.

| change | regex-learnable? | why |
|---|---|---|
| P1 `label` | **yes** | `\label{...}` is a literal token in the environment header |
| P2 nesting | **mostly** | nested `\begin{proof}`, `Proof of Claim N`, `\begin{claim}` are lexical; deeper logical nesting is not |
| P3 granularity | **mostly** | every trigger in the rubric is a keyword or a numbered marker |
| P4 `origin` on steps | **yes** | `\cite{}` inside the span |
| P5 vocabulary | n/a | consistency fix, not extraction |
| `\ref` → `uses` edge | **yes, deterministically** | not even a rule — a lookup once labels exist |
| deferred `claim` field | **no** | requires knowing what the step establishes |
| deferred `weight` | **no** | editorial judgement; would repeat `rigor`'s fate |

P1–P4 all move T2 and T3 **together**. That is the property that makes them
right for this cycle.

---

## 4. What this does and does not buy

**Does:** closes two declared-but-unrequested fields; gives the corpus real proof
structure instead of a flat list; gives the largest and weakest node type a
policy; converts 26K cross-references from display text into edges — which
attacks edge recall, the paper's own weakest result (soft F₁ ≈ 0.18).

**Does not:** change any type count, touch the paper's schema macros, add a field
only the teacher can fill, or require the offset pipeline.

**Not addressed, deliberately:** E120 (forward references forcing deletion of
real edges — the only confirmed case of the spec destroying true data; needs a
policy decision on cycles, not a prompt line), and E142's restatement duplicates
(needs `restates`, which is a new field).

---

## 5. Open questions for Or

1. **`rigor`** — delete, or require with a rubric?
2. **`solves`** — canonical (count → 8, paper changes) or deleted (count stays 7,
   24 edges migrate to `uses`)?
3. **`k_max`** — unrelated to v6 but still open: the paper says 12, your audit
   caps at 3 with a 25 % member share.
4. **P3 rubric wording** — the trigger lists are a first draft; they should be
   checked against real spans before freezing.
5. **Scope confirmation** — is "no new node/edge types this cycle" the right call,
   or do you want `notation` promoted now and the paper's counts updated?

Freeze rule still applies whatever is chosen: one atomic re-extraction of all
200 papers, never incremental. The register's incident note records what happens
otherwise — 34.3 % vs ~0 % orphans between papers extracted before and after a
mid-run change.
