# T-OPEN — Open-Problem Resolution: state & first results

**Task.** Was an open problem / conjecture stated in paper A actually settled by a
theorem in a *different, later* paper B? Find such cross-paper resolutions over the
100K arXiv corpus.

## Pipeline (finished, runs end-to-end)

1. **Sweep — `sweep_open.py`** (CPU, no cost). Indexes every `open_problem` /
   `conjecture` node as a query and every `theorem/lemma/prop/corollary/claim` as a
   candidate; ranks by math-aware token-Jaccard, enforcing *different paper* and
   *candidate.year ≥ problem.year* (a solution can't predate the problem). Retrieval
   tokenizes the real math (`clean_latex_to_text(raw_latex)`), not the `[MATH]`-masked
   text — this was a key fix; masking had collapsed all formulas to one token.
2. **Triage — `triage_open.py`** (CPU, no cost). Filters the sweep to a reviewable
   shortlist: min score, month-level temporal gate, per-problem dedup, and an optional
   cross-category filter. Short/symbolic statements are *flagged for context*, not dropped.
3. **Judge — `batch_o4.py`** (Opus). For each shortlisted pair it locates both nodes in
   their original `.tex` and sends the surrounding text (the statement + the prose that
   reveals intent, e.g. "we now settle the conjecture of …") to the model, which returns
   VERDICT (YES/NO/PARTIAL), SAME_OBJECT, and a justification.
4. **Citation-novelty gate — `--citations`** (S2). Over the YES/PARTIAL survivors only:
   does B cite A? Separates a *known* resolution (B cites A) from a candidate
   *undiscovered* one (neither cites). **Pending a Semantic Scholar API key** (rate-limited
   without one) — so the `b_cites_a / a_cites_b / novel` columns are not yet filled.

## Run over the 100K corpus

- Sweep emitted **~300,204 candidate problem→theorem pairs** (Jaccard ≥ 0.10);
  **~15,062 distinct conjecture/open-problem statements** had at least one candidate;
  ~206,350 pairs were cross-category.
- Triage shortlist (cross-category, score ≥ 0.5, ≤ 3 theorems/problem): **166 pairs /
  104 distinct problems** → `runs/triage_top_raw.csv`.
- Judged all 166 with Opus + surrounding-`.tex` context → `runs/o4_verdicts_all.csv`:
  **154 NO, 7 YES, 5 PARTIAL**. 17/20 of the top pairs located both statements in `.tex`.

## The 5 resolutions found (YES/PARTIAL + same object + full context)

| Problem (A) | Resolution (B) | Verdict | Status |
|---|---|---|---|
| `1501.03489` (Friedl–Tillmann marked-polytope conj., GR) | `1912.04650` (AT) | YES | **known** — B cites A |
| `1310.5682` (Christensen–Wang ghost-number bounds, RT) | `1502.05727` (GR) | PARTIAL | **known** — B cites Christensen–Wang |
| `1301.5740` (ghost number of kG, AT) | `1502.05727` (GR) | PARTIAL | **known** — same result |
| `1006.0205` (inverse Gowers conjecture GI(s), NT) | `1608.04127` (CO) | YES | known in literature (proof attributed to Green–Tao–Ziegler) |
| `1503.04675` (maximal-green-sequence subquiver conj., CO) | `1804.00479` (RT) | YES | **to verify** — B gives a counterexample; no explicit cite seen in the window |

**Reading:** 3 of 5 are re-discoveries of documented resolutions (validates the method —
the pipeline correctly re-finds real, cited resolutions). The inverse-Gowers one is a known
theorem. The maximal-green-sequence pair (a *disproof by counterexample*) is the one
without a visible A→B citation and is the candidate to check once the citation gate runs.

**No confirmed *undiscovered* resolution yet** in the top-166 — expected, since genuine
undiscovered resolutions are rare and won't cluster at the top of a surface-similarity
ranking. Next: get the S2 key to run the novelty gate, judge deeper than the top-166, and
relax the cross-category filter (most real resolutions are same-field).

Data: `runs/triage_top_raw.csv` (shortlist), `runs/o4_verdicts_all.csv` (all 166 verdicts).
