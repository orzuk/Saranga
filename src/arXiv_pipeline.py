import os
from pathlib import Path
import networkx as nx
from sympy import simplify
from some_latex_parser import parse_latex
from embedding_library import get_math_embeddings
from api_tools import fetch_arxiv_metadata, fetch_arxiv_pdfs
from graph_tools import build_citation_network, build_concept_network


# Step 1: Configuration
class Config:
    ARXIV_CATEGORY = "math"  # E.g., 'math', 'cs', etc.
    OUTPUT_DIR = "output/"
    METADATA_FILE = "arxiv_metadata.json"
    GRAPH_OUTPUT = "citation_network.graphml"


# Step 2: Fetch Data
def fetch_data(config):
    print("Fetching metadata from arXiv...")
    metadata = fetch_arxiv_metadata(config.ARXIV_CATEGORY, max_results=1000)
    Path(config.OUTPUT_DIR).mkdir(exist_ok=True, parents=True)
    with open(os.path.join(config.OUTPUT_DIR, config.METADATA_FILE), "w") as f:
        json.dump(metadata, f)
    print("Fetching PDFs from arXiv...")
    fetch_arxiv_pdfs(metadata, config.OUTPUT_DIR)


# Step 3: Parse Papers for Mathematical Content
def parse_math_content(papers_dir):
    math_content = {}
    for paper_file in Path(papers_dir).glob("*.pdf"):
        try:
            print(f"Parsing {paper_file}...")
            content = parse_latex(paper_file)  # Use a LaTeX or PDF parser
            math_content[paper_file.name] = {
                "definitions": extract_definitions(content),
                "theorems": extract_theorems(content),
                "formulas": extract_formulas(content)
            }
        except Exception as e:
            print(f"Error parsing {paper_file}: {e}")
    return math_content


# Step 4: Normalize and Match Mathematical Content
def normalize_and_match(math_content):
    normalized_content = {}
    for paper, content in math_content.items():
        normalized_formulas = [simplify(f) for f in content.get("formulas", [])]
        normalized_content[paper] = {
            "definitions": content["definitions"],
            "theorems": content["theorems"],
            "formulas": normalized_formulas
        }
    return normalized_content


# Step 5: Build Networks
def build_networks(math_content, metadata, config):
    print("Building citation network...")
    citation_graph = build_citation_network(metadata)  # Use metadata to link papers by citation
    nx.write_graphml(citation_graph, os.path.join(config.OUTPUT_DIR, config.GRAPH_OUTPUT))

    print("Building concept network...")
    concept_graph = build_concept_network(math_content)  # Link papers to shared formulas/concepts
    nx.write_graphml(concept_graph, os.path.join(config.OUTPUT_DIR, "concept_network.graphml"))


# Step 6: Analyze and Visualize Networks
def analyze_networks(config):
    print("Analyzing networks...")
    citation_graph = nx.read_graphml(os.path.join(config.OUTPUT_DIR, config.GRAPH_OUTPUT))
    concept_graph = nx.read_graphml(os.path.join(config.OUTPUT_DIR, "concept_network.graphml"))

    print("Citation Network Info:")
    print(nx.info(citation_graph))
    print("Concept Network Info:")
    print(nx.info(concept_graph))

    # Visualize or perform further analysis here...


# Main Function to Run Pipeline
def main():
    config = Config()

    # Step 1: Fetch metadata and PDFs
    fetch_data(config)

    # Step 2: Parse papers for mathematical content
    math_content = parse_math_content(config.OUTPUT_DIR)

    # Step 3: Normalize and match content
    normalized_content = normalize_and_match(math_content)

    # Step 4: Build networks
    build_networks(normalized_content, metadata=config.METADATA_FILE, config=config)

    # Step 5: Analyze networks
    analyze_networks(config)


if __name__ == "__main__":
    main()
