// Paper viewer. Reads ?tier=N&id=PAPER_ID, fetches data/tierN/<id>.json,
// renders Overview / Nodes / Raw JSON tabs. Tolerates BOTH the simple
// {metadata, nodes, edges} shape AND the v2 {blocks, relations, ...} shape.

(function () {
  "use strict";

  const esc = Authomathics.esc;

  // Map common section/type labels to readable group titles.
  const TYPE_ORDER = [
    "definition", "assumption", "problem", "open_problem",
    "theorem", "lemma", "proposition", "corollary", "claim", "conjecture",
    "proof", "proof_step",
    "algorithm", "algorithm_step",
    "equation", "example", "exercise", "remark"
  ];

  function normalizeNodes(data) {
    // Returns {nodes: [...normalized...], shape: 'simple'|'v2', edges: [...]}
    if (Array.isArray(data.nodes)) {
      return { shape: "simple", nodes: data.nodes, edges: data.edges || [] };
    }
    if (Array.isArray(data.blocks)) {
      // v2 shape: blocks → translate to node-like dicts so the renderer is uniform
      const nodes = data.blocks.map(function (b) {
        return {
          id: b.id,
          type: b.type,
          name: b.name || b.label || null,
          number: b.number || null,
          section: b.number || null,
          statement: b.clean_text || b.statement || b.raw_latex || "",
          assumptions: (b.assumptions || []).map(function (a) {
            return typeof a === "string" ? a : (a.text || JSON.stringify(a));
          }),
          conclusions: (b.conclusions || []).map(function (c) {
            return typeof c === "string" ? c : (c.text || JSON.stringify(c));
          }),
          equations: b.equations || [],
          tags: b.tags || [],
          subclass: b.subclass || null,
          origin: b.origin || null,
          origin_citation: b.origin_citation || null
        };
      });
      return { shape: "v2", nodes: nodes, edges: data.relations || [] };
    }
    return { shape: "unknown", nodes: [], edges: [] };
  }

  function getMetadata(data) {
    if (data.metadata) return data.metadata;
    // v2: top-level fields are the metadata.
    return {
      title: data.title,
      paper_id: data.paper_id,
      authors: data.authors,
      arxiv_categories: data.arxiv_categories,
      abstract: data.abstract,
      schema_version: data.schema_version
    };
  }

  function arxivLink(paper_id) {
    if (!paper_id) return null;
    // Strip trailing version (v1, v2, ...) for the URL.
    const cleaned = String(paper_id).replace(/^arXiv:/i, "");
    return "https://arxiv.org/abs/" + encodeURIComponent(cleaned);
  }

  function buildHistogram(nodes) {
    const counts = {};
    for (const n of nodes) {
      const t = n.type || "unknown";
      counts[t] = (counts[t] || 0) + 1;
    }
    return Object.keys(counts).sort(function (a, b) {
      return counts[b] - counts[a];
    }).map(function (k) { return [k, counts[k]]; });
  }

  function renderOverview(meta, nodes, paperId) {
    const root = document.getElementById("tab-overview");
    root.innerHTML = "";

    const dl = document.createElement("dl");
    dl.className = "meta-grid";
    function pair(k, v) {
      if (v === null || v === undefined || v === "") return;
      const dt = document.createElement("dt"); dt.textContent = k;
      const dd = document.createElement("dd");
      dd.innerHTML = v;
      dl.appendChild(dt); dl.appendChild(dd);
    }
    pair("Paper ID", esc(paperId));
    pair("Title", esc(meta.title || "(untitled)"));
    if (meta.authors) {
      const a = Array.isArray(meta.authors) ? meta.authors.join(", ") : meta.authors;
      pair("Authors", esc(a));
    }
    if (meta.arxiv_categories) {
      const c = Array.isArray(meta.arxiv_categories)
        ? meta.arxiv_categories.join(", ") : meta.arxiv_categories;
      pair("arXiv categories", esc(c));
    }
    pair("Annotator", esc(meta.annotator || meta.model || ""));
    if (meta.extraction_date) pair("Extracted", esc(meta.extraction_date));
    const link = arxivLink(meta.paper_id || paperId);
    if (link) {
      pair("arXiv", '<a href="' + link + '" target="_blank" rel="noopener">' +
        esc(meta.paper_id || paperId) + "</a>");
    }
    if (meta.abstract) pair("Abstract", esc(meta.abstract));
    root.appendChild(dl);

    // Node-type histogram.
    const hist = buildHistogram(nodes);
    const histRoot = document.createElement("div");
    histRoot.className = "histogram";
    for (const [t, c] of hist) {
      const span = document.createElement("span");
      span.className = "bar";
      span.innerHTML = "<strong>" + c + "</strong> " + esc(t);
      histRoot.appendChild(span);
    }
    const h = document.createElement("h4");
    h.textContent = "Node-type histogram (" + nodes.length + " nodes total)";
    h.style.margin = "20px 0 8px";
    h.style.fontSize = "14px";
    root.appendChild(h);
    root.appendChild(histRoot);

    // Section TOC if section info is present.
    const sections = [];
    const seen = new Set();
    for (const n of nodes) {
      const s = n.section;
      if (s && !seen.has(s)) { seen.add(s); sections.push(s); }
    }
    if (sections.length > 0) {
      const h2 = document.createElement("h4");
      h2.textContent = "Sections referenced";
      h2.style.margin = "20px 0 8px";
      h2.style.fontSize = "14px";
      root.appendChild(h2);
      const ul = document.createElement("ul");
      ul.style.fontSize = "13px";
      for (const s of sections) {
        const li = document.createElement("li");
        li.textContent = s;
        ul.appendChild(li);
      }
      root.appendChild(ul);
    }
  }

  function nodeBodyHTML(n) {
    const bits = [];
    if (n.statement) {
      bits.push('<p>' + esc(n.statement) + '</p>');
    }
    if (n.assumptions && n.assumptions.length) {
      bits.push('<div class="label">Assumptions</div><ul>');
      for (const a of n.assumptions) bits.push("<li>" + esc(a) + "</li>");
      bits.push("</ul>");
    }
    if (n.conclusions && n.conclusions.length) {
      bits.push('<div class="label">Conclusions</div><ul>');
      for (const c of n.conclusions) bits.push("<li>" + esc(c) + "</li>");
      bits.push("</ul>");
    }
    if (n.equations && n.equations.length) {
      bits.push('<div class="label">Equations</div>');
      for (const eq of n.equations) {
        const tex = eq.raw_latex || eq.statement || "";
        bits.push("<p>" + esc(tex) + "</p>");
      }
    }
    const meta = [];
    if (n.subclass) meta.push("subclass: " + n.subclass);
    if (n.origin) meta.push("origin: " + n.origin);
    if (n.origin_citation) meta.push("citation: " + n.origin_citation);
    if (n.tags && n.tags.length) meta.push("tags: " + n.tags.join(", "));
    if (n.section && !n.number) meta.push("section: " + n.section);
    if (meta.length) {
      bits.push('<div class="label">Meta</div><p style="font-size:12px;color:#6a6a6a">'
        + esc(meta.join(" · ")) + "</p>");
    }
    return bits.join("\n");
  }

  function renderNodes(nodes) {
    const root = document.getElementById("tab-nodes");
    root.innerHTML = "";

    if (nodes.length === 0) {
      root.innerHTML = '<div class="empty">No nodes.</div>';
      return;
    }

    // Group by type, in TYPE_ORDER first then anything else alphabetical.
    const byType = {};
    for (const n of nodes) {
      const t = n.type || "unknown";
      (byType[t] = byType[t] || []).push(n);
    }
    const knownOrdered = TYPE_ORDER.filter(function (t) { return byType[t]; });
    const remaining = Object.keys(byType).filter(function (t) {
      return TYPE_ORDER.indexOf(t) === -1;
    }).sort();
    const orderedTypes = knownOrdered.concat(remaining);

    for (const t of orderedTypes) {
      const grp = document.createElement("div");
      grp.className = "type-group";
      const h = document.createElement("h3");
      h.textContent = t + " (" + byType[t].length + ")";
      grp.appendChild(h);
      for (const n of byType[t]) {
        const det = document.createElement("details");
        det.className = "node-card";
        det.id = "node-" + (n.id || "");
        const sum = document.createElement("summary");
        sum.innerHTML =
          '<span>' + esc(n.name || n.id || "(unnamed)") + '</span>' +
          '<span class="node-id">' + esc(n.id || "") + '</span>';
        det.appendChild(sum);
        const body = document.createElement("div");
        body.className = "node-body";
        body.innerHTML = nodeBodyHTML(n);
        det.appendChild(body);
        grp.appendChild(det);
      }
      root.appendChild(grp);
    }

    Authomathics.renderMath(root);
  }

  function renderRaw(data) {
    const root = document.getElementById("tab-raw");
    root.innerHTML = "";
    const pre = document.createElement("pre");
    pre.className = "raw-json";
    pre.textContent = JSON.stringify(data, null, 2);
    root.appendChild(pre);
  }

  function activateTab(name) {
    for (const t of ["overview", "nodes", "raw"]) {
      const btn = document.getElementById("tabbtn-" + t);
      const pane = document.getElementById("tab-" + t);
      if (btn) btn.classList.toggle("active", t === name);
      if (pane) pane.classList.toggle("active", t === name);
    }
    if (name === "nodes") {
      // Re-render math for any newly opened cards.
      Authomathics.renderMath(document.getElementById("tab-nodes"));
    }
  }

  document.addEventListener("DOMContentLoaded", async function () {
    const tier = Authomathics.getQueryParam("tier") || "1";
    const id = Authomathics.getQueryParam("id");
    const titleEl = document.getElementById("paper-title");
    const subtitleEl = document.getElementById("paper-subtitle");

    if (!id) {
      titleEl.textContent = "No paper id in URL";
      subtitleEl.textContent = "Use ?tier=N&id=PAPER_ID";
      return;
    }

    const tierDir = "tier" + tier;
    const url = "data/" + tierDir + "/" + id + ".json";
    let data;
    try {
      data = await Authomathics.fetchJson(url);
    } catch (e) {
      titleEl.textContent = "Failed to load " + id;
      subtitleEl.innerHTML = '<span style="color:#a33">' +
        esc(e.message) + "</span><br>Tried: " + esc(url);
      return;
    }

    const meta = getMetadata(data);
    const norm = normalizeNodes(data);

    titleEl.textContent = meta.title || id;
    const link = arxivLink(meta.paper_id || id);
    subtitleEl.innerHTML =
      "Tier " + esc(tier) + " &middot; " + norm.nodes.length + " nodes" +
      (link ? ' &middot; <a href="' + link + '" target="_blank" rel="noopener">arXiv</a>' : "");

    renderOverview(meta, norm.nodes, id);
    renderNodes(norm.nodes);
    renderRaw(data);
    activateTab("overview");
    Authomathics.renderMath(document.body);

    for (const t of ["overview", "nodes", "raw"]) {
      const btn = document.getElementById("tabbtn-" + t);
      if (btn) btn.addEventListener("click", function () { activateTab(t); });
    }
  });
})();
