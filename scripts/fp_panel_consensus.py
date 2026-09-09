#!/usr/bin/env python3
"""Join the four judges' verdicts and report adjusted precision.

Consensus, not a vote average. A rescue is credited where at least three of the
four judges say GENUINE; anything short of quorum is recorded as SPLIT and left
that way.
Splits are not noise to be resolved by majority -- they are the rows where what
counts as a missed annotation is genuinely contested, and collapsing them would
manufacture a precision number no judge actually supports.

Because a single number would hide that, precision is reported as a band:

  raw          every M3 FP is a real error             (0.7563 F1, the published one)
  unanimous    rescue only 4-0 GENUINE rows            floor
  3of4         rescue rows meeting quorum              the reported reading
  any          rescue rows any judge called GENUINE    ceiling

Recall is untouched throughout. A rescued FP is a correct extraction the silver
lacks, not a gold node found -- it leaves the numerator of precision's
denominator, and never enters recall's.

This is a read-only audit. Nothing here feeds the prune gate or the rule set.

Usage:
    python scripts/fp_panel_consensus.py \
        --fps  src/LLMVersion/heldout_eval_selected146/heldout_fp_m3.csv \
        --scores src/LLMVersion/heldout_eval_selected146/heldout_scores.jsonl \
        --panel src/LLMVersion/heldout_eval_selected146/panel/fp_panel_*.csv
"""

import argparse
import csv
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

G, F, M = "GENUINE", "FALSE_POSITIVE", "MISSING"


def f1(p, r):
    return 2 * p * r / (p + r) if p + r else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", required=True)
    ap.add_argument("--scores", required=True)
    ap.add_argument("--panel", nargs="+", required=True)
    ap.add_argument("--quorum", type=int, default=3,
                    help="votes needed to call a row (default 3 of 4)")
    ap.add_argument("--out", default=None, help="default: <fps dir>/panel/")
    args = ap.parse_args()

    fps = list(csv.DictReader(open(args.fps, encoding="utf-8")))
    order = [r["fp_id"] for r in fps]
    meta = {r["fp_id"]: r for r in fps}

    judges, votes = [], {}
    for p in args.panel:
        rows = list(csv.DictReader(open(p, encoding="utf-8")))
        name = rows[0]["model"] if rows else Path(p).stem
        judges.append(name)
        seen = {r["fp_id"]: r for r in rows}
        missing_ids = set(order) - set(seen)
        if missing_ids:
            raise SystemExit(f"{name}: {len(missing_ids)} fp_ids absent from "
                             f"{p} -- judge every FP or the panel is uneven")
        for fid, r in seen.items():
            # Verify identity rather than trust row order: a mismatched join
            # would silently compare verdicts about different spans.
            if (r["type"], r["paper_id"]) != (meta[fid]["type"],
                                              meta[fid]["paper_id"]):
                raise SystemExit(f"{name}: {fid} identity mismatch")
            votes[(name, fid)] = r["verdict"]
    n_j = len(judges)
    quorum = args.quorum
    if not 1 <= quorum <= n_j:
        raise SystemExit(f"--quorum {quorum} impossible with {n_j} judges")
    print(f"judges: {', '.join(judges)}   FPs: {len(order)}   "
          f"quorum: {quorum} of {n_j}")

    # ---- per-FP consensus --------------------------------------------------
    out_dir = Path(args.out) if args.out else Path(args.fps).parent / "panel"
    out_dir.mkdir(parents=True, exist_ok=True)
    table = out_dir / "fp_verdicts.csv"
    cons = {}
    with open(table, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=(
            ["fp_id", "type", "paper_id"] + judges +
            ["n_genuine", "n_false_positive", "n_missing", "consensus",
             "snippet"]))
        w.writeheader()
        for fid in order:
            vs = [votes[(j, fid)] for j in judges]
            ng, nf, nm = vs.count(G), vs.count(F), vs.count(M)
            # Quorum, not unanimity: a verdict counts when at least `quorum`
            # of the judges say the same thing. At 3-of-4 one judge may dissent
            # or fail to answer without voiding the row -- which matters,
            # because MISSING is a formatting failure, not a disagreement, and
            # unanimity would let one truncated reply veto a 3-0 call.
            if nm == n_j:
                c = "NO_VOTE"
            elif ng >= quorum:
                c = G
            elif nf >= quorum:
                c = F
            else:
                c = "SPLIT"
            cons[fid] = (c, ng, nf, nm)
            w.writerow(dict(zip(judges, vs), fp_id=fid,
                            type=meta[fid]["type"],
                            paper_id=meta[fid]["paper_id"],
                            n_genuine=ng, n_false_positive=nf, n_missing=nm,
                            consensus=c,
                            snippet=meta[fid]["snippet"][:300].replace("\n", " ")))
    print(f"wrote {table}")

    # ---- panel behaviour ---------------------------------------------------
    n = len(order)
    lines = []
    def say(s=""):
        print(s); lines.append(s)

    say("\n" + "=" * 70)
    say("PANEL BEHAVIOUR")
    say(f"{'judge':<22}{'GENUINE':>10}{'rate':>8}{'FALSE_POS':>11}{'MISSING':>9}")
    for j in judges:
        c = Counter(votes[(j, fid)] for fid in order)
        say(f"{j:<22}{c[G]:>10}{c[G]/n:>8.1%}{c[F]:>11}{c[M]:>9}")
    say("\nA judge that forgives far more than the others is not a better "
        "judge, it is a rubber stamp -- compare the rates, not the agreement.")

    say("\npairwise agreement (rows both judges answered)")
    for a, b in itertools.combinations(judges, 2):
        both = [fid for fid in order
                if votes[(a, fid)] != M and votes[(b, fid)] != M]
        ag = sum(1 for fid in both if votes[(a, fid)] == votes[(b, fid)])
        say(f"  {a:<20} {b:<20} {ag:>5}/{len(both):<5} {ag/len(both):>7.1%}"
            if both else f"  {a} {b}   no shared rows")

    cc = Counter(c for c, *_ in cons.values())
    say("\nconsensus")
    for k in (G, F, "SPLIT", "NO_VOTE"):
        if cc[k]:
            say(f"  {k:<16}{cc[k]:>6}  {cc[k]/n:6.1%}")
    say(f"\n{cc['SPLIT']} FPs are recorded as split and left unresolved.")

    # ---- adjusted precision ------------------------------------------------
    rows = [json.loads(l) for l in open(args.scores, encoding="utf-8")]
    m3 = [r for r in rows if r["mode"] == "m3"]
    tp = sum(r["tp"] for r in m3)
    raw_fp = sum(r["fp"] for r in m3)
    tp_rec = sum(r["tp_recall"] for r in m3)
    fn = sum(r["fn"] for r in m3)
    rec = tp_rec / (tp_rec + fn)
    if raw_fp != n:
        raise SystemExit(f"panel covers {n} FPs but the run recorded {raw_fp}")

    readings = {
        "raw":       lambda c, ng, nf: False,
        "unanimous": lambda c, ng, nf: ng == n_j,
        f"{quorum}of{n_j}":  lambda c, ng, nf: ng >= quorum,
        "any":       lambda c, ng, nf: ng > 0,
    }
    say("\n" + "=" * 70)
    say(f"ADJUSTED PRECISION -- 146 rules, 140 held-out papers, M3 "
        f"(containment, th=0.7, cover=0.7)")
    say(f"TP {tp}   raw FP {raw_fp}   recall {rec:.4f} (unchanged by judging)")
    say(f"\n{'reading':<12}{'rescued':>9}{'FP_adj':>9}{'precision':>11}{'F1':>9}"
        f"{'dF1':>9}")
    base = None
    for name, keep in readings.items():
        resc = sum(1 for fid in order
                   if keep(*cons[fid][:3])) if name != "raw" else 0
        fp_adj = raw_fp - resc
        p = tp / (tp + fp_adj)
        f = f1(p, rec)
        base = f if base is None else base
        say(f"{name:<12}{resc:>9}{fp_adj:>9}{p:>11.4f}{f:>9.4f}"
            f"{f - base:>+9.4f}")
    say(f"\nThe headline adjusted number is `{quorum}of{n_j}`, the reported "
        f"consensus rule. `unanimous` is the floor it cannot go below and "
        f"`any` the ceiling, so the two bracket how much the contested rows "
        f"could still move it.")

    # ---- per-type ----------------------------------------------------------
    say(f"\nper type ({quorum}of{n_j} reading)")
    say(f"{'type':<14}{'tp':>7}{'rawFP':>7}{'resc':>6}{'split':>6}"
        f"{'P_raw':>8}{'P_adj':>8}")
    tp_t = Counter()
    for r in m3:
        for t, d in r["per_type"].items():
            tp_t[t] += d["tp"]
    fp_t, res_t, spl_t = Counter(), Counter(), Counter()
    for fid in order:
        t = meta[fid]["type"]
        fp_t[t] += 1
        c, ng, nf, nm = cons[fid]
        res_t[t] += int(c == G)
        spl_t[t] += int(c == "SPLIT")
    for t in sorted(set(tp_t) | set(fp_t)):
        if not tp_t[t] and not fp_t[t]:
            continue
        pr = tp_t[t] / (tp_t[t] + fp_t[t]) if tp_t[t] + fp_t[t] else 0.0
        adj = fp_t[t] - res_t[t]
        pa = tp_t[t] / (tp_t[t] + adj) if tp_t[t] + adj else 0.0
        say(f"{t:<14}{tp_t[t]:>7}{fp_t[t]:>7}{res_t[t]:>6}{spl_t[t]:>6}"
            f"{pr:>8.4f}{pa:>8.4f}")

    rep = out_dir / "fp_panel_report.txt"
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {rep}")


if __name__ == "__main__":
    main()
