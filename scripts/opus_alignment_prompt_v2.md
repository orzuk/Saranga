# Authomathics — STEREO Alignment Prompt (v2, with-steps schema)

You are aligning two structured math-paper knowledge graphs that were each
extracted by Authomathics's MONO single-paper pipeline (with-steps variant,
schema v2). Your task is to produce a node-level correspondence between them
and a pair-level relationship classification, both serialized to a single
JSON file.

The two papers are part of a curated pair pool (e.g., `DDPM_vs_ScoreSDE`,
`BERT_vs_GPT`, `Word2Vec_vs_GloVe`). Pairs were chosen because their content
is expected to overlap meaningfully — through extension, parallel rediscovery,
alternative proof, etc.

## What changed since v1 of this prompt

This prompt is consumed by alignment runs against the new **with-steps**
extraction (`silver_opus_4_7_final_scheme_with_steps.json`). Three rules
were added or sharpened:

1. **Level-2 step-block alignment** is restricted (see §"Level-2 nodes"). The
   v1 prompt predates Level-2 nodes; following v1 verbatim would balloon the
   alignment file with low-signal step-by-step matches.

2. **`why_related` hint** from the master pair CSV is provided as input
   context (when available); use it as a prior on the relationship type but
   never as a substitute for the JSON evidence.

3. **PDF-fallback fidelity caveat**: 116 of 268 papers were extracted from
   PDF→text rather than `.tex`. Their `statement` fields are NL paraphrases
   with reduced math fidelity (flagged by `metadata.source_note`). When a
   paper is PDF-fallback, weight node `name` and `type` more heavily than
   exact math in the statement.

## Node ID scheme — STRICT

The input JSONs use **paperNNN-prefixed IDs**: every node ID looks like
`<TYPE_PREFIX><paper_number>.<seq>` — e.g. `DP208.1` (definition #1 of
paper208), `TP209.5` (theorem #5 of paper209), `PSP208.3` (proof_step #3
of paper208).

When you reference node IDs in your output `paper_a_nodes` / `paper_b_nodes`
arrays, you MUST use these exact ID strings as they appear in the input
JSONs. Do NOT invent abbreviated forms (e.g. `DP_W2V.1` from an older
scheme); do NOT add or strip prefixes; do NOT renumber.

## Schema reference

The two input papers conform to the Authomathics mid-level schema:
- 18 node types (16 Level-1 + 2 Level-2 = `proof_step`, `algorithm_step`),
  defined in `src/node_types.py`.
- 7 edge types (`uses`, `generalizes`, `specializes`, `proves`, `illustrates`,
  `tests`, `resolves`), defined in `src/edge_types.py`.
- Each node has `id`, `name`, `type`, `statement` (LaTeX), `statement_clean`
  (NL), `section`, `origin` (paper / external), and other fields.

## Inputs

You will be given:
- `paper_a` JSON: full nodes + edges of paper A (with-steps schema)
- `paper_b` JSON: full nodes + edges of paper B (with-steps schema)
- `pair_metadata`: `{alignment_name, paper_a_arxiv_id, paper_a_title,
  paper_b_arxiv_id, paper_b_title, hypothesised_relation_type, why_related}`
  - `hypothesised_relation_type` may be `"unknown"`
  - `why_related` (NEW in v2) is a one-line description of why these papers
    were curated as a pair (from the master CSV's `short_description` /
    `notes`). It is a HINT only — do not override the JSON evidence.

You should NOT request or read the original LaTeX/PDF of either paper. The
JSONs are the source of truth for alignment; if the JSONs are too sparse
to disambiguate a candidate match, mark it `analogous` with low confidence
or omit it.

## Output JSON schema

Single file, top-level shape mirrors the existing alignments in
`portal/data/pairs/*_alignment.json`, with two new metadata fields:

```json
{
  "metadata": {
    "alignment_name": "<from pair_metadata>",
    "paper_a": {"arxiv_id": "...", "title": "..."},
    "paper_b": {"arxiv_id": "...", "title": "..."},
    "relation_type": "<one of EXT, CF, PR, BI, AP, SM, NEG>",
    "annotator": "Claude (claude-opus-4-7-silver-with-steps)",
    "scheme_version": "with_steps_v2",
    "description": "<1-3 sentences summarising the relationship>"
  },
  "matches": [
    {
      "paper_a_nodes": ["TP208.1"],
      "paper_b_nodes": ["TP209.3", "LP209.1"],
      "match_type": "exact" | "analogous" | "none",
      "confidence": "high" | "medium" | "low",
      "explanation": "<one paragraph: why this match, what is preserved, what differs>"
    },
    ...
  ]
}
```

Both `annotator` and `scheme_version` MUST appear verbatim as above so
downstream tools can distinguish v2 alignments from older v1 ones. The
`confidence` field is new in v2 and required.

## Level-2 nodes (NEW in v2)

The with-steps schema introduces two Level-2 sub-block types:
- `proof_step` (atomic step inside a `proof`)
- `algorithm_step` (atomic step inside an `algorithm`)

**Rule:** do NOT emit individual `proof_step ↔ proof_step` or
`algorithm_step ↔ algorithm_step` matches by themselves. They are far too
fine-grained for cross-paper alignment in most cases.

**Allowed L2 alignment patterns (only these):**

1. **Parent first**: emit a Level-1 match (e.g. `proof ↔ proof`) AND, when
   the inner step DAGs differ in interesting ways, optionally emit a single
   composite many-to-many entry that lists the parent's L2 children in both
   `paper_a_nodes` and `paper_b_nodes`.

2. **Parent skipped**: if a paper's proof/algorithm decomposition is the
   meaningful contribution (e.g. a step-by-step algorithm vs a closed-form
   formula in the other paper), the L1 parent match can be omitted in
   favor of one composite L2-vs-L1 entry. Justify in `explanation`.

3. **Pure L2 matches without their L1 parents**: not allowed.

For L2 nodes that genuinely have no counterpart, do NOT emit `none` entries
(see "Compactness" below).

## Match-type vocabulary (closed set)

- **`exact`** — same mathematical object up to notation and naming.
  Example: paper A's "Restricted Isometry Property of order $k$" and
  paper B's "$k$-RIP" are both the standard RIP definition.
- **`analogous`** — same conceptual role, different formulation. The
  objects play the same part in their respective theories but differ in
  hypotheses, normalisation, or framing.
  Example: paper A's "noise schedule $\beta_t$" (DDPM) and paper B's
  "drift coefficient $g(t)$" (Score SDE) — both parametrise the forward
  diffusion, but in discrete vs continuous time.
- **`none`** — A-side concept with no B-counterpart (or vice versa).

## Compactness rules for `none` matches (NEW in v2)

Emit `none` matches only for **paper-original** nodes (`origin: "paper"`)
of Level 1 type. Do NOT emit `none` for:
- Level-2 step nodes (proof_step, algorithm_step)
- Cited external results (`origin: "external"`)
- Auxiliary types: `example`, `remark`

This keeps the alignment file readable. Unmatched L2/external/aux nodes are
implicit by their absence from the matches list.

## Confidence (NEW in v2, required)

For every match (including `none`), tag a `confidence`:
- `high`: the JSONs explicitly justify the match (same name, type,
  statement nearly identical or transparent translation; or for `none`,
  the unmatched node is a clearly paper-specific contribution).
- `medium`: defensible from the JSONs but a careful reader could disagree
  on the boundary.
- `low`: best guess from sparse evidence (typical with PDF-fallback
  papers); flag any edge-of-feasibility match here.

Use `low` instead of omitting borderline matches; we'd rather see the
hypothesis tagged low-confidence than discarded silently.

## Relation-type vocabulary (closed set, pair-level)

Pick exactly one for the pair:

- **`EXT`** (extension): paper A extends paper B (or vice versa) to a
  more general setting, deeper bound, or richer object class.
- **`CF`** (competing frameworks): both papers tackle the same problem
  from substantially different theoretical machinery (e.g., compressed
  sensing via RIP vs via Gel'fand widths).
- **`PR`** (parallel rediscovery): independent derivations of the same
  result in different communities or eras.
- **`BI`** (bijection / equivalence): the two papers' main objects are
  mathematically equivalent under a translation / dictionary that the
  papers (or community) make explicit.
- **`AP`** (alternative proof): same theorem, fundamentally different
  proof technique.
- **`SM`** (same method): different problems attacked by the same
  technique (e.g., entropy compression, container method).
- **`NEG`** (negative): the pair turns out to have no meaningful
  alignment after inspection. Use sparingly and only when the matches
  are mostly `none`.

## Many-to-many alignment

Different extractors choose different node granularities. A composite
node in one paper may legitimately match multiple atomic nodes in the
other. Encode this with the list-valued `paper_a_nodes` /
`paper_b_nodes` fields:

- One A composite ↔ several B atoms: single match entry with
  `paper_a_nodes: [single_id]` and `paper_b_nodes: [multiple_ids]`.
- Several A atoms ↔ one B composite: symmetric.
- Several A ↔ several B (cluster correspondence): single match entry
  listing all on each side.

## Type-compatibility guidance (soft)

When proposing matches, the schema's type-compatibility weights apply
as a soft prior:
- `theorem ↔ theorem` (high)
- `theorem ↔ lemma`, `lemma ↔ proposition`, `theorem ↔ corollary` (high)
- `definition ↔ definition` (high)
- `problem ↔ problem`, `problem ↔ definition` (medium)
- `algorithm ↔ algorithm` (high)
- `proof ↔ proof` (high; the PROOFS may be aligned even when the
  parent theorems are stated slightly differently)
- `example ↔ example` (medium; usually weaker signal)
- Cross-group (e.g., `theorem ↔ definition`, `proof ↔ algorithm`) only
  with explicit justification in the match's `explanation`.

Type-incompatible matches are allowed when the underlying mathematics
truly corresponds — but the `explanation` must justify the cross-type
match.

## Origin-aware filtering

- Both papers carry `origin: paper` and `origin: external` markers on
  their nodes. **Skip alignment of `external`-origin nodes against each
  other unless the underlying cited result is the same.** If paper A
  cites Cauchy-Schwarz and paper B also cites Cauchy-Schwarz, you may
  emit a match (`exact`, `confidence: high`) — but it carries no
  information about A↔B relationship and should not influence the
  pair-level `relation_type`.
- `paper`-origin ↔ `external`-origin alignments are interesting: when
  paper A's *contribution* matches a result paper B *cites as prior
  work*, that is signal for `relation_type` EXT or PR.

## PDF-fallback fidelity caveat (NEW in v2)

Check each input paper's `metadata.source_note`. If it reads
`"Extracted from PDF→text fallback; .tex source not available. Math
fidelity reduced."`, that paper's `statement` fields are NL paraphrases:
- Trust `name` and `type` over exact `statement` LaTeX.
- A semantically equivalent match where the LaTeX strings differ should
  still be `exact` if the names/types align — drop the confidence to
  `medium` to flag the reduced certainty, but don't downgrade to
  `analogous` purely because the LaTeX differs.
- For PDF↔PDF pairs, expect higher noise; lean on `name` + the `section`
  hierarchy to align.

## Self-validation before writing

Before producing the output JSON:
1. Every node ID referenced in `matches` exists in the corresponding
   paper graph. If you find a typo'd ID in your own draft, fix it before
   writing.
2. Every paper-A and paper-B Level-1, paper-origin node appears in at
   least one match entry (use `match_type: none` for unmatched
   contributions to make the alignment complete). Level-2 / external /
   aux nodes do NOT need `none` entries (see "Compactness").
3. `relation_type` is one of the 7 closed-set values.
4. `match_type` is one of the 3 closed-set values.
5. `confidence` is one of the 3 closed-set values, present on every
   match (including `none`).
6. `metadata.annotator == "Claude (claude-opus-4-7-silver-with-steps)"`
   verbatim.
7. `metadata.scheme_version == "with_steps_v2"` verbatim.
8. No duplicate match entries (same pair of node-id sets).

## Failure modes (return one of these instead of placeholder JSON)

- If either input JSON is unreadable or malformed: reply with
  `FAILED: <reason>` and do NOT write a placeholder alignment.
- If you hit a quota or rate-limit error: reply with
  `QUOTA_ERROR: <exact error text>`.

## Final reply

In addition to writing the JSON, your final 1-2 line summary to the
caller should be:
`pair <alignment_name>: NN matches (X exact, Y analogous, Z none),
relation_type=...`
plus any noteworthy observations about granularity, confidence
distribution, or PDF-fallback impact.
