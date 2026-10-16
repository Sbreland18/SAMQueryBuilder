"""Privacy guardrails - which fields in a query (or export) are sensitive student / staff data.

Levels
  restricted : should almost never leave SAM (SSN, passwords)
  protected  : program / eligibility data protected by FERPA, IDEA, Section 504, USDA meal rules, McKinney-Vento...
  personal   : personal / contact information (birth date, address, phone, email, race...)
"""
from __future__ import annotations

import re

from .query_model import QueryDef

LEVELS = {
    "restricted": ("Restricted", "#B42318", "Should almost never leave SAM. Remove unless a contract requires it."),
    "protected": ("Protected program data", "#C2410C",
                  "Special education, 504, meal eligibility, homeless, foster, migrant, discipline and health data. "
                  "Share only with vendors whose data-privacy agreement covers it."),
    "personal": ("Personal information", "#9A6700",
                 "Birth dates, addresses, phone numbers, emails, race/ethnicity and state IDs. Check the vendor's "
                 "data-privacy agreement."),
}

RESTRICTED_COLS = {"ssn", "teacherssn", "password", "ssha_password", "pin", "guardianrefusedssn"}
PROTECTED_COLS = {"spedstatus", "spedflag", "flag504", "foodservicecode", "giftedstatus", "fosterchildflag",
                  "titleoneflag", "tanfstatus", "homelessflag", "ismigrant", "doesmigrantwork", "infractioncode",
                  "actiontaken", "weapontype", "daystoserve", "secluded", "restraint_physical", "restraint_mechanical",
                  "policenotified", "custodyorderdate", "nocontact", "custodial"}
PROTECTED_TABLE_PREFIXES = ("sped", "med", "immun", "discipline", "incident", "stuhomeless", "stumigrant", "historymedical",
                            "historydiscipline", "historyincident", "stutitleone", "stuatrisk", "ews_")
PERSONAL_COLS = {"dob", "birthdate", "addrline1", "addrline2", "city", "zipcode", "latitude", "longitude",
                 "phonenumber", "areacode", "emailaddress", "racecode", "statecode", "stateid", "birthcity",
                 "birthstate", "birthcountry", "lunchnumber", "langbackground", "primarylanguage", "maritalstatus",
                 "sexcode", "gendercode", "employer", "occupation", "routemiles", "buszone"}
PERSONAL_TABLES = {"address", "phonenumber", "emailaddress", "stumultirace"}


def classify(table: str, column: str) -> str | None:
    t, c = (table or "").lower(), (column or "").lower()
    if c in RESTRICTED_COLS:
        return "restricted"
    if c in PROTECTED_COLS or (t.startswith(PROTECTED_TABLE_PREFIXES) and not c.endswith("id")):
        return "protected"
    if c in PERSONAL_COLS or (t in PERSONAL_TABLES and c not in ("flags", "tstamp") and not c.endswith("id")):
        return "personal"
    return None


def _refs(q: QueryDef, col) -> list[tuple[str, str]]:
    if col.kind == "field":
        return [(col.alias, col.column)]
    if col.kind == "custom":
        return [(p.alias, p.column) for p in col.parts if p.kind == "field"]
    # raw SQL expression: alias.column mentions
    return re.findall(r"\[?([A-Za-z_][A-Za-z0-9_]*)\]?\.\[?([A-Za-z_][A-Za-z0-9_]*)\]?", col.column)


def report(q: QueryDef) -> dict:
    """{"shown": [(level, heading, 'Table.Column')], "filtered": [(level, 'Table.Column')]} across all parts."""
    shown, filtered = [], []
    for qq in [q] + list(q.union_parts):
        for col in qq.columns:
            if "password" in (col.heading or "").lower():
                src = "starting password column"
                if ("restricted", col.heading, src) not in shown:
                    shown.append(("restricted", col.heading, src))
            for a, c in _refs(qq, col):
                t = qq.alias_table(a) or a
                lvl = classify(t, c)
                if lvl and (lvl, col.heading, f"{t}.{c}") not in shown:
                    shown.append((lvl, col.heading, f"{t}.{c}"))
        for g in qq.filters:
            for cond in g.conditions:
                t = qq.alias_table(cond.alias) or cond.alias
                lvl = classify(t, cond.column)
                if lvl and (lvl, f"{t}.{cond.column}") not in filtered:
                    filtered.append((lvl, f"{t}.{cond.column}"))
    order = list(LEVELS)
    shown.sort(key=lambda x: order.index(x[0]))
    filtered.sort(key=lambda x: order.index(x[0]))
    return {"shown": shown, "filtered": filtered}


def summary_lines(q: QueryDef) -> list[str]:
    r = report(q)
    out = []
    for lvl in LEVELS:
        cols = [h for l, h, _src in r["shown"] if l == lvl]
        if cols:
            out.append(f"{LEVELS[lvl][0]}: {', '.join(dict.fromkeys(cols))}")
    flt = [src for l, src in r["filtered"] if l in ("protected", "restricted")]
    if flt:
        out.append("Rows are chosen using protected data: " + ", ".join(flt))
    return out


def html(q: QueryDef) -> str:
    r = report(q)
    if not r["shown"] and not r["filtered"]:
        return "<span style='color:#1E7B34'><b>Privacy:</b> no sensitive fields - names, IDs, grades and schools only.</span>"
    parts = ["<b>Privacy check</b>"]
    for lvl, (name, color, tip) in LEVELS.items():
        cols = list(dict.fromkeys(h for l, h, _s in r["shown"] if l == lvl))
        if cols:
            parts.append(f"<span style='color:{color}'><b>{name}:</b> {', '.join(cols)}</span> "
                         f"<span style='color:#4A5568'>- {tip}</span>")
    flt = [s for l, s in r["filtered"] if l in ("protected", "restricted")]
    if flt:
        parts.append(f"<span style='color:#C2410C'>Rows are selected using protected data ({', '.join(flt)}) - the "
                     "list itself reveals who is in that program.</span>")
    return "<br>".join(parts)
