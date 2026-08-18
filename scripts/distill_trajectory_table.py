#!/usr/bin/env python3
"""Trajectory table: how the student scores on every paper, at every rule state.

Rows are the training papers in the order the run distilled them (worst-first
from the phase-1 ranking, so row 1 is the paper the base parser handled worst).
Columns are RULE STATES: the base parser, then the rule set as it stood after
each paper. Cells are pooled F1 over all structure types.

    paper (worst->best)   base    after 1   after 2   ...
     1  1102.4533v1        .118     .486<     .501    ...
     2  1003.1038v1        .202     .245      .601<   ...
     3  1906.04768v3       .190     .223      .266    ...
    ------------------------------------------------------
    HELD-OUT F1            .606     .609      .612    ...
    HELD-OUT precision     ...
    HELD-OUT recall        ...
    not-yet-seen (mean F1) ...

The `<` marks the diagonal. LEFT of it a paper had not yet been distilled from,
so those cells are genuine out-of-sample measurements — read down the columns
just left of the diagonal and you have a learning curve (how well does the
student do on an unseen paper after N papers of training?). RIGHT of it the
paper is in-sample.

`not-yet-seen` is the mean F1 over papers still left of the diagonal in that
column: a running, honest estimate of generalisation during the run.

Read-only. No LLM calls, and it never edits a rule file — it installs each
snapshot's rules, parses, scores, and restores. Safe to re-run.

    python scripts/distill_trajectory_table.py \
        --eval-dir src/LLMVersion/merged_eval_v51 \
        --tex-dir corpus/silver/tex_staged \
        --t2-dir corpus/silver/opus-5__v5.1 \
        --heldout-split test --interval 10 --workers 8
"""
import argparse
import csv
import json
import multiprocessing as mp
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))

import silver_distillation_merged as mrg          # noqa: E402
import silver_distillation_sequential as seq      # noqa: E402
from silver_distillation_sequential import FNAME_MAP, convert_t2_to_gold_csv  # noqa: E402

# Set by _init_worker in each child process (spawn re-imports this module).
_W = {}


def _init_worker(tex_dir, types):
    _W["tex"] = Path(tex_dir)
    _W["types"] = types


def _parse_one(pid):
    """Child-process entry point. Parses under the rules the PARENT installed —
    never installs anything itself, so nothing races on the shared symlink."""
    return pid, mrg.parse_buckets_installed(pid, _W["tex"], _W["types"])


# ---------------------------------------------------------------------------


def load_recorded(path: Path, *, metric=None, threshold=None, cover=None):
    """{mode: {state_label: {paper_id: row}}} from the run's scores.jsonl.

    Written by silver_distillation_merged --score-every. Returns None if absent,
    which is the signal to fall back to re-parsing.

    Rows whose scoring parameters differ from the ones asked for are DROPPED,
    not silently served. A cached score is only reusable if it was produced
    under the same metric/threshold/cover; serving a jaccard row to a
    containment request just shifts every number with nothing to indicate it
    happened. Dropping them makes the coverage check fail, which falls back to
    an honest reparse.
    """
    if not path.exists():
        return None
    out = {"m1": {}, "m3": {}}
    mismatched = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue            # partial last line from a killed run
            md = r.get("mode")
            if md not in out:
                continue
            if ((metric is not None and r.get("metric") != metric)
                    or (threshold is not None
                        and r.get("threshold") != threshold)
                    or (cover is not None and r.get("cover") != cover)):
                mismatched += 1
                continue
            # Recompute p/r/f1 from the integer counts instead of trusting the
            # stored floats, which are rounded to 4dp on write. Reading them
            # back made a cached cell differ from a re-parsed one in the third
            # decimal (0.658 vs 0.659) -- small, but it means the two paths
            # disagree, and then neither can be used to check the other.
            # Later rows win: a resumed run re-scoring a state should supersede.
            out[md].setdefault(r["state"], {})[r["paper_id"]] = _prf(
                r.get("tp", 0), r.get("fp", 0), r.get("fn", 0),
                r.get("tp_recall", r.get("tp", 0)))
    if mismatched:
        print(f"  [note] dropped {mismatched} recorded row(s) scored under "
              f"different parameters than requested "
              f"(metric={metric}, threshold={threshold}, cover={cover})")
    return out if any(out[m] for m in out) else None


def _reparse_all(args, out_dir: Path, states, all_papers, types, gold):
    """Fallback path: install each state, parse every paper, score both modes.

    Only reached when the run did not record its own scores. Every state here
    is reconstructed after the fact, which is why the recorded path is
    preferred — this one depends on the .tex tree and the snapshots still
    matching what the run saw.
    """
    cells = {"m1": {}, "m3": {}}
    base_snap = mrg.baseline_snapshot(out_dir, mrg.base_method_groups(types))
    for label, snap, _n in states:
        # `None` would mean "whatever is installed" -- normally a PREVIOUS run's
        # final rules. The empty snapshot is the true base parser.
        state_dir = base_snap if snap is None else snap
        with mrg.installed_rules(state_dir, types):
            if args.workers > 1:
                with mp.Pool(args.workers, initializer=_init_worker,
                             initargs=(str(args.tex_dir), types)) as pool:
                    parsed = dict(pool.map(_parse_one, all_papers))
            else:
                parsed = {p: mrg.parse_buckets_installed(p, args.tex_dir, types)
                          for p in all_papers}
        # Score both modes off the SAME parse. Parsing dominates cost; a second
        # scoring pass is nearly free, so the appendix can always show m1 and m3
        # side by side whichever one the main table uses.
        for md in ("m1", "m3"):
            cells[md][label] = {p: score(parsed[p], gold, p, types,
                                         args.threshold, md, args.cover)
                                for p in all_papers}
    return cells


def discover_states(eval_dir: Path, interval: int):
    """[(label, snapshot_dir, n_papers_distilled), ...] at the given interval.

    Always includes the empty base state and the final state, whatever the
    interval — the first and last columns are the ones anyone actually quotes.
    """
    snaps = sorted((eval_dir / "snapshots").glob("step_*"),
                   key=lambda p: int(p.name.split("_")[1]))
    steps = [s for s in snaps if not s.name.startswith("step_00")]
    out = [("base", None, 0)]
    for i, s in enumerate(steps, 1):
        if i % interval == 0 or i == len(steps):
            out.append((f"after {i}", s, i))
    return out


def load_gold(papers, t2_dir: Path, gold_dir: Path, types):
    """One gold CSV per type covering every paper (convert_* appends)."""
    gold_dir.mkdir(parents=True, exist_ok=True)
    for t in types:
        p = gold_dir / FNAME_MAP[t]
        if p.exists():
            p.unlink()
    for pid in papers:
        jp = t2_dir / f"{pid}.json"
        if jp.exists():
            for t in types:
                convert_t2_to_gold_csv(jp, t, gold_dir)
    return {t: mrg.load_gold_texts(gold_dir / FNAME_MAP[t]) for t in types}


def score(buckets, gold_by_type, pid, types, threshold, mode, cover):
    tp = tpr = fp = fn = 0
    # m3's support is gold across EVERY type (nesting crosses types).
    support = [g for t in types for g in gold_by_type[t].get(pid, [])]
    for t in types:
        m = mrg.metrics(buckets[t], gold_by_type[t].get(pid, []), threshold,
                        mode=mode, support_texts=support, cover=cover)
        tp += m["tp"]; tpr += m["tp_recall"]; fp += m["fp"]; fn += m["fn"]
    return _prf(tp, fp, fn, tpr)


def _prf(tp, fp, fn, tp_recall=None):
    """tp is the PRECISION numerator; tp_recall the RECALL one. They differ
    under m3 (many spans inside one gold node), so recall must never use tp."""
    tpr = tp if tp_recall is None else tp_recall
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tpr / (tpr + fn) if (tpr + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"tp": tp, "tp_recall": tpr, "fp": fp, "fn": fn,
            "precision": p, "recall": r, "f1": f}


def judge_rescues(eval_dir: Path):
    """{paper_id: n_FPs the LLM judge ruled GENUINE}, or {} if no judge ran.

    The judge is a MEASUREMENT correction, not another distillation step: it
    re-labels FPs the silver under-labelled, lifting precision. It cannot change
    recall, so the recall row must be identical across the judge boundary --
    a built-in sanity check.
    """
    p = eval_dir / "fp_judge.csv"
    if not p.is_file():
        return {}
    out = {}
    for r in csv.DictReader(open(p, encoding="utf-8")):
        if (r.get("verdict") or "").strip().upper().startswith("GENUINE"):
            out[r.get("paper_id", "")] = out.get(r.get("paper_id", ""), 0) + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-dir", required=True, type=Path)
    ap.add_argument("--tex-dir", required=True, type=Path,
                    help="nested <paper>/source/*.tex (see stage_tex_pool.py)")
    ap.add_argument("--t2-dir", type=Path,
                    default=REPO / "corpus/silver/opus-5__v5.1")
    ap.add_argument("--interval", type=int, default=1,
                    help="score every Nth rule state (default 1 = every paper). "
                         "Base and final states are always included.")
    ap.add_argument("--heldout-split", default="test",
                    help="split in split_opus5.csv to use for the held-out rows")
    ap.add_argument("--heldout-papers", default=None,
                    help="explicit comma list, overrides --heldout-split")
    ap.add_argument("--exclude-papers", default=None,
                    help="comma list to drop from the held-out set (e.g. papers "
                         "already scored elsewhere, to keep the rest pristine)")
    ap.add_argument("--limit-heldout", type=int, default=None)
    ap.add_argument("--workers", type=int, default=1,
                    help="parallel parse workers. Rules are installed ONCE per "
                         "state in the parent; workers only read. >1 pays a "
                         "per-worker import cost, so it only wins on big sets "
                         "(measured: 0.7x at 12 papers, 1.5x at 60 on 8 cores).")
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--match-mode", default="m1", choices=["m1", "m3"],
                    help="Scoring mode. Use the SAME mode the run's prune gate "
                         "used, or rules selected under one are scored under the "
                         "other. m1 = strict same-type 1:1; m3 = nesting/"
                         "decomposition tolerant (see match_modes.py).")
    ap.add_argument("--cover", type=float, default=0.7,
                    help="m3: fraction of a span that must be accounted for")
    ap.add_argument("--match-metric", default="containment",
                    choices=["jaccard", "containment"])
    ap.add_argument("--out", default=None, help="output dir (default <eval-dir>/trajectory)")
    args = ap.parse_args()

    seq.set_match_metric(args.match_metric)
    eval_dir = args.eval_dir.resolve()
    out_dir = Path(args.out) if args.out else eval_dir / "trajectory"
    out_dir.mkdir(parents=True, exist_ok=True)
    types = mrg.ALL_SILVER_TYPES

    # --- rows: training papers in the order the run distilled them ----------
    log = json.load(open(eval_dir / "iteration_log.json", encoding="utf-8"))
    train = [e["paper_id"] for e in log]

    # --- rows: held-out set --------------------------------------------------
    if args.heldout_papers:
        held = [x.strip() for x in args.heldout_papers.split(",") if x.strip()]
    else:
        held = [r["arxiv_id"] for r in
                csv.DictReader(open(REPO / "corpus/silver/split_opus5.csv",
                                    encoding="utf-8"))
                if r["split"] == args.heldout_split]
    if args.exclude_papers:
        drop = {x.strip() for x in args.exclude_papers.split(",")}
        held = [p for p in held if p not in drop]
    held = [p for p in held if (args.tex_dir / p / "source").is_dir()]
    if args.limit_heldout:
        held = held[:args.limit_heldout]

    states = discover_states(eval_dir, args.interval)
    all_papers = train + held

    print(f"eval-dir   : {eval_dir}")
    print(f"train rows : {len(train)} (run order = worst-first from phase 1)")
    print(f"held-out   : {len(held)}")
    print(f"states     : {len(states)} (interval {args.interval}) "
          f"-> {[s[0] for s in states]}")
    print(f"parses     : {len(all_papers)} x {len(states)} = "
          f"{len(all_papers)*len(states):,}   workers={args.workers}\n")

    # --- prefer scores the run already recorded ------------------------------
    # The run can write these itself (--score-every), which is strictly better
    # than reconstructing them: those rows were produced BY the state, at the
    # moment it existed, so they cannot drift from it. Re-parsing here is the
    # fallback for runs that did not record them.
    recorded = load_recorded(eval_dir / "trajectory" / "scores.jsonl",
                             metric=args.match_metric,
                             threshold=args.threshold, cover=args.cover)
    cells = {"m1": {}, "m3": {}}
    if recorded:
        have = [lb for lb, _s, _n in states if lb in recorded["m1"]]
        missing_p = {p for lb in have for p in all_papers
                     if p not in recorded["m1"].get(lb, {})}
        if len(have) == len(states) and not missing_p:
            print(f"using scores recorded by the run "
                  f"({len(states)} states x {len(all_papers)} papers, "
                  f"no reparse)\n")
            cells = recorded
        else:
            print(f"  [note] scores.jsonl covers {len(have)}/{len(states)} "
                  f"states" + (f", missing {len(missing_p)} paper(s)"
                               if missing_p else "") + " -- reparsing\n")
            recorded = None

    cell = cells[args.match_mode]
    if not recorded:
        gold = load_gold(all_papers, args.t2_dir, out_dir / "gold", types)
        cells = _reparse_all(args, out_dir, states, all_papers, types, gold)
        cell = cells[args.match_mode]
    for label, _snap, _n in states:
        hp = _prf(*[sum(cells[args.match_mode][label][p][k] for p in held)
                    for k in ("tp", "fp", "fn", "tp_recall")])
        print(f"  {label:<12} held-out F1={hp['f1']:.3f}")

    labels = [s[0] for s in states]
    n_at = {s[0]: s[2] for s in states}

    # --- judge column: measurement correction, not a rule change -------------
    rescues = judge_rescues(eval_dir)
    judge_label = None
    if rescues:
        judge_label = f"{labels[-1]} +judge"
        cell[judge_label] = {}
        for p in all_papers:
            c = dict(cell[labels[-1]][p])
            cell[judge_label][p] = _prf(c["tp"],
                                        max(0, c["fp"] - rescues.get(p, 0)),
                                        c["fn"], c["tp_recall"])
        labels.append(judge_label)
        n_at[judge_label] = n_at[labels[-2]]

    # --- write + print -------------------------------------------------------
    _emit(out_dir, train, held, labels, n_at, cell, judge_label, args, cells)
    return 0


def _emit(out_dir, train, held, labels, n_at, cell, judge_label, args, cells=None):
    # main table: F1 only
    main = out_dir / "trajectory_f1.csv"
    with open(main, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row", "paper_id", "run_index"] + labels)
        for i, p in enumerate(train, 1):
            w.writerow([i, p, i] + [f"{cell[l][p]['f1']:.4f}" for l in labels])
        for name, key in (("HELD-OUT F1", "f1"), ("HELD-OUT precision", "precision"),
                          ("HELD-OUT recall", "recall")):
            row = []
            for l in labels:
                agg = _prf(*[sum(cell[l][p][k] for p in held)
                             for k in ("tp", "fp", "fn", "tp_recall")])
                row.append(f"{agg[key]:.4f}")
            w.writerow(["", name, ""] + row)
        # not-yet-seen: mean F1 over papers still LEFT of the diagonal
        row = []
        for l in labels:
            unseen = [cell[l][p]["f1"] for i, p in enumerate(train, 1) if i > n_at[l]]
            row.append(f"{statistics.mean(unseen):.4f}" if unseen else "")
        w.writerow(["", "not-yet-seen (mean F1)", ""] + row)

    # appendix: every metric per cell
    app = out_dir / "trajectory_detail.csv"
    with open(app, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["paper_id", "run_index", "state", "mode", "in_sample",
                    "tp", "tp_recall", "fp", "fn",
                    "precision", "recall", "f1"])
        by_mode = cells if cells else {args.match_mode: cell}
        for md, cm in by_mode.items():
            for i, p in enumerate(train, 1):
                for l in labels:
                    c = cm.get(l, {}).get(p)
                    if not c:
                        continue
                    w.writerow([p, i, l, md, "yes" if i <= n_at[l] else "no",
                                c["tp"], c["tp_recall"], c["fp"], c["fn"],
                                f"{c['precision']:.4f}", f"{c['recall']:.4f}",
                                f"{c['f1']:.4f}"])
            for p in held:
                for l in labels:
                    c = cm.get(l, {}).get(p)
                    if not c:
                        continue
                    w.writerow([p, "", l, md, "heldout", c["tp"],
                                c["tp_recall"], c["fp"], c["fn"],
                                f"{c['precision']:.4f}",
                                f"{c['recall']:.4f}", f"{c['f1']:.4f}"])

    # console view
    wid = max(12, max(len(l) for l in labels) + 1)
    print(f"\n{'paper (worst->best)':<24}" + "".join(f"{l:>{wid}}" for l in labels))
    print("-" * (24 + wid * len(labels)))
    for i, p in enumerate(train, 1):
        cells = []
        for l in labels:
            # Marker TRAILS its own value: a leading marker sits next to the
            # previous column and reads as belonging to it.
            mark = "<" if i == n_at[l] else " "
            cells.append(f"{cell[l][p]['f1']:>{wid-1}.3f}{mark}")
        print(f"{i:>3} {p:<20}" + "".join(cells))
    print("-" * (24 + wid * len(labels)))
    for name, key in (("HELD-OUT F1", "f1"), ("HELD-OUT precision", "precision"),
                      ("HELD-OUT recall", "recall")):
        vals = []
        for l in labels:
            agg = _prf(*[sum(cell[l][p][k] for p in held)
                       for k in ("tp", "fp", "fn", "tp_recall")])
            vals.append(f"{agg[key]:>{wid}.3f}")
        print(f"{name:<24}" + "".join(vals))
    vals = []
    for l in labels:
        unseen = [cell[l][p]["f1"] for i, p in enumerate(train, 1) if i > n_at[l]]
        vals.append(f"{statistics.mean(unseen):>{wid}.3f}" if unseen else " " * wid)
    print(f"{'not-yet-seen (mean F1)':<24}" + "".join(vals))

    print("\n  '<' marks the diagonal — the state at which that paper was "
          "distilled.\n  LEFT of it the paper was still UNSEEN, so those cells "
          "are out-of-sample;\n  reading down a column just left of the diagonal "
          "gives a learning curve.")
    if judge_label:
        print(f"  '{judge_label}' is a MEASUREMENT correction (FPs the silver "
              f"under-labelled), not\n  a rule change -- recall is identical to "
              f"the previous column by construction.")
    print(f"\nwrote {main}\n      {app}")


if __name__ == "__main__":
    sys.exit(main())
