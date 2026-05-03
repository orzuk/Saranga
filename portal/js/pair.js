// Pair viewer. Reads ?id=<pair_id>, fetches data/pairs/<id>.json,
// renders pair metadata + matches table.

(function () {
  "use strict";

  const esc = Authomathics.esc;

  function matchPillClass(t) {
    const k = String(t || "").toLowerCase();
    if (k === "exact") return "exact";
    if (k === "analogous" || k === "analogue") return "analogous";
    return "none";
  }

  function nodeLink(paperKey, nodeId) {
    // We don't currently know which tier a side-paper lives in;
    // safest is to show the bare id and only deep-link when we know.
    // Side papers in the alignment files are typically not in our
    // data/tierN/ store, so render as plain text.
    return esc(nodeId);
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
      const aNodes = (m.paper_a_nodes || []).map(function (n) {
        return nodeLink("a", n);
      }).join("\n");
      const bNodes = (m.paper_b_nodes || []).map(function (n) {
        return nodeLink("b", n);
      }).join("\n");
      const cls = matchPillClass(m.match_type);
      tr.innerHTML =
        "<td>" + (i + 1) + "</td>" +
        '<td class="nodes-cell">' + (aNodes || '<span class="empty">—</span>') + "</td>" +
        '<td class="nodes-cell">' + (bNodes || '<span class="empty">—</span>') + "</td>" +
        '<td><span class="match-pill ' + cls + '">' +
            esc(m.match_type || "?") + "</span></td>" +
        '<td class="expl-cell">' + esc(m.explanation || "") + "</td>";
      tbody.appendChild(tr);
    });

    Authomathics.renderMath(root);
  }

  document.addEventListener("DOMContentLoaded", async function () {
    const id = Authomathics.getQueryParam("id");
    const titleEl = document.getElementById("pair-title");
    const headerEl = document.getElementById("pair-header");

    if (!id) {
      titleEl.textContent = "No pair id";
      return;
    }

    let data;
    try {
      data = await Authomathics.fetchJson("data/pairs/" + id + ".json");
    } catch (e) {
      titleEl.textContent = "Failed to load " + id;
      headerEl.innerHTML = '<div class="empty">' + esc(e.message) + "</div>";
      return;
    }

    const meta = data.metadata || {};
    const a = meta.paper_a || {};
    const b = meta.paper_b || {};

    titleEl.textContent = meta.alignment_name || id;

    headerEl.innerHTML =
      "<h2>" + esc(meta.alignment_name || id) + "</h2>" +
      '<div class="papers"><strong>A:</strong> ' + esc(a.title || "?") +
        (a.arxiv_id ? ' <small>(' + esc(a.arxiv_id) + ')</small>' : "") + "</div>" +
      '<div class="papers"><strong>B:</strong> ' + esc(b.title || "?") +
        (b.arxiv_id ? ' <small>(' + esc(b.arxiv_id) + ')</small>' : "") + "</div>" +
      '<div class="papers" style="margin-top:6px"><strong>Relation:</strong> ' +
        '<span class="relation-pill">' + esc(meta.relation_type || "?") + "</span>" +
        " &middot; <strong>Annotator:</strong> " + esc(meta.annotator || "?") + "</div>" +
      (meta.description ? '<div class="description">' + esc(meta.description) + "</div>" : "");

    renderMatches(data.matches || []);
    Authomathics.renderMath(document.body);
  });
})();
