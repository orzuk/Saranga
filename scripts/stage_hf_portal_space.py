#!/usr/bin/env python3
"""Stage the full SARANGA portal as a Hugging Face Docker Space (RHCPP/saranga).

    python3 scripts/stage_hf_portal_space.py /tmp/saranga_portal_space
    (cd /tmp/saranga_portal_space && PORT=7860 SARANGA_SILVER_DIR=$PWD/silver_v6 \
        SARANGA_T3_REMOTE="curl -sfL https://huggingface.co/datasets/RHCPP/saranga/resolve/main/{cat}/json/{id}.json" \
        python3 portal/portal_server.py)          # test locally
    huggingface-cli upload RHCPP/saranga /tmp/saranga_portal_space . --repo-type=space \
        --delete="*"                              # replaces the old static Space's files

Layout: portal/ (pages, js, css, vendor, data), src/ (parser, viewer), extractors/rules/ and
extractors/edges/ (the alg3 extractor and its edge model, alg3/edges.py),
silver_v6/graphs/ (the 200 silver papers, LLM and rule pages, built here). Only files
tracked by git are staged (never untracked data, the gold candidates or run_local.sh), so
any clone stages the same Space.
"""
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SILVER = "corpus/silver/opus-5.5__v6/"     # LLM graphs; rules_v6/ holds the rule graphs
RULES = "extractors/rules/silver_v7__sentence_tagger__2026-10/"   # alg3, the "Your paper" rule-based extractor
EDGES = "extractors/edges/silver_v7__edges_allpairs__2026-10/"    # its learned edges (alg3/edges.py)
sys.path.insert(0, str(REPO / "src"))
SKIP = ("portal/graphs/", "portal/data/tier2/", "portal/data/tier2_tex/", "portal/data/tier3-sample",
        "portal/gold_", "portal/run_local.sh")


def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / src, dst)


def main(out):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    git = lambda *a: subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True).stdout
    tracked = [f[2:] for f in git("ls-files", "-z", "-t").split("\0") if f[:1] == "H"]   # S: skip-worktree, not checked out
    for f in ("Dockerfile", "README.md"):
        copy("deploy/hf_space_portal/" + f, out / f)
    for f in tracked:
        p = Path(f)
        if (f.startswith("portal/") and not f.startswith(SKIP)
                or f.startswith(RULES) or f.startswith(EDGES) or f in ("alg3/edges.py", "alg3/edges_all.py")
                or f == "scripts/opus_extract_prompt_v7.md"                           # LLM agent prompt
                or p.suffix == ".py" and str(p.parent) in ("src", "src/LLMVersion")
                or str(p.parent) == "src/graph_view" and p.suffix in (".py", ".html", ".js", ".css")):
            copy(f, out / f)
    # no git in the container: the LLM runs' prompt version
    from provenance import code_commit
    (out / "COMMIT").write_text(code_commit(7, dirty=False))
    # the portal footer's "updated <date> · version <commit>"
    (out / "portal/version.json").write_text(json.dumps({"commit": code_commit(7, dirty=False),
                                                         "date": datetime.date.today().isoformat()}))
    # the 200 silver papers' pages, built here from the JSONs in git (LLM and rule graphs)
    g = out / "silver_v6/graphs"
    g.mkdir(parents=True)
    build = [sys.executable, str(REPO / "src/graph_view/build.py")]
    for d, suffix in ((SILVER, "_new"), (SILVER + "rules_v6/", "_rules")):
        jsons = [str(REPO / f) for f in tracked if f.startswith(d) and f.endswith(".json") and "/" not in f[len(d):]]
        r = subprocess.run(build + jsons + ["-o", str(g), "--suffix", suffix],
                           capture_output=True, text=True)
        print(f"  {suffix}: " + (r.stdout.strip().splitlines() or ["?"])[-1])
        if r.returncode:
            sys.exit(r.stderr[-1000:])
    files = [x for x in out.rglob("*") if x.is_file()]
    print(f"staged {len(files)} files, {sum(x.stat().st_size for x in files) / 2**20:.0f} MB, in {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/saranga_portal_space")
