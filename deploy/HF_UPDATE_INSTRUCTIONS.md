# Updating the public SARANGA site on Hugging Face (v6 + "Your paper")

Goal: keep the same addresses, replace the old content.

- Website: https://huggingface.co/spaces/RHCPP/saranga — today a *static* Space (pre-built
  pages, old version). It becomes a *Docker* Space running `portal/portal_server.py`: all
  tiers, 100K pages built on the fly, and "Your paper" (graph from any arXiv id or uploaded
  LaTeX, rule-based, a few seconds).
- Data: https://huggingface.co/datasets/RHCPP/saranga — today the old (v4) 100K graphs plus
  pre-built pages. It gets the v6b graphs; the pre-built pages are dropped.

Everything below was tested locally (the staged Space, with 100K JSONs read from the dataset).
Order matters a little: do the dataset first (step 2), then the Space (step 3). If the Space
goes first it still works, but 100K papers show the old v4 graphs until step 2 is done.

## 1. Once

    cd <your clone of orzuk/Saranga> && git pull
    pip install -U huggingface_hub          # in the venv you use (on the cluster: authomathics-venv)
    huggingface-cli login                   # a WRITE token of an account with write access to RHCPP

## 2. Dataset: upload the v6b 100K graphs (on the cluster, where the run lives)

    python3 scripts/hf_update_dataset_v6b.py \
        /sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data/parsed_100k_v6b

- Uploads `<cat>/json/*.json` (same names as before, `<id>_rules.json`, so they overwrite the
  old ones) and the per-category reports, then deletes the old `<cat>/html/` folders.
- ~100K files: expect an hour or more. It is resumable: if it stops, run it again.
- Run it inside `screen`/`tmux` or as a SLURM job, so it survives a dropped connection.

## 3. Website: replace the static Space with the Docker Space (any machine with the repo)

    python3 scripts/stage_hf_portal_space.py /tmp/saranga_portal_space
    huggingface-cli upload RHCPP/saranga /tmp/saranga_portal_space . --repo-type=space --delete="*"

- Run it from a machine that has the portal data: `portal/data/` (tier-3 index with titles)
  and `corpus/silver/opus-5.5__v6/graphs/` (the 200 silver pages). Or's laptop has them; if
  you run it elsewhere, check that the staging script reports ~1,365 files / ~300 MB.
- `--delete="*"` removes the old static files in the same commit; the old site stays in the
  Space's git history and can be restored from there.
- The Space then rebuilds (a few minutes; watch the "Building" log on the Space page).

## 4. Check

- https://huggingface.co/spaces/RHCPP/saranga opens; Tier 2 shows 200 papers (LLM and rules).
- Tier 3: open a category, click a paper: its page appears after a few seconds.
- "Your paper": enter 1206.0313 -> a graph of about 150 nodes opens.

## Notes

- A Docker Space is public with its files: the parser, rules and viewer code become visible.
- Free Spaces sleep after ~48 h without visits; the first visit then takes about a minute.
- "Your paper" uploads are stored only in the container's /tmp and deleted after 24 h.
- To update later: `git pull`, then step 3 again (and step 2 only if the 100K data changes).
