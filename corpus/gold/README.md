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

```bash
python scripts/build_gold_corpus.py
```

Idempotent, offline. Inputs: root `gold/*.json` and
`$SARANGA_DATA_ROOT/tier1/*_*.json` (left untouched — this is a mirror).

See `corpus/silver/README.md` for the silver corpus.
