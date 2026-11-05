#!/usr/bin/env python3
"""Build the v7 LLM extraction of OpenAI, 'A superquadratic separation between sensitivity and
block sensitivity' (OpenAI math release, OAI-132).
Nodes, types, spans and edges were chosen by reading the paper; this script only slices spans
out of the prepared source, assembles the JSON and runs the finishing step."""
import json, re, sys
REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize
from latex_facts import read_tex

SCR = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_132"
BASE = REPO + "/corpus/case_studies/ai/openai_132_sensitivity_separation"
TEX = BASE + "/arxiv_src/paper.tex"
OUT = BASE + "/openai_132_sensitivity_separation.json"
facts = json.load(open(SCR + "/facts.json"))
S = facts["source"]
F = {f["id"]: f for f in facts["facts"]}
SECS = [s for s in facts["sections"] if s.get("inside") is None]


def norm(t):
    return re.sub(r"\s+", " ", t).strip()


def rx(t):
    return r"\s*".join(re.escape(w) for w in norm(t).split(" ")).replace(r"\ ", r"\s*")


def find(t, lo=0, hi=None):
    m = re.compile(rx(t)).search(S, lo, hi if hi is not None else len(S))
    assert m, ("not found", t)
    return m.start(), m.end()


def sec_at(pos):
    s = max((x for x in SECS if x["start"] <= pos), key=lambda x: x["start"])
    return f"{s['number']} {s['title']}"


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


def prose(nid, typ, name, a, b, after=0, origin="paper", conf=0.75, **kw):
    i, _ = find(a, after)
    _, j = find(b, i)
    return add(nid, typ, name, norm(S[i:j]), i, j, origin, conf, **kw)


def sub(nid, a, b=None):
    st = byid[nid]["statement"]
    a = norm(a)
    i = st.index(a)
    if b is None:
        return a
    j = st.index(norm(b), i) + len(norm(b))
    return st[i:j]


def fsub(fid, a, b=None):
    st = norm(F[fid]["statement"])
    a = norm(a)
    i = st.index(a)
    if b is None:
        return a
    j = st.index(norm(b), i) + len(norm(b))
    return st[i:j]


def sent(a, b):
    """verbatim span of the source from a through b (for also_stated_at)"""
    i, _ = find(a); _, j = find(b, i)
    return norm(S[i:j])


NPS = [0]


def step(parent, a, b, sc, name, short=None, conf=0.75, order=None):
    lo, hi = POS[parent]
    i, _ = find(a, lo, hi)
    _, j = find(b, i, hi)
    NPS[0] += 1
    sid = f"PSP{NPS[0]}"
    root = parent
    while byid[root]["type"] == "proof_step":
        root = byid[root]["parent_id"]
    add(sid, "proof_step", name, norm(S[i:j]), i, j, byid[root]["origin"], conf,
        parent_id=parent, step_order=order, subclass=sc, statement_short=short or name,
        section=byid[root]["section"])
    return sid


def steps(parent, spec):
    out = []
    for k, sp in enumerate(spec):
        a, b, sc, nm = sp[:4]
        short = sp[4] if len(sp) > 4 else None
        conf = sp[5] if len(sp) > 5 else 0.75
        out.append(step(parent, a, b, sc, nm, short, conf, order=k + 1))
    return out


def E(s, t, typ="uses", conf=0.8, basis="inferred", **kw):
    e = {"source": s, "target": t, "type": typ, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)


STD = "standard (uncited)"

# ======================================================== abstract copies (no nodes)
ABS_MAIN = sent(r"We disprove the quadratic strengthening", r"constant multiple of sensitivity squared.")
ABS_COR = sent(r"In fact, for some fixed", r"\(\operatorname{bs}(f)\ge s(f)^\alpha\).")
INTRO_MAIN = sent(r"We construct total Boolean functions for which the second", r"square of the first.")

# ======================================================== 1 Introduction
prose("DP1", "definition", "[n] notation", r"For a positive integer \(n\), write", r"\([n]=\{1,\ldots,n\}\).",
      origin="external", origin_citation=STD, conf=0.85, definiendum="$[n]$")
prose("DP2", "definition", "Flipped input x^B", r"If \(x\in\{0,1\}^n\) and \(B\subseteq[n]\)", r"\(x^{\{a\}}\) to \(x^a\).",
      origin="external", origin_citation=STD, conf=0.85, definiendum=["$x^B$", "$x^a$"],
      statement_short="$x^B$ is $x$ with the coordinates in $B$ flipped; $x^a$ for a single coordinate.")
prose("DP3", "definition", "Sensitivity", r"For a total Boolean function \(f:\{0,1\}^n\to\{0,1\}\), define",
      r"s(f)=\max_x s(f,x). \]", origin="external", origin_citation=STD, conf=0.85,
      definiendum=["$s(f,x)$", "$s(f)$"],
      statement_short="Sensitivity: number of single bits whose flip changes $f(x)$, maximized over $x$.",
      tags=["boolean_functions", "complexity_measure"])
prose("DP4", "definition", "Block sensitivity", r"Its block sensitivity \(\operatorname{bs}(f,x)\) is the largest",
      r"\(\operatorname{bs}(f)=\max_x\operatorname{bs}(f,x)\).", origin="external", origin_citation="Nisan 1989",
      conf=0.85, definiendum=["block sensitivity", "$\\operatorname{bs}(f,x)$", "$\\operatorname{bs}(f)$"],
      genus="largest number of pairwise disjoint nonempty sets",
      differentia=["\\(f(x^{B_j})\\ne f(x)\\) for every \\(j\\)"],
      statement_short="Block sensitivity: maximum number of disjoint blocks each of whose flip changes $f(x)$, maximized over $x$.",
      tags=["boolean_functions", "complexity_measure"])
prose("CnjP1", "conjecture", "Sensitivity Conjecture", r"The Sensitivity Conjecture asked whether",
      r"uniformly over the number of inputs and the function.", origin="external",
      origin_citation="Nisan 1989; Nisan & Szegedy 1994", conf=0.85,
      assumptions=[], conclusions=["block sensitivity is bounded by a polynomial in sensitivity, uniformly over the number of inputs and the function"],
      statement_short="Block sensitivity is polynomially bounded in sensitivity.", tags=["sensitivity_conjecture"])
prose("CnjP2", "conjecture", "Quadratic sensitivity conjecture (Nisan-Szegedy)", r"Nisan and Szegedy studied the problem",
      r"\cite[Section~4]{NisanSzegedy1994}.", origin="external", origin_citation="Nisan & Szegedy 1994", conf=0.85,
      assumptions=[], conclusions=["the quadratic inequality \\(\\operatorname{bs}(f)\\le s(f)^2\\)"],
      statement_short="Nisan and Szegedy suggested $\\mathrm{bs}(f)\\le s(f)^2$ for all Boolean functions.",
      tags=["sensitivity_conjecture"])
prose("TP1", "theorem", "Rubinstein's quadratic separation", r"Rubinstein's construction \cite{Rubinstein1995}",
      r"would need degree at least two.", origin="external", origin_citation="Rubinstein 1995", conf=0.8,
      assumptions=[], conclusions=["a polynomial upper bound would need degree at least two"],
      tags=["separation", "lower_bound"])
prose("TP2", "theorem", "Virza and Ambainis-Sun quadratic separations", r"Virza improved the separation",
      r"\cite[Theorem~1]{AmbainisSun2011}.", origin="external", origin_citation="Virza 2011; Ambainis & Sun 2011",
      conf=0.8, assumptions=[],
      conclusions=["\\(\\operatorname{bs}(f)=\\tfrac12s(f)^2+\\tfrac12s(f)\\)",
                   "\\[ \\operatorname{bs}(f)=\\frac23s(f)^2-\\frac13s(f) \\]"],
      statement_short="Functions with $\\mathrm{bs}=\\frac12 s^2+\\frac12 s$ (Virza) and $\\mathrm{bs}=\\frac23 s^2-\\frac13 s$ (Ambainis-Sun).",
      tags=["separation", "lower_bound"])
prose("TP3", "theorem", "Huang's sensitivity theorem (bs <= s^4)", r"Huang resolved the polynomial conjecture in 2019.",
      r"\cite[Theorem~1.5]{Huang2019}.", origin="external", origin_citation="Huang 2019; Tal 2013", conf=0.85,
      assumptions=["for every total Boolean function"], conclusions=["\\(\\operatorname{bs}(f)\\le s(f)^4\\)"],
      statement_short="Huang's degree bound plus Tal's refinement give $\\mathrm{bs}(f)\\le s(f)^4$.",
      tags=["sensitivity_conjecture", "upper_bound"])
prose("TP4", "theorem", "Wellens' constant improvement", r"Wellens later improved its leading constant,",
      r"\cite[Corollary~4.2]{Wellens2022}.", origin="external", origin_citation="Wellens 2022", conf=0.85,
      assumptions=[], conclusions=["\\(\\operatorname{bs}(f)\\le\\sqrt{2/3}\\,s(f)^4+1\\)"],
      tags=["sensitivity_conjecture", "upper_bound"])
env("TP5", "F1", "theorem", "Superquadratic separation of sensitivity and block sensitivity", main=True,
    assumptions=[], conclusions=[fsub("F1", r"there are a positive integer", r"\operatorname{bs}(f)>C\,s(f)^2. \]"),
                                 fsub("F1", r"the construction below gives", r"\frac{2^d}{4(d+2)^2}. \]")],
    parts=[{"assumptions": [fsub("F1", r"For every real \(C>0\)")],
            "conclusions": [fsub("F1", r"there are a positive integer", r"\operatorname{bs}(f)>C\,s(f)^2. \]")]},
           {"assumptions": [fsub("F1", r"for every integer \(d\ge1\)")],
            "conclusions": [fsub("F1", r"the construction below gives", r"\frac{2^d}{4(d+2)^2}. \]")]}],
    also_stated_at=[ABS_MAIN, INTRO_MAIN],
    statement_short="No constant $C$ gives $\\mathrm{bs}(f)\\le C s(f)^2$: depth-$d$ construction has ratio $\\ge 2^d/(4(d+2)^2)$.",
    tags=["separation", "sensitivity_conjecture", "boolean_functions"])
byid["TP5"]["assumptions"] = [fsub("F1", r"For every real \(C>0\)"), fsub("F1", r"for every integer \(d\ge1\)")]
prose("DP5", "definition", "Sensitivity graph", r"The sensitivity graph joins adjacent cube inputs",
      r"exactly when the function changes value.", origin="external", origin_citation=STD, conf=0.8,
      definiendum="sensitivity graph")
prose("DP6", "definition", "Spectral sensitivity", r"Its maximum degree is \(s(f)\); spectral sensitivity",
      r"\cite{AaronsonEtAl2021}.", origin="external", origin_citation="Aaronson et al. 2021", conf=0.8,
      definiendum=["spectral sensitivity", "$\\lambda(f)$"], genus="operator norm",
      differentia=["of its adjacency matrix"])
prose("RP1", "remark", "Spectral sensitivity does not give the separation", r"Since \(\lambda(f)\le s(f)\), a lower bound",
      r"without a spectral input.", conf=0.75,
      statement_short="Since $\\lambda(f)\\le s(f)$, a $\\mathrm{bs}/\\lambda^2$ separation does not imply Theorem 1.1; the paper argues directly.")
prose("PP1", "proof", "Proof sketch of Theorem 1.1 (construction and strategy)", r"We recursively construct nested families",
      r"\cite[Section~4, Lemma~1]{AmbainisSun2011}.", conf=0.7, rigor="semi_formal",
      statement_short="Sketch: recursive tournament-gated nested predicates; joint sensitivities of predicate pairs control ordinary sensitivity, OR of copies balances.",
      proof_strategy=["construction"])
prose("PP2", "proof", "Proof sketch of Corollary 4.3 (amplification by composition)", r"Finally, Lemma~\ref{lem:composition} amplifies",
      r"power separation of Corollary~\ref{cor:power-separation}.", conf=0.7, rigor="semi_formal",
      statement_short="Sketch: compose a seed with $\\mathrm{bs}(f,0)>s(f)^2$ with itself to get a power separation.",
      proof_strategy=["construction"])
prose("TP6", "theorem", "Ambainis-Prusis amplification observation", r"Ambainis and Pr\={u}sis explicitly",
      r"\cite[Section~1]{AmbainisPrusis2014}.", origin="external", origin_citation="Ambainis & Prusis 2014", conf=0.7,
      assumptions=["a seed with block sensitivity greater than sensitivity squared"],
      conclusions=["would yield a superquadratic power separation by iteration"], tags=["composition", "separation"])

# ======================================================== 2 construction
prose("DP7", "definition", "Construction parameters L, k, r, t", r"Fix integers \(d\ge1\) and \(M\ge3\), and put",
      r"\qquad t=16. \]", conf=0.85, definiendum=["$L$", "$k$", "$r$", "$t$"],
      statement_short="Parameters: depth $d$, size $M$, $L=d+2$, $k=2M^2+1$ rows, $r=\\lceil\\sqrt M\\rceil$ positions, $t=16$.")
prose("DP8", "definition", "Tournament", r"A tournament is an orientation of every pair",
      r"exactly one of \(i\to j\) and \(j\to i\) holds.", origin="external", origin_citation=STD, conf=0.9,
      definiendum="tournament", genus="orientation", differentia=["of every pair of distinct vertices"])
prose("DP9", "definition", "Regular tournament on [k]", r"Use a tournament on \([k]\) in which",
      r"every vertex has outdegree \(M^2\).", conf=0.75, definiendum="tournament on $[k]$",
      genus="tournament", differentia=["every vertex has outdegree \\(M^2\\)"])
prose("ExP1", "example", "Cyclic regular tournament", r"For example, place the vertices cyclically",
      r"to the next \(M^2\) vertices.", conf=0.85)
env("LP1", "F2", "lemma", "Random labelling lemma", assumptions=[],
    conclusions=[fsub("F2", r"there is no set \(I\subseteq[k]\)", r"within }I. \]")],
    statement_short="Edge labels $a(i,j)\\in[r]$ exist with no $t$-set $I$ whose in-edge labels all agree with one position $m_j$ per vertex.",
    tags=["existence", "randomized", "tournament"])
env("PP3", "F3", "proof", "Proof of Lemma 2.1", statement_short="Probabilistic method: union bound over $k^t r^t$ configurations, each of probability $r^{-\\binom t2}$.",
    proof_strategy=["probabilistic"])
prose("DP10", "definition", "Level parameters H_l and N_l", r"For \(0\le\ell\le d\), set",
      r"N_\ell=LM(kr)^\ell. \]", conf=0.85, definiendum=["$H_\\ell$", "$N_\\ell$"])
prose("DP11", "definition", "Nested predicates P_{l,q}", r"We construct predicates \(P_{\ell,q}",
      r"nesting concerns the predicate index, not the input bits.", conf=0.8,
      definiendum=["$P_{\\ell,q}$", "nested"],
      statement_short="Predicates $P_{\\ell,q}$, $1\\le q\\le H_\\ell$, on $N_\\ell$ bits with $P_{\\ell,1}\\ge\\cdots\\ge P_{\\ell,H_\\ell}$ pointwise.")
prose("DP12", "definition", "Blocks E_j", r"Partition \([LM]\) into \(M\) blocks", r"each of size \(L\).", conf=0.8,
      definiendum="$E_j$")
prose("DP13", "definition", "Centres z_j", r"Let \(z_j\) be the string", r"one precisely on \(E_j\).", conf=0.8,
      definiendum="$z_j$")
prose("DP14", "definition", "Initial predicates P_{0,q} (Hamming balls)", r"Write \(\operatorname{dist}(x,z)\) for Hamming",
      r"P_{0,q}(x)=\mathbf1\{D(x)\le H_0-q\}. \]", conf=0.85,
      definiendum=["$\\operatorname{dist}(x,z)$", "$D(x)$", "$P_{0,q}$"],
      statement_short="$D(x)$ is the distance to the nearest centre; $P_{0,q}$ indicates the union of balls of radius $H_0-q$.")
prose("ClP1", "claim", "Initial predicates are nested", r"These predicates are nested. Their radii",
      r"distinct centres have distance \(2L=2d+4\).", conf=0.7, assumptions=[],
      conclusions=["These predicates are nested.", "distinct centres have distance \\(2L=2d+4\\)"])
prose("DP15", "definition", "Children x_{j,c}", r"Suppose \(1\le\ell\le d\). Partition the input",
      r"each with \(r\) positions \(c\in[r]\).", conf=0.8, definiendum="$x_{j,c}$",
      statement_short="At level $\\ell$ the input splits into $kr$ child inputs in $k$ rows of $r$ positions.")
prose("DP16", "definition", "Level shorthand H and Q", r"For this level put \(H=H_\ell\)", r"\(Q=H+1=H_{\ell-1}\).",
      conf=0.8, definiendum=["$H$", "$Q$"])
prose("DP17", "definition", "Clause i at index q", r"For \(q\in[H]\), let clause \(i\) at index \(q\) assert",
      r"\end{aligned} \end{equation}", conf=0.8, definiendum="clause $i$ at index $q$",
      statement_short="Clause $i$: strongest child predicate accepts every child in row $i$, and $P_{\\ell-1,Q-q}$ rejects child $a(i,j)$ of each out-neighbour row $j$.")
prose("DP18", "definition", "Target and gate conditions", r"Call the first line its \emph{target conditions}",
      r"its \emph{gate conditions}.", conf=0.85, definiendum=["target conditions", "gate conditions"])
prose("DP19", "definition", "Recursive predicate P_{l,q}", r"Define \(P_{\ell,q}(x)=1\) if at least",
      r"and zero otherwise.", conf=0.85, definiendum="$P_{\\ell,q}$",
)
prose("ClP2", "claim", "Indices are valid", r"All indices are valid:", r"\(1\le Q-q\le H<Q\).", conf=0.65,
      assumptions=[], conclusions=["\\(1\\le Q-q\\le H<Q\\)"])
prose("ClP3", "claim", "Conditions of a clause use distinct children", r"Within a single clause, all",
      r"use distinct children.", conf=0.75, assumptions=[], conclusions=["all \\(r+M^2\\) conditions use distinct children"])
prose("PP4", "proof", "Proof that clause conditions use distinct children", r"Indeed, targets use row \(i\)",
      r"only one edge from \(i\) to any given row.", conf=0.75,
      statement_short="Direct: targets lie in row $i$, gates in other rows, one edge per row pair.", proof_strategy=["direct"])
prose("ClP4", "claim", "One bit affects at most one condition of a clause", r"Consequently a change of one raw input bit",
      r"at most one condition of that clause.", conf=0.75, assumptions=[],
      conclusions=["a change of one raw input bit can affect at most one condition of that clause"])
prose("PP5", "proof", "Proof that the recursive predicates are nested", r"By induction, increasing \(q\)",
      r"Targets do not change.", conf=0.75,
      statement_short="Induction on $\\ell$: raising $q$ lowers the gate index, strengthening every gate; targets are unchanged.",
      proof_strategy=["induction"])
prose("ClP5", "claim", "Recursive predicates are nested", r"Thus each clause, and hence each \(P_{\ell,q}\)",
      r"is nested as asserted.", conf=0.75, assumptions=[],
      conclusions=["each clause, and hence each \\(P_{\\ell,q}\\), is nested as asserted"])
prose("ClP6", "claim", "Dimension recursion N_l = kr N_{l-1}", r"This recursion defines total Boolean functions",
      r"\(N_\ell=krN_{\ell-1}\) bits.", conf=0.65, assumptions=[],
      conclusions=["This recursion defines total Boolean functions on exactly \\(N_\\ell=krN_{\\ell-1}\\) bits."])
prose("DP20", "definition", "Sensitivity profile S_{l,b}", r"For \(b\in\{0,1\}\), define \[ S_{\ell,b}",
      r"P_{\ell,q}(x^a)=1-b\}\bigr|. \]", conf=0.85, definiendum="$S_{\\ell,b}$",
      statement_short="$S_{\\ell,b}$: maximum over $q$ and inputs with $P_{\\ell,q}=b$ of the number of bits flipping $P_{\\ell,q}$.")
prose("DP21", "definition", "Joint sensitivity profile J_{l,b}", r"We also keep track of simultaneous changes",
      r"P_{\ell,q'}(x^a)=1-b\}\bigr|. \]", conf=0.85, definiendum="$J_{\\ell,b}$",
      statement_short="$J_{\\ell,b}$: maximum number of bits that flip two distinct predicates $P_{\\ell,q},P_{\\ell,q'}$ simultaneously from $b$.")
prose("DP22", "definition", "Empty-maximum convention", r"A maximum over no cases is defined to be zero;",
      r"since \(H_d=1\).", conf=0.8, definiendum="maximum over no cases")
prose("RP2", "remark", "Joint sensitivity uses one input and one bit", r"The two predicates in the definition of",
      r"changed by the same raw input bit.", conf=0.7)
env("LP2", "F5", "lemma", "Initial sensitivity profiles", assumptions=[],
    conclusions=[fsub("F5", r"S_{0,0}\le L,", r"J_{0,0}=J_{0,1}=0.")],
    statement_short="At level 0: $S_{0,0}\\le L$, $S_{0,1}\\le LM$, and both joint sensitivities vanish.", tags=["bound"])
env("PP6", "F7", "proof", "Proof of Lemma 2.2",
    statement_short="Separated Hamming balls: a successful flip moves toward the unique nearby centre; $D$ is 1-Lipschitz so no bit crosses two radii.",
    proof_strategy=["direct", "geometric"])
env("LP3", "F8", "lemma", "Disjoint sensitive blocks at zero",
    assumptions=[fsub("F8", r"At every level \(0\le\ell\le d\)")],
    conclusions=[fsub("F8", r"all predicates are zero at the all-zero input."),
                 fsub("F8", r"There are \(Mk^\ell\) pairwise disjoint", r"every predicate at that level equal to one.")],
    statement_short="All predicates vanish at $0$, and $Mk^\\ell$ disjoint blocks of size $Lr^\\ell$ each turn every level-$\\ell$ predicate on.",
    tags=["lower_bound", "block_sensitivity"])
env("PP7", "F9", "proof", "Proof of Lemma 2.3",
    statement_short="Induction on $\\ell$: unions over a row of copies of a lower-level block satisfy that row's clause.",
    proof_strategy=["induction", "construction"])

# ======================================================== 3 recurrences
env("PrP1", "F10", "proposition", "Sensitivity recurrences",
    assumptions=[fsub("F10", r"For $1\leq \ell\leq d$, write", r"$J'_b=J_{\ell-1,b}$.")],
    conclusions=[fsub("F10", r"\begin{equation}", r"\end{equation}")],
    statement_short="Four coupled recurrences bounding $S_{\\ell,b}$ and $J_{\\ell,b}$ by level-$(\\ell-1)$ profiles.",
    tags=["bound", "recurrence"])
env("PP8", "F12", "proof", "Proof of Proposition 3.1",
    statement_short="Case analysis of one-bit transitions per clause with union bounds. At a zero, the labelling lemma caps target-failing clauses below $t$ and the tournament caps gate-failing clauses at 3.",
    proof_strategy=["case_analysis", "direct"])

# ======================================================== 4 quantitative + separation
env("LP4", "F13", "lemma", "Quantitative sensitivity profiles",
    assumptions=[fsub("F13", r"$d\geq 1$ and $M\geq 9^{d+1}$"), fsub("F13", r"For every $0\leq\ell\leq d$ and $b\in\{0,1\}$")],
    conclusions=[fsub("F13", r"\[ S_{\ell,b}\leq 2L M^{\ell+b}. \]")],
    statement_short="For $M\\ge 9^{d+1}$, $S_{\\ell,b}\\le 2LM^{\\ell+b}$ at every level.", tags=["bound"])
env("PP9", "F14", "proof", "Proof of Lemma 4.1",
    statement_short="Normalize the recurrences by $M^{\\ell+b}$ and compare with linear sequences $U_\\ell,V_\\ell$. A simultaneous induction keeps $U_\\ell\\le 2L$ since $\\epsilon\\le 2/3^{d+1}$.",
    proof_strategy=["induction", "algebraic_manipulation"])
env("PP10", "F20", "proof", "Proof of Theorem 1.1",
    statement_short="Construction: OR of $M$ copies of $P_{d,1}$; $s(f)\\le 2LM^{d+1}$, $\\mathrm{bs}(f,0)\\ge M^2k^d$, then let $d\\to\\infty$.",
    proof_strategy=["construction"])
env("LP5", "F25", "lemma", "Disjoint composition bounds",
    origin="external", origin_citation="Tal 2013; standard (composition facts)",
    assumptions=[fsub("F25", r"Let $f:\{0,1\}^a\to\{0,1\}$ and", r"be total Boolean functions."), fsub("F25", r"If $g(0)=0$")],
    conclusions=[fsub("F25", r"\[ s(f\circ g)\leq s(f)s(g). \]"),
                 fsub("F25", r"$(f\circ g)(0)=f(0)$ and", r"\operatorname{bs}(f,0)\operatorname{bs}(g,0). \]"),
                 fsub("F25", r"any disjoint families of $p$ and $q$ blocks", r"sensitive at zero for $f\circ g$.")],
    parts=[{"assumptions": [], "conclusions": [fsub("F25", r"\[ s(f\circ g)\leq s(f)s(g). \]")]},
           {"assumptions": [fsub("F25", r"If $g(0)=0$")],
            "conclusions": [fsub("F25", r"$(f\circ g)(0)=f(0)$ and", r"\operatorname{bs}(f,0)\operatorname{bs}(g,0). \]"),
                            fsub("F25", r"any disjoint families of $p$ and $q$ blocks", r"sensitive at zero for $f\circ g$.")]}],
    statement_short="Sensitivity is submultiplicative under disjoint composition; if $g(0)=0$, block sensitivity at zero is supermultiplicative.",
    tags=["composition", "boolean_functions"])
prose("DP23", "definition", "Disjoint composition", r"Their disjoint composition is the function on $ab$ bits",
      r"x_i\in\{0,1\}^b. \]", origin="external", origin_citation=STD, conf=0.8,
      definiendum=["disjoint composition", "$f\\circ g$"], genus="function on $ab$ bits")
env("PP11", "F26", "proof", "Proof of Lemma 4.2",
    statement_short="Direct: a bit is sensitive for $f\\circ g$ iff sensitive for its child and the child's coordinate for $f$; product blocks $C_i\\times D_j$.",
    proof_strategy=["direct", "construction"])
env("CP1", "F27", "corollary", "Fixed-exponent power separation", main=True,
    assumptions=[],
    conclusions=[fsub("F27", r"There exist a real number $\alpha>2$", r"\longrightarrow\infty. \]")],
    also_stated_at=[ABS_COR],
    statement_short="Some fixed $\\alpha>2$ and functions $F_m$ with $\\mathrm{bs}(F_m,0)\\ge s(F_m)^\\alpha$ and unbounded block sensitivity.",
    tags=["separation", "composition"])
env("PP12", "F28", "proof", "Proof of Corollary 4.3",
    statement_short="Take the $d=9$ seed with $s\\le A$, $\\mathrm{bs}(\\cdot,0)\\ge B>A^2$, iterate disjoint composition, $\\alpha=\\log B/\\log A$.",
    proof_strategy=["construction", "induction"])

EQ = [("EP1", "F4", "Clause conditions (1)"), ("EP2", "F6", "Initial profile bounds (2)"),
      ("EP3", "F11", "Sensitivity recurrences (3)"), ("EP4", "F16", "Normalized recurrences (4)"),
      ("EP5", "F17", "Choice of epsilon (5)"), ("EP6", "F18", "Comparison bounds (6)"),
      ("EP7", "F21", "Final dimension (7)"), ("EP8", "F22", "Final sensitivity bound (8)"),
      ("EP9", "F23", "Final block sensitivity bound (9)"), ("EP10", "F24", "Ratio separation (10)")]
for nid, fid, nm in EQ:
    env(nid, fid, "equation", nm)

# ======================================================== proof steps
# PP1 sketch: one step per paragraph
steps("PP1", [
    (r"We recursively construct nested families", r"produces a new nested family.", "introduce_variable",
     "Recursive tournament-gated construction"),
    (r"Fix one parent predicate at a rejecting input", r"even in the possible exceptional clause.", "bound_estimate",
     "One-bit repairs fail one condition; joint sensitivities needed"),
    (r"The initial family consists of indicators", r"\cite[Section~4, Lemma~1]{AmbainisSun2011}.", "conclude",
     "Base family, normalization and OR balancing")])
# PP3 (Lemma 2.1)
p3 = steps("PP3", [
    (r"Choose all edge labels independently", r"is \(r^{-\binom t2}\).", "introduce_variable",
     "Random labels; per-configuration probability"),
    (r"There are at most \(k^t r^t\) choices", r"and \(M\ge3\).", "bound_estimate", "Union bound below 1"),
    (r"Thus a labelling with the required property exists.", r"Thus a labelling with the required property exists.",
     "conclude", "A good labelling exists")])
# PP6 (Lemma 2.2)
p6 = steps("PP6", [
    (r"Fix a predicate of radius", r"at distance exactly \(R+1\) from \(x\).", "introduce_variable",
     "A successful flip reaches distance R+1 of a centre"),
    (r"There is at most one centre within distance", r"at most \(2d+2<2L\).", "bound_estimate", "At most one nearby centre"),
    (r"Thus every successful bit flip", r"\le L\) possibilities.", "bound_estimate", "S_{0,0} <= L"),
    (r"The bound on \(S_{0,1}\) is simply", r"the number \(LM\) of input bits.", "bound_estimate", "S_{0,1} <= LM"),
    (r"For adjacent inputs \(x,y\)", r"Hence \(|D(x)-D(y)|\le1\).", "bound_estimate", "D is 1-Lipschitz"),
    (r"To change both predicates with distinct", r"to change by at least two.", "other",
     "A joint change needs D to move by two"),
    (r"Both joint sensitivities are therefore", r"zero.", "conclude", "Joint sensitivities vanish")])
# PP7 (Lemma 2.3)
P7a = step("PP7", r"At level zero, \(D(0)=L>d\)", r"because \(0^{E_j}=z_j\).", "induction_step", "Base case: blocks E_j",
           order=1)
P7b = step("PP7", r"Suppose the claim holds at level", r"each of size \(r\cdot Lr^{\ell-1}=Lr^\ell\), as required.",
           "induction_step", "Inductive step: row unions of lower blocks", order=2)
p7 = steps(P7b, [
    (r"Suppose the claim holds at level", r"so every clause fails at level \(\ell\).", "setup",
     "Hypothesis; all predicates zero at 0"),
    (r"Enumerate the preceding-level block family", r"in all \(r\) children of row \(i\).", "introduce_variable",
     "Row unions of copies of a block"),
    (r"Flipping this union makes the strongest", r"Thus every \(P_{\ell,q}\) is one after the flip.", "bound_estimate",
     "Flipping a row union satisfies clause i"),
    (r"Within a row these unions are disjoint", r"each of size \(r\cdot Lr^{\ell-1}=Lr^\ell\), as required.", "conclude",
     "Disjointness and count")])
# PP8 (Proposition 3.1)
P8s = step("PP8", r"Fix $\ell$, put $H=H_\ell$", r"we use a union bound.", "setup", "Setup: one bit, one child, one condition",
           order=1)
p8s = steps(P8s, [
    (r"Fix $\ell$, put $H=H_\ell$", r"uses a different child.", "setup", "Recall the clause structure"),
    (r"All flips below are flips", r"we use a union bound.", "setup", "A flip changes at most one condition per clause")])
P8a = step("PP8", r"\emph{Transitions from one.}", r"This proves both inequalities on the one side.", "bound_estimate",
           "Transitions from one", "Bound S_{l,1} and J_{l,1}", 0.95, order=2)
p8a = steps(P8a, [
    (r"Fix an input where $P_{\ell,q}=1$", r"must break that fixed clause.", "introduce_variable",
     "Fix a satisfied clause"),
    (r"It either changes a gate predicate", r"giving at most $M^2S'_0+rS'_1$ such flips.", "bound_estimate",
     "S_{l,1} bound"),
    (r"Next fix $q<q'$ and an input where both", r"fixed for all flips being counted.", "introduce_variable",
     "Fix a clause witnessing both predicates"),
    (r"A flip taking both parent predicates to zero", r"1\leq g'<g<Q. \]", "case_split",
     "Break a target or fail a gate"),
    (r"At such a gate, initially", r"This proves both inequalities on the one side.", "bound_estimate",
     "A failed gate flips two child predicates: J_{l,1} bound")])
P8b = step("PP8", r"\emph{The initial candidate clauses at a zero.}",
           r"this proves $S_{\ell,0}\leq tS'_0+S'_1+3J'_1$.", "bound_estimate",
           "The initial candidate clauses at a zero", "Bound S_{l,0}", 0.95, order=3)
p8b = steps(P8b, [
    (r"Fix $q$ and an input $x$ with", r"before a flipped coordinate is chosen.", "introduce_variable",
     "Candidate lists T and G"),
    (r"Every flip making $P_{\ell,q}$ one", r"must be repaired.", "setup", "Every repair goes through T or G"),
    (r"For each $j\in\mathcal T$, let $m_j\in[r]$", r"Thus $|\mathcal T|<t$.", "apply_lemma",
     "Labelling lemma gives |T|<t"),
    (r"Repairing a clause in this list", r"Their total contribution is at most $tS'_0$.", "bound_estimate",
     "Target contribution tS'_0"),
    (r"All targets in the row of a vertex", r"and hence}\qquad m\leq3. \]", "bound_estimate",
     "Tournament outdegree count gives |G|<=3"),
    (r"There is at most one vertex of outdegree zero", r"leaves one of them.", "other", "At most one sink in G"),
    (r"If $i\in\mathcal G$ has an outgoing edge", r"other gates are unchanged.", "bound_estimate",
     "Gate repair inside G costs J'_1"),
    (r"The possible vertex with no outgoing edge", r"this proves $S_{\ell,0}\leq tS'_0+S'_1+3J'_1$.", "conclude",
     "Sink costs S'_1; conclude S_{l,0} bound")])
P8c = step("PP8", r"\emph{Joint transitions from zero.}", r"a union bound gives $J_{\ell,0}\leq tS'_0+3J'_1$.",
           "bound_estimate", "Joint transitions from zero", "Bound J_{l,0}", 0.95, order=4)
p8c = steps(P8c, [
    (r"Fix $q<q'$ and an input $x$ where both", r"simply contribute no flips.", "setup",
     "Same lists for the weaker index; final witnesses lie in them"),
    (r"A witness in $\mathcal T$ is counted", r"target bound $tS'_0$.", "bound_estimate", "Target witnesses: tS'_0"),
    (r"For a witness in $\mathcal G$, let $g=Q-q$", r"each such clause contributes at most $J'_1$.", "bound_estimate",
     "Gate witnesses flip two child predicates"),
    (r"This reasoning applies also to the possible vertex", r"The gate contribution is therefore at most $3J'_1$.",
     "bound_estimate", "Including the sink: 3J'_1"),
    (r"Every joint-success coordinate is thus counted", r"a union bound gives $J_{\ell,0}\leq tS'_0+3J'_1$.",
     "conclude", "Union bound gives J_{l,0}")])
P8d = step("PP8", r"All bounds hold for every relevant input", r"by the empty-maximum convention.", "conclude",
           "Take maxima; empty-maximum case", order=5)
# PP9 (Lemma 4.1)
p9a = steps("PP9", [
    (r"Define \[ u_\ell=", r"\epsilon=\frac{\max(r,t)}{M}. \]", "introduce_variable", "Normalized profiles u, v and epsilon"),
    (r"The base bounds in~\eqref{eq:base-profile}", r"give $u_0\leq L$ and $v_0=0$.", "apply_lemma", "Base values"),
    (r"For $1\leq\ell\leq d$, dividing the four", r"v_\ell&\leq \epsilon u_{\ell-1}+3v_{\ell-1}. \end{split} \end{equation}",
     "apply_lemma", "Divide the recurrences by powers of M"),
    (r"The forcing term for $v_\ell$", r"small compared with $3^{-d}$.", "setup", "Need epsilon small against 3^{-d}"),
    (r"Since $M\geq81$, both", r"\leq\frac{2}{3^{d+1}}. \end{equation}", "bound_estimate", "epsilon <= 2/3^{d+1}"),
    (r"Let $U_0=L$, $V_0=0$, and define", r"$v_\ell\leq V_\ell$ by induction.", "introduce_variable",
     "Comparison sequences dominate u, v"),
    (r"We prove simultaneously that", r"This completes the simultaneous induction.", "induction_step",
     "Simultaneous induction: U <= 2L, V <= eps L (3^l - 1)"),
    (r"In particular, $u_\ell\leq2L$", r"which is the desired bound.", "conclude", "Conclude S_{l,b} <= 2LM^{l+b}")])
P9ind = p9a[6]
p9b = steps(P9ind, [
    (r"These bounds hold at $\ell=0$.", r"These bounds hold at $\ell=0$.", "induction_step", "Base case"),
    (r"Suppose they hold at every index", r"=\epsilon L(3^\ell-1). \]", "induction_step", "Inductive step for V"),
    (r"Next, summing the increments", r"<2L. \end{align*}", "bound_estimate", "Telescoping bound for U"),
    (r"The last inequality follows from", r"This completes the simultaneous induction.", "bound_estimate",
     "Use the epsilon choice")])
# PP10 (Theorem 1.1)
p10 = steps("PP10", [
    (r"Fix any integer $d\geq1$", r"provides the required tournament labels.", "introduce_variable", "Fix d, M and labels"),
    (r"Following the OR-balancing principle", r"n=LM^2(kr)^d \end{equation} bits.", "introduce_variable",
     "f = OR of M copies of P_{d,1}"),
    (r"By Lemma~\ref{lem:blocks}, every copy is zero", r"Thus $f(0)=0$ and $f$ is nonconstant.", "apply_lemma",
     "f(0)=0 and f nonconstant"),
    (r"At a zero input of $f$, every copy is zero", r"at most $S_{d,1}$ such bits.", "case_split",
     "Sensitivity of an OR at zeros and ones"),
    (r"Lemma~\ref{lem:quantitative-profiles} therefore gives", r"\leq2L M^{d+1}. \end{equation}", "apply_lemma",
     "s(f) <= 2LM^{d+1}"),
    (r"Each copy supplies $M k^d$ pairwise disjoint", r"\geq M^2k^d. \end{equation}", "apply_lemma", "bs(f,0) >= M^2k^d"),
    (r"Since $f$ is nonconstant, $s(f)>0$.", r"tends to infinity as $d$ tends to infinity.", "algebraic_manipulation",
     "Ratio >= 2^d/(4(d+2)^2), unbounded in d"),
    (r"For any proposed constant $C$", r"Hence no universal quadratic constant exists.", "conclude",
     "Choose d, then M, then labels")])
# PP11 (Lemma 4.2)
p11 = steps("PP11", [
    (r"For an input $x=(x_1,\ldots,x_a)$", r"sensitive for $f$ at $y$.", "setup", "Characterize sensitive bits of f o g"),
    (r"Thus \[ s(f\circ g,x)", r"\leq s(f)s(g). \]", "bound_estimate", "s(f o g) <= s(f)s(g)"),
    (r"Now suppose $g(0)=0$.", r"E_{i,j}=C_i\times D_j. \]", "introduce_variable", "Product blocks"),
    (r"These blocks are nonempty and pairwise disjoint", r"disjoint coordinate sets in each child.", "other",
     "Product blocks are disjoint"),
    (r"Flipping $E_{i,j}$ at zero", r"the inequality is immediate.", "conclude",
     "Each product block is sensitive at zero; take maximum families")])
# PP12 (Corollary 4.3)
p12 = steps("PP12", [
    (r"Fix $d=9$, choose an integer", r"B=M^2k^9. \]", "introduce_variable", "Seed with d=9; constants A, B"),
    (r"Here $L=11$, so~\eqref{eq:final-sensitivity}", r"while $f(0)=0$.", "apply_lemma", "s(f) <= A, bs(f,0) >= B"),
    (r"Moreover, \[ \frac{B}{A^2}", r"=\frac{128}{121}>1. \]", "bound_estimate", "B/A^2 >= 128/121"),
    (r"In particular, $A>1$, $B>A^2$", r"is greater than two.", "introduce_variable", "alpha = log B / log A > 2"),
    (r"Set $F_1=f$ and, for $m\geq1$", r"and $F_m(0)=0$.", "introduce_variable", "Iterated composition F_m"),
    (r"Lemma~\ref{lem:composition} gives", r"\operatorname{bs}(F_m,0)\geq B^m. \]", "apply_lemma",
     "s(F_m) <= A^m, bs(F_m,0) >= B^m"),
    (r"The latter bound proves nonconstancy", r"=B^m\leq\operatorname{bs}(F_m,0). \]", "bound_estimate",
     "bs(F_m,0) >= s(F_m)^alpha"),
    (r"The same estimates give the explicit ratio bound", r"\left(\frac{128}{121}\right)^m.\qedhere \]", "conclude",
     "Explicit ratio (128/121)^m")])

# ======================================================== edges
T = "term"
# history and resolution
E("CnjP1", "TP3", "resolves", 0.9, "named")
E("CnjP2", "TP5", "resolves", 0.9, "named")
E("CnjP1", "CnjP2", "specializes", 0.7, "inferred")
E("TP1", "TP2", "uses", 0.85, "named", mention=True)
E("TP3", "TP4", "uses", 0.85, "named", mention=True)
E("TP5", "RP1", "uses", 0.95, None, mention=True)
E("DP9", "ExP1", "illustrates", 0.9, "named")
E("PP1", "TP5", "proves", 0.7, "inferred", alternative=True)
E("PP2", "CP1", "proves", 0.85, "named", alternative=True)
E("PP4", "ClP3", "proves", 0.75, "inferred")
E("PP5", "ClP5", "proves", 0.75, "inferred")
E("ClP3", "ClP4", "uses", 0.85, "inferred")
# pass 2: defined terms
for t in ["DP2", "DP3", "DP4", "DP9", "LP1", "DP12", "DP14", "DP15", "DP17", "DP20", "DP21", "PP11"]:
    E("DP1", t, conf=0.75, basis=T)
for t in ["DP3", "DP4", "DP20", "DP21", "PP7", "PP11"]:
    E("DP2", t, conf=0.8, basis=T)
for t in ["CnjP1", "CnjP2", "TP1", "TP2", "TP3", "TP4", "TP5", "DP6", "RP1", "LP5", "CP1", "PP10", "PP12", "TP6"]:
    E("DP3", t, conf=0.85, basis=T)
for t in ["CnjP1", "CnjP2", "TP1", "TP2", "TP3", "TP4", "TP5", "RP1", "LP5", "CP1", "PP10", "PP11", "PP12", "TP6"]:
    E("DP4", t, conf=0.85, basis=T)
E("DP5", "DP6", conf=0.85, basis=T)
E("DP6", "RP1", conf=0.85, basis=T)
for t in ["DP9", "LP1", "PP3", "DP10", "DP12", "LP2", "LP3", "PrP1", "LP4", "DP15", "DP17", "ClP1", "ClP3",
          "PP6", "PP7", "PP8", "PP9", "PP10", "PP12"]:
    E("DP7", t, conf=0.8, basis=T)
for t in ["DP9", "PP8", "PP10"]:
    E("DP8", t, conf=0.8, basis=T)
E("DP11", "PP5", conf=0.8, basis=T)
for t in ["DP20", "DP21"]:
    E("DP19", t, conf=0.8, basis=T)
for t in ["LP1", "DP17", "PP4", "PP8", "PP10"]:
    E("DP9", t, conf=0.8, basis=T)
E("LP1", "DP17", conf=0.8, basis="inferred")       # the labels a(i,j) fixed by Lemma 2.1
for t in ["DP11", "DP14", "DP15", "DP16", "DP20", "DP21", "DP22", "ClP6", "PP6"]:
    E("DP10", t, conf=0.8, basis=T)
for t in ["ClP1", "ClP5", "LP3", "DP17", "DP19", "DP20", "DP21", "PP8", "PP10", "PP7"]:
    E("DP11", t, conf=0.8, basis=T)
for t in ["DP13", "PP7"]:
    E("DP12", t, conf=0.85, basis=T)
for t in ["DP14", "PP6", "PP7"]:
    E("DP13", t, conf=0.8, basis=T)
for t in ["ClP1", "PP6", "PP7", "LP2"]:
    E("DP14", t, conf=0.8, basis=T)
for t in ["DP17", "ClP3", "PP8", "PP7"]:
    E("DP15", t, conf=0.8, basis=T)
for t in ["DP17", "ClP2", "PP8"]:
    E("DP16", t, conf=0.8, basis=T)
for t in ["DP18", "DP19", "ClP3", "ClP4", "ClP5", "PP5", "PP7", "PP8", "PP4"]:
    E("DP17", t, conf=0.8, basis=T)
for t in ["PP5", "PP8", "PP4", "PP7"]:
    E("DP18", t, conf=0.8, basis=T)
for t in ["ClP5", "ClP6", "LP3", "PP7", "PP8", "PP10"]:
    E("DP19", t, conf=0.8, basis=T)
for t in ["LP2", "PrP1", "LP4", "PP9", "PP10"]:
    E("DP20", t, conf=0.85, basis=T)
for t in ["DP22", "RP2", "LP2", "PrP1", "PP9"]:
    E("DP21", t, conf=0.85, basis=T)
E("DP22", "PP8", conf=0.9, basis="named")
for t in ["PP11", "PP12"]:
    E("DP23", t, conf=0.85, basis=T)
# pass 3: results used in proofs (no \ref)
E("ClP1", "PP6", conf=0.8)
E("ClP1", "PP8", conf=0.7)
E("ClP5", "PP8", conf=0.8)
E("ClP3", "PP8", conf=0.8)
E("ClP4", "PP8", conf=0.8)
E("ClP2", "PP8", conf=0.6)
E("ClP3", "PP7", conf=0.75)
E("ClP6", "PP10", conf=0.75)
E("ClP5", "PP7", conf=0.6)
E("PP10", "PP12", conf=0.9, basis="named")      # "the function constructed in the proof of Theorem 1.1"
E("TP5", "PP12", conf=0.95, basis=None, mention=True)
E("TP5", p12[0], conf=0.95, basis=None, mention=True)
# pass 4: inside proofs
E(p3[0], p3[1]); E(p3[1], p3[2])
E(p6[0], p6[1]); E(p6[1], p6[2]); E(p6[4], p6[5]); E(p6[5], p6[6])
E(p7[1], p7[2]); E(p7[1], p7[3]); E(P7a, P7b)
E(p8a[0], p8a[1]); E(p8a[2], p8a[3]); E(p8a[3], p8a[4])
E(p8b[0], p8b[1]); E(p8b[2], p8b[3]); E(p8b[4], p8b[6]); E(p8b[5], p8b[7]); E(p8b[3], p8b[7]); E(p8b[6], p8b[7])
E(p8b[0], p8c[0])  # "form the same initial lists"  -- same proof, different label
E(p8b[3], p8c[1], conf=0.85, basis="named")  # "the preceding target bound"
E(p8c[2], p8c[3]); E(p8c[1], p8c[4]); E(p8c[3], p8c[4])
E(P8a, P8d); E(P8b, P8d); E(P8c, P8d)
E(p9a[0], p9a[2]); E(p9a[2], p9a[5]); E(p9a[4], p9b[3]); E(p9a[5], p9a[6]); E(p9a[6], p9a[7])
E(p9b[1], p9b[2]); E(p9b[2], p9b[3])
E(p10[1], p10[3]); E(p10[3], p10[4]); E(p10[4], p10[6]); E(p10[5], p10[6]); E(p10[6], p10[7]); E(p10[2], p10[6])
E(p11[0], p11[1]); E(p11[2], p11[3]); E(p11[2], p11[4]); E(p11[3], p11[4])
E(p12[0], p12[1]); E(p12[1], p12[2]); E(p12[2], p12[3]); E(p12[4], p12[5]); E(p12[5], p12[6]); E(p12[3], p12[6])
E(p12[5], p12[7]); E(p12[2], p12[7])

# ======================================================== metadata, finalize, write
graph = {"metadata": {
    "title": "A superquadratic separation between sensitivity and block sensitivity",
    "arxiv_id": "OAI-132",
    "authors": ["OpenAI"],
    "year": 2026,
    "annotator": "agent-extraction",
    "model": "claude-opus-5-5",
    "effort": "default",
    "prompt_version": "v7-86dcfbecdc4d78a5-f5c7dfe",
    "extraction_date": "2026-11-05",
    "rigor_nonformal_count": sum("rigor" in n for n in nodes),
    "paper_style": ["theorem_proof"],
    "extraction_notes": [],
    "extraction_comment": "",
}, "nodes": nodes, "edges": edges}
graph["metadata"]["extraction_notes"] = [
    {"category": "rule_conflict", "nodes": ["PP1", "PP2"],
     "note": "The proof-sketch rule asks for rigor semi_formal on a sketch, while the rigor rule forbids rigor on proofs; I followed the sketch rule (finalize warns)."},
    {"category": "rule_conflict", "nodes": ["TP2"],
     "note": "One sentence states two cited separations (Virza; Ambainis-Sun); nodes never split a sentence, so both are one external theorem node."},
    {"category": "type_uncertain", "nodes": ["LP5"],
     "note": "Composition lemma marked external (Tal 2013 / standard): the paper calls these 'elementary composition facts' of the principle 'studied by Tal' and includes them for self-containment; its proof is the paper's own."},
    {"category": "type_uncertain", "nodes": ["TP6"],
     "note": "Ambainis-Prusis 'explicitly noted' observation (a seed with bs > s^2 amplifies by iteration) emitted as an external theorem; it is an observation more than a stated theorem."},
    {"category": "boundary_uncertain", "nodes": ["PP1"],
     "note": "The 'Construction and proof strategy' paragraphs of the introduction are taken as one proof sketch of Theorem 1.1 (alternative proves edge); the surrounding 'Method and relation to spectral sensitivity' discussion is not extracted except the spectral-sensitivity definitions and remark."},
    {"category": "not_extracted", "nodes": [],
     "note": "Meiburg 2026 architecture description and its footnote on GPT-5.6-Sol attribution, the motivation paragraphs opening Sections 2, 3, 4 and 4.1, and the TikZ figure (Fig. 1, which only depicts equation (1)) have no nodes."},
]
graph["metadata"]["extraction_comment"] = ("Text, proof and Lean formalization of this paper were produced by an OpenAI model "
                                           "(OpenAI math release); the author field is 'OpenAI'.")
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
