#!/usr/bin/env python3
"""
prompt_optimizer.py

Iterative prompt optimization for math structure extraction.

Each iteration:
  1. Extract structures using current prompt
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
import glob as globmod
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import FULL_PAPERS_DIR
from math_paper_parser import PaperParser, STRUCTURE_TYPE_CONFIG
from extract_arxiv_funcs import fetch_arxiv_batch, resolve_source_to_tex_local_first
from definitions_from_json_to_csv import extract_definitions_to_csv
from add_gold_standard import add_gold_standard_to_csv
from evaluate_definitions import evaluate_definitions


class PromptOptimizer:
    def __init__(
        self,
        paper_id: Optional[str] = None,
        provider: str = "anthropic",
        model: str = "claude-sonnet-4-20250514",
        gold_csv: str = "Gold_Standard.csv",
        initial_prompt_file: str = "custom_prompt.txt",
        threshold: float = 0.7,
        max_iterations: int = 3,
        meta_provider: str = "anthropic",
        meta_model: str = "claude-sonnet-4-20250514",
        out_dir: str = ".",
        work_dir: Optional[str] = None,
        structure_type: str = "definition",
        train_paper_ids: Optional[List[str]] = None,
        val_paper_ids: Optional[List[str]] = None,
    ):
        # Resolve train/val paper lists (backward compat with paper_id)
        if train_paper_ids:
            self.train_paper_ids = train_paper_ids
        elif paper_id:
            self.train_paper_ids = [paper_id]
        else:
            raise ValueError("Must provide either paper_id or train_paper_ids")
        self.val_paper_ids = val_paper_ids or []
        # Keep paper_id for backward compat (first train paper)
        self.paper_id = self.train_paper_ids[0]

        self.provider = provider
        self.model = model
        self.gold_csv = gold_csv
        self.initial_prompt_file = initial_prompt_file
        self.threshold = threshold
        self.max_iterations = max_iterations
        self.meta_provider = meta_provider
        self.meta_model = meta_model
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir = Path(work_dir) if work_dir else None
        self.structure_type = structure_type
        self._temp_dir = None

        self.history: List[Dict[str, Any]] = []
        self.best_f1 = -1.0
        self.best_prompt = ""
        self.best_iteration = -1

        # Read the initial prompt
        with open(self.initial_prompt_file, "r") as f:
            self.current_prompt = f.read()

        # Read gold standard examples for the meta-prompt (per-paper and flat)
        self.gold_examples_by_paper: Dict[str, List[str]] = self._load_gold_examples()
        self.gold_examples: List[str] = [
            ex for examples in self.gold_examples_by_paper.values() for ex in examples
        ]

    def _get_work_dir(self) -> Path:
        if self.work_dir:
            self.work_dir.mkdir(parents=True, exist_ok=True)
            return self.work_dir
        if self._temp_dir is None:
            self._temp_dir = tempfile.mkdtemp(prefix="prompt_opt_")
        return Path(self._temp_dir)

    def _load_gold_examples(self) -> Dict[str, List[str]]:
        """Load gold standard examples for all train papers. Returns dict keyed by paper_id."""
        examples_by_paper: Dict[str, List[str]] = {pid: [] for pid in self.train_paper_ids}
        try:
            with open(self.gold_csv, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                reader.fieldnames = [n.strip() for n in reader.fieldnames]
                for row in reader:
                    row = {k.strip(): v for k, v in row.items()}
                    pid = row.get("paper_id", "").strip().replace('_', '.')
                    if pid in examples_by_paper:
                        text = row.get("Gold_Standard_raw_latex", "").strip()
                        if text:
                            examples_by_paper[pid].append(text)
        except FileNotFoundError:
            print(f"[WARN] Gold CSV not found: {self.gold_csv}")
        return examples_by_paper

    def optimize(self) -> Tuple[str, List[Dict[str, Any]]]:
        """Run the optimization loop. Returns (best_prompt_text, history)."""
        print(f"\n{'='*60}")
        print(f"PROMPT OPTIMIZATION ({self.structure_type})")
        print(f"Train papers: {self.train_paper_ids}")
        if self.val_paper_ids:
            print(f"Val papers:   {self.val_paper_ids}")
        print(f"Provider: {self.provider} | Model: {self.model}")
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

            # 2. Run extraction for each train paper
            try:
                for pid in self.train_paper_ids:
                    print(f"  Extracting {pid}...")
                    self._run_extraction(str(prompt_file), iter_dir, paper_id=pid)
                print(f"[2/5] Extraction complete ({len(self.train_paper_ids)} papers)")
            except Exception as e:
                print(f"[ERROR] Extraction failed: {e}")
                self.history.append({
                    "iteration": iteration,
                    "error": f"extraction_failed: {e}",
                    "prompt": self.current_prompt,
                })
                continue

            # 3. Run postprocessing & evaluation across all train papers
            try:
                metrics, detailed = self._run_postprocessing(iter_dir, paper_ids=self.train_paper_ids)
                print(f"[3/5] Train evaluation: P={metrics['precision']:.3f} "
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
                "train_metrics": metrics,
                "error_counts": {
                    "false_negatives": len(error_analysis["false_negatives"]),
                    "false_positives": len(error_analysis["false_positives"]),
                    "near_misses": len(error_analysis["near_misses"]),
                },
                "prompt": self.current_prompt,
            })

            # 5. Call meta-optimizer (skip on last iteration or perfect score)
            if metrics["f1"] >= 1.0:
                print("[5/5] Perfect F1 — stopping early.")
                break
            if iteration < self.max_iterations - 1:
                try:
                    improved_prompt, reasoning = self._call_meta_optimizer(
                        self.current_prompt, metrics, error_analysis
                    )
                    print(f"[5/5] Meta-optimizer reasoning: {reasoning[:100]}...")
                    self.current_prompt = improved_prompt
                except Exception as e:
                    print(f"[WARN] Meta-optimizer failed: {e}. Keeping current prompt.")

        # Run validation if val papers are specified
        val_metrics = None
        if self.val_paper_ids:
            val_metrics = self._validate()

        # Save outputs
        self._save_history(val_metrics=val_metrics)
        self._save_best_prompt()

        print(f"\n{'='*60}")
        print(f"OPTIMIZATION COMPLETE")
        print(f"Best train F1: {self.best_f1:.3f} (iteration {self.best_iteration + 1})")
        if val_metrics:
            print(f"Validation F1: {val_metrics['f1']:.3f} "
                  f"(P={val_metrics['precision']:.3f} R={val_metrics['recall']:.3f})")
        print(f"{'='*60}\n")

        return self.best_prompt, self.history

    def _find_local_tex(self, paper_id: str) -> Optional[Tuple[str, str]]:
        """Search FULL_PAPERS_DIR for an already-cached .tex file matching paper_id.
        Returns (tex_path, versioned_id) or None."""
        pattern = os.path.join(FULL_PAPERS_DIR, "**", f"{paper_id}*.tex")
        matches = globmod.glob(pattern, recursive=True)
        if not matches:
            return None
        tex_path = matches[0]
        # Extract versioned_id from filename (e.g. "2208.03112v1.tex" -> "2208.03112v1")
        versioned_id = Path(tex_path).stem
        return tex_path, versioned_id

    def _run_extraction(self, prompt_file: str, iter_dir: Path, paper_id: str) -> None:
        """Run structure extraction for a single paper using the given prompt."""
        # Try local .tex first to avoid arXiv API calls
        local = self._find_local_tex(paper_id)
        if local:
            tex_path, versioned_id = local
        else:
            regex_id = f"^{paper_id}"

            # Fetch metadata
            data = fetch_arxiv_batch(
                regex_id=regex_id,
                formats="metadata",
                output_dir=None,
                verbose=False,
            )

            if not data:
                raise RuntimeError(f"No papers found for {paper_id}")

            # Get base_id and metadata
            base_id = None
            meta = None
            for vid, entry in data.items():
                bid = vid.split("v")[0]
                if bid == paper_id:
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
            extraction_mode="llm",
            llm_model=self.model,
            llm_provider=self.provider,
            custom_prompt_file=prompt_file,
            structure_types=[self.structure_type],
        )
        graph = parser.parse_file(tex_path)

        # Save JSON in the expected directory structure
        json_dir = iter_dir / "json"
        json_dir.mkdir(parents=True, exist_ok=True)

        suffix = self.model.replace("/", "-")
        json_filename = f"{versioned_id}_{suffix}.json"
        json_path = json_dir / json_filename

        json_path.write_text(
            json.dumps(graph.to_unified_dict(), indent=2), encoding="utf-8"
        )
        print(f"  JSON saved: {json_path}")

    def _run_postprocessing(
        self, iter_dir: Path, paper_ids: Optional[List[str]] = None
    ) -> Tuple[Dict[str, float], List[Dict[str, str]]]:
        """Run CSV conversion, gold merging, and evaluation. Returns (metrics, detailed)."""
        if paper_ids is None:
            paper_ids = self.train_paper_ids
        defs_csv = str(iter_dir / "definitions.csv")
        merged_csv = str(iter_dir / "merged.csv")
        summary_csv = str(iter_dir / "evaluation_results.csv")
        detailed_csv = str(iter_dir / "detailed_matches.csv")

        # Step 1: JSON -> CSV
        extract_definitions_to_csv(
            out_dir=str(iter_dir),
            paper_ids=paper_ids,
            output_csv=defs_csv,
            structure_type=self.structure_type,
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
        """Read evaluation summary CSV and return aggregated metrics across all rows."""
        total_tp = 0
        total_fp = 0
        total_fn = 0
        total_gold = 0
        total_extracted = 0
        found_rows = False
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    found_rows = True
                    total_tp += int(row.get("true_positives", 0))
                    total_fp += int(row.get("false_positives", 0))
                    total_fn += int(row.get("false_negatives", 0))
                    total_gold += int(row.get("num_gold_standards", 0))
                    total_extracted += int(row.get("num_extracted", 0))
        except FileNotFoundError:
            pass

        if not found_rows:
            return {
                "precision": 0.0, "recall": 0.0, "f1": 0.0,
                "true_positives": 0, "false_positives": 0, "false_negatives": 0,
                "num_gold": 0, "num_extracted": 0,
            }

        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "true_positives": total_tp,
            "false_positives": total_fp,
            "false_negatives": total_fn,
            "num_gold": total_gold,
            "num_extracted": total_extracted,
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

    @staticmethod
    def _select_within_budget(items: List[Dict], budget: int) -> List[Dict]:
        """Select as many items as fit within a character budget."""
        selected = []
        used = 0
        for item in items:
            item_chars = sum(len(str(v)) for v in item.values())
            if used + item_chars > budget and selected:
                break
            selected.append(item)
            used += item_chars
        return selected

    def _build_error_analysis(
        self,
        detailed_matches: List[Dict[str, str]],
        metrics: Dict[str, float],
    ) -> Dict[str, List[Dict[str, str]]]:
        """Categorize extraction errors into FP, FN, and near-misses."""
        false_positives = []
        near_misses = []
        # Track matched gold indices per paper
        matched_gold_by_paper: Dict[str, set] = {pid: set() for pid in self.train_paper_ids}

        for row in detailed_matches:
            sim = float(row.get("similarity", 0))
            is_match = row.get("is_match", "No") == "Yes"
            def_text = row.get("definition_text", "")
            gold_text = row.get("best_match_gold_text", "")
            gold_idx = row.get("best_match_gold_index", "")
            row_paper_id = row.get("paper_id", "")

            if is_match and gold_idx:
                if row_paper_id in matched_gold_by_paper:
                    matched_gold_by_paper[row_paper_id].add(gold_idx)
                else:
                    # Fallback: add to a flat set if paper_id not in detailed CSV
                    for pid_set in matched_gold_by_paper.values():
                        pid_set.add(gold_idx)
            elif sim < 0.3:
                entry = {
                    "extracted": def_text[:200],
                    "best_gold": gold_text[:200],
                    "similarity": sim,
                }
                if row_paper_id:
                    entry["paper_id"] = row_paper_id
                false_positives.append(entry)
            else:
                # 0.3 <= sim < threshold
                entry = {
                    "extracted": def_text[:200],
                    "best_gold": gold_text[:200],
                    "similarity": sim,
                }
                if row_paper_id:
                    entry["paper_id"] = row_paper_id
                near_misses.append(entry)

        # False negatives: gold examples not matched, computed per-paper
        false_negatives = []
        for pid, gold_list in self.gold_examples_by_paper.items():
            matched = matched_gold_by_paper.get(pid, set())
            for i, gold_text in enumerate(gold_list):
                if str(i) not in matched:
                    false_negatives.append({
                        "gold_index": i,
                        "gold_text": gold_text[:200],
                        "paper_id": pid,
                    })

        # Prioritize: near-misses by highest similarity (easiest wins),
        # FPs by lowest similarity (most egregious), FNs as-is (all important)
        near_misses.sort(key=lambda x: x["similarity"], reverse=True)
        false_positives.sort(key=lambda x: x["similarity"])

        # Budget-based selection: ~6000 chars total, split equally then
        # redistribute unused budget to categories that need more
        total_budget = 6000
        per_category = total_budget // 3

        selected_nm = self._select_within_budget(near_misses, per_category)
        selected_fp = self._select_within_budget(false_positives, per_category)
        selected_fn = self._select_within_budget(false_negatives, per_category)

        # Redistribute unused budget
        used = sum(sum(len(str(v)) for v in item.values()) for item in selected_nm + selected_fp + selected_fn)
        remaining = total_budget - used
        if remaining > 0:
            # Give remaining budget to FNs first (recall matters), then near-misses
            for category, full_list, selected in [
                ("fn", false_negatives, selected_fn),
                ("nm", near_misses, selected_nm),
                ("fp", false_positives, selected_fp),
            ]:
                extras = self._select_within_budget(full_list[len(selected):], remaining)
                selected.extend(extras)
                remaining -= sum(sum(len(str(v)) for v in item.values()) for item in extras)
                if remaining <= 0:
                    break

        return {
            "false_negatives": selected_fn,
            "false_positives": selected_fp,
            "near_misses": selected_nm,
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
        num_papers = len(self.train_paper_ids)
        paper_context = f"Evaluated across {num_papers} training paper(s)." if num_papers > 1 else ""

        # Gold examples for context
        gold_section = ""
        if self.gold_examples:
            gold_section = "\n## Gold Standard Examples (what correct extractions look like):\n"
            for i, ex in enumerate(self.gold_examples[:2]):
                gold_section += f"\nExample {i+1} (truncated):\n{ex[:300]}\n"

        # Error examples
        stype = self.structure_type
        fn_section = ""
        if error_analysis["false_negatives"]:
            fn_section = f"\n## False Negatives (gold {stype}s the prompt MISSED):\n"
            for item in error_analysis["false_negatives"]:
                paper_tag = f" [paper {item['paper_id']}]" if item.get("paper_id") else ""
                fn_section += f"\n- Gold {stype} #{item['gold_index']}{paper_tag}: {item['gold_text']}\n"

        fp_section = ""
        if error_analysis["false_positives"]:
            fp_section = f"\n## False Positives (extracted but NOT real {stype}s, similarity < 0.3):\n"
            for item in error_analysis["false_positives"]:
                paper_tag = f" [paper {item['paper_id']}]" if item.get("paper_id") else ""
                fp_section += f"\n- Extracted{paper_tag}: {item['extracted']}\n  Best gold match (sim={item['similarity']:.2f}): {item['best_gold']}\n"

        nm_section = ""
        if error_analysis["near_misses"]:
            nm_section = f"\n## Near Misses (partially matched, 0.3 <= similarity < {self.threshold}):\n"
            for item in error_analysis["near_misses"]:
                paper_tag = f" [paper {item['paper_id']}]" if item.get("paper_id") else ""
                nm_section += f"\n- Extracted{paper_tag}: {item['extracted']}\n  Best gold match (sim={item['similarity']:.2f}): {item['best_gold']}\n"

        # Get correct JSON fields for this structure type
        config = STRUCTURE_TYPE_CONFIG.get(stype, STRUCTURE_TYPE_CONFIG["definition"])
        json_fields = config["json_fields"]
        fields_str = ", ".join(json_fields)

        return f"""You are an expert prompt engineer optimizing a prompt for extracting mathematical {stype}s from LaTeX papers.

CRITICAL: You are optimizing extraction of **{stype}s** — NOT definitions or any other structure type. The improved prompt MUST remain focused on extracting {stype}s only.

## Task
Improve the extraction prompt below based on the evaluation results and error analysis.
{paper_context}

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
- Gold standard {stype}s: {metrics['num_gold']}
- Extracted {stype}s: {metrics['num_extracted']}

## Evaluation Method:
Extractions are compared using Jaccard similarity on tokenized, normalized LaTeX text.
A match is counted when similarity >= {self.threshold}.
Tokens include LaTeX commands (\\command), words, numbers, and symbols.
{gold_section}{fn_section}{fp_section}{nm_section}

## Instructions:
1. Analyze the error patterns to identify **general structural reasons** for false positives and false negatives.
2. Derive improvements based on **LaTeX constructs and document structure** (e.g., environment types, sentence patterns, mathematical notation conventions) — NOT based on specific content from the error examples.
3. Do NOT copy or reference specific text, notation, variable names, or terminology from the error examples into the improved prompt. The prompt must generalize to ANY mathematical paper, not just the ones evaluated here.
4. Gold standard {stype}s include the FULL passage with all mathematical content and surrounding text.
5. The improved prompt MUST still extract **{stype}s** — do NOT change it to extract a different structure type.
6. The improved prompt MUST contain the placeholder {{latex_chunk}} exactly as written.
7. The improved prompt must ask for JSON array output with fields: {fields_str}.
8. Prefer fewer, broader rules over many specific rules. Each instruction in the prompt should apply across diverse mathematical papers and subfields.
9. Authors often define custom LaTeX environments via \\newtheorem or \\newcommand (e.g., \\newtheorem{{defn}}{{Definition}}). The improved prompt SHOULD instruct the LLM to look for such macro declarations in the provided LaTeX and treat custom environments as equivalent to their standard counterparts.

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

    def _validate(self) -> Optional[Dict[str, float]]:
        """Run the best prompt on held-out validation papers. Returns val metrics."""
        if not self.val_paper_ids or not self.best_prompt:
            return None

        print(f"\n{'='*60}")
        print(f"VALIDATION on {self.val_paper_ids}")
        print(f"{'='*60}")

        work = self._get_work_dir()
        val_dir = work / "validation"
        val_dir.mkdir(parents=True, exist_ok=True)

        # Save best prompt
        prompt_file = val_dir / "prompt.txt"
        prompt_file.write_text(self.best_prompt, encoding="utf-8")

        # Extract from each val paper
        succeeded = []
        for pid in self.val_paper_ids:
            try:
                print(f"  Extracting {pid}...")
                self._run_extraction(str(prompt_file), val_dir, paper_id=pid)
                succeeded.append(pid)
            except Exception as e:
                print(f"[WARN] Validation extraction failed for {pid}: {e}, skipping")

        if not succeeded:
            print("[ERROR] All validation papers failed extraction")
            return None

        # Run postprocessing across succeeded val papers
        try:
            metrics, _ = self._run_postprocessing(val_dir, paper_ids=succeeded)
            print(f"Validation results: P={metrics['precision']:.3f} "
                  f"R={metrics['recall']:.3f} F1={metrics['f1']:.3f}")
            return metrics
        except Exception as e:
            print(f"[ERROR] Validation postprocessing failed: {e}")
            return None

    def _save_history(self, val_metrics: Optional[Dict[str, float]] = None) -> None:
        """Save optimization history to JSON."""
        history_path = self.out_dir / "optimization_history.json"
        history_data = {
            "train_paper_ids": self.train_paper_ids,
            "val_paper_ids": self.val_paper_ids,
            "provider": self.provider,
            "model": self.model,
            "threshold": self.threshold,
            "meta_provider": self.meta_provider,
            "meta_model": self.meta_model,
            "best_iteration": self.best_iteration,
            "best_f1": self.best_f1,
            "iterations": self.history,
        }
        if val_metrics:
            history_data["validation_metrics"] = val_metrics
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(history_data, f, indent=2)
        print(f"History saved to {history_path}")

    def _save_best_prompt(self) -> None:
        """Save the best prompt to a file."""
        if not self.best_prompt:
            return
        prompt_path = self.out_dir / f"optimized_prompt_{self.structure_type}_{self.provider}.txt"
        prompt_path.write_text(self.best_prompt, encoding="utf-8")
        print(f"Best prompt saved to {prompt_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Iterative prompt optimization for math structure extraction"
    )
    # Paper selection: either --paper-id (single, backward compat) or --train-papers
    paper_group = parser.add_mutually_exclusive_group(required=True)
    paper_group.add_argument(
        "--paper-id", type=str, help="ArXiv paper ID (single paper, no validation)"
    )
    paper_group.add_argument(
        "--train-papers",
        nargs="+",
        type=str,
        help="ArXiv paper IDs for training (optimize on these)",
    )
    parser.add_argument(
        "--val-papers",
        nargs="+",
        type=str,
        default=None,
        help="ArXiv paper IDs for validation (held-out evaluation)",
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
    parser.add_argument(
        "--structure-type",
        type=str,
        default="definition",
        help="Structure type to optimize extraction for (default: definition)",
    )

    args = parser.parse_args()

    if args.val_papers and not args.train_papers:
        parser.error("--val-papers requires --train-papers (not --paper-id)")

    optimizer = PromptOptimizer(
        paper_id=args.paper_id,
        train_paper_ids=args.train_papers,
        val_paper_ids=args.val_papers,
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
        structure_type=args.structure_type,
    )

    best_prompt, history = optimizer.optimize()


if __name__ == "__main__":
    main()
