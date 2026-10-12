#!/usr/bin/env python3
"""Per-type errors of an alg3 extractor on the VALIDATION papers (never test).

    python3 alg3/analyze.py --model alg3/runs/v1 [--examples 3]
"""
from __future__ import annotations

import argparse
import importlib.util
import pickle
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (HERE, REPO / "scripts", REPO / "src" / "LLMVersion", REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import distill_units as DU                                   # noqa: E402
import latex_facts as L                                      # noqa: E402
import train as TR                                           # noqa: E402


def load_runtime(model_dir: Path):
    sys.path.insert(0, str(model_dir))
    spec = importlib.util.spec_from_file_location("alg3_runtime", model_dir / "alg3_runtime.py")
    rt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rt)
    return rt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", default=str(HERE / "cache/papers.pkl"))
    ap.add_argument("--examples", type=int, default=3)
    a = ap.parse_args()
    papers = pickle.load(open(a.data, "rb"))
    val = sorted(p for p, (s, _) in papers.items() if s == "val")
    rt = load_runtime(Path(a.model))
    scorer = DU.Scorer({pid: p for pid, (_, p) in papers.items()}, 0.7, metric="m1g")
    by_type = defaultdict(lambda: Counter())
    conf = Counter()
    fps, fns = defaultdict(list), defaultdict(list)
    preds_all = {}
    for pid in val:
        p = papers[pid][1]
        preds = [dict(n, uid=0) for n in rt.tag(p.text, L.extract_facts(p.text), p.sents)]
        preds_all[pid] = preds
        taken = set()
        for pred in preds:
            k, w = TR.match(scorer, p, pred, taken)
            if k is not None:
                taken.add(k)
                n = p.nodes[k]
                if n.base_covered:
                    by_type[pred["type"]]["neutral"] += 1
                    continue
                by_type[pred["type"]]["tp"] += w
                by_type[pred["type"]]["fp"] += 1 - w
                if n.type != pred["type"]:
                    conf[(n.type, pred["type"])] += 1
            else:
                by_type[pred["type"]]["fp"] += 1
                fps[pred["type"]].append((pid, p.text[pred["start"]:pred["end"]][:160]))
        for k, n in enumerate(p.nodes):
            if not n.base_covered:
                by_type[n.type]["gold"] += 1
            if k not in taken and not n.base_covered:
                fns[n.type].append((pid, p.text[n.start:n.end][:160]))
    print(TR.evaluate(scorer, papers, val, preds_all))
    print(f"\n{'type':<13}{'gold':>6}{'tp':>8}{'fp':>8}{'fn':>6}{'P':>7}{'R':>7}")
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]["gold"]):
        tp, fp, g = c["tp"], c["fp"], c["gold"]
        print(f"{t:<13}{g:>6}{tp:>8.1f}{fp:>8.1f}{len(fns[t]):>6}"
              f"{(tp / (tp + fp) if tp + fp else 0):>7.2f}{(tp / g if g else 0):>7.2f}")
    print("\ntype confusions (silver -> predicted):", conf.most_common(8))
    rnd = random.Random(0)
    for t in ("definition", "claim", "remark", "theorem"):
        print(f"\n== {t}: sample FP")
        for x in rnd.sample(fps[t], min(a.examples, len(fps[t]))):
            print("   ", x[0], repr(x[1]))
        print(f"== {t}: sample FN")
        for x in rnd.sample(fns[t], min(a.examples, len(fns[t]))):
            print("   ", x[0], repr(x[1]))


if __name__ == "__main__":
    main()
