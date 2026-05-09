#!/bin/bash
# Usage: bash optimize.sh <structure_type>
# Example: bash optimize.sh theorem
#
# Valid types: definition theorem lemma proof proposition corollary claim conjecture problem

set -euo pipefail

STYPE="${1:?Usage: bash optimize.sh <structure_type>}"

case "$STYPE" in
    definition)  GOLD_CSV="Gold_Standard_Definitions.csv" ;;
    theorem)     GOLD_CSV="Gold_Standard_Theorems.csv" ;;
    lemma)       GOLD_CSV="Gold_Standard_Lemmas.csv" ;;
    proof)       GOLD_CSV="Gold_Standard_Proofs.csv" ;;
    proposition) GOLD_CSV="Gold_Standard_Propositions.csv" ;;
    corollary)   GOLD_CSV="Gold_Standard_Corollaries.csv" ;;
    claim)       GOLD_CSV="Gold_Standard_Claims.csv" ;;
    conjecture)  GOLD_CSV="Gold_Standard_Conjectures.csv" ;;
    problem)     GOLD_CSV="Gold_Standard_Problems.csv" ;;
    *)
        echo "Error: unknown structure type '$STYPE'"
        echo "Valid types: definition theorem lemma proof proposition corollary claim conjecture problem"
        exit 1
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

python prompt_optimizer.py \
    --structure-type "$STYPE" \
    --train-papers 1210.4634 2401.00367 1204.0109v1 1405.2464 1512.09272v2 2208.03112 2309.05826 \
    --val-papers 2603.09769v1 2312.16785 2505.12804v1 \
    --gold-csv "$GOLD_CSV" \
    --initial-prompt "prompts/${STYPE}_prompt.txt" \
    --provider anthropic \
    --model claude-opus-4-7 \
    --meta-model claude-opus-4-7 \
    --iterations 3 \
    --out-dir "${STYPE}_optimization"
