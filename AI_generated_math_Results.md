# Studying AI-assisted mathematics through the dependency graph

**Status: research plan, not results.** Written 2026-08-07. Nothing here has been
measured yet; the point of the document is to say what would have to be true for
the study to work, and what would sink it.

## 1. The question

Do proofs produced with substantial AI assistance differ *structurally* from
human ones, in ways a typed dependency graph can see?

Candidate structural signals, all computable from a Saranga graph today:

| signal | graph quantity | hypothesis being tested |
|---|---|---|
| depth | longest dependency chain (median 14 in our corpus) | are AI proofs shallower — more direct, less layered? |
| breadth | nodes, edges, branching factor | do they introduce fewer intermediate lemmas? |
| reuse vs invention | `definition` count, ratio of new definitions to imported ones | do they invent new machinery or recombine existing? |
| external reliance | share of `origin: external` nodes | do they lean harder on cited prior results? |
| **technique distance** | subject distance between a theorem and the external results its proof uses | **do AI proofs reach further across fields?** |
| granularity | `proof_step` per `proof` | are AI write-ups more or less explicit? |
| lemma economy | theorem-like : lemma ratio | do humans scaffold more? |

The technique-distance one is the most interesting and the most Saranga-specific:
it needs typed external nodes plus the foundation graph, which is exactly what
we have and what Tao's format and the Lean blueprints do not.

## 2. Why this could be a better story than T-OPEN

- It is a **question about mathematics**, not about our pipeline. The graph is
  the instrument, not the subject — which is a much stronger framing for a paper.
- It is **timely to the point of urgency** and nobody has done it, because
  nobody else has automated typed extraction at scale (see
  `tao_visualization_paper_Graph.md`).
- It reuses the whole stack: extraction, the foundation graph, cross-paper
  alignment. T-OPEN infrastructure (`discovery_suite/open_problems/`) applies
  almost directly.

## 3. What we do NOT have — read this before planning around it

**Our corpus cannot answer this question.** The 200-paper silver set is sampled
from roughly 2010–2019. Scanning all 200 staged `.tex` files for any mention of
GPT / ChatGPT / Claude / AlphaProof / Gemini / "large language model" returns
**1 hit, in a 2017 paper** — i.e. a false positive.

So this study needs a **new corpus**, freshly downloaded and extracted:

1. a set of AI-assisted papers (2025–2026), and
2. a matched human control set.

That is a real cost — download, extraction, and the Opus spend — and it should be
weighed against the v6 re-extraction, not stacked on top of it without a decision.

## 4. Candidate sources for the AI-assisted set

Found 2026-08-07; each needs verification, and the "what did the AI actually do"
column is the part that will take the work.

**Individual papers with documented assistance**

- [arXiv 2509.03065](https://arxiv.org/abs/2509.03065) — *Mathematical research
  with GPT-5: a Malliavin-Stein experiment*
- [arXiv 2510.26647](https://arxiv.org/abs/2510.26647) — convex analysis; GPT-5-Pro
  established a Taylor expansion for the gradient of the biconjugation operator
- [arXiv 2511.18828](https://arxiv.org/pdf/2511.18828) — *Solving a Research
  Problem in Mathematical Statistics with AI Assistance*; GPT-5 Pro suggested the
  dynamic Benamou–Brenier formulation, yielding a minimax optimal rate
- [arXiv 2606.13614](https://arxiv.org/pdf/2606.13614) — *Majority-of-Three is
  Optimal*; GPT-5.5 Pro used to check calculations and find local simplifications
- [arXiv 2606.19681](https://arxiv.org/pdf/2606.19681) — moment-based Eulerian
  method; GPT-5.5 used for symbolic manipulation and derivation
- *On Learning-Curve Monotonicity for Maximum Likelihood Estimators* — cited by
  OpenAI as an open problem resolved with GPT-5.2 Pro
- Verbeken et al., *Early Evidence of Vibe-Proving with Consumer LLMs* (2026) —
  spectral region characterization with ChatGPT-5.2

**Systematic sources — these matter far more than any individual paper**

- **erdosproblems.com** (Thomas Bloom) — ~1,133–1,179 catalogued problems with
  several hundred marked solved, *and solver attribution*. This is the single
  best source, because it gives **the same problem solved by different agents**.
- **Formal Conjectures** (DeepMind, open source) — Lean statements for 353 Erdős
  problems as of early 2026. Gives verified statements, so alignment is exact.
- **AlphaProof Nexus** — reported 9 open Erdős problems and 44 OEIS conjectures.
- GPT-5.2 Pro on Erdős **#397, #728, #729**, formalized in Lean and accepted by Tao.
- OpenAI on the Erdős **unit distance problem** (May 2026).
- **AlphaEvolve** — matrix multiplication record, new optima on ~20% of targets.
  (Probably out of scope: these are *constructions*, not proofs, so they have
  little dependency structure to extract.)

**Detection at scale.** Acknowledgements live in the body, not the abstract, so
the arXiv API cannot find these. But our pipeline already downloads `.tex`; a
grep over the acknowledgements section for model names and assistance phrases is
a straightforward harvester, and it is the only way to get a population rather
than a handful of famous cases.

## 5. The confounds — this is where the study lives or dies

Ordered by how likely each is to kill it.

**5.1 Selection bias on problem type (fatal if unaddressed).** AI-assisted
results today cluster in combinatorics, analysis and Erdős-style problems, and
are overwhelmingly *short, self-contained, single-result* papers. A human control
drawn from arbitrary arXiv would differ in depth and breadth for reasons that
have nothing to do with authorship. Any raw comparison measures *problem type*,
not *who proved it*.

**5.2 The write-up is human even when the proof is not.** Nearly all of these
papers are human-authored expositions of AI-suggested steps. The graph measures
the exposition. "AI proofs are shallower" may just mean "this human wrote it up
tersely". This is not fixable by better extraction; it has to be stated as a
limitation, and it argues for measuring things the write-up style affects least
(technique distance, external reliance) over things it affects most (proof_step
granularity).

**5.3 Assistance is a spectrum, not a label.** "Checked my algebra" and "produced
the entire proof" are both "AI-assisted". Without a graded taxonomy the treatment
group is incoherent. Minimum viable taxonomy:

    L0  tool use only (numerics, symbolic manipulation, literature search)
    L1  suggested a technique or reference; humans supplied the proof
    L2  proved a lemma or a key step
    L3  proved the main result; humans wrote it up
    L4  autonomous, formally verified (AlphaProof-class)

Coding this requires reading each acknowledgement, and it should be done blind to
the graph metrics, or it will drift toward the hypothesis.

**5.4 Sample size.** The realistic population is tens, not thousands. With n≈30
per arm, only large effects are detectable, and multiple comparisons across seven
metrics will manufacture a significant result by chance. **Pre-register one
primary metric.** My candidate: technique distance.

**5.5 The extractor is the instrument.** If AI-assisted papers are systematically
shorter and cleaner, extraction quality differs between arms and every metric is
confounded. This must be checked directly — extract a sample of both arms, hand-
audit, and confirm the error rates are comparable — before any comparison runs.

## 6. The strongest design: same problem, different agent

The way to defeat 5.1 is to hold the problem fixed.

**Erdős problems with both a human and an AI solution** give matched pairs: same
statement, same difficulty, same subfield, different agent. `erdosproblems.com`
tracks solver attribution, so the pairing is available rather than inferred, and
`Formal Conjectures` supplies a canonical Lean statement so the two write-ups can
be aligned exactly rather than by text similarity.

This turns the study from "AI papers vs human papers" (hopelessly confounded)
into "two proofs of the same theorem" (a clean paired comparison), and it is the
one design worth the extraction cost. It also directly exercises **T-ALIGN**:
aligning two graphs that prove the same statement is exactly the cross-paper
alignment task, so the study and the tooling reinforce each other.

Cost: the number of such pairs is small — likely tens, possibly under ten with
*published* proofs on both sides. **Establishing that count is the first thing to
do, before anything else**, because if it is under ~15 the paired design is not
viable and the study falls back to the confounded population comparison.

## 7. Proposed sequence

1. **Feasibility count (days, no extraction).** Scrape `erdosproblems.com` +
   Formal Conjectures. How many problems have BOTH a human and an AI solution
   with a public write-up? This single number decides the design.
2. **Build the harvester.** Grep staged `.tex` acknowledgements for model names
   and assistance phrases; produce a candidate list with the L0–L4 taxonomy coded
   by hand, blind to metrics.
3. **Matched control set.** For each AI paper: same primary category, same year
   ±1, similar length, no AI mention. Match on covariates, do not sample at random.
4. **Extract both arms** with the same prompt version — v6 if it has landed, else
   the frozen v5.1, but *the same one for both arms*, or the instrument differs
   between treatment and control.
5. **Audit extraction quality per arm** before comparing anything (5.5).
6. **Measure the pre-registered primary metric**, then the rest as exploratory
   and labelled as such.

## 8. Honest assessment

**Upside:** genuinely novel, timely, uses the whole stack, and asks a question
people outside our subfield care about. The paired-Erdős version would be hard
for anyone else to run, because it needs typed extraction plus cross-paper
alignment.

**Risk:** it depends on a population that may be too small and too biased, and it
needs a *new* corpus we do not have. The failure mode is a paper reporting
differences that are really differences in problem selection and write-up style.

**Recommendation:** do step 1 — the feasibility count — before committing
anything else. It is cheap, needs no extraction, and it decides whether this is a
strong paired study or a weak observational one. Do not start extraction until
that number is known.

**Relation to the current plan:** this competes for the same extraction budget as
the v6 re-extraction, and it *needs* v6-quality extraction to be credible. The
natural order is v6 first, then this on top — not instead. It is an addition to
the roadmap, not a substitute for closing the distillation loop.
