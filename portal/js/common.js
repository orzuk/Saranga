// Shared helpers for the SARANGA portal: fetch, manifest cache, KaTeX render.
//
// All pages assume `vendor/katex/` is reachable as a relative path from the
// HTML page, and `data/manifest.json` likewise. We compute the prefix from
// the current document path so that the same JS works for index.html and
// for nested viewers (paper.html, pair.html) which share the same depth.

(function (global) {
  "use strict";

  // All HTML files live at the portal root, so vendor/ and data/ are
  // both reachable as plain relative paths. If we ever move pages into
  // a subdirectory, this is the single place to change.
  const BASE = "";

  function relPath(rel) {
    return BASE + rel;
  }

  async function fetchJson(rel) {
    const url = relPath(rel);
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) {
      throw new Error("Failed to fetch " + url + " (" + r.status + ")");
    }
    return await r.json();
  }

  let _manifestPromise = null;
  function loadManifest() {
    if (!_manifestPromise) {
      _manifestPromise = fetchJson("data/manifest.json").catch(function (e) {
        console.error("manifest.json missing or invalid:", e);
        return { papers: { tier1: [], tier2: [], tier3: [] }, pairs: [] };
      });
    }
    return _manifestPromise;
  }

  // Shared KaTeX macros: cover operators and symbol families that author
  // \newcommand / \DeclareMathOperator definitions in arXiv preambles
  // routinely introduce. The same dict is mirrored inside the embedded
  // HTML emitted by src/visualize_annotation.py — keep them in sync.
  function _buildMacros() {
    const m = {
      // Number sets
      "\\R": "\\mathbb{R}", "\\N": "\\mathbb{N}", "\\Z": "\\mathbb{Z}",
      "\\Q": "\\mathbb{Q}", "\\C": "\\mathbb{C}", "\\F": "\\mathbb{F}",
      "\\E": "\\mathbb{E}", "\\P": "\\mathbb{P}", "\\1": "\\mathbf{1}",
      // Probability / statistics
      "\\Var": "\\operatorname{Var}", "\\Cov": "\\operatorname{Cov}",
      "\\Cor": "\\operatorname{Cor}", "\\KL":  "\\operatorname{KL}",
      "\\indep": "\\perp\\!\\!\\!\\perp",
      // Linear algebra / matrix operators
      "\\Tr": "\\operatorname{Tr}", "\\tr": "\\operatorname{tr}",
      "\\rk": "\\operatorname{rank}", "\\rank": "\\operatorname{rank}",
      "\\diag": "\\operatorname{diag}", "\\Span": "\\operatorname{Span}",
      "\\Hom": "\\operatorname{Hom}", "\\End": "\\operatorname{End}",
      "\\Aut": "\\operatorname{Aut}", "\\Hess": "\\operatorname{Hess}",
      "\\sgn": "\\operatorname{sgn}", "\\spec": "\\operatorname{spec}",
      "\\supp": "\\operatorname{supp}", "\\vol": "\\operatorname{vol}",
      "\\diam": "\\operatorname{diam}",
      // Complexity / discrete
      "\\poly": "\\operatorname{poly}", "\\polylog": "\\operatorname{polylog}",
      // Laplacian variants (graph / spectral)
      "\\Lsym": "L_{\\mathrm{sym}}", "\\Lrw": "L_{\\mathrm{rw}}",
      "\\Lun":  "L_1",
      // Custom paper-specific operators that appear in our gold/silver corpus
      "\\Cut":     "\\operatorname{Cut}",
      "\\Ncut":    "\\operatorname{Ncut}",
      "\\charfct": "\\mathbf{1}",
      // Symbols and shortcuts
      "\\T":      "\\top",
      "\\defeq":  "\\stackrel{\\mathrm{def}}{=}",
      "\\eqdef":  "\\stackrel{\\mathrm{def}}{=}",
      // Bold-font shortcuts for vectors / random variables
      "\\bx": "\\mathbf{x}", "\\by": "\\mathbf{y}", "\\bz": "\\mathbf{z}",
      "\\bw": "\\mathbf{w}", "\\bu": "\\mathbf{u}", "\\bv": "\\mathbf{v}",
      "\\bA": "\\mathbf{A}", "\\bB": "\\mathbf{B}", "\\bX": "\\mathbf{X}",
      "\\bY": "\\mathbf{Y}", "\\bZ": "\\mathbf{Z}",
      "\\bepsilon": "\\boldsymbol{\\epsilon}", "\\btheta":   "\\boldsymbol{\\theta}",
      "\\bmu":      "\\boldsymbol{\\mu}",      "\\bSigma":   "\\boldsymbol{\\Sigma}"
    };
    // Caligraphic family \cA … \cZ → \mathcal{A} … \mathcal{Z}
    for (let i = 0; i < 26; i++) {
      const L = String.fromCharCode(65 + i);
      m["\\c" + L] = "\\mathcal{" + L + "}";
    }
    return m;
  }
  const _KATEX_MACROS = _buildMacros();

  // KaTeX auto-render wrapper. KaTeX exposes window.renderMathInElement
  // when contrib/auto-render.min.js loads after katex.min.js.
  function renderMath(root) {
    if (typeof renderMathInElement !== "function") return;
    try {
      renderMathInElement(root || document.body, {
        delimiters: [
          { left: "$$", right: "$$", display: true  },
          { left: "$",  right: "$",  display: false },
          { left: "\\(", right: "\\)", display: false },
          { left: "\\[", right: "\\]", display: true  }
        ],
        macros: _KATEX_MACROS,
        // Don't blow up on unknown commands — just leave them as text.
        throwOnError: false,
        ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code"]
      });
    } catch (e) {
      console.warn("KaTeX render failed:", e);
    }
  }

  function getQueryParam(name) {
    const u = new URL(window.location.href);
    return u.searchParams.get(name);
  }

  // Escape user / data text before injecting into innerHTML. Used widely.
  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function el(tag, attrs, children) {
    const e = document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        if (k === "class") e.className = attrs[k];
        else if (k === "html") e.innerHTML = attrs[k];
        else e.setAttribute(k, attrs[k]);
      }
    }
    if (children) {
      for (const c of children) {
        if (c == null) continue;
        e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
      }
    }
    return e;
  }

  global.Authomathics = {
    relPath: relPath,
    fetchJson: fetchJson,
    loadManifest: loadManifest,
    renderMath: renderMath,
    getQueryParam: getQueryParam,
    esc: esc,
    el: el
  };
})(window);
