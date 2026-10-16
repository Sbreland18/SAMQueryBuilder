"""Your district's real SAM codes and schools.

Users run the 'Find your SAM codes' helper queries in SAM, save the results as CSV and load
them here (or type them in). The codes then appear as drop-downs in filters, fill District
Settings automatically, and let the Query Assistant use real grade codes and school names.

Stored in settings["codes"] = {set_name: [{"code": "...", "description": "..."}]}
and settings["schools"] = [{"id": "12", "name": "Hancock High School", "code": "010", "short": "HHS"}].
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

CODE_SETS = {
    "grade": ("Grade levels", [("Student", "ADAGrade"), ("Student", "ChronoGrade"), ("historyStudent", "ADAGrade"),
                               ("SchoolDef", "LowestGradeTaught"), ("SchoolDef", "HighestGradeTaught"),
                               ("lookupADAGrade", "Val")]),
    "enrollment": ("Enrollment status", [("Student", "EnrollmentStatus"), ("stuSchool", "EnrollmentStatus"),
                                         ("lookupEnrollmentStatus", "Val")]),
    "gender": ("Gender", [("Student", "GenderCode"), ("Employee", "SexCode"), ("lookupGenderCode", "Val")]),
    "race": ("Race", [("Student", "RaceCode"), ("Employee", "RaceCode"), ("stuMultiRace", "RaceCode"),
                      ("lookupRaceCode", "Val")]),
    "owner_type": ("Owner types (addresses / phones / emails)", [("AddressRelationship", "OwnerType"),
                                                                ("PhoneRelationship", "OwnerType"),
                                                                ("EmailAddress", "OwnerType"), ("OwnerType", "Val")]),
    "relationship": ("Contact relationships", [("StudentContact", "RelationshipCode"),
                                               ("lookupRelationshipType", "Val")]),
    "phone_type": ("Phone types", [("PhoneNumber", "PhoneType"), ("lookupPhoneType", "Val")]),
    "roster_status": ("Schedule roster status", [("ScheduleRoster", "Status"), ("LookupRosterStatus", "Val")]),
    "attendance": ("Attendance codes", [("AttendanceDaily", "AttendanceCode"), ("AttendancePeriod", "AttendanceCode"),
                                        ("AttendanceCodes", "AttendanceCode")]),
}
# which helper-query file fills which set
FILE_HINTS = {"enrollment_status": "enrollment", "grade": "grade", "gender": "gender", "race": "race",
              "owner_type": "owner_type", "relationship": "relationship", "phone_type": "phone_type",
              "roster_status": "roster_status", "attendance": "attendance", "school": "schools"}
SCHOOL_COLUMNS = [("SchoolDef", "SchoolID"), ("stuSchool", "SchoolID"), ("empSchool", "SchoolID"),
                  ("Schedule", "SchoolID"), ("AttendanceDaily", "SchoolID"), ("historyStudentSessions", "SchoolID"),
                  ("empPositions", "SchoolID"), ("AcademicSessions", "SchoolID")]


def code_set_for(table: str, column: str) -> str | None:
    if (table, column) in SCHOOL_COLUMNS or column == "SchoolID":
        return "schools"
    for name, (_label, targets) in CODE_SETS.items():
        if (table, column) in targets:
            return name
    return None


def options(settings: dict, set_name: str) -> list[tuple[str, str]]:
    """[(code, label)] for a code set (schools use their SchoolID)."""
    if set_name == "schools":
        return [(str(s["id"]), s.get("name", "")) for s in settings.get("schools", []) if str(s.get("id", "")).strip()]
    return [(str(c["code"]), c.get("description", "")) for c in settings.get("codes", {}).get(set_name, [])]


def _read_csv(path_or_text: str) -> list[dict]:
    p = Path(path_or_text)
    if len(path_or_text) < 400 and p.exists():
        text = p.read_text(encoding="utf-8-sig", errors="replace")
    else:
        text = path_or_text
    sample = text[:2000]
    delim = "\t" if sample.count("\t") > sample.count(",") else ("|" if sample.count("|") > sample.count(",") else ",")
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(io.StringIO(text), delimiter=delim)]


def _pick(row: dict, *names):
    low = {k.lower().replace(" ", "").replace("_", ""): v for k, v in row.items()}
    for n in names:
        v = low.get(n.lower().replace(" ", "").replace("_", ""))
        if v not in (None, ""):
            return v
    return ""


def guess_set(filename: str, rows: list[dict]) -> str | None:
    f = Path(filename).stem.lower()
    for hint, name in FILE_HINTS.items():
        if hint in f:
            return name
    if rows and any(k.lower().replace(" ", "") in ("schoolid",) for k in rows[0]):
        return "schools"
    return None


def parse_codes(path_or_text: str) -> list[dict]:
    out = []
    for r in _read_csv(path_or_text):
        code = _pick(r, "Code", "Val", "Value", "AttendanceCode")
        if code:
            out.append({"code": code, "description": _pick(r, "Description", "Desc", "AttendanceDescription", "Name"),
                        "table": _pick(r, "Table", "TableName")})
    return out


def parse_schools(path_or_text: str) -> list[dict]:
    out = []
    for r in _read_csv(path_or_text):
        sid = _pick(r, "SchoolID", "School ID", "ID")
        if sid:
            out.append({"id": sid, "name": _pick(r, "School Name", "SchoolName", "Name"),
                        "code": _pick(r, "School Code", "SchoolCode", "Code"),
                        "short": _pick(r, "Short Name", "ShortName", "Short")})
    return out


def suggest_district_settings(settings: dict) -> dict:
    """Fill blank District Settings from loaded codes (owner types, enrolled status)."""
    from . import district
    ds = dict(settings.get("district") or {})
    changes = {}
    owners = settings.get("codes", {}).get("owner_type", [])
    for key, words in (("owner_type_student", ("student",)), ("owner_type_contact", ("contact", "parent", "guardian")),
                       ("owner_type_employee", ("employee", "staff"))):
        if str(ds.get(key, "")).strip():
            continue
        for c in owners:
            text = f"{c.get('description', '')} {c.get('table', '')}".lower()
            if any(w in text for w in words) and not ("contact" in text and key == "owner_type_student"):
                changes[key] = c["code"]
                break
    if not str(ds.get("enrolled_status_codes", "")).strip():
        enrolled = [c["code"] for c in settings.get("codes", {}).get("enrollment", [])
                    if re.search(r"\benrolled\b|\bactive\b", c.get("description", "").lower())
                    and not re.search(r"\b(not|un|non|no longer|pre)", c.get("description", "").lower())]
        if enrolled:
            changes["enrolled_status_codes"] = ", ".join(enrolled)
    return changes


def grade_code(settings: dict, n: str) -> str | None:
    """Map a grade like '9', 'KG', 'PK' to the district's real grade code (when grade codes are loaded)."""
    codes = settings.get("codes", {}).get("grade", [])
    if not codes:
        return None
    n = n.upper()
    for c in codes:
        code = c["code"].upper().strip()
        desc = c.get("description", "").lower()
        if n in ("KG", "K"):
            if code in ("KG", "K", "00", "0") or "kindergarten" in desc and "pre" not in desc and "trans" not in desc:
                return c["code"]
        elif n == "PK":
            if code in ("PK", "P", "PRE-K", "PREK") or "pre" in desc and "k" in desc:
                return c["code"]
        else:
            if code.lstrip("0") == n.lstrip("0") and code.isdigit():
                return c["code"]
    return None


def match_schools(settings: dict, phrase: str) -> list[dict]:
    """Schools whose name/short name/code matches a phrase like 'westside' or 'the high school'."""
    words = [w for w in re.findall(r"[a-z0-9]+", phrase.lower()) if w not in ("the", "school", "of", "at")]
    if not words:
        return []
    hits = []
    for s in settings.get("schools", []):
        hay = f"{s.get('name', '')} {s.get('short', '')} {s.get('code', '')}".lower()
        if all(re.search(rf"\b{re.escape(w)}", hay) for w in words):
            hits.append(s)
    return hits
