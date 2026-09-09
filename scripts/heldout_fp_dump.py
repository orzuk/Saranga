#!/usr/bin/env python3
"""Recover the M3 false positives of the 146-rule held-out run, verbatim.

`score_state` wrote counts, not spans: heldout_scores.jsonl says paper
1001.2291v2 produced 15 M3 false positives but not which 15. Judging them needs
the text, so this re-parses the same 140 papers under the same rule set and
re-derives the same classification.

Re-parsing is not a second look at the held-out set. The parse is deterministic
and the rules are frozen, so this reconstructs the run that already happened
rather than sampling a new one -- and the script proves that rather than
asserting it: every per-paper, per-type tp/fp/fn it computes is checked against
the row score_state already wrote, and any disagreement is a hard failure. If
the numbers match, the FP list is by construction the one behind 0.7563.

Buckets are cached to disk on the way through, so the ~105 CPU-minutes of
parsing is spent once no matter how often the FP list is rebuilt.

Usage:
    python scripts/heldout_fp_dump.py \
        --eval-dir src/LLMVersion/heldout_eval_selected146 \
        --gold-dir src/LLMVersion/merged_eval_v51_train60_v2/silver_gold \
        --tex-dir corpus/silver/tex_staged --workers 6
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import silver_distillation_sequential as seq
import silver_distillation_merged as sdm
from silver_distillation_merged import (
    FNAME_MAP, load_gold_texts, metrics, _all_gold, installed_rules)


def parse_incremental(papers, tex_dir, types, eval_dir, cache: Path,
                      workers: int):
    """Parse into an append-as-you-go cache, skipping what is already there.

    `parse_all` returns one dict at the end, so a run killed at paper 139 keeps
    nothing -- which is exactly what happened once, at the cost of 20 minutes
    of someone's laptop. One JSONL line per paper, flushed on arrival, makes an
    interruption cost only the papers in flight.

    The rules are installed ONCE around the whole fan-out, not per paper: the
    install renames a shared path and symlinks over it, so it is not
    concurrency-safe, while the parse itself only reads. Children therefore run
    under the state the parent holds -- the same arrangement `parse_all` uses,
    and the reason its results are byte-identical to a serial loop.
    """
    import multiprocessing as _mp

    done = {}
    if cache.exists():
        for line in open(cache, encoding="utf-8"):
            d = json.loads(line)
            done[d["paper_id"]] = d["buckets"]
    todo = [p for p in papers if p not in done]
    print(f"  [parse] {len(done)} cached, {len(todo)} to parse, "
          f"{workers} worker(s)")
    if not todo:
        return done

    t0 = time.perf_counter()
    with open(cache, "a", encoding="utf-8") as fh, \
            installed_rules(eval_dir, types):
        with _mp.Pool(workers, initializer=sdm._pool_init,
                      initargs=(str(tex_dir), types)) as pool:
            for i, (pid, buckets, secs) in enumerate(
                    pool.imap_unordered(sdm._pool_parse, todo), 1):
                done[pid] = buckets
                fh.write(json.dumps({"paper_id": pid, "buckets": buckets}) + "\n")
                fh.flush()
                print(f"  [parse] {i}/{len(todo)}  {pid}  {secs:.0f}s  "
                      f"(elapsed {time.perf_counter()-t0:.0f}s)", flush=True)
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-dir", required=True)
    ap.add_argument("--gold-dir", required=True)
    ap.add_argument("--tex-dir", required=True)
    ap.add_argument("--scores", default=None,
                    help="default: <eval-dir>/heldout_scores.jsonl")
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--cover", type=float, default=0.7)
    ap.add_argument("--match-metric", default="containment")
    ap.add_argument("--workers", type=int, default=4,
                    help="4 of 8 cores leaves the machine usable")
    ap.add_argument("--cache", default=None,
                    help="default: <eval-dir>/heldout_buckets.jsonl")
    args = ap.parse_args()

    seq.set_match_metric(args.match_metric)
    eval_dir = Path(args.eval_dir).resolve()
    gold_dir = Path(args.gold_dir).resolve()
    tex_dir = Path(args.tex_dir).resolve()
    scores = Path(args.scores) if args.scores else eval_dir / "heldout_scores.jsonl"
    cache = Path(args.cache) if args.cache else eval_dir / "heldout_buckets.jsonl"

    types = list(FNAME_MAP.keys())
    gold = {t: load_gold_texts(gold_dir / FNAME_MAP[t]) for t in types}

    # The papers, and the counts to reproduce, both come from the run's own
    # output -- so the check cannot drift onto a different paper set.
    ref = {}
    papers = []
    for line in open(scores, encoding="utf-8"):
        d = json.loads(line)
        if d["paper_id"] not in ref:
            papers.append(d["paper_id"])
            ref[d["paper_id"]] = {}
        ref[d["paper_id"]][d["mode"]] = d
    print(f"papers: {len(papers)}  types: {len(types)}  "
          f"metric: {args.match_metric}  cache: {cache.name}")

    parsed = parse_incremental(papers, tex_dir, types, eval_dir, cache,
                               args.workers)

    # --- reproduce the scores, then dump the FPs the m3 pass rejected --------
    import match_modes as _mm
    rows, bad = [], []
    for pid in papers:
        buckets = parsed.get(pid, {t: [] for t in types})
        support = _all_gold(gold, pid, types)
        for mode in ("m1", "m3"):
            for t in types:
                m = metrics(buckets.get(t, []), gold[t].get(pid, []),
                            args.threshold, mode=mode, support_texts=support,
                            cover=args.cover)
                was = ref[pid][mode]["per_type"][t]
                for k in ("tp", "tp_recall", "fp", "fn"):
                    if m[k] != was[k]:
                        bad.append((pid, mode, t, k, was[k], m[k]))
        # Only m3 spans are dumped: m1's extra 2,410 rejections are nesting and
        # boundary artefacts m3 already forgives, and re-judging them would
        # re-measure the metric ladder rather than the content.
        for t in types:
            ext = buckets.get(t, [])
            if not ext:
                continue
            ok = _mm.classify_extractions(ext, gold[t].get(pid, []),
                                          args.threshold, mode="m3",
                                          support_texts=support,
                                          cover=args.cover)
            for i, (span, good) in enumerate(zip(ext, ok)):
                if not good:
                    rows.append({"fp_id": "", "type": t, "paper_id": pid,
                                 "ext_index": i, "snippet": span})

    if bad:
        print(f"\nFAIL: {len(bad)} count(s) differ from heldout_scores.jsonl")
        for b in bad[:20]:
            print("   pid=%s mode=%s type=%s %s: run=%s now=%s" % b)
        sys.exit(1)
    print("  [check] every per-paper per-type m1/m3 count reproduces exactly")

    for n, r in enumerate(rows):
        r["fp_id"] = f"fp{n:05d}"
    out = eval_dir / "heldout_fp_m3.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["fp_id", "type", "paper_id",
                                          "ext_index", "snippet"])
        w.writeheader()
        w.writerows(rows)
    n_m3 = sum(ref[p]["m3"]["fp"] for p in papers)
    print(f"\nwrote {out}  ({len(rows)} M3 FPs; scores say {n_m3})")
    assert len(rows) == n_m3, "FP dump does not match the recorded FP total"
    from collections import Counter
    for t, c in Counter(r["type"] for r in rows).most_common():
        print(f"  {t:14s} {c:5d}")


if __name__ == "__main__":
    main()
