#!/usr/bin/env python3
"""Build the v7 LLM extraction of arXiv 1707.00314, 'On The Asymptotic Efficiency of Selection Procedures
for Independent Gaussian Populations' (Jacobovic & Zuk 2017). Nodes, types, spans and edges were chosen by
reading the paper; this script only slices the chosen spans out of the prepared source, assembles the
graph and runs finalize().  Usage: python3 build.py [--write]"""
import json, re, sys, subprocess, os
REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize, pseudocode_steps
from latex_facts import read_tex

SCR = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_orzuk/1707_00314"
CASE = REPO + "/corpus/orzuk/1707_00314"
TEX = CASE + "/arxiv_src/arxiv-version-asymptotic-efficiency.tex"
OUT = CASE + "/1707_00314.json"
os.makedirs(SCR, exist_ok=True)
if not os.path.exists(SCR + "/facts.json"):
    subprocess.run([sys.executable, REPO + "/src/latex_facts.py", TEX, "--out", SCR + "/facts.json"], check=True)
facts = json.load(open(SCR + "/facts.json"))
S = facts["source"]
F = {f["id"]: f for f in facts["facts"]}
SECS = [s for s in facts["sections"] if s.get("inside") is None]
LABEL = re.compile(r"\\label\{[^}]*\}")


def norm(t):
    return re.sub(r"\s+", " ", LABEL.sub("", t)).strip()


def sec_at(pos):
    s = max((x for x in SECS if x["start"] <= pos), key=lambda x: x["start"])
    return f"{s['number']} {s['title']}" if s["number"] else s["title"]


def rx(marker):
    return re.compile(r"\s*".join(re.escape(w) for w in marker.split()))


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
    return nid


def env(nid, fid, typ, name, origin="paper", conf=1.0, **kw):
    f = F[fid]
    return add(nid, typ, name, norm(f["statement"]), f["start"], f["end"], origin, conf, **kw)


def prose(nid, typ, name, a, b, lo=0, origin="paper", conf=0.75, end_at=None, **kw):
    i, _ = find(a, lo)
    _, j = find(b, end_at if end_at is not None else i)
    return add(nid, typ, name, norm(S[i:j]), i, j, origin, conf, **kw)


def lit(t, lo=0):
    find(t, lo)
    return norm(t)


EQN = [0]
EPOF = {}


def eq(fid, name, origin="paper", **kw):
    EQN[0] += 1
    nid = f"EP{EQN[0]}"
    env(nid, fid, "equation", name, origin, 1.0, **kw)
    EPOF[fid] = nid
    return nid


CNT = {"proof_step": [0, "PSP"], "algorithm_step": [0, "ASP"]}
ORDER = {}


def step(parent, a, b, subclass, name, short=None, conf=0.75, typ="proof_step"):
    lo, hi = POS[parent]
    i, _ = find(a, lo, hi)
    _, j = find(b, i, hi)
    CNT[typ][0] += 1
    sid = f"{CNT[typ][1]}{CNT[typ][0]}"
    ORDER[parent] = ORDER.get(parent, 0) + 1
    root = parent
    while byid[root]["type"] in ("proof_step", "algorithm_step"):
        root = byid[root]["parent_id"]
    add(sid, typ, name, norm(S[i:j]), i, j, byid[root]["origin"], conf,
        section=byid[root]["section"], parent_id=parent, step_order=ORDER[parent],
        subclass=subclass, statement_short=short or name)
    return sid


def E(s, t, typ="uses", conf=0.8, basis="inferred", **kw):
    e = {"source": s, "target": t, "type": typ, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)


def proves(p, r, conf=0.9, basis="named", **kw):
    byid[p]["proves"] = r
    E(p, r, "proves", conf, basis, **kw)


STD = "standard (uncited)"
DD = "Dudewicz & Dalal 1975"
RIN = "Rinott 1978"

# ============================================================ 1 Introduction
prose("CnjP1", "conjecture", "Logarithmic optimal first-stage sample size",
      "However, our asymptotic analysis motivates a conjecture", "may be asymptotically equivalent.",
      conf=0.8, conclusions=[lit("the optimal sample size in the first stage of both procedures grows logarithmically in the number of populations"),
                             lit("with this optimal choice the multiplicative factor approaches one and the two procedures may be asymptotically equivalent")],
      statement_short="The optimal first-stage sample size of both two-stage procedures grows like log k, making their relative efficiency tend to one.")

# ============================================================ 2 Linear combinations of partial maxima
S2 = F["F1"]["start"] - 3000
prose("DP1", "definition", "I.i.d. sequence X_m with c.d.f. F", "Let $\\{X_m;m=1,2,\\ldots\\}$ be an infinite sequence",
      "F(x) =1$.", conf=0.85, definiendum=["$\\{X_m;m=1,2,\\ldots\\}$", "$F$"])
prose("DP2", "definition", "Partition s_k^(t) of {1,..,k} into T sub-groups", "Let $T\\in\\mathbb{N}$ and for each $k>T$",
      "into $T$ sub-groups.", conf=0.85, definiendum=["$T$", "$s_k^{(t)}$"])
prose("DP3", "definition", "Partial maxima M_k^(t)", "Define the partial maxima of", "t\\in\\mathcal{T}:=\\{1,\\ldots,T\\}$.",
      conf=0.9, definiendum=["partial maxima $M_k^{(t)}$", "$\\mathcal{T}$"])
prose("AssumP1", "assumption", "Broad-sense convergence of the group sizes delta_k^(t)",
      "With regard to this sequence of partitions assume", "\\longrightarrow} \\delta^{(t)}$.", conf=0.8,
      statement_short="Each group size $\\delta_k^{(t)}=s_k^{(t)}-s_k^{(t-1)}$ converges to some $\\delta^{(t)}\\in\\mathbb{N}\\cup\\{\\infty\\}$.")
prose("DP4", "definition", "Max-stable distribution (normalizing constants a_k, b_k)", "Moreover, let $F$ be max-stable",
      "\\end{enumerate}", conf=0.85, origin="external", origin_citation=STD,
      definiendum=["max-stable", "$\\{a_k\\}$", "$\\{b_k\\}$", "$Y\\sim F_Y$"],
      differentia=[lit("$a_k>0$ for any $k>K$"), lit("$\\{a_k\\}$ is weakly-monotonic"),
                   lit("$a_k\\big(\\underset{j=1,\\ldots,k}{\\max} X_j-b_k\\big) \\xrightarrow {\\mathcal{L}}Y$")],
      statement_short="F is max-stable when eventually positive, weakly monotone constants $a_k,b_k$ give $a_k(\\max_{j\\le k}X_j-b_k)\\to Y$ in law, $Y$ continuous.")
prose("DP5", "definition", "Target limit L of P(sum alpha_t M_k^(t) <= xi_k)", "Considering the deterministic sequence",
      "\\end{equation}", conf=0.85, definiendum=["$\\{\\xi_k\\}$", "$\\alpha$", "$L$"],
      statement_short="For thresholds $\\xi_k$ and weights $\\alpha$, $L=\\lim_k P(\\sum_t\\alpha_tM_k^{(t)}\\le\\xi_k)$ is the limit to be computed.")
eq("F1", "Definition of the limit L")
prose("DP6", "definition", "Finite and infinite groups T_1, T_2", "To phrase the main results, consider the partition",
      "corresponding to finite subsequences.", conf=0.85, definiendum=["$\\mathcal{T}_1$", "$\\mathcal{T}_2$"])
prose("DP7", "definition", "Limit a_infinity of the normalizing constants", "In addition, since $\\{a_k\\}$ is positive",
      "exists in the broad sense.", conf=0.8, definiendum="$a_\\infty$")
env("TP1", "F2", "theorem", "Limit of linear combinations of partial maxima (a_infinity > 0)", main=True,
    assumptions=[lit("Let $F$ be a max-stable distribution associated with sequences $\\{a_k\\}, \\{b_k\\}$ such that $a_\\infty\\in(0,\\infty]$."),
                 lit("$\\{M_t;t\\in\\mathcal{T}_1\\}\\cup\\{Y_t;t\\in\\mathcal{T}_2\\}$ is a set of independent r.v's"),
                 lit("suppose that the limit \\begin{equation} L^*:=\\lim\\limits_{k\\rightarrow\\infty}\\bigg\\{\\xi_k-\\sum_{t\\in\\mathcal{T}_2}\\alpha_t b_{\\delta_k^{(t)}}\\bigg\\} \\end{equation} exists in the broad sense")],
    conclusions=[lit("L=F_V(L^*).")],
    statement_short="If $a_\\infty>0$, the limit $L$ equals $F_V(L^*)$, with $V$ the sum of the finite-group maxima and the scaled extreme-value limits of the infinite groups.")
eq("F3", "Limit variable V (a_infinity > 0)")
eq("F4", "Centering limit L*")
eq("F5", "L = F_V(L*)")
env("TP2", "F6", "theorem", "Limit of linear combinations of partial maxima (a_infinity = 0)", main=True,
    assumptions=[lit("Suppose that $F$ is associated with $\\{a_k\\},\\{b_k\\}$ such that $a_{\\infty}=0$,"),
                 lit("there exists an index $t^*\\in\\mathcal{T}_2$ such that"),
                 lit("the limit \\begin{equation} L^{**}:=\\lim\\limits_{k\\rightarrow\\infty}a_k(\\xi_k-\\sum_{t\\in\\mathcal{T}_2}\\alpha_t b_{\\delta_k^{(t)}}) \\end{equation} exists in the broad sense")],
    conclusions=[lit("L=F_V(L^{**}).")],
    statement_short="If $a_\\infty=0$ and the ratios $\\lambda_t$ of the infinite groups' constants converge, $L=F_V(L^{**})$ with $V=\\sum_{t\\in T_2}\\alpha_t\\lambda_tY_t$.")
eq("F7", "Ratio limits lambda_t")
eq("F8", "Limit variable V (a_infinity = 0)")
eq("F9", "Scaled centering limit L**")
eq("F10", "L = F_V(L**)")

# ------------------------------------------------------------ 2.1 Proofs
env("LP1", "F11", "lemma", "Convergence of c.d.f. values under convergence in law", origin="external",
    origin_citation="Billingsley (Convergence of Probability Measures)",
    assumptions=[lit("$V$ is a finite r.v and $V_1,V_2\\ldots$ are r.v's"), lit("$V_k\\xrightarrow{\\mathcal{L}}V$."),
                 lit("$F_V$ is continuous on $\\mathcal{C}\\subseteq\\mathbb{R}$."),
                 lit("$\\{x_k;k\\in\\mathbb{N}\\}$ is a deterministic sequence such that $x_k\\rightarrow\\bar{x}$ where $\\bar{x}\\in\\mathcal{C}\\cup\\{-\\infty,\\infty\\}$ .")],
    conclusions=[lit("Then $F_{V_k}(x_k)\\xrightarrow[k\\rightarrow\\infty]{} F_V(\\bar{x})$.")])
env("LP2", "F12", "lemma", "Convergence in law of sums of independent variables", origin="external", origin_citation=STD,
    assumptions=[lit("Let $s \\in \\mathbb{N}$."), lit("$\\forall k\\in\\mathbb{N}$, $Z_k^{(1)},\\ldots,Z_k^{(s)}$ are independent r.v's such that $Z_k^{(i)}\\xrightarrow[k\\rightarrow\\infty]{\\mathcal{L}}Z_i, \\: \\forall i=1,\\ldots,s$")],
    conclusions=[lit("\\begin{equation} Z_k^{(1)}+\\ldots +Z_k^{(s)}\\xrightarrow[k\\rightarrow\\infty]{\\mathcal{L}}Z_1+\\ldots+Z_s \\end{equation}")])
eq("F13", "Sum converges in law", origin="external", origin_citation=STD)
prose("PP1", "proof", "Proof of Lemma 2", "Lemma \\ref{lemma:convergence_sum} is obtained by", "\\xrightarrow{\\mathcal{L}}(Z_1,\\ldots,Z_s)$.",
      conf=0.8, proof_strategy=["direct"],
      statement_short="Multivariate continuous mapping theorem applied to the jointly converging independent vector.")
proves("PP1", "LP2", conf=0.8)

prose("PP2", "proof", "Proof of Theorem 2.1", "\\proof(Theorem \\ref{thm:sum_max_a_k_positive})", "\\endproof",
      conf=0.9, proof_strategy=["case_analysis", "direct"],
      statement_short="Normalize the infinite-group maxima, combine the limits by Lemma 2 and Slutsky's lemma, then apply Lemma 1 at $L^*$.")
proves("PP2", "TP1")
a = step("PP2", "Assume first that", "\\end{align}", "case_split", "Case all alpha_t/a_inf nonzero: rewrite L",
         "Assume all $\\alpha_t/a_\\infty\\neq0$ and rewrite $L$ with normalized maxima of the infinite groups.")
eq("F14", "Rewriting L with normalized maxima")
b = step("PP2", "For any $t\\in\\mathcal{T}_2$, known properties", "\\xrightarrow{\\mathcal{L}}\\alpha_t M_t$.", "bound_estimate",
         "Limits in law of each summand")
eq("F15", "Normalized maximum converges to alpha_t Y_t / a_inf")
c = step("PP2", "For any $k\\in\\mathbb{N}$, the random variables", "are independent r.v's.", "other", "Independence of the partial maxima")
d = step("PP2", "Therefore, Lemma \\ref{lemma:convergence_sum} implies that", "is a set of independent r.v's.", "apply_lemma",
         "Lemma 2 gives convergence of the sum to V")
eq("F16", "Sum of both parts converges to V")
e = step("PP2", "At this stage, assume that", "converges in law to $V$.", "case_split",
         "Case some alpha_t/a_inf = 0: Slutsky",
         "Split off the summands converging to zero and conclude convergence to $V$ by Slutsky's lemma.")
f = step("PP2", "The distribution of $Y$ is characterized", "hence it is a continuous r.v.", "other", "V is continuous")
g = step("PP2", "Finally, since $L^*$ exists", "Lemma \\ref{lemma:convergence_law}.", "conclude", "Apply Lemma 1 at L*")
for s_, t_ in [(a, d), (b, d), (c, d), (d, e), (e, g), (f, g)]:
    E(s_, t_, conf=0.75)

prose("PP3", "proof", "Proof of Theorem 2.2", "\\proof(Theorem \\ref{thm:sum_max_a_k_zero})", "\\endproof",
      lo=POS["PP2"][1], conf=0.9, proof_strategy=["direct"],
      statement_short="As for Theorem 2.1 with everything scaled by $a_{\\delta_k^{(t^*)}}$: the finite groups vanish, Lemma 2 and Slutsky give $V$, Lemma 1 concludes.")
proves("PP3", "TP2")
a = step("PP3", "In the spirit of the proof", "\\forall t\\in\\mathcal{T}_2$.", "setup", "Reduce to alpha_t lambda_t nonzero")
b = step("PP3", "Under this assumption, the limit $L$", "\\end{align}", "algebraic_manipulation", "Rewrite L scaled by a_{delta^{t*}}")
eq("F17", "Rewriting L with scaled maxima")
c = step("PP3", "By similar arguments as in the proof", "\\end{enumerate}", "bound_estimate", "Limits in law of each scaled summand")
c1_ = step(c, "$\\alpha_t a_{\\delta^{t^*}_k}M_k^{(t)}\\xrightarrow{\\mathcal{L}}0$", "\\forall t\\in\\mathcal{T}_1$.", "bound_estimate", "Item 1: finite groups vanish in law", conf=0.95)
c2_ = step(c, "$\\alpha_t \\frac{a_{\\delta^{t^*}_k}}", "\\forall t\\in\\mathcal{T}_2$.", "bound_estimate", "Item 2: infinite groups converge to alpha_t lambda_t Y_t", conf=0.95)
c3_ = step(c, "For any $k\\in\\mathbb{N}$, $M_k^{(1)}", "are independent r.v's.", "other", "Item 3: independence", conf=0.95)
d = step("PP3", "Since all the preconditions of Lemma", "are independent r.v's.", "apply_lemma", "Lemma 2: infinite groups converge to V")
eq("F18", "Infinite-group sum converges to V")
e = step("PP3", "On the other hand, because convergence in law", "\\end{equation}", "bound_estimate", "Finite groups vanish in probability")
eq("F19", "Finite-group sum tends to 0 in probability")
f = step("PP3", "Thus, Slutsky's Lemma can be applied", "\\end{equation}", "apply_lemma", "Slutsky: total sum converges to V")
eq("F20", "Total sum converges to V")
g = step("PP3", "Fisher-Tippet-Gnedenko's Theorem implies", "so it is also a finite continuous r.v.", "other", "V is continuous")
h = step("PP3", "Finally, since $L^*$ exists in the broad sense, Lemma", "the needed result.", "conclude", "Apply Lemma 1")
for s_, t_ in [(a, b), (b, c), (c, d), (c, e), (d, f), (e, f), (f, h), (g, h)]:
    E(s_, t_, conf=0.75)

# ============================================================ 3 Generalized Robbins-Siegmund
L3 = F["F20"]["end"]
prose("DP8", "definition", "Homoscedastic Gaussian populations X_ij ~ N(theta_i, sigma^2)",
      "Let $X_{ij}\\sim N(\\theta_i,\\sigma^2);i=1,\\ldots,k", "\\in\\mathbb{R}^k$.", lo=L3, conf=0.85,
      definiendum=["$X_{ij}$", "$\\sigma^2$", "$\\theta$"])
prose("ProbP1", "problem", "Selecting the s populations with the largest means", "The task is to find the",
      "populations with the largest means.", lo=L3, conf=0.8)
prose("AP1", "algorithm", "Natural selection by empirical means", "An intuitive procedure for this purpose",
      "associated with the highest values.", lo=L3, conf=0.75, origin="external", origin_citation=STD,
      input=[lit("$X_{ij}\\sim N(\\theta_i,\\sigma^2);i=1,\\ldots,k, \\: j=1,\\ldots,N$")],
      output=[lit("the $s$ populations associated with the highest values")],
      definiendum=None,
      statement_short="Compute each population's empirical mean $\\bar X_i$ and select the $s$ populations with the largest ones.")
step("AP1", "compute the empirical means", "\\forall i=1,\\ldots,k$", "compute", "Compute the empirical means",
     "Compute $\\bar X_i=\\frac1N\\sum_jX_{ij}$ for each population.", 0.7, "algorithm_step")
step("AP1", "select the $s$ populations", "with the highest values", "select", "Select the s largest means", None, 0.7, "algorithm_step")
prose("ProbP2", "problem", "Minimal common sample size N guaranteeing P(CS) >= p", "Our goal is to find the minimal $N$",
      "for this procedure.", lo=L3, conf=0.8)
prose("ClP1", "claim", "P(CS) cannot be controlled without further assumptions", "It is not possible to control the probability",
      "without further assumptions.", lo=L3, conf=0.75,
      conclusions=[lit("It is not possible to control the probability of correct selection (denoted by $\\mathbb{P}(CS)$) without further assumptions.")])
prose("PP4", "proof", "Equal-means counterexample", "To see this, take populations with equal means",
      "is not sensitive to $N$.", lo=L3, conf=0.75, proof_strategy=["construction"],
      statement_short="Counterexample: with all means equal the populations are indistinguishable and P(CS) does not depend on N.")
proves("PP4", "ClP1", conf=0.75, basis="inferred")
prose("DP9", "definition", "Indifference-zone parameter space Theta(Delta,k)", "In order to allow the user to distinguish",
      "bottom $k-s$ populations.", lo=L3, conf=0.85, origin="external", origin_citation="Bechhofer 1954",
      definiendum=["$\\Theta(\\Delta,k)$", "$\\Delta$", "$\\tilde{\\theta}_{[1]}\\leq\\ldots\\leq\\tilde{\\theta}_{[k]}$"],
      genus="parameter-space", differentia=[lit("\\tilde{\\theta}_{[k-s+1]}-\\tilde{\\theta}_{[k-s]}\\geq\\Delta")],
      statement_short="Bechhofer's indifference zone: means whose top-$s$ and bottom-$(k-s)$ groups are separated by at least $\\Delta$.")
eq("F21", "Indifference-zone parameter space", origin="external", origin_citation="Bechhofer 1954")
prose("RP1", "remark", "Delta as the experimenter's indifference level", "$\\Delta$ can also be interpreted as the indifference level",
      "as equivalent populations.", lo=L3, conf=0.7)
prose("ClP2", "claim", "P(CS) tends to 1 as N grows", "Since $(\\bar{X}_1,\\ldots,\\bar{X}_k)$ is a consistent estimator",
      "regardless of the true parametrization.", lo=L3, conf=0.7,
      assumptions=[lit("$(\\bar{X}_1,\\ldots,\\bar{X}_k)$ is a consistent estimator for any $\\theta\\in\\Theta(\\Delta,k)$")],
      conclusions=[lit("the probability of correct selection tends to $1$ as $N\\rightarrow\\infty$, regardless of the true parametrization")])
prose("ClP3", "claim", "The minimal sample size is well-defined", "Thus, the minimal sample size which ensures",
      "is well-defined.", lo=L3, conf=0.7,
      conclusions=[lit("the minimal sample size which ensures correct selection with probability $p$ is well-defined")])
L36 = F["F21"]["end"]
prose("DP10", "definition", "Minimal sample size N*_{k,s}(p)", "Fix $\\Delta>0$ and denote by $N^*_{k,s}(p)$",
      "is above $p$.", lo=L36, conf=0.85, definiendum="$N^*_{k,s}(p)$")
prose("DP11", "definition", "N*_{k,s}(p) as solution of P(CS)=p, event CS^s_{k,N}", "For simplicity, we follow",
      "samples from each population.", lo=L36, conf=0.85, origin="external", origin_citation="Gupta & Panchapakesan (Multiple Decision Procedures)",
      definiendum=["$N_{k,s}^*(p)$", "$CS_{k,N}^s$"],
      statement_short="Ignoring rounding, $N^*_{k,s}(p)$ solves $P(CS^s_{k,N};\\Delta,\\theta^*)=p$, $CS^s_{k,N}$ being correct selection of the top $s$ with $N$ samples each.")
eq("F22", "Defining equation of N*_{k,s}(p)", origin="external", origin_citation="Gupta & Panchapakesan (Multiple Decision Procedures)")
prose("DP12", "definition", "Least favorable configuration (LFC)", "In addition, $\\theta^*$ is some",
      "\\end{equation}", lo=L36, conf=0.9, origin="external", origin_citation=STD,
      definiendum="least favorable configuration (LFC)", genus="parametrization",
      differentia=[lit("\\mathbb{P}(CS^s_{k,N_{k,s}};\\Delta, \\theta^*)=\\inf_{\\tilde{\\theta}\\in\\Theta(\\Delta,k)}\\mathbb{P}(CS^s_{k,N_{k,s}};\\Delta,\\tilde{\\theta})")])
eq("F23", "LFC attains the infimum of P(CS)", origin="external", origin_citation=STD)
prose("TP3", "theorem", "Robbins-Siegmund asymptotic sample size", "With regard to this model, it was shown in",
      "regardless of the value of $p\\in(0,1)$.", lo=L36, conf=0.85, origin="external", origin_citation="Robbins & Siegmund 1967",
      assumptions=[lit("for $s=1$ and $k\\rightarrow\\infty$")],
      conclusions=[lit("$N_{k,s=1}^*(p)\\sim\\frac{2\\sigma^2}{\\Delta^2}\\ln(k-1)$ regardless of the value of $p\\in(0,1)$")])
prose("DP13", "definition", "Asymptotic equivalence a_k ~ b_k", "The asymptotic notation $\\sim$ is interpreted",
      "\\overset{k \\to \\infty}{\\longrightarrow} 1$.", lo=L36, conf=0.85, origin="external", origin_citation=STD,
      definiendum="$a_k\\sim b_k$")
prose("DP14", "definition", "Selection-size regime s_k -> s-bar, ln(s_k)/ln(k-s_k) -> C", "We study the more general settings where",
      "for $\\beta=1$).", lo=L36, conf=0.75, definiendum=["$s:=s_k$", "$\\bar{s}$", "$C$"],
      statement_short="Regime: $1\\le s_k<k-s_k$, $s_k\\to\\bar s\\in\\mathbb{N}\\cup\\{\\infty\\}$ and $\\ln s_k/\\ln(k-s_k)\\to C\\in[0,1]$ (e.g. $s_k$ fixed, $\\ln k$, $\\psi k^\\beta$).")
prose("DP15", "definition", "Shorthand N*_k(p)", "To simplify notation, let $N^*_k(p)", "is understood from context.",
      lo=L36, conf=0.85, definiendum="$N^*_k(p)$")
prose("RP2", "remark", "ln(k-s_k) may be replaced by ln(k)", "Observe that in the following statement we can replace",
      "implies $\\ln(k-s_k)\\sim\\ln(k)$.", lo=L36, conf=0.7)
env("TP4", "F24", "theorem", "Generalized Robbins-Siegmund theorem", main=True,
    assumptions=[lit("$\\forall k\\in\\mathbb{N}$, $1\\leq s_k\\leq k-s_k$."), lit("$s_k\\rightarrow\\bar{s}\\in\\mathbb{N}\\cup\\{\\infty\\}$"),
                 lit("$\\frac{\\ln(s_k)}{\\ln(k-s_k)}\\rightarrow C\\in[0,1]$.")],
    conclusions=[lit("There exists $K_p\\in\\mathbb{N}$ such that $N^*_k(p)$ exists for any $k>K_p$."),
                 lit("$N^*_k(p) \\sim \\tilde{N}_k^* := \\frac{2\\sigma^2(1+\\sqrt{C})^2}{\\Delta^2}\\ln(k-s_k)$ as $k\\rightarrow\\infty$.")],
    statement_short="For every $p$, $N^*_k(p)$ eventually exists and $N^*_k(p)\\sim 2\\sigma^2(1+\\sqrt C)^2\\ln(k-s_k)/\\Delta^2$, independent of $p$ to first order.")

L4p = F["F24"]["end"]
prose("PP5", "proof", "Proof of Theorem 3.1", "\\proof", "\\endproof", lo=L4p, conf=0.9,
      proof_strategy=["direct", "case_analysis"],
      statement_short="Write P(CS) at the LFC as a c.d.f. of a sum of two partial Gaussian maxima and apply Theorem 2.1. "
                      "Existence follows from the intermediate value theorem; the asymptotics from sandwiching $N^*_k$ between $N^\\pm_k(\\tau)$ whose limits are $0$ and $1$.")
proves("PP5", "TP4")
s1 = step("PP5", "Recall the definition of", "$N_k^*$ is well defined.", "other", "Statement 1: existence of N*_k",
          "Statement 1: express $f(n,k)$ as a convolution, then the intermediate value theorem gives $N_k^*$.", conf=0.95)
c1 = step(s1, "Recall the definition of", "and $0$ otherwise.", "setup", "Least favorable configurations")
eq("F25", "Set of least favorable configurations")
c2 = step(s1, "Consequently, w.l.o.g. set $c=0$", "\\end{align}", "introduce_variable", "Define f(n,k) = P(CS) at the LFC")
eq("F26", "f(n,k) as probability of max <= min + Delta")
c4 = step(s1, "Denote the partial maxima by", "\\end{equation}", "algebraic_manipulation",
          "Partial maxima M^(1), M^(2) and convolution formula for f(n,k)")
eq("F27", "Convolution formula for f(n,k)")
c5 = step(s1, "Using this representation of $f(n,k)$", "\\end{enumerate}", "other", "Three observations on f",
          "Observations: $f(\\infty,k)=1$, $f$ continuous in $n$, and $f(1,k)\\to0$ by Theorem 2.1.")
o1 = step(c5, "$f(\\infty;k) :=", "\\forall k\\in\\mathbb{N}$.", "other", "Observation 1: f(infinity,k)=1", conf=0.95)
o2 = step(c5, "For fixed $k$ and", "is continuous in $n$.", "other", "Observation 2: continuity in n", conf=0.95)
o3 = step(c5, "As mentioned in", "f(1,k) = 0$.", "apply_lemma", "Observation 3: f(1,k) -> 0 by Theorem 2.1", conf=0.95)
eq("F28", "Normalizing constants of the Gaussian maximum", origin="external", origin_citation="Leadbetter, Lindgren & Rootzen 1983")
eq("F29", "L* = -infinity for n = 1")
c6 = step(s1, "To end the proof of the first statement", "$N_k^*$ is well defined.", "conclude",
          "Intermediate value theorem gives N*_k")
for s_, t_ in [(c1, c2), (c2, c4), (c4, c5), (o1, c6), (o2, c6), (o3, c6)]:
    E(s_, t_, conf=0.75)
s2 = step("PP5", "We prove the statement for two separate cases", "previously for Case $1$.", "other",
          "Statement 2: asymptotics of N*_k", "Statement 2: two cases, $s_k\\to\\infty$ and $s_k\\to\\bar s$ finite.", conf=0.95)
d1 = step(s2, "We prove the statement for two separate cases", "\\end{equation}", "introduce_variable", "Define upsilon(r)")
eq("F30", "Auxiliary function upsilon")
d2 = step(s2, "{\\bf \\underline{Case $1$}:}", "which ends the proof of this case.", "case_split",
          "Case 1: s_k -> infinity", conf=0.95)
k1 = step(d2, "For any $\\tau\\in(0,1)$ define the following sequences", "\\end{equation}", "introduce_variable", "Bracketing sequences N^pm_k(tau)")
eq("F31", "Bracketing sample sizes N^pm_k(tau) (case 1)")
k2 = step(d2, "Recalling the normalizing sequences used in the proof", "\\end{equation}", "bound_estimate", "L*(N^pm) = pm infinity")
eq("F32", "L*(N^pm_k) = pm infinity (case 1)")
k3 = step(d2, "As mentioned in the proof of Statement $1$", "\\end{equation}", "apply_lemma", "Theorem 2.1: f(N^-)->0, f(N^+)->1")
eq("F33", "f(N^+_k, k) -> 1")
k4 = step(d2, "In addition, by definition", "\\end{equation}", "bound_estimate", "f(N^-) < p < f(N^+) eventually")
eq("F34", "Sandwich of f values")
k5 = step(d2, "$f(n,k)$ is nondecreasing in $n$.", "\\end{equation}", "bound_estimate", "Monotonicity sandwiches N*_k")
eq("F35", "Sandwich N^-_k <= N*_k <= N^+_k")
k6 = step(d2, "Recalling the exact expressions of", "\\end{equation}", "algebraic_manipulation", "Scaled limits 1 pm tau")
eq("F36", "Scaled limits of N^pm_k equal 1 pm tau")
k7 = step(d2, "Fix $\\epsilon>0$.", "\\end{equation}", "bound_estimate", "Ratio within 1 pm (tau + eps/2)")
eq("F37", "Ratio bound with tau and epsilon")
k8 = step(d2, "Thus, by rearranging this inequality", "which ends the proof of this case.", "conclude", "Choose tau_eps; ratio -> 1")
eq("F38", "Final epsilon bound (case 1)")
for s_, t_ in [(k1, k2), (k2, k3), (k3, k4), (k4, k5), (k5, k7), (k6, k7), (k7, k8)]:
    E(s_, t_, conf=0.75)
E(o3, k3, conf=0.8, basis="named")
E(c6, k4, conf=0.75)
d3 = step(s2, "{\\bf \\underline{Case $2$}:}", "previously for Case $1$.", "case_split", "Case 2: s_k -> s-bar finite", conf=0.95)
m1 = step(d3, "The sequence of naturals", "up to some finite prefix.", "setup", "s_k is eventually constant")
m2 = step(d3, "Therefore, since this claim is about", "previously for Case $1$.", "conclude",
          "Bracketing sequences for k - s-bar; repeat Case 1")
eq("F39", "Bracketing sample sizes N^pm_k(tau) (case 2)")
eq("F40", "L*(N^pm_k) = pm infinity (case 2)")
E(m1, m2, conf=0.75)
E(d2, m2, conf=0.85, basis="named")
E(d1, k1, conf=0.75); E(d1, m2, conf=0.75)
E(s1, s2, conf=0.8, basis="named")

prose("ClP4", "claim", "Numerical accuracy of the generalized Robbins-Siegmund approximation",
      "The results confirm our analytic asymptotic predictions, yet", "the size $s_k$ of the selected set.",
      conf=0.7, rigor="numerical",
      conclusions=[lit("The results confirm our analytic asymptotic predictions, yet the rate at which the numerical results approach the asymptotic limit depends on $p$ and the size $s_k$ of the selected set.")])

# ============================================================ 4 Two-stage procedures
L4 = F["F40"]["end"]
prose("ClP5", "claim", "Dudewicz-Dalal is asymptotically more efficient by 2^{2/(N_0-1)}", "Our major conclusion states that",
      "in the first stage.", lo=L4, conf=0.8, main=True,
      assumptions=[lit("as $k\\rightarrow\\infty$"), lit("where $N_0$ is the sample size used by both procedures in the first stage")],
      conclusions=[lit("the procedure in \\cite{dudewicz1975allocation} is relatively more efficient by a factor of $2^{\\frac{2}{N_0-1}}$")],
      statement_short="As $k\\to\\infty$, Dudewicz-Dalal needs fewer samples than Rinott by the factor $2^{2/(N_0-1)}$.")
prose("DP16", "definition", "Heteroscedastic Gaussian populations Pi_i", "Let $X_{ij}\\sim N(\\theta_j,\\sigma_j^2)",
      "variances $\\sigma_i^2$.", lo=L4, conf=0.85, definiendum=["$X_{ij}$", "$\\Pi_i$", "$\\theta_i$", "$\\sigma_i^2$"])
prose("DP17", "definition", "Ordered means theta_[i]", "Denote the ordered means by $\\theta_{[1]}",
      "\\theta_{[k+1]}$.", lo=L4, conf=0.85, definiendum="$\\theta_{[1]}\\leq\\ldots\\leq\\theta_{[k+1]}$")
prose("ProbP3", "problem", "Selecting the best of k+1 Gaussian populations with unknown variances", "The goal is to select the best population",
      "mean is $\\theta_{[k+1]}$.", lo=L4, conf=0.8)
prose("DP18", "definition", "Multi-stage selection procedures", "We consider general selection procedures, namely",
      "results of previous stages.", lo=L4, conf=0.8, definiendum="multi-stage procedures", genus="selection procedures",
      differentia=[lit("sequentially draw samples from the populations where the number of samples drawn from each population at any stage may depend on the sampling results of previous stages")])
prose("TP5", "theorem", "No single-stage procedure controls P(CS) with unknown variances", "Considering the known indifference parameter",
      "\\in\\mathbb{R}^{k+1}_{++}$.", lo=L4, conf=0.85, origin="external", origin_citation="Dudewicz 1971",
      conclusions=[lit("no {\\it single-stage} procedure controls the probability of correct selection above a prescribed value $p\\in(0,1)$")],
      assumptions=[lit("the known indifference parameter $\\Delta>0$"), lit("for any parametrization $(\\theta_1,\\ldots,\\theta_{k+1})\\in\\Theta(\\Delta,k+1), (\\sigma_1^2,\\ldots,\\sigma_{k+1}^2)\\in\\mathbb{R}^{k+1}_{++}$")])
prose("TP6", "theorem", "Two-stage procedures control P(CS)", "Consequentially, \\cite{dudewicz1975allocation,rinott1978two} provided",
      "above a prescribed value $p\\in(0,1)$.", lo=L4, conf=0.75, origin="external", origin_citation="Dudewicz & Dalal 1975; Rinott 1978",
      conclusions=[lit("they are guaranteed to control $\\mathbb{P}(CS)$ above a prescribed value $p\\in(0,1)$")])

# ------------------------------------------------------------ 4.2 Dudewicz and Dalal
env("AP2", "F41", "algorithm", "Dudewicz and Dalal's two-stage procedure P_E", origin="external", origin_citation=DD,
    input=[lit("$\\Delta$ - indifference parameter"), lit("$N_0 \\geq 2$ - initial sample size"), lit("$p$ - desired $\\mathbb{P}(CS)$")],
    output=[lit("$\\hat{i}$ - selected population")],
    statement_short="Stage one estimates each variance from $N_0$ samples; stage two tops up to $N_i\\propto S_i^2(h/\\Delta)^2$ samples and selects the largest weighted mean.")
steps = pseudocode_steps(facts, "F41", byid["AP2"], first_seq=CNT["algorithm_step"][0] + 1)
# printed lines: Stage One items 1-2, Stage Two items 1-3; the sub-items (a)-(c) are conditions on the
# weights of Stage Two item 2, not operations, and are dropped.  The parser nests Stage Two under
# Stage One item 2 (two separate enumerate lists); Stage Two's items are re-parented to the algorithm.
names = ["Stage one: draw N_0 observations", "Stage one: unbiased variance estimates S_i^2",
         "Stage two: draw N_i - N_0 more samples", "Stage two: choose weights a_ij", None, None, None,
         "Stage two: select the largest weighted mean"]
subs = ["other", "compute", "compute", "solve", None, None, None, "select"]
shorts = ["Draw $N_0$ observations from each population.", "Compute the unbiased variance estimate $S_i^2$ of each population.",
          "Draw $N_i-N_0$ further samples, $N_i=\\max\\{N_0+1,\\lceil (h_k^{(1)}/\\Delta)^2S_i^2\\rceil\\}$.",
          "Choose weights $a_{ij}$ summing to one, equal on the first stage, with $S_i^2\\sum_j a_{ij}^2=(\\Delta/h_k^{(1)})^2$.",
          None, None, None, "Select $\\hat i=\\arg\\max_i\\sum_j a_{ij}X_{ij}$."]
order = 0
for k_, s_ in enumerate(steps):
    if names[k_] is None:
        continue
    order += 1
    CNT["algorithm_step"][0] += 1
    nid = f"ASP{CNT['algorithm_step'][0]}"
    stmt = s_["statement"]
    if k_ == 1:   # Stage One item 2 is only its own line, not the Stage Two list after it
        stmt = stmt[:stmt.index("\\end{enumerate}")]
    add(nid, "algorithm_step", names[k_], norm(stmt), 0, 0, "external", 1.0, section=byid["AP2"]["section"],
        parent_id="AP2", step_order=order, subclass=subs[k_], statement_short=shorts[k_])
eq("F42", "Second-stage sample size N_i", origin="external", origin_citation=DD)
eq("F43", "Selection rule: largest weighted mean", origin="external", origin_citation=DD)
L42 = F["F41"]["end"]
prose("TP7", "theorem", "Existence of the weights a_ij", "As mentioned in \\cite{dudewicz1975allocation} a set of numbers",
      "it is easy to compute.", lo=L42, conf=0.75, origin="external", origin_citation=DD,
      conclusions=[lit("a set of numbers $\\{a_{ij}\\}$ almost surely exists and it is easy to compute")])
prose("TP8", "theorem", "Dudewicz-Dalal lower bound on P(CS)", "This probability is bounded from below by the following integral",
      "degrees of freedom (d.f's).", lo=L42, conf=0.85, origin="external", origin_citation=DD,
      conclusions=[lit("\\mathbb{P}(CS|P_E)\\geq\\int_{-\\infty}^{\\infty}G_{\\nu}^k(t+h_k^{(1)})g_{\\nu}(t)dt")],
      assumptions=[lit("where $G_{\\nu}$ and $g_{\\nu}$ are the c.d.f. and p.d.f. of Student's $t$-distribution with $\\nu=N_0-1$ degrees of freedom (d.f's)")],
      statement_short="P(CS) of $P_E$ is at least $\\int G_\\nu^k(t+h)g_\\nu(t)dt$, with $G_\\nu,g_\\nu$ the Student-$t_{N_0-1}$ c.d.f. and density.")
eq("F44", "Lower bound on P(CS|P_E)", origin="external", origin_citation=DD)
prose("DP19", "definition", "Constant h_k^(1) and function f_1(h,k)", "Therefore, in order to ensure that the probability",
      "\\end{equation}", lo=L42, conf=0.85, origin="external", origin_citation=DD,
      definiendum=["$h_k^{(1)}$", "$f_1(h,k)$"],
      statement_short="$h_k^{(1)}(\\nu)$ solves $f_1(h,k)=\\int G_\\nu^k(t+h)g_\\nu(t)dt=p$.")
eq("F45", "Defining equation of h_k^(1)", origin="external", origin_citation=DD)
env("LP3", "F46", "lemma", "Unique positive solution for h_k^(1)",
    conclusions=[lit("There exists $K>0$ such that $\\forall k>K$ eq. \\eqref{eq:h1_integral_def} has a unique positive solution.")])
prose("PP6", "proof", "Proof of Lemma 3", "\\proof $G_{\\nu}$ is strictly increasing", "\\endproof", lo=L42, conf=0.9,
      proof_strategy=["direct"],
      statement_short="Strict monotonicity, bounded convergence and the intermediate value theorem give a unique root; $f_1(0,k)\\to0<p$ makes it positive.")
proves("PP6", "LP3")
a = step("PP6", "$G_{\\nu}$ is strictly increasing hence", "\\forall k\\in\\mathbb{N}$.", "bound_estimate", "f_1 strictly increasing in h")
b = step("PP6", "Since $G_{\\nu}$ is bounded", "such that $f_1(h,k)=p$.", "apply_lemma",
         "Bounded convergence + IVT: unique root")
c = step("PP6", "In addition, $G_{\\nu}^k(t)", "\\forall k>K$.", "bound_estimate", "f_1(h,k) < p for h <= 0 eventually")
d = step("PP6", "Finally, because", "positive $\\forall k>K$.", "conclude", "The root is positive")
for s_, t_ in [(a, b), (a, c), (b, d), (c, d)]:
    E(s_, t_, conf=0.75)

# ------------------------------------------------------------ 4.3 Rinott
L43 = POS["PP6"][1]
prose("AP3", "algorithm", "Rinott's two-stage procedure P_R", "Rinott introduced such a procedure $P_R$",
      "specified by Rinott.", lo=L43, conf=0.8, origin="external", origin_citation=RIN,
      statement_short="Dudewicz-Dalal's procedure with ordinary means ($a_{ij}=1/N_i$) and Rinott's constant $h_k^*\\ge h_k^{(1)}$ in place of $h_k^{(1)}$.")
step("AP3", "in Step $3$ set", "\\forall i,j$", "compute", "Use ordinary means a_ij = 1/N_i", None, 0.7, "algorithm_step")
step("AP3", "in Step $2$ replace", "specified by Rinott", "update", "Replace h_k^(1) by Rinott's h_k^*",
     "Use Rinott's constant $h_k^*\\ge h_k^{(1)}$, the root of his integral equation.", 0.7, "algorithm_step")
prose("DP20", "definition", "Rinott's constant h_k^(2) and function f_2(h,k)", "Practically, Rinott suggested to use",
      "\\end{equation}", lo=L43, conf=0.85, origin="external", origin_citation=RIN,
      definiendum=["$h_k^{(2)}$", "$f_2(h,k)$"],
      statement_short="Rinott's practical constant $h_k^{(2)}\\ge h_k^*$ solves $f_2(h,k)=[\\int G_\\nu(t+h)g_\\nu(t)dt]^k=p$.")
eq("F47", "Defining equation of h_k^(2)", origin="external", origin_citation=RIN)
prose("ClP6", "claim", "h_k^(2) is well-defined and eventually positive", "The same arguments used in Lemma",
      "up to a finite prefix.", lo=L43, conf=0.75, rigor="semi_formal",
      conclusions=[lit("$\\{h_k^{(2)}\\}_{k\\in\\mathbb{N}}$ is also well-defined and positive up to a finite prefix")])
prose("AssumP2", "assumption", "w.l.o.g. 0 < h_k^(1) <= h_k^(2) for all k", "Consequently, since our analysis performs",
      "\\forall k\\in\\mathbb{N}$.", lo=L43, conf=0.8)

# ------------------------------------------------------------ 4.4 Asymptotic efficiency
L44 = POS["AssumP2"][1]
prose("PP7", "proof", "Both procedures draw infinitely many samples", "To see how this expected sample size relates",
      "as $k\\rightarrow\\infty$.", lo=L44, conf=0.65, proof_strategy=["direct"],
      statement_short="Both procedures draw unboundedly many samples, so the maximum with $N_0+1$ is eventually inactive.")
prose("ClP7", "claim", "Expected sample sizes are (h_k^(j))^2 sum sigma_i^2 / Delta^2", "Therefore, regardless the value of $N_0$",
      "up to rounding errors.", lo=L44, conf=0.7, rigor="semi_formal",
      assumptions=[lit("for any large enough $k$")],
      conclusions=[lit("the procedures $P_E$ and $P_R$ are associated respectively with expected sample-sizes of $\\big(h_k^{(1)}\\big)^2 \\sum_{i=1}^{k+1}\\frac{\\sigma_i^2}{\\Delta^2}$ and $\\big(h_k^{(2)}\\big)^2 \\sum_{i=1}^{k+1}\\frac{\\sigma_i^2}{\\Delta^2}$, up to rounding errors")])
proves("PP7", "ClP7", conf=0.65, basis="inferred")
prose("ClP8", "claim", "Relative efficiency reduces to the ratio (h^(2)/h^(1))^2", "Consequently, in order to analyze the asymptotic relative efficiency",
      "as $k\\rightarrow\\infty$.", lo=L44, conf=0.7)
prose("RP3", "remark", "First-order approximations of h_k^(1), h_k^(2) (announcement)", "Theorems \\eqref{thm:dalal_asymptotic} and",
      "to be specified later.", lo=L44, conf=0.7,
      statement_short="Announces $h_k^{(1)}\\sim\\gamma_\\nu k^{1/\\nu}q_p$ and $h_k^{(2)}\\sim2^{1/\\nu}\\gamma_\\nu k^{1/\\nu}q_p$, with $q_p$ the Fréchet quantile.")
prose("ClP9", "claim", "h_k^(2) - h_k^(1) diverges", "This result implies that for any initial sample size",
      "\\rightarrow\\infty$.", lo=L44, conf=0.75,
      conclusions=[lit("for any initial sample size $h_k^{(2)}-h_k^{(1)}\\rightarrow\\infty$")])
prose("ClP10", "claim", "Rinott's numerical insight fails for large k", "Therefore, regardless the exact value of $p$, the numerical insight",
      "is also increased.", lo=L44, conf=0.75,
      conclusions=[lit("is incorrect for large enough values of $k$ unless the sample size $N_0=\\nu+1$ is also increased")],
      statement_short="Rinott's observation that $h_k^{(1)}$ and $h_k^{(2)}$ are close for $p\\ge0.75$ fails for large $k$ unless $N_0$ grows.")
env("TP9", "F48", "theorem", "Asymptotics of the Dudewicz-Dalal constant h_k^(1)", main=True,
    assumptions=[lit("Let $q_p$ be the $p$'th quantile of $\\nu$-Fr\\'echet distribution")],
    conclusions=[lit("Then $h_k^{(1)}\\sim \\tilde{h}_k^{(1)} := \\gamma_\\nu k^{\\frac{1}{\\nu}}q_p$.")],
    statement_short="$h_k^{(1)}\\sim\\gamma_\\nu k^{1/\\nu}q_p$, with $q_p$ the $\\nu$-Fréchet quantile and $\\gamma_\\nu$ an explicit Gamma-function constant.")
eq("F49", "Constant gamma_nu")
L441 = F["F48"]["end"]
prose("PP8", "proof", "Proof of Theorem 4.1", "\\proof", "\\endproof", lo=L441, conf=0.9, proof_strategy=["direct"],
      statement_short="Write $f_1$ as the c.d.f. of a Student-$t$ maximum minus an independent $t$, apply Theorem 2.2 with Fréchet normalization, and sandwich $h_k^{(1)}$ between $\\gamma_\\nu k^{1/\\nu}q_{p\\pm\\tau}$.")
proves("PP8", "TP9")
a = step("PP8", "Set some $\\tau\\in(0,p\\wedge1-p)$", "Fr\\'echet distribution.", "introduce_variable", "Bracketing sequences h^pm_k(tau)")
eq("F50", "Bracketing sequences h^pm_k(tau)")
b = step("PP8", "The Fr\\'echet distribution is nonnegative and continuous and hence its quantiles", "0<p-\\tau<p+\\tau<1$.", "setup",
         "Frechet quantiles are well defined")
c = step("PP8", "In addition, let $X_1,\\ldots,X_{k+1}", "\\end{equation}", "invoke_identity", "f_1 as c.d.f. of max of t's minus a t")
eq("F51", "f_1 as probability of max minus X_{k+1}")
d = step("PP8", "Recall a known result", "\\end{equation}", "setup", "Recall Grigelionis: Student-t maxima are Frechet; limits L**",
         "Recall that Student-$t$ maxima have a $\\nu$-Fréchet limit with $a_k=\\gamma_\\nu^{-1}k^{-1/\\nu}$, $b_k=0$, and compute $L^{**}(h^\\pm_k)=q_{p\\pm\\tau}$.")
prose("TP10", "theorem", "Extreme value limit of Student's t maxima", "Recall a known result", "b_k\\equiv0$.", lo=L441,
      conf=0.85, origin="external", origin_citation="Grigelionis 2013, Proposition 2.5 (constant corrected)",
      conclusions=[lit("the extreme value distribution of a sequence of i.i.d Student's $t$ random variables with $\\nu$ d.f's is $\\nu$-Fr\\'echet distribution with the normalizing constants $a_k:=\\gamma_{\\nu}^{-1} k^{-\\frac{1}{\\nu}}$ and $b_k\\equiv0$")])
eq("F52", "L**(h^pm_k) = q_{p pm tau}")
f = step("PP8", "The c.d.f of $\\nu$-Fr\\'echet distribution is continuous", "\\end{equation}", "apply_lemma", "Theorem 2.2: f_1(h^pm) -> p pm tau")
eq("F53", "f_1(h^-_k) -> p - tau")
g = step("PP8", "By definition, $f_1(h_k^{(1)},k)=p", "\\end{equation}", "bound_estimate", "f_1 values sandwiched eventually")
eq("F54", "Sandwich of f_1 values")
h = step("PP8", "Since for any $k\\in\\mathbb{N}$, $f_1(h,k)$ is strictly increasing", "\\end{equation}", "bound_estimate", "Sandwich h^-_k < h_k^(1) < h^+_k")
eq("F55", "Sandwich of h_k^(1)")
i_ = step("PP8", "The Fre\\'chet distribution is nonnegative", "\\end{equation}", "algebraic_manipulation", "Divide by gamma k^{1/nu} q_p")
eq("F56", "Scaled sandwich of h_k^(1)")
j_ = step("PP8", "Since the $\\nu$-Fr\\'echet distribution is continuous, the inverse function theorem", "\\tilde{h}_k^{(1)} := \\gamma_\\nu k^\\frac{1}{\\nu}q_p$.",
          "conclude", "Let tau -> 0: h_k^(1) ~ h-tilde_k^(1)")
eq("F57", "Quantile ratios within epsilon")
eq("F58", "Ratio h_k^(1)/h-tilde within epsilon")
for s_, t_ in [(a, d), (c, f), (d, f), (b, f), (f, g), (g, h), (h, i_), (i_, j_), (b, i_)]:
    E(s_, t_, conf=0.75)

env("TP11", "F59", "theorem", "Asymptotics of Rinott's constant h_k^(2)", main=True,
    assumptions=[lit("With the same notations of Theorem \\ref{thm:dalal_asymptotic}")],
    conclusions=[lit("$h_k^{(2)}\\sim \\tilde{h}_k^{(2)} := 2^{\\frac{1}{\\nu}}\\gamma_\\nu k^{\\frac{1}{\\nu}}q_p$.")],
    statement_short="$h_k^{(2)}\\sim2^{1/\\nu}\\gamma_\\nu k^{1/\\nu}q_p$: Rinott's constant is larger by the factor $2^{1/\\nu}$.")
L442 = F["F59"]["end"]
prose("PP9", "proof", "Proof of Theorem 4.2", "\\proof", "\\endproof", lo=L442, conf=0.9, proof_strategy=["direct"],
      statement_short="Write $f_2$ as the c.d.f. of a maximum of sums of two $t_\\nu$ variables, whose density tail is twice that of $t_\\nu$ (Ghosh's density, Euler and Gauss hypergeometric identities). "
                      "The Fréchet normalization gains the factor $2^{-1/\\nu}$ and the argument of Theorem 4.1 concludes.")
proves("PP9", "TP11")
a = step("PP9", "Let $T_i^{(j)}\\overset{i.i.d}{\\sim}t_\\nu", "\\end{align}", "invoke_identity", "f_2 as c.d.f. of a max of sums of t's")
eq("F60", "f_2 as probability of a maximum of t sums")
b = step("PP9", "Let $\\tilde{g}_\\nu$ be the density", "with $|z|<1$.", "setup", "Ghosh's density of a sum of two t's")
eq("F61", "Density of the sum of two Student t variables", origin="external", origin_citation="Ghosh 1975, eq. (2.1)")
c = step("PP9", "We next use Euler's transformation", "\\end{equation}", "invoke_identity", "Euler's transformation of 2F1",
         "Apply Euler's transformation to rewrite the density's hypergeometric factor.")
env("TP12", "F62", "theorem", "Euler's transformation for the hypergeometric function", origin="external",
    origin_citation="Euler (standard, uncited)", conf=0.9, conclusions=[lit("{}_2 F_1(a, b; c; z) = (1-z)^{c-a-b}{}_2 F_1(c-a, c-b; c; z)")])
eq("F63", "Density of the sum after Euler's transformation")
d = step("PP9", "We have $\\frac{t^2}{4\\nu+t^2}", "provided by Gauss' Theorem.", "invoke_identity", "Limit of 2F1 at 1 by Gauss' theorem")
eq("F64", "Limit of the hypergeometric factor (Gauss)")
e = step("PP9", "Plugging eq. \\eqref{eq:Gauss_hypergeometric_1} into", "\\end{equation}", "substitute", "Tail: g-tilde ~ 2 g_nu")
eq("F65", "Tail of the density: g-tilde ~ 2 g_nu")
f = step("PP9", "Since the asymptotic values of the densities", "b_k\\equiv0$.", "apply_lemma", "Frechet normalization with factor 2^{-1/nu}",
         "Grigelionis' Propositions 2.3 and 2.5: tail $1-\\tilde G_\\nu\\sim2\\gamma_\\nu^\\nu t^{-\\nu}$, so $a_k=2^{-1/\\nu}\\gamma_\\nu^{-1}k^{-1/\\nu}$.")
eq("F66", "Tail of the c.d.f. of the sum")
g = step("PP9", "Next, set some $\\tau\\in(0,p\\wedge1-p)$", "\\end{equation}", "introduce_variable", "Bracketing sequences h^pm_k(tau)")
eq("F67", "Bracketing sequences for h_k^(2)")
h = step("PP9", "Finally, the arguments used to prove Theorem", "imply the needed result.", "conclude", "Repeat the proof of Theorem 4.1")
for s_, t_ in [(a, f), (b, c), (c, d), (d, e), (e, f), (f, g), (g, h)]:
    E(s_, t_, conf=0.75)
E("TP10", f, conf=0.85, basis="named")

env("CP1", "F68", "corollary", "Rinott's exact constant h_k^* differs from h_k^(1) by O(k^{1/nu})",
    assumptions=[lit("Using the same notations of Theorem \\ref{thm:dalal_asymptotic}")],
    conclusions=[lit("$h_k^*-h_k^{(1)}=\\mathcal{O}(\\gamma_\\nu k^{\\frac{1}{\\nu}}q_p)$ as $k\\rightarrow\\infty$.")])
L443 = F["F68"]["end"]
prose("PP10", "proof", "Proof of Corollary 1", "\\proof", "\\endproof", lo=L443, conf=0.9, proof_strategy=["direct"],
      statement_short="Sandwich $h_k^{(1)}\\le h_k^*\\le h_k^{(2)}$ (Rinott) and use Theorems 4.1-4.2 to bound the scaled difference by $2^{1/\\nu}-1$.")
proves("PP10", "CP1")
eq("F69", "Scaled difference bounded by 2^{1/nu}-1")
eq("F70", "limsup bound")
prose("ClP11", "claim", "Relative efficiency tends to 1 as nu -> infinity after k -> infinity", "Theorems \\ref{thm:dalal_asymptotic},\\ref{thm:rinott_procedure} show the dependency",
      "\\end{equation}", lo=POS["PP10"][1], conf=0.8,
      conclusions=[lit("\\lim_{\\nu \\to \\infty} \\lim_{k \\to \\infty} \\Big(\\frac{h_k^{(2)}(\\nu)}{h_k^{(1)}(\\nu)}\\Big)^2 = \\lim_{\\nu \\to \\infty} 2^{\\frac{2}{\\nu}} = 1 .")])
eq("F71", "Iterated limit nu then k equals 1")
prose("ClP12", "claim", "nu = infinity is a discontinuity point of the relative efficiency", "The next theorem reveals that surprisingly",
      "as a function of $\\nu$.", lo=POS["PP10"][1], conf=0.8,
      conclusions=[lit("\\lim_{k \\to \\infty} \\Big(\\frac{h_k^{(2)}(\\infty)}{h_k^{(1)}(\\infty)}\\Big)^2 = 2"),
                   lit("$\\nu=\\infty$ is a discontinuity point of the asymptotic relative efficiency as a function of $\\nu$")])
eq("F72", "Limit for nu = infinity equals 2")
env("TP13", "F73", "theorem", "Gaussian case nu = infinity: h^(2) ~ sqrt(2) h^(1) ~ 2 sqrt(ln k)",
    assumptions=[lit("For $\\nu=\\infty$")],
    conclusions=[lit("$h_k^{(2)}(\\infty) \\sim\\sqrt{2}h_k^{(1)}(\\infty) \\sim 2\\sqrt{\\ln(k)}$")])
L444 = F["F73"]["end"]
prose("PP11", "proof", "Proof of Theorem 4.3", "\\proof", "\\endproof", lo=L444, conf=0.9, proof_strategy=["direct"],
      statement_short="With $\\nu=\\infty$ the $t$'s are Gaussian: $f_2$ is a Gaussian-maximum c.d.f. (Gumbel limit) and $f_1$ is handled by Theorem 2.1, each followed by the sandwich argument of Theorem 4.1.")
proves("PP11", "TP13")
a = step("PP11", "To derive the asymptotics of $h_k^{(2)}(\\infty)$", "\\sim 2 \\sqrt{\\ln(k)}$.", "other",
         "Item 1: h^(2)(infinity) via the Gumbel limit", conf=0.95)
eq("F74", "f_2 as a Gaussian-maximum probability")
eq("F75", "f_2(h^pm_k) -> p pm tau (nu = infinity)")
b = step("PP11", "To derive the asymptotics of $h_k^{(1)}$, set", "\\sim \\sqrt{2\\ln(k)}$.", "other",
         "Item 2: h^(1)(infinity) via Theorem 2.1", conf=0.95)
eq("F76", "f_1 for nu = infinity")
eq("F77", "f_1(h^pm_k) -> p pm tau (nu = infinity)")
env("RP4", "F78", "remark", "Relative efficiency is invariant to p")
env("RP5", "F79", "remark", "Guaranteed bounds may not be tight")
prose("ClP13", "claim", "Numerical accuracy of the two-stage approximations", "The results confirm our asymptotic predictions.",
      "varies with $\\nu$ and $p$.", lo=F["F79"]["end"], conf=0.7, rigor="numerical",
      conclusions=[lit("The results confirm our asymptotic predictions.")])

# ------------------------------------------------------------ 4.6 Choosing nu
L46 = facts["sections"][13]["start"]
prose("DP21", "definition", "Expected sample size mu_k^(j)(nu)", "Define the expected sample size for the two procedures",
      "is the actual (random) sample size.", lo=L46, conf=0.85, definiendum=["$\\mu_k^{(j)}(\\nu)$", "$N_{i,k}$", "${\\bf N_k^{(j)}}$"])
eq("F80", "Expected sample size mu_k^(j)")
prose("ClP14", "claim", "A minimizing nu exists", "Since $\\mu_k^{(j)}(\\nu) \\to \\infty$ as $\\nu \\to \\infty$",
      "must exist.", lo=L46, conf=0.75,
      assumptions=[lit("$\\mu_k^{(j)}(\\nu) \\to \\infty$ as $\\nu \\to \\infty$")], conclusions=[lit("a minimizer $\\nu_k^{(j*)}$ must exist")])
prose("DP22", "definition", "Optimal parameter nu_k^(j*) and optimal sample size mu_k^(j*)", "Thus, we may define the optimal parameter choice",
      "\\end{equation}", lo=L46, conf=0.85, definiendum=["$\\nu_k^{(j*)}$", "$\\mu_k^{(j*)}$"])
eq("F81", "Optimal nu and optimal expected sample size")
prose("RP6", "remark", "Difficulties in finding the optimal nu", "Finding the optimal parameter",
      "computationally challenging.", lo=L46, conf=0.7)
prose("DP23", "definition", "Approximate expected sample size and approximate optimal nu", "To overcome these difficulties, we propose",
      "\\end{equation}", lo=F["F81"]["end"], end_at=F["F83"]["start"], conf=0.8, definiendum=["$\\tilde{\\mu}_k^{(j)}(\\nu)$", "${\\tilde{\\nu}_k}^{(j*)}$", "${\\tilde{\\mu}}_k^{(j*)}$"],
      statement_short="Ignore the $N_0+1$ floor and replace $h_k^{(j)}$ by $\\tilde h_k^{(j)}$: $\\tilde\\mu_k^{(j)}(\\nu)=(\\tilde h_k^{(j)})^2\\sum\\sigma_i^2/\\Delta^2$, minimized at $\\tilde\\nu_k^{(j*)}$.")
eq("F82", "Approximate expected sample size")
eq("F83", "Approximate optimal nu and sample size")
prose("ClP15", "claim", "The approximate optimum is variance-free: minimize h-tilde^(1)(nu)", "${\\tilde{\\nu}_k}^{(j*)}, {\\tilde{\\mu}}_k^{(j*)}$ do not depend",
      "\\end{equation}", lo=F["F83"]["end"], conf=0.75,
      conclusions=[lit("do not depend on the unknown variances $\\sigma_i^2$ and can be found by minimizing:")],
      statement_short="$\\tilde\\nu_k^{(j*)}$ and $\\tilde\\mu_k^{(j*)}$ do not depend on the variances and minimize the explicit $\\tilde h_k^{(1)}(\\nu)=[\\Gamma(\\frac{\\nu+1}2)k/(-\\nu^{1-\\nu/2}\\sqrt\\pi\\Gamma(\\frac\\nu2)\\ln p)]^{1/\\nu}$.")
eq("F84", "Explicit h-tilde^(1)(nu)")
env("TP14", "F85", "theorem", "Asymptotically optimal first-stage size nu ~ 2 ln k", main=True,
    assumptions=[lit("For $k$ large enough")],
    conclusions=[lit("eq. \\eqref{eq:h_nu} has a unique solution ${\\tilde{\\nu}_k}^{(j*)}$."),
                 lit("${\\tilde{\\nu}_k}^{(j*)} \\sim 2 \\ln(k)$"), lit("$\\tilde{h}_k^{(1*)} \\sim \\sqrt{2 e \\ln(k)}$"),
                 lit("${\\tilde{\\mu}}_k^{(j*)} \\sim 2 e \\ln(k) \\frac{\\sum_{i=1}^k \\sigma_i^2}{\\Delta^2}$")],
    statement_short="The approximate optimum is unique for large $k$, with $\\tilde\\nu_k^*\\sim2\\ln k$, $\\tilde h_k^{(1*)}\\sim\\sqrt{2e\\ln k}$ and $\\tilde\\mu_k^*\\sim2e\\ln k\\sum\\sigma_i^2/\\Delta^2$.")
L46b = F["F85"]["end"]
prose("PP12", "proof", "Proof of Theorem 4.4", "\\proof", "\\endproof", lo=L46b, conf=0.9, proof_strategy=["direct", "algebraic_manipulation"],
      statement_short="First-order condition for $\\ln\\tilde h_k^{(1)}(\\nu)$: the function $\\mathcal H_k$ has derivative above 1 (polygamma bound), so its root is unique. "
                      "Sandwich bounds on $\\mathcal H_k$ give $\\tilde\\nu_k^*\\sim2\\ln k$, and substituting gives $\\sqrt{2e\\ln k}$.")
proves("PP12", "TP14")
a = step("PP12", "Differentiating the logarithm of eq.", "is the digamma function.", "algebraic_manipulation", "First-order condition H_k(nu) = 0")
eq("F86", "Logarithm of h-tilde^(1)(nu)")
eq("F87", "First-order condition")
eq("F88", "Function H_k(nu)")
b = step("PP12", "Since $\\nu>0$ we have", "if and only if $\\mathcal{H}_k(\\nu) = 0$.", "other", "Sign of the derivative is the sign of H_k")
c = step("PP12", "The derivative of $\\mathcal{H}_k$ is", "\\end{equation}", "algebraic_manipulation", "Derivative of H_k")
eq("F89", "Derivative of H_k")
d = step("PP12", "By Lemma $1$ in \\cite{alzer2001mean}", "\\end{equation}", "apply_lemma", "Trigamma monotonicity and recurrence bound")
eq("F90", "Polygamma recurrence bound")
e = step("PP12", "Plugging eq. \\eqref{eq:polygamma_recurrence} into", "is monotonically increasing.", "bound_estimate", "H_k' > 1: H_k increasing")
f = step("PP12", "We use the following bounds,", "\\end{equation}", "bound_estimate", "Sandwich bounds on H_k")
eq("F91", "Bounds on the Gamma ratio and digamma difference")
eq("F92", "Sandwich of H_k")
g = step("PP12", "For $k$ large enough the right bound", "in $\\nu \\in (1,\\infty)$.", "conclude", "Unique root is the global minimum")
h = step("PP12", "We can solve eq. \\eqref{eq:nu_first_order} numerically", "\\end{align}", "bound_estimate", "nu-tilde* ~ 2 ln k")
eq("F93", "Asymptotics of nu-tilde*")
i_ = step("PP12", "Plugging the asymptotic solution", "\\end{align}", "substitute", "h-tilde(2 ln k) ~ sqrt(2e ln k)")
eq("F94", "h-tilde at nu = 2 ln k")
j_ = step("PP12", "Thus, for the choice", "\\frac{\\sum_{i=1}^k \\sigma_i^2}{\\Delta^2}$.", "conclude", "Approximate optimal sample size")
env("RP7", "F95", "remark", "Comparison with Robbins-Siegmund: within a factor e of the known-variance case",
    statement_short="With equal variances, the approximate optimal two-stage sample size $2e k\\ln k\\,\\sigma^2/\\Delta^2$ is a factor $e$ above Robbins-Siegmund's known-variance $2k\\ln k\\,\\sigma^2/\\Delta^2$.")
L46c = F["F95"]["end"]
prose("ClP16", "claim", "Rinott's constant at nu = 2 ln k is also ~ sqrt(2e ln k)", "For Rinott's procedure \\cite{rinott1978two}, the asymptotic behavior",
      "\\end{equation}", lo=L46c, conf=0.75, rigor="semi_formal",
      conclusions=[lit("\\tilde{h}_k^{(2)}\\big(2 \\ln (k)\\big)\\sim 2^{\\frac{1}{2\\ln(k)}} \\tilde{h}_k^{(1)}\\big(2 \\ln (k)\\big) \\sim \\tilde{h}_k^{(1)}\\big(2 \\ln (k)\\big) \\sim \\sqrt{2e\\ln(k)}.")])
eq("F96", "h-tilde^(2) at nu = 2 ln k")
prose("ClP17", "claim", "Optimal-nu procedures are first-order equivalent", "Thus, while for every fixed $\\nu$",
      "up to a first order error term.", lo=L46c, conf=0.75, main=True,
      conclusions=[lit("the approximations of the optimal $\\nu$'s for both procedures are equivalent up to a first order error term")],
      statement_short="Dudewicz-Dalal wins for each fixed $\\nu$, but at the approximately optimal $\\nu$ the two procedures agree to first order.")
prose("PP13", "proof", "Ratio 2^{1/(2 ln k)} tends to 1", "The reason is that as $\\nu = 2\\ln(k)$ increases",
      "goes to $1$.", lo=L46c, conf=0.7, proof_strategy=["direct"],
      statement_short="The factor $2^{1/\\nu}$ with $\\nu=2\\ln k$ tends to 1.")
proves("PP13", "ClP17", conf=0.7, basis="inferred")
prose("RP8", "remark", "Second-order correction for Rinott's procedure", "Although to the first order the two sample sizes are identical",
      "may yield more accurate results.", lo=L46c, conf=0.7)
env("LP4", "F97", "lemma", "Sums of two Student t variables are stochastically ordered in nu",
    assumptions=[lit("Let $T_i^{(j)} \\sim t_{\\nu_i} \\: ; i,j=1,2$ be four independent Student's $t$ r.v's."), lit("with ${\\nu}_1\\leq{\\nu}_2$."),
                 lit("$\\forall h>0$")],
    conclusions=[lit("\\mathbb{P}(T_1^{(1)} + T_1^{(2)} \\leq h) \\leq \\mathbb{P}(T_2^{(1)} + T_2^{(2)} \\leq h) .")])
eq("F98", "Stochastic ordering inequality")
L46d = F["F97"]["end"]
prose("PP14", "proof", "Proof of Lemma 4", "\\proof", "\\endproof", lo=L46d, conf=0.9, proof_strategy=["algebraic_manipulation"],
      statement_short="Fold the convolution integral onto $(0,\\infty)$ using symmetry; since $G_{\\nu_1}<G_{\\nu_2}$ on $t>0$, replace one variable's law at a time.")
proves("PP14", "LP4")
a2 = step("PP14", "Let $\\nu_1 < \\nu_2$.", "in the fifth line of eq. \\eqref{eq:rinott_monotonic_h} above.", "algebraic_manipulation",
          "Fold the convolution and compare c.d.f.s on t > 0")
eq("F99", "Chain of convolution identities and inequalities")
b2 = step("PP14", "To obtain the second inequality", "replaced by $g_{\\nu_1}$.", "conclude", "Repeat with g_{nu_1}: second inequality")
E(a2, b2, conf=0.8, basis="named")
env("CP2", "F100", "corollary", "h_k^(2)(nu) is non-increasing in nu",
    assumptions=[lit("$\\exists K>0$ such that $\\forall k>K$")], conclusions=[lit("$h_k^{(2)}(\\nu)$ is monotonically non-increasing in $\\nu$.")])
L46e = F["F100"]["end"]
prose("PP15", "proof", "Proof of Corollary 2", "\\proof", "\\endproof", lo=L46e, conf=0.9, proof_strategy=["direct"],
      statement_short="Apply Lemma 4 at $h=h_k^{(2)}(\\nu_2)$ in the defining equation of $h_k^{(2)}$ and use monotonicity of $G_{\\nu_1}$.")
proves("PP15", "CP2")
eq("F101", "Convolution comparison at h_k^(2)(nu_2)")
env("RP9", "F102", "remark", "Order of the limits k, nu -> infinity matters",
    statement_short="For fixed $k$, $\\tilde h_k^{(j)}(\\nu)\\sim\\sqrt\\nu\\to\\infty$ while the exact $h_k^{(2)}(\\nu)$ decreases to a finite limit, so $h/\\tilde h\\to1$ is not uniform in $\\nu$.")
eq("F103", "h-tilde^(1)(nu) ~ sqrt(nu) as nu -> infinity")
prose("RP10", "remark", "Only diverging nu_k need be considered", "Since for bounded sequences $\\{\\nu_k\\}$",
      "such that $\\nu_k\\rightarrow \\infty$.", lo=F["F102"]["end"], conf=0.7)
env("TP15", "F104", "theorem", "Asymptotic optimality of nu-tilde* for per-population sample sizes", main=True,
    assumptions=[lit("Consider a sequence $\\{\\nu_k\\}$ such that $\\nu_k\\rightarrow\\infty$"),
                 lit("If $2e \\sigma_i^2 > \\Delta^2, \\: \\forall i\\in\\mathbb{N} $")],
    conclusions=[lit("$\\tilde{N}_{i,k*}\\sim\\big[\\tilde{h}_k^{(1)}(\\tilde{\\nu}_k^{(i*)})\\big]^2\\frac{\\sigma_i^2}{\\Delta^2} \\ \\ , \\ \\ \\forall i\\in\\mathbb{N} \\ \\ , \\ \\ \\mathbb{P}-a.s.$")],
    statement_short="If $2e\\sigma_i^2>\\Delta^2$, the per-population sample size at $\\tilde\\nu_k^*$ is a.s. its second term, and no diverging $\\nu_k$ does asymptotically better.")
L46f = F["F104"]["end"]
prose("PP16", "proof", "Proof of Theorem 4.5", "\\proof", "\\endproof", lo=L46f, conf=0.9, proof_strategy=["direct", "case_analysis"],
      statement_short="Strong law of large numbers for $S_i^2$ plus $\\tilde h_k^{(1)}(\\tilde\\nu_k^*)^2\\sim2e\\ln k$, which eventually dominates $\\tilde\\nu_k^*+2$ when $2e\\sigma_i^2>\\Delta^2$.")
proves("PP16", "TP15")
a = step("PP16", "Since $\\nu_k\\rightarrow\\infty$ and the $S_i^2$'s", "throughout the proof.", "setup", "Strong law of large numbers available")
b = step("PP16", "The following approximation stems", "the claim follows.", "other", "Statement 1", conf=0.95)
b1 = step(b, "The following approximation stems", "\\end{equation}", "apply_lemma", "SLLN: S_i^2 may be replaced by sigma_i^2")
eq("F105", "SLLN approximation")
b2 = step(b, "Let $i\\in\\mathbb{N}$ and consider the sequence", "\\end{equation}", "bound_estimate", "Second term dominates nu-tilde*+2")
eq("F106", "nu-tilde* + 2 below the second term")
b3 = step(b, "Thus, almost surely, up to a finite prefix", "the claim follows.", "conclude", "N-tilde_{i,k*} equals its second term a.s.")
eq("F107", "N-tilde_{i,k*} asymptotics")
c = step("PP16", "Let $i\\in\\mathbb{N}$ and consider the following two cases", "\\end{equation}", "case_split", "Statement 2: case (i)", conf=0.95)
eq("F108", "liminf ratio >= 1 in case (i)")
for s_, t_ in [(a, b1), (b1, b2), (b2, b3), (a, c)]:
    E(s_, t_, conf=0.75)

# ============================================================ 5 Discussion
L5 = facts["sections"][14]["start"]
prose("OpenP1", "open_problem", "Asymptotics of Rinott's exact constant h_k^*", "Can one apply the techniques we used",
      "asymptotic results for $h_k^*$?", lo=L5, conf=0.8)
prose("OpenP2", "open_problem", "Optimality of N_0 ~ 2 ln k", "Can one prove rigorously that our conjecture",
      "optimal choice of the $N_0$ parameter?", lo=L5, conf=0.8)
prose("OpenP3", "open_problem", "Relative efficiency under the actual probability of correct selection", "What is the relative efficiency of the two procedures",
      "instead of its bounds?", lo=L5, conf=0.8)
prose("TP16", "theorem", "Asymptotic inefficiency of Rinott's procedure as Delta -> 0", "Other asymptotic regimes for R\\&S procedures",
      "where $\\Delta^* \\downarrow 0$.", lo=L5, conf=0.7, origin="external", origin_citation="Mukhopadhyay 1979; Chow & Robbins 1965",
      conclusions=[lit("Rinott's procedure is asymptotically inefficient in the sense of \\cite{chow1965asymptotic}, i.e. in the asymptotic regime where $\\Delta^* \\downarrow 0$")])


def SN(parent, name):
    return next(n["id"] for n in nodes if n.get("parent_id") == parent and n["name"] == name)


# ============================================================ edges: words, results, inference
E("TP4", "TP3", "specializes", 0.9, "named")
E("ProbP1", "AP1", "resolves", 0.85, "named")
E("AP1", "ProbP2", conf=0.85, basis="named")
E("ProbP2", "TP4", "resolves", 0.7, "inferred")
E("ProbP3", "AP2", "resolves", 0.85, "named")
E("ProbP3", "AP3", "resolves", 0.85, "named")
E("ClP2", "ClP3", conf=0.85, basis="named")
E("TP4", "ClP4", conf=0.75)
E("AP2", "AP3", conf=0.9, basis="named")
E("AP2", "TP6", conf=0.75); E("AP3", "TP6", conf=0.75)
E("TP10", SN("PP8", "Theorem 2.2: f_1(h^pm) -> p pm tau"), conf=0.85, basis="named")
E("TP9", "PP10", conf=0.85); E("TP11", "PP10", conf=0.85)
E("TP13", "ClP12", conf=0.9, basis="named"); E("ClP11", "ClP12", conf=0.7)
E(EPOF["F28"], "PP11", conf=0.85, basis="named")
E("TP11", "RP4", conf=0.9, basis="named")
E("TP9", "ClP13", conf=0.75); E("TP11", "ClP13", conf=0.75)
E("ClP14", "DP22", conf=0.8, basis="named")
E("TP3", "RP7", conf=0.9, basis="named")
E("TP11", "ClP16", conf=0.8); E("TP14", "ClP16", conf=0.75)
E("ClP16", "ClP17", conf=0.85, basis="named"); E("TP14", "ClP17", conf=0.75); E("ClP5", "ClP17", conf=0.75)
E("ClP16", "RP8", conf=0.75)
E("ClP6", "PP15", conf=0.65)
E("CP2", "RP9", conf=0.75)
E("TP9", "RP3", conf=0.95, mention=True); E("TP11", "RP3", conf=0.95, mention=True)
E("TP9", "ClP9", conf=0.8); E("TP11", "ClP9", conf=0.8); E("RP3", "ClP9", conf=0.85, basis="named")
E("ClP9", "ClP10", conf=0.85, basis="named")
E("TP9", "ClP5", conf=0.8); E("TP11", "ClP5", conf=0.8); E("ClP8", "ClP5", conf=0.75)
E("ClP7", "ClP8", conf=0.85, basis="named")
E("TP14", "CnjP1", conf=0.75, mention=True); E("ClP17", "CnjP1", conf=0.75, mention=True)
E("CnjP1", "OpenP2", conf=0.9, basis="named", mention=True)
E("TP9", "OpenP1", conf=0.7, mention=True); E("TP11", "OpenP1", conf=0.7, mention=True)

# ------------------------------------------------------------ defined terms (pass 2)
TERM = {
    "DP1": ["DP3", "DP4", "TP1", "TP2", "PP2"],
    "DP2": ["DP3", "AssumP1"],
    "DP3": ["DP5", "DP6", "PP2", "PP3"],
    "AssumP1": ["DP6", "TP1", "TP2", "PP2", "PP3"],
    "DP4": ["DP7", "TP1", "TP2", "PP2", "PP3", "PP5", "PP8", "PP9", "PP11"],
    "DP5": ["TP1", "TP2", "PP2", "PP3"],
    "DP6": ["TP1", "TP2", "PP2", "PP3"],
    "DP7": ["TP1", "TP2", "PP2"],
    "DP8": ["ProbP1", "AP1", "ProbP2", "ClP2", "DP11", "TP3", "TP4", "PP5"],
    "AP1": ["ClP2", "PP5"],
    "ClP1": ["DP10", "DP11"],
    "DP9": ["ClP2", "DP10", "DP12", "RP1", "PP5"],
    "DP10": ["DP11", "DP15", "TP3"],
    "DP11": ["DP12", "DP15", "TP3", "TP4", "PP5"],
    "DP12": ["PP5"],
    "DP13": ["TP3", "TP4", "RP2", "TP9", "TP11", "TP13", "TP14", "ClP16", "TP15", "RP7"],
    "DP14": ["DP15", "RP2", "TP4", "PP5"],
    "DP15": ["TP4", "PP5", "ClP4"],
    "DP16": ["DP17", "ProbP3", "TP5", "AP2", "ClP7", "DP21"],
    "DP17": ["ProbP3", "TP5"],
    "DP18": ["TP5", "TP6", "AP2"],
    "AP2": ["TP7", "TP8", "ClP7", "RP5", "ClP5", "DP21", "OpenP3", "TP15"],
    "TP8": ["DP19", "DP20", "PP6", "TP9", "PP8", "PP9", "LP4", "PP14", "PP15"],
    "DP19": ["ClP8", "ClP9", "LP3", "PP6", "AssumP2", "ClP7", "RP3", "TP9", "PP8", "CP1", "PP10", "ClP11", "ClP12", "TP13", "PP11", "DP21", "RP9"],
    "AP3": ["DP20", "ClP7", "RP5", "ClP5", "CP1", "PP10", "OpenP1", "OpenP3", "TP16", "ClP16"],
    "DP20": ["ClP6", "AssumP2", "ClP7", "RP3", "TP11", "PP9", "PP10", "ClP11", "ClP12", "TP13", "PP11", "CP2", "PP15", "RP9", "DP21"],
    "TP9": ["DP23", "ClP15", "TP14", "PP12", "TP15", "PP16"],
    "TP11": ["DP23"],
    "DP22": ["RP6"],
    "DP21": ["ClP14", "DP22", "DP23", "RP10"],
    "DP23": ["ClP15", "TP14", "PP12", "TP15", "PP16", "RP9"],
}
for d, ts in TERM.items():
    for t in ts:
        E(d, t, conf=0.75, basis="term")

# ============================================================ metadata
NOTES = [
    {"category": "source_problem", "nodes": ["PP2", "PP5", "PP6", "PP8", "PP9", "PP10", "PP11", "PP12", "PP14", "PP15", "PP16"],
     "note": "Proofs are written as \\proof ... \\endproof (plain TeX), which latex_facts does not report as proof facts; each was emitted as a prose proof spanning \\proof to \\endproof with a named proves edge (confidence 0.9)."},
    {"category": "source_problem", "nodes": ["AP2"],
     "note": "pseudocode_steps nested Stage Two's items under Stage One's item 2 (two separate enumerate lists) and gave that line the whole Stage Two text; the build script cut it to its own line, re-parented Stage Two to the algorithm and dropped the three weight conditions (a)-(c), which are constraints rather than operations."},
    {"category": "type_uncertain", "nodes": ["TP12", "EP52", "EP54"],
     "note": "Euler's transformation (4.18) is named as a result, so it was retyped theorem/external; Ghosh's density (4.17) and the Gauss-theorem limit (4.20) are cited formulas not named as results and stay equations (Ghosh's with origin external)."},
    {"category": "type_uncertain", "nodes": ["RP3", "RP10"],
     "note": "RP3 announces the results of Theorems 4.1-4.2 (with \\eqref to theorem labels) and introduces the tilde-h notation; it was made a remark with mention edges, as the theorems themselves state the definitions. RP10 argues and concludes in one sentence (remark, not claim)."},
    {"category": "boundary_uncertain", "nodes": ["PP7", "ClP7", "PP13", "ClP17"],
     "note": "Two short prose arguments ('both procedures draw an infinite number of samples', 'the reason is that ... the ratio goes to 1') are single-sentence proof nodes of the claims next to them."},
    {"category": "not_extracted", "nodes": [],
     "note": "Not extracted: figures and tables (numerical results are represented by ClP4 and ClP13), the introduction's literature review and outline, the research directions in the Discussion other than the three numbered questions, and the trivial sentence that a_{delta^(t)} converges for finite groups."},
]
NOTES.insert(2, {"category": "source_problem", "nodes": ["PP15", "RP9", "AP3", "TP15"],
     "note": "Cross-references kept as written although they look wrong: the proof of Corollary 2 cites Lemma 3 (about h^(1)) for positivity of h^(2) (ClP6 states it; an inferred edge ClP6->PP15 was added); Remark 4 cites eq. (4.26) for h-tilde ~ h at fixed nu (that is Theorems 4.1-4.2); Rinott's 'Step 3'/'Step 2' do not match Algorithm 1's numbering. Theorem 4.5's source contains stray Hebrew vowel marks inside \\tilde{N}_{i,k}, copied verbatim."})
NOTES.insert(3, {"category": "rule_conflict", "nodes": ["DP14"],
     "note": "finalize warns that DP14 introduces symbols in separate sentences; the split it sees is the 'e.g.' abbreviation inside one sentence, so DP14 was kept whole (nodes never split a sentence)."})
COMMENT = ("Possible errors in the paper are listed in the agent report: the exponent of Ghosh's density (4.17)/(4.19) is inconsistent with the tail (4.21), "
           "the limit of h_k^(2)(nu) as nu -> infinity in Remark 4 should be sqrt(2) Phi^{-1}(p^{1/k}) rather than divided by sqrt(2), "
           "and part 2 of the proof of Theorem 4.5 treats only case (i) of the two announced cases.")
meta = {
    "title": "On The Asymptotic Efficiency of Selection Procedures for Independent Gaussian Populations",
    "arxiv_id": "1707.00314",
    "authors": ["Royi Jacobovic", "Or Zuk"],
    "year": 2017,
    "annotator": "agent-extraction",
    "model": "claude-opus-5-5",
    "effort": "default",
    "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
    "extraction_date": "2026-11-05",
    "rigor_nonformal_count": sum(1 for n in nodes if "rigor" in n),
    "paper_style": ["theorem_proof", "computational"],
    "extraction_notes": NOTES,
    "extraction_comment": COMMENT,
}
graph = {"metadata": meta, "nodes": nodes, "edges": edges}
report = finalize(graph, read_tex(TEX))
json.dump(report, open(SCR + "/report.json", "w"), indent=1, default=str)
print("errors", len(report["errors"]))
for x in report["errors"]:
    print("  E", x)
print("warnings", len(report["warnings"]))
for w in report["warnings"]:
    print("  W", w)
for k in ("matched_to_environment", "labels_filled", "proves_added", "ref_uses_added", "ref_backward", "orphans"):
    print(k, report.get(k))
if not report["errors"]:
    json.dump(graph, open(OUT if "--write" in sys.argv else SCR + "/draft.json", "w"), indent=1, ensure_ascii=False)
    print("written", len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
