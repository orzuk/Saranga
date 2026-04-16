# Set paths for papers data
import sys
import os

# ArXiv API endpoint and XML namespaces for query mode
ATOM_URL = 'http://export.arxiv.org/api/query'
NS = {'atom': 'http://www.w3.org/2005/Atom',
    'opensearch': 'http://a9.com/-/spec/opensearch/1.1/'}
ARXIV_NS = {'arxiv': 'http://arxiv.org/schemas/atom'}


SCRIPTS_DIR = './scripts'
SRC_DIR = './src'

if sys.platform.lower().startswith('win'):
    # Running on Windows/PyCharm
    DATA_DIR = 'C:/Datasets/big_data_project_52017/arxiv_data'
else:
    # Running on *nix – decide between your WSL‐mount vs cluster
    # 1) Check for your local WSL path
    wsl_path = '/mnt/c/Datasets/big_data_project_52017/arxiv_data'
    # 2) Check for your cluster path
    cluster_path = '/sci/labs/orzuk/orzuk/teaching/big_data_project_52017/2024_25/arxiv_data'
    # 3) If neither exists, fall back to your home‐dir layout
    home_path = os.path.expanduser('~/Datasets/big_data_project_52017/arxiv_data')

    if os.path.exists(wsl_path):
        DATA_DIR = wsl_path
    elif os.path.exists(cluster_path):
        DATA_DIR = cluster_path
    else:
        DATA_DIR = home_path

# Make sure it really points somewhere valid:
if not os.path.isdir(DATA_DIR):
    raise RuntimeError(f"DATA_DIR not found: {DATA_DIR}")

print("Using DATA_DIR =", DATA_DIR)

ARXIV_IDS_FILE = DATA_DIR + "/arxiv_ids_all_min_max.json"
ARXIV_META_DATA = DATA_DIR + '/arxiv-metadata-oai-snapshot.json'
ARXIV_META_DATA_COMPACT = DATA_DIR + '/arxiv-metadata-oai-snapshot-compact.pkl'
ARXIV_META_DATA_HDF5 = DATA_DIR + '/arxiv-metadata-oai-snapshot-compact.h5'
FULL_PAPERS_DIR = DATA_DIR + '/full_papers'
FULL_PAPERS_ADVANCED_DIR = DATA_DIR + '/full_papers_advanced'

LOCAL_FIRST = True  # Try to find papers data/meta-data locally first. If can't find, then crawl arxiv website.
