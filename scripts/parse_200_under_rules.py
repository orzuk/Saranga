#!/usr/bin/env python3
"""Run parse_batch over the staged corpus under a CHOSEN rule set.

parse_batch reads whatever happens to be symlinked into src/LLMVersion/*_eval/,
which makes "which rules produced these JSONs?" a question about ambient state
rather than about the command. This wraps the batch in `installed_rules()`, so
the rule set is an argument and is restored afterwards on every exit path --
including a crash, which hand-editing the symlinks does not give you.

Usage:
    python scripts/parse_200_under_rules.py \
        --eval-dir src/LLMVersion/merged_eval_v51_train60_v2/snapshots/step_40_1302.1114v2 \
        --tex-dir corpus/silver/tex_staged \
        --out-dir src/LLMVersion/parsed_v51_200_step40
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "LLMVersion"))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from silver_distillation_merged import FNAME_MAP, installed_rules


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-dir", required=True,
                    help="dir holding the distilled_rules.py importer to install")
    ap.add_argument("--tex-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--safeguard", type=int, default=0)
    args = ap.parse_args()

    types = list(FNAME_MAP.keys())
    eval_dir = Path(args.eval_dir).resolve()
    if not (eval_dir / "distilled_rules.py").exists():
        sys.exit(f"no distilled_rules.py in {eval_dir}")

    import parse_batch
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    print(f"[wrap] installing rules from {eval_dir}")
    with installed_rules(eval_dir, types):
        parse_batch.run_batch(
            start_date=None, end_date=None, category=None, regex_id=None,
            top_k=0, out_dir=out, draw_graphs=False, verbose=False,
            extraction_mode="rules", llm_model=None, llm_chunk_chars=30000,
            llm_provider="anthropic", prompt_file=None,
            structure_types=types, tex_dir=args.tex_dir,
            safeguard_timeout=(args.safeguard or None),
        )
    print(f"[wrap] rules restored; JSONs in {out/'json'}")


if __name__ == "__main__":
    main()
