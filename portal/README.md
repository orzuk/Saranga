# Authomathics Database — portal v0.1

This directory holds a static web app that lets you browse the extracted
knowledge graphs of math / CS papers in the Authomathics
dataset.

It is **temporary**. The portal lives here under `portal/` only so we can
preview it on GitHub Pages while iterating. The production database UI
will move to a Hugging Face Space (`sdk: static`).

## What you'll see

- **Single papers**, three tiers
  - Tier 1 — 10 manually curated gold extractions
  - Tier 2 — silver-tier Opus extractions from the alignment benchmark
    (the repo ships a 30-paper sample of the full 270; see below)
  - Tier 3 — a future 100-paper sample drawn from a 100K math/CS pool
    (placeholder only in v0.1)
- **Pair alignments** — cross-paper match annotations, filterable by
  pair-level relation type (EXT / AP / PR / BI / CF / SM / NEG)

## Viewing it locally

The portal is fully static, so any HTTP server will do:

```bash
cd portal
python3 -m http.server 8000
# then open http://localhost:8000/
```

## Viewing it via GitHub Pages

In the repo Settings → Pages, set:

- Source: **Deploy from a branch**
- Branch: **main**, folder: **/portal**

GitHub will publish to `https://<user>.github.io/Authomathics/`.

(For a tighter URL — e.g., `…/portal/` — leave the folder as `/` and
adjust the link, but the configuration above is the simplest.)

## Adding more tier-2 papers

The repo intentionally only ships a 30-paper sample of the 270 silver
extractions. To preview the full set locally:

```bash
# Drop your silver_opus_4_7_final_scheme_with_steps.json files into
# data/tier2/, named like paperNNN.json (the URL ?id= must equal the
# filename stem):
cp /path/to/paper042/silver_opus_4_7_final_scheme_with_steps.json \
   portal/data/tier2/paper042.json

# Then rebuild the manifest:
cd portal && python3 build_manifest.py
```

Same idea for `tier1/`, `tier3-sample/`, and `pairs/`.

## What's in v0.1

- Landing page with three tier cards plus a smaller "pair alignments" card
- Tier list pages with text search + sortable columns
- Paper viewer (Overview / Nodes-by-type / Raw JSON tabs)
  - Accepts both the simple `{metadata, nodes, edges}` schema and the
    v2 `{title, blocks, relations}` schema
  - KaTeX auto-render walks the DOM and renders `$..$` / `$$..$$`
- Pair viewer with color-coded match-type pills (exact / analogous / none)
- `build_manifest.py` to regenerate the index

## What's deferred (NOT in v0.1)

- Cytoscape graph view of nodes + edges
- Full-text Lunr index
- Full tier-3 manifest (the 100K dream-scale pool)
- Alignment-aware cross-paper view (deep links from a pair into both
  papers' node cards)
- Per-section filters / origin filter / tag-cloud filters

## Repo layout

```
portal/
  index.html
  papers_tier{1,2,3}.html
  pairs.html
  paper.html              # ?tier=N&id=PAPER_ID
  pair.html               # ?id=PAIR_ID
  data/
    manifest.json         # built by build_manifest.py
    tier1/                # 10 gold JSONs (committed)
    tier2/                # 30 silver JSONs (sample of 270; committed)
    tier3-sample/         # empty placeholder
    pairs/                # 80 alignment JSONs (committed)
  js/                     # common.js, index.js, list.js, paper.js, pair.js
  css/styles.css
  vendor/katex/           # KaTeX 0.16.11 (CSS + JS + auto-render + fonts)
  build_manifest.py
```

KaTeX is vendored (~1.4 MB) so the portal works offline and doesn't
depend on a CDN. Same intent on Hugging Face Spaces.
