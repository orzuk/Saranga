# opus-5.5__v7_blueprint — v7 extractions of the Lean blueprints

The human and mixed-provenance Lean blueprints of `corpus/gold_blueprints/` (98: a pilot of 5 and 93 more), extracted
2026-10-19/20 with exactly the prompt and code of the v7 silver (`prompt_opus_v7.md`, one Claude Opus 5.5 agent per
blueprint). The only differences are the input and the title: each blueprint's `blueprint.tex` with the Lean macros
(`\uses`, `\lean`, `\leanok`, `\proves`) removed, because the declared dependencies are the gold, and the title
"<repo> (Lean blueprint)". The agents did not read `all.tex`, `graph.json` or `meta.json`.

**Scores against the blueprints' own dependency graphs** (`docs/v7_handoff/gold_eval_bp_v7.py`, json next to it; 97
blueprints, those in `corpus/gold_blueprints/excluded.json` skipped; a v7 node that keeps a restated result once also
matches the blueprint's copies, `graph_score.copy_matches`): dependency edge P 0.457, R 0.739, F1 0.565 [0.525, 0.602];
hierarchy-invariant F1 0.696; recall on dependencies on definitions 0.78 (rules 0.19). Rules baseline F1 0.399.
Against the gold without empty or placeholder proofs (`--text-only`, `gold_eval_bp_v7_textonly.json`): F1 0.560,
R 0.767. Human blueprints (73) 0.547, mixed (24) 0.612. Precision is low because blueprints declare few
dependencies; many of v7's extra term edges are undeclared but real.

**Statistics:** 29,810 nodes and 45,988 edges.

**Known issues:** v7 merges restated results (`also_stated_at`) while the gold keeps the copies; empty proof
environments get no node; finalize does not treat 。 as a sentence end (cluster_sfuk_lean, lean_Galois have no proof
steps), does not read environments without `\newtheorem` or custom ref macros, and misplaces identical proof bodies
(ramanujan_nagell, fixed by hand). Weak golds still scored: m2r-group-7, evm-equivalence and the skeletons
FontaineWintenberger, RamificationGroup, elementary-toposes, AlgoLib.
