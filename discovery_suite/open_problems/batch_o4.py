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
import json
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

# Metadata regions that are keyword-dense but are NOT the statement — the probe
# showed the locator otherwise landing on the abstract / \keywords / author block.
_ABSTRACT_RE = re.compile(r"\\begin\{abstract\}.*?\\end\{abstract\}", re.S)
_META_CMD_RE = re.compile(
    r"\\(?:keywords|subjclass|title|author|address|email|thanks|date|dedicatory)"
    r"\s*(?:\[[^\]]*\])?\s*\{", re.I)
# A theorem-like environment (any name containing a statement-ish stem). Excludes
# proof/abstract/figure/table. Non-greedy body; envs don't nest in practice.
_ENV_RE = re.compile(r"\\begin\{([A-Za-z]+\*?)\}(.*?)\\end\{\1\}", re.S)
_STMT_STEMS = ("thm", "theorem", "conj", "lemma", "lem", "prop", "cor", "claim",
               "defin", "defn", "dfn", "problem", "question", "cnj")


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


def _strip_meta(tex: str) -> str:
    """Drop the preamble and metadata so the locator can't land on them. Cuts
    everything before \\begin{document}, blanks the abstract, and blanks the
    argument-opening of title/author/keywords/... commands (length-preserving via
    space-fill so any offsets stay meaningful)."""
    doc = tex.find("\\begin{document}")
    if doc != -1:
        tex = " " * doc + tex[doc:]
    tex = _ABSTRACT_RE.sub(lambda m: " " * len(m.group(0)), tex)
    tex = _META_CMD_RE.sub(lambda m: " " * len(m.group(0)), tex)
    return tex


def _coverage(text: str, kws: list[str]) -> int:
    low = text.lower()
    return sum(1 for kw in kws if kw in low)


def _best_stmt_env(tex: str, kws: list[str]) -> tuple[int, int, int] | None:
    """Best-matching theorem-like environment: (start, end, coverage) or None. The
    node is usually a \\begin{theorem/conjecture/...} block, so scoring statement
    environments by keyword overlap targets the claim, not the surrounding prose."""
    best = None
    for m in _ENV_RE.finditer(tex):
        name = m.group(1).lower()
        if not any(s in name for s in _STMT_STEMS):
            continue
        cov = _coverage(m.group(2), kws)
        if best is None or cov > best[2]:
            best = (m.start(), m.end(), cov)
    return best


def _snap(tex: str, lo: int, hi: int, radius: int) -> str:
    """Extend [lo,hi] out to nearby paragraph (blank-line) breaks, capped by radius."""
    pbreak = tex.rfind("\n\n", max(0, lo - radius), lo + 1)
    if pbreak != -1:
        lo = pbreak
    nbreak = tex.find("\n\n", max(hi - 1, 0), hi + radius)
    if nbreak != -1:
        hi = nbreak
    return tex[max(0, lo):hi].strip()


def locate_window(tex: str, snippet: str, radius: int) -> tuple[str | None, int]:
    """Best surrounding-text window in `tex` for the node described by `snippet`.

    Prefers the theorem-like environment whose body best matches the snippet's
    keywords (that IS the statement), widened to the paragraph before/after for the
    narrative ("we now settle ..."). Falls back to the tightest keyword cluster for
    statements written inline (no environment). Returns (window | None, coverage)."""
    kws = _keywords(snippet)
    if not kws:
        return None, 0
    tex = _strip_meta(tex)
    low = tex.lower()

    # keyword-cluster fallback (also used to score inline statements)
    hits: list[tuple[int, int]] = []
    for i, kw in enumerate(kws):
        start = 0
        while (j := low.find(kw, start)) >= 0:
            hits.append((j, i))
            start = j + len(kw)
    cluster_center, cluster_cov = None, 0
    hits.sort()
    n = len(hits)
    for a in range(n):
        seen, b = set(), a
        while b < n and hits[b][0] - hits[a][0] <= radius:
            seen.add(hits[b][1])
            b += 1
        if len(seen) > cluster_cov:
            cluster_cov = len(seen)
            cluster_center = (hits[a][0] + hits[b - 1][0]) // 2

    # prefer a statement environment when it matches at least as well as the cluster
    env = _best_stmt_env(tex, kws)
    if env is not None and env[2] >= max(2, cluster_cov - 1):
        return _snap(tex, env[0], env[1], radius), env[2]
    if cluster_center is not None and cluster_cov >= 2:
        lo = max(0, cluster_center - radius)
        return _snap(tex, lo, min(len(tex), cluster_center + radius), radius), cluster_cov
    return None, cluster_cov


# ── raw_latex fallback anchor (for symbolic nodes with no content words) ─────
# The CSV snippet of a node like "the map psi is a bijection" has no distinctive
# words (psi/map are short/generic), so keyword-locate fails (b=0kw). The parsed
# JSON keeps the node's raw_latex, which carries its \label{...} — a far more
# reliable anchor — and, failing that, is itself a better excerpt than the tiny
# normalized snippet.
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")


def resolve_parsed(parsed_root: str, pid: str) -> Path | None:
    """Find the parsed JSON for `pid`. Layout is <category>/<year>/<id>*.json; the
    year comes from the id and the category is globbed (~20 dirs), so no tree walk."""
    try:
        yyyy = year_from_arxiv_id(pid)
    except ValueError:
        return None
    for pat in (f"{parsed_root}/*/{yyyy}/{pid}*.json",
                f"{parsed_root}/{yyyy}/{pid}*.json"):
        hits = sorted(glob.glob(pat))
        if hits:
            return Path(hits[0])
    return None


def load_node_raw(parsed_root: str, key: str, cache: dict) -> str | None:
    """raw_latex of the node `paper::id` from its parsed JSON (None if not found)."""
    pid, nid = key.split("::", 1)
    if pid not in cache:
        p = resolve_parsed(parsed_root, pid)
        try:
            cache[pid] = json.loads(p.read_text(encoding="utf-8")).get("nodes", []) \
                if p else []
        except Exception:
            cache[pid] = []
    for n in cache[pid]:
        if str(n.get("id")) == nid:
            return (n.get("raw_latex") or "").strip() or None
    return None


def locate_by_label(tex: str, raw_latex: str, radius: int) -> str | None:
    """Locate the node in `tex` by its \\label{...} (taken from raw_latex) — exact
    and symbol-proof — then window with the paragraph snap. None if no label hits."""
    for lab in _LABEL_RE.findall(raw_latex):
        j = tex.find("\\label{" + lab + "}")
        if j >= 0:
            return _snap(tex, max(0, j - radius), min(len(tex), j + radius), radius)
    return None


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


def _preview(side: str, text: str, edge: int = 320) -> None:
    """Print the head and tail of a located window (with its size) so --probe shows
    what the judge will actually receive, not just the first line."""
    flat = " ".join(text.split())
    size = len(text)
    if size <= 2 * edge:
        print(f"        {side} [{size}c]: {flat}")
    else:
        print(f"        {side} [{size}c] head: {flat[:edge]}")
        print(f"        {side}       tail: {flat[-edge:]}")


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
    ap.add_argument("--radius", type=int, default=1800,
                    help="context window half-width in chars each side of the node "
                         "(~6 chars/word, so 1800 ~= 300 words/side). Bigger = more "
                         "context but more tokens/$ and risk of pulling in a neighbour.")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--parsed-root", default=None,
                    help="root of the parsed JSON (<category>/<year>/<id>.json). Enables "
                         "the raw_latex fallback: when a symbolic node has no content "
                         "words to keyword-locate, anchor on its \\label{} in the .tex, "
                         "else send its raw_latex instead of the tiny normalized snippet.")
    ap.add_argument("--citations", default=None,
                    help="S2 citation-graph sqlite (common/citation_graph.py). Enables "
                         "the novelty gate: flag pairs where B cites A (a KNOWN "
                         "resolution) vs neither (the undiscovered target).")
    ap.add_argument("--s2-key", default=None,
                    help="Semantic Scholar API key (else $S2_KEY). Higher rate limit.")
    ap.add_argument("--no-fetch-citations", action="store_true",
                    help="with --citations: query the cache only, don't hit S2 for "
                         "missing papers (offline / already-populated cache).")
    ap.add_argument("--probe", action="store_true",
                    help="locate-only: resolve .tex + windows and report hit/miss, "
                         "NO API calls. Run this first to validate before spending.")
    args = ap.parse_args()

    with open(args.triage, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))[: args.top]
    print(f"[batch_o4] {len(rows)} rows (top {args.top}) from {args.triage}")

    # cache each paper's .tex text / parsed nodes (a pair may reuse a paper)
    tex_cache: dict[str, str | None] = {}
    node_cache: dict[str, list] = {}

    def _context(key: str, snippet: str) -> tuple[str, str, int]:
        """Return (excerpt, status, coverage). status: 'ctx' = located window in the
        .tex (best), 'raw' = the node's raw_latex (real statement, no surrounding
        prose), 'snip' = the normalized snippet (last resort)."""
        pid = key.split("::", 1)[0]
        if pid not in tex_cache:
            p = resolve_tex(args.tex_root, pid, args.layout)
            tex_cache[pid] = (p.read_text(encoding="utf-8", errors="replace")
                              if p else None)
        tex = tex_cache[pid]
        if tex:
            win, cover = locate_window(tex, snippet, args.radius)
            if win:
                return win, "ctx", cover
        # keyword-locate failed (or no .tex). Try the raw_latex fallback (#2).
        if args.parsed_root:
            raw = load_node_raw(args.parsed_root, key, node_cache)
            if raw:
                if tex:
                    win = locate_by_label(tex, raw, args.radius)
                    if win:
                        return win, "ctx", -1     # anchored on \label, not keywords
                return raw, "raw", -1             # real statement beats the snippet
        return snippet, "snip", 0

    # citation-novelty gate (#3): does B cite A (a KNOWN resolution) or neither?
    cg = None
    if args.citations:
        from citation_graph import S2CitationGraph
        cg = S2CitationGraph(Path(args.citations),
                             api_key=args.s2_key or os.environ.get("S2_KEY"))
        if not args.no_fetch_citations:
            pids = sorted({r["problem_key"].split("::")[0] for r in rows} |
                          {r["theorem_key"].split("::")[0] for r in rows})
            print(f"[batch_o4] fetching S2 citations for {len(pids)} papers …")
            cg.fetch_batch(pids)

    def _cite_gate(pk: str, tk: str) -> tuple[int, int, int]:
        """(b_cites_a, a_cites_b, novel). Each 1/0, or -1 if a paper is unknown to
        the cache. novel=1 only when BOTH directions are known AND neither cites."""
        a, b = pk.split("::")[0], tk.split("::")[0]
        if cg is None or not (cg.has(a) and cg.has(b)):
            return -1, -1, -1
        ba, ab = int(cg.cites(b, a)), int(cg.cites(a, b))
        return ba, ab, int(not (ba or ab))

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
        a_text, a_st, a_cov = _context(pk, r["problem_snippet"])
        b_text, b_st, b_cov = _context(tk, r["theorem_snippet"])
        both_ctx = (a_st == "ctx" and b_st == "ctx")
        found += int(both_ctx)
        b_cites_a, a_cites_b, novel = _cite_gate(pk, tk)
        ctag = ("CITED" if (b_cites_a == 1 or a_cites_b == 1) else
                "novel" if novel == 1 else "?    ")
        print(f"  [{i:>3}] {r['score']:>5} {pk} -> {tk}  "
              f"[a:{a_st}/{a_cov}kw b:{b_st}/{b_cov}kw {ctag}]")
        if args.probe:
            _preview("A", a_text)
            _preview("B", b_text)
            continue
        res = judge.judge(a_pid=pk.split("::")[0], a_text=a_text[: args.radius * 2],
                          b_pid=tk.split("::")[0], b_text=b_text[: args.radius * 2])
        p = res.parsed
        print(f"        -> VERDICT={p['verdict']} SAME_OBJECT={p['same_object']} "
              f"cite={ctag.strip()} {'(cached)' if res.cached else ''}")
        print(f"           {p['justification'][:140]}")
        out_rows.append({**r, "verdict": p["verdict"], "same_object": p["same_object"],
                         "justification": p["justification"],
                         "ctx_found": int(both_ctx),
                         "b_cites_a": b_cites_a, "a_cites_b": a_cites_b, "novel": novel})

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
    # the discovery target: YES + same object + solid context + not a cited resolution
    disc = [r for r in out_rows
            if r["verdict"].upper() in ("YES", "PARTIAL")
            and str(r["same_object"]).upper() == "YES"
            and r["ctx_found"] == 1 and r["novel"] == 1]
    print(f"[batch_o4] wrote {len(out_rows)} verdicts -> {args.out} "
          f"({yes} YES, {part} PARTIAL)")
    if args.citations:
        print(f"[batch_o4] {len(disc)} UNDISCOVERED candidate(s) "
              f"(YES/PARTIAL + same_object + ctx + not-cited):")
        for r in disc:
            print(f"    {r['score']} {r['problem_key']} -> {r['theorem_key']}")


if __name__ == "__main__":
    main()
