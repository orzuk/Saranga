# Tao's paper-diagram visualizer, and the neighbouring projects

Read 2026-08-07 against the live artifacts, not from memory (all three postdate the
assistant's training cutoff). Sources:

- Blog post — <https://terrytao.wordpress.com/2026/07/13/a-paper-diagram-visualizer/>
- Live viewer — <https://teorth.github.io/tao-web/apps/paper-diagram.html?paper=gilbreath>
- Format notes — <https://teorth.github.io/tao-web/apps/paper-diagram-making-of.html>
- Source + data — <https://github.com/teorth/tao-web> (`static/apps/diagrams/*.js`)
- Lean Blueprint example — <https://thefundamentaltheor3m.github.io/Sphere-Packing-Lean/blueprint/dep_graph_document.html>

Schema figures below are measured from the actual diagram files in the repo, not
from the prose.

---

## 1. What Tao actually built

An **offline-generation / thin-viewer** split, stated as the core design principle:

> "an LLM produces the diagrams offline; a small, deterministic app reads them."

The viewer is a static web app. It validates on load (rejecting duplicate ids,
dangling edges, self-loops and cycles), auto-computes a layered layout, and
exports to **six** formats: SVG, TikZ, quiver, DOT, Mermaid, JSON.

The published corpus is **10 diagrams**, hand- or LLM-encoded:

| diagram | nodes | edges | origin |
|---|---|---|---|
| gilbreath | 25 | 42 | hand |
| kakeya | 56 | 85 | hand |
| sphere-packing-lean | 132 | 188 | Lean Blueprint |
| pfr-lean | 202 | 343 | Lean Blueprint |
| …plus wiles-flt, szemeredi, perelman-ricci, 2211.15847, 2405.20552, cpg-ktitarev | | | |

Roughly **400–600 nodes in total across the whole project.**

Tao is explicit about status: diagrams "are not guaranteed to be 100% accurate,
and should only be used as approximations to the logical structure of these
papers", and are "LLM-generated editorial readings — a visual aid for
orientation, not an authoritative account of any paper."

His stated reason for building the viewer rather than the extractor is worth
quoting, because it is the exact inverse of our position:

> LLMs now handle diagram *generation* adequately, so he focused instead on
> *presentation* … "the review process which is now the most time-consuming"
> represents the true bottleneck, not coding capability.

## 2. The measured schema

```
top level : format, schemaVersion, meta, layout, nodes, edges
meta      : title, paper{arxiv, authors, year, companion}, generatedBy, date, note
layout    : engine ("layered"), direction ("up" | "down")
node      : id, kind, label, name, statement, section, weight, color,
            external, ref, note, plain, lean
edge      : from, to, type
```

Measured over all parsed diagrams (415 nodes, 658 edges):

- **6 node kinds** — definition, theorem, proposition, lemma, corollary, remark.
- **2 edge types** — `uses` (653) and `generalizes` (5).
- `weight` present on only **81 of 415** nodes (the hand-encoded ones).
- `lean` present on **279** (the Blueprint-derived ones) — a link to a Lean declaration.
- `external` + `ref` on 3 — cited prior results.

## 3. Side by side with Saranga

| | Tao paper-diagram | Saranga (silver v5.1) |
|---|---|---|
| corpus | 10 diagrams, ~400–600 nodes | **200 papers, 25,162 nodes, 39,839 edges** |
| node types | 6 | **18** |
| edge types | 2 (`uses`, `generalizes`) | **8** (`uses`, `proves`, `illustrates`, `generalizes`, `specializes`, `solves`, `resolves`, `tests`) |
| proofs | not modelled (a proof is an edge) | first-class `proof` node + 7,332 `proof_step` sub-nodes |
| theorem internals | one `statement` blob | `assumptions` / `conclusions` split |
| definition internals | one `statement` blob | `genus` / `differentia` |
| production | hand, or LLM per paper, reviewed | automated pipeline from arbitrary arXiv LaTeX |
| grounding | `lean` field on Blueprint imports | foundation graph (~298K nodes) via `grounded_to` |
| cross-paper | none | T-PLAG / T-ALIGN / T-OPEN |
| rule distillation | none | NtRED (LLM → interpretable regex) |
| importance | `weight` 1–5, LLM-assigned | **absent** |
| export | SVG, TikZ, quiver, DOT, Mermaid, JSON | SVG, PNG, interactive HTML |

## 4. Scooping assessment

**Not scooped, but the framing has to change.**

- Tao's artifact is a **viewer plus a curated exhibit**, published as a blog post.
  It is not a paper, has no evaluation, no ground truth, no extraction pipeline,
  and no claim about doing this at scale. He says so himself.
- The Lean Blueprint dependency graphs (`leanblueprint`) are **established
  tooling from the formalization community**, several years old. They visualise a
  *hand-written blueprint* of a formalization project, keyed to Lean
  declarations. The graph is authored, not extracted.
- The comment-thread projects are individual, half-finished, and mostly convert
  Blueprint → Tao's JSON.

So the contributions do not collide: theirs is presentation of authored
structure; ours is **automated extraction, at scale, with evaluation, plus
distillation into interpretable rules**. Nobody in this ecosystem is extracting
from arbitrary papers without a human in the loop.

**But two cautions against the "we have scale, so hurry" reflex:**

1. **Our scale claim is currently unaudited.** The 200-paper silver corpus is
   real. The 100K tier3 claim rests on the rule-based extractor whose accuracy is
   exactly what is in dispute (F1 0.711 → 0.735, with precision *falling*, and
   the metric itself under review). `portal/data/tier3` currently holds **0**
   `*_rules.json` files locally. A reviewer will ask what 100K papers of unmeasured
   extraction is worth. Scale is only a contribution if paired with a defensible
   quality number.
2. **Tao has framed the standard of honesty.** He labels his diagrams
   "approximations" and "editorial readings". A submission claiming automated
   extraction at 100K scale will be read against that. Under-claiming with
   measurements beats over-claiming with volume.

The right citation posture: cite Tao's visualizer and the Blueprint graphs as the
**presentation layer this work complements**, and position Saranga as the
extraction-and-evaluation layer that neither addresses.

## 5. What they do that we should take

Ordered by value.

### 5.1 `weight` — LLM-assigned editorial importance (HIGH)

Tao asks the model for a **1–5 subjective importance**, and uses it for *node
size and border thickness, never layout*:

> "Position is derived, not authored; weight drives size and emphasis, never layout."

This lands directly on the open question in E148 (how to rank nodes without an
LLM at query time). His answer: you *do* use the LLM, but once, at extraction
time, and you store the result. That is exactly the "derive what is mechanical,
ask the model for judgement" split E147/E148 argue for — arrived at
independently, which is mild evidence it is right.

Caveat worth respecting: only 81 of his 415 nodes carry a weight, i.e. even he
only has it where a human curated. And a free-form 1–5 score is precisely the
shape that produced E130's `rigor` disaster (5% coverage, concentrated in 6
papers) when stated without a rubric.

### 5.2 `id` = the paper's own label (HIGH — validates E146)

Tao's node ids are the paper's own reference keys: `thm:1.2`, `def:array`,
`lem:3.11`. That is exactly the `\label{}` capture queued as **E146**, and it is
load-bearing for him: it is what makes the diagram addressable and
round-trippable against the source.

This is independent confirmation that E146 is the right change, and it raises
its priority: our auto-generated `TP1.2` display ids are *ours*, not the paper's,
so nothing we emit can be cross-referenced against the PDF a reader is holding.

### 5.3 Edge-type composition rule (MEDIUM — a real gap)

> "generalization∘generalization stays a generalization; any dependence in the
> path dominates."

We have no composition semantics for edge types, and we **need one**: the
transitive-reduction toggle shipped today computes implied edges while ignoring
type entirely. An implied path mixing `uses` and `generalizes` is not the same
relation as either. This is the cleverest single idea in his format and we missed it.

### 5.4 `label` / `name` separation (MEDIUM)

`label` is the short display tag ("(1.1)"), `name` the descriptive title
("Gilbreath array"). We conflate: `name` is descriptive and the display tag is
synthesised. Splitting them is cheap and improves box headers directly.

### 5.5 Export formats (MEDIUM, cheap)

TikZ and Mermaid export would matter for the paper itself — a figure generated
from the data rather than redrawn. DOT/quiver are near-free once the graph is in
memory.

### 5.6 `plain` and `note` on nodes (LOW)

`plain` = a plain-text alternative to the LaTeX statement (an authored fallback
rather than our derived `clean_text`). `note` = editorial annotation, e.g.
*"Stated; not used directly — superseded by the variant Lem 3.11"*. We have
`note` on edges only. Both cheap.

### 5.7 `schemaVersion` + preserve-unknown-fields on round-trip (LOW, good hygiene)

We have neither. Given the corpus is versioned by directory name
(`opus-5__v5.1/`) rather than in the payload, a stray file is unidentifiable.

## 6. What we should NOT take

- **Do not shrink to 6 node types.** `proof`, `proof_step`, `algorithm`,
  `equation`, `open_problem`, `assumption` carry the discovery and verification
  signal that is the whole point of our corpus. Tao's 6 fit a *reading* diagram;
  ours must support T-ALIGN/T-OPEN.
- **Do not adopt 2 edge types.** `proves` alone accounts for 2,401 edges and is
  what lets proofs collapse into their parents.
- **Do not fold proofs into edges.** His model has no place for proof *steps*;
  ours has 7,332 of them, and they are the substrate for step-level gold.
- **Do not adopt his acyclicity-by-rejection.** His viewer *rejects* cyclic
  input. That is the exact policy that forces E120's silent edge deletion. Our
  direction (keep the edge, mark it `forward_reference`) is better, and this is a
  point of genuine disagreement worth stating in the paper.

## 7. Recommended changes

### For prompt v6 (extraction schema)

| id | change | rationale |
|---|---|---|
| **E146** (already queued) | capture `\label{}` | now doubly justified — it is Tao's node `id` |
| **new** | `weight` 1–5 editorial importance, **with a rubric** | fills the ranking gap; do NOT ship it rubric-free (see E130) |
| **new** | split `label` (short tag) from `name` (descriptive) | cheap, improves display and matches the source's own numbering |
| **new** | node-level `note` for editorial caveats | captures "stated but superseded", currently unrepresentable |

Sequencing unchanged: **E146 alone first**, then the rest. A wrong label
silently manufactures a wrong weight, a wrong edge, and a wrong ranking.

### For the visualization

1. **Edge-type-aware transitive reduction** — adopt the composition rule; the
   toggle shipped today is type-blind and can hide an edge that is not implied.
2. **Use `weight` for node size / border** once it exists — semantic zoom already
   has the tier machinery; weight would make the far tier meaningful rather than
   type-based.
3. **TikZ + Mermaid export** — for figures in the paper.
4. **Layout direction toggle** (results top vs bottom) — trivial, and Tao's
   default of results-at-top reads better than our results-at-bottom.

### For the paper

- Cite Tao's visualizer and `leanblueprint` explicitly as related work, framing
  them as the presentation layer.
- Lead with **extraction + evaluation + distillation**, not with node counts.
- Do not headline 100K until the tier3 extraction has a defensible quality
  number. The 200-paper silver corpus with a measured F1 is a stronger claim than
  100K papers with none.
