# alg3 autoresearch

An automatic search loop for the alg3 sentence tagger, after Karpathy's autoresearch
(github.com/karpathy/autoresearch): you, a coding agent, change the tagger, train it
under a fixed budget, read one number, keep the change if the number went up and revert
it otherwise, and repeat. Nobody answers questions during the loop: decide, log, move on.

## Setup (once, before the loop)

1. Pick a tag from today's date, e.g. `oct16`. Work in a throwaway worktree on a LOCAL
   branch, never pushed:

       git worktree add ../Saranga_ar_<tag> -b autoresearch/<tag> main
       cd ../Saranga_ar_<tag>

2. Copy the training data (gitignored) into the worktree, or build it (about a minute):

       mkdir -p alg3/cache && cp <main checkout>/alg3/cache/papers.pkl alg3/cache/
       # or: python3 alg3/data.py --splits train,val --tex-dir corpus/silver/tex_staged

3. Read `alg3/README.md`, `alg3/features.py`, `alg3/train.py` and `alg3/doc/alg3_method.tex`.
4. Create `alg3/runs/autoresearch/<tag>/results.tsv` with the header row below.
5. Run the baseline (the released v2b settings) unchanged and log it as the first row.

## The experiment

    timeout 900 python3 alg3/train.py --class-weight sqrt --stack \
        --out alg3/runs/autoresearch/<tag>/run > alg3/runs/autoresearch/<tag>/run.log 2>&1
    grep "train OOF F" alg3/runs/autoresearch/<tag>/run.log

That line holds `train OOF F=<oof>` (thresholds tuned on out-of-fold predictions for the 120
train papers) and `val {... 'F': <val>}` (the 40 validation papers). Both are the pooled
(micro) overall F of the whole extractor (base parser + tagger) under m1g, the headline
metric of the paper. The baseline takes about 6 minutes on an 8-core Mac.

**score = (oof + val) / 2.** Use the OOF number, which covers 120 papers, so that you don't
chase noise in 40 validation papers. Keep a change when the score rises by at least 0.001.
A tie with less code is a keep: simpler is better.

You may change train.py's options and defaults (C, class weights, `--stack`, `--min-count`,
`--classifier lr|gb`, span model settings) as well as the code.

## What you may change

- `alg3/features.py`: the clues of a sentence. Add, remove or reshape them, e.g. cue phrases,
  context windows, section and environment cues, bucketings, or conjunctions of clues.
- `alg3/train.py`: the model and training: classifier, regularisation, class weights,
  stacking, span model, and the threshold search space.
- When `FEATURES_VERSION` in features.py no longer describes the clues, bump it.

## What you must NOT change

- The scoring: `evaluate`, `fast_eval`, `candidates`, `tokens` and the objective of
  `tune_tau` in train.py, plus anything under `scripts/` and `src/`. The assert in
  `tune_tau`, which checks that the fast path agrees with the full decode, must keep
  passing.
- The data: `alg3/data.py`, `alg3/cache/`, the silver (`corpus/silver/`), and the split
  (`corpus/silver/split_v6_6-2-2.csv`).
- **Never read, load or score a TEST paper.** The cache holds train and val only, and
  `data.py` refuses test. The test set is scored once, by a human, with
  `scripts/compare_distillers.py`, after the loop.
- Parse time must stay pure Python. `alg3/runtime.py` applies the exported model with no
  numpy, scikit-learn or xgboost; if you change the model's form, extend the export and
  runtime to match. Keep it at most about 1.5 s per paper.
- Clues must be deterministic string tests: no LLM calls, no network, no neural models or
  embeddings, no new packages.
- Nothing outside the worktree; never push; never merge into main.

## Logging

`alg3/runs/autoresearch/<tag>/results.tsv` is tab-separated and never committed:

    commit	oof	val	score	minutes	status	description

`status` is `keep`, `discard` or `crash` (a crash logs 0 for every number). `description`
is one line on what changed and why.

## The loop

1. Look at the current errors. Use the out-of-fold mistakes on the TRAIN papers
   (`--dump-oof`), or `python3 alg3/analyze.py --model <run dir>` (validation, per type).
   Pick one idea.
2. Edit, then `git commit -am "<description>"`.
3. Run the experiment. If it runs over 15 minutes, kill it and log a crash. If it crashes,
   fix trivial mistakes and rerun once; otherwise log the crash, revert, and move on.
4. Log the row in results.tsv.
5. Keep the commit if the score improved, otherwise `git reset --hard HEAD~1`.
6. Repeat until the budget is spent.

## Budget

Stop after **40 experiments or 6 hours**, whichever comes first, or when the human
interrupts. Do not stop earlier to ask whether to go on. At the end, write
`alg3/runs/autoresearch/<tag>/SUMMARY.md` with:

- the baseline and the best score
- the kept commits, in order, each with its score change
- what did not work

Leave the branch as it is: the human decides what goes into main.

## Second track: edges (a separate session and worktree)

The same loop, on `alg3/edges.py` only: the learned edges added on top of a parsed graph,
namely a keep/drop filter for the parser's own edges and the definition -> user edges.
Graphs of the 160 train+val papers (alg3, current parser) are in
`alg3/runs/val_graphs/alg3_v2b/`; make them once if missing with
`python3 alg3/analyze.py --rules-dir extractors/rules/silver_v6__sentence_tagger__2026-10 --name alg3_v2b --parse-train`.

    timeout 900 python3 alg3/edges.py train --graphs alg3/runs/val_graphs/alg3_v2b \
        --out alg3/runs/autoresearch/<tag>/edges > alg3/runs/autoresearch/<tag>/run.log 2>&1
    grep "^\[val\] threshold" alg3/runs/autoresearch/<tag>/run.log

That line reads `[val] threshold T (best OOF F1 <oof>): val F1 <val>`. Both numbers are the
pooled edge F1 of the whole graph against the Level-1 silver (`src/LLMVersion/edge_metrics.py`):
`oof` covers the 120 train papers, out-of-fold, and `val` the 40 validation papers.
**score = (oof + val) / 2**, with the same keep rule. A run takes about 9 minutes.

- You may change in `alg3/edges.py`: candidates, the clues of both models (`cand_features`,
  `pairs_of`, `parser_edge_rows`), the definiendum model, regularisation, threshold grids,
  and new learned edge kinds (e.g. result -> X).
- You must NOT change the labels and the scoring: `_level1_ref`, `paper_pairs` and
  `filter_data` labelling, `curve_f1`, `parser_f1`, the `EM.score_paper` calls, and
  anything in `src/`. Do not touch `alg3/features.py` or `alg3/train.py` in this track.
- `add_edges` / `filter_edges` must still work from model.json alone, without scikit-learn.
  Keep the equation `parent_id` handling in `filter_edges`, which the viewer relies on.
- Log to `alg3/runs/autoresearch/<tag>/results.tsv`, with the same columns.

## Running it

In a terminal inside the worktree, with Claude Code as the agent:

    claude -p "Read alg3/doc/program.md and follow it: the <nodes|edges> track. Tag: <tag>." \
        --model opus --effort medium \
        --allowedTools "Read" "Edit" "Write" "Bash(python3:*)" "Bash(timeout:*)" "Bash(git:*)" "Bash(grep:*)" "Bash(cat:*)" "Bash(tail:*)"

Alternatively, paste the same line into an interactive session. A node experiment takes about
6 to 7 minutes and an edge experiment about 9. The edge training uses one core, so the two
tracks can run side by side, each in its own worktree.
