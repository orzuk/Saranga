#!/usr/bin/env python3
"""Build the SARANGA v7 extraction of OAI-165 (The crossing number of complete
bipartite graphs, OpenAI 2026) and run extraction_finalize.finalize on it.

Node choices, spans and edges are hand-decided by reading the prepared source;
this script only slices the chosen spans (by start/end snippets) and assembles JSON.
"""
import json
import re
import sys
from collections import Counter

REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize          # noqa: E402
from latex_facts import read_tex, extract_facts, span_text   # noqa: E402

BASE = REPO + "/corpus/case_studies/ai/openai_165_zarankiewicz_bipartite"
TEX = BASE + "/arxiv_src/paper.tex"
OUT = BASE + "/openai_165_zarankiewicz_bipartite.json"

tex = read_tex(TEX)
facts = extract_facts(tex)
SRC = facts["source"]
F = {f["id"]: f for f in facts["facts"]}


def _rx(snip):
    parts = [re.escape(p) for p in snip.split()]
    return r"\s+".join(parts)


def pos(snip, after=0):
    ms = list(re.finditer(_rx(snip), SRC[after:]))
    if not ms:
        raise ValueError("snippet not found: %r" % snip)
    if after == 0 and len(ms) > 1:
        raise ValueError("snippet not unique (%d): %r" % (len(ms), snip))
    m = ms[0]
    return after + m.start(), after + m.end()


def sp(a, b, after=0):
    """Verbatim span from the start of snippet a through the end of snippet b."""
    s, _ = pos(a, after)
    _, e = pos(b, s)
    return span_text(SRC, s, e)


def sub(stmt, a, b=None):
    """A verbatim sub-span of a statement (whitespace already collapsed)."""
    i = stmt.index(a)
    if b is None:
        return a
    j = stmt.index(b, i) + len(b)
    return stmt[i:j]


nodes, edges = [], []
NODE = {}


def node(id, type, name, statement, section, origin="paper", conf=1.0, **kw):
    n = {"id": id, "type": type, "name": name, "statement": statement,
         "section": section, "origin": origin, "confidence": conf}
    n.update(kw)
    nodes.append(n)
    NODE[id] = n
    return n


def fact_node(id, fid, type, name, section, conf=1.0, **kw):
    return node(id, type, name, F[fid]["statement"], section, conf=conf, **kw)


def E(s, t, type="uses", conf=0.8, basis="inferred", **kw):
    e = {"source": s, "target": t, "type": type, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)


S1 = "1 Introduction"
S2 = "2 A subspace intersection inequality"
S3 = "3 Signed intersections and cycle relations"
S4 = "4 Detecting spoke orders by matrices of full rank"
S5 = "5 The crossing-number formula"
S6 = "5.1 The upper bound"
S7 = "5.2 The lower bound for odd \\texorpdfstring{$n$}{n}"
S8 = "5.3 The even case"
SA = "A Normalization of continuous-arc drawings"
STD = "standard (uncited)"
CROSS_CIT = "standard; point-count convention of Pach & Toth 2000, Fulek et al. 2012"

# ───────────────────────── Section 1: Introduction ─────────────────────────
node("DP1", "definition", "plane drawing",
     sp("For a finite graph $G$, a plane drawing places", "avoids the vertices."), S1,
     origin="external", origin_citation=STD, conf=0.85,
     definiendum="plane drawing", genus="places its vertices at distinct points",
     differentia=["represents each edge by a simple continuous arc whose interior avoids the vertices"])
node("DP2", "definition", "proper crossing",
     sp("A meeting of two edge interiors is a proper crossing", "horizontal and vertical diameters."), S1,
     origin="external", origin_citation=STD, conf=0.85,
     definiendum="proper crossing", genus="meeting of two edge interiors",
     statement_short="A point where two edge interiors meet is a proper crossing if locally homeomorphic to two crossing diameters of a disk.")
node("DP3", "definition", "admissible drawing",
     sp("We require that edge interiors meet at finitely many proper crossings",
        "or common subarcs."), S1, origin="external", origin_citation=STD, conf=0.7,
     definiendum="admissible drawing")
node("DP4", "definition", "crossing count c(D)",
     sp("The number $c(D)$ of a drawing $D$ counts crossing points",
        "each crossing is counted."), S1, origin="external", origin_citation=CROSS_CIT,
     conf=0.85, definiendum="$c(D)$")
node("DP5", "definition", "ordinary crossing number",
     sp("The ordinary crossing number is", "\\mathrm{cr}(G)=\\min_D c(D). \\]"), S1,
     origin="external", origin_citation=CROSS_CIT, conf=0.9,
     definiendum="ordinary crossing number $\\mathrm{cr}(G)$")
node("DP6", "definition", "complete bipartite graph K_{m,n}",
     sp("Let $K_{m,n}$ be the complete bipartite graph with vertex classes",
        "$\\{b_1,\\ldots,b_n\\}$."), S1, origin="external", origin_citation=STD, conf=0.85,
     definiendum="$K_{m,n}$", genus="complete bipartite graph",
     differentia=["vertex classes $\\{a_1,\\ldots,a_m\\}$ and $\\{b_1,\\ldots,b_n\\}$"])
node("DP7", "definition", "Zarankiewicz factor d_r",
     sp("Put \\begin{equation} \\label{eq:dr}", "\\end{equation}"), S1, conf=0.9,
     definiendum="$d_r$",
     statement_short="$d_r=\\lfloor r/2\\rfloor\\lfloor (r-1)/2\\rfloor$, also a sum of two binomials.")
fact_node("EP1", "F1", "equation", "definition of d_r", S1)
abstract_copy = sp("For all positive integers $m,n$, the ordinary crossing", "\\right\\rfloor. \\]")
tp1 = fact_node("TP1", "F2", "theorem", "Zarankiewicz crossing-number formula for K_{m,n}", S1,
                main=True, also_stated_at=[abstract_copy],
                statement_short="The crossing number of $K_{m,n}$ is exactly $d_m d_n$ (Zarankiewicz's conjecture).",
                tags=["crossing_number", "extremal_graph_theory", "identity"])
tp1["assumptions"] = ["For all positive integers $m,n$"]
tp1["conclusions"] = [sub(tp1["statement"], "\\[ \\mathrm{cr}(K_{m,n})", "\\]")]

node("TP2", "theorem", "Kleitman's theorem (min(m,n) <= 6)",
     sp("Kleitman established the exact formula", "\\cite{Kleitman1970}."), S1,
     origin="external", origin_citation="Kleitman 1970", conf=0.7,
     assumptions=["when one vertex class has at most six vertices"],
     conclusions=["the exact formula"],
     statement_short="Zarankiewicz's formula holds when one vertex class has at most six vertices.")
node("TP3", "theorem", "Woodall's computation of cr(K_{7,7}) and cr(K_{7,9})",
     sp("Woodall developed this approach through cyclic-order graphs", "\\cite{Woodall1993}."), S1,
     origin="external", origin_citation="Woodall 1993", conf=0.65,
     conclusions=["verified the cases $K_{7,7}$ and $K_{7,9}$ by computation"])
node("TP4", "theorem", "Balogh-Lidicky-Norin-Pfender-Salazar-Spiro flag-algebra bound",
     sp("For balanced graphs, Balogh, Lidick", "\\cite{Razborov2007,BaloghEtAl2023}."), S1,
     origin="external", origin_citation="Balogh, Lidicky, Norin, Pfender, Salazar, Spiro 2023", conf=0.75,
     conclusions=["\\[ \\operatorname{cr}(K_{n,n})\\ge0.9118\\,d_n^2+o(n^4) \\]"],
     statement_short="Asymptotic lower bound $\\mathrm{cr}(K_{n,n})\\ge 0.9118 d_n^2+o(n^4)$ via flag algebras.",
     tags=["bound", "asymptotic"])
intro_sub_copy = sp("In Section~\\ref{sec:subspaces}, we prove that subspaces", "\\end{equation}")
node("DP8", "definition", "half comparison-sign matrix S_prec",
     sp("For a linear order $\\prec$ on $\\{1,\\ldots,n\\}$, let", "$0$ if $p=q$."), S1, conf=0.8,
     definiendum="$S_\\prec$", genus="half its comparison-sign matrix",
     differentia=["its $(p,q)$ entry is $\\tfrac12$ if $p\\prec q$, $-\\tfrac12$ if $q\\prec p$, and $0$ if $p=q$"])

# Proof sketch of Theorem 1.1 in the introduction
node("PP1", "proof", "Proof outline of Theorem 1.1",
     sp("To connect these statements, normalize a minimum drawing",
        "gives the matching upper bound."), S1, conf=0.7, rigor="semi_formal", proves="TP1",
     proof_strategy=["algebraic_manipulation", "direct"],
     statement_short="Outline: signed-intersection matrix $J$ of a normalized drawing, blocks additive by cycle pairing; the rank detector and the rank-sum corollary give $c(D)\\ge d_md_n$.")
STEPS = []


def step(id, parent, order, name, statement, sub, short, conf=0.75):
    p = NODE[parent]
    while p["type"] == "proof_step":
        p = NODE[p["parent_id"]]
    n = node(id, "proof_step", name, statement, p["section"], origin=p["origin"], conf=conf,
             parent_id=parent, step_order=order, subclass=sub, statement_short=short)
    STEPS.append(id)
    return n


_ps = [0]


def ps():
    _ps[0] += 1
    return "PSP%d" % _ps[0]


def steps(parent, specs):
    """specs: list of (name, a, b, subclass, short[, conf][, children])."""
    out = []
    for k, spec in enumerate(specs, 1):
        name, a, b, sc, short = spec[:5]
        conf = 0.75
        kids = None
        for extra in spec[5:]:
            if isinstance(extra, list):
                kids = extra
            else:
                conf = extra
        sid = ps()
        anchor = SPAN_START.get(parent, 0)
        st = sp(a, b, after=anchor)
        s0, _ = pos(a, anchor)
        SPAN_START[sid] = s0
        step(sid, parent, k, name, st, sc, short, conf)
        out.append(sid)
        if kids:
            steps(sid, kids)
    return out


SPAN_START = {}


def anchor_of(nid, snip):
    SPAN_START[nid] = pos(snip)[0]


anchor_of("PP1", "To connect these statements, normalize a minimum drawing")
sk = steps("PP1", [
    ("normalize the drawing and read spoke orders", "To connect these statements, normalize",
     "from a chosen gap.", "setup", "Normalize a minimum drawing, orient edges, read the spoke order at each vertex."),
    ("form the matrix J", "Form a matrix $J$ indexed by these edges.", "to those incident with $a_k$.",
     "introduce_variable", "Define $J$: signed crossing counts plus half order signs at common endpoints."),
    ("blocks additive", "The vanishing of algebraic intersections of closed plane curves",
     "(Section~\\ref{sec:intersections}).", "apply_lemma", "Blocks are additive modulo row-plus-column terms."),
    ("apply the linear map", "Applying the linear map produces", "by the corresponding crossing counts.",
     "apply_lemma", "Detector map gives full-rank diagonal blocks, off-diagonal ranks bounded by crossings."),
    ("rank-sum bound", "Corollary~\\ref{cor:rank-sum} bounds the ordered sum", "This gives $c(D)\\ge d_m d_n$.",
     "bound_estimate", "Rank sum $\\ge 2d_md_n$ and $\\le 2c(D)$."),
    ("even case and upper bound", "Section~\\ref{sec:formula} completes the proof:",
     "gives the matching upper bound.", "conclude", "Vertex deletion for even n; axis drawing for the upper bound."),
])

# ───────────────────────── Section 2 ─────────────────────────
lp1 = fact_node("LP1", "F4", "lemma", "Subspace intersection bound", S2, main=True,
                also_stated_at=[intro_sub_copy],
                statement_short="If $U_i\\cap V_i=0$ for all $i$, then $\\sum_{i,j}\\dim(U_i\\cap V_j)\\le\\lfloor m^2/4\\rfloor N$.",
                tags=["linear_algebra", "bound", "subspaces"])
lp1["assumptions"] = [sub(lp1["statement"], "Let $W$ be a real vector space of dimension $N$", "where $m\\geq1$"),
                      "$U_i\\cap V_i=\\{0\\}$ for every $i$"]
lp1["conclusions"] = [sub(lp1["statement"], "\\begin{equation}", "\\end{equation}")]
fact_node("EP2", "F5", "equation", "subspace intersection bound (2.1)", S2)
fact_node("PP2", "F6", "proof", "Proof of Lemma 2.1", S2,
          proof_strategy=["algebraic_manipulation", "direct"],
          statement_short="Polynomial interpolation with subspace constraints at nodes $t_i$: a minor of the evaluation matrix vanishes to order $k_h(V_j)$ at each node; comparing with its degree and summing over the filtration gives the bound.")
anchor_of("PP2", "We encode the subspaces by polynomial evaluation constraints.")
steps("PP2", [
    ("overview and constrained polynomial spaces", "We encode the subspaces by polynomial", "k_{-1}(Z)=0. \\]",
     "setup", "Plan of the proof; define $\\mathcal P_h(Z)$, $E_h(Z;t)$ and $k_h(Z)$.", [
         ("plan", "We encode the subspaces by polynomial", "will give the bound.", "setup",
          "Outline: evaluation filtration, rank loss at nodes, minor vanishing order vs degree."),
         ("define P_h, E_h, k_h", "Choose distinct real numbers $t_1,\\ldots,t_m$.", "k_{-1}(Z)=0. \\]",
          "introduce_variable", "Define node-constrained polynomial spaces, their evaluations and increments $k_h$."),
     ]),
    ("Evaluation away from the nodes", "\\emph{Evaluation away from the nodes.}", "\\sum_{i=1}^{m}\\dim(U_i\\cap Z). \\end{equation}",
     "other", "Evaluation at a non-node has dimension $k_h(Z)$; evaluation at all nodes gives (2.3).", 0.95, [
         ("kernel of evaluation", "For $t\\notin\\{t_1,\\ldots,t_m\\}$, the kernel", "\\end{equation}",
          "algebraic_manipulation", "Kernel of evaluation at a non-node is $(\\xi-t)\\mathcal P_{h-1}$, giving (2.2)."),
         ("Lagrange isomorphism", "Also, evaluation at all $m$ nodes is an isomorphism",
          "\\sum_{i=1}^{m}\\dim(U_i\\cap Z). \\end{equation}", "invoke_identity",
          "Lagrange interpolation identifies $\\mathcal P_{m-1}(Z)$ with $\\bigoplus_i(U_i\\cap Z)$, giving (2.3)."),
     ]),
    ("Polynomial minors of controlled degree", "\\emph{Polynomial minors of controlled degree.}",
     "use the empty determinant $\\Delta_h=1$.", "other",
     "Build a polynomial matrix $M_h$ with a nonvanishing minor $\\Delta_h$ of degree $\\le\\sum e\\ell_e$.", 0.95, [
         ("increments l_h", "Fix $t_*$ outside the nodes.", "(0\\leq h\\leq m-1). \\]", "introduce_variable",
          "Nested evaluation spaces give nonnegative increments $\\ell_h$."),
         ("choose columns and minor", "At stage $h$, choose $\\ell_h$ polynomials", "with $\\Delta_h(t_*)\\ne0$.",
          "introduce_variable", "Choose polynomial columns stage by stage and a minor $\\Delta_h$ nonzero at $t_*$."),
         ("degree of minor", "Each column introduced at stage $e$ has degree at most $e$.",
          "use the empty determinant $\\Delta_h=1$.", "bound_estimate", "Degree bound (2.4) for $\\Delta_h$."),
     ]),
    ("Rank loss at the nodes", "\\emph{Rank loss at the nodes.}", "k_h(V_j)\\leq\\sum_{e=0}^{h}e\\ell_e. \\end{equation}", "other",
     "At each node $t_j$ the minor loses rank $k_h(V_j)$, so $\\Delta_h$ is divisible by $(\\xi-t_j)^{k_h(V_j)}$; gives (2.6).", 0.95, [
         ("claim (2.5)", "For each $j$ we claim that", "This proves \\eqref{eq:node-rank}.", "bound_estimate",
          "Claim: $\\dim E_h(W;t_j)\\le k_h(W)-k_h(V_j)$.", [
              ("quotient bound at non-nodes", "Let $\\pi_j:W\\longrightarrow W/V_j$ be the quotient map.",
               "\\leq k_h(W)-k_h(V_j). \\]", "bound_estimate", "Project by $W\\to W/V_j$; bound the image at non-nodes."),
              ("pass to the node", "To pass to $t_j$, take a fixed basis", "obeys the same bound.",
               "other", "Minors vanishing at infinitely many points vanish identically, so the bound holds at $t_j$."),
              ("injectivity on U_j", "But $E_h(W;t_j)\\subseteq U_j$", "This proves \\eqref{eq:node-rank}.",
               "conclude", "$\\pi_j$ is injective on $U_j$ since $U_j\\cap V_j=0$."),
          ]),
         ("rank deficiency of the minor", "The chosen columns of $M_h(t_j)$ lie in",
          "at least $k_h(V_j)$ at $t_j$.", "bound_estimate", "The minor's submatrix has deficiency $\\ge k_h(V_j)$ at $t_j$."),
         ("vanishing order", "A square polynomial matrix with deficiency", "\\quad\\text{divides }\\Delta_h(\\xi). \\]",
          "algebraic_manipulation", "Rank deficiency $q$ at $t_j$ gives a factor $(\\xi-t_j)^q$ of the determinant."),
         ("multiplicity budget", "For $r_h=0$, all $k_h(V_j)$ are zero", "\\end{equation}", "bound_estimate",
          "Compare vanishing order with degree: (2.6)."),
     ]),
    ("Summing the degree bounds", "\\emph{Summing the degree bounds.}", "\\leq N$.", "conclude",
     "Sum (2.6) over $h$, use (2.3) and $e(m-e)\\le\\lfloor m^2/4\\rfloor$.", 0.95),
])
for fid, eid, nm in [("F7", "EP3", "evaluation dimension away from nodes (2.2)"),
                     ("F8", "EP4", "filtration sum identity (2.3)"),
                     ("F9", "EP5", "degree bound for the minor (2.4)"),
                     ("F10", "EP6", "rank bound at the nodes (2.5)"),
                     ("F11", "EP7", "multiplicity budget (2.6)")]:
    fact_node(eid, fid, "equation", nm, S2)
fact_node("RP1", "F13", "remark", "Sharpness of the subspace intersection bound", S2,
          statement_short="Splitting $W=P\\oplus Q$ and the indices into two halves attains $\\lfloor m^2/4\\rfloor N$.")
cp1 = fact_node("CP1", "F14", "corollary", "Rank sum for differences", S2,
                statement_short="If every $X_i-Y_i$ is invertible ($d\\times d$), then $\\sum_{i\\ne j}\\mathrm{rank}(X_i-Y_j)\\ge 2d_m d$.",
                tags=["linear_algebra", "bound", "rank"])
cp1["assumptions"] = [sub(cp1["statement"], "Let $X_1,\\ldots,X_m,Y_1,\\ldots,Y_m$ be real $d\\times d$ matrices"),
                      "$X_i-Y_i$ is invertible for every $i$"]
cp1["conclusions"] = [sub(cp1["statement"], "\\begin{equation}", "\\end{equation}"),
                      "The sum is over ordered pairs of distinct indices."]
fact_node("EP8", "F15", "equation", "rank sum inequality (2.7)", S2)
fact_node("PP3", "F16", "proof", "Proof of Corollary 2.3", S2, proof_strategy=["direct"],
          statement_short="Apply Lemma 2.1 to the graphs of $X_i$ and $Y_j$ in $\\mathbb R^d\\oplus\\mathbb R^d$ and remove the diagonal terms.")
anchor_of("PP3", "In $W=\\mathbb R^d\\oplus\\mathbb R^d$, let")
steps("PP3", [
    ("graphs of linear maps", "In $W=\\mathbb R^d\\oplus\\mathbb R^d$, let", "\\qquad U_i\\cap V_i=\\{0\\}. \\]",
     "introduce_variable", "Take graph subspaces; $\\dim(U_i\\cap V_j)=d-\\mathrm{rank}(X_i-Y_j)$."),
    ("apply Lemma 2.1", "Lemma~\\ref{lem:subspace}, with $N=2d$, gives", "\\right)d. \\]", "apply_lemma",
     "Lemma 2.1 with $N=2d$ bounds the full rank sum below."),
    ("remove diagonal", "The $m$ diagonal terms each equal $d$.", "=2d_m. \\]", "conclude",
     "Subtract the $m$ diagonal terms; arithmetic gives $2d_m$."),
])

# ───────────────────────── Section 3 ─────────────────────────
node("AssumP1", "assumption", "normalized minimum drawing D",
     sp("Fix a minimum drawing $D$ of $K_{m,n}$.", "having a common endpoint."), S3, conf=0.7,
     statement_short="Fix a minimum drawing, normalized (polygonal, locally straight, no adjacent-edge crossings).")
node("DP9", "definition", "orientation of edge ip",
     sp("Orient the edge $ip$ from $a_i$ to $b_p$.", "from $a_i$ to $b_p$."), S3, conf=0.75,
     definiendum="$ip$")
node("DP10", "definition", "signed intersection I(e,f)",
     sp("For oriented edges $e,f$, let $I(e,f)$", "their interior crossings."), S3, conf=0.85,
     definiendum="$I(e,f)$", genus="the sum of the signs of their interior crossings")
node("DP11", "definition", "positive crossing",
     sp("A crossing is positive when", "positive orientation of the plane."), S3, conf=0.8,
     definiendum="positive crossing")
node("DP12", "definition", "I(e,e)=0 convention",
     sp("Set $I(e,e)=0$.", "Set $I(e,e)=0$."), S3, conf=0.7, definiendum="$I(e,e)$")
node("DP13", "definition", "counterclockwise spoke order at a vertex",
     sp("At a vertex $v$, choose a gap between consecutive", "counterclockwise from that gap."), S3, conf=0.75,
     definiendum="spoke order from a gap")
node("DP14", "definition", "order sign T_v and orientation sign sigma",
     sp("Define \\[ T_v(e,f)=", "\\end{cases} \\]", after=pos("At a vertex $v$, choose a gap")[0]), S3, conf=0.9,
     definiendum=["$T_v(e,f)$", "$\\sigma_{ve}$"],
     statement_short="$T_v(e,f)=\\pm1$ by which edge precedes in the spoke order; $\\sigma_{ve}=\\pm1$ by whether $e$ leaves or enters $v$.")
node("DP15", "definition", "signed-intersection matrix J",
     sp("The matrix indexed by the edges that we use is", "\\end{equation}",
        after=pos("The matrix indexed by the edges that we use is")[0]), S3, conf=0.9,
     definiendum=["$J(e,f)$", "$J^{ik}$"],
     statement_short="$J(e,f)$ = signed crossing count plus half the signed order term at each common endpoint; $J^{ik}$ its $n\\times n$ blocks.")
fact_node("EP9", "F17", "equation", "signed-intersection matrix (3.1)", S3)
lp2 = fact_node("LP2", "F18", "lemma", "Cycle pairing", S3,
                statement_short="For signed edge vectors $z,y$ of any two oriented cycles of $K_{m,n}$, $z^{\\mathsf T}Jy=0$.",
                tags=["topological_graph_theory", "algebraic_intersection", "identity"])
lp2["assumptions"] = [sub(lp2["statement"], "Let $z,y\\in\\mathbb R^{E(K_{m,n})}$", "is $0$ on an unused edge"),
                      "The cycles may share vertices and edges, and may traverse a shared edge in opposite directions."]
lp2["conclusions"] = ["\\begin{equation} z^{\\mathsf T}Jy=0. \\end{equation}"]
fact_node("EP10", "F19", "equation", "cycle pairing identity (3.2)", S3)
fact_node("PP4", "F20", "proof", "Proof of Lemma 3.1", S3, proof_strategy=["geometric", "construction"],
          statement_short="Local chord formula (3.3) explains the half-order term; replace one cycle by a closed walk and the other by left/right shifts, then the total signed intersection of two closed plane walks is zero (coning argument). Averaging the two shifts makes shared spokes cancel.")
anchor_of("PP4", "We first establish the local formula that explains the factor $1/2$.")
steps("PP4", [
    ("local chord formula", "We first establish the local formula", "These are exactly the signed intersection values.",
     "other", "Prove the chord formula (3.3) for signed intersection of two disk chords.", [
         ("chords and formula", "Let $C$ and $E$ be oriented chords", "\\end{equation}", "introduce_variable",
          "Set up two oriented chords, endpoint coefficients and boundary order; state (3.3)."),
         ("cut independence", "Moving the cut past one endpoint", "cut just before the start of $C$.",
          "other", "The right side is independent of the cut; cut before the start of $C$."),
         ("evaluate", "The right-hand side then becomes", "These are exactly the signed intersection values.",
          "conclude", "The sum counts the other chord's endpoints on the right arc: the signed intersection."),
     ]),
    ("figure pointer", "Figure~\\ref{fig:chord-pairing} illustrates the local signs", "used below.",
     "setup", "Figure 1 illustrates the local signs."),
    ("first cycle as closed walk gamma", "Choose small pairwise disjoint round vertex disks",
     "may have self-intersections.", "introduce_variable", "Replace the first cycle's vertex passages by chords: closed walk $\\gamma$."),
    ("shifted walks eta_+-", "For the second cycle construct two closed polygonal walks", "at seams and corners.",
     "introduce_variable", "Construct left/right shifted closed walks $\\eta_\\pm$ of the second cycle.", [
         ("define shifts", "For the second cycle construct two closed polygonal walks", "boundary endpoints by a chord.",
          "introduce_variable", "Shift edge tracks left and right; join by chords in vertex disks."),
         ("explicit tracks", "Here is an explicit construction of", "The right shift uses the other sector.",
          "other", "Explicit shifted tracks through crossing and bend disks."),
         ("no extra intersections", "All remaining distinct truncated straight stretches", "entire construction.",
          "other", "Small enough shifts add no intersections."),
         ("seams and corners", "At vertex-circle seams the two walks'", "at seams and corners.",
          "other", "No contacts at seams or corners."),
     ]),
    ("exterior contribution", "Consequently, in each version the signed intersections",
     "the traversal coefficients $z_e y_f$.", "other", "Outside vertex disks the signed intersections sum to $z^{\\mathsf T}Iy$ (3.4)."),
    ("vertex disk contribution", "Consider a vertex disk used by both cycles.", "the two order signs remain opposite.",
     "other", "Each shared vertex disk contributes the half-order term of $J$.", [
         ("endpoint coefficients", "Consider a vertex disk used by both cycles.", "coefficient is $\\sigma_{vf}y_f$.",
          "setup", "Chord endpoint coefficients are $\\sigma_{ve}z_e$ and $\\sigma_{vf}y_f$."),
         ("comparison signs", "All endpoints belonging to the two different chords", "as required by $T_v(e,e)=0$.",
          "other", "Different spokes compare by $T_v$; a shared spoke's two signs average to 0."),
         ("apply chord formula", "Applying \\eqref{eq:chord-formula} and averaging", "\\sigma_{ve}\\sigma_{vf}T_v(e,f). \\]",
          "invoke_identity", "Chord formula averaged over both shifts gives the local term."),
         ("opposite traversals", "This cancellation for a shared spoke is unaffected", "the two order signs remain opposite.",
          "other", "Opposite traversals do not affect the cancellation."),
     ]),
    ("reduction to zero total", "It remains to show that the total signed intersection", "$(\\gamma,\\eta_\\pm)$ is zero.",
     "setup", "Remains: total signed intersection of $\\gamma$ with $\\eta_\\pm$ is zero."),
    ("closed walks have zero total intersection", "More generally, let two closed polygonal",
     "any unnecessary straight subdivision points can be removed.", "other",
     "Cone each segment of one walk to a point; triangle boundaries have zero intersection with a closed walk.", [
         ("cone construction", "More generally, let two closed polygonal", "also avoid its segment lines.",
          "introduce_variable", "Cone every segment of the first walk to a generic point $o$."),
         ("triangles contribute zero", "The added cone segments meet the second", "the two have opposite signs.",
          "other", "Each triangle boundary meets a closed walk with total sign zero."),
         ("sum triangles", "On summing triangle boundaries", "any unnecessary straight subdivision points can be removed.",
          "conclude", "Cone segments cancel; the walk's total is zero."),
     ]),
    ("conclude", "Finally, average the zero total", "proving \\eqref{eq:cycle-pairing}.", "conclude",
     "Average over $\\eta_\\pm$: exterior plus vertex terms equal $z^{\\mathsf T}Jy=0$."),
])
fact_node("EP11", "F21", "equation", "chord formula (3.3)", S3)
fact_node("EP12", "F22", "equation", "exterior intersections (3.4)", S3)
node("DP16", "definition", "additive matrix space L",
     sp("Let \\begin{equation} \\label{eq:additive-space}", "\\end{equation}"), S3, conf=0.9,
     definiendum="$\\mathcal L$", genus="matrices", differentia=["H(p,q)=r_p+c_q\\text{ for some }r,c\\in\\mathbb R^n"],
     statement_short="$\\mathcal L$: $n\\times n$ matrices of row-plus-column form $r_p+c_q$.")
fact_node("EP13", "F23", "equation", "additive space (3.5)", S3)
lp3 = fact_node("LP3", "F24", "lemma", "Additive block relation", S3,
                statement_short="$J^{ik}-J^{i1}-J^{1k}+J^{11}$ has row-plus-column form.",
                assumptions=["For every $1\\le i,k\\le m$"],
                conclusions=["\\begin{equation} J^{ik}-J^{i1}-J^{1k}+J^{11}\\in\\mathcal L. \\end{equation}"])
fact_node("EP14", "F25", "equation", "additive block relation (3.6)", S3)
fact_node("PP5", "F26", "proof", "Proof of Lemma 3.2", S3, proof_strategy=["direct"],
          statement_short="Apply cycle pairing to two four-cycles through stars $a_i,a_1$ and $a_k,a_1$: all rectangular differences of $H$ vanish.")
anchor_of("PP5", "Write the matrix on the left as $H$.")
steps("PP5", [
    ("fix indices and four-cycles", "Write the matrix on the left as $H$.", "$-1$ on $kq',1q$.", "introduce_variable",
     "Name $H$, fix indices, take two four-cycle vectors."),
    ("apply cycle pairing", "Expanding Lemma~\\ref{lem:cycle-pairing} gives", "H(p',q'). \\]", "apply_lemma",
     "Cycle pairing gives a vanishing rectangular difference of $H$."),
    ("trivial cases", "If any of those index differences is trivial", "differences of $H$ vanish.", "case_split",
     "Degenerate index choices vanish directly; all rectangular differences vanish."),
    ("row-plus-column form", "For any fixed $p_0,q_0$ this says", "row-plus-column form.", "conclude",
     "Vanishing rectangular differences mean $H\\in\\mathcal L$."),
])

# ───────────────────────── Section 4 ─────────────────────────
node("AssumP2", "assumption", "odd n = 2s+1, d = s^2",
     sp("Suppose throughout this section that $n=2s+1$", "$d=s^2=d_n$."), S4, conf=0.75,
     statement_short="Standing assumption for Section 4: $n=2s+1$ odd, $d=s^2=d_n$.")
lp4 = fact_node("LP4", "F27", "lemma", "Two-triangle interpolation", S4,
                statement_short="Bivariate polynomials of degree $<s$ in each variable are determined by values on the two-triangle pattern $Q_s$.",
                tags=["polynomial_interpolation", "uniqueness"])
lp4["assumptions"] = ["For any pairwise distinct real numbers $x_1,\\ldots,x_{2s+1}$"]
lp4["conclusions"] = [sub(lp4["statement"], "The values at $(x_p,x_q)$", "in each variable."),
                      sub(lp4["statement"], "Equivalently, the $s^2$ vectors", "in any fixed order.")]
lp4["equivalent_conditions"] = lp4["conclusions"][:]
fact_node("EP15", "F28", "equation", "two-triangle pattern Q_s (4.1)", S4)
fact_node("PP6", "F29", "proof", "Proof of Lemma 4.1", S4, conf=0.9, proves="LP4",
          proof_strategy=["induction"],
          statement_short="Induction on $s$: a vanishing polynomial is divisible by $(u-x_{s+1})(v-x_1)$, and the quotient vanishes on a relabeled $Q_{s-1}$ after swapping variables.")
anchor_of("PP6", "The polynomial space has dimension $s^2$, and")
steps("PP6", [
    ("dimension count", "The polynomial space has dimension $s^2$, and", "=s^2. \\]", "other",
     "Both the polynomial space and $Q_s$ have size $s^2$."),
    ("reduce to injectivity", "It therefore suffices to show", "is zero.", "setup",
     "Suffices: a polynomial vanishing on $Q_s$ is zero."),
    ("base case", "We prove this by induction on $s$.", "indexed by $(2,1)$.", "induction_step",
     "Induction on $s$; base $s=1$."),
    ("inductive step", "Let $s>1$.", "both assertions.", "induction_step",
     "Factor out $(u-x_{s+1})(v-x_1)$ and apply induction to the swapped quotient.", [
         ("row p=s+1", "Let $s>1$.", "vanishes identically.", "other",
          "$P(x_{s+1},v)$ has $s$ roots, so vanishes."),
         ("divide in u", "Division in the variable $u$ gives", "\\deg_v P_1\\leq s-1. \\]", "algebraic_manipulation",
          "$P=(u-x_{s+1})P_1$."),
         ("column q=1", "For $p=2,\\ldots,s$, the remaining points", "\\end{equation}", "algebraic_manipulation",
          "$P_1(u,x_1)$ vanishes, giving (4.2)."),
         ("remaining triangles", "At every point in the two remaining triangles", "s+2\\leq p<q\\leq2s+1. \\]",
          "other", "$R$ vanishes on the two remaining triangles."),
         ("relabel", "Define a tuple of $2s-1$ distinct nodes", "for the $y$-tuple.", "introduce_variable",
          "Swap variables and relabel nodes: $S$ vanishes on $Q_{s-1}$."),
         ("apply induction", "The induction hypothesis gives $S=0$", "both assertions.", "conclude",
          "Induction gives $S=0$, hence $P=0$."),
     ]),
])
fact_node("EP16", "F30", "equation", "triangle factorization (4.2)", S4)
lp5 = fact_node("LP5", "F31", "lemma", "Rank detector", S4, main=True,
                statement_short="A linear map $\\Phi$ from $n\\times n$ to $s^2\\times s^2$ matrices kills additive and diagonal matrices, sends entries to rank $\\le1$, and every half sign matrix $S_\\prec$ to an invertible matrix.",
                tags=["linear_algebra", "construction", "rank"])
lp5["assumptions"] = [sub(lp5["statement"], "Fix any pairwise distinct real numbers $x_1,\\ldots,x_n$", "$d=s^2$")]
lp5["conclusions"] = [
    sub(lp5["statement"], "There is a linear map", "with the following properties."),
    sub(lp5["statement"], "$\\Phi$ annihilates every additive matrix", "every diagonal matrix."),
    sub(lp5["statement"], "For the coordinate matrix $E_{pq}$", "is zero if $p=q$."),
    sub(lp5["statement"], "For every strict linear order", "\\end{cases} \\]"),
    "The same map has these properties for all orders simultaneously."]
fact_node("PP7", "F32", "proof", "Proof of Lemma 4.2", S4, proof_strategy=["construction", "algebraic_manipulation"],
          statement_short="Define $\\Phi$ by rank-one matrices $B_{pq}$ with barycentric weights; Lagrange vanishing kills additive matrices; for $S_\\prec$, $\\Phi(S)$ factors as $A_QD_QA_Q^{\\mathsf T}$ with $A_Q$ invertible by Lemma 4.1.")
anchor_of("PP7", "Set \\begin{equation} \\label{eq:detector-definition}")
steps("PP7", [
    ("define Phi; property (ii)", "Set \\begin{equation}", "H(p,q)\\ne0\\}\\bigr|. \\end{equation}", "introduce_variable",
     "Define $\\Phi$ via $B_{pq}$; get (ii), diagonal annihilation and the support bound (4.4).", [
         ("definition (4.3)", "Set \\begin{equation}", "\\end{equation}", "introduce_variable",
          "Define $F$, $h_{pq}$, $B_{pq}$ and $\\Phi$."),
         ("barycentric weights", "The factors $1/F'(x_p)$ are the classical barycentric weights",
          "because the nodes are distinct.", "setup", "Weights are barycentric; denominators nonzero."),
         ("rank one and support bound", "The constant coordinate of $h_{pq}$ is $1$",
          "\\end{equation}", "bound_estimate", "$B_{pq}$ rank one off the diagonal, zero on it: (ii) and (4.4)."),
     ]),
    ("Lagrange vanishing identity", "For the additive matrices, we use the elementary identity",
     "proves \\eqref{eq:lagrange-vanishing}.", "invoke_identity", "Prove (4.5) by Lagrange interpolation.", [
         ("state identity", "For the additive matrices, we use the elementary identity", "\\end{equation}",
          "invoke_identity", "State (4.5)."),
         ("Lagrange expansion", "Indeed, the polynomials", "\\frac{F(t)}{(t-x_p)F'(x_p)}. \\]", "algebraic_manipulation",
          "Expand $A$ in the Lagrange basis."),
         ("compare top coefficient", "Comparison of the coefficients of $t^{n-1}$", "proves \\eqref{eq:lagrange-vanishing}.",
          "conclude", "Top coefficient gives (4.5)."),
     ]),
    ("property (i)", "The entry of $B_{pq}$ indexed by", "completing \\textup{(i)}.", "conclude",
     "Row and column sums of $B_{pq}$ vanish by (4.5), so additive matrices are annihilated."),
    ("property (iii) for the natural order", "It remains to prove \\textup{(iii)}.", "so $\\Phi(S)$ is invertible.",
     "other", "Reduce $S$ to $H'$ supported on $Q_s$ and factor $\\Phi(S)=-A_QD_QA_Q^{\\mathsf T}$.", [
         ("remains (iii)", "It remains to prove \\textup{(iii)}.", "\\Phi(S)=-\\Phi(H). \\]", "setup",
          "Natural order: $\\Phi(S)=-\\Phi(H)$ for the strict lower-triangular indicator $H$."),
         ("modify to H'", "Subtract $1$ from each row of $H$", "and $-1$ on the second.", "algebraic_manipulation",
          "Additive modification gives $H'$ supported on $Q_s$."),
         ("A_Q invertible", "List the pairs in $Q_s$ in any order", "$A_Q$ is invertible.", "apply_lemma",
          "Lemma 4.1 makes $A_Q$ invertible."),
         ("factorization", "Equation \\eqref{eq:detector-definition} now gives", "so $\\Phi(S)$ is invertible.",
          "conclude", "Factorization (4.6) with nonzero diagonal $D_Q$."),
     ]),
    ("arbitrary orders", "Finally let $\\pi(1)\\prec\\cdots\\prec\\pi(n)$", "under the original map.", "conclude",
     "Relabeling the nodes reduces any order to the natural one."),
])
for fid, eid, nm in [("F33", "EP17", "detector map definition (4.3)"),
                     ("F34", "EP18", "support rank bound (4.4)"),
                     ("F35", "EP19", "Lagrange vanishing identity (4.5)"),
                     ("F36", "EP20", "detector factorization (4.6)")]:
    fact_node(eid, fid, "equation", nm, S4)

# ───────────────────────── Section 5: proof of Theorem 1.1 ─────────────────────────
node("PP8", "proof", "Proof of Theorem 1.1",
     sp("We now combine the preceding results to prove", "this completes Theorem~\\ref{thm:main}. \\qed"),
     S5, conf=0.9, proves="TP1", proof_strategy=["construction", "algebraic_manipulation", "case_analysis"],
     statement_short="Upper bound by the axis drawing; lower bound for odd $n$ by the rank-sum corollary applied to detector images of the $J$ blocks; even $n$ by vertex deletion.")
anchor_of("PP8", "We now combine the preceding results to prove")
steps("PP8", [
    ("announce", "We now combine the preceding results to prove", "to prove Theorem~\\ref{thm:main}.", "setup",
     "Combine the previous results."),
    ("The upper bound", "\\subsection{The upper bound}", "this already proves equality by nonnegativity.", "other",
     "Axis drawing with $d_md_n$ crossings gives (5.1); equality if $m\\le2$ or $n\\le2$.", 0.95, [
         ("recall axis construction", "We recall the classical axis construction", "\\cite[p.~658]{Woodall1993}.",
          "setup", "Recall the classical (Zarankiewicz) axis construction."),
         ("place vertices", "Place the vertices $a_i$ on the vertical axis", "contained in one open quadrant.",
          "introduce_variable", "Vertices split evenly on the two axes, straight edges."),
         ("count by quadrants", "In a quadrant whose bounding rays", "concur in their interiors.", "bound_estimate",
          "Each quadrant contributes $\\binom u2\\binom v2$; total $d_md_n$."),
         ("general position", "The positions can be chosen to ensure this condition.", "achieves the stated count.",
          "other", "Generic intercepts avoid triple concurrences."),
         ("upper bound (5.1)", "In particular, \\begin{equation}", "this already proves equality by nonnegativity.",
          "conclude", "$\\mathrm{cr}(K_{m,n})\\le d_md_n$; small cases done."),
     ]),
    ("The lower bound for odd n", "\\subsection{The lower bound for odd \\texorpdfstring{$n$}{n}}",
     "for odd $n\\ge3$.", "other", "Detector images of $J$ blocks satisfy the rank-sum corollary; ranks bounded by crossings.", 0.95, [
         ("set up R_ik, X_i, Y_k", "Assume $m\\ge3$ and $n=2s+1\\ge3$", "Y_k=R_{11}-R_{1k}. \\]", "introduce_variable",
          "Normalized minimum drawing; $R_{ik}=\\Phi(J^{ik})$, $X_i$, $Y_k$."),
         ("difference form", "Lemma~\\ref{lem:additive} and the annihilation property", "bound the other block ranks by crossings.",
          "apply_lemma", "Additive relation and annihilation give $R_{ik}=X_i-Y_k$ (5.2)."),
         ("diagonal blocks invertible", "All edges in the star at $a_i$ are oriented outward", "\\end{equation}",
          "apply_lemma", "$J^{ii}=S_\\prec$ for the spoke order at $a_i$, so $\\mathrm{rank}R_{ii}=d$ (5.3)."),
         ("off-diagonal ranks vs crossings", "For $i\\ne k$, let $c_{ik}$ be the number", "the number of nonzero contributions.",
          "bound_estimate", "$\\mathrm{rank}R_{ik}\\le c_{ik}$ by rank subadditivity (5.4)."),
         ("combine", "Corollary~\\ref{cor:rank-sum}, applied to", "for odd $n\\ge3$.", "conclude",
          "$2d_md\\le\\sum\\mathrm{rank}R_{ik}\\le 2c(D)$."),
     ]),
    ("The even case", "\\subsection{The even case}", "this completes Theorem~\\ref{thm:main}. \\qed", "other",
     "Delete each second-class vertex and average the odd-case bound.", 0.95, [
         ("recall vertex-deletion count", "We use the vertex-deletion count appearing in",
          "\\cite[Theorem~1 and Corollary~1.1]{Woodall1993}.", "setup", "Recall the Kleitman/Woodall vertex-deletion count."),
         ("delete vertices", "Let $n>2$ be even", "of the deleted-vertex drawings.", "apply_lemma",
          "Each $K_{m,n-1}$ subdrawing has $\\ge d_md_{n-1}$ crossings; each crossing survives in $n-2$ of them."),
         ("conclude", "Therefore \\[ (n-2)c(D)", "this completes Theorem~\\ref{thm:main}. \\qed", "conclude",
          "$(n-2)c(D)\\ge(n-2)d_md_n$; with (5.1) equality."),
     ]),
])
for fid, eid, nm, sec in [("F37", "EP21", "axis-drawing upper bound (5.1)", S6),
                          ("F38", "EP22", "difference form of detector blocks (5.2)", S7),
                          ("F39", "EP23", "full rank of diagonal blocks (5.3)", S7),
                          ("F40", "EP24", "crossing bound on block ranks (5.4)", S7)]:
    fact_node(eid, fid, "equation", nm, sec)

# ───────────────────────── Appendix A ─────────────────────────
lp6 = fact_node("LP6", "F41", "lemma", "Drawing normalization", SA,
                statement_short="Any admissible drawing can be made polygonal, locally straight, with no adjacent-edge crossings, without adding crossings.",
                tags=["topological_graph_theory", "normalization"])
lp6["assumptions"] = ["An admissible continuous-arc drawing of a finite simple graph"]
lp6["conclusions"] = [sub(lp6["statement"], "can be replaced by a polygonal drawing", "sharing an endpoint."),
                      sub(lp6["statement"], "In particular, a drawing attaining", "these properties.")]
fact_node("PP9", "F42", "proof", "Proof of Lemma A.1", SA, proof_strategy=["construction", "geometric"],
          statement_short="Isolate vertices and crossings in small disks, replace exterior pieces by polygonal arcs and fill disks by chords and spokes; then remove each adjacent-edge crossing by swapping prefixes and deleting loops, which decreases the crossing count.")
anchor_of("PP9", "\\emph{Isolating the marked passages.}")
steps("PP9", [
    ("Isolating the marked passages", "\\emph{Isolating the marked passages.}", "only finitely many times.", "other",
     "Disjoint disks around marks; keep disjoint middle pieces of edges.", 0.95, [
         ("choose disks", "Call the vertices and crossing points", "avoid $D_w$ altogether.", "introduce_variable",
          "Marks and small disjoint disks $D_w$ visited only near marked parameters."),
         ("trim edges", "For an interior mark on $e$, remove", "only finitely many times.", "other",
          "Remove first-to-last visits; middle pieces are disjoint arcs in $\\Omega$."),
     ]),
    ("Replacing the exterior pieces", "\\emph{Replacing the exterior pieces.}", "no resulting exterior pieces meet.",
     "other", "Replace each exterior piece by a simple polygonal arc in a disjoint neighborhood.", 0.95, [
         ("spurs and connection", "The finitely many disjoint compact middle pieces", "lies in $U_P\\cap\\Omega$.",
          "introduce_variable", "Radial spurs connected to the piece within its neighborhood."),
         ("polygonal replacement", "Any continuous path with compact image", "no resulting exterior pieces meet.",
          "other", "Polygonal approximation and loop removal give simple polygonal arcs."),
     ]),
    ("Filling the disks", "\\emph{Filling the disks.}", "It is straight near every vertex and every crossing.",
     "other", "Chords in crossing disks, spokes in vertex disks; result is admissible.", 0.95, [
         ("chords and spokes", "In a crossing disk join each of its two pairs", "different disks are distinct.",
          "introduce_variable", "Straight chords in crossing disks, straight spokes to a new vertex point."),
         ("assemble", "Assemble the spokes, chords, and exterior polygonal", "every vertex and every crossing.",
          "conclude", "Assembled edges are simple, admissible, with no more crossings."),
     ]),
    ("Removing adjacent-edge crossings", "\\emph{Removing adjacent-edge crossings.}", "This proves all asserted properties.",
     "other", "Swap prefixes at an adjacent crossing, delete loops; crossing count decreases.", 0.95, [
         ("swap prefixes", "Suppose two polygonal edges $e=vu$", "exactly once in total to the two new walks.",
          "other", "Swap the prefixes of $e,f$ at the crossing $x$, removing it."),
         ("delete loops", "The walks may have self-intersections.", "between the required endpoints.",
          "other", "Delete closed subwalks to get simple paths."),
         ("admissibility preserved", "We check that this operation preserves admissibility.",
          "with no new crossing or improper meeting.", "other",
          "Loop deletion keeps admissibility and creates no new crossing.", [
              ("old e-f crossings", "At an old crossing of $e$ and", "nor a third edge is present there.",
               "case_split", "Old crossings of $e,f$: tracks in different walks or in one walk."),
              ("third-edge crossings", "Likewise, a crossing with any third edge", "no common subarcs.",
               "other", "Crossings with third edges are visited once and stay straight-through."),
              ("endpoints", "The tracks avoid graph vertices in their interiors", "no new crossing or improper meeting.",
               "conclude", "Simplified paths are admissible edges."),
          ]),
         ("termination", "The crossing at $x$ has been removed and none", "This proves all asserted properties.",
          "conclude", "Crossing count decreases each time, so the process terminates."),
     ]),
])

# ───────────────────────── Edges (passes 1-4; \ref edges are added by finalize) ─────────────────────────
T = "term"
# definitions among themselves
E("DP1", "DP2", conf=0.8, basis=T); E("DP1", "DP3", conf=0.8, basis=T); E("DP2", "DP3", conf=0.85, basis=T)
E("DP1", "DP4", conf=0.8, basis=T); E("DP4", "DP5", conf=0.85, basis=T)
E("DP10", "DP15", conf=0.85, basis=T); E("DP11", "DP10", conf=0.8, basis=T); E("DP12", "DP15", conf=0.75, basis=T)
E("DP13", "DP14", conf=0.85, basis=T); E("DP14", "DP15", conf=0.85, basis=T); E("DP9", "DP15", conf=0.8, basis=T)
E("DP9", "DP10", conf=0.75, basis=T); E("DP7", "AssumP2", conf=0.8, basis=T)
E("DP6", "AssumP1", conf=0.8, basis=T); E("DP5", "AssumP1", conf=0.7, basis=T)
E("DP6", "DP9", conf=0.75, basis=T)
# statements of results
for d in ["DP5", "DP6", "DP7"]:
    E(d, "TP1", conf=0.85, basis=T)
for t in ["TP2", "TP3", "TP4"]:
    E("DP5", t, conf=0.75, basis=T); E("DP6", t, conf=0.75, basis=T)
E("DP7", "TP4", conf=0.8, basis=T)
E("DP7", "CP1", conf=0.8, basis=T)
E("DP6", "LP2", conf=0.8, basis=T); E("DP9", "LP2", conf=0.75, basis=T); E("DP15", "LP2", conf=0.85, basis=T)
E("AssumP1", "LP2", conf=0.7, basis="inferred")
E("DP15", "LP3", conf=0.85, basis=T); E("DP16", "LP3", conf=0.9, basis=T)
E("AssumP2", "LP4", conf=0.65, basis="inferred")
E("DP8", "LP5", conf=0.7, basis=T)
E("DP3", "LP6", conf=0.85, basis=T); E("DP4", "LP6", conf=0.75, basis=T); E("DP5", "LP6", conf=0.8, basis=T)
E("DP1", "LP6", conf=0.75, basis=T)
# mention: Remark 2.2 is about Lemma 2.1 (sharpness), not relying on it
E("LP1", "RP1", conf=0.95, basis=None, mention=True)
# results generalized by the main theorem
E("TP1", "TP2", type="specializes", conf=0.85, basis="inferred")
E("TP1", "TP3", type="specializes", conf=0.8, basis="inferred")
E("TP1", "TP4", type="specializes", conf=0.7, basis="inferred")
# proofs: definitions and results used in arguments
E("DP4", "PP1", conf=0.8, basis=T); E("DP7", "PP1", conf=0.75, basis=T)
E("DP14", "PP4", conf=0.85, basis=T); E("DP10", "PP4", conf=0.85, basis=T); E("DP15", "PP4", conf=0.85, basis=T)
E("DP16", "PP5", conf=0.75, basis=T)
E("DP15", "PP8", conf=0.85, basis=T); E("DP10", "PP8", conf=0.85, basis=T); E("DP4", "PP8", conf=0.85, basis=T)
E("DP5", "PP8", conf=0.8, basis=T); E("DP8", "PP8", conf=0.7, basis=T); E("DP6", "PP8", conf=0.8, basis=T)
E("DP7", "PP8", conf=0.85, basis=T); E("DP3", "PP8", conf=0.75, basis=T)
E("DP8", "PP7", conf=0.75, basis=T)
E("PP1", "TP1", type="proves", conf=0.7, basis="inferred", alternative=True)
E("DP2", "PP9", conf=0.75, basis=T); E("DP3", "PP9", conf=0.8, basis=T)
# inside proofs (pass 4): later steps rely on earlier ones
def chain(*ids, conf=0.75):
    for a, b in zip(ids, ids[1:]):
        E(a, b, conf=conf, basis="inferred")


# Lemma 2.1 proof
nm = lambda name: [n["id"] for n in nodes if n["type"] == "proof_step" and n["name"] == name][0]
E(nm("define P_h, E_h, k_h"), nm("Evaluation away from the nodes"), conf=0.8)
E(nm("Evaluation away from the nodes"), nm("Polynomial minors of controlled degree"), conf=0.75)
E(nm("Polynomial minors of controlled degree"), nm("Rank loss at the nodes"), conf=0.8)
E(nm("Rank loss at the nodes"), nm("Summing the degree bounds"), conf=0.8)
chain(nm("rank deficiency of the minor"), nm("vanishing order"), nm("multiplicity budget"))
E(nm("claim (2.5)"), nm("rank deficiency of the minor"), conf=0.8)
chain(nm("quotient bound at non-nodes"), nm("pass to the node"), nm("injectivity on U_j"))
chain(nm("increments l_h"), nm("choose columns and minor"), nm("degree of minor"))
# Cor 2.3
chain(nm("graphs of linear maps"), nm("apply Lemma 2.1"), nm("remove diagonal"))
# Lemma 3.1
E(nm("local chord formula"), nm("vertex disk contribution"), conf=0.8)
E(nm("first cycle as closed walk gamma"), nm("exterior contribution"), conf=0.75)
E(nm("shifted walks eta_+-"), nm("exterior contribution"), conf=0.75)
E(nm("shifted walks eta_+-"), nm("vertex disk contribution"), conf=0.75)
PP4_LAST = [n["id"] for n in nodes if n.get("parent_id") == "PP4"][-1]
E(nm("exterior contribution"), PP4_LAST, conf=0.8)
E(nm("closed walks have zero total intersection"), PP4_LAST, conf=0.8)
E(nm("vertex disk contribution"), PP4_LAST, conf=0.8)
chain(nm("chords and formula"), nm("cut independence"), nm("evaluate"))
chain(nm("cone construction"), nm("triangles contribute zero"), nm("sum triangles"))
# Lemma 3.2
chain(nm("fix indices and four-cycles"), nm("apply cycle pairing"))
E(nm("apply cycle pairing"), nm("row-plus-column form"), conf=0.8)
E(nm("trivial cases"), nm("row-plus-column form"), conf=0.75)
# Lemma 4.1
chain(nm("dimension count"), nm("reduce to injectivity"))
E(nm("base case"), nm("apply induction"), conf=0.8)
chain(nm("row p=s+1"), nm("divide in u"), nm("column q=1"), nm("remaining triangles"), nm("relabel"), nm("apply induction"))
# Lemma 4.2
E(nm("definition (4.3)"), nm("rank one and support bound"), conf=0.8)
E(nm("Lagrange vanishing identity"), nm("property (i)"), conf=0.85)
E(nm("define Phi; property (ii)"), nm("property (iii) for the natural order"), conf=0.75)
chain(nm("remains (iii)"), nm("modify to H'"), nm("factorization"))
E(nm("A_Q invertible"), nm("factorization"), conf=0.85)
E(nm("property (i)"), nm("modify to H'"), conf=0.75)
E(nm("property (iii) for the natural order"), nm("arbitrary orders"), conf=0.85)
chain(nm("Lagrange expansion"), nm("compare top coefficient"))
# Theorem 1.1 proof
chain(nm("place vertices"), nm("count by quadrants"), nm("general position"), nm("upper bound (5.1)"))
chain(nm("set up R_ik, X_i, Y_k"), nm("difference form"))
E(nm("difference form"), nm("combine"), conf=0.85)
E(nm("diagonal blocks invertible"), nm("combine"), conf=0.85)
E(nm("off-diagonal ranks vs crossings"), nm("combine"), conf=0.85)
E(nm("The lower bound for odd n"), nm("The even case"), conf=0.9, basis="named")  # "by the odd case"
E(nm("The upper bound"), nm("The even case"), conf=0.9, basis="named")  # "the upper bound (5.1)"
chain(nm("delete vertices"), [n["id"] for n in nodes if n["type"] == "proof_step" and n["name"] == "conclude"
                              and n["parent_id"] == nm("The even case")][0])
# Lemma A.1 proof
E(nm("Isolating the marked passages"), nm("Replacing the exterior pieces"), conf=0.8)
E(nm("Replacing the exterior pieces"), nm("Filling the disks"), conf=0.8)
E(nm("Filling the disks"), nm("Removing adjacent-edge crossings"), conf=0.75)
chain(nm("choose disks"), nm("trim edges"))
chain(nm("spurs and connection"), nm("polygonal replacement"))
chain(nm("chords and spokes"), nm("assemble"))
chain(nm("swap prefixes"), nm("delete loops"), nm("admissibility preserved"), nm("termination"))

# Section-5 steps: named results without \ref (pass 1/3)
E("LP5", nm("off-diagonal ranks vs crossings"), conf=0.8, basis="inferred")  # B_pp=0 via (4.3), property (ii)

graph = {
    "metadata": {
        "title": "The crossing number of complete bipartite graphs",
        "arxiv_id": "OAI-165",
        "authors": ["OpenAI"],
        "year": 2026,
        "annotator": "agent-extraction",
        "model": "claude-opus-5-5",
        "effort": "default",
        "prompt_version": "v7-86dcfbecdc4d78a5-f5c7dfe",
        "extraction_date": "2026-11-05",
        "rigor_nonformal_count": sum(1 for n in nodes if "rigor" in n),
        "paper_style": ["theorem_proof"],
        "extraction_notes": [],
        "extraction_comment": "",
    },
    "nodes": nodes,
    "edges": edges,
}
NOTES = graph["metadata"]["extraction_notes"]
NOTES += [
    {"category": "not_extracted", "nodes": ["TP1"],
     "note": "The Zarankiewicz conjecture and Turan's brickyard problem are only named (abstract, introduction), never stated apart from Theorem 1.1, so no conjecture/open_problem node and no resolves edge; the abstract's copy of the formula is in TP1.also_stated_at."},
    {"category": "rule_conflict", "nodes": ["PP1"],
     "note": "The introduction's proof outline is a proof sketch: the sketch rule asks for rigor semi_formal and an alternative proves edge, while the rigor rule excludes proofs; the specific sketch rule was followed."},
    {"category": "boundary_uncertain", "nodes": ["LP1"],
     "note": "Equation (1.2) in the introduction restates Lemma 2.1 (same inequality as (2.1)); treated as a restated copy (LP1.also_stated_at), no node of its own."},
    {"category": "type_uncertain", "nodes": ["EP21"],
     "note": "(5.1), the upper bound from the classical axis (Zarankiewicz) drawing, is kept an equation inside the proof of Theorem 1.1 though it is a result in its own right, referred to later as 'the upper bound'."},
    {"category": "type_uncertain", "nodes": ["LP6"],
     "note": "Lemma A.1 kept origin paper although the appendix calls the adjacent-crossing removal 'a standard ordinary-crossing reduction' [FulekEtAl2012]; only that part is attributed, the continuous-arc normalization is the paper's own."},
    {"category": "unexpected_construct", "nodes": ["PP4", "PP6"],
     "note": "Two TikZ figures sit inside or between proof environments; the figure code is inside PP4's verbatim statement but no step covers it. The proof of Lemma 4.1 follows a figure, so its proves edge to LP4 was set by hand."},
    {"category": "source_problem", "nodes": ["PP9"],
     "note": "latex_facts missed the run-in heading \\emph{Filling the disks.} in the proof of Lemma A.1; it was made a labelled step like the other three headings."},
]

report = finalize(graph, tex)
print(json.dumps({k: v for k, v in report.items() if k not in ("warnings",)}, indent=1, default=str)[:6000])
print("WARNINGS (%d):" % len(report["warnings"]))
for w in report["warnings"]:
    print(" -", w)
assert not report["errors"], report["errors"]
graph["metadata"]["rigor_nonformal_count"] = sum(1 for n in graph["nodes"] if "rigor" in n)
with open(OUT, "w") as fh:
    json.dump(graph, fh, indent=1, ensure_ascii=False)
print("nodes", Counter(n["type"] for n in graph["nodes"]))
print("edges", Counter(e["type"] for e in graph["edges"]))
print("wrote", OUT)
