---
title: SARANGA - Your paper
emoji: 🕸️
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

Build the typed knowledge graph of any mathematics paper from its LaTeX source:
paste an arXiv id, or upload a .tex file or a .zip / .tar.gz of the project.
Extraction uses the SARANGA rule-based extractor (LaTeX parser plus distilled
sentence rules; no language model) and takes a few seconds. Uploads are deleted
after 24 hours.
