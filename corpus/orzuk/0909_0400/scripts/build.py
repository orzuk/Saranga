"""Build the SARANGA v7 graph of arXiv 0909.0400 (Shental, Amir, Zuk 2009).
Node choices are made by reading; this script only slices the chosen spans."""
import json, sys, re
sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
from extraction_finalize import finalize
from latex_facts import read_tex, extract_facts

TEX = "/mnt/c/Code/Github/Saranga/corpus/orzuk/0909_0400/arxiv_src/cs_seq_NS_AA_OZ.tex"
OUT = "/mnt/c/Code/Github/Saranga/corpus/orzuk/0909_0400/0909_0400.json"
tex = read_tex(TEX)
facts = extract_facts(tex)
SRC = facts["source"]
FACT = {f["id"]: f for f in facts["facts"]}
SECS = sorted([s for s in facts["sections"] if s["inside"] is None], key=lambda s: s["start"])

def sec_of(pos):
    cur = None
    for s in SECS:
        if s["start"] <= pos:
            cur = s
    return f"{cur['number']} {cur['title']}" if cur else ""

def _pat(t):
    return r"\s+".join(re.escape(w) for w in t.split())

def sp(a, b):
    """Slice from the unique occurrence of `a` to the first `b` after it (whitespace-insensitive)."""
    ms = list(re.finditer(_pat(a), SRC))
    assert len(ms) == 1, (len(ms), a)
    i = ms[0].start()
    m = re.compile(_pat(b)).search(SRC, i)
    assert m, (a, b)
    return SRC[i:m.end()]

def clean(s):
    return " ".join(s.split())

nodes, edges = [], []
def N(id, type, name, stmt, origin="paper", conf=0.75, **kw):
    pos = SRC.find(stmt)
    assert pos >= 0, id
    n = {"id": id, "type": type, "name": name, "statement": clean(stmt),
         "section": sec_of(pos), "origin": origin, "confidence": conf}
    n.update(kw)
    nodes.append(n)
    return n

def EQ(id, fid, name, conf=1.0, **kw):
    f = FACT[fid]
    N(id, "equation", name, SRC[f["start"]:f["end"]], conf=conf, **kw)

def E(s, t, conf=0.8, basis="term", type="uses", **kw):
    e = {"source": s, "target": t, "type": type, "confidence": conf, "basis": basis}
    e.update(kw)
    edges.append(e)

EXT = dict(origin="external")
# ---------------- 2.1 The Compressed Sensing Problem ----------------
N("DP1", "definition", "Compressed sensing measurements",
  sp("In a standard {\\bf CS } problem one wishes", "i=1,\\ldots,k$."), conf=0.8,
  origin="external", origin_citation="standard (uncited)",
  definiendum=["$\\textbf{x}$", "$N$", "$k$", "$y_i$", "$\\textbf{m}_{i}$"],
  statement_short="Standard CS: recover a sparse length-$N$ vector x from $k$ linear measurements $y_i=\\mathbf{m}_i\\cdot\\mathbf{x}$.")
N("DP2", "definition", "Measurement (sensing) matrix",
  sp("This may be represented as solving the following set of linear equations", "lower case to denote scalars: $x,y,x_i$.)"),
  conf=0.85, origin="external", origin_citation="standard (uncited)",
  definiendum=["measurement matrix", "sensing matrix", "$M$"],
  differentia=["whose rows are the different $\\textbf{m}_i$'s"],
  statement_short="The measurements form the linear system $M\\mathbf{x}=\\mathbf{y}$ with $M$ the $k\\times N$ sensing matrix; notation conventions.")
EQ("EP1", "F1", "Linear measurement system $M\\mathbf{x}=\\mathbf{y}$")
N("TP1", "theorem", "Compressed sensing unique recovery",
  sp("However, it has been shown that if $\\textbf{x}$ is sparse,", "is the number of non-zero entries in $\\textbf{x}$."),
  conf=0.8, origin="external", origin_citation="Candes, Romberg & Tao 2006; Donoho 2006",
  assumptions=["$\\textbf{x}$ is sparse", "$M$ has certain properties", "$k > C s \\log (N/s)$",
               "$C$ is a constant, and $s$ is the is the number of non-zero entries in $\\textbf{x}$"],
  conclusions=["the original vector $\\textbf{x}$ can be recovered uniquely from Eq.~(\\ref{eq:cs_classic})"],
  statement_short="A sparse x is uniquely recoverable from $k > C s\\log(N/s)$ measurements by a suitable $M$.")
N("DP3", "definition", "Uniform Uncertainty Principle (Restricted Isometry Property)",
  sp("A sensing matrix which  allows for a correct reconstruction", "``invertible'' for sparse vectors $\\textbf{x}$."),
  conf=0.85, origin="external", origin_citation="Candes & Tao 2005; Candes, Romberg & Tao 2006",
  definiendum=["Uniform Uncertainty Principle", "UUP", "Restricted Isometry Property", "RIP"],
  differentia=["any subset of the columns of $M$ of size $2s$ form a matrix which is almost orthogonal"],
  statement_short="UUP/RIP: every $2s$ columns of $M$ are nearly orthogonal, making $M$ invertible on sparse vectors.")
N("DP4", "definition", "Bernoulli matrix",
  sp("As an example of a UUP matrix consider a Bernoulli matrix", "divided by $\\sqrt{k}$.}."),
  conf=0.8, origin="external", origin_citation="standard (uncited)",
  definiendum="Bernoulli matrix", genus="matrix",
  differentia=["entries are independent random variables set to be $1$ or $-1$ with probability $0.5$"])
N("TP2", "theorem", "Random Bernoulli matrices satisfy UUP",
  sp("It is known that almost any instance of such a random matrix", "standard Gaussian random variable.)"),
  conf=0.8, origin="external", origin_citation="Donoho 2006; Candes & Tao 2006",
  assumptions=["such a random matrix"],
  conclusions=["almost any instance of such a random matrix will satisfy UUP with an overwhelming probability"],
  statement_short="Random Bernoulli (or Gaussian) matrices satisfy UUP with overwhelming probability.")
N("ProbP1", "problem", "$\\ell_0$ sparse recovery problem",
  sp("Once $M$ and $\\textbf{y}$ are given,", "number of non-zero elements in $\\textbf{x}$."),
  conf=0.85, origin="external", origin_citation="standard (uncited)",
  statement_short="Find the sparsest x (minimum $\\ell_0$ norm) with $M\\mathbf{x}=\\mathbf{y}$.")
EQ("EP2", "F2", "$\\ell_0$ minimization")
N("TP3", "theorem", "Intractability of $\\ell_0$ minimization",
  sp("Problem (\\ref{eq:cs_problem}) involves a non-convex", "intractable in general \\cite{candes2005error}."),
  conf=0.75, origin="external", origin_citation="Candes & Tao 2005",
  assumptions=[], conclusions=["can be shown to be computationally intractable in general"])
N("TP4", "theorem", "$\\ell_1$ relaxation equivalence",
  sp("However, another impressive breakthrough", "identical to the solution of problem (\\ref{eq:cs_problem})."),
  conf=0.7, origin="external", origin_citation="CS theory (Candes; Donoho)",
  assumptions=["under certain conditions"],
  conclusions=["one can relax this constraint to the closest convex $\\ell_p$ norm, namely the $\\ell_1$ norm, and still get a solution which, under certain conditions, is identical to the solution of problem (\\ref{eq:cs_problem})"],
  statement_short="Under conditions, the convex $\\ell_1$ relaxation has the same solution as the $\\ell_0$ problem.")
N("ProbP2", "problem", "$\\ell_1$ minimization (basis pursuit)",
  sp("Hence the problem is reformulated as the following $\\ell_1$ minimization problem", "\\label{eq:cs_problem_L1}\n\\end{equation}"),
  conf=0.85, origin="external", origin_citation="standard (uncited)")
EQ("EP3", "F3", "$\\ell_1$ minimization")
N("ProbP3", "problem", "Noisy $\\ell_1$ minimization",
  sp("In most realistic {\\bf CS } problems measurements are corrupted by noise", "while still obtaining a sparse solution."),
  conf=0.85, origin="external", origin_citation="standard (uncited)",
  statement_short="With noisy measurements $M\\mathbf{x}+\\eta=\\mathbf{y}$, minimize $\\|x\\|_1$ s.t. $\\|Mx-y\\|_2\\le\\epsilon$.")
EQ("EP4", "F4", "Noisy $\\ell_1$ minimization")
N("TP5", "theorem", "Robustness of CS reconstruction to noise",
  sp("It is known that {\\bf CS } reconstruction is robust to noise", "number of measurements $k$ \\cite{candes2005stable}."),
  conf=0.75, origin="external", origin_citation="Candes, Romberg & Tao 2006 (stable recovery)",
  assumptions=["adding the noise term $\\epsilon$"],
  conclusions=["{\\bf CS } reconstruction is robust to noise",
               "does not cause a breakdown of the {\\bf CS } machinery, but merely leads to a possible increase in the number of measurements $k$"])
# ---------------- 2.2 Rare-allele identification in a CS framework ----------------
N("DP5", "definition", "Number of individuals $N$",
  sp("We wish to reconstruct the genotypes of $N$ individuals", "at a specific locus."), conf=0.75,
  definiendum="$N$")
N("DP6", "definition", "Genotype vector",
  sp("The genotypes are represented by a vector $\\textbf{x}$ of length $N$", "of the {\\it i}'th individual."),
  conf=0.85, definiendum=["genotype vector", "$\\textbf{x}$"])
N("DP7", "definition", "Reference and alternative alleles $A$, $B$",
  sp("We denote the reference allele", "alternative allele by $B$."), conf=0.85,
  definiendum=["$A$", "$B$"])
N("DP8", "definition", "Genotype encoding $x_i\\in\\{0,1,2\\}$",
  sp("The possible entries of $x_{i}$ are $0$, $1$ and $2$", "respectively."), conf=0.85,
  definiendum="$x_{i}$",
  statement_short="$x_i\\in\\{0,1,2\\}$ encodes genotypes AA, AB, BB (number of B alleles).")
N("RP1", "remark", "Integer genotypes ease reconstruction",
  sp("In classic {\\bf CS } the unknown variables are typically real numbers.", "simplifies the reconstruction problem \\cite{Donoho:positive}."),
  conf=0.65, rigor="conjectural",
  statement_short="The integer restriction on x is expected to reduce the measurements needed; even positivity already helps (Donoho).")
N("DP9", "definition", "Bernoulli(0.5) pooling design",
  sp("The sensing matrix $M$ is built of $k$ different measurements", "a certain individual is $0.5$."),
  conf=0.85, definiendum=["sensing matrix $M$", "$m_{ij}$"], 
  differentia=["The entry $m_{ij}$ is set to $1$ if the {\\it j}'th individual participates in {\\it i}'th measurement, and zero otherwise",
               "the probability to include a certain individual is $0.5$"],
  statement_short="Pool $i$ contains each individual independently with probability 0.5; $m_{ij}=1$ iff individual $j$ is in pool $i$.")
N("ClP1", "claim", "Pooling matrix is a good sensing matrix",
  sp("Hence, $M$ is equivalent to the Bernoulli matrix mentioned", "is considered in Section~\\ref{sec:Results})."),
  conf=0.7, rigor="semi_formal",
  assumptions=["$M$"], conclusions=["$M$ is equivalent to the Bernoulli matrix mentioned in Section~\\ref{sec:csIntro}, which is known to be a ``good'' sensing matrix"],
  statement_short="The 0/1 pooling matrix is an affine transform of a $\\pm1$ Bernoulli matrix, hence a good sensing matrix.")
N("AP1", "algorithm", "Pooled sequencing measurement protocol",
  sp("In practice, measurements are performed by taking equal amounts of DNA", "such as MAQ \\cite{li2008mapping}.)"),
  conf=0.7, statement_short="Mix equal DNA amounts per pool, PCR-amplify, sequence each pool in its own lane and map reads to the reference.")
N("ASP1", "algorithm_step", "Mix equal DNA amounts",
  sp("In practice, measurements are performed by taking equal amounts of DNA", "approximately equal."),
  conf=0.7, parent_id="AP1", step_order=1, subclass="initialize")
N("ASP2", "algorithm_step", "PCR amplification",
  sp("Then, the mixture is amplified using PCR", "\\cite{Ingman:01}."),
  conf=0.7, parent_id="AP1", step_order=2, subclass="compute")
N("ASP3", "algorithm_step", "Sequence each pool and map reads",
  sp("Finally, DNA of each pool is sequenced in a separate lane", "such as MAQ \\cite{li2008mapping}.)"),
  conf=0.7, parent_id="AP1", step_order=3, subclass="compute")
N("DP10", "definition", "Reads per pool $r$",
  sp("For each locus of interest we record the number of reads", "in each pool, denoted by $r$."),
  conf=0.8, definiendum="$r$")
N("DP11", "definition", "Measurement vector $\\mathbf{y}$ (pool frequencies)",
  sp("These numbers provide the measurement vector $\\textbf{y}$", "in the $k$ different pools."),
  conf=0.8, definiendum=["measurement vector", "$\\textbf{y}$"])
N("ProbP4", "problem", "Rare-allele carrier identification",
  sp("For each locus, our goal is to reconstruct the vector $\\textbf{x}$,", "(see Eq.~(\\ref{eq:cs_problemFinal}).)"),
  conf=0.7, statement_short="Per locus, reconstruct the genotype vector x from the pooling matrix M and noisy pool frequencies y.")
# ---------------- 2.3 Mathematical formulation ----------------
N("DP12", "definition", "Rare-allele frequency $f$",
  sp("The fraction of individuals with the rare allele is denoted $f$", "is in fact $1-\\sqrt{1-f}$.}."),
  conf=0.85, definiendum=["$f$", "rare-allele-frequency", "$s$"],
  statement_short="$f$ = fraction of carrier individuals, so x has $s=fN$ non-zeros (allele frequency is $1-\\sqrt{1-f}$ under HW).")
N("DP13", "definition", "Normalized pooling matrix $\\hat M$",
  sp("$M$ is a $k \\times N$ Bernoulli sensing matrix,", "\\hat{m}_{ij} \\equiv \\frac{m_{ij}}{\\sum_{j=1}^{N} m_{ij}}\n\\end{equation}"),
  conf=0.85, definiendum="$\\hat{M}$", 
  differentia=["entries represent the fraction of each individual's DNA in each pool"])
EQ("EP5", "F5", "Row normalization $\\hat m_{ij}$")
N("AssumP1", "assumption", "Perfect unbiased mixing",
  sp("Assume that the mixing of DNA is perfect and unbiased,", "by the sequencing machinery."), conf=0.85)
N("DP14", "definition", "B-allele read probability $q_i$",
  sp("Suppose that a read from the {\\it i}'th pool is drawn", "sequenced for each individual.)"),
  conf=0.8, definiendum="$q_i$",
  statement_short="A read from pool $i$ carries allele B with probability $q_i=\\frac12\\hat{\\mathbf m}_i\\cdot\\mathbf x$.")
N("DP15", "definition", "Pool B-allele frequency vector $\\mathbf q$",
  sp("The vector of frequencies of the $B$ allele, for each of the $k$ pools", "\\textbf{q}=\\frac{1}{2}\\hat{M}\\textbf{x}\n\\end{equation}"),
  conf=0.8, definiendum="$\\textbf{q}$")
EQ("EP6", "F6", "$\\mathbf q=\\frac12\\hat M\\mathbf x$")
N("DP16", "definition", "Binomial read sampling",
  sp("In practice a specific position is covered by a limited number of reads,", "$z_{i}\\sim Binomial(r,q_i)$."),
  conf=0.8, definiendum="$\\textbf{z}$",
  statement_short="The rare-allele read counts $z_i$ out of $r$ reads are Binomial$(r,q_i)$.")
N("AssumP2", "assumption", "Gamma-distributed coverage",
  sp("The distribution of $r$ over different loci", "and apply it to all $k$ pools."),
  conf=0.85, statement_short="Per-locus read count $r\\sim\\Gamma(R/L,1)$ (following Prabhu & Pe'er), shared by all pools.")
N("DP17", "definition", "Sampling noise",
  sp("This binomial sampling process provides measurements", "regarded as {\\it sampling noise}."),
  conf=0.85, definiendum="sampling noise")
N("ProbP5", "problem", "Integer CS problem with sampling noise",
  sp("Therefore the {\\bf CS } problem formulation is given by", "< \\epsilon\n\\end{eqnarray}"),
  conf=0.85, statement_short="Minimize $\\|x\\|_1$ over $x\\in\\{0,1,2\\}^N$ s.t. $\\|\\frac12\\hat Mx - z/r\\|_2<\\epsilon$.")
EQ("EP7", "F7", "CS problem with sampling noise")
N("DP18", "definition", "Read error $e_r$",
  sp("All of these can be modeled using a single parameter $e_r$", "at a given locus."),
  conf=0.85, definiendum=["read error", "$e_r$"])
N("AssumP3", "assumption", "Errors always produce allele B",
  sp("The resulting base can be any of the other three different nucleotides,", "reducing the effective error rate.)"),
  conf=0.85)
N("ClP2", "claim", "B-read probability under read error",
  sp("The probability of observing $B$ at a certain read is therefore obtained", "e_r (1-\\frac{1}{2}\\hat{M}\\textbf{x})\n\\end{equation}"),
  conf=0.7, assumptions=["the read error"],
  conclusions=["\\textbf{q} = (1-e_r) \\frac{1}{2}\\hat{M}\\textbf{x} + e_r (1-\\frac{1}{2}\\hat{M}\\textbf{x})"],
  statement_short="With read error, B is observed with probability $(1-e_r)q+e_r(1-q)$.")
EQ("EP8", "F8", "Read-error convolution of $\\mathbf q$")
N("AssumP4", "assumption", "Known, lane-independent read error",
  sp("We assume that $e_r$ is known to the researcher,", "similar across different lanes."), conf=0.9)
N("ProbP6", "problem", "Read-error-corrected CS problem",
  sp("In this case, one can correct for the convolution", "the sensing matrix is $\\frac{1}{2} \\hat{M}$."),
  conf=0.85, statement_short="Invert the read-error convolution: measurements $y=(z/r-e_r)/(1-2e_r)$, sensing matrix $\\frac12\\hat M$, integer $\\ell_1$ minimization.")
EQ("EP9", "F9", "Read-error-corrected CS problem")
N("RP2", "remark", "Estimating an unknown read error",
  sp("If $e_r$ is unknown, one may still estimate it,", "from the overlapping pooled sequence data."),
  conf=0.7, statement_short="An unknown $e_r$ can be estimated from a control lane, or learned within the CS problem (Appendix A).")
N("DP19", "definition", "DNA preparation (DP) errors",
  sp("Finally we add to our model one more source of noise,", "({DP } errors.)"),
  conf=0.85, definiendum=["DNA preparation errors", "DP errors"])
N("DP20", "definition", "Actual measurement matrix $M'$",
  sp("While $M$ is our original zero-one Bernoulli matrix,", "to each non-zero entry."),
  conf=0.8, definiendum="$M'$")
N("DP21", "definition", "DP error matrix $D$",
  sp("Hence, the true mixture matrix is $M' \\equiv M+D$,", "\\end{array} \\right.\n\\end{eqnarray}"),
  conf=0.8, definiendum=["$D$", "$\\sigma$"],
  statement_short="$M'=M+D$, where $D$ adds $N(0,\\sigma^2)$ noise to each non-zero entry of $M$.")
EQ("EP10", "F10", "DP error distribution $d_{ij}$")
N("RP3", "remark", "DP errors perturb the sensing matrix",
  sp("The matrix $M'$ is unknown and we only have access to $M$,", "robust to such noise."),
  conf=0.7, statement_short="$M'$ is unknown, so the problem is unchanged; DP errors act as noise in the sensing matrix itself.")
N("DP22", "definition", "Expected reads per locus $E[r]=R/L$",
  sp("The expected number of reads from a certain locus is determined", "Gamma distribution with mean $\\frac{R}{L}$.)"),
  conf=0.85, definiendum=["$R$", "$L$"])
N("DP23", "definition", "Aligned reads per lane $R$",
  sp("$R$ is defined as the number of reads which were successfully", "regions of interest."), conf=0.9,
  definiendum="$R$")
N("AssumP5", "assumption", "Fixed lane throughput $R=4\\cdot10^6$",
  sp("Throughout this paper we have fixed $R$ to be $R = 4000000$", "in \\cite{gnirke2009solution}.)"), conf=0.8)
N("DP24", "definition", "Average coverage per individual per SNP $c$",
  sp("Another important and related parameter is the {\\it average coverage per individual per SNP}", "\\Big({\\equiv \\frac{E[r]}{N/2}}\\Big)\n\\end{equation}"),
  conf=0.9, definiendum=["average coverage per individual per SNP", "$c$"])
EQ("EP11", "F11", "Coverage $c$")
N("ClP3", "claim", "Per-individual coverage is approximately $c$",
  sp("When the total number of reads in a pool $r$ is given,", "is indeed approximately $c$."),
  conf=0.7, rigor="semi_formal",
  assumptions=["the total number of reads in a pool $r$ is given", "$N_{pooled} \\sim \\frac{N}{2}$ is the number of individuals in the pool"],
  conclusions=["the actual coverage obtained for each person in a pool has a distribution which is approximately $Binomial(r, 1/N_{pooled})$",
               "the average coverage per individual in a given pool is indeed approximately $c$"])
# ---------------- 2.4 Example ----------------
N("ExP1", "example", "Measured pool frequencies, N=3000, f=0.1%",
  sp("In order to visualize the effect of the three noise factors", "when pooling many individuals together."),
  conf=0.85, statement_short="3 carriers among 3000 over 100 pools: measured frequencies at coverage 27, 267, infinity with/without 1% read error; quantization lost and errors at low coverage.")
# ---------------- 2.5 Reconstruction ----------------
N("AP2", "algorithm", "GPSR reconstruction with integer post-processing",
  sp("We use the Gradient Projection for Sparse Reconstruction algorithm (GPSR)", "the sparsity of the vector\nobtained by GPSR."),
  conf=0.8, main=True,
  input=["the sensing matrix $M$ and the measurement vector $\\textbf{y}$"],
  output=["the vector ${\\textbf{x}}^{*s}$ which minimizes the error term $err_s$"],
  statement_short="Solve the penalized $\\ell_1$ problem with GPSR, then round the top-$s$ entries to $\\{0,1,2\\}$ and pick the $s$ minimizing the residual.")
N("ASP4", "algorithm_step", "Run GPSR",
  sp("We use the Gradient Projection for Sparse Reconstruction algorithm (GPSR)", "to solve the optimization problem~(\\ref{eq:CSopt_noise})."),
  conf=0.8, parent_id="AP2", step_order=1, subclass="call")
N("ProbP7", "problem", "GPSR penalized formulation",
  sp("GPSR is designed to solve a slightly different, but equivalent,", "maximal allowed error $\\epsilon$."),
  conf=0.85, statement_short="Unconstrained form: minimize residual norm plus $\\tau\\|x\\|_1$; $\\tau$ plays the role of $\\epsilon$.")
EQ("EP12", "F12", "GPSR objective")
N("ASP5", "algorithm_step", "Set the regularization $\\tau$",
  sp("We have chosen to adopt this scaling throughout this paper,", "did not alter results significantly."),
  conf=0.75, parent_id="AP2", step_order=2, subclass="initialize",
  statement_short="Set $\\tau=0.01\\|\\hat M^T y\\|_\\infty$.")
N("ASP6", "algorithm_step", "Round the top-$s$ values",
  sp("we rank all non-zero values obtained by GPSR,", "to get the vector ${\\textbf{x}}^{*s}$."),
  conf=0.75, parent_id="AP2", step_order=3, subclass="select")
N("ASP7", "algorithm_step", "Residual of the rounded vector",
  sp("We then compute an error term $err_s", "- \\textbf{y}||_2$."),
  conf=0.75, parent_id="AP2", step_order=4, subclass="compute")
N("ASP8", "algorithm_step", "Choose $s$ minimizing the residual",
  sp("Repeating this for different values of $s$ we select", "minimizes the error term $err_s$."),
  conf=0.75, parent_id="AP2", step_order=5, subclass="select")
# ---------------- 2.6 Barcodes ----------------
N("DP25", "definition", "Barcode",
  sp("A barcode is obtained by attaching to the DNA", "\\cite{hamady2008error}."),
  conf=0.85, origin="external", origin_citation="Hamady et al. 2008",
  definiendum="barcode", genus="unique DNA sequence of about $5$ additional nucleotides",
  differentia=["enables the unique identification of this sample"])
N("DP26", "definition", "Pooled-barcodes design",
  sp("In a pooled-barcodes design \\cite{Erlich:01},", "is tagged using a unique barcode."),
  conf=0.85, origin="external", origin_citation="Erlich et al. 2009", definiendum="pooled-barcodes design")
N("DP27", "definition", "Number of barcodes $n_{bar}$",
  sp("If $n_{bar}$ different\nbarcodes are available,", "(although not the specific individual.)"),
  conf=0.8, origin="external", origin_citation="Erlich et al. 2009", definiendum="$n_{bar}$")
N("AP3", "algorithm", "CS with barcoded pools",
  sp("We utilize barcodes by increasing the number of effective lanes", "$R/n_{bar}$ total reads per lane."),
  conf=0.8, main=True,
  input=["$k$ lanes and $n_{bar}$ barcodes"],
  statement_short="Treat $k$ lanes with $n_{bar}$ barcodes as $k n_{bar}$ pools of $R/n_{bar}$ reads each and solve the same CS problem.")
# ---------------- 2.7 Simulations ----------------
N("AP4", "algorithm", "Simulation protocol",
  sp("Various parameter ranges were simulated,", "reconstruct $\\textbf{x}$ from these measurements."),
  conf=0.7, statement_short="For each parameter set, 500 times: draw x, simulate pooled measurements under the noise model, reconstruct.")
N("ASP9", "algorithm_step", "Repeat 500 instances per parameter set",
  sp("Various parameter ranges were simulated,", "tested in $500$ instances."),
  conf=0.7, parent_id="AP4", step_order=1, subclass="loop")
N("ASP10", "algorithm_step", "Generate, measure, reconstruct",
  sp("In each simulation we have generated an input genotype vector", "reconstruct $\\textbf{x}$ from these measurements."),
  conf=0.7, parent_id="AP4", step_order=2, subclass="call")
N("DP28", "definition", "Reconstruction error",
  sp("Each entry $i$ for which $x_i$ is different from $x^*_i$", "($x_i \\neq 0 = x^*_i$)."),
  conf=0.9, definiendum="reconstruction error",
  differentia=["$x_i$ is different from $x^*_i$"])
N("DP29", "definition", "Successful reconstruction",
  sp("A certain value of the problem's parameters (such as number", "were reconstructed correctly."),
  conf=0.9, definiendum="successful",
  differentia=["at least $95\\%$ of its instances (i.e. $475$ out of $500$) had {\\it zero} reconstruction errors"])
N("ClP4", "claim", "Success criterion bounds the FDR",
  sp("In particular, this requirement guarantees that the False-Discovery-Rate", "will not exceed $0.05$."),
  conf=0.75, rigor="semi_formal", assumptions=["this requirement"],
  conclusions=["the False-Discovery-Rate of discovering rare-allele carriers will not exceed $0.05$"])
N("DP30", "definition", "$N_{max}$",
  sp("Performance is then measured in terms of $N_{max}$,", "values of the problem's parameters."),
  conf=0.9, definiendum="$N_{max}$")
# ---------------- 3 Results ----------------
N("ClP5", "claim", "Large groups with many lanes (f=0.1%)",
  sp("When the number of available lanes is large, we can successfully identify", "(Fig.~\\ref{fig:lanesAndNmax1Pro}(a,b).)"),
  conf=0.75, rigor="numerical", main=True,
  assumptions=["for $k=500$ lanes, and $L=10$ or $L=1$, respectively"],
  conclusions=["we can successfully identify the carriers in groups of up to $9000$ or $20000$ individuals"])
N("ClP6", "claim", "Few lanes suffice for few carriers (f=0.1%)",
  sp("In case the number of available lanes is small we can still identify", "for $L=1,10$, respectively."),
  conf=0.75, rigor="numerical",
  conclusions=["we can still identify a single carrier out of $1000$ individuals with merely $k=20$ lanes, for $L=1$ and $L=10$",
               "With $k=30,40$ lanes, we can identify $2$ or $3$ carriers in a group of $2000$ or $3000$, for $L=1,10$, respectively"])
N("ClP7", "claim", "$N_{max}$ decreases with the number of loci $L$",
  sp("As is evident from the four panels of Fig.~\\ref{fig:lanesAndNmax1Pro}, $N_{max}$", "increase in sampling noise."),
  conf=0.75, rigor="numerical",
  conclusions=["$N_{max}$ decreases as a function of $L$"])
N("ClP8", "claim", "$N_{max}$ grows almost linearly in $k$",
  sp("Increasing the number of lanes can overcome this under-sampling", "almost linearly with $k$ in most cases."),
  conf=0.7, rigor="numerical", conclusions=["the value of $N_{max}$ increases almost linearly with $k$ in most cases"])
N("DP31", "definition", "Efficiency score",
  sp("In order to quantify the advantage of applying {\\bf CS } we define an ``efficiency score''", "one-individual-per-lane approach."),
  conf=0.9, definiendum="efficiency score", statement_short="Efficiency score $= N_{max}/k$, the gain over one individual per lane.")
N("ClP9", "claim", "Efficiency score up to 70 (f=0.1%)",
  sp("When considering up to $L=100$ SNPs, the efficiency score", "as high as $70$."),
  conf=0.8, rigor="numerical", main=True, assumptions=["up to $L=100$ SNPs"],
  conclusions=["the efficiency score is around or above $10$, and in some cases is as high as $70$"])
N("ClP10", "claim", "Sharp success transition in coverage and lanes",
  sp("An improvement in performance may be achieved both by increasing", "to overcome sampling noise."),
  conf=0.65, rigor="numerical",
  conclusions=["The transition between ``successful'' and ``unsuccessful'' reconstruction is rather sharp."])
N("ClP11", "claim", "Performance for f=1% and f=2%",
  sp("The resulting $N_{max}$ is lower than for the case of $f=0.1\\%$", "compared to the naive approach."),
  conf=0.7, rigor="numerical", main=True,
  conclusions=["The resulting $N_{max}$ is lower than for the case of $f=0.1\\%$, although still much higher than in the naive approach",
               "is around $5$, still offering a considerable saving compared to the naive approach"])
N("ClP12", "claim", "Homozygous carriers handled by the same framework",
  sp("Our {\\bf CS } framework deals with this scenario in exactly the same way", "$2\\%$ heterozygous carriers."),
  conf=0.7, rigor="numerical")
N("ClP13", "claim", "Effect of sampling error",
  sp("Differences between the cases appear only when the number\nof SNPs is high", "and the infinite read case."),
  conf=0.7, rigor="numerical",
  conclusions=["In these cases $N_{max}$ is reduced by a factor of $2$ to $4$ with respect to an infinite coverage"])
N("ClP14", "claim", "Effect of read errors",
  sp("In the absence of read errors $N_{max}$ may be twice", "(see Eq.~(\\ref{eq:CSopt_noise}).)"),
  conf=0.7, rigor="numerical")
N("ClP15", "claim", "Robustness to DP errors",
  sp("In all cases we have studied the results are quite robust to {DP } errors", "by the {\\bf CS } reconstruction."),
  conf=0.75, rigor="numerical")
N("DP32", "definition", "Sparse ($\\sqrt N$) sensing matrix",
  sp("Here we shortly present the possibility of modifying $M$ into a {\\it sparse} sensing matrix", "few individuals per pool."),
  conf=0.65, definiendum="sparse sensing matrix")
N("ClP16", "claim", "Dense vs sparse pools",
  sp("For a small number of loci taken together ($L=1$ or $10$) the former dense", "sparse pools of size $\\sqrt{N}$."),
  conf=0.75, rigor="numerical")
N("OpenP1", "open_problem", "Optimal sparsity of the sensing matrix",
  sp("Further research is needed in order to determine", "for a given set of parameters."), conf=0.8)
N("ClP17", "claim", "Barcodes dramatically increase $N_{max}$",
  sp("Incorporating even a small number of barcodes into our {\\bf CS } framework", "a dramatic increase in $N_{max}$."),
  conf=0.8, rigor="numerical", main=True)
N("ClP18", "claim", "Diminishing returns of many barcodes",
  sp("As long as the coverage is kept high, it is still beneficial", "starts to diminish."),
  conf=0.7, rigor="numerical")
# ---------------- 4 Discussion ----------------
N("OpenP2", "open_problem", "Highest rare-allele frequency for CS",
  sp("The highest frequency possible for {\\bf CS } to perform well", "naive one-individual-per-lane approach is preferable."),
  conf=0.75)
N("ClP19", "claim", "CS beneficial up to about 5% frequency",
  sp("The simulations we have performed estimate this frequency", "the case of {\\it common} alleles."),
  conf=0.7, rigor="numerical")
N("OpenP3", "open_problem", "Joint optimization of pool design",
  sp("Therefore, one needs to optimize the pool design", "This issue remains for future study."), conf=0.75)
# ---------------- Appendix A ----------------
N("AssumP6", "assumption", "Unknown constant read error",
  sp("We assume that the read error $e_r$ is unknown to the researcher,", "constant across all\nlanes."), conf=0.9)
N("DP33", "definition", "Read-error convolution $\\mathbf z * e_r$",
  sp("We replace $\\textbf{z}$ in Eq.~(\\ref{eq:CSopt}) by the convolution:", "\\textbf{z} * e_r \\equiv \\textbf{z} + e_r - 2 \\textbf{z} e_r\n\\end{equation}"),
  conf=0.8, definiendum="$\\textbf{z} * e_r$")
EQ("EP13", "F13", "Convolution $\\mathbf z*e_r$")
N("DP34", "definition", "Auxiliary variable $x_{N+1}$",
  sp("We can approximate it by $x_{N+1}", "the mean value of the vector $\\textbf{z}$)."),
  conf=0.8, definiendum=["$x_{N+1}$", "$\\bar{z}$"])
N("ProbP8", "problem", "CS problem with learned read error",
  sp("We can now reformulate\nthe {\\bf CS } problem by adding one extra variable.", "with all its values set to $-1$."),
  conf=0.85, statement_short="Augment x with $x_{N+1}$ and M with a constant $-1$ column, then solve the $\\ell_1$ problem to learn $e_r$ jointly.")
EQ("EP14", "F14", "Augmented CS problem")

# ======================= edges =======================
# named / cited dependencies
E("DP3", "TP2", 0.85, "term"); E("DP4", "TP2", 0.9, "named")
E("DP3", "DP4", 0.8, "term")
E("TP4", "ProbP2", 0.8, "inferred")          # "Hence the problem is reformulated"
E("ProbP2", "ProbP3", 0.8, "inferred")       # noisy version of the l1 problem
E("TP5", "ProbP3", 0.6, "inferred")
E("DP1", "DP2", 0.85, "term"); E("DP1", "TP1", 0.8, "term"); E("DP2", "TP1", 0.8, "term")
E("DP2", "DP3", 0.8, "term"); E("DP2", "ProbP1", 0.8, "term"); E("DP2", "ProbP3", 0.75, "term")
E("DP5", "DP6", 0.8, "term"); E("DP6", "DP8", 0.85, "term"); E("DP7", "DP8", 0.85, "term")
E("DP8", "RP1", 0.8, "term")
E("DP2", "DP9", 0.75, "term"); E("DP5", "DP9", 0.7, "term")
E("DP9", "ClP1", 0.85, "term"); E("DP4", "ClP1", 0.9, "named"); E("TP2", "ClP1", 0.7, "inferred")
E("DP9", "AP1", 0.75, "term")
E("AP1", "DP10", 0.75, "inferred"); E("AP1", "DP11", 0.75, "inferred"); E("DP10", "DP11", 0.7, "term")
E("DP6", "ProbP4", 0.8, "term"); E("DP9", "ProbP4", 0.8, "term"); E("DP11", "ProbP4", 0.8, "term")
E("DP6", "DP12", 0.8, "term"); E("DP9", "DP13", 0.85, "term")
E("DP13", "DP14", 0.85, "term"); E("DP6", "DP14", 0.8, "term"); E("AssumP1", "DP14", 0.8, "inferred"); E("DP7", "DP14", 0.75, "term")
E("DP14", "DP15", 0.85, "term"); E("DP13", "DP15", 0.8, "term")
E("DP10", "DP16", 0.75, "term"); E("DP14", "DP16", 0.85, "term")
E("DP16", "AssumP2", 0.75, "term"); E("DP22", "AssumP2", 0.7, "term")
E("DP16", "DP17", 0.85, "inferred")
E("DP13", "ProbP5", 0.8, "term"); E("DP16", "ProbP5", 0.85, "term"); E("DP6", "ProbP5", 0.8, "term"); E("DP8", "ProbP5", 0.75, "term")
E("DP17", "ProbP5", 0.75, "inferred"); E("ProbP3", "ProbP5", 0.8, "named")
E("DP18", "AssumP3", 0.8, "term"); E("DP7", "AssumP3", 0.8, "term")
E("DP18", "ClP2", 0.85, "term"); E("AssumP3", "ClP2", 0.8, "inferred"); E("DP15", "ClP2", 0.8, "term")
E("DP18", "AssumP4", 0.8, "term")
E("ClP2", "ProbP6", 0.9, "named"); E("AssumP4", "ProbP6", 0.85, "inferred"); E("ProbP5", "ProbP6", 0.8, "inferred")
E("DP16", "ProbP6", 0.8, "term"); E("DP10", "ProbP6", 0.75, "term"); E("DP13", "ProbP6", 0.8, "term")
E("DP18", "RP2", 0.8, "term"); E("ProbP8", "RP2", 0.9, "named", mention=True)
E("DP19", "DP20", 0.8, "term"); E("DP9", "DP20", 0.75, "term")
E("DP20", "DP21", 0.85, "term"); E("DP19", "DP21", 0.8, "term")
E("DP20", "RP3", 0.85, "term"); E("DP19", "RP3", 0.8, "term")
E("DP22", "DP24", 0.85, "term"); E("DP23", "DP24", 0.75, "term"); E("DP5", "DP24", 0.7, "term")
E("DP23", "AssumP5", 0.85, "term")
E("DP24", "ClP3", 0.85, "term"); E("DP10", "ClP3", 0.75, "term"); E("DP16", "ClP3", 0.7, "inferred")
# example
for s in ("DP17", "DP18", "DP19", "DP24", "DP12"):
    E(s, "ExP1", 0.85, "named" if s in ("DP17", "DP18", "DP19") else "term", type="illustrates")
E("ProbP6", "ExP1", 0.8, "named", type="illustrates")
E("DP21", "ExP1", 0.75, "term")
# reconstruction algorithm
E("ProbP6", "AP2", 0.9, "named", type="resolves"); E("ProbP4", "AP2", 0.8, "inferred", type="resolves")
E("ProbP6", "ProbP7", 0.85, "named"); E("ProbP7", "ASP4", 0.8, "inferred")
E("DP12", "ASP6", 0.7, "term"); E("ASP6", "ASP7", 0.8, "inferred"); E("ASP7", "ASP8", 0.85, "inferred")
E("ASP4", "ASP6", 0.8, "inferred"); E("DP8", "AP2", 0.75, "term")
# barcodes
E("DP25", "DP26", 0.85, "term"); E("DP26", "DP27", 0.8, "term"); E("DP25", "DP27", 0.75, "term")
E("DP27", "AP3", 0.85, "term"); E("DP23", "AP3", 0.75, "term"); E("AP2", "AP3", 0.7, "inferred")
# simulations
E("ProbP6", "AP4", 0.7, "inferred"); E("AP2", "AP4", 0.7, "inferred"); E("DP21", "AP4", 0.65, "inferred"); E("AssumP2", "AP4", 0.65, "inferred")
E("DP28", "DP29", 0.9, "term"); E("DP29", "ClP4", 0.85, "named"); E("DP28", "ClP4", 0.7, "term")
E("DP29", "DP30", 0.9, "term"); E("DP5", "DP30", 0.7, "term")
# results
for c in ("ClP5", "ClP6", "ClP7", "ClP8", "ClP11", "ClP13", "ClP14", "ClP16", "ClP17"):
    E("DP30", c, 0.85, "term")
for c in ("ClP5", "ClP6", "ClP8", "ClP9", "ClP10", "ClP11", "ClP12", "ClP13", "ClP14", "ClP15", "ClP16", "ClP17", "ClP18", "ClP19"):
    E("AP2", c, 0.7, "inferred")
E("DP22", "ClP5", 0.7, "term"); E("DP22", "ClP6", 0.7, "term"); E("DP22", "ClP7", 0.75, "term")
E("DP17", "ClP7", 0.8, "term"); E("ClP7", "ClP8", 0.75, "inferred")
E("DP12", "ClP5", 0.75, "term"); E("DP12", "ClP11", 0.75, "term"); E("DP12", "ClP13", 0.7, "term")
E("DP31", "ClP9", 0.9, "term"); E("DP31", "ClP11", 0.9, "term"); E("DP22", "ClP9", 0.7, "term")
E("DP24", "ClP10", 0.8, "term"); E("DP17", "ClP10", 0.75, "term"); E("DP29", "ClP10", 0.75, "term")
E("DP8", "ClP12", 0.75, "term"); E("DP17", "ClP13", 0.8, "term"); E("DP24", "ClP13", 0.8, "term")
E("DP18", "ClP14", 0.85, "term"); E("DP22", "ClP14", 0.7, "term"); E("DP19", "ClP15", 0.85, "term")
E("DP32", "ClP16", 0.85, "term"); E("DP9", "ClP16", 0.75, "term"); E("DP22", "ClP16", 0.7, "term")
E("DP32", "OpenP1", 0.75, "term"); E("ClP16", "OpenP1", 0.65, "inferred", mention=True)
E("AP3", "ClP17", 0.85, "inferred"); E("DP27", "ClP17", 0.75, "term")
E("AP3", "ClP18", 0.8, "inferred"); E("DP17", "ClP18", 0.75, "term"); E("DP27", "ClP18", 0.7, "term")
E("DP12", "OpenP2", 0.7, "inferred"); E("OpenP2", "ClP19", 0.65, "inferred", mention=True)
E("OpenP1", "OpenP3", 0.6, "inferred", mention=True); E("DP32", "OpenP3", 0.65, "inferred")
# appendix
E("DP18", "AssumP6", 0.85, "term")
E("DP16", "DP33", 0.8, "term"); E("DP18", "DP33", 0.8, "term")
E("DP33", "DP34", 0.8, "inferred"); E("DP34", "ProbP8", 0.9, "term"); E("DP9", "ProbP8", 0.75, "term")
E("DP13", "ProbP8", 0.75, "term"); E("AssumP6", "ProbP8", 0.8, "inferred"); E("DP6", "ProbP8", 0.75, "term")
# term uses flagged by finalize
for t in ("ClP1", "ProbP4", "DP13", "ProbP6", "RP3", "DP32", "ClP16", "OpenP1", "DP20"):
    E("DP2", t, 0.75, "term")
E("DP4", "DP20", 0.8, "term"); E("DP6", "ExP1", 0.75, "term"); E("DP6", "AP4", 0.75, "term")
E("DP8", "DP28", 0.8, "term"); E("DP9", "DP21", 0.8, "term"); E("DP11", "ProbP6", 0.8, "term")
E("DP18", "DP29", 0.7, "term")
for t in ("ProbP6", "AP2", "ProbP7"):
    E("DP18", t, 0.85, "term")
for t in ("AP3", "ClP17", "ClP18"):
    E("DP25", t, 0.85, "term")

nonformal = sum(1 for n in nodes if "rigor" in n)
graph = {"metadata": {
    "title": "Rare-Allele Detection Using Compressed Se(que)nsing",
    "arxiv_id": "0909.0400",
    "authors": ["Noam Shental", "Amnon Amir", "Or Zuk"], "year": 2009,
    "annotator": "agent-extraction", "model": "claude-opus-5-5", "effort": "default",
    "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3", "extraction_date": "2026-11-05",
    "rigor_nonformal_count": nonformal,
    "paper_style": ["computational", "modeling"],
    "extraction_notes": [],
    "extraction_comment": ""},
    "nodes": nodes, "edges": edges}
NOTES = [
 {"category": "unexpected_construct", "nodes": ["ClP5", "ClP9", "ClP11", "ClP13", "ClP14", "ClP15", "ClP16", "ClP17"],
  "note": "There are no theorem environments; the results are simulation findings read off figures. Each finding the text states is a claim with rigor numerical; figure captions (which repeat or add numbers) are not nodes."},
 {"category": "rule_conflict", "nodes": ["ProbP1", "ProbP2", "ProbP3", "ProbP5", "ProbP6", "ProbP7", "ProbP8"],
  "note": "The optimization problems are numbered equations; per the rules the equations stay equation nodes, and each is nested in a prose problem node spanning the sentence that introduces it."},
 {"category": "source_problem", "nodes": ["DP33", "DP34", "ProbP8"],
  "note": "Appendix A applies the read-error convolution to the count vector z rather than to the frequencies z/r, reuses $M'$ (earlier M+D) for the augmented matrix, and never defines z'; with the 1/2 prefactor the -1 column contributes $-x_{N+1}/2$, not $-x_{N+1}$."},
 {"category": "source_problem", "nodes": ["AssumP2", "DP22"],
  "note": "R and L are used in the Gamma coverage assumption before they are defined in the 'Targeted region length' paragraph; the edge DP22->AssumP2 is backward."},
 {"category": "type_uncertain", "nodes": ["DP4", "ClP2"],
  "note": "DP4 is introduced as an example of a UUP matrix but defines the term used later, so definition; ClP2 (Eq. 8) could be a model definition of q, kept as a claim since the text says it is 'therefore obtained' from the read-error assumption."},
 {"category": "not_extracted", "nodes": [],
  "note": "The abstract's headline (4 carriers among over 4000 individuals with about 10 lanes and 10 barcodes) is stated nowhere in the body, so it is not a node; the introduction's account of prior designs (Prabhu & Pe'er, Erlich et al.) and the discussion's future directions (adaptive pooling, LD, CNVs) are prose without stated results."},
 {"category": "boundary_uncertain", "nodes": ["AP1", "ProbP4", "AP4"],
  "note": "The pooled-sequencing protocol, the informal statement of the identification goal and the simulation protocol are prose procedures; their spans and step splits are judgment."},
]
graph["metadata"]["extraction_notes"] = NOTES

if __name__ == "__main__":
    exec(open(__file__.replace("build.py", "notes.py")).read()) if False else None
    report = finalize(graph, tex)
    for w in report["warnings"]:
        print("WARN", w)
    print("ERRORS", report["errors"])
    assert not report["errors"], report["errors"]
    print({k: (len(v) if isinstance(v, list) else v) for k, v in report.items()})
    json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
    print("wrote", OUT, len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
