// Shared helpers for the Authomathics portal: fetch, manifest cache, KaTeX render.
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
