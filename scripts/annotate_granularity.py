#!/usr/bin/env python3
"""
Re-scan all extracted paper/book JSONs and (re-)populate granularity columns:

  - proof_steps_granularity  {yes, partial, no, no_proofs, unknown}
  - equations_granularity    {yes, partial, no, unknown}
  - proof_count              int
  - proof_step_count         int
  - equation_count           int

Run it after any batch of new extractions to refresh the CSVs.
Safe to run repeatedly — overwrites the above columns in place.

CSVs updated:
  /mnt/g/My Drive/Research/Automath/alignment_benchmark/paper_registry.csv
  /mnt/g/My Drive/Research/Automath/undergrad_textbooks.csv

Paper JSONs expected at:
  /mnt/g/My Drive/Research/Automath/alignment_benchmark/papers/paperN/gold.json

Book JSONs expected at:
  /mnt/c/Code/Github/Authomathics/textbooks/extracted/bNNN_slug/book.json
  (plus chapter_*.json siblings for the Blum-Hopcroft-Kannan course layout)
"""
import json
import os
import csv
import glob
import sys
from collections import Counter

# --- config -----------------------------------------------------------------

PAPER_REGISTRY = '/mnt/g/My Drive/Research/Automath/alignment_benchmark/paper_registry.csv'
PAPER_BASE = '/mnt/g/My Drive/Research/Automath/alignment_benchmark/papers'
BOOK_CSV = '/mnt/g/My Drive/Research/Automath/undergrad_textbooks.csv'
BOOK_BASE = '/mnt/c/Code/Github/Authomathics/textbooks/extracted'

NEW_COLS = [
    'proof_steps_granularity',
    'equations_granularity',
    'proof_count',
    'proof_step_count',
    'equation_count',
]

THEOREM_LIKE = {'theorem', 'lemma', 'proposition', 'corollary', 'claim'}
TYPE_ALIASES = {
    'thm': 'theorem', 'lem': 'lemma', 'prop': 'proposition', 'cor': 'corollary',
    'pf': 'proof', 'eq': 'equation',
    'step': 'proof_step', 'proof-step': 'proof_step', 'proofstep': 'proof_step',
}


# --- per-JSON classifier ----------------------------------------------------

def classify(json_path):
    """Read one paper/book JSON and return granularity dict."""
    out = {
        'proof_count': 0,
        'proof_step_count': 0,
        'theorem_like_count': 0,
        'equation_count': 0,
        'proof_steps_granularity': 'unknown',
        'equations_granularity': 'unknown',
        'node_count': 0,
    }
    try:
        with open(json_path) as f:
            data = json.load(f)
    except Exception:
        return out

    nodes = []
    if isinstance(data, dict):
        nodes = data.get('nodes', []) or data.get('chapter_nodes', []) or []

    # If book.json is empty, some layouts store content in chapter_*.json siblings
    if not nodes:
        d = os.path.dirname(json_path)
        for cf in sorted(glob.glob(os.path.join(d, 'chapter_*.json'))):
            try:
                cd = json.load(open(cf))
                if isinstance(cd, dict):
                    nodes.extend(cd.get('nodes', []) or [])
            except Exception:
                pass

    out['node_count'] = len(nodes)
    if not nodes:
        return out

    for n in nodes:
        t = (n.get('type', '') or '').lower().strip()
        t = TYPE_ALIASES.get(t, t)
        if t == 'proof':
            out['proof_count'] += 1
            # Legacy: nested steps[] inside proof node
            if n.get('steps'):
                out['proof_step_count'] += len(n['steps'])
        elif t == 'proof_step':
            out['proof_step_count'] += 1
        elif t in THEOREM_LIKE:
            out['theorem_like_count'] += 1
        elif t == 'equation':
            out['equation_count'] += 1

    # Proof-step granularity
    p, ps = out['proof_count'], out['proof_step_count']
    if p == 0:
        out['proof_steps_granularity'] = 'no_proofs'
    elif ps == 0:
        out['proof_steps_granularity'] = 'no'
    else:
        ratio = ps / max(p, 1)
        if ratio >= 2.0:
            out['proof_steps_granularity'] = 'yes'
        elif ratio >= 0.3:
            out['proof_steps_granularity'] = 'partial'
        else:
            out['proof_steps_granularity'] = 'partial'  # any steps at all ⇒ not "no"

    # Equation granularity
    tl, eq = out['theorem_like_count'], out['equation_count']
    if tl == 0 and eq == 0:
        out['equations_granularity'] = 'unknown'
    elif eq == 0:
        out['equations_granularity'] = 'no'
    else:
        ratio = eq / max(tl, 1)
        if ratio >= 0.5:
            out['equations_granularity'] = 'yes'
        elif ratio >= 0.05:
            out['equations_granularity'] = 'partial'
        else:
            out['equations_granularity'] = 'partial'

    return out


# --- CSV helpers ------------------------------------------------------------

def ensure_cols(fieldnames, cols):
    for c in cols:
        if c not in fieldnames:
            fieldnames.append(c)
    return fieldnames


def update_csv(csv_path, json_locator, stats_label):
    """Read csv, classify each row's JSON, write back."""
    rows = list(csv.DictReader(open(csv_path)))
    fieldnames = list(rows[0].keys()) if rows else []
    fieldnames = ensure_cols(fieldnames, NEW_COLS)

    processed = 0
    stats = Counter()

    for r in rows:
        jp = json_locator(r)
        if jp and os.path.exists(jp):
            info = classify(jp)
            r['proof_steps_granularity'] = info['proof_steps_granularity']
            r['equations_granularity'] = info['equations_granularity']
            r['proof_count'] = str(info['proof_count'])
            r['proof_step_count'] = str(info['proof_step_count'])
            r['equation_count'] = str(info['equation_count'])
            stats['proof_steps:' + info['proof_steps_granularity']] += 1
            stats['equations:' + info['equations_granularity']] += 1
            processed += 1
        else:
            for c in NEW_COLS:
                r.setdefault(c, '')

    with open(csv_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f'\n=== {stats_label} ({len(rows)} rows, {processed} with JSON) ===')
    for k, v in sorted(stats.items()):
        print(f'  {v:4d}  {k}')


# --- locators ---------------------------------------------------------------

def locate_paper_json(row):
    pid = row.get('paper_id', '').strip()
    return os.path.join(PAPER_BASE, pid, 'gold.json')


# Build book-id → extracted-dir map (has slug suffixes like "b283_mathforcs")
_BOOK_DIR_MAP = None


def _book_dirs():
    global _BOOK_DIR_MAP
    if _BOOK_DIR_MAP is None:
        _BOOK_DIR_MAP = {}
        if os.path.isdir(BOOK_BASE):
            for d in os.listdir(BOOK_BASE):
                if d.startswith('b') and '_' in d:
                    _BOOK_DIR_MAP[d.split('_', 1)[0]] = os.path.join(BOOK_BASE, d)
                elif len(d) >= 4 and d.startswith('b') and d[1:4].isdigit():
                    _BOOK_DIR_MAP[d[:4]] = os.path.join(BOOK_BASE, d)
    return _BOOK_DIR_MAP


def locate_book_json(row):
    bid = row.get('book_id', '').strip()
    d = _book_dirs().get(bid)
    if not d:
        return None
    return os.path.join(d, 'book.json')


# --- main -------------------------------------------------------------------

def main():
    print('Annotating papers...')
    update_csv(PAPER_REGISTRY, locate_paper_json, 'Papers')
    print('\nAnnotating books...')
    update_csv(BOOK_CSV, locate_book_json, 'Books')
    print('\nDone. Both CSVs updated in place.')


if __name__ == '__main__':
    main()
