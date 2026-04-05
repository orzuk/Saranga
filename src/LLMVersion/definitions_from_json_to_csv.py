import json
import csv
import argparse
from pathlib import Path
from glob import glob

def extract_definitions_to_csv(out_dir='.', paper_ids=None, output_csv='definitions.csv',
                               structure_type='definition'):
    """Extract objects of a given structure type from all provider JSONs into CSV."""

    if paper_ids is None:
        paper_ids = ['2501.00685']

    all_data = {}

    for paper_id in paper_ids:
        # Find all JSON files matching the paper_id pattern
        pattern = f"{out_dir}/**/json/{paper_id}*_*.json"
        files = sorted(glob(pattern, recursive=True))

        if not files:
            print(f"No JSON files found for paper {paper_id}")
            continue

        print(f"Found {len(files)} files for {paper_id}: {[Path(f).name for f in files]}")

        # Load objects from each file
        for f in files:
            fname = Path(f).name
            with open(f) as file:
                content = json.load(file)
                nodes = content.get('nodes', [])
                defs = [obj for obj in nodes if obj.get('type') == structure_type]

                # Key: (paper_id, provider)
                provider = fname.split('_', 1)[1].rsplit('.', 1)[0]
                all_data[(paper_id, provider)] = defs

    if not all_data:
        print(f"No {structure_type}s found")
        return
    
    max_len = max(len(v) for v in all_data.values())
    
    # Create headers: paper_id, provider_raw_latex, provider_clean_text
    headers = ['paper_id']
    providers = sorted(set(provider for _, provider in all_data.keys()))
    for provider in providers:
        headers.extend([f'{provider}_raw_latex', f'{provider}_clean_text'])
    
    # Write CSV
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(headers)
        
        # Group by paper
        papers = sorted(set(paper_id for paper_id, _ in all_data.keys()))
        
        for paper_id in papers:
            # Find max defs for this paper across all providers
            paper_max = max(
                len(all_data.get((paper_id, p), []))
                for p in providers
            )
            
            for i in range(paper_max):
                row = [paper_id]
                for provider in providers:
                    key = (paper_id, provider)
                    if key in all_data and i < len(all_data[key]):
                        obj = all_data[key][i]
                        row.append(obj.get('raw_latex', ''))
                        row.append(obj.get('clean_text', ''))
                    else:
                        row.extend(['', ''])
                w.writerow(row)
    
    print(f"Saved {structure_type}s from {len(papers)} papers to {output_csv}")


# Backward-compatible alias
extract_objects_to_csv = extract_definitions_to_csv


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract objects from parsed papers to CSV")
    parser.add_argument('--paper-id', type=str, action='append', help='Paper ID (can be used multiple times)')
    parser.add_argument('--out-dir', type=str, default='.', help='Output directory where JSONs are stored')
    parser.add_argument('--output-csv', type=str, default='definitions.csv', help='Output CSV filename')
    parser.add_argument('--structure-type', type=str, default='definition',
                        help='Structure type to extract (default: definition)')

    args = parser.parse_args()

    extract_definitions_to_csv(args.out_dir, args.paper_id, args.output_csv,
                               structure_type=args.structure_type)
