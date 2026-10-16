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
    "registration": ("Registration codes (entry / withdrawal)",
                     [("StudentRegistration", "RegistrationCode"), ("EnrollmentAudit", "OldRegistrationCode"),
                      ("EnrollmentAudit", "NewRegistrationCode"), ("RegistrationCodes", "Code")]),
}
# extra columns some lists keep (shown in SAM Codes & Schools): key -> [(field, heading)]
EXTRA_COLUMNS = {"registration": [("direction", "In / Out"), ("active", "Active")]}
# which helper-query file fills which set
FILE_HINTS = {"enrollment_status": "enrollment", "grade": "grade", "gender": "gender", "race": "race",
              "owner_type": "owner_type", "relationship": "relationship", "phone_type": "phone_type",
              "roster_status": "roster_status", "attendance": "attendance", "registration": "registration",
              "school": "schools"}
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
            row = {"code": code, "description": _pick(r, "Description", "Desc", "AttendanceDescription", "Name"),
                   "table": _pick(r, "Table", "TableName")}
            for k, names in (("direction", ("In / Out", "InOut", "InOutDirection", "Direction")),
                             ("active", ("Active",))):
                v = _pick(r, *names)
                if v:
                    row[k] = v
            out.append(row)
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


# ----------------------------------------------------------------- queries that pull these lists from SAM
# file name each list's own helper query saves to (matches the 'Find your SAM codes' package)
HELPER_FILES = {"schools": "school_list.csv", "grade": "grade_codes.csv", "enrollment": "enrollment_status_codes.csv",
                "gender": "gender_codes.csv", "race": "race_codes.csv", "owner_type": "owner_type_codes.csv",
                "relationship": "relationship_codes.csv", "phone_type": "phone_type_codes.csv",
                "roster_status": "roster_status_codes.csv", "attendance": "attendance_codes.csv",
                "registration": "registration_codes.csv"}
ALL_IN_ONE_FILE = "sam_all_codes.csv"
# value in the List column of the all-in-one query -> set key
ALL_LISTS = {"Schools": "schools", "Grade levels": "grade", "Enrollment status": "enrollment", "Gender": "gender",
             "Race": "race", "Owner types": "owner_type", "Contact relationships": "relationship",
             "Phone types": "phone_type", "Schedule roster status": "roster_status",
             "Attendance codes": "attendance", "Registration codes": "registration"}
_ALL_PARTS = [  # (list name, FROM table, code expr, description expr, extra1, extra2, distinct)
    ("Schools", "SchoolDef", "SchoolID", "SchoolName", "SchoolCode", "ShortName", False),
    ("Grade levels", "lookupADAGrade", "Val", "Description", None, None, False),
    ("Enrollment status", "lookupEnrollmentStatus", "Val", "Description", None, None, False),
    ("Gender", "lookupGenderCode", "Val", "Description", None, None, False),
    ("Race", "lookupRaceCode", "Val", "Description", None, None, False),
    ("Owner types", "OwnerType", "Val", "Description", "TableName", None, False),
    ("Contact relationships", "lookupRelationshipType", "Val", "Description", None, None, False),
    ("Phone types", "lookupPhoneType", "Val", "Description", None, None, False),
    ("Schedule roster status", "LookupRosterStatus", "Val", "Description", None, None, False),
    ("Attendance codes", "AttendanceCodes", "AttendanceCode", "AttendanceDescription", None, None, True),
    ("Registration codes", "RegistrationCodes", "Code", "Description", "InOutDirection", "Active", False),
]


def _v(col, n=100):
    # COLLATE DATABASE_DEFAULT avoids "cannot resolve collation conflict" when the tables differ
    return f"LTRIM(RTRIM(CAST({col} AS VARCHAR({n})))) COLLATE DATABASE_DEFAULT" if col else "''"


def all_in_one_sql(header: bool = True) -> str:
    """One query that returns every list (schools + all code sets) in one result: List, Code, Description,
    Extra1, Extra2. Run once in SAM, save as sam_all_codes.csv, import."""
    parts = []
    for name, table, code, desc, e1, e2, distinct in _ALL_PARTS:
        parts.append(f"SELECT {'DISTINCT ' if distinct else ''}'{name}' AS List, {_v(code, 50)} AS Code, "
                     f"{_v(desc, 200)} AS Description, {_v(e1, 100)} AS Extra1, {_v(e2, 100)} AS Extra2\n"
                     f"FROM {table}")
    sql = "\nUNION ALL\n".join(parts) + "\nORDER BY List, Code"
    if header:
        sql = ("-- SAM Ad Hoc Query Builder: all schools and code lists in one result\n"
               f"-- Run in SAM (Ad Hoc Query > Query > paste > Run Query) and save the results as {ALL_IN_ONE_FILE}\n"
               "-- Extra1 = school code (Schools), table name (Owner types) or in/out direction (Registration codes)\n"
               "-- Extra2 = school short name (Schools) or Active (Registration codes)\n" + sql)
    return sql


def helper_queries(settings: dict) -> dict:
    """{set key: {'title', 'file', 'sql'}} - one SAM query per list, from the 'Find your SAM codes' package."""
    from .exports import build_query, load_platforms
    from .query_model import generate_sql
    p = next((x for x in load_platforms(include_custom=False) if x["id"] == "codes"), None)
    out = {}
    if not p:
        return out
    by_file = {fe["file"]: fe for fe in p["files"]}
    for key, fname in HELPER_FILES.items():
        fe = by_file.get(fname)
        if fe:
            q = build_query(p, fe, settings, use_override=False)
            out[key] = {"title": q.name, "file": fname, "sql": generate_sql(q)}
    return out


def is_all_in_one(rows: list[dict]) -> bool:
    return bool(rows) and any(k.strip().lower() == "list" for k in rows[0]) and any(
        k.strip().lower() == "code" for k in rows[0])


def parse_all_in_one(path_or_text: str) -> dict:
    """{set key: rows} from the all-in-one result (schools use the school row shape)."""
    lookup = {k.lower(): v for k, v in ALL_LISTS.items()}
    lookup.update({v: v for v in ALL_LISTS.values()})
    out: dict = {}
    for r in _read_csv(path_or_text):
        key = lookup.get(_pick(r, "List").strip().lower())
        code = _pick(r, "Code")
        if not key or not code:
            continue
        if key == "schools":
            out.setdefault(key, []).append({"id": code, "name": _pick(r, "Description"), "code": _pick(r, "Extra1"),
                                            "short": _pick(r, "Extra2")})
        else:
            if key == "registration":
                row = {"code": code, "description": _pick(r, "Description"), "table": "",
                       "direction": _pick(r, "Extra1"), "active": _pick(r, "Extra2")}
            else:
                row = {"code": code, "description": _pick(r, "Description"), "table": _pick(r, "Extra1")}
            if row not in out.get(key, []):
                out.setdefault(key, []).append(row)
    return out


def save_helper_queries(settings: dict, folder) -> list[Path]:
    """Write the all-in-one query, one query per list and a short read-me to <folder>/SAM codes queries."""
    out = Path(folder) / "SAM codes queries"
    out.mkdir(parents=True, exist_ok=True)
    files = [out / "00 All codes in one.sql"]
    files[0].write_text(all_in_one_sql(), encoding="utf-8")
    labels = {"schools": "Schools", **{k: v[0] for k, v in CODE_SETS.items()}}
    lines = ["SAM codes and schools - helper queries", "=" * 50, "",
             "Quickest: run '00 All codes in one.sql' in SAM (Ad Hoc Query > Query > paste > Save > Run Query),",
             f"save the results as {ALL_IN_ONE_FILE}, then File > SAM Codes & Schools > Import CSV files.", "",
             "If SAM reports an error (a code table your SAM doesn't have), run the separate queries instead and",
             "save each result with the file name below. You can import all the CSV files at once.", ""]
    for i, (key, h) in enumerate(helper_queries(settings).items(), 1):
        p = out / f"{i:02d} {Path(h['file']).stem}.sql"
        p.write_text(h["sql"], encoding="utf-8")
        files.append(p)
        lines.append(f"{p.name:34} -> save as {h['file']:30} ({labels.get(key, key)})")
    rd = out / "READ ME.txt"
    rd.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return files + [rd]
