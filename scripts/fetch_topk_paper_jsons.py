"""Pre-fetch the full extracted paper JSONs for the top-K cross-paper
candidates in a candidates_ranked.csv, so post-Phase-2a hand-audit
doesn't need a fresh ssh round-trip per paper.

Workflow:
  1. Scan candidates_ranked.csv (locally pulled from cluster).
  2. Take the top-K cross-paper rows (or filter by score / filters).
  3. Identify unique paper IDs (problem_paper + candidate_paper).
  4. Diff against the local cache dir.
  5. For missing papers, locate them on cluster (papers live at
     <cluster_base>/<category>/json/<arxiv_id>v*_manual.json) and
     stream them down via ssh-cat in a single batched query.

Usage:
  python3 scripts/fetch_topk_paper_jsons.py \\
      --csv  /mnt/g/.../candidates_ranked.csv \\
      --top  50 \\
      --local-dir /mnt/g/.../v2_paper_jsons \\
      --cluster-host huji-work \\
      --cluster-base /sci/labs/orzuk/orzuk/projects/Authomathics/arxiv/parsed_multi_category_20

If --cluster-host or --cluster-base aren't given, prints the list of
missing arxiv IDs and the cluster-side glob pattern; you can fetch
manually via ssh huji-work 'cat ...' >local.json.

Idempotent: re-runs skip papers already in the local cache.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def safe_arxiv_for_filename(arxiv_id: str) -> str:
    """Old-style IDs have a slash (e.g. math/9410211); replace with __
    for safe local filenames."""
    return arxiv_id.replace("/", "__")


def load_top_k(csv_path: Path, k: int, min_score: float = 0.0,
               include_same_paper: bool = False,
               only_cross_author: bool = False,
               only_non_citing: bool = False) -> list[dict]:
    """Top-K candidate rows (sorted by score desc, optional filters)."""
    rows = []
    with csv_path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not include_same_paper and r.get("problem_paper") == r.get("candidate_paper"):
                continue
            try:
                if float(r.get("combined", 0)) < min_score:
                    continue
            except ValueError:
                continue
            if only_cross_author:
                sa = r.get("same_author", "")
                if sa not in ("False", "false", "no", "0"):
                    continue
            if only_non_citing:
                c = r.get("cites_problem_paper", "")
                if c not in ("False", "false", "no", "0"):
                    continue
            rows.append(r)
    return rows[:k]


def collect_paper_ids(rows: list[dict]) -> set[str]:
    out: set[str] = set()
    for r in rows:
        for k in ("problem_paper", "candidate_paper"):
            pid = (r.get(k) or "").strip()
            if pid:
                out.add(pid)
    return out


def local_cache_status(papers: set[str], local_dir: Path) -> tuple[set[str], set[str]]:
    """Return (present, missing) based on existence of .json files."""
    local_dir.mkdir(parents=True, exist_ok=True)
    have = set()
    for p in papers:
        fname = safe_arxiv_for_filename(p) + ".json"
        if (local_dir / fname).exists():
            have.add(p)
    return have, papers - have


def cluster_find_paths(arxiv_ids: list[str], cluster_host: str,
                       cluster_base: str) -> dict[str, str]:
    """For each arxiv_id, locate its JSON on cluster via shell glob.

    Cluster layout: <base>/<category>/json/<arxiv_id>v*_manual.json
    Returns {arxiv_id: cluster_path} for found papers.
    """
    if not arxiv_ids:
        return {}
    # Build a shell snippet that prints "<arxiv_id>\t<path>" per found paper.
    # Use a single ssh call rather than one per paper.
    script_lines = []
    for aid in arxiv_ids:
        # arxiv_id may contain slash (old-style); be careful in glob
        safe = aid.replace("'", "'\\''")
        script_lines.append(
            f"hit=$(ls {cluster_base}/*/json/{safe}v*_manual.json 2>/dev/null | head -1); "
            f"[ -n \"$hit\" ] && echo '{safe}'$'\\t'\"$hit\"")
    cmd = "; ".join(script_lines)
    print(f"[fetch] querying cluster for {len(arxiv_ids)} paper paths "
          f"via 1 ssh call...", file=sys.stderr)
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=30", cluster_host, cmd],
            capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print("[fetch] ssh timed out; cluster may be unreachable", file=sys.stderr)
        return {}
    if result.returncode != 0:
        print(f"[fetch] ssh failed (rc={result.returncode}): "
              f"{result.stderr[:300]}", file=sys.stderr)
        return {}
    out: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        aid, path = line.split("\t", 1)
        out[aid.strip()] = path.strip()
    return out


def cluster_fetch_paper(cluster_host: str, cluster_path: str,
                        local_path: Path) -> bool:
    """Stream one paper via ssh cat. Returns True on success."""
    safe = cluster_path.replace("'", "'\\''")
    cmd = ["ssh", "-o", "ConnectTimeout=30", cluster_host, f"cat '{safe}'"]
    try:
        with local_path.open("wb") as fout:
            r = subprocess.run(cmd, stdout=fout, stderr=subprocess.PIPE, timeout=60)
        if r.returncode != 0:
            print(f"[fetch] ssh cat failed for {cluster_path}: "
                  f"{r.stderr.decode('utf-8', errors='replace')[:200]}",
                  file=sys.stderr)
            if local_path.exists():
                local_path.unlink()
            return False
        # Sanity: file should be non-empty and parse as JSON
        if local_path.stat().st_size == 0:
            local_path.unlink()
            return False
        try:
            json.loads(local_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            local_path.unlink()
            return False
        return True
    except subprocess.TimeoutExpired:
        if local_path.exists():
            local_path.unlink()
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, required=True,
                    help="candidates_ranked.csv to scan")
    ap.add_argument("--top", type=int, default=50,
                    help="How many top-K cross-paper rows to consider (default 50)")
    ap.add_argument("--min-score", type=float, default=0.0,
                    help="Drop rows with combined < this (default 0)")
    ap.add_argument("--only-cross-author", action="store_true",
                    help="Skip rows where same_author is True or unknown")
    ap.add_argument("--only-non-citing", action="store_true",
                    help="Skip rows where cites_problem_paper is True or unknown")
    ap.add_argument("--local-dir", type=Path, required=True,
                    help="Local cache dir for paper JSONs (created if missing)")
    ap.add_argument("--cluster-host", default=None,
                    help="SSH alias for cluster (e.g. huji-work). If omitted, "
                         "prints missing IDs and exits (no fetching).")
    ap.add_argument("--cluster-base", default=None,
                    help="Cluster path to parsed_multi_category_20 root")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be fetched but don't actually fetch")
    args = ap.parse_args()

    rows = load_top_k(args.csv, args.top, min_score=args.min_score,
                       only_cross_author=args.only_cross_author,
                       only_non_citing=args.only_non_citing)
    print(f"[fetch] loaded {len(rows)} candidate rows from {args.csv.name}",
          file=sys.stderr)
    papers = collect_paper_ids(rows)
    print(f"[fetch] {len(papers)} unique paper IDs across the top-K",
          file=sys.stderr)

    have, missing = local_cache_status(papers, args.local_dir)
    print(f"[fetch] local cache: have={len(have)}, missing={len(missing)}",
          file=sys.stderr)

    if not missing:
        print("[fetch] all papers already cached. nothing to do.", file=sys.stderr)
        return

    missing_list = sorted(missing)
    if args.cluster_host is None or args.cluster_base is None:
        print(f"\nMISSING ({len(missing_list)} papers):")
        for p in missing_list:
            print(f"  {p}")
        print(f"\n(no --cluster-host / --cluster-base provided; "
              f"would query: ls <base>/*/json/<id>v*_manual.json)",
              file=sys.stderr)
        return

    paths = cluster_find_paths(missing_list, args.cluster_host, args.cluster_base)
    print(f"[fetch] resolved cluster paths for {len(paths)}/{len(missing_list)}",
          file=sys.stderr)
    not_found = [p for p in missing_list if p not in paths]
    for p in not_found:
        print(f"[fetch] NOT FOUND on cluster: {p}", file=sys.stderr)

    if args.dry_run:
        print(f"\n[fetch] DRY RUN — would fetch {len(paths)} papers")
        for aid, path in paths.items():
            print(f"  {aid} <- {path}")
        return

    n_ok = n_fail = 0
    for aid, path in paths.items():
        local_path = args.local_dir / (safe_arxiv_for_filename(aid) + ".json")
        if cluster_fetch_paper(args.cluster_host, path, local_path):
            n_ok += 1
            if n_ok % 10 == 0:
                print(f"[fetch] {n_ok}/{len(paths)} fetched...", file=sys.stderr)
        else:
            n_fail += 1
    print(f"\n[fetch] DONE  ok={n_ok}  failed={n_fail}  "
          f"missing-on-cluster={len(not_found)}", file=sys.stderr)


if __name__ == "__main__":
    main()
