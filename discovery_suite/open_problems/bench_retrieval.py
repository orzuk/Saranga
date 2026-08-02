"""Tier-A benchmark — which retrieval arm actually finds resolutions?

This is the comparison the paper reports. It runs the full factorial over

    embedder  x  view (node | ctx-concat | ctx-late | concepts-only)
              x  canonicalization (raw | canon | fused)
              x  fusion (dense alone | hybrid with the lexical sweep)

on a small slice with KNOWN answers, scores every arm with the suite's existing
``eval_harness/scorer.evaluate``, and writes one row per arm. Only the winners
are ever run over the full corpus (Tier B) — that two-tier split is what keeps a
40-arm factorial affordable.

    python discovery_suite/open_problems/bench_retrieval.py \
        --papers 300 --models minilm --views node,ctx-concat --canons raw,canon \
        --out discovery_suite/open_problems/runs/bench_matrix.csv

The headline output is the detection-vs-obfuscation curve: recall at L0 (verbatim)
through L4 (conceptual). Lexical matching is expected to win or tie at L0 and
collapse by L2; if the embedders don't hold up as obfuscation rises, they are not
buying anything and that is the honest result to report.

PLANTING NOTE. ``eval_harness/open_planter.plant_twins`` poses its synthetic
problems from ``clean_text``, which the base parser masks to ``[MATH]``. Retrieval
(both arms, since sweep_open's ``--text-source raw`` fix) reads math-preserving
``raw_latex``. Planting from the masked field therefore measures retrieval against
text no method actually indexes, and penalizes the canonical arm hardest — there
is no notation left to canonicalize. ``--planter mathaware`` (the default) poses
from the same source retrieval sees; ``--planter legacy`` reproduces the old
behaviour for comparison.
"""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
for _p in (_SUITE, _HERE, _SUITE / "eval_harness", _SUITE / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.corpus import load_papers, node_norm_text  # noqa: E402
from embed import index as IDX, views as V  # noqa: E402
from embed.models import EMBEDDERS, Embedder, get_card  # noqa: E402
from embed.progress import banner  # noqa: E402
from embed.fuse import fuse  # noqa: E402
from eval_harness.open_planter import OpenTwin, PlantedOpen, plant_twins  # noqa: E402
from eval_harness.obfuscate import obfuscate  # noqa: E402
from eval_harness.scorer import evaluate  # noqa: E402
from o1_retrieve import THEOREM_TYPES, _jaccard  # noqa: E402

KS = (10, 50, 100, 500)


# ── planting ─────────────────────────────────────────────────────────────────

def plant_mathaware(
    papers: Sequence,
    *,
    n_twins: int = 40,
    levels: Sequence[str] = ("L0", "L1", "L2"),
    min_words: int = 12,
    seed: int = 11,
    paraphraser=None,
) -> PlantedOpen:
    """Same protocol as open_planter.plant_twins, sourced from ``raw_latex``.

    Take a real theorem T in paper P, pose it as an open problem in a DIFFERENT,
    EARLIER paper Q, and obfuscate the phrasing. Gold = (planted problem in Q, T
    in P). The only change from the original is where the statement text comes
    from: ``views._clean(raw_latex)``, i.e. exactly what every retrieval arm
    indexes, instead of the ``[MATH]``-masked ``clean_text``.
    """
    rng = random.Random(seed)
    aug = [copy.copy(p) for p in papers]
    for p in aug:
        p.nodes = [dict(n) for n in p.nodes]

    theorems = [(p, n) for p in aug for n in p.nodes
                if (n.get("type") or "").lower() in THEOREM_TYPES
                and len(V._clean(V._node_source_latex(n)).split()) >= min_words]
    if not theorems:
        raise ValueError("no eligible theorem nodes to seed twins")

    gold: list[OpenTwin] = []
    for i in range(n_twins):
        level = levels[i % len(levels)]
        src_paper, thm = rng.choice(theorems)
        cands = [p for p in aug if p.paper_id != src_paper.paper_id
                 and p.year <= src_paper.year]
        if not cands:
            continue
        tgt = rng.choice(cands)

        stmt = V._clean(V._node_source_latex(thm))
        posed = obfuscate(
            f"It remains an open problem whether the following holds. {stmt}",
            level, seed=seed + i, paraphraser=paraphraser)
        pid = f"OPENTWIN_{i}_{thm.get('id')}"
        # raw_latex too: _node_source_latex prefers it, so writing only
        # statement/clean_text would leave the planted node's indexed text
        # depending on field-precedence rather than on what we planted.
        tgt.nodes.append({"id": pid, "type": "open_problem",
                          "name": "Planted open problem", "statement": posed,
                          "clean_text": posed, "raw_latex": posed, "_planted": True})
        gold.append(OpenTwin(problem_paper_id=tgt.paper_id, problem_node_id=pid,
                             theorem_paper_id=src_paper.paper_id,
                             theorem_node_id=str(thm.get("id")), level=level))
    return PlantedOpen(papers=aug, gold=gold)


# ── arms ─────────────────────────────────────────────────────────────────────

@dataclass
class Arm:
    name: str
    preds: list           # (problem_key, theorem_key, score)
    encode_s: float = 0.0
    search_s: float = 0.0
    n_texts: int = 0
    extra: dict = field(default_factory=dict)


def _records(papers, *, with_canon: bool, ctx_depth: int, max_neighbours: int,
             max_ctx_chars: int) -> list:
    recs = []
    for p in papers:
        recs.extend(V.paper_records(p, with_canon=with_canon, ctx_depth=ctx_depth,
                                    max_neighbours=max_neighbours,
                                    max_ctx_chars=max_ctx_chars))
    return recs


def lexical_arm(papers, *, top_k: int, prefer_raw: bool = True) -> Arm:
    """The baseline: token Jaccard, exactly as sweep_open.py scores it.

    Reimplemented in ten lines rather than calling o1_retrieve.retrieve because
    that entry point hardcodes the masked text source; sweep_open's production
    default is ``--text-source raw``, and the baseline has to be the thing we
    actually run or the comparison is against a straw man.
    """
    t0 = time.time()
    problems, theorems = [], []
    for p in papers:
        for n in p.nodes:
            t = (n.get("type") or "").lower()
            if t not in V.QUERY_TYPES and t not in THEOREM_TYPES:
                continue
            toks = set(node_norm_text(n, prefer_raw=prefer_raw).split())
            if len(toks) < 6:
                continue
            rec = (f"{p.paper_id}::{n.get('id')}", p.paper_id, p.year, toks)
            (problems if t in V.QUERY_TYPES else theorems).append(rec)
    preds = []
    for pk, ppid, pyear, ptoks in problems:
        scored = [(tk, _jaccard(ptoks, ttoks)) for tk, tpid, tyear, ttoks in theorems
                  if tpid != ppid and tyear >= pyear]
        scored = [x for x in scored if x[1] > 0]
        scored.sort(key=lambda x: (-x[1], x[0]))
        preds.extend((pk, tk, s) for tk, s in scored[:top_k])
    preds.sort(key=lambda x: -x[2])
    return Arm(name="lexical-jaccard", preds=preds, search_s=time.time() - t0,
               n_texts=len(problems) + len(theorems))


def dense_arm(recs, embedder: Embedder, *, view: str, canon: str, top_k: int,
              alpha: float, cache: dict) -> Arm:
    """One (model, view, canon) retrieval arm over in-memory records."""
    column = V.column_for(view, canon == "canon")
    enc_view = "node" if view in V.VECTOR_VIEWS else view
    # Key the cache on the COLUMN, not on the canon flag: concepts-only reads the
    # same column either way (canonicalization does nothing to a list of concept
    # names), so keying on canon would pay for an identical encode twice.
    ck = (embedder.card.key, enc_view, column)

    fresh = ck not in cache
    n_fallback = 0
    if fresh:
        texts, metas = [], []
        for r in recs:
            row = r.as_row()
            t = (row.get(column) or "").strip()
            if not t:
                # concepts-only in particular is empty for ungrounded nodes; an
                # empty string embeds to a near-constant vector that matches
                # everything, so fall back to the node text and report the rate.
                t = row.get("text_raw") or ""
                n_fallback += 1
            texts.append(t)
            metas.append({**{k: row.get(k) for k in
                             ("key", "paper_id", "year", "yymm", "category",
                              "ntype", "role", "ctx_keys", "ctx_weights")},
                          "snippet": " ".join(t.split())[:180]})
        t0 = time.time()
        q_idx = [i for i, m in enumerate(metas) if m["role"] == "query"]
        d_idx = [i for i, m in enumerate(metas) if m["role"] != "query"]
        vecs = None
        for idx, role in ((q_idx, "query"), (d_idx, "doc")):
            if not idx:
                continue
            v = embedder.encode([texts[i] for i in idx], role=role)
            if vecs is None:
                vecs = np.zeros((len(texts), v.shape[1]), dtype=np.float16)
            vecs[idx] = v
        cache[ck] = (vecs, metas, time.time() - t0, len(texts),
                     n_fallback / max(len(texts), 1))
    vecs, metas, cached_enc_s, n_texts, fallback_frac = cache[ck]
    # Only the arm that actually paid for the encoding reports its cost; later
    # arms reusing the cached vectors would otherwise inflate the cost column.
    enc_s = cached_enc_s if fresh else 0.0

    t0 = time.time()
    use = IDX.build_ctx_late(vecs, metas, alpha=alpha) if view == "ctx-late" else vecs
    q_sel = [i for i, m in enumerate(metas) if m["role"] == "query"]
    d_sel = [i for i, m in enumerate(metas) if m["role"] == "doc"]
    if not q_sel or not d_sel:
        return Arm(name=f"{embedder.card.key}/{view}/{canon}", preds=[])
    q = IDX.QuerySide(np.asarray(use)[q_sel], [metas[i] for i in q_sel])
    d_metas = [metas[i] for i in d_sel]
    doc_idx, scores = IDX.search_shard(q, np.asarray(use)[d_sel], d_metas,
                                       k=top_k, backend="auto")
    preds = []
    for qi in range(len(q)):
        for j in range(doc_idx.shape[1]):
            di = int(doc_idx[qi, j])
            if di < 0:
                continue
            preds.append((q.keys[qi], d_metas[di]["key"], float(scores[qi, j])))
    preds.sort(key=lambda x: -x[2])
    name = f"{embedder.card.key}/{view}/{canon}"
    if view == "ctx-late":
        name += f"/a{alpha:g}"
    return Arm(name=name, preds=preds, encode_s=enc_s, search_s=time.time() - t0,
               n_texts=n_texts, extra={"fallback_frac": round(fallback_frac, 3)})


def fuse_arms(arms: Sequence[Arm], name: str, *, method: str = "rrf",
              weights=None, top_k: int = 50) -> Arm:
    """Score-level fusion of two or more arms, via embed.fuse (one implementation)."""
    import pandas as pd
    frames = []
    for a in arms:
        if not a.preds:
            continue
        df = pd.DataFrame(a.preds, columns=["problem_key", "theorem_key", "score"])
        df["arm"] = a.name
        df["rank"] = (df.groupby("problem_key")["score"]
                        .rank(method="first", ascending=False).astype(int))
        frames.append(df)
    if len(frames) < 2:
        return Arm(name=name, preds=list(arms[0].preds) if arms else [])
    fused = fuse(frames, method=method, weights=weights,
                 top_per_problem=top_k, rescale=True)
    preds = list(fused[["problem_key", "theorem_key", "score"]]
                 .itertuples(index=False, name=None))
    preds.sort(key=lambda x: -x[2])
    return Arm(name=name, preds=preds,
               encode_s=sum(a.encode_s for a in arms),
               search_s=sum(a.search_s for a in arms))


# ── scoring ──────────────────────────────────────────────────────────────────

def _mrr(preds, gold_pairs, gold_problem_keys) -> float:
    """Mean reciprocal rank of the first correct hit, per planted problem.

    Complements AP: the shortlist handed to an expensive LLM judge is truncated
    per problem, so where the FIRST right answer lands *within a problem's own
    candidate list* is the operationally relevant quantity. A problem whose
    resolution is never retrieved contributes 0, so the denominator is the count
    of planted problems, not the count of problems that happened to get a hit.
    """
    rank_in_problem: dict[str, int] = {}
    first_hit: dict[str, int] = {}
    for pk, tk, _s in preds:
        r = rank_in_problem.get(pk, 0) + 1
        rank_in_problem[pk] = r
        if pk not in first_hit and frozenset({pk, tk}) in gold_pairs:
            first_hit[pk] = r
    n = len(gold_problem_keys) or 1
    return sum(1.0 / r for r in first_hit.values()) / n


def load_judged(path: Path, *, keys_present: set) -> tuple[set, dict, set]:
    """Real (non-synthetic) gold from the Opus verdicts on the lexical top-166.

    YES/PARTIAL are positives, NO are hard negatives — and they are *hard*: every
    one of them was ranked in the lexical top-166, so they are exactly the
    surface-similar-but-wrong pairs an embedder must also learn to rank down.

    Two honest caveats, both reported by the caller:
      * these pairs were FOUND by token Jaccard, so recall measured on them is
        biased toward the lexical arm. They test precision/ranking, not recall.
      * only pairs whose BOTH nodes exist in the current slice can be scored;
        on a small local slice that is usually none, which is why the planted
        twins remain the primary metric.
    """
    import pandas as pd
    df = pd.read_csv(path, dtype=str)
    pos, neg, levels = set(), set(), {}
    for r in df.itertuples(index=False):
        if r.problem_key not in keys_present or r.theorem_key not in keys_present:
            continue
        pair = frozenset({r.problem_key, r.theorem_key})
        if str(r.verdict).upper() in ("YES", "PARTIAL"):
            pos.add(pair)
            levels[pair] = "judged"
        else:
            neg.add(pair)
    return pos, levels, neg


def _markdown_table(df) -> str:
    """Render a DataFrame as a GitHub markdown table.

    Hand-rolled rather than DataFrame.to_markdown, which needs the optional
    `tabulate` package — not installed here, and a missing formatting dependency
    should never be able to lose a completed benchmark run.
    """
    cols = list(df.columns)
    rows = [[("" if v is None or (isinstance(v, float) and v != v) else str(v))
             for v in rec] for rec in df.itertuples(index=False, name=None)]
    widths = [max(len(c), *(len(r[i]) for r in rows)) if rows else len(c)
              for i, c in enumerate(cols)]
    head = "| " + " | ".join(c.ljust(w) for c, w in zip(cols, widths)) + " |"
    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    body = ["| " + " | ".join(v.ljust(w) for v, w in zip(r, widths)) + " |" for r in rows]
    return "\n".join([head, sep] + body)


def _hard_neg_rate(preds, hard_negs, k: int = 50) -> Optional[float]:
    """Fraction of judged-NO pairs the arm still ranks in a problem's top-k.

    LOWER IS BETTER. These 154 pairs all scored highly under token Jaccard and
    Opus then rejected every one — they are the surface-similar traps that make
    up 93% of the current shortlist. An arm that finds new true positives but
    keeps all the old traps has not improved the shortlist a judge has to read.
    """
    if not hard_negs:
        return None
    seen: dict[str, int] = {}
    caught = set()
    for pk, tk, _s in preds:
        r = seen.get(pk, 0) + 1
        seen[pk] = r
        if r <= k and frozenset({pk, tk}) in hard_negs:
            caught.add(frozenset({pk, tk}))
    return round(len(caught) / len(hard_negs), 4)


def score_arm(arm: Arm, gold_pairs, gold_levels, gold_problem_keys,
              hard_negs=None) -> dict:
    res = evaluate(arm.preds, gold_pairs, gold_levels=gold_levels, ks=KS)
    row = {
        "arm": arm.name,
        "n_pred": res.n_pred,
        "n_gold": res.n_gold,
        "AP": round(res.average_precision, 4),
        "MRR": round(_mrr(arm.preds, gold_pairs, gold_problem_keys), 4),
        "encode_s": round(arm.encode_s, 1),
        "search_s": round(arm.search_s, 2),
        "texts_per_s": (round(arm.n_texts / arm.encode_s, 1)
                        if arm.encode_s > 0 and arm.n_texts else None),
    }
    for k in KS:
        row[f"P@{k}"] = round(res.precision_at_k.get(k, 0.0), 4)
        row[f"R@{k}"] = round(res.recall_at_k.get(k, 0.0), 4)
    for lv, v in sorted(res.recall_by_level.items()):
        row[f"recall_{lv}"] = round(v, 4)
    hn = _hard_neg_rate(arm.preds, hard_negs)
    if hn is not None:
        row["hardneg@50"] = hn
    row.update(arm.extra)
    return row


# ── driver ───────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=None, help="corpus root (default: portal tier3)")
    ap.add_argument("--papers", type=int, default=300)
    ap.add_argument("--categories", default=None)
    ap.add_argument("--models", default="minilm",
                    help=f"comma-separated; known: {','.join(sorted(EMBEDDERS))}")
    ap.add_argument("--views", default="node,ctx-concat,ctx-late,concepts-only")
    ap.add_argument("--canons", default="raw,canon")
    ap.add_argument("--alphas", default="0.7",
                    help="ctx-late mixing weights to sweep (no re-encoding)")
    ap.add_argument("--levels", default="L0,L1,L2",
                    help="obfuscation levels to plant. WITHOUT --llm, L2+ falls "
                         "back to rule-based scrambling that leaves most tokens "
                         "intact, so the twins stay lexically near-verbatim and "
                         "the curve says little about semantic matching")
    ap.add_argument("--llm", default=None, metavar="MODEL",
                    help="use eval_harness/llm_paraphrase for L2-L4 (e.g. 'haiku'). "
                         "This is what makes the detection-vs-obfuscation curve "
                         "measure paraphrase robustness rather than token noise. "
                         "Needs ANTHROPIC_API_KEY; responses are sqlite-cached")
    ap.add_argument("--twins", type=int, default=40)
    ap.add_argument("--top-k", type=int, default=50)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--planter", choices=("mathaware", "legacy"), default="mathaware")
    ap.add_argument("--judged", default=None, metavar="CSV",
                    help="o4_verdicts CSV (e.g. runs/o4_verdicts_all.csv). Adds the "
                         "real Opus-judged pairs whose nodes are in this slice as "
                         "gold positives (YES/PARTIAL) and hard negatives (NO). "
                         "These were surfaced BY the lexical arm, so they measure "
                         "ranking/precision, not recall")
    ap.add_argument("--no-lexical", action="store_true")
    ap.add_argument("--no-hybrid", action="store_true",
                    help="skip dense+lexical and raw+canon fusion arms")
    ap.add_argument("--device", default=None)
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--ctx-depth", type=int, default=1)
    ap.add_argument("--max-neighbours", type=int, default=4)
    ap.add_argument("--max-ctx-chars", type=int, default=600)
    ap.add_argument("--out", default=str(_HERE / "runs" / "bench_matrix.csv"))
    args = ap.parse_args()

    import pandas as pd

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    views = [v.strip() for v in args.views.split(",") if v.strip()]
    canons = [c.strip() for c in args.canons.split(",") if c.strip()]
    alphas = [float(a) for a in args.alphas.split(",") if a.strip()]
    levels = tuple(l.strip() for l in args.levels.split(",") if l.strip())
    cats = args.categories.split(",") if args.categories else None

    papers = load_papers(Path(args.root) if args.root else None,
                         limit=args.papers, categories=cats)
    if not papers:
        sys.exit("[bench] no papers loaded — check --root/--categories")

    paraphraser = None
    if args.llm:
        from eval_harness.llm_paraphrase import make_paraphraser
        # NB: do not forward a dry_run flag here — llm_paraphrase's dry_run
        # returns the input unchanged, which would silently make L2-L4 identical
        # to L0 and report a flat, meaningless curve.
        paraphraser = make_paraphraser(model=args.llm)
    elif any(l >= "L2" for l in levels):
        print("[bench] NOTE: L2+ planted without --llm uses the rule-based "
              "fallback (synonym swap / variable rename / sentence shuffle). It "
              "leaves most content words in place, so lexical matching will look "
              "strong at every level. Pass --llm haiku for a real paraphrase curve.",
              file=sys.stderr, flush=True)

    planter = plant_mathaware if args.planter == "mathaware" else plant_twins
    planted = planter(papers, n_twins=args.twins, levels=levels, seed=args.seed,
                      paraphraser=paraphraser)
    gold_pairs, gold_levels = planted.gold_pairs(), planted.gold_levels()

    need_canon = "canon" in canons
    recs = _records(planted.papers, with_canon=need_canon, ctx_depth=args.ctx_depth,
                    max_neighbours=args.max_neighbours, max_ctx_chars=args.max_ctx_chars)
    n_q = sum(1 for r in recs if r.role == "query")
    n_d = sum(1 for r in recs if r.role == "doc")

    n_judged_pos = n_judged_neg = 0
    jneg: set = set()
    if args.judged:
        present = {r.key for r in recs}
        jpos, jlevels, jneg = load_judged(Path(args.judged), keys_present=present)
        n_judged_pos, n_judged_neg = len(jpos), len(jneg)
        gold_pairs = set(gold_pairs) | jpos
        gold_levels = {**gold_levels, **jlevels}
        if not jpos and not jneg:
            print(f"[bench] --judged: none of the judged pairs have both nodes in "
                  f"this {len(papers)}-paper slice; scoring on planted twins only. "
                  f"Widen --papers or point --root at the full corpus to use them.",
                  file=sys.stderr, flush=True)
        else:
            print(f"[bench] --judged: +{n_judged_pos} real positives, "
                  f"{n_judged_neg} hard negatives in slice", file=sys.stderr, flush=True)
    banner("bench", papers=len(papers), gold_twins=len(planted.gold),
           records=len(recs), queries=n_q, docs=n_d,
           pairs_per_arm=n_q * n_d,
           arms=len(models) * len(views) * len(canons), levels=",".join(levels))

    arms: list[Arm] = []
    lex: Optional[Arm] = None
    if not args.no_lexical:
        lex = lexical_arm(planted.papers, top_k=args.top_k)
        arms.append(lex)
        print(f"[bench] lexical baseline: {len(lex.preds):,} pairs "
              f"in {lex.search_s:.1f}s", file=sys.stderr, flush=True)

    cache: dict = {}
    for mkey in models:
        emb = Embedder(get_card(mkey), device=args.device, batch_size=args.batch_size)
        per_canon: dict[tuple[str, str], Arm] = {}
        for view in views:
            for canon in canons:
                for alpha in (alphas if view == "ctx-late" else [1.0]):
                    t0 = time.time()
                    arm = dense_arm(recs, emb, view=view, canon=canon,
                                    top_k=args.top_k, alpha=alpha, cache=cache)
                    arms.append(arm)
                    per_canon[(view, canon)] = arm
                    print(f"[bench] {arm.name:<34} {len(arm.preds):>6,} pairs "
                          f"({time.time()-t0:.1f}s)", file=sys.stderr, flush=True)
            if not args.no_hybrid and len(canons) > 1:
                a, b = per_canon.get((view, "raw")), per_canon.get((view, "canon"))
                if a and b and a.preds and b.preds:
                    arms.append(fuse_arms([a, b], f"{mkey}/{view}/raw+canon-rrf",
                                          top_k=args.top_k))
        if not args.no_hybrid and lex is not None:
            for (view, canon), arm in per_canon.items():
                if arm.preds:
                    arms.append(fuse_arms(
                        [arm, lex], f"{mkey}/{view}/{canon}+lexical-rrf",
                        top_k=args.top_k))

    gold_problem_keys = {f"{g.problem_paper_id}::{g.problem_node_id}"
                         for g in planted.gold}
    if n_judged_pos:
        # A judged pair's problem side is whichever member is a query node.
        query_keys = {r.key for r in recs if r.role == "query"}
        gold_problem_keys |= {k for pair in gold_pairs for k in pair
                              if k in query_keys}
    rows = [score_arm(a, gold_pairs, gold_levels, gold_problem_keys, hard_negs=jneg)
            for a in arms if a.preds]
    df = pd.DataFrame(rows).sort_values("AP", ascending=False)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    lvl_cols = [c for c in df.columns if c.startswith("recall_")]
    extra_cols = [c for c in ("hardneg@50",) if c in df.columns]
    show = (["arm", "AP", "MRR", "R@50", "R@100"] + lvl_cols + extra_cols
            + ["encode_s", "texts_per_s"])
    print("\n" + df[show].to_string(index=False))
    print(f"\n[bench] {len(df)} arms -> {out}")

    md = out.with_suffix(".md")
    md.write_text(
        f"# T-OPEN retrieval benchmark\n\n"
        f"- papers: {len(papers)} | planted twins: {len(planted.gold)} "
        f"({', '.join(levels)}) | planter: {args.planter} "
        f"| paraphrase: {args.llm or 'rule-based (weak; see --llm)'}\n"
        f"- query nodes: {n_q} | doc nodes: {n_d} | top-k: {args.top_k}\n\n"
        + _markdown_table(df[show]) + "\n", encoding="utf-8")
    out.with_suffix(".meta.json").write_text(json.dumps({
        "papers": len(papers), "twins": len(planted.gold), "levels": list(levels),
        "planter": args.planter, "models": models, "views": views,
        "canons": canons, "alphas": alphas, "top_k": args.top_k,
        "seed": args.seed, "queries": n_q, "docs": n_d,
    }, indent=2), encoding="utf-8")
    print(f"[bench] markdown -> {md}")


if __name__ == "__main__":
    main()
