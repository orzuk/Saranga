import networkx as nx
import json


def build_citation_network(metadata_file):
    """
    Build a citation network from arXiv metadata.

    Parameters:
    - metadata_file (str): Path to the JSON file containing arXiv metadata.

    Returns:
    - nx.DiGraph: A directed citation network graph.
    """
    # Load metadata from JSON
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)

    # Initialize a directed graph
    citation_graph = nx.DiGraph()

    # Add nodes and edges to the graph
    for paper in metadata:
        paper_id = paper.get("id")  # Unique identifier for the paper
        references = paper.get("references", [])  # List of cited paper IDs

        # Add the paper as a node
        citation_graph.add_node(paper_id, title=paper.get("title"), authors=paper.get("authors"))

        # Add edges for each reference
        for ref in references:
            citation_graph.add_edge(paper_id, ref)

    return citation_graph


# Example usage
if __name__ == "__main__":
    # Path to your metadata file
    metadata_file = "arxiv_metadata.json"

    # Build the citation network
    citation_network = build_citation_network(metadata_file)

    # Save the network to a file
    nx.write_graphml(citation_network, "citation_network.graphml")

    # Print summary information
    print("Citation Network Summary:")
    print(nx.info(citation_network))
