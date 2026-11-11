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
  const PAGE_SIZE = 50;
  let page = 0;
  let filterRel = "all";
  let filterStatus = "all";

  function init(manifest) {
    if (cfg.mode === "papers") {
      const tierKey = "tier" + cfg.tier;
      let rows = (manifest.papers && manifest.papers[tierKey]) || [];
      if (cfg.tier === 1) rows = collapseTier1Versions(rows);

      // Tier 3 (whole arXiv): the category grid from manifest.tier3_index (data/tier3_<version>/index.json),
      // grouped by field; a category's papers are listed one year at a time, <cat>/<year>.json next to it.
      if (cfg.tier === 3) {
        var t3Index = manifest.tier3_index || "data/tier3_all/index.json";
        var here = new URL(window.location.href).searchParams;
        var catParam = here.get("cat");
        Authomathics.fetchJson(t3Index).then(function (ix) {
          var cats = ix.categories || [];
          if (!catParam) { renderCategoryGrid(cats); return; }
          var info = cats.find(function (c) { return c.category === catParam; });
          var years = info && info.years ? Object.keys(info.years).sort() : [];
          // default: the latest year with a full list (the last bundle year holds a handful of early papers)
          var full = years.filter(function (y) { return info.years[y] >= 100; });
          var year = here.get("year") || (full.length ? full[full.length - 1] : years[years.length - 1]);
          renderYearBar(catParam, years, year, info ? info.years : {});
          if (!year) return;
          Authomathics.fetchJson(t3Index.replace(/index\.json$/, "") + encodeURIComponent(catParam) + "/" + year + ".json").then(function (r3) {
            allRows = r3;
            sortKey = "paper_id";
            renderPapers();
          });
        });
        return;
      }

      if (cfg.tier === 2) {
        var cat2 = new URL(window.location.href).searchParams.get("cat");
        if (!cat2) {
          var counts = {};
          rows.forEach(function (r) {
            var c = r.category || "unknown";
            counts[c] = counts[c] || { category: c, count: 0, avg_nodes: 0 };
            counts[c].count++; counts[c].avg_nodes += (r.n_nodes || 0);
          });
          var cats = Object.keys(counts).map(function (k) {
            var c = counts[k]; c.avg_nodes = c.avg_nodes / c.count; return c;
          });
          renderCategoryGrid(cats, "papers_tier2.html", "all");
          return;
        }
        if (cat2 !== "all") rows = rows.filter(function (r) { return r.category === cat2; });
      }
      allRows = rows;
      sortKey = "paper_id";
      renderPapers();
    } else {
      allRows = manifest.pairs || [];
      sortKey = "pair_id";
      renderPairs();
    }
  }

  function renderYearBar(cat, years, year, counts) {
    var bar = document.getElementById("t3-years");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "t3-years";
      bar.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px;font-size:13px;";
      var listing = document.getElementById("listing");
      listing.parentNode.insertBefore(bar, listing);
    }
    bar.innerHTML = years.map(function (y) {
      var on = y === year;
      return '<a href="papers_tier3.html?cat=' + encodeURIComponent(cat) + '&year=' + y + '" title="' + counts[y] + ' papers" style="padding:3px 8px;border-radius:4px;text-decoration:none;' +
        (on ? 'background:#34495e;color:#fff' : 'background:#eef1f4;color:#34495e') + '">' + y + '</a>';
    }).join("");
  }

  function renderCategoryGrid(rows, page, allKey) {
    page = page || "papers_tier3.html";
    var main = document.getElementById("listing");
    if (!main) return;
    main.innerHTML = "";

    // rows: [{category, count, avg_nodes, field?}] from the Tier-3 index
    var total = 0, fields = {};
    for (var i = 0; i < rows.length; i++) {
      var f = rows[i].field || "";
      (fields[f] = fields[f] || []).push(rows[i]);
      total += rows[i].count;
    }
    var heading = document.createElement("p");
    heading.style.cssText = "color:#6a6a6a;font-size:14px;margin-bottom:18px";
    heading.innerHTML = rows.length + " categories, " + total.toLocaleString() + " papers total" +
      (allKey ? ' &middot; <a href="' + page + '?cat=' + allKey + '">show all</a>' : "");
    main.appendChild(heading);

    var order = Object.keys(fields).sort(function (a, b) {
      var na = fields[a].reduce(function (s, r) { return s + r.count; }, 0);
      var nb = fields[b].reduce(function (s, r) { return s + r.count; }, 0);
      return nb - na;
    });
    order.forEach(function (f) {
      var list = fields[f].slice().sort(function (a, b) { return a.category < b.category ? -1 : 1; });
      if (f) {
        var h = document.createElement("h3");
        var n = list.reduce(function (s, r) { return s + r.count; }, 0);
        h.style.cssText = "font-size:16px;color:#2c3e50;margin:22px 0 10px;";
        h.innerHTML = esc(f) + ' <span style="font-weight:400;font-size:13px;color:#888">' + list.length + " categories &middot; " + n.toLocaleString() + " papers</span>";
        main.appendChild(h);
      }
      var grid = document.createElement("div");
      grid.style.cssText = "display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;";
      list.forEach(function (r) {
        var card = document.createElement("a");
        card.href = page + "?cat=" + encodeURIComponent(r.category);
        card.style.cssText = "display:block;padding:16px;background:#fff;border:1px solid #e0e0e0;border-radius:8px;text-decoration:none;color:inherit;transition:box-shadow 0.15s;";
        card.onmouseover = function() { this.style.boxShadow = "0 2px 8px rgba(0,0,0,0.12)"; };
        card.onmouseout = function() { this.style.boxShadow = "none"; };
        card.innerHTML =
          '<div style="font-size:18px;font-weight:600;color:#2c3e50;margin-bottom:4px;">' + esc(r.category) + '</div>' +
          '<div style="font-size:13px;color:#888;">' + r.count.toLocaleString() + ' papers &middot; ' +
          Math.round(r.avg_nodes) + ' avg nodes</div>';
        grid.appendChild(card);
      });
      main.appendChild(grid);
    });
  }

  // Tier 1 ships three extractions per paper (manual / anthropic / openai)
  // as separate JSONs named <id>_<variant>.json. Collapse the 3 entries into
  // one row so the table shows one row per paper with three version links.
  function collapseTier1Versions(rows) {
    const SUFFIXES = ["_manual", "_rules", "_anthropic", "_openai"];
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
      if (!groups.has(base)) groups.set(base, { paper_id: base, versions: {}, provider_nodes: {}, provider_buckets: {} });
      const g = groups.get(base);
      g.versions[variant] = r.paper_id; // suffixed id used in paper.html link
      g.provider_nodes[variant] = r.n_nodes || 0;
      g.provider_buckets[variant] = r.buckets || null;
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
    page = 0;
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
      ? '<th title="Four independent extractions of each gold-standard paper: manual gold (M), rule-based regex (R), Claude Opus (C), and OpenAI GPT-4o (G)">Versions</th>'
      : (cfg.tier === 2 ? '<th title="The LLM graph and the rule-based graph of the same paper">Graphs</th>'
         : (cfg.tier === 3 ? '<th title="Built on first click">Graph</th>' : ""));
    tbl.innerHTML =
      "<thead><tr>" +
      '<th data-k="paper_id">Paper ID</th>' +
      '<th data-k="title">Title</th>' +
      '<th data-k="n_nodes" style="text-align:right">' + (cfg.tier === 1 ? 'Nodes (M/R/C/G)' : 'Nodes') + '</th>' +
      '<th data-k="bucket_def"   style="text-align:right" title="Definitions">' + (cfg.tier === 1 ? 'Def (M/R/C/G)' : 'Def') + '</th>' +
      '<th data-k="bucket_thm"   style="text-align:right" title="Theorem-like: theorem, lemma, proposition, corollary, claim, conjecture">' + (cfg.tier === 1 ? 'Thm (M/R/C/G)' : 'Thm-like') + '</th>' +
      '<th data-k="bucket_alg"   style="text-align:right" title="Algorithms">' + (cfg.tier === 1 ? 'Alg (M/R/C/G)' : 'Alg') + '</th>' +
      '<th data-k="bucket_pf"    style="text-align:right" title="Proofs">' + (cfg.tier === 1 ? 'Proofs (M/R/C/G)' : 'Proofs') + '</th>' +
      '<th data-k="bucket_other" style="text-align:right" title="Other: equation, problem, open_problem, assumption, example, remark">' + (cfg.tier === 1 ? 'Other (M/R/C/G)' : 'Other') + '</th>' +
      versionHeader +
      "</tr></thead><tbody></tbody>";
    main.appendChild(tbl);

    tbl.querySelectorAll("thead th[data-k]").forEach(function (th) {
      th.addEventListener("click", function () { setSort(th.getAttribute("data-k")); });
    });
    document.getElementById("q").addEventListener("input", function (e) {
      filterText = e.target.value;
      page = 0;
      applyFilter();
      renderPapersBody();
    });

    applyFilter();
    renderPapersBody();
  }

  function renderPager(pages) {
    let bar = document.getElementById("pager");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "pager";
      bar.style.cssText = "display:flex;gap:10px;align-items:center;justify-content:flex-end;margin:10px 0;font-size:13px;color:#555;";
      const tbl = document.querySelector("#listing table.listing");
      tbl.parentNode.insertBefore(bar, tbl.nextSibling);
    }
    bar.style.display = pages > 1 ? "flex" : "none";
    const btn = function (label, to, on) {
      return '<button data-p="' + to + '"' + (on ? "" : " disabled") + ' style="padding:3px 10px;border:1px solid #ccc;border-radius:4px;background:#fff;cursor:pointer">' + label + "</button>";
    };
    bar.innerHTML = btn("&laquo; Prev", page - 1, page > 0) +
      "<span>Page " + (page + 1) + " of " + pages.toLocaleString() + "</span>" + btn("Next &raquo;", page + 1, page < pages - 1);
    bar.querySelectorAll("button").forEach(function (b) {
      b.addEventListener("click", function () {
        page = +b.getAttribute("data-p");
        renderPapersBody();
        window.scrollTo(0, document.getElementById("listing").offsetTop);
      });
    });
  }

  function renderPapersBody() {
    const tbody = document.querySelector("#listing table.listing tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    const colspan = (cfg.tier === 1 || cfg.tier === 2 || cfg.tier === 3) ? 9 : 8;
    if (view.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = '<td colspan="' + colspan + '" class="empty">No papers match.</td>';
      tbody.appendChild(tr);
    }
    function fmt(n) { return (n && n > 0) ? String(n) : '<span style="color:#bbb">&ndash;</span>'; }
    function paperUrl(id) {
      var catq = "";
      if (cfg.tier === 3) {
        var sp = new URL(window.location.href).searchParams;
        catq = "&cat=" + encodeURIComponent(sp.get("cat") || "") + (sp.get("year") ? "&year=" + sp.get("year") : "");
      }
      return "paper.html?tier=" + cfg.tier + "&id=" + encodeURIComponent(id) + catq;
    }
    // one page of PAGE_SIZE rows (a year of a large category holds tens of thousands of papers)
    const pages = Math.max(1, Math.ceil(view.length / PAGE_SIZE));
    if (page >= pages) page = pages - 1;
    renderPager(pages);
    for (const r of view.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)) {
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
      if (cfg.tier === 2 && r.graph_path) {
        versionsCell = '<td style="white-space:nowrap">' +
          '<a href="' + r.graph_path + '" target="_blank" title="Claude Opus extraction">LLM</a>' +
          (r.graph_rules_path ? ' | <a href="' + r.graph_rules_path + '" target="_blank" title="Distilled rule-based extraction">rules</a>' : '') +
          '</td>';
      } else if (cfg.tier === 3 && r.graph_path) {
        versionsCell = '<td><a href="' + r.graph_path + '" target="_blank">graph</a></td>';
      }
      if (cfg.tier === 1 && r.versions) {
        const vs = r.versions;
        const link = function (id, label, title) {
          if (!id) return '<span style="color:#bbb" title="' + title + ' (missing)">' + label + '</span>';
          return '<a href="' + paperUrl(id) + '" title="' + title + '">' + label + '</a>';
        };
        versionsCell =
          '<td style="white-space:nowrap;font-family:monospace;font-size:12px">' +
            link(vs.manual,    "M", "Manual gold (hand-annotated)") + " | " +
            link(vs.rules,     "R", "Rule-based regex parser") + " | " +
            link(vs.anthropic, "C", "Claude Opus extraction") + " | " +
            link(vs.openai,    "G", "OpenAI GPT-4o extraction") +
          '</td>';
      }
      // Tier 1: show M/C/G for node counts and all bucket columns.
      var nodesCell, defCell, thmCell, algCell, pfCell, stepsCell, otherCell;
      if (cfg.tier === 1 && r.provider_buckets) {
        var pn = r.provider_nodes || {};
        var pb = r.provider_buckets;
        function mcg(field) {
          var bm = pb.manual || {}, br = pb.rules || {}, bc = pb.anthropic || {}, bg = pb.openai || {};
          return fmt(bm[field]) + ' / ' + fmt(br[field]) + ' / ' + fmt(bc[field]) + ' / ' + fmt(bg[field]);
        }
        nodesCell = (pn.manual || 0) + ' / ' + (pn.rules || 0) + ' / ' + (pn.anthropic || 0) + ' / ' + (pn.openai || 0);
        defCell = mcg('def'); thmCell = mcg('thm'); algCell = mcg('alg');
        pfCell = mcg('pf'); stepsCell = mcg('steps'); otherCell = mcg('other');
      } else {
        nodesCell = String(r.n_nodes || 0);
        defCell = fmt(b.def); thmCell = fmt(b.thm); algCell = fmt(b.alg);
        pfCell = fmt(b.pf); stepsCell = fmt(b.steps); otherCell = fmt(b.other);
      }
      var idCell = (cfg.tier === 1)
        ? '<td>' + esc(r.paper_id) + '</td>'
        : '<td><a href="' + url + '">' + esc(r.paper_id) + "</a></td>";
      tr.innerHTML =
        idCell +
        "<td>" + esc(r.title || "(untitled)") + "</td>" +
        '<td style="text-align:right">' + nodesCell + "</td>" +
        '<td style="text-align:right">' + defCell   + "</td>" +
        '<td style="text-align:right">' + thmCell   + "</td>" +
        '<td style="text-align:right">' + algCell   + "</td>" +
        '<td style="text-align:right">' + pfCell    + "</td>" +
        '<td style="text-align:right">' + otherCell + "</td>" +
        versionsCell;
      tbody.appendChild(tr);
    }
    document.getElementById("count-line").textContent =
      view.length.toLocaleString() + " of " + allRows.length.toLocaleString() + " papers";
    if (Authomathics.renderMath) Authomathics.renderMath(tbody);   // $...$ in titles
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
