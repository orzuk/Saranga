// Display names for node ids: TP5 -> "Thm 5", PSP12 -> "Step 12". Display only; stored ids,
// links and the URL hash keep the extraction's prefixes. Global: the side panel uses it too.
// The table (ID_SHORT) is node_types.ID_SHORT, written into the page by build.py.
window.dispId = window.dispId || function (id) {
  var m = /^([A-Za-z]+?)(\d+)$/.exec(String(id));
  return m && ID_SHORT[m[1]] ? ID_SHORT[m[1]] + ' ' + m[2] : String(id);
};
/* Paper-graph viewer v2 (src/graph_view/viewer.js).
 *
 * The page embeds the paper's graph as JSON (#graph-data, written by build.py)
 * and lays it out here, on load and after every change, with Cytoscape.js and
 * ELK "layered" (elkjs 0.9.3, cytoscape 3.34.3; see lib/README.md).
 *
 * Each change of state (level, opened section or proof, toggle, focus)
 * rebuilds the element set from the data and re-runs the layout:
 *   Overview  one box per section, summary edges with counts, click to open;
 *   Results   definitions and results, each proof folded into its result;
 *   Full      every top-level node, a proof opens to its steps one level at
 *             a time (double-click, or the panel's button).
 * ELK is called directly rather than through cytoscape-elk, so its edge
 * routes are kept (drawn as round segments) and a failed or oversized
 * compound layout falls back to a flat layered one.
 */
(function () {
  'use strict';
  var G = JSON.parse(document.getElementById('graph-data').textContent);
  var T0 = performance.now();
  var NODE = {}, STEP = {}, STEP_HOST = {}, KIDS = {};
  G.nodes.forEach(function (n) { NODE[n.id] = n; });
  Object.keys(G.steps).forEach(function (h) {
    G.steps[h].forEach(function (s) {
      STEP[s.id] = s; STEP_HOST[s.id] = h;
      var p = s.parent || h;
      (KIDS[p] = KIDS[p] || []).push(s.id);
    });
  });
  // Panel data was written without its duplicates (build.py): restore them.
  if (typeof DETAILS !== 'undefined') Object.keys(DETAILS).forEach(function (k) {
    var d = DETAILS[k];
    if (!('statement_clean' in d)) d.statement_clean = d.statement;
    if (!('statement_render' in d)) d.statement_render = d.statement;
    if (!d.step_info) d.step_info = d.steps;
  });
  var SEC = {};
  G.sections.forEach(function (s) { SEC[s.id] = s; });
  G.subsections.forEach(function (s) { SEC[s.id] = s; });
  var MAIN = {};
  G.main.forEach(function (i) { MAIN[i] = true; });
  // Few top-level sections: group the overview by subsection instead.
  var PROMOTE = G.sections.length < 3 && G.subsections.length >= 3;

  var DEP = { uses: 1, generalizes: 1, specializes: 1 };
  var AUX = { example: 1, remark: 1 };
  var COMPOUND_MAX = 900;      // visible nodes above which ELK runs flat
  var FLAT_FAST = 350;         // above this, cheaper ELK settings
  var SLOW_MS = 4000;          // a grouped layout slower than this: flat from then on

  var S = {
    level: G.level, open: {}, proofs: {}, focus: null, k: 1, selected: null,
    show: { ext: false, extdef: true, aux: true, ghosts: false, low: true, implied: true,
            back: true, mention: true, nested: true },
    tred: false, search: '', openOrder: [], ctx: null, ctxNow: true, ctxN: 0,
    authors: true                                    // gold pages: the authors' layout first, where the figure gives it
  };
  var cy = null, firstDone = false, layoutSeq = 0, lastNote = '';

  // ── Text measurement and box sizes ────────────────────────────────────
  var ctx = document.createElement('canvas').getContext('2d');
  var FONT = '"Segoe UI", Tahoma, Arial, sans-serif';

  function wrap(text, px, maxW, maxLines) {
    ctx.font = px + 'px ' + FONT;
    var words = String(text || '').split(/\s+/).filter(Boolean), lines = [], cur = '';
    for (var i = 0; i < words.length; i++) {
      var w = words[i];
      while (ctx.measureText(w).width > maxW && w.length > 4) {        // very long token
        var cut = Math.max(3, Math.floor(w.length * maxW / ctx.measureText(w).width) - 1);
        if (cur) { lines.push(cur); cur = ''; }
        lines.push(w.slice(0, cut)); w = w.slice(cut);
      }
      var t = cur ? cur + ' ' + w : w;
      if (ctx.measureText(t).width <= maxW) cur = t;
      else { if (cur) lines.push(cur); cur = w; }
    }
    if (cur) lines.push(cur);
    if (lines.length > maxLines) {
      lines = lines.slice(0, maxLines);
      var last = lines[maxLines - 1];
      while (last.length > 1 && ctx.measureText(last + '…').width > maxW) last = last.slice(0, -1);
      lines[maxLines - 1] = last.replace(/[\s,;:]+$/, '') + '…';
    }
    return lines;
  }

  function mix(hex, f) {          // hex colour blended with white, f = share of colour
    var c = parseInt(hex.slice(1), 16), r = c >> 16, g = (c >> 8) & 255, b = c & 255;
    var m = function (v) { return Math.round(255 - (255 - v) * f); };
    return 'rgb(' + m(r) + ',' + m(g) + ',' + m(b) + ')';
  }

  function colorsOf(type) { return G.colors[type] || G.default_color; }

  // A text box: header band (id and name) over the body text.
  function box(head, body, extra, imp, maxBody) {
    var fs = Math.round((11 + 0.6 * (imp - 1)) * 10) / 10;
    var w = Math.round(150 + 30 * (imp - 1));
    var inner = w - 14, lh = fs * 1.25;
    var hl = wrap(head, fs, inner, 2);
    var bl = body ? wrap(body, fs, inner, maxBody) : [];
    if (extra) bl.push(extra);
    var lines = hl.concat(bl);
    var bandH = hl.length * lh + 6;
    var h = Math.round(lines.length * lh + 12 + (bl.length ? 4 : 0));
    return { label: lines.join('\n'), w: w, h: h, fs: fs, band: Math.min(95, Math.round(100 * (bandH + 2) / h)) };
  }

  // ── Visibility ────────────────────────────────────────────────────────
  function level() { return S.level === 'overview' && S.focus ? 'full' : S.level; }

  function shownBase(n) {
    if (n.origin === 'external' && !(n.type === 'definition' ? S.show.extdef : S.show.ext)) return false;
    if (AUX[n.type] && !S.show.aux) return false;
    if (n.inside && !S.show.nested) return false;
    if (level() === 'results' && !n.res) return false;
    return true;
  }

  function groupPath(n) {             // overview groups containing n, outermost first
    if (PROMOTE) return [n.sub || n.top];
    return n.sub ? [n.top, n.sub] : [n.top];
  }

  // Display name of a node id: its paper number when it has one (Thm 1.1), else the id form (Thm 3).
  function dispNum(id) {
    var d = window.dispId ? dispId(id) : String(id), n = NODE[id];
    return (n && n.num && /\d+$/.test(d)) ? d.replace(/\d+$/, n.num) : d;
  }

  function dependencyAdj(ids) {        // forward dependency edges among ids
    var up = {}, down = {};
    G.edges.forEach(function (e) {
      // resolves (a problem settled by a result) and illustrates (an example of it) are not
      // dependencies: the result does not rest on the problem or the example
      if (e.mention || e.back || e.type === 'resolves' || e.type === 'illustrates' || !ids[e.s] || !ids[e.t]) return;
      (up[e.t] = up[e.t] || []).push(e.s);
      (down[e.s] = down[e.s] || []).push(e.t);
    });
    return { up: up, down: down };
  }

  function focusSet(base) {
    if (!S.focus) return null;
    var ids = {};
    base.forEach(function (n) { ids[n.id] = true; });
    var adj = dependencyAdj(ids), keep = {};
    if (S.focus.mode === 'main' || S.focus.mode === 'up' || S.focus.mode === 'down') {
      // One walk from the seeds: 'main' and 'up' keep everything the seeds rest on
      // (only that: a claim stated inside a kept theorem stays only if something on
      // the path uses it); 'down' keeps everything that rests on the seed.
      var seeds = S.focus.mode === 'main' ? G.main : [S.focus.id];
      var next = S.focus.mode === 'down' ? adj.down : adj.up;
      var stack = seeds.filter(function (i) { return ids[i]; });
      stack.forEach(function (i) { keep[i] = true; });
      while (stack.length) {
        (next[stack.pop()] || []).forEach(function (p) {
          if (!keep[p]) { keep[p] = true; stack.push(p); }
        });
      }
      return keep;
    }
    // neighbourhood: k steps up and k steps down, over every shown edge
    var nb = {};
    G.edges.forEach(function (e) {
      if (!ids[e.s] || !ids[e.t]) return;
      (nb[e.s] = nb[e.s] || { up: [], down: [] }).down.push(e.t);
      (nb[e.t] = nb[e.t] || { up: [], down: [] }).up.push(e.s);
    });
    keep[S.focus.id] = true;
    ['up', 'down'].forEach(function (dir) {
      var front = [S.focus.id], seen = {};
      seen[S.focus.id] = true;
      for (var k = 0; k < S.k; k++) {
        var next = [];
        front.forEach(function (x) {
          ((nb[x] || {})[dir] || []).forEach(function (y) {
            if (!seen[y]) { seen[y] = true; keep[y] = true; next.push(y); }
          });
        });
        front = next;
      }
    });
    return keep;
  }

  // Typed transitive reduction, as in classic: a `uses` edge is implied by any
  // path of dependency edges, a generalizes/specializes edge only by a path of
  // its own type; other types are never implied.
  function reduce(edges) {
    var out = {}, adj = { uses: {}, generalizes: {}, specializes: {} };
    edges.forEach(function (e) {
      if (!DEP[e.type]) return;
      (adj.uses[e.s] = adj.uses[e.s] || []).push(e);
      if (e.type !== 'uses') (adj[e.type][e.s] = adj[e.type][e.s] || []).push(e);
    });
    edges.forEach(function (e) {
      if (!DEP[e.type]) return;
      var g = adj[e.type], seen = {}, stack = [e.s];
      seen[e.s] = true;
      while (stack.length) {
        var lst = g[stack.pop()] || [];
        for (var i = 0; i < lst.length; i++) {
          var f = lst[i];
          if (f === e) continue;
          if (f.t === e.t) { out[e.key] = true; return; }
          if (!seen[f.t]) { seen[f.t] = true; stack.push(f.t); }
        }
      }
    });
    return out;
  }

  // ── Elements from state ───────────────────────────────────────────────
  function buildElements() {
    var lv = level(), els = [], nodesOut = {};
    var base = G.nodes.filter(shownBase);
    var fset = focusSet(base);
    if (fset) base = base.filter(function (n) { return fset[n.id]; });
    var shown = {};
    base.forEach(function (n) { shown[n.id] = true; });

    // Where each shown base node is drawn: itself, or its collapsed group.
    var rep = {}, groupCount = {}, groupTypes = {};
    base.forEach(function (n) {
      var r = n.id;
      if (lv === 'overview') {
        var path = groupPath(n);
        for (var i = 0; i < path.length; i++) {
          groupCount[path[i]] = (groupCount[path[i]] || 0) + 1;
          var gt = groupTypes[path[i]] = groupTypes[path[i]] || {};
          gt[n.type] = (gt[n.type] || 0) + 1;
        }
        for (var j = 0; j < path.length; j++) {
          if (!S.open[path[j]]) { r = path[j]; break; }
        }
      }
      rep[n.id] = r;
    });

    // Group nodes (overview): collapsed boxes or open compounds.
    if (lv === 'overview') {
      G.sections.concat(G.subsections).forEach(function (g) {
        if (!groupCount[g.id]) return;
        var par = (!PROMOTE && g.parent) ? g.parent : null;
        if (par && !S.open[par]) return;               // inside a collapsed section
        var title = (g.title || g.key).replace(/^([A-Z])\.?\s+(?=\S)/, 'Appendix $1: ');
        if (S.open[g.id]) {
          els.push({ group: 'nodes', data: { id: g.id, kind: 'secopen', parent: par || undefined,
            label: '−  ' + title } });
        } else {
          var tc = groupTypes[g.id] || {}, parts = [];
          [['theorem', 'theorems'], ['proposition', 'propositions'], ['lemma', 'lemmas'],
           ['corollary', 'corollaries'], ['definition', 'definitions']].forEach(function (t) {
            if (tc[t[0]]) parts.push(tc[t[0]] + ' ' + t[tc[t[0]] > 1 ? 1 : 0]);
          });
          var nMain = base.filter(function (n) { return MAIN[n.id] && groupPath(n).indexOf(g.id) >= 0; }).length;
          var b = box('+  ' + title, groupCount[g.id] + ' nodes' + (parts.length ? ': ' + parts.join(', ') : '')
                      + (nMain ? '  ★ ' + nMain + ' main' : ''), '', 4.2, 3);
          els.push({ group: 'nodes', data: { id: g.id, kind: 'secbox', parent: par || undefined,
            label: b.label, w: b.w, h: b.h, fs: b.fs, band: b.band, count: groupCount[g.id] } });
        }
        nodesOut[g.id] = true;
      });
    }

    // Proof steps that are open: a step is drawn when its container is open.
    function stepShown(sid) {
      var p = STEP[sid].parent || STEP_HOST[sid];
      if (!S.proofs[p]) return false;
      return STEP[p] ? stepShown(p) : (shown[p] && rep[p] === p);
    }
    function repOf(x) {
      if (STEP[x]) return stepShown(x) ? x : repOf(STEP[x].parent || STEP_HOST[x]);
      return shown[x] ? rep[x] : null;
    }

    // An open proof is a frame ('pf:' + id) holding the result's own box and
    // the proof's steps, the steps leading down to the result; a step with
    // open sub-steps gets a frame of its own, inside.
    var frames = [];
    function frame(id, parent, label) {
      els.push({ group: 'nodes', data: { id: 'pf:' + id, kind: 'proofframe', of: id, parent: parent,
        label: label } });
      frames.push(id);
      return 'pf:' + id;
    }

    // A statement with results stated inside it (a "Moreover" clause made a
    // claim of its own, a lemma inside a theorem) is drawn as one frame holding
    // its own box and theirs, so edges land on the part they support.
    var partsOf = {};
    base.forEach(function (n) {
      if (!n.inside || rep[n.id] !== n.id || !shown[n.inside] || rep[n.inside] !== n.inside) return;
      (partsOf[n.inside] = partsOf[n.inside] || []).push(n.id);
    });
    function headOf(n) {
      var dm = /^DIST_[A-Z_]+?(\d+)$/.exec(n.id);
      var nm = (n.name && n.name !== n.id) ? n.name : '';
      var did = dispNum(n.id);                           // the paper's number (Thm 1.1) when the node has one
      return { nm: nm, did: did, head: (MAIN[n.id] ? '\u2605 ' : '') +
        (dm ? n.type.replace(/_/g, ' ') + ' ' + dm[1] + ' (rule)' + (nm ? ': ' + nm : '') : did + ': ' + (nm || n.type)) };
    }
    var partFrame = {};
    // Base nodes drawn as themselves.
    base.forEach(function (n) {
      if (rep[n.id] !== n.id) return;
      var c = colorsOf(n.type);
      var par;
      if (lv === 'overview') {
        var path = groupPath(n);
        par = path[path.length - 1];
      }
      if (n.inside && partFrame[n.inside]) par = partFrame[n.inside];
      var open = S.proofs[n.id] && n.nsteps > 0;
      if (open) par = frame(n.id, par, 'proof of ' + n.id);
      if (partsOf[n.id]) {
        var hp = headOf(n);
        els.push({ group: 'nodes', data: { id: 'pt:' + n.id, kind: 'partframe', of: n.id, parent: par,
          label: hp.head, hc: c.header } });
        partFrame[n.id] = par = 'pt:' + n.id;
      }
      // Nodes made by a distilled sentence rule (DIST_DEFINITION7) carry no
      // name of their own: show "definition 7 (rule)" rather than the id twice.
      var h0 = headOf(n), nm = h0.nm;
      // Inside its own part frame the statement's box is its main part: the frame carries the head.
      var head = partsOf[n.id] ? h0.did + ': main statement' : h0.head;
      var extra = n.nsteps ? (open ? '\u25be proof open (' + n.nsteps + ' steps)' : '\u25b8 proof: ' + n.nsteps + ' step' + (n.nsteps > 1 ? 's' : '')) : '';
      var b = box(head, n.short, extra, n.imp, n.imp >= 4 ? 4 : 3);
      var d = { id: n.id, kind: 'node', type: n.type, parent: par,
        hc: c.header, bc: c.body, band_c: mix(c.header, 0.38), imp: n.imp,
        ext: n.origin === 'external' ? 1 : 0, main: MAIN[n.id] ? 1 : 0,
        label: b.label, w: b.w, h: b.h, fs: b.fs, band: b.band };
      if (n.pos) d.pos = n.pos;          // [x, y, drawing]: where the authors drew it
      if (n.tex) {                       // typeset by MathJax in the math layer, not on the canvas
        d.tex = 1;
        d.texHead = head.replace(nm, n.tex_name || nm);
        d.texBody = n.tex; d.texExtra = extra;
      }
      els.push({ group: 'nodes', data: d });
      nodesOut[n.id] = true;
    });
    // Steps of open proofs (parents first, so frames exist before their kids).
    var stepOrder = [];
    Object.keys(G.steps).forEach(function (h) {
      (function walk(p) { (KIDS[p] || []).forEach(function (k) { stepOrder.push(k); walk(k); }); })(h);
    });
    stepOrder.forEach(function (sid) {
      if (!stepShown(sid)) return;
      var s = STEP[sid], host = STEP_HOST[sid];
      var open = !!(S.proofs[sid] && KIDS[sid]);
      var nk = (KIDS[sid] || []).length;
      var par = 'pf:' + (s.parent || host);
      if (open) par = frame(sid, par, '');
      var head = sid + (s.name ? ': ' + s.name : '');
      var c = colorsOf('proof_step');
      var b = box(head, s.short, nk ? (open ? '\u25be ' : '\u25b8 ') + nk + ' sub-step' + (nk > 1 ? 's' : '') : '', 1, 3);
      els.push({ group: 'nodes', data: { id: sid, kind: 'step', parent: par, host: host,
        hc: c.header, bc: c.body, band_c: mix(c.header, 0.35), imp: 1,
        label: b.label, w: b.w, h: b.h, fs: b.fs, band: b.band } });
      nodesOut[sid] = true;
    });

    // Edges between base nodes (and summary edges into collapsed groups).
    var regular = [], summary = {};
    G.edges.forEach(function (e) {
      if (!shown[e.s] || !shown[e.t]) return;
      if (e.low && !S.show.low) return;
      if (e.back && !S.show.back) return;
      if (e.mention && !S.show.mention) return;
      if (e.implied && !S.show.implied) return;
      var a = rep[e.s], b = rep[e.t];
      if (a === b) return;
      if (a !== e.s || b !== e.t) {
        if (e.mention || e.back) return;        // summaries count dependencies only
        var key = a + '→' + b;
        (summary[key] = summary[key] || { s: a, t: b, n: 0 }).n++;
        return;
      }
      regular.push({ key: 'e:' + e.s + '→' + e.t, s: e.s, t: e.t, type: e.type, e: e });
    });
    // Edges at proof steps, when at least one end is a drawn step.
    var seenStep = {};
    G.step_edges.forEach(function (e) {
      if (e.back && !S.show.back) return;
      if (e.mention && !S.show.mention) return;
      var a = repOf(e.s), b = repOf(e.t);
      if (!a || !b || a === b || !nodesOut[a] || !nodesOut[b]) return;
      if (!(STEP[a] && a === e.s) && !(STEP[b] && b === e.t)) return;
      if (SEC[a] || SEC[b]) return;
      var key = 's:' + a + '→' + b;
      if (seenStep[key]) return;
      seenStep[key] = true;
      regular.push({ key: key, s: a, t: b, type: e.type, e: e, step: 1 });
    });
    // Reading order of sibling steps, where no edge links them already, and
    // the last step down to what it proves.
    frames.forEach(function (p) {
      var ks = (KIDS[p] || []).filter(function (k) { return nodesOut[k]; });
      for (var i = 0; i + 1 < ks.length; i++) {
        var k1 = 's:' + ks[i] + '\u2192' + ks[i + 1], k2 = 's:' + ks[i + 1] + '\u2192' + ks[i];
        if (!seenStep[k1] && !seenStep[k2]) {
          regular.push({ key: 'o:' + ks[i] + '\u2192' + ks[i + 1], s: ks[i], t: ks[i + 1], type: 'order', order: 1 });
        }
      }
      if (ks.length && !seenStep['s:' + ks[ks.length - 1] + '\u2192' + p]) {
        regular.push({ key: 'o:' + ks[ks.length - 1] + '\u2192' + p, s: ks[ks.length - 1], t: p, type: 'order', order: 1 });
      }
    });
    var hidden = (S.tred || (S.focus && S.focus.mode !== 'nbhd'))
      ? reduce(regular.filter(function (r) { return !r.order && !(r.e && (r.e.back || r.e.mention)); }))
      : {};
    var nEdges = 0;
    // A node whose only shown edges are mentions (its supports are hidden, e.g.
    // cited nodes) would float as an isolated component at the top left; let a
    // mention edge place such a node below the node that mentions it.
    var hasLay = {};
    regular.forEach(function (r) {
      var e = r.e || {};
      if (!hidden[r.key] && !(e.back || e.mention)) { hasLay[r.s] = true; hasLay[r.t] = true; }
    });
    regular.forEach(function (r) {
      if (hidden[r.key]) return;
      var e = r.e || {}, cls = [];
      var lay = !(e.back || e.mention) || (e.mention && !e.back && !(hasLay[r.s] && hasLay[r.t]));
      if (r.order) cls.push('order');
      if (e.back) cls.push('back');
      if (e.mention) cls.push('mention');
      if (e.low) cls.push('low');
      if (e.both) cls.push('both');                   // drawn <=> by the authors: equivalent statements
      if (r.type === 'resolves') cls.push('resolves');
      els.push({ group: 'edges', classes: cls.join(' '), data: { id: r.key, source: r.s, target: r.t,
        etype: r.type, color: G.edge_colors[r.type] || G.default_edge_color, lay: lay ? 1 : 0,
        conf: e.conf } });
      nEdges++;
    });
    Object.keys(summary).forEach(function (k) {
      var x = summary[k];
      els.push({ group: 'edges', classes: 'summary', data: { id: 'g:' + k, source: x.s, target: x.t,
        n: x.n, label: String(x.n), wd: Math.min(5, 1.2 + 0.9 * Math.log2(x.n)), lay: 1 } });
      nEdges++;
    });
    // "Stated inside": a dotted line from a nested result to the box it is in.
    base.forEach(function (n) {
      if (!n.inside || rep[n.id] !== n.id || !shown[n.inside] || rep[n.inside] !== n.inside) return;
      if (partFrame[n.inside]) return;                 // drawn inside the statement's frame instead
      els.push({ group: 'edges', classes: 'inside', data: { id: 'in:' + n.id, source: n.inside,
        target: n.id, lay: 0 } });
    });
    // Foundations (external results the paper relies on), above the graph.
    if (S.show.ghosts) {
      G.ghosts.forEach(function (g, gi) {
        var tgts = {};
        g.refs.forEach(function (r) { if (shown[r]) tgts[rep[r]] = true; });
        var ts = Object.keys(tgts);
        if (!ts.length) return;
        var gid = 'ghost:' + gi;
        var b = box(g.name, 'foundation' + (g.book ? ' (book)' : ''), '', 1, 1);
        els.push({ group: 'nodes', classes: g.book ? 'ghostbook' : 'ghost', data: { id: gid, kind: 'ghost', name: g.name,
          label: b.label, w: b.w, h: b.h, fs: b.fs, band: b.band } });
        ts.forEach(function (t) {
          els.push({ group: 'edges', classes: g.book ? 'ghostbook' : 'ghost', data: { id: gid + '→' + t,
            source: gid, target: t, lay: 0 } });
        });
      });
    }
    return { els: els, nBase: base.length, nEdges: nEdges };
  }

  // ── Styles ────────────────────────────────────────────────────────────
  var STYLE = [
    { selector: 'node', style: {
      'shape': 'round-rectangle', 'border-width': 1.5, 'background-color': '#F4F6F7', 'border-color': '#546E7A',
      'font-family': FONT, 'font-size': 12, 'color': '#1d1d1d',
      'text-wrap': 'wrap', 'text-max-width': 4000, 'text-valign': 'center', 'text-halign': 'center',
      'text-justification': 'left', 'line-height': 1.25, 'min-zoomed-font-size': 5,
      'background-fill': 'linear-gradient', 'background-gradient-direction': 'to-bottom',
      'corner-radius': 5 } },
    { selector: 'node[w]', style: { 'width': 'data(w)', 'height': 'data(h)' } },
    { selector: 'node[label]', style: { 'label': 'data(label)' } },
    { selector: 'node[tex = 1]', style: { 'label': '' } },
    { selector: 'node[fs]', style: { 'font-size': 'data(fs)' } },
    { selector: 'node[bc]', style: { 'background-color': 'data(bc)' } },
    { selector: 'node[hc]', style: { 'border-color': 'data(hc)' } },
    { selector: 'node[ext = 1]', style: { 'border-style': 'dashed', 'border-width': 2, 'background-opacity': 0.9 } },
    { selector: 'node[main = 1]', style: { 'border-width': 3.5, 'underlay-color': '#FFD54F', 'underlay-opacity': 0.55, 'underlay-padding': 5, 'underlay-shape': 'round-rectangle' } },
    // #mark=ID,ID[&markc=#hex]: circle nodes (e.g. the ones another extraction missed)
    { selector: 'node.marked', style: { 'underlay-color': 'data(mk)', 'underlay-opacity': 0.9, 'underlay-padding': 7, 'underlay-shape': 'round-rectangle' } },
    // #dim=ID,ID: fade these nodes (e.g. the ones the other extraction does not share)
    { selector: 'node.dimmed', style: { 'opacity': 0.22 } },
    { selector: 'node[kind = "secbox"]', style: { 'background-color': '#F4F6F7', 'border-color': '#546E7A',
      'border-width': 2, 'color': '#263238' } },
    { selector: 'node[kind = "ghost"], node.ghost', style: { 'background-color': '#E8E8E8', 'border-color': '#777',
      'border-style': 'dashed', 'color': '#333', 'background-fill': 'solid' } },
    { selector: 'node.ghostbook', style: { 'background-color': '#FFF8E1', 'border-color': '#8D6E63',
      'border-style': 'dotted', 'background-fill': 'solid' } },
    { selector: ':parent', style: {
      'background-fill': 'solid', 'background-opacity': 0.55, 'text-valign': 'top', 'text-halign': 'center',
      'text-wrap': 'wrap', 'text-max-width': 2000, 'text-justification': 'center', 'font-size': 13, 'padding': 14,
      'compound-sizing-wrt-labels': 'include', 'corner-radius': 8 } },
    { selector: 'node[kind = "secopen"]', style: { 'background-color': '#EEF2F4', 'border-color': '#78909C',
      'border-width': 2, 'border-style': 'dashed', 'color': '#37474F' } },
    { selector: 'node[kind = "proofframe"]', style: { 'background-color': '#F7F1FA', 'border-color': '#A569BD',
      'border-width': 1.5, 'border-style': 'dashed', 'font-size': 11, 'color': '#6C3483', 'padding': 10 } },
    { selector: 'node[kind = "partframe"]', style: { 'background-color': '#FFFFFF', 'border-color': 'data(hc)',
      'border-width': 2.5, 'border-style': 'solid', 'font-size': 12, 'font-weight': 'bold', 'color': '#1d1d1d',
      'padding': 8, 'text-valign': 'top', 'text-halign': 'center', 'text-margin-y': -4,
      'text-background-color': '#FFFFFF', 'text-background-opacity': 1, 'text-background-padding': 3,
      'text-background-shape': 'roundrectangle', 'z-index': 2 } },
    { selector: 'node.match', style: { 'overlay-color': '#FFEB3B', 'overlay-opacity': 0.45, 'overlay-padding': 6 } },
    { selector: 'node:selected', style: { 'overlay-color': '#1E88E5', 'overlay-opacity': 0.22, 'overlay-padding': 7 } },
    { selector: '.dim', style: { 'opacity': 0.25 } },
    { selector: 'edge', style: {
      'width': 1.6, 'line-color': '#455A64', 'target-arrow-color': '#455A64',
      'target-arrow-shape': 'triangle', 'arrow-scale': 0.9, 'curve-style': 'straight', 'opacity': 0.9 } },
    { selector: 'edge[color]', style: { 'line-color': 'data(color)', 'target-arrow-color': 'data(color)' } },
    { selector: 'edge.routed', style: { 'curve-style': 'round-segments', 'segment-radius': 12,
      'edge-distances': 'endpoints' } },
    { selector: 'edge.ends', style: { 'edge-distances': 'endpoints' } },
    { selector: 'edge.resolves', style: { 'line-style': 'dashed' } },
    { selector: 'edge.low', style: { 'line-color': '#546E7A', 'target-arrow-color': '#546E7A', 'width': 1.8,
      'opacity': 1, 'line-style': 'dashed', 'line-dash-pattern': [4, 3] } },
    { selector: 'edge.both', style: { 'source-arrow-shape': 'triangle', 'source-arrow-color': 'data(color)' } },
    { selector: 'edge.back', style: { 'line-style': 'dashed', 'line-dash-pattern': [6, 2, 1, 2],
      'curve-style': 'unbundled-bezier', 'control-point-distances': 70, 'control-point-weights': 0.5 } },
    { selector: 'edge.mention', style: { 'line-color': '#5C6BC0', 'target-arrow-color': '#5C6BC0', 'width': 1.3,
      'line-style': 'dashed', 'line-dash-pattern': [2, 2], 'curve-style': 'unbundled-bezier',
      'control-point-distances': 50, 'control-point-weights': 0.5, 'opacity': 0.85 } },
    { selector: 'edge.order', style: { 'line-color': '#9575CD', 'target-arrow-color': '#9575CD', 'width': 1.3,
      'line-style': 'dotted', 'arrow-scale': 0.6 } },
    { selector: 'edge.inside', style: { 'line-color': '#7F8C8D', 'width': 2, 'line-style': 'dashed',
      'line-dash-pattern': [1, 2], 'target-arrow-shape': 'none', 'opacity': 0.8, 'z-index': 0 } },
    { selector: 'edge.summary', style: { 'line-color': '#78909C', 'target-arrow-color': '#78909C',
      'width': 'data(wd)', 'label': 'data(label)', 'font-size': 13, 'color': '#263238', 'opacity': 0.8,
      'text-background-color': '#fff', 'text-background-opacity': 0.9, 'text-background-padding': 2,
      'text-background-shape': 'round-rectangle', 'arrow-scale': 1.1 } },
    { selector: 'edge.ghost', style: { 'line-color': '#9E9E9E', 'target-arrow-color': '#9E9E9E', 'width': 1,
      'line-style': 'dashed', 'line-dash-pattern': [8, 6] } },
    { selector: 'edge.ghostbook', style: { 'line-color': '#8D6E63', 'target-arrow-color': '#8D6E63', 'width': 1,
      'line-style': 'dashed', 'line-dash-pattern': [3, 3] } },
    { selector: 'edge.hl', style: { 'width': 3.2, 'opacity': 1, 'z-index': 999 } },
    { selector: 'edge.summary.hl', style: { 'width': 'data(wd)', 'line-color': '#37474F', 'target-arrow-color': '#37474F' } },
    { selector: 'node.hl', style: { 'border-width': 3 } }
  ];

  // ── Layout (ELK layered, top to bottom) ───────────────────────────────
  // Model order (keep paper order where it costs no crossings) and network-
  // simplex placement read best but scale badly: network simplex overflows
  // the stack near 500 nodes, model order is 5x slower there. Small views get
  // both, large ones the fast settings.
  function elkOptions(n, m) {
    var small = n <= 150 && m <= 500;
    var o = {
      'elk.algorithm': 'layered',
      'elk.direction': 'DOWN',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.spacing.nodeNodeBetweenLayers': 44,
      'elk.spacing.nodeNode': 22,
      'elk.spacing.edgeNode': 12,
      'elk.spacing.edgeEdge': 6,
      'elk.layered.spacing.edgeNodeBetweenLayers': 14,
      'elk.spacing.componentComponent': 40,
      'elk.layered.thoroughness': small ? 7 : (n <= FLAT_FAST ? 5 : 3),
      'elk.layered.nodePlacement.strategy': small ? 'NETWORK_SIMPLEX' : 'BRANDES_KOEPF',
      'elk.layered.nodePlacement.favorStraightEdges': true,
      'elk.aspectRatio': Math.max(0.8, Math.min(3, cy.width() / Math.max(1, cy.height()))),
      'elk.separateConnectedComponents': true
    };
    if (small) o['elk.layered.considerModelOrder.strategy'] = 'NODES_AND_EDGES';
    return o;
  }

  function elkGraph(compound) {
    var nodes = cy.nodes(), k = {}, opts = elkOptions(nodes.length, cy.edges().length);
    var root = { id: '__root', layoutOptions: opts, children: [], edges: [] };
    if (compound) opts['elk.hierarchyHandling'] = 'INCLUDE_CHILDREN';
    nodes.forEach(function (n) {
      if (n.data('kind') === 'ghost') return;           // placed after, see placeGhosts
      var e = { id: n.id() };
      if (compound && n.isParent()) {
        e.layoutOptions = { 'elk.padding': '[top=40,left=16,bottom=16,right=16]' };
        e.children = [];
      } else if (n.isParent()) {
        return;                                    // flat: compounds are not laid out
      } else { e.width = n.data('w'); e.height = n.data('h'); }
      k[n.id()] = e;
    });
    nodes.forEach(function (n) {
      if (!k[n.id()]) return;
      var p = compound ? n.parent() : null;
      if (p && p.nonempty() && k[p.id()]) k[p.id()].children.push(k[n.id()]);
      else root.children.push(k[n.id()]);
    });
    cy.edges().forEach(function (e) {
      if (!e.data('lay')) return;
      var s = e.source(), t = e.target();
      if (!k[s.id()] || !k[t.id()]) return;
      if (s.ancestors().contains(t) || t.ancestors().contains(s)) return;
      root.edges.push({ id: e.id(), sources: [s.id()], targets: [t.id()] });
    });
    return { root: root, map: k };
  }

  function applyLayout(res, map) {
    var abs = {};
    (function walk(n, ox, oy) {
      (n.children || []).forEach(function (c) {
        var x = ox + (c.x || 0), y = oy + (c.y || 0);
        abs[c.id] = { x: x, y: y, w: c.width, h: c.height };
        walk(c, x, y);
      });
    })(res, 0, 0);
    cy.batch(function () {
      cy.nodes().forEach(function (n) {
        var a = abs[n.id()];
        if (a && !n.isParent()) n.position({ x: a.x + a.w / 2, y: a.y + a.h / 2 });
      });
    });
    // Compound positions follow their children only once their bounds are
    // updated; the edge endpoints below are relative to them.
    cy.nodes().updateCompoundBounds(true);
    cy.batch(function () {
      cy.edges().removeClass('routed ends').removeStyle('segment-distances segment-weights source-endpoint target-endpoint');
      var routes = {};
      (function collect(n) {
        (n.edges || []).forEach(function (e) { routes[e.id] = { e: e, c: n.id }; });
        (n.children || []).forEach(collect);
      })(res);
      cy.edges().forEach(function (edge) {
        var r = routes[edge.id()];
        if (!r || !r.e.sections || !r.e.sections.length) return;
        var off = r.e.container && r.e.container !== '__root' && abs[r.e.container]
          ? abs[r.e.container] : (r.c !== '__root' && abs[r.c] ? abs[r.c] : { x: 0, y: 0 });
        var sec = r.e.sections[0];
        var A = { x: sec.startPoint.x + off.x, y: sec.startPoint.y + off.y };
        var B = { x: sec.endPoint.x + off.x, y: sec.endPoint.y + off.y };
        var sp = edge.source().position(), tp = edge.target().position();
        var dx = B.x - A.x, dy = B.y - A.y, l2 = dx * dx + dy * dy;
        if (l2 < 1) return;
        var l = Math.sqrt(l2), ws = [], ds = [];
        (sec.bendPoints || []).forEach(function (p) {
          var px = p.x + off.x - A.x, py = p.y + off.y - A.y;
          ws.push((px * dx + py * dy) / l2);
          ds.push((px * -dy + py * dx) / l);
        });
        var st = {
          'source-endpoint': (A.x - sp.x).toFixed(1) + 'px ' + (A.y - sp.y).toFixed(1) + 'px',
          'target-endpoint': (B.x - tp.x).toFixed(1) + 'px ' + (B.y - tp.y).toFixed(1) + 'px'
        };
        if (ws.length) {
          st['segment-weights'] = ws.map(function (v) { return v.toFixed(4); }).join(' ');
          st['segment-distances'] = ds.map(function (v) { return v.toFixed(1); }).join(' ');
          edge.addClass('routed');
        } else edge.addClass('ends');
        edge.style(st);
      });
    });
  }

  // Foundations sit in a band above the graph, as in classic: each under the
  // mean position of the nodes it supports. Kept out of ELK, which they would
  // slow down tenfold on the largest papers.
  function placeGhosts() {
    var gs = cy.nodes('[kind = "ghost"]');
    if (!gs.length) return;
    var bb = cy.nodes().not(gs).boundingBox();
    var xs = gs.map(function (g) {
      var t = g.outgoers('node'), x = 0;
      t.forEach(function (n) { x += n.position('x'); });
      return { g: g, x: t.length ? x / t.length : bb.x1 };
    }).sort(function (a, b) { return a.x - b.x; });
    var width = Math.max(bb.w, 1200), gap = 16, rowH = 0, rows = [[]], used = 0;
    xs.forEach(function (o) {
      var w = o.g.data('w') + gap;
      if (used + w > width && rows[rows.length - 1].length) { rows.push([]); used = 0; }
      rows[rows.length - 1].push(o); used += w;
      rowH = Math.max(rowH, o.g.data('h'));
    });
    cy.batch(function () {
      rows.forEach(function (row, r) {
        var tot = row.reduce(function (a, o) { return a + o.g.data('w') + gap; }, -gap);
        var x = bb.x1 + bb.w / 2 - tot / 2;
        var y = bb.y1 - 90 - (rows.length - r) * (rowH + 30) + rowH / 2;
        row.forEach(function (o) {
          o.g.position({ x: x + o.g.data('w') / 2, y: y });
          x += o.g.data('w') + gap;
        });
      });
    });
  }

  function flatten() {
    // Fallback: no groups. Children leave their frames, which are removed.
    cy.batch(function () {
      var moved = true;
      while (moved) {
        moved = false;
        cy.nodes().forEach(function (n) {
          if (n.isChild()) { n.move({ parent: null }); moved = true; }
        });
      }
      cy.nodes('[kind = "secopen"], [kind = "proofframe"], [kind = "partframe"]').remove();
    });
    paintNodes();
  }

  function paintNodes() {
    cy.batch(function () {
      cy.nodes().forEach(function (n) {
        if (n.isParent() || n.data('kind') === 'ghost' || n.hasClass('ghostbook')) return;
        var band = n.data('band') || 30, bc = n.data('bc') || '#F4F6F7';
        var hc = n.data('band_c') || mix(n.data('hc') || '#546E7A', 0.25);
        if (n.data('kind') === 'secbox') hc = '#CFD8DC';
        n.style({ 'background-gradient-stop-colors': [hc, hc, bc, bc].join(' '),
                  'background-gradient-stop-positions': '0 ' + band + ' ' + band + ' 100' });
      });
    });
  }

  function setBusy(on) { document.getElementById('busy').style.display = on ? 'block' : 'none'; }

  // ── The authors' layout: the boxes where the figure draws them ─────────────
  // Coordinates are ranked (clustered to the drawing's rows and columns), so boxes never overlap and the
  // order of rows and columns is the figure's; several drawings stand side by side.
  function authorsLayoutPossible() {
    var leaves = cy.nodes('[kind = "node"]');
    return leaves.length > 1 && leaves.filter(function (n) { return n.data('pos'); }).length >= 0.8 * leaves.length;
  }
  function authorsLayout() {
    var leaves = cy.nodes('[kind = "node"]'), byDrawing = {};
    leaves.forEach(function (n) { var p = n.data('pos'); if (p) (byDrawing[p[2] || 0] = byDrawing[p[2] || 0] || []).push(n); });
    var W = 0, H = 0;
    leaves.forEach(function (n) { W = Math.max(W, n.data('w') || 150); H = Math.max(H, n.data('h') || 60); });
    var x0 = 0, bottom = 0;
    cy.batch(function () {
      Object.keys(byDrawing).sort(function (a, b) { return a - b; }).forEach(function (k) {
        var ns = byDrawing[k], P = ns.map(function (n) { return n.data('pos'); });
        var ys = P.map(function (p) { return p[1]; }), xs = P.map(function (p) { return p[0]; });
        var spanY = (Math.max.apply(null, ys) - Math.min.apply(null, ys)) || 1;
        // the drawing's scale: the closest two boxes of one row, and the closest two rows, get our box sizes apart
        var dx = Infinity, dy = Infinity;
        P.forEach(function (a, i) { P.forEach(function (b, j) {
          if (j <= i) return;
          var gx = Math.abs(a[0] - b[0]), gy = Math.abs(a[1] - b[1]);
          if (gy < 0.05 * spanY) { if (gx > 1e-6) dx = Math.min(dx, gx); } else dy = Math.min(dy, gy);
        }); });
        var sx = isFinite(dx) ? (W + 30) / dx : 1, sy = isFinite(dy) ? (H + 50) / dy : sx;
        var minX = Math.min.apply(null, xs), maxY = Math.max.apply(null, ys);
        var pts = ns.map(function (n) { var p = n.data('pos'); return { n: n, x: x0 + (p[0] - minX) * sx, y: (maxY - p[1]) * sy }; });
        // minimal adjustment: boxes that would still overlap (a row drawn unevenly) are pushed right, row by row
        pts.sort(function (a, b) { return a.y - b.y || a.x - b.x; });
        var rows = [];
        pts.forEach(function (q) { var r = rows[rows.length - 1]; if (r && q.y - r[0].y < H + 10) r.push(q); else rows.push([q]); });
        var right = 0;
        rows.forEach(function (r) {
          r.sort(function (a, b) { return a.x - b.x; });
          for (var i = 1; i < r.length; i++) {
            var need = (r[i - 1].n.data('w') || W) / 2 + (r[i].n.data('w') || W) / 2 + 20;
            if (r[i].x - r[i - 1].x < need) r[i].x = r[i - 1].x + need;
          }
          r.forEach(function (q) { q.n.position({ x: q.x, y: q.y }); right = Math.max(right, q.x); bottom = Math.max(bottom, q.y); });
        });
        x0 = right + 2 * (W + 40);
      });
      var k = 0;                                         // boxes the figure does not place (a result named in a note): below
      leaves.forEach(function (n) { if (!n.data('pos')) n.position({ x: (k++) * (W + 40), y: bottom + 1.5 * (H + 60) }); });
      cy.edges().removeClass('routed ends').removeStyle('segment-distances segment-weights source-endpoint target-endpoint');
    });
    cy.nodes().updateCompoundBounds(true);
  }

  function layout(after, focusId) {
    var seq = ++layoutSeq, t0 = performance.now();
    if (S.authors && authorsLayoutPossible()) {
      authorsLayout(); placeGhosts(); cy.fit(cy.elements(), 30); if (cy.zoom() > 1) { cy.zoom(1); cy.center(); }
      lastNote = "authors' layout"; status(performance.now() - t0);
      if (after) after();
      return;
    }
    setBusy(true);
    // Groups need ELK's hierarchical mode; a large view, or a page where it
    // already took too long, gets the flat layout instead (groups dissolved).
    var n = cy.nodes().length;
    var compound = cy.nodes(':parent').length > 0 && n <= COMPOUND_MAX && !S.forceFlat && !S.slowCompound;
    var note = '';
    if (cy.nodes(':parent').length && !compound) {
      flatten();
      note = S.slowCompound ? 'flat layout (grouped layout was slow)' : 'flat layout (large view)';
    }
    var elk = new ELK();
    var run = function (useCompound) {
      var g = elkGraph(useCompound);
      return elk.layout(g.root).then(function (res) { return { res: res, map: g.map }; });
    };
    // ELK runs on this thread: wait a moment so the "laying out" note shows.
    new Promise(function (r) { setTimeout(r, 15); }).then(function () {
      return run(compound);
    }).catch(function (err) {
      console.info('[v2] compound layout failed, falling back to flat:', err && err.message);
      note = 'flat layout (compound layout failed)';
      flatten();
      return run(false);
    }).then(function (out) {
      if (seq !== layoutSeq) return;
      applyLayout(out.res, out.map);
      placeGhosts();
      var dt = performance.now() - t0;
      if (compound && dt > SLOW_MS) S.slowCompound = true;
      lastNote = note;
      fitView(focusId);
      setBusy(false);
      status(dt);
      if (!firstDone) {
        firstDone = true;
        window.__v2 = { firstLayoutMs: Math.round(performance.now()), scriptStartMs: Math.round(T0), layoutMs: Math.round(dt),
          nodes: cy.nodes().length, edges: cy.edges().length, level: S.level, note: note };
        console.log('V2_FIRST_LAYOUT ms=' + Math.round(performance.now()) + ' start=' + Math.round(T0) + ' layout=' + Math.round(dt) +
          ' level=' + S.level + ' nodes=' + cy.nodes().length + ' edges=' + cy.edges().length +
          (note ? ' note=' + note.replace(/ /g, '_') : ''));
      }
      if (/(^|[#&])dump=1/.test(location.hash)) dump();
      if (after) after();
    }).catch(function (err) {
      setBusy(false);
      console.info('[v2] layout failed:', err && err.message);
      document.getElementById('status').textContent = 'layout failed: ' + (err && err.message);
    });
  }

  // #dump=1: the drawn boxes and edges, as JSON in a <pre> (for checks run
  // with chrome --dump-dom).
  function dump() {
    var pre = document.getElementById('v2-dump') || document.body.appendChild(document.createElement('pre'));
    pre.id = 'v2-dump';
    pre.style.display = 'none';
    pre.textContent = JSON.stringify({
      level: level(),
      nodes: cy.nodes().filter(function (n) { return !n.isParent(); }).map(function (n) { return n.id(); }),
      edges: cy.edges().map(function (e) { return [e.source().id(), e.target().id(), e.classes().join(' ')]; })
    });
  }

  // Fit (the whole graph, or the element just opened); if that makes the text
  // unreadable, open at a readable zoom: on the top of the opened element, or
  // on the main result (else the most important node) with its sources above.
  function fitView(focusId) {
    var el = focusId ? cy.getElementById(focusId) : cy.collection();
    var target = el.nonempty() ? el.union(el.descendants()) : cy.elements();
    cy.fit(target, 30);
    if (document.body.classList.contains('bare')) return;   // figure mode: always the whole graph
    if (cy.zoom() > 1) { cy.zoom(1); cy.center(target); }
    if (cy.zoom() >= 0.55) return;
    var z = 0.8;
    if (cy.nodes().filter(function (n) { return !n.isParent(); }).length <= 30) {   // small: readable, from its top (Fit shows it whole)
      var b = target.boundingBox();
      cy.zoom(0.6); cy.pan({ x: cy.width() / 2 - 0.6 * (b.x1 + b.w / 2), y: 20 - 0.6 * b.y1 }); return;
    }
    cy.zoom(z);
    if (el.nonempty()) {
      var bb = target.boundingBox();
      cy.pan({ x: cy.width() / 2 - z * (bb.x1 + bb.w / 2), y: 30 - z * bb.y1 });
      return;
    }
    var best = null;
    cy.nodes().forEach(function (n) {
      if (n.isParent()) return;
      var x = NODE[n.id()], score = x ? (MAIN[x.id] ? 10 : 0) + x.imp : 0;
      if (!best || score > best.s) best = { n: n, s: score };
    });
    var p = best ? best.n.position() : { x: 0, y: 0 };
    cy.pan({ x: cy.width() / 2 - z * p.x, y: cy.height() * 0.7 - z * p.y });
  }

  function status(dt) {
    var lv = level(), nb = cy.nodes().filter(function (n) { return !n.isParent(); }).length;
    var txt = { overview: 'Overview', results: 'Results', full: 'Full' }[lv];
    if (S.focus) txt += S.focus.mode === 'main' ? ' · path to main results'
      : S.focus.mode === 'up' ? ' · what ' + dispNum(S.focus.id) + ' rests on'
      : S.focus.mode === 'down' ? ' · what rests on ' + dispNum(S.focus.id)
      : ' · neighbourhood of ' + S.focus.id + ' (' + S.k + ' step' + (S.k > 1 ? 's' : '') + ')';
    txt += ' · ' + nb + ' boxes, ' + cy.edges().length + ' edges · layout ' + Math.round(dt) + ' ms';
    if (lastNote) txt += ' · ' + lastNote;
    if (lv === 'overview') txt += ' · click a section to open it, its frame to close it';
    else if (lv !== 'overview') txt += ' · double-click a result to open its proof';
    document.getElementById('status').textContent = txt;
  }

  // ── Rendering ─────────────────────────────────────────────────────────
  function render(after, focusId) {
    var built = buildElements();
    cy.batch(function () {
      cy.elements().remove();
      cy.add(built.els);
      if (level() === 'overview' && Object.keys(S.open).length)
      {                                  // keep only the closed sections linked to an open one
        var inOpen = cy.nodes('[kind = "secopen"]').descendants();
        var linked = cy.nodes('[kind = "secbox"]').filter(function (g) { return g.isOrphan() && g.edgesWith(inOpen).nonempty(); });
        // the linked sections are context: shown by default around a small section, hidden around a big one
        S.ctxN = linked.length;
        S.ctxNow = S.ctx !== null ? S.ctx : G.nodes.filter(function (x) { return S.open[x.top] && shownBase(x); }).length <= 15;
        cy.nodes('[kind = "secbox"]').filter(function (g) { return g.isOrphan(); }).difference(S.ctxNow ? linked : cy.collection()).remove();
      }
    });
    paintNodes();
    applySearch();
    (S.mark || []).forEach(function (id) {             // #mark=: circle these nodes
      var n = cy.getElementById(id);
      if (n.nonempty()) n.data('mk', S.markc || '#e74c3c').addClass('marked');
    });
    (S.dim || []).forEach(function (id) {              // #dim=: fade these nodes
      var n = cy.getElementById(id);
      if (n.nonempty()) n.addClass('dimmed');
    });
    syncControls();
    cy.resize();                         // the toolbars above may have re-wrapped
    layout(function () {
      if (S.selected && cy.getElementById(S.selected).nonempty()) cy.getElementById(S.selected).select();
      mathLayer();
      if (after) after();
    }, focusId);
  }

  // ── Math layer: boxes whose text has math are typeset by MathJax in HTML
  // boxes over the canvas (the canvas cannot draw TeX), kept in step with the view.
  var MLAYER = null;
  function esc(t) {
    return String(t || '').replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; });
  }
  function mathLayer() {
    if (!MLAYER) {
      MLAYER = document.createElement('div');
      MLAYER.id = 'mathlayer';
      document.getElementById('cy').appendChild(MLAYER);
      cy.on('viewport', placeLayer);
      cy.on('position', 'node[tex = 1]', function (ev) { placeBox(ev.target); });
    }
    MLAYER.innerHTML = '';
    var made = [];
    cy.nodes('[tex = 1]').forEach(function (n) {
      var d = n.data(), div = document.createElement('div');
      div.className = 'mbox';
      div.id = 'mb-' + n.id();
      var lh = d.fs * 1.25, headH = d.h * d.band / 100;
      var bodyLines = Math.max(1, Math.floor((d.h - headH - 6) / lh) - (d.texExtra ? 1 : 0));
      div.style.cssText = 'width:' + d.w + 'px;height:' + d.h + 'px;font-size:' + d.fs + 'px;';
      var headLines = Math.max(1, Math.floor((headH - 4) / lh));
      div.innerHTML = '<div class="mhead" style="height:' + headH + 'px;max-height:' + (headLines * lh + 2) + 'px;-webkit-line-clamp:' + headLines + '">' +
        esc(d.texHead) + '</div><div class="mbody" style="-webkit-line-clamp:' + bodyLines + '">' + esc(d.texBody) + '</div>' +
        (d.texExtra ? '<div class="mextra">' + esc(d.texExtra) + '</div>' : '');
      MLAYER.appendChild(div);
      placeBox(n);
      made.push(div);
    });
    placeLayer();
    if (made.length && window.MathJax && MathJax.startup)
      MathJax.startup.promise.then(function () { return MathJax.typesetPromise(made); }).catch(function () {});
  }
  function placeBox(n) {
    var div = document.getElementById('mb-' + n.id());
    if (!div) return;
    var p = n.position(), d = n.data();
    div.style.left = (p.x - d.w / 2) + 'px';
    div.style.top = (p.y - d.h / 2) + 'px';
    div.style.opacity = n.hasClass('dimmed') || n.hasClass('dim') ? 0.25 : 1;
  }
  function placeLayer() {
    if (!MLAYER) return;
    var z = cy.zoom(), pan = cy.pan();
    MLAYER.style.transform = 'translate(' + pan.x + 'px,' + pan.y + 'px) scale(' + z + ')';
    MLAYER.style.display = z * 11 < 5 ? 'none' : '';     // as the canvas hides tiny text
  }

  // ── Controls ──────────────────────────────────────────────────────────
  var TOGGLES = [
    ['ghosts', 'Foundations', function () { return G.ghosts.length; }, G.grounded ? 'Textbook and ProofWiki concepts the nodes are grounded to' : 'External results from the foundation graph that nodes rely on'],
    ['aux', 'Examples & Remarks', function () { return G.nodes.filter(function (n) { return AUX[n.type]; }).length; }, ''],
    ['extdef', 'Cited definitions', function () { return G.nodes.filter(function (n) { return n.origin === 'external' && n.type === 'definition'; }).length; }, 'Standard or cited definitions the paper recalls (dashed boxes): the vocabulary its results use'],
    ['ext', 'Cited results', function () { return G.nodes.filter(function (n) { return n.origin === 'external' && n.type !== 'definition'; }).length; }, 'Results the paper cites rather than proves (dashed boxes)'],
    ['low', 'Low-confidence edges', function () { return G.edges.filter(function (e) { return e.low; }).length; }, ''],
    ['implied', 'Implied edges', function () { return G.edges.filter(function (e) { return e.implied; }).length; }, 'Edges also reachable by a longer path, in the whole graph (classic)'],
    ['back', 'Backward edges', function () { return G.edges.filter(function (e) { return e.back; }).length; }, 'Dependencies that point against paper order (dash-dotted)'],
    ['mention', 'Mentions', function () { return G.edges.filter(function (e) { return e.mention; }).length; }, 'References that do not rely on the source (thin, light dashes)'],
    ['nested', 'Nested results', function () { return G.nodes.filter(function (n) { return n.inside; }).length; }, 'Results stated inside a proof or another result']
  ];

  function buildControls() {
    var tg = document.getElementById('toggles');
    TOGGLES.forEach(function (t) {
      var b = document.createElement('button');
      var cnt = t[2]();
      b.className = 'toggle-btn'; b.id = 'tg-' + t[0];
      b.textContent = t[1] + ' (' + cnt + ')';
      if (t[3]) b.title = t[3];
      if (!cnt) b.disabled = true;
      b.onclick = function () { S.show[t[0]] = !S.show[t[0]]; render(); };
      tg.appendChild(b);
    });
    var tr = document.createElement('button');
    tr.className = 'toggle-btn'; tr.id = 'tg-tred';
    tr.textContent = 'Transitive reduction';
    tr.title = 'Hide every edge implied by a longer path in the current view';
    tr.onclick = function () { S.tred = !S.tred; render(); };
    tg.appendChild(tr);

    document.querySelectorAll('#level-group .seg').forEach(function (b) {
      b.onclick = function () {
        if (S.level === b.dataset.level && !S.focus) {
          if (S.level === 'overview' && anyOpen()) { S.open = {}; render(); }   // back to all boxes
          return;
        }
        S.level = b.dataset.level; S.focus = null; render();
      };
    });
    document.getElementById('back-btn').onclick = goBack;
    document.getElementById('ctx-btn').onclick = function () { S.ctx = !S.ctxNow; render(); };
    document.getElementById('lay-btn').onclick = function () { S.authors = !S.authors; render(); };
    document.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Escape' || /^(INPUT|TEXTAREA)$/.test((ev.target || {}).tagName || '')) return;
      closePanel() || goBack();
    });
    var mb = document.getElementById('main-btn');
    if (!G.main.length) { mb.disabled = true; mb.title = 'No main-result candidates in this paper'; }
    mb.onclick = function () {
      S.focus = (S.focus && S.focus.mode === 'main') ? null : { mode: 'main' };
      render();
    };
    // Focus on the selected node: its neighbourhood, everything it rests on, everything that rests on it.
    [['nbhd-btn', 'nbhd', 'Neighbourhood'], ['up-btn', 'up', 'Rests on'], ['down-btn', 'down', 'Depends on it']].forEach(function (p) {
      document.getElementById(p[0]).onclick = function () {
        var on = S.focus && S.focus.mode === p[1];
        if (on && S.focus.id === S.selected) { S.focus = null; render(); return; }
        if (!S.selected || !NODE[S.selected]) {
          document.getElementById('status').textContent = 'Select a node first (click it), then ' + p[2] + '.';
          return;
        }
        S.focus = { mode: p[1], id: S.selected }; render();
      };
    });
    document.getElementById('hop-minus').onclick = function () { if (S.k > 1) { S.k--; if (S.focus && S.focus.mode === 'nbhd') render(); else syncControls(); } };
    document.getElementById('hop-plus').onclick = function () { if (S.k < 9) { S.k++; if (S.focus && S.focus.mode === 'nbhd') render(); else syncControls(); } };
    document.getElementById('fit-btn').onclick = function () { cy.fit(cy.elements(), 30); };
    // A page opened from disk (a downloaded graph) has no portal to go back to.
    if (location.protocol === 'file:') document.getElementById('home-link').style.display = 'none';
    // Legend / Filters rows: shown by default (hidden when embedded in another page); the choice is remembered.
    [['legend-btn', 'show-legend'], ['filters-btn', 'show-filters']].forEach(function (p) {
      var btn = document.getElementById(p[0]), key = 'saranga.' + p[1];
      function set(on) {
        document.body.classList.toggle(p[1], on); btn.classList.toggle('on', on);
        try { localStorage.setItem(key, on ? '1' : '0'); } catch (e) {}
        if (cy) cy.resize();
      }
      var saved = null; try { saved = localStorage.getItem(key); } catch (e) {}
      set(saved ? saved === '1' : window.self === window.top);
      btn.onclick = function () { set(!document.body.classList.contains(p[1])); };
    });
    document.getElementById('zin-btn').onclick = function () { zoomBy(1.3); };
    document.getElementById('zout-btn').onclick = function () { zoomBy(1 / 1.3); };
    var si = document.getElementById('search');
    si.addEventListener('input', function () { S.search = si.value.trim(); applySearch(); });
    si.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') nextMatch(); });
    var info = document.getElementById('info-btn');
    if (G.n_notes) info.textContent = 'Paper info (' + G.n_notes + ' notes)';
    if (typeof ORPHANS !== 'undefined' && ORPHANS.length) {
      var ob = document.getElementById('orphan-toggle');
      ob.style.display = 'block';
      ob.textContent = ORPHANS.length + ' orphan eq' + (ORPHANS.length > 1 ? 's' : '');
    }
    buildLegend();
  }

  function zoomBy(f) {
    cy.zoom({ level: Math.max(0.05, Math.min(4, cy.zoom() * f)), renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  }

  function anyOpen() { return Object.keys(S.open).length > 0; }
  // One step coarser: leave a focus, else close the last opened section.
  function goBack() {
    if (S.focus) { S.focus = null; render(); return; }
    if (level() === 'overview' && anyOpen()) {
      var last = S.openOrder.filter(function (g) { return S.open[g]; }).pop();
      if (last) closeGroup(last); else S.open = {};
      render(); return;
    }
  }

  function syncControls() {
    var back = document.getElementById('back-btn');
    back.style.display = (S.focus || (level() === 'overview' && anyOpen())) ? 'block' : 'none';
    back.textContent = S.focus ? '\u2190 Leave focus' : '\u2190 Close section';
    var lay = document.getElementById('lay-btn');
    lay.style.display = authorsLayoutPossible() ? 'block' : 'none';
    lay.textContent = S.authors ? 'Layout by dependency depth' : "Authors' layout";
    var ctx = document.getElementById('ctx-btn');
    ctx.style.display = !S.focus && level() === 'overview' && anyOpen() && S.ctxN ? 'block' : 'none';
    ctx.textContent = S.ctxNow ? 'Hide linked sections' : 'Show linked sections (' + S.ctxN + ')';
    document.querySelectorAll('#level-group .seg').forEach(function (b) {
      b.classList.toggle('on', !S.focus && S.level === b.dataset.level);
    });
    TOGGLES.forEach(function (t) {
      var b = document.getElementById('tg-' + t[0]);
      if (b) b.dataset.showing = S.show[t[0]] ? '1' : '0';
    });
    document.getElementById('tg-tred').dataset.showing = S.tred ? '1' : '0';
    document.getElementById('main-btn').dataset.showing = (S.focus && S.focus.mode === 'main') ? '1' : '0';
    document.getElementById('nbhd-btn').dataset.showing = (S.focus && S.focus.mode === 'nbhd') ? '1' : '0';
    document.getElementById('up-btn').dataset.showing = (S.focus && S.focus.mode === 'up') ? '1' : '0';
    document.getElementById('down-btn').dataset.showing = (S.focus && S.focus.mode === 'down') ? '1' : '0';
    document.getElementById('hop-k').textContent = S.k;
  }

  function legendLine(color, width, dash, label) {
    return '<div class="legend-item"><svg class="legend-line" width="30" height="10"><line x1="0" y1="5" x2="30" y2="5" stroke="' +
      color + '" stroke-width="' + width + '"' + (dash ? ' stroke-dasharray="' + dash + '"' : '') + '/></svg> ' + label + '</div>';
  }

  function buildLegend() {
    var present = {}, h = '';
    G.nodes.forEach(function (n) { present[n.type] = true; });
    if (Object.keys(G.steps).length) present.proof_step = true;
    Object.keys(G.colors).forEach(function (t) {
      if (!present[t]) return;
      var c = G.colors[t];
      h += '<div class="legend-item"><div class="legend-color" style="background:' + c.body + ';border-color:' + c.header + ';"></div>' +
        t.replace(/_/g, ' ').replace(/\b\w/g, function (x) { return x.toUpperCase(); }) + '</div>';
    });
    h += '<div class="legend-item" style="margin-left:12px;"><span style="font-size:18px;color:#555;">&#8594;</span> A supports B</div>';
    var seenTypes = {};
    G.edges.forEach(function (e) { seenTypes[e.type] = true; });
    Object.keys(G.edge_colors).forEach(function (t) {
      if (seenTypes[t] && t !== 'uses') h += legendLine(G.edge_colors[t], 2, t === 'resolves' ? '5,3' : '', t);
    });
    h += legendLine('#455A64', 2, '6,2,1,2', 'backward reference');
    h += legendLine('#5C6BC0', 1.5, '2,2', 'mention');
    h += legendLine('#546E7A', 1.8, '4,3', 'low confidence');
    h += legendLine('#7F8C8D', 2, '1,1.5', 'stated inside');
    h += '<div class="legend-item"><div class="legend-color" style="background:#fff;border:3px solid #C0392B;box-shadow:0 0 0 3px #FFE082;"></div>&#9733; main result</div>';
    h += '<div class="legend-item"><div class="legend-color" style="background:#fff;border:1.5px dashed #777;"></div>cited (external)</div>';
    h += '<div class="legend-item" title="Box size grows with importance: how much of the paper builds on the node">box size = importance</div>';
    document.getElementById('legend').innerHTML = h;
  }

  // ── Search ────────────────────────────────────────────────────────────
  var matchIdx = -1;
  function matchesOf(q) {
    q = q.toLowerCase();
    var out = {};
    G.nodes.forEach(function (n) {
      var d = (typeof DETAILS !== 'undefined' && DETAILS[n.id]) || {};
      var hay = (n.id + ' ' + n.name + ' ' + n.short + ' ' + (d.statement || '')).toLowerCase();
      if (hay.indexOf(q) >= 0) out[n.id] = true;
    });
    Object.keys(STEP).forEach(function (sid) {
      var s = STEP[sid];
      if ((sid + ' ' + s.name + ' ' + s.short).toLowerCase().indexOf(q) >= 0) out[sid] = true;
    });
    return out;
  }
  function applySearch() {
    if (!cy) return;
    var cnt = document.getElementById('search-count');
    cy.batch(function () {
      cy.elements().removeClass('match dim');
      if (!S.search) { cnt.textContent = ''; return; }
      var m = matchesOf(S.search), total = Object.keys(m).length, vis = 0;
      cy.nodes().forEach(function (n) {
        var id = n.id(), hit = !!m[id];
        if (!hit && (n.data('kind') === 'secbox' || n.data('kind') === 'secopen')) {
          hit = G.nodes.some(function (x) { return m[x.id] && groupPath(x).indexOf(id) >= 0; }) && n.data('kind') === 'secbox';
        }
        if (!hit && n.data('kind') === 'node' && NODE[id] && NODE[id].nsteps) {
          hit = (G.steps[id] || []).some(function (s) { return m[s.id]; }) && !S.proofs[id];
        }
        if (hit) { n.addClass('match'); if (m[id]) vis++; }
        else if (!n.isParent()) n.addClass('dim');
      });
      cy.edges().addClass('dim');
      cnt.textContent = total + ' found' + (total > vis ? ' (' + (total - vis) + ' folded)' : '');
    });
    matchIdx = -1;
    if (MLAYER) cy.nodes('[tex = 1]').forEach(placeBox);
  }
  function nextMatch() {
    var ms = cy.nodes('.match');
    if (!ms.length) return;
    matchIdx = (matchIdx + 1) % ms.length;
    var n = ms[matchIdx];
    cy.animate({ center: { eles: n }, zoom: Math.max(cy.zoom(), 0.9) }, { duration: 250 });
    if (NODE[n.id()]) select(n.id());
  }

  // ── Selection, panel, hover ───────────────────────────────────────────
  function edgeList(id) {
    var uses = [], usedBy = [];
    G.edges.forEach(function (e) {
      if (e.t === id) uses.push(e); else if (e.s === id) usedBy.push(e);
    });
    var item = function (e, other) {
      var n = NODE[other];
      var flags = (e.back ? ' backward' : '') + (e.mention ? ' mention' : '') + (e.implied ? ' implied' : '');
      return '<div>&bull; <span class="nodelink" data-nid="' + escAttr(other) + '" onclick="showDetail(this.dataset.nid)">' +
        esc(dispNum(other) + ': ' + (n ? n.name || n.type : '')) + '</span> <span style="color:#888;">' + esc(e.type + flags) +
        (e.conf !== undefined && e.conf !== null ? ', conf ' + Number(e.conf).toFixed(2) : '') + '</span></div>';
    };
    var h = '';
    if (uses.length) h += '<div class="detail-section v2-edges"><h4>Uses (' + uses.length + ')</h4>' + uses.map(function (e) { return item(e, e.s); }).join('') + '</div>';
    if (usedBy.length) h += '<div class="detail-section v2-edges"><h4>Used by (' + usedBy.length + ')</h4>' + usedBy.map(function (e) { return item(e, e.t); }).join('') + '</div>';
    return h;
  }

  function panelExtras(id) {
    var panel = document.getElementById('detail-panel');
    if (panel.className !== 'open' || _lastDetailNode !== id) return;
    var n = NODE[id], acts = '';
    if (n && n.nsteps) acts += '<button data-act="proof">' + (S.proofs[id] ? 'Close proof' : 'Open proof (' + n.nsteps + ' steps)') + '</button>';
    if (n) acts += '<button data-act="up" title="Everything this node rests on, all the way down">\u22EF\u2192\u25CF Rests on</button>' +
      '<button data-act="down" title="Everything that rests on this node, all the way up">\u25CF\u2192\u22EF Depends on it</button>' +
      '<button data-act="nbhd" title="What it uses and what uses it, only k steps each way">\u2192\u25CF\u2192 Neighbourhood (' + S.k + ')</button>';
    if (n) acts += '<span style="font-size:11px;color:#777;align-self:center;">importance ' + n.imp.toFixed(1) +
      (MAIN[id] ? ' · ★ main result' : '') + ' · ' + n.desc + ' build on it</span>';
    var div = document.createElement('div');
    div.className = 'v2-actions';
    div.innerHTML = acts;
    var h3 = panel.querySelector('h3');
    if (h3 && window.dispId && dispId(id) !== dispNum(id)) {          // the heading with the paper's number, like the box
      var tn = h3.firstChild;
      if (tn && tn.nodeType === 3 && tn.textContent.indexOf(dispId(id)) === 0) tn.textContent = dispNum(id) + tn.textContent.slice(dispId(id).length);
    }
    if (h3 && h3.nextSibling) panel.insertBefore(div, h3.nextSibling.nextSibling); else panel.prepend(div);
    div.querySelectorAll('button').forEach(function (b) {
      b.onclick = function () {
        if (b.dataset.act === 'proof') toggleProof(id);
        else { S.focus = { mode: b.dataset.act, id: id }; render(); }
      };
    });
    var ed = document.createElement('div');
    ed.innerHTML = edgeList(id);
    panel.appendChild(ed);
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([ed]).catch(function () {});   // TeX in node names
  }

  function showStep(sid) {
    var host = STEP_HOST[sid], d = (DETAILS[host] || {}), s = null;
    (d.steps || []).forEach(function (x) { if (x.id === sid) s = x; });
    var panel = document.getElementById('detail-panel');
    _lastDetailNode = sid;
    var h = '<h3 style="margin:0 0 8px;font-size:16px;">' + esc(sid) + (STEP[sid].name ? ': ' + esc(STEP[sid].name) : '') + '</h3>';
    h += '<div style="font-size:12px;color:#888;margin-bottom:6px;">' + esc((s && s.type) || 'proof step') + ' in the proof of ' + nodeLink(host) + '</div>';
    if (s) {
      h += '<div style="margin-bottom:6px;">' + rigorBadge(s.rigor) + confBadge(s.confidence) + '</div>';
      if (s.statement_short) h += '<div class="detail-section"><h4>Summary</h4><div style="font-size:13px;">' + esc(s.statement_short) + '</div></div>';
      h += '<div class="detail-section"><h4>Step</h4><div style="font-size:14px;">' + esc(s.statement || s.statement_clean || '') + '</div></div>';
    }
    var nk = (KIDS[sid] || []).length;
    if (nk) h += '<div class="v2-actions"><button id="v2-step-btn">' + (S.proofs[sid] ? 'Close sub-steps' : 'Open ' + nk + ' sub-step' + (nk > 1 ? 's' : '')) + '</button></div>';
    panel.innerHTML = h;
    panel.className = 'open';
    addCloseButton();
    var b = document.getElementById('v2-step-btn');
    if (b) b.onclick = function () { toggleProof(sid); };
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([panel]).catch(function () {});
  }

  // The panel slides in and out (0.3 s): tell cytoscape its box changed.
  // After the panel opens or closes: keep the selected box in the part of the canvas the panel leaves free
  function panelMoved() {
    setTimeout(function () {
      if (!cy) return;
      cy.resize();
      var el = S.selected ? cy.getElementById(S.selected) : cy.collection(), panel = document.getElementById('detail-panel');
      if (el.empty()) return;
      var bb = el.renderedBoundingBox(), pr = panel.getBoundingClientRect(), cr = cy.container().getBoundingClientRect();
      var w = panel.className === 'open' && pr.left < cr.right ? pr.left - cr.left : cy.width();
      if (bb.x1 < 0 || bb.y1 < 0 || bb.x2 > w || bb.y2 > cy.height())
        cy.animate({ panBy: { x: w / 2 - (bb.x1 + bb.x2) / 2, y: cy.height() / 2 - (bb.y1 + bb.y2) / 2 } }, { duration: 250 });
    }, 350);
  }

  function closePanel() {
    var panel = document.getElementById('detail-panel');
    if (panel.className !== 'open') return false;
    panel.className = ''; _lastDetailNode = null;
    if (cy) { cy.nodes(':selected').unselect(); setTimeout(function () { cy.resize(); }, 350); }
    return true;
  }

  function addCloseButton() {
    var panel = document.getElementById('detail-panel');
    if (panel.className !== 'open' || panel.querySelector('.v2-close')) return;
    var b = panel.insertBefore(document.createElement('button'), panel.firstChild);
    b.className = 'v2-close'; b.title = 'Close (Esc)'; b.textContent = '\u2715';
    b.onclick = closePanel;
  }

  function select(id) {
    S.selected = id;
    panelMoved();
    cy.nodes(':selected').unselect();
    var n = cy.getElementById(id);
    if (n.nonempty()) n.select();
    if (STEP[id]) { showStep(id); return; }
    classicShowDetail(id);              // the classic panel; a second click closes it
    panelExtras(id);
    addCloseButton();
    if (S.focus && S.focus.mode === 'nbhd' && S.focus.id !== id && NODE[id]) {
      document.getElementById('status').textContent = 'Neighbourhood of ' + S.focus.id + '; click Neighbourhood to recentre on ' + id + '.';
    }
  }

  // Panel links (classic nodeLink) land here: open whatever hides the node.
  window.showDetail = function (id) {
    var host = (typeof FOLDED_HOST !== 'undefined' && FOLDED_HOST[id] && !NODE[id] && !STEP[id]) ? FOLDED_HOST[id] : id;
    var n = NODE[host];
    var need = false;
    if (n && cy.getElementById(host).empty()) {
      if (S.focus) { S.focus = null; need = true; }
      if (n.origin === 'external' && n.type === 'definition' && !S.show.extdef) { S.show.extdef = true; need = true; }
      if (n.origin === 'external' && n.type !== 'definition' && !S.show.ext) { S.show.ext = true; need = true; }
      if (AUX[n.type] && !S.show.aux) { S.show.aux = true; need = true; }
      if (n.inside && !S.show.nested) { S.show.nested = true; need = true; }
      if (S.level === 'results' && !n.res) { S.level = 'full'; need = true; }
      if (S.level === 'overview') groupPath(n).forEach(function (g) { if (!S.open[g]) { S.open[g] = true; need = true; } });
    }
    var go = function () {
      var el = cy.getElementById(host);
      if (el.nonempty()) cy.animate({ center: { eles: el }, zoom: Math.max(cy.zoom(), 0.8) }, { duration: 250 });
      select(host);
    };
    if (need) render(go); else go();
  };

  function toggleProof(id) {
    if (S.proofs[id]) {
      delete S.proofs[id];
      Object.keys(S.proofs).forEach(function (k) {     // close what was open inside it
        if (STEP[k] && (STEP_HOST[k] === id || isUnder(k, id))) delete S.proofs[k];
      });
    } else S.proofs[id] = true;
    render(function () {
      var el = cy.getElementById(id);
      if (el.nonempty()) cy.animate({ fit: { eles: el.union(el.descendants()), padding: 60 } }, { duration: 250 });
      if (NODE[id]) { _lastDetailNode = null; select(id); }
    });
  }
  function isUnder(sid, anc) {
    var p = STEP[sid] && STEP[sid].parent;
    while (p) { if (p === anc) return true; p = STEP[p] && STEP[p].parent; }
    return false;
  }

  function initCy() {
    cy = cytoscape({
      container: document.getElementById('cy'),
      style: STYLE, minZoom: 0.03, maxZoom: 4,
      boxSelectionEnabled: false, selectionType: 'single', textureOnViewport: false
    });
    var lastTap = null;
    cy.on('tap', 'node', function (ev) {
      // A tap on a node inside a compound bubbles up to the compound: once only.
      if (lastTap === ev.originalEvent) return;
      lastTap = ev.originalEvent;
      var n = ev.target, kind = n.data('kind');
      if (kind === 'secbox') { S.open[n.id()] = true; S.openOrder.push(n.id()); openSubsIfSmall(n.id()); render(null, n.id()); return; }
      if (kind === 'secopen') { closeGroup(n.id()); render(); return; }
      if (kind === 'ghost') { _lastDetailNode = null; showGhostDetail(n.data('name')); return; }
      if (kind === 'proofframe' || kind === 'partframe') { select(n.data('of')); return; }
      select(n.id());
    });
    cy.on('tap', function (ev) { if (ev.target === cy) closePanel(); });   // a click on the empty canvas
    cy.on('dbltap', 'node', function (ev) {
      var id = ev.target.id();
      if ((NODE[id] && NODE[id].nsteps) || (STEP[id] && KIDS[id])) toggleProof(id);
    });
    cy.on('mouseover', 'node', function (ev) {
      var n = ev.target;
      n.connectedEdges().addClass('hl');
      n.neighborhood('node').addClass('hl');
    });
    cy.on('mouseout', 'node', function () { cy.elements('.hl').removeClass('hl'); });
  }

  function openSubsIfSmall(gid) {
    var g = SEC[gid];
    if (!g || !g.subs || PROMOTE) return;
    var n = G.nodes.filter(function (x) { return x.top === gid && shownBase(x); }).length;
    if (n <= 15) g.subs.forEach(function (s) { S.open[s] = true; });
  }
  function closeGroup(gid) {
    delete S.open[gid];
    var g = SEC[gid];
    if (g && g.subs) g.subs.forEach(function (s) { delete S.open[s]; });
  }

  // #selftest=1: run through every view and control once, for headless
  // checks; logs V2_SELFTEST with the number of steps, or the error.
  function selftest() {
    var withSteps = G.nodes.filter(function (n) { return n.nsteps > 0; })[0];
    var deep = Object.keys(KIDS).filter(function (k) { return STEP[k]; })[0];
    var some = (withSteps || G.nodes[0] || {}).id;
    var steps = [
      function () { S.level = 'results'; },
      function () { S.level = 'full'; },
      function () { if (withSteps) S.proofs[withSteps.id] = true; },
      function () { if (deep) { S.proofs[STEP_HOST[deep]] = true; S.proofs[deep] = true; } },
      function () { if (some) window.showDetail(some); },
      function () {
        var p = document.getElementById('detail-panel'), b = p.querySelector('.v2-close');
        if (some && (p.className !== 'open' || !b)) throw new Error('panel without a close button');
        if (b) { b.click(); if (p.className === 'open') throw new Error('close button left the panel open'); }
        if (some) { window.showDetail(some); closePanel(); if (p.className === 'open') throw new Error('Esc close failed'); }
      },
      function () { if (some) { S.focus = { mode: 'nbhd', id: some }; S.k = 2; } },
      function () { S.focus = G.main.length ? { mode: 'main' } : null; },
      function () { S.focus = null; S.tred = true; },
      function () { S.tred = false; Object.keys(S.show).forEach(function (k) { S.show[k] = true; }); },
      function () { S.show.ghosts = false; S.level = 'overview'; },
      function () { var g = G.sections[0]; if (g) { S.open[g.id] = true; openSubsIfSmall(g.id); } },
      function () { S.level = 'overview'; S.open = {}; var g = G.sections[0]; if (g) { S.open[g.id] = true; S.openOrder.push(g.id); } },
      function () { goBack(); if (S.level === 'overview' && anyOpen()) throw new Error('back left a section open'); },
      function () { S.search = 'the'; applySearch(); nextMatch(); S.search = ''; },
      function () { S.forceFlat = true; S.level = 'full'; },
      function () { S.forceFlat = false; S.proofs = {}; S.open = {}; S.level = G.level; }
    ];
    var t0 = performance.now();
    (function next(i) {
      if (i >= steps.length) {
        console.log('V2_SELFTEST ok steps=' + steps.length + ' ms=' + Math.round(performance.now() - t0));
        return;
      }
      try { steps[i](); } catch (err) { console.log('V2_SELFTEST error step=' + i + ' ' + err.message); return; }
      render(function () { next(i + 1); });
    })(0);
  }

  // State from the URL hash, e.g. #level=full&open=sec:3&proof=TP2&focus=main&select=TP2
  var hashFocus = null;
  function readHash() {
    var sel = null;
    location.hash.replace(/^#/, '').split('&').forEach(function (kv) {
      var i = kv.indexOf('='), k = kv.slice(0, i), v = decodeURIComponent(kv.slice(i + 1));
      if (i < 0 || !v) return;
      if (k === 'level' && /^(overview|results|full)$/.test(v)) S.level = v;
      else if (k === 'open') v.split(',').forEach(function (g) { S.open[g] = true; openSubsIfSmall(g); hashFocus = g; });
      else if (k === 'proof') v.split(',').forEach(function (g) { S.proofs[g] = true; });
      else if (k === 'k') S.k = Math.max(1, Math.min(9, parseInt(v, 10) || 1));
      else if (k === 'show') v.split(',').forEach(function (t) { if (t in S.show) S.show[t] = true; });
      else if (k === 'hide') v.split(',').forEach(function (t) { if (t in S.show) S.show[t] = false; });
      else if (k === 'tred') S.tred = v === '1';
      else if (k === 'ctx') S.ctx = v !== '0';   // linked sections around an open one: 1 shown, 0 hidden
      else if (k === 'mark') S.mark = v.split(',');
      else if (k === 'markc') S.markc = v;
      else if (k === 'dim') S.dim = v.split(',');
      else if (k === 'bare' && v === '1') document.body.classList.add('bare');   // figure mode: graph only
      else if (k === 'select') sel = v;
      else if (k === 'focus' && v === 'main') S.focus = { mode: 'main' };
      else if (k === 'focus' && /^(up|down):/.test(v) && NODE[v.slice(v.indexOf(':') + 1)]) S.focus = { mode: v.split(':')[0], id: v.slice(v.indexOf(':') + 1) };
      else if (k === 'focus' && NODE[v]) S.focus = { mode: 'nbhd', id: v };
    });
    return sel;
  }

  function start() {
    window.addEventListener('resize', function () { if (cy) cy.resize(); });
    window.addEventListener('load', function () {      // TeX in the paper title
      var M = window.MathJax;
      if (M && M.startup && M.startup.promise) M.startup.promise.then(function () {
        return M.typesetPromise([document.getElementById('title')]);
      }).catch(function () {});
    });
    var sel = readHash();
    initCy();
    buildControls();
    var after = sel ? function () { window.showDetail(sel); } : null;
    if (/(^|[#&])selftest=1/.test(location.hash)) after = selftest;
    render(after, hashFocus);
  }
  if (typeof cytoscape === 'undefined' || typeof ELK === 'undefined') {
    document.getElementById('status').textContent = 'Could not load the graph libraries (lib/).';
    console.error('[v2] cytoscape or ELK missing');
    return;
  }
  start();
})();
