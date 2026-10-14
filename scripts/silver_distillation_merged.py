#!/usr/bin/env python3
"""
Silver Standard MERGED Distillation (single pass, all structure types)
======================================================================
A cost-reduced sibling of ``silver_distillation_sequential.py``.  Instead of
re-running the whole pipeline once per structure type, this distills *all*
requested types in ONE pass per paper.  Two levers cut LLM calls and tokens:

  1. Types are grouped by the base parser method they share, so the 7
     theorem-like types (theorem/lemma/proposition/corollary/claim/conjecture/
     problem) collapse to ONE "theoremlike" track.  Aggregate calls drop from
     up to 9/paper to 3/paper, and the shared base-method context is sent once
     per group, not once per type.
  2. The analyze step batches B missed structures per LLM call (not 1) and marks
     the static base-method source with ``cache_control`` so it bills at the
     cache-read rate on every batch + the aggregate within a paper.

Each base-method group keeps its OWN self-contained ``distilled_rules.py`` under
``<eval_dir>/groups/<group>/`` (so the existing per-group prune works unchanged).
A thin, hand-authored importer ``<eval_dir>/distilled_rules.py`` re-exports a
per-type ``extract_distilled_<type>`` for every type plus ``extract_distilled_all``
so the parser dispatch (``_apply_distilled_rules``) is untouched.

Usage:
    python scripts/silver_distillation_merged.py \
        --structure-types definition,theorem,lemma,proof \
        --pilot-papers paper001,paper005 \
        --t2-dir portal/data/tier2 \
        --tex-dir /path/to/alignment/papers \
        --eval-dir src/LLMVersion/merged_eval_silver \
        --model claude-sonnet-4-6 \
        --batch-size 8
"""

import argparse
import ast
import builtins as _builtins
import contextlib
import csv
import json
import re
import os
import shutil
import signal
import sys
import time
from pathlib import Path

# Names always available without definition (builtins + dunders).
_SAFE_NAMES = set(dir(_builtins)) | {"__name__", "__file__", "__doc__", "__builtins__"}

# Add src/LLMVersion to path for imports
REPO = Path(__file__).resolve().parent.parent
LLM_DIR = REPO / "src" / "LLMVersion"
sys.path.insert(0, str(LLM_DIR))
sys.path.insert(0, str(REPO / "src"))

import distillation_analysis as _da
from distillation_analysis import (
    base_method_groups,
    identify_dark_knowledge,
    analyze_patterns_batched,
    aggregate_rules_merged,
    prune_rules,
)

# Reuse the proven helpers + the cleaned matcher from the per-type pipeline.
import silver_distillation_sequential as seq
from silver_distillation_sequential import (
    FNAME_MAP,
    convert_t2_to_gold_csv,
    _find_main_tex,
    count_compiled_patterns,
    jaccard_similarity,
)

ALL_SILVER_TYPES = list(FNAME_MAP.keys())

from distillation_analysis import estimate_cost   # noqa: E402  (single pricing table)


# ---------------------------------------------------------------------------
# Generated-code guard: validate + auto-repair each group's distilled_rules.py
# right after the aggregate LLM writes it, so one bad codegen can't abort the
# whole multi-paper run. Catches the common failure class (undefined name that
# only differs by case from a defined global, e.g. `_referential` vs
# `_REFERENTIAL`), repairs it with an alias, and otherwise falls back to the
# previous good file (or a safe empty stub). This touches only the generated
# ARTIFACT, never the LLM prompt.
# ---------------------------------------------------------------------------

def _target_names(t) -> set:
    out = set()
    if isinstance(t, ast.Name):
        out.add(t.id)
    elif isinstance(t, (ast.Tuple, ast.List)):
        for e in t.elts:
            out |= _target_names(e)
    elif isinstance(t, ast.Starred):
        out |= _target_names(t.value)
    return out


def _scan_names(tree) -> tuple:
    """Return (module_top_bound, all_bound, loads) for a parsed module.

    `all_bound` over-approximates definitions (a name bound in ANY scope counts
    as defined everywhere) so we never flag a real binding as undefined; that
    keeps the repair conservative. `module_top_bound` is used as the alias
    source, since helper globals live at module level.
    """
    module_top = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_top.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                module_top.add((a.asname or a.name).split('.')[0])
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                module_top |= _target_names(t)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            module_top |= _target_names(node.target)

    bound, loads = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            if not isinstance(node, ast.Lambda):
                bound.add(node.name)
            a = node.args
            for arg in (list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)):
                bound.add(arg.arg)
            if a.vararg:
                bound.add(a.vararg.arg)
            if a.kwarg:
                bound.add(a.kwarg.arg)
        elif isinstance(node, ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for al in node.names:
                bound.add((al.asname or al.name).split('.')[0])
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                bound |= _target_names(t)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            bound |= _target_names(node.target)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            bound |= _target_names(node.target)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for it in node.items:
                if it.optional_vars:
                    bound |= _target_names(it.optional_vars)
        elif isinstance(node, ast.comprehension):
            bound |= _target_names(node.target)
        elif isinstance(node, ast.NamedExpr):
            bound |= _target_names(node.target)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                bound.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loads.add(node.id)
    return module_top, bound, loads


class _RuleTimeout(Exception):
    pass


def _run_with_timeout(fn, arg, seconds: float):
    """Run fn(arg) but abort with _RuleTimeout if it exceeds `seconds`.

    Uses SIGALRM (main thread, Unix) — the merged pipeline is single-threaded,
    so this safely interrupts a catastrophically-backtracking regex.
    """
    def _handler(signum, frame):
        raise _RuleTimeout()

    old = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return fn(arg)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


_SHARED_CLEANER_SHIM = '''
# --- injected by validate_and_repair_group_file -----------------------------
# The generated `_clean_latex` is replaced by a delegate to the ONE shared
# cleaner. Every codegen wrote its own, and they masked math as the literal
# token `[MATH]` while the base parser preserves math as words. Containment
# between two *identical* theorem statements cleaned by the two functions
# measured 0.44 -- under the 0.7 dedup bar -- so identical statements survived
# as duplicate nodes. `latex_clean` already declares itself the single cleaner
# for "the base regex parser AND all distilled-rule extractors"; this makes
# that true. Call sites are untouched: only the body changes.
try:
    from latex_clean import clean_latex_to_text as _shared_clean_latex
except Exception:                                    # standalone import
    _shared_clean_latex = None


def _clean_latex(text: str) -> str:
    if _shared_clean_latex is not None:
        return _shared_clean_latex(text or "")
    import re as _re                                 # math-preserving fallback
    t = _re.sub(r"%[^\\n]*", "", text or "")
    t = _re.sub(r"\\\\(?:label|ref|cref|Cref|eqref|cite[a-zA-Z]*)\\{[^}]*\\}", "", t)
    t = _re.sub(r"\\\\(?:begin|end)\\{[^}]*\\}", " ", t)
    t = _re.sub(r"[{}$]", "", t)
    return _re.sub(r"\\s+", " ", t).strip()
# ---------------------------------------------------------------------------
'''


def canonicalize_clean_latex(src: str) -> tuple:
    """Point a generated file's `_clean_latex` at the shared cleaner.

    Returns ``(new_src, changed)``. Replaces the module-level `_clean_latex`
    definition (leaving every call site alone) so the file stops inventing its
    own LaTeX normalisation. No-op if the file has no such definition or has
    already been repaired.
    """
    if "_shared_clean_latex" in src:                 # already canonical
        return src, False
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src, False
    node = next((n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == "_clean_latex"),
                None)
    if node is None:
        return src, False
    lines = src.splitlines(keepends=True)
    start = node.lineno - 1
    # include any decorators, and cut to the end of the function body
    for d in getattr(node, "decorator_list", []):
        start = min(start, d.lineno - 1)
    end = node.end_lineno
    new = "".join(lines[:start]) + _SHARED_CLEANER_SHIM + "".join(lines[end:])
    try:
        ast.parse(new)
    except SyntaxError:
        return src, False
    return new, True


def validate_and_repair_group_file(path: Path, gkey: str, prev_src,
                                   probe_text: str = "", timeout_s: float = 30.0,
                                   max_rule_seconds: float = 10.0) -> str:
    """Make `path` safe to import+run, or fall back. Returns the action taken:
    'ok' | 'aliased' | 'reverted' | 'stubbed' | 'slow→...'.

    `probe_text` (real LaTeX from the papers seen so far) is run through the
    entry point under a `timeout_s` wall-clock limit, so a regex that is valid
    Python but catastrophically backtracks on real input is caught here and
    reverted — before it can hang the prune/parse steps.

    On a timeout the SLOW PATTERNS ARE PRUNED INDIVIDUALLY before any
    whole-file fallback is considered. This guard can only run the composed
    entry point, so it cannot tell which of N suggestions is the slow one —
    and discarding all of them is a heavy price for one bad regex. Observed
    live: one pattern among 26 definition suggestions timed out, the group had
    no previous file to revert to, and the entire type was replaced with
    ``return []`` — 26 analyzed FNs and a 26.8k-token aggregate call bought
    nothing, silently. ``prune_slow_rules`` already times each pattern
    separately and comments out only the offenders; it just ran too late, in
    step 5, by which point this function had already stubbed the file.
    """
    fn_name = f"extract_distilled_{gkey}"

    def _restore() -> str:
        if prev_src is not None:
            path.write_text(prev_src, encoding='utf-8')
            return 'reverted'
        path.write_text(f"def {fn_name}(text):\n    return []\n", encoding='utf-8')
        return 'stubbed'

    try:
        src = path.read_text(encoding='utf-8')
    except Exception:
        return _restore()

    # Route the file's LaTeX cleaning through the shared cleaner before any
    # other check, so a freshly generated file never ships its own normaliser.
    src, _cleaned = canonicalize_clean_latex(src)
    if _cleaned:
        path.write_text(src, encoding='utf-8')
        print("      [repair] _clean_latex -> shared latex_clean.clean_latex_to_text")

    try:
        tree = ast.parse(src)
    except SyntaxError:
        return _restore()

    module_top, bound, loads = _scan_names(tree)
    undefined = loads - bound - _SAFE_NAMES

    action = 'ok'
    if undefined:
        lower_map = {}
        for n in module_top:
            lower_map.setdefault(n.lower(), n)
        aliases, unfixable = [], []
        for u in sorted(undefined):
            m = lower_map.get(u.lower())
            if m and m != u:
                aliases.append((u, m))
            else:
                unfixable.append(u)
        if unfixable:
            return _restore()
        src = (src + "\n\n# --- auto-repair: alias case-mismatched globals ---\n"
               + "\n".join(f"{u} = {m}" for u, m in aliases) + "\n")
        path.write_text(src, encoding='utf-8')
        try:
            _, b2, l2 = _scan_names(ast.parse(src))
        except SyntaxError:
            return _restore()
        if l2 - b2 - _SAFE_NAMES:
            return _restore()
        action = 'aliased'

    # Final smoke test: import the module + call the entry point on empty input.
    ns = {'__name__': 'distilled_smoke'}
    try:
        exec(compile(src, str(path), 'exec'), ns)
        fn = ns.get(fn_name)
        if not callable(fn):
            return _restore()
        # The return value matters, not just that it is callable. A truncated
        # generated file loses its trailing `return results`, so the function
        # falls off the end and returns None -- and the parser's
        # `if not raw_results: return []` reads that as "found nothing".
        # definition died this way for 8 consecutive papers while every guard
        # reported success. Anything that is not a list is a broken file.
        _probe = fn("")
        if not isinstance(_probe, list):
            print(f"      [guard] {fn_name} returned {type(_probe).__name__}, "
                  f"expected list — file is incomplete (truncated?)")
            return _restore()
    except Exception:
        return _restore()

    # Timed run on real text: reject catastrophically-backtracking regexes.
    if probe_text:
        try:
            _run_with_timeout(fn, probe_text, timeout_s)
        except _RuleTimeout:
            # Surgery before amputation: comment out the individual patterns
            # that are slow, then retry. Only if the file is STILL too slow
            # with every offender removed do we fall back to the whole-file
            # revert/stub.
            try:
                from distillation_analysis import prune_slow_rules
                slow = prune_slow_rules(str(path), {"_probe": probe_text},
                                        max_rule_seconds)
            except Exception as e:
                print(f"      [guard] per-pattern prune failed: {e}")
                slow = {}
            if slow:
                print(f"      [guard] slow: pruned {len(slow)} pattern(s) "
                      f"individually ({', '.join(sorted(slow)[:5])}"
                      f"{'...' if len(slow) > 5 else ''}) — keeping the rest")
                try:
                    src2 = path.read_text(encoding='utf-8')
                    ns2 = {'__name__': 'distilled_smoke_retry'}
                    exec(compile(src2, str(path), 'exec'), ns2)
                    fn2 = ns2.get(fn_name)
                    if callable(fn2):
                        _run_with_timeout(fn2, probe_text, timeout_s)
                        return f"slow→pruned {len(slow)}"
                except _RuleTimeout:
                    print("      [guard] still slow after per-pattern prune")
                except Exception as e:
                    print(f"      [guard] retry failed to import: {e}")
            return f"slow→{_restore()}"
        except Exception:
            return _restore()
    return action


# ---------------------------------------------------------------------------
# Combined importer (hand-authored — no codegen risk)
# ---------------------------------------------------------------------------

def snapshot_dirs(eval_dir: Path) -> list:
    """<eval_dir>/snapshots/step_NN_* in step order (numeric: step_100 after step_99)."""
    def step(p):
        m = re.match(r"step_(\d+)", p.name)
        return int(m.group(1)) if m else -1
    return sorted((Path(eval_dir) / "snapshots").glob("step_*"), key=step)


def write_combined_importer(eval_dir: Path, groups: dict) -> Path:
    """Write <eval_dir>/distilled_rules.py re-exporting per-type entry points.

    `groups` maps group_key -> [types]. The importer loads each group's
    self-contained module by a path RELATIVE to the importer file itself
    (resolved at runtime via realpath(__file__)) -- so it works on any
    machine and no matter which {type}_eval/ dir it gets symlinked into
    (realpath follows the symlink back to this snapshot's groups/ dir).
    Exposes, for every type, an extract_distilled_<type>(text) that filters
    the group's output by structure_type. Missing group files degrade to [].
    """
    group_files = {
        gkey: f"groups/{gkey}/distilled_rules.py"
        for gkey in groups
    }
    type_to_group = {t: gkey for gkey, types in groups.items() for t in types}

    lines = [
        "# AUTO-GENERATED combined distilled-rules importer (silver merged",
        "# distillation). Re-exports per-type entry points from per-group rule",
        "# modules so the parser dispatch (_apply_distilled_rules ->",
        "# extract_distilled_<type>) works unchanged. This file holds NO patterns,",
        "# so the prune step (which edits the per-group files) never touches it.",
        "import importlib.util as _ilu",
        "import os as _os",
        "",
        "# Group files are stored relative to this importer; resolve against",
        "# its real location so it works through symlinks and across machines.",
        "_HERE = _os.path.dirname(_os.path.realpath(__file__))",
        "",
        f"_GROUP_FILES = {json.dumps(group_files, indent=4)}",
        "",
        f"_TYPE_TO_GROUP = {json.dumps(type_to_group, indent=4)}",
        "",
        "",
        "_LOADED = {}",
        "",
        "",
        "def _load_group(gkey):",
        "    # loaded once per process, and its patterns put under rule_guard by name,",
        "    # so a slow rule is quarantined in ITS file (the importer holds none)",
        "    if gkey in _LOADED:",
        "        return _LOADED[gkey]",
        "    _LOADED[gkey] = None",
        "    rel = _GROUP_FILES.get(gkey)",
        "    if not rel:",
        "        return None",
        "    path = _os.path.join(_HERE, rel)",
        "    if not _os.path.isfile(path):",
        "        return None",
        "    try:",
        "        spec = _ilu.spec_from_file_location('distilled_group_' + gkey, path)",
        "        m = _ilu.module_from_spec(spec)",
        "        spec.loader.exec_module(m)",
        "    except Exception as e:",
        "        print(f'[WARN] distilled group {gkey} failed to load: {type(e).__name__}: {e}')",
        "        return None",
        "    try:",
        "        import rule_guard",
        "        rule_guard.guard_module(m, source_path=path)",
        "    except Exception:",
        "        pass",
        "    _LOADED[gkey] = m",
        "    return m",
        "",
        "",
        "def _extract_group(gkey, text):",
        "    m = _load_group(gkey)",
        "    if m is None:",
        "        return []",
        "    fn = getattr(m, 'extract_distilled_' + gkey, None)",
        "    if fn is None:",
        "        return []",
        "    try:",
        "        return fn(text) or []",
        "    except Exception as e:",
        "        print(f'[WARN] distilled group {gkey} raised {type(e).__name__}: {e}')",
        "        return []",
        "",
        "",
        "def extract_distilled_all(text):",
        "    out = []",
        "    for gkey in _GROUP_FILES:",
        "        out.extend(_extract_group(gkey, text))",
        "    return out",
        "",
    ]

    # Per-type entry points.
    for t, gkey in type_to_group.items():
        if len([x for x in type_to_group.values() if x == gkey]) == 1:
            # Single-type group: the group function IS this type; re-export whole.
            lines += [
                "",
                f"def extract_distilled_{t}(text):",
                f"    return _extract_group({gkey!r}, text)",
            ]
        else:
            # Multi-type (theoremlike): filter by structure_type.
            lines += [
                "",
                f"def extract_distilled_{t}(text):",
                f"    return [d for d in _extract_group({gkey!r}, text)",
                f"            if d.get('structure_type') == {t!r}]",
            ]
    lines.append("")

    eval_dir.mkdir(parents=True, exist_ok=True)
    out = eval_dir / "distilled_rules.py"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Install / uninstall the combined importer across all involved type dirs
# ---------------------------------------------------------------------------

#: Depth of the current install. Not a lock — it cannot see other processes —
#: but it catches the failure that actually happened: a nested/concurrent
#: install inside one process tree.
_INSTALL_DEPTH = 0


class NestedInstallError(RuntimeError):
    """Raised instead of silently destroying the backup of an outer install."""


#: Cross-process guard. The depth counter above only sees one process, and the
#: corruption that motivated all this was FOUR processes installing at once.
INSTALL_LOCK = REPO / "src" / "LLMVersion" / ".silver_install.lock"


def _acquire_install_lock() -> None:
    """O_EXCL lock around the shared rule symlinks. One installer at a time.

    A stale lock from a killed run is reclaimed: the holder's pid is written
    into the file, and if that process is gone the lock is not real. Without
    that, one SIGKILL would wedge every future run.
    """
    global _LOCK_HELD
    for _ in range(2):
        try:
            fd = os.open(INSTALL_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            _LOCK_HELD = True
            return
        except FileExistsError:
            try:
                holder = int(INSTALL_LOCK.read_text().strip() or 0)
            except (ValueError, OSError):
                holder = 0
            alive = False
            if holder:
                try:
                    os.kill(holder, 0)
                    alive = True
                except OSError:
                    alive = False
            if alive:
                raise NestedInstallError(
                    f"another process (pid {holder}) is installing rules into "
                    f"src/LLMVersion/*_eval/. Concurrent installs overwrite "
                    f"each other's .silver_bak and destroy the originals. "
                    f"Wait for it, or kill it and remove {INSTALL_LOCK}.")
            print(f"  [lock] reclaiming stale install lock from dead pid {holder}")
            INSTALL_LOCK.unlink(missing_ok=True)
    raise NestedInstallError(f"could not acquire {INSTALL_LOCK}")


def _release_install_lock() -> None:
    global _LOCK_HELD
    if _LOCK_HELD:
        INSTALL_LOCK.unlink(missing_ok=True)
        _LOCK_HELD = False


_LOCK_HELD = False


def install_importer(eval_dir: Path, types) -> dict:
    """Symlink <eval_dir>/distilled_rules.py into every {type}_eval/ dir.

    Returns {type: backup_path_or_None} for restoration. Reuses the per-type
    installer so sys.modules cache invalidation stays consistent.

    Refuses to nest. `_install_silver_rules` renames the CURRENT
    src/LLMVersion/<type>_eval/distilled_rules.py to .silver_bak; a second
    install while one is active therefore renames the first install's symlink
    over the original file's backup, and the original is gone for good. That is
    not hypothetical — it destroyed all 14 production rule symlinks once, and
    they were only recoverable because git tracked them. Failing loudly here is
    much cheaper than discovering it afterwards.
    """
    global _INSTALL_DEPTH
    if _INSTALL_DEPTH > 0:
        raise NestedInstallError(
            "install_importer called while an install is already active in "
            "this process. The outer install's backup would be overwritten "
            "and the original rule files lost. Parse many papers under ONE "
            "installed_rules() block (see parse_all) instead of installing "
            "per paper.")
    _acquire_install_lock()
    try:
        backups = {}
        for t in types:
            _, backup = seq._install_silver_rules(eval_dir, t)
            backups[t] = backup
    except BaseException:
        _release_install_lock()
        raise
    _INSTALL_DEPTH += 1
    return backups


def uninstall_importer(types, backups: dict) -> None:
    global _INSTALL_DEPTH
    try:
        for t in types:
            seq._uninstall_silver_rules(t, backups.get(t))
    finally:
        _INSTALL_DEPTH = max(0, _INSTALL_DEPTH - 1)
        _release_install_lock()


# ---------------------------------------------------------------------------
# Per-step rule snapshots (for the paper-by-paper graph filmstrip)
# ---------------------------------------------------------------------------

SILVER_METADATA = REPO / "corpus" / "silver" / "metadata.csv"


def load_splits(metadata_csv: Path = SILVER_METADATA) -> dict:
    """{paper_id: split} from the silver corpus index — the one source of truth.

    The split lives in metadata.csv, not in the directory tree, precisely so it
    can be redrawn. Everything that selects papers should consult it rather than
    hardcoding lists.
    """
    # A paper has ONE row per extraction, so every train/test paper ALSO has a
    # `pool` row (its older v3 extraction). Taking the first row seen would
    # label the whole train set "pool" and silently defeat the split guard, so
    # the specific splits win over the catch-all.
    precedence = {"train": 3, "test": 3, "val": 3, "pool": 1}
    out, rank = {}, {}
    if not Path(metadata_csv).exists():
        return out
    with open(metadata_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # metadata.csv names papers by paper_id, a split file (split_v6.csv) by arxiv_id
            pid, split = row.get("paper_id") or row.get("arxiv_id"), row.get("split")
            if not (pid and split):
                continue
            r = precedence.get(split, 2)
            if r > rank.get(pid, 0):
                out[pid], rank[pid] = split, r
    return out


def split_file(args) -> Path:
    """Where the train/val/test split is read from: --splits, else the corpus index."""
    if getattr(args, "splits", None):
        return Path(args.splits)
    return Path(args.metadata) if args.metadata else SILVER_METADATA


def assert_no_test_leak(papers, splits: dict) -> None:
    """Refuse to distil on anything the corpus marks as test.

    Distillation writes rules FROM these papers, so a test paper here is
    training on the test set — it would silently invalidate every held-out
    number we report. Fail loudly rather than warn: a warning in a long run
    scrolls past.
    """
    leaked = [p for p in papers if splits.get(p) == "test"]
    if leaked:
        raise SystemExit(
            f"ABORT: {len(leaked)} test-split paper(s) in the distillation set: "
            f"{', '.join(sorted(leaked))}\n"
            f"Distillation writes rules from these papers; including test "
            f"papers trains on the test set. Fix --pilot-papers, or pass "
            f"--allow-test-papers if you genuinely intend this.")
    unknown = [p for p in papers if p not in splits]
    if unknown:
        print(f"  [split] {len(unknown)} paper(s) not in metadata.csv "
              f"(no split recorded): {', '.join(sorted(unknown)[:5])}"
              f"{' ...' if len(unknown) > 5 else ''}")


def rank_worst_first(papers, tex_dir: Path, types, gold_dir: Path,
                     base_snap: Path, threshold: float,
                     match_mode: str = "m1", cover: float = 0.7,
                     base_buckets: dict | None = None):
    """Order papers by how much the BASE parser misses on them, worst first.

    Hard-example mining (OHEM, Shrivastava et al. 2016) applied to which paper
    to distil next: spend the next LLM call where the current student is
    weakest, rather than in corpus order.

    Ranked by **dark-knowledge count** — gold items the base parser fails to
    account for — not by base F1. F1 is low both when a paper is genuinely rich
    in missable structure AND when it is simply pathological (an ML paper with
    no theorem environments, a broken multi-\\begin{document} file). Ranking on
    raw badness feeds us the pathological ones; dark-knowledge count is the
    actual proxy for recoverable gain, and it is what the loop distils from
    anyway.

    `base_buckets` is the {pid: buckets} PHASE 2 already produced under exactly
    this base snapshot. Pass it. Re-parsing here would repeat that whole pass
    for a second, identical answer — the two phases used to do precisely that.

    Returns [(paper_id, n_missed, n_gold), ...] sorted by n_missed descending.
    """
    import match_modes as _mm
    gold_by_type = {t: load_gold_texts(gold_dir / FNAME_MAP[t]) for t in types}
    scored = []
    for i, pid in enumerate(papers, 1):
        if base_buckets is not None and pid in base_buckets:
            buckets = base_buckets[pid]
        else:
            buckets = parse_buckets(pid, tex_dir, types, eval_dir=base_snap)
        # WITHIN-type on purpose, unlike the prune gate's cross-type support.
        # The two ask opposite questions: the gate asks "is the span I emitted
        # real content anywhere?" (cross-type is right), this asks "must I still
        # learn to extract this?" — and "a proof rule already swallowed it" is
        # not a reason to skip learning the definition. Cross-type here marked
        # 79% of missed items as covered on a 4-paper probe (124 -> 26),
        # including real definitions the parser never extracted AS definitions.
        missed = n_gold = 0
        for t in types:
            gold = gold_by_type[t].get(pid, [])
            n_gold += len(gold)
            for g in gold:
                if not _mm.gold_is_found(g, buckets[t], threshold,
                                         mode=match_mode, cover=cover):
                    missed += 1
        scored.append((pid, missed, n_gold))
        print(f"  [rank {i}/{len(papers)}] {pid}: {missed} missed / {n_gold} gold")
    scored.sort(key=lambda r: (-r[1], r[0]))
    return scored


def baseline_snapshot(eval_dir: Path, groups: dict) -> Path:
    """An always-empty rule snapshot, for measuring the TRUE base parser.

    Do not use ``eval_dir=None`` to mean "baseline". That means "whatever is
    installed", and all 14 production ``*_eval`` dirs are normally symlinked to
    a previous run's FINAL rules — so the "baseline" would silently include
    them, and every new rule would be distilled on top of the last run's output.

    Installing this snapshot instead displaces those symlinks for the duration
    of the parse (``_install_silver_rules`` renames whatever is there to
    ``.silver_bak`` and puts it back afterwards), so the measurement is honest
    and the promoted rules survive the run untouched.

    Kept separate from ``step_00`` because ``step_00`` is written from
    ``groups_dir``, which on ``--resume`` already holds rules.
    """
    snap = eval_dir / "snapshots" / "_baseline"
    for g in groups:
        (snap / "groups" / g).mkdir(parents=True, exist_ok=True)
    write_combined_importer(snap, groups)     # no group files -> extracts nothing
    return snap


def snapshot_rules(eval_dir: Path, groups_dir: Path, groups: dict,
                   step_idx: int, label: str) -> Path:
    """Freeze the current per-group distilled_rules.py into a self-contained
    snapshot dir so paper graphs can later be re-parsed at this exact rule state.

    Layout: <eval_dir>/snapshots/step_<NN>_<label>/{distilled_rules.py, groups/<g>/...}
    The snapshot's importer is written with the snapshot as its base, so it
    points at the FROZEN copies — installing it reproduces this step's rules.
    Copies only (no LLM); cheap and additive.
    """
    snap = eval_dir / "snapshots" / f"step_{step_idx:02d}_{label}"
    (snap / "groups").mkdir(parents=True, exist_ok=True)
    for g in groups:
        src = groups_dir / g / "distilled_rules.py"
        gdst = snap / "groups" / g
        gdst.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, gdst / "distilled_rules.py")
    # Importer pointing at the frozen group files (snap as base dir).
    write_combined_importer(snap, groups)
    return snap


# ---------------------------------------------------------------------------
# Combined parse: one parser run, bucket extracted raw_latex by kind
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def installed_rules(eval_dir: Path | None, types):
    """Install a rule state for the duration of the block, then restore it.

    Split out of parse_buckets so a caller can install ONCE and parse many
    papers under the same state — which is what makes parallel scoring
    possible. The install/restore itself is NOT concurrency-safe (it renames a
    single shared path, src/LLMVersion/<type>_eval/distilled_rules.py, to
    .silver_bak and symlinks over it), so two workers each doing their own
    install would destroy each other's backup even when installing identical
    rules. Hold this once around a fan-out instead; the parse itself only reads.
    """
    backups = install_importer(eval_dir, types) if eval_dir is not None else {}
    try:
        yield
    finally:
        if eval_dir is not None:
            uninstall_importer(types, backups)


def parse_buckets_installed(pid: str, tex_dir: Path, types) -> dict:
    """Parse one paper under the CURRENTLY installed rules. Read-only, so it is
    safe to call concurrently. Use inside an `installed_rules(...)` block."""
    from math_paper_parser import PaperParser

    buckets = {t: [] for t in types}
    src_dir = tex_dir / pid / "source"
    main_tex = _find_main_tex(src_dir)
    if main_tex:
        try:
            parser = PaperParser(paper_id=pid, extraction_mode='rules',
                                 structure_types=list(types))
            graph = parser.parse_file(str(main_tex))
            for _oid, obj in graph.to_dict().get('objects', {}).items():
                kind = obj.get('kind')
                if kind in buckets:
                    raw = obj.get('raw_latex', '') or obj.get('statement', '')
                    if raw.strip():
                        buckets[kind].append(raw)
        except Exception as e:
            print(f"  [warn] parse failed for {pid}: {e}")
    return buckets


_PW = {}


def _pool_init(tex_dir, types):
    _PW["tex"] = Path(tex_dir)
    _PW["types"] = types


def _pool_parse(pid):
    """Child entry point: parses under the rules the PARENT installed.

    Returns its own wall-clock time too: with a pool the parent cannot time
    individual papers, and per-paper parse time is the signal that separates
    "these rules are slow" from "this paper is big" -- the distinction that
    took three stalled runs to see.
    """
    import time as _t
    _t0 = _t.perf_counter()
    b = parse_buckets_installed(pid, _PW["tex"], _PW["types"])
    return pid, b, _t.perf_counter() - _t0


def parse_all(papers, tex_dir: Path, types, eval_dir: Path | None,
              workers: int = 1, label: str = "", timings: dict | None = None) -> dict:
    """Parse MANY papers under ONE rule state. Returns {pid: buckets}.

    The whole point is that the install happens once for the batch rather than
    once per paper. The per-paper install/uninstall (symlink renames plus
    flushing sys.modules) measured *more expensive than the parse itself* —
    2.9x on a 6-paper set — so this is the bigger win, and it needs no
    multiprocessing at all. `workers > 1` fans out on top of that; children
    only read, which is safe precisely because the parent holds the install
    for the duration (see `installed_rules`).

    Results are byte-identical to calling parse_buckets in a loop; verified on
    2,506 extractions across 60 papers with 8 workers.
    """
    papers = list(papers)
    timings.clear() if timings is not None else None
    if not papers:
        return {}
    if label:
        print(f"  [parse] {len(papers)} paper(s) under {label}"
              + (f", {workers} workers" if workers > 1 else ""))
    t_all = time.perf_counter()
    with installed_rules(eval_dir, types):
        if workers > 1 and len(papers) > 1:
            import multiprocessing as _mp
            with _mp.Pool(workers, initializer=_pool_init,
                          initargs=(str(tex_dir), types)) as pool:
                out = {}
                for pid, buckets, secs in pool.map(_pool_parse, papers):
                    out[pid] = buckets
                    if timings is not None:
                        timings[pid] = round(secs, 2)
        else:
            out = {}
            for p in papers:
                t0 = time.perf_counter()
                out[p] = parse_buckets_installed(p, tex_dir, types)
                if timings is not None:
                    timings[p] = round(time.perf_counter() - t0, 2)
    if label and timings:
        wall = time.perf_counter() - t_all
        worst = sorted(timings.items(), key=lambda kv: -kv[1])[:3]
        print(f"  [parse] {wall:.1f}s wall  |  slowest: "
              + ", ".join(f"{k} {v:.1f}s" for k, v in worst))
    return out


def score_state(papers, tex_dir: Path, types, eval_dir: Path | None,
                gold_texts_by_type, threshold: float, *, state: str,
                run_index: int, distilled, pilot_set, out_path: Path,
                workers: int = 1, cover: float = 0.7) -> None:
    """Parse `papers` under the CURRENT rule state, score, append to a JSONL.

    Called from inside the distillation loop so the trajectory table can be a
    pure reader. Doing it here rather than after the fact is not just tidier:
    reconstructing it later means re-installing every snapshot and re-parsing
    every paper, which needs the .tex tree and the snapshots to still exist and
    still agree with the parser — three things that drift. Scoring at the
    moment the state existed is the only way the number is definitely the one
    that state produced.

    Both m1 and m3 are written from the SAME parse. They are two readings of
    one set of extractions, so scoring them together costs one extra pass over
    already-parsed text and removes any chance of the two lenses disagreeing
    because they saw different parses.
    """
    parse_secs = {}
    parsed = parse_all(papers, tex_dir, types, eval_dir, workers=workers,
                       label=f"scoring @ {state}", timings=parse_secs)
    # Stamp the scoring parameters onto every row. metrics() resolves the
    # similarity metric from a module global that the CALLER is responsible for
    # setting, so a cached row is meaningless without knowing which metric was
    # live when it was written -- a jaccard row served to a containment request
    # is silently wrong, and looks like nothing more than a shifted number.
    import node_similarity as _ns
    stamp = {"metric": _ns.get_match_metric(), "threshold": threshold,
             "cover": cover}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "a", encoding="utf-8") as fh:
        for pid in papers:
            buckets = parsed.get(pid, {t: [] for t in types})
            support = _all_gold(gold_texts_by_type, pid, types)
            for mode in ("m1", "m3"):
                agg = {"tp": 0, "tp_recall": 0, "fp": 0, "fn": 0}
                # Per-type counts as well as the sum. final_eval's per-type
                # table is the only reason it re-parses every paper three
                # times; recording the breakdown here makes that derivable
                # instead, and costs a few hundred bytes per row.
                per_type = {}
                for t in types:
                    m = metrics(buckets.get(t, []),
                                gold_texts_by_type[t].get(pid, []), threshold,
                                mode=mode, support_texts=support, cover=cover)
                    for k in agg:
                        agg[k] += m.get(k, 0)
                    per_type[t] = {k: m.get(k, 0) for k in
                                   ("tp", "tp_recall", "fp", "fn", "n_gold")}
                prec = agg["tp"] / (agg["tp"] + agg["fp"]) if agg["tp"] + agg["fp"] else 0.0
                rec = (agg["tp_recall"] / (agg["tp_recall"] + agg["fn"])
                       if agg["tp_recall"] + agg["fn"] else 0.0)
                f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
                fh.write(json.dumps({
                    "state": state, "run_index": run_index, "paper_id": pid,
                    "mode": mode, **stamp,
                    # yes = already distilled from (on/right of the diagonal);
                    # no = a pilot paper not yet reached, so still out-of-sample
                    # at this state; heldout = never distilled from at all.
                    "in_sample": ("yes" if pid in distilled else
                                  "no" if pid in pilot_set else "heldout"),
                    **agg, "precision": round(prec, 4),
                    "recall": round(rec, 4), "f1": round(f1, 4),
                    # Per-paper parse time at THIS rule state. Rules only get
                    # slower as they accumulate, and the cost lands on every
                    # paper at every checkpoint -- so this is the series that
                    # shows a bad rule arriving, and which paper it hurts.
                    "parse_seconds": parse_secs.get(pid),
                    "per_type": per_type,
                }) + "\n")
    print(f"  [score] {len(papers)} paper(s) @ {state} -> {out_path.name}")


def parse_buckets(pid: str, tex_dir: Path, types, eval_dir: Path | None) -> dict:
    """Parse one paper ONCE with rules; return {type: [raw_latex, ...]}.

    If eval_dir is given, the combined importer is installed across all type
    dirs so distilled rules are applied; otherwise the parser runs as-is
    (baseline = whatever is committed, matching the per-type script).
    The install is restored even if the parse is interrupted (installed_rules).

    NOTE `eval_dir=None` means "whatever happens to be installed", NOT a clean
    baseline — see baseline_snapshot().
    """
    with installed_rules(eval_dir, types):
        return parse_buckets_installed(pid, tex_dir, types)


def build_guard_probe(tex_dir: Path, paper_ids, per_paper_cap: int = 20000) -> str:
    """Concatenate (capped) LaTeX of the given papers as a backtracking probe.

    Mirrors what prune later runs the rules over (all papers so far), so a rule
    that backtracks on any of them is caught by the timed guard before use.
    """
    chunks = []
    for pid in paper_ids:
        main_tex = _find_main_tex(tex_dir / pid / "source")
        if main_tex is None:
            continue
        try:
            txt = Path(main_tex).read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        chunks.append(txt[:per_paper_cap])
    return "\n".join(chunks)


def opus_buckets(t2_path: Path, types, origin_filter) -> dict:
    """Bucket opus (tier2) nodes by type from a tier2 JSON."""
    d = json.load(open(t2_path, encoding='utf-8'))
    buckets = {t: [] for t in types}
    for n in d.get("nodes", []):
        t = n.get("type")
        if t not in buckets:
            continue
        if origin_filter is not None:
            o = n.get("origin")
            if o is not None and o != origin_filter:
                continue
        raw = (n.get("statement_latex") or n.get("statement")
               or n.get("raw_latex") or "")
        if raw.strip():
            buckets[t].append(raw)
    return buckets


def write_detailed_matches(eval_dir: Path, pid: str, t: str,
                           manual_texts, opus_texts) -> Path:
    """Write <eval_dir>/_dm/<type>/detailed_matches.csv for identify_dark_knowledge."""
    out_dir = eval_dir / "_dm" / t
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "detailed_matches.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["paper_id", "provider", "definition_text"])
        w.writeheader()
        for raw in manual_texts:
            w.writerow({"paper_id": pid, "provider": "manual", "definition_text": raw})
        for raw in opus_texts:
            w.writerow({"paper_id": pid, "provider": "anthropic", "definition_text": raw})
    return out


# ---------------------------------------------------------------------------
# Per-type P/R/F1 from extracted vs gold (same greedy match as the per-type
# script's evaluate_single_paper).
# ---------------------------------------------------------------------------


def _all_gold(gold_texts_by_type, pid, types):
    """Gold across EVERY type for one paper — m3's support set.

    m3's dominant case crosses types (a definition nested in a proof), so the
    support must not be scoped to the type being scored.
    """
    return [g for t in types for g in gold_texts_by_type[t].get(pid, [])]


def metrics(extracted_texts, gold_texts, threshold, *, mode="m1",
            support_texts=None, cover=0.7) -> dict:
    """Score one type's extractions against its gold.

    `mode` must match whatever the prune gate used. It previously did not
    exist here: --match-mode reached the prune gate and dark-knowledge
    selection but NOT the reported numbers, so rules were selected under m3 and
    then scored under m1 — a silent mismatch between gate and report.

    m1  same-type, greedy 1:1 at `threshold`.
    m3  m1, plus an extraction contained in ANY gold node counts (nesting), and
        a gold node counts as found when the UNION of extractions covers it
        (decomposition). `support_texts` is gold across EVERY type — the
        dominant nesting case crosses types (a definition inside a proof), so
        scoping it to this type would miss what m3 exists for.

    Under m3 precision and recall have different numerators — supported
    extractions vs covered gold — so they are counted separately rather than
    sharing one `tp`, matching eval_metric_ladder's M3.
    """
    import match_modes as _mm

    if mode == "m1":
        # Strict 1:1. Kept explicit rather than routed through gold_is_found,
        # which is NOT 1:1-constrained (one extraction can "find" several gold
        # nodes) and so reports a slightly generous recall — 0.477 vs 0.468 on
        # the 8-paper probe. M1 must stay exactly the historical pairing.
        pairs = []
        for i, ext in enumerate(extracted_texts):
            for j, gold in enumerate(gold_texts):
                sim = jaccard_similarity(ext, gold)
                if sim >= threshold:
                    pairs.append((sim, i, j))
        pairs.sort(reverse=True)
        m_ext, m_gold = set(), set()
        for sim, i, j in pairs:
            if i in m_ext or j in m_gold:
                continue
            m_ext.add(i); m_gold.add(j)
        tp = tp_recall = len(m_ext)
        fp = len(extracted_texts) - tp
        fn = len(gold_texts) - tp
    else:
        # m3: precision and recall have DIFFERENT numerators — supported
        # extractions vs covered gold — matching eval_metric_ladder's M3.
        verdicts = _mm.classify_extractions(
            extracted_texts, gold_texts, threshold,
            mode=mode, support_texts=support_texts, cover=cover)
        tp = sum(1 for v in verdicts if v)
        fp = len(extracted_texts) - tp
        tp_recall = sum(1 for g in gold_texts
                        if _mm.gold_is_found(g, extracted_texts, threshold,
                                             mode=mode, cover=cover))
        fn = len(gold_texts) - tp_recall
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp_recall / (tp_recall + fn) if (tp_recall + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    # `tp` is the PRECISION numerator (extractions that count as hits) and
    # `tp_recall` the RECALL numerator (gold items accounted for). Under m1 they
    # are equal — a 1:1 pairing — so tp+fn == n_gold and the row reads as an
    # ordinary confusion matrix. Under m3 they DIVERGE by design: several
    # extractions may sit inside one gold node (32 supported spans covering only
    # 19 gold items on one probe paper), so tp+fn == 48 against 35 gold and the
    # row is NOT a confusion matrix. Anything pooling these must sum tp_recall
    # for recall, never tp.
    return {'tp': tp, 'tp_recall': tp_recall, 'fp': fp, 'fn': fn,
            'precision': p, 'recall': r, 'f1': f1,
            'n_extracted': len(extracted_texts), 'n_gold': len(gold_texts)}


def load_gold_texts(gold_csv: Path) -> dict:
    """Return {paper_id: [raw_latex, ...]} for one type's gold CSV."""
    out = {}
    if not gold_csv.exists():
        return out
    with open(gold_csv, encoding='utf-8-sig', errors='replace') as f:
        for row in csv.DictReader(f):
            pid = (row.get('paper_id') or '').strip()
            raw = (row.get('Gold_Standard_raw_latex') or '').strip()
            if pid and raw:
                out.setdefault(pid, []).append(raw)
    return out


def build_group_gold(gold_dir: Path, group_key: str, types_in_group) -> Path:
    """Concatenate the subtype gold CSVs into one group gold CSV for pruning."""
    out = gold_dir / f"_group_{group_key}.csv"
    cols = ["paper_id", "Gold_Standard_raw_latex", "Gold_Standard_clean_text"]
    with open(out, "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=cols)
        w.writeheader()
        for t in types_in_group:
            src = gold_dir / FNAME_MAP[t]
            if not src.exists():
                continue
            with open(src, encoding='utf-8-sig', errors='replace') as fi:
                for row in csv.DictReader(fi):
                    w.writerow({c: row.get(c, "") for c in cols})
    return out


# ---------------------------------------------------------------------------
# Main merged loop
# ---------------------------------------------------------------------------

def run(args):
    t2_dir = Path(args.t2_dir).resolve()
    tex_dir = Path(args.tex_dir).resolve()
    eval_dir = Path(args.eval_dir).resolve()
    gold_dir = eval_dir / "silver_gold"
    groups_dir = eval_dir / "groups"
    model = args.model
    threshold = args.threshold
    batch_size = args.batch_size
    origin_filter = args.origin_filter or None

    types = [t.strip() for t in args.structure_types.split(',') if t.strip()]
    bad = [t for t in types if t not in FNAME_MAP]
    if bad:
        print(f"ERROR: unknown structure type(s): {bad}; valid: {ALL_SILVER_TYPES}")
        sys.exit(1)
    pilot_papers = [p.strip() for p in args.pilot_papers.split(',') if p.strip()]

    groups = base_method_groups(types)
    # BOTH modules must be set. seq's copy scores the baseline/post metrics;
    # _da's scores the prune gate's TP/FP verdict. Setting only seq (the old
    # behaviour) left the prune on jaccard while the metrics used containment.
    seq.set_match_metric(args.match_metric)

    print("Silver MERGED Distillation")
    print(f"  types: {types}")
    print(f"  groups: { {g: ts for g, ts in groups.items()} }")
    print(f"  model: {model}  batch_size: {batch_size}")
    print(f"  pilot papers: {pilot_papers}")
    print(f"  eval_dir: {eval_dir}")
    print(f"  match_metric: {args.match_metric}  prune_alpha: {args.prune_alpha}"
          f"  resume: {args.resume}")
    print(f"  match_mode: {args.match_mode}  cover: {args.cover}"
          f"   (m1 = strict same-type 1:1; m3 = nesting/label tolerant)")
    print()

    for pid in pilot_papers:
        if not (t2_dir / f"{pid}.json").exists():
            print(f"ERROR: T2 JSON not found: {t2_dir / (pid + '.json')}")
            sys.exit(1)
        if _find_main_tex(tex_dir / pid / "source") is None:
            print(f"WARNING: no .tex source for {pid}")

    eval_dir.mkdir(parents=True, exist_ok=True)
    groups_dir.mkdir(parents=True, exist_ok=True)
    log_path = eval_dir / "iteration_log.json"

    # Write the combined importer up front (groups may not exist yet -> [] until
    # a group's distilled_rules.py is generated).
    write_combined_importer(eval_dir, groups)

    iteration_log = []
    #: (paper_idx, paper_id, group, error) for aggregate calls that failed and
    #: fell back to the previous rules. Reported at the end so a degraded run
    #: is never mistaken for a clean one.
    agg_failures = []
    cumulative_cost = 0.0
    prior_papers = []
    start_idx = 0
    # Per-group cumulative analyze rows (accumulate across papers for sub-linearity)
    group_cum_rows = {g: [] for g in groups}
    group_cum_csv = {g: groups_dir / g / "cumulative_analyze.csv" for g in groups}

    if args.resume:
        if log_path.exists():
            iteration_log = json.load(open(log_path, encoding='utf-8'))
            prior_papers = [e['paper_id'] for e in iteration_log]
            start_idx = len(iteration_log)
            if iteration_log:
                cumulative_cost = iteration_log[-1].get('cumulative_cost_usd', 0.0)
        for g in groups:
            if group_cum_csv[g].exists():
                group_cum_rows[g] = list(csv.DictReader(open(group_cum_csv[g], encoding='utf-8')))
        # Drop already-distilled papers from the work list so --resume means
        # "re-run the exact same command". Without this, --pilot-papers is
        # taken verbatim and every prior paper is distilled AGAIN: duplicate
        # rows in the log, wasted LLM spend, and rules re-derived from papers
        # already learned. The alternative was hand-constructing the remaining
        # list in the run's own worst-first order, which is not something
        # anyone should have to do at 3am after a crash at paper 37.
        done = set(prior_papers)
        dropped = [p for p in pilot_papers if p in done]
        pilot_papers = [p for p in pilot_papers if p not in done]
        print(f"  RESUME: {len(prior_papers)} prior paper(s), cumulative ${cumulative_cost:.4f}")
        print(f"          prior: {prior_papers}")
        if dropped:
            print(f"          skipping {len(dropped)} already-distilled paper(s) "
                  f"from --pilot-papers")
        print(f"          remaining this run: {len(pilot_papers)}\n")
        if not pilot_papers:
            print("  Nothing left to distil — every requested paper is already "
                  "in the iteration log. Running finalize only.\n")
    else:
        # Clean slate: drop gold + per-group caches so a fresh run starts empty.
        for t in types:
            gp = gold_dir / FNAME_MAP[t]
            if gp.exists():
                gp.unlink()
        for g in groups:
            gd = groups_dir / g
            for stale in ("distilled_rules.py", "cumulative_analyze.csv"):
                if (gd / stale).exists():
                    (gd / stale).unlink()
        for g in groups:
            (groups_dir / g).mkdir(parents=True, exist_ok=True)
        # Drop stale per-step snapshots so the filmstrip starts clean.
        if (eval_dir / "snapshots").exists():
            shutil.rmtree(eval_dir / "snapshots")

    # ---- Phase 1: gold CSVs (no LLM) ----
    print("=" * 70)
    print("PHASE 1: tier2 opus JSON -> per-type silver gold CSV")
    print("=" * 70)
    for pid in pilot_papers:
        for t in types:
            existing = load_gold_texts(gold_dir / FNAME_MAP[t])
            if pid in existing:
                continue
            _, n = convert_t2_to_gold_csv(t2_dir / f"{pid}.json", t, gold_dir,
                                          origin_filter=origin_filter)
            if n:
                print(f"  {pid} [{t}]: {n}")
    gold_texts_by_type = {t: load_gold_texts(gold_dir / FNAME_MAP[t]) for t in types}
    print()

    # ---- Phase 2: baseline (one parse per paper, no distilled rules) ----
    print("=" * 70)
    print("PHASE 2: baseline (single combined parse per paper)")
    print("=" * 70)
    baselines = {}  # pid -> {type -> metrics}
    base_snap = baseline_snapshot(eval_dir, groups)
    print(f"  baseline rules: {base_snap.relative_to(eval_dir)} (empty by construction)")
    # ONE batched pass. Reused verbatim by worst-first ordering below, which
    # scores the same papers under this same snapshot.
    base_buckets = parse_all(pilot_papers, tex_dir, types, base_snap,
                             workers=args.workers, label="base snapshot")
    for pid in pilot_papers:
        b = base_buckets[pid]
        _sup = _all_gold(gold_texts_by_type, pid, types)
        baselines[pid] = {t: metrics(b[t], gold_texts_by_type[t].get(pid, []),
                                     threshold, mode=args.match_mode,
                                     support_texts=_sup, cover=args.cover)
                          for t in types}
        avg = sum(m['f1'] for m in baselines[pid].values()) / len(types)
        print(f"  {pid}: avg baseline F1={avg:.3f}  "
              + " ".join(f"{t[:3]}={baselines[pid][t]['f1']:.2f}" for t in types))
    print()

    # ---- In-run trajectory scoring set ----
    scores_path = eval_dir / "trajectory" / "scores.jsonl"
    score_set = []
    _done_states = set()
    if args.score_every > 0:
        sel = args.score_papers.strip()
        if sel in ("train", "test"):
            _sp = load_splits(split_file(args))
            score_set = sorted(p for p, s in _sp.items() if s == sel)
            missing = [p for p in score_set
                       if _find_main_tex(tex_dir / p / "source") is None]
            if missing:
                print(f"  [score] skipping {len(missing)} '{sel}' paper(s) with "
                      f"no .tex source")
                score_set = [p for p in score_set if p not in missing]
        elif sel:
            score_set = [p.strip() for p in sel.split(",") if p.strip()]
        else:
            score_set = []
        # The pilot papers are ALWAYS scored: they are the table's rows, and
        # without them the recorded set is incomplete and the table silently
        # falls back to re-parsing everything. --score-papers ADDS a held-out
        # set to them, it does not replace them.
        score_set = list(prior_papers) + list(pilot_papers) + [
            p for p in score_set
            if p not in set(prior_papers) | set(pilot_papers)]
        # Gold is needed to score, and it is only loaded for pilot papers.
        need_gold = [p for p in score_set if p not in gold_texts_by_type[types[0]]
                     and not any(p in gold_texts_by_type[t] for t in types)]
        for pid in need_gold:
            t2p = t2_dir / f"{pid}.json"
            if not t2p.exists():
                continue
            for t in types:
                convert_t2_to_gold_csv(t2p, t, gold_dir, origin_filter=origin_filter)
        if need_gold:
            gold_texts_by_type = {t: load_gold_texts(gold_dir / FNAME_MAP[t])
                                  for t in types}
        score_set = [p for p in score_set
                     if any(p in gold_texts_by_type[t] for t in types)]
        print(f"  [score] --score-every {args.score_every}: "
              f"{len(score_set)} paper(s) -> {scores_path}")
        # Resume appends, so drop any rows for states we are about to rewrite.
        if scores_path.exists() and not args.resume:
            scores_path.unlink()
        if scores_path.exists():
            with open(scores_path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        _done_states.add(json.loads(line)["state"])
                    except Exception:
                        pass
        if "base" not in _done_states:
            score_state(score_set, tex_dir, types, base_snap,
                        gold_texts_by_type, threshold, state="base",
                        run_index=0, distilled=set(),
                        pilot_set=set(prior_papers) | set(pilot_papers),
                        out_path=scores_path, workers=args.workers,
                        cover=args.cover)

    # ---- Phase 3: sequential merged distillation ----
    print("=" * 70)
    print("PHASE 3: merged distillation")
    print("=" * 70)

    # Never distil on a test paper: rules are written FROM these papers.
    splits = load_splits(split_file(args))
    if splits and not args.allow_test_papers:
        assert_no_test_leak(pilot_papers, splits)
    n_train = sum(1 for p in pilot_papers if splits.get(p) == "train")
    print(f"  [split] {n_train}/{len(pilot_papers)} paper(s) marked train "
          f"in {'metadata.csv' if splits else '(no metadata found)'}")

    # Hard-example mining: reorder so the worst-parsed papers go first.
    if args.order == "worst-first":
        print("\n" + "=" * 70)
        print("ORDERING: worst-first (dark-knowledge count under base rules)")
        print("=" * 70)
        ranked = rank_worst_first(pilot_papers, tex_dir, types, gold_dir,
                                  base_snap, threshold,
                                  match_mode=args.match_mode, cover=args.cover,
                                  base_buckets=base_buckets)
        pilot_papers = [pid for pid, _m, _g in ranked]
        with open(eval_dir / "paper_ranking.csv", "w", newline="",
                  encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["rank", "paper_id", "n_missed", "n_gold"])
            for i, (pid, m, g) in enumerate(ranked, 1):
                w.writerow([i, pid, m, g])
        print(f"  order: {', '.join(pilot_papers)}")
        print(f"  wrote {eval_dir / 'paper_ranking.csv'}\n")

    # Step-0 snapshot = no distilled rules yet (clean baseline for the filmstrip).
    if start_idx == 0:
        snapshot_rules(eval_dir, groups_dir, groups, 0, "initial")

    for offset, pid in enumerate(pilot_papers):
        paper_idx = start_idx + offset + 1
        t0 = time.time()
        t2_path = t2_dir / f"{pid}.json"
        print(f"\n{'─'*60}\nPaper {paper_idx} ({offset+1}/{len(pilot_papers)} this run): {pid}\n{'─'*60}")

        # 3a: ONE combined parse with current distilled rules + opus buckets ->
        #     per-type detailed_matches for dark-knowledge.
        print("  [1] Combined parse (rules + current distilled) ...")
        manual = parse_buckets(pid, tex_dir, types, eval_dir=eval_dir)
        opus = opus_buckets(t2_path, types, origin_filter)
        for t in types:
            write_detailed_matches(eval_dir, pid, t, manual[t], opus[t])

        # 3b: dark knowledge per type (no LLM), tagged + filtered to this paper.
        fn_items_by_group = {g: [] for g in groups}
        total_fns = 0
        per_type_fns = {}
        # Deliberately WITHIN-type — no cross-type support passed. See
        # identify_dark_knowledge's docstring: the prune gate is cross-type
        # because it asks whether an emitted span is real content anywhere;
        # this asks whether we must still learn to extract the node AS its own
        # type, and a span filed under another type does not answer that.
        for t in types:
            dk = identify_dark_knowledge(str(eval_dir / "_dm" / t),
                                         str(gold_dir / FNAME_MAP[t]), t, threshold,
                                         match_mode=args.match_mode,
                                         cover=args.cover)
            dk = [d for d in dk if d['paper_id'] == pid]
            for d in dk:
                d['structure_type'] = t
            per_type_fns[t] = len(dk)
            total_fns += len(dk)
            gkey = next(g for g, ts in groups.items() if t in ts)
            fn_items_by_group[gkey].extend(dk)
        print(f"  [2] Dark knowledge: {total_fns} FN(s) "
              + " ".join(f"{t[:3]}={per_type_fns[t]}" for t in types if per_type_fns[t]))

        # 3c+3d: batched analyze + grouped aggregate, per group.
        analyze_usage_tot = _da._empty_usage()
        agg_usage_tot = _da._empty_usage()
        search_dirs = [str(tex_dir / pid / "source")]
        # Backtracking probe = LaTeX of every paper the prune will run over.
        guard_probe = build_guard_probe(
            tex_dir, prior_papers + pilot_papers[:offset + 1])
        per_group = {}
        for gkey, items in fn_items_by_group.items():
            gdir = groups_dir / gkey
            gdir.mkdir(parents=True, exist_ok=True)
            rows = []
            if items:
                print(f"  [3:{gkey}] analyze {len(items)} item(s) (batch={batch_size}) ...")
                rows, ausage = analyze_patterns_batched(
                    items, str(tex_dir), group_key=gkey,
                    types_in_group=groups[gkey], model=model,
                    search_dirs=search_dirs, batch_size=batch_size)
                for k in analyze_usage_tot:
                    analyze_usage_tot[k] += ausage.get(k, 0)
                group_cum_rows[gkey].extend(rows)
                # rewrite cumulative CSV for this group
                if group_cum_rows[gkey]:
                    fns_cols = list(group_cum_rows[gkey][0].keys())
                    with open(group_cum_csv[gkey], 'w', newline='', encoding='utf-8') as f:
                        w = csv.DictWriter(f, fieldnames=fns_cols)
                        w.writeheader()
                        w.writerows(group_cum_rows[gkey])

            # Aggregate only when THIS paper actually contributed a suggestion.
            #
            # The gate used to be "has this group ever produced a suggestion",
            # so once a group had any rule it re-aggregated on EVERY subsequent
            # paper — even those where it found no dark knowledge at all. That
            # call re-sends the entire accumulated rule set, which grows as the
            # run proceeds, so the wasted calls also get steadily more
            # expensive. Measured on a 6-paper run: groups with zero new FNs
            # still paid full aggregates; over 60 papers that is ~240 aggregate
            # calls, most of them re-deriving an unchanged pool.
            #
            # Still aggregate when the group has accumulated suggestions but no
            # rules file yet — that is a first build, or a recovery after the
            # guard rejected generated code.
            gfile = gdir / "distilled_rules.py"
            new_sugg = any((r.get('llm_suggested_rule') or '').strip()
                           for r in rows)
            has_sugg = any((r.get('llm_suggested_rule') or '').strip()
                           for r in group_cum_rows[gkey])
            if new_sugg or (has_sugg and not gfile.exists()):
                print(f"  [4:{gkey}] aggregate {len(group_cum_rows[gkey])} cumulative rule(s) ...")
                prev_src = gfile.read_text(encoding='utf-8') if gfile.exists() else None
                # The aggregate prompt carries EVERY cumulative row for this
                # group, so it grows with the run and is the one call that can
                # outgrow the context window. A failure here used to propagate
                # and kill the run mid-paper, discarding everything already
                # paid for; the group's last-good rules are a far better
                # outcome than losing the run. Mirrors how a SyntaxError in the
                # generated code is already handled inside aggregate.
                try:
                    # Only THIS paper's rows go into the prompt; the model is
                    # shown the current rule file and asked to extend it. The
                    # CSV stays the full archive (the reports read it) but is
                    # no longer re-sent in full every paper -- that was a 33x
                    # prompt-to-artifact ratio and it truncated definition's
                    # output for 8 consecutive papers.
                    _path, gusage = aggregate_rules_merged(
                        str(group_cum_csv[gkey]), gkey, groups[gkey], str(gdir),
                        model, new_paper_ids=[pid])
                except Exception as e:
                    print(f"      [{gkey}] AGGREGATE FAILED: {type(e).__name__}: "
                          f"{str(e)[:300]}")
                    print(f"      [{gkey}] keeping previous rules; this group "
                          f"learned nothing from paper {paper_idx}")
                    agg_failures.append((paper_idx, pid, gkey, f"{type(e).__name__}: {str(e)[:200]}"))
                    gusage = {}
                for k in agg_usage_tot:
                    agg_usage_tot[k] += gusage.get(k, 0)
                # Surface the input size: this is the number that tells you
                # whether the prompt is on track to exceed the context window,
                # and it is already measured -- it just was not shown.
                _in = gusage.get('input_tokens', 0) + gusage.get(
                    'cache_read_input_tokens', 0)
                if _in:
                    print(f"      [{gkey}] aggregate input ~{_in:,} tok "
                          f"({len(group_cum_rows[gkey])} rows)")
                guard = validate_and_repair_group_file(
                    gfile, gkey, prev_src, probe_text=guard_probe,
                    max_rule_seconds=args.max_rule_seconds)
                if guard != 'ok':
                    print(f"      [guard] generated rules unsafe → {guard}")
            per_group[gkey] = {
                'fns': len(items),
                'rules': count_compiled_patterns(gdir / "distilled_rules.py"),
            }

        # Re-write the importer (in case a group dir was created this paper).
        write_combined_importer(eval_dir, groups)

        # 3e: prune per group (group-level gold so a pattern that's good for one
        #     subtype isn't pruned over another subtype's FP).
        papers_so_far = prior_papers + pilot_papers[:offset + 1]
        tex_search_dirs = [str(tex_dir / p / "source") for p in papers_so_far]
        # m3 scores an extraction against gold of EVERY type, not just the
        # group's — the nesting case we care about (a definition inside a
        # proof) crosses groups, so group-scoped support would miss it.
        all_types_gold = build_group_gold(gold_dir, "_alltypes", types)
        for gkey in groups:
            gfile = groups_dir / gkey / "distilled_rules.py"
            if not gfile.exists():
                continue
            group_gold = build_group_gold(gold_dir, gkey, groups[gkey])
            print(f"  [5:{gkey}] prune (mode={args.match_mode} "
                  f"alpha={args.prune_alpha:.2f}) over "
                  f"{len(papers_so_far)} paper(s) ...")
            pre_prune_src = gfile.read_text(encoding='utf-8')
            n_pruned = prune_rules(
                paper_ids=papers_so_far, structure_type=gkey,
                gold_csv=str(group_gold), eval_dir=str(groups_dir / gkey),
                threshold=threshold, max_fdr=args.prune_alpha,
                tex_search_dirs=tex_search_dirs,
                max_rule_seconds=args.max_rule_seconds,
                match_mode=args.match_mode, cover=args.cover,
                support_gold_csv=str(all_types_gold))
            if n_pruned:
                print(f"      pruned {n_pruned} rule(s)")
            # Defense-in-depth: prune output is unguarded codegen too — a
            # corrupted comment-out would silently disable the whole group.
            pruned_guard = validate_and_repair_group_file(
                gfile, gkey, pre_prune_src, probe_text=guard_probe,
                max_rule_seconds=args.max_rule_seconds)
            if pruned_guard != 'ok':
                print(f"      [guard:post-prune] {pruned_guard}")

        # 3e-snapshot: freeze this paper's cumulative rule state for the filmstrip.
        snapshot_rules(eval_dir, groups_dir, groups, paper_idx, pid)

        # 3f: post-eval (one combined parse with installed importer).
        post = parse_buckets(pid, tex_dir, types, eval_dir=eval_dir)
        _sup = _all_gold(gold_texts_by_type, pid, types)
        post_metrics = {t: metrics(post[t], gold_texts_by_type[t].get(pid, []),
                                   threshold, mode=args.match_mode,
                                   support_texts=_sup, cover=args.cover)
                        for t in types}

        # ---- cost + log ----
        analyze_cost = estimate_cost(analyze_usage_tot, model)
        aggregate_cost = estimate_cost(agg_usage_tot, model)
        total_cost = analyze_cost + aggregate_cost
        cumulative_cost += total_cost
        wall = time.time() - t0
        total_rules = sum(count_compiled_patterns(groups_dir / g / "distilled_rules.py")
                          for g in groups)
        llm_calls = analyze_usage_tot['llm_calls']   # batched analyze calls
        agg_calls = agg_usage_tot['llm_calls']        # aggregate calls actually made

        def _mean(key, d):
            return round(sum(d[t][key] for t in types) / len(types), 4)

        new_fns_total = total_fns
        entry = {
            'paper_idx': paper_idx,
            'paper_id': pid,
            'total_fns': total_fns,
            'already_covered': 0,
            'new_fns_to_distill': new_fns_total,
            'new_rules_in_file': total_rules,
            'cumulative_rules': total_rules,
            'analyze_llm_calls': llm_calls,
            'aggregate_llm_calls': agg_calls,
            'total_llm_calls': llm_calls + agg_calls,
            'analyze_input_tokens': analyze_usage_tot['input_tokens'],
            'analyze_output_tokens': analyze_usage_tot['output_tokens'],
            'analyze_cache_read_tokens': analyze_usage_tot['cache_read_input_tokens'],
            'analyze_cost_usd': round(analyze_cost, 6),
            'aggregate_input_tokens': agg_usage_tot['input_tokens'],
            'aggregate_output_tokens': agg_usage_tot['output_tokens'],
            'aggregate_cache_read_tokens': agg_usage_tot['cache_read_input_tokens'],
            'aggregate_cost_usd': round(aggregate_cost, 6),
            'total_cost_usd': round(total_cost, 6),
            'cumulative_cost_usd': round(cumulative_cost, 6),
            'wall_time_seconds': round(wall, 1),
            # cross-type means (the old silver_distillation_report.py read them):
            'baseline_f1': _mean('f1', baselines[pid]),
            'baseline_precision': _mean('precision', baselines[pid]),
            'baseline_recall': _mean('recall', baselines[pid]),
            'post_f1': _mean('f1', post_metrics),
            'post_precision': _mean('precision', post_metrics),
            'post_recall': _mean('recall', post_metrics),
            'per_type': {t: {
                'fns': per_type_fns[t],
                'baseline': {k: round(baselines[pid][t][k], 4)
                             for k in ('precision', 'recall', 'f1', 'tp', 'fp', 'fn',
                                       'n_gold', 'n_extracted')},
                'post': {k: round(post_metrics[t][k], 4)
                         for k in ('precision', 'recall', 'f1', 'tp', 'fp', 'fn',
                                   'n_gold', 'n_extracted')},
            } for t in types},
            'per_group': per_group,
        }
        iteration_log.append(entry)
        json.dump(iteration_log, open(log_path, 'w', encoding='utf-8'), indent=2)

        # Trajectory row for the state as it now stands. AFTER the log write, so
        # a crash here costs the scoring pass and not the paper's LLM spend.
        if args.score_every > 0:
            _state = f"after {paper_idx}"
            # offset is within THIS run; on resume pilot_papers holds only the
            # remaining papers, so papers_so_far (prior + done) is the real
            # distilled set and offset+1 the real end-of-run test.
            _last = offset + 1 == len(pilot_papers)
            if (paper_idx % args.score_every == 0 or _last) \
                    and _state not in _done_states:
                score_state(score_set, tex_dir, types, eval_dir,
                            gold_texts_by_type, threshold, state=_state,
                            run_index=paper_idx,
                            distilled=set(papers_so_far),
                            pilot_set=set(prior_papers) | set(pilot_papers),
                            out_path=scores_path,
                            workers=args.workers, cover=args.cover)

        print(f"\n  Summary: {total_fns} FNs → {total_rules} rules | "
              f"{llm_calls + agg_calls} LLM calls "
              f"({llm_calls} analyze + {agg_calls} aggregate) | "
              f"${total_cost:.4f} (cumul ${cumulative_cost:.4f}) | {wall:.1f}s")
        print("           avg F1 "
              f"{entry['baseline_f1']:.3f} → {entry['post_f1']:.3f}")

    # ---- Final report ----
    print(f"\n\n{'='*70}\nSILVER MERGED SUMMARY\n{'='*70}")
    print(f"\nIteration log: {log_path}")
    print(f"\n{'Paper':<12} {'FNs':>4} {'Rules':>6} {'Calls':>6} "
          f"{'Cost':>9} {'F1 pre':>7} {'F1 post':>8}")
    print("-" * 60)
    for e in iteration_log:
        print(f"{e['paper_id']:<12} {e['total_fns']:>4} {e['new_rules_in_file']:>6} "
              f"{e['total_llm_calls']:>6} ${e['total_cost_usd']:>8.4f} "
              f"{e['baseline_f1']:>7.3f} {e['post_f1']:>8.3f}")
    total_calls = sum(e['total_llm_calls'] for e in iteration_log)
    print(f"\n  Total LLM calls: {total_calls}")
    if agg_failures:
        print(f"\n  !! {len(agg_failures)} AGGREGATE CALL(S) FAILED — those "
              f"groups kept their previous rules and learned nothing from the "
              f"paper in question. Results below are a FLOOR, not this "
              f"configuration's ceiling:")
        for idx, pid, gkey, err in agg_failures:
            print(f"       paper {idx} ({pid}) / {gkey}: {err}")
    print(f"  Total cost: ${cumulative_cost:.4f}")
    if iteration_log:
        print(f"  Avg cost/paper: ${cumulative_cost/len(iteration_log):.4f}")
    print(f"\n  Combined importer: {eval_dir}/distilled_rules.py")
    print(f"  Per-group rules:   {groups_dir}/<group>/distilled_rules.py")

    # Scoring and comparison of every algorithm live in scripts/compare_distillers.py.


def run_tagger(args) -> None:
    """--alg tagger: build the training data and train the sentence tagger
    (alg3/data.py, alg3/train.py) into --eval-dir, which then holds an extractor
    (distilled_rules.py + sentence_model.json) like any rule set. Training papers:
    --pilot-papers (a list, or the split name `train`); validation: the split's
    val papers. No teacher call."""
    import shlex
    import subprocess
    eval_dir = Path(args.eval_dir).resolve()
    eval_dir.mkdir(parents=True, exist_ok=True)
    split_csv = split_file(args)
    pids = [p.strip() for p in args.pilot_papers.split(",") if p.strip()]
    if pids in (["train"], ["val"]):
        pids = sorted(p for p, s in load_splits(split_csv).items() if s == pids[0])
    if not args.allow_test_papers:
        assert_no_test_leak(pids, load_splits(split_csv))
    data = eval_dir / "tagger_papers.pkl"
    a3 = REPO / "alg3"
    steps = [
        [sys.executable, "-u", str(a3 / "data.py"), "--splits", "train,val",
         "--tex-dir", str(Path(args.tex_dir).resolve()), "--out", str(data),
         "--split-file", str(split_csv), "--silver", str(Path(args.t2_dir).resolve()),
         "--train-papers", ",".join(pids), "--workers", str(args.prepare_workers)],
        [sys.executable, "-u", str(a3 / "train.py"), "--data", str(data),
         "--out", str(eval_dir)] + shlex.split(args.tagger_args),
    ]
    for cmd in steps:
        print("[tagger] " + " ".join(cmd), flush=True)
        rc = subprocess.run(cmd, cwd=REPO).returncode
        if rc != 0:
            raise SystemExit(f"[tagger] failed (exit {rc}): {cmd[2]}")


def main():
    p = argparse.ArgumentParser(description="Silver Standard MERGED Distillation")
    p.add_argument("--structure-types", default=",".join(ALL_SILVER_TYPES),
                   help="Comma list of types (default: all 9 silver types)")
    p.add_argument("--alg", default="merged", choices=["merged", "units", "tagger"],
                   help="merged: the teacher writes per-group extractor files, one "
                        "training paper at a time (analyze -> aggregate -> prune). "
                        "units: the teacher writes sentence rules for clusters of "
                        "missed prose nodes, each tested on all training papers "
                        "before it is accepted (scripts/distill_units.py). "
                        "tagger: no teacher call; a weighted clue model is learned "
                        "from the silver itself (alg3/, see alg3/README.md).")
    p.add_argument("--tagger-args", default="--class-weight sqrt --stack",
                   help="with --alg tagger: options passed to alg3/train.py "
                        "(default: the released v2b settings)")
    p.add_argument("--pilot-papers", required=True,
                   help="Comma-separated paper IDs (e.g. paper001,paper005); "
                        "with --alg units also a split name (train)")
    p.add_argument("--t2-dir", default="corpus/silver/opus-5.5__v6",
                   help="silver graphs, one <paper>.json per paper")
    p.add_argument("--tex-dir", required=True,
                   help="Directory with paper*/source/*.tex files")
    p.add_argument("--eval-dir", required=True, help="Output dir for artifacts")
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--batch-size", type=int, default=8,
                   help="Missed structures per analyze LLM call (default 8)")
    p.add_argument("--origin-filter", default=None,
                   help="Only include opus nodes whose `origin` matches (e.g. 'paper')")
    p.add_argument("--match-metric", default="containment",
                   choices=["jaccard", "containment"])
    p.add_argument("--max-rule-seconds", type=float, default=10.0,
                   help="Time-guard: prune any distilled pattern whose worst "
                        "per-paper findall exceeds this many seconds "
                        "(catastrophic backtracking). 0 disables.")
    p.add_argument("--workers", type=int, default=1,
                   help="parallel workers for the batched multi-paper parses "
                        "(baseline pass and per-step scoring). Rules are "
                        "installed ONCE per state in the parent; workers only "
                        "read. >1 pays a per-worker import cost, so it only "
                        "wins on big sets (measured 0.7x at 12 papers, 1.5x at "
                        "60 on 8 cores).")
    p.add_argument("--score-every", type=int, default=1, metavar="N",
                   help="after every Nth paper, parse and score ALL papers in "
                        "--score-papers under the rule state as it stands, and "
                        "append to trajectory/scores.jsonl. This is what makes "
                        "the trajectory table a pure reader instead of a job "
                        "that re-runs the whole run. Default 1 = every paper; "
                        "raise it if the scoring set is large (cost is "
                        "|score-papers| x |papers| parses). 0 = off.")
    p.add_argument("--score-papers", default="",
                   help="EXTRA papers to score under --score-every, on top of "
                        "the pilot papers (which are always scored, since "
                        "they are the trajectory table's rows). Comma "
                        "list, or a split name (train/test) to pull that "
                        "split from the metadata as a held-out set.")
    p.add_argument("--order", default="given",
                   choices=["given", "worst-first"],
                   help="Distillation order. 'worst-first' = hard-example "
                        "mining: rank the pool by how much the BASE parser "
                        "misses (dark-knowledge count) and distil the worst "
                        "first, so each LLM call is spent where the student is "
                        "weakest.")
    p.add_argument("--metadata", default=None,
                   help="Silver corpus index for the train/test split "
                        "(default corpus/silver/metadata.csv)")
    p.add_argument("--effort", default=None, choices=["low", "medium", "high", "xhigh", "max"],
                   help="teacher effort: how much it thinks before answering (thinking is "
                        "billed as output, most of a run's cost); default: the model's own")
    p.add_argument("--thinking", default=None, choices=["adaptive", "disabled"],
                   help="disabled turns the teacher's thinking off (Haiku 5.5 allows it, "
                        "Sonnet 5.5 does not); default: the model's own (adaptive)")
    p.add_argument("--splits", default=None,
                   help="CSV with arxiv_id (or paper_id) and split columns, e.g. "
                        "corpus/silver/split_v6.csv; overrides the split in --metadata")
    p.add_argument("--allow-test-papers", action="store_true",
                   help="Permit test-split papers in the distillation set. "
                        "Off by default — distilling on test papers trains on "
                        "the test set.")
    p.add_argument("--match-mode", default="m1", choices=["m1", "m3"],
                   help="Scoring used by the prune gate AND dark-knowledge "
                        "selection. m1 = strict same-type 1:1 (unchanged). "
                        "m3 = nesting/label tolerant; see match_modes.py")
    p.add_argument("--cover", type=float, default=0.7,
                   help="m3: fraction of a span that must be accounted for")
    p.add_argument("--prune-alpha", type=float, default=None,
                   help="Per-rule FDR tolerance: prune when FP/(FP+TP) > alpha")
    p.add_argument("--resume", action="store_true",
                   help="Continue a prior run in --eval-dir (per-paper invocation)")
    u = p.add_argument_group("units algorithm (--alg units)")
    u.add_argument("--rounds", type=int, default=5,
                   help="maximum rounds of repair -> cluster -> propose -> refine -> cleanup")
    u.add_argument("--min-cluster", type=int, default=3,
                   help="smallest cluster of missed nodes the teacher is asked about")
    u.add_argument("--train-metric", default="m1g", choices=["m1g", "m1"],
                   help="how a rule's output is matched to the silver while training "
                        "(src/LLMVersion/node_metrics.py): m1g = the headline metric, with "
                        "partial credit for related types (type table); m1 = same type only")
    u.add_argument("--accept", default="f1", choices=["f1", "fdr", "precision"],
                   help="f1: a rule is kept if, added to the rules already accepted, it raises "
                        "the overall F (all silver nodes, the base parser's included) on the "
                        "fitting papers by more than --min-gain and does not lower it on the "
                        "validation papers; refinement maximises that gain. fdr: a rule is kept "
                        "if, added to the rules already accepted, it finds at least --min-tp new "
                        "silver nodes at an FDR <= --max-fdr (--fdr-scope: of what it adds, or "
                        "of the whole extractor), on the fitting and the validation papers; "
                        "refinement maximises the nodes it adds within that. precision: a rule "
                        "alone must reach --min-precision; refinement maximises TP - fp_weight*FP")
    u.add_argument("--max-fdr", type=float, default=0.2,
                   help="--accept fdr: the false discovery rate allowed (see --fdr-scope)")
    u.add_argument("--fdr-scope", default="rule", choices=["rule", "overall"],
                   help="--accept fdr: rule = the FDR of the nodes the rule adds (nodes the base "
                        "parser or another rule already finds count neither way); every rule "
                        "within q keeps the extractor within q too. overall = the FDR of the "
                        "whole extractor, base parser included")
    u.add_argument("--rule-min-precision", type=float, default=0.0,
                   help="--accept fdr: also a floor on each rule's own precision (useful with "
                        "--fdr-scope overall, where noisy rules accepted early could spend the "
                        "whole FDR budget)")
    u.add_argument("--beta", type=float, default=1.0,
                   help="F-beta for --accept f1 (beta < 1 favours precision)")
    u.add_argument("--min-gain", type=float, default=0.0,
                   help="overall F gain a rule must add on the fitting papers (--accept f1)")
    u.add_argument("--min-precision", type=float, default=0.8,
                   help="--accept precision: precision a rule needs (on the fitting papers, and "
                        "on the validation papers where it fires --val-min-fired times)")
    u.add_argument("--min-tp", type=int, default=3,
                   help="true positives a rule needs on the fitting papers to be accepted")
    u.add_argument("--max-refine", type=int, default=4,
                   help="hill-climbing steps per rule (each: tighten and/or broaden); it stops "
                        "earlier at a local maximum. 0 = accept or reject the first proposal")
    u.add_argument("--refine-moves", default="tighten,broaden",
                   help="refinement moves: tighten (on confirmed false positives), "
                        "broaden (on the cluster's missed nodes)")
    u.add_argument("--fp-weight", type=float, default=2.0,
                   help="--accept precision: refinement maximises TP - fp_weight x FP on the "
                        "fitting papers")
    u.add_argument("--judge", default="teacher", choices=["teacher", "none"],
                   help="before tightening, ask a judge which false positives are real "
                        "errors (the rest are likely silver misses and are not tightened against)")
    u.add_argument("--judge-model", default=None, help="judge model (default: --model)")
    u.add_argument("--max-examples", type=int, default=0,
                   help="cluster members shown when a rule is proposed (0 = all)")
    u.add_argument("--max-negatives", default="auto",
                   help="look-alikes shown when a rule is proposed: sentences with the "
                        "cluster's cue that start no node of its type and lie inside none. "
                        "auto = max(12, number of positives shown); a number = fixed cap; "
                        "0 = all")
    u.add_argument("--max-refine-examples", type=int, default=12,
                   help="per refinement step: true positives to keep, missed members, and "
                        "false positives shown to the judge and the teacher (0 = all)")
    u.add_argument("--val-tolerance", type=float, default=0.0,
                   help="how much a refinement (and, with --accept f1, an accepted rule) may lower "
                        "the validation value: the overall F gain (f1) or TP - w*FP (precision)")
    u.add_argument("--val-min-fired", type=int, default=3,
                   help="--accept precision: validation precision is checked only if the rule "
                        "fires this often there")
    u.add_argument("--val-papers", default="10",
                   help="validation papers (acceptance and stopping checks): a number = that many "
                        "of the --pilot-papers, drawn with --seed; a split name (val) = that "
                        "split's papers, and all --pilot-papers are fitted")
    u.add_argument("--max-llm-calls", type=int, default=400, help="teacher-call budget")
    u.add_argument("--parallel", type=int, default=6,
                   help="clusters worked on at once (their teacher calls overlap); rules are "
                        "still accepted one at a time, in cluster order, each re-checked "
                        "against the rules accepted meanwhile")
    u.add_argument("--prepare-workers", type=int, default=4,
                   help="processes preparing the papers (base parse, sentences, silver nodes)")
    u.add_argument("--snapshot-every", type=int, default=5,
                   help="freeze the rules every N accepted rules (and at each round's end), "
                        "for the learning curve; 0 = round ends only")
    u.add_argument("--stop-gain", type=float, default=0.005,
                   help="stop when a round adds less than this to validation F1")
    u.add_argument("--seed", type=int, default=0, help="fit/validation split seed")
    args = p.parse_args()
    print(f"[llm] request options: {_da.set_llm_options(args.effort, args.thinking)}")
    if args.alg == "units":
        import distill_units                  # alpha defaults to 0.2 there (rule precision >= 0.8)
        distill_units.run(args)
        return
    if args.alg == "tagger":
        run_tagger(args)
        return

    # alpha is mode-dependent: m1's 0.5 was tuned against a signal that is ~98%
    # labelling noise. Under m3 that noise is gone, so the same 0.5 would almost
    # never trip and pruning would silently stop happening.
    if args.prune_alpha is None:
        import match_modes as _mm
        args.prune_alpha = _mm.DEFAULT_ALPHA[args.match_mode]
        print(f"[prune] alpha not given; using {args.prune_alpha} "
              f"for match-mode={args.match_mode}")
    run(args)


if __name__ == "__main__":
    main()
