"""Graph checks shared by the validator, the anomaly detector, QA and the figures: longest-path
depth and cycles. Backward edges (a forward reference, an induction using the result itself)
are real dependencies against the reading order; the extraction spec requires the graph to be
acyclic without them, so the checks below are run on forward_edges(edges)."""
from collections import Counter, defaultdict


def forward_edges(edges):
    return [e for e in edges if not e.get("backward")]


def adjacency(ids, edges):
    adj = defaultdict(list)
    for e in edges:
        if e.get("source") in ids and e.get("target") in ids:
            adj[e["source"]].append(e["target"])
    return adj


def depths(nodes, edges):
    """(longest-path depth of every node, roots 0; acyclic?). On a cycle, the nodes on or
    after it keep the depth reached so far."""
    ids = {n["id"] for n in nodes}
    adj = adjacency(ids, edges)
    indeg = Counter(t for ts in adj.values() for t in ts)
    d, q, seen = dict.fromkeys(ids, 0), [i for i in ids if not indeg[i]], 0
    while q:
        u = q.pop(); seen += 1
        for v in adj[u]:
            d[v] = max(d[v], d[u] + 1); indeg[v] -= 1
            if not indeg[v]:
                q.append(v)
    return d, seen == len(ids)


def find_cycle(nodes, edges):
    """One cycle as a node-id path (first node repeated at the end), or None."""
    ids = {n.get("id") for n in nodes}
    adj, color = adjacency(ids, edges), dict.fromkeys(ids, 0)       # 0 new, 1 on the path, 2 done
    for start in ids:
        if color[start]:
            continue
        path, stack, color[start] = [start], [iter(adj[start])], 1
        while stack:
            nxt = next(stack[-1], None)
            if nxt is None:
                color[path.pop()] = 2; stack.pop()
            elif color[nxt] == 1:
                return path[path.index(nxt):] + [nxt]
            elif not color[nxt]:
                color[nxt] = 1; path.append(nxt); stack.append(iter(adj[nxt]))
    return None
