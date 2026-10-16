"""Sample-data preview.

Builds a small, made-up dataset for exactly the tables in a query (in an in-memory
SQLite database), translates the query to SQLite and runs it, so users can see the
*shape* of their results - columns, formats, joins, filters, sort - before pasting
the real SQL into SAM. No real SAM data is ever used.
"""
from __future__ import annotations

import random
import re
import sqlite3
import zlib
from dataclasses import dataclass, field
from datetime import date, timedelta

from .query_model import (parse_map, OutColumn, QueryDef, Condition, from_sql, heading_ident, col_ref, sql_str, _int)

PREVIEW_LIMIT = 200

# ----------------------------------------------------------------------------- made-up values
FIRST = ["Aaron", "Abby", "Bella", "Brandon", "Caleb", "Chloe", "Daniel", "Destiny", "Elijah", "Emma",
         "Gavin", "Grace", "Hannah", "Isaiah", "Jada", "Jacob", "Kayla", "Landon", "Madison", "Mason",
         "Noah", "Olivia", "Parker", "Riley", "Sophia", "Tyler", "Victoria", "William", "Zoe", "Logan"]
LAST = ["Adams", "Baker", "Bennett", "Brooks", "Carter", "Collins", "Davis", "Evans", "Fisher", "Garcia",
        "Harris", "Hughes", "Jackson", "Johnson", "Kelly", "Lewis", "Martin", "Mc Donald", "Nelson", "Owens",
        "Parker", "Reed", "Roberts", "Sanders", "Smith", "Taylor", "Turner", "Walker", "White", "Young"]
GRADES = ["KG", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
GRADE_DESC = {"KG": "Kindergarten", "01": "First Grade", "02": "Second Grade", "03": "Third Grade",
              "04": "Fourth Grade", "05": "Fifth Grade", "06": "Sixth Grade", "07": "Seventh Grade",
              "08": "Eighth Grade", "09": "Ninth Grade", "10": "Tenth Grade", "11": "Eleventh Grade",
              "12": "Twelfth Grade"}
COURSES = [("120101", "English I"), ("270201", "Algebra I"), ("260101", "Biology I"), ("450802", "U.S. History"),
           ("500101", "Art I"), ("360101", "Physical Education"), ("160101", "Spanish I"), ("400101", "Chemistry"),
           ("270301", "Geometry"), ("120201", "English II")]
SCHOOLS = [("010", "Sample High School"), ("020", "Sample Middle School"), ("030", "Sample Elementary School")]
STREETS = ["Oak St", "Pine Ave", "Magnolia Dr", "Beach Blvd", "Main St", "Cedar Ln", "Live Oak Rd", "Highway 90"]
CITIES = ["Bay St. Louis", "Kiln", "Waveland", "Diamondhead", "Pearlington"]
ATT = {"P": "Present", "A": "Absent - Unexcused", "E": "Absent - Excused", "T": "Tardy"}
LOOKUP_DESC = {
    "gendercode": {"M": "Male", "F": "Female"}, "sexcode": {"M": "Male", "F": "Female"},
    "racecode": {"W": "White", "B": "Black or African American", "H": "Hispanic", "A": "Asian",
                 "I": "American Indian"},
    "enrollmentstatus": {"E": "Enrolled", "W": "Withdrawn"},
    "status": {"A": "Active", "D": "Dropped", "W": "Withdrawn"},
    "relationshipcode": {"MO": "Mother", "FA": "Father", "GU": "Guardian", "GM": "Grandmother"},
}


def _rng(*parts) -> random.Random:
    return random.Random(zlib.crc32("|".join(map(str, parts)).encode()))


def _is_id(col: str) -> bool:
    lc = col.lower()
    return lc.endswith("id") and not lc.endswith("guid") and lc not in ("stateid",)


def _affinity(col: str) -> str:
    lc = col.lower()
    if _is_id(lc) or lc.startswith("is") or lc.endswith("flag") or lc in (
            "active", "flags", "sequence", "seq", "liveflag", "primarycontact", "emergencyflag", "resideswith",
            "primaryaddress", "primaryphone", "capacity", "seatlimit", "totalseats"):
        return "INTEGER"
    if any(k in lc for k in ("gpa", "qpa", "credit", "hours", "numeric", "average", "avg", "points", "miles")):
        return "REAL"
    return "TEXT"


def domain(col: str, table: str = "") -> list | None:
    """Fixed value lists for code-like columns (shared so joins/lookups line up)."""
    lc = col.lower()
    if lc in ("adagrade", "chronograde", "gradelevel", "highgradelevel", "lowgradelevel"):
        return GRADES
    for key, m in LOOKUP_DESC.items():
        if lc == key:
            return list(m)
    if lc in ("attendancecode", "teacherattendancecode"):
        return list(ATT)
    if lc in ("schoolcode",):
        return [s[0] for s in SCHOOLS]
    if lc in ("period",):
        return [str(i) for i in range(1, 8)]
    if lc in ("termcode", "term"):
        return ["AY", "S1", "S2", "T1", "T2", "T3"]
    return None


def describe(col: str, v) -> str:
    lc = col.lower()
    if lc in ("adagrade", "chronograde", "gradelevel", "highgradelevel", "lowgradelevel"):
        return GRADE_DESC.get(v, str(v))
    if lc in ("attendancecode", "teacherattendancecode"):
        return ATT.get(v, str(v))
    return LOOKUP_DESC.get(lc, {}).get(v, f"{v} description")


def _past(rng, lo_days, hi_days) -> str:
    return (date.today() - timedelta(days=rng.randint(lo_days, hi_days))).isoformat()


def value_for(table: str, col: str, i: int, rng: random.Random):
    lc = col.lower()
    tl = table.lower()
    dom = domain(col, table)
    if dom:
        if lc == "enrollmentstatus":
            return "E" if rng.random() < 0.85 else "W"
        if lc == "status":
            return "A" if rng.random() < 0.85 else rng.choice(["D", "W"])
        if lc == "adagrade" and "student" in tl:
            return GRADES[(i * 5) % len(GRADES)]
        return dom[i % len(dom)] if lc in ("period", "schoolcode") else rng.choice(dom)
    emp = "emp" in tl or "teacher" in tl or "staff" in tl
    if "firstname" in lc or lc in ("preferredname", "emppreferredfirstname"):
        return FIRST[(i * 7 + (11 if emp else 0)) % len(FIRST)]
    if "lastname" in lc or lc in ("maidenname", "formername", "emppreferredlastname"):
        return LAST[(i * 11 + (5 if emp else 0)) % len(LAST)]
    if "language" in lc:
        return "English" if rng.random() < 0.85 else "Spanish"
    if lc == "middlename":
        return rng.choice(FIRST)
    if lc in ("namesuffix", "suffix"):
        return "Jr" if rng.random() < 0.08 else ""
    if lc in ("nameprefix", "prefix"):
        return rng.choice(["Mr.", "Ms.", "Mrs.", "Dr."])
    if lc in ("studentcode", "employeenumber", "lunchnumber", "alternateid", "empalternateid"):
        return str((200000 if emp else 100000) + i + 1)
    if lc == "statecode":
        return f"000{rng.randint(1000000, 9999999)}"
    if lc == "ssn":
        return "XXX-XX-" + str(1000 + i)
    if lc == "dob":
        if emp:
            return _past(rng, 365 * 25, 365 * 60)
        if "student" in tl:  # age matches the sample grade level
            g = (i * 5) % len(GRADES)
            return _past(rng, 365 * (g + 5) + 60, 365 * (g + 6) + 30)
        return _past(rng, 365 * 6, 365 * 18)
    if lc == "attendancedate":
        return _past(rng, 0, 45)
    if lc == "hiredate":
        return _past(rng, 365, 365 * 25)
    if lc in ("terminationdate", "withdrawndate", "yearendstatusdate", "finalgraduationdate", "dropdate"):
        return None
    if "date" in lc or lc in ("tstamp", "lastupdated", "modified", "startdate", "begindate"):
        return _past(rng, 0, 120)
    if lc in ("enddate",):
        return (date.today() + timedelta(days=rng.randint(30, 200))).isoformat()
    if "email" in lc or (tl == "emailaddress" and lc == "address"):
        return f"{FIRST[(i * 7) % 30].lower()}.{LAST[(i * 11) % 30].lower().replace(' ', '')}@example.org"
    if lc == "shortname" and "school" in tl:
        return ["SHS", "SMS", "SES"][i % 3]
    if lc == "latitude":
        return round(30.30 + rng.uniform(0, 0.12), 6)
    if lc == "longitude":
        return round(-89.45 + rng.uniform(0, 0.15), 6)
    if lc == "schoolname":
        return SCHOOLS[i % len(SCHOOLS)][1]
    if lc in ("coursecode", "localcoursecode", "coursecode_local", "coursecode_state", "statecourseid"):
        return COURSES[i % len(COURSES)][0]
    if lc in ("longname", "shortname", "longname_local", "shortname_local", "longname_state", "shortname_state") \
            or (lc == "description" and "course" in tl):
        return COURSES[i % len(COURSES)][1]
    if lc == "sectionnumber":
        return f"{(i % 4) + 1:02d}"
    if lc in ("room", "roomcode"):
        return str(100 + (i * 13) % 120)
    if lc == "addrline1":
        return f"{100 + (i * 37) % 900} {STREETS[i % len(STREETS)]}"
    if lc == "addrline2":
        return "" if rng.random() < 0.8 else f"Apt {rng.randint(1, 20)}"
    if lc == "city":
        return CITIES[i % len(CITIES)]
    if lc == "state":
        return "MS"
    if lc == "zipcode":
        return rng.choice(["39520", "39525", "39556", "39576"])
    if lc == "county":
        return "Sample County"
    if lc == "areacode":
        return "228"
    if lc == "phonenumber":
        return f"555-{1000 + (i * 97) % 9000:04d}"
    if lc in ("descr",):
        y = date.today().year - (i % 3)
        return f"{y - 1}-{y}"
    if lc == "reportingdescription":
        return rng.choice(["Q1", "Q2", "S1", "Final"])
    if lc in ("attendancedescription",):
        return None  # filled from code by lookup logic when needed
    if lc in ("liveflag",):
        return 1 if i % 3 != 2 else 0
    if lc == "flags":
        return 0
    if lc.startswith("is") or lc.endswith("flag") or lc in ("active", "primarycontact", "emergencyflag",
                                                            "resideswith", "primaryaddress", "primaryphone"):
        return 1 if rng.random() < 0.7 else 0
    if lc in ("sequence", "seq"):
        return (i % 3) + 1
    if "gpa" in lc or "qpa" in lc:
        return round(rng.uniform(2.0, 4.0), 3)
    if "credit" in lc:
        return rng.choice([0.5, 1.0, 1.0])
    if "numeric" in lc or "average" in lc or "avg" in lc:
        return float(rng.randint(62, 100))
    if lc.endswith("alpha"):
        return rng.choice(["A", "B", "C", "D"])
    a = _affinity(col)
    if a == "INTEGER":
        return rng.randint(1, 5)
    if a == "REAL":
        return round(rng.uniform(0, 10), 2)
    return f"{split_word(col)} {i + 1}"


def split_word(col: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", col)


# ----------------------------------------------------------------------------- dataset
BASE_ROWS = {"student": 12, "employee": 8, "schooldef": 3, "course": 8, "schedule": 3, "academicsessions": 3,
             "contactinfo": 16, "districtdef": 1, "address": 14, "phonenumber": 16}


@dataclass
class PreviewResult:
    headings: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    total: int = 0
    error: str = ""
    sql: str = ""
    shown: int = 0


def build_dataset(q: QueryDef, catalog) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    allq = [q] + list(q.union_parts)
    tables = []
    for qq in allq:
        for t in qq.tables:
            if t.table not in tables and catalog.has_table(t.table):
                tables.append(t.table)
    # tables used inside custom SQL conditions, e.g. "... IN (SELECT ScheduleID FROM Schedule WHERE ...)"
    raw_text = " ".join(c.value for qq in allq for g in qq.filters for c in g.conditions if c.op == "raw") + " " + \
        " ".join(c.value for qq in allq for l in qq.links for c in l.conditions if c.op == "raw") + " " + \
        " ".join(c.column for qq in allq for c in qq.columns if c.kind == "raw")
    for name in re.findall(r"\b(?:from|join)\s+\[?([A-Za-z_][A-Za-z0-9_]*)", raw_text, re.I):
        if catalog.has_table(name) and name not in tables:
            tables.append(name)

    pk = {t: (catalog.columns(t)[0] if catalog.columns(t) and _is_id(catalog.columns(t)[0]) else None) for t in tables}

    # link info by table name: (table, col) -> (partner table, partner col)
    partners: dict[tuple, tuple] = {}
    for qq, l in [(qq, l) for qq in allq for l in qq.links]:
        lt, rt = qq.alias_table(l.left_alias), qq.alias_table(l.right_alias)
        if lt in pk and rt in pk:
            partners.setdefault((lt, l.left_col), (rt, l.right_col))
            partners.setdefault((rt, l.right_col), (lt, l.left_col))

    # ID columns named like another sample table's key (e.g. stuHRTeacher.ScheduleID -> Schedule) point at it too
    for t in tables:
        for c in catalog.columns(t):
            if c == pk.get(t) or (t, c) in partners or not _is_id(c):
                continue
            other = next((o for o in tables if o != t and pk.get(o) == c), None)
            if other:
                partners[(t, c)] = (other, c)

    # lookup tables: X.code = lookup.Val -> lookup rows come from the code's value list
    # values the query asks for (link ON conditions and filters) so sample rows actually match them
    preferred: dict[tuple, list] = {}

    def want(qq, c):
        t = qq.alias_table(c.alias)
        if not t:
            return
        if c.op in ("eq", "contains", "starts", "ends") and str(c.value).strip():
            vals = [c.value]
        elif c.op == "in":
            vals = [x.strip() for x in str(c.value).split(",") if x.strip()]
        else:
            return
        lst = preferred.setdefault((t, c.column), [])
        lst += [x for x in vals if x not in lst]

    for qq in allq:
        for l in qq.links:
            for c in l.conditions:
                want(qq, c)
        for g in qq.filters:
            for c in g.conditions:
                want(qq, c)

    lookup_src: dict[str, str] = {}
    for (t, c), (pt, pc) in partners.items():
        if c.lower() == "val" and (t.lower().startswith("lookup") or "Description" in catalog.columns(t)):
            lookup_src.setdefault(t, pc)

    # row counts: base, then children sized from the tables they point at
    rows: dict[str, int] = {}
    for t in tables:
        rows[t] = BASE_ROWS.get(t.lower(), 10)
    for t in tables:
        fk_targets = [pt for (tt, c), (pt, pc) in partners.items()
                      if tt == t and c != pk[t] and pk.get(pt) and pc == pk[pt]]
        if fk_targets:
            biggest = max(rows[x] for x in fk_targets)
            many = {"scheduleroster": 3, "attendancedaily": 3, "attendanceperiod": 3,
                    "studentcontact": 2}.get(t.lower(), 1)
            rows[t] = min(60, max(rows[t], biggest * many))
    for t, src in lookup_src.items():
        rows[t] = len(domain(src) or [None] * 5)
    # code-definition tables joined on a code column (e.g. AttendanceCodes.AttendanceCode): one row per code
    code_tables: dict[str, str] = {}
    for (t, c), _p in partners.items():
        if t not in lookup_src and c != pk[t] and domain(c) and ("code" in t.lower() or t.lower().startswith("lookup")):
            code_tables[t] = c
            rows[t] = len(domain(c))

    for t in tables:
        cols = catalog.columns(t)
        con.execute(f"CREATE TABLE {heading_ident(t)} (" +
                    ", ".join(f"{heading_ident(c)} {_affinity(c)}" for c in cols) + ")")
        data = []
        fk_cols = [c for c in cols if c != pk[t] and (t, c) in partners
                   and pk.get(partners[(t, c)][0]) and partners[(t, c)][1] == pk[partners[(t, c)][0]]]
        # the FK pointing at the table nearest the start of the query cycles through every parent row
        fk_cols.sort(key=lambda c: tables.index(partners[(t, c)][0]))
        cycle_col = fk_cols[0] if fk_cols else None
        for i in range(rows[t]):
            rng = _rng(t, i)
            row = []
            for c in cols:
                if t in lookup_src:
                    src = lookup_src[t]
                    dom = domain(src) or [f"{split_word(src)} {k + 1}" for k in range(rows[t])]
                    v = dom[i % len(dom)]
                    if c.lower() == "val":
                        row.append(v)
                        continue
                    if c.lower() == "description":
                        row.append(describe(src, v))
                        continue
                if c == pk[t]:
                    row.append(i + 1)
                    continue
                if t in code_tables and c == code_tables[t]:
                    row.append(domain(c)[i % len(domain(c))])
                    continue
                part = partners.get((t, c))
                if part and pk.get(part[0]) and part[1] == pk[part[0]]:
                    n = rows[part[0]]
                    # first FK cycles through every parent row; others vary
                    if c == cycle_col:
                        row.append((i % n) + 1)
                    else:
                        # spread so one parent row never gets the same partner twice
                        nc = rows[partners[(t, cycle_col)][0]] if cycle_col else 1
                        row.append(((i % nc) * 3 + i // nc + zlib.crc32(c.encode()) % 5) % n + 1)
                    continue
                if c.lower() == "attendancedescription":
                    row.append(ATT[list(ATT)[i % len(ATT)]])
                    continue
                if t.lower() == "attendancecodes" and c.lower() == "attendancecode":
                    row.append(list(ATT)[i % len(ATT)])
                    continue
                if _is_id(c):
                    row.append(_rng(t, c, i).randint(1, 10))
                    continue
                if (t, c) in preferred:
                    pref = preferred[(t, c)]
                    other = "0" if all(x == "1" for x in pref) else value_for(t, c, i, rng)
                    if cycle_col:
                        nc = rows[partners[(t, cycle_col)][0]]
                        j = i // max(1, nc)      # 0 for the first child row of each parent, 1 for the second...
                        row.append(pref[j] if j < len(pref) else other)
                    else:
                        # most rows match the filter, a few don't (so filters visibly do something)
                        row.append(pref[i % len(pref)] if i % 4 != 3 else other)
                    continue
                row.append(value_for(t, c, i, rng))
            data.append(row)
        con.executemany(f"INSERT INTO {heading_ident(t)} VALUES ({', '.join('?' * len(cols))})", data)
    return con


# ----------------------------------------------------------------------------- SQLite translation
def lite_heading(h: str) -> str:
    return '"' + h.replace('"', '""') + '"'


def _txt(e):
    return f"CAST({e} AS TEXT)"


def lite_formats(expr: str, formats) -> str:
    for f in formats:
        t, a, b = f.type, f.a, f.b
        if t == "trim":
            expr = f"TRIM({expr})"
        elif t == "upper":
            expr = f"UPPER({expr})"
        elif t == "lower":
            expr = f"LOWER({expr})"
        elif t == "proper_first":
            expr = f"(UPPER(SUBSTR({expr}, 1, 1)) || LOWER(SUBSTR({_txt(expr)}, 2)))"
        elif t == "left":
            expr = f"SUBSTR({expr}, 1, {_int(a, 1)})"
        elif t == "right":
            expr = f"SUBSTR({_txt(expr)}, -{_int(a, 1)})"
        elif t == "replace":
            expr = f"REPLACE({expr}, {sql_str(a)}, {sql_str(b)})"
        elif t == "remove_spaces":
            expr = f"REPLACE({expr}, ' ', '')"
        elif t == "strip_zeros":
            expr = f"LTRIM({_txt(expr)}, '0')"
        elif t == "pad_zeros":
            n = _int(a, 1)
            expr = f"SUBSTR('{'0' * n}' || {_txt(expr)}, -{n})"
        elif t == "prefix":
            expr = f"({sql_str(a)} || IFNULL({expr}, ''))"
        elif t == "suffix":
            expr = f"(IFNULL({expr}, '') || {sql_str(a)})"
        elif t == "if_blank":
            expr = f"IFNULL(NULLIF(TRIM({_txt(expr)}), ''), {sql_str(a)})"
        elif t == "date_us":
            expr = f"STRFTIME('%m/%d/%Y', {expr})"
        elif t == "date_iso":
            expr = f"DATE({expr})"
        elif t == "age":
            expr = (f"(CAST(STRFTIME('%Y%m%d', 'now') AS INTEGER) - "
                    f"CAST(STRFTIME('%Y%m%d', {expr}) AS INTEGER)) / 10000")
        elif t == "yes_no":
            expr = f"CASE WHEN {expr} IN (1, '1', 'Y', 'T') THEN 'Yes' ELSE 'No' END"
        elif t == "decimals":
            n = _int(a, 2)
            expr = f"PRINTF('%.{n}f', {expr})"
        elif t == "map":
            pairs = parse_map(a)
            if pairs:
                whens = " ".join(f"WHEN {sql_str(k)} THEN {sql_str(v)}" for k, v in pairs)
                expr = f"CASE {_txt(expr)} {whens} ELSE {_txt(expr)} END"
        elif t == "year":
            expr = f"STRFTIME('%Y', {expr})"
    return expr


def tsql_to_sqlite(sql: str, condition: bool = False) -> str:
    """Best-effort translation of a T-SQL snippet for the sample preview.

    Conditions are translated inside a WHERE clause: in a SELECT list T-SQL reads 'x = (...)' as an alias."""
    try:
        import sqlglot
        if condition:
            out = sqlglot.transpile(f"SELECT 1 WHERE {sql}", read="tsql", write="sqlite")[0]
            i = out.upper().find(" WHERE ")
            return out[i + 7:] if i >= 0 else sql
        out = sqlglot.transpile(f"SELECT {sql}", read="tsql", write="sqlite")[0]
        return out[len("SELECT "):] if out.upper().startswith("SELECT ") else sql
    except Exception:
        return sql


def lite_column(c: OutColumn) -> str:
    if c.kind == "raw":
        return lite_formats(f"({tsql_to_sqlite('(' + c.column + ')')})", c.formats)
    if c.kind == "custom":
        pieces = [sql_str(p.value) if p.kind == "text"
                  else f"IFNULL({lite_formats(col_ref(p.alias, p.column), p.formats)}, '')" for p in c.parts]
        base = "(" + " || ".join(pieces) + ")" if pieces else "''"
        return lite_formats(base, c.formats)
    return lite_formats(col_ref(c.alias, c.column), c.formats)


def _like(v):
    return str(v).replace("'", "''").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def lite_condition(c: Condition) -> str:
    x = col_ref(c.alias, c.column)
    v, v2, op = c.value, c.value2, c.op
    esc = " ESCAPE '\\'"
    simple = {"eq": "=", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}
    if op in simple:
        return f"{x} {simple[op]} {sql_str(v)}"
    if op == "ne":
        return f"({x} <> {sql_str(v)} OR {x} IS NULL)"
    if op == "contains":
        return f"{x} LIKE '%{_like(v)}%'{esc}"
    if op == "not_contains":
        return f"({x} NOT LIKE '%{_like(v)}%'{esc} OR {x} IS NULL)"
    if op == "starts":
        return f"{x} LIKE '{_like(v)}%'{esc}"
    if op == "ends":
        return f"{x} LIKE '%{_like(v)}'{esc}"
    if op == "between":
        return f"{x} BETWEEN {sql_str(v)} AND {sql_str(v2)}"
    if op in ("in", "not_in"):
        items = [i.strip() for i in str(v).split(",") if i.strip()]
        return f"{x} {'NOT IN' if op == 'not_in' else 'IN'} ({', '.join(sql_str(i) for i in items) or chr(39) * 2})"
    if op == "blank":
        return f"({x} IS NULL OR TRIM({_txt(x)}) = '')"
    if op == "not_blank":
        return f"({x} IS NOT NULL AND TRIM({_txt(x)}) <> '')"
    if op == "last_days":
        return f"DATE({x}) >= DATE('now', '-{_int(v, 7)} days')"
    if op == "today":
        return f"DATE({x}) = DATE('now')"
    if op == "raw":
        return f"({tsql_to_sqlite(v, condition=True)})"
    raise ValueError(op)


def lite_sql(q: QueryDef) -> str:
    sql = "\nUNION ALL\n".join(_lite_body(p) for p in [q] + list(q.union_parts))
    if q.sort:
        sql += "\nORDER BY " + ", ".join(f"{lite_heading(s.heading)}{' DESC' if s.desc else ''}" for s in q.sort)
    return sql


def _lite_agg(c, expr):
    a = c.agg
    if not a:
        return expr
    if a == "count":
        return "COUNT(*)" if (c.kind == "custom" and not c.parts) else f"COUNT({expr})"
    if a == "count_distinct":
        return f"COUNT(DISTINCT {expr})"
    if a == "avg":
        return f"ROUND(AVG({expr}), 2)"
    return f"{a.upper()}({expr})"


def _lite_body(q: QueryDef) -> str:
    cols = [f"{_lite_agg(c, lite_column(c))} AS {lite_heading(c.heading or c.column)}" for c in q.columns] or ["*"]
    sql = "SELECT " + ("DISTINCT " if q.distinct else "") + ",\n  ".join(cols)
    frm, _ = from_sql(q, lite_condition)
    sql += "\n" + frm
    groups = []
    for g in q.filters:
        conds = [lite_condition(c) for c in g.conditions if c.alias and c.column]
        if conds:
            groups.append("(" + (" AND " if g.match == "ALL" else " OR ").join(conds) + ")")
    if groups:
        sql += "\nWHERE " + (" AND " if q.filter_mode == "ALL" else " OR ").join(groups)
    if any(c.agg for c in q.columns):
        keys = [lite_column(c) for c in q.columns if not c.agg]
        if keys:
            sql += "\nGROUP BY " + ", ".join(keys)
    return sql


def friendly_error(msg: str) -> str:
    m = re.search(r"no such column: (\S+)", msg)
    if m:
        return f"The column {m.group(1)} is not in that table. Check Step 1 or the links in Step 2."
    if "RIGHT and FULL OUTER JOINs are not currently supported" in msg:
        return "Right / Full Outer links need a newer SQLite; the preview can't show them on this PC."
    return msg


def run_preview(q: QueryDef, catalog, limit: int = PREVIEW_LIMIT) -> PreviewResult:
    res = PreviewResult()
    if q.sql_override.strip():
        res.error = "The SQL was edited by hand, so the sample preview is not available. Discard manual edits to see it again."
        return res
    if not q.tables or not q.columns:
        res.error = "Choose tables and columns in Step 1 to see sample results."
        return res
    for qq in [q] + list(q.union_parts):
        label = f" (part '{qq.name}')" if q.union_parts else ""
        if not qq.columns:
            res.error = f"Choose columns in Step 1{label} to see sample results."
            return res
        if len(qq.columns) != len(q.columns):
            res.error = f"Every part must have the same number of columns{label}."
            return res
        _, unreachable = from_sql(qq)
        if unreachable:
            res.error = (f"Link every table in Step 2{label} to see sample results (not linked: "
                         + ", ".join(unreachable) + ").")
            return res
        for l in qq.links:
            if not l.left_col or not l.right_col:
                res.error = f"A link in Step 2{label} is missing a column."
                return res
    try:
        sql = lite_sql(q)
        res.sql = sql
        con = build_dataset(q, catalog)
        res.total = con.execute(f"SELECT COUNT(*) FROM ({sql})").fetchone()[0]
        n = min(limit, int(q.top)) if q.top and int(q.top) > 0 else limit
        cur = con.execute(f"{sql}\nLIMIT {n}")
        res.headings = [d[0] for d in cur.description]
        res.rows = cur.fetchall()
        res.shown = len(res.rows)
        if q.top and int(q.top) > 0:
            res.total = min(res.total, int(q.top))
        con.close()
    except Exception as e:  # bad raw condition etc.
        res.error = "Preview could not run: " + friendly_error(str(e))
    return res
