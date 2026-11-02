"""The Open Logic Project's LaTeX as one plain LaTeX file per chapter, for the v7-books extractor:
the same OUT as prepare_book (chNN.tex, labels.json, chapters.json).

    python -m structured_math.books.openlogic_to_latex OLP_ROOT OUT --book slc [--book-dir DIR]
    python -m structured_math.books.openlogic_to_latex OLP_ROOT OUT --parts set-theory computability \\
        [--skip-dup OTHER_OUT] [--labels-from OTHER_OUT]

--book NAME follows the driver NAME.tex (in --book-dir, default: a folder next to OLP_ROOT holding
it) with NAME-config.sty and NAME-envs.sty; --parts takes whole parts content/<part>/<part>.tex,
each chapter its own file, with the complete build's configuration. TeX is not run: \\olimport is
inlined (the subfile wrappers dropped), \\ollabel / \\olref become \\label / \\cref with the key OLP
resolves from the current \\olfileid, !!{token} becomes its word, !A its letter, \\iftag and
\\tagitem take the branch the configuration's tags select, problems go to the end of their chapter
(after the book's chapter summary, if any), and the configuration's macros and theorem
environments go to the preamble. --skip-dup leaves out a chapter whose files another prepared
book already has; --labels-from counts that book's labels as defined for \\oliflabeldef.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from latex_facts import extract_facts, read_tex          # noqa: E402
from latex_macros import group, strip_comments          # noqa: E402

GREEK = {"greek": "A/\\varphi,B/\\psi,C/\\chi,D/\\theta,E/\\alpha,F/\\beta,G/\\gamma,H/\\delta,K/\\xi,"
                  "L/\\zeta,O/\\omega,R/\\rho,S/\\sigma,T/\\tau",          # sty/open-logic-formulas.sty
         "alphagreek": "A/\\alpha,B/\\beta,C/\\gamma,D/\\delta,E/\\phi,F/\\psi,G/\\chi,H/\\theta,K/\\xi,"
                       "L/\\zeta,O/\\omega,R/\\rho,S/\\sigma,T/\\tau", "latin": ""}
_DEF = re.compile(r"\\(settexttoken|tagtrue|tagfalse|ollatinformulas|olgreekformulas|olalphagreekformulas"
                  r"|DeclareDocumentMacro|DeclareDocumentCommand|(?:re|provide)?newcommand\*?|DeclareMathOperator\*?"
                  r"|let|def)(?![A-Za-z@])")
_OL = re.compile(r"\\(olimport|olfileid|olchapterid|olpartid|ollabel|olref|Olref|olsection|olchapter|olpart"
                 r"|input|subfile)(?![A-Za-z@])")
_SPEC = {"olimport": "somo", "olfileid": "mmm", "olchapterid": "mm", "olpartid": "m", "ollabel": "m",
         "olref": "ooom", "Olref": "ooom", "olsection": "om", "olchapter": "ommm", "olpart": "omm", "input": "m",
         "subfile": "m"}
_DRIVER_KEEP = re.compile(r"\\chapter\*?\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}|\\appendix(?![A-Za-z])|\\bibliography\{")
_CHAPTER = re.compile(r"\\chapter\*?\s*(?:\[[^\]]*\])?\s*\{")
_PROB = re.compile(r"\\begin\{prob\}.*?\\end\{prob\}", re.S)
_TOKEN = re.compile(r"!!\s*(\^)?\s*(a)?\s*\{([^{}]*)\}(s)?")   # xparse: t^ and ta skip spaces, !ts not


def _read(f: Path) -> str:
    return strip_comments(f.read_text(encoding="utf-8", errors="replace"))


def _args(s: str, i: int, spec: str):
    """The arguments after a command name ending at i, by xparse letters (s star, o optional,
    m mandatory, t mandatory but maybe one unbraced token), and the index after them; (None, i) when a mandatory one is missing."""
    out = []
    for c in spec:
        if c == "s":
            out.append(s.startswith("*", i))
            i += out[-1]
        else:
            g, j = group(s, i, *("[]" if c == "o" else "{}"))
            if g is None and c == "t" and re.compile(r"[ \t]*\n[ \t]*\n").match(s, i):
                g, j = "\\par", i                               # a blank line is the token \par
            elif g is None and c == "t":                        # an unbraced argument: one token
                m = re.compile(r"\s*(\\[A-Za-z@]+|\\.|[^\s{}])").match(s, i)
                g, j = (m.group(1), m.end()) if m else (None, i)
            if g is None and c in "mt":
                return None, i
            out.append(g)
            i = j
    return out, i


def _sub_cmd(s: str, name: str, spec: str, fn) -> str:
    """Every \\name with its arguments replaced by fn(*args); a replacement is scanned again."""
    pat, i = re.compile(r"\\%s(?![A-Za-z@])" % name), 0
    while m := pat.search(s, i):
        a, j = _args(s, m.end(), spec)
        if a is None:
            i = m.end()
            continue
        s, i = s[:m.start()] + fn(*a) + s[j:], m.start()
    return s


def _sub_env(s: str, env: str, nargs: int, fn) -> str:
    """Every \\begin{env}{args}...\\end{env} replaced by fn(args, body)."""
    b, e = "\\begin{%s}" % env, "\\end{%s}" % env
    i = 0
    while (k := s.find(b, i)) >= 0:
        a, j = _args(s, k + len(b), "m" * nargs)
        if a is None:
            i = k + 1
            continue
        depth, p = 1, j
        while depth:
            nb, ne = s.find(b, p), s.find(e, p)
            if ne < 0:
                return s
            depth, p = (depth + 1, nb + len(b)) if 0 <= nb < ne else (depth - 1, ne + len(e))
        s, i = s[:k] + fn(a, s[j:p - len(e)]) + s[p:], k
    return s


_XDEF = re.compile(r"\\(?:DeclareDocumentCommand|NewDocumentCommand|RenewDocumentCommand)\s*\{?\\([A-Za-z]+)\}?")
_IF = re.compile(r"\\If(NoValue|Value|Boolean)(TF|T|F)(?![A-Za-z@])")


def _xspec(spec: str) -> list[tuple]:
    """xparse argument letters as [(kind, open, close, default)]: s, t<token>, o, O{d}, m, d<oc>, r<oc>."""
    out, i = [], 0
    while i < len(spec):
        c = spec[i]
        if c in " \t\n":
            i += 1
        elif c == "t":
            tok, j = group(spec, i + 1)
            tok, i = (tok, j) if tok is not None else (spec[i + 1], i + 2)
            out.append(("t", tok, None, None))
        elif c == "O":
            d, i = group(spec, i + 1)
            out.append(("o", "[", "]", d))
        elif c in "dr":
            out.append(("o" if c == "d" else "m", spec[i + 1], spec[i + 2], None))
            i += 3
        else:
            out.append({"s": ("t", "*", None, None), "o": ("o", "[", "]", None)}.get(c, ("m", "{", "}", None)))
            i += 1
    return out


def xparse_macros(pre: str) -> dict:
    """{name: (argument spec, body)} of the preamble's \\DeclareDocumentCommand macros."""
    out = {}
    for m in _XDEF.finditer(pre):
        spec, j = group(pre, m.end())
        body, _ = group(pre, j) if spec is not None else (None, j)
        if body is not None:
            out[m.group(1)] = (_xspec(spec), body)
    return out


def _branch(s: str, i: int):
    """A conditional's branch: a group, or one token."""
    g, j = group(s, i)
    if g is not None:
        return g, j
    m = re.compile(r"\s*(\\[A-Za-z@]+|\\.|[^\s{}])").match(s, i)
    return (m.group(1), m.end()) if m else ("", i)


def _ifs(body: str, vals: list) -> str:
    """\\IfNoValueTF{#k}{..}{..} and its kin decided by the call's arguments."""
    i = 0
    while m := _IF.search(body, i):
        a, j = _branch(body, m.end())
        k = re.fullmatch(r"\s*#(\d)\s*", a)
        if not k:
            i = m.end()
            continue
        v = vals[int(k.group(1)) - 1]
        yes = {"NoValue": v is None, "Value": v is not None, "Boolean": v is True}[m.group(1)]
        t, j = _branch(body, j) if "T" in m.group(2) else ("", j)
        f, j = _branch(body, j) if "F" in m.group(2) else ("", j)
        body, i = body[:m.start()] + (t if yes else f) + body[j:], m.start()
    return body


def _call(s: str, i: int, spec: list):
    """The values of a call's arguments after s[i] (True/False for flags, None for an absent optional), and the end."""
    vals = []
    for kind, o, c, d in spec:
        if kind == "t":
            m = re.compile(r"\s*" + re.escape(o)).match(s, i)
            vals.append(bool(m))
            i = m.end() if m else i
            continue
        g, j = group(s, i, o, c)
        if g is None and kind == "m" and o == "{":
            m = re.compile(r"\s*(\\[A-Za-z@]+|\\.|[^\s{}])").match(s, i)
            g, j = (m.group(1), m.end()) if m else (None, i)
        if g is None and kind == "m":
            return None, i
        vals.append(g if g is not None else d)
        i = j
    return vals, i


def expand_xparse(text: str, macros: dict, passes: int = 8) -> str:
    """The book's xparse macros (optional and flag arguments, which MathJax cannot read) expanded
    in text; the plain \\newcommand macros stay, as in papers (metadata.macros)."""
    if not macros:
        return text
    pat = re.compile(r"\\(%s)(?![A-Za-z@])" % "|".join(sorted(macros, key=len, reverse=True)))
    for _ in range(passes):
        out, i, changed = [], 0, False
        while m := pat.search(text, i):
            spec, body = macros[m.group(1)]
            vals, j = _call(text, m.end(), spec)
            if vals is None:
                out.append(text[i:m.end()])
                i = m.end()
                continue
            x = _ifs(body, vals)
            x = re.sub(r"#(\d)", lambda k: "" if not isinstance(v := vals[int(k.group(1)) - 1], str) else v, x)
            x = re.sub(r"\\relax(?![A-Za-z@])", "", x)
            out.append(text[i:m.start()] + " " + re.sub(r"\s+", " ", x).strip() + " ")
            i, changed = j, True
        text = "".join(out) + text[i:]
        if not changed:
            break
    return text


def _name(s: str, i: int):
    g, j = group(s, i)
    if g is not None:
        return g.strip(), j
    m = re.compile(r"\s*(\\[A-Za-z@]+)").match(s, i)
    return (m.group(1), m.end()) if m else (None, i)


class Config:
    """Tokens, tags, formula letters, macros and theorem environments of one build."""

    def __init__(self):
        self.tokens, self.tags, self.formulas, self.macros = {}, {}, "greek", {}
        self.theorems, self.excluded, self.envs = [], set(), {}

    def read(self, text: str):
        """Read a configuration file, in load order (later definitions win)."""
        i = 0
        while m := _DEF.search(text, i):
            cmd, i = m.group(1), m.end()
            if cmd == "settexttoken":
                (key, star, s, p, S, P), i = _args(text, i, "msmmoo")
                if key is not None:
                    up = lambda w: w[:1].upper() + w[1:]          # noqa: E731
                    self.tokens[key] = {"s": s, "p": p, "S": S or up(s), "P": P or up(p),
                                        "a": "an" if star else "a", "A": "An" if star else "A"}
            elif cmd in ("tagtrue", "tagfalse"):
                (tags,), i = _args(text, i, "m")
                for t in tags.split(","):
                    self.tags[t.strip()], self.tags["not" + t.strip()] = cmd == "tagtrue", cmd != "tagtrue"
            elif cmd.endswith("formulas"):
                self.formulas = cmd[2:-8]
            else:
                i = self._macro(text, m.start(), cmd, i)

    def _macro(self, text: str, a: int, cmd: str, i: int) -> int:
        name, i = _name(text, i)
        if not name:
            return i
        if name == "\\indcase":                                   # expanded in the text (OLP._indcase)
            self.macros.pop(name, None)
        if cmd == "let":
            m = re.compile(r"\s*=?\s*(\\[A-Za-z@]+)").match(text, i)
            if m and "@" not in name and not name.startswith("\\old"):
                self.macros[name] = f"\\let{name}{m.group(1)}"
            return m.end() if m else i
        if cmd == "def":
            m = re.compile(r"(?:#\d)*").match(text, i)
            body, j = group(text, m.end())
            if body is not None and "@" not in name:
                self.macros[name] = text[a:j]
            return j
        spec = ""
        if cmd == "DeclareDocumentCommand":
            spec, i = group(text, i)
            spec = re.sub(r"\s+", "", spec or "")
        elif cmd.endswith("command") or cmd.endswith("command*"):
            for _ in range(2):                                   # [n][default]
                o, j = group(text, i, "[", "]")
                if o is None:
                    break
                i = j
        body, j = group(text, i)
        if body is None:
            return i
        if name == "\\indcase":
            pass
        elif cmd == "DeclareDocumentMacro":
            self.macros[name] = "\\newcommand{%s}{%s}" % (name, body)
        elif cmd == "DeclareDocumentCommand" and set(spec) <= {"m"}:
            n = len(spec)
            self.macros[name] = "\\newcommand{%s}%s{%s}" % (name, f"[{n}]" if n else "", body)
        elif cmd == "DeclareDocumentCommand":
            self.macros[name] = "\\DeclareDocumentCommand{%s}{%s}{%s}" % (name, spec, body)
        else:
            self.macros[name] = text[a:j]
        return j

    def read_envs(self, text: str):
        """Theorem environments (\\declaretheorem), excluded and wrapper environments."""
        for m in re.finditer(r"\\declaretheorem\s*(?:\[((?:[^\[\]{}]|\{[^{}]*\})*)\])?\s*\{([^}]*)\}", text):
            o, env = m.group(1) or "", m.group(2).strip()
            get = lambda k: (re.search(k + r"\s*=\s*\{?([^,}\]]+)", o) or [None, None])[1]   # noqa: E731
            name, sib, within = get("name"), get("sibling"), get("numberwithin")
            if "unnumbered" in o or "numbered=no" in o.replace(" ", ""):
                line = "\\newtheorem*{%s}{%s}" % (env, name)
            else:
                line = "\\newtheorem{%s}%s{%s}%s" % (env, f"[{sib.strip()}]" if sib else "", name,
                                                   f"[{within.strip()}]" if within else "")
            self.theorems = [t for t in self.theorems if not t.startswith(f"\\newtheorem{{{env}}}")
                             and not t.startswith(f"\\newtheorem*{{{env}}}")] + [line]
        for m in re.finditer(r"\\(exclude|include)env\{([^}]*)\}", text):
            (self.excluded.add if m.group(1) == "exclude" else self.excluded.discard)(m.group(2))
        for m in re.finditer(r"\\newenvironment\{(\w+)\}", text):
            a, _ = _args(text, m.end(), "omm")
            if a is not None and a[0] is None:
                beg, end = a[1:]
                self.envs[m.group(1)] = (beg.strip(), end.strip())

    def on(self, tags: str) -> bool:
        return any(self.tags.get(t.strip(), False) for t in tags.split(","))

    def preamble(self) -> str:
        fl = dict(x.split("/") for x in GREEK[self.formulas].split(",") if x)
        macros = "\n".join(re.sub(r"(?<![!\\])!([A-Z])", lambda m: fl.get(m.group(1), m.group(1)), v)
                           for v in self.macros.values())
        macros = re.sub(r"\\old(phi|epsilon)(?![A-Za-z])", r"\\\1", macros)
        return ("\\documentclass{book}\n\\usepackage{amsmath,amssymb,amsthm}\n\n"
                "% Open Logic Project theorem environments\n" + "\n".join(self.theorems) +
                "\n\n% Open Logic Project macros (open-logic-config.sty and the book's config)\n" + macros + "\n")


class OLP:
    """One build: the OLP content folder, a configuration, and every file it reads."""

    def __init__(self, root: Path, cfg: Config):
        self.root, self.cfg, self.files, self.chapter_dirs = root, cfg, [], {}

    # ── 1. includes and hierarchical labels, file by file ─────────────────────
    def inline(self, path: Path, ids=("udf", "udf", "udf"), sec="section", driver=False) -> str:
        s = _read(path)
        if not driver and (a := s.find("\\begin{document}")) >= 0:          # a subfile's own text
            b = s.find("\\end{document}", a)
            s = s[a + len("\\begin{document}"): b if b >= 0 else None]
        s = self.select(s)
        self.files.append(str(path.relative_to(self.root) if path.is_relative_to(self.root) else path))
        ids, out, i = list(ids), [], 0
        keep = (lambda t: "\n".join(_DRIVER_KEEP.findall(t)) + "\n") if driver else (lambda t: t)
        while m := _OL.search(s, i):
            a, j = _args(s, m.end(), _SPEC[m.group(1)])
            out.append(keep(s[i:m.start()]))
            if a is None:
                out.append(m.group(0))
                i = m.end()
                continue
            out.append(self._ol(m.group(1), a, ids, sec, path))
            i = j
        out.append(keep(s[i:]))
        return "".join(out)

    def _ol(self, cmd: str, a: list, ids: list, sec: str, here: Path) -> str:
        if cmd == "olimport":
            star, d, f, cs = a
            olp = lambda x: x.replace("\\olpath", str(self.root.parent)).strip()   # noqa: E731
            base = (self.root if star else here.parent) if d is not None else here.parent
            p = base / olp(d or "") / olp(f)
            p = p if p.suffix == ".tex" else p.with_name(p.name + ".tex")
            if not p.is_file():
                print("missing:", p, file=sys.stderr)
                return ""
            return self.inline(p, ids, cs or "section")
        if cmd == "subfile":                                        # a rules table, next to the file
            return self._ol("olimport", [False, None, a[0], None], ids, sec, here)
        if cmd == "input":                                          # the driver's front matter, summaries
            return ""
        if cmd in ("olfileid", "olchapterid", "olpartid"):
            ids[:len(a)] = [x.strip() for x in a]
            return ""
        if cmd == "ollabel":
            return "\\label{%s}" % ":".join(ids + [a[0].strip()])
        if cmd in ("olref", "Olref"):
            p, c, s_, x = [y.strip() if y is not None else None for y in a]
            pre = ids if p is None else [ids[0], ids[1], p] if c is None else [ids[0], p, c] if s_ is None \
                else [p, c, s_]
            return "\\%s{%s}" % ("cref" if cmd == "olref" else "Cref", ":".join(pre + [x]))
        if cmd == "olsection":
            short, title = a
            lab = "\\label{%s}" % ":".join(ids + ["sec"])
            if sec == "nosection":
                return lab
            return "\\%s%s{%s}%s" % (sec, f"[{short}]" if short else "", title, lab)
        if cmd == "olchapter":
            alt, p, c, title = a
            self.chapter_dirs[(p.strip(), c.strip())] = str(here.parent.relative_to(self.root)) + "/"
            return "\\chapter%s{%s}\\label{%s:%s::chap}" % (f"[{alt}]" if alt else "", title, p.strip(), c.strip())
        return ""                                                   # \olpart: the part heading is dropped

    def select(self, s: str) -> str:
        """The text the build's tags select (per file: \\iftag can choose an \\olfileid)."""
        cfg = self.cfg
        s = _sub_env(s, "tagblock", 1, lambda a, body: body if cfg.on(a[0]) else "")
        s = _sub_env(s, "tagenumerate", 1, self._tagenumerate)
        s = re.sub(r"\\tagprob(?![A-Za-z])(.*?)\\tagendprob(?![A-Za-z])", self._tagprob, s, flags=re.S)
        s = _sub_cmd(s, "iftag", "mmt", lambda t, y, n: y if cfg.on(t) else n)
        s = _sub_cmd(s, "tagitem", "mmt", lambda t, y, n: (f"\\item {y}" if y.strip() else "") if cfg.on(t)
                     else (f"\\item {n}" if n.strip() else ""))
        s = _sub_cmd(s, "tagrefs", "m", lambda x: self._tagrefs(x))
        s = s.replace("\\startycommalist", "\\YCOMMAFIRST")      # \ycomma: nothing the first time, then ", "
        return re.sub(r"\\YCOMMAFIRST(.*?)\\ycomma(?![A-Za-z])|\\ycomma(?![A-Za-z])",
                      lambda m: m.group(1) if m.group(1) is not None else ",", s, flags=re.S)

    # ── 2. the build's words, on assembled text ────────────────────────────────
    def convert(self, s: str) -> str:
        cfg = self.cfg
        for env in cfg.excluded:
            s = re.sub(r"\\begin\{%s\}.*?\\end\{%s\}" % (env, env), "", s, flags=re.S)
        s = _TOKEN.sub(self._token, s)
        tok = lambda f, k: cfg.tokens.get(k.strip(), {}).get(f.strip(), k.strip())     # noqa: E731
        s = _sub_cmd(s, "(?:usetoken|printtoken)", "mm", tok)
        s = _sub_cmd(s, "article", "m", lambda k: tok("a", k))
        s = _sub_cmd(s, "Article", "m", lambda k: tok("A", k))
        s = re.sub(r"\\old(phi|epsilon)(?![A-Za-z])", r"\\\1", s)        # \let\oldphi\phi before \let\phi\varphi
        fl = dict(x.split("/") for x in GREEK[cfg.formulas].split(",") if x)
        s = re.sub(r"(?<![!\\])!([A-Z])([A-Za-z]?)",
                   lambda m: fl.get(m.group(1), m.group(1)) + (" " if m.group(2) and m.group(1) in fl else "")
                   + m.group(2), s)
        s = _sub_cmd(s, "formula", "m", lambda x: fl.get(x.strip(), x.strip()))
        s = re.sub(r"\\indcase(?![A-Za-z])\s*(\*?)\s*(!?)", r"\\indcase{\1}{\2}", s)
        s = _sub_cmd(s, "indcase", "mmmmm", self._indcase)
        s = re.sub(r"\\(begin|end)\{probtag\}(\{[^{}]*\})?", r"\\\1{prob}", s)
        for env, (beg, end) in cfg.envs.items():
            if env in ("probtag",) or env in cfg.excluded:
                continue
            if not beg and not end:
                s = re.sub(r"\\(?:begin|end)\{%s\}" % env, "", s)
            elif re.fullmatch(r"\\paragraph\{[^{}]*\}\\par", beg) and not end:
                s = s.replace("\\begin{%s}" % env, beg[:-4]).replace("\\end{%s}" % env, "")
        s = _sub_cmd(s, "olphoto", "omm", lambda *a: "")
        s = _sub_cmd(s, "olasset", "om", lambda *a: "")
        s = re.sub(r"\\OLEnd(?:Chapter|Part)Hook(?![A-Za-z])", "", s)
        return re.sub(r"\n{3,}", "\n\n", s)

    def _tagenumerate(self, a, body):
        tags = a[0].split(",")
        if sum(self.cfg.on(t) for t in tags) > 1:
            return "\\begin{enumerate}" + body + "\\end{enumerate}"
        return _sub_cmd(body, "tagitem", "mmt", lambda t, y, n: y if self.cfg.on(t) else n)

    @staticmethod
    def _indcase(star, excl, a, c, text):
        """config's \\indcase*!{A}{complex}{text}: the case's description, \\indfrm and \\indcomplex set."""
        head = f"${a}$ is atomic: " if star else f"${a} \\ident {c}$: "
        body = "exercise." if excl else re.sub(r"\\indfrmp?(?![A-Za-z])", lambda _: a, text)
        return head + re.sub(r"\\indcomplex(?![A-Za-z])", lambda _: c, body)

    def _tagprob(self, m):
        (t1, t2), j = _args(m.group(1), 0, "om")
        body = m.group(1)[j:]
        keep = self.cfg.on(t1 or "tagTrue") and self.cfg.on(t2 or "")
        return body if keep else re.sub(r"\\begin\{(prob|probtag)\}.*?\\end\{\1\}", "", body, flags=re.S)

    def _tagrefs(self, x: str) -> str:
        keys = [k.strip() for t, k in re.findall(r"([A-Za-z]+)\s*/\s*\{([^{}]*)\}", x) if self.cfg.on(t)]
        return "\\cref{%s}" % ",".join(keys) if keys else ""

    def _token(self, m) -> str:
        up, art, key, pl = m.groups()
        t = self.cfg.tokens.get(key)
        if t is None:
            return key + (pl or "")
        if art:
            return t["A" if up else "a"] + " " + t["p" if pl else "s"]
        return t[("P" if pl else "S") if up else ("p" if pl else "s")]


def chapters(body: str) -> list[dict]:
    """[{title, body, appendix}] of an assembled book; the text before the first chapter is
    dropped, and the book ends at \\bibliography."""
    end = body.find("\\bibliography{")
    body = body[:end] if end >= 0 else body
    starts = [m.start() for m in _CHAPTER.finditer(body)]
    apx = body.find("\\appendix")
    out = []
    for a, b in zip(starts, starts[1:] + [len(body)]):
        m = _CHAPTER.match(body, a)
        title, _ = group(body, m.end() - 1)
        text = body[a:b].replace("\\appendix", "")
        out.append({"title": title.strip(), "body": text.strip(), "appendix": 0 <= apx < a})
    return out


def write_book(out: Path, pre: str, chs: list[dict], main: str):
    """chNN.tex, labels.json and chapters.json, as prepare_book writes them."""
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("ch[0-9][0-9].tex"):                       # a previous run's chapters
        f.unlink()
    labels, toc, n_main, n_apx = {}, [], 0, 0
    xmac = xparse_macros(pre)
    for k, c in enumerate(chs, 1):
        c["body"] = expand_xparse(c["body"], xmac)
        if c["appendix"]:
            n_apx += 1
            num = "\\appendix\n\\setcounter{chapter}{%d}" % (n_apx - 1)
        else:
            n_main += 1
            num = "\\setcounter{chapter}{%d}" % (n_main - 1)
        f = out / f"ch{k:02d}.tex"
        f.write_text(f"{pre}\n\\begin{{document}}\n{num}\n{c['body']}\n\\end{{document}}\n", encoding="utf-8")
        facts = extract_facts(read_tex(str(f)))
        by_label = {lab: x for x in facts["facts"] for lab in x["labels"]}
        for lab, v in facts["labels"].items():
            x = by_label.get(lab, {})
            num_ = v["number"]
            if c["appendix"] and num_ and num_[:1] == "A":      # latex_facts letters every lone appendix chapter A
                num_ = chr(ord("A") + n_apx - 1) + num_[1:]
            labels[lab] = {"chapter": k, "number": num_, "kind": v["kind"], "type": x.get("type"),
                           "display": x.get("display"), "name": x.get("optarg")}
        toc.append({"chapter": k, "file": f.name, "title": c["title"], "facts": len(facts["facts"]),
                    "chars": len(c["body"]), "sources": c.get("sources", [])})
        print(f"ch{k:02d} {len(facts['facts']):4d} facts {len(c['body']) // 1000:5d}K chars  {c['title'][:60]}")
    (out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=0))
    (out / "chapters.json").write_text(json.dumps({"main": main, "chapters": toc}, indent=1))
    print(f"{len(chs)} chapters, {len(labels)} labels -> {out}")


def finish(olp: OLP, chs: list[dict], book_dir: Path | None, extra_labels: set) -> list[dict]:
    """\\oliflabeldef against the book's labels; summary and problems at each chapter's end."""
    known = extra_labels | {x for c in chs for x in re.findall(r"\\label\{([^{}]*)\}", c["body"])}
    n_main = 0
    for c in chs:
        body = _sub_cmd(c["body"], "oliflabeldef", "mmm", lambda lab, y, n: y if lab.strip() in known else n)
        probs = _PROB.findall(body)
        body = _PROB.sub("", body).rstrip()
        n_main += not c["appendix"]
        summ = book_dir / "include" / f"summary-{n_main}.tex" if book_dir and not c["appendix"] else None
        if summ and summ.is_file():
            body += "\n\n\\section*{Summary}\n" + olp.convert(_read(summ)).strip()
        if probs:
            body += "\n\n\\section*{Problems}\n" + "\n\n".join(probs)
        c["body"] = re.sub(r"\n{3,}", "\n\n", body)
    return chs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("olp_root")
    ap.add_argument("out")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--book", help="a book's driver name (slc)")
    g.add_argument("--parts", nargs="+", help="OLP parts, content/<part>/<part>.tex")
    ap.add_argument("--book-dir", help="folder of the book's driver and config (default: found next to OLP_ROOT)")
    ap.add_argument("--skip-dup", help="a prepared book: leave out chapters whose files it already has")
    ap.add_argument("--labels-from", help="a prepared book whose labels count as defined (\\oliflabeldef)")
    a = ap.parse_args()
    root, out = Path(a.olp_root).resolve(), Path(a.out)
    content = root / "content"
    cfg = Config()
    cfg.read(_read(root / "open-logic-config.sty"))
    extra = set(json.loads((Path(a.labels_from) / "labels.json").read_text())) if a.labels_from else set()
    if a.book:
        bd = Path(a.book_dir) if a.book_dir else next(p.parent for p in root.parent.glob(f"*/{a.book}.tex"))
        if (bd / f"{a.book}-config.sty").is_file():
            cfg.read(_read(bd / f"{a.book}-config.sty"))
        envs = _read(bd / f"{a.book}-envs.sty") if (bd / f"{a.book}-envs.sty").is_file() \
            else _read(root / "open-logic-envs.sty")
        for m in re.finditer(r"\\usepackage\{\\olpath/([^}]*)\}", envs):
            envs += _read(root / f"{m.group(1)}.sty")
        cfg.read_envs(envs)
        olp = OLP(content, cfg)
        body = olp.inline(bd / f"{a.book}.tex", driver=True)
        chs = chapters(olp.convert(body))
        main_f = str(bd / f"{a.book}.tex")
    else:
        bd = None
        cfg.read(_read(root / "open-logic-complete-config.sty"))
        cfg.read_envs(_read(root / "open-logic-envs.sty"))
        olp = OLP(content, cfg)
        dup = set()
        if a.skip_dup:
            dup = {f for c in json.loads((Path(a.skip_dup) / "chapters.json").read_text())["chapters"]
                   for f in c.get("sources", [])}
        chs = [c for part in a.parts for c in chapters(olp.convert(olp.inline(content / part / f"{part}.tex")))]
        main_f = " ".join(str(content / p / f"{p}.tex") for p in a.parts)
    # each chapter's source files (for --skip-dup): those under its \olchapter's folder
    for c in chs:
        m = re.search(r"\\label\{([^:{}]*):([^:{}]*)::chap\}", c["body"])
        d = olp.chapter_dirs.get(m.groups()) if m else None
        c["sources"] = sorted(f for f in olp.files if d and f.startswith(d))
    if not a.book and a.skip_dup:
        kept = [c for c in chs if not (c["sources"] and len(set(c["sources"]) & dup) * 2 > len(c["sources"]))]
        for c in chs:
            if c not in kept:
                print("skip (in", a.skip_dup + "):", c["title"])
        chs = kept
    write_book(out, cfg.preamble(), finish(olp, chs, bd, extra), main_f)


if __name__ == "__main__":
    main()
