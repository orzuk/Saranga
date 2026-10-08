# Learning to Discover Interesting Mathematics

Patel, Rammal, Hayat, Munos, Kempe (FAIR @ Meta, NYU, ENPC) · arXiv `2609.28603v1` (2026-09-23), 27 pp.
Local copy: `G:\My Drive\Research\Automath\Papers\LearningInterestingMath_Kempe_2609.28603v1.pdf`.
No code or data release is mentioned. The same group wrote Atlas / "Formalizing mathematics at scale"
(`2605.29955`, already in `Papers/`).

Read 2026-09-27 to ask whether any of it transfers to Saranga.

---

## 1. What it does

It asks which new theorems are worth adding to a library, and answers with a number that
can be computed from the proof and dependency structure, with no human taste involved.

**Primitive: conditional proof difficulty V(T | P).** This is the number of Lean proof lines
needed to prove theorem T when premise set P is available. The paper states three axioms for it:
- **Grounding:** V equals the observed line count in the library.
- **Premise monotonicity:** more premises never make a proof longer.
- **Composition:** V(T|P) ≤ V(L|P) + V(T|P∪{L}), with equality (a Bellman relation) when L is
  a genuine intermediate step.

**Data via "premise expansion".** Mathlib is too atomised to learn from directly: the median
proof is 3 lines and the median premise has 1 use. So they repeatedly replace a premise L of T
by L's own premises and add L's proof lines to T's label. This walks the dependency DAG
backwards. From 113K Mathlib declarations it produces 18K groups (110K prompts), with labels
of median 49 and max 500 lines.

**Difficulty model Vθ.** They fine-tune Qwen3.6-27B with GRPO to predict V from (definitions,
premises, target). The reward has three parts: a truth term, a Bellman-consistency term and a
one-sided monotonicity penalty. On held-out data it scores MAE 20 lines and Spearman 0.91,
against GPT-5.5 (MAE 31, ρ 0.78) and Claude Opus 4.6 (MAE 34, ρ 0.82). All three models
underestimate long proofs.

**Interestingness I(T|P) = 100 · V(T|P) / L(T|P).** This is proof length over conditional
description length. L counts the statement's characters plus the characters of every
definition needed to state it that is not already available through P. So the statement is
"easy to state, hard to prove" *relative to the vocabulary already available*. With P = ∅
it is absolute (I₀) and computable directly from Mathlib. The ordering looks right:
1ⁿ = 1 at the bottom, the mean value theorem low because its definitional prerequisites are
huge, and FLT for n = 3 or 4 at the top.

**Utility U₀(T) = (#direct users of T) · V(T|∅).** Roughly, this is how many lines the library
saves by having T. On Mathlib, **I₀ and U₀ correlate with Spearman 0.756**, excluding
theorems with no users. There are high-I, low-U theorems, but almost no high-U, low-I ones.
This is the key empirical claim: an intrinsic score available when a theorem is proposed
predicts extrinsic usefulness, which is only observable later.

**Using the metric.**
1. *RL conjecturer.* They train Qwen-27B with log(1 + Iθ) as the reward, where Iθ uses the
   learned Vθ so no proof is needed during training. Statements provable by `simp`/`rfl`
   get reward 0. Mean verified interestingness rises from 1.76 to 7.58 and beats prompted
   Claude Opus 4.6 in all 8 areas. An Opus judge rates the fraction of statements
   "substantially or fully contained in Mathlib" at 30.6%, versus 91.9% for the base model
   and 92.5% for Claude.
2. *Iterative discovery at inference time.* Claude 4.6 proposes 400 conjectures from 20
   premises, a semantic filter deduplicates them, Claude Code proves them in Lean, and the
   top 10 by *ground-truth* I are promoted into the premise set. This runs for 6 rounds.
   Ranking by I beats keeping everything, random promotion, and ranking by raw proof length
   on quality, diversity and "most interesting" judgements. Since raw length loses, the gain
   comes from the ratio and not just from long proofs.

**Limitations they state.** Lean line counts are a stylistic artefact (`aesop` and `grind`
trade lines for runtime). The metric doesn't capture "connects previously unrelated areas".
They don't invent new definitions. Whether promoted theorems are actually *used* later is
not shown.

## 2. Is it Lean?

**Entirely.** Mathlib / Lean 4 is the ground truth for proof length, dependencies,
definitions and statement length. Lean is also the verifier for generated conjectures, with
Claude Code as the proving agent. Nothing touches informal or arXiv mathematics. The learned
Vθ reads Lean prompts, and the "contained in Mathlib" check is an LLM judge.

## 3. Can Saranga use a similar approach?

Saranga doesn't need their model, and shouldn't adopt their Lean setting (see CLAUDE.md,
"do not Lean-ify"). But their three quantities are all **functions of a dependency DAG with
statement and proof spans**, which is what Saranga already extracts. The informal versions:

| theirs (Lean) | Saranga analog | available now? |
|---|---|---|
| statement length S(T) | tokens of the theorem-like node's verbatim `statement` | yes |
| definitions needed to state T, C(T) | `definition` nodes with `uses` edges into T, recursively | yes (in-paper) |
| C(P), what the reader already has | foundation-graph-grounded concepts, plus `origin: external` nodes | partially |
| proof length V(T\|P) | tokens of the `proof` node that `proves` T, plus its `proof_step`s | yes |
| premise expansion | unroll `uses` edges from in-paper lemmas: add the lemma's proof length to T's | yes, but edge recall is weak |
| direct users \|D(T)\| | in-paper out-degree of `uses`, and cross-paper via shared foundation objects | yes / via grounding |

Concrete uses, cheapest first:

1. **Informal I₀ and U₀ over the 100K T3 corpus, and a test of their correlation.** This needs
   no training and no LLM. The question is whether "short statement, long proof" predicts
   in-paper reuse (and, with S2 data, citations) on informal arXiv mathematics as it does on
   Mathlib. That is a new result either way, and a natural cross-paper diagnostic for the
   paper or a follow-up. Two caveats. Informal proof length is noisy: "it is easy to see" and
   cited external results make proofs short. Our own cross-category data shows about 30×
   variation in formal-environment density. So normalise within arXiv category, and treat
   `origin: external` citations as members of P, which is exactly their conditioning.
2. **Ranking inside the portal and the discovery tasks.** Score nodes by I and U to surface
   each paper's main results and key lemmas. For T-OPEN, a statement's conditional
   description length given the corpus's vocabulary is a cheap prior on which conjectures
   are "easy to state from known concepts". That fits the "tractability oracle" framing of
   Method E. V(T|P), premise-conditioned difficulty, is also a formal version of item 4 on
   the informal paper TODO list ("measure of distance in proof usage").
3. **Mathlib-grounded foundation nodes.** The foundation graph already contains Mathlib via
   LeanDojo/Herald. Their I₀ and U₀ can be computed *exactly* for those roughly 100K+
   declarations using their premise-expansion recipe, then attached to foundation objects.
   Paper nodes grounded to them inherit a "how deep a result does this lean on" signal.
   This is cheap and deterministic, and it is the only place Lean enters, as data we
   already hold.
4. **Not recommended now:** training an informal Vθ, or running their conjecturing and RL
   loop. That is proof generation, which our discovery-direction memo says not to compete
   on, and there is no verifier in the informal setting.

**Link to v6.** Every item above depends on dependency-edge quality, and edge F₁ (about 0.18)
is Saranga's weakest number. The v6 `label` capture, which turns about 26K `\ref`s into
`uses` edges, and nested `proof_step`s are what make premise expansion possible in the
informal setting. This paper is an extra argument for putting v6 first.

## 4. For our paper

Cite it in Related Work (the automated-discovery / interestingness thread, next to Colton
et al. 2000 and Tsoukalas et al. 2025) and in Discussion as a future use of the corpus. The
one-line framing: they compute interestingness on a formal library; Saranga's graph makes
an informal analog computable over the arXiv literature. Check the bib entry with
`scripts/check_refs.py` before adding it.
