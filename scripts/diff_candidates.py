"""Diff two candidates.jsonl files and show what changed after a filter
update (e.g. after Phase 2a populates citation data and Phase 2b is
re-run with the headline_only_no_citation + drop_same_author filters
firing for real).

Use case: compare candidates_pre_s2.jsonl (Phase 2b output BEFORE
Phase 2a ran) against candidates.jsonl (Phase 2b output AFTER) to
quantify how many trivial-by-citation and trivial-by-author rows
the filters caught.

Usage:
  python3 scripts/diff_candidates.py \\
      --before /path/to/run/candidates_pre_s2.jsonl \\
      --after  /path/to/run/candidates.jsonl \\
      --top    20

Output: summary stats + the new top-K cross-paper candidates with
their (cites_problem_paper, same_author) flags now populated.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def load(path: Path) -> list[dict]:
    out: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def pair_key(r: dict) -> tuple[str, str]:
    return (r.get("problem_id", "") or "", r.get("candidate_id", "") or "")


def diff(before_path: Path, after_path: Path, *, top: int = 20):
    before = load(before_path)
    after = load(after_path)

    print(f"=== Phase 2b output diff ===")
    print(f"  before: {len(before):>6} candidates  ({before_path.name})")
    print(f"  after:  {len(after):>6} candidates  ({after_path.name})")
    print(f"  delta:  {len(after) - len(before):>+6}  "
          f"({100*(len(after)-len(before))/max(1,len(before)):>+.1f}%)")

    before_keys = {pair_key(r) for r in before}
    after_keys = {pair_key(r) for r in after}
    dropped = before_keys - after_keys
    added = after_keys - before_keys
    print(f"\n  dropped (in before, not in after):  {len(dropped):>6}")
    print(f"  added   (in after, not in before):  {len(added):>6}")

    # Reason analysis on dropped rows
    print(f"\n=== Why rows were dropped ===")
    dropped_rows = [r for r in before if pair_key(r) in dropped]
    reason_counts = Counter()
    for r in dropped_rows:
        same_paper = r.get("problem_paper") == r.get("candidate_paper")
        if same_paper:
            reason_counts["same_paper"] += 1
            continue
        # Without "after" knowing why each row was dropped, we infer
        # by looking at AFTER's all-rows attributes. But the dropped
        # rows aren't there. So we just bucket by what's KNOWN from
        # the BEFORE row.
        py = r.get("problem_year")
        cy = r.get("candidate_year")
        if py and cy and py == cy:
            reason_counts["same_year_(possibly_temporal_violation)"] += 1
            continue
        reason_counts["unknown_(probably_cites_or_same_author)"] += 1
    for reason, n in reason_counts.most_common():
        print(f"  {reason:<45}  {n:>6}")

    # AFTER-only stats: cites + same_author distribution
    print(f"\n=== AFTER-run cites + same_author distribution ===")
    cites_counts = Counter()
    sa_counts = Counter()
    cross = Counter()
    for r in after:
        c = r.get("cites_problem_paper")
        s = r.get("same_author")
        cites_counts[c] += 1
        sa_counts[s] += 1
        cross[(c, s)] += 1
    print(f"  cites_problem_paper: True={cites_counts.get(True,0)}  "
          f"False={cites_counts.get(False,0)}  None={cites_counts.get(None,0)}")
    print(f"  same_author:         True={sa_counts.get(True,0)}  "
          f"False={sa_counts.get(False,0)}  None={sa_counts.get(None,0)}")
    print(f"\n  Cross-table (cites x same_author):")
    print(f"    {'cites:':<8} {'sameA:':<8} {'count':>6}")
    for (c, s), n in sorted(cross.items(), key=lambda x: -x[1]):
        print(f"    {str(c):<8} {str(s):<8} {n:>6}")

    # New top-K cross-paper (sorted by score desc), with cite/author flags
    print(f"\n=== AFTER-run top-{top} cross-paper candidates ===")
    after_xp = [r for r in after if r.get("problem_paper") != r.get("candidate_paper")]
    after_xp.sort(key=lambda r: -float(r.get("combined") or 0))
    topK = after_xp[:top]
    print(f"  {'#':>3} {'score':>6} {'cites':>5} {'sameA':>5} {'years':>5}  "
          f"{'O':<18} -> {'T':<18}")
    for i, r in enumerate(topK, 1):
        c = {True: "YES", False: "no", None: "?"}[r.get("cites_problem_paper")]
        s = {True: "YES", False: "no", None: "?"}[r.get("same_author")]
        ya = r.get("years_apart")
        ya_s = str(ya) if ya is not None and ya != "" else "?"
        print(f"  {i:>3} {float(r.get('combined') or 0):>6.3f} {c:>5} {s:>5} "
              f"{ya_s:>5}  {r.get('problem_paper',''):<18} -> "
              f"{r.get('candidate_paper',''):<18}")

    # Estimate novel candidates: cites=False AND same_author=False
    print(f"\n=== Novel-candidate estimate (cites=False AND same_author=False) ===")
    novel = [r for r in after_xp
             if r.get("cites_problem_paper") is False
             and r.get("same_author") is False]
    print(f"  novel cross-paper rows: {len(novel)} / {len(after_xp)} "
          f"({100*len(novel)/max(1,len(after_xp)):.1f}%)")
    novel.sort(key=lambda r: -float(r.get("combined") or 0))
    print(f"\n  top-{min(top, len(novel))} NOVEL cross-paper candidates:")
    print(f"  {'#':>3} {'score':>6}  {'O':<18} -> {'T':<18}")
    for i, r in enumerate(novel[:top], 1):
        print(f"  {i:>3} {float(r.get('combined') or 0):>6.3f}  "
              f"{r.get('problem_paper',''):<18} -> "
              f"{r.get('candidate_paper',''):<18}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--before", type=Path, required=True,
                    help="candidates.jsonl before the change")
    ap.add_argument("--after", type=Path, required=True,
                    help="candidates.jsonl after the change")
    ap.add_argument("--top", type=int, default=20,
                    help="How many top-K rows to show (default 20)")
    args = ap.parse_args()
    diff(args.before, args.after, top=args.top)


if __name__ == "__main__":
    main()
