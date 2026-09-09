#!/usr/bin/env python3
"""Complexity and cost of a distilled rule set.

Answers two separate questions about every ``re.compile`` pattern in a set of
distilled rules, and keeps them separate because they disagree:

1. *Can this rule ever hang?*  A static verdict — linear, polynomial of degree
   k, or exponential — obtained without executing the pattern, by handing it to
   ``regexploit`` (https://github.com/doyensec/regexploit).  The underlying
   method is the NFA ambiguity analysis of Weideman, van der Merwe, Berglund and
   Watson, *Analyzing Matching Time Behavior of Backtracking Regular Expression
   Matchers by Using Ambiguity of NFA*, CIAA 2016, LNCS 9705, 322-334.  For a
   flagged rule regexploit also returns a witness string that triggers the
   blow-up, which is carried through to the ``witness`` column.

2. *What does this rule actually cost us?*  Wall-clock seconds for one
   ``finditer`` pass over each paper of a ``.tex`` sample, per pattern, under a
   per-pair timeout.  This is the number that predicts corpus-scale throughput.

Alongside both, a handful of structural metrics read off Python's own regex
parser (``re._parser``): star height, quantifier and alternation counts,
lookarounds, backreferences, pattern length.

On the v5.1 train60 rules the two verdicts rank the set completely differently:
the 15 statically exponential rules are 2.7% of measured runtime, while the 20
slowest rules — 67% of runtime — are all classified linear.  Rank by measured
time to make the parse faster; rank by static verdict to find what can hang.

Usage::

    # both halves, over one distillation run's group files
    python src/LLMVersion/rule_complexity.py \
        --rules src/LLMVersion/merged_eval_v51_train60_v2/groups \
        --tex   portal/data/tier2_tex \
        --out   rule_complexity_train60.csv

    # static verdicts only (no corpus needed, seconds instead of minutes)
    python src/LLMVersion/rule_complexity.py --rules <dir> --out static.csv --no-bench

``--rules`` accepts either a ``groups/`` directory of per-group
``distilled_rules.py`` files or a single such file.  Commented-out patterns —
what the FDR prune step leaves behind — are skipped, so the count reflects live
rules only.

Requires ``pip install regexploit`` for the static half; without it the script
still reports structure and timings and leaves ``verdict`` empty.
"""
from __future__ import annotations

import argparse
import ast
import csv
import re
import signal
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

try:                                    # 3.11 renamed the parser internals
    import re._constants as sre_constants
    import re._parser as sre_parse
except ImportError:                     # pragma: no cover - older interpreters
    import sre_constants
    import sre_parse

MAXREPEAT = sre_parse.MAXREPEAT
_REPEATS = {sre_constants.MAX_REPEAT, sre_constants.MIN_REPEAT}


# ── 1. pull the patterns out of the rule files ──────────────────────────────
def extract_patterns(path: Path) -> list[dict]:
    """Every live ``re.compile`` call in one rules file, with flags resolved.

    Patterns are read from the AST rather than by importing, so module-level
    constants and calls nested inside functions are both caught, and anything
    the prune step commented out is invisible.  Shared sub-patterns
    (``_DISPLAY_MATH`` and friends) are resolved by evaluating the file's
    module-level string assignments first.
    """
    tree = ast.parse(path.read_text())

    ns: dict = {"re": re}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            try:
                ns[node.targets[0].id] = eval(ast.unparse(node.value), dict(ns))
            except Exception:
                pass                    # not a constant we can fold; skip it

    # nearest enclosing assignment or def, so each pattern gets a usable name
    owner: dict[int, str] = {}
    for node in ast.walk(tree):
        label = None
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            label = node.targets[0].id
        elif isinstance(node, ast.FunctionDef):
            label = node.name
        if label:
            for sub in ast.walk(node):
                if _is_compile(sub):
                    owner.setdefault(sub.lineno, label)

    out = []
    for node in ast.walk(tree):
        if not _is_compile(node):
            continue
        try:
            pattern = eval(ast.unparse(node.args[0]), dict(ns))
        except Exception:
            continue                    # dynamically built; nothing to analyse
        flags = 0
        for kw in node.keywords:
            if kw.arg in ("flags", None):
                flags = _try_eval(ast.unparse(kw.value), ns, flags)
        if len(node.args) > 1:
            flags = _try_eval(ast.unparse(node.args[1]), ns, flags)
        out.append({"file": path, "line": node.lineno,
                    "name": owner.get(node.lineno, f"<line {node.lineno}>"),
                    "pattern": pattern, "flags": int(flags)})
    return out


def _is_compile(node) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compile" and node.args)


def _try_eval(src: str, ns: dict, default):
    try:
        return eval(src, dict(ns))
    except Exception:
        return default


# ── 2. structural metrics, off Python's own parser ──────────────────────────
def metrics(pattern: str, flags: int = 0) -> dict:
    """Shape of one pattern: star height, quantifiers, alternations, length."""
    try:
        tree = sre_parse.parse(pattern, flags)
    except Exception:
        return {}
    m: dict = defaultdict(int)
    m["star_height"] = 0

    def walk(seq, depth):
        for op, av in seq:
            m["nodes"] += 1
            if op in _REPEATS:
                _lo, hi, sub = av
                m["quantifiers"] += 1
                if hi == MAXREPEAT:
                    m["unbounded"] += 1
                m["star_height"] = max(m["star_height"], depth + 1)
                walk(sub, depth + 1)
            elif op is sre_constants.BRANCH:
                m["alternations"] += 1
                m["branches"] += len(av[1])
                for branch in av[1]:
                    walk(branch, depth)
            elif op is sre_constants.SUBPATTERN:
                m["groups"] += 1
                walk(av[3], depth)
            elif op in (sre_constants.ASSERT, sre_constants.ASSERT_NOT):
                m["lookarounds"] += 1
                walk(av[1], depth)
            elif op is sre_constants.GROUPREF:
                m["backrefs"] += 1
            elif op is sre_constants.ATOMIC_GROUP:
                walk(av, depth)
            elif op is sre_constants.GROUPREF_EXISTS:
                for branch in av[1:]:
                    if branch:
                        walk(branch, depth)

    walk(tree, 0)
    m["length"] = len(pattern)
    m["dotall"] = bool(flags & re.DOTALL)
    return dict(m)


# ── 3. static verdicts, via regexploit ──────────────────────────────────────
_VULN_RE = re.compile(r"#(\d+)\s*$")


def static_verdicts(files: list[Path]) -> dict[tuple[Path, int], dict]:
    """Run regexploit's Python-AST scanner and keep the worst verdict per rule.

    regexploit reports one entry per way a pattern can blow up; a rule's
    verdict is the worst of them.  Keyed by (file, line) so it joins onto the
    extracted patterns.  Returns {} if regexploit is not installed.
    """
    verdicts: dict[tuple[Path, int], dict] = {}
    for path in files:
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "regexploit.bin.regexploit_python_ast", str(path)],
                capture_output=True, text=True, timeout=1800)
        except FileNotFoundError:       # pragma: no cover
            return {}
        if proc.returncode != 0 and not proc.stdout:
            print(f"  regexploit unavailable ({proc.stderr.strip()[:80]})", file=sys.stderr)
            return {}

        key = None
        for line in proc.stdout.splitlines():
            if line.startswith("Vulnerable regex in"):
                hit = _VULN_RE.search(line)
                key = (path, int(hit.group(1))) if hit else None
                if key:
                    verdicts.setdefault(key, {"star": 0, "verdict": "", "witness": ""})
            elif key and line.startswith("Worst-case complexity:"):
                star = int(re.search(r":\s*(\d+)", line).group(1))
                if star > verdicts[key]["star"]:
                    verdicts[key].update(star=star, verdict=line.split("(")[-1].rstrip(")"))
            elif key and line.startswith("Example:") and not verdicts[key]["witness"]:
                verdicts[key]["witness"] = line[len("Example:"):].strip()
    return verdicts


# ── 4. measured cost over a .tex sample ─────────────────────────────────────
class _Timeout(Exception):
    pass


def bench(patterns: list[dict], docs: list[tuple[str, str]], cap: float) -> None:
    """Time one finditer pass of every pattern over every document, in place.

    A pattern that exceeds ``cap`` seconds on one document is recorded as
    ``cap`` and abandoned — so a timed-out rule's true cost is a lower bound,
    not a measurement.
    """
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(_Timeout()))
    for i, rec in enumerate(patterns, 1):
        try:
            rx = re.compile(rec["pattern"], rec["flags"])
        except re.error:
            continue
        total = worst = 0.0
        worst_doc, timed_out = "", False
        for name, text in docs:
            signal.setitimer(signal.ITIMER_REAL, cap)
            start = time.perf_counter()
            try:
                for _ in rx.finditer(text):
                    pass
            except _Timeout:
                timed_out, elapsed = True, cap
            else:
                elapsed = time.perf_counter() - start
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
            total += elapsed
            if elapsed > worst:
                worst, worst_doc = elapsed, name
            if timed_out:
                break
        rec.update(total_s=round(total, 4), worst_doc_s=round(worst, 4),
                   worst_doc=worst_doc, timeout=timed_out)
        if timed_out:
            print(f"  timeout >{cap:g}s: {rec['name']} on {worst_doc}", file=sys.stderr)
        if i % 50 == 0:
            print(f"  {i}/{len(patterns)} timed", file=sys.stderr)


# ── main ────────────────────────────────────────────────────────────────────
FIELDS = ["group", "name", "line", "verdict", "redos_star", "total_s", "worst_doc_s",
          "timeout", "length", "nodes", "star_height", "quantifiers", "unbounded",
          "alternations", "groups", "lookarounds", "backrefs", "dotall",
          "witness", "pattern"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rules", required=True, type=Path,
                    help="groups/ directory, or a single distilled_rules.py")
    ap.add_argument("--tex", type=Path, help="directory of .tex files to time against")
    ap.add_argument("--out", required=True, type=Path, help="CSV to write")
    ap.add_argument("--timeout", type=float, default=10.0,
                    help="seconds per pattern-document pair (default 10)")
    ap.add_argument("--no-bench", action="store_true", help="skip the timing pass")
    args = ap.parse_args()

    files = ([args.rules] if args.rules.is_file()
             else sorted(args.rules.glob("*/distilled_rules.py"))
             or sorted(args.rules.glob("distilled_rules.py")))
    if not files:
        sys.exit(f"no distilled_rules.py under {args.rules}")

    patterns: list[dict] = []
    for path in files:
        found = extract_patterns(path)
        patterns.extend(found)
        print(f"{path.parent.name}: {len(found)} live patterns", file=sys.stderr)
    print(f"{len(patterns)} live patterns total", file=sys.stderr)

    print("static analysis (regexploit)...", file=sys.stderr)
    verdicts = static_verdicts(files)

    if not args.no_bench:
        if not args.tex:
            sys.exit("--tex is required unless --no-bench is given")
        docs = [(p.name, p.read_text(encoding="utf-8", errors="ignore"))
                for p in sorted(args.tex.glob("*.tex"))]
        print(f"timing over {len(docs)} papers, "
              f"{sum(len(t) for _, t in docs):,} chars...", file=sys.stderr)
        bench(patterns, docs, args.timeout)

    rows = []
    for rec in patterns:
        shape = metrics(rec["pattern"], rec["flags"])
        hit = verdicts.get((rec["file"], rec["line"]), {})
        rows.append({
            "group": rec["file"].parent.name, "name": rec["name"], "line": rec["line"],
            "verdict": hit.get("verdict", "linear" if verdicts else ""),
            "redos_star": hit.get("star", 0),
            "total_s": rec.get("total_s", ""), "worst_doc_s": rec.get("worst_doc_s", ""),
            "timeout": rec.get("timeout", ""),
            "length": shape.get("length", 0), "nodes": shape.get("nodes", 0),
            "star_height": shape.get("star_height", 0),
            "quantifiers": shape.get("quantifiers", 0),
            "unbounded": shape.get("unbounded", 0),
            "alternations": shape.get("alternations", 0),
            "groups": shape.get("groups", 0),
            "lookarounds": shape.get("lookarounds", 0),
            "backrefs": shape.get("backrefs", 0),
            "dotall": shape.get("dotall", False),
            "witness": hit.get("witness", ""), "pattern": rec["pattern"],
        })
    rows.sort(key=lambda r: -(r["total_s"] or 0) if r["total_s"] != "" else 0)

    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    _summary(rows)
    print(f"wrote {args.out}")


def _summary(rows: list[dict]) -> None:
    from collections import Counter
    order = {"linear": 0, "quadratic": 1, "cubic": 2, "quartic": 3,
             "quintic": 4, "exponential": 9}
    print(f"\n{len(rows)} rules")
    for verdict, count in sorted(Counter(r["verdict"] for r in rows).items(),
                                 key=lambda kv: order.get(kv[0], 5)):
        print(f"  {verdict or '(no static verdict)':<14} {count:>4}")
    timed = [r for r in rows if r["total_s"] != ""]
    if not timed:
        return
    total = sum(r["total_s"] for r in timed)
    flagged = sum(r["total_s"] for r in timed if r["verdict"] not in ("linear", ""))
    top20 = sum(r["total_s"] for r in timed[:20])
    print(f"\n  measured total        {total:.1f}s")
    print(f"  flagged non-linear    {flagged / total * 100:.1f}% of runtime")
    print(f"  20 slowest rules      {top20 / total * 100:.1f}% of runtime")
    print(f"  non-linear in top 20  "
          f"{sum(1 for r in timed[:20] if r['verdict'] not in ('linear', ''))}")


if __name__ == "__main__":
    main()
