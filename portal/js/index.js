// Landing page: populate counts from the manifest.

(function () {
  "use strict";

  function render(manifest) {
    const papers = manifest.papers || { tier1: [], tier2: [], tier3: [] };
    const pairs = manifest.pairs || [];

    const t1 = (papers.tier1 || []).length;
    const t2 = (papers.tier2 || []).length;
    const t3 = (papers.tier3 || []).length;

    var uniqueTier1 = Math.round(t1 / 3) || t1;
    setText("count-tier1", uniqueTier1 + "");
    setText("count-tier2", t2 + "");
    setText("count-tier3", t3 > 0 ? t3 + "" : "—");

    setText("blurb-tier1", uniqueTier1 + " manual gold papers");
    setText("blurb-tier2", t2 + " silver-extracted");
    var t3k = t3 >= 1000 ? (t3 / 1000).toFixed(1) + "k" : t3 + "";
    setText("blurb-tier3", t3k + "/100k arXiv math/CS papers");

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
