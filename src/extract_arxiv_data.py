from extract_arxiv_funcs import *

if __name__ == "__main__":
    import sys, argparse
    # decide interactive (PyCharm/Windows) vs CLI
    if sys.platform.lower().startswith('win') and len(sys.argv) == 1:
        # interactive example: single paper, extract all formats
        example_id = '2309.00543v1'
        print(f"=== Interactive example: ID={example_id} ===")
        regex_id   = f'^{example_id}$'
        start_date = None
        end_date   = None
        category   = None
        formats    = ['metadata', 'pdf', 'html', 'source']
        output_dir = None
        verbose    = True
    else:
        # command-line mode
        parser = argparse.ArgumentParser(description="Fetch arXiv content via fetch_arxiv_batch")
        parser.add_argument('--id',        dest='regex_id',  help='Regex for arXiv ID, e.g. "2309.00543v1"')
        parser.add_argument('--start',     dest='start_date',help='Start date YYYY-MM-DD')
        parser.add_argument('--end',       dest='end_date',  help='End date YYYY-MM-DD')
        parser.add_argument('--category',                 help='ArXiv category, e.g. cs.AI')
        parser.add_argument('--formats',   nargs='+',     default=['metadata'],
                            help='One or more: metadata, abstract, pdf, html, source')
        parser.add_argument('--output-dir',                help='Directory to save pdf/html/source files')
        parser.add_argument('--verbose',    action='store_true', help='Enable debug prints')
        args = parser.parse_args()

        regex_id   = args.regex_id
        start_date = args.start_date
        end_date   = args.end_date
        category   = args.category
        formats    = args.formats
        output_dir = args.output_dir
        verbose    = args.verbose
        if output_dir is None:
            output_dir = DATA_DIR + '/full_papers'

    # Single unified call
    data = fetch_arxiv_batch(
        regex_id   = regex_id,
        start_date = start_date,
        end_date   = end_date,
        category   = category,
        formats    = formats,
        output_dir = output_dir,
        verbose    = verbose)


    # Print snippets for each paper
    for aid, entry in data.items():
        print(f"=== {aid} ===")
        if 'metadata' in formats:
            md = entry.get('metadata', {})
            print("MD: ", md)
            print("MD TYPE: ", type(md))
            print("MD KEYS: ", md.keys())
            print("Title:", md.get('title'))
#            print("Authors:", ', '.join(md.get('authors', [])))
            print("Authors:", md.get('authors', ''))
            abs_txt = md.get('abstract', '')
            print("Abstract (first 3 lines):")
            for ln in abs_txt.splitlines()[:3]: print("  ", ln)
        if 'abstract' in formats:
            abs_txt = entry.get('abstract', '')
            print("Abstract (first 3 lines):")
            for ln in abs_txt.splitlines()[:3]: print("  ", ln)
            print(" ")
        if 'pdf' in formats and 'pdf' in entry:
            pdf = entry['pdf']
            print("PDF (first 50 bytes):")
            print(pdf[:50])
            print(" ")
        if 'html' in formats and 'html' in entry:
            html_lines = entry['html']
            print("HTML (first 5 lines):")
            for ln in html_lines[:5]: print("  ", ln)
            print(" ")
        if 'source' in formats and 'source' in entry:
            src_lines = entry['source']
            if src_lines is None:
                print(f"No valid LaTeX source for {aid}, skipping.\n")
            else:
                print("LaTeX source (first 5 lines):")
                for ln in src_lines[:5]: print("  ", ln)
                print(" ")
    sys.exit(0)


