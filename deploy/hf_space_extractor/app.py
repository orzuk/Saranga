"""SARANGA 'Your paper' service: the public, stand-alone version of the portal page.

Serves the upload page at /, builds a graph from an arXiv id (GET /yours/arxiv?id=)
or an uploaded LaTeX file/archive (POST /yours/upload?name=), and serves the
built pages at /yours_pages/<rid>/. Rule-based extractor only (no model, no key).
Runs on a Hugging Face Docker Space (port 7860), or locally:  python3 app.py
"""
import json
import os
import re
import sys
import time
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "portal"))
os.environ.setdefault("SARANGA_LIBS_CDN", "1")
import yours                                        # noqa: E402

WORK = Path(os.environ.get("SARANGA_WORK", "/tmp/saranga_yours"))
WORK.mkdir(parents=True, exist_ok=True)
PAGE = HERE / "portal" / "papers_yours.html"


def reply(h, code, obj):
    body = json.dumps(obj).encode()
    h.send_response(code)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def handle(h, query, upload):
    t0 = time.time()
    try:
        rid, work = yours.new_workdir(WORK)
        if upload:
            n = int(h.headers.get("Content-Length") or 0)
            if n <= 0 or n > yours.MAX_UPLOAD:
                raise yours.YoursError("Empty or too large upload (limit 50 MB).")
            name = (query.get("name") or ["paper.tex"])[0]
            yours._unpack(h.rfile.read(n), name, work / "source")
            pid = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name.split(".")[0]) or "paper"
            title = ""
        else:
            aid = yours.parse_arxiv_id((query.get("id") or [""])[0])
            title = yours.fetch_arxiv(aid, work / "source")
            pid = aid.replace("/", "_")
        info = yours.build(work, pid, title)
        info.update({"url": f"yours_pages/{rid}/{info['page']}", "json_url": f"yours_pages/{rid}/{info['json']}",
                     "seconds": round(time.time() - t0, 1)})
        reply(h, 200, info)
    except yours.YoursError as e:
        reply(h, 400, {"error": str(e)})
    except Exception as e:                          # noqa: BLE001
        sys.stderr.write(f"[yours] {e!r}\n")
        reply(h, 500, {"error": f"Extraction failed: {type(e).__name__}"})


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        clean = urllib.parse.urlparse(path).path
        if clean.startswith("/yours_pages/"):
            p = (WORK / urllib.parse.unquote(clean[len("/yours_pages/"):])).resolve()
            if str(p).startswith(str(WORK.resolve())):
                return str(p)
        return str(HERE / "portal" / "_none_")      # nothing else is served from disk

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html", "/papers_yours.html"):
            body = PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path == "/yours/arxiv":
            handle(self, urllib.parse.parse_qs(u.query), upload=False)
            return
        super().do_GET()

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/yours/upload":
            handle(self, urllib.parse.parse_qs(u.query), upload=True)
            return
        self.send_error(404)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "7860"))
    print(f"SARANGA 'Your paper' on http://0.0.0.0:{port}/")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
