import json
import csv

files = ['1707.07938v2_manual.json']

data = {}
for f in files:
    with open(f) as file:
        content = json.load(file)
        objects = content.get('objects', {})
        # Filter objects where kind == 'definition'
        data[f] = [obj for obj in objects.values() if obj.get('kind') == 'definition']

max_len = max(len(v) for v in data.values())

# Create headers: provider_raw_latex, provider_clean_text for each file
headers = []
for f in files:
    provider = f.split('_')[1].split('.')[0]  # Extract 'openai', 'huggingface', 'anthropic'
    headers.extend([f'{provider}_raw_latex', f'{provider}_clean_text'])

with open('definitions.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(headers)
    
    for i in range(max_len):
        row = []
        for file in files:
            if i < len(data[file]):
                obj = data[file][i]
                row.append(obj.get('raw_latex', ''))
                row.append(obj.get('clean_text', ''))
            else:
                row.extend(['', ''])
        w.writerow(row)
