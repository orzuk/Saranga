# Rigor Classification and NeurIPS Scope

## NeurIPS 2026 paper: 10 target arXiv categories

| Category | Field | Rigor level | In NeurIPS scope? |
|----------|-------|-------------|-------------------|
| math.CO | Combinatorics | **formal** | ✓ YES |
| math.PR | Probability | **formal** | ✓ YES |
| math.AG | Algebraic Geometry | **formal** | ✓ YES |
| math.NT | Number Theory | **formal** | ✓ YES |
| math.LO | Logic | **formal** | ✓ YES |
| math.GR | Group Theory | **formal** | ✓ YES |
| cs.DS | Data Structures & Algorithms | **formal** | ✓ YES |
| cs.CC | Computational Complexity | **formal** | ✓ YES |
| math.OC | Optimization & Control | **mostly formal** | ✓ YES |
| stat.ML | Machine Learning (statistics) | **mixed** | ⚠ PARTIAL — only papers with rigorous content |

**For NeurIPS 2026:** report results on all 10 categories, but note that
stat.ML results are mixed-rigor. The DAG acyclicity metric and extraction
quality evaluation are most meaningful on the 9 formal categories.

## Book catalog: rigor classification

| Rigor | Books | Examples |
|-------|-------|---------|
| **formal** | ~60 | Axler (linear algebra), Hatcher (algebraic topology), Arora-Barak (complexity), Judson (algebra) |
| **semi_formal** | ~30 | Boyd CVX, Hastie ESL, Bishop PRML, Wasserman AoS |
| **mixed** | ~20 | Goodfellow DL, d2l.ai, BHK (mix of formal + applied) |
| **heuristic** | ~15 | Tong physics notes, Feynman lectures |

For the NeurIPS paper foundation graph: use **formal + semi_formal** books.
Flag heuristic content separately.

## Paper pairs catalog: rigor classification

| Rigor | Pairs | Examples |
|-------|-------|---------|
| **formal** | ~40 | CT/Donoho (compressed sensing), Nesterov/FISTA, JL lemma |
| **semi_formal** | ~25 | VAE/DLGM, PPO/TRPO, Adam/AdamW |
| **mixed** | ~20 | BatchNorm/LayerNorm, SimCLR/MoCo |
| **heuristic** | ~10 | Physics pairs (if any) |

For the NeurIPS alignment benchmark: report mainly on **formal** pairs.
Include semi_formal pairs with a note. Exclude heuristic pairs from
main results (mention in appendix if extracted).

## Future work: non-rigorous fields

After NeurIPS, extend extraction to:
- Theoretical physics (hep-th, cond-mat): flag rigor="heuristic"
- Mathematical biology (q-bio): flag rigor="mixed"
- Signal processing (eess.SP): flag rigor="semi_formal"

The schema supports these via the `rigor` field — no schema changes needed,
just extraction prompt domain-guidance sections.
