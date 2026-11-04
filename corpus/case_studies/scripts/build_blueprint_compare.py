"""Side-by-side page: a paper's SARANGA results view next to its Lean blueprint.

One standalone HTML page per case (the Saranga-only pages are untouched):
left, the paper's results view (results_view.json of the case study); right,
the blueprint's statements that its main theorem rests on, proofs folded into
the result they prove, transitively reduced. Aligned statements are drawn in
their type colour on both sides; a blueprint statement with no counterpart in
the paper is grey, with a badge saying where the paper has it (inside a
proof, folklore never stated, cited and only applied). Clicking a box
highlights its counterpart and shows the alignment note.

    python3 corpus/case_studies/scripts/build_blueprint_compare.py pfr viazovska

PFR uses the hand alignment (blueprint_manual_alignment.json). Viazovska uses
the automatic alignment of scripts/gold_candidates/score_bp_papers.align
(quoted number, then statement similarity), with the number matches marked
as checked and the text matches as unverified.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "src"), str(REPO / "src/LLMVersion"), str(REPO / "scripts/gold_candidates")]
import graph_score as GS                      # noqa: E402
import latex_facts                            # noqa: E402
from score_bp_papers import align, _NUM       # noqa: E402

CASES = REPO / "case_studies" if (REPO / "case_studies").is_dir() else REPO / "corpus/case_studies"
BP = REPO / "corpus/gold_blueprints"
LIB = Path.home() / ".cache/saranga_graph_view/lib"
COLORS = {"theorem": ("#C0392B", "#FADBD8"), "lemma": ("#D35400", "#F5CBA7"), "proposition": ("#B03A2E", "#FADBD8"),
          "corollary": ("#943126", "#F2D7D5"), "claim": ("#E74C3C", "#FDEDEC"), "definition": ("#27AE60", "#D5F5E3"),
          "conjecture": ("#B9770E", "#FCF3CF"), "remark": ("#117A65", "#A2D9CE")}
GREY = ("#7F8C8D", "#ECEFF1")
STATUS = {"node": "", "inside": "stated inside a proof", "implicit": "folklore, never stated", "cited": "cited, only applied",
          "auto": "text match, unverified", "none": "no counterpart"}

CONFIG = {
    "pfr": dict(
        case="pfr_2023", title="On a conjecture of Marton (PFR), Gowers, Green, Manners, Tao 2023",
        paper=REPO / "corpus/silver/opus-5.5__v7_cases/pfr_2023.json", bp=BP / "teorth__pfr", bp_main="T10",
        bp_name="teorth/pfr blueprint (C = 12 theorem `pfr`)", manual="blueprint_manual_alignment.json",
        notes=["The blueprint proves the C = 12 theorem from 84 statements on a chain of 17; the paper states 28 results on a chain of 9.",
               "22 blueprint lemmas are inequalities the paper proves inside a proof: first-fibre, first-cond, dist-sums, key-ident (U+V+W=0), tau-min.",
               "6 are results the paper cites and applies: Tao's 100% inverse theorem (proved from a symmetry group), the Ruzsa covering lemma.",
               "13 are folklore never written down: the definition of entropy, d >= 0, copies preserve entropy, subadditivity, the concavity behind Jensen.",
               "Where both sides state a statement, 47 of the blueprint's 60 dependencies are edges of the paper graph and 49 are paths (82%)."]),
    "viazovska": dict(
        case="viazovska_2016", title="The sphere packing problem in dimension 8, Viazovska 2016",
        paper=REPO / "corpus/silver/opus-5.5__v7_cases/viazovska_2016.json", bp=BP / "thefundamentaltheor3m__Sphere-Packing-Lean",
        bp_main="C2", bp_name="Sphere-Packing-Lean blueprint (`MainTheorem`)", manual=None,
        # The automatic alignment checked by hand against the two sources (2026-11-04): `checked` pairs are
        # right (blueprint id -> paper id), `drop` pairs are wrong; what is left of the automatic pairs stays "auto".
        checked={"T10": "TP8", "T19": "TP12", "T9": "TP7", "C1": "TP4", "C2": "TP4", "P5": "PrP1", "P6": "PrP1", "P7": "PrP2",
                 "P8": "PrP3", "P9": "PrP4", "P10": "PrP5", "P11": "PrP5", "P12": "PrP6", "P13": "PrP7", "P14": "PrP8",
                 "L15": "ClP5", "L21": "ClP9", "L22": "ClP10", "T13": "ClP11", "L26": "ClP13", "L27": "ClP15", "L19": "ClP16",
                 "L32": "ClP17", "L35": "ClP18", "L45": "ClP33", "L39": "ClP25", "L10": "ClP3", "D13": "DP10", "D14": "DP12",
                 "D1": "DP2", "D15": "DP19", "D16": "DP20", "D18": "DP22", "D19": "DP23", "D21": "DP26", "D23": "DP27",
                 "D25": "DP29", "D20": "DP32", "D29": "DP35", "D30": "DP36", "D32": "DP39", "D8": "DP4", "D33": "DP40",
                 "D2": "DP5", "D3": "DP6", "D4": "DP7", "D10": "DP8", "D12": "DP9"},
        drop={"L30", "C7", "T8", "L31", "L25", "C12", "T18", "L37", "L23", "C6", "C11", "C3", "T7", "L6", "L51", "C15", "D27",
              "D31", "L13", "D24", "T15", "D22", "L40", "T16", "D26", "D11", "P1", "Rm2", "L8", "L14", "C13", "L9", "T1", "D9"},
        notes=["The blueprint has 141 statements, 94 of them under MainTheorem; the paper has 12 numbered results.",
               "Theorem 2 (Cohn-Elkies) is cited in the paper and proved in the blueprint, from Poisson summation.",
               "Theorem 1 becomes five blueprint nodes: Cohn-Elkies for periodic packings, periodic packings suffice, the E8 bound, MainTheorem, and the E8 density pi^4/384, which the paper only asserts.",
               "The interval-arithmetic check of A(t) < 0, B(t) > 0 is replaced by an analytic proof via modular differential equations and Serre derivatives.",
               "The automatic alignment pairs numbered results reliably; the text matches (marked unverified) are right about half the time."]),
}


def fold_blueprint(bp):
    """Statements and the dependencies among them, proofs folded into the result they prove."""
    nodes = {n["id"]: n for n in bp["nodes"]}
    proves = {e["source"]: e["target"] for e in bp["edges"] if e["type"] == "proves"}
    deps = defaultdict(set)
    for e in bp["edges"]:
        if e["type"] != "uses":
            continue
        s, t = e["source"], e["target"]
        s = proves.get(s, s)
        t = proves.get(t, t)
        if s != t and nodes[s]["type"] != "proof" and nodes[t]["type"] != "proof":
            deps[t].add(s)
    return nodes, deps


def ancestors(deps, root):
    keep, stack = {root}, [root]
    while stack:
        for p in deps.get(stack.pop(), ()):
            if p not in keep:
                keep.add(p)
                stack.append(p)
    return keep


def reduce_edges(deps, keep):
    """Transitive reduction of the dependencies among `keep`."""
    sub = {k: {p for p in deps.get(k, ()) if p in keep} for k in keep}
    reach = {}

    def r(x):
        if x not in reach:
            reach[x] = set()
            for p in sub[x]:
                reach[x] |= {p} | r(p)
        return reach[x]
    out = []
    for k in keep:
        for p in sub[k]:
            if not any(p in r(q) for q in sub[k] if q != p):
                out.append((p, k))
    return out


def short(s, n=120):
    s = re.sub(r"\s+", " ", (s or "")).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def disp(n):
    """Box head of a paper node: its paper number (Thm 1.2) or its id."""
    t = {"theorem": "Thm", "lemma": "Lem", "proposition": "Prop", "corollary": "Cor", "claim": "Cl", "definition": "Def",
         "conjecture": "Conj", "remark": "Rem"}.get(n.get("type"), n.get("type", ""))
    num = n.get("number") or (n.get("label") or "").replace("Theorem ", "").replace("Proposition ", "") if n.get("label", "").startswith(("Theorem", "Proposition")) else n.get("number")
    return f"{t} {num}" if num else n["id"]


def build(key):
    c = CONFIG[key]
    case = CASES / c["case"]
    paper = json.loads(c["paper"].read_text(encoding="utf-8"))
    pby = {n["id"]: n for n in paper["nodes"]}
    rv = json.loads((case / "results_view.json").read_text(encoding="utf-8"))
    bp = json.loads((c["bp"] / "graph.json").read_text(encoding="utf-8"))
    bnodes, bdeps = fold_blueprint(bp)
    keep = {i for i in ancestors(bdeps, c["bp_main"]) if bnodes[i]["type"] not in ("proof", "definition", "remark")}
    bedges = reduce_edges(bdeps, keep)

    # Alignment: blueprint id -> (paper id or None, status, note)
    al = {}
    if c["manual"]:
        rows = json.loads((case / c["manual"]).read_text(encoding="utf-8"))["rows"]
        for bid, _t, _name, _lab, _sec, status, pid, note in rows:
            al[bid] = (pid, status, note or "")
    else:
        tex = latex_facts.read_tex(str(case / "paper.tex"))
        results = [n for n in bp["nodes"] if n.get("type") not in GS._NOT_RESULTS]
        auto, _ = align(results, paper, tex, 0.5)
        for bid, pid in auto.items():
            if bid in c.get("drop", ()):
                continue
            al[bid] = (pid, "auto", "matched by statement text (unverified)")
        for bid, pid in c.get("checked", {}).items():
            al[bid] = (pid, "node", "checked by hand")
    counterpart = defaultdict(list)
    for bid, (pid, st_, _n) in al.items():
        if pid and st_ in ("node", "auto"):
            counterpart[pid].append(bid)

    # Paper side: the results view as it is.
    pv_ids = {n["id"] for n in rv["nodes"]}
    left_nodes = []
    for n in rv["nodes"]:
        full = pby.get(n["id"], n)
        cps = counterpart.get(n["id"], [])
        left_nodes.append({"id": n["id"], "type": n["type"], "head": disp(full) if not n.get("label") else n["label"],
                           "name": short(full.get("name") or n.get("name") or "", 90),
                           "stmt": short(full.get("statement") or "", 400), "origin": full.get("origin", "paper"),
                           "main": bool(n.get("main")), "aligned": bool(cps), "cp": cps,
                           "note": "; ".join(f"{bnodes[b].get('label') or b}" for b in cps)})
    left_edges = [{"s": e["source"], "t": e["target"], "implied": bool(e.get("implied_by_others"))}
                  for e in rv["edges"] if e["source"] in pv_ids and e["target"] in pv_ids]

    # Blueprint side.
    right_nodes = []
    for bid in sorted(keep):
        n = bnodes[bid]
        pid, status, note = al.get(bid, (None, "none", ""))
        in_view = pid in pv_ids
        right_nodes.append({"id": bid, "type": n["type"], "head": n.get("label") or bid,
                            "name": short(n.get("name") or "", 90), "stmt": short(n.get("statement") or "", 400),
                            "main": bid == c["bp_main"], "aligned": status in ("node", "auto") and bool(pid), "cp": [pid] if in_view else [],
                            "status": status, "badge": STATUS.get(status, status),
                            "note": (f"paper node {pid}" + ("" if in_view else " (not in the results view)") + (f": {note}" if note else "")) if pid else (note or STATUS["none"])})
    right_edges = [{"s": s, "t": t, "implied": False} for s, t in bedges]

    n_al = sum(1 for n in right_nodes if n["aligned"])
    for n in right_nodes:                       # the paper has it, but not as a result of its own: say where
        if n["status"] in ("inside", "implicit", "cited") and not n["aligned"]:
            pass
    st = defaultdict(int)
    for n in right_nodes:
        st[n["status"]] += 1
    model = {"title": c["title"], "left": {"name": "SARANGA results view (LLM extraction, v7)", "nodes": left_nodes, "edges": left_edges},
             "right": {"name": c["bp_name"], "nodes": right_nodes, "edges": right_edges},
             "stats": {"paper_results": len(left_nodes), "paper_deps": len(left_edges), "bp_statements": len(right_nodes),
                       "bp_deps": len(right_edges), "aligned": n_al, "status": dict(st)},
             "notes": c["notes"], "colors": COLORS, "grey": GREY}
    out = case / f"{c['case']}_vs_blueprint.html"
    out.write_text(render(model), encoding="utf-8")
    print(f"{out}: paper {len(left_nodes)} results / {len(left_edges)} deps; blueprint {len(right_nodes)} statements / "
          f"{len(right_edges)} deps; aligned {n_al}; status {dict(st)}")


def render(model):
    libs = "".join(f"<script>{(LIB / f).read_text(encoding='utf-8')}</script>\n" for f in ("cytoscape.min.js", "elk.bundled.js"))
    data = json.dumps(model, ensure_ascii=True).replace("</", "<\\/")
    return TEMPLATE.replace("{{LIBS}}", libs).replace("{{DATA}}", data).replace("{{TITLE}}", model["title"])


TEMPLATE = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}: paper vs Lean blueprint</title>
<style>
 body { margin: 0; overflow: hidden; font-family: Segoe UI, Helvetica, Arial, sans-serif; color: #1d1d1d; background: #fff; }
 header { background: #263238; color: #fff; padding: 8px 14px; }
 header h1 { font-size: 17px; margin: 0 0 4px; font-weight: 600; }
 header .sub { font-size: 12.5px; color: #CFD8DC; }
 #bar { display: flex; gap: 18px; align-items: center; padding: 6px 14px; font-size: 12.5px; background: #ECEFF1; border-bottom: 1px solid #B0BEC5; flex-wrap: wrap; }
 .sw { display: inline-block; width: 12px; height: 12px; border: 1.5px solid #555; vertical-align: -2px; margin-right: 4px; border-radius: 2px; }
 #panes { display: flex; height: calc(100vh - 175px); }
 .pane { flex: 1; position: relative; border-right: 1px solid #B0BEC5; }
 .pane:last-child { border-right: 0; }
 .pane .cap { position: absolute; top: 6px; left: 10px; z-index: 5; background: rgba(255,255,255,.92); padding: 3px 8px; font-size: 13px; font-weight: 600; border: 1px solid #B0BEC5; border-radius: 4px; }
 .pane .cy { position: absolute; inset: 0; }
 #info { height: 70px; overflow: auto; padding: 6px 14px; font-size: 13px; border-top: 1px solid #B0BEC5; background: #FAFAFA; }
 #notes { display: none; position: absolute; right: 14px; top: 58px; width: 440px; background: #fff; border: 1px solid #90A4AE; border-radius: 6px; padding: 8px 12px 8px 26px; font-size: 12.5px; z-index: 9; box-shadow: 0 3px 12px rgba(0,0,0,.2); }
 #notes li { margin: 3px 0; }
 button { font-size: 12px; padding: 2px 8px; }
</style></head><body>
<header><h1>{{TITLE}}</h1><div class="sub" id="sub"></div></header>
<div id="bar"></div>
<ul id="notes"></ul>
<div id="panes">
 <div class="pane"><div class="cap" id="capL"></div><div class="cy" id="cyL"></div></div>
 <div class="pane"><div class="cap" id="capR"></div><div class="cy" id="cyR"></div></div>
</div>
<div id="info">Click a box: its counterpart on the other side lights up, and the alignment note shows here. Boxes in colour are statements both sides have; grey boxes on the right are blueprint statements the paper does not state as a result, with a badge saying where the paper has them.</div>
{{LIBS}}
<script id="data" type="application/json">{{DATA}}</script>
<script>
(function () {
  var M = JSON.parse(document.getElementById('data').textContent);
  var S = M.stats;
  document.getElementById('sub').textContent = 'Paper: ' + S.paper_results + ' results, ' + S.paper_deps + ' dependencies.  Blueprint: ' +
    S.bp_statements + ' statements under its main theorem, ' + S.bp_deps + ' dependencies (proofs folded, transitively reduced).  Aligned: ' + S.aligned + ' blueprint statements have a paper counterpart.';
  var bar = document.getElementById('bar');
  function sw(c, t) { return '<span><span class="sw" style="background:' + c + '"></span>' + t + '</span>'; }
  var st = S.status || {};
  bar.innerHTML = sw(M.colors.theorem[1], 'aligned (colour by type)') + sw(M.grey[1], 'blueprint only') +
    ' <span>badges: ' + ['inside', 'implicit', 'cited', 'auto', 'none'].filter(function (k) { return st[k]; }).map(function (k) {
      return ({inside: 'inside a proof', implicit: 'folklore', cited: 'cited', auto: 'unverified match', none: 'no counterpart'})[k] + ' ' + st[k]; }).join(' · ') + '</span>' +
    ' <span>★ main theorem</span> <button id="nb">What the formalisers made explicit</button> <button id="fit">Fit</button>';
  var notes = document.getElementById('notes');
  notes.innerHTML = M.notes.map(function (t) { return '<li>' + t.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</li>'; }).join('');
  document.getElementById('nb').onclick = function () { notes.style.display = notes.style.display === 'block' ? 'none' : 'block'; };
  document.getElementById('capL').textContent = M.left.name;
  document.getElementById('capR').textContent = M.right.name;

  function lines(s, w) { var words = s.split(' '), n = 1, cur = 0; words.forEach(function (x) { if (cur + x.length + 1 > w) { n++; cur = x.length; } else cur += x.length + 1; }); return n; }
  function els(side) {
    var out = [];
    side.nodes.forEach(function (n) {
      var c = n.aligned ? (M.colors[n.type] || M.grey) : M.grey;
      var head = (n.main ? '★ ' : '') + n.head + (n.name ? ': ' + n.name : '');
      var body = n.badge ? '[' + n.badge + ']' : '';
      var label = head + (body ? '\n' + body : '');
      var w = 190, h = 16 + 13 * lines(head, 30) + (body ? 14 : 0);
      out.push({ group: 'nodes', data: { id: n.id, label: label, hc: c[0], bc: c[1], w: w, h: h, cp: n.cp, note: n.note, stmt: n.stmt, head: head, main: n.main ? 1 : 0, aligned: n.aligned ? 1 : 0 } });
    });
    side.edges.forEach(function (e, i) { out.push({ group: 'edges', classes: e.implied ? 'implied' : '', data: { id: 'e' + i, source: e.s, target: e.t } }); });
    return out;
  }
  var STYLE = [
    { selector: 'node', style: { 'shape': 'round-rectangle', 'width': 'data(w)', 'height': 'data(h)', 'background-color': 'data(bc)', 'border-color': 'data(hc)', 'border-width': 1.5,
      'label': 'data(label)', 'font-size': 10.5, 'text-wrap': 'wrap', 'text-max-width': 180, 'text-valign': 'center', 'text-halign': 'center', 'color': '#1d1d1d' } },
    { selector: 'node[main = 1]', style: { 'border-width': 3.5, 'underlay-color': '#FFD54F', 'underlay-opacity': 0.55, 'underlay-padding': 5 } },
    { selector: 'node[aligned = 0]', style: { 'border-style': 'dashed', 'color': '#455A64' } },
    { selector: 'node.hi', style: { 'overlay-color': '#1E88E5', 'overlay-opacity': 0.25, 'overlay-padding': 8 } },
    { selector: 'node.cp', style: { 'overlay-color': '#43A047', 'overlay-opacity': 0.3, 'overlay-padding': 8 } },
    { selector: 'edge', style: { 'width': 1.4, 'line-color': '#78909C', 'target-arrow-color': '#78909C', 'target-arrow-shape': 'triangle', 'arrow-scale': 0.8, 'curve-style': 'taxi', 'taxi-direction': 'downward' } },
    { selector: 'edge.implied', style: { 'line-style': 'dashed', 'opacity': 0.5 } }
  ];
  var elk = new ELK();
  function make(id, side, otherRef) {
    var cy = cytoscape({ container: document.getElementById(id), elements: els(side), style: STYLE, wheelSensitivity: 0.2 });
    var g = { id: 'root', layoutOptions: { 'elk.algorithm': 'layered', 'elk.direction': 'DOWN', 'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.spacing.nodeNodeBetweenLayers': 40, 'elk.spacing.nodeNode': 18, 'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
      'elk.layered.thoroughness': 7 }, children: [], edges: [] };
    cy.nodes().forEach(function (n) { g.children.push({ id: n.id(), width: n.data('w'), height: n.data('h') }); });
    cy.edges().forEach(function (e) { g.edges.push({ id: e.id(), sources: [e.source().id()], targets: [e.target().id()] }); });
    elk.layout(g).then(function (res) {
      cy.batch(function () { res.children.forEach(function (c) { cy.getElementById(c.id).position({ x: c.x + c.width / 2, y: c.y + c.height / 2 }); }); });
      cy.fit(undefined, 20);
    });
    cy.on('tap', 'node', function (ev) {
      var n = ev.target;
      cy.nodes().removeClass('hi cp'); otherRef.cy.nodes().removeClass('hi cp');
      n.addClass('hi');
      (n.data('cp') || []).forEach(function (c) { var m = otherRef.cy.getElementById(c); if (m.nonempty()) { m.addClass('cp'); otherRef.cy.animate({ center: { eles: m } }, { duration: 300 }); } });
      document.getElementById('info').innerHTML = '<b>' + esc(n.data('head')) + '</b> — ' + esc(n.data('note') || '') + '<br><span style="color:#546E7A">' + esc(n.data('stmt') || '') + '</span>';
    });
    return cy;
  }
  function esc(t) { return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
  var R = {}, L = {};
  L.cy = make('cyL', M.left, R);
  R.cy = make('cyR', M.right, L);
  document.getElementById('fit').onclick = function () { L.cy.fit(undefined, 20); R.cy.fit(undefined, 20); };
})();
</script></body></html>
"""

if __name__ == "__main__":
    for k in (sys.argv[1:] or list(CONFIG)):
        build(k)
