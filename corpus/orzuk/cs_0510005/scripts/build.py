"""Build the SARANGA v7 graph for cs/0510005 (Zuk, Domany, Kanter, Aizenman 2005).

Node choices, spans and edges were decided by reading the paper; this script only
slices the chosen spans out of the prepared source, assembles the JSON and runs
the finishing step.
"""
import json, re, subprocess, sys
sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
from extraction_finalize import finalize
from latex_facts import read_tex

HERE = "/mnt/c/Code/Github/Saranga/corpus/orzuk/cs_0510005"
TEX = HERE + "/arxiv_src/HMP_Series_ZDKA_2005_10_03.tex"
OUT = HERE + "/cs_0510005.json"
SCR = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_orzuk/cs_0510005"
FACTS = SCR + "/facts.json"
subprocess.run(["python3", "/mnt/c/Code/Github/Saranga/src/latex_facts.py", TEX, "--out", FACTS],
               check=True, capture_output=True)
facts = json.load(open(FACTS))
src = facts["source"]
F = {f["id"]: f for f in facts["facts"]}
SEC = {s["id"]: (s["number"] + " " + s["title"]) if s["number"] else s["title"] for s in facts["sections"]}


def clean(t):
    return re.sub(r"\s+", " ", t).strip()


def _rx(t):
    return r"\s*".join(re.escape(w) for w in t.split())


def cut(start, end, after=None):
    """Verbatim span from `start` through `end` (first occurrence after `after`);
    whitespace in the markers matches any whitespace in the source."""
    p0 = 0
    if after:
        m = re.compile(_rx(after)).search(src)
        assert m, after
        p0 = m.start()
    m = re.compile(_rx(start)).search(src, p0)
    assert m, ("start", start)
    m2 = re.compile(_rx(end)).search(src, m.start())
    assert m2, ("end", end)
    return clean(src[m.start():m2.end()])


def sec_of(pos):
    best = None
    for s in facts["sections"]:
        if s["inside"] is None and s["start"] <= pos:
            best = s["id"]
    return SEC[best]


def secpos(text):
    k = src.find(text[:40])
    return sec_of(k) if k >= 0 else None


nodes, edges = [], []


def node(id, type, name, statement, origin="paper", conf=0.75, section=None, **kw):
    n = {"id": id, "type": type, "name": name, "statement": statement,
         "section": section or secpos(statement), "origin": origin, "confidence": conf}
    n.update(kw)
    nodes.append(n)
    return n


def env(id, fid, type, name, origin="paper", conf=1.0, **kw):
    f = F[fid]
    return node(id, type, name, clean(f["statement"]), origin, conf, section=SEC[f["section"]], **kw)


def E(s, t, type="uses", conf=0.8, basis="term", **kw):
    e = {"source": s, "target": t, "type": type, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)


STEPS = {}


def steps(parent, specs, sec):
    """specs: list of (id, start, end, subclass, name, short, conf, parent_override)."""
    order = {}
    for sp in specs:
        sid, a, b, sub, name, short = sp[:6]
        conf = sp[6] if len(sp) > 6 and sp[6] is not None else 0.75
        par = sp[7] if len(sp) > 7 and sp[7] else parent
        order[par] = order.get(par, 0) + 1
        stmt = cut(a, b, after=STEPS.get("anchor"))
        node(sid, "proof_step", name, stmt, conf=conf, section=sec, parent_id=par,
             step_order=order[par], subclass=sub, statement_short=short)


EXT_STD = dict(origin="external", origin_citation="standard (uncited)")

# ---------------------------------------------------------------- 1 Introduction
S1 = SEC["S1"]
node("DP1", "definition", "Finite-state stationary Markov process",
     cut("Let $\\{X_N\\}$ be a finite state", "\\Sigma = \\{1,\\ldots,s\\}$."), conf=0.85,
     definiendum=["$\\{X_N\\}$", "$\\Sigma$"], genus="finite state stationary markov process", **EXT_STD)
node("DP2", "definition", "Noisy observation process",
     cut("Let $\\{Y_N\\}$ be its noisy", "(on the same alphabet)."), conf=0.85,
     definiendum="$\\{Y_N\\}$", **EXT_STD)
node("DP3", "definition", "Markov transition matrix and emission matrix",
     cut("Let $M = M_{s \\times s}", "= r_{ij}$."), conf=0.85,
     definiendum=["$M$", "$R$"],
     statement_short="$M=\\{m_{ij}\\}$ is the transition matrix of $X$ and $R=\\{r_{ij}\\}$ the emission matrix from $X_N$ to $Y_N$.",
     **EXT_STD)
node("AssumP1", "assumption", "Strictly positive Markov matrix",
     cut("We assume that the\nMarkov matrix", "$\\pi^t M = \\pi^t$."), conf=0.85,
     statement_short="$M$ is strictly positive; $\\pi$ denotes its stationary distribution, $\\pi^t M=\\pi^t$.")
node("DP4", "definition", "Hidden Markov Process (HMP)",
     cut("The process $Y$ can be viewed", "by the parameters $M$ and $R$."), conf=0.9,
     definiendum="Hidden Markov Process (HMP)", genus="noisy observation of $X$, through a noisy channel",
     origin="external", origin_citation="Ephraim & Merhav 2002; Rabiner 1989")
node("DP5", "definition", "Block notation $[X]_i^j$",
     cut("More formally, for $i \\leq j$", "$(X_i,\\ldots,X_j)$."), conf=0.85,
     definiendum="$[X]_i^j$")
node("DP6", "definition", "Entropy rate",
     cut("Then the entropy rate $\\bar{H}(Y)$", "$0 \\log 0 \\equiv 0$."), conf=0.9,
     definiendum=["entropy rate $\\bar{H}(Y)$", "$H(X)$"],
     statement_short="Entropy rate $\\bar{H}(Y)=\\lim_N H([Y]_1^N)/N$ with Shannon entropy $H(X)=-\\sum P\\log P$ in nats.",
     origin="external", origin_citation="Shannon 1948")
node("TP1", "theorem", "Entropy rate as limit of conditional entropies",
     cut("The entropy rate can also be\ncomputed", "coincide (\\cite{Cover})."), conf=0.85,
     origin="external", origin_citation="Cover & Thomas 1991",
     assumptions=["for a stationary process"],
     conclusions=["$\\bar{H}(Y) = \\lim_{N \\to \\infty} H(Y_N | [Y]_1^{N-1})$",
                  "the two limits exist and coincide"])
node("DP7", "definition", "Conditional entropy",
     cut("The conditional\nentropy $H(Y|X)$", "H(Y | X=x) $."), conf=0.85,
     definiendum="conditional entropy $H(Y|X)$", **EXT_STD)
node("TP2", "theorem", "Chain rule for entropy",
     cut("By the chain rule for\nentropy", "which will be used later."), conf=0.85,
     assumptions=[], conclusions=["$H(Y|X) = H(X,Y) - H(X)$"], **EXT_STD)
node("DP8", "definition", "Symmetric binary HMP",
     cut("The expansion coefficients were given in", "parameters\n$p,\\epsilon$."), conf=0.8,
     definiendum=["symmetric binary case", "$p$", "$\\epsilon$"],
     statement_short="Symmetric binary HMP: $M$ flips with probability $p$, $R$ flips with probability $\\epsilon$.",
     origin="external", origin_citation="Zuk, Kanter & Domany 2005 (DCC)")

# ---------------------------------------------------------------- 2.1 High SNR
node("DP9", "definition", "High-SNR regime",
     cut("In the High-SNR regime the observations", "$\\sum_{j=1}^{s}{t_{ij}} = 0$."), conf=0.85,
     definiendum=["High-SNR regime", "$\\epsilon$", "$T$"],
     statement_short="High-SNR regime: $R=I+\\epsilon T$ with small $\\epsilon>0$ and $T$ a zero-row-sum matrix with negative diagonal.")
env("TP3", "F2", "theorem", "Settling of finite-system entropy coefficients (High-SNR)", main=True,
    statement_short="If $C_N=H_N-H_{N-1}$ and $\\bar H$ are analytic in $\\epsilon$ near 0, the $k$-th Taylor coefficient of $C_N$ equals that of $\\bar H$ once $N\\ge\\lceil (k+3)/2\\rceil$.",
    assumptions=["Let $H_N \\equiv H_N(M,T,\\epsilon) = H([Y]_1^N)$ be the entropy of a finite system of length $N$, and let $C_N = H_N - H_{N-1}$.",
                 "there is some (complex) neighborhood $B_{\\rho}(0) = \\{\\epsilon : |\\epsilon| < \\rho \\} \\subset \\mathbb{C}$ of $\\epsilon=0$, in which the (one-variable) functions $\\{ C_N \\}, \\bar{H}$ are analytic in $\\epsilon$"],
    conclusions=["N \\geq \\lceil \\frac{k+3}{2} \\rceil \\Rightarrow C_N^{(k)} = C^{(k)}"],
    tags=["entropy_rate", "hidden_markov_process", "series_expansion", "analyticity"])
node("RP1", "remark", "Han-Marcus analyticity not applicable at $\\epsilon=0$",
     cut("The recent result (\\cite{Marcus})", "will be discussed elsewhere."), conf=0.8)
node("TP4", "theorem", "$C_N$ upper-bounds the entropy rate",
     cut("$C_N$ is actually an upperbound", "for $\\bar{H}$."), conf=0.8,
     origin="external", origin_citation="Cover & Thomas 1991",
     assumptions=[], conclusions=["$C_N$ is actually an upperbound (\\cite{Cover}) for $\\bar{H}$."])
node("RP2", "remark", "Prior symbolic evidence for Theorem 1",
     cut("The behavior stated in Thm.", "(see \\cite{ZKD1})."), conf=0.8)
node("DP10", "definition", "Site-dependent noise process $Z$",
     cut("First, we distinguish between the noise", "determined by $M$,$T$ and\n$[\\epsilon]_{1}^N$."), conf=0.8,
     definiendum=["$\\{Z_N\\}$", "$R_i$", "$\\epsilon_i$"],
     statement_short="Generalized process $Z$ with site-dependent emission matrices $R_i=I+\\epsilon_i T$.")
node("DP11", "definition", "$F_N$ (entropy increment of $Z$)",
     cut("We define the following functions :", "\\end{equation}", after="We define the following functions"),
     conf=0.9, definiendum="$F_N(M,T,[\\epsilon]_1^{N})$")
node("ClP1", "claim", "$F_N$ at equal noise reduces to $C_N$",
     cut("Setting all the $\\epsilon_i$'s equal", "C_N(\\epsilon)$."), conf=0.75,
     assumptions=["Setting all the $\\epsilon_i$'s equal"],
     conclusions=["$F_N(M,T, (\\epsilon,\\ldots,\\epsilon)) = C_N(\\epsilon)$"])
node("RP3", "remark", "Blocking idea",
     cut("Second, we observe that if a particular", "is 'blocked'."), conf=0.7)
env("LP1", "F6", "lemma", "Blocking lemma",
    statement_short="If $\\epsilon_j=0$ for an interior site, $F_N$ depends only on the sites from $j$ on (the past is blocked).",
    assumptions=["Assume $\\epsilon_j=0$ for some $1 < j < N$."],
    conclusions=["F_N([\\epsilon]_1^N) = F_{N-j+1}([\\epsilon]_{j+1}^N)"])
env("PP1", "F7", "proof", "Proof of Lemma 1", proof_strategy=["direct", "algebraic_manipulation"],
    statement_short="Write $F_N$ as a conditional entropy and use the Markov property: $Z_j=X_j$ blocks conditioning on earlier sites.")
env("EP5", "F8", "equation", "$F_N$ as a sum of conditional entropies")
env("EP6", "F9", "equation", "Blocking of conditional probabilities")
env("EP7", "F10", "equation", "$F_N = F_{N-j+1}$")
STEPS["anchor"] = "$F$ can be written as a sum"
steps("PP1", [
    ("PSP1", "$F$ can be written as a sum", "the probabilities $P(..)$.", "setup",
     "Write $F_N$ as conditional entropy", "Express $F_N$ as a sum of conditional entropies"),
    ("PSP2", "Since $\\epsilon_j=0$, we must have", "but\nnot for $j=N$).", "apply_lemma",
     "Blocking by the Markov property", "$\\epsilon_j=0$ forces $Z_j=X_j$, so conditioning beyond site $j$ is blocked"),
    ("PSP3", "Substituting in eq. (\\ref{F_cond_eq}) gives", "= F_{N-j+1}\n\\end{equation}", "conclude",
     "Substitute and recognise $F_{N-j+1}$", "Substitute the blocked probabilities and marginalize to get $F_{N-j+1}$"),
], SEC["S3"])
node("DP12", "definition", "Multi-index $\\vec{k}$",
     cut("Let $\\vec{k} = [k]_1^N$ be a vector", "\\{\\mathbb{N} \\cup 0\\}$."), conf=0.85,
     definiendum="$\\vec{k}$")
node("DP13", "definition", "Weight of a multi-index",
     cut("Define its 'weight'", "\\sum_{i=1}^N k_i$."), conf=0.9,
     definiendum="$\\omega(\\vec{k})$")
node("DP14", "definition", "Mixed derivative $F_N^{\\vec{k}}$",
     cut("Define also : \\begin{equation} F_N^{\\vec{k}}", "\\end{equation}"), conf=0.9,
     definiendum="$F_N^{\\vec{k}}$",
     statement_short="$F_N^{\\vec{k}}$ is the mixed partial derivative of $F_N$ of orders $k_i$ in $\\epsilon_i$ at $\\vec\\epsilon=0$.")
env("EP8", "F11", "equation", "Definition of $F_N^{\\vec{k}}$")
env("LP2", "F12", "lemma", "Zero-padding lemma",
    statement_short="Prepending zeros to a multi-index whose first entry is at most 1 does not change the derivative $F_N^{\\vec k}$.",
    assumptions=["Let $\\vec{k} = [k]_1^N$ with $k_1 \\leq 1$."],
    conclusions=["F_N^{\\vec{k}} = F_{r+N}^{\\vec{k}^{(r)}} \\quad, \\forall r \\in \\mathbb{N}"])
env("PP2", "F13", "proof", "Proof of Lemma 2", proof_strategy=["case_analysis", "algebraic_manipulation"],
    statement_short="Case $k_1=0$ follows from the blocking lemma; case $k_1=1$ is reduced to it by differentiating in the first coordinate.")
env("EP9", "F14", "equation", "Padding for $k_1=0$")
env("EP10", "F15", "equation", "Padding for $k_1=1$")
STEPS["anchor"] = "Assume first $k_1 = 0$"
steps("PP2", [
    ("PSP4", "Assume first $k_1 = 0$.", "\\label{k_is_zero_eq}\n\\end{equation}", "case_split",
     "Case $k_1=0$", "Case $k_1=0$: apply the blocking lemma to drop the zero sites"),
    ("PSP5", "The case $k_1 = 1$ is reduced", "where $Z_j = r$.", "case_split",
     "Case $k_1=1$: reduction", "Case $k_1=1$: reduce to $k_1=0$ by taking the derivative; introduce $[Z]^{(j\\to r)}$"),
    ("PSP6", "Using eq. (\\ref{k_is_zero_eq}),\nwe get", "F_{N}^{\\vec{k}}([\\epsilon]_1^{N})\\end{equation}", "conclude",
     "Compute the derivative and shift", "Differentiate in $\\epsilon_2$, apply the $k_1=0$ case and shift indices"),
], SEC["S3"])
node("ClP2", "claim", "$C_N^{(k)}$ as sum of mixed derivatives",
     cut("$C_N^{(k)}$ is obtained by summing", "\\end{equation}", after="\\label{zero_tail_lemma}"), conf=0.75,
     assumptions=[], conclusions=["C_N^{(k)} = \\sum_{\\vec{k},\\omega(\\vec{k})=k} F_N^{\\vec{k}}"])
env("EP11", "F16", "equation", "$C_N^{(k)} = \\sum F_N^{\\vec{k}}$")
env("LP3", "F17", "lemma", "No-hole lemma",
    statement_short="A mixed derivative vanishes if some earlier site has order $\\ge1$ and a later non-final site has order $\\le1$.",
    assumptions=["Let $\\vec{k} = (k_1,\\ldots,k_N)$.", "$\\exists i < j < N$, with $k_i \\geq 1, k_j \\leq 1$"],
    conclusions=["$F_N^{\\vec{k}} = 0$"])
env("PP3", "F18", "proof", "Proof of Lemma 3", proof_strategy=["case_analysis", "algebraic_manipulation"],
    statement_short="Case $k_j=0$: blocking removes dependence on $\\epsilon_i$. Case $k_j=1$: differentiate $P(Z)$ in $\\epsilon_j$ and show the derivative of $F_N$ is blocked from earlier sites.")
for i, fid in enumerate(["F19", "F20", "F21", "F22", "F23", "F24"]):
    env("EP%d" % (12 + i), fid, "equation",
        ["Vanishing for $k_j=0$", "Probability of $Z$ via $X$", "Derivative of $P(Z)$ in $\\epsilon_j$",
         "Derivative of conditional probability", "Derivative of $P\\log P$", "Derivative of $F_N$ in $\\epsilon_j$"][i])
STEPS["anchor"] = "Assume first $k_j = 0$"
steps("PP3", [
    ("PSP7", "Assume first $k_j = 0$.", "\\right|_{\\vec{\\epsilon} = 0} = 0 \\end{equation}", "case_split",
     "Case $k_j=0$", "Case $k_j=0$: by the blocking lemma $F_N$ does not depend on $\\epsilon_i$, so the derivative vanishes"),
    ("PSP8", "The case $k_j = 1$ is more difficult", "and $F_N^{\\vec{k}} = 0$.", "case_split",
     "Case $k_j=1$", "Case $k_j=1$: the $\\epsilon_j$-derivative of $F_N$ is blocked from earlier sites"),
    ("PSP9", "The case $k_j = 1$ is more difficult", "is Kronecker delta.", "setup",
     "Write $P(Z)$ through $X$", "Write $P([Z]_1^N)$ as a sum over hidden paths", None, "PSP8"),
    ("PSP10", "Write now the derivative with respect", "\\right\\} \\right|_{\\epsilon_j = 0} \\end{equation}", "algebraic_manipulation",
     "Differentiate $P(Z)$", "Differentiate $P(Z)$ with respect to $\\epsilon_j$ at $\\epsilon_j=0$", None, "PSP8"),
    ("PSP11", "Using Bayes' rule", "\\right] \\right|_{\\epsilon_j = 0} \\end{equation}", "invoke_identity",
     "Bayes' rule", "Use Bayes' rule to differentiate the conditional probability", None, "PSP8"),
    ("PSP12", "This gives :", "\\right\\} \\right|_{\\epsilon_j = 0} \\end{equation}", "algebraic_manipulation",
     "Derivative of $P\\log P$", "Derivative of $P\\log P(Z_N|\\cdot)$", None, "PSP8"),
    ("PSP13", "And therefore :", "'blocks' the dependence backwards.", "apply_lemma",
     "Blocked derivative of $F_N$", "Combine and use the blocking equation to restrict to sites $j..N$", None, "PSP8"),
    ("PSP14", "Eq. \\ref{F_N_deriv_eq} shows that", "and $F_N^{\\vec{k}} = 0$.", "conclude",
     "Conclude vanishing", "The derivative does not depend on $\\epsilon_i$, $i<j$, hence $F_N^{\\vec k}=0$", None, "PSP8"),
], SEC["S3"])
env("PP4", "F25", "proof", "Proof of Theorem 1", conf=1.0, proves="TP3",
    proof_strategy=["direct", "induction"],
    statement_short="Lemma 3 bounds the support length of nonzero $F_N^{\\vec k}$, Lemma 2 shows they equal those of $N=\\lceil(k+3)/2\\rceil$; summing and analyticity give the limit.")
env("EP18", "F26", "equation", "Reduction to length $\\lceil (k+3)/2 \\rceil$")
STEPS["anchor"] = "\\label{No_hole_strong_lemma}"
steps("PP4", [
    ("PSP15", "Let  $\\vec{k} = [k]_1^N$ with $\\omega(\\vec{k}) = k$.", "\\min_{k_i > 1} \\{i \\}$.", "introduce_variable",
     "Define length of $\\vec k$", "Introduce the length $l(\\vec k)$ of a multi-index of weight $k$"),
    ("PSP16", "It easily\nfollows from lemma", "\\rceil - 1$.", "apply_lemma",
     "Bound the length", "By Lemma 3, a nonzero $F_N^{\\vec k}$ has length at most $\\lceil (k+3)/2\\rceil-1$"),
    ("PSP17", "Therefore, according to lemma", "for all $\\vec{k}$'s in the sum.", "apply_lemma",
     "Pad to a short system", "By Lemma 2 each nonzero term equals one of the system of length $\\lceil (k+3)/2\\rceil$"),
    ("PSP18", "Summing on all\n$F_N^{\\vec{k}}$", "\\rceil$.", "algebraic_manipulation",
     "Sum over weight $k$", "Summing gives $C_N^{(k)}=C_{\\lceil (k+3)/2\\rceil}^{(k)}$ for larger $N$"),
    ("PSP19", "From the analyticity\nof $C_N$", "\\lceil \\frac{k+3}{2} \\rceil $.", "conclude",
     "Pass to the limit", "Analyticity gives $C_N^{(k)}\\to C^{(k)}$, so the settled value is $C^{(k)}$"),
], SEC["S3"])
for nid, fid in [("EP1", "F1"), ("EP2", "F3"), ("EP3", "F4"), ("EP4", "F5")]:
    env(nid, fid, "equation", {"EP1": "Entropy rate", "EP2": "Taylor expansions of $C_N$ and $\\bar H$ in $\\epsilon$",
                               "EP3": "Settling of coefficients (High-SNR)", "EP4": "Definition of $F_N$"}[nid])

# ---------------------------------------------------------------- 2.2 Almost memoryless
node("DP15", "definition", "Almost-Memoryless (A-M) regime",
     cut("In the A-M regime, the Markov transition", "$\\sum_{j=1}^{s}{t_{ij}} = 0$.", after="\\label{almost_memoryless_sec}"),
     conf=0.85, definiendum=["Almost-Memoryless (A-M) regime", "$U$", "$\\delta$"],
     statement_short="A-M regime: $M=U+\\delta T$ with $U$ the uniform matrix, small $\\delta>0$, and $T$ with zero row sums.")
env("TP5", "F27", "theorem", "Analyticity and settling of coefficients (Almost-Memoryless)", main=True, rigor="semi_formal",
    statement_short="In the A-M regime $C_N$ and $\\bar H$ are analytic in $\\delta$ near 0, and their $k$-th coefficients agree for $N\\ge\\lceil (k+3)/2\\rceil$.",
    assumptions=["Let $H_N \\equiv H_N(R,T,\\delta) = H([Y]_1^N)$ be the entropy of a finite system of length $N$, and let $C_N = H_N - H_{N-1}$."],
    conclusions=["There is some (complex) neighborhood $B_{\\rho}(0) = \\{\\delta : |\\delta| < \\rho \\} \\subset \\mathbb{C}$ of $\\delta=0$, in which the (one-variable) functions $\\{ C_N \\}, \\bar{H}$ are analytic in $\\delta$",
                 "N \\geq \\lceil \\frac{k+3}{2} \\rceil \\Rightarrow C_N^{(k)} = C^{(k)}"],
    parts=[{"assumptions": [], "conclusions": ["There is some (complex) neighborhood $B_{\\rho}(0) = \\{\\delta : |\\delta| < \\rho \\} \\subset \\mathbb{C}$ of $\\delta=0$, in which the (one-variable) functions $\\{ C_N \\}, \\bar{H}$ are analytic in $\\delta$"]},
           {"adds_to": 0, "assumptions": [], "conclusions": ["N \\geq \\lceil \\frac{k+3}{2} \\rceil \\Rightarrow C_N^{(k)} = C^{(k)}"]}],
    tags=["entropy_rate", "hidden_markov_process", "series_expansion", "analyticity"])
env("EP19", "F28", "equation", "Taylor expansions in $\\delta$")
env("EP20", "F29", "equation", "Settling of coefficients (A-M)")
env("PP5", "F30", "proof", "Proof of Theorem 2", proof_strategy=["construction", "other"],
    statement_short="Part 1: recast $Y$ as a function of the positive Markov chain $W=(X,Y)$ and apply Han-Marcus Thm. 1.1. Part 2: as for Theorem 1, with $\\delta_i=0$ blocking.")
STEPS["anchor"] = "The proof of analyticity relies"
steps("PP5", [
    ("PSP20", "The proof of analyticity relies", "analytic (as functions of\n$\\delta$) in some complex neighborhood $B_{\\rho}(0) \\subset\n\\mathbb{C}$ of zero.", "other",
     "Part 1: analyticity", "Part 1: analyticity via Han-Marcus", 0.95),
    ("PSP21", "The proof of analyticity relies", "in the following way :", "setup",
     "Plan: use Han-Marcus", "Reduce to Thm. 1.1 of Han-Marcus", None, "PSP20"),
    ("PSP22", "We introduce the\nnew alphabet", "parameterized by\n$\\delta$.", "introduce_variable",
     "Represent $Y$ as function of Markov chain $W$", "Construct the chain $W=(X,Y)$ on $\\Gamma$ with $Y_N=\\Phi(W_N)$", None, "PSP20"),
    ("PSP23", "Moreover, there is some (real)", "entries are positive.", "bound_estimate",
     "Positivity of $\\Delta$", "Near $\\delta=0$ all entries of $\\Delta$ are positive", None, "PSP20"),
    ("PSP24", "Therefore, Thm. 1.1 from", "of zero.", "conclude",
     "Apply Han-Marcus", "Han-Marcus Thm. 1.1 gives analyticity of $C_N$ and $\\bar H$", None, "PSP20"),
    ("PSP25", "The proof of part 2 is very similar", "details are thus omitted here.", "other",
     "Part 2: analogous to Theorem 1", "Part 2: same blocking argument as Theorem 1, with $\\delta_i=0$ making $M_i$ uniform", 0.95),
], SEC["S4"])

# ---------------------------------------------------------------- 3 Coefficients
node("RP4", "remark", "Application: computing expansion coefficients",
     cut("An immediate application of Thms.", "for $N$ large enough."), conf=0.75)
node("AP1", "algorithm", "Coefficient computation by enumeration",
     cut("Our method for computing\n$C^{(k)}$", "summing their contribution."), conf=0.75,
     statement_short="Compute $C^{(k)}$ as $C_N^{(k)}$ at $N=\\lceil(k+3)/2\\rceil$ by enumerating all observation sequences and summing the $k$-th coefficient of $P\\log P$.",
     input=["$k$"], output=["$C^{(k)}$"])
for sid, a, b, sub, nm, order in [
        ("ASP1", "We compute $C_N^{(k)}$ for $N =", "enumerating all sequences\n$[Y]_1^N$", "loop", "Enumerate sequences", 1),
        ("ASP2", "computing the $k$-th coefficient", "for each one", "compute", "Coefficient of $P\\log P$", 2),
        ("ASP3", "and summing their contribution", "and summing their contribution", "compute", "Sum contributions", 3)]:
    node(sid, "algorithm_step", nm, cut(a, b, after="Our method for computing"), conf=0.7,
         section=SEC["S5"], parent_id="AP1", step_order=order, subclass=sub)
node("RP5", "remark", "Exponential cost of the enumeration",
     cut("This\ncomputation is, however, exponential", "for larger alphabets."), conf=0.75)
node("DP16", "definition", "$diag(\\alpha)$",
     cut("For a vector $\\alpha$, $diag(\\alpha)$", "on the diagonal."), conf=0.85,
     definiendum="$diag(\\alpha)$", **EXT_STD)
node("DP17", "definition", "Element-wise matrix operations",
     cut("We use Matlab-like\nnotation", "$\\{a_{ij} b_{ij} \\}$."), conf=0.85,
     definiendum=["$log A$", "$[A .* B]$"], **EXT_STD)
node("DP18", "definition", "Vector of ones $\\xi$",
     cut("$\\xi$ denotes the (column) vector", "of $N$ ones."), conf=0.85, definiendum="$\\xi$")
env("PrP1", "F31", "proposition", "First-order High-SNR expansion for general alphabet", main=True,
    statement_short="First-order expansion of $\\bar H$ in $\\epsilon$ for $R=I+\\epsilon T$ and a general alphabet, in matrix form.",
    assumptions=["Let $R = I + \\epsilon T$.", "Assume that the entropy rate $\\bar{H}$ is analytic in some neighborhood of $\\delta = 0$."],
    conclusions=["$\\bar{H}$ satisfies"], tags=["entropy_rate", "series_expansion"])
env("EP21", "F32", "equation", "First-order High-SNR expansion")
env("PP6", "F33", "proof", "Proof of Proposition 1", proof_strategy=["algebraic_manipulation"],
    statement_short="By Theorem 1, $\\bar H=C_2+O(\\epsilon^2)$; write $C_2$ in matrix form and expand it to first order in $\\epsilon$.")
for nid, fid, nm in [("EP22", "F34", "$C_2 = H(Y_N|Y_{N-1})$"), ("EP23", "F35", "Pair probabilities $F_{ij}$"),
                     ("EP24", "F36", "$C_2$ in matrix form"), ("EP25", "F37", "First-order expansion of $F .* \\log F$")]:
    env(nid, fid, "equation", nm)
STEPS["anchor"] = "Noting that according to Thm."
steps("PP6", [
    ("PSP26", "Noting that according to Thm.", "substituting $R = I + \\epsilon T$.", "apply_lemma",
     "Reduce to $C_2$", "By Theorem 1, $\\bar H=C_2+O(\\epsilon^2)$; plan to expand $C_2$"),
    ("PSP27", "Write $C_2$ as :", "\\label{C_2_eq}\\end{equation}", "setup",
     "Write $C_2$", "Write $C_2$ as a conditional entropy"),
    ("PSP28", "We can express the above probabilities", "\\label{prob_ys_eqs}\\end{equation}", "introduce_variable",
     "Pair probabilities", "Express the probabilities through $\\pi$, $M$, $R$"),
    ("PSP29", "Substituting eq. (\\ref{prob_ys_eqs})", "hmm_entropy} \\end{equation}", "substitute",
     "Matrix form of $C_2$", "Write $C_2$ in matrix form"),
    ("PSP30", "Substituting $R = I + \\epsilon T$ gives", "\\label{F_log_F_first_order} \\end{equation}", "algebraic_manipulation",
     "Expand in $\\epsilon$", "Expand $F$ and $F.*\\log F$ to first order"),
    ("PSP31", "Substituting these in eq.", "(\\ref{general_1st_order_final}).", "conclude",
     "Simplify", "Substitute and simplify to obtain the proposition"),
], SEC["S6"])
node("RP6", "remark", "Proposition 1 generalizes Jacquet et al.",
     cut("We note that prop. \\ref{high_SNR_first_order}", "for a binary\nalphabet."), conf=0.8)
node("ClP3", "claim", "Correctness of the High-SNR series of ZKD1",
     cut("Turning now into the symmetric binary case", "which is not\nrepeated here."), conf=0.7,
     assumptions=["(under the analyticity assumption on $\\bar{H}$)"],
     conclusions=["Thm. \\ref{high_SNR_thm} proves the correctness of the entire expansion from \\cite{ZKD1}"])
env("PrP2", "F38", "proposition", "First-order Almost-Memoryless expansion for general alphabet", main=True,
    statement_short="First-order expansion of $\\bar H$ in $\\delta$ for $M=U+\\delta T$ and a general alphabet; generically linear in $\\delta$.",
    assumptions=["Let $M = U + \\delta T$."], conclusions=["$\\bar{H}$ satisfies"],
    tags=["entropy_rate", "series_expansion"])
env("EP26", "F39", "equation", "First-order A-M expansion")
env("PP7", "F40", "proof", "Proof of Proposition 2", proof_strategy=["algebraic_manipulation"],
    statement_short="Expand $C_2$ in $\\delta$, with $\\pi=s^{-1}\\xi+\\delta\\psi$ found from a perturbed stationarity equation; terms cancel to the result.")
env("EP27", "F41", "equation", "Perturbed stationarity equation")
env("EP28", "F42", "equation", "First-order expansion of $C_2$ in $\\delta$")
STEPS["anchor"] = "Since $\\bar{H} = C_2 + O(\\delta^2)$"
steps("PP7", [
    ("PSP32", "Since $\\bar{H} = C_2 + O(\\delta^2)$", "replaced by $U + \\delta T$.", "setup",
     "Reduce to $C_2$", "Since $\\bar H=C_2+O(\\delta^2)$, expand $C_2$ with $M=U+\\delta T$"),
    ("PSP33", "Dealing with $\\pi$ is more\nproblematic.", "+ \\delta \\psi) + O(\\delta^2) \\end{equation}", "introduce_variable",
     "Perturb $\\pi$", "Write $\\pi=s^{-1}\\xi+\\delta\\psi$ and impose stationarity"),
    ("PSP34", "It follows that $\\psi$ should satisfy", "\\sum_{i=1}^s \\psi_i = 0$.", "algebraic_manipulation",
     "Solve for $\\psi$", "Determine $\\psi$ from $\\psi(I-U)=\\xi T$ and $\\sum\\psi_i=0$"),
    ("PSP35", "Substituting $M =U + \\delta T$ and", "\\label{almost_memoryless_inter_eq}\\end{equation}", "substitute",
     "Substitute into $C_2$", "Substitute into the matrix form of $C_2$"),
    ("PSP36", "After further simplification", "(\\ref{prop_weak_memory}).", "conclude",
     "Simplify", "Cancellations give the proposition"),
], SEC["S7"])
node("RP7", "remark", "Consistency with Ordentlich-Weissman and linear behaviour",
     cut("In \\cite{Weissman:01} it was shown that the first", "for the general case."), conf=0.75)
nodes.append({"id": "ClP4", "type": "claim", "name": "Almost-memoryless series for the symmetric binary HMP up to $O(\\delta^{14})$",
              "statement": cut("We have computed higher orders for the symmetric binary case", "\\label{series_almost_memoryless} \\end{equation}"),
              "section": SEC["S7"], "origin": "paper", "confidence": 0.75, "main": True,
              "statement_short": "Expanding $C_8$ gives $\\bar H$ in $\\delta=1/2-p$ to order 13 for the symmetric binary HMP, with $\\mu=1-2\\epsilon$.",
              "assumptions": ["the symmetric binary case", "the expansion is in the parameter $\\delta = \\frac{1}{2}-p$"],
              "conclusions": [], "tags": ["series_expansion", "symbolic_computation"]})
env("EP29", "F43", "equation", "Symmetric binary A-M series")
node("TP6", "theorem", "Ordentlich-Weissman second-order A-M asymptotics",
     cut("The above expansion generalizes a result from", "+ o(\\delta^2)$."), conf=0.85,
     origin="external", origin_citation="Ordentlich & Weissman",
     assumptions=[], conclusions=["$\\bar{H} = \\log(2) - 2 \\mu^4 \\delta^2 + o(\\delta^2)$"])
node("RP8", "remark", "Odd powers vanish in the A-M series",
     cut("Note that for the first few coefficients, all odd", "(\\cite{ZKD1})."), conf=0.75)

# ---------------------------------------------------------------- 4 Radius of convergence
node("RP9", "remark", "Radius of convergence and analyticity domain",
     cut("The usefulness of a series expansion", "expansion is positive."), conf=0.75)
node("ClP5", "claim", "A-M expansion has much larger estimated radius", rigor="numerical",
     statement=cut("For the High-SNR case, we gave a numerical estimation", "are much\nhigher."), conf=0.7,
     assumptions=[], conclusions=["the numerical values of the estimated radius are much higher"])
node("TP7", "theorem", "Upper and lower bounds on the HMP entropy rate",
     cut("In this figure, the (finite)", "for $N=2$."), conf=0.75,
     origin="external", origin_citation="Cover & Thomas 1991",
     assumptions=[], conclusions=["The upper bound is simply $C_N = H(Y_N | [Y]_1^{N-1})$ and the lower bound is $c_N \\equiv H(Y_N | X_1, [Y]_1^{N-1})$"])
node("ClP6", "claim", "Finite-order expansions versus bounds", rigor="numerical",
     statement=cut("As can be seen from\nthe figure", "$0<p<\\frac{1}{2}$."), conf=0.7,
     assumptions=[], conclusions=["the finite-order expansions are not within the bounds for large values of $\\epsilon$",
                                  "the finite-order expansions remain within the bounds for any $0<p<\\frac{1}{2}$"])
node("TP8", "theorem", "Real analyticity of the binary HMP entropy rate (Han-Marcus)",
     cut("In\nour context, the result of \\cite{Marcus}", "maximal with that respect)."), conf=0.8,
     origin="external", origin_citation="Han & Marcus 2005",
     assumptions=[], conclusions=["$\\bar{H}(p,\\epsilon)$ is real analytic in the domain $\\Omega \\subset \\mathbb{R}^2, \\quad \\Omega = \\{(p,\\epsilon): 0<p,\\epsilon<1 \\}$"])
node("RP10", "remark", "A-M expansion is interior, High-SNR on the boundary",
     cut("For any $0<\\epsilon<1$, the\nA-M expansion", "boundary of $\\Omega$."), conf=0.75)

# ---------------------------------------------------------------- 5 Conclusion
node("ClP7", "claim", "Weaker settling for conditional-probability functionals", rigor="semi_formal",
     statement=cut("For other functions involving only\nconditional", "\\geq k$."), conf=0.7,
     assumptions=["For other functions involving only conditional probabilities (e.g. relative entropy between two {\\it HMPs})"],
     conclusions=["the coefficients 'settle' for $N \\geq k$"])
node("TP9", "theorem", "No finite-chain approximation in the rare-transitions regime",
     cut("We note that this is still a highly non-trivial result", "even to the first order."), conf=0.7,
     origin="external", origin_citation="Nair, Ordentlich & Weissman 2005",
     assumptions=["for other regimes (e.g. 'rare-transitions' \\cite{Weissman:03})"],
     conclusions=["a finite chain of any length does not give the correct asymptotic behavior even to the first order"])

# ================================================================ edges
# definitions of the setup
E("DP1", "DP2"); E("DP1", "DP3"); E("DP2", "DP3"); E("DP3", "AssumP1", conf=0.85)
E("DP2", "DP4"); E("DP3", "DP4"); E("DP5", "DP6"); E("DP2", "DP6", conf=0.7)
E("DP6", "TP1"); E("DP7", "TP1", conf=0.75); E("DP5", "TP1", conf=0.75); E("DP7", "TP2")
E("DP3", "DP8"); E("DP4", "DP8", conf=0.75)
E("DP3", "DP9"); E("DP4", "DP9", conf=0.75)
# Theorem 1 and its machinery
for s in ["DP9", "DP6", "DP5", "DP3"]:
    E(s, "TP3", conf=0.85 if s == "DP9" else 0.8)
E("DP6", "RP1", conf=0.7); E("TP3", "RP1", conf=0.7)
E("DP6", "TP4", conf=0.8); E("TP3", "TP4", conf=0.75, mention=True)
E("TP3", "RP2", conf=0.95, basis="ref", mention=True)
E("DP8", "RP2", conf=0.75)
E("DP9", "RP8", conf=0.75)
for pp, rr in [("PP1", "LP1"), ("PP2", "LP2"), ("PP3", "LP3"), ("PP6", "PrP1"), ("PP7", "PrP2")]:
    E(pp, rr, type="proves", conf=1.0, basis="syntax")
    next(n for n in nodes if n["id"] == pp)["proves"] = rr
E("DP9", "DP10", conf=0.85); E("DP5", "DP10", conf=0.7)
E("DP10", "DP11", conf=0.85); E("DP5", "DP11", conf=0.75); E("DP6", "DP11", conf=0.8)
E("DP11", "ClP1", conf=0.85); E("TP3", "ClP1", conf=0.75, mention=True); E("DP10", "ClP1", conf=0.8)
E("DP10", "RP3", conf=0.8)
E("DP11", "LP1", conf=0.85); E("DP7", "PP1", conf=0.75); E("DP10", "PP1", conf=0.75); E("DP5", "LP1", conf=0.75)
E("DP5", "DP12", conf=0.7); E("DP12", "DP13", conf=0.85); E("DP12", "DP14", conf=0.85)
E("DP13", "DP14", conf=0.85); E("DP11", "DP14", conf=0.85)
E("DP14", "LP2", conf=0.85); E("DP12", "LP2", conf=0.85); E("DP13", "PP2", conf=0.8); E("DP10", "PP2", conf=0.75)
E("DP14", "ClP2", conf=0.85); E("DP13", "ClP2", conf=0.85); E("TP3", "ClP2", conf=0.8, mention=True)
E("ClP1", "ClP2", conf=0.75, basis="inferred")
E("DP14", "LP3", conf=0.85); E("DP12", "LP3", conf=0.85); E("DP13", "PP3", conf=0.8); E("DP10", "PP3", conf=0.75)
E("PP4", "TP3", type="proves", conf=0.9, basis="named")
for s in ["DP12", "DP13", "DP14"]:
    E(s, "PP4", conf=0.8)
E("ClP2", "PP4", conf=0.8, basis="inferred")
E("LP2", "PP4", conf=0.9, basis="named"); E("LP3", "PP4", conf=0.9, basis="named")
# steps
E("PSP1", "PSP3", conf=0.8, basis="inferred"); E("PSP2", "PSP3", conf=0.8, basis="inferred")
E("PSP5", "PSP6", conf=0.8, basis="inferred")
E("PSP9", "PSP10", conf=0.8, basis="inferred"); E("PSP10", "PSP11", conf=0.8, basis="inferred")
E("PSP11", "PSP12", conf=0.8, basis="inferred"); E("PSP12", "PSP13", conf=0.8, basis="inferred")
E("PSP15", "PSP16", conf=0.8, basis="inferred"); E("PSP16", "PSP17", conf=0.8, basis="inferred")
E("PSP17", "PSP18", conf=0.8, basis="inferred"); E("PSP18", "PSP19", conf=0.8, basis="inferred")
E("PSP22", "PSP23", conf=0.75, basis="inferred"); E("PSP23", "PSP24", conf=0.8, basis="inferred")
E("PSP22", "PSP24", conf=0.8, basis="inferred")
E("PSP27", "PSP29", conf=0.8, basis="inferred"); E("PSP28", "PSP29", conf=0.8, basis="inferred")
E("PSP29", "PSP31", conf=0.8, basis="inferred"); E("PSP30", "PSP31", conf=0.8, basis="inferred")
E("PSP33", "PSP34", conf=0.8, basis="inferred"); E("PSP34", "PSP35", conf=0.8, basis="inferred")
E("PSP32", "PSP35", conf=0.75, basis="inferred")
# Theorem 2
for s in ["DP15", "DP6", "DP5", "DP3"]:
    E(s, "TP5", conf=0.85 if s == "DP15" else 0.8)
E("LP1", "PP5", conf=0.85, basis="named"); E("LP2", "PP5", conf=0.85, basis="named"); E("LP3", "PP5", conf=0.85, basis="named")
E("DP4", "PP5", conf=0.75); E("DP3", "PP5", conf=0.8); E("DP10", "PP5", conf=0.7); E("DP1", "PP5", conf=0.75)
# Section 3
E("TP3", "AP1", conf=0.8, basis="inferred"); E("TP5", "AP1", conf=0.8, basis="inferred"); E("DP5", "AP1", conf=0.75)
E("AP1", "RP5", conf=0.8, basis="inferred")
for t in ["PrP1", "PrP2", "PP6", "PP7"]:
    E("DP16", t, conf=0.8); E("DP17", t, conf=0.8); E("DP18", t, conf=0.8)
E("DP9", "PrP1", conf=0.85); E("AssumP1", "PrP1", conf=0.8); E("DP3", "PrP1", conf=0.8); E("DP6", "PrP1", conf=0.8)
E("DP7", "PP6", conf=0.75); E("AssumP1", "PP6", conf=0.8)
E("PrP1", "RP6", conf=0.95, basis="ref", mention=True)
E("DP8", "ClP3", conf=0.8)
E("DP15", "PrP2", conf=0.85); E("DP3", "PrP2", conf=0.8); E("DP6", "PrP2", conf=0.8)
E("TP5", "PP7", conf=0.8, basis="inferred"); E("AssumP1", "PP7", conf=0.8)
E("DP8", "RP7", conf=0.75)
E("TP5", "ClP4", conf=0.8, basis="inferred"); E("AP1", "ClP4", conf=0.75, basis="inferred")
E("DP8", "ClP4", conf=0.8); E("DP15", "ClP4", conf=0.8); E("DP6", "ClP4", conf=0.75)
E("TP6", "ClP4", type="generalizes", conf=0.9, basis="named")
E("DP8", "TP6", conf=0.75)
E("ClP4", "RP8", conf=0.8, basis="inferred")
# Section 4
E("ClP4", "ClP5", conf=0.7, basis="inferred")
E("DP6", "TP7", conf=0.8); E("DP5", "TP7", conf=0.75); E("TP3", "TP7", conf=0.7, mention=True)
E("TP7", "ClP6", conf=0.8, basis="inferred"); E("ClP4", "ClP6", conf=0.75, basis="inferred"); E("DP8", "ClP6", conf=0.8)
E("DP8", "TP8", conf=0.8); E("DP6", "TP8", conf=0.75)
E("TP8", "RP10", conf=0.85); E("DP15", "RP10", conf=0.7); E("DP9", "RP10", conf=0.7)
# Section 5
E("TP3", "ClP7", conf=0.6, basis="inferred", mention=True)

edges = [e for e in edges if e]

graph = {
    "metadata": {
        "title": "Taylor series expansions for the entropy rate of Hidden Markov Processes",
        "arxiv_id": "cs/0510005",
        "authors": ["Or Zuk", "Eytan Domany", "Ido Kanter", "Michael Aizenman"],
        "year": 2005,
        "annotator": "agent-extraction",
        "model": "claude-opus-5-5",
        "effort": "default",
        "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
        "extraction_date": "2026-11-05",
        "rigor_nonformal_count": sum(1 for n in nodes if n.get("rigor")),
        "paper_style": ["theorem_proof", "derivation"],
        "extraction_notes": [
            {"category": "not_extracted", "nodes": [],
             "note": "Thm. 1.1 of Han & Marcus is only applied inside the proof of Theorem 2 (not stated), and the conjecture of ZKD1 that Theorem 1 proves is only mentioned, so neither is a node."},
            {"category": "type_uncertain", "nodes": ["AssumP1"],
             "note": "assumption or definition: one sentence both assumes $M>0$ and introduces $\\pi$; kept as assumption, with term edges from it to the nodes that use $\\pi$."},
            {"category": "boundary_uncertain", "nodes": ["LP1", "LP2", "LP3", "PrP1", "PrP2"],
             "note": "Each proof environment sits inside its lemma/proposition environment, so the result nodes' statements include their proofs (spans as the facts give them)."},
            {"category": "unexpected_construct", "nodes": ["ClP5", "ClP6"],
             "note": "The radius-of-convergence comparison lives mainly in two figures; only the prose statements of the numerical findings were extracted, as numerical claims."},
            {"category": "not_extracted", "nodes": ["TP8"],
             "note": "The open question 'it is not known whether Omega is maximal' sits inside the sentence stating the Han-Marcus result and was not split off as an open_problem."},
        ],
        "extraction_comment": "",
    },
    "nodes": nodes,
    "edges": edges,
}
report = finalize(graph, read_tex(TEX))
for k in ["matched_to_environment", "labels_filled", "proves_added", "ref_uses_added", "ref_backward"]:
    print(k, report[k] if not isinstance(report[k], list) else len(report[k]))
print("ERRORS", len(report["errors"]))
for e in report["errors"]:
    print("  E", e)
print("WARNINGS", len(report["warnings"]))
for w in report["warnings"]:
    print("  W", w)
assert not report["errors"], report["errors"]
json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
print("wrote", OUT, len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
