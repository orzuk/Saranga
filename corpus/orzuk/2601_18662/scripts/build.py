#!/usr/bin/env python3
"""Build the SARANGA v7 graph of arXiv 2601.18662 (Dolinsky & Zuk),
'A Unique Inverse Decomposition of Positive Definite Matrices under Linear Constraints'."""
import json, os, re, subprocess, sys
REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize, pseudocode_steps
from latex_facts import read_tex

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = HERE + "/arxiv_src/revision.tex"
OUT = HERE + "/2601_18662.json"
SCR = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_orzuk/2601_18662"
os.makedirs(SCR, exist_ok=True)
FACTS = SCR + "/facts.json"
if not os.path.exists(FACTS):
    subprocess.run(["python3", REPO + "/src/latex_facts.py", TEX, "--out", FACTS], check=True)
facts = json.load(open(FACTS))
SRC = facts["source"]
FX = {f["id"]: f for f in facts["facts"]}
SEC = {s["id"]: (f"{s['number']} {s['title']}" if s["number"] else s["title"]) for s in facts["sections"]}


def clean(t):
    t = re.sub(r"\\label\{[^}]*\}", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _pat(m):
    return re.compile(r"(?:\s|\\label\{[^}]*\})+".join(re.escape(w) for w in m.split()))


def sp(a, b=None, frm=0, end=None):
    """Verbatim span from the first match of `a` (at or after frm) to the end of
    the first match of `b` after it; b=None means up to offset `end`."""
    ma = _pat(a).search(SRC, frm)
    if not ma:
        raise ValueError("start not found: " + a)
    if b is None:
        return clean(SRC[ma.start():end])
    mb = _pat(b).search(SRC, ma.start())
    if not mb:
        raise ValueError("end not found: " + b)
    return clean(SRC[ma.start():mb.end()])


def fx(fid):
    return clean(FX[fid]["statement"])


def sec(fid):
    return SEC[FX[fid]["section"]]


def secid(i):
    return SEC[i]


nodes, edges = [], []
NODE = {}


def N(id, type, name, statement, section, conf, origin="paper", **kw):
    n = {"id": id, "type": type, "name": name, "statement": statement, "section": section,
         "origin": origin, "confidence": conf}
    n.update(kw)
    nodes.append(n)
    NODE[id] = n
    return n


def E(s, t, typ="uses", conf=0.8, basis="term", **kw):
    e = {"source": s, "target": t, "type": typ, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)


PSP = [0]


def steps(parent, fid, specs, section, origin="paper", par=None, first_label_conf=None):
    """specs: list of (start, end, subclass, short[, children][, conf]).
    end may be None = up to the fact's end."""
    out = []
    frm = FX[fid]["start"] if fid else 0
    fend = FX[fid]["end"] if fid else None
    for order, spec in enumerate(specs, 1):
        a, b, sub, short = spec[:4]
        kids = spec[4] if len(spec) > 4 else None
        conf = spec[5] if len(spec) > 5 else 0.75
        PSP[0] += 1
        sid = f"PSP{PSP[0]}"
        st = sp(a, b, frm, end=fend) if b is not None else sp(a, None, frm, end=fend)
        N(sid, "proof_step", short.split(";")[0][:60], st, section, conf, origin,
          parent_id=par or parent, step_order=order, subclass=sub, statement_short=short)
        out.append(sid)
        if kids:
            kid_ids = steps(parent, fid, kids, section, origin, par=sid)
            NODE[sid]["_kids"] = kid_ids
        frm = _pat(a).search(SRC, frm).start() + 1
    return out


EQ = {}
eqn = 0
for f in facts["facts"]:
    if f["kind"] == "equation" and f["id"] != "F42":
        eqn += 1
        EQ[f["id"]] = f"EP{eqn}"


def EQN(fid, name, conf=1.0, **kw):
    N(EQ[fid], "equation", name, fx(fid), sec(fid), conf, **kw)


S1, S2, S21, S22, S23 = secid("S1"), secid("S2"), secid("S3"), secid("S4"), secid("S5")
S3_, S31, S32, S33, S34, S35 = secid("S6"), secid("S7"), secid("S8"), secid("S9"), secid("S10"), secid("S11")
S4_, S5_, S6_, SA, SB, SC = secid("S12"), secid("S13"), secid("S14"), secid("S16"), secid("S17"), secid("S18")
STD = "standard (uncited)"

# ================================================================ Section 2
N("DP1", "definition", "Space of symmetric matrices $\\mathbb{S}^n$ with the Frobenius inner product",
  sp("Let $\\mathbb{S}^n$ denote the space of symmetric real", "induced norm $\\|\\cdot\\|_F$."), S2, 0.9,
  "external", origin_citation=STD, definiendum=["$\\mathbb{S}^n$", "$\\langle X,Y\\rangle_F$", "$\\|\\cdot\\|_F$"])
N("DP2", "definition", "Positive definite and positive semidefinite cones",
  sp("Let $\\mathbb{S}^n_{++} \\subset \\mathbb{S}^n$ be the (open) cone", "cone of positive semidefinite matrices."), S2, 0.9,
  "external", origin_citation=STD, definiendum=["$\\mathbb{S}^n_{++}$", "$\\mathbb{S}^n_{+}$"])
N("DP3", "definition", "Orthogonal complement ${\\mathcal{S}}^\\perp$ of a subspace",
  sp("A linear subspace ${\\mathcal{S}}\\subset\\mathbb{S}^n$ has orthogonal complement", "\\forall\\,Y\\in {\\mathcal{S}}\\,\\}$."), S2, 0.9,
  "external", origin_citation=STD, definiendum="${\\mathcal{S}}^\\perp$",
  differentia=["\\mathrm{tr}(XY)=0\\ \\ \\forall\\,Y\\in {\\mathcal{S}}"])

t1 = fx("F1")
N("TP1", "theorem", "General structured decomposition", t1, S2, 1.0, main=True,
  assumptions=["Let ${\\mathcal{S}}\\subset\\mathbb{S}^n$ be a linear subspace.",
               "If ${\\mathcal{S}}$ contains no nonzero positive semidefinite matrix, that is, \\begin{equation} {\\mathcal{S}} \\cap \\mathbb{S}^n_{+} = \\{0\\}, \\end{equation}",
               "if \\eqref{eq:maindecomposition} admits a solution for even a single $A\\in\\mathbb{S}^n_{++}$"],
  conclusions=["every $A\\in\\mathbb{S}^n_{++}$ admits a \\emph{unique} pair $(B^\\ast \\in \\mathbb{S}^n_{++} \\cap {\\mathcal{S}}^{\\perp}, C^\\ast \\in {\\mathcal{S}})$ such that \\begin{equation} A = {B^\\ast}^{-1} + C^\\ast. \\end{equation}",
               "then \\eqref{eq:nopsddirections} holds."],
  parts=[{"assumptions": ["If ${\\mathcal{S}}$ contains no nonzero positive semidefinite matrix, that is, \\begin{equation} {\\mathcal{S}} \\cap \\mathbb{S}^n_{+} = \\{0\\}, \\end{equation}"],
          "conclusions": ["every $A\\in\\mathbb{S}^n_{++}$ admits a \\emph{unique} pair $(B^\\ast \\in \\mathbb{S}^n_{++} \\cap {\\mathcal{S}}^{\\perp}, C^\\ast \\in {\\mathcal{S}})$ such that \\begin{equation} A = {B^\\ast}^{-1} + C^\\ast. \\end{equation}"]},
         {"assumptions": ["if \\eqref{eq:maindecomposition} admits a solution for even a single $A\\in\\mathbb{S}^n_{++}$"],
          "conclusions": ["then \\eqref{eq:nopsddirections} holds."]}],
  also_stated_at=[sp("Our main contribution is a global existence and uniqueness theorem", "\\cap \\mathbb{S}^n_{+} = \\{0\\}$.")],
  statement_short="Every SPD $A$ splits uniquely as $A=(B^*)^{-1}+C^*$ with $B^*\\succ0$ in ${\\mathcal{S}}^\\perp$ and $C^*\\in{\\mathcal{S}}$ iff ${\\mathcal{S}}$ contains no nonzero PSD matrix.",
  tags=["existence", "uniqueness", "matrix_decomposition"])
EQN("F2", "Nondegeneracy condition ${\\mathcal{S}}\\cap\\mathbb{S}^n_+=\\{0\\}$")
EQN("F3", "Main decomposition $A=(B^*)^{-1}+C^*$")

N("LP1", "lemma", "Boundedness of the feasible set $\\Omega_C$", fx("F4"), S2, 1.0,
  assumptions=["Let $A \\in \\mathbb{S}_{++}^n$ and let ${\\mathcal{S}} \\subset \\mathbb{S}^n$ be a linear subspace satisfying \\eqref{eq:nopsddirections}."],
  conclusions=["Then $\\Omega_C$ is a bounded subset of ${\\mathcal{S}}$.", "In particular, its closure $\\overline{\\Omega_C}$ is compact."],
  statement_short="Under the nondegeneracy condition, $\\{C\\in{\\mathcal{S}}: A-C\\succ0\\}$ is bounded.", tags=["bound", "compactness"])
EQN("F5", "Feasible set $\\Omega_C$")
N("PP1", "proof", "Proof of Lemma (bounded feasible set)", fx("F6"), S2, 1.0, proves="LP1",
  statement_short="By contradiction: normalize an unbounded sequence, extract a limit $X\\in{\\mathcal{S}}$ with $X\\preceq0$, so $-X$ is a nonzero PSD element of ${\\mathcal{S}}$.",
  proof_strategy=["contradiction", "compactness"])
EQN("F7", "Normalized matrices $X^{(k)}$")
EQN("F8", "Quadratic-form bound along the subsequence")
EQN("F9", "Limit of normalized quadratic forms")
pp1 = steps("PP1", "F6", [
    ("Assume by contradiction", "is the Frobenius norm.", "contradiction_setup", "Assume $\\Omega_C$ unbounded; take $\\|C^{(k)}\\|_F\\to\\infty$"),
    ("Define the normalized matrices", "with $\\|X\\|_F = 1$.", "introduce_variable", "Normalize and extract a convergent subsequence $X^{(k_j)}\\to X$"),
    ("Take the corresponding subsequence", "{\\longrightarrow} \\infty$.", "bound_estimate", "Positivity of $A-C^{(k_j)}$ bounds the normalized quadratic forms by a vanishing term"),
    ("But continuity of quadratic forms", "Thus, $X \\preceq 0$.", "bound_estimate", "Pass to the limit: $X\\preceq0$"),
    ("But $X\\neq 0$ and", "must be bounded.", "conclude", "$-X$ is a nonzero PSD element of ${\\mathcal{S}}$, contradiction"),
], S2)

N("PP2", "proof", "Proof of Theorem (general structured decomposition)", fx("F10"), S2, 1.0, proves="TP1",
  statement_short="Variational: decompositions are stationary points of the strictly convex barrier $\\Phi(x)=-\\log\\det(A-C(x))$ on the bounded set $\\Omega_x$, which has a unique minimizer. Necessity: a PSD $X\\in{\\mathcal{S}}$ would give $\\mathrm{tr}(B^*X)>0$.",
  proof_strategy=["direct", "compactness", "contradiction"])
for f, nm in [("F11", "Parametrization $C(x)=\\sum_k x_kD_k$"), ("F12", "Feasible parameter set $\\Omega_x$"),
              ("F13", "$M(x)$, $B(x)$ and the objective $\\Phi(x)$"), ("F14", "Gradient of $\\Phi$"),
              ("F15", "Stationarity $\\nabla\\Phi(x)=0$")]:
    EQN(f, nm)
pp2 = steps("PP2", "F10", [
    ("The proof is divided into three steps.", "Step~3 proves part~\\textbf{(ii)}.", "setup", "Plan: Steps 1-2 prove (i), Step 3 proves (ii)"),
    ("\\emph{Step 1: Reduction", "\\nabla\\Phi(x)=0. \\end{equation}", "other", "Step 1: reduce the decomposition to a stationarity condition of $\\Phi$", [
        ("Let $D_1,...,D_m", "$\\Omega_C = C(\\Omega_x)$.", "introduce_variable", "Parametrize ${\\mathcal{S}}$ by a basis; define $\\Omega_x$"),
        ("For $x \\in \\Omega_x$ let", "k = 1,\\dots,m. \\end{equation}", "algebraic_manipulation", "Define $M,B,\\Phi$; chain rule gives $\\partial_k\\Phi=\\mathrm{tr}(BD_k)$"),
        ("Thus a pair $(B,C)", "\\nabla\\Phi(x)=0. \\end{equation}", "conclude", "Decompositions correspond to stationary points of $\\Phi$"),
    ], 0.95),
    ("\\emph{Step 2: Existence", "This proves part~\\textbf{(i)}.", "other", "Step 2: existence and uniqueness of the minimizer", [
        ("The map $M(x)$ is affine", "\\to +\\infty$ as $k \\to \\infty$.", "bound_estimate", "$\\Phi$ is strictly convex and blows up at $\\partial\\Omega_x$"),
        ("Since $A \\succ 0$ and $C(0)=0$", "is compact.", "apply_lemma", "$\\Omega_x$ nonempty and bounded by the lemma"),
        ("Extend $\\Phi$ to", "satisfying $\\nabla\\Phi(x^\\ast)=0$.", "other", "Lower semicontinuity and compactness give a unique minimizer, the unique stationary point"),
        ("Define $C^\\ast := C(x^\\ast)$", "This proves part~\\textbf{(i)}.", "conclude", "Set $C^*=C(x^*)$, $B^*=(A-C^*)^{-1}$; uniqueness via Step 1"),
    ], 0.95),
    ("\\emph{Step 3: Necessity", None, "contradiction_setup", "Step 3: a nonzero PSD $X\\in{\\mathcal{S}}$ would give $0=\\mathrm{tr}(B^*X)>0$", None, 0.95),
], S2)
E("PP2", "TP1", "proves", 0.9, "named")  # "The proof of Theorem ... then frames ..." (proof not adjacent)

N("RP1", "remark", "Sufficient condition and variational necessity of nondegeneracy", fx("F16"), S2, 1.0,
  statement_short="A positive definite $\\hat B\\perp{\\mathcal{S}}$ suffices for nondegeneracy; without it the log-det objective is unbounded below along $-tX$.")

# ---------------------------------------------------------------- 2.1
N("ClP1", "claim", "Primal log-determinant characterization of $C^*$",
  sp("By Step~2 of the proof of Theorem~\\ref{thm:general_decomposition}, the matrix", "-\\log\\det(A-C) . \\end{equation}"), S21, 0.8,
  assumptions=[], conclusions=["the matrix $C^\\ast$ is the unique minimizer of the strictly convex problem \\begin{equation} \\min_{C\\in\\Omega_C} \\; -\\log\\det(A-C) . \\end{equation}"],
  tags=["optimization", "log_determinant"])
EQN("F17", "Primal log-det problem")
N("PP3", "proof", "Derivation of the dual log-determinant problem",
  sp("The primal problem \\eqref{eq:primal_logdet} can be written", "first-order optimality conditions for $\\Psi_A$."), S21, 0.7,
  statement_short="Lagrangian duality: eliminate $M=A-C$ to get the concave dual $\\Psi_A$, and check that $B^*$ satisfies its first-order conditions using $A=(B^*)^{-1}+C^*$.",
  proof_strategy=["dual_argument", "direct"])
steps("PP3", None, [
    ("The primal problem \\eqref{eq:primal_logdet} can be written", "yields the dual problem stated below:", "setup", "Rewrite with $M=A-C$; Lagrange multiplier $B\\in{\\mathcal{S}}^\\perp$; eliminate $M$"),
    ("Let $(B^\\ast \\in \\mathbb{S}^n_{++} \\cap {\\mathcal{S}}^{\\perp},\\, C^\\ast", "=\\mathrm{tr}(BA)$.", "algebraic_manipulation", "Orthogonality gives $\\mathrm{tr}((A-C)B)=\\mathrm{tr}(BA)$"),
    ("The function \\[ \\Psi_A(B):=", "\\forall X\\in {\\mathcal{S}}^\\perp . \\]", "introduce_variable", "Introduce the concave dual objective $\\Psi_A$ and its gradient"),
    ("Moreover, using the decomposition $A={B^\\ast}^{-1}+C^\\ast$", "first-order optimality conditions for $\\Psi_A$.", "conclude", "$B^*$ satisfies the first-order conditions of $\\Psi_A$"),
], S21)
N("ClP2", "claim", "Dual characterization: $B^*$ maximizes the dual log-det problem",
  sp("Since $\\log\\det(B)$ is strictly concave on", "\\log\\det(B)-\\mathrm{tr}(BA)+n. \\end{equation}"), S21, 0.75,
  assumptions=["Since $\\log\\det(B)$ is strictly concave on $\\mathbb{S}^n_{++} \\cap {\\mathcal{S}}^\\perp$"],
  conclusions=["$B^\\ast$ is the unique maximizer of the dual problem \\begin{equation} \\max_{B\\succ 0,\\; B\\in {\\mathcal{S}}^{\\perp}} \\log\\det(B)-\\mathrm{tr}(BA)+n. \\end{equation}"],
  tags=["duality", "optimization", "log_determinant"])
EQN("F18", "Dual log-det problem",
    also_stated_at=[sp("\\begin{equation} \\max_{B\\succ0,\\; B\\in {\\mathcal{S}}^\\perp}\\;\\; \\log\\det(B)-\\mathrm{tr}(AB)+n.", "\\end{equation}", FX["F42"]["outer_start"] - 5)])
N("ClP3", "claim", "Strong duality between the primal and dual log-det problems",
  sp("Since the primal problem \\eqref{eq:primal_logdet} is convex and strictly", "optimal values coincide."), S21, 0.75,
  rigor="semi_formal", assumptions=["Since the primal problem \\eqref{eq:primal_logdet} is convex and strictly feasible,"],
  conclusions=["strong duality holds, and the primal and dual optimal values coincide."], tags=["duality"])
N("RP2", "remark", "Dual problem as an alternative computational route",
  sp("Accordingly, the dual problem \\eqref{eq:dual_logdet} provides", "naturally expressed in terms of $B$."), S21, 0.75,
  statement_short="Optimize over $B$ directly; primal preferable for small $\\dim{\\mathcal{S}}$, dual for small $\\dim{\\mathcal{S}}^\\perp$.")

# ---------------------------------------------------------------- 2.2
N("DP4", "definition", "Orthogonal group ${\\mathcal{O}}(n)$",
  sp("Let ${\\mathcal{O}}(n)$ denote the set of all", "orthogonal matrices."), S22, 0.9, "external", origin_citation=STD,
  definiendum="${\\mathcal{O}}(n)$")
N("DP5", "definition", "Action by conjugation",
  sp("For $P \\in {\\mathcal{O}}(n)$, consider the action on", "denotes transposition)."), S22, 0.85, "external",
  origin_citation=STD, definiendum="action by conjugation")
N("ClP4", "claim", "Equivariance of the decomposition under orthogonal conjugation",
  sp("From the equality \\[ \\mathrm{tr}\\!\\left(P B^\\ast P^\\top", "P {\\mathcal{S}} P^\\top . $"), S22, 0.8,
  assumptions=[], conclusions=[],
  statement_short="Conjugating $A$ and ${\\mathcal{S}}$ by an orthogonal $P$ conjugates both components of the decomposition.", tags=["symmetry"])
N("DP6", "definition", "Group $\\mathcal G$ acting by conjugation",
  sp("Let $\\mathcal G \\subset {\\mathcal{O}}(n)$ act on $\\mathbb{S}^n$ by conjugation,", "X \\mapsto P X P^\\top . $"), S22, 0.85,
  definiendum="$\\mathcal G$")
N("DP7", "definition", "$\\mathcal G$-fixed matrix and $\\mathcal G$-invariant subspace",
  sp("Assume that $A$ is $\\mathcal G$-fixed", "\\quad \\forall P \\in \\mathcal G. $"), S22, 0.75,
  definiendum=["$\\mathcal G$-fixed", "$\\mathcal G$-invariant"])
N("ClP5", "claim", "Inheritance of group symmetry",
  sp("By the above analysis and the uniqueness of the decomposition", "\\end{equation}"), S22, 0.8,
  assumptions=[], conclusions=["the decomposition is then $\\mathcal G$-fixed:"],
  statement_short="If $A$ is $\\mathcal G$-fixed and ${\\mathcal{S}}$ is $\\mathcal G$-invariant then $B^*$ and $C^*$ are $\\mathcal G$-fixed.", tags=["symmetry", "uniqueness"])
EQN("F19", "$\\mathcal G$-fixedness of $B^*$ and $C^*$")
N("ClP6", "claim", "Determinant inequality $\\det(B^*)\\le\\det(A^{-1})$",
  sp("From the primal representation,", "\\det(B^\\ast) \\le \\det(A^{-1}). \\end{equation}"), S22, 0.8,
  assumptions=[], conclusions=["\\det({B^\\ast}^{-1}) \\ge \\det(A), \\quad\\text{i.e.}\\quad \\det(B^\\ast) \\le \\det(A^{-1})."],
  statement_short="Comparing the primal objective at $C=0$ and $C^*$ gives $\\det((B^*)^{-1})\\ge\\det(A)$.", tags=["bound", "determinant"])
EQN("F20", "Determinant inequality")
N("ClP7", "claim", "Decomposition of the inverse $A^{-1}$",
  sp("Define the transformed subspace", "is the unique decomposition of \\(A^{-1}\\) associated with \\(\\hat {\\mathcal{S}}\\)."), S22, 0.8,
  assumptions=[], conclusions=["\\((\\hat B,\\hat C) \\in \\mathbb{S}^n_{++} \\times \\hat {\\mathcal{S}}\\) is the unique decomposition of \\(A^{-1}\\) associated with \\(\\hat {\\mathcal{S}}\\)."],
  statement_short="$A^{-1}=(AB^*A)^{-1}+A^{-1}C^*A^{-1}$ is the decomposition of $A^{-1}$ for $\\hat{\\mathcal{S}}=A^{-1}{\\mathcal{S}}A^{-1}$.", tags=["uniqueness"])
EQN("F21", "Transformed components $\\hat B$, $\\hat C$")

# ---------------------------------------------------------------- 2.3
N("DP8", "definition", "Decomposition map $A\\mapsto(B^*(A),C^*(A))$",
  sp("By Theorem~\\ref{thm:general_decomposition} each $A\\in\\mathbb{S}^n_{++}$ determines a unique", "\\big(B^{*}(A),C^{*}(A)\\big)$."), S23, 0.85,
  definiendum=["$B^{*}(A)$", "$C^{*}(A)$"])
N("AssumP1", "assumption", "Nonzero constraint subspace",
  sp("Assume throughout that ${\\mathcal{S}}\\neq\\{0\\}$", "$B^{*}(A)=A^{-1}$)."), S23, 0.85)
N("DP9", "definition", "Curvature constant $\\alpha(B,{\\mathcal{S}})$",
  sp("For $B\\in\\mathbb{S}^n_{++}$ set \\begin{equation}", "at the point $C$ with $B=(A-C)^{-1}$."), S23, 0.9,
  definiendum="$\\alpha(B,{\\mathcal{S}})$",
  statement_short="$\\alpha(B,{\\mathcal{S}})$ is the minimum of $\\mathrm{tr}(BXBX)$ over unit $X\\in{\\mathcal{S}}$, the minimal curvature of the log-det objective along ${\\mathcal{S}}$.")
EQN("F22", "Definition of $\\alpha(B,{\\mathcal{S}})$")
N("LP2", "lemma", "Positivity and Lipschitz continuity of $\\alpha$", fx("F23"), S23, 1.0,
  assumptions=["Let $B,B'\\in\\mathbb{S}^n_{++}$ and let ${\\mathcal{S}}\\subset\\mathbb{S}^n$ be a nonzero linear subspace."],
  conclusions=["$0<\\lambda_{\\min}(B)^2\\le\\alpha(B,{\\mathcal{S}})\\le\\|B\\|_2^2$.",
               "$\\big|\\alpha(B',{\\mathcal{S}})-\\alpha(B,{\\mathcal{S}})\\big|\\le\\big(\\|B'\\|_2+\\|B\\|_2\\big)\\,\\|B'-B\\|_2$."],
  statement_short="$\\lambda_{\\min}(B)^2\\le\\alpha(B,{\\mathcal{S}})\\le\\|B\\|_2^2$, and $\\alpha$ is Lipschitz in $B$ with constant $\\|B'\\|_2+\\|B\\|_2$.",
  tags=["bound", "lipschitz"])
N("PP4", "proof", "Proof of Lemma (positivity and Lipschitz continuity of $\\alpha$)", fx("F24"), S23, 1.0, proves="LP2",
  statement_short="Write $\\mathrm{tr}(BXBX)=\\|B^{1/2}XB^{1/2}\\|_F^2$ and bound it; for (ii) expand the difference of traces and use Cauchy-Schwarz.",
  proof_strategy=["direct", "algebraic_manipulation"])
pp4 = steps("PP4", "F24", [
    ("\\textbf{(i)} For $X\\in\\mathbb{S}^n$,", "because $\\lambda_{\\min}(B)>0$ for $B\\in\\mathbb{S}^n_{++}$.", "bound_estimate", "(i): sandwich $\\|B^{1/2}XB^{1/2}\\|_F$ between $\\lambda_{\\min}(B)\\|X\\|_F$ and $\\|B\\|_2\\|X\\|_F$", None, 0.95),
    ("\\textbf{(ii)} For every $X\\in\\mathbb{S}^n$,", None, "bound_estimate", "(ii): bound the difference of the traces pointwise, then of their minima", None, 0.95),
], S23)
N("DP10", "definition", "Restricted condition number $\\kappa(B,{\\mathcal{S}})$",
  sp("Part~\\textbf{(i)} gives $\\alpha(B,{\\mathcal{S}})>0$, so we may write", "\\lambda_{\\max}(B)/\\lambda_{\\min}(B)$."), S23, 0.9,
  definiendum="$\\kappa(B,{\\mathcal{S}})$", genus="restricted condition number",
  statement_short="$\\kappa(B,{\\mathcal{S}})=\\|B\\|_2/\\sqrt{\\alpha(B,{\\mathcal{S}})}$, between 1 and the condition number of $B$.")
EQN("F27", "Definition of $\\kappa(B,{\\mathcal{S}})$")
p1 = fx("F28")
N("PrP1", "proposition", "Local stability of the decomposition", p1, S23, 1.0, main=True,
  assumptions=["Let $A\\in\\mathbb{S}^n_{++}$ with decomposition $(B^{*},C^{*})$ given by Theorem~\\ref{thm:general_decomposition} for a nonzero subspace ${\\mathcal{S}}$, and let $\\widetilde A=A+\\Delta\\in\\mathbb{S}^n_{++}$ have decomposition $(\\widetilde B,\\widetilde C)$ for the same ${\\mathcal{S}}$.",
               "If $\\varepsilon<1-\\tfrac1{\\sqrt2}$"],
  conclusions=["\\|\\widetilde C-C^{*}\\|_F &\\le \\frac{\\kappa(B^{*},{\\mathcal{S}})}{\\sqrt{1-4\\varepsilon+2\\varepsilon^{2}}}\\,\\|\\Delta\\|_F,",
               "\\|\\widetilde B-B^{*}\\|_2 &\\le \\frac{\\|B^{*}\\|_2^{2}}{1-\\|B^{*}\\|_2\\|\\Delta\\|_F}\\,\\|\\Delta\\|_F."],
  statement_short="For a perturbation with $\\varepsilon=\\|B^*\\|_2^3\\|\\Delta\\|_F/\\alpha(B^*,{\\mathcal{S}})<1-1/\\sqrt2$, $C^*$ moves by $O(\\kappa\\|\\Delta\\|_F)$ and $B^*$ by $O(\\|B^*\\|_2^2\\|\\Delta\\|_F)$.",
  tags=["stability", "perturbation", "bound"])
EQN("F29", "Smallness parameter $\\varepsilon$")
EQN("F30", "Stability bound for $C^*$")
EQN("F102", "Stability bound for $B^*$")
N("RP3", "remark", "Interpretation of the stability bounds", fx("F31"), S23, 1.0,
  statement_short="The $B$-bound is free of $\\alpha$; the $C$-bound degrades with $\\kappa$; both recover the infinitesimal rates as $\\Delta\\to0$.")
N("CP1", "corollary", "Uniform stability on compact sets", fx("F32"), S23, 1.0,
  assumptions=["Let ${\\mathcal{S}}$ be nonzero and let $\\Theta\\subset\\mathbb{S}^n_{++}$ be nonempty, compact and convex,",
               "for all $A,\\widetilde A\\in\\Theta$,"],
  conclusions=["\\|C^{*}(\\widetilde A)-C^{*}(A)\\|_F\\le\\frac{\\beta_0}{\\sqrt{\\alpha_0}}\\,\\|\\widetilde A-A\\|_F,",
               "\\|B^{*}(\\widetilde A)-B^{*}(A)\\|_2\\le \\beta_0^{2}\\,\\|\\widetilde A-A\\|_F ."],
  statement_short="On a compact convex $\\Theta$, $C^*$ and $B^*$ are Lipschitz with constants $\\beta_0/\\sqrt{\\alpha_0}$ and $\\beta_0^2$.",
  tags=["stability", "lipschitz"])

# ================================================================ Section 3
N("ProbP1", "problem", "Primal convex program for the decomposition",
  sp("Writing $C(x)=\\sum_{k=1}^m x_k D_k$", "$B^\\ast=M(x^\\ast)^{-1}$."), S3_, 0.85,
  statement_short="Minimize $\\Phi(x)=-\\log\\det(A-C(x))$ over $\\Omega_x$; then $C^*=C(x^*)$, $B^*=M(x^*)^{-1}$.",
  tags=["optimization", "log_determinant"])
EQN("F33", "Primal problem in coordinates $x$")
N("ClP8", "claim", "Hessian of $\\Phi$",
  sp("Differentiating once more yields the Hessian", "k,\\ell=1,\\dots,m. \\end{equation}"), S31, 0.8,
  assumptions=[], conclusions=["\\frac{\\partial^2\\Phi}{\\partial x_k\\partial x_\\ell}(x) = \\mathrm{tr}\\big(B(x)D_kB(x)D_\\ell\\big),"],
  tags=["derivatives"])
EQN("F34", "Hessian formula")
N("ClP9", "claim", "Positive definiteness of the Hessian; strict convexity of $\\Phi$",
  sp("Writing $D(v):=\\sum_{\\ell=1}^m v_\\ell D_\\ell$", "$\\Phi$ is strictly convex on $\\Omega_x$."), S31, 0.8,
  assumptions=["Writing $D(v):=\\sum_{\\ell=1}^m v_\\ell D_\\ell$ for $v\\in\\mathbb{R}^m$"],
  conclusions=["Thus $H(x)\\succ0$ for all $x\\in\\Omega_x$, and $\\Phi$ is strictly convex on $\\Omega_x$."],
  statement_short="$v^\\top H(x)v=\\|B^{1/2}D(v)B^{1/2}\\|_F^2>0$ for $v\\ne0$, so $\\Phi$ is strictly convex.", tags=["convexity"])
N("RP4", "remark", "Analytic derivatives via linear solves with $M(x)$",
  sp("All derivatives of $\\Phi$ are computed using explicit", "at cost $O(n^3)$."), S31, 0.75,
  statement_short="Derivatives need only solves with $M(x)$; in structured cases only entries of $M^{-1}$ on the supports of the $D_k$.")
N("ClP10", "claim", "Hessian-vector product formula",
  sp("The Newton-CG method requires only Hessian-vector products.", "same linear solves with $M(x)$."), S31, 0.8,
  assumptions=["With $D(v)$ as above,"],
  conclusions=["\\big(H(x)v\\big)_k = \\mathrm{tr}\\big(B(x)D_kB(x)D(v)\\big),"], tags=["derivatives"])
EQN("F35", "Hessian-vector product")
N("AP1", "algorithm", "Newton-CG with feasibility-preserving backtracking",
  sp("At a current iterate $x\\in\\Omega_x$", "sufficient decrease of $\\Phi$."), S32, 0.8, main=True,
  statement_short="Newton's method on $\\Phi$ with the Newton system solved by matrix-free CG and Armijo backtracking that keeps $A-C(x)\\succ0$.",
  input=["At a current iterate $x\\in\\Omega_x$"], output=[], tags=["optimization", "newton_method"])
for i, (a, b, sub, sh) in enumerate([
        ("At a current iterate $x\\in\\Omega_x$, let", "$H=\\nabla^2\\Phi(x)$.", "compute", "Compute gradient and Hessian at the iterate"),
        ("The Newton direction $d$ is defined implicitly", "given by \\eqref{eq:Hv_formula}.", "solve", "Solve the Newton system by CG with Hessian-vector products"),
        ("Step sizes are chosen by backtracking", "sufficient decrease of $\\Phi$.", "select", "Backtracking step keeping $M(x+td)\\succ0$ with sufficient decrease")], 1):
    N(f"ASP{i}", "algorithm_step", sh, sp(a, b), S32, 0.75, parent_id="AP1", step_order=i, subclass=sub, statement_short=sh)
ASPN = 3
EQN("F36", "Newton system $H(x)d=-g(x)$")
N("PP5", "proof", "Argument for global convergence of Newton-CG",
  sp("The objective $\\Phi(x)=-\\log\\det\\bigl(A-C(x)\\bigr)$ is strictly convex and self-concordant", "bounded away from $\\partial\\Omega_x$."), S32, 0.7,
  rigor=None, statement_short="Self-concordance of the log-det barrier composed with an affine map, plus compact sublevel sets from the theorem and lemma.",
  proof_strategy=["direct"])
NODE["PP5"].pop("rigor")
N("ClP11", "claim", "Global convergence of feasibility-preserving Newton-CG",
  sp("Consequently, Newton-CG with feasibility-preserving Armijo backtracking", "\\eta_k\\le\\bar\\eta<1 . \\end{equation}"), S32, 0.8,
  main=True, rigor="semi_formal",
  assumptions=["provided each CG solve is terminated by an inexact-Newton forcing condition \\begin{equation} \\|H(x_k)d_k+g(x_k)\\|_2\\le\\eta_k\\,\\|g(x_k)\\|_2, \\qquad \\eta_k\\le\\bar\\eta<1 . \\end{equation}"],
  conclusions=["Newton-CG with feasibility-preserving Armijo backtracking is globally convergent from any feasible initialization,"],
  tags=["convergence", "newton_method"])
EQN("F37", "Inexact-Newton forcing condition")
N("ClP12", "claim", "CG iterates are descent directions",
  sp("Started from $d=0$, every CG iterate", "since $H(x_k)\\succ0$."), S32, 0.7, rigor="semi_formal",
  assumptions=["Started from $d=0$,"], conclusions=["every CG iterate is a descent direction,"], tags=["convergence"])
N("ClP13", "claim", "Local convergence rates under the forcing sequence",
  sp("The \\emph{local} rate is governed by the forcing sequence", "nocedal2006numerical}."), S32, 0.75, rigor="semi_formal",
  assumptions=[], conclusions=["$\\eta_k\\le\\bar\\eta<1$ gives a linear rate, $\\eta_k\\to0$ a superlinear one, and $\\eta_k=O(\\|g(x_k)\\|_2)$ a quadratic one,"],
  statement_short="Linear, superlinear or quadratic local rate according to the forcing sequence (standard inexact-Newton theory).",
  tags=["convergence", "rate"])

# ---------------------------------------------------------------- 3.3
N("RP5", "remark", "Per-iteration cost of dense Newton-CG",
  sp("The dense bounds assume unstructured basis matrices", "corresponding structured solve cost."), S33, 0.75,
  statement_short="Dense Newton-CG costs $O(n^3+N_{cg}(n^3+mn^2))$ per outer iteration; precomputing $M^{-1}D_k$ pays only for many CG steps.",
  tags=["complexity"])
N("RP6", "remark", "Banded setting: structure-preserving solves and traces",
  sp("In the banded setting, both $A$ and the constraint subspace", "this term reduces to $O(m)$."), S33, 0.75,
  statement_short="If $M(x)$ stays banded, solves cost $O(nb^2)$ and traces $O(b^2)$ via sparse-inverse (Takahashi) recursions.",
  tags=["complexity", "banded"])
N("RP7", "remark", "Banded Hessian-vector products", fx("F38"), S33, 1.0, rigor="semi_formal",
  statement_short="The band of $G=M^{-1}D(v)M^{-1}$ is a directional derivative of the selected inverse and is computable in $O(nb^2)$ by differentiating the block Takahashi recursion.",
  tags=["complexity", "banded"])
EQN("F40", "$G$ as a derivative of the inverse")
N("RP8", "remark", "Circulant setting: FFT diagonalization",
  sp("In the circulant setting, $A$ and the basis matrices", "gohberg1994fast}."), S33, 0.75,
  statement_short="Circulant $M(x)$ is diagonalized by the DFT, so Hessian-vector products are pointwise products after two FFTs.",
  tags=["complexity", "circulant"])
EQN("F41", "Circulant Hessian-vector product")
N("RP9", "remark", "General Toeplitz setting",
  sp("For a general Toeplitz $M(x)$, linear solves remain fast", "retains the dense bound."), S33, 0.75,
  tags=["complexity", "toeplitz"])

# ---------------------------------------------------------------- 3.4
N("DP11", "definition", "Basis $\\{E_k\\}$ of ${\\mathcal{S}}^\\perp$ and dual dimension $m^\\perp$",
  sp("Let $\\{E_1,\\dots,E_{m^\\perp}\\}$ be a basis of ${\\mathcal{S}}^\\perp$", "\\end{equation}"), S34, 0.9,
  definiendum=["$\\{E_1,\\dots,E_{m^\\perp}\\}$", "$m^\\perp$"])
EQN("F43", "Dual dimension $m^\\perp$")
N("DP12", "definition", "Dual parametrization $B(y)$",
  sp("Fix any $B_0\\in {\\mathcal{S}}^\\perp\\cap\\mathbb{S}^n_{++}$ and write", "\\end{equation}"), S34, 0.9,
  definiendum=["$B_0$", "$B(y)$"])
EQN("F44", "Dual parametrization")
N("RP10", "remark", "Feasible initialization of the dual",
  sp("Unlike the primal formulation, which is always initialized", "banded and group-invariant settings."), S34, 0.75,
  statement_short="The dual needs a feasible $B_0$ (a phase-one SDP in general); $B_0=I_n$ works when ${\\mathcal{S}}$ has zero diagonal.")
N("DP13", "definition", "Dual objective $\\Psi(y)$",
  sp("Define \\begin{equation} \\Psi(y) :=", "\\end{equation}"), S34, 0.9, definiendum="$\\Psi(y)$")
EQN("F45", "Dual objective in coordinates")
N("ClP14", "claim", "Gradient and Hessian of the dual objective",
  sp("Then \\begin{align} \\frac{\\partial\\Psi}{\\partial y_k}(y)", "\\end{align}"), S34, 0.8,
  assumptions=[], conclusions=[sp("\\frac{\\partial\\Psi}{\\partial y_k}(y) &=", "\\end{align}")[:-len("\\end{align}")].strip()],
  tags=["derivatives", "duality"])
EQN("F46", "Dual gradient and Hessian")

# ---------------------------------------------------------------- 3.5
N("AssumP2", "assumption", "Finite symmetry group with $A$ and ${\\mathcal{S}}$ invariant",
  sp("Assume that a finite group $\\mathcal G\\subset{\\mathcal{O}}(n)$", "are $\\mathcal G$-invariant."), S35, 0.85)
N("DP14", "definition", "Fixed-point subspace ${\\mathcal{S}}^{\\mathcal G}$ and $m_{\\mathcal G}$",
  sp("Define \\begin{equation} {\\mathcal{S}}^{\\mathcal G} :=", "\\end{equation}"), S35, 0.9,
  definiendum=["${\\mathcal{S}}^{\\mathcal G}$", "$m_{\\mathcal G}$"])
EQN("F47", "Fixed-point subspace")
N("ClP15", "claim", "Reduction of the optimization to the fixed-point subspace",
  sp("By \\eqref{eq:G_fixed}, the unique minimizer", "with the reduced derivatives."), S35, 0.8,
  assumptions=[], conclusions=["the unique minimizer $C^\\ast$ lies in ${\\mathcal{S}}^{\\mathcal G}$.", "the optimization problem reduces to dimension $m_{\\mathcal G}$."],
  tags=["symmetry", "dimension_reduction"])
EQN("F48", "Reduced parametrization")
N("RP11", "remark", "Per-iteration cost of group-invariant Newton-CG",
  sp("The per-iteration cost is that of Table~\\ref{tab:per_iteration_complexity} with", "outside the per-iteration cost."), S35, 0.75,
  statement_short="Symmetry reduces the number of traces to $m_{\\mathcal G}$ but not the $n\\times n$ linear algebra; the change of basis is a one-time cost.",
  tags=["complexity", "symmetry"])
EQN("F49", "Group-invariant dense cost")
N("RP12", "remark", "Block-permutation symmetry: cost independent of $n$",
  sp("Further reduction occurs when the symmetry shrinks $M(x)$ itself.", "m_{\\mathcal G}\\le r(r+1)/2 . \\end{equation}"), S35, 0.75,
  statement_short="When $\\mathcal G$ acts by blocks, every invariant matrix has $O(r^2)$ coefficients and an iteration costs $O(r^3+N_{cg}(r^3+m_{\\mathcal G}r^2))$.",
  tags=["complexity", "symmetry"])
EQN("F50", "Block-permutation cost")
N("RP13", "remark", "Cost of the symmetry-adapted transform", fx("F51"), S35, 1.0, tags=["complexity"])

# ================================================================ Section 4
N("DP15", "definition", "Time horizon $N$", sp("Let \\(N\\in\\mathbb{N}\\) denote", "the time horizon."), S4_, 0.85, definiendum="$N$")
N("DP16", "definition", "Tradable assets and their increments $X^i_j$",
  sp("At each time \\(i=1,\\dots,N\\), suppose that", "X^i_1,\\dots,X^i_{p_i}. $"), S4_, 0.85, definiendum=["$p_i$", "$X^i_j$"])
N("DP17", "definition", "Non-tradable risk factors $X^i_{p_i+1},\\dots,X^i_{q_i}$",
  sp("In addition, we allow for further random variables", "not tradable at time \\(i\\)."), S4_, 0.85, definiendum="$q_i$")
N("DP18", "definition", "Information vector $Y^i$",
  sp("The information available for trading at time \\(i\\) is generated", "is a deterministic matrix."), S4_, 0.85,
  definiendum=["$Y^i$", "$m_i$", "$A^i$"],
  statement_short="The information at time $i$ is a fixed linear transform $Y^i$ of all past increments.")
N("AssumP3", "assumption", "Gaussian increments $Z\\sim\\mathcal N(0,\\Sigma)$",
  sp("Let \\(n=\\sum_{i=1}^N q_i\\), and assume", "covariance matrix \\(\\Sigma\\in\\mathbb{S}^n_{++}\\)."), S4_, 0.85)
N("DP19", "definition", "Precision matrix $\\Lambda$",
  sp("Denote by \\({\\Lambda}=\\Sigma^{-1}\\)", "precision matrix."), S4_, 0.9, definiendum="${\\Lambda}$")
N("DP20", "definition", "Trading strategy $\\gamma$",
  sp("A trading strategy is a random vector", "with increment \\(X^i_j\\)."), S4_, 0.9,
  definiendum="trading strategy", genus="random vector")
N("DP21", "definition", "Measurability of positions",
  sp("The position \\(\\gamma^i_j\\) is required to be", "\\end{equation}"), S4_, 0.85, definiendum="$g^i_j$")
EQN("F52", "Positions as measurable functions of $Y^i$")
N("DP22", "definition", "Terminal portfolio value $V^\\gamma$",
  sp("The corresponding terminal portfolio value is", "\\end{equation}"), S4_, 0.9, definiendum="$V^\\gamma$")
EQN("F53", "Terminal portfolio value")
N("DP23", "definition", "Admissible strategies $\\mathcal A$",
  sp("We denote by \\(\\mathcal A\\) the set of all trading strategies", "well defined."), S4_, 0.9, definiendum="$\\mathcal A$")
N("DP24", "definition", "Linear strategies $\\mathcal A_l$",
  sp("Let \\(\\mathcal A_l \\subset \\mathcal A\\) be the set", "($g^i_j(0)=0$)."), S4_, 0.9, definiendum="$\\mathcal A_l$")
N("ClP16", "claim", "Linear strategies give quadratic, integrable terminal values",
  sp("For these $V^\\gamma$ is a quadratic form in $Z$", "holds automatically."), S4_, 0.7, rigor="semi_formal",
  assumptions=["For these"], conclusions=["$V^\\gamma$ is a quadratic form in $Z$ and the integrability requirement holds automatically."])
N("DP25", "definition", "Representing matrices $D^{i,j,k}$",
  sp("For any \\(i=1,\\ldots,N\\), \\(j=1,\\ldots,p_i\\), and \\(k=1,\\ldots,m_i\\), the product", "representing this quadratic form."), S4_, 0.85,
  definiendum="$D^{i,j,k}$")
EQN("F54", "Quadratic-form representation of $Y^i_kX^i_j$")
N("ClP17", "claim", "The matrices $D^{i,j,k}$ have zero diagonal",
  sp("Since the random vector $Y^i$ is", "is a zero-diagonal matrix."), S4_, 0.75,
  assumptions=["Since the random vector $Y^i$ is determined by $X^r_j$, $r<i$, $j=1,\\ldots,q_r$,"],
  conclusions=["$D^{i,j,k}$ is a zero-diagonal matrix."])
N("DP26", "definition", "Strategy subspace ${\\mathcal{D}}$",
  sp("Let \\({\\mathcal{D}}\\subset\\mathbb{S}^n\\) denote the linear span", "of the form \\(D^{i,j,k}\\)."), S4_, 0.9, definiendum="${\\mathcal{D}}$")
N("ClP18", "claim", "Linear strategies correspond to matrices in ${\\mathcal{D}}$",
  sp("A strategy \\(\\gamma\\) lies in \\(\\mathcal A_l\\) if and only if", "\\end{equation}"), S4_, 0.75, rigor="semi_formal",
  assumptions=[], conclusions=[sp("A strategy \\(\\gamma\\) lies in \\(\\mathcal A_l\\) if and only if", "\\end{equation}")],
  equivalent_conditions=["A strategy \\(\\gamma\\) lies in \\(\\mathcal A_l\\)", "there exists $X\\in{\\mathcal{D}}$ such that"])
EQN("F55", "Linear strategy as a quadratic form")
N("DP27", "definition", "Exponential utility",
  sp("The investor’s preferences are described by the exponential utility function", "parameter \\(\\rho>0\\)."), S4_, 0.9,
  definiendum=["$u$", "$\\rho$"])
N("ProbP2", "problem", "Exponential utility maximization",
  sp("The optimization problem is therefore", "denotes expectation with respect to it."), S4_, 0.9,
  statement_short="Maximize $\\mathbb E_{\\mathbb P}[-\\exp(-\\rho V^\\gamma)]$ over admissible strategies.", tags=["optimization", "utility_maximization"])
EQN("F56", "Exponential utility maximization problem")
N("RP14", "remark", "Normalization of risk aversion to $\\rho=1$",
  sp("For any $\\gamma\\in\\mathcal A$ and \\(\\lambda\\in\\mathbb{R}\\) we have", "we set \\(\\rho:=1\\)."), S4_, 0.75)
N("RP15", "remark", "Utility maximization as a log-det problem over ${\\mathcal{D}}$",
  sp("By \\eqref{eq:v_gamma_bilinear}, a linear trading strategy corresponds", "over the subspace \\({\\mathcal{D}}\\)."), S4_, 0.75)
N("PrP2", "proposition", "Optimal exponential-utility portfolio via the constrained decomposition", fx("F57"), S4_, 1.0, main=True,
  assumptions=[],
  conclusions=["There exists a unique decomposition \\begin{equation} {\\Lambda}=\\hat Q^{-1}+\\hat\\Gamma, \\ \\ \\hat Q\\succ 0, \\ \\ \\hat Q\\in {\\mathcal{D}}^{\\perp}, \\ \\ \\hat\\Gamma\\in{\\mathcal{D}}. \\end{equation}",
               "The maximizer $\\hat\\gamma$ for the optimization problem \\eqref{eq:exp_util} is unique (and lies in $\\mathcal A_l$) with terminal wealth given by \\begin{equation} V^{\\hat\\gamma}=-\\frac{1}{2} Z \\hat\\Gamma Z^{\\top}. \\end{equation}",
               "The corresponding value is given by \\begin{equation} \\mathbb E_{\\mathbb P}\\left[-\\exp\\left(- V^{\\hat\\gamma}\\right)\\right]=-\\sqrt{\\frac{\\det(\\hat Q)}{\\det(\\Sigma)}}. \\end{equation}"],
  statement_short="Decompose $\\Lambda=\\hat Q^{-1}+\\hat\\Gamma$ with $\\hat Q\\in{\\mathcal{D}}^\\perp$, $\\hat\\Gamma\\in{\\mathcal{D}}$; the unique optimal strategy is linear with $V=-\\frac12 Z\\hat\\Gamma Z^\\top$ and value $-\\sqrt{\\det\\hat Q/\\det\\Sigma}$.",
  tags=["utility_maximization", "existence", "uniqueness", "mathematical_finance"])
for f, nm in [("F58", "Finance decomposition $\\Lambda=\\hat Q^{-1}+\\hat\\Gamma$"), ("F59", "Optimal terminal wealth"), ("F60", "Optimal value")]:
    EQN(f, nm)
N("RP16", "remark", "Scope of the Gaussian exponential-utility framework", fx("F61"), S4_, 1.0)
N("PP6", "proof", "Proof of Proposition (exponential utility)", fx("F62"), S4_, 1.0, proves="PrP2",
  statement_short="Duality via change of measure: ${\\mathcal{D}}$ has no PSD element so the theorem gives $\\hat Q$; under $\\hat{\\mathbb Q}$ every gain has mean zero, Fenchel's inequality $xy\\le e^x+y(\\log y-1)$ gives a lower bound attained by the linear candidate.",
  proof_strategy=["dual_argument", "construction", "direct"])
for f, nm in [("F63", "Martingale-measure property $\\mathbb E_{\\hat{\\mathbb Q}}[V^\\gamma]=0$"), ("F65", "Lower bound on expected exponential loss"),
              ("F66", "Gaussian likelihood ratio"), ("F67", "Value of the candidate strategy")]:
    EQN(f, nm)
pp6 = steps("PP6", "F62", [
    ("Every matrix in \\({\\mathcal{D}}\\) has zero diagonal.", "{\\mathcal{D}}\\cap\\mathbb S_+^n=\\{0\\}. $", "bound_estimate", "Zero diagonal and PSD force ${\\mathcal{D}}\\cap\\mathbb S^n_+=\\{0\\}$"),
    ("Thus, condition~\\eqref{eq:nopsddirections} holds", "decomposition~\\eqref{eq:finance_decomposition}.", "apply_lemma", "Apply the decomposition theorem to $\\Lambda$ and ${\\mathcal{D}}$"),
    ("Define a probability measure $\\hat{\\mathbb Q}$", "=0. \\]", "introduce_variable", "Define $\\hat{\\mathbb Q}$ with covariance $\\hat Q$; cross-covariances vanish"),
    ("Hence, since $Z$ is Gaussian", "\\end{equation}", "other", "Independence under $\\hat{\\mathbb Q}$ and the tower property give zero mean gains"),
    ("Next, choose $\\gamma\\in\\mathcal A$.", "The last equality is straightforward.", "bound_estimate", "Fenchel-type inequality gives a lower bound for every $z>0$"),
    ("From simple calculus it follows", "\\end{equation}", "bound_estimate", "Optimize over $z$ to get the lower bound"),
    ("The bound \\eqref{lowerbound} was derived", "established below.", "introduce_variable", "Candidate linear strategy $\\hat\\gamma$ from $\\hat\\Gamma\\in{\\mathcal{D}}$"),
    ("For multivariate normal distributions the likelihood ratio is", "\\label{equality} \\end{align}", "algebraic_manipulation", "Compute the likelihood ratio and the candidate's expected loss"),
    ("Comparing \\eqref{equality} with \\eqref{lowerbound}", "right hand side of \\eqref{eq:expected_value}.", "conclude", "Candidate attains the bound: optimality and value"),
    ("For uniqueness, equality in", "terminal wealth is therefore unique.", "other", "Equality case forces the terminal wealth"),
    ("Finally, the map $\\gamma\\mapsto V^{\\gamma}$ is injective", "portfolio is unique.", "conclude", "Injectivity of $\\gamma\\mapsto V^\\gamma$ by backward induction"),
], S4_)

# ================================================================ Section 5
N("DP28", "definition", "Strictly upper and lower triangular matrices $\\mathcal U_n$, $\\mathcal L_n$",
  sp("Let $\\mathcal U_n\\subset\\mathcal M_n(\\mathbb{R})$ denote", "(with no restriction on the diagonal)."), S5_, 0.9,
  "external", origin_citation=STD, definiendum=["$\\mathcal U_n$", "$\\mathcal L_n$"])
N("DP29", "definition", "Bilinear triangular decomposition",
  sp("Given $A,{\\Lambda}\\in\\mathbb{S}^n_{++}$, we seek a pair", "decomposition} of ${\\Lambda}$."), S5_, 0.9,
  definiendum="bilinear triangular decomposition",
  statement_short="A pair $(U,L)$, $U$ strictly upper and $L$ lower triangular, with $\\Lambda=L+U+UAL$.")
EQN("F68", "Bilinear triangular decomposition $\\Lambda=L+U+UAL$")
N("DP30", "definition", "Triangularly regular pair",
  sp("The pair $(A,{\\Lambda})$ is \\emph{triangularly regular}", "when it exists."), S5_, 0.9,
  definiendum="triangularly regular")
N("RP17", "remark", "Backward elimination as an analogue of LU",
  sp("Algorithm~\\ref{alg:backward_elimination} is the natural analogue of $LU$", "as partial pivoting does in standard $LU$."), S5_, 0.75,
  statement_short="Like LU without pivoting, but backward, with a triangular solve and one scalar pivot per step; a zero pivot certifies non-existence.")

N("AP2", "algorithm", "Backward triangular elimination for $\\Lambda=L+U+UAL$", fx("F69"), S5_, 1.0, main=True,
  input=["$A,{\\Lambda}\\in\\mathbb{S}^n_{++}$"], output=["The unique pair $(U,L)$, or a zero-pivot certificate of nonexistence"],
  statement_short="Eliminate backward from the lower-right corner: per step one triangular solve for the new row of $U$, one scalar pivot, and the new column of $L$; stop at a zero pivot.",
  tags=["matrix_decomposition", "elimination"])


def pseudo(fid, ap, subs, shorts=None, names=None):
    global ASPN
    st = pseudocode_steps(facts, fid, NODE[ap], first_seq=ASPN + 1)
    keep = [s for s in st if s["statement"].strip() and not s["statement"].strip().startswith("\\End")]
    ids = [s["id"] for s in keep]
    # renumber ids contiguously and step_order within parents
    ren = {}
    for s in keep:
        ASPN += 1
        ren[s["id"]] = f"ASP{ASPN}"
    cnt = {}
    for i, s in enumerate(keep):
        s["id"] = ren[s["id"]]
        if s["parent_id"] in ren:
            s["parent_id"] = ren[s["parent_id"]]
        cnt[s["parent_id"]] = cnt.get(s["parent_id"], 0) + 1
        s["step_order"] = cnt[s["parent_id"]]
        if s.get("subclass") is None:
            s["subclass"] = subs[i]
        if shorts and shorts[i]:
            s["statement_short"] = shorts[i]
        if names and names[i]:
            s["name"] = names[i]
        nodes.append(s)
        NODE[s["id"]] = s
    return [s["id"] for s in keep]


ap2 = pseudo("F69", "AP2",
             ["initialize", "loop", "compute", "compute", "solve", "solve", "compute", "branch", "return", "compute"],
             [None, "Backward loop over $k$", None, "Form $K_0$ and $M_0$", "Triangular row-solve for the new row of $U$",
              "Two solves with $K_0$", "Scalar pivot $\\pi_k$", "Zero-pivot test", "Certify non-existence", "New diagonal entry and column of $L$"],
             ["Initialize $U,L$ and $L_{nn}$", "Loop $k=n-1,\\dots,1$", "Trailing index set $J$", "Form $K_0$, $M_0$", "Solve for $U_{k,J}$",
              "Solve with $K_0$", "Pivot $\\pi_k$", "If $\\pi_k=0$", "Stop: no solution", "Update $L_{kk}$, $L_{J,k}$"])

N("RP18", "remark", "Efficient $O(n^3)$ implementation", fx("F71"), S5_, 1.0,
  statement_short="Update $M_0^{-1}$ and $K_0^{-1}$ by Schur-complement bordering at $O((n-k)^2)$ per step, giving $O(n^3)$ total.",
  tags=["complexity"])
N("LP3", "lemma", "Regularity", fx("F72"), S5_, 1.0,
  assumptions=["Let $A,{\\Lambda}\\in\\mathbb{S}^n_{++}$.", "If $(U,L)\\in\\mathcal U_n\\times\\mathcal L_n$ satisfies \\eqref{eq:twisted_decomposition},"],
  conclusions=["then $I_n+UA$ is invertible, and hence $L=(I_n+UA)^{-1}({\\Lambda}-U)$."])
N("PP7", "proof", "Proof of the regularity lemma", fx("F73"), S5_, 1.0, proves="LP3",
  statement_short="A left null vector $v$ of $I_n+UA$ would satisfy $v^\\top(\\Lambda+A^{-1})=0$, impossible since $\\Lambda+A^{-1}\\succ0$.",
  proof_strategy=["contradiction", "algebraic_manipulation"])
pp7 = steps("PP7", "F73", [
    ("The identity is equivalent to", "$(I_n+UA)L={\\Lambda}-U$.", "algebraic_manipulation", "Rewrite as $(I_n+UA)L=\\Lambda-U$"),
    ("Suppose $v\\in\\mathbb{R}^n$", "$v^\\top{\\Lambda}=v^\\top U$.", "introduce_variable", "Left null vector $v$ gives $v^\\top\\Lambda=v^\\top U$"),
    ("On the other hand $v^\\top(I_n+UA)=0$", "$v^\\top U=-v^\\top A^{-1}$.", "algebraic_manipulation", "Also $v^\\top U=-v^\\top A^{-1}$"),
    ("Combining the two identities", "$I_n+UA$ is invertible.", "conclude", "$v^\\top(\\Lambda+A^{-1})=0$ forces $v=0$"),
], S5_)
N("TP2", "theorem", "Bilinear triangular decomposition", fx("F74"), S5_, 1.0, main=True,
  assumptions=["Let $A,{\\Lambda}\\in\\mathbb{S}^n_{++}$.",
               "Whenever a pair $(U,L)\\in\\mathcal U_n\\times\\mathcal L_n$ satisfying \\eqref{eq:twisted_decomposition} exists,", "Otherwise"],
  conclusions=["Algorithm~\\ref{alg:backward_elimination} is well defined: at every step the matrices $M_0$ and $K_0$ are invertible.",
               "it is unique, $L=(I_n+UA)^{-1}({\\Lambda}-U)$, and $I_n+UA$ is invertible with $\\det(I_n+UA)=\\prod_{k=1}^{n-1}\\pi_k$.",
               "In addition, no pivot vanishes, so that Algorithm~\\ref{alg:backward_elimination} reaches its last step and returns this pair.",
               "Algorithm~\\ref{alg:backward_elimination} stops at a zero pivot $\\pi_k=0$, and this certifies that no pair in $\\mathcal U_n\\times\\mathcal L_n$ satisfies \\eqref{eq:twisted_decomposition}."],
  parts=[{"assumptions": [], "conclusions": ["Algorithm~\\ref{alg:backward_elimination} is well defined: at every step the matrices $M_0$ and $K_0$ are invertible."]},
         {"assumptions": ["Whenever a pair $(U,L)\\in\\mathcal U_n\\times\\mathcal L_n$ satisfying \\eqref{eq:twisted_decomposition} exists,"],
          "conclusions": ["it is unique, $L=(I_n+UA)^{-1}({\\Lambda}-U)$, and $I_n+UA$ is invertible with $\\det(I_n+UA)=\\prod_{k=1}^{n-1}\\pi_k$.",
                          "In addition, no pivot vanishes, so that Algorithm~\\ref{alg:backward_elimination} reaches its last step and returns this pair."]},
         {"assumptions": ["Otherwise"],
          "conclusions": ["Algorithm~\\ref{alg:backward_elimination} stops at a zero pivot $\\pi_k=0$, and this certifies that no pair in $\\mathcal U_n\\times\\mathcal L_n$ satisfies \\eqref{eq:twisted_decomposition}."]}],
  statement_short="Backward elimination is well defined; a bilinear triangular decomposition, when it exists, is unique and returned with $\\det(I_n+UA)=\\prod\\pi_k$; otherwise a zero pivot certifies non-existence.",
  tags=["matrix_decomposition", "existence", "uniqueness"])
N("PP8", "proof", "Proof of Theorem (bilinear triangular decomposition)", fx("F75"), S5_, 1.0, proves="TP2",
  statement_short="Block decoupling into trailing, row and column blocks; Sylvester's identity shows $M_0,K_0$ invertible, backward induction forces every entry, and the regularity lemma turns a zero pivot into non-existence.",
  proof_strategy=["induction", "algebraic_manipulation", "contradiction"])
for f, nm in [("F76", "Trailing-block identity"), ("F77", "First-column block system"), ("F78", "$\\det(M_0)\\det(K_0)=\\det(I+A_{J,J}\\Lambda_{J,J})$")]:
    EQN(f, nm)
pp8 = steps("PP8", "F75", [
    ("Fix $k$ and $J=\\{k+1,\\ldots,n\\}$.", "where $K_0=I_{|J|}+U_{J,J}A_{J,J}$.", "setup", "Decouple the identity into trailing, upper-right and first-column blocks"),
    ("\\textbf{(i)} \\emph{Well-posedness}.", "every step is well defined.", "other", "(i) Well-posedness of the algorithm", [
        ("Whenever the trailing relation~\\eqref{eq:trailing_block} holds", "the last step by~\\eqref{eq:trailing_block}.", "invoke_identity", "Sylvester's identity: $\\det M_0\\det K_0=\\det(I+A_{J,J}\\Lambda_{J,J})$"),
        ("This determinant is positive:", "both $M_0$ and $K_0$ are invertible.", "bound_estimate", "Positivity of the determinant gives invertibility"),
        ("Since the algorithm maintains", "every step is well defined.", "conclude", "The trailing relation is maintained, so every step is defined"),
    ], 0.95),
    ("\\textbf{(ii)} \\emph{Construction, uniqueness", "This proves~\\textbf{(ii)}.", "induction_step", "(ii) Entries forced by backward induction; determinant of $I_n+UA$", [
        ("We show by backward induction on $k$", "computed by the algorithm.", "setup", "Plan: backward induction forcing all entries"),
        ("The base case is", "by the $(n,n)$ entry.", "induction_step", "Base case $L_{nn}=\\Lambda_{nn}$"),
        ("For the inductive step, suppose", "$L_{J,k}=z-w\\,L_{kk}$ are determined.", "induction_step", "Inductive step: row of $U$ from $M_0$, pivot equation from the Schur complement of $K_0$"),
        ("Hence a solution, if it exists, is unique", "satisfying \\eqref{eq:twisted_decomposition}.", "conclude", "Uniqueness and agreement with the algorithm"),
        ("For the determinant, taking determinants", "This proves~\\textbf{(ii)}.", "algebraic_manipulation", "Schur complement gives $\\det(I_n+UA)=\\prod\\pi_k$"),
    ], 0.95),
    ("\\textbf{(iii)} \\emph{Non-existence}.", None, "contradiction_setup", "(iii) A zero pivot plus a solution would make $I_n+UA$ singular, contradicting the regularity lemma", None, 0.95),
], S5_)
N("DP31", "definition", "Matrix $S_U$",
  sp("This viewpoint also supplies the positive definiteness of", "\\end{equation}"), S5_, 0.85, definiendum="$S_U$")
EQN("F79", "Definition of $S_U$")
N("PrP3", "proposition", "Variational form of $U$; positivity of $S_U$", fx("F80"), S5_, 1.0, main=True,
  assumptions=["Let $A,{\\Lambda}\\in\\mathbb{S}^n_{++}$."],
  conclusions=["There is a unique $U\\in\\mathcal U_n$ such that $S_U\\succ0$ and $S_U^{-1}(I_n+UA)$ is lower triangular.",
               "It is obtained as $C=\\bigl(\\begin{smallmatrix}0&U\\\\U^\\top&0\\end{smallmatrix}\\bigr)$, the ${\\mathcal S}_{2n}$-component of the constrained decomposition of $B^{-1}$ furnished by Theorem~\\ref{thm:general_decomposition}, with $B$ as in~\\eqref{eq:B_def}.",
               "$(A,{\\Lambda})$ is triangularly regular if and only if $I_n+UA$ is invertible for this $U$.",
               "In that case $U$ is the matrix of the decomposition~\\eqref{eq:twisted_decomposition}.",
               "In particular the decomposition's $U$ satisfies $S_U\\succ0$."],
  equivalent_conditions=["$(A,{\\Lambda})$ is triangularly regular", "$I_n+UA$ is invertible for this $U$"],
  statement_short="The theorem applied to a $2n\\times2n$ matrix gives a unique $U$ with $S_U\\succ0$ and $S_U^{-1}(I+UA)$ lower triangular; the pair is triangularly regular iff $I+UA$ is invertible.",
  tags=["matrix_decomposition", "uniqueness", "variational"])
N("PP9", "proof", "Proof of Proposition (variational form of $U$)", fx("F81"), S5_, 1.0, proves="PrP3",
  statement_short="Apply the decomposition theorem to $B^{-1}$ with the off-diagonal-block subspace ${\\mathcal S}_{2n}$ and read $U$ off Schur complements; for (ii) factor $S_{U'}=(I+U'A)(L'-U'^\\top)$ and prove $S_{U'}\\succ0$ by induction on $n$.",
  proof_strategy=["construction", "algebraic_manipulation", "induction"])
for f, nm in [("F82", "Auxiliary $2n\\times2n$ matrix $B$ and its inverse"), ("F84", "Factorization $S_{U'}=(I_n+U'A)(L'-U'^\\top)$")]:
    EQN(f, nm)
pp9 = steps("PP9", "F81", [
    ("\\textbf{(i)} Set ${\\Sigma}:={\\Lambda}^{-1}$", "Therefore $U$ is unique.", "other", "(i) Existence and uniqueness of $U$ via the $2n\\times2n$ decomposition", [
        ("\\textbf{(i)} Set ${\\Sigma}:={\\Lambda}^{-1}$", "L\\in\\mathcal L_n \\right\\}. \\]", "introduce_variable", "Build $B$, ${\\mathcal S}_{2n}$ and its complement"),
        ("Every matrix in ${\\mathcal S}_{2n}$ has zero diagonal", "Theorem~\\ref{thm:general_decomposition} applies.", "apply_lemma", "Zero diagonal gives nondegeneracy, so the theorem applies"),
        ("It therefore supplies a unique pair", "=S_U^{-1}(I_n+UA). \\]", "algebraic_manipulation", "Schur complement of $A^{-1}$ is $S_U$; block inverse gives $Q_{11},Q_{12}$"),
        ("Since $Q\\in{\\mathcal S}_{2n}^{\\perp}$, the block $Q_{12}$", "This proves existence.", "conclude", "$Q_{12}$ lower triangular and $S_U\\succ0$: existence"),
        ("For uniqueness, let $U\\in\\mathcal U_n$ be", "Therefore $U$ is unique.", "other", "Any such $U$ yields a constrained decomposition, so it is unique"),
    ], 0.95),
    ("\\textbf{(ii)} For any $(U',L')", None, "other", "(ii) Triangular regularity iff $I_n+UA$ invertible", [
        ("\\textbf{(ii)} For any $(U',L')", "\\end{equation}", "algebraic_manipulation", "Factor $S_{U'}=(I_n+U'A)(L'-U'^\\top)$"),
        ("($\\Leftarrow$) If $I_n+UA$ is invertible", "$(A,{\\Lambda})$ is regular.", "case_split", "($\\Leftarrow$) construct $L$ and check it is lower triangular"),
        ("($\\Rightarrow$) If $(A,{\\Lambda})$ is regular", "making $I_n+UA$ invertible.", "case_split", "($\\Rightarrow$) the decomposition's $U'$ satisfies the conditions of (i), granting $S_{U'}\\succ0$"),
        ("It remains to prove $S_{U'}\\succ0$.", "It remains to prove $S_{U'}\\succ0$.", "setup", "Remaining: $S_{U'}\\succ0$"),
        ("We argue by induction on $n$", "={\\Lambda}_{11}>0$.", "induction_step", "Induction on $n$; base case $n=1$"),
        ("Let $J=\\{2,\\dots,n\\}$.", "positive definite by the inductive hypothesis.", "induction_step", "Trailing block positive definite by induction"),
        ("By the bordered-matrix criterion", "Hence $S_{U'}\\succ0$.", "bound_estimate", "Schur complement bounded below by that of $\\Lambda$"),
    ], 0.95),
], S5_)
N("ExP1", "example", "The $2\\times2$ case", fx("F85"), S5_, 1.0,
  statement_short="For $n=2$ the decomposition exists iff $1+cr+bq\\ne0$; a positive definite pair with $1+cr+bq=0$ has no decomposition but the variational $U$ exists.")
N("RP19", "remark", "The role of $A$", fx("F86"), S5_, 1.0,
  statement_short="For diagonal $A$ every pair is triangularly regular; for non-diagonal $A$ regularity can fail.")

# ================================================================ Section 6
N("CnjP1", "conjecture", "Extension to Hermitian matrices and positive operators",
  sp("The theory should extend from real symmetric", "infinite-dimensional spaces."), S6_, 0.6,
  assumptions=[], conclusions=["The theory should extend from real symmetric matrices to complex Hermitian ones, and further to positive operators on infinite-dimensional spaces."])

# ================================================================ Appendix A
N("PP10", "proof", "Proof of Proposition (local stability)", fx("F87"), SA, 1.0, proves="PrP1",
  statement_short="Follow the decomposition along $A_t=A+t\\Delta$: the implicit function theorem makes it analytic, $\\dot C_t$ is the $B_t$-orthogonal projection of $\\Delta$ onto ${\\mathcal{S}}$, and a Riccati-type comparison for $\\|B_t\\|_2$ controls the coefficients when integrating.",
  proof_strategy=["direct", "other"])
for f, nm in [("F88", "Partial derivatives of the optimality map $F$"), ("F89", "Equation for $\\dot C_t$"),
              ("F90", "Inner product $\\langle X,Y\\rangle_B$"), ("F91", "Bound on $\\|\\dot C_t\\|_F$"),
              ("F92", "Bound on $\\|\\dot B_t\\|_2$"), ("F93", "Comparison bound on $\\|B_t\\|_2$")]:
    EQN(f, nm)
pp10 = steps("PP10", "F87", [
    ("Let $A_t:=A+t\\Delta", "for all $X\\in {\\mathcal{S}}$.", "setup", "Path $A_t$, its decompositions $(B_t,C_t)$, and the optimality map $F$"),
    ("\\emph{Step 1 (differentiate along the path).}", "=\\mathrm{proj}_{\\mathcal{S}}(B_t\\Delta B_t). \\end{equation}", "other", "Step 1: analyticity of the path and the equation for $\\dot C_t$", [
        ("Since $\\frac{d}{ds}\\big|_{s=0}(M+sE)^{-1}", "\\end{align}", "algebraic_manipulation", "Partial derivatives of $F$"),
        ("By the definition of $\\alpha$ and", "hence bijective.", "apply_lemma", "Lemma (i) makes the $C$-derivative of $F$ invertible"),
        ("Matrix inversion is real analytic", "as is $t\\mapsto B_t=(A_t-C_t)^{-1}$.", "apply_lemma", "Analytic implicit function theorem and uniqueness give analytic $C_t$, $B_t$"),
        ("Write $\\dot C_t:=\\frac{d}{dt}C_t$", "\\end{equation}", "algebraic_manipulation", "Differentiate $F(A_t,C_t)=0$"),
    ], 0.95),
    ("\\emph{Step 2 (the derivative is a projection).}", "\\le\\|B_t\\|_2^2\\,\\delta . \\end{align}", "other", "Step 2: $\\dot C_t$ is a $B_t$-orthogonal projection of $\\Delta$; bounds on $\\dot C_t$, $\\dot B_t$", [
        ("For $B\\in\\mathbb{S}^n_{++}$ the formula", "since $B^{1/2}$ is invertible.", "introduce_variable", "Define the $B$-inner product"),
        ("Pairing~\\eqref{eq:dC_eq} with $X\\in {\\mathcal{S}}$", "in the inner product~\\eqref{eq:B_inner}.", "other", "Identify $\\dot C_t$ as the projection of $\\Delta$"),
        ("Set $R_t:=\\Delta-\\dot C_t$.", "$\\|R_t\\|_{B_t}\\le\\|\\Delta\\|_{B_t}$.", "bound_estimate", "Pythagoras for the residual $R_t$"),
        ("By~\\eqref{eq:alpha_def_fro}, $\\sqrt{\\alpha(B_t,{\\mathcal{S}})}", "\\end{equation}", "bound_estimate", "Bound $\\|\\dot C_t\\|_F\\le\\kappa(B_t)\\delta$"),
        ("Differentiating $B_t=(A_t-C_t)^{-1}$ gives", "\\end{align}", "bound_estimate", "Bound $\\|\\dot B_t\\|_2\\le\\|B_t\\|_2^2\\delta$"),
    ], 0.95),
    ("\\emph{Step 3 (integrate).}", None, "other", "Step 3: integrate the derivative bounds", [
        ("Recall from Lemma~\\ref{lem:alpha_lipschitz}\\textbf{(i)} that", "in terms of $\\|B^{*}\\|_2$.", "setup", "Need to bound $\\|B_t\\|_2$ by $\\|B^*\\|_2$"),
        ("Since $t\\mapsto B_t$ is continuously differentiable", "\\end{equation}", "bound_estimate", "Comparison for $1/\\|B_t\\|_2$ bounds $\\|B_t\\|_2$"),
        ("By~\\eqref{eq:smallness_fro} and $\\kappa(B^{*},{\\mathcal{S}})\\ge1$", "the first bound is~\\eqref{eq:B_stab_fro}.", "bound_estimate", "Integrate to get the $B$ bound"),
        ("Lemma~\\ref{lem:alpha_lipschitz}\\textbf{(ii)} bounds", "\\alpha(B^{*},{\\mathcal{S}})$ throughout.", "apply_lemma", "Lipschitz bound keeps $\\alpha(B_t)$ comparable to $\\alpha(B^*)$"),
        ("The factors $1-\\varepsilon$ therefore cancel", None, "conclude", "Integrate the $\\dot C_t$ bound to get the $C$ bound"),
    ], 0.95),
], SA)
N("PP11", "proof", "Proof of Corollary (uniform stability)", fx("F95"), SA, 1.0, proves="CP1",
  statement_short="Integrate the infinitesimal bounds along segments in the convex set, with $\\beta_0$, $\\alpha_0$ uniform on $\\Theta$.",
  proof_strategy=["direct"])
pp11 = steps("PP11", "F95", [
    ("The maximum and minimum defining", "$\\alpha_0>0$ by Lemma~\\ref{lem:alpha_lipschitz}\\textbf{(i)}.", "setup", "$\\beta_0$, $\\alpha_0$ are attained and $\\alpha_0>0$"),
    ("For $A,\\widetilde A\\in\\Theta$, the segment", "integrated as they stand.", "introduce_variable", "Segment in $\\Theta$ with uniform coefficients"),
    ("Integrating~\\eqref{eq:dC_bound} gives", None, "conclude", "Integrate the two derivative bounds"),
], SA)

# ================================================================ Appendix B
fr = _pat("We illustrate the framework with six concrete examples").search(SRC).start()
for i, (a, b, nm) in enumerate([
        ("(dense, small ${\\mathcal{S}}$, exact Newton):", "Cholesky factorization.", "Example I: dense, small ${\\mathcal{S}}$, exact Newton"),
        ("(dense, small ${\\mathcal{S}}$, Newton-CG):", "rather than exact Newton.", "Example II: dense, small ${\\mathcal{S}}$, Newton-CG"),
        ("(dense, tridiagonal ${\\mathcal{S}}^\\perp$, dual Newton-CG):", "while $M(x)$ stays dense.", "Example III: tridiagonal ${\\mathcal{S}}^\\perp$, dual Newton-CG"),
        ("($\\mathcal G$-invariant, $r$ blocks):", "becomes independent of $n$.", "Example IV: block-permutation invariant"),
        ("(banded): both $A$ and ${\\mathcal{S}}$", "reaches much larger $n$.", "Example V: banded"),
        ("(circulant): $A$ and every $D_k$", "discrete Fourier transform.", "Example VI: circulant")], 2):
    N(f"ExP{i}", "example", nm, sp(a, b, fr), SB, 0.85)
N("RP20", "remark", "Measured per-iteration scaling across structural settings",
  sp("Table~\\ref{tab:scaling_summary} reports the measured per-iteration cost", "roughly $330$ times higher."), SB, 0.75,
  rigor="numerical",
  statement_short="Measured costs match the bounds; structure-aware banded evaluation is 6-20x faster, and the dual is ~330x cheaper than the primal on the tridiagonal-complement instance.",
  tags=["numerical_experiments", "complexity"])

# ================================================================ Appendix C
N("AP3", "algorithm", "ConstrainedDecompositionNewtonCG", fx("F96"), SC, 1.0,
  input=["$A\\in\\mathbb{S}^n_{++}$, basis $\\{D_k\\}_{k=1}^m$ of ${\\mathcal{S}}$", "tolerances $\\texttt{tol},\\texttt{tol\\_cg}>0$"],
  output=["The minimizer $x$, $C^\\ast=C(x)$, and $B^\\ast=(A-C^\\ast)^{-1}$"],
  statement_short="Outer Newton loop from $x=0$ with inner CG on the Newton system (relative tolerance $\\min\\{tol_{cg},\\|g\\|\\}$), then feasibility-preserving Armijo backtracking.",
  tags=["optimization", "newton_method"])
ap3 = pseudo("F96", "AP3", ["initialize", "loop", "initialize", "loop", "call", "update", "update", "select", "call", "return"],
             ["Start at $x=0$ and evaluate", "Outer Newton loop until $\\|g\\|\\le$ tol", "Initialize CG", "Inner CG loop with forcing tolerance",
              "Hessian-vector product", "CG step length and updates", "New conjugate direction", "Backtracking line search and step",
              "Re-evaluate objective and gradient", "Assemble the output"],
             ["Initialize", "Newton loop", "CG init", "CG loop", "Hv product", "CG update", "Direction update", "Line search", "Evaluate", "Output $C^*,B^*$"])
N("AP4", "algorithm", "EvaluatePhiGrad", fx("F98"), SC, 1.0,
  input=["$A\\in\\mathbb{S}^n_{++}$, $x\\in\\Omega_x$"], output=["$\\Phi$, the gradient $g=\\nabla\\Phi(x)\\in\\mathbb{R}^m$, and $B=M^{-1}$"],
  statement_short="Factorize $M=A-C(x)$, evaluate $-\\log\\det M$, invert, and take the traces $\\mathrm{tr}(BD_k)$.")
ap4 = pseudo("F98", "AP4", ["compute", "compute", "loop", "compute"], [None, None, None, None],
             ["Form $C$, $M$", "Factorize, $\\Phi$, $B$", "Loop over $k$", "Gradient trace"])
N("AP5", "algorithm", "HvProduct", fx("F100"), SC, 1.0,
  input=["Basis $\\{D_k\\}_{k=1}^m$, $B\\in\\mathbb{S}^n_{++}$, a vector $p\\in\\mathbb{R}^m$"], output=["$q=H(x)p\\in\\mathbb{R}^m$"],
  statement_short="Form $D(p)$, the two-sided product $BD(p)B$, and the traces against each $D_k$.")
ap5 = pseudo("F100", "AP5", ["compute", "compute", "loop", "compute"], [None, None, None, None],
             ["Form $D(p)$", "Two-sided product", "Loop over $k$", "Trace"])

# ================================================================ EDGES
def P(i):
    return f"PSP{i}"


# step id lookup by short prefix
def sid(proof, k, kid=None):
    top = [n["id"] for n in nodes if n.get("parent_id") == proof and n["type"] == "proof_step"]
    s = top[k - 1]
    if kid is None:
        return s
    return NODE[s]["_kids"][kid - 1]


# Pass 2: defined terms
for t in ["DP2", "DP3", "TP1", "LP1", "LP2", "PrP1", "CP1", "DP5", "DP9", "PP1"]:
    E("DP1", t, conf=0.75)
for t in ["TP1", "LP1", "LP2", "DP8", "DP9", "PrP1", "CP1", "ClP2", "DP29", "LP3", "TP2", "PrP3", "AssumP3", "DP11", "DP12"]:
    E("DP2", t, conf=0.75)
for t in ["TP1", "ClP2", "PP3", "DP11", "PrP2", "PP9", "RP1"]:
    E("DP3", t, conf=0.8)
for t in ["DP5", "DP6", "AssumP2"]:
    E("DP4", t, conf=0.85)
for t in ["ClP4", "DP6"]:
    E("DP5", t, conf=0.8)
for t in ["DP7", "ClP5"]:
    E("DP6", t, conf=0.8)
for t in ["ClP5", "AssumP2", "DP14"]:
    E("DP7", t, conf=0.8)
for t in ["CP1", "PP10", "AssumP1"]:
    E("DP8", t, conf=0.8)
for t in ["PrP1", "CP1", "DP9", "LP2"]:
    E("AssumP1", t, conf=0.7, basis="inferred")
for t in ["LP2", "DP10", "PrP1", "RP3", "CP1", "PP10", "PP11"]:
    E("DP9", t, conf=0.85)
for t in ["PrP1", "RP3", "PP10"]:
    E("DP10", t, conf=0.85)
for t in ["DP12", "ClP14", "ExP4", "RP20"]:
    E("DP11", t, conf=0.8)
for t in ["DP13", "ClP14", "RP10"]:
    E("DP12", t, conf=0.85)
E("DP13", "ClP14", conf=0.85)
for t in ["DP14", "ClP15"]:
    E("AssumP2", t, conf=0.8, basis="inferred")
for t in ["ClP15", "RP11", "RP12", "ExP5"]:
    E("DP14", t, conf=0.85)
for t in ["DP16", "DP18", "DP20"]:
    E("DP15", t, conf=0.75)
for t in ["DP17", "DP18", "AssumP3", "DP20", "DP22", "DP25", "PP6"]:
    E("DP16", t, conf=0.8)
for t in ["DP18", "AssumP3"]:
    E("DP17", t, conf=0.8)
for t in ["DP21", "DP25", "ClP17", "PP6"]:
    E("DP18", t, conf=0.8)
for t in ["DP19", "DP23", "DP25", "ProbP2", "PrP2", "PP6", "ClP16"]:
    E("AssumP3", t, conf=0.8)
for t in ["PrP2", "PP6"]:
    E("DP19", t, conf=0.85)
for t in ["DP21", "DP22", "DP23"]:
    E("DP20", t, conf=0.8)
for t in ["PP6"]:
    E("DP21", t, conf=0.75)
for t in ["DP23", "ClP16", "ClP18", "ProbP2", "RP14", "PrP2", "PP6"]:
    E("DP22", t, conf=0.85)
for t in ["DP24", "ProbP2", "RP14", "PrP2", "PP6"]:
    E("DP23", t, conf=0.85)
for t in ["ClP16", "ClP18", "PrP2", "PP6", "RP15"]:
    E("DP24", t, conf=0.85)
for t in ["ClP17", "DP26", "PP6"]:
    E("DP25", t, conf=0.85)
for t in ["ClP18", "RP15", "PrP2", "PP6"]:
    E("DP26", t, conf=0.85)
for t in ["ProbP2", "RP14"]:
    E("DP27", t, conf=0.8)
for t in ["DP29", "LP3", "TP2", "DP31", "PrP3", "PP8", "PP9", "AP2"]:
    E("DP28", t, conf=0.8)
for t in ["DP30", "AP2", "RP17"]:
    E("DP29", t, conf=0.85)
for t in ["PrP3", "RP19", "PP9"]:
    E("DP30", t, conf=0.85)
for t in ["PrP3", "PP9", "ExP1"]:
    E("DP31", t, conf=0.85)
# symbols introduced in the proof of Theorem 1 (Step 1) and reused in Section 3
st1 = sid("PP2", 2)
for t in ["ProbP1", "ClP8", "ClP9", "RP4", "AP1", "PP5", "AP3", "AP4", "RP6", "RP9", "RP5"]:
    E(EQ["F13"], t, conf=0.75)
for t in ["ProbP1", "AP1", "ClP9", "PP5"]:
    E(EQ["F12"], t, conf=0.75)
for t in ["ClP8", "AP4"]:
    E(EQ["F14"], t, conf=0.75, basis="inferred")

# Pass 1/3: results built on results (no \ref)
E(sid("PP2", 3), "RP1", conf=0.9, basis="named")          # "the construction of Step 2"
E(sid("PP2", 3), "ClP1", conf=0.9, basis="named")         # "By Step 2 of the proof"
E("PP3", "ClP2", "proves", 0.75, "inferred")
E("ClP1", "ClP3", conf=0.75, basis="inferred")
E("ClP2", "ClP3", conf=0.75, basis="inferred")
E("ClP3", "RP2", conf=0.75, basis="inferred")
E("TP1", "ClP4", conf=0.8, basis="inferred")
E("ClP4", "ClP5", conf=0.85, basis="named")               # "By the above analysis"
E("TP1", "ClP5", conf=0.8, basis="inferred")
E("ClP1", "ClP6", conf=0.85, basis="named")               # "From the primal representation"
E("TP1", "ClP7", conf=0.8, basis="inferred")
E("LP2", "DP10", conf=0.9, basis="named")                 # "Part (i) gives"
E("ClP8", "ClP9", conf=0.85, basis="inferred")
E("ClP9", "ClP10", conf=0.85, basis="named")              # "With D(v) as above"
E("ClP8", "ClP10", conf=0.8, basis="inferred")
E("ClP8", "AP1", conf=0.75, basis="term")
E("ProbP1", "AP1", "resolves", 0.85, "inferred")
E("AP1", "AP3", conf=0.85, basis="named")                 # "Algorithmic details ... are given in Appendix"
E("ProbP1", "AP3", "resolves", 0.8, "inferred")
E("ClP9", "PP5", conf=0.75, basis="inferred")
E(sid("PP2", 3, 1), "PP5", conf=0.7, basis="inferred")    # barrier behaviour at the boundary
E("PP5", "ClP11", "proves", 0.75, "inferred")
E("ClP9", "ClP12", conf=0.8, basis="inferred")
E("ClP11", "ClP13", conf=0.75, basis="inferred")
E("ClP10", "RP6", conf=0.7, basis="inferred")
E("ClP10", "RP9", conf=0.7, basis="inferred")
E("ClP2", "DP12", conf=0.7, basis="inferred")
E("ClP15", "RP11", conf=0.8, basis="inferred")
E("RP5", "RP11", conf=0.7, basis="inferred")
E("ExP5", "RP12", conf=0.9, basis="named", mention=True)  # "Example IV of Appendix"
E("RP11", "RP13", conf=0.75)
E("ProbP1", "ClP15", conf=0.75)
E("ClP17", "PP6", conf=0.85, basis="inferred")            # "Every matrix in D has zero diagonal"
E("ClP16", "ClP18", conf=0.7, basis="inferred")
E("ProbP2", "PrP2", "resolves", 0.9, "named")             # "The following solves the ... problem"
E("ProbP2", "RP14", conf=0.8, basis="inferred")
E("PP6", "PP9", conf=0.85, basis="named")                 # "as in the proof of Proposition"
E("PrP2", "PP9", conf=0.95, mention=True, basis=None)
E("PrP2", sid("PP9", 1), conf=0.95, mention=True, basis=None)
E("PrP2", sid("PP9", 1, 2), conf=0.95, mention=True, basis=None)
E("DP30", "ExP1", "illustrates", 0.8, "term")
E("DP29", "ExP1", "illustrates", 0.85, "term")
E("TP1", "CnjP1", "generalizes", 0.7, "inferred")
E("ProbP1", "ExP2", "illustrates", 0.8, "inferred")
E("AP3", "ExP3", "illustrates", 0.8, "inferred")
E("ExP2", "ExP3", conf=0.9, basis="named")                # "the setting of Example I"
E("DP11", "ExP4", "illustrates", 0.8, "term")
E("DP14", "ExP5", "illustrates", 0.8, "term")
E("RP12", "ExP5", "illustrates", 0.75, "inferred")
E("RP6", "ExP6", "illustrates", 0.75, "inferred")
E("RP8", "ExP7", "illustrates", 0.75, "inferred")
for x in ["ExP2", "ExP3", "ExP4", "ExP5", "ExP6", "ExP7"]:
    E(x, "RP20", conf=0.7, basis="inferred")
E("AP4", "AP3", conf=0.95, basis="named")                 # \Call{EvaluatePhiGrad}
E("AP5", "AP3", conf=0.95, basis="named")                 # \Call{HvProduct}
E("ClP10", "AP5", conf=0.85, basis="named")
E("PP10", "PP11", conf=0.75, basis="inferred")            # the integrated bounds are those of the proof
E("TP2", "ExP1", "illustrates", 0.8, "inferred")
E("AP2", "TP2", conf=0.9, basis="term")

# Pass 4: inside proofs
def chain(pairs, conf=0.75):
    for a, b in pairs:
        E(a, b, conf=conf, basis="inferred")


chain([(pp1[0], pp1[2]), (pp1[1], pp1[3]), (pp1[3], pp1[4])])
s1k = NODE[sid("PP2", 2)]["_kids"]
s2k = NODE[sid("PP2", 3)]["_kids"]
chain([(s1k[0], s1k[1]), (s1k[1], s1k[2]), (s2k[0], s2k[2]), (s2k[1], s2k[2]), (s2k[2], s2k[3])])
E(s1k[2], s2k[3], conf=0.9, basis="named")                # "the equivalence in Step 1"
k3 = [n["id"] for n in nodes if n.get("parent_id") == "PP3"]
chain([(k3[1], k3[3]), (k3[2], k3[3])])
chain([(pp6[0], pp6[1]), (pp6[2], pp6[3]), (pp6[4], pp6[5]), (pp6[6], pp6[7]), (pp6[5], pp6[8]), (pp6[7], pp6[8]), (pp6[9], pp6[10])])
chain([(pp7[0], pp7[1]), (pp7[1], pp7[3]), (pp7[2], pp7[3])])
ik, iik = NODE[pp8[1]]["_kids"], NODE[pp8[2]]["_kids"]
chain([(pp8[0], ik[0]), (ik[0], ik[1]), (ik[1], ik[2]), (pp8[0], iik[2]), (iik[2], iik[3])])
E(ik[1], iik[2], conf=0.85, basis="inferred")             # "By (mk_det), M_0 is invertible"
E(iik[2], pp8[3], conf=0.9, basis="named")                # "By the forcing above"
E(iik[4], pp8[3], conf=0.85, basis="inferred")            # determinant product
p9i, p9ii = NODE[pp9[0]]["_kids"], NODE[pp9[1]]["_kids"]
chain([(p9i[0], p9i[1]), (p9i[1], p9i[2]), (p9i[2], p9i[3])])
E(p9i[2], p9i[4], conf=0.9, basis="named")                # "The computation above shows"
chain([(p9ii[0], p9ii[1]), (p9ii[0], p9ii[2]), (p9ii[4], p9ii[5]), (p9ii[5], p9ii[6])])
E(p9ii[6], p9ii[2], conf=0.8, basis="inferred")           # "Granting this" -- proved after
E(pp9[0], p9ii[2], conf=0.85, basis="named")              # "the two conditions of part (i)"
st1k, st2k, st3k = NODE[pp10[1]]["_kids"], NODE[pp10[2]]["_kids"], NODE[pp10[3]]["_kids"]
chain([(pp10[0], st1k[0]), (st1k[1], st1k[2]), (st1k[2], st1k[3]), (st2k[2], st2k[3]), (st2k[2], st2k[4]),
       (st3k[1], st3k[2]), (st3k[2], st3k[3]), (st3k[3], st3k[4])])
chain([(pp11[0], pp11[2]), (pp11[1], pp11[2])])
# pseudocode data flow
E(ap2[4], ap2[6], conf=0.8, basis="inferred")
E(ap2[5], ap2[6], conf=0.8, basis="inferred")
E(ap2[6], ap2[7], conf=0.8, basis="inferred")

c4 = NODE["ClP4"]["statement"]
NODE["ClP4"]["conclusions"] = [c4[c4.index("P A P^\\top = (P B"):]]
for a_, b_ in [("DP1", "ClP7"), ("DP3", "RP2"), ("DP8", "PP11"), ("DP16", "DP21"), ("DP16", "ProbP2"),
               ("DP18", "ProbP2"), ("DP20", "RP15"), ("DP21", "DP24")]:
    E(a_, b_, conf=0.75)
for n in nodes:
    n.pop("_kids", None)

NOTES = [
    {"category": "type_uncertain", "nodes": ["DP7"],
     "note": "Sentence 'Assume that A is G-fixed, i.e., ... and that S is G-invariant, i.e., ...' is both an assumption and the definition of the two terms reused in Section 3.5; typed definition."},
    {"category": "type_uncertain", "nodes": ["DP29"],
     "note": "'Given A, Lambda, we seek a pair (U,L) satisfying (50), which we call the bilinear triangular decomposition' is both a problem statement and the definition of the term; typed definition since Algorithm 1 and Theorem 5.2 refer to the term."},
    {"category": "boundary_uncertain", "nodes": ["PP3", "ClP2", "ClP3"],
     "note": "Section 2.1 derives the dual in running text; split into the derivation (proof), the sentence concluding that B* is the unique dual maximizer (claim), and the strong-duality sentence (claim)."},
    {"category": "boundary_uncertain", "nodes": ["ClP4", "ClP5", "ClP6", "ClP7"],
     "note": "The enumerated 'properties' of Section 2.2 argue and conclude inside single sentences; each property is one claim containing its own short argument, no separate proof node."},
    {"category": "rule_conflict", "nodes": ["EP8", "EP9", "EP10"],
     "note": "Omega_x, M(x), B(x), Phi(x) and the gradient formula are introduced inside the proof of Theorem 2.1 but used throughout Section 3; edges go from those equation nodes (nested in the proof steps) to the Section 3 nodes."},
    {"category": "unexpected_construct", "nodes": ["RP5", "RP6", "RP8", "RP9", "RP11", "RP12", "RP20"],
     "note": "Complexity accounting (Table 1) and the measured scaling (Table 2, Figures) are tables; the prose paragraphs deriving each table row are remarks, the tables themselves are not nodes."},
    {"category": "source_problem", "nodes": ["AP2", "AP3", "AP4", "AP5"],
     "note": "pseudocode_steps returns an empty statement for every '\\State \\Return ...' line and the hidden \\EndFor/\\EndIf/\\EndWhile lines; those were dropped, so the return lines have no step."},
    {"category": "not_extracted", "nodes": [],
     "note": "Introduction overview, the Newton-CG rationale paragraph of Section 3, the dual Newton sentence of 3.4 (no procedure beyond 'as in the primal case'), the reproducibility paragraph, figures and the remaining future-work directions of the Conclusion are not nodes."},
]

graph = {
    "metadata": {
        "title": "A Unique Inverse Decomposition of Positive Definite Matrices under Linear Constraints",
        "arxiv_id": "2601.18662",
        "authors": ["Yan Dolinsky", "Or Zuk"],
        "year": 2026,
        "annotator": "agent-extraction",
        "model": "claude-opus-5-5",
        "effort": "default",
        "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
        "extraction_date": "2026-11-05",
        "rigor_nonformal_count": sum(1 for n in nodes if "rigor" in n),
        "paper_style": ["theorem_proof", "computational"],
        "extraction_notes": NOTES,
        "extraction_comment": "",
    },
    "nodes": nodes,
    "edges": edges,
}
report = finalize(graph, read_tex(TEX))
for k in ("errors", "warnings"):
    print(k.upper(), len(report.get(k, [])))
    for x in report.get(k, []):
        print("  ", x)
print({k: (v if not isinstance(v, list) else len(v)) for k, v in report.items() if k not in ("errors", "warnings")})
assert not report["errors"], report["errors"]
json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
print("wrote", OUT)
