"""Build the SARANGA v7 graph of arXiv 2209.00346 (Jacobovic & Zuk 2022,
A correlation inequality for random points in a hypercube with some implications).
Node choices are made by reading; this script only slices the chosen spans."""
import json, sys, re
sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
from extraction_finalize import finalize
from latex_facts import read_tex, extract_facts

TEX = "/mnt/c/Code/Github/Saranga/corpus/orzuk/2209_00346/arxiv_src/XYZ_DNF_CNF.tex"
OUT = "/mnt/c/Code/Github/Saranga/corpus/orzuk/2209_00346/2209_00346.json"
tex = read_tex(TEX)
facts = extract_facts(tex)
SRC = facts["source"]
FACT = {f["id"]: f for f in facts["facts"]}
SECS = sorted([s for s in facts["sections"] if s["inside"] is None], key=lambda s: s["start"])


def sec_of(pos):
    cur = None
    for s in SECS:
        if s["start"] <= pos:
            cur = s
    if not cur:
        return ""
    return f"{cur['number']} {cur['title']}" if cur["number"] else cur["title"]


def _pat(t):
    return r"\s+".join(re.escape(w) for w in t.split())


def sp(a, b, lo=0, hi=None):
    """Slice from the unique occurrence of `a` in [lo, hi) to the end of the first `b` after it."""
    hi = len(SRC) if hi is None else hi
    ms = [m for m in re.finditer(_pat(a), SRC) if lo <= m.start() < hi]
    assert len(ms) == 1, (len(ms), a)
    i = ms[0].start()
    m = re.compile(_pat(b)).search(SRC, i)
    assert m, (a, b)
    return SRC[i:m.end()]


def clean(s):
    return " ".join(s.split())


def fs(fid):
    f = FACT[fid]
    return SRC[f["start"]:f["end"]]


def fst(fid):
    """clean body of a fact, for assumptions/conclusions"""
    return clean(re.sub(r"\\label\{[^{}]*\}", "", fs(fid)))


nodes, edges = [], []


def N(id, type, name, stmt, origin="paper", conf=0.75, **kw):
    pos = SRC.find(stmt)
    assert pos >= 0, id
    n = {"id": id, "type": type, "name": name, "statement": clean(stmt),
         "section": sec_of(pos), "origin": origin, "confidence": conf}
    n.update(kw)
    nodes.append(n)
    return n


def F(id, fid, type, name, conf=1.0, **kw):
    return N(id, type, name, fs(fid), conf=conf, **kw)


def EQ(id, fid, name, conf=1.0, **kw):
    return F(id, fid, "equation", name, conf=conf, **kw)


def STEPS(parent, specs, lo, hi, kind="proof_step"):
    """specs: list of (id, name, a, b, subclass, short[, parent_override, conf])"""
    order = {}
    par = next(n for n in nodes if n["id"] == parent)
    for spec in specs:
        sid, name, a, b, sub, short = spec[:6]
        pid = spec[6] if len(spec) > 6 and spec[6] else parent
        conf = spec[7] if len(spec) > 7 else 0.75
        st = sp(a, b, lo, hi)
        st = re.sub(r"^\\item\s*", "", st)
        order[pid] = order.get(pid, 0) + 1
        N(sid, kind, name, st, origin=par["origin"], conf=conf, parent_id=pid,
          step_order=order[pid], subclass=sub, statement_short=short)


def E(s, t, conf=0.8, basis="term", type="uses", **kw):
    e = {"source": s, "target": t, "type": type, "confidence": conf, "basis": basis}
    e.update(kw)
    edges.append(e)


STD = dict(origin="external", origin_citation="standard (uncited)")

# ================= 1 Introduction =================
N("DP1", "definition", "Index set $[l]$ and product order $\\prec$ on $\\mathbb{R}^k$",
  sp("For every positive integer $l \\in \\mathbb{N}$, denote", "\\end{equation}"), conf=0.85, **STD,
  definiendum=["$[l]$", "$\\prec$"],
  statement_short="$[l]=\\{1,\\dots,l\\}$; $x\\prec y$ iff $x_i\\le y_i$ for every coordinate $i$ (product order).")
EQ("EP1", "F2", "Product order $x\\prec y$")
N("DP2", "definition", "Negation $\\not\\prec$ of the product order",
  sp("In addition, $\\not\\prec$ is the negation of $\\prec$.", "of $\\prec$."), conf=0.85, **STD,
  definiendum="$\\not\\prec$")
N("DP3", "definition", "Random points $X_1,\\ldots,X_n$ and random sets $W$, $S$",
  sp("Let $X_1,X_2,\\ldots,X_n$ ($n\\geq3$) be i.i.d. random vectors distributed uniformly on", "\\end{equation}"),
  conf=0.85, definiendum=["$X_1,\\ldots,X_n$", "$W$", "$S$"],
  statement_short="$X_1,\\dots,X_n$ i.i.d. uniform on $[0,1]^k$; $W$ = points not dominated by any of $X_3..X_n$, $S$ = points dominating all of them.")
EQ("EP2", "F3", "Random sets $W$ and $S$")
MAIN_COPY = clean(sp("The main result of this work is the following correlation inequality", "\\end{equation}", 3600, 3900))
N("RP1", "remark", "$S\\subset W$ almost surely",
  sp("Observe that $S\\subset W$ with probability one", "on the left-hand side."), conf=0.7,
  statement_short="$S\\subset W$ a.s., so conditioning $X_1\\in S$ is more restrictive than $X_1\\in W$.")
N("DP4", "definition", "Maximum of $\\textbf{X}_n$ under the product order",
  sp("For each $i\\in [n]$ the vector $X_i$ is said to be a maximum of", "$\\prec$-dominates $X_i$."),
  conf=0.85, **STD, definiendum=["maximum", "$\\textbf{X}_n$"],
  differentia=["no \\textit{other} vector in $\\textbf{X}_n$ $\\prec$-dominates $X_i$"])
N("DP5", "definition", "Maximum events $E_{i,n}$",
  sp("Define the events \\begin{equation} E_{i,n}", "\\end{equation}"), conf=0.85, definiendum="$E_{i,n}$",
  also_stated_at=[clean(sp("For every $1\\leq i \\leq n$ let $E_{i,n}$ be the event", "in $\\{X_1,\\ldots,X_n\\}$."))])
EQ("EP3", "F5", "Event $E_{i,n}$ that $X_i$ is a maximum")

# ================= 1.1 Related literature =================
LIT = dict(origin="external", origin_citation="standard (uncited)")
N("DP6", "definition", "Finite poset $\\{U_1,\\ldots,U_\\ell\\}$ with partial order $\\prec_1$",
  sp("In this settings, there is a set with $\\ell$ elements", "equipped with a partial order $\\prec_1$."),
  conf=0.8, **LIT, definiendum=["$\\ell$", "$\\prec_1$"])
N("DP7", "definition", "Partial order $\\prec_1$ as a set of pairs",
  sp("With a bit abuse of notation, we may represent $\\prec_1$", "such that $U_i\\prec_1U_j$."),
  conf=0.8, **LIT, definiendum="$\\prec_1$")
N("DP8", "definition", "Uniform random linear extension $\\prec_2$",
  sp("Let $\\prec_2$ be a random linear extension of $\\prec_1$", "all linear extensions of $\\prec_1$."),
  conf=0.8, **LIT, definiendum="$\\prec_2$", genus="random linear extension of $\\prec_1$",
  differentia=["distributed uniformly over the set of all linear extensions of $\\prec_1$"])
N("DP9", "definition", "Ordering event $E_I$",
  sp("In this probability space, for every $I\\subseteq[\\ell]\\times[\\ell]$, define an ordering event", "\\forall(i,j)\\in I\\}$."),
  conf=0.8, **LIT, definiendum="ordering event $E_I$")
N("DP10", "definition", "I.i.d. uniform variables $U_1,\\ldots,U_n$",
  sp("Equivalently, we can assume $n$ i.i.d. continuous uniform random variables", "\\sim U(0,1)$."),
  conf=0.8, **LIT, definiendum="$U_1,U_2,\\ldots,U_n$")
N("DP11", "definition", "Ordering event $\\widetilde{E}_I$ for uniform variables",
  sp("Denote for every $I\\subseteq[\\ell]\\times[\\ell]$ the event $\\widetilde{E}_I", "\\forall(i,j)\\in I\\right\\}$."),
  conf=0.8, **LIT, definiendum="$\\widetilde{E}_I$")
F("TP1", "F6", "theorem", "XYZ inequality", origin="external",
  origin_citation="Shepp 1982; Fishburn 1984",
  assumptions=["Let $\\prec_1$ be a subset of $[\\ell]\\times[\\ell]$ which is representing a partial order"],
  conclusions=[fst("F7")],
  statement_short="Conditioning on the poset plus $U_1<U_3$ does not decrease $P(U_1<U_2)$.")
EQ("EP4", "F7", "XYZ inequality")
N("RP2", "remark", "Natural generalizations of the XYZ inequality fail",
  sp("While Eq. \\eqref{eq:XYZ} seems intuitive", "leads to a false statement."), conf=0.7,
  origin="external", origin_citation="Shepp 1982; Graham 1983; Shepp 1980",
  statement_short="Generalizations of XYZ fail, e.g. $B=\\{(1,3),(3,4)\\}$ with $\\prec_1=\\{(1,3)\\}$.")
N("RP3", "remark", "Three-chain product inequality and its failure for four-chains",
  sp("Another intriguing result is that although Theorem \\ref{thm:XYZ} implies", "P(U_3 < U_4)$."), conf=0.7,
  origin="external", origin_citation="Brightwell 1985",
  statement_short="XYZ gives $P(U_1<U_2<U_3)\\le P(U_1<U_2)P(U_2<U_3)$, but the 4-chain analogue can fail (Brightwell).")
N("RP4", "remark", "Results extend to any continuous marginal distribution",
  sp("Since all events of interest can be expressed in terms of the ranks", "by any continuous distribution."),
  conf=0.7, rigor="semi_formal",
  statement_short="Events depend only on ranks, so the results hold for any continuous marginal, not just $U(0,1)$.")

# ================= 2 A correlation inequality =================
N("DP12", "definition", "Dominance events $B_{ij}$ and $\\overline{B_{ij}}$",
  sp("For every $i, j\\in [n]$ denote $B_{ij}", "\\{ X_i \\not\\prec X_j \\}$."), conf=0.85,
  definiendum=["$B_{ij}$", "$\\overline{B_{ij}}$"])
F("TP2", "F8", "theorem", "Correlation inequality for random points in a hypercube", main=True,
  also_stated_at=[MAIN_COPY],
  assumptions=[clean(sp("Let $X_1,X_2,\\ldots,X_n$ ($n\\geq3$) be i.i.d.", "on $[0,1]^ k$"))],
  conclusions=[fst("F9")],
  statement_short="Given $X_1$ is undominated by $X_3..X_n$, $X_2$ is less likely undominated than when $X_1$ dominates all of them.")
EQ("EP5", "F9", "Correlation inequality in dominance events")

P1 = FACT["F10"]
N("PP1", "proof", "Proof of Theorem 2", fs("F10"), conf=1.0,
  proof_strategy=["direct", "induction", "algebraic_manipulation"],
  statement_short="Condition on $x_1,x_2$, factorize over $j$ and reduce to $G(x_2;x_1)\\ge0$ on a box. G is linear in each coordinate, so its minimum is at the boundary, handled by induction on zero coordinates.")
for eid, fid, nm in [("EP6", "F11", "Pointwise inequality given $x_{[2]}$"),
                     ("EP7", "F12", "Product form over $j$"),
                     ("EP8", "F13", "Power form by symmetry"),
                     ("EP9", "F14", "One-vector inequality"),
                     ("EP10", "F15", "Box volumes for the events"),
                     ("EP11", "F96", "Box volume for $\\overline{B_{23}}\\cap B_{31}$"),
                     ("EP12", "F16", "Inequality after substitution"),
                     ("EP13", "F17", "Inequality after cancelling common terms"),
                     ("EP14", "F18", "Definition of $G(x_2;x_1)$"),
                     ("EP15", "F19", "$G\\ge0$ when $x_{2i}=x_{1i}$"),
                     ("EP16", "F20", "$G(\\bm{0_k};x_1)=0$"),
                     ("EP17", "F21", "Coordinate function $G_{x_{2[-i]},x_1}(y)$"),
                     ("EP18", "F22", "Minimum of linear function at endpoints"),
                     ("EP19", "F23", "Base case: $k-1$ zero coordinates"),
                     ("EP20", "F24", "Induction step bound"),
                     ("EP21", "F25", "Interior bound")]:
    EQ(eid, fid, nm)
lo, hi = P1["start"], P1["end"]
STEPS("PP1", [
    ("PSP1", "Reduce to a pointwise inequality given $x_1,x_2$", "Let $x_1, x_2 \\in", "integration over $x_{[2]}$.",
     "setup", "Fix $x_1,x_2$; it suffices to prove the inequality conditionally on them and integrate."),
    ("PSP2", "Factorize over $j$ and use symmetry", "Due to the conditioning on $x_{[2]}$", "\\end{equation}",
     "algebraic_manipulation", "Given $x_{[2]}$ the events for $j\\ge3$ are independent and identical: both sides become $(n-2)$-th powers."),
    ("PSP3", "Reduce to one extra vector", "Hence, it is enough to prove:", "\\end{equation}",
     "setup", "It suffices to prove the inequality for a single vector $X_3$."),
    ("PSP4", "Compute the box probabilities", "In order to compute the probabilities of each of the events above", "\\end{align}",
     "invoke_identity", "Express each probability as a volume of boxes via inclusion-exclusion."),
    ("PSP5", "Substitute the volumes", "Thus, an insertion of the probabilities", "\\end{align}",
     "substitute", "Insert the volumes into the one-vector inequality."),
    ("PSP6", "Cancel common terms", "Then, subtraction of the common terms", "\\end{equation}",
     "algebraic_manipulation", "Cancel common terms to get an indicator-weighted inequality."),
    ("PSP7", "Case $x_2\\not\\prec x_1$", "When $ x_2\\not\\prec x_1$, the left-hand side is zero", "always non-negative.",
     "case_split", "If $x_2\\not\\prec x_1$ the left side vanishes and the inequality holds."),
    ("PSP8", "Case $x_2\\prec x_1$: define $G$ and plan", "When $x_2\\prec x_1$, it is left to show that:", "also in the interior.",
     "case_split", "If $x_2\\prec x_1$, show $G(x_2;x_1)\\ge0$ on the box $\\times_i[0,x_{1i}]$: boundary first, then interior."),
    ("PSP9", "Faces $x_{2i}=x_{1i}$", "First, if $x_{2i} = x_{1i}$ for some", "\\end{equation}",
     "bound_estimate", "On faces $x_{2i}=x_{1i}$ the subtracted term vanishes, so $G\\ge0$."),
    ("PSP10", "Vertex at the origin", "Next, if $\\textbf{0}_k$ is the zero-vector", "\\end{equation}",
     "substitute", "At $x_2=0$, $G=0$."),
    ("PSP11", "Coordinate restriction of $G$", "For every $i \\in [k]$ let $x_{2 [-i]}", "\\end{equation}",
     "introduce_variable", "Define $G$ as a function of the single coordinate $y=x_{2i}$."),
    ("PSP12", "Linearity gives endpoint minimum", "Then, Eq. \\eqref{eq:G_volume_x1_x2} implies that $G_{x_{2 [-i]},x_1}(\\cdot)$ is a linear function", "\\end{equation}",
     "bound_estimate", "$G$ is linear in each coordinate, so its minimum on an interval is at an endpoint."),
    ("PSP13", "Base case: $k-1$ zero coordinates", "In particular, Eqs. \\eqref{eq:boundary_one} and \\eqref{eq:boundary_zero} yield that", "with at least $k-1$ zero coordinates.",
     "induction_step", "With $k-1$ zero coordinates the endpoint values are $\\ge0$, so $G\\ge0$."),
    ("PSP14", "Induction on the number of zero coordinates", "We next continue by induction.", "the boundary of the box $\\bigtimes\\limits_{i=1}^k [0, x_{1i}]$.",
     "induction_step", "Induct on the number of zero coordinates to get $G\\ge0$ on the whole boundary."),
    ("PSP15", "Interior and conclusion", "Next, for any $x_{2 [-i]} \\in \\bigtimes\\limits_{j=1, j \\neq i}^k [0, x_{1j}]$ and any $y", "depth-0.1ex \\newline\\newline",
     "conclude", "Endpoint minimum with nonnegative boundary gives $G\\ge0$ on the whole box."),
], lo, hi)

# ================= 2.1 Conjecture =================
F("OpenP1", "F26", "open_problem", "General conditions for the CNF-DNF correlation inequality", conf=0.9,
  statement_short="For which families $F_t,H_s$ of pairs does conditioning on an AND of ORs vs an AND of ANDs of order events preserve the inequality?")
EQ("EP22", "F27", "CNF-DNF correlation inequality")
F("RP5", "F28", "remark", "XYZ inequality as a special case of the CNF-DNF inequality",
  statement_short="Choosing $H_i$ from the poset relations plus $\\{(1,3)\\}$ and $F_1=\\{(1,2)\\}$ recovers the XYZ inequality.")
F("RP6", "F29", "remark", "Theorem 2 as a special case of the CNF-DNF inequality",
  statement_short="Encoding each $X_i$ by $k$ consecutive uniforms makes Theorem 2 an instance of the CNF-DNF inequality with $T=S=n-2$.")
EQ("EP23", "F30", "$B_{ij}$ as an intersection of coordinate events")
EQ("EP24", "F31", "Sets $F_t,H_s$ encoding Theorem 2")
F("RP7", "F32", "remark", "Counterexample to the general CNF-DNF inequality",
  statement_short="With $\\ell=4$, $T=S=2$ the inequality becomes $P(U_1<U_4|U_1<U_3)\\le P(U_1<U_4|U_1,U_2<U_3)$, which fails: $5/8<8/12$.")
EQ("EP25", "F33", "Set choices of the counterexample")
EQ("EP26", "F34", "Reduced counterexample inequality")
F("CnjP1", "F35", "conjecture", "Unique-vertex-per-clause CNF-DNF inequality",
  assumptions=["Assume that $U_1,..,U_k, U_{k+1},..,U_{2k}, U_{2k+1},...,U_{n} \\sim U(0,1)$ are i.i.d. uniform random variables",
               clean(sp("Let $F_1,..,F_T \\subset [k] \\times", "\\forall t \\in [T]$")),
               clean(sp("Suppose that $\\sum\\limits_{j=1}^m \\indicatorpar{(i,j) \\in F_t} \\leq 1", "t \\in [T]$.", 22681, 23298))[len("Suppose that "):-1]],
  conclusions=["the inequality \\eqref{eq:CNF_DNF_inequality} holds"],
  statement_short="If first indices of $F_t$ and $H_t$ come from disjoint blocks, each appears once per set, and all sets have size $m$, the CNF-DNF inequality holds.")
N("ClP1", "claim", "Numerical verification of Conjecture 1",
  sp("Conjecture \\ref{conj:unique_vertex_in_each_clause} was checked numerically", "T \\leq 3$."), conf=0.8,
  rigor="numerical",
  also_stated_at=[clean(sp("The next command was used to verify Conjecture", "failing to find a counter-example among them:"))],
  conclusions=[clean(sp("Conjecture \\ref{conj:unique_vertex_in_each_clause} was checked numerically", "T \\leq 3$"))],
  statement_short="Exhaustive search verified Conjecture 1 for $n\\le12$, $m\\le4$, $T\\le3$.")
N("RP8", "remark", "The three restrictions in Conjecture 1",
  sp("Three restrictions are imposed on the $F_t, H_t$ sets in the above conjecture", "are fixed at $m$."), conf=0.75,
  statement_short="The conjecture's hypotheses: three index blocks, each first index at most once per set, all sets of size $m$.")
N("ClP2", "claim", "Necessity of the three restrictions", sp("All three conditions are necessary.", "necessary."),
  conf=0.7, rigor="numerical", conclusions=["All three conditions are necessary."])
N("ExP1", "example", "Counterexample with sets $H_t$ of different sizes",
  sp("For example, if we allow sets $H_t$", "= \\frac{336}{840} = 0.4. \\end{align}"), conf=0.8,
  statement_short="With $|H_1|=1$, $|H_2|=2$ the inequality fails: $861/2100=0.41>336/840=0.4$.")
EQ("EP27", "F36", "Counterexample sets $F_t,H_t$")
EQ("EP28", "F37", "Exact probabilities violating the inequality")

# ================= 2.1.1 Computations =================
N("AP1", "algorithm", "Exhaustive permutation counting check of the CNF-DNF inequality",
  sp("We have developed a computational pipeline for checking whether", "specified by $F_t, H_s$."), conf=0.75,
  input=["the partial ordering events specified by $F_t, H_s$"],
  statement_short="Decide whether the CNF-DNF inequality holds for given sets by exhaustively counting consistent permutations.")
N("TP3", "theorem", "#P-completeness of counting linear extensions",
  sp("For a general partial order, it was shown in \\cite{brightwell1991counting}", "is $\\#P$-complete."),
  conf=0.9, origin="external", origin_citation="Brightwell & Winkler 1991",
  assumptions=["For a general partial order"],
  conclusions=["counting the number of linear extensions is $\\#P$-complete"])
N("ClP3", "claim", "Number of linear extensions of a chain",
  sp("For some specific cases the computation might be easier", "by symmetry."), conf=0.7, **STD,
  assumptions=["a partial order given by a chain over $m \\leq n$ variables"],
  conclusions=["is $\\frac{n!}{m!}$ by symmetry"],
  statement_short="A chain on $m$ of $n$ variables has $n!/m!$ linear extensions.")
N("RP9", "remark", "Randomized approximate counting as a filter",
  sp("There are known polynomial randomized approximation algorithms", "provides evidence for a violation of the inequality."),
  conf=0.7,
  statement_short="Approximate counting (Dyer et al.) needs error below $1/n!$, or can serve as a filter before exact counting.")
N("AP2", "algorithm", "Python checker and counterexample search for the CNF-DNF inequality",
  sp("The above techniques are implemented in a python code", "of given sizes."), conf=0.75,
  input=["a particular set collection $\\{F_1,..,F_T ; H_1, .., H_S\\}$"],
  statement_short="Check the inequality for one set collection, or search for counterexamples by sampling or exhaustive enumeration of collections.")
lo2 = SRC.find("The above techniques are implemented in a python code")
STEPS("AP2", [
    ("ASP1", "Check one set collection", "checking whether the inequality \\eqref{eq:CNF_DNF_inequality} holds for a particular set collection",
     "H_1, .., H_S\\}$", "test", "Test the inequality for a given collection by exact counting."),
    ("ASP2", "Search for counterexamples", "finding putative counter-example by either sampling", "of given sizes",
     "select", "Search over collections, by random sampling or exhaustive enumeration of given sizes, for a violation."),
], lo2, lo2 + 600, kind="algorithm_step")
for n in nodes:
    if n["id"] in ("ASP1", "ASP2"):
        n["confidence"] = 0.7

# ================= 3.1 Asymptotic independence =================
T3 = FACT["F38"]
F("TP4", "F38", "theorem", "Asymptotic independence of two maxima events", main=True,
  assumptions=[clean(sp("Let $X_1,X_2,\\ldots,X_n$ ($n\\geq3$) be i.i.d.", "on $[0,1]^ k$")), "$k\\geq1$", "$k>1$"],
  conclusions=[fst("F40"), fst("F41"), fst("F42")],
  parts=[{"assumptions": ["$k\\geq1$"], "conclusions": [fst("F40")]},
         {"assumptions": ["$k>1$"], "conclusions": [fst("F41"), fst("F42")]}],
  statement_short="Exact alternating-sum formula for $e_n=P(E_{1,n}\\cap E_{2,n})$; for $k>1$, $e_n\\sim p_n^2$ and the correlation is $o(\\log^{k-1}n/n)$.")
EQ("EP29", "F39", "Definitions of $p_n$ and $e_n$")
EQ("EP30", "F40", "Exact formula for $e_n$")
EQ("EP31", "F41", "Asymptotics $e_n\\sim p_n^2$")
EQ("EP32", "F42", "Correlation $\\rho_{k,n}=o(\\log^{k-1}n/n)$")
F("RP10", "F43", "remark", "Suppression of the dimension $k$ in notation")
N("TP5", "theorem", "Exact formula and asymptotics of $P(X_1$ is a maximum$)$",
  SRC[SRC.find("Specifically, it is well-known"):FACT["F45"]["outer_end"]],
  conf=0.9, origin="external", origin_citation="O'Neill 1981 (Theorems 3 and 4)",
  conclusions=[fst("F44"), fst("F45")],
  statement_short="$p_n=\\sum_u\\binom{n-1}{u-1}(-1)^{u-1}u^{-k}$ and $p_n\\sim\\log^{k-1}n/(n(k-1)!)$.")
EQ("EP33", "F44", "Combinatorial formula for $p_n$")
EQ("EP34", "F45", "First-order asymptotics of $p_n$")
N("TP6", "theorem", "Variance of the number of maxima",
  sp("The main result of \\cite{bai1998variance} implies that", "\\end{equation}"), conf=0.9,
  origin="external", origin_citation="Bai, Chao, Hwang & Liang 1998",
  assumptions=["for every $k>1$"], conclusions=[fst("F46")],
  statement_short="The variance of the number of maxima is $\\sim C_k\\log^{k-1}n$.")
EQ("EP35", "F46", "Variance asymptotics of the number of maxima")
N("PP2", "proof", "Alternative proof of Theorem 3(2) from known results",
  sp("Thus, because \\begin{align} \\text{Var}", "=1\\,. \\end{equation}"), conf=0.75,
  statement_short="Write the variance of the number of maxima via $p_n$ and $e_n$; known asymptotics of $p_n$ and of the variance force $e_n/p_n^2\\to1$.")
EQ("EP36", "F47", "Variance decomposition of the number of maxima")
EQ("EP37", "F48", "Limit $e_n/p_n^2\\to1$")

# ================= 3.2 A limit theorem =================
N("DP13", "definition", "Triangular array of random points $X_1^n,\\ldots,X_{m_n}^n$",
  sp("In this part, we consider a sequence of models:", "the unit hypercube $[0,1]^k$."), conf=0.8,
  definiendum="$X_1^n,X_2^n,\\ldots,X_{m_n}^n$")
N("DP14", "definition", "Maximum events $E_{i,n}$ and indicators $Z_{ni}$ in the triangular array",
  sp("For every $n\\in\\mathbb{N}$ and $i\\in[m_n]$ denote the event", "Z_{ni}\\equiv \\indicator{E_{i,n}}$."), conf=0.85,
  definiendum=["$E_{i,n}$", "$Z_{ni}$"])
EQ("EP38", "F49", "Event $E_{i,n}$ in the triangular array")
F("TP7", "F50", "theorem", "LLN and CLTs for partial sums of Pareto-maxima indicators", main=True,
  assumptions=["If $m_n=n$ for every $n\\in\\mathbb{N}$",
               clean(sp("Let $(m_n)_{n=1}^\\infty$ be a sequence of positive integers such that", "assume that $k>1$")),
               "For any $k > 1$"],
  conclusions=[fst("F51"), fst("F53"), fst("F54"), fst("F55")],
  parts=[{"assumptions": ["If $m_n=n$ for every $n\\in\\mathbb{N}$"], "conclusions": [fst("F51")]},
         {"assumptions": [clean(sp("Let $(m_n)_{n=1}^\\infty$ be a sequence of positive integers such that", "assume that $k>1$"))],
          "conclusions": [fst("F53")]},
         {"assumptions": ["For any $k > 1$"], "conclusions": [fst("F54"), fst("F55")]}],
  statement_short="(1) $L^2$ LLN for the number of maxima; (2) CLT for full minus partial normalized sums when $n/m_n\\to\\gamma$; (3) CLT for a partial sum for some $n\\ll m_n\\ll n\\log^k n$.")
EQ("EP39", "F51", "$L^2$ law of large numbers for the number of maxima")
EQ("EP40", "F52", "Standardized indicators $U_{ni}$")
EQ("EP41", "F53", "CLT for the difference of normalized sums")
EQ("EP42", "F54", "Growth window $n\\ll m_n\\ll n\\log^k n$")
EQ("EP43", "F55", "CLT for the partial sum")
F("RP11", "F56", "remark", "Pareto-front interpretation of Theorem 4",
  statement_short="The set of maxima is the Pareto front; Theorem 4 gives an LLN for its size and CLTs for partial Pareto fronts.")
F("RP12", "F57", "remark", "Relation to the CLT of Bai et al. for the number of maxima",
  statement_short="The partial-sum CLTs neither follow from nor clearly imply the CLT of Bai et al. for the full sum.")

# ================= 3.3 Proofs =================
F("LP1", "F58", "lemma", "Size-biased mean of exchangeable Bernoulli sums",
  assumptions=["Let $W_1,..,W_n$ be exchangeable random variables such that $W_1\\sim\\text{Ber}(p)$ for some $p\\in(0,1)$",
               "denote $W\\equiv\\sum\\limits_{j=1}^nW_j$"],
  conclusions=[fst("F59")],
  statement_short="For exchangeable Bernoulli($p$) variables, conditioning on $W_1=1$ raises the mean of their sum to at least $np$.")
EQ("EP44", "F59", "$\\mathbb{E}(W|W_1=1)\\geq np$")
F("PP3", "F60", "proof", "Proof of Lemma 1", proof_strategy=["direct", "algebraic_manipulation"],
  statement_short="Bayes' rule with exchangeability gives $\\mathbb{E}(W|W_1=1)=\\mathbb{E}W^2/\\mathbb{E}W$; Jensen/Cauchy-Schwarz bounds it below by $\\mathbb{E}W$.")
EQ("EP45", "F61", "Size-biased mean computation")

# Proof of Theorem 3 (prose, fills subsubsection*)
a3 = SRC.find("\\begin{enumerate}", 35253)
b3 = SRC.find("\\end{enumerate}", 42400) + len("\\end{enumerate}")
N("PP4", "proof", "Proof of Theorem 3", SRC[a3:b3], conf=0.9,
  proof_strategy=["direct", "algebraic_manipulation", "probabilistic"],
  statement_short="Part 1: condition on $X_1,X_2$, expand the integrand by the multinomial theorem and integrate coordinatewise. Part 2: squeeze $e_n/p_n^2$ between a lower bound from Lemma 1 and an upper bound from Theorem 2 with inclusion-exclusion.")
for eid, fid, nm in [("EP46", "F62", "Integral representation of $e_n$"),
                     ("EP47", "F63", "Probability $X_3$ dominates neither point"),
                     ("EP48", "F64", "Multinomial expansion and integration of $e_n$"),
                     ("EP49", "F65", "Conditional mean of the number of maxima"),
                     ("EP50", "F66", "Lower bound on $e_n/p_n^2$"),
                     ("EP51", "F67", "Upper bound on $e_n$ via Theorem 2"),
                     ("EP52", "F68", "Conditional dominance probability $((n-1)/(nu))^k$"),
                     ("EP53", "F70", "$(e_n-p_n^2)$ normalized limit"),
                     ("EP54", "F71", "$e_n-p_n^2=o(p_n^2)$"),
                     ("EP55", "F72", "Correlation formula $\\rho_{k,n}$")]:
    EQ(eid, fid, nm)
STEPS("PP4", [
    ("PSP16", "Part 1: exact formula for $e_n$", "\\item For every $i\\in[n]$ and $j\\in[k]$ let $X_{ij}$", "(a+b+c+2)^k} \\ . \\end{align}",
     "conclude", "Prove the exact formula for $e_n$.", None, 0.95),
    ("PSP20", "Part 2: squeezing $e_n/p_n^2$ and the correlation", "\\item The proof of Eq. \\eqref{eq:e_k,n approx} will follow", "Eq. \\eqref{eq:little o rho} follows.\\hfill \\vrule height1.3ex width1.2ex depth-0.1ex",
     "conclude", "Prove $e_n\\sim p_n^2$ by a squeeze, then deduce the correlation bound.", None, 0.95),
], a3, b3)
STEPS("PP4", [
    ("PSP17", "Coordinates and conditioning on $X_1,X_2$", "For every $i\\in[n]$ and $j\\in[k]$ let $X_{ij}$", "\\end{align}",
     "introduce_variable", "Introduce coordinates and condition on $X_1,X_2$ to write $e_n$ as an integral of an $(n-2)$-th power.", "PSP16"),
    ("PSP18", "Inclusion-exclusion for one point", "The probabilities that appear inside the integral above are as follows:", "\\end{align}",
     "invoke_identity", "Inclusion-exclusion gives the probability that $X_3$ dominates neither point.", "PSP16"),
    ("PSP19", "Multinomial expansion and coordinatewise integration", "Thus, using the multinomial theorem deduce that", "(a+b+c+2)^k} \\ . \\end{align}",
     "algebraic_manipulation", "Expand the power multinomially and integrate each coordinate in closed form.", "PSP16"),
    ("PSP21", "Squeezing argument", "The proof of Eq. \\eqref{eq:e_k,n approx} will follow from the next squeezing argument.", "squeezing argument.",
     "setup", "Plan: squeeze $e_n/p_n^2$ between bounds tending to one.", "PSP20"),
    ("PSP22", "Lower bound via Lemma 1", "Applying Lemma \\ref{lemma:exchangalble_monotone} to the indicator", "the lower bound tends to one as $n\\to\\infty$.",
     "apply_lemma", "Lemma 1 on the maxima indicators gives $e_n/p_n^2\\ge n/(n-1)-1/((n-1)p_n)\\to1$.", "PSP20", 0.95),
    ("PSP23", "Upper bound via Theorem 2", "Next we prove that there exists an upper bound", "the upper bound above tends to one as $n\\to\\infty$.",
     "bound_estimate", "Drop constraints, apply Theorem 2 and inclusion-exclusion, evaluate by symmetry: the upper bound tends to one.", "PSP20", 0.95),
    ("PSP29", "Correlation is $o(\\log^{k-1}n/n)$", "Once we have established the proof of Eq. \\eqref{eq:e_k,n approx}", "Eq. \\eqref{eq:little o rho} follows.\\hfill \\vrule height1.3ex width1.2ex depth-0.1ex",
     "conclude", "From $e_n-p_n^2=o(p_n^2)$ and $\\rho=(e_n-p_n^2)/(p_n(1-p_n))$ deduce the correlation bound.", "PSP20"),
], a3, b3)
STEPS("PP4", [
    ("PSP24", "Bound $e_n$ by a conditional probability", "To this end, observe that \\begin{align} e_n &= P\\left(\\bigcap_{i=1}^2", "\\end{align}",
     "bound_estimate", "Relax the event and apply Theorem 2 to bound $e_n$ by $p_{n-1}$ times a conditional probability, expanded by inclusion-exclusion.", "PSP23"),
    ("PSP25", "Justification of the bound", "The second inequality above follows from Theorem", "with an inclusion-exclusion principle.",
     "apply_lemma", "The inequality is Theorem 2; the expansion is De Morgan plus inclusion-exclusion.", "PSP23"),
    ("PSP26", "Evaluate the conditional probability by symmetry", "The next step is to evaluate the probability", "\\end{align}",
     "invoke_identity", "By symmetry across coordinates the conditional probability is $((n-1)/(nu))^k$.", "PSP23"),
    ("PSP27", "Plug in and use the binomial theorem", "Plugging Eq. \\eqref{eq:cond_prob_upperbound_evaluation} into", "\\end{align}",
     "substitute", "Substitute and use the formula for $p_n$ to rewrite the upper bound.", "PSP23"),
    ("PSP28", "Upper bound tends to one", "Finally, $np_n\\rightarrow\\infty$ and $p_{k,n-1}/p_n\\rightarrow1$", "tends to one as $n\\to\\infty$.",
     "conclude", "Since $np_n\\to\\infty$ and $p_{n-1}/p_n\\to1$ the upper bound tends to one.", "PSP23"),
], SRC.find("Next we prove that there exists an upper bound"), b3)
# fix: the first "Next we prove" sentence belongs to PSP24
for n in nodes:
    if n["id"] == "PSP24":
        n["statement"] = clean(sp("Next we prove that there exists an upper bound", "\\end{align}", a3, b3))

# Lemma 2 and proof
F("LP2", "F73", "lemma", "$L^2$ law of large numbers for squared standardized indicators",
  assumptions=["$np_{m_n}\\rightarrow\\infty$ as $n\\to\\infty$"], conclusions=[fst("F74")],
  statement_short="If $np_{m_n}\\to\\infty$, the mean of the first $n$ squared standardized maxima indicators tends to 1 in $L^2$.")
EQ("EP56", "F74", "$\\frac1n\\sum U_{ni}^2\\to1$ in $L^2$")
P5 = FACT["F75"]
F("PP5", "F75", "proof", "Proof of Lemma 2", proof_strategy=["direct", "algebraic_manipulation"],
  statement_short="Compute $EU^4$ and $EU_{n1}^2U_{n2}^2$; with Theorem 3 the variance of the average vanishes while its mean is 1.")
for eid, fid, nm in [("EP57", "F76", "Fourth moment of $U_{n1}$"),
                     ("EP58", "F77", "$EU_{n1}^4/n\\to0$"),
                     ("EP59", "F78", "Mixed moment $EU_{n1}^2U_{n2}^2$"),
                     ("EP60", "F79", "$EU_{n1}^2U_{n2}^2\\to1$"),
                     ("EP61", "F80", "Variance of the average of $U_{ni}^2$"),
                     ("EP62", "F81", "Variance of the average tends to 0")]:
    EQ(eid, fid, nm)
STEPS("PP5", [
    ("PSP30", "Fourth moment", "By definition $U_{ni}^2=", "\\end{align}",
     "algebraic_manipulation", "Compute $EU_{n1}^4$ from the Bernoulli law."),
    ("PSP31", "Fourth moment is $o(n)$", "Thus, the assumption that", "\\end{equation}",
     "bound_estimate", "Since $np_{m_n}\\to\\infty$, $EU_{n1}^4/n\\to0$."),
    ("PSP32", "Mixed fourth moment", "Similarly, \\begin{align} EU_{n1}^2U_{n2}^2", "\\end{align}",
     "algebraic_manipulation", "Express $EU_{n1}^2U_{n2}^2$ through $e_{m_n}$ and $p_{m_n}$."),
    ("PSP33", "Apply Theorem 3", "Using Theorem \\ref{thm:asymptotic independence} and recalling that", "\\end{equation}",
     "apply_lemma", "Theorem 3 gives $e_{m_n}/p_{m_n}^2\\to1$, so the mixed moment tends to 1."),
    ("PSP34", "Variance of the average vanishes", "In addition, standard calculations yield that", "\\rightarrow0\\ \\ \\text{as}\\ \\ n\\to\\infty\\,. \\end{equation}",
     "bound_estimate", "Decompose the variance of the average; both terms vanish."),
    ("PSP35", "Conclude $L^2$ convergence", "Finally, the result follows since for each", "depth-0.1ex\\newline",
     "conclude", "Mean 1 and vanishing variance give $L^2$ convergence to 1."),
], P5["start"], P5["end"])

# Proof of Theorem 4 (prose, fills subsubsection*)
a4 = SRC.find("\\begin{enumerate}", 45215)
b4 = SRC.find("\\end{enumerate}", 51150) + len("\\end{enumerate}")
N("PP6", "proof", "Proof of Theorem 4", SRC[a4:b4], conf=0.9,
  proof_strategy=["direct", "construction"],
  statement_short="Part 1 from Lemma 2; parts 2 and 3 verify the conditions of Weber's CLTs for exchangeable triangular arrays. For part 3, $m_n$ is constructed from a rate function $g$ for the correlation.")
for eid, fid, nm in [("EP63", "F82", "LLN for $U_{ni}^2$ with $m_n=n$"),
                     ("EP64", "F83", "LLN in terms of $Z_{ni}$"),
                     ("EP65", "F84", "$np_{m_n}\\to\\infty$ when $n/m_n\\to\\gamma$"),
                     ("EP66", "F85", "$EU_{n1}U_{n2}=\\rho_{k,m_n}\\to0$"),
                     ("EP67", "F86", "Max condition $n^{-1/2}\\max|U_{ni}|\\to0$"),
                     ("EP68", "F87", "LLN for $U_{ni}^2$ (part 2)"),
                     ("EP69", "F88", "Choice of $m_n$"),
                     ("EP70", "F89", "$n|\\rho_{k,m_n}|\\to0$"),
                     ("EP71", "F90", "Lower bound on $n$ from minimality of $m_n$"),
                     ("EP72", "F91", "$np_{m_n}\\to\\infty$ (part 3)"),
                     ("EP73", "F92", "Max condition (part 3)"),
                     ("EP74", "F93", "LLN for $U_{ni}^2$ (part 3)"),
                     ("EP75", "F94", "$n/m_n\\to0$"),
                     ("EP76", "F95", "Upper growth bound on $m_n$")]:
    EQ(eid, fid, nm)
it1 = SRC.find("\\item For $k=1$", a4)
it2 = SRC.find("\\item $\\left\\{U_{ni}", a4)
it3 = SRC.find("\\item \nSince $\\rho_{k,n} =", a4)
assert min(it1, it2, it3) > 0
STEPS("PP6", [
    ("PSP36", "Part 1: law of large numbers", "\\item For $k=1$, the proof is immediate.", "because $p_n\\rightarrow0$ as $n\\to\\infty$.",
     "conclude", "Prove the $L^2$ LLN via Lemma 2.", None, 0.95),
    ("PSP40", "Part 2: CLT for differences via Weber's Theorem 2", "\\item $\\left\\{U_{ni};n\\geq1", "pre-condition of Theorem 2 in \\cite{weber1980martingale} follows.",
     "conclude", "Verify the conditions of Weber's Theorem 2.", None, 0.95),
    ("PSP47", "Part 3: CLT for a partial sum via Weber's Corollary 1", "Since $\\rho_{k,n} = o\\left(", "completing the proof of the theorem. \\hfill \\vrule height1.3ex width1.2ex depth-0.1ex",
     "conclude", "Construct $m_n$ and verify the four conditions of Weber's Corollary 1.", None, 0.95),
], a4, b4)
STEPS("PP6", [
    ("PSP37", "Case $k=1$ and setup for $k>1$", "For $k=1$, the proof is immediate.", "for every $n\\geq1$.",
     "case_split", "$k=1$ is immediate; assume $k>1$ and $m_n=n$.", "PSP36"),
    ("PSP38", "Apply Lemma 2", "Then by Eq. \\eqref{eq:little o rho}, $n\\rho_{k,m_n}", "\\end{equation}",
     "apply_lemma", "Check the growth condition and apply Lemma 2.", "PSP36"),
    ("PSP39", "Rewrite in terms of $Z_{ni}$", "Since $Z_{ni}^2=Z_{ni}$ for each", "because $p_n\\rightarrow0$ as $n\\to\\infty$.",
     "conclude", "Use $Z^2=Z$ and $p_n\\to0$ to get the LLN for $\\sum Z_{ni}$.", "PSP36"),
], it1, it2)
STEPS("PP6", [
    ("PSP41", "Exchangeable standardized triangular array", "$\\left\\{U_{ni};n\\geq1, i\\in [m_n]\\right\\}$ is a triangular array", "for every $n\\geq1$, $ i\\in [n]$.",
     "setup", "The $U_{ni}$ form a row-exchangeable triangular array with mean 0 and variance 1.", "PSP40"),
    ("PSP42", "Reduce to Weber's conditions", "Thus, in order to complete the proof, it is left to verify", "are satisfied.",
     "setup", "It remains to check the hypotheses of Weber's Theorem 2.", "PSP40"),
    ("PSP43", "$np_{m_n}\\to\\infty$", "To this end, recall that $\\frac{n}{m_n}\\rightarrow\\gamma", "\\end{equation}",
     "bound_estimate", "With $n/m_n\\to\\gamma$ and the asymptotics of $p_n$, $np_{m_n}\\to\\infty$.", "PSP40"),
    ("PSP44", "(a) Vanishing correlation", "\\item Eq. \\eqref{eq:little o rho} yields that", "\\end{equation}",
     "apply_lemma", "Theorem 3 gives $EU_{n1}U_{n2}\\to0$.", "PSP40", 0.95),
    ("PSP45", "(b) Max condition", "\\item Since $p_{m_n}\\rightarrow0$ as $n\\to\\infty$, then", "\\end{equation}",
     "bound_estimate", "$n^{-1/2}\\max|U_{ni}|\\le(np_{m_n})^{-1/2}\\to0$.", "PSP40", 0.95),
    ("PSP46", "(c) LLN for squares", "\\item Due to Eq. \\eqref{eq:np_km to infinity}, it is possible to apply Lemma", "pre-condition of Theorem 2 in \\cite{weber1980martingale} follows.",
     "apply_lemma", "Lemma 2 gives $\\frac1n\\sum U_{ni}^2\\to1$ in probability.", "PSP40", 0.95),
], it2, it3)
STEPS("PP6", [
    ("PSP48", "Rate function $g$", "Since $\\rho_{k,n} = o\\left(", "\\log^{k-1} (n')}$).",
     "introduce_variable", "Choose a decreasing $g\\to0$ with $|\\rho_{k,n}|\\le g(n)\\log^{k-1}n/n$.", "PSP47"),
    ("PSP49", "Define $m_n$", "Then, for each $n\\in\\mathbb{N}$, define", "note that $m_n<\\infty$.",
     "introduce_variable", "Define $m_n$ as the least $m$ with $n<m/(\\log^{k-1}m\\max(\\sqrt{g(m)},1/\\sqrt{\\log m}))$.", "PSP47"),
    ("PSP50", "Reduce to Weber's Corollary 1", "The proof will follow by verifying that the following four pre-conditions", "are satisfied.",
     "setup", "It remains to verify four conditions of Weber's Corollary 1.", "PSP47"),
    ("PSP51", "(a) $n\\rho_{k,m_n}\\to0$", "\\item First, \\eqref{eq:n_vs_m_n} and the definition of $g(n)$", "\\end{align}",
     "bound_estimate", "The choice of $m_n$ gives $n|\\rho_{k,m_n}|\\le\\min(\\sqrt g, g\\sqrt{\\log m_n})\\to0$.", "PSP47", 0.95),
    ("PSP52", "(b) $np_{m_n}\\to\\infty$ and max condition", "\\item Next, the definition of $m_n$ yields that", "\\underset{n\\to\\infty}{\\longrightarrow} 0 . \\end{equation}",
     "bound_estimate", "Minimality of $m_n$ and the asymptotics of $p_n$ give $np_{m_n}\\to\\infty$, hence the max condition.", "PSP47", 0.95),
    ("PSP53", "(c) LLN for squares", "\\item By Eq. \\eqref{eq:n_p_k_m_n_to_infty}, $n p_{m_n}", "implies convergence in probability.",
     "apply_lemma", "Lemma 2 gives the LLN for $U_{ni}^2$.", "PSP47", 0.95),
    ("PSP54", "(d) $n/m_n\\to0$", "\\item Finally, \\begin{equation} \\frac{n}{m_n}", "\\end{equation}",
     "bound_estimate", "The definition of $m_n$ gives $n/m_n\\to0$.", "PSP47", 0.95),
    ("PSP55", "Apply Weber's Corollary 1", "Since the above four conditions are satisfied", "Eq. \\eqref{eq:CLT_partial_sum} holds.",
     "apply_lemma", "Weber's Corollary 1 yields the CLT for the partial sum."),
    ("PSP56", "Growth window for $m_n$", "By condition \\eqref{eq:n_m_n_ratio_to_zero} above, $n \\ll m_n$.", "completing the proof of the theorem. \\hfill \\vrule height1.3ex width1.2ex depth-0.1ex",
     "conclude", "Show $n\\ll m_n<c'n\\log^{k-1}n$, hence $m_n\\ll n\\log^k n$.", "PSP47"),
], it3, b4)
for n in nodes:
    if n["id"] in ("PSP16", "PSP20", "PSP36", "PSP40", "PSP47"):
        n["subclass"] = "other"
    if n["id"] == "PSP55":
        n["parent_id"] = "PSP47"
# renumber step_order per parent in source order
pos = {n["id"]: SRC.find(n["statement"][:60]) for n in nodes}
for n in nodes:
    if n["type"] in ("proof_step", "algorithm_step"):
        n["_pos"] = SRC.find(n["statement"][:80].split(" \\begin")[0]) if False else 0
kids = {}
for n in nodes:
    if n["type"] in ("proof_step", "algorithm_step"):
        kids.setdefault(n["parent_id"], []).append(n)
norm = clean(SRC)
for pid, ks in kids.items():
    ks.sort(key=lambda n: (norm.find(n["statement"]), -len(n["statement"])))
    for i, n in enumerate(ks, 1):
        n["step_order"] = i
for n in nodes:
    n.pop("_pos", None)

# ================= EDGES =================
# definitions -> users (term)
for t in ["DP2", "DP3", "DP4", "DP12"]:
    E("DP1", t, 0.8)
for t in ["DP6", "DP7", "TP1", "OpenP1", "CnjP1"]:
    E("DP1", t, 0.7)   # [l] notation
E("DP2", "DP3", 0.8); E("DP2", "DP12", 0.85)
for t in ["DP12", "DP4", "RP1", "TP2"]:
    E("DP3", t, 0.8)
E("DP4", "DP5", 0.85); E("DP4", "DP14", 0.85); E("DP4", "RP11", 0.75)
for t in ["TP4", "RP10", "TP6", "PP2", "PP4", "EP29"]:
    E("DP5", t, 0.8)
E("DP6", "DP7", 0.8); E("DP6", "DP8", 0.8); E("DP6", "TP1", 0.75)
E("DP7", "DP8", 0.75); E("DP7", "DP9", 0.75); E("DP7", "TP1", 0.8); E("DP7", "RP2", 0.75); E("DP7", "RP5", 0.75)
E("DP8", "DP9", 0.8)
E("DP10", "DP11", 0.8); E("DP10", "TP1", 0.8); E("DP10", "RP3", 0.75); E("DP10", "OpenP1", 0.7)
E("DP11", "TP1", 0.85)
for t in ["TP2", "RP6", "PP4", "PP1"]:
    E("DP12", t, 0.85)
for t in ["TP5", "TP7", "PP2", "LP2", "PP5", "PP6"]:
    E("EP29", t, 0.8)        # p_n, e_n defined in Theorem 3
E("DP13", "DP14", 0.85); E("DP13", "TP7", 0.8)
for t in ["TP7", "PP5", "PP6", "RP12"]:
    E("DP14", t, 0.8)
for t in ["LP2", "PP5", "PP6"]:
    E("EP40", t, 0.8)        # U_ni defined in Theorem 4
E("EP22", "AP1", 0.8); E("EP22", "AP2", 0.8)
E("RP8", "ClP2", 0.85, "named")
E("EP14", "PSP9", 0.8); E("EP17", "PSP12", 0.8)

# results used (no \ref)
E("TP5", "PP2", 0.8, "inferred")
E("TP6", "PP2", 0.85, "inferred")
E("PP2", "TP4", 0.75, "named", type="proves", alternative=True)
E("PP4", "TP4", 0.9, "named", type="proves")
E("PP6", "TP7", 0.9, "named", type="proves")
E("TP2", "CnjP1", 0.85, "named", type="generalizes")
E("TP1", "OpenP1", 0.8, "named", type="generalizes")
E("TP2", "OpenP1", 0.8, "named", type="generalizes")
E("CnjP1", "RP8", 0.9, "named")
E("CnjP1", "ExP1", 0.8, "named", type="illustrates")
E("ExP1", "ClP2", 0.75, "inferred")
E("AP2", "ClP1", 0.75, "inferred")
E("AP1", "AP2", 0.7, "named")   # "The above techniques are implemented"
E("RP9", "AP2", 0.7, "named")
E("TP3", "RP9", 0.65, "inferred")
E("TP2", "RP4", 0.6, "inferred"); E("TP4", "RP4", 0.6, "inferred"); E("TP7", "RP4", 0.6, "inferred")
E("TP1", "RP2", 0.85, "named")   # "Eq. (XYZ)" is a ref; theorem itself
# inside proofs
for s, t in [("PSP1", "PSP2"), ("PSP2", "PSP3"), ("PSP4", "PSP5"), ("PSP5", "PSP6"), ("PSP6", "PSP7"), ("PSP6", "PSP8"),
             ("PSP11", "PSP12"), ("PSP12", "PSP13"), ("PSP13", "PSP14"), ("PSP14", "PSP15"), ("PSP12", "PSP15"),
             ("PSP17", "PSP18"), ("PSP18", "PSP19"), ("PSP22", "PSP29"), ("PSP28", "PSP29"),
             ("PSP24", "PSP26"), ("PSP26", "PSP27"), ("PSP27", "PSP28"),
             ("PSP30", "PSP31"), ("PSP32", "PSP33"), ("PSP31", "PSP34"), ("PSP33", "PSP34"), ("PSP34", "PSP35"),
             ("PSP38", "PSP39"), ("PSP43", "PSP45"), ("PSP43", "PSP46"), ("PSP48", "PSP51"), ("PSP49", "PSP51"),
             ("PSP49", "PSP52"), ("PSP52", "PSP53"), ("PSP49", "PSP54"), ("PSP51", "PSP55"), ("PSP52", "PSP55"),
             ("PSP53", "PSP55"), ("PSP54", "PSP55"), ("PSP49", "PSP56"), ("PSP41", "PSP44"),
             ("ASP1", "ASP2")]:
    E(s, t, 0.75, "inferred")

notes = [
    {"category": "rule_conflict", "nodes": ["TP2"],
     "note": "Eq. (3) in the introduction states the main inequality in the $W,S$ notation; Theorem 2 rephrases it with $B_{ij}$. Treated as one result: kept the environment (TP2) and put the Eq. (3) sentence in also_stated_at instead of an equation node, so refs to eq:main inequality land on TP2."},
    {"category": "type_uncertain", "nodes": ["OpenP1"],
     "note": "Environment 'Problem' asks for the most general conditions under which an inequality holds, an unresolved research question, so typed open_problem rather than problem."},
    {"category": "boundary_uncertain", "nodes": ["PP4", "PP6"],
     "note": "Proofs of Theorems 3 and 4 are headed by \\subsubsection*{Proof (Theorem ...):} with no proof environment; each is one proof node spanning that heading's enumerate, items as steps."},
    {"category": "boundary_uncertain", "nodes": ["PP2", "TP5", "TP6"],
     "note": "The alternative proof of Theorem 3(2) from known results: the cited O'Neill and Bai et al. results are separate external theorems, and the proof node is only the closing 'Thus, because ...' computation."},
    {"category": "source_problem", "nodes": ["EP10", "EP11"],
     "note": "The align labelled eq:three_boxes_volumes numbers only its first row and puts \\label on an unnumbered row; latex_facts splits it into a numbered and a labelled fact, both kept as equations."},
    {"category": "not_extracted", "nodes": [],
     "note": "Python command listings (check_CNF_DNF_inequality, find_enumerate_counter_example_DNF_CNF_inequality) and the closing future-work paragraph are not nodes; Weber's limit theorems are only applied and get no node."},
]

graph = {
    "metadata": {
        "title": "A correlation inequality for random points in a hypercube with some implications",
        "arxiv_id": "2209.00346",
        "authors": ["Royi Jacobovic", "Or Zuk"],
        "year": 2022,
        "annotator": "agent-extraction",
        "model": "claude-opus-5-5",
        "effort": "default",
        "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
        "extraction_date": "2026-11-05",
        "rigor_nonformal_count": sum(1 for n in nodes if "rigor" in n),
        "paper_style": ["theorem_proof", "computational"],
        "extraction_notes": notes,
        "extraction_comment": "",
    },
    "nodes": nodes,
    "edges": edges,
}
report = finalize(graph, tex)
for k in ("errors", "warnings"):
    print(k.upper(), len(report.get(k, [])))
    for x in report.get(k, []):
        print("  ", x)
for k, v in report.items():
    if k not in ("errors", "warnings"):
        print(k, v if not isinstance(v, (list, dict)) or len(str(v)) < 600 else str(v)[:600])
assert not report["errors"], report["errors"]
json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
print("wrote", OUT, len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
