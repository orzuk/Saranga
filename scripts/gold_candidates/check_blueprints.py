#!/usr/bin/env python3
"""Automatic checks of the Lean-blueprint gold set (provenance human / mixed).

1. depgraph: our graph.json vs the authors' published dependency graph (leanblueprint's
   dep_graph_document.html), at the LaTeX-label level. Differences are classified against all.tex:
   an edge only in theirs whose \\uses is not in all.tex, or only in ours whose \\uses is, is a version
   difference (their site was built from another commit); an edge only in ours that is implied by a
   path in theirs was dropped by their transitive reduction (plastexdepgraph runs `tred` by default);
   the rest are converter suspects.
2. refs: \\ref/\\cref/\\Cref/\\autoref targets (statement labels) vs \\uses, per statement and proof.
3. stats: per provenance group.

Writes <out>_depgraph.csv (per blueprint), <out>_depgraph_diff.csv (each differing edge, classified),
<out>_refs.csv, <out>_refs_missing.csv (each \\ref'd result missing from \\uses), <out>_stats.csv; prints a summary. Dep graphs are cached under /tmp/claude-1000/bp_depgraphs/ (1 request/s).

Usage: check_blueprints.py [--out PREFIX]
"""
import argparse
import csv
import json
import re
import statistics
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blueprint_to_graph as b2g                         # noqa: E402

REPO = Path(__file__).resolve().parents[2]
GOLD = REPO / "corpus" / "gold_blueprints"
CACHE = Path("/tmp/claude-1000/bp_depgraphs")
OUT = "/mnt/g/My Drive/Research/Automath/blueprint_checks_2026-10-15"
OUTLIERS = {"mathlib-initiative__Etingof-RepresentationTheory-draft1"}    # every item \\uses all earlier ones (170k edges)
DEP_TYPES = {"definition", "lemma", "proposition", "theorem", "corollary"}    # plastexdepgraph's default thms
ID = r'"(?:[^"\\]|\\.)*"|[\w.]+'
STMT = re.compile(rf'({ID})\s*(?:->\s*({ID})\s*)?(\[(?:[^\]"]|"(?:[^"\\]|\\.)*")*\])?\s*;')
INNER = re.compile(r"\\begin\s*\{(proof|equation|align|gather|multline|eqnarray|split|aligned|enumerate|itemize|description|cases|array|[pbvBV]?matrix|tikzcd|tikzpicture|center|figure|quote)\b")
REF = re.compile(r"\\(?:[cC]ref|ref|autoref|cpageref|nameref)\*?\{([^}]*)\}")
_last = [0.0]


def fetch(url: str, slug: str):
    f = CACHE / f"{slug}.html"
    if not f.exists():
        time.sleep(max(0.0, 1 - (time.time() - _last[0])))
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "saranga-gold-check"})
            f.write_bytes(urllib.request.urlopen(req, timeout=30).read())
        except Exception as e:                           # noqa: BLE001
            print(f"  {slug}: {e!r}", file=sys.stderr)
            f.write_text("")
    return f.read_text(encoding="utf-8", errors="replace") or None


def parse_dot(html: str):
    """Nodes and edges (with style) of the DOT graph inside the page; None if there is none."""
    if j := re.search(r'"__main__": ("(?:[^"\\]|\\.)*")', html):     # a customised template: DOTS = {name: dot}
        html = json.loads(j.group(1)) + "`"
    m = re.search(r"digraph[^{]*\{(.*?)\}\s*[`']", html, re.S)          # renderDot(`...`) or, older, ('...')
    if not m:
        return None
    unq = lambda s: s[1:-1].replace('\\"', '"') if s.startswith('"') else s
    nodes, edges = set(), {}
    for s in STMT.finditer(m.group(1)):
        a, b, attrs = unq(s.group(1)), s.group(2) and unq(s.group(2)), s.group(3) or ""
        if b:
            nodes |= {a, b}
            edges[a, b] = "dashed" if "dashed" in attrs else "solid"
        elif a not in ("graph", "node", "edge"):
            nodes.add(a)
    return nodes, edges


def units(tex: str):
    """The blueprint's statements and proofs as the converter reads them:
    dicts kind, type, labels, uses, refs, words, owner (label of the statement a proof proves)."""
    t = b2g.strip_comments(tex)
    envs = dict(b2g.ENVS, **b2g.declared_envs(t))
    pos, out, last = 0, [], None
    for m in b2g.begin_re(envs).finditer(t):
        if m.start() < pos or (end := b2g.find_end(t, m.group(1), m.end())) < 0:
            continue
        env, body = m.group(1), t[m.end():end]
        if env == "proof":
            body = re.sub(r"\\begin\s*\{(" + "|".join(map(re.escape, envs)) + r")\*?\}.*?\\end\s*\{\1\*?\}", " ", body, flags=re.S)
            pv = b2g.cmd_args(body, "proves")
            owner, last = (pv[0] if pv else last), None
        else:
            owner = None
        pos = m.end() if env == "proof" else end
        labels = b2g.cmd_args(body, "label")
        u = {"kind": "proof" if env == "proof" else "statement", "type": envs.get(env, "proof"), "labels": labels,
             "uses": b2g.cmd_args(body, "uses"), "owner": owner, "last_uses": last_uses(body), "words": len(b2g.clean(body).split()),
             "refs": [x.strip() for g in REF.findall(body) for x in g.split(",") if x.strip()]}
        if env != "proof":
            last = labels[0] if labels else None
        out.append(u)
    return out


def last_uses(body: str) -> set:
    """The \\uses plasTeX keeps: each \\uses overwrites the environment's list, so only the last one counts."""
    ms = list(re.finditer(r"\\uses\{((?:[^{}]|\{[^{}]*\})*)\}", body))
    return {x.strip() for x in ms[-1].group(1).split(",") if x.strip()} if ms else set()


def uses_in_tex(t: str, a: str, b: str) -> str:
    """Independent of the converter: is `a` in a \\uses of the environment carrying \\label{b} or of the
    text up to the next environment other than a proof or a math/list one (its proof), or of a proof with \\proves{b}?"""
    spans = []
    for m in re.finditer(r"\\label\s*\{" + re.escape(b) + r"\}", t):
        s = max(t.rfind("\\begin", 0, m.start()), 0)
        while s > 0 and INNER.match(t, s):
            s = max(t.rfind("\\begin", 0, s), 0)
        nxt = next((x for x in re.finditer(r"\\begin\s*\{", t[m.end():]) if not INNER.match(t[m.end():], x.start())), None)
        spans.append(t[s:m.end() + nxt.start() if nxt else len(t)])
    spans += [t[m.start():t.find("\\end{proof}", m.start())] for m in re.finditer(r"\\proves\s*\{" + re.escape(b) + r"\}", t)]
    envs = [e for sp in spans for e in re.split(r"\\begin\s*\{proof", sp)]
    return "kept" if any(a in last_uses(e) for e in envs) else "earlier" if any(a in b2g.cmd_args(e, "uses") for e in envs) else ""


def dead_labels(tex: str) -> set:
    """Labels defined only in files that content.tex never \\input's (all.tex concatenates every .tex file
    of the repo, including demo/template files and chapters commented out of content.tex)."""
    parts = re.split(r"^%%FILE (.*)$", tex, flags=re.M)
    files = dict(zip(parts[1::2], map(b2g.strip_comments, parts[2::2])))
    todo, live = [f for f in files if f.rsplit("/", 1)[-1] == "content.tex"], set()
    if not todo:
        return set()
    while todo:
        if (f := todo.pop()) in live:
            continue
        live.add(f)
        for x in re.findall(r"\\(?:input|include|subfile)\s*\{([^}]+)\}", files[f]):
            x = re.sub(r"^(\.\.?/|\\\w+/)+", "", x.strip()).removesuffix(".tex") + ".tex"     # drop ../ and \\MyPath/
            todo += [g for g in files if g == x or g.endswith("/" + x)]
    lab = lambda fs: {x for f in fs for x in re.findall(r"\\label\s*\{([^}]+)\}", files[f])}
    return lab(set(files) - live) - lab(live)


def ours(g: dict, theirs=()):
    """Our graph at the label level: labelled statement nodes, (used, user) -> dashed|solid. A node with several
    \\label's is named by the one their graph uses (plasTeX names it by the last)."""
    labels = defaultdict(list)
    for lb, v in g["metadata"]["labels"].items():
        labels[v["node"]].append(lb)
    lab = {n["id"]: next((x for x in labels[n["id"]] if x in theirs), n["label"]) for n in g["nodes"] if n["type"] != "proof"}
    typ = {lab[n["id"]]: n["type"] for n in g["nodes"] if n["type"] != "proof" and n["label"]}
    owner = {n["id"]: n["proves"][0] for n in g["nodes"] if n["type"] == "proof"}
    edges, unlab = {}, 0
    for e in g["edges"]:
        if e["type"] != "uses":
            continue
        a, b = lab.get(e["source"]), lab.get(owner.get(e["target"], e["target"]))
        if not (a and b):
            unlab += 1
        elif (a, b) not in edges or e["target"] in owner:
            edges[a, b] = "solid" if e["target"] in owner else edges.get((a, b), "dashed")
    return typ, edges, unlab


def reach(edges, a, b) -> bool:
    """A path a -> ... -> b of length >= 2 in `edges`."""
    succ = defaultdict(set)
    for x, y in edges:
        succ[x].add(y)
    seen, todo = set(), [y for y in succ[a] if y != b]
    while todo:
        x = todo.pop()
        if x == b:
            return True
        if x not in seen:
            seen.add(x)
            todo += succ[x]
    return False


def md(rows, cols):
    return "\n".join(["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
                     + ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows])


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    metas = [m for f in sorted(GOLD.glob("*/meta.json")) if (m := json.loads(f.read_text()))["provenance"] in ("human", "mixed")]
    dg_rows, diff_rows, ref_rows, missing, stat = [], [], [], [], defaultdict(lambda: defaultdict(list))
    for m in metas:
        d, slug = GOLD / m["id"], m["id"]
        tex, g = (d / "all.tex").read_text(encoding="utf-8", errors="replace"), json.loads((d / "graph.json").read_text())
        t, us = b2g.strip_comments(tex), units(tex)
        dot = parse_dot(fetch(m["links"]["dep_graph"], slug) or "") if m["links"].get("dep_graph") else None
        typ, oe, unlab = ours(g, dot[0] if dot else ())
        dead = dead_labels(tex) & set(typ)
        # ---- 3. stats
        st = [n for n in g["nodes"] if n["type"] != "proof"]
        pr_of = {n["id"]: n["proves"][0] for n in g["nodes"] if n["type"] == "proof"}
        row = {"blueprints": 1, "statements": len(st), "proofs": len(g["nodes"]) - len(st),
               "edges": sum(e["type"] == "uses" for e in g["edges"]),
               "with_uses": len({pr_of.get(e["target"], e["target"]) for e in g["edges"] if e["type"] == "uses"}),
               "dead": len(dead), "dead_edges": sum(bool({x, y} & dead) for x, y in oe), "arxiv": bool(m.get("arxiv")),
               "arxiv_readme": bool(m.get("arxiv") or m.get("arxiv_readme")), "pdf": bool(m["links"].get("pdf")),
               "dep_link": bool(m["links"].get("dep_graph")), "dep_ok": bool(dot),
               "plastex_drops": sum(len(set(u["uses"]) - u["last_uses"]) for u in us)}
        for k in [m["provenance"]] + (["mixed excl. outlier"] if m["provenance"] == "mixed" and slug not in OUTLIERS else []):
            for c, v in row.items():
                stat[k][c].append(v)
            stat[k]["proof_words"] += [u["words"] for u in us if u["kind"] == "proof"]
        # ---- 2. refs vs uses (labels canonicalised to a statement's first \\label)
        canon = {lab: u["labels"][0] for u in us if u["kind"] == "statement" for lab in u["labels"]}
        utype = {u["labels"][0]: u["type"] for u in us if u["kind"] == "statement" and u["labels"]}
        node_uses = defaultdict(set)
        for u in us:
            u["me"] = canon.get(u["owner"]) if u["kind"] == "proof" else (u["labels"][0] if u["labels"] else None)
            u["uses"], u["refs"] = {canon.get(x, x) for x in u["uses"]}, {canon[x] for x in u["refs"] if x in canon} - {u["me"]}
            node_uses[u["me"]] |= u["uses"]
        r = Counter()
        for u in us:
            miss, silent = u["refs"] - node_uses[u["me"]], u["uses"] - u["refs"]
            r["units"] += 1
            r["units_with_refs"] += bool(u["refs"])
            r["refs"] += len(u["refs"])
            r["ref_not_in_unit_uses"] += len(u["refs"] - u["uses"])
            r["ref_not_in_node_uses"] += len(miss)
            r["uses"] += len(u["uses"])
            r["uses_not_refd"] += len(silent)
            r["uses_not_refd_def"] += sum(utype.get(x) == "definition" for x in silent)
            missing += [{"id": slug, "unit": u["kind"], "of": u["me"], "ref": x, "ref_type": utype[x]} for x in sorted(miss)]
        ref_rows.append({"id": slug, "provenance": m["provenance"], **r})
        # ---- 1. depgraph
        if not dot:
            continue
        tn, te = dot
        on = set(typ)
        cls = Counter()
        for (x, y), sty in sorted(te.items()):
            if (x, y) in oe:
                continue
            c = ("their node absent from ours" if not (x in on and y in on) else
                 "converter suspect (\\uses in all.tex)" if uses_in_tex(t, x, y) else "version (\\uses not in all.tex)")
            cls["theirs:" + c] += 1
            diff_rows.append({"id": slug, "side": "theirs", "source": x, "target": y, "style": sty, "class": c})
        for (x, y), sty in sorted(oe.items()):
            if (x, y) in te:
                continue
            c = ("node in a file not \\input by content.tex" if {x, y} & dead else
                 "node type outside their thms" if not ({typ[x], typ[y]} <= DEP_TYPES) else
                 "node absent from theirs" if not (x in tn and y in tn) else
                 "transitive reduction" if reach(te, x, y) else
                 {"kept": "version (\\uses in all.tex)", "earlier": "plasTeX keeps only the last \\uses of an environment"}.get(
                     uses_in_tex(t, x, y), "converter suspect (\\uses not in all.tex)"))
            cls["ours:" + c] += 1
            diff_rows.append({"id": slug, "side": "ours", "source": x, "target": y, "style": sty, "class": c})
        auto = {x for x in tn if re.fullmatch(r"a\d{7,}", x)}
        dg_rows.append({"id": slug, "provenance": m["provenance"], "their_nodes": len(tn), "their_unlabelled": len(auto),
                        "their_edges": len(te), "their_dashed": sum(v == "dashed" for v in te.values()),
                        "our_nodes": len(on), "our_nodes_in_thms": sum(v in DEP_TYPES for v in typ.values()),
                        "our_edges": len(oe), "our_unlabelled_edges": unlab, "both": len(set(te) & set(oe)),
                        "both_same_style": sum(te[k] == oe[k] for k in set(te) & set(oe)),
                        "their_redundant_edges": sum(reach(te, x, y) for x, y in te),     # > 0: not transitively reduced
                        "only_theirs": len(set(te) - set(oe)), "only_ours": len(set(oe) - set(te)),
                        "nodes_both": len(tn & on), "nodes_only_theirs": len(tn - on - auto),
                        "nodes_only_theirs_label_in_tex": len([x for x in tn - on - auto if re.search(r"\\label\s*\{" + re.escape(x) + r"\}", t)]),
                        "nodes_only_ours_thms": len({x for x in on - tn if typ[x] in DEP_TYPES}),
                        "nodes_only_ours_uninput": len((on - tn) & dead),
                        **{k: cls[k] for k in ("theirs:converter suspect (\\uses in all.tex)", "ours:converter suspect (\\uses not in all.tex)")}})
    pre = a.out
    write_csv(pre + "_depgraph.csv", dg_rows)
    write_csv(pre + "_depgraph_diff.csv", diff_rows)
    write_csv(pre + "_refs.csv", ref_rows)
    write_csv(pre + "_refs_missing.csv", missing)
    srows = [{"group": k, "blueprints": len(v["blueprints"]), "statements": sum(v["statements"]), "proofs": sum(v["proofs"]),
              "uses_edges": sum(v["edges"]), "stmts_with_uses": f"{sum(v['with_uses']) / sum(v['statements']):.0%}",
              "stmts_in_uninput_files": sum(v["dead"]),
              "edges_touching_them": sum(v["dead_edges"]), "median_words_per_proof": statistics.median(v["proof_words"]), "arxiv": sum(v["arxiv"]),
              "arxiv_or_readme": sum(v["arxiv_readme"]), "pdf_link": sum(v["pdf"]),
              "dep_graph_link": sum(v["dep_link"]), "dep_graph_reachable": sum(v["dep_ok"]),
              "uses_lost_to_plastex_last_wins": sum(v["plastex_drops"])} for k, v in sorted(stat.items())]
    write_csv(pre + "_stats.csv", srows)
    # ---- print
    print("## stats\n" + md(srows, list(srows[0])))
    tot = {k: sum(r[k] for r in dg_rows) for k in dg_rows[0] if k not in ("id", "provenance")}
    print(f"\n## depgraph ({len(dg_rows)} blueprints)\n", json.dumps(tot, indent=0))
    print(Counter((r["side"], r["class"]) for r in diff_rows))
    for grp in ("human", "mixed"):
        print(f"\n## refs {grp} excl. outlier\n", json.dumps({k: sum(r[k] for r in ref_rows if r["provenance"] == grp and r["id"] not in OUTLIERS)
                                                             for k in ref_rows[0] if k not in ("id", "provenance")}))
    print(len(missing), Counter(x["ref_type"] for x in missing))


if __name__ == "__main__":
    main()
