# SARANGA "Your paper": rule-based paper-to-graph extraction, public Hugging Face Docker Space.
FROM python:3.12-slim
RUN pip install --no-cache-dir numpy pandas regex requests matplotlib networkx pyahocorasick pillow python-dateutil
RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY --chown=user . .
USER user
ENV PORT=7860 SARANGA_LIBS_CDN=1 SARANGA_WORK=/tmp/saranga_yours MPLBACKEND=Agg
EXPOSE 7860
CMD ["python3", "app.py"]
