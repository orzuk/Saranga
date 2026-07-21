"""T-OPEN batch O4 — adjudicate a triage shortlist with surrounding-text context.

Walks triage_open.py's CSV and, for each problem->theorem pair, asks the LLM judge
whether paper B's theorem RESOLVES paper A's open problem. Unlike o4_judge.py (which
sends only the two node statements), this locates each node in its ORIGINAL .tex and
sends a window of surrounding text (a paragraph or so before/after) so the judge sees
the narrative that reveals intent — "we now settle the conjecture of ...", the local
notation setup, the citation to the problem. That prose is dropped at parse time, so
it only exists in the source .tex.

Two on-disk .tex layouts (pick with --layout):
  * advanced (the 100k v4 run): <root>/<category>/<YYYY>/<MM>/<DD>/<id>v<n>/<id>v<n>.tex
  * flat     (the 3M run):      <root>/<YYYY>/<MM>/<DD>/<id>v<n>/<id>v<n>.tex
The id's YYMM prefix gives <YYYY>/<MM> (via year_from_arxiv_id); <DD>, the category
(advanced), and the version are globbed, so we jump straight to one month — never a
full-tree walk.

    # 1. PROBE first (no API): check we can find the .tex and locate the nodes.
    python discovery_suite/open_problems/batch_o4.py \
        --triage discovery_suite/open_problems/runs/triage_top_raw.csv \
        --tex-root .../arxiv_data/full_papers_advanced --layout advanced \
        --top 20 --probe

    # 2. then judge (opus, cached):
    python discovery_suite/open_problems/batch_o4.py \
        --triage discovery_suite/open_problems/runs/triage_top_raw.csv \
        --tex-root .../arxiv_data/full_papers_advanced --layout advanced \
        --out discovery_suite/open_problems/runs/o4_verdicts.csv --top 20 --model opus
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
for _p in (_REPO / "src", _REPO / "src" / "discovery",
           _REPO / "src" / "discovery" / "common", _REPO / "discovery_suite",
           _REPO / "discovery_suite" / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from arxiv_id import normalize_arxiv_id, year_from_arxiv_id  # noqa: E402


def _load_dotenv() -> None:
    env = _REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ── locate the paper's .tex ──────────────────────────────────────────────────
def _year_month(pid: str) -> tuple[int, str] | None:
    """(YYYY, 'MM') from an arXiv id, or None for un-datable (old-style) ids."""
    base = normalize_arxiv_id(pid)
    m = re.match(r"^\d{2}(\d{2})\.\d{4,5}$", base)
    if not m:
        return None
    try:
        return year_from_arxiv_id(base), m.group(1)
    except ValueError:
        return None


def resolve_tex(tex_root: str, pid: str, layout: str) -> Path | None:
    """Find the concatenated .tex for `pid` under either on-disk layout.

    The category (advanced) and day are globbed, so only YYYY/MM (from the id) need
    to be known. Returns the first matching .tex, or None."""
    ym = _year_month(pid)
    if ym is None:
        return None
    yyyy, mm = ym
    root = Path(tex_root)
    if layout == "advanced":
        dir_globs = [f"{root}/*/{yyyy}/{mm}/*/{pid}v*"]
    else:  # flat (3M)
        dir_globs = [f"{root}/{yyyy}/{mm}/*/{pid}v*"]
    for pat in dir_globs:
        for d in sorted(glob.glob(pat)):
            dd = Path(d)
            named = dd / f"{dd.name}.tex"          # prefer <id>v<n>.tex
            if named.exists():
                return named
            texs = sorted(dd.glob("*.tex"))        # else any .tex in the dir
            if texs:
                return texs[0]
    return None


# ── locate the node inside the .tex + take a surrounding-text window ──────────
_STOP = set("the a an of in on to is are be that this these for and or not with as "
            "if then let we our by any all such there exists it its where which".split())
_WORD = re.compile(r"[A-Za-z]{4,}")


def _keywords(snippet: str, k: int = 6) -> list[str]:
    """Content words from the (normalized) snippet, longest first (rarer). These
    survive into the .tex prose, so they anchor the node even though the snippet is
    normalized and the source is raw LaTeX."""
    seen, words = set(), []
    for w in _WORD.findall(snippet.lower()):
        if w in _STOP or w in seen:
            continue
        seen.add(w)
        words.append(w)
    return sorted(words, key=len, reverse=True)[:k]


def locate_window(tex: str, snippet: str, radius: int) -> tuple[str | None, int]:
    """Best surrounding-text window in `tex` for the node described by `snippet`.

    Finds the tightest span where the most keywords co-occur, then extends to the
    nearest blank-line (paragraph) boundaries, capped at `radius` each side.
    Returns (window_text | None, n_keywords_matched)."""
    kws = _keywords(snippet)
    if not kws:
        return None, 0
    low = tex.lower()
    # positions of each keyword
    hits: list[tuple[int, int]] = []  # (pos, kw_index)
    for i, kw in enumerate(kws):
        start = 0
        while True:
            j = low.find(kw, start)
            if j < 0:
                break
            hits.append((j, i))
            start = j + len(kw)
    if not hits:
        return None, 0
    hits.sort()
    # slide a window over the sorted hit positions; keep the one covering most kws
    best_center, best_cover = None, 0
    n = len(hits)
    for a in range(n):
        seen = set()
        b = a
        while b < n and hits[b][0] - hits[a][0] <= radius:
            seen.add(hits[b][1])
            b += 1
        if len(seen) > best_cover:
            best_cover = len(seen)
            best_center = (hits[a][0] + hits[b - 1][0]) // 2
    if best_center is None or best_cover < min(2, len(kws)):
        return None, best_cover
    lo = max(0, best_center - radius)
    hi = min(len(tex), best_center + radius)
    # snap outward to paragraph breaks when one is nearby
    pbreak = tex.rfind("\n\n", max(0, lo - radius), lo + 1)
    if pbreak != -1:
        lo = pbreak
    nbreak = tex.find("\n\n", hi - 1, hi + radius)
    if nbreak != -1:
        hi = nbreak
    return tex[lo:hi].strip(), best_cover


# ── judge prompt ─────────────────────────────────────────────────────────────
_PROMPT = (
    "Below are excerpts (with surrounding text for context) from two different "
    "arXiv papers.\n\n"
    "PAPER A ({a_pid}) states an open problem / conjecture. Excerpt:\n"
    "-----\n{a_text}\n-----\n\n"
    "PAPER B ({b_pid}, same year or later) contains a candidate theorem. Excerpt:\n"
    "-----\n{b_text}\n-----\n\n"
    "Does paper B's theorem RESOLVE paper A's open problem/conjecture — i.e. prove, "
    "disprove, or directly settle the SAME mathematical claim about the SAME "
    "object/quantity? \\-macros (e.g. \\CR) are paper-specific; judge whether the "
    "objects truly coincide, not the wording. Use the surrounding text to tell what "
    "each statement is really about and whether B is aware of / cites A.\n\n"
    "Answer in exactly this format:\n"
    "VERDICT: YES | NO | PARTIAL\n"
    "SAME_OBJECT: YES | NO\n"
    "JUSTIFICATION: <1-3 sentences>"
)


def _parse(raw: str) -> dict:
    out = {"verdict": "", "same_object": "", "justification": "", "raw": raw}
    for line in raw.splitlines():
        u = line.upper()
        if u.startswith("VERDICT:"):
            out["verdict"] = line.split(":", 1)[1].strip()
        elif u.startswith("SAME_OBJECT:"):
            out["same_object"] = line.split(":", 1)[1].strip()
        elif u.startswith("JUSTIFICATION:"):
            out["justification"] = line.split(":", 1)[1].strip()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--triage", required=True, help="triage_open.py output CSV")
    ap.add_argument("--tex-root", required=True, help="root of the on-disk .tex tree")
    ap.add_argument("--layout", choices=("advanced", "flat"), default="advanced",
                    help="advanced = 100k (category/YYYY/MM/DD/id), flat = 3M (YYYY/MM/DD/id)")
    ap.add_argument("--out", default=None, help="verdicts CSV (omit with --probe)")
    ap.add_argument("--top", type=int, default=20, help="judge the top-N triage rows")
    ap.add_argument("--radius", type=int, default=1200,
                    help="context window half-width in chars, each side of the node")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--probe", action="store_true",
                    help="locate-only: resolve .tex + windows and report hit/miss, "
                         "NO API calls. Run this first to validate before spending.")
    args = ap.parse_args()

    with open(args.triage, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))[: args.top]
    print(f"[batch_o4] {len(rows)} rows (top {args.top}) from {args.triage}")

    # cache each paper's .tex text (a pair may reuse a paper across rows)
    tex_cache: dict[str, str | None] = {}

    def _context(key: str, snippet: str) -> tuple[str, bool, int]:
        pid = key.split("::", 1)[0]
        if pid not in tex_cache:
            p = resolve_tex(args.tex_root, pid, args.layout)
            tex_cache[pid] = (p.read_text(encoding="utf-8", errors="replace")
                              if p else None)
        tex = tex_cache[pid]
        if not tex:
            return snippet, False, 0            # no .tex -> fall back to snippet
        win, cover = locate_window(tex, snippet, args.radius)
        return (win, True, cover) if win else (snippet, False, cover)

    judge = None
    if not args.probe:
        if not args.out:
            raise SystemExit("--out is required unless --probe")
        _load_dotenv()
        from common.llm_judge import LLMJudge
        judge = LLMJudge(
            model=args.model,
            cache_path=_HERE.parent / "eval_harness" / "runs" / "o4_judge_cache.sqlite",
            prompt_template=_PROMPT,
            prompt_version="o4_resolution_ctx_v1",
            response_parser=_parse,
            max_tokens=400,
            system="You are an expert mathematician judging whether one paper's "
                   "theorem resolves another paper's open problem.",
        )

    found = 0
    out_rows = []
    for i, r in enumerate(rows, 1):
        pk, tk = r["problem_key"], r["theorem_key"]
        a_text, a_ok, a_cov = _context(pk, r["problem_snippet"])
        b_text, b_ok, b_cov = _context(tk, r["theorem_snippet"])
        found += int(a_ok and b_ok)
        tag = "ctx" if (a_ok and b_ok) else ("A?" if not a_ok else "B?")
        print(f"  [{i:>3}] {r['score']:>5} {pk} -> {tk}  "
              f"[{tag} a={a_cov}kw b={b_cov}kw]")
        if args.probe:
            print(f"        A excerpt: {a_text[:110].strip()}")
            print(f"        B excerpt: {b_text[:110].strip()}")
            continue
        res = judge.judge(a_pid=pk.split("::")[0], a_text=a_text[: args.radius * 2],
                          b_pid=tk.split("::")[0], b_text=b_text[: args.radius * 2])
        p = res.parsed
        print(f"        -> VERDICT={p['verdict']} SAME_OBJECT={p['same_object']} "
              f"{'(cached)' if res.cached else ''}")
        print(f"           {p['justification'][:140]}")
        out_rows.append({**r, "verdict": p["verdict"], "same_object": p["same_object"],
                         "justification": p["justification"],
                         "ctx_found": int(a_ok and b_ok)})

    print(f"\n[batch_o4] context located for {found}/{len(rows)} pairs "
          f"(both sides found in their .tex)")
    if args.probe:
        print("[batch_o4] probe only — no verdicts written. Re-run without --probe "
              "(and with --out) to judge.")
        return

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    yes = sum(1 for r in out_rows if r["verdict"].upper() == "YES")
    part = sum(1 for r in out_rows if r["verdict"].upper() == "PARTIAL")
    print(f"[batch_o4] wrote {len(out_rows)} verdicts -> {args.out} "
          f"({yes} YES, {part} PARTIAL)")


if __name__ == "__main__":
    main()
