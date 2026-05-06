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

  // Map short relation codes to their full names; convert underscores
  // in already-full names ('parallel_rediscovery' -> 'parallel rediscovery').
  // Keeps the Rel column human-readable and consistent across rows.
  const REL_DISPLAY = {
    EXT: "extension",
    AP:  "application",
    PR:  "precursor",
    BI:  "bidirectional",
    CF:  "counterfactual",
    SM:  "similar",
    SP:  "specialization",
    NEG: "negative",
  };
  function relDisplay(rt) {
    if (!rt) return "?";
    const upper = String(rt).toUpperCase();
    if (REL_DISPLAY[upper]) return REL_DISPLAY[upper];
    return String(rt).replace(/_/g, " ");
  }

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
      let rows = (manifest.papers && manifest.papers[tierKey]) || [];
      if (cfg.tier === 1) rows = collapseTier1Versions(rows);
      allRows = rows;
      sortKey = "paper_id";
      renderPapers();
    } else {
      allRows = manifest.pairs || [];
      sortKey = "pair_id";
      renderPairs();
    }
  }

  // Tier 1 ships three extractions per paper (manual / anthropic / openai)
  // as separate JSONs named <id>_<variant>.json. Collapse the 3 entries into
  // one row so the table shows one row per paper with three version links.
  function collapseTier1Versions(rows) {
    const SUFFIXES = ["_manual", "_anthropic", "_openai"];
    const groups = new Map();
    for (const r of rows) {
      let base = r.paper_id, variant = null;
      for (const s of SUFFIXES) {
        if (base.endsWith(s)) { variant = s.slice(1); base = base.slice(0, -s.length); break; }
      }
      if (!variant) {
        // Fall back: keep ungrouped row as-is
        groups.set(r.paper_id, Object.assign({}, r, { versions: {} }));
        continue;
      }
      if (!groups.has(base)) groups.set(base, { paper_id: base, versions: {} });
      const g = groups.get(base);
      g.versions[variant] = r.paper_id; // suffixed id used in paper.html link
      // Prefer manual stats; fall back to whichever appeared first.
      if (variant === "manual" || g.n_nodes == null) {
        g.title = r.title;
        g.n_nodes = r.n_nodes;
        g.buckets = r.buckets;
        g.top_node_types = r.top_node_types;
      }
    }
    return [...groups.values()];
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
    const versionHeader = (cfg.tier === 1)
      ? '<th title="Three independent extractions of each gold-standard paper: manual hand-coded, Claude Opus, and OpenAI GPT">Versions</th>'
      : "";
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
      versionHeader +
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
    const colspan = (cfg.tier === 1) ? 10 : 9;
    if (view.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = '<td colspan="' + colspan + '" class="empty">No papers match.</td>';
      tbody.appendChild(tr);
    }
    function fmt(n) { return (n && n > 0) ? String(n) : '<span style="color:#bbb">&ndash;</span>'; }
    function paperUrl(id) {
      return "paper.html?tier=" + cfg.tier + "&id=" + encodeURIComponent(id);
    }
    for (const r of view) {
      const tr = document.createElement("tr");
      // Tier 1: paper_id link points to the manual version (the gold reference);
      // Versions column links each of the three extractions independently.
      const primaryId = (cfg.tier === 1 && r.versions && r.versions.manual)
        ? r.versions.manual : r.paper_id;
      const url = paperUrl(primaryId);
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
      let versionsCell = "";
      if (cfg.tier === 1 && r.versions) {
        const vs = r.versions;
        const link = function (id, label, title) {
          if (!id) return '<span style="color:#bbb" title="' + title + ' (missing)">' + label + '</span>';
          return '<a href="' + paperUrl(id) + '" title="' + title + '">' + label + '</a>';
        };
        versionsCell =
          '<td style="white-space:nowrap;font-family:monospace;font-size:12px">' +
            link(vs.manual,    "M", "Manual gold (hand-coded)") + " | " +
            link(vs.anthropic, "C", "Claude Opus extraction") + " | " +
            link(vs.openai,    "G", "OpenAI GPT extraction") +
          '</td>';
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
        '<td style="text-align:right">' + fmt(b.other) + "</td>" +
        versionsCell;
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
      '<th data-k="n_positive_matches" style="text-align:right" title="Positive matches (exact + analogous) / total annotated pairs (positives + non-matches)">Matches&nbsp;(+&thinsp;/&thinsp;total)</th>' +
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
      // Show "positive / total" so the user can see annotated non-matches
      // are included in the total and don't mistake them for true matches.
      let matchesCell;
      if (r.n_matches == null || r.n_matches === 0) {
        matchesCell = '<span style="color:#bbb">&ndash;</span>';
      } else if (r.n_positive_matches != null) {
        matchesCell = String(r.n_positive_matches) +
          ' <span style="color:#999">/ ' + String(r.n_matches) + '</span>';
      } else {
        matchesCell = String(r.n_matches);
      }
      tr.innerHTML =
        '<td><a href="' + url + '">' + esc(r.pair_id) + "</a></td>" +
        "<td>" + paperLabel(r.paper_a, r.paper_a_title, r.paper_a_id) + "</td>" +
        "<td>" + paperLabel(r.paper_b, r.paper_b_title, r.paper_b_id) + "</td>" +
        '<td><span class="relation-pill">' + esc(relDisplay(r.relation_type)) + "</span></td>" +
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
