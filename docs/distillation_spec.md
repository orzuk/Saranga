# NtRED distillation — where the spec lives

**The specification is the paper, not this repo.**
Appendix *Knowledge Distillation Details* in `saranga_common.tex`, paper repo
(Overleaf project `69334d3ec1463188f54b0393`). No LaTeX lives here; a copy in
this repo would drift from the paper and has done exactly that before.

This file exists so the pointer is findable from the code side. It is a summary
of the contract, not a second source of truth — on any disagreement the paper wins.

## What the implementation is expected to do

| # | Component | Contract |
|---|---|---|
| 1 | **Alignment** | Group alignment, not one-to-one: unambiguous pairs first, then splits (n outputs vs 1 reference), then merges. Guards `m_tok = 5` shared tokens and `m_J = 0.10`, `k_max = 12`, `θ = 0.7`. The guards are load-bearing — unguarded pooling reads precision 0.93 against 0.75 guarded. |
| 2 | **Type compatibility** | Similarity is `containment × κ(τ, τ')`. κ is `TYPE_COMPAT` in `src/node_similarity.py` — the one table, shared with cross-paper alignment. Not a same-type gate, and not type-blind. |
| 3 | **Counting** | Over *structures covered*, not pairs — one accepted group can credit three outputs against two references. Pooled across papers, never macro-averaged. |
| 4 | **Dark knowledge** | Unmatched references under (1). This is why (1) matters: the alignment defines the **training target**, not just the score. A reference recovered as two structures must not enter DK. |
| 5 | **Selection** | `argmax_Θ F1(Θ; D_val) − λ|Θ|`, by backward greedy elimination over cached per-paper counts. **Not** a per-rule FDR bound — that optimises precision in isolation and is blind to a rule that is the only cover for a class of statements. The `λ|Θ|` term is required, not cosmetic. Report the λ-frontier. |
| 6 | **Registry** | Rules persist in a registry with immutable ids and `active`/`retired` status; the emitted `distilled_rules.py` is a *projection* of the active subset. Never delete, only deactivate. Makes selection reversible, the λ-sweep a dict scan, and lets a retired rule be recycled instead of re-invented. |
| 7 | **Attribution** | Earliest-firing rule takes credit, so per-rule counts sum to the paper totals. |
| 8 | **Integrate** | Add-only. The aggregate step extends the current rule file; it must not rewrite existing rules, or identifiers and their statistics reset. |

## Status (2026-08-21)

Shipped in `scripts/silver_distillation_merged.py`: (3), (8), and pooled scoring.
Not yet shipped: (1), (2), (5), (6), (7). The shipped gate is still per-rule FDR
at `α`, and the shipped match relaxation is `match_modes.py` M1/M3 — a coverage
test that addresses the same *symptom* as (1) (granularity) by a different
mechanism, and is not a substitute for it.

Reported numbers predate this spec; the paper says so explicitly.

## Ablations the paper commits to

Group alignment (revert to one-to-one), κ → identity, recycling, `λ = 0`, and
add-only. Only the alignment ablation moves the training target rather than the
score — run that one first.
