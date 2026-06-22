# Silver Merged Distillation — Results Report

_eval-dir: `src/LLMVersion/merged_eval_silver_001_011_v3` · papers: 17 · generated read-only from existing artifacts_

## 0. Headline — pooled P/R/F1 (base → distillation → LLM-judge)

_Pooled over every node in all papers (not a per-type macro), so it is not deflated by sparse/absent types. The judge corrects precision only (rescues FPs that were silver under-labeling); it cannot change recall._

| stage | TP | FP | FN | precision | recall | F1 |
|---|---|---|---|---|---|---|
| Base (no distilled rules) | 374 | 105 | 199 | 0.781 | 0.653 | 0.711 |
| Post-distillation (final rules) | 421 | 151 | 152 | 0.736 | 0.735 | 0.735 |
| Post-LLM-judge (spurious FPs removed) | 421 | 45 | 152 | 0.903 | 0.735 | 0.810 |

## 1. Run summary

- Papers: paper001, paper002, paper003, paper004, paper005, paper006, paper007, paper009, paper010, paper011, paper008, paper012, paper013, paper014, paper015, paper016, paper450
- Total LLM calls: 134  ·  Total cost: $14.5735  ·  Avg $0.8573/paper
- LLM steps per group: 2 (analyze + aggregate); identify-dark-knowledge & prune are deterministic

| paper | FN (no rules) | FN (rules so far) | cum. rules | calls (a+agg) | cost |
|---|---|---|---|---|---|
| paper001 | 20 | 20 | 25 | 7 (4+3) | $0.4051 |
| paper002 | 14 | 14 | 38 | 10 (5+5) | $0.5023 |
| paper003 | 4 | 3 | 33 | 7 (2+5) | $0.4363 |
| paper004 | 24 | 24 | 49 | 10 (5+5) | $0.7344 |
| paper005 | 11 | 11 | 63 | 9 (4+5) | $0.7413 |
| paper006 | 28 | 24 | 68 | 9 (4+5) | $0.9268 |
| paper007 | 5 | 5 | 61 | 6 (1+5) | $0.7819 |
| paper009 | 0 | 0 | 71 | 5 (0+5) | $0.7504 |
| paper010 | 6 | 6 | 64 | 6 (1+5) | $0.8189 |
| paper011 | 11 | 11 | 65 | 8 (3+5) | $0.8602 |
| paper008 | 15 | 10 | 71 | 8 (3+5) | $0.9499 |
| paper012 | 10 | 10 | 73 | 9 (4+5) | $0.9569 |
| paper013 | 10 | 10 | 79 | 8 (3+5) | $1.0235 |
| paper014 | 16 | 14 | 77 | 10 (5+5) | $1.1882 |
| paper015 | 3 | 3 | 67 | 8 (3+5) | $1.0537 |
| paper016 | 20 | 11 | 75 | 7 (2+5) | $1.2573 |
| paper450 | 2 | 2 | 88 | 7 (2+5) | $1.1863 |

## 2. Final per-type F1 (containment matching)

_Per-paper diagnostic detail. `present` = macro over only the types that appear in that paper; `all9` counts absent types as 0 (deflated — ignore for quality). Use this table to spot which specific types are weak, not for the headline number (that's §0)._

| paper_id | fn_base | fn_sofar | baseline_all9 | baseline_present | final_all9 | final_present | final_f1_definition | final_f1_theorem | final_f1_lemma | final_f1_proof | final_f1_proposition | final_f1_corollary | final_f1_claim | final_f1_conjecture | final_f1_problem | final_f1_remark | final_f1_algorithm | final_f1_example | final_f1_assumption | final_f1_open_problem | final_gold_definition | final_gold_theorem | final_gold_lemma | final_gold_proof | final_gold_proposition | final_gold_corollary | final_gold_claim | final_gold_conjecture | final_gold_problem | final_gold_remark | final_gold_algorithm | final_gold_example | final_gold_assumption | final_gold_open_problem | final_fp_definition | final_fp_theorem | final_fp_lemma | final_fp_proof | final_fp_proposition | final_fp_corollary | final_fp_claim | final_fp_conjecture | final_fp_problem | final_fp_remark | final_fp_algorithm | final_fp_example | final_fp_assumption | final_fp_open_problem |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| paper001 | 20 | 20 | 0.2407 | 0.4213 | 0.25 | 0.4375 | 0.5 | 1.0 | 0.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 12 | 1 | 0 | 5 | 6 | 0 | 0 | 0 | 4 | 4 | 3 | 2 | 0 | 0 | 12 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper002 | 14 | 14 | 0.3121 | 0.4369 | 0.4009 | 0.5612 | 0.8 | 0.8889 | 1.0 | 0.9231 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 5 | 5 | 5 | 6 | 0 | 1 | 0 | 0 | 4 | 2 | 1 | 1 | 0 | 1 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper003 | 4 | 3 | 0.25 | 0.5 | 0.2932 | 0.5865 | 0.5 | 1.0 | 0.9655 | 0.973 | 0.0 | 0.0 | 0.0 | 0.0 | 0.6667 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 2 | 5 | 14 | 18 | 0 | 0 | 0 | 0 | 2 | 0 | 1 | 0 | 0 | 1 | 4 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper004 | 24 | 24 | 0.3644 | 0.5668 | 0.3684 | 0.573 | 0.5 | 0.8571 | 1.0 | 1.0 | 1.0 | 0.8 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 8 | 6 | 3 | 10 | 1 | 2 | 0 | 0 | 2 | 7 | 0 | 0 | 7 | 0 | 4 | 2 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper005 | 11 | 11 | 0.2803 | 0.4905 | 0.3111 | 0.5444 | 0.8 | 0.6667 | 1.0 | 0.8889 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 4 | 2 | 1 | 4 | 2 | 0 | 0 | 0 | 2 | 2 | 1 | 0 | 0 | 0 | 2 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper006 | 28 | 24 | 0.343 | 0.4365 | 0.41 | 0.5219 | 0.1333 | 0.8571 | 1.0 | 0.75 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.5 | 0.5 | 1.0 | 0.0 | 5 | 4 | 11 | 7 | 0 | 2 | 0 | 0 | 3 | 3 | 6 | 3 | 5 | 3 | 9 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper007 | 5 | 5 | 0.3402 | 0.7937 | 0.3367 | 0.7857 | 0.7143 | 0.6667 | 0.6667 | 1.0 | 0.6667 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 8 | 3 | 2 | 5 | 2 | 0 | 0 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 1 | 3 | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper009 | 0 | 0 | 0.4821 | 0.9643 | 0.4675 | 0.9351 | 0.5455 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 6 | 16 | 17 | 38 | 5 | 8 | 0 | 0 | 0 | 0 | 0 | 4 | 0 | 0 | 10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 18 | 0 | 0 | 0 | 0 |
| paper010 | 6 | 6 | 0.1429 | 0.6667 | 0.1429 | 0.6667 | 0.0 | 1.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 6 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper011 | 11 | 11 | 0.385 | 0.6737 | 0.3731 | 0.6529 | 0.5 | 1.0 | 0.9231 | 0.8 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 2 | 7 | 13 | 14 | 0 | 1 | 0 | 0 | 1 | 5 | 2 | 0 | 0 | 0 | 4 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper008 | 15 | 10 | 0.2873 | 0.3657 | 0.3115 | 0.3965 | 0.4444 | 1.0 | 1.0 | 0.9167 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 2 | 6 | 6 | 12 | 1 | 0 | 0 | 0 | 1 | 1 | 2 | 3 | 1 | 1 | 5 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper012 | 10 | 10 | 0.0952 | 0.2222 | 0.1429 | 0.3333 | 0.3333 | 0.0 | 0.0 | 0.6667 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 3 | 0 | 0 | 2 | 1 | 0 | 2 | 0 | 0 | 3 | 4 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper013 | 10 | 10 | 0.1786 | 0.3571 | 0.2473 | 0.4945 | 0.4615 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 4 | 3 | 1 | 4 | 1 | 0 | 0 | 0 | 2 | 0 | 0 | 2 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper014 | 16 | 14 | 0.0571 | 0.1333 | 0.1175 | 0.2741 | 0.4444 | 0.0 | 0.0 | 0.4 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.8 | 0.0 | 0.0 | 0.0 | 7 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 1 | 1 | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper015 | 3 | 3 | 0.2857 | 0.5714 | 0.2857 | 0.5714 | 0.0 | 1.0 | 0.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 1 | 1 | 0 | 3 | 2 | 0 | 0 | 0 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| paper016 | 20 | 11 | 0.3351 | 0.5864 | 0.3809 | 0.6665 | 0.5 | 1.0 | 0.9231 | 0.9091 | 1.0 | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 12 | 2 | 6 | 10 | 1 | 0 | 1 | 0 | 0 | 4 | 0 | 1 | 0 | 0 | 6 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| paper450 | 2 | 2 | 0.2174 | 0.4347 | 0.1981 | 0.3962 | 0.2353 | 1.0 | 0.9286 | 0.2759 | 0.0 | 0.3333 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 2 | 6 | 26 | 4 | 0 | 1 | 0 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 13 | 0 | 4 | 21 | 0 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## 2b. LLM-judge FP adjustment

| type | judged FP | GENUINE (rescued) | real FP |
|---|---|---|---|
| algorithm | 1 | 0 | 1 |
| corollary | 5 | 5 | 0 |
| definition | 79 | 49 | 30 |
| lemma | 9 | 5 | 4 |
| proof | 32 | 23 | 9 |
| proposition | 2 | 2 | 0 |
| remark | 18 | 17 | 1 |
| theorem | 5 | 5 | 0 |

## 3. Per-group breakdown

### algorithm
- active patterns: 8  ·  pruned: 2  ·  FNs analyzed: 14 {'algorithm': 14}
- PRUNED rules:
  - FP on paper001, paper008, paper009 +4 more | also 1 TP — review before uncommenting
  - SLOW backtracking (TIMEOUT > 10.00s/paper cap)

### definition
- active patterns: 30  ·  pruned: 16  ·  FNs analyzed: 51 {'definition': 51}
- PRUNED rules:
  - FP on paper001, paper002, paper003 +7 more | also 4 TP — review before uncommenting
  - FP on paper002, paper003, paper004 +6 more
  - FP on paper008
  - FP on paper006, paper008, paper013 +1 more | also 1 TP — review before uncommenting
  - FP on paper002, paper003, paper004 +1 more | also 2 TP — review before uncommenting
  - FP on paper004, paper005
  - FP on paper001, paper010, paper014 | also 1 TP — review before uncommenting
  - FP on paper016
  - FP on paper006, paper007, paper013 | also 1 TP — review before uncommenting
  - FP on paper002, paper004, paper013 | also 2 TP — review before uncommenting
  - FP on paper013, paper014, paper016 | also 4 TP — review before uncommenting
  - FP on paper013
  - FP on paper004, paper006, paper009 +4 more | also 4 TP — review before uncommenting
  - FP on paper003, paper004, paper015 | also 1 TP — review before uncommenting
  - FP on paper013
  - FP on paper009, paper013 | also 1 TP — review before uncommenting

### proof
- active patterns: 9  ·  pruned: 0  ·  FNs analyzed: 9 {'proof': 9}

### simpleenv
- active patterns: 22  ·  pruned: 0  ·  FNs analyzed: 56 {'remark': 34, 'example': 14, 'assumption': 8}

### theoremlike
- active patterns: 11  ·  pruned: 1  ·  FNs analyzed: 42 {'problem': 24, 'theorem': 6, 'open_problem': 5, 'proposition': 4, 'lemma': 1, 'claim': 2}
- PRUNED rules:
  - FP on paper005, paper012


## 4. FN-level detail (what each group learned from)

### algorithm (14 items)

- **paper001 / algorithm** — `${\bf Unnormalized spectral clustering}\\$ Input: Similarity matrix $S \in \R^{n \times n}$, number $k$ of clusters to con\-struct. $\bullet$ Construct a simila`
  - why missed: All three missed algorithms are produced by a custom macro \ulesalgorithm{<title>}{<body>} (not a \begin/\end environment). The base extractor only looks for \begin{algorithm}...\end{algorithm}. We need a new regex branc
  - suggested: `def _extract_ulesalgorithm(self, text: str) -> List[Algorithm]:     """     Extract algorithms defined via the custom macro:         \\ulesalgorithm{<title>}{<b`
- **paper001 / algorithm** — `${\bf Normalized spectral clustering according to \citeA{ShiMal00}}\\$ Input: Similarity matrix $S \in \R^{n \times n}$, number $k$ of clusters to con\-struct. `
  - why missed: Same structural pattern as Item 0: \ulesalgorithm{title}{body}. The _extract_ulesalgorithm method added for Item 0 will also catch this occurrence because it generalises to ALL invocations of macros ending in 'algorithm'
  - suggested: `# No additional code required beyond the _extract_ulesalgorithm method introduced for Item 0. # That method's pattern r'\\(?P<macro>[A-Za-z]*[Aa]lgorithm)\{...\`
- **paper001 / algorithm** — `${\bf Normalized spectral clustering according to \citeA{NgJorWei02}}\\$ Input: Similarity matrix $S \in \R^{n \times n}$, number $k$ of clusters to con\-struct`
  - why missed: Same structural pattern as Items 0 and 1: \ulesalgorithm{title}{body}. The _extract_ulesalgorithm method introduced for Item 0 already handles this case in a generalised way. No further code is needed.
  - suggested: `# No additional code required beyond the _extract_ulesalgorithm method introduced for Item 0. # The general macro pattern r'\\(?P<macro>[A-Za-z]*[Aa]lgorithm)\{`
- **paper002 / algorithm** — `\begin{enumerate} \item select $n$ (the size of the input signal) and $m$ so that with the same notations as before, $A$ is an $n$ by $m$ matrix; sample $A$ wit`
  - why missed: The missed algorithm is described as a numbered list of procedural steps (an `enumerate` environment) that describes an experimental/algorithmic procedure. The base extractor only looks for explicit `algorithm`/`algorith
  - suggested: `# Add to _extract_algorithms, after the existing env_names block: # Also scan for \begin{enumerate} blocks that look like procedural step lists # (structural he`
- **paper003 / algorithm** — `The algorithm proceeds by splitting the information obtained in the graph into a part that is used by the partial recovery algorithm and a part that is used for`
  - why missed: This algorithm is described in plain prose within a section body, not inside a LaTeX environment like \begin{algorithm}...\end{algorithm}. The text describes an algorithmic procedure but is embedded as regular paragraph 
  - suggested: `# No safe minimal regex addition is possible for prose-only algorithm descriptions. # The item is a plain paragraph, not a LaTeX environment. # If desired, one `
- **paper006 / algorithm** — `\paragraph{Average mixture algorithm} \begin{enumerate} \item[(1)] For each $i \in \{1, \ldots, \nummac\}$, processor $i$ uses its local dataset $\samples_{1, i`
  - why missed: This algorithm is described inline: a \paragraph{...} heading followed by a \begin{enumerate}...\end{enumerate} block. The pattern is \paragraph{<words> algorithm} then \begin{enumerate}...\end{enumerate}. We need a rege
  - suggested: `# Pattern: \paragraph{... algorithm ...} \begin{enumerate} ... \end{enumerate} _PARA_ALG_RE = re.compile(     r'\\paragraph\{(?P<name>[^}]*?\balgorithm\b[^}]*)\`
- **paper006 / algorithm** — `The subsampled average mixture (\savgm) algorithm is based on an additional level of sampling on top of the first, involving a fixed subsampling rate $\ratio \i`
  - why missed: Same structural pattern as Item 0: \paragraph{... algorithm ...} followed by \begin{enumerate}...\end{enumerate}. The same _extract_paragraph_algorithms method handles this case. No additional code needed beyond what is 
  - suggested: `# Already covered by _extract_paragraph_algorithms added for Item 0. # No additional code required for Item 1.`
- **paper006 / algorithm** — `The averaged stochastic gradient algorithm (\sgdavgm) is based on the following two steps: \begin{enumerate} \item[(1)] Given some constant $c > 1$, each machin`
  - why missed: This algorithm is described inline in prose: a sentence ending in 'the following <N> steps:' or 'the following two steps:' immediately followed by \begin{enumerate}...\end{enumerate}. We can generalize: prose context con
  - suggested: `# Pattern: sentence containing 'algorithm' ... 'following ... steps:' then \begin{enumerate}...\end{enumerate} _PROSE_ALG_RE = re.compile(     r'(?:algorithm\b[`
- **paper006 / algorithm** — `Stochastic gradient descent algorithms iteratively update a parameter vector $\optvar^t$ over time based on randomly sampled gradient information. Specifically,`
  - why missed: This describes an algorithm (SGD) in prose + a \begin{equation}...\end{equation} block (not enumerate). The structural pattern: text describing an iterative method mentioning 'performs the following ... steps:' or 'the f
  - suggested: `# Pattern: 'following ... steps:' immediately before \begin{equation}...\end{equation} _STEPS_EQ_RE = re.compile(     r'following\s+\w+\s+steps\s*:\s*'     r'(?`
- **paper006 / algorithm** — `that this computation can be performed in time $\order(\numobs \log(\nummac \numobs))$. In particular, the following two-stage strategy, involving a combination`
  - why missed: Same pattern as Item 2: inline prose with 'algorithm' or 'strategy' context + 'the following ... steps:' + \begin{enumerate}...\end{enumerate}. The _extract_prose_algorithms regex with 'following ... steps:' already gene
  - suggested: `# Broaden _PROSE_ALG_RE to not require 'algorithm' in the lead, just 'following ... steps:' # Replace the previous _PROSE_ALG_RE with: _PROSE_ALG_RE = re.compil`
- **paper006 / algorithm** — `The dataset is too large to fit in the memory of most computers: in total, four splits of the data require 55~gigabytes. Consequently, it is difficult to provid`
  - why missed: Item 5 is a paragraph of prose describing experiments with SGD/SDCA algorithms. There is no \begin{enumerate}, no \begin{algorithm}, no \paragraph{... algorithm}. The 'algorithm' mention is incidental—this is a results/e
  - suggested: `# Item 5 is a prose experimental-results paragraph with no structural marker # (no \begin{algorithm}, \paragraph{...algorithm...}, or enumerate block). # Catchi`
- **paper008 / algorithm** — `The algorithm we focus on is stochastic gradient descent (SGD). The SGD algorithm is parameterized by step sizes $\eta_1,\ldots,\eta_T$, and is defined as follo`
  - why missed: This algorithm is described inline in prose followed by a \begin{enumerate}...\end{enumerate} environment. The structural pattern is: a sentence or two introducing 'the algorithm' (or naming a specific algorithm), immedi
  - suggested: `# Inline algorithm pattern: prose intro ending with 'as follows' (or similar) + \begin{enumerate} _INLINE_ALG_PATTERN = re.compile(     r'(?P<intro>(?:[^\n]|\n(`
- **paper008 / algorithm** — `In the previous section, we showed that SGD with averaging may have a rate of $\Omega(\log(T)/T)$ for non-smooth $F$. To get the optimal $\Ocal(1/T)$ rate for a`
  - why missed: This item is pure prose—there is no \begin{enumerate} or any LaTeX environment wrapping the algorithm description. The 'algorithm' (suffix averaging) is described entirely in a paragraph, including a display math block (
  - suggested: `# Pattern for prose-only algorithm descriptions introduced by 'we call this [procedure|algorithm|method]' # Matches a paragraph (up to 2000 chars) containing a `
- **paper014 / algorithm** — `Let $\pT(\bx, \bz) = \pT(\bz) \pT(\bx|\bz)$ be the generative model we are sampling from, and for a given datapoint $\bxi$ we would like to estimate the margina`
  - why missed: This is not a standard LaTeX algorithm environment at all — it's a numbered enumeration (`\begin{enumerate}`) embedded in prose that describes a multi-step algorithmic process. The gold label is assigning 'algorithm' typ
  - suggested: `# Add to _extract_algorithms, after the existing `found = self._extract_envs(...)` block:  # Heuristic: catch enumerate environments used as algorithmic procedu`

### definition (51 items)

- **paper001 / definition** — `Given a set of data points $x_1,\hdots x_n$ and some notion of similarity $s_{ij} \geq 0$ between all pairs of data points $x_i$ and $x_j$, the intuitive goal o`
  - why missed: This is a paragraph immediately following a \section or \subsection heading that introduces a concept using italic/em markup ('{\em term}') but has no explicit 'Definition N' marker or environment. The pattern is: after 
  - suggested: `# C5: Paragraph after \section/\subsection containing emphasized term {\em ...} or {\textit{...}} # Pattern: after a section/subsection, a non-empty paragraph c`
- **paper001 / definition** — `A subset $A \subset V$ of a graph is connected if any two vertices in $A$ can be joined by a path such that all intermediate points also lie in $A$. A subset $A`
  - why missed: Items 1, 2, 3, 4 share the same structural pattern: a paragraph (or a block delimited by '\\') that begins with a bold term '{\bf TERM:}' or '{\bf TERM}' followed by a colon, then a descriptive paragraph. This is a very 
  - suggested: `# C6: {\bf Term:} or {\bf Term} followed by definitional prose # Pattern: {\bf <name>:} <body> ending at \\\\ or double newline or \begin or \section inline_bf_`
- **paper001 / definition** — `${\bf The $\eps$-neighborhood graph:}$ Here we connect all points whose pairwise distances are smaller than $\eps$. As the distances between all connected point`
  - why missed: Same pattern as item 1: '{\bf TERM:}' introducing a named concept. The C6 pattern added for item 1 will catch this too — '{\bf The $\eps$-neighborhood graph:}'. No additional code needed beyond C6.
  - suggested: `# No additional code needed — covered by the C6 pattern ({\bf Term:} block) added for item 1. # The pattern inline_bf_term_pattern will match '{\bf The $\eps$-n`
- **paper001 / definition** — `${\bf $k$-nearest neighbor graphs:}$ Here the goal is to connect vertex $v_i$ with vertex $v_j$ if $v_j$ is among the $k$-nearest neighbors of $v_i$. However, t`
  - why missed: Same pattern as items 1 and 2: '{\bf $k$-nearest neighbor graphs:}' introducing a named concept. The C6 pattern covers this. No additional code needed.
  - suggested: `# No additional code needed — covered by the C6 pattern ({\bf Term:} block) added for item 1. pass`
- **paper001 / definition** — `${\bf The fully connected graph:}$ Here we simply connect all points with positive similarity with each other, and we weight all edges by $s_{ij}$. As the graph`
  - why missed: Same pattern as items 1, 2, 3: '{\bf The fully connected graph:}' followed by definitional prose. The C6 pattern covers this. No additional code needed.
  - suggested: `# No additional code needed — covered by the C6 pattern ({\bf Term:} block) added for item 1. pass`
- **paper001 / definition** — `There are two matrices which are called normalized graph Laplacians in the literature. Both matrices are closely related to each other and are defined as $\Lsym`
  - why missed: This definition is introduced by 'There are two ... defined as' with a math array (\ba...\ea or align environment) followed by explanatory prose. The phrase 'are defined as' is a passive-voice definitional anchor. The ex
  - suggested: `# Extend C2 anchor to also catch plural 'are defined as/to be' _c2_anchor_plural = re.compile(     r"\bare\s+defined\s+(?:as|to\s+be)\s",     flags=re.IGNORECAS`
- **paper001 / definition** — `A second connection between random walks and graph Laplacians can be made via the commute distance on the graph. The commute distance (also called resistance di`
  - why missed: This definition follows a \subsubsection* heading and opens with 'A second connection ... The TERM (also called ALIAS) ... is defined as ...'. The parenthetical '(also called ALIAS)' pattern combined with 'is defined as'
  - suggested: `# C7: Inline definition via parenthetical '(also called ALIAS)' or '(called ALIAS)' # Pattern: sentence containing '(also called ...)' or '(known as ...)' defin`
- **paper002 / definition** — `a linear code is a given collection of codewords which are vectors $a_1,\ldots, a_n \in \R^m$---the columns of the matrix $A$.`
  - why missed: The pattern here is an inline definition introduced by an italicized/emphasized term followed by a semicolon and an explanatory clause: '\emph{term}; term is a ...' or 'a \emph{term}; a term is ...'. The key structural a
  - suggested: `# C5: '{\em term}; term is ...' or '\emph{term}; ... term is ...' # Structural pattern: italicized term introduced inline, then defined after semicolon _c5_patt`
- **paper002 / definition** — `the object of interest is {\em compressible} in the sense that the reordered entries of $\alpha$ decay like a power-law; concretely, suppose that the entries of`
  - why missed: The pattern here is a multi-sentence inline definition introduced by 'Suppose now that ... is {\em term} in the sense that ...' followed by formal constraints, and then concluded with 'We will denote by X the class/set o
  - suggested: `# C6: 'We (will) denote by X the ...' - standard math definition pattern _c6_pattern = re.compile(     r'(?P<full>'     r'(?:We\s+(?:will\s+)?|[Ll]et\s+us\s+)de`
- **paper002 / definition** — `a {\em random} matrix $F$ obeys the UUP with oversampling factor $\lambda$ if $F$ obeys \begin{equation} \delta_S \le 1/2, \qquad S = \rho \cdot K/\lambda, \end`
  - why missed: The pattern here is an inline definition of the form 'a {\em term} obeys/satisfies [condition] if [formal statement with equation]'. The key structural anchors are: (1) an italicized/emphasized term via {\em} or \emph{},
  - suggested: `# C7: '{\em term} obeys/satisfies ... if ...' - definitional condition pattern _c7_pattern = re.compile(     r'(?P<full>'     r'(?:a\s+|an\s+|the\s+)?'     r'(?`
- **paper004 / definition** — `The notation  $\|\cdot\|_n$ stands for the empirical norm: $$\|g\|_n= \sqrt{\frac1n \sum_{i=1}^n g^2(Z_i)}$$ for any $g:\mathcal Z\to\RR$. We suppose that $\|f_`
  - why missed: The pattern is inline definitional text anchored on 'stands for' (or 'denotes'/'refers to') — a common notation-introduction phrase. The existing C1 pattern requires 'define/Define' and C2 requires 'is defined as'. This 
  - suggested: `# C5: 'X stands for ...', 'X denotes ...', 'X refers to ...' — notation definitions inline_stands_for_pattern = re.compile(     r"(?P<full>"     r"(?P<name>(?:\`
- **paper004 / definition** — `Let $$ \scm(\beta)= \sum_{j=1}^M I_{\{ \beta_j\ne 0\}} = |J(\beta)|$$ denote the number of non-zero coordinates of $\beta$, where $I_{\{ \cdot\}}$ denotes the i`
  - why missed: The pattern is 'Let $EXPR$ denote ...' — a very common math definitional idiom. The existing C4 pattern matches 'Let X be ...' but this uses 'denote' instead of 'be'. We need a new pattern for 'Let X denote ...' which is
  - suggested: `# C6: 'Let X denote ...' — definitional idiom inline_let_denote_pattern = re.compile(     r"(?P<full>"     r"[Ll]et\s+"     r"(?P<name>(?:\$[^$]+\$|[A-Za-z0-9\\`
- **paper004 / definition** — `Introduce the residual sum of squares $$ \wh{S} (\beta) = \frac1n \sum_{i=1}^n \{ Y_i - {\sf f}_{\beta}(Z_i) \}^2,$$ for all $\beta\in\RR^M$.`
  - why missed: The pattern is a sentence starting with 'Introduce ...' followed by a definition (often with a display math block). This is a common imperative-verb definitional pattern in math papers, similar to how authors write 'Intr
  - suggested: `# C7: Imperative sentence 'Introduce ...', 'Set ...' at sentence/paragraph start inline_imperative_pattern = re.compile(     r"(?P<full>"     r"(?:^|(?<=[.\n]))`
- **paper004 / definition** — `Finally for any $n\ge 1$, $M\ge2$, we consider the Gram matrix $$ \Psi_{n} = \frac1n X^TX = \left( \frac1n \sum_{i=1}^n f_j(Z_i) f_{j^\prime} (Z_i) \right)_{ 1\`
  - why missed: The pattern is 'we consider X ... and let Y denote ...' — a two-part sentence introducing objects. The anchor is 'we consider' followed by definitional content. More generally this follows 'Finally for any ...' or simila
  - suggested: `# C8: 'we consider X' or 'consider X' as definitional introduction inline_we_consider_pattern = re.compile(     r"(?P<full>"     r"[Ww]e\s+consider\s+"     r"(?`
- **paper004 / definition** — `For a real number $1\le u\le M$ we introduce the following quantities that we will call {\it restricted eigenvalues}: \begin{equation*} \begin{split} \phi_{\min`
  - why missed: The pattern is 'we introduce the following quantities that we will call {\it NAME}:' followed by an equation environment. This is a named multi-quantity definition introduced with 'introduce ... call ... :'. The existing
  - suggested: `# C9: 'we introduce ... (that we will) call {\it NAME}:' followed by equation inline_introduce_call_pattern = re.compile(     r"(?P<full>"     r"[Ww]e\s+introdu`
- **paper004 / definition** — `Denote by $X_J$ the $n\times |J|$ submatrix of $X$ obtained by removing from $X$ the columns that do not correspond to the indices in $J$, and for $1\le m_1,m_2`
  - why missed: The pattern is 'Denote by X the ... and for ... introduce the following quantities called {\it NAME}:' — a sentence starting with 'Denote by'. This is a very common math pattern. We should add a C10 pattern anchored on '
  - suggested: `# C10: 'Denote by X ...' or 'We denote by X ...' definitional pattern inline_denote_by_pattern = re.compile(     r"(?P<full>"     r"(?:[Ww]e\s+)?[Dd]enote\s+by\`
- **paper004 / definition** — `we consider $f$ satisfying the {\it weak sparsity} property relative to the dictionary $f_1,\dots,f_M$. That is, we assume that there exist an integer $s$ and c`
  - why missed: The pattern is 'we consider X satisfying the {\it PROPERTY} property ... That is, we assume that ... \begin{equation} ... \end{equation} ...' — a property/assumption definition introduced with 'That is, we assume'. The a
  - suggested: `# C11: 'That is, we assume/say/require ...' — formal definition of a named property inline_that_is_pattern = re.compile(     r"(?P<full>"     r"(?P<name>[^.\n]{`
- **paper005 / definition** — `In what follows, $\langle \cdot,\cdot \rangle$ stands for the Frobenius dot-product. For two histograms $r$ and $c$ in the simplex $\Sigma_d\defeq \{x\in \RR^d_`
  - why missed: This is a multi-sentence definitional paragraph introduced after a \subsection heading. The pattern is: \subsection{...} followed by inline prose that uses 'we write X for ..., namely ...' or 'X denotes ...' style langua
  - suggested: `# C5: 'we write X for Y, namely ...' definitional pattern inline_we_write_pattern = re.compile(     r"(?P<full>"     r"[Ww]e\s+write\s+"     r"(?P<name>(?:\$[^$`
- **paper005 / definition** — `We define the entropy $h$ and the Kullback-Leibler divergences of these tables and their marginals as $\begin{gather*}$ $r\in\Sigma_d,\quad$ $h(r)=-\sum_{i=1}^d`
  - why missed: This definition uses 'We define X as \begin{gather*}...\end{gather*}', i.e. the definitional sentence ends not with a period but with a display math environment (\begin{gather*}...\end{gather*}). The existing C1 inline_d
  - suggested: `# C1b: 'We define X as \begin{env}...\end{env}' — definition whose body is a display environment inline_define_env_pattern = re.compile(     r"(?P<full>"     r"`
- **paper005 / definition** — `This bound is tight, since the table $rc^T$ -- known as the independence $table~\citep{good1963maximum}$ -- has an entropy of $h(rc^T)=h(r)+h(c)$. By the concav`
  - why missed: This definition is introduced by 'we can introduce the convex set X as $$...$$', i.e. the pattern is 'we (can) introduce X as $$ display math $$'. The existing patterns don't cover 'introduce' as a definitional verb. A g
  - suggested: `# C6: 'we (can) introduce X as $$ ... $$' definitional pattern inline_introduce_pattern = re.compile(     r"(?P<full>"     r"[Ww]e\s+(?:can\s+)?(?:also\s+)?intr`
- **paper006 / definition** — `\, x)$ is $\statprob$-integrable, the \emph{population risk} $\popfun : \optvarspace \rightarrow \R$ is given by \begin{equation} \popfun(\optvar) \defeq \E_\st`
  - why missed: This pattern is: a noun phrase introduced by 'the \emph{...}' (or similar emphasis) followed by a math expression, then 'is given by' or 'is defined by/as', followed by an equation environment. The key structural anchor 
  - suggested: `# C5: 'X is given by \begin{equation}...\end{equation}' style inline definitions # Anchor: 'is given by' or 'is defined by' immediately before an equation env _`
- **paper006 / definition** — `$\samples$ of samples from the distribution $\statprob$. Empirical risk minimization is based on estimating $\optvar^*$ by solving the optimization problem \beg`
  - why missed: This pattern is: a sentence ending with 'by solving the optimization problem' (or 'via' / 'as follows' / 'by') immediately before a \begin{equation} block — essentially a definition of a quantity through the equation tha
  - suggested: `# C5b: 'X is based on ... by solving \begin{equation}...\end{equation}' style # Generalizes to any 'introduced/defined via/by/as follows' + equation block _c5b_`
- **paper006 / definition** — `\neq j$. In addition, for each processor $i$ we define the (local) empirical distribution $\statprob_{1,i}$ and empirical objective $F_{1,i}$ via \begin{equatio`
  - why missed: This is already partially caught by C1 (inline_define: 'we define X via \begin{equation}'). The issue is that C1's pattern uses '[^.]*\.' as the tail, which doesn't span \begin{equation}...\end{equation} blocks (it stops
  - suggested: `# C1b: 'we define X via/by/as \begin{equation}...\end{equation}' # Handles cases where the definition body IS the equation block inline_define_eqn_pattern = re.`
- **paper006 / definition** — `particular, under suitable regularity conditions~\citep[e.g.][Chapter 6]{LehmannCa98}, we can define the Fisher information matrix \begin{equation*} \informatio`
  - why missed: This pattern is 'we can define X \begin{equation*}...\end{equation*}'. The existing C1 pattern requires 'define NAME as/by/to be/=/...' but here there is no such connector — the name ('the Fisher information matrix') is 
  - suggested: `# C1c: 'define X \begin{equation}' with no explicit connector (as/by/to be) # Catches: 'we can define the Fisher information matrix \begin{equation*}...' inline`
- **paper006 / definition** — `A convex function $F$ is $\strongparam$-strongly convex on a set $U \subseteq \R^d$ if for arbitrary $u, v \in U$ we have \begin{equation*} F(u) \ge F(v) + \<\n`
  - why missed: This is a structural definition introduced by an adjective predicate pattern: 'A [noun phrase] is [CONDITION] if [criterion] \begin{equation*}...\end{equation*}'. The structural anchor is: sentence starting with a capita
  - suggested: `# C6: 'A/An X is [property] if ... \begin{equation}...\end{equation}' # Catches property/condition definitions: 'A convex function F is alpha-strongly convex if`
- **paper007 / definition** — `The kernel $K$ is \emph{positive definite with respect to  $|| \cdot ||_{p^{in}} $}  if $ || f ||_{p^{in}} > 0 \implies || f ||_K > 0$.`
  - why missed: The pattern here is an inline definition introduced by a bold/italic term followed by 'if' or 'when', preceded by a sentence that sets up the term. More specifically, the structure is: a noun phrase (optionally with math
  - suggested: `# C5: 'The X is \emph{property name} if <condition>.' pattern inline_emph_if_pattern = re.compile(     r"(?P<full>"     r"[A-Z][^.]{0,120}?"     r"\\(?:emph|tex`
- **paper007 / definition** — `For ANNs trained using gradient descent on the composition $C \circ F^{(L)}$, the situation is very similar to that studied in the Section \ref{sec:rfa}. During`
  - why missed: The pattern here is a named concept introduced via \emph{name} (or \textbf{name}) often followed by an abbreviation in parentheses like (NTK), where the definition spans a display equation ($$...$$) or align environment.
  - suggested: `# C6: '...the \emph{term} (ABBR)\n$$...$$' or '...with respect to the \emph{term}\n$$...$$' # Pattern: a sentence fragment ending with \emph{name} (opt abbrev) `
- **paper007 / definition** — `Given a goal function $f^*$ and input distribution $p^{in}$, the least-squares regression cost is $$  C(f) = \frac{1}{2} ||f - f^*||^2_{p^{in}} = \frac{1}{2}\ma`
  - why missed: The pattern here is a section or paragraph opening with 'Given <context>, the <X> [cost/norm/function/...] is $$...$$'. This is a common definitional pattern in math papers where a quantity is introduced via a display eq
  - suggested: `# C7: 'The <noun phrase> is\n$$...$$' or 'Given ..., the <noun> is\n$$...$$' # Sentence ending with 'is' (or 'is given by'/'is defined as') followed by display `
- **paper007 / definition** — `A natural choice of convergence to study the NTK is with respect to the operator norm on kernels: $$ \lVert K \rVert_{op} = \max_{\lVert f \rVert_{p^{in}} \leq `
  - why missed: The pattern here is 'A natural choice of <X> is ... $$...$$, where ...' - a definitional sentence that introduces a norm/metric/quantity with a display equation followed by a 'where' clause. More generally, this is: a se
  - suggested: `# C8: '... <noun phrase>:\n$$...$$\nwhere ...' - definition via display math + where-clause # Also catches 'X is with respect to the <name>: $$...$$' inline_dis`
- **paper010 / definition** — `The predictor $h_n$ is commonly chosen from some function class $\cH$, such as neural networks with a certain architecture, using \emph{empirical risk minimizat`
- **paper010 / definition** — `The challenge stems from the mismatch between the goals of minimizing the empirical risk (the explicit goal of ERM algorithms, optimization) and minimizing the `
- **paper010 / definition** — `The \emph{double descent risk curve}, which incorporates the U-shaped risk curve (i.e., the ``classical'' regime) together with the observed behavior from using`
- **paper010 / definition** — `We first consider a popular class of non-linear parametric models called \emph{Random Fourier Features} (\emph{RFF})~\cite{rahimi2008random}, which can be viewe`
- **paper010 / definition** — `Specifically, the Random ReLU features model family $\cHN$ with $N$ parameters consists of functions $h \colon \R^d \to \R$ of the form \[ h(x) = \sum_{k=1}^N a`
- **paper010 / definition** — `Consider the class $\cH$ of periodic complex-valued functions on the interval $[0,2\pi]$, and let \[ e_k(x) := \exp(\sqrt{-1}(k{-}1)x) \] for positive integers `
- **paper012 / definition** — `Diffusion models~\citep{sohl2015deep} are latent variable models of the form $p_\theta(\bx_0) \defeq \int p_\theta(\bx_{0:T}) \,d\bx_{1:T}$, where $\bx_1, \dots`
  - why missed: This definition is a prose paragraph in a \section{} or \subsection{} that introduces a named concept using the pattern 'X is called the \emph{NAME}, and it is defined as ...'. The existing C2 anchor 'is defined as/to be
  - suggested: `# C5: 'is called \emph{NAME}[,...] and (it) is defined as ...' # Also catches: 'called the \emph{NAME}' even without 'and is defined' # Structural pattern: \emp`
- **paper012 / definition** — `To obtain discrete log likelihoods, we set the last term of the reverse process to an independent discrete decoder derived from the Gaussian $\mathcal{N}(\bx_0 `
  - why missed: This definition consists of a prose sentence ending with a colon that introduces a set of equations inside \begin{align}\begin{split}...\end{split}\end{align}, followed by a 'where ...' clause. The content defines functi
  - suggested: `# C6: Colon-introduced display math definition. # Pattern: sentence ending ':' that contains definitional language, # followed by \begin{align/equation/...}...\`
- **paper013 / definition** — `A vector field $v_t$ can be used to construct a time-dependent diffeomorphic map, called a \emph{flow}, $\phi:[0,1]\times \Real^d \too \Real^d$, defined via the`
  - why missed: Item 0 is a multi-paragraph prose block that introduces a named concept via 'called a \emph{...}' followed by '... is defined by/via ...'. The gold text spans from 'A vector field ...' through the final display equation.
  - suggested: `# C5: '... called a \emph{Name} ...' definitional pattern inline_called_emph_pattern = re.compile(     r"(?P<full>"     r"[A-Z][^.\n]{0,300}?"     r"(?:called|k`
- **paper013 / definition** — `Namely, we consider conditional probability paths of the form \begin{equation} p_t(x\vert x_1) = \gN(x\, \vert\, \mu_t(x_1), \sigma_t(x_1)^2 I ), \end{equation}`
  - why missed: Item 1 is a prose paragraph that introduces a mathematical construction with 'we consider ... of the form' followed by a display equation, then elaborates the components. The recurring structural pattern is: 'we consider
  - suggested: `# C6: 'we consider/define/study X of the form \begin{equation}...' pattern inline_of_the_form_pattern = re.compile(     r"(?P<full>"     r"(?:we\s+)?(?:consider`
- **paper014 / definition** — `When a neural network is used for the recognition model, we arrive at the \emph{variational auto-encoder}.`
  - why missed: No context found (not_found_in_tex)
- **paper014 / definition** — `For the purpose of solving the above problems, let us introduce a recognition model $\qPhi(\bz|\bx)$: an approximation to the intractable true posterior $\pT(\b`
  - why missed: This definition is introduced by 'let us introduce a <term> ...' pattern — a multi-sentence paragraph starting with 'let us introduce'. The existing C4 pattern only handles 'Let X be ...' with a single-word/math name the
  - suggested: `# C5: 'let us introduce [a/an/the] <name> ...' definitional introduction inline_let_us_introduce_pattern = re.compile(     r"(?P<full>"     r"[Ll]et\s+us\s+intr`
- **paper014 / definition** — `From a coding theory perspective, the unobserved variables $\bz$ have an interpretation as a latent representation or \emph{code}. In this paper we will therefo`
  - why missed: This definition uses 'we will (also) refer to X as Y' — a standard mathematical naming/definition pattern. The existing patterns don't cover this. A new pattern anchored on 'refer to ... as' (with optional 'also', 'there
  - suggested: `# C6: 'we will (also/therefore/henceforth) refer to <X> as <name>' inline_refer_to_pattern = re.compile(     r"(?P<full>"     r"[Ww]e\s+(?:will\s+)?(?:also\s+|t`
- **paper014 / definition** — `The first RHS term is the KL divergence of the approximate from the true posterior. Since this KL-divergence is non-negative, the second RHS term $\LB{}{\bxi}$ `
  - why missed: This definition uses 'X is called the/a <name>' — the passive 'is called' naming pattern. The existing C2 pattern covers 'is defined as/to be' but not 'is called'. A new pattern anchored on 'is called' with a look-back f
  - suggested: `# C7: '<X> is called the/a/an <name>' _c7_anchor = re.compile(     r"\bis\s+called\s+(?:the\s+|a\s+|an\s+)?",     flags=re.IGNORECASE, )  for anchor_m in _c7_an`
- **paper014 / definition** — `The essential parameterization trick is quite simple. Let $\bz$ be a continuous random variable, and $\bz \sim \qPhi(\bz|\bx)$ be some conditional distribution.`
  - why missed: This definition starts with 'The essential X is quite simple. Let $z$ be a continuous random variable...' — it's a multi-sentence paragraph that begins with a framing sentence and then uses 'Let X be ...' in a definition
  - suggested: `# Extend definition_keywords to include 'variable' and related terms # so that C4 fires on 'Let $z$ be a continuous random variable ...' definition_keywords = r`
- **paper015 / definition** — `To learn the generator's distribution $p_g$ over data $\bm{x}$, we define a prior on input noise variables $p_{\bm{z}}(\bm{z})$, then represent a mapping to dat`
  - why missed: The missed definition is a multi-sentence paragraph that starts with 'we define' and continues across several sentences (including ones that don't end with a period immediately after the define clause). The current C1 pa
  - suggested: `# C5: Multi-sentence paragraph starting with 'we define' / 'we also define' # Captures from the start of the sentence containing 'we define' through # the end o`
- **paper016 / definition** — `A Transformer block is a sequence-to-sequence function mapping $\reals^{d \times n}$ to $\reals^{d \times n}$. It consists of two layers: a self-attention layer`
  - why missed: This is a subsection-level block definition: a term (bolded or plain noun phrase at start of a paragraph) followed by 'is a ...' sentence and then an align/equation environment. The pattern is: a capitalized term at the 
  - suggested: `# C5: "<Term> is a/an ..." paragraph-level definition containing a display math block # Structural anchor: sentence starting near paragraph boundary with 'X is `
- **paper016 / definition** — `Next, we present our theorem on Transformers with \emph{positional encodings}. In order to endow the Transformer networks with the ability to capture the inform`
  - why missed: This definition introduces a named set/class using 'Consider the functions/objects ...' followed by a display math environment containing \defeq (or :=, =). The general structural pattern is: a sentence ending with a col
  - suggested: `# C6: "Consider the <things> ...:" followed immediately by a display math definitional block # Structural anchor: 'Consider' lead sentence + display equation wi`
- **paper016 / definition** — `\begin{align*} \overline{\mc F}_{\rm PE}(\delta) \defeq \left \{ f: \mX \mapsto \sum\nolimits_{\mL \in \sG_{\delta}} \mA_\mL \indic{\mX \in \sS_\mL} \mid f \tex`
  - why missed: This definition uses the pattern 'we define the following <class/set/object>' (or 'we define ... as follows') immediately before a display math environment containing a definitional operator (\defeq, :=, \triangleq). The
  - suggested: `# C7: "we define the following ... " + display math block with definitional operator # Catches: 'we define the following class of ... \begin{align*} X \defeq ..`
- **paper016 / definition** — `Given token embeddings $\mX$ as input, the bi-linear projection layer computes the following update. \begin{equation*} {\rm BProj}(\mX) = \mX + \mW_O \cdot \mX `
  - why missed: This is a subsection-level informal definition introduced by a \subsection heading and a paragraph of the form '<Name> computes/defines the following update:' followed by an equation. The general pattern is: a paragraph 
  - suggested: `# C8: "<Name> computes/defines/involves the following update/operation ..." + display math # Structural anchor: technical noun phrase + active verb + 'the follo`
- **paper016 / definition** — `A depth-wise convolution layer \citep{sifre2014rigid,chollet2017xception,kaiser2017depthwise} involves convolving each dimension of $\mX$ with a corresponding c`
  - why missed: This is structurally identical to Item 3: a subsection introduces a named architectural component, and the definition body is a paragraph starting with '<Name> involves/computes ...' + display math. The C8 pattern added 
  - suggested: `# Extension of C8 / new C8b: '<Name> involves/computes <description>:' + display math # without requiring 'the following' inline_computes_direct_pattern = re.co`
- **paper016 / definition** — `\noindent{\bf Average attention.}~An average attention layer replaces the self-attention layer, and just computes the average of projections of all the other to`
  - why missed: This is a \noindent{\bf <Term>.}~ ... informal definition paragraph — a very common LaTeX pattern for inline definitions in ML/math papers. The structure is: \noindent{\bf <Name>.}~<description sentence(s)>. We add a new
  - suggested: `# C9: \noindent{\bf <Name>.}~ definition paragraphs # Very common in ML papers for informal component definitions inline_noindent_bf_pattern = re.compile(     r`

### proof (9 items)

- **paper002 / proof** — `Observe first that standard convex arguments give that there exists at least one minimizer $d = (d_j)_{j \in J}$ to the problem $(P_1)$. We need to prove that $`
  - why missed: The missed proof is not inside a \begin{proof}...\end{proof} environment. Instead, it appears under a subsection heading of the form '\subsection{Proof of ...}' and runs until the next sectioning command or end of docume
  - suggested: `# Add this block inside _extract_proofs, after the inline_proof_pattern block:  subsection_proof_pattern = re.compile(     r'\\(?:sub)*section\s*\*?\s*\{\s*Proo`
- **paper004 / proof** — `Consider a partition $J_0^c$ into subsets of size $m$, with the last subset of size $\le m$: $J_0^c=\cup_{k=1}^K J_k$ where $K\ge 1$, $|J_k|=m$ for $k=1,\dots,K`
  - why missed: This proof is written as a plain-text header using the pattern `{\sc Proof of ...}.` (small caps via `\sc`) followed by the proof body, rather than a `\begin{proof}...\end{proof}` environment. The general structural patt
  - suggested: `# Add this block inside _extract_proofs, after the inline_proof_pattern block:  sc_proof_pattern = re.compile(     r'\{\\sc\s+Proof[^}]*\}\.?\s*'     r'(.*?)'  `
- **paper005 / proof** — `$\emph{Proof of Theorem~\ref{theo:metric}.}$ The symmetry of $d_{M,\alpha}$ is a direct result of $M$'s symmetry. Let $x,y,z$ be three elements in $\Sigma_d$. L`
  - why missed: This proof is written inline (not in a \begin{proof}...\end{proof} environment) but starts with \emph{Proof of ...} followed by content ending at a \blacksquare or section boundary. The existing inline pattern only catch
  - suggested: `# Add this block inside _extract_proofs, after the inline_proof_pattern block  standalone_emph_proof_pattern = re.compile(     r'(?:^|(?<=\n\n))'           # st`
- **paper011 / proof** — `\begin{align*} \Prb{}{\Uc \vee \Vc} &= \Prb{}{\Vc} + \Prb{}{\Uc \mid \neg \Vc} \Prb{}{\neg \Vc}\\ &\ge \Prb{}{\Uc \mid \neg \Vc} \Prb{}{\Vc} + \Prb{}{\Uc \mid \`
  - why missed: The base method uses re.DOTALL with a lazy match between \begin{proof} and \end{proof}, but the body contains a nested \begin{align*}...\end{align*} environment. The issue is that the base regex uses \1 backreference for
  - suggested: `# Minimal addition: replace body pattern in _extract_envs (or add a separate # nested-aware proof extractor) to handle proofs whose body is entirely a # nested `
- **paper012 / proof** — `Below is a derivation of \cref{eq:vb}, the reduced variance variational bound for diffusion models. This material is from \citet{sohl2015deep}; we include it he`
  - why missed: This proof is not inside a \begin{proof}...\end{proof} environment. Instead, it appears in a dedicated section (e.g. 'Extended derivations', 'Derivations', 'Proofs') and consists of introductory prose followed by one or 
  - suggested: `# Minimal addition: capture proof-like content inside sections with derivation/proof titles. # Add this branch at the end of _extract_proofs, before the final r`
- **paper012 / proof** — `The following is an alternate version of $L$. It is not tractable to estimate, but it is useful for our discussion in \cref{sec:coding}. \begin{align} L &= \Eb{`
  - why missed: This proof is a standalone math derivation block: introductory prose (one or two sentences ending with a period) immediately followed by \begin{align}...\end{align} (or similar display math env), appearing between two su
  - suggested: `# Minimal addition: capture prose-introduced math derivation blocks. # Pattern: sentence(s) of prose followed immediately by a display math environment. # Bound`
- **paper014 / proof** — `A proof is as follows. Given the deterministic mapping $\bz = \gPhi(\beps, \bx)$ we know that $\qPhi(\bz|\bx) \prod_i d z_i = p(\beps) \prod_i d \epsilon_i$. Th`
  - why missed: This is an inline proof introduced by the phrase 'A proof is as follows.' (or similar variants like 'The proof is as follows.', 'Proof is as follows.') directly in running text — not inside any environment. The existing 
  - suggested: `inline_proof_as_follows_pattern = re.compile(     r'(?:^|(?<=\n\n)|(?<=\\par\s))'  # paragraph boundary     r'(?:[Aa]\s+)?[Pp]roof\s+is\s+as\s+follows\.?\s*'   `
- **paper014 / proof** — `Here we give the solution when both the prior $\pT(\bz) = \mathcal{N}(0,\bI)$ and the posterior approximation $\qPhi(\bz|\bxi)$ are Gaussian. Let $J$ be the dim`
  - why missed: This proof appears inside a dedicated \section{...} whose title signals it is a derivation/solution/proof — e.g. 'Solution of ...', 'Derivation of ...', 'Proof of ...'. The content is the entire section body (not wrapped
  - suggested: `section_proof_pattern = re.compile(     r'\\(?:sub)*section\*?\{\s*(?:Proof|Solution|Derivation|Verification)\b[^}]*\}'     r'\s*(?:\\label\{[^}]*\})?\s*'     r`
- **paper014 / proof** — `Derivation of the estimator: \begin{align*} \frac{1}{\pT(\bxi)} &= \frac{\int q(\bz) \,d\bz}{\pT(\bxi)} = \frac{\int q(\bz) \frac{\pT(\bxi, \bz) }{\pT(\bxi, \bz`
  - why missed: This proof appears as a paragraph that begins with a proof-introduction phrase like 'Derivation of the estimator:', 'Derivation:', 'Proof:', etc., followed immediately by math content (often an align* environment). The p
  - suggested: `inline_derivation_pattern = re.compile(     r'(?:(?<=\n\n)|(?:^))'     r'(?:[A-Z][a-zA-Z]*\s+)?(?:Derivation|Proof|Justification|Verification)(?:\s+of\s+[^:\n]{`

### simpleenv (56 items)

- **paper001 / remark** — `As a general recommendation we suggest to work with the $k$-nearest neighbor graph as the first choice. It is simple to work with, results in a sparse adjacency`
  - why missed: Items 0-3 are all free-standing paragraphs (no \begin/\end environment) that the gold labels as 'remark'. They appear as plain text blocks between section/subsection headings or paragraph breaks. There is no LaTeX enviro
  - suggested: `# Items 0-3 are plain prose paragraphs with no \begin/\end wrapper and no # bold/italic keyword marker — no general structural anchor exists. # The closest gene`
- **paper001 / remark** — `Additionally, one tool which is particularly designed for spectral clustering is the eigengap heuristic, which can be used for all three graph Laplacians. Here `
  - why missed: Same situation as item 0 — a free prose paragraph with no LaTeX environment wrapper and no bold/italic keyword prefix. No general structural anchor is present. Same proposed general rule applies.
  - suggested: `# Same as item 0: plain prose paragraph, no \begin/\end, no inline keyword marker. # No general structural regex can catch this without content-based heuristics`
- **paper001 / remark** — `Looking at the differences between the two normalized spectral clustering algorithms using $\Lrw$ and $\Lsym$, all three explanations of spectral clustering are`
  - why missed: Same as items 0 and 1. Free prose paragraph, no environment wrapper, no structural marker. Cannot be generically extracted.
  - suggested: `# Same as items 0 and 1. No actionable minimal addition beyond the inline # keyword pattern already proposed. pass`
- **paper001 / remark** — `In contrast to the clear convergence statements for normalized spectral clustering, the situation for unnormalized spectral clustering is much more unpleasant. `
  - why missed: Same as items 0-2. Free prose paragraph, no environment, no structural marker. The only difference is it starts with 'In contrast to...' which is pure prose. Cannot be caught generically.
  - suggested: `# Same as items 0-2. No actionable minimal addition. pass`
- **paper001 / example** — `This toy data set consists of a random sample of 200 points $x_1,\hdots,x_{200} \in \R$ drawn according to a mixture of four Gaussians. The first row of Figure `
  - why missed: Item 4 is also a free prose paragraph labeled 'example' in the gold data, with no \begin{example}...\end{example} wrapper. It appears after 'we would like to illustrate its principle on a very simple toy example.' A gene
  - suggested: `INLINE_EXAMPLE_PATTERN = re.compile(     r'(?:^|\n)\s*'     r'(?:\\textbf{(?:Example|Illustration)}|\\textit{(?:Example|Illustration)}'     r'|(?:Example|Illust`
- **paper001 / example** — `For instance, the authors consider a very simple class of graphs called ``cockroach graphs''. Those graphs essentially look like a ladder, with a few rimes remo`
  - why missed: Item 5 is another free prose paragraph labeled 'example', introduced by 'For instance, the authors consider...' — a content phrase, not a structural LaTeX marker. No \begin/\end wrapper exists. The same inline example pa
  - suggested: `# Item 5: free prose paragraph starting with 'For instance,...' # No structural LaTeX anchor. The INLINE_EXAMPLE_PATTERN from item 4 # is the closest general ru`
- **paper002 / remark** — `It is likely that one may push the condition $\delta_S + \theta_{S,S} + \theta_{S,2S} < 1$ a little further. The key idea is as follows. Each vector $w_n$ in th`
  - why missed: The remark is written as a freestanding bold-text paragraph using '{\bf Remark.}' (or equivalently '\textbf{Remark.}') rather than a \begin{remark}...\end{remark} environment. The general pattern is: a paragraph starting
  - suggested: `# Add to _extract_simple_envs or as a separate helper method # Catches freestanding bold-keyword paragraphs like {\bf Remark.} ... or \textbf{Remark.} ...  BOLD`
- **paper002 / remark** — `Lemma \ref{erp-3} actually solves the dual recovery problem. Indeed, our result states that one can find a vector $w \in H$ obeying both properties (i) and (ii)`
  - why missed: Item 1 is prose text (not inside any LaTeX environment) that appears between a \end{proof} and a \subsection. It is a running paragraph, not wrapped in any \begin/\end. There is no structural marker (bold keyword, etc.) 
  - suggested: `# Item 1 has NO structural anchor (no bold/italic keyword, no \begin/\end env). # The closest safe generalization: catch paragraphs starting with an explicit # `
- **paper002 / example** — `if the fraction of the corrupted entries is too large, then of course we have no hope of reconstructing $f$ from $Af+e$; for instance, assume that $m = 2n$ and `
  - why missed: Item 2 is inline prose — a paragraph of running text, not inside any LaTeX environment and with no bold/italic keyword marker. The text contains the phrase 'This simple example shows...' but anchoring on that would be co
  - suggested: `# Item 2 is freestanding prose with no LaTeX structural marker (no \begin/\end, # no bold/italic keyword). It cannot be caught by a general structural regex. # `
- **paper004 / remark** — `The approximate equivalence is essentially that of the rates as Theorem \ref{th1} exhibits. A statement free of $\scm(\beta)$ holds for linear regression, see d`
  - why missed: Item 0 is a remark introduced by '\noindent{\sc Remark.}' (or '\noindent{\sc Remarks.}') followed by free text until the next \section, \noindent{\sc ...}, or similar structural break. This is a common LaTeX pattern for 
  - suggested: `# Add to extraction pipeline: a regex for \noindent{\sc Remark[s]?.} ... style remarks _SC_REMARK_PATTERN = re.compile(     r'\\noindent\s*\{\\sc\s+Remarks?\.?\`
- **paper004 / remark** — `Theorems \ref{th4} and \ref{th5} only give non-asymptotic upper bounds on the loss, with some probability and under some conditions. The probability depends on `
  - why missed: Items 1-6 all come from the same structural pattern: a '\noindent{\sc Remarks.}' header followed by a \begin{list}...\end{list} environment, where each \item is an individual remark. The base extractor misses these becau
  - suggested: `# Regex to find \noindent{\sc Remark[s]?.} followed by \begin{list}...\end{list} # and extract each \item as a separate remark _SC_REMARKS_LIST_PATTERN = re.com`
- **paper004 / remark** — `Note that Assumptions RE($s,c_0$) or RE($s,m,c_0$) do not imply identifiability of $\beta^*$ in the linear model (\ref{linmod}). However, the vector $\beta^*$ a`
  - why missed: Same structural pattern as Item 1: a \noindent{\sc Remarks.} list, second \item. The same _extract_sc_remarks_list method handles this since it iterates all \item entries within the matched list environment.
  - suggested: `# No additional code needed beyond what was added for Item 1. # The _extract_sc_remarks_list method already handles all \item entries # within a \noindent{\sc R`
- **paper004 / remark** — `For the smallest value of $A$ (which is $A=2\sqrt{2}$) the constants in the bound of Theorem \ref{th5} for the Lasso are larger than the corresponding numerical`
  - why missed: Same structural pattern as Items 1-2: third \item in the same \noindent{\sc Remarks.} + \begin{list} block. Already handled by _extract_sc_remarks_list.
  - suggested: `# Already covered by _extract_sc_remarks_list from Item 1. pass`
- **paper004 / remark** — `The proofs of Theorems \ref{th4} and \ref{th5} differ mainly in the value of the tuning constant: $c_0=1$ in Theorem \ref{th4} and $c_0=3$ in Theorem \ref{th5}.`
  - why missed: Same structural pattern as Items 1-3: fourth \item in the same \noindent{\sc Remarks.} + \begin{list} block. Already handled by _extract_sc_remarks_list.
  - suggested: `# Already covered by _extract_sc_remarks_list from Item 1. pass`
- **paper004 / remark** — `For the Dantzig selector in the linear regression model and under Assumptions 1 or 2 some further improvement of constants in the $\ell_p$ bounds for the coeffi`
  - why missed: Same structural pattern as Items 1-4: fifth \item. Already handled by _extract_sc_remarks_list.
  - suggested: `# Already covered by _extract_sc_remarks_list from Item 1. pass`
- **paper004 / remark** — `All our results are stated with probabilities at least $1-M^{1-A^2/2}$ or $1-M^{1-A^2/8}$. These are reasonable (but not the most accurate) lower bounds on the `
  - why missed: Same structural pattern as Items 1-5: sixth \item (last one before \end{list}). Already handled by _extract_sc_remarks_list.
  - suggested: `# Already covered by _extract_sc_remarks_list from Item 1. pass`
- **paper004 / assumption** — `For some integer $s$ such that $1\le s\le M$,  and a positive number $c_0$ the following condition holds: $$ \kappa(s, c_0) \triangleq \min_{\substack{J_0\subse`
  - why missed: Item 7 is an assumption presented inside a \begin{description}...\end{description} environment with a \item[Assumption ...] label. The body is the description item content. The general pattern is: \begin{description}\ite
  - suggested: `# Regex for \begin{description}...\item[Assumption ...]...\end{description} _DESCRIPTION_ASSUMPTION_PATTERN = re.compile(     r'\\begin\{description\}'     r'(?`
- **paper004 / assumption** — `For integers $s,m$ such that $1\le s \le M/2$ and $m\ge s$, $s+m\le M$, a vector $\bD\in \RR^M$ and a set of indices $J_0\subseteq \{1,\dots,M\}$ with $|J_0|\le`
  - why missed: This assumption is defined inside a LaTeX `description` environment using `\item[Assumption ...]`. The pattern is `\begin{description}\item[Assumption ...]: body \end{description}`. We need a regex that catches `\begin{d
  - suggested: `DESCRIPTION_ASSUMPTION_PATTERN = re.compile(     r'\\begin\{description\}'     r'\s*\\item\[(?P<label>Assumption[^\]]*)\]'     r'(?P<body>.*?)'     r'\\end\{des`
- **paper004 / assumption** — `Assume $$ \phi_{\min}(2s) > c_0\theta_{s,2s} $$ for some integer $1\le s \le M/2$ and a constant $c_0>0$.`
  - why missed: Same pattern as Item 0: `\begin{description}\item[Assumption N:]` body `\end{description}`. The general description-environment assumption extractor from Item 0 handles this case as well.
  - suggested: `# Same fix as Item 0 — the DESCRIPTION_ASSUMPTION_PATTERN and _extract_description_assumptions # method already handle this case (\begin{description}\item[Assum`
- **paper004 / assumption** — `Assume $$ m\phi_{\min}(s+m) > c_0^2 s\phi_{\max}(m) $$ for some integers $s,m$ such that $1\le s \le M/2$, $m\ge s$, and $s+m\le M$, and a constat $c_0>0$.`
  - why missed: Same pattern as Items 0 and 1: `\begin{description}\item[Assumption N:]` body `\end{description}`. Covered by the general description-environment assumption extractor.
  - suggested: `# Same fix as Item 0 — the DESCRIPTION_ASSUMPTION_PATTERN and _extract_description_assumptions # method already handle this case (\begin{description}\item[Assum`
- **paper004 / assumption** — `For an integer $s$ such that $1\le s \le M$ we have $$ \phi_{\min}(s) > 2c_0 \theta_{s,1} \sqrt{s} $$ where $c_0>0$ is a constant.`
  - why missed: This assumption uses the pattern `\noindent {\bf Assumption N.} {\it body}` — an inline bold/italic formatting pattern, not a LaTeX environment. We need a regex anchored on `\noindent` + `\textbf` or `{\bf` + 'Assumption
  - suggested: `NOINDENT_ASSUMPTION_PATTERN = re.compile(     r'\\noindent\s*'     r'(?:\{\\bf\s+|\\textbf\{)'     r'(?P<label>Assumption[^.}]*)'     r'(?:\}|\.)'     r'[^{]*' `
- **paper004 / assumption** — `For an integer $s$ such that $1\le s \le M$ we have \begin{equation*}\begin{split} \phi_{\min}(s) > 2c_0 \theta_{1,1} s \end{split}\end{equation*} where $c_0>0$`
  - why missed: Same pattern as Item 3: `\noindent {\bf Assumption N.} {\it body}`. The NOINDENT_ASSUMPTION_PATTERN extractor from Item 3 handles this generically.
  - suggested: `# Same fix as Item 3 — the NOINDENT_ASSUMPTION_PATTERN and _extract_noindent_assumptions # method already handle this case (\noindent {\bf Assumption N.} {\it .`
- **paper004 / assumption** — `All the diagonal elements of the Gram matrix $\Psi_n$ are equal to 1 and for an integer $s$ such that $1\le s \le M$ we have \begin{equation}\begin{split} \thet`
  - why missed: Same pattern as Items 3 and 4: `\noindent {\bf Assumption N.} {\it body}`. Covered by the NOINDENT_ASSUMPTION_PATTERN extractor.
  - suggested: `# Same fix as Item 3 — the NOINDENT_ASSUMPTION_PATTERN and _extract_noindent_assumptions # method already handle this case (\noindent {\bf Assumption 5.} {\it .`
- **paper005 / remark** — `With a naive approach, $d_{M,\alpha}$ can be obtained by computing $d_{M}^\lambda$ iteratively until the entropy of the solution $P^\lambda$ has reached an adeq`
  - why missed: Item 0 is a remark embedded inside a \subsection{...} heading — the text immediately follows the subsection title on the same line, with no \begin{remark}...\end{remark} wrapper. This is a free-standing paragraph-level r
  - suggested: `# Item 0: The missed content lives inside a \subsection{...} whose title is # paper-specific math notation — there is no generic structural marker # (keyword, e`
- **paper005 / remark** — `$\emph{Remark.}$ The proof above suggests a faster way to compute the Independence kernel. Given a matrix $M$, one can indeed pre-compute the vector of norms $u`
  - why missed: Item 1 is a remark written as inline text with an italic/emphasized label pattern: '\emph{Remark.}' (or variants like '\textit{Remark.}', '\textbf{Remark.}') followed by body text, not wrapped in any \begin/\end environm
  - suggested: `import re from typing import List  # Inline-labeled remark/note pattern: \emph{Keyword.} or \textit{Keyword.} or \textbf{Keyword.} # followed by body text up to`
- **paper006 / remark** — `If we assume $k$th moment bounds instead of $4$th, i.e.\ $\E[\matrixnorm{\nabla^2 f(\optvar^*; \statrv)}_2^k] \le \lipgrad^k$ and $\E[\ltwo{\gradient_t}^k] \le `
- **paper006 / remark** — `convergence guarantee. We remark that an inspection of our proof shows that, at the expense of worse constants on higher order terms, we can reduce the factor o`
- **paper006 / remark** — `The intuition for the weighted estimator~\eqref{eqn:bootstrap-avg-def} is similar to that for standard bias correction procedures using the bootstrap or subsamp`
- **paper006 / example** — `In this section, we report the results of simulation studies comparing the \avgm, \savgm, and \sgdavgm\ methods, as well as a trivial method using only a fracti`
- **paper006 / example** — `Predicting whether a user of a search engine will click on an advertisement presented to him or her is of central importance to the business of several internet`
- **paper011 / remark** — `\textbf{Remark:} note that we allow preprocessing to be randomized as well, and we measure the probability of success over the random coins tossed during \emph{`
  - why missed: All five items share the same structural pattern: a standalone inline remark introduced by \textbf{Remark:} (not wrapped in a \begin/\end environment). The base _extract_envs method only handles \begin{...}...\end{...} b
  - suggested: `import re  # Add to BASE_ENV_KIND_MAP or handle separately: # Inline remark pattern: \textbf{Remark:} ... up to next blank line or \begin INLINE_REMARK_PATTERN `
- **paper011 / remark** — `\textbf{Remark:} for $\mathcal{H}$ to be useful we should have $r_1 < r_2$ and $p_1 > p_2$.`
  - why missed: Same pattern as Item 0: \textbf{Remark:} inline (not in \begin/\end). The same general _extract_inline_remarks method added for Item 0 will catch this too. No additional code needed beyond what was added for Item 0.
  - suggested: `# No additional code needed beyond the _extract_inline_remarks method from Item 0. # The same regex pattern: # r'\\textbf\{Remark[^}]*\}\s*:?\s*(?P<body>(?:(?!\`
- **paper011 / remark** — `\textbf{Remark:} this theorem says that in order to construct a good data structure for the $(c, r)$-ANN it is sufficient to have a $(r, cr, p_1, p_2)$-sensitiv`
  - why missed: Same pattern: \textbf{Remark:} inline text not in any environment. Covered by the general _extract_inline_remarks method from Item 0.
  - suggested: `# No additional code needed beyond the _extract_inline_remarks method from Item 0. pass`
- **paper011 / remark** — `\textbf{Remark:} we could have had $O_{\nu}(1 / c^4)$ term in the expression for $\rho$, but we state the theorem with $O_{\nu}(1 / c^3)$ in order to be consist`
  - why missed: Same pattern: \textbf{Remark:} inline text after \end{proof}, not in any environment. Covered by the general _extract_inline_remarks method from Item 0.
  - suggested: `# No additional code needed beyond the _extract_inline_remarks method from Item 0. pass`
- **paper011 / remark** — `\textbf{Remark:} if one is willing to have quasi-linear preprocessing time, then it is possible to modify Algorithm~\ref{two_level_hashing_alg} slightly to achi`
  - why missed: Same pattern: a longer \textbf{Remark:} inline block spanning multiple paragraphs and a display math environment. The body delimiter in the general pattern needs to also stop at section boundaries. The existing pattern s
  - suggested: `# Extend _extract_inline_remarks to also try a multi-paragraph variant # that terminates at \section/\subsection/\paragraph or \begin{known_env}.  def _extract_`
- **paper008 / remark** — `Note that for any constant $\alpha\in (0,1)$, the bound above is $\Ocal(G^2/\lambda T)$. This matches the optimal guarantees in \cite{HazanKa11} up to constant `
  - why missed: Item 0 is a remark-like paragraph that appears in free-flowing prose (not inside a \begin{remark}...\end{remark} block). It starts with 'Note that' right after a \end{theorem}. This is a common pattern in math papers whe
  - suggested: `# Add to BASE_ENV_KIND_MAP or handle via a separate prose-remark extractor. # Minimal addition: a regex for prose paragraphs starting with remark keywords.  PRO`
- **paper008 / example** — `We begin with the following relatively simple example, which shows the essence of the idea. Let $F$ be the $1$-strongly convex function \[ F(\bw) = \frac{1}{2}\`
  - why missed: Item 1 is an inline/prose example: a block of text beginning with 'We begin with the following relatively simple example' (or similar 'the following ... example' phrasing) that is NOT wrapped in a \begin{example}...\end{
  - suggested: `# Prose example extractor pattern PROSE_EXAMPLE_PATTERN = re.compile(     r'(?:^|(?<=\n\n))'     r'(?P<body>(?:We (?:begin with|now (?:present|give|show|conside`
- **paper008 / example** — `In particular, let $F$ be the $1$-strongly convex function \[ F(\bw) = \frac{1}{2}\norm{\bw}^2+\begin{cases} w_1 & w_1\geq 0 \\ -7w_1 & w_1<0\end{cases}, \] ove`
  - why missed: Item 2 is another prose example (same structural pattern as Item 1): a block of running text that describes an example construction, not wrapped in any LaTeX environment. It begins with 'In particular, let F be...' which
  - suggested: `# Extend BASE_ENV_KIND_MAP with additional common example environment names _EXTRA_EXAMPLE_ENVS = [     "exmp", "exmpl", "running-example", "runningexample",   `
- **paper008 / example** — `First, as a simple sanity check, we measured the performance of these algorithms on a simple, strongly convex stochastic optimization problem, which is also smo`
  - why missed: Item 3 is a prose example embedded inside a \section or after an enumerate environment — it's a paragraph in running text that describes an experimental example (a simple sanity check). It begins 'First, as a simple sani
  - suggested: `# Add more experimental/numerical example environment names to the map _EXTRA_EXPERIMENT_EXAMPLE_ENVS = [     "experiment", "Experiment",     "numerical", "Nume`
- **paper008 / assumption** — `In general, we will assume that regardless of how the iterates evolve, it holds that $\E[\norm{\hat{\bg}_t}^2]\leq G^2$ for some fixed constant $G$. Note that t`
  - why missed: Item 4 is a prose assumption: a paragraph in running text that is NOT wrapped in a \begin{assumption}...\end{assumption} environment. It begins 'In general, we will assume that...' which is a very common pattern in math/
  - suggested: `# Prose assumption extractor pattern PROSE_ASSUMPTION_PATTERN = re.compile(     r'(?:^|(?<=\n\n))'     r'(?P<body>'     r'(?:In general,\s+we (?:will )?assume|'`
- **paper012 / remark** — `First, we set $\bSigma_\theta(\bx_t, t) = \sigma_t^2 \bI$ to untrained time dependent constants. Experimentally, both $\sigma_t^2 = \beta_t$ and $\sigma_t^2 = \`
  - why missed: This 'remark' is plain prose — no \begin{remark} wrapper, no \textbf{Remark} leader, no structural marker whatsoever. It is a body paragraph inside a \subsection. The base simpleenv extractor cannot reach it. The only ge
  - suggested: `# No extractable structural pattern exists for this item. # It is unmarked prose with no \begin{remark}, no keyword prefix, # and no other structural delimiter `
- **paper012 / remark** — `In particular, our diffusion process setup in \cref{sec:experiments} causes the simplified objective to down-weight loss terms corresponding to small $t$. These`
  - why missed: Same situation as Item 0: plain prose paragraph with no \begin/\end, no \textbf{Remark} or similar keyword prefix. It sits between a \Cref and a \section heading. No structural anchor distinguishes it from any other body
  - suggested: `# No extractable structural pattern exists for this item. # It is unmarked prose with no \begin{remark}, no keyword prefix, # and no other structural delimiter `
- **paper012 / remark** — `Since our samples are nonetheless of high quality, we conclude that diffusion models have an inductive bias that makes them excellent lossy compressors. Treatin`
  - why missed: Same situation as Items 0 and 1: plain prose paragraph, no environment wrapper, no keyword prefix. The only possible weak structural anchor is that it starts a new paragraph after a sentence ending in a citation, but tha
  - suggested: `# No extractable structural pattern exists for this item. # It is unmarked prose with no \begin{remark}, no keyword prefix, # and no other structural delimiter `
- **paper013 / example** — `Diffusion models start with data points and gradually add noise until it approximates pure noise. These can be formulated as stochastic processes, which have st`
  - why missed: The missed 'example' content is not inside a LaTeX environment like \begin{example}...\end{example}. Instead, it is a paragraph introduced by \paragraph{Example I: ...} (or \paragraph{Example N: ...} more generally). The
  - suggested: `# Add a new extraction method for \paragraph-introduced examples (generalizes to any paper) # This is a STRUCTURAL addition alongside _extract_simple_envs, not `
- **paper013 / example** — `An arguably more natural choice for conditional probability paths is to define the mean and the std to simply change linearly in time, \ie, \begin{equation} \mu`
  - why missed: Same structural pattern as Item 0: the missed 'example' content is introduced by \paragraph{Example II: ...} (no \begin{example}...\end{example} wrapper). The base _extract_envs cannot catch it. The same general \paragra
  - suggested: `# No additional code needed beyond Item 0's _extract_paragraph_examples. # The same pattern: #   r'\\paragraph\{(Example[^}]*)\}(?P<body>.*?)(?=\\paragraph\{|\\`
- **paper014 / remark** — `A connection with auto-encoders becomes clear when looking at the objective function given at eq.~\eqref{eq:estimator2}. The first term is (the KL divergence of`
  - why missed: This remark appears as a plain paragraph in the LaTeX source (not inside any \begin{...}...\end{...} environment). It's preceded and followed by comment lines (%). There is no LaTeX environment wrapping it. The base _ext
  - suggested: `# Item 0: No reliable structural anchor exists for this plain paragraph remark. # It has no \begin{remark}, no bold 'Remark' prefix, no section heading. # Canno`
- **paper014 / example** — `In this section we'll give an example where we use a neural network for the probabilistic encoder $\qPhi(\bz|\bx)$ (the approximation to the posterior of the ge`
  - why missed: The example content lives under a \section{Example: ...} heading (or \subsection{Example}), not inside a \begin{example}...\end{example} environment. The section title starts with the word 'Example'. A general rule: dete
  - suggested: `import re from typing import List  def _extract_section_examples(self, text: str) -> List:     """     Catch examples (and similar kinds) introduced as \\sectio`
- **paper014 / example** — `Take, for example, the univariate Gaussian case: let $z \sim p(z|x) = \mathcal{N}(\mu, \sigma^2)$. In this case, a valid reparameterization is $z = \mu + \sigma`
  - why missed: This example is a plain paragraph starting with 'Take, for example,' — it has no \begin{example} environment and no section heading. There is no structural LaTeX anchor. A general regex for paragraphs introduced by inlin
  - suggested: `# Item 2: Plain inline paragraph starting with 'Take, for example,'. # No \begin{example} environment, no section heading, no bold/emph keyword marker. # A gene`
- **paper014 / example** — `Let the prior over the parameters and latent variables be the centered isotropic Gaussian $\pA(\bT) = \mathcal{N}(\bz; \bzero, \bI)$ and $\pT(\bz) = \mathcal{N}`
  - why missed: The example content appears under \subsection{Example} (no \begin{example} environment). The same _extract_section_examples method from Item 1 handles this pattern: it matches \subsection{Example} and extracts the body u
  - suggested: `# Item 3: Same pattern as Item 1 — content under \subsection{Example}. # The _extract_section_examples method proposed for Item 1 already handles this. # \subse`
- **paper015 / remark** — `In practice, equation~\ref{eq:minimaxgame-definition} may not provide sufficient gradient for $G$ to learn well. Early in learning, when $G$ is poor, $D$ can re`
  - why missed: The missed remark is not wrapped in a LaTeX environment at all — it's plain paragraph text in the document body, not inside any \begin{remark}...\end{remark} (or similar) block. The base _extract_envs method only catches
  - suggested: `# No safe general regex addition is possible for this item. # The content is a plain paragraph with no \begin/\end environment wrapper # and no structural keywo`
- **paper016 / remark** — `At this point, a few remarks about the result in Lemma~\ref{lemma:contextmap} are in order. First, since the Transformer networks are bound to implement permuta`
  - why missed: Item 0 is a free-standing paragraph remark that appears between LaTeX environments (after \end{lemma}, before \subsubsection), not wrapped in any \begin{remark}...\end{remark} environment. The gold text is plain prose pa
  - suggested: `# Item 0: No minimal simpleenv addition possible. # The missed remark is free-standing prose between environments with no \begin{remark}...\end{remark} wrapper.`
- **paper016 / remark** — `We showed in this section that Theorem~\ref{thm:univapprox} requires $O(n(1/\delta)^{dn}/n!)$ Transformer blocks for approximation, where $\delta$ is the width `
  - why missed: Item 1 is another free-standing prose subsection (\subsection{Tightness of constructions}) that contains remark-like discussion. It has no \begin{remark}...\end{remark} wrapper. Like Item 0, there is no structural \begin
  - suggested: `# Item 1: No minimal simpleenv addition possible. # The missed remark is a subsection body paragraph with no \begin{remark}...\end{remark} wrapper. # The simple`
- **paper016 / remark** — `Next, we swap a varying number of the first few self-attention layers in $\BB$ with ${\rm SepConv}$, implemented with filter reuse across dimensions \citep{wu20`
  - why missed: Item 2 is again a free-standing prose paragraph in the document body (inside a section, after a footnote-containing sentence), with no \begin{remark}...\end{remark} wrapper. Same structural issue as Items 0 and 1. Cannot
  - suggested: `# Item 2: No minimal simpleenv addition possible. # The missed remark is free-standing prose with no \begin/\end environment wrapper. # The simpleenv extractor `
- **paper016 / remark** — `Since Lemma~\ref{lemma:contextmap} is one of the major technical contributions of this paper, we provide a short sketch of its proof. The complete proof is pres`
  - why missed: Item 3 is the body of a \subsubsection{Proof sketch of ...} — it is section-body prose, not inside any \begin/\end environment. The same structural limitation applies. However, note that 'proof sketch' or 'sketch' subsec
  - suggested: `# Item 3: No minimal simpleenv addition possible via _extract_envs. # The text is a \subsubsection body (no \begin/\end wrapper). # A general section-title-base`
- **paper016 / example** — `Let us consider a setting where we are interested in embedding two sentences: 1) I am happy; and 2) I am Bob. These sentences are fed to a sequence-to-sequence `
  - why missed: Item 4 is a paragraph that begins with 'Let us consider a setting where...' inside a \subsection body, followed later by \begin{definition}. The gold label says 'example' but there is no \begin{example}...\end{example} w
  - suggested: `# Item 4: No minimal simpleenv addition possible. # The missed example is a free-standing prose paragraph with no \begin{example}...\end{example} wrapper. # The`
- **paper450 / remark** — `The quantity $r_0(\Sigma)$ is an important complexity parameter for covariance estimation problems, where it has been called the `effective $rank'~\cite{v-inaar`
  - why missed: The missed content is free-standing prose in a LaTeX section (between \end{proof} and \begin{lemma}), not wrapped in any \begin/\end environment. It appears to be an informal remark written as plain text after a section 
  - suggested: `# No reliable structural anchor exists for this pattern. # The missed content is plain prose between environments with no \begin/\end wrapper, # no leading keyw`

### theoremlike (42 items)

- **paper001 / problem** — `Given a similarity graph with adjacency matrix $W$, the simplest and most direct way to construct a partition of the graph is to solve the mincut problem. To de`
- **paper001 / problem** — `The two most common objective functions to encode this are $\Ratiocut$ $(\citeNP{HagKah92})$ and the normalized cut $\Ncut$ $(\citeNP{ShiMal00})$. In $\Ratiocut`
- **paper001 / problem** — `$\Ncut(A_1,\hdots,A_k) := \frac{1}{2}\sum_{i=1}^k \frac{W(A_i, \bar A_i)}{\vol(A_i)} = \sum_{i=1}^k \frac{\Cut(A_i, \bar A_i)}{\vol(A_i)}.$`
- **paper001 / problem** — `This can be seen even more explicitly by considering yet another graph cut objective function, namely the $\MinmaxCut$ criterion introduced by $\citeA{DingEtal0`
- **paper002 / problem** — `(P'_1) \quad \quad \min_{g \in \R^n} \|y - A g\|_{\ell_1}.`
  - why missed: No context found (not_found_in_tex)
- **paper002 / problem** — `\min 1^T t , \qquad -t \le y - A g \le t,`
  - why missed: No context found (not_found_in_tex)
- **paper002 / theorem** — `$\lambda_{\min}(F_T^* F_T) \goto (1 - \sqrt{\gamma})^2 \text{ a.s.}$ $\lambda_{\max}(F_T^* F_T) \goto (1 + \sqrt{\gamma})^2 \text{ a.s.}$, in the limit where $p`
  - why missed: This content appears inside a standard LaTeX `align*` environment followed by display math, not inside any named theorem-like environment. There is no `\begin{theorem}` or similar wrapper here — the gold label 'theorem' 
  - suggested: `# Item 0: No structural regex addition is possible. # The result is stated in running prose + align*/equation environments, # not wrapped in any named theorem-l`
- **paper002 / problem** — `(P_0) \quad \quad \min_{d \in \R^m} \|d\|_{\ell_0} \quad \text{subject to} \quad F d = \tilde y \,\, ( = F e),`
  - why missed: The content is inside a standard `equation` environment (\begin{equation}...\end{equation}), not a theorem-like environment. The gold label 'problem' is assigned because the equation label is `eq:P0` and the content begi
  - suggested: `# Item 1 & 2: Catch optimization problems stated inside equation/align environments # whose body begins with a (P_...) or (P^...) label pattern. import re  PROB`
- **paper002 / problem** — `(P_1)\quad \quad \min_{x \in \R^m} \|d\|_{\ell_1}, \qquad F d = \tilde y,`
  - why missed: Same structural pattern as Item 1: an `align*` environment whose body begins with an optimization-problem label `(P_1)`. The same `_extract_equation_problems` function added for Item 1 covers this case too, since the reg
  - suggested: `# Item 2 is covered by the same addition as Item 1 (_extract_equation_problems). # The PROBLEM_EQ_PATTERN already matches align* environments, # and the body ch`
- **paper002 / open_problem** — `The ideas presented in this paper may be adapted to recover input vectors taking values from a finite alphabet. We hope to report on work in progress in a follo`
  - why missed: This content is plain running prose (no \begin/\end environment at all). The gold label 'open_problem' is a human judgment about the semantic content of a paragraph. There is no structural LaTeX marker here. A general he
  - suggested: `# Item 3: Catch open-problem statements in running prose paragraphs. # Matches a paragraph-like block introduced by common open-problem phrases.  OPEN_PROBLEM_P`
- **paper003 / problem** — `The proposed algorithm will attempt to maximize the following \begin{align} \max\ &x^TBx\\ \text{s.t.}\ &x_i=\pm1. \end{align}`
  - why missed: Item 0 is not inside a named theorem environment. It's a prose sentence followed by a \begin{align}...\end{align} block containing \max/\min and \text{s.t.}. This is a free-standing optimization problem. The fix is a new
  - suggested: `# New method to add to the class, called from _extract_theorem_like or a top-level extract method  def _extract_inline_optimization_problems(self, text: str) ->`
- **paper003 / problem** — `Our approach will be to consider a simple SDP relaxation to this combinatorial problem. The SDP relaxation considered here dates back to the seminal work of Goe`
  - why missed: Item 1 is structurally identical to Item 0 — a prose paragraph (longer lead-in) followed by \begin{align}...\end{align} containing \max + \text{s.t.}. The same _extract_inline_optimization_problems method (defined for It
  - suggested: `# The method from Item 0 handles Item 1 as well. # Only adjustment: allow the lead-in to span multiple lines (a full paragraph) # by replacing the single-line l`
- **paper004 / problem** — `Define the Lasso solution $\wh{\beta}_L = (\wh{\beta}_{1,L},\dots,\wh{\beta}_{M,L})$ by \begin{equation}\begin{split} \wh{\beta}_L = \argmin_{\beta\in\RR^M} \le`
  - why missed: The missed 'problem' is not inside any named LaTeX environment — it is a prose paragraph containing equation environments. There is no structural LaTeX marker (\begin{...}) to anchor a general regex on. Any pattern that 
  - suggested: `# No generalizable regex addition is possible for this case. # The 'problem' is embedded in free prose with no enclosing \begin{...}\end{...} environment. # A c`
- **paper004 / problem** — `The Dantzig estimator of the regression function $f$ is based on a particular solution of \eqref{dc}, the Dantzig selector $\wh{\beta}_D$ which is defined as a `
  - why missed: Same structural situation as Item 0: the missed 'problem' is a prose paragraph with embedded equation environments, not wrapped in any named LaTeX environment. There is no \begin{...}\end{...} boundary to match. The defi
  - suggested: `# No generalizable regex addition is possible for this case. # The 'problem' is embedded in free prose with no enclosing \begin{...}\end{...} environment. # A c`
- **paper005 / theorem** — `When $\lambda>0$, the solution $P^\lambda$ is unique by strict convexity of minus the entropy. In fact, $P^\lambda$ is necessarily of the form $u_i e^{-\lambda `
  - why missed: Item 0 is prose text inside a \subsection{...} that immediately precedes an \begin{algorithm}. It is NOT inside any LaTeX environment — it's free-flowing text between a subsection heading and an algorithm block. There is
  - suggested: `# Item 0: The missed content is plain prose in a \subsection body — no \begin/\end environment wraps it. # No minimal regex addition is possible without hardcod`
- **paper005 / proposition** — `$\begin{property}\label{prop:nsd}$ For $\alpha$ large enough, the Sinkhorn distance $d_{M,\alpha}$ is the transportation distance $d_{M}$$.\end{property}$`
  - why missed: Items 1 and 2 both use a custom \begin{property}...\end{property} environment which maps to 'proposition' semantically. Adding 'property' and 'Property' to the BASE_ENV_KIND_MAP (and env_kind_map) as 'proposition' will c
  - suggested: `# Add to BASE_ENV_KIND_MAP: # "property": "proposition", # "Property": "proposition",  # Minimal in-place addition: BASE_ENV_KIND_MAP_ADDITIONS = {     "propert`
- **paper005 / proposition** — `$\begin{property}[Independence$ Kernel] When $\alpha=0$ and $M$ is a Euclidean Distance $Matrix\footnote{$\exists n, \exists \varphi_1,\cdots,\varphi_d\in\RR^n$`
  - why missed: Same as Item 1 — the \begin{property}[Independence Kernel]...\end{property} environment is caught by the same addition of 'property'/'Property' -> 'proposition' mapping.
  - suggested: `# Same fix as Item 1 — adding 'property'/'Property' to env_kind_map covers both Item 1 and Item 2. # No additional code needed beyond what was added for Item 1.`
- **paper005 / problem** — `Given a $d\times d$ cost matrix $M$, the cost of mapping $r$ to $c$ using a transportation matrix (or joint probability) $P$ can be quantified as $\dotprod{P}{M`
  - why missed: Item 3 is again plain prose under a \subsection{Optimal Transportation} heading, with a displayed equation. It has no \begin/\end environment. The 'problem' is implicitly described by a subsection heading followed by a d
  - suggested: `# Item 3: Plain prose under a \subsection — no \begin/\end environment. # Cannot be captured reliably with a general LaTeX environment regex. # Closest general `
- **paper005 / problem** — `Recall that the Sinkhorn distance (Definition $~\ref{def:sinkhorn})$ is defined through a hard constraint on the entropy of $h(P)$ relative to $h(r)$ and $h(c)$`
  - why missed: Item 4 is also plain prose (a paragraph introducing a boxed equation in an \begin{equation} environment), not wrapped in any theorem-like \begin/\end. The content spans from a paragraph start to a subsection. Like Items 
  - suggested: `# Item 4: Plain prose paragraph with an embedded \begin{equation}...\end{equation}. # No theorem-like \begin/\end wraps the content. # Cannot be captured with a`
- **paper006 / theorem** — `Recalling that $\totalnumobs = \nummac \numobs$ is the total number of samples available, let us define the neighborhood $B_2(\optvar, t) \defeq \{\optvar' \in `
  - why missed: This item is a block of prose text (not inside any \begin/\end environment) that describes a minimax lower bound result. It is not wrapped in any LaTeX theorem-like environment, so no regex on \begin{...} will catch it. 
  - suggested: `# Item 0: No minimal addition possible. # This theorem is stated in running prose (no \begin/\end environment). # A general rule to catch it would require conte`
- **paper006 / problem** — `Our goal is to estimate the parameter vector minimizing the population risk, namely the quantity \begin{equation} \optvar^* \defeq \argmin_{\optvar \in \optvars`
  - why missed: This item is also in running prose (no \begin/\end environment). It describes the optimization problem goal. The gold label 'problem' was assigned by a human. Like item 0, it cannot be caught by environment-based extract
  - suggested: `# Item 1: No minimal addition possible. # This 'problem' is stated in running prose (no \begin/\end environment). # Cannot be reliably extracted by environment-`
- **paper006 / problem** — `The goal of this paper is to understand under what conditions---and in what sense---the estimators~\eqref{eqn:avgm-alg-def} and~\eqref{eqn:bootstrap-avg-def} ap`
  - why missed: This item is also in running prose (no \begin/\end environment). It is a goal/problem statement introduced by 'The goal of this paper is to understand...'. Like items 0 and 1, it cannot be caught by environment-based ext
  - suggested: `# Item 2: No minimal addition possible. # This 'problem' is stated in running prose (no \begin/\end environment). # Cannot be reliably extracted by environment-`
- **paper006 / problem** — `Our goal is to predict the probability of a user clicking a given advertisement as a function of the covariates in Table~\ref{tab:feature}. To do so, we use a l`
  - why missed: This item is also in running prose (no \begin/\end environment). It is a goal statement introduced by 'Our goal is to predict...'. Like items 0-2, it cannot be caught by environment-based extraction. No minimal general a
  - suggested: `# Item 3: No minimal addition possible. # This 'problem' is stated in running prose (no \begin/\end environment). # Cannot be reliably extracted by environment-`
- **paper006 / open_problem** — `In practice, an optimal choice of $\ratio$ may not be apparent, which may necessitate cross validation or another type of model evaluation. We leave as intrigui`
  - why missed: This item is also in running prose (no \begin/\end environment). It is an open problem/question stated inline, introduced by 'We leave as intriguing open questions...'. The pattern 'We leave ... as open question(s)' or '
  - suggested: `# Item 4: Prose open problem detection via regex on paragraph text. # Add to a prose-scanning method (separate from _extract_envs): import re  OPEN_PROBLEM_PROS`
- **paper006 / open_problem** — `a bootstrap correction is possible for the stochastic-gradient based estimator; such a correction could be significant, because the term $\beta^2 / \numobs^{3/2`
  - why missed: This item is in running prose (no \begin/\end environment). It is an open problem introduced by 'We leave this question to future work.' The phrase 'We leave this ... to future work' is a structural signal. A general reg
  - suggested: `# Item 5: Prose open problem — 'leave ... to/for future work' pattern. # Add to a prose-scanning method: FUTURE_WORK_PROSE_PATTERN = re.compile(     r'(?:[A-Z][`
- **paper006 / open_problem** — `remain open after this work. First, nonparametric estimation problems, which often suffer superlinear scaling in the size of the data, may provide an interestin`
  - why missed: This item is in running prose inside a Discussion section (no \begin/\end environment). It is an open problem introduced by 'remain open after this work' and 'may provide an interesting avenue for further study'. The str
  - suggested: `# Item 6: Prose open problem in Discussion/Conclusion sections. # Combine section detection with 'remain open' signal: REMAIN_OPEN_PROSE_PATTERN = re.compile(  `
- **paper011 / lemma** — `$\Prb{}{\Bc \mid \Ac} \geq 1/2$`
  - why missed: No context found (not_found_in_tex)
- **paper011 / problem** — `The \emph{$(c, r)$-approximate near neighbor problem (ANN)} with failure probability $f$ is to construct a data structure over a set of points $P$ in metric spa`
  - why missed: The missed structure is a standard `\begin{definition}...\end{definition}` environment. Looking at BASE_ENV_KIND_MAP, 'definition' is already mapped to 'definition' kind, but 'definition' kind is not in THEOREM_LIKE_KIND
  - suggested: `# Add 'definition' to THEOREM_LIKE_KINDS so \begin{definition}...\end{definition} # environments are extracted by _extract_theorem_like. # Locate the THEOREM_LI`
- **paper008 / problem** — `We consider the standard setting of convex stochastic optimization, using first-order methods. Our goal is to minimize a convex function $F$ over some convex do`
  - why missed: Item 0 is a plain paragraph of running text with no LaTeX environment wrapper (no \begin{problem}...\end{problem}). The 'problem' is described inline in prose. There is no structural LaTeX marker (no \begin/\end, no \tex
  - suggested: `# No safe general addition possible for Item 0. # The missed block is plain prose with no \begin{...}/\end{...} wrapper, # no leading \textbf{Problem} or simila`
- **paper008 / open_problem** — `There are several open issues remaining. In particular, the $\Ocal(1/T)$ rate in the non-smooth case still requires some sort of averaging. However, in our expe`
  - why missed: Item 1 is also plain prose in a Discussion/Conclusion section — there is no \begin{openproblem} or similar LaTeX environment. However, there IS a structural anchor: the paragraph contains rhetorical open-question markers
  - suggested: `import re from typing import List, Tuple  # Add to the extraction pipeline as a supplementary extractor for inline open_problem paragraphs. # Catches paragraphs`
- **paper012 / proposition** — `A notable property of the forward process is that it admits sampling  $\bx_t$ at an arbitrary timestep $t$ in closed form: using the notation $\alpha_t \defeq 1`
  - why missed: The missed proposition is plain running text (no \begin{proposition} environment). It is a prose paragraph containing an align block. There is no structural LaTeX marker (\begin/\end theorem env) to anchor on. Any regex 
  - suggested: `# Not feasible: no \begin{...}...\end{...} wrapper exists. # The 'proposition' is inline prose. A general inline-claim detector # would require NLP, not regex o`
- **paper012 / claim** — `As \cref{eq:vb_term_langevin_eps} is equal to (one term of) the variational bound for the Langevin-like reverse process, we see that optimizing an objective res`
  - why missed: The missed claim is a single prose sentence in running text, not enclosed in any LaTeX environment. There is no \begin{claim} or similar. The sentence begins with 'As \cref{...} is equal to...' — entirely content-specifi
  - suggested: `# Not feasible: no \begin{...}...\end{...} wrapper exists. # The 'claim' is a prose sentence. Catching it requires content/NLP heuristics, # not LaTeX structure`
- **paper012 / claim** — `With these choices, $\kl{q(\bx_T)}{p(\bx_T)}=0$, and minimizing $\kl{q(\bx_{t-1}|\bx_t)}{p_\theta(\bx_{t-1}|\bx_t)}$ trains $p_\theta$ to copy coordinates $t+1,`
  - why missed: The missed claim is a prose paragraph starting 'With these choices,...' — again, pure running text with no enclosing LaTeX theorem environment. No structural anchor exists. The conclusion 'training p_theta with this part
  - suggested: `# Not feasible: no \begin{...}...\end{...} wrapper exists. # The 'claim' is a prose paragraph. Cannot be caught by env-based extraction. # No code addition reco`
- **paper013 / theorem** — `Given vector fields $u_t(x|x_1)$ that generate conditional probability paths $p_t(x|x_1)$, for any distribution $q(x_1)$, the marginal vector field $u_t$ in \eq`
  - why missed: Items 0, 1, 2 all use \begin{restatable}{theorem}{...} — a 'restatable' wrapper environment from the thmtools package. The inner type (theorem/lemma/etc.) is passed as the first mandatory argument. The base extractor onl
  - suggested: `# Add to _extract_theorem_like (or as a helper called from it): # Handles \begin{restatable}{<kind>}{<macro_name>}[opt] body \end{restatable} RESTATABLE_PATTERN`
- **paper013 / theorem** — `Assuming that $p_t(x)>0$ for all $x\in\Real^d$ and $t\in [0,1]$, then, up to a constant independent of $\theta$, $\gL_{\CFM}$ and $\gL_{\FM}$ are equal. Hence, `
  - why missed: Same \begin{restatable}{theorem}{...} pattern as Item 0. The fix is identical — the RESTATABLE_PATTERN handles all restatable theorems generically by reading the inner environment kind.
  - suggested: `# Same RESTATABLE_PATTERN addition as Item 0 covers this case. # No additional code needed beyond what is described in Item 0. pass`
- **paper013 / theorem** — `Let $p_t(x\vert x_1)$ be a Gaussian probability path as in \eqref{e:pt_gau}, and $\psi_t$ its corresponding flow map as in \eqref{e:phi_t_gau}. Then, the unique`
  - why missed: Same \begin{restatable}{theorem}{...} pattern as Items 0 and 1. Covered by the same RESTATABLE_PATTERN fix.
  - suggested: `# Same RESTATABLE_PATTERN addition as Item 0 covers this case. pass`
- **paper013 / proposition** — `One method of testing if a vector field $v_t$ generates a probability path $p_t$ is the continuity equation \citep{villani2009optimal}. It is a Partial Differen`
  - why missed: This is a standalone section in an appendix titled 'The continuity equation' containing a definition/proposition presented inline (not inside any \begin{...}\end{...} environment). It cannot be caught by an environment-b
  - suggested: `# This item is an inline proposition presented as a section body, not inside # any theorem-like LaTeX environment. Catching it generically would require # conte`
- **paper013 / problem** — `Given a target probability density path $p_t(x)$ and a corresponding vector field $u_t(x)$, which generates $p_t(x)$, we define the Flow Matching (FM) objective`
  - why missed: This 'problem' (an objective/definition) is presented inline as a paragraph with a \begin{equation}...\end{equation} block, not inside any theorem-like environment. Like Item 3, there is no structural LaTeX environment b
  - suggested: `# This item is an inline objective definition presented as a paragraph + equation, # not inside any theorem-like LaTeX environment. No reliable general structur`
- **paper013 / problem** — `Specifically, we consider the \emph{Conditional Flow Matching} (CFM) objective, \begin{equation} \mathcal{L}_{\CFM}(\theta) = \mathbb{E}_{t,q(x_1),p_t(x\vert x_`
  - why missed: Item 5 is also an inline equation block (\begin{equation}...\end{equation}) with surrounding prose, not inside a theorem-like environment. The 'unknown_environment' rule-based guess is incorrect; there is no \begin{...}\
  - suggested: `# This item is an inline equation with surrounding prose, not inside any # theorem-like LaTeX environment. No general structural anchor is available. # No code `
- **paper014 / problem** — `We are interested in, and propose a solution to, three related problems in the above scenario: \begin{enumerate} \item Efficient approximate ML or MAP estimatio`
  - why missed: This 'problem' is not inside a LaTeX theorem-like environment (\begin{problem}...\end{problem}). Instead, it is a free-standing paragraph introduced by the phrase 'We are interested in, and propose a solution to, three r
  - suggested: `# No minimal general-purpose addition is possible for this item. # The content is a free-form prose paragraph + enumerate block, not wrapped # in any theorem-li`
- **paper015 / problem** — `In other words, $D$ and $G$ play the following two-player minimax game with value function $V(G, D)$: \begin{equation} \min_G \max_D V(D, G) = \mathbb{E}_{\bm{x`
  - why missed: The missed item is not inside a theorem-like LaTeX environment at all — it is an `equation` environment containing a minimax optimization problem. The 'gold' label of 'problem' appears to be a content-based heuristic jud
  - suggested: `# No minimal generalizable addition is possible for this item. # The content lives inside \begin{equation}...\end{equation} with no theorem-like wrapper. # A ge`
- **paper450 / problem** — `A linear regression problem in a separable Hilbert space $\bbH$ is defined by a random covariate vector $x\in\bbH$ and outcome $y\in\Re$. We define $\begin{enum`
  - why missed: This 'problem' is defined inline in the text (not inside a \begin{problem}...\end{problem} environment). The content describes a 'problem' in a section/paragraph that begins with 'A linear regression problem' or similar.
  - suggested: `# This missed item has no \begin{...}...\end{...} environment wrapper. # The closest generalizable pattern for inline problems is a paragraph # starting with a `
