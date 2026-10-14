#!/usr/bin/env python3
"""Parse an author-drawn dependency diagram (TikZ, tikzcd, xymatrix, picture) into a graph.

Nodes are the drawing's boxes with their text and the \\ref labels inside them (resolved
to what each label is attached to); edges are its arrows. Used by build_gold_review.py.
Taken from the survey's fetch_eprints.py (stage 7), with the e-print download left out.
"""
import re


REF_CMDS = r"(?:ref|cref|Cref|eqref|autoref|Autoref|nameref|vref|Vref|thmref|labelcref)"


def strip_comments(t):
    return "\n".join(re.sub(r"(?<!\\)%.*", "", ln) for ln in t.split("\n"))


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


def parse_tikz(code, lmap, macros):
    """Statement-level TikZ parser -> nodes (named / positioned) and directed edges."""
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
    global_arrow = bool(re.search(r"(?:^|[\[,\s])(?:->|-latex|-stealth|-Stealth|-Latex|-to|->>|-\{[^}]*\})(?:[\],\s]|$)", code[:2000])) or "every path/.style={draw, -" in code
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
            arrow = bool(re.search(r"->|<-|latex|stealth|Stealth|Latex|-to\b|>=|Triangle|pil|arrow", opts)) or global_arrow
            rev = ("<-" in opts and "->" not in opts) or bool(re.search(r"\[\s*<-", opts))
            body = re.sub(r"node\s*(\[[^\]]*\])?\s*(\([^)]*\))?\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", " ", s0)
            body = re.sub(r"\[[^\]]*\]", " ", body)
            toks = re.finditer(r"\bedge\b|--|\bto\b|\band\b|\.\.(?:\s*controls)?|\(\s*([^()]*?(?:\([^()]*\)[^()]*?)*)\s*\)", body)
            cur = None; start = None; op = None; pairs = []; chain = []
            def flush():
                if len(chain) >= 2:
                    if all(k == "n" for k, _ in chain):
                        pairs.extend(zip(chain, chain[1:]))
                    else:
                        pairs.append((chain[0], chain[-1]))
            for t in toks:
                tok = t.group(0)
                if tok == "edge":
                    op = "edge"; continue
                if tok == "and":
                    op = "line"; continue
                if tok in ("--", "to") or tok.startswith(".."):
                    op = op or "line"; continue
                c = (t.group(1) or "").strip()
                if c.startswith("$"):
                    inner = re.search(r"\(\s*([^()$]+?)\s*\)", c)
                    c = inner.group(1) if inner and not _num_xy(inner.group(1)) else ""
                if "|-" in c or "-|" in c or c.startswith("[") or not c:
                    continue
                nm = re.sub(r"\.(?:north|south|east|west|center|north east|north west|south east|south west|base|mid|\d+)\s*$", "", c).strip()
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
                pending.append((x, y, rev, arrow, None))
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
    seen = set()
    for x, y, rev, arrow, lab in pending:
        a, b = resolve(x), resolve(y)
        if not a or not b or a == b:
            continue
        if rev:
            a, b = b, a
        key = (a, b)
        if key in seen:
            continue
        seen.add(key)
        e = {"from": a, "to": b, "directed": bool(arrow)}
        if lab:
            e["label"] = lab[:200]; e["label_refs"] = resolve_refs(lab, lmap, macros)
        edges.append(e)
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
        dirn = ""; labs = []
        # xy: @{..} @/^1pc/ @<2pt> @(ur,dl) etc.
        while j < n and cell[j] in " \t\n" and cell[j:].lstrip()[:1] == "@":    # \ar @/_2cm/ [ddd]
            j += 1
        while j < n and cell[j] == "@":
            j += 1
            if j < n and cell[j] == "{":
                _, j = brace_arg(cell, j)
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
        arrows.append((dirn, " ".join(labs)))
        i = j
    return "".join(out), arrows


def parse_grid(code, kind, lmap, macros):
    """xymatrix / tikzcd: cells and arrows with relative [dir] targets"""
    rows = re.split(r"\\\\", code)
    nodes = []; edges = []
    for i, row in enumerate(rows):
        for j, cell in enumerate(row.split("&")):
            txt, arrows = _scan_arrows(cell, kind)
            txt = txt.strip()
            nid = f"r{i+1}c{j+1}"
            if txt:
                nodes.append({"id": nid, "text": txt[:300], "refs": resolve_refs(txt, lmap, macros)})
            for dirn, lab in arrows:
                di = dirn.count("d") - dirn.count("u"); dj = dirn.count("r") - dirn.count("l")
                e = {"from": nid, "to": f"r{i+1+di}c{j+1+dj}", "directed": True}
                if lab.strip():
                    e["label"] = lab[:200]; e["label_refs"] = resolve_refs(lab, lmap, macros)
                edges.append(e)
    return {"nodes": nodes, "edges": edges}


def parse_picture(code, lmap, macros):
    """LaTeX picture env: boxes from \\put(x,y){\\framebox(w,h){text}} and arrows from \\put(x,y){\\vector(dx,dy){len}}."""
    boxes = []; vecs = []
    for m in re.finditer(r"\\put\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)\s*\{", code):
        body, _ = brace_arg(code, m.end() - 1)
        if body is None:
            continue
        x, y = float(m.group(1)), float(m.group(2))
        v = re.match(r"\s*\\vector\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)\s*\{\s*([-\d.]+)\s*\}", body)
        if v:
            dx, dy, L = float(v.group(1)), float(v.group(2)), float(v.group(3))
            if dx != 0:
                ex, ey = x + L * (1 if dx > 0 else -1), y + L * dy / abs(dx)
            else:
                ex, ey = x, y + L * (1 if dy > 0 else -1)
            vecs.append(((x, y), (ex, ey)))
            continue
        fb = re.match(r"\s*\\(?:framebox|makebox|dashbox\{[^}]*\}|oval)\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)\s*(?:\[[^\]]*\])?\s*\{", body)
        if fb:
            w, h = float(fb.group(1)), float(fb.group(2))
            txt, _ = brace_arg(body, fb.end() - 1)
            txt = (txt or "").strip()
            if txt:
                boxes.append({"id": f"b{len(boxes)+1}", "text": txt[:300], "refs": resolve_refs(txt, lmap, macros), "box": [x, y, w, h]})
        else:
            txt = body.strip()
            if txt and not re.match(r"\\(?:line|circle|vector|oval|multiput|qbezier)", txt):
                boxes.append({"id": f"b{len(boxes)+1}", "text": txt[:300], "refs": resolve_refs(txt, lmap, macros), "box": [x, y, 0, 0]})
    def nearest(pt):
        best = None; bd = 1e9
        for b in boxes:
            x, y, w, h = b["box"]
            cx = min(max(pt[0], x), x + w); cy = min(max(pt[1], y), y + h)
            d = ((pt[0] - cx) ** 2 + (pt[1] - cy) ** 2) ** 0.5
            if d < bd:
                bd = d; best = b["id"]
        return best, bd
    edges = []
    for s0, e0 in vecs:
        a, da = nearest(s0); b, db = nearest(e0)
        if a and b and a != b:
            edges.append({"from": a, "to": b, "directed": True, "snap_dist": [round(da, 2), round(db, 2)]})
    return {"nodes": boxes, "edges": edges}
