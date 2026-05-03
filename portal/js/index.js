// Landing page: populate counts from the manifest.

(function () {
  "use strict";

  function render(manifest) {
    const papers = manifest.papers || { tier1: [], tier2: [], tier3: [] };
    const pairs = manifest.pairs || [];

    const t1 = (papers.tier1 || []).length;
    const t2 = (papers.tier2 || []).length;
    const t3 = (papers.tier3 || []).length;

    setText("count-tier1", t1 + "");
    setText("count-tier2", t2 + "");
    setText("count-tier3", t3 > 0 ? t3 + "" : "—");

    setText("blurb-tier1", t1 + " manual gold papers");
    setText("blurb-tier2", t2 + " silver-extracted (sample of 270)");
    setText("blurb-tier3", "100K dream-scale arXiv math/CS — coming soon");

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
