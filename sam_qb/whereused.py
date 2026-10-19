"""'Where is this field used?' - every export package, saved query and template that reads a SAM column, and which
vendors in use receive it."""
from __future__ import annotations

import json
import re

from .query_model import QueryDef


def _uses(q: QueryDef, table: str, column: str) -> list[str]:
    """Where in the query the column is used: 'shown as <heading>', 'filter', 'link'."""
    out = []
    alias_tables = {t.alias: t.table for t in q.tables}
    aliases = {a for a, t in alias_tables.items() if t.lower() == table.lower()}
    rx = re.compile(rf"\b({'|'.join(map(re.escape, aliases | {table}))})\.\[?{re.escape(column)}\]?\b", re.I) \
        if aliases or table else None
    col = column.lower()
    for c in q.columns:
        hit = (c.kind == "field" and c.alias in aliases and c.column.lower() == col) or \
              any(p.kind == "field" and p.alias in aliases and p.column.lower() == col for p in c.parts) or \
              (c.kind == "raw" and rx and rx.search(c.column)) or \
              any(p.kind == "sql" and rx and rx.search(p.value) for p in c.parts)
        if hit:
            out.append(f"shown as '{c.heading or c.column}'")
    for g in q.filters:
        for c in g.conditions:
            if (c.alias in aliases and c.column.lower() == col) or (c.op == "raw" and rx and rx.search(c.value)):
                out.append("filter")
                break
    for l in q.links:
        if (l.left_alias in aliases and l.left_col.lower() == col) or (l.right_alias in aliases and
                                                                        l.right_col.lower() == col):
            out.append("link")
        elif any((c.alias in aliases and c.column.lower() == col) for c in l.conditions):
            out.append("link condition")
    for p in q.union_parts:
        out += [u + f" (part '{p.name}')" for u in _uses(p, table, column)]
    return list(dict.fromkeys(out))


def find(table: str, column: str, settings: dict) -> dict:
    """{'packages': [...], 'queries': [...], 'templates': [...], 'vendors_in_use': [...]}"""
    from .exports import build_query, load_platforms
    from .register import in_use_ids
    res = {"packages": [], "queries": [], "templates": [], "vendors_in_use": []}
    in_use = in_use_ids(settings)
    for p in load_platforms():
        hits = []
        for fe in p.get("files", []):
            try:
                q = build_query(p, fe, settings)
            except Exception:
                continue
            u = _uses(q, table, column)
            if u:
                hits.append({"file": fe["file"], "how": u})
        if hits:
            res["packages"].append({"id": p["id"], "name": p["name"], "in_use": p["id"] in in_use,
                                    "kind": p.get("kind", ""), "files": hits})
            if p["id"] in in_use and p.get("kind") != "tool":
                res["vendors_in_use"].append(p["name"])
    res["packages"].sort(key=lambda p: (not p["in_use"], p["name"].lower()))
    from .paths import queries_dir
    for f in sorted(queries_dir().glob("*.samq")):
        try:
            q = QueryDef.from_dict(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
        u = _uses(q, table, column)
        if u:
            res["queries"].append({"name": q.name or f.stem, "path": str(f), "how": u})
    try:
        from .paths import active_data_file
        for t in json.loads(active_data_file("templates.json").read_text(encoding="utf-8")).get("templates", []):
            u = _uses(QueryDef.from_dict(t), table, column)
            if u:
                res["templates"].append({"name": t.get("name", ""), "how": u})
    except Exception:
        pass
    return res
