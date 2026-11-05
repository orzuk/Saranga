#!/usr/bin/env python3
"""Build the SARANGA v7 graph for arXiv 2605.08777 (Tolkovsky, Meidler, Zuk 2026).

Every node, its type and its span were chosen by reading the prepared source;
this script only slices those spans out of facts.json's `source`, assembles the
JSON and runs extraction_finalize.finalize().

Usage: python3 build.py   (writes ../2605_08777.json)
"""
import json
import os
import re
import sys

REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, os.path.join(REPO, "src"))
from extraction_finalize import finalize, pseudocode_steps   # noqa: E402
from latex_facts import read_tex                             # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
TEX = os.path.join(PAPER, "arxiv_src", "SSA_DA_arxiv.tex")
OUT = os.path.join(PAPER, "2605_08777.json")
SCRATCH = ("/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/"
           "scratchpad/extract_orzuk/2605_08777")
FACTS = os.path.join(SCRATCH, "facts.json")
if not os.path.exists(FACTS):
    os.makedirs(SCRATCH, exist_ok=True)
    os.system(f"python3 {REPO}/src/latex_facts.py {TEX} --out {FACTS}")
facts = json.load(open(FACTS))
SRC = facts["source"]
FACT = {f["id"]: f for f in facts["facts"]}
SECS = facts["sections"]

# ---------------------------------------------------------------- slicing
# whitespace-collapsed view of the source with an index map back to offsets
_norm, _idx = [], []
prev_space = False
for i, ch in enumerate(SRC):
    if ch.isspace():
        if not prev_space:
            _norm.append(" ")
            _idx.append(i)
        prev_space = True
    else:
        _norm.append(ch)
        _idx.append(i)
        prev_space = False
NORM = "".join(_norm)


def _nfind(marker, after=0):
    m = re.sub(r"\s+", " ", marker)
    k = NORM.find(m, after)
    assert k >= 0, f"marker not found: {marker[:80]!r}"
    return k, len(m)


def clean(text):
    text = re.sub(r"\\label\{[^{}]*\}", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def span(a, b, after=0):
    """Verbatim text from the start of marker `a` to the end of marker `b`."""
    ka, _ = _nfind(a, after)
    if not after:
        assert NORM.find(re.sub(r"\s+", " ", a), ka + 1) < 0, f"marker not unique: {a[:80]!r}"
    kb, lb = _nfind(b, ka)
    s, e = _idx[ka], _idx[kb + lb - 1] + 1
    return clean(SRC[s:e]), s


def off(a):
    return _idx[_nfind(a)[0]]


def section_at(pos):
    best = None
    for s in SECS:
        if s["inside"] is None and s["start"] <= pos:
            best = s
    return f"{best['number']} {best['title']}"


def sec_of_fact(fid):
    sid = FACT[fid]["section"]
    s = next(x for x in SECS if x["id"] == sid)
    return f"{s['number']} {s['title']}"


def fact_text(fid):
    f = FACT[fid]
    return clean(SRC[f["start"]:f["end"]])


NODES, EDGES = [], []
BYID = {}


def node(id, type, name, stmt_pos, conf, origin="paper", **kw):
    stmt, pos = stmt_pos
    n = {"id": id, "type": type, "name": name, "statement": stmt,
         "section": kw.pop("section", None) or section_at(pos), "origin": origin,
         "confidence": conf}
    if origin == "external":
        n["origin_citation"] = kw.pop("cite")
    n.update(kw)
    NODES.append(n)
    BYID[id] = n
    return n


def env(id, type, name, fid, conf=1.0, origin="paper", **kw):
    f = FACT[fid]
    kw.setdefault("section", sec_of_fact(fid))
    return node(id, type, name, (fact_text(fid), f["start"]), conf, origin, **kw)


def steps(parent, specs, first, conf=0.75):
    """specs: list of (start_marker, end_marker, subclass, name, short[, children])."""
    p = BYID[parent]
    ppos = off_of(parent)
    seq = first
    out = []

    def mk(pid, lst, order0=1):
        nonlocal seq
        for k, sp in enumerate(lst):
            a, b, sub, name, short = sp[:5]
            kids = sp[5] if len(sp) > 5 else []
            text, _ = span(a, b, after=ppos)
            sid = f"PSP{seq}"
            seq += 1
            st = {"id": sid, "type": "proof_step", "parent_id": pid, "step_order": order0 + k,
                  "name": name, "statement": text, "statement_short": short, "subclass": sub,
                  "section": p["section"], "origin": p["origin"],
                  "confidence": 0.95 if a.lstrip().startswith(("\\textit{(", "\\emph{")) else conf}
            NODES.append(st)
            BYID[sid] = st
            out.append(sid)
            if kids:
                mk(sid, kids)
    mk(parent, specs)
    return seq


def off_of(nid):
    """Normalized offset of a node's statement (to anchor step markers inside it)."""
    st = BYID[nid]["statement"]
    k = NORM.find(st[:60])
    assert k >= 0, nid
    return k


def E(s, t, type="uses", conf=0.8, basis="inferred", **kw):
    e = {"source": s, "target": t, "type": type, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    EDGES.append(e)


# ===================================================================== NODES
# ---- Section 3: problem setup and the canonical diffusion
node("DP1", "definition", "Probability density f",
     span("Let $f : \\mathbb{R}^d \\to (0, \\infty)$ be a probability density.",
          "be a probability density."), 0.75, definiendum="$f$")
node("DP2", "definition", "Generator spectrum of a reversible diffusion",
     span("A reversible It\\^o diffusion with stationary density $f$ has",
          "metastable structure of $f$~\\cite{Pavliotis2014}."), 0.75, origin="external",
     cite="Pavliotis 2014", definiendum=["$\\mathcal{L}_f$", "$\\mu_k$", "$\\psi_k$"],
     statement_short="A reversible diffusion with stationary f has a self-adjoint generator with "
                     "discrete spectrum $0=\\mu_1<\\mu_2\\le\\cdots$; small eigenvalues encode barriers.")
node("DP3", "definition", "Canonical diffusion",
     span("We single out a specific diffusion by reversibility",
          "with $W_t$ a standard $d$-dimensional Brownian motion."), 0.9,
     definiendum="canonical diffusion", genus="reversible It\\^o diffusion",
     differentia=["stationary density $f$", "constant scalar diffusion $A_0 = \\sigma_f^2 I_d$"],
     statement_short="The reversible diffusion with stationary density f and diffusion "
                     "$\\sigma_f^2 I_d$, $\\sigma_f^2=\\mathrm{tr}\\,\\mathrm{Cov}_f/d$: Langevin "
                     "SDE with drift $\\tfrac12\\sigma_f^2\\nabla\\log f$.")
env("EP1", "equation", "Canonical diffusion SDE", "F1")
env("TP1", "theorem", "Uniqueness of the canonical diffusion", "F2", main=True,
    assumptions=["Fix any $A_0\\succ 0$ and let $f$ be sufficiently regular.",
                 "reversible It\\^o diffusions with stationary density $f$ and constant diffusion matrix $A_0$"],
    conclusions=["the drift is uniquely $b(x) = \\tfrac12 A_0\\nabla\\log f(x)$"],
    statement_short="The only reversible diffusion with stationary density f and constant "
                    "diffusion matrix $A_0$ has drift $\\tfrac12 A_0\\nabla\\log f$.",
    tags=["uniqueness", "diffusion"])
env("PrP1", "proposition", "Similarity Invariance", "F3",
    assumptions=["$Y = cQX + b$ for any $c > 0$, orthogonal $Q$, and $b \\in \\mathbb{R}^d$"],
    conclusions=["$Y_t = cQX_t + b$ is the canonical diffusion for the density of $Y$",
                 "the generator spectrum is preserved, so SSA and DA are invariant under rotation, uniform rescaling, and translation"],
    statement_short="Similarity maps of the data map canonical diffusions to canonical diffusions, "
                    "so the generator spectrum, SSA and DA are similarity invariant.",
    tags=["invariance"])
node("RP1", "remark", "Robustness to the coefficient choice",
     span("We fix $A_0 = \\sigma_f^2 I_d$. For scalar alternatives",
          "kinetic Langevin in the deep-barrier limit."), 0.75,
     statement_short="Scalar $A_0=cI$ leaves DA unchanged; for general $A_0$ Rayleigh bounds control "
                     "slow eigenvalues and barrier exponents dominate in the metastable regime.")
node("DP4", "definition", "Centered canonical process",
     span("Both of our readouts derive from the stationary autocovariance",
          "where $\\bar x_f = \\mathbb{E}_f[X]$."), 0.85,
     definiendum=["$Y_t$", "$\\bar x_f$"])
node("DP5", "definition", "Autocovariance and trace-normalized autocorrelation",
     span("Let $C(\\tau) = \\mathbb{E}_f[Y_\\tau Y_0^\\top]$ and $\\rho(\\tau)",
          "\\mathrm{tr} C(0)$."), 0.9, definiendum=["$C(\\tau)$", "$\\rho(\\tau)$"])
node("DP6", "definition", "Projection coefficients",
     span("Define projection coefficients", "since $\\psi_1 \\equiv 1$."), 0.9,
     definiendum="$\\alpha_k$")
node("DP7", "definition", "Trajectory-averaged lag-tau autocovariance estimator",
     span("The empirical estimator from $N$ canonical-diffusion trajectories",
          "\\tfrac{1}{2}[\\hat C(\\tau) + \\hat C(\\tau)^\\top]$."), 0.85,
     definiendum=["$\\hat C(\\tau)$", "$\\bar x$", "$\\hat C^{\\mathrm{sym}}(\\tau)$"],
     statement_short="Estimator $\\hat C(\\tau)$: lag-$\\tau$ cross products of centered points "
                     "averaged over N trajectories; $\\hat C^{\\mathrm{sym}}$ is its symmetric part.")
env("EP2", "equation", "Empirical autocovariance", "F4")
env("LP1", "lemma", "Spectral representation of C(tau)", "F5",
    assumptions=["The stationary autocovariance"],
    conclusions=["C(\\tau) = \\sum_{k \\geq 2} e^{-\\mu_k \\tau}\\,\\alpha_k \\alpha_k^\\top",
                 "\\rho(\\tau) = \\sum_{k \\geq 2} e^{-\\mu_k \\tau}\\, w_k"],
    statement_short="$C(\\tau)$ is a sum of rank-one terms $e^{-\\mu_k\\tau}\\alpha_k\\alpha_k^\\top$, so "
                    "$\\rho(\\tau)$ is a mixture of exponentials with weights $w_k$.",
    tags=["spectral_decomposition", "identity"])

# ---- Section 4: SSA
env("DP8", "definition", "SSA (Sum of Squared Autocorrelations)", "F6",
    definiendum="SSA", statement_short="SSA $S(f)$ is the integral of $\\rho(\\tau)^2$ over all lags.")
env("EP3", "equation", "SSA definition", "F7")
env("CP1", "corollary", "Spectral formula for SSA", "F8",
    assumptions=["whenever the canonical diffusion has a spectral gap"],
    conclusions=["$S(f) \\;=\\; \\displaystyle\\sum_{k,\\ell \\geq 2} \\frac{w_k w_\\ell}{\\mu_k + \\mu_\\ell}$",
                 "$S(f)<\\infty$"],
    statement_short="$S(f)=\\sum_{k,\\ell} w_k w_\\ell/(\\mu_k+\\mu_\\ell)$, finite under a spectral gap.",
    tags=["identity"])
env("PrP2", "proposition", "Monotonicity of SSA in every eigenvalue", "F9", main=True,
    assumptions=["holding the weights $\\{w_k\\}_{k\\ge 2}$ and all other eigenvalues fixed"],
    conclusions=["$S(f)$ is nonincreasing in each generator eigenvalue $\\mu_k$, and strictly decreasing in $\\mu_k$ whenever $w_k > 0$",
                 "The same holds for the finite-horizon score $S_T(f) = \\int_0^T \\rho(\\tau)^2\\,d\\tau$."],
    statement_short="With weights fixed, SSA (and its finite-horizon version) decreases in every "
                    "generator eigenvalue.", tags=["monotonicity"])
env("PrP3", "proposition", "SSA for k well-separated equal-weight modes", "F10", main=True,
    rigor="semi_formal",
    assumptions=["$f$ has $k$ equally weighted, well-separated modes with all inter-mode barriers of common height $\\Delta U$",
                 "the $k-1$ slow eigenvalues are all approximately $\\mu_{\\mathrm{slow}} \\sim e^{-\\Delta U}$ and the slow-mode variance fraction is $(k-1)/k$"],
    conclusions=["$S(f) \\approx (k-1)^2 / (2 k^2 \\mu_{\\mathrm{slow}}) + O(1/\\mu_{\\mathrm{fast}})$",
                 "monotone in $\\Delta U$ and saturating at $1/(2\\mu_{\\mathrm{slow}})$ as $k \\to \\infty$"],
    statement_short="For k equal modes with common barrier, $S\\approx (k-1)^2/(2k^2\\mu_{slow})$: "
                    "growing with barrier height, saturating in k.", tags=["asymptotics"])
node("RP2", "remark", "SSA weighs slow modes by variance share",
     span("SSA summarizes slow-mode dynamics weighted by their variance", "must increase SSA."), 0.75,
     statement_short="SSA reflects slow modes weighted by variance share, not mode count; "
                     "monotonicity is only at fixed weights.")
node("DP9", "definition", "Empirical SSA estimator",
     span("We estimate SSA from $N$ trajectories with step-size",
          "at lag $\\tau_\\ell = \\ell\\,\\Delta t$."), 0.85,
     definiendum=["$\\widehat S$", "$L_{\\max}$", "$\\hat\\rho(\\tau_\\ell)$"])
env("EP4", "equation", "SSA estimator", "F11")
node("DP10", "definition", "Variance-scale stopping lag T_max",
     span("A principled stopping lag is the largest $\\tau$ at which",
          "(derivation in Appendix~\\ref{app:rho_clt})."), 0.85, definiendum="$T_{\\max}$",
     statement_short="Stop the SSA lag integral at the largest lag where $\\hat\\rho^2$ exceeds the "
                     "distribution-free null-variance bound $1/N$.")
env("EP5", "equation", "Stopping rule T_max", "F12", also_stated_at=[fact_text("F36")])

# ---- Section 5: DA
env("DP11", "definition", "Dominant Autocorrelation (DA) directions", "F13",
    definiendum="DA directions", genus="eigenvectors",
    differentia=["ordered by decreasing eigenvalue"])
env("PrP4", "proposition", "Convergence of the leading DA direction", "F14",
    assumptions=["$\\mu_2 < \\mu_3$", "$\\|\\alpha_2\\| > 0$"],
    conclusions=["the leading unit-norm eigenvector $v_1(\\tau)$ of $C(\\tau)$ satisfies $1 - \\langle v_1(\\tau), \\alpha_2\\rangle^2 / \\|\\alpha_2\\|^2 = O(e^{-2(\\mu_3 - \\mu_2)\\tau})$ as $\\tau \\to \\infty$"],
    statement_short="Under a gap $\\mu_2<\\mu_3$, DA1 aligns with $\\alpha_2$ at rate "
                    "$e^{-2(\\mu_3-\\mu_2)\\tau}$.", tags=["convergence"])
node("ClP1", "claim", "Subspace convergence of the top-m DA eigenspace",
     span("Assume $\\alpha_2, \\ldots, \\alpha_{m+1}$ are linearly independent and",
          "as $\\tau \\to \\infty$ (Appendix~\\ref{app:da_convergence_proof})."), 0.8,
     assumptions=["$\\alpha_2, \\ldots, \\alpha_{m+1}$ are linearly independent", "$\\mu_{m+1} < \\mu_{m+2}$"],
     conclusions=["the top-$m$ eigenspace of $C(\\tau)$ converges to $\\mathrm{span}(\\alpha_2, \\ldots, \\alpha_{m+1})$ as $\\tau \\to \\infty$"],
     tags=["convergence"])
node("OpenP1", "open_problem", "Recovery of individual slow modes by DA",
     span("Recovering the individual slow modes as the eigenvectors",
          "A theory is left to future work."), 0.65,
     statement_short="When do the individual DA eigenvectors $v_2,\\dots,v_m$ recover individual slow modes? "
                     "Not established; validated only empirically.")
env("TP2", "theorem", "Limit spectrum of the symmetrized lag-tau autocovariance under the isotropic Gaussian null", "F15",
    main=True,
    assumptions=["$f = \\mathcal{N}(0,\\sigma^2 I_d)$, $\\gamma = d/N$, and fix $\\tau > 0$",
                 "$(X_0^{(n)}, X_\\tau^{(n)})_{n=1}^N$ be independent stationary OU lag-pairs from the canonical diffusion of $f$",
                 "In the proportional regime $d, N \\to \\infty$ with $d/N \\to \\gamma \\in (0, \\infty)$"],
    conclusions=["the empirical spectral distribution of $\\widetilde C^{\\mathrm{sym}}(\\tau)$ converges weakly almost surely to",
                 "the boundary points of the continuous support are real roots of the discriminant quartic",
                 "on the continuous support, $\\tilde\\rho_\\tau^\\gamma(\\lambda) = -\\pi^{-1}\\,\\mathrm{Im}\\,G(\\lambda+i0^+)$, where $G$ is the lower-half-plane root of the Stieltjes cubic",
                 "At $\\tau = 0$, $\\mu_0^\\gamma$ is the standard Marchenko--Pastur law with edge $\\lambda_+(0) = \\sigma^2(1+\\sqrt\\gamma)^2$."],
    statement_short="Null ESD of the symmetrized lag-$\\tau$ cross-covariance: atom $\\max(0,1-2/\\gamma)$ plus a "
                    "density from a Stieltjes cubic, edges from its discriminant quartic, MP at $\\tau=0$.",
    tags=["random_matrix", "free_probability", "spectral_distribution"])
env("EP6", "equation", "Limit measure decomposition", "F16")
env("EP7", "equation", "Cubic coefficients a, b, c", "F17")
env("EP8", "equation", "Edge quartic", "F18")
env("EP9", "equation", "Stieltjes cubic", "F19")
node("ClP2", "claim", "Limit spectrum at tau = 0 is Marchenko-Pastur",
     span("At $\\tau = 0$, $\\mu_0^\\gamma$ is the standard Marchenko--Pastur law",
          "\\lambda_+(0) = \\sigma^2(1+\\sqrt\\gamma)^2$."), 0.8,
     assumptions=["At $\\tau = 0$"],
     conclusions=["$\\mu_0^\\gamma$ is the standard Marchenko--Pastur law with edge $\\lambda_+(0) = \\sigma^2(1+\\sqrt\\gamma)^2$"])
node("ClP3", "claim", "Upper edge as tau to infinity",
     span("As $\\tau \\to \\infty$, \\begin{equation} \\lambda_+(\\tau) \\to",
          "\\sqrt{\\sqrt{1+4\\gamma}-1}. \\label{eq:edge-tauinf-main} \\end{equation}"), 0.8,
     assumptions=["As $\\tau \\to \\infty$"],
     conclusions=["\\lambda_+(\\tau) \\to \\lambda_+(\\infty) = \\frac{\\sigma^2}{8}\\bigl(\\sqrt{1+4\\gamma}+3\\bigr)^{3/2}\\sqrt{\\sqrt{1+4\\gamma}-1}"])
env("EP10", "equation", "Upper edge lambda_+(infinity)", "F20", also_stated_at=[fact_text("F43")])
node("RP3", "remark", "Operational noise floor",
     span("Under the null $f = \\mathcal{N}(0, \\sigma^2 I_d)$ there are no slow",
          "Appendix~\\ref{app:sdxl_elderly}). "), 0.8,
     statement_short="$\\lambda_+(\\tau)$ serves as the DA noise floor; exact only for the simple-pair "
                     "estimator, so the pipeline is calibrated by a matched Monte-Carlo null.")
node("DP12", "definition", "Lag-selection criterion tau*(m)",
     span("For $m \\geq 1$ directions, choose $\\tau^*(m)$ as the largest lag at",
          "short lags (Appendix~\\ref{app:lag_selection})."), 0.85, definiendum="$\\tau^*(m)$",
     statement_short="$\\tau^*(m)$: the largest lag where the top-m eigenvalues beat the null (Bonferroni), "
                     "each projection rejects unimodality, and $\\rho<1/e$.")
node("DP13", "definition", "Number of metastable directions",
     span("The number of metastable directions recovered is the maximal $m$ for which",
          "$\\tau^*(m)$ exists."), 0.85, definiendum="number of metastable directions recovered")

# ---- Section 6: score oracles and algorithms
node("TP3", "theorem", "Tweedie's identity",
     span("For score-based generative models, Tweedie's identity", "no dimensionality barrier."),
     0.85, origin="external", cite="Tweedie's formula (standard, uncited)",
     assumptions=["score-based generative models", "at noise level $t$ with schedule variance $\\sigma_t^2$"],
     conclusions=["$\\nabla \\log f_t(x) = -\\epsilon_\\theta(x, t) / \\sigma_t$"],
     statement_short="The score of the noised marginal equals minus the predicted noise over $\\sigma_t$, "
                     "so a denoiser gives a score oracle.")
env("AP1", "algorithm", "SSA and DA from a Score Oracle", "F21", main=True,
    input=["$\\nabla \\log \\hat{f}$, samples from $f$, trajectories $N$, step $\\Delta t$, max steps $T$, lag grid $\\{\\tau_1 < \\cdots < \\tau_L\\}$"],
    output=["SSA score $\\hat S$; DA directions $\\{v_j, \\lambda_j\\}_{j=1}^d$"],
    statement_short="Simulate the canonical diffusion by Euler-Maruyama, estimate $\\hat C(\\tau)$ on a lag grid, "
                    "integrate $\\hat\\rho^2$ to the 1/N stop (SSA) and eigendecompose at $\\tau^*$ (DA).")

# ---- Appendix A
node("AssumP1", "assumption", "Regularity of f for uniqueness",
     span("We assume $f:\\mathbb{R}^d \\to (0,\\infty)$ is smooth",
          "integration by parts has no boundary terms."), 0.85)
node("DP14", "definition", "Generator of an Ito diffusion",
     span("Consider It\\^o diffusions on $\\mathbb{R}^d$ with generator",
          "$A(x) = \\Sigma(x)\\Sigma(x)^\\top$."), 0.8, origin="external", cite="standard (uncited)",
     definiendum=["$\\mathcal{L}$", "$A(x)$"])
env("PP1", "proof", "Proof of Theorem 1 (uniqueness)", "F23",
    statement_short="Constant $A_0$ in Fokker-Planck; reversibility means zero probability current, "
                    "which solves for the drift uniquely.", proof_strategy=["direct"])
env("RP4", "remark", "Necessity of both conditions", "F24",
    statement_short="Without reversibility add an f-divergence-free drift; without fixed $A_0$ every "
                    "$A(x)$ gives a different reversible diffusion.")
node("PP2", "proof", "Proof of Proposition 1 (similarity invariance)",
     span("Let $Y = cQX + b$. By change of variables", "Hence the spectra coincide."), 0.9,
     statement_short="Ito's lemma plus score and variance transformation rules give the canonical SDE for $Y$; "
                     "a unitary change of variables intertwines the generators.",
     proof_strategy=["direct", "algebraic_manipulation"])
node("RP5", "remark", "Why reversibility",
     span("A diffusion with stationary distribution $f$ is not unique in general",
          "of the dynamics."), 0.8,
     statement_short="Non-reversible drifts add circulating currents whose mixing depends on the drift, "
                     "not the barriers; reversibility removes them.")
node("RP6", "remark", "Why not A_0 = I_d",
     span("Consider a bimodal density $f$ in $\\mathbb{R}^d$ with modes at", "of~$f$."), 0.8,
     statement_short="With $A_0=I_d$ rescaling the data changes the drift-to-noise ratio and so SSA: "
                     "the measure would depend on units.")
node("RP7", "remark", "Why not A_0 = Cov_f(X)",
     span("Full-covariance whitening, $A_0 = \\mathrm{Cov}_f(X)$, is a natural alternative",
          "interpolates back toward the scalar convention."), 0.8,
     statement_short="Whitening gives affine invariance but needs $d(d+1)/2$ parameters and fails in the "
                     "sample-limited regime; the scalar choice is minimal.")

# ---- Appendix B
env("PP3", "proof", "Proof of Lemma 1 and of the spectral formula for SSA", "F25",
    statement_short="Expand the centered coordinates in the generator eigenbasis and apply the semigroup; "
                    "trace and integrate term by term.", proof_strategy=["direct", "algebraic_manipulation"])
env("EP11", "equation", "Conditional expectation expansion", "F26")
env("EP12", "equation", "SSA spectral formula (derivation)", "F27")
env("PrP5", "proposition", "Orthogonal Invariance", "F28",
    assumptions=["For any orthogonal $Q$"], conclusions=["$\\rho_{QY}(\\tau) = \\rho_Y(\\tau)$"],
    statement_short="The trace-normalized autocorrelation is unchanged by rotating the process.",
    tags=["invariance"])
env("PP4", "proof", "Proof of orthogonal invariance", "F29",
    statement_short="Cyclicity of the trace.", proof_strategy=["direct"])
node("RP8", "remark", "Why trace normalization",
     span("Collapsing the $d \\times d$ matrix $C(\\tau)$ to a scalar requires a choice.",
          "under isotropic rescaling of the data."), 0.8,
     statement_short="Trace (not Frobenius) aggregates modes linearly so slow modes persist in the integral; "
                     "normalizing by tr C(0) removes scale.")
node("RP9", "remark", "Why center by the population mean",
     span("The autocovariance $C(\\tau) = \\mathbb{E}_f[Y_\\tau Y_0^\\top]$ requires centering",
          "behavior for a metastability measure."), 0.8,
     statement_short="Per-trajectory centering erases the inter-mode signal of trapped trajectories; "
                     "population centering keeps it.")
node("RP10", "remark", "Why squaring the autocorrelation",
     span("Without squaring, the integrated autocorrelation", "rather than a single dominant one."), 0.8,
     statement_short="Integrating $\\rho$ gives an autocorrelation time dominated by $\\mu_2$; squaring adds "
                     "cross-terms that reward several slow barriers.")
env("PrP6", "proposition", "Monotonicity and Saturation of the spectral kernel", "F30",
    assumptions=["For any fixed $T > 0$", "$h(x) = (1 - e^{-xT})/x$"],
    conclusions=["strictly decreasing for $x > 0$", "$\\lim_{x \\to 0^+} h(x) = T$"])
env("PP5", "proof", "Proof of kernel monotonicity", "F31",
    statement_short="L'Hopital for the limit; sign of $h'$ via $e^z>1+z$.", proof_strategy=["direct"])
env("CP2", "corollary", "Metastable Variance Penalty", "F32",
    assumptions=["Fix $T > 0$ and weights $\\{w_k\\}$.",
                 "As $\\mu_k \\to 0$ for all $k \\in \\mathcal{K}_{\\text{slow}}$, with $\\mu_k$ for $k \\in \\mathcal{K}_{\\text{fast}}$ held fixed"],
    conclusions=["S_T(f) \\;=\\; T\\Big(\\textstyle\\sum_{k \\in \\mathcal{K}_{\\text{slow}}} w_k\\Big)^2 \\;+\\; O(1)"],
    statement_short="As slow eigenvalues vanish, $S_T \\approx T\\,(\\text{slow weight})^2$.")
env("PP6", "proof", "Proof of the metastable variance penalty", "F33",
    statement_short="Split the double sum into slow-slow, slow-fast and fast-fast blocks; the kernel limit gives "
                    "T on the first, $h\\le 1/x$ bounds the rest.", proof_strategy=["direct", "case_analysis"])
env("PP7", "proof", "Proof of Proposition 2 (SSA monotonicity)", "F34",
    statement_short="Differentiate the spectral formula term by term: every derivative is nonpositive, "
                    "the diagonal one strictly.", proof_strategy=["direct", "algebraic_manipulation"])
node("ClP5", "claim", "Canonical diffusion of a Gaussian is Ornstein-Uhlenbeck",
     span("For $f = \\mathcal{N}(0,\\Sigma)$ with eigenvalues",
          "{\\sum_i \\lambda_i}. \\]"), 0.75, rigor="semi_formal",
     assumptions=["$f = \\mathcal{N}(0,\\Sigma)$ with eigenvalues $\\lambda_1,\\ldots,\\lambda_d$ and scalar variance $\\sigma_f^2 = \\frac{1}{d}\\mathrm{tr}(\\Sigma)$"],
     conclusions=["the canonical diffusion is Ornstein--Uhlenbeck",
                  "stationary autocovariance $C(\\tau) = e^{-\\frac{\\sigma_f^2}{2}\\Sigma^{-1}\\tau}\\,\\Sigma$"],
     statement_short="For a Gaussian target the canonical diffusion is OU with "
                     "$C(\\tau)=e^{-\\sigma_f^2\\Sigma^{-1}\\tau/2}\\Sigma$.")
node("PP8", "proof", "Derivation of the isotropic Gaussian SSA baseline",
     span("For the isotropic case $\\Sigma = \\sigma^2 I_d$, the canonical diffusion",
          "leaving the autocorrelation structure invariant."), 0.75,
     statement_short="Isotropic OU: drift $-x/2$, conditional law at lag $\\tau$, so "
                     "$C(\\tau)=e^{-\\tau/2}\\sigma^2 I_d$.", proof_strategy=["direct"])
node("ClP6", "claim", "SSA baseline of the isotropic Gaussian equals one",
     span("The trace-normalized autocorrelation is $\\rho(\\tau) = e^{-\\tau/2}$",
          "\\text{as } T \\to \\infty. \\]"), 0.8,
     assumptions=["the isotropic case $\\Sigma = \\sigma^2 I_d$"],
     conclusions=["S_T(f) = \\int_0^T e^{-\\tau}\\,d\\tau = 1 - e^{-T} \\;\\to\\; 1 \\quad\\text{as } T \\to \\infty"],
     statement_short="For an isotropic Gaussian $\\rho(\\tau)=e^{-\\tau/2}$ and SSA $=1$.")
node("RP11", "remark", "Unimodal versus multimodal SSA contrast",
     span("This confirms that SSA introduces no spurious slow timescales",
          "while the unimodal value stays fixed at unity."), 0.8)
node("PP9", "proof", "Derivation of the asymptotic null distribution of rho-hat",
     span("Write $Y_n = X_0^{(n)} - \\bar x_f$ and",
          "drops toward $1$ as the spectrum concentrates on a single direction."), 0.75,
     statement_short="Delta method for the ratio of two sample means under independence of $X_0, X_\\tau$: "
                     "only the numerator variance $\\mathrm{tr}(\\Sigma_f^2)/N$ survives.",
     proof_strategy=["direct", "probabilistic"])
env("EP13", "equation", "Null CLT for rho-hat", "F35")
node("ClP4", "claim", "Distribution-free 1/N bound on the null variance of rho-hat",
     span("The asymptotic distribution \\eqref{eq:rho_clt} provides a null-variance scale",
          "\\label{eq:rho_clt_threshold} \\end{equation}"), 0.8,
     assumptions=["$d_{\\mathrm{eff}} \\geq 1$ for any $\\Sigma_f$"],
     conclusions=["the universal upper bound $\\mathrm{Var}[\\hat\\rho(\\tau)] \\leq 1/N$ holds without structural assumptions on $f$"],
     statement_short="Since $d_{eff}\\ge1$, the null variance of $\\hat\\rho$ is at most 1/N for any f, "
                     "giving the stopping rule.")
node("RP12", "remark", "Operational threshold versus alpha-level test",
     span("This is an operational threshold (squared autocorrelation exceeds",
          "already needed for normalization."), 0.8,
     statement_short="The 1/N rule is a variance-scale threshold, not an $\\alpha$-level test; sharper "
                     "plug-in thresholds use $d_{eff}$.")
node("RP13", "remark", "Scope of the trace CLT versus the DA noise floor",
     span("The CLT \\eqref{eq:rho_clt} holds for any fixed $d$", "object for DA's eigendecomposition."), 0.8,
     statement_short="The trace CLT (fixed d) serves SSA; the proportional-limit edge $\\lambda_+$ serves DA.")

# ---- Appendix C
env("PP10", "proof", "Proof of Proposition 4 (DA convergence) and subspace convergence", "F37",
    statement_short="Factor out $e^{-\\mu_2\\tau}$: a rank-one signal plus an exponentially small remainder, "
                    "then Davis-Kahan; the same for the top-m block.", proof_strategy=["direct"])
node("ClP7", "claim", "Bimodal heuristic: alpha_2 proportional to mu_A - mu_B",
     span("We give the derivation behind the bimodal example in",
          "proportional to the direction connecting mode centers."), 0.75, rigor="heuristic",
     assumptions=["for a strongly metastable bimodal density"],
     conclusions=["the linear summary $\\alpha_2$ of the slowest eigenfunction $\\psi_2$ is proportional to the direction connecting mode centers"])
node("PP11", "proof", "Derivation of the bimodal heuristic",
     span("Let $f = \\pi_A f_A + \\pi_B f_B$ where",
          "with a prefactor depending on $\\pi_A, \\pi_B$."), 0.75,
     statement_short="Approximate $\\psi_2$ as piecewise constant on the basins, fix the levels by orthogonality "
                     "to constants, and integrate.", proof_strategy=["direct"])
node("ClP8", "claim", "Leading DA direction of a bimodal target connects the mode centers",
     span("Combined with Proposition~\\ref{prop:da_convergence}, this shows that",
          "independently of how variance is distributed within each mode."), 0.8, rigor="heuristic",
     assumptions=["for a bimodal target"],
     conclusions=["the leading DA direction at large lag converges to the direction connecting mode centers, independently of how variance is distributed within each mode"])
node("TP4", "theorem", "Marchenko-Pastur law",
     span("For reference, the Marchenko--Pastur (MP) law", "atom for $\\gamma > 1$."), 0.9,
     origin="external", cite="Marchenko & Pastur 1967",
     assumptions=["$N$ i.i.d.\\ samples $x_n \\in \\mathbb{R}^d$ with $\\mathrm{Cov}(x) = \\sigma^2 I_d$",
                  "in the proportional limit $d,N \\to \\infty$, $d/N \\to \\gamma > 0$"],
     conclusions=["governs the limit eigenvalue distribution of the sample covariance $\\hat{\\Sigma} = \\frac{1}{N}\\sum_n x_n x_n^\\top$",
                  "plus a $(1 - 1/\\gamma)\\delta_0$ atom for $\\gamma > 1$"],
     tags=["random_matrix"])
node("PP12", "proof", "Proof of Theorem 2, outline (Appendix C.4)",
     span("This appendix proves Theorem~\\ref{thm:limit-spectrum} in three steps:",
          "departs from the exact simple-pair null."), 0.9,
     statement_short="Three steps: exact Wishart-difference decomposition, free additive convolution, "
                     "Stieltjes cubic and edge quartic.", proof_strategy=["algebraic_manipulation", "other"])
node("PP13", "proof", "Proof of Theorem 2, Step 1: exact Wishart-difference decomposition",
     span("The first step is a finite-$N$ rewriting of", "a deterministic function of $\\tau$. \\end{proof}"),
     0.85, statement_short="Rewrite $\\hat C^{sym}(\\tau)$ via an orthogonal rotation as a difference of two "
                           "independent Wisharts (Lemma 2).", proof_strategy=["construction"])
env("LP2", "lemma", "Exact decomposition of the symmetrized lag-tau autocovariance", "F38",
    assumptions=["$c_\\pm(\\tau) = (\\sigma^2/2)(1 \\pm e^{-\\tau/2})$"],
    conclusions=["there exist $d\\times N$ random matrices $U, V$ with i.i.d.\\ $\\mathcal N(0,1)$ entries, independent of each other",
                 "$\\hat C^{\\mathrm{sym}}(\\tau) \\stackrel{d}{=} c_+(\\tau)\\,W_+ - c_-(\\tau)\\,W_-$"],
    statement_short="$\\hat C^{sym}(\\tau)=c_+UU^\\top/N-c_-VV^\\top/N$ with independent Gaussian U, V.",
    tags=["random_matrix", "identity"])
env("EP14", "equation", "Wishart-difference decomposition", "F39")
env("PP14", "proof", "Proof of Lemma 2", "F40",
    statement_short="Rotate (sample, noise) by 45 degrees, then diagonalize the 2x2 coefficient matrix with "
                    "eigenvalues $\\sigma^2(\\alpha\\pm1)$.", proof_strategy=["algebraic_manipulation", "construction"])
node("DP15", "definition", "Stieltjes transform",
     span("For a compactly supported probability measure $\\mu$ on $\\mathbb{R}$,",
          "\\mathbb{C}\\setminus\\mathrm{supp}(\\mu)$."), 0.85, origin="external", cite="standard (uncited)",
     definiendum="$G_\\mu$")
node("DP16", "definition", "Empirical spectral distribution",
     span("For a self-adjoint $d \\times d$ matrix $X$, write", "for the limit (when it exists)."), 0.85,
     origin="external", cite="standard (uncited)", definiendum=["$\\mathrm{ESD}(X)$", "$\\mu_X$"])
node("TP5", "theorem", "Voiculescu's asymptotic-freeness theorem",
     span("Voiculescu's asymptotic-freeness theorem~\\cite{voiculescu1992,nica2006} guarantees that",
          "\\lim_{d\\to\\infty}\\,\\mathrm{ESD}(A+B). \\]"), 0.9, origin="external",
     cite="Voiculescu, Dykema, Nica 1992; Nica & Speicher 2006",
     assumptions=["$A, B$ be $d\\times d$ self-adjoint random matrices that are independent, with at least one of them orthogonally invariant in distribution"],
     conclusions=["$\\mathrm{ESD}(A+B)$ converges weakly almost surely to a measure on $\\mathbb{R}$, the \\emph{free additive convolution} of $\\mu_A$ and $\\mu_B$"],
     tags=["free_probability"])
node("DP17", "definition", "Compositional inverse K of the Stieltjes transform",
     span("Let $K_\\mu(z) = G_\\mu^{-1}(z)$ be the compositional inverse", "near $z=0$."), 0.85,
     origin="external", cite="standard (uncited)", definiendum="$K_\\mu$")
node("DP18", "definition", "R-transform",
     span("The $R$-transform is $R_\\mu(z) := K_\\mu(z) - 1/z$.", "K_\\mu(z) - 1/z$."), 0.9,
     origin="external", cite="Voiculescu 1992 (standard)", definiendum="$R$-transform")
node("TP6", "theorem", "Additivity and scaling of the R-transform",
     span("It is \\emph{additive} under free convolution", "$R_{-X}(z) = -R_X(-z)$."), 0.85,
     origin="external", cite="Voiculescu; Nica & Speicher 2006",
     conclusions=["$R_{A\\boxplus B}(z) = R_A(z) + R_B(z)$", "$R_{cX}(z) = c\\,R_X(cz)$, $R_{-X}(z) = -R_X(-z)$"],
     tags=["free_probability"])
node("TP7", "theorem", "R-transform of the Marchenko-Pastur law",
     span("The Marchenko--Pastur law has $R_{\\mathrm{MP}(\\gamma)}(z) = 1/(1 - \\gamma z)$",
          "~\\cite{marchenko1967, bai2010, nica2006}."), 0.85, origin="external",
     cite="Marchenko & Pastur 1967; Bai & Silverstein 2010; Nica & Speicher 2006",
     conclusions=["$R_{\\mathrm{MP}(\\gamma)}(z) = 1/(1 - \\gamma z)$"])
node("AP2", "algorithm", "Free-convolution recipe: from R-transforms back to a density",
     span("The three identities above give a procedure for deriving",
          "Eq.~\\eqref{eq:edge-quartic}). \\end{enumerate}"), 0.8,
     input=["$R_A, R_B$ are known"], output=["spectral distribution $\\mu_A \\boxplus \\mu_B$"],
     statement_short="Add R-transforms, invert $K=R+1/z$ to get the Stieltjes transform, then Stieltjes-invert; "
                     "edges from the discriminant.")
node("PP15", "proof", "Proof of Theorem 2, Step 2: asymptotic freeness and the atom",
     span("$W_+, W_-$ in Lemma~\\ref{lem:decomp} are independent standard Wisharts",
          "by a dominant-balance argument at $z = 0$ (not shown)."), 0.85,
     statement_short="The two Wisharts are asymptotically free, so the limit is a free convolution of scaled MP laws "
                     "with explicit R-transform; the atom rule gives mass $\\max(0,1-2/\\gamma)$.",
     proof_strategy=["other"])
env("EP15", "equation", "R-transform of the null limit", "F41")
node("PP16", "proof", "Proof of Theorem 2, Step 3: Stieltjes cubic and edge quartic",
     span("The compositional-inverse identity $K(G(\\lambda)) = \\lambda$ with",
          "is the largest real support edge."), 0.85,
     statement_short="Clear denominators in $K(G)=\\lambda$ to get the cubic; edges are double roots, i.e. zeros "
                     "of its discriminant, a quartic in $\\lambda$.", proof_strategy=["algebraic_manipulation"])
env("RP14", "remark", "Two regimes for tau > 0", "F42",
    statement_short="For $\\tau>0$ the limit has no atom when $\\gamma\\le2$ and an atom $1-2/\\gamma$ when "
                    "$\\gamma>2$; the cubic is the same.")
node("PP17", "proof", "Derivation of the tau = 0 boundary case",
     span("$c_-=0$, so $a\\equiv 0$ and the Stieltjes cubic collapses",
          "on $[\\lambda_-, \\lambda_+]$."), 0.75,
     statement_short="At $\\tau=0$, $c_-=0$ and the cubic reduces to the MP quadratic.",
     proof_strategy=["direct"])
node("PP18", "proof", "Derivation of the closed-form edge as tau to infinity",
     span("$c_+ = c_- = c := \\sigma^2/2$. The edge quartic becomes a biquadratic",
          "by symmetry."), 0.75,
     statement_short="With $c_+=c_-$ the quartic is biquadratic in $\\lambda$; factor with $s=\\sqrt{1+4\\gamma}$.",
     proof_strategy=["algebraic_manipulation"])
node("RP15", "remark", "Small-gamma semicircle approximation of the edge",
     span("For $\\gamma \\ll 1$ the $R$-transform", "it recovers $\\sigma^2\\sqrt{2\\gamma}$."), 0.75,
     rigor="heuristic",
     statement_short="For small $\\gamma$ the null bulk is near a semicircle, giving a closed-form approximation "
                     "of $\\lambda_+(\\tau)$.")
env("EP16", "equation", "Small-gamma edge approximation", "F44")
env("RP16", "remark", "Score-oracle scope", "F45",
    statement_short="Noise-floor calibration needs the score correct only on iso-Gaussian inputs; interpreting DA "
                    "directions needs it correct on f.")
node("RP17", "remark", "Scope of the analytic noise floor",
     span("Lemma~\\ref{lem:decomp} requires that the process whose autocovariance",
          "(applied in Appendix~\\ref{app:sdxl_elderly})."), 0.8,
     statement_short="Exact only for the canonical diffusion in native space with independent pairs; otherwise a "
                     "reference floor checked by matched Monte Carlo.")
node("CnjP1", "conjecture", "Universality of the null bulk-and-edge picture",
     span("We expect the bulk-and-spike picture it predicts", "inherits this robustness."), 0.65,
     assumptions=["broader distributions"],
     conclusions=["the bulk-and-spike picture it predicts to extend to broader distributions via Marchenko--Pastur universality"],
     statement_short="The analytic bulk and edge should extend to non-Gaussian targets by MP universality.")
node("OpenP2", "open_problem", "Spiked-model threshold and Tracy-Widom fluctuations for DA",
     span("Two natural extensions remain for future work:", "explicit false-positive rate."), 0.65,
     statement_short="Open: a BBP-type detection threshold for slow modes and Tracy-Widom edge fluctuations "
                     "of the free-convolution null.")
node("ClP9", "claim", "Valid lag window for recovering m DA directions",
     span("For recovering $m$ DA directions, the valid window is",
          "is the first to fall below the noise floor as $\\tau$ grows."), 0.75, rigor="heuristic",
     conclusions=["\\frac{1}{\\mu_{m+2} - \\mu_{m+1}} \\;\\ll\\; \\tau \\;\\ll\\; \\frac{\\log N}{2\\mu_{m+1}}"],
     statement_short="Lags must be long enough to suppress fast modes and short enough that the m-th slow "
                     "eigenvalue stays above the floor.")
node("DP19", "definition", "Relaxation time of the OU process",
     span("The threshold is taken from the OU convention~\\cite{Pavliotis2014}:",
          "filtering directions that have not yet decayed."), 0.8, origin="external",
     cite="Pavliotis 2014", definiendum="relaxation time $\\tau_c$")
node("DP20", "definition", "Appendix lag-selection rule",
     span("The selection rule is: choose $\\tau^*(m)$ as the largest lag at",
          "all exceed $\\lambda_+(\\tau)$ and $\\rho(\\tau) < 1/e$."), 0.75, definiendum="$\\tau^*(m)$",
     statement_short="Choose the largest lag where the top-m eigenvalues exceed $\\lambda_+(\\tau)$ and "
                     "$\\rho<1/e$.")
node("RP18", "remark", "Insufficient lag budget",
     span("The selection rule succeeds when the window", "DA separates cleanly from PCA at $\\tau^*$ in every case."),
     0.8, statement_short="If the lag window is empty DA stays close to PCA; check that DA and PCA separate, "
                          "or raise N.")
env("AP3", "algorithm", "Operational Noise Floor via Matched-Pipeline Monte Carlo", "F46",
    input=["data samples $\\{x_n\\}_{n=1}^N$, lag $\\tau^*$, replicates $B$, pipeline $\\mathcal{P}$ (score estimator, canonical diffusion simulator, optional embedding)"],
    output=["empirical null distribution $\\{\\lambda_i^{(b)}\\}_{b=1}^B$ for each $i$"],
    statement_short="Draw covariance-matched Gaussian null samples, rerun the whole pipeline B times and "
                    "threshold observed eigenvalues at the null $(1-\\alpha)$-quantile.")
node("DP21", "definition", "Hartigan's dip statistic",
     span("Hartigan's dip statistic $D$~\\cite{hartigan1985} measures",
          "departure from unimodality of an empirical CDF."), 0.85, origin="external",
     cite="Hartigan & Hartigan 1985", definiendum="Hartigan's dip statistic $D$")
node("ExP1", "example", "Planted slow subspace",
     span("Fix $d = 200$ ambient dimensions and $k = 20$ planted metastable axes.",
          "no equilibration is needed."), 0.8,
     statement_short="A d=200 density with k=20 randomly rotated double-well axes and matched per-axis variance, "
                     "so PCA has no preferred direction.")

# ---- Appendix D
node("DP22", "definition", "Reversible diffusion with diffusion matrix A_0",
     span("Fix any constant positive-definite $A_0 \\in \\mathbb{R}^{d \\times d}$.",
          "A_0^{1/2}\\,dW_t. \\]"), 0.8, definiendum="reversible It\\^o diffusion with diffusion matrix $A_0$")
node("DP23", "definition", "Generator L_{A_0} and its spectrum",
     span("Its infinitesimal generator", "\\mu_3(A_0) \\le \\cdots$."), 0.8,
     definiendum=["$\\mathcal{L}_{A_0}$", "$\\mu_k(A_0)$"])
env("PrP7", "proposition", "Eigenvalue ratio bound across diffusion matrices", "F48",
    assumptions=["For any two constant positive-definite diffusion matrices $A, B \\in \\mathbb{R}^{d\\times d}$ and every $k \\ge 1$"],
    conclusions=["\\lambda_{\\min}\\!\\bigl(B^{-1/2} A B^{-1/2}\\bigr)\\,\\mu_k(B) \\;\\le\\; \\mu_k(A) \\;\\le\\; \\lambda_{\\max}\\!\\bigl(B^{-1/2} A B^{-1/2}\\bigr)\\,\\mu_k(B)"],
    statement_short="Generator eigenvalues for two diffusion matrices differ by at most the extreme eigenvalues of "
                    "$B^{-1/2}AB^{-1/2}$.", tags=["bound", "spectral"])
env("PP19", "proof", "Proof of the eigenvalue ratio bound", "F49",
    statement_short="Compare the Dirichlet forms pointwise and apply the Courant-Fischer min-max principle.",
    proof_strategy=["direct"])
node("ClP10", "claim", "Scalar diffusion matrix rescales the spectrum",
     span("For $A_0 = c\\,I_d$ scalar, all eigenvalues scale by $c$ exactly.",
          "(Proposition~\\ref{prop:similarity_invariance})."), 0.8,
     assumptions=["$A_0 = c\\,I_d$ scalar"],
     conclusions=["all eigenvalues scale by $c$ exactly", "SSA scales as $1/c$", "DA directions are independent of $c$"])
node("ClP11", "claim", "Slow-mode orderings preserved across diffusion matrices",
     span("For $A_0$ general positive-definite, eigenvalue ratios", "dominates the $A_0$-dependent prefactors."),
     0.7, rigor="heuristic",
     assumptions=["$A_0$ general positive-definite", "In the metastable regime"],
     conclusions=["slow-mode orderings $\\mu_k(f_A) \\lessgtr \\mu_k(f_B)$ across densities are preserved asymptotically whenever the barrier-height gap dominates the $A_0$-dependent prefactors"])
node("ClP12", "claim", "Bimodal leading DA direction is independent of A_0",
     span("DA directions depend on $A_0$ in general.", "for any $A_0$ in this regime."), 0.7,
     rigor="heuristic",
     assumptions=["In the strongly-metastable bimodal limit"],
     conclusions=["The leading DA direction therefore converges to the inter-mode direction $\\mu_A - \\mu_B$ for any $A_0$ in this regime."])
node("DP24", "definition", "Underdamped Langevin dynamics",
     span("Real physical systems (proteins, peptides, biomolecules in solvent)",
          "$U(q) = -\\beta^{-1}\\log f(q)$."), 0.85, origin="external", cite="standard (uncited)",
     definiendum="underdamped Langevin dynamics")
env("EP17", "equation", "Underdamped Langevin SDE", "F50")
node("DP25", "definition", "Slow relaxation rates mu^UD and mu^OD",
     span("We write $\\mu_k^{\\rm UD}(\\eta, \\beta)$ for its slow real relaxation rates",
          "overdamped canonical diffusion attached to $f$."), 0.85,
     definiendum=["$\\mu_k^{\\rm UD}(\\eta, \\beta)$", "$\\mu_k^{\\rm OD}(f)$"])
env("PrP8", "proposition", "Smoluchowski limit", "F51", conf=0.9, origin="external",
    cite="Pavliotis & Stuart 2008; Pavliotis 2014",
    assumptions=["As $\\eta \\to \\infty$"],
    conclusions=["the time-rescaled position trajectory $q_{\\eta t}$ of the underdamped Langevin equation~\\eqref{eq:underdamped} converges weakly to an overdamped Langevin diffusion with stationary marginal $f$ and a constant diffusion matrix determined by $M$ and $\\beta$"],
    statement_short="High-friction underdamped Langevin converges to an overdamped diffusion sharing the "
                    "canonical diffusion's barrier exponents.")
node("TP8", "theorem", "Eyring-Kramers asymptotics",
     span("Standard Eyring--Kramers theory~\\cite{kramers1940,bovier_dh2015,nelson1967}",
          "with a different prefactor."), 0.85, origin="external",
     cite="Kramers 1940; Bovier & den Hollander 2015; Nelson 1967",
     assumptions=["a metastable density $f$ with a finite collection of well-separated basins (well-defined saddle structure, non-degenerate quadratic minima and saddles)",
                  "at fixed positive $\\eta$ and $M$"],
     conclusions=["\\mu_k^{\\rm UD}(\\eta, \\beta;\\, f) \\;\\sim\\; \\kappa_k(\\eta, M;\\, f)\\,\\exp\\!\\bigl(-\\beta\\,\\Delta U_k(f)\\bigr) \\quad \\text{as } \\beta \\to \\infty",
                  "The same form holds for the overdamped rates $\\mu_k^{\\rm OD}$ with a different prefactor."],
     statement_short="Slow rates are a prefactor times $\\exp(-\\beta\\Delta U_k)$ with barrier heights fixed by f.")
node("CP3", "corollary", "Asymptotic ordering implication for kinetic dynamics",
     span("For two densities $f_A, f_B$ with non-degenerate barrier-height ordering at index $k$,",
          "matches the corresponding overdamped sign."), 0.8, rigor="semi_formal",
     assumptions=["two densities $f_A, f_B$ with non-degenerate barrier-height ordering at index $k$",
                  "in the deep-barrier limit $\\beta\\,|\\Delta U_k(f_A) - \\Delta U_k(f_B)| \\to \\infty$ (at fixed $\\eta, M$)"],
     conclusions=["the sign of $\\mu_k^{\\rm UD}(f_A) - \\mu_k^{\\rm UD}(f_B)$ is determined by the barrier-height comparison and matches the corresponding overdamped sign"],
     statement_short="In the deep-barrier limit underdamped and overdamped dynamics order slow rates the same way.")
node("PP20", "proof", "Derivation sketch of the kinetic ordering implication",
     span("The Eyring--Kramers form gives $\\mu_k^{\\rm UD}(\\eta, \\beta;\\, f) \\sim",
          "The same applies to $\\mu_k^{\\rm OD}$ via the Smoluchowski limit."), 0.85,
     statement_short="Ratio of Eyring-Kramers rates: finite prefactor ratio, diverging exponent.",
     proof_strategy=["direct"])
node("RP19", "remark", "Consequence for slow-mode orderings",
     span("For \\emph{leading exponential escape rates}, the deep-barrier asymptotic predicts",
          "(alanine dihedrals at 300\\,K)."), 0.8)
node("RP20", "remark", "Algorithmic relation of DA to TICA",
     span("DA and TICA differ in the eigenvalue-problem formulation", "a natural direction for future work."),
     0.8, statement_short="DA solves $C(\\tau)v=\\lambda v$ (variance-weighted), TICA "
                          "$C(\\tau)v=\\lambda C(0)v$; they coincide for $A_0=\\mathrm{Cov}_f$.")
node("CnjP2", "conjecture", "Non-asymptotic underdamped/overdamped rate comparison",
     span("Without taking limits, comparing $\\eta\\,\\mu_k^{\\rm UD}(\\eta, \\beta)$",
          "we leave it to follow-up work."), 0.65,
     conclusions=["\\Bigl|\\,\\eta\\,\\mu_k^{\\rm UD}(\\eta, \\beta;\\, f) \\,/\\, \\mu_k^{\\rm OD}(f) \\;-\\; 1\\,\\Bigr| \\;\\le\\; C_1/\\eta^2 \\;+\\; C_2\\,e^{-\\beta\\,\\Delta U_k(f)}"],
     statement_short="A relative-error bound $C_1/\\eta^2+C_2e^{-\\beta\\Delta U_k}$ between scaled underdamped and "
                     "overdamped rates is plausible but unproven.")

# ---- Appendix E
node("PP21", "proof", "Derivation of the Tweedie identity",
     span("A diffusion model defines a forward noising process",
          "\\nabla \\log f_t(x) = -\\frac{\\epsilon_\\theta(x, t)}{\\sigma_t}. \\]"), 0.85,
     statement_short="Bayes' rule gives the score through the posterior mean; substituting the denoiser's "
                     "estimate of $x_0$ yields $-\\epsilon_\\theta/\\sigma_t$.", proof_strategy=["direct"])
node("RP21", "remark", "Recovery of the data score as t to 0",
     span("As $t \\to 0$, $\\sigma_t \\to 0$ and $\\sqrt{\\bar\\alpha_t} \\to 1$",
          "first discrete timestep of a standard linear schedule ($\\sigma_1 \\approx 0.01$)."), 0.75,
     rigor="semi_formal",
     statement_short="At small noise the Tweedie score approximates $\\nabla\\log f$ with one denoiser pass.")
node("RP22", "remark", "Iso-Gaussian null via large-t score evaluation",
     span("The same trained denoiser provides a self-contained iso-Gaussian score",
          "(details in Appendix~\\ref{app:sdxl_elderly})."), 0.75, rigor="heuristic",
     statement_short="At large noise the same denoiser gives the linear iso-Gaussian score, running the null "
                     "through the full pipeline.")

# ---- Appendix I
node("ClP13", "claim", "T-stability of fixed-profile SSA rankings",
     span("For comparisons of the fixed-spectral-profile kind covered by",
          "increasing $T$ can only widen the gap."), 0.75, rigor="semi_formal",
     assumptions=["comparisons of the fixed-spectral-profile kind covered by Proposition~\\ref{prop:ssa_monotonicity} (one density's spectral profile dominates another's term-by-term)"],
     conclusions=["$S_A(T) > S_B(T)$ for every $T > 0$", "increasing $T$ can only widen the gap"],
     also_stated_at=[span("By Proposition~\\ref{prop:ssa_monotonicity}, in fixed-spectral-profile comparisons",
                          "the gap between scores can only widen as $T_{\\max}$ grows.")[0]],
     statement_short="If one spectral profile dominates another term by term, its finite-horizon SSA is larger at "
                     "every horizon, with a widening gap.")

# =============================================================== PROOF STEPS
q = 1
q = steps("PP1", [
    ("For a general diffusion with $A(x)\\equiv A_0$ constant", "+ \\frac{1}{2}\\,\\nabla \\cdot \\big(A_0 \\nabla p(x,t)\\big). \\]",
     "setup", "Fokker-Planck equation", "Write the Fokker-Planck equation for constant $A_0$."),
    ("Define the probability current", "requires $\\nabla \\cdot J_f(x) = 0$.",
     "introduce_variable", "Probability current", "Define the probability current; stationarity means zero divergence."),
    ("Reversibility with respect to $f$ is equivalent", "see~\\cite[Ch.~4]{Pavliotis2014}).",
     "apply_lemma", "Reversibility as zero current", "Reversibility is equivalent to vanishing current (cited)."),
    ("With $A(x)\\equiv A_0$ and $J_f\\equiv 0$, we have", "drift and hence the diffusion.",
     "conclude", "Solve for the drift", "Zero current solves to $b=\\tfrac12A_0\\nabla\\log f$."),
], q)
q = steps("PP2", [
    ("Let $Y = cQX + b$. By change of variables", "c^{-1} Q^\\top (y - b)\\right). \\]",
     "introduce_variable", "Density of Y", "Change of variables for the density of $Y$."),
    ("Applying It\\^o's lemma to $Y_t = cQX_t + b$ yields", "c \\sigma_f\\, Q\\,dW_t. \\]",
     "apply_lemma", "Ito's lemma", "Apply Ito's lemma to the affine map."),
    ("The scalar variance of $Y$ is", "This is exactly the canonical diffusion for $f_Y$.",
     "substitute", "Transform variance and score", "Substitute the transformed variance and score: canonical SDE for $f_Y$."),
    ("The change-of-variables map", "Hence the spectra coincide.",
     "conclude", "Unitary intertwining", "A unitary map intertwines the generators, so spectra agree."),
], q)
q = steps("PP3", [
    ("Let $P_\\tau = e^{\\tau\\mathcal{L}_f}$ denote the Markov semigroup", "\\label{eq:cond_exp_expansion} \\end{equation}",
     "setup", "Eigen-expansion of coordinates", "Expand centered coordinates in the eigenbasis and apply the semigroup."),
    ("\\textit{(i)} Writing the expectation", "C(\\tau) = \\sum_{k \\geq 2} e^{-\\mu_k \\tau}\\,\\alpha_k\\,\\alpha_k^\\top. \\]",
     "algebraic_manipulation", "Part (i): autocovariance", "Tower property and the expansion give $C(\\tau)$."),
    ("\\textit{(ii)} Taking the trace of (i)", "{\\sum_{j \\geq 2}\\|\\alpha_j\\|^2}. \\]",
     "algebraic_manipulation", "Part (ii): autocorrelation", "Trace and normalize to get $\\rho(\\tau)$."),
    ("\\textit{(iii) Spectral formula for SSA", "which is the spectral formula of Corollary~\\ref{thm:ssa_spectral}.",
     "conclude", "Part (iii): spectral formula", "Square and integrate term by term."),
], q)
q = steps("PP6", [
    ("Partition the double sum in~\\eqref{eq:ST_spectral}", "where $h(x) = (1-e^{-xT})/x$.",
     "case_split", "Partition into blocks", "Split the double sum into slow-slow, slow-fast, fast-fast blocks."),
    ("For $(k,\\ell) \\in \\mathcal{K}_{\\text{slow}}^2$", "= T\\big(\\sum_{k \\in \\mathcal{K}_{\\text{slow}}} w_k\\big)^2$.",
     "apply_lemma", "Slow block limit", "The kernel limit $h\\to T$ gives the slow block."),
    ("For $B$ and $C$, at least one index is fast.", "giving $B, C = O(1)$.",
     "bound_estimate", "Fast blocks bounded", "Bound the other blocks by $h(x)\\le1/x$."),
    ("Hence $S_T(f) = T\\big(", "in the stated limit.",
     "conclude", "Conclude", "Combine the blocks."),
], q)
q = steps("PP7", [
    ("For the infinite-horizon score $S(f) =", "Terms not involving $k$ are independent of $\\mu_k$.",
     "setup", "Fix an index", "Fix k; only terms with k depend on $\\mu_k$."),
    ("For off-diagonal terms", "\\;\\leq\\; 0. \\]",
     "algebraic_manipulation", "Off-diagonal derivatives", "Off-diagonal derivatives are nonpositive."),
    ("For the diagonal term $i = j = k$,", "-\\frac{w_k^2}{2\\mu_k^2} \\;\\leq\\; 0. \\]",
     "algebraic_manipulation", "Diagonal derivative", "The diagonal derivative is nonpositive."),
    ("All terms are nonpositive, so the sum is nonincreasing", "(the diagonal term then has strict negative derivative).",
     "bound_estimate", "Monotonicity of S", "Sum of nonpositive derivatives; strict when $w_k>0$."),
    ("The same argument applies to the finite-horizon score", "in $x > 0$.",
     "conclude", "Finite horizon", "Repeat with the strictly decreasing kernel $h_T$."),
], q)
q = steps("PP8", [
    ("For the isotropic case $\\Sigma = \\sigma^2 I_d$, the canonical diffusion", "as expected from similarity invariance (Proposition~\\ref{prop:similarity_invariance}).",
     "substitute", "Isotropic OU process", "Specialize to the isotropic OU process with drift $-x/2$."),
    ("The conditional distribution at lag $\\tau$ is:", "and DA applied to the population autocovariance would find no distinguished direction.",
     "algebraic_manipulation", "Autocovariance is scalar", "Conditional law gives $C(\\tau)=e^{-\\tau/2}\\sigma^2I_d$."),
    ("Crucially, the decay rate $e^{-\\tau/2}$ is independent of $\\sigma^2$.", "leaving the autocorrelation structure invariant.",
     "conclude", "Scale independence", "The decay rate does not depend on $\\sigma^2$."),
], q)
q = steps("PP9", [
    ("Write $Y_n = X_0^{(n)} - \\bar x_f$ and", "B_N := \\mathrm{tr} \\hat C(0). \\]",
     "introduce_variable", "Setup", "Write $\\hat\\rho$ as a ratio $A_N/B_N$ of sample means."),
    ("Each summand $Z_n := Y_n^\\top Y_n'", "$\\mathrm{Var}[A_N] = \\mathrm{tr}(\\Sigma_f^2)/N$.",
     "algebraic_manipulation", "Numerator moments", "Under independence the numerator has mean 0 and variance tr$(\\Sigma_f^2)/N$."),
    ("The denominator $B_N = \\mathrm{tr} \\hat C(0) = \\tfrac{1}{N}\\sum_n", "at the $1/\\sqrt{N}$ rate.",
     "bound_estimate", "Denominator moments", "The denominator concentrates at tr$\\Sigma_f$."),
    ("The denominator $B_N$ has mean $\\mathrm{tr}\\Sigma_f$ and variance", "\\label{eq:rho_clt} \\end{equation}",
     "apply_lemma", "CLT and delta method", "Multivariate CLT and delta method at $(0,\\mathrm{tr}\\Sigma_f)$."),
    ("The asymptotic variance is $\\nabla g^\\top \\Sigma_T \\nabla g$", "= 1/d_{\\mathrm{eff}}$.",
     "algebraic_manipulation", "Asymptotic variance", "Off-diagonal covariance vanishes; variance is $1/d_{eff}$."),
    ("Equivalently, $\\mathrm{Var}[\\hat\\rho(\\tau)] \\approx", "concentrates on a single direction.",
     "conclude", "Participation ratio", "Variance $\\approx 1/(Nd_{eff})$ with $d_{eff}\\in[1,d]$."),
], q)
q = steps("PP10", [
    ("Starting from Lemma~\\ref{lem:spectral}(i), factor out", "_{R(\\tau)}\\bigg]. \\]",
     "algebraic_manipulation", "Factor out the dominant exponential", "Write $C(\\tau)$ as $e^{-\\mu_2\\tau}$ times rank-one plus remainder."),
    ("Since $\\mu_k \\geq \\mu_3$ for all $k \\geq 3$", "and eigenvector $\\alpha_2/\\|\\alpha_2\\|$.",
     "bound_estimate", "Remainder bound", "Bound the remainder by $e^{-(\\mu_3-\\mu_2)\\tau}$."),
    ("For sufficiently large $\\tau$, $\\|R(\\tau)\\| < \\|\\alpha_2\\|^2$", "- \\|R(\\tau)\\|}\\right)^2. \\]",
     "apply_lemma", "Davis-Kahan", "Eigengap and Davis-Kahan bound the angle."),
    ("As $\\tau \\to \\infty$, $\\|R(\\tau)\\| \\to 0$ and the denominator", "$O(e^{-2(\\mu_3 - \\mu_2)\\tau})$.",
     "conclude", "Rate", "The bound decays as $e^{-2(\\mu_3-\\mu_2)\\tau}$."),
    ("The same factorization extends to subspace level.", "Appendix~\\ref{app:validation}).",
     "other", "Subspace convergence", "Same argument for the top-m block.", [
         ("The same factorization extends to subspace level.", "\\alpha_k\\alpha_k^\\top$.",
          "setup", "Slow block", "Linear independence lower-bounds the slow block's m-th eigenvalue."),
         ("Splitting the bracket into this slow block and a tail", "\\sum_{k \\geq m+2}\\|\\alpha_k\\|^2$.",
          "bound_estimate", "Tail bound", "Bound the tail."),
         ("Applying the Davis--Kahan $\\sin\\Theta$ theorem to the gap", "$\\mathrm{span}(\\alpha_2, \\ldots, \\alpha_{m+1})$.",
          "apply_lemma", "Davis-Kahan for subspaces", "Davis-Kahan gives the projector bound."),
         ("The bound controls the \\emph{subspace} only;", "Appendix~\\ref{app:validation}).",
          "other", "Limits of the bound", "Individual eigenvectors are not identified; checked empirically."),
     ]),
], q)
q = steps("PP11", [
    ("Let $f = \\pi_A f_A + \\pi_B f_B$ where", "of support of $f_A$ and $f_B$, respectively).",
     "introduce_variable", "Two-basin mixture", "Set up a two-basin mixture."),
    ("In the strongly metastable limit, the slowest eigenfunction", "basins and is otherwise constant.",
     "apply_lemma", "Piecewise-constant psi_2", "The slowest eigenfunction is approximately constant on each basin (cited)."),
    ("Since $\\psi_1 \\equiv 1$ and $\\langle \\psi_1, \\psi_2 \\rangle_f = 0$,", "write $c := c_A$.",
     "algebraic_manipulation", "Levels by orthogonality", "Orthogonality to constants fixes the two levels."),
    ("By definition, $(\\alpha_2)_j =", "\\alpha_2 \\approx \\tfrac{c}{2}(\\mu_A - \\mu_B). \\]",
     "algebraic_manipulation", "Compute alpha_2", "Split the integral over basins."),
    ("That is, $\\alpha_2$ is aligned with the vector connecting", "with a prefactor depending on $\\pi_A, \\pi_B$.",
     "conclude", "Conclude", "$\\alpha_2$ points along $\\mu_A-\\mu_B$."),
], q)
q = steps("PP12", [
    ("This appendix proves Theorem~\\ref{thm:limit-spectrum} in three steps:", "scope and empirical verification in Section~\\ref{app:scope}.",
     "setup", "Outline", "Outline of the three-step proof."),
    ("The proof analyses the simple-pair estimator", "departs from the exact simple-pair null.",
     "setup", "Estimator scope", "The proof is for the simple-pair estimator only."),
], q)
q = steps("PP13", [
    ("The first step is a finite-$N$ rewriting of", "independent-ensemble representation.",
     "setup", "Why a rotation is needed", "The naive decomposition shares $X_0$; a rotation gives independent ensembles."),
    ("\\begin{lemma}[Exact decomposition", "a deterministic function of $\\tau$. \\end{proof}",
     "setup", "Lemma 2 and its proof", "State and prove the exact decomposition."),
], q)
q = steps("PP14", [
    ("Standardize $X_0^{(n)} = \\sigma\\tilde X^{(n)}$", "\\beta\\sigma\\bigl(Z\\tilde X^\\top + \\tilde X Z^\\top\\bigr). \\]",
     "setup", "Standardize", "Write $2N\\hat C^{sym}$ in standardized sample and noise matrices."),
    ("\\emph{Intermediate change of basis.}", "\\bigl(AB^\\top + BA^\\top\\bigr). \\]",
     "introduce_variable", "45-degree rotation", "Rotate to $A,B$ and expand."),
    ("\\emph{Diagonalization.}", "a deterministic function of $\\tau$.",
     "conclude", "Diagonalize", "Diagonalize the 2x2 coefficient matrix to get $U,V$."),
], q)
q = steps("PP15", [
    ("$W_+, W_-$ in Lemma~\\ref{lem:decomp} are independent standard Wisharts", "with $d/N \\to \\gamma \\in (0, \\infty)$.",
     "apply_lemma", "Asymptotic freeness", "Independent orthogonally invariant Wisharts are asymptotically free."),
    ("Consequently $\\mathrm{ESD}(\\hat C^{\\mathrm{sym}}(\\tau))$ converges", "\\label{eq:R-explicit-appendix} \\end{equation}",
     "invoke_identity", "R-transform of the limit", "The limit is a free convolution with explicit R-transform."),
    ("The standard Marchenko--Pastur measure $\\mathrm{MP}(\\gamma)$ has a", "when $d > N$~\\cite{marchenko1967, bai2010}.",
     "setup", "MP atom", "Recall the MP atom."),
    ("Free additive convolution combines atoms via the rule", "$\\max(0, p + q - 1)$ at $a + b$.",
     "setup", "Atom rule", "Recall the free-convolution atom rule (cited)."),
    ("Applied to $(c_+\\,\\mathrm{MP}(\\gamma))", "continues to hold for all $\\gamma > 0$.",
     "algebraic_manipulation", "Atom mass", "The atom has mass $\\max(0,1-2/\\gamma)$."),
    ("The formal identity $R_{\\mathrm{MP}(\\gamma)}(z) = 1/(1-\\gamma z)$ is valid", "of Theorem~\\ref{thm:limit-spectrum}.",
     "other", "Validity for all gamma", "The formal R-transform is valid for every $\\gamma$; recovers the decomposition."),
    ("The rank-deficiency argument has a direct finite-$N$ counterpart:", "(not shown).",
     "other", "Finite-N rank check", "Rank at most 2N matches the atom mass."),
], q)
q = steps("PP16", [
    ("The compositional-inverse identity $K(G(\\lambda)) = \\lambda$ with", "\\;=\\; \\lambda. \\]",
     "invoke_identity", "Inverse identity", "Write $K(G)=\\lambda$ explicitly."),
    ("Multiplying through by $G(1 - c_+\\gamma G)(1 + c_-\\gamma G)$", "and the constant term is $1$.",
     "algebraic_manipulation", "Cubic", "Clear denominators: the Stieltjes cubic."),
    ("Density on the interior of the support follows", "= -\\pi\\rho(\\lambda)$.",
     "apply_lemma", "Density", "Sokhotski-Plemelj gives the density."),
    ("Edges are points at which the complex-conjugate pair", "of Theorem~\\ref{thm:limit-spectrum}(i).",
     "invoke_identity", "Edges as discriminant zeros", "Edges are double roots: discriminant zero."),
    ("Expanding as a polynomial in $\\lambda$:", "and $c_++c_- = \\sigma^2$.",
     "algebraic_manipulation", "Leading coefficient", "The quartic has leading coefficient $\\gamma^2\\sigma^4$."),
    ("Depending on $(\\gamma, \\tau)$, the quartic", "is the largest real support edge.",
     "conclude", "Support structure", "Two or four real roots: one or two support intervals."),
], q)
q = steps("PP18", [
    ("$c_+ = c_- = c := \\sigma^2/2$. The edge quartic becomes", "with discriminant $(1+4\\gamma)^3$.",
     "substitute", "Biquadratic", "With $c_+=c_-$ the quartic is biquadratic."),
    ("Setting $s = \\sqrt{1+4\\gamma}$ and", "by symmetry.",
     "conclude", "Closed form", "Factor and take the positive root."),
], q)
q = steps("PP19", [
    ("The Dirichlet form associated with $\\mathcal{L}_{A_0}$ is", "of zero-mean functions.",
     "introduce_variable", "Dirichlet form", "Introduce the Dirichlet form."),
    ("For any test function $\\varphi$ in this domain,", "of $B^{-1/2} A B^{-1/2}$.",
     "bound_estimate", "Pointwise comparison", "Compare the quadratic forms pointwise."),
    ("Integrating against $f\\,dx$,", "\\,\\mathcal{E}_B(\\varphi). \\]",
     "bound_estimate", "Integrated comparison", "Integrate to compare Dirichlet forms."),
    ("The min-max characterization of the $k$-th non-trivial eigenvalue,", "gives the stated bound term-by-term.",
     "conclude", "Min-max", "Courant-Fischer transfers the bound to eigenvalues."),
], q)
q = steps("PP20", [
    ("The Eyring--Kramers form gives $\\mu_k^{\\rm UD}", "as $\\beta \\to \\infty$.",
     "apply_lemma", "Eyring-Kramers form", "Apply the Eyring-Kramers asymptotics."),
    ("Taking the ratio of the rates for $f_A$ and $f_B$,", "in the deep-barrier limit.",
     "bound_estimate", "Ratio of rates", "Finite prefactor ratio, diverging exponent."),
    ("The same applies to $\\mu_k^{\\rm OD}$ via the Smoluchowski limit.", "via the Smoluchowski limit.",
     "conclude", "Overdamped case", "Same for overdamped rates."),
], q)
q = steps("PP21", [
    ("A diffusion model defines a forward noising process", "f_t(x) = \\int q(x \\mid x_0) f(x_0)\\, dx_0. \\]",
     "setup", "Forward process", "Forward noising kernel and marginal."),
    ("Using Bayes' rule to express the posterior", "{\\sigma_t^2}. \\]",
     "invoke_identity", "Score via posterior mean", "Bayes' rule: score through the posterior mean."),
    ("One can notice that any sample from this kernel", "{\\sqrt{\\bar\\alpha_t}}. \\]",
     "introduce_variable", "Reparameterization", "Reparameterize the noised sample."),
    ("A diffusion model trains a denoiser", "/\\sqrt{\\bar\\alpha_t}$.",
     "other", "Denoiser estimate", "The denoiser estimates the posterior mean."),
    ("Substituting into the score expression above yields the Tweedie identity:", "{\\sigma_t}. \\]",
     "conclude", "Tweedie identity", "Substitute to obtain the identity."),
], q)
q = steps("AP2", [
    ("By additivity, $R_\\mu = R_A + R_B$.", "$R_\\mu = R_A + R_B$.", None, "Add R-transforms", "Add the R-transforms."),
    ("Set $K_\\mu(z) := R_\\mu(z) + 1/z$.", "on the upper-half-plane branch.", None, "Invert K", "Invert $K$ to get the Stieltjes transform (cubic)."),
    ("Recover $\\mu_A \\boxplus \\mu_B$ from $G_\\mu$ by Stieltjes", "Eq.~\\eqref{eq:edge-quartic}).", None, "Stieltjes inversion", "Stieltjes inversion; edges from the discriminant."),
], q, conf=0.75)
# AP2's steps are algorithm steps, not proof steps
asp = 1
for n in NODES:
    if n.get("parent_id") == "AP2":
        n["type"] = "algorithm_step"
        n["id_old"] = n["id"]
sub = {"Add R-transforms": "compute", "Invert K": "solve", "Stieltjes inversion": "compute"}
for n in NODES:
    if n.get("parent_id") == "AP2":
        n["subclass"] = sub[n["name"]]
        n["confidence"] = 0.75

# pseudocode steps
alg_steps = []
for fid, aid in (("F21", "AP1"), ("F46", "AP3")):
    st = pseudocode_steps(facts, fid, BYID[aid], first_seq=asp)
    asp += len(st)
    alg_steps += st
# rename AP2's steps into the ASP sequence
ren = {}
for n in NODES:
    if n.get("id_old"):
        nid = f"ASP{asp}"
        asp += 1
        ren[n["id"]] = nid
        n["id"] = nid
        del n["id_old"]
for old, new in ren.items():
    BYID[new] = BYID.pop(old)

ALG_SUB = {
    # AP1 (Algorithm 1)
    "sample $X_0^{(n)}": "initialize", "\\bar x_f \\gets": "initialize",
    "X_{t+1}^{(n)} \\gets": "update", "\\hat C(\\tau_\\ell) \\gets": "compute",
    "\\hat\\rho(\\tau_\\ell) \\gets": "compute", "L^* \\gets": "select", "\\hat S \\gets": "compute",
    "Select $\\tau^*": "select", "\\hat C^{\\mathrm{sym}} \\gets": "compute",
    "Eigendecompose": "solve", "\\Return $\\hat S$": "return",
    # AP3 (Algorithm 2)
    "\\hat\\Sigma \\gets": "compute", "Draw $\\{x_n^{(b)}\\}": "initialize",
    "Refit score estimator": "solve", "Run pipeline": "call", "\\mathrm{eig}(": "solve",
    "\\Return $\\{\\lambda_i^{(b)}\\}$": "return",
}
SHORT = {
    "X_{t+1}^{(n)} \\gets": "Euler-Maruyama step of the canonical diffusion.",
    "\\hat C(\\tau_\\ell) \\gets": "Trajectory-averaged lag autocovariance.",
    "L^* \\gets": "Stopping lag by the 1/N rule.",
    "Select $\\tau^*": "Choose the DA lag by the selection rule.",
    "Run pipeline": "Same diffusion and embedding as for the data.",
    "\\Return $\\{\\lambda_i^{(b)}\\}$": "Threshold at the null $(1-\\alpha)$-quantile.",
}
kept = []
for s in alg_steps:
    t = s["statement"]
    if not t.strip():   # the \\Return line comes back empty from pseudocode_steps: slice it by hand
        alg = BYID[s["parent_id"]]["statement"]
        t = alg[alg.index("\\Return"):alg.index("\\end{algorithmic}")].strip()
        s["source_note"] = "Return line sliced by hand"
    if "\\textbf{Input:}" in t or "\\textbf{Output:}" in t:
        continue
    if s["subclass"] is None:
        for k, v in ALG_SUB.items():
            if k in t:
                s["subclass"] = v
                break
    for k, v in SHORT.items():
        if k in t:
            s["statement_short"] = v
    s["statement"] = clean(t)
    kept.append(s)
order = {}
for s in kept:
    order[s["parent_id"]] = order.get(s["parent_id"], 0) + 1
    s["step_order"] = order[s["parent_id"]]
    assert s["subclass"], repr(s["statement"])
NODES += kept
for s in kept:
    BYID[s["id"]] = s

# ===================================================================== EDGES
# proves edges with no syntax (proofs under "Proof of ..." headings, prose proofs)
E("PP1", "TP1", "proves", 0.95, "named")
E("PP2", "PrP1", "proves", 0.9, "named")
E("PP3", "LP1", "proves", 0.95, "named")
E("PP3", "CP1", "proves", 0.95, "named")
E("PP7", "PrP2", "proves", 0.95, "named")
E("PP8", "ClP6", "proves", 0.75, "inferred")
E("PP9", "ClP4", "proves", 0.75, "inferred")
E("PP10", "PrP4", "proves", 0.95, "named")
E("PP10", "ClP1", "proves", 0.85, "named")
E("PP11", "ClP7", "proves", 0.8, "named")
for p in ("PP12", "PP13", "PP15", "PP16"):
    E(p, "TP2", "proves", 0.9, "named")
for p in ("PP13", "PP15", "PP16"):
    E(p, "PP12", "uses", 0.85, "named")          # continuation parts of one proof
E("PP17", "ClP2", "proves", 0.75, "inferred")
E("PP18", "ClP3", "proves", 0.75, "inferred")
E("PP20", "CP3", "proves", 0.85, "named")
E("PP21", "TP3", "proves", 0.9, "named")

# mentions stated by a \ref (added before finalize, per Hard rule 7)
STEP_iii = next(n["id"] for n in NODES if n["type"] == "proof_step" and n["statement"].startswith("\\textit{(iii)"))
for s, t in [("CP1", STEP_iii), ("PrP2", "RP2"), ("PrP1", "ClP10"), ("EP9", "AP2"), ("EP8", "AP2")]:
    E(s, t, "uses", 0.95, "ref" if t.startswith("PSP") else None, mention=True)

# pass 1/3: results built on results (named in words or read from the maths)
E("LP1", "CP1", conf=0.85, basis="inferred")
E("CP1", "PP7", conf=0.85, basis="named")         # "differentiate spectral formula"
E("PrP6", "PP7", conf=0.75, basis="inferred")      # strict monotonicity of h_T
E("LP1", "PP7", conf=0.8, basis="named")
E("ClP7", "ClP8", conf=0.9, basis="named")
E("ClP7", "ClP12", conf=0.85, basis="named")
E("PrP4", "ClP12", conf=0.7, basis="inferred")
E("PrP7", "ClP10", conf=0.85, basis="named")
E("PrP7", "ClP11", conf=0.85, basis="named")
E("TP8", "CP3", conf=0.9, basis="named")
E("TP8", "PP20", conf=0.9, basis="named")
E("PrP8", "PP20", conf=0.9, basis="named")
E("ClP4", "DP10", conf=0.85, basis="named")
E("ClP6", "RP11", conf=0.85, basis="named")
E("ClP5", "PP8", conf=0.75, basis="inferred")
E("TP3", "RP21", conf=0.9, basis="named")
E("TP3", "RP22", conf=0.75, basis="inferred")
E("TP3", "AP1", conf=0.7, basis="inferred")
E("PrP4", "ClP9", conf=0.75, basis="named")
E("ClP1", "ClP9", conf=0.7, basis="inferred")
E("TP2", "ClP9", conf=0.7, basis="inferred")
E("TP5", "PP15", conf=0.9, basis="named")
E("TP6", "PP15", conf=0.8, basis="inferred")
E("TP7", "PP15", conf=0.8, basis="inferred")
E("TP4", "PP15", conf=0.8, basis="inferred")
E("TP4", "ClP2", conf=0.8, basis="term")
E("TP4", "PP17", conf=0.8, basis="inferred")
E("TP6", "AP2", conf=0.85, basis="named")
E("AP2", "PP16", conf=0.8, basis="named")         # Step 3 executes items (ii), (iii) of the recipe
E("AP2", "PP15", conf=0.8, basis="named")
E("ClP4", "RP12", conf=0.75, basis="inferred")
E("CP1", "ClP13", conf=0.75, basis="inferred")
E("TP1", "DP3", conf=0.7, basis="inferred")       # the definition singles out the unique diffusion
E("TP2", "OpenP2", conf=0.8, basis="inferred", mention=True)
E("TP2", "RP15", conf=0.75, basis="inferred")
E("TP2", "ExP1", "illustrates", 0.85, "named")
E("ClP9", "ExP1", "illustrates", 0.75, "named")
E("DP3", "ExP1", conf=0.75, basis="term")
E("TP2", "AP1", conf=0.7, basis="inferred")       # lag selection uses the edge
E("AP3", "RP3", conf=0.85, basis="named")
E("DP21", "AP1", conf=0.6, basis="inferred")
E("TP1", "RP5", conf=0.7, basis="inferred")        # the non-reversible drift family it discusses

# pass 2: defined terms
TERM = {
    "DP1": ["DP2", "DP3", "DP4", "DP5", "DP6", "TP1", "AssumP1"],
    "DP2": ["RP8", "RP10", "PP6", "PP7", "RP11", "PP10", "DP6", "LP1", "CP1", "PrP2", "PrP3", "PrP4", "ClP1", "PP3", "PrP1", "RP2", "ClP7", "PP11",
            "OpenP1"],
    "DP3": ["CP1", "PP8", "RP17", "AP3", "RP19", "RP22", "DP25", "PrP1", "DP4", "DP7", "AP1", "TP2", "PP2", "ClP5", "RP1", "RP6", "RP7", "ClP6"],
    "DP4": ["PP11", "DP5", "DP6", "PrP5", "PP3", "RP9", "AP1", "PP9"],
    "DP5": ["PP8", "PP10", "LP1", "DP8", "DP11", "PrP5", "RP8", "RP9", "RP10", "PP3", "PrP4", "ClP1", "DP12", "DP20",
            "ClP5"],
    "DP6": ["RP8", "PP10", "LP1", "PrP4", "ClP1", "ClP7", "PP11", "PP3", "OpenP1"],
    "DP7": ["PP15", "DP9", "RP3", "DP12", "AP1", "AP3", "RP17", "LP2", "PP12", "PP9", "DP20", "RP18", "PP13"],
    "DP8": ["CP1", "PrP2", "PrP3", "RP2", "ClP6", "RP11", "ClP10", "CP2", "DP9", "RP10", "ClP13"],
    "DP9": ["AP1"], "DP10": ["AP1", "RP12"],
    "DP11": ["AP1", "RP16", "ClP9", "ClP10", "RP19", "PrP4", "RP3", "DP12", "ClP8", "ClP12", "RP20", "RP18", "OpenP1"],
    "DP12": ["DP13", "AP1", "RP18"],
    "AssumP1": ["PP1"],
    "DP14": ["PP1", "RP4"],
    "DP15": ["DP17", "AP2", "PP16", "TP2"],
    "DP16": ["TP5", "PP15", "TP2"],
    "DP17": ["DP18", "AP2", "PP16"],
    "DP18": ["TP6", "TP7", "AP2", "PP15", "PP16", "RP15"],
    "TP5": ["TP6", "AP2", "RP14"],
    "DP19": ["DP20", "DP12"],
    "DP21": ["DP12"],
    "DP22": ["DP23", "PrP7", "ClP10", "ClP11", "ClP12"],
    "DP23": ["PrP7", "ClP10", "ClP11", "PP19"],
    "DP24": ["DP25", "PrP8", "TP8", "CP3", "PP20", "RP19", "CnjP2"],
    "DP25": ["TP8", "CP3", "PP20", "RP19", "CnjP2"],
}
for s, ts in TERM.items():
    for t in ts:
        E(s, t, conf=0.75, basis="term")

# pass 4: inside proofs (step -> step)
def kids(pid):
    return [n["id"] for n in NODES if n.get("parent_id") == pid and n["type"] == "proof_step"]


for pid, chain in [("PP3", None), ("PP9", None), ("PP10", None), ("PP14", None), ("PP16", None),
                   ("PP19", None), ("PP21", None)]:
    ks = kids(pid)
    for a, b in zip(ks, ks[1:]):
        E(a, b, conf=0.75, basis="inferred")

# metadata
rigor_count = sum(1 for n in NODES if "rigor" in n)
graph = {
    "metadata": {
        "title": "Measuring and Decomposing Mode Separation via the Canonical Diffusion",
        "arxiv_id": "2605.08777",
        "authors": ["Shaul Tolkovsky", "Ori Meidler", "Or Zuk"],
        "year": 2026,
        "annotator": "agent-extraction",
        "model": "claude-opus-5-5",
        "effort": "default",
        "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
        "extraction_date": "2026-11-05",
        "rigor_nonformal_count": rigor_count,
        "paper_style": ["modeling", "theorem_proof"],
        "extraction_notes": [
            {"category": "rule_conflict", "nodes": ["PP12", "PP13", "PP15", "PP16", "PP17", "PP18", "ClP2", "ClP3"],
             "note": "The proof of Theorem 2 fills C.4.1-C.4.3 but C.4 also holds non-proof subsections, so it is one proof node per part (each proves TP2, continuations use PP12); the tau=0 and tau->infinity statements of the theorem, derived separately in C.4.4, are nested claims ClP2/ClP3 with their own proofs."},
            {"category": "unexpected_construct", "nodes": ["DP15", "DP16", "DP17", "DP18", "TP5", "TP6", "TP7", "AP2"],
             "note": "C.4.2 is a free-probability primer between proof parts; its definitions and cited facts are external Level-1 nodes and its three-item recipe is an unmarked algorithm, not proof steps."},
            {"category": "type_uncertain", "nodes": ["CP3"],
             "note": "corollary or claim: a prose result labelled cor:kinetic_ordering and called 'the corollary', but the paper says it is 'not a free-standing theorem'; kept corollary with rigor semi_formal."},
            {"category": "type_uncertain", "nodes": ["EP13"],
             "note": "equation or claim: eq:rho_clt is later called 'the CLT'; kept as an equation inside the prose derivation PP9, which proves the 1/N bound ClP4."},
            {"category": "boundary_uncertain", "nodes": ["ClP4", "EP5", "PP18", "EP10"],
             "note": "eq:rho_clt_threshold repeats eq:tmax_stopping and eq:edge-tauinf-appendix repeats eq:edge-tauinf-main; the copies are in also_stated_at and lie inside ClP4 and PP18."},
            {"category": "rule_conflict", "nodes": ["DP1", "DP4", "DP2"],
             "note": "The density f is used by nearly every node; term edges from DP1 go only to the core definitions. Remaining finalize warnings are other senses of a symbol (Y = cQX in PP2/RP6, mu_k(A_0) in D.1)."},
            {"category": "source_problem", "nodes": ["PP14", "PSP51"],
             "note": "The prepared source expands \\R after a line break in the smallmatrix of Lemma 2's proof, giving 'P&R\\\\mathbb{R}&Q' instead of 'P&R\\\\R&Q'; copied verbatim from the prepared source."},
            {"category": "source_problem", "nodes": ["ASP15", "ASP24"],
             "note": "pseudocode_steps returned empty statements for both \\Return lines; they were sliced by hand from the algorithm body."},
            {"category": "not_extracted", "nodes": [],
             "note": "Experiments (Sec. 7, App. F-J: GMM sweeps, SDXL, alanine dipeptide, bootstrap tables, compute) are numerical evidence and gave no nodes except the planted-subspace construction ExP1; Related Work and the random-matrix literature paragraph were left out."}
        ],
        "extraction_comment": "Many appendix results (lag window, bimodal heuristic, A_0 and kinetic robustness, Tweedie recovery) are heuristic or asymptotic sketches and carry rigor flags; the formally proved core is Theorems 1-2, Lemmas 1-2, Propositions 1-2 and 4-7 and Corollaries 1-2.",
    },
    "nodes": NODES,
    "edges": EDGES,
}
NOTES = json.load(open(os.path.join(HERE, "notes.json"))) if os.path.exists(os.path.join(HERE, "notes.json")) else None
if NOTES:
    graph["metadata"]["extraction_notes"] = NOTES["extraction_notes"]
    graph["metadata"]["extraction_comment"] = NOTES.get("extraction_comment", "")

report = finalize(graph, read_tex(TEX))
for k in ("matched_to_environment", "labels_filled"):
    print(k, report.get(k))
print("proves_added", len(report["proves_added"]), "ref_uses_added", len(report["ref_uses_added"]))
print("ref_backward", report["ref_backward"])
print("ERRORS", len(report["errors"]))
for e in report["errors"]:
    print("  E", e)
print("WARNINGS", len(report["warnings"]))
for w in report["warnings"]:
    print("  W", w)
assert not report["errors"], report["errors"]
json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
print("wrote", OUT, len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
