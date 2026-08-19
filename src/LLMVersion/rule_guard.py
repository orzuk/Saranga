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
            lines = fh.readlines()
    except Exception:
        return False

    start = None
    for i, ln in enumerate(lines):
        if re.match(rf"\s*{re.escape(name)}\s*=\s*re\.compile", ln):
            start = i
            break
    if start is None or lines[start].lstrip().startswith("#"):
        return False

    depth, end = 0, start
    for i in range(start, len(lines)):
        depth += lines[i].count("(") - lines[i].count(")")
        end = i
        if depth <= 0:
            break

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
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
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

    # -- the timed call ---------------------------------------------------
    def _run(self, meth_name, args, kwargs):
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

    def finditer(self, *args, **kwargs):
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
    for attr in dir(module):
        if attr.startswith("__"):
            continue
        try:
            val = getattr(module, attr)
        except Exception:
            continue
        if isinstance(val, re.Pattern):
            setattr(module, attr,
                    GuardedPattern(val, name=attr, source=src, budgeted=True))
            n += 1
        elif isinstance(val, GuardedPattern) and val._name is None:
            # install_global already wrapped it at compile time, but anonymously.
            # Re-wrap with the module-level variable name so a quarantine record
            # can name the culprit and comment out the right block at source.
            setattr(module, attr,
                    GuardedPattern(val._pat, name=attr, source=src,
                                   budgeted=True))
            n += 1
    return n


_ORIG_COMPILE = re.compile


_ORIG_FUNCS = {}


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
            if isinstance(pattern, GuardedPattern):
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

    for _fn in ("search", "match", "fullmatch", "findall", "finditer",
                "sub", "subn", "split"):
        setattr(re, _fn, _make_func(_fn))


def uninstall_global():
    re.compile = _ORIG_COMPILE
    for k, v in _ORIG_FUNCS.items():
        setattr(re, k, v)
    _ORIG_FUNCS.clear()
