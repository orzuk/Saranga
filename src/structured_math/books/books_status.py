"""Progress of the v7-books foundation by topic: which books have source, which chapters are
extracted. Reads foundation_books.json and the books_v7b/{prepared,graphs} folders.

    python -m structured_math.books.books_status [ROOT]     (ROOT default: <DATASET_ROOT>/foundation/books_v7b)
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def book_state(b: dict, root: Path) -> tuple[str, int, int]:
    """(state, chapters extracted, chapters prepared)."""
    prep = root / "prepared" / b.get("prepared", "")
    n = len(json.loads((prep / "chapters.json").read_text())["chapters"]) if b.get("prepared") and (prep / "chapters.json").is_file() else 0
    done = len(list((root / "graphs" / b["id"]).glob("ch[0-9][0-9].json")))
    if n and done >= n:
        return "done", done, n
    if done:
        return "extracting", done, n
    if n:
        return "prepared", done, n
    return ("source" if b["source"] == "have" else b["source"].split(":")[0]), done, n


def main():
    sys.path.insert(0, str(HERE.parents[1]))
    from config import DATASET_ROOT
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(DATASET_ROOT) / "foundation/books_v7b"
    cat = json.loads((HERE / "foundation_books.json").read_text())
    rank = {"done": 0, "extracting": 1, "prepared": 2, "source": 3, "pending": 4, "blocked": 5}
    states = {b["id"]: book_state(b, root) for b in cat["books"]}
    print(f"{'topic':32} {'status':11} books")
    for t in cat["topics"]:
        bs = sorted((b for b in cat["books"] if t in b["topics"]), key=lambda b: rank[states[b["id"]][0]])
        best = states[bs[0]["id"]][0] if bs else "nothing"
        shown = "; ".join(f"{b['id']} {s}" + (f" {d}/{n}" if n else "")
                          for b in bs for s, d, n in [states[b["id"]]])
        print(f"{t:32} {best:11} {shown or '-'}")


if __name__ == "__main__":
    main()
