"""SAM setup check - reads the results of the 'SAM setup check' queries (CSV files, or run live through the
optional read-only connection) and checks the assumptions the export packages make about this district's data.
Returns findings and suggested District Settings."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

FILES = ["check_owner_types.csv", "check_owner_type_usage.csv", "check_enrollment_status.csv",
         "check_live_schedules.csv", "check_data_summary.csv", "check_registration_codes.csv",
         "check_code_values.csv"]
FLAG_OK = {"", "0", "1", "y", "n", "t", "f", "true", "false", "yes", "no"}
GRADES_EXPECTED = {"PK", "KG", "K", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"}


@dataclass
class Finding:
    level: str          # ok | info | warn | error
    area: str
    message: str


@dataclass
class Result:
    findings: list = field(default_factory=list)
    suggest: dict = field(default_factory=dict)       # district settings to apply
    missing: list = field(default_factory=list)

    def add(self, level, area, msg):
        self.findings.append(Finding(level, area, msg))

    @property
    def errors(self):
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.level == "warn"]


# ----------------------------------------------------------------------------- loading results
def load_folder(folder) -> dict:
    from .filediff import read_csv
    out = {}
    for name in FILES:
        p = Path(folder) / name
        if not p.exists():
            alt = next((x for x in Path(folder).glob("*.csv") if x.name.lower() == name), None)
            p = alt or p
        if p.exists():
            out[name] = read_csv(p)[1]
    return out


def run_live(settings: dict) -> dict:
    """Run the check queries through the read-only SAM connection."""
    from . import samdb
    from .exports import build_query, load_platforms
    from .query_model import generate_sql
    plat = next(p for p in load_platforms() if p["id"] == "samcheck")
    out = {}
    for fe in plat["files"]:
        res = samdb.run(settings, generate_sql(build_query(plat, fe, settings), header=False), max_rows=5000,
                        count=False)
        out[fe["file"]] = [{h: ("" if v is None else str(v)) for h, v in zip(res["headings"], r)} for r in res["rows"]]
    return out


def _int(v):
    try:
        return int(float(str(v).strip() or 0))
    except ValueError:
        return 0


# ----------------------------------------------------------------------------- analysis
def analyze(data: dict, settings: dict, today: dt.date | None = None) -> Result:
    from . import district
    today = today or dt.date.today()
    ds = district.get(settings)
    r = Result(missing=[f for f in FILES if f not in data])
    for f in r.missing:
        r.add("info", "Files", f"{f} was not found - that part of the check was skipped.")

    # -- owner types
    if "check_owner_types.csv" in data:
        usage: dict[str, dict[str, int]] = {}
        for row in data.get("check_owner_type_usage.csv", []):
            usage.setdefault(str(row.get("OwnerType", "")).strip(), {})[row.get("Table", "")] = _int(row.get("Rows"))
        guess = {}
        for row in data["check_owner_types.csv"]:
            code = str(row.get("Code", "")).strip()
            text = f"{row.get('Description', '')} {row.get('Table', '')}".lower()
            for role, words in (("student", ("student",)), ("contact", ("contact", "parent", "guardian")),
                                ("employee", ("employee", "staff", "teacher"))):
                if any(w in text for w in words) and role not in guess:
                    guess[role] = code
        for role in ("student", "contact", "employee"):
            key = f"owner_type_{role}"
            cur = str(ds.get(key, "")).strip()
            g = guess.get(role)
            used = usage.get(cur, {}) if cur else {}
            if not cur and g:
                r.suggest[key] = g
                r.add("warn", "Owner types", f"{role.title()} owner type is blank - SAM's OwnerType table suggests "
                                             f"'{g}' ({_usage_text(usage.get(g, {}))}).")
            elif not cur:
                r.add("warn", "Owner types", f"{role.title()} owner type is blank and could not be found in the "
                                             "OwnerType table - look it up in check_owner_types.csv.")
            elif g and g != cur:
                r.add("warn", "Owner types", f"{role.title()} owner type is '{cur}' but the OwnerType table "
                                             f"describes '{g}' as {role}. Check which is right.")
                r.suggest[key] = g
            elif usage and not any(used.values()):
                r.add("error", "Owner types", f"{role.title()} owner type '{cur}' has no phones, emails or "
                                              "addresses in SAM - that's probably the wrong code.")
            else:
                r.add("ok", "Owner types", f"{role.title()} owner type '{cur}' is used ({_usage_text(used)}).")

    # -- enrollment status
    rows = data.get("check_enrollment_status.csv")
    if rows is not None:
        counts = {str(x.get("EnrollmentStatus", "")).strip(): _int(x.get("Students")) for x in rows}
        listing = ", ".join(f"{k or '(blank)'}: {v:,}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
        cur = [c.strip() for c in str(ds.get("enrolled_status_codes", "")).split(",") if c.strip()]
        if not cur and counts:
            top = max(counts, key=counts.get)
            r.suggest["enrolled_status_codes"] = top
            r.add("warn", "Enrollment", f"Enrolled status code is blank, so every student (also withdrawn) is "
                                        f"exported. Most students have '{top}' - is that 'enrolled'? ({listing})")
        else:
            bad = [c for c in cur if c not in counts]
            if bad:
                r.add("error", "Enrollment", f"Enrolled code(s) {', '.join(bad)} are not used by any student. "
                                             f"Values in SAM: {listing}")
            else:
                n = sum(counts[c] for c in cur)
                r.add("ok", "Enrollment", f"Enrolled code(s) {', '.join(cur)} match {n:,} students. ({listing})")

    # -- live schedules
    rows = data.get("check_live_schedules.csv")
    if rows is not None:
        by_school: dict[str, list] = {}
        for x in rows:
            by_school.setdefault(x.get("School", ""), []).append(x)
        if not rows:
            r.add("error", "Live schedule", "No schedule is marked Live - every class, homeroom and roster file "
                                            "will be empty.")
        known = {str(s.get("name", "")).strip(): s for s in settings.get("schools", [])}
        for school, lst in sorted(by_school.items()):
            active = str(lst[0].get("SchoolActive", "1")).strip() in ("1", "True", "true", "")
            if len(lst) > 1:
                r.add("warn", "Live schedule", f"{school}: {len(lst)} live schedules - classes may be listed twice.")
            for x in lst:
                try:
                    end = dt.date.fromisoformat(str(x.get("EndDate", ""))[:10])
                except ValueError:
                    end = None
                if end and end < today:
                    r.add("warn", "Live schedule", f"{school}: live schedule {x.get('ScheduleCode', '')} ended "
                                                   f"{end:%m/%d/%Y} - last year's schedule is still live.")
            if active and len(lst) == 1:
                r.add("ok", "Live schedule", f"{school}: one live schedule ({lst[0].get('ScheduleCode', '')}).")
        missing = [n for n in known if n and n not in by_school]
        if missing:
            r.add("warn", "Live schedule", "Schools with no live schedule: " + ", ".join(missing))

    # -- summary counts
    rows = data.get("check_data_summary.csv")
    if rows:
        s = {k: _int(v) for k, v in rows[0].items()}
        tot = s.get("Students", 0)
        if s.get("StudentsSeveralPrimarySchools"):
            r.add("error", "Schools", f"{s['StudentsSeveralPrimarySchools']:,} students have more than one primary "
                                      "school - they appear twice in student files.")
        if s.get("StudentsNoPrimarySchool"):
            r.add("info", "Schools", f"{s['StudentsNoPrimarySchool']:,} of {tot:,} students (often withdrawn ones) "
                                     "have no primary school and are left out of student files.")
        if s.get("StudentsWithContacts") and not s.get("StudentsWithPrimaryContact"):
            r.add("error", "Contacts", "No contact is marked Primary - 'primary guardian' columns will be blank. "
                                       "Mark primary contacts in SAM, or change those packages to use Sequence 1.")
        elif s.get("StudentsWithContacts"):
            pct = 100 * s["StudentsWithPrimaryContact"] / max(1, s["StudentsWithContacts"])
            r.add("ok" if pct >= 90 else "warn", "Contacts",
                  f"{pct:.0f}% of students with contacts have a primary contact.")
        if s.get("StudentsSeveralPrimaryContacts"):
            r.add("warn", "Contacts", f"{s['StudentsSeveralPrimaryContacts']:,} students have more than one primary "
                                      "contact - one-row-per-student files may repeat them (the checker flags it).")
        if not s.get("RosterRowsLive"):
            r.add("error", "Rosters", "No class roster rows on the live schedule - enrollment files will be empty.")
        elif not s.get("RosterRowsLiveWithdrawn"):
            r.add("warn", "Rosters", "No live roster row has a Withdrawn Date - if your district drops students from "
                                     "classes another way, dropped students may stay in class files.")
        else:
            r.add("ok", "Rosters", f"{s['RosterRowsLive']:,} live roster rows; {s['RosterRowsLiveWithdrawn']:,} "
                                   "withdrawn rows are excluded.")
        if not s.get("HomeroomRowsLive"):
            r.add("warn", "Homerooms", "No homerooms on the live schedule - homeroom columns will be blank.")
        if s.get("HomeroomRowsLive") and not s.get("HomeroomRowsWithCounselor"):
            r.add("info", "Homerooms", "No counselors are set on homerooms - counselor caseloads (Xello, Naviance, "
                                       "SchooLinks, Scoir) will be empty.")
        if not s.get("StaffActiveFaculty"):
            r.add("error", "Staff", "No active staff have FacultyFlag = 1 - teacher files will be empty.")
        if s.get("StaffActiveNoPrimarySchool"):
            r.add("warn", "Staff", f"{s['StaffActiveNoPrimarySchool']:,} active staff have no primary school and are "
                                   "left out of staff files (see Data cleanup reports).")
        if s.get("SectionsLiveNoTeacher"):
            r.add("warn", "Classes", f"{s['SectionsLiveNoTeacher']:,} live sections have no teacher and are dropped "
                                     "by most rostering files.")
        if not s.get("RegistrationRowsLast60Days"):
            r.add("warn", "Account shutoff", "No StudentRegistration rows in the last 60 days - the account shutoff "
                                             "list may not find students who left. Confirm where withdrawals are kept.")
        src = ds.get("student_email_source", "pattern")
        if src == "sam" and not s.get("StudentsWithEmailInSAM"):
            r.add("error", "Email", "District Settings use the student email stored in SAM, but no student has one.")
        elif src != "sam" and s.get("StudentsWithEmailInSAM", 0) > tot * 0.8 > 0:
            r.add("info", "Email", "Most students have an email stored in SAM - you could use it instead of the "
                                   "username pattern (District Settings > Student email comes from).")

    # -- registration codes
    rows = data.get("check_registration_codes.csv")
    if rows is not None:
        wd = sorted({x.get("RegistrationCode", "") for x in rows if str(x.get("WithdrawalReason", "")).strip()})
        r.add("info", "Account shutoff", "Registration codes used in the last year: " +
              ", ".join(sorted({x.get('RegistrationCode', '') for x in rows})) +
              (f". Codes with a withdrawal reason: {', '.join(wd)}." if wd else "."))

    # -- code values
    rows = data.get("check_code_values.csv")
    if rows is not None:
        vals: dict[str, dict[str, int]] = {}
        for x in rows:
            vals.setdefault(x.get("Field", ""), {})[str(x.get("Value", "")).strip()] = _int(x.get("Rows"))
        for fld in ("Student.Flag504", "Course.CoreCourse", "Course.DualCreditReported", "StudentContact.CheckInOut",
                    "StudentContact.NoContact", "Employee.FacultyFlag"):
            odd = [v for v in vals.get(fld, {}) if v.lower() not in FLAG_OK]
            if odd:
                r.add("warn", "Flags", f"{fld} uses {', '.join(odd)} - packages treat only 1/Y/T as yes.")
        grades = set(vals.get("Student.ADAGrade", {}))
        odd = sorted(g for g in grades - GRADES_EXPECTED if g)
        if odd:
            r.add("warn", "Grades", f"Grade codes {', '.join(odd)} are not the usual PK/KG/01-12 - grade filters and "
                                    "translations in packages (e.g. '09,10,11,12') may need changing.")
        elif grades:
            r.add("ok", "Grades", "Grade codes are the usual PK/KG/01-12.")
        g = set(vals.get("Student.GenderCode", {})) - {"M", "F", ""}
        if g:
            r.add("info", "Gender", f"Gender codes besides M/F: {', '.join(sorted(g))} - check packages that only "
                                    "accept M/F (College Board uses A, Naviance X, PBIS Rewards X/N).")
        for fld, label in (("Student.SPEDStatus", "Special education"), ("Student.FoodServiceCode", "Meal status"),
                           ("Student.LangBackground", "Home language")):
            if vals.get(fld):
                top = sorted(vals[fld].items(), key=lambda kv: -kv[1])[:8]
                r.add("info", "Codes", f"{label} values: " + ", ".join(f"{k or '(blank)'} ({v:,})" for k, v in top))
    return r


def _usage_text(u: dict) -> str:
    return ", ".join(f"{n:,} {t.replace('Relationship', '').replace('EmailAddress', 'email')}"
                     for t, n in u.items() if n) or "no rows"


def store_summary(settings: dict, res: Result):
    settings["sam_check"] = {"when": dt.datetime.now().isoformat(timespec="seconds"), "errors": len(res.errors),
                             "warnings": len(res.warnings)}
