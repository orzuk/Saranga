// Pair viewer. Reads ?id=<pair_id>, looks the pair up in the manifest
// for its status + paper info, and (when an alignment JSON exists)
// fetches data/pairs/<file>.json to render the matches table.
//
// When no alignment JSON exists yet (status: ready/partial/pending), the
// page renders only the metadata card so the pair is still discoverable.

(function () {
  "use strict";

  const esc = Authomathics.esc;

  function matchPillClass(t) {
    const k = String(t || "").toLowerCase();
    if (k === "exact") return "exact";
    if (k === "analogous" || k === "analogue") return "analogous";
    return "none";
  }

  function arxivUrl(arxiv_id) {
    if (!arxiv_id) return null;
    const cleaned = String(arxiv_id).replace(/^arXiv:/i, "");
    return "https://arxiv.org/abs/" + encodeURIComponent(cleaned);
  }

  function paperLinkHTML(side) {
    side = side || {};
    const title = side.title || side.short_name || side.arxiv_id || "?";
    const ax = side.arxiv_id;
    const pieces = [];
    if (side.extracted && side.paper_dir && side.tier != null) {
      const url = "paper.html?tier=" + encodeURIComponent(side.tier) +
                  "&id=" + encodeURIComponent(side.paper_dir);
      pieces.push('<a href="' + url + '">' + esc(title) + "</a>");
    } else {
      pieces.push("<span>" + esc(title) + "</span>");
    }
    if (ax) {
      const url = arxivUrl(ax);
      pieces.push(' <small>(<a href="' + url +
        '" target="_blank" rel="noopener">' + esc(ax) + "</a>)</small>");
    } else if (side.short_name && side.short_name !== title) {
      pieces.push(' <small>(' + esc(side.short_name) + ")</small>");
    }
    if (side.year) {
      pieces.push(' <small style="color:#9aa0a6">' + esc(side.year) + "</small>");
    }
    if (!side.extracted) {
      pieces.push(' <span class="status-pill status-pending" style="margin-left:6px">' +
        "not extracted</span>");
    }
    return pieces.join("");
  }

  function renderHeader(entry) {
    const headerEl = document.getElementById("pair-header");
    const titleEl = document.getElementById("pair-title");
    const a = entry.paper_a || {};
    const b = entry.paper_b || {};
    const status = entry.status || "?";
    const name = entry.alignment_name || entry.pair_id;
    titleEl.textContent = name;

    const parts = [];
    parts.push('<h2>' + esc(name) +
      ' <span class="status-pill status-' + esc(status) + '" ' +
      'style="vertical-align:middle;margin-left:8px">' +
      esc(status) + "</span></h2>");
    parts.push('<div class="papers"><strong>A:</strong> ' +
      paperLinkHTML(a) + "</div>");
    parts.push('<div class="papers"><strong>B:</strong> ' +
      paperLinkHTML(b) + "</div>");
    const metaBits = [];
    if (entry.relation_type) {
      metaBits.push('<strong>Relation:</strong> ' +
        '<span class="relation-pill">' + esc(entry.relation_type) + "</span>");
    }
    if (entry.math_category) {
      metaBits.push('<strong>Category:</strong> ' + esc(entry.math_category));
    }
    if (entry.annotator) {
      metaBits.push('<strong>Annotator:</strong> ' + esc(entry.annotator));
    }
    if (metaBits.length) {
      parts.push('<div class="papers" style="margin-top:6px">' +
        metaBits.join(" &middot; ") + "</div>");
    }
    if (entry.why_related) {
      parts.push('<div class="description"><strong>Why related:</strong> ' +
        esc(entry.why_related) + "</div>");
    }
    headerEl.innerHTML = parts.join("");
  }

  function renderMatches(matches) {
    const root = document.getElementById("matches");
    root.innerHTML = "";

    if (!matches || matches.length === 0) {
      root.innerHTML = '<div class="empty">No match entries.</div>';
      return;
    }

    const tbl = document.createElement("table");
    tbl.className = "listing matches-table";
    tbl.innerHTML =
      "<thead><tr>" +
      "<th>#</th>" +
      "<th>Paper A nodes</th>" +
      "<th>Paper B nodes</th>" +
      "<th>Match</th>" +
      "<th>Explanation</th>" +
      "</tr></thead><tbody></tbody>";
    root.appendChild(tbl);
    const tbody = tbl.querySelector("tbody");

    matches.forEach(function (m, i) {
      const tr = document.createElement("tr");
      const aNodes = (m.paper_a_nodes || []).map(esc).join("\n");
      const bNodes = (m.paper_b_nodes || []).map(esc).join("\n");
      const cls = matchPillClass(m.match_type);
      tr.innerHTML =
        "<td>" + (i + 1) + "</td>" +
        '<td class="nodes-cell">' + (aNodes || '<span class="empty">&mdash;</span>') + "</td>" +
        '<td class="nodes-cell">' + (bNodes || '<span class="empty">&mdash;</span>') + "</td>" +
        '<td><span class="match-pill ' + cls + '">' +
            esc(m.match_type || "?") + "</span></td>" +
        '<td class="expl-cell">' + esc(m.explanation || "") + "</td>";
      tbody.appendChild(tr);
    });

    Authomathics.renderMath(root);
  }

  function renderNoAlignmentNotice(entry) {
    const root = document.getElementById("matches");
    const heading = document.getElementById("matches-heading");
    if (heading) heading.textContent = "Status";
    let msg, hint;
    switch (entry.status) {
      case "ready":
        msg = "Both papers have been extracted, but no alignment JSON " +
              "has been written yet.";
        hint = "Click either paper above to view its node graph.";
        break;
      case "partial":
        msg = "Only one of the two papers has been extracted so far.";
        hint = "The extracted paper is linked above.";
        break;
      case "pending":
      default:
        msg = "Neither paper has been extracted yet; this pair only " +
              "exists as a row in the master pairs CSV.";
        hint = "When the source PDFs are processed, this page will " +
               "automatically pick them up.";
        break;
    }
    root.innerHTML =
      '<div class="notice">' + esc(msg) +
      '<div style="margin-top:6px;font-size:13px;color:#6a6a6a">' +
      esc(hint) + "</div></div>";
  }

  document.addEventListener("DOMContentLoaded", async function () {
    const id = Authomathics.getQueryParam("id");
    const titleEl = document.getElementById("pair-title");
    const headerEl = document.getElementById("pair-header");

    if (!id) {
      titleEl.textContent = "No pair id";
      return;
    }

    let manifest;
    try {
      manifest = await Authomathics.loadManifest();
    } catch (e) {
      titleEl.textContent = "Failed to load manifest";
      headerEl.innerHTML = '<div class="empty">' + esc(e.message) + "</div>";
      return;
    }

    // Find the pair entry by id (also tolerate the legacy "<id>_alignment"
    // form which used to be the URL fragment).
    let entry = (manifest.pairs || []).find(function (p) {
      return p.pair_id === id;
    });
    if (!entry && id.endsWith("_alignment")) {
      const stripped = id.slice(0, -"_alignment".length);
      entry = (manifest.pairs || []).find(function (p) {
        return p.pair_id === stripped;
      });
    }

    if (!entry) {
      titleEl.textContent = id;
      headerEl.innerHTML =
        '<h2>' + esc(id) + "</h2>" +
        '<div class="notice">Pair id not found in manifest. ' +
        "It may have been renamed or removed from the master CSV.</div>";
      document.getElementById("matches").innerHTML = "";
      const heading = document.getElementById("matches-heading");
      if (heading) heading.style.display = "none";
      return;
    }

    renderHeader(entry);

    if (entry.alignment_available && entry.alignment_file) {
      try {
        const data = await Authomathics.fetchJson(
          "data/pairs/" + entry.alignment_file);
        // Header may carry a richer description in the alignment JSON;
        // append it if present and we don't already have it.
        if (data && data.metadata && data.metadata.description &&
            !entry.why_related) {
          headerEl.insertAdjacentHTML("beforeend",
            '<div class="description">' +
            esc(data.metadata.description) + "</div>");
        }
        renderMatches(data.matches || []);
      } catch (e) {
        document.getElementById("matches").innerHTML =
          '<div class="notice">Could not load alignment JSON: ' +
          esc(e.message) + "</div>";
      }
    } else {
      renderNoAlignmentNotice(entry);
    }

    Authomathics.renderMath(document.body);

    // ---------------- Tabs (Matches / Alignment graph) ----------------
    function activateTab(name) {
      for (const t of ["matches", "graph"]) {
        const btn = document.getElementById("tabbtn-" + t);
        const pane = document.getElementById("tab-" + t);
        if (btn) btn.classList.toggle("active", t === name);
        if (pane) pane.classList.toggle("active", t === name);
      }
      if (name === "graph") {
        loadGraph(false);
      }
    }

    function buildRenderUrl(force) {
      const sel = document.getElementById("graph-mode");
      const mode = (sel && sel.value) || "S";
      let u = "/render_alignment?id=" + encodeURIComponent(id) + "&mode=" + mode;
      if (force) u += "&nocache=1&_=" + Date.now();
      return u;
    }

    function loadGraph(force) {
      const iframe = document.getElementById("graph-iframe");
      const status = document.getElementById("graph-status");
      const openLink = document.getElementById("graph-open-tab");
      const url = buildRenderUrl(force);
      if (openLink) openLink.href = buildRenderUrl(false);
      if (!entry.alignment_available) {
        if (status) status.textContent =
          "No alignment annotation yet — graph view requires an annotated alignment.";
        iframe.removeAttribute("src");
        iframe.srcdoc = '<div style="font:13px sans-serif;padding:24px;color:#666">' +
          'Alignment graph not available — pair status is <b>' + esc(entry.status || "unknown") +
          "</b>. The graph view appears once an alignment JSON is annotated for this pair.</div>";
        return;
      }
      if (status) status.textContent = force ? "Re-rendering..." : "Loading...";
      iframe.removeAttribute("srcdoc");
      iframe.onload = function () {
        if (status) status.textContent = "(check banner in top-right of graph for cache status)";
      };
      iframe.src = url;
    }

    // If alignment is missing, disable the graph tab visually but keep the
    // tab button so the user understands what *would* be there.
    if (!entry.alignment_available) {
      const gbtn = document.getElementById("tabbtn-graph");
      if (gbtn) {
        gbtn.title = "No alignment annotation yet for this pair";
        gbtn.style.opacity = "0.55";
      }
    }

    for (const t of ["matches", "graph"]) {
      const btn = document.getElementById("tabbtn-" + t);
      if (btn) btn.addEventListener("click", function () { activateTab(t); });
    }
    const rebuild = document.getElementById("graph-force-rebuild");
    if (rebuild) rebuild.addEventListener("click", function () { loadGraph(true); });
    const modeSel = document.getElementById("graph-mode");
    if (modeSel) modeSel.addEventListener("change", function () { loadGraph(false); });
  });
})();
