#!/usr/bin/env python3
"""Build the v7 LLM extraction of arXiv 1510.05214, 'Clustering Noisy Signals with Structured
Sparsity Using Time-Frequency Representation' (Hope, Wagner, Zuk 2015). Nodes, types, spans and edges were chosen by reading
the paper; this script only slices the chosen spans out of the prepared source, assembles the graph
and runs finalize().  Usage: python3 build.py [--write]"""
import json, re, sys, subprocess, os
REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize
from latex_facts import read_tex

SCR = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_orzuk/1510_05214"
CASE = REPO + "/corpus/orzuk/1510_05214"
TEX = CASE + "/arxiv_src/WaveletsSparseClustering_Arxiv01.tex"
OUT = CASE + "/1510_05214.json"
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


def prose(nid, typ, name, a, b, lo=0, origin="paper", conf=0.75, lo2=None, **kw):
    i, _ = find(a, lo if lo2 is None else lo2)
    _, j = find(b, max(i, lo))
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

WT = "Witten & Tibshirani 2010"
MAL = "Mallat 2012"


def ep(nid, fid, name, **kw):
    return env(nid, fid, "equation", name, kw.pop("origin", "paper"), 1.0, **kw)


def astep(parent, a, b, subclass, name, short=None, conf=0.7):
    return step(parent, a, b, subclass, name, short, conf, typ="algorithm_step")


# ============================================================ 1 Introduction
prose("DP1", "definition", "SPARCWave", "We introduce SPARCWave", "in our sparse clustering method.", conf=0.85,
      definiendum="SPARCWave", genus="a framework of methods for sparse clustering of noisy signals",
      differentia=["uses ``global\" cross-signal information for smoothing and dimensionality reduction simultaneously",
                   "is geared towards preserving clustering information",
                   "exploits structure in the signal representation",
                   "uses the scattering transform"],
      statement_short="SPARCWave: sparse clustering of noisy signals in a time-frequency (wavelet / scattering) representation, exploiting structured sparsity.")

# ============================================================ 2 Related Work
prose("AP1", "algorithm", "Wavelet-denoise-then-cluster (Giacofci et al.)", "Giacofci et al. \\cite{giacofci2013wavelet} first perform",
      "non-zero coefficients after shrinkage.", origin="external", origin_citation="Giacofci et al. 2013", conf=0.75,
      statement_short="Denoise each signal by wavelet shrinkage, then model-based clustering on the union of surviving coefficients.")
astep("AP1", "first perform wavelets-based denoising", "for each signal,", "compute", "Per-signal wavelet denoising")
astep("AP1", "then use model-based clustering", "after shrinkage", "call", "Model-based clustering on non-zero coefficients")
prose("AP2", "algorithm", "Multi-scale energy features (Antoniadis et al.)", "Antoniadis et al. \\cite{antoniadis2013clustering} use the fact",
      "relative importance.", origin="external", origin_citation="Antoniadis et al. 2013", conf=0.7,
      statement_short="Cluster on features that average wavelet coefficients within each scale and weigh each scale's relative energy.")
astep("AP2", "extracting features that involve averaging", "in each scale", "compute", "Average wavelet coefficients per scale")
astep("AP2", "measuring each scale's", "relative importance", "compute", "Measure each scale's relative importance")
prose("RP1", "remark", "Scale averaging loses time information", "However, this averaging loses the time information:",
      "which may lead to clustering errors.", conf=0.75,
      statement_short="Averaging all wavelets at a scale discards timing: signals with equal power spectra get similar features.")
prose("AP3", "algorithm", "Dynamic Time Warping", "A common approach to dealing with deformations is the Dynamic Time Warping",
      "to align pairs of signals.", origin="external", origin_citation="Berndt & Clifford 1994", conf=0.7,
      statement_short="DTW: align pairs of signals by dynamic programming before comparing them.")

# ============================================================ 3.1 Wavelets Background
i0 = find("More formally, a wavelet family")[0]
prose("DP2", "definition", "Wavelet family", "More formally, a wavelet family", "and $k$ translations.", conf=0.9,
      origin="external", origin_citation=STD, definiendum="wavelet family $\\Psi_{j,k}$",
      genus="a set of functions", differentia=["generated by dilations and translations of a unique mother wavelet $\\Psi$"],
      statement_short="Wavelet family: dilations and translations $a^{j/2}\\Psi(a^j t-k)$ of a mother wavelet $\\Psi$.")
ep("EP1", "F1", "Dilation-translation of the mother wavelet", origin="external", origin_citation=STD)
prose("DP3", "definition", "Scaling function family", "We similarly define a family of functions $\\phi_{0,k}$",
      "formulation given in eq. (\\ref{def:wave_funcs}).", conf=0.85, origin="external", origin_citation=STD,
      definiendum="$\\phi_{0,k}$", genus="a family of functions",
      differentia=["derived from a scaling function $\\phi(t)$ by using the dilation and translation formulation"])
prose("TP1", "theorem", "Wavelet decomposition", "Any function $f \\in L^2(\\mathbb{R})$ can then be decomposed",
      "called the wavelet coefficients of $f(t)$.", conf=0.7, origin="external", origin_citation=STD,
      assumptions=["Any function $f \\in L^2(\\mathbb{R})$"],
      conclusions=["can then be decomposed in terms of these functions"],
      statement_short="Every $L^2$ function expands in scaling functions and wavelets; the coefficients are inner products (scaling and wavelet coefficients).")
ep("EP2", "F2", "Wavelet expansion of f", origin="external", origin_citation=STD)
prose("DP4", "definition", "Discrete Wavelet Transform (DWT)", "This decomposition has a discrete version known as the Discrete Wavelet Transform",
      "and $\\langle \\Psi_{j,k}, \\mathbf{x} \\rangle$.", conf=0.85, origin="external", origin_citation=STD,
      definiendum="Discrete Wavelet Transform (DWT)",
      statement_short="DWT of a length-$T=2^J$ signal: the scaling coefficient $c_0$ and wavelet coefficients $v_{j,k}$ computed as discrete inner products.")
prose("DP5", "definition", "DWT matrix form", "The DWT can be written conveniently in a matrix form", "properly ordered.",
      conf=0.85, origin="external", origin_citation=STD, definiendum="$\\mathbf{W}$",
      statement_short="DWT as $\\mathbf{v}=\\mathbf{W}\\mathbf{x}$ with orthogonal $\\mathbf{W}$ determined by $\\Psi,\\phi$.")
prose("AP4", "algorithm", "Wavelet shrinkage denoising", "This property is typically used for signal denoising",
      "(|\\mathbf{v}| - \\lambda)_{+}$.", conf=0.8, origin="external", origin_citation="Donoho 1995",
      statement_short="Denoise by transforming to the wavelet domain, shrinking coefficients (e.g. soft-thresholding at $\\lambda$), and inverting.")
ep("EP3", "F3", "Wavelet shrinkage estimator", origin="external", origin_citation="Donoho 1995")

# ============================================================ 3.2 univariate
prose("DP6", "definition", "Signal instances and their DWT", "Consider $n$ instances (signal vectors)", "be their DWT transforms.",
      conf=0.85, definiendum=["$n$", "$\\mathbf{x}^{(i)}$", "$\\mathbf{v}^{(i)}$"])
prose("DP7", "definition", "Coordinate-wise squared distance", "Let $d_{i_{1},i_{2},j}$ be the squared",
      "(\\mathbf{v}_j^{(i_1)}-\\mathbf{v}_j^{(i_2)})^2$.", conf=0.85, definiendum="$d_{i_{1},i_{2},j}$")
prose("DP8", "definition", "Cluster index sets", "Let $C_{k}$ be the set of indices", "with $|C_k|=n_k$.", conf=0.85,
      definiendum=["$C_{k}$", "$n_k$"])
prose("DP9", "definition", "Between Cluster Sum of Squares (BCSS)", "In standard K-means clustering, the goal is to",
      "\\end{equation}", lo=find("Let $C_{k}$ be the set")[0], conf=0.85, origin="external", origin_citation=STD,
      definiendum=["Between Cluster Sum of Squares (BCSS)", "$\\mathcal{D}$"],
      statement_short="K-means maximizes the BCSS $1^T\\mathcal{D}$, where $\\mathcal{D}_j$ is coordinate $j$'s between-cluster contribution.")
ep("EP4", "F4", "Per-coordinate BCSS contribution", origin="external", origin_citation=STD)
prose("DP10", "definition", "Feature weights and sparsity parameter", "Let $\\mathbf{w} \\in \\mathbb{R}^T$ be a vector of weights",
      "bounding $\\|\\mathbf{w}\\|_1$.", conf=0.85, definiendum=["$\\mathbf{w}$", "$s$"])
prose("ProbP1", "problem", "Sparse K-means problem", "We get the following sparse K-means",
      "w_j \\geq 0, \\forall j=1,..,T \\}$.", conf=0.85, origin="external", origin_citation=WT,
      statement_short="Sparse K-means in the wavelet domain: maximize $\\mathbf{w}^T\\mathcal{D}$ over clusters and nonnegative $\\mathbf{w}$ in the $L_2$ unit ball and $L_1$ ball of radius $s$.")
ep("EP5", "F5", "Sparse K-means objective in the wavelet domain", origin="external", origin_citation=WT)
prose("AP5", "algorithm", "Sparse K-means algorithm", "In \\cite{witten2010framework} the authors propose an iterative algorithm",
      "Gap Statistic method \\cite{tibshirani2001estimating}.", conf=0.8, origin="external", origin_citation=WT,
      statement_short="Alternate K-means updates of the clusters with closed-form updates of the weights $\\mathbf{w}$; $s$ chosen by the gap statistic.")
lp = astep("AP5", "each iteration consists of", "with a closed-form expression", "loop", "Iterate")
astep(lp, "updating the clusters $C_j$", "by running K-means", "call", "Update clusters by K-means")
astep(lp, "updating $\\mathbf{w}$", "with a closed-form expression", "update", "Closed-form weight update")
astep("AP5", "The tuning parameter $s$ is set by", "\\cite{tibshirani2001estimating}.", "select", "Choose $s$ by the gap statistic")

# ============================================================ 3.3 Group sparse
prose("DP11", "definition", "Partition and group sub-vector", "Let $\\mathcal{G}$ be a partition of", "to group $g \\in \\mathcal{G}$.",
      conf=0.85, definiendum=["$\\mathcal{G}$", "$\\mathbf{v}_{(g)}$"])
prose("DP12", "definition", "Group size", "Let $|g|$ the number of elements in $g$.", "Let $|g|$ the number of elements in $g$.",
      conf=0.8, definiendum="$|g|$")
prose("DP13", "definition", "Group norm", "Define the group-norm with respect to the partition",
      "(other coefficients may also be used).", conf=0.85, origin="external", origin_citation="Bach et al. 2011",
      definiendum="group-norm $|| \\mathbf{v} ||_{\\mathcal{G}}$",
      statement_short="Group norm: sum over groups of $\\sqrt{|g|}$ times the $L_2$ norm of the group's sub-vector.")
ep("EP6", "F6", "Group norm", origin="external", origin_citation="Bach et al. 2011")
prose("ProbP2", "problem", "Group-sparse K-means problem", "Using the group norm, we define the group-sparse K-means problem",
      "\\end{equation}", lo=F["F6"]["outer_end"], conf=0.85,
      statement_short="Group-sparse K-means: sparse K-means with the $L_1$ constraint replaced by a group-norm ball of radius $s$.")
ep("EP7", "F7", "Group-sparse K-means objective")
prose("ClP1", "claim", "Group-sparse K-means generalizes sparse K-means", "generalizes the sparse K-means problem in eq.",
      "groups to have size $1$.", lo=POS["ProbP2"][1], conf=0.8, rigor="semi_formal",
      assumptions=["setting all groups to have size $1$"],
      conclusions=["Problem (\\ref{problem_group_sparse}) generalizes the sparse K-means problem in eq. (\\ref{eq:sparse_k_means_wavelet_ver2})"])
# fix the start: the sentence begins with "Problem (\ref{problem_group_sparse})"
n = byid["ClP1"]; a = find("Problem (\\ref{problem_group_sparse}) generalizes")[0]
n["statement"] = norm(S[a:POS["ClP1"][1]]); POS["ClP1"] = (a, POS["ClP1"][1])
prose("DP14", "definition", "Element-wise square root and product", "($\\sqrt{\\cdot}$ and $\\odot$ in step (a.)",
      "= w_j v_j$).", conf=0.8, definiendum=["$\\sqrt{\\cdot}$", "$\\odot$"])
prose("RP2", "remark", "Weight step as an SOCP", "Optimization $w.r.t$ $\\mathbf{w}$ can be done with standard",
      "by introducing auxiliary variables.", conf=0.75,
      statement_short="The weight update is a second-order cone program, solvable with standard SOCP solvers.")
env("AP6", "F8", "algorithm", "Group-Sparse K-means", main=True,
    input=["$\\mathbf{v}^{(1)},\\mathbf{v}^{(2)},...,\\mathbf{v}^{(n)}$, $K$, $iters$, $\\mathcal{G}$, $s$"],
    output=["Clusters $C_1,C_2,...,C_K$"],
    statement_short="Alternate K-means on $\\sqrt{\\mathbf{w}}$-weighted features with solving the group-sparse weight problem for fixed clusters.")
from extraction_finalize import pseudocode_steps
ps = pseudocode_steps(facts, "F8", byid["AP6"], first_seq=CNT["algorithm_step"][0] + 1)
info = {1: ("initialize", "Initialize uniform weights", None),
        2: ("loop", "Iterate iters times", None),
        3: ("call", "K-means on weighted features", "Run K-means on the $\\sqrt{\\mathbf{w}}$-scaled coefficient vectors."),
        4: ("solve", "Solve for weights", "With clusters fixed, solve the group-sparse problem for $\\mathbf{w}$."),
        5: ("return", "Return clusters", None)}
for k, s in enumerate(ps, 1):
    s["subclass"], s["name"], sh = info[k]
    if sh:
        s["statement_short"] = sh
    s["statement"] = norm(s["statement"])
    nodes.append(s); byid[s["id"]] = s
CNT["algorithm_step"][0] += len(ps)

# ---- 3.3.1
prose("DP15", "definition", "Scale-based wavelet group partition", "Therefore, we define the partitions $\\mathcal{G} =",
      "with the group norm defined by $\\mathcal{G}$.", conf=0.8, definiendum="$\\mathcal{G}$ (wavelet scales)",
      statement_short="Groups are the wavelet scales: $g_j$ holds the $2^j$ coefficients at level $j$.")
prose("RP3", "remark", "Other group structures for wavelet trees", "Our choice of $\\mathcal{G}$ in this work is not the only one",
      "as in \\cite{chen2012compressive}.", conf=0.75,
      statement_short="Alternatives: groups as connected sub-trees, or overlapping groups giving tree-structured sparsity.")
# ---- 3.3.2
prose("DP16", "definition", "Multivariate signal instance", "Let each instance $\\mathbf{X}^{(i)}$ be a multivariate signal",
      "(See Figure \\ref{fig:data_multi}).", conf=0.85, definiendum=["$\\mathbf{X}^{(i)}$", "$G$"])
prose("AP7", "algorithm", "Multivariate group-sparse clustering", "We transform each row of $\\mathbf{X}^{(i)}$",
      "comprising $\\mathbf{X}^{(i)}$.", lo=POS["DP16"][0], conf=0.75, main=True,
      input=["each instance $\\mathbf{X}^{(i)}$"],
      statement_short="DWT each variable, concatenate, and solve group-sparse K-means with groups = the same time-frequency coordinate across the $G$ variables.")
astep("AP7", "We transform each row", "to get $\\mathbf{V}^{(i)}$.", "compute", "Row-wise DWT")
astep("AP7", "We then concatenate the rows", "of length $G\\times T$", "compute", "Concatenate rows")
astep("AP7", "solve Problem (\\ref{problem_group_sparse}) with the group norm", "t = 1,..,T \\big\\}$.", "solve", "Solve with slice groups")
astep("AP7", "Each group corresponds to", "comprising $\\mathbf{X}^{(i)}$.", "other", "Groups are vertical time-frequency slices")
prose("RP4", "remark", "Prior behind the multivariate grouping", "Intuitively, this structure reflects the prior assumption",
      "to be different.", conf=0.75,
      statement_short="An active clustering feature at time-frequency point $t$ is expected active in all $G$ variables, with weights still free to differ.")

# ============================================================ 3.4 Scattering
prose("TP2", "theorem", "Wavelet transform is not translation invariant", "The wavelet transform is not invariant to translations and scaling.",
      "The wavelet transform is not invariant to translations and scaling.", conf=0.65, origin="external", origin_citation=STD,
      assumptions=[], conclusions=["The wavelet transform is not invariant to translations and scaling."])
prose("TP3", "theorem", "Instability of fine wavelet coefficients", "In addition, while the coarse-grain coefficients are stable",
      "unstable \\cite{mallat2012group}.", conf=0.65, origin="external", origin_citation=MAL,
      assumptions=["small deformations"],
      conclusions=["the coarse-grain coefficients are stable under small deformations", "the fine resolution coefficients are unstable"])
prose("DP17", "definition", "Scattering transform", "To overcome the effects of the above transformations",
      "given by a wavelet operator \\cite{anden2014deep}.", conf=0.8, origin="external", origin_citation=MAL,
      definiendum="scattering transform", genus="a recent extension of wavelets",
      differentia=["which is stable to such deformations"],
      statement_short="Scattering transform: a deformation-stable, unitary, nonlinear extension of wavelets computed like a convolutional network.")
prose("DP18", "definition", "Zeroth scattering layer", "For a function $f(t)$ the $0$-th scattering layer",
      "$\\phi$ is an averaging filter.", conf=0.85, origin="external", origin_citation=MAL,
      definiendum=["$S^{(0)}$", "$\\star$", "$\\phi$"])
ep("EP8", "F9", "Zeroth scattering layer", origin="external", origin_citation=MAL)
prose("DP19", "definition", "First-layer wavelet filter bank", "Let $\\{\\Psi^{(1)}_{j_1}\\}_{j_1 \\in J_1}$",
      "\\Psi(a_1^{j_1} t)$.", conf=0.85, origin="external", origin_citation=MAL,
      definiendum=["$\\Psi^{(1)}_{j_1}$", "$J_1$"], genus="a filter-bank",
      differentia=["containing different dilations of a complex mother wavelet function $\\Psi$"])
prose("DP20", "definition", "First scattering layer", "To regain translation invariance lost by applying",
      "deeper scattering layers \\cite{mallat2012group}.", conf=0.85, origin="external", origin_citation=MAL,
      definiendum="$S_{j_1}^{(1)}$")
ep("EP9", "F10", "First scattering layer", origin="external", origin_citation=MAL)
prose("DP21", "definition", "Second-layer filters", "To recover the high frequencies lost by averaging",
      "for some $j_2 \\in J_2$.", conf=0.75, origin="external", origin_citation=MAL,
      definiendum=["$\\Psi^{(2)}_{j_2}$", "$J_2$"])
prose("DP22", "definition", "Layer-l wavelet filters", "More generally, define $\\Psi^{(l)}_{j_l}(t)",
      "resolution at layer $l$.", conf=0.85, origin="external", origin_citation=MAL,
      definiendum=["$\\Psi^{(l)}_{j_l}$", "$a_l$"])
prose("DP23", "definition", "Scale path", "For a scattering layer $l$, let $(j_1,..,j_l)$", "along the scattering network.",
      conf=0.85, origin="external", origin_citation=MAL, definiendum="scale path")
prose("DP24", "definition", "l-th scattering layer", "This process above continues in the same way",
      "\\end{equation}", lo=POS["DP23"][0], conf=0.85, origin="external", origin_citation=MAL,
      definiendum="$S^{(l)}_{j_1,..,j_{l}}$",
      statement_short="Layer-$l$ scattering: iterate wavelet convolution and modulus along the scale path, then average with $\\phi$.")
ep("EP10", "F11", "l-th scattering layer", origin="external", origin_citation=MAL)
prose("DP25", "definition", "Scattering coefficients", "The corresponding scattering coefficients",
      "at time $t$.", conf=0.85, origin="external", origin_citation=MAL,
      definiendum="$v_{j_1,..,j_l}^{(l)}(t)$")
prose("DP26", "definition", "Sampling resolution", "In practice, we let a resolution parameter $\\Delta_t$",
      "\\lceil\\frac{2T}{\\Delta_t}\\rceil$.", conf=0.8, definiendum="$\\Delta_t$")
prose("DP27", "definition", "Final scattering layer", "We stop the process when reaching the final scattering layer $L$",
      "in layers $l=0,1,..,L$.", conf=0.8, definiendum="$L$")
prose("ClP2", "claim", "Scattering yields sparse representations", "We empirically found that in many cases the scattering transform",
      "for real-data results).", conf=0.75, rigor="numerical",
      assumptions=["in many cases"],
      conclusions=["the scattering transform can give a sparse representation of signals", "this sparsity helps in the clustering task"])
# ---- 3.4.1
prose("DP28", "definition", "Scattering group structure", "For each function $S^{(l)}_{j_1,..,j_{l}}$, we group all coefficients",
      "\\end{equation}", lo=F["F13"]["start"], conf=0.8, lo2=find("Exploiting Scattering Group Structure")[0],
      definiendum="$\\mathcal{G}$ (scattering groups)",
      statement_short="One group per scattering function $S^{(l)}_{j_1..j_l}$: all its sampled coefficients.")
ep("EP11", "F12", "Scattering group partition")
ep("EP12", "F13", "Scattering group of one path")

# ============================================================ 4 Simulation Results
prose("ClP3", "claim", "Group sparsity helps for few signals (univariate)", "Group sparsity improved accuracy substantially when the number of curves",
      "(and thus so is SNR).", conf=0.7, rigor="numerical",
      assumptions=["when the number of curves $n$ is particularly low"], conclusions=["Group sparsity improved accuracy substantially"])
prose("ClP4", "claim", "Unconstrained sparse K-means catches up for large n", "When $n$ grows, the more flexible method",
      "reach about the same accuracy.", conf=0.7, rigor="numerical",
      assumptions=["When $n$ grows"], conclusions=["the two methods reach about the same accuracy"])
prose("ClP5", "claim", "Group sparsity helps for multivariate signals", "Group sparsity improved clustering accuracy substantially,",
      "especially for low $n$.", lo=find("For multivariate signals, we select curves")[0], conf=0.7, rigor="numerical",
      assumptions=[], conclusions=["Group sparsity improved clustering accuracy substantially, especially for low $n$."])

# ============================================================ 5 Real data
prose("ClP6", "claim", "Scattering improves accuracy on all real datasets", "In all cases, using the scattering transform improved clustering accuracy.",
      "In all cases, using the scattering transform improved clustering accuracy.", conf=0.7, rigor="numerical",
      assumptions=["In all cases"], conclusions=["using the scattering transform improved clustering accuracy"])
prose("ClP7", "claim", "Scattering with sparse clustering improves Berkeley growth accuracy", "We applied the scattering transform together with sparse clustering",
      "substantial improvements in accuracy.", conf=0.7, rigor="numerical",
      assumptions=[], conclusions=["We applied the scattering transform together with sparse clustering, which lead to substantial improvements in accuracy."])
prose("ClP8", "claim", "Sparse K-means equals K-means on Berkeley scattering features", "Applying sparse K-means on the scattering features",
      "with $ARI=0.87$).", conf=0.7, rigor="numerical",
      assumptions=[], conclusions=["led to the about the same results as ordinary K-means in this feature space"])
prose("AP8", "algorithm", "SPARCWave feature selection then K-means", "The features with high-magnitude coefficients can, however,",
      "using only these features.", conf=0.75,
      statement_short="Use SPARCWave as feature selection: keep features with non-zero (or large) weights $w_j$ and rerun K-means on them.")
astep("AP8", "We can select all non-zero features", "(or above some threshold)", "filter", "Keep non-zero-weight features")
astep("AP8", "apply K-means using only these features", "using only these features", "call", "K-means on selected features")
prose("ClP9", "claim", "Feature selection raises Berkeley ARI", "This technique improved accuracy from $0.87$ to $0.91$.",
      "This technique improved accuracy from $0.87$ to $0.91$.", conf=0.75, rigor="numerical",
      assumptions=[], conclusions=["This technique improved accuracy from $0.87$ to $0.91$."])
prose("ClP10", "claim", "Group sparsity neutral on Berkeley", "Group-sparse clustering with the scattering transform lead to similar results",
      "and Figure \\ref{fig:real}).", conf=0.7, rigor="numerical",
      assumptions=[], conclusions=["Group-sparse clustering with the scattering transform lead to similar results"])
prose("ClP11", "claim", "Log-frequency scattering gives frequency-scaling invariance", "By applying the scattering transform on data in the log-frequency domain,",
      "to scaling in frequency.", conf=0.7, rigor="semi_formal",
      assumptions=["applying the scattering transform on data in the log-frequency domain"],
      conclusions=["we obtain invariance to translation in log-frequency and consequently to scaling in frequency"])
prose("ClP12", "claim", "Group sparsity neutral on Phoneme", "Here too group-sparse clustering did not change accuracy",
      "in the Appendix).", conf=0.7, rigor="numerical",
      assumptions=[], conclusions=["group-sparse clustering did not change accuracy"])
prose("ClP13", "claim", "Scattering with sparse clustering improves Wheat accuracy", "Applying the scattering transform in combination with sparse clustering",
      "improved accuracy significantly.", conf=0.7, rigor="numerical",
      assumptions=[], conclusions=["Applying the scattering transform in combination with sparse clustering improved accuracy significantly."])
prose("ClP14", "claim", "Group sparsity hurts on Wheat", "However, using group sparsity reduced accuracy,",
      "in the Appendix).", lo=POS["ClP13"][0], conf=0.7, rigor="numerical",
      assumptions=[], conclusions=["using group sparsity reduced accuracy"])
prose("ClP15", "claim", "SPARCScatter is best on all datasets", "The SPARCScatter\\: method shows superior clustering accuracy",
      "all datasets.", conf=0.65, rigor="numerical",
      assumptions=[], conclusions=["The SPARCScatter\\: method shows superior clustering accuracy over all datasets."])

# ============================================================ 6 Conclusion
prose("OpenP1", "open_problem", "Theoretical guarantees for (group) sparse clustering", "Finally, there are few known theoretical guarantees",
      "group extension we have proposed.", conf=0.7,
      statement_short="Develop theoretical guarantees for sparse K-means and its group-sparse extension.")

# ============================================================ Appendix
prose("DP29", "definition", "Adjusted Rand Index", "To evaluate the clustering performance we used the {\\it Adjusted Rand Index}",
      "\\sum_{i,j} n_{ij}$.", conf=0.9, origin="external", origin_citation="Hubert & Arabie 1985; Wagner & Wagner 2007",
      definiendum="Adjusted Rand Index ($ARI$)",
      statement_short="ARI: chance-corrected agreement between true and assigned clusters, from the contingency counts $n_{ij}$, $a_i$, $b_j$.")
ep("EP13", "F14", "Adjusted Rand Index")

# ============================================================ edges
T, I, N = "term", "inferred", "named"
# background
E("DP2", "DP3", conf=0.8, basis=T); E("DP2", "TP1", conf=0.8, basis=T); E("DP3", "TP1", conf=0.8, basis=T)
E("TP1", "DP4", conf=0.85, basis=N)  # "This decomposition has a discrete version"
E("DP4", "DP5", conf=0.85, basis=T); E("DP5", "AP4", conf=0.85, basis=T)
E("DP4", "AP1", conf=0.7, basis=I); E("AP4", "AP1", conf=0.7, basis=I)
E("TP1", "AP2", conf=0.7, basis=I); E("AP2", "RP1", conf=0.9, basis=N)
# univariate sparse K-means
E("DP4", "DP6", conf=0.85, basis=T); E("DP6", "DP7", conf=0.8, basis=T)
E("DP7", "DP9", conf=0.85, basis=T); E("DP8", "DP9", conf=0.85, basis=T); E("DP6", "DP9", conf=0.75, basis=T)
E("DP9", "ProbP1", conf=0.85, basis=T); E("DP10", "ProbP1", conf=0.85, basis=T); E("DP8", "ProbP1", conf=0.8, basis=T)
E("ProbP1", "AP5", "resolves", conf=0.9, basis=N); E("DP8", "AP5", conf=0.75, basis=T); E("DP10", "AP5", conf=0.75, basis=T)
# group sparse
E("DP10", "DP11", conf=0.7, basis=T); E("DP11", "DP13", conf=0.85, basis=T); E("DP12", "DP13", conf=0.85, basis=T)
E("DP13", "ProbP2", conf=0.9, basis=N); E("DP9", "ProbP2", conf=0.85, basis=T); E("DP10", "ProbP2", conf=0.8, basis=T)
E("DP11", "ProbP2", conf=0.8, basis=T); E("DP8", "ProbP2", conf=0.75, basis=T)
E("ProbP1", "ProbP2", "generalizes", conf=0.9, basis=N)
E("ProbP2", "AP6", "resolves", conf=0.9, basis=N)  # "can be solved iteratively as shown in Algorithm \ref"
E("DP14", "AP6", conf=0.85, basis=N); E("DP6", "AP6", conf=0.8, basis=T); E("DP11", "AP6", conf=0.8, basis=T)
E("DP10", "AP6", conf=0.8, basis=T); E("DP8", "AP6", conf=0.75, basis=T)
E("AP5", "AP6", "generalizes", conf=0.7, basis=I)
E("ProbP2", "RP2", conf=0.8, basis=I)
E("DP4", "DP15", conf=0.8, basis=T); E("DP13", "DP15", conf=0.85, basis=N); E("DP11", "DP15", conf=0.8, basis=T)
E("DP15", "RP3", conf=0.85, basis=N, mention=True)
E("DP4", "AP7", conf=0.85, basis=T); E("DP16", "AP7", conf=0.85, basis=T); E("DP13", "AP7", conf=0.85, basis=N)
E("AP7", "RP4", conf=0.85, basis=N)
# scattering
E("TP2", "DP17", conf=0.7, basis=N, mention=True); E("TP3", "DP17", conf=0.7, basis=N, mention=True)
E("DP17", "DP18", conf=0.8, basis=T); E("DP2", "DP19", conf=0.75, basis=T)
E("DP18", "DP20", conf=0.85, basis=T); E("DP19", "DP20", conf=0.85, basis=T)
E("DP19", "DP21", conf=0.8, basis=T); E("DP20", "DP21", conf=0.75, basis=I)
E("DP19", "DP22", conf=0.8, basis=I)  # generalizes the layer-1 construction
E("DP22", "DP24", conf=0.85, basis=T); E("DP23", "DP24", conf=0.75, basis=T); E("DP18", "DP24", conf=0.8, basis=T)
E("DP20", "DP24", conf=0.8, basis=N); E("DP21", "DP24", conf=0.75, basis=T)
E("DP24", "DP25", conf=0.85, basis=T); E("DP25", "DP26", conf=0.8, basis=T); E("DP24", "DP26", conf=0.8, basis=T)
E("DP26", "DP27", conf=0.7, basis=I)
E("DP17", "ClP2", conf=0.85, basis=T)
E("DP24", "DP28", conf=0.85, basis=T); E("DP25", "DP28", conf=0.85, basis=T); E("DP26", "DP28", conf=0.85, basis=T)
E("DP27", "DP28", conf=0.85, basis=T); E("DP11", "DP28", conf=0.75, basis=T)
# simulations
E("DP15", "ClP3", conf=0.75, basis=I); E("AP6", "ClP3", conf=0.75, basis=I); E("AP5", "ClP3", conf=0.7, basis=I)
E("DP29", "ClP3", conf=0.7, basis=I)
E("AP6", "ClP4", conf=0.7, basis=I); E("AP5", "ClP4", conf=0.7, basis=I)
E("AP7", "ClP5", conf=0.75, basis=I); E("DP29", "ClP5", conf=0.7, basis=I)
# real data
E("DP17", "ClP6", conf=0.85, basis=T); E("DP29", "ClP6", conf=0.7, basis=I)
E("DP17", "ClP7", conf=0.85, basis=T); E("AP5", "ClP7", conf=0.75, basis=I)
E("DP17", "ClP8", conf=0.85, basis=T); E("AP5", "ClP8", conf=0.8, basis=N); E("DP29", "ClP8", conf=0.8, basis=T)
E("DP1", "AP8", conf=0.85, basis=T); E("DP10", "AP8", conf=0.8, basis=T); E("ProbP1", "AP8", conf=0.75, basis=I)
E("AP8", "ClP9", conf=0.9, basis=N)
E("DP28", "ClP10", conf=0.8, basis=I); E("DP17", "ClP10", conf=0.85, basis=T); E("AP6", "ClP10", conf=0.75, basis=I)
E("DP17", "ClP11", conf=0.85, basis=T)
E("DP28", "ClP12", conf=0.75, basis=I)
E("DP17", "ClP13", conf=0.85, basis=T); E("AP5", "ClP13", conf=0.7, basis=I)
E("DP28", "ClP14", conf=0.75, basis=I); E("DP10", "ClP14", conf=0.7, basis=T)
E("DP17", "ClP15", conf=0.75, basis=I); E("AP5", "ClP15", conf=0.65, basis=I); E("DP29", "ClP15", conf=0.7, basis=I)
E("AP5", "OpenP1", conf=0.8, basis=N); E("AP6", "OpenP1", conf=0.8, basis=N)

NOTES = [
    {"category": "type_uncertain", "nodes": ["TP1"],
     "note": "theorem or definition: the sentence states the standard L^2 wavelet expansion and in its 'where' clause names the scaling and wavelet coefficients; kept as one external theorem, since splitting the sentence is not allowed."},
    {"category": "type_uncertain", "nodes": ["TP2", "TP3"],
     "note": "theorem or remark: two qualitative cited facts (wavelets not translation invariant; fine coefficients unstable under deformations, Mallat 2012) stated as motivation for the scattering transform."},
    {"category": "unexpected_construct", "nodes": ["AP4"],
     "note": "The 'three-step procedure' of wavelet shrinkage is written as one formula W^{-1} eta(W x), so no algorithm_step could be cut from it without splitting the display; AP4 has zero steps."},
    {"category": "unexpected_construct", "nodes": ["ClP15", "ClP6"],
     "note": "Table 1 (real-data ARI for seven methods) and Table 2 (scattering parameters) carry most of the empirical content; they are represented only by the claims that read them, including the Table 1 caption claim ClP15."},
    {"category": "boundary_uncertain", "nodes": ["DP17", "DP18", "DP19", "DP20", "DP21", "DP22", "DP23", "DP24", "DP25", "DP26", "DP27"],
     "note": "The scattering transform is built sentence by sentence (filters, layers, scale path, sampling, final layer); each symbol-introducing sentence is its own definition rather than one algorithm node."},
    {"category": "not_extracted", "nodes": [],
     "note": "Not extracted: the simulation set-up (test curves, packages, baselines), dataset descriptions, figure captions, the Wasserman GMM mention, and the future-work directions other than the theoretical-guarantees question."},
]
COMMENT = ("The SPARCScatter method reported in Table 1 is never defined in the text; it is presumably sparse K-means (ProbP1/AP5) "
           "on scattering coefficients, possibly followed by the feature-selection re-clustering AP8 (the 0.91 Growth figure matches ClP9).")
meta = {
    "title": "Clustering Noisy Signals with Structured Sparsity Using Time-Frequency Representation",
    "arxiv_id": "1510.05214",
    "authors": ["Tom Hope", "Avishai Wagner", "Or Zuk"],
    "year": 2015,
    "annotator": "agent-extraction",
    "model": "claude-opus-5-5",
    "effort": "default",
    "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
    "extraction_date": "2026-11-05",
    "rigor_nonformal_count": sum(1 for n in nodes if "rigor" in n),
    "paper_style": ["modeling", "computational"],
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
