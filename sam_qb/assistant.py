"""Query Assistant - built-in (offline) natural-language query builder.

How it reads a request
----------------------
1. normalize   - lower-case, strip filler ("I would like a query of"), apply the vocabulary's
                 replacements (studentID -> student id, seniors -> 12th grade, e-mail -> email...)
                 and fix likely typos against the known vocabulary.
2. subject     - who each row is about: students (default), parents of students, or staff.
3. columns     - if the request lists what to show ("with their homeroom, first name, last name,
                 studentID and email") those columns are used, in that order. Each item is resolved
                 to an owner (student / parent / homeroom teacher / counselor / teacher / school)
                 plus a field (first name, email, phone, ...). Unknown items are fuzzy-matched
                 against the real SAMS column names.
4. filters     - grade ranges and lists, class years, school levels, school names, gender,
                 enrollment, attendance dates, birth years, GPA comparisons, program flags,
                 missing data ("without an email"), course and teacher names, negation.
5. shape       - counts/averages per group ("how many ... per grade"), top N, distinct, sort.
6. build       - adds tables and links (with the right ON conditions), then checks that every
                 table is connected.

Vocabulary lives in data/assistant_vocab.json, so new phrases can be shipped with a data update.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field

from . import district
from .paths import active_data_file
from .query_model import Condition, FilterGroup, Fmt, Link, OutColumn, Part, QueryDef, SortItem, TableRef


@dataclass
class Plan:
    query: QueryDef
    understood: list = field(default_factory=list)
    unsure: list = field(default_factory=list)
    source: str = "Built-in helper"
    summary: str = ""


EXAMPLES = [
    "All 9th - 12th grade students with their homeroom, first name, last name, studentID and email",
    "Student schedules for grades 6-8 with teacher, period and room",
    "Parents of kindergarten students with phone numbers and emails",
    "How many students are in each grade at each school",
    "Students absent in the last 7 days with the attendance code description",
    "Top 10 seniors by GPA with their birth dates",
    "Teachers at each school with their email addresses",
    "Students in Algebra I without an email address",
]

GRADE_NAMES = {"KG": "Kindergarten", "PK": "Pre-K"}
LEVELS = {"high": ["09", "10", "11", "12"], "middle": ["06", "07", "08"], "elementary": ["KG", "01", "02", "03", "04", "05"]}
STOP_WORDS = set("""a an the of for to in on at by with and or but not all any each every their his her its our my
your this that these those who whose which what where when is are was were be been being have has had do does
did only also just than then from into as per vs versus about over under above below between through thru
students student list show give include including showing""".split())


AMBIGUOUS = {"middle", "first", "last", "name", "names", "number", "numbers", "code", "date", "status", "zone",
             "route", "routes", "class", "course", "subject", "section", "room", "period", "description", "reason",
             "enrollment", "born", "credit", "credits", "pin", "id", "school", "building", "campus", "town", "relation",
             "relationship", "language", "login", "eligibility", "residence", "emergency", "schedule", "teacher",
             "instructor", "zip", "city", "age", "ages"}


def _vocab():
    try:
        return json.loads(active_data_file("assistant_vocab.json").read_text(encoding="utf-8"))
    except Exception:
        return {"fillers": [], "replacements": {}, "owners": {}, "fields": {}}


def _g(tok: str) -> str | None:
    """Grade token -> SAM grade code (assumed KG, PK, 01..12)."""
    tok = tok.lower().strip().rstrip(".")
    tok = re.sub(r"(st|nd|rd|th)$", "", tok)
    if tok in ("k", "kg", "kindergarten"):
        return "KG"
    if tok in ("pk", "prek", "pre-k", "pre-kindergarten", "prekindergarten"):
        return "PK"
    if tok.isdigit() and 1 <= int(tok) <= 12:
        return f"{int(tok):02d}"
    return None


ORDER = ["PK", "KG"] + [f"{i:02d}" for i in range(1, 13)]


def _grade_range(a: str, b: str) -> list[str]:
    ia, ib = ORDER.index(a), ORDER.index(b)
    if ia > ib:
        ia, ib = ib, ia
    return ORDER[ia:ib + 1]


GTOK = r"(?:pre-?k|pk|k|kg|kindergarten|\d{1,2}(?:st|nd|rd|th)?)"


# =============================================================================== text normalisation
class Normalizer:
    def __init__(self, vocab):
        self.v = vocab
        self.reps = sorted(vocab.get("replacements", {}).items(), key=lambda kv: -len(kv[0]))
        words = set()
        for group in ("fields", "owners"):
            for phrases in vocab.get(group, {}).values():
                for p in phrases:
                    words.update(p.split())
        for k, val in vocab.get("replacements", {}).items():
            words.update(k.split())
            words.update(val.split())
        numberish = {"first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
                     "eleventh", "twelfth", "senior", "seniors", "junior", "juniors", "freshman", "freshmen",
                     "sophomore", "sophomores", "mother", "father", "moms", "dads"}
        self.vocab_words = {w for w in words if len(w) > 3 and w.isalpha() and w not in numberish}
        words.update(STOP_WORDS)
        words.update("""homeroom sorted ordered order sort grouped group alphabetical alphabetically absent tardy enrolled
        active withdrawn current elementary middle high school schools boys girls male female taking taught class
        roster rosters count many number total average how top first last most least highest lowest without missing
        blank empty except excluding born before after since today yesterday week month year days past""".split())
        self.known = {w for w in words if len(w) > 2}
        self.notes: list[str] = []

    def __call__(self, text: str) -> str:
        text = self._typos(text.replace("’", "'").replace("“", '"').replace("”", '"'))
        t = " " + text.lower() + " "
        t = t.replace("&", " and ").replace("+", " and ")
        t = re.sub(r"\s+", " ", t)
        # strip filler at the start (repeat - "please can you give me a list of")
        changed = True
        fillers = sorted(self.v.get("fillers", []), key=len, reverse=True)
        while changed:
            changed = False
            s = t.strip()
            for f in fillers:
                if s.startswith(f + " ") or s == f:
                    t = " " + s[len(f):] + " "
                    changed = True
                    break
        for k, val in self.reps:
            t = re.sub(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", val, t)
        return re.sub(r"\s+", " ", t)

    NAME_TRIGGERS = {"named", "is", "mr", "mrs", "ms", "miss", "dr", "coach", "taking", "teacher", "at", "from",
                     "attending", "by", "called", "in"}

    def _typos(self, text):
        """Fix likely misspellings of vocabulary words. Capitalised words (names, schools) and words right
        after 'named', 'Mrs.', 'taking'... are left alone."""
        tokens = list(re.finditer(r"[A-Za-z']+", text))
        out, last = [], 0
        for i, m in enumerate(tokens):
            w = m.group(0)
            prev = tokens[i - 1].group(0).lower() if i else ""
            lw = w.lower()
            keep = (len(lw) < 4 or lw in self.known or not lw.replace("'", "").isalpha()
                    or (w[0].isupper() and i > 0) or prev in self.NAME_TRIGGERS)
            new = w
            if not keep:
                best = difflib.get_close_matches(lw, self.vocab_words, n=1, cutoff=0.78)
                if best and best[0] != lw:
                    self.notes.append(f"Read '{w}' as '{best[0]}'")
                    new = best[0]
            out.append(text[last:m.start()] + new)
            last = m.end()
        out.append(text[last:])
        return "".join(out)


# =============================================================================== builder
class Builder:
    def __init__(self, catalog, settings):
        self.cat = catalog
        self.settings = settings or {}
        self.ds = district.get(self.settings)
        self.v = _vocab()
        self.norm = Normalizer(self.v)
        self.q = QueryDef()
        self.understood: list[str] = []
        self.unsure: list[str] = []
        self.conds: list[Condition] = []
        self.any_groups: list[FilterGroup] = []
        self.sort: list[str] = []
        self.explicit = False
        self.field_phrases = sorted(((p, f) for f, ps in self.v.get("fields", {}).items() for p in ps),
                                    key=lambda x: -len(x[0]))
        self.owner_phrases = sorted(((p, o) for o, ps in self.v.get("owners", {}).items() for p in ps),
                                    key=lambda x: -len(x[0]))

    # ------------------------------------------------------------ low-level helpers
    def table(self, table, alias=None):
        alias = alias or table
        if not any(t.alias == alias for t in self.q.tables):
            self.q.tables.append(TableRef(alias, table))
        return alias

    def link(self, la, lc, ra, rc, join="INNER", conds=()):
        for l in self.q.links:
            if {l.left_alias, l.right_alias} == {la, ra}:
                return
        self.q.links.append(Link(la, lc, ra, rc, join, list(conds)))

    def col(self, alias, column, heading, *fmts, agg=""):
        for c in self.q.columns:
            if c.heading == heading:
                return heading
        self.q.columns.append(OutColumn("field", alias, column, heading, list(fmts), agg=agg))
        return heading

    def custom(self, heading, parts, agg=""):
        for c in self.q.columns:
            if c.heading == heading:
                return heading
        self.q.columns.append(OutColumn("custom", heading=heading, parts=parts, agg=agg))
        return heading

    def name_col(self, alias, heading):
        return self.custom(heading, [Part("field", alias, "LastName", formats=[Fmt("trim")]), Part("text", value=", "),
                                     Part("field", alias, "FirstName", formats=[Fmt("trim")])])

    def phone_parts(self, alias):
        return [Part("text", value="("), Part("field", alias, "AreaCode", formats=[Fmt("trim")]),
                Part("text", value=") "), Part("field", alias, "PhoneNumber", formats=[Fmt("trim")])]

    def owner_code(self, key, what):
        code = str(self.ds.get(key, "")).strip()
        if not code:
            msg = (f"{what} need the '{district.LABELS[key]}' District Setting. Fill it in (File > District "
                   "Settings), then build again.")
            if msg not in self.unsure:
                self.unsure.append(msg)
            return "{{" + key.upper() + "}}"
        return code

    def say(self, text):
        if text not in self.understood:
            self.understood.append(text)

    def check(self, text):
        if text not in self.unsure:
            self.unsure.append(text)

    # ------------------------------------------------------------ joins (owners)
    def student_school(self):
        self.table("stuSchool")
        self.table("SchoolDef")
        self.link("Student", "StudentID", "stuSchool", "StudentID")
        self.link("stuSchool", "SchoolID", "SchoolDef", "SchoolID")
        c = Condition("stuSchool", "PrimarySchoolFlag", "eq", "1")
        if not any(x.column == "PrimarySchoolFlag" for x in self.conds):
            self.conds.append(c)

    def staff_school(self):
        self.table("empSchool")
        self.table("SchoolDef")
        self.link("Employee", "EmployeeID", "empSchool", "EmployeeID")
        self.link("empSchool", "SchoolID", "SchoolDef", "SchoolID")
        if not any(x.column == "PrimarySchoolFlag" for x in self.conds):
            self.conds.append(Condition("empSchool", "PrimarySchoolFlag", "eq", "1"))

    LIVE_HR = "stuHRTeacher.ScheduleID IN (SELECT ScheduleID FROM Schedule WHERE LiveFlag = 1)"

    def homeroom(self):
        self.table("stuHRTeacher")
        self.table("Employee", "HomeroomTeacher")
        self.link("Student", "StudentID", "stuHRTeacher", "StudentID", "LEFT",
                  [Condition("stuHRTeacher", "ScheduleID", "raw", self.LIVE_HR)])
        self.link("stuHRTeacher", "HRTeacherID", "HomeroomTeacher", "EmployeeID", "LEFT")
        self.say("Homeroom teacher from the current (live) schedule: stuHRTeacher -> Employee")
        return "HomeroomTeacher"

    def counselor(self):
        self.table("stuHRTeacher")
        self.table("Employee", "Counselor")
        self.link("Student", "StudentID", "stuHRTeacher", "StudentID", "LEFT",
                  [Condition("stuHRTeacher", "ScheduleID", "raw", self.LIVE_HR)])
        self.link("stuHRTeacher", "CounselorID", "Counselor", "EmployeeID", "LEFT")
        self.say("Counselor: stuHRTeacher.CounselorID -> Employee")
        return "Counselor"

    def schedule(self):
        root_staff = self.subject == "staff"
        if not root_staff:
            self.table("ScheduleRoster")
            self.link("Student", "StudentID", "ScheduleRoster", "StudentID")
            self.link("ScheduleRoster", "ScheduleFrameworkID", "ScheduleFramework", "ScheduleFrameworkID")
            if not any(c.column == "WithdrawnDate" for c in self.conds):
                self.conds.append(Condition("ScheduleRoster", "WithdrawnDate", "blank"))
        for t in ("ScheduleFramework", "ScheduleCourseTerm", "ScheduleCourse", "Course", "Schedule"):
            self.table(t)
        self.link("ScheduleFramework", "ScheduleCourseTermID", "ScheduleCourseTerm", "ScheduleCourseTermID")
        self.link("ScheduleCourseTerm", "ScheduleCourseID", "ScheduleCourse", "ScheduleCourseID")
        self.link("ScheduleCourse", "CourseID", "Course", "CourseID")
        self.link("ScheduleCourse", "ScheduleID", "Schedule", "ScheduleID")
        if root_staff:
            self.link("Employee", "EmployeeID", "ScheduleFramework", "TeacherID")
        if not any(c.column == "LiveFlag" for c in self.conds):
            self.conds.append(Condition("Schedule", "LiveFlag", "eq", "1"))
        self.say("Classes from the live schedule" + ("" if root_staff else
                                                     " (Student -> Schedule Roster -> section -> course)"))

    def section_teacher(self):
        if self.subject == "staff":
            return "Employee"
        self.schedule()
        self.table("Employee", "Teacher")
        self.link("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "LEFT")
        return "Teacher"

    def parent(self, which=None):
        """Student -> StudentContact -> ContactInfo (alias Parent)."""
        self.table("StudentContact")
        self.table("ContactInfo", "Parent")
        cond = [Condition("StudentContact", "NoContact", "ne", "1")]
        if which == "primary":
            cond = [Condition("StudentContact", "PrimaryContact", "eq", "1")]
        self.link("Student", "StudentID", "StudentContact", "StudentID", "LEFT", cond)
        self.link("StudentContact", "ContactID", "Parent", "ContactID", "LEFT")
        return "Parent"

    def phone_of(self, owner_alias, id_col, owner_key, what, sfx):
        code = self.owner_code(owner_key, what)
        link, num = f"{sfx}PhoneLink", f"{sfx}Phone"
        self.table("PhoneRelationship", link)
        self.table("PhoneNumber", num)
        self.link(owner_alias, id_col, link, "OwnerID", "LEFT",
                  [Condition(link, "OwnerType", "eq", code), Condition(link, "PrimaryPhone", "eq", "1")])
        self.link(link, "PhoneNumberID", num, "PhoneNumberID", "LEFT")
        return num

    def email_of(self, owner_alias, id_col, owner_key, what, sfx):
        code = self.owner_code(owner_key, what)
        em = f"{sfx}Email"
        self.table("EmailAddress", em)
        self.link(owner_alias, id_col, em, "OwnerID", "LEFT",
                  [Condition(em, "OwnerType", "eq", code), Condition(em, "PrimaryAddress", "eq", "1")])
        return em

    def address_of(self, owner_alias, id_col, owner_key, what, sfx):
        code = self.owner_code(owner_key, what)
        link, ad = f"{sfx}AddressLink", f"{sfx}Address"
        self.table("AddressRelationship", link)
        self.table("Address", ad)
        self.link(owner_alias, id_col, link, "OwnerID", "LEFT",
                  [Condition(link, "OwnerType", "eq", code), Condition(link, "PrimaryAddress", "eq", "1")])
        self.link(link, "AddressID", ad, "AddressID", "LEFT")
        return ad

    def attendance(self):
        self.table("AttendanceDaily")
        self.table("AttendanceCodes")
        self.link("Student", "StudentID", "AttendanceDaily", "StudentID")
        self.link("AttendanceDaily", "AttendanceCode", "AttendanceCodes", "AttendanceCode", "LEFT")
        self.say("Daily attendance (AttendanceDaily + AttendanceCodes)")

    # ------------------------------------------------------------ fields
    def add_field(self, owner: str, fld: str, heading: str | None = None, agg: str = "") -> str | None:
        """Add one requested column. Returns its heading (or None if not possible)."""
        o = owner
        if o == "student" and self.subject == "staff":
            o = "staff"
        if o == "student" and self.subject == "parent" and fld in ("first_name", "last_name", "full_name", "email",
                                                                    "phone", "address", "city", "zip", "language"):
            o = "parent"
        if fld in ("homeroom", "homeroom_room", "counselor", "teacher", "course", "course_code", "period",
                   "section", "room", "schedule", "relationship", "emergency", "attendance_date", "attendance_code",
                   "attendance_desc") and o not in ("staff",):
            o = {"relationship": "parent", "emergency": "parent"}.get(fld, "student") if o in ("student", "parent") else o

        H = lambda default: heading or default  # noqa: E731

        # ---------------- school
        if fld in ("school", "school_code") or o == "school":
            if self.subject == "staff":
                self.staff_school()
            else:
                self.student_school()
            if fld == "school_code":
                return self.col("SchoolDef", "SchoolCode", H("School Code"), agg=agg)
            return self.col("SchoolDef", "SchoolName", H("School"), Fmt("trim"), agg=agg)

        # ---------------- people owned by a student
        if o in ("homeroom", "counselor", "teacher") or fld in ("homeroom", "counselor", "teacher"):
            who = o if o in ("homeroom", "counselor", "teacher") else fld
            alias = {"homeroom": self.homeroom, "counselor": self.counselor, "teacher": self.section_teacher}[who]()
            label = {"homeroom": "Homeroom Teacher", "counselor": "Counselor", "teacher": "Teacher"}[who]
            if fld == "homeroom_room" or (who == "homeroom" and fld == "room"):
                self.check("Homeroom room shows stuHRTeacher.HRRoomID (the room's ID). Link it to SchoolRoom in "
                           "Step 2 if you need the room name.")
                return self.col("stuHRTeacher", "HRRoomID", H("Homeroom Room"), agg=agg)
            return self._person_field(alias, "staff", fld if fld not in (who, "homeroom") else "full_name",
                                      label, heading, agg)

        if o == "parent":
            alias = self.parent()
            if fld not in ("full_name", "first_name", "last_name") and \
                    not any(c.heading == "Parent/Guardian" for c in self.q.columns):
                self.name_col("Parent", "Parent/Guardian")
            if fld == "emergency":
                self.conds.append(Condition("StudentContact", "EmergencyFlag", "eq", "1"))
                self.say("Emergency contacts only (StudentContact.EmergencyFlag = 1)")
                return self.col("StudentContact", "RelationshipCode", H("Relationship"), agg=agg)
            if fld == "relationship":
                return self.col("StudentContact", "RelationshipCode", H("Relationship"), agg=agg)
            return self._person_field(alias, "parent", fld, "Parent", heading, agg)

        if o == "staff":
            return self._person_field("Employee", "staff", fld, "", heading, agg)

        # ---------------- student
        return self._person_field("Student", "student", fld, "", heading, agg)

    def _person_field(self, alias, kind, fld, label, heading, agg=""):
        pre = (label + " ") if label else ""
        H = lambda default: heading or (pre + default if pre else default)  # noqa: E731
        table_cols = set(self.cat.columns(self._table_of(alias)))
        id_col = {"student": "StudentID", "staff": "EmployeeID", "parent": "ContactID"}[kind]
        owner_key = {"student": "owner_type_student", "staff": "owner_type_employee", "parent": "owner_type_contact"}[kind]
        sfx = {"student": "Student", "staff": "Staff" if alias == "Employee" else alias, "parent": "Parent"}[kind]
        whose = {"student": "Student", "staff": "Staff", "parent": "Parent"}[kind]

        if fld == "full_name":
            default = "Parent/Guardian" if kind == "parent" else (label or {"student": "Student", "staff": "Name"}[kind])
            return self.name_col(alias, heading or default)
        simple = {"first_name": ("FirstName", "First Name"), "last_name": ("LastName", "Last Name"),
                  "middle_name": ("MiddleName", "Middle Name"),
                  "preferred_name": ("PreferredName" if kind != "staff" else "EmpPreferredFirstName", "Preferred Name")}
        if fld in simple and simple[fld][0] in table_cols:
            c, h = simple[fld]
            return self.col(alias, c, H(h), Fmt("trim"), agg=agg)
        if fld == "student_id" or fld == "employee_number":
            if kind == "student":
                return self.col(alias, "StudentCode", H("Student ID"), Fmt("trim"), agg=agg)
            if kind == "staff":
                return self.col(alias, "EmployeeNumber", H("Employee #"), Fmt("trim"), agg=agg)
            return self.col(alias, "ContactID", H("Contact ID"), agg=agg)
        if fld == "email":
            if kind == "student":
                if self.ds.get("student_email_source") == "pattern" and self.settings.get("district_confirmed") \
                        and not self.settings.get("assistant_use_sam_email", True):
                    return self.custom(H("Email"), district.email_parts(alias, "student", self.ds), agg=agg)
                self.say("Student email = Student.EmailAddress stored in SAM")
                return self.col(alias, "EmailAddress", H("Email"), Fmt("trim"), Fmt("lower"), agg=agg)
            if kind == "staff":
                self.say(f"Staff email built from the staff username pattern @{self.ds['staff_email_domain']} "
                         "(District Settings)")
                return self.custom(H("Email"), district.email_parts(alias, "staff", self.ds), agg=agg)
            em = self.email_of(alias, id_col, owner_key, f"{whose} email addresses", sfx)
            self.say(f"{whose} email = primary email (EmailAddress)")
            return self.col(em, "Address", H("Email"), Fmt("trim"), Fmt("lower"), agg=agg)
        if fld == "phone":
            num = self.phone_of(alias, id_col, owner_key, f"{whose} phone numbers", sfx)
            self.say(f"{whose} phone = primary phone (PhoneRelationship -> PhoneNumber)")
            return self.custom(H("Phone"), self.phone_parts(num), agg=agg)
        if fld in ("address", "city", "zip"):
            ad = self.address_of(alias, id_col, owner_key, f"{whose} addresses", sfx)
            self.say(f"{whose} address = primary address (AddressRelationship -> Address)")
            if fld == "city":
                return self.col(ad, "City", H("City"), Fmt("trim"), agg=agg)
            if fld == "zip":
                return self.col(ad, "ZipCode", H("Zip"), agg=agg)
            first = self.col(ad, "AddrLine1", H("Address"), Fmt("trim"))
            self.col(ad, "AddrLine2", pre + "Address 2", Fmt("trim"))
            self.col(ad, "City", pre + "City", Fmt("trim"))
            self.col(ad, "State", pre + "State")
            self.col(ad, "ZipCode", pre + "Zip")
            return first
        if fld == "birth_date":
            return self.col(alias, "DOB", H("Birth Date"), Fmt("date_us"), agg=agg)
        if fld == "age":
            return self.col(alias, "DOB", H("Age"), Fmt("age"), agg=agg)
        if fld == "gender":
            return self.col(alias, "GenderCode" if kind == "student" else "SexCode", H("Gender"), agg=agg)
        if fld == "race":
            return self.col(alias, "RaceCode", H("Race"), agg=agg)
        if fld == "language":
            return self.col(alias, "PrimaryLanguage" if kind == "parent" else "LangBackground", H("Language"), agg=agg)
        if fld == "username" and kind in ("student", "staff"):
            return self.custom(H("Username"), district.username_parts(alias, kind, self.ds), agg=agg)
        if kind == "staff":
            if fld == "hire_date":
                return self.col(alias, "HireDate", H("Hire Date"), Fmt("date_us"), agg=agg)
            if fld in ("course", "course_code", "period", "section", "room", "schedule"):
                return self._class_field(fld, heading, agg)
        if kind == "student":
            stu = {
                "state_id": ("StateCode", "State ID", [Fmt("strip_zeros")]),
                "grade": ("ADAGrade", "Grade", []),
                "gpa": ("CumulativeGPA", "GPA", [Fmt("decimals", "2")]),
                "qpa": ("CumulativeQPA", "QPA", [Fmt("decimals", "2")]),
                "lunch_pin": ("LunchNumber", "Lunch PIN", [Fmt("trim")]),
                "meal_status": ("FoodServiceCode", "Meal Status", []),
                "enrollment_status": ("EnrollmentStatus", "Enrollment Status", []),
                "bus_zone": ("BusZone", "Bus Zone", []),
                "flag_504": ("Flag504", "504", [Fmt("yes_no")]),
                "sped": ("SPEDStatus", "SPED Status", []),
                "gifted": ("GiftedStatus", "Gifted Status", []),
                "title_one": ("TitleOneFlag", "Title I", [Fmt("yes_no")]),
                "foster": ("FosterChildFlag", "Foster", [Fmt("yes_no")]),
                "grad_year": ("OriginalGradDate", "Graduation Year", [Fmt("year")]),
                "ninth_year": ("YearEnteringNinth", "Year Entering 9th", []),
            }
            if fld in stu:
                c, h, f = stu[fld]
                return self.col(alias, c, H(h), *f, agg=agg)
            if fld == "transportation":
                first = None
                for c, h in (("TransportationCode", "Transportation Code"), ("AMTransMethod", "AM Method"),
                             ("PMTransMethod", "PM Method"), ("BusZone", "Bus Zone"), ("RouteMiles", "Route Miles")):
                    got = self.col(alias, c, h)
                    first = first or got
                self.say("Transportation columns from the Student table")
                return first
            if fld in ("course", "course_code", "period", "section", "room", "schedule"):
                return self._class_field(fld, heading, agg)
            if fld in ("attendance_date", "attendance_code", "attendance_desc"):
                self.attendance()
                c, h, f = {"attendance_date": ("AttendanceDate", "Date", [Fmt("date_us")]),
                           "attendance_code": ("AttendanceCode", "Code", []),
                           "attendance_desc": ("AttendanceDescription", "Attendance", [])}[fld]
                return self.col("AttendanceDaily" if fld != "attendance_desc" else "AttendanceCodes", c, H(h), *f,
                                agg=agg)
            if fld == "transcript":
                self.table("historyStudentSessions")
                self.table("historyStudentCourses")
                self.table("historyStudentCourseGrades")
                self.link("Student", "StudentID", "historyStudentSessions", "StudentID")
                self.link("historyStudentSessions", "HistSessionID", "historyStudentCourses", "HistSessionID")
                self.link("historyStudentCourses", "HistStuCourseID", "historyStudentCourseGrades", "histStuCourseID")
                self.col("historyStudentSessions", "Descr", "Session")
                self.col("historyStudentCourses", "LongName_Local", "Course", Fmt("trim"))
                self.col("historyStudentCourseGrades", "GradeNumeric", "Grade Earned")
                self.say("Transcript (historyStudentSessions -> Courses -> CourseGrades)")
                return self.col("historyStudentCourseGrades", "CreditHoursEarned", "Credits Earned")
        return None

    def _class_field(self, fld, heading, agg=""):
        self.schedule()
        c, h, f = {"course": ("LongName", "Course", [Fmt("trim")]), "course_code": ("CourseCode", "Course Code", []),
                   "period": ("Period", "Period", []), "section": ("SectionNumber", "Section", []),
                   "room": ("Room", "Room", []), "schedule": ("Period", "Period", [])}[fld]
        alias = "Course" if fld in ("course", "course_code") else "ScheduleFramework"
        out = self.col(alias, c, heading or h, *f, agg=agg)
        if fld == "schedule":
            self.col("Course", "LongName", "Course", Fmt("trim"))
            self.col("ScheduleFramework", "SectionNumber", "Section")
            self.name_col(self.section_teacher(), "Teacher")
        return out

    def _table_of(self, alias):
        return next((t.table for t in self.q.tables if t.alias == alias), alias)

    # ------------------------------------------------------------ resolving one requested item
    def resolve(self, item: str):
        """'parent email' -> ('parent', 'email');  'homeroom' -> ('student', 'homeroom')."""
        item = re.sub(r"^(?:their|the|a|an|his|her|its|each|every|all|also|any|students'|student's|and|with)\s+", "",
                      item.strip())
        item = re.sub(r"\s+(?:info|information|details|data)$", "", item).strip(" .")
        if not item:
            return None
        fld, owner, rest = None, None, item
        for p, f in self.field_phrases:
            if re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", item):
                fld, rest = f, re.sub(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", " ", item)
                break
        for p, o in self.owner_phrases:
            if re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", rest):
                owner = o
                break
        if fld is None and owner is None and re.search(r"s\b", item):
            singular = re.sub(r"(?<=[a-z]{3})s\b", "", item)
            if singular != item:
                return self.resolve(singular)
        if fld is None and owner:
            fld = {"parent": "full_name", "homeroom": "homeroom", "counselor": "counselor", "teacher": "teacher",
                   "school": "school", "student": "full_name"}[owner]
        if fld is None:
            return None
        if owner in (None, "student") and fld == "homeroom":
            owner = "student"
        return owner or "student", fld

    def fuzzy_column(self, item: str):
        """Last resort: match the words against real column names of the main table."""
        base = "Employee" if self.subject == "staff" else "Student"
        words = re.sub(r"[^a-z0-9 ]", " ", item.lower()).split()
        if not words:
            return None
        target = "".join(words)
        best, score = None, 0.0
        for c in self.cat.columns(base):
            name = c.lower()
            s = difflib.SequenceMatcher(None, target, name).ratio()
            if all(w in name for w in words):
                s = max(s, 0.9)
            if s > score:
                best, score = c, s
        if best and score >= 0.78:
            return base, best
        close = difflib.get_close_matches(target, [c.lower() for c in self.cat.columns(base)], n=3, cutoff=0.5)
        names = [c for c in self.cat.columns(base) if c.lower() in close]
        return None if not names else ("?", names)

    # ------------------------------------------------------------ main
    def build(self, messages: list[str]) -> Plan:
        messages = [m.strip().rstrip(".") for m in messages if m.strip()]
        raw = " . ".join(messages)
        norms = [self.norm(m) for m in messages] or [" "]
        t = " " + " . ".join(n.strip() for n in norms) + " "
        self.text = t
        for n in self.norm.notes:
            self.say(n)

        # remove/hide requests in follow-ups
        removals = []
        for m in re.finditer(r"\b(?:remove|drop|hide|delete|take out|get rid of|don't (?:show|include)|do not "
                             r"(?:show|include)|no need for|without the) ([a-z0-9 ,'/-]+?)(?: column| columns|\.|$)", t):
            removals += [x for x in re.split(r",| and ", m.group(1)) if x.strip()]
        t_clean = re.sub(r"\b(?:remove|drop|hide|delete|take out|get rid of|don't (?:show|include)|do not "
                         r"(?:show|include)|no need for|without the) [a-z0-9 ,'/-]+?(?: column| columns|\.|$)", " . ", t)

        # ----- subject
        staff_w = re.search(r"\b(teacher|staff|principal|counselors|administrators|administrator|employees?)\b",
                            t_clean)
        student_w = re.search(r"\b(students?|grade|kindergarten|homeroom|parent|guardian|mother|father|absent|tardy|"
                              r"enrolled|gpa|schedule|504|sped|gifted|riders?|roster)\b", t_clean)
        parent_first = re.match(r"\s*(?:all |the |every )?(parent|guardian|mother|father|families|contacts?|emergency"
                                r" contacts?)\b", t_clean)
        if parent_first:
            self.subject = "parent"
        elif staff_w and (not student_w or staff_w.start() < student_w.start()) and \
                not re.search(r"\b(students?|kids)\b", t_clean[:staff_w.start()]):
            self.subject = "staff"
        else:
            self.subject = "student"
        q = self.q
        q.name = (raw[:60] + ("..." if len(raw) > 60 else "")) or "New query"
        q.description = f"Built by the Query Assistant from: {raw}"
        base = "Employee" if self.subject == "staff" else "Student"
        self.table(base)
        self.say({"student": "Each row is a student", "parent": "Each row is a parent/guardian of a student",
                  "staff": "Each row is a staff member"}[self.subject])

        # ----- aggregation intent
        agg_m = re.search(r"\b(how many|number of|count of|counts?|total number|totals?|average|avg|mean|tally)\b",
                          t_clean)
        self.agg = None
        group_items = []
        if agg_m:
            self.agg = "avg" if agg_m.group(1) in ("average", "avg", "mean") else "count"
            for gm in re.finditer(r"\b(?:per|by|for each|in each|at each|of each|broken down by|grouped by|group by|"
                                  r"for every|in every)\s+([a-z0-9 ]+?)(?=\s*(?:,|\band\b|\.|$|\bat\b|\bin\b|\bwho\b|"
                                  r"\bwith\b|\bfor\b|\bsorted\b))", t_clean):
                group_items.append(gm.group(1))
                for extra in re.finditer(r"\band (?:each |every |by )?([a-z ]+?)(?=\s*(?:,|\.|$))",
                                         t_clean[gm.end():gm.end() + 30]):
                    group_items.append(extra.group(1))
                    break

        # ----- explicit column list
        items = self._list_items(norms[0])
        for n in norms[1:]:          # follow-ups: "also add grade and birth date", "include parent email"
            am = re.match(r"\s*(?:and |please |can you |could you )?(?:also )?(?:add|include|show|plus|put in|"
                          r"give me|i also need|i need|with)\b(?: the| a| an| their)?\s+(.*)", n)
            if am:
                items += [x.strip(" .") for x in re.split(r"\s*(?:,|;|\band\b|\bplus\b)\s*", am.group(1))
                          if x.strip(" .") and x.strip(" .") not in STOP_WORDS]
        if group_items and self.agg:
            items = []
        added_headings = []
        if items:
            self.explicit = True
        for it in items:
            if any(it.strip() == r.strip() for r in removals):
                continue
            r = self.resolve(it)
            h = None
            if r:
                h = self.add_field(r[0], r[1])
            if not h:
                fz = self.fuzzy_column(it)
                if fz and fz[0] != "?":
                    h = self.col(fz[0], fz[1], it.strip().title())
                    self.check(f"Matched '{it.strip()}' to {fz[0]}.{fz[1]} - check it is the column you meant.")
                elif fz:
                    self.check(f"I couldn't find '{it.strip()}'. Closest columns: {', '.join(fz[1])} "
                               "(add one in Step 1).")
                else:
                    self.check(f"I couldn't find '{it.strip()}' - add it in Step 1 (search for it).")
            if h:
                added_headings.append(h)
        if added_headings:
            self.say("Columns you asked for: " + ", ".join(added_headings))

        # ----- make sure each row can be identified (explicit lists without a name/ID)
        if self.explicit and not self.agg:
            self._identity()

        # ----- aggregation build
        if self.agg:
            self._aggregate(t_clean, group_items)

        # ----- domain triggers (add their tables even if not listed)
        self._domains(t_clean)

        # ----- default columns
        if not self.explicit and not self.agg:
            self._defaults()

        # ----- filters
        self._filters(t_clean)
        if self.subject == "staff" and re.search(r"\bprincipal\b", t_clean):
            self.staff_school()
            self.link("SchoolDef", "SchoolPrincipalID", "Employee", "EmployeeID")
            self.conds = [c for c in self.conds if c.column != "PrimarySchoolFlag"]
            self.say("Principals = SchoolDef.SchoolPrincipalID")
        if self.subject == "parent" and re.search(r"\bemergency\b", t_clean):
            self.parent()
            self.conds.append(Condition("StudentContact", "EmergencyFlag", "eq", "1"))
            self.say("Emergency contacts only (StudentContact.EmergencyFlag = 1)")
        if re.search(r"\b(mother|father)\b", t_clean) and self.subject == "parent":
            self.check("Mothers/fathers: filter Relationship (StudentContact.RelationshipCode) in Step 4 using your "
                       "relationship codes (run 'Contact relationship codes' in Find your SAM codes).")
        zm = re.search(r"\bzip (?:code )?(?:is |of |=)?(\d{5})", t_clean)
        if zm:
            owner = "parent" if self.subject == "parent" else ("staff" if self.subject == "staff" else "student")
            self.add_field(owner, "zip")
            zc = next(c for c in self.q.columns if c.heading.endswith("Zip"))
            self.conds.append(Condition(zc.alias, zc.column, "eq", zm.group(1)))
            self.say(f"ZIP code {zm.group(1)}")
        heads_now = [c.heading for c in self.q.columns]
        if self.explicit and self.subject != "staff" and any(h in heads_now for h in ("Teacher", "Period", "Room",
                                                                                        "Section")) \
                and "Course" not in heads_now:
            self.add_field("student", "course")

        # ----- removals
        for r in removals:
            res = self.resolve(r)
            before = len(q.columns)
            if res:
                tmp = Builder(self.cat, self.settings)
                tmp.subject = self.subject
                tmp.table(base)
                h = tmp.add_field(res[0], res[1])
                q.columns = [c for c in q.columns if c.heading != h]
            q.columns = [c for c in q.columns if r.strip().lower() not in c.heading.lower()] \
                if len(q.columns) == before else q.columns
            if len(q.columns) < before:
                self.say(f"Removed '{r.strip()}'")

        # ----- top N / distinct
        top = re.search(r"\b(?:top|first|limit(?: to)?)\s+(\d{1,5})\b", t_clean)
        if top:
            q.top = int(top.group(1))
            self.say(f"Only the first {q.top} rows")
        if re.search(r"\b(unique|distinct|one row per|no duplicates)\b", t_clean):
            q.distinct = True
            self.say("Distinct rows only")

        # ----- sort
        self._sort(t_clean, top is not None)

        # ----- show the filtered-on grade/school when they span several values
        grade_c = next((c for c in self.conds if c.column == "ADAGrade"), None)
        if grade_c and grade_c.op in ("in", "not_in", "ne") and not self.agg and not self.explicit:
            self.add_field("student", "grade")
        if any(c.column == "SchoolName" and c.op == "contains" for c in self.conds) and not self.agg \
                and not self.explicit:
            self.add_field("staff" if self.subject == "staff" else "student", "school")

        # ----- summary columns (counts/averages) always go last
        self.q.columns = [c for c in self.q.columns if not c.agg] + [c for c in self.q.columns if c.agg]

        # ----- finish
        uniq = []
        for c in self.conds:
            if not any((u.alias, u.column, u.op, u.value, u.value2) == (c.alias, c.column, c.op, c.value, c.value2)
                       for u in uniq):
                uniq.append(c)
        self.conds = uniq
        groups = []
        if self.conds:
            groups.append(FilterGroup("ALL", self.conds))
        groups += self.any_groups
        q.filters = groups
        _, added, problems = self.cat.suggest_links(q, add_tables=True)
        if added:
            self.say("Added linking tables: " + ", ".join(added))
        for p in problems:
            self.check(p)
        if not str(self.ds.get("enrolled_status_codes", "")).strip() and self.subject != "staff":
            self.check("Withdrawn students are included because the Enrolled status code isn't set in District "
                       "Settings (run 'Enrollment status codes' in Find your SAM codes).")
        plan = Plan(q, self.understood, self.unsure)
        plan.summary = self._summary()
        return plan

    # ------------------------------------------------------------ pieces
    LIST_INTRO = (r"\b(?:with|including|include|includes|showing|that shows?|show(?:ing)?|containing|listing|"
                  r"that (?:has|have|lists?|includes?)|and their|along with|plus|columns?:?|fields?:?|"
                  r"i need|i want)\b")
    LIST_STOP = (r"\b(?:sorted|sort(?:ed)? by|order(?:ed)? by|grouped|group by|where|who|whose|that are|that is|which|"
                 r"only|excluding|except|but not|for (?:grade|the|all|each|every|students|kids)|in (?:grade|the last|"
                 r"the past|each|every|the)|at (?:the|each|every)|from (?:the|each)|born|enrolled|absent|tardy|per|"
                 r"broken down|by (?:grade|school|homeroom|teacher|last|first|name)|taking|enrolled in)\b")

    def _list_items(self, t):
        m = re.search(self.LIST_INTRO, t)
        # "distinct last names and emails of all teachers" -> the part before "of <people>"
        pre = re.match(r"\s*(?:the |all |distinct |unique |just |only )*([a-z0-9 ,'/-]+?) (?:of|for) (?:all |the |every |each "
                       r"|our )*(?:students|kids|staff|teacher|parent|guardian|employees|\d+th grade|kindergarten|"
                       r"pre-k|seniors|juniors)\b", t)
        if pre and (not m or pre.start(1) < m.start()) and not re.search(self.LIST_INTRO, pre.group(1)):
            cand = [x.strip() for x in re.split(r"\s*(?:,|\band\b|\bplus\b)\s*", pre.group(1)) if x.strip()]
            got = [c for c in cand if (r := self.resolve(c)) and r[0] not in ("parent",) or
                   (self.resolve(c) and self.resolve(c)[1] not in ("full_name",))]
            if got and all(self.resolve(c) for c in cand) and not all(
                    self.resolve(c)[1] == "full_name" and self.resolve(c)[0] != "student" for c in cand):
                return cand
        if not m:
            # "student id, first, last, grade" / "students, their grade, school and parent names"
            first = t.split(" . ")[0]
            if "," in first:
                body = re.sub(r"^\s*(?:all |the |every )?(?:students|kids|staff|teacher)\s*(?:,|:|-)?\s*", "", first)
                cand = [re.sub(r"^(?:their|the|a|an)\s+", "", x.strip(" .")) for x in
                        re.split(r"\s*(?:,|\band\b|\bplus\b)\s*", body) if x.strip(" .")]
                if len(cand) >= 2 and sum(1 for c in cand if self.resolve(c)) >= len(cand) - 1:
                    return cand
            return []
        region = t[m.end():]
        stop = re.search(self.LIST_STOP, region)
        if stop:
            region = region[:stop.start()]
        region = region.split(" . ")[0]
        parts = [p.strip(" .") for p in re.split(r"\s*(?:,|;|\band\b|\bplus\b|\bas well as\b|\balso\b)\s*", region)]
        out = []
        for p in parts:
            p = re.sub(r"^(?:their|the|a|an|his|her|its|each|all|also)\s+", "", p).strip()
            if not p or p in STOP_WORDS:
                continue
            # skip pure filter phrases like "a gpa above 3.5" keep the field part
            if re.search(r"\b(starting|beginning|that start|that begin|starts with|begins with|who|whose|that are|"
                         r"is|are|equals?|named|born)\b", p):
                continue
            p2 = re.sub(r"\b(above|over|below|under|greater than|less than|at least|more than|of|between|or higher|"
                        r"or above|or better|or lower|\d).*$", "", p).strip()
            if re.fullmatch(r"(no|missing|without|blank|empty)\b.*", p2) or not p2:
                continue
            out.append(p2 or p)
        return out

    def _identity(self):
        heads = [c.heading for c in self.q.columns]
        idents = ({"Last Name", "First Name", "Name", "Employee #"} if self.subject == "staff"
                  else {"Student ID", "Last Name", "First Name", "Student"})
        front = []
        if not idents.intersection(heads):
            existing = list(self.q.columns)
            self.q.columns = []
            if self.subject == "staff":
                for f in ("last_name", "first_name"):
                    front.append(self.add_field("staff", f))
            else:
                self.add_field("student", "student_id")
                if self.subject == "parent":
                    front.append(self.name_col("Student", "Student"))
                else:
                    front += [self.add_field("student", "last_name"), self.add_field("student", "first_name")]
            have = {c.heading for c in self.q.columns}
            self.q.columns += [c for c in existing if c.heading not in have]
            self.say("Added name/ID columns so each row can be identified")
        # domain key columns the user would expect, placed right after the name/ID columns
        extra = []
        if re.search(r"\b(absent|tardy|attendance)\b", self.text) and "Date" not in heads:
            extra.append(("student", "attendance_date"))
        if re.search(r"\bschedule\b", self.text) and "Course" not in heads:
            extra.append(("student", "course"))
        n_ident = sum(1 for c in self.q.columns if c.heading in idents or c.heading == "Student ID")
        for o, f in extra:
            h = self.add_field(o, f)
            col = next(c for c in self.q.columns if c.heading == h)
            self.q.columns.remove(col)
            self.q.columns.insert(n_ident, col)
            n_ident += 1

    def _aggregate(self, t, group_items):
        q = self.q
        heads = []
        for gi in group_items:
            r = self.resolve(gi)
            if r:
                h = self.add_field(r[0], r[1])
                if h:
                    heads.append(h)
            else:
                self.check(f"I couldn't group by '{gi}'.")
        what = "students" if self.subject == "student" else ("parents" if self.subject == "parent" else "staff")
        if self.agg == "avg":
            m = re.search(r"\b(?:average|avg|mean) ([a-z ]+?)(?=\s*(?:per|by|for|in|at|of|$|\.))", t)
            r = self.resolve(m.group(1)) if m else None
            if r and r[1] in ("gpa", "qpa", "age"):
                fld = r[1]
                h = self.add_field("student", fld, heading=f"Average {fld.upper() if fld != 'age' else 'Age'}",
                                   agg="avg")
                self.say(f"Average {fld} per group")
            else:
                self.check("I can average GPA, QPA or age. Pick another column's 'Summarize' option in Step 3.")
        absences = re.search(r"\b(absent|tardy|attendance)\b", t)
        noun = "Absences" if absences and "absent" in absences.group(1) else (
            "Tardies" if absences and "tardy" in absences.group(1) else f"Number of {what.title()}")
        if self.agg == "count":
            if absences and self.subject == "student" and not heads:
                for f in ("student_id", "last_name", "first_name", "grade"):
                    heads.append(self.add_field("student", f))
            self.custom(noun, [], agg="count")
            self.say(f"Count: {noun}" + (" per " + ", ".join(heads) if heads else " (one total)"))
        for h in heads:
            self.sort.append(h)
        if self.agg == "count":
            self.sort.insert(0, "-" + noun) if re.search(r"\b(most|highest|top)\b", t) else None
        q.distinct = False

    def _domains(self, t):
        if re.search(r"\b(absent|tardy|attendance|missed school)\b", t):
            self.attendance()
            if not self.explicit and not self.agg:
                self.col("AttendanceDaily", "AttendanceDate", "Date", Fmt("date_us"))
                self.col("AttendanceDaily", "AttendanceCode", "Code")
                self.col("AttendanceCodes", "AttendanceDescription", "Attendance")
                self.sort.insert(0, "-Date")
        if self.subject in ("student", "parent") and re.search(
                r"\b(schedule|class|course|section|period|taking|enrolled in|taught by)\b", t) and not self.explicit \
                and not self.agg:
            self._class_field("schedule", None)
            self._class_field("period", None)
            self._class_field("course_code", None)
            self.sort += ["Period"]
        if self.subject == "staff" and re.search(r"\b(class|course|section|period|schedule|teach(?:es|ing)?)\b", t) \
                and not self.explicit and not self.agg:
            for f in ("period", "course_code", "course", "section", "room"):
                self._class_field(f, None)
            self.sort += ["Period"]
        if self.subject == "parent" and not self.explicit and not self.agg:
            self.parent()
            self.name_col("Parent", "Parent/Guardian")
            self.col("StudentContact", "RelationshipCode", "Relationship")

    def _defaults(self):
        if self.subject == "staff":
            first = [("staff", "employee_number"), ("staff", "last_name"), ("staff", "first_name"), ("staff", "school")]
        elif self.subject == "parent":
            first = [("student", "student_id"), ("student", "full_name"), ("student", "grade"), ("student", "school")]
        else:
            first = [("student", "student_id"), ("student", "last_name"), ("student", "first_name"),
                     ("student", "grade"), ("student", "school")]
        existing = list(self.q.columns)
        self.q.columns = []
        for o, f in first:
            if self.subject == "parent" and f == "full_name":
                self.name_col("Student", "Student")
            else:
                self.add_field(o, f)
        # mentioned-but-not-listed concepts (e.g. "seniors with GPA above 3.5")
        for p, fld in self.field_phrases:
            if fld in ("grade", "school", "student_id", "full_name", "first_name", "last_name", "phone", "email",
                       "address", "attendance_date", "attendance_code", "attendance_desc", "course", "teacher",
                       "period", "section", "room", "schedule", "enrollment_status"):
                continue
            if p in AMBIGUOUS:
                continue
            if re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", self.text):
                o = "student" if self.subject != "staff" else "staff"
                self.add_field(o, fld)
        for p, fld in (("email", "email"), ("phone", "phone"), ("address", "address")):
            if re.search(rf"\b{p}\b", self.text):
                owner = "parent" if re.search(r"\b(parent|guardian|mother|father|contact|famil)", self.text) else \
                    ("staff" if self.subject == "staff" else "student")
                self.add_field(owner, fld)
        if re.search(r"\bhomeroom\b", self.text):
            self.add_field("student", "homeroom")
        if re.search(r"\bcounselor\b", self.text) and self.subject != "staff":
            self.add_field("student", "counselor")
        # keep any domain columns that were added earlier, after the defaults
        have = {c.heading for c in self.q.columns}
        self.q.columns += [c for c in existing if c.heading not in have]

    # ------------------------------------------------------------ filters
    def _filters(self, t):
        self._grade_filter(t)
        self._gender(t)
        self._school_filter(t)
        self._enrollment(t)
        self._attendance_filters(t)
        self._born(t)
        self._numeric(t)
        self._flags(t)
        self._missing(t)
        self._course_teacher(t)
        self._names(t)

    def _grade_filter(self, t):
        spans = []
        for m in re.finditer(rf"\b({GTOK})\s*(?:-|–|to|through|thru)\s*({GTOK})(?:\s*grade)?\b", t):
            ctx = t[max(0, m.start() - 12):m.end() + 8]
            if "grade" in ctx or m.group(1).startswith(("k", "pk")) or re.search(r"(st|nd|rd|th)$", m.group(1)):
                a, b = _g(m.group(1)), _g(m.group(2))
                if a and b:
                    spans.append((m.start(), _grade_range(a, b)))
        for m in re.finditer(rf"\b((?:{GTOK})(?:\s*(?:,|and|or|&)\s*(?:{GTOK}))+)\s*grade\b", t):
            toks = re.findall(GTOK, m.group(1))
            codes = [c for c in (_g(x) for x in toks) if c]
            if codes:
                spans.append((m.start(), codes))
        for m in re.finditer(rf"\bgrade\s+((?:{GTOK})(?:\s*(?:,|and|or)\s*(?:{GTOK}))*)", t):
            nxt = t[m.end():m.end() + 14]
            if re.match(r"\s*(?:-|–|to|through|thru)\s", nxt):
                continue
            codes = [c for c in (_g(x) for x in re.findall(GTOK, m.group(1))) if c]
            if codes:
                spans.append((m.start(), codes))
        covered = [(m.start(), m.end()) for m in re.finditer(
            rf"\b({GTOK})\s*(?:-|–|to|through|thru)\s*({GTOK})(?:\s*grade)?\b|\b((?:{GTOK})(?:\s*(?:,|and|or|&)\s*"
            rf"(?:{GTOK}))+)\s*grade\b|\bgrade\s+((?:{GTOK})(?:\s*(?:,|and|or)\s*(?:{GTOK}))*)", t)]
        inside = lambda pos: any(a <= pos < b for a, b in covered)  # noqa: E731
        for m in re.finditer(rf"\b({GTOK})\s*grade\b", t):
            if not inside(m.start()):
                c = _g(m.group(1))
                if c:
                    spans.append((m.start(), [c]))
        for word, code in (("kindergarten", "KG"), ("pre-k", "PK")):
            for m in re.finditer(rf"(?<![a-z-]){word}(?![a-z])", t):
                if not inside(m.start()):
                    spans.append((m.start(), [code]))
        for lvl, codes in LEVELS.items():
            m = re.search(rf"\b{lvl}(?: school)? (?:students|schoolers|kids)\b|\b{lvl} schoolers\b", t)
            if m and not spans:
                spans.append((m.start(), codes))
                self.check(f"'{lvl.title()} school students' was read as grades {codes[0]}-{codes[-1]}. Adjust in "
                           "Step 4 if your grade spans differ.")
        if not spans:
            return
        spans.sort()
        # all spans in the same sentence combine; a later sentence (follow-up) replaces earlier ones
        last_sentence = t.rfind(" . ", 0, spans[-1][0])
        codes = []
        neg = False
        for s, cs in spans:
            if s > last_sentence:
                codes += [c for c in cs if c not in codes]
                if re.search(r"(except|excluding|not|other than|but not|besides)\s+(the\s+)?$", t[max(0, s - 18):s]):
                    neg = True
        codes.sort(key=ORDER.index)
        from .codes import grade_code
        real = [grade_code(self.settings, c) for c in codes]
        if all(real):
            codes = real
            self.say("Grade codes from your SAM code list")
        else:
            self.check("Grade codes are assumed to be KG, 01-12. Load your grade codes (File > SAM Codes & Schools) "
                       "so the assistant uses the real ones.")
        op = ("not_in" if neg else "in") if len(codes) > 1 else ("ne" if neg else "eq")
        self.conds = [c for c in self.conds if c.column != "ADAGrade"]
        self.conds.append(Condition("Student", "ADAGrade", op, ", ".join(codes)))
        self.say(("Excluding grade " if neg else "Grade ") + ", ".join(codes))

    def _gender(self, t):
        alias, col = ("Employee", "SexCode") if self.subject == "staff" else ("Student", "GenderCode")
        both = re.search(r"\b(boys|males?)\b", t) and re.search(r"\b(girls|females?)\b", t)
        if both:
            if self.agg:
                self.add_field("staff" if self.subject == "staff" else "student", "gender")
                self.sort.insert(0, "Gender")
            return
        if re.search(r"\b(boys|males?|men)\b", t):
            self.conds.append(Condition(alias, col, "eq", "M"))
            self.say("Gender M")
        elif re.search(r"\b(girls|females?|women)\b", t):
            self.conds.append(Condition(alias, col, "eq", "F"))
            self.say("Gender F")

    def _school_filter(self, t):
        # 1) the district's own school list (File > SAM Codes & Schools)
        from .codes import match_schools
        if self.settings.get("schools"):
            for m in re.finditer(r"\b(?:at|from|in|for|attending|of) (?:the )?([a-z0-9.'& -]{2,40}?)(?=\s*(?:,|\.|$|"
                                 r"\bwith\b|\bwho\b|\bsorted\b|\bin\b|\bfor\b|\band\b|\bthat\b|students|kids))", t):
                phrase = m.group(1).strip()
                if re.match(r"(each|every|all|their|his|her|my|our|any|a|which|what|that|this|grade|the last|the "
                            r"past|\d)", phrase):
                    continue
                hits = match_schools(self.settings, phrase)
                if hits and len(hits) <= max(3, len(self.settings["schools"]) // 2):
                    if self.subject == "staff":
                        self.staff_school()
                        alias = "empSchool"
                    else:
                        self.student_school()
                        alias = "stuSchool"
                    ids = [str(h["id"]) for h in hits]
                    self.conds.append(Condition(alias, "SchoolID", "in" if len(ids) > 1 else "eq", ", ".join(ids)))
                    self.say("School: " + ", ".join(f"{h['name']} (SchoolID {h['id']})" for h in hits))
                    if not self.agg:
                        self.add_field("staff" if self.subject == "staff" else "student", "school")
                    return
        # 2) otherwise a "name contains" guess
        for m in re.finditer(r"\b(?:at|from|in|for|attending) (?:the )?((?:[a-z.'-]+ ){0,3}?(?:elementary|middle|"
                             r"high|junior high|primary|intermediate|academy|center|school))\b", t):
            phrase = m.group(1).strip()
            if re.match(r"(each|every|all|their|his|her|my|our|any|a|which|what|that|this)\b", phrase):
                continue
            if re.match(r"\s*(school\s+)?(students|schoolers|kids|grades?)\b", t[m.end():m.end() + 20]):
                continue
            words = [w for w in phrase.split() if w not in ("school", "the")]
            if not words:
                continue
            val = " ".join(words).title()
            if self.subject == "staff":
                self.staff_school()
            else:
                self.student_school()
            self.conds.append(Condition("SchoolDef", "SchoolName", "contains", val))
            self.say(f"School name contains '{val}'")
            self.check(f"Check the school filter ('{val}') matches the school's name in SAM.")
            break
        if re.search(r"\b(each|every|all|by|per) school", t) and not self.agg:
            self.add_field("staff" if self.subject == "staff" else "student", "school")

    def _enrollment(self, t):
        if self.subject == "staff":
            self.conds.append(Condition("Employee", "TerminationDate", "blank"))
            self.say("Current staff (no termination date)")
            if re.search(r"\b(teacher|faculty)\b", t):
                self.conds.append(Condition("Employee", "FacultyFlag", "eq", "1"))
                self.say("Teachers only (Faculty flag)")
            self.staff_school()
            return
        codes = str(self.ds.get("enrolled_status_codes", "")).strip()
        if re.search(r"\b(withdrawn|not enrolled|unenrolled|inactive|dropped|left)\b", t):
            if codes:
                self.conds.append(Condition("Student", "EnrollmentStatus", "not_in", codes))
                self.say(f"Only students NOT enrolled (status not in {codes})")
            else:
                self.check("'Withdrawn/not enrolled' needs the Enrolled status code in District Settings.")
            self.add_field("student", "enrollment_status")
        elif codes:
            self.conds.append(Condition("Student", "EnrollmentStatus", "in", codes))
            self.say(f"Enrolled students only (status {codes})")
        self.student_school()

    def _attendance_filters(self, t):
        if not re.search(r"\b(absent|tardy|attendance|missed school)\b", t):
            return
        if re.search(r"\babsent|missed school", t):
            self.conds.append(Condition("AttendanceCodes", "AttendanceDescription", "contains", "Absent"))
            self.check("Absent = attendance description contains 'Absent'. Use your absence codes in Step 4 if "
                       "your descriptions differ.")
        if re.search(r"\btardy\b", t):
            self.conds.append(Condition("AttendanceCodes", "AttendanceDescription", "contains", "Tard"))
            self.check("Tardy = attendance description contains 'Tard'.")
        self._dates(t, "AttendanceDaily", "AttendanceDate")

    def _dates(self, t, alias, col):
        m = re.search(r"(?:last|past|previous) (\d+) (day|week|month)s?", t)
        if m:
            n = int(m.group(1)) * {"day": 1, "week": 7, "month": 30}[m.group(2)]
            self.conds.append(Condition(alias, col, "last_days", str(n)))
            self.say(f"Dates in the last {n} days")
            return
        for words, n in ((r"today", 0), (r"yesterday", 1), (r"(this|last|past) week", 7),
                         (r"(this|last|past) month", 30), (r"this (school )?year|so far this year", -1)):
            if re.search(rf"\b{words}\b", t):
                if n == 0:
                    self.conds.append(Condition(alias, col, "today"))
                    self.say("Today only")
                elif n == -1:
                    start = f"{int(self.ds['school_year']) - 1}-07-01"
                    self.conds.append(Condition(alias, col, "ge", start))
                    self.say(f"This school year (since {start})")
                else:
                    self.conds.append(Condition(alias, col, "last_days", str(n)))
                    self.say(f"Last {n} day(s)")
                return
        m = re.search(r"(?:between|from) (\d{1,2}/\d{1,2}/\d{2,4}) (?:and|to|through|-) (\d{1,2}/\d{1,2}/\d{2,4})", t)
        if m:
            self.conds.append(Condition(alias, col, "between", m.group(1), m.group(2)))
            self.say(f"Dates between {m.group(1)} and {m.group(2)}")
            return
        m = re.search(r"\b(?:since|after|on or after) (\d{1,2}/\d{1,2}/\d{2,4})", t)
        if m:
            self.conds.append(Condition(alias, col, "ge", m.group(1)))
            self.say(f"Dates on/after {m.group(1)}")

    def _born(self, t):
        alias = "Employee" if self.subject == "staff" else "Student"
        m = re.search(r"\bborn (in|after|before|between) (\d{4})(?: and (\d{4}))?", t)
        if not m:
            return
        kind, y1, y2 = m.group(1), m.group(2), m.group(3)
        if kind == "in":
            self.conds.append(Condition(alias, "DOB", "between", f"{y1}-01-01", f"{y1}-12-31"))
        elif kind == "after":
            self.conds.append(Condition(alias, "DOB", "gt", f"{y1}-12-31"))
        elif kind == "before":
            self.conds.append(Condition(alias, "DOB", "lt", f"{y1}-01-01"))
        elif y2:
            self.conds.append(Condition(alias, "DOB", "between", f"{y1}-01-01", f"{y2}-12-31"))
        self.add_field("student" if alias == "Student" else "staff", "birth_date")
        self.say(f"Born {kind} {y1}" + (f" and {y2}" if y2 else ""))

    def _numeric(self, t):
        ops = {"above": "gt", "over": "gt", "greater than": "gt", "higher than": "gt", "more than": "gt", ">": "gt",
               "at least": "ge", ">=": "ge", "or higher": "ge", "or above": "ge", "below": "lt", "under": "lt",
               "less than": "lt", "lower than": "lt", "<": "lt", "<=": "le", "at most": "le", "of": "eq",
               "equal to": "eq", "=": "eq"}
        for fld, alias, col in (("gpa", "Student", "CumulativeGPA"), ("qpa", "Student", "CumulativeQPA")):
            m = re.search(rf"\b{fld}\s*(?:is\s*|of\s*)?(above|over|greater than|higher than|more than|at least|below|"
                          rf"under|less than|lower than|at most|equal to|>=|<=|>|<|=|of)?\s*(\d(?:\.\d+)?)"
                          rf"(?:\s*(or higher|or above|and above|and up|or better|or lower|or below))?", t)
            m2 = re.search(rf"\b{fld}\s*(?:between|from)\s*(\d(?:\.\d+)?)\s*(?:and|to|-)\s*(\d(?:\.\d+)?)", t)
            if m2:
                self.conds.append(Condition(alias, col, "between", m2.group(1), m2.group(2)))
                self.add_field("student", fld)
                self.say(f"{fld.upper()} between {m2.group(1)} and {m2.group(2)}")
            elif m and (m.group(1) or m.group(3)):
                op = ops.get(m.group(1) or "", "eq")
                if m.group(3):
                    op = "ge" if any(w in m.group(3) for w in ("higher", "above", "up", "better")) else "le"
                self.conds.append(Condition(alias, col, op, m.group(2)))
                self.add_field("student", fld)
                self.say(f"{fld.upper()} {op} {m.group(2)}")

    def _flags(self, t):
        if self.subject == "staff":
            return
        flags = [(r"\b504\b", "Flag504", "eq", "1", "flag_504", "Students with a 504 flag"),
                 (r"\bsped\b", "SPEDStatus", "not_blank", "", "sped", None),
                 (r"\bgifted\b", "GiftedStatus", "not_blank", "", "gifted", None),
                 (r"\btitle (one|i|1)\b", "TitleOneFlag", "eq", "1", "title_one", "Title I students"),
                 (r"\bfoster\b", "FosterChildFlag", "eq", "1", "foster", "Foster students"),
                 (r"\b(bus )?riders?\b|\bride the bus\b", "TransportationCode", "not_blank", "", "transportation", None)]
        for rx, col, op, val, fld, msg in flags:
            if re.search(rx, t):
                neg = re.search(r"\b(not|without|no|non)[- ]" + rx.strip(r"\b")[:6], t)
                if neg and op == "eq":
                    op = "ne"
                self.conds.append(Condition("Student", col, op, val))
                self.add_field("student", fld)
                if msg:
                    self.say(msg)
                else:
                    self.check(f"'{fld.replace('_', ' ').title()}' = Student.{col} is not blank. Narrow it to your "
                               "codes in Step 4 if needed.")

    def _missing(self, t):
        for m in re.finditer(r"\b(?:without|missing|no|with no|with a blank|with blank|that don't have|that do not "
                             r"have|who don't have|who do not have|lacking) (?:an? |any )?([a-z ]+?)(?=\s*(?:,|\.|$|"
                             r"\band\b|\bsorted\b|\bin\b|\bat\b|\bfor\b))", t):
            r = self.resolve(m.group(1))
            if not r:
                continue
            h = self.add_field(r[0], r[1])
            col = next((c for c in self.q.columns if c.heading == h), None)
            if not col:
                continue
            if col.kind == "field":
                self.conds.append(Condition(col.alias, col.column, "blank"))
            else:
                p = next((p for p in col.parts if p.kind == "field"), None)
                if p:
                    self.conds.append(Condition(p.alias, p.column, "blank"))
            self.say(f"Only rows missing {h}")

    def _course_teacher(self, t):
        if self.subject == "staff":
            return
        m = re.search(r"\b(?:taking|enrolled in|in|scheduled (?:in|for)|signed up for) ([a-z][a-z0-9 .&'-]{1,30}?)"
                      r"(?: class| course| section)", t) or \
            re.search(r"\b(?:taking|enrolled in|scheduled for|signed up for) ([a-z][a-z0-9 .&'-]{1,30}?)"
                      r"(?=\s*(?:,|\.|$|\bwith\b|\bwho\b|\bin\b|\bat\b|\bsorted\b|\bfor\b|\bwithout\b))", t)
        if not m:
            m = re.search(r"\b(?:students|kids|those|everyone|anyone|seniors|juniors) (?:who are |that are )?in "
                          r"([a-z][a-z0-9 .&'-]{1,30}?)(?=\s*(?:,|\.|$|\bwith\b|\bwho\b|\bwithout\b|\bsorted\b|\bat\b|"
                          r"\bfor\b|\bthat\b))", t)
        if m and not re.search(r"grade|school|homeroom|the last|the past|this|their|each|every|all|period|room|"
                               r"\d(st|nd|rd|th)|kindergarten|mr|mrs|ms|elementary|middle|high|district|class of",
                               m.group(1)):
            name = m.group(1).strip().title().replace(" Ii", " II").replace(" Iii", " III").replace(" Iv", " IV")
            self.schedule()
            self.add_field("student", "course")
            self.conds.append(Condition("Course", "LongName", "contains", name))
            self.say(f"Course name contains '{name}'")
            self.check(f"Course filter: name contains '{name}' - adjust in Step 4 if it should be a course code.")
        m = re.search(r"\b(?:taught by|in) (?:mr\.?|mrs\.?|ms\.?|miss|dr\.?|coach) ([a-z'-]+)(?:'s)?", t)
        if m:
            last = m.group(1).replace("'s", "").title()
            homeroom = re.search(r"homeroom", t[m.end():m.end() + 15])
            if homeroom:
                self.homeroom()
                self.add_field("student", "homeroom")
                self.conds.append(Condition("HomeroomTeacher", "LastName", "eq", last))
                self.say(f"Homeroom teacher's last name is {last}")
            else:
                alias = self.section_teacher()
                self.add_field("student", "teacher")
                self.conds.append(Condition(alias, "LastName", "eq", last))
                self.say(f"Teacher's last name is {last}")

    def _names(self, t):
        alias = "Employee" if self.subject == "staff" else "Student"
        m = re.search(r"\blast names? (?:starting|beginning|that (?:start|begin)s?|starts|begins) with ([a-z])"
                      r"(?:\s*(?:-|through|to|thru)\s*([a-z]))?\b", t)
        if m:
            if m.group(2):
                self.conds.append(Condition(alias, "LastName", "between", m.group(1).upper(), m.group(2).upper() + "zzz"))
                self.say(f"Last names {m.group(1).upper()}-{m.group(2).upper()}")
            else:
                self.conds.append(Condition(alias, "LastName", "starts", m.group(1).upper()))
                self.say(f"Last names starting with {m.group(1).upper()}")
        m = re.search(r"\b(?:last name is|named|whose last name is|with the last name) ([a-z'-]{2,})\b", t)
        if m and m.group(1) not in STOP_WORDS:
            self.conds.append(Condition(alias, "LastName", "eq", m.group(1).title()))
            self.say(f"Last name is {m.group(1).title()}")
        m = re.search(r"\bfirst name (?:is|=) ([a-z'-]{2,})\b", t)
        if m:
            self.conds.append(Condition(alias, "FirstName", "eq", m.group(1).title()))
            self.say(f"First name is {m.group(1).title()}")

    # ------------------------------------------------------------ sort
    def _sort(self, t, has_top):
        q = self.q
        headings = [c.heading for c in q.columns]
        wanted = []
        m = re.search(r"\b(?:sort(?:ed)?|order(?:ed)?|group(?:ed)?|arrange(?:d)?|list(?:ed)?) (?:them )?by ([a-z0-9 ,]+?)"
                      r"(?:$|\.|;)", t)
        phrase = m.group(1) if m else None
        if not phrase:
            m2 = re.search(r"\b(?:top \d+|highest|lowest|bottom \d+) [a-z0-9 ]*?by ([a-z ]+?)(?:$|\.|,| with)", t)
            phrase = m2.group(1) if m2 else None
        if phrase:
            for chunk in re.split(r",| and | then ", phrase):
                chunk = chunk.strip()
                desc = bool(re.search(r"\b(desc|descending|highest|newest|most recent|largest|z-a|reverse)\b", chunk)) \
                    or (has_top and re.search(r"\b(gpa|qpa|count|absences|number)\b", chunk) is not None)
                chunk = re.sub(r"\b(desc|descending|asc|ascending|highest|lowest|newest|oldest|first|a-z|z-a)\b",
                               "", chunk).strip()
                if not chunk:
                    continue
                h = next((x for x in headings if x.lower() == chunk or x.lower() == chunk + " teacher"), None) or \
                    next((x for x in headings if chunk in x.lower()), None)
                if not h:
                    r = self.resolve(chunk)
                    if r:
                        if r[1] == "full_name" and r[0] in ("student", "staff"):
                            r = (r[0], "last_name")
                        h = self.add_field(r[0], r[1])
                if h:
                    wanted.append(("-" if desc else "") + h)
            if wanted:
                self.say("Sorted by " + ", ".join(w.lstrip("-") + (" (high to low)" if w.startswith("-") else "")
                                                   for w in wanted))
        elif re.search(r"\balphabetical(ly)?\b", t):
            wanted = ["Last Name", "First Name"]
        heads = [c.heading for c in q.columns]
        if not wanted:
            # sensible default: keep the first listed grouping column, then school/grade/name
            first = heads[0] if heads else None
            default = []
            if self.explicit and first in ("Homeroom Teacher", "Teacher", "School", "Grade", "Counselor"):
                default.append(first)
            default += self.sort + ["School", "Grade", "Homeroom Teacher", "Last Name", "First Name", "Student",
                                    "Parent/Guardian", "Period"]
            wanted = default
        seen = []
        for w in wanted:
            name = w.lstrip("-")
            if name in heads and name not in [s.lstrip("-") for s in seen]:
                seen.append(w)
        q.sort = [SortItem(w.lstrip("-"), w.startswith("-")) for w in seen]

    # ------------------------------------------------------------ summary sentence
    def _summary(self):
        q = self.q
        who = {"student": "students", "parent": "parents/guardians of students", "staff": "staff members"}[self.subject]
        bits = []
        for g in q.filters:
            for c in g.conditions:
                if c.column == "ADAGrade":
                    codes = [x.strip() for x in c.value.split(",")]
                    nice = lambda x: ("K" if x.upper() in ("KG", "K") else "Pre-K" if x.upper() == "PK"  # noqa: E731
                                      else str(int(x)) if x.isdigit() else x)
                    idx = [ORDER.index(x) for x in codes if x in ORDER]
                    if len(codes) > 2 and idx == list(range(idx[0], idx[0] + len(idx))):
                        txt = f"grades {nice(codes[0])}-{nice(codes[-1])}"
                    else:
                        txt = ("grades " if len(codes) > 1 else "grade ") + ", ".join(nice(x) for x in codes)
                    bits.append(("not in " if c.op in ("ne", "not_in") else "in ") + txt)
                elif c.column == "SchoolID" and self.settings.get("schools"):
                    ids = [x.strip() for x in c.value.split(",")]
                    names = [x["name"] for x in self.settings["schools"] if str(x["id"]) in ids]
                    bits.append("at " + " / ".join(names))
                elif c.column == "SchoolName":
                    bits.append(f"at schools named like '{c.value}'")
                elif c.column in ("GenderCode", "SexCode"):
                    bits.append("boys" if c.value == "M" else "girls")
        cols = ", ".join(c.heading for c in q.columns)
        s = f"A list of {who}" + (" " + ", ".join(bits) if bits else "") + f", showing {cols}"
        if q.sort:
            s += ", sorted by " + ", ".join(x.heading for x in q.sort)
        if q.top:
            s += f" (first {q.top} rows)"
        return s + "."


def build_from_text(text: str, catalog, settings: dict | None = None) -> Plan:
    return Builder(catalog, settings).build([text])


def build_conversation(messages: list[str], catalog, settings: dict | None = None) -> Plan:
    """First message is the request; later messages refine it ('also add birth date', 'only 10th grade',
    'remove school')."""
    return Builder(catalog, settings).build(messages)
