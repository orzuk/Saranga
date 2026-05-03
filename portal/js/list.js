// Generic list view used by papers_tier{1,2,3}.html and pairs.html.
//
// The owning HTML page sets `window.AuthomathicsListConfig` to one of:
//   { mode: "papers", tier: 1|2|3 }
//   { mode: "pairs" }
// before this script runs.

(function () {
  "use strict";

  const cfg = window.AuthomathicsListConfig || { mode: "papers", tier: 1 };
  const esc = Authomathics.esc;

  let allRows = [];
  let view = [];
  let sortKey = null;
  let sortDir = 1;
  let filterText = "";
  let filterRel = "all";

  function init(manifest) {
    if (cfg.mode === "papers") {
      const tierKey = "tier" + cfg.tier;
      allRows = (manifest.papers && manifest.papers[tierKey]) || [];
      sortKey = "paper_id";
      renderPapers();
    } else {
      allRows = manifest.pairs || [];
      sortKey = "pair_id";
      renderPairs();
    }
  }

  function applyFilter() {
    const q = filterText.trim().toLowerCase();
    view = allRows.filter(function (r) {
      if (cfg.mode === "papers") {
        if (!q) return true;
        const hay = (r.paper_id + " " + (r.title || "")).toLowerCase();
        return hay.indexOf(q) !== -1;
      } else {
        let ok = true;
        if (filterRel !== "all") {
          ok = (r.relation_type || "").toUpperCase() === filterRel.toUpperCase();
        }
        if (ok && q) {
          const hay = (
            r.pair_id + " " +
            (r.paper_a_title || "") + " " + (r.paper_b_title || "")
          ).toLowerCase();
          ok = hay.indexOf(q) !== -1;
        }
        return ok;
      }
    });
    sortView();
  }

  function sortView() {
    if (!sortKey) return;
    const k = sortKey, d = sortDir;
    view.sort(function (a, b) {
      let av = a[k], bv = b[k];
      if (av == null) av = "";
      if (bv == null) bv = "";
      if (typeof av === "number" && typeof bv === "number") {
        return (av - bv) * d;
      }
      return String(av).localeCompare(String(bv)) * d;
    });
  }

  function setSort(k) {
    if (sortKey === k) sortDir = -sortDir;
    else { sortKey = k; sortDir = 1; }
    sortView();
    if (cfg.mode === "papers") renderPapersBody();
    else renderPairsBody();
  }

  function renderPapers() {
    const main = document.getElementById("listing");
    if (!main) return;
    main.innerHTML = "";

    const toolbar = document.createElement("div");
    toolbar.className = "toolbar";
    toolbar.innerHTML =
      '<input type="text" id="q" placeholder="Search by paper id or title..." />' +
      '<span class="count" id="count-line"></span>';
    main.appendChild(toolbar);

    const tbl = document.createElement("table");
    tbl.className = "listing";
    tbl.innerHTML =
      "<thead><tr>" +
      '<th data-k="paper_id">Paper ID</th>' +
      '<th data-k="title">Title</th>' +
      '<th data-k="n_nodes">Nodes</th>' +
      '<th>Top types</th>' +
      "</tr></thead><tbody></tbody>";
    main.appendChild(tbl);

    tbl.querySelectorAll("thead th[data-k]").forEach(function (th) {
      th.addEventListener("click", function () { setSort(th.getAttribute("data-k")); });
    });
    document.getElementById("q").addEventListener("input", function (e) {
      filterText = e.target.value;
      applyFilter();
      renderPapersBody();
    });

    applyFilter();
    renderPapersBody();
  }

  function renderPapersBody() {
    const tbody = document.querySelector("#listing table.listing tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    if (view.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = '<td colspan="4" class="empty">No papers match.</td>';
      tbody.appendChild(tr);
    }
    for (const r of view) {
      const tr = document.createElement("tr");
      const url = "paper.html?tier=" + cfg.tier + "&id=" + encodeURIComponent(r.paper_id);
      const types = (r.top_node_types || []).slice(0, 4).map(function (t) {
        return esc(t[0]) + ":" + t[1];
      }).join("  ");
      tr.innerHTML =
        '<td><a href="' + url + '">' + esc(r.paper_id) + "</a></td>" +
        "<td>" + esc(r.title || "(untitled)") + "</td>" +
        "<td>" + (r.n_nodes || 0) + "</td>" +
        '<td class="types">' + types + "</td>";
      tbody.appendChild(tr);
    }
    document.getElementById("count-line").textContent =
      view.length + " of " + allRows.length + " papers";
  }

  function renderPairs() {
    const main = document.getElementById("listing");
    if (!main) return;
    main.innerHTML = "";

    const toolbar = document.createElement("div");
    toolbar.className = "toolbar";
    toolbar.innerHTML =
      '<input type="text" id="q" placeholder="Search by pair id, paper title..." />' +
      '<select id="rel">' +
      '  <option value="all">all relations</option>' +
      '  <option value="EXT">EXT (extension)</option>' +
      '  <option value="AP">AP (application)</option>' +
      '  <option value="PR">PR (precursor)</option>' +
      '  <option value="BI">BI (bidirectional)</option>' +
      '  <option value="CF">CF (counterfactual)</option>' +
      '  <option value="SM">SM (similar)</option>' +
      '  <option value="NEG">NEG (negative)</option>' +
      "</select>" +
      '<span class="count" id="count-line"></span>';
    main.appendChild(toolbar);

    const tbl = document.createElement("table");
    tbl.className = "listing";
    tbl.innerHTML =
      "<thead><tr>" +
      '<th data-k="pair_id">Pair</th>' +
      '<th data-k="paper_a_title">Paper A</th>' +
      '<th data-k="paper_b_title">Paper B</th>' +
      '<th data-k="relation_type">Rel</th>' +
      '<th data-k="n_matches">Matches</th>' +
      "</tr></thead><tbody></tbody>";
    main.appendChild(tbl);

    tbl.querySelectorAll("thead th[data-k]").forEach(function (th) {
      th.addEventListener("click", function () { setSort(th.getAttribute("data-k")); });
    });
    document.getElementById("q").addEventListener("input", function (e) {
      filterText = e.target.value;
      applyFilter();
      renderPairsBody();
    });
    document.getElementById("rel").addEventListener("change", function (e) {
      filterRel = e.target.value;
      applyFilter();
      renderPairsBody();
    });

    applyFilter();
    renderPairsBody();
  }

  function renderPairsBody() {
    const tbody = document.querySelector("#listing table.listing tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    if (view.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = '<td colspan="5" class="empty">No pair alignments match.</td>';
      tbody.appendChild(tr);
    }
    for (const r of view) {
      const tr = document.createElement("tr");
      const url = "pair.html?id=" + encodeURIComponent(r.pair_id);
      tr.innerHTML =
        '<td><a href="' + url + '">' + esc(r.pair_id) + "</a></td>" +
        "<td>" + esc(r.paper_a_title || r.paper_a_id || "?") + "</td>" +
        "<td>" + esc(r.paper_b_title || r.paper_b_id || "?") + "</td>" +
        '<td><span class="relation-pill">' + esc(r.relation_type || "?") + "</span></td>" +
        "<td>" + (r.n_matches || 0) + "</td>";
      tbody.appendChild(tr);
    }
    document.getElementById("count-line").textContent =
      view.length + " of " + allRows.length + " pairs";
  }

  document.addEventListener("DOMContentLoaded", function () {
    Authomathics.loadManifest().then(init);
  });
})();
