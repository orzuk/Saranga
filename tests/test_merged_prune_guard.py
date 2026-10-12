"""Regression tests for two bugs of the merged algorithm, on the real rule files
that showed them (a 40-paper Haiku run on the v6 silver, snapshot after paper 10):

1. A prune that left its file broken was undone in full. Pruning _STEP_REF
   commented out `distinct = {... _STEP_REF.findall(para)}` but not the line
   after it that reads `distinct`; the post-prune check found the undefined
   name and restored the pre-prune file, so _PROCEDURAL_LEAD (322 FP, 5 TP),
   pruned in the same step, came back. Each prune is now checked on its own.

2. A table keyed by id(pattern) broke under rule_guard.guard_module. The
   simpleenv group looked its patterns up in {id(REMARK_ENV_RE): ...}; the
   guard swaps each module-level pattern for a wrapper after import, so the
   lookup raised KeyError and the parser dropped every remark, example and
   assumption rule on any paper where one matched.

Runs without pytest:  python3 tests/test_merged_prune_guard.py
"""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO / "scripts", REPO / "src" / "LLMVersion", REPO / "src"):
    sys.path.insert(0, str(p))

import distillation_analysis as da        # noqa: E402
import rule_guard                         # noqa: E402

FIX = REPO / "tests" / "fixtures" / "merged_prune_guard"
FAILS = []


def check(got, want, why):
    if got != want:
        FAILS.append(f"{why}\n     got  {got!r}\n     want {want!r}")


def load(path: Path, name: str, src: str | None = None):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    if src is None:
        spec.loader.exec_module(mod)
    else:
        exec(compile(src, str(path), "exec"), mod.__dict__)
    return mod


PROBE_ALG = ("We compute the value of the functional below.\n"
             "\\begin{equation}\n  F(x) = \\int_0^1 f(t)\\,dt\n\\end{equation}\n\n"
             "In step 1 we fix the data, and in step 2 we update it.\n")


def test_prune_does_not_break_or_revert():
    lines = (FIX / "algorithm_group.py").read_text().splitlines(keepends=True)
    before = da._undefined_names("".join(lines))
    check(before, set(), "the fixture file reads no undefined name")

    # the bug: the old comment-out alone strands `distinct`
    old = da._comment_out_rule_block(lines, "_STEP_REF", ["p"], 0)
    check(da._undefined_names("".join(old)), {"distinct"},
          "plain comment-out of _STEP_REF leaves `distinct` undefined (the bug)")

    hows = []
    for name in ("_PROCEDURAL_LEAD", "_METHOD_SUBST_PROSE", "_STEP_REF"):
        lines, how = da._prune_rule_safely(lines, name, ["p"], 0)
        hows.append(how)
    check(hows, ["commented", "commented", "rebound"],
          "two rules commented out, _STEP_REF rebound to a never-matching pattern")
    src = "".join(lines)
    check(da._undefined_names(src), set(), "pruned file reads no undefined name")

    # the merged driver's own post-prune check now passes instead of reverting
    import silver_distillation_merged as sdm
    tmp = FIX / "_pruned_tmp.py"
    tmp.write_text(src)
    try:
        verdict = sdm.validate_and_repair_group_file(tmp, "algorithm", src, probe_text=PROBE_ALG)
    finally:
        tmp.unlink(missing_ok=True)
    check(verdict, "ok", "post-prune check accepts the pruned file")

    # behaviour: the pruned rules no longer fire, the others still can
    pre = load(FIX / "algorithm_group.py", "alg_pre")
    post = load(FIX / "algorithm_group.py", "alg_post", src)
    fired_pre = {d["rule_name"] for d in pre.extract_distilled_algorithm(PROBE_ALG)}
    fired_post = {d["rule_name"] for d in post.extract_distilled_algorithm(PROBE_ALG)}
    check("_PROCEDURAL_LEAD" in fired_pre, True, "before: the display-only match fires")
    check(fired_post & {"_PROCEDURAL_LEAD", "_STEP_REF", "_METHOD_SUBST_PROSE"}, set(),
          "after: none of the pruned rules fires")


PROBE_SIMPLE = ("\\emph{Remark.} The bound in the previous section is not sharp.\n\n"
                "For example, the cycle $C_4$ is bipartite and has four vertices.\n\n"
                "\\textbf{Example.} Consider the complete graph on five vertices.\n\n"
                "Intuitively, the estimate fails because the graph is too dense.\n")


def test_guard_keeps_id_tables_working():
    plain = load(FIX / "simpleenv_group.py", "se_plain")
    want = plain.extract_distilled_simpleenv(PROBE_SIMPLE)
    check(len(want) > 0, True, "the probe makes some simpleenv rule fire")
    guarded = load(FIX / "simpleenv_group.py", "se_guarded")
    rule_guard.guard_module(guarded, source_path=str(FIX / "simpleenv_group.py"))
    try:
        got = guarded.extract_distilled_simpleenv(PROBE_SIMPLE)
    except KeyError as e:
        got = f"KeyError {e}"
    check(got, want, "guarded module returns exactly what the plain module returns")


def test_tables_keyed_by_pattern_object():
    import re
    mod = type(sys)("tbl")
    mod.A_RE = re.compile(r"alpha")
    mod.B_RE = re.compile(r"(?!x)x")
    mod.C_RE = re.compile(r"(?!x)x")              # the same cached object as B_RE
    mod.BY_ID = {id(mod.A_RE): "A_RE", id(mod.B_RE): "B_or_C"}
    mod.BY_OBJ = {mod.A_RE: "A_RE"}
    rule_guard.guard_module(mod)
    check(mod.BY_ID.get(id(mod.A_RE)), "A_RE", "id table finds the wrapper")
    check((mod.BY_ID.get(id(mod.B_RE)), mod.BY_ID.get(id(mod.C_RE))), ("B_or_C", "B_or_C"),
          "every wrapper of a shared compiled object is found")
    check(mod.BY_OBJ.get(mod.A_RE), "A_RE", "object-keyed table finds the wrapper")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as e:                            # noqa: BLE001
                FAILS.append(f"{name} raised {type(e).__name__}: {e}")
    if FAILS:
        print("FAILED:\n  " + "\n  ".join(FAILS))
        sys.exit(1)
    print("all merged prune/guard tests passed")
