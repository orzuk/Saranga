# opus-5 / v5.1 silver corpus — final QA report

Extraction dir: `corpus/silver/opus-5__v5.1`  
Prompt: **v5.1**, sha256 prefix `100e6cf6fdbb3aea` (frozen for all papers)

## Headline

| metric | value |
|---|---|
| papers | **100** |
| nodes | **12817** (mean 128.2/paper) |
| edges | **21601** (mean 216.0/paper) |
| edge/node ratio | mean 1.72, median 1.70 |
| mean node confidence | 0.882 |
| mean edge confidence | 0.892 |
| statement_short coverage | 77.3% |
| papers with 0 orphans | 90/100 |
| acyclic | 100/100 |

## Node types

| type | n | %% |
|---|---|---|
| `proof_step` | 3515 | 27.4% |
| `definition` | 2111 | 16.5% |
| `proof` | 1248 | 9.7% |
| `remark` | 1092 | 8.5% |
| `proposition` | 697 | 5.4% |
| `theorem` | 650 | 5.1% |
| `claim` | 611 | 4.8% |
| `equation` | 605 | 4.7% |
| `lemma` | 576 | 4.5% |
| `algorithm_step` | 456 | 3.6% |
| `example` | 312 | 2.4% |
| `corollary` | 228 | 1.8% |
| `assumption` | 204 | 1.6% |
| `algorithm` | 182 | 1.4% |
| `open_problem` | 157 | 1.2% |
| `problem` | 142 | 1.1% |
| `conjecture` | 31 | 0.2% |

## Edge types

| type | n | %% | canonical in `edge_types.py`? |
|---|---|---|---|
| `uses` | 19621 | 90.8% | yes |
| `proves` | 1261 | 5.8% | yes |
| `illustrates` | 412 | 1.9% | yes |
| `generalizes` | 104 | 0.5% | yes |
| `specializes` | 90 | 0.4% | yes |
| `solves` | 61 | 0.3% | yes |
| `resolves` | 52 | 0.2% | **NO — see E113** |

## Field coverage

| field | nodes | %% |
|---|---|---|
| `id` | 12817 | 100% |
| `type` | 12817 | 100% |
| `name` | 12817 | 100% |
| `statement` | 12817 | 100% |
| `section` | 12817 | 100% |
| `origin` | 12817 | 100% |
| `confidence` | 12817 | 100% |
| `tags` | 10866 | 85% |
| `statement_short` | 9904 | 77% |
| `parent_id` | 3971 | 31% |
| `step_order` | 3971 | 31% |
| `subclass` | 3971 | 31% |
| `conclusions` | 2704 | 21% |
| `assumptions` | 2601 | 20% |
| `definiendum` | 2011 | 16% |
| `origin_citation` | 1906 | 15% |
| `genus` | 1535 | 12% |
| `differentia` | 1457 | 11% |
| `proof_strategy` | 1248 | 10% |
| `proves` | 782 | 6% |
| `rigor` | 600 | 5% |
| `input` | 144 | 1% |
| `output` | 139 | 1% |

## Per-category (axis = `sampled_from`; see ROADMAP 7.5.1)

| category | papers | nodes | edges | mean node conf | orphans |
|---|---|---|---|---|---|
| cs_CC | 5 | 770 | 1326 | 0.904 | 2 |
| cs_DS | 5 | 595 | 1055 | 0.849 | 4 |
| cs_IT | 5 | 725 | 1209 | 0.865 | 0 |
| cs_LG | 5 | 475 | 813 | 0.825 | 0 |
| math_AG | 5 | 650 | 1033 | 0.899 | 1 |
| math_AP | 5 | 573 | 1008 | 0.899 | 1 |
| math_AT | 5 | 1255 | 1836 | 0.959 | 1 |
| math_CA | 5 | 546 | 987 | 0.906 | 0 |
| math_CO | 5 | 492 | 835 | 0.848 | 0 |
| math_DG | 5 | 627 | 1239 | 0.888 | 0 |
| math_FA | 5 | 561 | 933 | 0.922 | 1 |
| math_GR | 5 | 449 | 886 | 0.906 | 0 |
| math_LO | 5 | 963 | 1539 | 0.887 | 0 |
| math_NA | 5 | 392 | 750 | 0.854 | 0 |
| math_NT | 5 | 701 | 1036 | 0.890 | 0 |
| math_OC | 5 | 417 | 770 | 0.849 | 0 |
| math_PR | 5 | 669 | 1224 | 0.881 | 0 |
| math_RT | 5 | 644 | 1021 | 0.893 | 2 |
| math_ph | 5 | 484 | 883 | 0.827 | 0 |
| stat_TH | 5 | 829 | 1218 | 0.893 | 0 |

## Integrity problems

None. Every paper: valid JSON, all edge endpoints resolve, acyclic,
`model=claude-opus-5[1m]`, `prompt_version=v5.1`.

## Known limits — NOT measurable from this data

- **E120 (dropped forward-reference edges).** Nodes keep no source `\label`
  and `name` is descriptive, so `\ref{}` cannot be resolved to a node.
  Edges an agent deleted to preserve acyclicity leave no trace. Confirmed
  in 1 paper / 2 edges only because that agent reported it; true rate unknown.
- **`rigor` (E130).** Declared universal in `node_types.py`, requested nowhere
  in the prompt; present on ~5% of nodes in 6 papers. Excluded from all
  cross-paper statistics above.
- **`confidence` is within-paper only.** No shared rubric anchor across papers
  (E54); per-paper means range widely. Do not compare across papers.
- **Step->parent edges are inconsistent (E8).** Some papers emit them, some
  rely on `parent_id` alone, which shifts edge/node ratio by up to ~0.5.

## Verbatim / anti-hallucination audit

`scripts/audit_verbatim.py` re-derives the cleaned source independently and checks
every `statement` against it — it does not trust agent self-reports.

| metric | value |
|---|---|
| statements checked | 12,817 |
| traced to source | **12,812 (99.96%)** |
| — exact match | 10,363 |
| — match after permitted cleanup | 2,376 |
| — head-anchored | 73 |
| not found | 5 |

The 5 misses were each diagnosed by binary-searching the longest matching prefix
against the source. **Only 2 are genuine content alterations:**

| paper / node | difference | verdict |
|---|---|---|
| `1011.1633v3` EP1.1 | source `(h_1,g_1)\cdot(h_2,g_2) = \bigl(...`; statement has `s_i` for `g_i`, `:=` for `=`, and an **added** `f(s_1 \triangleleft h_2, s_2)` factor | **fabrication** — not a transcription of this span |
| `1404.7771v1` RP1.4 | source "frame **matrix**"; statement "frame **matroid**" | **alteration** — source typo silently corrected |
| `1512.04893v3` PSP1.2 | span skips a `\begin{comment}` block | cleanup artifact (E131) |
| `1611.01043v4` DP1.25 | `\noeqref{...}` dropped | cleanup artifact (E123) |
| `1710.09079v3` PSP1.20 | `\hspace{-10mm}` dropped | cleanup artifact (E123) |

**Genuine fabrication rate: 2 / 12,817 = 0.016%.** The remaining 3 are consequences
of the permitted-cleanup list being under-specified (E123/E131), not of the model
inventing mathematics — closing those v6 gaps would move fidelity to 99.98%.

Note the asymmetry in severity: `1011.1633v3` EP1.1 introduces a term that is not
in the source at that location, which is the failure mode the verbatim rule exists
to prevent. `1404.7771v1` RP1.4 is a one-word "correction" of a real source typo —
still a rule violation, but the opposite of hallucination.

## Mis-slice check (builder-script failure mode)

The `1712.05495v4` agent reported that an ambiguous anchor initially produced a
19k-char mis-sliced `proof_step`, caught by its own structural-boundary assertion
before writing. Since not every builder script carried that guard, the corpus was
swept for the same failure mode.

**Note:** the verbatim audit cannot detect this — a mis-sliced span is still a
literal substring of the source. Coherence is the only usable test.

Method: flag any `statement` containing a structural boundary (`\section{`,
`\begin{proof}`, `\begin{lemma}`, ...) more than 200 chars in, then check whether
it terminates at a proof-ending phrase.

| result | count |
|---|---|
| statements checked | 12,817 |
| containing an interior structural boundary | 14 |
| of those, terminating coherently | **14** |
| confirmed mis-slices | **0** |

Statement length: median 356, p95 1,808, max 32,115 chars.

The 14 are concentrated in analysis/PDE papers (7 in `1209.2510v1` alone) where
proofs legitimately run to tens of thousands of characters and state auxiliary
lemmas inline — the accepted proof-contains-X nesting (B1), not extraction error.
The longest, `1209.2510v1` PP1.12 (32,115 chars), opens `{\bf step 1} Weighted
$L^2$ controls at the right` and closes `This concludes the proof of Lemma
\ref{propasymtp}.` — a complete, correctly-bounded span.
