"""T-OPEN O5 — cross-encoder rerank of the candidate shortlist.

A bi-encoder has to compress a whole theorem into one vector before it ever sees
the problem it will be compared against. A cross-encoder reads both together and
can attend across them, so it is markedly more precise — and quadratically more
expensive, which is why it only ever runs on the top-M candidates per problem
that retrieval already surfaced.

The arithmetic that makes this the last cheap rung: 15,143 problems x top-20 is
~300k pairs. At ~250 pairs/s on one L40s that is ~20 minutes; four array tasks
make it five. Compare to scoring all 24 billion problem-theorem pairs with a
cross-encoder, which is what "millions of pairs is unreasonable" correctly rules
out. Retrieval is O(N); only this stage is per-pair, and it sees 1e-5 of them.

    python discovery_suite/open_problems/o5_rerank.py \
        --in  runs/triage_top_dense.csv --store $STORE \
        --out runs/reranked.csv --model bge-reranker --top-per-problem 20

Output = input schema + ``rerank_score`` (and ``retrieval_score``/``retrieval_rank``
preserved), re-sorted, so it drops straight into ``triage_open.py`` /
``batch_o4.py`` like every other stage.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from embed import textstore as TS  # noqa: E402
from embed import views as V  # noqa: E402
from embed.models import RERANKERS, ModelCard, get_card, pick_device, pick_dtype  # noqa: E402
from embed.progress import Heartbeat, banner  # noqa: E402

RERANK_INSTRUCT = ("Given an open mathematical problem or conjecture, judge "
                   "whether the candidate theorem resolves it.")


class CrossEncoder:
    """Scores (problem, theorem) pairs jointly. Two backends, one interface."""

    def __init__(self, card: ModelCard, *, device: Optional[str] = None,
                 batch_size: Optional[int] = None, max_tokens: Optional[int] = None,
                 dtype: str = "auto") -> None:
        self.card = card
        self.device = pick_device(device)
        self.batch_size = batch_size or card.batch_size
        self.max_tokens = max_tokens or card.max_tokens
        self._dtype_req = dtype
        self._tok = self._model = None
        self._yes = self._no = None

    def load(self) -> "CrossEncoder":
        if self._model is not None:
            return self
        import torch
        from transformers import AutoTokenizer
        dtype = pick_dtype(self.device, self._dtype_req)
        self._tok = AutoTokenizer.from_pretrained(
            self.card.hf_id, trust_remote_code=self.card.trust_remote_code)
        if self._is_causal():
            from transformers import AutoModelForCausalLM
            self._model = AutoModelForCausalLM.from_pretrained(
                self.card.hf_id, torch_dtype=dtype,
                trust_remote_code=self.card.trust_remote_code).to(self.device).eval()
            # Qwen3-Reranker frames relevance as a yes/no next-token decision;
            # the score is P(yes) over just those two logits.
            self._yes = self._tok.convert_tokens_to_ids("yes")
            self._no = self._tok.convert_tokens_to_ids("no")
        else:
            from transformers import AutoModelForSequenceClassification
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self.card.hf_id, torch_dtype=dtype,
                trust_remote_code=self.card.trust_remote_code).to(self.device).eval()
        print(f"[rerank] loaded {self.card.key} ({self.card.hf_id}) "
              f"device={self.device}", file=sys.stderr, flush=True)
        return self

    def _is_causal(self) -> bool:
        return "reranker" in self.card.hf_id.lower() and "qwen" in self.card.hf_id.lower()

    def _prompt(self, query: str, doc: str) -> str:
        return (f"<Instruct>: {RERANK_INSTRUCT}\n"
                f"<Query>: {query}\n<Document>: {doc}")

    def score(self, pairs: Sequence[tuple[str, str]],
              on_batch=None) -> np.ndarray:
        """Return one relevance score per (query, doc) pair, in input order."""
        self.load()
        import torch
        out = np.zeros(len(pairs), dtype=np.float32)
        # Length-sorted batching, same rationale as the bi-encoder: padding a
        # 40-token pair up to an 900-token one wastes most of the forward pass.
        order = sorted(range(len(pairs)),
                       key=lambda i: len(pairs[i][0]) + len(pairs[i][1]))
        for s in range(0, len(order), self.batch_size):
            idx = order[s:s + self.batch_size]
            if self._is_causal():
                texts = [self._prompt(pairs[i][0], pairs[i][1]) for i in idx]
                enc = self._tok(texts, padding=True, truncation=True,
                                max_length=self.max_tokens,
                                return_tensors="pt").to(self.device)
                with torch.no_grad():
                    logits = self._model(**enc).logits[:, -1, :]
                two = torch.stack([logits[:, self._no], logits[:, self._yes]], dim=1)
                sc = torch.softmax(two.float(), dim=1)[:, 1]
            else:
                enc = self._tok([pairs[i][0] for i in idx],
                                [pairs[i][1] for i in idx],
                                padding=True, truncation=True,
                                max_length=self.max_tokens,
                                return_tensors="pt").to(self.device)
                with torch.no_grad():
                    logits = self._model(**enc).logits
                # Single-logit rerankers (ms-marco, bge-reranker) emit an
                # unbounded relevance logit. Squash it: downstream consumers —
                # triage_open.py's --min-score, the fusion rescaler — all assume
                # a score in [0, 1] like a cosine. Sigmoid is monotone, so the
                # ranking is untouched and only the axis becomes comparable.
                sc = torch.sigmoid(logits[:, 0].float()) if logits.shape[-1] == 1 \
                    else torch.softmax(logits.float(), dim=1)[:, -1]
            out[idx] = sc.cpu().numpy()
            if on_batch is not None:
                on_batch(len(idx))
        return out


# ── text lookup ──────────────────────────────────────────────────────────────

def load_texts(store: Path, keys: set, *, view: str = "ctx-concat",
               canon: str = "raw") -> dict:
    """Fetch full node text for the shortlist keys from the text store.

    The CSV only carries a 160-char snippet — enough to eyeball, far too little
    to adjudicate on. The cross-encoder reads the same view the retriever used,
    so a rerank of a ctx-concat run sees the graph context too.
    """
    column = V.column_for(view, canon == "canon")
    out: dict[str, str] = {}
    for sid in TS.list_shards(store):
        for row in TS.read_shard(store, sid):
            k = row.get("key")
            if k in keys and k not in out:
                out[k] = (row.get(column) or row.get("text_raw") or "").strip()
        if len(out) == len(keys):
            break
    return out


def main() -> None:
    import pandas as pd

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--in", dest="inp", required=True, help="candidate CSV (sweep schema)")
    ap.add_argument("--store", required=True, help="text store (for full node text)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="bge-reranker", choices=sorted(RERANKERS))
    ap.add_argument("--view", default="ctx-concat",
                    help="which text view the cross-encoder reads")
    ap.add_argument("--canon", choices=("raw", "canon"), default="raw")
    ap.add_argument("--top-per-problem", type=int, default=20,
                    help="rerank only this many candidates per problem — the "
                         "knob that keeps the per-pair stage affordable")
    ap.add_argument("--max-pairs", type=int, default=0, help="hard cap (0 = none)")
    ap.add_argument("--shard-id", type=int, default=None,
                    help="default $SLURM_ARRAY_TASK_ID; splits pairs across an array")
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--device", default=None)
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--max-tokens", type=int, default=None)
    ap.add_argument("--status-dir", default=None)
    ap.add_argument("--probe", action="store_true",
                    help="report pair counts and text coverage, load no model")
    args = ap.parse_args()

    df = pd.read_csv(args.inp, dtype=str)
    for c in ("problem_key", "theorem_key", "score"):
        if c not in df.columns:
            sys.exit(f"[rerank] {args.inp} has no '{c}' column")
    df["score"] = df["score"].astype(float)

    df = df.sort_values("score", ascending=False, kind="mergesort")
    if args.top_per_problem:
        df = df.groupby("problem_key", sort=False).head(args.top_per_problem)
    if args.max_pairs:
        df = df.head(args.max_pairs)
    df = df.reset_index(drop=True)

    env_task = os.environ.get("SLURM_ARRAY_TASK_ID")
    shard_id = args.shard_id if args.shard_id is not None else (
        int(env_task) if env_task is not None else None)
    if shard_id is not None and args.shards > 1:
        df = df.iloc[shard_id::args.shards].reset_index(drop=True)

    keys = set(df.problem_key) | set(df.theorem_key)
    t0 = time.time()
    texts = load_texts(Path(args.store), keys, view=args.view, canon=args.canon)
    missing = len(keys) - len(texts)
    banner("rerank", pairs=len(df), nodes=len(keys), text_missing=missing,
           model=args.model, view=args.view, canon=args.canon,
           lookup_s=round(time.time() - t0, 1))
    if missing:
        print(f"[rerank] WARNING: {missing} node(s) absent from the text store — "
              f"their pairs fall back to the CSV snippet, which is far less "
              f"information than the model expects", file=sys.stderr, flush=True)

    if args.probe:
        print("[rerank] --probe: no model loaded, nothing scored", file=sys.stderr)
        return

    def _text(key: str, snippet: str) -> str:
        return texts.get(key) or (snippet or "")

    pairs = [(_text(r.problem_key, getattr(r, "problem_snippet", "")),
              _text(r.theorem_key, getattr(r, "theorem_snippet", "")))
             for r in df.itertuples(index=False)]

    ce = CrossEncoder(get_card(args.model), device=args.device,
                      batch_size=args.batch_size, max_tokens=args.max_tokens)
    status_dir = Path(args.status_dir) if args.status_dir else Path(args.out).parent / "status"
    hb = Heartbeat("rerank", total=len(pairs), unit="pairs", status_dir=status_dir,
                   every=500, extra={"model": args.model,
                                     "shard": shard_id if shard_id is not None else 0})
    t0 = time.time()
    scores = ce.score(pairs, on_batch=lambda n: hb.tick(n))
    hb.close()

    df["retrieval_score"] = df["score"]
    df["retrieval_rank"] = (df.groupby("problem_key")["score"]
                              .rank(method="first", ascending=False).astype(int))
    df["rerank_score"] = scores
    # 'score' stays the operative ranking column so downstream consumers
    # (triage_open.py, batch_o4.py) need no knowledge of this stage at all.
    df["score"] = df["rerank_score"]
    df["method"] = f"rerank-{args.model}"
    df = df.sort_values(["score", "problem_key", "theorem_key"],
                        ascending=[False, True, True], kind="mergesort")

    out = Path(args.out)
    if shard_id is not None and args.shards > 1:
        out = out.with_name(f"{out.stem}.part{shard_id:03d}{out.suffix}")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    dt = time.time() - t0
    moved = int((df.retrieval_rank != df.groupby("problem_key")["score"]
                 .rank(method="first", ascending=False).astype(int)).sum())
    print(f"[rerank] {len(df):,} pairs in {dt:.0f}s ({len(df)/max(dt,1e-9):.1f}/s); "
          f"{moved:,} changed rank within their problem -> {out}",
          file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
