# Studying AI-assisted mathematics through the dependency graph

**Status: plan + a completed feasibility check.** Written 2026-08-07.
Sections 1-8 are the plan as first written; **section 9 is the measured result of
step 1, and it retires the design proposed in section 6.** The plan is left intact
above rather than rewritten, so the reasoning that led to the gate — and what the
gate then overturned — both stay on the record.

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


---

## 9. Step 1 executed — the feasibility count (2026-08-07)

Ran the gate described in §7 against the **Formal Conjectures** repo
(`google-deepmind/formal-conjectures`, 604 formalized Erdős problems). Each
`.lean` file carries a machine-readable status (`@[category research solved]`),
an AMS subject code, and a prose paragraph naming who solved the problem and how
— e.g. *"Somani, using ChatGPT, has given a negative answer … formalized in Lean
by Wu using Aristotle."* That makes the count exact rather than estimated.

### What the corpus contains

| | count |
|---|---|
| Erdős problems formalized | 604 |
| solved | 273 (open: 292) |
| **solved, AI-attributed** | **44** |
| solved, human-attributed | 229 |
| AI ones carrying a `formal_proof` link | 39 |

Systems: Aristotle 29, ChatGPT 10, GPT-5 8, Claude 3, AlphaProof 2, AlphaEvolve 1,
Gemini 1.

### Three findings, in order of how much they change the plan

**(a) The strict paired design is dead.** Problems whose write-up names BOTH an AI
and a human solver: **2** (#650, #1074). Far below the ~15 needed. Same-problem
pairing is not available.

**(b) The subject-mix confound is milder than §5.1 feared — within this corpus.**
AI-touched problems are 62% AMS 11 (number theory) and 27% AMS 5 (combinatorics),
against 55% / 33% for the Erdős corpus overall. So an Erdős-internal control set
is reasonably matched *by construction*, and the 44-vs-229 comparison is a real
matched design even without exact pairing. This is better than assumed.

**(c) And the finding that actually decides it: the artifacts are not papers.**

| | problems | distinct arXiv papers referenced |
|---|---|---|
| AI-attributed solved | 44 | **3** |
| human-attributed solved | 229 | **7** |

Erdős solutions are overwhelmingly short notes, gists, MathOverflow answers and
Lean files. **A three-line construction has no dependency graph**, and our
instrument extracts graphs from arXiv LaTeX. So the Erdős route gives us plenty
of *attributed solutions* and almost no *extractable proofs*.

### Consequence

**Drop the Erdős-based design.** Not for lack of n on the problem side (44 is
fine) but because the population is the wrong kind of object for this instrument.
Continuing would have meant discovering that after paying for extraction.

**The surviving route is the acknowledgement harvester** (§4, "Detection at
scale"): arXiv papers whose acknowledgements credit substantial AI assistance —
the individually-found papers in §4 (2509.03065, 2510.26647, 2511.18828,
2606.13614, 2606.19681, …) are of exactly the right kind: full papers, real
structure, human write-up of AI-assisted work.

**The new gate, before any extraction:** how many such papers exist? arXiv's API
does not search full text and acknowledgements are not in abstracts, so this
needs either a full-text service or a targeted crawl of recent months in the
likely categories (math.CO, math.NT, math.PR, cs.LG theory). If that number is
also in the tens, the study is observational with a small n and should be framed
as a case study, not a population claim.

**Worth noting what this cost:** an afternoon and no extraction spend. Had the
gate been skipped, the same conclusion would have arrived after downloading and
Opus-extracting two arms of a corpus — which is precisely the argument for
putting a cheap feasibility count in front of an expensive pipeline.

---

## 10. Correction and major revision (2026-08-08)

**I had missed the central artifact.** §4 cited OpenAI's *Early science
acceleration experiments with GPT-5* — the wrong document. The one that matters
is:

### 10.1 *Ten Advances in Mathematics and Theoretical Computer Science* (OpenAI)

<https://cdn.openai.com/pdf/ten-proofs-oai.pdf> — "results obtained by an
internal OpenAI model". Updated 2026-08-06; the superseded version is preserved
at `ten-proofs-oai-original.pdf`.

Ten results, each a full chapter with its own proofs and references:

1. High-dimensional sphere packing — asymptotic strength of the Cohn–Elkies LP determined exactly
2. Binary and spherical codes — classical upper bounds improved by exponential factors
3. **Nonsofic groups exist** — settles whether every countable group is sofic
4. **Connes's rigidity conjecture disproved** — plus a finite-to-one question of Popa
5. Arithmetic circuit complexity — permanent lower bounds
6. Quantum parallel repetition — for every finite two-player entangled game
7. Closest vector problem — n^(1/400) hardness from a direct 3SAT reduction
8. **Ehrhart's volume conjecture** — sharp bound proved in every dimension
9. Multicolor Ramsey numbers — R_k(3) grows as k^Θ(k)
10. Extremal graph theory — disproves Erdős–Simonovits compactness AND an Erdős degeneracy conjecture

Measured structure: **111 Theorem, 239 Lemma, 84 Proposition, 30 Corollary**
references across ~682K characters. This is not a blog exhibit; it is a corpus.

**Not on arXiv** (checked: chapters 1, 3, 8 by title). So there is no LaTeX
source — extraction needs Mathpix PDF→LaTeX, for which we already have
infrastructure in `src/structured_math/books/`. That is a real added step, not a
blocker.

### 10.2 A version pair — and it does NOT show simplification

| | chars | Thm | Lem | Prop | Cor |
|---|---|---|---|---|---|
| original | 667,097 | 105 | 238 | 82 | 27 |
| updated (Aug 6) | 681,613 | 111 | 239 | 84 | 30 |

The revision **grew**. So the "humans later rewrote and simplified" hypothesis is
not supported by this pair — it reads as correction and expansion. Worth knowing
before building a study around the simplification story.

### 10.3 *How the Ideas Came Together* — process traces

<https://cdn.openai.com/pdf/reasoning-walkthroughs.pdf> — an AI model read the
**original chains of thought** plus the finished papers and reconstructed, per
problem, "which ideas first suggested a path forward, which substantial
approaches encountered **genuine obstacles**, what changes of perspective
revealed the underlying structure".

This is a category of data that **does not exist for human papers**: the
abandoned branches. A published human proof records the path that worked and
silently discards the rest. If the study wants to say something about *how* AI
mathematics differs, this is the richest available evidence and nobody has
touched it. It is prose, not a graph — but the dead ends are nameable, and a
"path attempted → obstacle → pivot" structure is extractable.

### 10.4 The arXiv population is larger and growing faster than §9 concluded

§9 said the artifacts are not papers. That was true **of the Erdős route** and
false in general. Searching abstracts for an AI system *plus* an attribution verb
("obtained by", "proved by", "discovered by") gives **30 arXiv papers, 2025–26**
— saved as `discovery_suite/ai_math/ai_proved_arxiv.csv`.

By month: 2026-07 **10**, 2026-05 **8**, 2026-06 3, 2026-08 3 (partial), earlier 6.
By area: **math.AG 11**, math.CO 3, math.NT 2, math.FA 2, cs.DS 2, others.

Two things follow. The population is **growing steeply** — most of it is the last
four months — so a count taken today understates what will exist at submission.
And it is **concentrated in algebraic geometry**, which is a specific,
checkable claim about where this is happening, not a guess.

### 10.5 The paired design is alive after all

`arXiv:2608.01040` — *The equality case of Ehrhart's volume conjecture*:

> "This resolves the equality case of Ehrhart's volume conjecture, as a
> counterpart of the inequality part **recently proved by OpenAI**. The main
> result of this paper is obtained by generative AI, particularly GPT-5.6-sol,
> Fable 5, and the Danus system."

So an ecosystem is forming: OpenAI publishes an AI proof, other groups publish
AI-assisted arXiv follow-ups on the same problem. That yields same-problem pairs
— the design §9 retired via the Erdős route — but sourced from *chapters of
ten-proofs* rather than from the Erdős database.

### 10.6 Revised recommendation

The study is **substantially more viable** than §9 concluded:

1. **`ten-proofs` is the treatment corpus.** Ten results, 464 theorem-like
   statements, uniform authorship, one PDF. Mathpix it and extract.
2. **Controls come from the classical literature on the same ten problems** —
   Cohn–Elkies, Kun–Thom, existing Ramsey bounds. Same problem, human proof.
   That is the matched design, and it is much better than "AI papers vs arbitrary
   arXiv".
3. **`ai_proved_arxiv.csv` (30 and growing) is the second arm**, with real LaTeX.
4. **The walkthroughs are the differentiator** — no human corpus has dead ends.

The §5 confounds still stand, especially 5.2 (the write-up is not the proof).
But 5.1, selection bias, is much weaker here: comparing an AI proof of Ehrhart
against the human literature on Ehrhart holds the problem fixed by construction.
