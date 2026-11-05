"""Build the SARANGA v7 graph of arXiv 1007.3424 (Amir & Zuk 2010,
Bacterial Community Reconstruction Using A Single Sequencing Reaction).
Node choices are made by reading; this script only slices the chosen spans."""
import json, sys, re
sys.path.insert(0, "/mnt/c/Code/Github/Saranga/src")
from extraction_finalize import finalize
from latex_facts import read_tex, extract_facts

TEX = "/mnt/c/Code/Github/Saranga/corpus/orzuk/1007_3424/arxiv_src/BCS_arxiv.tex"
OUT = "/mnt/c/Code/Github/Saranga/corpus/orzuk/1007_3424/1007_3424.json"
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
    if not cur:
        return ""
    return f"{cur['number']} {cur['title']}" if cur["number"] else cur["title"]


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


def STEPS(parent, specs, conf=0.7):
    """specs: list of (id, name, start, end, subclass, short)"""
    for k, (sid, name, a, b, sub, short) in enumerate(specs, 1):
        st = sp(a, b)
        if st.startswith("\\item"):
            st = st[len("\\item"):]
        N(sid, "algorithm_step", name, st, conf=conf, parent_id=parent, step_order=k,
          subclass=sub, statement_short=short)


def E(s, t, conf=0.8, basis="term", type="uses", **kw):
    e = {"source": s, "target": t, "type": type, "confidence": conf, "basis": basis}
    e.update(kw)
    edges.append(e)


STD = dict(origin="external", origin_citation="standard (uncited)")

# ================= 1 Introduction =================
N("ProbP1", "problem", "Compressed sensing problem (underdetermined linear system)",
  sp("The classical problem in {\\bf CS } is solving an under-determined linear system of equations",
     "number of equations $k$."),
  conf=0.85, origin="external", origin_citation="Candes, Romberg & Tao 2006; Donoho 2006",
  statement_short="Classical CS: solve $\\mathcal{A}\\mathbf{v}=\\mathbf{b}$ with $N$ unknowns far exceeding the $k$ equations.")
EQ("EP1", "F1", "Classical CS linear system $\\mathcal{A}\\mathbf{v}=\\mathbf{b}$")
N("AssumP1", "assumption", "Sparsity assumption in compressed sensing",
  sp("Here one uses an additional sparsity assumption on the solution", "for some $s \\ll N$."),
  conf=0.8, **STD,
  statement_short="CS assumes the solution has at most $s\\ll N$ non-zero entries.")
N("TP1", "theorem", "Compressed sensing recovery with O(s log(N/s)) measurements",
  sp("According to the {\\bf CS } theory,", "needed for general solution of a linear system."),
  conf=0.85, origin="external", origin_citation="Candes, Romberg & Tao 2006; Donoho 2006; Candes & Tao 2005",
  assumptions=["the matrix $\\mathcal{A}$ satisfy certain conditions, most notably the RIP condition \\cite{candes2005stable,candes2005decoding}"],
  conclusions=["one can find the sparsest solution uniquely by using only a logarithmic number of equations, $k = O(s \\log(N/s))$"],
  also_stated_at=[clean(sp("Furthermore, it is known that with very high probability a unique and accurate reconstruction",
                           "assumption \\cite{Candes:01,Donoho:01}."))],
  statement_short="Under RIP, the sparsest solution is recovered uniquely from $k=O(s\\log(N/s))$ equations instead of $N$.")
N("AP1", "algorithm", "Bacterial Compressed Sensing algorithm (BCS)",
  sp("The proposed Bacterial Compressed", "and their predicted frequencies."),
  conf=0.85, main=True,
  input=["a database of known 16S rRNA sequences", "the measured Sanger-sequence of the unknown mixture"],
  output=["the sparse set of bacteria present in the mixture and their predicted frequencies"],
  statement_short="BCS: from a 16S rRNA database and one mixed Sanger chromatogram, return the sparse set of species and their frequencies.")

# ================= 2.1 The Bacterial Community Reconstruction Problem =================
N("ProbP2", "problem", "Bacterial Community Reconstruction Problem",
  sp("In the Bacterial Community Reconstruction Problem we are given", "are available in the database."),
  conf=0.9,
  statement_short="Given a mixture of unknown composition and a database of one gene's sequences, recover which species are present and their frequencies.")
N("AssumP3", "assumption", "Linearity of the mixed Sanger chromatogram",
  sp("Since Sanger sequencing proceeds independently for each DNA strand", "abundance of each species in the mixture."),
  conf=0.75,
  statement_short="The mixture chromatogram is a linear combination of the constituent sequences, weighted by abundance.")
N("DP1", "definition", "Number of database species $N$",
  sp("Let $N$ be the number of known bacterial species", "present in our database."), conf=0.85,
  definiendum="$N$")
N("DP2", "definition", "Species frequency vector $\\mathbf{v}$",
  sp("Each bacterial population is characterized by", "of frequencies of the different species."), conf=0.85,
  definiendum="${\\textbf v}$", genus="vector", differentia=["of frequencies of the different species"])
N("DP3", "definition", "Number of species present $s$ and the $\\ell_0$ norm",
  sp("Denote by $s$ the number of species present", "\\sum_i 1_{\\{v_i \\neq 0\\}}$."), conf=0.85,
  definiendum=["$s$", "$\\|.\\|_{\\ell 0}$"],
  statement_short="$s=\\|\\mathbf{v}\\|_{\\ell 0}$, the number of non-zero entries of $\\mathbf{v}$.")
N("AssumP2", "assumption", "Sparsity of bacterial communities",
  sp("While the total number of known species $N$ is usually very large", "${\\textbf v}$ is a sparse vector."),
  conf=0.8,
  also_stated_at=[clean(sp("The sparseness assumption in our scenario is obtained by noting", "of all other species is essentially zero.")),
                  clean(sp("The crucial assumption we make in order to cope with the insufficiency of information",
                           "only a small number of species are present in the mixture."))],
  statement_short="A community contains a small subset of the $N$ known species, so $s\\ll N$ and $\\mathbf{v}$ is sparse.")
N("DP4", "definition", "Database sequence matrix $S$",
  sp("The database sequences are denoted by a matrix $S$", "($i=1,..,N, j=1,..,k$)."), conf=0.85,
  definiendum="$S$")
N("DP5", "definition", "Position-specific score matrix (PSSM) of the mixture",
  sp("We represent the results of the mixture Sanger sequencing", "with $a_j,c_j,g_j,t_j \\geq 0$."), conf=0.85,
  definiendum=["Position-specific-Score-Matrix (PSSM)", "$P$", "${\\textbf p}_j$"],
  genus="$4 \\times k$ Position-specific-Score-Matrix",
  statement_short="The mixed Sanger read of length $k$ is a $4\\times k$ PSSM whose column $j$ holds the observed nucleotide frequencies $(a_j,c_j,g_j,t_j)$.")
EQ("EP2", "F2", "PSSM $P$ with rows $\\mathbf{a},\\mathbf{c},\\mathbf{g},\\mathbf{t}$")
N("ExP1", "example", "A zero-frequency position excludes species",
  sp("For example, if at a certain position $j$, the frequency $a_j$", "are not present in the mixture."), conf=0.8,
  statement_short="If $a_j=0$ (no noise), every species with A at position $j$ is absent.")
N("ClP1", "claim", "Per-position linear constraint on the mixture",
  sp("More generally, the frequency of each nucleotide at a given position $j$", "and similarly for $'\\!C','\\!G','\\!T'$."),
  conf=0.75,
  assumptions=["at a given position $j$"],
  conclusions=["the frequency of each nucleotide at a given position $j$ gives a linear constraint on the mixture"],
  statement_short="Each nucleotide frequency at position $j$ equals the total frequency of species carrying that nucleotide there.")
EQ("EP3", "F3", "Linear constraint $\\sum_i v_i 1_{\\{S_{ij}=A\\}}=a_j$")
N("DP6", "definition", "Mixture matrices $A, C, G, T$",
  sp("Define the $k \\times N$ mixture matrix $A$", "and similarly for the nucleotides $'\\!{C}','\\!{G}','\\!{T}'$."), conf=0.9,
  definiendum=["mixture matrix", "$A$", "$C$", "$G$", "$T$"], genus="$k \\times N$ mixture matrix",
  statement_short="$A$ is the binary $k\\times N$ indicator of nucleotide A in the database sequences; likewise $C,G,T$.")
EQ("EP4", "F4", "Mixture matrix entries $A_{ij}$")
N("ClP2", "claim", "Sequencing constraints as a linear system",
  sp("The constraints given by the sequencing reaction can therefore be expressed as:", "T\\textbf{v}=\\textbf{t} \\label{eq:LinConstraints}\n\\end{equation}"),
  conf=0.75, assumptions=[], conclusions=["A\\textbf{v}=\\textbf{a}, C\\textbf{v}=\\textbf{c}, G\\textbf{v}=\\textbf{g}, T\\textbf{v}=\\textbf{t}"],
  statement_short="The sequencing data give the four linear systems $A\\mathbf{v}=\\mathbf{a}$, ..., $T\\mathbf{v}=\\mathbf{t}$.")
EQ("EP5", "F5", "BCS linear constraints $A\\mathbf{v}=\\mathbf{a},\\dots,T\\mathbf{v}=\\mathbf{t}$")
N("RP1", "remark", "The reconstruction system is underdetermined",
  sp("Hence, from a single sequencing reaction of length $k$ we derive", "we are not guaranteed a single solution."), conf=0.75,
  statement_short="A read gives $4k\\sim 2000$-$4000$ equations, far fewer than $N$, so the system is underdetermined.")

# ================= 2.2 Mapping the Problem to Compressed Sensing =================
N("ProbP3", "problem", "$\\ell_0$ sparse reconstruction problem",
  sp("We seek a sparse solution for the set of equations", "\\label{eq:L0Min}\n\\end{equation}"), conf=0.85,
  statement_short="Find the sparsest $\\mathbf{v}$ satisfying the four nucleotide constraint systems.")
EQ("EP6", "F6", "$\\ell_0$ minimization (2.5)")
N("ClP3", "claim", "BCS reduces to the classical CS problem",
  sp("The formulation above can be easily seen as a {\\bf CS } problem", "eq. (\\ref{eq:cs_classic})."),
  conf=0.75, rigor="semi_formal",
  assumptions=["one can in principle construct a big 'sensing' matrix $\\mathcal{A}_{4k\\times N}$ as a simple concatenation of the matrices A,C,G,T, and similarly a measurements vector $\\textbf{b}$ as a concatenation of the measurements $\\textbf{a}, \\textbf{c}, \\textbf{g}$ and $\\textbf{t}$"],
  conclusions=["problem (\\ref{eq:L0Min}) is in fact reduced to the classic {\\bf CS } problem \\cite{Candes:01} of finding the sparsest solution for eq. (\\ref{eq:cs_classic})"],
  statement_short="Stacking $A,C,G,T$ into a $4k\\times N$ sensing matrix turns (2.5) into the classical sparsest-solution CS problem.")
N("TP2", "theorem", "NP-hardness of $\\ell_0$ minimization",
  sp("From a practical point of view, problem (\\ref{eq:L0Min}) is known to be in general", "not computationally feasible."),
  conf=0.85, origin="external", origin_citation="Candes & Tao 2005 (Decoding by linear programming)",
  assumptions=[], conclusions=["problem (\\ref{eq:L0Min}) is known to be in general NP-Hard \\cite{candes2005error}"],
  statement_short="Exact $\\ell_0$ minimization is NP-hard in general.")
N("TP3", "theorem", "$\\ell_1$ convex relaxation recovers the sparse solution (basis pursuit)",
  sp("However, a remarkable breakthrough of the {\\bf CS } theory shows", "can be obtained in polynomial time."),
  conf=0.85, origin="external", origin_citation="Candes, Romberg & Tao 2006; Donoho 2006; Tropp 2006",
  assumptions=["under certain conditions on the mixture matrix and the number of measurements (see below)"],
  conclusions=["the sparse solution can be recovered uniquely by solving a convex relaxation of the problem, which is obtained by replacing the $\\ell 0$ norm with the ''closest'' convex $\\ell p$ norm, namely the $\\ell 1$ norm",
               "which is a convex optimization problem whose solution can be obtained in polynomial time"],
  statement_short="Under suitable conditions the sparse solution is recovered uniquely by the polynomial-time $\\ell_1$ minimization (2.6).")
EQ("EP7", "F7", "$\\ell_1$ minimization (2.6)")
N("TP4", "theorem", "Robustness of compressed sensing to measurement noise",
  sp("Fortunately, the {\\bf CS } paradigm is known", "\\cite{candes2005stable,candes2007dantzig}."),
  conf=0.8, origin="external", origin_citation="Candes, Romberg & Tao 2006 (stable recovery); Candes & Tao 2007 (Dantzig selector)",
  assumptions=[], conclusions=["the {\\bf CS } paradigm is known to be robust to measurement noise"])
N("ProbP4", "problem", "Noise-tolerant BCS problem ($\\ell_2$ fit plus $\\ell_1$ penalty)",
  sp("One can cope with noise by enabling a", "\\label{eq:GPSR}\n\\end{equation}"), conf=0.85,
  statement_short="Minimize half the squared $\\ell_2$ misfit of the four constraint systems plus $\\tau\\|\\mathbf{v}\\|_1$.")
EQ("EP8", "F8", "$\\ell_2$-$\\ell_1$ objective (2.7)")
N("RP2", "remark", "Role of $\\tau$ and relation of (2.7) to (2.6)",
  sp("This problem represents a more general form of eq. (\\ref{eq:L1Min})", "the problem is reduced back to eq. (\\ref{eq:L1Min}))."),
  conf=0.8,
  statement_short="(2.7) generalizes (2.6) and stays convex; larger $\\tau$ gives sparser, worse-fitting solutions, and small $\\tau$ recovers (2.6).")
N("AP2", "algorithm", "BCS solver: GPSR on problem (2.7)",
  sp("Many algorithms which enable an efficient solution of problem (\\ref{eq:GPSR})", "for the reconstruction of the experimental mixture."),
  conf=0.75,
  input=["problem (\\ref{eq:GPSR})"],
  statement_short="Solve (2.7) with the GPSR algorithm, $\\tau=10$ for simulated and $\\tau=100$ for experimental mixtures.")
STEPS("AP2", [
    ("ASP1", "Call GPSR", "Many algorithms which enable an efficient solution of problem (\\ref{eq:GPSR})",
     "described in \\cite{GPSR:01}.", "call", "Solve (2.7) with GPSR."),
    ("ASP2", "Set $\\tau$", "The error tolerance parameter was set to $\\tau=10$",
     "for the reconstruction of the experimental mixture.", "initialize", "$\\tau=10$ (simulation), $\\tau=100$ (experiment)."),
])
N("ClP4", "claim", "Robustness of BCS to the choice of $\\tau$",
  sp("These values achieved a rather sparse solution in most cases", "was not\nfollowed in this study."),
  conf=0.7, rigor="numerical",
  statement_short="The chosen $\\tau$ gives sparse, sensitive solutions and performance is robust to $\\tau$.")
N("DP7", "definition", "Restricted Isometry Property (RIP) / Uniform Uncertainty Principle (UUP)",
  sp("The most well-known condition for successful reconstruction is the 'Robust Isometry Property'",
     "for sparse vectors $v$ with sparsity $s$."),
  conf=0.85, origin="external", origin_citation="Candes, Romberg & Tao 2006; Candes & Tao 2005",
  definiendum=["Robust Isometry Property (RIP)", "Uniform Uncertainty Principle (UUP)"],
  genus="condition for successful reconstruction",
  differentia=["any subset of $2s$ columns of the matrix $\\mathcal{A}$ is 'almost orthogonal'"],
  statement_short="RIP: every set of $2s$ columns of the sensing matrix is almost orthogonal, so the matrix is invertible on $s$-sparse vectors.")
N("ClP5", "claim", "A few thousand measurements suffice for a few dozen species",
  sp("In our case the number of measurements $4k$ is on order of a few thousands", "in the range of a few dozens."),
  conf=0.7, rigor="heuristic",
  assumptions=["the number of measurements $4k$ is on order of a few thousands"],
  conclusions=["accurate reconstruction is possible, at least when the sparsity $s$ in the range of a few dozens"])
N("RP3", "remark", "The BCS mixing matrix is predetermined and coherent",
  sp("One important\ndifference between classical {\\bf CS } and our problem", "This point is addressed in the Results section."),
  conf=0.75,
  statement_short="Unlike designed CS matrices, the BCS mixing matrix is fixed by the database and has near-parallel columns for related species.")

# ================= 3.1 Simulation Results =================
N("AP7", "algorithm", "Simulated mixture reconstruction protocol",
  sp("In order to asses the performance of the proposed {\\textbf {BCS} } reconstruction algorithm, random subsets",
     "(see Methods section and Figure \\ref{fig:MethodScheme})."),
  conf=0.75,
  output=["the frequencies of database sequences predicted to participate in the mixture"],
  statement_short="Draw random species subsets with uniform random frequencies, compute the mixed PSSM, and reconstruct it with BCS.")
STEPS("AP7", [
    ("ASP3", "Select random species", "In order to asses the performance of the proposed {\\textbf {BCS} } reconstruction algorithm, random subsets",
     "\\cite{desantis2006greengenes} were selected.", "select", "Pick a random subset of database species."),
    ("ASP4", "Draw frequencies and compute PSSM", "Within these subsets, the relative frequencies of each species were drawn",
     "frequency distribution, are shown later).", "compute", "Uniform random frequencies, normalized; compute the mixed PSSM."),
    ("ASP5", "Run BCS", "This PSSM was then used as the input for the {\\textbf {BCS} } algorithm",
     "(see Methods section and Figure \\ref{fig:MethodScheme}).", "call", "Reconstruct the frequencies with BCS."),
])
N("ClP6", "claim", "Sample simulated reconstruction of 10 species",
  sp("The {\\textbf {BCS} } algorithm successfully identified all of the species present", "with a total fraction of $0.04$ false positives."),
  conf=0.7, rigor="numerical",
  statement_short="On a 10-species mixture with 500 bp, BCS finds all species plus small false positives (max 0.01, total 0.04).")
N("DP8", "definition", "Reconstruction RMSE",
  sp("RMSE is the Root-Mean Squared-Error between the original", "(v_i-v^*_i)^2\\Big)^{1/2}$."), conf=0.9,
  definiendum="RMSE", genus="Root-Mean Squared-Error between the original mixture vector and the reconstructed vector",
  statement_short="RMSE $=\\|\\mathbf{v}-\\mathbf{v}^*\\|_2$.")
N("DP9", "definition", "Recall and precision of a reconstruction",
  sp("As another measure, we have recorded the {\\it recall}", "original\nmixture vector $\\textbf{v}$."), conf=0.9,
  definiendum=["recall", "precision"],
  statement_short="Recall: fraction of true species recovered; precision: fraction of reconstructed species that are true.")
N("DP10", "definition", "Minimal frequency threshold for calling a species present",
  sp("Since the predicted frequency is a continuous variable, whereas the recall/precision", "before calculating the\nrecall/precision scores."),
  conf=0.8, definiendum="minimal threshold for calling a species present")

# 3.1.1 Coherence
N("RP4", "remark", "Insertions and deletions decorrelate orthologous sequences",
  sp("In our case this cannot be achieved, as we were given the sequences", "to a number typically much lower)."),
  conf=0.7,
  statement_short="The database columns cannot be designed, but indels shift similar sequences out of phase and lower their correlation.")
N("DP11", "definition", "Mutual coherence of a mixing matrix",
  sp("It has been previously shown \\cite{ben-haim_near-oracle_2009,tropp_just_2006}", "two columns of the mixing\nmatrix."),
  conf=0.85, origin="external", origin_citation="Ben-Haim, Eldar & Elad 2009; Tropp 2006",
  definiendum="mutual coherence", genus="maximal coherence (inner product) between two columns of the mixing matrix")
N("ClP7", "claim", "Coherence distribution of 16S rRNA database columns",
  sp("The distribution of coherence values for random pairs of database species", "maximal correlation value\nof $0.998$."),
  conf=0.75, rigor="numerical",
  statement_short="Pairwise coherences centre at 0.25, but 0.5% of pairs exceed 0.8 and the maximum is 0.998.")
N("RP5", "remark", "High coherence limits worst-case reconstruction only",
  sp("This high mutual coherence value places a limit on the reconstruction performance", "of nucleotides read in the sequencing)."),
  conf=0.7, rigor="heuristic",
  statement_short="Near-duplicate sequences cannot be told apart, but they are usually close relatives and most pairs are near-random, so few measurements suffice.")

# 3.1.2 Sequence length
N("ClP8", "claim", "About 300 nucleotides suffice for 10 species",
  sp("It is shown in Figure \\ref{fig:SeqNum}.A that using longer sequence lengths", "of 10 sequences."),
  conf=0.75, rigor="numerical",
  statement_short="Longer reads give more constraints and accuracy; about 300 nt reconstruct a 10-species mixture accurately.")
N("DP12", "definition", "Random nucleotide sequence database",
  sp("In order to asses the effect of the dependence between the database sequences", "for 'A','C','G' or 'T')."),
  conf=0.75, definiendum="database of random nucleotide sequences",
  differentia=["each sequence was composed of i.i.d. nucleotides with $0.25$ probability for 'A','C','G' or 'T'"])
N("ClP9", "claim", "Coherence of random sequence databases",
  sp("Since sequences were independently\ndrawn, the pairwise correlation values", "(data not shown)."),
  conf=0.7, rigor="numerical")
N("ClP10", "claim", "Random sequences need about 100 nucleotides",
  sp("Using a mixing matrix derived from these random sequences", "database using $300$ nucleotides."),
  conf=0.75, rigor="numerical",
  statement_short="With an i.i.d. random database, about 100 nt match the RMSE that the 16S database reaches with 300 nt.")

# 3.1.3 Number of species
N("ClP11", "claim", "Reconstruction of 100-species mixtures",
  sp("Even on a mixture\nof $100$ species, the reconstruction showed", "$0.75$ and a precision of $0.85$."),
  conf=0.75, rigor="numerical",
  statement_short="At $k=500$, 100-species mixtures give RMSE below 0.04, and recall 0.75 / precision 0.85 at threshold 0.0025.")
N("ClP12", "claim", "16S rRNA sequences suffice for mixtures of tens of species",
  sp("Therefore, while the sequence database did not perform as well as random sequences", "with a small percent of errors."),
  conf=0.75, rigor="numerical", main=True,
  statement_short="Although worse than random sequences, 16S rRNA varies enough to reconstruct mixtures of tens of species.")
N("DP13", "definition", "Power-law species frequency distribution",
  sp("We therefore tested the performance of the {\\textbf {BCS} } reconstruction\non a similar power-law", "with with $v_i \\sim i^{-1}$."),
  conf=0.7, definiendum="power-law distribution of species frequencies")
N("ClP13", "claim", "Power-law mixtures: RMSE similar to uniform",
  sp("Performance on such a power-law mixture is similar", "in terms of the RMSE."),
  conf=0.7, rigor="numerical")
N("ClP14", "claim", "Power-law mixtures: recall/precision up to 50 species",
  sp("The recall/precision of the {\\textbf {BCS} } algorithm on such mixtures", "due to the long tail of low frequency species."),
  conf=0.7, rigor="numerical",
  statement_short="On power-law mixtures recall/precision match the uniform case up to 50 species and degrade beyond, due to the long tail.")

# 3.1.4 Noise
N("AssumP4", "assumption", "Additive Gaussian measurement-noise model",
  sp("Measurement noise was modeled\nas additive i.i.d. Gaussian noise", "PSSM element in eq. (\\ref{eq:PSSM})."),
  conf=0.8, statement_short="Each PSSM entry gets i.i.d. $N(0,\\sigma^2)$ additive noise.")
N("ClP15", "claim", "Reconstruction degrades slowly with noise",
  sp("The reconstruction performance slowly degrades", "random sequence database."),
  conf=0.7, rigor="numerical")
N("ClP16", "claim", "Reconstruction at the experimental noise level $\\sigma=0.15$",
  sp("Using a noise standard deviation of $\\sigma=0.15$", "attained under realistic noise levels."),
  conf=0.75, rigor="numerical",
  statement_short="With $\\sigma=0.15$ and 500 nt, a 40-species mixture gives RMSE 0.07 and recall and precision about 0.7 at threshold 0.006.")
N("ClP17", "claim", "Graceful degradation under realistic noise",
  sp("To conclude, we have observed that the addition of noise leads to a graceful degradation", "with realistic noise levels."),
  conf=0.75, rigor="numerical", main=True)

# ================= 3.2 Experimental mixture =================
N("ClP18", "claim", "Local-sequence correction reduces peak prediction error",
  sp("The distribution of relative peak height and position errors following local sequence correction", "for peak height and position respectively."),
  conf=0.7, rigor="numerical",
  statement_short="6-mer context correction reduces the SD of peak height and position errors from 0.26 and 1.3 to 0.15 and 0.75.")
N("ClP19", "claim", "Predicted mixture chromatogram accuracy on bins 125-700",
  sp("On the region of bins 125-700 the prediction\nshows high accuracy", "with an average root square error of 0.08."),
  conf=0.7, rigor="numerical")
N("ClP20", "claim", "Reconstruction of a five-species experimental mixture",
  sp("The algorithm successfully identifies three of the five bacteria", "is mistakenly identified as \\textit{Salmonella enterica}."),
  conf=0.75, rigor="numerical", main=True,
  statement_short="From one Sanger read of a 5-strain mixture BCS finds 3 strains, one more to genus level, and confuses E. coli with S. enterica.")
N("ClP21", "claim", "E. coli recovered once its sequence is in the database",
  sp("While \\textit{Escherichia coli}\nand \\textit{Salmonella enterica} show a sequence difference", "rather than \\textit{Salmonella enterica} in the mixture."),
  conf=0.7, rigor="numerical",
  statement_short="E. coli was removed as a near-duplicate of S. enterica in the used region; re-adding it lets BCS identify E. coli correctly.")

# ================= 4 Discussion =================
N("ClP22", "claim", "One read suffices even for databases of millions of sequences",
  sp("Essentially, the amount of information needed for identifying the species", "even when the database contains millions of different sequences."),
  conf=0.7, rigor="heuristic",
  assumptions=["as long as the number of the species present in the mixture is kept constant"],
  conclusions=["the amount of information needed for identifying the species present in the mixture is logarithmic in the database size",
               "a single sequencing reaction with hundreds of bases contains in principle a very large amount of information and should suffice for unique reconstruction even when the database contains millions of different sequences"])
N("RP6", "remark", "Non-negativity of frequencies is not enforced",
  sp("In the current implementation, the fact that bacteria have only non-negative frequencies", "more efficient and accurate reconstruction."),
  conf=0.75,
  statement_short="(2.7) does not enforce $\\mathbf{v}\\ge 0$; adding it is known to simplify recovery and is expected to help.")
N("RP7", "remark", "Extension to several sequencing reactions",
  sp("The proposed method can easily be extended to more than one sequencing reaction per mixture", "in the presence of experimental noise."),
  conf=0.75)

# ================= A Chromatogram Preprocessing =================
N("DP14", "definition", "Chromatogram trace vectors $\\mathfrak{a},\\mathfrak{c},\\mathfrak{g},\\mathfrak{t}$",
  sp("The input to the chromatogram preprocessing is the measured chromatogram", "by one pixel in the chromatogram image."),
  conf=0.85, definiendum=["$\\mathfrak{a}, \\mathfrak{c},\\mathfrak{g}, \\mathfrak{t}$", "$\\mathfrak{a}_p$"],
  statement_short="The measured chromatogram is four trace vectors; $\\mathfrak{a}_p$ is the A-signal intensity at pixel $p$.")
N("AP3", "algorithm", "Chromatogram Preprocessing",
  sp("\\noindent {\\bf Algorithm:} Chromatogram Preprocessing", "and similarly for $c_i$,$g_i$,$t_i$."),
  conf=0.85,
  input=["$(\\mathfrak{a}, \\mathfrak{c},\\mathfrak{g}, \\mathfrak{t})$ - four fluorescent trace vectors"],
  output=["$P = (a, c, g, t)^t$ - a PSSM representing nucleotide frequencies"],
  statement_short="Turn a mixed chromatogram into a PSSM: normalize amplitude by a 50 bp running total, then sum 12-pixel bins and take square roots.")
STEPS("AP3", [
    ("ASP6", "Normalize amplitude", "\\item Normalize the chromatogram amplitude:", "and similarly for $\\mathfrak{c}_p$,$\\mathfrak{g}_p$ and $\\mathfrak{t}_p$.",
     "compute", "Divide each trace by the total intensity in a 50 bp window."),
    ("ASP7", "Bin and square-root", "\\item bin into constant sized bins, average bin values", "and similarly for $c_i$,$g_i$,$t_i$.",
     "compute", "Sum 12-pixel bins and take the square root to get PSSM column $i$."),
], conf=0.8)
EQ("EP9", "F9", "Amplitude normalization (A.1)")
EQ("EP10", "F10", "Square-root binning (A.2)")

# ================= B Database Preprocessing =================
N("AP4", "algorithm", "Database Preprocessing scheme",
  sp("The database preprocessing therefore contains two steps:", "of the measure and predicted chromatograms."),
  conf=0.8,
  input=["a training set $S'$ of known sequences and their chromatograms", "a set $S$ of $N$ sequences"],
  output=["predicted PSSMs"],
  statement_short="Learn 6-mer peak height/position tables from training chromatograms, predict a PSSM for every database sequence, then align with the measurement.")
STEPS("AP4", [
    ("ASP8", "Compute local-sequence statistics", "\\item A preliminary step: Compute local-sequence adjusted chromatogram statistics.",
     "for different local-sequence contexts.", "compute", "Estimate the peak height and position tables $H,P$ from a training set."),
    ("ASP9", "Generate predicted PSSMs", "\\item Database PSSMs Generation step: Generate a database of predicted PSSMs.",
     "This step is illustrated in Figure \\ref{fig:PreprocessingScheme}.B.", "compute", "Predict a chromatogram, then a PSSM, for each database sequence."),
    ("ASP10", "Align measured and predicted chromatograms", "After performing these two steps, and additional alignment step is required",
     "of the measure and predicted chromatograms.", "other", "Align the start of measured and predicted chromatograms."),
])
N("DP15", "definition", "Training peak positions $p_{i,j}$ and heights $h_{i,j}$",
  sp("We use $p_{i,j}$ and $h_{i,j}$\nto denote the position and height", "distinguishable from the three\nother peaks)."),
  conf=0.85, definiendum=["$p_{i,j}$", "$h_{i,j}$"])
N("AssumP5", "assumption", "Local sequence context is the preceding 5 nucleotides (6-mer)",
  sp("We have modeled the local sequence context by looking at the\n$5$ nucleotides preceding", "each representing a possible nucleotide and the $5$ nucleotides\npreceding it."),
  conf=0.75,
  statement_short="Peak height and position depend on the nucleotide and its 5 predecessors, a 6-mer among $4^6=4096$.")
N("DP16", "definition", "Peak height statistic $H(\\alpha)$",
  sp("More formally, for a given kmer $\\alpha = (\\alpha_1,..,\\alpha_6)$", "\\label{eq:peak_height}\n\\end{equation}"),
  conf=0.85, definiendum=["$H(\\alpha)$", "$P(\\alpha)$"],
  statement_short="$H(\\alpha)$ is the average training peak height at positions whose 6-mer context is $\\alpha$.")
EQ("EP11", "F11", "Peak height statistic (B.1)")
N("DP17", "definition", "Relative peak-peak distance $d_{i,j}$",
  sp("\\noindent For peak position $P(\\alpha)$, we first computed", "p_{i,j}-p_{i,j-1}}.\n\\end{equation}"),
  conf=0.85, definiendum="$d_{i,j}$")
EQ("EP12", "F12", "Relative peak-peak distance (B.2)")
N("DP18", "definition", "Peak position statistic $P(\\alpha)$",
  sp("\\noindent Then, we measured the average relative peak-peak distance", "\\label{eq:peak_position}\n\\end{equation}"),
  conf=0.85, definiendum="$P(\\alpha)$",
  statement_short="$P(\\alpha)$ is the average relative peak-peak distance at positions with 6-mer context $\\alpha$.")
EQ("EP13", "F13", "Peak position statistic (B.3)")
N("ClP23", "claim", "Context-dependent variability of peak height and position",
  sp("While the average height and position were $1$ (as was ensured by our normalizations)", "(see Figure \\ref{fig:PosHeightDist})."),
  conf=0.7, rigor="numerical",
  statement_short="Across 6-mers, height ranges about 0.5-1.3 and position 0.8-1.2 around a mean of 1.")
N("DP19", "definition", "Position drift parameter $\\beta$",
  sp("An additional sequence-independent non-linearity in the peak position", "(see next section in eq. (\\ref{eq:peak_params_estimation}) )."),
  conf=0.75, definiendum="$\\beta$",
  statement_short="A linear fit in position adds $\\beta=0.00036$ to the peak-peak distance per position.")

N("AP5", "algorithm", "Database PSSM generation (predicted chromatograms)",
  sp("The input for this step is the database sequence matrix $S$", "with one PSSM for each sequence in $S$."),
  conf=0.8,
  input=["the database sequence matrix $S$"],
  output=["a set of PSSMs $(a, c, g, t)^t$, one for each sequence $S_i$ in the database"],
  statement_short="For each database sequence, predict peak heights and positions from 6-mer tables, sum Gaussian peaks into traces, then bin and square-root into a PSSM.")
STEPS("AP5", [
    ("ASP11", "Estimate peak heights and positions", "For every nucleotide in the database, we estimated",
     "per position as we move further along the sequence.", "compute", "Height $H(L_{i,j})$; position advances by $P(L_{i,j})+\\beta j$."),
    ("ASP12", "Model each peak as a Gaussian", "In order to generate a chromatogram trace for a given sequence, each peak was modeled",
     "\\label{eq:gaussian_peak}\n\\end{equation}", "compute", "Each nucleotide contributes a Gaussian peak at its predicted position and height."),
    ("ASP13", "Fix peak width", "The widths of the chromatogram Gaussian peaks were approximated", "by setting $c=0.4$.",
     "initialize", "Constant width $c=0.4$."),
    ("ASP14", "Sum peaks into trace vectors", "A chromatogram was generated for each sequence by summing",
     "and similarly for the other three nucleotides.", "compute", "Evaluate on a 1/12 grid and sum each base's peaks into its trace."),
    ("ASP15", "Bin and square-root", "The resulting predicted chromatograms were binned using a constant bin size",
     "with one PSSM for each sequence in $S$.", "compute", "Bin and square-root as in (A.2) to get one PSSM per sequence."),
])
EQ("EP14", "F14", "Predicted peak height and position (B.4)")
EQ("EP15", "F15", "Gaussian peak function (B.5)")
EQ("EP16", "F16", "Predicted trace vector (B.6)")

N("ProbP5", "problem", "Alignment of predicted and measured chromatograms",
  sp("We are therefore faced with the problem of correctly aligning", "the bin positions of the predicted chromatograms."),
  conf=0.75)
N("AP6", "algorithm", "Offset selection by minimal reconstruction distance",
  sp("This was solved by trying the {\\textbf {BCS} } reconstruction for different initial bin offsets", "predicted chromatogram based the reconstructed species frequencies."),
  conf=0.75,
  statement_short="Run BCS for each initial bin offset and keep the offset whose reconstruction best matches the measured chromatogram.")
STEPS("AP6", [
    ("ASP16", "Try offsets and select the best", "This was solved by trying the {\\textbf {BCS} } reconstruction for different initial bin offsets",
     "(see Figure \\ref{fig:ChromatogramOffset}.A).", "select", "Run BCS per offset; pick the lowest root square distance."),
    ("ASP17", "Compute reconstruction distance", "This reconstruction root square distance is calculated as the difference",
     "predicted chromatogram based the reconstructed species frequencies.", "compute", "Distance between measured and reconstruction-predicted chromatograms."),
])
N("ClP24", "claim", "Offset criterion validated with the known composition",
  sp("To verify the validity of this criterion, we also\ncompared", "Both methods obtained an identical offset, which was used in the reconstruction."),
  conf=0.7, rigor="numerical",
  statement_short="Using the known composition gives the same offset as the reconstruction-based criterion.")

# ================= edges =================
# 1 Introduction / CS background
E("AssumP1", "TP1", 0.8, "inferred")
E("ProbP1", "TP1", 0.75, "inferred")
E("DP7", "TP1", 0.8, "term")            # "the RIP condition"
E("ProbP1", "AssumP1", 0.7, "term")      # solution vectors v, N
E("ProbP2", "AP1", 0.85, "inferred", type="resolves")
E("AssumP2", "AP1", 0.75, "inferred")
E("AP2", "AP1", 0.7, "inferred")         # the CS step of BCS
E("AP4", "AP1", 0.7, "inferred")
E("AP3", "AP1", 0.7, "inferred")
# 2.1
E("DP1", "DP2", 0.8); E("DP2", "DP3", 0.8)
E("DP1", "AssumP2", 0.8); E("DP2", "AssumP2", 0.8); E("DP3", "AssumP2", 0.85)
E("DP1", "DP4", 0.75)
E("DP5", "ExP1", 0.8, type="illustrates"); E("DP4", "ExP1", 0.75)
E("AssumP3", "ExP1", 0.7, "inferred")
E("ClP1", "ExP1", 0.75, "inferred", type="illustrates")
E("AssumP3", "ClP1", 0.8, "inferred"); E("DP2", "ClP1", 0.8); E("DP4", "ClP1", 0.8); E("DP5", "ClP1", 0.8)
E("DP4", "DP6", 0.85); E("DP1", "DP6", 0.75)
E("ClP1", "ClP2", 0.8, "inferred"); E("DP6", "ClP2", 0.85); E("DP5", "ClP2", 0.8); E("DP2", "ClP2", 0.8)
E("ClP2", "RP1", 0.8, "inferred"); E("DP1", "RP1", 0.75)
# 2.2
E("AssumP2", "ProbP3", 0.8, "inferred"); E("DP6", "ProbP3", 0.85); E("DP3", "ProbP3", 0.8); E("DP5", "ProbP3", 0.8)
E("ProbP2", "ProbP3", 0.75, "inferred")
E("ProbP1", "ClP3", 0.85, "inferred"); E("DP6", "ClP3", 0.8)
E("ProbP1", "TP2", 0.6, "inferred")
E("TP2", "TP3", 0.65, "inferred", mention=True)  # "However, ..." contrast
E("DP7", "TP3", 0.7, "inferred")       # "conditions on the mixture matrix (see below)"
E("ProbP3", "TP3", 0.8, "inferred"); E("DP6", "TP3", 0.7)
E("EP7", "ProbP4", 0.8, "named", type="generalizes")  # "a more general form of eq. (2.6)"
E("TP4", "ProbP4", 0.75, "inferred"); E("DP6", "ProbP4", 0.85); E("DP5", "ProbP4", 0.8)
E("ProbP4", "AP2", 0.9, "inferred", type="resolves")
E("AP2", "ClP4", 0.8, "inferred")
E("TP1", "ClP5", 0.85, "named")        # "these results suggest"
E("RP1", "ClP5", 0.65, "inferred")
E("DP7", "RP3", 0.65, "inferred"); E("DP4", "RP3", 0.8)
# 3.1
E("AP1", "AP7", 0.85, "named"); E("DP5", "AP7", 0.8)
E("AP7", "ClP6", 0.8, "inferred"); E("AP1", "ClP6", 0.8, "named")
E("DP2", "DP8", 0.8)
E("DP2", "DP9", 0.75)
E("DP9", "DP10", 0.85)
E("DP7", "RP4", 0.8, "named"); E("RP3", "RP4", 0.7, "inferred")
E("DP11", "ClP7", 0.85); E("DP6", "ClP7", 0.7)
E("ClP7", "RP5", 0.85, "named"); E("DP11", "RP5", 0.85)
E("AP7", "ClP8", 0.8, "inferred"); E("DP8", "ClP8", 0.85)
E("DP11", "ClP9", 0.8); E("DP12", "ClP9", 0.85)
E("DP12", "ClP10", 0.85); E("DP8", "ClP10", 0.8); E("ClP8", "ClP10", 0.8, "named")
E("DP8", "ClP11", 0.85); E("DP9", "ClP11", 0.85); E("DP10", "ClP11", 0.8)
E("ClP11", "ClP12", 0.85, "inferred"); E("ClP10", "ClP12", 0.8, "inferred")
E("DP2", "DP13", 0.7)
E("DP13", "ClP13", 0.85); E("DP8", "ClP13", 0.85)
E("DP13", "ClP14", 0.85); E("DP9", "ClP14", 0.85)
E("DP5", "AssumP4", 0.8)
E("AssumP4", "ClP15", 0.85, "inferred"); E("DP12", "ClP15", 0.8); E("ProbP4", "ClP15", 0.7, "inferred")
E("AssumP4", "ClP16", 0.85); E("DP8", "ClP16", 0.85); E("DP9", "ClP16", 0.85); E("DP10", "ClP16", 0.8)
E("ClP15", "ClP17", 0.8, "inferred"); E("ClP16", "ClP17", 0.85, "inferred")
# 3.2
E("AP5", "ClP18", 0.7, "inferred"); E("AssumP5", "ClP18", 0.75, "inferred")
E("AP5", "ClP19", 0.7, "inferred")
E("AP1", "ClP20", 0.85, "named"); E("AP3", "ClP20", 0.7, "inferred"); E("AP4", "ClP20", 0.7, "inferred")
E("ClP19", "ClP20", 0.7, "inferred")
E("ClP20", "ClP21", 0.8, "inferred"); E("AP1", "ClP21", 0.8, "named")
# 4
E("TP1", "ClP22", 0.85, "inferred"); E("AssumP2", "ClP22", 0.7, "inferred")
E("ProbP4", "RP6", 0.7, "inferred")
E("ClP2", "RP7", 0.7, "inferred"); E("AP1", "RP7", 0.75, "inferred")
# A
E("DP14", "AP3", 0.9); E("DP5", "AP3", 0.8)
# B
E("AP3", "AP4", 0.6, "inferred")
E("DP16", "ASP8", 0.8); E("DP18", "ASP8", 0.8)
E("AP5", "ASP9", 0.85, "inferred")
E("AP6", "ASP10", 0.85, "inferred")
E("DP14", "AP4", 0.8)
E("AssumP5", "DP16", 0.85); E("DP15", "DP16", 0.9)
E("DP15", "DP17", 0.9)
E("DP17", "DP18", 0.9); E("AssumP5", "DP18", 0.85)
E("DP16", "ClP23", 0.85); E("DP18", "ClP23", 0.85)
E("DP15", "DP19", 0.6, "inferred")
edges.append({"source": "EP14", "target": "DP19", "type": "uses", "confidence": 0.95, "mention": True})  # "(see next section in eq. ...)"
E("DP19", "AP5", 0.85); E("DP16", "AP5", 0.9); E("DP18", "AP5", 0.9); E("AssumP5", "AP5", 0.8)
E("DP4", "AP5", 0.85); E("DP14", "AP5", 0.85); E("AP3", "AP5", 0.8, "named")  # "in similar to the chromatogram preprocessing step"
E("ProbP5", "AP6", 0.9, "inferred", type="resolves")
E("AP1", "AP6", 0.85, "named")
E("AP6", "ClP24", 0.85, "inferred")

nonformal = sum(1 for n in nodes if "rigor" in n)
NOTES = [
 {"category": "unexpected_construct", "nodes": ["ClP6", "ClP8", "ClP11", "ClP16", "ClP20"],
  "note": "There are no theorem or proof environments; the paper's own results are simulation and wet-lab findings read off figures. Each finding the text states is a claim with rigor numerical; figure captions are not nodes."},
 {"category": "type_uncertain", "nodes": ["TP3", "ProbP4", "ClP2"],
  "note": "The l1 relaxation (2.6) appears inside the sentence citing the basis-pursuit recovery result, so that sentence is an external theorem with the equation nested, not a problem node; (2.7), which the paper solves, is a problem. ClP2 could be a definition of the constraint system; kept a claim since it is derived ('can therefore be expressed')."},
 {"category": "boundary_uncertain", "nodes": ["AP1", "AP2"],
  "note": "BCS is never given as one procedure: the introduction states its input/output (AP1, no steps: a single-sentence specification) and Section 2.2 its solver (GPSR on (2.7)); preprocessing (AP3-AP6) is in the appendix. They are linked by uses edges into AP1."},
 {"category": "source_problem", "nodes": ["DP7"],
  "note": "RIP is expanded as 'Robust Isometry Property'; the standard name (Candes-Tao) is Restricted Isometry Property."},
 {"category": "source_problem", "nodes": ["DP6", "DP4"],
  "note": "S is N x k with S_ij the j-th nucleotide of species i, but A is called k x N with A_ij = 1 iff S_ij = 'A'; for Av = a to make sense the entry should be A_ji (indices transposed)."},
 {"category": "source_problem", "nodes": ["DP17", "EP12", "ClP23"],
  "note": "(B.2) uses j both as free index and as summation index and lacks parentheses; as written d_ij sums to 1 over a read, so its mean is 1/(k-1), not 1 as the text says the normalization ensures (a factor k-1 seems missing)."},
 {"category": "source_problem", "nodes": ["DP16", "DP18", "AP5", "DP5"],
  "note": "Symbols are overloaded: P is both the PSSM (2.1) and the peak-position table P(alpha); a_ij and c denote peak height and Gaussian width in Appendix B while a_j, c_j are PSSM entries."},
 {"category": "source_problem", "nodes": ["ClP13", "ClP19", "DP8", "DP9"],
  "note": "Text says power-law vs uniform are the 'blue and green lines' of Fig. 4B but the caption makes the uniform 16S curve black (green is random sequences); the usable region is bins 125-700 in the text but 100-700 in the Fig. 7 caption; RMSE is defined as the plain l2 norm (no mean); the Fig. 4C caption calls precision the 'fraction of incorrect sequences identified'."},
 {"category": "not_extracted", "nodes": [],
  "note": "Database curation (2.3), the wet-lab protocol (2.4.1), the prose overview of preprocessing (2.4.2, detailed in the appendix) and the introduction's survey of prior methods carry no stated mathematics and give no nodes."},
]
graph = {"metadata": {
    "title": "Bacterial Community Reconstruction Using A Single Sequencing Reaction",
    "arxiv_id": "1007.3424",
    "authors": ["Amnon Amir", "Or Zuk"], "year": 2010,
    "annotator": "agent-extraction", "model": "claude-opus-5-5", "effort": "default",
    "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3", "extraction_date": "2026-11-05",
    "rigor_nonformal_count": nonformal,
    "paper_style": ["modeling", "computational"],
    "extraction_notes": NOTES,
    "extraction_comment": ""},
    "nodes": nodes, "edges": edges}

if __name__ == "__main__":
    report = finalize(graph, tex)
    for w in report["warnings"]:
        print("WARN", w)
    print("ERRORS", report["errors"])
    assert not report["errors"], report["errors"]
    print({k: (len(v) if isinstance(v, list) else v) for k, v in report.items()})
    json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
    print("wrote", OUT, len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
