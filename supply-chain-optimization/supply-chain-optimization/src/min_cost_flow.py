"""
min_cost_flow.py
----------------
A small min-cost network-flow solver written with plain Python (no scipy,
no LP library). Method: Successive Shortest Paths.

Idea (in plain words):
  1. Build a graph: source -> refineries -> terminals -> markets -> sink.
  2. Repeatedly find the CHEAPEST path from source to sink that still has
     spare capacity, push as much flow as that path allows, and repeat.
  3. Stop when every market's demand is met (or no path is left = infeasible).

Because we always take the cheapest path first (and allow "undoing" earlier
flow through reverse edges), the final answer is the true minimum-cost flow,
the same optimum a linear-programming solver would return.
"""
EPS = 1e-9


class MinCostFlow:
    def __init__(self, n_nodes):
        self.n = n_nodes
        self.graph = [[] for _ in range(n_nodes)]   # adjacency: list of edge ids
        self.to, self.cap, self.cost = [], [], []   # edge arrays (edge i and i^1 are a pair)

    def add_edge(self, u, v, capacity, cost):
        """Add edge u->v plus its zero-capacity reverse edge (used to undo flow)."""
        self.graph[u].append(len(self.to))
        self.to.append(v); self.cap.append(capacity); self.cost.append(cost)
        self.graph[v].append(len(self.to))
        self.to.append(u); self.cap.append(0.0); self.cost.append(-cost)
        return len(self.to) - 2                     # id of the forward edge

    def flow_on(self, edge_id):
        """Flow currently sent on a forward edge = capacity sitting on its reverse edge."""
        return self.cap[edge_id ^ 1]

    def _cheapest_path(self, s, t):
        """Bellman-Ford style shortest path on edges with spare capacity."""
        INF = float("inf")
        dist = [INF] * self.n
        prev_edge = [-1] * self.n
        dist[s] = 0.0
        for _ in range(self.n - 1):
            changed = False
            for u in range(self.n):
                if dist[u] == INF:
                    continue
                for e in self.graph[u]:
                    if self.cap[e] > EPS and dist[u] + self.cost[e] < dist[self.to[e]] - 1e-12:
                        dist[self.to[e]] = dist[u] + self.cost[e]
                        prev_edge[self.to[e]] = e
                        changed = True
            if not changed:
                break
        return dist[t], prev_edge

    def solve(self, s, t, required_flow):
        """Push `required_flow` from s to t at minimum cost. Returns (flow_sent, total_cost)."""
        sent, total_cost = 0.0, 0.0
        while sent < required_flow - 1e-7:
            d, prev_edge = self._cheapest_path(s, t)
            if d == float("inf"):
                break                                # no route left -> can't ship more
            # find the bottleneck (smallest spare capacity) along the path
            push, v = required_flow - sent, t
            while v != s:
                e = prev_edge[v]
                push = min(push, self.cap[e])
                v = self.to[e ^ 1]
            # push flow along the path
            v = t
            while v != s:
                e = prev_edge[v]
                self.cap[e] -= push
                self.cap[e ^ 1] += push
                v = self.to[e ^ 1]
            sent += push
            total_cost += push * d
        return sent, total_cost


def solve_network(plants, terminals, regions, lane_pt, lane_tr, demand):
    """
    Two-echelon min-cost flow.
      plants, terminals, regions : DataFrames (same columns as the CSVs)
      demand : dict region_id -> units/day
    Returns (ok, total_cost, flow_pt_df, flow_tr_df).
    """
    import pandas as pd

    P, T, R = plants.plant_id.tolist(), terminals.terminal_id.tolist(), regions.region_id.tolist()
    cap_p = dict(zip(plants.plant_id, plants.capacity_units_per_day))
    cap_t = dict(zip(terminals.terminal_id, terminals.throughput_cap_units_per_day))
    c_pt = lane_pt.set_index(["plant_id", "terminal_id"])["cost_per_unit"].to_dict()
    c_tr = lane_tr.set_index(["terminal_id", "region_id"])["cost_per_unit"].to_dict()

    # node numbering: 0=source, then plants, terminal-in, terminal-out, regions, sink
    src = 0
    p_node = {p: 1 + i for i, p in enumerate(P)}
    tin = {t: 1 + len(P) + i for i, t in enumerate(T)}
    tout = {t: 1 + len(P) + len(T) + i for i, t in enumerate(T)}
    r_node = {r: 1 + len(P) + 2 * len(T) + i for i, r in enumerate(R)}
    sink = 1 + len(P) + 2 * len(T) + len(R)

    big = sum(demand.values()) + 1.0
    net = MinCostFlow(sink + 1)
    for p in P:
        net.add_edge(src, p_node[p], cap_p[p], 0.0)              # refinery capacity
    e_pt = {(p, t): net.add_edge(p_node[p], tin[t], big, c_pt[(p, t)]) for p in P for t in T}
    for t in T:
        net.add_edge(tin[t], tout[t], cap_t[t], 0.0)             # terminal throughput cap
    e_tr = {(t, r): net.add_edge(tout[t], r_node[r], big, c_tr[(t, r)]) for t in T for r in R}
    for r in R:
        net.add_edge(r_node[r], sink, demand[r], 0.0)            # demand at each market

    required = sum(demand.values())
    sent, cost = net.solve(src, sink, required)
    if sent < required - 1e-4:
        return False, None, None, None

    rows_pt = [(p, t, net.flow_on(e), c_pt[(p, t)]) for (p, t), e in e_pt.items() if net.flow_on(e) > 1e-6]
    rows_tr = [(t, r, net.flow_on(e), c_tr[(t, r)]) for (t, r), e in e_tr.items() if net.flow_on(e) > 1e-6]
    fpt = pd.DataFrame(rows_pt, columns=["plant_id", "terminal_id", "flow_units", "cost_per_unit"])
    ftr = pd.DataFrame(rows_tr, columns=["terminal_id", "region_id", "flow_units", "cost_per_unit"])
    fpt["lane_cost"] = fpt.flow_units * fpt.cost_per_unit
    ftr["lane_cost"] = ftr.flow_units * ftr.cost_per_unit
    return True, float(cost), fpt, ftr
