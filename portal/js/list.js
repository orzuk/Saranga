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
  let filterStatus = "all";

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
        if (ok && filterStatus !== "all") {
          ok = (r.status || "") === filterStatus;
        }
        if (ok && q) {
          // Pull both legacy fields (paper_a_title/paper_b_title) and the
          // new nested shape (paper_a.title, paper_b.title) so the search
          // works whether the manifest is pre- or post-expansion.
          const a = r.paper_a || {};
          const b = r.paper_b || {};
          const hay = (
            r.pair_id + " " +
            (r.paper_a_title || a.title || "") + " " +
            (r.paper_b_title || b.title || "") + " " +
            (a.short_name || "") + " " + (b.short_name || "")
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
    function getVal(row, key) {
      if (key && key.indexOf("bucket_") === 0) {
        const b = row.buckets || {};
        return b[key.slice("bucket_".length)] || 0;
      }
      return row[key];
    }
    view.sort(function (a, b) {
      let av = getVal(a, k), bv = getVal(b, k);
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
      '<th data-k="n_nodes" style="text-align:right">Nodes</th>' +
      '<th data-k="bucket_def"   style="text-align:right" title="Definitions">Def</th>' +
      '<th data-k="bucket_thm"   style="text-align:right" title="Theorem-like: theorem, lemma, proposition, corollary, claim, conjecture">Thm-like</th>' +
      '<th data-k="bucket_alg"   style="text-align:right" title="Algorithms">Alg</th>' +
      '<th data-k="bucket_pf"    style="text-align:right" title="Proofs">Proofs</th>' +
      '<th data-k="bucket_steps" style="text-align:right" title="Level-2 step decomposition: proof_step + algorithm_step">Steps</th>' +
      '<th data-k="bucket_other" style="text-align:right" title="Other: equation, problem, open_problem, assumption, example, remark">Other</th>' +
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
      tr.innerHTML = '<td colspan="9" class="empty">No papers match.</td>';
      tbody.appendChild(tr);
    }
    function fmt(n) { return (n && n > 0) ? String(n) : '<span style="color:#bbb">&ndash;</span>'; }
    for (const r of view) {
      const tr = document.createElement("tr");
      const url = "paper.html?tier=" + cfg.tier + "&id=" + encodeURIComponent(r.paper_id);
      // Buckets: prefer the structured field; fall back to recomputing from
      // top_node_types if the manifest predates the bucket columns.
      let b = r.buckets;
      if (!b) {
        const counts = {};
        (r.top_node_types || []).forEach(function (pair) { counts[pair[0]] = pair[1]; });
        const sumOf = function (types) {
          return types.reduce(function (s, t) { return s + (counts[t] || 0); }, 0);
        };
        b = {
          def:   sumOf(["definition"]),
          thm:   sumOf(["theorem","lemma","proposition","corollary","claim","conjecture"]),
          alg:   sumOf(["algorithm"]),
          pf:    sumOf(["proof"]),
          steps: sumOf(["proof_step","algorithm_step"]),
          other: sumOf(["equation","problem","open_problem","assumption","example","remark"]),
        };
      }
      tr.innerHTML =
        '<td><a href="' + url + '">' + esc(r.paper_id) + "</a></td>" +
        "<td>" + esc(r.title || "(untitled)") + "</td>" +
        '<td style="text-align:right">' + (r.n_nodes || 0) + "</td>" +
        '<td style="text-align:right">' + fmt(b.def)   + "</td>" +
        '<td style="text-align:right">' + fmt(b.thm)   + "</td>" +
        '<td style="text-align:right">' + fmt(b.alg)   + "</td>" +
        '<td style="text-align:right">' + fmt(b.pf)    + "</td>" +
        '<td style="text-align:right">' + fmt(b.steps) + "</td>" +
        '<td style="text-align:right">' + fmt(b.other) + "</td>";
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
      '  <option value="SP">SP (specialization)</option>' +
      '  <option value="NEG">NEG (negative)</option>' +
      "</select>" +
      '<select id="status-filter" title="Filter by extraction / annotation status">' +
      '  <option value="all">all statuses</option>' +
      '  <option value="annotated">annotated (v2 with-steps)</option>' +
      '  <option value="legacy">legacy (v1 only)</option>' +
      '  <option value="ready">ready</option>' +
      '  <option value="partial">partial</option>' +
      '  <option value="pending">pending</option>' +
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
      '<th data-k="status">Status</th>' +
      '<th data-k="n_matches" style="text-align:right">Matches</th>' +
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
    document.getElementById("status-filter").addEventListener("change", function (e) {
      filterStatus = e.target.value;
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
      tr.innerHTML = '<td colspan="6" class="empty">No pairs match.</td>';
      tbody.appendChild(tr);
    }
    function paperLabel(side, legacyTitle, legacyId) {
      side = side || {};
      // Prefer the most informative thing we have.
      const t = side.title || legacyTitle || side.short_name || side.arxiv_id ||
                legacyId || "?";
      return esc(t);
    }
    for (const r of view) {
      const tr = document.createElement("tr");
      const url = "pair.html?id=" + encodeURIComponent(r.pair_id);
      const status = r.status || (r.alignment_available ? "annotated" : "");
      const matchesCell = (r.n_matches != null && r.n_matches > 0)
        ? String(r.n_matches)
        : '<span style="color:#bbb">&ndash;</span>';
      tr.innerHTML =
        '<td><a href="' + url + '">' + esc(r.pair_id) + "</a></td>" +
        "<td>" + paperLabel(r.paper_a, r.paper_a_title, r.paper_a_id) + "</td>" +
        "<td>" + paperLabel(r.paper_b, r.paper_b_title, r.paper_b_id) + "</td>" +
        '<td><span class="relation-pill">' + esc(r.relation_type || "?") + "</span></td>" +
        '<td><span class="status-pill status-' + esc(status) + '">' +
            esc(status || "?") + "</span></td>" +
        '<td style="text-align:right">' + matchesCell + "</td>";
      tbody.appendChild(tr);
    }
    document.getElementById("count-line").textContent =
      view.length + " of " + allRows.length + " pairs";
    if (typeof Authomathics !== "undefined" && Authomathics.renderMath) {
      Authomathics.renderMath(tbody);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    Authomathics.loadManifest().then(init);
  });
})();
