"""Authomathics database portal — local + HF-Space-compatible server.

Serves the static portal files AND a /render endpoint that generates the
rich knowledge-graph HTML on the fly from a paper's JSON, using the same
visualize_annotation.py renderer that produced the per-paper HTML files
on Drive.

Stores ONLY JSON per paper. The HTML is generated on-demand and cached
under portal/cache/. This is the architecture intended for HF Spaces —
on a Docker Space, run this same script via `python portal_server.py`.

Usage (local):
    cd portal && python3 portal_server.py
    open http://localhost:8000

The /render endpoint:
    GET /render?id=paper015&tier=2
    -> reads data/tier2/paper015.json
    -> runs visualize_annotation.py --html-only on it
    -> returns the resulting HTML (text/html)
    -> caches gzipped under cache/paper015_<jsonmtime>.html.gz

Subsequent requests for the same paper hit the cache and return instantly.
Cache invalidates automatically when the source JSON's mtime changes.
"""
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PORTAL_DIR = Path(__file__).resolve().parent
DATA_DIR = PORTAL_DIR / "data"
CACHE_DIR = PORTAL_DIR / "cache"
WORK_DIR = CACHE_DIR / "_work"
CACHE_DIR.mkdir(exist_ok=True)
WORK_DIR.mkdir(exist_ok=True)

VIZ_SCRIPT = PORTAL_DIR.parent / "src" / "visualize_annotation.py"
ALIGN_SCRIPT = PORTAL_DIR.parent / "src" / "visualize_alignment.py"
MANIFEST_PATH = DATA_DIR / "manifest.json"
PYTHON = sys.executable
RENDER_TIMEOUT_SEC = 180

# ── v6 data (Oct 2026) ──────────────────────────────────────────────────────
# Tier 2 = the 200 v6 silver papers: their LLM pages (<id>_new.html) and
# rule-based pages (<id>_rules.html) are already built, served as they are.
REPO_DIR = PORTAL_DIR.parent
SILVER_DIR = Path(os.environ.get("SARANGA_SILVER_DIR", REPO_DIR / "corpus/silver/opus-5.5__v6"))
GRAPH_BUILD = REPO_DIR / "src" / "graph_view" / "build.py"
# Tier 3 = the 100K corpus: an index of every paper (data/tier3_v6/<cat>/index.json),
# a local sample of JSONs (data/tier3_v6/<cat>/json/<id>.json), and, for any
# other paper, the JSON fetched on first click by SARANGA_T3_REMOTE, a command
# with {cat} and {id} placeholders that prints the JSON, e.g.
#   ssh orzuk@moriah-gw.cs.huji.ac.il cat /sci/.../parsed_100k_v6b/{cat}/json/{id}_rules.json
# The page is then built with the v2 viewer and cached.
T3_DIR = DATA_DIR / "tier3_v6"
T3_REMOTE = os.environ.get("SARANGA_T3_REMOTE", "")
T3_CACHE = CACHE_DIR / "tier3_v6"
MOUNTS = {"/silver_v6/": SILVER_DIR, "/t3cache/": T3_CACHE}


def find_json(paper_id: str, tier: str) -> Path | None:
    """Locate the JSON for a paper in the configured tier dir."""
    candidate = DATA_DIR / f"tier{tier}" / f"{paper_id}.json"
    if candidate.exists():
        return candidate
    if tier == "3":
        candidate = DATA_DIR / "tier3-sample" / f"{paper_id}.json"
        if candidate.exists():
            return candidate
    return None


def cache_path(paper_id: str, json_path: Path) -> Path:
    """Cache key includes both the JSON mtime AND the renderer-script mtime,
    so editing visualize_annotation.py (new colors, buttons, edge routing,
    etc.) invalidates every cached HTML automatically."""
    json_mtime = int(json_path.stat().st_mtime)
    script_mtime = int(VIZ_SCRIPT.stat().st_mtime) if VIZ_SCRIPT.exists() else 0
    return CACHE_DIR / f"{paper_id}_j{json_mtime}_s{script_mtime}.html.gz"


def render_html(paper_id: str, json_path: Path) -> bytes:
    """Run visualize_annotation.py on the JSON, return the produced HTML bytes."""
    # Run the renderer in a fresh per-call subdir so concurrent requests for
    # different papers don't trip over each other's temp files.
    run_dir = WORK_DIR / paper_id
    if run_dir.exists():
        shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    work_json = run_dir / f"{paper_id}.json"
    work_json.write_bytes(json_path.read_bytes())
    work_html = run_dir / f"{paper_id}.html"

    cmd = [PYTHON, str(VIZ_SCRIPT), str(work_json), "--html-only"]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=RENDER_TIMEOUT_SEC,
        cwd=str(VIZ_SCRIPT.parent),
    )

    if proc.returncode != 0 or not work_html.exists():
        msg = (
            f"visualize_annotation.py failed for {paper_id}\n"
            f"exit={proc.returncode}\n"
            f"stdout:\n{proc.stdout[-1500:]}\n"
            f"stderr:\n{proc.stderr[-1500:]}\n"
        )
        shutil.rmtree(run_dir, ignore_errors=True)
        raise RuntimeError(msg)

    html_bytes = work_html.read_bytes()
    shutil.rmtree(run_dir, ignore_errors=True)
    return html_bytes


def serve_render(handler: "PortalHandler", query: dict[str, list[str]]) -> None:
    import time

    paper_id = (query.get("id", [""])[0] or "").strip()
    tier = (query.get("tier", ["2"])[0] or "2").strip()
    nocache = (query.get("nocache", ["0"])[0] or "0").strip() in ("1", "true", "yes")

    if not paper_id:
        handler.send_error(400, "missing ?id= parameter")
        return

    json_path = find_json(paper_id, tier)
    if json_path is None:
        handler.send_error(
            404, f"JSON not found for {paper_id} in tier {tier}"
        )
        return

    cache = cache_path(paper_id, json_path)
    cache_status = "MISS"
    render_ms = 0
    if cache.exists() and not nocache:
        with gzip.open(cache, "rb") as f:
            html_bytes = f.read()
        cache_status = "HIT"
    else:
        if nocache and cache.exists():
            cache_status = "BYPASS"
        t0 = time.time()
        try:
            html_bytes = render_html(paper_id, json_path)
        except subprocess.TimeoutExpired:
            handler.send_error(504, f"render timed out after {RENDER_TIMEOUT_SEC}s")
            return
        except Exception as exc:
            handler.send_error(500, str(exc).splitlines()[0])
            return
        render_ms = int((time.time() - t0) * 1000)
        # Cache for next time
        with gzip.open(cache, "wb", compresslevel=6) as f:
            f.write(html_bytes)
        # Best-effort cleanup of stale cache entries for this paper
        for old in CACHE_DIR.glob(f"{paper_id}_*.html.gz"):
            if old != cache:
                old.unlink(missing_ok=True)

    # Inject a small banner at the top of the HTML so the cache status is
    # visible to the user (without polluting the headers-only path that
    # iframes hide). The banner is a fixed-position overlay in the corner.
    banner = (
        '<div style="position:fixed;top:6px;right:8px;z-index:9999;'
        'font:11px sans-serif;background:rgba(0,0,0,0.78);color:#fff;'
        'padding:3px 8px;border-radius:4px">'
        f'cache: <b>{cache_status}</b>'
        + (f' &middot; render: {render_ms} ms' if render_ms else '')
        + '</div>'
    )
    if isinstance(html_bytes, bytes):
        html_str = html_bytes.decode("utf-8", errors="replace")
    else:
        html_str = html_bytes
    inject_at = html_str.find("<body")
    if inject_at != -1:
        end_of_body_tag = html_str.find(">", inject_at)
        if end_of_body_tag != -1:
            html_str = (
                html_str[: end_of_body_tag + 1]
                + banner
                + html_str[end_of_body_tag + 1 :]
            )
    html_bytes = html_str.encode("utf-8")

    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(html_bytes)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Authomathics-Cache", cache_status)
    if render_ms:
        handler.send_header("X-Authomathics-Render-Ms", str(render_ms))
    handler.end_headers()
    handler.wfile.write(html_bytes)


def find_pair_in_manifest(pair_id: str) -> dict | None:
    if not MANIFEST_PATH.exists():
        return None
    try:
        m = json.loads(MANIFEST_PATH.read_text())
        for p in m.get("pairs", []):
            if p.get("pair_id") == pair_id:
                return p
    except Exception:
        return None
    return None


def find_paper_json(paper_dir: str, tier: int | str) -> Path | None:
    """Resolve a paper_dir like 'paper208' or '1204.0109v1_claude' to its JSON
    in the portal data dir."""
    for t in (str(tier), "1", "2"):
        cand = DATA_DIR / f"tier{t}" / f"{paper_dir}.json"
        if cand.exists():
            return cand
    return None


def alignment_cache_path(pair_id: str, key_mtimes: tuple[int, ...]) -> Path:
    keystr = "_".join(str(k) for k in key_mtimes)
    return CACHE_DIR / f"align_{pair_id}_{keystr}.html.gz"


def render_alignment_html(pair: dict, mode: str) -> bytes:
    """Run visualize_alignment.py on the pair and return wrapped HTML bytes
    containing the inlined SVG. The script writes a PNG by default; we ask
    for SVG by passing an output path with .svg extension (matplotlib infers
    the format from the suffix)."""
    pa = pair.get("paper_a") or {}
    pb = pair.get("paper_b") or {}
    a_path = find_paper_json(pa.get("paper_dir") or "", pa.get("tier") or 2)
    b_path = find_paper_json(pb.get("paper_dir") or "", pb.get("tier") or 2)
    align_file = pair.get("alignment_file")
    align_path = (DATA_DIR / "pairs" / align_file) if align_file else None
    if not (a_path and b_path and align_path and align_path.exists()):
        missing = []
        if not a_path: missing.append(f"paper_a JSON ({pa.get('paper_dir')!r})")
        if not b_path: missing.append(f"paper_b JSON ({pb.get('paper_dir')!r})")
        if not (align_path and align_path.exists()):
            missing.append(f"alignment JSON ({align_file!r})")
        raise FileNotFoundError("Missing inputs for alignment render: " + ", ".join(missing))

    run_dir = WORK_DIR / f"align_{pair['pair_id']}"
    if run_dir.exists():
        shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    out_svg = run_dir / "alignment.svg"

    cmd = [PYTHON, str(ALIGN_SCRIPT),
           str(a_path), str(b_path), str(align_path),
           str(out_svg), "--mode", mode]
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=RENDER_TIMEOUT_SEC, cwd=str(ALIGN_SCRIPT.parent),
    )
    if proc.returncode != 0 or not out_svg.exists():
        msg = (
            f"visualize_alignment.py failed for {pair['pair_id']}\n"
            f"exit={proc.returncode}\n"
            f"stdout:\n{proc.stdout[-1500:]}\n"
            f"stderr:\n{proc.stderr[-1500:]}\n"
        )
        shutil.rmtree(run_dir, ignore_errors=True)
        raise RuntimeError(msg)

    svg = out_svg.read_text(encoding="utf-8")

    # Mode S writes a sidecar JSON next to the SVG with per-cluster details
    # (paper-A/B node names + statements + types + explanation) so we can
    # render a click-through detail panel without re-loading the source
    # JSONs in the browser.
    sidecar_data = None
    if mode == "S":
        sidecar_path = out_svg.with_suffix(".shared.json")
        if sidecar_path.exists():
            try:
                sidecar_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
            except Exception:
                sidecar_data = None

    shutil.rmtree(run_dir, ignore_errors=True)

    title = pair.get("pair_id", "")
    rel = pair.get("relation_type", "")
    a_title = (pa.get("title") or pa.get("paper_dir") or "?")
    b_title = (pb.get("title") or pb.get("paper_dir") or "?")

    if mode == "S" and sidecar_data is not None:
        html = _wrap_mode_s_html(svg, sidecar_data, title, rel,
                                 a_title, b_title)
    else:
        html = (
            "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
            f"<title>Alignment: {title}</title>"
            "<style>body{font:13px/1.4 sans-serif;margin:0;padding:0;background:#fafafa}"
            "header{padding:8px 14px;background:#2c3e50;color:#fff;display:flex;"
            "gap:14px;align-items:baseline}"
            "header h1{margin:0;font-size:14px}"
            "header .rel{background:#fff;color:#2c3e50;padding:2px 8px;"
            "border-radius:4px;font-size:11px;font-weight:bold}"
            ".sub{font-size:11px;color:#aaa}"
            ".svg-wrap{padding:10px;overflow:auto}"
            ".svg-wrap svg{max-width:none;display:block;margin:auto}</style></head>"
            "<body>"
            f"<header><h1>{title}</h1>"
            f'<span class="rel">{rel}</span>'
            f'<span class="sub">A: {a_title} &middot; B: {b_title} &middot; mode {mode}</span>'
            "</header>"
            f'<div class="svg-wrap">{svg}</div>'
            "</body></html>"
        )
    return html.encode("utf-8")


def _wrap_mode_s_html(svg: str, sidecar: dict, title: str, rel: str,
                      a_title: str, b_title: str) -> str:
    """Wrap a Mode-S SVG with an interactive detail panel.

    Mirrors the #detail-panel.open scaffold from
    visualize_annotation.generate_interactive_html: clicking a shared
    cluster opens a 380px right-side panel populated with the full
    cluster details (paper-A/B node lists, statements, explanation),
    with KaTeX math typesetting via the locally-vendored katex bundle.
    """
    from html import escape as _esc
    # Inject a click handler + cursor on every shared_cluster_<n> rect.
    # matplotlib's SVG output puts the gid on a <g> wrapper; we need to
    # tag both the <g> and its child <path>/<rect> so clicks land.
    def _inject_click(m):
        gid = m.group(1)
        return (f'id="shared_cluster_{gid}" '
                f'onclick="showSharedDetail({gid})" '
                f'style="cursor:pointer"')
    svg = re.sub(r'id="shared_cluster_(\d+)"', _inject_click, svg)

    sidecar_json = json.dumps(sidecar, ensure_ascii=True)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Alignment (mode S): {_esc(title)}</title>
<link rel="stylesheet" href="vendor/katex/katex.min.css">
<script defer src="vendor/katex/katex.min.js"></script>
<script defer src="vendor/katex/contrib/auto-render.min.js"></script>
<script>
window.KATEX_CONFIG = {{
  delimiters: [
    {{left:'$$',right:'$$',display:true}},
    {{left:'$',right:'$',display:false}},
    {{left:'\\\\(',right:'\\\\)',display:false}},
    {{left:'\\\\[',right:'\\\\]',display:true}}
  ],
  throwOnError:false, errorColor:'#cc0000', strict:'ignore', trust:false,
  macros: {{
    '\\\\R':'\\\\mathbb{{R}}', '\\\\N':'\\\\mathbb{{N}}', '\\\\Z':'\\\\mathbb{{Z}}',
    '\\\\Q':'\\\\mathbb{{Q}}', '\\\\C':'\\\\mathbb{{C}}',
    '\\\\E':'\\\\mathbb{{E}}', '\\\\Var':'\\\\mathrm{{Var}}',
    '\\\\Cov':'\\\\mathrm{{Cov}}',
    '\\\\T':'\\\\top'
  }}
}};
function typesetMath(el) {{
  if (window.renderMathInElement) {{
    try {{ renderMathInElement(el || document.body, window.KATEX_CONFIG); }}
    catch(e) {{}}
  }}
}}
window.addEventListener('DOMContentLoaded', function(){{ typesetMath(document.body); }});
</script>
<style>
body {{ font:13px/1.4 'Segoe UI',Tahoma,sans-serif; margin:0; background:#fafafa; }}
header {{ padding:8px 14px; background:#2c3e50; color:#fff;
         display:flex; gap:14px; align-items:baseline; }}
header h1 {{ margin:0; font-size:14px; }}
header .rel {{ background:#fff; color:#2c3e50; padding:2px 8px;
              border-radius:4px; font-size:11px; font-weight:bold; }}
header .sub {{ font-size:11px; color:#aaa; }}
#main {{ display:flex; height:calc(100vh - 38px); }}
#svg-wrap {{ flex:1; overflow:auto; padding:10px; background:#fff; }}
#svg-wrap svg {{ max-width:none; display:block; margin:auto; }}
#detail-panel {{ width:0; overflow-y:auto; background:#fff;
                 border-left:1px solid #ddd; transition:width 0.3s; }}
#detail-panel.open {{ width:380px; padding:16px; }}
#detail-panel h3 {{ margin:0 0 8px; font-size:16px; color:#2c3e50; }}
#detail-panel h4 {{ margin:14px 0 6px; color:#444; font-size:12px;
                    text-transform:uppercase; letter-spacing:0.04em; }}
.det-meta {{ font-size:12px; color:#666; margin-bottom:8px; }}
.det-pill {{ display:inline-block; padding:2px 8px; border-radius:3px;
             font-size:11px; font-weight:bold; margin-right:6px; }}
.det-pill.exact {{ background:#D5F5E3; color:#1E8449; }}
.det-pill.analogous {{ background:#FCF3CF; color:#9A7D0A; }}
.det-side-a {{ background:#FADBD8; border-left:3px solid #7B241C;
              padding:6px 10px; margin:4px 0; border-radius:0 3px 3px 0; }}
.det-side-b {{ background:#D6EAF8; border-left:3px solid #1A5276;
              padding:6px 10px; margin:4px 0; border-radius:0 3px 3px 0; }}
.det-node-id {{ font-family:monospace; font-size:11px; color:#555; }}
.det-node-name {{ font-weight:bold; font-size:13px; color:#222; }}
.det-node-stmt {{ font-size:12px; color:#333; margin-top:3px; }}
.det-explanation {{ font-size:12px; color:#333; font-style:italic;
                    background:#F4ECF7; border-left:3px solid #7D3C98;
                    padding:6px 10px; border-radius:0 3px 3px 0; }}
[id^="shared_cluster_"]:hover {{ filter:brightness(0.92); }}
</style>
</head><body>
<header>
  <h1>{_esc(title)}</h1>
  <span class="rel">{_esc(rel)}</span>
  <span class="sub">A: {_esc(a_title)} &middot; B: {_esc(b_title)} &middot; mode S (shared only)</span>
</header>
<div id="main">
  <div id="svg-wrap">{svg}</div>
  <div id="detail-panel"></div>
</div>
<script>
var SHARED_DATA = {sidecar_json};
var CLUSTERS_BY_INDEX = {{}};
SHARED_DATA.clusters.forEach(function(c){{ CLUSTERS_BY_INDEX[c.cluster_index] = c; }});

function _esc(t) {{
  return String(t==null?'':t)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

var _lastClusterIdx = null;
function showSharedDetail(idx) {{
  var panel = document.getElementById('detail-panel');
  if (_lastClusterIdx === idx && panel.className === 'open') {{
    panel.className = ''; panel.innerHTML = ''; _lastClusterIdx = null; return;
  }}
  _lastClusterIdx = idx;
  var c = CLUSTERS_BY_INDEX[idx];
  if (!c) return;
  var h = '<h3>' + _esc(c.pair_id) + '</h3>';
  h += '<div class="det-meta">';
  h += '<span class="det-pill ' + _esc(c.match_type) + '">' + _esc(c.match_type) + '</span>';
  if (c.confidence) h += '<span style="font-size:11px;color:#666">confidence: ' + _esc(c.confidence) + '</span>';
  h += '</div>';
  h += '<h4>' + _esc(SHARED_DATA.paper_a_name) + ' &mdash; ' + c.paper_a_nodes.length + ' node' +
       (c.paper_a_nodes.length !== 1 ? 's' : '') + '</h4>';
  c.paper_a_nodes.forEach(function(n) {{
    h += '<div class="det-side-a">';
    h += '<div><span class="det-node-id">' + _esc(n.id) + '</span> ';
    h += '<span style="font-size:10px;color:#888">[' + _esc(n.type) + ']</span></div>';
    if (n.name) h += '<div class="det-node-name">' + _esc(n.name) + '</div>';
    if (n.statement) h += '<div class="det-node-stmt">' + _esc(n.statement) + '</div>';
    h += '</div>';
  }});
  h += '<h4>' + _esc(SHARED_DATA.paper_b_name) + ' &mdash; ' + c.paper_b_nodes.length + ' node' +
       (c.paper_b_nodes.length !== 1 ? 's' : '') + '</h4>';
  c.paper_b_nodes.forEach(function(n) {{
    h += '<div class="det-side-b">';
    h += '<div><span class="det-node-id">' + _esc(n.id) + '</span> ';
    h += '<span style="font-size:10px;color:#888">[' + _esc(n.type) + ']</span></div>';
    if (n.name) h += '<div class="det-node-name">' + _esc(n.name) + '</div>';
    if (n.statement) h += '<div class="det-node-stmt">' + _esc(n.statement) + '</div>';
    h += '</div>';
  }});
  if (c.explanation) {{
    h += '<h4>Explanation</h4>';
    h += '<div class="det-explanation">' + _esc(c.explanation) + '</div>';
  }}
  panel.innerHTML = h;
  panel.className = 'open';
  typesetMath(panel);
}}
</script>
</body></html>"""


def serve_render_alignment(handler: "PortalHandler",
                            query: dict[str, list[str]]) -> None:
    import time
    pair_id = (query.get("id", [""])[0] or "").strip()
    mode = (query.get("mode", ["S"])[0] or "S").strip().upper()
    nocache = (query.get("nocache", ["0"])[0] or "0").strip() in ("1", "true", "yes")
    if mode not in ("B", "C", "S"):
        mode = "S"
    if not pair_id:
        handler.send_error(400, "missing ?id= parameter")
        return

    pair = find_pair_in_manifest(pair_id)
    if pair is None:
        handler.send_error(404, f"pair {pair_id!r} not in manifest")
        return
    if not pair.get("alignment_available"):
        handler.send_error(404, f"pair {pair_id!r} has no alignment JSON yet")
        return

    pa = pair.get("paper_a") or {}
    pb = pair.get("paper_b") or {}
    a_path = find_paper_json(pa.get("paper_dir") or "", pa.get("tier") or 2)
    b_path = find_paper_json(pb.get("paper_dir") or "", pb.get("tier") or 2)
    align_file = pair.get("alignment_file")
    align_path = (DATA_DIR / "pairs" / align_file) if align_file else None
    if not (a_path and b_path and align_path and align_path.exists()):
        handler.send_error(503, "one or more inputs missing on disk; "
                                "rebuild manifest after extracting both papers")
        return

    key = (
        int(a_path.stat().st_mtime), int(b_path.stat().st_mtime),
        int(align_path.stat().st_mtime),
        int(ALIGN_SCRIPT.stat().st_mtime) if ALIGN_SCRIPT.exists() else 0,
        ord(mode),
    )
    cache = alignment_cache_path(pair_id, key)
    cache_status = "MISS"
    render_ms = 0
    if cache.exists() and not nocache:
        with gzip.open(cache, "rb") as f:
            html_bytes = f.read()
        cache_status = "HIT"
    else:
        if nocache and cache.exists():
            cache_status = "BYPASS"
        t0 = time.time()
        try:
            html_bytes = render_alignment_html(pair, mode)
        except subprocess.TimeoutExpired:
            handler.send_error(504, f"alignment render timed out after {RENDER_TIMEOUT_SEC}s")
            return
        except Exception as exc:
            handler.send_error(500, str(exc).splitlines()[0])
            return
        render_ms = int((time.time() - t0) * 1000)
        with gzip.open(cache, "wb", compresslevel=6) as f:
            f.write(html_bytes)
        for old in CACHE_DIR.glob(f"align_{pair_id}_*.html.gz"):
            if old != cache:
                old.unlink(missing_ok=True)

    # Inject the same cache-status banner used by /render so user can tell
    # whether the SVG was just computed or served from cache.
    banner = (
        '<div style="position:fixed;top:6px;right:8px;z-index:9999;'
        'font:11px sans-serif;background:rgba(0,0,0,0.78);color:#fff;'
        'padding:3px 8px;border-radius:4px">'
        f'cache: <b>{cache_status}</b>'
        + (f' &middot; render: {render_ms} ms' if render_ms else '')
        + '</div>'
    )
    html_str = html_bytes.decode("utf-8", errors="replace")
    inject = html_str.find("<body")
    if inject != -1:
        end = html_str.find(">", inject)
        if end != -1:
            html_str = html_str[: end + 1] + banner + html_str[end + 1:]
    html_bytes = html_str.encode("utf-8")

    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(html_bytes)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Authomathics-Cache", cache_status)
    if render_ms:
        handler.send_header("X-Authomathics-Render-Ms", str(render_ms))
    handler.end_headers()
    handler.wfile.write(html_bytes)


_SAFE = re.compile(r"^[A-Za-z0-9._\-]+$")


def t3_json(cat: str, pid: str) -> Path | None:
    """The paper's JSON: the local sample, the cache, or fetched by T3_REMOTE."""
    if not (_SAFE.match(cat) and _SAFE.match(pid)):
        return None
    for p in (T3_DIR / cat / "json" / f"{pid}.json", T3_CACHE / cat / f"{pid}.json"):
        if p.is_file():
            return p
    if not T3_REMOTE:
        return None
    dst = T3_CACHE / cat / f"{pid}.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = T3_REMOTE.format(cat=cat, id=pid)
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        return None
    if out.returncode != 0 or not out.stdout.strip().startswith(b"{"):
        sys.stderr.write(f"[t3] fetch failed for {cat}/{pid}: {out.stderr[-300:]!r}\n")
        return None
    dst.write_bytes(out.stdout)
    return dst


def serve_t3_json(handler, query) -> None:
    cat, pid = (query.get("cat") or [""])[0], (query.get("id") or [""])[0]
    p = t3_json(cat, pid)
    if not p:
        handler.send_error(404, f"no JSON for {cat}/{pid} (set SARANGA_T3_REMOTE to fetch it)")
        return
    body = p.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def serve_render3(handler, query) -> None:
    """Build (once) the v2 viewer page of a 100K paper and redirect to it."""
    cat, pid = (query.get("cat") or [""])[0], (query.get("id") or [""])[0]
    src = t3_json(cat, pid)
    if not src:
        handler.send_error(404, f"no JSON for {cat}/{pid} (set SARANGA_T3_REMOTE to fetch it)")
        return
    out_dir = T3_CACHE / cat
    page = out_dir / f"{pid}_new.html"
    if not page.is_file() or page.stat().st_mtime < src.stat().st_mtime:
        out_dir.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([PYTHON, str(GRAPH_BUILD), str(src), "-o", str(out_dir)],
                           capture_output=True, text=True, timeout=RENDER_TIMEOUT_SEC)
        if r.returncode != 0 or not page.is_file():
            handler.send_error(500, f"build failed: {r.stderr[-500:]}")
            return
    handler.send_response(302)
    handler.send_header("Location", f"/t3cache/{cat}/{pid}_new.html")
    handler.end_headers()


class PortalHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PORTAL_DIR), **kwargs)

    def translate_path(self, path):
        clean = urllib.parse.urlparse(path).path
        for prefix, root in MOUNTS.items():
            if clean.startswith(prefix):
                rel = urllib.parse.unquote(clean[len(prefix):])
                p = (Path(root) / rel).resolve()
                if str(p).startswith(str(Path(root).resolve())):
                    return str(p)
        return super().translate_path(path)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/render3", "/t3json"):
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            (serve_render3 if parsed.path == "/render3" else serve_t3_json)(self, query)
            return
        if parsed.path == "/render":
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            serve_render(self, query)
            return
        if parsed.path == "/render_alignment":
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            serve_render_alignment(self, query)
            return
        super().do_GET()

    def log_message(self, fmt, *args):
        # Slightly tidier than the default
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")


def main():
    port = int(os.environ.get("PORT", "8000"))
    bind = os.environ.get("HOST", "0.0.0.0")
    print(f"Authomathics portal serving from {PORTAL_DIR}")
    print(f"  data dir:    {DATA_DIR}")
    print(f"  cache dir:   {CACHE_DIR}")
    print(f"  viz script:  {VIZ_SCRIPT}  (exists: {VIZ_SCRIPT.exists()})")
    print(f"  listening on http://{bind}:{port}")
    print(f"  open http://localhost:{port}/")
    HTTPServer((bind, port), PortalHandler).serve_forever()


if __name__ == "__main__":
    main()
