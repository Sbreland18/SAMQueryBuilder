"""Import existing SQL (e.g. a query already saved in SAM) back into the builder's steps.

Understands SELECT [DISTINCT] [TOP n] columns FROM table [alias] JOIN ... ON ... WHERE ... GROUP BY ...
ORDER BY ..., UNION ALL, and common functions (LTRIM/RTRIM, UPPER, LOWER, LEFT, RIGHT, REPLACE, CONVERT(...,101/23),
CONCAT / + concatenation, ISNULL, COUNT/SUM/AVG/MIN/MAX). Anything else is kept as an exact SQL expression
("SQL expression" column or "custom SQL condition") so nothing is lost. If the statement can't be read at all
(CTEs, subqueries in FROM, HAVING...) the SQL is kept as hand-edited SQL.
"""
from __future__ import annotations

import re

from .query_model import (Condition, FilterGroup, Fmt, Link, OutColumn, Part, QueryDef, SortItem, TableRef)


def _sqlglot():
    import sqlglot
    from sqlglot import exp
    return sqlglot, exp


def import_sql(sql: str, catalog=None) -> tuple[QueryDef, list[str]]:
    notes: list[str] = []
    clean = sql.strip().rstrip(";")
    try:
        sqlglot, exp = _sqlglot()
        tree = sqlglot.parse_one(clean, read="tsql")
    except Exception as e:  # noqa: BLE001
        q = QueryDef(name="Imported query", sql_override=sql)
        notes.append(f"Couldn't read this SQL ({str(e).splitlines()[0][:150]}). It was kept exactly as written "
                     "(hand-edited SQL).")
        return q, notes
    if tree.find(exp.With) is not None or tree.args.get("having") is not None or \
            any(isinstance(f.this, exp.Subquery) for f in tree.find_all(exp.From)):
        notes.append("This SQL uses features the steps can't show (WITH, HAVING or a subquery in FROM). "
                     "It was kept exactly as written (hand-edited SQL).")
        return QueryDef(name="Imported query", sql_override=sql), notes
    order = None
    selects = []
    if isinstance(tree, exp.Union):
        order = tree.args.get("order")

        def flatten(u):
            if isinstance(u, exp.Union):
                if u.args.get("distinct"):
                    notes.append("UNION (without ALL) was imported as UNION ALL - add 'Only distinct rows' if needed.")
                flatten(u.this)
                flatten(u.expression)
            else:
                selects.append(u)
        flatten(tree)
    elif isinstance(tree, exp.Select):
        selects = [tree]
        order = tree.args.get("order")
    else:
        notes.append("Only SELECT statements can be imported.")
        return QueryDef(name="Imported query", sql_override=sql), notes

    parts = [_one_select(s, catalog, notes, i) for i, s in enumerate(selects)]
    root = parts[0]
    root.union_parts = parts[1:]
    for i, p in enumerate(root.union_parts, 2):
        p.name = f"Part {i}"
    root.name = "Imported query"
    m = re.match(r"\s*--\s*(.+)", sql)
    if m:
        root.name = m.group(1).strip()[:80]
    # ORDER BY -> headings
    if order is not None:
        heads = [c.heading for c in root.columns]
        for o in order.expressions:
            e = o.this
            name = e.name if isinstance(e, (exp.Column, exp.Identifier)) else e.sql(dialect="tsql")
            h = next((x for x in heads if x.lower() == name.lower()), None)
            if h is None and isinstance(e, exp.Column):
                h = next((c.heading for c in root.columns if c.kind == "field" and c.column.lower() == name.lower()
                          and not c.formats), None)
            if h is None and isinstance(e, exp.Literal) and e.this.isdigit() and int(e.this) <= len(heads):
                h = heads[int(e.this) - 1]
            if h:
                root.sort.append(SortItem(h, bool(o.args.get("desc"))))
            else:
                notes.append(f"ORDER BY {name} isn't one of the shown columns - add it in Step 5.")
    return root, notes


def _canon_table(name, catalog, notes):
    if catalog is None:
        return name
    if catalog.has_table(name):
        return name
    low = {t.lower(): t for t in catalog.tables}
    if name.lower() in low:
        return low[name.lower()]
    notes.append(f"Table {name} isn't in the table catalog.")
    return name


def _one_select(sel, catalog, notes, idx) -> QueryDef:
    sqlglot, exp = _sqlglot()
    q = QueryDef()
    frm = sel.args.get("from_") or sel.args.get("from")
    tables = [frm.this] if frm is not None else []
    joins = sel.args.get("joins") or []

    def add_table(t):
        name = _canon_table(t.name, catalog, notes)
        alias = t.alias_or_name
        if not any(x.alias == alias for x in q.tables):
            q.tables.append(TableRef(alias, name))
        return alias

    for t in tables:
        if isinstance(t, exp.Table):
            add_table(t)
    for j in joins:
        if not isinstance(j.this, exp.Table):
            notes.append("A join to a subquery was skipped.")
            continue
        alias = add_table(j.this)
        side = (j.args.get("side") or "").upper()
        kind = (j.args.get("kind") or "").upper()
        jt = side if side in ("LEFT", "RIGHT", "FULL") else ("INNER" if kind != "CROSS" else "INNER")
        if kind == "CROSS":
            notes.append(f"CROSS JOIN {alias} has no link - add one in Step 2.")
            continue
        on = j.args.get("on")
        conjuncts = _and_list(on, q) if on is not None else []
        link = None
        extras = []
        for c in conjuncts:
            if link is None and isinstance(c, exp.EQ) and isinstance(c.this, exp.Column) and \
                    isinstance(c.expression, exp.Column) and alias in (c.this.table, c.expression.table):
                a, b = c.this, c.expression
                if b.table == alias:
                    link = Link(a.table or q.tables[0].alias, a.name, b.table, b.name, jt)
                else:
                    flip = {"LEFT": "RIGHT", "RIGHT": "LEFT"}.get(jt, jt)
                    link = Link(b.table or q.tables[0].alias, b.name, a.table, a.name, flip)
            else:
                extras.append(_condition(c, q, notes))
        if link is None:
            notes.append(f"Couldn't find the column pair that links {alias} - set it in Step 2.")
            link = Link(q.tables[0].alias, "", alias, "", jt)
        link.conditions = [x for x in extras if x]
        q.links.append(link)

    # columns
    for i, e in enumerate(sel.expressions, 1):
        heading = e.alias if isinstance(e, exp.Alias) else None
        inner = e.this if isinstance(e, exp.Alias) else e
        if isinstance(inner, exp.Star):
            notes.append("SELECT * was skipped - pick the columns in Step 1.")
            continue
        col = _column(inner, q, notes)
        col.heading = heading or (col.column if col.kind == "field" else f"Column {i}")
        col.heading = q.unique_heading(col.heading)
        q.columns.append(col)

    # WHERE
    where = sel.args.get("where")
    if where is not None:
        all_conds = []
        for c in _and_list(where.this, q):
            if isinstance(c, exp.Paren) and _pattern(c, q) is None:
                c = c.this
            if isinstance(c, exp.Or) and _pattern(c, q) is None:
                ors = _or_list(c)
                q.filters.append(FilterGroup("ANY", [x for x in (_condition(o, q, notes) for o in ors) if x]))
            else:
                cd = _condition(c, q, notes)
                if cd:
                    all_conds.append(cd)
        if all_conds:
            q.filters.insert(0, FilterGroup("ALL", all_conds))
    if sel.args.get("distinct"):
        q.distinct = True
    lim = sel.args.get("limit")
    top = sel.args.get("top") if "top" in sel.args else None
    for node in (lim, top):
        if node is not None:
            lit = node.args.get("expression") or node.this
            if isinstance(lit, exp.Literal) and str(lit.this).isdigit():
                q.top = int(lit.this)
    return q


def _and_list(e, q=None):
    _, exp = _sqlglot()
    if isinstance(e, exp.And):
        return _and_list(e.this, q) + _and_list(e.expression, q)
    if isinstance(e, exp.Paren) and isinstance(e.this, exp.And):
        if q is not None and _pattern(e, q) is not None:
            return [e]
        return _and_list(e.this, q)
    return [e]


def _or_list(e):
    _, exp = _sqlglot()
    if isinstance(e, exp.Or):
        return _or_list(e.this) + _or_list(e.expression)
    if isinstance(e, exp.Paren):
        return _or_list(e.this)
    return [e]


def _default_alias(q, col):
    return col.table or (q.tables[0].alias if q.tables else "")


def _lit(e):
    _, exp = _sqlglot()
    if isinstance(e, exp.Literal):
        return str(e.this)
    if isinstance(e, exp.Neg) and isinstance(e.this, exp.Literal):
        return "-" + str(e.this.this)
    if isinstance(e, exp.Boolean):
        return "1" if e.this else "0"
    return None


def _col_inside(e):
    """The single column inside trim/cast wrappers, or None."""
    _, exp = _sqlglot()
    while isinstance(e, (exp.Trim, exp.Cast, exp.Paren, exp.TsOrDsToDate)):
        e = e.this
    return e if isinstance(e, exp.Column) else None


def _pattern(c, q):
    """Recognise the multi-part conditions the builder writes (blank, not blank, does not equal, last N days...)."""
    _, exp = _sqlglot()
    while isinstance(c, exp.Paren):
        c = c.this
    if isinstance(c, exp.Or):
        a, b = c.this, c.expression
        while isinstance(a, exp.Paren):
            a = a.this
        while isinstance(b, exp.Paren):
            b = b.this
        if isinstance(a, exp.Is) and isinstance(a.expression, exp.Null) and isinstance(b, exp.EQ) \
                and _lit(b.expression) == "" and _col_inside(b.this) is not None:
            col = a.this
            return Condition(_default_alias(q, col), col.name, "blank")
        if isinstance(b, exp.Is) and isinstance(b.expression, exp.Null) and isinstance(a, exp.NEQ) \
                and isinstance(a.this, exp.Column) and _lit(a.expression) is not None:
            return Condition(_default_alias(q, a.this), a.this.name, "ne", _lit(a.expression))
        if isinstance(b, exp.Is) and isinstance(b.expression, exp.Null) and isinstance(a, exp.Not) \
                and isinstance(a.this, exp.Like) and isinstance(a.this.this, exp.Column):
            v = _lit(a.this.expression) or ""
            if v.startswith("%") and v.endswith("%"):
                return Condition(_default_alias(q, a.this.this), a.this.this.name, "not_contains",
                                 v.strip("%").replace("[%]", "%").replace("[_]", "_").replace("[[]", "["))
    if isinstance(c, exp.And):
        a, b = c.this, c.expression
        if isinstance(a, exp.Not) and isinstance(a.this, exp.Is) and isinstance(b, exp.NEQ) and _lit(b.expression) == "":
            col = a.this.this
            if isinstance(col, exp.Column):
                return Condition(_default_alias(q, col), col.name, "not_blank")
    if isinstance(c, exp.GTE) and isinstance(c.this, exp.Column) and isinstance(c.expression, exp.DateAdd):
        n = c.expression.expression
        if isinstance(n, exp.Neg) and _lit(n.this) is not None:
            return Condition(_default_alias(q, c.this), c.this.name, "last_days", _lit(n.this))
    if isinstance(c, exp.EQ) and isinstance(c.expression, exp.Cast) and \
            isinstance(c.expression.this, exp.CurrentTimestamp):
        col = _col_inside(c.this)
        if col is not None:
            return Condition(_default_alias(q, col), col.name, "today")
    return None


def _condition(c, q, notes) -> Condition | None:
    _, exp = _sqlglot()
    pat = _pattern(c, q)
    if pat is not None:
        return pat
    inner = c
    while isinstance(inner, exp.Paren):     # the builder wraps raw conditions in ( ) itself
        inner = inner.this
    raw = Condition(q.tables[0].alias if q.tables else "", "", "raw", inner.sql(dialect="tsql"))
    raw.column = _first_col(c) or (q.tables and "")
    if raw.column:
        raw.alias = next((x.table for x in c.find_all(exp.Column) if x.table), raw.alias)
    neg = False
    if isinstance(c, exp.Not):
        neg, c = True, c.this
        if isinstance(c, exp.Paren):
            c = c.this
    ops = {exp.EQ: "eq", exp.NEQ: "ne", exp.GT: "gt", exp.GTE: "ge", exp.LT: "lt", exp.LTE: "le"}
    for cls, op in ops.items():
        if isinstance(c, cls) and isinstance(c.this, exp.Column) and _lit(c.expression) is not None and not neg:
            return Condition(_default_alias(q, c.this), c.this.name, op, _lit(c.expression))
    if isinstance(c, exp.In) and isinstance(c.this, exp.Column) and c.expressions and \
            all(_lit(x) is not None for x in c.expressions):
        return Condition(_default_alias(q, c.this), c.this.name, "not_in" if neg else "in",
                         ", ".join(_lit(x) for x in c.expressions))
    if isinstance(c, exp.Like) and isinstance(c.this, exp.Column) and _lit(c.expression) is not None and not neg:
        v = _lit(c.expression)
        if "_" not in v.strip("%") and "[" not in v:
            inner = v.strip("%")
            if "%" not in inner:
                if v.startswith("%") and v.endswith("%"):
                    return Condition(_default_alias(q, c.this), c.this.name, "contains", inner)
                if v.endswith("%"):
                    return Condition(_default_alias(q, c.this), c.this.name, "starts", inner)
                if v.startswith("%"):
                    return Condition(_default_alias(q, c.this), c.this.name, "ends", inner)
                return Condition(_default_alias(q, c.this), c.this.name, "eq", inner)
    if isinstance(c, exp.Between) and isinstance(c.this, exp.Column) and not neg:
        lo, hi = _lit(c.args.get("low")), _lit(c.args.get("high"))
        if lo is not None and hi is not None:
            return Condition(_default_alias(q, c.this), c.this.name, "between", lo, hi)
    if isinstance(c, exp.Is) and isinstance(c.this, exp.Column) and isinstance(c.expression, exp.Null):
        return Condition(_default_alias(q, c.this), c.this.name, "not_blank" if neg else "blank")
    if not raw.column:
        notes.append(f"Condition kept as custom SQL: {raw.value[:80]}")
        raw.column = "(custom)"
    return raw


def _first_col(e):
    _, exp = _sqlglot()
    c = next(e.find_all(exp.Column), None)
    return c.name if c is not None else None


def _column(e, q, notes) -> OutColumn:
    """Turn a SELECT expression into a field / custom / SQL-expression column."""
    _, exp = _sqlglot()
    agg = ""
    aggs = {exp.Count: "count", exp.Sum: "sum", exp.Avg: "avg", exp.Min: "min", exp.Max: "max"}
    for cls, name in aggs.items():
        if isinstance(e, cls):
            inner = e.this
            if isinstance(inner, exp.Distinct):
                agg, inner = "count_distinct", inner.expressions[0]
            else:
                agg = name
            if isinstance(inner, exp.Star) or inner is None:
                return OutColumn("custom", heading="", agg="count")
            col = _column(inner, q, notes)
            col.agg = agg
            return col
    parts = _concat_parts(e, q)
    if parts is not None:
        pieces = []
        for p in parts:
            if isinstance(p, exp.Literal) and p.is_string:
                pieces.append(Part("text", value=str(p.this)))
            else:
                f = _field(p, q)
                if f is None:
                    return _raw(e, q, notes)
                pieces.append(Part("field", f[0], f[1], formats=f[2]))
        return OutColumn("custom", parts=pieces)
    f = _field(e, q)
    if f is not None:
        return OutColumn("field", f[0], f[1], formats=f[2])
    if isinstance(e, exp.Literal):
        return OutColumn("custom", parts=[Part("text", value=str(e.this))])
    return _raw(e, q, notes)


def _raw(e, q, notes):
    while isinstance(e, _sqlglot()[1].Paren):   # the builder wraps raw expressions in ( ) itself
        e = e.this
    if isinstance(e, _sqlglot()[1].Subquery) and not e.alias:   # (SELECT ...) -> SELECT ...; the ( ) come back
        e = e.this
    sql = e.sql(dialect="tsql")
    notes.append(f"Column kept as an exact SQL expression: {sql[:80]}")
    alias = next((c.table for c in e.find_all(_sqlglot()[1].Column) if c.table), q.tables[0].alias if q.tables else "")
    return OutColumn("raw", alias=alias, column=sql)


def _concat_parts(e, q):
    _, exp = _sqlglot()
    if isinstance(e, (exp.Concat, exp.ConcatWs)) and not isinstance(e, exp.ConcatWs):
        return list(e.expressions)
    if isinstance(e, exp.Add) and (_has_string(e)):
        out = []

        def walk(x):
            if isinstance(x, exp.Add):
                walk(x.this)
                walk(x.expression)
            else:
                out.append(x)
        walk(e)
        return out
    return None


def _has_string(e):
    _, exp = _sqlglot()
    return any(isinstance(x, exp.Literal) and x.is_string for x in e.find_all(exp.Literal))


def _field(e, q):
    """Column wrapped in known functions -> (alias, column, [Fmt...]) or None."""
    _, exp = _sqlglot()
    fmts = []
    while True:
        if isinstance(e, exp.Column):
            return _default_alias(q, e), e.name, list(reversed(fmts))
        if isinstance(e, exp.Paren):
            e = e.this
            continue
        if isinstance(e, (exp.Cast, exp.TsOrDsToDate)):
            e = e.this
            continue
        if isinstance(e, exp.Trim):
            inner = e.this
            if isinstance(inner, exp.Trim):
                fmts.append(Fmt("trim"))
                e = inner.this
            else:
                fmts.append(Fmt("trim"))
                e = inner
            continue
        if isinstance(e, exp.Upper):
            fmts.append(Fmt("upper"))
            e = e.this
            continue
        if isinstance(e, exp.Lower):
            fmts.append(Fmt("lower"))
            e = e.this
            continue
        if isinstance(e, (exp.Left, exp.Right)) and _lit(e.expression) is not None:
            fmts.append(Fmt("left" if isinstance(e, exp.Left) else "right", _lit(e.expression)))
            e = e.this
            continue
        if isinstance(e, exp.Replace) and _lit(e.expression) is not None:
            rep = e.args.get("replacement")
            fmts.append(Fmt("replace", _lit(e.expression), _lit(rep) if rep is not None else ""))
            e = e.this
            continue
        if isinstance(e, exp.Convert) and e.args.get("style") is not None:
            style = _lit(e.args["style"])
            if style in ("101", "23"):
                fmts.append(Fmt("date_us" if style == "101" else "date_iso"))
                e = e.expression
                continue
            return None
        if isinstance(e, exp.Coalesce) and len(e.expressions) == 1 and _lit(e.expressions[0]) is not None:
            fmts.append(Fmt("if_blank", _lit(e.expressions[0])))
            e = e.this
            continue
        if isinstance(e, exp.Year):
            fmts.append(Fmt("year"))
            e = e.this
            continue
        # ---- patterns the builder itself writes ----
        if isinstance(e, exp.Substring) and "PATINDEX('%[^0]%'" in e.sql(dialect="tsql").upper().replace(
                "PATINDEX('%[^0]%'", "PATINDEX('%[^0]%'"):
            fmts.append(Fmt("strip_zeros"))
            e = e.this
            continue
        if isinstance(e, exp.Case) and e.args.get("this") is None and len(e.args.get("ifs") or []) == 1:
            cond = e.args["ifs"][0].this
            t_val = _lit(e.args["ifs"][0].args.get("true"))
            d_val = _lit(e.args.get("default")) if e.args.get("default") is not None else None
            if isinstance(cond, exp.In) and t_val == "Yes" and d_val == "No":
                fmts.append(Fmt("yes_no"))
                e = cond.this
                continue
            return None
        if isinstance(e, exp.Case) and e.args.get("this") is not None:
            pairs = []
            for i in e.args.get("ifs") or []:
                k, v = _lit(i.this), _lit(i.args.get("true"))
                if k is None or v is None:
                    return None
                pairs.append(f"{k}={v}")
            dflt = e.args.get("default")
            subject = e.args["this"]
            if dflt is not None and dflt.sql() != subject.sql():
                return None
            fmts.append(Fmt("map", "; ".join(pairs)))
            e = subject
            continue
        if isinstance(e, exp.Round) and _lit(e.args.get("decimals")) is not None:
            fmts.append(Fmt("decimals", _lit(e.args.get("decimals"))))
            e = e.this
            continue
        if isinstance(e, exp.Coalesce) and len(e.expressions) == 1 and isinstance(e.this, exp.Nullif):
            fmts.append(Fmt("if_blank", _lit(e.expressions[0]) or ""))
            e = e.this.this
            continue
        return None
