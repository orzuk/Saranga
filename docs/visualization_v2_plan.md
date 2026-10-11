# Paper-graph viewer v2: plan

Status: plan, 2026-10-11. The current viewer (`src/visualize_annotation.py`,
"classic") stays as it is and stays the default until v2 passes the acceptance
checks below.

## Why

The classic viewer draws the graph once, in Python (matplotlib), into a fixed
SVG inside the HTML. The browser can click, zoom and hide boxes, but cannot move
them: hiding a group leaves holes and long edges, there is a blank band for the
hidden foundation boxes, nothing can be collapsed, and a 700-node paper is one
huge picture. User studies put the limit of a readable node-link view at about
50 nodes (dense) to 100 (sparse) (Yoghourdjian et al. 2020).

v2 puts the graph DATA in the page and computes the layout in the browser, on
load and after every change, so views can be coarse, filtered or focused.

## What a user gets

- One self-contained HTML file per paper, as now (`graphs_v2/<id>.html`), next to
  the classic one (`graphs/<id>.html`), with a link between the two.
- Levels, chosen by the reader (default by size):
  - **Overview** (default above 50 top-level nodes): one box per section, edge counts
    between boxes; click a box to open it in place.
  - **Results**: definitions and results, each proof folded into its result.
  - **Full**: every top-level node; a proof opens to its steps, one level at a
    time (Lamport-style).
- Focus modes: **path to the main results** (what they depend on, redundant
  edges removed); **neighbourhood** of a selected node (what it uses, what uses
  it, expandable hop by hop); **search**; hover highlights a node's edges.
- Kept from classic: top-to-bottom foundations-to-results direction, type
  colours, edge styles and legend, the toggles (now re-laying out), the side
  panel with MathJax statements.

## Architecture

- **Python builder** (`src/graph_view/build.py`): reuses the classic data
  preparation (`_normalize_schema`, `_classify_and_merge`, `merge_proofs`,
  `split_cycle_edges`, foundation links, macros, side-panel text), and writes
  one JSON object per paper: nodes (id, type, label, short text, section,
  parent, confidence, origin), edges (type, confidence, backward), sections,
  and precomputed helpers (proof-to-result folding, main-result candidates,
  transitive reduction).
- **Viewer** (`src/graph_view/viewer.js`, `viewer.css`): Cytoscape.js with the
  ELK "layered" layout (compound nodes for sections and proofs) and the
  expand-collapse extension (summary edges between collapsed groups).
- **Page** = template + the paper's JSON (about 0.05-0.3 MB) + the viewer. The
  libraries (about 2 MB) sit ONCE in a shared `lib/` folder next to the pages:
  offline, and about 10x smaller than classic pages (median 1.9 MB, 454 MB for
  200 papers, because each holds a drawn SVG). `--standalone` inlines the
  libraries for a single file to share; `--libs cdn` loads them online.
- Entry points: `python3 src/graph_view/build.py <json...> -o <dir>`, and in
  `run_pipeline.py` an option `--viewer classic|v2|both` (default `classic`
  until acceptance, then `both`).

## Phases (each ends usable; classic untouched throughout)

| | Phase | Delivers | Effort |
|---|---|---|---|
| 0 | Classic quick fixes | no blank band, opens fitted (talk-ready) | ~1 h |
| 1 | Data + minimal v2 | full graph, ELK layout, colours, legend, side panel, toggles that re-lay out | ~1 day |
| 2 | Levels | proofs ⊃ steps and sections ⊃ nodes as collapsible groups; overview default above 50 nodes | ~1 day |
| 3 | Focus modes | path to main results, neighbourhood, search, hover, transitive reduction | ~0.5–1 day |
| 4 | Scale and batch | the largest papers (1,700 nodes), all 200 silver graphs, portal hook, docs, tests | ~0.5 day |

## Acceptance checks (before v2 becomes a default)

1. All 200 silver papers render in headless Chrome with no script error.
2. 95% open in under 3 s; the largest in under 10 s.
3. The overview of the 5 largest papers shows at most ~50 items.
4. A side-by-side check on 10 papers of different sizes: nothing the classic view
   shows is missing from the v2 full level.

## Risks

- ELK has known problems routing edges that cross group boundaries; fallback:
  layered layout without groups at the full level, fCoSE for the overview.
- Layout time on very large papers; fallback: precompute positions in Python
  for papers above a size, or open those at the overview level only.
- What a "main result" is: start with the paper's named/numbered theorems that
  nothing else in the paper uses, plus any marked main in the silver; review.

## Decisions (2026-10-11)

- Libraries: one shared `lib/` folder per graph folder (`--standalone` for a
  single self-contained file).
- Overview is the default above 50 top-level nodes.
- Node size by importance: the viewer reads an `importance` field when the
  graph has one (a future extraction prompt may ask for it, as Tao's viewer
  does); otherwise a proxy from the graph itself: how much of the paper builds
  on the node (its descendants), boosted for named and numbered results. The
  same proxy proposes the main results for the path-to-main-results view.
