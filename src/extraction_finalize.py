#!/usr/bin/env python3
"""Finish an extracted graph with what the LaTeX source states by syntax, then check it.

The last stage of the v6 extraction, run by the extraction agent's builder
script before it writes the JSON. Everything here is deterministic and comes
from `latex_facts` (LaTeX syntax) and `algorithm_lines` (pseudocode numbering):

  label              the \\label key of the environment a node was extracted from
  source_line_label  the printed line number of an algorithm step
  proves edges       \\begin{proof}[Proof of Theorem~\\ref{x}], or a proof that
                     directly follows its theorem (amsthm convention)
  uses edges         a \\ref{key} inside a node's statement, pointing at another node

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
                   "source_problem", "not_extracted"}
_REF = re.compile(r"\\(?:" + _REF_CMDS + r")\*?\s*\{([^}]*)\}")


def _key(s: str) -> str:
    """Whitespace- and label-insensitive form of a span, for matching."""
    return re.sub(r"\s+", "", re.sub(r"\\(?:label|index)\s*\{[^{}]*\}", "", s or ""))


def match_nodes_to_facts(graph: dict, facts: dict) -> dict[str, str]:
    """node id -> fact id, for Level-1 nodes whose statement IS an environment body."""
    by_key: dict[str, str] = {}
    for f in facts["facts"]:
        k = _key(f["statement"])
        if len(k) > 10:
            by_key.setdefault(k, f["id"])
    out = {}
    for n in graph["nodes"]:
        if n.get("type") in _LEVEL2:
            continue
        fid = by_key.get(_key(n.get("statement")))
        if fid:
            out[n["id"]] = fid
    return out


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

    `headings` are the offsets of the paper's top-level section headings (not
    those inside an environment); a prose node that contains one is an error.

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
        if any(start < h < end for h in headings or ()):
            report["errors"].append(f"{n['id']}: prose node crosses a section heading "
                                    "(a proof continued elsewhere is one node per part)")
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


def check_defined_terms(graph: dict, spans: dict, parent: dict, report: dict) -> None:
    """Warn when a later node's statement uses a definition's `definiendum` (a
    plain-word term) and no edge links the definition to it, to the node's
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
    def term_of(d):
        t = d.get("definiendum") if d.get("type") == "definition" else None
        t = (t[0] if t else None) if isinstance(t, list) else t
        return t.strip() if t and len(t.strip()) >= 4 and not re.search(r"[$\\{}]", t) else None
    terms = {term_of(d) for d in graph["nodes"]} - {None}
    keys = re.compile(r"\\(?:" + _REF_CMDS + r"|label|cite[a-zA-Z]*)\*?\s*(?:\[[^\]]*\]\s*)?\{[^{}]*\}")
    for d in graph["nodes"]:
        term = term_of(d)
        if not term or d["id"] not in spans:
            continue
        pat = re.compile(r"(?<![\w-])" + re.escape(term) + r"(?:s|es)?(?![\w-])", re.I)
        longer = [re.compile(re.escape(u), re.I) for u in terms
                  if u.lower() != term.lower() and term.lower() in u.lower()]

        def uses(text):
            text = keys.sub(" ", text or "")
            for lp in longer:                 # "clone" inside "weighted clone" is the other term
                text = lp.sub(" ", text)
            return bool(pat.search(text))
        mine = family(d["id"])
        missing = [n["id"] for n in graph["nodes"]
                   if n["id"] not in mine and n["id"] in spans
                   and spans[n["id"]][0] > spans[d["id"]][0]
                   and uses(n.get("statement"))
                   and not (out.get(d["id"], set()) & family(n["id"]))]
        if missing:
            report["warnings"].append(f"{d['id']} defines {term!r}, used with no edge from it in: "
                                      + ", ".join(missing[:12]) + (" ..." if len(missing) > 12 else ""))


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
    report = {"matched_to_environment": len(n2f), "labels_filled": 0,
              "proves_added": [], "ref_uses_added": [], "ref_backward": [],
              "errors": [], "warnings": []}

    # 1. label
    for nid, fid in n2f.items():
        f = fact_by_id[fid]
        if f["labels"] and not nodes[nid].get("label"):
            nodes[nid]["label"] = f["labels"][0]
            report["labels_filled"] += 1

    # 2. source_line_label
    alg = fill_source_line_labels(graph, source)      # prepared: macros expanded
    for sid, lines in alg["merged"]:
        report["errors"].append(f"MERGED step {sid} spans printed lines {lines}: one step per line")

    # 3. hierarchy: parent_id = innermost containing node
    spans = node_spans(graph, source)
    parent = compute_hierarchy(graph, spans, report)

    pairs = {(e["source"], e["target"]) for e in graph["edges"]}

    # 4. proves edges stated by syntax
    for nid, fid in n2f.items():
        f = fact_by_id[fid]
        if f["kind"] != "proof" or not f.get("proves"):
            continue
        tgt = node_of_fact.get(f["proves"])
        if tgt is None or (nid, tgt) in pairs:
            continue
        if any(e["source"] == nid and e["type"] == ET.PROVES for e in graph["edges"]):
            continue                      # the agent already chose a target
        conf = 1.0 if f["proves_basis"] == "optarg" else 0.9
        graph["edges"].append({"source": nid, "target": tgt, "type": ET.PROVES,
                               "confidence": conf})
        pairs.add((nid, tgt))
        report["proves_added"].append((nid, tgt, f["proves_basis"]))

    # 5. uses edges from \ref, into Level-1 nodes and proof steps alike
    for n in graph["nodes"]:
        if n.get("type") == "algorithm_step":
            continue
        for key in _REF.findall(n.get("statement") or ""):
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
                if (src, tgt) in pairs or (tgt, src) in pairs:
                    continue
                graph["edges"].append({"source": src, "target": tgt, "type": ET.USES,
                                       "confidence": 0.95, "note": f"\\ref{{{k.strip()}}}"})
                pairs.add((src, tgt))
                report["ref_uses_added"].append((src, tgt, k.strip()))

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
                                   "confidence": n.get("confidence", 0.7)})
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

    # 7. the paper's full label table, so every \ref kept in a statement resolves
    graph.setdefault("metadata", {})["labels"] = label_table(facts, node_of_fact)
    unresolved = sorted({r["key"] for r in facts["refs"] if r["key"] not in facts["labels"]})
    graph["metadata"]["unresolved_refs"] = unresolved
    report["labels_total"] = len(graph["metadata"]["labels"])
    report["unresolved_refs"] = unresolved

    # 8. prose nodes: whole sentences, and no partial overlap between nodes
    headings = [x["start"] for x in facts["sections"] if x.get("inside") is None]
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


_SUBSPAN_FIELDS_STRICT = ("assumptions", "conclusions", "input", "output")
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
    comment = meta.get("extraction_comment") or ""
    if len(comment) > 600:
        warn.append(f"metadata.extraction_comment is {len(comment)} chars; keep it to 3 sentences")
    src_key = _key(source)
    for n in graph["nodes"]:
        st = n.get("statement")
        if not st:
            err.append(f"{n['id']}: empty statement")
        elif _key(st) not in src_key:
            (warn if n.get("type") in _LEVEL2 else err).append(
                f"{n['id']}: statement is not a verbatim span of the cleaned source")
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
        if ty == ET.USES and (s in _ancestors(t, parent) or t in _ancestors(s, parent)):
            err.append(f"edge {s}->{t}: a `uses` edge between a node and its own "
                       f"container; containment is parent_id, remove the edge")
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
