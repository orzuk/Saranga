#!/usr/bin/env python3
"""Score parse_batch JSONs against the silver gold, the way score_state did.

The held-out number in the deck (pooled M3 F1 0.7563) came from a scoring pass
that parsed in memory and kept only counts. This re-derives the same figure from
the SAVED graph JSONs, so the two can be compared: same gold, same metric,
same threshold and cover, same 14 types.

Only the 140 held-out papers are scored by default. The 200-paper parse also
covers the 60 training papers, but those chose the rules, so pooling them in
would not be the reported quantity.

Buckets are rebuilt the way the scoring path built them -- `raw_latex`, falling
back to `statement` -- from `nodes`, which is what to_unified_dict() emits.
Node types outside the 14 (equations, tables) are ignored, exactly as the
scoring path ignored them by having no bucket to put them in.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import silver_distillation_sequential as seq
from silver_distillation_merged import FNAME_MAP, load_gold_texts, metrics, _all_gold


def buckets_from_json(path, types):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = d.get("nodes") or d.get("objects") or []
    if isinstance(nodes, dict):
        nodes = list(nodes.values())
    b = {t: [] for t in types}
    for o in nodes:
        t = o.get("type") or o.get("kind")
        if t in b:
            raw = (o.get("raw_latex") or o.get("statement") or "")
            if raw.strip():
                b[t].append(raw)
    return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-dir", required=True)
    ap.add_argument("--gold-dir", required=True)
    ap.add_argument("--reference", default=None,
                    help="heldout_scores.jsonl to compare against")
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--cover", type=float, default=0.7)
    ap.add_argument("--match-metric", default="containment")
    ap.add_argument("--mode", default="m3", choices=["m1", "m3"])
    args = ap.parse_args()

    seq.set_match_metric(args.match_metric)
    types = list(FNAME_MAP.keys())
    gold = {t: load_gold_texts(Path(args.gold_dir) / FNAME_MAP[t]) for t in types}

    ref, papers = {}, None
    if args.reference:
        for line in open(args.reference, encoding="utf-8"):
            r = json.loads(line)
            if r["mode"] == args.mode:
                ref[r["paper_id"]] = r
        papers = list(ref)
    jdir = Path(args.json_dir)
    if papers is None:
        papers = sorted(p.name.replace("_rules.json", "")
                        for p in jdir.glob("*_rules.json"))

    agg = Counter()
    per_type_tp, per_type_fp = Counter(), Counter()
    missing, moved = [], []
    for pid in papers:
        f = jdir / f"{pid}_rules.json"
        if not f.exists():
            missing.append(pid)
            continue
        b = buckets_from_json(f, types)
        support = _all_gold(gold, pid, types)
        row = Counter()
        for t in types:
            m = metrics(b[t], gold[t].get(pid, []), args.threshold,
                        mode=args.mode, support_texts=support, cover=args.cover)
            for k in ("tp", "tp_recall", "fp", "fn"):
                row[k] += m[k]
            per_type_tp[t] += m["tp"]; per_type_fp[t] += m["fp"]
        agg.update(row)
        if pid in ref:
            was = ref[pid]
            if (row["tp"], row["fp"], row["fn"]) != (was["tp"], was["fp"], was["fn"]):
                moved.append((pid, (was["tp"], was["fp"], was["fn"]),
                              (row["tp"], row["fp"], row["fn"])))

    if missing:
        print(f"[warn] {len(missing)} paper(s) have no JSON: {missing[:5]}")
    p = agg["tp"] / (agg["tp"] + agg["fp"]) if agg["tp"] + agg["fp"] else 0.0
    r = agg["tp_recall"] / (agg["tp_recall"] + agg["fn"]) if agg["tp_recall"] + agg["fn"] else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    n = len(papers) - len(missing)
    print(f"\nFROM SAVED JSONs  ({n} papers, {args.mode}, {args.match_metric}, "
          f"th={args.threshold}, cover={args.cover})")
    print(f"  tp {agg['tp']}  fp {agg['fp']}  tp_recall {agg['tp_recall']}  fn {agg['fn']}")
    print(f"  precision {p:.4f}   recall {r:.4f}   F1 {f1:.4f}")

    if ref:
        R = Counter()
        for pid in papers:
            if pid in ref and pid not in missing:
                for k in ("tp", "tp_recall", "fp", "fn"):
                    R[k] += ref[pid][k]
        rp = R["tp"] / (R["tp"] + R["fp"])
        rr = R["tp_recall"] / (R["tp_recall"] + R["fn"])
        rf = 2 * rp * rr / (rp + rr)
        print(f"\nREPORTED RUN")
        print(f"  tp {R['tp']}  fp {R['fp']}  tp_recall {R['tp_recall']}  fn {R['fn']}")
        print(f"  precision {rp:.4f}   recall {rr:.4f}   F1 {rf:.4f}")
        print(f"\nDELTA  F1 {f1 - rf:+.4f}   precision {p - rp:+.4f}   "
              f"recall {r - rr:+.4f}")
        print(f"papers whose counts moved: {len(moved)}/{n}")
        for pid, a, bb in moved[:8]:
            print(f"   {pid}  (tp,fp,fn) {a} -> {bb}")


if __name__ == "__main__":
    main()
