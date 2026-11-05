#!/usr/bin/env python3
"""Build the SARANGA v7 graph of arXiv 2605.09439 (Inverse Design for Conditional
Distribution Matching). Every node, type and span below was chosen by reading the
prepared source; this script only slices the chosen spans and assembles the JSON."""
import json, os, re, subprocess, sys

REPO = "/mnt/c/Code/Github/Saranga"
sys.path.insert(0, REPO + "/src")
from extraction_finalize import finalize, pseudocode_steps   # noqa: E402
from latex_facts import read_tex                              # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
TEX = PAPER + "/arxiv_src/CDM_arxiv.tex"
OUT = PAPER + "/2605_09439.json"
SCRATCH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-1000/-mnt-c-Code-Github-Saranga/4aaa7f89-0b3d-4550-9681-028600ff1e2f/scratchpad/extract_orzuk/2605_09439"
os.makedirs(SCRATCH, exist_ok=True)
FACTS = SCRATCH + "/facts.json"
subprocess.run([sys.executable, REPO + "/src/latex_facts.py", TEX, "--out", FACTS], check=True,
               stdout=subprocess.DEVNULL)
facts = json.load(open(FACTS))
S = facts["source"]
F = {f["id"]: f for f in facts["facts"]}
HEADINGS = sorted([h for h in facts["sections"] if h.get("inside") is None], key=lambda h: h["start"])


def pat(snippet):
    parts = re.split(r"\s+", snippet.strip())
    return re.compile(r"\s+".join(re.escape(p) for p in parts))


def find(snippet, start=0):
    m = pat(snippet).search(S, start)
    assert m, f"snippet not found: {snippet!r}"
    return m


def span(a, b, after=None, unique=True):
    """Span from the start of snippet `a` to the end of snippet `b` (first after a)."""
    st = find(after).end() if after else 0
    ma = find(a, st)
    if unique and not after:
        assert len(pat(a).findall(S)) == 1, f"start snippet not unique: {a!r}"
    mb = find(b, ma.start())
    return ma.start(), mb.end()


def text(sp):
    return S[sp[0]:sp[1]]


def sub(stmt, a, b=None):
    """A verbatim sub-span of a statement (for assumptions/conclusions)."""
    m = pat(a).search(stmt)
    assert m, f"sub start not found: {a!r}"
    if b is None:
        return stmt[m.start():m.end()]
    mb = pat(b).search(stmt, m.start())
    assert mb, f"sub end not found: {b!r}"
    return stmt[m.start():mb.end()]


def section_of(pos):
    h = None
    for x in HEADINGS:
        if x["start"] <= pos:
            h = x
    title = re.sub(r"\\texorpdfstring\{([^{}]*)\}\{[^{}]*\}", r"\1", h["title"])
    return f"{h['number']} {title}"


nodes, edges, SPANS = [], [], {}


def node(nid, typ, name, sp, origin="paper", conf=1.0, **kw):
    d = {"id": nid, "type": typ, "name": name, "statement": text(sp), "section": section_of(sp[0]),
         "origin": origin, "confidence": conf}
    if origin == "external":
        d["origin_citation"] = kw.pop("cite")
    d.update(kw)
    nodes.append(d)
    SPANS[nid] = sp
    return d


def env(nid, typ, name, fid, conf=1.0, **kw):
    f = F[fid]
    return node(nid, typ, name, (f["start"], f["end"]), conf=conf, **kw)


def step(nid, parent, order, name, sp, subclass, short, conf=0.75):
    p = next(n for n in nodes if n["id"] == parent)
    d = {"id": nid, "type": "proof_step", "parent_id": parent, "step_order": order, "name": name,
         "statement": text(sp), "statement_short": short, "subclass": subclass,
         "section": p["section"], "origin": p["origin"], "confidence": conf}
    nodes.append(d)
    SPANS[nid] = sp
    return d


def edge(src, tgt, typ="uses", conf=0.8, basis="term", **kw):
    e = {"source": src, "target": tgt, "type": typ, "confidence": conf}
    if basis:
        e["basis"] = basis
    e.update(kw)
    edges.append(e)


def mention(src, tgt):
    edge(src, tgt, "uses", 0.95, None, mention=True)


EXT_STD = "standard (uncited)"

# ---------------------------------------------------------------- 2 Problem Formulation
node("DP1", "definition", "Joint distribution P(X,Y)",
     span("We consider a joint distribution $\\mathcal{P}(X, Y)$", "an associated variable."), conf=0.85,
     definiendum="$\\mathcal{P}(X, Y)$", genus="joint distribution",
     differentia=["over paired random variables"])
node("DP2", "definition", "Distance between distributions",
     span("Let $\\|\\cdot\\|$ denote a distance metric", "the Sliced Wasserstein Distance, SWD)."), conf=0.85,
     definiendum="$\\|\\cdot\\|$", genus="distance metric between probability distributions")
env("ProbP1", "problem", "Conditional Distribution Matching Sampling (CDMS)", "F1",
    statement_short="Sample from the tilted target $\\mathcal{Q}_\\beta(x)\\propto\\mathcal{P}(x)e^{-\\beta\\mathcal{L}(x)}$, "
                    "with $\\mathcal{L}(x)$ the distance between $\\mathcal{P}(Y\\mid X=x)$ and a target $\\mathcal{G}(Y)$.",
    tags=["sampling", "distribution_matching", "inverse_design"])
env("ProbP2", "problem", "Conditional Distribution Matching Optimization (CDMO)", "F2",
    statement_short="Find $x^*$ minimising the distance between the induced conditional $\\mathcal{P}(Y\\mid X=x)$ and the target $\\mathcal{G}(Y)$.",
    tags=["optimization", "distribution_matching", "inverse_design"])
c = node("ClP1", "claim", "CDMO as the β→∞ limit of CDMS",
         span("Problem~\\ref{prob:opt} corresponds to Problem~\\ref{prob:sampling}", "at the mode of the loss."),
         conf=0.75, rigor="semi_formal",
         statement_short="CDMO is the $\\beta\\to\\infty$ limit of CDMS, where $\\mathcal{Q}_\\beta$ concentrates at the loss optimum.")
c["assumptions"] = [sub(c["statement"], "in the limit $\\beta \\to \\infty$")]
c["conclusions"] = [sub(c["statement"], "Problem~\\ref{prob:opt} corresponds to Problem~\\ref{prob:sampling}"),
                    sub(c["statement"], "$\\mathcal{Q}(x)$ concentrates at the mode of the loss")]
node("RP1", "remark", "CDM problems as loss-guided sampling",
     span("Both problems are instances of loss-guided", "- \\mathcal{G}(Y)\\|$."), conf=0.75)

# ---------------------------------------------------------------- 3 Background
node("DP3", "definition", "Denoising Diffusion Probabilistic Model (DDPM)",
     span("Denoising Diffusion Probabilistic Models (DDPM)~\\cite", "back to a sample $x_0$ from the data distribution."),
     origin="external", cite="Sohl-Dickstein et al. 2015; Ho et al. 2020", conf=0.85,
     definiendum="Denoising Diffusion Probabilistic Models (DDPM)",
     statement_short="DDPMs gradually noise data through a forward process and learn a reverse denoising process from $\\mathcal{N}(0,I)$ back to data.")
node("DP4", "definition", "Diffusion notation and Tweedie's estimate",
     span("Throughout we use this notation:", "is Tweedie's estimate of the clean sample given $x_t$."),
     origin="external", cite=EXT_STD, conf=0.85,
     definiendum=["$x_t$", "$q(x_t \\mid x_0)$", "$\\{\\bar{\\alpha}_t\\}_{t=1}^{T}$", "$s_\\theta(x_t, t)$", "$\\hat{x}_0$"],
     statement_short="Noisy state $x_t$, closed-form forward marginal, noise schedule $\\bar\\alpha_t$, unconditional score network $s_\\theta$ and Tweedie's estimate $\\hat x_0$.")
node("DP5", "definition", "Probability flow ODE (DDIM sampler)",
     (find("A\ndeterministic alternative to ancestral sampling").start(),
      find("enables faster sampling with fewer steps.").end()),
     origin="external", cite="Song et al. (DDIM)", conf=0.8,
     definiendum="probability flow ODE")
node("DP6", "definition", "Consistency model",
     span("One direction is consistency models", "without requiring a pretrained teacher."),
     origin="external", cite="Song et al. 2023; Song & Dhariwal 2023", conf=0.8,
     definiendum="consistency models",
     differentia=["enforce self-consistency along the probability-flow ODE trajectory without requiring a pretrained teacher"])
node("DP7", "definition", "Diffusion distillation",
     span("Another direction is \\emph{diffusion distillation}", "sauer2023adversarialdiffusiondistillation}."),
     origin="external", cite="Salimans & Ho 2022; Sauer et al. 2023", conf=0.8,
     definiendum="diffusion distillation",
     differentia=["compresses a pretrained diffusion model into a student that generates samples in one or very few steps"])
a = node("AP1", "algorithm", "Loss-Guided Diffusion (LGD) / Diffusion Posterior Sampling (DPS)",
         span("Diffusion Posterior Sampling (DPS)~\\cite{DiffusionPosteriorSampling} and",
              "averaging over multiple Monte Carlo Tweedie estimates."),
         origin="external", cite="Chung et al. 2023 (DPS); Song et al. 2023 (LGD)", conf=0.8,
         statement_short="Guide reverse diffusion by adding the gradient of a loss at the Tweedie estimate to the score; LGD averages over Monte Carlo Tweedie samples.")
nodes.append({"id": "ASP1", "type": "algorithm_step", "parent_id": "AP1", "step_order": 1,
              "name": "Augment score with loss gradient",
              "statement": text(span("At each denoising step, the score is", "via Tweedie's formula.")),
              "subclass": "update", "section": a["section"], "origin": "external", "confidence": 0.7,
              "statement_short": "Add $\\nabla_{x_t}\\mathcal{L}(\\hat x_0)$ to the score at each denoising step."})
nodes.append({"id": "ASP2", "type": "algorithm_step", "parent_id": "AP1", "step_order": 2,
              "name": "Monte Carlo averaging (LGD)",
              "statement": text(span("LGD further stabilises the gradient", "Monte Carlo Tweedie estimates.")),
              "subclass": "compute", "section": a["section"], "origin": "external", "confidence": 0.7,
              "statement_short": "Average the guidance over several Monte Carlo Tweedie estimates."})

# ---------------------------------------------------------------- 4 Methodology
node("DP8", "definition", "Matching-Loss Guided Diffusion (MLGD)",
     span("MLGD (Matching-Loss Guided Diffusion) specialises", "with a conditional sampler $f_\\phi$ for $\\mathcal{P}(Y \\mid X)$."),
     conf=0.9, definiendum="MLGD (Matching-Loss Guided Diffusion)", genus="Loss-Guided Diffusion",
     differentia=["combining the pretrained score network $s_\\theta$ for $\\mathcal{P}(X)$ with a conditional sampler $f_\\phi$ for $\\mathcal{P}(Y \\mid X)$"],
     statement_short="MLGD specialises LGD to conditional distribution matching by pairing the prior score network with a conditional sampler $f_\\phi$.")
node("DP9", "definition", "MLGD-F (few-step instantiation)",
     span("When $f_\\phi$ is a few-step sampler, we refer", "slower choices of $f_\\phi$."), conf=0.9,
     definiendum="MLGD-F", genus="MLGD", differentia=["$f_\\phi$ is a few-step sampler"])
node("DP10", "definition", "DDIM_step notation",
     span("We write $\\textsc{DDIM\\_step}(x_t, s_\\theta, t)$", "the explicit form is given in Algorithm~\\ref{alg:mlgd-d-full}."),
     conf=0.85, definiendum="$\\textsc{DDIM\\_step}(x_t, s_\\theta, t)$")


def algo_steps(fid, alg_id, first, subclasses, shorts, names):
    raw = pseudocode_steps(facts, fid, next(n for n in nodes if n["id"] == alg_id), first_seq=1)
    lines = F[fid]["lines"]
    kept, idmap, order = [], {}, {}
    seq = first
    li = [ln for ln in lines if ln["start"] is not None]
    for st, ln in zip(raw, li):
        if ln["kind"] == "end":                       # \EndFor: printed, not an operation
            continue
        if not st["statement"].strip():               # \Return line: parser gave an empty span
            m = find("\\Return", ln["start"] - 40)
            st["statement"] = S[m.start():S.index("\n", m.start())].rstrip()
        new = f"ASP{seq}"
        seq += 1
        idmap[st["id"]] = new
        st["id"] = new
        kept.append(st)
    for st in kept:
        st["parent_id"] = idmap.get(st["parent_id"], st["parent_id"])
        order[st["parent_id"]] = order.get(st["parent_id"], 0) + 1
        st["step_order"] = order[st["parent_id"]]
    for st, sc, sh, nm in zip(kept, subclasses, shorts, names):
        st["subclass"] = sc
        if sh:
            st["statement_short"] = sh
        st["name"] = nm
    assert len(kept) == len(subclasses), (fid, len(kept))
    nodes.extend(kept)
    return seq


env("AP2", "algorithm", "MLGD outer loop (black-box loss)", "F3",
    statement_short="LGD skeleton: reverse DDIM from noise, at each step subtracting $\\zeta_t$ times the loss gradient at the Tweedie estimate.",
    input=[sub(text((F["F3"]["start"], F["F3"]["end"])), "Pretrained score network $s_\\theta$ for $\\mathcal{P}(X)$"),
           sub(text((F["F3"]["start"], F["F3"]["end"])), "black-box loss $\\mathcal{L}: \\mathcal{X} \\to \\mathbb{R}$"),
           sub(text((F["F3"]["start"], F["F3"]["end"])), "noise schedule $\\{\\bar{\\alpha}_t\\}_{t=1}^T$"),
           sub(text((F["F3"]["start"], F["F3"]["end"])), "guidance strengths $\\{\\zeta_t\\}_{t=1}^T$")],
    output=[sub(text((F["F3"]["start"], F["F3"]["end"])), "Sample $x_0$ guided toward $\\mathcal{G}$")])
seq = algo_steps("F3", "AP2", 3, ["initialize", "loop", "compute", "compute", "return"],
                 [None, None, "Tweedie estimate of the clean sample.",
                  "Deterministic DDIM step minus guidance from the inner estimator.", None],
                 ["Initial noise", "Reverse-diffusion loop", "Tweedie estimate", "Guided denoising step", "Return sample"])
F5T = text((F["F5"]["start"], F["F5"]["end"]))
env("AP3", "algorithm", "Inner estimator for the distribution-matching loss", "F5", main=True,
    statement_short="Plug-in estimate of $\\mathcal{L}(x)$ from $n_{\\mathrm{cond}}$ fast conditional samples against target samples, differentiated by autograd through $f_\\phi$.",
    input=[sub(F5T, "Query conditioning $x$"),
           sub(F5T, "pretrained differentiable sampler $f_\\phi$ for $\\mathcal{P}(Y{\\mid}X)$"),
           sub(F5T, "target sample $\\mathcal{S}_{\\mathcal{G}} \\sim \\mathcal{G}$"),
           sub(F5T, "number of conditional samples $n_{\\mathrm{cond}}$"),
           sub(F5T, "distributional distance $\\mathcal{L}$ (e.g.\\ MMD, SWD)")],
    output=[sub(F5T, "Estimate $\\widehat{\\mathcal{L}}(x)$ and its gradient $\\nabla_x \\widehat{\\mathcal{L}}(x)$")])
seq = algo_steps("F5", "AP3", seq, ["initialize", "call", "compute", "compute", "return"],
                 [None, "Draw fast conditional samples $f_\\phi(x,\\eta_i)$, differentiable in $x$.",
                  "Plug-in distributional loss between conditional and target samples.",
                  "Gradient by backpropagation through $f_\\phi$.", None],
                 ["Sample internal noise", "Fast conditional samples", "Plug-in loss", "Autograd gradient", "Return estimate"])

node("RP2", "remark", "Why a fast conditional sampler",
     span("The choice of a fast model for $f_\\phi$ is deliberate.", "we measure the resulting memory gap in Section~\\ref{sec:ablation}."),
     conf=0.7, statement_short="A $K_\\star$-step inner sampler multiplies cost by $T K_\\star n_{\\mathrm{cond}}$ and needs backprop through an unrolled chain; a single-step $f_\\phi$ avoids both.")
node("RP3", "remark", "Sampling vs optimisation: role of β",
     span("Algorithm~\\ref{alg:mlgd-outer} interpolates between two regimes", "so the two are not separately identified."),
     conf=0.7, rigor="heuristic",
     statement_short="$\\beta=0$ samples the prior, $\\beta\\to\\infty$ concentrates at $\\arg\\min\\mathcal{L}$; $\\beta$ is absorbed into the step sizes $\\zeta_t$.")
ap4 = node("AP4", "algorithm", "CDMO by multistart at large β",
           span("In practice we report CDMO solutions", "\\widehat{\\mathcal{L}}(x_0^{(r)})$."), conf=0.7,
           statement_short="Solve CDMO by running the guided sampler at large $\\beta$ from $R$ restarts and returning the restart with lowest estimated loss.")
nodes.append({"id": f"ASP{seq}", "type": "algorithm_step", "parent_id": "AP4", "step_order": 1,
              "name": "R restarts at large β",
              "statement": text(span("running at large $\\beta$ with $R$ independent restarts", "x_T^{(r)} \\sim \\mathcal{N}(0,I)$")),
              "subclass": "loop", "section": ap4["section"], "origin": "paper", "confidence": 0.7,
              "statement_short": "Run Algorithm 1 at large $\\beta$ from $R$ independent noise initialisations."})
nodes.append({"id": f"ASP{seq + 1}", "type": "algorithm_step", "parent_id": "AP4", "step_order": 2,
              "name": "Return best restart",
              "statement": text(span("returning $x^* = \\arg\\min_{r=1,\\ldots,R}", "\\widehat{\\mathcal{L}}(x_0^{(r)})$")),
              "subclass": "select", "section": ap4["section"], "origin": "paper", "confidence": 0.7,
              "statement_short": "Select the restart with the smallest estimated loss."})
seq += 2

node("DP36", "definition", "Jacobian fidelity ε_g (main-text form)",
     span("Appendix~\\ref{app:theory} analyses the squared-MMD estimator", "\\partial_x f_{\\mathrm{true}}\\|_F^2)^{1/2}$."),
     conf=0.75, definiendum="$\\varepsilon_g$",
     statement_short="Informal list of the three assumptions of Appendix E, introducing the output gap $\\varepsilon_s$ and the Jacobian gap $\\varepsilon_g$.")

# ---------------------------------------------------------------- 5 Experiments
node("DP11", "definition", "Four Stable Diffusion target distributions",
     span("We define four distribution matching tasks", "\\end{itemize}"), conf=0.8,
     definiendum=["$\\mathcal{G}_{bal}$", "$\\mathcal{G}_{skew}$", "$\\mathcal{G}_{interpGender}$", "$\\mathcal{G}_{interpAge}$"],
     statement_short="Balanced and skewed two-mode gender mixtures, and gender- and age-interpolation continuum targets in CLIP space.")
env("EP1", "equation", "Peak memory decomposition", "F7")
c = node("ClP2", "claim", "Inner-loop memory is Θ(n_cond·K)",
         span("Since the autograd engine", "is $\\Theta(n_{\\text{cond}} \\cdot K)$."), conf=0.75, rigor="semi_formal")
c["assumptions"] = [sub(c["statement"], "the autograd engine must track all unrolled iterations")]
c["conclusions"] = [sub(c["statement"], "total memory is $\\Theta(n_{\\text{cond}} \\cdot K)$")]

# ---------------------------------------------------------------- Appendix A
node("DP12", "definition", "Squared Maximum Mean Discrepancy (population)",
     span("All synthetic experiments instantiate the abstract loss", "is a characteristic positive-definite kernel."),
     origin="external", cite="Gretton et al. 2008", conf=0.85, definiendum="$\\operatorname{MMD}^2$",
     statement_short="Population squared MMD between $\\mathcal{P}(Y\\mid X=x)$ and $\\mathcal{G}$ via kernel expectations over independent pairs.")
node("DP13", "definition", "Biased V-statistic MMD estimator",
     span("In practice we replace this with the biased $V$-statistic", "k(\\tilde{y}_j,\\tilde{y}_{j'}). \\]"),
     origin="external", cite=EXT_STD, conf=0.85, definiendum="$\\widehat{\\operatorname{MMD}}^2$")
node("DP14", "definition", "Multi-bandwidth RBF kernel",
     span("The kernel $k$ is the multi-bandwidth RBF", "mean pairwise squared distance of the merged sample."),
     conf=0.85, definiendum="$k(a,b)$", genus="multi-bandwidth RBF",
     differentia=["$\\sigma$ is the mean pairwise squared distance of the merged sample"])
env("EP2", "equation", "Multi-bandwidth RBF kernel formula", "F8")
node("DP15", "definition", "L2 distance between Gaussian mixtures",
     span("Because both $\\mathcal{P}(Y\\mid X=\\hat{x}^*)$", "Gaussian--Gaussian inner products."),
     origin="external", cite=EXT_STD, conf=0.8, definiendum="$\\|p - q\\|_{L^2}^2$")
t = node("TP1", "theorem", "Gaussian–Gaussian L2 inner product formula",
         span("Each such inner product admits the closed-form evaluation", "\\Sigma_1+\\Sigma_2). \\]"),
         origin="external", cite="Petersen & Pedersen, The Matrix Cookbook 2012", conf=0.85)
t["assumptions"] = []
t["conclusions"] = [sub(t["statement"], "\\langle \\mathcal{N}(\\mu_1,\\Sigma_1)", "\\Sigma_1+\\Sigma_2)")]
env("EP3", "equation", "iCT discretization curriculum", "F9", conf=0.9, origin="external",
    cite="Song & Dhariwal 2023 (iCT)",
    also_stated_at=[text(span("$N(k) = \\min(s_0 \\cdot 2^{\\lfloor k/K' \\rfloor}, s_1) + 1$", "s_1) + 1$"))])

# ---------------------------------------------------------------- Appendix B
node("DP16", "definition", "1-Wasserstein distance",
     span("For two probability distributions $P$ and $Q$ on $\\mathbb{R}^d$", "denotes the set of all joint distributions with marginals $P$ and $Q$."),
     origin="external", cite="Bischoff et al. 2024", conf=0.9, definiendum="$W_1$")
env("EP4", "equation", "1-Wasserstein distance (coupling form)", "F10")
t = node("TP2", "theorem", "One-dimensional Wasserstein distance via CDFs",
         span("For one-dimensional distributions $P$ and $Q$ on $\\mathbb{R}$", "are the CDFs of $P$ and $Q$, respectively."),
         origin="external", cite=EXT_STD, conf=0.85)
t["assumptions"] = [sub(t["statement"], "For one-dimensional distributions $P$ and $Q$ on $\\mathbb{R}$")]
t["conclusions"] = [sub(t["statement"], "the 1-Wasserstein distance has a closed-form expression")]
env("EP5", "equation", "W1 as L1 distance of CDFs", "F11")
node("DP17", "definition", "Empirical 1D Wasserstein distance (sorted samples)",
     span("Given samples $S_1 = \\{s_1, \\ldots, s_m\\}$", "|s_{(i)} - t_{(i)}|. \\end{equation}"),
     origin="external", cite=EXT_STD, conf=0.85, definiendum="$W_1(S_1, S_2)$")
env("EP6", "equation", "Sorted-sample W1 estimator", "F12")
node("DP18", "definition", "Sliced Wasserstein Distance (SWD)",
     span("The SWD between distributions $P$ and $Q$ is defined as:", "and $W_1$ is the 1-Wasserstein distance."),
     origin="external", cite="Bischoff et al. 2024", conf=0.9, definiendum="$\\text{SWD}(P, Q)$",
     statement_short="Average over unit directions $\\theta$ of the 1D Wasserstein distance between the projected distributions.")
env("EP7", "equation", "SWD integral", "F13")
node("DP19", "definition", "Monte Carlo SWD approximation",
     span("In practice, we approximate this integral", "are uniformly sampled from $\\mathbb{S}^{d-1}$."),
     origin="external", cite=EXT_STD, conf=0.85)
env("EP8", "equation", "SWD with L random projections", "F14")

# ---------------------------------------------------------------- Appendix C
node("DP20", "definition", "Stabilised square-root U-statistic MMD estimator",
     span("We use the unbiased U-statistic MMD estimator", "arise when $n$ is small."), conf=0.85,
     definiendum="$\\widehat{\\operatorname{MMD}}\\bigl(\\{y_i\\},\\{\\tilde{y}_j\\}\\bigr)$",
     statement_short="Square root of the absolute U-statistic MMD$^2$ plus $\\epsilon$, on CLIP embeddings.")
env("EP9", "equation", "Stabilised MMD U-statistic formula", "F15")
node("DP21", "definition", "Generalized RBF kernel with median heuristic",
     span("The kernel $k$ is a generalized RBF:", "recovering the standard Gaussian RBF."), conf=0.85,
     definiendum="$k(a,b)$", genus="generalized RBF")
node("DP22", "definition", "CLIP gender saliency",
     span("Define the per-pixel saliency as", "``a photo of a woman''."), conf=0.9,
     definiendum=["per-pixel saliency", "$s(x)$"],
     statement_short="Per-pixel saliency $|\\partial s/\\partial x|$ of the CLIP man-vs-woman cosine score of the image generated from scribble $x$.")

# ---------------------------------------------------------------- Appendix D
F16T = text((F["F16"]["start"], F["F16"]["end"]))
env("AP5", "algorithm", "MLGD-F conditional sampling (full version)", "F16", main=True,
    statement_short="Guided reverse SDE: at each step, perturb the Tweedie estimate $n_{\\mathrm{MC}}$ times, score each with a fast-sampler distributional loss, and guide by the log-sum-exp gradient.",
    input=[sub(F16T, "Pretrained score network $s_\\theta$ for $\\mathcal{P}(X)$"),
           sub(F16T, "pretrained few-step model $f_\\phi$ for $\\mathcal{P}(Y|X)$"),
           sub(F16T, "target distribution $\\mathcal{G}$"),
           sub(F16T, "drift function $f(x,t)$"),
           sub(F16T, "diffusion coefficient $g(t)$"),
           sub(F16T, "noise schedule $\\{\\bar{\\alpha}_t\\}_{t=1}^T$"),
           sub(F16T, "step-size schedule $\\{\\zeta_t\\}$")],
    output=[sub(F16T, "Sample $x_0$ approximately drawn from $\\mathcal{Q}_\\beta$")])
seq = algo_steps("F16", "AP5", seq,
                 ["initialize", "initialize", "loop", "compute", "compute", "compute", "loop", "call", "compute",
                  "compute", "compute", "compute", "return"],
                 ["Draw the target sample once.", None, None, None, "Tweedie estimate of $x_0$.",
                  "Gaussian Monte Carlo perturbations around $\\hat x_0$.", None,
                  "Fast conditional samples at each perturbation using $f_\\phi$.",
                  "Distributional loss of each perturbation against the target sample.",
                  "Guidance gradient from a log-sum-exp aggregate of the perturbation losses.",
                  "Standard reverse-SDE denoising increment.", "Denoising plus guidance update.", None],
                 ["Sample target", "Initial noise", "Outer reverse-diffusion loop", "Time", "Tweedie estimate",
                  "MC perturbations", "Loop over perturbations", "Fast conditional samples", "Per-perturbation loss",
                  "Log-sum-exp guidance gradient", "Denoising increment", "Guided update", "Return sample"])

# ---------------------------------------------------------------- Appendix E
node("RP4", "remark", "Scope of the formal analysis",
     span("Throughout this appendix the loss is the", "(cf.\\ Remark~\\ref{rem:lgd-approx})."), conf=0.75,
     statement_short="The analysis covers squared-MMD U-statistics with a fixed kernel at fixed $x$; SWD, the square-root MMD gradient and data-dependent bandwidths are out of scope.")
node("DP23", "definition", "Distilled conditional sampler f_φ and its law P_φ",
     span("The distilled conditional sampler is a measurable map", "denote the law of $f_\\phi(x, \\eta)$."), conf=0.9,
     definiendum=["$f_\\phi$", "$\\mathcal{P}_\\phi(Y \\mid X=x)$"], genus="measurable map",
     differentia=["with internal randomness $\\eta \\sim \\pi$"])
node("DP24", "definition", "Fixed analysis kernel k",
     span("Throughout this appendix, $k$ denotes a fixed kernel", "understood with respect to this one $k$."), conf=0.85,
     definiendum="$k$")
c = node("ClP3", "claim", "Multi-bandwidth RBF satisfies kernel regularity",
         span("Such a kernel satisfies Assumption~\\ref{ass:kernel} with", "Lipschitz constant on its feature map."),
         conf=0.75, rigor="semi_formal")
c["assumptions"] = []
c["conclusions"] = [sub(c["statement"], "Such a kernel satisfies Assumption~\\ref{ass:kernel}", "on its feature map")]
node("DP25", "definition", "Feature map, RKHS, population losses L and L_φ",
     span("We write $\\varphi_k$ for the feature map", "\\mathcal{P}_\\phi(Y\\mid X=x),\\, \\mathcal{G}\\bigr). \\]"), conf=0.9,
     definiendum=["$\\varphi_k$", "$\\mathcal{H}_k$", "$\\mathcal{L}(x)$", "$\\mathcal{L}_\\phi(x)$"],
     statement_short="$\\varphi_k$ is the RKHS feature map; $\\mathcal{L}$ and $\\mathcal{L}_\\phi$ are the squared MMDs of the true and distilled conditionals to $\\mathcal{G}$.")
node("DP26", "definition", "Plug-in estimator L̂_φ (squared-MMD U-statistic)",
     span("The formal estimator analysed below is the unbiased", "drawn independently of $\\mathcal{S}_{\\mathrm{cond}}$."),
     conf=0.9, definiendum=["$\\widehat{\\mathcal{L}}_\\phi(x)$", "$\\mathcal{S}_{\\mathrm{cond}}(x)$", "$\\mathcal{S}_{\\mathcal{G}}$"],
     statement_short="$\\widehat{\\mathcal{L}}_\\phi(x)$ is the unbiased squared-MMD U-statistic between $n_{\\mathrm{cond}}$ samples of $f_\\phi(x,\\cdot)$ and $n_{\\mathrm{target}}$ target samples.")
node("DP27", "definition", "MLGD-F gradient estimator",
     span("The MLGD-F{} gradient estimator $\\nabla_x \\widehat{\\mathcal{L}}_\\phi(x)$", "automatic differentiation through $f_\\phi$."),
     conf=0.85, definiendum="$\\nabla_x \\widehat{\\mathcal{L}}_\\phi(x)$")
env("AssumP1", "assumption", "Kernel regularity", "F18",
    statement_short="Kernel bounded by $K_{\\max}$, feature map $L_k$-Lipschitz with $H_k$-Lipschitz derivative, and characteristic.")
env("AssumP2", "assumption", "Output fidelity of f_φ under shared noise", "F19",
    statement_short="Same-noise mean-square gap between $f_\\phi$ and $f_{\\mathrm{true}}$ at most $\\varepsilon_s^2$ for every $x$.")
env("AssumP3", "assumption", "Differentiability of f_φ", "F20")
env("AssumP4", "assumption", "Reparameterisable truth", "F21",
    statement_short="The true conditional is the law of a differentiable map $f_{\\mathrm{true}}(x,\\eta)$ of the same noise with bounded Jacobian second moment.")
env("AssumP5", "assumption", "Jacobian fidelity", "F22",
    statement_short="Mean-square Frobenius gap between the Jacobians of $f_\\phi$ and $f_{\\mathrm{true}}$ in $x$ at most $\\varepsilon_g^2$.")
node("AssumP6", "assumption", "Gradient–expectation interchange",
     (find("The proofs below also use the gradient--expectation interchange").start(),
      find("regularity hypothesis on $f_\\phi, f_{\\mathrm{true}}$.").end()), conf=0.85)

# Proposition 1 and its proof
p = env("PrP1", "proposition", "Plug-in loss concentration", "F23",
        statement_short="With probability $1-\\delta$, $|\\widehat{\\mathcal{L}}_\\phi-\\mathcal{L}| \\lesssim K_{\\max}\\sqrt{\\log(2/\\delta)(1/n_{\\mathrm{cond}}+1/n_{\\mathrm{target}})}+4\\sqrt{K_{\\max}}L_k\\varepsilon_s$.",
        tags=["concentration", "bound", "mmd"])
st = p["statement"]
p["assumptions"] = [sub(st, "Under Assumptions~\\ref{ass:kernel} and~\\ref{ass:samples}"), sub(st, "every $\\delta \\in (0,1)$"),
                    sub(st, "every $x \\in \\mathcal{X}$"),
                    sub(st, "every $n_{\\mathrm{cond}}, n_{\\mathrm{target}} \\ge 2$")]
p["conclusions"] = [sub(st, "with probability at least $1-\\delta$ over the draws", "where $C_2 = 4\\sqrt{K_{\\max}}\\,L_k$.")]
env("PP1", "proof", "Proof of Proposition 1 (plug-in loss concentration)", "F24", proves="PrP1",
    proof_strategy=["direct", "probabilistic"],
    statement_short="Triangle inequality into a Monte Carlo and a distillation term. McDiarmid with bounded differences $4K_{\\max}/n$, $4K_{\\max}/m$ bounds the first; a Lipschitz feature map and same-noise coupling bound the second by $4\\sqrt{K_{\\max}}L_k\\varepsilon_s$.")
env("EP10", "equation", "Loss error split into Monte Carlo and distillation terms", "F25")
env("EP11", "equation", "Monte Carlo term bound (McDiarmid)", "F26")
env("EP12", "equation", "Reverse triangle inequality for MMD", "F27")
env("EP13", "equation", "Distillation term bound", "F28")
sp_body = (F["F24"]["start"], F["F24"]["end"])
step("PSP1", "PP1", 1, "Split the error", span("Write $n := n_{\\mathrm{cond}}$ and $m := n_{\\mathrm{target}}$.", "and we bound $T_1, T_2$ separately."),
     "setup", "Split the error into Monte Carlo $T_1$ and distillation $T_2$ terms by the triangle inequality.")
step("PSP2", "PP1", 2, "Step 1: Monte Carlo term", span("\\emph{Step 1: Monte Carlo term.}", "where the second inequality uses $\\sqrt{a+b}\\le\\sqrt{a}+\\sqrt{b}$."),
     "bound_estimate", "Bound $T_1$ by McDiarmid's inequality.", conf=0.95)
step("PSP3", "PSP2", 1, "U-statistic expansion and bounded differences", span("\\emph{Step 1: Monte Carlo term.}", "affects only:"),
     "setup", "Expand the U-statistic; each kernel term lies in $[0,K_{\\max}]$; set up bounded differences.", conf=0.95)
step("PSP4", "PSP2", 2, "Within-Y term", (find("the within-$Y$ term, in which").start(), find("\\tfrac{2(n-1)\\cdot K_{\\max}}{n(n-1)}=\\tfrac{2K_{\\max}}{n}$;").end()),
     "bound_estimate", "Within-sample term contributes $2K_{\\max}/n$.", conf=0.95)
step("PSP5", "PSP2", 3, "Cross term", (find("the cross term, in which $Y_i$ appears").start(), find("\\tfrac{m\\cdot 2 K_{\\max}}{nm}=\\tfrac{2K_{\\max}}{n}$.").end()),
     "bound_estimate", "Cross term contributes $2K_{\\max}/n$.", conf=0.95)
step("PSP6", "PSP2", 4, "Apply McDiarmid", span("Summing, the bounded-difference constant", "where the second inequality uses $\\sqrt{a+b}\\le\\sqrt{a}+\\sqrt{b}$."),
     "apply_lemma", "Sum squared constants to $16K_{\\max}^2(1/n+1/m)$ and apply McDiarmid's inequality.")
step("PSP7", "PP1", 3, "Step 2: Distillation term", span("\\emph{Step 2: Distillation term.}", "\\label{eq:loss-dist} \\end{equation}"),
     "bound_estimate", "Bound $T_2$ via kernel mean embeddings and the coupling.", conf=0.95)
step("PSP8", "PSP7", 1, "MMD as embedding distance", span("\\emph{Step 2: Distillation term.}", "\\label{eq:loss-reverse-tri} \\end{equation}"),
     "invoke_identity", "MMD equals the RKHS distance of mean embeddings; reverse triangle inequality.", conf=0.95)
step("PSP9", "PSP7", 2, "Coupling bound", span("Let $(Y, \\tilde Y)$ be any coupling", "by Assumption~\\ref{ass:samples}."),
     "bound_estimate", "Jensen and the Lipschitz feature map give an $L_k W_1 \\le L_k\\varepsilon_s$ bound on the embedding gap.")
step("PSP10", "PSP7", 3, "From MMD to squared MMD", span("Substituting into~\\eqref{eq:loss-reverse-tri}", "\\label{eq:loss-dist} \\end{equation}"),
     "bound_estimate", "Use $|a^2-b^2|\\le(a+b)|a-b|$ with $a,b\\le2\\sqrt{K_{\\max}}$ to get $T_2\\le C_2\\varepsilon_s$.")
step("PSP11", "PP1", 4, "Combine", (find("Combining~\\eqref{eq:loss-mc}, \\eqref{eq:loss-dist}").start(), sp_body[1]),
     "conclude", "Combine the two bounds.")

# Proposition 2 and its proof
p = env("PrP2", "proposition", "Gradient estimator bias and variance", "F29",
        statement_short="The autograd gradient of the plug-in loss has bias $\\le C_g\\varepsilon_g+C_s\\varepsilon_s$ and variance $\\le C_v(1/n_{\\mathrm{cond}}+1/n_{\\mathrm{target}})$.",
        tags=["bias", "variance", "bound", "gradient_estimation"])
st = p["statement"]
p["assumptions"] = [sub(st, "Under Assumptions~\\ref{ass:kernel}--\\ref{ass:grad}"),
                    sub(st, "$n_{\\mathrm{cond}}, n_{\\mathrm{target}} \\ge 2$"),
                    sub(st, "assuming the gradient--expectation interchange", "$f_{\\mathrm{true}}$ in $x$)")]
p["conclusions"] = [sub(st, "there exist constants $C_g, C_s, C_v$", "\\end{aligned} \\]")]
env("PP2", "proof", "Proof of Proposition 2 (gradient estimator)", "F30", proves="PrP2",
    proof_strategy=["direct", "algebraic_manipulation"],
    statement_short="Interchange gradient and expectation, write the bias as RKHS pairings of $u=B-A$ and $v=A-C$, bound the four norms and apply Cauchy-Schwarz; variance by Hoeffding U-statistic bounds. "
                    "The key step bounds $\\|\\nabla_x u\\|$ by adding and subtracting $d\\varphi_k(f_\\phi)\\partial_x f_{\\mathrm{true}}$.")
for i, fid in enumerate(["F31", "F32", "F33", "F34", "F35", "F36", "F37", "F38"]):
    env(f"EP{14 + i}", "equation",
        ["Gradient envelope of kernel terms", "Gradient–expectation interchange", "Bias decomposition into RKHS pairings",
         "Decomposition of ∇u", "Bound on Δ1", "Bound on Δ2", "Bound on ∇u", "Variance split"][i], fid)
body2 = (F["F30"]["start"], F["F30"]["end"])
step("PSP12", "PP2", 1, "Roadmap", span("Throughout, expectations are over $\\eta_1", "\\textbf{Step~5} bounds the variance separately."),
     "setup", "Set the probability space and outline the five steps.")
step("PSP13", "PSP12", 1, "Probability space", span("Throughout, expectations are over $\\eta_1", "in five steps:"),
     "setup", "Expectations over independent noise and target samples; five-step plan.")
step("PSP14", "PSP12", 2, "Plan: Step 1", span("\\textbf{Step~1} establishes", "used throughout."), "setup", "Plan: envelope and interchange.", conf=0.95)
step("PSP15", "PSP12", 3, "Plan: Step 2", span("\\textbf{Step~2} fixes", "into three RKHS pairings."), "setup", "Plan: bias decomposition.", conf=0.95)
step("PSP16", "PSP12", 4, "Plan: Step 3", span("\\textbf{Step~3} bounds", "that appear in those pairings."), "setup", "Plan: four norm bounds.", conf=0.95)
step("PSP17", "PSP12", 5, "Plan: Step 4", span("\\textbf{Step~4} assembles", "by Cauchy--Schwarz."), "setup", "Plan: assemble bias bound.", conf=0.95)
step("PSP18", "PSP12", 6, "Plan: Step 5", span("\\textbf{Step~5} bounds the variance", "separately."), "setup", "Plan: variance bound.", conf=0.95)
step("PSP19", "PP2", 2, "Notation", span("\\paragraph{Notation for Steps~2--4.}", "coordinate by coordinate."),
     "introduce_variable", "Define embeddings $A,B,C$, differences $u,v$ and Hilbert-Schmidt norms of their gradients.")
step("PSP20", "PP2", 3, "Step 1a: Dominating envelope", span("\\paragraph{Step 1a: Dominating envelope.}", "$\\mathcal{G}$-distributed)."),
     "bound_estimate", "Chain rule gives an integrable envelope $2L_k\\sqrt{K_{\\max}}C_f$ for the summand gradients.", conf=0.95)
step("PSP21", "PP2", 4, "Step 1b: Interchange", span("\\paragraph{Step 1b: Gradient--expectation interchange.}", "Fr\\'echet-differentiable in $x$."),
     "setup", "Adopt the Leibniz interchange so the expected gradient is $\\nabla_x\\mathcal{L}_\\phi$.", conf=0.95)
step("PSP22", "PP2", 5, "Step 2: Bias decomposition", span("\\paragraph{Step 2: Bias decomposition.}", "combine them via Cauchy--Schwarz."),
     "algebraic_manipulation", "Write the bias as $2\\langle u,\\nabla u\\rangle+2\\langle u,\\nabla v\\rangle+2\\langle v,\\nabla u\\rangle$.", conf=0.95)
step("PSP23", "PP2", 6, "Step 3: Bound the four norms", span("\\paragraph{Step 3: Bound the four norms.}", "does not depend on $x$.)"),
     "bound_estimate", "Bound $\\|u\\|$, $\\|\\nabla u\\|$, $\\|v\\|$, $\\|\\nabla v\\|$.", conf=0.95)
step("PSP24", "PSP23", 1, "(a) Bound on ‖u‖", span("\\paragraph{(a) $\\|u(x)\\|_{\\mathcal{H}_k}", "\\|u\\|_{\\mathcal{H}_k} \\;\\le\\; L_k\\,\\varepsilon_s. \\]"),
     "bound_estimate", "Jensen, Lipschitz feature map and Assumption 2 give $\\|u\\|\\le L_k\\varepsilon_s$.", conf=0.95)
step("PSP25", "PSP23", 2, "(b) Bound on ‖∇u‖", span("\\paragraph{(b) $\\|\\nabla_x u(x)\\|_{\\mathcal{H}_k}", "\\label{eq:nabla-u-final} \\end{equation}"),
     "bound_estimate", "Add and subtract to split $\\nabla u$ into Jacobian-gap and feature-derivative-gap terms.", conf=0.95)
step("PSP26", "PSP25", 1, "Split ∇u", span("\\paragraph{(b) $\\|\\nabla_x u(x)\\|_{\\mathcal{H}_k}", "\\|\\Delta_2(\\eta)\\|_{\\mathcal{H}_k}$."),
     "algebraic_manipulation", "Write $\\nabla u = \\mathbb{E}[\\Delta_1+\\Delta_2]$.", conf=0.95)
step("PSP27", "PSP25", 2, "Bound on Δ1", span("\\paragraph{Bound on $\\Delta_1$.}", "\\label{eq:T1-bound} \\end{equation}"),
     "bound_estimate", "Hilbert-Schmidt inequality and Assumption 5 give $L_k\\varepsilon_g$.")
step("PSP28", "PSP25", 3, "Bound on Δ2", span("\\paragraph{Bound on $\\Delta_2$.}", "\\label{eq:T2-bound} \\end{equation}"),
     "bound_estimate", "Lipschitz derivative and Cauchy-Schwarz give $H_k C_f\\varepsilon_s$.")
step("PSP29", "PSP25", 4, "Combine (b)", span("Combining \\eqref{eq:T1-bound}--\\eqref{eq:T2-bound}", "\\label{eq:nabla-u-final} \\end{equation}"),
     "conclude", "Sum the two bounds.")
step("PSP30", "PSP23", 3, "(c) Bound on ‖v‖", span("\\paragraph{(c) $\\|v(x)\\|_{\\mathcal{H}_k}", "\\le 2\\sqrt{K_{\\max}}$."),
     "bound_estimate", "Mean embeddings have norm at most $\\sqrt{K_{\\max}}$.", conf=0.95)
step("PSP31", "PSP23", 4, "(d) Bound on ‖∇v‖", span("\\paragraph{(d) $\\|\\nabla_x v(x)\\|_{\\mathcal{H}_k}", "does not depend on $x$.)"),
     "bound_estimate", "Chain rule on $A$ alone gives $L_k C_f$.", conf=0.95)
step("PSP32", "PP2", 7, "Step 4: Assemble the bias bound", span("\\paragraph{Step 4: Assemble the bias bound.}", "Both depend only on $K_{\\max}, L_k, H_k, C_f$."),
     "bound_estimate", "Cauchy-Schwarz on the three pairings gives $C_g=8L_k\\sqrt{K_{\\max}}$, $C_s=2L_k^2C_f+8H_kC_f\\sqrt{K_{\\max}}$.", conf=0.95)
step("PSP33", "PP2", 8, "Step 5: Variance", span("\\paragraph{Step 5: Variance.}", "since only the rate is used."),
     "conclude", "Split the variance and apply Hoeffding's U-statistic variance bounds.", conf=0.95)

env("RP5", "remark", "Generic distillation-through-autograd structure", "F39", conf=1.0, rigor="semi_formal",
    statement_short="The Step 3(b) argument bounds any student-vs-teacher gradient gap by $C_g\\varepsilon_{g,\\mathrm{dist}}+C_s\\varepsilon_{\\mathrm{dist}}$; output closeness alone does not control Jacobians.")

# Proposition 3
node("DP28", "definition", "Teacher sampler f_⋆ and few-step student",
     span("For comparison, consider the same estimator using a $K_\\star$-step", "or a single-step CM, $K_s=1$)."), conf=0.85,
     definiendum=["$f_\\star$", "$K_\\star$", "$K_s$"])
node("DP29", "definition", "Teacher conditional, loss and gradient estimators",
     span("Denote the teacher's induced conditional by", "the corresponding gradient estimator by $\\nabla_x \\widehat{\\mathcal{L}}_\\star(x)$."),
     conf=0.85, definiendum=["$\\mathcal{P}_\\star$", "$\\widehat{\\mathcal{L}}_\\star$", "$\\nabla_x \\widehat{\\mathcal{L}}_\\star(x)$"])
p = env("PrP3", "proposition", "Memory–fidelity trade-off", "F40",
        statement_short="A $K_s$-step student cuts reverse-mode memory by $\\Theta(K_\\star/K_s)$ versus a $K_\\star$-step teacher, at a student-teacher gradient gap $\\le C_g\\varepsilon_{g,\\mathrm{dist}}+C_s\\varepsilon_{\\mathrm{dist}}$.",
        tags=["memory", "distillation", "bound"])
st = p["statement"]
A_mem = sub(st, "Under Assumption~\\ref{ass:diff} for both $f_\\phi$ and $f_\\star$")
A_fix = sub(st, "Fix $x\\in\\mathcal{X}$ and assume", "are well-defined")
A_s1 = sub(st, "$\\mathbb{E}_\\eta\\|f_\\phi(x,\\eta) - f_\\star(x,\\eta)\\|^2", "for every $x$")
A_s2 = sub(st, "$\\mathbb{E}_\\eta\\|\\partial_x f_\\phi(x,\\eta) - \\partial_x f_\\star(x,\\eta)\\|_F^2", "for every $x$")
A_s3 = sub(st, "$\\mathbb{E}_\\eta\\|\\partial_x f_\\star(x,\\eta)\\|_F^2 \\le C_f^2$ for every $x$")
A_int = sub(st, "Assume moreover that the gradient--expectation interchange", "differentiability in $x$)")
C1 = sub(st, "reverse-mode evaluation of $\\nabla_x \\widehat{\\mathcal{L}}_\\star(x)$", "(absent checkpointing)")
C2 = sub(st, "reverse-mode evaluation of $\\nabla_x \\widehat{\\mathcal{L}}_\\phi(x)$", "therefore $\\Theta(K_\\star/K_s)$")
C3 = sub(st, "\\bigl\\|\\mathbb{E}[\\nabla_x \\widehat{\\mathcal{L}}_\\phi] - \\mathbb{E}[\\nabla_x \\widehat{\\mathcal{L}}_\\star]\\bigr\\|",
         "C_s\\,\\varepsilon_{\\mathrm{dist}}")
p["assumptions"] = [A_mem, A_fix, A_s1, A_s2, A_s3, A_int]
p["conclusions"] = [C1, C2, C3]
p["parts"] = [{"assumptions": [A_mem], "conclusions": [C1, C2]},
              {"assumptions": [A_fix, A_s1, A_s2, A_s3, A_int], "conclusions": [C3]}]
env("PP3", "proof", "Proof of Proposition 3 (memory–fidelity trade-off)", "F41", proves="PrP3",
    proof_strategy=["direct"],
    statement_short="Count reverse-mode chain depth and stored activations per conditional sample; for the gradient gap, replay the proof of Proposition 2 with the teacher in place of the truth.")
body3 = (F["F41"]["start"], F["F41"]["end"])
step("PSP34", "PP3", 1, "Parts (1) and (2): reverse-mode memory",
     span("\\emph{Parts (1) and (2): reverse-mode memory.}", "as claimed."), "bound_estimate",
     "Reverse-mode memory scales with the number of unrolled sampler steps times $n_{\\mathrm{cond}}$.", conf=0.95)
step("PSP35", "PSP34", 1, "Reverse-mode structure", span("\\emph{Parts (1) and (2): reverse-mode memory.}", "U-statistic reduction node."),
     "setup", "Autodiff propagates through each of the $n_{\\mathrm{cond}}$ sampler calls into one reduction node.", conf=0.95)
step("PSP36", "PSP34", 2, "Teacher memory", span("Each teacher forward $f_\\star(x, \\eta_i)$", "this is unavoidable."),
     "bound_estimate", "A $K_\\star$-step unrolled chain gives depth $\\Theta(K_\\star)$ and $\\Theta(K_\\star n_{\\mathrm{cond}})$ activations.")
step("PSP37", "PSP34", 3, "Student memory and ratio", span("For the few-step student, $f_\\phi(x, \\eta_i)$", "as claimed."),
     "conclude", "The student costs $\\Theta(K_s n_{\\mathrm{cond}})$; the ratio is $\\Theta(K_\\star/K_s)$.")
step("PSP38", "PP3", 2, "Gradient discrepancy", (find("\\emph{Gradient discrepancy:}").start(), body3[1]), "apply_lemma",
     "Replay Proposition 2's proof with $f_\\star$ for $f_{\\mathrm{true}}$.", conf=0.95)
step("PSP39", "PSP38", 1, "Primed notation", span("\\emph{Gradient discrepancy:}", "holds with primes."),
     "introduce_variable", "Define $A',B',u',v'$ with the teacher's embedding; the decomposition holds with primes.", conf=0.95)
step("PSP40", "PSP38", 2, "Substituted norm bounds", span("Steps~3(a)--(d) of Proposition~\\ref{prop:grad}'s proof", "for this comparison."),
     "substitute", "Steps 3(a)-(d) go through with $\\varepsilon_{\\mathrm{dist}},\\varepsilon_{g,\\mathrm{dist}}$ under (S1)-(S3).")
step("PSP41", "PSP38", 3, "Assemble", span("Step~4 then yields", "as in Proposition~\\ref{prop:grad}.", after="for this comparison."),
     "conclude", "Step 4 gives the student-teacher bound with the same constants.")
step("PSP42", "PSP38", 4, "Truth errors absent", (find("The teacher-to-truth errors $\\varepsilon_d$ and $\\varepsilon_{g,d}$").start(), body3[1]),
     "other", "Teacher-to-truth errors never enter, since the comparison is student versus teacher.")

c = env("CP1", "corollary", "Identifiability under low-rank targets", "F42", rigor="semi_formal",
        statement_short="With a characteristic kernel, zero loss iff the induced conditional equals $\\mathcal{G}$, so zero-loss inputs reproduce low-rank supports; uniform convergence gives consistency of empirical minimisers.",
        tags=["identifiability", "consistency"])
st = c["statement"]
E1 = sub(st, "\\mathcal{L}(x) = 0 \\;\\iff\\; \\mathcal{P}(Y\\mid X=x) = \\mathcal{G}")
A_sup = sub(st, "if $\\mathcal{G}$ is supported on a (low-rank) submanifold", "\\subseteq \\mathcal{Y}$")
C_sup = sub(st, "any global minimiser $x^\\star$ of", "\\subseteq \\mathcal{M};")
A_unif = sub(st, "If, in addition, $\\widehat{\\mathcal{L}}_\\phi \\to \\mathcal{L}$", "$\\varepsilon_s, \\varepsilon_g \\to 0$")
C_unif = sub(st, "then any sequence of empirical minimisers", "\\to \\min_x \\mathcal{L}(x)$")
A_char = sub(st, "Suppose $k$ is characteristic on $\\mathcal{Y}$")
c["assumptions"] = [A_char, A_sup, A_unif]
c["conclusions"] = [E1, C_sup, C_unif]
c["equivalent_conditions"] = [sub(st, "\\mathcal{L}(x) = 0"), sub(st, "\\mathcal{P}(Y\\mid X=x) = \\mathcal{G}")]
c["parts"] = [{"assumptions": [], "conclusions": [E1]},
              {"adds_to": 0, "assumptions": [A_sup], "conclusions": [C_sup]},
              {"adds_to": 0, "assumptions": [A_unif], "conclusions": [C_unif]}]

env("RP6", "remark", "Q_β as ideal target; MLGD-F as an LGD-style approximate sampler", "F43",
    statement_short="Exact $\\mathcal{Q}_\\beta$ sampling needs the intractable noisy-time guidance score; MLGD-F uses the Tweedie-Jensen surrogate $-\\beta\\nabla\\mathcal{L}(\\hat x_0)$, so it is approximate.")
env("EP22", "equation", "Exact tilted score", "F44")

# E.8 status of the fidelity assumptions
node("DP30", "definition", "Teacher-to-truth and distillation errors ε_d, ε_dist",
     span("\\emph{Distilled samplers (teacher refinement)}", "the student-to-teacher distillation error."), conf=0.8,
     definiendum=["$\\varepsilon_d$", "$\\varepsilon_{\\mathrm{dist}}$"],
     statement_short="For a distilled student, $\\varepsilon_s\\le\\varepsilon_d+\\varepsilon_{\\mathrm{dist}}$ with teacher-to-truth error $\\varepsilon_d$ and student-to-teacher error $\\varepsilon_{\\mathrm{dist}}$.")
node("OpenP1", "open_problem", "Bounding the Jacobian gap ε_g by training quantities",
     span("Bounding $\\varepsilon_g$ in terms of training", "independent of this paper."), conf=0.85)
node("DP31", "definition", "Reference sampler f_ref",
     span("We can still measure a \\emph{component} of $\\varepsilon_g$", "trained on the same data."), conf=0.75,
     definiendum="$f_{\\mathrm{ref}}$")
node("DP32", "definition", "Jacobian error components ε_{g,d}, ε_{g,dist}",
     span("Triangle inequality gives", "the truth's Jacobian is unknown.", after="trained on the same data."), conf=0.8,
     definiendum=["$\\varepsilon_{g,d}$", "$\\varepsilon_{g,\\mathrm{dist}}$"],
     statement_short="$\\varepsilon_g\\le\\varepsilon_{g,d}+\\varepsilon_{g,\\mathrm{dist}}$: an unmeasurable reference-to-truth Jacobian gap plus a measurable student-to-reference gap.")
node("RP7", "remark", "The Jacobian diagnostic is one-sided",
     span("The empirical check is \\emph{one-sided}.", "becomes a bias bound in terms of $\\varepsilon_g$ alone."), conf=0.75,
     statement_short="A large measured $\\varepsilon_{g,\\mathrm{dist}}$ can falsify Assumption 5, but a small one does not prove $\\varepsilon_g$ small.")
node("DP33", "definition", "VJP probing directions",
     span("Because the latent observable", "one reverse-mode pass each."), conf=0.75,
     definiendum=["$D$", "$v_d$"])
node("DP34", "definition", "Empirical gaps ε̂_dist and ε̂_{g,dist}",
     span("Writing $J_\\bullet^{(i,d)}", "\\bigl\\|J_\\phi^{(i,d)} - J_\\star^{(i,d)}\\bigr\\|^2}. \\]"), conf=0.85,
     definiendum=["$J_\\bullet^{(i,d)}$", "$\\widehat\\varepsilon_{\\mathrm{dist}}$", "$\\widehat\\varepsilon_{g,\\mathrm{dist}}$"],
     statement_short="Root-mean-square output gap and directional-Jacobian gap between student and teacher over prompts and VJP directions.")
node("DP35", "definition", "Relative errors r̂_s and r̂_g",
     span("Since these quantities have different units", "\\|v_d^\\top\\partial_x f_\\phi(x_i,\\eta_i)\\|\\Bigr)^2}. \\]"), conf=0.85,
     definiendum=["$\\widehat r_s$", "$\\widehat r_g$", "$\\bar y_\\phi$", "$\\bar J_\\phi$"],
     statement_short="Output and Jacobian gaps normalised by the student's own output and directional-Jacobian magnitudes.")

# ================================================================ edges (passes 1-4)
T = lambda s_, t_, c_=0.8: edge(s_, t_, "uses", c_, "term")
Nm = lambda s_, t_, c_=0.9: edge(s_, t_, "uses", c_, "named")
I = lambda s_, t_, c_=0.7: edge(s_, t_, "uses", c_, "inferred")

# Section 2
for t_ in ["ProbP1", "ProbP2"]:
    T("DP1", t_, 0.8); T("DP2", t_, 0.85)
Nm("ProbP1", "RP1"); Nm("ProbP2", "RP1")
T("AP1", "RP1", 0.75)
mention("RP6", "ProbP1")            # "analysed in Remark ... of Appendix"
# Section 3
T("DP3", "DP4", 0.75); T("DP3", "DP5", 0.7); T("DP5", "DP6", 0.8); T("DP3", "DP7", 0.75)
T("DP4", "AP1", 0.85)
# Section 4
edge("AP1", "DP8", "specializes", 0.9, "named")
T("DP4", "DP8", 0.8)
edge("DP8", "DP9", "specializes", 0.9, "named")
T("DP5", "DP10", 0.85)
edge("AP1", "AP2", "specializes", 0.9, "named")
T("DP8", "AP2", 0.8); T("DP4", "AP2", 0.85); T("DP10", "AP2", 0.9)
T("DP8", "AP3", 0.8); T("DP2", "AP3", 0.7)
edge("ProbP1", "AP2", "resolves", 0.8, "inferred")
Nm("AP3", "RP2", 0.85); T("AP2", "RP2", 0.8); T("DP3", "RP2", 0.7)
T("AP2", "AP4", 0.8); T("AP3", "AP4", 0.75); T("ProbP1", "AP4", 0.75)
edge("ProbP2", "AP4", "resolves", 0.85, "named")
# Section 5
I("EP1", "ClP2", 0.75)
# Appendix A-C
T("ProbP1", "DP12", 0.75); T("DP12", "DP13", 0.8)
T("DP15", "TP1", 0.7)
T("DP6", "EP3", 0.7)
T("DP16", "TP2", 0.85); T("DP16", "DP17", 0.85); T("DP16", "DP18", 0.85); T("DP18", "DP19", 0.85)
T("DP12", "DP20", 0.75); T("DP21", "DP20", 0.75)
# Appendix D
T("DP4", "AP5", 0.85); T("DP9", "AP5", 0.85); T("DP2", "AP5", 0.7)
edge("ProbP1", "AP5", "resolves", 0.85, "named")
I("AP2", "AP5", 0.75); I("AP3", "AP5", 0.75)
# Appendix E setup
T("DP14", "DP24", 0.85); T("DP24", "ClP3", 0.85)
T("DP8", "DP23", 0.7)
T("DP24", "DP25", 0.8); T("DP12", "DP25", 0.8); T("DP23", "DP25", 0.85)
T("DP23", "DP26", 0.85); T("DP25", "DP26", 0.75); T("AP3", "DP26", 0.75)
T("DP26", "DP27", 0.85); T("DP23", "DP27", 0.8)
T("DP20", "RP4", 0.75); mention("PrP2", "RP4"); mention("RP6", "RP4")
T("DP25", "AssumP1", 0.85); T("DP24", "AssumP1", 0.8)
T("DP23", "AssumP2", 0.85); T("DP23", "AssumP3", 0.85); T("DP23", "AssumP4", 0.75)
T("DP23", "AssumP5", 0.8); T("AssumP4", "AssumP5", 0.85)
T("DP23", "AssumP6", 0.75); T("AssumP4", "AssumP6", 0.75)
mention("PrP1", "AssumP1"); mention("PrP2", "AssumP1")   # "Clauses (ii)--(iii) are needed only for Proposition ..."
# Proposition 1
T("DP26", "PrP1", 0.85); T("DP25", "PrP1", 0.85)
I("AssumP4", "PrP1", 0.7)            # epsilon_s is defined through f_true (Assumption 4)
T("DP25", "PP1", 0.8); T("DP26", "PP1", 0.8); T("DP16", "PP1", 0.75)
I("PSP2", "PSP11", 0.8); I("PSP7", "PSP11", 0.8)
I("PSP3", "PSP6", 0.8); I("PSP4", "PSP6", 0.8); I("PSP5", "PSP6", 0.8)
I("PSP9", "PSP10", 0.8)
# Proposition 2
for a_ in ["AssumP2", "AssumP3", "AssumP4"]:
    Nm(a_, "PrP2", 0.9)              # the range "Assumptions 1--5"
T("AssumP6", "PrP2", 0.8); T("DP26", "PrP2", 0.85); T("DP25", "PrP2", 0.85)
T("DP25", "PP2", 0.8); T("DP26", "PP2", 0.8)
Nm("PSP21", "PSP26", 0.9)            # "By Step 1b's Leibniz justification"
Nm("PSP25", "PSP31", 0.9)            # "Repeat the chain-rule expansion of (b)"
for s_ in ["PSP24", "PSP30", "PSP31"]:
    Nm(s_, "PSP32", 0.9)             # "Step 3(a)", "Step 3(c)", "Step 3(d)"
I("PSP19", "PSP22", 0.75)
I("PSP27", "PSP29", 0.8); I("PSP28", "PSP29", 0.8)
# Remark 1 (generic distillation structure)
Nm("PP2", "RP5", 0.9)
edge("PrP2", "RP5", "generalizes", 0.85, "named")
edge("RP5", "PrP3", "specializes", 0.85, "named")
# Proposition 3
T("DP23", "DP28", 0.75); T("DP28", "DP29", 0.85); T("DP26", "DP29", 0.8)
T("DP28", "PrP3", 0.85); T("DP29", "PrP3", 0.85); T("DP26", "PrP3", 0.8); T("AssumP6", "PrP3", 0.8)
for a_ in ["AssumP2", "AssumP4", "AssumP5"]:
    mention(a_, "PrP3")              # "direct analogues of Assumptions ..."
edge("DP30", "PrP3", "uses", 0.7, "term", mention=True)   # eps_d, eps_{g,d} "do not enter"
edge("DP32", "PrP3", "uses", 0.7, "term", mention=True)
Nm("PP2", "PP3", 0.9)                # "Replay the proof of Proposition ... verbatim"
T("DP28", "PP3", 0.8); T("DP29", "PP3", 0.8)
I("PSP35", "PSP36", 0.75); I("PSP36", "PSP37", 0.8)
I("PSP39", "PSP40", 0.8); I("PSP40", "PSP41", 0.8)
mention("PrP2", "PSP42")             # "would require Proposition ... applied to f_star separately"
for t_ in ["PSP40", "PSP38", "PP3"]:
    mention("AssumP2", t_); mention("AssumP5", t_)   # "(S1),(S2) ... replace Assumptions ..."
# Corollary
T("AssumP1", "CP1", 0.8); T("DP25", "CP1", 0.85); T("DP26", "CP1", 0.8)
T("AssumP2", "CP1", 0.7); T("AssumP5", "CP1", 0.7)
mention("PrP1", "CP1")               # "Proposition ... is pointwise"
for t_ in ["PSP8", "PSP7", "PP1"]:
    mention("CP1", t_)               # footnote: "used only for the identifiability part of Corollary"
# Remark on Q_beta
Nm("AP1", "RP6", 0.85); T("DP4", "RP6", 0.8)
mention("PrP1", "RP6"); mention("PrP2", "RP6")
# E.8 - E.9
T("DP28", "DP30", 0.85); T("AssumP4", "DP30", 0.8)
T("AssumP5", "OpenP1", 0.85)
T("AssumP5", "DP31", 0.7)
T("DP31", "DP32", 0.85); T("AssumP5", "DP32", 0.8); T("AssumP4", "DP32", 0.75); T("DP23", "DP32", 0.75)
T("DP32", "RP7", 0.85)
T("DP33", "DP34", 0.85); T("DP28", "DP34", 0.8); T("DP23", "DP34", 0.75)
T("DP30", "DP34", 0.8); T("DP32", "DP34", 0.8)
T("DP34", "DP35", 0.9); T("DP33", "DP35", 0.8)

# finishing-step warnings: defined terms used without an edge
T("DP6", "RP5", 0.7)
T("DP9", "DP27", 0.8); T("DP9", "RP6", 0.8)
for t_ in ["PP1", "PP2", "RP5", "PrP3", "PP3", "DP30", "DP35"]:
    T("DP23", t_, 0.8)
T("DP25", "PP3", 0.8)
T("DP27", "PrP2", 0.85); T("DP27", "PP2", 0.8)
T("DP36", "PrP2", 0.7); T("DP36", "PP2", 0.7)
for t_ in ["PP3", "CP1", "RP6", "DP32"]:
    T("DP36", t_, 0.6)

rigor_n = sum(1 for n in nodes if "rigor" in n)
graph = {
    "metadata": {
        "title": "Inverse Design for Conditional Distribution Matching",
        "arxiv_id": "2605.09439",
        "authors": ["Ori Meidler", "Shaul Tolkovsky", "Or Zuk"],
        "year": 2026,
        "annotator": "agent-extraction",
        "model": "claude-opus-5-5",
        "effort": "default",
        "prompt_version": "v7-86dcfbecdc4d78a5-f0f2ca3",
        "extraction_date": "2026-11-05",
        "rigor_nonformal_count": rigor_n,
        "paper_style": ["computational", "modeling"],
        "extraction_notes": [
            {"category": "source_problem", "nodes": [],
             "note": "\\input{checklist.tex} (NeurIPS checklist) is not in the archive; it carries no mathematics and was ignored."},
            {"category": "source_problem", "nodes": ["AP2", "AP3", "AP5"],
             "note": "pseudocode_steps returned empty spans for the \\State \\Return lines; the return steps take the verbatim '\\Return ...' line instead. \\EndFor lines were dropped."},
            {"category": "rule_conflict", "nodes": ["PSP12"],
             "note": "The proof of Proposition 2 opens with a roadmap whose sentences start with \\textbf{Step~1}..\\textbf{Step~5}; the parser reports them as author labels, so each roadmap sentence is a setup step under one roadmap step, separate from the actual Step 1a-5 paragraphs."},
            {"category": "type_uncertain", "nodes": ["DP30", "DP32"],
             "note": "definition or claim: each sentence introduces error symbols (used by Proposition 3 and E.9) and also asserts a triangle-inequality bound on epsilon_s or epsilon_g; typed by the symbols it introduces."},
            {"category": "type_uncertain", "nodes": ["RP5"],
             "note": "remark or proposition: Remark 1 asserts a general student-vs-teacher gradient bound (argued only by pointing to Step 3(b)) plus a counterexample; kept as remark with rigor semi_formal."},
            {"category": "boundary_uncertain", "nodes": ["AP4"],
             "note": "The CDMO multistart procedure is one sentence at the end of the beta paragraph; its two algorithm steps are sub-sentence spans."},
            {"category": "not_extracted", "nodes": [],
             "note": "Experimental setups, hyperparameter and result tables, dataset construction, the informal restatement of Propositions 1-3 in Section 4.2, the empirical 'open questions' of E.9 and the E.10 discussion bullets were not made nodes."},
        ],
        "extraction_comment": "The mathematical core is Appendix E (five assumptions, three propositions with proofs, a corollary); the body defines the CDM problems and the MLGD/MLGD-F algorithms and validates them empirically.",
    },
    "nodes": nodes,
    "edges": edges,
}

report = finalize(graph, read_tex(TEX))
json.dump(report, open(SCRATCH + "/finalize_report.json", "w"), indent=1)
print("errors:", len(report["errors"]))
for e in report["errors"]:
    print("  E", e)
print("warnings:", len(report["warnings"]))
for w in report["warnings"]:
    print("  W", w)
print({k: (len(v) if isinstance(v, list) else v) for k, v in report.items() if k not in ("errors", "warnings")})
assert not report["errors"], report["errors"]
json.dump(graph, open(OUT, "w"), indent=1, ensure_ascii=False)
print("wrote", OUT, len(graph["nodes"]), "nodes", len(graph["edges"]), "edges")
