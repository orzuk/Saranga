# Prompts

Canonical catalog of every LLM prompt actively used by SARANGA code. One
latest version per task; older versions are removed (use git history if
you need to recover them).

## Loaded automatically by

| Prompt | Loader | Purpose |
|---|---|---|
| `<type>_prompt.txt` (12 files) | `src/LLMVersion/math_paper_parser.py:1832` | Per-node-type extraction templates fed to the LLM extractor (`parse_batch.py`). Types: algorithm, claim, conjecture, corollary, definition, lemma, open_problem, problem, proof, proposition, table, theorem. |
| `method_e_judge.txt` | `src/discovery/method_e/judge.py:load_prompt` | LLM-as-judge for Method E retrieval candidates. Six-way RELATIONSHIP taxonomy + YES/MAYBE/NO verdict. |

## Used by humans / agents (not auto-loaded)

| Prompt | Used by | Purpose |
|---|---|---|
| `method_e_pair_review.txt` | Hand-review agents (general-purpose Claude Code agents) | Deep verification of a single (open-problem, candidate-theorem) pair. Reads both arXiv papers, returns RELATIONSHIP / VERDICT / ACKNOWLEDGMENT / HEADLINE assessment. Stricter than the bulk LLM judge. |
| `alignment.md` | Manual cross-paper alignment runs | Latest version of the Opus alignment prompt (was `opus_alignment_prompt_v2.md` in scripts/). Used to build Benchmark 2 pair-alignment graphs. |

## File naming convention

- `*_prompt.txt` — Yaron's per-type extraction templates. Filenames are
  load-key-coupled: `math_paper_parser.py` builds the path as
  `prompts/<type>_prompt.txt`. Don't rename without updating the loader.
- `method_e_*` — Method E pipeline prompts.
- `alignment.md` — alignment / Benchmark 2 prompt.

## Versioning

Only the latest version of each prompt is checked in. Updates land
in-place; if you need to recover an older version, use `git log -- <file>`
and `git show <commit>:<path>`.

When making a non-trivial revision to an auto-loaded prompt, bump the
`prompt_version` string in the loader code (e.g.
`MethodEConfig.judge_prompt_version`) so the LLM-judge cache invalidates
prior judgments cleanly. Sqlite cache keys include the version tag.

## Adding a new prompt

1. Create the file in this directory.
2. Add a row to the table above with its loader / purpose.
3. If it should be auto-loaded by code, write the loader to read from
   `<repo_root>/prompts/<name>.txt` (the canonical pattern; see existing
   loaders for examples).
