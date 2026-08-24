# Prompts

Canonical catalog of every LLM prompt actively used by SARANGA code. One
latest version per task; older versions are removed (use git history if
you need to recover them).

## Loaded automatically by

| Prompt | Loader | Purpose |
|---|---|---|
| `<type>_prompt.txt` (12 files) | `src/LLMVersion/math_paper_parser.py:1832` | Per-node-type extraction templates fed to the LLM extractor (`parse_batch.py`). Types: algorithm, claim, conjecture, corollary, definition, lemma, open_problem, problem, proof, proposition, table, theorem. |
| `method_e_judge.txt` | `src/discovery/method_e/judge.py:load_prompt` | LLM-as-judge for Method E retrieval candidates. Seven-way RELATIONSHIP taxonomy (DIRECT / GENERALIZES / SPECIAL_HARD / SPECIAL_CORNER / INDIRECT_TOOL / COUNTER / UNRELATED) + YES/MAYBE/NO roll-up. |

## Built in code, not loaded from this directory

| Prompt | Built by | Purpose |
|---|---|---|
| O4 resolution judge (`o4_resolution_ctx_v2`, `o4_resolution_v2`) | `discovery_suite/open_problems/resolution_taxonomy.py`, assembled in `batch_o4.py` / `o4_judge.py` | T-OPEN's problem→theorem resolution judge. Uses the **same seven-way RELATIONSHIP taxonomy as `method_e_judge.txt`**, rolled up to YES/PARTIAL/NO (O4's `PARTIAL` = Method E's `MAYBE`), plus a separate SAME_OBJECT axis. Kept in code rather than here because the prompt body differs per judge (context window vs. bare statements) while the taxonomy block is shared. |

## Used by humans / agents (not auto-loaded)

| Prompt | Used by | Purpose |
|---|---|---|
| `method_e_pair_review.txt` | Hand-review agents (general-purpose Claude Code agents) | Deep verification of a single (open-problem, candidate-theorem) pair. Reads both arXiv papers, returns RELATIONSHIP / VERDICT / ACKNOWLEDGMENT / HEADLINE assessment. Stricter than the bulk LLM judge. |
| `alignment.md` | Manual cross-paper alignment runs | Latest version of the Opus alignment prompt (was `opus_alignment_prompt_v2.md` in scripts/). Used to build Benchmark 2 pair-alignment graphs. |

## File naming convention

- `*_prompt.txt` — Yaron's per-type extraction templates. Filenames are
  load-key-coupled: `math_paper_parser.py` builds the path as
  `prompts/<type>_prompt.txt`. Don't rename without updating the loader.
- `method_e_*` — Method E pipeline prompts. The RELATIONSHIP taxonomy in
  `method_e_judge.txt` is mirrored in `discovery_suite/open_problems/resolution_taxonomy.py`
  for T-OPEN's O4 judge — change one, change the other.
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
