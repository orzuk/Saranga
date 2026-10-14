#!/usr/bin/env python3
"""Teacher-invented clues for alg3: the teacher proposes, the learner disposes.

From the tagger's out-of-fold predictions on the TRAINING papers (train.py
--dump-oof), collect, for each node type, the sentences it missed (silver nodes
of that type it did not find) and look-alikes it should not fire on (its false
positives of that type and the 'none' sentences it scored highest for it). The
teacher sees both and proposes regex clues that tell them apart. A clue is not
a rule: it is one more feature, and train.py decides its weight, so a weak or
partly wrong clue costs little. Validation papers are never shown to the
teacher; they only judge the retrained model.

    python3 alg3/invent.py --oof alg3/cache/oof_v2b.pkl --out alg3/clues_r1.json
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (HERE, REPO / "scripts", REPO / "src" / "LLMVersion", REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import distill_units as DU                                   # noqa: E402
import train as TR                                           # noqa: E402

try:
    import regex as RX
except ImportError:                                          # pragma: no cover
    RX = re

MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 0.10, 0.50                             # $ per million tokens

TYPES = {
    "definition": "introduces the meaning of a term, notation or symbol "
                  "(\"we call\", \"let X denote\", \"is said to be\", a defining equation)",
    "claim": "a mathematical assertion made in the running text, outside any theorem "
             "environment: a derived fact, a computed value, \"we obtain that ...\"",
    "remark": "a comment on the mathematics: an observation, explanation, caveat or side note",
    "proof": "an argument that establishes a result, written in running prose",
    "theorem": "a major result stated in prose, often attributed to other work "
               "(\"X proved that every ...\")",
    "algorithm": "a procedure or its steps described in prose",
    "example": "a concrete instance illustrating a notion or result",
    "assumption": "a standing hypothesis the text adopts (\"we assume throughout that ...\")",
    "problem": "a task or question the text poses",
    "open_problem": "a question explicitly described as open or unsolved",
}

SYSTEM = """You help build a rule-based extractor for mathematical papers written in LaTeX.

The extractor cuts the running prose of a paper into sentences and must decide, for each
sentence, whether it STARTS a node of a given type. A statistical learner combines many
yes/no CLUES about a sentence; your job is to invent new clues for cases it currently
gets wrong.

A clue is ONE Python regular expression, applied with re.search to the LaTeX source of a
single sentence. It does not have to be precise on its own: the learner weighs it against
all other evidence. It must be GENERAL: key on structure that recurs across papers
(phrasing, sentence openings, verbs, connectives, LaTeX markup like \\emph{...},
\\cite{...}, \\ref{...}, $...$, displayed equations, colons, enumerations), never on words
specific to one paper (names, notation, topic words).

Reply with ONLY a JSON array, no markdown fences, of 6 to 10 objects:
[{"name": "short_snake_case", "regex": "...", "flags": "i", "why": "few words"}]
Python `re` syntax; flags as letters ("i" ignore case, "s" dot matches newline).
In JSON, write every backslash of the regex doubled (\\\\b, \\\\emph).
"""


def short(s: str, n: int = 320) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n] + (" ..." if len(s) > n else "")


def spread(items, k, rnd):
    """Up to k items, round-robin over papers so no paper dominates."""
    by = defaultdict(list)
    for pid, txt in items:
        by[pid].append(txt)
    for v in by.values():
        rnd.shuffle(v)
    out, pids = [], sorted(by)
    rnd.shuffle(pids)
    while len(out) < k and any(by.values()):
        for pid in pids:
            if by[pid] and len(out) < k:
                out.append(by[pid].pop())
    return out


def collect(papers, oof, train, rnd):
    """Per type: (missed anchors, look-alikes) as (pid, sentence LaTeX)."""
    scorer = DU.Scorer({pid: p for pid, (_, p) in papers.items()}, 0.7, metric="m1g")
    missed, fps, hard = defaultdict(list), defaultdict(list), defaultdict(list)
    for pid in train:
        p = papers[pid][1]
        d = oof[pid]
        found_as = {}
        m = scorer.match(p, d["preds"], [TR.tokens(p, q) for q in d["preds"]])
        for q, pred in enumerate(d["preds"]):
            if q in m:
                found_as[m[q][0]] = pred["type"]
                continue
            i = next((j for j, s in enumerate(p.sents) if s.start == pred["start"]), None)
            if i is not None:
                fps[pred["type"]].append((pid, p.sent_text[i]))
        for k, n in enumerate(p.nodes):
            if n.base_covered:
                continue
            if found_as.get(k) != n.type:
                missed[n.type].append((pid, p.sent_text[n.first]))
        classes = d["classes"]
        anchors = set(p.anchor) | set(p.inside)
        for t in TYPES:
            if t not in classes:
                continue
            c = classes.index(t)
            cand = [(d["probs"][i][c], i) for i in range(len(p.sents)) if i not in anchors]
            cand.sort(reverse=True)
            hard[t] += [(pid, p.sent_text[i]) for _, i in cand[:3]]
    return missed, fps, hard


def ask(client, prompt: str, usage: dict) -> list:
    msg = client.messages.create(model=MODEL, max_tokens=4000, thinking={"type": "disabled"},
                                 system=SYSTEM, messages=[{"role": "user", "content": prompt}])
    usage["in"] += msg.usage.input_tokens
    usage["out"] += msg.usage.output_tokens
    usage["calls"] += 1
    if msg.stop_reason != "end_turn":
        print(f"    [warn] stop_reason={msg.stop_reason}", flush=True)
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    try:
        out = json.loads(text)
        return out if isinstance(out, list) else []
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.S)
        try:
            return json.loads(m.group(0)) if m else []
        except json.JSONDecodeError:
            print("    [warn] unparsable reply", flush=True)
            return []


def fires(pat, s: str) -> bool:
    try:
        if RX is not re:
            return pat.search(s, timeout=0.2) is not None
        return pat.search(s) is not None
    except Exception:                                        # noqa: BLE001
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "cache/papers.pkl"))
    ap.add_argument("--oof", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--prev", default=None, help="clues of an earlier round, kept and extended")
    ap.add_argument("--n-pos", type=int, default=30)
    ap.add_argument("--n-neg", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    import anthropic
    client = anthropic.Anthropic()
    rnd = random.Random(a.seed)
    papers = pickle.load(open(a.data, "rb"))
    oof = pickle.load(open(a.oof, "rb"))
    train = sorted(p for p, (s, _) in papers.items() if s == "train")
    assert set(oof) <= set(train), "out-of-fold predictions must be on training papers only"
    missed, fps, hard = collect(papers, oof, train, rnd)
    all_sents = [(pid, i, papers[pid][1].sent_text[i], papers[pid][1].anchor.get(i))
                 for pid in train for i in range(len(papers[pid][1].sents))]
    clues = json.load(open(a.prev)) if a.prev else []
    names = {c["name"] for c in clues}
    usage = {"in": 0, "out": 0, "calls": 0}
    report = []
    t0 = time.time()
    for t, desc in TYPES.items():
        pos = spread(missed[t], a.n_pos, rnd)
        neg = spread(fps[t] + hard[t], a.n_neg, rnd)
        if len(pos) < 5:
            continue
        prompt = (f"TARGET TYPE: {t} — {desc}.\n\n"
                  f"POSITIVE sentences (each starts a {t} node; the extractor MISSED them):\n"
                  + "\n".join(f"+ {short(x)}" for x in pos)
                  + f"\n\nNEGATIVE sentences (they do NOT start a {t} node, but the extractor "
                    f"confuses them with one):\n"
                  + "\n".join(f"- {short(x)}" for x in neg)
                  + "\n\nPropose clues that fire on many POSITIVE and few NEGATIVE sentences.")
        print(f"[invent] {t}: {len(missed[t])} missed, {len(fps[t])} false positives; "
              f"asking with {len(pos)}+{len(neg)} examples", flush=True)
        for c in ask(client, prompt, usage):
            if not isinstance(c, dict) or not c.get("regex") or not c.get("name"):
                continue
            name = re.sub(r"[^a-z0-9_]", "_", f"{t}__{c['name']}".lower())[:60]
            if name in names:
                continue
            flags = 0
            for ch in str(c.get("flags", "")):
                flags |= {"i": re.I, "s": re.S, "m": re.M}.get(ch, 0)
            try:
                pat = RX.compile(c["regex"], flags)
            except Exception:                                # noqa: BLE001
                continue
            hit_t = hit_other = 0
            t_total = 0
            for pid, i, txt, node in all_sents:
                is_t = node is not None and node.type == t
                t_total += is_t
                if fires(pat, txt):
                    if is_t:
                        hit_t += 1
                    else:
                        hit_other += 1
            n_fire = hit_t + hit_other
            keep = 5 <= n_fire <= 0.25 * len(all_sents)
            report.append({"name": name, "type": t, "fires": n_fire, "on_type": hit_t,
                           "type_total": t_total,
                           "precision": round(hit_t / n_fire, 3) if n_fire else 0.0,
                           "kept": keep, "regex": c["regex"], "why": c.get("why", "")})
            if keep:
                clues.append({"name": name, "regex": c["regex"], "flags": c.get("flags", ""),
                              "type": t, "why": c.get("why", "")})
                names.add(name)
    cost = usage["in"] / 1e6 * PRICE_IN + usage["out"] / 1e6 * PRICE_OUT
    Path(a.out).write_text(json.dumps(clues, indent=1), encoding="utf-8")
    Path(a.out).with_suffix(".report.json").write_text(
        json.dumps({"usage": usage, "cost_usd": round(cost, 4), "clues": report}, indent=1),
        encoding="utf-8")
    kept = sum(r["kept"] for r in report)
    print(f"[invent] {usage['calls']} calls, {usage['in']} in / {usage['out']} out tokens, "
          f"${cost:.4f}; {len(report)} clues proposed, {kept} kept -> {a.out} "
          f"({time.time() - t0:.0f}s)")
    for r in sorted(report, key=lambda r: -r["precision"])[:15]:
        print(f"   {'+' if r['kept'] else '-'} {r['name']:<45} fires {r['fires']:>5}  "
              f"on type {r['on_type']:>4}/{r['type_total']:<5} prec {r['precision']:.2f}")


if __name__ == "__main__":
    main()
