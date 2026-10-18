#!/usr/bin/env python3
"""Finish an extracted graph with what the LaTeX source states by syntax, then check it.

The last stage of the v6 extraction, run by the extraction agent's builder
script before it writes the JSON. Everything here is deterministic and comes
from `latex_facts` (LaTeX syntax) and `algorithm_lines` (pseudocode numbering):

  label              the \\label key of the environment a node was extracted from
  display, number    the author's environment word and the number LaTeX prints (v7)
  cites              the bib keys \\cite'd inside a node's statement (v7)
  source_line_label  the printed line number of an algorithm step
  proves edges       \\begin{proof}[Proof of Theorem~\\ref{x}], or a proof that
                     directly follows its theorem (amsthm convention); basis "syntax"
  uses edges         a \\ref{key} inside a node's statement, pointing at another node;
                     basis "ref" (also set on the extractor's own edges that a \\ref states)

v7 also: a proof step with the same span as a Level-1 claim is merged into the
claim (its children move to the claim); the labels of a result's restated copies
(`also_stated_at`) resolve to the one node; and a result stated inside a proof but
used outside it is reported (encapsulation).

Then it validates the graph. `errors` must be fixed before writing; `warnings`
are for the agent's report.

It also sets `parent_id` on every Level-1 node to the innermost node containing
it (the hierarchy), and `backward: true` on every uses/generalizes/specializes
edge whose source comes after its target in the paper. The graph must contain no
circular reasoning: no cycle made only of results (a proof standing for the
result it proves) or only of definitions (validate_annotation.reasoning_cycles).

Also written: `metadata.labels`, the paper's complete \\label table (so a \\ref
kept verbatim in any statement resolves within the JSON), and
`metadata.unresolved_refs`, \\ref keys with no \\label in this source.

Usage:
    python3 src/extraction_finalize.py --tex paper.tex --json paper.json           # check
    python3 src/extraction_finalize.py --tex paper.tex --json paper.json --write   # fill + write
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edge_types as ET                                   # noqa: E402
from algorithm_lines import fill_source_line_labels      # noqa: E402
from latex_facts import extract_facts, _REF_CMDS         # noqa: E402
from proof_structure import check_steps as check_proof_steps   # noqa: E402
from proof_structure import detect as detect_proof_structure   # noqa: E402
from validate_annotation import CYCLE_HELP, cycle_noted, reasoning_cycles   # noqa: E402

_LEVEL2 = {"proof_step", "algorithm_step"}
# metadata.paper_style and metadata.extraction_notes[].category; anything else goes in the
# free-text metadata.extraction_comment (see the prompt's "Extraction notes")
PAPER_STYLES = {"theorem_proof", "formal", "derivation", "modeling", "computational", "problem_list",
                "expository", "discursive", "other"}
NOTE_CATEGORIES = {"type_uncertain", "boundary_uncertain", "unexpected_construct", "rule_conflict",
                   "source_problem", "not_extracted", "cycle"}
CYCLE_KINDS = {"wrong_ref", "granularity", "circular"}
_REF = re.compile(r"\\(?:" + _REF_CMDS + r")\*?\s*\{([^}]*)\}")
_REF_RANGE = re.compile(r"\\(?:" + _REF_CMDS + r")\*?\s*\{([^}]*)\}\)?\s*(?:--|–|-)\s*\(?"
                        r"\\(?:" + _REF_CMDS + r")\*?\s*\{([^}]*)\}")
_CITE = re.compile(r"\\[a-zA-Z]*cite[a-zA-Z]*\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^{}]*)\}")
_RESULTS = {"theorem", "lemma", "proposition", "corollary", "claim"}


def _key(s: str) -> str:
    """Whitespace- and label-insensitive form of a span, for matching."""
    return re.sub(r"\s+", "", re.sub(r"\\(?:label|index)\s*\{[^{}]*\}", "", s or ""))


def match_nodes_to_facts(graph: dict, facts: dict) -> dict[str, str]:
    """node id -> fact id, for Level-1 nodes whose statement IS an environment body.

    Environments with identical text (an equation restated in the introduction)
    are told apart by the node's `label`, then by its parent's environment, then
    by position: the copy that lies between the node's neighbours in node order
    (nodes are listed in document order), else the last copy."""
    by_key: dict[str, list[dict]] = {}
    for f in facts["facts"]:
        k = _key(f["statement"])
        if len(k) > 10:
            by_key.setdefault(k, []).append(f)
    level1 = [n for n in graph["nodes"] if n.get("type") not in _LEVEL2]
    out, taken = {}, set()
    for n in level1:                          # unique text: the one environment
        cands = by_key.get(_key(n.get("statement")))
        if cands and len(cands) == 1:
            out[n["id"]] = cands[0]["id"]
            taken.add(cands[0]["id"])
    fact = {f["id"]: f for f in facts["facts"]}
    groups: dict[str, list[dict]] = {}
    for n in level1:
        k = _key(n.get("statement"))
        if len(by_key.get(k, ())) > 1:
            groups.setdefault(k, []).append(n)
    for k, nodes in groups.items():
        free = lambda: [f for f in by_key[k] if f["id"] not in taken]
        rest = []
        for n in nodes:
            f = next((f for f in free() if n.get("label") and n["label"] in f["labels"]), None)
            if f is None and out.get(n.get("parent_id")):
                p = fact[out[n["parent_id"]]]
                f = next((f for f in free() if p["start"] <= f["start"] and f["end"] <= p["end"]), None)
            if f is None:
                rest.append(n)
            else:
                out[n["id"]] = f["id"]
                taken.add(f["id"])
        for n in rest:                        # the copy between its neighbours in node order
            lo, hi = _neighbour_bounds(level1, n["id"], out, fact)
            cands = free()
            inside = [f for f in cands if lo <= f["start"] <= hi]
            f = (inside or cands[-1:])[0] if len(inside) <= 1 else inside[-1]
            if f:
                out[n["id"]] = f["id"]
                taken.add(f["id"])
    return out


def _neighbour_bounds(nodes: list, nid: str, out: dict, fact: dict) -> tuple:
    """Start of the nearest earlier and later nodes already matched to a fact."""
    i = next(k for k, n in enumerate(nodes) if n["id"] == nid)
    lo = next((fact[out[n["id"]]]["start"] for n in reversed(nodes[:i]) if n["id"] in out), 0)
    hi = next((fact[out[n["id"]]]["start"] for n in nodes[i + 1:] if n["id"] in out), float("inf"))
    return (lo, hi) if lo <= hi else (0, float("inf"))


def _sentence_end(text: str, end: int) -> bool:
    """Does a span ending at `end` end a sentence? Peels closing markup first, so
    "... x.$" and "... bounded.} \\end{equation}" end sentences."""
    s = text[:end].rstrip()
    tail = re.compile(r"(?:\\end\{[a-zA-Z*]+\}|\\\]|\$\$?|\\(?:label|tag)\{[^{}]*\}"
                      r"|\\[a-zA-Z]+\*?|\\\\|[}\s~&)\]])$")
    prev = None
    peeled_macro = False
    while s and s != prev:
        prev = s
        s = tail.sub("", s).rstrip()
        peeled_macro = peeled_macro or bool(re.search(r"\\[a-zA-Z]+\*?$", prev))
    if s and s[-1] in ".!?:":
        return True
    nxt = text[end:end + 40]
    # a display closed by a paper's own shorthand (\ee, \eea) before a new sentence
    if peeled_macro and re.match(r"\s*[A-Z]", nxt):
        return True
    # the source simply moves on: blank line, a new environment, an \item, end of text
    return bool(re.match(r"\s*(?:\n\s*\n|\\begin\{|\\end\{|\\item|\\(?:sub)*section|$)", nxt))


def check_prose_boundaries(graph: dict, source: str, env_nodes: set, report: dict,
                           headings: list[int] | None = None) -> None:
    """Spec "Where a prose node starts and ends": whole sentences, within one
    section, no partial overlap.

    `headings` are (offset, level) of the paper's section headings (not those
    inside an environment); a prose node that contains one is an error, except a
    proof that stays within the section it starts in (v7: a proof with no
    environment that fills a section, its subsections as steps).

    A mid-sentence start or end that continues in lowercase is an error; one at
    unusual markup is a warning (it may be a false alarm). Partial overlap between
    two Level-1 nodes (they share text, neither contains the other) is an error.
    """
    from proof_structure import _norm_map, _sentence_initial
    norm, idx = _norm_map(source)
    spans = []
    for n in graph["nodes"]:
        if n.get("type") in _LEVEL2:
            continue
        key = re.sub(r"\s+", "", re.sub(r"\\(?:label|index)\s*\{[^{}]*\}", "", n.get("statement") or ""))
        i = norm.find(key) if key else -1
        if i < 0:
            continue                      # non-verbatim: reported by validate()
        start, end = idx[i], idx[i + len(key) - 1] + 1
        spans.append((start, end, n["id"]))
        if n["id"] in env_nodes or n.get("type") == "equation":
            continue
        if not _sentence_initial(source, start):
            lower = bool(re.match(r"\s*[a-z]", source[start:start + 3]))
            (report["errors"] if lower else report["warnings"]).append(
                f"{n['id']}: prose node starts mid-sentence")
        if not _sentence_end(source, end):
            nxt = source[end:end + 3].lstrip()[:1]
            (report["errors"] if nxt.islower() or nxt in ",;" else report["warnings"]).append(
                f"{n['id']}: prose node ends mid-sentence")
        crossed = [h for h in headings or () if start < h[0] < end]
        if crossed and not (n.get("type") == "proof" and _covers_subsections(start, crossed, headings)):
            report["errors"].append(f"{n['id']}: prose node crosses a section heading "
                                    "(a proof continued elsewhere is one node per part; a proof "
                                    "may span the subsections of the section it starts in)")
    spans.sort()
    for a in range(len(spans)):
        s1, e1, id1 = spans[a]
        for b in range(a + 1, len(spans)):
            s2, e2, id2 = spans[b]
            if s2 >= e1:
                break
            contains = (s1 <= s2 and e2 <= e1) or (s2 <= s1 and e1 <= e2)
            if not contains:
                report["errors"].append(f"{id1} and {id2} partly overlap (share text, neither contains the other)")


def _covers_subsections(start: int, crossed: list, headings: list) -> bool:
    """Are all `crossed` headings deeper than the heading of the section `start` lies in?"""
    own = [h for h in headings if h[0] <= start]
    level = max(own)[1] if own else 0
    return all(h[1] > level for h in crossed)


def label_table(facts: dict, node_of_fact: dict[str, str]) -> dict[str, dict]:
    """Every \\label in the paper -> what it labels, and where that lives in the graph.

    kind     env | equation | section | item | line | float | unknown
    number   the number the PDF prints, where it could be replayed; else null
    node     the node this label IS (an environment or equation extracted as a node)
    within   the node that contains it, when the label is on something that is not
             a node of its own (an equation inside a theorem, an enumerate item)
    section  the title of the section it sits in
    """
    sec_title = {s["id"]: s["title"] for s in facts["sections"]}
    fact_sec = {f["id"]: f["section"] for f in facts["facts"]}
    out = {}
    for key, lab in facts["labels"].items():
        node = node_of_fact.get(lab["id"]) if lab["id"] else None
        within = node_of_fact.get(lab["enclosing"]) if lab.get("enclosing") else None
        if lab["kind"] == "section":
            section = sec_title.get(lab["id"])
        else:
            section = sec_title.get(fact_sec.get(lab["id"] or lab.get("enclosing") or ""))
        out[key] = {"kind": lab["kind"], "number": lab["number"], "node": node,
                    "within": within if within != node else None, "section": section}
    return out


def node_spans(graph: dict, source: str) -> dict[str, tuple[int, int]]:
    """node id -> (start, end) of its statement in the cleaned source, where found.

    Nodes whose statements are identical (the same equation stated twice) take
    successive occurrences, in node order, instead of all landing on the first.
    """
    from proof_structure import _norm_map
    norm, idx = _norm_map(source)
    nxt: dict[str, int] = {}
    out = {}
    for n in graph["nodes"]:
        key = _key(n.get("statement"))
        if not key:
            continue
        i = norm.find(key, nxt.get(key, 0))
        if i < 0:
            i = norm.find(key)
        if i >= 0:
            out[n["id"]] = (idx[i], idx[i + len(key) - 1] + 1)
            nxt[key] = i + len(key)
    # a statement that also occurs inside a larger node of the same type (an
    # equation repeated within a longer display) takes an occurrence outside it
    by_type: dict[str, list[str]] = {}
    for n in graph["nodes"]:
        if n["id"] in out:
            by_type.setdefault(n.get("type"), []).append(n["id"])

    def inside_same_type(nid, span):
        return any(o != nid and out[o][0] <= span[0] and span[1] <= out[o][1] and out[o] != span
                   for o in by_type.get(types[nid], ()))
    types = {n["id"]: n.get("type") for n in graph["nodes"]}
    taken = set(out.values())
    for n in graph["nodes"]:
        me = out.get(n["id"])
        if not me or not inside_same_type(n["id"], me):
            continue
        key = _key(n.get("statement"))
        i = norm.find(key)
        while i >= 0:
            span = (idx[i], idx[i + len(key) - 1] + 1)
            if span not in taken and not inside_same_type(n["id"], span):
                taken.discard(me)
                out[n["id"]] = span
                taken.add(span)
                break
            i = norm.find(key, i + 1)
    # a node with a parent lies inside it: re-place a repeated statement there
    pos = {x: k for k, x in enumerate(idx)}
    for n in graph["nodes"]:
        p, me = out.get(n.get("parent_id")), out.get(n["id"])
        if not (p and me) or (p[0] <= me[0] and me[1] <= p[1]):
            continue
        key = _key(n.get("statement"))
        i = norm.find(key, pos.get(p[0], 0))
        if i >= 0 and idx[i + len(key) - 1] + 1 <= p[1]:
            out[n["id"]] = (idx[i], idx[i + len(key) - 1] + 1)
    return out


def compute_hierarchy(graph: dict, spans: dict, report: dict) -> dict[str, str | None]:
    """Spec HIERARCHY: `parent_id` = the innermost node whose span contains this one.

    Level-1 nodes: computed here and written (the extractor does not set them).
    Steps: the extractor sets them by the nesting rules; a step whose parent's
    span does not contain it is reported. Returns node id -> parent id.
    """
    nodes = {n["id"]: n for n in graph["nodes"]}
    order = sorted(spans, key=lambda i: (spans[i][0], -(spans[i][1] - spans[i][0])))
    parent: dict[str, str | None] = {}
    for nid in order:
        s, e = spans[nid]
        best = None
        for oid in order:
            if oid == nid:
                continue
            os_, oe = spans[oid]
            if os_ <= s and e <= oe and (oe - os_) > (e - s):
                if best is None or (oe - os_) < (spans[best][1] - spans[best][0]):
                    best = oid
        parent[nid] = best
    filled = 0
    for n in graph["nodes"]:
        nid = n["id"]
        if n.get("type") in _LEVEL2:
            p = n.get("parent_id")
            if p in spans and nid in spans:
                ps, pe = spans[p]
                cs, ce = spans[nid]
                if not (ps <= cs and ce <= pe):
                    report["warnings"].append(
                        f"{nid}: its parent {p}'s statement does not contain it")
            parent[nid] = p
            continue
        p = parent.get(nid)
        if p:
            if n.get("parent_id") != p:
                filled += 1
            n["parent_id"] = p
        else:
            n.pop("parent_id", None)
        n.pop("parent_step", None)
    report["parents_set"] = filled
    return parent


def _innermost(spans: dict, pos: int) -> str | None:
    """The node with the smallest span containing source offset `pos`."""
    inside = [(e - s, nid) for nid, (s, e) in spans.items() if s <= pos < e]
    return min(inside)[1] if inside else None


def _ancestors(nid, parent):
    out, seen = set(), set()
    while parent.get(nid) and nid not in seen:
        seen.add(nid)
        nid = parent[nid]
        out.add(nid)
    return out


def merge_claim_steps(graph: dict, spans: dict, report: dict) -> None:
    """A claim inside a proof is a Level-1 node, never also a step (prompt, step rule 7):
    a proof step whose span is that of a Level-1 result is removed, its children take
    the result as parent, and its edges and notes move to the result."""
    level1 = {spans[n["id"]]: n["id"] for n in graph["nodes"]
              if n.get("type") in _RESULTS and n["id"] in spans}
    gone = {n["id"]: level1[spans[n["id"]]] for n in graph["nodes"]
            if n.get("type") == "proof_step" and spans.get(n["id"]) in level1}
    if not gone:
        report["steps_merged"] = []
        return
    old_parent = {n["id"]: n.get("parent_id") for n in graph["nodes"] if n["id"] in gone}
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] not in gone]
    for n in graph["nodes"]:
        if n.get("parent_id") in gone:
            n["parent_id"] = gone[n["parent_id"]]
    for p in set(old_parent.values()):        # step_order stays 1, 2, ... within each parent
        sibs = sorted((n for n in graph["nodes"] if n.get("type") in _LEVEL2 and n.get("parent_id") == p),
                      key=lambda n: n.get("step_order") or 0)
        for k, n in enumerate(sibs, 1):
            n["step_order"] = k
    edges, seen = [], set()
    for e in graph["edges"]:
        e["source"], e["target"] = gone.get(e["source"], e["source"]), gone.get(e["target"], e["target"])
        if e["source"] == e["target"] or (e["source"], e["target"], e.get("type")) in seen:
            continue
        seen.add((e["source"], e["target"], e.get("type")))
        edges.append(e)
    graph["edges"] = edges
    for note in (graph.get("metadata") or {}).get("extraction_notes") or []:
        if isinstance(note, dict) and note.get("nodes"):
            note["nodes"] = list(dict.fromkeys(gone.get(x, x) for x in note["nodes"]))
    for sid in gone:
        spans.pop(sid, None)
    report["steps_merged"] = sorted(gone.items())


def check_encapsulation(graph: dict, parent: dict, report: dict) -> None:
    """A result stated inside a proof belongs to that proof: it should be used only
    inside it (proof_dag_hierarchy note). Every use from outside is listed in the report;
    one the extractor added (not a \\ref) is also a warning: the usual fix is the
    edge's source (the later node relies on the result the proof proves)."""
    kids: dict[str, set] = {}
    for c, p in parent.items():
        if p:
            kids.setdefault(p, set()).add(c)

    def inside(root):
        out, stack = {root}, [root]
        while stack:
            for c in kids.get(stack.pop(), ()):
                if c not in out:
                    out.add(c)
                    stack.append(c)
        return out
    types = {n["id"]: n.get("type") for n in graph["nodes"]}
    found = []
    for n in graph["nodes"]:
        if types[n["id"]] not in _RESULTS:
            continue
        proof = next((a for a in _chain(n["id"], parent) if types.get(a) == "proof"), None)
        if not proof:
            continue
        mine = inside(proof)
        out = [e for e in graph["edges"] if e["source"] == n["id"] and e.get("type") == ET.USES
               and not e.get("mention") and e["target"] not in mine]
        if out:
            found.append((n["id"], proof, sorted({e["target"] for e in out})))
        users = sorted({e["target"] for e in out if e.get("basis") != "ref"})   # a \ref is the author's
        if users:
            report["warnings"].append(f"{n['id']} is stated inside proof {proof} but used outside it by "
                                      f"{', '.join(users[:8])}: check each edge's source (usually the result "
                                      f"{proof} proves); keep it if the paper really relies on {n['id']}")
    report["used_outside_proof"] = found


def _chain(nid, parent):
    """Ancestors of a node, innermost first."""
    out, seen = [], {nid}
    while parent.get(nid) and parent[nid] not in seen:
        nid = parent[nid]
        seen.add(nid)
        out.append(nid)
    return out


_POSITIONAL_TYPES = {ET.USES, ET.GENERALIZES, ET.SPECIALIZES}


def set_backward_flags(graph: dict, spans: dict, report: dict) -> None:
    """Spec Hard rule 10: `backward: true` on a uses/generalizes/specializes edge
    whose source starts after its target in the paper. Set by position, so it does
    not depend on the order edges were added. Other edge types never carry it."""
    n = 0
    for e in graph["edges"]:
        if e.get("type") in _POSITIONAL_TYPES and e["source"] in spans and e["target"] in spans:
            if spans[e["source"]][0] > spans[e["target"]][0]:
                e["backward"] = True
                n += 1
            else:
                e.pop("backward", None)
        elif e.get("type") not in _POSITIONAL_TYPES:
            e.pop("backward", None)
    report["backward_edges"] = n


_LINE_SUBCLASS = {"for": "loop", "while": "loop", "loop": "loop", "repeat": "loop",
                  "if": "branch", "else": "branch", "switch": "branch", "case": "branch",
                  "return": "return", "until": "test", "end": "other", "comment": "other",
                  "function": "other", "begin": "other"}


def pseudocode_steps(facts: dict, fact_id: str, algorithm: dict, first_seq: int = 1) -> list[dict]:
    """The algorithm_step nodes of a pseudocode algorithm, built from its lines.

    `facts` is extract_facts' output, `fact_id` the algorithm's fact, `algorithm`
    your algorithm node (its id, section and origin are used). One step per
    printed line, in order: `statement` is the line's verbatim span (a loop or
    branch line spans its body), `parent_id` the enclosing loop or branch step
    (or the algorithm), `step_order` counts within each parent. `subclass` is set
    for control lines and is None for ordinary lines: choose it. Add a
    `statement_short` where the line is not self-explanatory. IDs run
    ASP<first_seq>, ASP<first_seq + 1>, ...; pass the next free number.
    """
    fact = next(f for f in facts["facts"] if f["id"] == fact_id)
    src, lines = facts["source"], fact.get("lines") or []
    ids: dict[int, str] = {}
    order: dict[str, int] = {}
    steps, seq = [], first_seq

    def parent_of(i):
        p = lines[i]["parent"]
        while p is not None and p not in ids:      # a line printed but not in the source
            p = lines[p]["parent"]
        return algorithm["id"] if p is None else ids[p]
    for i, ln in enumerate(lines):
        if ln["start"] is None:
            continue
        pid = parent_of(i)
        order[pid] = order.get(pid, 0) + 1
        sid = f"ASP{seq}"
        seq += 1
        ids[i] = sid
        steps.append({
            "id": sid, "type": "algorithm_step", "parent_id": pid,
            "step_order": order[pid],
            "name": f"Line {ln['number']}" if ln["number"] else f"Step {len(steps) + 1}",
            "statement": src[ln["start"]:ln["end"]],
            "subclass": _LINE_SUBCLASS.get(ln["kind"]),
            "section": algorithm.get("section"), "origin": algorithm.get("origin", "paper"),
            "confidence": 1.0,
        })
    return steps


_KEYS = re.compile(r"\\(?:" + _REF_CMDS + r"|label|cite[a-zA-Z]*)\*?\s*(?:\[[^\]]*\]\s*)?\{[^{}]*\}")


def _sym(text: str) -> str:
    """A math symbol in comparable form: no $, spaces or braces (L^{\\lambda} = L^\\lambda)."""
    return re.sub(r"[\s${}]", "", text or "")


def _trivial_sym(sym: str) -> bool:
    """A single letter or a single command (x, \\beta): too common to track."""
    return bool(re.fullmatch(r"[A-Za-z0-9]|\\[A-Za-z]+", sym)) or len(sym) < 2


def _sym_in(sym: str, text: str) -> bool:
    flat = _sym(_KEYS.sub(" ", text or ""))
    i = flat.find(sym)
    while i >= 0:
        before = flat[i - 1] if i else ""
        after = flat[i + len(sym)] if i + len(sym) < len(flat) else ""
        if not re.match(r"[A-Za-z\\]", before) and not re.match(r"[A-Za-z0-9_^,']", after):
            return True
        i = flat.find(sym, i + 1)
    return False


def check_defined_terms(graph: dict, spans: dict, parent: dict, report: dict) -> None:
    """Warn when a later node uses a definition's `definiendum` (a plain-word term,
    or a `$...$` symbol) and no edge links the definition to it, to the node's
    container, or to a node it contains. A false match (the word used in another
    sense) needs no edge; every real use does (prompt: edge pass 2)."""
    out: dict[str, set] = {}
    for e in graph["edges"]:
        out.setdefault(e["source"], set()).add(e["target"])
    kids: dict[str, set] = {}
    for c, p in parent.items():
        if p:
            kids.setdefault(p, set()).add(c)

    def family(nid):
        fam, stack = {nid} | _ancestors(nid, parent), [nid]
        while stack:
            for c in kids.get(stack.pop(), ()):
                if c not in fam:
                    fam.add(c)
                    stack.append(c)
        return fam

    def one_term(t):
        """("word", term) or ("symbol", normalized symbol) or None."""
        if not isinstance(t, str) or not t.strip():
            return None
        t = t.strip()
        if re.fullmatch(r"\$[^$]+\$", t):
            sym = _sym(t)
            return None if _trivial_sym(sym) else ("symbol", sym)
        return ("word", t) if len(t) >= 4 and not re.search(r"[$\\{}]", t) else None

    def terms_of(d):
        """Every term a definition defines: `definiendum` is one, or a list (one sentence
        introducing several symbols)."""
        t = d.get("definiendum") if d.get("type") == "definition" else None
        return [x for x in map(one_term, t if isinstance(t, list) else [t]) if x]
    words = {t[1] for n in graph["nodes"] for t in terms_of(n) if t[0] == "word"}
    for d, (kind, term) in ((d, t) for d in graph["nodes"] for t in terms_of(d)):
        if d["id"] not in spans:
            continue
        if kind == "symbol":
            uses = lambda text, sym=term: _sym_in(sym, text)
        else:
            pat = re.compile(r"(?<![\w-])" + re.escape(term) + r"(?:s|es)?(?![\w-])", re.I)
            longer = [re.compile(re.escape(u), re.I) for u in words
                      if u.lower() != term.lower() and term.lower() in u.lower()]

            def uses(text, pat=pat, longer=longer):
                text = _KEYS.sub(" ", text or "")
                for lp in longer:             # "clone" inside "weighted clone" is the other term
                    text = lp.sub(" ", text)
                return bool(pat.search(text))
        mine = family(d["id"])
        # a later definition of the same term or symbol takes over from there
        until = min((spans[e["id"]][0] for e in graph["nodes"] if e["id"] != d["id"]
                     and e["id"] in spans and spans[e["id"]][0] > spans[d["id"]][0]
                     and (kind, term) in terms_of(e)), default=float("inf"))
        missing = [n["id"] for n in graph["nodes"]
                   if n["id"] not in mine and n["id"] in spans
                   and spans[d["id"]][0] < spans[n["id"]][0] < until
                   and uses(n.get("statement"))
                   and not (out.get(d["id"], set()) & family(n["id"]))]
        if missing:
            shown = term if kind == "word" else f"${term}$"
            report["warnings"].append(f"{d['id']} defines {shown!r}, used with no edge from it in: "
                                      + ", ".join(missing[:12]) + (" ..." if len(missing) > 12 else ""))


_INTRO_SYM = [re.compile(r"\b[Ll]et\s+\$([^$]{1,40})\$\s+(?:be|denote)\b(?!\s+(?:as\s+(?:in|above|before|defined)|defined\s+(?:in|as\s+in)))"),
              re.compile(r"\b[Ww]e\s+(?:denote|write)\b[^.$]{0,60}\$([^$]{1,40})\$"),
              re.compile(r"\$([^$=]{1,30}?)\s*:=")]


def check_introduced_symbols(graph: dict, source: str, spans: dict, facts: dict,
                             report: dict, env_nodes: set = frozenset()) -> None:
    """Warn when running text outside proofs and outside every node introduces a
    symbol ("Let $X$ be", "we denote ... $X$", "$X :=") that a later node uses:
    that sentence should be a definition node (prompt: introduced terms)."""
    proofs = [(f["start"], f["end"]) for f in facts["facts"] if f["kind"] == "proof"]
    proofs += [spans[n["id"]] for n in graph["nodes"] if n.get("type") == "proof" and n["id"] in spans]
    covered = list(spans.values())
    seen = set()
    for d in graph["nodes"]:                  # one introduced symbol per definition node
        if d.get("type") != "definition" or d["id"] in env_nodes:
            continue                          # an environment cannot be split
        st = d.get("statement") or ""
        hits = sorted({(m.start(), _sym(m.group(1))) for p in _INTRO_SYM for m in p.finditer(st)
                       if not _trivial_sym(_sym(m.group(1)))})
        apart = [b for a, b in zip(hits, hits[1:])
                 if re.search(r"[.;]\s", st[a[0]:b[0]]) and a[1] != b[1]]
        if apart:
            report["warnings"].append(f"{d['id']}: introduces {len(apart) + 1} symbols in separate "
                                      f"sentences; each is its own definition node")
    for pat in _INTRO_SYM:
        for m in pat.finditer(source):
            pos, sym = m.start(), _sym(m.group(1))
            if sym in seen or _trivial_sym(sym):
                continue
            if any(a <= pos < b for a, b in proofs) or any(a <= pos < b for a, b in covered):
                continue
            later = [n["id"] for n in graph["nodes"] if n["id"] in spans
                     and spans[n["id"]][0] > pos and _sym_in(sym, n.get("statement"))]
            if later:
                seen.add(sym)
                line = re.sub(r"\s+", " ", source[pos:pos + 70])
                report["warnings"].append(
                    f"introduced symbol ${sym}$ ({line!r}) is used in {', '.join(later[:6])}"
                    f"{' ...' if len(later) > 6 else ''} but no definition node covers its introduction")


def finalize(graph: dict, tex: str) -> dict:
    """Fill the syntactic fields and edges of `graph` in place; return a report."""
    facts = extract_facts(tex)
    source = facts["source"]
    fact_by_id = {f["id"]: f for f in facts["facts"]}
    node_of_fact = {}
    n2f = match_nodes_to_facts(graph, facts)
    for nid, fid in n2f.items():
        node_of_fact.setdefault(fid, nid)
    nodes = {n["id"]: n for n in graph["nodes"]}
    for n in graph["nodes"]:                  # \label and \index are dropped (mechanical cleanup)
        if n.get("statement"):
            n["statement"] = re.sub(r"\s*\\(?:label|index)\s*\{[^{}]*\}\s*", " ", n["statement"]).strip()
    report = {"matched_to_environment": len(n2f), "labels_filled": 0,
              "proves_added": [], "ref_uses_added": [], "ref_backward": [],
              "errors": [], "warnings": []}

    # 0. a proof step that duplicates a Level-1 claim is merged into the claim
    merge_claim_steps(graph, node_spans(graph, source), report)
    nodes = {n["id"]: n for n in graph["nodes"]}

    # 0b. a result's restated copies (`also_stated_at`): their environments, and so their
    #     \labels, stand for the one node
    for n in graph["nodes"]:
        for copy in n.get("also_stated_at") or []:
            k = _key(copy) if isinstance(copy, str) else ""
            for f in facts["facts"]:
                if len(k) > 10 and _key(f["statement"]) == k and f["id"] not in node_of_fact:
                    node_of_fact[f["id"]] = n["id"]

    # 1. label; the author's environment word and printed number
    for nid, fid in n2f.items():
        f = fact_by_id[fid]
        if f["labels"] and nodes[nid].get("label") not in f["labels"]:   # an environment's own label
            nodes[nid]["label"] = f["labels"][0]
            report["labels_filled"] += 1
        for field in ("display", "number"):
            if f.get(field):
                nodes[nid][field] = f[field]
            else:
                nodes[nid].pop(field, None)

    # 1b. bib keys cited inside each statement
    for n in graph["nodes"]:
        keys = [k.strip() for m in _CITE.findall(n.get("statement") or "") for k in m.split(",")]
        keys = list(dict.fromkeys(k for k in keys if k))
        if keys:
            n["cites"] = keys
        else:
            n.pop("cites", None)

    # 2. source_line_label
    alg = fill_source_line_labels(graph, source)      # prepared: macros expanded
    for sid, lines in alg["merged"]:
        report["errors"].append(f"MERGED step {sid} spans printed lines {lines}: one step per line")

    # 3. hierarchy: parent_id = innermost containing node
    spans = node_spans(graph, source)
    for nid, fid in n2f.items():             # an environment node is where its environment is
        f = fact_by_id[fid]
        spans[nid] = (f["start"], f["end"])
    parent = compute_hierarchy(graph, spans, report)

    pairs = {(e["source"], e["target"]) for e in graph["edges"]}

    # 4. proves edges stated by syntax
    for nid, fid in n2f.items():
        f = fact_by_id[fid]
        if f["kind"] != "proof" or not f.get("proves"):
            continue
        tgt = node_of_fact.get(f["proves"])
        if tgt is None:
            continue
        if (nid, tgt) in pairs:
            for e in graph["edges"]:
                if (e["source"], e["target"]) == (nid, tgt) and e.get("type") == ET.PROVES:
                    e.setdefault("basis", "syntax")
            continue
        if any(e["source"] == nid and e["type"] == ET.PROVES for e in graph["edges"]):
            continue                      # the agent already chose a target
        conf = 1.0 if f["proves_basis"] == "optarg" else 0.9
        graph["edges"].append({"source": nid, "target": tgt, "type": ET.PROVES,
                               "confidence": conf, "basis": "syntax"})
        pairs.add((nid, tgt))
        report["proves_added"].append((nid, tgt, f["proves_basis"]))

    # 5. uses edges from \ref, into Level-1 nodes and proof steps alike
    ref_pairs: set = set()
    for n in graph["nodes"]:
        if n.get("type") == "algorithm_step":
            continue
        stmt = n.get("statement") or ""
        found = _REF.findall(stmt)
        order = list(facts["labels"])           # document order
        for a, b in _REF_RANGE.findall(stmt):   # \eqref{a}--\eqref{b}: everything between
            if a in facts["labels"] and b in facts["labels"]:
                i, j = order.index(a), order.index(b)
                kind = facts["labels"][a]["kind"]
                found += [k for k in order[i + 1:j] if facts["labels"][k]["kind"] == kind]
        for key in found:
            keys = [key] if (key.strip() in facts["labels"] or "," not in key) else key.split(",")
            for k in keys:
                lab = facts["labels"].get(k.strip())
                if not lab:
                    continue
                fid = lab["id"] if lab["kind"] in ("env", "equation") else lab["enclosing"]
                src = node_of_fact.get(fid) if fid else None
                if lab["kind"] == "item" and lab.get("offset") is not None:
                    # the node holding the item, which may start right after the \\label
                    after = re.compile(r"\\label\s*\{[^{}]*\}\s*").match(source, lab["offset"])
                    src = (_innermost(spans, lab["offset"])
                           or (after and _innermost(spans, after.end())) or src)
                if lab["kind"] == "equation" and src is None and lab["enclosing"]:
                    src = node_of_fact.get(lab["enclosing"])
                tgt = n["id"]
                if not src or src == tgt:
                    continue
                # containment is parent_id, never an edge
                if src in _ancestors(tgt, parent) or tgt in _ancestors(src, parent):
                    continue
                ref_pairs.add((src, tgt))
                if (src, tgt) in pairs or (tgt, src) in pairs:
                    continue
                graph["edges"].append({"source": src, "target": tgt, "type": ET.USES,
                                       "confidence": 0.95, "note": f"\\ref{{{k.strip()}}}",
                                       "basis": "ref"})
                pairs.add((src, tgt))
                report["ref_uses_added"].append((src, tgt, k.strip()))

    # 5a. an edge the extractor added itself (a mention) that a \ref states has basis "ref"
    for e in graph["edges"]:
        if (e["source"], e["target"]) in ref_pairs and e.get("type") != ET.PROVES:
            e.setdefault("basis", "ref")

    # 5b. a proof's `proves` field names the result its `proves` edge points to
    #     (the prompt: "always the same as the target of its proves edge")
    for n in graph["nodes"]:
        if n.get("type") != "proof":
            continue
        targets = [e["target"] for e in graph["edges"]
                   if e.get("source") == n["id"] and e.get("type") == ET.PROVES]
        if targets:
            if n.get("proves") not in targets:
                n["proves"] = targets[0]
        elif n.get("proves") in nodes:
            graph["edges"].append({"source": n["id"], "target": n["proves"], "type": ET.PROVES,
                                   "confidence": n.get("confidence", 0.7),
                                   "basis": "named" if n.get("confidence", 0.7) >= 0.85 else "inferred"})
            pairs.add((n["id"], n["proves"]))
            report["proves_added"].append((n["id"], n["proves"], "field"))
        else:
            n.pop("proves", None)            # null or not a node: no claim at all

    # 6. backward flags by position (after every edge is in)
    set_backward_flags(graph, spans, report)
    report["ref_backward"] = [(e["source"], e["target"], e.get("note"))
                              for e in graph["edges"] if e.get("backward") and e.get("note")]

    # 6b. defined terms used later with no edge from their definition
    check_defined_terms(graph, spans, parent, report)
    check_introduced_symbols(graph, source, spans, facts, report, set(n2f))
    check_encapsulation(graph, parent, report)

    # 7. the paper's full label table, so every \ref kept in a statement resolves
    graph.setdefault("metadata", {})["labels"] = label_table(facts, node_of_fact)
    unresolved = sorted({r["key"] for r in facts["refs"] if r["key"] not in facts["labels"]})
    graph["metadata"]["unresolved_refs"] = unresolved
    report["labels_total"] = len(graph["metadata"]["labels"])
    report["unresolved_refs"] = unresolved

    # 8. prose nodes: whole sentences, and no partial overlap between nodes
    headings = [(x["start"], x.get("level") or 1) for x in facts["sections"] if x.get("inside") is None]
    check_prose_boundaries(graph, source, set(n2f), report, headings)

    # 9. proof steps against the proof's author structure, for EVERY proof node
    kids: dict[str, list[dict]] = {}
    for n in graph["nodes"]:
        if n.get("type") == "proof_step" and n.get("parent_id"):
            kids.setdefault(n["parent_id"], []).append(n)

    def descendants(pid):
        out = []
        for c in kids.get(pid, []):
            out.append(c)
            out.extend(descendants(c["id"]))
        return out
    for n in graph["nodes"]:
        if n.get("type") != "proof" or n["id"] not in spans:
            continue
        s, e = spans[n["id"]]
        body = source[s:e]
        f = fact_by_id.get(n2f.get(n["id"], ""), {})
        if "structure" in f and f["start"] == s:
            labels = [dict(l, offset=l["offset"] - f["start"]) for l in f["structure"]["labels"]]
        else:
            labels = detect_proof_structure(body)["labels"]
        errs, warns = check_proof_steps(body, {"labels": labels}, descendants(n["id"]))
        report["errors"].extend(f"{n['id']}: {x}" for x in errs)
        report["warnings"].extend(f"{n['id']}: {x}" for x in warns)

    validate(graph, source, report, parent)
    return report


_SUBSPAN_FIELDS_STRICT = ("assumptions", "conclusions", "input", "output", "also_stated_at",
                          "equivalent_conditions")
_SUBSPAN_FIELDS_SOFT = ("differentia", "genus")


def validate(graph: dict, source: str, report: dict, parent: dict | None = None) -> dict:
    """Structural checks. Appends to report['errors'] / report['warnings']."""
    err, warn = report["errors"], report["warnings"]
    parent = parent or {}
    ids = [n["id"] for n in graph["nodes"]]
    nodes = {n["id"]: n for n in graph["nodes"]}
    if len(ids) != len(set(ids)):
        err.append("duplicate node ids")
    meta = graph.get("metadata") or {}
    for key in ("paper_style", "rigor_nonformal_count"):
        if key not in meta:
            err.append(f"metadata.{key} is missing (required; see the prompt)")
    if "paper_style" in meta:
        st = meta["paper_style"]
        if not (isinstance(st, list) and 1 <= len(st) <= 2 and set(st) <= PAPER_STYLES):
            err.append(f"metadata.paper_style must be a list of 1-2 values from {sorted(PAPER_STYLES)}")
    for i, note in enumerate(meta.get("extraction_notes") or []):
        if not isinstance(note, dict) or note.get("category") not in NOTE_CATEGORIES:
            err.append(f"metadata.extraction_notes[{i}]: category not in {sorted(NOTE_CATEGORIES)}")
            continue
        for nid in note.get("nodes") or []:
            if nid not in nodes:
                warn.append(f"metadata.extraction_notes[{i}]: unknown node {nid!r}")
        if note["category"] == "cycle":      # a cycle the paper's text states, edge by edge
            ev = note.get("evidence")
            if note.get("kind") not in CYCLE_KINDS:
                err.append(f"metadata.extraction_notes[{i}]: a cycle note has `kind` in {sorted(CYCLE_KINDS)}")
            if len(note.get("nodes") or []) < 2:
                err.append(f"metadata.extraction_notes[{i}]: a cycle note names the nodes of the cycle, in order")
            if not isinstance(ev, list) or len(ev) < len(note.get("nodes") or []):
                err.append(f"metadata.extraction_notes[{i}]: a cycle note quotes the text stating each edge "
                           f"of the cycle (`evidence`, one verbatim span per edge)")
            for q in ev if isinstance(ev, list) else []:
                if not isinstance(q, str) or _key(q) not in _key(source):
                    err.append(f"metadata.extraction_notes[{i}]: evidence is not a verbatim span: {str(q)[:50]!r}")
    comment = meta.get("extraction_comment") or ""
    if len(comment) > 600:
        warn.append(f"metadata.extraction_comment is {len(comment)} chars; keep it to 3 sentences")
    src_key = _key(source)
    for n in graph["nodes"]:
        st = n.get("statement")
        if not st:
            err.append(f"{n['id']}: empty statement")
        elif _key(st) not in src_key:
            err.append(f"{n['id']}: statement is not a verbatim span of the cleaned source")
        for field in _SUBSPAN_FIELDS_STRICT + _SUBSPAN_FIELDS_SOFT:
            vals = n.get(field)
            vals = [vals] if isinstance(vals, str) else (vals or [])
            for v in vals:
                if isinstance(v, str) and v.strip() and _key(v) not in src_key:
                    (err if field in _SUBSPAN_FIELDS_STRICT else warn).append(
                        f"{n['id']}: {field} element is not a verbatim span: {v[:50]!r}")
    for e in graph["edges"]:
        s, t, ty = e.get("source"), e.get("target"), e.get("type")
        if s not in nodes or t not in nodes:
            err.append(f"edge {s}->{t}: endpoint does not exist")
            continue
        if ty not in ET.ALL_EDGE_TYPES:
            err.append(f"edge {s}->{t}: unknown type {ty!r}")
            continue
        allowed_s = ET.get_allowed_source_types(ty)
        allowed_t = ET.get_allowed_target_types(ty)
        if allowed_s and nodes[s].get("type") not in allowed_s:
            err.append(f"edge {s}->{t} ({ty}): source type {nodes[s].get('type')} not allowed")
        if allowed_t and nodes[t].get("type") not in allowed_t:
            err.append(f"edge {s}->{t} ({ty}): target type {nodes[t].get('type')} not allowed")
        if "confidence" not in e:
            err.append(f"edge {s}->{t}: missing confidence")
        if "basis" in e and e["basis"] not in ET.EDGE_BASIS:
            err.append(f"edge {s}->{t}: basis {e['basis']!r} not in {list(ET.EDGE_BASIS)}")
        if ty == ET.USES and (s in _ancestors(t, parent) or t in _ancestors(s, parent)):
            err.append(f"edge {s}->{t}: a `uses` edge between a node and its own "
                       f"container; containment is parent_id, remove the edge")
    no_basis = [f"{e.get('source')}->{e.get('target')}" for e in graph["edges"] if "basis" not in e]
    if no_basis:
        warn.append(f"{len(no_basis)} edges have no basis (named, term or inferred): "
                    + ", ".join(no_basis[:10]) + (" ..." if len(no_basis) > 10 else ""))
    for n in graph["nodes"]:
        if "main" in n and (n["main"] is not True or n.get("type") not in _RESULTS | {"algorithm"}):
            err.append(f"{n['id']}: `main` is only `true`, on a result or an algorithm")
        eq = n.get("equivalent_conditions")
        if eq is not None and (n.get("type") not in _RESULTS | {"conjecture"} or not isinstance(eq, list)
                               or len(eq) < 2):
            err.append(f"{n['id']}: `equivalent_conditions` is a list of at least two spans, on a result "
                       f"or a conjecture")
    for n in graph["nodes"]:                  # parts: which assumptions give which conclusions
        parts = n.get("parts")
        if parts is None:
            continue
        if n.get("type") not in _RESULTS | {"conjecture"} or not isinstance(parts, list) or len(parts) < 2:
            err.append(f"{n['id']}: `parts` is a list of at least two parts, on a result or a conjecture")
            continue
        flat = {_key(x) for f in ("assumptions", "conclusions") for x in n.get(f) or [] if isinstance(x, str)}
        for k, part in enumerate(parts):
            if not isinstance(part, dict) or not part.get("conclusions") or set(part) - {"assumptions", "conclusions",
                                                                                       "adds_to"}:
                err.append(f"{n['id']}: parts[{k}] is {{assumptions, conclusions, adds_to}} with conclusions")
                continue
            a = part.get("adds_to")
            if a is not None and not (isinstance(a, int) and 0 <= a < k):
                err.append(f"{n['id']}: parts[{k}].adds_to is the index of an earlier part")
            for f in ("assumptions", "conclusions"):
                for x in part.get(f) or []:
                    if not isinstance(x, str) or _key(x) not in src_key:
                        err.append(f"{n['id']}: parts[{k}].{f} element is not a verbatim span: {str(x)[:50]!r}")
                    elif _key(x) not in flat:
                        warn.append(f"{n['id']}: parts[{k}].{f} element is not in the node's own {f}: "
                                    f"{x[:50]!r} (the flat lists hold every span)")
    # alternative proofs: only on proves edges, and the result keeps a proof of its own
    main_proof = {e["target"] for e in graph["edges"] if e.get("type") == ET.PROVES and not e.get("alternative")}
    for e in graph["edges"]:
        if "alternative" not in e:
            continue
        if e["alternative"] is not True or e.get("type") != ET.PROVES:
            err.append(f"edge {e.get('source')}->{e.get('target')}: `alternative` is only `true`, on a proves edge")
        elif e.get("target") not in main_proof:
            err.append(f"edge {e['source']}->{e['target']}: an alternative proof of {e['target']}, which has no "
                       f"other proof; the first proof the paper gives is the main one (no `alternative`)")
    # no circular reasoning (validate_annotation.reasoning_cycles)
    for cyc in reasoning_cycles(graph["nodes"], graph["edges"]):
        (warn if cycle_noted(cyc, graph.get("metadata")) else err).append(
            "circular reasoning: " + " -> ".join(cyc) + ": " + CYCLE_HELP)
    has_edge = {e["source"] for e in graph["edges"]} | {e["target"] for e in graph["edges"]}
    has_child = {p for p in parent.values() if p}
    orphans = [i for i in ids if i not in has_edge and not parent.get(i) and i not in has_child]
    report["orphans"] = orphans
    for n in graph["nodes"]:
        if n.get("type") == "proof" and not any(
                e["source"] == n["id"] and e["type"] == ET.PROVES for e in graph["edges"]):
            warn.append(f"{n['id']}: proof with no proves edge")
        if n.get("type") in _LEVEL2 and n.get("parent_id") not in nodes:
            err.append(f"{n['id']}: parent_id {n.get('parent_id')!r} does not exist")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tex", required=True)
    ap.add_argument("--json", required=True)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    tex = open(args.tex, encoding="utf-8", errors="replace").read()
    graph = json.load(open(args.json, encoding="utf-8"))
    rep = finalize(graph, tex)
    print(f"nodes matched to environments: {rep['matched_to_environment']}; "
          f"labels filled: {rep['labels_filled']}; proves added: {len(rep['proves_added'])}; "
          f"\\ref uses added: {len(rep['ref_uses_added'])} "
          f"({len(rep['ref_backward'])} flagged backward)")
    print(f"parent_id set by containment: {rep['parents_set']}; backward edges: "
          f"{rep['backward_edges']}; orphans: {len(rep['orphans'])}")
    print(f"errors: {len(rep['errors'])}; warnings: {len(rep['warnings'])}")
    for e in rep["errors"][:40]:
        print("  ERROR  ", e)
    for w in rep["warnings"][:20]:
        print("  warning", w)
    if args.write and not rep["errors"]:
        tmp = args.json + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False, indent=1)
        os.replace(tmp, args.json)
    sys.exit(1 if rep["errors"] else 0)


if __name__ == "__main__":
    main()
