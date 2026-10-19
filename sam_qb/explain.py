"""'Explain this query' - describe a query in plain English: what it lists, which rows it includes or leaves
out, and how the tables connect. Works for queries built in the steps and for imported SQL."""
from __future__ import annotations

import html as _h

from .query_model import AGGREGATES, OPERATORS, QueryDef


def _friendly(catalog, q: QueryDef, alias: str) -> str:
    t = q.alias_table(alias) if alias else ""
    name = catalog.friendly(t) if (catalog and t) else (t or alias)
    return f"{name} (as {alias})" if t and alias != t else name


def _col(catalog, q, alias, column) -> str:
    note = catalog.column_note(q.alias_table(alias) or alias, column) if catalog else ""
    return f"{alias}.{column}" + (f" - {note}" if note else "")


def _cond(c, q, catalog) -> str:
    if c.op == "raw":
        return f"custom SQL: {c.value}"
    label = OPERATORS.get(c.op, (c.op, 1))[0].replace(" (comma separated)", "")
    who = f"{c.alias}.{c.column}"
    if c.op == "between":
        return f"{who} is between {c.value} and {c.value2}"
    if OPERATORS.get(c.op, ("", 1))[1] == 0:
        return f"{who} {label}"
    ask = f" (asked for when copying: \"{c.ask}\")" if getattr(c, "ask", "") else ""
    if c.op == "last_days":
        return f"{who} is within the last {c.value} days{ask}"
    return f"{who} {label} {c.value}{ask}"


def _column_text(c, q, catalog) -> str:
    agg = f"{AGGREGATES.get(c.agg, c.agg).lower()} of " if c.agg else ""
    if c.kind == "field":
        src = _col(catalog, q, c.alias, c.column)
    elif c.kind == "raw":
        src = "a calculated value (custom SQL)"
    else:
        bits = []
        for p in c.parts:
            if p.kind == "text":
                bits.append(f"'{p.value}'")
            elif p.kind == "sql":
                bits.append("a calculated piece")
            else:
                bits.append(f"{p.alias}.{p.column}")
        src = " + ".join(bits) if bits else ("a count of rows" if c.agg == "count" else "nothing yet")
    fmts = [f.type.replace("_", " ") for f in c.formats]
    return f"<b>{_h.escape(c.heading or c.column)}</b>: {_h.escape(agg + src)}" + \
           (f" <i>(formatted: {_h.escape(', '.join(fmts))})</i>" if fmts else "")


def explain(q: QueryDef, catalog=None) -> list[tuple[str, list[str]]]:
    """[(section title, [html lines])]"""
    out = []
    if q.sql_override.strip():
        out.append(("Note", ["This query's SQL was edited by hand, so the description below is of the steps, "
                             "not of the edited SQL."]))
    if not q.tables:
        return out + [("What it lists", ["Nothing yet - no tables are chosen."])]
    root = q.tables[0].alias
    has_agg = any(c.agg for c in q.columns)
    one = f"One row for each record in {_friendly(catalog, q, root)}"
    lines = []
    if has_agg:
        groups = [c.heading for c in q.columns if not c.agg]
        lines.append("Totals " + (f"for each {', '.join(groups)}" if groups else "for everything that matches") + ".")
    else:
        try:
            from .dupcheck import analyze
            many = [f for f in analyze(q, catalog) if f["kind"] in ("one_to_many", "cross")]
        except Exception:
            many = []
        if many:
            lines.append(one + ", repeated for each matching record in " + " and ".join(
                _friendly(catalog, q, f["alias"]) for f in many) + ".")
        else:
            lines.append(one + ".")
    if q.distinct:
        lines.append("Exact duplicate rows are removed.")
    if q.top:
        lines.append(f"Only the first {q.top:,} rows are shown.")
    out.append(("What it lists", lines))
    out.append(("Columns", [_column_text(c, q, catalog) for c in q.columns] or ["No columns yet."]))
    tl = []
    for l in q.links:
        a, b = _friendly(catalog, q, l.left_alias), _friendly(catalog, q, l.right_alias)
        how = f"{a} linked to {b} on {l.left_alias}.{l.left_col} = {l.right_alias}.{l.right_col}"
        if l.join == "LEFT":
            how += f" - {a} rows are kept even when there is no match"
        elif l.join == "INNER":
            how += f" - rows with no matching {b} are left out"
        if l.conditions:
            how += "; only where " + "; ".join(_cond(c, q, catalog) for c in l.conditions)
        tl.append(_h.escape(how[0].upper() + how[1:]) + ".")
    if tl:
        out.append(("How the tables connect", tl))
    fl = []
    for g in q.filters:
        conds = [_cond(c, q, catalog) for c in g.conditions]
        if not conds:
            continue
        joiner = " AND " if g.match == "ALL" else " OR "
        fl.append(_h.escape(("All of: " if g.match == "ALL" and len(conds) > 1 else
                             "Any of: " if len(conds) > 1 else "") + joiner.join(conds)))
    if fl:
        mode = "every group must match" if q.filter_mode == "ALL" else "any group may match"
        out.append(("Which rows are included" + (f" ({mode})" if len(fl) > 1 else ""), fl))
    else:
        out.append(("Which rows are included", ["Every row - there are no filters, so withdrawn students, "
                                                "terminated staff and past years may be included."]))
    if q.sort:
        out.append(("Order", [_h.escape(", ".join(s.heading + (" (largest/latest first)" if s.desc else "")
                                                  for s in q.sort))]))
    for i, p in enumerate(q.union_parts, 2):
        out.append((f"Combined part {i}", [f"<b>{_h.escape(p.name)}</b> - its rows are added below the first "
                                          f"part's ({len(p.columns)} columns, {len(p.tables)} tables)."]))
    return out


def explain_html(q: QueryDef, catalog=None) -> str:
    parts = []
    for title, lines in explain(q, catalog):
        items = "".join(f"<li>{x}</li>" for x in lines)
        parts.append(f"<p style='margin:6px 0 2px 0'><b>{_h.escape(title)}</b></p><ul style='margin-top:0'>{items}</ul>")
    return "".join(parts)


def explain_text(q: QueryDef, catalog=None) -> str:
    import re
    out = []
    for title, lines in explain(q, catalog):
        out.append(title.upper())
        out += ["  - " + _h.unescape(re.sub(r"<[^>]+>", "", x)) for x in lines]
        out.append("")
    return "\n".join(out)
