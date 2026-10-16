"""Optional AI mode for the Query Assistant (Claude API).

Only the user's description, table/column names, known links and the district's code
settings are sent - never student data. The model returns a query definition as JSON,
which is checked against the catalog before it is used.
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request

from . import district
from .assistant import Plan, build_from_text
from .query_model import FORMATS, OPERATORS, JOIN_TYPES, QueryDef

API_URL = "https://api.anthropic.com/v1/messages"
MODELS = ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"]
DEFAULT_MODEL = "claude-sonnet-5-5"

SCHEMA_HELP = """Return ONLY one JSON object (no prose outside it) with this shape:
{
  "name": "short query name",
  "description": "one sentence",
  "tables": [{"alias": "Student", "table": "Student"}],
  "links": [{"left_alias": "Student", "left_col": "StudentID", "right_alias": "stuSchool", "right_col": "StudentID",
             "join": "INNER|LEFT|RIGHT|FULL",
             "conditions": [{"alias": "...", "column": "...", "op": "eq", "value": "..."}]}],
  "columns": [
     {"kind": "field", "alias": "Student", "column": "LastName", "heading": "Last Name", "formats": [{"type": "trim", "a": "", "b": ""}]},
     {"kind": "custom", "heading": "Student", "parts": [
         {"kind": "field", "alias": "Student", "column": "LastName", "formats": []},
         {"kind": "text", "value": ", "},
         {"kind": "field", "alias": "Student", "column": "FirstName", "formats": []}]}],
  "filters": [{"match": "ALL|ANY", "conditions": [{"alias": "Student", "column": "ADAGrade", "op": "in", "value": "09, 10", "value2": ""}]}],
  "filter_mode": "ALL",
  "sort": [{"heading": "Last Name", "desc": false}],
  "distinct": false,
  "notes": ["anything the user should double-check, e.g. assumed codes"]
}
Rules:
- Use ONLY tables and columns listed in the catalog below; aliases must be unique. Use a second alias for a second copy of a table (e.g. Employee as HomeroomTeacher).
- Every table must be connected through links. Prefer the KNOWN LINKS listed.
- Use LEFT links for optional data (contacts, phones, emails, addresses, lookups) and put OwnerType / PrimaryPhone /
  PrimaryAddress style restrictions in that link's "conditions", not in "filters".
- AddressRelationship, PhoneRelationship and EmailAddress hold rows for several owner types; always restrict OwnerType
  using the district codes given. If a needed code is blank, use the placeholder {{OWNER_TYPE_STUDENT}} /
  {{OWNER_TYPE_CONTACT}} / {{OWNER_TYPE_EMPLOYEE}} and add a note.
- Students link to classes ONLY through ScheduleRoster -> ScheduleFramework -> ScheduleCourseTerm -> ScheduleCourse -> Course;
  the current schedule is Schedule.LiveFlag = 1. Homeroom is stuHRTeacher.HRTeacherID -> Employee.EmployeeID.
- Values in filters are SAM codes (grades usually KG, 01..12). Sort headings must be column headings.
- No GROUP BY/aggregates are available; if the user asks for counts, list the rows and say so in notes.
"""


def _catalog_context(text: str, catalog, base: QueryDef) -> str:
    words = [w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in
             {"the", "and", "with", "for", "all", "their", "who", "are", "list", "show", "that", "from", "each"}]
    tables = [t.table for t in base.tables]
    for t in catalog.common_tables:
        if t not in tables:
            tables.append(t)
    for w in words:
        for t, c in catalog.search(w)[:15]:
            if t not in tables and not catalog.tables[t].get("hidden"):
                tables.append(t)
    tables = tables[:45]
    lines = ["CATALOG (table: friendly name - columns):"]
    for t in tables:
        info = catalog.tables[t]
        desc = f" ({info['description']})" if info.get("description") else ""
        lines.append(f"- {t}: {info.get('friendly', t)}{desc}\n  columns: {', '.join(info['columns'])}")
    lines.append("\nKNOWN LINKS:")
    seen = 0
    tset = set(tables)
    for r in catalog.relationships:
        if r["from_table"] in tset and r["to_table"] in tset:
            lines.append(f"- {r['from_table']}.{r['from_col']} = {r['to_table']}.{r['to_col']}"
                         + (" (lookup)" if r.get("lookup") else ""))
            seen += 1
            if seen > 220:
                break
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


def _clean(d: dict, catalog) -> tuple[QueryDef, list[str]]:
    """Drop anything that doesn't exist in the catalog; return the QueryDef and notes about removals."""
    notes = []
    tables = []
    aliases = {}
    for t in d.get("tables", []):
        if catalog.has_table(t.get("table", "")) and t.get("alias") and t["alias"] not in aliases:
            tables.append({"alias": t["alias"], "table": t["table"]})
            aliases[t["alias"]] = t["table"]
        else:
            notes.append(f"Ignored unknown table {t.get('table')}")

    def ok(alias, col):
        return alias in aliases and col in catalog.columns(aliases[alias])

    links = []
    for l in d.get("links", []):
        if ok(l.get("left_alias"), l.get("left_col")) and ok(l.get("right_alias"), l.get("right_col")):
            l["join"] = l.get("join", "INNER").upper() if l.get("join", "INNER").upper() in JOIN_TYPES else "INNER"
            l["conditions"] = [c for c in l.get("conditions", []) if ok(c.get("alias"), c.get("column"))
                               and c.get("op", "eq") in OPERATORS]
            links.append(l)
        else:
            notes.append(f"Ignored a link with an unknown column ({l.get('left_alias')}.{l.get('left_col')} = "
                         f"{l.get('right_alias')}.{l.get('right_col')})")
    cols = []
    for c in d.get("columns", []):
        fm = [f for f in c.get("formats", []) if f.get("type") in FORMATS]
        c["formats"] = fm
        if c.get("kind") == "custom":
            parts = []
            for p in c.get("parts", []):
                if p.get("kind") == "text" or ok(p.get("alias"), p.get("column")):
                    p["formats"] = [f for f in p.get("formats", []) if f.get("type") in FORMATS]
                    parts.append({"kind": p.get("kind", "field"), "alias": p.get("alias", ""),
                                  "column": p.get("column", ""), "value": p.get("value", ""), "formats": p["formats"]})
            if parts:
                cols.append({"kind": "custom", "alias": "", "column": "", "heading": c.get("heading") or "Custom",
                             "formats": fm, "parts": parts})
        elif ok(c.get("alias"), c.get("column")):
            cols.append({"kind": "field", "alias": c["alias"], "column": c["column"],
                         "heading": c.get("heading") or c["column"], "formats": fm, "parts": []})
        else:
            notes.append(f"Ignored unknown column {c.get('alias')}.{c.get('column')}")
    filters = []
    for g in d.get("filters", []):
        conds = [c for c in g.get("conditions", []) if ok(c.get("alias"), c.get("column")) and c.get("op") in OPERATORS]
        if conds:
            filters.append({"match": g.get("match", "ALL") if g.get("match") in ("ALL", "ANY") else "ALL",
                            "conditions": [{"alias": c["alias"], "column": c["column"], "op": c["op"],
                                            "value": str(c.get("value", "")), "value2": str(c.get("value2", ""))}
                                           for c in conds]})
    headings = {c["heading"] for c in cols}
    sort = [{"heading": s["heading"], "desc": bool(s.get("desc"))} for s in d.get("sort", [])
            if s.get("heading") in headings]
    for l in links:
        l["conditions"] = [{"alias": c["alias"], "column": c["column"], "op": c.get("op", "eq"),
                            "value": str(c.get("value", "")), "value2": str(c.get("value2", ""))}
                           for c in l["conditions"]]
    qd = {"name": d.get("name") or "AI query", "description": d.get("description", ""), "tables": tables,
          "links": [{k: l[k] for k in ("left_alias", "left_col", "right_alias", "right_col", "join", "conditions")}
                    for l in links],
          "columns": cols, "filters": filters, "filter_mode": d.get("filter_mode", "ALL"), "sort": sort,
          "distinct": bool(d.get("distinct", False))}
    return QueryDef.from_dict(qd), notes


def ask_claude(text: str, catalog, settings: dict, progress=None) -> Plan:
    key = (settings.get("ai_api_key") or "").strip()
    if not key:
        raise ValueError("Add your Anthropic API key in File > Settings to use the AI helper.")
    model = settings.get("ai_model") or DEFAULT_MODEL
    base = build_from_text(text, catalog, settings).query   # gives the AI a head start on relevant tables
    ds = district.get(settings)
    codes = {k: ds[k] for k in ("enrolled_status_codes", "owner_type_student", "owner_type_contact",
                                "owner_type_employee", "staff_email_domain", "student_email_domain")}
    system = ("You build read-only SQL Server queries for the SAM student information system (SAMS database) "
              "used by Mississippi school districts. You answer with a JSON query definition only.\n\n"
              + SCHEMA_HELP + "\nAvailable formats: " + ", ".join(f"{k} ({v[0]})" for k, v in FORMATS.items())
              + "\nAvailable filter ops: " + ", ".join(f"{k} ({v[0]})" for k, v in OPERATORS.items())
              + "\n\nDISTRICT SETTINGS: " + json.dumps(codes) + "\n\n" + _catalog_context(text, catalog, base))
    body = {"model": model, "max_tokens": 4000, "system": system,
            "messages": [{"role": "user", "content": f"Build a query for this request:\n\n{text}"}]}
    if progress:
        progress("Asking Claude...", 30)
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120, context=ssl.create_default_context()) as r:
            resp = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        raise RuntimeError(f"Claude API error {e.code}: {detail}") from None
    text_out = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
    if progress:
        progress("Checking the answer against the table catalog...", 80)
    d = _extract_json(text_out)
    q, notes = _clean(d, catalog)
    _, added, problems = catalog.suggest_links(q, add_tables=True)
    understood = [f"Built by {model}"] + ([f"Added linking tables: {', '.join(added)}"] if added else [])
    plan = Plan(q, understood, list(d.get("notes", [])) + notes + problems, source=f"AI helper ({model})")
    plan.summary = d.get("description", "") or ""
    return plan
