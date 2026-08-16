#!/usr/bin/env python3
"""LLM-as-judge false-positive adjustment (read-only post-distillation step)
============================================================================
The silver "gold" is Opus's tier2 extraction, which UNDER-LABELS some types
(e.g. it skips inline "X is defined as ..." definitions). A rule that extracts
such an item is scored as a false positive even though it is correct. This tool
re-judges each FP with an LLM: a FP that is in fact a GENUINE instance of its
type (silver simply missed it) is removed from the FP count, lifting precision.

It is a READ-ONLY CONSUMER of existing artifacts (final snapshot rules + silver
gold). It does NOT modify the distilled rules, the prune step, or any
LLM-generation path — it only recomputes adjusted precision/F1 and writes a
report. Mirrors final_eval.py's parse/match logic.

Usage:
    python scripts/fp_judge.py \
        --eval-dir src/LLMVersion/merged_eval_silver_001_011_v3 \
        --tex-dir /Users/yaronot/Datasets/Authomathics_data/alignment/papers \
        --match-metric containment
"""

import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import silver_distillation_sequential as seq
from silver_distillation_sequential import jaccard_similarity
from silver_distillation_merged import FNAME_MAP, parse_buckets, load_gold_texts
from distillation_analysis import _parse_json_array, _acc_usage, _empty_usage

# One-line working definitions to anchor the judge per type.
TYPE_GUIDE = {
    "definition": "introduces and NAMES a mathematical object/notion ('X is "
                  "defined as ...', 'we define X as ...', 'We say X is Y if ...'). "
                  "NOT: restating a known fact ('Recall that ...'), local scratch "
                  "notation, or a passing mention.",
    "theorem": "a formally stated, named principal result with a claim.",
    "lemma": "a formally stated auxiliary result used to prove something else.",
    "proposition": "a formally stated secondary result.",
    "corollary": "a result stated as an immediate consequence of another.",
    "claim": "a stated assertion, usually inside a proof.",
    "conjecture": "an unproven stated assertion believed true.",
    "problem": "a posed problem / task / optimization formulation.",
    "proof": "an argument establishing a stated result.",
    "remark": "an author observation/comment.",
    "algorithm": "a named step-by-step procedure / pseudocode.",
    "example": "a worked example illustrating a concept.",
    "assumption": "a standing hypothesis/condition imposed for later results.",
    "open_problem": "an explicitly unsolved question posed for future work.",
}


def find_fps(extracted, gold_texts, threshold, *, match_mode="m1",
             support_texts=None, cover=0.7):
    """Return the extracted items that count as false positives, plus tp count.

    Under ``m1`` this is bipartite matching, exactly as before. Under ``m3`` an
    extraction contained in any gold node of ANY type is not a false positive,
    so the judge only ever sees the residual — text the silver has nothing like.
    That is a ~20x smaller queue, and it is the only bucket a model can help
    with: nesting, labels and span boundaries are settled mechanically.
    """
    if match_mode != "m1":
        import match_modes as _mm
        verdicts = _mm.classify_extractions(
            extracted, gold_texts, threshold, mode=match_mode,
            support_texts=support_texts, cover=cover)
        fps = [e for e, ok in zip(extracted, verdicts) if not ok]
        return fps, sum(verdicts)
    pairs = []
    for i, ext in enumerate(extracted):
        for j, g in enumerate(gold_texts):
            if jaccard_similarity(ext, g) >= threshold:
                pairs.append((jaccard_similarity(ext, g), i, j))
    pairs.sort(reverse=True)
    matched_ext, matched_gold = set(), set()
    for _, i, j in pairs:
        if i in matched_ext or j in matched_gold:
            continue
        matched_ext.add(i)
        matched_gold.add(j)
    fps = [ext for i, ext in enumerate(extracted) if i not in matched_ext]
    return fps, len(matched_ext)


def judge_batch(client, model, stype, snippets, match_mode="m1"):
    """Return list of dicts {index, verdict, reason} for one type's FPs."""
    guide = TYPE_GUIDE.get(stype, f"an instance of '{stype}'.")
    if match_mode != "m1":
        # Under m3 everything nested / mislabelled / boundary-shifted has
        # already been resolved mechanically, so "is this really a {stype}?"
        # is the wrong question — it was asked before and answered GENUINE
        # 106 times out of 151, correctly, while the real issue was that the
        # span sat inside a proof the silver kept whole. What is left is only
        # text the silver has NOTHING resembling, so ask about that.
        sys_block = (
            "You are a careful mathematics-annotation judge. Each span below "
            "was extracted from a paper by a rule-based parser, and the "
            "reference annotation contains nothing resembling it — it is not a "
            "differently-labelled, differently-cut or nested version of any "
            "annotated node.\n\n"
            f"A '{stype}' is: {guide}\n\n"
            "So exactly one of these is true. Decide which:\n"
            "  GENUINE - a real {0} that the reference annotation MISSED "
            "entirely (the annotation is incomplete here)\n"
            "  FALSE_POSITIVE - not a {0} at all; the parser grabbed prose, "
            "boilerplate or a fragment (a real extraction error)\n"
            .format(stype)
        )
        parts = [f"Judge these {len(snippets)} unmatched '{stype}' spans.\n"]
        for k, sn in enumerate(snippets):
            parts.append(f"\n### Item {k}\n```\n{sn[:1200]}\n```\n")
        parts.append(
            "\nRespond with ONLY a JSON array (no fences), one object per item, "
            'same order: [{"index": <int>, "verdict": "GENUINE"|"FALSE_POSITIVE", '
            '"reason": "<short>"}]')
        return _call_judge(client, model, sys_block, "".join(parts))
    sys_block = (
        "You are a careful mathematics-annotation judge. You decide whether an "
        "extracted text span is a GENUINE instance of a given structure type. "
        "The reference annotation may have MISSED real instances, so do not "
        "assume an extraction is wrong just because it was flagged.\n\n"
        f"A '{stype}' is: {guide}\n\n"
        "For each item answer:\n"
        "  GENUINE  — it really IS a {0}; the reference missed it (NOT a true FP)\n"
        "  FALSE_POSITIVE — it is NOT a {0} (a real extraction error)\n"
        .format(stype)
    )
    parts = [f"Judge these {len(snippets)} candidate '{stype}' spans.\n"]
    for k, s in enumerate(snippets):
        parts.append(f"\n### Item {k}\n```\n{s[:1200]}\n```\n")
    parts.append(
        "\nRespond with ONLY a JSON array (no fences), one object per item, "
        'same order: [{"index": <int>, "verdict": "GENUINE"|"FALSE_POSITIVE", '
        '"reason": "<short>"}]'
    )
    return _call_judge(client, model, sys_block, "".join(parts))


def _call_judge(client, model, sys_block, user_text):
    """One judge call -> ({index: verdict-dict}, usage). Shared by both modes."""
    try:
        msg = client.messages.create(
            model=model, max_tokens=2048,
            system=[{"type": "text", "text": sys_block,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_text}],
        )
    except Exception:
        msg = client.messages.create(
            model=model, max_tokens=2048, system=sys_block,
            messages=[{"role": "user", "content": user_text}],
        )
    by_index = {}
    for obj in _parse_json_array(msg.content[0].text):
        try:
            by_index[int(obj.get("index"))] = obj
        except (TypeError, ValueError):
            continue
    return by_index, msg.usage


def main():
    import glob
    p = argparse.ArgumentParser(description="LLM-as-judge FP adjustment")
    p.add_argument("--eval-dir", required=True)
    p.add_argument("--tex-dir", required=True)
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--match-mode", default="m1", choices=["m1", "m3"],
                   help="Must match what the run pruned with. m1 = judge every "
                        "unmatched extraction (today). m3 = judge only the "
                        "residual the metric cannot settle mechanically.")
    p.add_argument("--cover", type=float, default=0.7)
    p.add_argument("--match-metric", default="containment",
                   choices=["jaccard", "containment"])
    p.add_argument("--batch-size", type=int, default=10)
    p.add_argument("--types", default=None,
                   help="comma list (default: all with gold)")
    args = p.parse_args()

    seq._MATCH_METRIC = args.match_metric
    eval_dir = Path(args.eval_dir).resolve()
    tex_dir = Path(args.tex_dir).resolve()
    gold_dir = eval_dir / "silver_gold"
    types = ([t.strip() for t in args.types.split(",")] if args.types
             else list(FNAME_MAP.keys()))

    snaps = sorted((eval_dir / "snapshots").glob("step_*"))
    if not snaps:
        print(f"ERROR: no snapshots under {eval_dir/'snapshots'}"); sys.exit(1)
    final = snaps[-1]
    papers = [e["paper_id"] for e in
              json.load(open(eval_dir / "iteration_log.json", encoding="utf-8"))]
    gold = {t: load_gold_texts(gold_dir / FNAME_MAP[t]) for t in types}

    # 1. Collect FPs per type (read-only parse with final rules).
    print(f"Final snapshot: {final.name} | papers: {len(papers)} | "
          f"match: {args.match_metric} | mode: {args.match_mode}\n")
    if args.match_mode != "m1":
        print("  [m3] nesting / labels / boundaries already settled by the "
              "metric; judging only the residual.\n")
    fp_items = {t: [] for t in types}   # (paper_id, snippet)
    tp_count = {t: 0 for t in types}
    for pid in papers:
        buckets = parse_buckets(pid, tex_dir, types, eval_dir=final)
        for t in types:
            support = [g for tt in types for g in gold[tt].get(pid, [])]
            fps, tp = find_fps(buckets[t], gold[t].get(pid, []), args.threshold,
                               match_mode=args.match_mode,
                               support_texts=support, cover=args.cover)
            tp_count[t] += tp
            for s in fps:
                fp_items[t].append((pid, s))

    # 2. Judge each type's FPs in batches.
    import anthropic
    client = anthropic.Anthropic()
    usage = _empty_usage()
    rows = []          # report rows
    adj = {}           # type -> {raw_fp, real_fp, rescued, tp}
    for t in types:
        items = fp_items[t]
        if not items:
            adj[t] = dict(raw_fp=0, real_fp=0, rescued=0, tp=tp_count[t])
            continue
        snippets = [s for _, s in items]
        real_fp = rescued = 0
        for b in range(0, len(snippets), args.batch_size):
            batch = snippets[b:b + args.batch_size]
            by_index, u = judge_batch(client, args.model, t, batch,
                                      match_mode=args.match_mode)
            usage["llm_calls"] += 1
            _acc_usage(usage, u)
            for k, snip in enumerate(batch):
                v = (by_index.get(k, {}) or {}).get("verdict", "FALSE_POSITIVE")
                reason = (by_index.get(k, {}) or {}).get("reason", "")
                is_real = (v != "GENUINE")
                real_fp += int(is_real)
                rescued += int(not is_real)
                rows.append({"type": t, "paper_id": items[b + k][0],
                             "verdict": v, "reason": reason,
                             "snippet": snip[:300].replace("\n", " ")})
        adj[t] = dict(raw_fp=len(items), real_fp=real_fp,
                      rescued=rescued, tp=tp_count[t])
        print(f"  {t:13s} raw_fp={len(items):3d}  rescued={rescued:3d}  "
              f"real_fp={real_fp:3d}")

    # 3. Adjusted precision (recall/gold unchanged; rescued FPs are NOT new TPs
    #    against gold — they are correct extractions the silver gold lacks).
    def prec(tp, fp):
        return tp / (tp + fp) if (tp + fp) else 0.0

    print("\n" + "=" * 64)
    print(f"{'type':13s} {'tp':>4} {'rawFP':>6} {'realFP':>6} "
          f"{'P_raw':>6} {'P_adj':>6}")
    print("-" * 64)
    tot_tp = tot_raw = tot_real = 0
    for t in types:
        a = adj[t]
        if a["tp"] == 0 and a["raw_fp"] == 0:
            continue
        tot_tp += a["tp"]; tot_raw += a["raw_fp"]; tot_real += a["real_fp"]
        print(f"{t:13s} {a['tp']:>4} {a['raw_fp']:>6} {a['real_fp']:>6} "
              f"{prec(a['tp'], a['raw_fp']):>6.2f} "
              f"{prec(a['tp'], a['real_fp']):>6.2f}")
    print("-" * 64)
    print(f"{'POOLED':13s} {tot_tp:>4} {tot_raw:>6} {tot_real:>6} "
          f"{prec(tot_tp, tot_raw):>6.2f} {prec(tot_tp, tot_real):>6.2f}")

    # 4. Write artifacts.
    csv_path = eval_dir / "fp_judge.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["type", "paper_id", "verdict",
                                          "reason", "snippet"])
        w.writeheader(); w.writerows(rows)
    print(f"\nWrote {csv_path}  ({len(rows)} judged FPs)")
    print(f"LLM: {usage['llm_calls']} call(s), "
          f"{usage['input_tokens']} in / {usage['output_tokens']} out "
          f"(cache_read {usage['cache_read_input_tokens']})")


if __name__ == "__main__":
    main()
