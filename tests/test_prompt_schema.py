"""The v6 and v7 extraction prompts must agree with the schema they describe.

Runs without pytest:  python3 tests/test_prompt_schema.py

Checks the prompt's node-ID table against node_types.ID_PREFIX (every type,
the same prefix), and that the prompt renders with no placeholder or
maintainer comment left over. For v7, also every vocabulary the prompt spells out:
proof_strategy, step subclasses, edge basis, paper_style, note categories, cycle kinds.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import edge_types as ET  # noqa: E402
import extraction_finalize as F  # noqa: E402
import node_types as NT  # noqa: E402
from schema_for_prompts import render_prompt  # noqa: E402

FAILS = []
for version in ("v6", "v7"):
    PROMPT = (ROOT / "scripts" / f"opus_extract_prompt_{version}.md").read_text(encoding="utf-8")
    ROWS = re.findall(r"^\| ([a-z_]+) \| ([A-Za-z]+) \| ([A-Za-z]+\d+) \|$", PROMPT, re.M)
    table = {t: p for t, p, _ in ROWS}
    if table != NT.ID_PREFIX:
        FAILS.append(f"{version}: prompt ID table differs from node_types.ID_PREFIX:\n  prompt {table}\n  schema {NT.ID_PREFIX}")
    for t, p, ex in ROWS:
        if ex != f"{p}1":
            FAILS.append(f"{version}: example ID for {t} is {ex}, expected {p}1")
    rendered = render_prompt(PROMPT)
    if "{{" in rendered or "<!--" in rendered:
        FAILS.append(f"{version}: rendered prompt still has a {{{{...}}}} placeholder or a <!-- comment -->")

V7 = (ROOT / "scripts" / "opus_extract_prompt_v7.md").read_text(encoding="utf-8")


def words(text):
    return set(re.findall(r"[a-z_]+", text))


alg = V7[V7.index("- algorithm_step — choose"):V7.index("### When to emit a `proof_step`")]
vocab = {
    "proof_strategy": (words(re.search(r"`(induction,[^`]*)`", V7).group(1)), NT.PROOF_STRATEGY_VALUES),
    "proof_step subclass": (words(re.search(r"- proof_step: `([^`]*)`", V7).group(1)),
                            set(NT.SUBCLASS_VALUES["proof_step"])),
    "algorithm_step subclass": (set(re.findall(r"`([a-z_]+)` [a-z]", alg)), set(NT.SUBCLASS_VALUES["algorithm_step"])),
    "edge basis": (set(re.findall(r"^\| `([a-z]+)` \| (?!when)", V7[V7.index("**Edge basis.**"):
                                                                     V7.index("**Direction.**")], re.M)),
                   set(ET.EDGE_BASIS)),
    "paper_style": (set(re.findall(r"^- `([a-z_]+)`:", V7[V7.index("`paper_style` is how"):
                                                            V7.index("`extraction_notes` is a list")], re.M)),
                    F.PAPER_STYLES),
    "note categories": (set(re.findall(r"^\| `([a-z_]+)` \| (?!when)", V7[V7.index("| `category` | when |"):
                                                                          V7.index("`extraction_comment` is")], re.M)),
                        F.NOTE_CATEGORIES),
    "cycle kinds": (set(re.findall(r"`([a-z_]+)`", re.search(r"`kind`: (`wrong_ref`[^.]*)", V7).group(1))),
                    F.CYCLE_KINDS),
}
for name, (prompt, code) in vocab.items():
    if prompt != set(code):
        FAILS.append(f"v7 {name}: prompt {sorted(prompt)} != code {sorted(code)}")

if FAILS:
    print("\n".join(FAILS))
    sys.exit(1)
print("prompt and schema agree")
