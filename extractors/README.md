# extractors/

One directory per **extractor** — a configuration you can point the pipeline at
to turn a paper's `.tex` into unified JSON. Two kinds, same interface:

```
extractors/
├── llm/     <model>__<prompt-version>/      an LLM + a frozen rendered prompt
└── rules/   <corpus>__<algorithm>__<date>/  a distilled regex rule set
```

## Why these live outside `src/`

`src/` is code a human writes, reviews as diffs, and fixes in place. Everything
here was produced by a program: an LLM proposed the rules, a pruning script
edited them, and the loop rewrote the files once per training paper — there are
17 near-identical snapshots of `groups/definition/distilled_rules.py` in one run
directory. A file where no rule survives one iteration by name is not source you
maintain; it is the **learned parameters of the student extractor**.

That they happen to be `.py` regexes rather than a tensor of floats is an
implementation detail of the representation. The test that settles it: you
cannot fix a bug here by editing the file, because the next `aggregate` call
overwrites it. You fix the generator (`scripts/silver_distillation_merged.py`)
and re-distil.

They are still **tracked in git**, unlike ordinary build output — LLM
non-determinism means re-running produces a *different* rule set, and the v3 run
cost $14.57. These are checkpoints you cannot regenerate byte-for-byte, so they
must be kept. Just not in the source tree.

## Every extractor has two files

| file | for | holds |
|---|---|---|
| `README.md` | you | what it is, why it exists, caveats worth a sentence |
| `recipe.json` | scripts | exact config, the train paper list, hashes |

The split matters. A README saying "trained on 60 papers" is how you end up not
knowing *which* 60 — which is precisely the question you need answered before
quoting any held-out number.

### `recipe.json` — rule extractor

```json
{
  "extractor_id": "silver_v5.1__greedy_m1__2026-06",
  "kind": "rules",
  "made_from": ["opus-5__v5.1"],
  "train": {
    "corpus": "corpus/silver/opus-5__v5.1",
    "split_file": "corpus/silver/split_opus5.csv", "split": "train",
    "summary": "60 of 200 v5.1 papers, stratified 3/category",
    "n_papers": 60, "papers": ["1003.1038v1", "..."], "order": "worst-first"
  },
  "algorithm": {
    "selection": "per_rule_fdr",        // or backward_greedy_f1_lambda, subset_selection
    "alpha": 0.5, "match_mode": "m1", "match_metric": "containment",
    "threshold": 0.7, "integrate": "full_csv"
  },
  "teacher_model": "claude-sonnet-4-6",
  "rules": {"groups": {"definition": 30, "...": 0}, "n_patterns": 80,
            "sha256": {"definition": "71719b07…"}},
  "cost": {"llm_calls": 134, "usd": 14.57},
  "git_sha": "c509465"
}
```

### `recipe.json` — LLM extractor

```json
{
  "extractor_id": "opus-5__v5.1",
  "kind": "llm",
  "model": "claude-opus-5",
  "prompt": {"template": "scripts/opus_extract_prompt_v5_1.md", "version": "v5.1",
             "rendered": "scripts/opus_extract_prompt_v5_1_rendered.md",
             "rendered_sha256": "100e6cf6fdbb3aea"},
  "schema": {"node_types": 18, "edge_types": 7, "granularity": "with_proof_steps"},
  "run": {"corpus_dir": "corpus/silver/opus-5__v5.1", "n_papers": 200,
          "papers": ["1001.2291v2", "..."]}
}
```

## The three fields that earn their place

**`train.papers`** — the list, not a count. It is the only way to check that a
held-out score is honest:

```bash
jq -r '.train.papers[]' extractors/rules/<id>/recipe.json | sort > /tmp/train
comm -12 /tmp/train <(ls corpus/silver/opus-5__v5.1 | sed 's/.json//' | sort)
```

Ranges and indices do not work here. The v3 run used
`paper001–007, 009, 010, 011, 008, 012–016, paper450` — non-contiguous, and out
of order because `--order worst-first` controls training order deliberately.
Indices also have no fixed referent: v5.1 uses arXiv ids, older corpora use
`paperNNN`, and any index shifts the moment a paper is added. The explicit list
for 60 papers is 935 bytes against a 3.9 MB run directory.

**`algorithm.selection`** — the axis the variants differ on. `per_rule_fdr` (what
shipped) vs `backward_greedy_f1_lambda` (docs/methods) vs `subset_selection`.
Without it, three directories differ by name alone.

**`rules.sha256` + `n_patterns`** — settles "which extractor produced this
output". The promoted set is 80 patterns; if a result claims 400+, it did not
come from here.

## Comparing algorithms fairly

The LLM proposes the rules, so two runs of the *same* algorithm on the *same*
papers give different rule sets. To compare selection algorithms, generate the
candidate pool **once** at `alpha=1.0` (nothing pruned) and run every selection
over that pool — `eval_distill_heldout.py` already does this. Then the only thing
varying is the selection rule, the comparison is exact, and the λ-frontier costs
no model calls.

Record it: extractors sharing a `"pool"` id are exactly comparable; extractors
that do not are not.

## Running an extractor

```bash
python3 src/run_pipeline.py --operations parse --extraction-mode rules \
    --rules-dir extractors/rules/<id> \
    --tex-dir <abs path to staged .tex> \
    --out-dir corpus/silver/rules__<id>
```

`--rules-dir` accepts either layout: an extractor directory (whose root
`distilled_rules.py` re-exports from `groups/`), or any directory holding
`<type>_eval/distilled_rules.py`. Omitting it uses `src/LLMVersion/`, i.e.
whatever the production symlinks currently point at.

The parser prints what it loaded — check this line before trusting any output:

```
[INFO] distilled rules: merged_eval_silver_001_011_v3, 88 pattern(s) across 5 group(s)
```

**Staging note.** `parse_batch.py` groups `.tex` files by parent directory and
picks one "main" file per directory. Given a *flat* directory it silently parses
exactly one file and reports success. Stage one directory per paper:

```bash
for f in corpus/silver/tex_pool/*.tex; do
  id=$(basename "$f" .tex); mkdir -p "out/silver_tex_staged/$id"
  cp "$f" "out/silver_tex_staged/$id/$id.tex"
done
```

## Naming

`<corpus>__<algorithm>__<date>` for rule extractors, corpus first so that
everything trained on the same papers sorts together — which is the grouping you
want when checking contamination. `<model>__<prompt-version>` for LLM
extractors, matching the existing `corpus/silver/` convention.

The three directories currently in `rules/` keep their legacy names
(`merged_eval_silver_001_011*`). Those names are misleading: `001_011` reads as
"papers 1–11" but the v3 run covered 17 papers ending at `paper450`, and `_v3` is
a revision counter, not a rule version. Their `recipe.json` carries the truth.
Rename on the next distillation run rather than breaking existing references.
