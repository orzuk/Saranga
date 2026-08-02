# T-OPEN semantic retrieval (O1b / O1c / O5)

Candidate generation for T-OPEN was lexical: `sweep_open.py` ranks problem→theorem
pairs by token Jaccard over `clean_latex_to_text(raw_latex)`. On the 100k v4 corpus
that produced 15,143 problems × 1,589,327 theorem-like nodes → 300,204 pairs → a
166-pair shortlist → **7 YES / 5 PARTIAL / 154 NO**, and every strong YES turned out
to be *cited*, i.e. already known. ROADMAP §7.1 names the gap: **only near-verbatim
resolutions ever reach the shortlist**. A resolution phrased in different words is
invisible to the matcher, so the judge never gets the chance to see it.

This is the semantic arm. It is **purely additive** — no existing file was modified.
`sweep_open.py` is now the lexical arm of a comparison, and the output of every new
stage keeps the same nine leading CSV columns, so `triage_open.py` → author gate →
`batch_o4.py` → S2 citation gate all work unchanged.

## Why this is affordable

A bi-encoder is **O(N), not O(N²)**. We run 1.6M forward passes once. Scoring is
then a dense matmul: 15,143 × 1,589,327 × 1024 ≈ 2.4e13 FLOPs — under a minute of
L40s tensor-core time, versus ~57 CPU-minutes for the lexical inverted-index rank.
Pairs are never materialized until the cross-encoder, which sees only the top-20 per
problem (~300k pairs, ~1e-5 of the 24 billion possible). "Millions of pairs is
unreasonable" is true of cross-encoders and false of bi-encoders; the pipeline is
shaped around that distinction.

| stage | cost at 100k | notes |
|---|---|---|
| text store (CPU) | ~25 min on 32 cores | canonicalization is ~98% of it, 240 nodes/s/core |
| encode (GPU) | ~33 GPU-min per (model, view, canon) | ~800 nodes/s on an L40s |
| dense retrieve (GPU) | ~1 min | exact; ANN only needed past ~10M docs |
| rerank (GPU) | ~20 min, ~5 across a 4-way array | the only per-pair stage |

Champion configuration end to end: **~3 GPU-hours, zero API spend** until the
existing Opus judge runs.

## The three axes being compared

**Embedder.** `minilm` (cheap floor, CPU-viable) · `distilbert` (raw mean-pooled
BERT — the naive baseline, expected to lose, which is the point) · `specter2`
(scientific) · `bge-m3` · `qwen3-0.6b` (instruction-aware, asymmetric) ·
`qwen3-4b` (ceiling). See `embed/models.py`; run
`python -m embed.models --check --models all` on the target machine before
launching anything.

**View — how much graph goes into the vector.**

| view | text embedded | extra GPU pass |
|---|---|---|
| `node` | the statement alone | baseline |
| `ctx-concat` | statement + typed block of the definitions/assumptions it `uses` + its non-generic `grounded_to` concepts | yes |
| `ctx-late` | `normalize(α·v_node + (1−α)·Σ wᵢ·v_neighbourᵢ)` | **no** — reuses node vectors, α swept post-hoc |
| `concepts-only` | just the grounded_to concept names | no |

Context comes from the typed graph (`uses` out-edges, `grounded_to` concepts with
their `idf`/`generic` flags), not from surrounding prose. Neighbour ordering is fully
deterministic so embeddings reproduce across runs and machines.

**Canonicalization.** `raw` vs `canon` (α-renamed variables, normalized
fractions/binomials/inequalities via `scripts/canonicalize`), plus **score-level
fusion of the two** — never vector concatenation, which would let whichever half has
the larger norm dominate. Two scopes on purpose: the `node` view uses **local**
scope (V1 = first variable in *this* statement, which is what aligns two isolated
statements pairwise, matching `scripts/embedding_sigma.py`), while `ctx-concat` uses
**paper** scope so the theorem and the definitions quoted beneath it share one
numbering. A local map per fragment would make the assembled block internally
inconsistent and unfairly penalize the canonical arm.

**Fusion** (`embed/fuse.py`): `rrf` (default — rank-based, needs no calibration,
which matters because a 0.83 cosine from one model and a 0.61 from another can be
equally good), `znorm` (per-problem z-scored linear blend, for arms that do share a
scale), `linear`, `max`.

## Running it

### Local (no GPU)

```bash
PY=/Users/yaronot/miniconda3/bin/python3     # the system python3 here is a broken 3.9 framework build
cd discovery_suite

# 1. text store (300 papers)
$PY -m embed.textstore plan  --out /tmp/store --limit 300
$PY -m embed.textstore build --out /tmp/store --shards 4 --workers 4

# 2. vectors
$PY -m embed.encode --store /tmp/store --out /tmp/vecs --model minilm --view node --canon raw

# 3. dense candidates (sweep_open-compatible CSV)
$PY open_problems/o1b_dense_sweep.py all --vectors /tmp/vecs \
    --model minilm --view node --canon raw --top-k 20 --out /tmp/dense.csv

# 4. fuse with the lexical sweep, then the unchanged triage
$PY open_problems/o1c_fuse.py --lexical /tmp/lex.csv --dense /tmp/dense.csv --out /tmp/fused.csv
$PY open_problems/triage_open.py --in /tmp/fused.csv --out /tmp/triage.csv --min-score 0.5 --per-problem 3
```

### Cluster

```bash
export ROOT=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4
export RUN=$PWD/discovery_suite/open_problems/runs/dense_100k
export MODELS="qwen3-0.6b bge-m3"
export ARMS="node:raw node:canon ctx-concat:raw"
bash discovery_suite/open_problems/embed_cluster.sh      # chains all stages with dependencies

python3 discovery_suite/open_problems/watch_open.py $RUN --watch 15
```

`embed_cluster.sh` builds the text store **once** and shares it across every
(model, view, canon) arm — canonicalization and context assembly don't depend on the
embedder, so rebuilding per arm would waste most of the CPU budget.

### Benchmark (which arm actually wins)

```bash
python3 discovery_suite/open_problems/bench_retrieval.py \
    --papers 300 --twins 40 --models minilm,bge-m3,qwen3-0.6b \
    --views node,ctx-concat,ctx-late,concepts-only --canons raw,canon \
    --judged discovery_suite/open_problems/runs/o4_verdicts_all.csv \
    --out discovery_suite/open_problems/runs/bench_matrix.csv
```

Emits one row per arm: AP, MRR, P@k/R@k, recall per obfuscation level, plus a cost
column (encode seconds, texts/s). Only the winners are run corpus-wide.

Two gold sources. **Planted twins** are the recall/obfuscation measurement.
`--judged` adds the **real** Opus verdicts on the lexical top-166 (7 YES + 5 PARTIAL
as positives, 154 NO as hard negatives — hard precisely because every one of them
already ranked highly under token Jaccard). Those pairs were *found by* the lexical
arm, so they measure **ranking and precision, not recall**, and only pairs whose both
nodes are in the current slice can be scored — on a small local slice that is often
none, and the tool says so rather than silently scoring nothing.

## Three things to know before trusting the benchmark

**1. The planter's text source.** `eval_harness/open_planter.plant_twins` poses its
synthetic problems from `clean_text`, which the base parser masks to `[MATH]`, while
both retrieval arms read math-preserving `raw_latex` (since the `--text-source raw`
fix). Planting from the masked field measures retrieval against text nothing
indexes, and hits the canonical arm hardest — there is no notation left to
canonicalize. `bench_retrieval.py --planter mathaware` (default) poses from the same
source retrieval sees; `--planter legacy` reproduces the old behaviour.

**2. Obfuscation without `--llm` is not paraphrase.** The offline L2–L4 fallback in
`eval_harness/obfuscate.py` does synonym swaps, variable renames and sentence
shuffling — it leaves most content words in place, so planted twins stay lexically
near-verbatim and **the lexical baseline scores near-perfectly at every level**. That
is a property of the harness, not a finding about embedders. The detection-vs-
obfuscation curve only becomes meaningful with `--llm haiku`, which routes L2–L4
through `eval_harness/llm_paraphrase.py` (sqlite-cached; needs `ANTHROPIC_API_KEY`).
**This has not been run** — it is the first thing to do before drawing any
conclusion about semantic vs lexical matching.

**3. Planted problems have no graph edges.** A planted twin is a bare node appended
to a paper, so it has no `uses` or `grounded_to` edges and the context views give it
no context — only the theorem side gets enriched. Real `conjecture`/`open_problem`
nodes do have edges, so the benchmark **understates** what `ctx-concat` / `ctx-late`
are worth. Treat a planted-twin context gain as a lower bound, and confirm on real
pairs (e.g. the 166 already judged) before concluding the context views don't help.

## Progress and resumability

Every stage prints its totals up front (papers, nodes to embed, query/doc counts,
pairs to score, pairs to rerank) and heartbeats with rate + ETA. Each task writes its
**own** `<stage>.<task>.json` status file — never a shared log, which is what killed
the whole-arXiv download jobs through NFS lock contention. `watch_open.py` aggregates
them into one table and flags tasks that have gone silent (a SLURM task can die
without ever writing a terminal state).

Every stage is resumable: text-store shards, vector shards and retrieval partials all
carry `.done` markers and are written atomically (temp file + rename), so a killed
job leaves either complete output or none — never a truncated file that a resume
would treat as finished.

## Files

```
embed/progress.py    Heartbeat, per-task status JSON, ETA
embed/views.py       node/ctx/canon text views, graph-context assembly
embed/textstore.py   corpus -> sharded text store (parallel CPU, resumable)
embed/models.py      ModelCard registry + `--check` availability probe
embed/encode.py      text shard -> fp16 unit vectors (resumable)
embed/index.py       search backends, ctx-late assembly, top-k merge
embed/fuse.py        RRF / z-norm / linear / max over CSVs

open_problems/o1b_dense_sweep.py   map-reduce dense retrieval -> sweep-schema CSV
open_problems/o1c_fuse.py          lexical+dense fusion with a contribution report
open_problems/o5_rerank.py         cross-encoder rerank of the shortlist
open_problems/bench_retrieval.py   Tier-A factorial benchmark
open_problems/watch_open.py        live progress across array tasks
open_problems/{textstore,encode,dense,rerank}_cluster.sh + embed_cluster.sh
```

## Verified so far (local, 300 papers, MiniLM)

- `numpy-flat` and `torch` backends return **identical** top-k (max score delta 6e-7).
- Re-encoding a shard is **bitwise identical** — vectors reproduce across runs.
- Temporal + self-paper filters: **0 violations** in the retrieved candidates.
- Dense CSV → `triage_open.py` runs **unchanged** (temporal gate, `needs_context`
  routing, per-problem cap all apply normally); fused CSV likewise.
- Retrieved node types are theorem-like only (theorem/lemma/corollary/proposition/claim).

Not yet run: the full model roster (needs a GPU), the LLM-paraphrase obfuscation
curve, and any corpus-scale run.
