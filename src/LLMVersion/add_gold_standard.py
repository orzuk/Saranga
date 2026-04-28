import csv
import argparse
import re

def add_gold_standard_to_csv(input_csv='definitions.csv', gold_csv='Gold_Standard.csv', output_csv='definitions_with_gold.csv', paper_ids=None):
    """Add Gold Standard columns from a separate CSV to the definitions CSV.

    If paper_ids is provided, only include gold-only rows for those papers
    (used to scope evaluation to train or val set).
    """
    
    # Load gold standard data
    gold_data = {}
    try:
        with open(gold_csv, 'r', encoding='utf-8-sig', errors='replace') as f:  # utf-8-sig handles BOM
            reader = csv.DictReader(f)
            # Strip whitespace from fieldnames
            reader.fieldnames = [name.strip() for name in reader.fieldnames]
            
            for row in reader:
                # Strip whitespace from keys and values
                row = {k.strip(): v for k, v in row.items()}
                paper_id = re.sub(r'v\d+$', '', row['paper_id'].strip().replace('_', '.'))

                if paper_id not in gold_data:
                    gold_data[paper_id] = []
                gold_data[paper_id].append({
                    'raw_latex': row.get('Gold_Standard_raw_latex', ''),
                    'clean_text': row.get('Gold_Standard_clean_text', '')
                })
        print(f"Loaded gold standard data for {len(gold_data)} papers")
    except FileNotFoundError:
        print(f"Warning: {gold_csv} not found.")
        return
    
    # Read input CSV
    with open(input_csv, 'r', encoding='utf-8-sig', errors='replace') as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
        headers = reader.fieldnames
        rows = [{k.strip(): v for k, v in row.items()} for row in reader]
    
    # Create new headers
    new_headers = ['paper_id', 'Gold_Standard_raw_latex', 'Gold_Standard_clean_text'] + headers[1:]
    
    # Process rows
    output_rows = []
    current_paper = None
    gold_index = 0
    # Track how many gold items were paired per paper (by normalized key)
    gold_paired_count = {}

    for row in rows:
        paper_id = row['paper_id'].strip()

        if paper_id != current_paper:
            current_paper = paper_id
            gold_index = 0

        new_row = {'paper_id': paper_id}

        gold_key = re.sub(r'v\d+$', '', paper_id)
        if gold_key in gold_data and gold_index < len(gold_data[gold_key]):
            new_row['Gold_Standard_raw_latex'] = gold_data[gold_key][gold_index]['raw_latex']
            new_row['Gold_Standard_clean_text'] = gold_data[gold_key][gold_index]['clean_text']
        else:
            new_row['Gold_Standard_raw_latex'] = ''
            new_row['Gold_Standard_clean_text'] = ''

        for header in headers[1:]:
            new_row[header] = row[header]

        output_rows.append(new_row)
        gold_index += 1
        gold_paired_count[gold_key] = max(gold_paired_count.get(gold_key, 0), gold_index)

    # Append gold-only rows for items not paired with any extraction
    # (papers with fewer extractions than gold items, or 0 extractions)
    # Normalize paper_ids for matching (strip version suffixes)
    if paper_ids is not None:
        allowed = {re.sub(r'v\d+$', '', pid.replace('_', '.')) for pid in paper_ids}
    else:
        allowed = None
    for gold_key, gold_items in gold_data.items():
        if allowed is not None and gold_key not in allowed:
            continue
        paired = gold_paired_count.get(gold_key, 0)
        for i in range(paired, len(gold_items)):
            new_row = {'paper_id': gold_key}
            new_row['Gold_Standard_raw_latex'] = gold_items[i]['raw_latex']
            new_row['Gold_Standard_clean_text'] = gold_items[i]['clean_text']
            for header in headers[1:]:
                new_row[header] = ''
            output_rows.append(new_row)
    
    # Write output
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=new_headers)
        writer.writeheader()
        writer.writerows(output_rows)
    
    print(f"Created {output_csv} with {len(output_rows)} rows")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-csv', type=str, default='definitions.csv')
    parser.add_argument('--gold-csv', type=str, default='Gold_Standard.csv')
    parser.add_argument('--output-csv', type=str, default='definitions_with_gold.csv')
    
    args = parser.parse_args()
    add_gold_standard_to_csv(args.input_csv, args.gold_csv, args.output_csv)
