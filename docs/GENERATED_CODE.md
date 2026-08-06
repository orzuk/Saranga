# Generated code in this repo

About half the Python here is not hand-written. Knowing which half is the
difference between a useful repo review and a misleading one.

| | files | lines |
|---|---|---|
| tracked `.py` | 382 | ~122,600 |
| **generated** (distillation output) | **171** | **~58,800** |
| hand-written | 211 | ~63,800 |

## What is generated

`distilled_rules.py`, written by the distillation pipeline
(`scripts/silver_distillation_sequential.py`, `src/LLMVersion/distillation_analysis.py`):

```
src/LLMVersion/<type>_eval/distilled_rules.py        one per structure type
src/LLMVersion/merged_eval_*/groups/*/               merged pools
src/LLMVersion/merged_eval_*/snapshots/step_*/       per-step trajectory
```

## Why it is committed

It is the record of what the extractor actually ran. A reported P/R/F1 is only
reproducible if the exact rule set that produced it is recoverable, and the
snapshots preserve how the pool evolved step by step. That is worth the size.

## What NOT to conclude from it

Analyses of this repo keep rediscovering the same false alarms:

- **Duplicate filenames are intentional.** Every structure type has its own
  `distilled_rules.py`. Fifteen of them are byte-identical. That is the
  generator emitting the same pool for types whose rules have not diverged —
  not copy-paste.
- **Identical function bodies across these dirs are not clones** in the
  refactor sense. Do not "unify" them; the next run overwrites them anyway.
- **LOC totals are dominated by it.** Any "the repo is 122k lines" claim is
  really "64k lines of code plus 59k lines of output".

Edits here do not survive: the next distillation run overwrites the file.
Change the generator, not the output.

## For tooling

`.gitattributes` marks these paths `linguist-generated=true`, so GitHub keeps
them out of language stats and collapses them in diffs.

Scripts that walk the tree should skip them. The predicate used throughout the
repo's own analyses is:

```python
def is_generated(path: str) -> bool:
    return ("/snapshots/" in path
            or "_eval/" in path
            or "merged_eval" in path)
```
