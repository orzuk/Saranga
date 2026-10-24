"""Provenance and bibliography for a unified JSON: what produced it, and the paper's references.

Every extractor calls stamp() on the graph it is about to write; scripts/stamp_provenance.py does the same for
JSONs written before this existed, without touching their nodes or edges. Two metadata fields:

  metadata.provenance    {extractor: rules | llm | both, tool, model, prompt_version, edge_model, rules_dir,
                          code_commit, date, stamped: at_extraction | backfill, stamp_date}
                         (fields that do not apply are left out; a backfilled field that was not recorded
                          at extraction is "unknown")
  metadata.bibliography  {cite key: {"text": entry, "arxiv": id or null}}, from \\bibitem lists in the source,
                         and the paper's .bbl / .bib files (beside the .tex, named by \\bibliography{...},
                         or inside the paper's source tarball)

    from provenance import stamp
    stamp(d, tex_path, extractor="rules", tool="parse_batch", edge_model=...)
"""
from __future__ import annotations

import datetime
import re
import subprocess
import tarfile
from functools import lru_cache
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_NEW_ID = re.compile(r"(?:arxiv[:\s/.]*|arxiv\.org/(?:abs|pdf)/)\s*(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
_OLD_ID = re.compile(r"\b((?:math|math-ph|hep-th|hep-ph|quant-ph|cs|nlin|gr-qc|cond-mat|stat|q-alg|alg-geom|dg-ga|"
                     r"funct-an)(?:\.[A-Z]{2})?/\d{7})")
_EPRINT = re.compile(r"\beprint\s*=\s*[{\"]\s*(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})", re.I)
_MAX_ENTRY = 1500


@lru_cache(maxsize=None)
def code_commit(short: int = 12, dirty: bool = True, paths: tuple = ("src",)) -> str:
    """The repo's commit (the one place the code version is read), '-dirty' when tracked files under `paths`
    have uncommitted changes. Without a checkout (the portal container) the COMMIT file staging writes."""
    try:
        sha = subprocess.run(["git", "-C", str(_REPO), "rev-parse", f"--short={short}", "HEAD"], capture_output=True,
                             text=True, timeout=10).stdout.strip()
        if sha and dirty and subprocess.run(["git", "-C", str(_REPO), "status", "--porcelain", "--untracked-files=no",
                                             "--", *paths], capture_output=True, text=True, timeout=30).stdout.strip():
            sha += "-dirty"
    except (OSError, subprocess.SubprocessError):
        sha = ""
    if not sha and (_REPO / "COMMIT").is_file():
        sha = (_REPO / "COMMIT").read_text().strip()
    return sha or "unknown"


def arxiv_source_dirs(root) -> dict:
    """arXiv id (no version) -> its folder in an arXiv tree laid out <root>/YYYY/MM/DD/<id>/ (the cluster's
    all_arxiv_papers): one directory listing per day, no recursive walk."""
    import glob
    import os
    out = {}
    for day in glob.glob(f"{root}/*/*/*"):
        try:
            for e in os.scandir(day):
                out[re.sub(r"v\d+$", "", e.name)] = Path(e.path)
        except OSError:
            pass
    return out


def arxiv_id_in(entry: str):
    """An arXiv id written in a bibliography entry (eprint field, arXiv:..., arxiv.org/abs/..., old style)."""
    m = _EPRINT.search(entry) or _NEW_ID.search(entry) or _OLD_ID.search(entry)
    return m.group(1) if m else None


def parse_bibliography(text: str) -> dict:
    """{key: entry text} of the \\bibitem lists and .bib records in text."""
    out = {}
    for m in re.finditer(r"\\bibitem\s*(?:\[[^\]]*(?:\[[^\]]*\][^\]]*)*\])?\s*\{([^}]+)\}(.*?)"
                         r"(?=\\bibitem|\\end\{thebibliography\}|$)", text, re.S):
        out.setdefault(m.group(1).strip(), " ".join(m.group(2).split())[:_MAX_ENTRY])
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)(?=\n\s*@\w+\s*\{|$)", text, re.S):
        if m.group(1).lower() not in ("string", "comment", "preamble"):
            out.setdefault(m.group(2).strip(), " ".join(m.group(3).split())[:_MAX_ENTRY])
    return out


def _sources(tex_path: Path, tex: str, src_dir: Path | None = None) -> list[str]:
    """The texts that may hold the bibliography: the .tex, its .bbl / .bib, and the paper's original source
    (its tarball beside the .tex, or src_dir: a folder holding only this paper's source, e.g. its arXiv tree
    folder), whose .tex files count too, since a flattened .tex may have lost its thebibliography."""
    d, stem = tex_path.parent, tex_path.stem
    names = {f"{stem}.bbl", f"{stem}.bib"}
    for m in re.finditer(r"\\(?:bibliography|addbibresource)\s*\{([^}]+)\}", tex):
        for b in m.group(1).split(","):
            b = b.strip()
            names.add(b if b.endswith(".bib") else b + ".bib")
    texts = [tex]
    for n in sorted(names):
        p = d / n
        if p.is_file() and p.stat().st_size < 20_000_000:
            texts.append(p.read_text(encoding="utf-8", errors="ignore"))
    tarballs = sorted(d.glob(f"{stem}*.tar.gz")) + sorted(d.glob(f"{stem}*.tgz"))
    if src_dir is not None and Path(src_dir).is_dir():
        for p in sorted(Path(src_dir).iterdir()):
            if p.suffix.lower() in (".bbl", ".bib", ".tex") and p.stat().st_size < 20_000_000:
                texts.append(p.read_text(encoding="utf-8", errors="ignore"))
            elif p.name.endswith((".tar.gz", ".tgz")):
                tarballs.append(p)
    for tgz in sorted(set(tarballs)):
        try:
            with tarfile.open(tgz) as t:
                for m in t.getmembers():
                    if m.isfile() and m.name.lower().endswith((".bbl", ".bib", ".tex")) and m.size < 20_000_000:
                        texts.append(t.extractfile(m).read().decode("utf-8", "ignore"))
        except (OSError, tarfile.TarError, EOFError):
            pass
    return texts


def bibliography(tex_path, tex: str | None = None, src_dir=None) -> dict:
    """{key: {"text", "arxiv"}} for the paper whose main source is tex_path (see _sources for src_dir)."""
    tex_path = Path(tex_path)
    if tex is None:
        tex = tex_path.read_text(encoding="utf-8", errors="ignore") if tex_path.is_file() else ""
    entries = {}
    for t in _sources(tex_path, tex, src_dir):
        for k, e in parse_bibliography(t).items():
            entries.setdefault(k, e)
    return {k: {"text": e, "arxiv": arxiv_id_in(e)} for k, e in entries.items()}


def stamp(d: dict, tex_path=None, *, extractor: str, tool: str, backfill: bool = False, tex: str | None = None,
          src_dir=None, **fields) -> dict:
    """Write metadata.provenance (and metadata.bibliography when the source is given) into d, in place.
    fields: model, prompt_version, edge_model, rules_dir, date, code_commit, ... (None values are dropped)."""
    md = d.setdefault("metadata", {})
    today = datetime.date.today().isoformat()
    prov = {"extractor": extractor, "tool": tool}
    prov.update({k: (str(v) if isinstance(v, Path) else v) for k, v in fields.items() if v is not None})
    prov.setdefault("code_commit", "unknown" if backfill else code_commit())
    prov.setdefault("date", "unknown" if backfill else today)
    prov["stamped"] = "backfill" if backfill else "at_extraction"
    prov["stamp_date"] = today
    if backfill:
        prov["stamp_commit"] = code_commit()
    md["provenance"] = prov
    if tex_path is not None or tex is not None or src_dir is not None:
        md["bibliography"] = bibliography(tex_path or Path("_"), tex, src_dir)
    return d
