# AUTO-GENERATED combined distilled-rules importer (silver merged
# distillation). Re-exports per-type entry points from per-group rule
# modules so the parser dispatch (_apply_distilled_rules ->
# extract_distilled_<type>) works unchanged. This file holds NO patterns,
# so the prune step (which edits the per-group files) never touches it.
import importlib.util as _ilu
import os as _os

# Resolve group files relative to this module's real location (realpath
# follows the production {type}_eval/distilled_rules.py symlinks), so the
# rules load regardless of repo path / host (local Mac or remote Linux).
_BASE = _os.path.join(_os.path.dirname(_os.path.realpath(__file__)), "groups")
_GROUP_FILES = {
    "definition": _os.path.join(_BASE, "definition", "distilled_rules.py"),
    "theoremlike": _os.path.join(_BASE, "theoremlike", "distilled_rules.py"),
    "proof": _os.path.join(_BASE, "proof", "distilled_rules.py"),
    "simpleenv": _os.path.join(_BASE, "simpleenv", "distilled_rules.py"),
    "algorithm": _os.path.join(_BASE, "algorithm", "distilled_rules.py"),
}

_TYPE_TO_GROUP = {
    "definition": "definition",
    "theorem": "theoremlike",
    "lemma": "theoremlike",
    "proposition": "theoremlike",
    "corollary": "theoremlike",
    "claim": "theoremlike",
    "conjecture": "theoremlike",
    "problem": "theoremlike",
    "open_problem": "theoremlike",
    "proof": "proof",
    "remark": "simpleenv",
    "example": "simpleenv",
    "assumption": "simpleenv",
    "algorithm": "algorithm"
}


def _load_group(gkey):
    path = _GROUP_FILES.get(gkey)
    if not path or not _os.path.isfile(path):
        return None
    try:
        spec = _ilu.spec_from_file_location('distilled_group_' + gkey, path)
        m = _ilu.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    except Exception:
        return None


def _extract_group(gkey, text):
    m = _load_group(gkey)
    if m is None:
        return []
    fn = getattr(m, 'extract_distilled_' + gkey, None)
    if fn is None:
        return []
    try:
        return fn(text) or []
    except Exception:
        return []


def extract_distilled_all(text):
    out = []
    for gkey in _GROUP_FILES:
        out.extend(_extract_group(gkey, text))
    return out


def extract_distilled_definition(text):
    return _extract_group('definition', text)

def extract_distilled_theorem(text):
    return [d for d in _extract_group('theoremlike', text)
            if d.get('structure_type') == 'theorem']

def extract_distilled_lemma(text):
    return [d for d in _extract_group('theoremlike', text)
            if d.get('structure_type') == 'lemma']

def extract_distilled_proposition(text):
    return [d for d in _extract_group('theoremlike', text)
            if d.get('structure_type') == 'proposition']

def extract_distilled_corollary(text):
    return [d for d in _extract_group('theoremlike', text)
            if d.get('structure_type') == 'corollary']

def extract_distilled_claim(text):
    return [d for d in _extract_group('theoremlike', text)
            if d.get('structure_type') == 'claim']

def extract_distilled_conjecture(text):
    return [d for d in _extract_group('theoremlike', text)
            if d.get('structure_type') == 'conjecture']

def extract_distilled_problem(text):
    return [d for d in _extract_group('theoremlike', text)
            if d.get('structure_type') == 'problem']

def extract_distilled_open_problem(text):
    return [d for d in _extract_group('theoremlike', text)
            if d.get('structure_type') == 'open_problem']

def extract_distilled_proof(text):
    return _extract_group('proof', text)

def extract_distilled_remark(text):
    return [d for d in _extract_group('simpleenv', text)
            if d.get('structure_type') == 'remark']

def extract_distilled_example(text):
    return [d for d in _extract_group('simpleenv', text)
            if d.get('structure_type') == 'example']

def extract_distilled_assumption(text):
    return [d for d in _extract_group('simpleenv', text)
            if d.get('structure_type') == 'assumption']

def extract_distilled_algorithm(text):
    return _extract_group('algorithm', text)
