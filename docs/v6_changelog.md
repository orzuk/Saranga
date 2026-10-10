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

## 5. Two-layer extractor: LaTeX facts, then the LLM (2026-10-07)

v6 extraction is a LaTeX-syntax parser plus an LLM for everything syntax cannot
state. The parser knows LaTeX and nothing about distillation (it imports nothing
from `src/LLMVersion/` or `extractors/`). It is the extractor a newcomer who knows
LaTeX would write first; the distilled rule-based extractor comes later.

- `src/latex_facts.py`: cleaned source; `\newtheorem` / `\declaretheorem` /
  wrapper-environment declarations; environment spans; `\label`s attributed the way
  LaTeX does (last numbered thing in the current group: section, theorem, equation
  line, enumerate item, algorithm line, float); printed numbers replayed from the
  counters, including `\theX` formats and resets; `\ref`s and `\cite`s; proof
  targets from `[Proof of ...\ref]` or adjacency; shorthand macros (`\be`, `\Eq{}`,
  `\nn`). Anything it cannot replay is null, never guessed.
- `src/extraction_finalize.py`: fills `label` and `source_line_label`, adds
  `\ref`-stated `uses` and syntax-stated `proves` edges, validates. The agent's
  builder calls it before writing and must fix every error.
- `src/algorithm_lines.py`: printed pseudocode line numbers (decision 2).

Measured on the 200 v5.1 papers (2.2 s for the facts, 4.5 s for finalize):
- 96% of environment facts match a v5.1 silver node span exactly; 98% of those
  agree on type. 9,429 silver nodes (61%) have no environment: that is the LLM's job.
- Printed numbers vs LaTeX's own .aux, on 15 compiled papers not used while
  building it: theorem-likes 452 right / 2 wrong / 5 null; equations 681 / 6 / 177;
  sections 114 / 6 / 2.
- Proof targets: syntax and the v5.1 agents agree on 1,468 of 1,475 (99.5%).
- Finalize would fill 2,948 labels (v5.1 has none) and add 1,005 `\ref`-stated
  `uses` edges the agents missed; 93 `\ref`s would close a cycle (decision 5).
- **v5.1 silver defect found:** 243 nodes in 2 papers (217 in `1403.5799v2`, 26 in
  `1103.5544v1`) were extracted from text after `\end{document}`, which is not in
  the paper. The cleaned `source` removes it.

The cleaner removes TeX-disabled regions ("always cut"), which presumes the
recommendation on E144 (decision 6).

## 6. After the pilot (2026-10-07/08): hierarchy, positional backward edges, rule fixes

**The graph is a hierarchy.** `parent_id` now means "is part of" for every node
type: the innermost node whose statement contains this one. Equations inside a
theorem/proof/definition, a lemma stated inside a proof, its proof, and steps all
get a parent. For Level-1 nodes the post-pass computes it exactly from spans; the
extractor sets it for steps, and a step with children must span them.
Containment is never a `uses` edge (the post-pass rejects such edges). Schema:
`node_types.py` (HIERARCHY), `annotation_schema.md` (Hierarchy section); legacy
`parent_step`/`parent_proof`/`parent_algorithm` still read.

**`backward` is set by position** in the post-pass (a uses/generalizes/specializes
edge whose source comes after its target), not by whichever edge closes a cycle.

**Model:** Opus 5.5 at `high` (pilot: 10 papers x 4 arms; see compare_pilot_arms.py).

**Prompt rules added from the pilot** (40 agent reports, 53 issues: 9 already
resolved, 14 won't-fix, the rest fixed): prose-node boundaries (whole sentences,
one statement per node, minimal, asides are one remark, applied citations are not
nodes, no partial overlap); unnamed prose results are `claim`; prose arguments are
`proof` nodes at 0.6-0.8 (0.85-0.95 if labelled), before or after the result;
interrupted proofs; rigor for routine facts; rule-7 claim openers/closers; rule-8
case openers; equation facts that name a result; folklore and re-proved results'
origin; restatements; inline claims as `claim` nodes only if numbered or cited;
step confidence/section/origin; containers' subclass; one printed line = one
step; consistency pass (regex rule vs builder scripts, `\WHILE{...}` verbatim,
`proves` confidence, `exercise` in the type list, cleaned source, duplicate
instructions removed).

**Tool fixes:** proof environments `proofof`/`demo`/`pf`; `{\bf Case 1}`, `$1^\circ$`,
"(1)=>(3)" labels; top-level list items only; step checks on every proof node;
false alarms (displays, `\ref`, labels, `)`, `:`); `\begin{appendix}`; `\ref` in
section titles; `\enum`/`\eref` label/ref macros; nested algorithmic dropped;
line numbering (control words, `\\`, enumerate inside algorithm floats);
sub-span verbatim checks; `\ref` edges into proof steps; old validator aligned.

## Open decisions before this can be frozen

1. **`solves`**: DECIDED 2026-10-07, merged into `resolves`. `resolves` now runs
   from a `problem` / `open_problem` / `conjecture` (source) to the theorem-like
   result or `algorithm` that settles it (target). `solves` is gone from
   `edge_types.py`, `schema_for_prompts.py`, the v6 direction table and worked
   example, `annotation_schema.md`, the algorithm `solves` field, every consumer,
   and the rule extractor. The extractor now emits `problem → algorithm`, where it
   used to emit `algorithm → problem`. There is no compatibility alias. The count
   stays at 7. (The register's "24 edges" was a mid-run count; the finished v5.1
   corpus has 141 `solves` + 30 `problem→algorithm uses` + 4 reversed.)
2. **`source_line_label`**: DECIDED 2026-10-07. Kept, and filled by a deterministic
   script, not by the LLM: `src/algorithm_lines.py` replays the numbering rules of
   algorithmic, algpseudocode and algorithm2e. The extraction agent's builder calls
   `fill_source_line_labels()` before the final write and must split any step the
   script reports as MERGED (spanning several printed lines). Checked on the v5.1
   corpus: the two papers that cite line numbers (1310.6780v3, 1604.03695v3) resolve
   to the cited lines (spot-checked lines 4, 7, 13; 33 citations, all in range).
   The script is a post-processor on any graph plus .tex, so the rule-based
   extractor can call it too.
3. **Rubric wording**: DONE 2026-10-07. Checked against 30 proofs (65 ambiguities
   found). The proof_step rule is rewritten as nine ordered rules: author labels from
   `facts.json` start steps; boundaries only at sentence ends; sentence-final paragraph
   breaks are a strong hint; runs of Let/Take sentences form one step; meta/reduction/
   recall sentences are `setup`; immediate sentences never stand alone; inline claims
   nest; case-split openers and reunions; 0 steps for a body of at most 2 sentences,
   never exactly 1. Subclass glosses added. `src/proof_structure.py` detects labels,
   claim openers and paragraph breaks (facts) and checks steps (post-pass): a label not
   starting a step, a step starting inside math or mid-sentence in lowercase, and
   exactly one step are errors. On v5.1 data: 8.5% of 1,915 proofs carry author labels;
   a sentence-final paragraph break coincides with a v5.1 step start 75% of the time
   (49% next to a display, 33% mid-sentence).
4. **Scope**: DECIDED 2026-10-07: no new types. 18 node types (16 + 2 Level-2),
   7 edge types. `notation` stays a `definition` subclass.
5. **E120, forward references and induction**: DECIDED 2026-10-07: keep the edge
   and flag it `backward: true`. Acyclicity is required of the graph with flagged
   edges removed. Silent deletion of a real edge is no longer allowed.
6. **E144, TeX-disabled text inside spans**: DECIDED 2026-10-07: always cut, in the
   deterministic first stage (`latex_facts.clean_source`: `%` comments, `\iffalse`,
   `\if0`, `comment` environments, text after `\end{document}`), before the LLM sees
   the source. The verbatim audit checks against the same cleaned source.
7. **E12, `\ref`/`\cite` inside statements**: keep verbatim (recommendation, applied
   for the pilot; not yet confirmed). The post-pass turns `\ref`s into `uses` edges.
8. **`rigor`**: DECIDED 2026-10-07: confirmed as in section 1 (optional, default
   `formal`, plus `metadata.rigor_nonformal_count`).
9. **Extraction model**: DECIDED 2026-10-08: Opus 5.5, effort `high`; 200 papers first.
10. **Extraction notes**: DECIDED 2026-10-08: the extractor writes
    `metadata.paper_style`, `metadata.extraction_notes` (closed categories, short
    free text, empty for an ordinary paper) and `metadata.extraction_comment` (free
    text, at most 3 sentences, for what fits no category), for people to filter papers and revise the
    prompt. The post-pass checks the categories; distillation ignores the notes.

## Before running

The freeze rule from the register still applies: **one atomic re-extraction of all 200
papers, never incremental.** The incident note records what happens otherwise — 34.3% vs
~0% orphan rates between papers extracted before and after a mid-run change. A consistent
flaw beats a fix that correlates with batch index.

Re-render and re-hash before the run; v5.1's frozen hash was `100e6cf6fdbb3aea`.

## Frozen for the 200-paper silver run (2026-10-09)

Frozen prompt: scripts/opus_extract_prompt_v6_rendered.md (sha256 prefix `a6613a6c3d147ec5`;
per-paper copies by scripts/render_v6_prompt.py), code at 466568d, then 8afe66e from the 7th paper on:
text-discarding macros (\\ignore{...}) are removed and line-broken \\ref keys resolve. Of the six papers
finished before it, five get the same facts under both (1001.2291v2 already had the one edge by hand);
1002.1782v3 was re-extracted.
Output: corpus/silver/opus-5.5__v6/, all 200 papers, one claude-opus-5-5 agent per paper,
each stamped `prompt_version` v6-a6613a6c3d147ec5-<commit>. The trial runs that led to this
freeze (26-paper runs and reruns, 2026-10-08/09) are archived outside the repository
(G:/My Drive/Research/Automath/Saranga_v6_trial_runs_2026-10-09.tar.gz).
From the 33rd paper on, finalize is at 0e00c76: environments with identical text are told apart (label,
parent, else the last copy), so a restated equation no longer takes the preview's place. The finishing
step alone is re-run on the earlier outputs at the end of the run (no extraction is repeated).
From the 44th paper on, the cycle check is at 4f4b446: a node inside a proof that other results use is not
folded into the proof's result. Earlier outputs may carry `mention` marks added to get around the old
check (1007.0740v1, 1204.5115v1, 1203.0186v1); they are reviewed after the run.
From the 96th paper on, finalize is at 4b1f874: a repeated statement's copy is chosen by its neighbours' positions.
latex_facts at fc5fff9 (from the 107th paper on): a text-discarding macro is removed only where its arguments
are braced; only 1511.06275v2's preamble differs, and its facts and output are unchanged.
latex_macros at 90622c2 (from the 140th paper on): @ continues a control word during macro expansion (a
pre-existing bug that turned \\mathcal into V in 1705.03359v2). That paper is re-extracted; 1309.2370v6
has two statements to repair; 1103.5544v1 and 1211.7155v1 are unaffected.
latex_macros at 9be9de2 (from the 158th paper on): a macro in a definition's name slot is never expanded (a
pre-existing bug that turned \\mathrm into G in 1711.05651v2). 1711.05651v2 and 1201.4897v6 are re-extracted;
1403.5799v2 is unaffected; 1804.10149v1 and 1909.06098v1 were not yet extracted.

## After the 200-paper run: the LaTeX layer for the rule-based extractor (2026-10-09)

The rule-based extractor builds on latex_facts, and it cannot rebuild by hand what the layer misses, as the
agents did. Before distillation, latex_facts and latex_macros report:
- proofs written by hand: a "Proof" heading at the start of a line in a font switch or command
  ({\bf Proof.}, \noindent{\it Proof of Theorem~\ref{x}.}, \emph{Proof:}, \mbox{\em Proof.}), ending at its
  last end-of-proof mark before the next theorem-like environment, heading or proof (`manual`, `end_basis`);
  \newproof environments; \newenvironment whose opening prints "Proof"; proof environments named with spaces;
- displays numbered by hand ($$ ... \eqno(3) $$), numcases, and thmtools restatable environments;
- conditionals the source fixes, resolved as TeX would: \iffalse/\iftrue/\if0, \if with two different
  letters (\if False), \newif switches by their last \Xtrue/\Xfalse; the \else branch is kept;
  \begin {comment} with a space;
- \subsection[short]{long} headings, \begin{section}{...}, and no heading from a macro's body (\section{#1});
- @ in a control word only in the preamble, \makeatletter or \catcode`\@=11 code (\Cbar@>>> in a CD
  diagram expands \Cbar).
On the 200 silver papers: +103 proofs, +105 numbered equations, +5 restatable results, sections fixed in 5
papers, disabled text removed in 3. The finishing step re-run on all 200 outputs passes with no errors after
three deterministic repairs: 1309.2370v6 (DP152, EP279 back to the agent's text), 1611.03739v3 (\iflong
tokens resolved in 8 statements), 1901.08164v4 (EP6, EP7 dropped and PP3 trimmed: they were \if False text).
1710.09079v3 gains 21 edges and its labels from the restatable environments.

## Environment typing, non-content environments, declared restatements (2026-10-10)

latex_facts types an environment by its printed title, not only by an exact standard name: a known
synonym (Statement -> proposition, Comment -> remark, Reduction Rule -> algorithm, Convention ->
definition, ...; the types the silver corpus gave them), else the first type word in the title
("Hahn-Banach Theorem", "Lemma B1", "Definition/Remark"); an empty title falls back to the environment's
own standard name. A block still untyped is typed from evidence only (`type_basis`): a proof right after
it -> claim, a defining phrase -> definition. Acknowledgement, funding, dedication, keywords and similar
environments are never facts. A result whose optional argument declares it a restatement of a later one
([= Theorem~\ref{x}], [see ...]) gets `duplicate_of`; the rule parser skips it. Similar text is not used:
on the silver corpus most near-identical environments are separate nodes.
On the 200 silver papers: no environment is left untyped (69 before), 53 more agree with the silver type,
acknowledgements are dropped, one declared restatement is marked (correctly). The finishing step re-run
on all 200 outputs passes with no errors and changes nothing. The base rule parser now recovers 98.8% of
the silver's environment nodes with the silver's type (0.1% missed) at 98% precision; of the prose nodes
it finds about 15%, which is what distillation is for.
