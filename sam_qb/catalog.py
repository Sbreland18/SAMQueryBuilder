"""Runtime table catalog with link (join) path finding."""
from __future__ import annotations

import heapq
import json
from collections import defaultdict
from pathlib import Path

from .paths import active_data_file
from .query_model import Link, QueryDef


class Catalog:
    def __init__(self, data: dict, source: Path | None = None):
        self.source = source
        self.data_version = data.get("data_version", "0")
        self.tables: dict[str, dict] = data.get("tables", {})
        self._lower = {k.lower(): k for k in self.tables}
        self.column_notes: dict[str, str] = data.get("column_notes", {})
        self.sensitive_columns: list[str] = data.get("sensitive_columns", [])
        self.common_tables: list[str] = data.get("common_tables", [])
        self.relationships: list[dict] = data.get("relationships", [])
        self.adj: dict[str, list[tuple]] = defaultdict(list)
        for r in self.relationships:
            self.adj[r["from_table"]].append((r["to_table"], r))
            self.adj[r["to_table"]].append((r["from_table"], r))

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Catalog":
        p = Path(path) if path else active_data_file("catalog.json")
        return cls(json.loads(p.read_text(encoding="utf-8")), p)

    # ---------------------------------------------------------------- lookups
    def has_table(self, name: str) -> bool:
        return name in self.tables

    def columns(self, table: str) -> list[str]:
        return self.tables.get(table, {}).get("columns", [])

    def friendly(self, table: str) -> str:
        return self.tables.get(table, {}).get("friendly", table)

    def description(self, table: str) -> str:
        return self.tables.get(table, {}).get("description", "")

    def column_note(self, table: str, column: str) -> str:
        return self.column_notes.get(f"{table}.{column}", "")

    def is_sensitive(self, column: str) -> bool:
        return column.lower() in {s.lower() for s in self.sensitive_columns}

    def categories(self, include_hidden=False) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for name, t in self.tables.items():
            if t.get("hidden") and not include_hidden:
                continue
            out[t.get("category", "Other")].append(name)
        for v in out.values():
            v.sort(key=str.lower)
        return dict(sorted(out.items()))

    def search(self, text: str, include_hidden=False) -> list[tuple[str, str]]:
        """Returns (table, matched column or '') pairs."""
        text = text.lower().strip()
        res = []
        if not text:
            return res
        for name, t in self.tables.items():
            if t.get("hidden") and not include_hidden:
                continue
            if text in name.lower() or text in t.get("friendly", "").lower() or text in t.get("description", "").lower():
                res.append((name, ""))
            for c in t["columns"]:
                if text in c.lower():
                    res.append((name, c))
        return res

    def links_between(self, a: str, b: str) -> list[dict]:
        return [r for (n, r) in self.adj.get(a, []) if n == b]

    # ---------------------------------------------------------------- path finding
    @staticmethod
    def _rkey(r):
        return (r["from_table"], r["from_col"].lower(), r["to_table"], r["to_col"].lower())

    def shortest_path(self, start: str, targets: set[str], used: set | None = None) -> list[tuple[str, dict]] | None:
        """Dijkstra from start to any table in targets. Returns list of (next_table, relationship).
        Relationships in `used` (already in the query) cost more, so a second copy of a table
        (e.g. Employee as Counselor) gets a different link than the first copy."""
        used = used or set()
        if start in targets:
            return []
        dist = {start: 0}
        prev: dict[str, tuple[str, dict]] = {}
        heap = [(0, start)]
        while heap:
            d, node = heapq.heappop(heap)
            if node in targets:
                path = []
                while node != start:
                    p, r = prev[node]
                    path.append((node, r))
                    node = p
                return list(reversed(path))
            if d > dist.get(node, 1e9):
                continue
            for nxt, r in self.adj.get(node, []):
                info = self.tables.get(nxt, {})
                is_target = nxt in targets
                # never route *through* lookup or hidden tables
                if not is_target and (info.get("hidden") or info.get("category") == "Lookup (code) tables"):
                    continue
                nd = d + r.get("weight", 2) + (0 if info.get("common") or is_target else 2) \
                    + (6 if self._rkey(r) in used else 0)
                if nd < dist.get(nxt, 1e9):
                    dist[nxt] = nd
                    prev[nxt] = (node, r)
                    heapq.heappush(heap, (nd, nxt))
        return None

    def suggest_links(self, q: QueryDef, add_tables: bool = True) -> tuple[list[Link], list[str], list[str]]:
        """Propose links so every table in q is connected.

        Returns (new_links, added_aliases, problems). Does not modify q unless add_tables
        is True, in which case bridging tables are added to q.tables.
        """
        new_links: list[Link] = []
        added: list[str] = []
        problems: list[str] = []
        if len(q.tables) < 2:
            return new_links, added, problems

        # union-find over aliases using existing links
        parent = {t.alias: t.alias for t in q.tables}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            parent[find(a)] = find(b)

        for l in q.links:
            if l.left_alias in parent and l.right_alias in parent:
                union(l.left_alias, l.right_alias)

        anchor = q.tables[0].alias
        for tref in list(q.tables[1:]):
            if find(tref.alias) == find(anchor):
                continue
            connected_aliases = [a for a in parent if find(a) == find(anchor)]
            table_to_alias = {}
            for a in connected_aliases:
                table_to_alias.setdefault(q.alias_table(a), a)
            targets = set(table_to_alias) - {tref.table}
            used = set()
            for l in q.links:
                lt, rt = q.alias_table(l.left_alias), q.alias_table(l.right_alias)
                used.add((lt, l.left_col.lower(), rt, l.right_col.lower()))
                used.add((rt, l.right_col.lower(), lt, l.left_col.lower()))
            path = self.shortest_path(tref.table, targets, used) if targets else None
            if path is None:
                problems.append(f"No known link from {tref.table} to the other tables. Add a link by hand.")
                continue
            cur_alias, cur_table = tref.alias, tref.table
            for nxt_table, r in path:
                if nxt_table in table_to_alias:
                    nxt_alias = table_to_alias[nxt_table]
                else:
                    existing = next((t.alias for t in q.tables if t.table == nxt_table), None)
                    if existing:
                        nxt_alias = existing
                    elif add_tables:
                        nxt_alias = q.add_table(nxt_table)
                        parent[nxt_alias] = nxt_alias
                        added.append(nxt_alias)
                    else:
                        problems.append(f"{tref.table} needs bridging table {nxt_table}.")
                        break
                link = _rel_to_link(r, nxt_alias, nxt_table, cur_alias, cur_table)
                new_links.append(link)
                q.links.append(link)
                union(cur_alias, nxt_alias)
                cur_alias, cur_table = nxt_alias, nxt_table
        return new_links, added, problems


def _rel_to_link(r: dict, a_alias, a_table, b_alias, b_table) -> Link:
    jt = "LEFT" if r.get("lookup") else "INNER"
    if r["from_table"] == a_table and r["to_table"] == b_table:
        return Link(a_alias, r["from_col"], b_alias, r["to_col"], jt)
    # relationship is stored the other way round: keep the "main" table on the left
    if r.get("lookup"):
        return Link(b_alias, r["from_col"], a_alias, r["to_col"], jt)
    return Link(a_alias, r["to_col"], b_alias, r["from_col"], jt)
