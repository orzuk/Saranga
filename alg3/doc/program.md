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

    timeout 1800 python3 alg3/train.py --class-weight sqrt --stack \
        --out alg3/runs/autoresearch/<tag>/run > alg3/runs/autoresearch/<tag>/run.log 2>&1
    grep "train OOF F" alg3/runs/autoresearch/<tag>/run.log            # -> oof
    rm -rf alg3/runs/val_graphs/<tag>_run
    python3 alg3/analyze.py --rules-dir alg3/runs/autoresearch/<tag>/run --name <tag>_run \
        --top 0 --show 0 | head -2                                     # -> val

`oof` is `train OOF F=<oof>` from the training log: thresholds tuned on out-of-fold
predictions for the 120 train papers, the tagger's prose predictions plus the base parser's
counts, m1g, pooled.

**`val` is the END-TO-END node F1**: the exported extractor run inside the real parser on the
40 validation papers, every node of the graph against the Level-1 silver, m1g, pooled (the
`nodes m1g pooled ... F1` number of `analyze.py` graph mode; about 1 minute). Do NOT use the
`val {... 'F': ...}` number of the training log: it scores the tagger's prose predictions
alone and ignores how the parser merges them with its own nodes. In October 2026 a span model
raised it by +0.009 while the end-to-end F1 fell by 0.002.

**score = (oof + val) / 2.** Use the OOF number, which covers 120 papers, so that you don't
chase noise in 40 validation papers.

**Noise floor first.** Before any idea, run the baseline three times with different fold
seeds (`--seed 0/1/2`; add the option to train.py if it is missing). Set
**bar = max(0.001, 2 x the spread of the three scores)** and log it. Keep a change only when
the score rises by at least the bar. A tie with less code is a keep: simpler is better.
Runs of structural changes may take up to 30 minutes (`timeout 1800`).

You may change train.py's options and defaults (C, class weights, `--stack`, `--min-count`,
`--classifier lr|gb`, span model settings) as well as the code.

## Explore, then exploit

Small tweaks of existing clues and settings (thresholds, C, min-count, one more cue phrase)
were tried in the first round (October 2026) and moved the score by about 0.001. This round
is for **structural** changes, which change what the tagger can see or produce:

- **First half of the budget: explore.** Each experiment is one bold, different idea, not a
  variant of the previous one. No hyperparameter tuning in this half.
- **Second half: exploit.** Refine and combine the ideas that won, and tune them.

**Round 3 findings (October 18), read these first.**

- **The thresholds are tuned on the wrong objective.** `tune_tau` picks each type's threshold by
  a matcher that sees only the tagger's prose predictions plus constant base-parser counts. End
  to end (the real parse, every node matched at once against the Level-1 silver) these choices
  cost ~0.006: the v2b model retrained today scores 0.715 end to end with its own thresholds and
  0.721 with the thresholds of the October-12 release. A span model (round 2) raised the training
  number by +0.009 while the end-to-end F1 fell. Top idea: tune the thresholds (and anything else
  tuned on OOF) against an end-to-end OOF objective: for each train paper, the tagger's OOF
  predictions together with the base parser's own nodes (the non-`distilled` nodes of
  `alg3/runs/val_graphs/<name>/<pid>.json`, made with `analyze.py --parse-train`), matched with
  `node_metrics` m1g one-to-one against the Level-1 silver nodes of the scored types
  (`edge_metrics.level1`, `distill_common.TYPES`). Precompute candidate pairs once; check that
  it reproduces the end-to-end val number of the release within ~0.002 before trusting it.
- 95% of the missed silver nodes are prose sentences with no prediction at all (definition,
  claim, remark). Cited results: of the train sentences that cite a result ("proved in [12]"),
  the silver makes only 17% theorem nodes (53% nothing) — learn which ones it keeps.
- Tried, about +0.001 end to end (noise): a "twin" clue (another sentence opening with the same
  three tokens got a high first-pass probability). Nodes inside proofs: only ~5 on val.

Where the errors are (`python3 alg3/analyze.py --rules-dir ... --name ...`, graph mode, VAL),
largest first, with structural ideas to try (counts from round 2; "inside" was then measured by
shared words and overstated: re-run analyze.py):

1. **Prose sentences the tagger never fires on** (~530 on VAL: definitions, claims, remarks).
   Most get P(none) ~0.9. Ideas: paragraph- or section-level context; a sequence decoder over
   a paper's sentences (e.g. Viterbi over types with learned transitions) instead of
   independent decisions; a separate "is this a node" detector before the type model.
2. **Nodes inside proofs and other environments** (~120 missed definitions and claims inside
   proofs; ~50 spurious). The tagger only sees prose sentences outside environments. Idea:
   an extra candidate stream of sentences inside proofs, built in alg3 (data.py / features.py
   / runtime.py), with its own clues.
3. **Granularity:** about 100 silver definitions sit inside one predicted multi-sentence
   definition. Ideas: a split decision between sentences of a span; span model per type.
4. **Wrong type** (~190): proof/claim, claim/definition, remark/definition confusions.

## What you may change

- `alg3/features.py`: the clues of a sentence. Add, remove or reshape them, e.g. cue phrases,
  context windows, section and environment cues, bucketings, or conjunctions of clues.
- `alg3/train.py`: the model and training: classifier, regularisation, class weights,
  stacking, span model, decoding, and the threshold search space.
- `alg3/data.py`: **which sentences are candidates** (e.g. sentences inside proofs), and
  `alg3/runtime.py` to match at parse time. The silver labels and the scorer must stay as
  they are: a new candidate is matched to the silver nodes by the same `Scorer` as all others.
  After changing data.py, rebuild the cache (`python3 alg3/data.py --splits train,val
  --tex-dir corpus/silver/tex_staged`, about a minute; tex dir: copy or symlink it from the
  main checkout) and re-run the baseline before comparing.
- When `FEATURES_VERSION` in features.py no longer describes the clues, bump it.

## What you must NOT change

- The scoring: `evaluate`, `tokens`, `analyze.py` (the end-to-end val metric), plus anything
  under `scripts/` and `src/`. Exception (round 3): you MAY give `tune_tau` / `fast_eval` /
  `candidates` an end-to-end objective (see the first idea below); the val metric and the
  silver stay as they are. The assert in
  `tune_tau`, which checks that the fast path agrees with the full decode, must keep
  passing.
- The labels: the silver (`corpus/silver/`), the split (`corpus/silver/split_v6_6-2-2.csv`),
  and how `data.py` matches silver nodes to sentences (it uses `scripts/distill_units.py`,
  which you must not change). `data.py` must keep refusing test papers.
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
3. Run the experiment, in the FOREGROUND (one blocking command; a non-interactive session
   ends when your turn ends). If it runs over its time limit, kill it and log a crash. If it crashes,
   fix trivial mistakes and rerun once; otherwise log the crash, revert, and move on.
4. Log the row in results.tsv.
5. Keep the commit if the score improved, otherwise `git reset --hard HEAD~1`.
6. Repeat until the budget is spent.

## Budget

Stop after **25 experiments** (the noise-floor baselines not counted), or the budget the
launch prompt gives, or when the human interrupts. Do not stop earlier to ask whether to go on. At the end, write
`alg3/runs/autoresearch/<tag>/SUMMARY.md` with:

- the baseline and the best score
- the kept commits, in order, each with its score change
- what did not work, and which explore ideas looked promising but need more work

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

- Round-3 edge findings: of the missed result -> proof / result -> X / equation -> X edges whose
  two endpoints were found, > 90% have no textual reference in the target (no \\ref, no
  "Lemma 3", no "the above"): mostly not learnable from text. Small fetchable sets: ~37 where the
  target \\refs the source's label but no edge exists; ~10 prose proofs (tagger-found) never
  attached to the preceding result; edges to cited results (missing endpoints).
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
