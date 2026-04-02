# Authomathics

Tools for downloading, parsing, and structuring mathematical knowledge from arXiv papers and textbooks. Extracts knowledge graphs (definitions, theorems, lemmas, proofs, and their dependencies) from LaTeX sources, links them to a foundation of well-known results, and provides visualization and evaluation tools.

---

## Overview

| Tool | What it does |
|------|-------------|
| `extract_arxiv_data.py` | Download metadata, PDFs, LaTeX source, and HTML from arXiv |
| `validate_annotation.py` | Validate knowledge graph JSONs (DAG check, field checks, edge integrity) |
| `visualize_annotation.py` | Generate PNG/SVG DAG visualizations and interactive HTML |
| `link_to_foundation.py` | Link paper nodes to well-known math results (Markov, Cauchy-Schwarz, ...) |
| `evaluate_extraction.py` | Evaluate extracted JSON against gold standard (precision/recall/F1) |
| `run_evaluation.py` | Full pipeline: extract + evaluate across documents x models |
| `run_all_evaluations.py` | Batch evaluation: compare multiple extractors + student submissions |

---

## Quick Start

```bash
git clone https://github.com/orzuk/Authomathics
cd Authomathics/src
```

### Prerequisites

- Python 3.8+
- `pip install matplotlib networkx` (for visualization)
- Optional: `pip install huggingface_hub` (for LLM extraction via HuggingFace)

---

## Knowledge Graph Extraction & Evaluation

### Validate annotations

Check that a JSON annotation is structurally correct (DAG property, required fields, edge references):

```bash
# Single file
python validate_annotation.py annotation.json

# Entire directory
python validate_annotation.py papers/gold/

# Glob pattern
python validate_annotation.py 'papers/gold/paper*.json'
```

### Visualize annotations

Generate PNG DAG images:

```bash
python visualize_annotation.py papers/gold/
```

Generate interactive HTML (with foundation graph links, click-to-expand detail panel):

```bash
# Both PNG + HTML
python visualize_annotation.py --html papers/gold/

# HTML only (faster, no PNG)
python visualize_annotation.py --html-only papers/gold/
```

### Link to foundation knowledge

Find connections between paper nodes and well-known mathematical results:

```bash
python link_to_foundation.py --paper-json paper1_gold.json --output paper1_linked.json
```

### Evaluate extraction quality

Compare an extracted JSON against a gold standard:

```bash
python evaluate_extraction.py --extracted output.json --gold gold.json
python evaluate_extraction.py --extracted output.json --gold gold.json --node-sim-threshold 0.7
python evaluate_extraction.py --extracted output.json --gold gold.json --flipped-edge-credit 0.5
```

**Flags:**
- `--node-sim-threshold` (default: 0.5) — minimum Jaccard similarity between node texts to count as a match
- `--flipped-edge-credit` (default: 0.5) — partial credit for edges with correct endpoints but reversed direction

### Run full evaluation pipeline

Evaluate an extractor across all documents and models:

```bash
cd class_52017/instructor_only

# Single extractor
python run_evaluation.py --extractor ../cluster_package/scripts/annotate_chapter.py --doc-type both --split both

# See all options
python run_evaluation.py --help
```

### Batch evaluation (compare extractors + students)

```bash
# Compare baseline vs solution
python run_all_evaluations.py \
  --extractors baseline:../cluster_package/scripts/annotate_chapter.py \
               solution:annotate_chapter_solution.py

# Add student submissions
python run_all_evaluations.py \
  --extractors baseline:../cluster_package/scripts/annotate_chapter.py \
  --students-dir ../StudentsSolutions

# Students only, papers, test split
python run_all_evaluations.py \
  --students-dir ../StudentsSolutions \
  --doc-type papers --split test
```

**Student directory structure:**
```
StudentsSolutions/
  john_doe_02345134/
    annotate_chapter_student.py
  jane_smith_98765432/
    annotate_chapter_student.py
```

Output: per-extractor CSVs + combined `all_results.csv` + printed leaderboard.

---

## ArXiv Data Extraction

Fetch metadata, PDFs, LaTeX source, and HTML abstracts from arXiv:

```bash
# Single paper
python extract_arxiv_data.py --id '2309.00543v1' --formats metadata pdf html source --verbose

# Multiple papers by date range and category
python extract_arxiv_data.py --start 2023-09-01 --end 2023-09-01 --category stat.ML --formats metadata source --output-dir out --verbose
```

### Configuration

Create a `config.py` file in `src/`:

```python
import sys
if 'win' in sys.platform:
    DATA_DIR = 'C:/Datasets/arxiv_data'
else:
    DATA_DIR = '/path/to/arxiv_data'
```

### Windows/PyCharm mode

When run on Windows without arguments, the script runs a built-in example:

```bash
python extract_arxiv_data.py
```

### SLURM integration

See `scripts/fetch_arxiv_papers_metadata.sh` for a batch job example.

---

## Project Structure

```
src/
  extract_arxiv_data.py        # ArXiv data fetcher
  validate_annotation.py       # JSON validation
  visualize_annotation.py      # PNG/SVG/HTML DAG visualization
  link_to_foundation.py        # Foundation knowledge linker
  evaluate_extraction.py       # Gold standard evaluation
  foundation_linker.py         # OOP foundation linker (NaturalProofs, Mathlib)
  math_classes.py              # Data model (PaperGraph, Relation, Concept)

class_52017/
  instructor_only/
    run_evaluation.py           # Single-extractor evaluation pipeline
    run_all_evaluations.py      # Batch evaluation + leaderboard
    annotate_chapter_solution.py # Instructor solution extractor
  cluster_package/
    scripts/                    # Student-facing scripts
    papers/gold/                # Gold standard JSONs for 20 papers
    chapters/                   # Textbook chapter .tex files
```
