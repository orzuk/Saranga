# v6 silver run: evaluation report (200 papers)

Internal report. The paper describes the same corpus without version history (Table `tab:silver-stats` in `saranga_common.tex`).

## 1. What was run

- 200 papers, 10 from each of 20 categories (`corpus/silver/opus-5.5__v6/`).
- One Claude Opus 5.5 agent per paper, five agents in parallel.
- Every paper used the same frozen prompt: `scripts/opus_extract_prompt_v6_rendered.md`, sha `a6613a6c3d147ec5`.
- **Code changed during the run.** The deterministic code (`latex_facts`, `latex_macros`, `extraction_finalize`, `validate_annotation`, `proof_structure`) was fixed during the run, from commit 466568d to ea74b60; `docs/v6_changelog.md` lists every fix.
  - **Re-runs:** a paper was re-run when a fix changed its prepared source. That made 213 agent runs in total.
  - **Final finishing pass:** after the run, `finalize()` was re-applied to all 200 outputs with the final code. It changed 7 papers (5 parent links, 3 labels, 1 edge), and a second pass changes nothing.
  - **Backup:** the outputs from before that pass are in `scratchpad/v6final/backup_prefinal/`.
- **Hand repair.** Two statements in 1309.2370v6 (DP152, EP279) were repaired by hand. The expander left `\Cbar@>>>` unexpanded inside a `CD` diagram, which is an open bug (see 5c).
- **Version stamps.** The `prompt_version` field is `v6-a6613a6c3d147ec5-75a541a` on 192 outputs and `...-7d96371` on 8. Both have the same prompt sha; the suffix is the commit at render time.

## 2. Corpus statistics

| | total | per paper: median [IQR] |
|---|---:|---:|
| nodes | 37,715 | 158 [106–225], range 26–1,715 |
| Level-1 nodes | 25,064 | 101 [67–149] |
| steps (proof + algorithm) | 12,651 | 48 [27–78] |
| results (thm/lem/prop/cor/claim/conj) | 6,135 | 24 [16–37] |
| numbered equations | 7,045 | 19 [4–44] |
| edges | 62,634 | 247 [150–374] |
| finalize errors / warnings | 0 / 517 | 0 / 1 [0–2]; 96 papers have none |
| extraction notes | 1,294 | 6 [6–7] |

- **Node types:** proof_step 11,324, equation 7,045, definition 5,972, proof 2,856, claim 2,209, theorem 1,733, remark 1,384, algorithm_step 1,327, lemma 1,035, proposition 745, example 532, assumption 411, corollary 343, algorithm 307, problem 213, open_problem 200, conjecture 70, exercise 9.
- **Edge types:** uses 58,541, proves 2,897, illustrates 674, generalizes 210, resolves 186, specializes 111, tests 15.
  - 538 edges are mentions, spread over 105 papers.
  - 1,751 edges point backward by position.
- **Origin:** 20% of Level-1 nodes are external (5,079 of 25,064).
- **Rigor flags:** semi_formal 1,164, numerical 264, heuristic 80, conjectural 9.
- **Proof and algorithm steps:**
  - 70% of proofs are decomposed into steps (1,993 of 2,856), with a median of 4 direct steps.
  - The other 863 proofs are short, so the rules leave them whole.
  - 36 of 307 algorithms have no steps.
- **statement_short coverage:** 56.5% overall.
  - 100% for proofs and algorithms, and ~100% for proof steps.
  - 58% for theorems and 27% for definitions.
  - 3% for equations.
- **Confidence:** mean 0.86, and 41% of nodes have confidence below 0.8.
- **paper_style:** theorem_proof 166, computational 45, modeling 38, derivation 18, expository 9, discursive 2, problem_list 1.
- **Extraction notes:** type_uncertain 381, not_extracted 219, rule_conflict 209, source_problem 199, boundary_uncertain 188, unexpected_construct 98.
- **Orphans:** 58 in total, in 35 papers.
- **Section fields:** 3 papers have none at all; their sources genuinely have no sections.

### By category

The table shows medians, plus the mean external share, the mean equation share and the mean number of warnings.

| cat | nodes | edges | L1 | steps | ext | eq | warn |
|---|---:|---:|---:|---:|---:|---:|---:|
| cs.CC | 198 | 312 | 106 | 74 | .36 | .10 | 2.3 |
| cs.DS | 154 | 199 | 63 | 86 | .14 | .01 | 4.4 |
| cs.IT | 131 | 182 | 89 | 47 | .15 | .25 | 1.4 |
| cs.LG | 70 | 112 | 62 | 17 | .18 | .15 | 1.6 |
| math-ph | 153 | 223 | 133 | 35 | .22 | .39 | 12.9 |
| math.AG | 132 | 200 | 77 | 66 | .29 | .05 | 0.9 |
| math.AP | 175 | 283 | 104 | 68 | .18 | .25 | 0.5 |
| math.AT | 214 | 415 | 184 | 37 | .20 | .09 | 5.4 |
| math.CA | 159 | 230 | 118 | 41 | .26 | .27 | 2.4 |
| math.CO | 120 | 163 | 73 | 43 | .40 | .03 | 1.7 |
| math.DG | 243 | 339 | 174 | 46 | .20 | .24 | 3.1 |
| math.FA | 178 | 346 | 97 | 79 | .31 | .13 | 3.4 |
| math.GR | 109 | 232 | 66 | 39 | .35 | .05 | 2.1 |
| math.LO | 153 | 279 | 94 | 66 | .26 | .01 | 2.2 |
| math.NA | 162 | 276 | 122 | 28 | .28 | .36 | 0.8 |
| math.NT | 136 | 214 | 96 | 56 | .27 | .12 | 1.1 |
| math.OC | 154 | 244 | 114 | 33 | .16 | .28 | 0.8 |
| math.PR | 136 | 279 | 113 | 43 | .17 | .24 | 1.6 |
| math.RT | 186 | 311 | 114 | 51 | .29 | .12 | 1.0 |
| stat.TH | 181 | 284 | 124 | 74 | .12 | .23 | 2.1 |

The math-ph warning mean comes almost entirely from one paper, 1309.7607v2, which has 120 warnings (see 4).

## 3. Time and cost

- **Wall clock per paper:** median 7.8 min, mean 8.6, range 2.5–26.
  - The five agents together used 29 agent-hours.
  - The run took about 6 h of elapsed time, including pauses for code fixes.
- **Model calls per paper:** median 17, range 9–81.
- **Tokens per paper:**
  - Median 1.8 M processed: cache reads plus cache writes plus input.
  - About 18 K of those are generated.
- **Cost per paper:** median $2.2, mean $2.7, range $0.8–$18.6.
  - **Totals:** $540 for the 200 final runs and $583 including the 13 re-runs.
  - **Where the money goes:** cache reads 45%, cache writes 37%, output 18%.
  - **Time vs cost:** correlation 0.86.
  - **Most expensive papers:**

    | paper | nodes | cost | time | calls |
    |---|---:|---:|---:|---:|
    | 1802.10441v2 | 777 | $18.6 | 22 min | 73 |
    | 1906.08737v3 | 826 | $18.6 | 26 min | 81 |
    | 1708.00522v2 | 613 | $9.3 | — | — |
- **Caveats:**
  - **Prices are assumed:** $5 / $25 per M input/output, $0.50 cache read, $6.25 cache write (5 min). Confirm the Opus 5.5 list prices.
  - **Output tokens are estimated:** the transcripts under-record output tokens for streamed calls (a 43 KB write is logged as 8 tokens). I estimated output as characters written / 3.5. Input and cache counts are as logged.
  - **1309.2370v6 is understated:** its agent forked 9 sub-agents, whose tokens are not counted.
- **Script:** `scratchpad/v6final/cost.py`.

## 4. Anomalies and special cases

- **The largest paper by far is 1309.2370v6** (math.AT, virtual fundamental cycles): 1,715 nodes, 3,011 edges and 990 environment facts.
  - It is the only paper whose agent split the work across 9 forked sub-agents, one per range of sections, and then merged the results.
  - Its consistency across fragments has not been checked yet.
- **1309.7607v2 alone has 120 of the 517 warnings.**
  - The source starts paragraphs with `\vskip`, so ~110 nodes are flagged as starting mid-sentence. These are false positives.
  - The next worst is 1301.0114v1, with 33 warnings. It is literate Haskell, and the checker does not treat `\end{code}` as the end of a sentence.
- **Derivation-heavy papers are mostly equations.**
  - 1802.10441v2 (resurgence primer): 74% of its nodes are equations (573), and it declares theorem environments but never uses them.
  - Similar papers: 1601.01819v1 (60%), 1312.5856v2, 1505.00362v2 and 1908.10890v1 (~47%).
- **External-heavy papers.**
  - 1408.6474v1 (*Developments in Formal Proofs*, a survey) has 97% external nodes.
  - Five other papers are near 60%.
  - By category, math.CO (40%), cs.CC (36%) and math.GR (35%) cite and restate the most prior work.
- **Low-confidence papers.** These are mostly applied or expository papers:
  - 1505.06386v1: 17% of nodes below 0.7.
  - 1408.6474v1: 13%.
  - 1602.06796v1: 12%.
- **Edge density.**
  - Densest: 1512.06258v1 (3.0 edges per node) and 1604.05338v2 (2.9).
  - Sparsest: 1804.04206v1, a retinal-segmentation ML paper with 40 nodes and only 25 edges.
- **Papers with no steps at all.** The proofs in these are all one or two sentences.
  - 1108.5376v2 (quantum dilogarithm graphs).
  - 1908.10890v1 (a 53-node note).
- **No LaTeX structure at all.** 1911.02696v6 (SIMD popcount) has 0 environment facts, and its pseudocode is C++ listings in figures. All 81 of its nodes come from prose.
- **Results with no proof.**
  - 220 paper-origin theorems, lemmas, propositions and corollaries have no `proves` edge.
  - 132 of them are marked semi_formal, which is consistent.
  - **88 have neither a proof nor a rigor flag; these are worth a look.** Some are proved implicitly by later text, and some are restatements in the introduction.
  - The extreme case is 1111.3171v5 (renaming of bound variables): its 9 corollaries are stated without proof and are all correctly marked semi_formal.
- **Real cycles in the source.** The agents kept these and recorded them as source_problem:
  - **1803.10897v2:** Theorem 5.26 defers p-torsion-freeness to Corollary 5.33, whose proof uses 5.26.
  - **1912.03646v4:** the proof of Lemma 4 cites Theorem 6 where Theorem 1 is meant (a typo), which closes a cycle.
  - **1811.09972v1:** Theorem 1.1's lower bounds use identities proved in step (v) of the main proof. The argument is fine, but at node level it forms a cycle.
- **Source defects the agents found.**
  - **Duplicate `\label` keys in at least 10 papers.** For example, `iterate-G`, `proporthogonality`, `eqn:hidden` and `lemma:apriori-bound-HM` are each used twice, and `2.1` labels two different displays. Refs then resolve to only one target.
  - **Other defects:**
    - A theorem that closes before its enumerated conclusions (1805.12521v2).
    - Swapped labels (1912.03646v4).
    - Empty numbered equations (1903.11002v2).
    - Missing `\input` files (1711.05651v2 and others).
    - Wrong cross-references, such as "Corollary 2.16" pointing to a definition.
- **Agents that deviated from the rules to get past a check.** These need review:
  - Two definitions that nothing used were deleted to avoid orphans: "optimal truncation" in 1802.10441v2 and a negative-cyclic-homology definition in 1803.10897v2.
  - Real edges were dropped to avoid flagged cycles:
    - DP1→DP2 in 1908.10890v1.
    - TP8→PP16/PP17 in a joint-induction paper.
    - Edges from notation defined inside proofs in two papers.
  - A step was retyped `setup` to get past a false author-label error ("(cf. Step~2)") in 1901.09722v1.
  - 538 mention edges were added; the largest counts are 37, 32, 28, 24 and 23 in a single paper. Many are legitimate: "the proof of Theorem X is complete", or a proof citing the equations it proves. Some are workarounds for false cycles, such as references to equations nested inside a theorem, and references of the form "under the assumptions of Theorem X".

## 5. Problems, grouped by where the fix belongs

### 5a. LaTeX layer (`latex_facts.py`): constructs not reported as facts

| problem | papers |
|---|---:|
| proofs written by hand, without a proof environment: `{\bf Proof.}`, `{\it Proof.}`, `\noindent\emph{Proof of ...}`, `\mbox{\em Proof.}`, custom `\newproof`, braced `\begin{proof}{(of ...)}` | ~12 |
| pseudocode: algorithm2e floats (several), `tabular`, the `pseudocode` package, fbox+enumerate, literate Haskell, verbatim Macaulay2, C++ listings, enumerate after a bold heading | ~12 |
| `algorithm_lines`: the two-body `\eIf` parse is wrong, an `ENDFOR` is dropped, hand-numbered `\STATE`s give flat steps | 3 |
| disabled text kept: custom `\newif` switches, `\if False ... \fi`, `\begin {comment}` with a space | 5 |
| sections not detected: `\begin{section}`, bold centred headings, custom section macros, `\subsection[short]{long}`, `\section{#1}` inside a `\newcommand` | 7 |
| numbered displays missed: `$$...\eqno$$`, `numcases`, `subequations` labels, a preamble that redefines `\[` | 5 |
| thmtools `restatable`, starred non-standard theorem environments | 2 |
| `\ref` inside section titles left raw; ref keys containing doubled spaces or line breaks | 3 |

### 5b. Checker (`proof_structure.py` / finalize warnings): false positives

- **"Starts/ends mid-sentence".** This is most of the 517 warnings. It fires after:
  - `\vskip`, `\vspace` or `\medskip`;
  - `\label` after a heading;
  - footnotes;
  - `''` after a full stop;
  - `\qedsymbol`;
  - `\end{code}`;
  - run-in `{\bf X}` headings;
  - displays without a closing full stop;
  - a stray non-UTF character.
- **Display-heavy proofs counted as ≤2 sentences.** Steps are then rejected and the proof gets 0 steps. 7+ papers.
- **Author labels not detected:**
  - `$(1)$` in math mode;
  - `1)`;
  - `Case (e)` and `(c1)`;
  - `(\vec a)` and `(\Rightarrow)`;
  - `\textbf` case headings;
  - `\ref{item}:`;
  - "part (ii)" inside a paragraph.
- **False author labels:**
  - `Eq.~(2)`, which cut off the end of a proof;
  - `(cf. Step~2)`;
  - figure captions (a)/(b) inside a proof.
- **The math-span parser loses sync** on `\\$` (an escaped backslash before `$`), and the steps over several pages collapse into one. 2 papers.
- **Defined-term matching finds substrings:**
  - 'slant submanifold' inside 'pointwise slant submanifold';
  - 'population count' inside 'positional population count';
  - 'ATT' inside 'ATT(g,t)';
  - generic words such as "simple", "degree", "normal" and "type".
- **Inline claims that span several paragraphs** cannot be nested (rule 7).

### 5c. Expander (`latex_macros.py`)

- `\Cbar@>>>` inside `CD`: since the @-boundary fix, `@` after a macro name is read as part of the name, so `\Cbar` is not expanded. Fix: treat `@` as part of the name only when the longer name is itself defined, or exclude the `CD` arrow patterns `@>>>`, `@<<<`, `@VVV`, `@AAA`, `@=` and `@|`.

### 5d. finalize / cycle check

- **Copy matching.** For identical-text copies, the choice now uses neighbouring nodes. One case is still wrong: in 1906.08737v3, DP58 (N(n,k)) was matched to the introduction copy, which creates 2 spurious backward edges.
- **Short equations are not matched** to their environments: `H(s^*)=1.`, `AF+BF'=0`, `D_1^0=0`. The minimum key length is 10.
- **An equation nested in a definition or theorem stands for its container** in the cycle check. That turns a real mutual dependency, or a reference to a formula, into a false cycle; this caused most of the workaround mention edges. Possible fix: give a non-proof container's nested equation its own identity when the container is a definition, as is already done for nodes used outside a proof (`local_to`).
- **List-item refs** are not resolved to the claim nodes that are those items.

### 5e. Prompt gaps (your decisions)

1. **Proofs with no proof environment that run across a whole section, or are split at subsection headings.** Seen in 10+ papers.
   - Agents produced 5–15 "proof part" nodes, or a single huge prose proof.
   - The prompt needs one rule. Suggested: one proof node per result, with section-level steps.
2. **Results justified by the preceding paragraph,** which ends with a colon (1906.08737v3, 16 prose proofs at confidence 0.7). Do these count as proofs?
3. **A numbered equation in an introduction restatement.** "Every numbered equation is a node" conflicts with "one node per repeated statement". 3 papers.
4. **Unused definitions:** may an agent drop one to avoid an orphan? Currently 2 agents did. Suggested: never drop; orphans are allowed.
5. **Definitions inside proofs that other results use.** Agents kept them as steps (rule 4) and lost the edges, or marked them as mentions.
6. **Joint induction / mutually recursive algorithms:** how to record a genuine mutual dependency.
7. **"Proof of the Claim":** handled one way inside a remark and another inside a proof (1906.08117v1). Separately, claims inside a proof were sometimes emitted both as labelled steps and as nested claims.
8. **A "where ..." clause after an equation retyped as a theorem** falls into no node.
9. **`resolves` cannot target an example** (an open question answered by a counterexample), and **`statement_short` is optional**. Coverage fell from 78% to 57% (see 6).

### 5f. Data fixes still to do

- **1605.09252v2:** TP3 rigor was dropped during the build.
- **1611.01043v4:** a stale edge (the agent's `build.py` has AssumP1→cond:sum; the JSON does not).
- **1309.2370v6:** check consistency across the 9 fragments.
- **Mention edges:** review the 538, starting with the papers that have the most.
- **Unproved results:** review the 88 that carry no rigor flag.

## 6. Comparison with v5.1 (same 200 papers, Claude Opus 5, prompt v5.1)

| | v5.1 | v6 |
|---|---:|---:|
| nodes | 25,162 | 37,715 (+50%) |
| Level-1 nodes | 16,724 | 25,064 (+50%) |
| steps | 8,438 | 12,651 (+50%) |
| edges | 39,839 | 62,634 (+57%) |
| dependency edges (uses/generalizes/specializes) | 36,414 | 58,862 (+62%) |
| verbatim statements | 99.5% | 100% (checked by finalize) |
| statement_short coverage (per paper mean) | 78.2% | 57.0% |
| results with assumptions/conclusions | 98.5% | 92.0% |
| external share of Level-1 (per paper mean) | 22.9% | 23.9% |
| finalize errors | not checked | 0 |

- **Node overlap.** Nodes were matched by token Jaccard ≥ 0.5, which cannot match short math-only equations.
  - **v5.1 → v6:** 77% of v5.1's Level-1 nodes (12,842 of 16,724) have a v6 counterpart.
  - **Highest overlap:** proofs 97%, lemmas 93% and theorems 89%.
  - **Lowest overlap:** remarks 64%, examples 68% and open problems 60%. v6 drops some discursive remarks and retypes others.
- **Reverse overlap (v6 → v5.1).** For non-equation types, 72% of v6 nodes have a v5.1 counterpart (13,034 of 18,019).
  - Claims are the exception at 52%: 1,061 of v6's 2,209 claims are new.
  - Definitions are 60%: 2,393 of 5,972 are new.
  - **v6 finds more prose content:** inline claims, notation definitions, and claims nested inside results.
- **Equations: 1,226 → 7,045.** v6 makes every numbered equation a node (by rule), while v5.1 kept only some.
- **Type changes among matched nodes:** 87% keep their type.
  - **Main changes:**
    - proposition → claim (222);
    - proposition → theorem (163);
    - equation → definition (118);
    - equation → claim (115);
    - remark → claim (102);
    - claim → theorem (82);
    - claim → remark (68);
    - assumption → definition (59).
  - **Propositions overall fell from 1,360 to 745.** v6 types by the environment and by what the text claims, while v5.1 used "proposition" for prose statements.
- **Edges.** Of the v5.1 dependency edges whose two ends both match v6 nodes, 69% (12,415 of 17,998) are present in v6, either on the same pair or between their containers.
- **Regressions to decide on:**
  - statement_short coverage fell from 78% to 57%. Equations and definitions were mostly left without one, which the prompt allows when the statement is already short.
  - The assumptions/conclusions split fell from 98.5% to 92%.
  - Both are prompt choices; tighten the prompt if they matter.

## 7. Paper (`saranga_common.tex`)

- The silver-corpus paragraph now gives the 200-paper statistics, with the new Table `tab:silver-stats`. The table includes the time, tokens and API-equivalent cost.
- The cost paragraph gives the time, calls, tokens and cost.
- Body text no longer mentions "v6" or the pilot. "v6" and "v5.1" remain only in `\todo`s.
- **Inconsistency still open:** the distillation sections (Sec. 4.4, App. F, the held-out set) are still truthfully described as using "200 papers extracted by Claude Opus 5 with prompt v5.1". Removing that label would misattribute their numbers. They must be re-run on this corpus (existing `\todo`), or the text must say that distillation used an earlier extraction.

## Scripts

All scripts are under `scratchpad/v6final/`.

- `eval/stats.py`: corpus statistics.
- `eval/trans.py`: node overlap and type changes vs v5.1.
- `run200/v5_vs_v6.py`: the v5.1-vs-v6 table.
- `cost.py`: time and cost.
- `issues.txt`: the per-paper issue log (156 entries).
