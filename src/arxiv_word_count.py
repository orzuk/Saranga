# ===== File: arxiv_wordcount_compare.py =====
#!/usr/bin/env python3
"""
arxiv_wordcount_compare.py

Compare abstract word usage between arXiv categories over a date range,
using the unified fetch_arxiv_batch() above.
Supports default test run (no args) and CLI mode.
"""
import os
import re
import argparse
import sys
from collections import Counter
from extract_arxiv_data import fetch_arxiv_batch

# Optional word-cloud support
try:
    from wordcloud import WordCloud, STOPWORDS
    _have_wordcloud = True
except ImportError:
    _have_wordcloud = False
    STOPWORDS = set()


def analyze_category(category, start_date, end_date,
                     top_n, batch_size, out_dir):
    print(f"\n=== CATEGORY: {category} | {start_date} to {end_date} ===")
    os.makedirs(out_dir, exist_ok=True)
    # Pull abstracts only
    data = fetch_arxiv_batch(
        start_date=start_date,
        end_date=end_date,
        category=category,
        formats='abstract',
        batch_size=batch_size,
        output_dir=None,
        verbose=True
    )
    abstracts = [data[aid]['abstract'] for aid in data]
    print(f"Total abstracts fetched: {len(abstracts)}")
    if not abstracts:
        print(">>> ERROR: No abstracts fetched. Verify query.")
        return
    text = " ".join(abstracts).lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    words = text.split()
    stop = set(STOPWORDS)
    filtered = [w for w in words if w not in stop and len(w) > 2]
    freq = Counter(filtered)
    top = freq.most_common(top_n)
    print(f"Top {top_n} words for '{category}':")
    for w, c in top:
        print(f"  {w:15} {c}")
    if _have_wordcloud:
        wc = WordCloud(width=800, height=400,
                       background_color='white', stopwords=stop)
        wc = wc.generate_from_frequencies(freq)
        fn = f"wordcloud_{category}_{start_date.replace('-','')}_to_{end_date.replace('-','')}.png"
        out_file = os.path.join(out_dir, fn)
        wc.to_file(out_file)
        print(f"Saved word cloud to {out_file}\n")


def main(args_list=None):
    parser = argparse.ArgumentParser(description="Compare arXiv abstracts between categories")
    parser.add_argument('--start', help='YYYY-MM-DD')
    parser.add_argument('--end', help='YYYY-MM-DD')
    parser.add_argument('--categories', nargs='+', help='Categories, e.g. math physics')
    parser.add_argument('--top-n', type=int, default=30)
    parser.add_argument('--batch-size', type=int, default=200)
    parser.add_argument('--out-dir', default='out')
    args = parser.parse_args(args_list)
    if args.start and args.end and args.categories:
        for cat in args.categories:
            analyze_category(cat, args.start, args.end, args.top_n, args.batch_size, args.out_dir)
    else:
        print("No CLI args; running default tests")
        default_start, default_end = '2023-09-01','2023-09-07'
        for cat in ['math','physics']:
            analyze_category(cat, default_start, default_end, args.top_n, args.batch_size, args.out_dir)

if __name__=='__main__':
    if sys.platform.startswith('win') and len(sys.argv)==1:
        main(args_list=[])
    else:
        main()
