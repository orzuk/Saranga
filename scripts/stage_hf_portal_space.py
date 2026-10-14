#!/usr/bin/env python3
"""Stage the full SARANGA portal as a Hugging Face Docker Space (RHCPP/saranga).

    python3 scripts/stage_hf_portal_space.py /tmp/saranga_portal_space
    (cd /tmp/saranga_portal_space && PORT=7860 SARANGA_SILVER_DIR=$PWD/silver_v6 \
        SARANGA_T3_REMOTE="curl -sfL https://huggingface.co/datasets/RHCPP/saranga/resolve/main/{cat}/json/{id}.json" \
        python3 portal/portal_server.py)          # test locally
    huggingface-cli upload RHCPP/saranga /tmp/saranga_portal_space . --repo-type=space \
        --delete="*"                              # replaces the old static Space's files

Layout: portal/ (pages, js, css, vendor, data), src/ (parser, viewer), extractors/rules/,
silver_v6/graphs/ (the 200 silver papers, LLM and rule pages, built here). Everything comes
from git, so any clone can stage it.
"""
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SILVER = REPO / "corpus/silver/opus-5.5__v6"   # LLM graphs; rules_v6/ holds the rule graphs
SKIP_DATA = {"tier2_test", "tier2_tex", "tier2.symlink.bak", "manifest_before_v6.json", "tier3-sample", "tier2"}


def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)


def main(out):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    d = REPO / "deploy/hf_space_portal"
    for f in ("Dockerfile", "README.md"):
        copy(d / f, out / f)
    p = REPO / "portal"
    for f in p.iterdir():
        if f.name in ("data", "cache", "graphs", "__pycache__") or f.suffix == ".bak":
            continue
        copy(f, out / "portal" / f.name)
    for f in (p / "data").iterdir():
        if f.name not in SKIP_DATA and f.name != "tier3_v6":
            copy(f, out / "portal/data" / f.name)
    # 100K index only (titles and counts); the graphs are read from the dataset on demand
    for f in [p / "data/tier3_v6/index.json"] + sorted((p / "data/tier3_v6").glob("*/index.json")):
        copy(f, out / "portal/data/tier3_v6" / f.relative_to(p / "data/tier3_v6"))
    copy(REPO / "scripts/opus_extract_prompt_v6.md", out / "scripts/opus_extract_prompt_v6.md")   # LLM agent prompt
    for f in sorted((REPO / "src").glob("*.py")):
        copy(f, out / "src" / f.name)
    for f in sorted((REPO / "src/LLMVersion").glob("*.py")):
        copy(f, out / "src/LLMVersion" / f.name)
    for f in (REPO / "src/graph_view").iterdir():
        if f.suffix in (".py", ".html", ".js", ".css"):
            copy(f, out / "src/graph_view" / f.name)
    copy(REPO / "extractors/rules/silver_v6__sentence_rules_haiku__2026-10",
         out / "extractors/rules/silver_v6__sentence_rules_haiku__2026-10")
    # the 200 silver papers' pages, built here from the JSONs in git (LLM and rule graphs)
    g = out / "silver_v6/graphs"
    g.mkdir(parents=True)
    build = [sys.executable, str(REPO / "src/graph_view/build.py")]
    for jsons, suffix in ((sorted(SILVER.glob("*.json")), "_new"), (sorted((SILVER / "rules_v6").glob("*.json")), "_rules")):
        r = subprocess.run(build + [str(j) for j in jsons] + ["-o", str(g), "--suffix", suffix],
                           capture_output=True, text=True)
        print(f"  {suffix}: " + (r.stdout.strip().splitlines() or ["?"])[-1])
        if r.returncode:
            sys.exit(r.stderr[-1000:])
    files = [x for x in out.rglob("*") if x.is_file()]
    print(f"staged {len(files)} files, {sum(x.stat().st_size for x in files) / 2**20:.0f} MB, in {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/saranga_portal_space")
