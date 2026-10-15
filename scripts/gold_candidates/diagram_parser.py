#!/usr/bin/env python3
"""Parse an author-drawn dependency diagram (TikZ, tikzcd, xymatrix, picture) into a graph.

Nodes are the drawing's boxes with their text and the \\ref labels inside them (resolved
to what each label is attached to); edges are its arrows. Used by build_gold_review.py.
Taken from the survey's fetch_eprints.py (stage 7), with the e-print download left out.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
from latex_macros import strip_comments  # noqa: E402,F401  (dp.strip_comments)


REF_CMDS = r"(?:ref|cref|Cref|eqref|autoref|Autoref|nameref|vref|Vref|thmref|labelcref)"


def brace_arg(t, i):
    n = len(t)
    while i < n and t[i] in " \t\n":
        i += 1
    if i >= n or t[i] != "{":
        return None, i
    depth = 0; j = i
    while j < min(n, i + 50000):
        c = t[j]
        if c == "\\":
            j += 2; continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return t[i + 1:j], j + 1
        j += 1
    return None, i


def label_map(alltex):
    """label -> (env/section kind, short title text)"""
    out = {}
    last = "?"
    for m in re.finditer(r"\\begin\s*\{([A-Za-z*]+)\}(\[[^\]]{0,200}\])?|\\((?:sub)*section|chapter)\*?\s*(?:\[[^\]]*\])?\s*\{([^}]{0,200})\}|\\label\s*\{([^}]*)\}", alltex):
        if m.group(1):
            last = m.group(1) + ((" " + m.group(2)) if m.group(2) else "")
        elif m.group(3):
            last = m.group(3) + " " + m.group(4)
        elif m.group(5):
            out[m.group(5).strip()] = last
    return out


def resolve_refs(text, lmap, macros):
    labs = re.findall(r"\\" + REF_CMDS + r"\*?\s*\{([^}]*)\}", text)
    for mac in macros:
        labs += re.findall(r"\\" + mac + r"\*?\s*\{([^}]*)\}", text)
    res = []
    for l in labs:
        for l1 in l.split(","):
            l1 = l1.strip()
            res.append({"label": l1, "target": lmap.get(l1, "unknown")})
    return res


def ref_macros(t):
    ms = set()
    for m in re.finditer(r"\\(?:re)?newcommand\*?\s*\{?\s*\\([A-Za-z]+)\s*\}?\s*(?:\[\d\])?(?:\[[^\]]*\])?\s*\{", t):
        body, _ = brace_arg(t, m.end() - 1)
        if body and re.search(r"\\" + REF_CMDS + r"\b", body):
            ms.add(m.group(1))
    return ms


# ---------------- TikZ / xy parsing into a graph
def _num_xy(c):
    m = re.match(r"\s*\(?\s*([-+]?\d*\.?\d+)\s*(?:cm|pt|mm|bp|em|ex|in)?\s*,\s*([-+]?\d*\.?\d+)\s*(cm|pt|mm|bp|em|ex|in)?\s*\)?\s*$", c or "")
    return (float(m.group(1)), float(m.group(2))) if m else None


def _split_statements(code):
    out = []; depth = 0; cur = []
    i = 0
    while i < len(code):
        ch = code[i]
        if ch == "\\" and i + 1 < len(code):
            cur.append(code[i:i + 2]); i += 2; continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch == ";" and depth <= 0:
            out.append("".join(cur)); cur = []; depth = 0
        else:
            cur.append(ch)
        i += 1
    if cur:
        out.append("".join(cur))
    return out


OPT = r"\[(?:[^\[\]]|\[[^\[\]]*\])*\]"                 # [options], one level of nested [..] allowed
NODE_RE = re.compile(r"\bnode\b((?:\s*(?:" + OPT + r"|\([^)]*\)|at\s*\([^)]*\)))*)\s*\{")
COORD_RE = re.compile(r"\(\s*([^()]*?(?:\([^()]*\)[^()]*?)*)\s*\)")


def _anchorless(c):
    return re.sub(r"\.(?:north|south|east|west|center|north east|north west|south east|south west|base|mid|\d+)\s*$", "", c.strip()).strip()


def _on_segment(p, a, b, eps=1e-3):
    """p strictly inside the segment a-b."""
    (px, py), (ax, ay), (bx, by) = p, a, b
    cross, dot, ll = (bx - ax) * (py - ay) - (by - ay) * (px - ax), (px - ax) * (bx - ax) + (py - ay) * (by - ay), (bx - ax) ** 2 + (by - ay) ** 2
    return ll > eps and abs(cross) <= eps * ll ** 0.5 and eps < dot < ll - eps


def _wire_edges(pending, nodes, resolve, lmap, macros):
    """Segments -> edges between nodes. Arrows may start or end at junctions (bare coordinates, midpoints
    $(B)!0.5!(C)$, points on other lines); the plain lines meeting there are wires, so an arrow out of a
    junction gets one edge per node wired into it (2 -> 1 merges) and arrows out of a junction that a node
    feeds give one edge each (1 -> 2 splits)."""
    xy = lambda p: nodes[p]["_xy"] if p in nodes else p[1] if p[0] == "j" else None
    mids = {}                                            # junction -> the two nodes it is the midpoint of
    def key(pt):                                         # node name, or a junction ("j", xy) / ("m", a, b)
        if not isinstance(pt, str) and pt[0] == "mid":
            pa, pb = nodes[pt[1]]["_xy"], nodes[pt[2]]["_xy"]
            j = ("j", (round((pa[0] + pb[0]) / 2, 3), round((pa[1] + pb[1]) / 2, 3))) if pa and pb else ("m",) + pt[1:]
            mids[j] = pt[1:]
            return j
        r = resolve(pt)
        return r or (("j", (round(pt[1][0], 3), round(pt[1][1], 3))) if not isinstance(pt, str) and pt[0] == "xy" else None)
    segs, labs = [], {}
    for x, y, rev, arrow, lab in pending:
        a, b = key(x), key(y)
        if a is None or b is None or a == b:
            continue
        a, b = (b, a) if rev else (a, b)
        segs.append((a, b, bool(arrow)))
        if lab and isinstance(a, str) and isinstance(b, str):     # a label, or extra edge fields
            labs.setdefault((a, b), lab)
    par = {}
    def find(j):
        while par.setdefault(j, j) != j:
            j = par[j]
        return j
    union = lambda u, v: par.__setitem__(find(u), find(v))
    attach = [(j, n) for j, ab in mids.items() for n in ab]   # (junction, node) joined by a wire
    wired = {p for ab in mids.values() for p in (ab, ab[::-1])}   # node-node lines that are only wires
    junctions = {p for s in segs for p in s[:2] if not isinstance(p, str)}
    for a, b, arrow in segs:
        if arrow:
            continue
        if not isinstance(a, str) and not isinstance(b, str):
            union(a, b)
        elif isinstance(a, str) != isinstance(b, str):
            attach.append((a, b) if not isinstance(a, str) else (b, a))
        pa, pb = xy(a), xy(b)
        for j in junctions:                              # T-junctions: a junction lying on this line
            if pa and pb and j[0] == "j" and _on_segment(j[1], pa, pb):
                for e in (a, b):
                    attach.append((j, e)) if isinstance(e, str) else union(j, e)
                wired |= {(a, b), (b, a)}
    comp = {}
    for j, n in attach:
        comp.setdefault(find(j), {"und": set(), "in": set(), "out": set()})["und"].add(n)
    for a, b, arrow in segs:
        if arrow and isinstance(a, str) != isinstance(b, str):
            c = comp.setdefault(find(b if isinstance(a, str) else a), {"und": set(), "in": set(), "out": set()})
            c["in" if isinstance(a, str) else "out"].add(a if isinstance(a, str) else b)
    out = []
    for a, b, arrow in segs:                             # direct node-node lines and arrows
        if isinstance(a, str) and isinstance(b, str) and (arrow or (a, b) not in wired):
            out.append((a, b, arrow))
    for c in comp.values():
        if not c["in"] and not c["out"]:                 # plain lines only: a bent line joining two boxes
            if len(c["und"]) == 2:
                out.append((*sorted(c["und"]), False))
            continue
        src, dst = (c["in"] | c["und"], c["out"]) if c["out"] else (c["in"], c["und"])
        out += [(a, b, True) for a in sorted(src) for b in sorted(dst) if a != b]
    edges, seen = [], set()
    for a, b, arrow in out:
        if (a, b) not in seen:
            seen.add((a, b))
            e = {"from": a, "to": b, "directed": arrow}
            if isinstance(labs.get((a, b)), dict):
                e.update(labs[a, b])
            elif (a, b) in labs:
                e["label"] = labs[a, b][:200]; e["label_refs"] = resolve_refs(labs[a, b], lmap, macros)
            edges.append(e)
    return edges


_ARROW = r"->|<-|latex|stealth|Stealth|Latex|-to\b|Triangle|pil|arrow"


def arrow_styles(tex):
    """Names of the paper's TikZ styles that draw arrows: \\tikzstyle{line}=[draw,-latex], line/.style={->}."""
    defs = re.findall(r"\\tikzstyle\s*\{([^}]+)\}\s*=\s*\[([^\]]*)\]", tex) + \
        re.findall(r"([A-Za-z][\w ]*?)/\.style\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}", tex)
    return {n.strip() for n, d in defs if re.search(_ARROW, d)}


def parse_tikz(code, lmap, macros, styles=()):
    """Statement-level TikZ parser -> nodes (named / positioned) and directed edges.
    styles: names of the paper's arrow styles (arrow_styles)."""
    m = re.search(r"\\begin\{tikzpicture\}\s*(" + OPT + r")?", code)
    # arrows by default: set in the picture's options or an every path/edge style, not by one \draw[->]
    styles = ((m.group(1) or "") if m else "") + " ".join(re.findall(r"every (?:path|edge)/\.style\s*=\s*\{[^}]*\}", code))
    code = re.sub(r"\\begin\{tikzpicture\}\s*(" + OPT + r")?|\\end\{tikzpicture\}", "", code)
    # inline \matrix bodies that contain explicit \node statements
    for _ in range(5):
        m = re.search(r"\\matrix\b[^{;]*\{", code)
        if not m:
            break
        body, end = brace_arg(code, m.end() - 1)
        if body is None or "\\node" not in body:
            # keep matrix-of-nodes as is but stop scanning this one
            code = code[:m.start()] + "\\MATRIXDONE" + code[m.start() + 7:]
            continue
        flat = re.sub(r"\\\\(\[[^\]]*\])?", " ", body).replace("&", " ")
        code = code[:m.start()] + flat + ";" + code[end:]
    code = code.replace("\\MATRIXDONE", "\\matrix")
    graph_edges = []
    for m in re.finditer(r"\\graph\s*(\[[^\]]*\])?\s*\{", code):
        gbody, _ = brace_arg(code, m.end() - 1)
        for st in re.split(r";|\n\s*\n", gbody or ""):
            parts = re.split(r"(->|<-|--|<->)(?:\s*\[[^\]]*\])?", st)
            groups = []; ops = []
            for k, part in enumerate(parts):
                if k % 2 == 1:
                    ops.append(part); continue
                part = re.sub(r"\[[^\]]*\]", "", part).strip().strip("{}")
                names = [re.sub(r"[\"/].*$", "", x).strip() for x in part.split(",")]
                groups.append([x for x in names if x])
            for k, op in enumerate(ops):
                if k + 1 < len(groups):
                    for a_ in groups[k]:
                        for b_ in groups[k + 1]:
                            graph_edges.append((a_, b_, op))
    global_arrow = bool(re.search(r"(?:^|[\[,\s{])(?:->|-latex|-stealth|-Stealth|-Latex|-to|->>|-\{[^}]*\})(?:[\],\s}]|$)", styles))
    nodes = {}; anon = 0; edges = []
    def add_node(comps, txt, name_hint=None):
        nonlocal anon
        at = re.search(r"at\s*\(([^)]*)\)", comps)
        rest = re.sub(r"at\s*\([^)]*\)", "", comps)
        rest = re.sub(OPT, "", rest)
        nm = re.search(r"\(([^)]*)\)", rest)
        nopt = re.search(r"\bname\s*=\s*([^,\]]+)", comps)
        name = (nm.group(1).strip() if nm else "") or (nopt.group(1).strip() if nopt else "") or name_hint
        if not name:
            anon += 1; name = f"_anon{anon}"
        pos = _num_xy(at.group(1)) if at else None
        nodes[name] = {"id": name, "text": (txt or "").strip()[:300], "refs": resolve_refs(txt or "", lmap, macros),
                       "at": at.group(1) if at else None, "_xy": pos}
        return name
    stmts = _split_statements(code)
    pending = []  # (kind, statement)
    for st in stmts:
        s0 = re.sub(r"^(?:\s*\\(?:begin|end)\{scope\}\s*(?:" + OPT + r")?)+", "", st).strip()   # \end{scope} \draw ...
        # a stray character or an argument-less command before it: "= \path", "\footnotesize \node"
        s0 = re.sub(r"^(?:[^\\\s]{1,3}|\\[A-Za-z]+(?![\[{\w]))(?=\s*\\(?:draw|path|node|matrix)\b)\s*", "", s0).strip()
        if re.match(r"\\(?:node|matrix)\b", s0):
            if s0.startswith("\\matrix"):
                m = re.match(r"\\matrix\s*(\[[^\]]*\])?\s*\(([^)]*)\)\s*(\[[^\]]*\])?\s*(?:at\s*\([^)]*\))?\s*\{", s0)
                if m:
                    body, _ = brace_arg(s0, m.end() - 1)
                    mname = m.group(2).strip()
                    for i, row in enumerate(re.split(r"\\\\", body or ""), 1):
                        for j, cell in enumerate(row.split("&"), 1):
                            c = re.sub(r"^\s*\|[^|]*\|", "", cell).strip()
                            if c:
                                nodes[f"{mname}-{i}-{j}"] = {"id": f"{mname}-{i}-{j}", "text": c[:300], "refs": resolve_refs(c, lmap, macros), "at": None, "_xy": None}
                continue
            m = re.match(r"\\node\b((?:\s*(?:" + OPT + r"|\([^)]*\)|at\s*\([^)]*\)))*)\s*\{", s0)
            if not m:
                continue
            txt, end = brace_arg(s0, m.end() - 1)
            src = add_node(m.group(1), txt)
            tail = s0[end:]
            for e in re.finditer(r"\bedge\b\s*(\[[^\]]*\])?\s*(?:node\s*(?:\[[^\]]*\])?\s*\{([^}]*)\})?\s*\(([^)]*)\)", tail):
                opts = e.group(1) or ""
                tgt = re.sub(r"\.\w+(?: \w+)?$", "", e.group(3).strip())
                rev = "<-" in opts and "->" not in opts
                pending.append((src, tgt, rev, ("->" in opts or "<-" in opts or "pil" in opts or global_arrow or ">" in opts), e.group(2)))
            for e in re.finditer(r"(?:--|->)\s*\(([^)]*)\)", tail):
                pending.append((src, re.sub(r"\.\w+$", "", e.group(1).strip()), False, global_arrow, None))
            continue
        if re.match(r"\\(?:draw|path|graph|foreach)\b", s0):
            if s0.startswith("\\foreach"):
                continue
            # inline named nodes inside the path
            for m in NODE_RE.finditer(s0):
                comps = m.group(1)
                if re.search(r"\(([^)]*)\)", re.sub(r"at\s*\([^)]*\)", "", re.sub(r"\[[^\]]*\]", "", comps))):
                    txt, _ = brace_arg(s0, m.end() - 1)
                    add_node(comps, txt)
            opts = " ".join(re.findall(r"^\\\w+\s*(\[[^\]]*\])", s0))
            arrow = bool(re.search(_ARROW, opts)) or any(o.strip() in styles for o in re.split(r"[\[\],]", opts)) \
                or global_arrow and not re.search(r"[\[,]\s*-\s*[\],]", opts)
            rev = ("<-" in opts and "->" not in opts) or bool(re.search(r"\[\s*<-", opts))
            both = bool(re.search(r"<[-=]+>|\b(\w+)-\1\b", opts))     # <->, <=>, latex-latex: arrowheads at both ends
            body = re.sub(r"node\s*(\[[^\]]*\])?\s*(\([^)]*\))?\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", " ", s0)
            body = re.sub(r"\[[^\]]*\]", " ", body)
            toks = re.finditer(r"\bedge\b|--|-\||\|-|\bto\b|\band\b|\.\.(?:\s*controls)?|\(\s*([^()]*?(?:\([^()]*\)[^()]*?)*)\s*\)", body)
            cur = None; start = None; op = None; pairs = []; chain = []
            def flush():
                if len(chain) >= 2:
                    if not arrow or all(p[0] == "n" for p in chain):     # plain lines: every piece is a wire
                        pairs.extend(zip(chain, chain[1:]))
                    else:
                        pairs.append((chain[0], chain[-1]))
            for t in toks:
                tok = t.group(0)
                if tok == "edge":
                    op = "edge"; continue
                if tok == "and":
                    op = "line"; continue
                if tok in ("--", "to", "-|", "|-") or tok.startswith(".."):
                    op = op or "line"; continue
                c = (t.group(1) or "").strip()
                if c.startswith("$"):
                    m = re.match(r"\$\s*\(([^()]+)\)\s*!\s*[\d.]+\s*!\s*\(([^()]+)\)\s*\$$", c)   # $(B)!0.5!(C)$
                    a_, b_ = (_anchorless(x) for x in m.groups()) if m else (None, None)
                    if a_ in nodes and b_ in nodes:
                        pt = ("mid", a_, b_)
                    else:
                        inner = re.search(r"\(\s*([^()$]+?)\s*\)", c)
                        c = inner.group(1) if inner and not _num_xy(inner.group(1)) else ""
                        pt = None
                    if pt:
                        if op == "edge" and cur is not None:
                            pairs.append((cur, pt))
                        elif op == "line" and cur is not None:
                            chain.append(pt); cur = pt
                        else:
                            flush(); chain = [pt]; cur = pt
                        op = None; continue
                if "|-" in c or "-|" in c or c.startswith("[") or not c:
                    continue
                nm = _anchorless(c)
                if nm in nodes:
                    pt = ("n", nm)
                elif _num_xy(c):
                    pt = ("xy", _num_xy(c))
                else:
                    op = None; continue
                if op == "edge" and cur is not None:
                    pairs.append((cur, pt))
                elif op == "line" and cur is not None:
                    chain.append(pt); cur = pt
                else:
                    flush(); chain = [pt]; cur = pt
                op = None
            flush()
            for x, y in pairs:
                pending.append((x, y, rev, arrow, {"both": True} if both else None))
    for a_, b_, op in graph_edges:
        if op == "<-":
            a_, b_ = b_, a_
        pending.append((a_, b_, False, op != "--", None))
    # snap numeric endpoints to positioned nodes
    posn = [(n["id"], n["_xy"]) for n in nodes.values() if n["_xy"]]
    def resolve(pt):
        if isinstance(pt, str):
            return pt if pt in nodes else None
        k, v = pt
        if k == "n":
            return v
        if not posn:
            return None
        best = min(posn, key=lambda q: (q[1][0] - v[0]) ** 2 + (q[1][1] - v[1]) ** 2)
        d = ((best[1][0] - v[0]) ** 2 + (best[1][1] - v[1]) ** 2) ** 0.5
        xs = sorted(set(round(q[1][0], 3) for q in posn)); ys = sorted(set(round(q[1][1], 3) for q in posn))
        gaps = [b - a for a, b in zip(xs, xs[1:]) if b - a > 1e-6] + [b - a for a, b in zip(ys, ys[1:]) if b - a > 1e-6]
        tol = (min(gaps) if gaps else 2.0) * 0.9
        return best[0] if d <= max(tol, 0.5) else None
    edges = _wire_edges(pending, nodes, resolve, lmap, macros)
    for n in nodes.values():
        n.pop("_xy", None)
    return {"nodes": list(nodes.values()), "edges": edges}


def _scan_arrows(cell, kind):
    """Return (text_without_arrows, [(dir, label)]) for xymatrix (\ar) or tikzcd (\ar/\arrow)."""
    arrows = []; out = []; i = 0; n = len(cell)
    pat = re.compile(r"\\(?:ar|arrow)\b")
    while i < n:
        m = pat.search(cell, i)
        if not m:
            out.append(cell[i:]); break
        out.append(cell[i:m.start()]); j = m.end()
        dirn = ""; labs = []; style = ""
        # xy: @{..} @/^1pc/ @<2pt> @(ur,dl) etc.
        while j < n and cell[j] in " \t\n" and cell[j:].lstrip()[:1] == "@":    # \ar @/_2cm/ [ddd]
            j += 1
        while j < n and cell[j] == "@":
            j += 1
            if j < n and cell[j] == "{":
                st, j = brace_arg(cell, j)
                style += st or ""
            elif j < n and cell[j] in "/<(":
                close = {"/": "/", "<": ">", "(": ")"}[cell[j]]
                k = cell.find(close, j + 1); j = k + 1 if k > 0 else j + 1
            else:
                while j < n and cell[j] not in "[{\\ ^_@": j += 1
            while j < n and cell[j] in " \t\n" and cell[j:].lstrip()[:1] == "@": j += 1
        while j < n and cell[j] in " \t\n": j += 1
        if j < n and cell[j] == "[":
            k = cell.find("]", j)
            opts = cell[j + 1:k] if k > 0 else ""
            j = k + 1 if k > 0 else j + 1
            d = re.match(r"\s*([udlr]+)\b", opts)
            dirn = d.group(1) if d else ""
            style += opts                                # tikzcd: \arrow[d, <->] or [leftrightarrow]
            labs += re.findall(r"\"((?:[^\"\\]|\\.)*)\"", opts)
        # labels: ^{..} _{..} |{..} ^(.4){..}  or tikzcd {..} args
        while True:
            while j < n and cell[j] in " \t\n": j += 1
            if j < n and cell[j] in "^_|":
                j += 1
                while j < n and cell[j] in " ": j += 1
                if j < n and cell[j] in "<>(":
                    close = {"<": ">", ">": "<", "(": ")"}[cell[j]]
                    k = cell.find(close, j + 1); j = k + 1 if k > 0 else j + 1
                if j < n and cell[j] == "{":
                    c, j2 = brace_arg(cell, j)
                    if c is None: break
                    labs.append(c); j = j2
                elif j < n and cell[j] == "\\":
                    m2 = re.match(r"\\[A-Za-z]+", cell[j:]); labs.append(m2.group(0) if m2 else ""); j += len(m2.group(0)) if m2 else 1
                elif j < n:
                    labs.append(cell[j]); j += 1
            elif kind == "tikzcd" and j < n and cell[j] == "{":
                c, j2 = brace_arg(cell, j)
                if c is None: break
                labs.append(c); j = j2
            else:
                break
        arrows.append((dirn, " ".join(labs), bool(re.search(r"<[-=]+>|leftrightarrow|Leftrightarrow|<->", style))))
        i = j
    return "".join(out), arrows


def _split_top(s, sep):
    """s split at the matches of sep that are outside braces."""
    out, depth, last = [], 0, 0
    for m in re.finditer(r"\\[{}]|[{}]|" + sep, s):
        t = m.group(0)
        if t in "{}":
            depth += 1 if t == "{" else -1
        elif not t.startswith(("\\{", "\\}")) and depth == 0:
            out.append(s[last:m.start()]); last = m.end()
    return out + [s[last:]]


def parse_grid(code, kind, lmap, macros):
    """xymatrix / tikzcd: cells and arrows with relative [dir] targets"""
    nodes = []; edges = []
    for i, row in enumerate(_split_top(code, r"\\\\(?:\[[^\]]*\])?")):     # a \\ inside a cell is a line break
        for j, cell in enumerate(_split_top(row, r"(?<!\\)&")):
            txt, arrows = _scan_arrows(cell, kind)
            txt = txt.strip()
            nid = f"r{i+1}c{j+1}"
            if txt:
                nodes.append({"id": nid, "text": txt[:300], "refs": resolve_refs(txt, lmap, macros)})
            for dirn, lab, both in arrows:
                di = dirn.count("d") - dirn.count("u"); dj = dirn.count("r") - dirn.count("l")
                e = {"from": nid, "to": f"r{i+1+di}c{j+1+dj}", "directed": True} | ({"both": True} if both else {})
                if lab.strip():
                    e["label"] = lab[:200]; e["label_refs"] = resolve_refs(lab, lmap, macros)
                edges.append(e)
    return {"nodes": nodes, "edges": edges}


_SIZE = {"tiny": 0.5, "scriptsize": 0.7, "footnotesize": 0.8, "small": 0.9, "large": 1.2, "Large": 1.44}
_EM = {"em": 1, "ex": 0.45, "pt": 0.1, "bp": 0.1, "mm": 0.285, "cm": 2.85, "in": 7.2}


def unit_em(tex):
    r"""The picture's \unitlength in em (the last setting in tex; LaTeX's default is 1pt)."""
    m = re.findall(r"\\unitlength\s*(?:=|\}\s*\{)\s*([-\d.]+)\s*(em|ex|pt|bp|mm|cm|in)", tex)
    return float(m[-1][0]) * _EM[m[-1][1]] if m else 0.1


def parse_picture(code, lmap, macros, unit=0.1):
    r"""LaTeX picture env: boxes from \put(x,y){\framebox...{text}} (or plain text), lines and arrows
    from \put(x,y){\line|\vector(dx,dy){len}}. Lines and arrows meeting at a point are one wire (an
    arrow that turns a corner); unit: \unitlength in em, to estimate the size of a box from its text."""
    boxes, segs = [], []
    for m in re.finditer(r"\\put\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)\s*\{", code):
        body, _ = brace_arg(code, m.end() - 1)
        if body is None:
            continue
        x, y = float(m.group(1)), float(m.group(2))
        v = re.match(r"\s*\\(vector|line)\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)\s*\{\s*([-\d.]+)\s*\}", body)
        if v:
            dx, dy, L = float(v.group(2)), float(v.group(3)), float(v.group(4))
            end = (x + L * (1 if dx > 0 else -1), y + L * dy / abs(dx)) if dx else (x, y + L * (1 if dy > 0 else -1))
            segs.append(((x, y), end, v.group(1) == "vector"))
            continue
        fb = re.match(r"\s*\\(?:framebox|makebox|fbox|dashbox\{[^}]*\}|oval)\s*(?:\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\))?\s*(?:\[([-\d.]+)\s*(em|ex|pt|bp|mm|cm|in)\])?\s*(?:\[[^\]]*\])?\s*\{", body)
        txt = ((brace_arg(body, fb.end() - 1)[0] if fb else body) or "").strip()
        if not txt or not fb and re.match(r"\\(?:line|circle|vector|oval|multiput|qbezier)", txt):
            continue
        vis = len(re.sub(r"\\[A-Za-z]+\*?|[{}$~]", "", re.sub(r"\\[cC]?ref\{[^}]*\}", "00", re.sub(r"\\cite\{[^}]*\}", "[00]", txt))))
        size = next((f for c, f in _SIZE.items() if "\\" + c in txt), 1)
        w = float(fb.group(1)) if fb and fb.group(1) else \
            float(fb.group(3)) * _EM[fb.group(4)] / unit if fb and fb.group(3) else (0.45 * size * vis + 0.6 * bool(fb)) / unit
        h = float(fb.group(2)) if fb and fb.group(2) else 1.2 * size / unit
        x, y = (x - w / 2, y - h / 2) if fb and "oval" in fb.group(0) else (x, y)   # \oval is centred on its point
        boxes.append({"id": f"b{len(boxes)+1}", "text": txt[:300], "refs": resolve_refs(txt, lmap, macros), "box": [x, y, w, h],
                      "_xy": (x + w / 2, y + h / 2)})

    def nearest(pt):                                     # (distance, box) nearest to pt; inside several: the nearest centre
        d = lambda b: (round(((pt[0] - min(max(pt[0], b["box"][0]), b["box"][0] + b["box"][2])) ** 2 +
                              (pt[1] - min(max(pt[1], b["box"][1]), b["box"][1] + b["box"][3])) ** 2) ** 0.5, 6),
                       (pt[0] - b["_xy"][0]) ** 2 + (pt[1] - b["_xy"][1]) ** 2)
        b = min(boxes, key=d) if boxes else None
        return (d(b)[0], b["id"]) if b else (1e9, None)
    ends = [p for a, b, _ in segs for p in (a, b)]
    shared = {p for p in ends if sum(abs(p[0] - q[0]) + abs(p[1] - q[1]) < 1e-3 for q in ends) > 1}
    # an end at a box is that box (several arrows may fan out of one point under a label); a point where
    # lines meet away from the boxes is a junction (an arrow turning a corner); any other end: the nearest box
    pt = lambda p: ("n", nearest(p)[1]) if p not in shared or nearest(p)[0] <= 0.3 / unit else ("xy", p)
    nodes = {b["id"]: b for b in boxes}
    pending = [(pt(a), pt(b), False, arrow, None) for a, b, arrow in segs]
    edges = [e for e in _wire_edges(pending, nodes, lambda p: p[1] if p[0] == "n" else None, lmap, macros)
             if e["directed"]]                                              # a bare line between two boxes: decoration
    for b in boxes:
        b.pop("_xy")
    return {"nodes": boxes, "edges": edges}
