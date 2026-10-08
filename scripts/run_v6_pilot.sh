#!/usr/bin/env bash
# v6 pilot: 10 papers (one per category) x 4 model arms, as headless Claude Code
# sessions, so model AND effort are set per run (--model / --effort).
#
#   scripts/run_v6_pilot.sh            run everything not yet done
#   scripts/run_v6_pilot.sh ARM PAPER  run one job (smoke test)
#
# Each run writes corpus/silver/pilot_v6/<arm>/<paper>.json (the extraction) and
# corpus/silver/pilot_v6/_runs/<arm>__<paper>.json (the CLI result: usage, cost,
# duration, the agent's report). Jobs whose extraction already exists are skipped.
set -u
REPO=/mnt/c/Code/Github/Saranga
OUT=$REPO/corpus/silver/pilot_v6
SCRATCH=${PILOT_SCRATCH:-/tmp/claude-1000/v6_pilot_scratch}
PARALLEL=${PARALLEL:-8}
mkdir -p "$OUT/_runs" "$SCRATCH"

PAPERS="1612.05419v3 1701.03237v1 1704.08863v2 1707.01421v4 1705.02768v1
1907.08507v2 1306.2128v2 1112.3679v2 1909.04464v2 1304.5152v1"
# arm  model  effort
ARMS="opus55_medium:claude-opus-5-5:medium
opus55_high:claude-opus-5-5:high
fable51_high:claude-fable-5-1:high
sonnet5_high:claude-sonnet-5:high"

TEMPLATE=$(awk '/^```$/{f=!f; next} f' "$REPO/scripts/LAUNCH_PROMPT_TEMPLATE_v6_pilot.md")

run_one() {
  local arm=$1 model=$2 effort=$3 pid=$4
  local target="$OUT/$arm/$pid.json" log="$OUT/_runs/${arm}__${pid}.json"
  [ -s "$target" ] && { echo "skip $arm $pid"; return 0; }
  mkdir -p "$OUT/$arm"
  local prompt=${TEMPLATE//\{ARXIV_ID\}/$pid}
  prompt=${prompt//\{ARM\}/$arm}
  prompt=${prompt//\{MODEL\}/$model}
  prompt=${prompt//\{EFFORT\}/$effort}
  prompt=${prompt//<your scratch dir>/$SCRATCH/${arm}_${pid}}
  prompt="$prompt
Your private scratch directory is $SCRATCH/${arm}_${pid} (create it)."
  echo "start $arm $pid $(date +%T)"
  ( cd "$REPO" && timeout 90m claude -p "$prompt" \
      --model "$model" --effort "$effort" --output-format json \
      --permission-mode acceptEdits --add-dir "$SCRATCH" --no-session-persistence \
      --allowedTools "Read Write Edit Glob Grep Bash(python3 *) Bash(mkdir *) Bash(ls *) Bash(head *) Bash(wc *) Bash(cat *) Bash(sed *) Bash(grep *)" \
      --disallowedTools "Agent WebFetch WebSearch" \
      > "$log" 2> "$log.err" )
  echo "done  $arm $pid $(date +%T) exit=$? out=$([ -s "$target" ] && echo yes || echo NO)"
}
export -f run_one
export OUT SCRATCH TEMPLATE REPO

if [ $# -eq 2 ]; then
  line=$(echo "$ARMS" | grep "^$1:")
  IFS=: read -r arm model effort <<< "$line"
  run_one "$arm" "$model" "$effort" "$2"
  exit
fi

for pid in $PAPERS; do
  echo "$ARMS" | while IFS=: read -r arm model effort; do
    echo "$arm $model $effort $pid"
  done
done | xargs -P "$PARALLEL" -L 1 bash -c 'run_one "$0" "$1" "$2" "$3"'
