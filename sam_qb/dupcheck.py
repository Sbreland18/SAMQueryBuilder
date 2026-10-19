"""Duplicate-row warning: spot links that repeat the main record (e.g. one row per contact or phone number)
before a file goes to a vendor.

A link from table A to table B is 'one-to-one' when B's column is B's key (or the 'one' side of a known
relationship). Otherwise each A row can match several B rows - unless a condition narrows it to one
(PrimaryContact = 1, LiveFlag = 1, a sequence number...)."""
from __future__ import annotations

import re

from .query_model import QueryDef

NARROW = re.compile(r"primary|sequence|seq$|seqno|liveflag|isfinal|current|default|^active", re.I)


def _is_key(catalog, table: str, column: str) -> bool:
    if not table:
        return False
    col = column.lower()
    cols = catalog.columns(table) if catalog else []
    if cols and cols[0].lower() == col and col.endswith("id"):
        return True                                     # first column is the table's own ID
    if table.lower().startswith("lookup") and col in ("val", "luid"):
        return True
    if catalog:
        for r in catalog.relationships:
            if r["to_table"] == table and r["to_col"].lower() == col:
                return True                             # the 'one' side of a known relationship
    base = re.sub(r"(info|def)$", "", table.lower())
    return col == f"{base}id" or col == f"{table.lower()}id"


def _narrowed(q: QueryDef, link, alias: str) -> bool:
    conds = list(link.conditions)
    for g in q.filters:
        if g.match == "ALL" and (q.filter_mode == "ALL" or len(q.filters) == 1):
            conds += g.conditions
    for c in conds:
        if c.alias == alias and c.op in ("eq", "today") and NARROW.search(c.column or ""):
            return True
        if c.op == "raw" and re.search(rf"\b{re.escape(alias)}\.", c.value or "") and \
                re.search(r"primary|seq|liveflag", c.value or "", re.I):
            return True
        if c.op == "raw" and re.search(r"\b(TOP\s+1|MAX\(|MIN\()", c.value or "", re.I) and alias in (c.value or ""):
            return True
    return False


def analyze(q: QueryDef, catalog=None) -> list[dict]:
    """[{'kind': 'one_to_many'|'cross'|'hidden_many', 'alias', 'parent', 'shown', 'message'}]"""
    if not q.tables or q.sql_override.strip():
        return []
    root = q.tables[0].alias
    adj = {}
    for l in q.links:
        adj.setdefault(l.left_alias, []).append((l, l.left_alias, l.right_alias, l.right_col))
        adj.setdefault(l.right_alias, []).append((l, l.right_alias, l.left_alias, l.left_col))
    shown = set()
    for c in q.columns:
        if c.kind == "field":
            shown.add(c.alias)
        shown |= {p.alias for p in c.parts if p.kind == "field"}
    seen, order, many = {root}, [root], {}
    parent = {}
    i = 0
    while i < len(order):
        a = order[i]
        i += 1
        for l, frm, to, to_col in adj.get(a, []):
            if to in seen:
                continue
            seen.add(to)
            order.append(to)
            parent[to] = frm
            t = q.alias_table(to)
            if not _is_key(catalog, t, to_col) and not _narrowed(q, l, to):
                many[to] = frm

    def subtree_shown(alias):
        kids = [x for x, p in parent.items() if p == alias]
        return alias in shown or any(subtree_shown(k) for k in kids)

    out = []
    fr = lambda al: (catalog.friendly(q.alias_table(al)) if catalog else q.alias_table(al)) or al  # noqa: E731
    for alias, par in many.items():
        if subtree_shown(alias):
            out.append({"kind": "one_to_many", "alias": alias, "parent": par, "shown": True,
                        "message": f"Each {fr(par)} can appear once per {fr(alias)} - expected if you want one row "
                                   f"per {fr(alias)}."})
        else:
            out.append({"kind": "hidden_many", "alias": alias, "parent": par, "shown": False,
                        "message": f"{fr(alias)} ({alias}) is linked but none of its columns are shown, so each "
                                   f"{fr(par)} may repeat with identical rows. Add a condition such as a Primary flag "
                                   f"on the link, or turn on 'Remove duplicate rows' in Step 5."})
    # two independent one-to-many branches multiply each other (e.g. contacts x classes)
    branches = {}
    for alias in many:
        top = alias
        while parent.get(top) in many:
            top = parent[top]
        branches.setdefault(parent.get(top, root), []).append(top)
    for par, tops in branches.items():
        tops = sorted(set(tops))
        if len(tops) > 1:
            names = " and ".join(f"{fr(t)} ({t})" for t in tops)
            out.append({"kind": "cross", "alias": tops[0], "parent": par, "shown": True,
                        "message": f"{names} both have several rows per {fr(par)}, so they multiply: every "
                                   f"combination becomes its own row. Usually you want separate files, or a "
                                   f"condition that keeps one row of each."})
    return out


def warnings(q: QueryDef, catalog=None) -> list[str]:
    """Messages for the Review step (DISTINCT queries only get the 'cross' warning)."""
    found = analyze(q, catalog)
    out = []
    for f in found:
        if f["kind"] == "hidden_many" and not q.distinct:
            out.append("Duplicate rows: " + f["message"])
        elif f["kind"] == "cross":
            out.append("Duplicate rows: " + f["message"])
    for p in q.union_parts:
        out += [w + f" (part '{p.name}')" for w in warnings(p, catalog)]
    return out


def info(q: QueryDef, catalog=None) -> list[str]:
    return [f["message"] for f in analyze(q, catalog) if f["kind"] == "one_to_many"]


def repeated_keys(headings: list, rows: list) -> tuple[str, int]:
    """For a result: (ID-like column, how many of its values repeat) - shown under the preview."""
    if not headings or not rows:
        return "", 0
    idx = next((i for i, h in enumerate(headings) if re.search(r"(student|staff|employee|person|user).*id$|^id$|"
                                                              r"sourcedid|_id$|number$", str(h), re.I)), None)
    if idx is None:
        return "", 0
    seen, dup = set(), 0
    for r in rows:
        v = r[idx] if idx < len(r) else None
        if v in (None, ""):
            continue
        if v in seen:
            dup += 1
        seen.add(v)
    return str(headings[idx]), dup
