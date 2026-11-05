"""Build the SARANGA v7 graph of arXiv 1309.6919 (Zuk, Amir, Zeisel, Shamir, Shental 2013).
Node choices are made by reading; this script only slices the chosen spans."""
import json, sys, re
sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
from extraction_finalize import finalize
from latex_facts import read_tex, extract_facts

TEX = "/mnt/c/Code/Github/Saranga/corpus/orzuk/1309_6919/arxiv_src/BCS_next_gen_SPIRE_arxiv.tex"
OUT = "/mnt/c/Code/Github/Saranga/corpus/orzuk/1309_6919/1309_6919.json"
tex = read_tex(TEX)
facts = extract_facts(tex)
SRC = facts["source"]
FACT = {f["id"]: f for f in facts["facts"]}
SECS = sorted([s for s in facts["sections"] if s["inside"] is None], key=lambda s: s["start"])
SECNUM = {}
# printed numbering: 1..6 body sections; appendix "A" with subsections A.1..A.6
_body = 0; _sub = 0; _app = False; _asub = 0
for s in SECS:
    if s["level"] == 1:
        if s["title"] == "Appendix":
            _app = True; SECNUM[s["id"]] = "A"
        else:
            _body += 1; _sub = 0; SECNUM[s["id"]] = str(_body)
    else:
        if _app:
            _asub += 1; SECNUM[s["id"]] = f"A.{_asub}"
        else:
            _sub += 1; SECNUM[s["id"]] = f"{_body}.{_sub}"


def sec_of(pos):
    cur = None
    for s in SECS:
        if s["start"] <= pos:
            cur = s
    if not cur:
        return ""
    # the facts give no printed numbers for this paper: the plain title is used
    return f"{cur['number']} {cur['title']}" if cur["number"] else cur["title"]


def _pat(t):
    return r"\s+".join(re.escape(w) for w in t.split())


def sp(a, b, after=0):
    """Slice from the unique occurrence of `a` (after `after`) to the first `b` after it."""
    ms = [m for m in re.finditer(_pat(a), SRC) if m.start() >= after]
    assert len(ms) == 1, (len(ms), a)
    i = ms[0].start()
    m = re.compile(_pat(b)).search(SRC, i)
    assert m, (a, b)
    return SRC[i:m.end()]


def clean(s):
    return " ".join(s.split())


nodes, edges = [], []
BYID = {}


def N(id, type, name, stmt, origin="paper", conf=0.75, **kw):
    pos = SRC.find(stmt)
    assert pos >= 0, id
    n = {"id": id, "type": type, "name": name, "statement": clean(stmt),
         "section": sec_of(pos), "origin": origin, "confidence": conf}
    n.update(kw)
    nodes.append(n)
    BYID[id] = n
    return n


def F(id, fid, type, name, conf=1.0, **kw):
    f = FACT[fid]
    return N(id, type, name, SRC[f["start"]:f["end"]], conf=conf, **kw)


def ST(id, parent, order, subclass, name, short, a, b, conf=0.75, type="proof_step"):
    p = BYID[parent]
    stmt = sp(a, b, after=SRC.find(p["statement"][:40]) if False else 0)
    n = {"id": id, "type": type, "name": name, "statement": clean(stmt),
         "section": p["section"], "origin": p["origin"], "confidence": conf,
         "parent_id": parent, "step_order": order, "subclass": subclass,
         "statement_short": short}
    nodes.append(n)
    BYID[id] = n
    return n


def E(s, t, conf=0.8, basis="term", type="uses", **kw):
    e = {"source": s, "target": t, "type": type, "confidence": conf, "basis": basis}
    e.update(kw)
    edges.append(e)


STD = dict(origin="external", origin_citation="standard (uncited)")

# ======================= 2 The MCR Problem Formulation =======================
N("DP1", "definition", "Number of species $N$",
  sp("We denote by $N$ the number of species in the database.", "in the database."),
  conf=0.8, definiendum="$N$")
N("DP2", "definition", "Species sequences $S_1,..,S_N$ and alphabet $\\Upsilon$",
  sp("The species' 16S rRNA sequences are marked", "`G', `T'}\\}$."),
  conf=0.8, definiendum=["$S_1,..,S_N$", "$\\Upsilon$"])
N("AssumP1", "assumption", "Distinct database sequences",
  sp("We assume that the $S_i$'s are {\\it distinct} sequences.", "sequences."), conf=0.8)
N("DP3", "definition", "Sequence lengths $n_i$",
  sp("The sequences may have {\\it different} lengths", "$S_i \\in \\Upsilon^{n_i}$."),
  conf=0.8, definiendum="$n_i$")
N("DP4", "definition", "Maximum sequence length $n_{MAX}$",
  sp("We define the maximum sequence length as", "\\max_{i} n_i$."),
  conf=0.85, definiendum="$n_{MAX}$")
N("DP5", "definition", "Nucleotide and substring notation $s_{i,j}$, $s_{i,j:k}$",
  sp("We denote by $s_{i,j}$ the j-th nucleotide", "in the sequence $S_i$."),
  conf=0.8, definiendum=["$s_{i,j}$", "$s_{i,j:k}$"])
N("DP6", "definition", "Species frequency vector ${\\mathbf x}$",
  sp("We represent the proportion of each species in the mixture", "the frequency of species $i$."),
  conf=0.8, definiendum="${\\mathbf x}$")
N("DP7", "definition", "Probability simplex $\\Delta_N$",
  sp("We have ${\\mathbf x} \\in \\Delta_N$, where $\\Delta_N$ is the $N$-dimensional simplex",
     "\\sum_{i=1}^N x_i = 1 \\}$."),
  conf=0.85, **STD, definiendum="$\\Delta_N$", genus="the $N$-dimensional simplex")
N("DP8", "definition", "Interior of a set $int(\\mathcal{A})$",
  sp("We represent the interior of a set", "as $int(\\mathcal{A})$."),
  conf=0.8, **STD, definiendum="$int(\\mathcal{A})$")
N("DP9", "definition", "Interior of the simplex $int(\\Delta_N)$",
  sp("In particular, $int(\\Delta_N)$ is the subset of", "x_i > 0, \\: \\sum_{i=1}^N x_i = 1 \\}$."),
  conf=0.8, **STD, definiendum="$int(\\Delta_N)$", genus="the subset of $\\Delta_N$",
  differentia=["containing vectors with positive entries"])
N("DP10", "definition", "Reads $r_1,..,r_R$ of length $L$",
  sp("We observe data in the form of $R$ reads of length $L$", "sequencing technologies."),
  conf=0.8, definiendum=["$R$", "$L$", "$r_1, .., r_R$"])
N("DP11", "definition", "Read frequency vector ${\\mathbf y}$",
  sp("We represent the data by a vector of read frequencies", "\\quad \\forall j=1,..,4^L$."),
  conf=0.85, definiendum="${\\mathbf y}$",
  statement_short="${\\mathbf y}\\in\\Delta_{4^L}$ is the empirical frequency of each of the $4^L$ possible reads.")
N("DP12", "definition", "Lexicographic read index $lex(r)$",
  sp("Here $lex(r)$ is the index of $r$ in the lexicographic ordering", "= 4^L$)."),
  conf=0.85, definiendum="$lex(r)$")
N("DP13", "definition", "Inverse lexicographic transformation $lex^{-1}$",
  sp("We also define the inverse lexicographic ordering transformation", "'AAA ... ATC'}$)."),
  conf=0.85, definiendum="$lex^{-1}$")
N("ProbP1", "problem", "Microbial Community Reconstruction (MCR) problem",
  sp("In the {\\textbf {MCR} } problem, the data vector", "from this information."),
  conf=0.85, tags=["inverse_problem", "metagenomics"],
  statement_short="Given read frequencies ${\\mathbf y}$ and database sequences $S_1..S_N$, reconstruct species frequencies ${\\mathbf x}$.")
N("DP14", "definition", "Number of unique reads $M$",
  sp("The vector ${\\mathbf y}$ is of exponential length", "number of {\\it unique} sequence reads."),
  conf=0.75, definiendum="$M$")

# ======================= 2.1 Probabilistic Model =======================
N("DP15", "definition", "Two-step read sampling model and read-sampling matrix $A$",
  sp("We assume that the $R$ reads are sampled identically and independently", "A_{ij} = Pr(r = i | b = j)$. \\end{enumerate}"),
  conf=0.8, definiendum=["$x'_j$", "read-sampling matrix $A$"], tags=["generative_model", "mixture_model"],
  statement_short="Reads are i.i.d.: pick species $b$ with probability $\\propto x_j n_j$, then a read $i$ with probability $A_{ij}$.")
F("RP1", "F1", "remark", "Length re-weighting $x'$ vs $x$ disregarded",
  statement_short="The length-weighted sampling vector ${\\mathbf x}'$ is identified with ${\\mathbf x}$; they coincide for equal lengths and convert easily.")
N("DP16", "definition", "Read distribution $P_{\\mathbf x}({\\mathbf y};A,L)$",
  sp("The sampling process defines a probability distribution $P_{{\\mathbf x}}", "e^{(i)}_j =0 \\: \\forall j \\neq i$."),
  conf=0.85, definiendum=["$P_{{\\mathbf x}}({\\mathbf y} ; A, L)$", "${\\mathbf e}^{(i)}$"],
  statement_short="One read is distributed on the basis vectors ${\\mathbf e}^{(i)}$ of $\\Delta_{4^L}$ with probability $[A{\\mathbf x}]_i$.")
F("EP1", "F2", "equation", "Mixture model for a single read")
N("DP17", "definition", "Reads as i.i.d. random vectors ${\\mathbf y}^{(i)}$",
  sp("The data can be represented as $R$ i.i.d. random variables", "\\sum_{i=1}^R {\\mathbf y}^{(i)}$."),
  conf=0.8, definiendum="${\\mathbf y}^{(1)}, .., {\\mathbf y}^{(R)}$")
N("DP18", "definition", "Problem ${\\textbf {MCR}}(L,A)$",
  sp("We denote the {\\textbf {MCR} } problem with read sampling matrix $A$ by", "by ${\\textbf {MCR} }(L,A)$."),
  conf=0.85, definiendum="${\\textbf {MCR} }(L,A)$")
N("DP19", "definition", "Uniform error-free read-sampling matrix",
  sp("In its simplest form, $A$ can be constructed as follows,", "assuming $L \\leq n_j \\: \\forall j$."),
  conf=0.8, definiendum="$A_{ij}$ (uniform error-free sampling)",
  statement_short="$A_{ij}$ is the fraction of the $n_j-L+1$ length-$L$ windows of $S_j$ equal to read $i$.")
F("EP2", "F3", "equation", "Uniform sampling matrix $A_{ij}$")
N("AssumP2", "assumption", "Uniform tail for reads longer than the sequence",
  sp("If $L > n_i$ we assume that the `tail' of each read", "\\ref{sec:appendix_small_seq})."), conf=0.8)
F("RP2", "F4", "remark", "Extending $A$ to errors and biases; model limitations",
  statement_short="Errors and biases are modeled by changing $A$; the problem depends on the database only through $A$; amplification biases are not modeled.")
N("DP20", "definition", "Estimator $\\hat{{\\mathbf x}}$",
  sp("An estimator $\\hat{{\\mathbf x}}$ of the frequency vector", "collections of strings over $\\Upsilon$)."),
  conf=0.85, definiendum="estimator $\\hat{{\\mathbf x}}$", genus="a function from the set of all reads and database, to the $n$-dimensional simplex")
N("ProbP2", "problem", "Empirical loss minimization over the simplex",
  sp("We can solve the {\\textbf {MCR} } problem by finding an estimator", "\\label{eq:optproblem} \\end{equation}"),
  conf=0.85, tags=["constrained_optimization"],
  statement_short="Estimate ${\\mathbf x}$ by minimizing a loss $l(A{\\mathbf x},{\\mathbf y})$ over the simplex $\\Delta_N$.")
F("EP3", "F5", "equation", "Loss-minimizing estimator over the simplex")
N("DP21", "definition", "Kullback-Leibler loss $l_{KL}$",
  sp("A natural loss function is the Kullback-Leibler divergence", "D(P_{{\\mathbf y}} || P_{\\hat{{\\mathbf y}}})$."),
  conf=0.8, **STD, definiendum="$l_{KL}$")
N("ClP1", "claim", "KL loss minimization is maximum likelihood",
  sp("This formulation is equivalent to maximizing the likelihood of the data", "\\ref{eq:mixture_model})."),
  conf=0.7, **STD, assumptions=[], conclusions=["This formulation is equivalent to maximizing the likelihood of the data ${\\mathbf y}$"])
N("DP22", "definition", "$l_2$ loss",
  sp("We choose instead the $l_2$ loss", "mainly for computational considerations."),
  conf=0.8, **STD, definiendum="$l_{2}$ loss")
N("RP3", "remark", "$l_1$ relaxation is vacuous on the simplex",
  sp("The most common remedy of replacing the $l_0$ norm by the convex", "trivially holds."), conf=0.7)

# ======================= 2.2 Metrics =======================
N("DP23", "definition", "Euclidean reconstruction error $\\mathcal{D}_{l_2}$",
  sp("We use the simple $l_2$ norm as a representative of this group.", "(x_i - \\hat{x}_i)^2}$."),
  conf=0.8, **STD, definiendum="$\\mathcal{D}_{l_2}$")
N("DP24", "definition", "Phylogenetically-aware Mahalanobis distance $\\mathcal{D}_{MA}$",
  sp("We propose a novel Phylogenetically-aware criterion, using a Mahalanobis distance",
     "which are closely-related (remote)."),
  conf=0.85, definiendum="$\\mathcal{D}_{MA}({\\mathbf x}, \\hat{{\\mathbf x}}; D)$", genus="Mahalanobis distance",
  differentia=["The matrix $D$ is constructed to capture the phylogenetic distance between species"],
  tags=["metric", "phylogeny"],
  statement_short="Error metric $\\sqrt{({\\mathbf x}-\\hat{{\\mathbf x}})^\\top D({\\mathbf x}-\\hat{{\\mathbf x}})}$ with $D$ a species-similarity matrix.")
N("DP25", "definition", "Weight matrix $D = A^{\\top} A$",
  sp("For concreteness, we choose specifically $D = A^{\\top} A$", "based on their 16S rRNA sequences."),
  conf=0.8, definiendum="$D = A^{\\top} A$")

# ======================= 3 Species Identifiability =======================
F("DP26", "F6", "definition", "Identifiability of ${\\textbf {MCR}}(L,A)$",
  definiendum="identifiable", statement_short="Distinct frequency vectors always give distinct read distributions.")
F("PrP1", "F7", "proposition", "Rank criterion for identifiability", main=True,
  assumptions=["Let $A_{(1)}$ be the matrix constructed from $A$, concatenated with an all $1$'s row vector ${\\textbf 1_N}$"],
  conclusions=["The reconstruction problem ${\\textbf {MCR} }(L,A)$ is identifiable if and only if $rank(A_{(1)}) = N$."],
  equivalent_conditions=["The reconstruction problem ${\\textbf {MCR} }(L,A)$ is identifiable", "$rank(A_{(1)}) = N$"],
  statement_short="MCR(L,A) is identifiable iff $A$ stacked with an all-ones row has full column rank $N$.")
F("PrP2", "F8", "proposition", "Critical read length for identifiability", main=True,
  assumptions=["Assume $N > 4$.",
               "the database $S$ is composed of $N$ distinct sequences such that no sequence is a substring of another sequence",
               "Let $A^{(u,L)}$ be the sampling matrix obtained by {\\it uniform} sampling of reads with read length $L$, according to eq. (\\ref{eq:MixMatrix})."],
  conclusions=["there is a critical read length $L_c$, $1 < L_c \\leq \\max_i n_i$ such that the problem ${\\textbf {MCR} }(L,A^{(u,L)})$ is identifiable if and only if $L \\geq L_c$."],
  statement_short="For substring-free databases with $N>4$, uniform-read MCR is identifiable exactly for read lengths above a threshold $L_c\\in(1,n_{MAX}]$.")
F("RP4", "F9", "remark", "Relaxing the substring-free and uniform-sampling assumptions",
  statement_short="The substring-free assumption is for convenience and the result extends to non-uniform read sampling.")
F("DP27", "F10", "definition", "Partial identifiability for species $j$",
  definiendum="partially identifiable for species $j$",
  statement_short="Any two frequency vectors with the same read distribution agree on the frequency of species $j$.")
F("PrP3", "F11", "proposition", "Null-space criterion for partial identifiability", main=True,
  assumptions=[],
  conclusions=["The problem ${\\textbf {MCR} }(L,A)$ is partially identifiable for species $j$, if and only if the standard basis vector ${\\mathbf e}^{(j)} \\in \\Delta_N$ is orthogonal to the null-space of $A_{(1)}$, that is $A_{(1)} {\\mathbf x} = 0 \\Rightarrow x_j=0 \\: \\forall {\\mathbf x} \\in \\mathbb{R}^N$."],
  equivalent_conditions=["The problem ${\\textbf {MCR} }(L,A)$ is partially identifiable for species $j$",
                         "the standard basis vector ${\\mathbf e}^{(j)} \\in \\Delta_N$ is orthogonal to the null-space of $A_{(1)}$"],
  statement_short="Species $j$ is identifiable iff every null vector of $A_{(1)}$ has zero $j$-th coordinate.")

# ======================= 4 Reconstruction Error =======================
F("PrP4", "F12", "proposition", "Finite-sample reconstruction error bounds ($l_2$ and Mahalanobis)", main=True,
  assumptions=["Consider the problem ${\\textbf {MCR} }(L,A)$ with $R$ sequence reads",
               "let $\\hat{{\\mathbf x}}$ be the estimator minimizing the $l_2$ loss, $\\hat{{\\mathbf x}} = argmin_{{\\mathbf x} \\in \\Delta_N} l_2(A {\\mathbf x}, {\\mathbf y})$",
               "Let $\\lambda_{\\min}(A^{\\top}A)$ be the smallest eigenvalue of $A^{\\top}A$."],
  conclusions=["The Euclidian $l_2$ distance satisfies:", "The Mahalanobis distance with weight matrix $A^{\\top} A$ satisfies:"],
  parts=[{"assumptions": ["Let $\\lambda_{\\min}(A^{\\top}A)$ be the smallest eigenvalue of $A^{\\top}A$."],
          "conclusions": ["The Euclidian $l_2$ distance satisfies:"]},
         {"assumptions": [], "conclusions": ["The Mahalanobis distance with weight matrix $A^{\\top} A$ satisfies:"]}],
  tags=["bound", "concentration"],
  statement_short="With prob. $1-\\delta$ the $l_2$ estimator has Mahalanobis error $\\le(2+\\sqrt{\\log 1/\\delta})/\\sqrt R$, and $l_2$ error that over $\\sqrt{\\lambda_{\\min}(A^\\top A)}$.")
F("EP4", "F13", "equation", "$l_2$ error bound")
F("EP5", "F14", "equation", "Mahalanobis error bound")
N("RP5", "remark", "$l_2$ bound depends on the spectrum of $A^{\\top}A$",
  sp("The bound on the convergence rate of the $\\mathcal{D}_{l_2}$ error", "may be arbitrarily large."), conf=0.75,
  statement_short="The $l_2$ rate depends on $\\lambda_{\\min}(A^\\top A)$, i.e. database coherence; for non-identifiable problems it is vacuous.")
N("RP6", "remark", "Mahalanobis bound is dimension-free",
  sp("In contrast, the Mahalanobis bound does not depend on the matrix $A$", "yet highly similar species."), conf=0.75,
  statement_short="The Mahalanobis bound is free of $A$ and $N$, so it converges even without identifiability, mixing abundance among similar species.")

# ======================= 5 / A.5 Divide-and-Conquer Algorithm =======================
ALG = sp("{\\bf Box 1: Divide-and-Conquer Reconstruction Algorithm}",
         "output the normalized vector as the solution \\end{enumerate}")
N("AP1", "algorithm", "Divide-and-Conquer Reconstruction Algorithm (COMPASS)", ALG, conf=0.85, main=True,
  input=["$S$ - Set of Sequences", "${\\mathbf y}$ - read measurements", "Probabilistic model"],
  output=["${\\mathbf x}$ - vector of species frequencies"],
  also_stated_at=[clean(sp("In a nutshell, the algorithm divides the species into distinct blocks",
                           "iterates to reduce problem size."))],
  tags=["divide_and_conquer", "convex_optimization", "sparsity", "thresholding"],
  statement_short="Repeatedly solve nonnegative least squares on random species blocks, keep species above a threshold, shrink, and finally solve once on the survivors. Sparsity comes from the per-block thresholding.")
ST("ASP1", "AP1", 1, "loop", "Partition to blocks (repeat $k_{B,j}$ times)",
   "Initialize the indicator ${\\mathbf v}$ and repeat block partition-and-solve $k_{B,j}$ times.",
   "Partition to blocks: Set ${\\mathbf v}$ as a binary vector", "set $v_i = 1$. \\end{enumerate}",
   conf=0.75, type="algorithm_step")
ST("ASP2", "ASP1", 1, "compute", "Random partition into blocks of size $B$", "Split species randomly into blocks of size $B$.",
   "Partition species randomly into non-overlapping blocks of size $B$.", "of size $B$.", conf=0.75, type="algorithm_step")
ST("ASP3", "ASP1", 2, "solve", "Solve the block NNLS problem with CVX",
   "Per block, build $A^{(B)}$ and solve nonnegative least squares exactly.",
   "In each block (B) compute the matrix $A^{(B)}$", "\\label{eq:problem_representation_one_block} \\end{equation}",
   conf=0.75, type="algorithm_step")
ST("ASP4", "ASP1", 3, "select", "Keep species above threshold $\\tau_B$",
   "Mark species whose block frequency is at least $\\tau_B$.",
   "Collect all species with frequency above the threshold:", "Set $j=j+1$.", conf=0.75, type="algorithm_step")
ST("ASP5", "ASP1", 4, "select", "Keep non-identifiable (linearly dependent) species",
   "Also mark species that are not identifiable within the block.",
   "Collect all linearly dependent species:", "orthogonal to the null space of $A^{(B)}$) set $v_i = 1$.",
   conf=0.75, type="algorithm_step")
ST("ASP6", "AP1", 2, "filter", "Collect results from blocks", "Keep indices marked in at least one block.",
   "Collect results from blocks:", "in at least one block reconstruction.", conf=0.75, type="algorithm_step")
ST("ASP7", "AP1", 3, "test", "Reduce problem size and iterate", "Restrict $A$ to the kept species; iterate while more than $k_F$ remain.",
   "Reduce problem size:", "go back to step 1.", conf=0.75, type="algorithm_step")
ST("ASP8", "AP1", 4, "solve", "Final NNLS solve and normalization", "Solve NNLS on the survivors and normalize to sum one.",
   "Solve for the last time the $l_2$ minimization problem", "output the normalized vector as the solution",
   conf=0.75, type="algorithm_step")
F("EP6", "F27", "equation", "Block nonnegative least squares problem")
F("EP7", "F28", "equation", "Final reduced nonnegative least squares problem")

# ======================= A.1 Short sequences =======================
N("DP28", "definition", "Sampling matrix for sequences shorter than the read length",
  sp("For completeness, we adopt a convention of a read having it's first", "(in lexicographic ordering)."),
  conf=0.8, definiendum=["$A_{ij}$ (for $L > n_j$)", "$lex^{-1}(i)_{1:k}$"],
  statement_short="When $L>n_j$ a read is the whole sequence followed by a uniform random tail, which multiplies the entry by $4^{n_j-L}$.")
F("EP8", "F15", "equation", "Generalized sampling matrix for $L > n_j$")

# ======================= A.2 Proof of Prop 1 =======================
F("PP1", "F16", "proof", "Proof of the rank criterion for identifiability", proves="PrP1",
  proof_strategy=["direct", "construction"],
  statement_short="Identifiability is injectivity of $A$ on $\\Delta_N$, equivalently of $A_{(1)}$; full rank gives it, and a null vector perturbs an interior point.")
ST("PSP1", "PP1", 1, "setup", "Reduce identifiability to injectivity of $A$ on $\\Delta_N$",
   "Identifiability means $A{\\mathbf x}$ determines ${\\mathbf x}$ on the simplex.",
   "From eq. (\\ref{eq:mixture_model}), we have $P_{{\\mathbf x}}({\\mathbf e}^{(i)} ; A, L) = [A {\\mathbf x}]_i",
   "Therefore identifiability holds if and only if $A {\\mathbf x}^{(1)} = A {\\mathbf x}^{(2)} \\Rightarrow {\\mathbf x}^{(1)} = {\\mathbf x}^{(2)}, \\: \\forall {\\mathbf x}^{(1)}, {\\mathbf x}^{(2)} \\in \\Delta_N$.")
ST("PSP2", "PP1", 2, "algebraic_manipulation", "Appending the ones row changes nothing on the simplex",
   "On $\\Delta_N$ the extra entry of $A_{(1)}{\\mathbf x}$ is 1, so $A_{(1)}$ and $A$ are injective together.",
   "The vector $A_{(1)} {\\mathbf x}$ is of size $4^L+1$", "Therefore $A_{(1)} {\\mathbf x}^{(1)} = A_{(1)} {\\mathbf x}^{(2)} \\iff")
ST("PSP3", "PP1", 3, "case_split", "Full rank implies identifiability", "If rank is $N$, $A_{(1)}$ is injective on all of $\\mathbb{R}^N$.",
   "If $rank(A_{(1)}) = N$, we have", "and identifiability holds.")
ST("PSP4", "PP1", 4, "case_split", "Rank deficiency gives a non-identifying perturbation",
   "A null vector of $A_{(1)}$ sums to zero; adding a small multiple to an interior point gives the same read distribution.",
   "Conversely, if $rank(A_{(1)}) < N$ then there exists", "is not identifiable.")
# PSP2 ends mid-sentence above; fix it to the full sentence
BYID["PSP2"]["statement"] = clean(sp("The vector $A_{(1)} {\\mathbf x}$ is of size $4^L+1$",
                                     "{\\mathbf x}^{(2)} \\in \\Delta_N$. If $rank"))[:-len(" If $rank")]

# ======================= A.3 Proof of Prop 2 =======================
F("PP2", "F17", "proof", "Proof of the critical read length", proves="PrP2",
  proof_strategy=["construction", "direct"],
  statement_short="Three steps: $L=1$ is not identifiable by a rank count, $L=n_{MAX}$ is by padded full-sequence reads, and identifiability is monotone in $L$ by marginalization.")
ST("PSP5", "PP2", 1, "bound_estimate", "$L=1$ is not identifiable",
   "With $L=1$, $A$ has rank at most 4 < N, so a null vector gives two mixtures with the same read distribution.",
   "Take $L=1$. Then the vector", "(1,A^{(u,1)})$ is not identifiable.")
ST("PSP6", "PP2", 2, "introduce_variable", "$L=n_{MAX}$ is identifiable via padded full-sequence reads",
   "The read $S_j$ padded with A's occurs only in species $j$, giving $N$ independent rows and full rank.",
   "Take $L = n_{MAX} (=\\max_i n_i)$.", "A^{(u,n_{MAX})})$ is identifiable.")
ST("PSP7", "PP2", 3, "conclude", "Identifiability is monotone in $L$",
   "The length-$L$ read distribution is a marginal of the length-$L'$ one, so identifiability persists for $L'>L$.",
   "Suppose that the problem is ${\\textbf {MCR} }(L,A^{(u,L)})$ is identifiable, and let $L' > L$.",
   "is also identifiable for $L'$.")

# ======================= A.4 Proof of Prop 3 =======================
F("PP3", "F18", "proof", "Proof of the null-space criterion for partial identifiability", proves="PrP3",
  proof_strategy=["direct"],
  statement_short="As for Proposition 1, reduce to $A_{(1)}$; the difference of two mixtures is a null vector, and an interior perturbation gives the converse.")
ST("PSP8", "PP3", 1, "setup", "Reduce partial identifiability to $A_{(1)}$",
   "Partial identifiability means equal $A_{(1)}{\\mathbf x}$ forces equal $j$-th coordinates on $\\Delta_N$.",
   "In similar to Proposition \\ref{prop:identifiability}, since", "\\forall {\\mathbf x}^{(1)}, {\\mathbf x}^{(2)} \\in \\Delta_N$. Assume")
BYID["PSP8"]["statement"] = BYID["PSP8"]["statement"][:-len(" Assume")]
ST("PSP9", "PP3", 2, "case_split", "Null-space condition implies partial identifiability",
   "Apply the null-space condition to ${\\mathbf x}^{(1)}-{\\mathbf x}^{(2)}$.",
   "Assume that $A_{(1)} {\\mathbf x} = 0 \\Rightarrow x_j=0", "is partially identifiable for species $j$. For")
BYID["PSP9"]["statement"] = BYID["PSP9"]["statement"][:-len(" For")]
ST("PSP10", "PP3", 3, "case_split", "Partial identifiability implies the null-space condition",
   "Perturb an interior point along a null vector; equal read distributions force $x_j=0$.",
   "For the other direction, assume that", "\\Rightarrow x_j=0. \\end{equation}")
F("EP9", "F19", "equation", "Null-space condition forces equal $j$-th coordinates")
F("EP10", "F20", "equation", "Converse implication for partial identifiability")

# ======================= A.4 16S rRNA identifiability =======================
N("ClP2", "claim", "Most Greengenes species are partially identifiable, but not all even at $L=100$",
  sp("Even for very short \\ensuremath{L}, we can identify most species,", "which are not identifiable."),
  conf=0.7, rigor="numerical", tags=["16S_rRNA", "identifiability"],
  assumptions=[], conclusions=["Even for very short \\ensuremath{L}, we can identify most species",
                               "even when \\ensuremath{L}\\: is long ($\\ensuremath{L}=100$), there is still a small subset of species which are not identifiable."])

# ======================= A.5 Proof of Prop 4 =======================
F("PP4", "F21", "proof", "Proof of the reconstruction error bounds", proves="PrP4",
  proof_strategy=["direct", "probabilistic"],
  statement_short="Projection onto the convex set $A(\\Delta_N)$ is non-expansive, so Mahalanobis error is at most $\\|{\\mathbf y}-{\\mathbf y}^*\\|$; a vector concentration bound finishes. The $l_2$ bound follows via $\\lambda_{\\min}(A^\\top A)$.")
ST("PSP11", "PP4", 1, "apply_lemma", "Non-expansiveness of convex projection",
   "$A\\hat{{\\mathbf x}}$ and $A{\\mathbf x}^*$ are projections onto $A(\\Delta_N)$, so their distance is at most $\\|{\\mathbf y}-{\\mathbf y}^*\\|_2$.",
   "Eq. (\\ref{eq:optproblem}) with a $l_2$ loss implies", "\\leq \\norm{{\\mathbf y}-{\\mathbf y}^{*}}_2. \\end{equation}")
ST("PSP12", "PP4", 2, "invoke_identity", "Left side is the Mahalanobis distance",
   "Identify $\\|A{\\mathbf x}-A{\\mathbf x}^*\\|_2$ with $\\mathcal{D}_{MA}$ for $D=A^\\top A$.",
   "The left hand side above is equal to the Mahalanobis distance", "\\label{eq:metric_inequality} \\end{equation}")
ST("PSP13", "PP4", 3, "bound_estimate", "Vector large-deviation bound for ${\\mathbf y}$",
   "Concentration of the mean of i.i.d. vectors bounds $\\|{\\mathbf y}-{\\mathbf y}^*\\|_2$.",
   "Recall that ${\\mathbf y} = \\frac{1}{R} \\sum_{i=1}^R {\\mathbf y}^{(i)}$", "\\label{eq:metric_large_deviation} \\end{equation}")
ST("PSP14", "PP4", 4, "conclude", "Combine to get part 2", "Chain the two inequalities for the Mahalanobis bound.",
   "Combining eqs. (\\ref{eq:metric_inequality},\\ref{eq:metric_large_deviation}), we get part $2$", "of the proposition.")
ST("PSP15", "PP4", 5, "conclude", "Convert to the Euclidean bound via $\\lambda_{\\min}$",
   "Eigen-decomposition gives $\\mathcal{D}_{MA}^2\\ge\\lambda_{\\min}\\mathcal{D}_{l_2}^2$, which yields part 1.",
   "To prove part $1$, we need to convert this result", "gives immediately part $1$.")
F("EP11", "F22", "equation", "Projection non-expansiveness inequality")
F("EP12", "F23", "equation", "Mahalanobis distance as $\\|A{\\mathbf x}-A{\\mathbf x}^*\\|_2$")
F("EP13", "F24", "equation", "Mahalanobis error bounded by read-frequency deviation")
F("EP14", "F25", "equation", "Large-deviation bound on $\\|{\\mathbf y}-{\\mathbf y}^*\\|_2$")
F("EP15", "F26", "equation", "Mahalanobis vs Euclidean via smallest eigenvalue")

# ======================= A.6 Simulation results =======================
N("ClP3", "claim", "Accurate reconstruction in simulation, well below the bounds",
  sp("Very low error ($\\sim\\!2\\%$) is achieved for $R > 500,000$,", "indicating that tighter bounds might be achieved."),
  conf=0.7, rigor="numerical", tags=["simulation"],
  assumptions=["$R > 500,000$"],
  conclusions=["Very low error ($\\sim\\!2\\%$) is achieved", "The error rate achieved in practice is much lower than the theoretical bounds"])
N("OpenP1", "open_problem", "Improved sparsity-aware reconstruction bounds",
  sp("Proving improved bounds on reconstruction performance which consider all these issues", "which does not hold in our case, and do not consider the poisson sampling model we use for the reads."),
  conf=0.7, statement_short="Prove reconstruction bounds that exploit sparsity, for the coherent matrices $A$ of this problem.")

# ======================= edges =======================
# terms / notation
for t in ["DP7", "DP14"]:
    E("DP1", t, 0.75)
for t in ["AssumP1", "DP3", "DP5", "DP10", "ProbP1", "DP20"]:
    E("DP2", t, 0.8)
E("DP3", "DP4", 0.85); E("DP3", "DP15", 0.8); E("DP3", "DP19", 0.8); E("DP3", "DP28", 0.8); E("DP3", "AssumP2", 0.8)
E("DP4", "PP2", 0.85)
E("DP3", "PrP2", 0.8); E("DP7", "PP2", 0.8); E("DP7", "PP4", 0.8); E("DP16", "PP1", 0.85); E("DP16", "PP3", 0.85)
E("DP5", "DP19", 0.8); E("DP5", "PrP2", 0.85); E("DP5", "DP28", 0.8)
for t in ["DP7", "ProbP1", "DP15", "DP20"]:
    E("DP6", t, 0.8)
for t in ["DP9", "DP20", "ProbP2", "DP26", "DP27", "PrP4", "PP1", "PP3"]:
    E("DP7", t, 0.8)
E("DP8", "DP9", 0.85)
for t in ["PP1", "PP2", "PP3"]:
    E("DP9", t, 0.85)
for t in ["DP11", "DP15", "DP17", "PrP4", "AssumP2"]:
    E("DP10", t, 0.8)
for t in ["ProbP1", "DP17", "ProbP2", "AP1"]:
    E("DP11", t, 0.8)
E("DP12", "DP11", 0.85); E("DP12", "PP2", 0.85); E("DP12", "DP13", 0.8)
E("DP13", "DP19", 0.85); E("DP13", "DP28", 0.85)
E("ProbP1", "ProbP2", 0.8, basis="inferred")
for t in ["RP1", "DP16", "DP18", "DP19", "RP2", "ProbP2", "PrP1", "PrP4", "DP25", "AP1", "RP5"]:
    E("DP15", t, 0.8)
for t in ["DP17", "DP26", "DP27", "ClP1"]:
    E("DP16", t, 0.85)
E("DP17", "PP4", 0.85)
for t in ["DP26", "DP27", "PrP1", "PrP2", "PrP3", "PrP4"]:
    E("DP18", t, 0.85)
E("AssumP2", "DP28", 0.85, basis="named")
E("DP20", "ProbP2", 0.85)
E("ProbP2", "DP21", 0.75, basis="inferred"); E("ProbP2", "DP22", 0.75, basis="inferred"); E("ProbP2", "RP3", 0.7, basis="inferred")
E("DP21", "ClP1", 0.85)
E("DP22", "PrP4", 0.85); E("DP22", "PP4", 0.85)
E("DP23", "PrP4", 0.85); E("DP23", "RP5", 0.85); E("DP23", "PP4", 0.85)
E("DP24", "DP25", 0.85); E("DP24", "PrP4", 0.85); E("DP24", "RP6", 0.85); E("DP24", "PP4", 0.85)
E("DP25", "PrP4", 0.85)
E("DP26", "PrP1", 0.9); E("DP26", "PrP2", 0.9); E("DP26", "RP4", 0.8); E("DP26", "RP5", 0.8); E("DP26", "RP6", 0.8)
E("DP26", "PP1", 0.85); E("DP26", "PP2", 0.9, basis="named")
E("DP27", "PrP3", 0.9); E("DP27", "PP3", 0.85); E("DP27", "ClP2", 0.8); E("DP27", "ASP5", 0.7)
E("PrP1", "PrP3", 0.8, basis="term")          # A_(1) is introduced in Proposition 1
E("PrP1", "PP2", 0.8, basis="inferred")       # "Therefore rank(A_(1))=N and the problem is identifiable"
E("DP28", "PP2", 0.7, basis="inferred")       # padded reads r^(j) for L = n_MAX > n_j
E("PrP2", "RP4", 0.8, basis="inferred", mention=True)
E("PrP4", "RP5", 0.85, basis="inferred"); E("PrP4", "RP6", 0.85, basis="inferred")
E("PrP3", "ClP2", 0.6, basis="inferred"); E("PrP3", "ASP5", 0.65, basis="inferred")
E("PrP4", "ClP3", 0.8, basis="inferred", mention=True)
E("ClP3", "OpenP1", 0.75, basis="inferred", mention=True)
E("PrP4", "OpenP1", 0.75, basis="inferred", mention=True)
E("ProbP2", "AP1", 0.8, basis="inferred", type="resolves")
E("ProbP1", "AP1", 0.8, basis="inferred", type="resolves")
E("AP1", "ClP3", 0.9, basis="named")          # "We performed reconstruction using Algorithm 1"
# proves edges for the appendix proofs ("Proof of Proposition \ref{...}" headings)
for pp, r in [("PP1", "PrP1"), ("PP2", "PrP2"), ("PP3", "PrP3"), ("PP4", "PrP4")]:
    E(pp, r, 0.95, basis="named", type="proves")
# inside proofs
E("PSP1", "PSP2", 0.8, basis="inferred"); E("PSP2", "PSP3", 0.8, basis="inferred"); E("PSP2", "PSP4", 0.8, basis="inferred")
E("PSP11", "PSP12", 0.8, basis="inferred"); E("PSP12", "PSP14", 0.8, basis="inferred"); E("PSP13", "PSP14", 0.8, basis="inferred")
E("PSP14", "PSP15", 0.8, basis="inferred")
E("PSP8", "PSP9", 0.75, basis="inferred"); E("PSP8", "PSP10", 0.75, basis="inferred")
E("ASP3", "ASP4", 0.8, basis="inferred"); E("ASP4", "ASP6", 0.8, basis="inferred"); E("ASP5", "ASP6", 0.8, basis="inferred")
E("ASP6", "ASP7", 0.8, basis="inferred"); E("ASP7", "ASP8", 0.8, basis="inferred")

rigor_n = sum(1 for n in nodes if "rigor" in n)
graph = {
    "metadata": {
        "title": "Accurate Profiling of Microbial Communities from Massively Parallel Sequencing using Convex Optimization",
        "arxiv_id": "1309.6919",
        "authors": ["Or Zuk", "Amnon Amir", "Amit Zeisel", "Ohad Shamir", "Noam Shental"],
        "year": 2013,
        "annotator": "agent-extraction",
        "model": "claude-opus-5-5",
        "effort": "default",
        "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
        "extraction_date": "2026-11-05",
        "rigor_nonformal_count": rigor_n,
        "paper_style": ["modeling", "theorem_proof"],
        "extraction_notes": [
            {"category": "unexpected_construct", "nodes": ["AP1"],
             "note": "The algorithm is a `framed` box with nested enumerate, not an algorithm environment; extracted as a prose algorithm with unmarked steps. The Section 5 'In a nutshell' summary is kept in also_stated_at."},
            {"category": "source_problem", "nodes": ["EP6", "EP7"],
             "note": "Both numbered displays (14) and (15) carry the same \\label{eq:problem_representation_one_block} (duplicate label in the source)."},
            {"category": "type_uncertain", "nodes": ["DP15"],
             "note": "definition or assumption: the i.i.d. two-step sampling is phrased 'We assume', but it introduces $x'_j$ and $A$ that the rest of the paper uses."},
            {"category": "boundary_uncertain", "nodes": ["PP4"],
             "note": "Proof environments have no [Proof of ...] argument; proves edges come from the subsection headings 'Proof of Proposition \\ref{...}'."},
            {"category": "not_extracted", "nodes": [],
             "note": "Simulation set-up parameters (A.6), the count bound on $K$ (used only in its paragraph), running-time statements and figure captions were not made nodes."},
        ],
        "extraction_comment": "",
    },
    "nodes": nodes,
    "edges": edges,
}
report = finalize(graph, tex)
print(json.dumps({k: v for k, v in report.items() if k not in ("warnings",)}, indent=1)[:4000])
for w in report["warnings"]:
    print("WARN", w)
assert not report["errors"], report["errors"]
json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
print("wrote", OUT, len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
