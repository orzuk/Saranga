#!/usr/bin/env python3
"""
L0 Reference-book extractor for survey/encyclopedia volumes:

  b245  Princeton Companion to Mathematics (PCM)       -- Gowers et al. 2008
  b246  Princeton Companion to Applied Mathematics     -- Higham (ed.) 2015
  b247  Encyclopedia of Mathematics                    -- Tanton 2005

These L0 books differ fundamentally from textbook sources: they are survey
articles (PCM/PCAM) or alphabetical encyclopedia entries (Tanton), not
theorem-proof mathematics. We therefore use a DIFFERENT schema from the
textbook pipeline:

Nodes:
  CONCEPT_ARTICLE   -- one per article/entry
  NAMED_RESULT      -- theorem/formula/conjecture with a famous name, mentioned
                       in an article (no proof needed; links later to L1/L2)
  HISTORICAL_NOTE   -- only for prominent biographical/chronological sections

Edges:
  cross_reference   -- explicit "see III.12" or "see also X"
  contains_named_result  -- article -> named result
  mentions          -- soft bolded-term link to another article in the same book

Usage:
  python extract_reference.py b247
  python extract_reference.py b245
  python extract_reference.py b246
  python extract_reference.py assemble b247   # just re-assemble book.json

LLM backend: uses the `claude` CLI via subprocess with `-p --model sonnet`.
ANTHROPIC_API_KEY is honored if set (the CLI picks it up automatically).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

PDF_DIR = Path("/mnt/c/Code/Github/Authomathics/textbooks/pdf")
OUT_ROOT = Path("/mnt/c/Code/Github/Authomathics/textbooks/extracted")

BOOKS = {
    "b247": {
        "slug": "b247_tanton",
        "pdf": "b247_tanton_encyclopedia_of_mathematics.pdf",
        "title": "Encyclopedia of Mathematics",
        "authors": ["James Tanton"],
        "year": 2005,
        "mode": "alphabet",         # A-Z letter buckets
        "num_pages_hint": 564,
    },
    "b245": {
        "slug": "b245_gowers_pcm",
        "pdf": "b245_gowers_princeton_companion_math.pdf",
        "title": "The Princeton Companion to Mathematics",
        "authors": ["Timothy Gowers (ed.)", "June Barrow-Green", "Imre Leader"],
        "year": 2008,
        "mode": "pcm",              # article-based (I.1, II.1, III.1, ...)
        "num_pages_hint": 1034,
    },
    "b246": {
        "slug": "b246_higham_pcam",
        "pdf": "b246_higham_princeton_companion_applied_math.pdf",
        "title": "The Princeton Companion to Applied Mathematics",
        "authors": ["Nicholas J. Higham (ed.)"],
        "year": 2015,
        "mode": "pcm",
        "num_pages_hint": 1016,
    },
}

# ---------------------------------------------------------------------------
# L0 extraction prompt
# ---------------------------------------------------------------------------

L0_PROMPT_TEMPLATE = """You are extracting a structured knowledge graph from a
reference-book chunk in the style of the Princeton Companion to Mathematics
or the Encyclopedia of Mathematics.

The input is raw PDF-extracted text for {chunk_desc}. Layout artifacts
(column breaks, hyphenations, page numbers) may be present -- ignore them.

Extract the following nodes and edges:

NODES
  - CONCEPT_ARTICLE -- one per article / encyclopedia entry.
      Fields: id, type="CONCEPT_ARTICLE", name, aliases (list),
              summary (1-2 sentences, generated from opening prose),
              domain_tags (short list like ["algebra","number_theory"]),
              page_start, page_end, author (string or null), layer="L0".
      The id must be unique within this chunk; use the form
      "{id_prefix}_art_<slug>" where <slug> is the article title
      lowercased with non-alphanumerics replaced by underscores.
  - NAMED_RESULT -- ONLY for theorems / formulas / conjectures that have a
      well-known proper name (e.g. "Cauchy-Schwarz inequality",
      "Riemann hypothesis", "Fundamental Theorem of Algebra",
      "Navier-Stokes equations"). Skip unnamed intermediate claims and
      every-noun-phrase inflation.
      Fields: id, type="NAMED_RESULT", name, statement (book's wording,
              may use $...$ math), parent_article_id, page.
  - HISTORICAL_NOTE -- ONLY for prominent biographical / chronological
      sections (explicit "History" heading, or a named historical essay).
      Do NOT emit for inline "Euler proved..." mentions.
      Fields: id, type="HISTORICAL_NOTE", name, summary, parent_article_id,
              page.

EDGES
  - cross_reference -- article A -> article B when A explicitly says
      "see Article X.Y", "see also [BOLDED_TITLE]", "[see III.12]", or an
      encyclopedia-style "See also COMPACTNESS". These are the backbone.
  - contains_named_result -- article A -> NAMED_RESULT R defined in A.
  - mentions -- softer: article A -> article B when a bolded (or
      small-caps) term inside A is itself another article title in this
      book. Do NOT link every noun phrase. If unsure, skip.

CROSS-REFERENCE TARGET ids:
  If the cross-reference points to an article inside this same chunk, use
  its id as extracted. If it points to an article outside this chunk,
  write the target as "{id_prefix}_art_<slug>" using the same slug rule
  as above. A downstream assembly step will resolve dangling targets.

CRITICAL RULES
  - Output STRICT JSON only (no prose, no code fences, no comments).
  - Math MUST be rendered as $...$ inline LaTeX. Do not leave plain-text
    math. Use standard LaTeX commands (\\sqrt, \\int, \\sum, \\mathbb{{R}}).
  - Do NOT extract proofs, examples, exercises, or intermediate equations.
  - Do NOT build within-article theorem DAGs.
  - If the text chunk is clearly boilerplate (copyright, index, TOC
    continuation, blank) return: {{"nodes": [], "edges": []}}.
  - If an article is so short (1-3 lines) that only "See FOO" remains,
    still emit a CONCEPT_ARTICLE with summary="(cross-reference stub)"
    and a cross_reference edge to the target.

Output schema exactly:
{{"nodes":[...], "edges":[...]}}

CHUNK TEXT ({page_start}-{page_end}):
----8<----
{text}
----8<----
"""

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def atomic_write_json(path, data):
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(path))


def slugify(name):
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name.lower()).strip("_")
    return s or "unnamed"


def pdftotext_range(pdf_path, first_page, last_page, layout=True, timeout=120):
    """Return text of [first_page, last_page] (inclusive, 1-based)."""
    args = ["pdftotext"]
    if layout:
        args.append("-layout")
    args += ["-f", str(first_page), "-l", str(last_page), str(pdf_path), "-"]
    try:
        out = subprocess.check_output(args, timeout=timeout, stderr=subprocess.DEVNULL)
        return out.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return ""
    except subprocess.CalledProcessError:
        return ""


def call_claude(prompt, model="sonnet", timeout=600):
    """Invoke the `claude` CLI in headless mode. Returns model text output."""
    # Use --print for non-interactive headless mode. --model sonnet picks the
    # default Sonnet alias (which the local CLI resolves).
    args = ["claude", "-p", "--model", model, "--output-format", "text", "--permission-mode", "bypassPermissions"]
    try:
        proc = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, "timeout"
    if proc.returncode != 0:
        return None, proc.stderr.strip()[:500] or f"exit {proc.returncode}"
    return proc.stdout, None


def parse_llm_json(text):
    """Tolerant JSON extraction from LLM output."""
    if not text:
        return None
    t = text.strip()
    # strip possible code fences
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    # fast path
    try:
        return json.loads(t)
    except Exception:
        pass
    # find first '{' and try progressively shorter suffixes
    start = t.find("{")
    if start < 0:
        return None
    end = t.rfind("}")
    if end <= start:
        return None
    candidate = t[start:end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Mode: Tanton encyclopedia (alphabet bucket)
# ---------------------------------------------------------------------------

# Letter buckets for Tanton -- discovered by scanning for "LETTER" headers or
# the first entry of each letter. Tanton's body spans about pages 13-538.
# We discover boundaries empirically on first run by scanning pdftotext of the
# full body for "^<lowercase word>$" headwords. A pragmatic approach: split the
# body into ~28-page chunks and let the LLM figure out which letter(s) each
# chunk straddles. That's both simpler and resilient.

TANTON_BODY_START = 13       # first entry begins "absolute convergence"
TANTON_BODY_END = 538        # last pages before appendices
TANTON_CHUNK_PAGES = 12      # pages per LLM call (each ~70k chars)


def plan_tanton_chunks(pdf_path):
    chunks = []
    p = TANTON_BODY_START
    idx = 0
    while p <= TANTON_BODY_END:
        end = min(p + TANTON_CHUNK_PAGES - 1, TANTON_BODY_END)
        idx += 1
        chunks.append({
            "chunk_id": f"chunk_{idx:03d}",
            "page_start": p,
            "page_end": end,
        })
        p = end + 1
    return chunks


# ---------------------------------------------------------------------------
# Mode: PCM / PCAM (article-based)
# ---------------------------------------------------------------------------

# We parse the TOC pages (first ~15 PDF pages of the file) to extract articles
# with labels like "III.14 Designs  172".
# TOC entries are formatted as:   I.1     Title ..... 1
# or two-column:                   III.23   Title         193    IV.5   Other   372

# Match ONE TOC entry in a line (can match multiple per line due to columns).
# Example spans:
#   "I.1      What Is Mathematics About?                       1"
#   "III.15   Determinants                                174"
# The title may contain en-dashes, ligatures, etc. We terminate the title at
# ≥2 spaces before the trailing integer page.
TOC_ENTRY_PAT = re.compile(
    r"(?P<part>(?:VIII|VII|VI|IV|V|III|II|I))"
    r"\.(?P<num>\d+)\.?"
    r"\s+"
    r"(?P<title>[^\s](?:.*?))"
    r"\s{2,}(?P<page>\d{1,4})(?=\s|$)"
)


def parse_toc(pdf_path):
    """Return a list of article entries from the front-matter TOC."""
    # Grab first 15 PDF pages (TOC is on pages 6-9 for PCM/PCAM).
    text = pdftotext_range(pdf_path, 1, 15, layout=True)
    raw_entries = []
    for line in text.splitlines():
        # Skip if no digit at all (optimization)
        if not any(c.isdigit() for c in line):
            continue
        for m in TOC_ENTRY_PAT.finditer(line):
            part = m.group("part")
            num = int(m.group("num"))
            title = m.group("title").strip()
            # strip dot leaders
            title = re.sub(r"[\.\s]{3,}$", "", title).strip()
            page = int(m.group("page"))
            # Basic sanity: title should contain at least one letter
            if not re.search(r"[A-Za-z]", title):
                continue
            # Reject entries where page > 1200 (likely false positive)
            if page <= 0 or page > 1200:
                continue
            raw_entries.append({
                "article_id": f"{part}.{num}",
                "part": part,
                "num": num,
                "title": title,
                "page_start": page,
            })
    # Dedup (part, num): keep the one with a sensible title (longer wins).
    seen = {}
    for e in raw_entries:
        key = (e["part"], e["num"])
        if key not in seen or len(e["title"]) > len(seen[key]["title"]):
            seen[key] = e
    entries = list(seen.values())
    part_order = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}
    entries.sort(key=lambda e: (part_order.get(e["part"], 99), e["num"]))
    # Strip trailing right-column bleed from wrapped titles. Example:
    # "The Prime Number Theorem and the                      VI.34   János Bolyai"
    # We cut at any occurrence of another part.num token with ≥4 preceding spaces.
    bleed_pat = re.compile(r"\s{4,}(?:VIII|VII|VI|IV|V|III|II|I)\.\d+\b")
    for e in entries:
        m = bleed_pat.search(e["title"])
        if m:
            e["title"] = e["title"][:m.start()].rstrip()
    # Pad page_end = next article's page_start - 1 (capped at 30 pages).
    MAX_ARTICLE_PAGES = 30
    for i, e in enumerate(entries):
        if i + 1 < len(entries):
            raw_end = entries[i + 1]["page_start"] - 1
        else:
            raw_end = e["page_start"] + 20
        e["page_end"] = max(e["page_start"], min(raw_end, e["page_start"] + MAX_ARTICLE_PAGES - 1))
    return entries


def enrich_toc_pages(entries, pdf_path, num_pages):
    """Front-matter vs body page offset: PCM/PCAM TOC lists *body* page numbers
    but the PDF physical page is offset (~16 pages of front matter in PCM).
    We detect the offset by finding the FIRST body article heading in the
    PDF text.
    """
    if not entries:
        return entries, 0
    # Search first 50 PDF pages for first "I.1  Title" header in the body.
    # PCM first article starts on PDF page ~20; just scan generously.
    text = pdftotext_range(pdf_path, 1, 60, layout=True)
    # Heading pattern: "I.1" possibly followed by title on same line
    # We look for a line starting with first article's tag.
    first = entries[0]
    pat = re.compile(rf"(?m)^\s*{re.escape(first['part'])}\.{first['num']}\b")
    # pdftotext emits a FORM FEED \x0c between pages; use that to find PDF page.
    pdf_pages = text.split("\x0c")
    offset = 0
    for pidx, ptext in enumerate(pdf_pages, start=1):
        if pat.search(ptext):
            # If the header appears on PDF page `pidx` but TOC says body page
            # `first['page_start']`, offset = pidx - first['page_start']
            offset = pidx - first["page_start"]
            break
    # Apply offset (clamp >=1)
    for e in entries:
        e["pdf_page_start"] = max(1, e["page_start"] + offset)
        e["pdf_page_end"] = max(e["pdf_page_start"], e["page_end"] + offset)
        # Hard cap at num_pages
        e["pdf_page_end"] = min(e["pdf_page_end"], num_pages)
        e["pdf_page_start"] = min(e["pdf_page_start"], num_pages)
    return entries, offset


def get_pdf_page_count(pdf_path):
    try:
        out = subprocess.check_output(["pdfinfo", str(pdf_path)], text=True,
                                      stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":", 1)[1].strip())
    except Exception:
        pass
    # fallback: pdftotext -last huge number + measure form feeds
    text = pdftotext_range(pdf_path, 1, 9999, layout=False, timeout=180)
    return max(1, text.count("\x0c"))


# ---------------------------------------------------------------------------
# Per-chunk extraction driver
# ---------------------------------------------------------------------------

MAX_CHARS_PER_CHUNK = 120_000   # safety cap; Sonnet handles this easily


def extract_chunk(pdf_path, chunk_meta, id_prefix, out_dir, dry_run=False):
    """Run the LLM on one chunk, save JSON, return (status, node_count, edge_count)."""
    cid = chunk_meta["chunk_id"]
    out_file = out_dir / f"{cid}.json"
    if out_file.exists():
        try:
            data = json.loads(out_file.read_text(encoding="utf-8"))
            return "cached", len(data.get("nodes", [])), len(data.get("edges", []))
        except Exception:
            pass  # re-extract
    p_start = chunk_meta.get("pdf_page_start", chunk_meta["page_start"])
    p_end = chunk_meta.get("pdf_page_end", chunk_meta["page_end"])
    text = pdftotext_range(pdf_path, p_start, p_end, layout=True)
    if not text.strip():
        atomic_write_json(out_file, {"chunk_id": cid, "nodes": [], "edges": [],
                                     "error": "empty_pdftotext"})
        return "empty", 0, 0
    # Truncate over-long chunks
    if len(text) > MAX_CHARS_PER_CHUNK:
        text = text[:MAX_CHARS_PER_CHUNK] + "\n...[TRUNCATED]\n"
    chunk_desc = chunk_meta.get("desc", cid)
    prompt = L0_PROMPT_TEMPLATE.format(
        chunk_desc=chunk_desc,
        id_prefix=id_prefix,
        page_start=chunk_meta["page_start"],
        page_end=chunk_meta["page_end"],
        text=text,
    )
    if dry_run:
        atomic_write_json(out_file, {
            "chunk_id": cid, "nodes": [], "edges": [],
            "dry_run": True,
            "prompt_chars": len(prompt),
            "text_chars": len(text),
            "page_range": [chunk_meta["page_start"], chunk_meta["page_end"]],
            "pdf_page_range": [p_start, p_end],
        })
        return "dry_run", 0, 0

    output, err = call_claude(prompt)
    if err:
        atomic_write_json(out_file, {"chunk_id": cid, "nodes": [], "edges": [],
                                     "error": f"claude_cli: {err}"})
        return "error", 0, 0
    parsed = parse_llm_json(output)
    if parsed is None:
        # Save the raw output for debugging but mark as error.
        atomic_write_json(out_file, {"chunk_id": cid, "nodes": [], "edges": [],
                                     "error": "unparseable_json",
                                     "raw_excerpt": (output or "")[:2000]})
        return "parse_error", 0, 0
    nodes = parsed.get("nodes", []) or []
    edges = parsed.get("edges", []) or []
    # Annotate each node with chunk info and layer
    for n in nodes:
        n.setdefault("layer", "L0")
        n.setdefault("source_chunk", cid)
        if "page" not in n and "page_start" in n:
            pass
        if "page_start" not in n and "page" in n:
            n["page_start"] = n["page"]
    atomic_write_json(out_file, {
        "chunk_id": cid,
        "page_range": [chunk_meta["page_start"], chunk_meta["page_end"]],
        "pdf_page_range": [p_start, p_end],
        "nodes": nodes,
        "edges": edges,
    })
    return "ok", len(nodes), len(edges)


# ---------------------------------------------------------------------------
# Per-book main
# ---------------------------------------------------------------------------

def run_book(book_id, dry_run=False, limit=None, resume=True):
    meta = BOOKS[book_id]
    pdf_path = PDF_DIR / meta["pdf"]
    if not pdf_path.exists():
        print(f"[{book_id}] PDF missing: {pdf_path}", file=sys.stderr)
        return None
    out_dir = OUT_ROOT / meta["slug"]
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[{book_id}] pdf={pdf_path.name}")
    num_pages = get_pdf_page_count(pdf_path)
    print(f"[{book_id}] pages={num_pages}")

    # Build chunk plan
    if meta["mode"] == "alphabet":
        chunks = plan_tanton_chunks(pdf_path)
        id_prefix = "tanton"
    elif meta["mode"] == "pcm":
        toc = parse_toc(pdf_path)
        if not toc:
            print(f"[{book_id}] FAILED: empty TOC parse", file=sys.stderr)
            return None
        toc, offset = enrich_toc_pages(toc, pdf_path, num_pages)
        print(f"[{book_id}] TOC: {len(toc)} articles, offset={offset}")
        chunks = []
        for e in toc:
            chunks.append({
                "chunk_id": f"article_{e['part']}_{e['num']:02d}",
                "desc": f"article {e['article_id']} \"{e['title']}\"",
                "page_start": e["page_start"],
                "page_end": e["page_end"],
                "pdf_page_start": e["pdf_page_start"],
                "pdf_page_end": e["pdf_page_end"],
                "article_id": e["article_id"],
                "title": e["title"],
            })
        id_prefix = "pcm" if book_id == "b245" else "pcam"
        # Save TOC for reference
        atomic_write_json(out_dir / "toc.json", {
            "book_id": book_id,
            "title": meta["title"],
            "num_pages": num_pages,
            "offset": offset,
            "articles": toc,
        })
    else:
        raise ValueError(f"Unknown mode {meta['mode']}")

    print(f"[{book_id}] planned {len(chunks)} chunks")
    if limit:
        chunks = chunks[:limit]

    progress_path = out_dir / "progress.json"
    progress = {}
    if resume and progress_path.exists():
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
        except Exception:
            progress = {}
    progress.setdefault("chunks", {})
    progress.setdefault("book_id", book_id)

    total_nodes = 0
    total_edges = 0
    errors = []

    for i, chunk in enumerate(chunks):
        cid = chunk["chunk_id"]
        status_prev = progress["chunks"].get(cid, {}).get("status")
        if status_prev == "ok" and (out_dir / f"{cid}.json").exists():
            # load counts
            try:
                d = json.loads((out_dir / f"{cid}.json").read_text(encoding="utf-8"))
                total_nodes += len(d.get("nodes", []))
                total_edges += len(d.get("edges", []))
            except Exception:
                pass
            continue
        t0 = time.time()
        status, n, e = extract_chunk(pdf_path, chunk, id_prefix, out_dir, dry_run=dry_run)
        dt = time.time() - t0
        total_nodes += n
        total_edges += e
        progress["chunks"][cid] = {
            "status": status,
            "nodes": n,
            "edges": e,
            "seconds": round(dt, 2),
        }
        progress["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        atomic_write_json(progress_path, progress)
        marker = " (dry)" if dry_run else ""
        print(f"[{book_id}] {i+1}/{len(chunks)} {cid}: {status} n={n} e={e} {dt:.1f}s{marker}")
        if status in ("error", "parse_error"):
            errors.append((cid, status))

    # Assemble book.json
    assemble(book_id)

    return {
        "book_id": book_id,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "errors": errors,
    }


def assemble(book_id):
    meta = BOOKS[book_id]
    out_dir = OUT_ROOT / meta["slug"]
    all_nodes = []
    all_edges = []
    node_ids = set()
    chunk_summaries = []
    for jf in sorted(out_dir.glob("*.json")):
        if jf.name in ("book.json", "progress.json", "toc.json"):
            continue
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        ns = data.get("nodes", []) or []
        es = data.get("edges", []) or []
        # deduplicate node ids
        for n in ns:
            nid = n.get("id")
            if not nid:
                continue
            if nid in node_ids:
                continue
            node_ids.add(nid)
            all_nodes.append(n)
        for e in es:
            all_edges.append(e)
        chunk_summaries.append({
            "chunk_id": data.get("chunk_id", jf.stem),
            "page_range": data.get("page_range"),
            "nodes": len(ns),
            "edges": len(es),
            "error": data.get("error"),
        })

    # Count by type
    by_type = {}
    for n in all_nodes:
        t = n.get("type", "UNKNOWN")
        by_type[t] = by_type.get(t, 0) + 1
    edge_by_type = {}
    for e in all_edges:
        t = e.get("type", "UNKNOWN")
        edge_by_type[t] = edge_by_type.get(t, 0) + 1

    book_data = {
        "book_id": book_id,
        "title": meta["title"],
        "authors": meta["authors"],
        "year": meta["year"],
        "source_type": "reference",
        "layer": "L0",
        "pdf": meta["pdf"],
        "num_pages": meta.get("num_pages_hint"),
        "total_nodes": len(all_nodes),
        "total_edges": len(all_edges),
        "nodes_by_type": by_type,
        "edges_by_type": edge_by_type,
        "num_chunks": len(chunk_summaries),
        "chunk_summaries": chunk_summaries,
        "nodes": all_nodes,
        "edges": all_edges,
    }
    atomic_write_json(out_dir / "book.json", book_data)
    print(f"[{book_id}] assembled book.json: {len(all_nodes)} nodes, "
          f"{len(all_edges)} edges, types={by_type}")
    return book_data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", help="book id (b245/b246/b247) or 'assemble'")
    ap.add_argument("book_arg", nargs="?", help="book id for 'assemble'")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan chunks and save stubs; do not call the LLM")
    ap.add_argument("--limit", type=int, default=None,
                    help="max chunks to process (for pilot runs)")
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()

    if args.command == "assemble":
        book_id = args.book_arg
        if book_id not in BOOKS:
            print("Unknown book id; must be one of", list(BOOKS.keys()))
            sys.exit(2)
        assemble(book_id)
        return

    if args.command not in BOOKS:
        print("Unknown book id; must be one of", list(BOOKS.keys()))
        sys.exit(2)
    run_book(args.command, dry_run=args.dry_run, limit=args.limit,
             resume=not args.no_resume)


if __name__ == "__main__":
    main()
