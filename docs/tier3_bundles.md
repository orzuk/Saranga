# Tier-3 bundles: how the 100K (and later all-arXiv) corpus is stored and served

Decided 2026-10-24 (Or). Code: `portal/bundle_t3.py` (writes and reads), `portal/portal_server.py`
(`t3_from_bundle`).

## Decision

- The corpus is stored on the Hugging Face dataset `saranga-project/saranga` (free for public data), not on
  Google Cloud (the portal's billing account is Yaron's) and not inside the portal container.
  The Cloud Run portal reads one paper at a time from there.
- One bundle per (category, year), not one file per paper: 100K papers give 211 bundles, 1.9 GB (422 files
  with the indexes; the per-paper JSON is 21.6 GB, the old per-month gzip bundles were 3.3 GB);
  all of arXiv about 5K bundles, about 45 GB. One file per paper would be 2.5M files, far over
  Hugging Face's ~100K files per repository. Per month would be 2,411 bundles for the 100K; per
  (category, year) keeps the count low and a paper's bundle is still found from its id alone.
- **Nothing is dropped.** The stored form is lossless; every paper is unpacked and compared with the
  original when the bundle is written.

## Format

`<cat>/<year>.json.xz` and `<cat>/<year>.idx.json`.

- Each paper's JSON is written compact (no indentation) and compressed on its own with xz (level 9,
  8 MB dictionary). The papers are written one after another, so a bundle is also a valid `.xz`
  file of all of them (`xz -dc` gives the papers' JSONs back to back).
- **Convention:** a node's `clean_text` is left out when it equals the node's `statement` (it did in
  every node sampled). A reader puts `statement` back into a node that has no `clean_text`
  (`bundle_t3.unpack` does this). A paper for which that would not give the original back exactly
  (e.g. a node with a statement but no clean_text) is stored unchanged and marked `"raw"` in the index.
- The index maps each paper id (e.g. `1504.05177v1_rules`) to `[offset, length]` in the bundle, or
  `[offset, length, "raw"]`. The year comes from the arXiv id (`bundle_key`).

Reading one paper: download the bundle's index once, then an HTTP range request for the paper's
bytes (about 25 KB), then `unpack(blob, entry)`. Measured from WSL against Hugging Face: 0.2-0.4 s.

Analysis code reads bundles through `src/discovery/common/corpus_io.py`, as it reads per-paper JSONs:
`walk(root)` yields one path per paper (`<cat>/<year>.json.xz#<id>`), `read_json` / `read_paper` /
`iter_papers` read it. So a task runs the same on a folder of JSONs or of bundles; only `--root` changes.
For all of arXiv only the bundles are kept (2.5M JSON files would strain the cluster's inode quota);
the 100K keeps its per-paper JSONs too, which the extractor's stats and validation steps read.

## Why not smaller

Measured on 60 papers of the 100K (10.1 MB of JSON as stored):

| Stored as | gzip | xz |
|---|---|---|
| as extracted (indented) | 1.21 MB | 1.01 MB |
| compact | 1.18 MB | 1.00 MB |
| compact, clean_text rule (chosen) | 1.11 MB | 0.96 MB |
| also without `statement` (lossy, rebuilt from `raw_latex`) | - | about 0.8 MB |

Compressing the papers of a bundle together instead of one by one saves only 2% with gzip and 12%
with xz, and would mean reading a whole bundle to get one paper.

The JSON is about 2.2x the size of the paper's main `.tex` (58 papers): the nodes keep about half
the paper's LaTeX (theorems, definitions and proofs; proofs are half of it), and each node's text is
stored three times (`raw_latex`, `statement`, and `clean_text`, which equals `statement`). Zipped,
the JSON is about the size of the zipped LaTeX. Writing `clean_text` only when it differs is a
change for the extractor (Yaron).
