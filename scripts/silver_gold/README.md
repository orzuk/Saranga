# Silver-Gold Multi-Model Extraction

Runs the holistic extraction prompt against paper .tex sources via any of
5 providers (OpenRouter, Alibaba, Google, Anthropic, OpenAI). Outputs land
next to the existing `gold.json` as `gold_<suffix>.json`, in the unified
`{metadata, nodes, edges}` schema.

**Modular by design**: the prompt is a CLI argument. To try a new
extraction strategy (different prompt, different granularity, different
schema request) — write the new prompt to a file and pass
`--prompt-file new_prompt.txt`. Everything else stays the same.

## Files

- `run_extraction.py` — the runner (single self-contained script)
- `README.md` — this file

## Prerequisites

```bash
pip install openai                   # all OpenAI-compatible providers
pip install google-generativeai      # only if using --provider google
pip install anthropic                # only if using --provider anthropic
```

API keys — set whichever you'll use:

```bash
export OPENROUTER_API_KEY=sk-or-...        # OpenRouter: Qwen, Gemini, etc.
export DASHSCOPE_API_KEY=sk-...            # Alibaba Bailian: Qwen direct
export GOOGLE_API_KEY=AIza...              # Google AI Studio: Gemini free tier
export ANTHROPIC_API_KEY=sk-ant-...        # Claude
export OPENAI_API_KEY=sk-...               # GPT
```

## Model/provider selection for Qwen (2026-04 status)

| Model | On HF Router? | On OpenRouter? | Notes |
|---|---|---|---|
| Qwen3.6-35B-A3B (Apr 2026) | NO (no provider yet) | Yes | Latest, wait a week or use OpenRouter |
| Qwen3-235B-A22B-Thinking-2507 (Jul 2025) | YES (Novita) | Yes | Strong reasoning, older but bigger |
| Qwen3-72B-Instruct | Check live | Yes | Non-thinking, faster |
| Qwen2.5-72B-Instruct | YES (multiple) | Yes | Older generation |

**Recommended if you already have HF credit**: use `Qwen/Qwen3-235B-A22B-Thinking-2507`
via `--provider huggingface`. Same silver-gold quality for this use case;
no separate signup.

## 5-paper smoke test (HF Router, Qwen3-235B-Thinking via Novita)

```bash
cd /mnt/c/Code/Github/Authomathics/scripts/silver_gold

export HF_TOKEN=hf_...      # your existing HF token

python run_extraction.py \
    --provider huggingface \
    --model Qwen/Qwen3-235B-A22B-Thinking-2507 \
    --prompt-file ../paper_extraction_prompt.txt \
    --out-suffix _qwenT \
    --limit 5
```

## 5-paper smoke test (OpenRouter, Qwen3.6-35B-A3B)

If you prefer the latest Qwen3.6 via OpenRouter:

```bash
export OPENROUTER_API_KEY=sk-or-...

python run_extraction.py \
    --provider openrouter \
    --model qwen/qwen3.6-35b-a3b \
    --prompt-file ../paper_extraction_prompt.txt \
    --out-suffix _qwen \
    --limit 5
```

Expected output per paper:

```
[1/5] paper1: tex=paper1.tex prompt=67,832 chars -> calling LLM
    OK  (48.3s) nodes=41 edges=57 -> gold_qwen.json
```

Files land at
`/mnt/g/My Drive/Research/Automath/alignment_benchmark/papers/paperN/gold_qwen.json`.

## Quick inspection of a result

```bash
python3 -c "
import json, sys
p = '/mnt/g/My Drive/Research/Automath/alignment_benchmark/papers/paper1/gold_qwen.json'
d = json.load(open(p))
print('nodes:', len(d.get('nodes', [])))
print('edges:', len(d.get('edges', [])))
print('first node:', json.dumps(d['nodes'][0], indent=2)[:400])
"
```

## Scale to all 270 extracted papers

Once the 5-paper run looks good, drop `--limit` and add `--resume`:

```bash
python run_extraction.py \
    --provider openrouter \
    --model qwen/qwen3.6-35b-a3b \
    --prompt-file ../paper_extraction_prompt.txt \
    --out-suffix _qwen \
    --resume \
    --sleep 1.0
```

`--resume` skips papers whose `gold_qwen.json` already exists — safe to
interrupt (Ctrl-C) and restart. `--sleep 1.0` is a 1-second pause between
calls to stay within OpenRouter rate limits on shared tiers.

Estimated time: OpenRouter Qwen3.6-35B-A3B completes a typical math paper
in 30-90s; 270 papers × 60s = ~4.5 hours wall clock. Background it with
`nohup` or `tmux`:

```bash
nohup python run_extraction.py ... > run_qwen.log 2>&1 &
tail -f run_qwen.log
```

Estimated cost: ~$0.04-0.08 per paper on OpenRouter (Qwen3.6-35B-A3B) = ~$11-22
for all 270. Alibaba Bailian direct is ~40% cheaper if accessible.

## Scale to all 270 with Gemini (free tier)

```bash
export GOOGLE_API_KEY=AIza...

python run_extraction.py \
    --provider google \
    --model gemini-2.5-pro \
    --prompt-file ../paper_extraction_prompt.txt \
    --out-suffix _gemini \
    --resume \
    --sleep 2.0
```

Gemini free tier on AI Studio rate-limits at ~2 requests/minute for 2.5-Pro;
`--sleep 2.0` respects it. 270 papers × 2s pace = ~9 min wall clock minimum.
If you hit daily-quota, pause and resume next day (--resume handles it).

## Swapping prompts (the modular bit)

Want to try a different prompt strategy? Write your prompt to a file — the
script looks for a `PROMPT\n====` marker and takes text after it, or uses
the whole file verbatim if no marker. Placeholders `{CHAPTER_TEXT}`,
`{PAPER_ID}`, `{TITLE}`, `{AUTHORS}`, `{YEAR}`, `{SOURCE_TYPE}`,
`{CHAPTER_NUM}`, `{CHAPTER_TITLE}`, `{BOOK_ID}` are auto-substituted;
unknown `{tokens}` pass through untouched.

```bash
# try a leaner prompt on just 5 papers
python run_extraction.py \
    --provider openrouter \
    --model qwen/qwen3.6-35b-a3b \
    --prompt-file my_experimental_prompt.txt \
    --out-suffix _qwen_v2 \
    --limit 5
```

Output files go to `gold_qwen_v2.json` — different suffix means they don't
overwrite your existing `gold_qwen.json`. So you can A/B-test prompts freely.

## Full CLI reference

```bash
python run_extraction.py --help
```

Key flags:

| Flag | Default | Meaning |
|---|---|---|
| `--provider` | required | `openrouter`, `alibaba`, `google`, `anthropic`, `openai` |
| `--model` | required | provider-specific model string |
| `--prompt-file` | required | path to prompt template |
| `--out-suffix` | required | output filename suffix, e.g. `_qwen` |
| `--limit N` | 0 (all) | only process first N eligible papers |
| `--paper-ids a,b,c` | all | exact paper_id list (overrides limit) |
| `--resume` | off | skip papers with existing output |
| `--sleep S` | 0 | seconds between calls (rate limits) |
| `--max-tokens N` | 16384 | LLM output length cap |
| `--max-input-chars N` | 200000 | truncate .tex larger than this |
| `--log PATH` | `silver_gold_log.csv` | per-paper log CSV |
| `--all-papers` | off | run on every registry row, not just json_status=extracted |

## Recommended sequence for the silver-gold experiment

1. **5-paper test with Qwen** (~5 min). Check JSON validity, node counts.
2. **Scale Qwen to 270** (~4-5 hours background, ~$15). Check log for failures.
3. **5-paper test with Gemini** (~5 min) same prompt.
4. **Scale Gemini to 270** (~1 day on free tier, $0).
5. Then run the (not-yet-written) `consensus_intersect.py` to build silver-gold
   from Opus ∩ Qwen ∩ Gemini outputs.

Steps 2 and 4 can run in parallel — they write to different output suffixes.
