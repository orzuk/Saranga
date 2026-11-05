#!/usr/bin/env python3
"""Build the v7 LLM extraction of arXiv 0909.3704, 'FDR control with adaptive procedures and FDR
monotonicity' (Zeisel, Zuk, Domany 2009/2011). Nodes, types, spans and edges were chosen by reading
the paper; this script only slices the chosen spans out of the prepared source, assembles the graph
and runs finalize().  Usage: python3 build.py [--write]"""
import json, re, sys, subprocess, os
REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize
from latex_facts import read_tex

SCR = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_orzuk/0909_3704"
CASE = REPO + "/corpus/orzuk/0909_3704"
TEX = CASE + "/arxiv_src/aoas399.tex"
OUT = CASE + "/0909_3704.json"
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


def span(a, b, lo=0):
    i, _ = find(a, lo)
    _, j = find(b, i)
    return norm(S[i:j])


def lit(t):
    find(t)
    return norm(t)


EQN = [0]


def eq(fid, name, **kw):
    EQN[0] += 1
    nid = f"EP{EQN[0]}"
    env(nid, fid, "equation", name, kw.pop("origin", "paper"), 1.0, **kw)
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


STD = "standard (uncited)"
BH = "Benjamini & Hochberg 1995"

# ============================================================ 1 Introduction
prose("DP1", "definition", "Discovery", "Such a finding is referred to as a", "\\textit{discovery}.",
      conf=0.85, origin="external", origin_citation=STD, definiendum="discovery",
      genus="finding", differentia=["the null hypothesis is rejected"])
prose("DP2", "definition", "Number of hypotheses m and of true nulls m_0",
      "Denote by $m$ the total number of hypotheses", "do not differentiate the two types).",
      conf=0.85, origin="external", origin_citation=STD, definiendum=["$m$", "$m_0$"])
prose("DP3", "definition", "Number of false nulls m_1", "For $m_1=m-m_0$ the null hypothesis is false",
      "different distributions).", conf=0.8, origin="external", origin_citation=STD, definiendum="$m_1$")
prose("DP4", "definition", "p-values p_i", "A~statistical test is performed independently for",
      "$i=1,2,\\ldots,m$.", conf=0.8, origin="external", origin_citation=STD, definiendum="$p_i$")
prose("DP5", "definition", "Number of rejections R", "On the basis of some thresholding operation",
      "is rejected for $R$ tests.", conf=0.8, origin="external", origin_citation=STD, definiendum="$R$")
prose("DP6", "definition", "False discovery (type I error)",
      "The decision to reject (or not) can be", "discovery'' (type I error).",
      conf=0.85, origin="external", origin_citation=STD, definiendum="false discovery",
      differentia=["the null hypothesis is rejected for one of the $m_0$ variables for which it is actually true"])
prose("DP7", "definition", "False Discovery Rate (FDR)", "Out of the $R$ rejected hypotheses, the fraction $V/R$",
      "is used for brevity.", conf=0.9, origin="external", origin_citation=BH,
      definiendum=["False Discovery Rate (FDR)", "$R^{+}$"],
      statement_short="FDR $=E(V/R^+)$, the expected fraction of false rejections among rejections, with $R^+=\\max(R,1)$.")
eq("F1", "FDR definition")
prose("AP1", "algorithm", "Benjamini-Hochberg (BH95) step-up procedure",
      "The original BH95 procedure to control the FDR is given as", "\\end{enumerate}",
      conf=0.85, origin="external", origin_citation=BH,
      input=[lit("the desired level, $0<q \\leq1$, of the FDR"), lit("the $p$-values $p_i$")],
      output=[lit("reject all $R$ hypotheses $(i)=1,2,\\ldots,R$")],
      statement_short="Sort the p-values and reject the R smallest, where R is the largest i with $p_{(i)}\\le iq/m$.")
eq("F2", "BH95 constants alpha_i = iq/m")
step("AP1", "Denote by $q$ the desired level", "\\end{equation}", "initialize",
     "Fix level q and constants alpha_i", "Fix the level $q$ and the constants $\\alpha_i=iq/m$.", 0.8, "algorithm_step")
step("AP1", "Sort the $p$-values $p_i$ and relabel", "smallest $p$-value.", "compute",
     "Sort the p-values", None, 0.8, "algorithm_step")
step("AP1", "Identify $R$ as", "$(i)=1,2,\\ldots,R$.", "select",
     "Select R and reject", "Take $R=\\max\\{i: p_{(i)}\\le\\alpha_i\\}$ and reject the $R$ smallest p-values.", 0.8, "algorithm_step")
eq("F3", "BH95 step-up rule R")
prose("DP8", "definition", "Step-up and step-down procedures", "It is referred to in BH95 as",
      "\\end{equation}", lo=F["F3"]["end"], conf=0.85, origin="external", origin_citation=BH,
      definiendum=["step-up", "step-down"],
      statement_short="Step-up takes the largest intersection of $p_{(i)}$ with $\\alpha_i$ as $R$; step-down takes $R=\\min\\{i:p_{(i)}>\\alpha_i\\}-1$.")
eq("F4", "Step-down rule", origin="external", origin_citation=BH)
prose("TP1", "theorem", "Benjamini-Hochberg FDR bound", "The bound", "Regression Dependency on each one from a Subset}).",
      lo=F["F4"]["end"], conf=0.85, origin="external", origin_citation="Benjamini & Hochberg 1995; Benjamini & Yekutieli 2001",
      assumptions=[lit("for independent tests"), lit("for a certain type of ``positive dependency'' called PRDS")],
      conclusions=[lit("\\mathit{FDR} = E \\biggl(\\frac{V}{R^+} \\biggr) \\leq\\frac{m_0}{m}q")],
      statement_short="The BH95 procedure has $FDR\\le (m_0/m)q$ for independent tests (BH95) and under PRDS dependence (Benjamini-Yekutieli).")
eq("F5", "BH95 bound FDR <= m_0 q/m", origin="external", origin_citation=BH)
prose("ClP1", "claim", "BH95 controls the FDR at level q", "The value of", "\\end{equation}", lo=F["F5"]["end"],
      conf=0.7, origin="external", origin_citation=BH,
      assumptions=[lit("since $m_0 \\leq m$")],
      conclusions=[lit("\\mathit{FDR} = E \\biggl(\\frac{V}{R^+} \\biggr) \\leq\\frac{m_0}{m}q \\leq q.")])
eq("F6", "BH95 bound FDR <= q", origin="external", origin_citation=BH)
prose("DP9", "definition", "Oracle constants alpha'_i and oracle rejection number R'", "Clearly, had we known $m_0$",
      "upper-bound on $m_0$.", conf=0.8, origin="external", origin_citation="Gavrilov, Benjamini & Sarkar 2009",
      definiendum=["$\\alpha'_i$", "$R^\\prime$"],
      statement_short="Knowing $m_0$, use $\\alpha'_i=iq/m_0$ and $R'=\\max\\{i:p_{(i)}\\le\\alpha'_i\\}\\ge R$, still with FDR $\\le q$.")
eq("F7", "Oracle constants alpha'_i = iq/m_0", origin="external", origin_citation="Gavrilov, Benjamini & Sarkar 2009")
eq("F8", "Oracle rejection number R'", origin="external", origin_citation="Gavrilov, Benjamini & Sarkar 2009")
prose("DP10", "definition", "Oracle procedure (ORC)", "This procedure, based on knowledge of $m_0$", "see \\citet{gavrilov2009}.",
      conf=0.85, origin="external", origin_citation="Gavrilov, Benjamini & Sarkar 2009", definiendum="oracle (ORC)")
prose("DP11", "definition", "Adaptive (improved) FDR procedures", "Subsequently, various improved (also called",
      "more accurate handle on the FDR.", conf=0.8, origin="external", origin_citation=STD,
      definiendum="adaptive procedures", genus="procedures", differentia=["based on the idea of estimating the unknown $m_0$"])
prose("DP12", "definition", "Local FDR estimation procedures and the estimator condition (9)",
      "Procedures for local FDR \\textit{estimation}:", "\\end{equation}", conf=0.75, origin="external",
      origin_citation="Yekutieli & Benjamini 1999; Storey 2002; Pounds & Cheng 2006",
      definiendum="Procedures for local FDR estimation",
      statement_short="Local FDR estimation uses an estimator $\\hat m_0$ of $m_0$ with $m_0\\le E(\\hat m_0)\\le m$.")
eq("F9", "Estimator condition m_0 <= E(hat m_0) <= m", origin="external", origin_citation="Pounds & Cheng 2006")
prose("DP13", "definition", "Local FDR (lFDR) estimate t_(i)", "In procedures of this type one can write the local FDR",
      "by $i/m$].", conf=0.8, origin="external", origin_citation="Pounds & Cheng 2006",
      definiendum=["local FDR (lFDR) estimate", "$t_{(i)}$", "$\\hat{v}(\\alpha)$", "$\\hat{F}(\\alpha)$"],
      statement_short="The lFDR estimate is $t_{(i)}=\\hat v(p_{(i)})/\\hat F(p_{(i)})$, estimated type I errors over estimated $\\Pr(p\\le\\alpha)$.")
eq("F10", "lFDR estimate", origin="external", origin_citation="Pounds & Cheng 2006")
prose("ClP2", "claim", "An estimator satisfying (9) improves the local-FDR estimator", "Since for $\\hat{v}(\\alpha)$ most methods use",
      "\\leq\\alpha. \\end{equation}", lo=F["F10"]["end"] + 200, conf=0.7,
      assumptions=[lit("for $\\hat{v}(\\alpha)$ most methods use"), lit("any estimator that satisfies equation (\\ref{eq:mhat_condition})")],
      conclusions=[lit("\\alpha\\frac{m_0}{m}\\leq E(\\hat{v}(\\alpha))=\\alpha\\frac{E(\\hat{m}_0 )}{m}\\leq\\alpha.")],
      statement_short="With $\\hat v(\\alpha)=\\alpha\\hat m_0/m$ and (9), $\\alpha m_0/m\\le E\\hat v(\\alpha)\\le\\alpha$.")
eq("F11", "hat v(alpha) = alpha hat m_0/m")
eq("F12", "Bounds on E(hat v(alpha))")
prose("ClP3", "claim", "Improved bound on the local-FDR estimator", "When using $\\hat{F}(p_{(i)}) = i/m$",
      "\\end{equation}", conf=0.7, assumptions=[lit("When using $\\hat{F}(p_{(i)}) = i/m$")],
      conclusions=[span("\\frac{p_{(i)}}{i} m_0 \\leq E", "\\frac{p_{(i)}}{i} m.", lo=F["F13"]["start"])],
      statement_short="With $\\hat F(p_{(i)})=i/m$: $\\frac{p_{(i)}}{i}m_0\\le E\\,t_{(i)}\\le\\frac{p_{(i)}}{i}m$.")
eq("F13", "Bounds on E t_(i)")
prose("DP14", "definition", "FDR control procedures with gamma_i = iq/hat m_0", "Procedures for FDR \\textit{control}:",
      "bound by the desired value $q$.", conf=0.75, origin="external", origin_citation=STD,
      definiendum=["Procedures for FDR control", "$\\gamma_i$"],
      statement_short="FDR control procedures fix level $q$ and use $\\gamma_i=iq/\\hat m_0$ in place of $\\alpha_i$.")
prose("TP2", "theorem", "Procedures with rigorously established FDR control (BH95, BKY, STS)",
      "However, as far as we know, only for a few such procedures", "(referred to as STS).", conf=0.65,
      origin="external", origin_citation="Benjamini & Hochberg 1995; Benjamini, Krieger & Yekutieli 2006; Storey 2002",
      assumptions=[], conclusions=[span("only for a few such procedures has control", "(referred to as STS)")],
      statement_short="FDR control is proven for BH95, the two-/multiple-stage adaptive BH procedures (BKY) and Storey's procedure (STS); names BKY and STS.")
prose("DP15", "definition", "Improved BH (IBH) procedures", "We analyze simulated and real", "``Improved BH'' (IBH).",
      conf=0.85, definiendum="Improved BH (IBH)", genus="procedures",
      differentia=["almost always reject more hypotheses than BH95, while maintaining control even under dependence"])

# ============================================================ 2 Preliminaries
prose("DP16", "definition", "Notation p_{i..j}", "Throughout this section and", "p_i,\\ldots,p_j$.",
      conf=0.85, definiendum="$p_{i..j}$")
prose("DP17", "definition", "Vector of p-values", "We also denote $\\vec{p}= (p_1,\\ldots,p_m)$", "of all $p$-values.",
      conf=0.85, definiendum="$\\vec{p}$")
env("DP18", "F14", "definition", "Monotonic estimator for m_0",
    definiendum=["estimator for $m_0$", "monotonic estimator"], genus="family of functions",
    statement_short="An $m_0$-estimator is monotonic if it is nondecreasing in each p-value and does not increase when a p-value is removed.")
env("AP2", "F15", "algorithm", "Modified step-up BH procedure with estimator hat m_0", conf=0.9,
    input=[lit("$\\vec{p}= (p_1,\\ldots,p_m)$ be the corresponding $p$-values"), lit("estimator $\\hat{m}_0$")],
    output=[lit("reject the hypotheses $(1),(2),\\ldots,(R)$")],
    statement_short="BH95 with $m$ replaced by an estimate $\\hat m_0(\\vec p)$: constants $\\gamma_i=iq/\\hat m_0$, step-up (or step-down) rule.")
step("AP2", "Compute $\\hat{m}_0\\equiv", "(\\vec{p})$.", "compute", "Estimate m_0", None, 0.8, "algorithm_step")
step("AP2", "For each $i$ define", "\\end{equation}", "compute", "Set gamma_i = iq/hat m_0", None, 0.8, "algorithm_step")
eq("F16", "Modified constants gamma_i")
step("AP2", "Order the $p$-values in an increasing order:", "p_{(m)}$.", "compute", "Sort the p-values", None, 0.8, "algorithm_step")
step("AP2", "Let $R = \\max\\{i\\dvtx p_{(i)} \\leq\\gamma_i\\}$", "reject any hypothesis).", "select",
     "Select R and reject", "Take $R=\\max\\{i:p_{(i)}\\le\\gamma_i\\}$ and reject the $R$ smallest.", 0.8, "algorithm_step")
env("TP3", "F17", "theorem", "FDR bound for adaptive BH procedures with a monotonic m_0 estimator", main=True,
    assumptions=[lit("Let $\\hat{m}_0\\equiv\\hat{m}_0(\\vec{p})$ be a monotonic estimator for $m_0$"),
                 lit("Consi\\-der the modified step-up BH procedure defined above"),
                 span("Let $\\hat{m}_0^{(\\not1)}(\\vec{p})", "the first (null) $p$-value $p_1$", lo=F["F17"]["start"]),
                 lit("Assume that the null $p$-values are i.i.d. $U[0,1]$")],
    conclusions=[span("\\mathit{FDR} = E \\biggl[\\frac{V}{R^{+}} \\biggr] \\leq m_0 q", "{\\hat{m}_0^{(\\not1)}} \\biggr]", lo=F["F17"]["start"])],
    statement_short="For a monotonic estimator and independent uniform nulls, the modified step-up BH procedure has $FDR\\le m_0 q\\,E[1/\\hat m_0^{(\\not 1)}]$.")
eq("F18", "FDR <= m_0 q E[1/hat m_0^(not 1)]")
prose("RP1", "remark", "The leave-one-out estimator is only auxiliary", "Here $p_1$ is a representative",
      "(as well as all other $p$-values).", lo=F["F17"]["end"], conf=0.75,
      statement_short="$\\hat m_0^{(\\not 1)}$ is not implementable but only serves the proof; the theorem applies to the practical procedure using all p-values.")
prose("RP2", "remark", "Theorem 2.3 reduces FDR control to bounding the reciprocal mean", "The advantage of Theorem~",
      "estimator for $m_0$.", lo=F["F17"]["end"], conf=0.75)

# ============================================================ 3 The proposed procedures
prose("ClP4", "claim", "Sufficient condition E[1/hat m_0^(not 1)] <= 1/m_0 for FDR control at q",
      "According to Theorem", "\\end{equation}", lo=21708, conf=0.7,
      assumptions=[lit("any estimator that satisfies our monotonicity assumption")],
      conclusions=[lit("E \\biggl[\\frac{1}{\\hat{m}_0^{(\\not1)}} \\biggr]\\leq\\frac{1}{m_0}.")],
      statement_short="By Theorem 2.3, a monotonic estimator gives FDR $\\le q$ once $E[1/\\hat m_0^{(\\not 1)}]\\le 1/m_0$.")
eq("F19", "Reciprocal-mean condition")
prose("DP19", "definition", "Sum estimator hat m_0' = 2 sum p_j", "Our first estimator is based on", "\\end{equation}",
      lo=21708, conf=0.85, origin="external", origin_citation="Pounds & Cheng 2006", definiendum="$\\hat{m}_0^\\prime$")
eq("F20", "hat m_0' = 2 sum p_j", origin="external", origin_citation="Pounds & Cheng 2006")
prose("DP20", "definition", "Log estimator tilde m_0' = -sum log(1-p_i)", "The second estimator is based on", "\\end{equation}",
      conf=0.85, definiendum="$\\tilde{m}_0^\\prime$")
eq("F21", "tilde m_0' = -sum log(1-p_i)")
prose("ClP5", "claim", "Both estimators are monotonic", "Both $\\hat{m}_0^\\prime,\\tilde{m}_0^\\prime$ are monotonic",
      "Definition \\ref{def:monotonit}.", conf=0.75, rigor="semi_formal",
      assumptions=[], conclusions=[lit("Both $\\hat{m}_0^\\prime,\\tilde{m}_0^\\prime$ are monotonic estimators")])
prose("ClP6", "claim", "Both IBH procedures control the FDR", "Both procedures control the FDR---for the list",
      "\\mbox{$\\mathit{FDR} \\leq q$}.", conf=0.7, main=True,
      assumptions=[], conclusions=[lit("for the list of $R'$ discoveries we have \\mbox{$\\mathit{FDR} \\leq q$}")])
prose("ClP7", "claim", "IBH procedures nearly always reject more than BH95", "In nearly all cases of interest the number",
      "very close).", conf=0.7, rigor="heuristic",
      assumptions=[lit("In nearly all cases of interest")],
      conclusions=[lit("the number of discoveries obtained by our procedures exceeds the number obtained (for the same value of $q$) by the BH95 procedure, that is, $R' \\geq R$")])
prose("DP21", "definition", "Conservative estimator", "A reasonable requirement from an estimator", "in expectation).",
      conf=0.8, origin="external", origin_citation=STD, definiendum="conservative",
      genus="estimator for $m_0$", differentia=["larger than $m_0$ in expectation"])
prose("DP22", "definition", "Asymptotically unbiased estimator", "Finally, a desirable property is being",
      "value~$m_0$.", conf=0.8, origin="external", origin_citation=STD, definiendum="asymptotically unbiased",
      differentia=["when the sample size of the individual tests grows to infinity, we would want the estimator to converge, on expectation, to the true value~$m_0$"])
prose("TP4", "theorem", "Pounds-Cheng: hat m_0' is conservative and asymptotically unbiased", "These properties were dealt with in",
      "indeed satisfy them.", conf=0.7, origin="external", origin_citation="Pounds & Cheng 2006",
      assumptions=[], conclusions=[lit("$\\hat{m}_0^\\prime$ indeed satisfy them")])
env("ClP8", "F22", "claim", "The two estimators are conservative and asymptotically unbiased",
    assumptions=[span("Assume that the sample size of all tests", "$i=m_0+1,\\ldots,m$", lo=F["F22"]["start"])],
    conclusions=[lit("Both estimators are conservative"), lit("E [\\hat{m}_0^\\prime]\\geq m,\\qquad E[\\tilde{m}_0^\\prime] \\geq m_0."),
                 lit("both estimators converge in expectation to $m_0$")],
    parts=[{"assumptions": [], "conclusions": [lit("Both estimators are conservative"),
                                                 lit("E [\\hat{m}_0^\\prime]\\geq m,\\qquad E[\\tilde{m}_0^\\prime] \\geq m_0.")]},
           {"assumptions": [span("Assume that the sample size of all tests", "$i=m_0+1,\\ldots,m$", lo=F["F22"]["start"])],
            "conclusions": [lit("both estimators converge in expectation to $m_0$")]}],
    also_stated_at=[span("Both estimators are conservative, that is, their expectation", "to the true value of $m_0$.")],
    statement_short="(a) $E\\hat m_0'$ and $E\\tilde m_0'$ are at least $m_0$; (b) as alternative p-values tend to 0, both converge in expectation to $m_0$.")
eq("F23", "Conservativeness of both estimators")
eq("F24", "Convergence in expectation to m_0")
env("PP1", "F25", "proof", "Proof of Claim 3.1", proves="ClP8", proof_strategy=["direct", "algebraic_manipulation"],
    statement_short="Linearity of expectation: null p-values contribute exactly $m_0$, alternative terms are nonnegative and vanish in the limit.")
a = step("PP1", "(a)", "\\end{eqnarray}", "algebraic_manipulation", "Part (a): expand the expectations",
         "Split each expectation into null and alternative sums; nulls give $m_0$.", 0.95)
eq("F26", "Expectation of hat m_0'")
eq("F34", "Expectation of tilde m_0'")
b = step("PP1", "(b) From the two equations above", "converges to $m_0$.", "conclude", "Part (b): limit of alternative terms",
         "Alternative terms vanish, so both expectations tend to $m_0$.", 0.95)
E(a, b, conf=0.9, basis="named")
prose("RP3", "remark", "Why small corrections to the estimators are needed", "In order to show control of the FDR using Theorem",
      "as the number of hypotheses goes to infinity.", lo=F["F25"]["end"], conf=0.75,
      statement_short="Corrections are needed because the bound uses the leave-one-out estimator and, by Jensen, the reciprocal of an unbiased estimator is biased.")

# 3.1 IBHsum
prose("PP2", "proof", "Argument that E[hat m_0'] >= m_0", "Since for the", "$E[\\hat{m}_0^\\prime]\\geq m_0$.",
      lo=27183, conf=0.65, proof_strategy=["direct"],
      statement_short="Null p-values are uniform with mean 1/2, so $E\\hat m_0'\\ge m_0$.")
prose("DP23", "definition", "Distribution f_i^false of alternative p-values", "We denote the distribution of $p_i^{\\mathrm{false}}$",
      "p_i^{\\mathrm{false}} \\sim f_i^{\\mathrm{false}}$.", conf=0.8, definiendum="$f_i^{\\mathrm{false}}$")
prose("ClP9", "claim", "E[hat m_0'] <= m when alternatives are stochastically smaller than uniform (with definition of stochastic order)",
      "If all the $f_i$'s are", "\\citet{Aven01}].", lo=27183, conf=0.7,
      assumptions=[span("If all the $f_i$'s are", "($f_i^{\\mathrm{false}} \\leq_{\\mathrm{st}} U[0,1]$)", lo=27183)],
      conclusions=[lit("we have $E[p_i^{\\mathrm{false}}]\\leq\\frac {1}{2}$"), lit("immediately implies $E[\\hat{m}_0^\\prime]\\leq m$")],
      statement_short="If alternative p-values are stochastically smaller than $U[0,1]$ ($F\\ge G$ pointwise), then $E p_i^{false}\\le 1/2$ and $E\\hat m_0'\\le m$.")
prose("DP24", "definition", "IBHsum estimator hat m_0 = C(m) min[m, max(s(m), hat m_0')]", "We introduce the following modified estimator:",
      "Supplement~B].", conf=0.85, definiendum=["$\\hat{m}_0$", "$C(m),s(m)$"],
      statement_short="IBHsum estimator: clip $\\hat m_0'$ to $[s(m),m]$ and multiply by $C(m)$; $C,s$ are chosen so that the reciprocal-mean condition holds.")
eq("F27", "IBHsum estimator")
prose("ClP10", "claim", "IBHsum correction factors vanish asymptotically", "The correction factors were computed",
      "reduces to $\\hat{m}_0^\\prime$.", lo=F["F27"]["end"], conf=0.7, rigor="numerical",
      assumptions=[lit("When $m\\rightarrow\\infty$")],
      conclusions=[lit("$C \\rightarrow1$ and $s/m \\rightarrow0$"), lit("the estimator $\\hat{m}_0$ reduces to $\\hat{m}_0^\\prime$")])

# 3.2 IBHlog
prose("PP3", "proof", "Argument that E[tilde m_0'] >= m_0", "Again, since for", "$E[\\tilde{m}_0^\\prime]\\geq m_0$.",
      lo=29484, conf=0.65, proof_strategy=["direct"],
      statement_short="For uniform null p-values $E[-\\log(1-p)]=1$, so $E\\tilde m_0'\\ge m_0$.")
prose("ClP11", "claim", "E[tilde m_0'] <= m when alternatives are stochastically smaller than uniform",
      "Furthermore, if all the", "$E[\\tilde{m}_0^\\prime]\\leq m$.", lo=29484, conf=0.7,
      assumptions=[span("if all the alternative $p$-values", "\\leq_{\\mathrm{st}} U[0,1])$", lo=29484)],
      conclusions=[lit("$E[-\\log(1-p_i^{\\mathrm{false}})]\\leq1$"), lit("$E[\\tilde{m}_0^\\prime]\\leq m$")])
prose("RP4", "remark", "The log estimator is typically closer to m_0", "The advantage of using the second estimator",
      "typically closer to the true $m_0$.", conf=0.7, rigor="heuristic",
      statement_short="Since $-\\log(1-p)<2p$ for $p<1/2$ and alternatives are left-skewed, typically $\\tilde m_0'\\le\\hat m_0'$, closer to $m_0$.")
prose("RP5", "remark", "The log estimator typically has larger variance", "A possible drawback is that the variance",
      "in the estimation of $m_0$.", conf=0.7, rigor="heuristic")
env("ClP12", "F28", "claim", "IBHlog: the corrected log estimator controls the FDR", main=True,
    assumptions=[lit("Assume that the null $p$-values are i.i.d. $U[0,1]$")],
    conclusions=[lit("the modified $BH$ procedure with estimator $\\tilde{m}_0$ and parameter $q$ controls the FDR at level $\\leq q$")],
    statement_short="With $\\tilde m_0=2-\\sum\\log(1-p_i)$ and i.i.d. uniform nulls, the modified BH procedure controls the FDR at level $q$.")
eq("F29", "Corrected log estimator tilde m_0")
prose("PP4", "proof", "Proof outline of Claim 3.2", "The proof is achieved by bounding", "Supplement C for full details.",
      conf=0.75, proof_strategy=["direct"],
      statement_short="Bound $E[1/\\tilde m_0^{(\\not 1)}]\\le 1/m_0$ and apply Theorem 2.3; details in Supplement C.")

# ============================================================ 4 Is the FDR monotonic?
prose("OpenP1", "open_problem", "FDR monotonicity question", "Our formulation of the question in the multiple-hypothesis",
      "\\mathit{FDR}^{(2)}$?", conf=0.75,
      statement_short="If procedure $B^{(2)}$ always rejects at least as many hypotheses as $B^{(1)}$, is $FDR^{(1)}\\le FDR^{(2)}$?")
env("TP5", "F30", "theorem", "FDR monotonicity theorem", main=True,
    assumptions=[lit("Let $\\vec{p}= (p_{1,\\ldots,m})$ be a set of independent $p$-values"),
                 lit("Assume that $f$, the marginal probability density function of the alternatives, is monotonically nonincreasing and differentiable"),
                 lit("Let $B^{(i)}$ be two threshold FDR procedures rejecting $R^{(i)}(\\vec{p})$ hypotheses and each having $\\mathit{FDR}^{(i)}$, $i=1,2$"),
                 lit("Assume that for any $q$, $R^{(1)}(\\vec{p}) \\leq R^{(2)}(\\vec{p}), \\forall\\vec{p}$")],
    conclusions=[lit("$\\mathit{FDR}^{(1)} \\leq \\mathit{FDR}^{(2)}$")],
    statement_short="For independent p-values with nonincreasing differentiable alternative density, a procedure that always rejects fewer has no larger FDR.")
prose("PP5", "proof", "Derivation of the step-down corollary", "A particular application of the above theorem",
      "we immediately get the following:", conf=0.8, proof_strategy=["direct"],
      statement_short="Apply the monotonicity theorem: step-down rejects no more than step-up, so its FDR is no larger.")
env("CP1", "F31", "corollary", "FDR bound of Theorem 2.3 holds for the step-down procedure",
    assumptions=[lit("provided that the alternative $f$ is monotonically decreasing")],
    conclusions=[lit("The statement of Theorem \\ref{thm:m0_control} holds also for the step-down procedure")])
prose("ClP13", "claim", "FDR monotonicity fails under stochastic ordering alone", "We have found that, perhaps surprisingly",
      "themselves are monotonic.", conf=0.75,
      assumptions=[lit("when $f \\leq_{\\mathrm{st}} U[0,1]$"), lit("when the FDR procedures themselves are monotonic")],
      conclusions=[lit("monotonicity of the FDR does not hold under such relaxed conditions")],
      statement_short="With only $f\\le_{st}U[0,1]$ (independent statistics, monotone procedures) FDR monotonicity can fail.")
env("ExP1", "F32", "example", "Counterexample to FDR monotonicity (m=3, m_0=1)",
    statement_short="Two alternatives with mass $1-\\varepsilon$ at $\\varepsilon$: rejecting one p-value gives FDR $\\approx\\varepsilon$, rejecting two gives $\\approx\\varepsilon/2$.")
eq("F33", "FDR of rejecting the lowest p-value")
eq("F35", "FDR of rejecting the two lowest p-values")

# ============================================================ 5 Synthetic data
prose("DP25", "definition", "Simulation model: null and alternative Gaussians", "The simulations produce",
      "centered on $\\mu_1>0$.", lo=36754, conf=0.8, definiendum=["$Z_i$", "$P_0$", "$P_1$", "$\\mu_1$"],
      statement_short="Simulated statistics: $m_0$ from $P_0=N(0,1)$, $m-m_0$ from $P_1=N(\\mu_1,1)$ with $\\mu_1>0$.")
prose("DP26", "definition", "Correlation rho", "All variables (both null and", "full (deterministic) dependency.",
      lo=36754, conf=0.8, definiendum="$\\rho$")
prose("DP27", "definition", "Two-tailed p-value", "For each~$Z_i$ the corresponding", "cumulative distribution function.",
      lo=36754, conf=0.8, origin="external", origin_citation=STD, definiendum=["two-tailed $p$-value", "$\\Phi$"])
prose("ClP14", "claim", "Distribution of simulated p-values", "The obtained $p_i$'s have", "(the alternative hypothesis).",
      lo=36754, conf=0.7, origin="external", origin_citation=STD,
      assumptions=[], conclusions=[lit("have a uniform $U[0,1]$ distribution for $i=1,\\ldots,m_0$"),
                                   lit("a distribution stochastically smaller than uniform for $i=m_0+1,\\ldots,m$")])
prose("DP28", "definition", "Comparison procedures BH95, BKY and STS", "Specifically, we compare our procedure to the",
      "STS procedure with $\\lambda=0.5$).", conf=0.8, origin="external",
      origin_citation="Benjamini, Krieger & Yekutieli 2006; Storey 2002",
      definiendum=["BKY procedure", "$\\hat{m}_0^{\\mathrm{BKY}}$", "STS procedure", "$\\hat{m}_0^{\\mathrm{STS}}$", "$r(\\lambda)$"],
      statement_short="BKY: local estimator $m+1-i(1-q)$ used step-down; STS: $(m+1-r(\\lambda))/(1-\\lambda)$ used step-up, $\\lambda=0.5$.")
prose("ClP15", "claim", "Step-up and step-down IBHsum coincide for strong signal (simulation)",
      "Figure \\ref{fig:m_500_q5_q20_rho_0and0p8_EVR_maps}a and c are for the", "or when $m_0/m$ is small.", lo=40000, conf=0.65, rigor="numerical",
      assumptions=[lit("for the independent case")], conclusions=[lit("the two become identical when the signal ($\\mu_1$) is strong or when $m_0/m$ is small")])
prose("ClP16", "claim", "IBHsum violates the FDR level under strong positive dependence (simulation)",
      "Figure \\ref{fig:m_500_q5_q20_rho_0and0p8_EVR_maps}b and d are for the", "will be discussed later.", lo=40000, conf=0.65, rigor="numerical",
      assumptions=[lit("positively dependent case ($\\rho=0.8$)")],
      conclusions=[lit("violation of the FDR level $q$ for large signals ($\\mu_1$)")])
# 5.1
prose("ClP17", "claim", "All methods satisfy the bound under independence (simulation)", "These means provide",
      "BH95 significantly lower.", conf=0.7, rigor="numerical",
      assumptions=[lit("for $\\rho = 0$")], conclusions=[lit("all methods satisfy the bound $E(V/R^+) \\leq q$")])
prose("ClP18", "claim", "Oracle slightly violates the bound for two-tailed tests under dependence (simulation)",
      "Furthermore, the proof of \\citet{BY2001}", "reported in \\citet{Reiner2007}.", conf=0.7, rigor="numerical",
      assumptions=[], conclusions=[lit("the proof of \\citet{BY2001} for the BH95 procedure does not hold for two-tailed tests"),
                                   lit("the FDR obtained by the oracle procedure (slightly) violates the bound $q=0.05$ for $m_0/m \\leq0.3$")])
prose("ClP19", "claim", "Under rho=0.8 STS overshoots the bound by more than twice; BH95, BKY, IBHsum stay near it (simulation)",
      "As seen in Figure", "but by much less than STS.", lo=45000, conf=0.7, rigor="numerical",
      assumptions=[lit("for $\\rho=0.8$")],
      conclusions=[lit("the STS method produces a measured FDR that overshoots the value $q=0.05$ of the bound by more than twice")])
prose("DP29", "definition", "Power (True Discovery Rate)", "We conclude these comparisons between the different procedures by",
      "``True Discovery Rate.''", conf=0.8, origin="external", origin_citation=STD,
      definiendum=["power", "True Discovery Rate"], genus="fraction of correctly rejected hypotheses")
prose("DP30", "definition", "False Non-Discovery Rate", "This measure of power is one minus", "[\\citet{Genovese2002}].",
      conf=0.75, origin="external", origin_citation="Genovese & Wasserman 2002", definiendum="False Non-Discovery Rate")
prose("ClP20", "claim", "Power comparison (simulation)", "For the independent case $\\rho= 0$ the power",
      "with a large gap to BH95.", conf=0.7, rigor="numerical",
      assumptions=[], conclusions=[lit("much better than that of BH95")])
prose("ClP21", "claim", "No simple monotone relation between FDR and power (simulation)", "Interestingly, there is no simple monotonicity",
      "Discovery Rate $E(S/m_1)$.", conf=0.65, rigor="numerical",
      assumptions=[], conclusions=[lit("there is no simple monotonicity relationship between the values of the FDR, $E(V/R^+)$, and the True Discovery Rate $E(S/m_1)$")])
prose("ClP22", "claim", "Standard deviation of V/R^+ (simulation)", "As can be seen when the $p$-values are independent",
      "is greater than 1.", conf=0.65, rigor="numerical",
      assumptions=[], conclusions=[lit("the st.d. is very similar for all the procedures, but increases steeply as $m_0/m\\rightarrow1$")])
prose("ClP23", "claim", "Summary of the simulation comparison", "We thus conclude that for", "violate it only slightly.",
      conf=0.7, rigor="numerical",
      assumptions=[], conclusions=[lit("For dependent variables STS violates the bound on $E(V/R^+)$ much more than the IBHlog and the IBHsum which violate it only slightly")])
# 5.2
prose("ClP24", "claim", "Probability that a single realization satisfies the level (simulation)", "As seen in Figure",
      "the most permissive procedure.", lo=49730, conf=0.65, rigor="numerical",
      assumptions=[], conclusions=[lit("the results of IBH are slightly more conservative than the oracle in the case of independence")])
prose("ClP25", "claim", "Positive dependence lowers the probability of violating the bound (simulation)", "It is very interesting to see that in the case",
      "is larger.", conf=0.65, rigor="numerical",
      assumptions=[lit("in the case of positive dependent statistics")],
      conclusions=[lit("the probability to violate the bound is smaller, although $E[V/R^+]$ is larger")])
prose("ClP26", "claim", "CDF of V/R^+ for the procedures (simulation)", "We would like to emphasize two points:",
      "is almost irrelevant.", lo=49730, conf=0.65, rigor="numerical",
      assumptions=[], conclusions=[lit("The CDFs of our improved procedures have very similar behavior to the other improved procedures")])

# ============================================================ 6 Gene expression data
prose("ClP27", "claim", "Leukemia data: IBHsum gives 23% more discoveries than BH95", "For the first data set the BH95 procedure",
      "that is, 23\\% more.", conf=0.7, rigor="numerical",
      assumptions=[lit("at $q=0.1$")], conclusions=[lit("that is, 23\\% more")])
prose("ClP28", "claim", "Breast cancer data: IBHsum gives 24% more discoveries than BH95", "The BH95 procedure yields for the second data set",
      "that is, 24\\% more.", conf=0.7, rigor="numerical",
      assumptions=[lit("(at $q=0.1$)")], conclusions=[lit("that is, 24\\% more")])
prose("ClP29", "claim", "Two-tailed data sets: STS and IBH improve more than BKY", "Inspection of Table",
      "followed by IBHsum.", conf=0.7, rigor="numerical",
      assumptions=[lit("for types (a), (b)---of two-tailed tests")],
      conclusions=[lit("STS and both IBH procedures give significantly higher improvement over BH95 than the BKY procedure")])
prose("ClP30", "claim", "One-tailed, many discoveries: BKY best and IBHlog fails", "For the one-tailed test with large numbers",
      "over-estimation of $m_0$.", conf=0.7, rigor="numerical",
      assumptions=[lit("For the one-tailed test with large numbers of discoveries [type (c)]")],
      conclusions=[lit("the mean improvement of BKY is the highest"), lit("IBHlog fails dramatically in this case")])
prose("ClP31", "claim", "One-tailed, few discoveries: IBHsum slightly better than STS", "For type (d), one-tailed tests",
      "improvement than BKY.", conf=0.7, rigor="numerical",
      assumptions=[lit("For type (d), one-tailed tests with a small number of discoveries")],
      conclusions=[lit("IBHsum is slightly better than STS and both yield a significantly higher improvement than BKY")])
prose("ClP32", "claim", "IBH improves on BH95 on all real-data comparison types", "In summary, our IBH procedures",
      "while IBH remains reliable.", conf=0.7, rigor="numerical",
      assumptions=[], conclusions=[lit("our IBH procedures constitute in all cases a significant improvement over the original BH95")])

# ============================================================ 7 Discussion
prose("RP6", "remark", "Recommendation: IBHlog for two-tailed, IBHsum for one-tailed tests", "We recommend using",
      "while controlling FDR levels.", conf=0.75)

# ============================================================ edges
N = lambda s, t, c=0.9, **kw: E(s, t, conf=c, basis="named", **kw)
I = lambda s, t, c=0.75, **kw: E(s, t, conf=c, basis="inferred", **kw)
# section 1
N("TP1", "ClP1", 0.85)                 # "this procedure leads to the bound"
N("AP1", "ClP1", 0.85)
N("AP1", "TP1", 0.9)                   # "was proved by BH95"
N("AP1", "DP8", 0.9)                   # "This procedure ... It is referred to in BH95 as step-up"
N("DP9", "DP10", 0.9)                  # "This procedure, based on knowledge of m_0"
N("AP1", "DP9", 0.85)                  # "than the number R given by the original BH95 procedure"
N("DP12", "DP13", 0.85)                # "In procedures of this type"
N("ClP2", "ClP3", 0.75)
N("AP1", "TP2", 0.85)                  # "the original BH95 procedure"
N("DP11", "TP2", 0.75)
N("TP2", "DP28", 0.8)                  # BKY/STS named in the intro, specified in Sec. 5
N("AP1", "DP15", 0.8)                  # Improved BH
# section 2-3
N("DP18", "TP3", 0.9)                  # "be a monotonic estimator"
N("AP2", "TP3", 0.9)                   # "the modified step-up BH procedure defined above"
N("AP1", "AP2", 0.9)                   # "similar to the original BH95 procedure"
I("DP14", "AP2", 0.7)
E("TP3", "RP1", conf=0.75, basis="inferred", mention=True)
E("TP3", "RP2", conf=0.95, basis=None, mention=True)
N("DP18", "ClP4", 0.85)                # "satisfies our monotonicity assumption"
N("TP4", "ClP8", 0.6)                  # Pounds-Cheng showed it for hat m_0'
N("DP21", "ClP8", 0.85)                # "conservative"
N("DP22", "ClP8", 0.7)
N("DP21", "TP4", 0.8); N("DP22", "TP4", 0.8)
N("DP19", "TP4", 0.8, ); 
E("PP2", "ClP8", "proves", 0.65, "inferred", alternative=True)
E("PP3", "ClP8", "proves", 0.65, "inferred", alternative=True)
N("ClP8", "RP3", 0.6)
N("ClP4", "RP3", 0.7)
N("DP23", "ClP9", 0.85)
N("ClP9", "ClP11", 0.8)                # "stochastically smaller" (definition inside ClP9)
N("ClP9", "ClP13", 0.8); N("ClP9", "ExP1", 0.8); N("ClP9", "ClP14", 0.75)
N("ClP9", "RP4", 0.75)
I("DP24", "ClP10", 0.85)
E("PP4", "ClP12", "proves", 0.8, "named")   # "The proof is achieved by ..."
I("ClP4", "PP4", 0.75)
N("AP2", "ClP12", 0.9)                 # "the modified BH procedure with estimator"
N("DP20", "ClP12", 0.85)
N("ClP12", "ClP6", 0.8)                # IBHlog control
I("DP24", "ClP6", 0.75)                # IBHsum control rests on the numerically chosen C(m), s(m)
I("ClP4", "ClP6", 0.75)
I("ClP5", "ClP6", 0.6)
I("DP24", "ClP7", 0.7)
N("DP9", "ClP7", 0.7)                  # R'
# section 4
N("DP7", "OpenP1", 0.8, )
E("OpenP1", "TP5", "resolves", 0.8, "inferred")
E("OpenP1", "ExP1", "illustrates", 0.75, "inferred")
N("TP5", "PP5", 0.9)                   # "A particular application of the above theorem"
E("PP5", "CP1", "proves", 0.8, "named")
N("DP8", "CP1", 0.8)                   # step-down
N("AP2", "CP1", 0.8)                   # modified step-down BH procedure
N("DP8", "PP5", 0.75)
E("TP5", "ClP13", conf=0.8, basis="named", mention=True)   # "The above conditions for monotonicity"
N("ExP1", "ClP13", 0.85)               # "by giving an example in which FDR monotonicity is violated"
N("DP17", "TP5", 0.8, ); N("DP7", "TP5", 0.8)
# section 5-7
N("DP25", "DP27", 0.85); N("DP27", "ClP14", 0.85); N("DP25", "ClP14", 0.8)
N("AP1", "DP28", 0.9)                  # "the BH95 procedure as described in the Introduction"
N("DP8", "DP28", 0.8)
for t in ("ClP15", "ClP16"):
    N("DP24", t, 0.8)                  # IBHsum
N("DP10", "ClP17", 0.75); N("DP10", "ClP18", 0.9); N("DP10", "ClP20", 0.85); N("DP10", "ClP24", 0.85)
N("TP1", "ClP18", 0.85)                # BY2001 proof for BH95
for t in ("ClP17", "ClP19", "ClP20", "ClP23", "ClP24", "ClP26", "ClP29", "ClP30", "ClP31", "ClP32"):
    N("DP28", t, 0.8)
for t in ("ClP19", "ClP23", "ClP29", "ClP30", "RP6"):
    N("ClP12", t, 0.75)                # IBHlog
for t in ("ClP17", "ClP19", "ClP23", "ClP27", "ClP28", "ClP29", "ClP30", "ClP31", "RP6"):
    N("DP24", t, 0.75)                 # IBHsum
for t in ("ClP17", "ClP23", "ClP24", "ClP26", "ClP32"):
    N("DP15", t, 0.8)                  # IBH
N("DP29", "DP30", 0.85)                # "This measure of power"
N("DP29", "ClP20", 0.85); N("DP29", "ClP21", 0.85)
N("ClP19", "ClP23", 0.75); N("ClP17", "ClP23", 0.75); N("ClP20", "ClP23", 0.75)
N("ClP19", "ClP32", 0.8)               # "as shown in Section 5.1"
N("ClP29", "ClP32", 0.8); N("ClP30", "ClP32", 0.8); N("ClP31", "ClP32", 0.8)
I("ClP29", "RP6", 0.7); I("ClP30", "RP6", 0.7); I("ClP31", "RP6", 0.7)
I("ClP22", "ClP25", 0.6)

# defined terms (pass 2), checked by reading each target
TERM = {
    "DP1": ["DP6", "ClP7", "RP6"],
    "DP2": ["DP3", "DP7", "AP1", "TP1", "ClP1", "DP9", "DP12", "DP14", "DP18", "AP2", "TP3", "ClP4", "DP19", "DP20",
            "ClP8", "PP1", "DP21", "DP22", "ExP1", "DP25", "DP28", "ClP14"],
    "DP3": ["ClP14", "DP30", "ClP21"],
    "DP4": ["AP1", "DP17", "DP16", "DP19", "DP20", "ClP8", "PP1", "TP5", "DP25", "DP27", "DP18", "PP3", "ClP12", "ExP1"],
    "DP5": ["DP7", "AP1", "DP9", "AP2", "TP5"],
    "DP7": ["TP1", "ClP1", "DP9", "DP14", "TP3", "ClP4", "ClP6", "ClP12", "ExP1", "ClP17", "ClP18", "ClP19", "ClP21", "ClP23", "ClP25", "ClP26", "ClP22"],
    "DP11": ["DP15"],
    "DP17": ["DP18", "AP2", "TP3"],
    "DP18": ["ClP5"],
    "DP19": ["ClP5", "ClP8", "PP1", "PP2", "ClP9", "DP24", "RP4", "RP5"],
    "DP20": ["ClP5", "ClP8", "PP1", "PP3", "ClP11", "RP4", "RP5"],
    "DP23": ["ClP11", "TP5", "CP1"],
    "DP24": ["ClP10"],
    "DP25": ["ClP15", "ClP16", "ClP17", "ClP18", "ClP19", "ClP20", "ClP24", "ClP26"],
    "DP26": ["ClP16", "ClP17", "ClP18", "ClP19", "ClP20", "ClP22", "ClP23"],
    "DP27": ["ClP18"],
    "DP3_": [],
    "DP29": ["ClP23", "RP6"],
    "DP13": ["ClP2", "ClP3"],
    "DP21_": ["RP3"],
    "DP8": ["AP2", "TP3", "ClP15"],
}
TERM.pop("DP3_"); TERM["DP21"] = TERM.pop("DP21_")
for d, ts in TERM.items():
    for t in ts:
        E(d, t, conf=0.75, basis="term")

# ============================================================ metadata
NOTES = [
    {"category": "source_problem", "nodes": ["ClP8", "PP1"],
     "note": "Claim 3.1(a) prints E[hat m_0'] >= m where conservativeness (and the proof) give >= m_0; the proof of (a) writes E[tilde m_0'] = sum E[log(1-p_j)] without the minus sign of the definition (18). Both look like typos; copied verbatim."},
    {"category": "source_problem", "nodes": ["AP2"],
     "note": "Definition 2.2 defines the modified step-down procedure with R = min{i: p_(i) > alpha_i} - 1, i.e. with the BH95 constants alpha_i; gamma_i was presumably intended."},
    {"category": "source_problem", "nodes": ["TP3", "TP5", "ClP12", "PP4"],
     "note": "The proofs of Theorem 2.3, Claim 3.2 and Theorem 4.1 are only in the online supplement, so these results have no proof node (PP4 is the one-sentence outline the paper gives). The supplement list calls the IBHlog result 'Claim 3.1', while it is the second claim (3.2)."},
    {"category": "rule_conflict", "nodes": ["PP4"],
     "note": "'A proof sketch' asks for rigor semi_formal on the proof node, while the rigor rules forbid rigor on proofs; PP4 got no rigor and its proves edge no alternative flag, since the full proof is not in the paper."},
    {"category": "type_uncertain", "nodes": ["ClP9"],
     "note": "One sentence both asserts E[hat m_0'] <= m and, in a bracket, defines 'stochastically smaller' (f <=_st g); it is one claim node (nodes never split a sentence), and its term edges stand in for the definition."},
    {"category": "boundary_uncertain", "nodes": ["PP2", "PP3"],
     "note": "Sections 3.1 and 3.2 reprove the lower bounds of Claim 3.1(a) in one sentence each; they are proof nodes with alternative proves edges to the claim."},
    {"category": "unexpected_construct", "nodes": ["DP7"],
     "note": "The counts U, V, T, S are defined only in Table 1 (a float), not in any sentence, so they have no definition node; Table 2 (real-data power ratios) is represented by the claims that read it (ClP29-ClP31)."},
    {"category": "not_extracted", "nodes": [],
     "note": "Not extracted: the announcement of results in the introduction, figure captions, the reported m_0 estimates of the two data sets, the description of p-value curve shapes, and the Discussion apart from the closing recommendation."},
]
COMMENT = ("Things worth checking: (i) Theorem 2.3 needs a monotonic estimator, but the paper verifies monotonicity only for the "
           "uncorrected hat m_0', tilde m_0' (ClP5, no argument); for the IBHsum estimator C(m) min[m, max(s(m), hat m_0')] the second "
           "condition of Definition 2.1 depends on C(m) and s(m), and its control rests on numerically computed factors; "
           "(ii) Theorem 4.1 uses 'threshold FDR procedures' and 'for any q' without defining them; (iii) Table 2 prints '(0.0340' for (0.034).")
meta = {
    "title": "FDR control with adaptive procedures and FDR monotonicity",
    "arxiv_id": "0909.3704",
    "authors": ["Amit Zeisel", "Or Zuk", "Eytan Domany"],
    "year": 2009,
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
