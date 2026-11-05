#!/usr/bin/env python3
"""Build the SARANGA v7 graph of arXiv 1912.05769 (Tenzer, Mandel, Zuk:
Testing Independence under Biased Sampling). Run from anywhere:
    python3 corpus/orzuk/1912_05769/scripts/build.py
"""
import json, os, re, subprocess, sys
REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize, pseudocode_steps
from latex_facts import read_tex

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
TEX = PAPER + "/arxiv_src/TIBS_arxiv.tex"
OUT = PAPER + "/1912_05769.json"
SCR = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_orzuk/1912_05769"
os.makedirs(SCR, exist_ok=True)
FACTS = SCR + "/facts.json"
if not os.path.exists(FACTS):
    subprocess.check_call([sys.executable, REPO + "/src/latex_facts.py", TEX, "--out", FACTS])
facts = json.load(open(FACTS))
src = facts["source"]
FA = {f["id"]: f for f in facts["facts"]}
SECS = [s for s in facts["sections"] if s["inside"] is None]
SEC = {s["id"]: s for s in facts["sections"]}

LABEL = re.compile(r"\\label\{[^{}]*\}")
# normalized source (labels dropped, whitespace collapsed) with a map to raw offsets
norm_chars, idx = [], []
i = 0
while i < len(src):
    m = LABEL.match(src, i)
    if m:
        i = m.end(); continue
    c = src[i]
    if c.isspace():
        if norm_chars and norm_chars[-1] != " ":
            norm_chars.append(" "); idx.append(i)
    else:
        norm_chars.append(c); idx.append(i)
    i += 1
NORM = "".join(norm_chars)

def clean(t):
    return re.sub(r"\s+", " ", LABEL.sub(" ", t)).strip()

def sec_name(s):
    return (s["number"] + " " if s["number"] else "") + s["title"]

def section_at(pos):
    cur = None
    for s in SECS:
        if s["start"] <= pos:
            cur = s
    return sec_name(cur) if cur else ""

POS = {}
def P(a, b, after=None):
    """verbatim prose span from snippet a to snippet b (normalized source)."""
    start = 0 if after is None else NORM.find(after)
    i = NORM.find(a, start)
    assert i >= 0, ("start not found", a)
    assert NORM.find(a, i + 1) < 0 or after is not None, ("start not unique", a)
    j = NORM.find(b, i)
    assert j >= 0, ("end not found", b)
    return NORM[i:j + len(b)].strip(), idx[i]

nodes, edges = [], []
def add(nid, typ, name, stmt, pos=None, fact=None, **kw):
    if fact is not None:
        f = FA[fact]
        stmt = clean(src[f["start"]:f["end"]])
        pos = f["start"]
        sec = sec_name(SEC[f["section"]]) if f.get("section") else section_at(pos)
        kw.setdefault("confidence", 1.0)
    else:
        sec = section_at(pos)
    n = {"id": nid, "type": typ, "name": name, "statement": stmt, "section": sec,
         "origin": kw.pop("origin", "paper")}
    n.update(kw)
    n.setdefault("confidence", 0.75)
    nodes.append(n)
    POS[nid] = pos
    return n

def prose(nid, typ, name, a, b, after=None, **kw):
    s, p = P(a, b, after)
    return add(nid, typ, name, s, pos=p, **kw)

def E(s, t, typ="uses", conf=0.8, basis="inferred", **kw):
    e = {"source": s, "target": t, "type": typ, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)

ESEQ = [0]
def eq(nid, fact, name, **kw):
    return add(nid, "equation", name, None, fact=fact, **kw)

# ---------------------------------------------------------------- 1 Introduction
QI_INTRO, _ = P("However, because $F_{XY}$ is not identifiable on", "\\citep{tsai1990testing}.")

# ---------------------------------------------------------------- 2 Preliminaries
prose("DP1", "definition", "Population distribution $F_{XY}$",
      "Let $F_{XY}$ be a bivariate distribution function", "univariate marginals $f_{X}, f_{Y}$.",
      definiendum=["$F_{XY}$", "$f_{XY}$", "$f_{X}, f_{Y}$"], confidence=0.85)
prose("DP2", "definition", "Biased (weighted) sampling density",
      "We consider $n$ independent pairs", "0 < \\mathbb{E}_{f_{XY}}\\{{w}(X,Y)\\} < \\infty$.",
      definiendum=["$f^{(w)}_{X,Y}$", "${w}$"], genus="joint density",
      differentia=["{w}(x,y) f_{XY}(x,y)/\\mathbb{E}_{f_{XY}} \\{{w}(X,Y)\\}"],
      statement_short="Observed pairs are i.i.d. from the density proportional to $w(x,y)f_{XY}(x,y)$, with $w\\ge 0$ a weight function of finite positive mean.",
      confidence=0.85, tags=["biased_sampling", "weighted_distribution"])
eq("EP1", "F1", "Weighted density")
prose("DP3", "definition", "Observed marginals $f^{(w)}_X, f^{(w)}_Y$",
      "The marginals of the observed data are denoted by", "f_{XY}^{(w)}(x,y) dx$.",
      definiendum=["$f_{X}^{(w)}$", "$f_{Y}^{(w)}$"], confidence=0.85)
prose("DP4", "definition", "Weighted independent density $[f_X f_Y]^{(w)}$",
      "The weighted independent density is defined as", "weighted distribution $[F_{X} F_{Y}]^{(w)}$.",
      definiendum="weighted independent density", confidence=0.9)
prose("DP5", "definition", "Truncation weight function",
      "An important special case is that of a truncated sample in which",
      "for some set $\\mathcal{A} \\subset \\mathbb{R}^2$.",
      definiendum="truncated sample", confidence=0.8, tags=["truncation"])
eq("EP2", "F2", "Truncation weight $w=\\mathbb{1}_{\\mathcal{A}}$")
add("DP6", "definition", "Quasi-independence", None, fact="F3",
    definiendum="quasi-independent", genus="joint distribution $F_{XY}^{(w)}$",
    differentia=["there exist density functions $\\tilde{f_{X}}$ and $\\tilde{f_{Y}}$"],
    also_stated_at=[QI_INTRO],
    statement_short="$F^{(w)}_{XY}$ is quasi-independent w.r.t. $w$ if its CDF is proportional to the $w$-tilted product of some densities $\\tilde f_X\\tilde f_Y$; else quasi-dependent.",
    tags=["quasi_independence"])
eq("EP3", "F4", "Quasi-independence condition")
prose("ProbP1", "problem", "Testing quasi-independence",
      "Based on the sample $\\mathcal{D} =", "H_1: & \\textrm{otherwise} \\end{array} \\end{equation}",
      statement_short="Test $H_0$: $F^{(w)}_{XY}$ is quasi-independent against the alternative, from an i.i.d. biased sample $\\mathcal{D}$.",
      confidence=0.85, tags=["hypothesis_testing"])
eq("EP4", "F5", "Hypotheses $H_0$ / $H_1$")
add("RP1", "remark", "Quasi-dependence implies dependence", None, fact="F6", rigor="semi_formal")
add("RP2", "remark", "Quasi-independence does not imply independence", None, fact="F7", rigor="semi_formal",
    statement_short="Where $w$ vanishes, quasi-independence can hold without independence, with $\\tilde F_X\\ne F_X$ or $\\tilde F_Y\\ne F_Y$.")
prose("DP7", "definition", "Unordered samples $\\mathcal{D}_x, \\mathcal{D}_y$",
      "We denote by $\\mathcal{D}_x, \\mathcal{D}_y$", "respectively.",
      definiendum=["$\\mathcal{D}_x$", "$\\mathcal{D}_y$"], confidence=0.85)
prose("DP8", "definition", "Partially unordered sample $(x, \\mathcal{D}_y)$",
      "For convenience, we often keep the indices", "empirical distribution of the $y_i$'s.",
      definiendum="$(x, \\mathcal{D}_y)$", confidence=0.8)

# ---------------------------------------------------------------- 3.1
prose("DP9", "definition", "Permuted sample $\\pi(\\mathcal{D})$",
      "Let $\\pi(y)$ be the vector $y$", "(x_n, y_{\\pi(n)})\\big)$.",
      definiendum=["$\\pi(y)$", "$\\pi(\\mathcal{D})$"], confidence=0.85)
prose("DP10", "definition", "Weight matrix $\\mathcal{W}$",
      "For a sample $\\mathcal{D}=\\{(x_i, y_i)\\}_{i=1}^n$, let $\\mathcal{W}", "\\mathcal{W}(i,j) \\equiv {w}(x_i, y_j).$",
      definiendum="$\\mathcal{W}$", genus="weight-matrix", confidence=0.85)
prose("DP11", "definition", "Weighted permutation distribution $P_{\\mathcal{W}}$",
      "Let $S_n$ be the set of all permutations", "given by the permanent of the matrix $\\mathcal{W}$.",
      definiendum=["$S_n$", "$P_{\\mathcal{W}}$", "$per(\\mathcal{W})$"],
      statement_short="$P_{\\mathcal{W}}(\\pi)\\propto\\prod_i \\mathcal{W}(i,\\pi(i))$, normalised by the permanent of $\\mathcal{W}$.",
      confidence=0.9, tags=["permutations", "permanent"])
eq("EP5", "F8", "$P_{\\mathcal{W}}(\\pi)$")
add("ClP1", "claim", "$P_{\\mathcal{W}}$ is the null conditional permutation law", None, fact="F9",
    assumptions=["Under $H_0$"],
    conclusions=["the probability $P_{\\mathcal{W}}(\\pi)$ represents the probability of observing permuted datasets conditional on the marginal sets, that is, $P_{\\mathcal{W}}(\\pi(\\mathcal{D})) = P_0(\\pi \\mid x, \\mathcal{D}_y)$"],
    statement_short="Under quasi-independence, the law of the pairing given both marginal samples is $P_{\\mathcal{W}}$.",
    tags=["permutation_test", "conditional_inference"])
PP1_COPY = clean(src[FA["F46"]["start"]:FA["F46"]["end"]])
add("PP1", "proof", "Proof of Claim 1", None, fact="F10", proves="ClP1",
    also_stated_at=[PP1_COPY], proof_strategy=["direct", "algebraic_manipulation"],
    statement_short="Write the conditional pairing law as a ratio of products of $f^{(w)}$; under the null the $\\tilde f$ factors cancel, leaving $P_{\\mathcal{W}}$.")
eq("EP6", "F11", "Conditional permutation law (general weighted model)",
   also_stated_at=[clean(src[FA["F47"]["start"]:FA["F47"]["end"]])])
prose("ClP2", "claim", "Truncation gives the uniform law on valid permutations",
      "When ${w}(x,y)$ is a truncation function, $P_{\\mathcal{W}}(\\pi)$ is simply", "consistent with the truncation.",
      rigor="semi_formal", confidence=0.7,
      assumptions=["${w}(x,y)$ is a truncation function"],
      conclusions=["$P_{\\mathcal{W}}(\\pi)$ is simply the uniform distribution over the set of valid permutations"])
add("LP1", "lemma", "Double randomization lemma", None, fact="F13",
    assumptions=["Let $\\mathcal{D} \\sim [F_{XY}^{(w)}]^n$", "conditionally on $\\mathcal{D}$ let $\\pi$ be a permutation having the conditional probability law given in Equation \\eqref{eq:generalperm}"],
    conclusions=["$\\pi(\\mathcal{D}) \\sim [F_{XY}^{(w)}]^n$"],
    statement_short="Permuting an i.i.d. biased sample by its conditional pairing law leaves its distribution unchanged.")
add("PP2", "proof", "Proof of Lemma 3.1", None, fact="F14", proves="LP1",
    proof_strategy=["direct"],
    statement_short="Law of total probability over permutations: the sum telescopes to the original product density.")
eq("EP7", "F15", "Density of the permuted sample")
prose("PP3", "proof", "Derivation of Corollary 1",
      "Recalling that under the null, Equation", "(by Claim \\ref{claim:P_W_conditional}), we have",
      proves="CP1", confidence=0.75, proof_strategy=["direct"],
      statement_short="Combine Lemma 3.1 with Claim 1: under the null the conditional law is $P_{\\mathcal{W}}$.")
add("CP1", "corollary", "Null distribution of $P_{\\mathcal{W}}$-permuted data", None, fact="F16", main=True,
    assumptions=["Under the null"],
    conclusions=["permuted data points drawn according to Equation \\eqref{eq:prob_perm} follow the distribution of $n$ independent copies of $(X,Y) \\sim [\\tilde {F_{X}} \\tilde {F_{Y}}]^{(w)}$"],
    statement_short="Under the null, data permuted by $P_{\\mathcal{W}}$ are i.i.d. from the weighted product of the quasi-marginals.",
    tags=["permutation_test", "validity"])

# ---------------------------------------------------------------- 3.2
prose("DP12", "definition", "Test statistic $T$", "Let $T(\\mathcal{D})$ be any test statistic.",
      "Let $T(\\mathcal{D})$ be any test statistic.", definiendum="$T(\\mathcal{D})$", confidence=0.8)
prose("DP13", "definition", "Permutation P-value",
      "In practice, a large number of permutations, $B$, is sampled",
      "where $\\pi_0$ is the identity permutation corresponding to $T(\\mathcal{D})$.",
      definiendum="${P}_{value}$", confidence=0.85,
      statement_short="Empirical P-value: fraction of the $B+1$ permutations (identity included) whose statistic is at least the observed one.")
eq("EP8", "F17", "Empirical permutation P-value")
add("AP1", "algorithm", "Weighted Permutation Test of Quasi-Independence", None, fact="F18", main=True,
    input=["$\\mathcal{D}$ - sample", "${w}(x,y)$ - bias function", "$T : \\mathbb{R}^{2n} \\to \\mathbb{R}$ - a test statistic"],
    output=["$P_{value} \\equiv \\frac{1}{B+1} \\sum_{i=0}^{B} \\indicator{T_i \\geq T_0}$"],
    statement_short="Permutation test with permutations drawn from $P_{\\mathcal{W}}$ instead of uniformly; P-value counts permuted statistics $\\ge$ the observed one.",
    tags=["permutation_test", "hypothesis_testing"])
prose("ClP3", "claim", "Type-1 error control of the weighted permutation test",
      "Corollary \\ref{cor:alpha} assures that", "weighted permutation test is at most $\\alpha$.",
      confidence=0.75, main=True,
      assumptions=["under the null distribution"],
      conclusions=["$P_{value} \\sim U[\\frac{1}{B+1},...,\\frac{B}{B+1},1]$", "the type-1 error probability of the weighted permutation test is at most $\\alpha$"],
      tags=["validity", "type_1_error"])

# ---------------------------------------------------------------- 3.3
prose("DP14", "definition", "Current permutation $\\pi_t$",
      "Let $\\pi_t = (\\pi_t(1),..,\\pi_t(n))$ be the permutation at step $t$.",
      "Let $\\pi_t = (\\pi_t(1),..,\\pi_t(n))$ be the permutation at step $t$.", definiendum="$\\pi_t$", confidence=0.8)
prose("DP15", "definition", "Swap neighbourhood $Neig(\\pi_t)$",
      "Define the neighbours of $\\pi_t$", "\\forall i < j\\}. \\]",
      definiendum="$Neig(\\pi_t)$", genus="permutations obtained from $\\pi_t$ by a single swap", confidence=0.9)
MH_PROSE, _ = P("We then proceed according to the standard MH algorithm", "\\mathcal{W}(j,\\pi_t(j))}. \\]")
add("AP2", "algorithm", "MCMC for Biased Sampling of Permutations", None, fact="F20", main=True,
    input=["$\\mathcal{D}$ - sample", "${w}(x,y)$ - bias function"],
    output=["The resulting $B$ permutations $\\pi_{M_0},\\pi_{M_0+M},..,\\pi_{M_0+B M}$"],
    also_stated_at=[MH_PROSE],
    statement_short="Metropolis-Hastings on permutations with random transpositions, accepting with the ratio of $\\mathcal{W}$ products; thinned output samples $P_{\\mathcal{W}}$.",
    tags=["mcmc", "metropolis_hastings", "permutations", "sampling"])

# ---------------------------------------------------------------- 3.4
prose("DP16", "definition", "Importance-sampling permutation P-value",
      "Due to the difficulty of sampling directly",
      "{\\sum_{i=0}^{B}\\frac{P_{\\mathcal{W}}(\\pi_i)}{P_{IS}(\\pi_i)}}. \\end{equation}",
      definiendum=["$P_{IS}$", "$P_{value}$"], confidence=0.8,
      statement_short="Sample permutations from a proposal $P_{IS}$ and weight the indicator $T_i\\ge T_0$ by $P_{\\mathcal{W}}/P_{IS}$ (self-normalised).",
      tags=["importance_sampling"])
eq("EP9", "F22", "Importance-sampling P-value")
prose("RP3", "remark", "Permanent cancels in the IS P-value",
      "The unknown term $per(\\mathcal{W})$", "known only up to a normalizing constant.", confidence=0.7)
prose("TP1", "theorem", "Harrison's conservative importance-sampling test",
      "\\cite{harrison2012conservative} shows that for any test statistic", "(see his Theorem 1).",
      origin="external", origin_citation="Harrison 2012, Theorem 1", confidence=0.85,
      assumptions=["any test statistic satisfying mild invariance properties"],
      conclusions=["the test that includes the identity permutation in the P-value calculation in Equation \\eqref{eq:IS_pval} controls the type-1 error at level $\\alpha$"],
      tags=["importance_sampling", "validity"])
prose("ClP4", "claim", "Validity of the importance-sampling permutation test",
      "This result applies directly to our case", "conditionally on the data $\\mathcal{D}$.",
      rigor="semi_formal", confidence=0.7,
      conclusions=["This result applies directly to our case"], tags=["validity"])

# ---------------------------------------------------------------- 4.1
add("AP3", "algorithm", "Bootstrap-Based Test of Quasi-Independence", None, fact="F23", main=True,
    input=["$\\mathcal{D}$ - sample", "${w}(x,y)$ - bias function", "$T : \\mathbb{R}^{2n} \\to \\mathbb{R}$ - a test statistic"],
    output=["$P_{value} \\equiv \\frac{1}{B+1} \\sum_{i=0}^{B} \\indicator{ T_0 \\ge T_i}$"],
    statement_short="Parametric-style bootstrap: resample from the $w$-weighted product of estimated marginals, re-estimate, recompute $T$, compare to $T_0$.",
    tags=["bootstrap", "hypothesis_testing"])

# ---------------------------------------------------------------- 4.2.1
prose("DP17", "definition", "Quasi-marginal variables $\\tilde X, \\tilde Y$",
      "Let $\\tilde{X}\\sim \\tilde{F}_X,", "in \\eqref{eq:quasi_independence}.",
      definiendum=["$\\tilde{X}$", "$\\tilde{Y}$", "$\\tilde{F}_X$", "$\\tilde{F}_Y$"], confidence=0.85)
prose("ClP5", "claim", "Observed $X$-density under quasi-independence",
      "Under quasi-independence, by the law of total probability", "/\\mathbb{E}\\{w(\\tilde{X},\\tilde{Y})\\}$.",
      confidence=0.75, assumptions=["Under quasi-independence"],
      conclusions=["the density of $X$ can be written as ${f}_{X}(x)=\\mathbb{E}\\{w(x,\\tilde{Y})\\}\\tilde{f}(x)/\\mathbb{E}\\{w(\\tilde{X},\\tilde{Y})\\}$"])
prose("DP18", "definition", "Inverse-weighting update for $\\tilde F_X$",
      "Thus, an estimate of $\\tilde{F}_Y$ yields", "\\hat{\\mathbb{E}}\\{w(x_i,\\tilde{Y})\\}^{-1}}. \\end{equation}",
      definiendum="$\\widehat{\\tilde{F}}_X$", confidence=0.8,
      statement_short="Estimate $\\tilde F_X$ by weighting each $x_i$ by the inverse of the estimated $\\mathbb{E} w(x_i,\\tilde Y)$.")
eq("EP10", "F25", "Inverse-weighting update")
prose("ClP6", "claim", "Reduction to the product-limit estimator under truncation",
      "For the important case ${w}(x,y) = \\indicator{x<y}$, the algorithm reduces", "\\citep{moreira2010dtda}.",
      rigor="semi_formal", confidence=0.7,
      assumptions=["${w}(x,y) = \\indicator{x<y}$"],
      conclusions=["the algorithm reduces to the standard product-limit (PL) estimator for left and right truncated data"],
      tags=["truncation", "product_limit"])
add("AP4", "algorithm", "Estimation of Marginal Distributions Under Quasi-independence", None, fact="F26", main=True,
    input=["$\\mathcal{D}$ - sample", "${w}(x,y)$ - bias function", "$d(F_1,F_2)$ - distance function"],
    output=["$\\tilde F^{new}_X$ and $\\tilde F^{new}_Y$"],
    statement_short="Alternate inverse-weighting updates of $\\tilde F_X$ and $\\tilde F_Y$, each using the other's current estimate, until the estimates stabilise.",
    tags=["marginal_estimation", "iterative"])
prose("RP4", "remark", "Null-consistent marginals give low power",
      "While Algorithm \\ref{alg:est_marg} provides", "The next example demonstrates this claim.", confidence=0.7,
      statement_short="Marginal estimates consistent only under the null (e.g. PL under truncation) make the bootstrap test weak; they should be consistent under the alternative too.")
prose("ExP1", "example", "Difficulties in Detecting Quasi-Independence",
      "\\noindent \\textbf{Example: Difficulties", "may result in a test with low power.", confidence=0.85,
      statement_short="Uniform strip $|x-y|<0.3$ under truncation $x<y$: PL marginal estimates are badly biased, and independent data drawn from them mimic the dependent sample.",
      tags=["truncation", "product_limit"])
prose("RP5", "remark", "Non-identifiability under the alternative",
      "A possible solution is to find estimators for the marginal CDFs", "(or both).", confidence=0.65)

# ---------------------------------------------------------------- 4.2.2
prose("TP2", "theorem", "NPMLE under weighted sampling",
      "The problem of estimating non-parametrically a general multivariate distribution", "\\end{equation}",
      origin="external", origin_citation="Vardi 1985", confidence=0.75,
      assumptions=["for $w>0$"],
      conclusions=["the non-parametric maximum likelihood estimator (NPMLE) is given by"],
      statement_short="For positive $w$, the NPMLE of $F_{XY}$ from weighted data is the empirical CDF reweighted by $1/w$.",
      tags=["npmle", "weighted_distribution"])
eq("EP11", "F28", "NPMLE $\\hat F^n_{XY}$")
prose("DP19", "definition", "Inverse-weighted marginal estimator",
      "Estimators for $F_{X}$ and $F_{Y}$ can be then obtained by marginalization", "\\end{equation}",
      definiendum="$\\hat{F}_{X}^n$", confidence=0.8)
eq("EP12", "F29", "Marginal estimator $\\hat F^n_X$")
prose("ClP7", "claim", "Consistency of inverse-weighted marginals for $w>0$",
      "By the law of large numbers,", "By similar arguments, $\\hat{F}_{Y}^n(s) \\to F_{Y}(s)$ a.s.",
      confidence=0.7, main=True,
      conclusions=["$\\hat{F}_{X}^n(t) \\to F_{X}(t)$ a.s.", "$\\hat{F}_{Y}^n(s) \\to F_{Y}(s)$ a.s."],
      statement_short="Law of large numbers plus continuous mapping: the inverse-weighted marginal estimators are strongly consistent when $w>0$.",
      tags=["consistency", "marginal_estimation"])

# ---------------------------------------------------------------- 4.2.3
add("PrP1", "proposition", "Consistent marginals under exchangeability and left truncation", None, fact="F30", main=True,
    assumptions=["Let $F_{XY}(x,y)$ be an exchangeable joint distribution having a density $f_{XY}(x,y) \\equiv f_{XY}(y,x)$",
                 "let $\\mathcal{D} \\sim [F_{XY}^{(w)}]^n$ be a sample with the truncation weight function ${w}(x,y) = \\indicator{x<y}$",
                 "Let $\\hat{F}^{(w),n}_X, \\hat{F}^{(w),n}_Y$ be the empirical CDFs of $F_{X}^{(w)}, F_{Y}^{(w)}$, respectively."],
    conclusions=["Then $\\hat{F}_{X}^n, \\hat{F}_{Y}^n \\to F_{X}=F_{Y}$ a.s."],
    statement_short="Under exchangeability and truncation $x<y$, the pooled empirical CDF of all $X_i$ and $Y_i$ is strongly consistent for the common marginal.",
    tags=["consistency", "truncation", "exchangeability"])
eq("EP13", "F31", "Pooled estimator")

# ---------------------------------------------------------------- 5.1
prose("DP20", "definition", "Data quadrants $Q_i^{jk}$",
      "Specifically, each data point $(x_i,y_i) \\in \\mathcal{D}$ defines a partition", "\\end{equation}",
      definiendum="$Q_{i}^{jk}$", confidence=0.85)
eq("EP14", "F32", "Quadrants $Q_i^{jk}$")
prose("DP21", "definition", "Observed and expected quadrant counts",
      "For a quadrant $Q_i^{jk}$, we denote the observed number", "e_{i}^{jk} \\equiv e_{Q_i^{jk}}$.",
      definiendum=["$o_{i}^{jk}$", "$e_{i}^{jk}$"], confidence=0.85)
prose("DP22", "definition", "Adjusted Hoeffding statistic",
      "We then compute, for each quadrant", "{e_{i}^{jk}}. \\end{equation}",
      definiendum="$T$", confidence=0.85,
      statement_short="Sum over sample points and their four quadrants of Pearson chi-square terms $(o-e)^2/e$.",
      tags=["hoeffding_statistic", "chi_squared"])
eq("EP15", "F33", "Adjusted Hoeffding statistic $T$")
prose("RP6", "remark", "Wrong expectations keep validity but cost power",
      "Estimating the expected values $e_{i}^{jk}$ requires", "Section \\ref{sec:fast_bootstrap}.", confidence=0.75,
      statement_short="Null expectations are hard under biased sampling; mis-estimated ones leave the WP test valid (Corollary 1) but can severely reduce power.")

# ---------------------------------------------------------------- 5.1.1
prose("DP23", "definition", "Pairing probabilities $P_{ij}$",
      "Let $P_{ij} \\equiv P_{\\mathcal{W}}(\\pi(i)=j)", "so $P_{ij} = \\mathbb{E}(\\xi^\\pi_{ij})$.",
      definiendum=["$P_{ij}$", "$\\xi^\\pi_{ij}$"], confidence=0.85)
prose("DP24", "definition", "Permuted counts $o_{\\mathcal{A}}(\\pi)$ and expected count $e_{\\mathcal{A}}$",
      "Let $\\mathcal{A} \\subset \\mathbb{R}^2$ be an arbitrary set.",
      "under the permutations distribution $P_{\\mathcal{W}}$.",
      definiendum=["$o_{\\mathcal{A}}(\\pi)$", "$e_{\\mathcal{A}}$"], confidence=0.85)
add("ClP8", "claim", "Expected counts from pairing probabilities", None, fact="F34",
    assumptions=["For any $\\mathcal{A} \\subset \\mathbb{R}^2$"],
    conclusions=["the expected number of points $e_{\\mathcal{A}}$ under the permutations distribution $P_{\\mathcal{W}}$ is given by:"],
    statement_short="$e_{\\mathcal{A}}=\\sum_{i,j}\\mathbb{1}\\{(x_i,y_j)\\in\\mathcal{A}\\}P_{ij}$.")
eq("EP16", "F35", "$e_{\\mathcal{A}}$ via $P_{ij}$")
add("PP4", "proof", "Proof of Claim 2", None, fact="F36", proves="ClP8", proof_strategy=["direct"],
    statement_short="Linearity of expectation over the indicators $\\pi(i)=j$.")
eq("EP17", "F37", "Expansion of $e_{\\mathcal{A}}$")
prose("DP25", "definition", "MCMC estimator $\\hat P_{ij}$",
      "The probabilities $P_{ij}$ can be easily estimated", "\\end{equation}",
      definiendum="$\\hat{P}_{ij}$", confidence=0.85)
eq("EP18", "F38", "$\\hat P_{ij}$")
prose("DP26", "definition", "Importance-sampling estimator $\\hat P^{(IS)}_{ij}$",
      "When we sample permutations using an importance distribution", "\\end{equation}",
      definiendum="$\\hat{P}_{ij}^{(IS)}$", confidence=0.85)
eq("EP19", "F39", "$\\hat P^{(IS)}_{ij}$")
prose("DP27", "definition", "Estimated expected count $\\hat e_{\\mathcal{A}}$",
      "Plugging Equation \\eqref{eq:P_ij_estimator}", "which can be used in the Chi-squared statistic.",
      definiendum="${\\hat{e}}_{\\mathcal{A}}$", confidence=0.85)
eq("EP20", "F40", "$\\hat e_{\\mathcal{A}}$")
prose("DP28", "definition", "Bootstrap expected quadrant count",
      "Consider, for example, the bottom-left quadrant", "\\end{equation}",
      definiendum="$\\widehat{e_{i}^{00}}$", confidence=0.8)
eq("EP21", "F41", "$\\widehat{e_i^{00}}$")

# ---------------------------------------------------------------- 5.2
prose("DP29", "definition", "Inverse weighted observed and expected counts",
      "For a set  $\\mathcal{A} \\in \\mathbb{R}^2$, define the {\\it inverse weighted}".replace("  ", " "), "\\end{align}",
      definiendum=["$o_{\\mathcal{A}}^{({w})}$", "$e_{\\mathcal{A}}^{({w})}$"], confidence=0.9)
eq("EP22", "F42", "Inverse weighted counts")
prose("DP30", "definition", "Inverse weighted expected quadrant counts",
      "For the quadrants $Q_i^{jk}$, we can compute estimates", "\\end{equation}",
      definiendum="${e_i^{jk}}^{({w})}$", confidence=0.85)
eq("EP23", "F43", "${e_i^{00}}^{(w)}$")
prose("DP31", "definition", "Inverse weighting statistic $T^{(w)}$",
      "Similarly to Equation \\eqref{eq:modifed_hoeffding}, the weighted statistic", "\\end{equation}",
      definiendum="$T^{(w)}$", confidence=0.85, tags=["inverse_weighting", "chi_squared"])
eq("EP24", "F44", "$T^{(w)}$")

# ---------------------------------------------------------------- 5.3
prose("DP32", "definition", "Left-truncation right-censoring model",
      "Consider the standard left-truncation right-censoring model", "independent of the censoring variables $C_i$.",
      definiendum="left-truncation right-censoring model", confidence=0.8, tags=["censoring", "truncation"])
prose("DP33", "definition", "Censoring indicators $\\Delta_i$",
      "We observe triplets", "for censored and uncensored observations, respectively.",
      definiendum="$\\Delta_i$", confidence=0.85)
prose("AP5", "algorithm", "Weighted test for left-truncated right-censored data",
      "We suggest testing independence based on the uncensored observations", "i=1,\\ldots,n \\}$.",
      confidence=0.7, main=True,
      input=["triplets $(X_i,\\min(Y_i,X_i+C_i),\\Delta_i$)"],
      statement_short="Test quasi-independence on the uncensored pairs with $w(x,y)=\\mathbb{1}\\{x<y\\}S(y-x)$, where $S$ is the Kaplan-Meier estimate of the censoring survival.",
      tags=["censoring", "truncation", "kaplan_meier"])
prose("ClP9", "claim", "Density of uncensored LTRC observations",
      "Specifically, the conditional density of an uncensored observation is simply", "is the survival function of $C$.",
      rigor="semi_formal", confidence=0.75,
      conclusions=["the conditional density of an uncensored observation is simply"])
eq("EP25", "F45", "Uncensored density")
prose("ClP10", "claim", "Censoring as a weight function",
      "Thus, the density of uncensored observations has exactly the form", "a continuous and a truncated part.",
      confidence=0.75,
      conclusions=["the density of uncensored observations has exactly the form of Equation \\eqref{eq:weighted_density}, with $w(x,y)=\\setindicator{\\{x<y\\}} S(y-x)$"])

# ---------------------------------------------------------------- 6 Simulations
prose("ClP11", "claim", "All tests hold level under the Gaussian null",
      "As expected, in the Gaussian settings, under the null distribution", "error rate.",
      rigor="numerical", confidence=0.65, conclusions=["all tests achieve the correct $\\alpha=0.05$ error rate"])
prose("ClP12", "claim", "Misspecified bootstrap fails to hold level",
      "The devastating impact of model miss-specification", "under the null hypothesis ($\\rho = 0$).",
      rigor="numerical", confidence=0.65)
prose("ClP13", "claim", "Biased sampling can mask dependence",
      "The biased sampling function here masks the dependence", "independent Gaussian random variables.",
      rigor="semi_formal", confidence=0.65,
      assumptions=["a bivariate Gaussian distribution $Norm(\\rho)$ for $X$ and $Y$", "${w}(x,y) \\propto Norm(-\\rho)$"],
      conclusions=["the observed pairs, $(X_i,Y_i)$, are independent Gaussian random variables"])

# ---------------------------------------------------------------- 8 Discussion
prose("CnjP1", "conjecture", "Consistency of the WP and bootstrap tests",
      "In particular we conjecture that", "are consistent.", confidence=0.9,
      assumptions=["under the assumption of quasi-dependence"],
      conclusions=["both the WP and bootstrap test are consistent"], tags=["consistency"])

# ---------------------------------------------------------------- Supplement
add("PP5", "proof", "Proof of Proposition 1", None, fact="F49", proves="PrP1", proof_strategy=["direct"],
    statement_short="With $P(X<Y)=1/2$, write both weighted marginals as integrals of $f_{XY}$; by exchangeability their average is $f_Y$; conclude by Glivenko-Cantelli.")
prose("ClP14", "claim", "Naive or fixed expectations lose power",
      "While these two approaches appear simpler and are faster,", "achieves power of $0.406$.",
      rigor="numerical", confidence=0.65)
prose("AP6", "algorithm", "Uniform importance sampling",
      "In 'uniform' importance sampling, we simply sample", "P_{IS}(\\pi)=\\frac{1}{n!}$.", confidence=0.7,
      statement_short="Proposal is the uniform law on $S_n$.", tags=["importance_sampling"])
prose("AP7", "algorithm", "Uniform grid importance sampling",
      "The 'uniform grid' method interpolates", "In our simulations we used $G=10$ with equidistant $\\alpha_i$ values.",
      confidence=0.7,
      statement_short="Tempered SIS: run the sequential sampler with weights $\\mathcal{W}^{\\alpha_k}$ over a grid of exponents from 0 (uniform) to 1 (monotonic).",
      tags=["importance_sampling"])
prose("AP8", "algorithm", "Kou-McCullagh importance sampling",
      "Finally, the Kou-McCullagh algorithm skips", "(see \\cite{kou2009approximating} for more details).",
      origin="external", origin_citation="Kou & McCullagh 2009", confidence=0.7,
      statement_short="SIS without row ordering, sampling column $j$ with probability proportional to $\\mathcal{W}(i,j)/(C_j-\\mathcal{W}(i,j))$.",
      tags=["importance_sampling", "permanent"])
prose("ClP15", "claim", "MCMC is calibrated, importance sampling is conservative at large $n$",
      "Empirically, the MCMC approach is robust", "are all overly conservative.", rigor="numerical", confidence=0.7)
add("AP9", "algorithm", "SIS Permutation Test of Quasi-Independence", None, fact="F50",
    input=["$\\mathcal{D}$ - sample", "${w}(x,y)$ - bias function."],
    output=["$P_{value}$ computed from the $P_{IS}(\\pi_b),P_{\\mathcal{W}}(\\pi_b)$'s according to Equation \\eqref{eq:IS_pval}"],
    statement_short="Monotonic sequential importance sampling: rows in decreasing variance of log-weights, each assigned a free column with probability proportional to $\\mathcal{W}$; P-value by IS weights.",
    tags=["importance_sampling", "permutation_test"])
prose("DP34", "definition", "$k$ variables made dependent by selection",
      "We consider the more general scenario of $k$ independent random variables", "due to selection bias.",
      definiendum=["${X}_1,\\ldots,{X}_k$", "${F}_1,\\ldots,{F}_k$"], confidence=0.8)
prose("DP35", "definition", "Multivariate biased sampling model",
      "Specifically, we assume that observations are vectors", "F_1\\times\\cdots\\times F_k$.",
      definiendum="$w$", confidence=0.85)
eq("EP26", "F52", "Multivariate weighted density")
prose("AssumP1", "assumption", "Identifiability: every subset of the support is observable",
      "For identifiability, we assume that for any measurable subset", "observations from any subset of the support can be observed.",
      confidence=0.9)
prose("DP36", "definition", "Naive inverse-weighted estimator $\\hat F^n_j$",
      "Specifically, generalizing Equation \\eqref{eq:non_parametric_MLE}", "is its $j$'th coordinate.",
      definiendum=["$\\hat{F}^n_j$", "$X_i$", "$X_{ij}$"], confidence=0.85)
eq("EP27", "F53", "Naive estimator")
prose("RP7", "remark", "Naive estimator ignores independence",
      "Estimator \\eqref{naive} does not exploit independence", "(i.e., truncation).", confidence=0.75)
prose("DP37", "definition", "Conditional expectation operator $\\tilde E$",
      "Let ${\\tilde{E}}$ denote the conditional expectation operator", "\\mid X_j=x\\}$.",
      definiendum="${\\tilde{E}}$", confidence=0.85)
prose("ClP16", "claim", "Likelihood factorization",
      "For any $1\\le j\\le k$, the likelihood of the data", "\\end{equation}", rigor="semi_formal", confidence=0.75,
      assumptions=["For any $1\\le j\\le k$"],
      conclusions=["the likelihood of the data $(x_{i1},\\ldots,x_{ik})$ ($i=1,\\ldots,n$) can be factorized as follows"],
      statement_short="The likelihood splits into a factor free of $F_j$ and a $\\tilde E$-weighted likelihood of $F_j$.")
eq("EP28", "F54", "Likelihood factorization")
prose("RP8", "remark", "Derivation of the iterative marginal update",
      "Due to independence, the first term in Equation \\eqref{splitlike}", "generalizing Algorithm \\ref{alg:est_marg} in the main text.",
      confidence=0.7,
      statement_short="With the other marginals fixed, the likelihood of $F_j$ is the second factor, whose maximiser weights $x_{ij}$ by $\\tilde E(w;j,x_{ij})^{-1}$.")
add("AP10", "algorithm", "Estimation of Marginals Under Quasi-independence ($k$ variables)", None, fact="F55",
    input=["$(x_{i1},\\ldots,x_{ik})$ ($i=1,\\ldots,n$) - sample", "$w$ - bias function", "$d(F_1,F_2)$ - distance function."],
    output=["$F^{new}_1,\\ldots,F^{new}_k$"],
    statement_short="Coordinate-wise iteration: recompute each $\\tilde E(w;j,x_{ij})$ under the current product and reset $F_j$ to the inverse-weighted empirical CDF.",
    tags=["marginal_estimation", "iterative"])
prose("RP9", "remark", "Complexity of the iterative algorithm",
      "Algorithm \\ref{alg:est_marg_app} provides a non-parametric estimator", "is $O(n^{k})$.", confidence=0.7)
prose("ClP17", "claim", "Linear weight gives $O(n)$ update",
      "For the important case of a linear weight function", "reduces to $O(n)$.", confidence=0.75,
      assumptions=["Let $w({\\bf x})={\\bf a}^{t}{\\bf x}+b$, where the vector $\\bf a$ and the constant $b$ are known"],
      conclusions=["the computational complexity of each step $5$ reduces to $O(n)$"])
eq("EP29", "F57", "$\\tilde E$ for linear weight")
add("PrP2", "proposition", "Monotone likelihood of the iterative algorithm", None, fact="F58", rigor="semi_formal",
    conclusions=["The likelihood increases in each step of the algorithm."])
add("PrP3", "proposition", "Convergence of the iterative algorithm", None, fact="F59", rigor="semi_formal",
    conclusions=["The algorithm converges in the interior of the parameter space."])
add("PrP4", "proposition", "NPMLE is a fixed point", None, fact="F60", rigor="semi_formal",
    conclusions=["The NPMLE is a fixed point of the algorithm."])

# ---------------------------------------------------------------- steps
def pstep(nid, parent, order, sub, a, b, short, conf=0.75, after=None):
    s, p = P(a, b, after)
    par = next(n for n in nodes if n["id"] == parent)
    n = {"id": nid, "type": "proof_step", "parent_id": parent, "step_order": order,
         "name": short.split(";")[0][:60], "statement": s, "statement_short": short,
         "subclass": sub, "section": par["section"], "origin": par["origin"], "confidence": conf}
    nodes.append(n); POS[nid] = p

AFTER_PP5 = "The proof of Proposition"
pstep("PSP1", "PP5", 1, "setup", "Since $X$ and $Y$ are continuous exchangeable random variables",
      "f_{XY}^{(w)}(x,y)=2\\indicator{x < y} f_{XY}(x,y). $$", "Exchangeability gives $P(X<Y)=1/2$, so $f^{(w)}=2\\mathbb{1}\\{x<y\\}f$")
pstep("PSP2", "PP5", 2, "algebraic_manipulation", "Calculating the weighted marginal, we have",
      "f_{XY}(x,t)dx . $$", "Integrate to get both weighted marginals, using exchangeability", after=AFTER_PP5)
pstep("PSP3", "PP5", 3, "algebraic_manipulation", "Thus (due to the continuity assumption),",
      "= f_{Y}(t). $$", "Average of the weighted marginals equals $f_Y$")
pstep("PSP4", "PP5", 4, "conclude", "The result follows by applying the Glivenko",
      "\\hat{F}^{(w),n}_Y$ .", "Conclude by Glivenko-Cantelli")

aseq = [1]
def asteps(fid, alg_id, subs, shorts=None):
    alg = next(n for n in nodes if n["id"] == alg_id)
    st = pseudocode_steps(facts, fid, alg, first_seq=aseq[0])
    assert len(st) == len(subs), (fid, len(st))
    for k, s in enumerate(st):
        s["statement"] = clean(s["statement"])
        if s["subclass"] is None:
            s["subclass"] = subs[k]
        if shorts and shorts.get(k + 1):
            s["statement_short"] = shorts[k + 1]
        POS[s["id"]] = POS[alg_id]
    aseq[0] += len(st)
    nodes.extend(st)
    return [s["id"] for s in st]

A1 = asteps("F18", "AP1", ["call", "compute", "loop", "compute", "return"],
            {1: "Sample $B$ permutations from $P_{\\mathcal{W}}$ (e.g. by MCMC)"})
A2 = asteps("F20", "AP2", ["compute", "initialize", "loop", "select", "branch", "update", "branch", "update", "return"],
            {4: "Propose a random transposition and draw $u$", 5: "Metropolis-Hastings acceptance test", 9: "Return thinned chain states"})
A3 = asteps("F23", "AP3", ["call", "compute", "loop", "compute", "call", "compute", "return"],
            {4: "Draw a bootstrap sample from the $w$-weighted product of estimated marginals", 5: "Re-estimate marginals on the bootstrap sample"})
A4 = asteps("F26", "AP4", ["initialize", "loop", "update", "compute", "compute", "return"],
            {4: "Update $\\tilde F_X$ by inverse weighting with $\\mathbb{E} w(x,Y)$", 5: "Update $\\tilde F_Y$ symmetrically"})
A9 = asteps("F50", "AP9", ["compute", "initialize", "loop", "initialize", "compute", "compute", "loop", "select", "update", "update", "return"],
            {5: "Row variances of log-weights", 6: "Order rows by decreasing variance", 8: "Sample a free column with probability proportional to $\\mathcal{W}$",
             9: "Accumulate proposal probability", 10: "Accumulate unnormalised target probability"})
A10 = asteps("F55", "AP10", ["initialize", "loop", "update", "loop", "compute", "update", "return"],
             {5: "Conditional expectations $\\tilde E(w;j,x_{ij})$ under the current product", 6: "Inverse-weighted update of $F_j$"})

def ustep(nid, parent, order, sub, a, b, short, after=None):
    s, p = P(a, b, after)
    par = next(n for n in nodes if n["id"] == parent)
    nodes.append({"id": nid, "type": "algorithm_step", "parent_id": parent, "step_order": order,
                  "name": short[:60], "statement": s, "statement_short": short, "subclass": sub,
                  "section": par["section"], "origin": par["origin"], "confidence": 0.7})
    POS[nid] = p
n0 = aseq[0]
U = lambda k: f"ASP{n0 + k}"
ustep(U(0), "AP5", 1, "call", "We suggest testing independence based on the uncensored observations",
      "used only for estimation of the weight function.", "Test on uncensored observations only")
ustep(U(1), "AP5", 2, "compute", "The survival function $S$ can be estimated by the standard Kaplan",
      "i=1,\\ldots,n \\}$.", "Estimate $S$ by Kaplan-Meier on the residual censoring data")
ustep(U(2), "AP7", 1, "initialize", "taking a grid of values $0 = \\alpha_1", "\\alpha_G = 1$", "Choose a grid of exponents")
ustep(U(3), "AP7", 2, "update", "for each $\\alpha_k$ modifying step $9$ of the algorithm",
      "\\mathcal{W}(\\sigma(i),j)^{\\alpha_k}$", "Run the SIS sampler with tempered weights")
ustep(U(4), "AP8", 1, "other", "skips the ordering steps 5,6", "skips the ordering steps 5,6", "Skip row ordering")
ustep(U(5), "AP8", 2, "compute", "computes the column-sums $C_i", "over the remaining rows at each step", "Compute remaining column sums")
ustep(U(6), "AP8", 3, "select", "Step $9$ is replaced by sampling", "{C_j-\\mathcal{W}(i,j)}$",
      "Sample column with Kou-McCullagh weights")

# ---------------------------------------------------------------- edges
T = lambda s, t, c=0.75, **k: E(s, t, conf=c, basis="term", **k)
I = lambda s, t, c=0.7, **k: E(s, t, conf=c, basis="inferred", **k)
N = lambda s, t, c=0.9, **k: E(s, t, conf=c, basis="named", **k)
# definitions -> users
for t in ["DP2", "DP4", "PrP1", "ClP7", "PP5", "DP19"]: T("DP1", t)
for t in ["DP3", "DP4", "DP5", "DP6", "ProbP1", "DP10", "LP1", "PP1", "PrP1", "TP2", "PP5"]: T("DP2", t)
for t in ["PrP1", "PP5"]: T("DP3", t)
for t in ["CP1", "AP3", "DP28", "DP29"]: T("DP4", t)
for t in ["ClP2", "ExP1", "PP5"]: T("DP5", t, 0.7)
for t in ["ProbP1", "RP1", "RP2", "ClP1", "ClP5", "AP4", "CnjP1"]: T("DP6", t, 0.8)
for t in ["ClP1", "AP1", "AP3"]: T("ProbP1", t, 0.75)
E("ProbP1", "AP1", "resolves", 0.85, "inferred"); E("ProbP1", "AP3", "resolves", 0.85, "inferred")
E("ProbP1", "AP9", "resolves", 0.75, "inferred"); E("ProbP1", "AP5", "resolves", 0.7, "inferred")
for t in ["DP8", "ClP1", "PP1"]: T("DP7", t)
for t in ["ClP1", "PP1"]: T("DP8", t)
for t in ["ClP1", "LP1", "DP13", "AP1", "DP24"]: T("DP9", t)
for t in ["DP11", "AP2", "AP9", "PP1", "AP8", "DP15"]: T("DP10", t)
for t in ["ClP1", "ClP2", "AP1", "DP16", "RP3", "DP23", "AP2", "AP9", "LP1"]: T("DP11", t)
for t in ["DP13", "AP1", "AP3", "DP16"]: T("DP12", t)
for t in ["AP1", "ClP3"]: T("DP13", t)
for t in ["DP15", "AP2"]: T("DP14", t)
T("DP15", "AP2", 0.85)
for t in ["ClP4", "DP26", "AP6", "AP9"]: T("DP16", t)
N("DP16", "RP3", 0.85)
for t in ["ClP5", "DP18", "AP4", "ExP1"]: T("DP17", t)
I("ClP5", "DP18", 0.75)
N("RP4", "ExP1", 0.9, ); edges[-1]["type"] = "illustrates"
E("ClP6", "ExP1", "illustrates", 0.75, "inferred")
T("ClP6", "RP4", 0.75)
T("DP19", "ClP7", 0.85)
for t in ["DP21", "DP28", "DP30"]: T("DP20", t, 0.8)
T("DP21", "DP22", 0.85)
T("DP21", "RP6", 0.8)
for t in ["ClP8", "DP25", "DP26", "PP4"]: T("DP23", t)
for t in ["ClP8", "DP27", "PP4"]: T("DP24", t)
I("DP27", "DP22", 0.6)
for t in ["DP30", "DP31"]: T("DP29", t, 0.8)
T("DP30", "DP31", 0.8)
for t in ["DP33", "ClP9", "AP5"]: T("DP32", t, 0.8)
T("DP33", "AP5", 0.8)
I("ClP9", "ClP10", 0.8)
# results / algorithms
I("LP1", "PP3", 0.8)
N("AP1", "ClP3", 0.85)
I("AP2", "AP1", 0.75)
N("TP1", "ClP4", 0.9)
I("AP4", "AP3", 0.65)
N("AP4", "ClP6", 0.9)
I("AP1", "AP5", 0.7)
for t in ["AP1", "AP3"]: I(t, "CnjP1", 0.75)
I("AP1", "ClP11", 0.6); I("AP3", "ClP11", 0.6); I("ClP11", "ClP3", 0.55, mention=True)
I("AP3", "ClP12", 0.7); T("PrP1", "ClP12", 0.65)
T("DP2", "ClP13", 0.7)
N("AP2", "ClP15", 0.8); N("AP9", "ClP15", 0.8)
I("ClP14", "RP6", 0.7)
N("AP9", "AP7", 0.9); N("AP6", "AP7", 0.85)
N("AP9", "AP8", 0.9)
for t in ["DP35", "AssumP1"]: T("DP34", t, 0.8)
for t in ["AssumP1", "DP36", "DP37", "ClP16", "AP10"]: T("DP35", t, 0.8)
for t in ["ClP16", "RP8", "AP10", "RP9", "ClP17"]: T("DP37", t, 0.85)
I("AssumP1", "AP10", 0.6)
I("RP8", "AP10", 0.75)
E("AP4", "RP8", "uses", 0.95, "named", mention=True)
E("AP4", "AP10", "generalizes", 0.9, "named")
N("AP10", "ClP17", 0.85)
for t in ["PrP2", "PrP3", "PrP4"]: N("AP10", t, 0.9)
# \ref to algorithm labels (not resolved by finalize: the \label sits outside the algorithmic body)
N("AP4", "RP4", 0.9); N("AP10", "RP9", 0.9); N("AP2", "DP25", 0.9)
T("DP6", "RP5", 0.75)
T("DP1", "ClP9", 0.8); T("DP1", "AP5", 0.8)
T("DP9", "PP1", 0.8)
for t in ["PP1", "DP24", "ClP8", "PP4"]: T("DP11", t, 0.8)
T("DP34", "DP37", 0.8)
# proofs
T("DP2", "PP1"); T("DP6", "PP1", 0.8)
T("DP23", "PP4", 0.8)
E("PP2", "LP1", "proves", 1.0, "syntax")
E("PP3", "CP1", "proves", 0.75, "inferred")
E("PP4", "ClP8", "proves", 1.0, "syntax")
E("PP5", "PrP1", "proves", 0.95, "named")
# steps inside PP5
I("PSP1", "PSP2", 0.8); I("PSP2", "PSP3", 0.8); I("PSP3", "PSP4", 0.8)
# algorithm-internal ordering not encoded as edges

nfm = sum(1 for n in nodes if "rigor" in n)
NOTES = [
 {"category": "boundary_uncertain", "nodes": ["ClP7", "ClP3", "ClP4"],
  "note": "These results are stated and justified in the same sentence (LLN + continuous mapping; 'Corollary 1 assures that'; 'This result applies directly'), so no separate proof node could be cut; each node spans the arguing sentence(s)."},
 {"category": "type_uncertain", "nodes": ["ClP7"],
  "note": "claim or remark: the paragraph argues and concludes in one go, but it is one of the two consistency results the introduction announces, so it is kept as a (main) claim."},
 {"category": "type_uncertain", "nodes": ["AP5"],
  "note": "algorithm or remark: the LTRC adaptation is a procedure described in prose (test uncensored pairs with w estimated by Kaplan-Meier); kept as an unmarked algorithm containing the two density claims."},
 {"category": "rule_conflict", "nodes": ["PP1"],
  "note": "The supplement repeats the proof of Claim 1 verbatim (including a second \\label{eq:generalperm}); it is recorded in also_stated_at of PP1 and EP6, not as a node."},
 {"category": "source_problem", "nodes": ["AP4", "AP10", "AP2", "RP4", "RP9"],
  "note": "Algorithm \\label commands sit after the algorithmic body, so \\ref{alg:...} edges were not resolved by the finishing step; they were added by hand with basis named. \\ref{fig:example} is unresolved (the figure's label is 'example')."},
 {"category": "unexpected_construct", "nodes": ["ClP11", "ClP12", "ClP14", "ClP15"],
  "note": "Power tables (Tables 1-2) and the real-data P-values are not nodes; only a few prose conclusions drawn from them are kept as numerical claims."},
 {"category": "not_extracted", "nodes": [],
  "note": "Section 7 (real datasets), the per-figure descriptions in Supp. 8.2 and the itemised implementation details of Supp. 8.6 (MCMC thinning M=2n, low-count cells, tie-breaking perturbation) are discursive or empirical and were not extracted."},
]
COMMENT = "The paper's numbered Lemma counter is per section (Lemma 3.1) while other environments are global; the supplement is an unnumbered section so its subsections print as 8.1-8.6."

graph = {"metadata": {
    "title": "Testing Independence under Biased Sampling",
    "arxiv_id": "1912.05769",
    "authors": ["Yaniv Tenzer", "Micha Mandel", "Or Zuk"], "year": 2019,
    "annotator": "agent-extraction", "model": "claude-opus-5-5", "effort": "default",
    "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3", "extraction_date": "2026-11-05",
    "rigor_nonformal_count": nfm,
    "paper_style": ["modeling", "computational"],
    "extraction_notes": [],
    "extraction_comment": ""},
    "nodes": nodes, "edges": edges}
graph["metadata"]["extraction_notes"] = NOTES
graph["metadata"]["extraction_comment"] = COMMENT

report = finalize(graph, read_tex(TEX))
json.dump(report, open(SCR + "/report.json", "w"), indent=1, default=str)
for w in report["warnings"]:
    print("WARN", w)
for e in report["errors"]:
    print("ERR", e)
assert not report["errors"], len(report["errors"])
json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
from collections import Counter
print("nodes", Counter(n["type"] for n in nodes))
print("edges", Counter(e["type"] for e in graph["edges"]))
print({k: (len(v) if isinstance(v, list) else v) for k, v in report.items() if k not in ("warnings", "errors")})
