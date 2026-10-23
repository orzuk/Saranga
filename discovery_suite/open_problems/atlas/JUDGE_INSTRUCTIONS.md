# Atlas LLM pass: judging problem / resolution links

Each record in your chunk file looks like:

    #<lid> <kind>/<node type> <arXiv id of the paper>
    TEXT: <LaTeX snippet of the node>
    CITES: key[optional note] arXiv:<id> (<bib year>): <bibliography entry> | ...

kind = `restated` (a conjecture / open problem / problem node that cites something) or `claim` (a theorem-like
node that may say it settles a cited problem). Judge each record from its text only. Do not use the web.

Write ONE line per record, tab-separated, 7 fields, to your output file (append as you go; never skip a record):

    lid  KEEP  STATUS  SRC  NAME  POSER  NOTE

- KEEP: `y` if the record is a genuine, specific mathematical open problem/conjecture/question (restated) or a
  statement that a specific named or cited problem/conjecture/question is settled (claim); else `n`.
  Say `n` for: future-work remarks, "the problem of computing X" / optimisation or benchmark tasks, classical
  named problems that are just topics (Dirichlet problem, moment problem) unless an open question about them is
  stated, NP-hardness facts, ordinary lemmas, parse garbage.
- STATUS: restated -> `open` (presented as open at the time), `resolved` (text says it was already settled),
  `partial` (open but partial results mentioned); claim -> `proved`, `disproved`, `answered` (question answered,
  either way), `partial` (special case / partial progress); `-` if KEEP=n.
- SRC: is the cited key (the first relevant one) the place the problem was posed (`origin`), the paper that
  resolved it (`resolver`), or just background / partial results / own earlier work (`other`)? `-` if KEEP=n.
- NAME: a short canonical name of the problem, <= 10 words, as a mathematician would search it
  (e.g. "Kaplansky direct finiteness conjecture", "Erdos unit distance problem", "Kourovka 9.68 p-length");
  include an Erdős problem number or Kourovka number if the text gives one. `-` if KEEP=n.
- POSER: the person(s) who posed it, if the text says (e.g. "Wiegold"); else `-`.
- NOTE: <= 8 words, optional; `-` if none.

No tabs or newlines inside fields. Be strict and fast; one line per record, in order.
