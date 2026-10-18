# v7 handoff — state on 2026-10-18 (Sunday)

Where we are in the v6 → v7 decision, what is decided, and what to do next.
To resume in a new Claude Code session: "read docs/v7_handoff/README.md and continue".

## Decided

> **Reopened 2026-10-18 (afternoon):** the choice of plan is open again. Options A / B / C, costs and
> arguments: `DECISION_v7_plan_2026-10-18.md`.

- **Plan B: build v7 (code + prompt), then re-extract everything with it**: the 200 silver papers,
  the 146 author-diagram papers (gold evaluation subset), the 104 Lean blueprints and the ~20 papers
  that blueprints follow. All on one frozen commit, so "all extracted the same way" holds.
- Not plan A (old code for the 146): the dry run below showed today's LaTeX layer prepares 109 of the
  200 papers differently from what their v6 agents saw, so mixing would break consistency, and Or wants
  all fixes in v7 anyway.
- Budget: weekly plan ≈ $1,750 (the 200 silver ≈ ⅓ week). Reset Monday 2026-10-19 afternoon.
  Or's plan: build v7 in a couple of hours, run the 200 + as many of the 146 as fit tonight (~¾ of the
  remaining week), the rest after the reset.

## Cost estimates (share of a weekly plan)

| job | estimate | week |
|---|---:|---:|
| 200 silver (v7 maybe +10–20%) | ~$580 | 33–40% |
| 146 diagram papers (LaTeX 2.2× silver, median 148 KB) | ~$750–900 | 45–50% |
| 104 blueprints (least certain) | ~$300–450 | 20–25% |
| ~20 blueprint source papers (long) | ~$150–250 | 10–15% |
| mini-pilot, 5 papers | ~$30 | ~2% |

## v7 status (2026-10-18 evening)

Implemented on main (not yet run on any paper):
- prompt `scripts/opus_extract_prompt_v7.md` (v6 + the rules below; render with
  `scripts/render_v6_prompt.py ... --prompt v7`, which also finds gold papers);
- `finalize()`: `display`, `number`, `cites` on nodes; edge `basis` (`ref`, `syntax` by code;
  `named`/`term`/`inferred` by the agent, warned when missing); a step duplicating a result's span
  is merged into it; `also_stated_at` copies' labels resolve to the one node; a result stated inside
  a proof but used outside it (not by `\ref`) is warned; a prose proof may span the subsections of
  its section; `definiendum` may be a list. Test: `tests/test_finalize_v7.py`.
- On the 200 v6 graphs (old graphs, new code): errors unchanged (1652, the known LaTeX-layer
  mismatch), 3 papers with a merged step, 12 encapsulation warnings in 10 papers, 27% of edges get a
  basis from code.
- LaTeX layer (from the v6 agents' notes): proof labels with inline math and $(1)$-style labels
  (38 new labels in 8 of the 200 papers, all where agents started steps or real part labels);
  algorithm2e under [algo2e] and `\begin {algorithm}` (algorithm facts 43 -> 49, with lines
  38 -> 46); the else-branch of `\eIf`. Gold conversion unchanged (799 papers, 0 differ).
  Test: `tests/test_latex_layer_v7.py`.
Not done: an align with several numbered rows is still one equation fact; the step checker on short proofs, schema
decisions 3/4 (`equivalent`, `motivates`), the 5-paper mini-pilot. The portal's "Your paper"
(`portal/yours_llm.py`) still uses the v6 prompt.

## v7 scope (proposed, NOT yet confirmed by Or)

- **LaTeX layer**: today's `latex_facts.py` / `latex_macros.py` (already written since the v6 run:
  164 environments found that v6 missed, 385 printed numbers and 42 types corrected, macro fixes).
- **finalize() additions** (code):
  - edge `basis`: `ref` (from \ref), `syntax` (proof environments) by code; `named` / `term` /
    `inferred` set by the agent;
  - printed number on each node; the author's environment word (`display`), next to `type`;
  - `cites`: bib keys cited inside a node;
  - remove a duplicate where a claim node and a proof step share the same span.
- **Prompt rules**:
  - a claim the author names or numbers inside a proof is a claim node (parent = the proof), never also a step;
  - a result stated twice (intro + body) is one node with `also_stated_at`;
  - a proof with no environment spanning a section: one proof node with section-level steps;
  - never drop a definition to avoid an orphan;
  - optional `main: true` on the paper's main results;
  - the agent sets `basis` on edges it adds.
- Already done on main (commit e7f0fc3): cycle check ignores an equation displayed in a result's
  statement; 67 workaround mention flags removed from the v6 silver.

## Run procedure

1. Implement v7 on main; dry-run `finalize()` on the 200 (free) with `docs/v7_handoff/dryrun.py`.
2. Mini-pilot: v7 on 5 papers (3 silver, 2 diagram incl. a hard one); check errors, new fields, cost.
3. Freeze: one commit, no code changes during the run (v6 needed 13 reruns from mid-run fixes).
4. Run the 200 silver first (every claim rests on them), then the 146, then blueprints + source papers.

## Blocker: the gold data is not on this machine

> **Resolved 2026-10-18:** unpacked from the Drive tarball and tracked in git (commit d1a0cda,
> `scripts/gold_candidates/track_gold.py`). Still open: no `review.json` is on this machine.

`corpus/gold_candidates/**` and `corpus/gold_blueprints/**` are git-ignored by design (.gitignore
lines 93–104): only `candidates.json` and `review.json` files are tracked. The 146 sources, the gold
graphs, `index.json` and all 104 blueprints are on the other laptop (battery dead). There:
1. `git status`, `git log origin/main..main` → commit and push any reviews or code not pushed
   (no `review.json` is in the repo yet — reviews are the one thing that cannot be regenerated);
2. **Decided: track the gold sets in git, in the same form as the silver** (silver `tex_pool` is already
   tracked). Narrow the .gitignore exceptions to add: `index.json`, each paper's `gold.json` and
   flattened main `.tex`; each blueprint's `all.tex`, `graph.json`, `meta.json` and the blueprint index.
   Keep out: original arXiv packages/tarballs, PDFs, rendered pages, cloned blueprint repos. Check
   sizes before committing (no file > 100 MB; aim for tens of MB in total). If the repo is public, keep
   the 43 blueprints with no licence out (or keep the repo private until release).
3. Commit, push, and pull on the other machine; check counts: 281 diagram papers, 146 evaluation,
   104 blueprints. (Fallback if git is not wanted: zip both dirs to Google Drive.)
The silver 200 can start without it.

## Files here

- `dryrun.py`: re-runs the LaTeX layer and `finalize()` on the 200 stored graphs with a given code dir.
- `old.jsonl` (code at ea74b60, the end of the v6 run) and `new.jsonl` (main as of 2026-10-18):
  - old reproduces the stored data (3 tiny diffs; errors only in the 8 unflagged papers, the
    hand-fixed 1309.2370v6, and 1611.03739v3);
  - new: prepared source differs in 74 papers, facts in 107, any stage-1 difference in 109; re-applying
    today's finalize to the v6 JSONs gives 550 non-verbatim statements in 58 papers — today's code is
    not compatible with the v6 graphs, hence re-extraction.
- `unflagged_edges.tsv`: the 67 mention flags removed in e7f0fc3.

## Loose ends

- Local branch `v6-frozen` (e069d4a = ea74b60 + the cycle fix), made for plan A; not needed under
  plan B — delete with `git branch -D v6-frozen` (its worktree was in /tmp; `git worktree prune`).
- `Papers/Saranga/saranga_common.tex`: uncommitted one-line xcolor fix (`\PassOptionsToPackage{table}{xcolor}`)
  that makes `saranga_tmlr.tex` compile cleanly.
- `docs/silver_v6_size_distribution.jpg`: nodes/edges per paper chart (untracked).
- Related notes: `G:\My Drive\Research\Automath\proof_hierarchy\proof_dag_hierarchy.tex` (proof DAG,
  post-dominator tree, hierarchy-invariant scoring).
