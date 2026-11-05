"""Build the SARANGA v7 graph of arXiv 1505.06292 (Wagner & Zuk 2015,
Low-Rank Matrix Recovery from Row-and-Column Affine Measurements).
Node choices are made by reading; this script only slices the chosen spans."""
import json, sys, re
sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
from extraction_finalize import finalize, pseudocode_steps
from latex_facts import read_tex, extract_facts

TEX = "/mnt/c/Code/Github/Saranga/corpus/orzuk/1505_06292/arxiv_src/RC_arxiv_ICML2015.tex"
OUT = "/mnt/c/Code/Github/Saranga/corpus/orzuk/1505_06292/1505_06292.json"
tex = read_tex(TEX)
facts = extract_facts(tex)
SRC = facts["source"]
FACT = {f["id"]: f for f in facts["facts"]}
SECID = {s["id"]: s for s in facts["sections"]}
SECS = sorted([s for s in facts["sections"] if s["inside"] is None], key=lambda s: s["start"])


def sec_name(s):
    return f"{s['number']} {s['title']}" if s["number"] else s["title"]


def sec_of(pos):
    cur = None
    for s in SECS:
        if s["start"] <= pos:
            cur = s
    return sec_name(cur) if cur else ""


def _pat(t):
    return r"\s+".join(re.escape(w) for w in t.split())


def sp(a, b):
    """Slice from the unique occurrence of `a` to the first `b` after it (whitespace-insensitive)."""
    ms = list(re.finditer(_pat(a), SRC))
    assert len(ms) == 1, (len(ms), a)
    i = ms[0].start()
    m = re.compile(_pat(b)).search(SRC, i)
    assert m, (a, b)
    return SRC[i:m.end()]


def clean(s):
    s = re.sub(r"\\label\{[^{}]*\}", "", s)
    return " ".join(s.split())


nodes, edges = [], []
BYID = {}


def _check_spans(n):
    st = n["statement"]
    for k in ("assumptions", "conclusions", "equivalent_conditions"):
        for x in n.get(k, []):
            assert x in st, (n["id"], k, x)


def N(id, type, name, stmt, origin="paper", conf=0.75, **kw):
    pos = SRC.find(stmt)
    assert pos >= 0, id
    n = {"id": id, "type": type, "name": name, "statement": clean(stmt),
         "section": sec_of(pos), "origin": origin, "confidence": conf}
    n.update(kw)
    _check_spans(n)
    nodes.append(n); BYID[id] = n
    return n


def F(id, type, fid, name, origin="paper", conf=1.0, **kw):
    f = FACT[fid]
    n = {"id": id, "type": type, "name": name, "statement": f["statement"],
         "section": sec_name(SECID[f["section"]]), "origin": origin, "confidence": conf}
    n.update(kw)
    _check_spans(n)
    nodes.append(n); BYID[id] = n
    return n


def STEPS(parent, specs, kind="proof_step", conf=0.75):
    """specs: list of (id, name, start, end, subclass, short)"""
    par = BYID[parent]
    for k, (sid, name, a, b, sub, short) in enumerate(specs, 1):
        st = sp(a, b)
        if st.startswith("\\item"):
            st = st[len("\\item"):]
        n = {"id": sid, "type": kind, "name": name, "statement": clean(st),
             "section": par["section"], "origin": par["origin"], "confidence": conf,
             "parent_id": parent, "step_order": k, "subclass": sub, "statement_short": short}
        nodes.append(n); BYID[sid] = n


def E(s, t, conf=0.8, basis="term", type="uses", **kw):
    e = {"source": s, "target": t, "type": type, "confidence": conf, "basis": basis}
    e.update(kw)
    edges.append(e)


STD = dict(origin="external", origin_citation="standard (uncited)")

# ---------------- equations (all numbered displays) ----------------
EQS = [
 ("EP1", "F1", "Noisy row-and-column measurement model"),
 ("EP2", "F2", "Squared loss $\\mathcal{F}(X)$"),
 ("EP3", "F3", "Rank-constrained least-squares problem"),
 ("EP4", "F5", "r-RIP inequality"),
 ("EP5", "F7", "Coherence $\\mu(U)$"),
 ("EP6", "F10", "Closed-form estimator of Algorithm 1 (row version)"),
 ("EP7", "F11", "Closed-form estimator (column version)"),
 ("EP8", "F13", "Least-squares step of SVLS"),
 ("EP9", "F14", "Closed form of $\\hat{Y}$ in SVLS"),
 ("EP10", "F15", "Elbow rank estimate"),
 ("EP11", "F16", "Projected estimators of $SVLS_P$"),
 ("EP12", "F19", "Conclusion of Lemma 2: agreement on measurements"),
 ("EP13", "F24", "Noisy GRC error bound"),
 ("EP14", "F26", "Noisy GRC bound for Gaussian noise"),
 ("EP15", "F27", "RRMSE"),
 ("EP16", "F31", "Row equality $A^{(R)}\\hat{X}=A^{(R)}X$"),
 ("EP17", "F32", "Column equality $\\hat{X}A^{(C)}=XA^{(C)}$"),
 ("EP18", "F35", "Kronecker product"),
 ("EP19", "F36", "Covariance of $V^TA^{(C)}$"),
 ("EP20", "F38", "Loss $\\mathcal{L}(W,S)$"),
 ("EP21", "F39", "Gradient of $\\mathcal{L}$ with respect to $S$"),
 ("EP22", "F40", "Projection form of the spectral bound"),
 ("EP23", "F42", "RCMC concentration bound"),
 ("EP24", "F44", "Expectation bound for Bernoulli sums of rank-one matrices"),
 ("EP25", "F46", "Supremum $Z$ of an empirical process"),
 ("EP26", "F47", "Talagrand tail bound"),
 ("EP27", "F49", "Tail bound for $Z=||Y||_2$"),
 ("EP28", "F51", "Uniform bound $|f(Y_i)|$"),
 ("EP29", "F52", "Variance bound $E(f^2(Y_i))$"),
 ("EP30", "F53", "Tail bound from Talagrand's inequality"),
 ("EP31", "F55", "Action of $P_UP_{A^{(R)T}}P_U$"),
 ("EP32", "F56", "$P_UP_{A^{(R)T}}P_U$ as sum of rank-one terms"),
 ("EP33", "F57", "Expectation bound for $P_UP_{A^{(R)T}}P_U-pP_U$"),
 ("EP34", "F59", "Positivity of $\\sigma_r(U^TA^{(R)T}A^{(R)}U)$"),
 ("EP35", "F61", "Szarek singular value tail bounds"),
 ("EP36", "F63", "Pseudoinverse norm bound"),
 ("EP37", "F65", "Pseudoinverse bound via $\\sigma_k$"),
 ("EP38", "F67", "JL distortion $\\epsilon$"),
 ("EP39", "F68", "JL concentration"),
 ("EP40", "F70", "Term I"),
 ("EP41", "F93", "Term II"),
 ("EP42", "F94", "Term III"),
 ("EP43", "F72", "First decomposition of $||X-\\hat{X}||_F$"),
 ("EP44", "F73", "Identity $XA^{(C)}A_{V^T}^{(C)\\dagger}V^T=X$"),
 ("EP45", "F74", "Rewriting the first part via $B^{(C,0)}$"),
 ("EP46", "F75", "Annihilation of $B^{(C)}_{(r)}$"),
 ("EP47", "F76", "Bound of the first part by I+II"),
 ("EP48", "F79", "Triangle inequality for Claim 1"),
 ("EP49", "F80", "Matrix norm inequalities"),
 ("EP50", "F82", "Rank bound for term I"),
 ("EP51", "F83", "Bound of I by spectral norms"),
 ("EP52", "F84", "Term I bound with $6\\sqrt{r/k}$"),
 ("EP53", "F85", "Probabilistic bound on I"),
 ("EP54", "F86", "Bound on II by norms"),
 ("EP55", "F87", "Probabilistic bound on II (first)"),
 ("EP56", "F88", "Bound on II via JL"),
 ("EP57", "F89", "Probabilistic bound on II"),
 ("EP58", "F90", "Bound on III"),
 ("EP59", "F91", "Probabilistic bound on III"),
]

# ================= 1 Introduction / 1.1 Prior Work =================
N("DP1", "definition", "Matrix representation of an affine transformation",
  sp("In general, we can represent any affine transformation", "on top of each other."),
  conf=0.8, **STD, definiendum="matrix representation $\\mathcal{{A}}(X)=Avec(X)$")
N("DP2", "definition", "Measurement sparsity",
  sp("We concentrate on two properties: (i) storage", "$S(\\mathcal{{A}})=||vec(A)||_0$."),
  conf=0.8, definiendum="measurement sparsity",
  statement_short="Measurement sparsity $S(\\mathcal{A})=||vec(A)||_0$: total number of matrix entries entering all measurements.")
N("DP3", "definition", "Gaussian Ensemble (GE)",
  sp("In the Gaussian Ensemble model, the entries of the matrix $A$", "$A_{ij} \\sim N(0,1)$."),
  conf=0.8, origin="external", origin_citation="Recht, Fazel & Parrilo 2010; Candes & Plan 2011",
  definiendum="Gaussian Ensemble", genus="matrix representation $\\mathcal{{A}}(X)=Avec(X)$",
  differentia=["i.i.d. Gaussian random variables, $A_{ij} \\sim N(0,1)$"],
  also_stated_at=[clean(sp("It is instructive to compare our GRC ensemble", "$A\\overset{i.i.d.}{\\sim} N(0,1)$."))])
N("TP1", "theorem", "Low-rank recovery in the Gaussian Ensemble from O(r(n1+n2)) measurements",
  sp("For this ensemble, one can recover uniquely a low", "which is optimal up to constants."),
  conf=0.7, origin="external", origin_citation="Recht, Fazel & Parrilo 2010; Candes & Plan 2011; Jain et al. 2010 (SVP)",
  assumptions=["For this ensemble"],
  conclusions=["one can recover uniquely a low rank matrix $X$ with $O(r (n_{1}+n_{2}))$ noiseless measurements"],
  statement_short="In GE, nuclear norm minimization or SVP recovers a rank-$r$ matrix from $O(r(n_1+n_2))$ noiseless measurements.")
N("TP2", "theorem", "Matrix completion needs Theta(n r log n) measurements",
  sp("However, recovery guarantees for this model are", "matrix of size $n_1 \\times n_2$ \\cite{candes2010power}."),
  conf=0.7, origin="external", origin_citation="Candes & Tao 2010",
  conclusions=["$\\Theta(nrlog(n))$ measurements are required to recover a rank $r$ matrix of size $n_1 \\times n_2$"],
  statement_short="Standard matrix completion needs $\\Theta(nr\\log n)$ uniformly sampled entries for a rank-$r$ matrix.")
N("DP4", "definition", "Rank one projections design",
  sp("Recently a new design of rank one projections was proposed", "have i.i.d standard Gaussian entries."),
  conf=0.8, origin="external", origin_citation="Cai & Zhang 2015", definiendum="rank one projections",
  statement_short="Each measurement is $\\alpha^TX\\beta$ with i.i.d. standard Gaussian $\\alpha,\\beta$.")
N("TP3", "theorem", "Nuclear norm recovery from rank one projections",
  sp("It was proven that nuclear norm\nminimization can recover", "$O(n_1r+n_2r)$ measurements."),
  conf=0.7, origin="external", origin_citation="Cai & Zhang 2015",
  conclusions=["nuclear norm minimization can recover $X$ with high probability in this design from $O(n_1r+n_2r)$ measurements"])

# ================= 2 Preliminaries and Notations =================
N("DP5", "definition", "Matrix spaces $\\mathbb{R}_{n_1\\times n_2}$, $\\mathcal{O}_{n_1\\times n_2}$, $\\mathcal{M}^{(r)}_{n_1\\times n_2}$",
  sp("We denote by $\\matrixspace{n_{1}}{n_{2}}$ the space of matrices of", "and rank $\\leqslant r$."),
  conf=0.85, **STD,
  definiendum=["$\\matrixspace{n_{1}}{n_{2}}$", "$\\orthomatrixspace{n_{1}}{n_{2}}$", "$\\lowrank{n_{1}}{n_{2}}r$"])
N("DP6", "definition", "$n=\\max(n_1,n_2)$", sp("We denote $n=\\max(n_1,n_2)$.", "$n=\\max(n_1,n_2)$."),
  conf=0.85, definiendum="$n$")
N("DP7", "definition", "Frobenius, nuclear and spectral norms",
  sp("We denote by $||\\cdot||_{F}$ the matrix Frobenius norm", "the spectral norm."),
  conf=0.85, **STD, definiendum=["$||\\cdot||_{F}$", "$||\\cdot||_{*}$", "$||\\cdot||_{2}$"])
N("DP8", "definition", "Vector $l_2$ norm", sp("For a\nvector, $||\\cdot||$ denotes", "$l_{2}$ norm."),
  conf=0.85, **STD, definiendum="$||\\cdot||$")
N("DP9", "definition", "Column span $span(X)$ and projection $P_X$",
  sp("For $X\\in\\matrixspace{n_{1}}{n_{2}}$we denote by $span(X)$", "orthogonal projection into $span(X)$."),
  conf=0.85, **STD, definiendum=["$span(X)$", "$P_{X}$"])
N("DP10", "definition", "Row, column and entry notation",
  sp("For a matrix $X$ we denote by $\\matrixrow Xi$", "the $(i,j)$\nelement."),
  conf=0.85, **STD, definiendum=["$\\matrixrow Xi$", "$\\matrixcolumn Xj$", "$X_{ij}$"])
N("DP11", "definition", "Sub-matrix $X_{IJ}$",
  sp("For two sets of indices $I,J$, we denote by $X_{IJ}$", "with indices in $J$ of $X$."),
  conf=0.85, **STD, definiendum="$X_{IJ}$")
N("DP12", "definition", "Index set $[k]$", sp("We denote by $[k]$ the set of indices", "$1,..,k$."),
  conf=0.85, **STD, definiendum="$[k]$")
N("DP13", "definition", "Vectorization $vec(X)$",
  sp("We denote by $vec(X)$ the (column) vector obtained by", "stacking all the columns of $X$ on top of each other."),
  conf=0.85, **STD, definiendum="$vec(X)$")
N("DP14", "definition", "i.i.d. random matrix notation",
  sp("We use the notation $X\\overset{i.i.d.}{\\sim} G$", "entries $X_{ij}\\sim G$."),
  conf=0.85, definiendum="$X\\overset{i.i.d.}{\\sim} G$")
N("DP15", "definition", "Singular Value Decomposition (SVD)",
  sp("For a rank-$r$ matrix $X\\in\\lowrank{n_{1}}{n_{2}}r$ let $X=U\\Sigma V^{T}$", "vectors from the decomposition)."),
  conf=0.85, **STD, definiendum="Singular Value Decomposition ($SVD$)",
  statement_short="Compact SVD $X=U\\Sigma V^T$ of a rank-$r$ matrix with only the $r$ non-zero singular values.")
N("DP16", "definition", "Top-r SVD $X_{(r)}$",
  sp("For\na general matrix $X\\in\\matrixspace{n_{1}}{n_{2}}$ we denote by $\\svdtop Xr$", "V_{\\bullet[r]}^{T}$."),
  conf=0.85, **STD, definiendum="$\\svdtop Xr$")
N("DP17", "definition", "Row-and-column affine measurements $B^{(C,0)}=XA^{(C)}$, $B^{(R,0)}=A^{(R)}X$",
  sp("Our model assumes two affine transformations applied to $X$", "respectively."),
  conf=0.85, definiendum=["$B^{(C,0)}$", "$B^{(R,0)}$", "$A^{(R)}$", "$A^{(C)}$"],
  statement_short="The measurements are $B^{(C,0)}=XA^{(C)}$ and $B^{(R,0)}=A^{(R)}X$: linear combinations of columns and of rows of $X$.")
N("DP18", "definition", "Noisy observations $B^{(R)},B^{(C)}$ and number of measurements $d$",
  sp("We obtain noisy observations", "are two zero-mean noise matrices."),
  conf=0.85, definiendum=["$B^{(R)}$", "$B^{(C)}$", "$d$", "$Z^{(R)}$", "$Z^{(C)}$"],
  statement_short="Observations $B^{(R)}=A^{(R)}X+Z^{(R)}$, $B^{(C)}=XA^{(C)}+Z^{(C)}$ with zero-mean noise; $d=k^{(R)}n_1+n_2k^{(C)}$ measurements.")
N("ProbP1", "problem", "Rank-constrained least-squares recovery",
  sp("To achieve this\ngoal, we define the squared loss function", "\\label{eq:problem1}\n\\end{equation}"),
  conf=0.85, definiendum="$\\mathcal{\\mathcal{\\mathcal{{F}}}}(X)$",
  statement_short="Minimize the squared loss $\\mathcal{F}(X)$ of row and column measurements over matrices of rank at most $r$.")
N("ClP1", "claim", "Least squares is maximum likelihood under Gaussian noise",
  sp("If $Z^{(R)},Z^{(C)}\\overset{i.i.d.}{\\sim} N(0,\\tau^{2})$ , minimizing", "for the\nabove score."),
  conf=0.7, **STD,
  assumptions=["If $Z^{(R)},Z^{(C)}\\overset{i.i.d.}{\\sim} N(0,\\tau^{2})$"],
  conclusions=["minimizing the loss function in eq. (\\ref{eq:losses_function}) is equivalent to maximizing the log-likelihood of the data"])
N("DP19", "definition", "Row and Column Matrix Completion (RCMC) ensemble",
  sp("\\textbf{Row and Column Matrix Completion (RCMC):} In this ensemble", "obtained from a single entry of $X$."),
  conf=0.85, definiendum="Row and Column Matrix Completion (RCMC)",
  differentia=["each row of $A^{(R)}$ and each column of $A^{(C)}$ is a vector of the standard basis $e_{j}$ for some $j$"])
N("DP20", "definition", "Row and column inclusion probabilities $p^{(R)},p^{(C)}$",
  sp("We define a row-inclusion\nprobability $p^{(R)}$", "$p^{(R)}$ ($p^{(C)}$)."),
  conf=0.85, definiendum=["$p^{(R)}$", "$p^{(C)}$"])
N("DP21", "definition", "Row-inclusion Bernoulli variables $r_i$",
  sp("More precisely, we define $r_{1},..,r_{n_{1}}$", "if and only if $r_{i}=1$."),
  conf=0.85, definiendum="$r_{i}$")
N("DP22", "definition", "Column-inclusion Bernoulli variables $c_i$",
  sp("Similarly, we define $c_{1}...c_{n_{2}}$", "if and only if $c_{i}=1$."),
  conf=0.85, definiendum="$c_{i}$")
N("DP23", "definition", "Gaussian Rows and Columns (GRC) ensemble",
  sp("\\textbf{Gaussian Rows and Columns (GRC):} In this ensemble", "with i.i.d. Gaussian weights."),
  conf=0.85, definiendum="Gaussian Rows and Columns (GRC)",
  differentia=["$A^{(R)},A^{(C)}\\overset{i.i.d.}{\\sim} N(0,1)$"])

# ================= 2.1 Comparison to Standard Designs =================
F("DP24", "definition", "F4", "r-Restricted Isometry Property (r-RIP)", origin="external",
  origin_citation="Recht, Fazel & Parrilo 2010; Candes & Plan 2011",
  definiendum="$r$-Restricted Isometry Constant $\\epsilon_{r}$")
N("TP4", "theorem", "The Gaussian Ensemble satisfies r-RIP",
  sp("The GE model satisfies the $r$-RIP condition", "\\cite{recht2010guaranteed}."),
  conf=0.75, origin="external", origin_citation="Recht, Fazel & Parrilo 2010",
  assumptions=["$d = O(rn)$"], conclusions=["The GE model satisfies the $r$-RIP condition"])
N("ClP2", "claim", "GRC does not satisfy RIP; nuclear norm minimization fails",
  sp("Unlike GE, in our GRC model", "norm minimization fails."),
  conf=0.65, rigor="semi_formal",
  conclusions=["in our GRC model $\\mathcal{{A}}(X)$ doesn't satisfy the $r$-RIP, and nuclear norm minimization fails"])
N("ClP3", "claim", "GRC preserves Frobenius norm of any low-rank matrix",
  sp("Instead, $A^{(R)},A^{(C)}$ preserve matrix Frobenius", "in the Appendix)."),
  conf=0.7,
  also_stated_at=[clean(sp("Representing the vectors in $Q$ as a\nmatrix,", "holds for \\textit{any} low-rank matrix."))])
F("DP25", "definition", "F6", "Coherence of a subspace (Incoherence)", origin="external",
  origin_citation="Candes & Recht 2009", definiendum="coherence $\\mu(U)$")
N("DP26", "definition", "$\\mu$-incoherent matrix",
  sp("We say that a matrix $X\\in\\matrixspace{n_{1}}{n_{2}}$ is $\\mu$-incoherent", "\\leq\\mbox{\\ensuremath{\\mu}}$."),
  conf=0.85, origin="external", origin_citation="Candes & Recht 2009", definiendum="$\\mu$-incoherent")
N("ClP4", "claim", "Nuclear norm minimization fails for RCMC",
  sp("However, nuclear norm minimization fails\nfor the RCMC design", "as shown\nby the next example:"),
  conf=0.75, conclusions=["nuclear norm minimization fails for the RCMC design, even when the matrix $X$ is incoherent"])
F("ExP1", "example", "F8", "All-ones matrix where nuclear norm minimization fails under RCMC",
  statement_short="For the all-ones $n\\times n$ matrix with $n/3$ observed rows and columns, filling the rest with 0.5 gives smaller nuclear norm.")

# ================= 3 Algorithms =================
F("AP1", "algorithm", "F9", "Noiseless recovery algorithm (Algorithm 1)",
  input=["$A^{(R)},A^{(C)},B^{(R)},B^{(C)}$ and rank $r$"], output=["$\\hat{X}=\\hat{U}Y$"],
  statement_short="Take a basis $\\hat{U}$ of the column space of $B^{(C)}$, solve $B^{(R)}=A^{(R)}\\hat{U}Y$ by least squares, output $\\hat{U}Y$.")
N("ClP5", "claim", "Closed form of the Algorithm 1 estimator",
  sp("If $rank(A^{(R)}\\hat{U})=r$ one can write the resulting estimator", "\\label{eq:algorithm1}\n\\end{equation}"),
  conf=0.7, rigor="semi_formal", assumptions=["If $rank(A^{(R)}\\hat{U})=r$"])
N("ClP6", "claim", "Column version of the closed-form estimator",
  sp("We can apply the same algorithm, but changing the role", "representing a basis for the\nrows of $X$."),
  conf=0.65, rigor="semi_formal")
F("AP2", "algorithm", "F12", "SVLS (Singular Value Least Squares)", main=True,
  input=["$A^{(R)},A^{(C)},B^{(R)},B^{(C)}$ and rank $r$"],
  output=["$\\hat{X} = argmin_{\\hat{X}^{(R)},\\hat{X}^{(C)}} \\mathcal{\\mathcal{{F}}}(X)$"],
  statement_short="Top-$r$ left singular vectors of $B^{(C)}$ give $\\hat{U}$; least squares on row measurements gives $\\hat{U}\\hat{Y}$; do the symmetric version, keep the lower-loss estimate.")

# Gradient descent (Appendix 7.2), placed here in id order
N("AP3", "algorithm", "Gradient descent refinement in factored form",
  sp("The gradient descent stage is performed directly in the space", "\\label{eq:-1}\n\\end{equation}"),
  conf=0.75, input=["$\\hat{X}$ (the output of SVLS\\!)"],
  statement_short="Gradient descent on $\\mathcal{L}(W,S)=\\mathcal{F}(WS)$ over the factors, started from the SVLS estimate.")
N("AP4", "algorithm", "Elbow-method rank estimator",
  sp("For the noisy case we estimate $rank(X)$ from", "\\frac{\\hat{r}^{(C)}+\\hat{r}^{(C)}}{2}\\right)$."),
  conf=0.8, input=["$B^{(C)},B^{(R)}$"], output=["$\\hat{r}=round\\left(\\frac{\\hat{r}^{(C)}+\\hat{r}^{(C)}}{2}\\right)$"],
  statement_short="Estimate the rank of each of $B^{(C)},B^{(R)}$ by the largest ratio of consecutive singular values, then average.")
N("ProbP2", "problem", "Low rank matrix approximation problem",
  sp("In the low rank matrix approximation problem, the goal is", "rank-$r$ matrix $X_{(r)}$."),
  conf=0.85, **STD)
N("TP5", "theorem", "Eckart-Young Theorem",
  sp("By the  Eckart-Young Theorem \\cite{eckart1936approximation}", "truncated $SVD$ of $X$."),
  conf=0.85, origin="external", origin_citation="Eckart & Young 1936",
  conclusions=["this problem has a closed-form solution which is the truncated $SVD$ of $X$"])
N("AP5", "algorithm", "$SVLS_P$ (SVLS with Halko-Martinsson-Tropp projections)",
  sp("We adjusted the algorithm presented in \\cite{halko2011finding} to our problem", "We call this new estimator $SVLS_P$."),
  conf=0.8,
  statement_short="SVLS whose two estimates are additionally projected on the top-$r$ singular subspaces of $B^{(R)}$ and $B^{(C)}$.")

# ================= 4 Performance Guarantees =================
N("ClP7", "claim", "Degrees of freedom of a rank-r matrix",
  sp("A rank $r$ matrix of size $n_{1}\\times n_{2}$ has", "by fewer measurements."),
  conf=0.75, **STD,
  conclusions=["has $r(n_{1}+n_{2}-r)$ degrees of freedom, and can therefore not be uniquely recovered by fewer measurements"])
F("LP1", "lemma", "F17", "Uniqueness from row and column measurements",
  assumptions=["Let $X_{1},X_{2}\\in\\lowrank{n_{1}}{n_{2}}r$ and $A^{(R)}\\in\\matrixspace{k^{(R)}}{n_{1}},A^{(C)}\\in\\matrixspace{n_{2}}{k^{(C)}}$ such that $rank(A^{(R)}X_{1})=rank(X_{1}A^{(C)})=r$",
               "If $A^{(R)}X_{1}=A^{(R)}X_{2}$ and $X_{1}A^{(C)}=X_{2}A^{(C)}$"],
  conclusions=["then $X_{1}=X_{2}$"],
  statement_short="Two rank-$r$ matrices agreeing on full-rank row and column measurements are equal.")
F("LP2", "lemma", "F18", "Algorithm 1 output agrees with the measurements",
  assumptions=["Let $X\\in\\lowrank{n_{1}}{n_{2}}r$ and $A^{(R)}\\in\\matrixspace{k^{(R)}}{n_{1}},A^{(C)}\\in\\matrixspace{n_{2}}{k^{(C)}}$ such that $rank(A^{(R)} X)=rank(XA^{(C)})=r$"],
  conclusions=["the output $\\hat{X}$ satisfies"],
  statement_short="With full-rank noiseless measurements, the Algorithm 1 output reproduces both $A^{(R)}X$ and $XA^{(C)}$.")
F("TP6", "theorem", "F20", "Exact recovery for GRC with minimal measurements", main=True,
  assumptions=["Let $\\hat{X}$ be the output of Algorithm \\ref{alg:noiseless_case} in the GRC model with $Z^{(C)},Z^{(R)}=0$ and $k^{(R)},k^{(C)}\\geq r$"],
  conclusions=["$P(\\hat{X}=X)=1$"],
  statement_short="In noiseless GRC with $k^{(R)},k^{(C)}\\ge r$, Algorithm 1 recovers $X$ with probability 1.")
F("TP7", "theorem", "F21", "Exact recovery for RCMC with high probability", main=True,
  assumptions=["Let $X=U\\Sigma V^{T}$ be the $SVD$ of $X \\in \\matrixspace {n_1}{n_2}$, and $\\max(\\mu(U),\\mu(V))<\\mu$",
               "Take $A^{(R)}$ and $A^{(C)}$ as in the RCMC model without noise and probabilities $p^{(R)}=\\frac{k}{n_1}$ and $p^{(C)}=\\frac{k}{n_2}$",
               "Let $\\beta>1$ such that $C_{R}\\sqrt{\\frac{\\beta log(n)r\\mu}{k}}<1$ where $C_{R}$ is uniform constant"],
  conclusions=["Then $P\\left(\\hat{X}=X\\right)>1-6min(n_1,n_2)^{-\\beta}$"],
  statement_short="For $\\mu$-incoherent $X$ and $k\\gtrsim \\beta\\mu r\\log n$ sampled rows and columns, Algorithm 1 recovers $X$ w.p. $>1-6\\min(n_1,n_2)^{-\\beta}$.")
F("RP1", "remark", "F22", "Both row and column measurements are needed")
N("TP8", "theorem", "Gaussian Ensemble noisy error bound",
  sp("In \\cite{candes2011tight} it is shown for GE that", "for some constant $C_{G}$."),
  conf=0.75, origin="external", origin_citation="Candes & Plan 2011",
  conclusions=["$||X-\\hat{X}||_{F}<C_{G}\\sqrt{\\frac{nr\\tau^{2}}{d}}$ holds with high probability for some constant $C_{G}$"])
F("TP9", "theorem", "F23", "Error bound for SVLS in the noisy GRC model", main=True,
  assumptions=["Let $A^{(R)}$ and $A^{(C)}$ with $k\\geq max(4r,40)$ be as in the GRC model with noise matrices $Z^{(R)},Z^{(C)}$",
               "Let $\\hat{X}$ be the output of SVLS"],
  conclusions=["there exist constants $c,c^{(R)},c^{(C)}$ such that with probability $>1-5e^{-ck}$:"],
  statement_short="In noisy GRC with $k\\ge\\max(4r,40)$, SVLS has $||X-\\hat{X}||_F\\le\\sqrt{r/k}\\,(c^{(C)}||Z^{(C)}||_2+c^{(R)}||Z^{(R)}||_2)$ w.p. $>1-5e^{-ck}$.")
N("PP1", "proof", "Proof of Corollary 1",
  sp("Theorem \\ref{thm:the_noisy_case} applies for any $Z^{(C)}$ and $Z^{(R)}$.", "for i.i.d. additive Gaussian noise:"),
  conf=0.8, proves="CP1", proof_strategy=["direct"],
  statement_short="Plug the Gaussian spectral-norm bound $||Z||_2\\le 4\\tau\\sqrt{n}$ (w.p. $1-e^{-2n}$) into Theorem 3.")
F("CP1", "corollary", "F25", "Noisy GRC error bound for i.i.d. Gaussian noise",
  assumptions=["Let $A^{(R)}$, $A^{(C)}$ as in the GRC with $n\\geq k\\geq max(4r,40)$, model and $Z^{(R)},Z^{(C)}\\overset{i.i.d.}{\\sim} N(0,\\tau^{2})$"],
  conclusions=["there exist constants $c,C_{GRC}$ such that:"],
  statement_short="With i.i.d. $N(0,\\tau^2)$ noise, $||X-\\hat{X}||_F\\le C_{GRC}\\sqrt{\\tau^2nr/k}$ w.p. $>1-5e^{-ck}-e^{-2n}$.")

# ================= 5 Simulations =================
N("DP27", "definition", "Relative Root-Mean-Squared-Error (RRMSE)",
  sp("We measured the\nreconstruction accuracy using the Relative Root-Mean-Squared-Error", "/||X||_{F}.\n\\end{equation}"),
  conf=0.85, definiendum="$RRMSE$")
N("ClP8", "claim", "RCMC with SVLS reaches exact recovery at the optimal number of measurements",
  sp("SVLS recovers\n$X$ with probability $1$ with the optimal number", "to guarantee exact recovery."),
  conf=0.7, rigor="numerical")
N("ClP9", "claim", "SVLS is stable on RCMC while OptSpace and SVT are not",
  sp("Figure \\ref{fig:algorithm_performance}\nshows that while the performance of SVLS", "poor accuracy for all problem instances."),
  conf=0.7, rigor="numerical")
F("RP2", "remark", "F28", "OptSpace trimming step omitted for RCMC")
N("ClP10", "claim", "SVLS on RCMC is faster than and comparably accurate to MC algorithms",
  sp("Results, displayed in Table \\ref{tab:accuracy-and-time}, show that SVLS", "comparable to MC for large number of measurements."),
  conf=0.7, rigor="numerical")
N("ClP11", "claim", "GRC outperforms GE at all noise levels",
  sp("For all noise levels, the performance of GRC was better", "the performance of GE."),
  conf=0.7, rigor="numerical")
N("ClP12", "claim", "RRMSE decays at rate sqrt(k)",
  sp("The $RRMSE$ error decays at a rate of $\\sqrt{k}$.", "$\\sqrt{k}$."), conf=0.65, rigor="numerical")
N("ClP13", "claim", "RRMSE is linear in the noise level",
  sp("The change in the relative error $RRMSE$ is linear in $\\tau$", "the rate depends on $r$."),
  conf=0.7, rigor="numerical")
N("ClP14", "claim", "Scaled RRMSE is insensitive to n",
  sp("Results (shown in the Appendix, Section \\ref{sec:appendix_simulations}) indicate that", "in agreement\nwith Theorem \\ref{thm:the_noisy_case}."),
  conf=0.7, rigor="numerical")
N("OpenP1", "open_problem", "Recovery guarantees for noisy RCMC",
  sp("For RCMC, our simulations show that the\nRCMC design may achieve", "is an interesting future challenge."),
  conf=0.7, statement_short="Prove recovery guarantees for the RCMC design (beyond the noiseless case).")

# ================= 7 Appendix =================
F("PP2", "proof", "F29", "Proof of Lemma 1", proves="LP1", proof_strategy=["algebraic_manipulation", "direct"],
  statement_short="Both matrices share one $r$-dimensional column space; write them as $UY_i$ and use invertibility of $U^TA^{(R)T}A^{(R)}U$.")
F("PP3", "proof", "F30", "Proof of Lemma 2", proves="LP2", proof_strategy=["algebraic_manipulation", "direct"],
  statement_short="$\\hat{U}$ spans $span(X)$; substitute $X=\\hat{U}Y$ in the closed form (6) and simplify both products.")
F("LP3", "lemma", "F33", "Rotation invariance of Gaussian matrices",
  assumptions=["Let $V\\in\\orthomatrixspace nr$ and $A^{(C)}\\in\\matrixspace nk$ be a random matrix $A^{(C)}\\overset{i.i.d.}{\\sim} N(0,\\sigma^{2})$"],
  conclusions=["Then $V^{T}A^{(C)} \\overset{i.i.d.}{\\sim} N(0,\\sigma^{2})$"],
  statement_short="For $V$ with orthonormal columns and i.i.d. Gaussian $A$, $V^TA$ is again i.i.d. Gaussian.")
F("PP4", "proof", "F34", "Proof of Lemma 3", proves="LP3", proof_strategy=["algebraic_manipulation"],
  statement_short="Write $vec(V^TA)=(I\\otimes V^T)vec(A)$ and compute its covariance via Kronecker products.")
F("PP5", "proof", "F37", "Proof of Theorem 1", proves="TP6", proof_strategy=["probabilistic", "direct"],
  statement_short="By Lemma 3, $V^TA^{(C)}$ is Gaussian so has rank $r$ a.s.; then Lemmas 2 and 1 give $\\hat{X}=X$.")
N("ClP15", "claim", "Projection form of the RCMC spectral condition",
  sp("Because $U$ is orthonormal, this is equivalent to", "and $p^{(R)}=p$."),
  conf=0.7, statement_short="$p^{-1}||U^TA^TAU-pI_r||_2<1$ is equivalent to the same bound for $P_UP_{A^{(R)T}}P_U-pP_U$.")
F("LP4", "lemma", "F41", "Spectral concentration for RCMC row sampling",
  assumptions=["Suppose $A^{(R)}$ as in the RCMC model with inclusion probability $p$, and $U\\in\\orthomatrixspace {n_1}r$ with $\\mu(U)=\\frac{n_1}{r}max_{i}||P_{U}(e_{i})||^{2}=\\mu$",
               "if $C_{R}\\sqrt{\\frac{\\beta log(n_1)r\\mu}{pn_1}}<1$"],
  conclusions=["there is a numerical constant $C_{R}$ such that for all $\\beta>1$"],
  statement_short="Row sampling with probability $p$ keeps $p^{-1}P_UP_{A^{(R)T}}P_U$ within $C_R\\sqrt{\\beta\\mu r\\log n_1/(pn_1)}$ of $P_U$ w.p. $>1-3n_1^{-\\beta}$.")
F("LP5", "lemma", "F43", "Expectation bound for Bernoulli sums of rank-one matrices (Rudelson-type)", origin="external",
  origin_citation="Candes & Romberg 2007",
  assumptions=["If $y_{i}$ is a family of vectors in $\\mathbb{R}^{d}$ and ${r_{i}}$ is a sequence of i.i.d. Bernoulli random variables with $P(r_{i}=1)=p$",
               "provided that the right hand side is less than $1$"])
F("TP10", "theorem", "F45", "Talagrand's concentration inequality", origin="external", origin_citation="Talagrand 1996",
  statement_short="Concentration of the supremum of a bounded, centered empirical process around its mean.")
F("LP6", "lemma", "F48", "Concentration of $||Y||_2$ for Bernoulli-sampled projections", origin="external",
  origin_citation="Candes & Recht 2009 (Theorem 4.2)",
  statement_short="$Z=||\\sum_i p^{-1}(r_i-p)P_U e_i\\otimes P_U e_i||_2$ concentrates around its mean at scale $\\sqrt{\\mu r\\log n/(pn)}$.")
F("PP6", "proof", "F50", "Proof of Lemma 6", proves="LP6", proof_strategy=["probabilistic"],
  statement_short="Write $Z$ as a supremum of an empirical process, bound $|f|$ and the variance by incoherence, apply Talagrand's inequality.")
F("PP7", "proof", "F54", "Proof of Lemma 4", proves="LP4", proof_strategy=["probabilistic"],
  statement_short="Write $P_UP_{A^{(R)T}}P_U$ as a Bernoulli sum of rank-one projections; bound its expectation (Lemma 5) and concentrate (Lemma 6).")
F("PP8", "proof", "F58", "Proof of Theorem 2", proves="TP7", proof_strategy=["probabilistic", "direct"],
  statement_short="Lemma 4 and a union bound give $A^{(R)}U$, $V^TA^{(C)}$ of rank $r$; then Lemmas 2 and 1 give $\\hat{X}=X$.")
F("TP11", "theorem", "F60", "Szarek's bounds on extreme singular values of Gaussian matrices", origin="external",
  origin_citation="Szarek 1991",
  assumptions=["Let $A\\in\\matrixspace nk$ be a random matrix $A\\overset{i.i.d.}{\\sim} N(0,\\frac{1}{n})$"])
F("CP2", "corollary", "F62", "Pseudoinverse norm bound for Gaussian matrices",
  assumptions=["Let $A\\in\\matrixspace nk$ be a random matrix $A\\overset{i.i.d.}{\\sim} N(0,1)$ where $n\\geq4k$, and let $\\psuedoinv A$ be the Moore-Penrose pseudoinverse of $A$"],
  statement_short="For an $n\\times k$ standard Gaussian matrix with $n\\ge 4k$, $||A^\\dagger||_2\\le 6/\\sqrt{n}$ w.p. $>1-e^{-n/18}$.")
F("PP9", "proof", "F64", "Proof of Corollary 2", proves="CP2", proof_strategy=["direct"],
  statement_short="$||A^\\dagger||_2=1/\\sigma_k(A)$; apply Szarek's lower tail with $t=1/3$ and $n\\ge 4k$.")
F("LP7", "lemma", "F66", "Johnson-Lindenstrauss concentration for a finite set", origin="external",
  origin_citation="Shalev-Shwartz & Ben-David 2014; Johnson-Lindenstrauss (Dasgupta & Gupta 2003)",
  statement_short="A $k\\times n$ Gaussian $N(0,1/k)$ matrix preserves squared norms of all vectors in $Q$ within $\\epsilon$ w.p. $>1-\\delta$.")
N("PP10", "proof", "Proof of Lemma 7",
  sp("Lemma \\ref{lem:JL_Lemma} is a direct result of the Johnson-Lindenstrauss", "and using the union bound."),
  conf=0.85, proves="LP7", proof_strategy=["probabilistic"],
  statement_short="Apply the Johnson-Lindenstrauss lemma to each vector of $Q$ and take a union bound.")
N("DP28", "definition", "Projected Gaussian design matrices $A_{\\hat{U}}^{(R)}$, $A_{V^T}^{(C)}$",
  sp("We define $A_{\\hat{U}}^{(R)}=A^{(R)}\\hat{U}$", "and $A_{V^{T}}^{(C)}=V^{T}A^{(C)}$."),
  conf=0.85, definiendum=["$A_{\\hat{U}}^{(R)}$", "$A_{V^{T}}^{(C)}$"])
N("ClP16", "claim", "Projected design matrices are Gaussian and of rank r",
  sp("From Lemma \\ref{lem:unitary_normal} $A_{\\hat{U}}^{(R)},A_{V^{T}}^{(C)}", "=r$ with probability $1$."),
  conf=0.75)
N("AssumP1", "assumption", "Without loss of generality SVLS returns the row estimate",
  sp("We assume w.l.o.g that $\\hat{X}=\\hat{X}^{(R)}$", "(see SVLS description)."), conf=0.8)
N("ClP17", "claim", "Closed form of the SVLS row estimate",
  sp("Therefore, from eq. (\\ref{eq:close_formula_alg2}) we have", "A_{\\hat{U}}^{(R)^{T}}B^{(R)}$."), conf=0.7)
N("DP29", "definition", "Moore-Penrose pseudoinverses of the projected design matrices",
  sp("We denote by $\\psuedoinv{A_{\\hat{U}}^{(R)}}=", "of $A_{\\hat{U}}^{(R)}$ and $A_{V^{T}}^{(C)}$, respectively."),
  conf=0.85, definiendum=["$\\psuedoinv{A_{\\hat{U}}^{(R)}}$", "$\\psuedoinv{A_{V^{T}}^{(C)}}$"])
F("LP8", "lemma", "F69", "Three-part decomposition of the SVLS error",
  assumptions=["Let $A^{(R)}$ and $A^{(C)}$ be as in the GRC model and $Z^{(R)},Z^{(C)}$ be noise matrices",
               "Let $\\hat{X}$ be the output of SVLS\\!"],
  conclusions=["\\[ ||X-\\hat{X}||_{F}\\leq\\mathbf{I+II+III} \\]"],
  statement_short="$||X-\\hat{X}||_F\\le$ I + II + III: two terms from the rank-$r$ truncation error of $B^{(C)}$ and one from the row noise.")
F("PP11", "proof", "F71", "Proof of Lemma 8", proves="LP8", proof_strategy=["algebraic_manipulation"],
  statement_short="Triangle inequality splits off the noise term; rewrite $X$ through $B^{(C,0)}$ and subtract the annihilated $B^{(C)}_{(r)}$.")
F("ClP18", "claim", "F77", "Claim 1: truncation error bounded by twice the column noise",
  conclusions=["$||B^{(C,0)}-\\svdtop{B^{(C)}}r||_{2}\\leq2||Z^{(C)}||_{2}$"])
F("PP12", "proof", "F78", "Proof of Claim 1", proves="ClP18", proof_strategy=["direct"],
  statement_short="$B^{(C)}_{(r)}$ is the best rank-$r$ approximation of $B^{(C)}$; triangle inequality.")
N("ClP19", "claim", "Matrix norm inequalities",
  sp("The proof\nuses the following inequalities for matrix norms", "\\label{eq:three_matrix_inequalities}\n\\end{align}"),
  conf=0.75, **STD)
F("PP13", "proof", "F81", "Proof of Theorem 3", proves="TP9", proof_strategy=["probabilistic", "direct"],
  statement_short="Bound I, II, III of Lemma 8 by Claim 1, the pseudoinverse bound (Corollary 2) and JL (Lemma 7); union bound. Term II applies JL to the rank-$2r$ truncation error.")
N("ClP20", "claim", "Recovery performance insensitive to n",
  sp("Recovery performance was insensitive to $n$.", "insensitive to $n$."), conf=0.65, rigor="numerical")
N("ClP21", "claim", "Relative error converges to a constant as n, k, r grow",
  sp("Again, the relative error converges rapidly", "independent of $n,k,r$ ."), conf=0.65, rigor="numerical")
F("AP6", "algorithm", "F92", "One-pass low rank approximation algorithm (Halko-Martinsson-Tropp)",
  origin="external", origin_citation="Halko, Martinsson & Tropp 2011",
  input=["$A^{(R)},A^{(C)},B^{(R)},B^{(C)}$"], output=["$\\hat{X}=Q^{(C)}YQ^{(R)^{T}}$"],
  statement_short="QR-factor $B^{(C)}$ and $B^{(R)T}$, solve a least-squares core $Y$, return $Q^{(C)}YQ^{(R)T}$.")
N("ClP22", "claim", "SVLS_P and SVLS have nearly equal error",
  sp("The $RRMSE$ for $SVLS_P$ was lower than", "very small and negligible."), conf=0.7, rigor="numerical")
N("ClP23", "claim", "RCMC with the elbow method estimates rank better than MC",
  sp("Our simulation results, shown in Figure \\ref{fig:rank_estimation}, indicate", "rank estimation of $X$."),
  conf=0.7, rigor="numerical")
N("DP30", "definition", "Measured entries $E(\\mathcal{A})$ and unmeasured entries $\\bar{E}$",
  sp("For each single-entry measurements operator", "$(i,j)\\in [n_1]\\times [n_2]$."),
  conf=0.85, definiendum=["$E(\\mathcal{{A}})$", "$\\bar{E}$"])
N("DP31", "definition", "Restriction $X^{\\bar{E}}$ to unmeasured entries",
  sp("We define $X^{\\bar{E}}$ to be a matrix such that", "and $0$ otherwise."),
  conf=0.85, definiendum="$X^{\\bar{E}}$")
N("ClP24", "claim", "No overfitting: RRMSE on unobserved entries matches overall RRMSE",
  sp("The results of OptSpace\\!, SVT and SVLS stay similar", "does not show overfitting."),
  conf=0.7, rigor="numerical",
  also_stated_at=[clean(sp("Results, shown in the Appendix, Section \\ref{sec:test error}, indicate", "no overfitting is observed."))])

for eid, fid, name in EQS:
    F(eid, "equation", fid, name)

# ================= steps =================
for aid, fid, first in (("AP1", "F9", 1), ("AP2", "F12", 4), ("AP6", "F92", 9)):
    st = pseudocode_steps(facts, fid, BYID[aid], first_seq=first)
    for s in st:
        s["statement"] = s["statement"]
        nodes.append(s); BYID[s["id"]] = s
SUB = {"ASP1": ("compute", "Basis $\\hat{U}$ of the column space of $B^{(C)}$", None),
       "ASP2": ("solve", "Solve the linear systems for $Y$", None),
       "ASP3": ("return", "Output $\\hat{U}Y$", None),
       "ASP4": ("compute", "Top-$r$ left singular vectors of $B^{(C)}$", None),
       "ASP5": ("solve", "Least squares for $\\hat{Y}$", "Least-squares fit of row measurements given $\\hat{U}$, with closed form when $A^{(R)}\\hat{U}$ has rank $r$."),
       "ASP6": ("compute", "Row estimate $\\hat{X}^{(R)}$", None),
       "ASP7": ("compute", "Symmetric column estimate $\\hat{X}^{(C)}$", "Repeat steps 1-3 with rows and columns swapped."),
       "ASP8": ("select", "Keep the lower-loss estimate", "Choose between $\\hat{X}^{(R)}$ and $\\hat{X}^{(C)}$ by the loss $\\mathcal{F}$."),
       "ASP9": ("compute", "QR decompositions of $B^{(C)}$ and $B^{(R)T}$", None),
       "ASP10": ("solve", "Least-squares core $Y$", None),
       "ASP11": ("return", "Return $Q^{(C)}YQ^{(R)T}$", None)}
for sid, (sub, name, short) in SUB.items():
    BYID[sid]["subclass"] = sub; BYID[sid]["name"] = name
    if short:
        BYID[sid]["statement_short"] = short

STEPS("AP3", [
 ("ASP12", "Factored loss $\\mathcal{L}(W,S)$", "The gradient descent stage is performed directly", "\\label{eq:loss_function_W_S}\n\\end{equation}", "initialize", "Parametrize $\\hat{X}=WS$ and define the factored loss."),
 ("ASP13", "Start from the SVLS estimate", "We want to minimize eq. (\\ref{eq:loss_function_W_S})", "may accelerate convergence.", "initialize", "Initialize gradient descent at the SVLS output."),
 ("ASP14", "Gradients in $W$ and $S$", "The gradient of $\\mathcal{\\mathcal{{L}}}$ is (using the chain rule)", "\\label{eq:-1}\n\\end{equation}", "compute", "Chain-rule gradients of $\\mathcal{L}$ in $W$ and $S$."),
], kind="algorithm_step", conf=0.7)
STEPS("AP4", [
 ("ASP15", "Elbow estimate from $B^{(C)}$", "For the noisy case we estimate $rank(X)$ from", "\\label{eq:rank_estimation}\n\\end{equation}", "compute", "Largest ratio of consecutive singular values of $B^{(C)}$."),
 ("ASP16", "Average with the row estimate", "We compute similarly $\\hat{r}^{(R)}$", "\\frac{\\hat{r}^{(C)}+\\hat{r}^{(C)}}{2}\\right)$.", "compute", "Same for $B^{(R)}$; round the average."),
], kind="algorithm_step", conf=0.7)

STEPS("PP1", [
 ("PSP1", "Gaussian noise has spectral norm $O(\\tau\\sqrt{n})$", "Theorem \\ref{thm:the_noisy_case} applies for any $Z^{(C)}$", "with probability\n$1-e^{-2n}$.", "bound_estimate", "Bound $||Z||_2\\le 4\\tau\\sqrt{n}$ via Szarek's inequality."),
 ("PSP2", "Conclude the corollary", "We therefore get the next Corollary", "additive Gaussian noise:", "conclude", "Substitute into Theorem 3."),
])
STEPS("PP2", [
 ("PSP3", "Common column space", "First, $rank(X_{2}A^{(C)})=rank(X_{1}A^{(C)})=r$", "a basis for this subspace.", "other", "Both have full-rank column measurements, so their column spaces coincide; take a basis $U$."),
 ("PSP4", "Factor through $U$", "For $X_{1},X_{2}$ there are $Y_{1},Y_{2}", "Therefore $A^{(R)}UY_{1}=A^{(R)}UY_{2}$.", "introduce_variable", "Write $X_i=UY_i$; row measurements agree."),
 ("PSP5", "Invertibility gives $Y_1=Y_2$", "Since $rank(A^{(R)}UY_{1})=r$ and", "=UY_{1}=UY_{2}=X_{2}$.", "conclude", "$A^{(R)}U$ has rank $r$, so $Y_1=Y_2$ and $X_1=X_2$."),
])
STEPS("PP3", [
 ("PSP6", "$\\hat{U}$ spans $span(X)$", "$span(XA^{(C)})\\subseteq span(X)$ and", "is a basis for $span(X)$.", "other", "The column measurements span the column space of $X$."),
 ("PSP7", "Factor $X=\\hat{U}Y$", "We can write $X=\\hat{U} Y$ for some matrix", "we have $rank(A^{(R)}\\hat{U})=r$.", "introduce_variable", "Write $X=\\hat{U}Y$; $A^{(R)}\\hat{U}$ has rank $r$."),
 ("PSP8", "Verify both equalities", "Thus eq. (\\ref{eq:algorithm1}) gives $\\hat{X}$ in closed form", "\\label{eq:Col_equllity}\n\\end{align}", "conclude", "Substitute in the closed form to get (16) and (17)."),
])
STEPS("PP5", [
 ("PSP9", "$V^TA^{(C)}$ has rank $r$ a.s.", "Let $U\\Sigma V^{T}$ be the $SVD$ of $X$. From Lemma", "$P(rank(V^{T} A^{(C)})=r)=1$.", "apply_lemma", "Lemma 3: $V^TA^{(C)}$ is Gaussian, hence of rank $r$ a.s."),
 ("PSP10", "Measurements have rank $r$ a.s.", "Since $B^{(C)}=U\\Sigma V^{T} A^{(C)}$", "In the same way $P(rank(B^{(R)})=r)=1$.", "other", "Hence $B^{(C)}$ and $B^{(R)}$ have rank $r$ a.s."),
 ("PSP11", "Combine Lemmas 1 and 2", "Combining Lemma \\ref{lem:hatX_is_X} with", "give us the required result.", "conclude", "Lemmas 2 and 1 give $\\hat{X}=X$."),
])
STEPS("PP6", [
 ("PSP12", "$Z$ as a supremum", "We know that $Z=||Y||_{2}=sup", "f_{1},f_{2}\\in F_{V}$.", "setup", "Express the spectral norm as a supremum over unit vectors."),
 ("PSP13", "Function class with zero mean", "Let $F$ be the set of all functions $f$", "we have $E(f(Y_{i}))=0$.", "introduce_variable", "Define the function class; each $f(Y_i)$ is centered."),
 ("PSP14", "Uniform bound", "From the incoherence of $U$ we conclude that", "\\leq p^{-1}\\frac{r}{n}\\mu. \\end{equation}", "bound_estimate", "Incoherence bounds $|f(Y_i)|\\le p^{-1}\\mu r/n$."),
 ("PSP15", "Variance bound", "In addition\n\\[\nE (f^{2}(Y_{i}))", "\\leq p^{-1}\\frac{r}{n}\\mu.$", "bound_estimate", "Sum of variances is at most $p^{-1}\\mu r/n$."),
 ("PSP16", "Apply Talagrand", "We can take $B=2p^{-1}\\frac{r}{n}\\mu$", "finishes our proof.", "conclude", "Talagrand's inequality with $\\log(1+u)\\ge\\log 2\\min(1,u)$."),
])
STEPS("PP7", [
 ("PSP17", "Expand in the standard basis", "(Lemma \\ref{lemma: uniqnes_MC}) Represent any vector", "\\langle w,P_{U}(e_{i}) \\rangle e_{i}$.", "setup", "Write $P_U(w)$ in the standard basis."),
 ("PSP18", "Recall the sampling variables", "Recall the $r_i$ Bernoulli variables", "as in Lemma \\ref{lem:bound_Z-1}.", "setup", "Recall $r_i$ and define $Y_i$, $Z$ as in Lemma 6."),
 ("PSP19", "Sum of rank-one projections and expectation bound", "We get\n\n\\begin{align}\nP_{A^{(R)^{T}}}P_{U}(w)", "\\leq 1.\n\\end{equation}", "apply_lemma", "$P_UP_{A^{(R)T}}P_U=\\sum_i r_iP_Ue_i\\otimes P_Ue_i$; incoherence and Lemma 5 bound its expected deviation."),
 ("PSP20", "Concentration and constant", "For $\\beta > 1$ which satisfy the lemma's requirement", "finishes our proof.", "conclude", "Lemma 6 with $\\lambda=\\sqrt{\\beta/\\gamma}$; set $C_R=C+1/\\sqrt{\\gamma}$."),
])
STEPS("PP8", [
 ("PSP21", "Apply Lemma 4 to rows and columns", "From Lemma \\ref{lemma: uniqnes_MC} and using a union bound", "A^{(C)}A^{(C)^{T}}V||_{2}<1$.", "apply_lemma", "Lemma 4 for rows and columns plus union bound."),
 ("PSP22", "Smallest singular value positive", "Since\nthe singular values of $p^{(R)} \\identity r-", "and similarly for $V^{T}A^{(C)}A^{(C)^{T}}V$.", "bound_estimate", "Hence $\\sigma_r(U^TA^{(R)T}A^{(R)}U)>0$."),
 ("PSP23", "Full rank measurements", "Therefore \n$rank(A^{(R)}U)=rank(V^{T}A^{(C)})=r$", "with probability $>1-6min(n_1,n_2)^{-\\beta}$.", "other", "So $A^{(R)}X$ and $XA^{(C)}$ have rank $r$."),
 ("PSP24", "Conclude by Lemmas 2 and 1", "From Lemma \\ref{lem:hatX_is_X}\nwe get", "we get $X=\\hat{X}$ with probability $>1-6min(n_1,n_2)^{-\\beta}$.", "conclude", "Lemmas 2 and 1 give $X=\\hat{X}$."),
])
STEPS("PP11", [
 ("PSP25", "Split off the noise term", "We represent $||X-\\hat{X}||_{F}$ as follows", "where we have used the triangle inequality.", "algebraic_manipulation", "Substitute $B^{(R)}=A^{(R)}X+Z^{(R)}$; triangle inequality isolates III."),
 ("PSP26", "Rewrite through $B^{(C,0)}$", "We next use the following\nequality", "because $V$ is orthogonal.", "algebraic_manipulation", "Use $XA^{(C)}A_{V^T}^{(C)\\dagger}V^T=X$."),
 ("PSP27", "Annihilate $B^{(C)}_{(r)}$", "Since $\\hat{U}$ is a basis for $span(\\svdtop{B^{(C)}}r)$", "\\label{eq:L_and_U}\n\\end{equation}", "algebraic_manipulation", "The operator kills $B^{(C)}_{(r)}$."),
 ("PSP28", "Bound by I+II", "Therefore\n\\begin{align}\n||(\\identity n-\\hat{U}\\psuedoinv{A_{\\hat{U}}^{(R)}}A^{(R)})B^{(C,0)}", "gives the required result.", "conclude", "Subtract $B^{(C)}_{(r)}$ and use the triangle inequality."),
])
STEPS("PP13", [
 ("PSP29", "Plan", "(Theorem \\ref{thm:the_noisy_case}) We prove (probabilistic)", "in Lemma \\ref{lem:three_parts(X-hatX)}.", "setup", "Bound each term of Lemma 8."),
 ("PSP30", "Bound on I", "We have\n\\begin{equation}\nrank\\left((B^{(C,0)}", "\\label{eq:bound_A1}\n\\end{equation}", "bound_estimate", "Rank-$r$ Frobenius-spectral bound, Corollary 2 and Claim 1."),
 ("PSP31", "Bound on II", "$\\hat{U}$ is orthogonal and can be omitted from", "\\label{eq:bound_A2}\n\\end{equation}", "bound_estimate", "Corollary 2 twice and Lemma 7 (JL) on the rank-$2r$ error, then Claim 1."),
 ("PSP32", "Bound on III", "$rank(\\psuedoinv{A_{\\hat{U}}^{(R)}})\\leq r$ and from Corollary", "\\label{eq:Z(R)_bound}\n\\end{align}", "bound_estimate", "Corollary 2 bounds the pseudoinverse acting on the row noise."),
 ("PSP33", "Union bound", "Hence we have constants $C_{3}$ and $c_{3}$ such that,", "concludes our proof.", "conclude", "Combine the three bounds by a union bound."),
], conf=0.75)
for sid in ("PSP30", "PSP31", "PSP32"):
    BYID[sid]["confidence"] = 0.95

# ================= edges =================
# proofs argued in prose
E("PP1", "CP1", 0.85, "named", type="proves")
E("PP10", "LP7", 0.85, "named", type="proves")
# intro / prior work
E("DP1", "DP2", 0.8); E("DP1", "DP3", 0.8); E("DP3", "TP1", 0.85); E("DP4", "TP3", 0.85)
# preliminaries
for t in ("DP15", "DP16", "DP17", "ProbP1", "DP24", "DP26", "ExP1", "AP1", "LP1", "LP2", "TP7", "LP3",
          "AP3", "LP4", "LP6", "TP11", "CP2", "LP7"):
    E("DP5", t, 0.8)
for t in ("TP7", "CP1", "PP1"):
    E("DP6", t, 0.75)
for t in ("DP24", "ExP1", "TP8", "TP9", "CP1", "DP27", "LP8", "ClP18", "ClP19", "PP13", "LP4", "ClP15",
          "AP2", "ProbP1", "PP12", "AP6"):
    E("DP7", t, 0.8)
for t in ("DP24", "DP25", "LP5", "LP7"):
    E("DP8", t, 0.75)
for t in ("PP2", "PP3", "PP11"):
    E("DP9", t, 0.8)
E("DP10", "DP16", 0.8); E("DP10", "AP1", 0.8)
E("DP11", "DP16", 0.75)
for t in ("DP16", "AP4", "LP6", "DP30", "ExP1"):
    E("DP12", t, 0.75)
E("DP13", "PP4", 0.8)
for t in ("DP23", "ClP1", "LP3", "LP7", "CP1", "CP2", "TP11", "ClP16"):
    E("DP14", t, 0.8)
for t in ("DP16", "DP26", "TP7", "PP5", "AP2", "DP28", "ExP1", "PP11"):
    E("DP15", t, 0.8)
for t in ("AP2", "LP8", "ClP18", "PP13", "ProbP2", "TP5", "PP12"):
    E("DP16", t, 0.8)
for t in ("DP18", "AP1", "LP2", "AP2", "DP19", "DP23", "LP8", "ClP18", "AP6", "AP5", "RP1", "DP28"):
    E("DP17", t, 0.8)
for t in ("ProbP1", "AP2", "TP9", "CP1", "AP4", "LP8", "ClP18", "PP11", "TP6"):
    E("DP18", t, 0.8)
E("ProbP1", "AP2", 0.7, "inferred", type="resolves")
E("ProbP1", "AP3", 0.8); E("ProbP1", "ClP1", 0.8)
E("DP19", "DP20", 0.75); E("DP19", "DP21", 0.75); E("DP19", "DP22", 0.75)
E("DP20", "DP21", 0.8); E("DP20", "DP22", 0.8)
for t in ("ClP4", "ExP1", "TP7", "RP2", "ClP8", "ClP9", "ClP10", "LP4", "PP7", "OpenP1", "ClP23", "ClP24", "ClP15", "RP1"):
    E("DP19", t, 0.8)
for t in ("TP7", "LP4", "ClP15", "PP8"):
    E("DP20", t, 0.8)
E("DP21", "PP7", 0.8); E("DP21", "LP4", 0.75)
for t in ("TP6", "TP9", "CP1", "ClP2", "ClP3", "ClP11", "LP8", "PP13", "ClP22", "ClP14"):
    E("DP23", t, 0.8)
E("DP24", "TP4", 0.85); E("DP24", "ClP2", 0.85)
for t in ("TP4", "ClP2", "TP8", "ClP11"):
    E("DP3", t, 0.8)
for t in ("DP26", "LP4", "LP6", "TP7", "PP7"):
    E("DP25", t, 0.85)
E("DP26", "ClP4", 0.8); E("DP26", "PP7", 0.75)
E("ClP4", "ExP1", 0.9, "named", type="illustrates")
# section 3
E("AP1", "ClP5", 0.8, "inferred"); E("AP1", "ClP6", 0.85, "named")
E("AP1", "AP2", 0.7, "inferred"); E("ClP5", "AP2", 0.7, "named")  # "in closed form as before"
E("AP2", "AP3", 0.9, "named"); E("DP18", "AP3", 0.8)
E("DP15", "AP4", 0.8)
E("DP7", "ProbP2", 0.8)
E("ProbP2", "TP5", 0.9, "named", type="resolves")
E("AP2", "AP5", 0.9, "named"); E("AP6", "AP5", 0.85, "named"); E("DP15", "AP5", 0.75); E("DP18", "AP5", 0.8)
# section 4
E("TP8", "TP9", 0.85, "named", mention=True)
E("AP2", "TP9", 0.9, "named"); E("AP2", "LP8", 0.9, "named")
E("TP11", "PP1", 0.85, "named")
E("ClP7", "ClP8", 0.7, "inferred")
E("ClP5", "PP3", 0.85, "named")
# section 5
for t in ("ClP8", "ClP9", "ClP10", "ClP12", "ClP13", "ClP22", "ClP24", "ClP14"):
    E("DP27", t, 0.8)
E("AP1", "ClP8", 0.8, "inferred")
for t in ("ClP9", "ClP10", "ClP13", "ClP22", "ClP24", "ClP14"):
    E("AP2", t, 0.8, "named")
E("TP9", "ClP14", 0.95, mention=True, basis=None)
E("ClP20", "ClP14", 0.7, "inferred"); E("ClP21", "ClP14", 0.7, "inferred")
E("AP5", "ClP22", 0.85, "named"); E("AP4", "ClP23", 0.9, "named")
E("DP30", "DP31", 0.85); E("DP31", "ClP24", 0.8); E("DP1", "DP30", 0.7)
# appendix
E("ClP15", "PP8", 0.7, "inferred")
E("DP28", "ClP16", 0.85); E("AP2", "AssumP1", 0.85, "named")
E("AssumP1", "ClP17", 0.85, "inferred"); E("DP28", "ClP17", 0.85)
E("DP28", "DP29", 0.85)
for t in ("LP8", "PP11", "PP13"):
    E("DP28", t, 0.8); E("DP29", t, 0.85)
E("ClP17", "PP11", 0.8, "inferred")
E("TP5", "PP12", 0.7, "inferred")
E("ClP19", "PP13", 0.9, "named"); E("ClP16", "PP13", 0.8, "inferred")
E("DP17", "AP4", 0.7)
for t in ("ClP5", "ClP6", "LP1", "PP2", "PP3", "LP3", "PP4", "PP8", "PP11", "PP12", "PP13"):
    E("DP17", t, 0.8)
for t in ("PP5", "PP12", "AP6", "ClP1", "PP1", "PP13"):
    E("DP18", t, 0.8)

for e in edges:
    if e.get("basis") is None:
        e.pop("basis", None)

nonformal = sum(1 for n in nodes if "rigor" in n)
NOTES = [
 {"category": "source_problem", "nodes": ["ExP1"],
  "note": "Arithmetic slip: with sigma_1=(sqrt2+1)n/3 and sigma_2=(sqrt2-1)n/3 the nuclear norm of X_0 is 2*sqrt2*n/3 (about 0.94n), not n*sqrt2/3 as written; the conclusion ||X_0||_* < ||X||_* = n still holds."},
 {"category": "source_problem", "nodes": ["AP4"],
  "note": "The rank estimator is printed as round((r^(C)+r^(C))/2); the text says it averages r^(C) and r^(R), so the second term should be r^(R)."},
 {"category": "source_problem", "nodes": ["PP13", "TP9"],
  "note": "In the proof of Theorem 3 the final bounds (bound_A2), (bound_A3) are stated as C_2||Z^(C)||_2 and C_3||Z^(R)||_2, dropping the sqrt(r/k) factor derived just before them and required by the theorem; there is also a stray fragment '$>1-e^{-c_3k}$.' before (bound_A3)."},
 {"category": "source_problem", "nodes": ["PP6", "PP7", "TP10"],
  "note": "Proof of Lemma 6 sets gamma=-log(2)/K, which is negative (should be log(2)/K); the proof of Lemma 4 says 'gamma as in Theorem 4' but gamma is defined in Lemma 6; Talagrand's bound is printed with log(1+t/(sigma+Br)), where r looks like a typo (the standard form has B*E(Z) there)."},
 {"category": "source_problem", "nodes": ["PP9", "PP4", "ClP15", "DP18"],
  "note": "Minor typos: probability '1-e^{nt^2/2}' (sign missing) in the proof of Corollary 2; 'N(0, sigma I_n)' for the covariance (sigma^2) in Lemma 3's proof; 'p{-1}' in (22); Z^(R) is declared n_1 x k^(R) and Z^(C) k^(C) x n_2, transposed relative to A^(R)X and XA^(C)."},
 {"category": "source_problem", "nodes": ["TP7", "DP19", "OpenP1"],
  "note": "Section 4.1.2 says RCMC rows and columns are 'sampled with replacement', but the model of Section 2 (and Theorem 2's proof) is independent Bernoulli inclusion, i.e. without replacement. The Discussion calls recovery guarantees for RCMC a future challenge although Theorem 2 proves noiseless RCMC recovery; OpenP1 reads it as the noisy case."},
 {"category": "source_problem", "nodes": ["PP12", "AP6"],
  "note": "Claim 1's proof appeals to B^(C)_(r) being closest in Frobenius norm but bounds the spectral-norm distance (Eckart-Young holds for both, so the step is fine but the stated reason does not match). In the Halko et al. algorithm, step 2 'argmin_C ||Q^(C)B^(C) - C Q^(R)T B^(R)T||' is dimensionally inconsistent as printed (Q^(C)T is presumably meant)."},
 {"category": "type_uncertain", "nodes": ["LP3", "LP6"],
  "note": "Lemma 3 (rotation invariance of Gaussian matrices) is a standard fact but the paper proves it without attribution, so kept origin paper; Lemma 6 is attributed to Candes & Recht (Thm 4.2) and re-proved, so it is external with a paper proof."},
 {"category": "boundary_uncertain", "nodes": ["DP28", "ClP16", "AssumP1", "ClP17", "AP5"],
  "note": "The set-up of the proof of Theorem 3 sits in running text before Lemma 8, outside any proof environment; it was split into definitions, a w.l.o.g. assumption and two claims used by the proofs. SVLS_P is a one-display modification of SVLS and gets no steps."},
]
graph = {"metadata": {
    "title": "Low-Rank Matrix Recovery from Row-and-Column Affine Measurements",
    "arxiv_id": "1505.06292",
    "authors": ["Avishai Wagner", "Or Zuk"], "year": 2015,
    "annotator": "agent-extraction", "model": "claude-opus-5-5", "effort": "default",
    "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3", "extraction_date": "2026-11-05",
    "rigor_nonformal_count": nonformal,
    "paper_style": ["theorem_proof", "computational"],
    "extraction_notes": NOTES,
    "extraction_comment": ""},
    "nodes": nodes, "edges": edges}

if __name__ == "__main__":
    report = finalize(graph, tex)
    for w in report["warnings"]:
        print("WARN", w)
    print("ERRORS", report["errors"])
    assert not report["errors"], report["errors"]
    print({k: (len(v) if isinstance(v, list) else v) for k, v in report.items()})
    json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
    print("wrote", OUT, len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
