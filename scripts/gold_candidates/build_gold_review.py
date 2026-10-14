#!/usr/bin/env python3
"""Build the review material for author-diagram gold candidates.

For each paper folder corpus/gold_candidates/papers/<id>/ holding
  paper.tex          the paper's flattened LaTeX (from the cluster copy of arXiv)
  figure.json        the located diagram figure (caption, LaTeX of the figure)
  graph_tikz.json    the diagram parsed from its drawing code (nodes, edges, \\ref labels)
this writes
  full.json          our graph of the whole paper (rule-based extractor)
  gold.json          the author's diagram in our format: one node per diagram box, mapped
                     through the paper's \\label to our nodes; one `uses` edge per arrow
  gold_new.html      the viewer page of gold.json (src/graph_view/build.py)
  paper.pdf, figpage.png   the arXiv PDF and the page that holds the figure
  meta.json          everything the review page shows
and corpus/gold_candidates/index.json for the list page.

Usage: python3 scripts/gold_candidates/build_gold_review.py [--ids a,b] [--no-pdf]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "corpus" / "gold_candidates"
PAPERS = ROOT / "papers"
RULES_DIR = REPO / "extractors" / "rules" / "silver_v6__sentence_rules_haiku__2026-10"
BUILD = REPO / "src" / "graph_view" / "build.py"
sys.path[:0] = [str(REPO / "src" / "LLMVersion"), str(REPO / "src"), str(Path(__file__).resolve().parent)]
from math_paper_parser import parse_to_unified  # noqa: E402

RESULT_KINDS = ("theorem", "lemma", "proposition", "corollary", "claim", "definition",
                "conjecture", "remark", "example", "assumption", "algorithm", "equation")


def arxiv_id(folder: str) -> str:
    m = re.match(r"^([a-z\-]+)(\d{7})$", folder)          # math0607726 -> math/0607726
    return f"{m.group(1)}/{m.group(2)}" if m else folder


def merge_diagrams(graphs: list) -> dict:
    """All parsed diagrams of the paper as one graph: boxes citing the same results are one node.

    A paper may draw several diagrams (one per main theorem); the same result can appear
    in more than one, or twice in one drawing."""
    nodes, edges, key_of = [], [], {}
    for k, g in enumerate(graphs):
        local = {}
        linked = {x for e in g.get("edges", []) for x in (e["from"], e["to"])}
        for n in g.get("nodes", []):
            if not (n.get("text") or "").strip() and n["id"] not in linked:
                continue                                 # a decorative shape (a 'fit' frame)
            labs = tuple(sorted({r["label"] for r in n.get("refs", [])}))
            key = labs or (k, n["id"])
            if key not in key_of:
                key_of[key] = f"d{len(nodes)}"
                nodes.append(dict(n, id=key_of[key]))
            local[n["id"]] = key_of[key]
        for e in g.get("edges", []):
            if e["from"] in local and e["to"] in local:
                edges.append(dict(e, **{"from": local[e["from"]], "to": local[e["to"]]}))
    seen, out = set(), []
    for e in edges:
        if (e["from"], e["to"]) not in seen:
            seen.add((e["from"], e["to"]))
            out.append(e)
    return {"nodes": nodes, "edges": out, "n_drawings": len(graphs)}


def strip_tex(s: str) -> str:
    s = (s or "").replace("\\\\", " ").replace("\\S", "§")   # TikZ line breaks; section sign
    s = re.sub(r"\\(?:color|textcolor|nodepart)\s*\{[^}]*\}", " ", s)   # formatting, not text
    s = re.sub(r"\\(ref|cref|Cref|eqref|label)\{[^}]*\}", "", s)
    s = re.sub(r"\\[A-Za-z]+\*?", " ", s)
    return re.sub(r"[{}$~\\]+", " ", re.sub(r"\s+", " ", s)).strip()


_TYPED_NUM = re.compile(r"(?i)\b(theorems?|thms?|lemmas?|lems?|propositions?|props?|corollar(?:y|ies)|cors?|"
                        r"definitions?|defs?|claims?|remarks?|conjectures?|sections?|secs?|§)\.?\s*~?\s*"
                        r"([A-Z]?\d+(?:\.\d+)*[a-z]?)")
_TYPE_WORD = {"thm": "theorem", "lem": "lemma", "prop": "proposition", "cor": "corollary", "def": "definition",
              "sec": "section", "§": "section"}


def _type_word(w: str) -> str:
    w = w.lower().rstrip("s") if w.lower() not in ("ies",) else w.lower()
    w = re.sub(r"corollarie$|corollar$", "corollary", w)
    return _TYPE_WORD.get(w, w)


def to_gold(pid: str, full: dict, diag: dict, fig: dict, macros: dict, fx: dict) -> tuple[dict, list, list]:
    """The diagram as a graph in our format, plus review rows for its nodes and edges.

    A box is matched to our nodes through the \\ref labels inside it or, when the author typed the
    number ("Lemma 3.2"), through the printed numbers latex_facts computes; boxes are named by
    their printed numbers so they read like the figure."""
    import latex_macros
    expand = lambda x: latex_macros.expand_macros(x, macros) if macros else x
    facts = {f["id"]: f for f in fx.get("facts", [])}
    sec_num = {str(x.get("number")): x.get("title", "") for x in fx.get("sections", []) if x.get("number")}

    def printed(label):                                   # "Lemma 6.2" for a label, if LaTeX numbers it
        info = fx.get("labels", {}).get(label) or {}
        f = facts.get(info.get("id") or "")
        if f and info.get("number"):
            return f"{f.get('display') or f.get('type', '').capitalize()} {info['number']}"
        if info.get("kind") == "section" and info.get("number"):
            return f"Section {info['number']}"
        return None
    labels = dict(full.get("metadata", {}).get("labels", {}) or {})
    ours = {n["id"]: n for n in full.get("nodes", [])}
    # the rule-based output keeps each node's own \label in `label`; other \label{}s inside a
    # node's LaTeX (several labels, labelled equations) point to that node too
    for n in full.get("nodes", []):
        if n.get("label"):
            labels.setdefault(n["label"], {"node": n["id"], "kind": "env"})
    for n in full.get("nodes", []):
        if n.get("type") == "proof":
            continue
        for lab in re.findall(r"\\label\{([^}]*)\}", n.get("raw_latex") or ""):
            labels.setdefault(lab, {"node": n["id"], "kind": "env"})
    nodes, node_rows, idmap = [], [], {}
    for i, dn in enumerate(diag.get("nodes", [])):
        refs = dn.get("refs", [])
        hits, secs = [], []
        names = []
        for r in refs:
            info = labels.get(r["label"]) or {}
            names.append(printed(r["label"]) or r["label"])
            if info.get("node") and info["node"] in ours:
                hits.append(info["node"])
            elif info.get("kind") == "section" or r.get("target", "").startswith(("section", "subsection")):
                secs.append(r["target"].split(" ", 1)[-1] if r.get("target") else r["label"])
        text = strip_tex(dn.get("text", ""))
        cited = bool(re.search(r"\\cite", dn.get("text", "")))   # "[13] (Theorem 2.1)": another paper's result
        if not refs and not cited:                       # numbers typed by hand: "Lemma 3.2", "Section 4"
            for m in _TYPED_NUM.finditer(dn.get("text", "")):
                typ_, num = _type_word(m.group(1)), m.group(2)
                if typ_ == "section":
                    secs.append(f"{num} {sec_num.get(num, '')}".strip())
                    names.append(f"Section {num}")
                    continue
                f = facts.get(fx.get("number_index", {}).get(f"{typ_} {num}", ""))
                if not f:
                    continue
                names.append(f"{f.get('display') or typ_.capitalize()} {num}")
                node = next((labels[l]["node"] for l in f.get("labels") or [] if l in labels), None)
                if not node:                             # unlabelled: our node with the same opening words
                    head = re.sub(r"\s+", " ", f.get("statement") or "")[:60]
                    node = next((n["id"] for n in ours.values() if head and
                                 re.sub(r"\s+", " ", n.get("raw_latex") or "").find(head[:40]) >= 0), None)
                if node and node in ours:
                    hits.append(node)
        gid = f"G{i + 1}"
        idmap[dn["id"]] = gid
        if hits:
            first = ours[hits[0]]
            typ = first.get("type", "theorem")
            stmt = "\n\n".join(expand(re.sub(r"\\label\{[^}]*\}", "", ours[h].get("raw_latex") or ours[h].get("statement") or ""))
                                 for h in hits)
            status = "mapped"
        elif secs:                                       # a section box citing a source stays a section
            typ, stmt, status = "remark", "Section: " + "; ".join(secs), "section"
        elif cited:
            typ, stmt, status = "theorem", "Cited: " + (text or ""), "cited"
        else:
            typ, stmt, status = "remark", text or "(empty box)", "unmatched"
        extra = _TYPED_NUM.sub(" ", re.sub(r"(?i)\b(theorems?|lemmas?|propositions?|corollar(?:y|ies)|definitions?|"
                                          r"claims?|sections?|and)\b|[&,.:;()]", " ", text or "")).strip()
        name = ", ".join(dict.fromkeys(names)) or text[:80] or None
        if names and len(extra) > 3:                     # the box also says what the result is
            name = f"{name}: {extra}"
        name = (name or "")[:100] or None
        nodes.append({"id": gid, "type": typ, "name": name, "statement": stmt,
                      "origin": "paper", "tags": ["diagram", status], "maps_to": hits})   # never hidden by the viewer
        hits = list(dict.fromkeys(hits))
        node_rows.append({"gid": gid, "box_text": text[:200], "refs": [r["label"] for r in refs], "printed": names,
                          "maps_to": hits, "our_types": [ours[h].get("type") for h in hits],
                          "status": status})
    edges, edge_rows = [], []
    for e in diag.get("edges", []):
        s, t = idmap.get(e["from"]), idmap.get(e["to"])
        if not s or not t or s == t:
            continue
        edges.append({"source": s, "target": t, "type": "uses", "confidence": 1.0})
        edge_rows.append({"source": s, "target": t, "directed": bool(e.get("directed", True))})
    gold = {"metadata": {"paper_id": pid, "title": full.get("metadata", {}).get("title", ""),
                         "extractor": "author diagram (parsed from the figure's LaTeX)",
                         "caption": strip_tex((fig or {}).get("caption", ""))[:500]},
            "nodes": nodes, "edges": edges}
    return gold, node_rows, edge_rows


def fetch_pdf(aid: str, dst: Path) -> bool:
    """Download the arXiv PDF politely (3 s between requests; back off when throttled)."""
    if dst.is_file() and dst.stat().st_size > 1000:
        return True
    req = urllib.request.Request(f"https://export.arxiv.org/pdf/{aid}", headers={"User-Agent": "saranga-gold-review"})
    for wait in (0, 30, 120, 300):
        time.sleep(wait)
        try:
            data = urllib.request.urlopen(req, timeout=90).read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                continue
            return False
        except Exception:                                # noqa: BLE001
            continue
        time.sleep(3)
        if not data.startswith(b"%PDF"):
            return False
        dst.write_bytes(data)
        return True
    return False


_BOX_LINE = re.compile(r"(?i)(theorem|thm\.?|lemma|lem\.?|proposition|prop\.?|corollary|cor\.?|definition|def\.?|"
                       r"claim|section|sec\.?|§)\s*[\dA-Z][\d.]*[a-z]?")


def find_fig_page(pdf: Path, caption: str) -> int:
    """The PDF page whose text best matches the caption (1-based; 0 if not found)."""
    words = [w for w in re.findall(r"[A-Za-z]{5,}", caption)]
    words = list(dict.fromkeys(words))[-14:] or ["figure"]
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    best, best_n = 0, 0
    for p, page in enumerate(txt.split("\f"), start=1):     # pdftotext separates pages by form feeds
        flat = re.sub(r"\s+", " ", page).lower()
        hit = sum(w.lower() in flat for w in words) + (3 if "figure" in flat and words[0].lower() in flat else 0)
        hit += 3 * sum(1 for ln in page.splitlines()                 # "Lemma 4.3" alone: a box
                       for cell in re.split(r"\s{3,}", ln.strip()) if _BOX_LINE.fullmatch(cell))
        if hit > best_n:
            best, best_n = p, hit
    return best


def reparse(folder: Path) -> list:
    """Parse every located diagram of the paper again from its LaTeX (diagram_parser.py),
    writing graph_tikz.json; the survey's own parse is kept only when nothing was located."""
    import diagram_parser as dp
    fj = folder / "figure.json"
    figs = json.loads(fj.read_text()).get("figures", []) if fj.is_file() else []
    tex = dp.strip_comments((folder / "paper.tex").read_text(encoding="utf-8", errors="replace"))
    lmap, macros = dp.label_map(tex), dp.ref_macros(tex)
    graphs = []
    for f in figs:
        if not f.get("found"):
            continue
        for code in f.get("tikz", []):
            code = dp.strip_comments(code)
            if code.startswith("\\begin{tikzcd}"):
                g = dp.parse_grid(re.sub(r"^\\begin\{tikzcd\}(\[[^\]]*\])?|\\end\{tikzcd\}$", "", code), "tikzcd", lmap, macros)
                g["format"] = "tikzcd"
            else:
                g = dp.parse_tikz(code, lmap, macros)
                g["format"] = "tikz"
            graphs.append(dict(g, fig_idx=f.get("fig_idx")))
        for code in f.get("xymatrix", []):
            graphs.append(dict(dp.parse_grid(dp.strip_comments(code), "xymatrix", lmap, macros),
                               format="xymatrix", fig_idx=f.get("fig_idx")))
        for code in f.get("picture", []):
            graphs.append(dict(dp.parse_picture(dp.strip_comments(code), lmap, macros),
                               format="picture", fig_idx=f.get("fig_idx")))
    graphs = [g for g in graphs if g.get("nodes")]
    if graphs:
        (folder / "graph_tikz.json").write_text(json.dumps(graphs, indent=1, ensure_ascii=False))
    elif (folder / "graph_tikz.json").is_file():
        graphs = json.loads((folder / "graph_tikz.json").read_text())
    return graphs


def page_hint(folder: Path, out: dict) -> str:
    """Text to find the figure's page by: its caption, else the paragraph just before it."""
    cap = strip_tex(out.get("caption", ""))
    if len(re.findall(r"[A-Za-z]{4,}", cap)) >= 5:
        return cap
    tex = (folder / "paper.tex").read_text(encoding="utf-8", errors="replace")
    head = (out.get("figure_latex") or "")[:200]
    i = tex.find(head[:120]) if head else -1
    before = tex[max(0, i - 1500):i] if i > 0 else ""
    before = re.sub(r"%.*", "", before)
    return cap + " " + strip_tex(before)[-600:]


def add_pdf(folder: Path, out: dict) -> None:
    """Fetch the arXiv PDF and render the page(s) holding the figure."""
    if fetch_pdf(out["arxiv"], folder / "paper.pdf"):
        out["pdf"] = "paper.pdf"
        tmp = Path(tempfile.mkdtemp())                   # the PDF tools are slow on the Windows drive
        local = tmp / "paper.pdf"
        shutil.copy(folder / "paper.pdf", local)
        page = find_fig_page(local, page_hint(folder, out))
        out["fig_page"] = page
        if page:                                 # the page found and the next (figures float)
            out["figpages"] = []
            for k, pg in enumerate((page, page + 1)):
                name = "figpage" if k == 0 else "figpage2"
                subprocess.run(["pdftoppm", "-f", str(pg), "-l", str(pg), "-r", "110", "-png", "-singlefile",
                                str(local), str(tmp / name)], capture_output=True)
                if (tmp / f"{name}.png").is_file():
                    shutil.copy(tmp / f"{name}.png", folder / f"{name}.png")
                    out["figpages"].append(f"{name}.png")
            out["figpage"] = (out["figpages"] or [None])[0]
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        out["problems"].append("PDF not downloaded")


def build_one(folder: Path, do_pdf: bool) -> dict:
    pid = folder.name
    aid = arxiv_id(pid)
    out = {"id": pid, "arxiv": aid, "problems": []}
    fig = {}
    if (folder / "figure.json").is_file():
        fj = json.loads((folder / "figure.json").read_text())
        figs = [f for f in fj.get("figures", []) if f.get("found")]
        fig = figs[0] if figs else {}
    out["caption"] = fig.get("caption", "")
    out["figure_latex"] = fig.get("env", "")[:20000]
    if not (folder / "paper.tex").is_file():
        out["problems"].append("no LaTeX source")
        return out
    full = parse_to_unified(folder / "paper.tex", pid, str(RULES_DIR))
    (folder / "full.json").write_text(json.dumps(full))
    out["title"] = full.get("metadata", {}).get("title", "")
    out["n_ours"] = len(full.get("nodes", []))
    graphs = reparse(folder)
    if not graphs:
        out["problems"].append("diagram not parsed from its LaTeX")
    else:
        import latex_macros
        import latex_facts
        tex = (folder / "paper.tex").read_text(encoding="utf-8", errors="replace")
        macros = latex_macros.read_definitions(tex)
        try:
            fx = latex_facts.extract_facts(tex)
        except Exception:                                # noqa: BLE001  (numbers are a nicety)
            fx = {}
        gold, nrows, erows = to_gold(pid, full, merge_diagrams(graphs), fig, macros, fx)
        gold["metadata"]["title"] = out["title"]
        (folder / "gold.json").write_text(json.dumps(gold, indent=1))
        out.update(nodes=nrows, edges=erows, n_nodes=len(nrows), n_edges=len(erows), n_drawings=len(graphs),
                   n_mapped=sum(r["status"] == "mapped" for r in nrows))
        r = subprocess.run([sys.executable, str(BUILD), str(folder / "gold.json"), "-o", str(folder), "--libs", "cdn"],
                           capture_output=True, text=True, timeout=300)
        if not nrows:
            out["problems"].append("diagram parsed to no boxes")
        elif (folder / "gold_new.html").is_file():
            out["gold_page"] = "gold_new.html"
        else:
            out["problems"].append("viewer build failed: " + r.stderr[-200:])
        r = subprocess.run([sys.executable, str(BUILD), str(folder / "full.json"), "-o", str(folder), "--libs", "cdn"],
                           capture_output=True, text=True, timeout=300)
        if (folder / "full_new.html").is_file():
            out["full_page"] = "full_new.html"
    if do_pdf:
        add_pdf(folder, out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--pdf-only", action="store_true", help="only fetch PDFs / figure pages for built papers")
    ap.add_argument("--index-only", action="store_true", help="rebuild index.json from the papers' meta.json")
    ap.add_argument("--ids-file", default="")
    ap.add_argument("--candidates", default=str(ROOT / "candidates.json"),
                    help="survey rows (granularity, found_by, category, ...) keyed by id")
    a = ap.parse_args()
    cand = {}
    if Path(a.candidates).is_file():
        cand = {r["arxiv_id"].replace("/", ""): r for r in json.loads(Path(a.candidates).read_text())}
    want = set(filter(None, a.ids.split(",")))
    if a.ids_file:
        want |= set(Path(a.ids_file).read_text().split())
    if a.index_only:
        write_index([json.loads(f.read_text()) for f in sorted(PAPERS.glob("*/meta.json"))], replace=True)
        return
    if a.pdf_only:
        for folder in sorted(PAPERS.iterdir()):
            mf = folder / "meta.json"
            if not mf.is_file() or (want and folder.name not in want):
                continue
            m = json.loads(mf.read_text())
            if "no LaTeX source" in m.get("problems", []):
                continue
            m["problems"] = [x for x in m.get("problems", []) if x != "PDF not downloaded"]
            add_pdf(folder, m)
            mf.write_text(json.dumps(m, indent=1))
            print(f"{folder.name:14s} page={m.get('fig_page')} {m.get('problems')}", flush=True)
        return
    index = []
    for folder in sorted(PAPERS.iterdir()):
        if not folder.is_dir() or (want and folder.name not in want):
            continue
        t0 = time.time()
        try:
            m = build_one(folder, not a.no_pdf)
            if a.no_pdf and (folder / "meta.json").is_file():      # keep the figure page found before
                old_m = json.loads((folder / "meta.json").read_text())
                for k in ("pdf", "fig_page", "figpage", "figpages"):
                    if k in old_m and k not in m:
                        m[k] = old_m[k]
        except Exception as e:                           # noqa: BLE001
            m = {"id": folder.name, "arxiv": arxiv_id(folder.name), "problems": [f"build error: {e!r}"]}
        c = cand.get(folder.name, {})
        m["survey"] = {k: c.get(k, "") for k in ("primary_category", "year", "granularity", "origin_format",
                                                  "found_by", "caption", "note", "in_100k")}
        m["title"] = m.get("title") or c.get("title", "")
        (folder / "meta.json").write_text(json.dumps(m, indent=1))
        m["pilot"] = bool(c.get("pilot"))
        (folder / "meta.json").write_text(json.dumps(m, indent=1))
        index.append(m)
        print(f"{folder.name:14s} {time.time() - t0:5.1f}s  nodes={m.get('n_nodes')} edges={m.get('n_edges')} "
              f"mapped={m.get('n_mapped')} page={m.get('fig_page')} {m['problems']}", flush=True)
    write_index(index)


def index_row(m: dict) -> dict:
    """The list page's row. 'good' (shown by default): a math/stat/CS paper whose diagram has >= 3
    boxes and >= 2 arrows, >= 70% of them resolved (to our node, a section or a cited result) and
    >= half to our nodes or sections."""
    res = sum(n["status"] in ("mapped", "section", "cited") for n in m.get("nodes", []))
    n = m.get("n_nodes") or 0
    return ({k: m.get(k) for k in ("id", "arxiv", "title", "n_nodes", "n_edges", "n_mapped", "problems")}
            | {"category": m["survey"]["primary_category"], "granularity": m["survey"]["granularity"],
               "year": m["survey"]["year"], "pilot": m.get("pilot", False), "n_resolved": res,
               "good": bool(m.get("gold_page")) and n >= 3 and (m.get("n_edges") or 0) >= 2 and res >= 0.7 * n
                       and sum(x["status"] in ("mapped", "section") for x in m.get("nodes", [])) >= 0.5 * n
                       and m["survey"]["primary_category"].split(".")[0] in ("math", "stat", "cs")})


def write_index(metas: list, replace: bool = False) -> None:
    f = ROOT / "index.json"
    old = {} if replace or not f.is_file() else {r["id"]: r for r in json.loads(f.read_text())}
    old.update({m["id"]: index_row(m) for m in metas})
    f.write_text(json.dumps(sorted(old.values(), key=lambda r: (r.get("category") or "", r["id"])), indent=1))


if __name__ == "__main__":
    main()
