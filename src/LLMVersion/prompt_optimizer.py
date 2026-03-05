#!/usr/bin/env python3
"""
prompt_optimizer.py

Iterative prompt optimization for math definition extraction.

Each iteration:
  1. Extract definitions using current prompt
  2. Evaluate against gold standard (Jaccard P/R/F1)
  3. Analyze errors (FP/FN/near-misses)
  4. Feed errors + prompt to meta-LLM -> get improved prompt
  5. Repeat

Usage:
  python3 prompt_optimizer.py \
      --paper-id 2208.03112 \
      --provider anthropic \
      --model claude-sonnet-4-20250514 \
      --iterations 3
"""

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import FULL_PAPERS_DIR
from math_paper_parser import PaperParser
from extract_arxiv_funcs import fetch_arxiv_batch, resolve_source_to_tex_local_first
from definitions_from_json_to_csv import extract_definitions_to_csv
from add_gold_standard import add_gold_standard_to_csv
from evaluate_definitions import evaluate_definitions


class PromptOptimizer:
    def __init__(
        self,
        paper_id: str,
        provider: str,
        model: str,
        gold_csv: str = "Gold_Standard.csv",
        initial_prompt_file: str = "custom_prompt.txt",
        threshold: float = 0.7,
        max_iterations: int = 3,
        meta_provider: str = "anthropic",
        meta_model: str = "claude-sonnet-4-20250514",
        out_dir: str = ".",
        work_dir: Optional[str] = None,
    ):
        self.paper_id = paper_id
        self.provider = provider
        self.model = model
        self.gold_csv = gold_csv
        self.initial_prompt_file = initial_prompt_file
        self.threshold = threshold
        self.max_iterations = max_iterations
        self.meta_provider = meta_provider
        self.meta_model = meta_model
        self.out_dir = Path(out_dir)
        self.work_dir = Path(work_dir) if work_dir else None
        self._temp_dir = None

        self.history: List[Dict[str, Any]] = []
        self.best_f1 = -1.0
        self.best_prompt = ""
        self.best_iteration = -1

        # Read the initial prompt
        with open(self.initial_prompt_file, "r") as f:
            self.current_prompt = f.read()

        # Read gold standard examples for the meta-prompt
        self.gold_examples = self._load_gold_examples()

    def _get_work_dir(self) -> Path:
        if self.work_dir:
            self.work_dir.mkdir(parents=True, exist_ok=True)
            return self.work_dir
        if self._temp_dir is None:
            self._temp_dir = tempfile.mkdtemp(prefix="prompt_opt_")
        return Path(self._temp_dir)

    def _load_gold_examples(self) -> List[str]:
        """Load a few gold standard examples for the meta-prompt context."""
        examples = []
        try:
            with open(self.gold_csv, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                reader.fieldnames = [n.strip() for n in reader.fieldnames]
                for row in reader:
                    row = {k.strip(): v for k, v in row.items()}
                    if row.get("paper_id", "").strip() == self.paper_id:
                        text = row.get("Gold_Standard_raw_latex", "").strip()
                        if text:
                            examples.append(text)
        except FileNotFoundError:
            print(f"[WARN] Gold CSV not found: {self.gold_csv}")
        return examples

    def optimize(self) -> Tuple[str, List[Dict[str, Any]]]:
        """Run the optimization loop. Returns (best_prompt_text, history)."""
        print(f"\n{'='*60}")
        print(f"PROMPT OPTIMIZATION")
        print(f"Paper: {self.paper_id} | Provider: {self.provider} | Model: {self.model}")
        print(f"Max iterations: {self.max_iterations} | Threshold: {self.threshold}")
        print(f"Meta-LLM: {self.meta_provider}/{self.meta_model}")
        print(f"{'='*60}\n")

        for iteration in range(self.max_iterations):
            print(f"\n--- Iteration {iteration + 1}/{self.max_iterations} ---")

            work = self._get_work_dir()
            iter_dir = work / f"iteration_{iteration}"
            iter_dir.mkdir(parents=True, exist_ok=True)

            # 1. Save current prompt
            prompt_file = iter_dir / "prompt.txt"
            prompt_file.write_text(self.current_prompt, encoding="utf-8")
            print(f"[1/5] Prompt saved to {prompt_file}")

            # 2. Run extraction
            try:
                self._run_extraction(str(prompt_file), iter_dir)
                print(f"[2/5] Extraction complete")
            except Exception as e:
                print(f"[ERROR] Extraction failed: {e}")
                self.history.append({
                    "iteration": iteration,
                    "error": f"extraction_failed: {e}",
                    "prompt": self.current_prompt,
                })
                continue

            # 3. Run postprocessing & evaluation
            try:
                metrics, detailed = self._run_postprocessing(iter_dir)
                print(f"[3/5] Evaluation: P={metrics['precision']:.3f} "
                      f"R={metrics['recall']:.3f} F1={metrics['f1']:.3f}")
            except Exception as e:
                print(f"[ERROR] Postprocessing failed: {e}")
                self.history.append({
                    "iteration": iteration,
                    "error": f"postprocessing_failed: {e}",
                    "prompt": self.current_prompt,
                })
                continue

            # 4. Build error analysis
            error_analysis = self._build_error_analysis(detailed, metrics)
            print(f"[4/5] Errors: {len(error_analysis['false_negatives'])} FN, "
                  f"{len(error_analysis['false_positives'])} FP, "
                  f"{len(error_analysis['near_misses'])} near-misses")

            # Track best
            if metrics["f1"] > self.best_f1:
                self.best_f1 = metrics["f1"]
                self.best_prompt = self.current_prompt
                self.best_iteration = iteration

            # Record history
            self.history.append({
                "iteration": iteration,
                "metrics": metrics,
                "error_counts": {
                    "false_negatives": len(error_analysis["false_negatives"]),
                    "false_positives": len(error_analysis["false_positives"]),
                    "near_misses": len(error_analysis["near_misses"]),
                },
                "prompt": self.current_prompt,
            })

            # 5. Call meta-optimizer (skip on last iteration)
            if iteration < self.max_iterations - 1:
                try:
                    improved_prompt, reasoning = self._call_meta_optimizer(
                        self.current_prompt, metrics, error_analysis
                    )
                    print(f"[5/5] Meta-optimizer reasoning: {reasoning[:100]}...")
                    self.current_prompt = improved_prompt
                except Exception as e:
                    print(f"[WARN] Meta-optimizer failed: {e}. Keeping current prompt.")

        # Save outputs
        self._save_history()
        self._save_best_prompt()

        print(f"\n{'='*60}")
        print(f"OPTIMIZATION COMPLETE")
        print(f"Best F1: {self.best_f1:.3f} (iteration {self.best_iteration + 1})")
        print(f"{'='*60}\n")

        return self.best_prompt, self.history

    def _run_extraction(self, prompt_file: str, iter_dir: Path) -> None:
        """Run definition extraction for the paper using the given prompt."""
        regex_id = f"^{self.paper_id}"

        # Fetch metadata
        data = fetch_arxiv_batch(
            regex_id=regex_id,
            formats="metadata",
            output_dir=None,
            verbose=False,
        )

        if not data:
            raise RuntimeError(f"No papers found for {self.paper_id}")

        # Get base_id and metadata
        base_id = None
        meta = None
        for vid, entry in data.items():
            bid = vid.split("v")[0]
            if bid == self.paper_id:
                base_id = bid
                meta = entry.get("metadata", entry)
                break

        if base_id is None:
            # Take the first match
            vid, entry = next(iter(data.items()))
            base_id = vid.split("v")[0]
            meta = entry.get("metadata", entry)

        # Resolve TeX source
        tex_path, versioned_id = resolve_source_to_tex_local_first(
            base_id=base_id,
            meta=meta,
            full_papers_dir=iter_dir,
            verbose=False,
        )

        # Parse with PaperParser
        parser = PaperParser(
            paper_id=versioned_id,
            definition_mode="llm",
            llm_model=self.model,
            llm_provider=self.provider,
            custom_prompt_file=prompt_file,
        )
        graph = parser.parse_file(tex_path)

        # Save JSON in the expected directory structure
        json_dir = iter_dir / "json"
        json_dir.mkdir(parents=True, exist_ok=True)

        suffix = self.model.replace("/", "-")
        json_filename = f"{versioned_id}_{suffix}.json"
        json_path = json_dir / json_filename

        json_path.write_text(
            json.dumps(graph.to_dict(), indent=2), encoding="utf-8"
        )
        print(f"  JSON saved: {json_path}")

    def _run_postprocessing(
        self, iter_dir: Path
    ) -> Tuple[Dict[str, float], List[Dict[str, str]]]:
        """Run CSV conversion, gold merging, and evaluation. Returns (metrics, detailed)."""
        defs_csv = str(iter_dir / "definitions.csv")
        merged_csv = str(iter_dir / "merged.csv")
        summary_csv = str(iter_dir / "evaluation_results.csv")
        detailed_csv = str(iter_dir / "detailed_matches.csv")

        # Step 1: JSON -> CSV
        extract_definitions_to_csv(
            out_dir=str(iter_dir),
            paper_ids=[self.paper_id],
            output_csv=defs_csv,
        )

        # Step 2: Add gold standard
        add_gold_standard_to_csv(
            input_csv=defs_csv,
            gold_csv=self.gold_csv,
            output_csv=merged_csv,
        )

        # Step 3: Evaluate
        evaluate_definitions(
            input_csv=merged_csv,
            output_csv=summary_csv,
            detailed_csv=detailed_csv,
            threshold=self.threshold,
        )

        # Read back results
        metrics = self._read_summary_csv(summary_csv)
        detailed = self._read_detailed_csv(detailed_csv)

        return metrics, detailed

    def _read_summary_csv(self, path: str) -> Dict[str, float]:
        """Read evaluation summary CSV and return metrics for our provider."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Match our provider's model name in the provider column
                    return {
                        "precision": float(row.get("precision", 0)),
                        "recall": float(row.get("recall", 0)),
                        "f1": float(row.get("f1_score", 0)),
                        "true_positives": int(row.get("true_positives", 0)),
                        "false_positives": int(row.get("false_positives", 0)),
                        "false_negatives": int(row.get("false_negatives", 0)),
                        "num_gold": int(row.get("num_gold_standards", 0)),
                        "num_extracted": int(row.get("num_extracted", 0)),
                    }
        except FileNotFoundError:
            pass
        return {
            "precision": 0.0, "recall": 0.0, "f1": 0.0,
            "true_positives": 0, "false_positives": 0, "false_negatives": 0,
            "num_gold": 0, "num_extracted": 0,
        }

    def _read_detailed_csv(self, path: str) -> List[Dict[str, str]]:
        """Read detailed matches CSV."""
        results = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    results.append(dict(row))
        except FileNotFoundError:
            pass
        return results

    def _build_error_analysis(
        self,
        detailed_matches: List[Dict[str, str]],
        metrics: Dict[str, float],
    ) -> Dict[str, List[Dict[str, str]]]:
        """Categorize extraction errors into FP, FN, and near-misses."""
        false_positives = []
        near_misses = []
        matched_gold_indices = set()

        for row in detailed_matches:
            sim = float(row.get("similarity", 0))
            is_match = row.get("is_match", "No") == "Yes"
            def_text = row.get("definition_text", "")
            gold_text = row.get("best_match_gold_text", "")
            gold_idx = row.get("best_match_gold_index", "")

            if is_match and gold_idx:
                matched_gold_indices.add(gold_idx)
            elif sim < 0.3:
                false_positives.append({
                    "extracted": def_text[:200],
                    "best_gold": gold_text[:200],
                    "similarity": sim,
                })
            else:
                # 0.3 <= sim < threshold
                near_misses.append({
                    "extracted": def_text[:200],
                    "best_gold": gold_text[:200],
                    "similarity": sim,
                })

        # False negatives: gold examples not matched
        false_negatives = []
        for i, gold_text in enumerate(self.gold_examples):
            if str(i) not in matched_gold_indices:
                false_negatives.append({
                    "gold_index": i,
                    "gold_text": gold_text[:200],
                })

        return {
            "false_negatives": false_negatives[:3],
            "false_positives": false_positives[:3],
            "near_misses": near_misses[:3],
        }

    def _call_meta_optimizer(
        self,
        current_prompt: str,
        metrics: Dict[str, float],
        error_analysis: Dict[str, List[Dict[str, str]]],
    ) -> Tuple[str, str]:
        """Call the meta-LLM to improve the prompt based on error analysis."""
        meta_prompt = self._build_meta_prompt(current_prompt, metrics, error_analysis)

        if self.meta_provider == "anthropic":
            response_text = self._call_anthropic(meta_prompt)
        elif self.meta_provider == "openai":
            response_text = self._call_openai(meta_prompt)
        else:
            raise ValueError(f"Unsupported meta_provider: {self.meta_provider}")

        # Parse JSON response
        improved_prompt, reasoning = self._parse_meta_response(response_text)

        # Validate placeholder preserved
        if "{latex_chunk}" not in improved_prompt:
            print("[WARN] Meta-LLM removed {latex_chunk} placeholder. Restoring it.")
            improved_prompt += "\n\nLaTeX text:\n\n{latex_chunk}\n\nRespond ONLY with JSON array."

        return improved_prompt, reasoning

    def _build_meta_prompt(
        self,
        current_prompt: str,
        metrics: Dict[str, float],
        error_analysis: Dict[str, List[Dict[str, str]]],
    ) -> str:
        """Build the meta-prompt for the optimization LLM."""
        # Gold examples for context
        gold_section = ""
        if self.gold_examples:
            gold_section = "\n## Gold Standard Examples (what correct extractions look like):\n"
            for i, ex in enumerate(self.gold_examples[:2]):
                gold_section += f"\nExample {i+1} (truncated):\n{ex[:300]}\n"

        # Error examples
        fn_section = ""
        if error_analysis["false_negatives"]:
            fn_section = "\n## False Negatives (gold definitions the prompt MISSED):\n"
            for item in error_analysis["false_negatives"]:
                fn_section += f"\n- Gold def #{item['gold_index']}: {item['gold_text']}\n"

        fp_section = ""
        if error_analysis["false_positives"]:
            fp_section = "\n## False Positives (extracted but NOT real definitions, similarity < 0.3):\n"
            for item in error_analysis["false_positives"]:
                fp_section += f"\n- Extracted: {item['extracted']}\n  Best gold match (sim={item['similarity']:.2f}): {item['best_gold']}\n"

        nm_section = ""
        if error_analysis["near_misses"]:
            nm_section = f"\n## Near Misses (partially matched, 0.3 <= similarity < {self.threshold}):\n"
            for item in error_analysis["near_misses"]:
                nm_section += f"\n- Extracted: {item['extracted']}\n  Best gold match (sim={item['similarity']:.2f}): {item['best_gold']}\n"

        return f"""You are an expert prompt engineer optimizing a prompt for extracting mathematical definitions from LaTeX papers.

## Task
Improve the extraction prompt below based on the evaluation results and error analysis.

## Current Prompt:
```
{current_prompt}
```

## Evaluation Results:
- Precision: {metrics['precision']:.3f}
- Recall: {metrics['recall']:.3f}
- F1 Score: {metrics['f1']:.3f}
- True Positives: {metrics['true_positives']}
- False Positives: {metrics['false_positives']}
- False Negatives: {metrics['false_negatives']}
- Gold standard definitions: {metrics['num_gold']}
- Extracted definitions: {metrics['num_extracted']}

## Evaluation Method:
Definitions are compared using Jaccard similarity on tokenized, normalized LaTeX text.
A match is counted when similarity >= {self.threshold}.
Tokens include LaTeX commands (\\command), words, numbers, and symbols.
{gold_section}{fn_section}{fp_section}{nm_section}

## Instructions:
1. Analyze why the current prompt produces false positives and misses gold definitions.
2. The main issue is typically that the LLM extracts isolated equations/formulas rather than full definitional passages with surrounding context.
3. Gold standard definitions include the FULL passage: the introductory text ("We define...", "Let X be..."), the mathematical formula, AND any explanatory text.
4. Improve the prompt to better capture complete definitional passages.
5. The improved prompt MUST contain the placeholder {{latex_chunk}} exactly as written.
6. The improved prompt must ask for JSON array output with fields: name, raw_latex, clean_text, label.

Respond with a JSON object (and nothing else):
{{
  "reasoning": "Brief explanation of what you changed and why",
  "improved_prompt": "The full improved prompt text"
}}"""

    def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic API for meta-optimization."""
        import anthropic

        client = anthropic.Anthropic()
        message = client.messages.create(
            model=self.meta_model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API for meta-optimization."""
        from openai import OpenAI

        client = OpenAI()
        response = client.chat.completions.create(
            model=self.meta_model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    def _parse_meta_response(self, response_text: str) -> Tuple[str, str]:
        """Parse the meta-LLM JSON response. Returns (improved_prompt, reasoning)."""
        # Try to extract JSON from the response
        text = response_text.strip()

        # Handle markdown code blocks
        if text.startswith("```"):
            # Remove ```json and ``` wrappers
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            parsed = json.loads(text)
            improved = parsed.get("improved_prompt", "")
            reasoning = parsed.get("reasoning", "")
            if improved:
                return improved, reasoning
        except json.JSONDecodeError:
            pass

        # Fallback: try to find JSON in the response
        json_match = None
        brace_depth = 0
        start = None
        for i, ch in enumerate(response_text):
            if ch == "{" and brace_depth == 0:
                start = i
            if ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
                if brace_depth == 0 and start is not None:
                    json_match = response_text[start : i + 1]
                    break

        if json_match:
            try:
                parsed = json.loads(json_match)
                improved = parsed.get("improved_prompt", "")
                reasoning = parsed.get("reasoning", "")
                if improved:
                    return improved, reasoning
            except json.JSONDecodeError:
                pass

        # Last resort: return current prompt unchanged
        print("[WARN] Could not parse meta-LLM response. Keeping current prompt.")
        return self.current_prompt, "parse_error"

    def _save_history(self) -> None:
        """Save optimization history to JSON."""
        history_path = self.out_dir / "optimization_history.json"
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "paper_id": self.paper_id,
                    "provider": self.provider,
                    "model": self.model,
                    "threshold": self.threshold,
                    "meta_provider": self.meta_provider,
                    "meta_model": self.meta_model,
                    "best_iteration": self.best_iteration,
                    "best_f1": self.best_f1,
                    "iterations": self.history,
                },
                f,
                indent=2,
            )
        print(f"History saved to {history_path}")

    def _save_best_prompt(self) -> None:
        """Save the best prompt to a file."""
        if not self.best_prompt:
            return
        prompt_path = self.out_dir / f"optimized_prompt_{self.provider}.txt"
        prompt_path.write_text(self.best_prompt, encoding="utf-8")
        print(f"Best prompt saved to {prompt_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Iterative prompt optimization for math definition extraction"
    )
    parser.add_argument(
        "--paper-id", type=str, required=True, help="ArXiv paper ID"
    )
    parser.add_argument(
        "--provider",
        type=str,
        required=True,
        choices=["anthropic", "openai", "huggingface"],
        help="LLM provider for extraction",
    )
    parser.add_argument(
        "--model", type=str, required=True, help="Model name for extraction"
    )
    parser.add_argument(
        "--gold-csv",
        type=str,
        default="Gold_Standard.csv",
        help="Gold standard CSV path",
    )
    parser.add_argument(
        "--initial-prompt",
        type=str,
        default="custom_prompt.txt",
        help="Initial prompt template file",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of optimization iterations",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.7,
        help="Jaccard similarity threshold for matching",
    )
    parser.add_argument(
        "--meta-provider",
        type=str,
        default="anthropic",
        choices=["anthropic", "openai"],
        help="LLM provider for meta-optimization",
    )
    parser.add_argument(
        "--meta-model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="Model for meta-optimization",
    )
    parser.add_argument(
        "--out-dir", type=str, default=".", help="Output directory"
    )
    parser.add_argument(
        "--work-dir",
        type=str,
        default=None,
        help="Working directory for iteration data (default: auto temp dir)",
    )

    args = parser.parse_args()

    optimizer = PromptOptimizer(
        paper_id=args.paper_id,
        provider=args.provider,
        model=args.model,
        gold_csv=args.gold_csv,
        initial_prompt_file=args.initial_prompt,
        threshold=args.threshold,
        max_iterations=args.iterations,
        meta_provider=args.meta_provider,
        meta_model=args.meta_model,
        out_dir=args.out_dir,
        work_dir=args.work_dir,
    )

    best_prompt, history = optimizer.optimize()


if __name__ == "__main__":
    main()
