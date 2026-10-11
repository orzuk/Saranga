#!/bin/bash
# Start the portal locally: http://localhost:${PORT:-8000}/
#   Tier 2 = the 200 v6 silver papers (LLM and rule-based graphs, prebuilt).
#   Tier 3 = the 100K corpus: index of every paper; a local sample of JSONs;
#            any other paper is fetched from the cluster on first click
#            (needs ssh to moriah without a password) and its page is built
#            and cached under portal/cache/tier3_v6/.
cd "$(dirname "$0")"
RUN=${T3_RUN:-parsed_100k_v6b}
export SARANGA_T3_REMOTE=${SARANGA_T3_REMOTE:-"ssh -o BatchMode=yes orzuk@moriah-gw.cs.huji.ac.il cat /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/$RUN/{cat}/json/{id}.json"}
exec python3 portal_server.py
