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
- Step checker (rule 9): a capitalised sentence after a display with no period now counts as a new
  sentence, so short proofs with displays may get steps (24 of 2856 silver proofs cross the 2-sentence
  line, in 18 papers).
- Equivalence and non-dependency links (decided 2026-10-19, no new edge type):
  - `"alternative": true` on the `proves` edge of a second proof of a result that has its own
    proof; the cycle check does not count that proof as the result (Hall gives König after a
    direct proof of König is not circular); errors if set on a non-proves edge or on a result's
    only proof;
  - `mention` widened: a result about a conjecture or another result without using it
    (equivalent to, motivated by, analogous to); "equivalent" alone is never a dependency;
  - Regime D for "iff"/TFAE: `assumptions` = shared hypotheses only, `conclusions` = the whole
    biconditional, optional `equivalent_conditions` = verbatim span of each side (>= 2);
  - scorer (`graph_score.score`): a gold arrow drawn as an equivalence (144 in the 281 papers,
    8 in the 146) is matched in either direction.
- Multi-line displays (`latex_facts._split_rows`): an align/gather/eqnarray whose numbered rows have
  their own left-hand sides is one equation fact per equation; a row with an empty first cell
  ("&= z", "&\\le") or opening with a relation continues the previous one, a row with no number or
  label joins its neighbour, `\\intertext` prose belongs to neither. Splits: 203 facts in 53 of the 200
  silver papers, 1796 in 293 gold-candidate papers, 279 in 31 blueprint files; every other fact,
  label number and ref unchanged; gold conversion unchanged (799 papers, 0 differ). finalize() on the
  old v6 graphs: +11 errors in 2 papers, where one v6 equation node holds a now-split align (expected;
  v7 emits one node per fact). Test: `tests/test_align_rows.py`.
- `parts[]` (Regime E): several implications in one statement, each part's verbatim assumptions and
  conclusions, `adds_to` for "if moreover"; the flat lists keep every span (additive field).
- `cycle` note: a cycle the paper's text states is kept and reported with `kind` (`wrong_ref`,
  `granularity`, `circular`) and one verbatim quote per edge; it turns the cycle error into a warning.
  The prompt asks to recheck inferred edges first. The v6 `source_problem` notes still count.
- Code review (2026-10-19, 4 reviewers; regression on 1449 files, gold snapshot, the 200 v6 graphs):
  - fixed: a crash matching equal-text nodes; the CLI not inlining \\input; \\chapter numbering (books,
    reports, blueprints: chapter.section, [chapter] counters, equations within chapters); a \\label in a
    nested aligned/split lost; \\eqno labels bound to the section; row spans starting at [2pt];
    prose-boundary checks at the first copy of a repeated text; a non-proves edge blocking the
    syntactic proves edge; step checker: an immediate sentence judged over the whole step, a step
    after ';' only warned, "non-trivial" read as immediate, missing claim and case openers, "Let us"
    read as an introduction, {\\bf Proof.}/{\\bf Remark} taken as step labels; pseudocode:
    enumerate in an algorithm2e float, \\SetNlSty/\\SetKwBlock arguments, repeated lines matched
    out of order, descendant test; latex_macros brace reader at `\\\\}`; a source_problem note
    silencing a v7 cycle (now v6 files only; a cycle note must name the whole cycle).
  - new checks in finalize (the prompt said it ran them): type and origin vocabularies, required
    fields, origin_citation on external nodes, rigor values and placement, rigor_nonformal_count,
    proof_strategy and step subclass vocabularies, strategies in a proof's tags, edges between steps
    of different proofs. On the 200 v6 graphs: 4 new errors, all real.
  - one \\ref command list (latex_macros.REF_CMDS: \\nameref, \\thmref now also rendered) and one
    span key; type sets from node_types/edge_types; shared ancestor/subtree walks; regexes compiled
    once; dead code removed; tests/test_prompt_schema.py checks every vocabulary the prompt lists.
  - prompt: facts also hold hand-written proofs and \\eqno displays; a \\ref gives an edge into every
    node containing it; step rule 1 lists every label kind the parser reports.
  - The schema block changed, so the v6 prompt hash on main changed too: run v6 only from v6-frozen.
Not done: the 5-paper mini-pilot. The portal's "Your paper"
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
