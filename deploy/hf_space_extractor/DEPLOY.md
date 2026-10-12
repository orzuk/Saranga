# Deploying the public "Your paper" service

The rule-based extractor runs on a free Hugging Face **Docker** Space (CPU basic:
2 vCPU, 16 GB). The existing portal Space `RHCPP/saranga` is a *static* Space and
cannot run Python, so this is a second Space.

1. On huggingface.co: New Space -> owner `RHCPP` (or your user), name e.g.
   `saranga-yours`, SDK **Docker**, hardware CPU basic (free), visibility **public**.
2. Locally:

       pip install -U huggingface_hub
       huggingface-cli login                      # a write token for the owner
       python3 scripts/stage_hf_extractor_space.py /tmp/saranga_space
       (cd /tmp/saranga_space && python3 app.py)  # optional: test on http://localhost:7860
       huggingface-cli upload RHCPP/saranga-yours /tmp/saranga_space . --repo-type=space

3. The Space builds the image (a few minutes) and is then live at
   `https://rhcpp-saranga-yours.hf.space/`. Re-run step 2 after code changes.

Notes
- The Space is public, so the ~33 staged files (parser, rules, viewer) are visible.
- Free Spaces sleep after ~48 h without visits; the first visit then takes ~1 min.
- Uploads live in /tmp of the container and are deleted after 24 h (and on restart).
- Link it from the static portal's home page once live.
