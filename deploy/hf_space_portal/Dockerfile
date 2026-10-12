# SARANGA portal as a Hugging Face Docker Space (same address as the old static Space):
# all tiers, 100K pages built on the fly from the dataset, and "Your paper".
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy pandas regex requests matplotlib networkx pyahocorasick pillow python-dateutil
RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY --chown=user . .
USER user
ENV PORT=7860 MPLBACKEND=Agg SARANGA_LIBS_CDN=1 \
    SARANGA_SILVER_DIR=/home/user/app/silver_v6 \
    SARANGA_T3_REMOTE="curl -sfL https://huggingface.co/datasets/RHCPP/saranga/resolve/main/{cat}/json/{id}.json"
EXPOSE 7860
CMD ["python3", "portal/portal_server.py"]
