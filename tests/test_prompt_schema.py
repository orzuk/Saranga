"""The v6 and v7 extraction prompts must agree with the schema they describe.

Runs without pytest:  python3 tests/test_prompt_schema.py

Checks the prompt's node-ID table against node_types.ID_PREFIX (every type,
the same prefix), and that the prompt renders with no placeholder or
maintainer comment left over.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

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

if FAILS:
    print("\n".join(FAILS))
    sys.exit(1)
print("prompt and schema agree")
