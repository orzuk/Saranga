"""Error breakdown on the v7 VAL papers (never test): analyze.py graph mode on our parsed graphs,
per subset (S = 40 silver val, G = 28 gold-author val), plus the author-diagram breakdown on G.
    python3 analyze_v7.py <graph_dir_name> <S|G>        # node/edge breakdown vs v7
    python3 analyze_v7.py --diagrams <graph_dir_name>   # vs the authors' diagrams, gold val"""
import argparse, csv, importlib.util, json, sys
from collections import Counter
from pathlib import Path
HERE = Path(__file__).resolve().parent
A3 = HERE.parents[1]; REPO = A3.parent
sys.path[:0] = [str(A3), str(REPO / "src/LLMVersion"), str(REPO / "src")]
import analyze as AN  # noqa: E402
C = A3 / "cache/v7_346"

ap = argparse.ArgumentParser()
ap.add_argument("graphs"); ap.add_argument("subset", nargs="?", default="G")
ap.add_argument("--diagrams", action="store_true")
ap.add_argument("--top", type=int, default=25); ap.add_argument("--show", type=int, default=8)
ap.add_argument("--examples", type=int, default=3)
a = ap.parse_args()
gdir = A3 / "runs/v7_346/graphs" / a.graphs
if a.diagrams:
    import graph_score as GS
    spec = importlib.util.spec_from_file_location("ge", REPO / "docs/v7_handoff/gold_eval_v7.py")
    ge = importlib.util.module_from_spec(spec); spec.loader.exec_module(ge)
    pids = [r["arxiv_id"] for r in csv.DictReader(open(C / "split_A.csv"))
            if r["split"] == "val" and r["source"] == "gold_author"]
    papers = REPO / "corpus/gold_candidates/papers"
    tot, cs = Counter(), []
    rows = []
    for p in pids:
        gold = ge.gold_of(papers / p)
        pred = json.loads((gdir / f"{p}.json").read_text())
        cs.append(GS.score(pred, gold, **GS.PRESETS["author"]))
        b = ge.breakdown(pred, gold)
        for k in ("missed_reversed", "missed_unmatched_end", "missed_other", "extra"):
            tot[k] += len(b[k])
        tot["arrows"] += b["arrows"]; tot["boxes"] += b["gold_boxes"]; tot["boxes_unmatched"] += len(b["boxes_unmatched"])
        rows.append((p, b))
    s = GS.pooled(cs)
    print(f"{a.graphs}: {len(pids)} gold val papers vs author diagrams | node R {s['node_R']:.3f} "
          f"edge P {s['edge_P']:.3f} R {s['edge_R']:.3f} F1 {s['edge_F1']:.3f}")
    print("arrow errors:", dict(tot))
    for k in ("missed_other", "missed_unmatched_end", "missed_reversed", "extra"):
        ex = [(p, x) for p, b in rows for x in b[k]][:6]
        print(f"\n-- {k}: examples")
        for p, x in ex:
            print("  ", p, str(x)[:230])
    sys.exit()
split = C / f"split_{a.subset}.csv"
AN.SPLIT, AN.SILVER, AN.TEX = split, C / "silver", C / "tex"
AN.parse_val = lambda _a: gdir
AN.graph_mode(argparse.Namespace(top=a.top, show=a.show, examples=a.examples))
