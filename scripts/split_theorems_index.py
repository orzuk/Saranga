"""Migrate an existing Method E `theorems.jsonl` (single-file, ~1.8GB)
into the new split format: `theorems_sig.jsonl` (slim, sig only) +
`theorems_text.sqlite` (lazy-load text store).

Why: at corpus scale (~1.24M theorems) the text fields dominate row
size, forcing retrieve onto a SLURM node with 64GB+ RAM. Split format
drops retrieve RAM from ~2.1GB to ~750MB (gateway-runnable). See
src/discovery/method_e/text_store.py for the full rationale.

Usage:
  python3 scripts/split_theorems_index.py \\
      --in   /path/to/run/theorems.jsonl \\
      --sig  /path/to/run/theorems_sig.jsonl \\
      --text /path/to/run/theorems_text.sqlite

The migration is non-destructive — the source theorems.jsonl is not
modified. Idempotent: rerunning overwrites the outputs.

After migration, retrieve_pairs.py auto-detects the split format:
if theorems_sig.jsonl exists in the run dir, it's used (and the
sqlite is opened for lazy text); else the single theorems.jsonl path
is used as before. So you can roll out the split per-run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Bootstrap path so we can import text_store from src/discovery/method_e
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from discovery.method_e.text_store import TextStore  # noqa: E402


SIG_KEEP_FIELDS = (
    "paper_id", "year", "category", "node_id", "node_type",
    "name", "subclass", "conclusion_type",
    "sig_foundation_ids", "sig_operators", "sig_statement_tokens",
)


def split(in_path: Path, sig_path: Path, text_path: Path, *,
          progress_every: int = 50000) -> dict:
    in_path = Path(in_path)
    sig_path = Path(sig_path)
    text_path = Path(text_path)

    # Wipe an existing sqlite so we get a clean store
    if text_path.exists():
        text_path.unlink()

    sig_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    n_with_text = 0
    t0 = time.time()
    batch_text: list[tuple] = []
    batch_size = 2000  # sqlite txn batch

    with in_path.open(encoding="utf-8") as fin, \
         sig_path.open("w", encoding="utf-8") as fsig, \
         TextStore(text_path) as store:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception as e:
                print(f"[split] skip bad line {n}: {e}", file=sys.stderr)
                continue
            n += 1

            # Slim sig row — only fields actually needed for scoring
            sig_row = {k: d.get(k) for k in SIG_KEEP_FIELDS if k in d
                       or k in ("paper_id", "node_id")}  # always keep keys
            fsig.write(json.dumps(sig_row, ensure_ascii=False) + "\n")

            # Stash text for batch insert
            raw = d.get("raw_latex") or ""
            clean = d.get("clean_text") or ""
            if raw or clean:
                batch_text.append((d.get("paper_id") or "",
                                   d.get("node_id") or "",
                                   raw, clean))
                n_with_text += 1
            if len(batch_text) >= batch_size:
                store.put_many(batch_text)
                batch_text = []

            if n % progress_every == 0:
                dt = time.time() - t0
                rate = n / dt if dt else 0
                print(f"[split] {n:>9} rows  ({n_with_text:>9} with text)  "
                      f"  {dt:>6.1f}s  ({rate:>7.0f}/s)", file=sys.stderr)

        if batch_text:
            store.put_many(batch_text)

    sig_size = sig_path.stat().st_size
    text_size = text_path.stat().st_size
    in_size = in_path.stat().st_size

    dt = time.time() - t0
    print(f"\n[split] DONE in {dt:.1f}s", file=sys.stderr)
    print(f"  source theorems.jsonl: {in_size/1e6:>8.1f} MB ({n} rows)", file=sys.stderr)
    print(f"  -> theorems_sig.jsonl: {sig_size/1e6:>8.1f} MB ({n} rows, "
          f"{100*sig_size/in_size:.0f}% of original)", file=sys.stderr)
    print(f"  -> theorems_text.sqlite: {text_size/1e6:>8.1f} MB ({n_with_text} rows with text)", file=sys.stderr)
    print(f"  combined: {(sig_size+text_size)/1e6:.1f} MB "
          f"({100*(sig_size+text_size)/in_size:.0f}% of original)", file=sys.stderr)
    return {"rows": n, "rows_with_text": n_with_text,
            "in_bytes": in_size, "sig_bytes": sig_size,
            "text_bytes": text_size}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_path", type=Path, required=True,
                    help="Source theorems.jsonl (or problems.jsonl)")
    ap.add_argument("--sig", dest="sig_path", type=Path, required=True,
                    help="Destination theorems_sig.jsonl (slim)")
    ap.add_argument("--text", dest="text_path", type=Path, required=True,
                    help="Destination theorems_text.sqlite (lazy store)")
    args = ap.parse_args()
    split(args.in_path, args.sig_path, args.text_path)


if __name__ == "__main__":
    main()
