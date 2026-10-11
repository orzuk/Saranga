#!/usr/bin/env python3
"""Render v2 pages in headless Chrome: time to first layout, console errors.

Usage:
    python3 src/graph_view/check_pages.py <page.html|dir ...> [-j 3]
        [--hash level=full] [--shots DIR] [--csv out.csv]

Each page logs `V2_FIRST_LAYOUT ms=... layout=... level=... nodes=... edges=...`
when its first layout is done (ms = performance.now(), from navigation
start). A page with no such line, or with an uncaught error or a failed
layout in its console, is reported as failing. With --hash selftest=1 the
page also runs through every level, focus mode and toggle once and must log
`V2_SELFTEST ok`. Runs Windows Chrome from WSL.
"""
import argparse
import csv
import queue
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CHROME = "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
_V2 = re.compile(r"V2_FIRST_LAYOUT ([^\"]*)")
_BAD = re.compile(r"Uncaught|layout failed|Could not load|is not defined|Cannot read|TypeError|ReferenceError|SyntaxError")


def winpath(p):
    return subprocess.run(["wslpath", "-w", str(p)], capture_output=True, text=True).stdout.strip()


def wslpath_u(p):
    return subprocess.run(["wslpath", "-u", p], capture_output=True, text=True).stdout.strip()


def check(page, profile, hash_="", shot=None, wait_ms=20000):
    """Load one page; return a dict with timings and console problems."""
    url = "file:///" + winpath(Path(page).resolve()).replace("\\", "/") + ("#" + hash_ if hash_ else "")
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
           "--user-data-dir=" + profile, "--enable-logging=stderr", "--v=0",
           "--window-size=1600,1000",
           # a self-test needs the page kept alive; timings need real time
           ("--virtual-time-budget=%d" % (3 * wait_ms)) if "selftest=1" in hash_ else "--timeout=%d" % wait_ms,
           "--screenshot=" + (winpath(shot) if shot else profile + "\\shot.png"), url]
    try:
        out = subprocess.run(["nice"] + cmd, capture_output=True, text=True, timeout=300).stderr
    except subprocess.TimeoutExpired:
        out = ""
    row = {"page": Path(page).name, "ok": False, "errors": ""}
    msgs = re.findall(r'CONSOLE[^\]]*\] "(.*?)", source', out)
    bad = [m for m in msgs if _BAD.search(m)]
    m = next((_V2.search(x) for x in msgs if _V2.search(x)), None)
    if m:
        for kv in m.group(1).split():
            k, _, v = kv.partition("=")
            row[k] = v
    st = [x for x in msgs if x.startswith("V2_SELFTEST")]
    if "selftest=1" in hash_:
        row["selftest"] = st[0] if st else "V2_SELFTEST missing"
        if not st or "ok" not in st[0]:
            bad.append(row["selftest"])
    row["errors"] = " | ".join(bad)[:500]
    row["ok"] = bool(m) and not bad
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pages", nargs="+")
    ap.add_argument("-j", "--jobs", type=int, default=3)
    ap.add_argument("--hash", default="", help="URL hash state, e.g. level=full")
    ap.add_argument("--shots", default=None, help="folder for screenshots (<id>.png)")
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    pages = []
    for p in args.pages:
        pp = Path(p)
        pages += sorted(pp.glob("*_new.html")) if pp.is_dir() else [pp]
    # Chrome profiles on the Windows side (one per worker, reused: warm cache).
    # A profile on the WSL file system adds ~4 s to every page load.
    wtemp = subprocess.run(["cmd.exe", "/c", "echo %TEMP%"], capture_output=True,
                           text=True, cwd="/mnt/c").stdout.strip()
    tmp = Path(tempfile.mkdtemp(prefix="v2check_", dir=wslpath_u(wtemp)))
    profiles = [winpath(tmp) + "\\prof%d" % i for i in range(args.jobs)]
    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)

    free = queue.Queue()                # a profile is used by one Chrome at a time
    for p in profiles:
        free.put(p)

    def work(page):
        shot = shots / (Path(page).stem.replace("_new", "") + ".png") if shots else None
        prof = free.get()
        try:
            return check(page, prof, args.hash, shot)
        finally:
            free.put(prof)

    with ThreadPoolExecutor(args.jobs) as ex:
        rows = []
        for r in ex.map(work, pages):
            rows.append(r)
            print("%-28s %s ms=%-6s layout=%-6s level=%-8s nodes=%-4s %s" % (
                r["page"], "ok  " if r["ok"] else "FAIL", r.get("ms", "-"), r.get("layout", "-"),
                r.get("level", "-"), r.get("nodes", "-"), r.get("note", "") + r["errors"]), flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    if args.csv:
        keys = ["page", "ok", "ms", "start", "layout", "level", "nodes", "edges", "note", "errors"]
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, keys, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    ms = sorted(float(r["ms"]) for r in rows if r.get("ms"))
    n_ok = sum(r["ok"] for r in rows)
    if ms:
        print("pages ok %d/%d; first layout ms: median %.0f, p95 %.0f, max %.0f; under 3 s: %d/%d"
              % (n_ok, len(rows), ms[(len(ms) - 1) // 2], ms[max(0, -(-95 * len(ms) // 100) - 1)], ms[-1],
                 sum(x < 3000 for x in ms), len(rows)))
    sys.exit(0 if n_ok == len(rows) else 1)


if __name__ == "__main__":
    main()
