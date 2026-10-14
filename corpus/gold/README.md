# Gold corpus — human-annotated ground truth, organized

Parallel structure to `corpus/silver/`, for the **research gold** (human
ground-truth) papers plus the baseline model extractions of those same papers.
The `class_52017/` student golds are intentionally **not** included here.

## Layout

```
corpus/gold/
  metadata.csv                 # ONE row per extraction
  README.md
  <model>__<prompt>/           # one dir per annotator/model
    prompt.md                  #   provenance note (gold has no LLM prompt file)
    <arxiv_id>.json ...
  tex/<arxiv_id>.tex
```

Here the **paper identity is the arXiv id** (gold files are named by arXiv id),
so no lookup is needed. Groups:

| Directory | Papers | `role` | Meaning |
|---|---|---|---|
| `human__gold/` | 5 | gold | root `gold/` research annotations (`objects/relations` schema) |
| `human__manual/` | 10 | gold | `tier1` human ground truth (`nodes/edges` schema) |
| `anthropic__tier1/` | 10 | baseline | Anthropic extraction of the tier1 gold papers |
| `openai__tier1/` | 10 | baseline | OpenAI extraction of the same papers |
| `rules__tier1/` | 10 | baseline | rule-based extraction of the same papers |

**45 extractions across 15 distinct papers**: 15 human-gold rows + 30 model
baselines (kept so the "organize by model/prompt" view lets you compare each
model's extraction against the human gold on identical papers). Filter
`role == gold` (or `annotator == human`) for ground truth only.

## metadata.csv columns

`paper_id, arxiv_id, role, model, prompt_version, annotator, schema, title,
n_nodes, n_edges, json_path, tex_path, has_tex`

- `role`: `gold` (human) vs `baseline` (model/rule extraction of a gold paper).
- `schema`: `objects_relations` (root gold, legacy) vs `nodes_edges` (tier1).
- tier1 provider JSONs carry no model/prompt metadata, so `model` is the
  provider token from the filename and `prompt_version` is `tier1`.

## Rebuilding

The corpus was built once by `scripts/build_gold_corpus.py` (historical; removed
2026-10-14, see git history). It is not meant to be rebuilt.

Idempotent, offline. Inputs: root `gold/*.json` and
`$SARANGA_DATA_ROOT/tier1/*_*.json` (left untouched — this is a mirror).

See `corpus/silver/README.md` for the silver corpus.

## Migrated from the legacy root `gold/` (2026-08)

The repo-root `gold/` directory was folded into this one and removed, so gold
lives in exactly one place. The migration was verified **lossless by content
hash: all 40 files accounted for**.

| here | from | what |
|---|---|---|
| `human__gold/` | `gold/<id>.json` | the 5 primary human annotations (byte-identical) |
| `templates/` | `gold/<id>_manual_template.json` | **annotation scaffolds, NOT gold** — `_EXAMPLE_T1` placeholders + an `instructions` field. Kept apart so they can never be mistaken for ground truth (`role=annotation_template`). |
| `human__diagram/` | `gold/1805.11176v1_gold_from_diagram_and_tex.json` | alternative gold derived from a diagram + tex, carries `concept_registry_refs` (`role=gold_variant`) |
| `figures/` | `gold/figures/` | diagrams. The file tracked as `gold/figures/.png` (a real 305 KB image with a broken name) is now `1805.11176v1_diagram.png`. |
| `pdf/` | `gold/pdf/` | rendered paper PDFs |
| `tex_source/<arxiv_id>/` | `gold/tex/YYYY/MM/DD/tex/` | full LaTeX sources incl. tarballs, `.cls`, `.bbl`, figure PDFs |

Note `tex/` (flat, 5 files) holds just the main `.tex` per paper for quick use;
`tex_source/` holds the complete original trees.

**Consumers updated:** `scripts/run_gold_eval.sh` now defaults `GOLD_DIR` to
`corpus/gold/human__gold`. `scripts/build_gold_corpus.py` (HISTORICAL, removed 2026-10-14; in git history) —
it built this dir *from* `gold/`, which no longer exists; `corpus/gold/` is now a
canonical store, not a derived artifact.
