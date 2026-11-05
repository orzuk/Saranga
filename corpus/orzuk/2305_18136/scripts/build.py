#!/usr/bin/env python3
"""Build the SARANGA v7 graph of arXiv 2305.18136 (Dolinsky & Zuk)."""
import json, os, re, subprocess, sys
REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize, pseudocode_steps
from latex_facts import read_tex

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = HERE + "/arxiv_src/main.tex"
OUT = HERE + "/2305_18136.json"
SCR = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_orzuk/2305_18136"
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
    return re.compile(r"\s+".join(re.escape(w) for w in m.split()))


def sp(a, b, frm=0):
    ma = _pat(a).search(SRC, frm)
    if not ma:
        raise ValueError("start not found: " + a)
    mb = _pat(b).search(SRC, ma.start())
    if not mb:
        raise ValueError("end not found: " + b)
    return clean(SRC[ma.start():mb.end()])


def fx(fid):
    return clean(FX[fid]["statement"])


def sec_of(fid):
    return SEC[FX[fid]["section"]]


S1, S2, S3 = SEC["S1"], SEC["S2"], SEC["S3"]
nodes, edges = [], []


def N(id, type, name, statement, section, conf, origin="paper", **kw):
    n = {"id": id, "type": type, "name": name, "statement": statement, "section": section,
         "origin": origin, "confidence": conf}
    n.update(kw)
    nodes.append(n)
    return n


def E(s, t, typ="uses", conf=0.8, basis="term", **kw):
    e = {"source": s, "target": t, "type": typ, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)


# ---------------------------------------------------------------- Section 1
N("DP1", "definition", "Probability space and risky asset $S$",
  sp("To formulate our main result, let", "fixed finite time horizon."), S1, 0.85,
  definiendum=["$S=(S_k)_{0\\leq k\\leq n}$", "$n$"])
N("AssumP1", "assumption", "Zero interest bank account",
  sp("We assume that the investor has a bank account", "bears no interest."), S1, 0.85)
N("AssumP2", "assumption", "Gaussian price increments",
  sp("We assume that the initial stock price", "multivariate normal distribution."), S1, 0.85,
  statement_short="$S_0$ is a known constant and $(S_1,\\dots,S_n)$ is non-degenerate multivariate normal.")
N("DP2", "definition", "Mean vector $\\mu$ and covariance $\\Sigma$ of the increments",
  sp("Hence, \n\\begin{equation*}\n(S_1-S_0", "is a constant positive definite matrix."), S1, 0.8,
  definiendum=["$\\mu$", "${\\Sigma}$", "$M_n(\\mathbb R)$"],
  statement_short="The increments are $\\mathcal N(\\mu,\\Sigma)$ with constant mean row vector $\\mu$ and positive definite $\\Sigma$.")
N("DP3", "definition", "Precision matrix $\\Lambda$",
  sp("Let ${\\Lambda}:={\\Sigma}^{-1}$", "the precision matrix."), S1, 0.9,
  definiendum="${\\Lambda}$", genus="matrix", differentia=["${\\Lambda}:={\\Sigma}^{-1}$"])
N("DP4", "definition", "Delay $D$",
  sp("We fix a nonnegative integer number", "trading times."), S1, 0.85, definiendum="${D}$")
N("DP5", "definition", "Delayed information filtration $\\mathcal G^D$",
  sp("Hence, the investor's flow of information", "$, $k=0,1,...,n$."), S1, 0.85,
  definiendum="$\\mathcal G^{{D}}_k$")
N("DP6", "definition", "Trading strategy",
  sp("A trading strategy is a random vector", "is the number of shares at time $k-1$)."), S1, 0.9,
  definiendum="trading strategy", genus="random vector $\\gamma=(\\gamma_1,...,\\gamma_n)$",
  differentia=["predictable with respect to the above filtration"],
  statement_short="A trading strategy is a vector $\\gamma$ with $\\gamma_k$ measurable w.r.t. the delayed information $\\mathcal G^D_{k-1}$.")
N("DP7", "definition", "Set of admissible strategies $\\mathcal A_D$",
  sp("Denote by $\\mathcal A_{{D}}$ the set", "trading strategies."), S1, 0.9, definiendum="$\\mathcal A_{{D}}$")
N("DP8", "definition", "Terminal portfolio value $V^\\gamma_n$",
  sp("For $\\gamma\\in\\mathcal A_{{D}}$ the corresponding portfolio value", "(S_i-S_{i-1}).\n$$"), S1, 0.9,
  definiendum="$V^{\\gamma}_n$")
N("ProbP1", "problem", "Exponential utility maximization with delay",
  sp("The investor’s preferences are described", "market probability measure \n$\\mathbb P$."), S1, 0.9,
  statement_short="Maximize expected exponential utility $\\mathbb E[-e^{-\\alpha V^\\gamma_n}]$ over strategies $\\gamma$ adapted to the $D$-delayed filtration.",
  tags=["optimization", "utility_maximization"])
N("EP1", "equation", "Exponential utility maximization problem (2.2)", fx("F2"), S1, 1.0)
N("RP1", "remark", "Reduction to risk aversion $\\alpha=1$",
  sp("Clearly, \nfor any portfolio strategy", "we take the risk aversion $\\alpha=1$."), S1, 0.75,
  statement_short="Since $V^{\\lambda\\gamma}_n=\\lambda V^\\gamma_n$, the risk aversion can be normalized to $\\alpha=1$.")
N("DP9", "definition", "Banded positive definite matrices $\\mathcal S_D$",
  sp("Let ${\\mathcal{S}}_{{D}}\\subset M_n(\\mathbb R)$ be the set", "upper bandwidth equal to ${D}$."), S1, 0.9,
  definiendum="${\\mathcal{S}}_{{D}}$", genus="positive definite matrices $Q\\in M_n(\\mathbb R)$",
  differentia=["$Q_{ij}=0$ for $|i-j|>{D}$"])
N("DP10", "definition", "Symmetric matrices vanishing on the band $\\mathcal T_D$",
  sp("Let ${\\mathcal{T}}_{{D}}\\subset M_n(\\mathbb R)$", "for $|i-j|\\leq {D}.$"), S1, 0.9,
  definiendum="${\\mathcal{T}}_{{D}}$", genus="symmetric matrices $\\Gamma\\in M_n(\\mathbb R)$",
  differentia=["$\\Gamma_{ij}=0$ for $|i-j|\\leq {D}.$"])
N("TP1", "theorem", "Optimal exponential-utility strategy under delay via banded decomposition", fx("F3"), S1, 1.0,
  main=True,
  assumptions=[],
  conclusions=[
      "There exists a unique decomposition \\begin{equation} {\\Lambda}=\\hat Q^{-1}+\\hat\\Gamma \\end{equation} where $\\hat Q\\in {\\mathcal{S}}_{{D}}$ and $\\hat\\Gamma\\in {\\mathcal{T}}_{{D}}$.",
      "The maximizer $\\hat\\gamma=(\\hat\\gamma_1,...,\\hat\\gamma_n)$ for the optimization problem (\\ref{2.2}) is unique and is given by the linear form",
      "The corresponding value is given by"],
  statement_short="$\\Lambda=\\hat Q^{-1}+\\hat\\Gamma$ uniquely with $\\hat Q$ $D$-banded and $\\hat\\Gamma$ vanishing on the band; the optimal strategy is linear in past increments via $\\hat\\Gamma$, with value $-\\sqrt{|\\hat Q|/|\\Sigma|}e^{-\\mu\\Lambda\\mu'/2}$.",
  tags=["existence", "uniqueness", "optimization", "matrix_decomposition"])
N("EP2", "equation", "Banded decomposition of the precision matrix (2.3)", fx("F4"), S1, 1.0)
N("EP3", "equation", "Optimal strategy formula (2.4)", fx("F5"), S1, 1.0)
N("EP4", "equation", "Optimal value formula (2.5)", fx("F6"), S1, 1.0)
N("RP2", "remark", "Deterministic optimal strategy in two trivial cases", fx("F7"), S1, 1.0, rigor="semi_formal",
  statement_short="For $D=n-1$ or diagonal $\\Sigma$, $\\hat Q=\\Sigma$, $\\hat\\Gamma=0$ and the optimal strategy is deterministic.")
c0 = FX["F8"]["start"]
CI = sp("the optimal strategy is given by", "(II) For", c0)[:-len("(II) For")].strip()
CII = sp("the optimal strategy is given by", "\\end{eqnarray*}", SRC.index("(II) For ${D}=1$", c0))
N("CP1", "corollary", "Explicit solution for delays $D=0$ and $D=1$", fx("F8"), S1, 1.0,
  assumptions=["For ${D}=0$ (no delay)", "For ${D}=1$"],
  conclusions=[CI, CII],
  parts=[{"assumptions": ["For ${D}=0$ (no delay)"], "conclusions": [CI]},
         {"assumptions": ["For ${D}=1$"], "conclusions": [CII]}],
  statement_short="Closed-form optimal strategy and value in terms of $\\Lambda$ for no delay ($D=0$) and for unit delay ($D=1$, tridiagonal $\\hat Q$).")
N("PP1", "proof", "Proof of Corollary 1.3", fx("F10"), S1, 1.0, proves="CP1", proof_strategy=["direct", "algebraic_manipulation"],
  statement_short="Identify $\\hat Q$ and $\\hat\\Gamma$ explicitly (diagonal for $D=0$; tridiagonal inverse formulas of Barrett 1979 for $D=1$) and substitute into (2.4)-(2.5).")
pp1 = FX["F10"]["start"]
N("PSP1", "proof_step", "Part (I): no delay", sp("(I) Observe that for", "completes the proof.", pp1), S1, 0.95,
  parent_id="PP1", step_order=1, subclass="case_split",
  statement_short="For $D=0$, $\\hat Q^{-1}$ is the diagonal of $\\Lambda$ and $\\hat\\Gamma$ its off-diagonal part; substitute.")
N("PSP2", "proof_step", "Part (II): unit delay", sp("(II) The matrix $\\hat Q$ satisfies", "we complete the proof.", pp1), S1, 0.95,
  parent_id="PP1", step_order=2, subclass="case_split",
  statement_short="For $D=1$, use tridiagonal-inverse formulas and the band equality $\\hat Q^{-1}=\\Lambda$ on $|i-j|\\le1$.")
N("PSP3", "proof_step", "Tridiagonal inverse formulas", sp("The matrix $\\hat Q$ satisfies $\\hat Q_{ij}=0$ for $|i-j|>1$", "{\\prod\\limits_{i=2}^{n-1}[\\hat Q^{-1}]_{ii}}.\n$$", pp1), S1, 0.75,
  parent_id="PSP2", step_order=1, subclass="apply_lemma",
  statement_short="$\\hat Q$ tridiagonal, so Barrett's formulas give the entries and determinant of $\\hat Q^{-1}$.")
N("PSP4", "proof_step", "Band entries equal those of $\\Lambda$", sp("Since $\\hat\\Gamma\\in{\\mathcal{T}}_1$ then", "\\end{eqnarray*}", pp1), S1, 0.75,
  parent_id="PSP2", step_order=2, subclass="substitute",
  statement_short="$\\hat\\Gamma\\in\\mathcal T_1$ gives $\\hat Q^{-1}_{ij}=\\Lambda_{ij}$ for $|i-j|\\le1$.")
N("PSP5", "proof_step", "Combine with (2.4)-(2.5)", sp("By combining the above equalities", "we complete the proof.", pp1), S1, 0.75,
  parent_id="PSP2", step_order=3, subclass="conclude", statement_short="Substitute into (2.4)-(2.5).")
N("RP3", "remark", "No Markov assumption needed", fx("F12"), S1, 1.0)
N("ExP1", "example", "Kac-Murdock-Szegő covariance with zero drift", fx("F13"), S1, 1.0,
  statement_short="For the Kac-Murdock-Szegő covariance $\\Sigma_{ij}=\\rho^{|i-j|}$ with $\\mu=0$, explicit optimal strategies and values for $D=0$ and $D=1$.")

# ---------------------------------------------------------------- Section 2: proof of Theorem 1.1
p = FX["F14"]["start"]
N("PP2", "proof", "Proof of Theorem 1.1", fx("F14"), S2, 1.0, proves="TP1",
  proof_strategy=["dual_argument", "construction"],
  statement_short="Duality/verification argument: existence of the banded decomposition from Barrett-Feinsilver, then a guessed strategy and an explicit Gaussian martingale-type measure satisfy the verification identity. Key step: under $\\hat{\\mathbb Q}$, $X\\sim\\mathcal N(0,\\hat Q)$ with $\\hat Q$ banded, so increments are independent of delayed information.")
N("PSP6", "proof_step", "Three-step plan", sp("The proof will be done in three steps.", "three steps.", p), S2, 0.75,
  parent_id="PP2", step_order=1, subclass="setup", statement_short="Announce the three-step structure.")
N("PSP7", "proof_step", "Step I: existence and uniqueness of the decomposition",
  sp("\\textbf{Step I:}", "the first step is completed.", p), S2, 0.95, parent_id="PP2", step_order=2, subclass="setup",
  statement_short="Prove existence and uniqueness of decomposition (2.3) via Barrett-Feinsilver.")
N("PSP8", "proof_step", "Aim of Step I", sp("In this step we provide an existence", "perfectly fit our purposes.", p), S2, 0.75,
  parent_id="PSP7", step_order=1, subclass="setup", statement_short="State the goal and the tool (Barrett-Feinsilver 1981).")
N("PSP9", "proof_step", "Minor notation $C^I_J$ and $[a:b]$", sp("First we introduce some notations.", "by $[a:b]$.", p), S2, 0.75,
  parent_id="PSP7", step_order=2, subclass="introduce_variable",
  statement_short="Introduce minors $C^I_J$ of a matrix and the index vector $[a:b]$.")
N("PSP10", "proof_step", "Positive principal minors by Sylvester's criterion", sp("Since ${\\Lambda}$ is positive definite it follows by Sylvester", "for all $k\\leq n-{D}$.", p), S2, 0.75,
  parent_id="PSP7", step_order=3, subclass="apply_lemma",
  statement_short="Sylvester's criterion gives positivity of the needed consecutive principal minors of $\\Lambda$.")
N("PSP11", "proof_step", "Apply Barrett-Feinsilver Theorem 5.5", sp("Hence, by applying Theorem 5.5 in", "$\\hat\\Gamma={\\Lambda}-R$.", p), S2, 0.75,
  parent_id="PSP7", step_order=4, subclass="apply_lemma",
  statement_short="Theorem 5.5 of Barrett-Feinsilver with $r=s=D+1$ gives a unique $R$ with $R^{-1}\\in\\mathcal S_D$, $\\Lambda-R\\in\\mathcal T_D$; set $\\hat Q=R^{-1}$.")
N("PSP12", "proof_step", "Symmetry of $R$ from uniqueness", sp("Since ${\\Sigma}$ is symmetric then from uniqueness", "the first step is completed.", p), S2, 0.75,
  parent_id="PSP7", step_order=5, subclass="conclude", statement_short="Uniqueness and symmetry of $\\Sigma$ give symmetric $R$.")
N("PSP13", "proof_step", "Step II: verification result",
  sp("\\textbf{Step II: }", "This completes the proof of (\\ref{4.2+}).", p), S2, 0.95, parent_id="PP2", step_order=3, subclass="setup",
  statement_short="Define the measures $\\mathcal Q_D$ and prove the duality verification result.")
N("EP5", "equation", "Delayed martingale condition (4.2-)", fx("F15"), S2, 1.0)
N("ClP1", "claim", "Verification result for exponential utility with delay",
  sp("In this step we prove the following verification result:", "This completes the proof of (\\ref{4.2+}).", p), S2, 0.9,
  assumptions=["If a triplet $(\\tilde\\gamma,\\tilde{\\mathbb Q},C)\\in \\mathcal A_{{D}}\\times \\mathcal Q_{{D}}\\times\\mathbb R$ satisfies"],
  conclusions=[clean("then $\\tilde\\gamma\\in\\mathcal A_{{D}}$ is the unique optimal portfolio for the optimization \n problem (\\ref{2.2}) and the corresponding value is \n $\n\\mathbb E_{\\mathbb P}\\left[-\\exp\\left(- V^{\\tilde\\gamma}_n\\right)\\right]=-e^{-C}.$")],
  statement_short="If $V^{\\tilde\\gamma}_n+\\log(d\\tilde{\\mathbb Q}/d\\mathbb P)=C$ for some $\\tilde{\\mathbb Q}\\in\\mathcal Q_D$, then $\\tilde\\gamma$ is the unique optimizer with value $-e^{-C}$.",
  tags=["duality", "verification"])
N("EP6", "equation", "Verification identity (4.2-+)", fx("F16"), S2, 1.0)
N("PSP14", "proof_step", "Zero expected gain under $\\mathcal Q_D$", sp("Indeed, using similar arguments as in the proof of Lemma 2.1", "\\right]<\\infty$.", p), S2, 0.75,
  parent_id="ClP1", step_order=1, subclass="apply_lemma",
  statement_short="As in Lemma 2.1 of Bank-Dolinsky 2021, $\\mathbb E_{\\mathbb Q}[V^\\gamma_n]=0$ when $\\mathbb E_{\\mathbb P}[e^{-V^\\gamma_n}]<\\infty$.")
N("PSP15", "proof_step", "Value at the candidate equals $-C$", sp("From (\\ref{4.2-+})\n $\\mathbb E_{\\mathbb P}", "\\end{equation}", SRC.index("Indeed, using similar arguments")), S2, 0.75,
  parent_id="ClP1", step_order=2, subclass="algebraic_manipulation",
  statement_short="From (4.2-+), $\\log\\mathbb E_{\\mathbb P}[e^{-V^{\\tilde\\gamma}_n}]=-C=-\\mathbb E_{\\tilde{\\mathbb Q}}[\\log d\\tilde{\\mathbb Q}/d\\mathbb P]$.")
N("EP7", "equation", "Duality equality at the candidate (4.2)", fx("F17"), S2, 1.0)
N("PSP16", "proof_step", "Reduction to the duality inequality", sp("Next, it is well known that for a strictly concave", "\\end{equation}", SRC.index("Next, it is well known")), S2, 0.75,
  parent_id="ClP1", step_order=3, subclass="setup",
  statement_short="Uniqueness by strict concavity; it remains to prove the general duality inequality (4.2+).")
N("EP8", "equation", "Duality inequality (4.2+)", fx("F18"), S2, 1.0)
N("PSP17", "proof_step", "Proof of the duality inequality (4.2+)", sp("Let us establish (\\ref{4.2+}).", "This completes the proof of (\\ref{4.2+}).", p), S2, 0.75,
  parent_id="ClP1", step_order=4, subclass="bound_estimate",
  statement_short="Prove (4.2+) via Legendre-Fenchel duality and optimization over a scalar $z$.")
N("PSP18", "proof_step", "WLOG finite exponential moment", sp("Without loss of generality assume that", "is trivial).", p), S2, 0.75,
  parent_id="PSP17", step_order=1, subclass="setup", statement_short="Reduce to $\\mathbb E_{\\mathbb P}[e^{-V^\\gamma_n}]<\\infty$.")
N("PSP19", "proof_step", "Legendre-Fenchel lower bound", sp("Then\nfor any $z\\in\\mathbb R$", "The last equality is straightforward.", p), S2, 0.75,
  parent_id="PSP17", step_order=2, subclass="bound_estimate",
  statement_short="Add $z\\frac{d\\mathbb Q}{d\\mathbb P}V^\\gamma_n$ (zero mean) and apply $xy\\le e^x+y(\\log y-1)$ to get a lower bound in $z$.")
N("PSP20", "proof_step", "Optimize over $z$", sp("From simple calculus it follows that the concave function", "This completes the proof of (\\ref{4.2+}).", p), S2, 0.75,
  parent_id="PSP17", step_order=3, subclass="conclude",
  statement_short="Maximize the concave bound over $z>0$; the maximum $z^*=e^{-\\mathbb E_{\\mathbb Q}[\\log d\\mathbb Q/d\\mathbb P]}$ gives (4.2+).")
N("PSP21", "proof_step", "Step III: the candidate strategy and measure",
  sp("\\textbf{Step III:}", "This yields\n (\\ref{4.2-}) and completes the proof.", p), S2, 0.95, parent_id="PP2", step_order=4, subclass="conclude",
  statement_short="Construct $\\hat{\\mathbb Q}$ for $\\hat\\gamma$ and check it lies in $\\mathcal Q_D$.")
N("PSP22", "proof_step", "Admissibility of $\\hat\\gamma$", sp("In view of Step I the portfolio", "we obtain that $\\hat\\gamma\\in\\mathcal A_{{D}}$.", p), S2, 0.75,
  parent_id="PSP21", step_order=1, subclass="setup",
  statement_short="$\\hat\\gamma$ is well defined and predictable since $\\hat\\Gamma$ vanishes on the band.")
N("PSP23", "proof_step", "Define $C$ and $\\hat{\\mathbb Q}$", sp("Set \n\\begin{equation*}\nC:=", "\\end{equation}", SRC.index("\\textbf{Step III:}")), S2, 0.75,
  parent_id="PSP21", step_order=2, subclass="introduce_variable",
  statement_short="Set $C=\\frac12(\\log|\\Sigma|-\\log|\\hat Q|+\\mu\\Lambda\\mu')$ and $d\\hat{\\mathbb Q}/d\\mathbb P=e^{C-V^{\\hat\\gamma}_n}$.")
N("EP9", "equation", "Candidate dual measure (4.3)", fx("F21"), S2, 1.0)
N("PSP24", "proof_step", "Reduction via Step II", sp("From Step II it follows that in order to complete", "satisfies $\\hat{\\mathbb Q}\\in\\mathcal Q_{{D}}$.", p), S2, 0.75,
  parent_id="PSP21", step_order=3, subclass="setup",
  statement_short="By the verification result, it remains to show $\\hat{\\mathbb Q}\\in\\mathcal Q_D$.")
N("PSP25", "proof_step", "Density of $\\hat{\\mathbb Q}$ as a Gaussian likelihood ratio", sp("To that end \ndefine $X=(X_1,...,X_n)$", "{\\sqrt {(2\\pi)^n |\\Sigma|}}}.$$", p), S2, 0.75,
  parent_id="PSP21", step_order=4, subclass="algebraic_manipulation",
  statement_short="With $X_i=S_i-S_{i-1}$, write $V^{\\hat\\gamma}_n$ as a quadratic form and $d\\hat{\\mathbb Q}/d\\mathbb P$ as the ratio of $\\mathcal N(0,\\hat Q)$ and $\\mathcal N(\\mu,\\Sigma)$ densities.")
N("PSP26", "proof_step", "$X\\sim\\mathcal N(0,\\hat Q)$ under $\\hat{\\mathbb Q}$", sp("Hence, the relation $\\left(X;{\\mathbb P}\\right)", "\\right)\\right]<\\infty$.", SRC.index("To that end")), S2, 0.75,
  parent_id="PSP21", step_order=5, subclass="invoke_identity",
  statement_short="$\\hat{\\mathbb Q}$ is a probability measure with $X\\sim\\mathcal N(0,\\hat Q)$ and finite entropy.")
N("PSP27", "proof_step", "Banded $\\hat Q$ gives the delayed martingale property", sp("Finally, from \nthe property", "completes the proof.", SRC.index("To that end")), S2, 0.75,
  parent_id="PSP21", step_order=6, subclass="conclude",
  statement_short="$\\hat Q$ $D$-banded makes $X_k$ independent of the delayed past, giving (4.2-).")
N("RP4", "remark", "Gaussian equivalent measures and equivalent martingale measures", fx("F22"), S2, 1.0,
  statement_short="Any positive definite $Q$ gives an equivalent measure with $X\\sim\\mathcal N(0,Q)$; diagonal $Q$ yields an EMM, so the market is arbitrage-free, and $\\mathcal Q_D$ contains all EMMs.")

# ---------------------------------------------------------------- Section 3
q = SRC.index("\\section{Computational Results}")
N("PP3", "proof", "Derivation of the minor characterization of $\\hat Q^{-1}$",
  sp("In view of Corollary 3.2 in", "for all $i\\leq n-{D}-1$.", q), S3, 0.7, proves="ClP2", proof_strategy=["direct"],
  statement_short="Corollary 3.2 of Barrett-Feinsilver turns $\\hat Q\\in\\mathcal S_D$ into vanishing $(D+1)$-minors of $R=\\hat Q^{-1}$; symmetry reduces to super minors and positivity of principal minors is inherited from $\\Lambda$.")
N("ClP2", "claim", "Characterization of $R=\\hat Q^{-1}$ by vanishing minors",
  sp("Thus, from Theorem 3.4 in", "\\end{equation}", q), S3, 0.75,
  assumptions=[],
  conclusions=[clean(sp("the matrix $R:=\\hat Q^{-1}$ is the unique", "\\end{equation}", q))],
  statement_short="$R=\\hat Q^{-1}$ is the unique symmetric matrix agreeing with $\\Lambda$ on the band and with vanishing $(D+1)$ super minors (3.1).")
N("EP10", "equation", "Vanishing super minors (3.1)", fx("F23"), S3, 1.0)
N("ClP3", "claim", "Minors can be ordered to determine one unknown entry each",
  sp("Observe that it is possible to order the $({D}+1)$-minors", "linear equation for this unknown element.", q), S3, 0.7,
  assumptions=[], conclusions=[sp("it is possible to order the $({D}+1)$-minors", "linear equation for this unknown element.", q)],
  statement_short="The minors in (3.1) can be ordered so each is linear in a single unknown entry of $R$.")
N("PP4", "proof", "Laplace-expansion argument for the ordering of minors",
  sp("For example, the first minor", "determine it in a similar manner.", q), S3, 0.65, proves="ClP3",
  proof_strategy=["construction", "algebraic_manipulation"],
  statement_short="Laplace expansion of the first minor along its first row isolates $R_{1,D+2}$ with a nonzero known coefficient; repeat for the next minors.")
N("DP11", "definition", "Index vector $[a:b]^{i\\to j}$",
  sp("For four integers $a \\leq i \\leq b \\leq j$", "(a,a+1,..,i-1,i+1,..,b, j)$.", q), S3, 0.9,
  definiendum="$[a:b]^{i \\to j}$")
N("AP1", "algorithm", "Banded Matrix Decomposition", fx("F25"), S3, 1.0,
  input=[clean("$\\Sigma \\in M_n(\\mathbb R)$ - a real Positive Definite matrix, ${D} \\leq n-1$ - band width.")],
  output=[clean("Two matrices $R+\\hat\\Gamma={\\Sigma}^{-1}$ such that $R^{-1} \\in {\\mathcal{S}}_{{D}}, \\hat\\Gamma \\in {\\mathcal{T}}_{{D}}$.")],
  statement_short="Computes the decomposition $\\Sigma^{-1}=R+\\hat\\Gamma$ by filling the off-band entries of $R$ diagonal by diagonal, each from a vanishing $(D+1)$-minor via Laplace expansion.",
  tags=["matrix_decomposition", "banded_matrices"])
steps = pseudocode_steps(facts, "F25", nodes[-1], first_seq=1)
subs = {1: ("initialize", "Invert $\\Sigma$ and copy the band of $\\Lambda$ into $R$", None),
        2: ("loop", "Loop over off-band diagonals $m$", None),
        3: ("loop", "Loop over positions $i$ on diagonal $m$", None),
        4: ("compute", "Fill symmetric entry from vanishing minor",
            "Solve the vanishing $(D+1)$-minor for $R_{i,i+m}$ by Laplace expansion along its first row."),
        5: ("compute", "Set $\\hat\\Gamma=\\Lambda-R$", None),
        6: ("return", "Output $R,\\hat\\Gamma$", None)}
for k, st in enumerate(steps, 1):
    sc, nm, ss = subs[k]
    st["subclass"] = st["subclass"] or sc
    st["name"] = nm
    if ss:
        st["statement_short"] = ss
nodes.extend(steps)
N("RP5", "remark", "Computational complexity of the algorithm", fx("F27"), S3, 1.0,
  statement_short="Algorithm 1 costs $O(n^{2.373})$ for inversion plus $O(n^2D^{2.373})$ for minors; Toeplitz $\\Sigma$ allows $O(n^2D^{2.373})$ via Trench's algorithm.")
N("DP12", "definition", "Fractional Brownian motion",
  sp("A fractional Brownian motion (fBm)", "\\end{equation}", q), S3, 0.9, origin="external",
  origin_citation="Mandelbrot & Van Ness 1968", definiendum="fractional Brownian motion",
  genus="centered Gaussian process $B^{{\\mathcal{H}}}_t$, $t\\geq 0$", differentia=["with the covariance function"])
N("EP11", "equation", "fBm covariance", fx("F28"), S3, 1.0, origin="external", origin_citation="Mandelbrot & Van Ness 1968")
N("DP13", "definition", "Discretized fBm market",
  sp("We consider a discretized version of the fBm framework.", "n\\Delta t=T$.", q), S3, 0.8,
  definiendum=["$\\Delta t$", "$T$"])
N("DP14", "definition", "Stock price in the discretized fBm market",
  sp("The stock price at time $k \\Delta t$ is given by", "$, $k=0,1,\\dots,n$.", q), S3, 0.8, definiendum="$S_k$")
N("ClP4", "claim", "Toeplitz covariance of discretized fBm increments",
  sp("In this case \n$\\mu=0$ and by", "\\end{align}", q), S3, 0.75,
  assumptions=[], conclusions=[sp("$\\mu=0$ and by", "\\end{align}", q)],
  statement_short="The fBm increments have zero mean and Toeplitz covariance $\\frac{\\Delta t^{2H}}{2}(|i-j-1|^{2H}+|i-j+1|^{2H}-2|i-j|^{2H})$.")
N("EP12", "equation", "Discretized fBm covariance", fx("F29"), S3, 1.0)
N("ClP5", "claim", "Positive definiteness of the discretized fBm covariance",
  sp("By following carefully the proof of Proposition 1.6", "is positive definite.", q), S3, 0.75, rigor="semi_formal",
  assumptions=[], conclusions=["$\\Sigma$ is positive definite"])
N("ClP6", "claim", "Value is invariant to the time step $\\Delta t$",
  sp("Moreover, when $\\Delta t$ is changed", "the value is invariant to $\\Delta t$.", q), S3, 0.75,
  assumptions=[clean(sp("for fixed values of $n$, the delay", "parameter", q))],
  conclusions=["the value is invariant to $\\Delta t$"])
N("ClP7", "claim", "Value decreases with the delay (numerical)",
  sp("The results, displayed in Fig.", "for both models.", q), S3, 0.7, rigor="numerical",
  assumptions=[], conclusions=[sp("show the decrease in the value", "for both models.", q)])
N("ClP8", "claim", "KMS model: value increases with correlation $\\rho$ (numerical)",
  sp("As expected, for any delay ${D}$ the value is monotonically increasing", "as $\\rho$ increases.", q), S3, 0.7, rigor="numerical",
  assumptions=["for any delay ${D}$"], conclusions=[sp("the value is monotonically increasing", "as $\\rho$ increases.", q)])
N("ClP9", "claim", "fBm with $H>1/2$: value increases towards 0 (numerical)",
  sp("For high ${\\mathcal{H}}$ values", "towards the maximum $0$.", q), S3, 0.7, rigor="numerical",
  assumptions=["For high ${\\mathcal{H}}$ values (${\\mathcal{H}}>0.5$)"], conclusions=[sp("the increments are positively correlated hence", "towards the maximum $0$.", q)])
N("ClP10", "claim", "fBm with $H=1/2$: value $-1$ for every delay",
  sp("For ${\\mathcal{H}}=0.5$ we reduce to", "regardless of the delay.", q), S3, 0.75,
  assumptions=["For ${\\mathcal{H}}=0.5$"], conclusions=["the value drops to $-1$ regardless of the delay"])
N("ClP11", "claim", "fBm with $H<1/2$: non-monotonic dependence on $H$ (numerical)",
  sp("For low ${\\mathcal{H}}$ values", "regarding the current price.", q), S3, 0.7, rigor="numerical",
  assumptions=["For low ${\\mathcal{H}}$ values (${\\mathcal{H}}<0.5$)"],
  conclusions=[sp("the increments are negatively correlated hence the value increases", "non-monotonic in ${\\mathcal{H}}$.", q)])
N("ClP12", "claim", "Value increases towards zero with $n$ for fixed delay (numerical)",
  sp("For a fixed delay ${D}$, the value increases towards zero with $n$", "\\cite{R:1997, C:2003}).", q), S3, 0.7, rigor="numerical",
  assumptions=["For a fixed delay ${D}$"], conclusions=["the value increases towards zero with $n$"])
N("ClP13", "claim", "Value converges to a negative limit for fixed delay ratio (numerical)",
  sp("Increasing the delay ${D}_n$ with $n$", "for $n=1024$.", q), S3, 0.65, rigor="numerical",
  assumptions=[sp("Increasing the delay ${D}_n$ with $n$", "fixed", q)],
  conclusions=[sp("The value appears to converge to a negative number", "for $n=1024$.", q)])

# ---------------------------------------------------------------- edges
T = "term"
# definitions -> definitions
for s, t in [("DP1", "AssumP2"), ("DP1", "DP5"), ("DP1", "DP8"), ("AssumP2", "DP2"), ("DP2", "DP3"),
             ("DP4", "DP5"), ("DP5", "DP6"), ("DP6", "DP7"), ("DP6", "DP8"), ("DP7", "DP8"),
             ("DP8", "ProbP1"), ("DP7", "ProbP1"), ("DP8", "RP1"), ("DP6", "RP1"), ("DP2", "DP9"), ("DP4", "DP9"),
             ("DP2", "DP10"), ("DP4", "DP10"), ("DP12", "DP13"), ("DP13", "DP14"), ("DP1", "DP14")]:
    E(s, t, conf=0.8)
E("AssumP1", "DP8", conf=0.6, basis="inferred")
E("ProbP1", "RP1", conf=0.85)
# Theorem 1.1
for s in ["DP1", "DP2", "DP3", "DP4", "DP7", "DP8", "DP9", "DP10"]:
    E(s, "TP1", conf=0.8)
E("AssumP2", "TP1", conf=0.8, basis="inferred")
E("RP1", "TP1", conf=0.75, basis="inferred")
E("ProbP1", "TP1", "resolves", conf=0.9, basis="inferred")
# Remark 1.2
for s in ["DP2", "DP3", "DP4", "DP6", "DP9", "DP10"]:
    E(s, "RP2", conf=0.75)
E("TP1", "RP2", conf=0.8, basis="inferred")
# Corollary 1.3 and its proof
for s in ["DP1", "DP2", "DP3", "DP4", "DP8"]:
    E(s, "CP1", conf=0.8)
E("TP1", "CP1", "specializes", conf=0.85, basis="inferred")
E("ProbP1", "CP1", "resolves", conf=0.8, basis="inferred")
E("TP1", "PP1", conf=0.85, basis="inferred")
E("DP9", "PP1", conf=0.8)
E("DP10", "PP1", conf=0.8)
# Example 1.5
for s in ["DP2", "DP3", "DP4"]:
    E(s, "ExP1", conf=0.8)
E("TP1", "ExP1", "illustrates", conf=0.8, basis="inferred")
# proof of Theorem 1.1
E("PP2", "TP1", "proves", conf=0.95, basis="named")
for s in ["DP1", "DP2", "DP3", "DP4", "DP5", "DP7", "DP8", "DP9", "DP10"]:
    E(s, "PP2", conf=0.8)
E("ProbP1", "PP2", conf=0.8)
E("PSP10", "PSP11", conf=0.85, basis="inferred")
E("PSP11", "PSP12", conf=0.8, basis="inferred")
E("PSP9", "PSP10", conf=0.8)
E("PSP14", "PSP15", conf=0.8, basis="inferred")
E("PSP14", "PSP19", conf=0.85, basis="inferred")
E("PSP18", "PSP19", conf=0.75, basis="inferred")
E("PSP19", "PSP20", conf=0.85, basis="inferred")
E("PSP7", "PSP22", conf=0.9, basis="named")
E("ClP1", "PSP24", conf=0.9, basis="named")
E("PSP13", "PSP27", conf=0.75)      # Q_D defined in Step II
E("PSP25", "PSP26", conf=0.85, basis="inferred")
E("PSP26", "PSP27", conf=0.8, basis="inferred")
E("TP1", "PSP24", conf=0.95, basis="ref", mention=True)
E("TP1", "PSP21", conf=0.95, basis="ref", mention=True)
# Remark 2.1
for s in ["DP2", "DP3"]:
    E(s, "RP4", conf=0.75)
E("PSP13", "RP4", conf=0.8)   # Q_D
E("PSP25", "RP4", conf=0.75)  # X
# Section 3
for s in ["DP3", "DP4", "DP9", "PSP9"]:
    E(s, "PP3", conf=0.8)
E("TP1", "PP3", conf=0.8, basis="inferred")
for s in ["DP3", "DP4", "PSP9"]:
    E(s, "ClP2", conf=0.8)
E("TP1", "ClP2", conf=0.8, basis="inferred")
E("PP3", "ClP2", "proves", conf=0.7, basis="inferred")
E("PSP9", "ClP3", conf=0.75)
E("PP4", "ClP3", "proves", conf=0.7, basis="inferred")
for s in ["DP3", "DP4", "PSP9"]:
    E(s, "PP4", conf=0.8)
E("ClP2", "PP4", conf=0.8, basis="inferred")
for s in ["DP2", "DP3", "DP4", "DP9", "DP10", "DP11", "PSP9"]:
    E(s, "AP1", conf=0.8)
E("TP1", "AP1", conf=0.85, basis="inferred")
E("ClP2", "AP1", conf=0.85, basis="inferred")
E("ClP3", "AP1", conf=0.85, basis="inferred")
for s in ["DP2", "DP4"]:
    E(s, "RP5", conf=0.75)
for s in ["DP2", "DP13", "DP14"]:
    E(s, "ClP4", conf=0.8)
E("DP2", "ClP5", conf=0.75)
E("ClP4", "ClP5", conf=0.85, basis="inferred")
E("ClP4", "ClP6", conf=0.85, basis="inferred")
E("DP13", "ClP6", conf=0.8)
E("DP4", "ClP6", conf=0.75)
E("TP1", "ClP6", conf=0.7, basis="inferred")
for t in ["ClP7", "ClP8", "ClP9", "ClP11", "ClP12", "ClP13"]:
    E("AP1", t, conf=0.7, basis="inferred")
    E("DP4", t, conf=0.75)
E("ExP1", "ClP7", conf=0.75, basis="inferred")
E("ClP4", "ClP7", conf=0.75, basis="inferred")
E("ExP1", "ClP8", conf=0.8, basis="inferred")
for t in ["ClP9", "ClP10", "ClP11"]:
    E("DP12", t, conf=0.8)
    E("ClP4", t, conf=0.75, basis="inferred")
E("RP2", "ClP10", conf=0.75, basis="inferred")
for t in ["ClP12", "ClP13"]:
    E("DP13", t, conf=0.75)
    E("ClP4", t, conf=0.75, basis="inferred")
    E("DP12", t, conf=0.75)

graph = {
    "metadata": {
        "title": "Exponential Utility Maximization in a Discrete Time Gaussian Framework",
        "arxiv_id": "2305.18136",
        "authors": ["Yan Dolinsky", "Or Zuk"],
        "year": 2023,
        "annotator": "agent-extraction",
        "model": "claude-opus-5-5",
        "effort": "default",
        "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
        "extraction_date": "2026-11-05",
        "rigor_nonformal_count": sum(1 for n in nodes if "rigor" in n),
        "paper_style": ["theorem_proof", "computational"],
        "extraction_notes": [],
        "extraction_comment": "",
    },
    "nodes": nodes,
    "edges": edges,
}
NOTES = [
    {"category": "type_uncertain", "nodes": ["ProbP1", "EP1"],
     "note": "The numbered display (2.2) is the optimization problem; kept as an equation nested in a prose problem node spanning the sentence that poses it, rather than retyping the equation fact."},
    {"category": "boundary_uncertain", "nodes": ["ClP1", "PSP13"],
     "note": "The unnumbered 'verification result' of Step II is cited later ('From Step II it follows'), so it is a Level-1 claim nested in the Step II step, spanning its statement and argument; the definition of Q_D before it stays in the Step II step."},
    {"category": "boundary_uncertain", "nodes": ["PP3", "ClP2", "PP4", "ClP3"],
     "note": "Section 3 derives the algorithm in running text; split into a characterization claim of R (with the preceding argument as its proof) and an ordering-of-minors claim (with the Laplace-expansion paragraph as its proof)."},
    {"category": "rule_conflict", "nodes": ["PSP9", "PSP13", "PSP25"],
     "note": "Notation introduced inside the proof of Theorem 1.1 (minors C^I_J and [a:b], the set Q_D, the vector X) is reused in Remark 2.1 and Section 3; kept as proof steps (step rule 4) with uses edges from those steps."},
    {"category": "not_extracted", "nodes": [],
     "note": "Literature review, description of the R implementation and timings, the figure, and the closing future-work sentence are not nodes."},
]
graph["metadata"]["extraction_notes"] = NOTES
report = finalize(graph, read_tex(TEX))
for k in ("errors", "warnings"):
    print(k.upper(), len(report.get(k, [])))
    for x in report.get(k, []):
        print("  ", x)
print({k: v for k, v in report.items() if k not in ("errors", "warnings")})
assert not report["errors"], report["errors"]
json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
print("wrote", OUT)
