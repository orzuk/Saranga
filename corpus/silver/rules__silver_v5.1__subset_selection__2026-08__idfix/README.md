# rules__silver_v5.1__subset_selection__2026-08__idfix

The 200 v5.1 papers parsed with
`extractors/rules/silver_v5.1__subset_selection__2026-08`, named `<id>.json` so
they align one-to-one with `opus-5__v5.1/`.

**Use this one.** The sibling directory without `__idfix` was produced by the
same extractor before a parser bug was fixed, and is kept only for comparison.

## What the fix was

Distilled objects were keyed `DIST_<first letter of type><n>`, with the counter
restarting per type, and `PaperGraph.add_object` is `self.objects[id] = obj`.
So the n-th distilled proposition and the n-th distilled proof were both
`DIST_P<n>` and one silently replaced the other. Three families collided:
corollary/claim/conjecture, proof/proposition/problem, algorithm/assumption.
Which object survived depended on dict iteration order, so it varied between
processes. Fixed by keying on the full type name.

Measured across these 200 papers, old vs new:

| type | objects recovered |
|---|---|
| proposition | +56 |
| algorithm | +32 |
| conjecture | +27 |
| problem | +21 |
| claim | +11 |
| **total** | **+147** (0.46%, 77 of 200 papers) |

Nothing outside those three families moved.

## Held-out score

Rescored from these JSONs on the 140 held-out papers, pooled M3 (containment,
threshold 0.7, cover 0.7): P 0.8221, R 0.6938, **F1 0.7525**.

Appendix F quotes 0.7563, which came from scoring in memory during the parse
rather than from saved graphs. The remaining gap is **not** this bug: it is
still open, and it is on the recall side. These JSONs hold *more* extractions
than that run counted (10,759 vs 10,661) while covering *fewer* gold nodes
(7,743 vs 7,809), which points at `to_unified_dict()` (what gets written here)
storing different `raw_latex` than `to_dict()` (what the scoring path read).
Until that is settled, treat 0.7525 as the number these files reproduce and
0.7563 as the number the run reported.
