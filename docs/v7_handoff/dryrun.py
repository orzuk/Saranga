"""Dry run over the 200 v6 silver papers with the code in CODE_DIR (no writes to the corpus).

Per paper: the LaTeX facts (summarised) and finalize() re-applied to the stored graph, compared with
the stored graph. Usage: dryrun.py CODE_DIR OUT.jsonl [--jobs N]"""
import copy
import hashlib
import json
import signal
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

CORPUS = Path("/mnt/c/Code/Github/Saranga/corpus/silver")
CODE = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2])
JOBS = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 6


def _timeout(*_):
    raise TimeoutError


def edge_key(e):
    return (e.get("source"), e.get("target"), e.get("type"))


def one(pid):
    sys.path[:0] = [str(CODE / "src"), str(CODE / "src" / "LLMVersion")]
    import latex_facts
    import extraction_finalize as F
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(600)
    t0 = time.time()
    tex = (CORPUS / "tex_pool" / f"{pid}.tex").read_text(encoding="utf-8", errors="replace")
    out = {"paper": pid}
    try:
        fx = latex_facts.extract_facts(tex)
        out["source_sha"] = hashlib.sha1(fx["source"].encode()).hexdigest()[:12]
        out["source_len"] = len(fx["source"])
        out["facts"] = sorted([f.get("kind") or "", f.get("env") or "", f.get("type") or "", f.get("start"),
                               f.get("end"), list(f.get("labels") or ()), f.get("number") or "",
                               f.get("proves") or ""]
                              for f in fx["facts"])
        out["sections"] = [(s.get("number"), s.get("title")) for s in fx.get("sections", [])]
        stored = json.loads((CORPUS / "opus-5.5__v6" / f"{pid}.json").read_text(encoding="utf-8"))
        g = copy.deepcopy(stored)
        rep = F.finalize(g, tex)
        out["errors"] = rep["errors"][:20]
        out["n_errors"], out["n_warnings"] = len(rep["errors"]), len(rep["warnings"])
        sn = {n["id"]: n for n in stored["nodes"]}
        gn = {n["id"]: n for n in g["nodes"]}
        changed = {}
        for i in set(sn) | set(gn):
            a, b = sn.get(i), gn.get(i)
            if a != b:
                ks = sorted(k for k in set(a or {}) | set(b or {}) if (a or {}).get(k) != (b or {}).get(k))
                changed[i] = ks if a and b else ("added" if b else "removed")
        out["nodes_changed"] = changed
        se = {edge_key(e): e for e in stored["edges"]}
        ge = {edge_key(e): e for e in g["edges"]}
        out["edges_added"] = sorted(map(list, set(ge) - set(se)))
        out["edges_removed"] = sorted(map(list, set(se) - set(ge)))
        out["edges_attr_changed"] = sorted(list(k) for k in set(se) & set(ge) if se[k] != ge[k])
        out["metadata_changed"] = sorted(k for k in set(stored["metadata"]) | set(g["metadata"])
                                         if stored["metadata"].get(k) != g["metadata"].get(k))
    except Exception as e:                     # noqa: BLE001
        out["exception"] = f"{type(e).__name__}: {e}"[:300]
    out["seconds"] = round(time.time() - t0, 1)
    return out


if __name__ == "__main__":
    papers = sorted(p.stem for p in (CORPUS / "opus-5.5__v6").glob("*.json"))
    with ProcessPoolExecutor(JOBS) as ex, OUT.open("w") as f:
        futs = [ex.submit(one, p) for p in papers]
        for k, fu in enumerate(as_completed(futs), 1):
            r = fu.result()
            f.write(json.dumps(r, default=list) + "\n")
            f.flush()
            print(f"{k}/{len(papers)} {r['paper']} {r['seconds']}s {r.get('exception', '')}", flush=True)
