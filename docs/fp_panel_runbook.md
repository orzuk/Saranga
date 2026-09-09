# Held-out FP audit — four open-weight judges, one pass

Reads the false positives of the 146-rule run over the 140 held-out papers and
asks whether they are extraction errors or places the silver corpus
under-labelled. Read-only: it changes no rule, no gate, no snapshot.

## Why it is shaped this way

**140 papers, not 200.** The 60 train papers chose the 146 rules, so an
adjusted precision measured on them is not reportable — and they have never
been parsed with the 146-rule set, so auditing them would mean an extra parse
run for a number that could not be quoted anyway. (Worth asking separately, and
later: does the rescue rate differ between papers the rules were built from and
papers they were not? That measures silver quality, not the 146.)

**M3, not M1.** 1,889 M3 FPs against 4,299 M1. The extra 2,410 are mostly
nesting and span-boundary artefacts M3 already forgives, so judging them would
re-measure the M1/M2/M3 ladder. The M3 residual is the part where the
disagreement is about content.

**Four judges, none of them Claude.** Alibaba, Mistral, Google, Meta — the
silver corpus is Claude Opus's, so no model reviews its own output. A verdict
counts only where all four agree; splits are recorded as splits.

**One pass.** The held-out set has now been scored once. Every further look
weakens it as an unbiased estimate, so this is planned as a single pass, not an
iterate-and-retry.

## Steps

1. **Recover the FP spans (local, ~30 min of parsing).**

   ```
   python scripts/heldout_fp_dump.py \
     --eval-dir src/LLMVersion/heldout_eval_selected146 \
     --gold-dir src/LLMVersion/merged_eval_v51_train60_v2/silver_gold \
     --tex-dir corpus/silver/tex_staged --workers 6
   ```

   Re-parses under the frozen 146 rules and **fails hard** unless every
   per-paper per-type m1/m3 count reproduces `heldout_scores.jsonl` exactly. If
   it passes, `heldout_fp_m3.csv` is by construction the FP set behind 0.7563.
   Buckets are cached to `heldout_buckets.json`, so the parse is paid once.

2. **Ship the FP list to the cluster.**

   ```
   cat src/LLMVersion/heldout_eval_selected146/heldout_fp_m3.csv | \
   ssh -J yaron.otmazgin@bava.cs.huji.ac.il yaron.otmazgin@moriah-gw.cs.huji.ac.il \
     "cat > /sci/labs/orzuk/yaron.otmazgin/Authomathics/src/LLMVersion/heldout_eval_selected146/heldout_fp_m3.csv"
   ```

3. **Run each judge (cluster).** One job per model; each serves vLLM and runs
   the client in the same allocation, so the GPUs come back when the judging
   ends rather than at the 24h walltime.

   ```
   sbatch --gres=gpu:l40s:1 scripts/run_fp_panel_cluster.sh qwen3-32b-awq
   sbatch --gres=gpu:l40s:2 scripts/run_fp_panel_cluster.sh mistral-small-24b
   sbatch --gres=gpu:l40s:2 scripts/run_fp_panel_cluster.sh gemma-3-27b-it
   sbatch --gres=gpu:l40s:4 scripts/run_fp_panel_cluster.sh llama-3.3-70b
   ```

   Each writes `heldout_eval_selected146/panel/fp_panel_<model>.csv` and is
   resumable — a server that dies at row 1,500 does not cost the first 1,500.

4. **Join and report.**

   ```
   python scripts/fp_panel_consensus.py \
     --fps    src/LLMVersion/heldout_eval_selected146/heldout_fp_m3.csv \
     --scores src/LLMVersion/heldout_eval_selected146/heldout_scores.jsonl \
     --panel  src/LLMVersion/heldout_eval_selected146/panel/fp_panel_*.csv
   ```

   Produces `panel/fp_verdicts.csv` (per-FP: four votes, consensus, snippet)
   and `panel/fp_panel_report.txt` (panel behaviour, adjusted precision band,
   per-type table).

## Things that have already cost time

- **Pin sampling.** Qwen3 ships `generation_config.json` with temperature 0.6,
  so an unpinned judge samples a fresh verdict per run. The shim pins
  temperature 0 / top_p 1 / top_k -1 / seed 0 and sends
  `enable_thinking=false` — without the latter a `<think>` block eats
  `max_tokens` before the `VERDICT:` line, giving empty verdicts rather than
  wrong ones.
- **MISSING is not a verdict.** Batched per-index answers are where a smaller
  model drifts first. An unanswered index is recorded `MISSING`, never folded
  into a verdict; `--repair-missing` re-asks exactly those rows singly and
  flags them, so the two prompt shapes stay distinguishable.
- **Ask the M3 question.** "Is this really a definition?" is beside the point
  when the disagreement is a span sitting inside a larger structure. Under m3
  `fp_judge.judge_batch` asks instead whether the reference missed it
  *entirely* — which is what an M3 FP actually is.
- **Some templates reject a system turn.** The shim retries once with the
  system block prepended to the first user message and records which envelope
  the endpoint accepted.
