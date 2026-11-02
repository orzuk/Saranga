"""The v7-books prompt for chapters of a prepared book (prepare_book.py), one file per chapter.

    python -m structured_math.books.render_book_prompt PREPARED_BOOK OUT_DIR --title T --authors A --year Y [--chapters 6 10]

Writes OUT_DIR/prompt_chNN.md and OUT_DIR/labels_chNN.json (the book's labels outside chapter
NN); the agent writes its graph to OUT_DIR/chNN.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
from schema_for_prompts import render_prompt        # noqa: E402

PROMPT = REPO / "scripts/opus_extract_prompt_v7_books.md"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("book")
    ap.add_argument("out")
    ap.add_argument("--title", required=True)
    ap.add_argument("--authors", required=True)
    ap.add_argument("--year", required=True)
    ap.add_argument("--chapters", type=int, nargs="*", help="default: all")
    ap.add_argument("--model", default="claude-opus-5-5")
    a = ap.parse_args()
    book, out = Path(a.book), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    toc = json.loads((book / "chapters.json").read_text())["chapters"]
    labels = json.loads((book / "labels.json").read_text())
    t = render_prompt(PROMPT.read_text())
    sha = hashlib.sha256(t.encode()).hexdigest()[:16]
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    for c in toc:
        k = c["chapter"]
        if a.chapters and k not in a.chapters:
            continue
        lab = out / f"labels_ch{k:02d}.json"
        lab.write_text(json.dumps({x: v for x, v in labels.items() if v["chapter"] != k}, ensure_ascii=False))
        v = {"BID": f"{book.name}_ch{k:02d}", "TITLE": f"{a.title}, Chapter {k}: {c['title']}",
             "AUTHORS": a.authors, "YEAR": a.year, "TEX_SOURCE": str((book / c["file"]).resolve()),
             "OUTPUT_JSON": str((out / f"ch{k:02d}.json").resolve()), "BOOK_LABELS": str(lab.resolve()),
             "REPO": str(REPO), "MODEL": a.model, "EFFORT": "default",
             "PROMPT_VERSION": f"v7-books-{sha}-{commit}"}
        x = t
        for key, val in v.items():
            x = x.replace("{" + key + "}", val)
        assert "<!--" not in x and not any("{" + key + "}" in x for key in v)
        (out / f"prompt_ch{k:02d}.md").write_text(x)
        print(out / f"prompt_ch{k:02d}.md")


if __name__ == "__main__":
    main()
