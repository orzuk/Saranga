# alg3 extractor `v2b`: the strongest clues per type

A sentence starts a node of type T when, after the second pass, P(T) is its highest type probability and at least the threshold τ_T. Weights are log-odds contributions (positive = evidence for T). Trained on 120 papers; 46912 clues in pass 1, 47087 in pass 2.

Validation (40 papers, overall F incl. base parser): **0.7256** (P 0.7746, R 0.6824); base 0.6188.

## conjecture  (τ = 0.15)

| for (weight) | against (weight) |
|---|---|
| cue phrase: conj (+1.61) | share-of-math bucket 3 (-0.49) |
| contains "conjecture" (+0.96) | contains "a" (-0.48) |
| position-in-paper decile 9 (+0.86) | paragraph-length bucket 2 (-0.46) |
| combination: cue=conj, sec=intro (+0.86) | length bucket 0 (-0.45) |
| contains "expect" (+0.86) | first in its paragraph (-0.44) |
| contains "that" (+0.85) | ends with "$…$" (-0.42) |
| contains "conjectured" (+0.81) | contains "can" (-0.40) |
| contains "we expect" (+0.67) | contains "the" (-0.38) |
| contains "conjectured that" (+0.65) | position-in-paper decile 6 (-0.35) |
| contains "results" (+0.64) | contains "on" (-0.35) |
| contains "we believe" (+0.63) | ends with "\cite" (-0.33) |
| contains "believe" (+0.60) | cue phrase: ex_example (-0.33) |
| section title contains "conclusion" (+0.59) | contains "by" (-0.30) |
| combination: cue=conj, sec=none (+0.58) | position-in-paper decile 8 (-0.29) |
| before any section (+0.58) | next sentence starts with "for" (-0.26) |

Second pass, strongest neighbour evidence: this sentence (1st pass) looks like theorem (p≥0.75) (+0.35); previous sentence looks like open_problem (p≥0.25) (+0.31); next sentence looks like proof (p≥0.10) (+0.29); two sentences before looks like open_problem (p≥0.25) (+0.28); this sentence (1st pass) looks like conjecture (p≥0.25) (+0.26); this sentence (1st pass) looks like conjecture (p≥0.10) (+0.21)

## problem  (τ = 0.3)

| for (weight) | against (weight) |
|---|---|
| cue phrase: problem_word (+1.48) | contains "if" (-0.58) |
| contains "problem" (+0.97) | combination: cue=alg step, sec=none (-0.56) |
| contains "optimization" (+0.80) | contains "in the" (-0.55) |
| contains "is to" (+0.78) | position-in-paper decile 9 (-0.54) |
| cue phrase: q_question (+0.74) | contains "an" (-0.53) |
| contains "given" (+0.70) | combination: cue=claim derive, sec=none (-0.49) |
| contains "by minimizing" (+0.61) | contains "using" (-0.48) |
| previous sentence starts with "in this" (+0.61) | contains "to the" (-0.47) |
| contains "solving" (+0.59) | contains "then" (-0.45) |
| contains "we are" (+0.57) | contains "solution" (-0.45) |
| position-in-paper decile 1 (+0.57) | contains "for $…$" (-0.44) |
| contains "consider" (+0.57) | length bucket 1 (-0.39) |
| combination: f1=hence, sec=none (+0.56) | contains "this" (-0.39) |
| contains "some" (+0.56) | contains "$…$ are" (-0.37) |
| contains "algorithms" (+0.55) | contains "case" (-0.36) |

Second pass, strongest neighbour evidence: previous sentence looks like remark (p≥0.25) (+0.71); this sentence (1st pass) looks like definition (p≥0.50) (+0.54); two sentences before looks like remark (p≥0.10) (+0.52); next sentence looks like proof (p≥0.10) (+0.50); next sentence looks like problem (p≥0.10) (+0.48); two sentences before looks like claim (p≥0.10) (+0.35)

## assumption  (τ = 0.35)

| for (weight) | against (weight) |
|---|---|
| cue phrase: ass_assume (+1.95) | next sentence starts with "then" (-1.03) |
| contains "assume" (+1.26) | position-in-paper decile 9 (-0.90) |
| position-in-paper decile 1 (+0.93) | position-in-paper decile 6 (-0.77) |
| contains "we assume" (+0.88) | cue phrase: claim_derive (-0.48) |
| contains "rules are" (+0.76) | ends with ":" (-0.48) |
| contains "believed" (+0.76) | contains "may" (-0.47) |
| combination: f1=two, sec=intro (+0.75) | previous sentence starts with "this" (-0.47) |
| contains "bounded" (+0.71) | previous sentence starts with "then" (-0.46) |
| contains "data" (+0.71) | contains "is a" (-0.43) |
| starts with "two" (+0.71) | contains "above" (-0.43) |
| contains "rules" (+0.69) | contains "example" (-0.42) |
| section title contains "theory" (+0.68) | contains "as $…$" (-0.41) |
| section title contains "nonlinear" (+0.68) | contains "system" (-0.41) |
| contains "consider the" (+0.68) | has a \ref (-0.41) |
| section title contains "good" (+0.67) | next sentence starts with "if" (-0.40) |

Second pass, strongest neighbour evidence: next sentence looks like assumption (p≥0.10) (+0.56); this sentence (1st pass) looks like definition (p≥0.10) (+0.50); previous sentence looks like definition (p≥0.10) (+0.42); this sentence (1st pass) looks like problem (p≥0.10) (+0.42); next sentence looks like definition (p≥0.50) (+0.40); two sentences before looks like problem (p≥0.10) (+0.40)

## claim  (τ = 0.4)

| for (weight) | against (weight) |
|---|---|
| contains "diagrams" (+1.02) | section title contains "weak" (-0.78) |
| section title contains "relations" (+0.99) | next sentence starts with "so" (-0.69) |
| section title contains "other" (+0.97) | contains "a function" (-0.68) |
| section title contains "mathcal" (+0.96) | starts with "let $…$" (-0.68) |
| section title contains "cylindric" (+0.93) | contains "is to" (-0.68) |
| section title contains "integrable" (+0.91) | right before a lemma environment (-0.67) |
| contains "optimal" (+0.89) | contains "smooth" (-0.63) |
| contains "see that" (+0.85) | position-in-paper decile 0 (-0.62) |
| combination: f1=further, sec=intro (+0.85) | contains "is also" (-0.61) |
| contains "hermitian" (+0.85) | section title contains "vertex" (-0.61) |
| contains "we note" (+0.84) | contains "called" (-0.61) |
| contains "$…$ as" (+0.83) | starts with "consider" (-0.60) |
| contains "then $…$" (+0.82) | contains "we" (-0.60) |
| contains "it follows" (+0.80) | section title contains "structured" (-0.60) |
| section title contains "spherical" (+0.80) | contains ";" (-0.60) |

Second pass, strongest neighbour evidence: this sentence (1st pass) looks like theorem (p≥0.10) (+0.66); next sentence looks like proof (p≥0.75) (+0.63); next sentence looks like example (p≥0.10) (+0.56); next sentence looks like open_problem (p≥0.75) (+0.54); two sentences before looks like proof (p≥0.10) (+0.45); this sentence (1st pass) looks like remark (p≥0.25) (+0.40)

## definition  (τ = 0.45)

| for (weight) | against (weight) |
|---|---|
| contains "called" (+1.44) | previous sentence starts with "\item" (-0.97) |
| cue phrase: def_denote (+1.23) | combination: emph, cue=def let be (-0.82) |
| cue phrase: def_called (+1.07) | contains "example" (-0.75) |
| contains "define" (+1.06) | contains "$…$ then" (-0.74) |
| contains "set [display]" (+0.97) | section title contains "field" (-0.72) |
| cue phrase: def_word (+0.94) | cue phrase: claim_derive (-0.70) |
| contains "introduce" (+0.89) | section title contains "example" (-0.69) |
| contains "map [display]" (+0.87) | contains "than" (-0.68) |
| position-in-paper decile 0 (+0.85) | in a section about Conclusion/Discussion (-0.67) |
| contains "let" (+0.84) | previous sentence starts with "we shall" (-0.67) |
| contains "be the" (+0.81) | contains "large" (-0.65) |
| combination: env before=proof, f1=em (+0.80) | ends with "map" (-0.64) |
| starts with "set" (+0.80) | cue phrase: claim_prove (-0.64) |
| contains "write $…$" (+0.79) | starts with "in fact" (-0.64) |
| section title contains "fields" (+0.78) | next sentence starts with "from" (-0.62) |

Second pass, strongest neighbour evidence: next sentence looks like definition (p≥0.75) (+0.90); next sentence looks like definition (p≥0.50) (+0.70); this sentence (1st pass) looks like example (p≥0.10) (+0.64); previous sentence looks like assumption (p≥0.25) (+0.57); next sentence looks like problem (p≥0.25) (+0.52); this sentence (1st pass) looks like problem (p≥0.50) (+0.46)

## theorem  (τ = 0.45)

| for (weight) | against (weight) |
|---|---|
| contains "\cite" (+1.43) | contains "our" (-0.83) |
| has a citation (+1.42) | contains "we" (-0.71) |
| contains "he" (+1.26) | share-of-math bucket 0 (-0.70) |
| contains "showed" (+1.25) | in a section about Algorithm/Method/Numerics (-0.63) |
| contains "proved" (+1.22) | contains "theorem \ref" (-0.63) |
| section title contains "previous" (+1.18) | cue phrase: ass_assume (-0.61) |
| starts with "he" (+1.06) | contains "such that" (-0.60) |
| contains "shown" (+1.06) | contains "be" (-0.52) |
| contains "showed that" (+1.05) | combination: cue=problem word, sec=intro (-0.50) |
| next sentence starts with "where" (+0.97) | contains "normal" (-0.48) |
| next sentence starts with "then" (+0.90) | contains "and let" (-0.48) |
| contains "bounded" (+0.88) | next sentence starts with "a" (-0.48) |
| combination: f1=\item, sec=prelim (+0.86) | contains "$…$ $…$" (-0.48) |
| contains "by \cite" (+0.81) | cue phrase: rem_note (-0.47) |
| next sentence starts with "theorem" (+0.78) | contains "points" (-0.45) |

Second pass, strongest neighbour evidence: this sentence (1st pass) looks like definition (p≥0.75) (+0.82); next sentence looks like theorem (p≥0.25) (+0.80); next sentence looks like remark (p≥0.10) (+0.58); previous sentence looks like remark (p≥0.10) (+0.57); this sentence (1st pass) looks like claim (p≥0.75) (+0.49); next sentence looks like theorem (p≥0.10) (+0.48)

## corollary  (τ = 0.5)

| for (weight) | against (weight) |
|---|---|
| combination: cue=claim follows, sec=none (+0.46) | paragraph-length bucket 3 (-0.33) |
| cue phrase: claim_follows (+0.42) | contains "of" (-0.32) |
| contains "s $…$" (+0.35) | last in its paragraph (-0.29) |
| contains "is bigger" (+0.35) | contains "to" (-0.27) |
| contains "bigger than" (+0.35) | inline-math count bucket 2 (-0.27) |
| contains "bigger" (+0.35) | ends with "$…$" (-0.27) |
| next sentence starts with "actually" (+0.35) | contains "$…$" (-0.23) |
| previous sentence starts with "as mentioned" (+0.35) | share-of-math bucket 2 (-0.19) |
| contains "the shannon" (+0.35) | share-of-math bucket 3 (-0.18) |
| ends with "s" (+0.34) | contains a displayed equation (-0.17) |
| contains "shannon" (+0.33) | contains "[display]" (-0.17) |
| contains "chernoff" (+0.33) | length bucket 0 (-0.15) |
| starts with "therefore the" (+0.33) | contains "and" (-0.15) |
| contains "therefore the" (+0.33) | contains "be" (-0.14) |
| contains "a corollary" (+0.33) | paragraph-length bucket 1 (-0.14) |

Second pass, strongest neighbour evidence: two sentences before looks like claim (p≥0.10) (+0.36); this sentence (1st pass) looks like claim (p≥0.25) (+0.26); this sentence (1st pass) looks like theorem (p≥0.50) (+0.22); this sentence (1st pass) looks like proof (p≥0.10) (+0.19); two sentences before looks like claim (p≥0.25) (+0.14); this sentence (1st pass) looks like remark (p≥0.75) (+0.13)

## lemma  (τ = 0.5)

| for (weight) | against (weight) |
|---|---|
| contains "lemma" (+0.61) | first in its paragraph (-0.44) |
| contains "chp" (+0.49) | contains "the" (-0.43) |
| section title contains "yokonuma" (+0.47) | inline-math count bucket 0 (-0.39) |
| section title contains "affine" (+0.47) | contains "and" (-0.35) |
| section title contains "hecke" (+0.47) | inline-math count bucket 2 (-0.32) |
| contains "$…$ [display]" (+0.46) | ends with "$…$" (-0.31) |
| contains "any" (+0.44) | share-of-math bucket 2 (-0.26) |
| section title contains "algebras" (+0.43) | contains "of" (-0.21) |
| contains "subgroup" (+0.42) | length bucket 0 (-0.21) |
| section title contains "wpd" (+0.41) | paragraph-length bucket 1 (-0.17) |
| section title contains "loxodromics" (+0.41) | has a \ref (-0.17) |
| section title contains "conjugacy" (+0.41) | contains "to" (-0.16) |
| section title contains "classes" (+0.41) | contains "\ref" (-0.16) |
| ends with "\cite" (+0.41) | position-in-paper decile 6 (-0.16) |
| section title contains "actions" (+0.40) | contains "$…$ and" (-0.15) |

Second pass, strongest neighbour evidence: next sentence looks like claim (p≥0.10) (+0.28); previous sentence looks like definition (p≥0.75) (+0.22); next sentence looks like proof (p≥0.10) (+0.21); this sentence (1st pass) looks like theorem (p≥0.25) (+0.20); next sentence looks like definition (p≥0.75) (+0.17); previous sentence looks like claim (p≥0.10) (+0.17)

## open_problem  (τ = 0.5)

| for (weight) | against (weight) |
|---|---|
| cue phrase: q_question (+1.66) | position-in-paper decile 4 (-0.52) |
| section title contains "conclusion" (+1.21) | contains "by" (-0.47) |
| in a section about Conclusion/Discussion (+1.09) | inline-math count bucket 3 (-0.44) |
| contains "question" (+1.07) | length bucket 4 (-0.43) |
| combination: cue=q question, sec=none (+1.04) | share-of-math bucket 3 (-0.41) |
| combination: f1=\item, sec=conclusion (+0.89) | length bucket 0 (-0.39) |
| contains "find" (+0.87) | contains "that" (-0.38) |
| ends with ? (+0.82) | position-in-paper decile 2 (-0.37) |
| contains "not" (+0.78) | combination: cue=claim derive, sec=none (-0.36) |
| contains "open" (+0.78) | contains "all" (-0.36) |
| contains "raised" (+0.75) | contains "can be" (-0.35) |
| contains "interest" (+0.73) | contains "has" (-0.35) |
| contains "it" (+0.70) | starts with "for" (-0.33) |
| position-in-paper decile 9 (+0.70) | contains "at" (-0.33) |
| combination: cue=q question, sec=intro (+0.66) | contains "set" (-0.32) |

Second pass, strongest neighbour evidence: next sentence looks like open_problem (p≥0.10) (+0.52); two sentences before looks like proof (p≥0.25) (+0.42); this sentence (1st pass) looks like open_problem (p≥0.50) (+0.41); previous sentence looks like theorem (p≥0.75) (+0.34); this sentence (1st pass) looks like theorem (p≥0.25) (+0.34); this sentence (1st pass) looks like open_problem (p≥0.10) (+0.34)

## proof  (τ = 0.5)

| for (weight) | against (weight) |
|---|---|
| first in its paragraph (+1.08) | contains "not" (-0.72) |
| right before a corollary environment (+1.07) | contains "general" (-0.70) |
| next sentence starts with "thus" (+1.07) | contains "condition" (-0.65) |
| cue phrase: proof_word (+1.07) | combination: f1=it, sec=none (-0.64) |
| contains "immediately" (+1.01) | contains ": [display]" (-0.63) |
| contains "follows" (+0.99) | contains "see that" (-0.60) |
| previous sentence starts with "we claim" (+0.93) | previous sentence starts with "hence" (-0.57) |
| right before a lemma environment (+0.92) | right after a definition environment (-0.56) |
| next sentence starts with "since" (+0.92) | next sentence starts with "here" (-0.56) |
| combination: f1=cm, sec=example (+0.92) | contains "paper" (-0.55) |
| contains "follows from" (+0.87) | section title contains "main" (-0.54) |
| contains "this follows" (+0.85) | right before a proof environment (-0.53) |
| contains "consequence of" (+0.85) | contains "used" (-0.53) |
| contains "and let" (+0.83) | contains "[display]" (-0.53) |
| ends with "duality" (+0.80) | right after a theorem environment (-0.53) |

Second pass, strongest neighbour evidence: two sentences before: none (region edge) (+0.85); previous sentence looks like theorem (p≥0.10) (+0.72); next sentence looks like proof (p≥0.50) (+0.71); next sentence looks like proof (p≥0.10) (+0.59); this sentence (1st pass) looks like claim (p≥0.10) (+0.46); previous sentence looks like claim (p≥0.50) (+0.46)

## proposition  (τ = 0.5)

| for (weight) | against (weight) |
|---|---|
| contains "proposition" (+0.85) | paragraph-length bucket 2 (-0.33) |
| ends with "proposition" (+0.58) | paragraph-length bucket 4 (-0.29) |
| section title contains "grand" (+0.54) | ends with "$…$" (-0.28) |
| section title contains "derivative" (+0.54) | contains "in" (-0.27) |
| section title contains "space" (+0.53) | length bucket 1 (-0.27) |
| section title contains "fractional" (+0.51) | inline-math count bucket 2 (-0.27) |
| section title contains "lebesgue" (+0.50) | contains "to" (-0.24) |
| section title contains "norm" (+0.50) | share-of-math bucket 2 (-0.21) |
| contains "that is" (+0.49) | contains "$…$" (-0.19) |
| section title contains "estimation" (+0.46) | first after a heading/environment (-0.18) |
| previous sentence starts with "mm" (+0.45) | no previous sentence in the region (-0.18) |
| combination: f1=\textbf, sec=none (+0.44) | contains "of" (-0.18) |
| no next sentence in the region (+0.41) | position-in-paper decile 4 (-0.16) |
| starts in bold (+0.40) | has a \ref (-0.14) |
| starts with "\textbf" (+0.39) | contains "\ref" (-0.14) |

Second pass, strongest neighbour evidence: two sentences before looks like assumption (p≥0.50) (+0.54); two sentences before looks like definition (p≥0.75) (+0.33); next sentence: none (region edge) (+0.33); next sentence looks like claim (p≥0.50) (+0.20); this sentence (1st pass) looks like claim (p≥0.10) (+0.16); this sentence (1st pass) looks like definition (p≥0.10) (+0.09)

## remark  (τ = 0.55)

| for (weight) | against (weight) |
|---|---|
| cue phrase: rem_note (+1.28) | position-in-paper decile 0 (-0.82) |
| first in its paragraph (+1.10) | contains "to be" (-0.74) |
| right after a theorem environment (+1.05) | next sentence starts with "then" (-0.67) |
| contains "inequality" (+0.94) | contains "very" (-0.62) |
| ends with "\emph" (+0.93) | contains "in $…$" (-0.62) |
| contains "warning" (+0.92) | emphasised term reused later, bucket 2 (-0.61) |
| ends with "warning" (+0.92) | contains "remark \ref" (-0.60) |
| starts with "warning" (+0.92) | contains "let" (-0.58) |
| previous sentence starts with "here $…$" (+0.91) | has a citation (-0.57) |
| contains "$…$ when" (+0.89) | contains "\cite" (-0.57) |
| contains "becomes" (+0.81) | contains "i e" (-0.55) |
| contains "diagram" (+0.80) | contains "“" (-0.53) |
| section title contains "fundamental" (+0.80) | contains "most" (-0.53) |
| right after a definition environment (+0.79) | contains "the proof" (-0.52) |
| contains "a function" (+0.78) | contains "method" (-0.52) |

Second pass, strongest neighbour evidence: previous sentence looks like remark (p≥0.75) (+0.66); next sentence looks like claim (p≥0.75) (+0.58); this sentence (1st pass) looks like claim (p≥0.10) (+0.57); next sentence looks like proof (p≥0.25) (+0.56); previous sentence looks like claim (p≥0.25) (+0.56); this sentence (1st pass) looks like claim (p≥0.75) (+0.53)

## algorithm  (τ = 0.6)

| for (weight) | against (weight) |
|---|---|
| contains "graph $…$" (+0.97) | contains "that" (-0.73) |
| combination: f1=center, sec=none (+0.97) | contains "by the" (-0.53) |
| ends with "center" (+0.89) | contains "any" (-0.53) |
| starts with "center" (+0.84) | paragraph-length bucket 2 (-0.49) |
| contains "distributed" (+0.82) | contains "when" (-0.49) |
| contains "as follows" (+0.76) | contains "for $…$" (-0.48) |
| contains "center" (+0.73) | before any section (-0.48) |
| contains "buffer" (+0.73) | contains "which is" (-0.46) |
| section title contains "sampling" (+0.72) | next sentence starts with "it" (-0.45) |
| section title contains "design" (+0.71) | position-in-paper decile 9 (-0.45) |
| section title contains "approach" (+0.69) | contains "also" (-0.45) |
| cue phrase: alg_step (+0.69) | contains "at" (-0.44) |
| ends with ":" (+0.65) | cue phrase: claim_derive (-0.44) |
| next sentence starts with "\textbf" (+0.64) | cue phrase: def_word (-0.43) |
| contains "based on" (+0.64) | contains "from the" (-0.39) |

Second pass, strongest neighbour evidence: this sentence (1st pass) looks like remark (p≥0.10) (+0.45); previous sentence looks like algorithm (p≥0.10) (+0.32); this sentence (1st pass) looks like theorem (p≥0.10) (+0.29); two sentences before looks like claim (p≥0.50) (+0.29); this sentence (1st pass) looks like definition (p≥0.75) (+0.29); two sentences before looks like definition (p≥0.50) (+0.25)

## example  (τ = 0.8)

| for (weight) | against (weight) |
|---|---|
| contains "example" (+2.02) | position-in-paper decile 1 (-0.84) |
| cue phrase: ex_example (+1.23) | last in its paragraph (-0.61) |
| section title contains "complete" (+1.23) | contains ": [display]" (-0.54) |
| previous sentence starts with "\item" (+1.06) | previous sentence starts with "we" (-0.52) |
| section title contains "graphs" (+1.00) | starts with "in" (-0.51) |
| contains "examples of" (+0.88) | previous sentence starts with "in" (-0.48) |
| contains "not" (+0.84) | combination: cue=def let be, sec=none (-0.44) |
| starts with "let $…$ where" (+0.81) | section title contains "algorithm" (-0.43) |
| contains "a smooth" (+0.79) | contains "it" (-0.43) |
| combination: f1=level, sec=example (+0.79) | contains "will" (-0.42) |
| starts with "level $…$ $…$" (+0.79) | contains "in the" (-0.42) |
| starts with "level $…$" (+0.79) | position-in-paper decile 9 (-0.40) |
| starts with "level" (+0.79) | contains "form" (-0.39) |
| contains "examples" (+0.76) | contains "section" (-0.39) |
| position-in-paper decile 6 (+0.76) | position-in-paper decile 3 (-0.39) |

Second pass, strongest neighbour evidence: two sentences before looks like claim (p≥0.10) (+0.75); this sentence (1st pass) looks like proof (p≥0.25) (+0.54); this sentence (1st pass) looks like definition (p≥0.25) (+0.50); two sentences before looks like example (p≥0.10) (+0.49); previous sentence looks like theorem (p≥0.75) (+0.46); this sentence (1st pass) looks like assumption (p≥0.10) (+0.41)

