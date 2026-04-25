# Pipeline Architecture: Datasets, Stages, and Refactor Plan

> **Status**: 2026-04-25 design doc, pre-refactor.
> **Owner**: Or Zuk; reviewer: Yaron Otmazgin.
> **Companion doc**: `docs/graph_compare_design.md` (the comparison-task half).

## 1. Five data tiers

| Tier | Name | Size | Extraction | Primary use |
|---|---|---|---|---|
| **A** | Corpus | ~50K papers | per-type regex (cheap) | scale, statistics, foundation linking |
| **B** | Silver-gold | ~270 papers | holistic LLM × 2-3 models | consensus → silver-gold annotations for distillation |
| **C** | Hand-gold eval | ~10 papers | hand-annotated reference | grade extractions vs human gold (T1) |
| **D** | High-resolution | ~20 papers | holistic LLM with proof-step decomposition | per-step proof structure for fine-grained eval |
| **E** | Cross-paper alignment | 131 pairs (20 active) | uses B/D extractions | bipartite alignment + Z-scores (T3) |

**Dependencies**:
- A is independent.
- B feeds C and E.
- D feeds C (if hand-gold has proof steps) and E (high-res variant).
- C reports T1 metrics.
- E reports T3 metrics.

## 2. Operations × tiers matrix (the contract)

Rows are stages (library functions). Columns are tier drivers. ✓ = stage applies to this tier.

| Operation | Tier A 50K | Tier B 270 | Tier C 10gold | Tier D 20hires | Tier E 131align |
|---|:---:|:---:|:---:|:---:|:---:|
| Source verify / arxiv fetch | ✓ | ✓ | ✓ | ✓ | (via B) |
| Extract: per-type regex | ✓ | — | — | — | — |
| Extract: holistic LLM (multi-model) | — | ✓ | — | — | — |
| Extract: holistic LLM with proof-steps | — | — | — | ✓ | — |
| Validate (DAG + schema) | ✓ | ✓ | ✓ | ✓ | (per-paper, via B) |
| Anomaly detection | ✓ | ✓ | ✓ | ✓ | — |
| Corpus stats | ✓ | ✓ | — | ✓ | — |
| Foundation graph link | ✓ | ✓ | ✓ | ✓ | (per-paper, via B) |
| Visualize per-paper (PNG + HTML) | optional | ✓ | ✓ | ✓ | ✓ |
| **Consensus across models** | — | ✓ | — | (if multi) | — |
| **Eval vs hand-gold (T1)** | — | — | ✓ | ✓ if gold | — |
| **Cross-paper alignment (T3)** | — | — | — | — | ✓ |
| Pair-level alignment HTML | — | — | — | — | ✓ |

Reading: ~30 cells, ~5-8 are filled per column. Each row is a single library function — fix bugs in one place; each column is one driver — only knows its own subset.

## 3. Architectural choice

**One master pipeline + thin tier-specific wrappers.**

```
src/run_pipeline.py                         (THE master dispatcher — extended)
  ├── --extract-mode {regex, holistic-multi, holistic-proof-steps}
  ├── --operations {parse, validate, anomalies, stats, link, visualize, consensus, eval, align}
  ├── --models-config <yaml>                   for holistic-multi
  ├── --gold-dir <path>                        for eval
  └── ... all other params

scripts/                                    (THIN WRAPPERS)
├── run_corpus.sh             ← Tier A invocation
├── run_silver_gold.sh        ← Tier B invocation
├── run_gold_eval.sh          ← Tier C invocation
├── run_high_res.sh           ← Tier D invocation
└── run_alignment.sh          ← Tier E invocation
```

Each wrapper is ~30 lines: hard-codes paths, mode, and operations for its tier; passes through user-tweakable args (--limit, --paper-ids).

Why this beats separate Python drivers:
- Single source of truth for the dispatcher → fix bugs once
- Adding a new stage = modify run_pipeline.py once → all tiers benefit
- Adding a new tier = write a new ~30-line wrapper → no dispatcher duplication
- Easier to test (one entry point to integration-test)

## 4. Current state vs target

| Component | Current state | Target state |
|---|---|---|
| `src/run_pipeline.py` | regex-only parse, fixed dispatch (Yaron) | extended: holistic-multi mode, consensus stage, eval stage |
| `scripts/silver_gold/run_extraction.py` | standalone multi-provider runner | becomes the holistic-multi backend that run_pipeline.py invokes |
| `scripts/silver_gold/run_full_pipeline.py` | standalone Tier B driver (current) | replaced by `scripts/run_silver_gold.sh` calling run_pipeline.py |
| `scripts/silver_gold/consensus_intersect.py` | standalone | becomes the `consensus` stage backend |
| `src/validate_annotation.py` | standalone | becomes the `validate` stage backend (no change needed; subprocess from run_pipeline) |
| `src/visualize_annotation.py`, `src/link_to_foundation.py` | standalone | already used as backends |
| Anomaly detector | inline in run_pipeline.py | factor out into `src/anomaly_detect.py` (cleaner) |
| `scripts/run_alignment_benchmark.py` | standalone Tier E driver | becomes one of the wrappers, or stays standalone (it's already thin) |

## 5. Phase 2 — light additions (TODAY, ~1 hour)

Goal: make `scripts/silver_gold/run_full_pipeline.py` (Tier B driver) feature-complete by adding the missing stages via subprocess to existing tools. **Does not touch Yaron's `src/run_pipeline.py`.** This is interim until the master refactor.

Stages to add as new flags:

```python
ap.add_argument("--validate", action="store_true",
                help="run src/validate_annotation.py on each output JSON")
ap.add_argument("--anomalies", action="store_true",
                help="run anomaly detection on each output JSON")
ap.add_argument("--consensus", action="store_true",
                help="after extractions, run consensus_intersect.py "
                     "pairwise vs the first model in the config "
                     "(typically Opus); writes gold_consensus_*.json")
```

Implementation pattern (same as existing --link-foundation):

```python
def run_validate(json_path: Path) -> bool:
    script = REPO_ROOT / "src" / "validate_annotation.py"
    cmd = [sys.executable, str(script), str(json_path)]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        # parse output for pass/fail; print summary
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [WARN] validate failed: {e.stderr.decode()[:200]}")
        return False

def run_anomaly_detect(json_path: Path) -> bool:
    # Need to find where anomaly logic lives — could be:
    #   src/anomaly_detect.py (if separated)
    #   src/run_pipeline.py with a CLI flag (if not separated)
    # If not separable, add a TODO and skip in Phase 2.
    pass

def run_consensus(model_configs: List[Dict], base_dir: Path, paper_ids: List[str]) -> None:
    # For each non-reference model, call consensus_intersect.py vs model[0]
    ref_suffix = model_configs[0].get("suffix", "")
    consensus_script = REPO_ROOT / "scripts" / "silver_gold" / "consensus_intersect.py"
    for m in model_configs[1:]:
        suffix = m.get("suffix", f"_{m['name']}")
        if not suffix:
            continue
        out_csv = f"agreement_{m['name']}_vs_ref.csv"
        cmd = [sys.executable, str(consensus_script),
               "--base-dir", str(base_dir),
               "--suffix-a", ref_suffix,
               "--suffix-b", suffix,
               "--out-suffix", f"_consensus_{m['name']}",
               "--report-csv", out_csv,
               ...]
        subprocess.run(cmd, check=False)
```

Caller wires these into the existing per-paper / per-config loops in `run_full_pipeline.py`.

Also: in `run_extraction.py`, lift `match_same_paper` into `src/graph_alignment.py` so future eval driver can reuse (Phase 2 of `graph_compare_design.md`).

**Estimated effort**: 1-1.5 hours. Single PR.

## 6. Phase 3 — master pipeline refactor (this week, ~6-8 hours)

Goal: `src/run_pipeline.py` becomes the master dispatcher; all tier-specific scripts become ~30-line wrappers.

### 6.1 Operation registry

Refactor `src/run_pipeline.py` to dispatch on a registry:

```python
OPERATIONS = {
    "parse": dispatch_parse,
    "validate": run_validate,
    "anomalies": run_anomaly_detect,
    "stats": run_stats,
    "link": run_foundation_link,
    "visualize": run_visualize,
    "consensus": run_consensus,
    "eval": run_eval_against_gold,
    "align": run_cross_paper_align,
}

def main():
    ops = args.operations.split(",")
    for op in ops:
        if op not in OPERATIONS:
            sys.exit(f"unknown operation: {op}")
        OPERATIONS[op](args)
```

### 6.2 Extract mode dispatch

`dispatch_parse` selects the extraction backend based on `--extract-mode`:

```python
def dispatch_parse(args):
    if args.extract_mode == "regex":
        return run_per_type_regex(args)            # existing logic
    elif args.extract_mode == "holistic-multi":
        return run_holistic_multi(args)            # NEW: calls run_extraction.py per model
    elif args.extract_mode == "holistic-proof-steps":
        return run_holistic_proof_steps(args)      # NEW: variant for Tier D
    else:
        sys.exit(f"unknown extract-mode: {args.extract_mode}")
```

`run_holistic_multi` reads the model config (yaml or json), iterates through models, calls `run_extraction.py` per model with appropriate env vars (current `run_full_pipeline.py` logic).

### 6.3 Wrapper scripts

```bash
# scripts/run_silver_gold.sh
#!/bin/bash
python3 src/run_pipeline.py \
    --operations parse,validate,anomalies,link,visualize,consensus \
    --extract-mode holistic-multi \
    --models-config scripts/silver_gold/example_config.yaml \
    --base-dir /sci/.../alignment_benchmark \
    --registry /sci/.../paper_registry.csv \
    --prompt-file scripts/paper_extraction_prompt.txt \
    --resume \
    "$@"   # passes through --limit, --paper-ids, etc.
```

```bash
# scripts/run_corpus.sh — Tier A invocation
python3 src/run_pipeline.py \
    --operations parse,validate,anomalies,stats,link \
    --extract-mode regex \
    --category math.CO \
    --start 2024-01-01 \
    --top-k 50000 \
    "$@"
```

Each wrapper is ~10-30 lines. Tier-specific knowledge (paths, ops, mode) lives only in the wrapper. The user invokes the wrapper for their tier.

### 6.4 Migration order

1. Add the operation registry to `src/run_pipeline.py` without breaking existing operations.
2. Add `--extract-mode` flag (default `regex` for backward compat).
3. Add holistic-multi backend (calls run_extraction.py).
4. Add `consensus`, `eval` operations.
5. Write 5 wrapper scripts.
6. Test each wrapper on a small sample.
7. Deprecate `scripts/silver_gold/run_full_pipeline.py` (point users at the wrapper).

**Estimated effort**: 6-8 hours focused work.

### 6.5 Risks

- Existing `src/run_pipeline.py` already has its own conventions (output paths YYYY/MM/DD/json/, etc.). Need to preserve for Tier A.
- Tier B (silver-gold) has different output convention (`papers/paperN/gold_*.json`). The dispatcher must respect the tier-specific structure.
- Solution: each operation knows the tier-specific I/O via the chosen `--extract-mode`, not via global config.

## 7. Paper appendix draft (latex-ready)

This table can drop into the manuscript appendix as-is.

```latex
\begin{table}[h]
\centering
\small
\caption{Datasets and pipeline stages used in SARANGA. Tier sizes
listed are pre-extraction. Each tier uses a subset of the available
operations; rows are operations, columns are tiers, $\checkmark$
denotes the operation is run on that tier.}
\label{tab:tier-stages}
\begin{tabular}{lccccc}
\toprule
& \multicolumn{5}{c}{\textbf{Tier}} \\
\cmidrule{2-6}
\textbf{Operation} & A: Corpus & B: Silver & C: Gold & D: High-res & E: Pairs \\
& 50K papers & 270 papers & 10 papers & 20 papers & 131 pairs \\
\midrule
Source fetch (arXiv)        & \checkmark & \checkmark & \checkmark & \checkmark & via B \\
Extract: per-type regex     & \checkmark & ---        & ---        & ---        & --- \\
Extract: multi-LLM holistic & ---        & \checkmark & ---        & ---        & --- \\
Extract: with proof steps   & ---        & ---        & ---        & \checkmark & --- \\
Validate (DAG, schema)      & \checkmark & \checkmark & \checkmark & \checkmark & via B \\
Anomaly detection           & \checkmark & \checkmark & \checkmark & \checkmark & --- \\
Corpus statistics           & \checkmark & \checkmark & ---        & \checkmark & --- \\
Foundation graph link       & \checkmark & \checkmark & \checkmark & \checkmark & via B \\
Visualize (PNG + HTML)      & opt.       & \checkmark & \checkmark & \checkmark & \checkmark \\
Multi-model consensus       & ---        & \checkmark & ---        & opt.       & --- \\
Eval vs hand-gold (T1)      & ---        & ---        & \checkmark & opt.       & opt. \\
Cross-paper alignment (T3)  & ---        & ---        & ---        & ---        & \checkmark \\
\bottomrule
\end{tabular}
\end{table}
```

## 8. Phase 4 — codebase cleanup (after refactor settles, ~1-2h)

After Phase 3 lands, several scripts become obsolete or duplicative.
Run a dedicated cleanup agent that produces a **proposal** (not deletions).

Cleanup agent mandate:
1. **Inventory** all `.py` and `.sh` files in `scripts/` and `src/`, with
   last-mod dates and import/subprocess relationships across the codebase.
2. **Classify** each as `keep / merge / delete / unsure` with one-line
   justification per file.
3. **Yaron-respect**: anything in `src/LLMVersion/` or files touched by
   Yaron in the last 30 days defaults to `unsure` — needs his sign-off.
4. **Output**: `docs/cleanup_proposal.md` for Or's review. **No deletions
   without explicit OK.** A second agent run executes approved deletions.

Likely candidates already visible:
- `scripts/silver_gold/run_full_pipeline.py` — replaced by
  `scripts/run_silver_gold.sh` if Phase 3 absorbs holistic-multi into
  master pipeline.
- Various `scripts/debug_*.sh` / `scripts/find_*.sh` — Herald-investigation
  one-offs that may no longer be used.
- Pairs like `link_to_foundation.py` vs `foundation_linker.py` —
  potential old/new duplication.
- Commented-out / dead code blocks in larger files.

The Phase 3 agent should leave a **handoff note** at the bottom of this
doc listing files it observed becoming obsolete during refactor, to seed
the Phase 4 inventory.

## 9. Schedule (working backwards from May 6)

| Date | Action |
|---|---|
| 2026-04-25 (today) | Doc + Phase 2 light changes (in flight) |
| 2026-04-25 to 2026-04-27 | Silver-gold extraction on cluster; manual inspection of LLM discrepancies on paper1/2/5 |
| 2026-04-26 to 2026-04-29 | Phase 3 master refactor (~6-8h, in 2 blocks) |
| 2026-04-29 to 2026-04-30 | **Phase 4 cleanup proposal → Or review → deletions** |
| 2026-04-28 to 2026-05-02 | Consensus computed; write up Section 6 (silver-gold methodology) |
| 2026-05-03 to 2026-05-05 | Paper polish, figures, references |
| 2026-05-06 | Submit |

## 9. Non-goals

- **Do not** rewrite `src/run_pipeline.py` in a single big-bang commit. Migrate operation-by-operation with backward compat.
- **Do not** unify holistic-multi and per-type backends — they have different output paths and different cost profiles. Two backends, one dispatcher.
- **Do not** preempt the master refactor while the silver-gold experiment is producing data — the experiment is using the standalone scripts and that's fine.
