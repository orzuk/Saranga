# Beyond the Library: An Agentic Framework for Autoformalizing Research Mathematics

**"Theo"** · Soltani Moakhar, JafariRaviz, Gholami, Springer et al. (Univ. of Maryland)
arXiv `2606.31134v3` · local: `G:\My Drive\Research\Automath\Papers\MohammandMarilandAutoFormalization_2606.31134v3.pdf`
Artifacts: <https://beyondthelibrary.github.io/formal_arxiv/>

Read 2026-08-23 for the Saranga v6 schema decision.

---

## 1. What the paper does

Autoformalization of **research-level** mathematics into Lean 4, driven by a
multi-agent pipeline whose orchestrator *is a Claude Code session*. The premise
is a capability inversion: general-purpose coding LLMs now beat small Lean-tuned
models, so the leverage is in **scaffolding**, not fine-tuning.

The named obstacle is the one in the title. Research papers depend on concepts
absent from Mathlib, so a system that can only compose library lemmas stalls
immediately. Theo therefore **builds the missing vocabulary first** and
formalizes the theorem second.

Two pipelines under one orchestrator:

| | Statement formalization (§2.1) | Proof formalization (§2.2) |
|---|---|---|
| goal | theorem + the types it needs, in Lean | machine-checked proof |
| key idea | type-first decomposition, validated by auxiliary lemmas | recursive tree of proof nodes |

The orchestrator writes **no** mathematical content itself — every line of Lean
and of natural-language proof comes from a subagent. It only routes, gates, and
backtracks. That is what keeps the derivation auditable, and it is a discipline
worth stealing independently of anything else here.

### 1.1 Statement pipeline

1. **Extractor** — finds the main theorem from the paper's PDF *and* LaTeX
   source, capturing "all definitions and assumptions required to understand the
   theorem, not just the theorem statement itself."
2. **Type Planner** — determines which types are missing from Mathlib and emits
   a **type plan**: a dependency *graph* over concepts. The orchestrator walks it
   in dependency order.
3. Per type: a **Lemma Planner** proposes well-known properties of that type,
   deliberately kept general and *not* tailored to the target problem. Then *k*
   **Type Formalizer** agents race to produce a Lean definition and prove those
   lemmas.
4. **Auctioneer** — best-of-*k* selection on three criteria: fraction of
   auxiliary lemmas proved, semantic alignment per a **Faithfulness Judge**, and
   Lean code length. Strictly gated: a flawed foundational type poisons
   everything downstream, so if no candidate passes, spawn more.
5. **Theorem Formalizer** — translates the main statement once the vocabulary
   exists.

The **auxiliary lemma** technique is the paper's cleanest idea: a definition is
validated by *unit tests*. If `2-edge-connected` is formalized correctly, then
"every vertex has degree ≥ 2" should be provable from it. Provability of
general, untailored consequences is the correctness signal for a definition.
This is explicitly framed as importing software-engineering practice —
object-oriented type decomposition plus unit testing.

### 1.2 Proof pipeline — the recursive proof tree

> "Following the same agentic paradigm as our statement formalization and
> **building on Liu et al. [4]**, our prover treats a proof as a **recursive tree
> of proof nodes**, where each node is a single statement to prove and the main
> theorem is the root."

**[4] = Numina-Lean-Agent** (Junqi Liu, Zihao Zhou, Zekai Zhu, Marco Dos Santos
et al., *"An open and general agentic reasoning system for formal mathematics"*,
arXiv `2601.14027`, 2026). **Note: a different group, not the Theo authors' own
earlier paper.** That is where the proof-node representation is specified in
detail; Theo inherits it. **Not yet read — should be, before v6.**

Per node, the same chain runs:

- **Natural Language Prover** — proposes an informal proof, using the paper's own
  argument where one exists.
- **Proof Critic** — audits the *informal* proof, in natural language only, never
  looking at Lean. Crucially it does **not** return pass/fail; it emits a list of
  concrete questions: inferences needing an unstated hypothesis, terms used
  before definition, hidden case splits, swapped quantifier order, appeals to "a
  standard argument", and steps that silently prove something weaker or stronger
  than the goal. The prover answers each against the source and rewrites; loop
  until no questions remain. This runs *inside* the prover so the orchestrator
  never sees the intermediate rounds.
- **Proof Detailer** — expands the accepted proof into tactic-sized steps and
  named sub-lemmas.
- **Lemma Breakdown** — decomposes into a **topologically ordered set of lemmas
  with stable identifiers**.
- **Lemma Leanifier** — each becomes a Lean statement with body `sorry`.

Three control decisions worth naming:

**Leaf-or-recurse is scored, not fixed.** Before proving a node the orchestrator
scores it on depth in the tree, length of its Lean statement, quantifier nesting,
and *cues in the source text* — "a step the paper calls immediate, versus one to
which it devotes a full section". Low score → leaf, close directly. High → break
into sub-lemmas.

**Parent before children.** Always. The parent is proved first using each child's
statement as an unproven `sorry` premise, and only then does it recurse. Reason:
the parent proof is what reveals whether a child's statement is *usable* — a
lemma can look reasonable and be too weak, too strong, or simply wrong for the
goal it must support. Proving children first sinks effort the parent would have
shown to be misdirected.

**Statements are immutable.** A proof attempt is accepted only if it leaves the
node's statement **byte for byte** unchanged (the "Claim Check" tool), while
still allowing added imports, opens, and helper lemmas. It also rejects imports
that would create a cycle against the node's ancestors. A proof therefore cannot
silently weaken the thing it closes.

**Failures are structured, not boolean.** A failed attempt returns a diagnosis —
missing hypothesis / child lemma too weak or contradictory / goal stuck despite
valid tactics — and the orchestrator routes each differently: re-run breakdown to
introduce a lemma, reformalize a conflicting child, or *promote a node that was
misjudged a leaf* back into the full pipeline. This is what makes backtracking
dynamic rather than a fixed retry.

**Cited prior work becomes an axiom.** The breakdown may tag a lemma as a result
cited from published work rather than something to prove. It is admitted as a
Lean `axiom`, and the Faithfulness Judge verifies the axiom matches the cited
result. This is the only route by which a non-Lean/Mathlib axiom enters.

---

## 2. Results

**PutnamBench:** 32/32 on a seed-0 random sample → Wilson lower bound **91.3 %**
at 95 % confidence over the full 672. At **~$5/problem**, on a flat $200 Claude
subscription (~$150 over three weeks). The same workload at metered API list
rates would be ~$939, i.e. ~$29/problem — which is *why* they run on a
subscription. Compare Aleph 94.8 % at $54/q, Seed-Prover 1.5 86.5 % at ~$168/q.

**Seven research papers** — five STOC (incl. STOC 2025) plus two OpenAI
manuscripts, across combinatorics, communication complexity, mechanism design,
learning theory, discrete geometry, number theory, graph theory. Main theorems
only, *not* whole papers.

The headline framing is unusually honest and is the part most relevant to us:

> **Axiom count is not a measure of system weakness but "an honest readout of
> each paper's self-containedness."**

| paper | area | axioms beyond Lean kernel |
|---|---|---|
| Mackenzie & Saffidine | communication complexity | **none** (cited results reproved from scratch) |
| Gravin & Jia | mechanism design | **none** |
| Pham | combinatorics | 1 — the paper's own Lemma 2.9 bound |
| Rivkin et al. | information-theoretic LB | 2 |
| Kalai et al. | learning theory | 3 |
| OpenAI [23] | discrete geometry | 2 |
| OpenAI [24] | graph theory | 3 |

**It found a gap in a peer-reviewed STOC proof.** Formalizing Pham against the
paper's literal definitions, the system produced a computer-verified
counterexample showing the paper's Lemma 2.6 is false as stated, so the
surjection Ψ_u is not surjective and the counting step fails for general H. They
are careful: this impugns *that proof*, not the theorem. Lacking a valid proof it
admits the bound as one scoped axiom and proves everything else. Driven by a CS
expert with limited Lean knowledge.

Other faithfulness catches: a theorem asserting monotonicity of `UB` where the
paper establishes it *only numerically*, by reading the shape off a plot.

**Output artifact:** group-level **proof-dependency DAGs** — box = proof stage
(with Lean files · lines · declarations), edge A→B = stage A uses stage B,
**transitively reduced**, bidirectional edges for mutual recursion, colour-coded
for admitted axioms vs. reproved-from-scratch external results.

**Limitations they state:** algorithmic results (algorithm + correctness +
complexity) were *not* formalized in any paper — only non-algorithmic main
theorems. And the backing model is closed-source, hurting reproducibility.

---

## 3. Relevance to Saranga

Different goal, overlapping representation. They formalize a handful of theorems
deeply (7 papers, ~$5–29 each); we extract 100K papers shallowly at ~3 s each.
Their structures are a **target** we can partially populate, not a plan we can
copy — anything requiring a Lean kernel or an agent per node is out of budget by
four orders of magnitude.

The useful question is narrower: **which of their representational choices can a
silver extraction capture, and which of those survive distillation into regex?**

### 3.1 Their proof tree vs. our `proof_step`

| | Saranga v5.1 | Theo |
|---|---|---|
| shape | **flat list** — `proof_step` with `parent_id` + `step_order` | **recursive tree**, arbitrary depth |
| node content | verbatim source span | a *statement to prove* (a claim, not a text span) |
| granularity rule | none stated | **scored** leaf-or-recurse |
| ordering | `step_order`, 1-based | topological order over a DAG |
| cross-links | steps may `uses` Level-1 nodes; **step→step across parents forbidden** | children are premises of the parent; cycles explicitly rejected |
| identity | `PSP5.1`-style, positional | **stable identifiers** from Lemma Breakdown |

Three real differences, in descending order of importance to us:

**(a) A step is a *claim*, not a span.** Our `proof_step.statement` is verbatim
source text with a `subclass` naming its rhetorical role
(`apply_lemma`, `case_split`, …). Theirs is a *statement to be proved* with
premises. Theirs composes — a node's children are exactly its obligations —
whereas ours describes. This is the deepest gap and it is **not** closable by a
prompt change alone; it is a schema question about whether `proof_step` carries a
claim in addition to a span.

**(b) Depth 1 vs. depth n.** Our `parent_id` already permits a chain, but the
prompt's worked example emits a flat "Part (1)/(2)/(3)" list, and the corpus
reflects that: 7,332 steps over 2,383 proofs ≈ 3.1 steps/proof, essentially flat.
A nested proof (lemma proved inside a proof, then used) is representable in our
schema and is *not being asked for*.

**(c) Granularity is unspecified in our prompt.** This is v6 item B2/E54
territory and is measurable in our own data: `proof_step` is our **largest** node
type (29 % of all nodes) and also our **least confident** (0.889 mean, per-paper
means down to 0.650). Theo's leaf-or-recurse score is a directly transplantable
idea — and note that two of its signals are *textual cues in the source*
("immediate" vs. a full section), which is exactly the kind of surface signal a
regex student can see.

### 3.2 Candidate v6 changes, sorted by whether they survive distillation

The test that matters for Yaron: **can a deterministic regex over LaTeX produce
this, or does it need a model?** Fields that only an LLM can fill make T2 richer
but widen the T2→T3 gap, which is the thing NtRED has to close.

| # | Change | Schema or prompt | Distillable to rules? | Verdict |
|---|---|---|---|---|
| 1 | **`proof_step.depth` / true nesting** (allow `parent_id` → another `proof_step`) | schema: none needed, `parent_id` already exists; **prompt** must ask | **Partly.** Nested `\begin{proof}` inside a proof, and "Proof of Claim N" headers, are lexically visible. Deeper logical nesting is not. | **Do it.** Cheapest real win; no type-count change. |
| 2 | **Granularity rubric for leaf-or-recurse** | prompt only | **Yes, partly** — "immediate/clearly/trivially" vs. a `\subsection` devoted to a step are regex-visible cues | **Do it.** Directly attacks our worst-confidence type. |
| 3 | **`cites_external` on a step/lemma** (their "admit as axiom" tag) | schema: we already have `origin: external` + `origin_citation` on nodes — extend to steps | **Yes.** `\cite{}` inside the span is a hard lexical signal. | **Do it.** Nearly free; we have the field. |
| 4 | **Statement-immutability / byte-exact claim check** | neither — it is a *pipeline* invariant | n/a | **Already ours** in spirit (verbatim spans, 99.9 % audit); becomes *provable* under v6 §F offsets. Reinforces §F. |
| 5 | **`proof_step.claim`** — the obligation, separate from the span | **schema: new field** | **No.** Requires understanding what the step establishes. | **Defer.** Big T2-only win, widens the T3 gap. Revisit after distillation is fixed. |
| 6 | **Auxiliary lemmas per definition** (their unit-test idea) | schema: new node/edge | **No.** Pure generation, not extraction. | **Out of scope** for extraction; interesting as a *validation* idea for our `definition` nodes. |
| 7 | **Type/concept dependency plan** (their Type Planner graph) | — | — | **We already have this**: `definition`→`definition` `uses` edges plus the foundation graph. Their type plan is our concept DAG rebuilt per paper. Worth citing as convergent evidence for the concept-inheritance DAG in `representation_strategy`. |
| 8 | **Transitively-reduced dependency DAG** as an output view | neither — a rendering choice | n/a | **Free.** Portal-side; makes dense graphs readable. |

### 3.3 What this says about the v6 decision

The paper **supports scoping v6 tightly** rather than expanding it:

- Items 1–3 are **prompt changes with no type-count change** — they join `label`
  (E146) and `rigor` (E130) in the class that does not break the 18-node/7-edge
  schema lock the paper hardcodes.
- Item 5 is the one genuinely attractive schema addition, and it is precisely the
  one a regex student cannot learn. Adding it makes T2 better and T3 relatively
  worse — the opposite of what the NtRED argument needs right now.
- Item 4 is an argument *for* §F offsets, which we had already put after
  submission.

Convergent-evidence points worth noting in the paper's related work: their
Extractor captures "definitions and assumptions required to understand the
theorem, not just the statement" — this is our `assumptions`/`conclusions` split
and `origin: external` chain, arrived at independently for a different purpose.
And their axiom-count-as-self-containedness readout is a measurement our corpus
could make at scale and they can only make one paper at a time.

### 3.4 Open item before v6 is finalised

**Read Numina-Lean-Agent (Liu et al., arXiv 2601.14027).** It is the actual
source of the proof-node representation; Theo cites it and does not re-specify
it. If we are going to align `proof_step` with anything, it should be with that
spec, not with Theo's one-paragraph summary of it.
