#!/usr/bin/env python3
"""Compare distilled extractors on the same papers, with the same scorer.

An experiment is a JSON config (scripts/compare_configs/*.json): a split of the
silver corpus, the silver labels, and a set of ARMS. An arm is one extractor
and how it is obtained:

    alg "none"     the base parser, no distilled rules
    alg "fixed"    an existing rule directory (e.g. a released extractor)
    alg "units"    trained here by the unit algorithm   (scripts/distill_units.py)
    alg "merged"   trained here by the original algorithm (silver_distillation_merged.py)
    alg "tagger"   trained here by the sentence tagger, no teacher call (alg3/; "model" unused)

with "model" (the teacher) and "args" (any driver option, {"max-llm-calls": 2500}),
so a parameter variant is just another arm. "train_per_category": k trains on a
balanced subset of the train papers (k per category; "train_seed" picks another),
for learning curves in the number of training papers.

Each arm goes through two stages, each skipped when its result exists:

    train   run the arm's driver on the split's train papers (validation papers:
            the split's val papers). Skipped if <out>/<arm>/train/train_done.json
            exists, unless --force-retrain.
    eval    parse every paper of the evaluation splits with the arm's final rules,
            and with each training snapshot (the learning curve; --no-trajectory
            to skip), and score them. Parses are cached under a fingerprint of the
            rules and the parser code, so an unchanged arm is never re-parsed.

and a final report over all arms:

    report  <out>/results/
              metrics.csv      arm x split x mode (m1, m3) x stratum x node type:
                               n_gold, n_pred, tp, fp, fn, precision, recall, f1,
                               and a paper-bootstrap 95% interval for f1
              per_paper.csv    the same counts per paper (for paired tests)
              trajectory.csv   per arm and snapshot: rules, LLM calls, cost, time,
                               and test/val scores (stratum and type "all")
              costs.csv        per arm and training stage: calls, tokens, USD, seconds
              runtime.csv      per arm: parse seconds per paper (the extractor's speed)
              summary.json     the config, the code version, and all of the above
              REPORT.md        the headline tables

Strata: a node (silver or predicted) is "env" if its text is the body of a LaTeX
environment (theorem-like, proof, algorithm), "prose" if it lies in the running
prose (src/prose_units.py: outside environments, floats, abstract and
bibliography), and "other" if neither (e.g. a node stated inside a proof). The
"all" rows score every node together and are the headline; a stratum row scores
that stratum's predictions against that stratum's silver nodes, so strata need
not add up to "all" exactly.

Usage:
    python scripts/compare_distillers.py run --config scripts/compare_configs/v6.json \\
        [--arms base,units_haiku] [--stages train,eval,report] [--force-retrain]
        [--jobs 2] [--workers 6]
    python scripts/compare_distillers.py report --config ...
    python scripts/compare_distillers.py status --config ...     # progress of each arm

Training calls the Anthropic API (key from ANTHROPIC_API_KEY or ~/.anthropic_env).
Run it with nohup from a terminal: every stage resumes where it stopped.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO / "scripts", REPO / "src" / "LLMVersion", REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import distill_common as C                             # noqa: E402
import node_similarity as NS                           # noqa: E402

TYPES = C.TYPES
# metrics (src/LLMVersion/node_metrics.py); the first is the headline. Config
# "metrics" or --metrics overrides.
DEFAULT_METRICS = ["m1g", "m1", "m3"]
STRATA = ("all", "env", "prose", "other")
DRIVER = REPO / "scripts" / "silver_distillation_merged.py"
# code whose change can change a parse: part of every parse-cache fingerprint
PARSER_CODE = ["src/LLMVersion/math_paper_parser.py", "src/latex_facts.py", "src/prose_units.py",
               "src/LLMVersion/unit_rules.py", "src/LLMVersion/rule_guard.py",
               "src/LLMVersion/latex_clean.py"]


# ---------------------------------------------------------------------------
# config and split
# ---------------------------------------------------------------------------

def rel(p) -> Path:
    p = Path(p)
    return p if p.is_absolute() else REPO / p


def load_config(path: str, metrics: str | None = None) -> dict:
    cfg = json.load(open(path, encoding="utf-8"))
    if metrics:
        cfg["metrics"] = [m.strip() for m in metrics.split(",") if m.strip()]
    cfg.setdefault("threshold", 0.7)
    cfg.setdefault("cover", 0.7)
    cfg.setdefault("match_metric", "containment")
    cfg.setdefault("eval_splits", ["train", "val", "test"])
    cfg.setdefault("trajectory_splits", ["val", "test"])
    cfg.setdefault("bootstrap", 1000)
    cfg.setdefault("metrics", list(DEFAULT_METRICS))
    cfg["out"] = rel(cfg.get("out", f"runs/compare/{cfg['name']}"))
    cfg["tex_dir"] = rel(cfg.get("tex_dir", "corpus/silver/tex_staged"))
    cfg["silver_dir"] = rel(cfg["silver_dir"])
    sp = cfg["split"]
    if "file" not in sp:
        sp["file"] = f"corpus/silver/split_v6_{sp['train']}-{sp['val']}-{sp['test']}.csv"
    sp["file"] = rel(sp["file"])
    if not sp["file"].is_file():
        if "train" not in sp:
            raise SystemExit(f"split file {sp['file']} missing")
        subprocess.run([sys.executable, str(REPO / "scripts" / "assign_split_v6.py"),
                        "--train", str(sp["train"]), "--val", str(sp["val"]),
                        "--test", str(sp["test"]), "--out", str(sp["file"])], check=True)
    return cfg


def read_split(cfg) -> dict:
    """{pid: (split, category)}"""
    out = {}
    for r in csv.DictReader(open(cfg["split"]["file"], encoding="utf-8")):
        out[r.get("arxiv_id") or r["paper_id"]] = (r["split"], r.get("category", ""))
    return out


def papers_of(cfg, splits) -> list:
    sp = read_split(cfg)
    return sorted(p for p, (s, _) in sp.items() if s in splits)


# ---------------------------------------------------------------------------
# training
# ---------------------------------------------------------------------------

def arm_dir(cfg, name) -> Path:
    return cfg["out"] / name


def train_papers(cfg, arm) -> list:
    """The arm's training papers: the split's train papers, or with
    "train_per_category": k a balanced subset, k per category, chosen by
    sha256 rank (with "train_seed" mixed in, for a different subset)."""
    train = papers_of(cfg, ["train"])
    k = arm.get("train_per_category")
    if not k:
        return train
    seed = str(arm.get("train_seed", ""))
    cats = defaultdict(list)
    for pid, (split, cat) in read_split(cfg).items():
        if split == "train":
            cats[cat].append(pid)
    rank = lambda pid: hashlib.sha256((seed + pid).encode()).hexdigest()    # noqa: E731
    return sorted(p for ps in cats.values() for p in sorted(ps, key=rank)[:k])


def driver_cmd(cfg, arm, train_dir: Path) -> list:
    cmd = [sys.executable, "-u", str(DRIVER), "--alg", arm["alg"],
           "--pilot-papers", ",".join(train_papers(cfg, arm)),
           "--splits", str(cfg["split"]["file"]), "--t2-dir", str(cfg["silver_dir"]),
           "--tex-dir", str(cfg["tex_dir"]), "--eval-dir", str(train_dir),
           "--model", arm.get("model", "none"), "--threshold", str(cfg["threshold"]),
           "--match-metric", cfg["match_metric"]]
    if arm["alg"] == "units":
        cmd += ["--val-papers", "val"]
    for k, v in arm.get("args", {}).items():
        if v is True:
            cmd.append(f"--{k}")
        elif v is not False and v is not None:
            cmd += [f"--{k}", str(v)]
    return cmd


def train_summary(alg: str, train_dir: Path) -> dict:
    """Costs and learning curve of a finished training run, from the driver's own logs."""
    if alg == "tagger":                       # alg3: no teacher call, no snapshots
        m = json.load(open(train_dir / "sentence_model.json", encoding="utf-8"))
        return {"stages": {}, "llm_calls": 0, "cost_usd": 0.0, "distill_seconds": 0,
                "n_rules": len(m["anchor"]["weights"]), "trajectory": [],
                "params": m.get("meta", {})}
    if alg == "units":
        s = json.load(open(train_dir / "units_summary.json", encoding="utf-8"))
        traj = [json.loads(line) for line in open(train_dir / "units" / "trajectory.jsonl",
                                                  encoding="utf-8")]
        return {"stages": s["usage_by_stage"], "llm_calls": s["llm_calls"],
                "cost_usd": s["cost_usd"], "prepare_seconds": s["prepare_seconds"],
                "distill_seconds": s["distill_seconds"], "n_rules": len(s["active_rules"]),
                "trajectory": traj, "params": s["params"]}
    log = json.load(open(train_dir / "iteration_log.json", encoding="utf-8"))
    stages = {st: {k: sum(e.get(f"{st}_{k}", 0) for e in log)
                   for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cost_usd")}
              for st in ("analyze", "aggregate")}
    for st in stages:
        stages[st]["llm_calls"] = sum(e.get(f"{st}_llm_calls", 0) for e in log)
    traj, calls, secs = [], 0, 0.0
    for e in log:
        calls += e["total_llm_calls"]
        secs += e["wall_time_seconds"]
        traj.append({"snapshot": f"step_{e['paper_idx']:02d}_", "paper": e["paper_id"],
                     "active": e["cumulative_rules"], "llm_calls": calls,
                     "cost_usd": e["cumulative_cost_usd"], "seconds": round(secs)})
    return {"stages": stages, "llm_calls": calls,
            "cost_usd": log[-1]["cumulative_cost_usd"] if log else 0.0,
            "distill_seconds": round(secs), "n_rules": log[-1]["cumulative_rules"] if log else 0,
            "trajectory": traj}


def train_arm(cfg, name, arm, force: bool) -> None:
    if arm["alg"] in ("none", "fixed"):
        return
    d = arm_dir(cfg, name) / "train"
    done = d / "train_done.json"
    if done.is_file() and not force:
        print(f"[{name}] trained already ({done}); --force-retrain to redo")
        return
    if force and d.exists():
        old = d.with_name(f"train.prev_{time.strftime('%Y%m%d_%H%M%S')}")
        d.rename(old)
        print(f"[{name}] previous training moved to {old}")
    d.mkdir(parents=True, exist_ok=True)
    cmd = driver_cmd(cfg, arm, d)
    resume = (d / "units" / "state.json").is_file() or (d / "iteration_log.json").is_file()
    if resume:
        cmd.append("--resume")
    print(f"[{name}] training{' (resuming)' if resume else ''}: log {d / 'train.log'}")
    t0 = time.time()
    with open(d / "train.log", "a", encoding="utf-8") as log:
        log.write(f"\n# {time.ctime()}  {' '.join(cmd)}\n")
        log.flush()
        rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=REPO,
                            env=dict(os.environ, PYTHONHASHSEED="0")).returncode
    if rc != 0:
        raise SystemExit(f"[{name}] training failed (exit {rc}); see {d / 'train.log'}")
    s = train_summary(arm["alg"], d)
    s.update(alg=arm["alg"], model=arm.get("model", ""), args=arm.get("args", {}), command=cmd,
             wall_seconds=round(time.time() - t0), finished=time.ctime(), code=code_version())
    done.write_text(json.dumps(s, indent=1), encoding="utf-8")
    print(f"[{name}] trained: {s['n_rules']} rules, {s['llm_calls']} calls, ${s['cost_usd']}")


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------

def code_version() -> dict:
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                              capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src", "scripts"],
                                    cwd=REPO, capture_output=True, text=True).stdout.strip())
    except OSError:
        head, dirty = "", None
    return {"git": head, "dirty": dirty}


def scorer_version() -> str:
    """Hash of the scoring code: a change re-scores (from the cached parses)."""
    h = hashlib.sha256()
    for f in ("src/LLMVersion/node_metrics.py", "src/LLMVersion/match_modes.py",
              "src/node_similarity.py", "src/prose_units.py"):
        h.update((REPO / f).read_bytes())
    return h.hexdigest()[:16]


def fingerprint(rules_dir: Path) -> str:
    """The rules a parse uses and the parser code: equal fingerprints, equal parses."""
    h = hashlib.sha256()
    files = [rules_dir / "distilled_rules.py", rules_dir / "unit_rules.json",
             *sorted(rules_dir.glob("groups/*/distilled_rules.py"))]
    for f in files + [REPO / c for c in PARSER_CODE]:
        if f.is_file():
            h.update(str(f.name).encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


_W: dict = {}


def _parse_init(tex_dir, rules_dir):
    _W["tex"], _W["rules"] = Path(tex_dir), str(rules_dir)


def _parse_one(pid):
    """(pid, [[type, raw latex, provenance]], seconds) for one paper."""
    t0 = time.perf_counter()
    objs = [list(o) for o in C.parse_objects(pid, _W["tex"], TYPES, _W["rules"])]
    return pid, objs, round(time.perf_counter() - t0, 2)


def parse_papers(pids, rules_dir: Path, cache: Path, workers: int, tex_dir: Path) -> dict:
    """{pid: {"objects", "seconds"}}, parsed once per fingerprint (cached, resumable)."""
    import multiprocessing as mp
    fp = fingerprint(rules_dir)
    done = {}
    if cache.is_file():
        lines = open(cache, encoding="utf-8").read().splitlines()
        if lines and json.loads(lines[0]).get("fingerprint") == fp:
            for line in lines[1:]:
                d = json.loads(line)
                done[d["pid"]] = d
        else:
            cache.unlink()
    todo = [p for p in pids if p not in done]
    if todo:
        cache.parent.mkdir(parents=True, exist_ok=True)
        new = not cache.is_file()
        t0 = time.time()
        with open(cache, "a", encoding="utf-8") as fh:
            if new:
                fh.write(json.dumps({"fingerprint": fp, "rules_dir": str(rules_dir)}) + "\n")
            with mp.Pool(workers, initializer=_parse_init, initargs=(str(tex_dir), str(rules_dir))) as pool:
                for i, (pid, objs, secs) in enumerate(pool.imap_unordered(_parse_one, todo), 1):
                    d = {"pid": pid, "objects": objs, "seconds": secs}
                    done[pid] = d
                    fh.write(json.dumps(d) + "\n")
                    fh.flush()
                    if i % 20 == 0 or i == len(todo):
                        print(f"    parsed {i}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)
    return {p: done[p] for p in pids if p in done}


# ---------------------------------------------------------------------------
# strata and scoring
# ---------------------------------------------------------------------------

class Strata:
    """Stratum of each text of one paper (prose_units.Locator), memoised on disk
    by text hash: a paper's silver nodes and most predictions recur across arms
    and snapshots, and building the locator costs a full LaTeX analysis."""

    def __init__(self, cfg, pid):
        self.cfg, self.pid = cfg, pid
        self.path = cfg["out"] / "_context" / f"{pid}.json"
        self.memo = json.load(open(self.path, encoding="utf-8")) if self.path.is_file() else {}
        self.loc, self.dirty = None, False

    def of(self, texts: list, raw: bool) -> list:
        """`raw`: texts quote the raw source (silver), so the paper's macros are
        expanded first; parser output is already prepared."""
        keys = [hashlib.sha1(("r" if raw else "p").encode() + t.encode()).hexdigest()[:16]
                for t in texts]
        todo = [(k, t) for k, t in zip(keys, texts) if k not in self.memo]
        if todo:
            if self.loc is None:
                import latex_facts as L
                import prose_units as U
                main = L.find_main_tex(self.cfg["tex_dir"] / self.pid / "source")
                self.loc = U.Locator(L.read_tex(str(main))) if main else None
            if self.loc is None:
                self.memo.update({k: "other" for k, _ in todo})
            else:
                prep = self.loc.prepare([t for _, t in todo]) if raw else [t for _, t in todo]
                for (k, _), x in zip(todo, prep):
                    self.memo[k] = self.loc.stratum(self.loc.locate(x))
            self.dirty = True
        return [self.memo[k] for k in keys]

    def save(self):
        if self.dirty:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(self.memo), encoding="utf-8")
            tmp.replace(self.path)


def load_gold(cfg) -> dict:
    """{type: {pid: [texts]}} from cfg gold_dir, or built from the silver JSONs."""
    gdir = rel(cfg["gold_dir"]) if cfg.get("gold_dir") else cfg["out"] / "_gold"
    if not cfg.get("gold_dir"):
        stamp = gdir / "_built_from.json"
        want = {"silver_dir": str(cfg["silver_dir"]), "split": str(cfg["split"]["file"])}
        if not (stamp.is_file() and json.load(open(stamp)) == want):
            if gdir.exists():
                shutil.rmtree(gdir)
            for pid in sorted(read_split(cfg)):
                jf = cfg["silver_dir"] / f"{pid}.json"
                if jf.is_file():
                    for t in TYPES:
                        C.convert_t2_to_gold_csv(jf, t, gdir)
            stamp.write_text(json.dumps(want))
    return {t: C.load_gold_texts(gdir / C.FNAME_MAP[t]) for t in TYPES}


def score_paper(cfg, pid, objs, gold) -> list:
    """Count rows (metric, stratum, type) for one paper. Each metric matches the
    paper's predictions and reference nodes once, over all types (node_metrics),
    and gives every item a credit; a row sums the credits of its items: the
    predictions of that type and stratum (n_pred, tp) and the reference nodes of
    that type and stratum (n_gold, tp_recall). So strata and types add up to
    their totals; credits are fractional under graded metrics."""
    import node_metrics as NM
    st = Strata(cfg, pid)
    preds = [(t, raw) for t, raw, _prov in objs]
    pstr = st.of([x for _, x in preds], raw=False)
    golds = [(t, g) for t in TYPES for g in gold[t].get(pid, [])]
    gstr = st.of([g for _, g in golds], raw=True)
    st.save()
    rows = []
    for metric in cfg["metrics"]:
        pc, gc = NM.score(preds, golds, metric, cfg["threshold"], cfg["cover"])
        acc = defaultdict(lambda: dict.fromkeys(COUNT_COLS, 0.0))
        for (t, _), s_, c in zip(preds, pstr, pc):
            for key in ((s_, t), (s_, "all"), ("all", t), ("all", "all")):
                acc[key]["n_pred"] += 1
                acc[key]["tp"] += c
        for (t, _), s_, c in zip(golds, gstr, gc):
            for key in ((s_, t), (s_, "all"), ("all", t), ("all", "all")):
                acc[key]["n_gold"] += 1
                acc[key]["tp_recall"] += c
        for (stratum, t), r in acc.items():
            if t == "all":
                continue                      # rebuilt from the type rows when reporting
            r["fp"] = r["n_pred"] - r["tp"]
            r["fn"] = r["n_gold"] - r["tp_recall"]
            rows.append({"mode": metric, "stratum": stratum, "type": t,
                         **{k: round(v, 4) for k, v in r.items()}})
    return rows


_S: dict = {}


def _score_init(cfg_path, gold_cache, metrics):
    _S["cfg"] = load_config(cfg_path)
    _S["cfg"]["metrics"] = metrics
    NS.set_match_metric(_S["cfg"]["match_metric"])
    _S["gold"] = json.load(open(gold_cache, encoding="utf-8"))


def _score_one(item):
    pid, objs = item
    return pid, score_paper(_S["cfg"], pid, objs, _S["gold"])


COUNT_COLS = ["n_pred", "n_gold", "tp", "tp_recall", "fp", "fn"]


def score_state(cfg, cfg_path, parses: dict, out_csv: Path, workers: int) -> None:
    """Per-paper count rows of one rule state, to out_csv."""
    import multiprocessing as mp
    gold_cache = cfg["out"] / "_gold_texts.json"
    if not gold_cache.is_file():
        gold_cache.write_text(json.dumps(load_gold(cfg)), encoding="utf-8")
    split = read_split(cfg)
    rows = []
    with mp.Pool(workers, initializer=_score_init, initargs=(cfg_path, str(gold_cache), cfg["metrics"])) as pool:
        for pid, prs in pool.imap_unordered(_score_one, [(p, d["objects"]) for p, d in parses.items()]):
            for r in prs:
                rows.append({"paper_id": pid, "split": split[pid][0], "category": split[pid][1],
                             "seconds": parses[pid]["seconds"], **r})
    rows.sort(key=lambda r: (r["paper_id"], r["mode"], r["stratum"], r["type"]))
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_csv.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["paper_id", "split", "category", "seconds", "mode",
                                          "stratum", "type"] + COUNT_COLS)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(out_csv)


# ---------------------------------------------------------------------------
# evaluation of one arm
# ---------------------------------------------------------------------------

def rule_states(cfg, name, arm, trajectory: bool) -> list:
    """[(label, rules dir)]: the final rules, then the training snapshots."""
    if arm["alg"] == "none":
        empty = cfg["out"] / "_empty_rules"
        empty.mkdir(parents=True, exist_ok=True)
        return [("final", empty)]
    if arm["alg"] == "fixed":
        return [("final", rel(arm["rules_dir"]))]
    d = arm_dir(cfg, name) / "train"
    if not (d / "train_done.json").is_file():
        raise SystemExit(f"[{name}] not trained yet: run with --stages train,eval")
    states = [("final", d)]
    if trajectory:
        states += [(s.name, s) for s in C.snapshot_dirs(d)]
    return states


def eval_arm(cfg, cfg_path, name, arm, force: bool, trajectory: bool, workers: int) -> None:
    ev = arm_dir(cfg, name) / "eval"
    if force and (ev / "scores").exists():
        shutil.rmtree(ev / "scores")          # re-score; parses are cached by fingerprint
    for label, rdir in rule_states(cfg, name, arm, trajectory):
        splits = cfg["eval_splits"] if label == "final" else cfg["trajectory_splits"]
        pids = papers_of(cfg, splits)
        out_csv = ev / "scores" / f"{label}.csv"
        cache = ev / "parses" / f"{label}.jsonl"
        fp = fingerprint(rdir)
        stamp = ev / "scores" / f"{label}.json"
        want = {"fingerprint": fp, "papers": pids, "metrics": cfg["metrics"],
                "scorer": scorer_version(), "threshold": cfg["threshold"], "cover": cfg["cover"]}
        if out_csv.is_file() and stamp.is_file() and json.load(open(stamp)) == want:
            continue
        print(f"[{name}] eval {label}: {len(pids)} papers ({rdir})", flush=True)
        parses = parse_papers(pids, rdir, cache, workers, cfg["tex_dir"])
        score_state(cfg, cfg_path, parses, out_csv, workers)
        stamp.write_text(json.dumps(want))


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def prf(c: dict) -> tuple:
    return NS.prf(c["tp"], c["tp_recall"], c["fp"], c["fn"])


def read_scores(path: Path) -> list:
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    for r in rows:
        for k in COUNT_COLS:
            r[k] = float(r[k])
        r["seconds"] = float(r["seconds"])
    return rows


def aggregate(rows, keys, n_boot=0, seed=0) -> list:
    """Pooled counts per key, with a paper-bootstrap 95% interval for f1."""
    groups = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(COUNT_COLS, 0)))
    for r in rows:
        k = tuple(r[c] for c in keys)
        for c in COUNT_COLS:
            groups[k][r["paper_id"]][c] += r[c]
    out = []
    rnd = random.Random(seed)
    for k, per in sorted(groups.items()):
        tot = dict.fromkeys(COUNT_COLS, 0)
        for c in per.values():
            for x in COUNT_COLS:
                tot[x] += c[x]
        p, r, f = prf(tot)
        row = dict(zip(keys, k), n_papers=len(per), **tot, precision=round(p, 4),
                   recall=round(r, 4), f1=round(f, 4))
        if n_boot:
            pids, fs = list(per), []
            for _ in range(n_boot):
                s = dict.fromkeys(COUNT_COLS, 0)
                for pid in (rnd.choice(pids) for _ in pids):
                    for x in COUNT_COLS:
                        s[x] += per[pid][x]
                fs.append(prf(s)[2])
            fs.sort()
            row["f1_lo"] = round(fs[int(0.025 * n_boot)], 4)
            row["f1_hi"] = round(fs[int(0.975 * n_boot) - 1], 4)
        out.append(row)
    return out


def paired_deltas(per_paper: list, ref: str, n_boot: int, seed=0) -> list:
    """F1(arm) - F1(ref) per split, mode and stratum (all node types pooled),
    with a paired paper-bootstrap 95% interval: both arms are resampled on the
    same papers, so paper-to-paper variation cancels."""
    cnt = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(COUNT_COLS, 0)))
    for r in per_paper:
        c = cnt[(r["arm"], r["split"], r["mode"], r["stratum"])][r["paper_id"]]
        for x in COUNT_COLS:
            c[x] += r[x]
    rnd, out = random.Random(seed), []
    for (arm, split, mode, st), per in sorted(cnt.items()):
        refp = cnt.get((ref, split, mode, st))
        if arm == ref or not refp:
            continue
        pids = sorted(set(per) | set(refp))
        zero = dict.fromkeys(COUNT_COLS, 0)

        def f1(table, sample):
            s = dict.fromkeys(COUNT_COLS, 0)
            for pid in sample:
                for x in COUNT_COLS:
                    s[x] += table.get(pid, zero)[x]
            return prf(s)[2]
        d = f1(per, pids) - f1(refp, pids)
        ds = sorted(f1(per, smp) - f1(refp, smp)
                    for smp in ([rnd.choice(pids) for _ in pids] for _ in range(n_boot)))
        out.append({"arm": arm, "ref": ref, "split": split, "mode": mode, "stratum": st,
                    "n_papers": len(pids), "delta_f1": round(d, 4),
                    "delta_lo": round(ds[int(0.025 * n_boot)], 4),
                    "delta_hi": round(ds[int(0.975 * n_boot) - 1], 4)})
    return out


def write_csv(path: Path, rows: list) -> None:
    if not rows:
        return
    cols = []
    for r in rows:
        cols += [c for c in r if c not in cols]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def report(cfg) -> None:
    res = cfg["out"] / "results"
    res.mkdir(parents=True, exist_ok=True)
    metrics, per_paper, traj, costs, runtime, arms_meta = [], [], [], [], [], {}
    for name, arm in cfg["arms"].items():
        sdir = arm_dir(cfg, name) / "eval" / "scores"
        final = sdir / "final.csv"
        if not final.is_file():
            continue
        rows = read_scores(final)
        for r in rows:
            r["arm"] = name
        per_paper += rows
        # "all"-type rows: the pooled headline; per-type rows: no bootstrap (cheap to add)
        allrows = [dict(r, type="all") for r in rows]
        metrics += aggregate(allrows, ["arm", "split", "mode", "stratum", "type"], cfg["bootstrap"])
        metrics += aggregate(rows, ["arm", "split", "mode", "stratum", "type"])
        # parse speed: one "all/all/m1" row per paper carries its seconds
        secs = {r["paper_id"]: r["seconds"] for r in rows}
        runtime.append({"arm": name, "papers": len(secs),
                        "seconds_total": round(sum(secs.values()), 1),
                        "seconds_per_paper": round(sum(secs.values()) / max(len(secs), 1), 2)})
        meta = {"alg": arm["alg"], "model": arm.get("model", ""), "args": arm.get("args", {}),
                "note": arm.get("note", "")}
        done = arm_dir(cfg, name) / "train" / "train_done.json"
        if done.is_file():
            t = json.load(open(done, encoding="utf-8"))
            meta.update({k: t.get(k) for k in ("llm_calls", "cost_usd", "n_rules", "wall_seconds",
                                                "prepare_seconds", "distill_seconds", "code")})
            for st, u in t["stages"].items():
                costs.append({"arm": name, "stage": st, **u})
            by_snap = {e["snapshot"]: e for e in t.get("trajectory", [])}
            for f in sorted(sdir.glob("step_*.csv"), key=lambda f: int(f.name.split("_")[1])):
                info = by_snap.get(f.stem) or next(
                    (e for k, e in by_snap.items() if f.stem.startswith(k)), {})
                srows = [dict(r, type="all") for r in read_scores(f) if r["stratum"] == "all"]
                for a in aggregate(srows, ["split", "mode"]):
                    traj.append({"arm": name, "snapshot": f.stem, "rules": info.get("active"),
                                 "llm_calls": info.get("llm_calls"), "cost_usd": info.get("cost_usd"),
                                 "train_seconds": info.get("seconds"), **a})
        arms_meta[name] = meta
    ref = cfg.get("reference_arm", "base")
    deltas = paired_deltas(per_paper, ref, cfg["bootstrap"]) if any(
        r["arm"] == ref for r in per_paper) else []
    write_csv(res / "deltas.csv", deltas)
    write_csv(res / "metrics.csv", metrics)
    write_csv(res / "per_paper.csv", per_paper)
    write_csv(res / "trajectory.csv", traj)
    write_csv(res / "costs.csv", costs)
    write_csv(res / "runtime.csv", runtime)
    summary = {"name": cfg["name"], "made": time.ctime(), "code": code_version(),
               "config": {k: (str(v) if isinstance(v, Path) else v) for k, v in cfg.items()
                          if k != "arms"},
               "arms": arms_meta, "runtime": runtime, "costs": costs,
               "headline": [m for m in metrics if m["type"] == "all"], "deltas": deltas}
    summary["config"]["split"] = {k: str(v) for k, v in cfg["split"].items()}
    (res / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    write_markdown(cfg, res, metrics, runtime, arms_meta, deltas)
    print(f"[report] {res}")


def write_markdown(cfg, res, metrics, runtime, arms_meta, deltas) -> None:
    idx = {(m["arm"], m["split"], m["mode"], m["stratum"], m["type"]): m for m in metrics}
    dix = {(d["arm"], d["split"], d["mode"], d["stratum"]): d for d in deltas}
    arms = list(arms_meta)
    head, others = cfg["metrics"][0], cfg["metrics"][1:]
    ref = cfg.get("reference_arm", "base")
    lines = [f"# Distiller comparison: {cfg['name']}", "",
             f"Split `{cfg['split']['file'].name}`, silver `{cfg['silver_dir'].name}`, pooled "
             f"counts, containment >= {cfg['threshold']}. Headline metric **{head}** "
             f"(src/LLMVersion/node_metrics.py); others: {', '.join(others) or 'none'}. "
             "F1 interval: 95% paper bootstrap; difference to the reference arm: paired.", ""]
    for split in cfg["eval_splits"]:
        lines += [f"## {split}", "",
                  f"| arm | stratum | {head} P / R / F1 [95% CI] | F1 - {ref} [paired 95% CI] | "
                  f"TP / FP / FN | silver nodes | " + " | ".join(f"{o} F1" for o in others) + " |",
                  "|---|---|---|---|---|---|" + "---|" * len(others)]
        for a in arms:
            for st in STRATA:
                h = idx.get((a, split, head, st, "all"))
                if not h:
                    continue
                d = dix.get((a, split, head, st))
                lines.append(
                    f"| {a} | {st} | {h['precision']:.3f} / {h['recall']:.3f} / **{h['f1']:.3f}** "
                    f"[{h.get('f1_lo', 0):.3f}, {h.get('f1_hi', 0):.3f}] | "
                    + (f"{d['delta_f1']:+.3f} [{d['delta_lo']:+.3f}, {d['delta_hi']:+.3f}]" if d else "")
                    + f" | {h['tp']:.0f} / {h['fp']:.0f} / {h['fn']:.0f} | {h['n_gold']:.0f} | "
                    + " | ".join(f"{idx[(a, split, o, st, 'all')]['f1']:.3f}"
                                 if (a, split, o, st, "all") in idx else "" for o in others) + " |")
        lines.append("")
    lines += ["## Cost and speed", "", "| arm | alg | teacher | rules | LLM calls | USD | "
              "training s | parse s / paper |", "|---|---|---|---|---|---|---|---|"]
    rt = {r["arm"]: r for r in runtime}
    for a, m in arms_meta.items():
        lines.append(f"| {a} | {m['alg']} | {m.get('model') or ''} | {m.get('n_rules') or ''} | "
                     f"{m.get('llm_calls') or ''} | {m.get('cost_usd') or ''} | "
                     f"{m.get('wall_seconds') or ''} | {rt[a]['seconds_per_paper']} |")
    (res / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def status(cfg) -> None:
    """Where each arm is: training progress (teacher calls, cost, accepted rules,
    clusters, validation F1, a rough time to the call budget) and evaluation."""
    import re as _re
    for name, arm in cfg["arms"].items():
        d = arm_dir(cfg, name)
        if arm["alg"] in ("none", "fixed"):
            ev = (d / "eval" / "scores" / "final.csv").is_file()
            print(f"{name:14s} {arm['alg']:6s} eval {'done' if ev else 'not run'}")
            continue
        t = d / "train"
        if (t / "train_done.json").is_file():
            s = json.load(open(t / "train_done.json", encoding="utf-8"))
            nsnap = len(C.snapshot_dirs(t))
            nscored = len(list((d / "eval" / "scores").glob("step_*.csv")))
            ev = ("final rules scored" if (d / "eval" / "scores" / "final.csv").is_file()
                  else "eval pending") + f", learning curve {nscored}/{nsnap} snapshots"
            print(f"{name:14s} trained: {s['n_rules']} rules, {s['llm_calls']} calls, "
                  f"${s['cost_usd']}, {s['wall_seconds'] / 3600:.1f} h; {ev}")
            continue
        state = t / "units" / "state.json"
        if arm["alg"] == "units" and state.is_file():
            st = json.load(open(state, encoding="utf-8"))
            import distillation_analysis as da
            stages = st.get("usage_by_stage", {})
            calls = sum(u.get("llm_calls", 0) for u in stages.values())
            judge = arm.get("args", {}).get("judge-model") or arm["model"]
            cost = sum(da.estimate_cost(u, judge if k.endswith("judge") else arm["model"])
                       for k, u in stages.items())
            traj = [json.loads(x) for x in open(t / "units" / "trajectory.jsonl", encoding="utf-8")] \
                if (t / "units" / "trajectory.jsonl").is_file() else []
            last = traj[-1] if traj else {}
            log = (t / "train.log").read_text(encoding="utf-8", errors="replace")
            ncl = _re.findall(r"misses (\d+) in (\d+) cluster", log)
            budget = int(arm.get("args", {}).get("max-llm-calls", 400))
            secs = st.get("seconds", 0)
            eta = (budget - calls) * secs / calls / 3600 if calls else float("nan")
            print(f"{name:14s} training: round {st['round']}, clusters tried "
                  f"{len(st.get('tried', []))}" + (f" of {ncl[-1][1]} this round" if ncl else "")
                  + f", {st.get('accepted', 0)} rules accepted, {calls}/{budget} calls, "
                  f"${cost:.2f}, {secs / 3600:.2f} h"
                  + (f" (budget reached in <= {eta:.1f} h)" if calls else "")
                  + (f"; validation overall recall {last.get('val_R')}, FDR {last.get('val_FDR')}, "
                     f"F {last.get('val_F')} at {last['snapshot']}" if last else ""))
        elif t.is_dir():
            print(f"{name:14s} training: preparing papers (see {t / 'train.log'})")
        else:
            print(f"{name:14s} not started")


def run_job(args) -> None:
    """One arm: its train and eval stages (what `run` launches per arm)."""
    cfg = load_config(args.config, args.metrics)
    NS.set_match_metric(cfg["match_metric"])
    arm = cfg["arms"][args.arm]
    stages = args.stages.split(",")
    if "train" in stages:
        train_arm(cfg, args.arm, arm, args.force_retrain)
    if "eval" in stages:
        eval_arm(cfg, args.config, args.arm, arm, args.force_eval, not args.no_trajectory,
                 args.workers)


def run_all(args) -> None:
    cfg = load_config(args.config, args.metrics)
    names = list(cfg["arms"]) if args.arms in ("", "all") else args.arms.split(",")
    unknown = [n for n in names if n not in cfg["arms"]]
    if unknown:
        raise SystemExit(f"unknown arm(s) {unknown}; the config has {list(cfg['arms'])}")
    stages = [s for s in args.stages.split(",") if s in ("train", "eval")]
    if stages:
        load_gold(cfg)                          # once, before the jobs share it
        procs, failed = [], []
        for name in names:
            log = arm_dir(cfg, name) / "job.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            cmd = [sys.executable, "-u", __file__, "job", "--config", args.config, "--arm", name,
                   "--stages", ",".join(stages), "--workers", str(args.workers),
                   "--metrics", ",".join(cfg["metrics"])]
            cmd += [f for f, on in (("--force-retrain", args.force_retrain),
                                    ("--force-eval", args.force_eval),
                                    ("--no-trajectory", args.no_trajectory)) if on]
            while len([p for p in procs if p[1].poll() is None]) >= args.jobs:
                time.sleep(5)
            print(f"[run] {name}: {' '.join(stages)}  (log {log})", flush=True)
            fh = open(log, "a", encoding="utf-8")
            procs.append((name, subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=REPO,
                                                 env=dict(os.environ, PYTHONHASHSEED="0"))))
        for name, p in procs:
            if p.wait() != 0:
                failed.append(name)
                print(f"[run] {name} FAILED (exit {p.returncode}); see "
                      f"{arm_dir(cfg, name) / 'job.log'}", flush=True)
            else:
                print(f"[run] {name} done", flush=True)
        if failed:
            print(f"[run] failed arms: {failed}")
    if "report" in args.stages.split(","):
        report(cfg)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("run", "job", "report", "status"):
        p = sub.add_parser(cmd)
        p.add_argument("--config", required=True)
        p.add_argument("--metrics", default=None,
                       help="comma list from node_metrics.METRICS (m1g, m1, m3); the first is "
                            "the headline. Default: the config's \"metrics\", else m1g,m1,m3")
        if cmd in ("report", "status"):
            continue
        p.add_argument("--stages", default="train,eval,report" if cmd == "run" else "train,eval")
        p.add_argument("--force-retrain", action="store_true",
                       help="retrain even if a finished training exists (the old one is kept "
                            "as train.prev_<time>)")
        p.add_argument("--force-eval", action="store_true", help="re-parse and re-score")
        p.add_argument("--no-trajectory", action="store_true",
                       help="evaluate the final rules only, not every training snapshot")
        p.add_argument("--workers", type=int, default=4, help="parse processes per arm")
        if cmd == "run":
            p.add_argument("--arms", default="all", help="comma list of arm names, or all")
            p.add_argument("--jobs", type=int, default=1, help="arms run at the same time")
        else:
            p.add_argument("--arm", required=True)
    args = ap.parse_args()
    if args.cmd == "run":
        run_all(args)
    elif args.cmd == "job":
        run_job(args)
    elif args.cmd == "status":
        status(load_config(args.config))
    else:
        report(load_config(args.config, args.metrics))


if __name__ == "__main__":
    main()
