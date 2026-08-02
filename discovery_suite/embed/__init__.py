"""Shared embedding engine for the discovery suite.

One place where "turn a typed math node into a vector" is defined, so T-OPEN,
T-PLAG and T-ALIGN all retrieve over the same substrate (ROADMAP §0/§7.2).

Stages, each a standalone resumable CLI:

    textstore.py  corpus JSONs -> sharded text store (raw + canonical, node + graph context)
    encode.py     text shard   -> fp16 L2-normalized vectors
    index.py      vectors      -> top-k neighbours (flat-gpu | numpy-flat | faiss)
    fuse.py       CSVs         -> fused ranking (RRF / z-norm linear / max)

Nothing here is task-specific: the T-OPEN head lives in ``open_problems/``.
"""
