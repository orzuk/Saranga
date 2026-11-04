"""Build the v7 extraction of Viazovska 2016 (arXiv 1603.04246).

Every node's type and span below was chosen by reading the paper; this script
only slices the chosen spans out of the prepared source, numbers the ids and
runs the finishing step.
"""
import json, re, sys
from collections import defaultdict
REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize
from latex_facts import read_tex

HERE = "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/181b34d2-e85e-4795-8729-4e70122e8101/scratchpad/via"
TEX = REPO + "/corpus/case_studies/viazovska_2016/paper.tex"
OUT = REPO + "/corpus/silver/opus-5.5__v7_cases/viazovska_2016.json"
facts = json.load(open(HERE + "/facts.json"))
SRC = facts["source"]
FACT = {f["id"]: f for f in facts["facts"]}
SEC = {s["id"]: f"{s['number']} {s['title']}" if s["number"] else s["title"] for s in facts["sections"]}
SECSTART = sorted((s["start"], SEC[s["id"]]) for s in facts["sections"] if s["inside"] is None)


def clean(t):
    t = re.sub(r"\\label\s*\{[^}]*\}", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def find(a, after=0):
    i = SRC.find(a, after)
    assert i >= 0, ("anchor not found", a)
    return i


def span(a, b, after=0):
    """from the start of anchor a to the end of anchor b (first b after a)"""
    i = find(a, after)
    j = find(b, i) + len(b)
    return i, j


def section_of(pos):
    s = None
    for st, name in SECSTART:
        if st <= pos:
            s = name
    return s


NODES = []      # dicts with key 'k' (my key), 'pos'


def node(k, typ, name, sp=None, fact=None, **kw):
    if fact:
        f = FACT[fact]
        sp = (f["start"], f["end"])
    i, j = sp
    n = dict(k=k, type=typ, name=name, statement=clean(SRC[i:j]), pos=i, end=j,
             section=section_of(i), **kw)
    n.setdefault("origin", "paper")
    n.setdefault("confidence", 1.0 if fact else 0.75)
    NODES.append(n)
    return n


def ext(cit="standard (uncited)"):
    return dict(origin="external", origin_citation=cit)


def sub(text, within):
    """a verbatim sub-span (for assumptions/conclusions): must occur in the node"""
    assert re.sub(r"\s+", "", text) in re.sub(r"\s+", "", within["statement"]), text
    return text


EQ = {}   # fact id -> key


def eq(fid, name, **kw):
    k = "eq_" + fid
    EQ[fid] = k
    node(k, "equation", name, fact=fid, **kw)
    return k


Z = "Zagier 2008 (The 1-2-3 of Modular Forms)"
# ---------------------------------------------------------------- Section 1
node("d_vol", "definition", "Euclidean distance and Lebesgue measure on R^d",
     span("More precisely, let $\\mathbb{R}^d$", "measure $\\mathrm{Vol}(\\cdot)$."),
     definiendum=["$\\|\\cdot\\|$", "$\\mathrm{Vol}(\\cdot)$"], confidence=0.8, **ext())
node("d_ball", "definition", "Open ball B_d(x,r)",
     span("For $x\\in\\mathbb{R}^d$ and $r\\in\\mathbb{R}_{>0}$ we denote", "and radius $r$."),
     definiendum="$B_d(x,r)$", genus="open ball in $\\mathbb{R}^d$", confidence=0.85, **ext())
node("d_packing", "definition", "Sphere packing",
     span("Let $X\\subset \\mathbb{R}^d$ be a discrete set", "is a \\emph{sphere packing}."),
     definiendum="sphere packing", genus="union", differentia=["$\\|x-y\\|\\geq2$ for any distinct $x,y\\in X$"],
     confidence=0.9, **ext())
node("d_lattice_packing", "definition", "Lattice sphere packing",
     span("If $X$ is a lattice in $\\mathbb{R}^d$ then", "\\emph{lattice sphere packing}."),
     definiendum="lattice sphere packing", confidence=0.9, **ext())
node("d_finite_density", "definition", "Finite density of a packing",
     span("The \\emph{finite density} of a packing", "\\quad r>0.$$"),
     definiendum="finite density", statement_short="$\\Delta_{\\mathcal{P}}(r)$: fraction of the ball $B_d(0,r)$ covered by the packing.",
     confidence=0.9, **ext())
node("d_density", "definition", "Density of a packing",
     span("We define the \\emph{density} of a packing", "\\Delta_{\\mathcal{P}}(r). $$"),
     definiendum="density", statement_short="Density $\\Delta_{\\mathcal{P}}$ = limsup of the finite density as $r\\to\\infty$.",
     confidence=0.9, **ext())
node("d_constant", "definition", "Sphere packing constant Delta_d",
     span("The number be want to know is the supremum", "called the \\emph{sphere packing constant}."),
     definiendum=["sphere packing constant", "$\\Delta_d$"], confidence=0.9, **ext())
node("c_dim1", "claim", "Delta_1 = 1", span("Trivially, in dimension~$1$", "$\\Delta_1=1$."),
     confidence=0.7, assumptions=[], conclusions=["$\\Delta_1=1$"], **ext())
node("t_thue", "theorem", "Optimality of the hexagonal packing in dimension 2 (Thue; Fejes Toth)",
     span("It has long been known  that a best packing in dimension $2$", "touching six others."),
     confidence=0.75, assumptions=[], conclusions=["a best packing in dimension $2$ is the familiar hexagonal lattice packing"],
     **ext("Thue 1910; Fejes Toth 1943"))
node("cj_kepler", "conjecture", "Kepler conjecture",
     span("Johannes Kepler conjectured in his essay", "greater than~$\\frac{\\pi}{\\sqrt{18}}$."),
     confidence=0.85, assumptions=[], conclusions=["no arrangement of equally sized spheres filling space has density greater than~$\\frac{\\pi}{\\sqrt{18}}$"],
     **ext("Kepler 1611"))
node("t_hales", "theorem", "Kepler conjecture (Hales)",
     span("The Kepler conjecture was famously proven by T. Hales", "\\approx0.74048$."),
     confidence=0.85, assumptions=[], conclusions=["$\\Delta_3=\\frac{\\pi}{\\sqrt{18}}\\approx0.74048$"], **ext("Hales 2005"))
node("op_dims", "open_problem", "Exact sphere packing constants in dimensions above 3",
     span("Before now, the exact values of the sphere packing constants", "have been unknown."),
     confidence=0.7, **ext())
node("r_close", "remark", "Cohn-Elkies upper bounds nearly meet lower bounds in dimensions 8 and 24",
     span("Surprisingly enough, these upper bounds", "dimensions~$d=8$ and~$d=24$."),
     confidence=0.7, **ext("Cohn & Elkies 2003"))
node("c_value", "claim", "Delta_8 = pi^4/384",
     span("The main result of this paper is the proof that", "$E_8$-lattice sphere packing."),
     confidence=0.8, main=True, assumptions=[], conclusions=["$$\\Delta_8=\\frac{\\pi^4}{384}\\approx 0.25367.$$"],
     statement_short="The sphere packing constant in dimension 8 equals $\\pi^4/384$, the density of the $E_8$-lattice packing.")
node("d_e8", "definition", "E8 lattice",
     span("Recall that the $E_8$-lattice $\\Lambda_8", "(\\mathrm{mod\\;2})\\}.$$"),
     definiendum=["$E_8$-lattice", "$\\Lambda_8$"], confidence=0.9, **ext())
node("t_e8_unique", "theorem", "Characterisation of E8 as the unique even unimodular lattice of rank 8",
     span("$\\Lambda_8$ is the unique up to isometry", "lattice of rank 8."),
     confidence=0.7, assumptions=[], conclusions=["$\\Lambda_8$ is the unique up to isometry positive-definite, even, unimodular lattice of rank 8"], **ext())
node("c_mindist", "claim", "Minimal distance in E8 is sqrt 2",
     span("The minimal distance between two points in $\\Lambda_8$", "is $\\sqrt{2}$."),
     confidence=0.75, assumptions=[], conclusions=["The minimal distance between two points in $\\Lambda_8$ is $\\sqrt{2}$"], **ext())
node("d_e8_packing", "definition", "E8-lattice sphere packing",
     span("The $E_8$-lattice sphere packing is the packing of unit balls", "\\frac{1}{\\sqrt{2}}\\Lambda_8.$"),
     definiendum="$E_8$-lattice sphere packing", genus="packing of unit balls",
     differentia=["with centers at $\\frac{1}{\\sqrt{2}}\\Lambda_8.$"], confidence=0.9, **ext())
node("t_main", "theorem", "Optimality of the E8 sphere packing in dimension 8", fact="F1", main=True,
     assumptions=[], conclusions=["No packing of unit balls in Euclidean space $\\mathbb{R}^8$ has density greater than that of the $E_8$-lattice packing."],
     also_stated_at=["In this paper we prove that no packing of unit balls in Euclidean space $\\mathbb{R}^8$ has density greater than that of the $E_8$-lattice packing."],
     tags=["sphere_packing", "optimality", "bound"])
node("c_unique", "claim", "E8 is the unique periodic packing of maximal density",
     span("Furthermore, our proof of Theorem~1 combined", "unique periodic packing of maximal density."),
     confidence=0.8, rigor="semi_formal", tags=["uniqueness"],
     assumptions=[], conclusions=["the $E_8$-lattice sphere packing is the unique periodic packing of maximal density"])

# ---------------------------------------------------------------- Section 2
node("op_lp", "open_problem", "How far linear programming bounds are from sharp",
     span("However, in general linear programming bounds are not sharp", "errors of such bounds can be."),
     confidence=0.7, **ext())
node("t_brv", "theorem", "Asymptotic optimality of LP bounds for spherical designs",
     span("It is known \\cite{BRV} that the linear programming bounds", "up to a constant depending on $d$."),
     confidence=0.75, assumptions=[], conclusions=["the linear programming bounds for the minimal number of points in an equal weight quadrature formula on the sphere $S^d$ are asymptotically optimal up to a constant depending on $d$"],
     **ext("Bondarenko, Radchenko, Viazovska 2013"))
node("t_ce_numeric", "theorem", "Cohn-Elkies numerical upper bound for Delta_8",
     span("For example, their upper bound for $\\Delta_8$ was only", "density of the $E_8$ sphere packing."),
     confidence=0.7, assumptions=[], conclusions=["their upper bound for $\\Delta_8$ was only $1.000001$ times greater than the lower bound"],
     **ext("Cohn & Elkies 2003"))
node("d_fourier", "definition", "Fourier transform",
     span("The \\emph{Fourier transform} of an $L^1$~function", "standard scalar product in $\\mathbb{R}^d$."),
     definiendum=["Fourier transform", "$\\mathcal{F}(f)$", "$\\widehat{f}$"], confidence=0.9, **ext())
node("d_schwartz", "definition", "Schwartz function",
     span("A $C^\\infty$~function $f:\\mathbb{R}^d\\to\\mathbb{C}$ is called", "all partial derivatives of $f$."),
     definiendum="Schwartz function", genus="$C^\\infty$~function $f:\\mathbb{R}^d\\to\\mathbb{C}$",
     differentia=["it tends to zero as $\\|x\\|\\to\\infty$ faster then any inverse power of $\\|x\\|$", "the same holds for all partial derivatives of $f$"],
     confidence=0.9, **ext())
node("d_schwartz_space", "definition", "Schwartz space",
     span("The set of all Schwartz functions is called", "\\emph{Schwartz space}."), definiendum="Schwartz space",
     confidence=0.9, **ext())
node("c_fourier_auto", "claim", "Fourier transform is an automorphism of the Schwartz space",
     span("The Fourier transform is an automorphism", "of this space."), confidence=0.75,
     assumptions=[], conclusions=["The Fourier transform is an automorphism of this space"], **ext())
node("d_admissible", "definition", "Admissible function",
     span("We say that a function $f:\\mathbb{R}^d\\to\\mathbb{C}$ is \\emph{admissible}", "(1+|x|)^{-d-\\delta}$."),
     definiendum="admissible", genus="function $f:\\mathbb{R}^d\\to\\mathbb{C}$", confidence=0.9, **ext("Cohn & Elkies 2003"))
node("t_ce", "theorem", "Cohn-Elkies linear programming bound", fact="F2", tags=["bound", "linear_programming"],
     assumptions=["$f:\\mathbb{R}^d\\to\\mathbb{R}$ is an admissible function, is not identically zero", "\\begin{equation}f(x)\\leq 0\\mbox{ for } \\|x\\|\\geq 1\\end{equation}",
                  "\\begin{equation}\\widehat{f}(x)\\geq0\\mbox{ for all } x\\in\\mathbb{R}^d.\\end{equation}"],
     conclusions=["the  density of  $d$-dimensional\n sphere packings is bounded above by $$\\frac{f(0)}{\\widehat{f}(0)}\\cdot \\frac{\\pi^{\\frac{d}{2}}}{2^d\\,\\Gamma(\\textstyle \\frac{d}{2}+1)}=\\frac{f(0)}{\\widehat{f}(0)}\\cdot \\mathrm{Vol}\\,B_d(0,\\frac 12).$$"],
     statement_short="If $f\\le0$ outside the unit ball and $\\widehat f\\ge0$, every packing has density at most $f(0)/\\widehat f(0)\\cdot\\mathrm{Vol}\\,B_d(0,1/2)$.",
     **ext("Cohn & Elkies 2003"))
eq("F3", "Cohn-Elkies condition (1): f <= 0 outside the unit ball", **ext("Cohn & Elkies 2003"))
eq("F4", "Cohn-Elkies condition (2): f-hat >= 0", **ext("Cohn & Elkies 2003"))
node("c_radial", "claim", "The Cohn-Elkies function can be taken radial",
     span("Without loss of generality we can assume that a function $f$", "\\cite[p. 695]{ElkiesCohn}."),
     confidence=0.7, assumptions=[], conclusions=["a function $f$ in Theorem~\\ref{thm: Cohn-Elkies} is radial"], **ext("Cohn & Elkies 2003, p. 695"))
node("d_radial", "definition", "Radial profile f_0(r)",
     span("For a radial function $f_0:\\mathbb{R}^d\\to\\mathbb{R}$ we will denote", "on vectors of length $r$."),
     definiendum="$f_0(r)$", confidence=0.85)
node("a_d8", "assumption", "Dimension d = 8", span("Henceforth we assume $d=8$.", "Henceforth we assume $d=8$."), confidence=0.85)
node("pp_ratio", "proof", "Proof of the lower bound f(0)/f-hat(0) >= 2^4 (Poisson summation)",
     span("The Poisson summation formula implies\n $$ \\sum", "\\widehat{f}(\\ell).$$"), confidence=0.75,
     statement_short="Poisson summation over $\\frac{1}{\\sqrt2}\\Lambda_8$ and its dual $\\sqrt2\\Lambda_8$.", proof_strategy=["direct"])
node("c_ratio", "claim", "Lower bound f(0)/f-hat(0) >= 2^4 for Cohn-Elkies functions in dimension 8",
     span("Hence, if a function $f$ satisfies conditions", "\\geq 2^4.$$"), confidence=0.75,
     assumptions=["a function $f$ satisfies conditions \\eqref{eqn: Cohn-Elkies condition 1} and \\eqref{eqn: Cohn-Elkies condition 2}"],
     conclusions=["$$ \\frac{f(0)}{\\widehat{f}(0)}\\geq 2^4.$$"], tags=["bound"])
node("d_optimal", "definition", "Optimal (Cohn-Elkies) function",
     span("We say that an admissible function $f:\\mathbb{R}^8\\to\\mathbb{R}$ is \\emph{optimal}", "$f(0)/\\widehat{f}(0)=2^4$."),
     definiendum="optimal", genus="admissible function $f:\\mathbb{R}^8\\to\\mathbb{R}$", confidence=0.9)
node("t_g", "theorem", "Existence of the optimal function g (magic function)", fact="F5", tags=["existence", "fourier_analysis"],
     assumptions=[],
     conclusions=["There exists a radial Schwartz function $g:\\mathbb{R}^8\\to\\mathbb{R}$ which satisfies", "the values $g(x)$ and $\\widehat{g}(x)$ do not vanish for all vectors $x$ with $\\|x\\|^2\\notin 2\\mathbb{Z}_{>0}$"],
     statement_short="A radial Schwartz $g$ on $\\mathbb{R}^8$ with $g\\le0$ for $\\|x\\|\\ge\\sqrt2$, $\\widehat g\\ge0$, $g(0)=\\widehat g(0)=1$ exists.")
eq("F6", "Condition (g1): g <= 0 for |x| >= sqrt 2")
eq("F96", "Condition (g2): g-hat >= 0")
eq("F97", "Condition (g3): g(0) = g-hat(0) = 1")
node("pp_main", "proof", "Proof of Theorem 1 from Theorems 2 and 3",
     span("Theorem \\ref{thm: Cohn-Elkies} applied to the optimal function", "immediately implies Theorem \\ref{thm: main}."),
     confidence=0.9, statement_short="Apply the Cohn-Elkies bound to the rescaled optimal function $f(x)=g(\\sqrt2 x)$.", proof_strategy=["direct"])
node("pp_unique", "proof", "Uniqueness via Cohn-Elkies Conjecture 8.1",
     span("Additionally, the function $g$ satisfies the conclusions", "densest periodic sphere packing in $\\mathbb{R}^8$."),
     confidence=0.75, rigor=None, statement_short="$g$ satisfies the conclusions of Cohn-Elkies Conjecture 8.1, which gives uniqueness among periodic packings.",
     proof_strategy=["direct"])
node("pp_dz", "proof", "Poisson summation forces zeroes of g at lattice points",
     span("Suppose that there exists a Schwartz function $g$ such that the conditions", "\\geq \\widehat{g}(0)=1.\n\\end{equation}"),
     confidence=0.75, statement_short="Poisson summation over $\\Lambda_8$ squeezes $\\sum g(\\ell)\\le1\\le\\sum\\widehat g(\\ell)$, so all nonzero lattice terms vanish.",
     proof_strategy=["direct"])
eq("F7", "Poisson summation over E8 for g")
eq("F8", "Sum of g over E8 is at most 1")
eq("F9", "Sum of g-hat over E8 is at least 1")
node("c_dz", "claim", "An optimal g must vanish to second order at nonzero E8 points",
     span("Therefore, we deduce that $g(\\ell)=\\widehat{g}(\\ell)=0$", "of length bigger than $\\sqrt{2}$."),
     confidence=0.75, rigor="semi_formal", tags=["necessary_condition"],
     assumptions=[], conclusions=["$g(\\ell)=\\widehat{g}(\\ell)=0$ for all $\\ell\\in\\Lambda_8\\backslash\\{0\\}$",
                                  "the first derivatives $\\frac{d}{dr}g(r)$ and $\\frac{d}{dr}\\widehat{g}(r)$ also vanish at all $\\Lambda_8$-lattice points of length bigger than $\\sqrt{2}$"])
node("d_dz", "definition", "Double zeroes", span("We will say that $g$ and $\\widehat{g}$ have double zeroes", "at these points."),
     definiendum="double zeroes", confidence=0.85)
node("r_hint", "remark", "Double zeroes as a hint for the construction",
     span("This property gives us a hint on constructing", "the function $g$ explicitly."), confidence=0.75)
node("r_closed", "remark", "g is a Laplace transform of a modular form",
     span("In Section \\ref{sec: g} a function $g$ satisfying", "of a certain kind."), confidence=0.75,
     statement_short="The optimal $g$ is given in closed form as a Laplace transform of a modular form.")

# ---------------------------------------------------------------- Section 3
node("d_H", "definition", "Upper half-plane", span("Let $\\mathbb{H}$ be the upper half-plane", "\\mathrm{Im}\\,(z)>0\\}$."),
     definiendum="$\\mathbb{H}$", confidence=0.9, **ext())
node("d_modgroup", "definition", "Modular group Gamma(1)", span("The modular group $\\Gamma(1):=", "\\frac{az+b}{cz+d}.$$"),
     definiendum="$\\Gamma(1)$", confidence=0.9, **ext())
node("d_GammaN", "definition", "Principal congruence subgroup Gamma(N)", span("Let $N$ be a positive integer. The \\emph{level $N$", "\\;\\mathrm{mod}\\;N\\right\\}.$$"),
     definiendum="$\\Gamma(N)$", confidence=0.9, **ext())
node("d_congruence", "definition", "Congruence subgroup", span("A subgroup $\\Gamma\\subset\\Gamma(1)$ is called", "for some $N\\in\\mathbb{N}$."),
     definiendum="congruence subgroup", genus="subgroup $\\Gamma\\subset\\Gamma(1)$", differentia=["$\\Gamma(N)\\subset\\Gamma$ for some $N\\in\\mathbb{N}$"],
     confidence=0.9, **ext())
node("d_Gamma0", "definition", "Congruence subgroup Gamma_0(N)", span("An important example of a congruence subgroup is", "c\\equiv0\\;\\mathrm{mod}\\;N\\right\\}.$$"),
     definiendum="$\\Gamma_0(N)$", confidence=0.85, **ext())
node("d_autfactor", "definition", "Automorphy factor of weight k", span("Let $z\\in\\mathbb{H}$, $k\\in\\mathbb{Z}$, and", ":=(cz+d)^{-k}.$$"),
     definiendum="automorphy factor", confidence=0.9, **ext())
node("c_chain", "claim", "Chain rule for the automorphy factor", span("The automorphy factor satisfies the \\emph{chain rule}", "j_k(\\gamma_2z,\\gamma_1). $$"),
     confidence=0.8, assumptions=[], conclusions=["$$j_k(z,\\gamma_1\\gamma_2)=j_k(z,\\gamma_2)\\,j_k(\\gamma_2z,\\gamma_1). $$"], **ext())
node("d_slash", "definition", "Slash operator", span("Let $F$ be a  function on $\\mathbb{H}$ and", "\\,F(\\gamma z). $$"),
     definiendum="slash operator", confidence=0.9, **ext())
node("c_slash_action", "claim", "The slash operator is a right action", span("The chain rule implies\n$$F|_k", "|_k\\gamma_2.$$"),
     confidence=0.8, assumptions=[], conclusions=["$$F|_k\\gamma_1\\gamma_2=(F|_k\\gamma_1)|_k\\gamma_2.$$"], **ext())
node("d_modform", "definition", "Holomorphic modular form", span("A \\emph{(holomorphic) modular form} of integer weight", "\\end{enumerate}"),
     definiendum="modular form", genus="holomorphic function $f:\\mathbb{H}\\to\\mathbb{C}$", confidence=0.9, **ext())
node("d_Mk", "definition", "Space M_k(Gamma) of modular forms", span("Let $M_k(\\Gamma)$ be the space", "congruence subgroup $\\Gamma$."),
     definiendum="$M_k(\\Gamma)$", confidence=0.9, **ext())
node("c_findim", "claim", "Spaces of modular forms are finite dimensional", span("A key fact in the theory of modular forms is", "are finite dimensional."),
     confidence=0.8, assumptions=[], conclusions=["the spaces $M_k(\\Gamma)$ are finite dimensional"], **ext())
node("d_eisenstein", "definition", "Eisenstein series E_k", span("For an even integer $k\\geq 4$ we define", "(cz+d)^{-k}.\\end{equation}"),
     definiendum=["weight $k$ Eisenstein series", "$E_k$"], confidence=0.9, **ext())
eq("F10", "Eisenstein series as a lattice sum", **ext())
node("c_Ek_modular", "claim", "E_k is a modular form of weight k", span("Since the sum converges absolutely, it is easy to see", "E_k\\in M_k(\\Gamma(1))$."),
     confidence=0.8, assumptions=[], conclusions=["$E_k\\in M_k(\\Gamma(1))$"], **ext())
node("c_Ek_fourier", "claim", "Fourier expansion of E_k", span("The\nEisenstein series possesses the Fourier expansion", "\\sum_{d|n} d^{k-1}$."),
     confidence=0.8, assumptions=[], conclusions=["\\begin{equation}E_k(z)=1+\\frac{2}{\\zeta(1-k)}\\sum_{n=1}^\\infty \\sigma_{k-1}(n)\\,e^{2\\pi i n z}, \\end{equation}"], **ext())
eq("F11", "Fourier expansion of E_k", **ext())
node("c_E4E6", "claim", "Fourier expansions of E_4 and E_6", span("In particular, we have\n\\begin{align*}\n  E_4(z)", "\\sigma_5(n)\\,e^{2\\pi i n z}.\n\\end{align*}"),
     confidence=0.8, assumptions=[], conclusions=["E_4(z)\\,=\\,& 1+240\\sum_{n=1}^\\infty \\sigma_3(n)\\,e^{2\\pi i n z}", "E_6(z)\\,=\\,& 1-504\\sum_{n=1}^\\infty \\sigma_5(n)\\,e^{2\\pi i n z}"], **ext())
node("r_E2_diverge", "remark", "The Eisenstein sum diverges for k = 2", span("The infinite sum \\eqref{eqn: Ek definition} does not converge", "for $k=2$."),
     confidence=0.7, **ext())
node("d_E2", "definition", "Weight 2 Eisenstein series E_2", span("On the other hand, the expression \\eqref{eqn: Ek Fourier} converges", "\\sigma_1(n)\\,e^{2\\pi i n z}.\\end{equation}"),
     definiendum="$E_2$", confidence=0.85, **ext())
eq("F13", "Definition of E_2 by its q-expansion", **ext())
node("c_E2_transform", "claim", "Quasimodular transformation law of E_2", span("This function is not modular, but it satisfies", "\\frac{1}{z}.\\end{equation}"),
     confidence=0.85, assumptions=[], conclusions=["This function is not modular", "\\begin{equation}z^{-2}\\,E_2\\Big(\\frac{-1}{z}\\Big)=E_2(z) -\\frac{6i}{\\pi}\\, \\frac{1}{z}.\\end{equation}"],
     **ext(Z + ", Sec. 2.3"))
eq("F14", "Transformation law of E_2 under z -> -1/z", **ext(Z + ", Sec. 2.3"))
node("r_quasimodular", "remark", "E_2 is quasimodular", span("The weight two Eisenstein series $E_2$ is an example", "\\cite[Section~5.1]{1-2-3}."),
     confidence=0.75, **ext(Z + ", Sec. 5.1"))
node("d_theta_term", "definition", "Theta functions", span("Another example of modular forms we consider are", "\\cite[Section~3.1]{1-2-3}."),
     definiendum="theta functions", confidence=0.7, **ext(Z + ", Sec. 3.1"))
node("d_theta", "definition", "Thetanullwerte theta_00, theta_01, theta_10", span("We define three theta functions", "(n+\\frac12)^2 z}.\n\\end{align*}"),
     definiendum=["$\\theta_{00}$", "$\\theta_{01}$", "$\\theta_{10}$"], confidence=0.9, **ext())
node("c_gens", "claim", "Gamma(1) is generated by T and S", span("The group $\\Gamma(1)$ is generated by the elements", "\\end{smallmatrix}\\right)$."),
     confidence=0.75, assumptions=[], conclusions=["The group $\\Gamma(1)$ is generated by the elements"], **ext())
node("c_theta_transform", "claim", "Action of S and T on fourth powers of theta functions",
     span("These elements  act on the fourth powers", "-\\theta_{10}^4(z). \\label{eqn: theta transform T}\n\\end{align}"),
     confidence=0.8, assumptions=[], conclusions=["These elements  act on the fourth powers of the theta functions in the following way"], **ext())
for fid, nm in (("F16", "S-transformation of theta_00^4"), ("F98", "S-transformation of theta_01^4"), ("F99", "S-transformation of theta_10^4"),
                ("F17", "T-transformation of theta_00^4"), ("F100", "T-transformation of theta_01^4"), ("F101", "T-transformation of theta_10^4")):
    eq(fid, nm, **ext())
k = "t_jacobi"; EQ["F18"] = k
node(k, "theorem", "Jacobi identity", fact="F18", confidence=0.9, assumptions=[], conclusions=["\\theta_{01}^4+\\theta_{10}^4=\\theta_{00}^4."], **ext())
node("c_theta_M2", "claim", "Fourth powers of theta functions are modular forms for Gamma(2)", span("The theta functions $\\theta^4_{00},\\theta^4_{01}$", "belong to $M_2(\\Gamma(2))$."),
     confidence=0.8, assumptions=[], conclusions=["The theta functions $\\theta^4_{00},\\theta^4_{01}$, and $\\theta^4_{10}$ belong to $M_2(\\Gamma(2))$"], **ext())
node("d_weakmod", "definition", "Weakly-holomorphic modular form", span("A \\emph{weakly-holomorphic modular form}", "$n_\\alpha\\in\\mathbb{N}$.\n\\end{enumerate}"),
     definiendum="weakly-holomorphic modular form", genus="holomorphic function $f:\\mathbb{H}\\to\\mathbb{C}$", confidence=0.9, **ext())
node("d_coef", "definition", "Fourier coefficient c_f(n)", span("For an $m$-periodic holomorphic function $f$", "c_f(n)\\,e^{2\\pi i n z}.$$"),
     definiendum="$c_f(n)$", confidence=0.9, **ext())
node("d_Mk_weak", "definition", "Space M_k^!(Gamma)", span("We denote the space of weakly-holomorphic modular forms of weight", "by $M_k^!(\\Gamma)$."),
     definiendum="$M_k^!(\\Gamma)$", confidence=0.9, **ext())
node("c_infdim", "claim", "Spaces of weakly-holomorphic modular forms are infinite dimensional", span("The spaces $M_k^!(\\Gamma)$ are infinite dimensional.", "are infinite dimensional."),
     confidence=0.75, assumptions=[], conclusions=["The spaces $M_k^!(\\Gamma)$ are infinite dimensional"], **ext())
node("d_j", "definition", "Elliptic j-invariant", span("Probably the most famous weakly-holomorphic modular form", "{E_4^3-E_6^2}. $$"),
     definiendum=["elliptic j-invariant", "$j$"], confidence=0.9, **ext())
node("c_j_fourier", "claim", "j is weakly holomorphic with the classical q-expansion", span("This function belongs to $M_0^!(\\Gamma(1))$", "where $q=e^{2\\pi i z}$."),
     confidence=0.8, assumptions=[], conclusions=["This function belongs to $M_0^!(\\Gamma(1))$"], **ext())
node("pr_j_coef", "problem", "Asymptotics of the Fourier coefficients of j", span("An important question is to find an  asymptotic formula", "Fourier coefficient  of $j$."),
     confidence=0.7, **ext())
node("t_rademacher", "theorem", "Rademacher-Petersson exact formula for the coefficients of j",
     span("Using the Hardy-Ramanujan circle method", "\\cite[Section~9.6]{Abramowitz}."), confidence=0.8,
     assumptions=[], conclusions=["\\begin{equation} c_j(n)=\\frac{2\\pi}{\\sqrt{n}}\\sum_{k=1}^\\infty \\frac{A_k(n)}{k}\\,I_1\\left(\\frac{4\\pi \\sqrt{n}}{k}\\right)\\qquad n\\in\\mathbb{Z}_{>0}\n\\end{equation}"],
     statement_short="Exact convergent Bessel-series formula for the $n$-th Fourier coefficient of $j$.",
     **ext("Rademacher & Zuckerman 1938; Petersson 1932"))
eq("F19", "Rademacher series for c_j(n)", **ext("Rademacher & Zuckerman 1938; Petersson 1932"))
node("t_hejhal", "theorem", "Convergent asymptotic expansion for coefficients of weakly holomorphic modular forms",
     span("A similar convergent asymptotic expansion holds", "\\cite[Propositions~1.10 and~1.12]{Bruinier}."), confidence=0.8,
     assumptions=[], conclusions=["A similar convergent asymptotic expansion holds for the Fourier coefficients of any weakly holomorphic modular form"],
     **ext("Hejhal 1983; Bruinier 2002, Props. 1.10, 1.12"))
node("c_effective", "claim", "Convergent expansions give effective coefficient bounds", span("Such a convergent expansion implies effective estimates", "for the Fourier coefficients."),
     confidence=0.75, assumptions=[], conclusions=["Such a convergent expansion implies effective estimates for the Fourier coefficients"], **ext())

# ---------------------------------------------------------------- Section 4
node("r_goal4", "remark", "Goal: radial Fourier eigenfunctions a, b with double zeroes on E8",
     span("In this section we construct two radial Schwartz functions", "of length greater than $\\sqrt{2}$."), confidence=0.75,
     statement_short="Section 4 constructs radial Schwartz $a$, $b$ with $\\mathcal F a=a$, $\\mathcal F b=-b$, both with double zeroes at $\\Lambda_8$-vectors longer than $\\sqrt2$.")
eq("F20", "Eigenfunction condition F(a) = a")
eq("F102", "Eigenfunction condition F(b) = -b")
node("c_lengths", "claim", "E8 vectors have lengths sqrt(2n)", span("Recall that each vector of $\\Lambda_8$ has length", "$n\\in\\mathbb{N}_{\\geq 0}$."),
     confidence=0.75, assumptions=[], conclusions=["each vector of $\\Lambda_8$ has length $\\sqrt{2n}$ for some $n\\in\\mathbb{N}_{\\geq 0}$"], **ext())
node("d_varphi", "definition", "Weakly holomorphic modular forms varphi_{-2}, varphi_{-4}",
     span("To this end we consider the following weakly holomorphic modular forms:", "{E_4^3-E_6^2}.\n \\end{align}"),
     definiendum=["$\\varphi_{-2}$", "$\\varphi_{-4}$"], confidence=0.9, tags=["modular_forms"])
eq("F21", "Definition of varphi_{-2}")
eq("F103", "Definition of varphi_{-4}")
node("c_nopoles", "claim", "varphi_{-2}, varphi_{-4} have no poles in H", span("The modular form $E_4^3-E_6^2$ does not vanish", "have no poles in $\\mathbb{H}$."),
     confidence=0.8, assumptions=[], conclusions=["$\\varphi_{-2}$ and $\\varphi_{-4}$ have no poles in $\\mathbb{H}$"])
node("c_varphi_asym", "claim", "Rademacher-type formula for the coefficients of varphi_{-2}, varphi_{-4}",
     span("Analogously to \\eqref{eqn: j Fourier asymptotic}, the Fourier coefficients", "\\kappa=-2,-4.\n  \\end{equation}"),
     confidence=0.8, rigor="semi_formal", assumptions=[], conclusions=["the Fourier coefficients of $\\varphi_{-2}$ and $\\varphi_{-4}$ satisfy"])
eq("F22", "Bessel-series formula for the coefficients of varphi_kappa")
node("d_phi", "definition", "Quasimodular forms phi_{-4}, phi_{-2}, phi_0 (the magic input for a)",
     span("We define\n\\begin{align}\n  \\phi_{-4}", "j-1728.\\label{eqn: def phi0}\n\\end{align}"),
     definiendum=["$\\phi_{-4}$", "$\\phi_{-2}$", "$\\phi_0$"], confidence=0.9, tags=["quasimodular_forms", "magic_function"],
     statement_short="$\\phi_{-4}=\\varphi_{-4}$, $\\phi_{-2}=\\varphi_{-4}E_2+\\varphi_{-2}$, $\\phi_0=\\varphi_{-4}E_2^2+2\\varphi_{-2}E_2+j-1728$.")
eq("F23", "Definition of phi_{-4}")
eq("F104", "Definition of phi_{-2}")
eq("F105", "Definition of phi_0")
node("c_phi0_transform", "claim", "Transformation rule of phi_0 under z -> -1/z", span("The function $\\phi_0(z)$ is not modular;", "\\phi_{-4}(z).\n\\end{equation}"),
     confidence=0.85, rigor="semi_formal", assumptions=[], conclusions=["The function $\\phi_0(z)$ is not modular"])
eq("F24", "phi_0(-1/z) transformation formula")
node("c_D", "claim", "phi_{-2}, phi_0 as derivatives of varphi's", span("Moreover, we have\n\\begin{align}\n\\phi_{-2}", "\\frac{d}{dz} f(z)$."),
     confidence=0.8, rigor="semi_formal", assumptions=[], conclusions=["\\phi_{-2}\\,=\\,&-3\\,D(\\varphi_{-4})+3\\varphi_{-2}"])
eq("F25", "phi_{-2} via the derivative D")
eq("F106", "phi_0 via the derivative D")
node("c_phi_asym", "claim", "Asymptotic formula for the coefficients of phi_{-4}, phi_{-2}, phi_0",
     span("These identities combined with \\eqref{eqn: j Fourier asymptotic}", "and $c_{\\phi_{0}}(n)$."), confidence=0.8, rigor="semi_formal",
     assumptions=[], conclusions=["give the asymptotic formula for the Fourier coefficients $c_{\\phi_{-4}}(n)$, $c_{\\phi_{-2}}(n)$, and $c_{\\phi_{0}}(n)$"])
node("c_phi_exp", "claim", "First Fourier coefficients of phi_{-4}, phi_{-2}, phi_0", span("The  first several terms of the corresponding Fourier expansions are", "where $q=e^{2\\pi i z}$.\nFor"),
     confidence=0.8, rigor="semi_formal", assumptions=[], conclusions=["The  first several terms of the corresponding Fourier expansions are"])
NODES[-1]["statement"] = NODES[-1]["statement"][:-len(" For")]
eq("F26", "q-expansion of phi_{-4}")
eq("F107", "q-expansion of phi_{-2}")
eq("F108", "q-expansion of phi_0")
node("d_a", "definition", "Magic function a (contour integral of phi_0)", span("For $x\\in\\mathbb{R}^8$ we define\n\\begin{align}", "e^{\\pi i \\|x\\|^2 z}\\,dz.\\nonumber\n\\end{align}"),
     definiendum="$a(x)$", confidence=0.9, tags=["magic_function", "contour_integral"],
     statement_short="$a(x)$: sum of four contour integrals of $\\phi_0$ against the Gaussian $e^{\\pi i\\|x\\|^2 z}$.")
eq("F27", "Contour-integral definition of a(x)")
node("c_a_conv", "claim", "The contour integrals defining a converge", span("We observe that the contour integrals in \\eqref{eqn: a(r) definition}", "for  $x\\in\\mathbb{R}^8$."),
     confidence=0.8, assumptions=[], conclusions=["the contour integrals in \\eqref{eqn: a(r) definition} converge absolutely and uniformly for  $x\\in\\mathbb{R}^8$"])
node("pp_a_conv", "proof", "Proof that a is well defined", span("Indeed,\n$\\phi_0(z)=O(e^{-2\\pi i z})$", "$a(x)$ is well defined."),
     confidence=0.85, statement_short="Exponential decay of $\\phi_0$ at $i\\infty$.", proof_strategy=["direct"])
node("p1", "proposition", "a is a Schwartz eigenfunction of the Fourier transform (eigenvalue +1)", fact="F28", tags=["fourier_eigenfunction", "magic_function"],
     assumptions=["The function $a$ defined by \\eqref{eqn: a(r) definition}"], conclusions=["belongs to the Schwartz space and satisfies $$\\widehat{a}(x)=a(x). $$"])
node("pp1", "proof", "Proof of Proposition 1", fact="F29", proof_strategy=["direct", "algebraic_manipulation"],
     statement_short="Bound $\\phi_0$ via its Fourier coefficients to get Schwartz decay; then Fourier-transform the Gaussian under the integral and substitute $w=-1/z$. The key step is the modular change of variables that maps the contour sum to itself.")
eq("F31", "Fourier transform of a Gaussian")
node("p2", "proposition", "Double zeroes of a: sin^2 factorisation", fact="F35", tags=["double_zeroes"],
     assumptions=["$r>\\sqrt{2}$"], conclusions=["\\begin{equation}\n  a(r)=-4\\sin(\\pi r^2/2)^2\\,\\int\\limits_{0}^{i\\infty}\\phi_0\\Big(\\frac{-1}{z}\\Big)\\,z^2\\,e^{\\pi i r^2 \\,z}\\,dz.\n\\end{equation}"],
     statement_short="For $r>\\sqrt2$, $a(r)=-4\\sin^2(\\pi r^2/2)\\int_0^{i\\infty}\\phi_0(-1/z)z^2e^{\\pi i r^2 z}dz$, so $a$ has double zeroes at $r^2\\in2\\mathbb{Z}$, $r>\\sqrt2$.")
eq("F36", "sin^2 representation of a(r)")
node("pp2", "proof", "Proof of Proposition 2", fact="F37", proof_strategy=["direct", "algebraic_manipulation"],
     statement_short="Deform contours and use the transformation rule of $\\phi_0$ to collapse the second difference to $2\\phi_0$.")
node("p3", "proposition", "Laplace-transform representation of a for all r >= 0", fact="F43",
     assumptions=["$r\\geq0$"], conclusions=["The integral converges absolutely for all $r\\in\\mathbb{R}_{\\geq 0}$."],
     statement_short="$a(r)=4i\\sin^2(\\pi r^2/2)(\\ldots+\\int_0^\\infty(\\ldots)e^{-\\pi r^2t}dt)$ for all $r\\ge0$, with the growing terms of $\\phi_0$ subtracted.")
eq("F44", "Laplace representation of a(r)")
node("pp3", "proof", "Proof of Proposition 3", fact="F45", proof_strategy=["direct"],
     statement_short="Valid for $r>\\sqrt2$ by Proposition 2 and the asymptotics of $\\phi_0$; extend to $[0,\\infty)$ by analytic continuation.")
eq("F46", "Asymptotics of t^2 phi_0(i/t)")
eq("F47", "Laplace transform of the growing part")
node("c_a_imag", "claim", "a takes purely imaginary values", span("From the identity~\\eqref{eqn: a another integral} we see", "for all $r\\in\\mathbb{R}_{\\geq0}$."),
     confidence=0.8, assumptions=[], conclusions=["the values $a(r)$ are in $i\\mathbb{R}$ for all $r\\in\\mathbb{R}_{\\geq0}$"])
node("p4", "proposition", "Special values of a at 0 and sqrt 2", fact="F48", rigor="semi_formal",
     assumptions=[], conclusions=["a(0)=\\frac{-i\\,8640}{\\pi}\\qquad\na(\\sqrt{2})=0\\qquad\na^\\prime(\\sqrt{2})=\\frac{i\\,72\\sqrt{2}}{\\pi}."])
eq("F49", "Values a(0), a(sqrt 2), a'(sqrt 2)")
node("pp4", "proof", "Proof of Proposition 4", fact="F50", proof_strategy=["direct"],
     statement_short="Read off from Proposition 3.")
node("d_h", "definition", "Theta quotient h (the magic input for b)", span("To this end we consider the modular form\n\\begin{equation}", "{\\theta_{10}^8}.\n\\end{equation}"),
     definiendum="$h$", confidence=0.9, tags=["modular_forms", "magic_function"])
eq("F51", "Definition of h = 128 (theta_00^4 + theta_01^4)/theta_10^8")
node("c_h_mod", "claim", "h is weakly holomorphic of weight -2 for Gamma_0(2)", span("It is easy to see that $h\\in M^!_{-2}(\\Gamma_0(2))$.", "$h\\in M^!_{-2}(\\Gamma_0(2))$."),
     confidence=0.8, assumptions=[], conclusions=["$h\\in M^!_{-2}(\\Gamma_0(2))$"])
node("pp_h", "proof", "Proof that h is in M^!_{-2}(Gamma_0(2))", span("Indeed, first we check that $h|_{-2}\\gamma=h$", "- 2550 q^3+O(q^4).\n\\end{equation*}"),
     confidence=0.85, proof_strategy=["direct"],
     statement_short="Check invariance on generators of $\\Gamma_0(2)$ via the theta transformation laws; poles only at cusps since $\\theta_{10}$ has no zeros (Mumford).")
node("d_IST", "definition", "Matrices I, T, S", span("Let $I=\\left(", "be elements of $\\Gamma(1)$."),
     definiendum=["$I$", "$T$", "$S$"], confidence=0.85, **ext())
node("d_psi", "definition", "Functions psi_I, psi_T, psi_S", span("We define the following three functions\n\\begin{align}\n  \\psi_I", "\\label{eqn: psi S define}\n\\end{align}"),
     definiendum=["$\\psi_I$", "$\\psi_T$", "$\\psi_S$"], confidence=0.9, tags=["magic_function"],
     statement_short="$\\psi_I=h-h|_{-2}ST$, $\\psi_T=\\psi_I|_{-2}T$, $\\psi_S=\\psi_I|_{-2}S$.")
eq("F53", "Definition of psi_I")
eq("F109", "Definition of psi_T")
eq("F110", "Definition of psi_S")
node("c_psi_explicit", "claim", "Explicit theta expressions for psi_I, psi_T, psi_S", span("More explicitly, we have\n\\begin{align}\n\\psi_I", "\\label{eqn: psi S explicit}\n\\end{align}"),
     confidence=0.8, rigor="semi_formal", assumptions=[], conclusions=["More explicitly, we have"])
eq("F54", "psi_I in theta functions")
eq("F111", "psi_T in theta functions")
eq("F112", "psi_S in theta functions")
node("c_psi_exp", "claim", "q-expansions of psi_I, psi_T, psi_S", span("The Fourier expansions of these functions are", "\\label{eqn: psi fourier S}\n\\end{align}"),
     confidence=0.8, rigor="semi_formal", assumptions=[], conclusions=["The Fourier expansions of these functions are"])
eq("F55", "q-expansion of psi_I")
eq("F113", "q-expansion of psi_T")
eq("F114", "q-expansion of psi_S")
node("d_b", "definition", "Magic function b (contour integral of psi's)", span("For $x\\in\\mathbb{R}^8$ define\n\\begin{align}", "\\,dz \\nonumber.\n\\end{align}"),
     definiendum="$b(x)$", confidence=0.9, tags=["magic_function", "contour_integral"],
     statement_short="$b(x)$: contour integrals of $\\psi_T,\\psi_I,\\psi_S$ against the Gaussian $e^{\\pi i\\|x\\|^2 z}$.")
eq("F56", "Contour-integral definition of b(x)")
node("p5", "proposition", "b is a Schwartz eigenfunction of the Fourier transform (eigenvalue -1)", fact="F57", tags=["fourier_eigenfunction", "magic_function"],
     assumptions=["The function $b$ defined by \\eqref{eqn: b(r) definition}"], conclusions=["belongs to the Schwartz space and satisfies\n  $$\\widehat{b}(x)=-b(x). $$"])
node("pp5", "proof", "Proof of Proposition 5", fact="F58", proof_strategy=["direct", "algebraic_manipulation"],
     statement_short="As for Proposition 1: decay of $\\psi_S$ gives Schwartz bounds; the Gaussian transform and $w=-1/z$ with the $S$-action on $\\psi_I,\\psi_T,\\psi_S$ give $\\mathcal F b=-b$.")
node("p6", "proposition", "Double zeroes of b: sin^2 factorisation", fact="F64", tags=["double_zeroes"],
     assumptions=["$r>\\sqrt{2}$"], conclusions=["\\begin{equation}\n  b(r)=-4\\sin(\\pi r^2/2)^2\\,\\int\\limits_{0}^{i\\infty}\\psi_I(z)\\,e^{\\pi i r^2 \\,z}\\,dz.\n\\end{equation}"])
eq("F65", "sin^2 representation of b(r)")
node("pp6", "proof", "Proof of Proposition 6", fact="F66", proof_strategy=["direct", "algebraic_manipulation"],
     statement_short="Deform contours and use the identity $\\psi_T+\\psi_S=\\psi_I$, proved from $h\\in M^!_{-2}(\\Gamma_0(2))$.")
eq("F68", "Contour deformation for psi_I(z+1)")
eq("F115", "Contour deformation for psi_I(z-1)")
eq("F69", "Intermediate expression for c(r)")
eq("F70", "Identity psi_T + psi_S = psi_I")
node("p7", "proposition", "Laplace-transform representation of b for all r >= 0", fact="F73",
     assumptions=["$r\\geq0$"], conclusions=["The integral converges absolutely for all $r\\in\\mathbb{R}_{\\geq 0}$."])
eq("F74", "Laplace representation of b(r)")
node("pp7", "proof", "Proof of Proposition 7", fact="F75", proof_strategy=["direct"],
     statement_short="Analogous to Proposition 3: Proposition 6 plus asymptotics of $\\psi_I$ for $r>\\sqrt2$, then analytic continuation.")
eq("F76", "Asymptotics of psi_I(it)")
eq("F77", "Laplace transform of e^{2 pi t} + 144")
node("c_b_imag", "claim", "b takes purely imaginary values", span("We see from \\eqref{eqn: b another integral} that $b(r)\\in i\\mathbb{R}$", "\\mathbb{R}_\\geq{0}$."),
     confidence=0.8, assumptions=[], conclusions=["$b(r)\\in i\\mathbb{R}$ far all $r\\in\\mathbb{R}_\\geq{0}$"])
node("p8", "proposition", "Special values of b at 0 and sqrt 2", fact="F78", rigor="semi_formal",
     assumptions=[], conclusions=["b(0)=0\\qquad\nb(\\sqrt{2})=0\\qquad\nb^\\prime(\\sqrt{2})=2\\sqrt{2}\\,\\pi\\,i."])
eq("F79", "Values b(0), b(sqrt 2), b'(sqrt 2)")

# ---------------------------------------------------------------- Section 5
node("t_g1", "theorem", "The explicit optimal function g = (pi i/8640) a + (i/240 pi) b", fact="F80", tags=["existence", "magic_function"],
     assumptions=[], conclusions=["satisfies conditions \\eqref{eqn: g1}--\\eqref{eqn: g3}", "the values $g(x)$ and $\\widehat{g}(x)$ do not vanish for all vectors $x$ with $\\|x\\|^2\\notin 2\\mathbb{Z}_{>0}$"],
     statement_short="The combination $g=\\frac{\\pi i}{8640}a+\\frac{i}{240\\pi}b$ satisfies (g1)-(g3) and $g,\\widehat g$ vanish only at $\\|x\\|^2\\in2\\mathbb{Z}_{>0}$.")
node("pp_g1", "proof", "Proof of Theorems 3 and 4", fact="F81", proof_strategy=["direct", "other"],
     statement_short="Write $g$ and $\\widehat g$ as $\\sin^2(\\pi r^2/2)$ times Laplace transforms of $A(t)$, $B(t)$ and show $A<0$, $B>0$. The key step bounds $A$, $B$ by truncated $q$-expansions with rigorous tail estimates, checked by interval arithmetic.")
for fid, nm in (("F82", "g(r) as sin^2 times a Laplace transform of A"), ("F84", "Asymptotics of A(t) as t -> 0"), ("F116", "Asymptotics of A(t) as t -> infinity"),
                ("F86", "Coefficient bound for psi_I"), ("F87", "Coefficient bounds for psi_S, phi_0, phi_{-2}, phi_{-4}"),
                ("F91", "g-hat(r) as sin^2 times a Laplace transform of B")):
    eq(fid, nm)

# ---------------------------------------------------------------- proof steps
STEPS = []


def step(k, parent, name, a, b, subclass, after=None, conf=0.75, short=None):
    base = next(x for x in NODES + STEPS if x["k"] == parent)["pos"]
    i, j = span(a, b, base)
    s = dict(k=k, type="proof_step", name=name, statement=clean(SRC[i:j]), pos=i, end=j, parent=parent,
             subclass=subclass, confidence=conf, statement_short=short or name)
    STEPS.append(s)
    return s


# Section 2 prose proof (pp_dz)
step("dz1", "pp_dz", "Assume g exists; apply Poisson summation over E8", "Suppose that there exists", "\\widehat{g}(\\ell).\n\\end{equation}", "invoke_identity")
step("dz2", "pp_dz", "Bound the g-side by g(0)", "Since $\\|\\ell\\|\\geq\\sqrt{2}$", "\\leq g(0)=1.\n\\end{equation}", "bound_estimate")
step("dz3", "pp_dz", "Bound the g-hat-side by g-hat(0)", "On the other hand, conditions", "\\geq \\widehat{g}(0)=1.\n\\end{equation}", "bound_estimate")
# pp_h
step("h1", "pp_h", "Check invariance of h under Gamma_0(2)", "Indeed, first we check", "and \\eqref{eqn: h define}.", "conclude")
step("h1a", "h1", "Reduce to the two generators of Gamma_0(2)", "Since the group $\\Gamma_0(2)$ is generated", "invariant under their action.", "setup")
step("h1b", "h1", "Invariance from the theta transformation laws", "This follows immediately", "and \\eqref{eqn: h define}.", "conclude")
step("h2", "pp_h", "Poles only at the cusps (theta_10 has no zeros)", "Next we analyze the poles", "poles only at the cusps.", "apply_lemma")
step("h3", "pp_h", "q-expansion of h at the cusp i infinity", "At the cusp $i\\infty$", "+O(q^4).\n\\end{equation*}", "other")
# pp1
P1 = "First, we prove that $a$ is a Schwartz function."
step("p1s1", "pp1", "a is a Schwartz function", P1, "for all derivatives $\\frac{d^k}{dr^k}a(r)$.", "conclude", conf=0.95)
step("p1s1a", "p1s1", "Exponential bound on the coefficients of phi_0", "From \\eqref{eqn: j Fourier asymptotic}, \\eqref{eqn: varphi", "\\quad n\\in\\mathbb{Z}_{>0}.$$", "bound_estimate")
step("p1s1b", "p1s1", "Exponential decay of phi_0 in the upper half-plane", "Thus, there exists a positive constant $C$ such that\n$$|\\phi_0", "\\mathrm{Im}\\,{z}>\\frac 12.$$", "bound_estimate")
step("p1s1c", "p1s1", "Bessel-K bound for the first three contour integrals", "We estimate the first summand", "second and third summand in \\eqref{eqn: a(r) definition}.", "bound_estimate")
step("p1s1d", "p1s1", "Bound for the last contour integral", "For the last summand we have", "{r^2+2}.$$", "bound_estimate")
step("p1s1e", "p1s1", "Combine into rapid decay of a(r)", "Therefore, we arrive at", "any inverse power of $r$.", "bound_estimate")
step("p1s1f", "p1s1", "Same estimates for all derivatives", "Analogous estimates can be obtained", "\\frac{d^k}{dr^k}a(r)$.", "conclude")
step("p1s2", "pp1", "a is a Fourier eigenfunction", "Now we show that $a$ is an eigenfunction", "This finishes the proof of the proposition.", "conclude", conf=0.95)
step("p1s2a", "p1s2", "Recall the Fourier transform of a Gaussian", "We recall that the Fourier transform of a Gaussian", "(\\frac{-1}{z}) }.\\end{equation}", "setup")
step("p1s2b", "p1s2", "Exchange contour integral and Fourier transform", "Next, we exchange the contour integration", "\\,(\\frac{-1}{z})}\\,dz.\n\\end{align*}", "algebraic_manipulation")
step("p1s2c", "p1s2", "Change of variables w = -1/z", "Now we make a change of variables", "\\,w}\\,dw.\n\\end{align*}", "substitute")
step("p1s2d", "p1s2", "Use 1-periodicity of phi_0 to recover a", "Since $\\phi_0$ is $1$-periodic", "This finishes the proof of the proposition.", "conclude")
# pp2
step("p2s1", "pp2", "Name the right-hand side d(r); it is well defined", "We denote the right hand side of \\eqref{eqn: a double zeroes}", "is well-defined.", "introduce_variable")
step("p2s2", "pp2", "Asymptotics of phi_0(-1/it); absolute convergence", "Indeed, from the transformation formula", "converges absolutely for $r>\\sqrt{2}$.", "bound_estimate")
step("p2s3", "pp2", "Split d(r) into three shifted integrals", "We can write", "\\,dz.\n\\end{align*}", "algebraic_manipulation")
step("p2s4", "pp2", "Deform the integration paths", "From \\eqref{eqn: phi0 transform} we deduce that if $r>\\sqrt{2}$", "\\,dz.\n\\end{align*}", "other")
step("p2s5", "pp2", "Second difference of phi_0 collapses to 2 phi_0", "Now from \\eqref{eqn: phi0 transform} we find", "&2\\phi_0(z).\n \\end{align*}", "invoke_identity")
step("p2s6", "pp2", "Conclude d(r) = a(r)", "Thus, we obtain\n \\begin{align*}\n d(r)", "This finishes the proof.", "conclude")
# pp3
step("p3s1", "pp3", "For r > sqrt 2 apply Proposition 2", "Suppose that $r>\\sqrt{2}$. Then by Proposition~\\ref{prop: a(r) double zeroes}", "\\,dt. $$", "apply_lemma")
step("p3s2", "pp3", "Asymptotic expansion of t^2 phi_0(i/t)", "From \\eqref{eqn: phi fourier0}--\\eqref{eqn: phi0 transform} we obtain", "\\;t\\to\\infty.\n\\end{equation}", "bound_estimate")
step("p3s3", "pp3", "Integrate the growing part: identity for r > sqrt 2", "For $r>\\sqrt{2}$ we have\n\\begin{equation}\n\\int\\limits_0^\\infty \\left(\\frac{36}", "holds for $r>\\sqrt{2}$.", "algebraic_manipulation")
step("p3s4", "pp3", "Extend to [0, infinity) by analytic continuation", "On the other hand, from the definition~", "This finishes the proof of the proposition.", "conclude")
# pp5
step("p5s0", "pp5", "Reuse the argument of Proposition 1", "Here, we repeat the arguments", "\\ref{prop: a(r) Fourier}.", "setup")
step("p5s1", "pp5", "b is a Schwartz function", "First we show that $b$ is a Schwartz function.", "\\frac{d^k}{d^k r} b(r)$.", "conclude", conf=0.95)
step("p5s1a", "p5s1", "Rewrite the first integral through psi_S", "We have\n\\begin{align*}\n &\\int\\limits_{-1}^{i}\\psi_T", "(-1/z-1)}\\,dz.\\\\\n\\end{align*}", "algebraic_manipulation")
step("p5s1b", "p5s1", "Exponential decay of psi_S", "There exists a positive constant $C$ such that\n$$|\\psi_S", "\\mathrm{Im}\\,{z}>\\frac12.$$", "bound_estimate")
step("p5s1c", "p5s1", "Bessel-K bound for the first integral", "Thus, as in the proof of Proposition~\\ref{prop: a(r) Fourier}", "\\leq C_1\\,r\\,K_1(2\\pi r).$$", "bound_estimate")
step("p5s1d", "p5s1", "Combine the four bounds; derivatives similarly", "We combine this inequality", "\\frac{d^k}{d^k r} b(r)$.", "conclude")
step("p5s2", "pp5", "b is a Fourier eigenfunction with eigenvalue -1", "Now we prove that $b$ is an eigenfunction", "$$ \\mathcal{F}(b)(x)=-b(x). $$", "conclude", conf=0.95)
step("p5s2a", "p5s2", "Gaussian transform under the integral", "We use identity~\\eqref{eqn: Gaussian Fourier}", "(\\frac{-1}{z})}\\,dz.\n\\end{align*}", "invoke_identity")
step("p5s2b", "p5s2", "Change of variables w = -1/z", "We make the change of variables $w=\\frac{-1}{z}$ and arrive at", "w}\\,dw.\n\\end{align*}", "substitute")
step("p5s2c", "p5s2", "S-action on psi_T, psi_I, psi_S", "Now we observe that the definitions", "\\psi_S|_{-2}S=&\\psi_I. \\\\\n\\end{align*}", "invoke_identity")
step("p5s2d", "p5s2", "Conclude F(b) = -b", "Therefore, we arrive at\n\\begin{align*}\n  \\mathcal{F}(b)(x)", "$$ \\mathcal{F}(b)(x)=-b(x). $$", "conclude")
# pp6
step("p6s0", "pp6", "Name the right-hand side c(r)", "We denote the right hand side of~\\eqref{eqn: b double zeroes}", "by $c(r)$.", "introduce_variable")
step("p6s1", "pp6", "c(r) is well defined", "First, we check that $c(r)$ is well-defined.", "converges for $r>\\sqrt{2}$.", "conclude", conf=0.95)
step("p6s1a", "p6s1", "Asymptotics of psi_I(it)", "We have\n\\begin{align*}\n\\psi_I(it)", "\\;t\\to\\infty.\n\\end{align*}", "bound_estimate")
step("p6s1b", "p6s1", "Convergence for r > sqrt 2", "Therefore, the integral~\\eqref{eqn: b double zeroes} converges", "converges for $r>\\sqrt{2}$.", "conclude")
step("p6s2", "pp6", "Rewrite c(r) as shifted integrals", "Then we rewrite it in the following way:", "\\,dz.$$", "algebraic_manipulation")
step("p6s3", "pp6", "Leading term of psi_I at i infinity", "From the Fourier expansion~\\eqref{eqn: psi fourier I} we know", "\\to\\infty$.", "bound_estimate")
step("p6s4", "pp6", "Deform the paths of integration", "By assumption $r^2>2$", "\\,dz.\n\\end{align}", "other")
step("p6s5", "pp6", "Intermediate form of c(r)", "We have\n\\begin{align}\\label{eqn: c1}", "\\,dz.\\nonumber\n \\end{align}", "algebraic_manipulation")
step("p6s6", "pp6", "Identity psi_T + psi_S = psi_I", "Next, we check that the functions", "=h-h|_{-2}ST=\\psi_I.$$", "conclude", conf=0.95)
step("p6s6a", "p6s6", "Expand by the definitions of the psi's", "Indeed, from definitions", "-h|_{-2}STS.\\end{align*}", "algebraic_manipulation")
step("p6s6b", "p6s6", "Use Gamma_0(2)-invariance of h (S T^2 S)", "Note that $ST^2S$ belongs", "h|_{-2}T-h|_{-2}STS. $$", "apply_lemma")
step("p6s6c", "p6s6", "Use Gamma_0(2)-invariance again to get psi_I", "Now we observe that $T$ and $STS(ST)^{-1}$", "=h-h|_{-2}ST=\\psi_I.$$", "conclude")
step("p6s7", "pp6", "Combine to get c(r) = b(r)", "Combining \\eqref{eqn: c1} and \\eqref{eqn: c2}", "=&b(r).\n \\end{align*}", "conclude")
# pp7
step("p7s0", "pp7", "Analogous to Proposition 3", "The proof is analogous to the proof", "\\ref{prop: a another integral}.", "setup")
step("p7s1", "pp7", "For r > sqrt 2 apply Proposition 6", "First, suppose that $r>\\sqrt{2}$.", "\\,dt. $$", "apply_lemma")
step("p7s2", "pp7", "Asymptotics of psi_I(it)", "From \\eqref{eqn: psi fourier I} we obtain", "\\;t\\to\\infty.\n\\end{equation}", "bound_estimate")
step("p7s3", "pp7", "Integrate the growing part: identity for r > sqrt 2", "For $r>\\sqrt{2}$ we have\n\\begin{equation}\n\\int\\limits_0^\\infty \\left(e^{2\\pi t}", "holds for $r>\\sqrt{2}$.", "algebraic_manipulation")
step("p7s4", "pp7", "Extend to [0, infinity) by analytic continuation", "On the other hand, from the definition \\eqref{eqn: b(r) definition}", "This finishes the proof of the proposition.", "conclude")
# pp_g1
step("g1", "pp_g1", "Prove (g1): g <= 0 beyond sqrt 2", "First, we prove that \\eqref{eqn: g1} holds.", "implies \\eqref{eqn: g1}.", "conclude", conf=0.95)
step("g1a", "g1", "g(r) = sin^2 times Laplace transform of A(t)", "By Propositions~\\ref{prop: a(r) double zeroes} and", "-\\frac{36}{\\pi^2}\\,\\psi_I(it).$$", "apply_lemma")
step("g1b", "g1", "Goal A(t) < 0; plot of A", "Our goal is to show that $A(t)<0", "\\end{figure}", "setup")
step("g1c", "g1", "Two presentations of A(t) for computation", "\\noindent We observe that we can compute the values of $A(t)$", "\\,\\psi_I(it).\n\\end{align*}", "invoke_identity")
step("g1d", "g1", "Define the truncated expansions A_0^(n), A_inf^(n)", "For an integer $n\\geq0$ let $A_0^{(n)}$", "\\eqref{eqn: psi fourier S}.", "introduce_variable")
step("g1e", "g1", "Compute A_inf^(6) and A_0^(6)", "For example, from \\eqref{eqn: phi fourier4}--\\eqref{eqn: phi fourier0} and \\eqref{eqn: psi fourier I} we compute", "e^{-5\\pi/t}).$$", "algebraic_manipulation")
step("g1f", "g1", "Coefficient bounds from the convergent expansions (Bruinier)", "Moreover, from the convergent asymptotic expansion", "\\label{eqn: Fourier estimate 5}\n \\end{align}", "bound_estimate")
step("g1g", "g1", "Tail bounds R_0^(m), R_inf^(m) for the truncation error", "Therefore, we can estimate the error terms", "e^{-\\pi nt}.\n\\end{align*}", "bound_estimate")
step("g1h", "g1", "Interval arithmetic: A(t) < 0 on (0, infinity)", "Using interval arithmetic we check that", "$A(t)<0$ for $t\\in (0,\\infty)$.", "other")
step("g1i", "g1", "Conclude (g1) from the Laplace representation", "Then identity \\eqref{eqn: g A} implies", "implies \\eqref{eqn: g1}.", "conclude")
step("g2", "pp_g1", "Prove (g2): g-hat >= 0", "Next, we prove \\eqref{eqn: g2}.", "implies \\eqref{eqn: g2}.", "conclude", conf=0.95)
step("g2a", "g2", "g-hat(r) = sin^2 times Laplace transform of B(t)", "By Propositions~\\ref{prop: a another integral} and~", "\\,\\psi_I(it).$$", "apply_lemma")
step("g2b", "g2", "Two presentations of B(t)", "This function can also be written as", "\\,\\psi_I(it).\n\\end{align*}", "invoke_identity")
step("g2c", "g2", "Goal B(t) > 0; plot of B", "Our aim is to prove that $B(t)>0$", "\\end{figure}", "setup")
step("g2d", "g2", "Truncated expansions B_0^(6), B_inf^(6)", "\\noindent For $n\\geq 0$ let $B_0^{(n)}$", "e^{-5 \\pi/t}) .$$", "algebraic_manipulation")
step("g2e", "g2", "Truncation error bounded by R_0^(6), R_inf^(6)", "The estimates \\eqref{eqn: Fourier estimate 1}--", "\\quad\\mbox{for}\\;t\\in[1,\\infty).$$", "bound_estimate")
step("g2f", "g2", "Interval arithmetic: B(t) > 0", "Using interval arithmetic we verify that", "\\end{align*}", "other")
step("g2g", "g2", "Conclude (g2) from the Laplace representation", "Now identity \\eqref{eqn: g B} implies", "implies \\eqref{eqn: g2}.", "conclude")
step("g3", "pp_g1", "Prove (g3) from the special values", "Finally, the property \\eqref{eqn: g3} readily follows", "\\ref{thm: g}.", "conclude", conf=0.95)

# ---------------------------------------------------------------- ids
PREFIX = {"definition": "DP", "theorem": "TP", "lemma": "LP", "proposition": "PrP", "corollary": "CP", "proof": "PP",
          "proof_step": "PSP", "equation": "EP", "example": "ExP", "remark": "RP", "problem": "ProbP",
          "open_problem": "OpenP", "assumption": "AssumP", "claim": "ClP", "conjecture": "CnjP", "algorithm": "AP"}
ID = {}
cnt = defaultdict(int)
for n in sorted(NODES + STEPS, key=lambda n: (n["pos"], -n["end"])):
    cnt[n["type"]] += 1
    ID[n["k"]] = f"{PREFIX[n['type']]}{cnt[n['type']]}"

out_nodes = []
for n in sorted(NODES + STEPS, key=lambda n: (n["pos"], -n["end"])):
    m = {kk: v for kk, v in n.items() if kk not in ("k", "pos", "end", "parent") and v is not None}
    m["id"] = ID[n["k"]]
    if n["type"] == "proof_step":
        par = n["parent"]
        m["parent_id"] = ID[par]
        m["section"] = next(x for x in NODES + STEPS if x["k"] == par).get("section") or section_of(n["pos"])
        m["origin"] = "paper"
    out_nodes.append(m)
# step_order within each parent, section of steps
order = defaultdict(int)
for m in out_nodes:
    if m["type"] == "proof_step":
        order[m["parent_id"]] += 1
        m["step_order"] = order[m["parent_id"]]
# steps take their parent's section
sec_of = {m["id"]: m.get("section") for m in out_nodes}
for m in out_nodes:
    if m["type"] == "proof_step":
        p = m["parent_id"]
        while sec_of.get(p) is None:
            p = next(x["parent_id"] for x in out_nodes if x["id"] == p)
        m["section"] = sec_of[p]

exec(open(HERE + "/edges.py").read())     # EDGES: list of (src_key, tgt_key, type, conf, basis, extra)

edges = []
for s, t, typ, conf, basis, *extra in EDGES:
    e = {"source": ID[s], "target": ID[t], "type": typ, "confidence": conf}
    if basis:
        e["basis"] = basis
    for x in extra:
        e.update(x)
    edges.append(e)
for m in out_nodes:
    if m["type"] == "proof":
        pr = [e["target"] for e in edges if e["source"] == m["id"] and e["type"] == "proves"]
        if pr:
            m["proves"] = pr[0]

meta = json.load(open(HERE + "/meta.json"))
meta["rigor_nonformal_count"] = sum(1 for m in out_nodes if m.get("rigor"))
graph = {"metadata": meta, "nodes": out_nodes, "edges": edges}
report = finalize(graph, read_tex(TEX))
for w in report["warnings"]:
    print("WARN", w)
for e in report["errors"]:
    print("ERR", e)
print({k: (len(v) if isinstance(v, list) else v) for k, v in report.items()})
json.dump(report, open(HERE + "/report.json", "w"), indent=1, default=str)
json.dump({v: k for k, v in ID.items()}, open(HERE + "/ids.json", "w"), indent=1)
if not report["errors"]:
    import provenance as PV
    from pathlib import Path
    md = graph["metadata"]
    PV.stamp(graph, Path(TEX), tex=read_tex(TEX), extractor="llm", tool="agent + extraction_finalize",
             model=md.get("model"), prompt_version=md.get("prompt_version"), effort=md.get("effort"),
             date=md.get("extraction_date"))
    json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
    print("wrote", OUT, len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
