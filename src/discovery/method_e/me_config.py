"""Method E configuration dataclass.

A MethodEConfig is serialized as the first artifact of every run (config.yaml
under the run dir) so the run is fully reproducible. Subsequent phases load
the same config to ensure consistency.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class MethodEConfig:
    # Corpus filters
    cutoff_year: int = 2018                 # problems posed <= cutoff_year-1
                                            # theorems published >= cutoff_year
    categories: Optional[list[str]] = None  # restrict to these tier3 dirs
    problem_types: list[str] = field(
        default_factory=lambda: ["open_problem", "conjecture"])
    theorem_types: list[str] = field(
        default_factory=lambda: ["theorem", "lemma", "proposition", "corollary"])

    # Self-resolution filter (exclude conjectures where the same authors
    # publish the resolution within a 2-year window)
    exclude_self_resolved: bool = True
    self_resolution_window_years: int = 2

    # Retrieval
    top_k_per_problem: int = 50
    score_threshold: float = 0.30
    sig_weight_foundation: float = 0.45
    sig_weight_operator: float = 0.20
    sig_weight_statement: float = 0.35
    # When the problem side has empty foundation_ids (common for open
    # problems), redistribute its weight to statement_jaccard.
    rebalance_on_empty_foundation: bool = True

    # Dedup
    dedup_statement_threshold: float = 0.85
    dedup_foundation_threshold: float = 0.5

    # Citation novelty
    headline_only_no_citation: bool = True   # K_structural is the headline;
                                             # K_citation kept for calibration

    # LLM judge
    judge_model: str = "sonnet"           # tier-1 cheap judge
    judge_model_tier2: str = "opus"       # tier-2 confirmation pass
    judge_prompt_version: str = "method_e_judge_v1"
    judge_dry_run: bool = False           # set True to skip LLM API spend

    # Paths (set at run-time; not part of the frozen config)
    run_dir: Optional[str] = None

    def to_yaml(self) -> str:
        """Minimal YAML serializer — avoids a hard PyYAML dep."""
        import textwrap
        lines = []
        for k, v in asdict(self).items():
            if v is None:
                lines.append(f"{k}: null")
            elif isinstance(v, bool):
                lines.append(f"{k}: {str(v).lower()}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k}: {v}")
            elif isinstance(v, str):
                lines.append(f"{k}: \"{v}\"")
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{k}: []")
                else:
                    lines.append(f"{k}:")
                    for item in v:
                        lines.append(f"  - {item}")
            else:
                lines.append(f"{k}: {v!r}")
        return "\n".join(lines) + "\n"

    @classmethod
    def from_dict(cls, d: dict) -> "MethodEConfig":
        # Accept only known fields; unknowns are dropped silently to keep
        # forward-compat with future fields.
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})
