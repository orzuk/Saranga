#!/usr/bin/env python3
"""Build the v7 SARANGA graph of arXiv 2112.15534 (Jacobovic & Zuk).

Run: python3 build.py   (reads facts.json from the scratch dir, writes ../2112_15534.json)
"""
import json
import os
import re
import sys

sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
from extraction_finalize import finalize  # noqa: E402
from latex_facts import read_tex  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
TEX = os.path.join(PAPER, "arxiv_src", "ParetoPhaseTransition_Revision02.tex")
SCRATCH = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_orzuk/2112_15534"
OUT = os.path.join(PAPER, "2112_15534.json")

facts = json.load(open(os.path.join(SCRATCH, "facts.json")))
SRC = facts["source"]
F = {f["id"]: f for f in facts["facts"]}
SEC = {s["id"]: s for s in facts["sections"]}


def clean(t):
    t = re.sub(r"\\label\{[^}]*\}", " ", t)
    return " ".join(t.split())


def cut(start, end, after=None):
    """Verbatim span of SRC from `start` through `end` (inclusive); the first `start` after `after`."""
    a = _find(after, 0)[0] if after else 0
    assert a >= 0, after
    i, _ = _find(start, a)
    assert i >= 0, start
    j, je = _find(end, i)
    assert j >= 0, (start, end)
    return clean(SRC[i:je])


def _find(marker, pos):
    m = re.compile(r"\s+".join(map(re.escape, marker.split()))).search(SRC, pos)
    return (m.start(), m.end()) if m else (-1, -1)


def fact(fid):
    f = F[fid]
    return clean(SRC[f["start"]:f["end"]])


def secname(sid):
    s = SEC[sid]
    return (s["number"] + " " if s["number"] else "") + s["title"]


SEC_OF = {}  # resolved after; nodes carry section ids first

nodes = []
edges = []


def node(id, type, name, statement, sec, origin="paper", conf=1.0, **kw):
    n = {"id": id, "type": type, "name": name, "statement": statement,
         "section": secname(sec), "origin": origin, "confidence": conf}
    n.update(kw)
    nodes.append(n)
    return n


def eq(id, fid, name, conf=1.0, **kw):
    f = F[fid]
    return node(id, "equation", name, fact(fid), f["section"], conf=conf, **kw)


def E(s, t, type="uses", conf=0.8, basis="inferred", **kw):
    e = {"source": s, "target": t, "type": type, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)


STD = "standard (uncited)"

# ---------------------------------------------------------------- Section 2
node("DP1", "definition", "Indicator function",
     cut("In the sequel, for every set $A$", "\\end{equation}"), "S2", origin="external",
     origin_citation=STD, conf=0.85, definiendum="$\\textbf{1}_A(a)$")
eq("EP1", "F1", "Indicator function cases")
node("DP2", "definition", "Min/max wedge-vee notation",
     cut("In addition, in several places of this manuscript", "\\max_i x_i$)."), "S2",
     origin="external", origin_citation=STD, conf=0.85,
     definiendum=["$\\underset{i}{\\wedge} x_i$", "$\\underset{i}{\\vee} x_i$"])
node("DP3", "definition", "Product order",
     cut("It is based on the product order", "\\end{equation}"), "S3", origin="external",
     origin_citation=STD, conf=0.85, definiendum="product order $\\preceq$",
     statement_short="Coordinatewise (product) partial order $a\\preceq b$ iff $a_i\\le b_i$ for all $i$.")
eq("EP2", "F2", "Product order relation")
node("DP4", "definition", "Strict product order",
     cut("Similarly, define \\begin{equation}", "\\end{equation}", after="It is based on the product order"),
     "S3", origin="external", origin_citation=STD, conf=0.85, definiendum="$\\prec$")
eq("EP3", "F3", "Strict product order relation")
node("DP5", "definition", "Maximum (strong) and Pareto-front", fact("F4"), "S3",
     origin="external", origin_citation=STD, conf=1.0,
     definiendum=["maximum", "Pareto-front"], genus="vectors in $\\mathbb{R}^k$",
     differentia=["there is no $j\\neq i$ such that $x_i\\preceq x_j$"],
     statement_short="$x_i$ is a (strong) maximum if no other $x_j$ weakly dominates it; the set of maxima is the Pareto-front.",
     also_stated_at=[cut("A vector is said to be a (strong) maximum", "dominates it in all coordinates.")])
node("RP1", "remark", "Definition 1 is a strong maximum", fact("F5"), "S3", conf=1.0,
     statement_short="Equal vectors are all usual maxima but none is a maximum in the sense of Definition 1.")
node("ExP1", "example", "Multiple maxima", fact("F6"), "S3", conf=0.9)
node("DP6", "definition", "Weak maximum and weak Pareto-front", fact("F7"), "S3",
     origin="external", origin_citation=STD, conf=0.9,
     definiendum=["weak maximum", "weak Pareto-front"],
     differentia=["there is no $j\\neq i$ such that $x_i\\prec x_j$"])
node("DP7", "definition", "iid array X_ij",
     cut("Let $\\left\\{X_{ij} ;i,j\\geq1\\right\\}$ be an infinite array", "distribution function $F$."),
     "S4", conf=0.8, definiendum="$X_{ij}$")
node("DP8", "definition", "Random vectors X_i^k and Pareto index set",
     cut("For every $i,k\\geq1$ denote $X_i^{k}", "X_1^k,X_2^k,\\ldots,X_n^k$."), "S4", conf=0.8,
     definiendum=["$X_i^{k}$", "$\\maxset{k}{n}$"],
     statement_short="$X_i^k$ is the first $k$ coordinates of row $i$; $\\mathcal{P}_{k,n}$ is the random set of Pareto-front indices among $n$ vectors.")
node("DP9", "definition", "Event A_{k,n}",
     cut("Then, observe that $\\textbf{1}_{\\maxset{k}{n}}(1)$", "occurs."), "S4", conf=0.8,
     definiendum="$A_{k,n}$",
     statement_short="Vector 1 is a maximum iff $A_{k,n}$: no other vector weakly dominates it.")
eq("EP4", "F8", "Event that vector 1 is a maximum")
node("ClP1", "claim", "Almost-sure convergence via liminf/limsup of A",
     cut("Moreover, note that for every  sequence", "\\end{equation}", after="A_{k,n}\\equiv"),
     "S4", conf=0.7, rigor="semi_formal",
     assumptions=["for every  sequence $(k_n)_{n\\geq1}$ of positive integers"],
     conclusions=["$\\textbf{1}_{\\maxset{k_n}{n}}(1)\\xrightarrow{n\\to\\infty}1$ (resp. $\\textbf{1}_{\\maxset{k_n}{n}}(1)\\xrightarrow{n\\to\\infty}0$) $P$-a.s. iff"],
     statement_short="Indicator of vector 1 being maximal tends to 1 (resp. 0) a.s. iff $P(\\liminf A_{k_n,n})=1$ (resp. $P(\\limsup A_{k_n,n})=0$).")
eq("EP5", "F9", "liminf/limsup criterion")
node("ClP2", "claim", "Initial observation: fixed k or fixed n",
     cut("An initial observation is that:", "\\end{enumerate}", after="\\subsection{Problem description}"),
     "S4", conf=0.75, rigor="semi_formal",
     conclusions=["For every fixed $k\\geq1$, $\\textbf{1}_{\\maxset{k}{n}}(1)\\xrightarrow{n\\to\\infty}0$ , $P$-a.s.",
                  "For every fixed $n\\geq1$, $\\textbf{1}_{\\maxset{k}{n}}(1)\\xrightarrow{k\\to\\infty}1$ , $P$-a.s."],
     statement_short="For fixed $k$ vector 1 is eventually not maximal a.s.; for fixed $n$ it is eventually maximal as $k\\to\\infty$.",
     also_stated_at=[cut("Once $k$ (resp. $n$) is fixed", "as $n\\to\\infty$ (resp. $k\\to\\infty$).")])
node("ProbP1", "problem", "Asymptotics of being a maximum for general k_n",
     cut("The main question is how to generalize", "$(k_n)_{n=1}^\\infty$?"), "S4", conf=0.75,
     statement_short="Characterize when vector 1 is eventually a.s. maximal for a general sequence $k_n$.")
node("DP10", "definition", "Random variable X with cdf F",
     cut("Let $X$ be a random variable with a cumulative distribution function $F$.", "$F$."), "S5",
     conf=0.8, definiendum="$X$")
node("DP11", "definition", "Function S (left-continuous survival)",
     cut("Define the function $S:", "P(X \\geq x)$."), "S5", conf=0.9, definiendum="$S$")
node("DP12", "definition", "Factor gamma",
     cut("Next, define \\begin{equation}", "\\end{equation}", after="Define the function $S:"), "S5",
     conf=0.9, definiendum="$\\gamma \\equiv \\gamma_F$",
     statement_short="$\\gamma_F=-E\\log S(X)$, the functional of $F$ that locates the phase transition.")
eq("EP6", "F10", "Definition of gamma")
TA = "Let $k_1,k_2,\\ldots$ be a sequence of positive integers"
node("TP1", "theorem", "Phase transition for being a maximum (a.s.)", fact("F11"), "S5", conf=1.0,
     main=True,
     assumptions=[TA, "\\liminf_{n\\to\\infty}\\frac{k_n}{\\log(n)}>\\gamma^{-1}\\,",
                  "\\limsup_{n\\to\\infty}\\frac{k_n}{\\log(n)}< \\gamma^{-1}\\,"],
     conclusions=["\\textbf{1}_{\\maxset{k_n}{n}}(1)\\xrightarrow{n\\to\\infty}1\\, \\ \\ P\\text{-a.s.}",
                  "\\textbf{1}_{\\maxset{k_n}{n}}(1)\\xrightarrow{n\\to\\infty}0, \\ \\ P\\text{-a.s.}"],
     parts=[{"assumptions": ["\\liminf_{n\\to\\infty}\\frac{k_n}{\\log(n)}>\\gamma^{-1}\\,"],
             "conclusions": ["\\textbf{1}_{\\maxset{k_n}{n}}(1)\\xrightarrow{n\\to\\infty}1\\, \\ \\ P\\text{-a.s.}"]},
            {"assumptions": ["\\limsup_{n\\to\\infty}\\frac{k_n}{\\log(n)}< \\gamma^{-1}\\,"],
             "conclusions": ["\\textbf{1}_{\\maxset{k_n}{n}}(1)\\xrightarrow{n\\to\\infty}0, \\ \\ P\\text{-a.s.}"]}],
     tags=["phase_transition", "pareto_front", "extreme_value_theory"],
     statement_short="If $k_n/\\log n$ eventually exceeds $1/\\gamma$, vector 1 is a.s. eventually a maximum; if it stays below $1/\\gamma$, a.s. eventually not.")
eq("EP7", "F12", "Condition (a): liminf k_n/log n > 1/gamma")
eq("EP8", "F13", "Conclusion (a)")
eq("EP9", "F14", "Condition (b): limsup k_n/log n < 1/gamma")
eq("EP10", "F15", "Conclusion (b)")
PKN_INTRO = "Let $p_{k,n}$ be the probability that the first vector is a maximum."
node("DP13", "definition", "Probability p_{k,n} of being a maximum",
     cut("For every $k,n\\geq1$, denote \\begin{equation}", "\\end{equation}", after="\\end{theorem}"),
     "S5", conf=0.9, definiendum="$p_{k,n}$", also_stated_at=[PKN_INTRO])
eq("EP11", "F16", "p_{k,n} as expectation")
node("PP1", "proof", "Corollary 1 via bounded convergence",
     cut("Then, an application of bounded convergence theorem", "corollary."), "S5", conf=0.85,
     proves="CP1", proof_strategy=["direct"],
     statement_short="Apply the bounded convergence theorem to the a.s. limits of Theorem 1.")
node("CP1", "corollary", "Phase transition for p_{k,n}", fact("F17"), "S5", conf=1.0, main=True,
     assumptions=["Let $k_1,k_2,\\ldots$ be a sequence of positive integers.",
                  "\\liminf_{n\\to\\infty}\\frac{k_n}{\\log(n)}>\\gamma^{-1}",
                  "\\limsup_{n\\to\\infty} \\frac{k_n}{\\log(n)}<\\gamma^{-1}"],
     conclusions=["\\lim_{n \\to \\infty} p_{k_n,n} = 1", "\\lim_{n \\to \\infty} p_{k_n,n} = 0"],
     parts=[{"assumptions": ["\\liminf_{n\\to\\infty}\\frac{k_n}{\\log(n)}>\\gamma^{-1}"],
             "conclusions": ["\\lim_{n \\to \\infty} p_{k_n,n} = 1"]},
            {"assumptions": ["\\limsup_{n\\to\\infty} \\frac{k_n}{\\log(n)}<\\gamma^{-1}"],
             "conclusions": ["\\lim_{n \\to \\infty} p_{k_n,n} = 0"]}],
     tags=["phase_transition", "pareto_front"],
     statement_short="$p_{k_n,n}\\to1$ if $\\liminf k_n/\\log n>1/\\gamma$ and $\\to0$ if $\\limsup k_n/\\log n<1/\\gamma$.",
     also_stated_at=[cut("The main result of the present paper is that", "as $n\\to\\infty$."),
                     cut("Namely, we will show that", "depends on the distribution $F$.")])
eq("EP12", "F18", "Part (a') implication")
eq("EP13", "F19", "Part (b') implication")
node("DP14", "definition", "Generalized inverse S^{-1}",
     cut("Define \\begin{equation}", "\\end{equation}", after="\\subsection{The factor $\\gamma$}"), "S6",
     origin="external", origin_citation=STD, conf=0.85, definiendum="$S^{-1}$")
eq("EP14", "F20", "Generalized inverse of S")
node("ClP3", "claim", "S(S^{-1}(y)) <= y",
     cut("Since $S$ is a nonincreasing leftcontinuous function", "y\\in(0,1)$."), "S6", conf=0.7,
     rigor="semi_formal", assumptions=["$S$ is a nonincreasing leftcontinuous function"],
     conclusions=["$S\\left[S^{-1}(y)\\right]\\leq y$ for every $y\\in(0,1)$"])
node("PP2", "proof", "gamma <= 1 via tail-integral formula",
     cut("By definition, $-\\log\\left[S(X)\\right]\\geq0$", "\\end{align}"), "S6", conf=0.7,
     proves="ClP5", proof_strategy=["direct"],
     statement_short="Write $\\gamma$ as $\\int_0^\\infty P[-\\log S(X)>t]dt$ and bound the integrand by $e^{-t}$.")
eq("EP15", "F21", "Tail-integral chain giving gamma <= 1")
node("ClP4", "claim", "gamma = 1 for continuous F",
     cut("When $F$ is continuous, the last inequality above", "$\\gamma=1$."), "S6", conf=0.75,
     rigor="semi_formal", assumptions=["When $F$ is continuous"],
     conclusions=["the last inequality above holds with equality and $\\gamma=1$"])
node("PP3", "proof", "gamma = 0 only if S = 1",
     cut("Moreover, $\\gamma=0$ if and only if $S\\equiv1$", "infinite."), "S6", conf=0.7,
     proves="ClP5", proof_strategy=["direct"],
     statement_short="$\\gamma=0$ forces $S\\equiv1$, impossible for a real-valued $X$.")
node("ClP5", "claim", "gamma lies in (0,1]",
     cut("Thus, the assumption that $X$ is real-valued implies", "(0,1]$."), "S6", conf=0.75,
     assumptions=["the assumption that $X$ is real-valued"], conclusions=["$\\gamma\\in(0,1]$"])
node("ExP2", "example", "gamma for the Bernoulli distribution",
     cut("For example, when the coordinates have a $\\text{Bernoulli}(p)$", "obtained at $p = e^{-1}$."),
     "S6", conf=0.85,
     statement_short="For Bernoulli($p$), $\\gamma=-p\\log p$, maximal value $e^{-1}$ at $p=e^{-1}$.")
eq("EP16", "F22", "S for Bernoulli(p)")
eq("EP17", "F23", "gamma = -p log p for Bernoulli")

# ---------------------------------------------------------------- Section 3
node("DP15", "definition", "F-indexed Pareto set and probability",
     cut("We specify the dependence on $F$ explicitly", "when $X_{ij} \\sim F$."), "S7", conf=0.8,
     definiendum=["$\\maxset{k}{n}^{(F)}$", "$p_{k,n}^{(F)}$"])
node("DP16", "definition", "Weak Pareto set and probability q_{k,n}",
     cut("Similarly, we denote by $\\weakmaxset{k}{n}^{(F)}$", "\\end{equation}"), "S7", conf=0.85,
     definiendum=["$\\weakmaxset{k}{n}^{(F)}$", "$q_{k,n}^{(F)}$"])
eq("EP18", "F24", "q_{k,n} as expectation")
node("ClP6", "claim", "Strong maxima are weak maxima",
     cut("By definition $X_j^k \\succ X_i^k", "p_{k,n}^{(F)} \\leq q_{k,n}^{(F)}$."), "S7", conf=0.75,
     conclusions=["$\\maxset{k}{n}^{(F)} \\subseteq \\weakmaxset{k}{n}^{(F)}$ and $p_{k,n}^{(F)} \\leq q_{k,n}^{(F)}$"])
node("ClP7", "claim", "Strong and weak coincide for continuous F",
     cut("In particular, when $F$ is continuous, $\\maxset{k}{n}^{(F)} = ", "p_{k,n}^{(F)}=q_{k,n}^{(F)}$."),
     "S7", conf=0.75, rigor="semi_formal", assumptions=["when $F$ is continuous"],
     conclusions=["$\\maxset{k}{n}^{(F)} = \\weakmaxset{k}{n}^{(F)}$, $P$-a.s., hence $p_{k,n}^{(F)}=q_{k,n}^{(F)}$"])
node("ClP8", "claim", "All continuous F give the uniform probabilities",
     cut("let $U(\\cdot)$ be the uniform distribution function", "\\end{equation}", after="In particular, when $F$ is continuous"),
     "S7", conf=0.7, rigor="semi_formal",
     assumptions=["let $U(\\cdot)$ be the uniform distribution function on $[0,1]$"],
     conclusions=["every continuous $F$ satisfies the relation"],
     statement_short="For continuous $F$, strong and weak maximum probabilities equal those of the uniform distribution.")
eq("EP19", "F25", "p^U = p^F = q^F = q^U")
nodes[-2]["statement"] = clean("Moreover, " + nodes[-2]["statement"])
node("DP17", "definition", "Bernoulli probability p_{k,n}^{(p)}",
     cut("To shorten notation, for every $p\\in(0,1)$", "distribution."), "S7", conf=0.85,
     definiendum="$p_{k,n}^{(p)}$")
node("PrP1", "proposition", "Continuous and Bernoulli are extreme cases", fact("F26"), "S7", conf=1.0,
     assumptions=["Let $F$ be a general distribution function."],
     conclusions=["$p_{k,n}^{(F)} \\leq p^{(U)}_{k,n}$",
                  "$p_{k,n}^{(p)} \\leq p_{k,n}^{(F)}$ for every $p \\in \\left\\{1-F(x);x\\in\\mathbb{R}\\right\\}$"],
     tags=["bound", "coupling"],
     statement_short="The strong-maximum probability for any $F$ lies between the Bernoulli($p$) value ($p$ in the range of $1-F$) and the continuous value.")
PP4 = node("PP4", "proof", "Proof of Proposition 1 by monotone coupling", fact("F27"), "S7", conf=1.0,
           proves="PrP1", proof_strategy=["construction"],
           statement_short="Couple via a nondecreasing transformation: $X=F^{-1}(U)$ for the upper bound, $B=\\mathbf 1\\{X>x\\}$ for the lower bound; domination is preserved.")
node("PSP1", "proof_step", "Upper bound via quantile coupling",
     cut("The random variables $X_{ij} \\sim F$ can be realized", "p^{(U)}_{k,n}$.", after="\\begin{proposition}"),
     "S7", conf=0.95, parent_id="PP4", step_order=1, subclass="introduce_variable",
     statement_short="Realize $X=F^{-1}(U)$; domination of $U$ vectors transfers, so $\\mathcal P^{(F)}\\subseteq\\mathcal P^{(U)}$.")
node("PSP2", "proof_step", "Lower bound via thresholding",
     cut("Take $x$ with $p \\equiv 1-F(x)$", "depth-0.1ex"), "S7", conf=0.95, parent_id="PP4",
     step_order=2, subclass="introduce_variable",
     statement_short="Threshold $B=\\mathbf 1\\{X>x\\}$; maxima of $B$ are maxima of $X$, so $\\mathcal P^{(p)}\\subseteq\\mathcal P^{(F)}$.")
node("RP2", "remark", "No ordering for weak maxima", fact("F28"), "S7", conf=1.0, rigor="numerical")

# 3.1 continuous
node("TP2", "theorem", "Exact formulas for p_{k,n}^{(U)}",
     cut("For every $k,n\\geq1$, there are well-known exact formulas", "\\end{enumerate}",
         after="\\subsection{Continuous distribution}"),
     "S8", origin="external", origin_citation="Bai et al. 2005 (bai2005maxima)", conf=0.85,
     assumptions=["For every $k,n\\geq1$"],
     statement_short="Alternating-sum formula, a recurrence in $k$, and a sum over nondecreasing integer tuples for the continuous-case probability.")
eq("EP20", "F29", "Combinatorial (alternating sum) formula")
eq("EP21", "F30", "Recurrence for p^{(U)}")
eq("EP22", "F31", "Sum over nondecreasing tuples")
eq("EP23", "F32", "Index set U_{k,n}")
node("TP3", "theorem", "Fixed-k asymptotics of p_{k,n}^{(U)}",
     cut("Furthermore, it is well known (see, e.g., \\cite{barndorff1966distribution})", "\\end{equation}"),
     "S8", origin="external", origin_citation="Barndorff-Nielsen & Sobel 1966", conf=0.85,
     assumptions=["for every fixed $k$"],
     conclusions=["p_{k,n}^{(U)}\\sim\\frac{\\log^{k-1}(n)}{n (k-1)!}\\ \\ \\text{as}\\ \\ n\\to\\infty."])
eq("EP24", "F33", "p^{(U)} ~ log^{k-1}(n)/(n(k-1)!)")
node("TP4", "theorem", "Hwang's first-order approximation",
     cut("Specifically, let $\\Phi(\\cdot)$ be the cumulative distribution", "as $n\\to\\infty$.",
         after="\\label{eq: Hwang2004}"[0:0] + "Hwang \\cite{hwang2004phase} applied"),
     "S8", origin="external", origin_citation="Hwang 2004", conf=0.85,
     assumptions=["let $\\Phi(\\cdot)$ be the cumulative distribution function of a standard normal random variable",
                  "let $\\Gamma(\\cdot)$ be the Gamma function"],
     conclusions=["it holds uniformly for all variations of $k$ as $n\\to\\infty$"],
     statement_short="Three-regime approximation of $p^{(U)}_{k,n}$: Gamma-corrected fixed-$k$ formula below, a normal cdf window around, and 1 above $k\\approx\\log n$.")
eq("EP25", "F34", "Hwang 2004 approximation")
node("ClP9", "claim", "Hwang's approximation implies Corollary 1 (continuous case)",
     cut("Since $\\gamma=1$ for every continuous $F$, it may be verified", "Corollary \\ref{cor: main corollary}."),
     "S8", conf=0.7, rigor="semi_formal")
node("RP3", "remark", "Theorem 1 not straightforward from Hwang",
     cut("However, since convergence in $P$ does not imply", "even for the continuous case."), "S8", conf=0.7)
node("OpenP1", "open_problem", "Hwang's question: probabilistic explanation of the phase transition",
     cut("In fact, Hwang \\cite{hwang2004phase} put forth the question", "$k\\approx\\log(n)$?"), "S8",
     origin="external", origin_citation="Hwang 2004", conf=0.8)
node("RP4", "remark", "Theorem 1 as a probabilistic explanation",
     cut("Theorem \\ref{thm: main result1} yields some probabilistic explanation", "\\eqref{eq: Hwang2004}."),
     "S8", conf=0.7)

# 3.2 Bernoulli
node("ClP10", "claim", "Exact formula for p_{k,n}^{(p)} (Bernoulli)",
     cut("Let $X_{ij}\\sim\\text{Bernoulli}\\left(p\\right)$", "is defined to be $1$."), "S9", conf=0.75,
     assumptions=["Let $X_{ij}\\sim\\text{Bernoulli}\\left(p\\right)$ for some $p \\in (0,1)$."],
     statement_short="Conditioning on the number of ones in vector 1 gives $p^{(p)}_{k,n}=\\sum_i\\binom ki p^i(1-p)^{k-i}(1-p^i)^{n-1}$.")
eq("EP26", "F35", "Bernoulli exact formula")
node("ClP11", "claim", "Fixed-k asymptotics, Bernoulli strong maximum",
     cut("Since $(1 - p^{i})^{n-1} = o", "\\end{equation}"), "S9", conf=0.75,
     conclusions=["p_{k,n}^{(p)} \\sim p^{k} (1-p^{k})^{n-1} \\ \\ \\text{as}\\ \\ n\\to\\infty."])
eq("EP27", "F36", "p^{(p)} ~ p^k (1-p^k)^{n-1}")
node("RP5", "remark", "Exact Bernoulli formula hard to analyze", fact("F37"), "S9", conf=1.0)
node("ClP12", "claim", "Exact formula for weak maximum, Bernoulli",
     cut("A similar calculation to the one in", "for fixed $k$ as $n \\to \\infty$."), "S9", conf=0.75,
     conclusions=["the asymptotic result $q_{k,n}^{(p)} \\to p^{k}$ for fixed $k$ as $n \\to \\infty$"],
     statement_short="Analogous conditioning gives an exact sum for $q^{(p)}_{k,n}$, and $q^{(p)}_{k,n}\\to p^k$ for fixed $k$.")
eq("EP28", "F38", "Bernoulli weak-maximum formula")
node("RP6", "remark", "Contrast of decay rates: continuous vs Bernoulli", fact("F39"), "S9", conf=1.0,
     statement_short="Continuous case decays like $\\log^{k-1}n/n$, Bernoulli strong maximum exponentially, weak maximum tends to $p^k$ since $(1,\\dots,1)$ appears.")
node("DP18", "definition", "Pair counts B_ij and their multinomial law",
     cut("For every $i,j\\in\\{0,1\\}$ define", "\\end{equation}", after="\\label{eq:multinom}"[0:0] + "we derive a combinatorial formula for the variance")
     + " " + cut("and observe that vector $(B_{00}", "\\end{equation}"),
     "S9", conf=0.8, definiendum="$B_{ij}$")
eq("EP29", "F40", "B_ij counts")
eq("EP30", "F41", "Multinomial law of (B_00,...,B_11)")
node("ClP13", "claim", "Variance of the Bernoulli Pareto-front size",
     cut("By conditioning on this random vector deduce that", "\\end{equation}", after="\\label{eq:multinom}"),
     "S9", conf=0.75,
     statement_short="Conditioning on the pair counts gives $P(1,2\\in\\mathcal P)$ and hence an exact variance of the front size.")
eq("EP31", "F42", "Joint probability that vectors 1 and 2 are maxima")
eq("EP32", "F43", "Variance V_{k,n}^{(p)}")
node("RP7", "remark", "Degenerate limit for fixed k", fact("F44"), "S9", conf=1.0)
node("OpenP2", "open_problem", "Non-degenerate limit of the Pareto-front size",
     cut("An interesting question for future work is whether", "is non-degenerate."), "S9", conf=0.8)
node("RP8", "remark", "Other distributions as follow-up", fact("F45"), "S9", conf=1.0)

# 3.3 numerics
node("RP9", "remark", "Numerical comparison Bernoulli vs continuous",
     cut("A numerical comparison between the Bernoulli and continuous cases", "for the continuous case."),
     "S10", conf=0.7, rigor="numerical",
     statement_short="Figure 1 shows fixed-$k$ behaviour and the phase transition at $k_n=c\\log n$ for uniform and Bernoulli(0.5).")
node("CnjP1", "conjecture", "Phase transition also holds for weak maxima",
     cut("However, when both $k,n \\to \\infty$, Figure", "also holds for $q_{k,n}^{(p)}$."), "S10",
     conf=0.75, assumptions=["when both $k,n \\to \\infty$"],
     conclusions=["the phase transition established by Theorem \\ref{thm: main result1} for $p_{k,n}^{(p)}$ also holds for $q_{k,n}^{(p)}$"])
node("RP10", "remark", "Numerical computation method",
     cut("For numerical calculation of $p^{(U)}_{k,n}$", "{https://github.com/orzuk/Pareto}."), "S10",
     conf=0.7,
     statement_short="Use the recurrence (stable, $O(n)$ per $k$) for the continuous case and the direct Bernoulli formula up to $n\\approx10^{130}$.")

# ---------------------------------------------------------------- Section 4: proof of Theorem 1
END_THM = "P\\text{-a.s.}"
pp5_start = SRC.find("For every $i\\geq2$, let")
pp5_end = SRC.find("\\hfill", SRC.find("Similarly, \\eqref{eq: condition2}"))
node("PP5", "proof", "Proof of Theorem 1", clean(SRC[pp5_start:pp5_end]), "S11", conf=0.9,
     proves="TP1", proof_strategy=["probabilistic"],
     statement_short="Reduce maximality to $M_n^1\\le k-1$ for a maximum of dependent geometrics, sandwich $M_n^1$ between maxima of iid geometrics (Lemma 1), and apply Ferguson. Key step: $M_n^1/\\log n\\to1/\\gamma$ a.s.")
# setup part (before the continuation heading)
setup = clean(SRC[pp5_start:SRC.find("\\subsubsection*{Proof of Theorem")])
node("PSP3", "proof_step", "Reduction to the maximum of dependent geometric variables", setup, "S11",
     conf=0.95, parent_id="PP5", step_order=1, subclass="setup",
     statement_short="Encode maximality through $M_n^1$ and couple it with iid geometric maxima.")
node("PSP4", "proof_step", "Define G_i^1",
     cut("For every $i\\geq2$, let", "for every $k> G^{1}_i$."), "S11", conf=0.75, parent_id="PSP3",
     step_order=1, subclass="introduce_variable",
     statement_short="$G_i^1$ = length of the initial run on which $X_i$ dominates $X_1$.")
eq("EP33", "F46", "G_i^1 definition")
node("PSP5", "proof_step", "Maximality criterion via M_n^1",
     cut("In particular, this implies that for every $n,k\\geq1$", "equals zero."), "S11", conf=0.75,
     parent_id="PSP3", step_order=2, subclass="other",
     statement_short="Vector 1 is a maximum iff $M_n^1=\\max_i G_i^1\\le k-1$.")
eq("EP34", "F47", "Max condition 1 in P_{k,n} iff M_n^1 <= k-1")
node("PSP6", "proof_step", "M_n^1 is a maximum of dependent geometrics",
     cut("Thus, the asymptotic behaviour of $\\textbf{1}_{\\maxset{k}{n}}(1)$ as $n,k\\to\\infty$", "{\\it independent} geometric random variables."),
     "S11", conf=0.75, parent_id="PSP3", step_order=3, subclass="setup",
     statement_short="Reduce to the asymptotics of $M_n^1$, a maximum of identically distributed dependent geometrics.")
lemma_block = clean(SRC[F["F48"]["outer_start"] if "outer_start" in F["F48"] else F["F48"]["start"]:F["F51"]["outer_end"]])
node("PSP7", "proof_step", "Coupling lemma and its proof", lemma_block, "S11", conf=0.75,
     parent_id="PSP3", step_order=4, subclass="setup",
     statement_short="State and prove Lemma 1 (coupling with iid geometric maxima).")
node("LP1", "lemma", "Coupling lemma with iid geometric maxima", fact("F48"), "S11", conf=1.0,
     assumptions=["Let $\\left\\{X_{ij};i,j\\geq1\\right\\}$ be iid random variables with a distribution function $F$ for which $\\gamma\\equiv\\gamma_F$ as defined in \\eqref{eq:gamma_def}.",
                  "let $G_2,G_3,\\ldots$ be an iid sequence of geometric random variables with success probability $\\alpha\\in(0,1)$.",
                  "assume that $\\left\\{G_i ; i\\geq2\\right\\}$ and $\\left\\{X_{ij};i,j\\geq1\\right\\}$ are independent.",
                  "for every $\\alpha\\in(0,1)\\setminus\\{1-e^{-\\gamma}\\}$"],
     conclusions=["is $P$-a.s. finite."], tags=["coupling", "geometric_distribution"],
     statement_short="Eventually $M_n\\le M_n^1$ if $1-\\alpha<e^{-\\gamma}$ and $M_n\\ge M_n^1$ if $1-\\alpha>e^{-\\gamma}$, a.s.")
eq("EP35", "F49", "Random index N_alpha")
node("RP11", "remark", "Meaning of N_alpha", fact("F50"), "S11", conf=1.0)
node("PP6", "proof", "Proof of Lemma 1", fact("F51"), "S11", conf=1.0, proves="LP1",
     proof_strategy=["probabilistic", "case_analysis"],
     statement_short="Compare hitting times of level $k$ conditionally on $X_1$: both are geometric, the SLLN controls $\\prod_j S(X_{1j})$, and Borel-Cantelli gives eventual ordering. Key step: $P(\\tau_k\\le\\tau_k^1\\mid X_1)\\le[(1-\\alpha)e^{L_k}]^k$ is summable.")
node("PSP8", "proof_step", "Hitting times and conditional independence",
     cut("For every $k\\geq1$ denote", "are independent.", after="\\begin{proof}\n\tFor every"[0:0] + "Then, for every $\\alpha\\in(0,1)"),
     "S11", conf=0.75, parent_id="PP6", step_order=1, subclass="introduce_variable",
     statement_short="Define hitting times $\\tau_k^1,\\tau_k$; given $X_1$ the domination events are independent.")
for fid, i in zip(["F52", "F53"], [36, 37]):
    eq(f"EP{i}", fid, {36: "Hitting times tau_k^1, tau_k", 37: "Domination events"}[i])
node("PSP9", "proof_step", "Conditional geometric laws",
     cut("Therefore, the random variables $\\tau_k^1$ and $\\tau_k$ are conditionally", "\\left(\\left(1-\\alpha\\right)^k\\right). \\end{equation}"),
     "S11", conf=0.75, parent_id="PP6", step_order=2, subclass="other",
     statement_short="Given $X_1$, $\\tau_k^1-1\\sim$Geo$(\\prod_{j\\le k}S(X_{1j}))$ and $\\tau_k-1\\sim$Geo$((1-\\alpha)^k)$.")
eq("EP38", "F54", "Conditional law of tau_k^1")
eq("EP39", "F55", "Law of tau_k")
node("PSP10", "proof_step", "SLLN for L_k",
     cut("In addition, as explained in Section \\ref{sec: gamma}", "$P$-a.s.", after="\\tau_k-1 \\sim"
         ).replace("", "") if False else cut("In addition, as explained in Section \\ref{sec: gamma}", "$e^{-kL_k}\\xrightarrow{k\\to\\infty}0$, $P$-a.s."),
     "S11", conf=0.75, parent_id="PP6", step_order=3, subclass="apply_lemma",
     statement_short="By the strong law of large numbers $L_k\\to\\gamma$ a.s.")
eq("EP40", "F56", "SLLN for L_k")
node("PSP11", "proof_step", "Case 1-alpha < e^{-gamma}",
     cut("Consider the case where $1-\\alpha<e^{-\\gamma}$.", "which yields the required result when $1-\\alpha<e^{-\\gamma}$."),
     "S11", conf=0.75, parent_id="PP6", step_order=4, subclass="case_split",
     statement_short="Case $1-\\alpha<e^{-\\gamma}$: show $M_n>M_n^1$ only finitely often.")
node("PSP12", "proof_step", "Uniform bound zeta_alpha < 1",
     cut("Consider the case where $1-\\alpha<e^{-\\gamma}$.", "such that $\\zeta_\\alpha<1$."), "S11",
     conf=0.75, parent_id="PSP11", step_order=1, subclass="bound_estimate",
     statement_short="Eventually $(1-\\alpha)e^{L_k}\\le\\zeta_\\alpha<1$.")
eq("EP41", "F57", "zeta_alpha bound (case 1)")
node("PSP13", "proof_step", "Summable bound via minimum of geometrics",
     cut("In addition, $e^{-k L_k} \\leq 1$ for every $k \\geq 1$.", "\\end{align}"), "S11", conf=0.75,
     parent_id="PSP11", step_order=2, subclass="bound_estimate",
     statement_short="$P(\\tau_k\\le\\tau_k^1\\mid X_1)\\le\\zeta_\\alpha^k$, summable.")
eq("EP42", "F58", "Summable series, case 1")
node("PSP14", "proof_step", "Borel-Cantelli, case 1",
     cut("Thus, the Lemma of Borel-Cantelli implies that", "\\end{equation}", after="\\zeta_\\alpha^k<\\infty"),
     "S11", conf=0.75, parent_id="PSP11", step_order=3, subclass="apply_lemma",
     statement_short="Conditional Borel-Cantelli, then average over $X_1$.")
node("PSP14b", "proof_step", "", "", "S11")  # placeholder removed below
nodes.pop()
eq("EP43", "F59", "Conditional Borel-Cantelli")
eq("EP44", "F60", "Unconditional Borel-Cantelli")
node("PSP15", "proof_step", "Conclude case 1",
     cut("Therefore, $P(M_n > M_n^1 \\, \\ \\text{i.o}) = 0$", "when $1-\\alpha<e^{-\\gamma}$."), "S11",
     conf=0.75, parent_id="PSP11", step_order=4, subclass="conclude",
     statement_short="Hence $M_n>M_n^1$ only finitely often.")
node("PSP16", "proof_step", "Case 1-alpha > e^{-gamma}",
     cut("Assume that $1-\\alpha>e^{-\\gamma}$.", "depth-0.1ex \\newline", after="when $1-\\alpha<e^{-\\gamma}$. \n"[0:0] + "which yields the required result"),
     "S11", conf=0.75, parent_id="PP6", step_order=5, subclass="case_split",
     statement_short="Case $1-\\alpha>e^{-\\gamma}$: symmetric argument with $\\zeta_\\alpha>1$.")
node("PSP17", "proof_step", "Uniform bound zeta_alpha > 1",
     cut("Assume that $1-\\alpha>e^{-\\gamma}$.", "such that $\\zeta_\\alpha>1$."), "S11", conf=0.75,
     parent_id="PSP16", step_order=1, subclass="bound_estimate",
     statement_short="Eventually $(1-\\alpha)e^{L_k}\\ge\\zeta_\\alpha>1$.")
eq("EP45", "F61", "zeta_alpha bound (case 2)")
node("PSP18", "proof_step", "Summable bound and Borel-Cantelli, case 2",
     cut("In addition, for every $k\\geq1$, $(1-\\alpha)^k\\leq1$", "depth-0.1ex \\newline"), "S11",
     conf=0.75, parent_id="PSP16", step_order=2, subclass="conclude",
     statement_short="$P(\\tau_k\\ge\\tau_k^1\\mid X_1)\\le\\zeta_\\alpha^{-k}$, summable; conclude by Borel-Cantelli.")
eq("EP46", "F62", "Summable series, case 2")
# continuation
cont_start = SRC.find("It is possible to use Lemma")
node("PSP19", "proof_step", "Continuation: M_n^1/log n -> 1/gamma and conclusion",
     clean(SRC[cont_start:pp5_end]), "S12", conf=0.95, parent_id="PP5", step_order=2, subclass="conclude",
     statement_short="Show $M_n^1/\\log n\\to1/\\gamma$ a.s. and compare with $k_n$.")
node("PSP20", "proof_step", "Claim: extended Ferguson limit",
     cut("It is possible to use Lemma", "\\eqref{eq: extended ferguson} follows."), "S12", conf=0.75,
     parent_id="PSP19", step_order=1, subclass="bound_estimate",
     statement_short="Sandwich $M_n^1$ between iid geometric maxima to get $M_n^1/\\log n\\to1/\\gamma$.")
eq("EP47", "F63", "Extended Ferguson limit")
node("PSP21", "proof_step", "Choose alpha_1, alpha_2 and iid geometric sequences",
     cut("To this end, fix $\\epsilon>0$", "as described in the statement of Lemma \\ref{proposition: basic lemma}."),
     "S12", conf=0.75, parent_id="PSP20", step_order=1, subclass="introduce_variable",
     statement_short="Pick $\\alpha_1,\\alpha_2$ on either side of $1-e^{-\\gamma}$ with limits within $\\epsilon/2$ of $1/\\gamma$.")
eq("EP48", "F65", "Choice of alpha_l")
eq("EP49", "F66", "Partial maxima M_n^{(alpha_l)}")
node("PSP22", "proof_step", "Sandwich via Lemma 1",
     cut("Then, Lemma \\ref{proposition: basic lemma} implies that there exists", "\\end{equation}"), "S12",
     conf=0.75, parent_id="PSP20", step_order=2, subclass="apply_lemma",
     statement_short="Lemma 1 gives $M_n^{(\\alpha_1)}\\le M_n^1\\le M_n^{(\\alpha_2)}$ eventually.")
eq("EP50", "F67", "Sandwich of M_n^1")
node("PSP23", "proof_step", "Apply Ferguson's theorem",
     cut("Furthermore, Theorem $2$ of \\cite{Ferguson1993} yields", "\\end{equation}"), "S12", conf=0.75,
     parent_id="PSP20", step_order=3, subclass="apply_lemma",
     statement_short="Ferguson: $M_n^{(\\alpha)}/\\log n\\to-1/\\log(1-\\alpha)$ a.s.")
eq("EP51", "F68", "Ferguson limit for iid geometric maxima")
node("PSP24", "proof_step", "Squeeze",
     cut("As a result, there exists a $P$-a.s. finite random variable $N^*\\geq N$", "\\eqref{eq: extended ferguson} follows."),
     "S12", conf=0.75, parent_id="PSP20", step_order=4, subclass="bound_estimate",
     statement_short="Squeeze $M_n^1/\\log n$ within $\\epsilon/2$ of $1/\\gamma$.")
eq("EP52", "F69", "Squeeze inequality")
node("PSP25", "proof_step", "Conclude part (a)",
     cut("Therefore, \\eqref{eq: condition1} implies that", "$P$-a.s. Similarly,").rsplit(" Similarly,", 1)[0],
     "S12", conf=0.75, parent_id="PSP19", step_order=2, subclass="conclude",
     statement_short="Under (a), eventually $k_n-1\\ge M_n^1$, so vector 1 is a maximum.")
eq("EP53", "F70", "liminf (k_n-1)/M_n^1 > 1")
node("PSP26", "proof_step", "Conclude part (b)",
     cut("Similarly, \\eqref{eq: condition2} implies that", "depth-0.1ex \\newline\\newline"
         ).replace("\\newline\\newline", "").strip() if False else clean(SRC[SRC.find("Similarly, \\eqref{eq: condition2} implies that"):pp5_end]),
     "S12", conf=0.75, parent_id="PSP19", step_order=3, subclass="conclude",
     statement_short="Under (b), eventually $k_n> M_n^1$, so vector 1 is not a maximum.")
eq("EP54", "F71", "limsup k_n/M_n^1 < 1")

# ---------------------------------------------------------------- edges
T = lambda s, t, c=0.8: E(s, t, conf=c, basis="term")
# indicator, wedge/vee, orders
for t in ["DP13", "DP16", "ClP1", "ClP2", "ProbP1", "TP1", "PP5"]:
    T("DP1", t)
for t in ["ClP10", "ClP12", "ClP13", "LP1"]:
    T("DP2", t, 0.75)
for t in ["DP4", "DP5", "DP9", "PP4", "PP5", "PP6", "ClP6", "ClP10"]:
    T("DP3", t)
for t in ["DP6", "ClP6", "ClP12"]:
    T("DP4", t)
for t in ["DP6", "DP8", "DP15", "DP17"]:
    T("DP5", t, 0.75)
E("DP5", "ExP1", "illustrates", 0.9, "named")
E("DP5", "RP1", "illustrates", 0.9, "named") if False else None
for t in ["DP16", "ClP12"]:
    T("DP6", t, 0.8)
for t in ["DP8", "DP15", "ClP10", "PP5"]:
    T("DP7", t, 0.8)
for t in ["DP9", "ClP1", "ClP2", "ProbP1", "TP1", "DP13", "DP15", "PP5", "RP7"]:
    T("DP8", t)
for t in ["ClP1", "DP13"]:
    T("DP9", t)
for t in ["DP11", "DP12"]:
    T("DP10", t)
for t in ["DP12", "DP14", "ClP3", "PP2", "PP3", "ExP2", "PP6"]:
    T("DP11", t)
for t in ["TP1", "CP1", "ClP4", "ClP5", "PP5", "PP6", "RP9", "ClP9"]:
    T("DP12", t)
E("DP12", "ExP2", "illustrates", 0.9, "named")
for t in ["CP1", "RP5"]:
    T("DP13", t)
for t in ["ClP3", "PP2"]:
    T("DP14", t)
for t in ["DP16", "ClP6", "ClP7", "ClP8", "PrP1", "PP4", "RP2", "TP2", "TP3", "TP4", "ClP9", "RP6", "RP9", "RP10"]:
    T("DP15", t, 0.75)
for t in ["ClP6", "ClP7", "ClP8", "RP2", "ClP12", "RP6", "RP9", "CnjP1"]:
    T("DP16", t)
for t in ["PrP1", "PP4", "ClP10", "ClP11", "RP5", "ClP13", "RP6", "RP7", "RP9", "CnjP1", "RP10"]:
    T("DP17", t)
for t in ["PrP1", "PP4", "RP2", "TP2", "TP3", "TP4", "RP6", "RP9", "RP10"]:
    T("ClP8", t, 0.75)
T("DP18", "ClP13", 0.85)
for t in ["RP2", "RP6", "PP5", "RP7", "OpenP2"]:
    T("DP5", t, 0.75)
T("DP6", "RP6", 0.8)
T("DP8", "RP6", 0.75)
T("ClP13", "RP7", 0.8)
T("PSP4", "LP1", 0.8)
T("PSP5", "LP1", 0.8)
T("PSP4", "PP6", 0.75)
T("LP1", "RP11", 0.85)
# results
E("TP1", "PP1", conf=0.8)
E("PP1", "CP1", "proves", 0.85, "named")
E("ProbP1", "TP1", "resolves", 0.8)
E("ClP3", "PP2", conf=0.7)
E("PP2", "ClP5", "proves", 0.7)
E("PP3", "ClP5", "proves", 0.7)
E("PP3", "PP2", conf=0.65)
E("EP15", "ClP4", conf=0.8)
E("ClP4", "ClP9", conf=0.85, basis="named")
E("ClP4", "ClP8", conf=0.6)
E("ClP5", "PP6", conf=0.9, basis="named")
E("ExP2", "RP9", conf=0.7)
E("ClP7", "ClP8", conf=0.7)
E("ClP6", "RP2", conf=0.6)
E("PrP1", "RP2", conf=0.8)
E("CP1", "ClP9", conf=0.95, basis=None, mention=True)
E("TP1", "RP3", conf=0.95, basis=None, mention=True)
E("EP25", "RP3", conf=0.95, basis=None, mention=True)
E("EP25", "RP4", conf=0.95, basis=None, mention=True)
E("TP1", "RP4", conf=0.95, basis=None, mention=True)
E("OpenP1", "TP1", "resolves", 0.6, "named")
E("EP26", "ClP12", conf=0.95, basis=None, mention=True)
E("ClP11", "RP6", conf=0.8)
E("ClP12", "RP6", conf=0.8)
E("ClP11", "RP7", conf=0.7)
E("TP1", "CnjP1", conf=0.95, basis=None, mention=True)
E("TP1", "RP9", conf=0.6)
E("PP5", "TP1", "proves", 0.9, "named")
E("PP6", "LP1", "proves", 0.8)
# inside proofs
E("PSP8", "PSP9", conf=0.8)
E("PSP9", "PSP13", conf=0.8)
E("PSP10", "PSP12", conf=0.8)
E("PSP10", "PSP17", conf=0.8)
E("PSP12", "PSP13", conf=0.8)
E("PSP13", "PSP14", conf=0.8)
E("PSP14", "PSP15", conf=0.8)
E("PSP17", "PSP18", conf=0.8)
E("PSP9", "PSP18", conf=0.8)
E("PSP11", "PSP16", conf=0.75, basis="named")
E("PSP4", "PSP5", conf=0.8)
E("PSP5", "PSP6", conf=0.8)
E("PSP21", "PSP22", conf=0.8)
E("PSP22", "PSP24", conf=0.8)
E("PSP23", "PSP24", conf=0.8)
E("PSP20", "PSP25", conf=0.8)
E("PSP20", "PSP26", conf=0.8)
E("PSP6", "PSP7", conf=0.7)

edges = [e for e in edges if e]

graph = {
    "metadata": {
        "title": "A phase transition for the probability of being a maximum among random vectors with general iid coordinates",
        "arxiv_id": "2112.15534",
        "authors": ["Royi Jacobovic", "Or Zuk"],
        "year": 2021,
        "annotator": "agent-extraction",
        "model": "claude-opus-5-5",
        "effort": "default",
        "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
        "extraction_date": "2026-11-05",
        "rigor_nonformal_count": sum(1 for n in nodes if n.get("rigor")),
        "paper_style": ["theorem_proof", "computational"],
        "extraction_notes": [],
        "extraction_comment": "Possible issues for the author: the introduction and Section 3.3 put the threshold at gamma*log(n) where Theorem 1 has gamma^{-1}*log(n); the Fig. 1c caption has the direction reversed; and the joint-probability formula before (26) lacks the multinomial cell probabilities. Section 2.4 asserts S[S^{-1}(y)]<=y for a left-continuous S, and gamma=0 iff X infinite; both fail in general (Bernoulli; a degenerate F gives gamma=0).",
    },
    "nodes": nodes,
    "edges": edges,
}
NOTES = json.load(open(os.path.join(HERE, "notes.json"))) if os.path.exists(os.path.join(HERE, "notes.json")) else []
graph["metadata"]["extraction_notes"] = NOTES

report = finalize(graph, read_tex(TEX))
for w in report["warnings"]:
    print("WARN", w)
for k in ("matched_to_environment", "labels_filled"):
    print(k, report[k])
print("proves_added", len(report["proves_added"]), "ref_uses_added", len(report["ref_uses_added"]),
      "ref_backward", report["ref_backward"])
assert not report["errors"], "\n".join(map(str, report["errors"]))
json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
print("wrote", OUT, len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
