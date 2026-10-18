# Single source of truth for paths, source/extractor metadata, model IDs,
# the corpus category list, and remote-store identifiers.
#
# Importing from here is the only sanctioned way to refer to any of these.
# No other module in the repo should hardcode a path under /mnt, /sci, or
# /home; nor a `_manual.json` / `_anthropic.json` etc. literal; nor a
# `claude-opus-4-7` / `gpt-4o` model id; nor the 20-category corpus list;
# nor the portal URL or the (legacy) HuggingFace dataset/space id.
import sys
import os
from pathlib import Path


# =============================================================================
# DETERMINISM
# =============================================================================
# Python randomises str hashing per process, so anything that iterates a set or
# keys on hash order can come out differently on every run. Measured on the
# rule-based extractor: the same paper parsed twice gave different output.
# The seed is read when the interpreter starts, so setting it later in the
# process is too late; an entry point calls this first, and it re-launches the
# same command once with the seed fixed. Cluster job scripts also export it.
HASH_SEED = "0"


def ensure_deterministic_hashing():
    """Re-exec this process with PYTHONHASHSEED fixed, unless it already is."""
    if os.environ.get("PYTHONHASHSEED") != HASH_SEED:
        os.environ["PYTHONHASHSEED"] = HASH_SEED
        os.execv(sys.executable, [sys.executable] + sys.argv)

# =============================================================================
# MASTER DIRECTORIES (platform-specific, only these change between environments)
# =============================================================================

def _safe_exists(p):
    # WSL drives can be temporarily disconnected (e.g. /mnt/g when GDrive
    # is unmounted); .exists() raises OSError("No such device") instead of
    # returning False. Treat that the same as "not present".
    try:
        return p.exists()
    except OSError:
        return False


if sys.platform.lower().startswith('win'):
    # Running on Windows / PyCharm
    DATA_DIR = Path('C:/Datasets/Saranga_data')
    CODE_DIR = Path('C:/Code/Github/Saranga')
else:
    # Running on *nix — decide between WSL-mount vs cluster
    wsl_code = Path('/mnt/c/Code/Github/Saranga')
    wsl_data_default = Path('/mnt/c/Datasets/Saranga_data')
    wsl_data_gdrive = Path('/mnt/g/My Drive/Research/Automath')  # legacy GDrive workspace

    cluster_code = Path('/sci/labs/orzuk/orzuk/github/Saranga')
    cluster_data = Path('/sci/labs/orzuk/orzuk/projects/Saranga')
    # Authomathics-named clones are still around during the rename window.
    cluster_code_legacy = Path('/sci/labs/orzuk/orzuk/github/Authomathics')
    cluster_data_legacy = Path('/sci/labs/orzuk/orzuk/projects/Authomathics')

    # The actual large arXiv corpus (full_papers YYYY/MM/DD + all_json/all_png)
    # lives OUTSIDE the projects/Saranga tree above, under the class_52017
    # ("big_data_project_52017") teaching dir. It predates the current layout
    # and is stored as EXTRACTED source trees — this is the directory that blew
    # the Isilon inode/file-count quota (2026-07); migrate to per-paper .tar.gz.
    cluster_arxiv_corpus_legacy = Path(
        '/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data')

    home_data = Path.home() / 'Datasets' / 'Saranga_data'
    home_code = Path.home() / 'Code' / 'Saranga'

    if _safe_exists(cluster_code) or _safe_exists(cluster_code_legacy):
        # Cluster takes priority if we're on a cluster machine
        CODE_DIR = cluster_code if _safe_exists(cluster_code) else cluster_code_legacy
        DATA_DIR = cluster_data if _safe_exists(cluster_data) else cluster_data_legacy
    elif _safe_exists(wsl_code):
        CODE_DIR = wsl_code
        # WSL: prefer the local Saranga_data root if it exists; else fall
        # back to the legacy GDrive workspace (read-only-ish, slow over Drive)
        if _safe_exists(wsl_data_default):
            DATA_DIR = wsl_data_default
        elif _safe_exists(wsl_data_gdrive):
            DATA_DIR = wsl_data_gdrive
        else:
            DATA_DIR = wsl_data_default  # default; will be created on demand
    else:
        DATA_DIR = home_data
        CODE_DIR = home_code

# =============================================================================
# SARANGA DATASET LAYOUT (canonical tier paths; everything outside the repo)
# =============================================================================

# Override with SARANGA_DATA_ROOT env var. Defaults under DATA_DIR so cluster
# / WSL / Windows naturally pick the right base.
DATASET_ROOT = Path(os.environ.get('SARANGA_DATA_ROOT', str(DATA_DIR)))

TIER1_DIR        = DATASET_ROOT / 'tier1'         # human gold (synced from HF)
TIER1_STEPS_DIR  = DATASET_ROOT / 'tier1_steps'   # step-level human gold (NEW)
TIER2_DIR        = DATASET_ROOT / 'tier2'         # LLM silver (~250+)
TIER3_DIR        = DATASET_ROOT / 'tier3'         # rule-based; symlink on cluster
TIER3_SAMPLES    = DATASET_ROOT / 'tier3_samples' # per-category small samples
ALIGNMENT_DIR    = DATASET_ROOT / 'alignment'     # Benchmark 2 (papers, pairs, alignments)
EVAL_DIR         = DATASET_ROOT / 'evaluation'    # LLM eval outputs, FP audits
INSPECTION_DIR   = DATASET_ROOT / 'inspection'    # ad-hoc analysis / scratch dirs
ARXIV_RAW_DIR    = DATASET_ROOT / 'arxiv'         # raw arxiv LaTeX + metadata
FOUNDATION_DIR   = DATASET_ROOT / 'foundation'    # foundation graph builders' inputs

# Foundation graph subdirs (legacy: at top level under DATA_DIR; new layout:
# under FOUNDATION_DIR). Resolve at import; both forms are accepted during the
# migration window.
def _resolve_foundation_subdir(name: str) -> Path:
    new = FOUNDATION_DIR / name
    legacy = DATA_DIR / name
    return new if _safe_exists(new) else legacy

NATURALPROOFS_DIR = _resolve_foundation_subdir('naturalproofs')
PROOFWIKI_DIR     = _resolve_foundation_subdir('proofwiki')
WIKIDATA_DIR      = _resolve_foundation_subdir('wikidata')
MATHLIB_DIR       = _resolve_foundation_subdir('mathlib')
BOOKS_DIR         = _resolve_foundation_subdir('books')
ARXIV_DIR         = _resolve_foundation_subdir('arxiv') if not _safe_exists(ARXIV_RAW_DIR) else ARXIV_RAW_DIR

# Foundation index — the merged JSON the linker reads. Change FOUNDATION_INDEX_FILE
# below to swap which file the link pipeline + foundation_audit + visualizers use.
FOUNDATION_INDEX_FILE = 'clean_foundation_with_books.json'
# FOUNDATION_INDEX_FILE = 'clean_foundation_with_books_neurips_submission_frozen.json'  # NeurIPS-frozen (3 books, ~27k entries)
# FOUNDATION_INDEX_FILE = 'clean_foundation.json'                                        # Mathlib-only baseline (~26k entries)
FOUNDATION_INDEX_PATH = NATURALPROOFS_DIR / FOUNDATION_INDEX_FILE

# In-repo manifests = source of truth for "what each tier should contain".
MANIFESTS_DIR        = CODE_DIR / 'dataset_manifests'
TIER1_MANIFEST       = MANIFESTS_DIR / 'tier1.csv'
TIER1_STEPS_MANIFEST = MANIFESTS_DIR / 'tier1_steps.csv'
TIER2_MANIFEST       = MANIFESTS_DIR / 'tier2.csv'
TIER3_MANIFEST       = MANIFESTS_DIR / 'tier3.csv'
ALIGNMENT_MANIFEST   = MANIFESTS_DIR / 'alignment.csv'

# =============================================================================
# REMOTE STORES
# =============================================================================

# The online portal (Google Cloud Run, europe-west1; Docker setup in deploy/hf_space_portal/).
PORTAL_URL = 'https://saranga-portal-1043069375918.europe-west1.run.app'

# Hugging Face is no longer used (dropped for the Cloud Run portal); kept for old scripts only.
HF_DATASET_REPO = 'RHCPP/saranga'   # huggingface.co/datasets/<HF_DATASET_REPO>
HF_PORTAL_SPACE = 'RHCPP/saranga'   # huggingface.co/spaces/<HF_PORTAL_SPACE>

# =============================================================================
# EXTRACTION SOURCES (single source of truth for filename suffix, model id,
# human-readable label per extraction provider)
# =============================================================================
#
# Adding a new model = one entry here. No other file in the repo should
# hardcode a `_<suffix>.json` literal or a model-name string.
#
# Naming conventions:
#   suffix     — what gets appended before `.json` in extracted-output filenames.
#                Includes the leading underscore so callers can do
#                `f"{paper_id}{SOURCES[k]['suffix']}.json"`.
#   label      — human-readable name for figures / tables / portal headers.
#   model      — provider-specific model ID for API calls. None for human gold
#                or rule-based.
#   kind       — one of 'human', 'rule', 'llm'. Used to bucket sources.
#
# `manual` is RESERVED for human-made gold (T1). Rule-based extractor output
# uses suffix `_rules` (was previously also `_manual`, which was overloaded).

SOURCES = {
    'manual':   dict(suffix='_manual',   label='Human gold (T1)',   model=None,
                     kind='human'),
    'rules':    dict(suffix='_rules',    label='Rule-based (T3)',   model=None,
                     kind='rule'),
    'opus':     dict(suffix='_opus',     label='Claude Opus 4.7',
                     model='claude-opus-4-7',           kind='llm'),
    'sonnet':   dict(suffix='_sonnet',   label='Claude Sonnet 4.6',
                     model='claude-sonnet-4-6',          kind='llm'),
    'haiku':    dict(suffix='_haiku',    label='Claude Haiku 4.5',
                     model='claude-haiku-4-5-20251001',  kind='llm'),
    'anthropic': dict(suffix='_anthropic', label='Anthropic (default Sonnet)',
                      model='claude-sonnet-4-6',         kind='llm'),
    'gpt4o':    dict(suffix='_openai',   label='GPT-4o',
                     model='gpt-4o-2024-08-06',          kind='llm'),
    'openai':   dict(suffix='_openai',   label='OpenAI (default GPT-4o)',
                     model='gpt-4o-2024-08-06',          kind='llm'),
    'gemini':   dict(suffix='_gemini',   label='Gemini 2.5 Pro',
                     model='gemini-2.5-pro',             kind='llm'),
    'qwen':     dict(suffix='_qwen',     label='Qwen 2.5 72B',
                     model='qwen2.5-72b-instruct',       kind='llm'),
    'deepseek': dict(suffix='_deepseek', label='DeepSeek R1',
                     model='deepseek-r1',                kind='llm'),
}

# Convenience reverse map and groupings.
SUFFIX_TO_SOURCE = {v['suffix']: k for k, v in SOURCES.items()}
HUMAN_SOURCES    = {k for k, v in SOURCES.items() if v['kind'] == 'human'}
RULE_SOURCES     = {k for k, v in SOURCES.items() if v['kind'] == 'rule'}
LLM_SOURCES      = {k for k, v in SOURCES.items() if v['kind'] == 'llm'}

# Default LLM model when nothing else is specified (used by CLI defaults).
DEFAULT_LLM_KEY = 'opus'
DEFAULT_LLM_MODEL = SOURCES[DEFAULT_LLM_KEY]['model']

# =============================================================================
# CORPUS CATEGORIES (the 20-category sample for the 100K T3 run)
# =============================================================================
#
# Filesystem-friendly form (underscores everywhere, no dots or dashes). This
# is what cluster, local, HF, and config.py paths all use.
#
# ARXIV_FORM gives the arxiv-canonical form (with dot or dash) for any code
# that needs to query the arxiv API. The two forms are interchanged ONLY at
# the arxiv-API boundary — every other layer uses the FS-friendly form.

CORPUS_CATEGORIES = [
    'cs_CC', 'cs_DS', 'cs_IT', 'cs_LG',
    'math_ph',
    'math_AG', 'math_AP', 'math_AT', 'math_CA', 'math_CO',
    'math_DG', 'math_FA', 'math_GR', 'math_LO', 'math_NA',
    'math_NT', 'math_OC', 'math_PR', 'math_RT',
    'stat_TH',
]

ARXIV_FORM = {
    'cs_CC': 'cs.CC', 'cs_DS': 'cs.DS', 'cs_IT': 'cs.IT', 'cs_LG': 'cs.LG',
    'math_ph': 'math-ph',
    'math_AG': 'math.AG', 'math_AP': 'math.AP', 'math_AT': 'math.AT',
    'math_CA': 'math.CA', 'math_CO': 'math.CO',
    'math_DG': 'math.DG', 'math_FA': 'math.FA', 'math_GR': 'math.GR',
    'math_LO': 'math.LO', 'math_NA': 'math.NA',
    'math_NT': 'math.NT', 'math_OC': 'math.OC', 'math_PR': 'math.PR',
    'math_RT': 'math.RT',
    'stat_TH': 'stat.TH',
}

# Reverse: from arxiv-canonical to FS-friendly.
FS_FORM = {v: k for k, v in ARXIV_FORM.items()}

# =============================================================================
# CODE / PORTAL DIRECTORIES (in the repo)
# =============================================================================

SCRIPTS_DIR = CODE_DIR / 'scripts'
SRC_DIR     = CODE_DIR / 'src'
PORTAL_DIR  = CODE_DIR / 'portal'

# Portal data is a build artifact (gitignored) regenerated by
# scripts/rebuild_portal.py from $SARANGA_DATA_ROOT.
PORTAL_DATA_DIR = PORTAL_DIR / 'data'

# =============================================================================
# ARXIV API ENDPOINTS
# =============================================================================

ATOM_URL = 'http://export.arxiv.org/api/query'
NS = {'atom': 'http://www.w3.org/2005/Atom',
      'opensearch': 'http://a9.com/-/spec/opensearch/1.1/'}
ARXIV_NS = {'arxiv': 'http://arxiv.org/schemas/atom'}

# arxiv data files (raw metadata + full papers cache)
ARXIV_IDS_FILE          = ARXIV_DIR / 'arxiv_ids_all_min_max.json'
ARXIV_META_DATA         = ARXIV_DIR / 'arxiv-metadata-oai-snapshot.json'
ARXIV_META_DATA_COMPACT = ARXIV_DIR / 'arxiv-metadata-oai-snapshot-compact.pkl'
ARXIV_META_DATA_HDF5    = ARXIV_DIR / 'arxiv-metadata-oai-snapshot-compact.h5'
FULL_PAPERS_DIR         = ARXIV_DIR / 'full_papers'

# proofwiki / wikidata data files
PROOFWIKI_CORPUS  = PROOFWIKI_DIR / 'proofwiki_corpus.json'
WIKIDATA_REGISTRY = WIKIDATA_DIR / 'concept_registry.json'

# =============================================================================
# OPTIONS / DEFAULTS
# =============================================================================

LOCAL_FIRST = True   # Try local cache before crawling arxiv.

# Default similarity / matching thresholds (used by evaluators and
# graph-alignment scoring as their default CLI values).
DEFAULT_NODE_SIM_THRESHOLD = 0.5
DEFAULT_FLIPPED_EDGE_CREDIT = 0.5

# =============================================================================
# INITIALIZATION
# =============================================================================

def ensure_data_dirs():
    """Create canonical data directories if missing."""
    for d in (DATASET_ROOT, TIER1_DIR, TIER2_DIR, TIER3_DIR, ALIGNMENT_DIR,
              EVAL_DIR, INSPECTION_DIR, ARXIV_RAW_DIR, FOUNDATION_DIR,
              MANIFESTS_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

# Optional verbose dump on import (set SARANGA_CONFIG_VERBOSE=1).
if os.environ.get('SARANGA_CONFIG_VERBOSE'):
    print(f"[config] CODE_DIR     = {CODE_DIR}")
    print(f"[config] DATA_DIR     = {DATA_DIR}")
    print(f"[config] DATASET_ROOT = {DATASET_ROOT}")
    print(f"[config] TIER1_DIR    = {TIER1_DIR}")
    print(f"[config] TIER3_DIR    = {TIER3_DIR}")
