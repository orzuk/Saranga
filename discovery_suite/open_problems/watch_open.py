"""Live progress across every stage and every array task.

Each task writes its own ``<stage>.<task>.json`` (see embed/progress.py — never a
shared log, which is what killed the download jobs on NFS). This reads all of
them and prints one table: what stage is running, how many shards are done, how
many items of how many, the aggregate rate and an ETA.

    # one-shot
    python discovery_suite/open_problems/watch_open.py $STORE/status $VECS

    # live
    python discovery_suite/open_problems/watch_open.py $RUN_ROOT --watch 15

Directories are searched recursively, so pointing it at the run root picks up the
text-store, encode, dense and rerank stages together.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from embed.progress import fmt_int, fmt_secs  # noqa: E402

#: A task that hasn't rewritten its status in this long is presumed dead — a
#: SLURM task can vanish (OOM, wall clock, node failure) without ever writing a
#: terminal state, and a stage sitting at 60% forever must not look healthy.
STALE_S = 300.0


def collect(dirs) -> list[dict]:
    out = []
    for d in dirs:
        p = Path(d)
        if not p.exists():
            continue
        for f in p.rglob("*.json"):
            if f.name.endswith(".tmp"):
                continue
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue  # mid-write or unrelated json; skip
            if "stage" in rec and "done" in rec:
                rec["_path"] = str(f)
                out.append(rec)
    return out


def group_stage(name: str) -> str:
    """'encode.s37' -> 'encode', so per-shard tasks roll up into one row."""
    return name.split(".s")[0] if ".s" in name else name


def summarize(records, *, stale_s: float = STALE_S) -> str:
    now = time.time()
    by = defaultdict(list)
    for r in records:
        by[group_stage(r.get("stage", "?"))].append(r)

    lines = [f"{'stage':<14} {'tasks':>7} {'done':>14} {'total':>14} "
             f"{'rate/s':>9} {'eta':>9}  state"]
    lines.append("-" * 96)
    for stage in sorted(by):
        recs = by[stage]
        done = sum(int(r.get("done") or 0) for r in recs)
        totals = [int(r["total"]) for r in recs if r.get("total")]
        total = sum(totals) if len(totals) == len(recs) else None
        running = [r for r in recs if r.get("state") == "running"]
        live = [r for r in running if now - float(r.get("ts") or 0) <= stale_s]
        stale = len(running) - len(live)
        finished = sum(1 for r in recs if r.get("state") == "done")
        failed = sum(1 for r in recs if r.get("state") == "failed")
        rate = sum(float(r.get("rate") or 0) for r in live)
        eta = ((total - done) / rate) if (total and rate > 0) else None
        state = f"{finished} done"
        if live:
            state += f", {len(live)} running"
        if stale:
            state += f", {stale} STALE(>{int(stale_s)}s)"
        if failed:
            state += f", {failed} FAILED"
        pct = f" ({100.0*done/total:.1f}%)" if total else ""
        lines.append(
            f"{stage:<14} {len(recs):>7} {fmt_int(done):>14} "
            f"{(fmt_int(total) if total else '?'):>14} {rate:>9,.0f} "
            f"{(fmt_secs(eta) if eta is not None else '?'):>9}  {state}{pct}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dirs", nargs="+",
                    help="status dirs or run roots (searched recursively)")
    ap.add_argument("--watch", type=float, default=0.0,
                    help="refresh every N seconds (0 = print once)")
    ap.add_argument("--stale", type=float, default=STALE_S)
    args = ap.parse_args()

    while True:
        recs = collect(args.dirs)
        header = time.strftime("%H:%M:%S")
        body = (summarize(recs, stale_s=args.stale) if recs
                else "no status files found yet (stages write them once they start)")
        if args.watch:
            print("\033[2J\033[H", end="")  # clear, home
        print(f"[{header}] {len(recs)} task status file(s)\n{body}", flush=True)
        if not args.watch:
            return
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
