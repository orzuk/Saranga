"""Progress reporting for long, sharded, parallel stages.

Every stage of the embedding pipeline must be answerable at any moment: how many
items are there, how many are done, how fast, how long left. That is what
``Heartbeat`` provides — a stderr line plus a machine-readable status file that
``open_problems/watch_open.py`` aggregates into one live table.

ONE STATUS FILE PER TASK, NEVER A SHARED ONE. The whole-arXiv download jobs died
from many array tasks appending to a single status log on NFS (lock contention +
partial writes). Here each task owns ``<status_dir>/<stage>.<task_id>.json`` and
writes it atomically (tmp + os.replace), so there is no cross-task coordination
at all and a crashed task leaves its last good state behind.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional


def task_id() -> str:
    """Stable identity for this process: SLURM array task > job > pid."""
    arr = os.environ.get("SLURM_ARRAY_TASK_ID")
    job = os.environ.get("SLURM_ARRAY_JOB_ID") or os.environ.get("SLURM_JOB_ID")
    if arr and job:
        return f"{job}_{arr}"
    if arr:
        return f"array{arr}"
    if job:
        return f"job{job}"
    return f"pid{os.getpid()}"


def fmt_secs(s: float) -> str:
    s = int(max(0, s))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def banner(stage: str, out=sys.stderr, **totals) -> None:
    """Announce a stage's planned totals BEFORE it starts.

    Knowing "1,589,327 nodes to embed" up front is what makes the later
    "43,000 done" line meaningful, so every stage calls this first.
    """
    body = "  ".join(f"{k}={fmt_int(v)}" for k, v in totals.items())
    print(f"[{stage}] START  {body}", file=out, flush=True)


class Heartbeat:
    """Count items, print/persist progress on an item- or time-based cadence.

    ``total`` may be None (unknown) — then no percentage or ETA is shown, but
    rate still is. Cheap enough to call per item: the common path is one integer
    increment plus two comparisons.
    """

    def __init__(
        self,
        stage: str,
        total: Optional[int] = None,
        *,
        status_dir: Optional[Path | str] = None,
        every: int = 2000,
        every_secs: float = 30.0,
        unit: str = "items",
        out=sys.stderr,
        extra: Optional[dict] = None,
    ) -> None:
        self.stage = stage
        self.total = total
        self.every = max(1, every)
        self.every_secs = every_secs
        self.unit = unit
        self.out = out
        self.extra = dict(extra or {})
        self.done = 0
        self.t0 = time.time()
        self._last_emit_n = 0
        self._last_emit_t = self.t0
        self.tid = task_id()
        self.status_path: Optional[Path] = None
        if status_dir:
            d = Path(status_dir)
            d.mkdir(parents=True, exist_ok=True)
            self.status_path = d / f"{stage}.{self.tid}.json"
        self._write_status("running")

    # ── reporting ────────────────────────────────────────────────────────────

    @property
    def rate(self) -> float:
        dt = time.time() - self.t0
        return self.done / dt if dt > 0 else 0.0

    @property
    def eta_s(self) -> Optional[float]:
        if not self.total or self.done <= 0:
            return None
        r = self.rate
        return (self.total - self.done) / r if r > 0 else None

    def _line(self) -> str:
        parts = [f"[{self.stage}] {fmt_int(self.done)}"]
        if self.total:
            pct = 100.0 * self.done / self.total
            parts[0] += f"/{fmt_int(self.total)} ({pct:.1f}%)"
        parts.append(f"{self.rate:,.0f} {self.unit}/s")
        eta = self.eta_s
        if eta is not None:
            parts.append(f"eta {fmt_secs(eta)}")
        parts.append(f"elapsed {fmt_secs(time.time() - self.t0)}")
        if self.extra:
            parts.append(" ".join(f"{k}={v}" for k, v in self.extra.items()))
        return "  ".join(parts)

    def _write_status(self, state: str) -> None:
        if self.status_path is None:
            return
        payload = {
            "stage": self.stage,
            "task": self.tid,
            "state": state,
            "done": self.done,
            "total": self.total,
            "unit": self.unit,
            "rate": round(self.rate, 3),
            "eta_s": (round(self.eta_s) if self.eta_s is not None else None),
            "elapsed_s": round(time.time() - self.t0, 1),
            "ts": time.time(),
            **self.extra,
        }
        tmp = self.status_path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            os.replace(tmp, self.status_path)  # atomic; readers never see a partial file
        except OSError:
            pass  # progress reporting must never take the job down

    def emit(self) -> None:
        print(self._line(), file=self.out, flush=True)
        self._write_status("running")
        self._last_emit_n = self.done
        self._last_emit_t = time.time()

    def tick(self, n: int = 1, **extra) -> None:
        self.done += n
        if extra:
            self.extra.update(extra)
        if (self.done - self._last_emit_n) >= self.every or \
           (time.time() - self._last_emit_t) >= self.every_secs:
            self.emit()

    def close(self, state: str = "done", **extra) -> None:
        if extra:
            self.extra.update(extra)
        print(f"[{self.stage}] {state.upper()}  {fmt_int(self.done)} {self.unit} "
              f"in {fmt_secs(time.time() - self.t0)} ({self.rate:,.0f}/s)",
              file=self.out, flush=True)
        self._write_status(state)

    def __enter__(self) -> "Heartbeat":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close("failed" if exc_type else "done")
