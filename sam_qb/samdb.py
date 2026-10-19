"""OPTIONAL read-only connection to the SAM SQL Server database (off by default).

The app is built to generate SQL that people paste into SAM. Some districts also allow a read-only SQL login;
with this turned on the builder can show real results, exact row counts, and email reports straight from SAM.

Safety:
  * only one SELECT (or WITH ... SELECT) statement is allowed - anything that could change data, call
    procedures or reach other servers is refused before it is sent (is_read_only);
  * the connection asks for ApplicationIntent=ReadOnly and READ UNCOMMITTED so it never blocks SAM users;
  * results are capped and queries time out.
Use a SQL login that is only in db_datareader (or Windows authentication for a read-only group).
"""
from __future__ import annotations

import re

DEFAULTS = {"enabled": False, "server": "", "database": "", "auth": "windows", "username": "", "password": "",
            "driver": "", "timeout": 60, "max_rows": 500, "encrypt": True, "trust_cert": True}

BLOCKED = ("insert", "update", "delete", "merge", "drop", "alter", "create", "truncate", "exec", "execute",
           "grant", "revoke", "deny", "backup", "restore", "dbcc", "shutdown", "into", "openrowset", "openquery",
           "opendatasource", "waitfor", "use", "bulk", "kill", "reconfigure", "setuser", "checkpoint", "declare",
           "dump", "load", "writetext", "updatetext", "readtext", "disable", "enable", "sp_", "xp_")


def get(settings: dict) -> dict:
    c = dict(DEFAULTS)
    c.update(settings.get("sam_connection") or {})
    return c


def enabled(settings: dict) -> bool:
    c = get(settings)
    return bool(c["enabled"] and c["server"] and c["database"])


def _strip_strings_comments(sql: str) -> str:
    """Blank out comments, strings and quoted names in ONE left-to-right scan (so '--' inside a string or a quote
    inside [brackets] can't hide anything). Lengths are kept, so positions match the original SQL."""
    out = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        two = sql[i:i + 2]
        if two == "--":
            j = sql.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif two == "/*":
            depth, j = 1, i + 2
            while j < n and depth:
                if sql[j:j + 2] == "/*":
                    depth, j = depth + 1, j + 2
                elif sql[j:j + 2] == "*/":
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            out.append(" " * (j - i))
            i = j
        elif ch in "'[\"":
            close = {"'": "'", "[": "]", '"': '"'}[ch]
            j = i + 1
            while j < n:
                if sql[j] == close:
                    if j + 1 < n and sql[j + 1] == close:   # doubled '' or ]] or ""
                        j += 2
                        continue
                    break
                j += 1
            j = min(j + 1, n)
            out.append(ch + " " * max(0, j - i - 2) + (close if j - i >= 2 else ""))
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def is_read_only(sql: str) -> tuple[bool, str]:
    s = _strip_strings_comments(sql).strip().rstrip(";").strip()
    if not s:
        return False, "The query is empty."
    if ";" in s:
        return False, "Only one statement can be run (remove the ';')."
    low = s.lower()
    if re.search(r"\b\w+\s*\.\s*\w+\s*\.\s*\w*\s*\.\s*\w+", re.sub(r"\[ *\]", "x", low)):
        return False, "Four-part (linked server) names are not allowed."
    if not re.match(r"^(select|with)\b", low):
        return False, "Only SELECT queries can be run against SAM."
    for w in BLOCKED:
        pat = rf"\b{re.escape(w)}" if w.endswith("_") else rf"\b{re.escape(w)}\b"
        if re.search(pat, low):
            return False, f"'{w.upper().rstrip('_')}' is not allowed in a read-only query."
    return True, ""


def strip_order_by(sql: str) -> str:
    """Remove a trailing ORDER BY (not allowed inside a COUNT(*) wrapper)."""
    clean = _strip_strings_comments(sql)
    m = list(re.finditer(r"\border\s+by\b", clean, re.I))
    if not m:
        return sql
    last = m[-1].start()
    if clean[last:].count("(") != clean[last:].count(")") or ")" in clean[last:]:
        return sql
    return sql[:last].rstrip()


def connection_string(c: dict) -> str:
    driver = c.get("driver") or pick_driver()
    parts = [f"DRIVER={{{driver}}}", f"SERVER={c['server']}", f"DATABASE={c['database']}",
             "ApplicationIntent=ReadOnly", "APP=SAM Ad Hoc Query Builder (read-only)"]
    if c.get("auth") == "sql":
        from .uploader import unprotect
        parts += [f"UID={c['username']}", f"PWD={{{unprotect(c.get('password', '')).replace('}', '}}')}}}"]
    else:
        parts.append("Trusted_Connection=yes")
    if "ODBC Driver 18" in driver or "ODBC Driver 17" in driver:
        parts.append("Encrypt=" + ("yes" if c.get("encrypt", True) else "no"))
        if c.get("trust_cert", True):
            parts.append("TrustServerCertificate=yes")
    return ";".join(parts)


def pick_driver() -> str:
    try:
        import pyodbc
        names = pyodbc.drivers()
    except Exception:
        names = []
    for pref in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server Native Client 11.0",
                 "SQL Server"):
        if pref in names:
            return pref
    return "ODBC Driver 18 for SQL Server"


def connect(settings: dict):
    try:
        import pyodbc
    except ImportError as e:
        raise RuntimeError("The pyodbc package is not installed.") from e
    c = get(settings)
    con = pyodbc.connect(connection_string(c), timeout=int(c.get("timeout") or 60), autocommit=True,
                         readonly=True)
    con.timeout = int(c.get("timeout") or 60)
    cur = con.cursor()
    cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
    cur.execute("SET NOCOUNT ON")
    return con


def run(settings: dict, sql: str, max_rows: int | None = None, count: bool = True) -> dict:
    """{'headings', 'rows', 'total', 'truncated'}; raises ValueError for anything that isn't read-only."""
    ok, why = is_read_only(sql)
    if not ok:
        raise ValueError(why)
    c = get(settings)
    max_rows = int(max_rows or c.get("max_rows") or 500)
    con = connect(settings)
    try:
        cur = con.cursor()
        cur.execute(sql)
        headings = [d[0] for d in cur.description or []]
        rows = [list(r) for r in cur.fetchmany(max_rows + 1)]
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        total = len(rows)
        if count and truncated:
            try:
                cur.execute(f"SELECT COUNT(*) FROM ({strip_order_by(sql)}) AS q")
                total = cur.fetchone()[0]
            except Exception:
                total = -1
        return {"headings": headings, "rows": rows, "total": total, "truncated": truncated}
    finally:
        con.close()


def test(settings: dict) -> str:
    con = connect(settings)
    try:
        cur = con.cursor()
        cur.execute("SELECT @@VERSION, DB_NAME(), SUSER_SNAME(), "
                    "HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'INSERT')")
        ver, db, login, can_write = cur.fetchone()
        msg = f"Connected to {db} as {login}.\n{str(ver).splitlines()[0]}"
        if can_write:
            msg += ("\n\nWARNING: this login can change data in SAM. The app only sends SELECT queries, but a "
                    "login that is only in db_datareader is strongly recommended.")
        return msg
    finally:
        con.close()


def count(settings: dict, sql: str) -> tuple[int, float]:
    """(rows the query returns, seconds it took) - used to check a query before creating its CAC job."""
    import time
    ok, why = is_read_only(sql)
    if not ok:
        raise ValueError(why)
    t = time.perf_counter()
    con = connect(settings)
    try:
        cur = con.cursor()
        cur.execute(f"SELECT COUNT(*) FROM ({strip_order_by(sql)}) AS q")
        n = int(cur.fetchone()[0])
    finally:
        con.close()
    return n, time.perf_counter() - t


def count_text(n: int, secs: float) -> str:
    speed = "fast" if secs < 5 else "OK" if secs < 30 else "SLOW - consider a narrower filter"
    warn = "  -  0 rows: check the filters before scheduling it" if n == 0 else ""
    return f"{n:,} rows, ran in {secs:.1f} s ({speed}){warn}"
