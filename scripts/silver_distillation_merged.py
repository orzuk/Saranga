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
import csv
import json
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

# Pricing (USD per million tokens). Mirrors the per-type script.
PRICING = {
    'claude-opus':   (15.0, 75.0),
    'claude-sonnet': (3.0,  15.0),
    'claude-haiku':  (0.25, 1.25),
}


def _rates(model: str):
    for prefix, (i, o) in PRICING.items():
        if prefix in model:
            return i, o
    return 3.0, 15.0


def estimate_cost(usage: dict, model: str) -> float:
    """Cache-aware USD estimate.

    Anthropic reports non-cached input in ``input_tokens`` and bills cache reads
    at ~0.1x and cache writes at ~1.25x the input rate.
    """
    i_rate, o_rate = _rates(model)
    inp = usage.get('input_tokens', 0) or 0
    cr = usage.get('cache_read_input_tokens', 0) or 0
    cw = usage.get('cache_creation_input_tokens', 0) or 0
    out = usage.get('output_tokens', 0) or 0
    return (inp * i_rate + cr * i_rate * 0.1 + cw * i_rate * 1.25
            + out * o_rate) / 1_000_000


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
                                   probe_text: str = "", timeout_s: float = 30.0) -> str:
    """Make `path` safe to import+run, or fall back. Returns the action taken:
    'ok' | 'aliased' | 'reverted' | 'stubbed' | 'slow'.

    `probe_text` (real LaTeX from the papers seen so far) is run through the
    entry point under a `timeout_s` wall-clock limit, so a regex that is valid
    Python but catastrophically backtracks on real input is caught here and
    reverted — before it can hang the prune/parse steps.
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
        fn("")
    except Exception:
        return _restore()

    # Timed run on real text: reject catastrophically-backtracking regexes.
    if probe_text:
        try:
            _run_with_timeout(fn, probe_text, timeout_s)
        except _RuleTimeout:
            return f"slow→{_restore()}"
        except Exception:
            return _restore()
    return action


# ---------------------------------------------------------------------------
# Combined importer (hand-authored — no codegen risk)
# ---------------------------------------------------------------------------

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
        "def _load_group(gkey):",
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
        "        return m",
        "    except Exception:",
        "        return None",
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
        "    except Exception:",
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

def install_importer(eval_dir: Path, types) -> dict:
    """Symlink <eval_dir>/distilled_rules.py into every {type}_eval/ dir.

    Returns {type: backup_path_or_None} for restoration. Reuses the per-type
    installer so sys.modules cache invalidation stays consistent.
    """
    backups = {}
    for t in types:
        _, backup = seq._install_silver_rules(eval_dir, t)
        backups[t] = backup
    return backups


def uninstall_importer(types, backups: dict) -> None:
    for t in types:
        seq._uninstall_silver_rules(t, backups.get(t))


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
            pid, split = row.get("paper_id"), row.get("split")
            if not (pid and split):
                continue
            r = precedence.get(split, 2)
            if r > rank.get(pid, 0):
                out[pid], rank[pid] = split, r
    return out


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
                     match_mode: str = "m1", cover: float = 0.7):
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

    Returns [(paper_id, n_missed, n_gold), ...] sorted by n_missed descending.
    """
    import match_modes as _mm
    gold_by_type = {t: load_gold_texts(gold_dir / FNAME_MAP[t]) for t in types}
    scored = []
    for i, pid in enumerate(papers, 1):
        buckets = parse_buckets(pid, tex_dir, types, eval_dir=base_snap)
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

def parse_buckets(pid: str, tex_dir: Path, types, eval_dir: Path | None) -> dict:
    """Parse one paper ONCE with rules; return {type: [raw_latex, ...]}.

    If eval_dir is given, the combined importer is installed across all type
    dirs so distilled rules are applied; otherwise the parser runs as-is
    (baseline = whatever is committed, matching the per-type script).
    """
    from math_paper_parser import PaperParser

    backups = {}
    if eval_dir is not None:
        backups = install_importer(eval_dir, types)

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

    if eval_dir is not None:
        uninstall_importer(types, backups)

    return buckets


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

def metrics(extracted_texts, gold_texts, threshold) -> dict:
    pairs = []
    for i, ext in enumerate(extracted_texts):
        for j, gold in enumerate(gold_texts):
            sim = jaccard_similarity(ext, gold)
            if sim >= threshold:
                pairs.append((sim, i, j))
    pairs.sort(reverse=True)
    matched_ext, matched_gold = set(), set()
    tp = 0
    for sim, i, j in pairs:
        if i in matched_ext or j in matched_gold:
            continue
        matched_ext.add(i)
        matched_gold.add(j)
        tp += 1
    fp = len(extracted_texts) - tp
    fn = len(gold_texts) - tp
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {'tp': tp, 'fp': fp, 'fn': fn, 'precision': p, 'recall': r, 'f1': f1,
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
    seq._MATCH_METRIC = args.match_metric  # drives jaccard_similarity (+ _da copy)

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
        print(f"  RESUME: {len(prior_papers)} prior paper(s), cumulative ${cumulative_cost:.4f}")
        print(f"          prior: {prior_papers}\n")
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
    for pid in pilot_papers:
        b = parse_buckets(pid, tex_dir, types, eval_dir=base_snap)
        baselines[pid] = {t: metrics(b[t], gold_texts_by_type[t].get(pid, []), threshold)
                          for t in types}
        avg = sum(m['f1'] for m in baselines[pid].values()) / len(types)
        print(f"  {pid}: avg baseline F1={avg:.3f}  "
              + " ".join(f"{t[:3]}={baselines[pid][t]['f1']:.2f}" for t in types))
    print()

    # ---- Phase 3: sequential merged distillation ----
    print("=" * 70)
    print("PHASE 3: merged distillation")
    print("=" * 70)

    # Never distil on a test paper: rules are written FROM these papers.
    splits = load_splits(Path(args.metadata) if args.metadata else SILVER_METADATA)
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
                                  match_mode=args.match_mode, cover=args.cover)
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

            # aggregate if this group has any accumulated suggestion
            has_sugg = any((r.get('llm_suggested_rule') or '').strip()
                           for r in group_cum_rows[gkey])
            if has_sugg:
                print(f"  [4:{gkey}] aggregate {len(group_cum_rows[gkey])} cumulative rule(s) ...")
                gfile = gdir / "distilled_rules.py"
                prev_src = gfile.read_text(encoding='utf-8') if gfile.exists() else None
                _path, gusage = aggregate_rules_merged(
                    str(group_cum_csv[gkey]), gkey, groups[gkey], str(gdir), model)
                for k in agg_usage_tot:
                    agg_usage_tot[k] += gusage.get(k, 0)
                guard = validate_and_repair_group_file(
                    gfile, gkey, prev_src, probe_text=guard_probe)
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
                gfile, gkey, pre_prune_src, probe_text=guard_probe)
            if pruned_guard != 'ok':
                print(f"      [guard:post-prune] {pruned_guard}")

        # 3e-snapshot: freeze this paper's cumulative rule state for the filmstrip.
        snapshot_rules(eval_dir, groups_dir, groups, paper_idx, pid)

        # 3f: post-eval (one combined parse with installed importer).
        post = parse_buckets(pid, tex_dir, types, eval_dir=eval_dir)
        post_metrics = {t: metrics(post[t], gold_texts_by_type[t].get(pid, []), threshold)
                        for t in types}

        # ---- cost + log ----
        analyze_cost = estimate_cost(analyze_usage_tot, model)
        aggregate_cost = estimate_cost(agg_usage_tot, model)
        total_cost = analyze_cost + aggregate_cost
        cumulative_cost += total_cost
        wall = time.time() - t0
        total_rules = sum(count_compiled_patterns(groups_dir / g / "distilled_rules.py")
                          for g in groups)
        llm_calls = analyze_usage_tot['llm_calls']  # batched analyze calls
        # plus one aggregate call per group that had suggestions:
        agg_calls = sum(1 for g in groups
                        if any((r.get('llm_suggested_rule') or '').strip()
                               for r in group_cum_rows[g]))

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
            # cross-type means keep silver_distillation_report.py working:
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
    print(f"  Total cost: ${cumulative_cost:.4f}")
    if iteration_log:
        print(f"  Avg cost/paper: ${cumulative_cost/len(iteration_log):.4f}")
    print(f"\n  Combined importer: {eval_dir}/distilled_rules.py")
    print(f"  Per-group rules:   {groups_dir}/<group>/distilled_rules.py")

    # ---- Finalize: auto-generate eval + report + chart + FP-judge ----
    # Read-only consumers of the just-produced rules; each is guarded so a
    # reporting failure never discards the (expensive) distillation result.
    finalize_run(args, eval_dir)


def finalize_run(args, eval_dir):
    """Run the read-only post-distillation steps: final_eval (per-type F1 CSV),
    LLM FP-judge (adjusted precision), consolidated REPORT.md, and the
    per-type F1/FP chart. Controlled by --skip-finalize / --skip-fp-judge.
    Every step is independently guarded.
    """
    import subprocess
    repo = Path(__file__).resolve().parent.parent
    eval_dir = Path(eval_dir)
    mm = args.match_metric

    if getattr(args, "skip_finalize", False):
        print("\n[finalize] skipped (--skip-finalize)")
        return

    print(f"\n{'='*70}\nFINALIZE (read-only reports)\n{'='*70}")

    # 1. final_eval.py -> final_eval.csv (subprocess: own argparse, no LLM)
    try:
        print("[finalize] final_eval ...")
        subprocess.run(
            [sys.executable, str(repo / "scripts" / "final_eval.py"),
             "--eval-dir", str(eval_dir), "--tex-dir", str(args.tex_dir),
             "--match-metric", mm],
            check=True)
    except Exception as e:
        print(f"[finalize] final_eval failed: {e}")

    # 2. fp_judge.py -> fp_judge.csv (subprocess: makes LLM calls)
    if not getattr(args, "skip_fp_judge", False):
        try:
            print("[finalize] fp_judge (LLM-as-judge) ...")
            subprocess.run(
                [sys.executable, str(repo / "scripts" / "fp_judge.py"),
                 "--eval-dir", str(eval_dir), "--tex-dir", str(args.tex_dir),
                 "--match-metric", mm, "--model", args.model],
                check=True)
        except Exception as e:
            print(f"[finalize] fp_judge failed: {e}")
    else:
        print("[finalize] fp_judge skipped (--skip-fp-judge)")

    # 3. consolidated REPORT.md (reads final_eval.csv + fp_judge.csv)
    try:
        print("[finalize] REPORT.md ...")
        from make_distill_report import build_report
        print(f"           wrote {build_report(eval_dir)}")
    except Exception as e:
        print(f"[finalize] report failed: {e}")

    # 4. per_type_f1_fp.png chart
    try:
        print("[finalize] per_type_f1_fp.png ...")
        from plot_type_f1_fp import build_chart
        print(f"           wrote {build_chart(eval_dir, args.tex_dir, mm)}")
    except Exception as e:
        print(f"[finalize] chart failed: {e}")


def main():
    p = argparse.ArgumentParser(description="Silver Standard MERGED Distillation")
    p.add_argument("--structure-types", default=",".join(ALL_SILVER_TYPES),
                   help="Comma list of types (default: all 9 silver types)")
    p.add_argument("--pilot-papers", required=True,
                   help="Comma-separated paper IDs (e.g. paper001,paper005)")
    p.add_argument("--t2-dir", default="portal/data/tier2")
    p.add_argument("--tex-dir", required=True,
                   help="Directory with paper*/source/*.tex files")
    p.add_argument("--eval-dir", required=True, help="Output dir for artifacts")
    p.add_argument("--model", default="claude-sonnet-4-6")
    p.add_argument("--threshold", type=float, default=0.7)
    p.add_argument("--batch-size", type=int, default=8,
                   help="Missed structures per analyze LLM call (default 8)")
    p.add_argument("--origin-filter", default=None,
                   help="Only include opus nodes whose `origin` matches (e.g. 'paper')")
    p.add_argument("--match-metric", default="jaccard",
                   choices=["jaccard", "containment"])
    p.add_argument("--max-rule-seconds", type=float, default=10.0,
                   help="Time-guard: prune any distilled pattern whose worst "
                        "per-paper findall exceeds this many seconds "
                        "(catastrophic backtracking). 0 disables.")
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
    p.add_argument("--skip-finalize", action="store_true",
                   help="Skip the post-run reports (final_eval + judge + report + chart)")
    p.add_argument("--skip-fp-judge", action="store_true",
                   help="Skip only the LLM FP-judge step (keeps final_eval/report/chart)")
    args = p.parse_args()

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
