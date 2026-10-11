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
    if (manifest.tier3_index) {                     // v6: the 100K is indexed per category
      Authomathics.fetchJson(manifest.tier3_index).then(function (ix) {
        var n = (ix.categories || []).reduce(function (s, c) { return s + c.count; }, 0);
        setText("count-tier3", "100,000");
        setText("blurb-tier3", n.toLocaleString() + " of 100,000 extracted: arXiv math/CS, " + (ix.categories || []).length + " categories, distilled rules; graphs built on click");
      });
    }

    setText("blurb-tier1", uniqueTier1 + " manual gold papers");
    setText("blurb-tier2", t2 + " papers (10 per category): Claude Opus graph and distilled-rule graph side by side");


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
