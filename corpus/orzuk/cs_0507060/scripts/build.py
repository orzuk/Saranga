#!/usr/bin/env python3
"""Build the v7 LLM extraction of Zuk, Kanter & Domany, 'The Entropy of a Binary Hidden Markov
Process' (cs/0507060). Nodes, types, spans and edges were chosen by reading the paper; this script
only slices the chosen spans out of the prepared source, assembles the JSON and runs finalize()."""
import json, re, sys, subprocess, os
REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize
from latex_facts import read_tex

SCR = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_orzuk/cs_0507060"
BASE = REPO + "/corpus/orzuk/cs_0507060"
TEX = BASE + "/arxiv_src/ZukKanterDomanyResub.tex"
OUT = BASE + "/cs_0507060.json"
os.makedirs(SCR, exist_ok=True)
if not os.path.exists(SCR + "/facts.json"):
    subprocess.run([sys.executable, REPO + "/src/latex_facts.py", TEX, "--out", SCR + "/facts.json"], check=True)
facts = json.load(open(SCR + "/facts.json"))
S = facts["source"]
F = {f["id"]: f for f in facts["facts"]}
SECS = [s for s in facts["sections"] if s.get("inside") is None]


def norm(t):
    return re.sub(r"\s+", " ", t).strip()


def rx(t):
    return r"\s*".join(re.escape(w) for w in norm(t).split(" "))


def find(t, lo=0, hi=None):
    m = re.compile(rx(t)).search(S, lo, hi if hi is not None else len(S))
    assert m, ("not found", t)
    return m.start(), m.end()


def sec_at(pos):
    s = max((x for x in SECS if x["start"] <= pos), key=lambda x: x["start"])
    return f"{s['number']} {s['title']}" if s["number"] else s["title"]


nodes, edges, byid, POS = [], [], {}, {}
STD = "standard (uncited)"


def add(nid, typ, name, stmt, start, end, origin="paper", conf=1.0, **kw):
    n = {"id": nid, "type": typ, "name": name, "statement": stmt,
         "section": kw.pop("section", None) or sec_at(start), "origin": origin, "confidence": conf}
    for k, v in kw.items():
        if v is not None:
            n[k] = v
    assert nid not in byid, nid
    nodes.append(n); byid[nid] = n; POS[nid] = (start, end)
    return n


def eq(nid, fid, name, origin="paper", conf=1.0, **kw):
    f = F[fid]
    return add(nid, "equation", name, norm(f["statement"]), f["start"], f["end"], origin, conf, **kw)


def prose(nid, typ, name, a, b, after=0, origin="paper", conf=0.75, **kw):
    i, _ = find(a, after)
    _, j = find(b, i)
    return add(nid, typ, name, norm(S[i:j]), i, j, origin, conf, **kw)


def sub(nid, a, b=None):
    st = byid[nid]["statement"]
    a = norm(a); i = st.index(a)
    if b is None:
        return a
    j = st.index(norm(b), i) + len(norm(b))
    return st[i:j]


def sent(a, b):
    i, _ = find(a); _, j = find(b, i)
    return norm(S[i:j])


CNT = {"proof_step": 0, "algorithm_step": 0}


def step(parent, a, b, sc, name, short=None, conf=0.75, order=None, typ="proof_step"):
    lo, hi = POS[parent]
    i, _ = find(a, lo, hi)
    _, j = find(b, i, hi)
    CNT[typ] += 1
    sid = ("PSP" if typ == "proof_step" else "ASP") + str(CNT[typ])
    root = parent
    while byid[root]["type"] in ("proof_step", "algorithm_step"):
        root = byid[root]["parent_id"]
    add(sid, typ, name, norm(S[i:j]), i, j, byid[root]["origin"], conf,
        parent_id=parent, step_order=order, subclass=sc, statement_short=short or name,
        section=byid[root]["section"])
    return sid


def E(s, t, conf=0.8, basis="inferred", typ="uses", **kw):
    e = {"source": s, "target": t, "type": typ, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)


# ======================================================== 1 Introduction
prose("DP1", "definition", "Number of received signals Omega_R",
      r"Two central aspects of this technology", r"the number of (expected) received signals.",
      conf=0.7, definiendum="$\\Omega_R$")
# "Two central aspects..." is the start of the sentence-pair; trim to the defining sentence
i, _ = find(r"For both problem areas it is of"); _, j = find(r"the number of (expected) received signals.", i)
byid["DP1"]["statement"] = norm(S[i:j]); POS["DP1"] = (i, j)
prose("ClP1", "claim", "Omega_R ~ 2^{NH} (typical set size)",
      r"In general, $\Omega_R$ is given, for large $N$", r"is the {\it entropy} of the process.",
      origin="external", origin_citation=STD, conf=0.7,
      assumptions=["for large $N$"], conclusions=["$\\Omega_R$ is given, for large $N$, by $2^{NH}$"],
      statement_short="For long messages the number of received signals is about $2^{NH}$, $H$ the entropy (asymptotic equipartition).")
byid["ClP1"]["conclusions"] = [sub("ClP1", r"$\Omega_R$ is given, for large $N$, by $2^{NH}$")]
byid["ClP1"]["assumptions"] = []
prose("OpenP1", "open_problem", "Channel capacity of a Markov source over a noisy channel",
      r"The calculation of channel capacity for a Markovian source", r"is still an open question.",
      origin="external", origin_citation=STD, conf=0.8)
prose("RP1", "remark", "Not the quenched random-field entropy (replica n=1)",
      r"Note that the object we are calculating is {\it not}", r"one works in the $n \rightarrow 0$ limit.",
      conf=0.75, statement_short="The computed quantity is the replica derivative at $n=1$, not the quenched ($n\\to0$) random-field Ising entropy.")

# ======================================================== 2.1 Defining the process
prose("DP2", "definition", "Binary transmitted symbols s_i",
      r"Binary valued symbols, $s_i=\pm 1$", r"at fixed times $i \Delta t $.",
      origin="external", origin_citation=STD, conf=0.8, definiendum="$s_i$")
prose("DP3", "definition", "Transmitted sequence S",
      r"Denote a sequence of $N$ transmitted", r"S = (s_1,s_2,....s_N) \end{equation}",
      origin="external", origin_citation=STD, conf=0.85, definiendum="$S$")
eq("EP1", "F1", "Transmitted sequence S", origin="external", origin_citation=STD)
prose("AssumP1", "assumption", "Markov source",
      r"The sequence is generated by a Markov process;", r"generated at previous times).",
      origin="external", origin_citation=STD, conf=0.8)
prose("DP4", "definition", "Transition matrix P",
      r"The process is parametrized by a transition matrix $P$", r"Pr(s_{i+1}=-1|s_i=+1) \end{equation}",
      origin="external", origin_citation=STD, conf=0.85, definiendum="$P$", genus="transition matrix")
eq("EP2", "F2", "Transition probabilities", origin="external", origin_citation=STD)
prose("DP5", "definition", "Binary symmetric Markov process (flipping rate p)",
      r"Here we treat the case of a {\it symmetric} process", r"\label{eq:Markov} \end{equation}",
      origin="external", origin_citation=STD, conf=0.8, definiendum=["symmetric process", "$p$"],
      differentia=["$P_{+,-} = P_{-,+}=p,~~$"],
      statement_short="Symmetric Markov chain: each symbol is flipped relative to the previous one with probability $p$.")
eq("EP3", "F3", "Symmetric Markov transition rule", origin="external", origin_citation=STD)
prose("AssumP2", "assumption", "Uniform first symbol",
      r"The first symbol $s_1$ takes the values", r"$Pr(s_1=+1)=Pr(s_1=-1)=1/2$.",
      origin="external", origin_citation=STD, conf=0.8)
eq("EP4", "F4", "Probability of a Markov sequence Pr(S)", origin="external", origin_citation=STD)
prose("DP6", "definition", "Received sequence R",
      r"The generated sequence $S$ is", r"is not identical to the transmitted one.",
      origin="external", origin_citation=STD, conf=0.85, definiendum="$R$")
eq("EP5", "F5", "Received sequence R", origin="external", origin_citation=STD)
bsc_intro = sent(r"The simplest way to model the noise is known as the {\it", r"flipped with probability $\epsilon$.")
prose("DP7", "definition", "Binary Symmetric Channel (noise level epsilon)",
      r"The noise can flip a transmitted symbol with probability", r"\label{eq:f}\end{equation}",
      origin="external", origin_citation=STD, conf=0.85, definiendum=["Binary Symmetric Channel", "$\\epsilon$"],
      also_stated_at=[bsc_intro])
eq("EP6", "F6", "Noise flip probability", origin="external", origin_citation=STD)
prose("AssumP3", "assumption", "i.i.d. noise",
      r"Here we assumed that the noise is generated by an independent", r"and of the value of $i$.",
      origin="external", origin_citation=STD, conf=0.85)
prose("AssumP4", "assumption", "Symmetric noise",
      r"We also assume that the noise is", r"does not depend on $s_i$.",
      origin="external", origin_citation=STD, conf=0.85)
eq("EP7", "F7", "Channel likelihood Pr(R|S)", origin="external", origin_citation=STD)
eq("EP8", "F8", "Joint probability Pr(R,S)", origin="external", origin_citation=STD)
prose("DP8", "definition", "Probability of a received signal Q(R)",
      r"Hence it is meaningful to ask - what is the probability", r"\label{eq:QSig} \end{equation}",
      origin="external", origin_citation=STD, conf=0.8, definiendum="$Q(R)$")
eq("EP9", "F9", "Output distribution Q(R)", origin="external", origin_citation=STD)
prose("DP9", "definition", "Shannon entropy H_N and entropy rate H",
      r"Furthermore, one is interested in the\footnote", r"\frac{H_N}{N}\end{equation}",
      origin="external", origin_citation=STD, conf=0.85,
      definiendum=["Shannon entropy $H_N$", "entropy rate $H$"])
eq("EP10", "F10", "Block entropy H_N", origin="external", origin_citation=STD)
eq("EP11", "F11", "Entropy rate H", origin="external", origin_citation=STD)

# ======================================================== 2.2 Ising form
prose("DP10", "definition", "Ising couplings J and K",
      r"The conditional Markov probabilities", r"e^{2K}=(1-\epsilon)/\epsilon \end{equation}",
      conf=0.8, definiendum=["$J$", "$K$"],
      statement_short="Write the Markov transition and the noise flip as Ising Boltzmann factors with couplings $e^{2J}=(1-p)/p$, $e^{2K}=(1-\\epsilon)/\\epsilon$.")
eq("EP12", "F12", "Markov coupling J")
eq("EP13", "F13", "Noise coupling K")
prose("TP1", "theorem", "Boltzmann-chain form of the HMP joint probability",
      r"The joint probability of realizing a pair of transmitted", r"\left( e^K + e^{-K} \right)^{-N}  \end{equation}",
      origin="external", origin_citation="Saul & Jordan 1994; MacKay 1996", conf=0.7,
      statement_short="The HMP joint law is an Ising chain with couplings $J$ and local fields $K r_i$, normalized by $A=A_0A_1$.")
byid["TP1"]["assumptions"] = []
byid["TP1"]["conclusions"] = [sub("TP1", r"Pr({\it R },S)= A \exp", r"\left( e^K + e^{-K} \right)^{-N}")]
eq("EP14", "F14", "Ising form of Pr(R,S)", origin="external", origin_citation="Saul & Jordan 1994; MacKay 1996")
eq("EP15", "F15", "Normalization constants A_0, A_1", origin="external", origin_citation="Saul & Jordan 1994; MacKay 1996")
prose("RP2", "remark", "Ising chain with dangling bonds",
      r"The first sum in (\ref{eq:prIsing}) is the Hamiltonian", r'bond" (see Fig 2).',
      conf=0.75)
prose("DP11", "definition", "Partition sum Z(R) over hidden variables",
      r"Denote the summation over the hidden variables", r"$Q({\it R } ) = A~Z({\it R })$.",
      conf=0.85, definiendum="$Z(R)$")
eq("EP16", "F16", "Partition sum Z(R)")
prose("ClP2", "claim", "Replica-derivative formula for H_N",
      r"Substituting in (\ref{eq:HN}),  the entropy of", r"\label{H_N_def} \end{equation}",
      conf=0.75, assumptions=[], statement_short="$H_N$ is minus the $n$-derivative at $n=1$ of $\\sum_R [A Z(R)]^n$.")
byid["ClP2"]["conclusions"] = [norm(F["F17"]["statement"])]
eq("EP17", "F17", "H_N as replica derivative")
prose("RP3", "remark", "Random-field Ising interpretation",
      r"The interpretation of this expression is obvious:", r"in the limit $n \rightarrow 0$).",
      conf=0.75, statement_short="$H_N$ averages $Z^n$ of an Ising chain over random-sign local fields $Kr_i$, as in the quenched RFIM but at $n=1$.")
prose("OpenP2", "open_problem", "Exact solution of the 1D random-field Ising chain",
      r"This problem has not been solved analytically", r"in the weak field limit \cite{DerHil}).",
      origin="external", origin_citation="Derrida et al.; Fisher et al.; Grinstein & Mukamel; Nieuwenhuizen & Luck", conf=0.65)
prose("RP4", "remark", "Entropy of the field signs, not of the spins",
      r"One should note that here we calculate the entropy", r"addressed yet by the physics community.",
      conf=0.75)
prose("RP5", "remark", "Small noise = infinite field limit",
      r"We are interested in calculating the entropy rate {\it in the", r"infinite field limit of the Ising chain.",
      conf=0.7)

# ======================================================== 3 Expansion to order eps^2
eq("EP18", "F18", "Entropy rate in Ising form")
prose("PP1", "proof", "Low-noise expansion of Z(R) to second order",
      r"A few technical points are in order.", r"using eq. (\ref{eq:pJ})):",
      conf=0.75, proves="ClP3", proof_strategy=["algebraic_manipulation"],
      statement_short="High-field expansion: expand $Z(R)$ by the number of spins flipped against their fields (0, 1, 2 adjacent or not), then sum over $R$ using partition-sum-like and energy-like identities. The key step is that every partition-sum-like term normalizes to $A_0\\sum_R e^{\\cal H}=1$.")
eq("EP19", "F19", "Small parameter e^{-2K}")
eq("EP20", "F20", "A_0 with periodic boundary conditions")
p1 = []
p1.append(step("PP1", r"A few technical points are in order.", r"expand to order $\epsilon^2$ afterwards.",
               "setup", "Small parameter e^{-2K}", "Use $e^{-2K}=\\epsilon/(1-\\epsilon)$ as the expansion parameter", order=1))
p1.append(step("PP1", r"Second, we will calculate", r"contains now $N$ pairs of neighbors.",
               "setup", "Periodic boundary conditions", "Replace open by periodic boundary conditions (a $1/N$ surface effect)", order=2))
p1.append(step("PP1", r"{\bf Expanding $Z({\it R })$:}", r"\label{eq:Z2b} \end{equation}",
               "introduce_variable", "Expanding Z(R)", "Expand $Z(R)$ by configurations with 0, 1 or 2 spins flipped against their fields", conf=0.95, order=3))
step(p1[2], r"Consider $Z({\it R } )$ from", r"\label{eq:Z0} \end{equation}",
     "introduce_variable", "Zeroth-order term Z^(0)", "Leading term: all spins aligned with their fields", order=1)
step(p1[2], r"The next term we add consists", r"\label{eq:Z1} \end{equation}",
     "introduce_variable", "First-order term Z^(1)", "One spin flipped: $N$ configurations with weight $e^{-2K}$", order=2)
step(p1[2], r"The next term is of the highest order", r"\label{eq:Z2b} \end{equation}",
     "case_split", "Second-order terms Z^(2a), Z^(2b)", "Two flipped spins: adjacent (class a) or not (class b)", order=3)
p1.append(step("PP1", r"Calculation of $H$ is now straightforward", r"over all the $r_i$ variables.",
               "setup", "Substitute and expand", "Substitute $AZ$ into the entropy, expand to second order and sum over $r_i$", order=4))
p1.append(step("PP1", r"These summations involve two kinds of terms.", r"A_0 \sum_R e^{{\cal H}(R)} =1 \end{equation}",
               "invoke_identity", "Partition-sum-like terms", "Partition-sum-like terms all normalize: $A_0\\sum_R e^{{\\cal H}(R)}=1$", order=5))
p1.append(step("PP1", r"The second type of term that contributes", r"keep track of their signs.",
               "bound_estimate", "Energy-like terms", "Energy-like terms have $\\Delta$-independent magnitude; track their signs", order=6))
p1.append(step("PP1", r"Finally, one has to remember that the constant", r"using eq. (\ref{eq:pJ})):",
               "conclude", "Expand A_1 and collect", "Expand $A_1$ in $\\epsilon$ and collect terms, switching from $J$ to $p$", order=7))
for k in range(21, 28):
    eq(f"EP{k}", f"F{k}", {21: "Zeroth-order term Z^(0)", 22: "First-order term Z^(1)", 23: "Second-order term Z^(2a)",
                           24: "Second-order term Z^(2b)", 25: "Partition-sum-like terms", 26: "Normalization of partition-sum-like terms",
                           27: "Energy-like terms"}[k])
abs_main = sent(r"We map the problem onto a one-dimensional", r"up to second order in $\epsilon$.")
sum_main = sent(r"Using a low-temperature/high-random-field", r"in the noise parameter $\epsilon$.")
i, _ = find(r"\begin{equation} H(p,\epsilon) = \sum_{k=0}^{\infty}"); _, j = find(r"\label{012_stat}\end{equation}", i)
add("ClP3", "claim", "Entropy rate of the binary symmetric HMP to second order in epsilon", norm(S[i:j]), i, j,
    conf=0.75, main=True, rigor="semi_formal", also_stated_at=[abs_main, sum_main],
    statement_short="Low-noise expansion $H=\\sum_k H^{(k)}(p)\\epsilon^k$ with explicit $H^{(0)}, H^{(1)}$ and the new second-order coefficient $H^{(2)}$.",
    tags=["entropy_rate", "hidden_markov_process", "series_expansion"])
byid["ClP3"]["assumptions"] = []
byid["ClP3"]["conclusions"] = [norm(F["F28"]["statement"]), norm(F["F29"]["statement"]), norm(F["F30"]["statement"])]
eq("EP28", "F28", "Low-noise series for H(p, epsilon)")
eq("EP29", "F29", "Zeroth and first order entropy coefficients", origin="external",
   origin_citation="Jacquet, Seroussi & Szpankowski 2004; Ordentlich & Weissman 2004")
eq("EP30", "F30", "Second order entropy coefficient H^(2)", main=None)
intro_attr = sent(r"While the zeroth and first", r"the second order term was not \cite{ZKD1} .")
prose("RP6", "remark", "Attribution of H^(0), H^(1); H^(2) new",
      r"The zeroth and first order terms (\ref{eq:H1H2}) were known", r"the second order term is new \cite{ZKD1}.",
      conf=0.8, also_stated_at=[intro_attr])

# ======================================================== 4 Upper bounds
prose("DP12", "definition", "Conditional entropy C_N",
      r"When investigating the limit $H$, it is useful", r"also known as the {\it conditional} entropy.",
      origin="external", origin_citation=STD, conf=0.85, definiendum=["conditional entropy", "$C_N$"])
prose("ClP4", "claim", "Entropy rate as limit of conditional entropies",
      r"Provided that $H$ exist, it easily follows that", r"H = \lim_{N \to \infty} C_N \end{equation}",
      origin="external", origin_citation=STD, conf=0.75,
      assumptions=["Provided that $H$ exist"], conclusions=["H = \\lim_{N \\to \\infty} C_N"])
eq("EP31", "F31", "H = lim C_N", origin="external", origin_citation=STD)
prose("TP2", "theorem", "Conditional entropy upper bound, monotone convergence",
      r"Moreover, according to \cite{Cover}, $C_N \geq H$", r"(N \to \infty) \end{equation}",
      origin="external", origin_citation="Cover & Thomas 1991", conf=0.85, assumptions=[],
      conclusions=["$C_N \\geq H$", "the convergence is monotone"])
eq("EP32", "F32", "C_N decreases to H", origin="external", origin_citation="Cover & Thomas 1991")
prose("ClP5", "claim", "Z(R) as a polynomial in p and epsilon",
      r"We can express $C_N$ as a function of $p$ and", r"where we denote $1_{s,s'}=(1+s s')/2$.",
      conf=0.7, assumptions=["from this point of we work with open boundary conditions on the Ising chain of $N$ spins"],
      statement_short="Rewrite $Z(R)$ with the original parameters $p,\\epsilon$ by counting agreeing neighbours and agreeing symbol pairs.")
byid["ClP5"]["conclusions"] = [norm(F["F33"]["statement"])]
eq("EP33", "F33", "Z(R) in p, epsilon variables")
prose("DP13", "definition", "Coefficients Z_i(R) of the epsilon-polynomial",
      r"Eq. (\ref{prob_R_cs_style}) gives $Z(R)$ explicitly", r"are functions of $p$ only.",
      conf=0.8, definiendum="$Z_i(R)$")
eq("EP34", "F34", "Z(R) = sum Z_i epsilon^i")
prose("ClP6", "claim", "Taylor expansion of H_N in epsilon",
      r"Substituting this expansion in eq. (\ref{H_N_def}), and", r"O({\epsilon }^{k+1}) \end{equation}",
      conf=0.75, assumptions=[], statement_short="Taylor-expanding $\\log Z(R)$ around $Z_0(R)$ gives $H_N$ to order $\\epsilon^k$.")
byid["ClP6"]["conclusions"] = [norm(F["F35"]["statement"])]
eq("EP35", "F35", "Order-k expansion of H_N")
prose("DP14", "definition", "Expansion coefficients C_N^(i) of the upper bound",
      r"When extended to terms of order $\epsilon^k$, this equation", r"+ O({\epsilon }^{k+1}) \end{equation}",
      conf=0.75, definiendum="$C_N^{(i)}$")
eq("EP36", "F36", "Series for C_N")
prose("ExP1", "example", "Second-order expansion of H_N",
      r"For example, stopping at order $L=2$ gives", r"\label{entropy_expansion} \end{equation}",
      conf=0.8)
eq("EP37", "F37", "H_N to second order")
prose("RP7", "remark", "Symbolic computation for N <= 8, k <= 11",
      r"The zeroth and first order terms can be evaluated", r"for $N \leq 8$ and $k \leq 11$.",
      conf=0.75, statement_short="Orders 0 and 1 are analytic for all $N$; higher orders computed symbolically in Maple for $N\\le 8$, $k\\le 11$.")
prose("TP3", "theorem", "First-order coefficient C_N^(1) independent of N",
      r"For the first order we have proved (\cite{ZKD1})", r"(and equals $H^{(1)}$).",
      origin="external", origin_citation="Zuk, Kanter & Domany, DCC 2005", conf=0.85, assumptions=[],
      conclusions=["$C_N^{(1)}$ is independent of $N$ (and equals $H^{(1)}$)"])
prose("ClP7", "claim", "Observed settling of C_N^(k) at N = ceil((k+3)/2)",
      r"The symbolic computation of higher order terms yielded", r"at $N=\lceil \frac{k+3}{2} \rceil$.",
      conf=0.7, rigor="numerical", assumptions=["For the values we have checked"],
      statement_short="Symbolically, $C_N^{(k)}$ becomes independent of $N$ from $N=\\lceil (k+3)/2\\rceil$; $C^{(2)}$ equals the exact $H^{(2)}$.")
byid["ClP7"]["conclusions"] = [sub("ClP7", r"So, $C_N^{(k)} = C^{(k)}$ for large enough $N$."),
                               sub("ClP7", r"the settling point for $C_N^{(k)}$ turned out to be at $N=\lceil \frac{k+3}{2} \rceil$")]
sum_settle = sent(r"We have shown for $k \leq 11$ that when the known", r"to values that are independent of $N$.")
byid["ClP7"]["also_stated_at"] = [sum_settle]
prose("CnjP1", "conjecture", "Critical chain length conjecture (settling of C_N^(k))",
      r"For any order $k$, there is a critical chain", r"we have $C_N^{(k)} = C^{(k)}$.",
      conf=0.9, statement_short="For each order $k$, the $\\epsilon^k$ coefficient of the conditional-entropy bound $C_N$ stops depending on $N$ once $N>\\lceil (k+3)/2\\rceil$.")
byid["CnjP1"]["assumptions"] = [sub("CnjP1", r"For any order $k$")]
byid["CnjP1"]["conclusions"] = [sub("CnjP1", r"there is a critical chain length", r"$C_N^{(k)} = C^{(k)}$")]
byid["CnjP1"]["also_stated_at"] = [sent(r"Posing a conjecture, that this continues", r"of the entropy up to order 11.")]
prose("ClP8", "claim", "C_N^(k) converges to H^(k)",
      r"It is known that $C_N \to H$, and $C_N$", r"for any $k \geq 1$ when $N \to \infty$.",
      conf=0.7, rigor="semi_formal",
      assumptions=["$C_N \\to H$", "$C_N$ and $H$ are analytic functions of ${\\epsilon }$ at ${\\epsilon }=0$"],
      conclusions=["$C_N^{(k)} \\to H^{(k)}$ for any $k \\geq 1$ when $N \\to \\infty$"],
      statement_short="Since $C_N\\to H$ and both are analytic at $\\epsilon=0$, the Taylor coefficients converge: $C_N^{(k)}\\to H^{(k)}$.")
byid["ClP8"]["assumptions"] = [sub("ClP8", r"$C_N \to H$"), sub("ClP8", r"$C_N$ and $H$ are analytic functions of ${\epsilon }$ at ${\epsilon }=0$")]
byid["ClP8"]["conclusions"] = [sub("ClP8", r"$C_N^{(k)} \to H^{(k)}$ for any $k \geq 1$ when $N \to \infty$")]
prose("ClP9", "claim", "Conjecture implies H^(k) = C^(k)",
      r"Therefore, if our conjecture is true,", r"this value equals $H^{(k)}$.",
      conf=0.75, statement_short="If the settling conjecture holds, the settled coefficient $C^{(k)}$ is the true entropy coefficient $H^{(k)}$.")
byid["ClP9"]["assumptions"] = [sub("ClP9", r"our conjecture is true"),
                               sub("ClP9", r"$C_N^{(k)}$ indeed settles  at some value $C^{(k)}$ independent of $N$ (for $N>N_c(k)$ )")]
byid["ClP9"]["conclusions"] = [sub("ClP9", r"this value equals $H^{(k)}$")]
prose("RP8", "remark", "Evidence for the conjecture at k = 0, 1, 2",
      r"Note that the settling is rigourously supported", r"supporting our conjecture.", conf=0.75)
prose("DP15", "definition", "lambda = 1 - 2p (second eigenvalue of P)",
      r"The first orders up to $H^{(11)}$, obtained by identifying", r"for better readability.",
      conf=0.75, definiendum="$\\lambda$")
prose("RP9", "remark", "Agreement with rigorous low-order coefficients",
      r"The values of $H^{(0)},H^{(1)}$ and $H^{(2)}$ coincide", r"postulating the above Conjecture.", conf=0.75)
prose("RP10", "remark", "Observed structure of the coefficients H^(k)",
      r"Interestingly, the nominators have a simpler expression", r"in the first derivative of $H$.",
      conf=0.7, rigor="numerical",
      statement_short="Numerators are simpler in $\\lambda$, contain only even powers, and the free term of $[p(1-p)]^{2(k-1)}H^{(k)}$ is claimed to be $(-1)^k/(k(k-1))$.")
prose("CnjP2", "conjecture", "Rational form of H^(k) in lambda",
      r"All of the above observations led us to", r"in the Appendix for $H^{(k)}$ up to $k=11$.",
      conf=0.85, statement_short="For $k\\ge3$, $H^{(k)}$ is $2^{4(k-1)}$ times an even integer polynomial in $\\lambda$ over $k(k-1)(1-\\lambda^2)^{2(k-1)}$.")
byid["CnjP2"]["assumptions"] = [sub("CnjP2", r"for $k \geq 3$")]
byid["CnjP2"]["conclusions"] = [norm(F["F38"]["statement"]), sub("CnjP2", r"$a_{j,k}$ and $d_k$ are integers")]
eq("EP38", "F38", "Conjectured form of H^(k)")

# ======================================================== 5 Radius of convergence
prose("ClP10", "claim", "H is not analytic at epsilon = 0 when p = 0",
      r"The fundamental observation made here is that for", r"since its first derivative diverges.",
      conf=0.7, assumptions=["for $p=0$"])
byid["ClP10"]["conclusions"] = [sub("ClP10", r"the function $H({\epsilon })$ is not an analytic function at ${\epsilon } = 0$")]
prose("RP11", "remark", "Singularity moves to negative epsilon as p grows",
      r"As we increase $p$, the singularity points", r"distance of ${\epsilon } = 0$ from this singularity.",
      conf=0.7, rigor="heuristic")
prose("DP16", "definition", "Radius of convergence rho(p)",
      r"Denote by $\rho(p)$ the radius of convergence", r"$\rho(p) \to 0$.",
      conf=0.85, definiendum="$\\rho(p)$", genus="radius of convergence")
prose("DP17", "definition", "Non-interacting i.i.d. model",
      r"It is useful to first look at a simpler model", r"of absolute value $K$ and a random sign.",
      conf=0.75, definiendum="i.i.d. model")
prose("ClP11", "claim", "Entropy rate of the i.i.d. model",
      r"For this simple i.i.d. model the entropy rate", r"is the binary entropy function.",
      conf=0.75, assumptions=[])
byid["ClP11"]["conclusions"] = [norm(F["F39"]["statement"])]
eq("EP39", "F39", "i.i.d. model entropy rate")
prose("ClP12", "claim", "Series expansion of the i.i.d. entropy rate",
      r"Expanding eq. (\ref{entropy_iid}) in ${\epsilon }$", r"\right] {\epsilon }^k \end{equation}",
      conf=0.75, assumptions=["$p > 0$"], statement_short="Closed-form Taylor coefficients in $\\epsilon$ of $h_b[p+\\epsilon(1-2p)]$.")
byid["ClP12"]["assumptions"] = [sub("ClP12", r"$p > 0$")] if "$p > 0$" in byid["ClP12"]["statement"] else []
byid["ClP12"]["conclusions"] = [norm(F["F40"]["statement"])]
eq("EP40", "F40", "i.i.d. entropy series")
prose("ClP13", "claim", "Radius of convergence of the i.i.d. model is p/(1-2p)",
      r"The radius of convergence here is easily shown", r"increases monotonically with $p$.",
      conf=0.75, rigor="semi_formal", assumptions=[])
byid["ClP13"]["conclusions"] = [sub("ClP13", r"The radius of convergence here is easily shown to be $p/(1-2p)$")]
prose("RP12", "remark", "HMP radius expected smaller than i.i.d.",
      r"Returning to the {\it HMP}, the orders", r"may be expected to be smaller.", conf=0.7, rigor="heuristic")
prose("AP1", "algorithm", "Ratio-fit extrapolation of the radius of convergence",
      r"Since we could not derive $\rho(p)$ analytically", r"was simply estimated by $a$.",
      conf=0.75, input=["the first $11$ orders"], output=["the radius of convergence was simply estimated by $a$"],
      statement_short="Estimate $\\rho(p)$ by fitting the coefficient ratios $H^{(k)}/H^{(k+1)}$ to $(ak+b)/(k+c)$ and reading off $a$.")
ap = [step("AP1", r"We use the fact that $\rho(p)", r"(provided the limit exists).", "compute",
           "Ratio limit", "Use $\\rho(p)=\\lim_k H^{(k)}/H^{(k+1)}$", conf=0.7, order=1, typ="algorithm_step"),
      step("AP1", r"The data was fitted to a rational function", r"\sim \frac{a k + b}{k + c}, \end{equation}", "solve",
           "Rational fit of ratios", "Fit the ratios to $(ak+b)/(k+c)$", conf=0.7, order=2, typ="algorithm_step"),
      step("AP1", r"For a given fit, the radius", r"was simply estimated by $a$.", "return",
           "Read off a", "Return $a$ as the radius estimate", conf=0.7, order=3, typ="algorithm_step")]
eq("EP41", "F41", "Rational fit of coefficient ratios")
prose("ClP14", "claim", "Estimated HMP radius of convergence",
      r"The resulting prediction is given in Fig.", r"starting at zero for $p=0$, and increasing with $p$.",
      conf=0.7, rigor="numerical",
      statement_short="Fitted radius for the HMP is much smaller than the i.i.d. one but likewise starts at 0 and grows with $p$.")
prose("ClP15", "claim", "Accuracy of the 11-order series vs. Cover-Thomas bounds",
      r"We compared the analytic expansion to estimates", r"than to the lower bound of \cite{Cover}.",
      conf=0.7, rigor="numerical",
      statement_short="At $\\epsilon=0.01$ the series is accurate for $p\\gtrsim0.1$, at $\\epsilon=0.2$ only for $p>0.37$; it lies near the upper bound.")

# ======================================================== Appendix
prose("ClP16", "claim", "Entropy coefficients H^(3) to H^(11)",
      r"Orders three to eleven, as function of", r"2569380\lambda^{2}+2277)\lambda^6/{495(1-\lambda^2)^{20}} $$",
      conf=0.7, main=True, rigor="conjectural",
      statement_short="Explicit rational functions of $\\lambda=1-2p$ for $H^{(3)},\\dots,H^{(11)}$, obtained by identifying $H^{(k)}$ with the settled $C^{(k)}$.",
      tags=["entropy_rate", "series_expansion"])
abs_11 = sent(r"Using a conjecture we extend the calculation to 11th order", r"convergence of the resulting series.")
byid["ClP16"]["also_stated_at"] = [abs_11]
byid["ClP16"]["assumptions"] = []
byid["ClP16"]["conclusions"] = [sub("ClP16", r"$$ H^{(3)} =", r"/{495(1-\lambda^2)^{20}} $$")]

# ======================================================== edges
T, N_, I = "term", "named", "inferred"
E("DP1", "ClP1", 0.8, T)
E("DP2", "DP3", 0.8, T); E("DP3", "AssumP1", 0.75, T); E("AssumP1", "DP4", 0.8, I); E("DP4", "DP5", 0.8, T)
E("DP3", "EP4", 0.8, T); E("DP5", "EP4", 0.8, T); E("AssumP1", "EP4", 0.8, I); E("AssumP2", "EP4", 0.85, I)
E("DP3", "DP6", 0.75, T); E("DP6", "DP7", 0.75, T); E("DP7", "AssumP3", 0.8, T); E("DP7", "AssumP4", 0.8, T)
E("DP6", "EP7", 0.8, T); E("AssumP3", "EP7", 0.8, I); E("DP7", "EP7", 0.75, T)
E("EP7", "EP8", 0.8, I); E("EP4", "EP8", 0.8, I)
E("DP6", "DP8", 0.8, T); E("DP8", "DP9", 0.85, T)
E("DP5", "DP10", 0.8, T); E("DP7", "DP10", 0.8, T); E("AssumP4", "DP10", 0.7, I)
E("DP10", "TP1", 0.85, T); E("DP3", "TP1", 0.75, T); E("DP6", "TP1", 0.75, T); E("EP8", "TP1", 0.8, I)
E("DP10", "DP11", 0.85, T); E("TP1", "DP11", 0.8, I)
E("DP11", "ClP2", 0.85, T); E("TP1", "ClP2", 0.75, T)
E("ClP2", "RP3", 0.85, N_); E("DP10", "RP3", 0.75, T)
E("RP3", "OpenP2", 0.8, N_)
E("DP9", "RP4", 0.75, T); E("DP6", "RP4", 0.7, T)
E("DP10", "RP5", 0.8, T); E("DP7", "RP5", 0.75, T)
E("DP11", "EP18", 0.8, T); E("TP1", "EP18", 0.75, T); E("DP9", "EP18", 0.8, T); E("ClP2", "EP18", 0.75, I)
E("DP11", "PP1", 0.85, T); E("TP1", "PP1", 0.8, T); E("DP10", "PP1", 0.8, T)
E("PP1", "ClP3", typ="proves", conf=0.8, basis=I)
E("DP9", "ClP3", 0.8, T); E("DP5", "ClP3", 0.8, T); E("DP7", "ClP3", 0.8, T)
# inside PP1
E(p1[1], "PSP4", 0.75, I); E(p1[2], p1[3], 0.8, I); E(p1[3], p1[4], 0.8, I); E(p1[3], p1[5], 0.8, I)
E(p1[4], p1[6], 0.8, I); E(p1[5], p1[6], 0.8, I); E(p1[0], p1[6], 0.75, I)
for t in ("DP4", "DP5", "EP4", "DP7", "EP7", "DP10", "TP1", "DP11"):
    E("DP2", t, 0.75, T)
# section 4
E("DP9", "DP12", 0.85, T)
E("DP12", "ClP4", 0.85, T); E("DP9", "ClP4", 0.8, T)
E("DP12", "TP2", 0.85, T)
E("DP12", "ClP5", 0.85, T); E("DP11", "ClP5", 0.8, T); E("DP5", "ClP5", 0.75, T); E("DP7", "ClP5", 0.75, T)
E("DP13", "ClP6", 0.9, N_); E("ClP5", "DP13", 0.85, T); E("DP11", "DP13", 0.7, T)
E("ClP6", "DP14", 0.9, N_); E("DP12", "DP14", 0.85, T)
E("ClP6", "ExP1", typ="illustrates", conf=0.9, basis=N_); E("DP13", "ExP1", 0.8, T)
E("ClP6", "RP7", 0.75, I); E("DP14", "RP7", 0.7, T)
E("DP14", "TP3", 0.85, T); E("ClP3", "TP3", 0.75, T)
E("DP14", "ClP7", 0.85, T); E("RP7", "ClP7", 0.85, N_)
E("DP14", "CnjP1", 0.85, T); E("ClP7", "CnjP1", 0.85, N_, mention=True)
E("ClP4", "ClP8", 0.85, N_); E("DP14", "ClP8", 0.85, T); E("ClP3", "ClP8", 0.75, T)
E("RP11", "ClP8", 0.65, N_)
E("CnjP1", "ClP9", 0.9, N_); E("ClP8", "ClP9", 0.85, N_)
E("TP3", "RP8", 0.8, I); E("ClP7", "RP8", 0.75, I); E("CnjP1", "RP8", 0.9, N_, mention=True)
E("DP5", "DP15", 0.75, T); E("ClP9", "DP15", 0.75, I)
E("ClP3", "RP9", 0.8, T); E("CnjP1", "RP9", 0.9, N_, mention=True)
E("DP15", "RP10", 0.85, T); E("DP4", "RP10", 0.75, T); E("ClP16", "RP10", 0.75, I)
E("RP10", "CnjP2", 0.9, N_, mention=True); E("DP15", "CnjP2", 0.85, T); E("ClP3", "CnjP2", 0.75, T)
E("ClP16", "CnjP2", 0.85, N_)
# section 5
E("DP9", "ClP10", 0.75, T); E("DP5", "ClP10", 0.75, T); E("DP7", "ClP10", 0.75, T)
E("ClP10", "RP11", 0.8, I)
E("ClP3", "DP16", 0.75, T)
E("DP10", "DP17", 0.8, T)
E("DP17", "ClP11", 0.85, T); E("DP5", "ClP11", 0.75, T); E("DP7", "ClP11", 0.75, T)
E("ClP12", "ClP13", 0.85, N_); E("DP16", "ClP13", 0.8, T)
E("ClP12", "RP12", 0.8, N_); E("ClP16", "RP12", 0.7, I); E("DP16", "RP12", 0.75, T)
E("DP16", "AP1", 0.85, T); E("DP17", "AP1", 0.8, T); E("DP17", "RP12", 0.8, T); E("DP17", "ClP14", 0.8, T); E("ClP16", "AP1", 0.85, N_); E("ClP12", ap[1], 0.8, N_)
E(ap[0], ap[1], 0.75, I); E(ap[1], ap[2], 0.8, I)
E("AP1", "ClP14", 0.85, N_); E("ClP13", "ClP14", 0.8, I)
E("ClP16", "ClP15", 0.8, I); E("TP2", "ClP15", 0.8, T); E("DP16", "ClP15", 0.75, T)
# appendix
E("ClP9", "ClP16", 0.85, N_); E("DP15", "ClP16", 0.85, T); E("RP7", "ClP16", 0.8, I)

# ======================================================== metadata, finalize, write
graph = {"metadata": {
    "title": "The Entropy of a Binary Hidden Markov Process",
    "arxiv_id": "cs/0507060",
    "authors": ["O. Zuk", "I. Kanter", "E. Domany"],
    "year": 2005,
    "annotator": "agent-extraction",
    "model": "claude-opus-5-5",
    "effort": "default",
    "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
    "extraction_date": "2026-11-05",
    "rigor_nonformal_count": sum("rigor" in n for n in nodes),
    "paper_style": ["derivation", "computational"],
    "extraction_notes": [
        {"category": "type_uncertain", "nodes": ["DP5"],
         "note": "Symmetric process P_{+,-}=P_{-,+}=p is both a modelling assumption and the introduction of p; typed definition because p is used throughout."},
        {"category": "type_uncertain", "nodes": ["TP1"],
         "note": "The Ising (Boltzmann-chain) form of Pr(R,S) is a direct rewriting, cited to Saul-Jordan and MacKay; typed external theorem per the cited-result rule, claim would also fit."},
        {"category": "type_uncertain", "nodes": ["ClP5"],
         "note": "Eq. (33) re-expresses Z(R) in p, epsilon; it is really Q(R) (it already contains the normalisation A), so it is a claim about a re-used symbol rather than a new definition."},
        {"category": "boundary_uncertain", "nodes": ["PP1", "ClP3"],
         "note": "Section 3 has no proof environment: the derivation from 'A few technical points' to the colon before (28) is the proof; (28)-(30) form the claimed result. The derivation omits the actual summations ('straightforward, albeit tedious'), hence semi_formal."},
        {"category": "unexpected_construct", "nodes": ["ClP16"],
         "note": "The coefficients H^(3)..H^(11) are only in unnumbered $$ displays in the Appendix; emitted as one conjectural claim spanning the Appendix list."},
        {"category": "not_extracted", "nodes": [],
         "note": "Motivational introduction (communication, compression, error correction), the Omega_S paragraph, captions of the four figures, and the radius-of-convergence motivation sentence have no nodes."},
    ],
    "extraction_comment": "Results here are derivations and symbolic/numerical computations rather than theorem-proof; only orders 0-2 are derived, orders 3-11 rest on the settling conjecture (CnjP1).",
}, "nodes": nodes, "edges": edges}
report = finalize(graph, read_tex(TEX))
for k in ("matched_to_environment", "labels_filled"):
    print(k, report[k])
print("proves_added", len(report["proves_added"]), "ref_uses_added", len(report["ref_uses_added"]))
print("ref_backward", report["ref_backward"])
print("ERRORS", *report["errors"], sep="\n  ")
print("WARNINGS", *report["warnings"], sep="\n  ")
assert not report["errors"], report["errors"]
json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
print("wrote", OUT, len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
