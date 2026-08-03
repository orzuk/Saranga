"""Embedder / reranker registry.

Every backbone we compare is one ``ModelCard``. Putting the awkward per-model
details (instruction prefixes, pooling, context window, batch size) in data
rather than in branching code means adding a seventh model is a dict entry, and
means "±instruction prefix" is a free ablation row instead of a code change.

Roster rationale — this is a comparison table for the paper, not a single choice:

  minilm       the cheap floor, and the only one that runs on a GPU-less Mac.
  distilbert   raw DistilBERT mean-pooled, NOT sentence-tuned. The naive
               "just use BERT" reference point. It is expected to do badly;
               showing that is the point, since it is the obvious thing to try.
  specter2     tuned on scientific documents + citation signal.
  bge-m3       strong general retriever, 8k context (matters for ctx-concat).
  qwen3-0.6b   instruction-aware, asymmetric query/doc encoding.
  qwen3-4b     the ceiling; benchmark-only unless it wins outright.

NOTHING HERE IS ASSUMED PRESENT. Run ``python -m embed.models --check`` on the
target machine first: it loads each card, reports the real embedding dim and a
measured throughput, and tells you which ones are missing from the HF cache.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))


# ── cards ────────────────────────────────────────────────────────────────────

#: Task string for instruction-tuned encoders. Phrased as the actual retrieval
#: task so the model conditions on "resolve", not on generic similarity.
OPEN_TASK = ("Given a stated open mathematical problem or conjecture, retrieve "
             "theorems that resolve it")


@dataclass(frozen=True)
class ModelCard:
    key: str
    hf_id: str
    backend: str = "st"          # st | hf-mean | hf-cls | ce (cross-encoder)
    dim: int = 0                 # documentation/estimate; the real dim is measured at load
    max_tokens: int = 512        # model's usable window; encode.py may cap lower
    batch_size: int = 64
    query_instruction: str = ""  # asymmetric encoders only
    doc_instruction: str = ""
    normalize: bool = True
    trust_remote_code: bool = False
    notes: str = ""

    def render(self, text: str, role: str) -> str:
        """Apply the model's query/document instruction wrapper."""
        instr = self.query_instruction if role == "query" else self.doc_instruction
        return f"{instr}{text}" if instr else text


EMBEDDERS: dict[str, ModelCard] = {
    "minilm": ModelCard(
        key="minilm", hf_id="sentence-transformers/all-MiniLM-L6-v2",
        backend="st", dim=384, max_tokens=256, batch_size=128,
        notes="22M params; CPU-viable. The local/Mac profile and the cost floor.",
    ),
    "distilbert": ModelCard(
        key="distilbert", hf_id="distilbert-base-uncased",
        backend="hf-mean", dim=768, max_tokens=512, batch_size=64,
        notes="NOT sentence-tuned. Deliberate naive-BERT baseline.",
    ),
    "specter2": ModelCard(
        key="specter2", hf_id="allenai/specter2_base",
        backend="hf-cls", dim=768, max_tokens=512, batch_size=64,
        notes="Scientific-document encoder; CLS-pooled. Base model, no adapter.",
    ),
    "bge-m3": ModelCard(
        key="bge-m3", hf_id="BAAI/bge-m3",
        backend="st", dim=1024, max_tokens=1024, batch_size=32,
        notes="568M; 8k window (capped here for speed). Symmetric, no prefix.",
    ),
    "qwen3-0.6b": ModelCard(
        key="qwen3-0.6b", hf_id="Qwen/Qwen3-Embedding-0.6B",
        backend="st", dim=1024, max_tokens=1024, batch_size=32,
        query_instruction=f"Instruct: {OPEN_TASK}\nQuery: ",
        trust_remote_code=True,
        notes="Instruction-aware and asymmetric: problems get the prefix, "
              "theorems go in bare. Drop the prefix for the ±instruction ablation.",
    ),
    "qwen3-4b": ModelCard(
        key="qwen3-4b", hf_id="Qwen/Qwen3-Embedding-4B",
        backend="st", dim=2560, max_tokens=1024, batch_size=8,
        query_instruction=f"Instruct: {OPEN_TASK}\nQuery: ",
        trust_remote_code=True,
        notes="Ceiling model. Tier-A benchmark only unless it wins outright.",
    ),
}

RERANKERS: dict[str, ModelCard] = {
    "minilm-ce": ModelCard(
        key="minilm-ce", hf_id="cross-encoder/ms-marco-MiniLM-L-6-v2",
        backend="ce", max_tokens=512, batch_size=64,
        notes="22M cross-encoder. CPU-viable (the local test path) and the cheap "
              "reranker baseline: shows how much of the rerank gain needs a big model.",
    ),
    "bge-reranker": ModelCard(
        key="bge-reranker", hf_id="BAAI/bge-reranker-v2-m3",
        backend="ce", max_tokens=1024, batch_size=32,
        notes="Cross-encoder; scores a (problem, theorem) pair jointly.",
    ),
    "qwen3-reranker": ModelCard(
        key="qwen3-reranker", hf_id="Qwen/Qwen3-Reranker-0.6B",
        backend="ce", max_tokens=1024, batch_size=16, trust_remote_code=True,
        notes="Instruction-following reranker; yes/no logit as the score.",
    ),
}

#: The Tier-A factorial roster. qwen3-4b is opt-in (--models all).
DEFAULT_ROSTER = ("minilm", "distilbert", "specter2", "bge-m3", "qwen3-0.6b")
LOCAL_ROSTER = ("minilm",)


def get_card(key: str) -> ModelCard:
    if key in EMBEDDERS:
        return EMBEDDERS[key]
    if key in RERANKERS:
        return RERANKERS[key]
    raise KeyError(f"unknown model {key!r}; known: "
                   f"{', '.join(sorted(EMBEDDERS) + sorted(RERANKERS))}")


# ── device / dtype ───────────────────────────────────────────────────────────

def pick_device(requested: Optional[str] = None) -> str:
    if requested and requested != "auto":
        return requested
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    # MPS is available on this Mac but is slower than CPU for these tiny batches
    # and has had silent-NaN issues in fp16; the local profile stays on CPU.
    return "cpu"


def pick_dtype(device: str, requested: str = "auto"):
    import torch
    if requested == "auto":
        return torch.float16 if device.startswith("cuda") else torch.float32
    return getattr(torch, requested)


# ── embedder ─────────────────────────────────────────────────────────────────

class Embedder:
    """Loads a card and turns text into L2-normalized float16 vectors.

    float16 storage halves the vector store (1.6M x 1024 x 4B = 6.5GB -> 3.3GB)
    and costs nothing: cosine similarity of unit vectors is well within fp16's
    precision for a top-k ranking, and the matmul runs in fp16 on tensor cores
    anyway. Ranking-relevant differences are ~1e-2, fp16 resolution is ~1e-3.
    """

    def __init__(self, card: ModelCard, *, device: Optional[str] = None,
                 dtype: str = "auto", batch_size: Optional[int] = None,
                 max_tokens: Optional[int] = None) -> None:
        self.card = card
        self.device = pick_device(device)
        self.batch_size = batch_size or card.batch_size
        self.max_tokens = max_tokens or card.max_tokens
        self._dtype_req = dtype
        self._model = None
        self._tok = None
        self.dim: Optional[int] = None

    # -- loading -------------------------------------------------------------

    def load(self) -> "Embedder":
        if self._model is not None:
            return self
        import torch
        t0 = time.time()
        dtype = pick_dtype(self.device, self._dtype_req)
        if self.card.backend == "st":
            from sentence_transformers import SentenceTransformer
            kw = {"device": self.device,
                  "trust_remote_code": self.card.trust_remote_code}
            self._model = SentenceTransformer(self.card.hf_id, **kw)
            self._model.max_seq_length = min(self.max_tokens,
                                             self._model.max_seq_length or self.max_tokens)
            if self.device.startswith("cuda"):
                self._model = self._model.half()
            self.dim = int(self._model.get_sentence_embedding_dimension())
        else:
            from transformers import AutoModel, AutoTokenizer
            self._tok = AutoTokenizer.from_pretrained(
                self.card.hf_id, trust_remote_code=self.card.trust_remote_code)
            self._model = AutoModel.from_pretrained(
                self.card.hf_id, torch_dtype=dtype,
                trust_remote_code=self.card.trust_remote_code).to(self.device).eval()
            self.dim = int(self._model.config.hidden_size)
        print(f"[embed] loaded {self.card.key} ({self.card.hf_id}) dim={self.dim} "
              f"device={self.device} in {time.time() - t0:.1f}s", file=sys.stderr, flush=True)
        return self

    # -- encoding ------------------------------------------------------------

    def _encode_hf(self, texts: Sequence[str]) -> np.ndarray:
        import torch
        enc = self._tok(list(texts), padding=True, truncation=True,
                        max_length=self.max_tokens, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self._model(**enc).last_hidden_state
        if self.card.backend == "hf-cls":
            vecs = out[:, 0]
        else:  # mean pooling over real tokens only — padding must not dilute it
            mask = enc["attention_mask"].unsqueeze(-1).to(out.dtype)
            vecs = (out * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return vecs.float().cpu().numpy()

    def _encode_st(self, texts: Sequence[str]) -> np.ndarray:
        return self._model.encode(
            list(texts), batch_size=len(texts), convert_to_numpy=True,
            normalize_embeddings=False, show_progress_bar=False)

    def encode(
        self,
        texts: Sequence[str],
        *,
        role: str = "doc",
        on_batch: Optional[Callable[[int], None]] = None,
    ) -> np.ndarray:
        """Encode texts -> (n, dim) float16, L2-normalized, in INPUT order.

        Batches are formed over length-sorted texts and scattered back. Math
        statements vary from 10 to 800 tokens; without sorting every batch pads
        to its longest member and most of the GPU's work is spent on padding.
        Sorting typically buys 2-4x on this corpus. The scatter-back makes the
        reordering invisible to callers, so vectors always line up with keys.
        """
        self.load()
        n = len(texts)
        if n == 0:
            return np.zeros((0, self.dim or 0), dtype=np.float16)
        rendered = [self.card.render(t or " ", role) for t in texts]
        order = sorted(range(n), key=lambda i: len(rendered[i]))
        out: Optional[np.ndarray] = None
        for start in range(0, n, self.batch_size):
            idx = order[start:start + self.batch_size]
            batch = [rendered[i] for i in idx]
            vecs = (self._encode_st(batch) if self.card.backend == "st"
                    else self._encode_hf(batch))
            vecs = np.asarray(vecs, dtype=np.float32)
            if out is None:
                out = np.zeros((n, vecs.shape[1]), dtype=np.float32)
            out[idx] = vecs
            if on_batch is not None:
                on_batch(len(idx))
        if self.card.normalize:
            norms = np.linalg.norm(out, axis=1, keepdims=True)
            out = out / np.maximum(norms, 1e-12)
        return out.astype(np.float16)


# ── availability check ───────────────────────────────────────────────────────

_PROBE = [
    "[conjecture] It remains open whether every 3-connected cubic graph has a "
    "Hamiltonian cycle when the girth is at least 5.",
    "[theorem] Every 3-connected cubic graph of girth at least 5 admits a "
    "Hamiltonian cycle.",
    "[lemma] The determinant of a positive definite matrix is strictly positive.",
]


def check(keys: Sequence[str], *, device: Optional[str] = None,
          batch_size: Optional[int] = None, probe_n: int = 3,
          corpus_nodes: int = 1_589_327) -> int:
    """Load each card; report real dim, MEASURED throughput, and a sanity check.

    Run this on the cluster BEFORE launching an encode array — a missing model
    should fail in 30 seconds here, not four hours into a job array.

    With ``probe_n`` above a few hundred the texts/s figure becomes a usable
    planning number rather than a warm-up artifact, so we also project how long
    the full corpus would take at that rate. That projection is the number worth
    writing down: everything downstream is scheduled around it.
    """
    failures = 0
    for key in keys:
        card = get_card(key)
        try:
            emb = Embedder(card, device=device, batch_size=batch_size).load()
            # correctness probe: [0] and [1] are the same claim, [2] is unrelated
            vecs = emb.encode(_PROBE, role="doc")
            rel = float(vecs[0].astype(np.float32) @ vecs[1].astype(np.float32))
            unrel = float(vecs[0].astype(np.float32) @ vecs[2].astype(np.float32))
            flag = "ok" if rel > unrel else "SUSPECT (unrelated scored higher)"

            # throughput on a batch big enough to amortise warm-up
            batch = (_PROBE * ((probe_n // len(_PROBE)) + 1))[:max(probe_n, len(_PROBE))]
            t0 = time.time()
            emb.encode(batch, role="doc")
            dt = max(time.time() - t0, 1e-9)
            rate = len(batch) / dt
            eta_h = corpus_nodes / rate / 3600.0
            print(f"  {key:<13} dim={emb.dim:<5} {rate:8.1f} texts/s  "
                  f"→ {eta_h:5.2f} h for {corpus_nodes:,} nodes   "
                  f"rel={rel:.3f} unrel={unrel:.3f}  {flag}")
        except Exception as exc:
            failures += 1
            print(f"  {key:<13} UNAVAILABLE: {type(exc).__name__}: {exc}")
    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="probe model availability")
    ap.add_argument("--models", default=",".join(DEFAULT_ROSTER),
                    help="comma-separated keys, or 'all' / 'embedders' / 'rerankers'")
    ap.add_argument("--device", default=None)
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--probe-n", type=int, default=3,
                    help="texts to encode when timing. Use 512+ on a GPU for a "
                         "throughput number you can actually plan around")
    ap.add_argument("--corpus-nodes", type=int, default=1_589_327,
                    help="corpus size used for the 'hours for a full pass' projection")
    ap.add_argument("--list", action="store_true", help="print the registry and exit")
    args = ap.parse_args()

    if args.list or not args.check:
        print("EMBEDDERS")
        for c in EMBEDDERS.values():
            print(f"  {c.key:<13} {c.hf_id:<42} dim~{c.dim:<5} ctx={c.max_tokens:<6} {c.notes}")
        print("RERANKERS")
        for c in RERANKERS.values():
            print(f"  {c.key:<13} {c.hf_id:<42} ctx={c.max_tokens:<6} {c.notes}")
        if not args.check:
            return

    sel = args.models
    if sel == "all":
        keys = list(EMBEDDERS) + list(RERANKERS)
    elif sel == "embedders":
        keys = list(EMBEDDERS)
    elif sel == "rerankers":
        keys = list(RERANKERS)
    else:
        keys = [k.strip() for k in sel.split(",") if k.strip()]
    print(f"checking {len(keys)} model(s) on device={pick_device(args.device)}, "
          f"timing on {args.probe_n} text(s)")
    failures = check(keys, device=args.device, batch_size=args.batch_size,
                     probe_n=args.probe_n, corpus_nodes=args.corpus_nodes)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
