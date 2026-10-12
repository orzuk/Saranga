"""Runtime quarantine for pathologically slow regexes — any rule, any source.

Why this exists
---------------
A catastrophically backtracking regex does not raise, does not return, and
cannot be interrupted by a `try/except`: it spins inside CPython's C matcher.
Three separate call sites in this codebase were each hung by one, and each was
patched individually — `prune_rules`, the distilled-rule dispatch in the
parser, and the scoring parse. Patching call sites does not scale, because the
next runaway simply appears at the fourth.

The generation-time guards do not close it either. `prune_slow_rules` times a
pattern against the papers seen SO FAR, so a rule written on paper 1 is only
ever proven fast on paper 1. Measured on the v5.1 corpus, rules that passed
that check stalled 8 of 40 unseen papers at the cap.

So the guard belongs on the pattern, not on the caller and not on the corpus:
time every match, and the first time one blows the budget, disable it for the
rest of the process and write down what happened. A rule that cannot finish is
not a rule.

What it does
------------
* wraps a compiled pattern so every search/findall/finditer/... is timed
* aborts a call that exceeds `threshold` (SIGALRM, so C-level spinning is
  actually interruptible) and returns the empty result for that call
* quarantines the pattern permanently: later calls return empty immediately,
  costing nothing
* records it — to stderr, to a JSONL file, and (for generated rule files) by
  commenting the offending rule out at source with a `# PRUNED-SLOW` marker,
  so the next run never even loads it

Limits, stated plainly
----------------------
* SIGALRM is process-global and main-thread only. Multiprocessing workers each
  have their own main thread, so the cap holds there. Off the main thread this
  degrades to timing-only: the first offence is not interrupted, but the
  pattern is still quarantined afterwards so it costs at most once.
* Quarantine is per-process. Source commenting is what makes it persist.
* A pattern that is merely slow on ONE pathological document is disabled for
  the whole run, including documents it would have handled fine. That is the
  intended trade: correctness of the run over the last few matches of one rule.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import threading
import time

#: Seconds a single regex call may take before the pattern is quarantined.
DEFAULT_THRESHOLD = 5.0

#: Seconds a pattern may spend in TOTAL, across all its calls, on one document
#: before it is quarantined. Needed because the per-call cap alone misses the
#: commoner failure: not one catastrophic match, but tens of thousands of
#: merely-slow ones. A generated definition rule stalled a document for
#: minutes without any single call approaching the per-call cap. Reset per
#: document via `new_document()`.
DEFAULT_BUDGET = 10.0

#: A pattern whose MEAN call is faster than this is never quarantined on
#: cumulative time, however many times it is called. Total time alone cannot
#: distinguish "pathological" from "popular", and disabling a popular pattern
#: is far more damaging than tolerating a slow one.
MIN_MEAN_SECONDS = 0.05

#: {(pattern, flags): [seconds, calls]} for the current document.
_SPENT: dict = {}
_BUDGET = DEFAULT_BUDGET

#: {(pattern, flags): record} for everything quarantined in this process.
_QUARANTINED: dict = {}

#: Where to append quarantine records. Set via `configure()`.
_LOG_PATH = None
_THRESHOLD = DEFAULT_THRESHOLD

_EMPTY = {
    "findall": lambda: [],
    "finditer": lambda: iter(()),
    "search": lambda: None,
    "match": lambda: None,
    "fullmatch": lambda: None,
    "split": lambda: [],
    "sub": lambda: None,      # replaced with the input string by _run
    "subn": lambda: None,
}


class _RegexTimeout(Exception):
    pass


# ── Speed-ups (exact) ────────────────────────────────────────────────────────
#
# Ways to do less work for the same answer. Each is exact by construction, and
# together they were checked byte-identical against the plain path on 152
# held-out papers (5.8x faster on the HUJI cluster). SARANGA_REGEX_REFERENCE=1
# turns them all off, to re-check a new rule set against the plain path.
#
#   sentinel     a rule switched off by subset selection is bound to (?!x)x,
#                which matches nothing yet still scans the whole paper: skipped
#   prefilter    a pattern that needs a literal (a keyword) cannot match a text
#                without it: skipped
#   memo         the same pattern on the same text returns its earlier result;
#                generated rule files ask the same question once per candidate
#                (_inside_excluded_env rescanned the whole paper each time)
#   anchoring    when the pattern bounds how far before its keyword a match can
#                start ([^.]{0,120}?\bcalled -> 120), only those starts are
#                tried, with pattern.match on the full text, in finditer's order

try:
    from re import _parser as sre_parse, _constants as sre_c
except ImportError:                      # Python < 3.11
    import sre_parse
    import sre_constants as sre_c

_FAST = os.environ.get("SARANGA_REGEX_REFERENCE", "") != "1"
_SENTINEL = "(?!x)x"
_MEMO: dict = {}             # (method, pattern, flags, text) -> result, this document

_CASEFOLD_TRAPS = set("KſıİÅﬅﬆẞ")


def _required_groups(parsed) -> list[list[str]]:
    """Literal groups that must ALL occur for `parsed` to match. Each group is a
    list of alternatives, one of which must occur. Conservative: anything not
    provably required contributes no group."""
    groups: list[list[str]] = []
    run: list[str] = []

    def flush():
        nonlocal run
        if len(run) >= 3:
            groups.append(["".join(run)])
        run = []

    for op, av in parsed:
        if op is sre_c.LITERAL:
            run.append(chr(av))
            continue
        flush()
        if op is sre_c.SUBPATTERN:
            # (?i:...) / (?-i:...) change case rules inside the group: derive nothing
            if not (av[1] or av[2]):
                groups.extend(_required_groups(av[-1]))
        elif op is sre_c.BRANCH:
            alts = [_best(_required_groups(b)) for b in av[1]]
            if all(alts):
                groups.append([x for a in alts for x in a])
        elif op in (sre_c.MAX_REPEAT, sre_c.MIN_REPEAT) and av[0] >= 1:
            groups.extend(_required_groups(av[2]))
        elif op is sre_c.ASSERT and av[0] == 1:      # positive lookahead
            groups.extend(_required_groups(av[1]))
    flush()
    return groups


def _best(groups):
    """The single most selective group (longest shortest alternative), for a branch."""
    return max(groups, key=lambda g: min(map(len, g)), default=None)


_LITS: dict[tuple, tuple] = {}


def _literals_for(pat: re.Pattern):
    key = (pat.pattern, pat.flags)
    if key not in _LITS:
        lits = None
        if isinstance(pat.pattern, str) and not (pat.flags & re.VERBOSE):
            try:
                lits = _required_groups(sre_parse.parse(pat.pattern, pat.flags)) or None
            except Exception:
                lits = None
        icase = bool(pat.flags & re.IGNORECASE)
        if lits and icase:
            lits = [[l.lower() for l in g] for g in lits]
        _LITS[key] = (lits, icase)
    return _LITS[key]


_LOWER: dict = {}


_VERDICT: dict = {}


def _may_match(pat: re.Pattern, text) -> bool:
    if not isinstance(text, str):
        return True
    lits, icase = _literals_for(pat)
    if not lits:
        return True
    vkey = (pat.pattern, pat.flags, text)
    v = _VERDICT.get(vkey)
    if v is not None:
        return v
    if icase:
        low = _LOWER.get(text)
        if low is None:
            low = _LOWER[text] = (text.lower(), bool(_CASEFOLD_TRAPS & set(text)))
        if low[1]:
            _VERDICT[vkey] = True
            return True
        hay = low[0]
    else:
        hay = text
    v = _VERDICT[vkey] = all(any(l in hay for l in g) for g in lits)
    return v


_PLANS: dict = {}


def _anchor_plans(pat: re.Pattern) -> list:
    """For each required literal group whose distance from the match start is
    bounded: (alternatives, B). Empty when the pattern cannot be anchored."""
    key = (pat.pattern, pat.flags)
    if key in _PLANS:
        return _PLANS[key]
    plans = []
    try:
        tree = sre_parse.parse(pat.pattern, pat.flags)
        if not (pat.flags & re.VERBOSE):
            groups = _required_groups(tree)
            for g in groups:
                b = _prefix_bound(tree, g, tree.state)
                if b is not None:
                    alts = [a.lower() for a in g] if pat.flags & re.IGNORECASE else g
                    plans.append((alts, b))
    except Exception:
        plans = []
    _PLANS[key] = plans
    return plans


def _width(items, state) -> int | None:
    hi = sre_parse.SubPattern(state, list(items)).getwidth()[1]
    return None if hi >= sre_c.MAXREPEAT else hi


def _prefix_bound(tree, group, state) -> int | None:
    """Max distance from the match start to where `group` is matched, or None."""
    acc, run, run_at = 0, "", 0
    items = list(tree)
    for i, (op, av) in enumerate(items):
        if op is sre_c.LITERAL:
            if not run:
                run_at = acc
            run += chr(av)
            acc += 1
            continue
        if len(run) >= 3 and group == [run]:
            return run_at
        run = ""
        one = [(op, av)]
        if group in _required_groups(sre_parse.SubPattern(state, one)):
            if op in (sre_c.ASSERT, sre_c.ASSERT_NOT):
                # A lookahead has zero width but reads ahead without limit:
                # `^(?=.*refer)` finds "refer" anywhere, so it gives no bound.
                # (Taking its width, 0, anchored the search at the literal's
                # occurrences, where a `^` pattern cannot match: lost matches.)
                return None
            if op is sre_c.SUBPATTERN and not (av[1] or av[2]):
                inner = _prefix_bound(av[-1], group, state)
                if inner is not None:
                    return acc + inner
            w = _width(one, state)
            return None if w is None else acc + w
        w = _width(one, state)
        if w is None:
            return None
        acc += w
    if len(run) >= 3 and group == [run]:
        return run_at
    return None


def _anchored_matches(pat: re.Pattern, text: str):
    """The matches of pat.finditer(text), found from anchor occurrences; or None
    when anchoring would not pay (or cannot be used for this text)."""
    plans = _anchor_plans(pat)
    if not plans:
        return None
    hay = text
    if pat.flags & re.IGNORECASE:
        low = _LOWER.get(text)
        if low is None:
            low = _LOWER[text] = (text.lower(), bool(_CASEFOLD_TRAPS & set(text)))
        if low[1]:
            return None
        hay = low[0]
    best = None
    for alts, b in plans:                  # the anchor with the fewest candidate starts
        occ = []
        for a in alts:
            i = hay.find(a)
            while i != -1:
                occ.append(i)
                i = hay.find(a, i + 1)
        cost = len(occ) * (b + 1)
        if best is None or cost < best[0]:
            best = (cost, occ, b)
    cost, occ, b = best
    if cost * 4 > len(text):               # most of the text anyway: scan it whole
        return None
    starts = set()
    for q in occ:
        starts.update(range(max(0, q - b), q + 1))
    out, done = [], 0
    for s in sorted(starts):
        if s < done:
            continue
        m = pat.match(text, s)
        if m is not None and m.end() > m.start():
            out.append(m)
            done = m.end()
    return out


_NOT_ANCHORED = object()


def _findall_item(pat: re.Pattern, m: re.Match):
    """What findall returns for one match: the whole match, the one group, or
    the tuple of groups ('' for a group that did not take part)."""
    if pat.groups == 0:
        return m.group(0)
    if pat.groups == 1:
        return m.group(1) or ""
    return m.groups("")


def _memo_iter(key, gen):
    """Yield from `gen`, and remember the results once it is exhausted."""
    out = []
    for m in gen:
        out.append(m)
        yield m
    _MEMO[key] = out


def configure(threshold=None, log_path=None, budget=None):
    """Set the per-call cap, the per-document budget, and the record file."""
    global _THRESHOLD, _LOG_PATH, _BUDGET
    if threshold is not None:
        _THRESHOLD = float(threshold)
    if budget is not None:
        _BUDGET = float(budget)
    if log_path is not None:
        _LOG_PATH = str(log_path)


def new_document():
    """Reset per-document time accounting. Call before parsing each paper.

    Quarantine itself is deliberately NOT reset: a pattern that has proven it
    cannot finish stays disabled for the process.
    """
    _SPENT.clear()
    _MEMO.clear()                     # a new paper: earlier texts cannot recur
    _VERDICT.clear()
    _LOWER.clear()


def quarantined():
    """Records for every pattern disabled in this process."""
    return list(_QUARANTINED.values())


def _record(pat, name, source, seconds, text_len, reason="single-call"):
    key = (pat.pattern, pat.flags)
    if key in _QUARANTINED:
        return _QUARANTINED[key]
    rec = {
        "rule_name": name or "<inline>",
        "source": source or "<unknown>",
        "pattern": pat.pattern[:400],
        "flags": pat.flags,
        "seconds": round(seconds, 2),
        "text_chars": text_len,
        "reason": reason,
        "pid": os.getpid(),
    }
    _QUARANTINED[key] = rec
    # Loud, on stderr, so it survives whatever the caller does with stdout.
    _why = (f"one match took >{_THRESHOLD:.0f}s" if reason == "single-call"
            else f"spent {seconds:.1f}s in total (budget {_BUDGET:.0f}s)")
    print(f"[SLOW-RULE] QUARANTINED {rec['rule_name']} from {rec['source']}: "
          f"{_why} on a {text_len:,}-char document. Disabled for the rest of "
          f"this run. pattern={rec['pattern'][:120]!r}",
          file=sys.stderr, flush=True)
    if _LOG_PATH:
        try:
            os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
            with open(_LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
        except Exception as e:                      # never let logging break a run
            print(f"[SLOW-RULE] could not write {_LOG_PATH}: {e}",
                  file=sys.stderr, flush=True)
    if name and source and source.endswith(".py"):
        comment_out_rule(source, name, seconds)
    return rec


def comment_out_rule(path: str, name: str, seconds: float) -> bool:
    """Comment out `name = re.compile(...)` in a generated rule file.

    Makes the quarantine persist: the next process never compiles it. Only
    touches module-level assignments to `name`, and stops at the first
    balanced-paren end so the following rules are untouched. Returns True if
    the file was modified.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except Exception:
        return False
    lines = text.splitlines(keepends=True)

    # Locate the assignment with Python's own parser: counting parentheses in
    # the source miscounts the ones inside regex strings (\(, [^)]), which can
    # comment out the rest of the file or cut a pattern in half.
    import ast
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    span = None
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name
                and isinstance(node.value, ast.Call)
                and getattr(node.value.func, "attr", None) == "compile"):
            span = (node.lineno - 1, node.end_lineno - 1)
            break
    if span is None:
        return False
    start, end = span

    # Rebind to a pattern that can never match, rather than deleting the name.
    # Commenting the assignment out leaves every USE of it — `for m in
    # NAME.finditer(...)` — referencing an undefined name, so the whole module
    # dies with NameError on the next import and the group is lost entirely.
    # That is the same "one bad rule kills the group" failure this is meant to
    # prevent. `(?!x)x` is unsatisfiable, so the rule is inert but the file
    # still runs and every other rule keeps working.
    indent = lines[start][:len(lines[start]) - len(lines[start].lstrip())]
    marker = (f"{indent}# PRUNED-SLOW: {seconds:.1f}s on one document exceeded "
              f"the rule_guard budget. Disabled by rebinding to a "
              f"never-matching pattern; original preserved below.\n")
    disabled = f"{indent}{name} = re.compile(r'(?!x)x')  # PRUNED-SLOW\n"
    lines[start:end + 1] = ([marker, disabled]
                            + [f"{indent}# " + l.lstrip("\n") if l.strip() else l
                               for l in lines[start:end + 1]])
    try:
        # write a sibling file and rename it over the original: a reader never
        # sees a half-written file, and a symlinked rule file is replaced at
        # its target, not turned into a regular file
        real = os.path.realpath(path)
        tmp = f"{real}.tmp{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        os.replace(tmp, real)
        print(f"[SLOW-RULE] commented out {name} in {path}",
              file=sys.stderr, flush=True)
        return True
    except Exception:
        return False


class GuardedPattern:
    """A compiled regex that disables itself if one match blows the budget."""

    __slots__ = ("_pat", "_name", "_source", "_budgeted")

    def __init__(self, pattern, name=None, source=None, budgeted=False):
        object.__setattr__(self, "_pat", pattern)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_source", source)
        # Cumulative budgets apply ONLY to named patterns from generated rule
        # files. Applied globally they are actively harmful: a hot, healthy
        # pattern like `\s+` runs hundreds of thousands of times at
        # microseconds each, crosses any total-time budget, and gets disabled
        # forever -- taking the LaTeX cleaner and tokenizer with it. That is
        # not hypothetical. It quarantined `\s+` mid-run, after which nothing
        # could match gold and every score from that point on was 0.000.
        # The more useful a pattern is, the faster it would trip. Only the
        # per-call cap is safe to apply everywhere.
        object.__setattr__(self, "_budgeted", budgeted)

    # -- the fast front end (see "Speed-ups") ------------------------------
    def _run(self, meth_name, args, kwargs):
        pat = self._pat
        if _FAST and isinstance(pat, re.Pattern) and meth_name not in ("sub", "subn", "split") \
                and (pat.pattern, pat.flags) not in _QUARANTINED:
            if pat.pattern == _SENTINEL:
                return _EMPTY[meth_name]()
            text = args[0] if args else None
            if len(args) == 1 and not kwargs and isinstance(text, str):
                if meth_name in ("findall", "search"):
                    key = (meth_name, pat.pattern, pat.flags, text)
                    if key in _MEMO:
                        return _MEMO[key]
                    if not _may_match(pat, text):
                        res = _EMPTY[meth_name]()
                    else:
                        ms = _anchored_matches(pat, text)
                        if ms is None:
                            res = self._run_timed(meth_name, args, kwargs)
                        elif meth_name == "search":
                            res = ms[0] if ms else None
                        else:
                            res = [_findall_item(pat, m) for m in ms]
                    _MEMO[key] = res
                    return res
                if not _may_match(pat, text):
                    return _EMPTY[meth_name]()
        return self._run_timed(meth_name, args, kwargs)

    def finditer(self, *args, **kwargs):
        """Matches as an iterator; whole-text calls take the fast front end."""
        pat = self._pat
        text = args[0] if args else None
        if _FAST and isinstance(pat, re.Pattern) and (pat.pattern, pat.flags) not in _QUARANTINED:
            if pat.pattern == _SENTINEL:
                return iter(())
            if len(args) == 1 and not kwargs and isinstance(text, str):
                key = ("finditer", pat.pattern, pat.flags, text)
                hit = _MEMO.get(key)
                if hit is not None:
                    return iter(hit)
                if not _may_match(pat, text):
                    return iter(())
                ms = _anchored_matches(pat, text)
                if ms is not None:
                    _MEMO[key] = ms
                    return iter(ms)
                return _memo_iter(key, self._finditer_timed(*args, **kwargs))
        return self._finditer_timed(*args, **kwargs)

    # -- the timed call ---------------------------------------------------
    def _run_timed(self, meth_name, args, kwargs):
        pat = self._pat
        key = (pat.pattern, pat.flags)
        text = args[0] if args else ""
        if key in _QUARANTINED:
            if meth_name in ("sub", "subn"):
                return (text, 0) if meth_name == "subn" else text
            return _EMPTY[meth_name]()

        meth = getattr(pat, meth_name)
        use_alarm = (threading.current_thread() is threading.main_thread()
                     and _THRESHOLD > 0)

        def _on_alarm(signum, frame):
            raise _RegexTimeout()

        old = signal.signal(signal.SIGALRM, _on_alarm) if use_alarm else None
        if use_alarm:
            signal.setitimer(signal.ITIMER_REAL, _THRESHOLD)
        t0 = time.perf_counter()
        try:
            return meth(*args, **kwargs)
        except _RegexTimeout:
            _record(pat, self._name, self._source, _THRESHOLD,
                    len(text) if isinstance(text, str) else 0)
            if meth_name in ("sub", "subn"):
                return (text, 0) if meth_name == "subn" else text
            return _EMPTY[meth_name]()
        finally:
            if use_alarm:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old)
            # Off-thread (or under a caller that swallowed the alarm) the call
            # is not interruptible, but it still gets quarantined afterwards so
            # the cost is paid at most once.
            el = time.perf_counter() - t0
            if el > _THRESHOLD:
                _record(pat, self._name, self._source, el,
                        len(text) if isinstance(text, str) else 0)
            elif (self._budgeted and _BUDGET > 0
                  and key not in _QUARANTINED):
                # Death by a thousand cuts: no single call is slow, but the
                # pattern is called tens of thousands of times per document.
                acc = _SPENT.setdefault(key, [0.0, 0])
                acc[0] += el
                acc[1] += 1
                if acc[0] > _BUDGET and acc[0] / acc[1] >= MIN_MEAN_SECONDS:
                    _record(pat, self._name, self._source, acc[0],
                            len(text) if isinstance(text, str) else 0,
                            reason=f"cumulative over {acc[1]} calls")

    def _finditer_timed(self, *args, **kwargs):
        """Lazy — so the guard must wrap the ITERATOR, not its creation.

        `finditer` returns immediately and does the matching during iteration.
        Timing the call therefore measures nothing, and a runaway pattern used
        as `for m in PAT.finditer(text)` sails straight past a guard that only
        wraps the call. This was not hypothetical: it is why the first version
        of this module still let a document hang for minutes.
        """
        pat = self._pat
        key = (pat.pattern, pat.flags)
        text = args[0] if args else ""
        tlen = len(text) if isinstance(text, str) else 0
        if key in _QUARANTINED:
            return
        it = pat.finditer(*args, **kwargs)
        acc = _SPENT.setdefault(key, [0.0, 0])
        while True:
            if key in _QUARANTINED:
                return
            use_alarm = (threading.current_thread() is threading.main_thread()
                         and _THRESHOLD > 0)

            def _on_alarm(signum, frame):
                raise _RegexTimeout()

            old_h = signal.signal(signal.SIGALRM, _on_alarm) if use_alarm else None
            if use_alarm:
                signal.setitimer(signal.ITIMER_REAL, _THRESHOLD)
            t0 = time.perf_counter()
            try:
                m = next(it)
            except StopIteration:
                return
            except _RegexTimeout:
                _record(pat, self._name, self._source, _THRESHOLD, tlen)
                return
            finally:
                if use_alarm:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    signal.signal(signal.SIGALRM, old_h)
                acc[0] += time.perf_counter() - t0
                acc[1] += 1
            if (self._budgeted and _BUDGET > 0 and acc[0] > _BUDGET
                    and acc[0] / acc[1] >= MIN_MEAN_SECONDS):
                _record(pat, self._name, self._source, acc[0], tlen,
                        reason=f"cumulative over {acc[1]} calls")
                return
            yield m

    def __getattr__(self, item):
        return getattr(self._pat, item)


def _make(meth_name):
    def _m(self, *args, **kwargs):
        return self._run(meth_name, args, kwargs)
    _m.__name__ = meth_name
    return _m


for _n in ("search", "match", "fullmatch", "findall", "sub",
           "subn", "split"):          # finditer is defined explicitly above
    setattr(GuardedPattern, _n, _make(_n))


def guard_module(module, source_path=None) -> int:
    """Wrap every module-level compiled pattern in `module`. Returns the count.

    Named patterns are the ones a generated rule file exposes and the ones
    `rule_name` in the prune step keys off, so quarantining them can name the
    culprit and comment it out at source.
    """
    n = 0
    src = source_path or getattr(module, "__file__", None)
    swapped = {}                       # id(object replaced) -> (object, [its wrappers])
    for attr in dir(module):
        if attr.startswith("__"):
            continue
        try:
            val = getattr(module, attr)
        except Exception:
            continue
        if isinstance(val, re.Pattern):
            g = GuardedPattern(val, name=attr, source=src, budgeted=True)
            setattr(module, attr, g)
            swapped.setdefault(id(val), (val, []))[1].append(g)
            n += 1
        elif isinstance(val, GuardedPattern) and val._name is None:
            # install_global already wrapped it at compile time, but anonymously.
            # Re-wrap with the module-level variable name so a quarantine record
            # can name the culprit and comment out the right block at source.
            g = GuardedPattern(val._pat, name=attr, source=src, budgeted=True)
            setattr(module, attr, g)
            swapped.setdefault(id(val), (val, []))[1].append(g)
            n += 1
    if swapped:
        _alias_pattern_tables(module, swapped)
    return n


def _alias_pattern_tables(module, swapped: dict) -> None:
    """Keep module-level tables keyed by a pattern working after the swap.

    A generated rule file may build, at import, a dict keyed by its patterns
    or by their id() (`{id(REMARK_ENV_RE): 'REMARK_ENV_RE'}`) and look a pattern
    up in it at match time. guard_module runs after the import and replaces
    each module-level pattern with a wrapper, so the lookup then gets the
    wrapper and raises KeyError, and the parser drops the whole group (every
    remark, example and assumption rule of a run, on any paper where one of
    them matched). Each such key gets its wrapper(s) as further keys (one
    compiled object can stand behind several names: re caches identical
    patterns, e.g. the never-matching pattern every pruned rule is rebound to)."""
    for attr in dir(module):
        if attr.startswith("__"):
            continue
        try:
            table = getattr(module, attr)
        except Exception:
            continue
        if not isinstance(table, dict):
            continue
        extra = {}
        for k, v in list(table.items()):
            if isinstance(k, int) and not isinstance(k, bool) and k in swapped:
                for g in swapped[k][1]:
                    extra[id(g)] = v
            elif isinstance(k, (re.Pattern, GuardedPattern)) and id(k) in swapped \
                    and swapped[id(k)][0] is k:
                for g in swapped[id(k)][1]:
                    extra[g] = v
        if extra:
            table.update(extra)


_ORIG_COMPILE = re.compile


_ORIG_FUNCS = {}


# position of `flags` among each re.<function>'s arguments after the pattern
_FLAGS_AT = {"search": 1, "match": 1, "fullmatch": 1, "findall": 1, "finditer": 1,
             "sub": 3, "subn": 3, "split": 2}


def install_global(threshold=None, log_path=None, budget=None):
    """Guard EVERY regex in this process — compiled, inline, or module-level.

    Two entry points must be covered, and covering only one is why the first
    version of this let a runaway through:

    * ``re.compile(...)`` then ``.search(...)`` — the module-level style
    * ``re.search(pattern_string, text)`` — the convenience functions, which
      go through ``re._compile`` internally and therefore NEVER touch
      ``re.compile``. Generated rule files use this style freely (11 such
      calls in one definition file alone).

    Patching the convenience functions rather than ``re._compile`` keeps
    ``isinstance(x, re.Pattern)`` working everywhere, which wrapping the
    internal cache would quietly break. Idempotent.
    """
    configure(threshold=threshold, log_path=log_path, budget=budget)
    if getattr(re.compile, "_rule_guard", False):
        return

    def _guarded_compile(pattern, flags=0):
        compiled = _ORIG_COMPILE(pattern, flags)
        if isinstance(pattern, (str, bytes)):
            return GuardedPattern(compiled, name=None, source="<inline>")
        return compiled

    _guarded_compile._rule_guard = True
    re.compile = _guarded_compile

    def _make_func(fname):
        orig = getattr(re, fname)
        _ORIG_FUNCS[fname] = orig

        def _f(pattern, *args, **kwargs):
            # re.<fname>(pattern, ..., flags): flags may come by position. The
            # pattern METHODS take a start position there instead (pos for
            # search, count for sub, maxsplit for split), so a positional flag
            # must be taken out here, never forwarded: forwarded, re.I silently
            # became "start at character 2" and the flag was lost.
            k = _FLAGS_AT[fname]
            if len(args) > k:
                if "flags" in kwargs:
                    raise TypeError(f"{fname}() got multiple values for argument 'flags'")
                kwargs["flags"], args = args[k], args[:k]
            if isinstance(pattern, GuardedPattern):
                if kwargs.pop("flags", 0):
                    raise ValueError("cannot process flags argument with a compiled pattern")
                return getattr(pattern, fname)(*args, **kwargs)
            flags = kwargs.pop("flags", 0)
            try:
                gp = GuardedPattern(_ORIG_COMPILE(pattern, flags),
                                    name=None, source="<inline>")
            except Exception:
                return orig(pattern, *args, flags=flags, **kwargs)
            return getattr(gp, fname)(*args, **kwargs)

        _f.__name__ = fname
        return _f

    for _fn in _FLAGS_AT:
        setattr(re, _fn, _make_func(_fn))


def uninstall_global():
    re.compile = _ORIG_COMPILE
    for k, v in _ORIG_FUNCS.items():
        setattr(re, k, v)
    _ORIG_FUNCS.clear()
