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
AT = r"at\s*\((?:[^()]|\([^()]*\))*\)"                    # at (x,y), at ($(a)!0.5!(b)$)
NODE_RE = re.compile(r"\bnode\b((?:\s*(?:" + OPT + r"|\([^)]*\)|" + AT + r"))*)\s*\{")
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
        if not isinstance(pt, str) and pt[0] == "c":    # a named \coordinate where lines meet
            return pt
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
    feeds = []                                           # (junction, node): lines meeting an arrow's shaft feed its head
    for a, b, arrow in segs:
        if arrow:
            pa, pb = xy(a), xy(b)
            if isinstance(b, str) and pa and pb:
                feeds += [(j, b) for j in junctions if j[0] == "j" and j[1] not in (pa, pb) and _on_segment(j[1], pa, pb)]
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
    for j, b in feeds:
        comp.setdefault(find(j), {"und": set(), "in": set(), "out": set()})["out"].add(b)
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
                if e.get("label"):
                    e["label"] = e["label"][:200]; e["label_refs"] = resolve_refs(e["label"], lmap, macros)
            elif (a, b) in labs:
                e["label"] = labs[a, b][:200]; e["label_refs"] = resolve_refs(labs[a, b], lmap, macros)
            edges.append(e)
    return edges


_ARROW = r"->|<-|latex|stealth|Stealth|Latex|-to\b|Triangle|pil|arrow|implies|-\{|-\s*(?:Straight|Classical|Rays|Computer|To)\b|-\s*(?:open )?(?:triangle|angle|diamond)\b|(?:triangle|angle) \d+\s*-"
GLOBAL_ARROW = "\0every path"
DECORATED_ARROW = "\0markings"                         # in arrow_styles: decorate draws an arrow mark on the path                            # in arrow_styles: the preamble makes every path an arrow


def arrow_styles(tex):
    """Names of the paper's TikZ styles that draw arrows: \\tikzstyle{line}=[draw,-latex], line/.style={->}."""
    defs = re.findall(r"\\tikzstyle\s*\{([^}]+)\}\s*=\s*\[([^\]]*)\]", tex) + \
        re.findall(r"([A-Za-z][\w ]*?)/\.style\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}", tex)
    glob = [d for d in re.findall(r"\\tikzset\s*\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}", tex)
            for d in [re.sub(r"[\w ]+/\.style\s*=\s*\{(?:[^{}]|\{[^{}]*\})*\}", "", d)]]        # \tikzset{-Latex, ...}
    glob += re.findall(r"every (?:path|edge)/\.style\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}", tex)
    top = any(re.search(r"(?:^|,)\s*(?:->|-latex|-stealth|-Stealth|-Latex|-to|->>|-\{[^}]*\})\s*(?:,|$)", d) for d in glob)
    marks = bool(re.search(r"markings[^;]{0,300}?\\arrow", tex))         # mark=at position .5 with {\arrow{>}}
    return {n.strip() for n, d in defs if re.search(_ARROW, d)} | ({GLOBAL_ARROW} if top else set()) | ({DECORATED_ARROW} if marks else set())


def _brace_groups(pending, braces, posn, shared):
    """Arrows that start or end at the tip of a curly brace (\\draw[decorate, decoration=brace]) connect every
    box the brace groups: those beside the brace, on the side of the nearest one. An arrow end within 0.9 of
    the brace's midpoint is at its tip."""
    groups = []
    for (ax, ay), (bx, by) in braces:
        L = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 or 1
        side = []
        for name, (x, y) in posn:
            t = ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / L ** 2
            perp = ((bx - ax) * (y - ay) - (by - ay) * (x - ax)) / L       # signed distance from the brace
            if -0.1 <= t <= 1.1 and abs(perp) <= 2.0:
                side.append((abs(perp), perp > 0, name))
        if side:
            d0, s0, _ = min(side)
            groups.append((((ax + bx) / 2, (ay + by) / 2), [n for d, s, n in side if s == s0 and d <= d0 + 0.6]))
    def ends(p):
        if isinstance(p, str) or p[0] != "xy" or p[1] in shared:
            return [p]
        g = next((m for (cx, cy), m in groups if ((p[1][0] - cx) ** 2 + (p[1][1] - cy) ** 2) ** 0.5 <= 0.9), None)
        return [("n", n) for n in g] if g else [p]
    return [(a, b, *rest) for x, y, *rest in pending for a in ends(x) for b in ends(y)]


def _cm(v, u):
    return float(v) * {"cm": 1, "mm": .1, "pt": .0351, "bp": .0353, "em": .35, "ex": .16, "in": 2.54}[u]


_DIRS = {"above": (0, 1), "below": (0, -1), "left": (-1, 0), "right": (1, 0)}


def _relative_place(opts, nodes, dist, scale):
    """Position of a node placed relative to another: "below of=X", "right=2cm of X", "above left=1 and 2 of X"
    (and xshift / yshift), in picture units; None when X has no position."""
    m = re.search(r"\b(above|below)?\s*(left|right)?\s*(?:of\s*=\s*|=\s*(?:([\d.]+)\s*(cm|mm|pt|em|ex|in)?\s*"
                  r"(?:and\s*([\d.]+)\s*(cm|mm|pt|em|ex|in)?\s*)?)?of\s+)\(?([^,\])]+?)\)?\s*(?:[,\]]|$)", opts)
    if not m or not (m.group(1) or m.group(2)):
        return None
    ref = nodes.get(_anchorless(m.group(7).strip()), {}).get("_xy")
    if not ref:
        return None
    d1 = _cm(m.group(3), m.group(4) or "cm") if m.group(3) else dist
    d2 = _cm(m.group(5), m.group(6) or "cm") if m.group(5) else d1
    vy, hx = (_DIRS[m.group(1)][1] if m.group(1) else 0), (_DIRS[m.group(2)][0] if m.group(2) else 0)
    dx, dy = hx * (d2 if vy else d1), vy * d1
    for k, sgn in (("xshift", 0), ("yshift", 1)):
        sh = re.search(k + r"\s*=\s*(-?[\d.]+)\s*(cm|mm|pt|em|ex|in)?", opts)
        if sh:
            v = _cm(sh.group(1).lstrip("-"), sh.group(2) or "cm") * (-1 if sh.group(1).startswith("-") else 1)
            dx, dy = (dx + v, dy) if sgn == 0 else (dx, dy + v)
    return (ref[0] + dx / scale, ref[1] + dy / scale)


def _node_extent(opts, txt, scale):
    """(half width, half height) of a TikZ node in picture units: text width / minimum width when given, else from
    the text (0.18cm a character, 0.42cm a line), plus inner sep; None for an empty node (a coordinate)."""
    if not txt.strip():
        return None
    cm = lambda v, u: float(v) * {"cm": 1, "mm": .1, "pt": .0351, "em": .35, "ex": .16, "in": 2.54}[u]
    dim = lambda k: next((cm(*m.groups()) for m in [re.search(k + r"\s*=\s*([\d.]+)\s*(cm|mm|pt|em|ex|in)", opts)] if m), 0)
    lines = re.split(r"\\\\", txt)
    vis = max(len(re.sub(r"\\[A-Za-z]+\*?|[{}$~]", "", re.sub(r"\\ref\{[^}]*\}", "00", re.sub(r"\\(?:[cC]ref|autoref)\{[^}]*\}", "Lemma 0.00", ln))))
              for ln in lines)                       # \cref prints "Lemma 3.2"
    w = max(dim(r"text width") or 0.18 * vis, dim(r"minimum width")) + 0.24
    h = max(0.42 * len(lines), dim(r"minimum height")) + 0.24
    return (w / 2 / scale, h / 2 / scale)


def parse_tikz(code, lmap, macros, styles=()):
    """Statement-level TikZ parser -> nodes (named / positioned) and directed edges.
    styles: names of the paper's arrow styles (arrow_styles)."""
    m = re.search(r"\\begin\{tikzpicture\}\s*(" + OPT + r")?", code)
    # arrows by default: set in the picture's options or an every path/edge style, not by one \draw[->]
    pic = ((m.group(1) or "") if m else "") + " ".join(re.findall(r"every (?:path|edge)/\.style\s*=\s*\{[^}]*\}", code))
    local = [(n.strip(), d) for n, d in re.findall(r"([A-Za-z][\w ]*?)/\.style\s*=\s*\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}", code)]
    # a tip only at the start ("<-", "{Straight Barb}-", "latex-"): the arrow points back to where it starts
    back = {n for n, d in local if re.search(r"(?:^|,)\s*(?:<|\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}|[A-Za-z]+(?:\[[^\]]*\])?)-\s*(?:,|$)", d)}
    styles = set(styles) | {n for n, d in local if re.search(_ARROW, d)} | back
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
    sc = re.search(r"(?<![\w ])scale\s*=\s*([\d.]+)", pic)         # coordinates are in units of scale x 1cm
    scale = float(sc.group(1)) if sc and float(sc.group(1)) > 0 else 1.0
    global_arrow = bool(re.search(r"(?:^|[\[,\s{])(?:->|-latex|-stealth|-Stealth|-Latex|-to|->>|-\{[^}]*\})(?:[\],\s}]|$)", pic)) or GLOBAL_ARROW in styles
    nd = re.search(r"node distance\s*=\s*([\d.]+)\s*(cm|mm|pt|em|ex|in)?", pic + " " + code)
    node_dist = _cm(nd.group(1), nd.group(2) or "cm") if nd else 1.0
    nodes = {}; anon = 0; edges = []
    def add_node(comps, txt, name_hint=None, standalone=False):
        nonlocal anon
        at = re.search(r"at\s*\(((?:[^()]|\([^()]*\))*)\)", comps)
        rest = re.sub(AT, "", comps)
        rest = re.sub(OPT, "", rest)
        nm = re.search(r"\(([^)]*)\)", rest)
        nopt = re.search(r"\bname\s*=\s*([^,\]]+)", comps)
        name = (nm.group(1).strip() if nm else "") or (nopt.group(1).strip() if nopt else "") or name_hint
        if not name:
            anon += 1; name = f"_anon{anon}"
        pos = _num_xy(at.group(1)) if at else None
        pos = (pos[0] + shifts[-1][0], pos[1] + shifts[-1][1]) if pos else None
        mid = re.match(r"\s*\$\s*\(([^()]+)\)\s*!\s*([\d.]+)\s*!\s*\(([^()]+)\)\s*\$\s*$", at.group(1)) if at else None
        if mid:                                          # at ($(a)!t!(b)$): between two placed boxes
            pa, pb = (nodes.get(_anchorless(x), {}).get("_xy") for x in (mid.group(1), mid.group(3)))
            t = float(mid.group(2))
            pos = (pa[0] + t * (pb[0] - pa[0]), pa[1] + t * (pb[1] - pa[1])) if pa and pb else None
        elif not at:                                     # "below of=X", "right=2cm of X", "above left=of X"
            pos = _relative_place(comps, nodes, node_dist, scale)
            if pos is None and standalone and not re.search(r"\bof\s*=|\bof\s+\(?\w", comps):
                pos = (0.0, 0.0)                         # "\node (a) {..};" with no position: at the origin
        fit = re.search(r"\bfit\s*=\s*((?:\s*\([^()]*\))+)", comps)      # a frame drawn around other boxes
        if fit:
            frames[name] = [_anchorless(x) for x in re.findall(r"\(([^()]*)\)", fit.group(1))]
        nodes[name] = {"id": name, "text": (txt or "").strip()[:300], "refs": resolve_refs(txt or "", lmap, macros),
                       "at": at.group(1) if at else None, "_xy": pos, "_ext": _node_extent(comps, txt or "", scale),
                       "_label": not re.search(r"\bdraw\b|\b(?:rectangle|circle|ellipse|rounded corners)\b|\\[cC]?ref|\\autoref|\\fbox",
                                               (comps or "") + (txt or "")) and not re.search(r"\[\s*[A-Za-z_]\w*\s*(?:,|\])", comps or "")}
        return name
    stmts = _split_statements(code)
    # "(A) -- coordinate[midway](M) (B)": a point on the arrow A -> B; a line or arrow drawn into M is a result
    # used for that step, so it ends at B (whatever the line's own tips: it meets an arrow)
    on_arrow = {}
    for st in stmts:
        for m in re.finditer(r"\(([^()]+)\)\s*(?:--|to)\s*coordinate\s*(?:\[[^\]]*\])?\s*\(([^()]+)\)\s*\(([^()]+)\)", st):
            rev_ = bool(re.search(r"^\\\w+\s*\[[^\]]*<-(?![^\]]*->)", st.strip()))
            on_arrow[m.group(2).strip()] = _anchorless(m.group(1)) if rev_ else _anchorless(m.group(3))
    braces, frames, arrow_labels, coords = [], {}, {}, {}
    pending = []  # (kind, statement)
    shifts = [(0.0, 0.0)]                                # \begin{scope}[xshift=.., yshift=.., shift={(x,y)}]
    scope_opts = [""]                                    # \begin{scope}[every path/.style=line]: paths styled within
    for st in stmts:
        for sc_ in re.finditer(r"\\(begin|end)\{scope\}\s*(" + OPT + r")?", st):
            if sc_.group(1) == "end":
                shifts, scope_opts = shifts[:-1] or [(0.0, 0.0)], scope_opts[:-1] or [""]
                continue
            o, (dx, dy) = sc_.group(2) or "", shifts[-1]
            ps = re.search(r"every (?:path|edge)/\.style\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|[^,\]]+)", o)
            # tips on the scope itself ("[->, shorten >=1mm]", "[-Triangle]") hold for its paths
            tips = ",".join(x for x in re.split(r",", re.sub(r"[\w ]+/\.style\s*=\s*\{(?:[^{}]|\{[^{}]*\})*\}", "", o.strip("[]")))
                            if re.search(r"^\s*(?:<|[A-Za-z{][^=]*)?-[^=]*$", x) and re.search(_ARROW, x))
            scope_opts.append(scope_opts[-1] + "," + (ps.group(1).strip("{} ") if ps else "") + ("," + tips if tips else ""))
            sh = _num_xy((re.search(r"\bshift\s*=\s*\{?\s*\(([^()]*)\)", o) or [None, ""])[1])
            dx, dy = (dx + sh[0], dy + sh[1]) if sh else (dx, dy)
            for k, ax in (("xshift", 0), ("yshift", 1)):
                v = re.search(k + r"\s*=\s*(-?[\d.]+)\s*(cm|mm|pt|em|ex|in)?", o)
                if v:
                    d = _cm(v.group(1).lstrip("-"), v.group(2) or "pt") * (-1 if v.group(1).startswith("-") else 1) / scale
                    dx, dy = (dx + d, dy) if ax == 0 else (dx, dy + d)
            shifts.append((dx, dy))
        off = shifts[-1]
        s0 = re.sub(r"^(?:\s*\\(?:begin|end)\{\w+\}\s*(?:" + OPT + r")?|\s*\\tikzstyle\s*\{[^}]*\}\s*=\s*" + OPT + r")+", "", st).strip()   # \end{scope}, \begin{scriptsize} \node ...
        s0 = re.sub(r"^(?:\s*\\(?:[gex]?def\s*\\\w+|pgfmathsetmacro\s*\{[^{}]*\}|tikzset|newcommand\s*\{?\\\w+\}?(?:\[\d\])?)\s*"
                    r"\{(?:[^{}]|\{[^{}]*\})*\})+", "", s0).strip()        # "\def\maxA{5} ... \node": the definitions before it
        # a stray character, an argument-less command or an option block before it: "= \path",
        # "\footnotesize \node", a repeated "[>=stealth]" line
        s0 = re.sub(r"^(?:[^\\\s]{1,3}|\\[A-Za-z]+(?![\[{\w])|(?:\s*" + OPT + r")+)(?=\s*\\(?:draw|path|node|matrix)\b)\s*", "", s0).strip()
        s0 = re.sub(r"^(?:\s*\\(?!(?:draw|path|node|matrix|coordinate|graph|foreach|fill|filldraw|shade)\b)[A-Za-z@]+\*?(?:\s*\[[^\]]*\])?"
                    r"(?:\s*\{(?:[^{}]|\{[^{}]*\})*\})+)+(?=\s*\\(?:draw|path|node|matrix|coordinate)\b)", "", s0).strip()  # \hypersetup{..} \node
        cm_ = re.match(r"\\coordinate\s*(?:\[[^\]]*\])?\s*\(([^)]*)\)\s*at\s*\((.*)\)\s*$", s0, re.S)
        if cm_:                                          # \coordinate (Q) at ([xshift=..]P.east): a point by box P
            base = re.findall(r"([A-Za-z_][\w-]*)\.(?:north|south|east|west|center)", cm_.group(2))
            coords[cm_.group(1).strip()] = base[0] if base else None
            continue
        if re.match(r"\\(?:node|matrix)\b", s0):
            if s0.startswith("\\matrix"):
                m = re.match(r"\\matrix\s*(\[[^\]]*\])?\s*\(([^)]*)\)\s*(\[[^\]]*\])?\s*(?:" + AT + r")?\s*\{", s0)
                if m:
                    body, _ = brace_arg(s0, m.end() - 1)
                    mname = m.group(2).strip()
                    for i, row in enumerate(re.split(r"\\\\", body or ""), 1):
                        for j, cell in enumerate(row.split("&"), 1):
                            c = re.sub(r"^\s*\|[^|]*\|", "", cell).strip()
                            if c:
                                nodes[f"{mname}-{i}-{j}"] = {"id": f"{mname}-{i}-{j}", "text": c[:300], "refs": resolve_refs(c, lmap, macros), "at": None, "_xy": None}
                continue
            m = re.match(r"\\node\b((?:\s*(?:" + OPT + r"|\([^)]*\)|" + AT + r"))*)\s*\{", s0)
            if not m:
                continue
            txt, end = brace_arg(s0, m.end() - 1)
            src = add_node(m.group(1), txt, standalone=True)
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
            # inline named nodes inside the path; "edge node={node {Motivates}}" in a to[...]: the arrow's label
            on_path = [m.group(1) for m in re.finditer(r"edge node\s*=\s*\{\s*node\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}", s0)]
            for m in NODE_RE.finditer(s0):
                comps = m.group(1)
                txt, _ = brace_arg(s0, m.end() - 1)
                if re.search(r"\(([^)]*)\)", re.sub(AT, "", re.sub(r"\[[^\]]*\]", "", comps))):
                    add_node(comps, txt)
                elif not re.search(r"\\[cC]?ref\{|\\autoref\{", txt or ""):
                    on_path.append(txt or "")              # text written along the path: the arrow's label
                elif re.search(r"\\[cC]?ref\{|\\autoref\{", txt or ""):     # "(1,-9) node[left]{Theorem \ref{a}}": a box there
                    before = re.search(r"\(([^()]*)\)\s*$", s0[:m.start()])
                    if before and _num_xy(before.group(1)):
                        add_node(comps + f" at ({before.group(1)})", txt)
            opts = " ".join(re.findall(r"^\\\w+\s*(\[[^\]]*\])", s0))
            # "(a) edge node[label=right:{Succeed}] {} (b)": the text on an arrow
            for e in re.finditer(r"\(([^()]*)\)\s*edge\s*(?:\[[^\]]*\])?\s*node\s*(\[(?:[^\[\]]|\[[^\]]*\])*\])?\s*\{([^{}]*)\}\s*\(([^()]*)\)", s0):
                txt = " ".join(re.findall(r"label\s*=\s*(?:\w+\s*:)?\s*\{([^{}]*)\}", e.group(2) or "")) + " " + e.group(3)
                if txt.strip():
                    arrow_labels[_anchorless(e.group(1)), _anchorless(e.group(4))] = re.sub(r"\s+", " ", txt).strip()
            if "decorat" in opts and "brace" in opts:   # a curly brace: groups the boxes beside it
                pts = [_num_xy(c) for c in re.findall(r"\(([^()]*)\)", re.sub(r"\[[^\]]*\]", "", s0))]
                braces += [tuple(pts[:2])] if len(pts) >= 2 and all(pts[:2]) else []
                continue
            opts = (opts + "," + scope_opts[-1]) if scope_opts[-1].strip(",") else opts
            if s0.startswith("\\path") and not re.search(r"\bedge\b", s0) and not re.search(
                    r"\bdraw\b|" + _ARROW, opts) and not any(o.strip() and "=" not in o for o in re.split(r"[\[\],]", opts)):
                continue                                 # "\path (a) -- (b)" draws nothing (placement only)
            arrow = bool(re.search(_ARROW, opts)) or (DECORATED_ARROW in styles and "decorate" in opts) or any(o.strip() and o.strip() in styles for o in re.split(r"[\[\],]", opts)) \
                or global_arrow and not re.search(r"[\[,]\s*-\s*[\],]", opts)
            rev = ("<-" in opts and "->" not in opts) or bool(re.search(r"\[\s*<-", opts)) \
                or any(x.strip() in back for x in re.split(r"[\[\],]", opts))
            both = bool(re.search(r"<[-=]+>|\b(\w+)-\1\b", opts))     # <->, <=>, latex-latex: arrowheads at both ends
            body = re.sub(r"node\s*(\[[^\]]*\])?\s*(\([^)]*\))?\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", " ", s0)
            body = re.sub(r"\bcoordinate\s*(\[[^\]]*\])?\s*\([^()]*\)", " ", body)    # a named point on the path
            def edge_kind(e):                            # "edge[->]": the edge's own tips (R reversed, B both, P plain)
                o = e.group(1)
                tip = bool(re.search(_ARROW, o)) or any(x.strip() and x.strip() in styles for x in o.split(","))
                kind = ("B" if re.search(r"<[-=]+>", o) else "R" if "<-" in o and "->" not in o else "A") if tip else \
                    ("A" if global_arrow and not re.search(r"(?:^|,)\s*-\s*(?:,|$)", o) else "P")
                return " edge" + kind + " "
            body = re.sub(r"\bedge\s*\[((?:[^\[\]]|\[[^\]]*\])*)\]", edge_kind, body)
            body = re.sub(r"\[[^\]]*\]", " ", body)
            toks = re.finditer(r"\bedge[ARBP]?\b|--|-\||\|-|\bto\b|\band\b|\.\.(?:\s*controls)?|\(\s*([^()]*?(?:\([^()]*\)[^()]*?)*)\s*\)", body)
            cur = None; start = None; op = None; pairs = []; chain = []; into_step = False; ctrl = False; ekind = None
            def flush():
                nonlocal chain
                # a plain text node (no frame, no \ref) inside an arrow's path is the arrow's label, not a stop
                chain = chain[:1] + [p for p in chain[1:-1] if not (arrow and p[0] == "n" and nodes[p[1]].get("_label"))] + chain[-1:] \
                    if len(chain) > 2 else chain
                if len(chain) >= 2:
                    if not arrow or all(p[0] == "n" for p in chain):     # plain lines: every piece is a wire
                        pairs.extend(zip(chain, chain[1:]))
                    else:
                        pairs.append((chain[0], chain[-1]))
            for t in toks:
                tok = t.group(0)
                if tok.startswith("edge"):
                    op, ekind = "edge", tok[4:] or None; continue
                if tok == "and":
                    if not ctrl:
                        op = "line"
                    continue
                if tok.startswith(".."):                 # .. controls (c1) and (c2) ..: control points, not ends
                    ctrl = "controls" in tok and not ctrl
                    op = op or "line"; continue
                if tok in ("--", "to", "-|", "|-"):
                    op = op or "line"; continue
                if ctrl and t.group(1) is not None:
                    continue
                c = (t.group(1) or "").strip()
                if c.startswith("$"):
                    m = re.match(r"\$\s*\(([^()]+)\)\s*!\s*[\d.]+\s*!\s*\(([^()]+)\)\s*\$$", c)   # $(B)!0.5!(C)$
                    a_, b_ = (_anchorless(x) for x in m.groups()) if m else (None, None)
                    if a_ in nodes and a_ == b_:                         # two anchors of one box: that box
                        pt = ("n", a_)
                    elif a_ in nodes and b_ in nodes:
                        pt = ("mid", a_, b_)
                    else:
                        inner = re.search(r"\(\s*([^()$]+?)\s*\)", c)
                        c = inner.group(1) if inner and not _num_xy(inner.group(1)) else ""
                        pt = None
                    if pt:
                        if op == "edge" and cur is not None:
                            pairs.append((cur, pt, ekind))
                        elif op == "line" and cur is not None:
                            chain.append(pt); cur = pt
                        else:
                            flush(); chain = [pt]; cur = pt
                        op = None; continue
                pm = re.match(r"(.+?)\s*(?:\|-|-\|)\s*(.+)$", c)
                if pm:                                   # (A |- B): the point level with A at B: B's box, else A's
                    c = next((x for x in (_anchorless(pm.group(2)), _anchorless(pm.group(1))) if x in nodes), "")
                if c.startswith("[") or not c:
                    continue
                nm = _anchorless(c)
                if nm in on_arrow and on_arrow[nm] in nodes and nm not in nodes:
                    pt = ("n", on_arrow[nm]); into_step = True
                elif nm in nodes:
                    pt = ("n", nm)
                elif nm in coords:
                    pt = ("c", nm)
                elif _num_xy(c):
                    pt = ("xy", (_num_xy(c)[0] + off[0], _num_xy(c)[1] + off[1]))
                else:
                    op = None; continue
                if op == "edge" and cur is not None:
                    pairs.append((cur, pt, ekind))
                elif op == "line" and cur is not None:
                    chain.append(pt); cur = pt
                else:
                    flush(); chain = [pt]; cur = pt
                op = None
            flush()
            if into_step and not arrow and chain:            # a plain line into an arrow's step: towards it
                pairs = [(chain[0], chain[-1])] if not pairs else [(pairs[0][0], pairs[-1][1])]
            for x, y, *k in pairs:
                k = k[0] if k else None
                lab = arrow_labels.get((x[1], y[1])) if x[0] == y[0] == "n" else None
                if not lab and len(pairs) == 1 and any(t.strip() for t in on_path):
                    lab = re.sub(r"\s+", " ", " ".join(dict.fromkeys(t.strip() for t in on_path if t.strip())))
                a_, r_, b_ = (k in "ARB", k == "R", k == "B") if k else (arrow or into_step, rev, both)
                extra = ({"both": True} if b_ else {}) | ({"label": lab} if isinstance(lab, str) and lab else {}) \
                    | ({"dashed": True} if re.search(r"\b(?:dashed|dotted|densely dashed|loosely dashed)\b", opts) else {})
                pending.append((x, y, r_, a_, extra or None))
    for a_, b_, op in graph_edges:
        if op == "<-":
            a_, b_ = b_, a_
        pending.append((a_, b_, False, op != "--", None))
    # a \coordinate where two or more lines end is a junction; one ending a single line is a point on its box
    c_ends = [p for x, y, *_ in pending for p in (x, y) if not isinstance(p, str) and p[0] == "c" and x != y]
    wired_c = {p for p in c_ends if c_ends.count(p) > 1}
    pending = [tuple(("n", coords[p[1]]) if not isinstance(p, str) and p[0] == "c" and p not in wired_c and coords.get(p[1]) else p
                     for p in (x, y)) + tuple(r) for x, y, *r in pending]
    # snap numeric endpoints to positioned nodes
    posn = [(n["id"], n["_xy"]) for n in nodes.values() if n["_xy"]]
    ends = [p[1] for x, y, *_ in pending for p in (x, y) if not isinstance(p, str) and p[0] == "xy"]
    shared = {p for p in ends if ends.count(p) > 1}        # where lines meet: junctions, never snapped loosely
    pending = _brace_groups(pending, braces, posn, shared)
    # an arrow to or from a frame (a fit node around other boxes) is an arrow to or from each box in it
    def members(p):
        name = p if isinstance(p, str) else p[1] if p[0] == "n" else None
        if name not in frames:
            return [p]
        return [q for m in frames[name] for q in members(("n", m) if not isinstance(p, str) else m)]
    pending = [(a, b, *rest) for x, y, *rest in pending for a in members(x) for b in members(y)]
    for f in frames:
        if not nodes[f]["text"]:
            del nodes[f]
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
        if d <= max(tol, 0.5):
            return best[0]
        # a free arrow end (touching no other line) stopping short of a box: the clearly nearest box
        d2 = min((((q[1][0] - v[0]) ** 2 + (q[1][1] - v[1]) ** 2) ** 0.5 for q in posn if q is not best), default=1e9)
        if v not in shared and d <= 1.5 and d2 >= 1.25 * d:
            return best[0]
        # an arrow ending at the edge of a wide box (text width=15cm): the box it touches, by the box's extent
        rect = sorted((((max(abs(q[1][0] - v[0]) - nodes[q[0]]["_ext"][0], 0) ** 2 + max(abs(q[1][1] - v[1]) - nodes[q[0]]["_ext"][1], 0) ** 2) ** 0.5,
                        q[0]) for q in posn if nodes.get(q[0], {}).get("_ext")))
        lim = (0.15 if v in shared else 0.35) / scale
        if rect and rect[0][0] <= lim and (len(rect) == 1 or rect[1][0] > lim):
            return rect[0][1]
        return None
    def ray(p, d, skip):                                 # the first box (by its extent) on the ray from p along d
        n = (d[0] ** 2 + d[1] ** 2) ** 0.5
        if not n:
            return None
        for k in range(1, 31):                           # up to 1.5cm
            q = (p[0] + d[0] / n * k * 0.05 / scale, p[1] + d[1] / n * k * 0.05 / scale)
            hit = next((nm for nm, c in posn if nm != skip and nodes.get(nm, {}).get("_ext")
                        and abs(q[0] - c[0]) <= nodes[nm]["_ext"][0] and abs(q[1] - c[1]) <= nodes[nm]["_ext"][1]), None)
            if hit:
                return hit
        return None
    xy_of = lambda p: p[1] if not isinstance(p, str) and p[0] == "xy" else None
    fixed = []
    for x, y, *rest in pending:                          # an arrow end in the gap before a box: the box it points to
        px, py = xy_of(x), xy_of(y)
        if px and py and rest[2]:
            rx, ry = resolve(x), resolve(y)
            if ry is None or ry == rx:
                h = ray(py, (py[0] - px[0], py[1] - px[1]), rx) if py not in shared else None
                y = ("n", h) if h else y
                ry = h or ry
            if rx is None or rx == ry:
                h = ray(px, (px[0] - py[0], px[1] - py[1]), ry) if px not in shared else None
                x = ("n", h) if h else x
        fixed.append((x, y, *rest))
    pending = fixed
    edges = _wire_edges(pending, nodes, resolve, lmap, macros)
    for n in nodes.values():
        if n.get("_xy"):                                 # where the authors put it (the viewer can draw it there)
            n["pos"] = [round(v, 3) for v in n["_xy"]]
        n.pop("_xy", None); n.pop("_ext", None); n.pop("_label", None)
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
    w = re.match(r"\s*\$*\s*\\xymatrix[^{]*\{", code)   # "\xymatrix@!0@=15pt{...}": its body
    if w:
        code = brace_arg(code, w.end() - 1)[0] or ""
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
    # a zero-size cell ("*=<0pt>{}", maybe with a caption beside it) is a point where arrows bend or branch:
    # an arrow into it continues along every arrow out of it, until a real cell
    junction = {n["id"] for n in nodes if re.match(r"\s*\*\s*=?\s*<0pt>\s*\{\s*\}", n["text"])}
    if junction:
        nodes = [n for n in nodes if n["id"] not in junction]
        out_of = {}
        for e in edges:
            out_of.setdefault(e["from"], []).append(e)
        def ends(j, seen):
            for e in out_of.get(j, []):
                if e["to"] in junction and e["to"] not in seen:
                    yield from ends(e["to"], seen | {e["to"]})
                elif e["to"] not in junction:
                    yield e
        edges = [e if e["to"] not in junction else dict(t, **{"from": e["from"]}) | ({k: e[k] for k in ("label", "label_refs") if k in e})
                 for e in edges if e["from"] not in junction
                 for t in ([e] if e["to"] not in junction else list(ends(e["to"], {e["to"]})))]
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

    def along(p, d, skip):                               # the first other box on the ray from p along d (within 6 em)
        n = (d[0] ** 2 + d[1] ** 2) ** 0.5 or 1
        tol = 0.2 / unit
        for k in range(1, 121):
            q = (p[0] + d[0] / n * k * 0.05 / unit, p[1] + d[1] / n * k * 0.05 / unit)
            hit = next((b["id"] for b in boxes if b["id"] != skip and b["box"][0] - tol <= q[0] <= b["box"][0] + b["box"][2] + tol
                        and b["box"][1] - tol <= q[1] <= b["box"][1] + b["box"][3] + tol), None)
            if hit:
                return hit
        return None

    pending = []
    for a, b, arrow in segs:
        pa, pb = pt(a), pt(b)
        if pa == pb and pa[0] == "n":                    # both ends at one box: the end farther from it was drawn
            far_a = nearest(a)[0] >= nearest(b)[0]       # loosely; it belongs to the box its line points back to
            o = along(a, (a[0] - b[0], a[1] - b[1]), pa[1]) if far_a else along(b, (b[0] - a[0], b[1] - a[1]), pb[1])
            if o:
                pa, pb = (("n", o), pb) if far_a else (pa, ("n", o))
        pending.append((pa, pb, False, arrow, None))
    edges = [e for e in _wire_edges(pending, nodes, lambda p: p[1] if p[0] == "n" else None, lmap, macros)
             if e["directed"]]                                              # a bare line between two boxes: decoration
    for b in boxes:
        b.pop("_xy")
    return {"nodes": boxes, "edges": edges}
