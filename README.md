# Authomatics

Scripts and code for downloading and parsing arXiv papers meta-data and data, and representing and connecting between different mathematical concepts

## ArXiv Data Extraction

The script **`extract_arxiv_data.py`** can: 

* **List and cache** all ArXiv IDs via OAI‑PMH
* **Fetch** metadata, PDFs, LaTeX source, and HTML abstracts for ArXiv papers

The script adapts automatically to your environment:

1. **Command‑line mode (Linux/Unix/SLURM)**

   * Use subcommands and flags to list IDs or fetch papers.
2. **Example mode (Windows/PyCharm)**

   * When run on Windows, it executes a built‑in example for a single paper ID.

---

### Prerequisites

* Python 3.6+
* No external dependencies (uses only Python standard library).
* A `config.py` file defining `DATA_DIR` (the cache directory).

Example `config.py`:

```python
# config.py
import sys
if 'win' in sys.platform:
    DATA_DIR = 'C:/Datasets/big_data_project_52017/arxiv_data'
else:
    DATA_DIR = '/path/to/arxiv_data'
```

---

### Installation

1. Clone this repo:

   ```bash
   ```

git clone https://github.com/orzuk/Authomathics

cd Authomathics/src

````
2. Ensure `extract_arxiv_data.py` is executable (on Unix):
```bash
chmod +x extract_arxiv_data.py
````

3. Create or update `config.py` next to the script.

---

### Usage: Command‑line Mode


#### 1. Fetch paper data

Fetch one paper by its id: 

```bash
./python extract_arxiv_data.py --id '2309.00543v1' --formats metadata pdf html source --verbose


* `--what`:

  * `metadata`: title, abstract, authors, categories, published date, ...
  * `pdf`: raw PDF bytes
  * `html`: html file
  * `source`: LaTeX source `.tex` file

The script prints:


```text
>>> filter_ids_by_regex: loaded 2744465 IDs
>>> filter_ids_by_regex: 1 bases, 1 versioned IDs
[DEBUG] 1 base IDs, 1 versioned IDs to process
[DEBUG] Fetching metadata for all versioned IDs via local JSONL + HDF5 offsets…
[fetch_arxiv_metadata] Loaded metadata for '2309.00543v1' (offset=3299592092)
[DEBUG] Processing 2309.00543v1 for formats: ['html', 'source', 'pdf', 'metadata']
[DEBUG] Downloading html for 2309.00543v1 from https://arxiv.org/abs/2309.00543v1
[DEBUG] Downloading source for 2309.00543v1 from https://arxiv.org/e-print/2309.00543v1
[DEBUG] Downloading pdf for 2309.00543v1 from https://arxiv.org/pdf/2309.00543v1.pdf
=== 2309.00543v1 ===
Title: Curating Naturally Adversarial Datasets for Learning-Enabled Medical
  Cyber-Physical Systems
Authors: S, y, d, n, e, y,  , P, u, g, h, ,,  , I, v, a, n,  , R, u, c, h, k, i, n, ,,  , I, n, s, u, p,  , L, e, e, ,,  , J, a, m, e, s,  , W, e, i, m, e, r
Abstract (first 3 lines):
     Deep learning models have shown promising predictive accuracy for time-series
   healthcare applications. However, ensuring the robustness of these models is
   vital for building trustworthy AI systems. Existing research predominantly
PDF (first 50 bytes):
b'%PDF-1.5\n%\x8f\n12 0 obj\n<< /Filter /FlateDecode /Leng'

HTML (first 5 lines):
   <!DOCTYPE html>
   <html lang="en">

   <head>  <title>[2309.00543v1] Curating Naturally Adversarial Datasets for Trustworthy AI in Healthcare</title>
     <meta name="viewport" content="width=device-width, initial-scale=1">

LaTeX source (first 5 lines):
   %File: anonymous-submission-latex-2024.tex
   \documentclass[letterpaper]{article} % DO NOT CHANGE THIS
   \usepackage{aaai24}  % DO NOT CHANGE THIS
   \usepackage{times}  % DO NOT CHANGE THIS
   \usepackage{helvet}  % DO NOT CHANGE THIS
```


Fetch multiple papers by dates, categories ...
```bash
./python extract_arxiv_data.py --start 2023-09-01 --end   2023-09-01 --category stat.ML --formats metadata pdf html source --output-dir out --verbose


---

### Usage: Example Mode (Windows/PyCharm)

When run on Windows (detected via `sys.platform`), the script automatically:

1. Downloads **metadata** for `2104.00001v1`, prints the Python `dict` with its fields.
2. Downloads **LaTeX source**, lists `.tex` files, and prints the first 5 lines.
3. Downloads **PDF**, prints its type, size, and header bytes.
4. Fetches the **HTML** abstract page and prints the first 5 lines of the HTML.

```bash
# Simply run:
python extract_arxiv_data.py
```

You’ll see output such as:

```
=== Example mode: processing 2104.00001v1 ===
[METADATA] Format: Python dict with fields:
  id: 2104.00001v1
  title: …
  abstract: …
[SOURCE] bytes type: <class 'bytes'> size: 209439
First five lines of ms_v1.tex
\documentclass{article}
…
[PDF] bytes type: <class 'bytes'> size: 437388
PDF header bytes: b'%PDF-1.4'…
# [HTML] Fetched HTML page, first five lines:
<!DOCTYPE html>
<html lang="en">
…
```

---

### Integration with SLURM

See usage example in the scripts directory   **`fetch_arxiv_papers_metadata.sh`**:
You may change the filter, format etc. 


---

