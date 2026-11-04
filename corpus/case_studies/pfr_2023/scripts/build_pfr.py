#!/usr/bin/env python3
"""Build the v7 LLM extraction of Gowers-Green-Manners-Tao, 'On a conjecture of Marton' (2311.05762).
Nodes, types, spans and edges were chosen by reading the paper; this script only slices spans."""
import json, re, sys
REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize
from latex_facts import read_tex

SCR = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/181b34d2-e85e-4795-8729-4e70122e8101/scratchpad"
TEX = REPO + "/corpus/gold_blueprints/teorth__pfr/paper/source/main.tex"
OUT = REPO + "/corpus/silver/opus-5.5__v7_cases/pfr_2023.json"
facts = json.load(open(SCR + "/facts.json"))
S = facts["source"]
F = {f["id"]: f for f in facts["facts"]}
SECS = [s for s in facts["sections"] if s.get("inside") is None]


def norm(t):
    return re.sub(r"\s+", " ", t).strip()


def sec_at(pos):
    s = max((x for x in SECS if x["start"] <= pos), key=lambda x: x["start"])
    return f"{s['number']} {s['title']}" if s["number"] else s["title"]


nodes, edges = [], []
byid = {}
POS = {}          # node id -> (start, end) in S


def add(nid, typ, name, stmt, start, end, origin="paper", conf=1.0, **kw):
    n = {"id": nid, "type": typ, "name": name, "statement": stmt, "section": kw.pop("section", None) or sec_at(start),
         "origin": origin, "confidence": conf}
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
    i = S.index(a, after)
    j = S.index(b, i) + len(b)
    return add(nid, typ, name, norm(S[i:j]), i, j, origin, conf, **kw)


def sub(nid, a, b=None):
    """verbatim sub-span of node nid's statement, from a through b"""
    st = byid[nid]["statement"]
    i = st.index(norm(a))
    if b is None:
        return norm(a)
    j = st.index(norm(b), i) + len(norm(b))
    return st[i:j]


PSP = [0]


def steps(pid, spec):
    """spec: list of (start_marker, subclass, name). Steps tile the proof body contiguously."""
    lo, hi = POS[pid]
    starts, pos = [], lo
    for m, sc, nm in spec:
        i = S.index(m, pos)
        assert i < hi, (pid, m)
        starts.append(i); pos = i + len(m)
    out = []
    for k, (m, sc, nm) in enumerate(spec):
        a = starts[k]
        b = starts[k + 1] if k + 1 < len(spec) else hi
        txt = S[a:b]
        txt = txt.rstrip()
        if b == hi:
            txt = re.sub(r"\\end\{proof\}\s*$", "", txt).rstrip()
        PSP[0] += 1
        sid = f"PSP{PSP[0]}"
        add(sid, "proof_step", nm, norm(txt), a, a + len(txt), byid[pid]["origin"],
            0.75, parent_id=pid, step_order=k + 1, subclass=sc, statement_short=nm,
            section=byid[pid]["section"])
        out.append(sid)
    return out


def E(s, t, typ="uses", conf=0.8, basis="inferred", **kw):
    e = {"source": s, "target": t, "type": typ, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)


EQNAMES = {}
EQN = [0]


def eq(fid, name, origin="paper", **kw):
    EQN[0] += 1
    nid = f"EP{EQN[0]}"
    env(nid, fid, "equation", name, origin, 1.0, **kw)
    return nid


STD = "standard (uncited)"
GMT = "Green, Manners & Tao 2023 (Sumsets and entropy revisited)"
TAO = "Tao 2010 (Sumset and inverse sumset theory for Shannon entropy)"

# ------------------------------------------------------------------ 1 Introduction
env("CnjP1", "F1", "conjecture", "Polynomial Freiman-Ruzsa conjecture (Marton's conjecture)", "external",
    origin_citation="Marton; Ruzsa 1999",
    statement_short="A set $A\\subset\\mathbf{F}_2^n$ with doubling $K$ is covered by $2K^C$ cosets of a subgroup of size at most $|A|$.",
    tags=["additive_combinatorics", "inverse_theorem", "sumset"])
byid["CnjP1"]["assumptions"] = [sub("CnjP1", r"$A \subset \mathbf{F}_2^n$ is a set with $|A + A| \leqslant K|A|$")]
byid["CnjP1"]["conclusions"] = [sub("CnjP1", r"$A$ is covered by at most $2 K^{C}$ cosets", r"of size at most $|A|$")]
prose("ClP1", "claim", "Covering by few cosets implies small doubling",
      r"Note that if $A$ is covered by at most $r$ cosets", "with at most a polynomial loss in the parameters.",
      origin="external", conf=0.7, origin_citation=STD,
      statement_short="Conversely, a set covered by $r$ cosets of a subgroup of size at most $|A|$ has doubling at most $\\binom r2+1$.",
      tags=["sumset", "bound"])
prose("TP1", "theorem", "Ruzsa's bound for Marton's conjecture",
      "The first result in this direction was due to Imre Ruzsa", "in place of the desired $2K^C$.",
      origin="external", conf=0.7, origin_citation="Ruzsa 1999",
      statement_short="Ruzsa: covering by $2K^2 2^{K^4}$ cosets.", tags=["bound"])
prose("TP2", "theorem", "Sanders' quasi-polynomial Freiman-Ruzsa bound",
      r"Sanders~\cite{sanders} made a dramatic breakthrough", "is permissible here.",
      origin="external", conf=0.7, origin_citation="Sanders 2012",
      statement_short="Sanders: bounds of shape $\\exp(\\log^{4+\\varepsilon} K)$.", tags=["bound"])
prose("TP3", "theorem", "Konyagin's refinement of Sanders' bound",
      "A variant of Sanders' argument due to Konyagin", r"showed that $C_1 = 3 + \varepsilon$ is permissible.",
      origin="external", conf=0.7, origin_citation="Konyagin (described in Sanders 2013)",
      statement_short="Konyagin: exponent $3+\\varepsilon$.", tags=["bound"])
prose("TP4", "theorem", "Green-Tao: PFR for downsets",
      r"We also remark that \Cref{pfr-conj} (with worse values of $C$)", r"when $A$ was a downset in~\cite{gt-freiman}.",
      origin="external", conf=0.7, origin_citation="Green & Tao 2009",
      statement_short="The conjecture, with worse constants, holds for downsets.", tags=["special_case"])
env("TP5", "F2", "theorem", "Polynomial Freiman-Ruzsa theorem in characteristic 2 (C = 12)", main=True,
    statement_short="Marton's conjecture holds with $C=12$.", tags=["additive_combinatorics", "inverse_theorem"],
    assumptions=[], conclusions=[r"\Cref{pfr-conj} is true with $C = 12$."])
prose("TP6", "theorem", "Liao's improvement to C = 11",
      "Since the initial release of this preprint, Jyun-Jie Liao", r"see~\cite{liao1,liao2}.",
      origin="external", conf=0.7, origin_citation="Liao 2023",
      statement_short="Liao refines the argument to get $C=11$.", tags=["bound"])
# Applications
prose("PP1", "proof", "Deduction of weak PFR over Z (via Green-Manners-Tao)",
      r"It was shown in~\cite[Theorem 1.11]{gmt}", "so that is now a theorem as well.", conf=0.75,
      proves="TP7", statement_short="Cite [GMT, Thm 1.11]: entropic PFR in characteristic 2 implies weak PFR over $\\mathbf{Z}$.")
env("TP7", "F3", "theorem", "Weak polynomial Freiman-Ruzsa theorem over Z",
    statement_short="A set in $\\mathbf{Z}^D$ with doubling $K$ has a $K^{-O(1)}$-dense subset of dimension $O(\\log K)$.",
    tags=["additive_combinatorics", "integers"])
byid["TP7"]["assumptions"] = [sub("TP7", r"$A$ be a finite subset of $\mathbf{Z}^D$ for some $D$"), sub("TP7", r"$|A+A| \leqslant K|A|$")]
byid["TP7"]["conclusions"] = [sub("TP7", r"there is some set $A' \subseteq A$", r"$\dim A' \leqslant C_2 \log K$")]
prose("OpenP1", "open_problem", "Strong PFR conjecture over Z",
      "We remark that there is also a `strong' PFR conjecture", "This remains a challenging open problem.",
      origin="external", conf=0.7, origin_citation="Lovett & Regev 2017; Manners 2019",
      statement_short="The strong PFR conjecture over $\\mathbf{Z}$ (with a careful formulation) remains open.")
env("CP1", "F4", "corollary", "Additive stability (approximate homomorphisms) in F_2^n",
    statement_short="A map with few additive defects is linear plus a map of polynomially small range.", tags=["approximate_homomorphism"])
byid["CP1"]["assumptions"] = [sub("CP1", r"$f: \mathbf{F}_2^m \to \mathbf{F}_2^n$ is a function such that", "has cardinality at most $K$")]
byid["CP1"]["conclusions"] = [sub("CP1", "$f$ may be written as $g+h$", "cardinality $O(K^{C_3})$")]
prose("PP2", "proof", "Ruzsa's equivalence (proof of Corollary 1.4)",
      r"The equivalence of this and \Cref{pfr}", r"the details may be found in~\cite{green-pfr-note}.", conf=0.75,
      proves="CP1", statement_short="Cite Ruzsa's (unpublished, written up by Green) equivalence of Corollary 1.4 with Theorem 1.2.")
prose("DP1", "definition", "Big-O notation", r"Here, as usual, $O(X)$ denotes", r"for some absolute constant~$C$.",
      origin="external", conf=0.85, origin_citation=STD, definiendum="$O(X)$")
env("CP2", "F5", "corollary", "Polynomial linearity testing in F_2^n",
    statement_short="A map that is additive with probability $1/K$ agrees with a homomorphism on a $K^{-O(1)}$ fraction.",
    tags=["linearity_testing"])
byid["CP2"]["assumptions"] = [sub("CP2", r"$f : \mathbf{F}_2^m \to \mathbf{F}_2^n$ is a function such that", r"\geqslant 1/K$")]
byid["CP2"]["conclusions"] = [sub("CP2", r"there is a homomorphism", r"\gg K^{-C_4}$")]
prose("PP3", "proof", "Pointer to Samorodnitsky (proof of Corollary 1.5)", r"See~\cite[Theorem 4.1]{samorodnitsky}.",
      r"See~\cite[Theorem 4.1]{samorodnitsky}.", conf=0.65, proves="CP2",
      statement_short="Follows from PFR by Samorodnitsky's Theorem 4.1.")
prose("DP2", "definition", "Notation X >> Y", r"The notation $X\gg Y$ means", r"such that $X\geqslant cY$.",
      origin="external", conf=0.85, origin_citation=STD, definiendum="$X\\gg Y$")
env("CP3", "F6", "corollary", "Polynomial inverse theorem for the U^3(F_2^n) norm",
    statement_short="A 1-bounded $f$ with $\\|f\\|_{U^3}\\ge 1/K$ correlates polynomially with a quadratic phase.",
    tags=["gowers_norm", "inverse_theorem"])
byid["CP3"]["assumptions"] = [sub("CP3", r"$f \colon \mathbf{F}_2^n \to \mathbf{C}$ be a $1$-bounded function", r"\geqslant 1/K$")]
byid["CP3"]["conclusions"] = [sub("CP3", "there exists a quadratic polynomial", r"\gg K^{-C_5}.\]")]
env("CP4", "F7", "corollary", "Mudgal's sum-product theorem for iterated sumsets", "external",
    origin_citation="Mudgal 2023, Theorem 6.2",
    statement_short="For finite $A\\subset\\mathbf{R}$, $|mA|$ or $|A^{(m)}|$ is at least $|A|^{f(m)}$ with $f(m)\\to\\infty$.",
    tags=["sum_product"])
prose("TP8", "theorem", "Bourgain-Chang theorem", "This generalizes a well-known result of Bourgain and Chang",
      "when $A$ is a set of integers.", origin="external", conf=0.7, origin_citation="Bourgain & Chang 2004",
      statement_short="The integer case of Corollary 1.7.", tags=["sum_product"])
# Entropy methods
prose("DP3", "definition", "Entropic Ruzsa distance", r"If $X, Y$ are two finitely supported random variables",
      r"where $X', Y'$ are independent copies of $X, Y$.", origin="external", conf=0.9,
      origin_citation="Ruzsa 2009; " + TAO + "; " + GMT, definiendum="entropic Ruzsa distance $\\dist{X}{Y}$",
      statement_short="$d[X;Y]=H[X'-Y']-\\frac12H[X']-\\frac12H[Y']$ for independent copies $X',Y'$.")
eq("F8", "Ruzsa distance formula (1.1)", "external", origin_citation=GMT)
env("TP9", "F9", "theorem", "Entropic polynomial Freiman-Ruzsa theorem", main=True,
    statement_short="Any two $\\mathbf{F}_2^n$-valued random variables are within $11\\,d[X_1^0;X_2^0]$ (total) of a uniform distribution on a subgroup.",
    tags=["entropy", "inverse_theorem"])
byid["TP9"]["assumptions"] = [sub("TP9", r"$G = \mathbf{F}_2^n$"), sub("TP9", r"$X^0_1, X^0_2$ are $G$-valued random variables")]
byid["TP9"]["conclusions"] = [sub("TP9", r"there is some subgroup $H \leqslant G$ such that", r"11\dist{X^0_1}{X^0_2}, \]"),
                              sub("TP9", r"both $\dist{X^0_1}{U_H}$", r"at most $6 \dist{X^0_1}{X^0_2}$")]
prose("TP10", "theorem", "Equivalence of entropic and combinatorial PFR", r"The fact that \Cref{pfr-entropy} is equivalent",
      r"was established in~\cite[Section 8]{gmt}.", origin="external", conf=0.7, origin_citation=GMT + ", Section 8",
      statement_short="Theorem 1.8 is equivalent up to constants to Marton's conjecture and its other formulations.",
      tags=["equivalence"])
# Variants and further remarks
prose("CnjP2", "conjecture", "Strong PFR conjecture (approximate homomorphisms)", r"One could consider strengthening \Cref{additive-stability}",
      r"for some absolute constant $C_7$.", origin="external", conf=0.7, origin_citation="Aaronson 2019; Tao 2009",
      statement_short="Corollary 1.4 with $h$ taking values in a bounded iterated sumset of the defect set.")
prose("TP11", "theorem", "Strong PFR conjecture is false", "However, this ``strong PFR conjecture'' is known to be false",
      r"\cite[Section 1.17]{tao-poincare}.", origin="external", conf=0.75, origin_citation="Aaronson 2019; Tao 2009")
prose("CnjP3", "conjecture", "Polynomial Bogolyubov conjecture", r"The \emph{polynomial Bogolyubov conjecture}",
      r"contains a subspace of cardinality $\gg K^{-O(1)} |A|$.", origin="external", conf=0.85,
      origin_citation="Lovett 2015, Conjecture 1.5",
      statement_short="$2A-2A$ contains a subspace of size $K^{-O(1)}|A|$ when $A$ has doubling $K$.")
prose("TP12", "theorem", "Sanders' Bogolyubov-Ruzsa lemma", r"In~\cite{sanders} it was shown that $2A-2A$",
      r"in~\cite{hosseini-lovett}.", origin="external", conf=0.7, origin_citation="Sanders 2012",
      statement_short="$2A-2A$ contains a subspace of size $K^{-O(\\log^3 K)}|A|$.")
prose("DP4", "definition", "Freiman constant f(2,K)", "Let $f(2,K)$ denote the best constant",
      r"cardinality at most $f(2,K) |A|$.", conf=0.85, definiendum="$f(2,K)$")
prose("TP13", "theorem", "Even-Zohar's asymptotics for f(2,K)", "It is known that $f(2,K)$ is a piecewise linear",
      r"\cite{diao, gt-freiman, konyagin}).", origin="external", conf=0.75, origin_citation="Even-Zohar 2012",
      statement_short="$f(2,K)$ is piecewise linear and $\\asymp 2^{2K}/K$.")

# ------------------------------------------------------------------ 2 Induction on entropy distance
prose("DP5", "definition", "Fixed group G and reference variables X^0_1, X^0_2", "Fix, for the rest of the paper, the group",
      r"appearing in \Cref{pfr-entropy}.", conf=0.85, definiendum=["$G$", "$X^0_1$", "$X^0_2$"])
prose("DP6", "definition", "Constant eta = 1/9", r"For the rest of the paper, $\eta$ will denote", r"the constant $\frac{1}{9}$.",
      conf=0.85, definiendum="$\\eta$")
prose("DP7", "definition", "Functional tau", "For any two $G$-valued random variables $X_1, X_2$, we introduce the functional",
      r"\eta \dist{X^0_2}{X_2}." + "\n" + r"\end{equation}", conf=0.9, definiendum="$\\tau[X_1; X_2]$",
      statement_short="$\\tau$ = Ruzsa distance plus $\\eta$ times the distances to the reference variables.")
eq("F10", "Definition of tau (2.1)")
env("PrP1", "F11", "proposition", "Distance-decrement proposition (tau can be decreased)",
    statement_short="If $d[X_1;X_2]>0$ there are $X'_1,X'_2$ with strictly smaller $\\tau$.", tags=["decrement"])
byid["PrP1"]["assumptions"] = [sub("PrP1", r"$X_1, X_2$ be two $G$-valued random variables with $\dist{X_1}{X_2} > 0$")]
byid["PrP1"]["conclusions"] = [sub("PrP1", r"there are $G$-valued random variables $X'_1, X'_2$ such that", r"\tau[X_1;X_2].")]
eq("F12", "Strict decrement of tau (2.2)")
env("LP1", "F13", "lemma", "100 percent case of entropic PFR",
    statement_short="Zero Ruzsa distance forces both variables to be at distance zero from a uniform distribution on a subgroup.")
byid["LP1"]["assumptions"] = [sub("LP1", r"$X_1,X_2$ are $G$-valued random variables such that", r"$\dist{X_1}{X_2}=0$")]
byid["LP1"]["conclusions"] = [sub("LP1", r"there exists a subgroup $H \leqslant G$", r"\dist{X_2}{U_H} = 0$")]
env("PP4", "F14", "proof", "Proof of Lemma 2.2", proof_strategy=["direct"],
    statement_short="Triangle inequality gives $d[X_1;-X_1]=0$; Tao's 100% inverse theorem gives $H$; triangle inequality again.")
s = steps("PP4", [("By the triangle inequality, $\\dist{X_1}{X_1} = 0$", "apply_lemma", "Triangle inequality gives d[X1;-X1]=0"),
                  ("By~\\cite[Theorem~1.11(i)]{tao-entropy}", "apply_lemma", "Tao's theorem gives the subgroup H"),
                  ("Then $\\dist{X_2}{U_H}=0$ follows", "conclude", "Triangle inequality for X2")])
env("PP5", "F15", "proof", "Proof of Theorem 1.8 assuming Proposition 2.1", proof_strategy=["compactness", "contradiction"],
    statement_short="Take a minimiser of $\\tau$ (exists by compactness); Prop. 2.1 forces $d=0$, Lemma 2.2 gives $H$. Bound $\\eta$ times the distances by $\\tau(X^0_2,X^0_1)$.")
s5 = steps("PP5", [("We choose a pair of variables", "introduce_variable", "Choose a minimiser of tau; it exists by compactness"),
                   ("As $(X_1,X_2)$ minimizes $\\tau$", "apply_lemma", "Prop. 2.1 and Lemma 2.2 give H"),
                   ("Finally, we have", "bound_estimate", "Compare tau with its value at the reference pair"),
                   ("Since\n  $", "conclude", "Second claim by the triangle inequality")])
env("RP1", "F17", "remark", "Algorithmic variant of the proof", rigor="semi_formal",
    statement_short="Proving a stronger multiplicative decrement gives an iterative, compactness-free proof with worse constants.")
eq("F18", "Proper decrement (2.3)")
env("RP2", "F19", "remark", "Weak Bogolyubov-type consequence", rigor="semi_formal",
    statement_short="The iteration yields a subspace of size $K^{-O(1)}|A|$ inside $mA$ with $m=O(\\log^{O(1)}K)$.")

# ------------------------------------------------------------------ 3 Plan of the remaining argument
prose("DP8", "definition", "Distance k", "Let $k$ denote the quantity", r"\dist{X_1}{X_2}$.", conf=0.85, definiendum="$k$")
prose("DP17", "definition", "Notation O(eta k)", "For the following preliminary discussion we write various estimates as",
      "for simplicity.", conf=0.8, definiendum="$O(\\eta k)$")
prose("DP9", "definition", "Independent copies tilde X_1, tilde X_2", "To describe the choices we will try, consider a four-tuple",
      "are independent.", after=24000, conf=0.8, definiendum=["$\\tilde X_1$", "$\\tilde X_2$"])
prose("DP10", "definition", "Candidate pairs: sums and fibres", r"Our primary choices for $(X'_1, X'_2)$ will be sums",
      r"for $g, g' \in G$.", conf=0.75, definiendum="sums and fibres",
      statement_short="The candidates $X'_i$: sums $X_i+\\tilde X_j$ (3.1)-(3.2) or fibres $(X_i|X_i+\\tilde X_j=g)$ (3.3)-(3.4).")
eq("F20", "Sum choice (3.1)"); eq("F21", "Sum choice (3.2)"); eq("F22", "Fibre choice (3.3)"); eq("F23", "Fibre choice (3.4)")
prose("ClP2", "claim", "Heuristic first estimate (I_1 small)", "What we find in this case is that if neither choice",
      r"= O(\eta k)." + "\n" + r"\end{equation}", conf=0.7, rigor="heuristic",
      statement_short="If sums (3.1) and fibres (3.3) fail, $I_1=O(\\eta k)$.")
eq("F24", "I_1 = O(eta k) (3.5)")
prose("ClP3", "claim", "Heuristic second estimate (I_2 small)", "Similarly, if neither choice", r"\end{equation}", after=26000,
      conf=0.7, rigor="heuristic", statement_short="If (3.2) and (3.4) fail, $I_2=O(\\eta k)$.")
eq("F25", "I_2 = O(eta k) (3.6)")
prose("ClP4", "claim", "Heuristic third estimate (I_3 = I_2)", "Finally,\n\\begin{equation}\\label{third-est-a}",
      r"the names of $\tilde X_1$ and $X_1$.", conf=0.7, rigor="heuristic",
      statement_short="$I_3=O(\\eta k)$ too, since $I_3=I_2$ by symmetry.")
eq("F26", "I_3 = O(eta k) (3.7)")
prose("ClP5", "claim", "Exact case: T_1, T_2, T_3 pairwise independent", "Suppose first for simplicity that the mutual informations",
      "are pairwise independent.", conf=0.7, rigor="semi_formal",
      statement_short="If $I_1=I_2=I_3=0$, the conditioned sums $T_1,T_2,T_3$ are pairwise independent.")
eq("F27", "Variables T_1, T_2, T_3 (3.8)")
prose("ClP6", "claim", "T_1 + T_2 + T_3 = 0", "We also note that $T_1+T_2+T_3$ is constant", "(in fact it is identically zero).", conf=0.75)
prose("ClP7", "claim", "Pairwise independent trio with constant sum has zero distances", "However, for any trio $(T_1,T_2,T_3)$",
      r"we have $\dist{X_1'}{X_2'} = 0$.", conf=0.7, rigor="semi_formal",
      statement_short="For pairwise independent $T_i$ with constant sum, the three pairwise Ruzsa distances sum to 0.")
eq("F28", "Sum of the three distances vanishes (3.9)")
prose("RP3", "remark", "Role of entropic Balog-Szemeredi-Gowers in the plan", "If the three variables in~\\eqref{three-variables} are merely",
      r"(using the same $s,t$ for both $X_1'$ and $X_2'$).", conf=0.7, rigor="heuristic",
      statement_short="In the almost-independent case entropic BSG produces $X'_1,X'_2$ of the form (3.10) with $d=O(\\eta k)$.")
eq("F29", "Form of the BSG output (3.10)")
# Motivating examples
prose("DP11", "definition", "K = e^k", "In this discussion is convenient to write", r"$K \coloneqq e^k$.", conf=0.85, definiendum="$K$")
prose("ExP1", "example", "Random subset of a subgroup", "Consider first the case in which $A_1=A_2=A$",
      "with room to spare, by the triangle inequality.", conf=0.85,
      statement_short="For a random dense subset of a subgroup the sums (3.2) already decrease $\\tau$.")
prose("ExP2", "example", "Union of independent cosets", "Consider next the case in which $A_1 = \\bigcup",
      "is typically a union of two cosets of $H$.)", conf=0.85,
      statement_short="For unions of $K$ independent cosets the fibres (3.3) decrease $\\tau$.")
prose("ExP3", "example", "Random subsets of unions of cosets (endgame needed)", "Here is a third example, a sort of combination",
      "(Again, permuting the variables may give slighly different conclusions.)", conf=0.85,
      statement_short="All four sum/fibre choices fail; the endgame with entropic BSG succeeds.")
prose("ExP4", "example", "Discrete Gaussians over Z", "Finally, we consider a further example over $G = \\mathbf{Z}$",
      "must `see' the finite characteristic in an essential way.", conf=0.85,
      statement_short="Discrete Gaussians show Prop. 2.1 fails over $\\mathbf{Z}$, so the endgame must use characteristic 2.")
# The contrapositive formulation
prose("AssumP1", "assumption", "Contrapositive hypothesis: (X_1, X_2) minimises tau", "Thus, suppose henceforth that we have a pair",
      r"for every pair of $G$-valued random variables $(X'_1, X'_2)$.", conf=0.85,
      statement_short="Assume $d[X_1;X_2]=k$ and no pair $(X'_1,X'_2)$ has smaller $\\tau$.")
eq("F30", "tau not decreased (3.11)")
prose("ClP8", "claim", "Hypothesis in terms of distances", r"Using the definition of $\tau$ (see~\eqref{tau-def})",
      r"\costb{X'_2}." + "\n" + r"\end{equation}", conf=0.75,
      statement_short="The hypothesis says $d[X'_1;X'_2]\\ge k$ minus the $\\eta$-penalties.")
eq("F31", "Hypothesis rewritten (3.12)")
env("ClP9", "F32", "claim", "First estimate (I_1 <= 2 eta k)", conf=0.9,
    statement_short="$I_1=I[X_1+X_2:\\tilde X_1+X_2\\mid X_1+X_2+\\tilde X_1+\\tilde X_2]\\le 2\\eta k$.",
    conclusions=[norm(F["F32"]["statement"])], assumptions=[])
env("ClP10", "F33", "claim", "Second estimate (bound on I_2)", conf=0.9,
    statement_short="$I_2\\le 2\\eta k+2\\eta(2\\eta k-I_1)/(1-\\eta)$.", conclusions=[norm(F["F33"]["statement"])], assumptions=[])
prose("ClP11", "claim", "Conditioned hypothesis", r"Note that~\eqref{to-contradict} implies a conditioned version of itself",
      r"&- \costb{X'_2 | Y_2}." + "\n" + r"\end{align}", conf=0.75,
      statement_short="Averaging (3.12) over conditionings gives the same lower bound for conditional distances.")
eq("F35", "Conditioned hypothesis (3.15)")
prose("RP4", "remark", "Odd characteristic", "We will handle the case $p$ odd in our forthcoming paper",
      "applied $p-1$ times.", conf=0.75, rigor="semi_formal",
      statement_short="All steps but the endgame carry over to odd $p$; there one minimises a $p$-partite distance.")

# ------------------------------------------------------------------ 4 Fibring lemma
env("PrP2", "F37", "proposition", "Fibring lemma", "external", origin_citation=GMT + ", Proposition 1.4",
    statement_short="Ruzsa distance splits into the distance of the images under a homomorphism plus the conditional distance of the fibres, up to a conditional mutual information.",
    tags=["entropy", "homomorphism"])
byid["PrP2"]["assumptions"] = [sub("PrP2", r"$\pi \colon H \to H'$ be a homomorphism between abelian groups", r"$H$-valued random variables")]
byid["PrP2"]["conclusions"] = [sub("PrP2", r"\dist{Z_1}{Z_2} \geqslant", r"\dist{Z_1|\pi(Z_1)}{Z_2 |\pi(Z_2)}")]
eq("F38", "Fibring defect as mutual information (4.1)")
env("PP6", "F39", "proof", "Proof of the fibring lemma", proof_strategy=["algebraic_manipulation"],
    statement_short="Expand both sides in entropies; submodularity gives the inequality and the defect is a conditional mutual information.")
s6 = steps("PP6", [("Let $Z_1,Z_2$ be independent throughout.", "algebraic_manipulation", "Expand the conditional distance and apply submodularity"),
                   ("In the middle step, we used submodularity", "invoke_identity", "Justify the steps; the inequality follows"),
                   ("The difference between the two sides is precisely", "algebraic_manipulation", "Write the defect as an entropy difference"),
                   ("To rewrite this in terms of (conditional) mutual information", "conclude", "Identify the defect as I[A:C|B]")])
env("CP5", "F41", "corollary", "Fibring identity for four independent variables",
    statement_short="For independent $Y_1,\\dots,Y_4$: $d[Y_1-Y_3;Y_2-Y_4]+d[Y_1|Y_1-Y_3;Y_2|Y_2-Y_4]+I[\\dots]=d[Y_1;Y_2]+d[Y_3;Y_4]$.")
byid["CP5"]["assumptions"] = [sub("CP5", r"$Y_1,Y_2,Y_3$ and $Y_4$ be independent random variables", "abelian group $G$")]
byid["CP5"]["conclusions"] = [sub("CP5", r"\begin{align*}", r"\end{align*}")]
env("PP7", "F43", "proof", "Proof of Corollary 4.2", proof_strategy=["direct"],
    statement_short="Apply the fibring lemma to $\\pi(x,y)=x-y$ on $G\\times G$ with $Z_1=(Y_1,Y_3)$, $Z_2=(Y_2,Y_4)$ and identify each term.")
s7 = steps("PP7", [("We apply \\Cref{projections-1} with", "apply_lemma", "Apply the fibring lemma to subtraction on G x G"),
                   ("Then by independence we easily calculate", "algebraic_manipulation", "Compute the unconditioned distances"),
                   ("Furthermore,\n", "algebraic_manipulation", "Identify the conditional distances"),
                   ("Finally, we have\n", "conclude", "Identify the mutual information term")])
env("RP5", "F45", "remark", "Signs in characteristic 2", statement_short="In characteristic 2 minus signs may be replaced by plus signs.")

# ------------------------------------------------------------------ 5 First estimate
i5 = S.index("Recall that in this and subsequent sections")
j5 = S.index(r"Adding all these inequalities, we obtain~\eqref{suff-for-first-est}.") + len(r"Adding all these inequalities, we obtain~\eqref{suff-for-first-est}.")
add("PP8", "proof", "Proof of the first estimate (Section 5)", norm(S[i5:j5]), i5, j5, conf=0.85, proves="ClP9",
    proof_strategy=["contradiction"],
    statement_short="Test the hypothesis on the sum pair (3.1) and the fibre pair (3.3) via the fibring identity. Lemma 5.2 bounds the $\\eta$-penalties by $2k$.")
s8 = steps("PP8", [("Recall that in this and subsequent sections", "setup", "Recall the standing hypotheses"),
                   ("In this section we establish the upper bound~\\eqref{first-est}", "setup", "State the goal (3.13)"),
                   ("We apply \\Cref{cor-fibre} (and Remark \\ref{rem:char2}) with the choice\n\\[\n  (Y_1,Y_2,Y_3,Y_4) \\coloneqq (X_1, X_2, \\tilde X_2, \\tilde X_1)", "apply_lemma", "Fibring identity with (X1, X2, tX2, tX1)"),
                   ("Applying~\\eqref{to-contradict},~\\eqref{to-contradict-avg}, we have", "apply_lemma", "Apply the hypothesis to the sum and fibre pairs"),
                   ("It therefore suffices to prove that", "setup", "Reduce to the penalty bound (5.3)"),
                   ("We pause to state some lemmas", "setup", "Lemmas 5.1 and 5.2 and the Kaimanovich-Vershik-Madiman inequality"),
                   ("We return to our main task", "setup", "Return to (5.3)"),
                   ("As usual, in the main setting", "apply_lemma", "Lemma 5.2 bounds the four penalty terms"),
                   ("Adding all these inequalities, we obtain~\\eqref{suff-for-first-est}.", "conclude", "Add the four bounds")])
eq("F46", "Fibring identity for the first choice (5.1)")
eq("F48", "Hypothesis on the fibre pair (5.2)")
eq("F49", "Sufficient penalty bound (5.3)")
env("LP2", "F50", "lemma", "Conditioning increases Ruzsa distance by at most half the mutual informations",
    statement_short="$d[X|Z;Y|W]\\le d[X;Y]+\\frac12 I[X:Z]+\\frac12 I[Y:W]$.", tags=["entropy", "bound"])
byid["LP2"]["assumptions"] = [sub("LP2", r"$(X, Z)$ and $(Y, W)$ are random variables", "take values in some abelian group")]
byid["LP2"]["conclusions"] = [sub("LP2", r"\[    \dist{X  | Z}", r"\I{Y : W}.\]")]
env("PP9", "F51", "proof", "Proof of Lemma 5.1", proof_strategy=["algebraic_manipulation"],
    statement_short="Use the alternative formula for conditional distance and drop the conditioning in the joint entropy.")
s9 = steps("PP9", [("The definition of conditional distance", "setup", "Recall the definition of conditional distance"),
                   ("Using the alternative expression", "algebraic_manipulation", "Expand and drop the conditioning"),
                   ("Here, in the middle step we used", "invoke_identity", "Justify the steps")])
env("LP3", "F54", "lemma", "Distance to a sum or a fibre (Lemma 5.2)",
    statement_short="Replacing $Y$ by $Y-Z$, or by $(Y|Y-Z)$, raises the distance to $X$ by at most $\\frac12 d[Y;Z]\\pm\\frac14(H[Z]-H[Y])$.",
    tags=["entropy", "bound"])
byid["LP3"]["assumptions"] = [sub("LP3", r"$X, Y, Z$ be random variables taking values in some abelian group"), sub("LP3", r"with $Y, Z$ independent")]
byid["LP3"]["conclusions"] = [sub("LP3", r"\begin{align}\nonumber \dist{X}{Y - Z}", r"\end{align}"),
                              sub("LP3", r"\begin{align}\nonumber \dist{X}{Y|Y-Z}", r"\tfrac{1}{4} \ent{Z}.")]
eq("F55", "Distance to a sum (5.5)")
eq("F56", "Distance to a fibre (5.6)")
env("PP10", "F57", "proof", "Proof of Lemma 5.2", proof_strategy=["algebraic_manipulation"],
    statement_short="(5.5) from the Kaimanovich-Vershik-Madiman inequality; (5.6) from Lemma 5.1 with $I[Y:Y-Z]=H[Y-Z]-H[Z]$.")
s10 = steps("PP10", [("We first prove~\\eqref{lem51-a}.", "setup", "Make X independent of Y, Z"),
                     ("Then we have\n", "algebraic_manipulation", "Write the difference in entropies"),
                     ("Combining this with~\\eqref{kv-2}", "apply_lemma", "Apply the Kaimanovich-Vershik-Madiman inequality"),
                     ("Turning to~\\eqref{ruzsa-3}, we have", "conclude", "Compute I[Y:Y-Z] and apply Lemma 5.1")])
eq("F60", "Penalty bound for the first fibre (5.7)")
eq("F61", "Penalty bound for the second fibre (5.8)")
prose("ClP12", "claim", "Entropy of the four-fold sum (HS bound)", "For use in the next two sections, we note that",
      r"(2 + \eta) k - I_1." + "\n" + r"\end{equation}", conf=0.8,
      statement_short="$H[X_1+X_2+\\tilde X_1+\\tilde X_2]\\le\\frac12H[X_1]+\\frac12H[X_2]+(2+\\eta)k-I_1$.")
eq("F62", "Entropy of the four-fold sum (5.9)")

# ------------------------------------------------------------------ 6 Second estimate
i6 = S.index("In this section we establish the upper bound~\\eqref{second-est}")
j6 = S.index(r"\end{align}", S.index(r"\I{ X_1+X_2 : X_1 + \tilde X_1 | X_1+X_2+\tilde X_1+\tilde X_2 } \leqslant 2 \eta k + \frac{2\eta(2\eta k - I_1)}{1-\eta}.")) if False else None
end6 = S.index(r"\leqslant 2 \eta k + \frac{2\eta(2\eta k - I_1)}{1-\eta}." + "\n" + r"\]") + len(r"\leqslant 2 \eta k + \frac{2\eta(2\eta k - I_1)}{1-\eta}." + "\n" + r"\]")
add("PP11", "proof", "Proof of the second estimate (Section 6)", norm(S[i6:end6]), i6, end6, conf=0.85, proves="ClP10",
    proof_strategy=["contradiction"],
    statement_short="Test the hypothesis on the pairs (3.2), (3.4) via the fibring identity with $(X_2,X_1,\\tilde X_2,\\tilde X_1)$. Bound $d[X_1;X_1]+d[X_2;X_2]$ through the four-fold sum bound (5.9) rather than the triangle inequality.")
s11 = steps("PP11", [("In this section we establish the upper bound~\\eqref{second-est}", "setup", "State the goal (3.14)"),
                     ("We apply \\Cref{cor-fibre} (and Remark \\ref{rem:char2}), but now", "apply_lemma", "Fibring identity with (X2, X1, tX2, tX1)"),
                     ("From~\\eqref{to-contradict} and~\\eqref{to-contradict-avg} as before", "apply_lemma", "Apply the hypothesis to the sum and fibre pairs"),
                     ("Now \\Cref{first-useful} gives", "apply_lemma", "Lemma 5.2 bounds the penalties by d[Xi;Xi]/2"),
                     ("Combining all these inequalities and cancelling terms", "algebraic_manipulation", "Combine to bound I_2 by eta(d[X1;X1]+d[X2;X2])"),
                     ("One could bound the right-hand side by $4\\eta k$", "bound_estimate", "Lower bound (6.5) for the sum distance"),
                     ("We may also expand", "bound_estimate", "Upper bound via the four-fold sum bound (5.9)"),
                     ("Combining this bound with~\\eqref{d12}", "bound_estimate", "Bound d[X1;X1]+d[X2;X2] (6.6)"),
                     ("Therefore by~\\eqref{combined} we have the desired bound", "conclude", "Conclude (3.14)")])
for f, nm in [("F64", "Hypothesis on the sum pair (6.1)"), ("F66", "Penalty bound (6.2)"), ("F67", "Penalty bound (6.3)"),
              ("F68", "I_2 bounded by self-distances (6.4)"), ("F69", "Lower bound on the sum distance (6.5)"),
              ("F71", "Bound on the self-distances (6.6)")]:
    eq(f, nm)

# ------------------------------------------------------------------ 7 Endgame
i7 = S.index(r"In this section we conclude the proof of \Cref{de-prop}.")
e7s = r"The proof of \Cref{de-prop} (and hence of all our results) is complete."
j7 = S.index(e7s) + len(e7s)
add("PP12", "proof", "Endgame: proof of Proposition 2.1 (Section 7)", norm(S[i7:j7]), i7, j7, conf=0.9, proves="PrP1",
    proof_strategy=["contradiction"],
    statement_short="Under the hypothesis, feed $T_i=(U|S=s),(V|S=s),(W|S=s)$ with $U+V+W=0$ (characteristic 2) into Lemma 7.2. With the first and second estimates this gives $k\\le(8\\eta+\\eta^2)k$, so $k=0$.")
s12 = steps("PP12", [("In this section we conclude the proof of \\Cref{de-prop}.", "setup", "Lemma 7.1"),
                     ("Turning now to the main argument", "introduce_variable", "Introduce U, V, W and S"),
                     ("From the definitions~\\eqref{first-est-a}", "substitute", "Express I_1, I_2, I_3 through U, V, W, S"),
                     ("Recall from~\\eqref{first-est} that", "setup", "Recall the first estimate"),
                     ("From~\\eqref{second-est} (and since $I_2 = I_3$)", "bound_estimate", "Sum of the three conditional mutual informations (7.2)"),
                     ("We assemble some preliminary estimates on distances.", "apply_lemma", "Lemma 7.1 bounds the penalties of U|S, V|S, W|S"),
                     ("To treat $\\dist{X^0_2}{W|S}$", "apply_lemma", "Penalty of W|S via W'"),
                     ("Summing these six estimates and using~\\eqref{HS-bound}", "bound_estimate", "Total penalty bound (7.3)"),
                     ("Now we come to the key observation", "invoke_identity", "Key observation U + V + W = 0 (characteristic 2)"),
                     ("To see the force of~\\eqref{uvw-s}", "setup", "Lemma 7.2"),
                     ("Applying \\Cref{lem:abstract} with any random variables", "apply_lemma", "Lemma 7.2 and the hypothesis give k <= delta + ..."),
                     ("In particular we may apply this for", "substitute", "Apply to the fibres of U, V, W over S and average (7.8)"),
                     ("Putting this together with~\\eqref{uvw-s} and~\\eqref{total-dist}", "bound_estimate", "k <= (8 eta + eta^2) k"),
                     ("Moreover, for\\footnote", "conclude", "8 eta + eta^2 < 1, so k = 0")])
env("LP4", "F72", "lemma", "Distance to a fibre of a double sum (Lemma 7.1)",
    statement_short="Bound on $d[X;Y-Z|Y-Z-Z']-d[X;Y]$ for independent $Y,Z,Z'$.", tags=["entropy", "bound"])
byid["LP4"]["assumptions"] = [sub("LP4", r"$X, Y, Z, Z'$ be random variables taking values in some abelian group"), sub("LP4", r"with $Y, Z, Z'$ independent")]
byid["LP4"]["conclusions"] = [sub("LP4", r"\begin{align}\nonumber", r"\end{align}")]
eq("F73", "Double-sum fibre bound (7.1)")
env("PP13", "F74", "proof", "Proof of Lemma 7.1", proof_strategy=["direct"],
    statement_short="Add the fibre bound (5.6), after a change of variables, to the sum bound (5.5).")
for f, nm in [("F75", "Sum of conditional mutual informations of U, V, W (7.2)"), ("F77", "Total penalty bound (7.3)"),
              ("F78", "U + V + W = 0 (7.4)")]:
    eq(f, nm)
env("LP5", "F79", "lemma", "Endgame lemma for a trio summing to zero (Lemma 7.2)",
    statement_short="If $T_1+T_2+T_3=0$, some pair $T'_1,T'_2$ has $\\tau$-type cost at most $\\delta$ plus $\\eta/3$ times penalties, $\\delta$ the pairwise mutual informations.",
    tags=["entropy", "characteristic_2"])
byid["LP5"]["assumptions"] = [sub("LP5", r"$G=\mathbf{F}_2^n$"), sub("LP5", r"$(T_1,T_2,T_3)$ be a $G^3$-valued random variable such that $T_1+T_2+T_3=0$ holds identically")]
byid["LP5"]["conclusions"] = [sub("LP5", r"there exist random variables $T'_1, T'_2$ such that", r"\end{align*}")]
eq("F80", "Definition of delta (7.5)")
env("PP14", "F82", "proof", "Proof of Lemma 7.2", proof_strategy=["probabilistic", "direct"],
    statement_short="Apply entropic BSG to $(T_1,T_2)$ with $T_1+T_2=T_3$, pick a good fibre $t_3$, and average over the six permutations.")
s14 = steps("PP14", [("We apply the variant of the entropic Balog", "apply_lemma", "Entropic BSG applied to (T1, T2)"),
                     ("The right-hand side in~\\eqref{bsg-t1t2} can be rearranged", "algebraic_manipulation", "The right-hand side equals delta"),
                     ("We also have\n", "apply_lemma", "Lemma 5.1 bounds the penalties of the fibres"),
                     ("Temporarily define", "introduce_variable", "Define psi"),
                     ("Putting the above observations together", "bound_estimate", "Average psi over t3"),
                     ("Choosing some $t_3$ in the support", "introduce_variable", "Choose a fibre t3 minimising psi (7.7)"),
                     ("We now repeat this analysis for all permutations", "conclude", "Average over the six permutations")])
eq("F83", "BSG bound for the fibres (7.6)")
eq("F88", "Bound for the chosen fibre (7.7)")
eq("F89", "Averaged endgame bound (7.8)")

# ------------------------------------------------------------------ A Entropy and additive combinatorics
prose("ClP13", "claim", "Entropy at most log of support size", "First we remark that if $X$ takes values in a set $S$",
      r"\ent{X} \leqslant \log |S|.\end{equation}", origin="external", conf=0.75, origin_citation=STD)
eq("F91", "Jensen bound (A.1)", "external", origin_citation=STD)
prose("ClP14", "claim", "Largest atom at least exp(-H)", "Also, denoting by $p_X$ the density function of $X$",
      r"\geqslant e^{-\ent{X}}.\end{equation}", origin="external", conf=0.75, origin_citation=STD)
eq("F92", "Largest atom bound (A.2)", "external", origin_citation=STD)
prose("DP12", "definition", "Conditional entropy", "Given a pair $(X,Y)$ of random variables, the \\emph{conditional entropy}",
      "conditioned on the event $Y=y$.", origin="external", conf=0.9, origin_citation=STD,
      definiendum=["conditional entropy $\\ent{X|Y}$", "$X|Y=y$"])
env("TP14", "F93", "theorem", "Chain rule for entropy", "external", 0.9, origin_citation=STD, assumptions=[],
    conclusions=[norm(F["F93"]["statement"])])
prose("DP13", "definition", "Abbreviation H[X,Y]", r"Here we abbreviate $\ent{(X,Y)}$ as $\ent{X,Y}$",
      r"becomes $\ent{X,Y|Z,W}$.", origin="external", conf=0.75, origin_citation=STD, definiendum="$\\ent{X,Y}$")
prose("ClP15", "claim", "Conditional chain rule", r"Note that~\eqref{chain-rule} implies a conditional generalization",
      "for all random variables $X,Y,Z$.", origin="external", conf=0.75, origin_citation=STD)
prose("DP14", "definition", "Mutual information", r"The \emph{mutual information} $\I{X:Y}$ is defined by the formula",
      "always.", after=65900, origin="external", conf=0.85, origin_citation=STD, definiendum="mutual information $\\I{X:Y}$",
      statement_short="$I[X:Y]=H[X]+H[Y]-H[X,Y]\\ge 0$, zero iff independent; hence (A.4) and $H[X|Y]\\le H[X]$.")
eq("F94", "Entropy of independent pair (A.4)", "external", origin_citation=STD)
eq("F95", "Conditioning reduces entropy (A.5)", "external", origin_citation=STD)
prose("TP15", "theorem", "Submodularity of entropy", r"Suppose now that $(X,Y,Z)$ is a triple of random variables.",
      r"\ent{X,Z} + \ent{Y,Z}.\end{equation}", origin="external", conf=0.85, origin_citation=STD,
      statement_short="$H[X|Y,Z]\\le H[X|Z]$, equivalently $H[X,Y,Z]+H[Z]\\le H[X,Z]+H[Y,Z]$.")
eq("F96", "Submodularity (A.6)", "external", origin_citation=STD)
eq("F97", "Submodularity, joint form (A.7)", "external", origin_citation=STD)
prose("DP15", "definition", "Conditional mutual information", r"The \emph{conditional mutual information} $\I{X:Y|Z}$ is defined by",
      r"\I{ (X|Z=z) : (Y|Z=z)}." + "\n" + r"\]", origin="external", conf=0.9, origin_citation=STD,
      definiendum="conditional mutual information $\\I{X:Y|Z}$")
prose("ClP16", "claim", "Non-negativity of conditional mutual information", "Submodularity is equivalent to the statement that",
      r"\ent{X,Y,Z} - \ent{Z}.\end{equation}", origin="external", conf=0.75, origin_citation=STD)
eq("F98", "I[X:Y|Z] >= 0 (A.8)", "external", origin_citation=STD)
eq("F99", "Conditional mutual information formula (A.9)", "external", origin_citation=STD)
prose("ClP17", "claim", "Equality case: conditional independence", r"Equality occurs in~\eqref{nonneg-cond}",
      "conditionally independent relative to $Z$.", origin="external", conf=0.75, origin_citation=STD)
prose("ClP18", "claim", "Sumset lower bound", "Whenever $X,Y$ are $G$-valued random variables, we have",
      r"\leqslant \ent{X\pm Y}." + "\n" + r"\end{equation}", origin="external", conf=0.75, origin_citation=STD)
eq("F100", "Sumset lower bound (A.10)", "external", origin_citation=STD)
prose("ClP19", "claim", "Conditional sumset lower bound", r"We note also the conditional variant of~\eqref{sumset-lower-gen}",
      "(weighted by $p_Z(z)$).", after=67900, origin="external", conf=0.75, origin_citation=STD)
prose("ClP20", "claim", "Sumset lower bound for independent variables", r"A particular consequence of~\eqref{sumset-lower-gen}",
      "when $X,Y$ are independent.", origin="external", conf=0.75, origin_citation=STD)
eq("F101", "max(H[X],H[Y]) <= H[X +- Y] (A.11)", "external", origin_citation=STD)
prose("ClP21", "claim", "Entropy difference bounded by twice the distance", r"Comparing this with~\eqref{sumset-lower} we see that",
      r"\leqslant 2\dist{X}{Y}." + "\n" + r"\end{equation}", origin="external", conf=0.75, origin_citation=STD)
eq("F102", "|H[X]-H[Y]| <= 2 d[X;Y] (A.12)", "external", origin_citation=STD)
prose("ClP22", "claim", "Sum entropy minus entropy bounded by twice the distance", "We may also deduce that",
      r"\leqslant 2\dist{X}{Y}." + "\n" + r"\]", after=68700, origin="external", conf=0.7, origin_citation=STD)
prose("TP16", "theorem", "Ruzsa triangle inequality", "The most important property of the Ruzsa distance",
      r"\dist{Z}{Y}.\]", origin="external", conf=0.9, origin_citation="Ruzsa 2009; " + TAO + " (16)",
      assumptions=[], conclusions=[r"$\dist{X}{Y} \leqslant \dist{X}{Z} + \dist{Z}{Y}.$"])
byid["TP16"]["conclusions"] = [sub("TP16", r"\[ \dist{X}{Y} \leqslant \dist{X}{Z} + \dist{Z}{Y}.\]")]
prose("PP15", "proof", "Proof of the Ruzsa triangle inequality", "This is equivalent to establishing",
      "we do not in fact use the independence of $X$ and $Y$ here.)", conf=0.85, proves="TP16",
      proof_strategy=["algebraic_manipulation"],
      statement_short="Reduce to $H[X-Y]\\le H[X-Z]+H[Z-Y]-H[Z]$ and get it from $I[X-Z:Y|X-Y]\\ge 0$.")
s15 = steps("PP15", [("This is equivalent to establishing", "setup", "Reduce to the entropy inequality (A.13)"),
                     ("To prove this, apply~\\eqref{nonneg-cond}", "apply_lemma", "Non-negativity of I[X-Z:Y|X-Y]"),
                     ("Using\n", "conclude", "Rewrite the entropies and rearrange")])
eq("F103", "Entropy form of the triangle inequality (A.13)")
prose("DP16", "definition", "Conditional Ruzsa distance", r"If $(X, Z)$ and $(Y, W)$ are random variables (where $X$ and $Y$ are $G$-valued) we define",
      r"\end{equation}", after=69929, origin="external", conf=0.9, origin_citation=TAO + "; " + GMT,
      definiendum="conditional Ruzsa distance $\\dist{X | Z}{Y | W}$")
eq("F104", "Conditional distance (A.14)", "external", origin_citation=TAO)
prose("ClP23", "claim", "Alternative formula for conditional distance", "Alternatively, if $(X',Z'), (Y',W')$ are independent copies",
      r"\tfrac{1}{2}\ent{Y'|W'} .\end{equation}", origin="external", conf=0.75, origin_citation=STD)
eq("F105", "Conditional distance via copies (A.15)", "external", origin_citation=STD)
env("LP6", "F106", "lemma", "Kaimanovich-Vershik-Madiman inequality", "external",
    origin_citation="Madiman 2008, Theorem I; Kaimanovich & Vershik 1983",
    also_stated_at=[norm(F["F53"]["statement"])],
    statement_short="$H[X+Y+Z]-H[X+Y]\\le H[Y+Z]-H[Y]$ for independent $X,Y,Z$ (entropy Plunnecke).", tags=["entropy", "plunnecke"])
byid["LP6"]["assumptions"] = [sub("LP6", "$X, Y, Z$ are independent random variables taking values in an abelian group")]
byid["LP6"]["conclusions"] = [sub("LP6", r"\[", r"\]")]
env("PP16", "F107", "proof", "Proof of the Kaimanovich-Vershik-Madiman inequality", proof_strategy=["algebraic_manipulation"],
    statement_short="Expand $I[X:Z|X+Y+Z]$ using independence; non-negativity is the inequality.")
s16 = steps("PP16", [("By~\\eqref{cond-form-mutual-2} we have", "invoke_identity", "Expand I[X:Z|X+Y+Z]"),
                     ("However, using~\\eqref{indep} three times", "substitute", "Simplify the joint entropies by independence"),
                     ("After a short calculation", "conclude", "The inequality is I[X:Z|X+Y+Z] >= 0")])
env("LP7", "F109", "lemma", "Entropic Balog-Szemeredi-Gowers lemma (variant)",
    statement_short="For a joint pair $(A,B)$ with $Z=A+B$, the fibres $(A|Z=z),(B|Z=z)$ have average distance at most $3I[A:B]+2H[Z]-H[A]-H[B]$.",
    tags=["entropy", "balog_szemeredi_gowers"])
byid["LP7"]["assumptions"] = [sub("LP7", r"$(A,B)$ be a $G^2$-valued random variable"), sub("LP7", r"set $Z \coloneqq A+B$")]
byid["LP7"]["conclusions"] = [sub("LP7", r"\sum_{z} p_Z(z)", r"- \ent{A} - \ent{B}.")]
eq("F110", "Entropic BSG bound (A.16)")
env("PP17", "F111", "proof", "Proof of the entropic Balog-Szemeredi-Gowers lemma", proof_strategy=["probabilistic", "algebraic_manipulation"],
    statement_short="Take conditionally independent trials of $(A,B)$ relative to $Z$, bound $H[A_1-B_2]$ by submodularity and compute the conditional entropies.")
s17 = steps("PP17", [("In the proof we will need the notion", "introduce_variable", "Conditionally independent trials"),
                     ("We then have\n", "algebraic_manipulation", "Entropy of conditionally independent trials (A.17)"),
                     ("Turning to the proof of \\Cref{lem-bsg} itself", "introduce_variable", "Take trials (A1,B1), (A2,B2) relative to Z"),
                     ("Observe that the left-hand side of~\\eqref{2-bsg-takeaway} is", "substitute", "Rewrite the left-hand side (A.18)"),
                     ("Applying submodularity~\\eqref{submod-basic} gives", "apply_lemma", "Submodularity (A.19)"),
                     ("We estimate the second, third and fourth terms", "bound_estimate", "Estimate the three terms (A.20)-(A.22)"),
                     ("Substituting~\\eqref{bsg-24}", "bound_estimate", "Bound H[A1-B2|Z]"),
                     ("Since\n\\begin{align*} \\ent{A_1 | Z}", "conclude", "Compute H[A1|Z], H[B2|Z] and conclude")])
for f, nm in [("F112", "Entropy of conditionally independent trials (A.17)"), ("F113", "Left-hand side rewritten (A.18)"),
              ("F114", "Submodularity applied (A.19)"), ("F115", "Joint entropy of the trials (A.20)"),
              ("F116", "Bound (A.21)"), ("F117", "Bound (A.22)")]:
    eq(f, nm)

# ------------------------------------------------------------------ B From entropic PFR to combinatorial PFR
iB = S.index("In this appendix we repeat the arguments from~\\cite{gmt}")
eB = r"translates of $H'$, and the claim again follows from~\eqref{ah}."
jB = S.index(eB) + len(eB)
add("PP18", "proof", "Proof that Theorem 1.8 implies Theorem 1.2 (Appendix B)", norm(S[iB:jB]), iB, jB, conf=0.9, proves="TP5",
    proof_strategy=["construction"],
    statement_short="Apply Theorem 1.8 to $X_1^0=X_2^0=U_A$; a large atom of $U_A-U_H$ gives a dense coset intersection, then Ruzsa covering.")
sB = steps("PP18", [("In this appendix we repeat the arguments", "setup", "Theorem 1.8 with C' gives Theorem 1.2 with C = C'+1"),
                    ("Let $A,K$ be as in \\Cref{pfr}.", "introduce_variable", "Uniform variable U_A"),
                    ("By~\\eqref{convexity-bound} and the fact that", "bound_estimate", "d[U_A;U_A] <= log K"),
                    ("By \\Cref{pfr-entropy}, we may thus find", "apply_lemma", "Theorem 1.8 gives H (B.1)"),
                    ("By~\\eqref{ruzsa-diff} we conclude that", "bound_estimate", "|log|H| - log|A|| <= C' log K (B.2)"),
                    ("From definition of Ruzsa distance", "substitute", "Unfold the Ruzsa distance"),
                    ("By~\\eqref{px-lower} we conclude", "bound_estimate", "A large atom: a dense coset intersection"),
                    ("Applying the Ruzsa covering lemma", "apply_lemma", "Ruzsa covering lemma"),
                    ("If $|H| \\leqslant |A|$ then", "case_split", "Case |H| <= |A|"),
                    ("If $|H| > |A|$ then", "case_split", "Case |H| > |A|: pass to a subgroup H'")])
eq("F119", "d[U_A;U_H] bound (B.1)")
eq("F120", "Size of H (B.2)")

# ------------------------------------------------------------------ sort nodes into document order (Level-1 by position)
order = sorted(range(len(nodes)), key=lambda k: (POS[nodes[k]["id"]][0], -POS[nodes[k]["id"]][1]))
nodes[:] = [nodes[k] for k in order]

# ------------------------------------------------------------------ edges (beyond \ref, added by the finishing step)
# pass 1/3: results named in words, and results / proofs
E("CnjP1", "TP5", "resolves", 0.95, None)
E("CnjP1", "ClP1", "uses", 0.95, None, mention=True)
E("CnjP1", "TP1", "uses", 0.7, "inferred", mention=True)
E("CnjP1", "TP2", "uses", 0.7, "inferred", mention=True)
E("CnjP1", "TP3", "uses", 0.7, "inferred", mention=True)
E("CnjP1", "TP4", "specializes", 0.95, None, mention=True)
E("TP5", "TP6", "uses", 0.95, None, mention=True)
E("TP9", "TP10", "uses", 0.95, None, mention=True)
E("CnjP1", "TP10", "uses", 0.85, "named", mention=True)
E("TP8", "CP4", "generalizes", 0.9, "named")
E("TP5", "PP3", "uses", 0.65, "inferred")
E("TP5", "CP3", "uses", 0.65, "inferred")
E("CP1", "CnjP2", "uses", 0.95, None, mention=True)
E("CnjP2", "TP11", "resolves", 0.9, "named")
E("CnjP3", "TP12", "uses", 0.7, "inferred", mention=True)
E("TP9", "DP5", "uses", 0.95, None, mention=True)
for x in ("PrP1", "TP9", "EP3"):
    E(x, "RP1", "uses", 0.95, None, mention=True)
# Section 5 opens by recalling its goal, the contrapositive of Prop 2.1 (a mention)
E("PrP1", "PP8", "uses", 0.95, None, mention=True)
E("PrP1", s8[0], "uses", 0.95, None, mention=True)
# plan text and examples name (2.2) as the goal to reach (mentions)
for t in ("ClP2", "ClP3", "RP3", "ExP1", "ExP2", "ExP3"):
    E("EP3", t, "uses", 0.95, None, mention=True)
# "Recalling (3.9), the proof below collapses to ..." is a reading hint (mention)
E("EP13", next(x for x in s12 if "Recalling~\\eqref{eq:i-eq-0}" in byid[x]["statement"]), "uses", 0.95, None, mention=True)
E("EP13", "PP12", "uses", 0.95, None, mention=True)
# "a particularly attractive application of Theorem 1.3 is the following result of Mudgal"
E("TP7", "CP4", "uses", 0.9, "named")
# the remark on odd p is about the argument of Sections 3-7
E("PP12", "RP4", "uses", 0.6, "inferred", mention=True)
# triangle inequality, named in words
E("TP16", "PP4", "uses", 0.9, "named")
E("TP16", "PP5", "uses", 0.9, "named")
E("TP16", "ExP1", "uses", 0.9, "named")
E("TP16", "RP1", "uses", 0.85, "named")
E("TP16", "PP11", "uses", 0.85, "named", mention=True)   # "One could bound ... using the Ruzsa triangle inequality"
E("TP16", "DP3", "uses", 0.6, "inferred", mention=True)
# submodularity named in the fibring lemma's proof
E("TP15", "PP6", "uses", 0.9, "named")
# Lemma 7.2's and BSG's proofs are separated from their lemmas by a paragraph
E("PP14", "LP5", "proves", 0.9, "named")
E("PP17", "LP7", "proves", 0.9, "named")
# examples illustrate the candidate pairs / the proposition
for x in ("ExP1", "ExP2", "ExP3"):
    E("DP10", x, "illustrates", 0.85, "named")
E("PrP1", "ExP4", "illustrates", 0.85, "named")
E("LP7", "ExP3", "uses", 0.95, None)
# the heuristic plan claims feed the precise estimates (motivation only)
E("ClP2", "ClP9", "uses", 0.9, "named", mention=True)
E("ClP3", "ClP10", "uses", 0.9, "named", mention=True)
E("ClP5", "ClP7", "uses", 0.7, "inferred")
E("ClP6", "ClP7", "uses", 0.7, "inferred")
E("AssumP1", "ClP8", "uses", 0.95, "named")
# the hypothesis is the standing assumption of Sections 5-7
for x in ("PP8", "PP11", "PP12", "ClP11", "ClP12"):
    E("AssumP1", x, "uses", 0.8, "inferred")
# the first estimate and the HS bound feed Sections 6 and 7
E("ClP9", "PP11", "uses", 0.85, "inferred")     # I_1 <= 2 eta k is used to keep 2 eta k - I_1 >= 0 ... in (3.14)'s statement
E("DP9", "DP10", "uses", 0.85, "term")
# pass 4: steps relying on earlier steps
def chain(ids, pairs):
    for a, b in pairs:
        E(ids[a], ids[b], "uses", 0.75, "inferred")
chain(s5, [(0, 1), (1, 2)])
chain(s6, [(0, 1), (2, 3)])
chain(s8, [(2, 3), (3, 4), (7, 8)])
chain(s11, [(1, 2), (2, 4), (3, 4), (5, 7), (6, 7), (7, 8), (4, 8)])
chain(s12, [(1, 2), (2, 4), (3, 4), (5, 7), (6, 7), (10, 11), (11, 12), (4, 12), (7, 12), (12, 13)])
chain(s14, [(0, 1), (1, 4), (2, 4), (3, 4), (4, 5), (5, 6)])
chain(s17, [(0, 1), (2, 3), (4, 5), (5, 6), (6, 7), (3, 7)])
chain(sB, [(1, 2), (2, 3), (3, 4), (3, 5), (5, 6), (6, 7), (4, 8), (4, 9)])
chain(s15, [(1, 2)])
chain(s16, [(0, 1), (1, 2)])
chain(s9, [(1, 2)])
chain(s10, [(1, 2)])

# pass 2: defined terms -> later Level-1 nodes (searched in statements, then reviewed)
L1 = [n for n in nodes if n["type"] not in ("proof_step", "algorithm_step")]
def parent_chain_has(nid, anc):
    return False
TERMS = {
    "DP1": [r"O\("],
    "DP17": [r"O\(\\eta k\)"],
    "DP2": [r"\\gg"],
    "DP3": [r"\\dist\{", r"\\bigdist\{", r"\\costa\{", r"\\costb\{", r"Ruzsa distance"],
    "DP4": [r"f\(2,K\)"],
    "DP5": [r"X\^0_[12]", r"X_[12]\^0", r"\\costa", r"\\costb", r"reference variables"],
    "DP6": [r"\\eta(?![a-zA-Z'])", r"\\costa", r"\\costb"],
    "DP7": [r"\\tau\["],
    "DP8": [r"(?<![A-Za-z\\_^{])k(?![A-Za-z])"],
    "DP9": [r"\\tilde X_[12]"],
    "DP11": [r"(?<![A-Za-z\\])K(?![A-Za-z])"],
    "DP12": [r"\\(?:ent|bigH)\{[^{}]*\|"],
    "DP13": [r"\\(?:ent|bigH)\{[^{}|]*,"],
    "DP14": [r"\\(?:I|bigI)\{", r"mutual information"],
    "DP15": [r"\\(?:I|bigI)\{[^{}]*\|"],
    "DP16": [r"\\(?:dist|bigdist)\{[^{}]*\|[^{}]*\}\{", r"\\(?:dist|bigdist)\{[^{}]*\}\{[^{}]*\|", r"conditional distance"],
}
# scope limits: a symbol defined for a part of the paper is only searched there
SCOPE = {"DP8": ("3 Plan of the remaining argument", None), "DP11": ("Motivating examples", "Motivating examples"),
         "DP9": None, "DP5": None, "DP6": None, "DP7": None}
SKIP = {("DP14", "DP15"), ("DP12", "DP15"), ("DP12", "DP13")}
APPENDIX_DEFS = {"DP12", "DP13", "DP14", "DP15", "DP16"}    # "Basic definitions and facts are recalled in Appendix A"
have = {(e["source"], e["target"]) for e in edges}
term_edges = []
for d, pats in TERMS.items():
    ds, de = POS[d]
    for n in L1:
        if n["id"] == d or n["type"] == "equation":
            continue
        ns, ne = POS[n["id"]]
        if ds <= ns and ne <= de:
            continue                          # nested inside the definition
        if ns < ds and d not in APPENDIX_DEFS:
            continue                          # only later nodes
        if ns < ds and d in APPENDIX_DEFS and ne > ds:
            continue
        if d == "DP8" and not (S.index(r"\section{Plan of the remaining argument}") <= ns < S.index(r"\appendix")):
            continue
        if d == "DP11" and n["type"] != "example":
            continue
        if d in ("DP5", "DP6", "DP7", "DP9") and ns > S.index(r"\appendix"):
            continue
        if (d, n["id"]) in SKIP or (d, n["id"]) in have:
            continue
        st = n["statement"]
        if any(re.search(p, st) for p in pats):
            term_edges.append((d, n["id"]))
for d, t in term_edges:
    E(d, t, "uses", 0.75, "term")
json.dump(term_edges, open(SCR + "/term_edges.json", "w"))

meta = {
    "title": "On a conjecture of Marton",
    "arxiv_id": "2311.05762",
    "annotator": "agent-extraction",
    "model": "claude-opus-5-5",
    "effort": "default",
    "prompt_version": "v7-86dcfbecdc4d78a5-78180fe",
    "extraction_date": "2026-11-03",
    "rigor_nonformal_count": sum(1 for n in nodes if "rigor" in n),
    "paper_style": ["theorem_proof"],
    "extraction_notes": [],
    "extraction_comment": "",
}
graph = {"metadata": meta, "nodes": nodes, "edges": edges}
NOTES = json.load(open(SCR + "/notes.json")) if len(sys.argv) > 1 else []
meta["extraction_notes"] = NOTES
report = finalize(graph, read_tex(TEX))
json.dump(report, open(SCR + "/report.json", "w"), indent=1, default=str)
print("errors", len(report["errors"]))
for e in report["errors"]:
    print("  E", e)
print("warnings", len(report["warnings"]))
for w in report["warnings"]:
    print("  W", w)
if not report["errors"]:
    json.dump(graph, open(OUT if len(sys.argv) > 1 else SCR + "/draft.json", "w"), indent=1, ensure_ascii=False)
    print("written", len(nodes), "nodes", len(edges), "edges")
