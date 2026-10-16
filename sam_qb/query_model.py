"""Query definition model and T-SQL generator for SAM Ad Hoc Query Builder.

Everything here is plain Python (no Qt) so it can be unit tested and reused.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime

JOIN_TYPES = {
    "INNER": ("Inner Link", "INNER JOIN", "Only rows that match on both sides (most common)."),
    "LEFT": ("Left Link", "LEFT JOIN", "All rows from the left table; matching rows from the right when they exist."),
    "RIGHT": ("Right Link", "RIGHT JOIN", "All rows from the right table; matching rows from the left when they exist."),
    "FULL": ("Full Outer Link", "FULL OUTER JOIN", "All rows from both tables, matched when possible."),
}

# --------------------------------------------------------------------------- formats
# key: (label, needs_a, needs_b, help)
FORMATS = {
    "trim": ("Trim spaces", None, None, "Removes leading and trailing spaces."),
    "upper": ("UPPER CASE", None, None, "Converts text to upper case."),
    "lower": ("lower case", None, None, "Converts text to lower case."),
    "proper_first": ("Capitalize first letter", None, None, "Upper-cases the first letter, lower-cases the rest."),
    "left": ("Left (first N characters)", "Number of characters", None, "Keeps the first N characters. Left 1 = first initial."),
    "right": ("Right (last N characters)", "Number of characters", None, "Keeps the last N characters."),
    "replace": ("Replace text", "Find", "Replace with", "Replaces every occurrence of Find with Replace with. Leave Replace with blank to delete it; type a single space to find spaces."),
    "remove_spaces": ("Remove all spaces", None, None, "Deletes every space (e.g. for building usernames)."),
    "strip_zeros": ("Remove leading zeros", None, None, "0001234 becomes 1234 (common for State Code)."),
    "pad_zeros": ("Pad with leading zeros", "Total length", None, "1234 with length 7 becomes 0001234."),
    "prefix": ("Add text before", "Text", None, "Adds text in front of the value."),
    "suffix": ("Add text after", "Text", None, "Adds text after the value (e.g. @district.k12.ms.us)."),
    "if_blank": ("If blank, show", "Text", None, "Shows this text when the value is empty or NULL."),
    "date_us": ("Date as MM/DD/YYYY", None, None, "Formats a date like 08/15/2026."),
    "date_iso": ("Date as YYYY-MM-DD", None, None, "Formats a date like 2026-08-15."),
    "age": ("Age in years (from a date)", None, None, "Calculates age today from a birth date."),
    "yes_no": ("1/0 as Yes/No", None, None, "Shows Yes when the value is 1/True, otherwise No."),
    "decimals": ("Round to N decimals", "Decimal places", None, "Rounds a number, e.g. GPA to 2 decimals."),
    "map": ("Translate values", "Pairs, e.g. KG=Kindergarten; 01=1", None,
            "Changes codes to the values another system expects. Separate pairs with ; - values not listed are kept as they are."),
    "year": ("Year from a date", None, None, "Keeps only the 4-digit year of a date (e.g. school year end)."),
}


def parse_map(text: str) -> list[tuple[str, str]]:
    pairs = []
    for chunk in str(text).split(";"):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            pairs.append((k.strip(), v.strip()))
    return pairs

OPERATORS = {
    "eq": ("equals", 1), "ne": ("does not equal", 1),
    "contains": ("contains", 1), "not_contains": ("does not contain", 1),
    "starts": ("starts with", 1), "ends": ("ends with", 1),
    "gt": ("is greater than", 1), "ge": ("is greater than or equal to", 1),
    "lt": ("is less than", 1), "le": ("is less than or equal to", 1),
    "between": ("is between", 2),
    "in": ("is one of (comma separated)", 1), "not_in": ("is not one of (comma separated)", 1),
    "blank": ("is blank / empty", 0), "not_blank": ("is not blank", 0),
    "last_days": ("is within the last N days", 1),
    "today": ("is today", 0),
    "raw": ("custom SQL condition", 1),
}

RESERVED = {"user", "group", "order", "table", "key", "index", "view", "select", "from", "where", "by",
            "desc", "asc", "date", "time", "file", "plan", "percent", "public", "rule", "schema",
            "session", "status", "type", "value", "values", "column", "default", "function", "level",
            # general SQL keywords (T-SQL and SQLite) so any column name is always safe
            "add", "all", "alter", "and", "any", "as", "between", "case", "check", "constraint", "create",
            "cross", "current", "database", "delete", "distinct", "drop", "else", "end", "escape", "except",
            "exists", "foreign", "full", "having", "in", "inner", "insert", "intersect", "into", "is", "join",
            "left", "like", "limit", "natural", "not", "null", "of", "offset", "on", "or", "outer", "primary",
            "references", "right", "rowid", "set", "then", "to", "transaction", "union", "unique", "update",
            "using", "when", "with", "identity", "open", "close", "fetch", "grant", "top", "tran", "begin",
            "backup", "bulk", "cursor", "deny", "exec", "execute", "external", "file", "fill", "go",
            "holdlock", "kill", "national", "nocheck", "off", "option", "over", "pivot", "print", "proc",
            "procedure", "read", "restore", "return", "revoke", "rule", "save", "some", "statistics",
            "trigger", "truncate", "user", "waitfor", "while"}


def ident(name: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) and name.lower() not in RESERVED:
        return name
    return "[" + name.replace("]", "]]") + "]"


def heading_ident(h: str) -> str:
    return "[" + h.replace("]", "]]") + "]"


def sql_str(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def like_escape(v: str) -> str:
    return str(v).replace("'", "''").replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")


# --------------------------------------------------------------------------- dataclasses
@dataclass
class TableRef:
    alias: str
    table: str


@dataclass
class Link:
    left_alias: str
    left_col: str
    right_alias: str
    right_col: str
    join: str = "INNER"
    conditions: list = field(default_factory=list)   # extra ON conditions (list[Condition])


@dataclass
class Fmt:
    type: str
    a: str = ""
    b: str = ""


@dataclass
class Part:
    kind: str = "field"          # field | text | sql (exact SQL expression in .value, e.g. a duplicate number)
    alias: str = ""
    column: str = ""
    value: str = ""
    formats: list = field(default_factory=list)


@dataclass
class OutColumn:
    kind: str = "field"          # field | custom | raw (exact SQL expression in .column)
    alias: str = ""
    column: str = ""
    heading: str = ""
    formats: list = field(default_factory=list)   # list[Fmt]
    parts: list = field(default_factory=list)     # list[Part] for custom
    agg: str = ""                                 # "" | count | count_distinct | sum | avg | min | max


AGGREGATES = {"": "Show each value", "count": "Count of rows", "count_distinct": "Count of different values",
              "sum": "Total (sum)", "avg": "Average", "min": "Smallest / earliest", "max": "Largest / latest"}


def agg_sql(c: "OutColumn", expr: str) -> str:
    """Wrap an expression in its aggregate. A custom column with no pieces + count = COUNT(*)."""
    a = c.agg
    if not a:
        return expr
    if a == "count":
        return "COUNT(*)" if (c.kind == "custom" and not c.parts) else f"COUNT({expr})"
    if a == "count_distinct":
        return f"COUNT(DISTINCT {expr})"
    if a == "avg":
        return f"AVG(CAST({expr} AS float))"
    return f"{a.upper()}({expr})"


@dataclass
class Condition:
    alias: str = ""
    column: str = ""
    op: str = "eq"
    value: str = ""
    value2: str = ""


@dataclass
class FilterGroup:
    match: str = "ALL"           # ALL | ANY
    conditions: list = field(default_factory=list)


@dataclass
class SortItem:
    heading: str
    desc: bool = False


@dataclass
class QueryDef:
    name: str = "New Query"
    description: str = ""
    tables: list = field(default_factory=list)
    links: list = field(default_factory=list)
    columns: list = field(default_factory=list)
    filters: list = field(default_factory=list)
    filter_mode: str = "ALL"     # how groups combine
    sort: list = field(default_factory=list)
    distinct: bool = False
    top: int = 0
    sql_override: str = ""
    created: str = ""
    modified: str = ""
    category: str = ""
    union_parts: list = field(default_factory=list)   # list[QueryDef] combined with UNION ALL

    # ------------------------------------------------------------------ helpers
    def alias_table(self, alias: str) -> str | None:
        for t in self.tables:
            if t.alias == alias:
                return t.table
        return None

    def new_alias(self, table: str) -> str:
        existing = {t.alias for t in self.tables}
        if table not in existing:
            return table
        i = 2
        while f"{table}{i}" in existing:
            i += 1
        return f"{table}{i}"

    def add_table(self, table: str, force_new: bool = False) -> str:
        if not force_new:
            for t in self.tables:
                if t.table == table:
                    return t.alias
        alias = self.new_alias(table)
        self.tables.append(TableRef(alias, table))
        return alias

    def remove_alias(self, alias: str):
        self.tables = [t for t in self.tables if t.alias != alias]
        self.links = [l for l in self.links if alias not in (l.left_alias, l.right_alias)]
        self.columns = [c for c in self.columns if not _col_uses(c, alias)]
        for g in self.filters:
            g.conditions = [c for c in g.conditions if c.alias != alias]
        headings = {c.heading for c in self.columns}
        self.sort = [s for s in self.sort if s.heading in headings]

    def unique_heading(self, base: str, ignore: OutColumn | None = None) -> str:
        used = {c.heading.lower() for c in self.columns if c is not ignore}
        h, i = base, 2
        while h.lower() in used:
            h = f"{base} {i}"
            i += 1
        return h

    # ------------------------------------------------------------------ serialisation
    def to_dict(self) -> dict:
        d = asdict(self)
        d["format"] = "sam-adhoc-query"
        d["format_version"] = 1
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "QueryDef":
        q = cls()
        for k in ("name", "description", "filter_mode", "distinct", "top", "sql_override", "created", "modified", "category"):
            if k in d:
                setattr(q, k, d[k])
        q.tables = [TableRef(**t) for t in d.get("tables", [])]
        q.links = []
        for l in d.get("links", []):
            l = dict(l)
            l["conditions"] = [Condition(**c) for c in l.get("conditions", [])]
            q.links.append(Link(**l))
        q.columns = []
        for c in d.get("columns", []):
            c = dict(c)
            c["formats"] = [Fmt(**f) for f in c.get("formats", [])]
            parts = []
            for p in c.get("parts", []):
                p = dict(p)
                p["formats"] = [Fmt(**f) for f in p.get("formats", [])]
                parts.append(Part(**p))
            c["parts"] = parts
            q.columns.append(OutColumn(**c))
        q.filters = [FilterGroup(g.get("match", "ALL"), [Condition(**c) for c in g.get("conditions", [])])
                     for g in d.get("filters", [])]
        q.sort = [SortItem(**s) for s in d.get("sort", [])]
        q.union_parts = [cls.from_dict(p) for p in d.get("union_parts", [])]
        return q

    @classmethod
    def from_json(cls, text: str) -> "QueryDef":
        return cls.from_dict(json.loads(text))

    def clone(self) -> "QueryDef":
        return copy.deepcopy(self)

    def touch(self):
        now = datetime.now().isoformat(timespec="seconds")
        if not self.created:
            self.created = now
        self.modified = now


def _col_uses(c: OutColumn, alias: str) -> bool:
    if c.kind == "field":
        return c.alias == alias
    return any(p.kind == "field" and p.alias == alias for p in c.parts)


# --------------------------------------------------------------------------- SQL generation
def apply_formats(expr: str, formats) -> str:
    for f in formats:
        t, a, b = f.type, f.a, f.b
        txt = f"CAST({expr} AS varchar(8000))"
        if t == "trim":
            expr = f"LTRIM(RTRIM({expr}))"
        elif t == "upper":
            expr = f"UPPER({expr})"
        elif t == "lower":
            expr = f"LOWER({expr})"
        elif t == "proper_first":
            expr = f"UPPER(LEFT({expr}, 1)) + LOWER(SUBSTRING({txt}, 2, 8000))"
        elif t == "left":
            expr = f"LEFT({expr}, {_int(a, 1)})"
        elif t == "right":
            expr = f"RIGHT({expr}, {_int(a, 1)})"
        elif t == "replace":
            expr = f"REPLACE({expr}, {sql_str(a)}, {sql_str(b)})"
        elif t == "remove_spaces":
            expr = f"REPLACE({expr}, ' ', '')"
        elif t == "strip_zeros":
            expr = f"SUBSTRING({txt}, PATINDEX('%[^0]%', {txt} + '.'), 8000)"
        elif t == "pad_zeros":
            n = _int(a, 1)
            expr = f"RIGHT(REPLICATE('0', {n}) + {txt}, {n})"
        elif t == "prefix":
            expr = f"CONCAT({sql_str(a)}, {expr})"
        elif t == "suffix":
            expr = f"CONCAT({expr}, {sql_str(a)})"
        elif t == "if_blank":
            expr = f"ISNULL(NULLIF(LTRIM(RTRIM({txt})), ''), {sql_str(a)})"
        elif t == "date_us":
            expr = f"CONVERT(varchar(10), {expr}, 101)"
        elif t == "date_iso":
            expr = f"CONVERT(varchar(10), {expr}, 23)"
        elif t == "age":
            expr = (f"(CONVERT(int, CONVERT(char(8), GETDATE(), 112)) - "
                    f"CONVERT(int, CONVERT(char(8), {expr}, 112))) / 10000")
        elif t == "yes_no":
            expr = f"CASE WHEN {expr} IN (1, '1', 'Y', 'T') THEN 'Yes' ELSE 'No' END"
        elif t == "decimals":
            n = _int(a, 2)
            expr = f"CAST(ROUND({expr}, {n}) AS decimal(18, {n}))"
        elif t == "map":
            pairs = parse_map(a)
            if pairs:
                whens = " ".join(f"WHEN {sql_str(k)} THEN {sql_str(v)}" for k, v in pairs)
                expr = f"CASE {txt} {whens} ELSE {txt} END"
        elif t == "year":
            expr = f"CAST(YEAR({expr}) AS varchar(4))"
    return expr


def _int(v, default):
    try:
        return max(0, int(str(v).strip()))
    except (TypeError, ValueError):
        return default


def col_ref(alias: str, column: str) -> str:
    return f"{ident(alias)}.{ident(column)}"


def column_expr(c: OutColumn) -> str:
    if c.kind == "raw":                      # exact SQL expression (e.g. imported CASE ... END)
        return apply_formats(f"({c.column})", c.formats)
    if c.kind == "custom":
        pieces = []
        for p in c.parts:
            if p.kind == "text":
                pieces.append(sql_str(p.value))
            elif p.kind == "sql":
                pieces.append(p.value)
            else:
                pieces.append(apply_formats(col_ref(p.alias, p.column), p.formats))
        if not pieces:
            base = "''"
        elif len(pieces) == 1:
            base = f"CONCAT({pieces[0]}, '')"
        else:
            base = "CONCAT(" + ", ".join(pieces) + ")"
        return apply_formats(base, c.formats)
    return apply_formats(col_ref(c.alias, c.column), c.formats)


def condition_sql(c: Condition) -> str:
    x = col_ref(c.alias, c.column)
    v, v2, op = c.value, c.value2, c.op
    if op == "eq":
        return f"{x} = {sql_str(v)}"
    if op == "ne":
        return f"({x} <> {sql_str(v)} OR {x} IS NULL)"
    if op == "contains":
        return f"{x} LIKE '%{like_escape(v)}%'"
    if op == "not_contains":
        return f"({x} NOT LIKE '%{like_escape(v)}%' OR {x} IS NULL)"
    if op == "starts":
        return f"{x} LIKE '{like_escape(v)}%'"
    if op == "ends":
        return f"{x} LIKE '%{like_escape(v)}'"
    if op in ("gt", "ge", "lt", "le"):
        sym = {"gt": ">", "ge": ">=", "lt": "<", "le": "<="}[op]
        return f"{x} {sym} {sql_str(v)}"
    if op == "between":
        return f"{x} BETWEEN {sql_str(v)} AND {sql_str(v2)}"
    if op in ("in", "not_in"):
        items = [i.strip() for i in str(v).split(",") if i.strip()]
        lst = ", ".join(sql_str(i) for i in items) or "''"
        return f"{x} {'NOT IN' if op == 'not_in' else 'IN'} ({lst})"
    if op == "blank":
        return f"({x} IS NULL OR LTRIM(RTRIM(CAST({x} AS varchar(8000)))) = '')"
    if op == "not_blank":
        return f"({x} IS NOT NULL AND LTRIM(RTRIM(CAST({x} AS varchar(8000)))) <> '')"
    if op == "last_days":
        return f"{x} >= DATEADD(day, -{_int(v, 7)}, CAST(GETDATE() AS date))"
    if op == "today":
        return f"CAST({x} AS date) = CAST(GETDATE() AS date)"
    if op == "raw":
        return f"({v})"
    raise ValueError(f"Unknown operator {op}")


def where_sql(q: QueryDef) -> str:
    groups = []
    for g in q.filters:
        conds = [condition_sql(c) for c in g.conditions if c.alias and c.column]
        if not conds:
            continue
        joiner = " AND " if g.match == "ALL" else " OR "
        groups.append(conds[0] if len(conds) == 1 else "(" + joiner.join(conds) + ")")
    if not groups:
        return ""
    joiner = "\n  AND " if q.filter_mode == "ALL" else "\n   OR "
    return "WHERE " + joiner.join(groups)


FLIP = {"LEFT": "RIGHT", "RIGHT": "LEFT", "INNER": "INNER", "FULL": "FULL"}


def from_sql(q: QueryDef, cond_fn=None) -> tuple[str, list[str]]:
    """Returns (FROM ... JOIN ... text, list of unreachable aliases).
    cond_fn renders a Condition (T-SQL by default; the preview passes its SQLite version)."""
    cond_fn = cond_fn or condition_sql

    def extra(l):
        return [cond_fn(c) for c in l.conditions if c.alias and c.column]
    if not q.tables:
        return "", []
    used_aliases = [t.alias for t in q.tables]
    first = used_aliases[0]
    placed = [first]
    clauses = []          # [alias, join_kw, [conditions]]
    pending = list(q.links)
    progress = True
    while progress:
        progress = False
        for l in list(pending):
            a_in, b_in = l.left_alias in placed, l.right_alias in placed
            if a_in and not b_in and l.right_alias in used_aliases:
                new, jt = l.right_alias, l.join
                cond = f"{col_ref(l.left_alias, l.left_col)} = {col_ref(l.right_alias, l.right_col)}"
            elif b_in and not a_in and l.left_alias in used_aliases:
                new, jt = l.left_alias, FLIP[l.join]
                cond = f"{col_ref(l.right_alias, l.right_col)} = {col_ref(l.left_alias, l.left_col)}"
            else:
                continue
            placed.append(new)
            clauses.append([new, JOIN_TYPES[jt][1], [cond] + extra(l)])
            pending.remove(l)
            progress = True
    # extra links between already placed tables -> AND onto the later join
    for l in pending:
        if l.left_alias in placed and l.right_alias in placed:
            later = max(placed.index(l.left_alias), placed.index(l.right_alias))
            if later == 0:
                continue
            clauses[later - 1][2].append(f"{col_ref(l.left_alias, l.left_col)} = {col_ref(l.right_alias, l.right_col)}")
            clauses[later - 1][2].extend(extra(l))
    def tsrc(alias):
        t = q.alias_table(alias)
        return ident(t) if t == alias else f"{ident(t)} AS {ident(alias)}"

    lines = [f"FROM {tsrc(first)}"]
    for alias, kw, conds in clauses:
        lines.append(f"{kw} {tsrc(alias)}\n    ON " + "\n   AND ".join(conds))
    unreachable = [a for a in used_aliases if a not in placed]
    return "\n".join(lines), unreachable


def _select_body(q: QueryDef, top: bool = True) -> list[str]:
    sel = "SELECT "
    if q.distinct:
        sel += "DISTINCT "
    if top and q.top and int(q.top) > 0:
        sel += f"TOP {int(q.top)} "
    cols = [f"    {agg_sql(c, column_expr(c))} AS {heading_ident(c.heading or c.column)}" for c in q.columns] or ["    *"]
    out = [sel.rstrip() + "\n" + ",\n".join(cols)]
    frm, _ = from_sql(q)
    if frm:
        out.append(frm)
    w = where_sql(q)
    if w:
        out.append(w)
    if any(c.agg for c in q.columns):
        keys = [column_expr(c) for c in q.columns if not c.agg]
        if keys:
            out.append("GROUP BY " + ",\n         ".join(keys))
    return out


def generate_sql(q: QueryDef, header: bool = True) -> str:
    if q.sql_override.strip():
        return q.sql_override
    parts = []
    if header:
        parts.append(f"-- {q.name}")
        if q.description:
            for line in q.description.splitlines():
                parts.append(f"-- {line}")
        parts.append(f"-- Built with SAM Ad Hoc Query Builder on {datetime.now():%m/%d/%Y}")
    if q.union_parts:
        blocks = ["\n".join(_select_body(q, top=False))]
        for p in q.union_parts:
            blocks.append((f"-- {p.name}\n" if header else "") + "\n".join(_select_body(p, top=False)))
        parts.append("\nUNION ALL\n".join(blocks))
    else:
        parts += _select_body(q)
    if q.sort:
        parts.append("ORDER BY " + ", ".join(
            f"{heading_ident(s.heading)}{' DESC' if s.desc else ''}" for s in q.sort))
    return "\n".join(parts) + "\n"


# --------------------------------------------------------------------------- validation
def validate(q: QueryDef, catalog=None) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    if q.sql_override.strip():
        warnings.append("The SQL has been edited by hand. Changes made in the steps will not appear until you click 'Discard manual edits'.")
        return errors, warnings
    if not q.tables:
        errors.append("Step 1: Choose at least one table.")
    if not q.columns:
        errors.append("Step 1: Choose at least one column to show.")
    _, unreachable = from_sql(q)
    if unreachable:
        errors.append("Step 2: These tables are not linked to the rest of the query: " + ", ".join(unreachable)
                      + ". Every table must be connected (use 'Suggest links').")
    aliases = {t.alias for t in q.tables}
    for l in q.links:
        if l.left_alias not in aliases or l.right_alias not in aliases:
            errors.append(f"Step 2: Link {l.left_alias} - {l.right_alias} refers to a table that was removed.")
        if not l.left_col or not l.right_col:
            errors.append(f"Step 2: Link {l.left_alias} - {l.right_alias} needs a column on both sides.")
        for c in l.conditions:
            need = OPERATORS.get(c.op, ("", 0))[1]
            if not c.alias or not c.column or (need >= 1 and not str(c.value).strip()):
                errors.append(f"Step 2: An extra condition on link {l.left_alias} - {l.right_alias} is incomplete.")
    seen = set()
    for c in q.columns:
        h = (c.heading or c.column).lower()
        if h in seen:
            errors.append(f"Step 3: Column heading '{c.heading}' is used more than once.")
        seen.add(h)
        if c.kind == "raw" and not c.column.strip():
            errors.append(f"Step 3: SQL expression column '{c.heading}' is empty.")
        if c.kind == "custom" and not c.parts and c.agg != "count":
            errors.append(f"Step 3: Custom column '{c.heading}' has no pieces.")
    for gi, g in enumerate(q.filters, 1):
        for c in g.conditions:
            if not c.alias or not c.column:
                errors.append(f"Step 4: Filter group {gi} has a condition without a column.")
                continue
            need = OPERATORS.get(c.op, ("", 0))[1]
            if need >= 1 and not str(c.value).strip():
                errors.append(f"Step 4: Filter on {c.alias}.{c.column} ({OPERATORS[c.op][0]}) needs a value.")
            if need == 2 and not str(c.value2).strip():
                errors.append(f"Step 4: Filter on {c.alias}.{c.column} needs a second value.")
    headings = {(c.heading or c.column) for c in q.columns}
    for s in q.sort:
        if s.heading not in headings:
            errors.append(f"Step 5: Sort column '{s.heading}' is no longer in the query.")
    if catalog is not None:
        try:
            from .privacy import report as _privacy_report
            for lvl, heading, src in _privacy_report(q)["shown"]:
                if lvl == "restricted":
                    warnings.append(f"'{heading}' ({src}) is restricted data (SSN/password). "
                                    "Remove it unless a contract requires it.")
        except Exception:
            pass
        for t in q.tables:
            if not catalog.has_table(t.table):
                warnings.append(f"Table {t.table} is not in the current table catalog.")
    if "{{" in generate_sql(q, header=False):
        names = sorted(set(re.findall(r"\{\{([A-Z_]+)\}\}", generate_sql(q, header=False))))
        try:
            from .district import LABELS as _labels
        except Exception:
            _labels = {}
        errors.append("District Settings needed: fill in "
                      + ", ".join(_labels.get(n.lower(), n.replace("_", " ").title()) for n in names)
                      + " (File > District Settings), then open the export again.")
    if len(q.tables) > 1 and not q.filters and not q.union_parts:
        warnings.append("No filters are set. The query may return a very large number of rows.")
    for p in q.union_parts:
        pe, pw = validate(p, catalog)
        errors += [f"Part '{p.name}': {e}" for e in pe if "Sort column" not in e]
        warnings += [f"Part '{p.name}': {w}" for w in pw if "No filters" not in w]
        if len(p.columns) != len(q.columns):
            errors.append(f"Part '{p.name}' has {len(p.columns)} columns but the first part has {len(q.columns)}. "
                          "Every part must have the same number of columns, in the same order.")
    return errors, warnings
