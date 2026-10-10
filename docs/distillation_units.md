# Unit distillation (`--alg units`)

A second distillation algorithm next to the original one (`--alg merged`), run by the
same driver, `scripts/silver_distillation_merged.py`.

## Why

On the 200-paper silver corpus the base rule parser already recovers 98.8% of the
nodes that come from LaTeX environments, with the silver's type, and finds about
15% of the nodes stated in running prose. Prose is 61% of the scored nodes
(11,010 of 18,010). Distillation is therefore about prose, and the original
algorithm is a poor fit for it:

- each rule is a whole extractor: it decides where a node starts and ends, its
  type, and where not to look, so boundaries are inconsistent with the silver's
  whole-sentence convention, and overlaps are settled by the order in which the
  teacher happened to write the rules;
- rules live in teacher-rewritten Python files, which drift between steps, and
  rewriting the files is most of the cost;
- a rule enters on positives alone and is pruned only after it has done damage.

## What a rule is

`src/prose_units.py` cuts the prose of a paper into sentences: the document body
minus environment facts, floats, the abstract and the bibliography, split at
sentence ends (outside math, not after an abbreviation), paragraph breaks and
`\item`. A display inside a sentence stays in it. On the silver corpus, a run of
up to four sentences lines up with 90-92% of the silver prose nodes (overlap >= 0.7).

A unit rule (`src/LLMVersion/unit_rules.py`) is a record:

    {"uid": 7, "type": "definition", "regex": "\\bwe\\s+say\\b", "flags": "i",
     "span": "1", "precision": 0.93}

Where the regex matches a sentence, that sentence starts a node of `type`; `span`
("1".."4", or "para" = to the end of the paragraph) says how far the node goes.
The most precise rule firing on a sentence decides, and a sentence inside an
emitted node starts no other. The same code scores rules during distillation and
applies them in the parser (through a generated `distilled_rules.py` importer
next to `unit_rules.json`), so a rule behaves identically in both.

The teacher writes only the regex. The span option is chosen from the data: the
option that best reproduces the silver spans of the cluster's nodes.

## The algorithm (`scripts/distill_units.py`)

    prepare  training papers -> sentences, silver prose nodes, and which of them
             the base parser already finds (those are not targets)
    split    the training papers into fitting papers and --val-papers validation papers
    repeat   (up to --rounds, until validation F1 gains < --stop-gain, or the budget ends)
      repair   an active rule whose precision fell below 1 - alpha is tightened
               (the teacher sees its false positives) or retired
      cluster  remaining misses grouped by the cue of their first sentence:
               (type, cue phrase or opening words, markup: \emph, bold heading,
               \cite, \item, ends with a colon); largest first; < --min-cluster skipped;
               a cluster tried once is not tried again
      propose  one teacher call: the cluster's first sentences as positives (all of
               them by default, --max-examples) and look-alikes as negatives: sentences
               with the same cue that start no node of the type and lie inside none
               (--max-negatives, default max(12, number of positives))
      refine   hill-climb, up to --max-refine steps: each step tries to tighten the rule
               on its false positives (only those a judge confirms as errors; the rest
               are likely silver misses) and to broaden it on the cluster members it
               still misses, and keeps the better version (see "accepting a rule")
               if it does not do worse on the validation papers (--val-tolerance);
               stops at a local maximum
      accept   see below; clusters are worked on --parallel at a time (their teacher
               calls overlap), but rules are accepted one at a time, in cluster
               order, each re-checked against the rules accepted meanwhile
      cleanup  retire a rule whose removal does not lower F1 on the fitting papers
    final    snapshots/step_00_base and step_NN_roundN (same layout as --alg merged),
             unit_rules.json + distilled_rules.py in --eval-dir, REPORT_units.md,
             units_summary.json, and eval_base_vs_distilled_split.py on all
             silver papers (base vs final rules, train and test)

## Accepting a rule (`--accept`)

A candidate is always scored together with the rules already accepted, so what
counts is what it ADDS: a node the base parser or another rule already finds is
neither a true nor a false positive of the new rule (the parser's merge drops
the duplicate).

- `fdr` (default), `--fdr-scope rule`: the nodes the rule adds must have a false
  discovery rate <= `--max-fdr`, on the fitting papers and on the validation
  papers where it fires at least `--val-min-fired` times, with at least `--min-tp`
  new nodes. Every rule within q keeps the whole extractor within q (the base
  parser starts at 1-6%). Refinement maximises the nodes added within that.
  `--fdr-scope overall` holds the FDR of the whole extractor instead (then
  `--rule-min-precision` keeps a few noisy early rules from spending the budget).
- `f1`: the rule must raise the overall F-beta (`--beta`, default 1) of the whole
  extractor, all silver nodes including the environment nodes the base parser
  finds, by more than `--min-gain`, and not lower it on the validation papers.
  Equivalently its own precision must exceed F/(1+beta^2) of the current
  extractor, about 0.3 at the start: the most permissive criterion.
- `precision`: the rule alone must reach `--min-precision` (the first version).

Cleanup and the stopping rule use the objective of the criterion: overall recall
for `fdr`, overall F for `f1`.

## Matching while training, and the cost levers

`--train-metric m1g` (default) matches a rule's output to the silver with the
headline metric of `src/LLMVersion/node_metrics.py`: one-to-one, overlap >= 0.7,
and a pair earns the type compatibility of its two types (`node_similarity.
type_compat`: a claim matched to a proposition counts 0.8, and 0.2 as an error).
The base parser's counts use the same metric, so what training optimises is
what the comparison reports. `--train-metric m1` is same-type only.

The teacher's cost is mostly output tokens, and most of those are its thinking:
`--effort low|medium|high|xhigh|max` (both models) limits it, `--thinking
disabled` turns it off (Haiku 5.5 only; Sonnet 5.5 always thinks). With
`--max-examples N` a proposal shows at most N members of a cluster (the largest
input). Each run records its options in units_summary.json. A full-cost run
simply leaves them out.

## Comparing extractors

`scripts/compare_distillers.py` trains and scores several arms (base parser,
fixed rule sets, this algorithm with any options, the original algorithm) on
one split (`scripts/assign_split_v6.py`, e.g. 6/2/2 papers per category), with
tables, paired bootstrap intervals and learning curves in `<out>/results/`.
`status` shows each arm's progress. Configs: `scripts/compare_configs/`.

A rule's false positives and true positives are counted with the reported
metric's own test (`match_modes`: token containment >= --threshold, same type).
A prediction of a node the base parser already finds is neutral (the parser's
merge drops it as a duplicate). The registry (`scripts/distill_registry.py`)
keeps every rule with a stable uid, its per-paper counts and its history;
nothing is deleted.

## Running it

    python scripts/silver_distillation_merged.py --alg units \
        --pilot-papers train --tex-dir <tex staged as <pid>/source/<pid>.tex> \
        --eval-dir <out> --model <teacher> [--max-llm-calls 400] [--rounds 5]

`--pilot-papers train` takes the training split from `corpus/silver/metadata.csv`;
test papers are refused unless `--allow-test-papers`. Every threshold and count is an
option (`--help`, group "units algorithm"), and each run's REPORT_units.md records them. `--resume` continues a run from
`<eval-dir>/units/` (registry, tried clusters, calls spent).

Without an API key, `PYTHONPATH=tests/stub_teacher` replaces the Anthropic client
with a stand-in that answers both algorithms' requests; it exercises the whole
pipeline (it is not a teacher: its rules key on the examples' first words).
`STUB_TEACHER_LOG=<file>` records the prompts it receives.

Offline tests: `python3 tests/test_unit_distillation.py`.

## What is not covered

- Nodes in proofs or results: by design. The silver almost never places a scored
  node inside a proof (191 of 18,010); nested environments come from the LaTeX layer.
- Prose nodes with no surface cue (most low-confidence claims and remarks).
- Edges: as with --alg merged, edges come from the parser's fixed relation builder.
