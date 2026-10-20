#!/bin/bash
# v7 346-paper experiment (Or, 2026-10-20): alg3 trained on T-S (120 silver), T-G (90 gold-author), T-A (210 all).
# Outputs (models, graphs) go to alg3/runs/v7_346/ (gitignored). Then:
#   python3 scripts/compare_distillers.py run --config alg3/experiments/v7_346/v7_346_alg3.json --stages eval,report
#   python3 alg3/experiments/v7_346/score.py --split test      (and --split val)
set -euo pipefail
cd "$(dirname "$0")/../../.."          # repo root
X=alg3/experiments/v7_346; R=alg3/runs/v7_346; C=alg3/cache/v7_346; G=$R/graphs
[ -f $C/split_A.csv ] || python3 $X/stage.py
REL=extractors/rules/silver_v6__sentence_tagger__2026-10
UNITS=extractors/rules/silver_v6__sentence_rules_haiku__2026-10
STACK=extractors/edges/silver_v6__edges_stack__2026-10
export PYTHONHASHSEED=0
P() { python3 -u $X/parse_all.py "$@"; }
# 0. reference parses (release tagger also = the e2e base graphs), units, base
P $REL $G/release_v2b
P $UNITS $G/units
P alg3/cache/_empty_rules $G/base
for g in release_v2b units; do
  [ -d $G/$g+stack ] || python3 -u alg3/edges.py apply --graphs $G/$g --model $STACK --out $G/$g+stack
done
# 1. the three training sets
for V in ${VARIANTS:-S G A}; do
  D=$R/T-$V; mkdir -p $D
  [ -f $D/papers.pkl ] || python3 -u alg3/data.py --splits train,val --tex-dir $C/tex --silver $C/silver \
      --split-file $C/split_$V.csv --out $D/papers.pkl
  [ -f $D/model/sentence_model.json ] || python3 -u alg3/train.py --data $D/papers.pkl --out $D/model \
      --class-weight sqrt --stack --objective e2e --graphs $G/release_v2b --silver $C/silver
  P $D/model $G/T-$V
  [ -f $D/edges/model.json ] || python3 -u alg3/edges.py train --graphs $G/T-$V --out $D/edges \
      --silver $C/silver --split $C/split_$V.csv
  [ -d $G/T-$V+edges ] || python3 -u alg3/edges.py apply --graphs $G/T-$V --model $D/edges --out $G/T-$V+edges
done
echo ALL DONE
