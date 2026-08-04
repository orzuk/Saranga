"""T-OPEN — reconcile an incoming Erdős-problems export against our committed CSV.

Why this exists
---------------
`erdos_problems.csv` in this dir is 1217 problems derived from
github.com/teorth/erdosproblems (the repo behind erdosproblems.com) plus a
Wayback scrape. When someone hands us "the list of Erdős problems" we need to
answer one question before importing anything: *is this the same data we
already have?* If yes, importing is a no-op and we go straight to the coverage
run; if no, we need to know exactly what moved.

Two modes
---------
    # Profile what WE have (no second file needed)
    python discovery_suite/open_problems/erdos_reconcile.py

    # Diff an incoming export against ours
    python discovery_suite/open_problems/erdos_reconcile.py \
        --theirs ~/Downloads/erdos_problems_or.csv \
        --out discovery_suite/open_problems/runs/erdos_reconcile.md

Deliberately stdlib-only and self-contained (no `shared.corpus`, no repo path
juggling) so it can also be run on Or's box, where the repo env may not exist.

Matching is on the problem `number`, which is the stable erdosproblems.com id.
Statements are compared after a light normalization (case, whitespace, LaTeX
delimiters) because scrapes differ in trivial ways; anything that survives that
is reported as a real content difference with a similarity ratio.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
DEFAULT_OURS = _HERE / "erdos_problems.csv"

# Mirrors erdos_coverage.RESOLVED_STATUSES / OPEN_STATUSES / _norm_status so the
# two tools agree on what "resolved" means. Kept as literals (not imported) to
# stay dependency-free — see erdos_coverage.py for the rationale on the Lean
# spellings ("proved (lean)"), which are resolved, not open.
RESOLVED_STATUSES = {
    "proved", "disproved", "solved",
    "proved_lean", "disproved_lean", "solved_lean",
    "proven", "resolved",
}
OPEN_STATUSES = {"open"}
_LEAN = re.compile(r"\s*\((?:lean)\)\s*$")


def norm_status(raw: str) -> str:
    s = (raw or "").strip().lower()
    return _LEAN.sub("_lean", s) if _LEAN.search(s) else s

_WS = re.compile(r"\s+")
_TRIVIAL = re.compile(r"[$\\{}]")


def norm_stmt(s: str) -> str:
    """Collapse the differences two scrapes of the same statement will always
    have (case, whitespace, LaTeX delimiters) without touching real content."""
    return _WS.sub(" ", _TRIVIAL.sub("", (s or "").lower())).strip()


def _denul(fh):
    """Drop NUL bytes. Our committed CSV carries some (a scrape artefact) and
    `csv` refuses to read a line containing one."""
    for line in fh:
        yield line.replace("\x00", "")


def load_csv(path: Path) -> tuple[dict[str, dict], list[str]]:
    """Read an Erdős CSV into {number: row}. Tolerant of column-name variation
    (same aliases erdos_coverage.load_erdos accepts). Returns (rows, header)."""
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(_denul(fh))
        header = list(reader.fieldnames or [])
        lower = {c.lower().strip(): c for c in header}

        def col(*names: str) -> Optional[str]:
            for n in names:
                if n in lower:
                    return lower[n]
            return None

        c_num = col("number", "id", "problem", "problem_number")
        c_status = col("yaml_status", "status")
        c_stmt = col("statement", "problem_statement", "text")
        if c_stmt is None:
            sys.exit(f"[reconcile] {path} has no statement column (saw: {header})")

        rows: dict[str, dict] = {}
        dups: list[str] = []
        for i, r in enumerate(reader):
            num = (r.get(c_num) or "").strip() if c_num else str(i)
            if num in rows:
                dups.append(num)
            rows[num] = {
                "number": num,
                "status": norm_status(r.get(c_status)) if c_status else "",
                "statement": (r.get(c_stmt) or "").strip(),
                "raw": r,
            }
    if dups:
        print(f"[reconcile] WARNING {path.name}: {len(dups)} duplicate numbers "
              f"(kept last): {dups[:10]}{'...' if len(dups) > 10 else ''}")
    return rows, header


def profile(rows: dict[str, dict], header: list[str], label: str,
            lines: list[str]) -> None:
    """Describe one CSV: size, status split, id coverage, statement health."""
    statuses = Counter(r["status"] or "(blank)" for r in rows.values())
    resolved = sum(1 for r in rows.values() if r["status"] in RESOLVED_STATUSES)
    open_ = sum(1 for r in rows.values() if r["status"] in OPEN_STATUSES)
    other = len(rows) - resolved - open_
    empty = sum(1 for r in rows.values() if len(r["statement"]) < 10)
    nums = sorted(int(n) for n in rows if n.isdigit())
    gaps = []
    if nums:
        present = set(nums)
        gaps = [n for n in range(nums[0], nums[-1] + 1) if n not in present]

    lines += [
        f"### {label}",
        "",
        f"- rows: **{len(rows)}**  (resolved {resolved} / open {open_} / "
        f"other-status {other})",
        f"- columns: `{', '.join(header)}`",
        f"- number range: {nums[0] if nums else '-'}–{nums[-1] if nums else '-'} "
        f"({len(gaps)} ids missing inside the range)",
        f"- statements shorter than 10 chars: {empty}",
        f"- status values: " + ", ".join(f"`{k}`={v}" for k, v in statuses.most_common()),
        "",
    ]
    if gaps:
        head = ", ".join(str(g) for g in gaps[:25])
        lines.append(f"  missing ids: {head}{' …' if len(gaps) > 25 else ''}")
        lines.append("")


def diff(ours: dict[str, dict], theirs: dict[str, dict],
         lines: list[str], show: int) -> bool:
    """Report ids and statements that differ. Returns True if the two files are
    equivalent (same ids, same normalized statements)."""
    only_ours = sorted(set(ours) - set(theirs), key=lambda n: (not n.isdigit(), n))
    only_theirs = sorted(set(theirs) - set(ours), key=lambda n: (not n.isdigit(), n))
    shared = set(ours) & set(theirs)

    stmt_diff, status_diff = [], []
    for n in shared:
        a, b = ours[n], theirs[n]
        if norm_stmt(a["statement"]) != norm_stmt(b["statement"]):
            ratio = difflib.SequenceMatcher(
                None, norm_stmt(a["statement"]), norm_stmt(b["statement"])).ratio()
            stmt_diff.append((ratio, n, a["statement"], b["statement"]))
        if a["status"] != b["status"]:
            status_diff.append((n, a["status"], b["status"]))
    stmt_diff.sort()  # lowest similarity = most different, first

    lines += [
        "## Diff",
        "",
        f"- shared ids: **{len(shared)}**",
        f"- only in OURS: **{len(only_ours)}**",
        f"- only in THEIRS: **{len(only_theirs)}**",
        f"- statement differs (after normalization): **{len(stmt_diff)}**",
        f"- status differs: **{len(status_diff)}**",
        "",
    ]

    if only_theirs:
        lines += ["**New problems in their export** (would need importing):", "",
                  "  " + ", ".join(only_theirs[:60])
                  + (" …" if len(only_theirs) > 60 else ""), ""]
    if only_ours:
        lines += ["**Present in ours, absent from theirs:**", "",
                  "  " + ", ".join(only_ours[:60])
                  + (" …" if len(only_ours) > 60 else ""), ""]
    if status_diff:
        lines += ["**Status changes** (ours → theirs) — these matter most: a problem",
                  "that flipped open→proved changes the coverage denominator.", "",
                  "| # | ours | theirs |", "|---|---|---|"]
        for n, a, b in status_diff[:show]:
            lines.append(f"| {n} | {a or '(blank)'} | {b or '(blank)'} |")
        if len(status_diff) > show:
            lines.append(f"| … | +{len(status_diff) - show} more | |")
        lines.append("")
    if stmt_diff:
        lines += [f"**Most-changed statements** (lowest similarity first, "
                  f"top {min(show, len(stmt_diff))}):", ""]
        for ratio, n, a, b in stmt_diff[:show]:
            lines += [f"- **#{n}** (similarity {ratio:.2f})",
                      f"  - ours:   {a[:220]}",
                      f"  - theirs: {b[:220]}"]
        lines.append("")

    return not (only_ours or only_theirs or stmt_diff or status_diff)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ours", type=Path, default=DEFAULT_OURS,
                    help="our committed Erdős CSV (default: erdos_problems.csv)")
    ap.add_argument("--theirs", type=Path,
                    help="incoming export to compare against ours; omit to just "
                         "profile ours")
    ap.add_argument("--out", type=Path,
                    help="write the markdown report here (also printed to stdout)")
    ap.add_argument("--show", type=int, default=20,
                    help="max rows per difference table")
    args = ap.parse_args()

    lines: list[str] = ["# Erdős CSV reconciliation", ""]

    ours, ours_hdr = load_csv(args.ours)
    profile(ours, ours_hdr, f"OURS — `{args.ours.name}`", lines)

    identical = None
    if args.theirs:
        theirs, theirs_hdr = load_csv(args.theirs)
        profile(theirs, theirs_hdr, f"THEIRS — `{args.theirs.name}`", lines)
        identical = diff(ours, theirs, lines, args.show)
        lines += ["## Verdict", ""]
        lines.append(
            "**Same data — importing is a no-op.** Proceed straight to "
            "`erdos_coverage.py` on the committed CSV."
            if identical else
            "**The exports differ.** Review the tables above before importing; "
            "status flips and new ids change the coverage denominator.")
        lines.append("")
    else:
        lines += ["## Verdict", "",
                  "Profile only — pass `--theirs <csv>` to diff an incoming export.",
                  ""]

    report = "\n".join(lines)
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"[reconcile] wrote {args.out}")

    if identical is False:
        sys.exit(1)  # non-zero so a wrapper script can gate on "needs review"


if __name__ == "__main__":
    main()
