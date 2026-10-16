"""Build an export package from ANY vendor's template.

The user picks what one row of the vendor file is (a 'base': students, staff, guardians, class enrollments,
sections or schools), opens or pastes the vendor's header row, and maps every vendor column to a SAM field
(suggested automatically). The result is saved as a normal export package (same format as data/exports.json),
so it gets the sample preview, export checker, Save package, CAC Agent walkthrough, uploads, district versions,
school limits and privacy check for free.

Custom packages live in %APPDATA%\\SAM Ad Hoc Query Builder\\custom_packages (shared by every district) and can be
exported / imported as .samqb-package files to share with other districts.
"""
from __future__ import annotations

import csv
import difflib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .query_model import Condition, FilterGroup, Fmt, Link, OutColumn, Part, QueryDef, TableRef

OT_STU, OT_CON, OT_EMP = "{{OWNER_TYPE_STUDENT}}", "{{OWNER_TYPE_CONTACT}}", "{{OWNER_TYPE_EMPLOYEE}}"
LIVE_HR = "stuHRTeacher.ScheduleID IN (SELECT ScheduleID FROM Schedule WHERE LiveFlag = 1)"
GRADE_NUM = "PK=-1; KG=0; K=0; 01=1; 02=2; 03=3; 04=4; 05=5; 06=6; 07=7; 08=8; 09=9"
YN = "CASE WHEN {x} IN (1, '1', 'Y', 'T') THEN 'Y' ELSE 'N' END"
FLAG_YN = "CASE WHEN LTRIM(RTRIM(ISNULL({x}, ''))) IN ('', '0', 'N') THEN 'N' ELSE 'Y' END"


# ----------------------------------------------------------------------------- bases (what one row is)
def _q(tables, links, conds):
    q = QueryDef(distinct=True)
    for t in tables:
        q.tables.append(TableRef(*t) if isinstance(t, tuple) else TableRef(t, t))
    q.links = [Link(*l) for l in links]
    q.filters = [FilterGroup("ALL", list(conds))] if conds else []
    return q


STU_CONDS = [Condition("stuSchool", "PrimarySchoolFlag", "eq", "1"),
             Condition("Student", "EnrollmentStatus", "in", "{{ENROLLED_STATUS_CODES}}")]
STAFF_CONDS = [Condition("empSchool", "PrimarySchoolFlag", "eq", "1"), Condition("Employee", "TerminationDate", "blank")]
SEC = [("ScheduleFramework", "ScheduleCourseTermID", "ScheduleCourseTerm", "ScheduleCourseTermID", "INNER"),
       ("ScheduleCourseTerm", "ScheduleCourseID", "ScheduleCourse", "ScheduleCourseID", "INNER"),
       ("ScheduleCourse", "CourseID", "Course", "CourseID", "INNER"),
       ("ScheduleCourse", "ScheduleID", "Schedule", "ScheduleID", "INNER")]
SEC_T = ["ScheduleFramework", "ScheduleCourseTerm", "ScheduleCourse", "Course", "Schedule"]
LIVE = Condition("Schedule", "LiveFlag", "eq", "1")

BASES = {
    "students": ("Students - one row per enrolled student", lambda: _q(
        ["Student", "stuSchool", "SchoolDef"],
        [("Student", "StudentID", "stuSchool", "StudentID", "INNER"),
         ("stuSchool", "SchoolID", "SchoolDef", "SchoolID", "INNER")], STU_CONDS)),
    "guardians": ("Guardians - one row per student + guardian", lambda: _q(
        ["Student", "stuSchool", "SchoolDef", ("StudentContact", "StudentContact"), ("Contact", "ContactInfo")],
        [("Student", "StudentID", "stuSchool", "StudentID", "INNER"),
         ("stuSchool", "SchoolID", "SchoolDef", "SchoolID", "INNER"),
         ("Student", "StudentID", "StudentContact", "StudentID", "INNER",
          [Condition("StudentContact", "NoContact", "ne", "1")]),
         ("StudentContact", "ContactID", "Contact", "ContactID", "INNER")], STU_CONDS)),
    "staff": ("Staff - one row per active staff member", lambda: _q(
        ["Employee", "empSchool", "SchoolDef"],
        [("Employee", "EmployeeID", "empSchool", "EmployeeID", "INNER"),
         ("empSchool", "SchoolID", "SchoolDef", "SchoolID", "INNER")], STAFF_CONDS)),
    "enrollments": ("Class enrollments - one row per student per class", lambda: _q(
        ["ScheduleRoster", "Student"] + SEC_T + [("Teacher", "Employee"), "SchoolDef"],
        [("ScheduleRoster", "StudentID", "Student", "StudentID", "INNER"),
         ("ScheduleRoster", "ScheduleFrameworkID", "ScheduleFramework", "ScheduleFrameworkID", "INNER")] + SEC +
        [("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "LEFT"),
         ("Schedule", "SchoolID", "SchoolDef", "SchoolID", "INNER")],
        [LIVE, Condition("ScheduleRoster", "WithdrawnDate", "blank"),
         Condition("Student", "EnrollmentStatus", "in", "{{ENROLLED_STATUS_CODES}}")])),
    "sections": ("Classes / sections - one row per class on the live schedule", lambda: _q(
        SEC_T + [("Teacher", "Employee"), "SchoolDef"],
        SEC + [("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "LEFT"),
               ("Schedule", "SchoolID", "SchoolDef", "SchoolID", "INNER")], [LIVE])),
    "schools": ("Schools - one row per active school", lambda: _q(
        ["SchoolDef", ("Principal", "Employee")],
        [("SchoolDef", "SchoolPrincipalID", "Principal", "EmployeeID", "LEFT")],
        [Condition("SchoolDef", "ActiveFlag", "eq", "1")])),
}

# extra joins a field can need (added only when a mapped field uses them)
CHAINS = {
    "hr": ([("stuHRTeacher", "stuHRTeacher"), ("HomeroomTeacher", "Employee")],
           [("Student", "StudentID", "stuHRTeacher", "StudentID", "LEFT",
             [Condition("stuHRTeacher", "ScheduleID", "raw", LIVE_HR)]),
            ("stuHRTeacher", "HRTeacherID", "HomeroomTeacher", "EmployeeID", "LEFT")]),
    "counselor": ([("Counselor", "Employee")], [("stuHRTeacher", "CounselorID", "Counselor", "EmployeeID", "LEFT")]),
    "pcontact": ([("PrimaryContactLink", "StudentContact"), ("PrimaryContact", "ContactInfo")],
                 [("Student", "StudentID", "PrimaryContactLink", "StudentID", "LEFT",
                   [Condition("PrimaryContactLink", "PrimaryContact", "eq", "1")]),
                  ("PrimaryContactLink", "ContactID", "PrimaryContact", "ContactID", "LEFT")]),
    "pphone": ([("PrimaryPhoneLink", "PhoneRelationship"), ("PrimaryPhone", "PhoneNumber")],
               [("PrimaryContact", "ContactID", "PrimaryPhoneLink", "OwnerID", "LEFT",
                 [Condition("PrimaryPhoneLink", "OwnerType", "eq", OT_CON),
                  Condition("PrimaryPhoneLink", "PrimaryPhone", "eq", "1")]),
                ("PrimaryPhoneLink", "PhoneNumberID", "PrimaryPhone", "PhoneNumberID", "LEFT")]),
    "pemail": ([("PrimaryEmail", "EmailAddress")],
               [("PrimaryContact", "ContactID", "PrimaryEmail", "OwnerID", "LEFT",
                 [Condition("PrimaryEmail", "OwnerType", "eq", OT_CON),
                  Condition("PrimaryEmail", "PrimaryAddress", "eq", "1")])]),
    "cphone": ([("ContactPhoneLink", "PhoneRelationship"), ("ContactPhone", "PhoneNumber")],
               [("Contact", "ContactID", "ContactPhoneLink", "OwnerID", "LEFT",
                 [Condition("ContactPhoneLink", "OwnerType", "eq", OT_CON),
                  Condition("ContactPhoneLink", "PrimaryPhone", "eq", "1")]),
                ("ContactPhoneLink", "PhoneNumberID", "ContactPhone", "PhoneNumberID", "LEFT")]),
    "cemail": ([("ContactEmail", "EmailAddress")],
               [("Contact", "ContactID", "ContactEmail", "OwnerID", "LEFT",
                 [Condition("ContactEmail", "OwnerType", "eq", OT_CON),
                  Condition("ContactEmail", "PrimaryAddress", "eq", "1")])]),
    "addr": ([("HomeAddressLink", "AddressRelationship"), ("HomeAddress", "Address")],
             [("Student", "StudentID", "HomeAddressLink", "OwnerID", "LEFT",
               [Condition("HomeAddressLink", "OwnerType", "eq", OT_STU),
                Condition("HomeAddressLink", "PrimaryAddress", "eq", "1")]),
              ("HomeAddressLink", "AddressID", "HomeAddress", "AddressID", "LEFT")]),
    "sphone": ([("StaffPhoneLink", "PhoneRelationship"), ("StaffPhone", "PhoneNumber")],
               [("Employee", "EmployeeID", "StaffPhoneLink", "OwnerID", "LEFT",
                 [Condition("StaffPhoneLink", "OwnerType", "eq", OT_EMP),
                  Condition("StaffPhoneLink", "PrimaryPhone", "eq", "1")]),
                ("StaffPhoneLink", "PhoneNumberID", "StaffPhone", "PhoneNumberID", "LEFT")]),
}
CHAIN_NEEDS = {"counselor": ["hr"], "pphone": ["pcontact"], "pemail": ["pcontact"]}


# ----------------------------------------------------------------------------- field library
@dataclass
class FieldDef:
    key: str
    label: str
    bases: tuple
    make: object                 # () -> OutColumn (heading set later)
    synonyms: tuple = ()
    needs: tuple = ()
    rule: str = ""               # export-checker format for this column
    group: str = ""


def F(alias, col, *fmts):
    return lambda: OutColumn("field", alias, col, "", list(fmts))


def C(*parts):
    return lambda: OutColumn("custom", parts=[p() if callable(p) else p for p in parts])


def P(alias, col, *fmts):
    return Part("field", alias, col, formats=list(fmts))


def X(text):
    return Part("text", value=text)


def RAW(sql):
    return lambda: OutColumn("raw", column=sql)


def EM(alias, role):
    return lambda: OutColumn("custom", parts=[Part("email", alias, value=role)])


def UN(alias, role):
    return lambda: OutColumn("custom", parts=[Part("username", alias, value=role)])


def phone(alias):
    return lambda: OutColumn("custom", parts=[
        P(alias, "AreaCode", Fmt("trim")),
        P(alias, "PhoneNumber", Fmt("replace", "-", ""), Fmt("remove_spaces"), Fmt("replace", "(", ""),
          Fmt("replace", ")", ""))])


T = Fmt("trim")
STU = ("students", "guardians", "enrollments")
ALLB = tuple(BASES)

FIELDS: list[FieldDef] = [
    # --- student
    FieldDef("stu_id", "Student ID (local)", STU, F("Student", "StudentCode", T),
             ("student id", "studentid", "student number", "local id", "sis id", "student_id", "id number",
              "local student id", "student code", "studentnumber", "person id", "user id"), group="Student"),
    FieldDef("stu_state", "State student ID (MSIS)", STU, F("Student", "StateCode"),
             ("state id", "state student id", "msis", "stateid", "ssid", "state number"), group="Student"),
    FieldDef("stu_first", "Student first name", STU, F("Student", "FirstName", T),
             ("first name", "firstname", "first", "given name", "student first name", "fname"), group="Student"),
    FieldDef("stu_middle", "Student middle name", STU, F("Student", "MiddleName", T),
             ("middle name", "middle", "mname"), group="Student"),
    FieldDef("stu_mi", "Student middle initial", STU, F("Student", "MiddleName", T, Fmt("left", "1")),
             ("middle initial", "mi"), group="Student"),
    FieldDef("stu_last", "Student last name", STU, F("Student", "LastName", T),
             ("last name", "lastname", "last", "surname", "family name", "student last name", "lname"), group="Student"),
    FieldDef("stu_pref", "Student preferred name", STU, F("Student", "PreferredName", T),
             ("preferred name", "nickname", "nick name"), group="Student"),
    FieldDef("stu_full", "Student full name (First Last)", STU,
             C(P("Student", "FirstName", T), X(" "), P("Student", "LastName", T)),
             ("full name", "name", "student name", "display name"), group="Student"),
    FieldDef("stu_lastfirst", "Student name (Last, First)", STU,
             C(P("Student", "LastName", T), X(", "), P("Student", "FirstName", T)),
             ("last first", "sort name"), group="Student"),
    FieldDef("stu_dob", "Birth date (MM/DD/YYYY)", STU, F("Student", "DOB", Fmt("date_us")),
             ("dob", "birth date", "birthdate", "date of birth", "birthday"), rule="date_us", group="Student"),
    FieldDef("stu_dob_iso", "Birth date (YYYY-MM-DD)", STU, F("Student", "DOB", Fmt("date_iso")),
             ("dob iso",), rule="date_iso", group="Student"),
    FieldDef("stu_gender", "Gender", STU, F("Student", "GenderCode"), ("gender", "sex"), group="Student"),
    FieldDef("stu_grade", "Grade (SAM code: KG, 01-12)", STU, F("Student", "ADAGrade"),
             ("grade", "grade level", "gradelevel", "current grade", "grade_level"), group="Student"),
    FieldDef("stu_grade_num", "Grade as number (K = 0)", STU, F("Student", "ADAGrade", Fmt("map", GRADE_NUM)),
             ("grade number", "numeric grade"), group="Student"),
    FieldDef("stu_grad", "Graduation year", STU, F("Student", "OriginalGradDate", Fmt("year")),
             ("graduation year", "grad year", "class year", "class of", "cohort", "year of graduation"),
             rule="year", group="Student"),
    FieldDef("stu_email", "Student email", STU, EM("Student", "student"),
             ("email", "email address", "student email", "e mail", "mail"), rule="email", group="Student"),
    FieldDef("stu_user", "Student username", STU, UN("Student", "student"),
             ("username", "user name", "login", "login id", "sis username", "network id"), group="Student"),
    FieldDef("stu_school_id", "School ID (SAM SchoolID)", ("students", "guardians"), F("SchoolDef", "SchoolID"),
             ("school id", "schoolid", "building id", "location id", "org id", "site id"), group="School"),
    FieldDef("stu_status", "Enrollment status code", STU, F("Student", "EnrollmentStatus"),
             ("enrollment status", "status"), group="Student"),
    FieldDef("stu_race", "Race code", STU, F("Student", "RaceCode"), ("race", "ethnicity"), group="Student"),
    FieldDef("stu_lang", "Home language", STU, F("Student", "LangBackground"),
             ("home language", "language", "native language", "primary language"), group="Student"),
    FieldDef("stu_sped", "Special education (Y/N)", STU, RAW(FLAG_YN.format(x="Student.SPEDStatus")),
             ("iep", "sped", "special education", "special ed", "swd"), rule="yn", group="Programs"),
    FieldDef("stu_504", "Section 504 (Y/N)", STU, RAW(YN.format(x="Student.Flag504")), ("504", "504 plan", "section 504"),
             rule="yn", group="Programs"),
    FieldDef("stu_gifted", "Gifted (Y/N)", STU, RAW(FLAG_YN.format(x="Student.GiftedStatus")),
             ("gifted", "gifted and talented", "gt"), rule="yn", group="Programs"),
    FieldDef("stu_meal", "Meal status code", STU, F("Student", "FoodServiceCode"),
             ("meal status", "frl", "lunch status", "free reduced", "economic status"), group="Programs"),
    FieldDef("stu_pin", "Lunch PIN / number", STU, F("Student", "LunchNumber", T),
             ("pin", "lunch number", "lunch pin", "barcode", "meal pin"), group="Student"),
    FieldDef("hr_teacher", "Homeroom teacher (last name)", ("students", "guardians"),
             F("HomeroomTeacher", "LastName", T), ("homeroom", "homeroom teacher", "hr teacher", "advisory"),
             needs=("hr",), group="Homeroom"),
    FieldDef("hr_teacher_email", "Homeroom teacher email", ("students", "guardians"), EM("HomeroomTeacher", "staff"),
             ("homeroom teacher email", "teacher email"), needs=("hr",), rule="email", group="Homeroom"),
    FieldDef("counselor_email", "Counselor email", ("students",), EM("Counselor", "staff"),
             ("counselor email", "counselor"), needs=("counselor",), rule="email", group="Homeroom"),
    FieldDef("addr1", "Home address line 1", ("students",), F("HomeAddress", "AddrLine1", T),
             ("address", "address 1", "street", "street address", "address line 1", "addr1"), needs=("addr",),
             group="Address"),
    FieldDef("addr2", "Home address line 2", ("students",), F("HomeAddress", "AddrLine2", T),
             ("address 2", "address line 2", "addr2", "apt"), needs=("addr",), group="Address"),
    FieldDef("city", "City", ("students",), F("HomeAddress", "City", T), ("city", "town"), needs=("addr",),
             group="Address"),
    FieldDef("state", "State", ("students",), F("HomeAddress", "State"), ("state", "st"), needs=("addr",),
             group="Address"),
    FieldDef("zip", "ZIP code", ("students",), F("HomeAddress", "ZipCode"), ("zip", "zip code", "postal code", "zipcode"),
             needs=("addr",), group="Address"),
    FieldDef("pg_name", "Primary guardian name", ("students",),
             C(P("PrimaryContact", "FirstName", T), X(" "), P("PrimaryContact", "LastName", T)),
             ("guardian", "guardian name", "parent", "parent name", "contact name"), needs=("pcontact",),
             group="Primary guardian"),
    FieldDef("pg_email", "Primary guardian email", ("students",), F("PrimaryEmail", "Address", T, Fmt("lower")),
             ("guardian email", "parent email", "contact email"), needs=("pemail",), rule="email",
             group="Primary guardian"),
    FieldDef("pg_phone", "Primary guardian phone", ("students",), phone("PrimaryPhone"),
             ("guardian phone", "parent phone", "contact phone", "home phone", "phone"), needs=("pphone",),
             rule="phone10", group="Primary guardian"),
    # --- guardian rows
    FieldDef("g_id", "Guardian ID (ContactID)", ("guardians",), F("Contact", "ContactID"),
             ("guardian id", "parent id", "contact id", "guardianid"), group="Guardian"),
    FieldDef("g_first", "Guardian first name", ("guardians",), F("Contact", "FirstName", T),
             ("guardian first name", "parent first name", "contact first name"), group="Guardian"),
    FieldDef("g_last", "Guardian last name", ("guardians",), F("Contact", "LastName", T),
             ("guardian last name", "parent last name", "contact last name"), group="Guardian"),
    FieldDef("g_full", "Guardian full name", ("guardians",),
             C(P("Contact", "FirstName", T), X(" "), P("Contact", "LastName", T)),
             ("guardian name", "parent name", "contact name"), group="Guardian"),
    FieldDef("g_email", "Guardian email", ("guardians",), F("ContactEmail", "Address", T, Fmt("lower")),
             ("guardian email", "parent email", "contact email"), needs=("cemail",), rule="email", group="Guardian"),
    FieldDef("g_phone", "Guardian phone (10 digits)", ("guardians",), phone("ContactPhone"),
             ("guardian phone", "parent phone", "contact phone", "mobile", "cell", "phone number"),
             needs=("cphone",), rule="phone10", group="Guardian"),
    FieldDef("g_rel", "Relationship code", ("guardians",), F("StudentContact", "RelationshipCode"),
             ("relationship", "relation"), group="Guardian"),
    FieldDef("g_lang", "Guardian language", ("guardians",), F("Contact", "PrimaryLanguage"),
             ("guardian language", "parent language", "preferred language"), group="Guardian"),
    FieldDef("g_primary", "Primary contact (Y/N)", ("guardians",), RAW(YN.format(x="StudentContact.PrimaryContact")),
             ("primary", "primary contact"), rule="yn", group="Guardian"),
    FieldDef("g_pickup", "Can pick up (Y/N)", ("guardians",), RAW(YN.format(x="StudentContact.CheckInOut")),
             ("pickup", "can pick up", "authorized pickup"), rule="yn", group="Guardian"),
    FieldDef("g_custodial", "Custodial (Y/N)", ("guardians",), RAW(YN.format(x="StudentContact.Custodial")),
             ("custodial", "custody"), rule="yn", group="Guardian"),
    # --- staff
    FieldDef("emp_id", "Staff ID (employee number)", ("staff",), F("Employee", "EmployeeNumber", T),
             ("staff id", "employee id", "employee number", "teacher id", "id", "identifier", "sis id", "user id"),
             group="Staff"),
    FieldDef("emp_internal", "Staff internal ID (EmployeeID)", ("staff",), F("Employee", "EmployeeID"),
             ("internal id", "sam id"), group="Staff"),
    FieldDef("emp_first", "Staff first name", ("staff",), F("Employee", "FirstName", T),
             ("first name", "firstname", "first", "given name", "fname"), group="Staff"),
    FieldDef("emp_last", "Staff last name", ("staff",), F("Employee", "LastName", T),
             ("last name", "lastname", "last", "surname", "lname"), group="Staff"),
    FieldDef("emp_middle", "Staff middle name", ("staff",), F("Employee", "MiddleName", T), ("middle name", "middle"),
             group="Staff"),
    FieldDef("emp_full", "Staff full name", ("staff",), C(P("Employee", "FirstName", T), X(" "), P("Employee", "LastName", T)),
             ("full name", "name", "display name"), group="Staff"),
    FieldDef("emp_email", "Staff email", ("staff",), EM("Employee", "staff"), ("email", "email address", "e mail"),
             rule="email", group="Staff"),
    FieldDef("emp_user", "Staff username", ("staff",), UN("Employee", "staff"), ("username", "user name", "login"),
             group="Staff"),
    FieldDef("emp_role", "Role (Teacher / Staff)", ("staff",),
             F("Employee", "FacultyFlag", Fmt("map", "1=Teacher; 0=Staff")), ("role", "type", "position", "title",
                                                                               "user type"), group="Staff"),
    FieldDef("emp_hire", "Hire date (MM/DD/YYYY)", ("staff",), F("Employee", "HireDate", Fmt("date_us")),
             ("hire date", "start date"), rule="date_us", group="Staff"),
    FieldDef("emp_phone", "Staff phone (10 digits)", ("staff",), phone("StaffPhone"), ("phone", "mobile", "cell"),
             needs=("sphone",), rule="phone10", group="Staff"),
    FieldDef("emp_school_id", "School ID (SAM SchoolID)", ("staff",), F("SchoolDef", "SchoolID"),
             ("school id", "schoolid", "building id", "location id", "site id"), group="School"),
    # --- classes
    FieldDef("sec_id", "Section / class ID", ("enrollments", "sections"), F("ScheduleFramework", "ScheduleFrameworkID"),
             ("section id", "class id", "sectionid", "classid", "class sourcedid", "section"), group="Class"),
    FieldDef("sec_name", "Class name (course - period - section)", ("enrollments", "sections"),
             C(P("Course", "LongName", T), X(" - Period "), P("ScheduleFramework", "Period"), X(" - "),
               P("ScheduleFramework", "SectionNumber")),
             ("class name", "section name", "title", "class title", "name"), group="Class"),
    FieldDef("course_code", "Course code", ("enrollments", "sections"), F("Course", "CourseCode", T),
             ("course code", "course id", "course number", "coursecode"), group="Class"),
    FieldDef("course_name", "Course name", ("enrollments", "sections"), F("Course", "LongName", T),
             ("course name", "course", "subject"), group="Class"),
    FieldDef("period", "Period", ("enrollments", "sections"), F("ScheduleFramework", "Period"), ("period", "block"),
             group="Class"),
    FieldDef("sec_num", "Section number", ("enrollments", "sections"), F("ScheduleFramework", "SectionNumber"),
             ("section number",), group="Class"),
    FieldDef("teacher_id", "Teacher ID (employee number)", ("enrollments", "sections"),
             F("Teacher", "EmployeeNumber", T), ("teacher id", "instructor id", "staff id", "teacherid"), group="Class"),
    FieldDef("teacher_name", "Teacher name", ("enrollments", "sections"),
             C(P("Teacher", "FirstName", T), X(" "), P("Teacher", "LastName", T)),
             ("teacher", "teacher name", "instructor"), group="Class"),
    FieldDef("teacher_email", "Teacher email", ("enrollments", "sections"), EM("Teacher", "staff"),
             ("teacher email", "instructor email"), rule="email", group="Class"),
    FieldDef("term_start", "Term start (MM/DD/YYYY)", ("enrollments", "sections"),
             F("Schedule", "BeginDate", Fmt("date_us")), ("term start", "start date", "begin date"), rule="date_us",
             group="Class"),
    FieldDef("term_end", "Term end (MM/DD/YYYY)", ("enrollments", "sections"), F("Schedule", "EndDate", Fmt("date_us")),
             ("term end", "end date"), rule="date_us", group="Class"),
    FieldDef("term_name", "Term / schedule code", ("enrollments", "sections"), F("Schedule", "ScheduleCode"),
             ("term", "term name", "semester", "session"), group="Class"),
    # --- schools (any base that has SchoolDef)
    FieldDef("sch_id", "School ID (SAM SchoolID)", ("enrollments", "sections", "schools"), F("SchoolDef", "SchoolID"),
             ("school id", "schoolid", "building id", "location id", "org id", "site id"), group="School"),
    FieldDef("sch_code", "School code", ALLB, F("SchoolDef", "SchoolCode"), ("school code", "school number", "building code"),
             group="School"),
    FieldDef("sch_name", "School name", ALLB, F("SchoolDef", "SchoolName", T),
             ("school", "school name", "building", "location", "site", "campus"), group="School"),
    FieldDef("sch_short", "School short name", ALLB, F("SchoolDef", "ShortName", T), ("short name", "site short name"),
             group="School"),
    FieldDef("sch_principal", "Principal name", ("schools",),
             C(P("Principal", "FirstName", T), X(" "), P("Principal", "LastName", T)), ("principal",), group="School"),
    FieldDef("sch_principal_email", "Principal email", ("schools",), EM("Principal", "staff"), ("principal email",),
             rule="email", group="School"),
    FieldDef("sch_low", "Lowest grade", ("schools",), F("SchoolDef", "LowestGradeTaught"), ("low grade", "lowest grade"),
             group="School"),
    FieldDef("sch_high", "Highest grade", ("schools",), F("SchoolDef", "HighestGradeTaught"),
             ("high grade", "highest grade"), group="School"),
]
FIELD = {f.key: f for f in FIELDS}
SPECIAL = {"__blank__": "(leave blank)", "__text__": "Fixed text..."}


def fields_for(base: str) -> list[FieldDef]:
    return [f for f in FIELDS if base in f.bases]


# ----------------------------------------------------------------------------- reading the vendor template
def read_template(text: str = "", path: str | None = None) -> tuple[list[str], list[list[str]]]:
    """Headers + up to 5 sample rows from a vendor CSV / TXT (comma, tab, pipe or semicolon) or a pasted header."""
    if path:
        text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    text = text.strip("﻿\r\n ")
    if not text:
        return [], []
    first = text.splitlines()[0]
    delim = max([",", "\t", "|", ";"], key=first.count)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    rows = [r for r in rows if any(c.strip() for c in r)]
    heads = [h.strip() for h in rows[0]] if rows else []
    return heads, rows[1:6]


def _norm(s: str) -> str:
    s = re.sub(r"\[.*?\]|\(.*?\)", " ", s.lower())        # drop "[Required]" / "(Y/N)" decorations
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return " ".join(re.findall(r"[a-z0-9]+", s.replace("_", " ")))


def _split_camel(s: str) -> str:
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", s)


def suggest_base(headers: list[str]) -> str:
    h = " ".join(_norm(_split_camel(x)) for x in headers)
    has = lambda *w: any(x in h for x in w)  # noqa: E731
    # one row per guardian when the guardian has their own name / ID / relationship columns;
    # a student row with just "parent email / phone" uses the primary guardian instead
    if re.search(r"\b(guardian|parent|contact)( first| last)? (first name|last name|name|id|first|last)\b", h) or \
            (has("guardian", "parent", "contact") and has("relationship")):
        return "guardians"
    if has("section", "class id", "period", "course") and has("student"):
        return "enrollments"
    if has("section", "class id", "class name", "period") and not has("student"):
        return "sections"
    if has("principal", "low grade", "lowest grade") or (has("school") and len(headers) <= 4 and not
                                                           has("student", "first name", "teacher")):
        return "schools"
    if has("staff", "employee", "hire", "position") and not has("student", "grade"):
        return "staff"
    return "students"


# ----------------------------------------------------------------------------- learning from corrections
def _learned_path() -> Path:
    from .paths import root_dir
    return root_dir() / "learned_fields.json"


def load_learned() -> dict:
    """{normalized heading: {base: field}} from your saved corrections plus every custom / shared package."""
    out: dict[str, dict[str, str]] = {}
    try:
        from .shared_library import load_shared
        pkgs = load_shared() + load_custom()
    except Exception:
        pkgs = []
    for p in pkgs:                                   # packages first, your own corrections win
        for fe in p.get("files", []):
            for m in fe.get("mapping", []) or []:
                if m.get("field") in FIELD and fe.get("base"):
                    out.setdefault(_norm(_split_camel(m["heading"])), {})[fe["base"]] = m["field"]
    try:
        for k, v in json.loads(_learned_path().read_text(encoding="utf-8")).items():
            out.setdefault(k, {}).update(v)
    except Exception:
        pass
    return out


def learn(base: str, mapping: list[dict], suggested: dict | None = None) -> int:
    """Remember the field chosen for each vendor heading (only where it differs from what was suggested,
    or every mapped column when no suggestions are given). Returns how many were learned."""
    try:
        data = json.loads(_learned_path().read_text(encoding="utf-8"))
    except Exception:
        data = {}
    n = 0
    for m in mapping:
        f = m.get("field")
        if f not in FIELD:
            continue
        key = _norm(_split_camel(m["heading"]))
        if suggested is not None and suggested.get(m["heading"]) == f:
            continue
        if data.get(key, {}).get(base) != f:
            data.setdefault(key, {})[base] = f
            n += 1
    if n:
        _learned_path().write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    return n


def suggest_field(header: str, base: str, sample: str = "", learned: dict | None = None) -> tuple[str, float]:
    """(field key or '__blank__', confidence 0-1). Learned matches come back with confidence 1.0."""
    n = _norm(_split_camel(header))
    if not n:
        return "__blank__", 0.0
    hit = (learned or {}).get(n, {}).get(base)
    if hit in FIELD and base in FIELD[hit].bases:
        return hit, 1.0
    best, score = "__blank__", 0.0
    for f in fields_for(base):
        cands = [_norm(s) for s in f.synonyms] + [_norm(f.label)]
        for c in cands:
            if n == c:
                sc = 1.0
            else:
                sc = difflib.SequenceMatcher(None, n, c).ratio()
                if c and (n.startswith(c + " ") or n.endswith(" " + c)):
                    sc = max(sc, 0.8)
            if sc > score:
                best, score = f.key, sc
    # date formats: follow the vendor's sample value
    if best == "stu_dob" and re.match(r"^\d{4}-\d{2}-\d{2}$", sample or ""):
        best = "stu_dob_iso"
    if best in ("stu_grade",) and re.match(r"^\d{1,2}$", sample or "") and sample not in ("01", "02", "03", "04", "05",
                                                                                        "06", "07", "08", "09"):
        best = "stu_grade_num"
    return (best, score) if score >= 0.72 else ("__blank__", score)


def auto_map(headers: list[str], base: str, samples: list[list[str]] | None = None) -> list[dict]:
    out = []
    learned = load_learned()
    for i, h in enumerate(headers):
        sample = next((r[i] for r in (samples or []) if i < len(r) and r[i].strip()), "")
        key, conf = suggest_field(h, base, sample, learned)
        out.append({"heading": h, "field": key, "text": "", "required": False, "unique": False,
                    "confidence": round(conf, 2)})
    # the first ID-like column is the key
    for m in out:
        if m["field"] in ("stu_id", "emp_id", "sec_id", "sch_id", "g_id"):
            m["unique"] = base != "guardians" or m["field"] == "g_id"
            m["required"] = True
            break
    return out


# ----------------------------------------------------------------------------- building the package
def build_query_dict(base: str, mapping: list[dict], name: str = "") -> dict:
    q = BASES[base][1]()
    q.name = name
    needs: list[str] = []
    cols = []
    for m in mapping:
        h = m["heading"]
        key = m.get("field") or "__blank__"
        if key == "__text__" or key == "__blank__":
            cols.append(OutColumn("custom", heading=h, parts=[Part("text", value=m.get("text", "") if key == "__text__"
                                                                   else "")]))
            continue
        fd = FIELD[key]
        col = fd.make()
        col.heading = h
        cols.append(col)
        for n in fd.needs:
            for dep in CHAIN_NEEDS.get(n, []) + [n]:
                if dep not in needs:
                    needs.append(dep)
    order = ["hr", "counselor", "pcontact", "pphone", "pemail", "cphone", "cemail", "addr", "sphone"]
    for n in sorted(needs, key=order.index):
        tables, links = CHAINS[n]
        for t in tables:
            q.tables.append(TableRef(*t))
        q.links += [Link(*l) for l in links]
    q.columns = cols
    return q.to_dict()


def rules_for(mapping: list[dict]) -> dict:
    req = [m["heading"] for m in mapping if m.get("required")]
    uniq = [m["heading"] for m in mapping if m.get("unique")]
    fmts = {m["heading"]: FIELD[m["field"]].rule for m in mapping
            if m.get("field") in FIELD and FIELD[m["field"]].rule}
    return {"required": req, "unique": [uniq] if uniq else [], "formats": fmts}


def requires_for(qdicts: list[dict]) -> list[str]:
    text = json.dumps(qdicts)
    need = sorted(set(re.findall(r"\{\{(OWNER_TYPE_[A-Z]+)\}\}", text)))
    return need


def make_package(pkg: dict) -> dict:
    """Turn the builder's package (name, works_with, files with base + mapping) into a platform dict."""
    files, rules = [], {"files": {}}
    for fe in pkg["files"]:
        qd = build_query_dict(fe["base"], fe["mapping"], f"{pkg['name']} - {fe['file']}")
        files.append({"file": fe["file"], "note": fe.get("note", ""), "query": qd, "base": fe["base"],
                      "mapping": fe["mapping"]})
        rules["files"][fe["file"]] = rules_for(fe["mapping"])
    return {
        "id": pkg["id"], "name": pkg["name"], "custom": True, "category": "My packages",
        "works_with": pkg.get("works_with", ""), "description": pkg.get("description") or
        "Built with the vendor template builder from the vendor's own file layout.",
        "spec_url": pkg.get("spec_url", ""), "delivery": pkg.get("delivery", ""),
        "requires": requires_for([f["query"] for f in files]), "rules": rules, "files": files,
        "builder_version": 1,
    }


# ----------------------------------------------------------------------------- storage
def store_dir() -> Path:
    from .paths import root_dir
    p = root_dir() / "custom_packages"
    p.mkdir(parents=True, exist_ok=True)
    return p


def slug(name: str) -> str:
    return "custom-" + (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "package")


def load_custom() -> list[dict]:
    out = []
    for p in sorted(store_dir().glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("files"):
                out.append(d)
        except Exception:
            pass
    return out


def save_custom(platform: dict) -> Path:
    p = store_dir() / f"{platform['id']}.json"
    p.write_text(json.dumps(platform, indent=1), encoding="utf-8")
    from .audit import record
    record("My packages", f"Saved package '{platform['name']}' ({len(platform['files'])} file(s))")
    return p


def delete_custom(pid: str) -> bool:
    p = store_dir() / f"{pid}.json"
    if p.exists():
        p.unlink()
        from .audit import record
        record("My packages", f"Deleted package {pid}")
        return True
    return False


def export_package(platform: dict, path):
    Path(path).write_text(json.dumps({"samqb_package": 1, "platform": platform}, indent=1), encoding="utf-8")


def import_package(path) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    plat = d.get("platform") if isinstance(d, dict) and "platform" in d else d
    if not isinstance(plat, dict) or not plat.get("files"):
        raise ValueError("This is not a SAM Ad Hoc Query Builder package file.")
    for fe in plat["files"]:
        QueryDef.from_dict(fe["query"])                  # validates the query structure
        if fe.get("base") and fe.get("mapping"):         # rebuild from the mapping so only known fields are used
            unknown = [m["field"] for m in fe["mapping"] if m.get("field") not in FIELD and
                       m.get("field") not in SPECIAL]
            if unknown:
                raise ValueError(f"Unknown fields in {fe['file']}: {', '.join(unknown)}")
    plat["custom"] = True
    plat["category"] = "My packages"
    existing = {p["id"] for p in load_custom()}
    if not str(plat.get("id", "")).startswith("custom-"):
        plat["id"] = slug(plat.get("name", "package"))
    base, n = plat["id"], 2
    while plat["id"] in existing:
        plat["id"], n = f"{base}-{n}", n + 1
    if all(fe.get("base") and fe.get("mapping") for fe in plat["files"]):
        plat = make_package({**plat, "files": [{"file": fe["file"], "base": fe["base"], "mapping": fe["mapping"],
                                                "note": fe.get("note", "")} for fe in plat["files"]]})
    save_custom(plat)
    return plat
