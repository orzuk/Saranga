# SARANGA portal as a Hugging Face Docker Space (same address as the old static Space):
# all tiers, Tier-3 pages built on the fly from the dataset's bundles (docs/tier3_bundles.md; all_v7g = the whole-arXiv v7
# graphs with the textbook grounding written in, portal/bundle_t3.py --grounding; the portal lists the categories of
# data/tier3_all/index.json, their per-year paper lists fetched from all_v7g/_portal_index), and "Your paper".
FROM python:3.12-slim
# bubblewrap + socat: the sandbox the LLM agent's commands run in ("Your paper" with an LLM)
RUN apt-get update && apt-get install -y --no-install-recommends curl bubblewrap socat && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy pandas regex requests matplotlib networkx pyahocorasick pillow python-dateutil claude-agent-sdk==0.2.166
RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY --chown=user . .
USER user
ENV PORT=7860 MPLBACKEND=Agg SARANGA_LIBS_CDN=1 \
    SARANGA_SILVER_DIR=/home/user/app/silver_v6 \
    SARANGA_T3_BUNDLES=https://huggingface.co/datasets/saranga-project/saranga/resolve/main/all_v7g \
    SARANGA_CONCEPTS=/home/user/app/foundation/concepts.json
# no SARANGA_T3_REMOTE: the dataset's per-paper JSONs ({cat}/json/) are the v6 run, so a v7 paper
# missing from the bundles is better a 404 than a v6 graph
EXPOSE 7860
CMD ["python3", "portal/portal_server.py"]
