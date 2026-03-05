import csv
import argparse
import re
from collections import defaultdict

def normalize_latex(text):
    """Normalize LaTeX for comparison"""
    if not text or pd.isna(text):
        return ""
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove formatting commands
    text = re.sub(r'\\textit\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\textbf\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\emph\{([^}]+)\}', r'\1', text)
    # Remove citations
    text = re.sub(r'\\cite\{[^}]+\}', '', text)
    text = re.sub(r'~\\cite\{[^}]+\}', '', text)
    return text.strip().lower()

def tokenize_latex(text):
    """Split into tokens: LaTeX commands and words"""
    if not text:
        return set()
    # Match LaTeX commands (\command), words, numbers, and important symbols
    tokens = re.findall(r'\\[a-zA-Z]+|[a-zA-Z]+|[0-9]+|\$|[{}()[\]]', text)
    return set(tokens)

def jaccard_similarity(text1, text2):
    """Compute Jaccard similarity between two LaTeX texts"""
    text1_norm = normalize_latex(text1)
    text2_norm = normalize_latex(text2)
    
    tokens1 = tokenize_latex(text1_norm)
    tokens2 = tokenize_latex(text2_norm)
    
    if not tokens1 or not tokens2:
        return 0.0
    
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    
    return len(intersection) / len(union)

def find_best_match(def_text, gold_standards):
    """Find the best matching gold standard and return (index, similarity, gold_text)"""
    if not def_text or not gold_standards:
        return None, 0.0, ""
    
    best_idx = None
    best_sim = 0.0
    best_text = ""
    
    for idx, gold_text in enumerate(gold_standards):
        if not gold_text:
            continue
        sim = jaccard_similarity(def_text, gold_text)
        if sim > best_sim:
            best_sim = sim
            best_idx = idx
            best_text = gold_text
    
    return best_idx, best_sim, best_text

def evaluate_definitions(input_csv, output_csv='evaluation_results.csv', 
                        detailed_csv='detailed_matches.csv', threshold=0.7):
    """Evaluate each method's definitions against gold standard"""
    
    # Read the merged CSV
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        rows = list(reader)
    
    # Extract provider names (columns ending with _raw_latex, excluding Gold_Standard)
    providers = []
    for h in headers:
        if h.endswith('_raw_latex') and not h.startswith('Gold_Standard'):
            provider = h.replace('_raw_latex', '')
            providers.append(provider)
    
    print(f"Found providers: {providers}")
    
    # Group rows by paper_id
    papers = defaultdict(list)
    for row in rows:
        papers[row['paper_id']].append(row)
    
    print(f"Found {len(papers)} papers")
    
    # Store detailed results for each definition
    detailed_results = []
    
    # Store summary results per paper and provider
    summary_results = []
    
    for paper_id, paper_rows in papers.items():
        # Extract gold standards for this paper
        gold_standards = [row.get('Gold_Standard_raw_latex', '') 
                         for row in paper_rows if row.get('Gold_Standard_raw_latex', '').strip()]
        
        print(f"\nPaper {paper_id}: {len(gold_standards)} gold standard definitions")
        
        # Track which gold standards have been matched
        gold_matched = [False] * len(gold_standards)
        
        # Evaluate each provider
        for provider in providers:
            provider_defs = []
            
            # Extract all definitions from this provider for this paper
            for row in paper_rows:
                def_text = row.get(f'{provider}_raw_latex', '')
                if def_text and def_text.strip():
                    provider_defs.append(def_text)
            
            if not provider_defs:
                print(f"  {provider}: No definitions found")
                continue
            
            print(f"  {provider}: {len(provider_defs)} definitions")
            
            # For each definition, find best matching gold standard
            tp = 0
            fp = 0
            
            for def_idx, def_text in enumerate(provider_defs):
                best_gold_idx, similarity, best_gold_text = find_best_match(def_text, gold_standards)
                
                is_match = similarity >= threshold
                
                # Record detailed result
                detailed_results.append({
                    'paper_id': paper_id,
                    'provider': provider,
                    'definition_index': def_idx,
                    'definition_text': def_text[:200] + '...' if len(def_text) > 200 else def_text,
                    'best_match_gold_index': best_gold_idx if best_gold_idx is not None else '',
                    'best_match_gold_text': best_gold_text[:200] + '...' if len(best_gold_text) > 200 else best_gold_text,
                    'similarity': f'{similarity:.3f}',
                    'is_match': 'Yes' if is_match else 'No',
                    'threshold': threshold
                })
                
                if is_match:
                    tp += 1
                    if best_gold_idx is not None:
                        gold_matched[best_gold_idx] = True
                else:
                    fp += 1
            
            # Calculate metrics for this provider and paper
            fn = len(gold_standards) - sum(gold_matched)
            
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / len(gold_standards) if len(gold_standards) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            
            summary_results.append({
                'paper_id': paper_id,
                'provider': provider,
                'num_gold_standards': len(gold_standards),
                'num_extracted': len(provider_defs),
                'true_positives': tp,
                'false_positives': fp,
                'false_negatives': fn,
                'precision': f'{precision:.3f}',
                'recall': f'{recall:.3f}',
                'f1_score': f'{f1:.3f}'
            })
            
            print(f"    TP: {tp}, FP: {fp}, FN: {fn}, Precision: {precision:.3f}, Recall: {recall:.3f}, F1: {f1:.3f}")
            
            # Reset gold_matched for next provider
            gold_matched = [False] * len(gold_standards)
    
    # Write detailed results
    if detailed_results:
        with open(detailed_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=detailed_results[0].keys())
            writer.writeheader()
            writer.writerows(detailed_results)
        print(f"\nDetailed results saved to {detailed_csv}")
    
    # Write summary results
    if summary_results:
        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=summary_results[0].keys())
            writer.writeheader()
            writer.writerows(summary_results)
        print(f"Summary results saved to {output_csv}")
    
    # Calculate overall metrics per provider
    print("\n" + "="*80)
    print("OVERALL METRICS BY PROVIDER")
    print("="*80)
    
    provider_totals = defaultdict(lambda: {'tp': 0, 'fp': 0, 'fn': 0, 'gold': 0})
    
    for result in summary_results:
        provider = result['provider']
        provider_totals[provider]['tp'] += result['true_positives']
        provider_totals[provider]['fp'] += result['false_positives']
        provider_totals[provider]['fn'] += result['false_negatives']
        provider_totals[provider]['gold'] += result['num_gold_standards']
    
    for provider, totals in sorted(provider_totals.items()):
        precision = totals['tp'] / (totals['tp'] + totals['fp']) if (totals['tp'] + totals['fp']) > 0 else 0.0
        recall = totals['tp'] / totals['gold'] if totals['gold'] > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        print(f"\n{provider}:")
        print(f"  Total Gold Standards: {totals['gold']}")
        print(f"  True Positives: {totals['tp']}")
        print(f"  False Positives: {totals['fp']}")
        print(f"  False Negatives: {totals['fn']}")
        print(f"  Precision: {precision:.3f}")
        print(f"  Recall: {recall:.3f}")
        print(f"  F1 Score: {f1:.3f}")

# Import pandas for isna check
try:
    import pandas as pd
except ImportError:
    # Fallback if pandas not available
    class pd:
        @staticmethod
        def isna(x):
            return x is None or (isinstance(x, str) and x.strip() == '')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate definition extraction methods")
    parser.add_argument('--input-csv', type=str, required=True, 
                        help='Merged CSV with gold standard and provider definitions')
    parser.add_argument('--output-csv', type=str, default='evaluation_results.csv',
                        help='Output CSV for summary results')
    parser.add_argument('--detailed-csv', type=str, default='detailed_matches.csv',
                        help='Output CSV for detailed per-definition results')
    parser.add_argument('--threshold', type=float, default=0.7,
                        help='Similarity threshold for considering a match (default: 0.7)')
    
    args = parser.parse_args()
    
    evaluate_definitions(args.input_csv, args.output_csv, args.detailed_csv, args.threshold)
