#!/usr/bin/env python3
"""
Side-by-side comparison: Opus extraction graph vs current rules-parser graph.

For each paper:
  - Opus side  = portal/data/tier2/paperNNN.json  (claude-opus-4-8, v4.1)
  - Rules side = parse paperNNN/source/paperNNN.tex with PaperParser(extraction_mode='rules')
Both rendered with src/visualize_annotation.py at the same resolution, then
composed into one PNG with a header showing node/edge counts.

Usage:
  python compare_opus_rules.py 001 005 006        # specific papers
  python compare_opus_rules.py all                # 001..011
"""
import json, subprocess, sys, os
from pathlib import Path

REPO = Path(__file__).resolve().parent
ALIGN = Path("/Users/yaronot/Datasets/Authomathics_data/alignment/papers")
OPUS_DIR = REPO / "portal/data/tier2"
SRC = REPO / "src"
OUT = REPO / "compare_opus_rules"
WORK = Path("/tmp/cmp_opus_rules")
OUT.mkdir(exist_ok=True)
WORK.mkdir(exist_ok=True)

sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
from math_paper_parser import PaperParser  # noqa: E402

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
Image.MAX_IMAGE_PIXELS = None  # these renders are legitimately huge


# Node types hidden by visualize_annotation.py "standard" resolution.
HIDDEN_TYPES = {"equation", "proof_step", "algorithm_step"}


def _drawn(d):
    """Node-id set the renderer actually draws (standard resolution)."""
    return {n["id"] for n in d.get("nodes", [])
            if "id" in n and n.get("type") not in HIDDEN_TYPES}


def longest_path(d):
    """Longest directed path (edges) over the DRAWN node DAG = graph depth."""
    from collections import defaultdict
    ids = _drawn(d)
    adj = defaultdict(list)
    indeg = defaultdict(int)
    for e in d.get("edges", []):
        s, t = e.get("source"), e.get("target")
        if s in ids and t in ids:
            adj[s].append(t); indeg[t] += 1
    # memoized DFS; tolerate cycles by visited-guard
    best = {}
    state = {}

    def dfs(u):
        if u in best:
            return best[u]
        if state.get(u) == 1:      # back-edge (cycle) -> treat as 0
            return 0
        state[u] = 1
        m = 0
        for v in adj[u]:
            m = max(m, 1 + dfs(v))
        state[u] = 2
        best[u] = m
        return m

    return max((dfs(n) for n in ids), default=0)


def counts(d):
    """Counts of the DRAWN graph (equations/steps hidden), matching the image."""
    ids = _drawn(d)
    e = sum(1 for x in d.get("edges", [])
            if x.get("source") in ids and x.get("target") in ids)
    return len(ids), e, longest_path(d)


def render(json_path, png_path):
    """Render a unified-format JSON to PNG via visualize_annotation.py."""
    r = subprocess.run(
        [sys.executable, "visualize_annotation.py", str(json_path), "-o", str(png_path)],
        cwd=str(SRC), capture_output=True, text=True)
    if not png_path.exists():
        print(f"  [render FAIL] {json_path.name}\n{r.stdout[-800:]}\n{r.stderr[-800:]}")
        return False
    return True


def label_strip(text, width, h=64):
    img = Image.new("RGB", (width, h), "white")
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 30)
    except Exception:
        f = ImageFont.load_default()
    tw = d.textlength(text, font=f)
    d.text(((width - tw) / 2, (h - 30) / 2), text, fill="black", font=f)
    return img


def compose(pid, opus_png, rules_png, opus_c, rules_c, out_png):
    """Stack vertically (Opus top, Rules below) at matched width — keeps the
    wide horizontal layouts readable."""
    a = Image.open(opus_png).convert("RGB")
    b = Image.open(rules_png).convert("RGB")
    W = min(max(a.width, b.width), 2600)
    a = a.resize((W, int(a.height * W / a.width)))
    b = b.resize((W, int(b.height * W / b.width)))
    la = label_strip(
        f"OPUS  —  {opus_c[0]} nodes / {opus_c[1]} edges / depth {opus_c[2]}  (drawn; equations hidden)", W, h=70)
    lb = label_strip(
        f"RULES PARSER  —  {rules_c[0]} nodes / {rules_c[1]} edges / depth {rules_c[2]}  (drawn; equations hidden)", W, h=70)
    parts = [la, a, lb, b]
    H = sum(p.height for p in parts) + 16
    canvas = Image.new("RGB", (W, H), "white")
    y = 0
    for p in parts:
        canvas.paste(p, (0, y)); y += p.height
        if p is a:  # divider line between the two panels
            ImageDraw.Draw(canvas).line([(0, y + 7), (W, y + 7)], fill="black", width=3)
            y += 16
    canvas.save(out_png)
    return out_png


def process(pid):
    opus_json = OPUS_DIR / f"paper{pid}.json"
    tex = ALIGN / f"paper{pid}" / "source" / f"paper{pid}.tex"
    if not opus_json.exists():
        print(f"paper{pid}: no Opus json ({opus_json}) — skip"); return None
    if not tex.exists():
        print(f"paper{pid}: no tex ({tex}) — skip"); return None

    # rules parse
    g = PaperParser(extraction_mode="rules").parse_file(str(tex))
    rules_doc = g.to_unified_dict()
    rules_json = WORK / f"paper{pid}_rules.json"
    rules_json.write_text(json.dumps(rules_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    opus_doc = json.load(open(opus_json))
    oc, rc = counts(opus_doc), counts(rules_doc)

    opus_png = WORK / f"paper{pid}_opus.png"
    rules_png = WORK / f"paper{pid}_rules.png"
    if not render(opus_json, opus_png):
        return None
    if not render(rules_json, rules_png):
        return None
    out_png = OUT / f"paper{pid}_compare.png"
    compose(pid, opus_png, rules_png, oc, rc, out_png)
    print(f"paper{pid}: OPUS {oc[0]}n/{oc[1]}e/d{oc[2]}  vs  RULES {rc[0]}n/{rc[1]}e/d{rc[2]}  -> {out_png}")
    return out_png


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["all"]:
        args = [f"{i:03d}" for i in range(1, 12)]
    for pid in args:
        try:
            process(pid)
        except Exception as e:
            import traceback
            print(f"paper{pid}: ERROR {e}")
            traceback.print_exc()
