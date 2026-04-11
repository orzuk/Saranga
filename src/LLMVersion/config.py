"""
LLMVersion/config.py — thin shim that re-exports src/config.py.

This file exists so that LLMVersion code can continue to use
`from config import X` unchanged. It explicitly loads the canonical
src/config.py file via importlib (under an alias name, to avoid a
circular self-import), then re-exports its constants — converting
`Path` objects to strings for LLMVersion's string-concatenation code.

If you add a new path constant to src/config.py that LLMVersion code
uses via string concatenation, add it to the _PATH_NAMES tuple below.
"""

import importlib.util as _importlib_util
from pathlib import Path as _Path

# Explicitly load src/config.py under a different module name so this
# shim doesn't recurse into itself when doing `from config import *`.
_src_config_path = _Path(__file__).resolve().parent.parent / "config.py"
_spec = _importlib_util.spec_from_file_location("_src_config", str(_src_config_path))
_src_config = _importlib_util.module_from_spec(_spec)
_spec.loader.exec_module(_src_config)

# Path constants: convert from pathlib.Path to str for LLMVersion's
# string-based path arithmetic.
_PATH_NAMES = (
    "DATA_DIR", "CODE_DIR", "SCRIPTS_DIR", "SRC_DIR",
    "ARXIV_DIR", "PROOFWIKI_DIR", "WIKIDATA_DIR",
    "ARXIV_IDS_FILE", "ARXIV_META_DATA",
    "ARXIV_META_DATA_COMPACT", "ARXIV_META_DATA_HDF5",
    "FULL_PAPERS_DIR",
    "PROOFWIKI_CORPUS", "WIKIDATA_REGISTRY",
)
for _name in _PATH_NAMES:
    _val = getattr(_src_config, _name, None)
    if _val is not None:
        globals()[_name] = str(_val)

# Non-path constants pass through unchanged.
_OTHER_NAMES = ("ATOM_URL", "NS", "ARXIV_NS", "LOCAL_FIRST", "ensure_data_dirs")
for _name in _OTHER_NAMES:
    if hasattr(_src_config, _name):
        globals()[_name] = getattr(_src_config, _name)

# Cleanup so `from config import *` doesn't drag internal names into callers.
del _importlib_util, _Path, _src_config_path, _spec, _src_config
del _PATH_NAMES, _OTHER_NAMES, _name
try:
    del _val
except NameError:
    pass
