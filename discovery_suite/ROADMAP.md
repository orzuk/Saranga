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
