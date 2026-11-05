#!/usr/bin/env python3
"""Build the v7 LLM extraction of cs/0510016, 'From finite-system entropy to entropy rate for a
Hidden Markov Process' (Zuk, Domany, Kanter, Aizenman 2005). Nodes, types, spans and edges were
chosen by reading the paper; this script only slices the chosen spans out of the prepared source,
assembles the graph and runs finalize().  Usage: python3 build.py [--write]"""
import json, re, sys, subprocess, os
REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize
from latex_facts import read_tex

SCR = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_orzuk/cs_0510016"
CASE = REPO + "/corpus/orzuk/cs_0510016"
TEX = CASE + "/arxiv_src/cs_0510016.tex"
OUT = CASE + "/cs_0510016.json"
os.makedirs(SCR, exist_ok=True)
if not os.path.exists(SCR + "/facts.json"):
    subprocess.run([sys.executable, REPO + "/src/latex_facts.py", TEX, "--out", SCR + "/facts.json"], check=True)
facts = json.load(open(SCR + "/facts.json"))
S = facts["source"]
F = {f["id"]: f for f in facts["facts"]}
SECS = [s for s in facts["sections"] if s.get("inside") is None]


def norm(t):
    return re.sub(r"\s+", " ", t).strip()


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


EQN = [0]


def eq(fid, name, **kw):
    EQN[0] += 1
    nid = f"EP{EQN[0]}"
    env(nid, fid, "equation", name, "paper", 1.0, **kw)
    return nid


PSP = [0]
ORDER = {}


def step(parent, a, b, subclass, name, short=None, conf=0.75):
    lo, hi = POS[parent]
    i, _ = find(a, lo, hi)
    _, j = find(b, i, hi)
    PSP[0] += 1
    sid = f"PSP{PSP[0]}"
    ORDER[parent] = ORDER.get(parent, 0) + 1
    root = parent
    while byid[root]["type"] == "proof_step":
        root = byid[root]["parent_id"]
    add(sid, "proof_step", name, norm(S[i:j]), i, j, byid[root]["origin"], conf,
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

# ============================================================ 1 Introduction
prose("DP1", "definition", "Markov process and its noisy observation",
      r"\PARstart{L}{et} $\{X_N\}$ be a finite state", "(on the same alphabet).",
      origin="external", origin_citation=STD, conf=0.8,
      definiendum=[r"$\{X_N\}$", r"$\Sigma$", r"$\{Y_N\}$"],
      statement_short="$X$ is a finite-state stationary Markov process on $\\Sigma=\\{1,..,s\\}$ and $Y$ its noisy observation.")
prose("DP2", "definition", "Transition matrix and emission matrix",
      "The pair can be described by the Markov transition matrix", "= i) = r_{ij}$.",
      origin="external", origin_citation=STD, conf=0.8,
      definiendum=[r"$M$", r"$R$"],
      statement_short="$M=\\{m_{ij}\\}$ is the Markov transition matrix and $R=\\{r_{ij}\\}$ the emission matrix.")
prose("AssumP1", "assumption", "Small-noise regime and strictly positive transition matrix",
      "We consider here the case where the signal to noise ratio", "has a unique stationary distribution.",
      conf=0.8)
prose("DP3", "definition", "High-SNR parametrization R = I + epsilon T",
      "For the `high - SNR' regime one may write", r"\sum_{j=1}^{s}{t_{ij}} = 0$.",
      conf=0.8, definiendum=[r"$\epsilon$", r"$T$"],
      statement_short="In the high-SNR regime the emission matrix is $R=I+\\epsilon T$ with small $\\epsilon>0$ and $T$ a rate-like matrix (rows sum to 0).")
prose("DP4", "definition", "Hidden Markov Process (HMP)",
      "The process $Y$ can be viewed as an observation", "parameters $M$, $T$ and $\\epsilon$.",
      origin="external", origin_citation="Ephraim & Merhav 2002; Rabiner 1989", conf=0.8,
      definiendum="Hidden Markov Process (HMP)", genus="observation of $X$ through a noisy channel")
prose("DP5", "definition", "Vector notation [X]_i^j",
      r"More formally, for $i \leq j$ let $[X]_i^j$", "the vector $(X_i,..,X_j)$.",
      conf=0.85, definiendum=r"$[X]_i^j$")
prose("DP6", "definition", "Shannon entropy rate",
      "The entropy rate is defined as:", "should be understood as $P(X = x)$.",
      origin="external", origin_citation="Shannon 1948", conf=0.9,
      definiendum=["entropy rate", r"$\bar{H}(Y)$", r"$H(X)$"],
      statement_short="The entropy rate is $\\bar H(Y)=\\lim_N H([Y]_1^N)/N$, with $H$ the Shannon entropy.")
prose("TP1", "theorem", "Entropy rate as limit of conditional entropy",
      "For a stationary process the limit in", r"H(Y_N | [Y]_1^{N-1})$.",
      origin="external", origin_citation="Cover & Thomas 1991", conf=0.85,
      assumptions=["For a stationary process"],
      conclusions=["the limit in (\\ref{entropy_rate_def}) exists",
                   span(r"$\bar{H}$ can also be computed via the conditional", r"H(Y_N | [Y]_1^{N-1})$")],
      statement_short="For a stationary process the entropy rate exists and equals $\\lim_N H(Y_N|[Y]_1^{N-1})$.")
prose("DP7", "definition", "Conditional entropy",
      r"Here $H(U|V)$ represents the conditional entropy", r"H(U | V=v) $.",
      origin="external", origin_citation=STD, conf=0.85,
      definiendum=["conditional entropy", r"$H(U|V)$"],
      genus="the average uncertainty of the conditional distribution of $U$ conditioned on $V$")
prose("TP2", "theorem", "Chain rule for entropy",
      "By the chain rule for entropy, it can also be viewed", r"H(U,V) - H(V)$.",
      origin="external", origin_citation=STD, conf=0.85,
      assumptions=[], conclusions=[r"$H(U|V) = H(U,V) - H(V)$"])
prose("OpenP1", "open_problem", "Explicit expression for the entropy rate of an HMP",
      "There is at present no explicit expression for the entropy", r"(\cite{Merhav,Jacquet}).",
      origin="external", origin_citation="Ephraim & Merhav 2002; Jacquet, Seroussi & Szpankowski 2004", conf=0.65)
EP1 = eq("F1", "Entropy rate definition")

# ============================================================ 2 Theorem Statement and Proof
env("TP3", "F2", "theorem", "Settling of the entropy-rate expansion coefficients", main=True,
    assumptions=[span(r"$H_N \equiv H_N(M,T,\epsilon) = H([Y]_1^N)$", "system of length $N$"),
                 span("$C_N = H_N - H_{N-1}$", "$C_N = H_N - H_{N-1}$"),
                 span(r"there is some (complex) neighborhood $B_{\rho}(0)", r"analytic in $\epsilon$")],
    conclusions=[span(r"N \geq \lceil \frac{k+3}{2} \rceil \Rightarrow", r"C_N^{(k)} = C^{(k)}", lo=8200)],
    also_stated_at=[span("The surprising 'settling' of the expansion", "hold for the entropy.")],
    statement_short="If $C_N=H_N-H_{N-1}$ and $\\bar H$ are analytic in $\\epsilon$ near 0 (uniformly), the $k$-th Taylor coefficient of $C_N$ equals that of the entropy rate once $N\\ge\\lceil (k+3)/2\\rceil$.")
EP2 = eq("F3", "Taylor expansions of C_N and the entropy rate")
EP3 = eq("F4", "Settling of the coefficients")
prose("TP4", "theorem", "C_N is an upper bound for the entropy rate",
      r"\noindent $C_N$ is an upperbound", r"for $\bar{H}$.", lo=8380,
      origin="external", origin_citation="Cover & Thomas 1991", conf=0.85,
      assumptions=[], conclusions=[span(r"$C_N$ is an upperbound", r"for $\bar{H}$.", lo=8380)])
prose("RP1", "remark", "Earlier symbolic discovery and k <= 2 proof",
      r"The behavior stated in Thm. \ref{main_thm}", r"binary symmetric case (\cite{ZKD1}).",
      origin="external", origin_citation="Zuk, Kanter & Domany 2005", conf=0.8)
prose("DP8", "definition", "Process Z with site-dependent noise",
      r"We consider a more general process $\{Z_N\}$", r"and $[\epsilon]_{1}^N$.",
      conf=0.85, definiendum=[r"$\{Z_N\}$", r"$R_i$", r"$\epsilon_i$"],
      genus="process", differentia=[r"$Z_i$'s emission matrix is $R_i = I + \epsilon_iT$"])
prose("DP9", "definition", "Functions F_N",
      "We define the following functions:", r"H([Z]_1^{N-1}) \end{equation}",
      conf=0.9, definiendum=r"$F_N$",
      statement_short="$F_N$ is the entropy increment $H([Z]_1^N)-H([Z]_1^{N-1})$ of the site-dependent-noise process.")
EP4 = eq("F5", "Definition of F_N")
prose("ClP1", "claim", "F_N on the diagonal equals C_N",
      r"Setting all the $\epsilon_i$'s equal", r"= C_N(\epsilon)$.",
      conf=0.75, assumptions=[r"Setting all the $\epsilon_i$'s equal"],
      conclusions=[r"$F_N(M,T, (\epsilon,..,\epsilon)) = C_N(\epsilon)$"])
prose("ClP2", "claim", "Blocking observation",
      r"Second, we observe that if a particular $\epsilon_i$", "to the past is 'blocked'.",
      conf=0.7, assumptions=[r"a particular $\epsilon_i$ is set to zero"],
      conclusions=[r"the observation $Z_i$ equals the state $X_i$", "conditioning back to the past is 'blocked'"],
      statement_short="If $\\epsilon_i=0$ then $Z_i=X_i$, so by the Markov property conditioning on the past is blocked at site $i$.")

env("LP1", "F6", "lemma", "Blocking lemma",
    assumptions=[r"$\epsilon_j=0$ for some $1 < j < N$"],
    conclusions=[r"F_N([\epsilon]_1^N) = F_{N-j+1}([\epsilon]_{j+1}^N)"],
    statement_short="A zero noise parameter at site $j$ cuts $F_N$ down to $F_{N-j+1}$ of the sites after $j$.")
env("PP1", "F7", "proof", "Proof of the blocking lemma", proves="LP1", proof_strategy=["direct"],
    statement_short="Write $F_N$ as a conditional entropy and use the Markov property: $Z_j=X_j$ blocks conditioning on sites before $j$.")
EP5 = eq("F8", "F_N as conditional entropy sum")
EP6 = eq("F9", "Blocking of conditioning")
EP7 = eq("F10", "F_N reduces to F_{N-j+1}")
step("PP1", r"$F$ can be written as the sum:", r"hidden in the probabilities $P(..)$.",
     "invoke_identity", "Write F_N as a conditional-entropy sum")
step("PP1", r"Since $\epsilon_j=0$, we must have", r"P(Z_N | [Z]_j^{N-1}) \label{blocking_cond} \end{equation}",
     "apply_lemma", "Markov property blocks conditioning at site j")
step("PP1", r"Substituting in eq. \ref{F_cond_eq}", r"F_{N-j+1} \end{equation}",
     "conclude", "Substitute and marginalize to get F_{N-j+1}")

prose("DP10", "definition", "Derivative-order vector k",
      r"\noindent Let $\vec{k} = [k]_1^N$ be a vector", r"\cup 0\}$.", lo=10400,
      conf=0.85, definiendum=r"$\vec{k}$")
prose("DP11", "definition", "Weight of k",
      "Define its 'weight' as", r"k_i$.", lo=10400, conf=0.9, definiendum=["weight", r"$\omega(\vec{k})$"])
prose("DP12", "definition", "Mixed derivatives F_N^k at zero noise",
      "Define also:", r"\right|_{\vec{\epsilon} = 0} \end{equation}", lo=10500,
      conf=0.9, definiendum=r"$F_N^{\vec{k}}$",
      statement_short="$F_N^{\\vec k}$ is the mixed partial derivative of $F_N$ of orders $k_i$ in $\\epsilon_i$, at $\\vec\\epsilon=0$.")
EP8 = eq("F11", "Definition of F_N^k")

env("LP2", "F12", "lemma", "Leading zeros leave F_N^k unchanged",
    assumptions=[r"$\vec{k} = [k]_1^N$ with $k_1 \leq 1$"],
    conclusions=[norm(r"F_N^{\vec{k}} = F_{r+N}^{\vec{k}^{(r)}} \quad,  \forall r \in \mathbb{N}")],
    statement_short="Padding $\\vec k$ (with $k_1\\le 1$) by $r$ leading zeros does not change $F_N^{\\vec k}$.")
env("PP2", "F13", "proof", "Proof that leading zeros leave F_N^k unchanged", proves="LP2",
    proof_strategy=["case_analysis", "direct"],
    statement_short="Cases $k_1=0$ (blocking lemma at the zero site) and $k_1=1$ (differentiate once in $\\epsilon_2$, reducing to $k_1=0$).")
EP9 = eq("F14", "Case k_1 = 0")
EP10 = eq("F15", "Case k_1 = 1")
step("PP2", r"Assume first $k_1 = 0$.", r"\label{k_is_zero_eq} \end{equation}", "case_split",
     "Case k_1 = 0 via the blocking lemma")
c2 = step("PP2", r"The case $k_1 = 1$ is reduced", r"F_{N}^{\vec{k}}([\epsilon]_1^{N})\end{equation}", "case_split",
          "Case k_1 = 1")
step(c2, r"The case $k_1 = 1$ is reduced", "by taking the derivative.", "setup",
     "Reduce k_1 = 1 to k_1 = 0 by differentiating")
step(c2, r"We denote ${[Z]_1^N}^{(j \to r)}$", r"F_{N}^{\vec{k}}([\epsilon]_1^{N})\end{equation}", "algebraic_manipulation",
     "Differentiate in epsilon_2 and apply the k_1 = 0 case")

prose("ClP3", "claim", "Taylor coefficient as a sum of mixed derivatives",
      r"\noindent $C_N^{(k)}$ is obtained by summing", r"F_N^{\vec{k}} \end{equation}", lo=13090,
      conf=0.7, rigor="semi_formal",
      assumptions=[], conclusions=[r"C_N^{(k)} = \sum_{\vec{k},\omega(\vec{k})=k} F_N^{\vec{k}}"])
EP11 = eq("F16", "C_N^(k) as sum over weight-k vectors")

env("LP3", "F17", "lemma", "No-hole lemma",
    assumptions=[r"$\vec{k} = [k]_1^N$",
                 norm(r"$\exists i < j < N$, with $k_i \geq 1, k_j \leq 1$")],
    conclusions=[r"$F_N^{\vec{k}} = 0$"],
    statement_short="$F_N^{\\vec k}$ vanishes if some site $i$ with $k_i\\ge1$ is followed (before $N$) by a site $j$ with $k_j\\le1$.")
env("PP3", "F18", "proof", "Proof of the no-hole lemma", proves="LP3",
    proof_strategy=["case_analysis", "direct"],
    statement_short="Case $k_j=0$: blocking removes $\\epsilon_i$. Case $k_j=1$: the first derivative in $\\epsilon_j$ at 0, computed via Bayes' rule and blocking, does not involve $\\epsilon_i$.")
for fid, nm in [("F19", "Case k_j = 0 vanishes"), ("F20", "Probability of Z as sum over X"),
                ("F21", "Derivative of P(Z) in epsilon_j"), ("F22", "Derivative of conditional probability"),
                ("F23", "Derivative of P log P"), ("F24", "Derivative of F_N in epsilon_j")]:
    eq(fid, nm)
step("PP3", r"Assume first $k_j = 0$.", r"\right|_{\vec{\epsilon} = 0} = 0 \end{equation}", "case_split",
     "Case k_j = 0 via the blocking lemma")
c2 = step("PP3", r"Assume now $k_j = 1$.", r"and $F_N^{\vec{k}} = 0$.", "case_split", "Case k_j = 1")
s1 = step(c2, r"Assume now $k_j = 1$.", "is Kronecker's delta.", "invoke_identity",
          "Write P(Z) as a sum over hidden states")
s2 = step(c2, "Differentiate with respect to", r"\right\} \right|_{\epsilon_j = 0} \end{equation}", "algebraic_manipulation",
          "Differentiate P(Z) in epsilon_j")
s3 = step(c2, "Using Bayes' rule", r"\right] \right|_{\epsilon_j = 0} \end{equation}", "invoke_identity",
          "Bayes' rule gives the derivative of the conditional probability")
s4 = step(c2, "This gives:", r"\right\} \right|_{\epsilon_j = 0} \end{equation}", "algebraic_manipulation",
          "Derivative of P log P")
s5 = step(c2, "And therefore:", "which 'blocks' the dependence backwards.", "substitute",
          "Derivative of F_N, then blocking")
s6 = step(c2, r"Eq. \ref{F_N_deriv_eq} shows", r"and $F_N^{\vec{k}} = 0$.", "conclude",
          "epsilon_i absent for i < j, so the mixed derivative vanishes")
E(s1, s2, conf=0.8); E(s2, s3, conf=0.8); E(s3, s4, conf=0.8); E(s4, s5, conf=0.8)

prose("PP4", "proof", "Proof of the main theorem",
      r"\noindent Let $\vec{k} = [k]_1^N$ with $\omega(\vec{k}) = k$.",
      r"\forall N \geq \lceil \frac{k+3}{2} \rceil $. \\", lo=16900, conf=1.0,
      proves="TP3", proof_strategy=["direct"],
      statement_short="Only vectors of bounded 'length' contribute (no-hole lemma); trimming leading zeros (zero-tail lemma) makes $C_N^{(k)}$ constant in $N$, and analyticity identifies it with $C^{(k)}$.")
EP18 = eq("F26", "F_N^k reduces to a vector of length ceil((k+3)/2)")
a = step("PP4", r"Let $\vec{k} = [k]_1^N$ with", r"\min_{k_i > 1} \{i \}$.", "introduce_variable",
         "Introduce the length of k")
b = step("PP4", "It easily follows from lemma", r"\rceil - 1$.", "apply_lemma",
         "No-hole lemma bounds the length of contributing k")
c = step("PP4", "Thus, according to lemma", "for all $\\vec{k}$'s in the sum.", "apply_lemma",
         "Zero-tail lemma reduces each term to fixed length")
d = step("PP4", r"Summing on all $F_N^{\vec{k}}$", r"\forall N > \lceil \frac{k+3}{2} \rceil$.", "algebraic_manipulation",
         "Sum over weight k: C_N^(k) constant in N")
e = step("PP4", "But from the analyticity", r"\forall N \geq \lceil \frac{k+3}{2} \rceil $. \\", "conclude",
         "Analyticity gives the limit C^(k)")
E(a, b); E(b, c); E(c, d); E(d, e)

# ============================================================ 3 Conclusion
prose("ClP4", "claim", "Weaker settling for conditional-probability functionals",
      "For other functions involving only conditional", r"'settle' for $N \geq k$.",
      conf=0.7, rigor="semi_formal",
      assumptions=["For other functions involving only conditional probabilities (e.g. relative entropy between two {\\it HMPs})"],
      conclusions=[r"the coefficients 'settle' for $N \geq k$"])
prose("ClP5", "claim", "Settling in the almost-memoryless regime",
      "As it turns out, exactly the same", r"makes the $X_i$'s i.i.d.",
      conf=0.7, rigor="semi_formal",
      assumptions=[r"the 'almost memoryless' regime, where $M$ is close to a matrix which makes the $X_i$'s i.i.d"],
      conclusions=[r"exactly the same 'settling' as was proven in Thm. \ref{main_thm} happens"])

# ============================================================ edges
# mentions stated by a \ref
E("TP3", "RP1", conf=0.95, basis=None, mention=True)
E("TP3", "ClP5", conf=0.95, basis=None, mention=True)
# proof of the main theorem labelled in words
E("PP4", "TP3", "proves", 0.95, "named")
# words / inferred
E("ClP2", "PP1", conf=0.85, basis="named")          # "This can be used to prove:"
E("TP2", "PP1", conf=0.7)                            # F_N as a conditional entropy
E("TP2", "TP4", conf=0.6)
E("ClP1", "ClP3", conf=0.75)
E("ClP3", d, conf=0.8)                               # summing over weight
E("TP1", e, conf=0.7)                                # C_N -> entropy rate
E("ClP1", "PP4", conf=0.7)
E("AssumP1", "TP3", conf=0.7)
E("AssumP1", "TP1", conf=0.6)
E("DP4", "OpenP1", conf=0.85, basis="term")
E("DP6", "OpenP1", conf=0.85, basis="term")
E("DP4", "ClP4", conf=0.8, basis="term")
E("DP3", "ClP1", conf=0.75, basis="term")
# notation C_N, C_N^(k) introduced inside the theorem: used, the theorem's truth is not
E("TP3", "ClP1", conf=0.75, basis="term", mention=True)
E("TP3", "ClP3", conf=0.75, basis="term", mention=True)
# "lemma \ref{..}": the \label sits after the nested proof, so latex_facts gives it to the proof;
# the lemma itself is what the text names
E("LP1", "PSP4", conf=0.9, basis="named"); E("LP1", "PSP8", conf=0.9, basis="named")
E("LP2", "PSP18", conf=0.9, basis="named"); E("LP3", "PSP17", conf=0.9, basis="named")
# defined terms (pass 2), checked by reading each target
TERM = {
    "DP1": ["DP2", "AssumP1", "DP3", "DP4", "DP6", "TP1", "TP3", "DP8", "PP1", "PP3"],
    "DP2": ["AssumP1", "DP3", "DP4", "TP3", "DP8", "ClP5"],
    "DP3": ["DP4", "TP3", "DP8", "PP2", "PP3"],
    "DP5": ["DP6", "TP1", "TP3", "DP8", "DP9", "LP1", "PP1", "DP10", "LP2", "PP2", "LP3", "PP3", "PP4"],
    "DP6": ["TP1", "DP7", "TP3", "TP4", "PP4", "ClP4"],
    "DP7": ["TP1", "TP2"],
    "DP8": ["DP9", "ClP1", "ClP2", "LP1", "PP1", "PP2", "PP3"],
    "DP10": ["DP11", "DP12", "LP2", "LP3", "ClP3", "PP4"],
    "DP11": ["DP12", "PP2", "PP3", "ClP3", "PP4"],
    "DP12": ["LP2", "PP2", "ClP3", "LP3", "PP3", "PP4"],
    "TP3": ["TP4", "ClP4"],
    "DP9": ["ClP1", "LP1", "PP1", "DP12", "LP2", "PP2", "LP3", "PP3"],
}
for d, ts in TERM.items():
    for t in ts:
        E(d, t, conf=0.75, basis="term")

# ============================================================ metadata
NOTES = [
    {"category": "source_problem", "nodes": ["LP1", "PP1", "PP3"],
     "note": "Lemma 1 states F_N([\\epsilon]_1^N) = F_{N-j+1}([\\epsilon]_{j+1}^N), but its proof ends with a sum over [Z]_j^N and the proof of Lemma 3 applies it as F_{N-j+1}([\\epsilon]_j^N); the index j+1 looks like a typo for j (a vector of length N-j+1 starts at j)."},
    {"category": "source_problem", "nodes": ["ClP3"],
     "note": "Eq. (11) writes C_N^{(k)} as the plain sum of F_N^{\\vec k} over weight-k vectors; the Taylor coefficient of the diagonal restriction carries a factor 1/(k_1!...k_N!), which is missing (the termwise argument of the main proof is unaffected). The claim is stated without argument (rigor semi_formal)."},
    {"category": "source_problem", "nodes": ["DP7", "AssumP1", "PP2", "PP3"],
     "note": "Typos copied verbatim: conditional entropy written with P(U=u) instead of P(V=v); 'the signal to noise ratio (SNR) is small' where the next sentence treats the high-SNR (small-noise) regime; t_{X_i r} in Lemmas 2-3 has an index i not bound there (should involve the differentiated site)."},
    {"category": "boundary_uncertain", "nodes": ["PP4"],
     "note": "The proof of Theorem 1 is a \\begin{proof} environment placed after Lemma 3, introduced by 'We are now ready to prove our main theorem:' (no syntactic link); its proves edge was added as named. A stray \\label{strong_thm} follows it and is never referenced."},
    {"category": "source_problem", "nodes": ["LP1", "LP2", "LP3", "PP1", "PP2", "PP3"],
     "note": "Each lemma's proof sits inside the lemma environment, with the lemma's \\label after \\end{proof}; latex_facts attributes the label to the proof, so the \\ref edges run from the proofs (PP1->PP2, PP3->PP4, ...) and into the lemma nodes whose statements contain the next proof. Named edges from the lemmas themselves were added to the citing steps."},
    {"category": "not_extracted", "nodes": [],
     "note": "The conjecture of [ZKD1] that the theorem generalizes is mentioned but never stated, so it has no node; the abstract, the history paragraph of the introduction and the first summarizing sentence of the conclusion are discussion."},
]
meta = {
    "title": "From finite-system entropy to entropy rate for a Hidden Markov Process",
    "arxiv_id": "cs/0510016",
    "authors": ["Or Zuk", "Eytan Domany", "Ido Kanter", "Michael Aizenman"],
    "year": 2005,
    "annotator": "agent-extraction",
    "model": "claude-opus-5-5",
    "effort": "default",
    "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
    "extraction_date": "2026-11-05",
    "rigor_nonformal_count": sum(1 for n in nodes if "rigor" in n),
    "paper_style": ["theorem_proof"],
    "extraction_notes": NOTES,
    "extraction_comment": "The main theorem assumes (footnote) uniform analyticity of C_N in a common neighbourhood of epsilon=0; this assumption is not proven in the paper and is recorded among the theorem's assumptions.",
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
