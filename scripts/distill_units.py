#!/usr/bin/env python3
"""
Unit distillation: learn rules that classify prose sentences, not extractors.

Environment nodes (theorem, lemma, proof, ... environments) come from the LaTeX
layer and the base parser; what is left for distillation is the prose: nodes
stated in running text (definitions, claims, cited results, prose proofs,
assumptions, ...). Fixed code cuts the prose into sentences
(src/prose_units.py); a rule (src/LLMVersion/unit_rules.py) is a regex on a
sentence plus a node type plus a span option ("this sentence", "N sentences",
"to the end of the paragraph"). The teacher writes only the regex. A rule is
accepted only after it has been tested on the training papers.

Algorithm (one call of `run`):

  prepare   every training paper: its sentences, its silver prose nodes, and
            which of them the base parser already finds (those are not targets)
  rounds    repeat until the validation gain stops or the budget is spent:
    repair  a rule whose precision has fallen below 1-alpha is tightened by the
            teacher (shown its false positives), else retired
    misses  silver prose nodes that no rule produces yet
    cluster misses grouped by the cue their first sentence carries (type, cue
            phrase or opening words, markup); largest cluster first; clusters
            below --min-cluster are skipped
    propose one teacher call per cluster: positives (the cluster's first
            sentences, from many papers) and look-alikes (sentences with the
            same cue that are not nodes); the span option is chosen from the
            data, not by the teacher
    refine  the rule is run on every training sentence; accepted if precision
            >= 1-alpha with at least --min-tp true positives, on the fitting
            papers and on the validation papers; otherwise the teacher is
            shown its false positives and asked for a tighter rule, up to
            --max-refine times; then dropped
    cleanup a rule whose removal does not lower F1 on the fitting papers is retired
  final     snapshots in the layout of the merged algorithm and a report of
            prose-stratum precision/recall on the fitting and validation papers
            (test scoring: scripts/compare_distillers.py)

Run through the common driver:

    python scripts/silver_distillation_merged.py --alg units \\
        --pilot-papers train --tex-dir <staged tex> --eval-dir <out> \\
        --model claude-haiku-5-5
"""
from __future__ import annotations

import json
import random
import re
import sys
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO / "scripts", REPO / "src" / "LLMVersion", REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import distillation_analysis as da                     # noqa: E402
import latex_facts as L                                # noqa: E402
import match_modes as mm                               # noqa: E402
import node_metrics as NM                              # noqa: E402
import node_similarity as NSIM                         # noqa: E402
import prose_units as U                                # noqa: E402
import distill_common as C                             # noqa: E402
import unit_rules as UR                                # noqa: E402
from distill_registry import RuleRegistry, STATUS_ACTIVE   # noqa: E402

SCORED = C.TYPES                           # the 14 node types distillation scores

# cue phrases, in order: the first one found in a sentence names its cluster
_CUES = [(c, re.compile(p)) for c, p in [
    ("we say", r"\bwe say\b"), ("is called", r"\b(?:is|are) called\b"),
    ("said to be", r"\bsaid to be\b"), ("we call", r"\bwe call\b"),
    ("we define", r"\bwe define\b"), ("is defined", r"\b(?:is|are) defined\b"),
    ("denote", r"\bdenot(?:e|es|ed)\b"), ("we write", r"\bwe write\b"),
    ("assume", r"\bassum(?:e|es|ing)\b"), ("suppose", r"\bsuppose\b"),
    ("we claim", r"\bwe claim\b"), ("conjecture", r"\bconjectur"),
    ("open question", r"\bopen (?:question|problem)\b"), ("question", r"\bquestion\b"),
    ("recall", r"\brecall\b"), ("proved", r"\b(?:proved|showed|established) (?:that|in)\b"),
    ("theorem", r"\btheorem\b"), ("lemma", r"\blemma\b"), ("proof", r"\bproof\b"),
    ("example", r"\bexample\b"), ("algorithm", r"\balgorithm\b"), ("step", r"\bstep\b"),
    ("note that", r"\bnote that\b"), ("observe", r"\bobserve\b"),
    ("it follows", r"\bit follows\b"), ("we show", r"\bwe (?:show|prove)\b"),
    ("let", r"^let\b"), ("consider", r"^consider\b"),
]]


# ---------------------------------------------------------------------------
# training data
# ---------------------------------------------------------------------------

@dataclass
class Node:
    type: str
    start: int
    end: int
    first: int                  # index of its first sentence (its anchor)
    last: int
    tokens: frozenset
    base_covered: bool = False  # the base parser already finds it: not a target


@dataclass
class Paper:
    pid: str
    text: str
    sents: list
    sent_text: list
    nodes: list                       # silver prose nodes of the scored types
    # the base parser against ALL silver nodes of the paper (environments too):
    # the constant part of the overall F the rules are chosen to raise
    base_tp: float = 0              # credits under the training metric (fractional for m1g)
    base_fp: float = 0
    n_silver: int = 0
    anchor: dict = field(default_factory=dict)   # sentence index -> Node starting there
    inside: set = field(default_factory=set)     # sentence indices inside a node, not its anchor
    _sig: list = field(default_factory=list)

    def sig(self, i: int) -> tuple:
        """signature() of sentence i, computed once."""
        if not self._sig:
            self._sig = [signature(t) for t in self.sent_text]
        return self._sig[i]


def _plain(s: str) -> str:
    s = re.sub(r"\$[^$]*\$", " math ", s)
    s = re.sub(r"\\(?:emph|textit|textbf|text|textsl|mathrm)\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\*?", " ", s)
    return " ".join(re.sub(r"[{}\[\]()~]", " ", s).lower().split())


def signature(sent: str) -> tuple:
    """(cue, markup flags) of a sentence: what a rule can key on."""
    p = _plain(sent)
    cue = next((c for c, pat in _CUES if pat.search(p)), None)
    if cue is None:
        cue = "lead:" + " ".join(p.split()[:2])
    flags = []
    if re.search(r"\\(?:emph|textit|textsl)\s*\{|\{\\(?:em|it|sl)\b", sent):
        flags.append("emph")
    if re.match(r"\s*(?:\\noindent\s*)?(?:\\textbf\s*\{|\{\\bf\b|\\paragraph\b)", sent):
        flags.append("bold")
    if "\\cite" in sent:
        flags.append("cite")
    if sent.lstrip().startswith("\\item"):
        flags.append("item")
    if sent.rstrip().endswith(":"):
        flags.append("colon")
    return cue, tuple(flags)


_sq = U._sq


def type_weight(metric: str):
    """How much a match between two node types counts: the type table for the
    graded metric (m1g, the headline), same type only for m1."""
    return NSIM.type_compat if metric == "m1g" else (lambda a, b: 1.0 if a == b else 0.0)


def load_paper(pid: str, tex_dir: Path, t2_dir: Path, base_buckets: dict, th: float,
               metric: str = "m1g") -> Paper | None:
    main = L.find_main_tex(tex_dir / pid / "source")
    jf = t2_dir / f"{pid}.json"
    if not main or not jf.is_file():
        return None
    text = da.paper_text(str(main))
    # sentences as the parser's rules will see them: cut from the document body
    # it hands them; the full source (with the preamble's macros and theorem
    # declarations) only to find and classify the silver nodes
    sents = U.sentences(L.extract_facts(text))
    loc = U.Locator(L.read_tex(str(main)))
    src = loc.fx["source"]
    body = src.find("\\begin{document}")
    body = body + len("\\begin{document}") if body >= 0 else 0
    if src[body:] != text:
        print(f"  [warn] {pid}: prepared text differs from the parser's; skipped")
        return None
    silver = [n for n in json.load(open(jf, encoding="utf-8"))["nodes"]
              if n.get("type") in SCORED and (n.get("statement") or "").strip()]
    toks = [frozenset(mm.tokens(n["statement"])) for n in silver]
    # the base parser against every silver node, with the reported metric itself
    base_preds = [(t, x) for t in SCORED for x in base_buckets.get(t, [])]
    pc, gc = NM.score(base_preds, [(n["type"], n["statement"]) for n in silver], metric, th)
    nodes = []
    for k, (n, prepared) in enumerate(zip(silver, loc.prepare([n["statement"] for n in silver]))):
        span = loc.locate(prepared)
        if loc.stratum(span) != "prose":
            continue                       # an environment's body, nested in one, or not found
        a, b = span[0] - body, span[1] - body          # offsets into `text`
        covered = [k for k, x in enumerate(sents) if x.start < b and a < x.end]
        if not covered:
            continue
        nodes.append(Node(n["type"], a, b, covered[0], covered[-1], toks[k], gc[k] > 0))
    p = Paper(pid, text, sents, [text[s.start:s.end] for s in sents], nodes,
              base_tp=sum(gc), base_fp=len(base_preds) - sum(pc), n_silver=len(silver))
    for n in nodes:
        p.anchor.setdefault(n.first, n)
        p.inside.update(range(n.first + 1, n.last + 1))
    return p


# ---------------------------------------------------------------------------
# scoring a rule, and a rule set
# ---------------------------------------------------------------------------

class Scorer:
    """Matches predicted nodes against a paper's silver prose nodes with the
    reported metric's own test (token containment >= threshold, same type).
    A prediction of a node the base parser already finds is neutral: the
    parser's merge drops it as a duplicate."""

    def __init__(self, papers: dict, th: float, beta: float = 1.0, metric: str = "m1g"):
        self.papers, self.th, self.beta = papers, th, beta
        self.weight = type_weight(metric)
        self.fire = defaultdict(dict)          # uid -> pid -> set of sentence indices

    def fire_sets(self, rule: dict, pids) -> dict:
        """Where a rule fires, per paper. A rule that does not compile, or that
        cannot finish on some sentence (UR.SlowRule), fires nowhere, so it is
        rejected like any rule that finds nothing."""
        c = UR.compile_rule(rule)
        out = {pid: set() for pid in pids}
        if c is None:
            return out
        try:
            for pid in pids:
                out[pid] = {i for i, s in enumerate(self.papers[pid].sent_text) if UR.fires(c, s)}
        except UR.SlowRule:
            print(f"    [slow] {rule.get('regex', '')[:60]!r} exceeded {UR.MATCH_TIMEOUT}s on a "
                  "sentence: rejected", flush=True)
            return {pid: set() for pid in pids}
        return out

    def cache(self, rule: dict, pids) -> None:
        missing = [pid for pid in pids if pid not in self.fire[rule["uid"]]]
        self.fire[rule["uid"]].update(self.fire_sets(rule, missing))

    def match(self, p: Paper, preds: list, toks=None) -> dict:
        """{prediction index: (silver node, credit)}: the reported metric's own
        one-to-one pairing (node_metrics._one_to_one); the credit is the type
        compatibility. `toks`: the predictions' token sets, if already known."""
        toks = toks or [frozenset(mm.tokens(p.text[q["start"]:q["end"]])) for q in preds]
        return NM._one_to_one([(q["type"], t) for q, t in zip(preds, toks)],
                              [(n.type, n.tokens) for n in p.nodes], self.weight, self.th)

    def score(self, rules: list[dict], pids, fire_override: dict | None = None) -> dict:
        """Counts over papers for a rule set: tp (new silver nodes found), fp,
        neutral (already found by the base parser), and per-rule tp/fp and the
        silver nodes each rule recovered."""
        tot = {"tp": 0, "fp": 0, "neutral": 0, "targets": 0, "per_rule": defaultdict(
            lambda: {"tp": 0, "fp": 0, "papers": defaultdict(lambda: [0, 0])}), "found": set()}
        for pid in pids:
            p = self.papers[pid]
            tot["targets"] += sum(not n.base_covered for n in p.nodes)
            fs = {}
            for r in rules:
                src = fire_override if fire_override and r["uid"] in fire_override else self.fire
                fs[r["uid"]] = src[r["uid"]].get(pid, set())
            preds = UR.select(p.sents, rules, fs)
            m = self.match(p, preds)
            for i, pred in enumerate(preds):
                k, w = m.get(i, (None, 0.0))
                pr = tot["per_rule"][pred["uid"]]
                if k is not None and p.nodes[k].base_covered:
                    tot["neutral"] += 1
                elif k is not None:               # credit w, the rest an error (graded)
                    tot["tp"] += w; pr["tp"] += w; pr["papers"][pid][0] += w
                    tot["fp"] += 1 - w; pr["fp"] += 1 - w; pr["papers"][pid][1] += 1 - w
                    if w >= 1.0:                  # a node found with another type stays a target
                        tot["found"].add((pid, k))
                else:
                    tot["fp"] += 1; pr["fp"] += 1; pr["papers"][pid][1] += 1
        tp, fp, tg = tot["tp"], tot["fp"], tot["targets"]
        tot["precision"] = tp / (tp + fp) if tp + fp else 0.0
        tot["recall"] = tp / tg if tg else 0.0
        tot["f1"] = (2 * tot["precision"] * tot["recall"] / (tot["precision"] + tot["recall"])
                     if tot["precision"] + tot["recall"] else 0.0)
        # overall: the base parser on all silver nodes, plus what the rules add
        all_tp = sum(self.papers[p].base_tp for p in pids) + tp
        all_fp = sum(self.papers[p].base_fp for p in pids) + fp
        all_fn = max(sum(self.papers[p].n_silver for p in pids) - all_tp, 0)
        b2 = self.beta ** 2
        den = (1 + b2) * all_tp + b2 * all_fn + all_fp
        tot.update(all_tp=all_tp, all_fp=all_fp, all_fn=all_fn,
                   F=(1 + b2) * all_tp / den if den else 0.0,
                   R=all_tp / (all_tp + all_fn) if all_tp + all_fn else 0.0,
                   FDR=all_fp / (all_tp + all_fp) if all_tp + all_fp else 0.0)
        return tot


# ---------------------------------------------------------------------------
# the teacher
# ---------------------------------------------------------------------------

SYSTEM = """You write UNIT RULES for a rule-based extractor of mathematical papers.

The extractor cuts the running prose of a LaTeX paper into sentences. A unit rule
is ONE Python regular expression, applied with re.search to the LaTeX source of a
single sentence. Where it matches, that sentence starts a node of the target type
(definition, claim, theorem, proof, remark, assumption, ...).

Requirements:
- Key on STRUCTURE that generalises across papers: cue phrases ("we say", "is
  called", "assume that", "it is known that"), sentence openings, markup
  (\\emph{...}, \\textbf{...}, \\cite{...}, \\item). Never on words specific to one
  paper (names, notation, topic words): the rule must work on papers it has not seen.
- Match the POSITIVE sentences and none of the NEGATIVE ones. Simple and precise
  beats clever: a rule that also fires on negatives will be rejected.
- Python `re` syntax. Flags as letters: "i" ignore case, "s" dot matches newline.

Reply with ONLY a JSON object, no markdown fences:
{"regex": "...", "flags": "i", "name": "short_snake_case_name", "reasoning": "one sentence"}
In JSON, write every backslash of the regex doubled (\\\\b, \\\\emph).
"""


def _examples(lines, prefix):
    """Numbered sentences for a prompt (the caller has already chosen how many)."""
    return "".join(f"{prefix} {i + 1}: {re.sub(chr(10), ' ', s)[:400]}\n" for i, s in enumerate(lines))


def propose_prompt(ntype: str, pos: list, neg: list) -> str:
    return (f"TARGET TYPE: {ntype}\n\nPOSITIVE sentences (each starts a {ntype} node):\n"
            + _examples(pos, "EXAMPLE")
            + ("\nNEGATIVE sentences (same cue, but NOT the start of a "
               f"{ntype} node):\n" + _examples(neg, "NEGATIVE") if neg else "")
            + "\nWrite one unit rule.")


def tighten_prompt(ntype: str, rule: dict, keep: list, wrong: list) -> str:
    return (f"TARGET TYPE: {ntype}\n\nCURRENT RULE: {json.dumps(rule['regex'])} "
            f"flags {json.dumps(rule.get('flags', ''))}\n\n"
            f"It ALSO matched these sentences, which do NOT start a {ntype} node:\n"
            + _examples(wrong, "NEGATIVE")
            + "\nIt must keep matching these:\n" + _examples(keep, "EXAMPLE")
            + "\nWrite a tighter unit rule.")


class TeacherError(RuntimeError):
    """The teacher could not be called (no SDK, no key, network, API error)."""


def broaden_prompt(ntype: str, rule: dict, keep: list, missed: list, wrong: list) -> str:
    return (f"TARGET TYPE: {ntype}\n\nCURRENT RULE: {json.dumps(rule['regex'])} "
            f"flags {json.dumps(rule.get('flags', ''))}\n\n"
            f"It does NOT yet match these sentences, which DO start a {ntype} node:\n"
            + _examples(missed, "EXAMPLE")
            + "\nIt already matches these, and must keep matching them:\n"
            + _examples(keep, "EXAMPLE")
            + (f"\nIt must NOT match these (they do not start a {ntype} node):\n"
               + _examples(wrong, "NEGATIVE") if wrong else "")
            + "\nWrite a broader unit rule.")


JUDGE_SYSTEM = """You check the output of a rule-based extractor of mathematical papers
against a reference extraction that is good but not complete.

You get sentences from papers (LaTeX source), each with the sentence that follows it.
For each, decide whether the sentence STARTS a node of the given type: a statement a
careful reader would extract on its own as that kind of item (a definition introduces
a term or notation for later use; a claim asserts something that is argued or used;
a theorem states a result; and so on). Recalling or restating something defined
earlier, discussion, and motivation are NOT new nodes.

Reply with ONLY a JSON array, one object per sentence, no markdown fences:
[{"index": <int>, "is_node": true|false}]
"""


def judge_prompt(ntype: str, items: list) -> str:
    return (f"TYPE: {ntype}\n\n" + "".join(
        f"SENTENCE {k}: {re.sub(chr(10), ' ', a)[:400]}\n   NEXT: {re.sub(chr(10), ' ', b)[:200]}\n"
        for k, (a, b) in enumerate(items)))


_RESEND = ("\n\nIMPORTANT: reply with ONLY the JSON object. Inside JSON strings every "
           "backslash of the regex must be doubled (\\\\b, \\\\s, \\\\$).")


def ask(model: str, prompt: str, usage: dict) -> dict | None:
    """The teacher's rule, or None if its reply is unusable. A failed CALL raises
    TeacherError: that is not an answer about the cluster, and must not be
    recorded as one."""
    try:
        text, _ = da.call_llm(model, SYSTEM, prompt, 8192, usage)   # room for thinking: pay only for what is used
    except Exception as e:
        raise TeacherError(f"{type(e).__name__}: {e}") from e
    objs = da._parse_json_array(text)
    obj = objs[0] if objs else None
    if not isinstance(obj, dict) or not isinstance(obj.get("regex"), str):
        if not prompt.endswith(_RESEND):            # one resend, with the format spelled out
            print(f"    [teacher] unusable reply, asking once more: {text[:120]!r}")
            return ask(model, prompt + _RESEND, usage)
        print(f"    [teacher] unusable reply: {text[:160]!r}")
        return None
    flags = "".join(ch for ch in str(obj.get("flags", "")) if ch in "isxm")
    return {"regex": obj["regex"], "flags": flags,
            "name": re.sub(r"\W+", "_", str(obj.get("name") or "rule"))[:40],
            "reasoning": str(obj.get("reasoning", ""))[:300]}


# ---------------------------------------------------------------------------
# the algorithm
# ---------------------------------------------------------------------------

def best_span(papers: dict, items) -> str:
    """The span option that best reproduces the silver spans of these nodes
    (mean character overlap), so the teacher never decides boundaries."""
    def overlap(p, n, span):
        j = UR.span_end(p.sents, n.first, span)
        a, b = p.sents[n.first].start, p.sents[j].end
        inter = max(0, min(b, n.end) - max(a, n.start))
        return inter / (max(b, n.end) - min(a, n.start))
    scores = {sp: sum(overlap(papers[pid], n, sp) for pid, n in items) for sp in UR.SPANS}
    return max(UR.SPANS, key=lambda sp: (scores[sp], -UR.SPANS.index(sp)))


def spread(items, k, seed=0):
    """Up to k items (all if k is None), round-robin across papers so that one
    paper cannot dominate a sample."""
    if k is None:
        k = len(items)
    by = defaultdict(list)
    for pid, x in items:
        by[pid].append((pid, x))
    rnd = random.Random(seed)
    pids = sorted(by)
    rnd.shuffle(pids)
    out = []
    while len(out) < k and any(by.values()):
        for pid in pids:
            if by[pid] and len(out) < k:
                out.append(by[pid].pop(0))
    return out


class UnitDistiller:
    def __init__(self, args, papers: dict, fit: list, val: list, eval_dir: Path):
        self.a, self.papers, self.fit, self.val = args, papers, fit, val
        self.dir = eval_dir / "units"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.reg = RuleRegistry.load(self.dir / "registry.json")
        self.scorer = Scorer(papers, args.threshold, args.beta, args.train_metric)
        self._current: dict = {}
        self.usage = da._empty_usage()
        self.failures, self.stopped = 0, False
        self.log_path = self.dir / "log.jsonl"
        state = self.dir / "state.json"
        self.state = json.loads(state.read_text()) if (args.resume and state.is_file()) else \
            {"round": 0, "tried": [], "llm_calls": 0}
        # cumulative over resumes: tokens per stage, accepted rules, snapshots, seconds
        self.by_stage = defaultdict(da._empty_usage, self.state.get("usage_by_stage", {}))
        self.phase = ""                     # "repair:" while repairing old rules
        self.t0 = time.time() - self.state.get("seconds", 0)
        # clusters are worked on in parallel threads (--parallel): shared counters
        # under a lock, and each cluster's log lines printed together when it is done
        self.lock = threading.RLock()
        self._tl = threading.local()
        for r in self.reg.active():
            self.scorer.cache(self.as_rule(r), fit + val)

    # -- bookkeeping -----------------------------------------------------------
    def lim(self, name: str):
        """A count option; 0 (or None) means no limit."""
        v = getattr(self.a, name, None)
        return None if not v else int(v)

    @staticmethod
    def as_rule(r) -> dict:
        return {"uid": r.uid, "name": r.name, "type": r.group, "regex": r.pattern_src,
                "flags": r.spec.get("flags", ""), "span": r.spec.get("span", "1"),
                "precision": r.spec.get("precision", 0.0)}

    def active(self) -> list:
        return [self.as_rule(r) for r in self.reg.active()]

    def save(self) -> None:
        self.reg.save()
        self.state["usage_by_stage"] = dict(self.by_stage)
        self.state["seconds"] = round(time.time() - self.t0)
        (self.dir / "state.json").write_text(json.dumps(self.state, indent=1))

    def say(self, msg: str) -> None:
        """Print, or (inside a cluster's thread) keep for printing with its cluster."""
        buf = getattr(self._tl, "buf", None)
        if buf is None:
            print(msg, flush=True)
        else:
            buf.append(msg)

    def book(self, stage: str, usage: dict, seconds: float) -> None:
        with self.lock:
            st = self.by_stage[self.phase + stage]
            for k, v in usage.items():
                st[k] = st.get(k, 0) + v
                self.usage[k] = self.usage.get(k, 0) + v
            st["seconds"] = round(st.get("seconds", 0) + seconds, 2)

    def charge(self, stage: str, fn, *args):
        """One teacher call, fn(*args, usage), booked with its tokens and wall
        time under `stage` (propose, tighten, broaden, judge; repair:... when
        repairing an old rule)."""
        u, t = da._empty_usage(), time.perf_counter()
        try:
            return fn(*args, u)
        finally:
            self.book(stage, u, time.perf_counter() - t)

    def cost(self) -> float:
        """Teacher cost so far, over resumes (the judge may be another model)."""
        with self.lock:
            return sum(da.estimate_cost(u, self.a.judge_model or self.a.model
                                        if k.endswith("judge") else self.a.model)
                       for k, u in self.by_stage.items())

    def calls(self) -> int:
        with self.lock:
            return sum(u.get("llm_calls", 0) for u in self.by_stage.values())

    def checkpoint(self, label: str) -> None:
        """Freeze the active rules as the next snapshot and log where the run is:
        the learning curve. Taken every --snapshot-every accepted rules and at
        the end of each round."""
        n = self.state.get("snapshots", 0) + 1
        self.state["snapshots"] = n
        name = f"step_{n:03d}_{label}"
        write_rules(self.dir.parent / "snapshots" / name, self.active())
        fit, val = self.scorer.score(self.active(), self.fit), self.scorer.score(self.active(), self.val)
        row = {"snapshot": name, "round": self.state["round"],
               "accepted": self.state.get("accepted", 0), "active": len(self.reg.active()),
               "llm_calls": self.calls(), "cost_usd": round(self.cost(), 4),
               "seconds": round(time.time() - self.t0),
               **{f"{lab}_{k}": (round(r[k], 4) if isinstance(r[k], float) else r[k])
                  for lab, r in (("fit", fit), ("val", val))
                  for k in ("tp", "fp", "targets", "precision", "recall", "f1",
                            "all_tp", "all_fp", "all_fn", "F", "R", "FDR")}}
        with open(self.dir / "trajectory.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        self.save()

    def log(self, **kw) -> None:
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": round(time.time()), **kw}) + "\n")

    def budget_left(self) -> bool:
        return not self.stopped and self.calls() < self.a.max_llm_calls

    def call_failed(self, e) -> None:
        """Three failed teacher calls in a row stop the run (no key, no SDK,
        no credit, network down): working through every cluster would only
        mark them all as failed."""
        with self.lock:
            self.failures += 1
            n = self.failures
            if n >= 3:
                self.stopped = True
        self.say(f"    [teacher] call failed ({n} in a row): {e}")
        if n >= 3:
            self.say("  [teacher] 3 failed calls in a row: stopping. Fix the cause and "
                     "rerun with --resume; no cluster was marked as tried.")

    # -- one candidate rule ------------------------------------------------------
    def test(self, cand: dict, pids) -> dict:
        """A candidate alone on `pids`: its true/false positives."""
        rule = dict(cand, uid=-1, precision=1.0)
        fs = {-1: self.scorer.fire_sets(rule, pids)}
        return self.scorer.score([rule], pids, fire_override=fs)

    def current(self, pids, without=None, rules=None) -> dict:
        """Scores of a rule set (default the active rules; minus rule `without`),
        memoised per rule set."""
        rules = [r for r in (self.active() if rules is None else rules) if r["uid"] != without]
        key = (tuple(sorted(r["uid"] for r in rules)), tuple(pids))
        if key not in self._current:
            self._current[key] = self.scorer.score(rules, pids)
        return self._current[key]

    def joint(self, cand: dict, pids, without=None, rules=None) -> dict:
        """A candidate added to the active rules (replacing rule `without`):
        the rule set's scores, "gain" = its overall F minus the set's without
        it, and "alone" = the candidate's own counts (its precision orders it
        among the rules where several fire on one sentence)."""
        rule = dict(cand, uid=-1, precision=1.0)
        fs = {-1: self.scorer.fire_sets(rule, pids)}
        alone = self.scorer.score([rule], pids, fire_override=fs)
        rule["precision"] = alone["precision"]
        base = self.active() if rules is None else rules
        res = self.scorer.score([r for r in base if r["uid"] != without] + [rule], pids,
                                fire_override=fs)
        cur = self.current(pids, without, base)
        res["gain"] = res["F"] - cur["F"]
        res["dtp"] = res["all_tp"] - cur["all_tp"]
        dfp = res["all_fp"] - cur["all_fp"]
        res["rule_fdr"] = dfp / (res["dtp"] + dfp) if res["dtp"] + dfp > 0 else 0.0
        res["fired"] = res["dtp"] + dfp
        res["alone"] = alone
        return res

    def evaluate(self, cand: dict, without=None, rules=None) -> tuple:
        """(fit, val) scores of a candidate, as the acceptance criterion needs them,
        against `rules` (default: the active rules)."""
        t = time.perf_counter()
        if self.a.accept in ("f1", "fdr"):
            out = (self.joint(cand, self.fit, without, rules),
                   self.joint(cand, self.val, without, rules))
        else:
            out = self.test(cand, self.fit), self.test(cand, self.val)
        self.book("scoring", {}, time.perf_counter() - t)
        return out

    @staticmethod
    def counts(res: dict) -> str:
        a = res.get("alone", res)
        g = f" F {res['gain'] * 100:+.3f}" if "gain" in res else ""
        if "dtp" in res:
            g += f" adds {res['dtp']:+.1f} tp at FDR {res['rule_fdr']:.2f} (overall {res['FDR']:.3f})"
        return f"tp={a['tp']:g} fp={a['fp']:g}{g}"

    def value(self, res: dict) -> float:
        """What refinement maximises. --accept f1: the gain in overall F of the
        rule set. --accept precision: true positives minus --fp-weight x false
        positives (precision alone is maximised by matching nothing)."""
        if self.a.accept == "f1":
            return res["gain"]
        if self.a.accept == "fdr":     # nodes found, while the FDR stays <= max_fdr
            return res["dtp"] - 1e6 * max(0.0, self.fdr(res) - self.a.max_fdr)
        return res["tp"] - self.a.fp_weight * res["fp"]

    def fdr(self, res: dict) -> float:
        """--accept fdr: the FDR held to --max-fdr: of what the rule adds (scope
        rule), or of the whole extractor (scope overall)."""
        return res["rule_fdr"] if self.a.fdr_scope == "rule" else res["FDR"]

    def objective(self, res: dict) -> float:
        """The rule SET's score: what cleanup keeps and the stopping rule watches."""
        return res["R"] if self.a.accept == "fdr" else res["F"]

    def acceptable(self, fit: dict, val: dict) -> bool:
        if self.a.accept == "f1":
            return (fit["alone"]["tp"] >= self.a.min_tp and fit["gain"] > self.a.min_gain
                    and val["gain"] >= -self.a.val_tolerance)
        if self.a.accept == "fdr":
            a = fit["alone"]
            if self.a.fdr_scope == "rule":     # validation: only where the rule fires enough
                ok_val = val["fired"] < self.a.val_min_fired or \
                    val["rule_fdr"] <= self.a.max_fdr + self.a.val_tolerance
            else:
                ok_val = val["FDR"] <= self.a.max_fdr + self.a.val_tolerance
            return (fit["dtp"] >= self.a.min_tp and fit["rule_fdr" if self.a.fdr_scope == "rule"
                                                       else "FDR"] <= self.a.max_fdr
                    and a["tp"] >= self.a.rule_min_precision * (a["tp"] + a["fp"]) and ok_val)
        fired = fit["tp"] + fit["fp"]
        ok_fit = fit["tp"] >= self.a.min_tp and fit["tp"] >= self.a.min_precision * fired
        fired_val = val["tp"] + val["fp"]
        ok_val = fired_val < self.a.val_min_fired or val["tp"] >= self.a.min_precision * fired_val
        return ok_fit and ok_val

    def firings(self, cand: dict, ntype: str) -> tuple:
        """(true, false) firings of a candidate on the fitting papers, as
        [(pid, sentence index)]: true where the sentence starts a target node of
        its type."""
        rule = dict(cand, uid=-1, precision=1.0)
        fs = self.scorer.fire_sets(rule, self.fit)
        tp, fp = [], []
        for pid in self.fit:
            p = self.papers[pid]
            for i in sorted(fs[pid]):
                n = p.anchor.get(i)
                if n is not None and n.type == ntype:
                    if not n.base_covered:
                        tp.append((pid, i))
                elif not any(m.first <= i <= m.last for m in p.nodes if m.type == ntype):
                    fp.append((pid, i))         # inside a node of its type: a boundary case
        return tp, fp

    def lookalikes(self, ntype: str, cue: str) -> list:
        """Sentences of the fitting papers with the cluster's cue that start no
        node of its type and lie inside none (those are boundary cases, not
        negatives): [(pid, sentence)]."""
        out = []
        for pid in self.fit:
            p = self.papers[pid]
            inside = {i for m in p.nodes if m.type == ntype for i in range(m.first, m.last + 1)}
            out += [(pid, p.sent_text[i]) for i in range(len(p.sents))
                    if i not in inside and p.sig(i)[0] == cue]
        return out

    def judged_errors(self, ntype: str, fps: list) -> list:
        """The false positives the judge confirms as errors. The rest are most
        likely nodes the silver missed: tightening against them would teach the
        rule to exclude real ones."""
        sample = spread(fps, self.lim("max_refine_examples"), seed=3)
        if self.a.judge == "none" or not sample or not self.budget_left():
            return sample
        items = []
        for pid, i in sample:
            p = self.papers[pid]
            items.append((p.sent_text[i], p.sent_text[i + 1] if i + 1 < len(p.sents) else ""))
        try:
            text, _ = self.charge("judge", da.call_llm, self.a.judge_model or self.a.model,
                                  JUDGE_SYSTEM, judge_prompt(ntype, items), 8192)
        except Exception as e:
            self.call_failed(TeacherError(f"{type(e).__name__}: {e}"))
            return sample
        genuine = {int(o.get("index", -1)) for o in da._parse_json_array(text)
                   if isinstance(o, dict) and o.get("is_node") is True}
        with self.lock:
            self.state["judged_silver_misses"] = self.state.get("judged_silver_misses", 0) + len(genuine)
        return [x for k, x in enumerate(sample) if k not in genuine]

    def refine(self, cand: dict, ntype: str, cluster: list, without=None, rules=None) -> tuple:
        """Hill-climb a candidate: each step tries to tighten it (on the false
        positives the judge confirms) and to broaden it (on the cluster's nodes it
        still misses), and keeps the better result if it raises value() on the
        fitting papers without lowering it on the validation papers by more than
        --val-tolerance. Stops at a local maximum or after --max-refine steps.
        Returns (rule, fit counts) if the best version is acceptable, else (None, ...)."""
        best = cand
        bfit, bval = self.evaluate(best, without, rules)
        self.say(f"    step 0: {best['regex'][:70]!r} span={best['span']} "
                 f"fit {self.counts(bfit)}  val {self.counts(bval)}")
        for step in range(1, self.a.max_refine + 1):
            if not self.budget_left():
                break
            tps, fps = self.firings(best, ntype)
            keep = [self.papers[pid].sent_text[i]
                    for pid, i in spread(tps, self.lim("max_refine_examples"), seed=4)]
            moves = []
            if fps and "tighten" in self.a.refine_moves:
                errors = self.judged_errors(ntype, fps)
                wrong = [self.papers[pid].sent_text[i] for pid, i in errors]
                if wrong:
                    moves.append(("tighten", tighten_prompt(ntype, best, keep, wrong)))
            if cluster and "broaden" in self.a.refine_moves:
                fired = {(pid, i) for pid, i in tps}
                missed = [(pid, n) for pid, n in cluster if (pid, n.first) not in fired]
                if missed:
                    wrong = [self.papers[pid].sent_text[i]
                             for pid, i in spread(fps, self.lim("max_refine_examples"), seed=5)]
                    moves.append(("broaden", broaden_prompt(
                        ntype, best, keep, [self.papers[pid].sent_text[n.first]
                                            for pid, n in spread(missed, self.lim("max_refine_examples"),
                                                                 seed=6)], wrong)))
            improved = None
            for name, prompt in moves:
                if not self.budget_left():
                    break
                try:
                    new = self.charge(name, ask, self.a.model, prompt)
                except TeacherError as e:
                    self.call_failed(e)
                    break
                if new is None:
                    continue
                c = dict(new, type=ntype, span=best["span"])
                cfit, cval = self.evaluate(c, without, rules)
                self.say(f"    step {step} {name}: {c['regex'][:60]!r} fit {self.counts(cfit)}  "
                         f"val {self.counts(cval)}")
                better = self.value(cfit) > self.value(bfit) and \
                    self.value(cval) >= self.value(bval) - self.a.val_tolerance
                if better and (improved is None or self.value(cfit) > self.value(improved[1])):
                    improved = (c, cfit, cval)
            if improved is None:
                break                                    # a local maximum
            best, bfit, bval = improved
        if self.acceptable(bfit, bval):
            return best, bfit
        return None, bfit

    # -- one round ---------------------------------------------------------------
    def misses(self) -> list:
        res = self.scorer.score(self.active(), self.fit)
        return [(pid, n) for pid in self.fit for k, n in enumerate(self.papers[pid].nodes)
                if not n.base_covered and (pid, k) not in res["found"]]

    def clusters(self, misses) -> list:
        fine, coarse = defaultdict(list), defaultdict(list)
        for pid, n in misses:
            cue, flags = self.papers[pid].sig(n.first)
            fine[(n.type, cue, flags)].append((pid, n))
        out = []
        for key, items in fine.items():
            if len(items) >= self.a.min_cluster:
                out.append((key, items))
            else:
                coarse[(key[0], key[1], ())].extend(items)
        out += [(k, v) for k, v in coarse.items() if len(v) >= self.a.min_cluster]
        return sorted(out, key=lambda kv: -len(kv[1]))

    def repair(self) -> None:
        """Tighten (or retire) active rules that now over-fire on the fitting papers."""
        res = self.scorer.score(self.active(), self.fit)
        for rule in self.active():
            st = res["per_rule"][rule["uid"]]
            fired = st["tp"] + st["fp"]
            if self.a.accept == "f1":       # a rule the overall F is better without
                hurts = self.current(self.fit, rule["uid"])["F"] > self.current(self.fit)["F"]
                why = "lowers the overall F"
            elif self.a.accept == "fdr":    # a rule whose own (marginal) FDR is now over q
                with_ = self.current(self.fit)
                wo = self.current(self.fit, rule["uid"])
                dtp, dfp = with_["all_tp"] - wo["all_tp"], with_["all_fp"] - wo["all_fp"]
                rule_fdr = dfp / (dtp + dfp) if dtp + dfp > 0 else 0.0
                hurts = (rule_fdr if self.a.fdr_scope == "rule" else with_["FDR"]) > self.a.max_fdr \
                    and (self.a.fdr_scope == "rule" or (fired and st["tp"] < (1 - self.a.max_fdr) * fired))
                why = f"FDR {rule_fdr:.2f} over {self.a.max_fdr}"
            else:
                hurts = fired and st["tp"] < self.a.min_precision * fired
                why = f"precision {st['tp'] / max(fired, 1):.2f} < {self.a.min_precision}"
            if not hurts or rule["uid"] not in {r["uid"] for r in self.active()}:
                continue
            print(f"  [repair] uid {rule['uid']} {rule['name']}: tp={st['tp']} fp={st['fp']}, {why}")
            self.phase = "repair:"
            new, fit = (self.refine(rule, rule["type"], [], without=rule["uid"])
                        if self.budget_left() else (None, None))
            self.phase = ""
            r = self.reg.rules[rule["uid"]]
            self.reg.retire_with(r, "tightened" if new is not None and new["regex"] != rule["regex"]
                                 else why)
            if new is not None and new["regex"] != rule["regex"]:
                self.accept(new, rule["type"], fit, born=f"round{self.state['round']}-repair")
            self.save()

    def accept(self, cand: dict, ntype: str, fit: dict, born: str) -> None:
        a = fit.get("alone", fit)
        prec = a["tp"] / (a["tp"] + a["fp"]) if a["tp"] + a["fp"] else 0.0
        r = self.reg.mint(cand["name"], ntype, cand["regex"], born,
                          spec={"flags": cand.get("flags", ""), "span": cand["span"]})
        r.spec["precision"] = round(prec, 4)
        r.spec["reasoning"] = cand.get("reasoning", "")
        r.status = STATUS_ACTIVE
        for pid, (tp, fp) in fit["per_rule"][-1]["papers"].items():
            self.reg.record(r.uid, pid, tp, fp)
        self.scorer.cache(self.as_rule(r), self.fit + self.val)
        print(f"    ACCEPTED uid {r.uid} {r.name}: precision {prec:.2f}, tp {a['tp']:g}"
              + (f", overall F {fit['gain'] * 100:+.3f} points" if "gain" in fit else ""))
        self.state["accepted"] = self.state.get("accepted", 0) + 1
        every = self.lim("snapshot_every")
        if every and self.state["accepted"] % every == 0:
            self.checkpoint(f"r{self.state['round']}_a{self.state['accepted']}")

    def cleanup(self) -> None:
        """Retire rules whose removal does not lower the objective on the fitting
        papers (overall F; overall recall with --accept fdr)."""
        rules = self.active()
        res = self.scorer.score(rules, self.fit)
        base, per = self.objective(res), res["per_rule"]
        for rule in sorted(rules, key=lambda r: per[r["uid"]]["tp"]):
            rest = [r for r in self.active() if r["uid"] != rule["uid"]]
            f = self.objective(self.scorer.score(rest, self.fit))
            if f >= base:
                self.reg.retire_with(self.reg.rules[rule["uid"]], f"redundant (F {base:.4f} -> {f:.4f})")
                base = f
                print(f"  [cleanup] retired uid {rule['uid']} {rule['name']}")

    def prepare_cluster(self, key, items):
        """A cluster's teacher request, built from the current state: its members
        the active rules do not find yet, its span option, positives and look-alikes."""
        covered = self.scorer.score(self.active(), self.fit)["found"]
        items = [(pid, n) for pid, n in items
                 if (pid, self.papers[pid].nodes.index(n)) not in covered]
        if len(items) < self.a.min_cluster:
            return None
        ntype = key[0]
        pos = [self.papers[pid].sent_text[n.first]
               for pid, n in spread(items, self.lim("max_examples"))]
        mn = str(self.a.max_negatives)
        k_neg = max(12, len(pos)) if mn == "auto" else (int(mn) or None)
        neg = [s for _, s in spread(self.lookalikes(ntype, key[1]), k_neg, seed=2)]
        return {"key": key, "tag": json.dumps(key), "items": items, "ntype": ntype,
                "span": best_span(self.papers, items), "prompt": propose_prompt(ntype, pos, neg)}

    def work(self, job: dict, rules: list) -> dict:
        """In a thread: propose a rule for the cluster and refine it, against
        `rules` (the active rules when the job started)."""
        self._tl.buf = [f"  cluster {job['key']} : {len(job['items'])} misses, span={job['span']}"]
        out = {"error": False, "cand": None}
        try:
            cand = self.charge("propose", ask, self.a.model, job["prompt"])
            if cand is not None:
                cand.update(type=job["ntype"], span=job["span"])
                out["cand"], _ = self.refine(cand, job["ntype"], job["items"], rules=rules)
        except TeacherError as e:
            self.call_failed(e)
            out["error"] = True
        except Exception as e:                                    # noqa: BLE001
            self.say(f"    [error] {type(e).__name__}: {e}")
            out["error"] = True
        out["log"], self._tl.buf = self._tl.buf, None
        return out

    def finish(self, job: dict, out: dict, rnd: int) -> None:
        """Back in the main thread: print the cluster's log; accept its rule if
        it still qualifies against the rules accepted while it was being refined."""
        for line in out["log"]:
            print(line)
        if out["error"]:
            return                                   # not tried: a resume asks again
        with self.lock:
            self.failures = 0
        self.state["tried"].append(job["tag"])
        cand, accepted = out["cand"], False
        if cand is not None:
            fit, val = self.evaluate(cand)
            if self.acceptable(fit, val):
                self.accept(cand, job["ntype"], fit, born=f"round{rnd}")
                accepted = True
            else:
                print(f"    not accepted: no longer qualifies with the rules accepted meanwhile "
                      f"(fit {self.counts(fit)})")
        self.log(round=rnd, cluster=job["tag"], size=len(job["items"]),
                 accepted=accepted, llm_calls=self.calls())
        self.save()

    def round(self) -> dict:
        self.state["round"] += 1
        rnd = self.state["round"]
        print(f"\n=== round {rnd}  ({len(self.reg.active())} active rules) ===")
        if rnd > 1:
            self.repair()
        miss = self.misses()
        cls = self.clusters(miss)
        print(f"  misses {len(miss)} in {len(cls)} cluster(s) of >= {self.a.min_cluster}")
        todo = iter([(k, v) for k, v in cls if json.dumps(k) not in self.state["tried"]])
        pending: deque = deque()
        with ThreadPoolExecutor(max(1, self.a.parallel)) as pool:
            def submit_next() -> bool:
                for key, items in todo:
                    if not self.budget_left():
                        return False
                    job = self.prepare_cluster(key, items)
                    if job is not None:       # a thread works on it against the rules as they are now
                        pending.append((job, pool.submit(self.work, job, self.active())))
                        return True
                return False
            while len(pending) < max(1, self.a.parallel) and submit_next():
                pass
            while pending:                    # finished in submission order: largest cluster first
                job, fut = pending.popleft()
                self.finish(job, fut.result(), rnd)
                while not self.stopped and len(pending) < max(1, self.a.parallel) and submit_next():
                    pass
        if not self.budget_left() and not self.stopped:
            print("  [budget] LLM-call budget reached")
        self.cleanup()
        fit, val = self.scorer.score(self.active(), self.fit), self.scorer.score(self.active(), self.val)
        out = {"round": rnd, "active": len(self.reg.active()),
               "fit": {k: round(fit[k], 4) for k in ("precision", "recall", "f1", "F", "R", "FDR")},
               "val": {k: round(val[k], 4) for k in ("precision", "recall", "f1", "F", "R", "FDR")},
               "fit_objective": round(self.objective(fit), 4),
               "val_objective": round(self.objective(val), 4),
               "llm_calls": self.calls(), "cost_usd": round(self.cost(), 4)}
        print(f"  round {rnd}: {out}")
        self.log(**out)
        self.checkpoint(f"r{rnd}_end")
        return out


# ---------------------------------------------------------------------------
# outputs in the merged algorithm's layout
# ---------------------------------------------------------------------------

def write_rules(dirpath: Path, rules: list) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "unit_rules.json").write_text(json.dumps({"rules": rules}, indent=1), encoding="utf-8")
    UR.write_importer(str(dirpath), SCORED)
    return dirpath


def prose_report(dist: UnitDistiller, pids, label: str) -> dict:
    res = dist.scorer.score(dist.active(), pids)
    n_nodes = sum(len(dist.papers[p].nodes) for p in pids)
    base = sum(n.base_covered for p in pids for n in dist.papers[p].nodes)
    out = {"split": label, "papers": len(pids), "prose_nodes": n_nodes,
           "found_by_base": base, "targets": res["targets"], "rules_tp": res["tp"],
           "rules_fp": res["fp"], "rules_precision": round(res["precision"], 4),
           "recall_of_targets": round(res["recall"], 4),
           "prose_recall_total": round((base + res["tp"]) / n_nodes, 4) if n_nodes else 0.0}
    print(f"  [{label}] {out}")
    return out


_PREP: dict = {}


def _prep_init(tex_dir, t2_dir, th, rules_dir, metric):
    _PREP.update(tex=Path(tex_dir), t2=Path(t2_dir), th=th, rules=str(rules_dir), metric=metric)


def _prep_one(pid):
    """One paper: its base parse (no distilled rules) and its training data."""
    buckets = C.parse_buckets(pid, _PREP["tex"], SCORED, _PREP["rules"])
    return pid, load_paper(pid, _PREP["tex"], _PREP["t2"], buckets, _PREP["th"], _PREP["metric"])


def load_papers(pids, args, eval_dir: Path) -> dict:
    """Training/test papers, with which silver nodes the base parser already
    finds; --prepare-workers processes at once."""
    import multiprocessing as mp
    empty = eval_dir / "snapshots" / "_empty_rules"              # no distilled rules at all
    empty.mkdir(parents=True, exist_ok=True)
    out = {}
    with mp.Pool(max(1, args.prepare_workers), initializer=_prep_init,
                 initargs=(args.tex_dir, args.t2_dir, args.threshold, str(empty),
                           args.train_metric)) as pool:
        for pid, p in pool.imap_unordered(_prep_one, pids):
            if p is None:
                print(f"  [skip] {pid}: no tex or no silver graph")
            else:
                out[pid] = p
    return out


def run(args) -> None:
    da.ensure_api_key()                 # fail now, not after preparing every paper
    eval_dir = Path(args.eval_dir)
    eval_dir.mkdir(parents=True, exist_ok=True)
    NSIM.set_match_metric(args.match_metric)
    splits = C.load_splits(C.split_file(args))
    pids = [p.strip() for p in args.pilot_papers.split(",") if p.strip()]
    if pids in (["train"], ["val"]):
        pids = sorted(p for p, s in splits.items() if s == pids[0])
    if str(args.val_papers).isdigit():
        rnd = random.Random(args.seed)
        shuffled = sorted(pids)
        rnd.shuffle(shuffled)
        n = int(args.val_papers)
        val, fit = sorted(shuffled[:n]), sorted(shuffled[n:])
    else:
        val = sorted(p for p, s in splits.items() if s == args.val_papers)
        fit = sorted(set(pids) - set(val))
        if not val:
            raise SystemExit(f"no papers of split {args.val_papers!r} in {C.split_file(args)}")
    if not args.allow_test_papers:
        C.assert_no_test_leak(fit + val, splits)
    print(f"[units] {len(fit)} fitting + {len(val)} validation papers; teacher {args.model}; "
          f"min precision {args.min_precision}; refine {args.max_refine} step(s) "
          f"({args.refine_moves}), judge {args.judge}; min cluster {args.min_cluster}; "
          f"budget {args.max_llm_calls} LLM calls")
    t0 = time.time()
    papers = load_papers(fit + val, args, eval_dir)
    prepare_seconds = round(time.time() - t0)
    fit = [p for p in fit if p in papers]
    val = [p for p in val if p in papers]
    tot = sum(len(p.nodes) for p in papers.values())
    tg = sum(not n.base_covered for p in papers.values() for n in p.nodes)
    print(f"[units] {tot} silver prose nodes, {tg} not found by the base parser "
          f"(prepared in {time.time() - t0:.0f}s)")

    dist = UnitDistiller(args, papers, fit, val, eval_dir)
    if not dist.state.get("snapshots"):
        dist.checkpoint("base")                         # step_001_base: no rules
    best, history = None, []
    while dist.state["round"] < args.rounds and dist.budget_left():
        out = dist.round()
        if dist.stopped:
            break
        history.append(out)
        v = out["val_objective"]
        if best is not None and v - best < args.stop_gain:
            print(f"[units] validation objective gain {v - best:+.4f} < {args.stop_gain}: stopping")
            break
        best = v if best is None else max(best, v)
    dist.save()
    write_rules(eval_dir, dist.active())                # the run's final rules

    reports = [prose_report(dist, fit, "fit"), prose_report(dist, val, "val")]
    params = {k: getattr(args, k) for k in ("min_precision", "min_tp", "fp_weight", "max_refine",
                                            "refine_moves", "judge", "judge_model", "val_tolerance",
                                            "val_min_fired", "min_cluster", "rounds", "val_papers",
                                            "max_llm_calls", "stop_gain", "seed", "threshold",
                                            "max_examples", "max_negatives", "max_refine_examples",
                                            "snapshot_every", "accept", "beta", "min_gain",
                                            "max_fdr", "fdr_scope", "rule_min_precision",
                                            "parallel", "effort", "thinking", "train_metric")}
    summary = {"algorithm": "units", "model": args.model, "params": params,
               "rounds": history, "reports": reports,
               "active_rules": dist.active(),
               "llm_calls": dist.calls(),
               "cost_usd": round(dist.cost(), 4),
               "usage_by_stage": {k: dict(v, cost_usd=round(da.estimate_cost(
                   v, args.judge_model or args.model if k.endswith("judge") else args.model), 4))
                   for k, v in sorted(dist.by_stage.items())},
               "prepare_seconds": prepare_seconds,
               "distill_seconds": dist.state.get("seconds", 0),
               "wall_seconds": round(time.time() - t0)}
    (eval_dir / "units_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    write_report(eval_dir, summary)
    print(f"[units] done: {len(dist.active())} active rules, {summary['llm_calls']} LLM calls, "
          f"${summary['cost_usd']}; summary in {eval_dir / 'units_summary.json'}")


def write_report(eval_dir: Path, s: dict) -> None:
    lines = [f"# Unit distillation: {eval_dir.name}", "",
             f"Teacher `{s['model']}`, {s['llm_calls']} LLM calls, "
             f"${s['cost_usd']}, {s['wall_seconds']} s.", "",
             "Parameters: " + ", ".join(f"{k}={v}" for k, v in s["params"].items()), "",
             "## Rounds", "", "| round | active rules | fit P / R / F1 | val P / R / F1 |",
             "|---|---|---|---|"]
    for r in s["rounds"]:
        f, v = r["fit"], r["val"]
        lines.append(f"| {r['round']} | {r['active']} | {f['precision']:.3f} / {f['recall']:.3f} / "
                     f"{f['f1']:.3f} | {v['precision']:.3f} / {v['recall']:.3f} / {v['f1']:.3f} |")
    lines += ["", "## Prose stratum", "",
              "| split | papers | prose nodes | found by base | rules TP | rules FP | rule precision | recall of the rest | prose recall |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in s["reports"]:
        lines.append(f"| {r['split']} | {r['papers']} | {r['prose_nodes']} | {r['found_by_base']} | "
                     f"{r['rules_tp']} | {r['rules_fp']} | {r['rules_precision']:.3f} | "
                     f"{r['recall_of_targets']:.3f} | {r['prose_recall_total']:.3f} |")
    lines += ["", "## Active rules", "", "| uid | type | span | precision | regex |", "|---|---|---|---|---|"]
    for r in s["active_rules"]:
        lines.append(f"| {r['uid']} | {r['type']} | {r['span']} | {r['precision']:.2f} | "
                     f"`{r['regex'][:80].replace('|', '¦')}` |")
    (eval_dir / "REPORT_units.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
