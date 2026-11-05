#!/usr/bin/env python3
"""Build the v7 LLM extraction of OAI-156, 'A nine-dimensional counterexample to Borsuk's covering assertion'
(OpenAI math release). Nodes, types, spans and edges were chosen by reading the paper; this script only
slices the chosen spans out of the prepared source, assembles the graph and runs finalize().
Usage: python3 build_156.py [--write]"""
import json, re, sys, subprocess, os
REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize
from latex_facts import read_tex

SCR = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_156"
CASE = REPO + "/corpus/case_studies/ai/openai_156_borsuk_nine"
TEX = CASE + "/arxiv_src/main.tex"
OUT = CASE + "/openai_156_borsuk_nine.json"
os.makedirs(SCR, exist_ok=True)
if not os.path.exists(SCR + "/facts.json"):
    subprocess.run([sys.executable, REPO + "/src/latex_facts.py", TEX, "--out", SCR + "/facts.json"], check=True)
facts = json.load(open(SCR + "/facts.json"))
S = facts["source"]
F = {f["id"]: f for f in facts["facts"]}
SECS = [s for s in facts["sections"] if s.get("inside") is None]


def norm(t):
    return re.sub(r"\s+", " ", t).strip()


def sec_at(pos):
    s = max((x for x in SECS if x["start"] <= pos), key=lambda x: x["start"])
    return f"{s['number']} {s['title']}" if s["number"] else s["title"]


def rx(marker):
    return re.compile(r"\s+".join(re.escape(w) for w in marker.split()))


def find(marker, lo=0, hi=None):
    m = rx(marker).search(S, lo, hi if hi is not None else len(S))
    assert m, ("marker not found", marker[:60], lo)
    return m.start(), m.end()


nodes, edges, byid, POS = [], [], {}, {}


def add(nid, typ, name, stmt, start, end, origin="paper", conf=1.0, **kw):
    n = {"id": nid, "type": typ, "name": name, "statement": stmt,
         "section": kw.pop("section", None) or sec_at(start), "origin": origin, "confidence": conf}
    for k, v in kw.items():
        if v is not None:
            n[k] = v
    assert nid not in byid, nid
    nodes.append(n); byid[nid] = n; POS[nid] = (start, end)
    return n


def env(nid, fid, typ, name, origin="paper", conf=1.0, **kw):
    f = F[fid]
    return add(nid, typ, name, norm(f["statement"]), f["start"], f["end"], origin, conf, **kw)


def prose(nid, typ, name, a, b, lo=0, origin="paper", conf=0.75, **kw):
    i, _ = find(a, lo)
    _, j = find(b, i)
    return add(nid, typ, name, norm(S[i:j]), i, j, origin, conf, **kw)


def sub(nid, a):
    st = byid[nid]["statement"]
    a = norm(a)
    assert a in st, (nid, a[:60])
    return a


EQN = [0]


def eq(fid, name, **kw):
    EQN[0] += 1
    nid = f"EP{EQN[0]}"
    env(nid, fid, "equation", name, "paper", 1.0, **kw)
    return nid


PSP = [0]
ORDER = {}


def step(parent, a, b, subclass, name, short=None, conf=0.75):
    """a proof step: from marker a through marker b, inside the parent's span"""
    lo, hi = POS[parent]
    i, _ = find(a, lo, hi)
    _, j = find(b, i, hi)
    PSP[0] += 1
    sid = f"PSP{PSP[0]}"
    ORDER[parent] = ORDER.get(parent, 0) + 1
    root = parent
    while byid[root]["type"] == "proof_step":
        root = byid[root]["parent_id"]
    add(sid, "proof_step", name, norm(S[i:j]), i, j, byid[root]["origin"], conf,
        section=byid[root]["section"], parent_id=parent, step_order=ORDER[parent],
        subclass=subclass, statement_short=short or name)
    return sid


def E(s, t, typ="uses", conf=0.8, basis="inferred", **kw):
    e = {"source": s, "target": t, "type": typ, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)


STD = "standard (uncited)"

# ============================================================ 1 Introduction
prose("CnjP1", "conjecture", "Borsuk's conjecture (Borsuk's partition problem)",
      "Borsuk's partition problem asks whether every bounded set", "subsets of strictly\nsmaller diameter.",
      origin="external", conf=0.75, origin_citation="Borsuk 1933",
      statement_short="Every bounded set in $\\mathbb R^d$ of positive diameter can be covered by $d+1$ sets of smaller diameter.",
      assumptions=[], conclusions=["every bounded set of positive diameter in $\\mathbb R^d$ can be covered by $d+1$ subsets of strictly smaller diameter"],
      tags=["discrete_geometry", "borsuk_problem", "diameter", "covering"])
prose("DP1", "definition", "Real symmetric 4x4 matrices with Frobenius norm",
      "Let $\\operatorname{Sym}_4(\\mathbb R)$ be the space", "$\\|A\\|_F^2=\\operatorname{tr}(A^2)$.",
      origin="external", conf=0.8, origin_citation=STD,
      definiendum=["$\\operatorname{Sym}_4(\\mathbb R)$", "$\\|A\\|_F$"], genus="the space of real symmetric $4\\times4$ matrices",
      tags=["linear_algebra", "symmetric_matrices"])
env("TP1", "F1", "theorem", "Rank-one projectors on R^4 are a Borsuk counterexample in R^9", main=True,
    statement_short="The set of rank-one projectors $uu^T$ on $\\mathbb R^4$ (in $\\mathbb R^9$, Frobenius metric) has diameter $\\sqrt2$ and needs more than ten smaller-diameter pieces.",
    tags=["discrete_geometry", "borsuk_problem", "counterexample", "projective_space", "covering"])
byid["TP1"]["assumptions"] = [sub("TP1", "The compact set \\[ X=\\{uu^{\\mathsf T}:u\\in\\mathbb R^4,\\ \\|u\\|=1\\} \\subset\\{A\\in\\operatorname{Sym}_4(\\mathbb R):\\operatorname{tr}A=1\\}, \\]"),
                              sub("TP1", "with the Frobenius metric")]
byid["TP1"]["conclusions"] = [sub("TP1", "has diameter $\\sqrt2$"),
                              sub("TP1", "cannot be covered by ten subsets of diameter strictly less than $\\sqrt2$")]
# History
prose("TP2", "theorem", "Kahn-Kalai disproof of Borsuk's conjecture",
      "Kahn and Kalai disproved it in high dimensions", "force many smaller-diameter parts.",
      origin="external", conf=0.75, origin_citation="Kahn & Kalai 1993 (using Frankl & Wilson 1981)",
      statement_short="Borsuk's conjecture fails in high dimensions, via the Frankl-Wilson forbidden-intersection theorem.",
      assumptions=[], conclusions=["Kahn and Kalai disproved it in high dimensions \\cite{KahnKalai1993}"],
      tags=["discrete_geometry", "borsuk_problem", "counterexample"])
prose("TP3", "theorem", "Grinsztajn's 63-dimensional Borsuk counterexample",
      "Grinsztajn's public proof note gives a", "dimension $63$ \\cite{Grinsztajn2026}.",
      origin="external", conf=0.7, origin_citation="Grinsztajn 2026",
      statement_short="A finite counterexample to Borsuk's conjecture in dimension 63 (previous record).",
      assumptions=[], conclusions=["gives a finite counterexample in dimension $63$"],
      tags=["discrete_geometry", "borsuk_problem", "counterexample"])

# ============================================================ 2 From diameter covers to projective maps
lo2 = S.index("\\section{From diameter covers")
prose("DP2", "definition", "Euclidean space V=R^k and its projective space P(V)",
      "Let $V=\\mathbb R^k$ have its usual inner product", "one-dimensional linear subspaces.", lo=lo2,
      origin="external", conf=0.8, origin_citation=STD,
      definiendum=["$V$", "$k$", "$\\mathbb P(V)$"], tags=["projective_space"])
prose("DP3", "definition", "Orthogonal projector P_x onto a line",
      "For a line $x=[u]$, represented by a unit vector $u$", "for the orthogonal projector onto $x$.", lo=lo2,
      origin="external", conf=0.8, origin_citation=STD,
      definiendum="$P_x$", genus="the orthogonal projector onto $x$", tags=["projective_space", "projectors"])
prose("DP4", "definition", "Sym(V), Frobenius inner product, N_k and the projector set X_k",
      "Let $\\operatorname{Sym}(V)$ be the", "X_k=\\{P_x:x\\in\\mathbb P(V)\\}.\n\\]", lo=lo2, conf=0.8,
      definiendum=["$\\operatorname{Sym}(V)$", "$\\langle A,B\\rangle_F$", "$N_k$", "$X_k$"],
      statement_short="Symmetric operators with Frobenius inner product; $N_k=k(k+1)/2$ is their dimension and $X_k$ the set of rank-one projectors.",
      tags=["symmetric_matrices", "projectors"])
env("LP1", "F2", "lemma", "Projector geometry", origin="external",
    origin_citation="Conway, Hardin & Sloane 1996 (Section 5, Theorem 2)",
    statement_short="$x\\mapsto P_x$ embeds $\\mathbb P(\\mathbb R^k)$ in a Euclidean space of dimension $N_k-1$ with $\\|P_x-P_y\\|_F^2=2-2\\langle u,v\\rangle^2$; diameter $\\sqrt2$, attained exactly at orthogonal lines.",
    tags=["projective_space", "projectors", "embedding", "diameter"])
EP1 = eq("F3", "Projector distance formula")
byid["LP1"]["assumptions"] = [sub("LP1", "If $u,v$ are unit representatives of $x,y$")]
byid["LP1"]["conclusions"] = [
    sub("LP1", "The map $x\\mapsto P_x$ identifies $\\mathbb P(V)$ homeomorphically with the compact set $X_k$ in the trace-one affine subspace of $\\operatorname{Sym}(V)$."),
    sub("LP1", "This affine subspace is Euclidean of dimension $N_k-1$."),
    sub("LP1", "\\|P_x-P_y\\|_F^2=2-2\\langle u,v\\rangle^2."),
    sub("LP1", "Consequently $\\operatorname{diam}(X_k)=\\sqrt2$, and two projectors are at this distance exactly when their lines are orthogonal.")]
env("PP1", "F4", "proof", "Proof of Lemma 2.1 (projector geometry)", proves="LP1",
    statement_short="Direct verification: $uu^T$ is well defined and injective on lines, compactness gives a homeomorphism, and trace identities give the distance formula.",
    proof_strategy=["direct"])
step("PP1", "The formula $uu^{\\mathsf T}$ is unchanged", "continuous map on projective space.", "other", "Well-defined continuous map on lines")
step("PP1", "Its range as an operator", "homeomorphism onto\nits image.", "other", "Injective, hence a homeomorphism by compactness")
step("PP1", "Every $P_x$ has trace one", "codimension one in $\\operatorname{Sym}(V)$.", "other", "Image lies in a trace-one hyperplane")
step("PP1", "Finally,\n$\\operatorname{tr}(P_x^2)", "Orthogonal lines exist because $k\\geq2$.", "conclude", "Trace computation gives the distance formula")

env("RP1", "F5", "remark", "Euclidean coordinates on trace-one symmetric 4x4 matrices",
    statement_short="Explicit isometry from trace-one symmetric $4\\times4$ matrices to $\\mathbb R^9$, so the witness $X_4$ lives in $\\mathbb R^9$.",
    tags=["isometry", "symmetric_matrices"])
EP2 = eq("F6", "Explicit isometry to R^9")
prose("DP5", "definition", "Label set [m] and standard simplex", "Write $[m]=\\{1,\\ldots,m\\}$ and",
      "\\sum_i t_i=1\\}$.", lo=lo2, origin="external", conf=0.8, origin_citation=STD,
      definiendum=["$[m]$", "$\\Delta^{m-1}$"], tags=["simplex"])
env("DP6", "F7", "definition", "Admissible map", definiendum=["admissible", "$S(x)$"],
    genus="A smooth map $f=(f_1,\\ldots,f_m):\\mathbb P(V)\\to\\mathbb R^m$",
    differentia=["each $f_i$ is nonnegative", "$\\sum_i f_i=1$", "x\\perp y\\quad\\Longrightarrow\\quad S(x)\\cap S(y)=\\varnothing."],
    statement_short="A smooth partition of unity on $\\mathbb P(V)$ in which orthogonal lines have disjoint sets $S(x)$ of positive coordinates.",
    tags=["partition_of_unity", "projective_space"])
EP3 = eq("F8", "Admissibility condition")
prose("ClP1", "claim", "Restriction of an admissible map to a subspace",
      "Restricting an admissible map to $\\mathbb P(W)$", "may be omitted.", lo=lo2, conf=0.75, rigor="semi_formal",
      statement_short="An admissible map restricted to $\\mathbb P(W)$ is admissible, dropping coordinates that vanish there.",
      assumptions=["for a nonzero linear subspace $W\\subseteq V$"],
      conclusions=["Restricting an admissible map to $\\mathbb P(W)$ for a nonzero linear subspace $W\\subseteq V$ preserves admissibility.",
                   "Coordinates that vanish identically on this subspace may be omitted."],
      tags=["restriction"])
env("LP2", "F9", "lemma", "The strict-gap reduction",
    statement_short="A cover of $X_k$ by $m$ sets of diameter $<\\sqrt2$ yields an admissible map $\\mathbb P(V)\\to\\mathbb R^m$.",
    assumptions=["If $X_k$ is covered by at most $m$ subsets, each of diameter strictly less than $\\sqrt2$"],
    conclusions=["there is an admissible map $f:\\mathbb P(V)\\to\\mathbb R^m$"], tags=["reduction", "covering", "partition_of_unity"])
env("PP2", "F10", "proof", "Proof of Lemma 2.4 (strict-gap reduction)", proves="LP2",
    statement_short="Construction: thicken each set by a quarter of its diameter gap, then take a smooth partition of unity subordinate to the open cover.",
    proof_strategy=["construction", "contradiction"])
p2a = step("PP2", "Pad the cover by empty sets", "The sets $U_i$ cover $X_k$.", "introduce_variable", "Thicken each set to an open neighborhood $U_i$")
p2b = step("PP2", "For any $P,Q\\in U_i$", "\\leq(d_i+\\sqrt2)/2<\\sqrt2$.", "bound_estimate", "Triangle inequality keeps diameters below $\\sqrt2$")
p2c = step("PP2", "Pull these sets back", "Empty sets receive the zero function.", "apply_lemma", "Smooth partition of unity subordinate to the cover")
p2d = step("PP2", "If $i$ belonged to\nboth", "a contradiction.", "conclude", "Orthogonal lines cannot share a label")
E(p2b, p2d, conf=0.8)
prose("RP2", "remark", "Why the strict diameter gap matters", "The strict diameter inequalities are what permit",
      "does not supply this reduction.", lo=lo2, conf=0.7,
      statement_short="The strict inequalities are needed for the open thickening and partition of unity; excluding orthogonal pairs alone is not enough.")
prose("DP7", "definition", "Support complex of an admissible map",
      "For an admissible map, define its \\emph{support complex}", "for some }x\\in\\mathbb P(V).\n\\]", lo=lo2, conf=0.85,
      definiendum=["support complex", "$K$"],
      differentia=["I\\subseteq S(x)\\ \\text{for some }x\\in\\mathbb P(V)."],
      statement_short="Label sets that are all positive at some common line form the faces of $K$.",
      tags=["simplicial_complex"])
prose("ClP2", "claim", "The support complex is a finite simplicial complex containing the image of f",
      "It is a finite simplicial complex, possibly with unused labels", "inside the standard simplex.", lo=lo2, conf=0.7,
      rigor="semi_formal", assumptions=[], conclusions=["It is a finite simplicial complex, possibly with unused labels, and $f$ takes values in its geometric realization inside the standard simplex."],
      tags=["simplicial_complex"])

# ============================================================ 3 An extension to symmetric matrices
lo3 = S.index("\\section{An extension to symmetric matrices}")
prose("DP8", "definition", "Degree-two homogeneous lift H",
      "Define the continuous degree-two homogeneous function", "Continuity at zero follows from $\\|H(v)\\|_1=\\|v\\|^2$.", lo=lo3, conf=0.85,
      definiendum="$H$", statement_short="$H(v)=\\|v\\|^2 f([v])$, extended by $0$ at the origin.", tags=["homogeneous_extension"])
prose("DP9", "definition", "Positive extension E_V to positive semidefinite operators",
      "For a positive semidefinite operator $Q$, let", "when the ambient space is clear.", lo=lo3, conf=0.85,
      definiendum=["$E_V$", "$\\mu_V$", "$E$"],
      statement_short="$E_V(Q)$ averages $H(Q^{1/2}u)$ over the unit sphere, times $k$.", tags=["extension", "positive_semidefinite"])
EP4 = eq("F11", "Definition of the positive extension E_V")
env("LP3", "F12", "lemma", "Properties of the positive extension",
    statement_short="$E_V$ is continuous, degree-one homogeneous, nonnegative with coordinate sum $\\operatorname{tr}Q$, supported on the labels used on $\\operatorname{ran}Q$, extends $f$, and restricts to subspaces.",
    tags=["extension", "positive_semidefinite"])
EP5 = eq("F13", "Support of the positive extension")
byid["LP3"]["assumptions"] = [sub("LP3", "For $t\\geq0$")]
byid["LP3"]["conclusions"] = [
    sub("LP3", "The map $E_V$ is continuous on the full positive semidefinite cone, including its singular boundary."),
    sub("LP3", "E_V(tQ)=tE_V(Q),\\qquad E_V(Q)_i\\geq0,\\qquad \\sum_{i=1}^m E_V(Q)_i=\\operatorname{tr}Q."),
    sub("LP3", "Its positive coordinates are exactly the labels used on the range of $Q$:"),
    sub("LP3", "$E_V(P_x)=f(x)$ for every line $x$"),
    sub("LP3", "if $Q$ is supported on a nonzero subspace $W\\subseteq V$, then $E_V(Q)=E_W(Q|_W)$"),
    sub("LP3", "this last expression is smooth when $W$ varies smoothly with fixed dimension and $Q|_W$ varies smoothly through positive definite operators")]
env("PP3", "F14", "proof", "Proof of Lemma 3.1 (positive extension)", proves="LP3",
    statement_short="Direct: continuity of the matrix square root, $\\int uu^T=k^{-1}I$ for the trace, open-set positivity for supports, and a pushforward-measure identity for the subspace formula.",
    proof_strategy=["direct"])
step("PP3", "The positive square root depends continuously", "proves continuity of $E_V$.", "other", "Continuity via polynomial approximation of the square root")
p3b = step("PP3", "Its homogeneity and nonnegativity follow", "=\\operatorname{tr}Q.\n\\]", "algebraic_manipulation", "Homogeneity, nonnegativity and trace identity")
p3c = step("PP3", "Every nonzero $Q^{1/2}u$ lies in", "in both\ndirections.", "other", "Positive coordinates are the labels used on the range")
step("PP3", "For $Q=P_x$, every nonzero integrand", "Thus $E_V(P_x)=f(x)$.", "substitute", "Extension agrees with $f$ on projectors")
p3e = step("PP3", "To prove the subspace identity", "as claimed.", "invoke_identity", "Pushforward measure gives the subspace formula")
p3f = step("PP3", "Finally choose, locally in the parameters", "asserted local smoothness.", "conclude", "Local frames give smoothness")
E(p3e, p3f, conf=0.8)
prose("DP10", "definition", "Absolute value and positive/negative parts of a symmetric operator",
      "For a symmetric operator $A$, let $|A|=(A^2)^{1/2}$", "their ranges are orthogonal.", lo=lo3, conf=0.85,
      origin="external", origin_citation=STD, definiendum=["$|A|$", "$A_+$", "$A_-$"],
      tags=["symmetric_matrices", "spectral_decomposition"])
prose("DP11", "definition", "Signed extension F", "Define\n\\begin{equation}\n F(A)=E_V(A_+)-E_V(A_-).",
      "\\end{equation}", lo=POS["DP10"][1], conf=0.85, definiendum="$F$", tags=["extension", "odd_map"])
EP6 = eq("F15", "Definition of the signed extension F")
env("LP4", "F16", "lemma", "The odd sphere map",
    statement_short="$F$ is continuous, odd, positively homogeneous, has $\\|F(A)\\|_1=\\operatorname{tr}|A|$, signed supports given by the spectral ranges, and induces an odd map between norm spheres.",
    tags=["odd_map", "sphere_map", "extension"])
EP7 = eq("F17", "Norm identities for F")
EP8 = eq("F18", "Spectral support of F")
EP9 = eq("F19", "Odd map between norm spheres")
byid["LP4"]["conclusions"] = [
    sub("LP4", "The map $F:\\operatorname{Sym}(V)\\to\\mathbb R^m$ is continuous, odd, and homogeneous of degree one for nonnegative scalars."),
    sub("LP4", "If every coordinate of $F(A)$ is nonzero, then $A$ is nonsingular."),
    sub("LP4", "If all coordinates of $F(A)$ are strictly negative, then $A$ is negative definite; the analogous statement holds with both signs reversed."),
    sub("LP4", "The map $F$ is smooth on the open set of nonsingular symmetric operators."),
    sub("LP4", "In particular, it restricts to a continuous odd map")]
byid["LP4"]["assumptions"] = []
env("PP4", "F20", "proof", "Proof of Lemma 3.2 (odd sphere map)", proves="LP4",
    statement_short="Direct: orthogonal spectral ranges carry disjoint labels by admissibility, so no cancellation occurs; kernel lines would leave a label unused; spectral projections give smoothness.",
    proof_strategy=["direct"])
p4a = step("PP4", "Continuity and homogeneity follow from", "so $F$ is odd.", "apply_lemma", "Continuity, homogeneity and oddness")
p4b = step("PP4", "Any line in\n$\\operatorname{ran}A_+$", "\\eqref{eq:extension-norms}.", "other", "Disjoint label supports give the norm identities")
p4c = step("PP4", "If $\\ker A$ contains a line $x$", "This proves the\nnonsingularity assertion.", "other", "A kernel line leaves a zero coordinate")
p4d = step("PP4", "If all coordinates of $F(A)$ are negative", "Oddness gives the positive case.", "other", "All-negative output forces negative definiteness")
step("PP4", "For local smoothness, fix nonsingular $A$.", "This proves smoothness of $F$.", "conclude", "Smoothness via spectral projections and frames")
E(p4b, p4d, conf=0.8); E(p4c, p4d, conf=0.85)
prose("RP3", "remark", "Norm spheres and sphere degree", "The two norm spheres in \\eqref{eq:norm-sphere-map} are not",
      "every preimage of a full-support value.", lo=lo3, conf=0.7,
      statement_short="Radial normalization identifies the trace-norm and $\\ell^1$ spheres with round spheres, so mod-two degree and local differential arguments apply to $F$ when $m=N_k$.",
      tags=["degree_theory"])

# ============================================================ 4 The equality case gives a simplicial cycle
lo4 = S.index("\\section{The equality case")
prose("DP12", "definition", "Trace-norm sphere Sigma(V) and l1-sphere Sigma_m",
      "For a Euclidean space $V$ of\ndimension $k$, write", "\\sum_i|y_i|=1\\}.\n\\]", lo=lo4, conf=0.85,
      definiendum=["$\\Sigma(V)$", "$\\Sigma_m$"], tags=["sphere"])
prose("RP4", "remark", "Smooth structures on Sigma(V) and Sigma_m",
      "Radial projection identifies these spaces antipodally with", "the relevant\nnorm functions are smooth there.", lo=lo4, conf=0.7,
      statement_short="$\\Sigma(V),\\Sigma_m$ get the smooth structure of round spheres, agreeing with the hypersurface structure near nonsingular / full-support points.",
      tags=["sphere", "smooth_structure"])
env("PrP1", "F21", "proposition", "The number of labels",
    statement_short="An admissible map on $\\mathbb P(\\mathbb R^k)$ needs at least $N_k=k(k+1)/2$ labels; at equality $F$ has odd degree, is onto, and every pair of labels is an edge.",
    tags=["lower_bound", "degree_theory", "borsuk_ulam"])
pr = byid["PrP1"]
pr["assumptions"] = [sub("PrP1", "If $k\\ge2$"), sub("PrP1", "If $m=N_k$")]
pr["conclusions"] = [sub("PrP1", "every smooth admissible map $f:\\mathbb P(\\mathbb R^k)\\to\\Delta^{m-1}$ satisfies $m\\ge N_k$"),
                     sub("PrP1", "its extension $F$ has mod-two degree one and is surjective"),
                     sub("PrP1", "every pair of labels is an edge of the support complex of $f$")]
pr["parts"] = [{"assumptions": [pr["assumptions"][0]], "conclusions": [pr["conclusions"][0]]},
               {"adds_to": 0, "assumptions": [pr["assumptions"][1]], "conclusions": pr["conclusions"][1:]}]
env("PP5", "F22", "proof", "Proof of Proposition 4.1 (number of labels)", proves="PrP1",
    statement_short="Borsuk-Ulam: an odd map $S^n\\to S^d$ forces $n\\le d$ and an odd self-map has odd degree; for edges, pick a target with two positive labels and use $N_2=3$ on the positive eigenspace.",
    proof_strategy=["contradiction", "other"])
prose("TP4", "theorem", "Odd maps between spheres (Borsuk-Ulam; odd maps have odd degree)",
      "An odd map $S^n\\to S^d$ requires $n\\le d$", "Corollary~2B.7]{Hatcher2002}.", lo=POS["PP5"][0], origin="external",
      conf=0.85, origin_citation="Hatcher 2002 (Proposition 2B.6 and Corollary 2B.7)",
      assumptions=[], conclusions=["An odd map $S^n\\to S^d$ requires $n\\le d$", "an odd self-map of $S^n$ has odd degree"],
      tags=["borsuk_ulam", "degree_theory", "odd_map"])
p5a = step("PP5", "Applying these facts to $F$", "the degree assertion.", "apply_lemma", "Apply the odd-map facts to $F$")
p5b = step("PP5", "A map of nonzero degree cannot omit", "contractible.", "other", "Nonzero degree implies surjectivity")
p5c = step("PP5", "Suppose $m=N_k$ and fix distinct labels", "uses only these\ntwo labels.", "introduce_variable", "Preimage of a value positive on exactly two labels")
p5d = step("PP5", "That subspace cannot have dimension at least two", "Its dimension is therefore one.", "bound_estimate", "Positive eigenspace is a line by $N_2=3$")
p5e = step("PP5", "The exact\nspectral-support property", "is an edge.", "conclude", "That line carries both labels, so the pair is an edge")
E("TP4", p5a, conf=0.9, basis="named")
E(p5b, p5c, conf=0.8); E(p5a, p5d, conf=0.8, basis="named"); E(p5d, p5e, conf=0.8)
env("LP5", "F23", "lemma", "Local counting",
    statement_short="Mod-two local degree: at a regular point of a locally smooth map from a closed manifold, the fiber is finite and its parity is the local image of the fundamental class.",
    tags=["degree_theory", "local_degree"])
byid["LP5"]["assumptions"] = [sub("LP5", "Let $M$ be a closed smooth $n$-manifold, possibly disconnected, and let $q:M\\to Y$ be continuous, with $Y$ Hausdorff."),
                              sub("LP5", "Suppose a point $y\\in Y$ has a neighborhood homeomorphic to an open subset of $\\mathbb R^n$, and that $q$ is smooth in the corresponding coordinates near $q^{-1}(y)$, with invertible derivative at each point of that fiber.")]
byid["LP5"]["conclusions"] = [sub("LP5", "Then the fiber is finite, and the image of the total fundamental class of $M$ in"),
                              sub("LP5", "is $|q^{-1}(y)|$ modulo two."),
                              sub("LP5", "In particular, if $Y$ is a connected closed $n$-manifold, this parity is the mod-two degree of $q$.")]
env("PP6", "F24", "proof", "Proof of Lemma 4.2 (local counting)", proves="LP5",
    statement_short="Inverse function theorem for finiteness, excision to split local homology over the fiber, naturality to sum the local generators.",
    proof_strategy=["direct"])
step("PP6", "The inverse function theorem makes", "hence finite.", "apply_lemma", "Fiber is finite")
step("PP6", "By excision,", "coordinate one in each summand.", "invoke_identity", "Excision splits local homology over the fiber")
step("PP6", "A local\ndiffeomorphism sends", "away from the selected fiber.", "conclude", "Naturality gives the parity")
env("TP5", "F25", "theorem", "Supports at equality",
    statement_short="With exactly $N_k$ labels, every facet of the support complex has $k$ vertices and the facets sum to a mod-2 cycle, so each codimension-one face lies in a positive even number of facets.",
    tags=["simplicial_complex", "degree_theory", "pseudomanifold"])
byid["TP5"]["assumptions"] = [sub("TP5", "Let $k\\ge3$ and $m=N_k$."), sub("TP5", "Suppose $f:\\mathbb P(\\mathbb R^k)\\to\\Delta^{m-1}$ is a smooth admissible map.")]
byid["TP5"]["conclusions"] = [sub("TP5", "Its support complex $K$ has every pair of labels as an edge, every facet has $k$ vertices, and"),
                              sub("TP5", "is a simplicial cycle over $\\mathbb F_2$."),
                              sub("TP5", "Consequently every $(k-2)$-dimensional face lies in a positive even number of facets.")]
env("PP7", "F26", "proof", "Proof of Theorem 4.3 (supports at equality)", proves="TP5",
    statement_short="Degree argument at equality: compare the odd-degree map $F$ with a map on a sphere bundle over a regular level set of a facet. "
                    "A trivial bundle over an affine chart forces degree zero unless the level set is finite, so facets have $k$ labels; odd local counts give the facet cycle.",
    proof_strategy=["contradiction", "geometric", "other"])
for f_ in ["F27", "F28", "F29", "F30", "F31", "F32", "F33", "F34", "F35"]:
    pass
EP10 = eq("F27", "Facet size upper bound")
EP11 = eq("F28", "Dimension of the level set L")
EP12 = eq("F29", "Trivialization of the sphere bundle")
EP13 = eq("F30", "Dimension of the sphere bundle M")
EP14 = eq("F31", "Splitting of a preimage")
EP15 = eq("F32", "Triangular form of F in local coordinates")
EP16 = eq("F33", "Odd preimage count on the bundle")
EP17 = eq("F34", "Pullback of the cover class")
EP18 = eq("F35", "Odd count of facet preimages")
# setup (text before the first \paragraph)
s0 = step("PP7", "The edge assertion is Proposition", "\\end{equation}", "setup", "Edge assertion; set up an arbitrary facet and bound its size")
step(s0, "The edge assertion is Proposition", "Proposition~\\ref{thm:label-bound}.", "apply_lemma", "Edges from Proposition 4.1")
s0b = step(s0, "We prove\nthe remaining assertions", "h=N_{k-1}.\n\\]", "introduce_variable", "Fix a facet $I$ and its complement $J$")
s0c = step(s0, "Since $I$ is a maximal support face", "\\end{equation}", "bound_estimate", "Label bound in $x_0^\\perp$ gives $|I|\\le k$")
E(s0b, s0c, conf=0.8)
sA = step("PP7", "\\paragraph{A compact level set over one affine chart.}", "\\dim M=(a-h)+(h-1)=a-1.\n\\end{equation}", "introduce_variable",
          "A compact level set over one affine chart", "Build the level set $L$ of $f_I$ and the sphere bundle $M$ over it", conf=0.95)
a1 = step(sA, "Define\n\\[\n U_I=", "open simplex\n$\\mathring\\Delta_I$ on $I$.", "introduce_variable", "Define $U_I$; $f_I$ maps it to the open simplex")
a2 = step(sA, "Moreover, $U_I$ lies in the affine", "any label in $I$.", "other", "$U_I$ lies in one affine chart")
a3 = step(sA, "Choose a regular value $r", "For now $L$ is allowed to be empty.", "introduce_variable", "Regular level set $L$ by Sard")
a4 = step(sA, "If $\\widetilde r$ denotes", "\\end{equation}", "other", "$L$ is a compact manifold of dimension $k-s$")
a5 = step(sA, "If $s<k$, the level-set dimension", "coefficient of $I$ in the desired cycle.", "setup", "Plan of the parity comparison")
a6 = step(sA, "For $x\\in U_I$, admissibility ensures", "G(x,B)=G_x(B).\n\\]", "introduce_variable", "Fiberwise extensions $G_x$ on the sphere bundle $M$")
a7 = step(sA, "The bundle $x\\mapsto x^\\perp$ is trivial", "\\end{equation}", "other", "The bundle is trivial over the chart")
a8 = step(sA, "Equip $M$ with the smooth structure", "\\end{equation}", "other", "Smooth structure and dimension of $M$")
E(a1, a3, conf=0.8); E(a2, a7, conf=0.85); E(a6, a7, conf=0.8)
sB = step("PP7", "\\paragraph{Odd parity on the bundle.}", "This proves, in particular, that $L$ is nonempty.", "other",
          "Odd parity on the bundle", "Show $|G^{-1}(g)|$ is odd by matching it with $F^{-1}(y)$", conf=0.95)
b1 = step(sB, "Consider the open negative orthant", "negative\ndefinite on $x^\\perp$.", "other", "Preimages of the negative orthant are negative definite")
b2 = step(sB, "Consequently $G$ is smooth", "possibility of an empty preimage.", "apply_lemma", "Regular value $g$ by Sard")
b3 = step(sB, "Fix $0<\\lambda<1$", "indexed by $I$ and $J$.", "introduce_variable", "Full-support target $y=(\\lambda r,(1-\\lambda)g)$")
b4 = step(sB, "We claim\nthat $F^{-1}(y)$", "gives a preimage by \\eqref{eq:preimage-splitting}.", "other",
          "Claim: $F^{-1}(y)$ corresponds to $G^{-1}(g)$")
b41 = step(b4, "Every $A\\in F^{-1}(y)$ is nonsingular", "labels in $I$.", "other", "Positive eigenspace uses only $I$-labels")
b42 = step(b4, "That subspace must be one-dimensional", "Call the resulting positive\nline $x$.", "bound_estimate", "Positive eigenspace is a line")
b43 = step(b4, "The positive output block", "\\end{equation}", "other", "Preimage splits as $\\lambda P_x+(1-\\lambda)B$")
b44 = step(b4, "The subspace formula for the extension", "gives a preimage by \\eqref{eq:preimage-splitting}.", "conclude", "Bijection of fibers")
b5 = step(sB, "The value $y$ is regular", "both have dimension $m-1$.", "other", "Triangular derivative: $y$ is a regular value")
b6 = step(sB, "By the odd degree of $F$", "This proves, in particular, that $L$ is nonempty.", "conclude", "Odd count from the degree of $F$")
E(b1, b2, conf=0.8); E(b2, b3, conf=0.75); E(b41, b42, conf=0.8); E(b42, b43, conf=0.8); E(b4, b6, conf=0.85); E(b5, b6, conf=0.85)
sC = step("PP7", "\\paragraph{The double cover forces maximal supports to have size $k$.}", "proves $a=h$ and $s=k$ for every facet.", "contradiction_setup",
          "The double cover forces maximal supports to have size k", "Cohomology of the projective bundle forces degree zero if $a>h$, contradicting odd parity", conf=0.95)
c1 = step(sC, "The oddness of $G$ in the sphere variable", "\\longrightarrow\\mathbb{RP}^{a-1}.\n\\]", "introduce_variable", "Quotient map $\\overline G$ on the projective bundle")
c2 = step(sC, "Write $w\\in H^1(\\mathbb{RP}^{a-1})$", "on each two-point fiber.", "other", "Equivariance identifies the pulled-back double cover")
c3 = step(sC, "This cover isomorphism induces", "in this identity.", "invoke_identity", "Naturality of Stiefel-Whitney classes: $\\overline G^*w=\\mathrm{pr}_2^*u$")
c4 = step(sC, "Suppose $a>h$.", "=0.\n\\]", "contradiction_setup", "If $a>h$, the top power of $w$ pulls back to zero")
c5 = step(sC, "Both source and target of $\\overline G$", "gives mod-two degree zero.", "other", "Hence $\\overline G$ has degree zero")
c6 = step(sC, "On the other hand, $[g]$ is a regular", "a contradiction.", "other", "Contradiction with the odd count")
c7 = step(sC, "Together with \\eqref{eq:facet-size-upper}", "for every facet.", "conclude", "Every facet has $k$ labels")
E(c1, c2, conf=0.8); E(c3, c4, conf=0.85); E(c4, c5, conf=0.85); E(c5, c6, conf=0.85); E(b6, c6, conf=0.85); E(c6, c7, conf=0.85)
sD = step("PP7", "\\paragraph{The coefficients of the facet cycle.}", "purity makes that number\npositive.", "conclude",
          "The coefficients of the facet cycle", "Odd local counts show every facet has coefficient one in $f_*[\\mathbb P(V)]$, a cycle", conf=0.95)
d1 = step(sD, "Now $\\dim L=0$", "for each such\nfiber map.", "setup", "$L$ finite; fiber maps $G_x$ are odd self-maps")
d2 = step(sD, "Each fiber therefore contributes", "\\end{equation}", "apply_lemma", "Each fiber contributes an odd count, so $|L|$ is odd")
d3 = step(sD, "Every facet has $k$ vertices", "\\in H_{k-1}(|K|).\n\\]", "introduce_variable", "Consider the pushed-forward fundamental class")
d4 = step(sD, "The interior point $\\widetilde r$", "The same holds for every facet.", "other", "Local reading: each facet coefficient is one")
d5 = step(sD, "Since a\n$(k-1)$-dimensional complex", "sum of all facets.", "other", "The class is the sum of all facets")
d6 = step(sD, "Its boundary vanishes.", "purity makes that number\npositive.", "conclude", "Even, positive incidences of codimension-one faces")
E(d1, d2, conf=0.85); E(d2, d4, conf=0.8); E(d3, d4, conf=0.8); E(d4, d5, conf=0.85); E(d5, d6, conf=0.85); E(sC, d1, conf=0.8)
E(sA, sB, conf=0.8); E(a4, d1, conf=0.75)

# ============================================================ 5 Triangle systems on six labels
lo5 = S.index("\\section{Triangle systems on six labels}")
prose("DP13", "definition", "Triangle and tetrahedron (faces of the support complex)",
      "We call a face with three vertices a \\emph{triangle}", "a \\emph{tetrahedron}.", lo=lo5, conf=0.85,
      definiendum=["triangle", "tetrahedron"], genus="a face", differentia=["with three vertices", "four vertices"],
      tags=["simplicial_complex"])
env("DP14", "F36", "definition", "Six-label triangle system", definiendum="six-label triangle system",
    genus="a collection $\\mathcal T\\subseteq\\binom{C}{3}$",
    differentia=["exactly one of $T$ and $C\\setminus T$ belongs to $\\mathcal T$ for each $T\\in\\binom{C}{3}$",
                 "every pair of elements of $C$ belongs to exactly two members of $\\mathcal T$"],
    statement_short="Triples of a 6-set, one from each complementary pair, covering every pair exactly twice.",
    tags=["combinatorics", "triple_system"])
env("LP6", "F37", "lemma", "Triangle system from an admissible map on RP^2",
    assumptions=["an admissible map $f:\\mathbb{RP}^2\\to\\Delta^5$"],
    conclusions=["The triangles of the support complex of an admissible map $f:\\mathbb{RP}^2\\to\\Delta^5$ form a six-label triangle system."],
    statement_short="An admissible map $\\mathbb{RP}^2\\to\\Delta^5$ has support-complex triangles forming a six-label triangle system.",
    tags=["combinatorics", "triple_system", "projective_plane"])
env("PP8", "F38", "proof", "Proof of Lemma 5.2", proves="LP6",
    statement_short="Theorem 4.3 gives a pure complex with all 15 edges each in an even number of triangles; complementary triples exclude each other, and double counting forces exactly one per pair.",
    proof_strategy=["contradiction", "other"])
p8a = step("PP8", "By Theorem~\\ref{thm:equality-complex}", "even number of triangles.", "apply_lemma", "Apply Theorem 4.3 with $k=3$")
p8b = step("PP8", "Two complementary triples cannot both", "none of the six labels.", "contradiction_setup", "Complementary triples are not both triangles")
p8c = step("PP8", "There are ten complementary pairs", "at most ten\ntriangles.", "bound_estimate", "At most ten triangles")
p8d = step("PP8", "Counting incidences between triangles", "triangles.", "bound_estimate", "Double counting gives at least ten")
p8e = step("PP8", "Equality holds throughout", "every edge occurs twice.", "conclude", "Equality gives both axioms")
E(p8b, p8c, conf=0.85); E(p8a, p8d, conf=0.85); E(p8c, p8e, conf=0.85); E(p8d, p8e, conf=0.85)
prose("DP15", "definition", "Link graph of a triangle system at a vertex",
      "For a triangle system $\\mathcal T$ on $C$ and $a\\in C$", "\\{a,u,v\\}\\in\\mathcal T$.", lo=lo5, conf=0.85,
      definiendum="link graph at $a$",
      differentia=["an edge $\\{u,v\\}$ precisely when $\\{a,u,v\\}\\in\\mathcal T$"], tags=["graph", "link"])
env("LP7", "F39", "lemma", "Properties of six-label triangle systems",
    statement_short="In a six-label triangle system, vertex links are 5-cycles, every 4-set contains some but not all triangles, no transposition is a symmetry, and any five labels determine the system.",
    tags=["combinatorics", "triple_system", "rigidity"])
byid["LP7"]["assumptions"] = [sub("LP7", "Let $\\mathcal T$ be a six-label triangle system on $C$.")]
byid["LP7"]["conclusions"] = [sub("LP7", "Every vertex link is a cycle of length five."),
                              sub("LP7", "Every four-element subset of $C$ contains a triangle, but does not contain all four of its triples as triangles."),
                              sub("LP7", "If $a,b\\in C$ are distinct and $R\\subset C\\setminus\\{a,b\\}$ has cardinality three, the link graphs at $a$ and $b$, restricted to $R$, are different. In particular, no transposition of two labels preserves $\\mathcal T$."),
                              sub("LP7", "The triangles contained in any five-element subset of $C$ determine $\\mathcal T$ uniquely.")]
env("PP9", "F40", "proof", "Proof of Lemma 5.3", proves="LP7",
    statement_short="Degree counting makes links 2-regular on five vertices, hence 5-cycles; independence in a 5-cycle gives (2); comparing the two links through a pair gives opposite matchings for (3); complementation gives (4).",
    proof_strategy=["case_analysis", "direct"])
p9a = step("PP9", "Every vertex of the link at $a$ has degree two", "a single five-cycle.", "other", "(1) Links are 2-regular on five vertices, hence 5-cycles")
p9b = step("PP9", "Let $A\\subset C$ have four elements", "which a five-cycle cannot contain.", "other", "(2) A 5-cycle has no independent 3-set and no triangle")
p9c = step("PP9", "For the third assertion, write", "which is impossible.", "other", "(3) Links at $a$ and $b$ use opposite matchings")
p9c1 = step(p9c, "For the third assertion, write", "\\{d,e\\}\\bigr\\}.\n\\]", "introduce_variable", "Link at $a$ minus $b$ is a path using matching $M_1$ or $M_2$")
p9c2 = step(p9c, "Deleting $a$ from the link at $b$", "forcing the second path to use $M_2$.", "other", "Complementary triples force the opposite matching at $b$")
p9c3 = step(p9c, "The symmetric difference of the two paths", "which is impossible.", "conclude", "Restrictions differ, so no transposition is a symmetry")
p9d = step("PP9", "Finally, if $z$ is the omitted vertex", "membership in\n$\\mathcal T$.", "conclude", "(4) Five labels determine the system by complementation")
E(p9a, p9b, conf=0.85); E(p9a, p9c1, conf=0.85); E(p9c1, p9c2, conf=0.85); E(p9c2, p9c3, conf=0.85)

# ============================================================ 6 The obstruction on ten labels
lo6 = S.index("\\section{The obstruction on ten labels}")
env("LP8", "F41", "lemma", "Facet complements carry triangle systems",
    statement_short="In the support complex of an admissible $\\mathbb{RP}^3\\to\\Delta^9$, the triangles in the complement of a tetrahedron form a six-label triangle system; tetrahedra pairwise intersect.",
    tags=["combinatorics", "triple_system", "simplicial_complex"])
byid["LP8"]["assumptions"] = [sub("LP8", "Suppose $f:\\mathbb{RP}^3\\to\\Delta^9$ is admissible, let $K$ be its support complex, and let $S$ be a tetrahedron of $K$.")]
byid["LP8"]["conclusions"] = [sub("LP8", "The triangles of $K$ contained in the six-element set $C=[10]\\setminus S$ form a six-label triangle system."),
                              sub("LP8", "In particular, two tetrahedra of $K$ cannot be disjoint.")]
env("PP10", "F42", "proof", "Proof of Lemma 6.1", proves="LP8",
    statement_short="Restrict $f$ to the plane orthogonal to a witness line of $S$ and apply Lemma 5.2; extra triangles or a disjoint tetrahedron would leave a common orthogonal line with no label.",
    proof_strategy=["contradiction", "direct"])
p10a = step("PP10", "Theorem~\\ref{thm:equality-complex} says that", "support exactly\n$S$.", "apply_lemma", "Pure complex; witness line for $S$")
p10b = step("PP10", "The restriction of $f$ to", "would be violated.", "other", "Restriction to $x^\\perp$ uses all six complementary labels")
p10c = step("PP10", "By Lemma~\\ref{lem:six-from-map}, this restriction", "$K$ on $C$.", "apply_lemma", "Lemma 5.2 gives a triangle system inside $K$ on $C$")
p10d = step("PP10", "There are no additional triangles on $C$.", "no admissible label.", "contradiction_setup", "No extra triangles: a common orthogonal line would have no label")
p10e = step("PP10", "If a tetrahedron $S'$ were disjoint", "Lemma~\\ref{lem:six-properties}(2).", "conclude", "A disjoint tetrahedron contradicts Lemma 5.3(2)")
E(p10a, p10b, conf=0.85); E(p10b, p10c, conf=0.85); E(p10c, p10d, conf=0.8); E(p10d, p10e, conf=0.8)
prose("ClP3", "claim", "Triangles lie in an even number of tetrahedra (k=4)",
      "By Theorem~\\ref{thm:equality-complex}, each\ntriangle of $K$", "positive even number of tetrahedra.", lo=lo6, conf=0.75,
      assumptions=[], conclusions=["each triangle of $K$ lies in a positive even number of tetrahedra"], tags=["simplicial_complex"])
env("LP9", "F43", "lemma", "Every triangle lies in exactly two tetrahedra",
    statement_short="Each triangle of the ten-label support complex is in exactly two tetrahedra.",
    assumptions=["Suppose $f:\\mathbb{RP}^3\\to\\Delta^9$ is admissible, let $K$ be its support complex"],
    conclusions=["Every triangle of $K$ belongs to exactly two tetrahedra."], tags=["combinatorics", "pseudomanifold"])
env("PP11", "F44", "proof", "Proof of Lemma 6.2", proves="LP9",
    statement_short="Transport of triangle systems: three tetrahedra on one triangle would let a cycle of transpositions fix a system while swapping two labels, contradicting Lemma 5.3(3).",
    proof_strategy=["contradiction"])
prose("ClP4", "claim", "Transport of triangle systems across adjacent tetrahedra",
      "First observe that if two tetrahedra differ by exchanging", "Lemma~\\ref{lem:six-properties}(4).", lo=POS["PP11"][0], conf=0.75,
      assumptions=["if two tetrahedra differ by exchanging labels $a,b$"],
      conclusions=["the same exchange carries their complementary triangle systems to one another"],
      statement_short="If two tetrahedra differ by swapping $a,b$, that swap maps one complementary triangle system to the other.",
      tags=["combinatorics", "triple_system"])
cl4a = step("ClP4", "Their complements share five labels", "triangles of $K$.", "other", "Both systems agree on the five shared labels")
cl4b = step("ClP4", "After the exchange these triangles remain fixed", "Lemma~\\ref{lem:six-properties}(4).", "conclude", "Five labels determine the system")
E(cl4a, cl4b, conf=0.85)
p11a = step("PP11", "Suppose three tetrahedra", "has four elements.", "contradiction_setup", "Suppose three tetrahedra share a triangle")
p11b = step("PP11", "Transporting\nthe complementary systems", "preserves the initial system.", "other", "Transport around a 3-cycle of swaps")
p11c = step("PP11", "The composite fixes $R$", "Lemma~\\ref{lem:six-properties}(3).", "other", "The composite is a transposition symmetry: contradiction")
p11d = step("PP11", "Thus at most\ntwo tetrahedra", "gives\nexactly two.", "conclude", "Even multiplicity gives exactly two")
E("ClP4", p11b, conf=0.85); E(p11a, p11b, conf=0.85); E(p11b, p11c, conf=0.85); E(p11c, p11d, conf=0.85)
E("ClP3", p11d, conf=0.85, basis="inferred")
prose("DP16", "definition", "Link graph of an edge of K",
      "For an edge $D$ of $K$, define its \\emph{link graph}", "is a tetrahedron.", lo=lo6, conf=0.85,
      definiendum="link graph (of an edge $D$)", genus="a graph",
      differentia=["as vertices the labels $v\\notin D$ for which $D\\cup\\{v\\}$ is a triangle",
                   "as edges the pairs $\\{v,w\\}$ for which $D\\cup\\{v,w\\}$ is a tetrahedron"], tags=["graph", "link"])
env("LP10", "F45", "lemma", "Edge links are short cycles",
    statement_short="Each component of an edge link is a 3- or 4-cycle.",
    assumptions=["For an edge $D$ of $K$"],
    conclusions=["Every connected component of an edge link is a cycle of length three or four."], tags=["combinatorics", "link"])
byid["LP10"]["assumptions"] = []
env("PP12", "F46", "proof", "Proof of Lemma 6.3", proves="LP10",
    statement_short="Links are 2-regular by Lemma 6.2; a path on five vertices would, by transporting systems along four swaps, give equal restricted links at two labels, contradicting Lemma 5.3(3).",
    proof_strategy=["contradiction"])
p12a = step("PP12", "Every vertex of an edge link has degree two", "a simple cycle.", "apply_lemma", "Links are 2-regular: unions of cycles")
p12b = step("PP12", "We show that the link contains no path", "five distinct vertices.", "setup", "Reduce to excluding paths on five vertices")
p12c = step("PP12", "Suppose such a path has consecutive", "\\end{aligned}\n\\]", "contradiction_setup", "Transport systems along the four tetrahedra of a 5-path")
p12d = step("PP12", "The composite fixes $R$ and sends", "membership in $K$.", "other", "The composite relates the links at $v_4$ and $v_2$")
p12e = step("PP12", "The first system therefore has identical", "Lemma~\\ref{lem:six-properties}(3).", "other", "Identical restricted links contradict Lemma 5.3(3)")
p12f = step("PP12", "Every cycle of length at least five", "proving the assertion.", "conclude", "Long cycles contain such a path")
E("ClP4", p12c, conf=0.8)
E(p12c, p12d, conf=0.85); E(p12d, p12e, conf=0.85); E(p12e, p12f, conf=0.85); E(p12a, p12f, conf=0.8)
env("LP11", "F47", "lemma", "Partner blocks of a tetrahedron",
    statement_short="For a tetrahedron $S$, the partner map $p$ groups labels into disjoint blocks $B_y$; omitting one element per block always gives a tetrahedron, and every tetrahedron meets some block twice.",
    tags=["combinatorics", "simplicial_complex"])
byid["LP11"]["assumptions"] = [sub("LP11", "Fix a tetrahedron $S$ of $K$.")]
byid["LP11"]["conclusions"] = [sub("LP11", "The sets $B_y$ are disjoint and have at least two elements."),
                               sub("LP11", "For every choice $q_y\\in B_y$, the set"),
                               sub("LP11", "is a tetrahedron."),
                               sub("LP11", "Moreover, every tetrahedron of $K$ contains at least two elements of one of these blocks.")]
env("PP13", "F48", "proof", "Proof of Lemma 6.4", proves="LP11",
    statement_short="Show block invariance under crossing a face via the short-link lemma (two cases, $a=b$ and $a\\ne b$), then realize every choice of omissions; a tetrahedron meeting each block once would be disjoint from one of them.",
    proof_strategy=["construction", "case_analysis", "contradiction"])
p13a = step("PP13", "The partner $p(v)$ exists and is unique", "lower size bound are immediate.", "apply_lemma", "Partners exist and are unique by Lemma 6.2")
p13b = step("PP13", "We first prove that replacing $v$", "all other blocks are unchanged.", "other", "Claim: crossing a face leaves the blocks unchanged")
q1 = step(p13b, "Put $S'=(S\\setminus\\{v\\})\\cup\\{a\\}$", "We have $p'(a)=v$.", "introduce_variable", "New tetrahedron $S'$ and partner map $p'$")
q2 = step(p13b, "For $w\\in S\\setminus\\{v\\}$", "\\{v,b\\}.\n\\]", "introduce_variable", "Three known edges in the link of $D$")
q3 = step(p13b, "If $a=b$, these form a three-cycle.", "Thus $p'(w)=v$.", "case_split", "Case $a=b$: a 3-cycle component")
q4 = step(p13b, "If $a\\ne b$, the displayed edges", "Thus $p'(w)=b=p(w)$.", "case_split", "Case $a\\ne b$: closes to a 4-cycle")
q5 = step(p13b, "The two cases are illustrated", "\\end{cases}\n\\]", "other", "Formula for the new partner map")
q6 = step(p13b, "The block formerly indexed by $a$", "all other blocks are unchanged.", "conclude", "Blocks keep their elements")
E(q1, q3, conf=0.8); E(q2, q3, conf=0.85); E(q2, q4, conf=0.85); E(q3, q5, conf=0.85); E(q4, q5, conf=0.85); E(q5, q6, conf=0.85)
p13c = step("PP13", "The tetrahedron $S$ contains all elements", "by block invariance.", "other", "Every tetrahedron reached omits one element per block")
p13d = step("PP13", "To change the omitted element", "=|S|=4$.", "introduce_variable", "Every choice of omissions is realized")
p13e = step("PP13", "Finally, suppose a tetrahedron $T$", "contrary to\nLemma~\\ref{lem:facet-complement}.", "conclude", "A tetrahedron meeting each block once yields a disjoint one")
E(p13b, p13c, conf=0.85); E(p13c, p13d, conf=0.85); E(p13d, p13e, conf=0.85)
E("LP9", "LP11", conf=0.75)
env("TP6", "F49", "theorem", "No admissible map from RP^3 to Delta^9",
    statement_short="There is no admissible map $\\mathbb{RP}^3\\to\\Delta^9$, i.e. ten labels do not suffice.",
    assumptions=[], conclusions=["There is no admissible map $\\mathbb{RP}^3\\to\\Delta^9$."], tags=["nonexistence", "combinatorics", "projective_space"])
env("PP14", "F50", "proof", "Proof of Theorem 6.5", proves="TP6",
    statement_short="Contradiction via partner blocks: counting forces block sizes 3,2,2 with three free labels $R$; a triangle $\\{r,s,z\\}$ with $z$ in a 2-block then lies in only one tetrahedron.",
    proof_strategy=["contradiction", "case_analysis"])
p14a = step("PP14", "Assume such a map exists", "|R|=6-t.\n\\]", "contradiction_setup", "Fix a tetrahedron; $t$ blocks and leftover labels $R$")
p14b = step("PP14", "If $t=4$, each block has size two", "Thus $t\\le3$.", "case_split", "Exclude $t=4$")
p14c = step("PP14", "There is no triangle entirely in $R$.", "two\nvertices in a block.", "other", "$R$ contains no triangle")
p14d = step("PP14", "On the other hand, $R$ is contained", "therefore $t\\ge3$.", "bound_estimate", "Hence $|R|\\le3$ and $t\\ge3$")
p14e = step("PP14", "It follows that $t=3$", "Figure~\\ref{fig:partner-blocks}.", "other", "Block sizes $3,2,2$")
p14f = step("PP14", "The complement of $S$ consists of $R$", "block $B$ of size two.", "other", "A triangle $\\{r,s,z\\}$ with $z$ in a 2-block")
p14g = step("PP14", "Every tetrahedron containing $\\{r,s,z\\}$", "Lemma~\\ref{lem:two-tetrahedra}.", "conclude", "That triangle has only one tetrahedron: contradiction")
E(p14a, p14b, conf=0.8); E(p14c, p14d, conf=0.85); E(p14b, p14e, conf=0.85); E(p14d, p14e, conf=0.85)
E(p14c, p14f, conf=0.85); E(p14e, p14f, conf=0.85); E(p14f, p14g, conf=0.85)
E("TP5", "PP14", conf=0.8, basis="named")       # "By purity"

# ============================================================ 7 The diameter obstruction
env("PP15", "F51", "proof", "Proof of Theorem 1.1", proves="TP1",
    statement_short="Combine: Lemma 2.1 gives the geometry and diameter; a ten-set cover would give an admissible $\\mathbb{RP}^3\\to\\Delta^9$ by Lemma 2.4, contradicting Theorem 6.5.",
    proof_strategy=["contradiction"])
p15a = step("PP15", "Lemma~\\ref{lem:projector-geometry}, with $k=4$", "exact diameter $\\sqrt2$.", "apply_lemma", "Geometry and diameter from Lemma 2.1")
p15b = step("PP15", "If ten subsets of strictly", "\\mathbb{RP}^3\\to\\Delta^9$.", "apply_lemma", "A ten-set cover gives an admissible map")
p15c = step("PP15", "This contradicts\nTheorem~\\ref{thm:no-ten-labels}.", "Theorem~\\ref{thm:no-ten-labels}.", "conclude", "Contradiction with Theorem 6.5")
E(p15b, p15c, conf=0.85)
env("CP1", "F52", "corollary", "Borsuk counterexamples in every dimension d>=9", main=True,
    statement_short="Compact counterexamples to Borsuk's conjecture of diameter $\\sqrt2$ exist in every dimension $d\\ge9$.",
    assumptions=["For every integer $d\\geq9$"],
    conclusions=["there is a compact subset of $\\mathbb R^d$ of diameter $\\sqrt2$ that cannot be covered by $d+1$ subsets of strictly smaller diameter"],
    tags=["discrete_geometry", "borsuk_problem", "counterexample"])
env("PP16", "F53", "proof", "Proof of Corollary 7.1", proves="CP1",
    statement_short="Construction: center the projector set and adjoin $s$ points at distance $\\sqrt2$ from everything (Gram matrix $I+\\frac14\\mathbf{1}\\mathbf{1}^T$); each new point needs its own part.",
    proof_strategy=["construction", "contradiction"])
p16a = step("PP16", "The case $d=9$ is Theorem", "$\\|y\\|_F^2=3/4$.", "introduce_variable", "Case $d=9$; center the projector set")
p16b = step("PP16", "In an orthogonal copy of", "for $i\\ne j$.", "introduce_variable", "Adjoin $s$ vectors with Gram matrix $I_s+\\frac14\\mathbf 1\\mathbf 1^T$")
p16c = step("PP16", "Therefore the compact set", "from every other new point.", "other", "The enlarged set has diameter $\\sqrt2$")
p16d = step("PP16", "A subset of $Z$ of strictly smaller", "number of covering sets.", "conclude", "New points need separate parts, leaving ten for $Y$")
E(p16a, p16c, conf=0.85); E(p16b, p16c, conf=0.85); E(p16c, p16d, conf=0.85)

# ============================================================ cross-node edges (passes 1 and 3)
E("CnjP1", "TP1", "resolves", 0.9, "named")      # "Thus Borsuk's assertion fails in dimension nine."
E("CnjP1", "CP1", "resolves", 0.85, "inferred")
E("CnjP1", "TP2", "resolves", 0.9, "named")      # "Kahn and Kalai disproved it"
E("CnjP1", "TP3", "resolves", 0.8, "inferred")
E("LP2", "RP2", conf=0.8, basis="inferred", mention=True)
E("LP1", "RP1", conf=0.6, basis="inferred")
E("ClP1", "PP5", conf=0.8, basis="inferred")    # restriction to a 2-dimensional subspace
E("ClP1", "PP7", conf=0.8, basis="inferred")    # Proposition applied in x_0^perp
E("ClP1", "PP10", conf=0.8, basis="inferred")   # restriction of f to P(x^perp)
E("ClP2", "PP7", conf=0.6, basis="inferred")    # f_*[P(V)] in H_{k-1}(|K|)
E("LP3", "PP7", conf=0.85, basis="named")       # "the subspace formula for the extension"
E("LP4", "PP5", conf=0.85, basis="named")       # "The exact spectral-support property of F"
E("LP4", "PP7", conf=0.85, basis="named")       # "the exact support property", "full-support property"
E("RP3", "PP5", conf=0.7, basis="inferred")     # sphere degree applies to F when m = N_k
E("RP4", "PP7", conf=0.65, basis="inferred")
E("TP4", "PP7", conf=0.75, basis="inferred")    # odd fiber maps G_x have odd degree
E("PrP1", "PP7", conf=0.85, basis="named")      # "By the odd degree of F"
E("ClP2", "LP6", conf=0.6, basis="inferred")

# ============================================================ pass 2: defined terms
L1 = [n for n in nodes if n["type"] not in ("proof_step", "algorithm_step", "equation")]
TERMS = {
    "DP1": [r"\\operatorname\{Sym\}_4"],
    "DP2": [r"\\mathbb P\(V\)", r"\\mathbb P\(\\mathbb R\^k\)"],
    "DP3": [r"P_x", r"P_y"],
    "DP4": [r"\\operatorname\{Sym\}\(V\)", r"N_k", r"N_\{k", r"N_2", r"X_k"],
    "DP5": [r"\\Delta\^", r"\[10\]", r"\[m\]"],
    "DP6": [r"admissib", r"S\(x\)", r"S\(x_0\)"],
    "DP7": [r"support complex", r"\|K\|", r"\$K\$"],
    "DP8": [r"(?<![A-Za-z\\])H\((?!Y)", r"of \$H\$"],
    "DP9": [r"E_V", r"E_W"],
    "DP10": [r"A_\+", r"A_-", r"A_\\pm", r"\\operatorname\{tr\}\|A\|"],
    "DP11": [r"F\(A\)", r"F\^\{-1\}", r"\$F\$", r"extension \$F\$"],
    "DP12": [r"\\Sigma"],
    "DP13": [r"triangle", r"tetrahedr"],
    "DP14": [r"triangle system"],
    "DP15": [r"link graphs? at", r"vertex link", r"link at \$", r"links at"],
    "DP16": [r"edge link", r"link of \$D", r"link vertex", r"link contains", r"Lemma~\\ref\{lem:short-links\}"],
}
SKIP = {("DP13", "DP14"), ("DP15", "DP16"), ("DP15", "LP10"), ("DP15", "PP13"), ("DP16", "PP13")}
SKIP |= {("DP13", "PP7")}
have = {(e["source"], e["target"]) for e in edges}
term_edges = []
for d, pats in TERMS.items():
    ds, de = POS[d]
    for n in L1:
        if n["id"] == d:
            continue
        ns, ne = POS[n["id"]]
        if ns < de:
            continue
        if (d, n["id"]) in SKIP or (d, n["id"]) in have:
            continue
        if any(re.search(p, n["statement"]) for p in pats):
            term_edges.append((d, n["id"]))
for d, t in term_edges:
    E(d, t, "uses", 0.75, "term")
json.dump(term_edges, open(SCR + "/term_edges.json", "w"))

# ============================================================ metadata
NOTES = [
    {"category": "type_uncertain", "nodes": ["CnjP1"],
     "note": "Borsuk's partition problem is phrased as a question ('asks whether') but the abstract calls it Borsuk's conjecture and it is the assertion the paper disproves; typed conjecture (not open_problem), with resolves edges to the disproofs."},
    {"category": "type_uncertain", "nodes": ["LP1"],
     "note": "Lemma 2.1 is marked external (Conway-Hardin-Sloane 1996): the text says the projector metric is the rank-one case of their Grassmannian embedding and that it re-proves it only to fix the normalization; its proof PP1 is paper."},
    {"category": "boundary_uncertain", "nodes": ["TP4"],
     "note": "The cited Borsuk-Ulam facts (Hatcher 2B.6/2B.7) are stated in full in the first sentence of the proof of Proposition 4.1, so they are an external theorem nested in that proof; the oddness-implies-odd-degree part is used again (unrestated) in the proof of Theorem 4.3 (step 'Each fiber therefore contributes an odd number')."},
    {"category": "boundary_uncertain", "nodes": ["ClP4"],
     "note": "The 'First observe' transport principle in the proof of Lemma 6.2 is used again, without restatement, in the proof of Lemma 6.3 ('complementary systems are transported'); extracted as a Level-1 claim nested in PP11 so that use can be recorded."},
    {"category": "unexpected_construct", "nodes": ["PP7"],
     "note": "The proof of Theorem 4.3 is organized by four \\paragraph{} headings not reported as structure labels by latex_facts; each was treated as an author label step (confidence 0.95) with child steps."},
    {"category": "not_extracted", "nodes": [],
     "note": "The 'Proof overview' subsection and the rest of 'History and the method' (dimension records 946, 903, 561, 560, 323, 321, 298, 65, 64; Walkup, Arnoux-Marin) are summary or history and were not made nodes; only the Kahn-Kalai disproof and the previous 63-dimensional record (which Theorem 1.1 improves) were extracted. The b(Y) notation and the T_C notation are used only in their own paragraph and get no definition node."},
    {"category": "not_extracted", "nodes": [],
     "note": "The three TikZ figures (opposite matchings, partner updates, block sizes 3,2,2) are illustrations of steps already in the proofs; two of them sit inside proof environments and so are part of those proofs' verbatim statements but of no step."},
]
meta = {
    "title": "A nine-dimensional counterexample to Borsuk's covering assertion",
    "arxiv_id": "OAI-156",
    "authors": ["OpenAI"],
    "year": 2026,
    "annotator": "agent-extraction",
    "model": "claude-opus-5-5",
    "effort": "default",
    "prompt_version": "v7-86dcfbecdc4d78a5-f5c7dfe",
    "extraction_date": "2026-11-05",
    "rigor_nonformal_count": sum(1 for n in nodes if "rigor" in n),
    "paper_style": ["theorem_proof"],
    "extraction_notes": NOTES,
    "extraction_comment": "Text, proof and Lean formalization were produced by an OpenAI model (OpenAI math release, github.com/openai/math); the Lean code is not part of this LaTeX source and was not extracted.",
}
graph = {"metadata": meta, "nodes": nodes, "edges": edges}
report = finalize(graph, read_tex(TEX))
json.dump(report, open(SCR + "/report.json", "w"), indent=1, default=str)
print("errors", len(report["errors"]))
for e in report["errors"]:
    print("  E", e)
print("warnings", len(report["warnings"]))
for w in report["warnings"]:
    print("  W", w)
if not report["errors"]:
    json.dump(graph, open(OUT if "--write" in sys.argv else SCR + "/draft.json", "w"), indent=1, ensure_ascii=False)
    print("written", len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
