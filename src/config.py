# Set paths for project data and code
import sys
import os
from pathlib import Path

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
    # Running on Windows/PyCharm
    DATA_DIR = Path('C:/Datasets/saranga_data')
    CODE_DIR = Path('C:/Code/Github/saranga')
else:
    # Running on *nix – decide between WSL-mount vs cluster
    # Local data mirrors cluster structure: DATA_DIR/naturalproofs/, DATA_DIR/arxiv/, etc.
    # Only the root changes; relative paths are the same everywhere.
    wsl_code = Path('/mnt/c/Code/Github/saranga')
    wsl_data_gdrive = Path('/mnt/g/My Drive/Research/saranga')  # Google Drive mirror
    wsl_data_legacy = Path('/mnt/c/Datasets/saranga_data')  # old location

    cluster_data = Path('/<cluster>/<user>/projects/saranga')
    cluster_code = Path('/<cluster>/<user>/github/saranga')

    home_data = Path.home() / 'Datasets' / 'saranga_data'
    home_code = Path.home() / 'Code' / 'saranga'

    if _safe_exists(cluster_code):
        # Cluster takes priority if it exists
        DATA_DIR = cluster_data
        CODE_DIR = cluster_code
    elif _safe_exists(wsl_code):
        CODE_DIR = wsl_code
        # Prefer Google Drive mirror (has naturalproofs/, arxiv/, etc.)
        if _safe_exists(wsl_data_gdrive):
            DATA_DIR = wsl_data_gdrive
        elif _safe_exists(wsl_data_legacy):
            DATA_DIR = wsl_data_legacy
        else:
            DATA_DIR = wsl_data_gdrive  # default, will be created if needed
    else:
        DATA_DIR = home_data
        CODE_DIR = home_code

# =============================================================================
# RELATIVE PATHS (same across all environments)
# =============================================================================

# Code directories
SCRIPTS_DIR = CODE_DIR / 'scripts'
SRC_DIR = CODE_DIR / 'src'

# Data subdirectories
ARXIV_DIR = DATA_DIR / 'arxiv'
PROOFWIKI_DIR = DATA_DIR / 'proofwiki'
WIKIDATA_DIR = DATA_DIR / 'wikidata'

# ArXiv data files
ARXIV_IDS_FILE = ARXIV_DIR / 'arxiv_ids_all_min_max.json'
ARXIV_META_DATA = ARXIV_DIR / 'arxiv-metadata-oai-snapshot.json'
ARXIV_META_DATA_COMPACT = ARXIV_DIR / 'arxiv-metadata-oai-snapshot-compact.pkl'
ARXIV_META_DATA_HDF5 = ARXIV_DIR / 'arxiv-metadata-oai-snapshot-compact.h5'
FULL_PAPERS_DIR = ARXIV_DIR / 'full_papers'

# ProofWiki data files
PROOFWIKI_CORPUS = PROOFWIKI_DIR / 'proofwiki_corpus.json'

# Wikidata data files
WIKIDATA_REGISTRY = WIKIDATA_DIR / 'concept_registry.json'

# =============================================================================
# API ENDPOINTS
# =============================================================================

# ArXiv API endpoint and XML namespaces for query mode
ATOM_URL = 'http://export.arxiv.org/api/query'
NS = {'atom': 'http://www.w3.org/2005/Atom',
    'opensearch': 'http://a9.com/-/spec/opensearch/1.1/'}
ARXIV_NS = {'arxiv': 'http://arxiv.org/schemas/atom'}

# =============================================================================
# OPTIONS
# =============================================================================

LOCAL_FIRST = True  # Try to find papers data/meta-data locally first. If can't find, then crawl arxiv website.

# =============================================================================
# INITIALIZATION
# =============================================================================

def ensure_data_dirs():
    """Create data directories if they don't exist."""
    for d in [DATA_DIR, ARXIV_DIR, PROOFWIKI_DIR, WIKIDATA_DIR]:
        d.mkdir(parents=True, exist_ok=True)

# Create directories on import (optional - can comment out if you want manual control)
# ensure_data_dirs()

# Print active configuration
print(f"CODE_DIR = {CODE_DIR}")
print(f"DATA_DIR = {DATA_DIR}")
