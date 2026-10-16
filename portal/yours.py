"""'Your paper': build a graph from any arXiv paper or uploaded LaTeX, on demand.

The rule-based extractor (LaTeX parser + distilled sentence rules) needs no model,
so a paper is parsed in about a second and its v2 viewer page built in a few more.
Inputs:
  - an arXiv id or link: the LaTeX source is downloaded from arxiv.org/e-print;
  - an upload: a .tex file, or a .zip / .tar.gz / .tgz / .tar of a LaTeX project.
Each request gets a random id; its page is served at /yours_pages/<rid>/ and the
work directory is deleted after KEEP_HOURS. LaTeX is only read, never compiled.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RULES_DIR = REPO / "extractors" / "rules" / "silver_v6__sentence_rules_haiku__2026-10"
GRAPH_BUILD = REPO / "src" / "graph_view" / "build.py"
sys.path[:0] = [str(REPO / "src" / "LLMVersion"), str(REPO / "src")]
import latex_facts                                  # noqa: E402
from math_paper_parser import parse_to_unified      # noqa: E402
KEEP_HOURS = 24
MAX_UPLOAD = 50 * 2**20          # bytes accepted from a request
MAX_UNPACKED = 200 * 2**20       # bytes written when unpacking an archive
MAX_FILES = 3000
BUILD_TIMEOUT = 180
_ARXIV_ID = re.compile(r"(\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)")


class YoursError(Exception):
    """A problem to report to the user (bad input, no LaTeX found, ...)."""


def parse_arxiv_id(text: str) -> str:
    m = _ARXIV_ID.search(text or "")
    if not m:
        raise YoursError("That does not look like an arXiv id or link (e.g. 2401.00367).")
    return m.group(1)


def new_workdir(root: Path) -> tuple[str, Path]:
    cleanup(root)
    rid = secrets.token_hex(8)
    d = root / rid
    (d / "source").mkdir(parents=True)
    return rid, d


def cleanup(root: Path) -> None:
    """Delete work directories older than KEEP_HOURS."""
    if not root.exists():
        return
    cutoff = time.time() - KEEP_HOURS * 3600
    for d in root.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def _safe_target(base: Path, name: str) -> Path | None:
    p = (base / name).resolve()
    return p if str(p).startswith(str(base.resolve()) + os.sep) else None


def _unpack(data: bytes, name: str, dest: Path) -> None:
    """Write a .tex, or unpack an archive, into dest, refusing paths outside it."""
    lname = name.lower()
    total, count = 0, 0

    def put(member: str, content: bytes):
        nonlocal total, count
        total += len(content)
        count += 1
        if total > MAX_UNPACKED or count > MAX_FILES:
            raise YoursError("The archive is too large.")
        t = _safe_target(dest, member)
        if t is None:
            return                                  # path escaping the folder: skipped
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_bytes(content)

    if lname.endswith(".zip") or data[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for i in z.infolist():
                if not i.is_dir():
                    put(i.filename, z.read(i))
        return
    raw = data
    if data[:2] == b"\x1f\x8b":                     # gzip: a tar, or a single .tex (arXiv)
        raw = gzip.decompress(data)
    try:
        with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
            for m in tf.getmembers():
                if m.isfile():
                    f = tf.extractfile(m)
                    if f:
                        put(m.name, f.read())
        return
    except tarfile.TarError:
        pass
    put("main.tex", raw)                            # a single LaTeX file


def find_main_tex(src: Path) -> Path:
    """The paper's main .tex (latex_facts.find_main_tex); a YoursError if there is none."""
    if (main := latex_facts.find_main_tex(src)) is None:
        raise YoursError("No .tex file found. Upload the LaTeX source (PDF is not supported).")
    return main


def fetch_arxiv(aid: str, dest: Path) -> str:
    """Download arXiv's LaTeX source into dest; return the paper's title (best effort)."""
    req = urllib.request.Request(f"https://arxiv.org/e-print/{aid}",
                                 headers={"User-Agent": "saranga-portal"})
    try:
        data = urllib.request.urlopen(req, timeout=60).read(MAX_UPLOAD + 1)
    except Exception as e:                          # noqa: BLE001
        raise YoursError(f"Could not download {aid} from arXiv ({e}).")
    if len(data) > MAX_UPLOAD:
        raise YoursError("The arXiv source is too large.")
    if data[:5] == b"%PDF-":
        raise YoursError(f"arXiv has only a PDF for {aid}, no LaTeX source.")
    _unpack(data, f"{aid}.tar.gz", dest)
    try:
        api = urllib.request.urlopen(f"http://export.arxiv.org/api/query?id_list={aid}", timeout=20).read().decode()
        t = re.findall(r"<title>(.*?)</title>", api, re.S)
        return re.sub(r"\s+", " ", t[1]).strip() if len(t) > 1 else ""
    except Exception:                               # noqa: BLE001
        return ""


def _title_from_tex(main: Path) -> str:
    s = main.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"\\title(?:\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}", s)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def build(work: Path, paper_id: str, title: str = "") -> dict:
    """Parse the source with the rules and build the viewer page. Returns a summary."""
    main = find_main_tex(work / "source")
    title = title or _title_from_tex(main) or paper_id
    d = parse_to_unified(main, paper_id, str(RULES_DIR))
    md = d.setdefault("metadata", {})
    md.update({"title": title, "paper_id": paper_id, "extractor": "rules (parser + distilled sentence rules)"})
    out_json = work / f"{paper_id}.json"
    out_json.write_text(json.dumps(d), encoding="utf-8")
    r = subprocess.run([sys.executable, str(GRAPH_BUILD), str(out_json), "-o", str(work)],
                       capture_output=True, text=True, timeout=BUILD_TIMEOUT)
    page = work / f"{paper_id}_new.html"
    if r.returncode != 0 or not page.is_file():
        raise YoursError("Building the page failed: " + (r.stderr or "")[-300:])
    return {"title": title, "n_nodes": len(d.get("nodes", [])), "n_edges": len(d.get("edges", [])),
            "page": page.name, "json": out_json.name}
