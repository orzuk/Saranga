# Erdős-problems coverage over the Saranga corpus (T-OPEN)

**Goal.** Of the ~1070 catalogued Erdős problems (statements + resolution status,
exported from [github.com/teorth/erdosproblems](https://github.com/teorth/erdosproblems)
plus a Wayback scrape, into `erdos_problems_extracted.csv`), determine **which are
present in our parsed corpus** — i.e. some paper we parsed states that problem as
an `open_problem`/`conjecture` node — and, for the resolved ones, whether the
T-OPEN sweep already surfaced a corpus theorem that could resolve the matched node.

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

## Local proof-of-concept results

The full 100K corpus is cluster-only; `portal/data/tier3` is empty locally. The
PoC ran over the **~87 local parsed papers** — `tier1` (canonical, arXiv-id'd) +
`tier2` + `tier2_test` (bare `paperNNN.json`, loaded with `--accept-bare` since
`corpus_io` structurally skips files without an arXiv id). Those papers yield
**43 `open_problem`/`conjecture` nodes** (28 conjecture, 15 open_problem).

Because the real 1070-row CSV lives on Or's Google-Drive stream (`/mnt/g/My Drive/...`)
which was **not mountable in this environment** ("No such device"), the PoC used a
committed 10-row fixture of **real** Erdős statements, `erdos_sample.csv`, chosen
to include a known positive control.

```
python discovery_suite/open_problems/erdos_coverage.py \
    --erdos-csv discovery_suite/open_problems/erdos_sample.csv \
    --corpus-dir portal/data/tier1 portal/data/tier2 portal/data/tier2_test \
    --accept-bare \
    --out discovery_suite/open_problems/runs/erdos_coverage_local.csv
```

**Result — 2 of 10 Erdős problems covered (both genuine):**

| Erdős # | status | score | matched corpus node | note |
|---|---|---|---|---|
| 88 (prime k-tuples) | open | **0.800** | `paper394::CnjP44.1` | paper394 states the prime k-tuples conjecture verbatim |
| 3 (Erdős conj. on APs) | proved | **0.412** | `paper294::CnjP43.1` | paper294 states "Erdős conjecture on arithmetic progressions" |

Everything else scored **<= 0.21** and is generic-word noise (e.g. an Erdős
problem "matching" a `middlelevels` or category-theory node on shared tokens like
`conjecture`, `positive`, `integers`). The default `--threshold 0.25` cleanly
separates the two true matches (0.41–0.80) from that noise. `covered + resolving`
= 0: neither paper394 nor paper294 is in the existing T-OPEN sweep runs (those
were produced on the cluster corpus), so there is no cross-referenced resolving
theorem locally — expected.

**Takeaway:** tiny local coverage (as anticipated), but the matcher demonstrably
works — it recovered the two real Erdős statements that are actually in the local
corpus and rejected the rest.

## Running on the full 100K corpus (HUJI cluster)

### 1. Get the Erdős CSV onto the cluster

The CSV is derived from `teorth/erdosproblems` + a Wayback scrape and currently
lives only on Or's local G-drive. Copy it up once (from Or's WSL box):

```bash
scp "/mnt/g/My Drive/Research/Automath/erdos_problems_extracted.csv" \
    orzuk@glacier-13:/sci/labs/orzuk/orzuk/projects/Saranga/erdos_problems_extracted.csv
```

(It's a single small CSV — no inode concern.)

### 2. Run the coverage script

The parsed 100K knowledge-graph corpus root is the **parent of the ~20 category
dirs** (same `ROOT` the T-OPEN sweep uses, per `sweep_cluster.sh`):

```bash
cd /sci/labs/orzuk/orzuk/github/Saranga   # (legacy: .../Authomathics)

python3 discovery_suite/open_problems/erdos_coverage.py \
    --erdos-csv /sci/labs/orzuk/orzuk/projects/Saranga/erdos_problems_extracted.csv \
    --corpus-dir /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v4 \
    --threshold 0.25 \
    --out discovery_suite/open_problems/runs/erdos_coverage_100k.csv
```

Notes:
- **No `--accept-bare`** on the cluster — tier3 files carry `_rules.json` suffixes
  and arXiv ids, so the canonical loader picks them up directly.
- Add `--match-theorems` to also test Erdős statements against theorem-like nodes
  (wider recall; more noise — intended for feeding an LLM judge, not for a headline
  coverage number).
- Single-threaded O(#Erdős × #corpus-nodes). At 1070 problems × the corpus's
  `open_problem`+`conjecture` nodes (~tens of thousands) this is a few minutes;
  it never holds the whole corpus in memory (`stream_papers`). Wrap in `sbatch`
  (32G/4cpu) only if you also pass `--match-theorems` (millions of theorem nodes).

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
- **The 0.25 threshold was tuned on the tiny local PoC.** On the 100K corpus,
  re-check the score histogram; you may want 0.20 for recall (then LLM-judge the
  0.20–0.25 band) or 0.30 for precision.
- **The G-drive CSV was not reachable in the dev environment**, so the local PoC
  numbers above are against the 10-row `erdos_sample.csv` fixture, not the full
  1070. The script is unchanged for the real CSV — just point `--erdos-csv` at it.
