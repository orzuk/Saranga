"""
Post-process Mathpix LaTeX output to:
1. Add proper theorem environments (\\begin{theorem}, etc.)
2. Split into per-chapter files (chapter1.tex, chapter2.tex, ...)
3. Extract bibliographic notes into separate files

Mathpix OCR produces plain text like:
    Theorem 2.1 (Markov's inequality) Let $x$ be ...
    Proof: ...

This script converts to proper LaTeX:
    \\begin{theorem}[Markov's inequality]\\label{thm:2.1}
    Let $x$ be ...
    \\end{theorem}
    \\begin{proof}
    ...
    \\end{proof}

Usage:
    # Single file, add theorem environments:
    python mathpix_to_thm_env.py input.tex output.tex --preamble

    # Split into chapters with theorem environments:
    python mathpix_to_thm_env.py input.tex --split-chapters --output-dir ./chapters/

    # Full pipeline (theorem envs + split + bib extraction):
    python mathpix_to_thm_env.py input.tex --split-chapters --extract-bib --output-dir ./chapters/ --preamble
"""

import re
import sys
import os
import shutil
import argparse
from pathlib import Path
from typing import Optional


# ============================================================================
# Pattern definitions
# ============================================================================

# Environment types we recognize, in order of matching priority.
ENV_TYPES = [
    ("theorem",     "thm",  r'^Theorem\s+(\d+(?:\.\d+)*)\s*(?:\(([^)]+)\))?\s*(.*)'),
    ("lemma",       "lem",  r'^Lemma\s+(\d+(?:\.\d+)*)\s*(?:\(([^)]+)\))?\s*(.*)'),
    ("corollary",   "cor",  r'^Corollary\s+(\d+(?:\.\d+)*)\s*(?:\(([^)]+)\))?\s*(.*)'),
    ("proposition", "prop", r'^Proposition\s+(\d+(?:\.\d+)*)\s*(?:\(([^)]+)\))?\s*(.*)'),
    ("definition",  "def",  r'^Definition\s+(\d+(?:\.\d+)*)\s*(?:\(([^)]+)\))?\s*(.*)'),
    ("claim",       "clm",  r'^Claim\s+(\d+(?:\.\d+)*)\s*(?:\(([^)]+)\))?\s*(.*)'),
    ("conjecture",  "conj", r'^Conjecture\s+(\d+(?:\.\d+)*)\s*(?:\(([^)]+)\))?\s*(.*)'),
    ("example",     "ex",   r'^Example\s+(\d+(?:\.\d+)*)\s*(?:\(([^)]+)\))?\s*(.*)'),
    ("remark",      "rem",  r'^Remark\s+(\d+(?:\.\d+)*)\s*(?:\(([^)]+)\))?\s*(.*)'),
]

PROOF_PATTERN = re.compile(r'^Proof[.:]?\s*(.*)', re.DOTALL)
QED_PATTERN = re.compile(r'\\?\(?\\square\\?\)?|□|∎|\\qed|\\blacksquare')
SECTION_PATTERN = re.compile(r'^\\(section|subsection|subsubsection)\*?\{')
ENV_START_PATTERN = re.compile(
    r'^(Theorem|Lemma|Corollary|Proposition|Definition|Claim|Conjecture|Example|Remark)\s+\d',
    re.IGNORECASE
)
UNNUMBERED_REMARK_PATTERN = re.compile(
    r'^(Remark|Note|Observation|Discussion)[.:]', re.IGNORECASE
)
END_DOCUMENT_PATTERN = re.compile(r'^\\end\{document\}')

# Chapter boundary: \section*{N ...} where N is 1-12 (real chapter numbers)
CHAPTER_PATTERN = re.compile(r'^\\section\*\{(\d{1,2})\s+(.+)\}')

# Bibliographic notes subsection
BIB_NOTES_PATTERN = re.compile(r'^\\subsection\*\{\d+\.\d+\s+Bibliographic\s+Notes\}', re.IGNORECASE)

# Exercises subsection
EXERCISES_PATTERN = re.compile(r'^\\subsection\*\{\d+\.\d+\s+Exercises?\}', re.IGNORECASE)


# ============================================================================
# Theorem environment transformation
# ============================================================================

def classify_line(line: str) -> Optional[dict]:
    """Classify a line as the start of a theorem-like environment, proof, or None."""
    stripped = line.strip()

    for env_name, label_prefix, pattern in ENV_TYPES:
        m = re.match(pattern, stripped)
        if m:
            number = m.group(1)
            name = m.group(2)
            rest = m.group(3).strip()
            rest = re.sub(r'\\\\$', '', rest).strip()
            after_env = None
            if '\\\\' in rest:
                parts = rest.split('\\\\', 1)
                rest = parts[0].strip()
                after_env = parts[1].strip() if parts[1].strip() else None
            return {
                'type': 'env',
                'env_name': env_name,
                'label_prefix': label_prefix,
                'number': number,
                'name': name,
                'rest': rest,
                'after_env': after_env,
            }

    m = PROOF_PATTERN.match(stripped)
    if m:
        return {'type': 'proof', 'rest': m.group(1).strip()}

    return None


def is_block_boundary(line: str) -> bool:
    """Check if a line starts a new section, theorem-like block, or end of document."""
    stripped = line.strip()
    if SECTION_PATTERN.match(stripped):
        return True
    if ENV_START_PATTERN.match(stripped):
        return True
    if PROOF_PATTERN.match(stripped):
        return True
    if UNNUMBERED_REMARK_PATTERN.match(stripped):
        return True
    if END_DOCUMENT_PATTERN.match(stripped):
        return True
    return False


def transform_tex(input_text: str) -> str:
    """Transform Mathpix LaTeX output to use proper theorem environments."""
    lines = input_text.split('\n')
    output = []
    i = 0
    in_env = None
    in_proof = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        classification = classify_line(stripped)

        # Close any open env/proof at boundaries
        if classification is not None or (is_block_boundary(stripped) and not classification):
            if in_proof:
                output.append('\\end{proof}')
                output.append('')
                in_proof = False
            if in_env:
                output.append('\\end{' + in_env + '}')
                output.append('')
                in_env = None

        # New environment
        if classification and classification['type'] == 'env':
            info = classification
            env = info['env_name']
            num = info['number']
            name = info['name']
            rest = info['rest']
            after_env = info.get('after_env')

            begin_line = '\\begin{' + env + '}'
            if name:
                begin_line += '[' + name + ']'
            begin_line += '\\label{' + info['label_prefix'] + ':' + num + '}'

            output.append(begin_line)
            if rest:
                output.append(rest)
            in_env = env

            if after_env:
                output.append('\\end{' + env + '}')
                output.append('')
                output.append(after_env)
                in_env = None

            i += 1
            continue

        # Proof start
        if classification and classification['type'] == 'proof':
            rest = classification['rest']
            output.append('\\begin{proof}')
            if rest:
                output.append(rest)
            in_proof = True
            i += 1
            continue

        # QED marker inside proof
        if in_proof and QED_PATTERN.search(stripped):
            cleaned = QED_PATTERN.sub('', line).rstrip()
            if cleaned.strip():
                output.append(cleaned)
            output.append('\\end{proof}')
            output.append('')
            in_proof = False
            i += 1
            continue

        # Regular line
        output.append(line)
        i += 1

    # Close any remaining open environments
    if in_proof:
        output.append('\\end{proof}')
    if in_env:
        output.append('\\end{' + in_env + '}')

    return '\n'.join(output)


# ============================================================================
# Preamble
# ============================================================================

THEOREM_PREAMBLE = r"""
%% Theorem environments (auto-generated by mathpix_to_thm_env.py)
\usepackage{amsthm}

\theoremstyle{plain}
\newtheorem{theorem}{Theorem}[section]
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{corollary}[theorem]{Corollary}
\newtheorem{proposition}[theorem]{Proposition}
\newtheorem{claim}[theorem]{Claim}
\newtheorem{conjecture}[theorem]{Conjecture}

\theoremstyle{definition}
\newtheorem{definition}[theorem]{Definition}
\newtheorem{example}[theorem]{Example}

\theoremstyle{remark}
\newtheorem{remark}[theorem]{Remark}
"""


def inject_preamble(tex: str) -> str:
    """Add \\newtheorem declarations before \\begin{document}."""
    if '\\begin{document}' in tex:
        if '\\usepackage{amsthm}' in tex:
            preamble = THEOREM_PREAMBLE.replace('\\usepackage{amsthm}\n', '')
        else:
            preamble = THEOREM_PREAMBLE
        tex = tex.replace('\\begin{document}', preamble + '\n\\begin{document}')
    return tex


def fix_preamble_packages(tex: str) -> str:
    """Comment out packages that Mathpix adds but may not be installed."""
    # bbold is rarely installed and often not actually used in the document
    tex = tex.replace('\\usepackage{bbold}',
                       '%\\usepackage{bbold} % commented out: often not installed')
    return tex


def get_preamble_and_body(tex: str):
    """Split tex into preamble (up to and including \\begin{document}) and body+postamble."""
    marker = '\\begin{document}'
    idx = tex.find(marker)
    if idx == -1:
        return '', tex
    split_point = idx + len(marker)
    return tex[:split_point], tex[split_point:]


# ============================================================================
# Chapter splitting
# ============================================================================

def find_chapter_boundaries(lines: list) -> list:
    """
    Find line indices where real chapters begin.
    Returns list of (line_index, chapter_number, chapter_title).
    Only matches \\section*{N Title} where N is a 1-2 digit number.
    Filters out spurious matches (e.g., numbered list items promoted to sections).
    """
    boundaries = []
    for i, line in enumerate(lines):
        m = CHAPTER_PATTERN.match(line.strip())
        if m:
            ch_num = int(m.group(1))
            ch_title = m.group(2).rstrip('}').strip()
            # Filter: real chapters are numbered 1-12 for BHK book
            # and title should be a real chapter title (not a numbered list item)
            if 1 <= ch_num <= 20 and len(ch_title) > 3:
                # Extra check: title shouldn't start with punctuation or math
                if not ch_title.startswith(('$', '\\', '.', ',')):
                    boundaries.append((i, ch_num, ch_title))
    return boundaries


def extract_bib_notes(chapter_lines: list) -> tuple:
    """
    Extract bibliographic notes from a chapter's lines.
    Returns (lines_without_bib, bib_lines).
    """
    bib_start = None
    bib_end = None

    for i, line in enumerate(chapter_lines):
        if BIB_NOTES_PATTERN.match(line.strip()):
            bib_start = i
        elif bib_start is not None and EXERCISES_PATTERN.match(line.strip()):
            bib_end = i
            break
        elif bib_start is not None and CHAPTER_PATTERN.match(line.strip()):
            bib_end = i
            break

    if bib_start is None:
        return chapter_lines, []

    if bib_end is None:
        # Bib notes run to end of chapter
        bib_end = len(chapter_lines)

    bib_lines = chapter_lines[bib_start:bib_end]
    remaining = chapter_lines[:bib_start] + chapter_lines[bib_end:]
    return remaining, bib_lines


def split_into_chapters(tex: str, output_dir: str, extract_bib: bool = False,
                        images_src_dir: str = None) -> list:
    """
    Split full-book .tex into per-chapter files.

    Returns list of (chapter_number, chapter_title, filename) tuples.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Set up images directory in output
    images_dst = os.path.join(output_dir, 'images')
    if images_src_dir and os.path.isdir(images_src_dir) and not os.path.exists(images_dst):
        os.makedirs(images_dst, exist_ok=True)
        for img_file in os.listdir(images_src_dir):
            src = os.path.join(images_src_dir, img_file)
            dst = os.path.join(images_dst, img_file)
            if os.path.isfile(src):
                shutil.copyfile(src, dst)

    preamble, body = get_preamble_and_body(tex)

    # Remove \end{document} from body, we'll add it per-chapter
    body = body.replace('\\end{document}', '').rstrip()

    body_lines = body.split('\n')
    boundaries = find_chapter_boundaries(body_lines)

    if not boundaries:
        print("WARNING: No chapter boundaries found!")
        return []

    chapters = []

    # Content before first chapter (TOC, front matter)
    if boundaries[0][0] > 0:
        front_lines = body_lines[:boundaries[0][0]]
        if any(l.strip() for l in front_lines):
            fname = os.path.join(output_dir, 'front_matter.tex')
            with open(fname, 'w', encoding='utf-8') as f:
                f.write(preamble + '\n')
                f.write('\n'.join(front_lines))
                f.write('\n\\end{document}\n')
            chapters.append((0, 'Front Matter', fname))

    # Each chapter
    for idx, (start_line, ch_num, ch_title) in enumerate(boundaries):
        # End of this chapter = start of next chapter, or end of body
        if idx + 1 < len(boundaries):
            end_line = boundaries[idx + 1][0]
        else:
            end_line = len(body_lines)

        ch_lines = body_lines[start_line:end_line]

        # Extract bib notes if requested
        bib_lines = []
        if extract_bib:
            ch_lines, bib_lines = extract_bib_notes(ch_lines)

        # Write chapter file
        fname = os.path.join(output_dir, f'chapter{ch_num}.tex')
        with open(fname, 'w', encoding='utf-8') as f:
            f.write(preamble + '\n')
            f.write('\n'.join(ch_lines))
            f.write('\n\\end{document}\n')
        chapters.append((ch_num, ch_title, fname))

        # Write bib notes file
        if bib_lines:
            bib_fname = os.path.join(output_dir, f'chapter{ch_num}_bib.tex')
            with open(bib_fname, 'w', encoding='utf-8') as f:
                f.write(f'% Bibliographic notes for Chapter {ch_num}: {ch_title}\n')
                f.write('\n'.join(bib_lines))
            print(f"    Bib notes: {bib_fname}")

    return chapters


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Post-process Mathpix LaTeX: add theorem envs, split chapters, extract bib.'
    )
    parser.add_argument('input', help='Input .tex file (Mathpix output)')
    parser.add_argument('output', help='Output .tex file (single-file mode)', nargs='?', default=None)
    parser.add_argument('--preamble', action='store_true',
                        help='Add \\newtheorem declarations to preamble')
    parser.add_argument('--split-chapters', action='store_true',
                        help='Split output into per-chapter files')
    parser.add_argument('--extract-bib', action='store_true',
                        help='Extract bibliographic notes to separate files')
    parser.add_argument('--output-dir', default='./chapters',
                        help='Output directory for chapter files')
    parser.add_argument('--images-dir', default=None,
                        help='Path to images directory (copied to output-dir)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print to stdout instead of writing files')

    args = parser.parse_args()

    # Read input
    with open(args.input, 'r', encoding='utf-8') as f:
        tex = f.read()

    print(f"Read {len(tex)} chars from {args.input}")

    # Auto-detect images directory
    images_dir = args.images_dir
    if images_dir is None:
        candidate = os.path.join(os.path.dirname(args.input), 'images')
        if os.path.isdir(candidate):
            images_dir = candidate
            print(f"Auto-detected images dir: {images_dir}")

    # Step 0: Fix preamble packages
    tex = fix_preamble_packages(tex)

    # Step 1: Add theorem environments
    tex = transform_tex(tex)
    print("Added theorem environments.")

    # Count what was found
    for env_name in ['theorem', 'lemma', 'corollary', 'proposition', 'definition',
                     'claim', 'conjecture', 'proof']:
        count = tex.count(f'\\begin{{{env_name}}}')
        if count > 0:
            print(f"  {env_name}: {count}")

    # Step 2: Inject preamble
    if args.preamble:
        tex = inject_preamble(tex)
        print("Injected theorem preamble.")

    # Step 3: Output
    if args.split_chapters:
        chapters = split_into_chapters(
            tex, args.output_dir,
            extract_bib=args.extract_bib,
            images_src_dir=images_dir
        )
        print(f"\nSplit into {len(chapters)} files in {args.output_dir}/:")
        for ch_num, ch_title, fname in chapters:
            print(f"  Chapter {ch_num:2d}: {ch_title[:50]:50s} -> {os.path.basename(fname)}")

    elif args.dry_run:
        print(tex)

    else:
        out_path = args.output or args.input.replace('.tex', '_thm.tex')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(tex)
        print(f"\nWrote: {out_path}")


if __name__ == '__main__':
    main()
