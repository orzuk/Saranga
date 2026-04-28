#!/bin/bash
# Usage: bash extraction.sh <structure_type> [providers]
# Example: bash extraction.sh definition
#          bash extraction.sh theorem anthropic,openai,manual
#          bash extraction.sh lemma anthropic
#
# Valid types: definition theorem lemma proof proposition corollary claim conjecture problem
# Default providers: anthropic,openai,manual

set -euo pipefail

STYPE="${1:?Usage: bash extraction.sh <structure_type> [providers]}"
PROVIDERS="${2:-anthropic,openai,manual}"

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

ALL_PAPERS="1210.4634,1405.2464,2208.03112,1204.0109v1,1512.09272v2,2309.05826,2312.16785,2401.00367,2505.12804v1,2603.09769v1"

PROMPT_FILE="${STYPE}_optimization/optimized_prompt_${STYPE}_anthropic.txt"
if [ ! -f "$PROMPT_FILE" ]; then
    echo "Warning: optimized prompt not found at $PROMPT_FILE, using base prompt"
    PROMPT_FILE="prompts/${STYPE}_prompt.txt"
fi

bash evaluation_pipeline.sh \
    --paper-id "$ALL_PAPERS" \
    --structure-type "$STYPE" \
    --gold-csv "$GOLD_CSV" \
    --prompt-file "$PROMPT_FILE" \
    --out-dir "${STYPE}_eval" \
    --providers "$PROVIDERS"
