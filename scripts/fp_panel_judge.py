#!/usr/bin/env python3
"""Run ONE open-weight judge over the held-out M3 false positives.

Four judges are run, one invocation each, because each needs the GPU to itself:

    qwen3-32b-awq  mistral-small-24b  gemma-3-27b-it  llama-3.3-70b

All four come from organisations other than the one that wrote the silver
corpus (Claude Opus), so no model is asked to review its own output -- which is
the whole reason the panel is open-weight rather than another Claude call.

The question put to each judge is `fp_judge.judge_batch`, called directly rather
than reimplemented, so the bytes are the ones the Anthropic path would send. It
is asked in m3 framing: these spans are not nested, relabelled or re-cut
versions of anything annotated, so "is this really a definition?" is not the
disagreement -- "did the reference miss this entirely?" is.

Failure modes this script refuses to hide:
  * A model that answers about item 3 when asked about item 4 drifts silently.
    Any index the model does not answer is recorded MISSING, never folded into
    a verdict, and `--repair-missing` re-asks exactly those rows one at a time,
    flagging the row as repaired so the two prompt shapes stay distinguishable.
  * Sampling is pinned in the shim (temperature 0, top_p 1, top_k -1, seed 0,
    enable_thinking false). Qwen3's own generation_config would otherwise
    sample a fresh verdict per run, and a <think> block would eat the token
    budget before the verdict.

Resumable: rows already in --out are kept and not re-asked, so a server that
dies at row 1,500 does not cost the other 1,500.

Usage:
    export LLM_LOCAL_BASE_URL=http://salmon-02:8000/v1
    python scripts/fp_panel_judge.py \
        --fps src/LLMVersion/heldout_eval_selected146/heldout_fp_m3.csv \
        --model qwen3-32b-awq --repair-missing
"""

import argparse
import csv
import os
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import fp_judge
from replay_fp_judge_local import LocalClient

FIELDS = ["fp_id", "type", "paper_id", "model", "verdict", "reason",
          "batch_size", "repaired"]


def _load_done(path):
    if not path.exists():
        return {}
    return {r["fp_id"]: r for r in csv.DictReader(open(path, encoding="utf-8"))}


def _judge_chunks(client, model, chunks, match_mode, workers, label):
    """Ask every chunk, in parallel; return {fp_id: (verdict, reason)}.

    vLLM serves concurrent requests off one weight copy, so fanning out costs
    nothing but sockets. Each request is independently pinned, so the answers
    do not depend on how the server happened to batch them.
    """
    out = {}
    lock = threading.Lock()
    done = [0]
    t0 = time.time()

    def run(chunk):
        stype = chunk[0]["type"]
        snippets = [r["snippet"] for r in chunk]
        try:
            by_index, _ = fp_judge.judge_batch(client, model, stype, snippets,
                                               match_mode=match_mode)
        except Exception as e:
            print(f"  [warn] batch failed ({stype}, n={len(chunk)}): {e}",
                  flush=True)
            by_index = {}
        got = {}
        for k, r in enumerate(chunk):
            obj = by_index.get(k) or {}
            got[r["fp_id"]] = (obj.get("verdict", "MISSING"),
                               obj.get("reason", ""))
        with lock:
            out.update(got)
            done[0] += len(chunk)
            if done[0] % 100 < len(chunk):
                print(f"  [{label}] {done[0]} judged ({time.time()-t0:.0f}s)",
                      flush=True)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(run, chunks))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", required=True, help="heldout_fp_m3.csv")
    ap.add_argument("--model", required=True,
                    help="served-model-name on the vLLM endpoint")
    ap.add_argument("--base-url", default=os.environ.get("LLM_LOCAL_BASE_URL"))
    ap.add_argument("--match-mode", default="m3", choices=["m1", "m3"])
    ap.add_argument("--batch-size", type=int, default=5,
                    help="items per prompt; smaller = less index drift")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--repair-missing", action="store_true",
                    help="re-ask unanswered indices one at a time")
    ap.add_argument("--limit", type=int, default=0, help="smoke test")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not args.base_url:
        sys.exit("set --base-url or $LLM_LOCAL_BASE_URL")

    src = Path(args.fps).resolve()
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    if args.limit:
        rows = rows[:args.limit]
    out_path = (Path(args.out) if args.out else
                src.parent / "panel" / f"fp_panel_{args.model}.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    done = _load_done(out_path)
    todo = [r for r in rows if r["fp_id"] not in done]
    print(f"{args.model}: {len(rows)} FPs, {len(done)} already judged, "
          f"{len(todo)} to go  (batch={args.batch_size}, "
          f"conc={args.concurrency}, mode={args.match_mode})")

    client = LocalClient(args.base_url, args.model, args.timeout, args.retries)

    # The prompt is per type, so batches never mix types. Order inside a type
    # is the dump's order, which is paper order -- stable across models.
    by_type = defaultdict(list)
    for r in todo:
        by_type[r["type"]].append(r)
    chunks = [g[i:i + args.batch_size]
              for t, g in sorted(by_type.items())
              for i in range(0, len(g), args.batch_size)]

    got = _judge_chunks(client, args.model, chunks, args.match_mode,
                        args.concurrency, args.model) if chunks else {}

    for r in todo:
        v, why = got.get(r["fp_id"], ("MISSING", ""))
        done[r["fp_id"]] = {"fp_id": r["fp_id"], "type": r["type"],
                            "paper_id": r["paper_id"], "model": args.model,
                            "verdict": v, "reason": why,
                            "batch_size": args.batch_size, "repaired": 0}

    if args.repair_missing:
        miss = [r for r in rows if done[r["fp_id"]]["verdict"] == "MISSING"]
        if miss:
            print(f"  [repair] {len(miss)} MISSING -> re-asking singly")
            chunks = [[r] for r in miss]
            fixed = _judge_chunks(client, args.model, chunks, args.match_mode,
                                  args.concurrency, args.model + "/repair")
            for r in miss:
                v, why = fixed.get(r["fp_id"], ("MISSING", ""))
                if v != "MISSING":
                    done[r["fp_id"]].update(verdict=v, reason=why,
                                            batch_size=1, repaired=1)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows([done[r["fp_id"]] for r in rows])

    c = Counter(done[r["fp_id"]]["verdict"] for r in rows)
    n = len(rows)
    print(f"\nwrote {out_path}")
    for v, k in c.most_common():
        print(f"  {v:<16}{k:>6}  {k/n:6.1%}")
    if c["MISSING"]:
        print(f"  MISSING is not a verdict -- {c['MISSING']} rows carry no "
              "vote and are excluded from this judge's consensus contribution.")


if __name__ == "__main__":
    main()
