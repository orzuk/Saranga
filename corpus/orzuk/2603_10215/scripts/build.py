#!/usr/bin/env python3
"""Build the v7 SARANGA graph of arXiv 2603.10215 (SDSR, Reshef et al.).

Run: python3 build.py   (reads facts.json from the scratch dir, writes ../2603_10215.json)
Regenerate facts.json first with
  python3 /mnt/c/Code/Github/Saranga/src/latex_facts.py ../arxiv_src/Species_tree_paper.tex --out <SCRATCH>/facts.json
"""
import json
import os
import re
import sys

sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
from extraction_finalize import finalize, pseudocode_steps  # noqa: E402
from latex_facts import read_tex  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
TEX = os.path.join(PAPER, "arxiv_src", "Species_tree_paper.tex")
SCRATCH = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_orzuk/2603_10215"
OUT = os.path.join(PAPER, "2603_10215.json")

facts = json.load(open(os.path.join(SCRATCH, "facts.json")))
SRC = facts["source"]
F = {f["id"]: f for f in facts["facts"]}
SEC = {s["id"]: s for s in facts["sections"]}
STD = "standard (uncited)"


def clean(t):
    t = re.sub(r"\\label\{[^}]*\}", " ", t)
    return " ".join(t.split())


def _find(marker, pos):
    m = re.compile(r"\s*".join(map(re.escape, marker.split()))).search(SRC, pos)
    return (m.start(), m.end()) if m else (-1, -1)


def cut(start, end, pos=0):
    """Verbatim span from the first `start` at/after offset pos-60 through the first `end` after it."""
    i, _ = _find(start, max(0, pos - 200))
    assert i >= 0, start
    j, je = _find(end, i + 1)
    if start.strip() == end.strip():
        j, je = _find(end, i)
    assert j >= 0, (start, end)
    return clean(SRC[i:je])


def fact(fid):
    f = F[fid]
    return clean(SRC[f["start"]:f["end"]])


def secname(sid):
    s = SEC[sid]
    return (s["number"] + " " if s["number"] else "") + s["title"]


PREFIX = {"definition": "DP", "theorem": "TP", "lemma": "LP", "proposition": "PrP",
          "corollary": "CP", "proof": "PP", "proof_step": "PSP", "algorithm": "AP",
          "algorithm_step": "ASP", "equation": "EP", "example": "ExP", "remark": "RP",
          "problem": "ProbP", "open_problem": "OpenP", "assumption": "AssumP",
          "claim": "ClP", "conjecture": "CnjP"}
COUNT = {}
nodes, edges = [], []
BYID = {}
ORDER = {}


def nid(type):
    COUNT[type] = COUNT.get(type, 0) + 1
    return f"{PREFIX[type]}{COUNT[type]}"


def node(type, name, statement, sec, origin="paper", conf=1.0, **kw):
    n = {"id": nid(type), "type": type, "name": name, "statement": statement,
         "section": secname(sec), "origin": origin, "confidence": conf}
    n.update({k: v for k, v in kw.items() if v is not None})
    nodes.append(n)
    BYID[n["id"]] = n
    return n["id"]


def env(type, name, fid, origin="paper", conf=1.0, **kw):
    return node(type, name, fact(fid), F[fid]["section"], origin, conf, **kw)


EQID = {}
for _f in facts["facts"]:
    if _f["kind"] == "equation" and _f["id"] != "F50":
        EQID[_f["id"]] = f"EP{len(EQID) + 1}"


def eq(fid, name, conf=1.0, **kw):
    n = {"id": EQID[fid], "type": "equation", "name": name, "statement": fact(fid),
         "section": secname(F[fid]["section"]), "origin": "paper", "confidence": conf}
    n.update(kw)
    nodes.append(n)
    BYID[n["id"]] = n
    return n["id"]


def step(parent, start, end, pos, subclass, short, name, conf=0.75, type="proof_step"):
    p = BYID[parent]
    ORDER[parent] = ORDER.get(parent, 0) + 1
    n = {"id": nid(type), "type": type, "parent_id": parent, "step_order": ORDER[parent],
         "name": name, "statement": cut(start, end, pos), "statement_short": short,
         "subclass": subclass, "section": p["section"], "origin": p["origin"],
         "confidence": conf}
    nodes.append(n)
    BYID[n["id"]] = n
    return n["id"]


def astep(parent, start, end, pos, subclass, short, name, conf=0.7):
    return step(parent, start, end, pos, subclass, short, name, conf, type="algorithm_step")


def E(s, t, type="uses", conf=0.8, basis="inferred", **kw):
    e = {"source": s, "target": t, "type": type, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)


def T(s, t, conf=0.8):
    E(s, t, conf=conf, basis="term")


# ================================================================ 1 Introduction
CAML = node("algorithm", "Concatenation Analysis using Maximum Likelihood (CA-ML)",
            cut("Perhaps one of the simplest ones is", "recovered by maximum likelihood.", 5991), "S1",
            origin="external", origin_citation="standard (uncited); RAxML, Stamatakis 2014", conf=0.75,
            statement_short="Concatenate all gene alignments and fit a single maximum-likelihood tree.",
            input=["the gene sequences of each species"], output=["the species tree"])
astep(CAML, "the gene sequences of each species are concatenated", "are concatenated", 6129,
      "compute", "Concatenate the gene alignments per species.", "Concatenate genes")
astep(CAML, "the species tree is recovered by maximum likelihood", "by maximum likelihood", 6200,
      "solve", "Fit one ML tree to the concatenated alignment.", "Maximum-likelihood tree")
INCONS = node("theorem", "Statistical inconsistency of CA-ML under the MSC",
              cut("Indeed, \\texttt{CA-ML} has been shown to be statistically inconsistent", "roch2015likelihood}.", 6405),
              "S1", origin="external", origin_citation="Kubatko & Degnan 2007; Roch & Steel 2015", conf=0.7,
              assumptions=[], conclusions=["\\texttt{CA-ML} has been shown to be statistically inconsistent under the multispecies coalescent (MSC) model"])
T(CAML, INCONS, 0.85)
SUMM = node("definition", "Summary methods",
            cut("A different approach to species tree reconstruction is to first estimate", "{\\em summary methods}.", 6576),
            "S1", origin="external", origin_citation=STD, conf=0.8, definiendum="summary methods",
            statement_short="Methods that first estimate each gene tree and then summarize them into a species tree.")
SUMMC = node("theorem", "Consistency of summary methods under the MSC",
             cut("These summary methods were proven to be consistent under the", "mirarab2014astral}.", 7095),
             "S1", origin="external",
             origin_citation="Allman et al. 2016; Liu et al. 2009; Vachaspati & Warnow 2015; Mirarab et al. 2014", conf=0.7,
             assumptions=["assuming the input gene trees are estimated correctly"],
             conclusions=["These summary methods were proven to be consistent under the MSC model"])
T(SUMM, SUMMC, 0.85)
UDANCE = node("algorithm", "uDance",
              cut("\\texttt{uDance} \\cite{balaban2024generation} offers an alternative", "assigned to the same edge.", 8518),
              "S1", origin="external", origin_citation="Balaban et al. 2024", conf=0.75,
              statement_short="Divide-and-conquer: backbone tree, place remaining species on its edges, rebuild a subtree per edge group.")
astep(UDANCE, "It recovers a backbone tree from a subset of species", "subset of species", 8614,
      "solve", "Reconstruct a backbone tree on a species subset.", "Backbone tree")
astep(UDANCE, "assigns each of the remaining species to an edge in the backbone tree", "in the backbone tree", 8650,
      "select", "Place each remaining species on a backbone edge.", "Assign species to edges")
astep(UDANCE, "Then, the algorithm reconstructs a subtree for every group", "assigned to the same edge.", 8750,
      "solve", "Reconstruct one subtree per edge group.", "Per-edge subtrees")

# ================================================================ 2 Problem Setting
TREE = node("definition", "Unrooted binary species tree",
            cut("Let $\\mathcal T = (V, E)$ denote an unrooted binary species tree", "to ancestor species.", 12158),
            "S2", origin="external", origin_citation=STD, conf=0.8, definiendum="$\\mathcal T$",
            genus="unrooted binary species tree", differentia=["$m$ terminal and $m-2$ non-terminal nodes"])
IDX = node("definition", "Index sets of terminal and non-terminal nodes",
           cut("We denote the indices of the terminal nodes by", "\\{m+1,\\ldots,2m-2\\}$.", 12370), "S2",
           conf=0.8, definiendum="$[m]$")
T(TREE, IDX)
ALPH = node("definition", "Alphabet of sequence symbols",
            cut("The observed data for each current species at a specific gene", "nucleotide bases.", 12502), "S2",
            conf=0.75, definiendum="$\\{\\alpha_1,\\ldots,\\alpha_\\ell\\}$")
KX = node("definition", "Gene alignments $\\{X^g\\}_{g=1}^K$",
          cut("In the problem at hand, we are given a set of $K$ gene alignments", "denoted $\\{X^g\\}_{g=1}^K$.", 12740),
          "S2", conf=0.8, definiendum=["$K$", "$\\{X^g\\}_{g=1}^K$"])
GALN = node("definition", "Gene alignment matrix",
            cut("A single gene alignment $X^g", "corresponds to a single species.", 12900), "S2", conf=0.8,
            definiendum="gene alignment", genus="$m$ sequences of length $n_g$")
T(ALPH, GALN)
T(KX, GALN)
XIG = node("definition", "Species sequence $X_i^g$",
           cut("We denote by $X_i^g", "in the $g$-th gene.", 13011), "S2", conf=0.8, definiendum="$X_i^g$")
T(GALN, XIG)
PROB = node("problem", "Species tree reconstruction from multiple gene alignments",
            cut("The goal is to reconstruct the species tree", "gene alignments.", 13130), "S2", conf=0.75)
T(KX, PROB)
T(TREE, PROB)
DHAT = node("definition", "Estimated evolutionary distance $\\hat D^g$",
            cut("For each gene $g$ with gene alignment matrix", "observed species $(i,j)$.", 13618), "S2", conf=0.8,
            definiendum="$\\hat D^g(i,j)$")
T(GALN, DHAT)
SHAT = node("definition", "Gene similarity matrix estimate $\\hat S^g$",
            cut("Next, we compute the gene $m\\times m$ similarity matrix", "\\end{equation}", 14066), "S2", conf=0.85,
            definiendum="$\\hat S^g$")
EP_sim = eq("F1", "Similarity from distance")
T(DHAT, SHAT)
AG = node("definition", "Degree matrix $A^g$",
          cut("Let $A^{g}$ denote the diagonal matrix", "\\hat S^g(i,j)$.", 14476), "S2", conf=0.8,
          definiendum="$A^{g}$")
T(SHAT, AG)
LNORM = node("definition", "Normalized graph Laplacian $L^g$",
             cut("The normalized Laplacian $L^{g}$ of the similarity graph", "\\end{equation}", 14571), "S2",
             conf=0.85, definiendum="normalized Laplacian $L^{g}$")
EP_lap = eq("F2", "Normalized Laplacian")
T(AG, LNORM)
T(SHAT, LNORM)
LAPPSD = node("claim", "Laplacian of a connected graph is PSD with simple zero eigenvalue",
              cut("For any connected graph, the Laplacian matrix is positive semi-definite", "multiplicity one.", 14750),
              "S2", origin="external", origin_citation=STD, conf=0.7,
              assumptions=["For any connected graph"],
              conclusions=["the Laplacian matrix is positive semi-definite with a zero eigenvalue with multiplicity one"])
FIED = node("definition", "Fiedler vector",
            cut("The Fiedler vector is the eigenvector of $L$", "smallest non-zero eigenvalue.", 14850), "S2",
            origin="external", origin_citation=STD, conf=0.85, definiendum="Fiedler vector",
            genus="eigenvector of $L$", differentia=["corresponds to its smallest non-zero eigenvalue"])
E(LAPPSD, FIED, conf=0.7)
T(LNORM, FIED, 0.75)
CLAN = node("definition", "Clan",
            cut("A subset of nodes $C$ in a tree $\\mathcal T$ is a {\\em clan}", "a single edge $e$.", 15088), "S2",
            origin="external", origin_citation=STD, conf=0.9, definiendum="clan",
            genus="subset of nodes $C$ in a tree $\\mathcal T$",
            differentia=["it can be separated from the rest of the tree by removing a single edge $e$"])
CLANROOT = node("definition", "Root $h_C$ of a clan",
                cut("The node $h_C \\in C$ that is at one end of the edge $e$", "includes $C$.", 15231), "S2",
                origin="external", origin_citation=STD, conf=0.85, definiendum="$h_C$")
T(CLAN, CLANROOT)
EX_CLAN = node("example", "Clans (E,F) and (E,F,G) of the Figure 1 tree",
               cut("For example, for the species tree in Figure", "form clans in $\\mathcal T$.", 15400), "S2",
               conf=0.75)
E(CLAN, EX_CLAN, "illustrates", 0.9, "named")

# ================================================================ 3 The SDSR algorithm
SDSR = env("algorithm", "SDSR (Spectral Divide-and-conquer Species tree Reconstruction)", "F3", main=True,
           input=["Gene alignments $\\{X^{g}\\}_{g=1}^K$ for a set of species $C$", "threshold $\\tau$",
                  "tree reconstruction subroutine", "minimum partition ratio $\\beta$"],
           output=["Reconstructed species tree."],
           statement_short="Recursively split species by constrained k-means on the Fiedler vector of the averaged gene Laplacian, "
                           "rebuild small subsets with a base method, and merge the subtrees via outgroups.",
           also_stated_at=[cut("The input to \\texttt{SDSR} consists of", "computed in (iii).", 15698)])
steps = pseudocode_steps(facts, "F3", BYID[SDSR], first_seq=COUNT["algorithm_step"] + 1)
SUB = ["compute", "solve", "select", "loop", "branch", "call", "branch", "call", None, None,
       "select", "filter", "compute", "return"]
SHORT = ["Compute per-gene distances, similarities and Laplacians, and their average $\\bar L$.",
         "Split species by size-constrained k-means on the Fiedler vector of $\\bar L$.",
         "Pick one outgroup from each side and add it to the other side.",
         None, None, "Recurse on the subset.", None, "Reconstruct the small subtree with the base method.",
         None, None, "Find the nodes adjacent to the outgroups (subtree roots).", "Delete the outgroups.",
         "Join the two subtrees by an edge between $h_1$ and $h_2$.", None]
NAMES = ["Averaged Laplacian", "Spectral partition", "Outgroups", "Loop over subsets", "Size test",
         "Recursive call", "Else", "Base reconstruction", None, None, "Subtree roots", "Remove outgroups",
         "Merge", "Return"]
kept = []
for k, s in enumerate(steps):
    if SUB[k] is None and k in (8, 9):
        continue
    s["subclass"] = SUB[k] or s["subclass"]
    if SHORT[k]:
        s["statement_short"] = SHORT[k]
    s["name"] = NAMES[k]
    kept.append(s)
for s in kept:
    if not s["statement"].strip():
        s["statement"] = "\\Return merged tree $\\hat{\\mathcal T}$."
    s["statement"] = clean(s["statement"])
order = {}
for s in kept:
    order[s["parent_id"]] = order.get(s["parent_id"], 0) + 1
    s["step_order"] = order[s["parent_id"]]
    nodes.append(s)
    BYID[s["id"]] = s
COUNT["algorithm_step"] += len(steps)

LBAR = node("definition", "Averaged Laplacian $\\bar L$",
            cut("We compute a gene-Laplacian matrix $L^{g}$ via", "\\end{equation}", 18333), "S3", conf=0.85,
            definiendum="averaged Laplacian $\\bar L$")
EP_avg = eq("F5", "Average of gene Laplacians")
T(LNORM, LBAR)
BETA = node("definition", "Minimum partition ratio $\\beta$",
            cut("Specifically, for an input set of species $C$ we add a constraint", "$0<\\beta<0.5$.", 18673),
            "S3", conf=0.8, definiendum="$\\beta$")
OGROOT = node("definition", "Outgroup rooting",
              cut("As described below in step 4, the merging step relies on", "reference point for the root's location.", 19085),
              "S3", origin="external", origin_citation="Grant 2019; Boykin et al. 2010", conf=0.8,
              definiendum="outgroup rooting",
              statement_short="Root an unrooted tree by adding a related species outside the group; the root sits next to it.")
OUTSEL = node("algorithm", "SDSR outgroup selection",
              cut("Here, we select the outgroup according to the following simple procedure.",
                  "is selected in a similar way.", 20000), "S3", conf=0.75,
              statement_short="Choose as outgroup the species of the other side whose Fiedler entry is closest to that side's mean.",
              input=["the Fiedler vector of $\\bar L$"], output=["The outgroup $O_1 \\in C_1$"])
astep(OUTSEL, "Let $v\\in \\mathds R^m$ denote the Fiedler vector of", "between species $i$ and $j$.", 20101,
      "initialize", "Use Fiedler-vector differences as species distances.", "Fiedler distances")
astep(OUTSEL, "We choose $O_2 \\in C_2$ by looking for the species", "from $C_2$ to $C_1$.", 20316,
      "select", "Criterion: average distance to $C_1$ closest to the mean cross distance.", "Selection criterion")
astep(OUTSEL, "Namely, for each node $j \\in C_2$ define", "\\sum_{j \\in C_2} d_j$.", 20487,
      "compute", "Compute $d_j$ and $D(C_1,C_2)$.", "Average distances")
astep(OUTSEL, "Let $\\bar v^{(2)} =", "|v_{j'}-\\bar v^{(2)}|. \\]", 20692,
      "select", "Equivalently pick $j$ minimizing $|v_j-\\bar v^{(2)}|$.", "Closest to mean")
astep(OUTSEL, "The outgroup $O_1 \\in C_1$ is selected in a similar way.", "is selected in a similar way.", 20938,
      "select", "Symmetric choice of $O_1$.", "Other outgroup")
E(FIED, OUTSEL, conf=0.85, basis="term")
E(OUTSEL, SDSR, conf=0.8, basis="inferred")
E(OGROOT, SDSR, conf=0.8, basis="inferred")
E(OGROOT, OUTSEL, conf=0.75, basis="inferred")
T(FIED, SDSR, 0.85)
T(BETA, SDSR, 0.8)
T(LBAR, SDSR, 0.8)
MERGE = node("claim", "Correctness of the outgroup merging step",
             cut("If the  partitioning and recovery steps were accurate, then both subtrees", "their respective root nodes.", 21411),
             "S3", conf=0.7, rigor="semi_formal",
             assumptions=["If the partitioning and recovery steps were accurate"],
             conclusions=["both subtrees, excluding their outgroups, form clans in the full tree $\\mathcal T$"])
E(SDSR, MERGE, conf=0.75)
T(CLAN, MERGE)
RP_STDR = env("remark", "Differences between SDSR and STDR", "F6",
              statement_short="SDSR differs from STDR by using many genes, constrained k-means partitions, and outgroup-based merging.")
E(SDSR, RP_STDR, conf=0.8, basis="named", mention=True)

# ================================================================ 4 Complexity
SIMCOST = node("claim", "Cost of computing the similarity matrices",
               cut("Regarding the first part, computing $K$ similarity matrices", "operations.", 24176), "S4", conf=0.7)
T(KX, SIMCOST)
PP_ITER = node("proof", "Argument for the per-iteration cost",
               cut("Partitioning the $m$ species requires computing the Fiedler vector", "linear in the number of terminal nodes.", 24389),
               "S4", conf=0.7, statement_short="Fiedler vector costs $O(m^2)$; outgroup merging is linear in $m$.")
step(PP_ITER, "Partitioning the $m$ species requires computing the Fiedler vector", "\\cite[Chapter 2]{stewart2001}.", 24389,
     "apply_lemma", "Fiedler vector computation is $O(m^2)$.", "Fiedler cost")
step(PP_ITER, "Applying the outgroup approach in the merging step", "linear in the number of terminal nodes.", 24578,
     "bound_estimate", "Merging operations are linear in $m$.", "Merge cost")
ITER = node("claim", "Per-iteration partition and merge cost $O(m^2)$",
            cut("Thus, the complexity of the partition and merging step", "is $\\mathcal{O}(m^2)$.", 24900), "S4", conf=0.75)
E(PP_ITER, ITER, "proves", 0.75, "inferred")
T(FIED, PP_ITER, 0.75)
TM = node("definition", "Partition-and-merge complexity $T(m)$",
          cut("Let $T(m)$ denote the complexity", "merging operations.", 25011), "S4", conf=0.8, definiendum="$T(m)$")
PP_REC = node("proof", "Balanced-partition justification of the recurrence",
              cut("Given an input of $m$ species, the partition satisfies", "$0<\\beta \\leq 0.5$.", 25088), "S4",
              conf=0.7, statement_short="Both sides have at least $\\beta m$ species by the k-means constraint.")
REC = node("claim", "Recurrence for $T(m)$",
           cut("Thus, the complexity of recursively reconstructing a tree", "for some constant $C$.", 25216), "S4",
           conf=0.75, assumptions=["Given an input of $m$ species, the partition satisfies $\\min(|C_1|,|C_2|) \\geq \\beta m$, for some constant $0<\\beta \\leq 0.5$."],
           conclusions=["T(m) \\leq \\max_{\\beta \\leq \\beta' \\leq 0.5}T(\\beta' m) + T( (1-\\beta')m) + C m^2,"])
EP_rec = eq("F7", "Complexity recurrence")
E(PP_REC, REC, "proves", 0.7, "inferred")
T(BETA, PP_REC)
T(TM, REC)
E(ITER, REC, conf=0.8)
TMB = node("claim", "Partition-and-merge complexity $T(m)=O(m^2)$",
           cut("By Lemma \\ref{lem:complexity_k2logk}", "depends on $\\beta$.", 25495), "S4", conf=0.8,
           conclusions=["the complexity $T(m)$ may be bounded by \\[ T(m) = \\mathcal{O}\\Big(m^2 \\Big), \\]"])
E(REC, TMB, conf=0.85)
T(TM, TMB)
PP_SMALL = node("proof", "Counting the small subtrees",
                cut("Given a threshold $\\tau$ for the partitioning step", "tree reconstruction subroutine.", 25830),
                "S4", conf=0.7, statement_short="Subsets have at least $\\tau\\beta$ species, so at most $m/(\\tau\\beta)$ subroutine calls.")
step(PP_SMALL, "Given a threshold $\\tau$ for the partitioning step", "bounded by $m/(\\tau \\beta)$.", 25830,
     "bound_estimate", "Smallest subset $\\tau\\beta$, so at most $m/(\\tau\\beta)$ subsets.", "Number of subsets")
step(PP_SMALL, "For each of these subsets we apply", "tree reconstruction subroutine.", 26000,
     "conclude", "One subroutine call per subset.", "One call per subset")
T(BETA, PP_SMALL)
FTAU = node("definition", "Subroutine complexity $f(\\tau)$",
            cut("Let $f(\\tau)$ denote the complexity", "user-chosen subroutine.", 26100), "S4", conf=0.8,
            definiendum="$f(\\tau)$")
SMALL = node("claim", "Cost of reconstructing all small trees",
             cut("The complexity of reconstructing all the small trees is thus", "f(\\tau)/\\tau)$.", 26206), "S4",
             conf=0.75)
E(PP_SMALL, SMALL, "proves", 0.7, "inferred")
T(FTAU, SMALL)
TOTAL = node("claim", "Overall complexity of SDSR",
             cut("Combining the complexity of all \\texttt{SDSR} steps yields", "\\end{equation}", 26298), "S4",
             conf=0.8, statement_short="Total cost: similarity computation + $O(m^2)$ partitioning/merging + $O(m f(\\tau)/\\tau)$ subroutine calls.")
EP_tot = eq("F8", "Total complexity of SDSR")
for s in (SIMCOST, TMB, SMALL):
    E(s, TOTAL, conf=0.8)
T(FTAU, TOTAL)
T(SDSR, TOTAL, 0.75)
EX_SQRT = node("example", "Quadratic subroutine with $\\tau=\\sqrt m$",
               cut("Taking these points into account, let us illustrate", "applying the algorithm to the full data.", 26844),
               "S4", conf=0.75,
               statement_short="For an $O(m^2)$ base method and $\\tau=\\sqrt m$, the subroutine term is $O(m^{3/2})$, a $\\sqrt m$ saving.")
E(TOTAL, EX_SQRT, "illustrates", 0.85, "inferred")
T(FTAU, EX_SQRT)
RP_CAML = node("remark", "Complexity of SDSR+CA-ML versus CA-ML",
               cut("We compare the complexity of \\texttt{CA-ML} to the complexity", "to $\\mathcal{O}(K\\tau m  n)$.", 27466),
               "S4", conf=0.7, rigor="semi_formal",
               statement_short="Each SPR move costs $O(Km^2n)$ on the full data but $O(K\\tau mn)$ in total over SDSR subsets, a factor $m/\\tau$ saving.")
T(CAML, RP_CAML, 0.85)
E(SIMCOST, RP_CAML, conf=0.75)
E(SMALL, RP_CAML, conf=0.7)

# ================================================================ 5 Theoretical guarantees
VARIANT = node("algorithm", "Sign-pattern spectral partitioning with unnormalized Laplacians (analyzed variant)",
               cut("The guarantees are derived for a partitioning scheme that slightly differs from",
                   "constrained $k$-means algorithm.", 29101), "S5", conf=0.75,
               statement_short="Average the exact similarity matrices, form the unnormalized Laplacian $A-S$, split by the sign of its Fiedler vector.")
astep(VARIANT, "(i) it uses the unnormalized Laplacian matrices", "compute its corresponding Laplacian.", 29218,
      "compute", "Average similarities, then take the unnormalized Laplacian $L=A-S$.", "Unnormalized Laplacian")
astep(VARIANT, "(ii) The partitioning is determined by the sign pattern", "constrained $k$-means algorithm.", 29554,
      "select", "Split by the signs of the Fiedler vector entries.", "Sign-pattern split")
T(AG, VARIANT)
T(FIED, VARIANT)
E(SDSR, VARIANT, conf=0.8, basis="named")
EXACT = node("assumption", "Exact gene Laplacians (no estimation error)",
             cut("Our analysis assumes that the un-normalized Laplacian matrices of individual genes are perfectly known.",
                 "are perfectly known.", 29682), "S5", conf=0.9,
             also_stated_at=[cut("Our analysis assumes that the Laplacian matrices of individual genes", "are perfectly known.", 10300)])
MSC_SENT = cut("Our analysis assumes the MSC model for generating random gene trees", "given a gene tree.", 29949)

# ---------------------------------------------------------------- 5.1
A_MSC = node("assumption", "Gene trees follow the MSC model",
             cut("Given a species tree, we assume that the random", "Multispecies Coalescent (MSC) model.", 31704), "S6",
             conf=0.9, also_stated_at=[MSC_SENT])
A_GTR = node("assumption", "Sequences follow the GTR model on each gene tree",
             cut("Next, for each gene tree, we assume its corresponding sequences", "similar to \\cite{allman2019species}.", 31823),
             "S6", conf=0.9,
             also_stated_at=[MSC_SENT, cut("As in \\cite{allman2019species}, we assume the GTR model", "for the substitution matrices.", 36451)])
SPTREE = env("definition", "Species tree (rooted, timed)", "F9", origin="external",
             origin_citation="Yang 2014; Allman, Long & Rhodes 2019", definiendum="species tree",
             genus="binary rooted tree",
             differentia=["each node $h$ has an associated time $\\tau_h\\geq 0$",
                          "each edge $e$ has a coalescence rate $\\lambda(e) > 0$"],
             statement_short="Rooted binary tree with node times (zero at leaves, increasing toward the root) and edge coalescence rates.")
MRCA = node("definition", "Most recent common ancestor $h_{ij}$",
            cut("Let $h_{ij}$ be the internal node of $\\mathcal T$", "most recent common ancestor (MRCA).", 33246), "S6",
            origin="external", origin_citation=STD, conf=0.85, definiendum=["$h_{ij}$", "MRCA"])
T(SPTREE, MRCA)
DIVT = node("definition", "Divergence time $\\tau_{ij}$",
            cut("The divergence time $\\tau_{ij}$ of species $i,j$", "$\\tau_{ij} = \\tau_{h_{ij}}$.", 33418), "S6",
            origin="external", origin_citation=STD, conf=0.85, definiendum="$\\tau_{ij}$")
T(MRCA, DIVT)
T(SPTREE, DIVT)
MSC = node("definition", "Multispecies Coalescent (MSC) model",
           cut("Under the MSC, a gene tree $\\mathcal T^g$ is randomly generated", "coalescence rates $\\lambda (e)$ on its edges.", 33656),
           "S6", origin="external", origin_citation="Yang 2014; Allman, Long & Rhodes 2019", conf=0.85,
           definiendum="Multispecies Coalescent (MSC) model",
           statement_short="Gene trees grow bottom-up from the present species, lineages coalescing at the species tree's edge rates.")
T(SPTREE, MSC)
TAUG = node("definition", "Gene-tree coalescence time $\\tau^g_{ij}$",
            cut("For any two species $i,j$, we denote by $\\tau^g_{ij}$", "in the gene tree $\\mathcal T^g$.", 34073), "S6",
            origin="external", origin_citation=STD, conf=0.85, definiendum="$\\tau^g_{ij}$")
COAL = node("definition", "MSC coalescence conditions and excess time $\\Delta^g_{ij}$",
            cut("The coalescence process satisfies the following two conditions:", "\\end{enumerate}", 34184), "S6",
            origin="external", origin_citation="Yang 2014; Allman, Long & Rhodes 2019", conf=0.85,
            definiendum="$\\Delta^g_{ij}$",
            statement_short="$\\tau^g_{ij}>\\tau_{ij}$ and the excess $\\Delta^g_{ij}$ is exponential with piecewise-constant rates on the path from the MRCA to the root.")
for s in (TAUG, DIVT, MRCA, MSC):
    T(s, COAL)
T(MSC, A_MSC, 0.85)
SEQM = node("definition", "Markov model of sequence evolution on a tree",
            cut("We assume that the observed sequences are generated according to the", "substitution matrices on its edges.", 35261),
            "S6", origin="external", origin_citation="Yang 2014", conf=0.8,
            definiendum="Markov model of sequence evolution")
XH = node("definition", "Node state variable $X_h$",
          cut("In addition, at each node $h$ in the tree, there is an associated random variable", "\\ldots,\\alpha_d\\}$.", 35582),
          "S6", origin="external", origin_citation="Yang 2014", conf=0.8, definiendum="$X_h$")
T(SEQM, XH)
PMAT = node("definition", "Substitution probability matrix $P_{h|h'}$",
            cut("The sequence generative process begins at the root", "independently for each location in the sequence.", 35704),
            "S6", origin="external", origin_citation="Yang 2014", conf=0.8,
            definiendum="substitution probability matrix $P_{h|h'}$",
            statement_short="States are drawn at the root, then propagated to children through the edge substitution matrices, site by site.")
EP_P = eq("F10", "Substitution matrix entries")
T(XH, PMAT)
T(SEQM, PMAT)
GTR = node("definition", "General Time Reversal (GTR) model",
           cut("Under this model, the sequences mutate along the edges of the tree", "distributed according to $\\pi$.", 36539),
           "S6", origin="external", origin_citation="Allman, Long & Rhodes 2019", conf=0.85,
           definiendum="General Time Reversal (GTR) model", genus="continuous-time Markov process",
           differentia=["$Q_{ij}\\geq0$ for all $i\\neq j$", "each row of $Q$ sums to zero",
                        "there is a distribution vector $\\pi\\in\\mathbb{R}^d$ with positive probabilities that satisfies $\\pi Q=0$",
                        "$\\text{diag}(\\pi)Q$ is symmetric"],
           statement_short="Reversible continuous-time Markov substitution process with rate matrix $Q$ and stationary root distribution $\\pi$.")
T(SEQM, GTR)
T(GTR, A_GTR, 0.85)
NEGSD = node("claim", "GTR rate matrix is negative semi-definite",
             cut("By the first two properties above, $Q$ is negative semi-definite", "non-positive.", 37104), "S6",
             origin="external", origin_citation=STD, conf=0.75,
             conclusions=["$Q$ is negative semi-definite, namely, all its eigenvalues are non-positive"])
NEGEIG = node("claim", "Nonzero GTR rate matrix has a negative eigenvalue",
              cut("If $Q\\neq \\textbf{0}_{d\\times d}$, then there is at least one eigenvalue", "strictly smaller than zero.", 37216),
              "S6", origin="external", origin_citation=STD, conf=0.7,
              assumptions=["$Q\\neq \\textbf{0}_{d\\times d}$"],
              conclusions=["there is at least one eigenvalue which is strictly smaller than zero"])
T(GTR, NEGSD)
T(GTR, NEGEIG)
E(NEGSD, NEGEIG, conf=0.7)
PEXP = node("claim", "GTR edge transition matrices are matrix exponentials",
            cut("Let $h,h'$ be two adjacent nodes in the gene tree with times", "\\end{equation}", 37405), "S6",
            origin="external", origin_citation=STD, conf=0.75,
            assumptions=["$h,h'$ be two adjacent nodes in the gene tree with times $\\tau^g_h,\\tau^g_{h'}$",
                         "Under the GTR model with rate matrix $Q$"],
            conclusions=["P_{h|h'}=P_{h'|h}=e^{Q|\\tau_h-\\tau_{h'}|}."])
EP_Pexp = eq("F11", "GTR transition matrix")
T(GTR, PEXP)
T(PMAT, PEXP)
DETP = node("claim", "Determinant of a GTR transition matrix",
            cut("Using the standard identity for the matrix exponential,", "\\end{equation}", 37661), "S6",
            origin="external", origin_citation=STD, conf=0.75,
            conclusions=["\\det(P_{h'|h})=e^{\\text{tr}(Q)|\\tau_h-\\tau_{h'}|}."])
EP_det = eq("F12", "Determinant of transition matrix")
E(PEXP, DETP, conf=0.8)
DET01 = node("claim", "GTR transition determinants lie in (0,1)",
             cut("Note that $\\text{tr}(Q)<0$, hence Eq.", "$0<\\det(P_{h'|h})<1$.", 37828), "S6", conf=0.75,
             conclusions=["$0<\\det(P_{h'|h})<1$"])
E(NEGEIG, DET01, conf=0.6)
CHANG = node("theorem", "Determinant condition necessary for tree identifiability",
             cut("This condition on the determinants of the substitution matrices is known", "\\cite{chang1996full}.", 37926),
             "S6", origin="external", origin_citation="Chang 1996", conf=0.7)
E(DET01, CHANG, conf=0.7, basis="named", mention=True)
RP_GEN = node("remark", "Analysis extends to gene-specific rate matrices",
              cut("We note that \\cite{allman2019species} considered a slightly more general model", "more general model in \\cite{allman2019species}.", 38084),
              "S6", conf=0.75, rigor="semi_formal")
T(GTR, RP_GEN)
PPROD = node("claim", "Path substitution matrix is the product along the path",
             cut("By the Markov property, the substitution matrix $P^g_{i|j}$", "along the path between $i$ and $j$.", 39024),
             "S6", origin="external", origin_citation=STD, conf=0.75)
T(PMAT, PPROD)
SG = node("definition", "Gene similarity matrix $S^g$",
          cut("Next, note that the matrix from Eq.~\\eqref{eq:similarity} is an estimate of", "where $i$ and $j$ are extant species.", 39238),
          "S6", conf=0.85, definiendum="gene similarity matrix $S^g$")
EP_Sg = eq("F13", "Gene similarity as product of determinants")
T(PPROD, SG)
SGGTR = node("claim", "Closed form of gene similarity under GTR",
             cut("Under the GTR model, a closed form expression", "\\end{equation}", 39524), "S6", conf=0.8,
             conclusions=["S^g_{ij} = e^{4 \\text{tr}(Q)\\tau^g_{ij}}."])
EP_SgGTR = eq("F14", "Gene similarity under GTR")
T(SG, SGGTR)
T(TAUG, SGGTR)
E(PPROD, SGGTR, conf=0.8, basis="named")
E(DETP, SGGTR, conf=0.75)
SSP = node("definition", "Species similarity matrix $S$",
           cut("Analogously, we define the \\textit{species similarity matrix} $S$", "coalescence time of species $i$ and $j$ in the species tree.", 40107),
           "S6", conf=0.9, definiendum="species similarity matrix $S$")
EP_S = eq("F15", "Species similarity")
T(DIVT, SSP)
E(SGGTR, SSP, conf=0.7, basis="named")
SIMF = node("definition", "Similarity function $\\mathcal S(h,h')$ between tree nodes",
            cut("We extend the definition of the similarity in Eq.", "\\end{equation}", 40753), "S6", conf=0.85,
            definiendum="similarity function $\\cal S$")
EP_simf = eq("F16", "Node similarity")
T(PMAT, SIMF)
MULT = node("claim", "Multiplicativity of similarity along paths",
            cut("Then, the similarities of the three pairs of nodes satisfy", "\\end{equation}", 41089), "S6",
            origin="external", origin_citation=STD, conf=0.8,
            assumptions=["let $v_1,v_2,v_3$ be three nodes in a tree, such that $v_2$ lies on the unique path from $v_1$ to $v_3$"],
            conclusions=["\\mathcal S(v_1,v_3) = \\mathcal S(v_1,v_2) \\cdot \\mathcal S(v_2,v_3)."])
EP_mult = eq("F17", "Multiplicativity of similarity")
T(SIMF, MULT)
PP_MULT = node("proof", "Proof of multiplicativity",
               cut("Eq. \\eqref{eq:multiplicativity} holds under the general Markov model", "multiplicativity of determinants.", 41280),
               "S6", conf=0.75, statement_short="Markov property plus multiplicativity of determinants.")
E(PP_MULT, MULT, "proves", 0.8, "inferred")
EDGESIM = node("definition", "Edge similarity $\\mathcal S(e)$",
               cut("Finally, for future use, for any edge $e=(h,h')$ in a tree we define the edge similarity", "\\end{equation}", 41425),
               "S6", conf=0.9, definiendum="edge similarity")
EP_edge = eq("F18", "Edge similarity")
T(SIMF, EDGESIM)
EDGE01 = node("claim", "Edge similarities lie in (0,1)",
              cut("Since $\\text{Tr}(Q)<0$, for each edge $e$ the similarity", "$0<\\mathcal S(e)<1$.", 41621), "S6",
              conf=0.75, conclusions=["for each edge $e$ the similarity $0<\\mathcal S(e)<1$"])
T(EDGESIM, EDGE01)
E(DET01, EDGE01, conf=0.75)
DXI = node("definition", "Edge similarity bounds $\\delta,\\xi$",
           cut("For future use, we denote the lower and upper bounds of $S(e)$", "respectively.", 41700), "S6",
           conf=0.85, definiendum=["$\\delta$", "$\\xi$"])
T(EDGESIM, DXI)

# ---------------------------------------------------------------- 5.2
TH1 = env("theorem", "Spectral partitioning with a tree similarity matrix (STDR)", "F19", origin="external",
          origin_citation="Aizenbud et al. 2021, Theorem 4.2",
          assumptions=["Let $\\mathcal T$ be a binary tree, whose similarity matrix $S$ has all entries between $0$ and $1$.",
                       "Let $v$ be the Fiedler vector of the Laplacian matrix of $S$.",
                       "Let {$C_1$, $C_2$} be the partition of the terminal nodes of $\\mathcal T$ according to the sign pattern of $v$."],
          conclusions=["Then $C_1$, $C_2$ are clans in $\\mathcal T$."],
          statement_short="Splitting leaves by the sign of the Fiedler vector of a tree similarity matrix gives two clans.")
T(CLAN, TH1, 0.85)
T(FIED, TH1, 0.85)
WT = node("definition", "Matrix family $\\mathcal W_{\\mathcal T}$",
          cut("The family $\\mathcal W_{\\mathcal T}$ consists of all matrices that satisfy", "the following two conditions.", 43079),
          "S7", conf=0.85, definiendum="$\\mathcal W_{\\mathcal T}$")
RANK1 = env("definition", "The $\\mathcal T$ rank-1 condition", "F20", definiendum="rank-1 condition",
            differentia=["the submatrix $W(A,B)\\in \\mathds R_+^{|A| \\times |B|}$ is rank-1 if and only if $A$ and $B$ are clans in $\\mathcal T$"],
            statement_short="Cross blocks $W(A,B)$ are rank one exactly for the bipartitions of the leaves into two clans.")
T(CLAN, RANK1, 0.9)
SUBM = node("definition", "2x2 submatrix notation $W((i,i'),(j,j'))$",
            cut("For the next condition, let \\( W((i,i'),(j,j'))", "columns \\( (j,j') \\).", 43550), "S7", conf=0.8,
            definiendum="$W((i,i'),(j,j'))$")
TQ = node("definition", "Induced quartet subtree $\\mathcal T_Q$",
          cut("In addition, let \\( \\mathcal T_Q \\) denote the subtree", "induced by \\( \\mathcal T \\).", 43700), "S7",
          conf=0.8, definiendum="$\\mathcal T_Q$")
QUART = env("definition", "The $\\mathcal T$ quartet condition", "F21", definiendum="quartet condition",
            differentia=["for every quartet of nodes \\(Q = ( i,j,i',j') \\) such that \\( (i,j) \\) and \\( (i',j') \\) are siblings in \\( \\mathcal T_Q \\), \\[ |W((i,i'),(j,j'))| > 0. \\]"],
            statement_short="Every 2x2 cross submatrix of a quartet, with sibling pairs as row/column partners, has positive determinant.")
T(SUBM, QUART)
T(TQ, QUART)
E(RANK1, WT, conf=0.85)
E(QUART, WT, conf=0.85)
LEM1 = env("lemma", "Edge-weight assignment for matrices in $\\mathcal W_{\\mathcal T}$", "F22",
           assumptions=["Let $W \\in \\mathcal W_{\\mathcal T}$ be an arbitrary matrix that satisfies the rank-1 condition and the quartet condition with respect to a tree $\\mathcal T$."],
           conclusions=["there exists an assignment of edge weights in \\( \\mathcal T \\), taking values in \\( [0,1] \\), such that for all pairs $(i,j)$, $W(i,j)$ is equal to the product of weights along the path from node $i$ to node $j$."],
           statement_short="Any $W\\in\\mathcal W_{\\mathcal T}$ is the path-product similarity matrix of some edge weighting of $\\mathcal T$.")
for s in (WT, RANK1, QUART):
    T(s, LEM1, 0.85)
TH2 = env("theorem", "Spectral partitioning for $W\\in\\mathcal W_{\\mathcal T}$", "F23",
          assumptions=["Let $G$ be a graph whose nodes correspond to the terminal nodes of a tree $\\mathcal T$, and let $W$ denote its weight matrix.",
                       "Let $v$ be the Fiedler vector of the graph's unnormalized Laplacian matrix $L$.",
                       "If $W \\in \\mathcal W_{\\mathcal T}$"],
          conclusions=["partitioning the terminal nodes according to the sign pattern of $v$ yields two clans in $\\mathcal T$."],
          statement_short="The sign pattern of the Fiedler vector of any $W\\in\\mathcal W_{\\mathcal T}$ splits the leaves into two clans.")
T(WT, TH2, 0.9)
T(FIED, TH2, 0.85)
T(CLAN, TH2, 0.85)
E(VARIANT, TH2, conf=0.7)
PP_TH2 = env("proof", "Proof of Theorem 2", "F24", proof_strategy=["direct"],
             statement_short="Lemma 1 realizes $W$ as the similarity of a re-weighted copy of $\\mathcal T$; then Theorem 1 applies.")
step(PP_TH2, "By lemma \\ref{lem:weight_assignment}, if a matrix", "along the path from node $i$ to node $j$.", 45681,
     "apply_lemma", "Lemma 1 gives a tree $\\tilde{\\mathcal T}$ of the same topology with similarity $W$.", "Re-weighted tree")
step(PP_TH2, "Theorem \\ref{thm:stdr_partition} (Theorem 4.2 from", "two clans of $\\tilde {\\mathcal T}$.", 45987,
     "apply_lemma", "Theorem 1 on $\\tilde{\\mathcal T}$ gives two clans.", "Apply Theorem 1")
step(PP_TH2, "Since the topology of $\\tilde {\\mathcal T}$ is identical", "two clans of $\\mathcal T$.", 46200,
     "conclude", "Same topology, so the clans are clans of $\\mathcal T$.", "Transfer clans")

# ---------------------------------------------------------------- 5.3
LEM2 = env("lemma", "Expected gene similarity satisfies the rank-1 and quartet conditions", "F25",
           assumptions=["Let $\\mathcal T$ be a species tree, and let $\\mathcal T^{g}$ be a gene tree generated according to the MSC model.",
                        "Let $\\mathbb E[S^{g}]$ be the expected similarity matrix over the distribution of $\\mathcal T^{g}$."],
           conclusions=["Then $\\mathbb E[S^{g}]$ satisfies the rank-1 condition and the quartet condition with respect to $\\mathcal T$."])
for s in (RANK1, QUART, SG):
    T(s, LEM2, 0.85)
T(MSC, LEM2, 0.85)
PROP1 = env("assumption", "Property 1 (pairs with a common MRCA have equally distributed $\\Delta$)", "F26", conf=0.9,
            statement_short="$\\Delta^g_{ij}$ and $\\Delta^g_{i'j'}$ have the same law whenever the pairs share their MRCA.")
PROP2 = env("assumption", "Property 2 (stochastic dominance of coalescence excess)", "F27", conf=0.9,
            statement_short="For a triplet with $i,j$ closer, $\\Delta^g_{ij}$ is strictly stochastically dominated by $\\tau_{il}-\\tau_{ij}+\\Delta^g_{il}$.")
for s in (COAL, MRCA):
    T(s, PROP1)
for s in (COAL, MRCA, DIVT):
    T(s, PROP2)
PROPS = env("claim", "Properties 1 and 2 hold under the MSC", "F28", conf=0.9, rigor="semi_formal",
            conclusions=["under the MSC model, both properties 1 and 2 above indeed hold."],
            statement_short="Under the MSC, the excess coalescence times satisfy Properties 1 and 2.")
PP_PROPS = node("proof", "Argument that the MSC satisfies Properties 1 and 2",
                cut("Indeed, property 1 holds since", "the second property holds.", 48206), "S8", conf=0.75,
                statement_short="Property 1: same edge rates above a common MRCA. Property 2: condition on whether $i,j$ coalesce before $\\tau_{il}$.",
                proof_strategy=["case_analysis"])
step(PP_PROPS, "Indeed, property 1 holds since", "the same of both pairs.", 48206, "conclude",
     "Same MRCA means same edge rates up to the root.", "Property 1")
step(PP_PROPS, "As for the second property,", "the second property holds.", 48425, "case_split",
     "Condition on early coalescence of $i,j$ (positive probability event).", "Property 2")
E(PP_PROPS, PROPS, "proves", 0.8, "inferred")
for s in (PROP1, PROP2):
    E(s, PROPS, conf=0.9, basis="named")
E(MSC, PROPS, conf=0.85, basis="term")
E(COAL, PP_PROPS, conf=0.8, basis="term")
TH3 = env("theorem", "Asymptotic consistency of the SDSR partition step", "F29", main=True,
          assumptions=["Let $\\{\\mathcal T^{g}\\}_{g=1}^K$ be $K$ gene trees, generated independently from a species tree according to a distribution that satisfies properties 1 and 2 above.",
                       "Let $\\bar{S}= \\frac1K \\sum_{g=1}^K S^{g}$ be the empirical mean of their (exact) similarity matrices $S^{g}$ given in \\eqref{eq:GTR_similarity}.",
                       "Assume that all entries of the Fiedler vector of the Laplacian matrix corresponding to $\\mathbb{E}[S^{g}]$ are non-zero, and that the smallest non-zero eigenvalue has multiplicity 1."],
          conclusions=["as $K\\to\\infty$, the partition computed by \\texttt{SDSR} yields two clans in the species tree, with probability tending to one."],
          also_stated_at=[cut("We prove that under the MSC model,", "is asymptotically consistent.", 9923)],
          statement_short="With infinitely many exact gene similarity matrices, the spectral split yields two clans of the species tree with probability tending to one.")
for s in (PROP1, PROP2):
    E(s, TH3, conf=0.9, basis="named")
T(FIED, TH3, 0.85)
T(CLAN, TH3, 0.85)
E(EXACT, TH3, conf=0.75)
E(VARIANT, TH3, conf=0.75)

# ---------------------------------------------------------------- 5.4
CHILD = node("definition", "Root children $h_L,h_R$ and their clans $C_L,C_R$",
             cut("Specifically, let $h_R$", "descendants of $h_L$ and $h_R$ respectively.", 50900), "S9", conf=0.8,
             definiendum=["$h_L$", "$h_R$", "$C_L$", "$C_R$"])
T(SPTREE, CHILD, 0.75)
ETA = node("definition", "Imbalance parameter $\\eta$",
           cut("The imbalance parameter is", "\\min\\{ |C_L|,|C_R| \\} }$.", 51101), "S9", conf=0.85,
           definiendum="imbalance parameter $\\eta$")
T(CHILD, ETA)
TE = node("definition", "Tree $\\mathcal T_E$ with similarity $\\mathbb E[S^g]$",
          cut("Next, we define $\\mathcal{T}_E$ to be the tree", "as stated in Lemma \\ref{lem:population_mean}.", 51201),
          "S9", conf=0.85, definiendum="$\\mathcal{T}_E$")
T(SG, TE)
SMIN = node("definition", "Minimal expected similarity $S_{\\min}$",
            cut("We denote $S_{\\min}=", "pairs $i,j$ of terminal nodes.", 51525), "S9", conf=0.85,
            definiendum="$S_{\\min}$")
T(SG, SMIN)
SR = node("definition", "Separation parameter $s_r$",
          cut("Next, we introduce a", "two nodes $h,h'\\in\\mathcal{T}_E$.", 51649), "S9", conf=0.85,
          definiendum=["separation parameter $s_r$", "$S_E(h,h')$"])
T(TE, SR)
T(CHILD, SR)
T(SIMF, SR, 0.75)
TH4 = env("theorem", "Finite-gene guarantee for the partition step", "F30", main=True,
          assumptions=["Let $\\mathcal T$ be an ultrametric species tree with $m$ terminal nodes and imbalance parameter $\\eta$.",
                       "Let $h_L,h_R$ be the two children of the root $r$ of $\\mathcal T$ and let $C_L, C_R$ be their observed descendant species, respectively.",
                       "Let ${\\mathcal{T}^{g}}_{g=1}^K$ be $K$ i.i.d. gene trees generated according to the MSC+GTR model,",
                       "let $\\{S^{g}\\}_{g=1}^K$ be their exact similarity matrices.",
                       "Assume that for some $\\epsilon>0$, the number of genes $K$ satisfies"],
          conclusions=["with probability larger than $1-\\epsilon$, partitioning based on the Fiedler vector corresponding to $\\bar S=\\frac1K \\sum_g S^{g}$ yields the two clans $C_L$ and $C_R$ of the species tree $\\mathcal T$."],
          statement_short="For an ultrametric species tree, $K \\gtrsim \\eta^3 (1-s_r^2)^{-2} S_{\\min}^{-2}\\log(m/\\epsilon)$ genes (times $m^{2+2\\log_2\\xi}$ if $\\xi>1/2$) make the spectral split recover the root clans w.p. $1-\\epsilon$.")
EP_RHS = eq("F31", "Sufficient number of genes")
for s in (ETA, SR, SMIN, DXI, CHILD, FIED):
    T(s, TH4, 0.85)
for s in (A_MSC, A_GTR):
    T(s, TH4, 0.75)
E(EXACT, TH4, conf=0.75)
E(VARIANT, TH4, conf=0.7)
RP3 = env("remark", "Specific versus unspecified clans", "F32",
          statement_short="Theorem 4, unlike Theorem 3, identifies the root clans, thanks to ultrametricity.")
RP4 = env("remark", "Gene count blows up as $s_r\\to1$", "F33")
E(TH4, RP4, conf=0.8)
T(SR, RP4)
PROP_SDSR = env("proposition", "Full-pipeline guarantee for SDSR (single partition)", "F34", main=True, rigor="semi_formal",
                assumptions=["Assume that the assumptions of Theorem \\ref{thm:finite_gene_guarantee_v2} hold, and that the number of gene alignments $K$ satisfies Eq. \\eqref{eq:RHS_bound}.",
                             "If, for both subsets $\\tilde C_1$ and $\\tilde C_2$ the subroutine computes a tree topology that matches the subtree of $\\mathcal T$ induced by the respective subset"],
                conclusions=["\\texttt{SDSR} returns a tree with the same topology as $\\mathcal T$, with probability $1-\\epsilon$."],
                also_stated_at=[cut("Moreover, if \\texttt{SDSR} partitioned correctly the species", "the exact species tree.", 10700)],
                statement_short="If the gene count meets Theorem 4's bound and the subroutine is exact on both subsets, SDSR returns the true topology w.p. $1-\\epsilon$.")
E(MERGE, PROP_SDSR, conf=0.7)
T(SDSR, PROP_SDSR, 0.8)

# ================================================================ 6 Simulations
PACC = node("claim", "Partition accuracy improves with the number of genes",
            cut("The results show that as the number of genes increases, the estimated partitions approach", "ground-truth partitions.", 58770),
            "S12", conf=0.7, rigor="numerical")
E(SDSR, PACC, conf=0.8)
E(TH3, PACC, conf=0.6, mention=True)
SACC = node("claim", "SDSR keeps base-method accuracy while reducing runtime",
            cut("As seen in the figure, \\texttt{SDSR} combined with either", "while significantly reducing runtime.", 62017),
            "S13", conf=0.7, rigor="numerical")
SPEED = node("claim", "8x (single CPU) and 17x (parallel) speedup of SDSR+CA-ML on 200 species",
             cut("The runtime of \\texttt{SDSR} + \\texttt{CA-ML} was $8$ times faster", "on separate  CPUs.", 62513),
             "S13", conf=0.75, rigor="numerical",
             also_stated_at=[cut("For example, reconstructing a 200-species tree from 100 genes", "on the full data.", 11068)])
for s in (SACC, SPEED):
    E(SDSR, s, conf=0.8)
    E(CAML, s, conf=0.75, basis="term")
RP_SPEED = node("remark", "Observed speedups match the complexity analysis",
                cut("The runtime results are consistent with the analysis in Section", "observed speedup of $17$.", 62708),
                "S13", conf=0.7, rigor="numerical",
                statement_short="Predicted speedups $m/\\tau=4$ (one CPU) and $m^2/\\tau^2=16$ (parallel) match the observed 8x and 17x.")
E(SPEED, RP_SPEED, conf=0.8)
E(RP_CAML, RP_SPEED, conf=0.75)
UDC = node("claim", "SDSR versus uDance on 10,000 species",
           cut("The results show that for settings where the reconstruction is done with less than", "larger number of genes.", 64900),
           "S13", conf=0.7, rigor="numerical")
E(SDSR, UDC, conf=0.8)
T(UDANCE, UDC, 0.85)

# ================================================================ App A
LEM3 = env("lemma", "Quadratic solution of the balanced-split recurrence", "F35",
           assumptions=["Let $f(k)$ be a function that satisfies the recurrence equation \\[ f(k) \\leq \\max_{ \\alpha_0\\leq \\alpha<0.5} f(\\alpha k) + f((1-\\alpha)k) + c k^2 \\] for some $0<\\alpha_0\\leq 0.5$ independent of $k$."],
           conclusions=["Then $f(k) = \\mathcal{O}(k^2)$."])
PP_L3 = env("proof", "Proof of Lemma 3", "F36", proof_strategy=["strong_induction"],
            statement_short="Strong induction: $C_c(\\alpha^2+(1-\\alpha)^2)+c\\le C_c$ for $C_c$ large since $\\alpha\\ge\\alpha_0$.")
step(PP_L3, "We prove the bound by induction.", "$f(k) \\leq C_c k^2 $.", 68910, "induction_step",
     "Base case: small $k$ bounded by a constant.", "Base case")
step(PP_L3, "Assume for all $k <k_0$", "\\end{align*}", 69000, "induction_step",
     "Inductive step: plug the hypothesis into the recurrence.", "Inductive step")
step(PP_L3, "For large enough $C_c$", "concludes the proof.", 69444, "conclude",
     "Choose $C_c$ large to close the induction.", "Choose constant")
RP5 = env("remark", "Akra-Bazzi alternative for constant split ratio", "F38")
E(REC, RP5, conf=0.65)

# ================================================================ App B
LEM4 = env("lemma", "Rank-1 condition passes to clan subtrees", "F39",
           assumptions=["Let $\\mathcal T$ be a tree decomposed into $\\mathcal T = \\mathcal T_A \\cup \\mathcal T_B$, where $A$ and $B$ are clans of $\\mathcal T$.",
                        "Suppose that $W$ satisfies the rank-1 condition with respect to $\\mathcal T$."],
           conclusions=["$W(A,A)$ and $W(B,B)$ satisfy the rank-1 condition with respect to $\\mathcal T_A$ and $\\mathcal T_B$, respectively."])
T(RANK1, LEM4, 0.85)
PP_L4 = env("proof", "Proof of Lemma 4", "F40", proof_strategy=["direct"],
            statement_short="A clan of $\\mathcal T_A$ is a clan of $\\mathcal T$, so its cross block is a submatrix of a rank-1 block.")
step(PP_L4, "Let $A=A_1 \\cup A_2$ be a partition", "is rank-1.", 70414, "introduce_variable",
     "Split $A$ into two clans of $\\mathcal T_A$; goal: $W(A_1,A_2)$ rank one.", "Setup")
step(PP_L4, "To this end,", "is rank-1.", 70537, "apply_lemma",
     "$A_1$ is a clan of $\\mathcal T$, so $W(A_1,A_2\\cup B)$ is rank one.", "Rank-1 in $\\mathcal T$")
step(PP_L4, "This implies that its submatrix", "rank-1 as well.", 70700, "conclude",
     "A submatrix of a rank-1 matrix is rank one.", "Submatrix")
PP_L1 = env("proof", "Proof of Lemma 1", "F41", proof_strategy=["induction", "construction"],
            statement_short="Induction on $m$: split at an edge, weight each side by induction, and set the cut-edge weight $c_Ac_B$ from the rank-1 cross block. "
                            "Auxiliary Lemma 5 aligns the induced root weights with the singular vectors of $W(A,B)$.")
step(PP_L1, "We prove the lemma by induction on the number of terminal nodes", "thus satisfy the lemma.", 70845,
     "induction_step", "Base case: two leaves, one edge of weight $W(1,2)$.", "Base case")
step(PP_L1, "Next, we assume that the lemma holds for any tree with up to", "those in $B$.", 71137,
     "induction_step", "Inductive step: split $\\mathcal T$ at an edge into $\\mathcal T_A,\\mathcal T_B$ and block $W$.", "Split tree")
step(PP_L1, "The four blocks of $S$ satisfy the following two properties", "with respect to the tree $\\mathcal T$.", 72299,
     "setup", "Two block properties follow.", "Block properties")
step(PP_L1, "[\\RNum{1}]", "is rank-1.", 72428, "other", "Property I: cross block rank one.", "Property I", conf=0.95)
step(PP_L1, "[\\RNum{2}]", "respectively.", 72484, "other", "Property II: diagonal blocks satisfy the rank-1 condition.",
     "Property II", conf=0.95)
step(PP_L1, "Property I follows from the", "Lemma \\ref{lem:rank_1_submatrices}.", 72651, "apply_lemma",
     "Property I from the rank-1 condition ($W(A,B)=v_Av_B^T$); Property II from Lemma 4.", "Justify properties")
step(PP_L1, "By Property II and the induction hypothesis", "such weights to $T_B$.", 73048, "induction_step",
     "Weight $\\mathcal T_A$ and $\\mathcal T_B$ by the induction hypothesis.", "Apply hypothesis")
step(PP_L1, "We denote by $w(A,h_A)", "between the subset $B$ and $h_B$.", 73318, "introduce_variable",
     "Root-to-leaf weight products $w(A,h_A)$, $w(B,h_B)$.", "Root weight vectors")
step(PP_L1, "Our proof is based on the following auxiliary lemma.", "and $w(A,h_B)$.", 73587, "setup",
     "State auxiliary Lemma 5.", "Auxiliary lemma")
step(PP_L1, "We first complete the proof of Lemma", "= v_A v_B^T = W(A,B). \\]", 74126, "introduce_variable",
     "Set the cut-edge weight $c_Ac_B$, reproducing $W(A,B)$.", "Cut-edge weight")
CL = step(PP_L1, "Finally, we prove that the product $c_Ac_B$", "implies that $c_Ac_B<1$.", 74371, "bound_estimate",
          "Show $c_Ac_B<1$.", "Weight below one")
ORDER_SAVE = ORDER.get(CL)
step(CL, "Consider a quartet of nodes $(i,j) \\in A$", "(1-(c_Ac_B)^2). \\]", 74400, "algebraic_manipulation",
     "A quartet 2x2 determinant equals $W(i,j)W(i',j')(1-(c_Ac_B)^2)$.", "Quartet determinant")
step(CL, "By the definition of the rank-1 matrix", "implies that $c_Ac_B<1$.", 74824, "conclude",
     "Positivity of the determinant gives $c_Ac_B<1$.", "Conclude bound")
step(PP_L1, "Together with property \\RNum{2}, we found", "which proves Lemma \\ref{lem:weight_assignment}.", 74937,
     "conclude", "All path products match $W$.", "Conclude Lemma 1")
LEM5 = env("lemma", "Root weight vectors are proportional to the singular vectors of $W(A,B)$", "F43",
           conclusions=["The vectors $w(A,h_A)$ and $w(B,h_B)$ are proportional to $v_A$ and $v_B$ defined in Eq. \\eqref{eq:v_AB}."],
           statement_short="$w(A,h_A)=c_Av_A$ and $w(B,h_B)=c_Bv_B$ for constants $c_A,c_B$.")
PP_L5 = node("proof", "Proof of Lemma 5",
             cut("Let us now prove auxiliary Lemma", "which concludes the proof.", 75099), "S16", conf=0.9,
             proof_strategy=["direct", "algebraic_manipulation"],
             statement_short="Concatenated rank-1 blocks share left singular vectors; use the free scaling of the two child edges of $h_A$ to match constants.")
E(PP_L5, LEM5, "proves", 0.9, "named")
step(PP_L5, "Let us now prove auxiliary Lemma", "see illustration in Figure \\ref{fig:similarity_structure}.", 75099,
     "introduce_variable", "Children of $h_A,h_B$ and the split $A=A_1\\cup A_2$.", "Setup")
step(PP_L5, "Consider the submatrix $W(A_1,A_2)$.", "\\end{equation}", 75422, "apply_lemma",
     "Factor $W(A_1,A_2)$ through $h_{A1},h_A,h_{A2}$.", "Factor block")
step(PP_L5, "Note that we have a degree of freedom", "this degree of freedom shortly.", 75674, "other",
     "Scaling freedom between the two child edges of $h_A$.", "Scaling freedom")
step(PP_L5, "Next, consider three submatrices", "proportional to $w(A_1,h_{A1})$.", 75944, "other",
     "Concatenated rank-1 blocks share a left singular vector $\\propto w(A_1,h_{A1})$.", "Shared singular vector")
step(PP_L5, "We can apply a similar reasoning", "$c_{A2} w(A_2,h_{A2})$.", 76528, "other",
     "Same for $A_2$; constants $c_{A1},c_{A2}$.", "Second side")
step(PP_L5, "The submatrix $W(A,B)$ is a concatenation", "which equals $c_A w(A,h_A)$.", 76964, "substitute",
     "Choose edge weights so both constants equal $c_A$; then $v_A=c_Aw(A,h_A)$.", "Fix constants")
step(PP_L5, "A similar reasoning yields that $v_B", "which concludes the proof.", 77452, "conclude",
     "Symmetric argument for $v_B$.", "Conclude")


# ================================================================ App C
PP_L2 = env("proof", "Proof of Lemma 2", "F45", proof_strategy=["case_analysis", "direct"],
            statement_short="Clan splits: expected cross similarities are column-rescaled species similarities, so rank one. Non-clan splits: Property 2 makes a quartet determinant positive.")
step(PP_L2, "Let $S(A,B)$ and $S^{g}(A,B)$ denote", "$\\mathbb E[S^{g}(A,B)]$ is not rank-1.", 77823, "setup",
     "Plan: clan splits give rank one, non-clan splits do not.", "Plan")
C1 = step(PP_L2, "Assume $A$ and $B$ are clans obtained by disconnecting", "is also rank-1.", 78286, "case_split",
          "Case: $A,B$ clans.", "Clan case")
step(C1, "Assume $A$ and $B$ are clans obtained", "\\end{equation}", 78286, "substitute",
     "Write $S^g(i,k)=S(i,k)\\exp(-2\\Delta_{ik})$.", "Gene similarity factor")
step(C1, "Since $k$ is external to the clan $A$", "for any node $i\\in A$.", 78672, "apply_lemma",
     "Property 1: the factor's law is the same for all $i\\in A$.", "Apply Property 1")
step(C1, "Let $S(A,k)$ be a single column", "is also rank-1.", 79017, "conclude",
     "Each expected column is a rescaled species column, so rank one.", "Rank one")
C2 = step(PP_L2, "Next, consider the case where the subset $A$ is not a clan", "cannot be rank-1.", 79938, "case_split",
          "Case: $A$ not a clan.", "Non-clan case")
step(C2, "Next, consider the case", "\\end{equation}", 79938, "introduce_variable",
     "Pick a quartet with sibling pairs split across $A,B$; its 2x2 expected submatrix.", "Quartet submatrix")
step(C2, "Similar to Eq. \\eqref{eq:gene_sim}, each element", "\\exp(-2D(h_{k,l}, r)) \\]", 80546,
     "algebraic_manipulation", "Express entries via species similarities and path multiplicativity.", "Entries")
step(C2, "The determinant of the submatrix in Eq.", "\\end{align}", 81068, "algebraic_manipulation",
     "Expand the determinant.", "Determinant")
step(C2, "Consider the triplet $(i,j,l)$.", "\\mathbb E[\\exp(-2\\Delta_{k,l})]. \\]", 81487, "apply_lemma",
     "Property 2 with monotonicity of $e^{-2d}$ bounds the cross terms.", "Apply Property 2")
step(C2, "Hence, the determinant of the submatrix is positive", "cannot be rank-1.", 81942, "conclude",
     "Positive determinant: rank two, so not rank one.", "Not rank one")
step(PP_L2, "To prove that the quartet condition holds", "between $0$ and $1$.", 82071, "setup",
     "Reduce the quartet condition to tree similarity matrices with weights in $(0,1)$.", "Reduce quartet condition")
step(PP_L2, "Consider a quartet $Q = ((i,j),(k,l))$", "(1-S(h_{i,j},h_{k,l})^2). \\]", 82247, "algebraic_manipulation",
     "Quartet determinant equals $S(i,k)S(j,l)(1-S(h,h')^2)$.", "Quartet determinant")
step(PP_L2, "Since $0<S(h_{i,j},h_{k,l})<1$", "the quartet is positive.", 82646, "conclude",
     "Inner edge similarity below one makes it positive.", "Positive")
E(MULT, PP_L2, conf=0.85, basis="named")
E(PROPS, PP_L2, conf=0.75)
T(SSP, PP_L2)
T(CLAN, PP_L2)
PP_TH3 = env("proof", "Proof of Theorem 3", "F49", proof_strategy=["direct"],
             statement_short="Lemma 2 + Theorem 2 give clans for the population Fiedler vector; Davis-Kahan and the law of large numbers transfer the sign pattern to $\\bar S$.")
step(PP_TH3, "By", "is equal to $\\mathbb E[S^{g}]$.", 82862, "apply_lemma",
     "Lemma 2: $\\mathbb E[S^g]\\in\\mathcal W_{\\mathcal T}$; let $v$ be its Fiedler vector.", "Population matrix")
step(PP_TH3, "Since $\\mathbb E[S^{g}] \\in \\mathcal W_{\\mathcal T}$, Theorem", "yields two clans.", 83134,
     "apply_lemma", "Theorem 2: sign of $v$ gives two clans.", "Population split")
step(PP_TH3, "Let $\\bar L$ be the Laplacian of a graph whose weight matrix equals", "smallest eigenvalues of $\\bar L$.", 83289,
     "introduce_variable", "Sample Laplacian $\\bar L$, its Fiedler vector $\\hat v$ and eigenvalues.", "Sample objects")
step(PP_TH3, "By the Davis-Kahan theorem", "\\end{equation}", 83549, "apply_lemma",
     "Davis-Kahan bounds $\\|\\hat v-v\\|$.", "Davis-Kahan")
step(PP_TH3, "By the law of large numbers", "two clans in the species tree.", 83750, "conclude",
     "LLN makes the bound vanish; once below $\\min_j|v(j)|$ the sign patterns agree.", "Sign patterns agree")
DK = env("theorem", "Davis-Kahan theorem (applied to $\\hat v$)", "F50", origin="external",
         origin_citation="Davis & Kahan; Yu, Wang & Samworth 2015", conf=0.9,
         conclusions=["\\|\\hat v-v\\| \\leq 2^{3/2}\\frac{\\|\\bar L- \\mathbb E[\\bar L]\\|}{\\min(\\gamma_2,\\gamma_3-\\gamma_2)}."])
E(EXACT, PP_TH3, conf=0.6)

# ================================================================ App E
DISTAP = node("algorithm", "Partitioning via the average distance matrix (baseline variant)",
              cut("Let \\( D^g \\) denote a pairwise distance matrix", "Step 1a of Section \\ref{sec:method}.", 86205),
              "S21", conf=0.75,
              statement_short="Average the gene distance matrices first, exponentiate to one similarity matrix, then split by its Fiedler vector.")
astep(DISTAP, "Let \\( D^g \\) denote a pairwise distance matrix", "\\sum_{g=1}^{K} D^g. \\]", 86205, "compute",
      "Average the gene distance matrices.", "Average distances")
astep(DISTAP, "We compute a single similarity matrix via,", "compute its corresponding Laplacian.", 86396, "compute",
      "One similarity matrix $\\exp(-\\bar D)$ and its Laplacian.", "Similarity and Laplacian")
astep(DISTAP, "Partitioning is then performed based on the Fiedler vector", "Step 1a of Section \\ref{sec:method}.", 86518,
      "call", "Partition by the Fiedler vector as in SDSR.", "Partition")
E(SDSR, DISTAP, conf=0.8, basis="named")
T(FIED, DISTAP)
DISTC = node("claim", "Distance averaging yields less accurate partitions",
             cut("The results show that partitions obtained via the distance-based approach", "averaged Laplacian approach.", 86985),
             "S21", conf=0.7, rigor="numerical",
             also_stated_at=[cut("The results, presented in Appendix \\ref{sec:distance_partition}, show that this approach", "more errors than \\texttt{SDSR}.", 59200)])
E(DISTAP, DISTC, conf=0.85)
E(SDSR, DISTC, conf=0.8)

# ================================================================ App H
ALLOW = node("definition", "Allowed error $\\Delta(\\mathcal T_E)$",
             cut("The quantity $\\Delta(\\mathcal T_E)$ is", "Subsection \\ref{subsec:finite_gene_garantee}.", 92171),
             "S25", conf=0.85, definiendum="allowed error $\\Delta(\\mathcal T_E)$")
EP_allow = eq("F51", "Allowed error")
for s in (ETA, SMIN, SR, TE):
    T(s, ALLOW, 0.85)
LEM6 = env("lemma", "Gene count sufficient for a correct partition (in terms of the allowed error)", "F52",
           assumptions=["Let $\\mathcal T$ be an ultrametric species tree with $m$ terminal nodes and similarity matrix $S$.",
                        "Let $h_L,h_R$ be the two children of the root $r$ of $\\mathcal T$ and let $C_L,C_R$ be their observed descendant species, respectively.",
                        "Let $\\{\\mathcal{T}^g\\}_{g=1}^K$ be $K$ i.i.d. gene trees generated according to the MSC+GTR model,",
                        "let $\\{S^g\\}_{g=1}^K$ be their exact similarity matrices.",
                        "Assume that for some $\\epsilon>0$"],
           conclusions=["then, with probability larger than $1-\\epsilon$, partitioning based on the Fiedler vector corresponding to $\\bar S=\\frac1K \\sum_g S^{g}$ yields the two clans $C_L$ and $C_R$ of the species tree $\\mathcal T$."],
           statement_short="If $K \\ge (\\|S\\|^2/(2\\Delta^2)+2\\|S\\|/(3\\Delta))\\log(2m/\\epsilon)$, the spectral split recovers $C_L,C_R$ w.p. $1-\\epsilon$.")
EP_fg = eq("F53", "Gene count in terms of allowed error")
for s in (ALLOW, TE, CHILD, SSP):
    T(s, LEM6, 0.85)
for s in (A_MSC, A_GTR):
    T(s, LEM6, 0.75)
TRIV = node("claim", "Trivial bound $\\|S\\|\\le m$",
            cut("Since all entries $S(i,j)\\in[0,1]$, a trivial bound is", "$\\|S\\|\\leq m$.", 93907), "S25", conf=0.7,
            conclusions=["$\\|S\\|\\leq m$"])
T(SSP, TRIV, 0.75)
LEM7 = env("lemma", "Spectral norm bound for tree similarity matrices", "F54",
           assumptions=["Let $\\mathcal{T}$ be a (rooted or unrooted) binary tree with $m$ terminal nodes, and let $S$ denote its associated similarity matrix.",
                        "Assume that for some constant $\\xi<1$, the similarity values $\\mathcal S(e)$ at all edges $e$ of $\\mathcal T$ satisfy $\\mathcal S(e) \\leq \\xi$."],
           conclusions=["\\|S\\|\\leq \\begin{cases} 3/2 & \\xi \\leq 0.5 \\\\ 1 + 2(m-1)^{1 + \\log_{2} \\xi} & \\xi > 0.5 \\end{cases}"],
           statement_short="$\\|S\\|\\le 3/2$ if all edge similarities are at most $1/2$, else $\\|S\\|\\le 1+2(m-1)^{1+\\log_2\\xi}$.")
EP_Snorm = eq("F55", "Spectral norm bound")
for s in (EDGESIM, DXI):
    T(s, LEM7, 0.85)
E(TRIV, LEM7, conf=0.6, mention=True)
PP_TH4 = env("proof", "Proof of Theorem 4", "F56", proof_strategy=["direct", "algebraic_manipulation"],
             statement_short="Show the bound of Theorem 4 dominates that of Lemma 6 by bounding $1/\\Delta(\\mathcal T_E)$ and $\\|S\\|$ (Lemma 7) separately.")
step(PP_TH4, "Assume that the conditions of Theorem", "upper bound $\\|S\\|$ and $\\frac{1}{\\Delta(T_E)}$.", 94915, "setup",
     "Reduce to comparing the right-hand sides of (23) and (15).", "Reduction")
B1 = step(PP_TH4, "To bound $\\frac{1}{\\Delta(\\mathcal{T}_E)}$, we take", "where $c_1$ is some constant.", 95385, "bound_estimate",
          "Bound $1/\\Delta(\\mathcal T_E)\\le c_1\\eta^{3/2}/((1-s_r^2)S_{\\min})$.", "Bound inverse allowed error")
step(B1, "To bound $\\frac{1}{\\Delta(\\mathcal{T}_E)}$, we take", "\\end{equation}", 95385, "algebraic_manipulation",
     "Take the reciprocal of (22).", "Reciprocal")
step(B1, "Next, we bound the maximum term", "\\end{equation}", 95761, "bound_estimate",
     "Max term at most $(1+\\eta)/(1-s_r^2)$.", "Max term")
step(B1, "Now, notice that", "where $c_1$ is some constant.", 96028, "bound_estimate",
     "Absorb constants.", "Combine")
step(PP_TH4, "We now proceed to bounding the spectral norm", "where $c_2$ is a universal constant.", 96452, "apply_lemma",
     "Lemma 7 bounds $\\|S\\|$.", "Norm bound")
step(PP_TH4, "Next, since both", "\\end{equation}", 96900, "bound_estimate",
     "The quadratic term dominates: factor $7/6$.", "Dominant term")
step(PP_TH4, "Finally, combining equations", "yields Eq. \\eqref{eq:finite_gene}.", 97381, "conclude",
     "Combine the bounds.", "Combine")
E(LEM6, PP_TH4, conf=0.85, basis="named")
LEM8 = env("lemma", "Allowed error suffices for a correct spectral partition", "F62", rigor="semi_formal",
           assumptions=["Let $\\mathcal T^g$ be a gene tree generated according to the MSC+GTR model with an underlying ultrametric species tree $\\cal T$ with $m$ species.",
                        "Let $\\mathcal T_E$ be the tree that corresponds to the matrix $\\mathbb{E}[S^g]$, where $S^g$ is the similarity of $\\mathcal T^g$.",
                        "Let $\\Delta(\\mathcal{T}_E)$ be the allowed error defined in Eq. \\eqref{eq:allowed_error_quantity}."],
           conclusions=["partitioning the terminal nodes based on the Fiedler vector of the Laplacian of $A$ yields two clans in the species tree $\\mathcal T$."],
           statement_short="Any symmetric $A$ within $\\Delta(\\mathcal T_E)$ of $\\mathbb E[S^g]$ in spectral norm is split into two clans by its Fiedler vector.")
EP_ae2 = eq("F63", "Allowed error condition")
T(TE, LEM8, 0.85)
T(SG, LEM8, 0.75)
PP_L8A = node("proof", "Proof of Lemma 8 (reduction to Lemma 5.1 of Aizenbud et al.)",
              cut("The above lemma is a variant of Lemma 5.1 from", "Subsection \\ref{subsec:allowed_error_justification}.", 99446),
              "S26", conf=0.7, statement_short="Adapt Lemma 5.1 of Aizenbud et al.; it only needs $\\mathcal T_E$ ultrametric.")
step(PP_L8A, "The above lemma is a variant of Lemma 5.1 from", "\\cite{aizenbud2021spectral}.", 99446, "setup",
     "Lemma 8 is a variant of Aizenbud et al.'s Lemma 5.1.", "Cite variant")
step(PP_L8A, "To apply the proof of", "Subsection \\ref{subsec:allowed_error_justification}.", 99523, "setup",
     "It remains to show $\\mathcal T_E$ ultrametric (Section H.3).", "Remaining step")
E(PP_L8A, LEM8, "proves", 0.75, "inferred")
LEM9 = env("lemma", "Concentration inequality for the mean gene similarity", "F64",
           assumptions=["Let $\\mathcal T$ be a species tree with $m$ terminal nodes, and similarity matrix $S$.",
                        "Let $\\{\\mathcal T^g\\}_{g=1}^K$ be $K$ i.i.d. gene trees generated according to the MSC+GTR model,",
                        "let $\\{S^g\\}_{g=1}^K$ be their exact similarity matrices."],
           conclusions=["the matrix $\\bar{S}=\\frac{1}{K}\\sum_{g=1}^K S^g$ satisfies"],
           statement_short="Bernstein-type tail: $\\Pr(\\|\\bar S-\\mathbb E S^g\\|>t)\\le 2m\\exp(-\\frac{Kt^2/2}{\\|S\\|^2/4+\\|S\\|t/3})$.")
EP_conc = eq("F65", "Concentration bound")
for s in (SSP, SG):
    T(s, LEM9, 0.8)
for s in (A_MSC, A_GTR):
    T(s, LEM9, 0.75)
PP_L6 = env("proof", "Proof of Lemma 6", "F66", proof_strategy=["probabilistic"],
            statement_short="Lemma 9 with $t=\\Delta(\\mathcal T_E)$ makes the allowed-error event likely; Lemma 8 turns it into a correct partition.")
step(PP_L6, "Let $\\Delta(\\mathcal{T}_E)$ be the allowed error, defined in", "\\end{equation}", 100621, "apply_lemma",
     "Lemma 9 at $t=\\Delta(\\mathcal T_E)$.", "Concentration")
step(PP_L6, "By Lemma~\\ref{lem:the_allowed_error}, if", "output a correct partition.", 101065, "apply_lemma",
     "Lemma 8 on that event.", "Allowed error")
step(PP_L6, "It is easy to verify that if the number of genes", "which concludes the proof.", 101237, "conclude",
     "Gene count (23) makes the probability at least $1-\\epsilon$.", "Solve for $K$")
PP_L8B = node("proof", "Proof of Lemma 8, continued (reference matrix of a different tree)",
              cut("Here we address the difference between Lemma", "This is formalized in the following lemma.", 101550),
              "S27", conf=0.7, statement_short="The cited proof needs an ultrametric reference tree; Lemma 10 shows $\\mathcal T_E$ is ultrametric.")
step(PP_L8B, "Here we address the difference between Lemma", "from a reference matrix.", 101550, "setup",
     "Both results bound the spectral distance to a reference matrix.", "Common form")
step(PP_L8B, "The key difference lies in the assumptions", "corresponds to a different tree $\\mathcal T_E$.", 101957, "setup",
     "Here the reference matrix belongs to $\\mathcal T_E$, not $\\mathcal T$.", "Key difference")
step(PP_L8B, "To apply the original proof from", "This is formalized in the following lemma.", 102402, "setup",
     "Suffices: $\\mathcal T_E$ ultrametric (Lemma 10).", "Reduction")
E(PP_L8B, LEM8, "proves", 0.7, "inferred")
E(PP_L8B, PP_L8A, conf=0.8, basis="inferred")
LEM10 = env("lemma", "$\\mathcal T_E$ is ultrametric", "F68",
            assumptions=["Let $S$ be the similarity matrix of an ultrametric species tree $\\mathcal{T}$.",
                         "Let $S^g$ be the similarity matrix of a gene tree $\\mathcal T^g$ generated according to the MSC+GTR model."],
            conclusions=["the tree $\\mathcal{T}_E$ with similarity $\\mathbb{E}[S^g]$ is also ultrametric."])
for s in (TE, SSP, SG):
    T(s, LEM10, 0.8)
E(LEM10, PP_L8B, conf=0.9, basis="named")
E(LEM10, PP_L8A, conf=0.8, basis="inferred")
PP_L10 = env("proof", "Proof of Lemma 10", "F69", proof_strategy=["direct"],
             statement_short="Ultrametric iff constant cross-root similarity; $\\mathbb E[S^g_{ij}]=S_{ij}\\mathbb E[e^{4\\mathrm{tr}(Q)\\Delta^g_{ij}}]$ with identically distributed $\\Delta^g_{ij}$.")
step(PP_L10, "Recall that an ultrametric tree is a tree where", "a property of ultrametric trees.", 102953, "setup",
     "Recall ultrametricity via leaf-root similarity.", "Recall")
step(PP_L10, "Let $\\mathcal T$ be a rooted tree with similarity $S$", "where $s_0$ is some constant.", 103224, "invoke_identity",
     "Characterize ultrametric by constant cross-root similarity (33).", "Characterization")
step(PP_L10, "Next, let $\\mathcal T$ be a species tree, $S^g$", "for all $i\\in C_l, j\\in C_r$.", 103576, "setup",
     "Suffices: $\\mathbb E[S^g_{ij}]$ constant across the root.", "Reduction")
step(PP_L10, "By Eq. \\eqref{eq:ultrametric}, since $\\mathcal T$ is ultrametric",
     "=s_1 \\mathbb E[e^{4\\text{tr}(Q)\\Delta^g_{ij}}]. \\end{equation*}", 104004, "substitute",
     "Factor $\\mathbb E[S^g_{ij}]=s_1\\mathbb E[e^{4\\mathrm{tr}(Q)\\Delta^g_{ij}}]$.", "Factor expectation")
step(PP_L10, "It remains to claim that", "for all $i\\in C_l, j\\in C_r$.", 104766, "conclude",
     "MSC: the $\\Delta^g_{ij}$ are identically distributed across the root.", "Conclude")
E(PROP1, PP_L10, conf=0.75)
T(COAL, PP_L10)
LEM11 = env("lemma", "Matrix Bernstein inequality", "F73", origin="external", origin_citation="Tropp 2015 (matrix Bernstein)",
            assumptions=["Let $\\boldsymbol{A} = \\sum_{l=1}^{K} A_{l}$ where $A_{l}$ are independent random symmetric $m \\times m$ matrices with $\\mathbb{E}[A_{l}] = 0$ and $\\|A_{l}\\| \\leq L$."],
            conclusions=["Then for all $t \\geq 0$,"],
            statement_short="Tail bound $2m\\exp(-\\frac{t^2/2}{\\nu+Lt/3})$ for sums of independent bounded zero-mean symmetric matrices.")
EP_nu = eq("F74", "Matrix variance proxy")
EP_bern = eq("F75", "Matrix Bernstein bound")
LEM12 = env("lemma", "Gene similarities are dominated by species similarities", "F76",
            assumptions=["Assuming $\\mathcal T^g$ is a random gene tree generated according to the MSC+GTR model, and let $S^g$ be its similarity."],
            conclusions=["Then $\\forall i,j\\quad 0\\leq S^g_{ij}\\leq S_{ij}$."])
for s in (SG, SSP):
    T(s, LEM12)
LEM13 = env("lemma", "Spectral norm monotone under adding a nonnegative matrix", "F77",
            assumptions=["Let \\( A,B\\in \\mathbb{R}^{m\\times m} \\) be matrices whose entries are all non-negative."],
            conclusions=["\\|A\\| &\\leq\\|{A+B}\\|."])
LEM14 = env("lemma", "Spectral norm bounded by that of the entrywise absolute value", "F79",
            assumptions=["Let \\( A\\in \\mathbb{R}^{m\\times m} \\) be a matrix."],
            conclusions=["$\\|A\\|\\leq \\||A|\\|$"])
PP_L9 = env("proof", "Proof of Lemma 9", "F80", proof_strategy=["direct", "probabilistic"],
            statement_short="Apply matrix Bernstein to $\\sum_g(S^g-\\mathbb E S^g)$ with $L=\\|S\\|$ and $\\nu\\le K\\|S\\|^2/4$ from Lemmas 12-14. "
                            "The variance bound uses $\\sigma(S^g_{il})\\le S_{il}/2$ for bounded variables.")
step(PP_L9, "Multiplying by $K$, we rewrite", "upper bounds for these two quantities.", 107165, "apply_lemma",
     "Rescale and apply matrix Bernstein; need $L$ and $\\nu$.", "Bernstein setup")
LB = step(PP_L9, "Recall that  $L$ is an upper bound on", "Hence, we may take $L=\\|S\\|$.", 108078, "bound_estimate",
          "Bound $L=\\|S\\|$.", "Bound L")
step(LB, "Recall that  $L$ is an upper bound on", "\\end{equation}", 108078, "apply_lemma",
     "Lemma 12: entrywise $|S^g_{ij}-\\mathbb E S^g_{ij}|\\le S_{ij}$.", "Entrywise bound")
step(LB, "Next, we decompose $S$ as the sum", "\\end{equation}", 108434, "apply_lemma",
     "Lemma 13 on a nonnegative decomposition of $S$.", "Nonnegative split")
step(LB, "By Lemma~\\ref{lem:entrywise_absolute} and Equation", "Hence, we may take $L=\\|S\\|$.", 108919, "conclude",
     "Lemma 14 gives $\\|S^g-\\mathbb E S^g\\|\\le\\|S\\|$.", "Take L")
NB = step(PP_L9, "Denote $V = \\mathbb{E}", "\\nu(\\boldsymbol{S}) \\leq K\\| S \\|^{2}/4. \\end{equation*}", 109208, "bound_estimate",
          "Bound $\\nu\\le K\\|S\\|^2/4$.", "Bound nu")
step(NB, "Denote $V = \\mathbb{E}", "\\end{equation*}", 109208, "introduce_variable",
     "Write $V_{ij}$ as a sum of covariances.", "Variance matrix")
step(NB, "By the triangle inequality,", "\\end{equation*}", 109670, "bound_estimate",
     "Covariances bounded by products of standard deviations.", "Cauchy-Schwarz")
step(NB, "Recall that by Lemma~\\ref{lem:entry_noise}, $S^g_{il}", "\\end{equation*}", 110059, "bound_estimate",
     "Bounded variables: $\\sigma\\le S_{il}/2$, so $|V_{ij}|\\le (S^2)_{ij}/4$.", "Bounded variance")
step(NB, "We express $\\frac14 S^2$", "\\leq \\frac{1}{4} \\| S^{2} \\|. \\]", 110474, "apply_lemma",
     "Lemmas 13-14 give $\\|V\\|\\le\\|S^2\\|/4$.", "Norm of V")
step(NB, "Since \\( S \\) is symmetric,", "\\end{equation*}", 110889, "conclude",
     "$\\|S^2\\|=\\|S\\|^2$.", "Conclude nu")
step(PP_L9, "Inserting the above bounds on $L$", "\\eqref{eq:concentration_bar_S}.", 111103, "conclude",
     "Insert into Bernstein.", "Conclude")
UVEC = env("definition", "Root-to-leaf similarity vector $u$", "F89", definiendum="$u$")
T(SIMF, UVEC)
LEM15 = env("lemma", "$\\ell_1$ bound on the root similarity vector", "F90",
            assumptions=["Let $\\mathcal T$ be a rooted binary tree with $m$ leaves, and let $r$ be its root.",
                         "Recall that $\\xi$ denotes the upper bound on the similarity between adjacent nodes."],
            conclusions=["\\|u\\|_1 \\leq \\begin{cases} 1 & \\text{if } \\xi \\leq 0.5, \\\\ \\frac{1}{\\xi}m^{1 + \\log_2 \\xi} & \\text{if } \\xi > 0.5. \\end{cases}"],
            statement_short="$\\|u\\|_1\\le1$ if $\\xi\\le1/2$ (caterpillar extremal), else $\\le m^{1+\\log_2\\xi}/\\xi$ (balanced extremal).")
EP_u1 = eq("F91", "l1 bound on u")
T(UVEC, LEM15, 0.85)
T(DXI, LEM15, 0.85)
PP_L7 = env("proof", "Proof of Lemma 7", "F92", proof_strategy=["direct"],
            statement_short="$\\|S\\|\\le$ max row $\\ell_1$ norm $\\le 1+\\xi\\|u\\|_1$, then Lemma 15.")
step(PP_L7, "We start with a known inequality", "respectively.", 112830, "invoke_identity",
     "$\\|S\\|\\le\\sqrt{\\|S\\|_1\\|S\\|_\\infty}$.", "Norm inequality")
step(PP_L7, "Next, note that in general", "\\end{equation}", 113150, "invoke_identity",
     "Symmetry: $\\|S\\|_1=\\|S\\|_\\infty$.", "Symmetry")
step(PP_L7, "Recall that the $\\ell_\\infty$ operator norm", "\\end{equation}", 113376, "bound_estimate",
     "So $\\|S\\|\\le\\max_i\\|S_{[i,:]}\\|_1$.", "Row norm")
step(PP_L7, "We now bound $\\|S_{[i,:]}\\|_1$.", "see Definition \\ref{def:u_vec}.", 113779, "introduce_variable",
     "Remove leaf $i$, root the rest at its neighbour $r$, vector $u$.", "Reroot")
step(PP_L7, "Using the fact that the similarity function is multiplicative", "\\end{equation}", 114149, "bound_estimate",
     "Row sum at most $1+\\xi\\|u\\|_1$.", "Row bound")
step(PP_L7, "Finally, combining", "completes the proof.", 114580, "conclude",
     "Apply Lemma 15.", "Conclude")
E(MULT, PP_L7, conf=0.85, basis="named")
PP_L15 = env("proof", "Proof of Lemma 15", "F97", proof_strategy=["direct", "other"], rigor=None,
             statement_short="Bound $\\|u\\|_1$ by $B=\\sum_i\\xi^{d_i}$ and maximize over topologies by a leaf-pair moving exchange. "
                             "The sign of $1-2\\xi$ decides whether the caterpillar or the balanced tree is extremal.")
step(PP_L15, "Given a rooted tree $\\mathcal{T}$, let $u", "to the root $r$.", 114908, "introduce_variable",
     "Leaf depths $d_i$.", "Depths")
step(PP_L15, "By the multiplicative property of the similarity measure, $u_i$", "\\end{equation}", 115214, "bound_estimate",
     "$\\|u\\|_1\\le B=\\sum_i\\xi^{d_i}$.", "Depth bound")
step(PP_L15, "To prove the lemma, we thus need to bound", "namely is global.", 115620, "setup",
     "Maximize $B$ over topologies via an improving modification.", "Strategy")
step(PP_L15, "Specifically, given a candidate tree", "a balanced tree that maximizes $B$.", 116195, "introduce_variable",
     "Move a sibling leaf pair under another leaf.", "Modification")
step(PP_L15, "Precisely, let $\\tilde {\\cal T}$ be the modified tree", "\\end{equation}", 116731, "algebraic_manipulation",
     "$\\tilde B-B=(1-2\\xi)(\\xi^{d_i-1}-\\xi^{d_k})$.", "Change in B")
step(PP_L15, "One can see that Eq.", "that is, the caterpillar tree.", 117388, "case_split",
     "$\\xi\\le1/2$: deepen pairs until the caterpillar.", "Case xi <= 1/2")
step(PP_L15, "For $\\xi > 0.5$, the argument is analogous.", "depth $\\lfloor \\log_2 m \\rfloor + 1$.", 118017, "case_split",
     "$\\xi>1/2$: the balanced tree is extremal.", "Case xi > 1/2")
step(PP_L15, "We now compute $B$ for each of the two extreme cases.", "+ \\xi^{m-1} = 1. \\]", 118881, "bound_estimate",
     "Caterpillar: $B\\le1$.", "Caterpillar value")
step(PP_L15, "For the balanced tree, let $N$", "This concludes the proof.", 119252, "conclude",
     "Balanced: $B\\le m^{1+\\log_2\\xi}/\\xi$.", "Balanced value")
E(MULT, PP_L15, conf=0.85, basis="named")
T(DXI, PP_L15)
PP_L12 = env("proof", "Proof of Lemma 12", "F100", proof_strategy=["direct"],
             statement_short="$S^g_{ij}=S_{ij}\\exp(4\\mathrm{tr}(Q)\\Delta^g_{ij})$ with $\\Delta\\ge0$ and $\\mathrm{tr}(Q)<0$.")
T(COAL, PP_L12)
PP_L13 = env("proof", "Proof of Lemma 13", "F101", proof_strategy=["direct"],
             statement_short="A maximizing unit vector can be taken nonnegative; then $\\|Av\\|\\le\\|(A+B)v\\|$.")
step(PP_L13, "Let \\( v \\in \\mathbb{R}^m \\) be a unit vector", "we may replace \\( v \\) with \\( u \\).", 120820, "setup",
     "WLOG the maximizing vector is entrywise nonnegative.", "Nonnegative maximizer")
step(PP_L13, "Next, observe that since both", "\\leq \\|A + B\\|. \\]", 121406, "conclude",
     "Nonnegative vectors: $\\|Av\\|\\le\\|(A+B)v\\|$.", "Compare norms")
PP_L14 = env("proof", "Proof of Lemma 14", "F102", proof_strategy=["direct"],
             statement_short="Triangle inequality entrywise: $|Av|\\le|A||v|$.")
step(PP_L14, "Let $A$ be an $m \\times m$ matrix", "\\end{equation}", 121705, "introduce_variable",
     "Take the maximizing $v$ and $u=|v|$.", "Setup")
step(PP_L14, "Next, we turn to upper bound", "\\end{equation*}", 122085, "bound_estimate",
     "Entrywise $|(Av)_i|\\le(|A|u)_i$.", "Entrywise bound")
step(PP_L14, "Hence,", "completes the proof.", 122355, "conclude",
     "So $\\|A\\|\\le\\||A|\\|$.", "Conclude")

# ---------------------------------------------------------------- remaining equations (source order irrelevant for ids)
EQN = {"F42": "Rank-one cross block", "F44": "Factorization of $W(A_1,A_2)$", "F46": "Gene similarity factor",
       "F47": "Expected quartet submatrix", "F48": "Quartet determinant expansion", "F57": "Inverse allowed error",
       "F58": "Max-term bound", "F59": "Inverse allowed error bound", "F60": "Spectral norm bound (constants)",
       "F61": "Dominant term", "F67": "Allowed-error event probability", "F70": "Ultrametric characterization",
       "F81": "Rescaled tail probability", "F82": "Entrywise deviation bound", "F83": "Norm of deviation",
       "F87": "Variance entry bound", "F93": "Norm via l1 and l-infinity", "F94": "Symmetric operator norms",
       "F95": "Norm via row sums", "F96": "Row l1 bound", "F98": "Depth bound B", "F99": "Change of B",
       "F103": "Norm via absolute vector", "F105": "Norm bound via |A|"}
for fid, nm in EQN.items():
    eq(fid, nm)


# ---------------------------------------------------------------- defined-term edges (acting on finalize warnings, checked by reading)
TERM_USES = {
    GALN: ["ProbP1", "AP3", "RP1", "ClP3", "PrP1", "AP6"],
    FIED: ["RP1", "PP5", "PP12", "LP6", "LP8", "PP16"],
    CLAN: ["PP5", "DP44", "TP7", "RP4", "RP5", "LP4", "PP8", "PP9", "PP12", "LP6", "LP8", "PP16", "PP17"],
    SPTREE: ["DP25", "DP31", "LP2", "AssumP4", "TP6", "TP7", "RP4", "PP11", "PP12", "LP6", "LP8", "LP9", "PP16", "LP10", "PP17"],
    MRCA: ["ClP15", "ClP18", "PP6", "PP11"],
    DIVT: ["PP17", "PP21"],
    TAUG: ["PP17", "PP21"],
    RANK1: ["PP5", "PP8", "PP9", "PP10", "PP12"],
    QUART: ["PP11"],
    TE: ["PP13", "PP15"],
    SMIN: ["PP13"],
}
_have = {(e["source"], e["target"]) for e in edges}
for src_, tgts in TERM_USES.items():
    for t_ in tgts:
        if (src_, t_) not in _have:
            T(src_, t_, 0.75)

NOTES = {
    "extraction_notes": [
        {"category": "type_uncertain", "nodes": ["AssumP4", "AssumP5", "ClP18"],
         "note": "Properties 1 and 2 (\\newtheorem{prop}{Property}) are typed assumption, not claim: Theorem 3 takes them as hypotheses on the gene-tree law. Remark 2, which asserts they hold under the MSC and argues it, is retyped claim with its argument as a nested proof (PP6)."},
        {"category": "boundary_uncertain", "nodes": ["PP14", "PP16", "LP8"],
         "note": "Lemma 8 has no proof environment; its justification (adapting Lemma 5.1 of Aizenbud et al. once T_E is ultrametric) is split between the text after the lemma (H.2) and Section H.3, emitted as two proof parts; Lemma 8 is marked semi_formal."},
        {"category": "boundary_uncertain", "nodes": ["ClP16", "DP32"],
         "note": "The multiplicativity claim's hypothesis sentence ('let v_1,v_2,v_3 ...') precedes the definition of the node similarity, so the claim starts at 'Then, ...' and the hypothesis is carried verbatim in assumptions."},
        {"category": "rule_conflict", "nodes": ["DP25"],
         "note": "The MSC coalescence conditions are one enumerate that introduces Delta^g_ij (and local path edges e_1..e_l); kept as one definition rather than split mid-list, against the one-symbol-per-sentence warning."},
        {"category": "rule_conflict", "nodes": ["PP9", "PP10"],
         "note": "The prose proof of auxiliary Lemma 5 sits inside the proof of Lemma 1; the outer proof gets no setup step for it, since that step would duplicate PP10's span exactly."},
        {"category": "unexpected_construct", "nodes": ["AP3"],
         "note": "pseudocode_steps returned an empty span for the \\Return line; its statement is set to the verbatim printed text. \\EndIf/\\EndFor lines dropped."},
        {"category": "not_extracted", "nodes": [],
         "note": "Dataset descriptions, figure-only experiments (Appendices D, F, G) and the discussion's future work are not extracted; only headline numerical findings are claims. The introduction's contribution list is folded into also_stated_at of Theorem 3, Proposition 1 and the speedup claim."},
        {"category": "not_extracted", "nodes": ["AP4"],
         "note": "The identity argmin |d_j - D(C_1,C_2)| = argmin |v_j - vbar^(2)| ('by simple linear algebra') is kept inside the outgroup-selection algorithm step, not as a separate claim; it needs the two k-means clusters to be separated on the Fiedler line."},
        {"category": "source_problem", "nodes": ["DP4", "DP27", "DP2", "DP20", "PP11"],
         "note": "Notation is inconsistent: alphabet size l (Sec. 2) vs d (Sec. 5.1); an unrooted species tree (Sec. 2) vs a rooted timed one (Def. 1); Appendix C writes S^g = S exp(-2 Delta) with distances D, while Sec. 5.1 gives S^g = exp(4 tr(Q) tau^g)."},
    ],
    "extraction_comment": "Possible gaps found while reading: the proof of Lemma 4 shows only the clan-implies-rank-1 direction of the iff in the rank-1 condition; the quartet part of the proof of Lemma 2 relies on a tree realisation that Lemma 1 provides only once the quartet condition is known; and Eq. (33) in the proof of Lemma 10 is not an equivalence as written.",
}

# ---------------------------------------------------------------- sort and finalize
graph = {
    "metadata": {
        "title": "SDSR: A Spectral Divide-and-Conquer Approach for Species Tree Reconstruction",
        "arxiv_id": "2603.10215",
        "authors": ["Ortal Reshef", "Ofer Glassman", "Or Zuk", "Yariv Aizenbud", "Boaz Nadler", "Ariel Jaffe"],
        "year": 2026,
        "annotator": "agent-extraction",
        "model": "claude-opus-5-5",
        "effort": "default",
        "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
        "extraction_date": "2026-11-05",
        "rigor_nonformal_count": 0,
        "paper_style": ["theorem_proof", "computational"],
        "extraction_notes": [],
        "extraction_comment": "",
    },
    "nodes": nodes,
    "edges": edges,
}
graph["metadata"]["extraction_notes"] = NOTES["extraction_notes"]
graph["metadata"]["extraction_comment"] = NOTES["extraction_comment"]
graph["metadata"]["rigor_nonformal_count"] = sum(1 for n in nodes if n.get("rigor"))
for n in nodes:
    if n.get("rigor") is None:
        n.pop("rigor", None)

report = finalize(graph, read_tex(TEX))
for k in ("errors", "warnings"):
    print(f"== {k}: {len(report[k])}")
    for w in report[k]:
        print("  ", w)
print({k: v for k, v in report.items() if k not in ("errors", "warnings")})
assert not report["errors"], report["errors"]
json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
print("wrote", OUT, len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
