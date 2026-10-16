#!/usr/bin/env python3
"""Convert a Lean blueprint (LaTeX with \\uses) into a graph in our format.

Input: the blueprint's .tex files concatenated (all.tex, '%%FILE <path>' separators).
Output (our unified JSON): one node per labelled statement environment (definition, lemma,
theorem, ...), one proof node per proof; edges from \\uses:
  \\uses{A} in the statement of B  ->  A --uses--> B
  \\uses{A} in the proof of B      ->  A --uses--> proof(B),  proof(B) --proves--> B
Results named in the text (\\ref, \\cref, ...) but not in \\uses are added as edges of kind "ref"; \\uses
edges are of kind "uses" (the gold for scoring is either kind, or both).
Lean markers become tags: lean (has \\lean{...}), leanok, mathlibok, notready.
Chapters/sections become the node's section (the viewer's section boxes).

Usage: blueprint_to_graph.py <all.tex> <out.json> [--title T] [--id ID]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import latex_macros                                      # noqa: E402
from latex_macros import strip_comments                  # noqa: E402

ENVS = {"definition": "definition", "lemma": "lemma", "theorem": "theorem", "proposition": "proposition",
        "corollary": "corollary", "conjecture": "conjecture", "remark": "remark", "example": "example",
        "claim": "claim", "axiom": "assumption", "assumption": "assumption", "hypothesis": "assumption",
        "question": "open_problem", "problem": "problem", "notation": "definition", "fact": "proposition",
        # usual abbreviations (often declared in a macros file the blueprint does not ship)
        "thm": "theorem", "lem": "lemma", "prop": "proposition", "cor": "corollary", "defn": "definition",
        "dfn": "definition", "rem": "remark", "rmk": "remark", "conj": "conjecture", "clm": "claim",
        "ex": "example", "eg": "example", "obs": "remark", "observation": "remark"}
_NAMED = [("theorem", "theorem"), ("lemma", "lemma"), ("proposition", "proposition"), ("corollary", "corollary"),
          ("definition", "definition"), ("conjecture", "conjecture"), ("remark", "remark"), ("example", "example"),
          ("claim", "claim"), ("notation", "definition"), ("axiom", "assumption"), ("assumption", "assumption")]


def declared_envs(tex: str) -> dict:
    """\\newtheorem{env}{Printed name}: environments the blueprint declares, by their printed name."""
    out = {}
    for m in re.finditer(r"\\newtheorem\*?\s*\{([^}]+)\}\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", tex):
        name = m.group(2).lower()
        for word, typ in _NAMED:
            if word in name:
                out[m.group(1).strip()] = typ
                break
    return out
PREFIX = {"definition": "D", "lemma": "L", "theorem": "T", "proposition": "P", "corollary": "C",   # as the parser
          "conjecture": "Cj", "remark": "Rm", "example": "Ex", "claim": "Cl", "assumption": "As",
          "open_problem": "OP", "problem": "Q"}
def begin_re(envs: dict):
    return re.compile(r"\\begin\s*\{(" + "|".join(sorted(map(re.escape, envs), key=len, reverse=True)) + r"|proof)\*?\}")
HEAD = re.compile(r"\\(chapter|section)\*?\{((?:[^{}]|\{[^{}]*\})*)\}")


def find_end(t: str, env: str, i: int) -> int:
    """Index of the matching \\end{env} (nested same-name environments allowed)."""
    depth, pat = 1, re.compile(r"\\(begin|end)\s*\{" + env + r"\*?\}")
    for m in pat.finditer(t, i):
        depth += 1 if m.group(1) == "begin" else -1
        if depth == 0:
            return m.start()
    return -1                                            # unterminated


def cmd_args(body: str, name: str) -> list:
    out = []
    for m in re.finditer(r"\\" + name + r"\{((?:[^{}]|\{[^{}]*\})*)\}", body):
        out += [x.strip() for x in m.group(1).split(",") if x.strip()]
    return out


def clean(body: str) -> str:
    body = re.sub(r"\\(uses|lean|label|proves)\{(?:[^{}]|\{[^{}]*\})*\}", "", body)
    body = re.sub(r"\\(leanok|mathlibok|notready|discussion\{[^}]*\})", "", body)
    return re.sub(r"\s+", " ", body).strip()


def compiled(tex: str) -> str:
    """The blueprint as LaTeX compiles it: from each blueprint root (content.tex, else web.tex / print.tex) through
    \\input and \\include, paths taken from the root's folder as LaTeX does (and from the including file's
    folder), with the project's path macros (\\newcommand{\\MyPath}{..}) expanded. Files the root never
    includes (templates, old chapters) are left out. Without a root, or when an \\input (other than a macro
    file) cannot be found while unreached files hold statements, all files are kept."""
    files = dict(re.findall(r"(?m)^%%FILE (\S+)\n(.*?)(?=^%%FILE |\Z)", tex, re.S))
    # one root per blueprint folder (a repository may hold several blueprints)
    roots = {p.rsplit("/", 1)[0]: p for name in ("print.tex", "web.tex", "content.tex") for p in files if p.endswith("src/" + name)}
    if not roots:
        return tex
    pmac = {m[0] or m[2]: m[1] or m[3] for m in re.findall(
        r"\\(?:re)?newcommand\*?\s*\{?\\(\w+)\}?\s*\{([^{}\\]*)\}|\\def\\(\w+)\{([^{}\\]*)\}", tex)}   # path macros
    norm = lambda path: re.sub(r"(^|/)\./", r"\1", re.sub(r"[^/]+/\.\./", "", path))
    seen, missing = set(), []
    def inline(path, base, depth=0):
        seen.add(path)
        here = path.rsplit("/", 1)[0]
        def sub(m):
            name = re.sub(r"\\(\w+)", lambda x: pmac.get(x.group(1), x.group(0)), m.group(1).strip())
            p = next((norm(c) for d in (base, here) for c in (f"{d}/{name}", f"{d}/{name}.tex") if norm(c) in files), None)
            if not p:
                missing.append(name)
            return inline(p, base, depth + 1) if p and depth < 10 else ""
        return re.sub(r"\\(?:input|include|subfile)\s*\{([^}]*)\}", sub, strip_comments(files[path]))
    out = "\n".join(inline(r, d) for d, r in sorted(roots.items()))
    missing = [n for n in missing if not re.search(r"macro|preamble|common|header|homeurl|print|web", n, re.I)]
    lost = [p for p in files if p not in seen and re.search(r"\\begin\s*\{(?:theorem|lemma|definition|proposition|corollary)", files[p])]
    return tex if missing and lost else out


def convert(tex: str, pid: str, title: str, macro_tex: str = "") -> dict:
    t = strip_comments(compiled(tex))
    envs = dict(ENVS, **declared_envs(t))
    BEGIN = begin_re(envs)
    # the blueprint's own macros: its macro files (blueprint/src/macros/*.tex) and any in the text
    macros = latex_macros.renderable(latex_macros.read_definitions(strip_comments(macro_tex) + "\n" + t, clean=False))
    expand = lambda x: latex_macros.expand_macros(x, macros) if macros else x
    heads = [(m.start(), m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()) for m in HEAD.finditer(t)]
    nodes, edges, by_label, counts = [], [], {}, {}
    pending_proof_of = None
    chap = sec = 0
    head_i = 0
    section = ""
    pos = 0
    items = []
    for m in BEGIN.finditer(t):
        if m.start() < pos:                                  # inside a previous environment
            continue
        env = m.group(1)
        end = find_end(t, env, m.end())
        if end < 0:                                      # unterminated: skip it, not the rest of the file
            continue
        body = t[m.end():end]
        if env == "proof":                               # statements nested in a proof (claims) are read too;
            body = re.sub(r"\\begin\s*\{(" + "|".join(map(re.escape, envs)) + r"|proof)\*?\}.*?\\end\s*\{\1\*?\}", " ", body, flags=re.S)
            pos = m.end()                                # their \uses are not the proof's own
        else:
            pos = end
        items.append((m.start(), env, body))
    for start, env, body in items:
        while head_i < len(heads) and heads[head_i][0] < start:
            _, kind, name = heads[head_i]
            if kind == "chapter":
                chap, sec = chap + 1, 0
                section = f"{chap} {name}"
            else:
                sec += 1
                section = f"{chap}.{sec} {name}" if chap else f"{sec} {name}"
            head_i += 1
        opt = re.match(r"\s*\[((?:[^\[\]]|\[[^\]]*\])*)\]", body)
        name = opt.group(1).strip() if opt else None
        if opt:
            body = body[opt.end():]
        uses = cmd_args(body, "uses")
        cited = [r for r in cmd_args(body, r"(?:[cC]|auto|eq)?ref") if r not in uses]   # named in the text only
        tags = [k for k in ("leanok", "mathlibok", "notready") if "\\" + k in body]
        if cmd_args(body, "lean"):
            tags.append("lean")
        if env == "proof":
            proves = cmd_args(body, "proves")
            owner = by_label.get(proves[0], pending_proof_of) if proves else pending_proof_of
            if not owner:
                continue
            pid_ = "PR_" + owner
            if any(n["id"] == pid_ for n in nodes):
                pid_ += f"_{len(nodes)}"
            nodes.append({"id": pid_, "type": "proof", "name": None, "statement": expand(clean(body))[:4000],
                          "origin": "paper", "tags": tags, "section": section, "label": None, "proves": [owner]})
            edges.append({"source": pid_, "target": owner, "type": "proves", "confidence": 1.0})
            edges += [{"source": u, "target": pid_, "type": "uses", "confidence": 1.0, "_label": True, "kind": k}
                      for k, us in (("uses", uses), ("ref", cited)) for u in us]
            continue                                     # a further proof belongs to the same statement
        typ = envs[env]
        labels = cmd_args(body, "label")
        counts[typ] = counts.get(typ, 0) + 1
        nid = f"{PREFIX.get(typ, 'N')}{counts[typ]}"
        nodes.append({"id": nid, "type": typ, "name": name, "statement": expand(clean(body))[:4000], "origin": "paper",
                      "tags": tags, "section": section, "label": labels[0] if labels else None,
                      "lean_names": cmd_args(body, "lean")})
        for lab in labels:
            by_label.setdefault(lab, nid)
        edges += [{"source": u, "target": nid, "type": "uses", "confidence": 1.0, "_label": True, "kind": k}
                  for k, us in (("uses", uses), ("ref", cited)) for u in us]
        pending_proof_of = nid                           # a proof that follows belongs to this statement
    # resolve \uses labels to node ids; unresolved targets are counted, not drawn
    out_edges, unresolved = [], []
    for e in edges:
        if e.pop("_label", False):
            if e["source"] not in by_label:
                if e["kind"] == "uses":                  # a \\ref to a section or an outside result: not a dependency
                    unresolved.append(e["source"])
                continue
            e["source"] = by_label[e["source"]]
        if e["source"] != e["target"]:
            out_edges.append(e)
    seen, dedup = set(), []
    for e in out_edges:
        k = (e["source"], e["target"], e["type"])
        if k not in seen:
            seen.add(k)
            dedup.append(e)
    return {"metadata": {"paper_id": pid, "title": title, "extractor": "Lean blueprint (\\uses), converted",
                         "labels": {lab: {"node": n, "kind": "env"} for lab, n in by_label.items()},
                         "unresolved_uses": sorted(set(unresolved))},
            "nodes": nodes, "edges": dedup}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tex")
    ap.add_argument("out")
    ap.add_argument("--title", default="")
    ap.add_argument("--id", default="")
    a = ap.parse_args()
    g = convert(Path(a.tex).read_text(encoding="utf-8", errors="replace"), a.id or Path(a.tex).parent.name, a.title)
    Path(a.out).write_text(json.dumps(g, indent=1))
    n_st = sum(n["type"] != "proof" for n in g["nodes"])
    print(f"{a.id}: {n_st} statements, {len(g['nodes']) - n_st} proofs, {len(g['edges'])} edges, "
          f"{len(g['metadata']['unresolved_uses'])} unresolved \\uses targets")


if __name__ == "__main__":
    main()
