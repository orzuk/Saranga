#!/usr/bin/env python3
"""Sentence features of the alg3 tagger. One function, sentence_features(), serves
training and the parser, so a feature means the same thing in both.

A paper is the prepared document body the parser hands distilled rules (`text`),
its latex_facts (`fx`, offsets into text) and its prose sentences
(prose_units.sentences(fx)). Every feature is a deterministic string test on
the LaTeX of a sentence, its neighbours, its section or the whole paper:

  lexical    words and word pairs, the first one to three words, the last word
             (math, displays, references, citations and markup are tokens)
  markup     emphasis, bold, \\item, citation, reference, display, colon or
             question mark at the end, quotes, enumerators like (i)
  shape      length, number of formulas, share of math
  position   first/last in its paragraph, paragraph length, place in the paper
  section    words and kind of the section heading it sits under
  context    the opening words and markup of the previous and next sentence
  neighbours an environment (theorem, proof, algorithm, ...) just before or after
  document   whether a term this sentence emphasises is used again later
"""
from __future__ import annotations

import bisect
import re

FEATURES_VERSION = "alg3-f2"

# cue phrases, matched on the sentence's token string (gaps of a word allowed
# where marked); each match is one feature, so the learner weighs them
_CUES = [(name, re.compile(p)) for name, p in [
    ("def_called", r"\b(?:is|are) (?:\w+ )?(?:called|said to be|termed|known as|referred to as|named)\b"),
    ("def_we", r"\bwe (?:\w+ )?(?:say|call|define|write|denote|refer to|introduce)\b"),
    ("def_denote", r"\b(?:denote[sd]?|stands? for|abbreviat\w*)\b"),
    ("def_word", r"\b(?:defin\w*|notation|terminology)\b"),
    ("def_let_be", r"^(?:<\w+> )*let <math> (?:\w+ ){0,3}(?:be|denote)\b"),
    ("claim_derive", r"\b(?:we|one) (?:\w+ )?(?:get|obtain|have|find|see|deduce|conclude|derive|infer)\b"),
    ("claim_prove", r"\b(?:we|one) (?:\w+ )?(?:show|prove|claim|verify|check|establish)\b"),
    ("claim_easy", r"\bit (?:is|can be) (?:\w+ )?(?:easy|clear|known|well known|straightforward|"
                   r"obvious|seen|shown|checked|verified)\b"),
    ("claim_follows", r"\b(?:it follows|follows (?:from|that)|implies|yields|gives|"
                      r"hence|therefore|thus|consequently|in particular)\b"),
    ("claim_iff", r"\b(?:if and only if|iff|equivalent|necessary and sufficient)\b"),
    ("rem_note", r"\b(?:note|notice|observe|remark|mention|emphasi[sz]e|stress|point out)\b"),
    ("rem_worth", r"\bit is (?:\w+ )?(?:worth|important|interesting|natural|instructive)\b"),
    ("rem_aside", r"\b(?:in fact|of course|indeed|actually|alternatively|similarly|incidentally)\b"),
    ("ass_assume", r"\b(?:assum\w*|suppos\w*|throughout|from now on|without loss of generality|"
                   r"hypothes\w*|we restrict)\b"),
    ("q_question", r"\b(?:question|open|unknown|ask|whether|wonder|unclear|unresolved)\b"),
    ("q_mark", r"\?"),
    ("conj", r"\bconjectur\w*\b"),
    ("ex_example", r"\b(?:for (?:example|instance)|e g|example|consider|such as|illustrat\w*)\b"),
    ("alg_step", r"\b(?:step|input|output|repeat|until|iterat\w*|initiali[sz]\w*|for each|return|"
                 r"algorithm|procedure|update|compute)\b"),
    ("proof_word", r"\b(?:proof|we prove|to prove|to see (?:this|that)|by induction|suppose not|"
                   r"contradiction|it suffices|it remains)\b"),
    ("cite_result", r"(?:<cite>|<ref>).*\b(?:proved|showed|shown|established|obtained|proven|"
                    r"theorem|lemma|result)\b|\b(?:proved|showed|shown|established|proven) "
                    r"(?:\w+ )?(?:in|by) (?:\w+ )?<cite>"),
    ("problem_word", r"\b(?:problem|task|goal|aim|objective|we want|we seek|find a|determine)\b"),
]]

_DISPLAY = re.compile(r"\\begin\{(equation|align|gather|multline|eqnarray|displaymath|flalign)"
                      r"\*?\}.*?\\end\{\1\*?\}|\\\[.*?\\\]|\$\$.*?\$\$", re.S)
_INLINE = re.compile(r"\$[^$]*\$|\\\(.*?\\\)", re.S)
_REF = re.compile(r"\\(?:eq|c|C|auto|page|name|v|labelc)?ref\*?\s*\{[^{}]*\}")
_CITE = re.compile(r"\\cite[a-zA-Z]*\*?\s*(?:\[[^\]]*\]\s*)*\{[^{}]*\}")
_EMPH = re.compile(r"\\(?:emph|textit|textsl)\s*\{|\{\\(?:em|it|sl)\b")
_BOLD = re.compile(r"\\textbf\s*\{|\{\\bf\b|\\bf\b")
_EMPH_TERM = re.compile(r"\\(?:emph|textit|textsl|textbf)\s*\{([^{}$]{2,60})\}|\{\\(?:em|it|bf)\s+([^{}$]{2,60})\}")
_CMD = re.compile(r"\\[a-zA-Z]+\*?")
_WORD = re.compile(r"[a-z]+|<[a-z]+>|[:?;]")
_ENUM = re.compile(r"^\s*(?:\\item\s*)?(?:\(\s*(?:[ivx]+|[a-z]|\d+)\s*\)|(?:[ivx]+|\d+)\s*[.)])")

_SEC_KINDS = [
    ("intro", r"introduc|overview|motivat"),
    ("prelim", r"preliminar|background|notation|setup|setting|framework|basic|definition|"
               r"terminolog|convention|review"),
    ("main", r"main|result|theorem|statement"),
    ("proof", r"proof|lemma"),
    ("example", r"example|application|illustrat|case"),
    ("open", r"open|question|problem|conjectur|future|further|outlook"),
    ("conclusion", r"conclu|discussion|summary|final|remark"),
    ("algorithm", r"algorithm|method|procedure|implement|numeric|experiment|simulat|comput"),
    ("model", r"model|assumption|formulation"),
    ("appendix", r"appendix"),
]
_SEC_RE = [(k, re.compile(p)) for k, p in _SEC_KINDS]

# Clues invented by the teacher (alg3/invent.py): regexes on a sentence's LaTeX,
# each one more feature for the learner to weigh. Matched with the `regex`
# package and a per-sentence timeout where it is installed, so a pathological
# pattern costs at most that and never hangs a run.
try:
    import regex as _rx_engine
except ImportError:                                          # pragma: no cover
    _rx_engine = None
_CLUES: list = []
CLUE_TIMEOUT = 0.2


def set_clues(clues: list) -> None:
    """clues: [{"name", "regex", "flags"}] (bad patterns are skipped)."""
    out = []
    for c in clues:
        flags = 0
        for ch in str(c.get("flags", "")):
            flags |= {"i": re.I, "s": re.S, "m": re.M}.get(ch, 0)
        try:
            pat = (_rx_engine or re).compile(c["regex"], flags)
        except Exception:                                    # noqa: BLE001
            continue
        out.append((c["name"], pat))
    _CLUES[:] = out


def _clue_fires(pat, s: str) -> bool:
    try:
        if _rx_engine is not None:
            return pat.search(s, timeout=CLUE_TIMEOUT) is not None
        return pat.search(s) is not None
    except Exception:                                        # noqa: BLE001  (timeout too)
        return False
_STOP = set("the a an of and in on for to with by from at as is are be its their this that "
            "some our".split())


def tokens(s: str) -> list[str]:
    """Lowercased words of a sentence's LaTeX, with markup turned into tokens."""
    s = _DISPLAY.sub(" <display> ", s)
    s = _INLINE.sub(" <math> ", s)
    s = _REF.sub(" <ref> ", s)
    s = _CITE.sub(" <cite> ", s)
    s = _EMPH.sub(" <emph> ", s)
    s = _BOLD.sub(" <bold> ", s)
    s = re.sub(r"\\item\b", " <item> ", s)
    s = re.sub(r"``|''|\"", " <quote> ", s)
    s = _CMD.sub(" ", s)
    return _WORD.findall(s.lower())


def _bucket(x: float, cuts) -> int:
    return bisect.bisect_right(cuts, x)


class PaperView:
    """What sentence_features needs of one paper, computed once."""

    def __init__(self, text: str, fx: dict, sents: list):
        self.text, self.fx, self.sents = text, fx, sents
        self.raw = [text[s.start:s.end] for s in sents]
        self.toks = [tokens(r) for r in self.raw]
        self.secs = sorted((int(s["start"]), s.get("title") or "") for s in fx.get("sections", []))
        self.sec_starts = [a for a, _ in self.secs]
        envs = [(int(f["outer_start"]), int(f["outer_end"]), f.get("type") or f["kind"])
                for f in fx.get("facts", []) if f["kind"] != "equation"]
        self.env_ends = sorted((b, t) for _, b, t in envs)
        self.env_starts = sorted((a, t) for a, _, t in envs)
        self.para_len, self.para_pos = {}, []
        for i, s in enumerate(sents):
            key = (s.region, s.para)
            self.para_pos.append(self.para_len.get(key, 0))
            self.para_len[key] = self.para_len.get(key, 0) + 1
        low = text.lower()
        self.low = low

    def section(self, pos: int) -> str:
        k = bisect.bisect_right(self.sec_starts, pos) - 1
        return self.secs[k][1] if k >= 0 else ""

    def env_before(self, pos: int):
        """Type of an environment ending just before `pos` (only whitespace between)."""
        k = bisect.bisect_right(self.env_ends, (pos, "~")) - 1
        if k >= 0:
            b, t = self.env_ends[k]
            if not self.text[b:pos].strip():
                return t
        return None

    def env_after(self, pos: int):
        k = bisect.bisect_left(self.env_starts, (pos, ""))
        if k < len(self.env_starts):
            a, t = self.env_starts[k]
            if not self.text[pos:a].strip():
                return t
        return None


def _opening(toks, prefix: str, out: dict, n: int = 2) -> None:
    for k in range(1, n + 1):
        if len(toks) >= k:
            out[f"{prefix}{k}=" + "_".join(toks[:k])] = 1.0
    if not toks:
        out[f"{prefix}empty"] = 1.0


def sentence_features(pv: PaperView, i: int) -> dict:
    s, raw, toks = pv.sents[i], pv.raw[i], pv.toks[i]
    f: dict = {"bias": 1.0}
    # lexical
    for t in set(toks):
        f["w=" + t] = 1.0
    for a, b in set(zip(toks, toks[1:])):
        f["b=" + a + "_" + b] = 1.0
    for k in (1, 2, 3):
        if len(toks) >= k:
            f[f"f{k}=" + "_".join(toks[:k])] = 1.0
    if toks:
        f["last=" + toks[-1]] = 1.0
    joined = " ".join(toks)
    cues = [name for name, rx in _CUES if rx.search(joined)]
    for name in cues:
        f["cue=" + name] = 1.0
    for name, pat in _CLUES:
        if _clue_fires(pat, raw):
            f["llm=" + name] = 1.0
    # markup and shape
    r = raw.strip()
    if _EMPH.search(raw):
        f["m:emph"] = 1.0
    if _BOLD.search(raw):
        f["m:bold"] = 1.0
    if re.match(r"(?:\\noindent\s*)?(?:\\textbf\s*\{|\{\\bf\b|\\paragraph\b)", r):
        f["m:bold_lead"] = 1.0
    if r.startswith("\\item"):
        f["m:item"] = 1.0
    if _ENUM.match(r):
        f["m:enum"] = 1.0
    if r.endswith(":") or re.search(r":\s*(?:\\\[|\\begin\{(?:equation|align|enumerate|itemize))", r):
        f["m:colon"] = 1.0
    if r.endswith("?") or "?" in r[-4:]:
        f["m:question"] = 1.0
    if _CITE.search(raw):
        f["m:cite"] = 1.0
    if _REF.search(raw):
        f["m:ref"] = 1.0
    if _DISPLAY.search(raw):
        f["m:display"] = 1.0
    n_math = len(_INLINE.findall(raw))
    f[f"s:nmath{_bucket(n_math, (1, 2, 4, 8))}"] = 1.0
    words = sum(1 for t in toks if not t.startswith("<"))
    f[f"s:len{_bucket(words, (6, 12, 20, 35, 60))}"] = 1.0
    mchars = sum(len(m.group(0)) for m in _INLINE.finditer(raw)) + \
        sum(len(m.group(0)) for m in _DISPLAY.finditer(raw))
    f[f"s:mfrac{_bucket(mchars / max(len(raw), 1), (0.1, 0.3, 0.6))}"] = 1.0
    # position
    plen = pv.para_len[(s.region, s.para)]
    ppos = pv.para_pos[i]
    if ppos == 0:
        f["p:first"] = 1.0
    if ppos == plen - 1:
        f["p:last"] = 1.0
    f[f"p:plen{_bucket(plen, (1, 2, 4, 8))}"] = 1.0
    f[f"p:doc{min(9, int(10 * i / max(len(pv.sents), 1)))}"] = 1.0
    if i == 0 or pv.sents[i - 1].region != s.region:
        f["p:region_start"] = 1.0
    # section
    title = pv.section(s.start).lower()
    if not title:
        f["sec:none"] = 1.0
    for k, rx in _SEC_RE:
        if rx.search(title):
            f["seck=" + k] = 1.0
    for w in set(re.findall(r"[a-z]{3,}", title)) - _STOP:
        f["secw=" + w] = 1.0
    # context
    same_prev = i > 0 and pv.sents[i - 1].region == s.region
    same_next = i + 1 < len(pv.sents) and pv.sents[i + 1].region == s.region
    if same_prev:
        _opening(pv.toks[i - 1], "prev", f)
        pr = pv.raw[i - 1].rstrip()
        if pr.endswith(":"):
            f["prev:colon"] = 1.0
        if _EMPH.search(pv.raw[i - 1]):
            f["prev:emph"] = 1.0
    else:
        f["prev:none"] = 1.0
    if same_next:
        _opening(pv.toks[i + 1], "next", f, 1)
        if _DISPLAY.search(pv.raw[i + 1][:40]):
            f["next:display"] = 1.0
    else:
        f["next:none"] = 1.0
    # neighbouring environments
    eb = pv.env_before(s.start)
    if eb:
        f["env_before=" + eb] = 1.0
    ea = pv.env_after(s.end)
    if ea:
        f["env_after=" + ea] = 1.0
    # document: an emphasised term used again later
    reuse = 0
    for m in _EMPH_TERM.finditer(raw):
        term = (m.group(1) or m.group(2) or "").strip().lower()
        term = re.sub(r"\s+", " ", term)
        if len(term) >= 3:
            reuse = max(reuse, pv.low.count(term, s.end))
    if _EMPH_TERM.search(raw):
        f[f"d:reuse{_bucket(reuse, (1, 2, 5))}"] = 1.0
    # a few conjunctions a linear model cannot form by itself
    kinds = [k for k, rx in _SEC_RE if rx.search(title)] or ["none"]
    f1 = toks[0] if toks else ""
    for k in kinds:
        f[f"x:f1={f1}|sec={k}"] = 1.0
        for name in cues:
            f[f"x:cue={name}|sec={k}"] = 1.0
    if "m:emph" in f:
        f[f"x:emph|f1={f1}"] = 1.0
        for name in cues:
            f[f"x:emph|cue={name}"] = 1.0
    if eb:
        f[f"x:env_before={eb}|f1={f1}"] = 1.0
    return f


def context_features(probs: list, i: int, sents: list, classes: list) -> dict:
    """Second pass: the first-pass type probabilities of this sentence and its
    neighbours in the same region, bucketed (a sentence after two definitions,
    a claim after a 'we get' sentence, the steps of an algorithm)."""
    f = {}
    cuts = (0.1, 0.25, 0.5, 0.75)
    for off, tag_ in ((-2, "p2"), (-1, "p1"), (0, "s"), (1, "n1")):
        j = i + off
        if j < 0 or j >= len(sents) or sents[j].region != sents[i].region:
            f[f"ctx:{tag_}:none"] = 1.0
            continue
        for c, p in zip(classes, probs[j]):
            if c == "none":
                continue
            b = _bucket(p, cuts)
            if b:
                f[f"ctx:{tag_}:{c}:{b}"] = 1.0
    return f


def span_features(pv: PaperView, i: int, ntype: str) -> dict:
    """Features for choosing how far a node anchored at sentence i extends."""
    s = pv.sents[i]
    f = {"bias": 1.0, "type=" + ntype: 1.0}
    rem = 0
    j = i + 1
    while j < len(pv.sents) and pv.sents[j].region == s.region and pv.sents[j].para == s.para:
        rem += 1
        j += 1
    f[f"rem{min(rem, 6)}"] = 1.0
    f[f"type_rem={ntype}_{min(rem, 4)}"] = 1.0
    toks = pv.toks[i]
    _opening(toks, "a", f, 2)
    if pv.raw[i].rstrip().endswith(":"):
        f["a:colon"] = 1.0
    if i + 1 < len(pv.sents) and pv.sents[i + 1].region == s.region:
        _opening(pv.toks[i + 1], "n", f, 1)
        if pv.sents[i + 1].para != s.para:
            f["n:newpara"] = 1.0
    words = sum(1 for t in toks if not t.startswith("<"))
    f[f"len{_bucket(words, (6, 12, 20, 35))}"] = 1.0
    return f
