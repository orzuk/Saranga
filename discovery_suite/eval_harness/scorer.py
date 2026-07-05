"""Score a ranked list of predicted node pairs against planted gold.

Metrics: precision@k, recall@k, average precision (AP), and the headline
detection-vs-obfuscation curve (recall per obfuscation level). Predictions are
undirected node-pair keys with a score; gold is the set of planted↔source pairs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass
class EvalResult:
    n_gold: int
    n_pred: int
    precision_at_k: dict[int, float]
    recall_at_k: dict[int, float]
    average_precision: float
    recall_by_level: dict[str, float]      # detection-vs-obfuscation curve

    def format(self) -> str:
        lines = [
            f"gold pairs        : {self.n_gold}",
            f"predicted pairs   : {self.n_pred}",
            f"average precision : {self.average_precision:.3f}",
            "precision@k       : " + ", ".join(f"{k}={v:.3f}" for k, v in self.precision_at_k.items()),
            "recall@k          : " + ", ".join(f"{k}={v:.3f}" for k, v in self.recall_at_k.items()),
            "recall by level   : " + ", ".join(f"{lv}={v:.2f}" for lv, v in sorted(self.recall_by_level.items())),
        ]
        return "\n".join(lines)


def evaluate(
    predictions: Iterable[tuple[str, str, float]],
    gold_pairs: set[frozenset],
    *,
    gold_levels: Optional[dict[frozenset, str]] = None,
    ks: Iterable[int] = (10, 50, 100, 500),
) -> EvalResult:
    """`predictions`: iterable of (key_a, key_b, score), any order (sorted here)."""
    preds = sorted(predictions, key=lambda x: -x[2])
    pred_sets = [frozenset({a, b}) for a, b, _ in preds]
    n_gold = len(gold_pairs)
    n_pred = len(preds)

    hits = [1 if ps in gold_pairs else 0 for ps in pred_sets]

    prec_at_k, rec_at_k = {}, {}
    for k in ks:
        topk = hits[:k]
        tp = sum(topk)
        prec_at_k[k] = tp / max(1, min(k, n_pred))
        rec_at_k[k] = tp / max(1, n_gold)

    # Average precision over the ranked list.
    ap, tp = 0.0, 0
    for i, h in enumerate(hits, 1):
        if h:
            tp += 1
            ap += tp / i
    average_precision = ap / max(1, n_gold)

    # Detection-vs-obfuscation: recall per level (a gold pair counts as found if
    # it appears anywhere in the predictions).
    recall_by_level: dict[str, float] = {}
    if gold_levels:
        found = set(pred_sets)
        per_level_total: dict[str, int] = {}
        per_level_found: dict[str, int] = {}
        for gp, lv in gold_levels.items():
            per_level_total[lv] = per_level_total.get(lv, 0) + 1
            if gp in found:
                per_level_found[lv] = per_level_found.get(lv, 0) + 1
        for lv, tot in per_level_total.items():
            recall_by_level[lv] = per_level_found.get(lv, 0) / max(1, tot)

    return EvalResult(
        n_gold=n_gold, n_pred=n_pred,
        precision_at_k=prec_at_k, recall_at_k=rec_at_k,
        average_precision=average_precision, recall_by_level=recall_by_level,
    )
