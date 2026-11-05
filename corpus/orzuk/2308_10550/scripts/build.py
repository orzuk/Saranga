#!/usr/bin/env python3
"""Build the SARANGA v7 graph of arXiv 2308.10550 (Dolinsky & Zuk, Delayed Semistatic Hedging).

Run: python3 build.py [scratch_dir]
Node choices and spans were decided by reading the paper; this script only slices text.
"""
import json, os, re, subprocess, sys
sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
from extraction_finalize import finalize
from latex_facts import read_tex

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = "/mnt/c/Code/Github/Saranga/corpus/orzuk/2308_10550/arxiv_src/revision.tex"
OUT = "/mnt/c/Code/Github/Saranga/corpus/orzuk/2308_10550/2308_10550.json"
SCR = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_orzuk/2308_10550"
FACTS = os.path.join(SCR, "facts.json")
if not os.path.exists(FACTS):
    subprocess.run([sys.executable, "/mnt/c/Code/Github/Saranga/src/latex_facts.py", TEX, "--out", FACTS], check=True)
facts = json.load(open(FACTS))
SRC = facts["source"]
F = {f["id"]: f for f in facts["facts"]}
SECS = facts["sections"]


def rx(anchor):
    anchor = re.sub(r"\\n(?![a-zA-Z])", " ", anchor)
    parts = re.split(r"\s+", anchor.strip())
    return re.compile(r"\s*".join(re.escape(p) for p in parts))


def find(anchor, after=0):
    m = rx(anchor).search(SRC, after)
    assert m, f"anchor not found: {anchor!r} after {after}"
    return m


TRAIL = re.compile(r"(\s|\\\\|\$\{\}\$)+$")


def span(a, b, after=0):
    s = find(a, after).start()
    e = find(b, s + 1).end() if b else None
    return s, e


def section_of(pos):
    cur = None
    for s in SECS:
        if s["inside"] is None and s["start"] <= pos:
            cur = s
    return f"{cur['number']} {cur['title']}" if cur else "Front matter"


nodes, edges = [], []
POS = {}


def add(nid, typ, name, s, e, origin="paper", conf=0.75, **kw):
    st = SRC[s:e]
    st = TRAIL.sub("", st)
    n = {"id": nid, "type": typ, "name": name, "statement": st, "section": section_of(s),
         "origin": origin, "confidence": conf}
    n.update(kw)
    nodes.append(n)
    POS[nid] = (s, s + len(st))
    n["_pos"] = s
    return n


def prose(nid, typ, name, a, b, after=0, **kw):
    s, e = span(a, b, after)
    return add(nid, typ, name, s, e, **kw)


def env(nid, fid, typ, name, conf=1.0, **kw):
    f = F[fid]
    n = {"id": nid, "type": typ, "name": name, "statement": f["statement"],
         "section": section_of(f["start"]), "origin": kw.pop("origin", "paper"), "confidence": conf}
    n.update(kw)
    nodes.append(n)
    POS[nid] = (f["start"], f["end"])
    n["_pos"] = f["start"]
    return n


def sub(nid, a, b):
    """verbatim sub-span of a node's statement (for assumptions/conclusions)."""
    st = next(n for n in nodes if n["id"] == nid)["statement"]
    m = rx(a).search(st)
    assert m, (nid, a)
    if b is None:
        return st[m.start():]
    m2 = rx(b).search(st, m.end() if b != a else m.start())
    assert m2, (nid, b)
    return st[m.start():m2.end()]


PSP = [0]


def steps(parent, specs, lo=None, hi=None):
    """specs: list of (anchor, subclass, name, short[, children-specs]). Each step runs to the next."""
    plo, phi = POS[parent] if lo is None else (lo, hi)
    starts = []
    cur = plo
    for sp in specs:
        m = find(sp[0], cur)
        assert m.start() < phi, (parent, sp[0])
        starts.append(m.start())
        cur = m.end()
    out = []
    for i, sp in enumerate(specs):
        s = starts[i]
        e = starts[i + 1] if i + 1 < len(specs) else phi
        PSP[0] += 1
        sid = f"PSP{PSP[0]}"
        par = next(n for n in nodes if n["id"] == parent)
        conf = 0.95 if sp[0].lstrip().startswith(("\\textbf{Step", "For $i", "\\noindent For")) else 0.75
        add(sid, "proof_step", sp[2], s, e, origin=par["origin"], conf=conf, parent_id=parent,
            step_order=i + 1, subclass=sp[1], statement_short=sp[3])
        nodes[-1]["section"] = par["section"]
        if len(sp) > 4 and sp[4]:
            steps(sid, sp[4], s, POS[sid][1])
        out.append(sid)
    return out


def E(s, t, typ="uses", conf=0.8, basis="inferred", **kw):
    e = {"source": s, "target": t, "type": typ, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)


# ---------------------------------------------------------------- Section 2: discrete model
prose("DP1", "definition", "Probability space and risky asset", r"Let $(\Omega,\mathcal F,\mathbb P)$ be a complete", "fixed finite time horizon.",
      definiendum=["$(\\Omega,\\mathcal F,\\mathbb P)$", "$S=(S_k)_{0\\leq k\\leq n}$", "$n$"], conf=0.85)
prose("AssumP1", "assumption", "Zero-interest bank account", "We assume that the investor has a bank account", "bears no interest.", conf=0.85)
prose("AssumP2", "assumption", "i.i.d. Gaussian stock increments", "We assume that the initial stock price $S_0$", r"for some $\sigma>0$.", conf=0.85,
      statement_short="Initial price $S_0$ is known; increments $X_k=S_k-S_{k-1}$ are i.i.d. $\\mathcal N(\\mu,\\sigma^2)$.")
prose("DP2", "definition", "Delay of D trading times", r"We fix a nonnegative integer number", "delay of ${D}$ trading times.", conf=0.85, definiendum="${D}$")
prose("AssumP3", "assumption", "Delay shorter than horizon", "Without loss of generality we assume that ${D}<n$.", None, conf=0.85)
nodes[-1]["statement"] = "Without loss of generality we assume that ${D}<n$."; 
prose("DP3", "definition", "Delayed information filtration", "Hence, the investor's flow of information", "$k=0,1,...,n$.", conf=0.85, definiendum="$\\mathcal G_k$")
prose("DP4", "definition", "Semistatic hedging setup", "We consider the following semistatic hedging setup.", "(determined by the market).", conf=0.85,
      definiendum=["semistatic hedging setup", "$\\hat\\nu$"],
      statement_short="Investor trades the stock dynamically at times $0,\\dots,n-1$ and buys any static payoff $f(S_n)$ at price $\\int f d\\hat\\nu$.")
prose("AssumP4", "assumption", "Normal pricing measure", r"We assume that $\hat\nu$ is a normal distribution.", None, conf=0.85)
nodes[-1]["statement"] = SRC[find(r"We assume that $\hat\nu$ is a normal distribution.").start():find(r"We assume that $\hat\nu$ is a normal distribution.").end()]
prose("RP1", "remark", "No-arbitrage forces mean of pricing measure", "Observe that \nthe market allows to buy one stock", r"$\int z d\hat\nu(z)=S_0$.", conf=0.8)
prose("AssumP5", "assumption", "Pricing measure N(S_0, n hat-sigma^2)", r"Hence, we assume that $\hat\nu=\mathcal N(S_0, n\hat\sigma^2)$", r"for some $\hat\sigma>0$.", conf=0.85)
prose("DP5", "definition", "Trading strategy (discrete semistatic)", "Formally, a trading strategy is a pair", r"$\int |f| d\hat\nu<\infty$.", conf=0.9,
      definiendum="trading strategy", genus="pair $\\pi=(\\gamma,f)$",
      differentia=["$\\gamma=(\\gamma_1,...,\\gamma_n)$ is a predictable process with respect to $\\{\\mathcal G_k\\}_{k=0}^n$",
                   "$f:\\mathbb R\\rightarrow\\mathbb R$ is a continuous function such that $\\int |f| d\\hat\\nu<\\infty$"])
prose("DP6", "definition", "Set of trading strategies A", r"Denote by $\mathcal A$ the set of all trading strategies.", None, conf=0.9, definiendum="$\\mathcal A$")
nodes[-1]["statement"] = r"Denote by $\mathcal A$ the set of all trading strategies."
s = find(r"For $\pi=(\gamma,f)\in\mathcal A$ the corresponding portfolio value").start()
add("DP7", "definition", "Terminal portfolio value V_n", s, F["F1"]["outer_end"], conf=0.9, definiendum="$V^{\\pi}_n$")
env("EP1", "F1", "equation", "Portfolio value (eq:value)")
env("RP2", "F2", "remark", "Equivalence of trading strategies (discrete)",
    statement_short="Two strategies give the same terminal value iff their stock positions differ by a constant $c$ and their payoffs by a linear function of slope $c$.")
prose("DP8", "definition", "Equivalent trading strategies", "We say that two trading strategies", "with slope equal to $c$.", conf=0.85,
      definiendum="equivalent trading strategies")
prose("ClP1", "claim", "Equivalent strategies iff equal terminal value", r"Clearly if $\pi=(\gamma,f)$", "Let us argue that the opposite direction also holds.", conf=0.75,
      assumptions=[], conclusions=[])
prose("PP1", "proof", "Proof that equal values imply equivalence", r"Indeed, let \n$\pi=(\gamma,f)$", "are equivalent.", after=POS["ClP1"][0], conf=0.75,
      statement_short="Conditioning on $S_0,\\dots,S_{n-1}$: $f-\\tilde f$ plus a linear term is measurable, and full support of $S_n$ forces $f-\\tilde f$ linear.",
      proof_strategy=["direct"])
prose("ProbP1", "problem", "Exponential utility maximization (discrete delayed semistatic)", "Next, the investor’s preferences", r"market probability measure $\mathbb P$.", conf=0.9,
      statement_short="Maximize $\\mathbb E_{\\mathbb P}[-\\exp(-V^\\pi_n)]$ over semistatic strategies $\\pi\\in\\mathcal A$ with delayed information.")
env("EP2", "F3", "equation", "Utility maximization objective (1.2)")
prose("RP3", "remark", "Unit risk aversion without loss of generality", "Clearly, \nfor any portfolio strategy", "to be equal $1$.", conf=0.8)
env("TP1", "F4", "theorem", "Explicit solution of delayed semistatic exponential utility maximization (discrete time)", main=True,
    statement_short="With i.i.d. Gaussian increments and delay $D$, the optimal strategy is Merton fraction plus a recursively computed linear filter of past increments, with a quadratic static payoff; the value is explicit.",
    tags=["utility_maximization", "semistatic_hedging", "explicit_solution", "existence", "uniqueness"])
for i, f in enumerate(["F5", "F6", "F7", "F8"], start=3):
    env(f"EP{i}", f, "equation", ["Constant a (eq:a_sol)", "Recursion for b_i (1.4)", "Optimal strategy (1.5)", "Optimal value (1.6)"][i - 3])
prose("RP4", "remark", "Financial interpretation of the optimal strategy", "Let us briefly collect some financial-economic observations", "quadratic payoff function.", conf=0.8)
prose("ClP2", "claim", "No mispricing gives the Merton strategy", r"Observe that for the case $\sigma=\hat\sigma$ we have $a=0$", r"\left(-\frac{n\mu^2}{2\sigma^2}\right).$", conf=0.75)
prose("ClP3", "claim", "Value without delay (D=0)", "First, for $D=0$ (i.e. no delay) we have", r"$g(z):=z-\log z-1$, $z>0$.", conf=0.75,
      statement_short="For $D=0$, $a=\\sigma^2/\\hat\\sigma^2-1$ and the value is the Merton value times $\\exp(-n g(\\hat\\sigma^2/\\sigma^2)/2)$ with $g(z)=z-\\log z-1$.")
prose("RP5", "remark", "Properties of g(z)=z-log z-1", r"The function $g\geq 0$ is convex", "the references therein.", conf=0.8)
prose("ClP4", "claim", "a is the largest root of the quadratic (equat)", r"For general $D$ and $\sigma\neq\hat\sigma$ we will see", r"quadratic equation (\ref{equat}).", conf=0.7)
prose("PP2", "proof", "Sign of a via Vieta's formulas", r"If $\hat\sigma>\sigma$", r"the large root $a$ is positive.", after=POS["ClP4"][0], conf=0.7,
      statement_short="Vieta's formulas for (equat): both roots negative when $\\hat\\sigma>\\sigma$, product negative (so largest root positive) when $\\sigma>\\hat\\sigma$.",
      proof_strategy=["case_analysis", "algebraic_manipulation"])
prose("ClP5", "claim", "Sign of a matches sign of sigma - hat sigma", r"Next, fix $n,D,\mu,\sigma$.", r"$a>0\Leftrightarrow\sigma>\hat\sigma$.", conf=0.75)
prose("ClP6", "claim", "Monotonicity of the value in hat sigma", "Hence, \nthe value function", r"decreasing for $\hat\sigma<\sigma$.", after=POS["ClP5"][0], conf=0.75,
      assumptions=[], conclusions=[])
prose("PP3", "proof", "Proof of monotonicity in hat sigma", r"Indeed, let $\sigma<\hat\sigma_1<\hat\sigma_2$", r"$\hat\sigma=\hat\sigma_1$ will be larger.", conf=0.75,
      statement_short="Keep the optimal portfolio for one $\\hat\\sigma$ and use the sign of $a$: the same portfolio does better at the other $\\hat\\sigma$.", proof_strategy=["direct"])
prose("ClP7", "claim", "Asymptotic arbitrage for extreme hat sigma", "Finally, we argue that there is an asymptotic arbitrage", "very large or very small.", conf=0.75)
s = find(r"To this end, instead of applying Theorem").start()
add("PP4", "proof", "Static-hedging proof of asymptotic arbitrage", s, F["F10"]["outer_end"], conf=0.75,
    statement_short="Static hedge only: take $\\gamma\\equiv 0$ and $f=\\pm(S_n-S_0)^2/\\hat\\sigma$, giving value tending to 0 as $\\hat\\sigma\\to 0$ or $\\infty$.",
    proof_strategy=["construction"])
env("EP7", "F9", "equation", "Limit as hat sigma -> 0 (static1)")
env("EP8", "F10", "equation", "Limit as hat sigma -> infinity (static2)")

# ---------------------------------------------------------------- Section 3: proof of Theorem 2.2
s = find(r"Denote by $\mathcal Q$ the set").start()
add("DP9", "definition", "Set Q of delayed martingale measures consistent with prices", s, find(r"is equal to $\hat\nu$).", s).end(), conf=0.9,
    definiendum="$\\mathcal Q$",
    statement_short="$\\mathcal Q$: finite-entropy equivalent measures under which $S$ is a martingale w.r.t. the delayed filtration and $S_n\\sim\\hat\\nu$.")
env("EP9", "F11", "equation", "Delayed martingale condition (2.0)")
env("LP1", "F12", "lemma", "Verification lemma for semistatic exponential utility",
    statement_short="If $V^{\\tilde\\pi}_n+\\log(d\\tilde Q/dP)$ is constant $C$ for some $\\tilde Q\\in\\mathcal Q$, then $\\tilde\\pi$ is the unique optimizer with value $-e^{-C}$.",
    tags=["duality", "verification", "uniqueness"])
env("EP10", "F13", "equation", "Verification identity (2.1)")
env("PP5", "F14", "proof", "Proof of the verification lemma",
    statement_short="Duality: Step I shows $\\mathbb E_Q[V^\\pi_n]=0$ for all $Q\\in\\mathcal Q$; Step II applies the Legendre-Fenchel inequality and optimizes over a scalar $z$.",
    proof_strategy=["dual_argument", "direct"])
for i, f in enumerate(["F15", "F16", "F17", "F18", "F19"], start=11):
    env(f"EP{i}", f, "equation", ["Zero expected value under Q (2.2)", "Static payoff price (2.3)", "Entropy bound on negative part (2.4)", "Duality equality (2.5)", "Weak duality inequality (2.6)"][i - 11])
prose("DP10", "definition", "Banded positive definite matrices S_D", r"Let ${\mathcal{S}}_{{D}}$ be the set", r"upper bandwidth equal to ${D}$.", conf=0.9, definiendum="${\\mathcal{S}}_{{D}}$",
      genus="$n \\times n$ positive definite matrices", differentia=["$Q_{ij}=0$ for $|i-j|>{D}$"])
prose("DP11", "definition", "Symmetric Toeplitz matrices T_n", r"Let ${T}_n$ be the set of all", "symmetric Toeplitz matrices.", conf=0.9, definiendum="${T}_n$")
prose("DP12", "definition", "Toeplitz matrix", "Recall that a Toeplitz matrix is a matrix", "is constant.", conf=0.9, origin="external", origin_citation="standard (uncited)",
      definiendum="Toeplitz matrix", genus="matrix", differentia=["each descending diagonal from left to right is constant"])
prose("DP13", "definition", "Row and column index vectors", r"Let $C$ be a $n \times n$ real matrix", r"$1 \leq j_1 < j_2 < .. < j_k \leq n$.", conf=0.85,
      definiendum=["$C$", "$I$", "$J$"])
prose("DP14", "definition", "Minor C_J^I", r"We denote by $C_J^I$ the minor", r"$i=i_1,..i_k ; j=j_1,..j_k$.", conf=0.9, definiendum="$C_J^I$")
prose("DP15", "definition", "Index vector [k:l]", r"For any two natural numbers $l \geq k$", r"by $[k:l]$.", conf=0.9, definiendum="$[k:l]$")
env("LP2", "F21", "lemma", "Toeplitz matrix A has banded inverse and explicit determinant",
    statement_short="The symmetric Toeplitz matrix $A_{ij}=b_{|i-j|}$ (with $b_0=a+1$) has $D$-banded positive definite inverse and an explicit determinant.",
    tags=["banded_matrix", "toeplitz_matrix", "determinant"])
env("EP11", "F22", "equation", "Determinant of A (2.8-)")
env("PP6", "F23", "proof", "Proof of banded inverse and determinant of A",
    statement_short="Show $a>-1/(D+1)$ by the intermediate value theorem; show all sub-$(D+1)$-minors vanish via the recursion; then apply Barrett-Feinsilver theorems on banded inverses.",
    proof_strategy=["direct", "algebraic_manipulation"])
env("EP12", "F24", "equation", "Quadratic equation for a (equat)")
env("EP13", "F25", "equation", "Two-sided recursion for b_i (2.8)")
env("LP3", "F26", "lemma", "Sum of entries of A^{-1}",
    statement_short="The entries of $A^{-1}$ sum to $n\\hat\\sigma^2/\\sigma^2$.", tags=["toeplitz_matrix", "identity"])
env("PP7", "F27", "proof", "Proof of the sum of entries of A^{-1}",
    statement_short="Find the vector $v$ solving the Toeplitz system (2.15) by cases, then apply the Gohberg-Semencul-type inversion formula of Rodman-Shalom and sum the entries.",
    proof_strategy=["direct", "case_analysis", "algebraic_manipulation"])
for i, f in enumerate(["F28", "F29", "F32"], start=14):
    env(f"EP{i}", f, "equation", ["Vector v (2.14+)", "Toeplitz system for v (2.15)", "Inverse formula for A (2.16)"][i - 14])
env("PP8", "F34", "proof", "Proof of Theorem 2.2",
    statement_short="Verification: build $\\hat Q$ with density $\\exp(\\hat C-V^{\\pi^*}_n)$, show $X\\sim\\mathcal N(0,\\sigma^2A^{-1})$ under it, and use Lemmas 3.2-3.3 to get $\\hat Q\\in\\mathcal Q$.",
    proof_strategy=["dual_argument", "construction"])
env("EP17", "F35", "equation", "Constant hat C (2.8+)")
env("EP18", "F36", "equation", "Density of hat Q (2.9)")

# ---------------------------------------------------------------- Section 4: Bachelier model
prose("DP16", "definition", "Brownian probability space", r"In this section we assume that $(\Omega, \mathcal{F}, \mathbb P)$ is", "time horizon $T=1$.", conf=0.85,
      definiendum="$W=(W_t)_{t \\in [0,1]}$")
prose("DP17", "definition", "Bachelier model", "We consider a simple financial market with a riskless savings account", "constant volatility.", conf=0.85,
      origin="external", origin_citation="standard (uncited)", definiendum=["Bachelier price dynamics", "$P$", "$\\theta$", "$\\varsigma$"])
prose("AssumP6", "assumption", "Constant information delay H", "We focus on an investor who is informed", "with a delay $H>0$.", conf=0.85)
prose("DP18", "definition", "Equidistant trading grid", r"Fix $n\in\mathbb N$ and consider an investor", r"\frac{2}{n},...,1\right\}$.", conf=0.8)
prose("DP19", "definition", "Discrete delayed filtration G^n and delay D_n", r"The investor's flow of information is given by the filtration", r"=\lceil H n\rceil$.", conf=0.85,
      definiendum=["$\\mathcal G^n_k$", "$D_n$"])
prose("DP20", "definition", "Static vanilla options priced by hat V", r"In addition, the investor can take a static position in $P_1$", r"for the amount $\int f d\hat{\mathcal{V}}$.", conf=0.85,
      definiendum="$\\hat{\\mathcal{V}}$")
prose("AssumP7", "assumption", "Normal pricing measure N(P_0, hat varsigma^2)", "We assume \n that $\\hat{\\mathcal{V}}= \\mathcal N(P_0, \\hat\\varsigma^2)$", r"constant $\hat\varsigma>0$.", conf=0.85)
prose("RP6", "remark", "No-arbitrage in the Bachelier setting", r"As in Section \ref{sec:2}, in order to avoid arbitrage", "initial stock price $P_0$.", conf=0.8)
s = find(r"A trading strategy is a pair $\pi=(\gamma,f)$ where $\gamma=(\gamma_t)_{t \in [0,1]}$ is a piecewise").start()
add("DP21", "definition", "Trading strategy on the grid", s, find(r"for all $k=0,1,...,n-1$.", s).end(), conf=0.9, definiendum="trading strategy (grid)")
env("EP19", "F37", "equation", "Piecewise constant strategy (4.0-)")
prose("DP22", "definition", "Set A^n of grid strategies", r"Denote by $\mathcal A^n$ the set of all trading strategies.", None, conf=0.9, definiendum="$\\mathcal A^n$")
nodes[-1]["statement"] = r"Denote by $\mathcal A^n$ the set of all trading strategies."
prose("DP23", "definition", "Terminal portfolio value V_1 (grid)", r"For $\pi=(\gamma,f)\in\mathcal A^n$ the corresponding portfolio value", "-\\int fd\\hat{\\mathcal{V}}.\n$$", conf=0.9, definiendum="$V^{\\pi}_1$")
prose("RP7", "remark", "Stochastic integral of a piecewise constant strategy", r"Observe that for $\gamma$ of the form (\ref{4.0-})", r"\left(P_{\frac{i}{n}}-P_{\frac{i-1}{n}}\right).$", conf=0.75)
s = find("Consider the exponential utility maximization problem").start()
add("ProbP2", "problem", "Exponential utility maximization on the grid U_n", s, F["F38"]["outer_end"], conf=0.9, definiendum="$U_n$")
env("EP20", "F38", "equation", "Value U_n (4.1)")
s = find(r"Set \begin{equation}\label{eq:alpha_def}").start()
add("DP24", "definition", "Constant alpha", s, F["F39"]["outer_end"], conf=0.85, definiendum="$\\alpha$")
env("EP21", "F39", "equation", "Definition of alpha (eq:alpha_def)")
s = find(r"Define the function $\kappa:[0,1]\rightarrow\mathbb R$ by").start()
add("DP25", "definition", "Weight function kappa", s, F["F41"]["outer_end"], conf=0.9, definiendum=["$\\kappa$", "$c_k$"],
    statement_short="$\\kappa$ equals $\\alpha/(1-\\alpha H)$ on $[0,H)$ and on each $[kH,(k+1)H)$ is an exponential times a polynomial with recursively defined coefficients $c_k$.")
env("EP22", "F40", "equation", "Explicit kappa (eq:b_sol_recursive)")
env("EP23", "F41", "equation", "Recurrence for c_k (eq:c_coefficients_recursive)")
prose("ClP8", "claim", "kappa is well defined", r"From (\ref{eq:alpha_def}) we have $\alpha<\frac{1}{H}$", r"$\kappa$ is well defined.", conf=0.75)
s = find(r"The fact that $c_1=-\alpha$ gives").start()
add("PP9", "proof", "Derivation of the delay integral equation for kappa", s, find(r"&=-\alpha\kappa_{t-H}. \end{align*}", s).end(), conf=0.7,
    statement_short="Differentiate the explicit formula with the product rule on each interval $(kH,(k+1)H)$ to get $\\kappa'-\\alpha\\kappa=-\\alpha\\kappa_{t-H}$, plus continuity.",
    proof_strategy=["direct", "algebraic_manipulation"])
s = find(r"We conclude that $\kappa$ satisfies the following (integral)").start()
add("ClP9", "claim", "Delay integral equation for kappa", s, F["F43"]["outer_end"], conf=0.8,
    conclusions=[], assumptions=[])
env("EP24", "F43", "equation", "Integral equation for kappa (prop)")
prose("RP8", "remark", "How kappa was obtained", r"In fact our definition of $\kappa$", r"and the property (\ref{prop}).", conf=0.75)
env("TP2", "F44", "theorem", "Scaling limit of delayed semistatic hedging in the Bachelier model", main=True,
    statement_short="As the trading grid refines, the value $U_n$ converges to an explicit limit, the static payoff to a quadratic, and the strategy uniformly a.s. to a Volterra Gaussian process $\\Gamma$.",
    tags=["scaling_limit", "utility_maximization", "Bachelier_model", "Volterra_process"])
for i, f in enumerate(["F45", "F46", "F47", "F48"], start=25):
    env(f"EP{i}", f, "equation", ["Limit value (4.0)", "Limit static payoff (4.2)", "Uniform strategy convergence (4.3)", "Volterra Gaussian process Gamma (vol)"][i - 25])
prose("RP9", "remark", "Behaviour of kappa_0 (Figure 1)", "The initial investment weight in the static option", r"decreases monotonically with $H$.", conf=0.65, rigor="numerical")
prose("DP26", "definition", "Continuous delayed filtration G_t", r"Let $\{\mathcal G_t\}_{t=0}^1$ be the augmented filtration", r"by the process $\{P_{(t-H)\vee 0}\}_{t=0}^1$.", conf=0.85, definiendum="$\\mathcal G_t$")
prose("DP27", "definition", "Continuous-time trading strategy", "A trading strategy is a \npair", r"as in Section \ref{section4.1}).", after=POS["DP26"][1], conf=0.9, definiendum="trading strategy (continuous time)")
s = find(r"For $\pi=(\gamma,f)$ the corresponding portfolio value").start()
add("DP28", "definition", "Terminal portfolio value V_1 (continuous time)", s, find(r"is the It\^{o} integral.", s).end(), conf=0.9, definiendum="$V^{\\pi}_1$")
env("EP29", "F49", "equation", "Continuous portfolio value (9.1)")
prose("RP10", "remark", "No admissibility condition needed", "Let us emphasize that we do not require", "strictly larger than zero).", conf=0.8)
prose("DP29", "definition", "Set of continuous-time strategies frak A", r"Denote by $\mathfrak A$ the set of all trading strategies.", None, conf=0.9, definiendum="$\\mathfrak A$")
nodes[-1]["statement"] = r"Denote by $\mathfrak A$ the set of all trading strategies."
env("RP11", "F50", "remark", "Equivalence of trading strategies (continuous time)",
    statement_short="Strategies with a.s. equal terminal values differ by a constant position and a linear payoff; shown backwards over intervals of length $1/n<H$.")
prose("DP30", "definition", "Equivalent continuous-time strategies", r"Similarly to Section \ref{sec:2}", "with slope equal to $c$.", after=POS["RP11"][0], conf=0.85,
      definiendum="equivalent trading strategies (continuous time)")
prose("ClP10", "claim", "Continuous-time strategies equivalent iff equal terminal value", r"Clearly if $\pi=(\gamma,f)$", "Let us argue that the opposite direction also holds.", after=POS["RP11"][0], conf=0.75)
prose("PP10", "proof", "Proof that equal values imply equivalence (continuous time)", r"Indeed, let", "as required.", after=POS["ClP10"][1], conf=0.75,
      statement_short="On the last interval of length $1/n<H$ the future Brownian increment is independent of the strategy, forcing a linear payoff and a constant position; iterate backwards.",
      proof_strategy=["direct", "induction"])
env("EP30", "F51", "equation", "Terminal identity (100)")
env("TP3", "F52", "theorem", "Solution of the continuous-time delayed semistatic hedging problem", main=True,
    statement_short="With delay $H>0$ in continuous time, the limit strategy $(\\Gamma,F)$ of Theorem 4.1 is the unique optimizer and the value equals the scaling limit.",
    tags=["utility_maximization", "Bachelier_model", "uniqueness", "existence"])
env("PP11", "F54", "proof", "Proof of Theorem 4.3",
    statement_short="Uniqueness from strict concavity and Remark 4.2; lower bound from Theorem 4.1 and Fatou's lemma; the upper bound (9.2) is deferred to Section 5.2.",
    proof_strategy=["direct", "dual_argument"])
env("ClP11", "F55", "claim", "Upper bound (9.2) for the continuous-time value", conf=0.9, conclusions=[F["F55"]["statement"]])
prose("RP12", "remark", "Sign of the investment weights (Figure 2, top)", r"For $\frac{\hat \varsigma^2}{\varsigma^2} < 1$, it holds that", r"are positive.\\", conf=0.65, rigor="numerical")
nodes[-1]["statement"] = TRAIL.sub("", nodes[-1]["statement"])
prose("RP13", "remark", "Numerical convergence of n b_i to kappa (Figure 2, bottom)", "As $n$ increases, the discrete values approach the continuous limit", r"for $n=1000$.", conf=0.65, rigor="numerical")
prose("RP14", "remark", "Properties of the limit value U (Figure 3)", "We observe the following properties:", r"then $U\rightarrow 0$.", conf=0.65, rigor="semi_formal",
      statement_short="Limit value: $U=-1$ when $\\varsigma=\\hat\\varsigma$; $U\\to0$ (arbitrage) as $H\\downarrow0$ under mispricing; monotone in $\\hat\\varsigma$ with $U\\to 0$ at the extremes.")
env("RP15", "F56", "remark", "Vanishing delay and the Merton line",
    statement_short="If $\\hat\\varsigma=\\varsigma$ the Merton strategy is optimal for every $H$; otherwise the value tends to 0 as $H\\downarrow 0$ (asymptotic arbitrage) and the strategy blows up.")

# ---------------------------------------------------------------- Section 5
env("LP4", "F57", "lemma", "Discrete Gronwall lemma", tags=["bound", "recursion"])
env("EP31", "F58", "equation", "Recursive inequality (5.rec)")
env("PP12", "F59", "proof", "Proof of the discrete Gronwall lemma", statement_short="Induction on $j$.", proof_strategy=["induction"])
prose("DP31", "definition", "O(1/n^C) notation", r"For a constant $C>0$ we use the notation", r"\alpha_n n^C<\infty$.", conf=0.9, definiendum="$O\\left(1/n^C\\right)$")
env("LP5", "F61", "lemma", "L^2 convergence of scaled coefficients n b_i to kappa",
    statement_short="The piecewise constant function $b^n_t=n b_{\\lfloor nt\\rfloor+1}$ built from the discrete coefficients converges to $\\kappa$ in $L^2[0,1]$ at rate $O(1/n)$.",
    tags=["scaling_limit", "convergence_rate"])
env("PP13", "F63", "proof", "Proof of the L^2 convergence of b^n to kappa",
    statement_short="Reduce to a sup bound on each delay block; compare the discrete recursion for $b^n$ with the integral equation for $\\kappa$ (each with $O(1/n^2)$ error). Induct over blocks of length $D_n$ using the discrete Gronwall lemma.",
    proof_strategy=["induction", "direct"])
for i, f in enumerate(["F65", "F66", "F67", "F69", "F71"], start=32):
    env(f"EP{i}", f, "equation", ["Blockwise error bound (5.10)", "Asymptotics of a_n (4.4)", "Recursion for b^n (5.11)", "Approximate recursion for kappa (5.12)", "Gronwall estimate (5.14)"][i - 32])
env("PP14", "F72", "proof", "Proof of Theorem 4.1",
    statement_short="Apply Theorem 2.2 on the grid with scaled parameters and take limits using (4.4); for (4.3), Borel-Cantelli with Markov's inequality on sixth moments of Gaussian errors controlled by Lemma 5.2.",
    proof_strategy=["direct", "probabilistic"])
prose("DP32", "definition", "Brownian filtration F_t", r"Let $\{\mathcal F_t\}_{t=0}^1$, $t\in [0,1]$ be the augmented", r"by $\{W_t\}_{t=0}^1$.", conf=0.85, definiendum="$\\mathcal F_t$")
env("LP6", "F75", "lemma", "Zero expectation of delayed stochastic integrals",
    statement_short="A stochastic integral with an $\\epsilon$-delayed integrand whose negative part is integrable has zero mean (no doubling strategies under delay).",
    tags=["stochastic_integral", "martingale", "no_arbitrage"])
env("PP15", "F76", "proof", "Proof by backward induction of zero expectation",
    statement_short="Backward induction over a grid of mesh $<\\epsilon$: on each interval the integrand is known in advance, so the conditional law of the increment is centered normal.",
    proof_strategy=["induction"])
env("EP37", "F77", "equation", "Martingale property on the grid (6.2)")
env("EP38", "F78", "equation", "Zero conditional increment (past)")
env("RP16", "F79", "remark", "Lemma fails without delay (doubling strategies)")
s = find(r"It is well known (see \cite{H:68}) that for any").start()
add("TP4", "theorem", "Hitsuda representation of equivalent Gaussian measures", s, F["F80"]["outer_end"], conf=0.85, origin="external", origin_citation="Hitsuda 1968",
    statement_short="Every square-integrable Volterra kernel $l$ gives an equivalent measure $\\mathbb Q(l)$ under which $W$ plus a Volterra drift is a Brownian motion.")
env("EP39", "F80", "equation", "Hitsuda representation (gir)")
s = find(r"From the Girsanov theorem").start()
add("ClP12", "claim", "Density of Q(l)", s, find(r"dW^{\mathbb Q(l)}_s\right)^2 dt\right). $$", s).end(), conf=0.7)
s = find(r"Hence, from the It\^{o} Isometry and the Fubini theorem").start()
add("ClP13", "claim", "Relative entropy of Q(l)", s, F["F81"]["outer_end"], conf=0.75)
env("EP40", "F81", "equation", "Relative entropy formula (2+.entropy)")
s = find(r"For any $\epsilon>0$ denote by $\Gamma_{\epsilon}$").start()
add("DP33", "definition", "Kernel class Gamma_epsilon", s, F["F82"]["outer_end"], conf=0.9, definiendum="$\\Gamma_{\\epsilon}$",
    statement_short="$\\Gamma_\\epsilon$: bounded deterministic Volterra kernels vanishing for $t>s+H-\\epsilon$ whose induced terminal variance is $\\hat\\varsigma^2$.")
env("EP41", "F82", "equation", "Variance constraint (variance)")
env("PP16", "F83", "proof", "Proof of the upper bound (9.2)",
    statement_short="Duality with Gaussian measures: reduce to $P=W$, show $\\mathbb E_{Q(l)}[V^\\pi_1]=0$ for $l\\in\\Gamma_\\epsilon$ via Lemma 5.3, then evaluate the entropy bound for an explicit kernel $l^\\epsilon$.",
    proof_strategy=["dual_argument", "construction"])
for i, f in enumerate(["F84", "F85", "F86", "F87", "F88"], start=42):
    env(f"EP{i}", f, "equation", ["Static payoff price under Q (6+.3)", "Weak duality (6.4)", "Identities for hat a (comp)", "Entropy upper bound (6.5)", "Entropy integral computation (6.6)"][i - 42])
s = find(r"The first $5$ coefficients $c_k$").start()
add("ClP14", "claim", "First five coefficients c_k", s, find(r"\end{align*}", s).end(), conf=0.7, rigor="numerical")

# ---------------------------------------------------------------- steps
steps("PP1", [(r"Indeed, let", "introduce_variable", "Compare two strategies", "Equal terminal values make a payoff difference measurable w.r.t. the past"),
              ("Since the support of $S_n$", "conclude", "Full support forces linearity", "Full support of $S_n$ forces $f-\\tilde f$ to be linear")])
steps("PP2", [(r"If $\hat\sigma>\sigma$", "case_split", "Case hat sigma > sigma", "Vieta: both roots negative, so $a<0$"),
              (r"For the case $\sigma>\hat\sigma$", "case_split", "Case sigma > hat sigma", "Vieta: negative product, so largest root positive")])
steps("PP5", [("The proof will be done in two steps.", "setup", "Plan", "Two-step plan"),
              (r"\textbf{Step I:}", "setup", "Step I: zero mean under Q", "Show $\\mathbb E_Q[V^\\pi_n]=0$ for every $Q\\in\\mathcal Q$", [
                  (r"\textbf{Step I:}", "setup", "State Step I", "Claim of Step I"),
                  (r"Indeed, let $\pi\in\mathcal A$ be as above", "substitute", "Static part has price as mean", "Under $Q$, $f(S_n)$ is integrable with mean $\\int f d\\hat\\nu$"),
                  ("Next, from the classical Legendre-Fenchel", "bound_estimate", "Entropy bound", "Legendre-Fenchel bounds the negative part of $V$ under $Q$"),
                  (r"From (\ref{eq:value}) and (\ref{2.3})--(\ref{2.4}) we get", "bound_estimate", "Integrable negative part", "Negative part of the stochastic sum is $Q$-integrable"),
                  ("Thus, using similar arguments as in the proof of Lemma 2.1", "apply_lemma", "Zero mean of the gains", "As in Lemma 2.1 of [BD:2021], the gains process has zero $Q$-mean"),
                  (r"This together with (\ref{2.3}) yields", "conclude", "Conclude Step I", "Combine to get (2.2)")]),
              (r"\textbf{Step II:}", "conclude", "Step II: duality", "Weak duality inequality and equality at the triplet", [
                  (r"\textbf{Step II:}", "setup", "Recall prior argument", "Follows Step II of an earlier proof"),
                  (r"From (\ref{2.1})--(\ref{2.2}) for", "substitute", "Equality at the triplet", "At $\\tilde\\pi$ the dual value is attained"),
                  ("Next, it is well known that for a strictly concave", "setup", "Reduce to weak duality", "Uniqueness from strict concavity; remains to prove (2.6)"),
                  (r"Let us establish (\ref{2.6}).", "bound_estimate", "Legendre-Fenchel lower bound", "Lower bound by Legendre-Fenchel for every $z\\geq0$"),
                  (r"The first equality is due to \eqref{2.2}.", "other", "Justify the chain", "Justify each step of the chain"),
                  ("From simple calculus it follows that the concave function", "conclude", "Optimize over z", "Maximize over $z$ to conclude (2.6)")])])
steps("PP6", [(r"For $D=0$ the statement is trivial.", "setup", "Reduce to D>0", "Trivial for $D=0$; three-step plan"),
              (r"\textbf{Step I:}", "bound_estimate", "Step I: a > -1/(D+1)", "Show $a>-1/(D+1)$", [
                  (r"\textbf{Step I:}", "setup", "State Step I", "Goal of Step I"),
                  ("Observe that (recall that $D<n$)", "bound_estimate", "Intermediate value argument", "Limits at the endpoints give a root $z>-1/(D+1)$"),
                  ("Hence, \n the quadratic equation", "algebraic_manipulation", "Quadratic form of the equation", "The root solves the quadratic (equat)"),
                  ("Since $a$ is the largest root", "conclude", "a is the largest root", "Hence $a\\geq z>-1/(D+1)$")]),
              (r"\textbf{Step II:}", "other", "Step II: vanishing minors", "All sub-$(D+1)$-minors of $A$ vanish", [
                  (r"\textbf{Step II:}", "setup", "State Step II", "Goal: vanishing sub-$(D+1)$-minors"),
                  (r"Set $b_{-i}:=b_i=a$", "introduce_variable", "Extend the recursion", "Extend $b$ to negative indices; recursion (2.8)"),
                  (r"Let $A^J_I$ be a sub-$(D+1)$-minor.", "conclude", "Rank argument", "Rows are combinations of $D$ rows, so the minor vanishes")]),
              (r"\textbf{Step III:}", "conclude", "Step III: apply banded-matrix theorems", "Determinant and banded positive definite inverse", [
                  (r"\textbf{Step III:}", "introduce_variable", "Matrices 1^{m,alpha}", "Introduce $\\mathbf 1^{m,\\alpha}$, positive definite with determinant $1+m\\alpha$"),
                  ("Thus, in view of the second step", "apply_lemma", "Determinant via Theorem 5.1 of [BF:81]", "Determinant as ratio of principal minors"),
                  ("Moreover, from Theorem 3.1 in", "apply_lemma", "Banded inverse via Theorem 3.1 of [BF:81]", "$A^{-1}$ is $D$-banded"),
                  (r"Finally, from the fact that $a>-\frac{1}{D+1}$", "bound_estimate", "Positive principal minors", "Principal minors positive"),
                  ("Hence, by applying Theorem 5.5", "conclude", "Positive definiteness via Theorem 5.5 of [BF:81]", "$A^{-1}\\in\\mathcal S_D$")])])
steps("PP7", [(r"For $D=0$ we have $A^{-1}", "setup", "Reduce to D>0", "Trivial for $D=0$; two-step plan"),
              (r"\textbf{Step I:}", "other", "Step I: solve the Toeplitz system", "Explicit $v$ solving (2.15)", [
                  (r"\textbf{Step I:}", "introduce_variable", "Define v", "Define $v$ and state (2.15)"),
                  ("For $i = 0$:", "case_split", "Case i=0", "Check $i=0$"),
                  (r"\noindent For $1 \leq i < {D}$:", "case_split", "Case 1<=i<D", "Check $1\\le i<D$"),
                  (r"\noindent For $i\geq {D}$:", "case_split", "Case i>=D", "Check $i\\ge D$ via the recursion")]),
              (r"\textbf{Step II:}", "conclude", "Step II: sum the entries", "Inversion formula and summation", [
                  (r"\textbf{Step II:}", "apply_lemma", "Inversion formula of Rodman-Shalom", "Theorem 1 of [rodman1992inversion] gives (2.16)"),
                  ("Thus,\n \\begin{align*}", "algebraic_manipulation", "Sum the entries", "Sum the entries of $A^{-1}$"),
                  ("The first equality is due to the fact", "conclude", "Justify and conclude", "Justify the chain; use that $a$ solves (equat)")])])
steps("PP8", [(r"From Lemma \ref{lem2.2} it follows that the portfolio", "apply_lemma", "Admissibility of pi*", "$\\pi^*$ is well defined and in $\\mathcal A$"),
              ("Set\n\\begin{equation}", "introduce_variable", "Define hat C and hat Q", "Define $\\hat C$ and $\\hat Q$, satisfying (2.1)"),
              (r"Thus, in view of Lemma \ref{lem2.1} in order", "setup", "Reduce to hat Q in Q", "By Lemma 3.1 it suffices to show $\\hat Q\\in\\mathcal Q$"),
              (r"Let $X=(S_1-S_0", "algebraic_manipulation", "Quadratic form of V", "Write $V^{\\pi^*}_n$ as a quadratic form and the density as a Gaussian ratio"),
              (r"Hence, the relation $\left(X;{\mathbb P}\right)", "substitute", "Law of X under hat Q", "$X\\sim\\mathcal N(0,\\sigma^2A^{-1})$ under $\\hat Q$"),
              (r"From Lemma \ref{lem2.2} we obtain that", "apply_lemma", "Delayed martingale property", "Banded inverse gives the delayed independence, hence (2.0)"),
              (r"Finally, the property $(S_n;\hat{\mathbb Q})", "conclude", "Terminal law", "Lemma 3.3 gives $S_n\\sim\\hat\\nu$ under $\\hat Q$")])
steps("PP9", [(r"The fact that $c_1=-\alpha$ gives", "substitute", "Value at H", "$\\kappa_H=\\int_0^H\\kappa$"),
              ("The recursive definition", "other", "Continuity", "Recursion makes $\\kappa$ continuous on $[H,1]$"),
              ("From \n(\\ref{eq:b_sol_recursive}) and the product rule", "algebraic_manipulation", "Differentiate", "Delay ODE $\\kappa'-\\alpha\\kappa=-\\alpha\\kappa_{t-H}$")])
steps("PP10", [(r"Indeed, let", "introduce_variable", "Set up the difference", "Introduce $\\beta$, $h$, $n$ with $1/n<H$ and the Brownian increment $B$"),
               (r"From $V^{\pi}_1=V^{\tilde\pi}_1$ we get", "substitute", "Terminal identity", "Equal values give (100)"),
               ("Observe that\n$B$ is a Brownian motion", "other", "Independence argument", "Independence of $B$ forces $h$ linear and $\\beta$ constant on the last interval"),
               ("By repeating this argument", "conclude", "Iterate backwards", "Repeat over earlier intervals")])
steps("PP11", [("Since the utility function is strictly concave", "setup", "Uniqueness", "Uniqueness from strict concavity and Remark 4.2"),
               ("Next, recall the optimal portfolios", "apply_lemma", "Lower bound via Fatou", "Theorem 4.1 and Fatou's lemma give the lower bound"),
               ("We conclude that in order to complete the proof", "setup", "Defer the upper bound", "Remains to prove (9.2), done in Section 5.2")])
steps("PP12", [("The proof will be done by induction.", "induction_step", "Base case", "Induction on $j$; base case $j=0$"),
               ("Assume the statement holds for $j$", "induction_step", "Inductive step", "Inductive step from $j$ to $j+1$")])
steps("PP13", [("The proof will be done in three steps.", "setup", "Plan", "Three-step plan"),
               (r"\textbf{Step I:}", "setup", "Step I: reduction to a discrete claim", "Reduce to blockwise sup bounds (5.10)", [
                   (r"\textbf{Step I:}", "setup", "Lipschitz property of kappa", "$\\kappa$ constant on $[0,H)$, Lipschitz on $[H,1]$"),
                   ("Fix $n$. From the above, by applying the triangle inequality", "bound_estimate", "Triangle inequality", "Split the $L^2$ error into a grid error and an $O(1/\\sqrt n)$ term"),
                   (r"Since $\kappa$ is not necessarily continuous in $H$", "other", "Why only O(1/sqrt n)", "Discontinuity at $H$ explains the rate"),
                   ("We conclude that in order to prove the Lemma it is sufficient", "setup", "Reduce to (5.10)", "Suffices to prove (5.10)")]),
               (r"\textbf{Step II:}", "bound_estimate", "Step II: preliminary estimates", "Asymptotics of $a_n$ and matching recursions", [
                   (r"\textbf{Step II:}", "bound_estimate", "Asymptotics of a_n", "$a_n=\\frac{\\alpha}{1-\\alpha H}\\frac1n+O(1/n^2)$"),
                   (r"Next, (\ref{1.4}) yields that for any", "algebraic_manipulation", "Recursion for b^n", "Two-term recursion (5.11)"),
                   (r"From (\ref{prop}) we have that for any $k\geq D_n$", "bound_estimate", "Approximate recursion for kappa", "Integral equation gives the same recursion up to $O(1/n^2)$"),
                   (r"We conclude that for any $k\geq D_n$ such that", "conclude", "State (5.12)", "Approximate recursion (5.12)")]),
               (r"\textbf{Step III:}", "induction_step", "Step III: induction over delay blocks", "Induction on the block index $i$", [
                   (r"\textbf{Step III:}", "setup", "Induction plan", "Prove (5.10) by induction on $i$"),
                   (r"Observe that $\kappa_H=\frac{\alpha^2 H}{1-\alpha H}$ and", "induction_step", "Base block", "$\\Delta^n_1=O(1/n)$"),
                   ("Assume that the statement holds true for $i$", "induction_step", "Error sequence z", "Inductive hypothesis; define $z^{n,i}_j$"),
                   (r"From \eqref{5.11},\eqref{5.12} we obtain", "bound_estimate", "Recursive error bound", "Error obeys $z_{k+1}\\le\\phi z_k+O(1/n^2)$"),
                   (r"Thus, the sequence $\{z^{n,i}_j\}_{j=0}^{D_n-2}$", "apply_lemma", "Apply discrete Gronwall", "Lemma 5.1 gives (5.14)"),
                   ("It remains to treat the term", "conclude", "Boundary terms", "Handle the last three indices")])])
steps("PP14", [(r"Choose $n\in\mathbb N$. We apply Theorem", "apply_lemma", "Limit of the value", "Theorem 2.2 on the grid and (4.4) give (4.0)"),
               (r"Next, by combining (\ref{1.5})", "substitute", "Limit of the static payoff", "(1.5) and (4.4) give (4.2)"),
               (r"Finally, we establish (\ref{4.3}).", "setup", "Reduce to grid points", "Continuity of $\\Gamma$ (Fernique) reduces (4.3) to $\\Phi_n\\to0$ a.s."),
               ("In view of the Borel", "setup", "Borel-Cantelli and Markov", "Suffices to show $\\sum_n\\mathbb E[\\Phi_n^6]<\\infty$"),
               (r"To this end we apply Lemma \ref{lem5.2}.", "conclude", "Sixth-moment bound", "Gaussian moments and Lemma 5.2 give $\\mathbb E[\\Phi_n^6]=O(1/n^2)$")])
steps("PP15", [(r"Choose $n\in\mathbb N$ such that", "induction_step", "Backward induction for (6.2)", "Prove (6.2) by backward induction on $k$", [
                   (r"Choose $n\in\mathbb N$ such that", "setup", "Grid and claim", "Grid of mesh $<\\epsilon$; claim (6.2)"),
                   (r"For $k=n$ (\ref{6.2}) is obvious.", "induction_step", "Base case k=n", "Trivial for $k=n$"),
                   (r"Assume that (\ref{6.2}) is correct for $k$", "induction_step", "Inductive step", "Jensen and the tower property reduce to (past)"),
                   (r"Thus, in order to prove (\ref{6.2}) for $k-1$", "setup", "Reduce to (past)", "Remains to show (past)"),
                   (r"Indeed, since $\frac{1}{n}<\epsilon$", "conclude", "Conditional normality", "Integrand known in advance, so the increment is conditionally centered normal")]),
               ("Taking $k=0$", "conclude", "Take k=0", "Set $k=0$")])
steps("PP16", [("The proof will be done in three steps.", "setup", "Plan", "Three-step plan"),
               (r"\textbf{Step I:}", "setup", "Step I: reduction to P=W", "Reduce to $P_0=\\theta=0$, $\\varsigma=1$", [
                   (r"\textbf{Step I:}", "setup", "Normalize location and scale", "Affine change of variables"),
                   (r"Thus, it remains to treat the drift $\theta$.", "introduce_variable", "Remove drift by Girsanov", "Change to $\\tilde P$ under which $P$ is Brownian"),
                   ("This property together with the simple equality", "conclude", "Drift reduction", "Value identity transfers the bound")]),
               (r"\textbf{Step II:}", "other", "Step II: zero mean under Q(l)", "$\\mathbb E_{Q(l)}[V^\\pi_1]=0$ for $l\\in\\Gamma_\\epsilon$", [
                   (r"\textbf{Step II:}", "setup", "State Step II", "Goal of Step II"),
                   (r"Choose $l\in\Gamma_{\epsilon}$", "introduce_variable", "Fix kernel and strategy", "Fix $l$, $\\pi$, $Q=Q(l)$"),
                   ("From the Fubini theorem and (\\ref{gir}) it follows", "substitute", "Terminal law under Q", "$W_1\\sim\\hat{\\mathcal V}$ under $Q$"),
                   ("Let us show \nthat", "bound_estimate", "Integrable negative part", "Negative part of the gains is $Q$-integrable", [
                       ("Indeed, in view of the relations", "substitute", "Static payoff price", "(6+.3)"),
                       ("From the classical Legendre-Fenchel duality inequality", "bound_estimate", "Entropy bound", "Legendre-Fenchel bound on the negative part"),
                       ("This together with \n(\\ref{6+.3}) yield", "conclude", "Conclude integrability", "Combine")]),
                   ("Finally, \n$$", "apply_lemma", "Apply Lemma 5.3", "Rewrite the gains as a delayed integral against $W^Q$ and apply Lemma 5.3")]),
               (r"\textbf{Step III:}", "conclude", "Step III: optimize the dual bound", "Explicit kernel $l^\\epsilon$ attains the bound", [
                   (r"\textbf{Step III:}", "apply_lemma", "Weak duality", "As after (2.6), get (6.4)"),
                   ("Set \n$\\hat a:=", "introduce_variable", "Define hat a", "Define $\\hat a$ with identities (comp)"),
                   ("Next, for any $\\epsilon>0$ define $l^{\\epsilon}", "bound_estimate", "Explicit kernel", "Kernel $l^\\epsilon$ and entropy formula give (6.5)"),
                   ("Observe that\n\\begin{align}", "algebraic_manipulation", "Compute the integral", "Evaluate the entropy integral (6.6)"),
                   (r"Finally, by combining (\ref{6.5})-(\ref{6.6})", "conclude", "Conclude", "Combine to obtain (9.2)")])])

# ---------------------------------------------------------------- edges (non-\ref)
M = dict(mention=True)
# proves edges for prose proofs and proofs without syntactic target
E("PP1", "ClP1", "proves", 0.75, "inferred")
E("PP2", "ClP5", "proves", 0.7, "inferred")
E("PP3", "ClP6", "proves", 0.8, "named")
E("PP4", "ClP7", "proves", 0.8, "named")
E("PP8", "TP1", "proves", 0.95, "named")
E("PP9", "ClP9", "proves", 0.75, "named")
E("PP10", "ClP10", "proves", 0.75, "inferred")
E("PP14", "TP2", "proves", 0.95, "named")
E("PP16", "ClP11", "proves", 0.95, "named")
E("PP11", "TP3", "proves", 1.0, "syntax")
# resolves
E("ProbP1", "TP1", "resolves", 0.9, "inferred")
E("ProbP2", "TP2", "resolves", 0.85, "inferred")
E("ProbP2", "TP3", "resolves", 0.7, "inferred")
# mention edges stated by \ref
E("TP1", "PP4", "uses", 0.95, None, **M)
E("LP6", "RP16", "uses", 0.95, None, **M)
# --- Section 2 terms
for t in ["DP3", "DP4", "DP7", "TP1"]:
    E("DP1", t, conf=0.75, basis="term")
for t in ["DP7", "TP1", "PP8"]:
    E("AssumP2", t, conf=0.8, basis="term")
for t in ["DP3", "TP1", "DP10"]:
    E("DP2", t, conf=0.8, basis="term")
E("AssumP3", "PP6", conf=0.8, basis="named")
E("AssumP1", "DP7", conf=0.6, basis="inferred")
for t in ["DP5", "DP9"]:
    E("DP3", t, conf=0.8, basis="term")
for t in ["AssumP4", "DP5", "DP7", "RP1", "DP9"]:
    E("DP4", t, conf=0.8, basis="term")
E("AssumP4", "AssumP5", conf=0.8, basis="inferred")
E("RP1", "AssumP5", conf=0.85, basis="named")
for t in ["TP1", "LP3"]:
    E("AssumP5", t, conf=0.8, basis="term")
E("DP5", "DP6", conf=0.85, basis="term")
E("DP5", "DP8", conf=0.8, basis="term")
E("DP5", "DP21", conf=0.7, basis="term")
E("DP5", "RP4", conf=0.7, basis="term")
E("DP28", "PP11", conf=0.8, basis="term")
E("DP27", "RP15", conf=0.7, basis="term")
E("DP5", "DP27", conf=0.7, basis="term")
E("DP7", "TP1", conf=0.8, basis="term")
E("DP7", "PP5", conf=0.8, basis="term")
E("DP19", "PP13", conf=0.8, basis="term")
E("DP25", "PP9", conf=0.8, basis="term")
for t in ["DP7", "ProbP1", "LP1", "TP1", "DP9"]:
    if t != "DP9":
        E("DP6", t, conf=0.8, basis="term")
for t in ["ProbP1", "LP1", "RP3", "ClP1", "PP8"]:
    E("DP7", t, conf=0.8, basis="term")
for t in ["TP1", "LP1"]:
    E("DP8", t, conf=0.8, basis="term")
E("DP8", "ClP1", conf=0.85, basis="term")
E("TP1", "ClP2", "specializes", 0.8, "inferred")
E("TP1", "ClP3", "specializes", 0.8, "inferred")
E("ClP3", "RP5", conf=0.8, basis="term")
E("TP1", "ClP4", conf=0.8, basis="term")
E("ClP4", "PP2", conf=0.85, basis="inferred")
E("ClP5", "ClP6", conf=0.85, basis="named")
E("TP1", "PP3", conf=0.8, basis="inferred")
E("ClP5", "PP3", conf=0.8, basis="inferred")
# --- Section 3
for t in ["LP1", "PP8"]:
    E("DP9", t, conf=0.85, basis="term")
E("DP12", "DP11", conf=0.85, basis="term")
for t in ["LP2", "PP7", "PP8"]:
    E("DP10", t, conf=0.8, basis="term")
E("DP11", "LP2", conf=0.85, basis="term")
E("DP13", "DP14", conf=0.8, basis="term")
E("DP14", "PP6", conf=0.8, basis="term")
E("DP15", "PP6", conf=0.8, basis="term")
E("LP2", "LP3", conf=0.85, basis="term")
E("LP2", "PP7", conf=0.85, basis="inferred")
# --- Section 4
for t in ["DP17", "DP32", "TP4"]:
    E("DP16", t, conf=0.8, basis="term")
for t in ["DP19", "DP20", "DP23", "ProbP2", "TP2", "DP26", "DP28"]:
    E("DP17", t, conf=0.8, basis="term")
for t in ["DP19", "DP24", "DP26", "TP2", "DP33"]:
    E("AssumP6", t, conf=0.8, basis="term")
E("DP18", "DP19", conf=0.8, basis="term")
for t in ["DP21", "LP5", "PP14"]:
    E("DP19", t, conf=0.8, basis="term")
for t in ["AssumP7", "DP21", "DP23", "DP27", "DP28", "RP6"]:
    E("DP20", t, conf=0.8, basis="term")
for t in ["DP24", "TP2", "DP33"]:
    E("AssumP7", t, conf=0.8, basis="term")
E("RP1", "RP6", conf=0.8, basis="named")
E("DP21", "DP22", conf=0.85, basis="term")
for t in ["DP23", "ProbP2", "TP2"]:
    E("DP22", t, conf=0.8, basis="term")
E("DP23", "ProbP2", conf=0.8, basis="term")
E("DP23", "RP7", conf=0.8, basis="term")
for t in ["DP25", "TP2", "TP3", "RP15", "PP13", "RP12", "RP14"]:
    E("DP24", t, conf=0.8, basis="term")
for t in ["ClP8", "ClP9", "TP2", "LP5", "RP9", "RP12", "RP13", "RP8"]:
    E("DP25", t, conf=0.8, basis="term")
E("LP5", "RP13", conf=0.7, basis="inferred")
E("ProbP2", "RP14", conf=0.8, basis="term")
E("ClP6", "RP14", conf=0.8, basis="named")
E("DP26", "DP27", conf=0.85, basis="term")
E("DP27", "DP29", conf=0.85, basis="term")
for t in ["TP3", "PP16", "RP10", "ClP11", "RP11"]:
    E("DP28", t, conf=0.8, basis="term")
for t in ["TP3", "ClP11", "PP16"]:
    E("DP29", t, conf=0.8, basis="term")
E("DP27", "DP30", conf=0.8, basis="term")
E("DP30", "TP3", conf=0.8, basis="term")
E("DP30", "ClP10", conf=0.85, basis="term")
E("TP3", "RP15", conf=0.75, basis="term")
E("TP2", "PP11", conf=0.9, basis="named")
# --- Section 5
for t in ["LP5", "PP13", "PP14"]:
    E("DP31", t, conf=0.8, basis="term")
E("DP32", "LP6", conf=0.85, basis="term")
E("DP32", "PP16", conf=0.75, basis="term")
E("TP4", "ClP12", conf=0.85, basis="named")
E("TP4", "ClP13", conf=0.8, basis="term")
E("TP4", "DP33", conf=0.75, basis="term")
E("ClP12", "ClP13", conf=0.85, basis="named")
E("DP33", "PP16", conf=0.85, basis="term")
E("LP1", "PP16", conf=0.7, basis="inferred")   # "the same arguments as after (2.6)"
# --- inside proofs (pass 4)
SID = {n["name"]: n["id"] for n in nodes if n["type"] == "proof_step"}
def stp(parent, order):
    return next(n["id"] for n in nodes if n.get("parent_id") == parent and n.get("step_order") == order)
E(stp("PP6", 2), stp("PP6", 3), conf=0.9, basis="named")   # "In view of the first step"
E(stp("PP6", 3), stp("PP6", 4), conf=0.9, basis="named")   # "in view of the second step"
E(stp("PP16", 3), stp("PP16", 4), conf=0.9, basis="named") # "in view of Step II"
E(stp("PP16", 2), stp("PP16", 4), conf=0.7, basis="inferred")
E(stp("PP14", 4), stp("PP14", 5), conf=0.75, basis="inferred")
E(stp("PP14", 3), stp("PP14", 4), conf=0.75, basis="inferred")
E(stp("PP11", 2), stp("PP11", 3), conf=0.7, basis="inferred")
E(stp("PP13", 2), stp("PP13", 4), conf=0.75, basis="inferred")
E(stp("PP13", 3), stp("PP13", 4), conf=0.8, basis="inferred")

# assumptions / conclusions of results
def AC(nid, ass, con, **kw):
    n = next(x for x in nodes if x["id"] == nid)
    n["assumptions"] = [sub(nid, *a) for a in ass]
    n["conclusions"] = [sub(nid, *c) for c in con]
    n.update(kw)
AC("TP1", [(r"Fix $n,D,\mu,\sigma,\hat\sigma$", r"Fix $n,D,\mu,\sigma,\hat\sigma$")],
   [(r"$a>-\frac{1}{D+1}$ and so", "well defined"), ("The maximizer", r"\end{equation}"), ("The corresponding value is given by", None)])
AC("LP1", [("a triplet", r"\end{equation}")], [(r"$\tilde\pi\in\mathcal A$ is the unique", None)])
AC("LP2", [(r"Let $\{b_i\}_{i=1}^{\infty}$ be the sequence", r"(\ref{1.4})"), ("Set $b_0=a+1$", r"$A_{ij}=b_{|i-j|}$")],
   [(r"$A^{-1}\in {\mathcal{S}}_{{D}}$", r"$A^{-1}\in {\mathcal{S}}_{{D}}$"), ("the determinant of $A$", None)])
n_ = next(x for x in nodes if x["id"] == "LP3")
n_["assumptions"] = [sub("LP2", "define the matrix", r"$A_{ij}=b_{|i-j|}$")]
n_["conclusions"] = [sub("LP3", r"$\sum_{i,j=1}^n", None)]
AC("TP2", [("for any $n\\in\\mathbb N$ let", r"for the optimization problem (\ref{4.1})")],
   [(r"As $n\rightarrow\infty$ we", r"\end{align}"), (r"\lim_{n\rightarrow\infty} f^{*,n}", r"\end{equation}"), ("we have the uniform convergence", None)])
AC("TP3", [(r"Let $\pi_{*}:=(\Gamma,F)$", "right-hand side of (\\ref{4.2})")],
   [(r"$\pi_{*}$ is the unique", r"\pi\in\mathfrak A. $"), ("Moreover,", None)])
AC("LP4", [("a positive real sequence", r"\end{equation}"), (r"for some constants $\phi>1$ and $\psi>0$", r"for some constants $\phi>1$ and $\psi>0$")],
   [(r"$$z_j\leq", None)])
AC("LP5", [(r"For any $n\in\mathbb N$ introduce", r"$\hat\sigma=\frac{\hat\varsigma}{\sqrt n}$")], [(r"$$\int_{0}^1 |b^n_t", None)])
AC("LP6", [(r"$\epsilon>0$ and $\gamma=", r"<\infty$ a.s."), ("the expectation of the negative part", r"\right)^{-}\right]<\infty$")],
   [(r"$\mathbb E_{\mathbb P}\left[\int_{0}^1 \gamma_t dW_t\right]=0.$", None)])
AC("TP4", [("for any \ndeterministic and measurable function", r"$L^2([0,1]^2)$")], [("there exists a probability measure", None)])
AC("ClP2", [(r"for the case $\sigma=\hat\sigma$", r"for the case $\sigma=\hat\sigma$")], [(r"we have $a=0$", None)])
AC("ClP3", [(r"for $D=0$", r"for $D=0$")], [("we have", None)])
for n_ in nodes:
    if n_["type"] in ("claim",) and not n_.get("conclusions"):
        n_["assumptions"] = []
        n_["conclusions"] = [n_["statement"]]
n_ = next(x for x in nodes if x["id"] == "ClP1")
n_["equivalent_conditions"] = [sub("RP2", r"$\pi=(\gamma,f)$ and $\tilde\pi=(\tilde\gamma,\tilde f)$ are equivalent", r"$\pi=(\gamma,f)$ and $\tilde\pi=(\tilde\gamma,\tilde f)$ are equivalent"), sub("ClP1", r"$V^{\pi}_n=V^{\tilde\pi}_n$", r"$V^{\pi}_n=V^{\tilde\pi}_n$")]

# equation ids: renumber in source order (they were typed by hand in groups)
eqs = sorted([n for n in nodes if n["type"] == "equation"], key=lambda n: n["_pos"])
for i, n in enumerate(eqs, start=1):
    n["id"] = f"EP{i}"
for n in nodes:
    n.pop("_pos", None)
import collections
dup = [k for k, v in collections.Counter(n["id"] for n in nodes).items() if v > 1]
assert not dup, dup
VOL = next(n["id"] for n in eqs if n["name"].startswith("Volterra"))
rigor_n = sum(1 for n in nodes if n.get("rigor"))
graph = {"metadata": {
    "title": "Explicit Computations for Delayed Semistatic Hedging",
    "authors": ["Yan Dolinsky", "Or Zuk"], "arxiv_id": "2308.10550", "year": 2023,
    "annotator": "agent-extraction", "model": "claude-opus-5-5", "effort": "default",
    "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3", "extraction_date": "2026-11-05",
    "rigor_nonformal_count": rigor_n,
    "paper_style": ["theorem_proof"],
    "extraction_notes": [
        {"category": "type_uncertain", "nodes": ["ClP11"],
         "note": "The numbered display (9.2) is retyped from equation to claim: the paper names it 'the upper bound (9.2)' and proves it in its own section (5.2), so PP16 needs a result to prove."},
        {"category": "type_uncertain", "nodes": ["RP2", "DP8", "ClP1", "PP1", "RP11", "DP30", "ClP10", "PP10"],
         "note": "Remarks 2.1 and 4.2 each define equivalence of strategies and prove an iff; kept as remarks containing a definition, a claim and its proof."},
        {"category": "unexpected_construct", "nodes": ["RP9", "RP12", "RP13", "RP14"],
         "note": "Figure captions carry results (sign/monotonicity of weights, properties I-III of the limit value); extracted as remarks, numerical or semi_formal."},
        {"category": "source_problem", "nodes": ["ClP11", "PP16"],
         "note": "Sign typo: (6.5) reads -exp(+1/2 int ...); duality gives -exp(-entropy), and only with the minus sign does (6.6) yield (9.2) (checked numerically)."},
        {"category": "source_problem", "nodes": ["RP15", "TP2"],
         "note": "Remark 4.4 says alpha H -> 1 as H -> 0, but (eq:alpha_def) gives alpha H -> 1 - hat varsigma/varsigma (as the Figure 3 caption says); it also gives Merton line theta/(2 varsigma^2), while (vol) gives theta/varsigma^2."},
        {"category": "source_problem", "nodes": [VOL, "PP14"],
         "note": "(vol) has prefactor 1/(2 varsigma^2) on the integral, but the proof of Theorem 4.1 derives gamma^{*,n} with 1/varsigma^2, consistent with (1.5); the 1/2 in (vol) looks like a typo."},
        {"category": "source_problem", "nodes": ["PP7", "PP6"],
         "note": "Proof of Lemma 3.3 ends '=n sigma^2' (should be n hat-sigma^2/sigma^2) and has '(D-2n-D-1)v_1' for D(2n-D-1)v_1; Lemma 3.2 Step II has 'i_i' for i_1. The lemmas themselves check numerically."},
        {"category": "not_extracted", "nodes": [],
         "note": "Introduction overview, the R/Maple repository description in the appendix, and the proof outline after Theorem 4.1 are meta-text; no nodes."},
    ],
    "extraction_comment": "In the proof of (9.2), l^epsilon has support length (H-epsilon) wedge (1-s) but denominator 1+hat a(H wedge (1-s)), so it seems not to satisfy the variance constraint defining Gamma_epsilon exactly for epsilon>0; the limit epsilon -> 0 is only sketched."},
    "nodes": nodes, "edges": edges}

report = finalize(graph, read_tex(TEX))
for w in report["warnings"]:
    print("WARN", w)
print("ERRORS", report["errors"])
print({k: (v if not isinstance(v, list) else len(v)) for k, v in report.items() if k not in ("warnings", "errors")})
assert not report["errors"], report["errors"]
json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
print("wrote", OUT, len(nodes), "nodes", len(graph["edges"]), "edges")
