# SARANGA — STEREO Alignment Prompt (v1)

You are aligning two structured math-paper knowledge graphs that were each
extracted by SARANGA's MONO single-paper pipeline. Your task is to produce
a node-level correspondence between them and a pair-level relationship
classification, both serialized to a single JSON file.

The two papers are part of a curated pair pool (e.g., "DDPM_vs_ScoreSDE",
"BERT_vs_GPT", "DistributedOpt_vs_Federated"). Pairs were chosen because
their content is expected to overlap meaningfully — through extension,
parallel rediscovery, alternative proof, etc.

## Schema reference

The two input papers conform to the SARANGA mid-level schema:
- 18 node types (16 Level-1 + 2 Level-2 = `proof_step`, `algorithm_step`),
  defined in `src/node_types.py`.
- 7 edge types (`uses`, `generalizes`, `specializes`, `proves`, `illustrates`,
  `tests`, `resolves`), defined in `src/edge_types.py`.
- Each node has `id`, `name`, `type`, `statement` (LaTeX), `statement_clean`
  (NL), `section`, `origin` (paper / external), and other fields.

Read the canonical schema files only if you need to disambiguate a node
type during alignment.

## Inputs

You will be given:
- `paper_a` JSON: full nodes + edges of paper A
- `paper_b` JSON: full nodes + edges of paper B
- `pair_metadata`: `{alignment_name, paper_a_arxiv_id, paper_a_title,
  paper_b_arxiv_id, paper_b_title, hypothesised_relation_type}`
  (`hypothesised_relation_type` may be `"unknown"`)

You should NOT request or read the original LaTeX of either paper. The
JSONs are the source of truth for alignment; if the JSONs are too sparse
to disambiguate a candidate match, mark it `analogous` with low confidence
or omit it.

## Output JSON schema

Single file, top-level shape mirrors existing gold alignments in
`alignment_benchmark/test_set/*_alignment.json`:

```json
{
  "metadata": {
    "alignment_name": "<from pair_metadata>",
    "paper_a": {"arxiv_id": "...", "title": "..."},
    "paper_b": {"arxiv_id": "...", "title": "..."},
    "relation_type": "<one of EXT, CF, PR, BI, AP, SM, NEG>",
    "annotator": "Claude (claude-opus-4-7-silver)",
    "description": "<1-3 sentences summarising the relationship>"
  },
  "matches": [
    {
      "paper_a_nodes": ["TP_A.1"],
      "paper_b_nodes": ["TP_B.3", "LP_B.1"],
      "match_type": "exact" | "analogous" | "none",
      "explanation": "<one paragraph: why this match, what is preserved, what differs>"
    },
    ...
  ]
}
```

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
  Used to record the *complement* of the alignment: which concepts are
  unique to one paper. **Always emit `none` entries for unmatched
  contributions** so the alignment is complete, not just the matches.

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
  with explicit justification.

Type-incompatible matches are allowed when the underlying mathematics
truly corresponds — but the `explanation` must justify the cross-type
match.

## Origin-aware filtering

- Both papers carry `origin: paper` and `origin: external` markers on
  their nodes. **Skip alignment of `external`-origin nodes against each
  other unless the underlying cited result is the same.** If paper A
  cites Cauchy-Schwarz and paper B also cites Cauchy-Schwarz, you may
  emit a match (`exact`) — but it carries no information about A↔B
  relationship and should not influence the pair-level
  `relation_type`.
- `paper`-origin ↔ `external`-origin alignments are interesting: when
  paper A's *contribution* matches a result paper B *cites as prior
  work*, that is signal for relation_type EXT or PR.

## Self-validation before writing

Before producing the output JSON:
1. Every node ID referenced in `matches` exists in the corresponding
   paper graph.
2. Every paper-A and paper-B node appears in at least one match entry
   (use `match_type: none` for unmatched contributions to make the
   alignment complete).
3. `relation_type` is one of the 7 closed-set values.
4. `match_type` is one of the 3 closed-set values.
5. No duplicate match entries (same pair of node-id sets).

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
plus any noteworthy observations about granularity or confidence.
