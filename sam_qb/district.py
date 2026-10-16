"""District settings used by platform-export templates.

Export templates may contain:
  * text like {{STAFF_EMAIL_DOMAIN}} in text pieces, filter values or format options
  * special custom-column pieces {"kind": "username", "alias": "Student", "value": "student"}
    and {"kind": "email", ...}, which are expanded into real column pieces using the
    district's username pattern when the template is opened.
"""
from __future__ import annotations

import copy
import re
from datetime import date

from .query_model import Fmt, Part, QueryDef

# Username / email patterns are written with tokens, e.g. "{f}.{last}" -> j.smith
#   {first} {last} {middle}      whole names (lower case, no spaces, apostrophes, hyphens or periods)
#   {f} {l} {m}                  first / last / middle initial
#   {first3} {last5} ...         first N letters of a name
#   {id}  {id4} {id6} ...        the ID (students: Student ID, staff: employee number) or its last N digits
#   {grad} {grad2}               graduation year (students only), 4 or 2 digits
# anything else (. _ - letters, digits) is copied as is, e.g. "s{id}" -> s1001234
PATTERN_PRESETS = [
    ("{first}.{last}", "first.last"),
    ("{f}.{last}", "first initial.last"),
    ("{f}{last}", "first initial + last"),
    ("{first}{last}", "first + last"),
    ("{first}_{last}", "first_last"),
    ("{first}-{last}", "first-last"),
    ("{first}{l}", "first + last initial"),
    ("{first}.{l}", "first.last initial"),
    ("{last}.{first}", "last.first"),
    ("{last}{first}", "last + first"),
    ("{last}{f}", "last + first initial"),
    ("{last}.{f}", "last.first initial"),
    ("{f}{m}{last}", "first initial + middle initial + last"),
    ("{first}.{m}.{last}", "first.middle initial.last"),
    ("{f}{last}{id4}", "first initial + last + last 4 of ID"),
    ("{first}.{last}{id4}", "first.last + last 4 of ID"),
    ("{f}{last}{grad2}", "first initial + last + 2-digit grad year"),
    ("{first}.{last}{grad2}", "first.last + 2-digit grad year"),
    ("{last}{f}{id4}", "last + first initial + last 4 of ID"),
    ("{f}{last5}{id3}", "first initial + 5 letters of last + last 3 of ID"),
    ("{id}", "ID number"),
    ("s{id}", "s + ID number"),
]
LEGACY_PATTERNS = {"first.last": "{first}.{last}", "flast": "{f}{last}", "firstlast": "{first}{last}",
                   "lastf": "{last}{f}", "flast+id4": "{f}{last}{id4}", "id": "{id}"}
_TOKEN = re.compile(r"\{([a-z]+)(\d*)\}")
TOKEN_NAMES = {"first", "last", "middle", "f", "l", "m", "id", "grad"}


def normalize_pattern(p: str) -> str:
    p = (p or "").strip()
    return LEGACY_PATTERNS.get(p, p) or "{f}{last}"


def pattern_errors(p: str) -> list[str]:
    p = normalize_pattern(p)
    errs = [f"{{{n}{d}}} is not a known token" for n, d in _TOKEN.findall(p) if n not in TOKEN_NAMES
            or (n == "grad" and d not in ("", "2")) or (n in ("f", "l", "m") and d)]
    if not _TOKEN.search(p):
        errs.append("The pattern needs at least one {token}.")
    if re.search(r"[^a-zA-Z0-9._\-{}]", p):
        errs.append("Only letters, digits, . _ - and {tokens} are allowed.")
    return errs


def example(pattern: str, staff: bool = False) -> str:
    """What the pattern makes for Jane Marie Smith (ID 1001234, class of 2027)."""
    p = normalize_pattern(pattern)
    vals = {"first": "jane", "last": "smith", "middle": "marie", "id": "E2741" if staff else "1001234",
            "grad": "" if staff else "2027"}

    def one(m):
        n, d = m.group(1), m.group(2)
        if n in ("f", "l", "m"):
            return {"f": "j", "l": "s", "m": "m"}[n]
        if n == "grad":
            return vals["grad"][-2:] if d == "2" else vals["grad"]
        v = vals.get(n, "")
        if not d:
            return v.lower()
        return (v[-int(d):] if n == "id" else v[:int(d)]).lower()
    return _TOKEN.sub(one, p)


USERNAME_PATTERNS = {k: f"{v}  ({example(k)})" for k, v in PATTERN_PRESETS}


def _default_year():
    t = date.today()
    return t.year + 1 if t.month >= 7 else t.year


DEFAULTS = {
    "district_name": "Hancock County School District",
    "district_id": "",                      # state or NCES district id (used as the district org id)
    "staff_email_domain": "hancockschools.net",
    "student_email_domain": "hancockschools.net",
    "student_username_pattern": "{f}{last}{id4}",
    "staff_username_pattern": "{first}.{last}",
    "student_email_pattern": "",            # blank = same as the student username
    "staff_email_pattern": "",              # blank = same as the staff username
    "student_email_source": "pattern",      # pattern | sam  (use Student.EmailAddress from SAM)
    "school_year": str(_default_year()),    # school year END year, e.g. 2027 for 2026-27
    "google_student_ou": "/Students",
    "google_staff_ou": "/Staff",
    "default_password": "****",             # **** = leave existing Google passwords unchanged
    "enrolled_status_codes": "",            # SAM Student.EnrollmentStatus code(s) for enrolled students, e.g. E
    # OwnerType codes used by AddressRelationship / PhoneRelationship / EmailAddress (see the OwnerType table)
    "owner_type_student": "",
    "owner_type_contact": "",
    "owner_type_employee": "",
    "act_org_code": "",                     # ACT high school / organization code (ACT test data upload)
    "account_password_prefix": "",          # starting passwords for AD / Entra = prefix + last 6 of the ID
    "ad_student_ou": "",                    # e.g. OU=Students,DC=district,DC=local
    "ad_staff_ou": "",                      # e.g. OU=Staff,DC=district,DC=local
    "online_course_keyword": "",            # course-name keyword that marks credit-recovery / online sections
    "adobe_identity_type": "Federated ID",  # Federated ID | Enterprise ID | Adobe ID
    "shutoff_days": "14",                   # account shutoff list looks back this many days
    "cb_ai_code": "",                       # College Board AI code of the testing school
    "cb_test": "SAT",                       # PNM | P89 | P10 | SAT
    "renaissance_course_keyword": "",       # Renaissance roster: course names containing this
    "cte_course_codes": "",                 # CTE testing roster: SAM course codes, comma separated
}

LABELS = {
    "district_name": "District name",
    "district_id": "District ID (state or NCES)",
    "staff_email_domain": "Staff email domain",
    "student_email_domain": "Student email domain",
    "student_username_pattern": "Student username pattern",
    "student_email_pattern": "Student email name pattern (blank = same as username)",
    "staff_username_pattern": "Staff username pattern",
    "staff_email_pattern": "Staff email name pattern (blank = same as username)",
    "student_email_source": "Student email comes from",
    "school_year": "School year (end year, e.g. 2027)",
    "google_student_ou": "Google OU for students",
    "google_staff_ou": "Google OU for staff",
    "default_password": "Google password column",
    "enrolled_status_codes": "Enrolled status code(s)",
    "owner_type_student": "Owner type code - Student",
    "owner_type_contact": "Owner type code - Contact (parent/guardian)",
    "owner_type_employee": "Owner type code - Employee",
    "act_org_code": "ACT organization (high school) code",
    "account_password_prefix": "Starting password prefix (AD / Entra: prefix + last 6 of ID)",
    "ad_student_ou": "Active Directory OU for students",
    "ad_staff_ou": "Active Directory OU for staff",
    "online_course_keyword": "Online / credit-recovery course name contains",
    "adobe_identity_type": "Adobe identity type",
    "shutoff_days": "Account shutoff: look back (days)",
    "cb_ai_code": "College Board AI code (testing school)",
    "cb_test": "College Board test (PNM, P89, P10 or SAT)",
    "renaissance_course_keyword": "Renaissance classes: course name contains",
    "cte_course_codes": "CTE course codes (comma separated)",
}


def get(settings: dict) -> dict:
    d = dict(DEFAULTS)
    d.update({k: v for k, v in (settings.get("district") or {}).items() if v is not None})
    return d


def variables(ds: dict) -> dict:
    return {k.upper(): str(v) for k, v in ds.items()}


def _clean(alias, col, *extra):
    return Part("field", alias, col, formats=[Fmt("lower"), Fmt("remove_spaces"), Fmt("replace", "'", ""),
                                               Fmt("replace", "-", ""), Fmt("replace", ".", ""), *extra])


def pattern_parts(alias: str, pattern: str, staff: bool) -> list[Part]:
    """Turn a token pattern into custom-column pieces for the alias (Student or Employee table)."""
    id_col = "EmployeeNumber" if staff else "StudentCode"
    cols = {"first": "FirstName", "last": "LastName", "middle": "MiddleName"}
    parts: list[Part] = []
    pos = 0
    p = normalize_pattern(pattern)
    for m in _TOKEN.finditer(p):
        if m.start() > pos:
            parts.append(Part("text", value=p[pos:m.start()].lower()))
        pos = m.end()
        n, d = m.group(1), m.group(2)
        if n in cols:
            parts.append(_clean(alias, cols[n], *([Fmt("left", d)] if d else [])))
        elif n in ("f", "l", "m"):
            parts.append(_clean(alias, cols[{"f": "first", "l": "last", "m": "middle"}[n]], Fmt("left", "1")))
        elif n == "id":
            parts.append(Part("field", alias, id_col, formats=[Fmt("trim")] + ([Fmt("right", d)] if d else [])))
        elif n == "grad" and not staff:
            parts.append(Part("field", alias, "OriginalGradDate",
                              formats=[Fmt("year")] + ([Fmt("right", "2")] if d == "2" else [])))
    if pos < len(p):
        parts.append(Part("text", value=p[pos:].lower()))
    return parts or [_clean(alias, "FirstName", Fmt("left", "1")), _clean(alias, "LastName")]


def username_parts(alias: str, role: str, ds: dict) -> list[Part]:
    staff = role == "staff"
    return pattern_parts(alias, ds["staff_username_pattern" if staff else "student_username_pattern"], staff)


def email_parts(alias: str, role: str, ds: dict) -> list[Part]:
    staff = role == "staff"
    if not staff and ds.get("student_email_source") == "sam":
        return [Part("field", alias, "EmailAddress", formats=[Fmt("trim"), Fmt("lower")])]
    domain = ds["staff_email_domain" if staff else "student_email_domain"]
    own = (ds.get("staff_email_pattern" if staff else "student_email_pattern") or "").strip()
    local = pattern_parts(alias, own, staff) if own else username_parts(alias, role, ds)
    return local + [Part("text", value="@" + domain)]


_VAR = re.compile(r"\{\{([A-Z_]+)\}\}")


OPTIONAL_VARS = {"ENROLLED_STATUS_CODES", "DISTRICT_ID"}


def _sub(text, vars_):
    if not isinstance(text, str):
        return text

    def one(m):
        val = vars_.get(m.group(1), "")
        if val.strip() or m.group(1) in OPTIONAL_VARS:
            return val
        return m.group(0)  # leave {{NAME}} so the Review step asks for the setting
    return _VAR.sub(one, text)


def expand(qdict: dict, settings: dict) -> QueryDef:
    """Turn an export template (dict) into a ready-to-edit QueryDef using district settings."""
    ds = get(settings)
    v = variables(ds)
    d = copy.deepcopy(qdict)

    def fix_formats(fmts):
        for f in fmts or []:
            f["a"] = _sub(f.get("a", ""), v)
            f["b"] = _sub(f.get("b", ""), v)

    def walk(q):
        q["name"] = _sub(q.get("name", ""), v)
        q["description"] = _sub(q.get("description", ""), v)
        for c in q.get("columns", []):
            fix_formats(c.get("formats"))
            new_parts = []
            for p in c.get("parts", []):
                kind = p.get("kind", "field")
                if kind in ("username", "email"):
                    fn = username_parts if kind == "username" else email_parts
                    new_parts += [_part_dict(x) for x in fn(p["alias"], p.get("value", "student"), ds)]
                    continue
                p["value"] = _sub(p.get("value", ""), v)
                fix_formats(p.get("formats"))
                new_parts.append(p)
            c["parts"] = new_parts
        for g in q.get("filters", []):
            kept = []
            for cnd in g.get("conditions", []):
                orig = str(cnd.get("value", ""))
                had_var = "{{" in orig
                cnd["value"] = _sub(cnd.get("value", ""), v)
                cnd["value2"] = _sub(cnd.get("value2", ""), v)
                if had_var and not str(cnd["value"]).strip() and "{{ENROLLED_STATUS_CODES}}" in orig:
                    continue  # optional district setting left blank -> skip this condition
                kept.append(cnd)
            g["conditions"] = kept
        q["filters"] = [g for g in q.get("filters", []) if g.get("conditions")]
        for l in q.get("links", []):
            for cnd in l.get("conditions", []):
                cnd["value"] = _sub(cnd.get("value", ""), v)
                cnd["value2"] = _sub(cnd.get("value2", ""), v)
        for p in q.get("union_parts", []):
            walk(p)

    walk(d)
    return QueryDef.from_dict(d)


def _part_dict(p: Part) -> dict:
    return {"kind": p.kind, "alias": p.alias, "column": p.column, "value": p.value,
            "formats": [{"type": f.type, "a": f.a, "b": f.b} for f in p.formats]}
