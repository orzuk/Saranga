# Embedding-Based Node Similarity for Cross-Paper Alignment

## What This Is

An embedding-based similarity function (`sigma`) that replaces the Jaccard baseline for cross-paper mathematical knowledge-graph alignment. Instead of comparing token-set overlap (Jaccard), it embeds each node's textual content using a sentence-transformer model and computes cosine similarity. This captures **semantic** similarity — nodes that describe the same concept in different notation/vocabulary will score high even with zero word overlap.

## Files Created

### `scripts/embedding_sigma.py`
The core sigma module. Drop-in replacement for `graph_alignment.jaccard_sim`.

**Key function:** `sigma(node_a, node_b) -> float`
- Extracts text from node fields (name, statement, assumptions, conclusions, proof_strategy)
- Prefers canonicalized fields (`*_canonical_local`) when present, falls back to raw fields
- Embeds text using a sentence-transformer model (default: `BAAI/bge-large-en-v1.5`)
- Returns cosine similarity * type_compat (same weighting scheme as the Jaccard baseline)
- Embeddings are cached via `lru_cache` for efficiency during the permutation test

**Also provides:**
- `sigma_no_type(a, b)` — raw cosine similarity without type compatibility (for ablation)
- `embed_node(node)` — get the raw embedding vector for a node
- `precompute_paper_embeddings(paper_json)` — batch compute all embeddings for a paper
- CLI smoke test: `python scripts/embedding_sigma.py paper_a.json paper_b.json --top-k 10`

**Configuration:**
- Set `EMBEDDING_MODEL` env var to switch models (e.g., `BAAI/bge-m3` if torch >= 2.6)
- Default model: `BAAI/bge-large-en-v1.5` (1024-dim, works with torch >= 2.2)

### `scripts/viz_alignment_heatmaps.py`
Side-by-side heatmap and scatter visualization comparing Jaccard vs Embedding sigma.

**Produces per positive pair:**
1. **Heatmap PNG** — two heatmaps (Jaccard left, Embedding right) with gold alignment pairs outlined in red. Cell values shown when matrix is small enough (<=20 nodes per side). Nodes sorted by type then ID.
2. **Scatter PNG** — two panels: (a) box plot of sigma values for gold-matched vs non-matched pairs, both methods; (b) Jaccard-sigma vs Embedding-sigma scatter, gold pairs marked as red stars.

**Usage modes:**
- **Single pair:** `--paper-a`, `--paper-b`, `--alignment`, `--pair-name`
- **Batch mode:** `--config benchmark_config.json` (runs all positive pairs)

## Results on VAE vs DLGM Test Pair

Tested locally on the VAE (Kingma & Welling, 1312.6114) vs DLGM (Rezende et al., 1401.4082) pair from `alignment_benchmark/test_set/`. This is a canonical parallel-rediscovery pair — both independently derive the reparameterization trick.

### Top matches found by embedding sigma

| Rank | Score | Paper A Node | Paper B Node | Gold Match |
|------|-------|-------------|-------------|------------|
| 1 | 0.845 | TP_VAE.1 (Unbiased gradient estimator via reparam.) | TP_DLGM.1 (Unbiased gradient estimator for DLGM) | exact |
| 2 | 0.823 | DP_VAE.2 (Intractable posterior / recognition model) | DP_DLGM.3 (Recognition model) | exact |
| 3 | 0.812 | EP_VAE.1 (MNIST and Frey Face generation) | EP_DLGM.1 (MNIST generative modeling) | exact |
| 4 | 0.803 | DP_VAE.4 (Reparameterization trick) | DP_DLGM.4 (Gaussian backpropagation) | exact |
| 5 | 0.770 | DP_VAE.3 (ELBO) | DP_DLGM.2 (Variational free energy / ELBO) | exact |
| 6 | 0.762 | DP_VAE.1 (Latent variable model) | DP_DLGM.1 (Deep latent Gaussian model) | analogous |

All 6 gold-standard exact/analogous pairs appear in the top 6 results. 

### Separation quality
- **Embedding gold pairs:** median ~0.79, range 0.69-0.85
- **Embedding non-gold pairs:** median ~0.12
- **Jaccard gold pairs:** median ~0.33, range 0.04-0.46
- **Jaccard non-gold pairs:** median ~0.03

The embedding sigma provides roughly 2x better separation between gold and non-gold pairs compared to Jaccard.

## How to Run the Full Benchmark (on the cluster)

### Prerequisites
```bash
pip install numpy scipy scikit-learn sentence-transformers
# torch >= 2.2 required (>= 2.6 for BGE-M3)
```

### Step 1: Run the benchmark
```bash
cd /sci/labs/orzuk/orzuk/projects/Authomathics/arxiv/alignment_benchmark

# Make sure scripts/ is on PYTHONPATH
export PYTHONPATH="/path/to/Authomathics/scripts:$PYTHONPATH"

python /path/to/Authomathics/scripts/run_alignment_benchmark.py \
    --config config/benchmark_config.json \
    --sigma-import embedding_sigma.sigma \
    --sigma-label bge-large \
    --n-perms 300 \
    --output results_embedding.csv
```

### Step 2: Compare to Jaccard baseline
```python
import pandas as pd

baseline = pd.read_csv("baseline_results/results_jaccard_combined.csv")
embedding = pd.read_csv("results_embedding.csv")

merged = baseline.merge(embedding, on="pair_name", suffixes=("_jac", "_emb"))
for col in ["z_hung", "z_gold", "f1"]:
    jc, ec = f"{col}_jac", f"{col}_emb"
    if jc in merged.columns and ec in merged.columns:
        merged[f"delta_{col}"] = merged[ec] - merged[jc]

print(merged[["pair_name", "type_jac", 
              "z_hung_jac", "z_hung_emb", "delta_z_hung",
              "f1_jac", "f1_emb", "delta_f1"]].to_string(index=False))
```

### Step 3: Generate heatmaps
```bash
python /path/to/Authomathics/scripts/viz_alignment_heatmaps.py \
    --config config/benchmark_config.json \
    --outdir heatmaps/
```

### Step 4 (optional): Run with canonicalization
For best results, canonicalize paper JSONs first, then run on canonicalized versions:
```python
from scripts.canonicalize import canonicalize_paper
import json

paper = json.load(open("papers/paper101_gold.json"))
canonical = canonicalize_paper(paper)
json.dump(canonical, open("papers/paper101_canonical.json", "w"))
```
The embedding sigma automatically reads `*_canonical_local` fields when present.

### Step 5 (optional): Try a different model
```bash
# If torch >= 2.6 on the cluster:
export EMBEDDING_MODEL=BAAI/bge-m3
# Then re-run steps 1 and 3
```

## Target Metrics (from README_FOR_YARON.md)

| Metric | Jaccard Baseline | Target | 
|--------|-----------------|--------|
| Positive Z(Hung) mean | +1.46 | >= +4.0 |
| Negative Z(Hung) mean | +0.26 | <= +1.5 |
| Negative pairs with Z > 2 | 3 | 0 |
| Pos vs Neg Z-gap | 0.82 sigma | >= 3 sigma |

## Architecture Notes

- The sigma function is stateless and cacheable — the same function handles all 20 pairs with no pair-specific tuning
- The `lru_cache` on `_embed_cached` means each unique node text is embedded only once, even across the 300+ permutation iterations in the significance test
- Type compatibility weighting (`type_compat` from `graph_alignment.py`) is applied identically to the Jaccard baseline — theorem-theorem = 1.0, theorem-lemma = 0.9, theorem-definition = 0.1, etc.
- The text extraction prioritizes: `field_canonical_local` > `field_canonical_paper` > `field` (raw), so canonicalization is used automatically when available
