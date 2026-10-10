#!/usr/bin/env python3
"""Post-hoc distilled-rule subset selection, on the train split only.

The distillation run leaves ~370 active patterns across 5 base-method groups.
The FDR prune gate judged each rule INDEPENDENTLY; this tool searches for the
best-scoring SUBSET, accounting for interactions (span suppression inside a
group's extract function, cross-rule dedup in _merge_objects, greedy 1:1
matching), without ever re-parsing per subset.

Two phases:

  precompute   (the only phase that parses / runs regexes)
      For each paper: one baseline parse (no distilled rules) that also
      captures the exact preprocessed text the parser feeds
      _apply_distilled_rules; then each group's extract function is run once
      per module-level pattern with every OTHER pattern replaced by a
      never-matching regex ("neutered"), once with all patterns neutered (the
      "floor": output owned by inline regexes no unit controls), and once with
      all patterns active (validation anchor). Results go to one JSON per
      paper.

  search       (pure in-memory set algebra; no parsing, no LLM)
      Replays the pipeline for any subset: floor + selected units' items in
      source order -> span-overlap suppression (only for groups whose source
      uses it) -> _merge_objects replica against the baseline nodes (exact
      dup + containment >= 0.7 on the parser cleaner's tokens) -> scored with
      an exact replica of silver_distillation_merged.metrics() (m1 and m3) on
      cached silver-profile token sets. Each candidate subset is evaluated
      incrementally (only papers the changed rule fires on are re-replayed),
      with a backward-elimination polish and optional k-fold CV to pick the
      stopping size honestly. NEVER give this the test split.

      --search-algo picks the selection algorithm. They all live together in
      scripts/rule_subset_algos.py, ordered classical -> contemporary:

        greedy       forward selection on pooled F1 (the original baseline)
        lazy         CELF lazy forward selection (same intent, fewer evals)
        localsearch  add/drop/swap to a local optimum
        distorted    distorted greedy, max g(S)-c(S)   (Harshaw+ ICML 2019)
        dinkelbach   fractional programming on the F1 ratio
        poss         Pareto optimisation over (F1, -|S|) (Qian+ NeurIPS 2015)
        porss        POSS + recombination                (Qian+ 2022)

      Greedy is the default and its outputs keep their historical filenames
      (greedy_curve.csv, selection.json, cv_curves.csv) so the Sep-01 report
      keeps reading them; every run also writes <tag>_curve.csv and
      selection_<tag>.json. Use --out-tag to compare algorithms side by side
      without clobbering.

Validation: `search --validate-only` replays the full active set and compares
per-paper pooled F1 against the run's recorded scores.jsonl ("after N" state)
and the baseline against state "base". Fix discrepancies before trusting any
search output.

Usage:
  python3 scripts/rule_subset_search.py precompute \
      --eval-dir src/LLMVersion/merged_eval_v51_train60_v2 \
      --tex-dir corpus/silver/tex_staged --workers 8
  python3 scripts/rule_subset_search.py search \
      --eval-dir src/LLMVersion/merged_eval_v51_train60_v2 [--cv 5]
  python3 scripts/rule_subset_search.py search \
      --eval-dir src/LLMVersion/merged_eval_v51_train60_v2 \
      --search-algo poss --out-tag poss_v1
"""
import argparse
import csv
import importlib.util
import json
import multiprocessing as mp
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO / "scripts", REPO / "src" / "LLMVersion", REPO / "src"):
    sys.path.insert(0, str(p))

import rule_subset_algos as algos          # noqa: E402  (needs sys.path)

GROUPS = {
    "definition": ["definition"],
    "theoremlike": ["theorem", "lemma", "proposition", "corollary", "claim",
                    "conjecture", "problem", "open_problem"],
    "proof": ["proof"],
    "simpleenv": ["remark", "example", "assumption"],
    "algorithm": ["algorithm"],
}
TYPES = [t for ts in GROUPS.values() for t in ts]
NEVER = re.compile(r"(?!x)x")          # matches nothing, still a re.Pattern


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def load_group_module(eval_dir: Path, gkey: str):
    path = eval_dir / "groups" / gkey / "distilled_rules.py"
    if not path.is_file():
        return None, None
    spec = importlib.util.spec_from_file_location(f"subsetsearch_{gkey}", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path


def unit_names(mod, src: str):
    """Module-level re.Pattern attrs that DRIVE a rule block, in SOURCE order.

    A selectable unit is a pattern the extract function iterates with
    `.finditer(` — that is how every generated rule block consumes its main
    pattern. Patterns used only via .search/.match/.findall are guards
    (_KEYWORDS, _TRIGGER, _GATE, ...) inside other rules' blocks: they stay
    always-active, because neutering a guard while testing another unit would
    distort that unit's behaviour. Name case is meaningless — theoremlike
    names ALL its drivers `_X_RE` (the known rule_name/var-name mismatch)."""
    pats = [n for n, v in vars(mod).items()
            if isinstance(v, re.Pattern) and f"{n}.finditer(" in src]
    order = {}
    for i, m in enumerate(re.finditer(
            r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*re\.compile", src, re.M)):
        order.setdefault(m.group(1), i)
    return sorted(pats, key=lambda n: order.get(n, 10**6))


def item_type(d: dict, gkey: str) -> str:
    t = d.get("structure_type")
    return t if t in TYPES else GROUPS[gkey][0]


def _safe_call(fn, arg):
    """Call an extract function; time bounds come from rule_guard (an outer
    SIGALRM would be cancelled by the guard's own setitimer anyway)."""
    try:
        return fn(arg)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# precompute
# ---------------------------------------------------------------------------

_PC = {}


def _pc_init(eval_dir, tex_dir, threshold, budget):
    _PC["eval_dir"] = Path(eval_dir)
    _PC["tex_dir"] = Path(tex_dir)
    # Production parses these modules under rule_guard (SIGALRM per pattern
    # call + per-document budget + process-wide quarantine). Unguarded, a
    # single full-group call can hang for minutes on a 56KB paper, and the
    # recorded scores we validate against were produced WITH the guard — so
    # running guarded is required for both speed and fidelity. The source tag
    # deliberately does not end in ".py": rule_guard comments quarantined
    # rules out AT SOURCE when it does, and precompute must never edit the
    # rule files.
    import rule_guard
    rule_guard.configure(threshold=threshold, budget=budget)
    _PC["rg"] = rule_guard
    _PC["mods"] = {}
    for g in GROUPS:
        mod, path = load_group_module(_PC["eval_dir"], g)
        if mod is None:
            continue
        src = path.read_text(encoding="utf-8")
        units = unit_names(mod, src)          # BEFORE guarding: needs re.Pattern
        rule_guard.guard_module(mod, source_path=f"<subset-search:{g}>")
        _PC["mods"][g] = {
            "mod": mod,
            "fn": getattr(mod, f"extract_distilled_{g}", None),
            "units": units,
            "uses_spans": ("seen_spans" in src or "_overlaps" in src),
        }


def _norm_items(raw_results, gkey, text):
    out = []
    for d in raw_results or []:
        raw = (d.get("raw_latex") or "").strip()
        if not raw:
            continue
        out.append({
            "raw": raw,
            "clean": d.get("clean_text") or "",
            "name": d.get("name"),
            "type": item_type(d, gkey),
            "span": text.find(raw),
        })
    return out


def _precompute_paper(pid: str):
    from silver_distillation_sequential import _find_main_tex
    from math_paper_parser import PaperParser

    t0 = time.perf_counter()
    src_dir = _PC["tex_dir"] / pid / "source"
    main_tex = _find_main_tex(src_dir)
    if not main_tex:
        return pid, {"error": f"no main tex under {src_dir}"}

    # -- baseline parse; capture the text the parser feeds distilled rules --
    captured = {}
    orig = PaperParser._apply_distilled_rules

    def _cap(self, text, stype):
        captured["text"] = text
        return []

    PaperParser._apply_distilled_rules = _cap
    try:
        parser = PaperParser(paper_id=pid, extraction_mode="rules",
                             structure_types=list(TYPES))
        graph = parser.parse_file(str(main_tex))
    except Exception as e:
        return pid, {"error": f"baseline parse failed: {e}"}
    finally:
        PaperParser._apply_distilled_rules = orig

    base = {t: [] for t in TYPES}
    for _oid, obj in graph.to_dict().get("objects", {}).items():
        kind = obj.get("kind")
        if kind in base:
            raw = (obj.get("raw_latex") or obj.get("statement") or "").strip()
            if raw:
                base[kind].append({"raw": raw,
                                   "clean": obj.get("clean_text") or ""})
    text = captured.get("text")
    if text is None:
        # parser never reached the distilled hook (empty paper?): fall back
        text = main_tex.read_text(encoding="utf-8", errors="replace")

    rec = {"paper_id": pid, "base": base, "groups": {},
           "baseline_secs": round(time.perf_counter() - t0, 2)}
    rg = _PC["rg"]
    rg.new_document()          # reset per-doc budgets (quarantine persists)

    for gkey, G in _PC["mods"].items():
        if G["fn"] is None:
            continue
        mod, units = G["mod"], G["units"]
        tg = time.perf_counter()
        print(f"    [{pid}] group {gkey}: {len(units)} units...", flush=True)
        saved = {n: getattr(mod, n) for n in units}
        try:
            # floor: every unit neutered
            for n in units:
                setattr(mod, n, NEVER)
            floor_raw = _safe_call(G["fn"], text)
            floor = _norm_items(floor_raw, gkey, text)
            floor_keys = defaultdict(int)
            for it in floor:
                floor_keys[(it["type"], it["raw"])] += 1

            per_unit = {}
            for n in units:
                for m in units:
                    setattr(mod, m, NEVER)
                setattr(mod, n, saved[n])
                q0 = {r["rule_name"] for r in rg.quarantined()}
                tu = time.perf_counter()
                res = _safe_call(G["fn"], text)
                secs = time.perf_counter() - tu
                timed_out = n in ({r["rule_name"] for r in rg.quarantined()}
                                  - q0) or n in q0
                items = _norm_items(res, gkey, text)
                # subtract floor output (multiset): items every run produces
                seen = defaultdict(int)
                own = []
                for it in items:
                    k = (it["type"], it["raw"])
                    seen[k] += 1
                    if seen[k] > floor_keys.get(k, 0):
                        own.append(it)
                per_unit[n] = {"items": own, "secs": round(secs, 3),
                               "timeout": timed_out}

            # full: everything active (validation anchor; guarded, like
            # production's own parse of this state)
            for n in units:
                setattr(mod, n, saved[n])
            full_raw = _safe_call(G["fn"], text)
            rec["groups"][gkey] = {
                "units": units,
                "uses_spans": G["uses_spans"],
                "floor": floor,
                "per_unit": per_unit,
                "full": _norm_items(full_raw, gkey, text),
            }
            n_to = sum(1 for u in per_unit.values() if u["timeout"])
            print(f"    [{pid}] group {gkey}: done in "
                  f"{time.perf_counter() - tg:.0f}s"
                  + (f", {n_to} timeout(s)" if n_to else ""), flush=True)
        finally:
            for n, v in saved.items():
                setattr(mod, n, v)

    rec["quarantined"] = sorted({r["rule_name"] for r in rg.quarantined()})
    rec["total_secs"] = round(time.perf_counter() - t0, 2)
    return pid, rec


def cmd_precompute(args):
    eval_dir = Path(args.eval_dir).resolve()
    out_dir = eval_dir / "subset_search" / "precompute"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Without the group modules every paper still "succeeds" -- it just does
    # the baseline parse and records zero units, and the whole run looks fine
    # until every arm scores identically to the base parser. Fail here instead.
    missing = [g for g in GROUPS
               if not (eval_dir / "groups" / g / "distilled_rules.py").is_file()]
    if len(missing) == len(GROUPS):
        raise SystemExit(
            f"[precompute] no distilled rule modules under {eval_dir/'groups'}\n"
            f"  Expected groups/<{'|'.join(GROUPS)}>/distilled_rules.py.\n"
            f"  Without them every paper records zero units and the scores are\n"
            f"  silently just the base parser. Nothing has been written.")
    if missing:
        print(f"[precompute] WARNING: no rules for group(s) {', '.join(missing)}"
              f" -- those groups contribute nothing")

    papers = resolve_papers(args, eval_dir)
    todo = [p for p in papers
            if args.force or not (out_dir / f"{p}.json").exists()]
    print(f"[precompute] {len(papers)} paper(s), {len(todo)} to do, "
          f"workers={args.workers}, rule_guard {args.rg_threshold}s/"
          f"{args.rg_budget}s")
    if not todo:
        return
    t0 = time.perf_counter()
    initargs = (str(eval_dir), str(Path(args.tex_dir).resolve()),
                args.rg_threshold, args.rg_budget)
    if args.workers > 1:
        with mp.Pool(args.workers, initializer=_pc_init, initargs=initargs) as pool:
            it = pool.imap_unordered(_precompute_paper, todo)
            _drain(it, out_dir, len(todo))
    else:
        _pc_init(*initargs)
        _drain((_precompute_paper(p) for p in todo), out_dir, len(todo))
    print(f"[precompute] done in {time.perf_counter() - t0:.0f}s -> {out_dir}")


def _drain(it, out_dir, total):
    done = 0
    for pid, rec in it:
        done += 1
        (out_dir / f"{pid}.json").write_text(
            json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        err = rec.get("error")
        n_items = sum(len(u["items"]) for g in rec.get("groups", {}).values()
                      for u in g["per_unit"].values())
        print(f"  [{done}/{total}] {pid}  "
              + (f"ERROR: {err}" if err else
                 f"{rec['total_secs']}s, {n_items} unit-items"), flush=True)


# ---------------------------------------------------------------------------
# search: replay + exact scorer
# ---------------------------------------------------------------------------

class Store:
    """Precompute records + gold + token caches for the search phase."""

    def __init__(self, eval_dir: Path, papers):
        import match_modes as mm
        from latex_clean import clean_latex_to_text
        self.mm = mm
        self._mtok_fn = clean_latex_to_text
        self.eval_dir = eval_dir
        pc_dir = eval_dir / "subset_search" / "precompute"
        self.recs = {}
        for pid in papers:
            f = pc_dir / f"{pid}.json"
            if not f.exists():
                print(f"  [warn] no precompute for {pid}; skipped")
                continue
            r = json.loads(f.read_text(encoding="utf-8"))
            if r.get("error"):
                print(f"  [warn] {pid}: {r['error']}; skipped")
                continue
            self.recs[pid] = r
        self.papers = sorted(self.recs)

        from silver_distillation_sequential import FNAME_MAP
        gold_dir = eval_dir / "silver_gold"
        self.gold = {t: {} for t in TYPES}
        for t in TYPES:
            f = gold_dir / FNAME_MAP[t]
            if not f.exists():
                continue
            with open(f, encoding="utf-8-sig", errors="replace") as fh:
                for row in csv.DictReader(fh):
                    pid = (row.get("paper_id") or "").strip()
                    raw = (row.get("Gold_Standard_raw_latex") or "").strip()
                    if pid in self.recs and raw:
                        self.gold[t].setdefault(pid, []).append(raw)

        self._stok = {}   # silver-profile tokens (matching metric)
        self._mtok = {}   # parser-cleaner tokens (merge dedup)
        # unit ids are namespaced "group:name" — pattern names are only
        # unique within one group module
        self.unit_group = {}
        self.unit_papers = defaultdict(set)
        self.unit_secs = defaultdict(float)
        self.unit_timeouts = defaultdict(int)
        for pid, r in self.recs.items():
            for g, G in r["groups"].items():
                for u, U in G["per_unit"].items():
                    uid = f"{g}:{u}"
                    self.unit_group[uid] = g
                    self.unit_secs[uid] += U["secs"]
                    if U.get("timeout"):
                        self.unit_timeouts[uid] += 1
                    if U["items"]:
                        self.unit_papers[uid].add(pid)
        self.all_units = sorted(self.unit_group,
                                key=lambda u: (self.unit_group[u], u))
        # a pattern rule_guard ever quarantined cannot run in production
        # either — keep it out of the candidate pool
        self.quarantined_units = set()
        for pid, r in self.recs.items():
            for name in r.get("quarantined", []):
                for g, G in r["groups"].items():
                    if name in G["units"]:
                        self.quarantined_units.add(f"{g}:{name}")
        # gold token cache + per-paper support (gold across all types: m3)
        self.gold_toks = {}
        self.support_toks = defaultdict(list)
        for t in TYPES:
            for pid, texts in self.gold[t].items():
                self.gold_toks[(pid, t)] = [self.stok(x) for x in texts]
                self.support_toks[pid].extend(self.gold_toks[(pid, t)])

    def stok(self, text):
        r = self._stok.get(text)
        if r is None:
            r = self._stok[text] = frozenset(self.mm.tokens(text))
        return r

    def mtok(self, raw, clean):
        key = raw or clean
        r = self._mtok.get(key)
        if r is None:
            r = self._mtok[key] = frozenset(
                self._mtok_fn(key).lower().split())
        return r

    # -- replay -------------------------------------------------------------

    def candidates(self, pid, active):
        """Per-group ordered candidate items for a unit subset, with the
        in-function span suppression replayed in source order."""
        r = self.recs[pid]
        out = {}
        for g, G in r["groups"].items():
            items = list(G["floor"])
            for u in G["units"]:
                if f"{g}:{u}" in active:
                    items.extend(G["per_unit"][u]["items"])
            if G["uses_spans"]:
                kept, spans = [], []
                for it in items:
                    s = it.get("span", -1)
                    if s is not None and s >= 0:
                        e = s + len(it["raw"])
                        if any(s < ke and e > ks for ks, ke in spans):
                            continue
                        spans.append((s, e))
                    kept.append(it)
                items = kept
            out[g] = items
        return out

    def merged_texts(self, pid, active):
        """_merge_objects replica: {type: [raw_latex,...]} after dedup."""
        r = self.recs[pid]
        cands = self.candidates(pid, active)
        by_type = defaultdict(list)
        for g, items in cands.items():
            for it in items:
                by_type[it["type"]].append(it)
        out = {}
        for t in TYPES:
            base = r["base"].get(t, [])
            kept_raw = [b["raw"] for b in base]
            seen_texts = {(b["clean"] or "").strip().lower() for b in base}
            kept_toks = [self.mtok(b["raw"], b["clean"]) for b in base]
            for it in by_type.get(t, []):
                txt = (it["clean"] or "").strip().lower()
                if txt in seen_texts:
                    continue
                dt = self.mtok(it["raw"], it["clean"])
                if dt and any(
                        kt and len(dt & kt) / min(len(dt), len(kt)) >= 0.7
                        for kt in kept_toks):
                    continue
                kept_raw.append(it["raw"])
                seen_texts.add(txt)
                kept_toks.append(dt)
            out[t] = kept_raw
        return out

    # -- exact metrics() replica on token sets ------------------------------

    def _counts_type(self, ext_toks, gold_toks, support, mode,
                     threshold=0.7, cover=0.7):
        cont = self.mm.sym_containment
        pairs = []
        for i, e in enumerate(ext_toks):
            for j, g in enumerate(gold_toks):
                s = cont(e, g)
                if s >= threshold:
                    pairs.append((s, i, j))
        pairs.sort(reverse=True)
        m_ext, m_gold = set(), set()
        for _s, i, j in pairs:
            if i in m_ext or j in m_gold:
                continue
            m_ext.add(i)
            m_gold.add(j)
        if mode == "m1":
            tp = tp_recall = len(m_ext)
            return {"tp": tp, "tp_recall": tp_recall,
                    "fp": len(ext_toks) - tp, "fn": len(gold_toks) - tp}
        cov = self.mm.coverage
        tp = 0
        for i, e in enumerate(ext_toks):
            if i in m_ext or any(cov(e, g) >= cover for g in support if g):
                tp += 1
        union = frozenset().union(*ext_toks) if ext_toks else frozenset()
        tp_recall = 0
        for g in gold_toks:
            if not g:
                continue
            if any(cont(e, g) >= threshold for e in ext_toks) \
                    or cov(g, union) >= cover:
                tp_recall += 1
        return {"tp": tp, "tp_recall": tp_recall,
                "fp": len(ext_toks) - tp, "fn": len(gold_toks) - tp_recall}

    def score_paper(self, pid, active):
        """{mode: {tp, tp_recall, fp, fn}} pooled over types for one paper."""
        merged = self.merged_texts(pid, active)
        support = self.support_toks.get(pid, [])
        out = {}
        for mode in ("m1", "m3"):
            agg = {"tp": 0, "tp_recall": 0, "fp": 0, "fn": 0}
            for t in TYPES:
                ext = [self.stok(x) for x in merged.get(t, [])]
                gold = self.gold_toks.get((pid, t), [])
                if not ext and not gold:
                    continue
                c = self._counts_type(ext, gold, support, mode)
                for k in agg:
                    agg[k] += c[k]
            out[mode] = agg
        return out


def prf(agg):
    p = agg["tp"] / (agg["tp"] + agg["fp"]) if agg["tp"] + agg["fp"] else 0.0
    r = (agg["tp_recall"] / (agg["tp_recall"] + agg["fn"])
         if agg["tp_recall"] + agg["fn"] else 0.0)
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f1


def pool_counts(per_paper, papers, mode):
    agg = {"tp": 0, "tp_recall": 0, "fp": 0, "fn": 0}
    for pid in papers:
        for k in agg:
            agg[k] += per_paper[pid][mode][k]
    return agg


# ---------------------------------------------------------------------------
# search driver (algorithms live in rule_subset_algos.py)
# ---------------------------------------------------------------------------

class Search:
    """In-memory replay bound to one paper set + objective mode.

    This is the entire surface the algorithms in rule_subset_algos.py touch;
    keep it stable when adding a new --search-algo."""

    def __init__(self, store: Store, papers, objective="m3"):
        self.st = store
        self.papers = list(papers)
        self.paper_set = set(self.papers)
        self.obj = objective
        self._pool = None

    # -- candidate pool -----------------------------------------------------

    def candidate_units(self):
        """Units eligible for selection: never quarantined by rule_guard (they
        cannot run in production either), and firing on at least one of MY
        papers (a unit that produces nothing here can never change a score)."""
        if self._pool is None:
            self._pool = [u for u in self.st.all_units
                          if u not in self.st.quarantined_units
                          and self.st.unit_papers[u] & self.paper_set]
        return self._pool

    # -- scoring ------------------------------------------------------------

    def evaluate(self, active):
        return {pid: self.st.score_paper(pid, active) for pid in self.papers}

    def rescore(self, per_paper, active, changed):
        """Incremental re-score of `active`, reusing untouched papers.

        `active` must already be the NEW subset; `changed` is the set of units
        whose membership differs from the one `per_paper` was computed for.
        unit_papers is an exact affected-set, not a heuristic: a unit that
        emitted no items on a paper cannot alter that paper's replay."""
        out = dict(per_paper)
        todo = set()
        for u in changed:
            todo |= self.st.unit_papers[u] & self.paper_set
        for pid in todo:
            out[pid] = self.st.score_paper(pid, active)
        return out

    def pooled_counts(self, per_paper, mode=None):
        return pool_counts(per_paper, self.papers, mode or self.obj)

    def pooled_f1(self, per_paper, mode=None):
        return prf(self.pooled_counts(per_paper, mode))[2]

    # -- reporting ----------------------------------------------------------

    def row(self, step, unit, per_paper, note=None, eval_papers=None):
        row = {"step": step, "unit": unit, "note": note}
        for mode in ("m1", "m3"):
            p, r, f1 = prf(pool_counts(per_paper, self.papers, mode))
            row.update({f"{mode}_p": round(p, 4), f"{mode}_r": round(r, 4),
                        f"{mode}_f1": round(f1, 4)})
        return row


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def resolve_papers(args, eval_dir):
    if args.papers:
        return [p.strip() for p in args.papers.split(",") if p.strip()]
    split_csv = REPO / "corpus" / "silver" / "split_opus5.csv"
    out = []
    with open(split_csv, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("split") or "").strip() == args.split:
                out.append(row["arxiv_id"].strip())
    return sorted(out)


def load_recorded_scores(eval_dir):
    """{(state, mode, pid): (tp, tp_recall, fp, fn)} from the run's scores.jsonl."""
    path = eval_dir / "trajectory" / "scores.jsonl"
    if not path.exists():
        return {}
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            out[(r["state"], r["mode"], r["paper_id"])] = (
                r.get("tp", 0), r.get("tp_recall", r.get("tp", 0)),
                r.get("fp", 0), r.get("fn", 0))
    return out


def algo_opts(args):
    """CLI flags -> the options dict every algorithm in rule_subset_algos reads."""
    return {
        "patience": args.patience,
        "seed": args.seed,
        "ls_seed": args.ls_seed,
        "ls_rounds": args.ls_rounds,
        "ls_swap_width": args.ls_swap_width,
        "distorted_k": args.distorted_k,
        "distorted_anchor": args.anchor,
        "dink_anchor": args.anchor,
        "dink_rounds": args.dink_rounds,
        "dink_inner": args.dink_inner,
        "poss_iters": args.poss_iters,
        "poss_seed": args.poss_seed,
    }


def ladder_val_curve(vs, ladder, kmax):
    """Score a size ladder on a held-out fold, as a step function of k.

    A ladder rung is (size, units). Greedy-family ladders are dense (one rung
    per k); a Pareto front is sparse. Reading the largest rung with size <= k
    puts both on the same k axis, so folds running different algorithms -- or
    the same algorithm reaching different front sizes -- still average."""
    pts = sorted((k, set(u)) for k, u in ladder)
    out, i, last, cache = [], 0, set(), {}
    for k in range(kmax + 1):
        while i < len(pts) and pts[i][0] <= k:
            last = pts[i][1]
            i += 1
        key = frozenset(last)
        if key not in cache:
            cache[key] = vs.pooled_f1(vs.evaluate(last))
        out.append(cache[key])
    return out


def planned_outputs(out_dir, args):
    """Every file a search run would write, resolved before any work starts.

    Nothing here is opened, so callers can refuse the whole run if any target
    already exists. --validate-only writes nothing at all."""
    if args.validate_only:
        return []
    tag = args.out_tag or args.search_algo
    paths = [out_dir / f"{tag}_curve.csv", out_dir / f"selection_{tag}.json"]
    if args.cv > 1:
        paths.append(out_dir / f"cv_curves_{tag}.csv")
    if args.search_algo == "greedy" and not args.out_tag:
        # the historical filenames the Sep-01 report reads
        paths += [out_dir / "greedy_curve.csv", out_dir / "selection.json"]
        if args.cv > 1:
            paths.append(out_dir / "cv_curves.csv")
    # greedy without --out-tag names <tag>_curve.csv and greedy_curve.csv the
    # same file; de-dup so the refusal message lists each path once
    return list(dict.fromkeys(paths))


def guard_outputs(out_dir, args):
    """Refuse to clobber. These outputs are untracked by git, so an overwrite
    is unrecoverable -- the run must fail BEFORE the search burns any time."""
    existing = [q for q in planned_outputs(out_dir, args) if q.exists()]
    if not existing and not args.overwrite:
        return
    if not existing and args.overwrite:
        print("[search] --overwrite given, but no output file exists yet")
        return
    if not args.overwrite:
        names = "\n".join(f"    {q.name}" for q in existing)
        raise SystemExit(
            f"[search] REFUSING TO RUN: these output files already exist in\n"
            f"  {out_dir}\n{names}\n"
            f"  Nothing has been written or deleted.\n"
            f"  Either pass --out-tag NAME to write a fresh set of files, or\n"
            f"  pass --overwrite to replace the ones listed above.")
    print("[search] --overwrite: these files WILL be replaced: "
          + ", ".join(q.name for q in existing))


def cmd_search(args):
    eval_dir = Path(args.eval_dir).resolve()
    out_dir = eval_dir / "subset_search"
    out_dir.mkdir(parents=True, exist_ok=True)
    algo = args.search_algo
    opts = algo_opts(args)
    tag = args.out_tag or algo
    guard_outputs(out_dir, args)          # before any work, before any write
    papers = resolve_papers(args, eval_dir)
    print(f"[search] loading precompute for {len(papers)} paper(s)")
    st = Store(eval_dir, papers)
    papers = st.papers
    per_g = defaultdict(int)
    for g in st.unit_group.values():
        per_g[g] += 1
    print(f"[search] {len(papers)} usable papers, {len(st.all_units)} units "
          f"({', '.join(f'{g}:{n}' for g, n in sorted(per_g.items()))})")

    # ---- anchors + validation ----
    all_units = set(st.all_units)
    base_pp = {pid: st.score_paper(pid, set()) for pid in papers}
    full_pp = {pid: st.score_paper(pid, all_units) for pid in papers}
    for label, pp in (("base(0 rules)", base_pp), ("full(all rules)", full_pp)):
        for mode in ("m1", "m3"):
            p, r, f1 = prf(pool_counts(pp, papers, mode))
            print(f"  [anchor] {label:15s} {mode}: "
                  f"P={p:.4f} R={r:.4f} F1={f1:.4f}")

    rec = load_recorded_scores(eval_dir)
    if rec:
        states = sorted({s for s, _m, _p in rec},
                        key=lambda s: (s != "base", s))
        last = [s for s in states if s.startswith("after")]
        last = max(last, key=lambda s: int(s.split()[1])) if last else None
        for state, pp in (("base", base_pp), (last, full_pp)):
            if state is None:
                continue
            for mode in ("m1", "m3"):
                mine = pool_counts(pp, papers, mode)
                have = [pid for pid in papers if (state, mode, pid) in rec]
                if not have:
                    continue
                theirs = {"tp": 0, "tp_recall": 0, "fp": 0, "fn": 0}
                for pid in have:
                    tp, tpr, fp, fn = rec[(state, mode, pid)]
                    theirs["tp"] += tp
                    theirs["tp_recall"] += tpr
                    theirs["fp"] += fp
                    theirs["fn"] += fn
                mine_sub = pool_counts(
                    {p_: base_pp[p_] if state == "base" else full_pp[p_]
                     for p_ in have}, have, mode)
                f_mine, f_thr = prf(mine_sub)[2], prf(theirs)[2]
                print(f"  [validate] {state:9s} {mode}: replay F1={f_mine:.4f} "
                      f"recorded F1={f_thr:.4f} (Δ={f_mine - f_thr:+.4f}, "
                      f"{len(have)} papers)")
    if args.validate_only:
        return

    # ---- CV: honest stopping size + held-out estimate ----
    k_star = None
    cv_info = {}
    if args.cv > 1:
        print(f"[search] {args.cv}-fold CV (algo={algo})")
        folds = [papers[i::args.cv] for i in range(args.cv)]
        val_curves, val_points, ladder_kmax = [], [], 0
        full_points = []
        fold_res = []
        for fi, val in enumerate(folds):
            train = [p for p in papers if p not in val]
            s = Search(st, train, objective=args.objective)
            res = algos.run(algo, s, opts,
                            log=lambda m, _f=fi: print(f"  [cv{_f}]{m[2:]}"))
            vs = Search(st, val, objective=args.objective)
            f_sel = vs.pooled_f1(vs.evaluate(set(res.selected)))
            val_points.append(f_sel)
            # The baseline the whole exercise is judged against: keeping EVERY
            # rule, scored on the same held-out papers. Selection only earns
            # its place in the pipeline if it beats this. Measured per fold so
            # it can be compared paired, cancelling fold difficulty.
            f_full = vs.pooled_f1(vs.evaluate(set(st.all_units)))
            full_points.append(f_full)
            print(f"  [cv{fi}] val F1: selection (|S|={len(res.selected)}) "
                  f"{f_sel:.4f} vs all-rules {f_full:.4f} "
                  f"({f_sel - f_full:+.4f})")
            fold_res.append((vs, res))
            if res.ladder:
                ladder_kmax = max(ladder_kmax, max(k for k, _ in res.ladder))
        mean_sel = sum(val_points) / len(val_points)
        # NOTE: each fold scores the algorithm's own selection as it comes out,
        # before the k* cut and the backward polish applied to the final run, so
        # this estimates the uncut procedure, not the selection written below.
        print(f"[search] CV held-out F1 of the per-fold selections (uncut, unpolished): "
              f"mean {mean_sel:.4f} "
              f"({', '.join(f'{v:.4f}' for v in val_points)})")
        cv_info["heldout_f1_per_fold"] = [round(v, 4) for v in val_points]
        cv_info["heldout_f1_mean"] = round(mean_sel, 4)
        cv_info["heldout_f1_note"] = ("per-fold selections before the k* cut and the "
                                      "polish; not an estimate for the final selection")
        mean_full = sum(full_points) / len(full_points)
        diffs = [a - b for a, b in zip(val_points, full_points)]
        wins = sum(1 for d in diffs if d > 0)
        cv_info["heldout_f1_allrules_per_fold"] = [round(v, 4) for v in full_points]
        cv_info["heldout_f1_allrules_mean"] = round(mean_full, 4)
        cv_info["heldout_gain_vs_allrules_per_fold"] = [round(d, 4) for d in diffs]
        cv_info["heldout_gain_vs_allrules_mean"] = round(mean_sel - mean_full, 4)
        cv_info["folds_beating_allrules"] = wins
        print(f"[search] CV all-rules baseline: mean {mean_full:.4f} "
              f"({', '.join(f'{v:.4f}' for v in full_points)})")
        print(f"[search] CV SELECTION vs ALL RULES: "
              f"{mean_sel - mean_full:+.4f} mean, wins {wins}/{len(diffs)} folds"
              + ("  <- selection is NOT paying for itself"
                 if mean_sel <= mean_full else ""))

        # A stopping size is only meaningful for algorithms that expose a
        # size ladder (a greedy path's prefixes, or a Pareto front). Rungs
        # are indexed by |S|, not by position, so a sparse front (poss) and a
        # dense path (greedy) average onto the same k axis.
        for vs, res in fold_res:
            if res.ladder:
                val_curves.append(ladder_val_curve(vs, res.ladder, ladder_kmax))
        if val_curves:
            mean_curve = [sum(v[k] for v in val_curves) / len(val_curves)
                          for k in range(ladder_kmax + 1)]
            k_star = mean_curve.index(max(mean_curve))
            cvf = out_dir / f"cv_curves_{tag}.csv"
            with open(cvf, "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["k"] + [f"fold{i}_val_f1"
                                    for i in range(len(val_curves))]
                           + ["mean_val_f1"])
                for k in range(ladder_kmax + 1):
                    w.writerow([k] + [round(v[k], 4) for v in val_curves]
                               + [round(mean_curve[k], 4)])
            if algo == "greedy" and not args.out_tag:
                (out_dir / "cv_curves.csv").write_text(
                    cvf.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"[search] CV: k*={k_star} (mean val F1 "
                  f"{mean_curve[k_star]:.4f} vs k=0 {mean_curve[0]:.4f})")
            cv_info["k_star"] = k_star
            cv_info["k_star_val_f1"] = round(mean_curve[k_star], 4)
        else:
            print(f"[search] {algo} exposes no size ladder; CV reports a "
                  f"held-out estimate only, no k* cut")

    # ---- final run on all papers ----
    print(f"[search] final {algo} on {len(papers)} papers "
          f"(objective={args.objective})")
    s = Search(st, papers, objective=args.objective)
    t_algo = time.perf_counter()
    res = algos.run(algo, s, opts)
    algo_secs = time.perf_counter() - t_algo
    sel, curve = list(res.selected), res.curve
    if k_star is not None and res.ladder:
        # largest rung no bigger than k*; for a greedy path this is exactly
        # the old prefix cut, for a Pareto front it is the nearest rung below
        rungs = sorted((k, u) for k, u in res.ladder if k <= k_star)
        if rungs:
            sel = sorted(rungs[-1][1])
            print(f"[search] cut selection to CV k*={k_star} "
                  f"(ladder rung k={rungs[-1][0]})")
    if args.no_polish:
        f1_sel = s.pooled_f1(s.evaluate(set(sel)))
    else:
        sel, f1_sel = algos.polish(s, sel)

    curve_path = out_dir / f"{tag}_curve.csv"
    if curve:
        fields = list(curve[0])
        with open(curve_path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows([{k: r.get(k) for k in fields} for r in curve])

    sel_pp = {pid: st.score_paper(pid, set(sel)) for pid in papers}
    report = {
        "algo": algo,
        "algo_options": opts,
        "algo_secs": round(algo_secs, 1),
        "algo_info": res.info,
        "papers": papers,
        "objective": args.objective,
        "cv_folds": args.cv,
        "cv": cv_info,
        "k_star": k_star,
        "polished": not args.no_polish,
        "n_units_total": len(st.all_units),
        "quarantined_units": sorted(st.quarantined_units),
        "selected_units": sel,
        "dropped_units": sorted(all_units - set(sel)),
        "scores": {},
        "unit_meta": {u: {"group": st.unit_group[u],
                          "papers_fired": len(st.unit_papers[u]),
                          "total_secs": round(st.unit_secs[u], 2),
                          "timeouts": st.unit_timeouts[u]}
                     for u in st.all_units},
    }
    print("[search] results (pooled over train):")
    for label, pp in (("base", base_pp), ("full", full_pp),
                      ("selected", sel_pp)):
        report["scores"][label] = {}
        for mode in ("m1", "m3"):
            p, r, f1 = prf(pool_counts(pp, papers, mode))
            report["scores"][label][mode] = {
                "precision": round(p, 4), "recall": round(r, 4),
                "f1": round(f1, 4)}
            print(f"  {label:9s} {mode}: P={p:.4f} R={r:.4f} F1={f1:.4f}")
    print(f"[search] selected {len(sel)}/{len(st.all_units)} units "
          f"in {algo_secs:.0f}s")
    sel_path = out_dir / f"selection_{tag}.json"
    sel_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if algo == "greedy" and not args.out_tag:
        # legacy names the Sep-01 report reads
        (out_dir / "selection.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")
    print(f"[search] wrote {sel_path.name} and {curve_path.name}")


def cmd_score(args):
    """Score already-chosen rule subsets on a paper set they never touched.

    The search phase answers "which subset", using CV inside the papers the
    rules were distilled from. That comparison cannot settle anything against
    keeping every rule, because those papers wrote the rules. This scores a
    finished selection on the held-out split instead: same replay, same exact
    metrics() replica, papers that entered no stage of distillation OR
    selection. It needs a precompute pass over THOSE papers first."""
    eval_dir = Path(args.eval_dir).resolve()
    papers = resolve_papers(args, eval_dir)
    print(f"[score] loading precompute for {len(papers)} {args.split} paper(s)")
    st = Store(eval_dir, papers)
    papers = st.papers
    if not papers:
        raise SystemExit(f"[score] no usable precompute for split {args.split!r};"
                         f" run `precompute --split {args.split}` first")
    print(f"[score] {len(papers)} usable papers, {len(st.all_units)} units present")

    sel_files = []
    for pat in args.selections:
        sel_files.extend(sorted(Path().glob(pat)) if any(c in pat for c in "*?[")
                         else [Path(pat)])
    if not sel_files:
        raise SystemExit("[score] --selections matched no files")

    all_units = set(st.all_units)
    rows = []

    def one(label, units, k=None):
        units = set(units) & all_units      # units absent here never fire
        pp = {pid: st.score_paper(pid, units) for pid in papers}
        out = {"arm": label, "rules": len(units) if k is None else k,
               "rules_active_here": len(units),
               "parse_secs": round(sum(st.unit_secs[u] for u in units), 1)}
        for mode in ("m1", "m3"):
            pr, rc, f1 = prf(pool_counts(pp, papers, mode))
            out[f"{mode}_p"] = round(pr, 4)
            out[f"{mode}_r"] = round(rc, 4)
            out[f"{mode}_f1"] = round(f1, 4)
        rows.append(out)
        print(f"  {label:<28} k={out['rules']:>4}  "
              f"m3 P={out['m3_p']:.4f} R={out['m3_r']:.4f} F1={out['m3_f1']:.4f}  "
              f"parse={out['parse_secs']:.0f}s")
        return out

    print("[score] anchors:")
    base = one("base (no rules)", set())
    full = one("all rules", all_units)

    print("[score] selections:")
    for f in sel_files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"  [warn] {f.name}: {e}; skipped")
            continue
        units = d.get("selected_units")
        if not units:
            print(f"  [warn] {f.name}: no selected_units; skipped")
            continue
        label = args.label_from and d.get(args.label_from) or f.stem.replace("selection_", "")
        one(label, units, k=len(units))

    full_parse = full["parse_secs"] or 1.0
    for r in rows:
        r["parse_pct_of_all"] = round(100 * r["parse_secs"] / full_parse, 1)
        r["m3_f1_vs_all"] = round(r["m3_f1"] - full["m3_f1"], 4)

    out_path = Path(args.out) if args.out else (
        eval_dir / "subset_search" / f"heldout_scores_{args.split}.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"[score] wrote {out_path}")
    if args.split == "train" and not args.papers:
        print(f"[score] NOTE: scored on the {len(papers)} TRAIN papers -- these "
              f"chose the rules AND wrote them, so this is not a held-out number")
    else:
        print(f"[score] every F1 above is on {len(papers)} {args.split} papers "
              f"that entered no stage of distillation or selection")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("precompute", help="per-rule isolated extraction runs")
    pc.add_argument("--eval-dir", required=True)
    pc.add_argument("--tex-dir", required=True)
    pc.add_argument("--papers", help="comma list; default: split papers")
    pc.add_argument("--split", default="train",
                    help="split_opus5.csv split to use (default train)")
    pc.add_argument("--workers", type=int, default=4)
    pc.add_argument("--rg-threshold", type=float, default=5.0,
                    help="rule_guard single-call cap (production: 5s)")
    pc.add_argument("--rg-budget", type=float, default=10.0,
                    help="rule_guard per-document budget (production: 10s)")
    pc.add_argument("--force", action="store_true")
    pc.set_defaults(fn=cmd_precompute)

    se = sub.add_parser(
        "search", help="subset selection (in-memory; no parsing, no LLM)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Algorithms, classical -> contemporary:\n"
                    + "\n".join(f"  {n:<12s} {b}"
                                for n, b in algos.BLURBS.items()))
    se.add_argument("--eval-dir", required=True)
    se.add_argument("--papers", help="comma list; default: split papers")
    se.add_argument("--split", default="train")
    se.add_argument("--objective", choices=["m1", "m3"], default="m3")
    se.add_argument("--cv", type=int, default=5,
                    help="folds for stopping-size CV; 1 = off")
    se.add_argument("--validate-only", action="store_true")
    se.add_argument("--overwrite", action="store_true",
                    help="allow replacing existing output files; without it "
                         "the run refuses to start if any target exists")
    se.add_argument("--out-tag",
                    help="suffix for the output files; default: the algo name."
                         " Set it to compare algorithms without clobbering.")

    sa = se.add_argument_group("algorithm")
    sa.add_argument("--search-algo", choices=list(algos.ALGOS),
                    default="greedy",
                    help="; ".join(f"{n}: {b}" for n, b in algos.BLURBS.items()))
    sa.add_argument("--patience", type=int, default=25,
                    help="forward-selection steps without improvement before "
                         "stopping (greedy, lazy, and the seeds/inner solves "
                         "built on them)")
    sa.add_argument("--no-polish", action="store_true",
                    help="skip the backward-elimination post-pass")
    sa.add_argument("--seed", type=int, default=0,
                    help="RNG seed (poss, porss)")
    sa.add_argument("--anchor", choices=["full", "empty"], default="full",
                    help="where the F1 ratio is linearised for distorted / "
                         "dinkelbach; 'full' = the all-rules state this tool "
                         "exists to prune")

    sl = se.add_argument_group("localsearch")
    sl.add_argument("--ls-seed", choices=["greedy", "full", "empty"],
                    default="greedy", help="starting subset")
    sl.add_argument("--ls-rounds", type=int, default=30,
                    help="max improving moves before giving up")
    sl.add_argument("--ls-swap-width", type=int, default=20,
                    help="swaps evaluated per round = width^2 (top-width "
                         "drops x top-width adds, ranked by exact deltas)")

    sd = se.add_argument_group("distorted / dinkelbach")
    sd.add_argument("--distorted-k", type=int, default=None,
                    help="distortion horizon; default = pool size")
    sd.add_argument("--dink-rounds", type=int, default=6,
                    help="max re-linearisations")
    sd.add_argument("--dink-inner", choices=["distorted", "greedy"],
                    default="distorted", help="inner solver for the surrogate")

    sp_ = se.add_argument_group("poss / porss")
    sp_.add_argument("--poss-iters", type=int, default=5000)
    sp_.add_argument("--poss-seed", choices=["greedy", "empty"],
                     default="greedy",
                     help="'greedy' warm-starts the front from the greedy "
                          "path (makes 'never worse than greedy' hold from "
                          "iteration 0); 'empty' is the paper's version")

    se.set_defaults(fn=cmd_search)

    sc = sub.add_parser(
        "score", help="score finished selections on a held-out split")
    sc.add_argument("--eval-dir", required=True)
    sc.add_argument("--selections", nargs="+", required=True,
                    help="selection_*.json paths or globs")
    sc.add_argument("--split", default="test",
                    help="split to score on (default test -- the 140 papers "
                         "that entered no stage of distillation or selection)")
    sc.add_argument("--papers", help="comma list; overrides --split")
    sc.add_argument("--label-from", default="algo",
                    help="selection.json field to label each row by")
    sc.add_argument("--out", help="output CSV (default: under subset_search/)")
    sc.set_defaults(fn=cmd_score)

    args = ap.parse_args()
    # the run scored with containment; match it for any code path that reads
    # node_similarity's module global
    import node_similarity as ns
    ns.set_match_metric("containment")
    args.fn(args)


if __name__ == "__main__":
    main()
