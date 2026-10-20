# alg3 extractor `silver_v7__sentence_tagger__2026-10`: the strongest clues per type

A sentence starts a node of type T when, after the second pass, P(T) is its highest type probability and at least the threshold τ_T. Weights are log-odds contributions (positive = evidence for T). Trained on 210 papers; 79337 clues in pass 1, 79520 in pass 2.

Validation (40 papers, overall F incl. base parser): **0.7484** (P 0.7575, R 0.7394); base 0.6574.

## problem  (τ = 0.15)

| for (weight) | against (weight) |
|---|---|
| contains "problem" (+1.49) | cue phrase: claim_derive (-0.64) |
| cue phrase: problem_word (+1.33) | contains "case" (-0.57) |
| contains "optimization" (+1.17) | next sentence starts with "in" (-0.55) |
| contains "is to" (+0.97) | contains "problem \ref" (-0.54) |
| contains "pt" (+0.81) | position-in-paper decile 9 (-0.54) |
| section title contains "recovery" (+0.72) | contains "theorem" (-0.53) |
| section title contains "problem" (+0.71) | contains "using" (-0.52) |
| contains "solve" (+0.70) | contains "given by" (-0.48) |
| cue phrase: q_question (+0.70) | next sentence starts with "let" (-0.48) |
| contains "training" (+0.68) | contains "point" (-0.47) |
| contains "sources" (+0.68) | contains "solution" (-0.47) |
| contains "solving the" (+0.68) | contains "also" (-0.47) |
| contains "consider" (+0.67) | combination: cue=claim derive, sec=none (-0.46) |
| contains "given" (+0.64) | contains "if" (-0.45) |
| contains "chosen" (+0.63) | contains "open" (-0.45) |

Second pass, strongest neighbour evidence: previous sentence looks like assumption (p≥0.75) (+0.46); next sentence looks like problem (p≥0.10) (+0.45); this sentence (1st pass) looks like problem (p≥0.75) (+0.37); next sentence looks like open_problem (p≥0.10) (+0.35); next sentence looks like remark (p≥0.10) (+0.33); previous sentence looks like definition (p≥0.25) (+0.32)

## conjecture  (τ = 0.2)

| for (weight) | against (weight) |
|---|---|
| cue phrase: conj (+2.08) | share-of-math bucket 3 (-0.71) |
| contains "conjectured" (+1.43) | next sentence starts with "for" (-0.53) |
| contains "expect" (+1.13) | position-in-paper decile 6 (-0.48) |
| combination: cue=conj, sec=none (+1.08) | paragraph-length bucket 2 (-0.48) |
| contains "that" (+1.01) | first in its paragraph (-0.47) |
| contains "conjectured that" (+1.01) | in a section about Examples/Applications (-0.47) |
| position-in-paper decile 9 (+0.94) | contains "by" (-0.47) |
| combination: cue=conj, sec=intro (+0.90) | cue phrase: cite_result (-0.43) |
| contains "conjecture" (+0.86) | contains "on" (-0.40) |
| contains "we expect" (+0.82) | contains "conjecture \ref" (-0.39) |
| contains "should" (+0.76) | cue phrase: ass_assume (-0.37) |
| contains "we believe" (+0.75) | contains "a" (-0.35) |
| contains "natural" (+0.71) | contains ":" (-0.35) |
| contains "conjecture that" (+0.69) | position-in-paper decile 4 (-0.35) |
| contains "results" (+0.68) | contains "is" (-0.35) |

Second pass, strongest neighbour evidence: two sentences before looks like remark (p≥0.10) (+0.83); next sentence looks like conjecture (p≥0.10) (+0.70); this sentence (1st pass) looks like conjecture (p≥0.25) (+0.59); next sentence looks like open_problem (p≥0.10) (+0.45); this sentence (1st pass) looks like theorem (p≥0.25) (+0.31); this sentence (1st pass) looks like conjecture (p≥0.75) (+0.30)

## claim  (τ = 0.35)

| for (weight) | against (weight) |
|---|---|
| next sentence starts with "that" (+1.21) | contains "namely" (-0.85) |
| combination: env before=proof, f1=let (+1.06) | contains "let" (-0.78) |
| starts with "we may" (+1.04) | contains "\textbf" (-0.77) |
| section title contains "integration" (+1.04) | contains "single" (-0.76) |
| contains "have [display]" (+1.03) | contains "that are" (-0.76) |
| section title contains "mathcal" (+0.98) | contains "we" (-0.76) |
| contains "diagrams" (+0.95) | starts with "to" (-0.75) |
| previous sentence starts with "myequation" (+0.91) | section title contains "estimate" (-0.75) |
| section title contains "cylindric" (+0.90) | section title contains "weak" (-0.74) |
| section title contains "change" (+0.89) | contains "means" (-0.74) |
| contains "example if" (+0.89) | next sentence starts with "our" (-0.72) |
| previous sentence starts with "all" (+0.87) | contains "stable" (-0.70) |
| section title contains "probability" (+0.86) | starts with "\item $…$ is" (-0.68) |
| section title contains "other" (+0.86) | section title contains "finite" (-0.67) |
| section title contains "contiguous" (+0.85) | contains "which implies" (-0.67) |

Second pass, strongest neighbour evidence: previous sentence looks like conjecture (p≥0.10) (+0.71); two sentences before looks like remark (p≥0.75) (+0.64); two sentences before looks like remark (p≥0.25) (+0.59); two sentences before looks like proof (p≥0.50) (+0.58); next sentence looks like theorem (p≥0.50) (+0.57); previous sentence looks like problem (p≥0.50) (+0.56)

## definition  (τ = 0.35)

| for (weight) | against (weight) |
|---|---|
| cue phrase: def_called (+1.45) | section title contains "sketch" (-1.14) |
| contains "called" (+1.42) | section title contains "formulae" (-1.01) |
| contains "set [display]" (+1.34) | section title contains "temporal" (-1.01) |
| cue phrase: def_denote (+1.31) | contains "inequality" (-0.99) |
| contains "define" (+1.20) | contains "example" (-0.92) |
| next sentence starts with "denote" (+1.12) | next sentence starts with "suppose" (-0.91) |
| section title contains "divisorperiodic" (+1.10) | section title contains "probabilistic" (-0.86) |
| section title contains "geometric" (+1.06) | section title contains "derivation" (-0.85) |
| contains "let [display]" (+1.01) | contains "that [display]" (-0.83) |
| section title contains "hol" (+0.97) | contains "solve" (-0.83) |
| cue phrase: def_we (+0.95) | contains "of graphs" (-0.80) |
| starts with "define" (+0.93) | next sentence starts with "indeed" (-0.78) |
| contains "write" (+0.93) | contains "show" (-0.77) |
| starts with "set" (+0.91) | section title contains "situation" (-0.76) |
| contains "means" (+0.90) | contains "the equation" (-0.75) |

Second pass, strongest neighbour evidence: next sentence looks like definition (p≥0.75) (+1.06); two sentences before looks like assumption (p≥0.25) (+0.77); next sentence looks like definition (p≥0.50) (+0.65); previous sentence looks like assumption (p≥0.25) (+0.59); next sentence looks like definition (p≥0.25) (+0.52); previous sentence looks like algorithm (p≥0.10) (+0.48)

## assumption  (τ = 0.4)

| for (weight) | against (weight) |
|---|---|
| cue phrase: ass_assume (+1.80) | position-in-paper decile 9 (-1.04) |
| contains "assume" (+1.73) | cue phrase: claim_derive (-0.88) |
| contains "assumed" (+1.07) | next sentence starts with "then" (-0.82) |
| contains "we assume" (+1.07) | contains "the following" (-0.68) |
| starts with "\item $…$ is" (+1.03) | contains "$…$ of" (-0.67) |
| contains "will assume" (+0.99) | contains "if" (-0.66) |
| contains "considered" (+0.96) | next sentence starts with "\item" (-0.63) |
| section title contains "criteria" (+0.90) | contains "we can" (-0.61) |
| right before a remark environment (+0.83) | section title contains "general" (-0.60) |
| combination: f1=\item, sec=model (+0.81) | in a section about Proofs (-0.57) |
| section title contains "exactness" (+0.80) | previous sentence starts with "then" (-0.56) |
| section title contains "fixing" (+0.77) | contains "let $…$" (-0.54) |
| combination: cue=ass assume, sec=main (+0.77) | cue phrase: rem_aside (-0.53) |
| section title contains "gauge" (+0.76) | contains "example" (-0.53) |
| in a section about Model/Assumptions (+0.75) | starts with "this" (-0.52) |

Second pass, strongest neighbour evidence: next sentence looks like remark (p≥0.10) (+0.83); previous sentence looks like assumption (p≥0.10) (+0.71); next sentence looks like assumption (p≥0.50) (+0.69); two sentences before looks like definition (p≥0.25) (+0.69); previous sentence looks like assumption (p≥0.75) (+0.61); two sentences before looks like problem (p≥0.25) (+0.50)

## open_problem  (τ = 0.4)

| for (weight) | against (weight) |
|---|---|
| cue phrase: q_question (+1.89) | length bucket 0 (-0.56) |
| contains "open" (+1.24) | contains "that" (-0.50) |
| in a section about Conclusion/Discussion (+1.24) | position-in-paper decile 4 (-0.50) |
| section title contains "conclusion" (+1.07) | contains "consider" (-0.49) |
| ends with ? (+1.03) | contains "by" (-0.49) |
| contains "would be" (+1.03) | contains "can be" (-0.49) |
| contains "question" (+0.96) | contains "$…$ $…$" (-0.44) |
| contains "not" (+0.96) | previous sentence has italics (-0.43) |
| contains "it" (+0.87) | contains "as a" (-0.42) |
| contains "know" (+0.84) | contains "$…$ for" (-0.41) |
| position-in-paper decile 9 (+0.81) | cue phrase: def_word (-0.41) |
| contains "can we" (+0.80) | combination: cue=claim follows, sec=none (-0.40) |
| contains "?" (+0.78) | position-in-paper decile 3 (-0.38) |
| cue phrase: q_mark (+0.78) | contains "all" (-0.37) |
| combination: cue=q question, sec=intro (+0.77) | starts with "for" (-0.37) |

Second pass, strongest neighbour evidence: previous sentence looks like claim (p≥0.10) (+0.61); previous sentence looks like theorem (p≥0.75) (+0.59); next sentence looks like open_problem (p≥0.75) (+0.54); this sentence (1st pass) looks like theorem (p≥0.25) (+0.51); two sentences before looks like proof (p≥0.10) (+0.44); two sentences before looks like proof (p≥0.25) (+0.43)

## proof  (τ = 0.45)

| for (weight) | against (weight) |
|---|---|
| right before a corollary environment (+1.44) | combination: f1=this, sec=proof (-1.01) |
| contains "sketch" (+1.42) | position-in-paper decile 0 (-0.87) |
| contains "implies theorem" (+1.16) | right after a example environment (-0.74) |
| ends with "\item" (+1.14) | right after a definition environment (-0.73) |
| next sentence starts with "since" (+1.13) | combination: env before=proof, f1=let (-0.72) |
| next sentence starts with "thus" (+1.13) | combination: f1=\item, sec=none (-0.68) |
| combination: f1=\item, sec=intro (+1.12) | right after a conjecture environment (-0.67) |
| cue phrase: proof_word (+1.09) | right before a definition environment (-0.67) |
| contains "directly" (+1.01) | contains "set $…$" (-0.66) |
| previous sentence starts with "we claim" (+1.01) | contains "edges" (-0.63) |
| contains "follows" (+1.00) | contains "condition" (-0.63) |
| contains "this follows" (+0.96) | previous sentence starts with "therefore" (-0.62) |
| contains "following result" (+0.96) | contains "considered" (-0.62) |
| first in its paragraph (+0.95) | starts in bold (-0.62) |
| ends with "following" (+0.95) | paragraph-length bucket 1 (-0.62) |

Second pass, strongest neighbour evidence: previous sentence looks like theorem (p≥0.25) (+0.65); two sentences before looks like assumption (p≥0.10) (+0.65); next sentence looks like proof (p≥0.50) (+0.64); two sentences before looks like theorem (p≥0.10) (+0.62); two sentences before: none (region edge) (+0.58); previous sentence looks like claim (p≥0.25) (+0.55)

## theorem  (τ = 0.45)

| for (weight) | against (weight) |
|---|---|
| has a citation (+1.78) | contains "theorem \ref" (-0.99) |
| contains "proved" (+1.64) | contains "so that" (-0.89) |
| contains "showed" (+1.60) | contains "theorem \cite" (-0.85) |
| contains "shown" (+1.28) | contains "our" (-0.83) |
| contains "\cite" (+1.26) | contains "we" (-0.80) |
| starts with "he" (+1.13) | right before a proposition environment (-0.79) |
| contains "he" (+1.11) | ends with ":" (-0.78) |
| contains "theorem" (+1.10) | next sentence starts with "note" (-0.67) |
| section title contains "previous" (+1.10) | contains "be the" (-0.64) |
| contains "showed that" (+1.00) | has bold (-0.63) |
| contains "is known" (+0.97) | contains "such that" (-0.63) |
| section title contains "involving" (+0.94) | contains "proposition \ref" (-0.60) |
| section title contains "incomplete" (+0.94) | contains "obtain" (-0.60) |
| section title contains "identities" (+0.94) | contains "with $…$" (-0.59) |
| combination: f1=then, sec=main (+0.91) | combination: f1=then, sec=none (-0.58) |

Second pass, strongest neighbour evidence: next sentence looks like theorem (p≥0.25) (+1.08); next sentence looks like theorem (p≥0.75) (+0.92); previous sentence looks like conjecture (p≥0.25) (+0.69); this sentence (1st pass) looks like claim (p≥0.75) (+0.67); next sentence looks like theorem (p≥0.50) (+0.66); two sentences before looks like theorem (p≥0.50) (+0.58)

## corollary  (τ = 0.5)

| for (weight) | against (weight) |
|---|---|
| contains "corollary" (+1.01) | paragraph-length bucket 3 (-0.37) |
| contains "a corollary" (+0.95) | inline-math count bucket 0 (-0.29) |
| contains "corollary of" (+0.68) | last in its paragraph (-0.27) |
| ends with "s" (+0.48) | share-of-math bucket 3 (-0.25) |
| contains "as a" (+0.46) | contains a displayed equation (-0.24) |
| combination: cue=claim follows, sec=none (+0.46) | contains "[display]" (-0.24) |
| contains "of \ref" (+0.44) | inline-math count bucket 3 (-0.24) |
| starts with "as a" (+0.43) | length bucket 2 (-0.23) |
| contains "as" (+0.41) | paragraph-length bucket 1 (-0.21) |
| cue phrase: claim_derive (+0.40) | position-in-paper decile 6 (-0.21) |
| cue phrase: claim_follows (+0.38) | position-in-paper decile 5 (-0.21) |
| contains "s" (+0.37) | contains "in" (-0.20) |
| contains "a transduction" (+0.37) | contains "to" (-0.20) |
| contains "chernoff s" (+0.36) | has a citation (-0.20) |
| contains "is bigger" (+0.36) | contains "\cite" (-0.20) |

Second pass, strongest neighbour evidence: two sentences before looks like claim (p≥0.75) (+0.32); this sentence (1st pass) looks like claim (p≥0.50) (+0.24); this sentence (1st pass) looks like claim (p≥0.25) (+0.21); this sentence (1st pass) looks like proof (p≥0.50) (+0.20); this sentence (1st pass) looks like claim (p≥0.10) (+0.12); this sentence (1st pass) looks like claim (p≥0.75) (+0.12)

## lemma  (τ = 0.5)

| for (weight) | against (weight) |
|---|---|
| section title contains "multivariate" (+1.50) | contains "the" (-0.61) |
| section title contains "isabelle" (+1.50) | position-in-paper decile 5 (-0.49) |
| section title contains "polynomials" (+1.41) | contains "to" (-0.48) |
| combination: f1=, sec=none (+1.41) | contains "with" (-0.45) |
| contains "lemma" (+1.14) | length bucket 3 (-0.40) |
| no next sentence in the region (+0.92) | contains "as" (-0.38) |
| contains "lem" (+0.89) | contains "is a" (-0.37) |
| position-in-paper decile 4 (+0.79) | position-in-paper decile 1 (-0.37) |
| contains "manuallemma" (+0.75) | starts with "the" (-0.33) |
| contains "nonbip" (+0.71) | contains "from" (-0.32) |
| contains "\ref $…$" (+0.67) | position-in-paper decile 2 (-0.32) |
| contains "\cite" (+0.66) | right before a lemma environment (-0.31) |
| has a citation (+0.66) | right after a proof environment (-0.30) |
| section title contains "sketch" (+0.66) | in a section about Preliminaries/Notation/Background (-0.30) |
| section title contains "join" (+0.64) | paragraph-length bucket 3 (-0.30) |

Second pass, strongest neighbour evidence: next sentence: none (region edge) (+0.61); this sentence (1st pass) looks like theorem (p≥0.50) (+0.55); two sentences before looks like claim (p≥0.75) (+0.43); this sentence (1st pass) looks like definition (p≥0.25) (+0.42); previous sentence looks like definition (p≥0.75) (+0.38); this sentence (1st pass) looks like proof (p≥0.25) (+0.31)

## proposition  (τ = 0.5)

| for (weight) | against (weight) |
|---|---|
| contains "proposition" (+1.22) | inline-math count bucket 2 (-0.41) |
| ends with "proposition" (+0.60) | contains "for" (-0.34) |
| section title contains "derivative" (+0.57) | paragraph-length bucket 2 (-0.31) |
| section title contains "grand" (+0.57) | contains "to" (-0.29) |
| section title contains "fractional" (+0.55) | share-of-math bucket 1 (-0.27) |
| section title contains "space" (+0.54) | paragraph-length bucket 4 (-0.23) |
| section title contains "lebesgue" (+0.54) | position-in-paper decile 6 (-0.22) |
| section title contains "norm" (+0.53) | contains "$…$ is" (-0.20) |
| section title contains "estimation" (+0.51) | contains "of" (-0.20) |
| previous sentence starts with "mm" (+0.51) | contains "the" (-0.19) |
| combination: f1=\textbf, sec=none (+0.49) | first in its paragraph (-0.19) |
| previous sentence starts with "defining $…$" (+0.42) | position-in-paper decile 7 (-0.18) |
| previous sentence starts with "defining" (+0.42) | position-in-paper decile 5 (-0.18) |
| no next sentence in the region (+0.42) | contains "in" (-0.18) |
| contains "prop" (+0.42) | contains "and $…$" (-0.17) |

Second pass, strongest neighbour evidence: two sentences before looks like definition (p≥0.50) (+0.46); this sentence (1st pass) looks like claim (p≥0.50) (+0.39); previous sentence looks like proof (p≥0.75) (+0.34); this sentence (1st pass) looks like proof (p≥0.50) (+0.33); next sentence: none (region edge) (+0.32); two sentences before looks like proof (p≥0.10) (+0.30)

## algorithm  (τ = 0.6)

| for (weight) | against (weight) |
|---|---|
| section title contains "situation" (+1.18) | no next sentence in the region (-0.89) |
| contains "scheme" (+1.07) | next sentence starts with "a" (-0.58) |
| contains "hash" (+1.01) | combination: cue=claim derive, sec=none (-0.56) |
| section title contains "dimensional" (+0.98) | in a section about Introduction (-0.55) |
| next sentence starts with "consider" (+0.96) | contains "$…$ is" (-0.55) |
| contains "$…$ vertex" (+0.88) | contains "that" (-0.53) |
| contains "as follows" (+0.88) | ends with "[display]" (-0.52) |
| contains "is based" (+0.86) | contains a displayed equation (-0.51) |
| previous sentence starts with "for the" (+0.83) | contains "[display]" (-0.51) |
| cue phrase: alg_step (+0.82) | contains "in \cite" (-0.51) |
| contains "graph $…$" (+0.82) | contains "is the" (-0.48) |
| section title contains "boldmath" (+0.80) | contains "its" (-0.47) |
| contains "first" (+0.80) | contains "with the" (-0.47) |
| contains "samples" (+0.76) | combination: cue=ass assume, sec=none (-0.46) |
| contains "distributed" (+0.75) | right after a theorem environment (-0.44) |

Second pass, strongest neighbour evidence: next sentence looks like definition (p≥0.10) (+0.37); this sentence (1st pass) looks like problem (p≥0.10) (+0.35); next sentence looks like problem (p≥0.25) (+0.32); previous sentence looks like proof (p≥0.10) (+0.30); this sentence (1st pass) looks like proof (p≥0.10) (+0.29); previous sentence looks like problem (p≥0.75) (+0.27)

## example  (τ = 0.6)

| for (weight) | against (weight) |
|---|---|
| contains "example" (+2.23) | position-in-paper decile 0 (-0.77) |
| section title contains "examples" (+1.65) | last in its paragraph (-0.75) |
| section title contains "complete" (+1.52) | position-in-paper decile 4 (-0.70) |
| previous sentence starts with "\item" (+1.15) | no next sentence in the region (-0.67) |
| contains "examples of" (+1.13) | section title contains "case" (-0.63) |
| contains "figure" (+1.09) | contains "of $…$" (-0.61) |
| starts with "let $…$ where" (+1.06) | cue phrase: def_let_be (-0.60) |
| cue phrase: ex_example (+1.06) | position-in-paper decile 1 (-0.60) |
| contains "not" (+0.92) | starts with "let $…$ be" (-0.55) |
| combination: f1=in, sec=example (+0.88) | contains "in \ref" (-0.55) |
| in a section about Examples/Applications (+0.88) | section title contains "algorithm" (-0.52) |
| position-in-paper decile 6 (+0.86) | combination: cue=ass assume, sec=none (-0.51) |
| section title contains "measures" (+0.83) | contains "$…$ are" (-0.50) |
| contains "example of" (+0.79) | combination: f1=the, sec=example (-0.50) |
| contains "$…$ where" (+0.76) | contains "every" (-0.49) |

Second pass, strongest neighbour evidence: next sentence looks like example (p≥0.75) (+0.89); this sentence (1st pass) looks like proof (p≥0.10) (+0.75); this sentence (1st pass) looks like definition (p≥0.25) (+0.61); previous sentence looks like theorem (p≥0.25) (+0.53); previous sentence looks like theorem (p≥0.75) (+0.50); previous sentence looks like proof (p≥0.25) (+0.47)

## remark  (τ = 0.7)

| for (weight) | against (weight) |
|---|---|
| cue phrase: rem_note (+1.46) | contains "as in" (-0.69) |
| section title contains "strategy" (+1.33) | contains "have" (-0.68) |
| combination: env before=remark, f1= (+1.10) | contains "sets" (-0.68) |
| previous sentence starts with "consider the" (+1.01) | contains "shown" (-0.66) |
| contains "assume $…$" (+1.01) | contains "in $…$" (-0.63) |
| section title contains "closure" (+1.00) | contains "then $…$" (-0.63) |
| contains "\textbf remark" (+0.92) | contains "in this" (-0.61) |
| right after a theorem environment (+0.92) | contains "that this" (-0.60) |
| starts with "\textbf remark" (+0.90) | contains "known" (-0.60) |
| right after a proof environment (+0.87) | section title contains "via" (-0.60) |
| contains "amenability" (+0.86) | contains "remark \ref" (-0.59) |
| previous sentence starts with "thm \textbf" (+0.86) | right before a theorem environment (-0.58) |
| ends with "\emph" (+0.85) | previous sentence starts with "sec" (-0.56) |
| combination: f1=the, sec=algorithm (+0.84) | contains "$…$ be" (-0.56) |
| ends with "warning" (+0.84) | next sentence starts with "here" (-0.55) |

Second pass, strongest neighbour evidence: this sentence (1st pass) looks like proof (p≥0.25) (+0.62); next sentence looks like problem (p≥0.10) (+0.56); this sentence (1st pass) looks like claim (p≥0.25) (+0.55); previous sentence looks like remark (p≥0.25) (+0.46); previous sentence looks like claim (p≥0.50) (+0.43); previous sentence looks like proof (p≥0.25) (+0.42)

