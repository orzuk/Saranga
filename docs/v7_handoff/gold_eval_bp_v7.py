#!/usr/bin/env python3
"""Score the v7 LLM extractions of the Lean blueprints against the blueprints' own dependency graphs.

    python3 docs/v7_handoff/gold_eval_bp_v7.py [--out docs/v7_handoff/gold_eval_bp_v7.json]

For each blueprint with an extraction in corpus/silver/opus-5.5__v7_blueprint/<id>.json (made from the blueprint
without \\uses, \\lean, \\leanok, \\proves), scored against corpus/gold_blueprints/<id>/graph.json with the presets of
scripts/gold_candidates/score_gold.py: 'blueprint' (declared + cited dependencies), 'blueprint_uses' (declared
only), 'blueprint_inv' (hierarchy-invariant). The rule-based extractions of the same blueprints (rules.json,
tagger.json, ta.json = alg3 T-A with the all-pairs edges, made by score_gold.py) are scored on the same blueprints for comparison. Pooled P/R/F1 with 95%
bootstrap intervals over blueprints, as in score_gold.summary. Blueprints in corpus/gold_blueprints/excluded.json
are skipped. --text-only scores against the gold without empty proofs and statements (see text_only).
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src/LLMVersion"), str(REPO / "src"), str(REPO / "scripts/gold_candidates")]
import blueprint_quality as BQ  # noqa: E402
import graph_score as GS  # noqa: E402
import score_gold as SG  # noqa: E402

V7 = REPO / "corpus/silver/opus-5.5__v7_blueprint"
PRESETS = SG.SETS["blueprint"][3]
EXCLUDED = json.loads((REPO / "corpus/gold_blueprints/excluded.json").read_text())


def text_only(gold):
    """The gold a reader of the text can recover: without proofs and statements that have no text (empty
    placeholders, "To do.", "No documentation.") and without the dependencies declared only inside them."""
    gone = {n["id"] for n in gold["nodes"] if BQ.empty(n.get("statement")) or (
        n["type"] == "proof" and BQ.PLACEHOLDER.match(" ".join((n.get("statement") or "").split())))}
    return dict(gold, nodes=[n for n in gold["nodes"] if n["id"] not in gone],
                edges=[e for e in gold["edges"] if e["source"] not in gone and e["target"] not in gone])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default=str(REPO / "docs/v7_handoff/gold_eval_bp_v7.json"))
    ap.add_argument("--text-only", action="store_true", help="score against text_only(gold)")
    a = ap.parse_args()
    root = SG.SETS["blueprint"][0]
    results = {}
    for f in sorted(V7.glob("*.json")):
        if f.stem in EXCLUDED:
            continue
        d = root / f.stem
        gold = json.loads((d / "graph.json").read_text())
        if a.text_only:
            gold = text_only(gold)
        preds = {"v7": json.loads(f.read_text())}
        preds |= {x: json.loads((d / f"{x}.json").read_text()) for x in ("rules", "tagger", "ta") if (d / f"{x}.json").is_file()}
        results[f.stem] = {x: {p: (c := GS.score(pred, gold, **GS.PRESETS[p])) | GS.pooled([c]) for p in PRESETS}
                           for x, pred in preds.items()}
    extractors = [x for x in ("v7", "rules", "tagger", "ta") if all(x in r for r in results.values())]
    summary = SG.summary(results, extractors, PRESETS)
    Path(a.out).write_text(json.dumps({"blueprints": len(results), "summary": summary, "per_item": results}, indent=1))
    print(len(results), "blueprints")
    for k, s in summary.items():
        print(f"{k:22s} node P {s.get('node_P', 0):.3f} R {s.get('node_R', 0):.3f}   edge P {s.get('edge_P', 0):.3f} "
              f"R {s.get('edge_R', 0):.3f} F1 {s.get('edge_F1', 0):.3f} {[round(v, 3) for v in s['ci95'].get('edge_F1', [])]}"
              f"   R(res) {s.get('edge_R_res', 0):.3f} R(def) {s.get('edge_R_def', 0):.3f}")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
