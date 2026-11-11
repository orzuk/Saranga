// Landing page: populate counts from the manifest.

(function () {
  "use strict";

  function render(manifest) {
    const papers = manifest.papers || { tier1: [], tier2: [], tier3: [] };
    const pairs = manifest.pairs || [];

    const t1 = (papers.tier1 || []).length;
    const t2 = (papers.tier2 || []).length;
    let t3 = (papers.tier3 || []).length;

    var uniqueTier1 = 10;
    setText("count-tier1", uniqueTier1 + "");
    setText("count-tier2", t2 + "");
    setText("count-tier3", t3 > 0 ? t3 + "" : "—");
    if (manifest.tier3_index) {                     // the whole-arXiv categories, indexed per category and year
      Authomathics.fetchJson(manifest.tier3_index).then(function (ix) {
        var cats = ix.categories || [];
        var n = cats.reduce(function (s, c) { return s + c.count; }, 0);
        setText("count-tier3", n >= 1e6 ? (n / 1e6).toFixed(2) + "M" : Math.round(n / 1000) + "K");
        setText("count-tier3-home", Math.round(n / 1000) + "K");
        setText("blurb-tier3", n.toLocaleString() + " arXiv papers in " + cats.length + " categories of mathematics, statistics and the mathematical parts of CS, physics, economics and finance; graphs built on click");
      });
    }

    setText("blurb-tier1", uniqueTier1 + " manual gold papers");
    setText("blurb-tier2", t2 + " papers (10 per category): Claude Opus graph and rule-based graph side by side");


    setText("count-pairs", pairs.length + "");
    setText("blurb-pairs", pairs.length + " pair alignments");
  }

  function setText(id, text) {
    const e = document.getElementById(id);
    if (e) e.textContent = text;
  }

  document.addEventListener("DOMContentLoaded", function () {
    Authomathics.loadManifest().then(render);
  });
})();
