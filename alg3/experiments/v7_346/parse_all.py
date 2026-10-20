"""Parse all 346 papers of the v7 pool with one rule dir (no edge model) -> <out>/<pid>.json.
    python3 parse_all.py <rules_dir> <out_dir> [workers]"""
import csv, sys, multiprocessing as mp
from pathlib import Path
HERE = Path(__file__).resolve().parent
A3 = HERE.parents[1]
sys.path.insert(0, str(A3))
import analyze as AN                                          # noqa: E402
AN.TEX = A3 / "cache/v7_346/tex"

def init(rules):
    AN.TEX = A3 / "cache/v7_346/tex"
    AN._parse_init(rules, None)

if __name__ == "__main__":
    rules, out = sys.argv[1], Path(sys.argv[2])
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    out.mkdir(parents=True, exist_ok=True)
    pids = [r["arxiv_id"] for r in csv.DictReader(open(A3 / "cache/v7_346/split_A.csv"))]
    todo = [(p, str(out / f"{p}.json")) for p in pids if not (out / f"{p}.json").is_file()]
    print(f"parsing {len(todo)} papers with {rules} -> {out}", flush=True)
    with mp.Pool(w, initializer=init, initargs=(rules,)) as pool:
        for k, _ in enumerate(pool.imap_unordered(AN._parse_one, todo), 1):
            if k % 50 == 0:
                print(f"  {k}/{len(todo)}", flush=True)
    print("done", out, flush=True)
