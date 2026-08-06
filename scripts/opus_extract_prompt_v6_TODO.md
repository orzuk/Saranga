# Prompt v6 — issue register (do NOT apply mid-run)

**Policy.** The Opus-5 silver run uses **v5.1 frozen** for all 100 papers:
`scripts/opus_extract_prompt_v5_1_rendered.md`, sha256 prefix `100e6cf6fdbb3aea`.
Every issue below is deferred to a **v6** that would be applied to *all* papers
from the start of a future re-extraction. Changing the prompt mid-run creates
batch-correlated drift, which is worse for a train/test corpus than consistent
noise — see the incident note at the bottom.

Verify before each batch:
```bash
python3 -c "import sys,hashlib;sys.path.insert(0,'src');import schema_for_prompts as s;\
print(hashlib.sha256(s.render_prompt(open('scripts/opus_extract_prompt_v5_1.md').read()).encode()).hexdigest()[:16])"
# must print 100e6cf6fdbb3aea
```

---

## A. Schema / spec conflicts (fix in canonical source, then re-render)

**A1. `solves` is invisible in the rendered schema block.**
`schema_for_prompts._EDGE_ORDER` omits `solves` (it is excluded from the
"advertised 7"), but `src/edge_types.py` defines it with
`source_types={problem}`, `target_types={algorithm}`, and the prompt's own edge
table lists it. Two agents independently flagged the contradiction.
*Observed effect:* 13 papers had both `problem` and `algorithm` nodes but only 9
emitted a `solves` edge; the rest downgraded to `uses`. 24 `solves` edges out of
9,134 (0.26%).
*v6 fix:* decide whether `solves` is canonical. If yes, add it to
`_EDGE_ORDER` so the generated block and the hand-written table agree.

**A2. No edge type expresses "cited as precedent / background".**
A theorem cited purely as historical motivation (Goodstein's theorem in
`1301.0114v1`) has no logical dependency, so it is correctly left an orphan —
the agent explicitly refused to invent an edge. Legitimate but lossy.
*v6 fix:* consider a `motivates` / `context` edge type, or accept and document
that such nodes are intentionally isolated.

**A3. No `notation` node type.**
`\newtheorem{Notation}` blocks are common; agents map them to `definition`
(reported in ≥3 papers, e.g. 10 such envs in `1005.0918v2`). `notation` exists
only as a `definition` **subclass**.
*v6 fix:* either promote to a node type, or instruct explicitly:
"`\begin{notation}` → `definition` with `subclass: notation`".

**A4. Algorithm `input[]` / `output[]` usually unavailable.**
Papers rarely state inputs/outputs verbatim, so the fields stay empty and the
verbatim rule forbids synthesising them.
*v6 fix:* mark explicitly optional, or permit a flagged non-verbatim summary.

## B. Representation tensions (no clean fix; document the choice)

**B1. Proof-inside-proof nesting (the accepted cost).**
When a paper nests a lemma *and its proof* inside a larger proof, the outer
proof's **contiguous verbatim** span necessarily swallows the inner nodes.
Corpus-wide: 216 nested pairs, **57,484 / 3,117,483 chars = 1.84%** duplicated.
Breakdown — proof⊃equation 24, proof⊃definition 20, proof_step⊃equation 20,
proof_step⊃definition 12, proof⊃proof ~11.
*Decision (2026-07-30):* **keep the overlap.** Excising inner text would break
the contiguous-verbatim invariant that makes the anti-hallucination audit
machine-checkable (99.9% verbatim / 0 fabrications), and most nesting
(proof⊃equation, proof⊃definition) is legitimate and desirable.
*v6 fix:* add an optional `contains: [node_ids]` field so the overlap is
explicit; **and de-duplicate at evaluation time** so a contained span cannot be
double-counted in P/R/F1.

**B2. Level-2 steps can fall outside their parent's span.**
Where a source splits a proof around an intervening lemma, a `proof_step` may
sit outside the parent proof's contiguous span (reported in `1907.08507v2`).
*v6 fix:* state the expected behaviour explicitly rather than leaving it to
agent judgment.

**B3. Non-contiguous span temptation.**
Agents are drawn to stitching a bold heading (`{\bf The upper bound}`) onto the
prose that follows, skipping an intervening display. Two such spans appeared in
the v5 run; v5.1's self-check now catches them (`1006.5551v1` caught and fixed
one pre-write).
*v6 fix:* keep the explicit "CONTIGUOUS" wording; consider an example of this
exact failure.

**B4. Custom macros left unexpanded.**
Statements preserve `\bh`, `\mlo`, `\salg`, … so they are not self-contained
LaTeX and need the preamble to render. Correct under the verbatim rule, but a
consumer-side burden.
*v6 fix:* optionally capture the preamble macro definitions in `metadata`.

## C. Metadata / provenance hygiene

**C1. Model string inconsistent.** Agents self-report `claude-opus-5` or
`claude-opus-5[1m]`. Normalise in `metadata.model`.

**C2. Section titles when the source is unhelpful.** Titles that are
`\ref`-only, commented out, or unnumbered force inference (`1104.1135v3`,
`1412.6141v1`, `1112.1643v2`). v6 should state a deterministic rule.

**C3. `origin_citation` for uncited classical results.** Papers assert classical
facts ("By the standard argument…") with no citation; agents mark
`origin: external` with a descriptive note at confidence 0.6–0.75. Works, but
should be specified rather than improvised.

**C4. Duplicate / misplaced `\label`s in sources** (duplicate `\label{split}`,
labels after `\end{...}`). Agents handle sensibly; specify the tie-break.

## D. Source-defect handling (working well — keep)

Agents consistently preserve source typos verbatim, exclude
`\if0`/`\iffalse`/`\comment` disabled regions, and break presentational
circularities to keep the graph a DAG (recording the dropped edge). Keep this
behaviour and add it to v6 as explicit, named guidance rather than emergent.

---

## Incident note — why the freeze rule exists

During this run I twice let instructions drift mid-extraction:

1. **Orphan-minimisation** was passed in the *agent* prompt, not the spec file,
   while all papers were still tagged `prompt_version: v5`. Papers extracted
   before/after differed systematically in edge density (34.3% vs ~0% orphans).
   *Resolved by* folding it into the spec, bumping to **v5.1**, and
   re-extracting everything.
2. **The A1 `solves` note** was added to v5.1 after 40 papers were done.
   *Resolved by* reverting it, so the ambiguity applies identically to all 100.

Lesson: a *consistent* flaw across the corpus is preferable to a *fix* that
correlates with batch index. Collect issues here; apply them all at once.

---

## E. Issues reported by agents during batch 3+ (append-as-we-go)

**E1. `origin` cannot express mixed attribution within one span.**
A single sentence may assert an external result *and* the paper's own claim about
it (e.g. an OEIS/Proctor attribution combined with the authors' parity claim).
`origin` is one value per node, so one of the two attributions is lost.
*(reported: `1602.06796v1`)*
*v6 fix:* allow per-node `origin` to be `mixed` with an explanatory field, or
instruct to split the span into two nodes.

**E2. No edge type for "theorem addresses / answers a `problem`".**
`solves` is restricted to `problem → algorithm`. When a *theorem* settles a
`problem` node (not an `open_problem`/`conjecture`, which `resolves` covers),
there is no valid edge. *(reported: `1602.06796v1`)*
*v6 fix:* widen `solves` target types, or widen `resolves` source types to
include `problem`.

**E3. Figure captions have no node type.**
Captions often carry real assertions. Agents variously map them to `example`
(conf 0.6) or drop them. *(reported: `1602.06796v1`; also seen as "tables are
unrepresentable" in `paper217`, `paper222`, `1906.04768v3`)*
*v6 fix:* decide explicitly — either a `figure`/`caption` type, an approved
mapping, or an instruction to skip them.

**E4. Spec is silent on commented-out / disabled source regions.**
`\iffalse`, `\if0`, `\comment{}` blocks and large working tables. Agents have
independently converged on *excluding* them (`1912.03646v4`, `1703.07758v2`,
`1602.06796v1`) which is right, but it is emergent, not specified.
*v6 fix:* state the rule explicitly.

**E5. `section` when the source has no `\section` at all.**
Agents fall back to the paper title, or to commented-out inline headers.
*(reported: `1602.06796v1`, `1412.6141v1`, `1431`-style short notes)*
*v6 fix:* specify the fallback deterministically (e.g. `""` or `"(unsectioned)"`)
rather than inventing a title.

**E6. Tables are unrepresentable.** Complexity/BLEU/ablation tables carry
findings; their numbers survive only inside neighbouring prose nodes.
*v6 fix:* accept and document, or add a `table` type.

**E7. Permitted-cleanup list is incomplete.** The spec allows stripping only
whitespace / `%`-comments / `\label`. Real bodies also span `\qed`,
`\smallskip`, `\hbox`, `\begin{itemize}`/`\item`, `\[...\]` vs `$...$`
re-wrapping — so a semantically contiguous body can fail the literal
"contiguous verbatim" test. *(reported: `1408.0968v1`)*
*v6 fix:* enumerate the full permitted-cleanup set, or define contiguity
modulo a named normalisation function shared with `scripts/audit_verbatim.py`.

**E8. Step→parent linkage is under-specified.** Spec does not say whether a
Level-2 step needs only `parent_id`, or also an explicit edge to its parent.
Agents split both ways (`1304.0302v3` added a `uses` edge to the parent;
`1302.6193v2` used `parent_id` only). *(reported: `1408.0968v1`, `1302.6193v2`)*
*This also broke my own QA metric* — the orphan count over-reported 20x until
parented steps were excluded. **v6 must state one convention.**

**E9. No `origin` value for classical-but-uncited definitions.** Standard notions
(e.g. "base", "irredundant") stated without citation force `origin: "paper"`,
falsely attributing them. *(reported: `1408.0968v1`)* Related to C3/E1.

**E8 (UPGRADED — measured, and it is the most consequential issue found).**
Step→parent linkage is not just under-specified, it is **inconsistently applied
across the corpus**: of 46 papers with Level-2 steps, **33 emit a step↔parent
edge and 13 do not** (e.g. `1912.03646v4` 79/79 steps have one; `1006.5551v1`
0/46; `1104.1135v3` 0/47). Where present it can be ~20% of all edges in a paper
(35 of 172 in `1604.03695v3`).
*Impact:* raw edge counts and edge-density are **not comparable across papers**.
*Good news — fixable WITHOUT re-extraction:* every step carries `parent_id`, so
the relation is fully recoverable. Normalise post-hoc (add the edge everywhere,
or strip it everywhere) as a deterministic, lossless pass. Do NOT change the
prompt mid-run. Agents reporting it: `1408.0968v1`, `1302.6193v2`,
`1604.03695v3`.

**E10. The v5.1 prompt itself contains stale example content (confirmed).**
It still says "Authomathics" (legacy project name) once, and its example
metadata block shows `model: claude-opus-4-7` and `"prompt_version": "v5"`.
Agents correctly overrode these from the launch instructions (all 46 papers
record `claude-opus-5[1m]` / `v5.1`), so **no data damage** — but it is
confusing and one agent flagged it. *v6 fix:* update the examples; rename to
Saranga; ideally template the version so it cannot go stale.

**E11. No node type for empirical / simulation content.** Monte-Carlo results
sections get forced into `example`/`remark`. *(reported: `1604.03695v3`,
`1008.2565v2` — 25 empirical findings prose-promoted)*
*v6 fix:* consider an `experiment`/`observation` type, or give explicit mapping
guidance for measurement results.

**E12. `\ref` / `\cite` inside verbatim statements — no rule.** The permitted-
cleanup list covers `\label` but is silent on `\ref`/`\cite`, so statements
retain dangling `(\ref{equ:joint_process2})`. *v6 fix:* keep / strip / rewrite
to node id — state which.

**E13. `algorithm_step` numbering diverges from the paper's own line numbers.**
`algorithmic` control lines (`\REPEAT`, `\ELSE`, `\ENDIF`) consume line numbers
that prose cites ("line 7"), but agents emit steps only for content lines, so
`step_order` no longer matches. *v6 fix:* add a `source_line_label` field.

**E14. `algorithm_step` subclass vocabulary too coarse.** identify / prune /
least-squares-solve / residual-update all collapse to `update`.

**E15. `assumptions[]` inside display math.** A condition living in
`\begin{align}` has no `$` delimiters, so a verbatim span is un-renderable as
inline math. *v6 fix:* state whether delimiters may be added.

**E16. Environment type vs. semantic type tie-break.** A `dfn` environment that
is semantically an `open_problem` (`1211.5218v2`). Rule 7 needs an explicit
precedence rule.

**E17. `origin` for paper-coined terminology attached to a cited phenomenon.**
"referred to as the *spatially common sparsity* \cite{TSE}" — the term is the
paper's, the phenomenon is cited; rule 6's trigger phrases force `external`.
Genuine coin-toss. *(reported: `1604.03695v3`)* Related to E1/E9.

**E18. Appendix restatements force duplicate nodes.** Papers commonly restate a
lemma/proposition verbatim in an appendix before proving it. Rule 9 (do not
demote stated results) forces a second node with near-identical text. This is
*exact duplication across sections*, distinct from B1's containment overlap.
*(reported: `1901.08164v4`; also `1703.07758v2` and `1912.03646v4` where agents
chose NOT to duplicate — so behaviour is inconsistent.)*
*v6 fix:* state one rule — canonical node + `restated_in` pointer, or an
explicit "extract once, earliest occurrence wins".

**E19. `\if False` / `\vspace` / `\small` not in the permitted-cleanup list.**
Extends E7. Dead `\if False` blocks (sometimes whole duplicate algorithms) and
spacing macros interrupt otherwise-contiguous bodies. *(reported:
`1901.08164v4`)*

**E20. Pseudocode steps cannot have a meaningful `statement_short`.** A
single-token pseudocode line has no shorter form, so the field is either
redundant or empty. *(reported: `1901.08164v4`)*

**Note on A1/`solves`:** now independently reported by **four** agents
(`1112.1643v2`, `1001.2291v2`, `1211.5218v2`, `1901.08164v4`). Highest-confidence
item in this register.

**E21. `rigor` is effectively MISSING from the corpus (measured — high priority).**
`src/node_types.py` declares `rigor` (formal / semi_formal / heuristic /
numerical / conjectural) a **universal orthogonal field on every node**, and
CLAUDE.md lists it as such. But the v5.1 prompt mentions it **once, in passing**,
and omits it from both the required and optional field lists.
*Measured result:* `rigor` is set on **378 / 5,794 nodes (6.5%)**, in only
**4 of 48 papers**. An entire documented schema dimension is absent.
*Why it matters:* `rigor` is exactly the axis that would let the paper
distinguish "this field writes less formally" from "the extractor struggled" —
directly relevant to the per-subfield analysis (§7.5 of ROADMAP), and
complementary to the new node `confidence`.
*(reported: `1011.2299v2` — "spec should say explicitly")*
*v6 fix:* add `rigor` to the required-or-optional field list with its controlled
vocabulary and a short decision rule. **Do not add mid-run.**

**E22. Bare labelled display math that asserts a result.** `(\ref{inegentropie})`
-style unframed displays are asserted facts; rule 9 ("don't demote stated
results") arguably demands theorem-like, but they look like `equation`. Needs a
tiebreak. *(reported: `1011.2299v2`)*

**E23. Domain-specific objects with no good type.** Numerical-flux formulas are
neither procedure (`algorithm`) nor plain concept (`definition`).
*(reported: `1011.2299v2`)* Consider guidance for "discretization operator"-like
objects.

**E24. Multiple distinct results on one source line.** Where a single line holds
an external theorem + a definition + a claim, contiguous-verbatim forces mid-line
slicing and awkward span starts (e.g. a definition beginning "if we define …").
*v6 fix:* permit (or require) a documented lead-in trim.
*(reported: `1011.2299v2`)*

**E25. Assumption granularity unspecified.** `(H1)`–`(H7)` as seven `assumption`
nodes vs. one block. Agents choose by whether the text cites them individually.
*(reported: `1011.2299v2`)*

**E26. `\item[(H1)]` label wrappers** are not in the permitted-cleanup list, yet
keeping them pollutes `statement`. Extends E7/E19.

**E27. Rule 7's `problem` promotion names only *optimization* formulations.**
Control-synthesis statements ("Find, if possible, α_i such that…", "find a
controller") are structurally problems but not optimizations, so promotion is a
judgment call. *(reported: `1307.0171v1`)*
*v6 fix:* widen the clause, or enumerate qualifying shapes.

**E28. No type fits a "control law" / closed-form operator.** Named controllers
with no steps are neither `algorithm` (no procedure) nor `definition`; agents
fell back to `equation`. *(reported: `1307.0171v1`)* Related to E23.

**E29. `section` granularity: sections vs subsections.** Spec says "plain section
title" but is silent on whether a subsection title should be used when it is the
more precise location. Agents differ. *(reported: `1307.0171v1`)* Extends C2/E5.

**E30. Cleanup list misses stray counters and missing inter-token spaces.**
`\setcounter{equation}{8}` mid-theorem, and source-level missing spaces
(`$\mathcal{G}_{\sigma(t)}$satisfying`) survive verbatim, hurting readability
and downstream tokenisation. *(reported: `1307.0171v1`)* Extends E7/E19/E26.

**E31. `definiendum` may be canonicalized but `genus`/`differentia` may not.**
The spec permits a canonicalized `definiendum` while requiring verbatim spans for
`genus`/`differentia`; where no single verbatim span exists for a multi-symbol
definiendum this asymmetry is confusing. *(reported: `1307.0171v1`,
`1105.0473v1`)*
*v6 fix:* state the verbatim requirement per field explicitly.

**E32. `category` may not be the paper's true arXiv primary category (AFFECTS
THE PER-SUBFIELD ANALYSIS).**
We pass `category` from the **tier3_v2 directory** the paper was sampled from.
An agent noticed `1512.04893v3` was labelled `math_AG` but is commutative
algebra — arXiv primary **math.AC**, MSC 13A30/13H10/16S37 — i.e. it was
presumably *cross-listed* into math.AG.
*Why it matters:* ROADMAP §7.5 proposes reporting results per subfield. If the
category label is the sampling bucket rather than the paper's primary category,
per-category claims are measuring the wrong thing for cross-listed papers.
*Fix (does NOT need re-extraction):* fetch each paper's true `primary_category`
+ `all_categories` from the arXiv API and store both — sampled bucket AND true
primary — then report §7.5 on the true primary, noting cross-listing rates.
*(reported: `1512.04893v3`)*

**E33. Duplicate definition stated twice in one paper (intro + body).** No dedup
rule; agents keep one node but choose differently. *(reported: `1512.04893v3`)*
Extends E18.

**E34. Whole-body formatting wrappers.** `{\em ...}` around an entire
Remark/Example body, `\noindent`, `\begin{comment}` mid-proof. Agents strip some
and keep others. *(reported: `1512.04893v3`)* Extends E7/E19/E26/E30.

**E35. Verbatim body includes structural headers.** A 379-line
`\subsection`-structured proof with no `\begin{proof}` yields a statement
containing `\subsection{...}` headers. *(reported: `1512.04893v3`)*

**E36. `statement_short` must not exceed `statement`.** For very short equation
nodes there is no valid shorter form, so the field is dropped — same shape as
E20. *(reported: `1512.04893v3`)*

**E37. Rule 9's environment-count self-check is vacuous when a paper has zero
environments.** Nothing to count against, so the check gives no assurance for
exactly the papers where extraction is hardest. *(reported: `1711.00418v8`)*

**E38. Contiguity forbids joining an assertion to its footnote**, or a sentence
split by an intervening display. *(reported: `1711.00418v8`)* Extends E24.

**E39. Non-UTF8 / mojibake source encodings** (latin9 author names) survive into
metadata. *(reported: `1711.00418v8`)* Specify an encoding-normalisation rule.

**E40. `generalizes` + `uses` can force a 2-cycle, colliding with the DAG rule
(structural).**
When Prop 6 is proved *via* the more general Prop 7, the natural encoding is both
"P7 generalizes P6" and "P6 uses P7" — but `generalizes`/`specializes` are
declared *subtypes of `uses`*, so the pair is a 2-cycle and violates the
acyclicity rule. The agent resolved it with a single `specializes` edge.
*(reported: `1502.03482v2`)*
*v6 fix:* reconcile explicitly — either state that `generalizes`/`specializes`
replace (never accompany) a `uses` edge between the same pair, or exempt them
from the DAG constraint as a separate relation layer.

**E41. Heavily-referenced labelled equations inside definitions have no
non-duplicating home.** An `eq:` label cited 6+ times sits inside a definition's
span; emitting it as its own `equation` node necessarily copies the definition's
text. Agents leave it inside. *(reported: `1502.03482v2`)* Related to B1.

**E42. Table/figure floats break span contiguity.** Where an `example` is
unreadable without its `\begin{table}`, agents either inline the float into the
statement or drop it — changing what "verbatim contiguous" means.
*(reported: `1502.03482v2`)* Extends E3/E6.

**E43. Section titles containing `\ref` require counter resolution.**
`\section{Proof of Theorem~\ref{thm:class2}}` — rule 12 forbids cross-ref
identifiers, so resolving it means counting `\newtheorem` shared counters (here
`proposition` shares the `theorem` counter). Error-prone.
*(reported: `1502.03482v2`)* Extends C2/E29/E43.

**E44. `statement_short` expectations are per-type but only checkable in
aggregate.** Spec says "always for proofs, almost always algorithms, selectively
elsewhere"; a single corpus-wide percentage (49.7% here, 100% for proofs) cannot
verify compliance. *v6 fix:* state per-type targets so QA can check them.

**Repeat-count update (strength of evidence):**
- step→parent convention (E8): **5 agents** — `1408.0968v1`, `1302.6193v2`,
  `1604.03695v3`, `1011.2299v2`, `1502.03482v2`
- `solves` vs schema block (A1): **5 agents**
- cleanup-list gaps (E7/E19/E26/E30/E34): **7+ agents**
- no table/figure type (E3/E6/E42): **5+ agents**
- restatement/dedup rule (E18/E33): **4 agents**

**E45. The confidence rubric has a GAP that systematically under-scores some
subfields — this qualifies the §7.5 confidence-vs-subfield finding.**
The rubric offers only: explicit environment = `1.0`; prose promotion = `0.6-0.8`.
It has **no band for a *named/announced labelled display equation*** — e.g. a
main result sitting in a bare `\begin{equation}` introduced by "one finds" /
"one gets". That is materially stronger evidence than loose prose, but having no
environment forces it into the 0.75-0.8 prose band.
*(reported: `1601.01819v1`, mean node confidence 0.792, "nothing at 1.0 — zero
theorem-like environments exist")*
*Consequence for the paper:* the observed correlation between subfield and mean
node confidence (math_OC 0.765 / math_ph 0.792 vs math_CA 0.965 / math_LO 0.953)
is **partly a rubric artifact**, not purely a property of the papers. Physics- and
engineering-style papers state results in announced display math, which the rubric
cannot score above ~0.8 even when the assertion is unambiguous.
*v6 fix:* add an intermediate band (~0.85-0.9) for "named or announced labelled
display equation", and re-derive the per-subfield confidence comparison. Until
then, report confidence per subfield **with this caveat stated**, and prefer
`rigor` (E21) as the cleaner subfield signal once it is actually populated.

**E46. `equation` vs `definition` vs `assumption` for model-setup displays.**
"We consider (eqm1) with the boundary condition (bc1)" — no rule assigns these.
*(reported: `1601.01819v1`)*

**E47. Inline-math delimiters must never be ADDED.** A span lifted from inside
display math has no `$…$`; one agent added them on a first pass and broke
verbatimness, then caught it in self-check. *v6 fix:* state this prohibition
explicitly. *(reported: `1601.01819v1`; same class as E15)*

**E48. `\medskip` / `\bigskip` mid-span** — cleanup list silent. Extends
E7/E19/E26/E30/E34.

**E49. Rule 3 (verbatim-only) and Rule 6 (external attribution) are
IRRECONCILABLE for named-but-unstated classical results.**
Papers routinely invoke a classical theorem by name without stating it
("in contradiction with Brouwer's fixed point theorem", Riemann-Roch, Bertini,
Rosenblum, Lyapunov, KPV Cauchy theory). Rule 6 wants these captured as
`origin: external` nodes; Rule 3 forbids a `statement` that is not a verbatim
span — and no span exists. Agents resolve it inconsistently: some omit the node
(correct under rule 3), some record it as a `proof_step`, some create a node from
the naming clause.
*(reported: `1209.2510v1`, `1112.3679v2`, `1906.08117v1`, `1211.5218v2`,
`1306.6362v2` — **5 agents**)*
*v6 fix:* decide explicitly. Options: (a) do not create nodes for unstated
results (recommended — preserves the verbatim invariant), and instead record the
invocation on the citing node; or (b) permit a `reference`-type node whose
`statement` is the naming clause, flagged as non-definitional.

**E50. `assumptions[]` spans may legitimately lie OUTSIDE the node's own
statement.** Claims nested in a proposition inherit the enclosing hypotheses, so
their `assumptions[]` quote text from the parent. **Validators must not require
containment** — ours does not, but v6 should state it so future tooling doesn't
regress. *(reported: `1209.2510v1`)*

**E51. `origin_citation: "classical"` should be an allowed value.** Uncited
classical facts (conservation laws, gKdV invariances, Fermi-Dirac, CAR algebra)
currently force invented descriptive strings. *(reported: `1209.2510v1`,
`1601.01819v1`, `1512.04893v3`, `1408.0968v1`)* Consolidates C3/E9/E17.

**E52. Distributed proofs spanning multiple subsections.** A proof running across
§3.2-3.5 forces `\subsection{...}` commands inside the verbatim statement.
*(reported: `1209.2510v1`, `1512.04893v3`)* Extends E35.

**E53. Non-section-scoped counters.** A `\claim` counter that is not
section-scoped yields Claims numbered 1,2 while siblings are 2.x/3.x, so
generated names look inconsistent. *(reported: `1209.2510v1`)*

**E54. Step-node confidence rubric is UNDEFINED — measured spread 0.65→1.00
across papers. `confidence` is therefore NOT valid for cross-paper comparison.**
v5.1 defines `confidence` for *prose-promoted* nodes and *explicit environments*,
but says nothing about **step segmentation**, where boundaries are almost always
judgment. `proof_step` is the largest node type (**1,877 nodes, ~32% of the
corpus**).
*Measured:* per-paper mean `proof_step` confidence ranges from **0.650**
(`1602.06796v1`) to **1.000** (`1006.5551v1`, `1104.1135v3`, `1510.02714v1`,
`1906.04768v3`) — a **0.35 spread**. Some agents score every step 1.0; others
grade paragraph-splits at 0.65 and explicitly-labelled splits at 0.95.
*By type (whole corpus):* proof 0.976 · theorem 0.924 · algorithm_step 0.916 ·
proposition 0.911 · equation 0.902 · proof_step 0.889 · definition 0.866 ·
remark 0.861 · claim 0.751.

**Consequences — must be stated in any write-up:**
1. **Within a paper**, `confidence` is usable: it separates environment-lifted
   certainties from prose promotions, which is what it was added for.
2. **Across papers/subfields it is NOT comparable.** Together with E45 (no band
   for announced display equations), the earlier observation that mean node
   confidence tracks subfield formality (math_OC 0.765 / math_ph 0.792 vs
   math_CA 0.965 / math_LO 0.953) is **confounded by rubric variance**, not a
   clean property of the subfields. Do not report it as a subfield finding
   without this caveat.
3. The cleaner subfield signals remain **formal-environment density** (measured,
   objective, 30x spread) and — once populated — **`rigor`** (E21).
*v6 fix:* give an explicit step-segmentation rubric (e.g. 1.0 for source-labelled
"Step 1/2/3" or "(i)/(ii)", 0.85 for signposted prose, 0.7 for pure paragraph
splits), and add the E45 band. Then confidence becomes cross-paper comparable.

**E55. Prose derivations outside `\begin{proof}`.** Results proved in running
prose before/after the environment ("Obviously, Proposition X is a direct
consequence of…"). Agents promote them to `proof` at 0.65-0.7. Needs an explicit
rule. *(reported: `1610.00230v3`)*

**E56. `origin` for re-provings.** A theorem "due to Zagier" but proved here in a
new (adelic) setting with an added part — paper or external? Genuinely ambiguous.
*(reported: `1610.00230v3`)* Related to E17.

**E57. No rule for WHEN a display equation merits its own `equation` node.**
Emission is entirely discretionary, so `equation` counts swing widely between
papers (0 in `1203.0186v1`, 27 in `1512.07109v1`/`1604.03695v3`) for
structurally similar sources. This makes per-type node counts non-comparable
across papers, the same failure mode as E54.
*(reported: `1203.0186v1`)*
*v6 fix:* state a trigger (e.g. "emit an `equation` node only for displays the
paper labels AND cross-references elsewhere").

**E58. Contiguity forces multiple `proof` nodes per theorem when a proof is split
across sections** (parts I/II with a lemma between). *(reported: `1203.0186v1`,
`1610.00230v3`, `1710.06030v2`)* Extends E52/E58.

**Repeat-count update (final for batch 3):**
- cleanup-list gaps: **11 agents** (now incl. `\vadjust`, `\vspace*`, `\break`,
  `\looseness`, `\noindent`, `\medskip`, `\bigskip`, `\qed`, `\hbox`, `\small`,
  `\if False`, `\item[..]`, `\setcounter`, `{\em ..}`)
- nested/overlapping spans: **8 agents**
- uncited-classical `origin`: **7 agents**
- step→parent edge convention: **6 agents**
- `solves` vs schema block: **5 agents**
- named-but-unstated classical results (E49): **5 agents**
- no table/figure type: **5 agents**

**E59. Math-environment delimiters break `assumptions`/`conclusions`/`differentia`
verbatim spans — QUANTIFIED at ~38% first-pass failure.**
An antecedent/consequent routinely straddles `$$…$$`, `\[…\]`,
`\begin{equation}…\tag{}…\end{equation}`, or `align` `&`/`\\` separators, so a
literally-contiguous span is impossible. One agent measured **46 of ~120
first-pass decomposition spans failing verbatim purely for this reason**
(`1512.03989v1`); it self-corrected, but the rate shows the rule is
under-specified rather than occasionally awkward.
*v6 fix (recommended):* define spans as **(start,end) character offsets** into a
canonicalised source, rather than as copied strings. That fixes E7/E15/E19/E24/
E26/E30/E34/E38/E47/E48 in one move and makes the audit exact instead of
substring-based. Failing that, explicitly permit stripping math-environment
delimiters and `align` separators.

**E60. `proof_strategy` and `proof_step.subclass` vocabularies are not
reconciled.** `bound_estimate` exists only as a step subclass; `construction`
only as a proof_strategy. Analysis papers' commonest strategies ("apply a
previously proven lemma", "epsilon-delta / sequential-continuity estimate") are
in neither. *(reported: `1512.03989v1`)*

**E61. Prose cross-references are not authoritative for `section`.** A paper may
call its own §3 "Section 2" in running text. Agents should use the true
sectioning, and v6 should say so. *(reported: `1512.03989v1`, `1610.00230v3`)*

**E62. `corollary` vs `claim` vs `remark` for prose consequences is
underdetermined.** "It follows that f is Parseval iff S=I" — agents pick
`corollary` when derived from a numbered result and `claim` otherwise, but that
heuristic is invented, not specified. *(reported: `1512.03989v1`)* Related to E16.

**E63. Shared `\newtheorem` counters mean numbering cannot disambiguate type** —
type must come from the environment name. Worth stating.
*(reported: `1512.03989v1`, `1901.01675v1`, `1502.03482v2`)*

**E64. `origin` attribution: measured 2.0%–54.8% external share across papers.**
Corpus-wide: **paper 84.3% / external 15.7%**; `origin_citation` is present on
**1187/1187 (100%)** of external nodes — that field is clean.
But the per-paper external share ranges from **2.0%** (`1610.00230v3`) to
**54.8%** (`1408.6474v1`), a ~27x spread.
*Honest interpretation:* this is **partly genuine** — `1408.6474v1` is a survey,
so most content really is others' work — and partly rule ambiguity. Two distinct
ambiguities drive the latter:
 - **"no citation ⇒ paper" default over-attributes.** Standard-but-uncited
   objects (Dirac element, `W_#`, extended Dirac cohomology) are literature
   notions given without a `\cite`; defaulting them to `paper` credits the wrong
   author. *(reported: `1705.06478v1`)*
 - **Survey/expository papers** invert the base rate; the rule gives no guidance.
   *(reported: `1408.6474v1`)*
*v6 fix:* state the default explicitly, and add `origin_citation: "classical"` /
`"standard, uncited"` (see E51) so "external without a bibliography entry" is
expressible without inventing a reference.

**E65. `origin_citation` cannot record a source conflict.** One construction was
attributed to `[CH15, A.3]` in the intro and `[BCT12, A.3]` in the body of the
same paper. *(reported: `1705.06478v1`)*

**E66. Restatement/announcement needs its own relation.** `theoremalpha`
(Theorems A/B/C in an intro) and starred `theorem*`/`lemma*` restate later
numbered results verbatim. Agents link body→intro with `uses` @0.85, which is a
poor semantic fit. *v6 fix:* add a `restates`/`announces` role or pointer.
*(reported: `1705.06478v1`; consolidates E18/E33)*

**E67. `lstlisting` / verbatim-code environments.** Whitespace collapse destroys
code alignment and semantics; one agent kept newlines, deviating from the
mechanical-cleanup rule to preserve meaning. *(reported: `1408.6474v1`,
`1301.0114v1` literate Haskell)*
*v6 fix:* exempt verbatim-like environments from whitespace collapse.

**E68. Footnotes mid-span** bloat statements but cannot be excised under
contiguity. *(reported: `1408.6474v1`, `1711.00418v8`)* Another case for the
offset-based span fix (E59).

---

## F. THE PRIORITY v6 CHANGE — offset-based spans (design, agreed 2026-07-31)

Supersedes/absorbs: **E7, E15, E19, E24, E26, E30, E34, E35, E38, E47, E48, E52,
E59, E67, E68**, and makes **B1, B3, E18, E33, E41, E66** measurable rather than
guessed. ~16 of the 68 issues collapse into this one change.

### Root cause
`statement` is a **copied string** required to be a "verbatim contiguous span",
and the spec enumerates only three permitted removals (whitespace, `%` comments,
`\label{}`). Real statements are constantly interrupted by material that is not
part of the statement, so agents repeatedly asked the same question in different
forms — *"may I strip this?"* — for: `\qed \medskip \bigskip \noindent \vspace*
\break \looseness \hbox \small \setcounter{} \item[(H1)] {\em ...}
\subsection{} \footnote{} $$..$$ \[..\] align & and \\ \xymatrix
\begin{table} \begin{comment} lstlisting`.
An enumeration of removable markup can never be complete. **Define spans by
their endpoints instead of their contents.**

### Representation
`statement` stays **clean** — the concatenation of the kept pieces only, with
holes REMOVED. `spans` records provenance.

```json
{
  "id": "PP1.7",
  "type": "proof",
  "statement": "it suffices to show that X.Therefore the claim follows.",
  "spans": [[70, 100], [130, 165]],
  "span_source": "tex_pool/1006.5551v1.tex",
  "span_canon": "collapse_ws+strip_comments+strip_label@v1"
}
```
Chars 100-130 (`\footnote{See Remark 3.}`) are the hole: absent from
`statement`, but the skip is explicit and auditable.

### Exact invariant (replaces fuzzy substring auditing)
```
"".join(canon(source)[s:e] for s,e in node.spans) == node.statement
```
Exact equality. Today `scripts/audit_verbatim.py` must try three tolerances
(exact / cleaned / head-60) and can false-positive on short statements; with
offsets the anti-hallucination guarantee becomes **provable**, not probabilistic.

### Required bookkeeping (offsets are meaningless without these)
- **`span_source`** — WHICH file the integers index. Also guards against the
  source being re-fetched (a new arXiv version) silently invalidating offsets.
- **`span_canon`** — WHICH cleaning was applied before counting, **versioned**.
  Position 48210 in cleaned text ≠ 48210 in raw text. If the canonicaliser is
  later improved (e.g. also stripping `\medskip`) every offset shifts; the
  version tag makes that a **detected mismatch** instead of silent rot. The
  canonicaliser MUST be one shared function imported by both the prompt-rendering
  path and the audit script.

### Division of labour (critical — do NOT ask the model for offsets)
LLMs cannot count characters reliably.
1. the **agent emits the text span(s)** — identifying content, which it is good at;
2. a **deterministic script resolves text → offsets**, and **fails loudly** on any
   span that does not resolve. This is an upgrade of `audit_verbatim.py` from a
   post-hoc check into a pipeline stage that stores its result.

### Free consequences
- **Overlap becomes arithmetic:** two nodes share content iff their ranges
  intersect. B1's 1.84%-of-characters duplication is computed, not searched; the
  proposed `contains` field becomes *derived*, not model-emitted.
- **Restatement duplicates** (E18/E33/E66) surface as near-identical ranges.
- **Evaluation de-duplication** (the agreed fix for proof-inside-proof) becomes a
  trivial range operation.
- Large or substantive gaps are auditable — exactly what could NOT be checked
  when `paper462` silently stitched a heading onto following prose.

### Costs / risks
- Corpus must **pin the source bytes** (`tex_pool/` already does) and the
  canonicaliser version.
- Offsets are not human-readable → **store both** resolved text and spans.
  Slight redundancy, large gain.
- Main risk: prompt and audit canonicalising differently. Mitigation: one shared
  versioned function, recorded per node in `span_canon`.

### What this does NOT fix (needs separate decisions)
Taxonomy gaps — no `table`/`figure` type (E3/E6/E42), no `notation` type (A3),
no "cited as precedent" relation (A2), no `restates` relation (E66), the `solves`
schema-block conflict (A1), missing `rigor` (E21), undefined step-confidence
rubric (E54). Rough split of the 68 issues: **~16 collapse into F**, ~12 taxonomy
additions, ~10 confidence/calibration, rest wording clarifications.

**E69. Do `\begin{equation}` wrappers belong inside an `equation` node's
`statement`?** Unspecified, so some agents include the environment delimiters and
some include only the body — making `equation` statements non-uniform across the
corpus. *(reported: `1908.10890v1`)* Resolved automatically by §F (offsets pick
exact boundaries).

**E70. Is `Abstract` a valid `section` value?** Papers assert results in the
abstract; agents differ on whether to label the section "Abstract" or attribute it
to the first numbered section. *(reported: `1908.10890v1`)* Extends C2/E5/E29/E61.

**E71. `\nonumber`, `&` alignment markers and `\\` inside a copied `align` body.**
Unspecified. One agent initially dropped `\nonumber` and a `\footnote{}` and only
caught it on re-verification — i.e. the model's instinct is to strip markup the
spec does not sanction. *(reported: `1610.03950v1`)* Further evidence for §F.

**E72. Unicode normalisation.** A fullwidth comma (U+FF0C) in the source made one
span unusable; the agent avoided that span entirely. v6 should state whether
unicode is normalised (and if so, before or after offset counting — matters for
§F). *(reported: `1610.03950v1`)*

**E73. Macro-laden `section` titles.** `\Prediction{} Subnet`,
`\texttt{ZRegression}` — should macros be expanded in `section`?
*(reported: `1610.03950v1`)* Extends B4/E29.

**E74. `input[]`/`output[]` verbatim requirement is often unsatisfiable.** Agents
correctly refuse to fabricate them, so the fields are empty for most baseline
algorithms. v6 should permit explicit omission. *(reported: `1610.03950v1`,
`1105.0473v1`)* Confirms A4.

**E75. Rule 9's "theorem-like count >= labelled env count" check is inverted for
ML/prose papers.** With zero environments the check is vacuous (see E37); v6
should instead state that `claim`/`proposition` promotion from result prose is
*expected* in such papers, and cap those confidences — which is what agents are
already doing (mean 0.786 with all prose promotions 0.65-0.85).
*(reported: `1610.03950v1`)*

**E76. The single-write rule is CORRECT but concentrates failure risk (measured
under a real hard kill).**
When the 5-hour session limit fired, it killed **16 in-flight agents**, every one
of them at the "now I'll assemble/write" moment — i.e. each had already read its
full paper (transcripts 244-728 KB) and lost all of it.
*The good news, and the reason to keep the rule:* **0 partial or corrupt files**
resulted. The corpus survived a hard kill perfectly intact, and
`extraction_status.py` reconstructed the exact TODO list. Compare the v5 run,
where a mid-write death left `1710.06030v2` with 114 nodes and 0 edges.
*The cost:* a late failure loses 100% of the work rather than a fraction, and
reads are the expensive phase.
*v6 fix (keep the guarantee, cut the exposure):* instruct agents to **write the
complete JSON as early as the graph is coherent**, then refine with further
complete writes if needed. Atomicity is preserved (each write is whole) while the
window of total loss shrinks. Optionally: emit a complete draft after reading,
before the self-check pass.

**E77. No confidence rung for "verbatim code figure".** A result stated in a
`minted`/`cpp` code block is stronger evidence than loose prose but has no
environment; one agent used 0.9 by analogy. *(reported: `1911.02696v6`)*
Same shape as E45 — the rubric needs intermediate rungs.

**E78. Rule 13's step triggers omit verbatim code blocks.** It names
`algorithmic`/`algorithm`/`enumerate` but not `minted`/`lstlisting`/`verbatim`,
so decomposing a code figure into `algorithm_step`s is unguided (one agent
grouped a 15-line circuit into 7 role-based steps). *(reported: `1911.02696v6`)*

**E79. May content inside stripped `%` comments ever be promoted?** One paper's
only future-work sentence lives in a `%` comment; the agent excluded it (correct
under the cleanup rule) but the spec never says. *(reported: `1911.02696v6`)*

**E80 (positive finding — keep this behaviour).** Where a paper states mutually
inconsistent figures (speedups quoted as 50x / 400x / 300x / 40x in different
sections), agents emit each as a separate `claim` rather than reconciling. This
is correct under the verbatim rule and desirable: the corpus preserves the
paper's own internal inconsistency instead of silently choosing one value.
v6 should state it explicitly as intended behaviour. *(reported: `1911.02696v6`)*

**E81. Content AFTER `\end{document}` — what counts as "the paper"?**
`1304.5152v1` has ~55 lines after `\end{document}`: a whole section
("Completions of subneat reducts") with a labelled theorem, a corollary and two
proofs. It does **not compile into the published paper**, so the agent excluded
it — defensible, but the spec never says, and a human gold annotator working
from the .tex might well include it.
*Why it matters beyond this paper:* it defines the extraction's **scope
boundary**. Same class as `\iffalse`/`\comment` (E4/E79) but more consequential,
since this is complete, labelled, apparently-finished mathematics.
*v6 fix:* state explicitly — recommend "extract only what compiles
(`\begin{document}`..`\end{document}`, excluding disabled regions)" and record
the excluded byte range in metadata so the choice is auditable.

**E82. Custom proof environments not in rule 7's mapping table.**
`\newenvironment{demo}` holding proofs (`1304.5152v1`), `\begin{pf}`
(`1712.00281v1`), `{\bf Proof.}...$\Box$` (`1503.02851v1`). Agents map them
correctly but by inference. *v6 fix:* say "map any environment whose body is a
proof to `proof`, regardless of its declared name".

**E83. Multi-clause `\begin{definition}` blocks.** A single definition
environment with 7 enumerated clauses: split into 7 nodes (better graph
structure) or keep as 1 (matches the source environment)? Rule 9's counting rule
covers theorem-likes only. *(reported: `1304.5152v1`)*

**Repeat-count: `solves` vs schema block (A1) now reported by 7+ agents** — the
single most-reported defect in this register.

**E83 (GENERALIZED). Multi-part environments have no decomposition rule.**
The spec defines Level-2 decomposition only for `proof`/`algorithm`. But sources
routinely pack several distinct results into one environment:
one `\begin{Def}` holding 5 chained definitions; one `\begin{Prop}` holding 6
labelled properties (`1108.5376v2`); a `\begin{definition}` with 7 enumerated
clauses (`1304.5152v1`); a `\begin{example}` whose 6 real examples live in a
following `itemize` (`1712.00281v1`); an `exs` block of 8 instances
(`1901.01675v1`).
Agents split them (conf 0.9-0.95) for better graph structure, but by judgment.
*v6 fix:* state a rule — recommend "split when the parts are individually
labelled or individually cross-referenced; otherwise keep as one" — and say
whether the parent environment also gets a node.

**E84. Remark granularity in figure/observation-heavy papers.** A visualization
survey produced 24 `remark` nodes at 0.7-0.8, one per `itemize` bullet of
figure commentary. No guidance on whether bullets are separate nodes.
*(reported: `1108.5376v2`)*

**E85. Sources that duplicate a labelled display verbatim in two sections**
(same `\label` reused: `Glim`, `qexp`, `qpenta`). Agents keep the environment
version and mention the prose one only if it adds content — sensible, unstated.
*(reported: `1108.5376v2`)* Related to E33/E85.

**E86. "No regex shortcut" is ambiguous between IDENTIFYING and LIFTING — and the
distinction matters a lot.**
Rule 2 forbids scripting the *semantic identification* of nodes (don't grep for
`Theorem N.M`), which is right. But it is silent on **mechanically lifting a span
the model has already chosen by reading**. Several agents adopted the pattern
"read the paper → hand-pick line ranges → have a script slice those exact bytes",
and it **strictly improves verbatim fidelity** by eliminating transcription
error. One agent asked for this to be clarified explicitly.
*(reported: `1611.01043v4`; the same pattern in `1610.00230v3`, `1512.03989v1`,
`1203.0186v1`, which all report "machine-lifted from hand-identified spans")*
*v6 fix:* endorse it explicitly — "identify semantically by reading; you MAY use
a script to lift the exact bytes of spans you have chosen."
*Note:* this is precisely the division of labour §F formalises (model identifies,
script resolves to offsets). Agents converged on it independently, which is good
evidence §F matches how the task actually wants to be done.

**E87. Layout-only commands inside statements** (`\begin{list}` scaffolding in a
lemma) forced dropping non-semantic sub-spans. *(reported: `1611.01043v4`)*
Extends E7 cluster → resolved by §F.

**E88. Unnumbered `\subsection{Proof of X}` with no `proof` environment** needs an
explicit rule. *(reported: `1611.01043v4`, `1610.00230v3`, `1512.04893v3`)*

**E12 (STRENGTHENED — downstream harm to T-ALIGN/T-PLAG/T-OPEN).**
`\label{}` is stripped by the cleanup rule but `\ref{}`/`\eqref{}`/`\cite{}` are
NOT, so statements carry dangling cross-references like `(\ref{gident})`,
`[CH15, A.3]`, `\eqref{equ:joint_process2}`. These are pure **noise for
cross-paper matching**: they are paper-local tokens that can never align across
papers, they inflate Jaccard denominators, and they pollute embeddings — hurting
exactly the discovery tasks this corpus exists to serve.
*(reported: `1008.1190v1`, `1604.03695v3`, `1610.03950v1`)*
*v6 fix:* decide and state — recommend **keep them in `statement` (verbatim
integrity) but strip them in `clean_text`/the embedding view**, so fidelity and
matchability are both served. Under §F this is trivial: the offsets stay exact
while the derived text is filtered.

**E89. No edge type for "consistency check / verification".**
Statements like "this can be checked directly", UV/IR limit checks, and sanity
verifications are not `proves` (no proof node, no formal derivation) but there is
no `verifies` relation; one agent used `proves` at 0.7 as the least-bad fit.
*(reported: `1008.1190v1`)* Note `tests` exists but is restricted to
`exercise → concept`.

**E90. No guidance for ranking COMPETING promotions in prose-only papers.**
When a physics paper states everything in prose, choosing between
`proposition` / `claim` / `remark` for a given assertion is unconstrained; one
agent used `proposition` for asserted-but-underived formulas and `claim` for
narrative assertions, calling the boundary "arbitrary and unspecified".
*(reported: `1008.1190v1`)* Related to E62.

**E91. Must Level-2 steps TILE their parent exactly?**
Unstated. If steps are verbatim spans and the parent proof is also a verbatim
span, re-joining the steps does not reproduce the parent (TeX `\\` separators and
inter-step glue are lost). One agent asked the spec to state explicitly that
**steps need not tile the parent exactly**. *(reported: `1007.0740v1`)*
*Why it matters:* a validator or evaluator might reasonably assume
`concat(steps) == parent` and flag every proof as malformed.
*v6 fix:* state "steps are a selection from the parent, not a partition of it"
— and under §F this becomes checkable arithmetic (step ranges ⊆ parent range,
gaps permitted).

**E92. `tags[]` collides with the `proof_strategy` vocabulary.** Legitimately
topical words (construction, compactness) belong in both, so rule 11's
"tags are topical only" separation is ambiguous. *(reported: `1007.0740v1`)*
Related to E60.

**E93. `problem` vs `equation` for a studied PDE.** A Cauchy problem the paper
sets up and solves is arguably both. *(reported: `1007.0740v1`)*
Related to E46/E27.

**E94 (CONVERGENT — "construction" is a missing first-class concept).**
The same gap has now surfaced in four distinct guises across the corpus:
 - `\begin{construction}` environment → forced to `algorithm` (`1010.2663v2`)
 - `cons` (Construction) environment → split across
   proposition/definition/remark by content (`1803.10897v2`)
 - `construction` exists in the `proof_strategy` vocabulary but NOT in the
   `proof_step.subclass` vocabulary (`1512.03989v1`, `1503.04023v2`)
 - closed-form operators / control laws / numerical fluxes — "we construct X"
   objects that are neither procedure nor plain concept (E23, E28)
*v6 fix:* treat this as one decision, not four. Either add a `construction`
node type, or state a single canonical mapping (e.g. "a `construction`
environment → `algorithm` when it has steps, `definition` when it defines an
object"), and reconcile the `proof_strategy` / `step.subclass` vocabularies so
`construction` exists in both.

**E95. `\qedhere`, `~` non-breaking spacers, `\makeatletter`, table floats inside
bodies** — kept verbatim for exact-span matching, but unlisted.
*(reported: `1010.2663v2`)* → resolved by §F.

**E96. Shared amsart counters make numbered names unrecoverable.** With one
counter across all environments, "Theorem 3.1" cannot be safely reconstructed, so
agents fall back to descriptive names — meaning `name` is not comparable to the
paper's own numbering. *(reported: `1010.2663v2`, `1512.03989v1`, `1502.03482v2`,
`1901.01675v1`)* Consolidates E63/E96.

**E66 (UPGRADED — three incompatible encodings of the SAME relation in one
corpus).**
Intro-restates-body is extremely common (Theorems A/B/C, `theorem*` restatements,
`mthm` + Thm 4.8). With no `restates` relation, agents have encoded it three
different ways:
 - `uses` @0.85 (`1705.06478v1`, `1803.10897v2`, `1901.08164v4`)
 - `specializes` (`1502.03482v2`)
 - `generalizes` @0.6 (`1509.08760v1`)
…and some agents instead **suppress the duplicate node entirely**
(`1703.07758v2`, `1912.03646v4`, `1512.04893v3`).
*Impact:* the same source phenomenon yields incompatible graph structure across
papers — a cross-paper inconsistency of the same kind as the step→parent issue
(E8), and it will confound any edge-type-aware evaluation or discovery matching.
*v6 fix:* add a `restates`/`announces` relation (or a `restated_by` pointer) and
state whether the duplicate node is emitted at all. **Decide once.**

**E97. Non-contiguous proofs → multiple `proves` edges to one theorem.**
Where a theorem is proved by two separated prose fragments, agents emit two
`proof` nodes each with its own `proves` edge. Reasonable, but unstated — and it
breaks any assumption of one-proof-per-theorem.
*(reported: `1509.08760v1`, `1203.0186v1`, `1710.06030v2`)*

**E98. Named identities** (shuffle / composition / reversal) sit between
`equation` and `proposition`. *(reported: `1509.08760v1`)* Related to E22/E93.

**E99. Edge NAMES read target→source while ARROWS run source→target (naming
awkwardness, not a data defect).**
Under the agreed dependency convention (arrow = prerequisite → dependent),
`illustrates` is emitted as `concept → example`, but the verb reads naturally as
"the *example* illustrates the *concept*" — i.e. the name describes the target's
action on the source. Same for `tests`. One agent called it "ambiguous but
consistent as used". *(reported: `1512.05406v1`)*
*Status:* **the corpus is internally consistent** — 0 nonconforming edges across
all papers after the v5.1 direction fix. This is a documentation-clarity issue
only.
*v6 fix:* keep the arrows as-is (uniform dependency semantics is worth more than
verb-reading convenience) but say plainly in the spec: "edge type names describe
the TARGET's relation to the SOURCE; the arrow always runs prerequisite →
dependent." Consider renaming to `illustrated_by` / `tested_by` if clarity is
preferred over continuity with existing tooling.

**E100. `problem` nodes have no sanctioned decomposition.** A `problem` with a
6-item `enumerate` (six sampling settings) could not be decomposed — rule 13's
step triggers cover only `proof`/`algorithm`. *(reported: `1512.05406v1`)*
Related to E83.

**E101. `grounded_to` appears in CLAUDE.md but in neither the prompt's edge list
nor its direction table.** An agent noticed the absence and flagged it as a gap.
*It is actually correct* — `grounded_to` links a paper node to the foundation
graph and is added later by `src/link_to_foundation.py`, never by the paper
extractor. But the spec never says so, so it reads as an omission.
*(reported: `1004.2924v1`)*
*v6 fix:* one line — "`grounded_to` is added downstream by the foundation
linker; do NOT emit it during extraction."

**E102. `assumptions[]`/`conclusions[]` for prose-promoted `claim` nodes whose
hypotheses live in earlier paragraphs.** Undefined; agents either omit the fields
or quote out-of-span text. *(reported: `1004.2924v1`)* Same root as E50 — the
decomposition fields may legitimately reference text outside the node's own span.

**E96 (ELEVATED — reconstructed numbering is a FABRICATION RISK, not just an
inconvenience).**
With shared `\newtheorem` counters, the paper's own numbering ("Theorem 2.1",
"Prop 2.14") cannot be read off the source — it must be reconstructed by counting
environments. One agent stated the risk plainly: *"names carry my computed
numbers, which is a fabrication risk if the count is off by one."*
*Why this is worse than it looks:* `name` is the ONE field not covered by the
verbatim guarantee. Every `statement` is machine-verified against the source, but
a wrong theorem number in `name` would pass every check we run — and would
silently break name-based matching against human gold annotations.
*(reported: `1011.1633v3`, `1010.2663v2`, `1512.03989v1`, `1502.03482v2`,
`1901.01675v1` — 5 agents)*
*v6 fix:* forbid reconstructed numbering in `name`. Either use the literal
label/title text from the source, or a descriptive name, and put any inferred
number in a separate clearly-derived field (e.g. `inferred_number`) so it is never
mistaken for source truth.

**E103. Custom label macros** (`\thlabel`, `\eqlabel`, `\index`) — the cleanup
list sanctions only `\label`. Agents drop `*label` variants (pure labels) but keep
`\equref`/`\prref` (cross-references). Correct, unstated.
*(reported: `1011.1633v3`, `1811.02767v4`)*

**E104. Plural environments** (`\begin{examples}` with two numbered items) — spec
silent; agents split. *(reported: `1011.1633v3`)* Same family as E83.

**E105. A theorem nested inside a `\begin{remark}`** — no nesting guidance for
theorem-in-remark. *(reported: `1811.02767v4`)*

**E106. `remark → definition` promotion is missing from rule 7's table**, though
remarks that are semantically definitions are common.
*(reported: `1811.02767v4`, `1211.5218v2`, `1005.0918v2`)*

**E52 (UPGRADED — distributed proofs are UNREPRESENTABLE, not merely awkward).**
An agent put it directly: *"The 'verbatim contiguous span' rule cannot express
distributed proofs."* Theorem 1 of `1512.07524v1` has no `\begin{proof}` and its
argument spans three subsections; the only legal single-range span is the
strategy paragraph, so the `proof` node captures ~a paragraph of a multi-page
argument (conf 0.7). **Real mathematical content is lost, not just formatted
badly.**
*(reported: `1512.07524v1`, `1209.2510v1`, `1610.00230v3`, `1203.0186v1`,
`1710.06030v2`, `1512.04893v3` — 6 agents)*
*This is the strongest single argument for §F:* multi-range spans
`[[a,b],[c,d],[e,f]]` express a distributed proof exactly, with the intervening
lemmas visible as gaps. No other proposed fix recovers this content.

**E107. `origin` needs a "re-proves" case.** A paper whose contribution is a NEW
PROOF of someone else's theorem fits neither `paper` (the result isn't theirs)
nor `external` (the proof is). Agents mark `paper` + a provenance remark.
*(reported: `1512.07524v1`, `1610.00230v3`, `1509.08760v1` — 3 agents)*
*v6 fix:* add `origin: "reproved"` or a `reproves` edge.

**E108. No confidence guidance for environment→type OVERRIDES.** Rule 7 permits
retyping (a `\begin{remark}` that is really an `assumption`), but says nothing
about what confidence such an override deserves — agents used anywhere from 0.85
to 1.0. *(reported: `1512.07524v1`)* Related to E54.

**E96 (CONCRETE EXAMPLE — labels can be actively MISLEADING, not just absent).**
In `1308.1738v1` the LaTeX label `theorem3.2` denotes what the compiled paper
numbers **Theorem 3.3** (and another is labelled `theorem-1`). So an extractor
that trusts the label text produces a wrong number, and one that counts
environments produces a different wrong number if any environment is skipped.
Both failure modes land in `name`, the one field with no verbatim check.
This is the sharpest evidence for the E96 fix: **never derive a number for
`name`** — use literal title text or a descriptive name, and isolate any inferred
number in a separate field.

**E109. Node IDs are assigned in source order per type, so EXTERNAL results shift
the paper's own numbering.**
When a cited theorem (Hoeffding) appears before the paper's Theorem 2, the
external one takes `TP1.2` and the paper's Theorem 2 becomes `TP1.3`. Prose
cross-references ("by Theorem 2") therefore do not match node IDs.
*(reported: `1703.01203v3`)*
*Not a data defect* — edges resolve by ID and the graph is correct (see E96
analysis) — but it makes IDs actively misleading to a human reader who assumes
`TP1.N` = "Theorem N".
*v6 fix:* say plainly that IDs are opaque and carry no numbering semantics, OR
assign IDs only over `origin: paper` nodes so they track the paper's own
sequence.

**E110. `proves` can point backwards in document order.** Where a derivation
precedes the theorem it establishes, the `proof → theorem` edge runs against
reading order. Still a valid DAG, but v6 should state it is expected so no
validator "corrects" it. *(reported: `1703.01203v3`)*

**E111. Trailing "where" clauses outside `\end{theorem}`.** A theorem's defining
condition (`\rho=\sqrt{1-r^2}`) placed after the environment closes; one agent
parked it in `assumptions[]`. Needs a rule. *(reported: `1703.01203v3`)*

**E112. Parallel extraction may duplicate a Level-1 node as a step.** A cited
bound appears both as a Level-1 `lemma` (cross-referenced later) AND as a
`proof_step` of the proof that uses it. Spec doesn't say whether step
decomposition may re-extract an existing Level-1 node.
*(reported: `1712.00232v3`)* Distinct from B1 (containment) — here the SAME
content is deliberately emitted at two levels.

**Convergent validation of the QA fix (E8):** an agent independently concluded
*"orphan metrics need a `parent_id` counts clause"* — the same correction already
applied to `scripts/qa_extractions.py` after the metric was found to over-count
orphans 20x by treating parented Level-2 steps as isolated.

---

## E113 (HIGH — taxonomy gap, corpus-wide). No canonical edge for "result settles open problem"

**Measured across the 88-paper corpus: 40 `resolves` edges in 19 papers.** Every
occurrence is `open_problem`|`conjecture` → theorem-like (`theorem`, `proposition`,
`claim`, `lemma`). Zero exceptions in direction or endpoint types.

**CORRECTION (initial analysis was wrong).** This is NOT agent invention. The
frozen v5.1 prompt *explicitly authorizes* `resolves`:

  - L366: `EDGE TYPES (7): uses, generalizes, specializes, proves, illustrates,
    tests, resolves.`  <- includes `resolves`, **omits `solves`**
  - L574: `| resolves | open_problem / conjecture | theorem-like | the theorem
    settles the open problem |`
  - L592: worked example `{"source":"OP1","target":"TH2","type":"resolves",...}`

The agents obeyed the spec exactly. The real defect is a **three-way vocabulary
disagreement**:

| source | lists `solves`? | lists `resolves`? | lists `grounded_to`? |
|---|---|---|---|
| prompt L366 ("EDGE TYPES (7)") | NO | YES | no |
| prompt L571 direction table (8 rows) | YES | YES | no |
| `src/edge_types.py` / CLAUDE.md | YES | **NO** | YES |

So the prompt contradicts itself (7 vs 8 types) *and* contradicts the code. Both
`solves` (56) and `resolves` (40) appear in the corpus because both are blessed by
the direction table.

Notably this is the exact relation **T-OPEN** (`discovery_suite/open_problems/`)
is built to discover, so it is worth first-class encoding rather than erasure.

*Revised options (the earlier "widen `solves`" recommendation assumed `resolves`
was spurious — it is not, so that recommendation is withdrawn):*
1. **Adopt `resolves` as canonical** and add it to `src/edge_types.py`. The corpus
   already uses it correctly and consistently (40/40 open_problem|conjecture ->
   theorem-like, zero exceptions), it is the T-OPEN relation, and it requires NO
   data migration. `solves` stays algorithmic. **Recommended.**
2. Collapse `resolves` into `solves` — contradicts the spec the corpus was built
   under and needs a migration pass.

Whichever is chosen, **the prompt's own 7-vs-8 inconsistency must be fixed** and
`edge_types.py` reconciled, or v6 reproduces the same split.

*Decision: DEFERRED.* Requires an owner call (schema is Or's). Do NOT mutate
mid-extraction — apply once over all 100 papers, as was done for edge direction.
Until then the 40 edges stay as extracted; they are internally consistent and
losslessly convertible either way.

**E114. `\ref`-only section/appendix titles.** Appendix A titled literally
`Derivation of $(\ref{eq:free energy})$`. Rule 12 bans cross-ref markers in
`section`, so the agent invented a title — a spec-forced fabrication.
*(reported: `1301.1423v2`)*

**E115. No confidence rung for non-theorem explicit float environments.**
`pseudocode`/`figure` envs are explicit markup but not theorem-like; the rubric
covers only explicit theorem envs vs prose promotion. Agent used 0.9.
*(reported: `1301.1423v2`)*

**E116. Must steps partition the parent body?** Rule 13 implies tiling, which
duplicates bytes for long appendix proofs. Agents variously tile fully or use
leading phase sentences only. *(reported: `1301.1423v2`, `1709.02579v2`)*

**E117. No edge for "experimental baseline compared against".** RFPI vs CISR
modelled as `uses`, overloading the relation. *(reported: `1301.1423v2`)*

**E118. `genus`/`differentia` verbatim-ness is unenforceable when the genus is a
display equation** — needs light canonicalization (`$...$` wrapping), unlike
`assumptions`/`conclusions` which stay 100% verbatim. *(reported: `1301.1423v2`)*

**E119. Adjacent sentence *fragments*.** Contiguity + clean node boundaries
conflict when one sentence runs syntactically into the next result; a
`span_continues` marker (or explicit permission for fragment spans) would help.
*(reported: `1301.1423v2`)*

## E120 (HIGH — silent data loss). Forward references force edge deletion to keep the DAG

`1707.01421v4`: Prop. 1's proof cites "Remark 2 and Remark 3 **below**"; Remark 3
cites "Remark 5 below". Honoring these creates cycles, so the agent **dropped two
real remark->proof edges** to satisfy the acyclicity requirement.

This is the first confirmed case of the spec forcing *deletion of a true edge*.
Every other logged issue is a typing/labelling ambiguity; this one silently
removes real mathematical dependency, and it is invisible in the output (a
dropped edge leaves no trace, unlike a mistyped one).

Forward references are normal mathematical writing, so this will recur wherever a
proof defers a lemma.

**Prevalence is NOT recoverable from the corpus — measurement attempted and it
cannot be done.** A scan for "<Kind> <N> ... below" that resolves to a real node
returned 0 hits across 88 papers, but the detector is unsound, not the finding:
node `name` fields are *descriptive* ("holonomic $\W_n$-module", "Proof of
Theorem 2", "Part (i)"), never "Remark 2", and `\label{}` is stripped by the
mandated cleanup. So a statement reading "see Remark 3 below" has no numbered
name and no label to resolve against. 238 nodes in 54 papers contain
below/later/in-the-sequel cues, but that is an upper bound on *opportunity*, not
evidence of dropped edges.

Confirmed occurrences remain exactly **1 paper / 2 edges** (`1707.01421v4`),
known only because that agent volunteered it in its report. Any other instance is
invisible. This unmeasurability is the core hazard, not the raw count.

*Corollary for v6:* whatever the acyclicity fix, nodes should retain their source
`\label` (or a `source_ref` field) — otherwise cross-reference integrity can
never be audited, here or anywhere else.

*v6 options:* (a) an edge attribute `forward_ref: true` exempt from the acyclicity
check; (b) keep the edge and relax the global DAG requirement to "acyclic after
removing forward_ref edges". Either way the edge must be **recorded, not dropped**.

**E121. `proof_strategy` vs step-`subclass` vocabularies overlap and mislead.** No
`variational`/`concentration_compactness`/`symmetrization`/`integration_by_parts`
for analysis/PDE; an agent reached for `bound_estimate`/`invoke_identity`, which
are step subclasses, then had to drop them. *(also reported: `1709.02579v2`)*

**E122. Adapted external results are unclassifiable.** `origin` is binary
(`paper`|`external`), but Lemma 2 is "provable by minor modifications of Cazenave
Prop. 1.7.6" and the Weinstein functional swaps in H for Dirichlet energy — neither
purely own nor purely cited. Proposal: `derived_external` value or `adapted_from`
field. *(also reported: `1712.00232v3`)*

**E123. `\medskip`, `\noindent` and friends are not in the mechanical-cleanup
allowlist**, so formatting macros persist inside long proof bodies.

**E124. `source_typo` flag.** Verbatimness requires copying real source errors
(`\int_{\rn}|v_{n_k}|dx` missing an exponent; `|v_k|+|z_k|\le|v_{n_k}|` should be
w_k). A flag would let consumers distinguish faithful transcription from
extraction error.

**E125. Whitespace normalization must precede verbatim verification** — `\end
{equation}` (with a space) defeats exact matching. Affects the audit tooling, not
just the prompt.

**E126. `origin` tiebreaker for "standard but uncited".** Lemmas 3.1/3.2 in
`1609.00771v2` are introduced as "well-known in convex geometry" with NO citation,
yet the paper proves them itself — rule 6 defines external as a cited result the
paper does not establish, so neither branch fits. Agent chose `external` with a
prose `origin_citation`. Meanwhile equally-standard toric-geometry terminology in
the same paper carried no signal phrase and was marked `paper`. The classification
therefore turns on the presence of a hedging phrase, not on provenance.

**E127. Multi-part theorems: one node or several?** Theorem A has parts I and II
with separate `\begin{proof}[Proof of Theorem A, part N]` blocks. Agent emitted one
`theorem` with two `proves` edges. Unspecified — and it shifts theorem-like counts
across papers, so it contaminates cross-paper and per-category statistics.

**E128. Prose construction: `definition` or `algorithm`?** Rule 7's promotion
clause is written only for `\begin{definition}` bodies, but "type is determined by
semantic content, not LaTeX environment". In one paper the same agent kept an
inductive construction ("we define a map phi ... this procedure") as `definition`
while promoting a `\begin{rem}` describing a search procedure to `algorithm`. Both
calls are defensible and mutually inconsistent.

---

## Corpus-metadata caveat (NOT a prompt issue) — `category` is the sampling query, not the primary category

`extraction_targets_opus5.csv` carries only `arxiv_id,category`, where `category`
is the arXiv **query** the paper was sampled from. arXiv returns cross-listed
papers for a category query, so a paper can occupy a slot for a category that is
not its primary. Confirmed: `1609.00771v2` sits in the `math_GR` slot but is
Diller & Lin, *Rotation Numbers of Elements in Thompson's Group T*, whose primary
listing is **math.DS**.

**Impact:** the planned per-subfield analysis (ROADMAP 7.5) would attribute this
paper's metrics to group theory rather than dynamical systems. Prevalence across
the 100 is unmeasured.

**Fix (cheap, post-hoc):** fetch the true `primary_category` + full category list
from the arXiv API for all 100 ids and add them as separate columns, keeping
`category` as `sampled_from`. Does not touch any extraction.

**E129. HARD RULE 2 wording invites a false conflict.** Rule 2 reads "NO
REGEX-SCRIPT SHORTCUT ... Identify each result environment semantically, then
COPY its body into the JSON node. Do NOT write a Python script that greps for
`Theorem N.M` patterns." Three agents read this as banning *any* builder script
and flagged a "direct conflict" when asked to use one.

The prohibition is actually narrow — it bans regex **identification**, not
mechanical **transcription** of spans the model located semantically. Evidence
that the narrow reading is correct: `1102.4533v1` chose a builder script under the
frozen prompt alone, with no operator instruction, and its output is verbatim-clean.

*v6 fix:* say so explicitly, e.g. "You MAY use a script to slice spans you have
already identified by reading; you MUST NOT use pattern matching to decide what
is a result." This also makes extraction more robust — emitting a large graph as
literal output tokens caused 11 mid-stream failures in batch 5, while
slice-from-anchor builds succeeded.

*Density check (mechanism does NOT bias output):* builder-built papers land at
edge/node 1.73 and 1.46 against a corpus mean of 1.73. The single low outlier
(`1302.1114v2`, 0.99) is explained by E8 — it emits no step->parent edges and is
47% step nodes — not by the write method.

## E130 (HIGH — schema gap, corpus-wide). `rigor` is declared universal but never requested

`src/node_types.py:118` and `CLAUDE.md` declare `rigor`
(formal|semi_formal|heuristic|numerical|conjectural) a **universal orthogonal
field on every node**. The v5.1 prompt mentions it **once**, parenthetically, at
L401 — "NOT how rigorous the maths is (that is `rigor`)" — while defining
`confidence`. It is absent from every required- and optional-field list.

Measured over 95 papers / 11,960 nodes: **600 nodes (5.0%) carry `rigor`**,
concentrated in **6 papers** (4 at 100%, 2 partial); the other **89 papers have
none**.

This is the canonical "mentioned but unspecified" failure: agents who noticed the
parenthetical inferred the field was wanted; the rest did not. Same frozen prompt,
opposite behaviour — so the split is a *prompt defect*, not agent error.

*Consequences:* (a) the corpus is missing a field the schema calls universal;
(b) the 600 present values are not usable for cross-paper analysis (n=6 papers,
confounded with which agent noticed).

*v6 fix:* decide and state it once — either add `rigor` to the required field
list with the closed vocabulary and a rubric, or drop the L401 parenthetical so
nothing dangles. Do **not** leave it mentioned-but-unspecified.

*Do not strip the existing 600 values* — they are real and correctly typed;
just exclude `rigor` from any cross-paper statistic for this corpus.

**E131. `\begin{comment}...\end{comment}` is not in the permitted-cleanup list.**
`1310.8200v3` hides a ~180-line superseded proof plus the bibliography inside
`comment` environments; leaving them in would have put an abandoned proof inside
PP1.7's verbatim body. Agent stripped them (correctly, in effect) but the spec
does not authorize it.

**E132. Environment attribution markers.** `\begin{thm}\cite{Berger}` and
`\begin{thm}[Heine-Borel]` — leading `\cite{...}` / `[...]` dropped from
`statement`. Spec is silent; both drop and keep leave a valid verbatim substring.

### E113 addendum — the 7-vs-8 contradiction is now confirmed to cause divergent encodings

Two batch-5 papers encode the SAME relation (problem -> algorithm) differently,
each following a different part of the same frozen prompt:

| paper | encoding | which part of the spec it followed |
|---|---|---|
| `1608.03959v1` | `solves` x3 | the direction table (8 rows, includes `solves`) |
| `1809.03369v2` | `uses` | the "EDGE TYPES (7)" list (omits `solves`) |

Neither agent erred — the spec licenses both. This is direct evidence that the
L366-vs-L571 inconsistency produces **cross-paper incomparability**, which is
exactly what the uniform-prompt discipline exists to prevent. A downstream query
for "algorithms that solve a stated problem" silently misses the `uses`-encoded
ones.

*Post-hoc detectability:* recoverable — problem->algorithm `uses` edges are
identifiable by endpoint types, so a normalization pass can find them. Unlike
E120, no information was destroyed.

### E131 addendum — `\begin{comment}` now reported by 2 agents

`1310.8200v3` (superseded ~180-line proof + bibliography) and `1809.03369v2`
(commented-out blocks *inside* two proof bodies). Both stripped them; both flagged
that the permitted-cleanup list authorizes only `%`-to-EOL. Keeping them would put
text absent from the rendered paper inside a "verbatim" proof body — so stripping
is almost certainly right, but it must be **stated**, since an agent following the
list literally would produce a materially different statement for the same paper.

### E120 addendum — second confirmed instance, and the cause generalizes badly

`1104.0194v1` (Montejano & Serra) dropped **two more real edges** to satisfy
acyclicity:

- `TP1.3 -> PP1.10` — the proof of Lemma qp explicitly assumes the main theorem
  **in the quotient G/K**: this is the induction hypothesis.
- `TP1.3 -> DP1.11` — the "H-regular" definition is phrased via the main
  theorem's conditions.

Both close cycles through `PrP1.3 -> TP1.3`.

**Running total: 2 papers, 4 dropped edges** — and both known only because the
agents volunteered it.

**The cause is worse than first thought.** E120 was originally logged as a
*forward-reference* problem ("see Remark 5 below"), which is a stylistic habit.
This instance is **mathematical induction**: a theorem's proof legitimately
invoking the theorem at a smaller instance. Induction is not a stylistic quirk —
it is one of the most common proof techniques in mathematics, and it is
*intrinsically* cyclic in a dependency graph. Strong induction, minimal
counterexample, and descent arguments all have this shape.

So the acyclicity invariant is not merely inconvenient at the margins; it is
**structurally incompatible with a standard and ubiquitous proof pattern**, and
the current spec's only escape is silent deletion.

*Sharpened v6 requirement:* an edge attribute that marks a dependency as
`cyclic_ok` (subtypes: `induction_hypothesis`, `forward_ref`, `mutual_recursion`)
with the DAG check run on the subgraph excluding them. Combined with retaining
source `\label`s, this makes induction representable AND auditable. Without it,
every inductive proof in the corpus is silently missing its key edge.

**E133. Whitespace collapse destroys code-block layout.** Rule 1 mandates
"collapse runs of whitespace and newlines", but `1805.10626v3` contains Macaulay2
`verbatim` blocks whose *layout is semantic*. Flattening them to one line is
spec-compliant and lossy — a downstream consumer cannot re-render the scripts.
v6 should exempt `verbatim`/`lstlisting`/`minted` bodies from whitespace collapse.

**E134. No rule for code blocks as nodes.** Same paper: the "universal script"
became an `algorithm` with `algorithm_step` children; per-root-system code blocks
that are *procedures* also became algorithms; blocks that are bare literal point
lists (E8, F4, H3, H4) were skipped as data. Defensible, entirely unguided.

**E135. `\begin{question}` and `\begin{problem}` vs the closed vocabulary.**
`question` is not in the vocabulary (mapped to `open_problem`). Separately, rule
8 defines `problem` as computational/optimization/decision, so a
"characterize and classify" research problem that the paper *partially* answers
fits neither `problem` nor `open_problem`.

**E136. Duplicate content at two locations.** In `1805.10626v3`, Section 5
open-problem item 6 is verbatim identical to Question 2.11 after cleaning. Both
emitted with an `uses` edge; anchor resolution required an occurrence index.
Spec has no rule for genuinely restated content (cf. the 5 restatement encodings
already logged).

## E137. Measured fabrication rate: 2/12,817 (0.016%) — both worth fixing differently

Independent verbatim audit over the finished 100-paper corpus found 5 statements
untraceable to source; diagnosis by longest-matching-prefix shows only 2 are real:

- `1011.1633v3` EP1.1 — renames `g_i`->`s_i`, `=`->`:=`, and **adds** a factor
  `f(s_1 \triangleleft h_2, s_2)` absent from the source span. This is the exact
  failure the verbatim rule targets. Suggests an equation was reconstructed from
  understanding rather than copied.
- `1404.7771v1` RP1.4 — "frame matrix" -> "frame matroid": a silent correction of
  a genuine source typo. Rule-violating but semantically *improving*; argues for
  the `source_typo` flag proposed in E124 so agents can mark rather than fix.

The other 3 (`1512.04893v3`, `1611.01043v4`, `1710.09079v3`) are cleanup-scope
gaps (E131 `\begin{comment}`, E123 formatting macros), not fabrication. Closing
those two v6 items raises measured fidelity 99.96% -> 99.98% with no change to
model behaviour.

**E138 (spec self-contradiction). Rule 13 vs core rule #2 on trivial steps.**
Rule 13: every step gets a `statement_short`. Core rule #2: a `statement_short`
must be real compression and never longer than `statement`. For bare loop
terminators (`End Inner Iteration Loop;`) both cannot hold. The agent let core
rule #2 win and omitted the field, so step coverage read 10/12 rather than 12/12
— i.e. the contradiction shows up as an apparent metric shortfall rather than as
an error. *(reported: `1701.03237v1`)*
*v6 fix:* exempt steps whose statement is under ~N chars from the mandatory
`statement_short`, and say so, so the metric means the same thing everywhere.

**E139. `equation` vs theorem-like for closed-form evaluations.** Rule 9 forbids
demoting a *stated result* to `equation`, but gives no test for a closed-form
formula that asserts no existence/uniqueness/optimality. In `1701.03237v1` four
BSC/MSC mutual-information formulas were typed `equation`; read as asserted
results they would have been 4 propositions. A one-line test would stop this
swinging theorem-like counts between papers.

**E140. Non-contiguous proof bodies (worst case of B1 so far).** In
`1612.00206v1` the proof of Theorem 2 is *interrupted*: Lemma 4, Claim 5, and
both of their proofs are interleaved inside it. Rule 1 demands a single verbatim
contiguous `statement`, so `PP1.5` must span the whole region — which means the
Lemma 4 and Claim 5 statements AND their proofs appear verbatim inside
`PP1.5.statement` as well as in their own five nodes.

Distinct from earlier B1 reports (a proof merely *quoting* an auxiliary lemma):
here the outer proof's span necessarily swallows several complete sibling nodes,
so one region of source is emitted up to 3x at different levels. The
offset-based `spans: [[start,end],...]` design in section F fixes exactly this —
the outer proof would list its own fragments and skip the holes.

### E138 addendum — CONFIRMED to produce opposite resolutions across papers

Two batch-6 agents hit the Rule 13 / core-rule-#2 contradiction on short steps
and resolved it **opposite ways**, under the same frozen prompt:

| paper | resolution | effect on the metric |
|---|---|---|
| `1701.03237v1` | core rule #2 wins -> field OMITTED | step coverage 10/12 |
| `1509.06688v1` | rule 13 wins -> terse sub-length short EMITTED | step coverage 19/19 |

So `statement_short` coverage is **not comparable across papers**: the number
partly reports which horn of a contradiction that agent picked. Any table
reporting it per paper or per category is measuring spec ambiguity as well as
extraction behaviour. Must be settled in v6, and the existing figures should
carry the caveat.

### E126 addendum — the `origin` tiebreaker measurably shifts external-node counts

`1509.06688v1` adopted an explicit uniform rule and flagged the consequence:
`external` iff the span itself attributes the content ("From \cite{MMZ}"),
`paper` otherwise — including hedged attributions ("notation similar to
\cite{KM}", "constructed in a similar manner as described in \cite{KM}"). It
noted this "materially changes external-node counts across the corpus."

Combined with `1609.00771v2` (marked uncited "well-known in convex geometry"
material `external`) and `1003.2518v1` (marked uncited classical setup `paper`),
that is **three different tiebreakers across three papers**. `origin` counts are
therefore not cross-paper comparable either.

**E141. `\\` (line break) is not in the permitted-cleanup list**, so statements
retain formatting noise (`and \\$|\Delta_0(...)|=1$`). Spec should say whether it
may be collapsed. *(reported: `1509.06688v1`)*

## E142 (HIGH). Rule 9's node-count floor FORCES duplicate nodes for restated theorems

`1409.3255v2`: Theorem B appears twice as two textually *distinct*
`\begin{theoremB}` blocks (Introduction and Section 5). The source has 9 labelled
theorem-like environments and rule 9 requires `theorem-like nodes >= env count`,
so the agent emitted **both** (TP1.2, TP1.3) rather than deduping — and `PP1.7`
carries `proves` edges to both (1.0 and 0.9). It flagged: "Downstream dedupe
should be aware these are the same result."

So rule 9, written to prevent *under*-extraction, mandates *duplicate truth* for
the common "state it in the intro, restate it before proving it" pattern. The two
nodes are not near-duplicates a matcher would catch by string equality either,
since the two blocks are textually different.

*v6 fix:* let rule 9's floor count *distinct results*, not environments, and add
an explicit `restates: <node_id>` field (or reuse `specializes` with a
`same_result` flag) so the relation is recorded instead of the duplication being
silent. This is the 6th distinct restatement encoding seen in the corpus.

## E143 (HIGH — affects T-PLAG / T-ALIGN, not just extraction). Unexpanded custom macros make spans un-comparable across papers

Macro expansion is not in the permitted-cleanup list, so verbatim `statement`
values retain each paper's private macros — `1409.3255v2` keeps
`\CQ \G \PP \Ocal \s \D`; `1102.4533v1` keeps `\gl \sgl \Ws`; `1809.03369v2`
keeps `\tjnew{} \wa{} \Era \phif \Kry`; `1705.08048v2` keeps `\bC \vL \roi`.

Consequence: a statement is only renderable with its own paper's preamble, and
**any cross-paper string or token matcher compares macro spellings rather than
mathematical content.** That is precisely the matching step T-PLAG and T-ALIGN
depend on, so this is a data-quality issue for the discovery suite, not only a
readability one.

*Options:* (a) expand macros during cleanup and store both raw and expanded;
(b) keep raw but emit a per-paper macro table in `metadata` so downstream can
expand; (c) leave as-is and require matchers to normalise. (b) is cheapest and
loses nothing.

### E143 REVISED — do NOT expand macros. Measured: expansion manufactures false positives

Initial framing ("expand macros so spans are comparable") was wrong. Measured
over 120 staged papers, both normalisation directions are lossy:

**Same expansion, different meaning — 341 expansions collide across papers.**
The macro NAME is the only disambiguator:

| renders as | names used |
|---|---|
| `\mathcal{C}` | `C`, `Casimir`, `Cc`, `Ccal`, `Cir` |
| `\mathcal{M}` | `Intw`, `M`, `MM`, `Mabs`, `Mm` |
| `\mathcal{D}` | `D`, `DC`, `Dcal`, `Dd`, `EssD` |

Expanding `Casimir` and `Cir` both to `\mathcal{C}` asserts a match between a
Casimir element and a circle.

**Same name, different meaning — 473 names collide.** So the name alone is no
better: `\e` -> {`\begin{equation}`, `\epsilon`, `\eta`, `\mathbb{E}`};
`\R` -> {`\mathbb{R}`, `\mathcal{R}`}; `\MM` -> {`\mathbb{M}`,
`\boldsymbol{M}`, `\mathcal{M}`}.

**Conclusion: the (name, expansion) PAIR is the unit of meaning.**

*Revised plan:*
1. `statement` stays RAW — no expansion. Keeps the corpus uniform and preserves
   within-paper co-reference.
2. Add `metadata.macros: {name: expansion}` — a per-paper **glossary**, parsed
   from the preamble by regex, no LLM, no re-extraction. Additive, so it can be
   backfilled onto all existing papers.
3. Matchers consume the pair, and may derive an expanded form on demand. Never
   store an expanded span as if it were the source.
4. **Macro co-occurrence is unused graph signal.** Measured: a median of 7
   custom macros per paper appear in >1 node, each linking a median ~13 nodes.
   That is author-certified evidence those nodes concern the same object, and the
   extractor currently emits edges only from explicit `\ref`s and clear-cut
   prose. Worth testing as an edge source — including for the dependencies E120
   loses. Precision must be measured first: check what fraction of EXISTING
   edges macro co-occurrence recovers before trusting the pairs it adds.

*For the discovery suite:* embed the macro NAME text (`Casimir`, `Intw`, `EssD`
are English-ish mnemonics), not only the rendered symbol. This gives a principled
reason to expect name+symbol concatenation to beat either alone.

### E120 addendum 2 — third instance, third distinct cause

`1705.02177v2` dropped a correct edge to break a cycle. New cause: **this paper
completes a CITED prior theorem's proof.** Theorem 1 is Langer-Singer's, but
sections 5.4/5.5 supply its missing winding-number and selfintersection proofs.
So `PrP1.9 -> TP1.1` and `PrP1.10 -> TP1.1` are real, and the equally real
`TP1.1 -> DP1.9` ("orbitlike" names the curvature family from Thm 1) closes a
cycle. The agent dropped `TP1.1 -> DP1.9` and re-pointed DP1.9 elsewhere.

**Running total: 3 papers, 5 dropped edges, THREE independent causes:**

| cause | paper | why it cycles |
|---|---|---|
| forward reference ("see Remark 5 below") | `1707.01421v4` | cited material appears later |
| **mathematical induction** | `1104.0194v1` | proof assumes the theorem in a quotient |
| **completing a cited theorem's proof** | `1705.02177v2` | paper both uses and proves the prior result |

Three unrelated mechanisms in three papers means this is not a tail case — the
acyclicity invariant is structurally at odds with ordinary mathematical practice,
and the only escape the spec offers is silent deletion. Still unmeasurable
post-hoc (nodes keep no source label), so 5 is a floor, not an estimate.

### E142 addendum — restatements are sometimes byte-identical, sometimes not

`1705.02177v2`: TP1.2/TP1.3 and CP1.1/CP1.2 have **byte-identical** statements;
rule 9 requires all four nodes. Contrast `1409.3255v2`, where the two Theorem B
blocks were textually *distinct*.

So a downstream dedupe by string equality catches the first case and misses the
second. Any dedupe must be semantic, or the spec must record the relation
explicitly (`restates: <node_id>`), which is the cheaper fix.

### E144. Spans are not always contiguous: interior excision of suppressed blocks

Measured on the full 200-paper corpus (2026-08-04). `audit_verbatim.py` reports
99.97% traced (7/25162 unmatched), but that figure is generous: 107 nodes match
only on their **head**, so a mid-span difference is invisible to it.

A stricter whole-span, whitespace-insensitive check finds **84 nodes across 19
papers** whose `statement` is *not* recoverable as one contiguous source
substring. Reconstructing them greedily takes 2–12 contiguous source chunks,
with head and tail both present in the source for almost all — i.e. the span
endpoints are real and **interior material was excised**, not invented. No
fabrication was found.

The excised material is LaTeX-suppressed content that the permitted-cleanup list
does not cover, and which several agents explicitly reported removing:
`\iffalse…\fi` (`1705.02768v1`), `\begin{comment}` (`1612.05419v3`,
`1909.06098v1`), `\excludeversion` (`1212.6243v1`), `\ignore{}`/`\commentout{}`
(`1207.0773v2`, `1002.1782v3`), `\exclude{}` (`1811.04151v1`), `\suppress{}`
(`1404.1366v4`).

Agents split **both ways** on these: some excised (breaking contiguity), some
kept the text verbatim (preserving contiguity but injecting never-typeset
content into statements). That is a uniformity defect, not a model failure.

**v6 must state one convention** — the cleanest is to extend the permitted
cleanup to "TeX-suppressed blocks (`\iffalse`, `comment`/`excludeversion`
environments, and zero-expansion macros such as `\ignore`/`\exclude`) are
removed exactly like `%` comments", which makes excision legal and contiguity
recoverable.

**Also fix the audit**: head-only matching should be reported as its own bucket
(107 nodes) rather than folded into "traced", and the audit should apply the
whole-span check.

### E145. Multi-`\documentclass` submissions can yield the wrong main .tex

`1505.06386v1` shipped a standalone `fig/all.tex` (2,974 B) carrying its own
`\documentclass`, which `pick_main_tex` selected over the real 64 KB body
because it took the *first* match in arbitrary tar order. The extraction that
resulted was 1 node / 0 edges; after the fix it is 74 nodes / 87 edges.

Fixed in `scripts/fetch_tex_for_targets.py` by scoring candidates on
`(\documentclass, \begin{document}, \title, size)` and taking the max. The
whole 200-paper pool was re-swept; this was the only affected paper.
