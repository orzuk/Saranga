# Erdős-problems coverage over the Saranga corpus (T-OPEN)

**Goal.** Of the **1217** catalogued Erdős problems (statements + resolution status,
exported from [github.com/teorth/erdosproblems](https://github.com/teorth/erdosproblems)
— the repo behind [erdosproblems.com](https://www.erdosproblems.com) — plus a Wayback
scrape), determine **which are present in our parsed corpus** — i.e. some paper we
parsed states that problem as an `open_problem`/`conjecture` node — and, for the
resolved ones, whether the T-OPEN sweep already surfaced a corpus theorem that could
resolve the matched node.

**The CSV ships in this directory** as `erdos_problems.csv` (committed `ccb720a0`);
there is nothing to fetch or mount. Status split: **556 resolved / 608 open /
53 other** (`falsifiable`, `decidable`, `independent`, … — logical-status labels that
are neither). Before importing any newer export, diff it with
`erdos_reconcile.py --theirs <csv>` (stdlib-only, runs anywhere); it exits non-zero
when the files differ and prints the id / status / statement changes.

**Script:** `erdos_coverage.py` (this dir). Cheap, dependency-free rung: same
math-aware token-Jaccard the T-OPEN sweep uses
(`shared.corpus.node_norm_text(prefer_raw=True)` -> `o1_retrieve._jaccard`).
Corpus loading goes through the canonical `shared.corpus.stream_papers`
(wrapper over `src/discovery/common/corpus_io.py`) — no raw re-globbing of the
tier3 corpus.

## How it works

1. **Erdős side** — each CSV `statement` is normalized through the *same*
   pipeline as corpus nodes (`clean_latex_to_text` -> `normalize_math_text`), so
   the two token sets are directly comparable.
2. **Corpus side** — every `open_problem`/`conjecture` node (add `--match-theorems`
   to also include theorem-like nodes) becomes a token set.
3. For each Erdős problem, keep the single best-scoring corpus node. It counts as
   **covered** when that best Jaccard >= `--threshold` (default **0.25**).
4. Coverage is reported split by status (open vs resolved). For covered problems
   whose matched node also appears in the T-OPEN run outputs
   (`runs/o4_verdicts_all.csv`), the resolving-theorem candidate + verdict is
   attached.

`--resolved` statuses: `proved, disproved, solved` (+ `_lean` variants).

## Status: never yet run at scale

The script has **only ever produced numbers on a 10-row fixture** (`erdos_sample.csv`,
since removed) against a local corpus that no longer exists in that form — the
earlier write-up's headline result (Erdős #88 ↔ `paper394::CnjP44.1` at 0.800,
#3 ↔ `paper294::CnjP43.1` at 0.412) came from `portal/data/tier2_test`, which is
gone. Today `tier1` + `tier2` yield **15** `open_problem`/`conjecture` nodes, so no
local run can say anything about coverage. **Treat the 100k cluster run as the first
real measurement.**

Two defects were fixed (Aug 2026) while validating the full CSV end-to-end — both
would have hit the cluster run:

1. **NUL bytes.** The export carries 841 stray `\x00`s. Python ≤ 3.10's `csv`
   hard-errors `line contains NUL`, so on any older cluster interpreter the job
   died before doing work. `load_erdos` now strips them.
2. **Lean statuses counted as unsolved.** `RESOLVED_STATUSES` expected
   `proved_lean`; the CSV spells it `proved (lean)`. 205 resolved problems were
   being reported as open — a **351/866** split instead of the true **556/608**.
   `_norm_status` now folds the spellings, and the summary reports a three-way
   resolved / open / other split so the 53 logical-status rows stop inflating "open".

Note `load_erdos` keeps **1063 of 1217** rows: 154 have statements too short to
tokenize (147 are under 10 characters — placeholder/figure-only entries). Coverage
rates are over 1063, not 1217.

### Local sanity run (validates the path, not the science)

```
python discovery_suite/open_problems/erdos_coverage.py \
    --erdos-csv discovery_suite/open_problems/erdos_problems.csv \
    --corpus-dir portal/data/tier1 portal/data/tier2 \
    --accept-bare \
    --out discovery_suite/open_problems/runs/erdos_coverage_local.csv
```

All 1217 rows parse, all 1063 statements tokenize, the histogram prints. The four
rows it marks "covered" at the 0.25 default are **pure noise** (an Erdős problem on
group orders "matching" a category-theory corollary at 0.269) — with 15 corpus nodes
every problem's best match is noise, and a few cross the line. That is the point of
the next section.

## Running on the full 100K corpus (HUJI cluster)

The CSV is already in the repo — pull, then submit. One command:

```bash
cd /sci/labs/orzuk/orzuk/github/Saranga   # (legacy: .../Authomathics)

export ROOT=/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4
sbatch discovery_suite/open_problems/erdos_cluster.sh
```

`erdos_cluster.sh` (32G/4cpu/4h, glacier — same profile as `sweep_cluster.sh`)
knobs, all env-overridable: `THRESHOLD` (default **0.15**, deliberately low — see
calibration below), `MATCH_THEOREMS=1` for the wider theorem-node pass, `ERDOS_CSV`,
`OUT`.

### 2. Calibrate the threshold — do NOT trust the default

**The score is a max over every corpus node, so the noise floor rises with corpus
size.** A threshold tuned on a small corpus admits pure noise on a large one. The
local run makes this concrete: at `--threshold 0.15` against a **2-node** corpus,
314 of 1063 problems (29.5%) come out "covered" — all of it noise.

So the first cluster run is a **calibration run**, not the answer:

1. Submit at `THRESHOLD=0.15`. Read the score histogram + percentiles printed to
   `logs/erdos_cov_<jobid>.out`.
2. Most of the 1217 problems are genuinely absent from a 100k arXiv corpus, so the
   bulk of that distribution **is the null**. p50/p90/p99 describe noise, not signal.
3. Re-run with a cut **above p99**. Hand-check the survivors; LLM-judge the band
   just below with `o4_judge.py`.

Notes:
- **No `--accept-bare`** on the cluster — tier3 files carry `_rules.json` suffixes
  and arXiv ids, so the canonical loader picks them up directly.
- `MATCH_THEOREMS=1` also tests Erdős statements against theorem-like nodes (wider
  recall, much more noise — for feeding an LLM judge, not for a headline number).
- Single-threaded O(#Erdős × #corpus-nodes). At 1063 problems × the corpus's
  `open_problem`+`conjecture` nodes (~tens of thousands) this is a few minutes;
  it never holds the whole corpus in memory (`stream_papers`). The 4h wall is
  sized for `MATCH_THEOREMS=1` (millions of theorem nodes).

### 3. Output & interpretation

`erdos_coverage_100k.csv` has one row per Erdős problem, sorted by best match
score, columns:

```
number, status, resolved, score, covered, match_key, match_type,
resolving_theorem, resolution_verdict, erdos_stmt, match_snip
```

Read it as:
- `covered == True` (score >= threshold) → **that Erdős problem appears in our
  corpus**, stated in paper/node `match_key`. Coverage rate split by `resolved`
  is printed to stdout (`COVERED in corpus: N (resolved R / open O)`).
- `resolving_theorem` non-empty → the matched node was already in the T-OPEN
  sweep and a candidate resolving theorem (`resolution_verdict` = the O4 LLM
  judge's YES/NO) was found. This is the **end-to-end** signal: our pipeline
  linked an Erdős open problem to a corpus theorem that resolves it.
- Always eyeball the top rows: token-Jaccard is a recall-oriented shortlister,
  not a judge. Confirm borderline matches by hand or via
  `o4_judge.py --problem <match_key> --theorem <resolving_theorem> --model opus`.

## Caveats (be honest about these)

- **Temporal gate / pre-arXiv resolutions.** Most Erdős problems predate arXiv,
  and many were resolved in pre-arXiv papers. The T-OPEN sweep enforces
  `theorem.year >= problem.year`; here the "problem" node's year is the *arXiv
  paper that restates it*, not Erdős's original date — so the coverage match is
  fine, but the **resolution** cross-reference can only find solutions that live
  in the arXiv corpus *and* postdate the restating paper. A classical pre-arXiv
  resolution (e.g. Erdős–Ginzburg–Ziv) will show as **covered but not resolved**
  by our pipeline even though the problem is solved — that's a corpus-coverage
  limit, not a matcher bug.
- **Prose vs formal statement.** Erdős CSV statements are natural-language prose;
  corpus nodes are LaTeX-derived. Jaccard rewards shared surface tokens, so a
  problem stated with very different wording than its arXiv restatement can be
  missed (false negative) and unrelated nodes sharing math boilerplate can score
  low-but-nonzero (handled by the threshold).
- **The threshold is not a constant.** `--threshold 0.25` was tuned against a
  handful of corpus nodes. Because each score is a max over the whole corpus, the
  null distribution shifts right as the corpus grows — the same cut means something
  different at 15 nodes than at 10⁵. Always recalibrate from the printed histogram
  (§2); never carry a threshold across corpora.
- **154 of 1217 problems never enter the match** (statement too short to tokenize,
  147 of them under 10 characters). They are silently dropped by `load_erdos`, so
  the denominator is 1063. If those entries matter, they need re-scraping.
- **Token-Jaccard is the cheap rung, and prose-vs-LaTeX is exactly its weak spot.**
  Erdős statements are natural-language prose; corpus nodes are LaTeX-derived. The
  dense/rerank arm built after this probe (`o1b_dense_sweep` → `o1c_fuse` →
  `o5_rerank`, see `SEMANTIC_RETRIEVAL.md`) is the intended fix and has never been
  pointed at the Erdős set — run lexical as the baseline, then dense, and compare.
