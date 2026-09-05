# Prompt v6 — what changed from v5.1

**Status: DRAFT. Not frozen, not rendered, not run.**
Prompt: `scripts/opus_extract_prompt_v6.md` (a copy of v5.1 with the edits below).
Issue register: `scripts/opus_extract_prompt_v6_TODO.md` (~150 items, the source of these).
Superseded: `docs/v6_decision.md` (2026-08-23) — read this file instead.

Everything here is a **prompt** change. No node type, edge type, or type count moves,
so `\schemenodes{18}` / `\schemenodesLone{16}` / `\schemeedges{7}` in the paper are
untouched. Two new optional fields and one subclass-vocabulary extension are the only
schema-adjacent items, and none of them changes a count.

---

## 1. `rigor` — from an unrequested parenthetical to sparse-with-default

**Was:** declared universal in `node_types.py:122`, mentioned *once* in v5.1 at L401,
parenthetically, inside the definition of a different field (`confidence`).

**Measured:** 726 of 25,162 nodes (2.9%) carry it, concentrated in **7 papers** — some
at 100%, most at zero. Same prompt, opposite behaviour: agents who noticed the
parenthetical filled it in, the rest did not. Nothing in the codebase reads the field.

**Now:** an optional field with an explicit default of `formal`. Omit on the common
case; emit only for `semi_formal` / `heuristic` / `numerical` / `conjectural`, judged
on the **justification**, not the node type or the arXiv category.

Two supporting findings, both from the corpus:

- **Theorem-like nodes barely vary** — 24 of 25 theorems carrying the field are
  `formal`. The variation lives in `claim` (16 numerical / 7 semi_formal / 4 heuristic),
  `remark`, `example`, `algorithm` and `definition`.
- **Category does not predict rigor**, so it cannot be derived. One `math.OC` paper is
  99% formal, another 83% non-formal; a `math.CO` paper — a category in
  `RIGOROUS_CATEGORIES` — is 72% non-formal.

**New:** `metadata.rigor_nonformal_count`. Absence of a `rigor` field is otherwise
ambiguous between "formal" and "the agent ignored the instruction" — which is exactly
the failure that produced the 2.9%. A count of `0` records that the rule was applied and
everything was formal; a *missing key* means it was skipped. Mechanically checkable
against the node count, no LLM needed.

*Distillability:* better than a required field. The student's default is "emit nothing",
correct on ~83% for free; it only has to learn cue phrases ("we argue heuristically",
"numerical experiments suggest", "a standard argument shows"), which are lexical.

## 2. `label` — capture the `\label{}` key (E146)

**Was:** listed in `annotation_schema.md` from the beginning, mirrored into
`node_types.py` as `LABEL_FIELD` on 2026-08-07, and **never requested by any prompt**.

**Measured: 0 of 25,162 nodes populate it.** Not a low rate — an absolute zero. Against
**26,102 `\ref`/`\eqref` occurrences across 187 of 200 papers**, nearly all pointing at
another node in the same graph. With no label recorded there is nothing to point at.

**Not recoverable afterwards.** The positional route — locate each statement in the
`.tex` and attach nearby labels — was implemented and measured at **43% coverage**, and
on the subset where the key names a type (`thm:`, `prop:`, so correctness is checkable)
only **40% land on a node of the matching type**. Worse than a coin flip on the checkable
subset, and a confidently wrong pointer is more damaging than a raw key. Rejected.

**Now:** requested for every node from a labelled environment, verbatim, no backslash or
braces. Read from the environment **header before span excision** — `\label` frequently
sits in the region the verbatim rule strips (interacts with E144).

**Follow-on, deliberately NOT bundled:** once labels exist, resolving `\ref{K}` to a
`uses` edge is deterministic post-processing, not a prompt change. Same cycle, validated
separately. This is the item that attacks edge recall, the paper's weakest reported
result (soft F₁ ≈ 0.18).

## 3. Proof steps — a granularity rubric, and nesting

**Was:** v5.1 specified the *fields* of a step and gave a worked example (a flat
"Part (1)/(2)/(3)" list), but never said **when** to emit one.

**Measured:** `proof_step` is the **largest** node type in the corpus — 7,332 nodes,
~29% of all 25,162 — and the **least confident**: 0.889 mean, per-paper means as low as
0.650. 7,332 steps over 2,383 proofs is ≈3.1 per proof, i.e. essentially depth 1.

**Now, two additions:**

**(a) When to emit.** Emit for a move the paper itself marks as one — a numbered or
named part (`Part (1)`, `Case 2`, `Step 3`, `Claim 4.1`), a paragraph opening with a
discourse marker (`First`, `Next`, `It remains to show`, `We claim that`, `Conversely`),
or an inline sub-proof. Do *not* emit for a sentence the paper calls immediate
(`clearly`, `trivially`, `by inspection`) unless it is itself named. Prefer more steps to
fewer.

Every trigger is **lexical on purpose**: the rule student has to be able to learn the
same rule, or this becomes a teacher-only capability and widens the T2→T3 gap.

**(b) Nesting.** `parent_id` already permitted a step to parent another step; the prompt
never asked, and the corpus obeyed. v6 states it explicitly, to any depth, for a claim
proved inline and then used, a `\begin{proof}` inside a proof, or a "Proof of Claim N"
block. `step_order` restarts at 1 within each parent.

*Source:* Theo (`2606.31134`) and Numina-Lean-Agent (`2601.14027`) both build recursive
proof structures — Theo a tree of proof nodes, Numina a `\uses{}` DAG over
definitions/lemmas/theorem. See `docs/related/theo_beyond_the_library.md`. Neither
supplies a copyable schema: Theo's Appendix D is agentic orchestration prose ("work for
23 hours"), and both derive granularity from Lean compilation feedback, which we do not
have. The rubric above is the substitute for that missing oracle.

## 4. Algorithm steps — the same, plus two corpus-specific fixes

**Measured:** 352 algorithms → 1,106 steps, mean **3.7** — as flat as the proofs.

**(a) When to emit + nesting.** One step per executable line, including control keywords
the paper numbers (`\REPEAT`, `\ELSE`, `\ENDIF`). Loop and branch bodies are **children,
not siblings** — a line inside `\FOR`/`\WHILE`/`\IF` takes that block's step as parent.

**(b) Expanded subclass vocabulary (E14).** `update` was **400 of 1,106 steps (36%)**
because it absorbed everything: "identify / prune / least-squares-solve / residual-update
all collapse to `update`". Added `test`, `compute`, `select`, `filter`, `solve`, `call`;
`update` is now explicitly the last resort.

The prompt also states the two step vocabularies are **disjoint** — `introduce_variable`,
a `proof_step` value, leaked onto an `algorithm_step` in the v5.1 corpus.

**(c) `source_line_label` (E13) — the one genuinely new field.** `algorithmic` control
lines consume line numbers that prose cites ("by line 7"), but agents emit steps only for
content lines, so `step_order` no longer matches the paper. This records the label the
paper prints, verbatim, and must **not** be derived from `step_order`. Nullable,
Level-2 only. Same class of problem as `label` for `\ref`: prose points at something and
there is nothing to resolve against.

---

## Not changed, and why

**No new node or edge types.** `notation` stays a `definition` subclass (A3); no
`table`/`figure` type (E3/E6/E42); no `motivates`/`context` edge (A2); no `restates`
(E142); no `contains` (B1). Each would move the paper's hardcoded counts and force a
dataset re-version.

**§F offset-based spans deferred.** Still the right design — it turns the
anti-hallucination guarantee from probabilistic (three tolerances in
`audit_verbatim.py`) into provable (exact equality), and absorbs ~16 register items. But
it is a *pipeline* change: the model emits text and a deterministic resolver converts
text → offsets and fails loudly. Not a prompt revision. Theo's byte-exact statement check
is independent evidence the invariant is right.

**No `claim` field on proof steps.** Theo's steps are claims-with-premises; ours are
verbatim spans with a rhetorical subclass. Theirs composes, ours describes — the deepest
gap between the representations. But a claim is precisely what no regex can produce, so
adding it improves T2 while widening the T2→T3 gap, which is the opposite of what the
distillation argument needs this cycle.

**No `weight` / node-level `note`** (from Tao's format). Subjective, no rubric — the
exact shape that gave `rigor` 2.9% coverage.

**E120 unaddressed.** Forward references force deletion of true edges to preserve the
DAG — the only confirmed case of the spec destroying real data. Needs a policy decision
on cycles, not a prompt line.

---

## Open decisions before this can be frozen

1. **`solves`** — four sources disagree: `SOLVES` is defined in `edge_types.py` but
   excluded from `ALL_EDGE_TYPES`; `schema_for_prompts._EDGE_ORDER` omits it; prompt
   L366 "EDGE TYPES (7)" omits it; the prompt's own direction table and a worked example
   include it; the paper omits it; the corpus fired 24. Either make it canonical (count
   → 8, paper macros change) or delete it (count stays 7, 24 edges migrate to `uses`).
   **Left untouched in the v6 draft pending this decision.**
2. **`source_line_label`** — accept as a new field this cycle, or defer with §F?
3. **Rubric wording** — the trigger phrase lists in §3 and §4 are a first draft and
   should be checked against real spans before freezing.
4. **Scope confirmation** — is "no new node/edge types this cycle" right, or promote
   `notation` now and update the paper's counts?

## Before running

The freeze rule from the register still applies: **one atomic re-extraction of all 200
papers, never incremental.** The incident note records what happens otherwise — 34.3% vs
~0% orphan rates between papers extracted before and after a mid-run change. A consistent
flaw beats a fix that correlates with batch index.

Re-render and re-hash before the run; v5.1's frozen hash was `100e6cf6fdbb3aea`.
