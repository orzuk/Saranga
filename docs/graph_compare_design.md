# Graph-Compare: Three Tasks, One Library

> **Status**: 2026-04-25 design doc, pre-refactor state.
> **Scope**: shared architecture for three paper-graph comparison tasks.
> **Deferred**: full restructure (post-NeurIPS).
> **Owner**: Or Zuk; reviewer: Yaron Otmazgin.

## 1. Three tasks, one underlying problem

We have three independent use cases that all reduce to "compare two paper-graph JSONs."

### T1 — Ground-truth vs prediction (extraction evaluation)

**Input**: hand-annotated `gold.json` + LLM-extracted `predicted.json`, **same paper**.
**Goal**: grade the prediction. How many gold nodes did the model find? How many of its predictions are correct?
**Asymmetry**: gold is authoritative. Precision uses |pred| denominator; recall uses |gold|.
**Match strictness**: medium — fuzzy paraphrase OK ("RIP" ≡ "Restricted Isometry Property"), genuinely-different objects must not match.
**Statistics**: bootstrap CI on F1; per-node-type breakdown.
**Today**: partial (`src/evaluate_extraction.py` does some of this but isn't unified with the new infra).

### T2 — Multi-LLM consensus (silver-gold)

**Input**: 2+ LLM JSONs, **same paper** (e.g., Opus + Qwen + Gemini).
**Goal**: which nodes/edges do *all* models agree on? Build a high-confidence silver-gold subset.
**Symmetry**: all models are peers, no ground truth.
**Match strictness**: strict — only count clear agreement; conservative on borderline matches.
**Statistics**: pairwise agreement matrix; N-way intersection size; Cohen's κ (2 models) or Fleiss' κ (N ≥ 3).
**Today**: implemented in `scripts/silver_gold/consensus_intersect.py` (this file).

### T3 — Cross-paper alignment

**Input**: JSONs of two **different** papers (e.g., Candès–Tao vs Donoho).
**Goal**: which mathematical objects across papers are analogous? Build a bipartite matching.
**Symmetry**: A and B are peers.
**Match strictness**: permissive — different surface forms can correspond (Gel'fand widths ↔ RIP).
**Algorithm**: Hungarian on cost matrix + structural QAP iterations.
**Statistics**: permutation null Z-score over node-label shuffles.
**Today**: implemented in `src/graph_alignment.py` + `scripts/run_alignment_benchmark.py`.

## 2. Side-by-side comparison

|  | T1 Eval | T2 Consensus | T3 Alignment |
|---|---|---|---|
| Same paper or different? | same | same | different |
| Symmetric? | no | yes | yes |
| Strictness | medium | strict | permissive |
| Match algo | greedy w/ σ threshold | greedy w/ σ threshold | Hungarian + QAP |
| Edge handling | post-hoc check | post-hoc check | structural bonus drives matching |
| Statistics | bootstrap CI on F1 | κ + N-way ∩ size | permutation null Z |
| Output unit | (P, R, F1) per type | consensus JSON + agreement matrix | matching M + Z scores |

**Reading this table**: T1 and T2 are *the same matching problem with different reporting*. T3 is a genuinely different matching problem.

## 3. Layered architecture (target)

```
┌─ Layer 4: Reporting (per-task)
│   precision_recall_f1(...)        ← T1 only
│   pairwise_agreement(...)          ← T2 only
│   n_way_consensus(...)             ← T2 only
│   significance_test(...)           ← T3 only (already exists)
│
├─ Layer 3: Matching algorithms (TWO, not three)
│   match_same_paper(...)            ← T1 + T2 share this
│   match_hungarian(...)             ← T3 only (= today's align_graphs)
│
├─ Layer 2: Pluggable σ functions
│   jaccard_sim, jaccard_combined,
│   jaccard_proof, embedding_sim,
│   SIGMA_FUNCTIONS registry         ← already exists
│
└─ Layer 1: Primitives
    tokenize, node_text, node_proof_text,
    _raw_jaccard, type_compat,
    edge_key                          ← already exists in graph_alignment.py
```

## 4. Target file layout

```
src/
├── graph_compare.py                  # renamed from graph_alignment.py
│   ├─ Layer 1 primitives             (already there)
│   ├─ Layer 2 σ registry             (already there)
│   ├─ Layer 3a match_same_paper      (NEW — lifted from consensus_intersect.py)
│   ├─ Layer 3b match_hungarian       (rename of align_graphs)
│   ├─ Layer 4 significance_test      (already there)
│   ├─ Layer 4 precision_recall_f1    (NEW — small)
│   └─ Layer 4 pairwise_agreement     (NEW — small)
│
└── graph_compare_eval.py             # renamed from graph_alignment_eval.py
    └─ gold-alignment parsing         (mostly today's content)

scripts/
├── silver_gold/
│   ├── run_extraction.py             # exists — multi-provider runner
│   ├── consensus_intersect.py        # T2 driver — thin
│   └── eval_against_gold.py          # NEW — T1 driver, thin
│
└── run_alignment_benchmark.py        # T3 driver — exists, retarget imports
```

## 5. Current state vs target

| Component | Status |
|---|---|
| Layer 1 primitives | ✅ in `src/graph_alignment.py` |
| Layer 2 σ registry | ✅ in `src/graph_alignment.py` |
| Layer 3a `match_same_paper` | ⚠️ in `consensus_intersect.py` only; not shared |
| Layer 3b `match_hungarian` | ✅ as `align_graphs` in `src/graph_alignment.py` |
| Layer 4 T1 reporting | ⚠️ partial in `src/evaluate_extraction.py`, separate machinery |
| Layer 4 T2 reporting | ✅ in `consensus_intersect.py` |
| Layer 4 T3 reporting | ✅ as `significance_test` in `src/graph_alignment.py` |
| T1 driver | ❌ doesn't exist with new infra |
| T2 driver | ✅ `consensus_intersect.py` |
| T3 driver | ✅ `run_alignment_benchmark.py` |

Net: ~80% there. Two real gaps: (i) `match_same_paper` is private to T2 driver, (ii) T1 driver missing.

## 6. Migration plan (phased)

### Phase 1 (NOW, ~30 min) — minimal refactor

- `consensus_intersect.py` imports primitives from `src/graph_alignment.py` instead of re-implementing
- Drop ~25 lines of duplicated code (`tokens`, `jaccard`, `node_text`, `normalize`)
- Keep `match_nodes` (greedy two-pass) local for now
- No behavior change; just deduplication
- Single small commit

**This is being done as part of this design doc.**

### Phase 2 (post-Qwen-validation, ~30 min) — lift Algorithm A

- Move `match_same_paper` (currently `match_nodes` in consensus_intersect.py) into `src/graph_alignment.py`
- Add small docstring noting "use this for T1 + T2; use `align_graphs` for T3"
- Update `consensus_intersect.py` to import it
- Single commit. Still no behavior change.

### Phase 3 (post-Qwen-scale-up, ~half day) — confidence + κ

- Add per-match `match_type` and `sigma_score` to consensus output (per-node confidence tag)
- Add Cohen's κ / Fleiss' κ to consensus reporting (per-paper confidence tag)
- Useful for the paper headline.

### Phase 4 (post-NeurIPS, ~1 day) — rename + T1 driver

- Rename `graph_alignment.py` → `graph_compare.py`; same for `_eval.py`
- Add `precision_recall_f1` and `pairwise_agreement` to the library
- Write `scripts/silver_gold/eval_against_gold.py` as T1 driver
- Update `evaluate_extraction.py` to delegate to library, or deprecate
- Update `run_alignment_benchmark.py` imports
- Bigger commit but mechanical.

### Phase 5 (later, optional) — N-way matching

- Today's matching primitives are pairwise. For 3+ models, consensus_intersect.py loops pairwise.
- Could add a true N-way matcher that aligns all N inputs simultaneously (more expensive, slightly more accurate on edge cases).
- Probably not worth it.

## 7. Open design questions

### 7a. Should T1 share match algorithm with T2?

Yes — both are "same paper, find matching nodes." Difference is in the reporting (P/R/F1 vs agreement matrix). Same `match_same_paper` works for both, called with possibly different threshold.

### 7b. Should the matching primitive be symmetric or asymmetric?

`match_same_paper(A, B)` should return `List[(i, j)]` where i ∈ A, j ∈ B. Same regardless of which is "gold" and which is "pred." T1 reporting then computes P (match/|B|) and R (match/|A|) by convention (gold = A). T2 reports both directions.

### 7c. Conservative match — what threshold?

For T2 silver-gold, want **high precision**: false agreements pollute the consensus set. Recommended:
- Pass 1: exact (type, normalized-name) match — tag confidence "exact"
- Pass 2: σ ≥ 0.7 — tag confidence "fuzzy"
- Below 0.7: no match — tag as disagreement

For T1, lower threshold (0.5) is reasonable since fuzzy paraphrase matches are still credit.

### 7d. What about per-node-type matching for T1?

T1 reports per-type F1 (definition F1, theorem F1, …). Current `match_same_paper` matches across types. After matching, you can split by type for reporting. No algorithm change needed.

### 7e. Should T2 N-way be the union or the intersection?

Could be either, with a parameter. Current `consensus_intersect.py` does pairwise; for N=3, "all 3 agree" is intersection of pairwise; "2 of 3 agree" is union of pairwise. Both useful. Add `--threshold-k` flag in Phase 3.

### 7f. Schema-conversion utilities

T1 evaluation requires that the predicted JSON conforms to the same schema as the gold. Today, multiple variants exist (Opus's holistic schema, Yaron's per-type pipeline schema). A schema normalizer (`graph_compare.normalize_schema(j)`) would help — converts any flavor into the canonical `{metadata, nodes, edges}` form. Out of scope for Phase 1-4.

## 8. Non-goals

- **Don't** unify `match_same_paper` and `match_hungarian` into one function. They have fundamentally different correctness criteria. Sharing would harm both.
- **Don't** require a single matching output format that handles all three tasks' downstream needs. Each driver knows what it wants from a `List[(i, j)]`; let them format.
- **Don't** refactor `evaluate_extraction.py` until Phase 4. It works today; touching it is risk for limited benefit.

## 9. Notes for Yaron

- Phase 1 (the minimal refactor below) keeps `graph_alignment.py` unchanged — just imports from it. Your code path is untouched.
- Phase 2+ would rename `graph_alignment.py` → `graph_compare.py`. Heads-up but not yet.
- The collaboration boundary still applies: this work lives in `scripts/silver_gold/` (Or area) and imports from `src/` (also Or area, but you may extend `src/graph_alignment.py` freely; coordinate). Nothing in `src/LLMVersion/`.
