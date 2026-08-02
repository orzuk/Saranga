# Discovery Suite — Three Cross-Paper Tasks over the 100k Parsed Corpus

Consolidated home for the tools that operate on our parsed knowledge-graph corpus
(and later, all of arXiv) to attack three related problems:

| Task | Question it answers |
|------|--------------------|
| **T-PLAG** Plagiarism / reuse | Did paper B copy/paraphrase/restructure content from paper A (without credit)? |
| **T-ALIGN** Alignment | Which nodes/subgraphs of paper A correspond to which of paper B (same object, possibly different notation)? |
| **T-OPEN** Open-problem resolution | Was an open problem/conjecture stated in paper A actually solved by paper B, with *neither side aware*? |

All three are the **same core primitive** — *cross-paper semantic matching of typed
math nodes* — at three different granularities and with three different decision
rules on top. So we build **one shared matching engine** and three thin task heads.

```
                    ┌─────────────────────────────────────────┐
                    │  SHARED MATCHING ENGINE (shared/)         │
                    │  corpus_io · node embeddings · signature  │
                    │  ANN index · candidate generation · σ     │
                    └───────────────┬─────────────────────────┘
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
   T-PLAG head                 T-ALIGN head                T-OPEN head
   (directional reuse,         (bipartite graph            (problem→theorem,
    obfuscation-robust)         alignment + significance)   temporal + judge)
```

---

## 0. Inputs — what every tool consumes

Each paper is one JSON: `{ "metadata": {"paper_id", ...}, "nodes": [...], "edges": [...] }`.

- **node**: `id, type, name, statement, clean_text, raw_latex, tags, subclass,
  rigor, foundation_ids/origin, index`. 18 locked node types (definition, theorem,
  lemma, proposition, corollary, claim, conjecture, problem/open_problem, proof,
  remark, algorithm, example, equation, notation, assumption, conclusion, …).
- **edge**: `source, target, type, confidence`. 7 locked edge types
  (uses / proves / grounded_to / generalizes / specializes / depends_on / …).

Corpus layout: `portal/data/tier3/<category>/<year>/<arxivid>_rules.json` (~15.7k on
portal; the full 100k parse lives on the cluster). All loaders go through
`src/discovery/common/corpus_io.py` so we get category/year/paper_id for free —
**never re-glob raw paths** in task code.

**Design rule for every tool:** consume *nodes+edges*, not raw LaTeX. Raw text is a
fallback feature, not the primary signal. This is exactly what the old (graph-free)
plagiarism pipeline lacked, and where our structured corpus should win.

---

## 1. T-PLAG — Plagiarism / undisclosed reuse

Prior art (pre-project, text-only): `pan-plagiarism-corpus-2011` pipeline —
HDBSCAN abstract clustering → Bloom-filter 8-gram overlap → Siamese/raw BERT →
ranked human review. **Reuse the lessons, replace the substrate with our graphs.**
Directional: "B reuses A" (A older). Ascending complexity:

- **P1 — Lexical fingerprinting (cheap, O(N) index).**
  MinHash / Bloom of k-shingles over each node's `clean_text` (LaTeX + stopwords
  stripped, math normalized). LSH banding → candidate paper pairs sharing shingles.
  This is the Bloom-filter stage, but *per node* and math-aware. Catches verbatim &
  light paraphrase. Fast enough for the whole corpus.
- **P2 — Structural fingerprinting (cheap-medium).**
  Hash the *graph* not the prose: per-paper multiset of (edge-type, src-type,
  dst-type) triples + degree histogram → Weisfeiler-Lehman-style graph shingles.
  Two papers with the same theorem→proof→lemma skeleton but reworded prose score
  high here even when P1 misses them. Purely combinatorial, no model.
- **P3 — Embedding retrieval (medium).**
  Node embeddings (bge-large / SPECTER2 for scientific text) → ANN index (FAISS) →
  for each node in B, nearest nodes across corpus. Aggregate node-level hits into a
  paper-pair reuse score. This is where paraphrase/translation obfuscation is caught
  — the exact gap the old Siamese model struggled with (it collapsed to raw BERT).
- **P4 — Cross-encoder / LLM adjudication (expensive, candidates only).**
  Re-rank top candidate node pairs with a cross-encoder (or an LLM judge reusing
  `common/llm_judge.py`) that outputs {verbatim / paraphrase / conceptual-reuse /
  legitimate-citation / independent}. **Must ingest the citation graph** so
  legitimate quotation-with-citation is *not* flagged — the biggest FP source in the
  old report (the QBism example, the Farhi-Harrow example).
- **Directionality & self-plag filters** (shared across tiers): older-paper-is-source
  via year; same-author → tag as *self-reuse* not plagiarism (via S2 authors, not
  brittle name-string matching — a documented failure of the old pipeline).

## 2. T-ALIGN — Cross-paper node/subgraph alignment

Prior art (T2): `src/graph_alignment.py` (signature prefilter → Hungarian → structural
refinement → permutation significance) + `scripts/embedding_sigma.py`. **Already
strong; extend and scale.** Ascending complexity:

- **A1 — Signature prefilter (existing, cheap).** Foundation-term TF-IDF + type-compat
  to shortlist which paper pairs are even worth aligning. Keep as gate.
- **A2 — Bipartite node matching (existing, medium).** Hungarian assignment on a σ
  matrix (Jaccard *or* embedding σ) with the type-compatibility matrix. Output =
  node↔node correspondence + alignment score. Add permutation test (exists) for a
  p-value per pair.
- **A3 — Structure-aware alignment (medium-high).** Reward matches that also preserve
  edges (an aligned theorem↔theorem whose *proofs* and *used lemmas* also align).
  This is graph matching / QAP-lite; iterate σ with a neighborhood-agreement term
  (partly present in "iterative structural refinement" — formalize & benchmark it).
- **A4 — Learned graph matching (high, optional/aspirational).** GNN node encoder
  (message passing over the typed graph) trained with the planted-pairs eval as
  supervision; deep graph-matching (e.g. neural Sinkhorn) for notation-invariant
  correspondence. Only if A2/A3 plateau.

Alignment is also the **substrate the other two tasks call**: P3/P4 candidate node
pairs and T-OPEN problem→theorem pairs are all "align these two nodes" queries.

## 3. T-OPEN — Undiscovered open-problem resolutions

Prior art: `src/discovery/method_e/` — **already a full pipeline.** Frame as ascending
tiers so we can present the ladder even though the top rungs exist:

- **O1 — Typed retrieval (existing).** Index `open_problem`+`conjecture` nodes (queries)
  and `theorem/lemma/prop/corollary` nodes (candidates); signature retrieval with the
  empty-foundation rebalancing. Enforce temporal direction (candidate.year ≥ problem.year).
- **O2 — Filtered candidate generation (existing).** Dedup restated theorems (canonical =
  earliest), drop same-author, exclude self-resolved-within-2yr. These encode the
  "neither side aware" requirement.
- **O3 — Citation-novelty gate (existing).** Via S2 citation graph: down-weight pairs
  where B already cites A (they knew) — the headline is the *structural* match; citation
  is calibration.
- **O4 — LLM judge, two-tier (existing).** Sonnet triage → Opus confirmation: "does
  theorem B actually resolve open problem A?" with structured verdict + rationale.
- **Extension worth adding:** embedding retrieval (as in P3) as an *alternative* first
  stage to the foundation-signature — catches problems phrased with no shared foundation
  vocabulary. Cheap to bolt on since the ANN index is shared.

---

## 4. Evaluation — planted ground truth ("known-answer" injection)

The old report's central weakness: *"the absence of ground-truth plagiarism labels in
the arXiv corpus"* — they could only validate by eyeballing. We fix that by **planting
synthetic positives with known answers** and measuring recovery. One harness,
`eval_harness/`, generates labeled injections for all three tasks and scores each
method's ranked output.

### 4.1 T-PLAG planting
Take real papers; inject content from a *source* paper into a *target* at controlled
**obfuscation levels** (mirrors PAN's none/low/high):
- **L0 verbatim** — copy a node's statement/proof unchanged.
- **L1 light** — synonym/notation swap, reorder clauses (rule-based or small LLM).
- **L2 paraphrase** — LLM rewrite preserving meaning, new surface form.
- **L3 structural** — split/merge nodes, re-derive same result via reworded proof.
- **L4 conceptual** — restate the *idea* in a different subfield's vocabulary.
Metrics: pair-level & node-level **precision@k, recall, AP/AUC**, and a
**detection-vs-obfuscation curve** (recovery rate per level — the key figure; directly
generalizes Fig. 2/3 of the old report). Include hard negatives: same-topic
non-copied pairs, and legitimate cite-and-quote pairs (must *not* fire).

### 4.2 T-ALIGN planting
- **Notation-perturbation clones:** take one paper, mechanically rename symbols /
  reorder nodes / swap synonyms → a "translated" copy with a **known node↔node
  permutation** as gold. Score alignment accuracy (fraction of nodes matched to their
  true image) vs perturbation strength.
- **Composite papers:** stitch subgraphs from two papers; gold = provenance labels.
Metrics: matching accuracy, Hungarian-vs-gold agreement, and significance calibration
(planted-clone p-values ≪ random-pair p-values).

### 4.3 T-OPEN planting
Hardest to plant honestly. Two complementary strategies:
- **Split-a-known-resolution (retrospective gold):** find real cases where paper B
  provably resolved an earlier conjecture in A (from S2 "solves"/follow-up citations),
  then **hide the link** (remove citation, mask authors) and check the pipeline
  re-discovers it. This gives *real* positives with a defensible label.
- **Synthetic problem↔theorem twins:** author a fictional `open_problem` node in one
  planted paper and a `theorem` node in another that resolves it (LLM-generated,
  human-checked), embedded among distractors.
Metrics: recall of planted/known resolutions in top-k, judge precision, and
false-discovery rate on a distractor pool.

### 4.4 Handling *real* (unplanted) hits
Every method will surface non-planted candidates. Protocol: (1) auto-separate planted
vs novel by ID bookkeeping; (2) route novel high-confidence hits to a triage CSV
(reuse `method_e/export_triage.py` format) for human/Or review with rationale +
evidence snippets; (3) a confirmed novel case is a *finding*, not a metric contaminant —
log it separately. This turns the eval into a live discovery loop.

---

## 5. Build order (proposed)

1. **`shared/`** — thin wrappers over existing `common/`: corpus iterator, node-text
   builder (reuse `embedding_sigma.node_text_for_embedding`), FAISS index builder,
   math-aware shingler. *Everything else depends on this.*
2. **`eval_harness/`** — planting + scoring first, so every method is measurable from
   day one (the discipline the old pipeline lacked).
3. **T-PLAG P1→P2** (pure algorithmic, no GPU) — fastest to demo corpus-wide.
4. **T-ALIGN A1→A2** — wire existing `graph_alignment` to the shared index + eval.
5. **T-OPEN O1→O4** — mostly wiring existing `method_e` into the suite + eval + the
   embedding-retrieval extension.
6. Climb to P3/P4, A3/A4 guided by the detection-vs-obfuscation curves.

## 6. Open decisions for Or
- Embedding backbone: **bge-large** (already used) vs **SPECTER2/SciNCL** (sci-tuned) —
  benchmark both on planted T-ALIGN clones.
- Whether T-OPEN eval leans on retrospective real resolutions (defensible, scarce) vs
  synthetic twins (plentiful, less "real") — probably both, reported separately.
- Corpus scope for first full run: portal 15.7k vs full 100k on cluster.

---

## 7. Status snapshot & prioritized next steps (2026-07)

Where each task actually stands (code-grounded), then the ordered work list. Owner
tags: **[O]** Or, **[Y]** Yaron, **[O+Y]** joint.

### 7.1 Task status — done vs TODO

- **T-OPEN — runs end-to-end on the full 100k.** Sweep→triage→judge→citation-gate all
  exist as code (`open_problems/{sweep_open,triage_open,batch_o4}.py`, `--citations`).
  Last run: 15,143 problem statements × 1,589,327 theorem-like nodes → **300,204
  candidate pairs → 166 shortlist → judged (154 NO / 7 YES / 5 PARTIAL)**. Citation
  gate (S2) now run on the 12 yes/partial: the strong ones (Friedl–Tillmann,
  Christensen–Wang, inverse-Gowers, maximal-green-sequence) are all **cited → known
  resolutions**; **no confirmed undiscovered resolution yet** (expected at this depth).
  *Gap:* matching is **lexical** — only near-verbatim resolutions reach the shortlist;
  the judge only ever sees 166 (an Opus-cost cutoff, not a discovery boundary).
- **T-PLAG — sweep + gates run on 100k; judge not run at scale.** 384,115 candidate
  reuse pairs → 15,003 strong → self-reuse (S2 author) gate → 6,116 cross-author →
  IDF/promiscuity filter → **737-pair cross-author shortlist**. The LLM judge
  (`plagiarism/p4_judge.py`) is coded but **not yet run** over the 737; the math.NT
  standout (1109.0956→1304.6179, 223 shared statements) is unverified.
- **T-ALIGN — engine exists, not wired to suite/eval at scale.** `src/graph_alignment.py`
  (signature prefilter → Hungarian → structural refinement → permutation significance,
  `jaccard` **and** `embedding` σ). Needs the shared ANN index + planted eval.
- **Erdős probe — data ready, only a fixture run.** `open_problems/erdos_problems.csv`
  = **1217 problems** with `yaml_status` (**~609 open / ~556 resolved**, incl. Lean
  formalization variants). `erdos_coverage.py` maps each to its best corpus
  `open_problem`/`conjecture` node + T-OPEN resolving theorem — but has only run on a
  **10-row fixture over ~87 local papers**. No solved-by-**human** vs solved-by-**AI**
  label exists (that is *not* derivable from `yaml_status` and must be curated).
- **Eval harness (planted ground truth, §4) — NOT built.** All three tasks still lack
  ground-truth labels, so hits can only be eyeballed. This is the largest missing
  methodological piece.

### 7.2 In-suite next steps (ordered)

1. **[O+Y] Build the planted-ground-truth eval harness (§4).** Turns discovery from
   anecdotes into precision/recall + detection-vs-obfuscation curves — the TMLR-grade
   result. Everything below is more credible once this exists.
2. **[Y] Semantic (BERT-class) retrieval at the *generation* stage of T-OPEN/T-PLAG.**
   The blind spot is recall at candidate generation, not the judge — a paraphrased
   resolution never enters the 166. Bi-encoder embeddings (**Qwen3-Embedding**, already
   on the cluster, or `bge-m3`) + ANN index for recall; **cross-encoder reranker**
   (`bge-reranker`/`Qwen3-Reranker`) for precision. Decisions: canonicalized vs raw
   text (ablate + optionally score-fuse, don't vector-concat); context from the **typed
   graph** (embed a node with its linked `definition`/`assumption` neighbors via late
   chunking), not arbitrary preceding prose. Watch the runtime blow-up — that's the
   real engineering constraint.
   **BUILT for T-OPEN (see `open_problems/SEMANTIC_RETRIEVAL.md`).** Shared engine in
   `discovery_suite/embed/` (textstore → encode → index → fuse), T-OPEN head in
   `open_problems/{o1b_dense_sweep,o1c_fuse,o5_rerank,bench_retrieval,watch_open}.py`
   plus sbatch scripts. Purely additive — `sweep_open.py` is untouched and is now the
   lexical arm; dense output keeps sweep_open's nine leading CSV columns so triage →
   `batch_o4.py` → citation gate all run unchanged. Six embedders, four views
   (`node` / `ctx-concat` / `ctx-late` / `concepts-only`; ctx-late is free — it mixes
   cached node vectors, so α is swept without re-encoding), raw vs canonical vs
   score-fused, RRF/z-norm fusion, cross-encoder rerank. Runtime is *not* the blow-up
   feared: a bi-encoder is O(N), so 100k scoring is a ~2.4e13-FLOP GEMM (<1 GPU-min vs
   57 CPU-min lexical); only the reranker is per-pair and it sees ~1e-5 of the pairs.
   Whole champion config ≈ 3 GPU-hours, no API spend. Verified locally: backend
   exactness, bitwise-reproducible encoding, filter correctness, triage contract.
   **Still to run:** the GPU model roster, and the obfuscation curve with `--llm`
   (without it the rule-based L2–L4 fallback isn't paraphrase, so the lexical baseline
   looks perfect at every level — a harness property, not a result).
3. **[Y] Scale past the top-166 with a local free judge.** Host Qwen/Kimi on the
   cluster (`scripts/launch_qwen_judge_server.sh` exists) as a cheap first-pass judge
   over thousands of (BERT-surfaced) candidates → Opus only adjudicates survivors.
   Validate the open judge against Opus on the current 166 *before* trusting it at 10k.
4. **[Y] Run the T-PLAG LLM judge over the 737-pair shortlist** and verify the NT standout.
5. **[O] Erdős at 100k scale + persist edges.** Copy the 1217-CSV to the cluster, run
   `erdos_coverage.py` over the parsed 100k (retune `--threshold` on the real score
   histogram), and **write `resolves`/`erdos_ref` edges back into the graph** (linkage
   currently lives only in an output CSV). Target classification = **open /
   solved-in-corpus / solved-elsewhere**, with a small **curated** AI-solved subset,
   and the "found-in-literature vs genuinely-new" split (the citation-gate logic)
   applied to that subset only.
6. **[O] Feed Mathlib *structure* to the matcher.** Grounding is currently pure
   string-match against a flat name index; the `uses`/`proves` edges already extracted
   into `mathlib4_midlevel.json` are discarded, and `extends` inheritance is never
   parsed. Ingest `extends` → concept→concept `specializes` edges, load the dependency
   edges, and let relevance **propagate over the concept DAG** so grounding recall and
   the cross-paper "related-concept" signal both improve. (The CLAUDE.md
   concept-inheritance DAG is still aspirational — this makes it real.)

### 7.3 Cross-cutting (outside the suite, but blocking the paper)

Tracked here for visibility; detailed plans live with each subsystem.

- **[O+Y] Proper silver train/test at scale (TMLR-critical).** Re-extract 200–300+
  papers with **Opus-5** (uniform model/prompt) into `corpus/silver/` (already
  organized by model/prompt with a `split` column), then a **random train/test split /
  k-fold** — replacing the current 17-paper **in-sample** setup. Freeze the schema first.
- **[Y] Held-out distillation eval.** Current numbers (`merged_eval_silver_001_011_v3`):
  base F1 **0.711 → 0.735** (distillation) **→ 0.810** (LLM-judge) are **in-sample on 17
  papers**. Report on the held-out set, and **separate the two effects** — regex
  distillation alone is only **+0.024** (and lowers precision); most of the headline
  lift is the LLM-judge FP-correction, a different mechanism. The 60-paper test set is
  already in `corpus/silver/` (`split=test`), so this can start now.
- **[O] Portal graph re-render + repo reconciliation.** Graphs are **pre-baked
  matplotlib SVG-in-HTML** committed under `portal/graphs/` and served statically by the
  Space — *not* rendered on the fly. The recurring "text out of the box" bug lives in
  `src/visualize_annotation.py` (fixed `fontsize=12` vs `CHARS_PER_UNIT`/`_display_width`
  width estimate); a fix only shows after re-running `scripts/render_tier2_graphs.sh`
  (+ tier-1) **and re-committing** to the Space. Reconcile the git-repo portal vs the HF
  Space repo (they appear to have diverged). Durable fix: move to **client-side
  rendering** (revive the vendored cytoscape, draw from JSON) to kill the stale-HTML
  bug class.

### 7.4 Held-out distillation with α-tuning — algorithm spec (to implement, not yet built)

Replaces the in-sample 17-paper number with a **held-out** result and tunes the FDR
prune threshold **α** (`prune_alpha`/`max_fdr`) properly — on **one API budget**.

**Key idea.** The LLM cost is in rule *generation* (`analyze`/`aggregate`); **α only
affects *pruning*, which is free CPU compute.** So generate the candidate pool **once,
unpruned (α = 1)**, cache each rule's stats, then sweep α **post-hoc**. Never run
generation once per α.

**Data.** `corpus/silver/metadata.csv` `split` → train / val / test (on this small a
corpus, prefer **k-fold CV over train to pick α** and keep one untouched test set).
Silver-gold node sets come from the JSONs; matching uses greedy Jaccard ≥ 0.7 (as today).

**Phase 1 — Generate the candidate pool (once, on train, α = 1).**
- **Dark-knowledge is defined against a *fixed baseline*** (the original manual rules,
  never updated mid-run) so the pool is α-independent. Dark-knowledge = gold items
  the baseline **misses (FN)** and **≥1 LLM extraction catches (TP)**.
- Maintain a growing **unpruned** pool `P` of candidate rules. Per train paper, in order:
  - candidates-needed = dark-knowledge items **not already covered by any rule in `P`**
    (coverage dedup is against the *unpruned* pool → no redundant regeneration);
  - `analyze`: batch those items → LLM proposes *generalizing* rules;
  - `aggregate`/validate: merge into `P` (dedup + codegen/backtracking guards).
- **No FDR pruning in this phase.** (Dedup by coverage, not by pruning.)

**Phase 2 — Cache per-rule stats (deterministic, no LLM).**
Run every rule in `P` over all train papers; attribute spans to gold by greedy Jaccard
→ per-rule `(TP, FP)` → `FDR`. Store per-paper hits so subset re-scoring is cheap.

**Phase 3 — α-sweep (free).**
For α on a grid (e.g. 0.0–0.5): `R(α) = {rules in P with FDR ≤ α}` (a **nested** family —
raising α only *adds* rules). **Re-score `R(α)`** by re-running the parse with that
subset (this correctly handles rule interaction, unlike a pure per-rule filter) →
validation F1 (or CV-F1). Pick `α* = argmax` val/CV F1. Emit the **F1-vs-α curve** (a
paper figure / ablation).

**Phase 4 — Optional targeted regeneration at α\* (pay once, not per α).**
regression-set = gold items covered somewhere in `P` but **not** by `R(α*)` (lost purely
to trimming). Run **one** `analyze` pass on just those items → new (aimed-to-be-precise)
candidates → keep those with train-FDR ≤ α* → add to `R(α*)`. Skip in v1 unless the
sweep shows meaningful recall lost at α*.

**Phase 5 — Report once, on TEST.**
Freeze `R(α*)` (+ optional top-up). On the held-out test set report **three stages
separately**, per node type, with CIs: **base** (manual rules only) vs **distilled**
`R(α*)` vs **+LLM-judge** (FP-correction). Do *not* conflate them — regex distillation
and the judge are different mechanisms.

**Cost.** One generation pass over train (~$1/paper, Anthropic API, runs locally — no
GPU/cluster) + one optional top-up. The α-sweep and all F1 evaluation are free (Jaccard,
no LLM); only the optional FP-judge stage adds calls. Entry point to build:
`scripts/eval_distill_heldout.py`, wrapping `distillation_analysis.py` +
`silver_distillation_merged.py`, reading the `split` column.

### 7.4.1 Status: IMPLEMENTED — `scripts/eval_distill_heldout.py`

Phases 1, 2, 3 and 5 of 7.4 are built. Phase 4 (targeted regeneration at alpha*)
is deliberately deferred per the spec's "skip in v1".

**It is a wrapper — nothing under `src/LLMVersion/` was modified.** Generation is
`run_sequential`, pruning is `prune_rules`, scoring is `evaluate_single_paper`.

Mechanics worth knowing:

- **Pool built at `alpha=1.0`, then snapshotted** to `distilled_rules.POOL.py`.
  `prune_rules` *mutates* `distilled_rules.py` in place (commenting rules out
  with `# PRUNED`), so every alpha in the sweep restores from the snapshot
  first. Without that, each alpha would prune the previous alpha's output.
- **`--skip-generation` makes the whole run zero-API-call**, so alpha can be
  re-tuned or results re-reported for free.
- **`--flat-tex`** stages `portal/data/tier2_tex/<pid>.tex` (and the new
  `corpus/silver/tex_pool/<arxiv_id>.tex`) into the `<pid>/source/` layout the
  pipeline expects, instead of patching the loader.
- CV defaults to **pool-once** (per the spec's one-API-budget constraint), which
  leaks val papers into generation and makes **CV F1 optimistic — it selects
  alpha, it does not get reported**. The headline number comes from the untouched
  test set. `--strict-cv` regenerates per fold (k x cost, no leakage).

**BLOCKER for Yaron — FP-to-rule attribution can silently no-op the sweep.**
Validated end-to-end with a synthetic pool: pruning removed **0 rules at every
alpha**, every FP landing in `<unattributed>`, giving an identical F1 at all
alphas and an arbitrary "alpha*". Two failure modes in
`distillation_analysis.prune_rules`:

1. The fast path requires `all(r.get('rule_name') ...)` over FP results — a
   **single** result dict missing `rule_name` drops the entire run to the slow
   path.
2. The slow path only collects patterns whose variable name **starts with `_`**
   (`name.startswith('_')`), but the codegen prompt tells the LLM to name rules
   like `P1_TEXTIT_IS` / `ENV_NOTATION`. So it can match nothing and attribute
   every FP to `<unattributed>` — pruning becomes a no-op **with no error**.

Real generated rules do emit `rule_name`, so the fast path normally holds and
the sweep works; the risk is a partial/missing `rule_name` degrading silently to
a broken fallback. `eval_distill_heldout.py` now **detects this and refuses to
present alpha\* as tuned** (`cv_degenerate` in the report), but the underlying
attribution should be fixed in `prune_rules` — Yaron's call, since that file is
his.

### 7.5 Report results PER MATH SUBFIELD, not pooled (paper framing)

**Motivation (Or, 2026-07-30).** Public discussion of "AI doing math" treats
mathematics as one monolith. It isn't: it is many subfields with different
cultures, and AI's impact plausibly differs across them. (Framing prompted by
@johnennis: many AI proofs amount to importing a known result from another
subfield, which is legitimate but leaves the "native" proof — and the questions
it would unlock — still open.) Our sampling design makes the per-subfield cut
free, so pooling would discard our most structural finding.

**We already measure a large subfield effect.** Formal-environment density
(does the field use `\begin{theorem}` at all?), 5 papers/category over the
staged 100:

| category | envs/paper | zero-env papers |
|---|---|---|
| math_ph | 5.0 | 3/5 |
| math_OC | 8.8 | 1/5 |
| cs_LG | 14.8 | 2/5 |
| math_CO | 19.8 | 1/5 |
| math_NT | 36.2 | 0/5 |
| math_RT | 45.2 | 0/5 |
| **math_AT** | **150.2** | 0/5 |

A ~30x spread. It propagates into extraction: v5.1 mean *node confidence* was
0.765 for a prose-only math_OC paper vs 0.965 for a formally-structured math_CA
paper — i.e. **the subfield determines how much of the extraction is judgment
rather than mechanical transcription.**

**What to do in the paper.**
1. **Per-category tables as first-class results**, not an appendix: rules-vs-silver
   F1, node/edge density, orphan rate, and the new node/edge `confidence`
   distributions — all broken out by the 20 `CORPUS_CATEGORIES`.
2. **Report formal-environment density as the explanatory variable.** It is the
   mechanism behind per-category differences in extractability, and it predicts
   where a regex extractor is structurally blind (11% of papers have zero
   environments, 17% fewer than five).
3. **T-OPEN: report cross-category vs within-category resolution rates
   separately.** This is the most direct engagement with the "cross-subfield
   transfer" thesis — and note that the 100k sweep's 5 candidates all came from
   cross-category pairs (the filter Yaron now wants to relax, which would let us
   quantify the contrast).
4. **Use `confidence` per category** to separate "the extractor struggled" from
   "this field writes less formally" — previously indistinguishable.

**Caveats to state explicitly (do not overclaim).**
- We measure **documentation culture** (LaTeX conventions), which is a *proxy*
  for mathematical culture, not the same thing. A field with few
  `\begin{theorem}` blocks is not less rigorous — math_ph and math_OC papers are
  rigorous but written differently. Say this plainly.
- 50 papers/category supports per-category point estimates with **wide CIs**;
  it does not support confident pairwise category rankings. Report intervals.
- Category labels are the arXiv primary category, which is author-chosen and
  noisy (many papers are genuinely cross-listed).

### 7.5.1 Category provenance — measured, and it changes the analysis design

`extraction_targets_opus5.csv` records the category each paper was **sampled
from**, not its arXiv primary listing. arXiv returns cross-listed papers for a
category query, so the two differ. Measured against the arXiv API for all 100
extracted papers (`corpus/silver/true_categories.csv`,
`scripts/fetch_true_categories.py`):

- **30/100** have a primary category genuinely different from the sampled one.
- A further **8/100** differ only notationally or by arXiv alias
  (`math.ST`≡`stat.TH`, `cs.IT`≡`math.IT`, `cs.SY`≡`eess.SY`, `math-ph` spelling).
  These are NOT misfiled; an earlier count of "38" conflated them.

**This does not mean the sampling is wrong — it means the two labels answer
different questions**, and the choice of axis matters:

| axis | property | problem |
|---|---|---|
| `sampled_from` | **designed, balanced** — exactly 5 papers per category x 20 | a paper may be primarily elsewhere |
| `primary_category` | authoritative single label | **unbalanced**, long tail of singletons (q-bio.NC, gr-qc, cond-mat.stat-mech, cs.CL, math.KT, math.CT ... each n=1) |

Re-bucketing by primary would scatter the 100 papers across ~35 categories with
many n=1 cells — useless for per-subfield comparison, which needs cell counts
large enough to say anything.

**Recommendation for the paper:** report per-subfield results along
`sampled_from` (the balanced design; cross-listing means the authors *did* file
the paper under that category), and use `primary_category` as a robustness check
on any subfield claim that looks large.

**The 30% cross-list rate is itself a finding worth reporting.** It is direct
evidence that mathematical subfields are porous rather than cleanly partitioned
— relevant to the "math is many subfields with different cultures" framing in
7.5. Notable flows: math_LO -> cs.LO (2), math_AG -> math.AC (2), cs_CC ->
quant-ph/math.OC, math_DG -> hep-th/gr-qc, math_CO & math_GR & math_NA ->
math.DS (3).
