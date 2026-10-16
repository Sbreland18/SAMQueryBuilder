"""Generates data/exports.json - platform export packages (one SAM query per required CSV file).

Column headers follow each vendor's published CSV specification. IDs are kept consistent
inside each package (e.g. the Section id in sections.csv matches enrollments.csv).

Placeholders such as {{STAFF_EMAIL_DOMAIN}} and the special "username"/"email" pieces are
filled in from File > District Settings when a user opens the query.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sam_qb.query_model import (QueryDef, OutColumn, Fmt, Part, Link, FilterGroup, Condition,  # noqa: E402
                                SortItem)

GRADE_CLEVER = ("PK=PreKindergarten; KG=Kindergarten; K=Kindergarten; 01=1; 02=2; 03=3; 04=4; 05=5; 06=6; "
                "07=7; 08=8; 09=9; 10=10; 11=11; 12=12")
GRADE_NWEA = "PK=PK; KG=K; 01=1; 02=2; 03=3; 04=4; 05=5; 06=6; 07=7; 08=8; 09=9"
SEX_ONEROSTER = "M=male; F=female"


# ---------------------------------------------------------------- column helpers
def F(alias, col, heading, *fmts):
    return OutColumn("field", alias, col, heading, list(fmts))


def T(heading, text=""):
    """Constant column (or blank when text is empty)."""
    return OutColumn("custom", heading=heading, parts=[Part("text", value=text)])


def C(heading, *parts, fmts=()):
    return OutColumn("custom", heading=heading, parts=list(parts), formats=list(fmts))


def P(alias, col, *fmts):
    return Part("field", alias, col, formats=list(fmts))


def X(text):
    return Part("text", value=text)


def EMAIL(alias, role):
    return Part("email", alias, value=role)


def USER(alias, role):
    return Part("username", alias, value=role)


def NAME(alias):
    return [P(alias, "FirstName"), X(" "), P(alias, "LastName")]


# ---------------------------------------------------------------- shared table setups
def query(name, tables, links, cols, conds=(), distinct=False, sort=(), parts=()):
    q = QueryDef(name=name, distinct=distinct)
    for t in tables:
        if isinstance(t, tuple):
            q.tables.append(__import__("sam_qb.query_model", fromlist=["TableRef"]).TableRef(*t))
        else:
            q.add_table(t)
    q.links = [Link(*l) for l in links]
    q.columns = cols
    q.filters = [FilterGroup("ALL", list(conds))] if conds else []
    q.sort = [SortItem(*s) if isinstance(s, tuple) else SortItem(s) for s in sort]
    q.union_parts = list(parts)
    return q


STU_T = ["Student", "stuSchool"]
STU_L = [("Student", "StudentID", "stuSchool", "StudentID", "INNER")]
STU_C = [Condition("stuSchool", "PrimarySchoolFlag", "eq", "1"),
         Condition("Student", "EnrollmentStatus", "in", "{{ENROLLED_STATUS_CODES}}")]

EMP_T = ["Employee", "empSchool"]
EMP_L = [("Employee", "EmployeeID", "empSchool", "EmployeeID", "INNER")]
EMP_C = [Condition("empSchool", "PrimarySchoolFlag", "eq", "1"),
         Condition("Employee", "FacultyFlag", "eq", "1"),
         Condition("Employee", "TerminationDate", "blank")]

SEC_T = ["ScheduleFramework", "ScheduleCourseTerm", "ScheduleCourse", "Course", "Schedule"]
SEC_L = [("ScheduleFramework", "ScheduleCourseTermID", "ScheduleCourseTerm", "ScheduleCourseTermID", "INNER"),
         ("ScheduleCourseTerm", "ScheduleCourseID", "ScheduleCourse", "ScheduleCourseID", "INNER"),
         ("ScheduleCourse", "CourseID", "Course", "CourseID", "INNER"),
         ("ScheduleCourse", "ScheduleID", "Schedule", "ScheduleID", "INNER")]
LIVE = Condition("Schedule", "LiveFlag", "eq", "1")

ROS_T = ["ScheduleRoster", "Student"] + SEC_T
ROS_L = [("ScheduleRoster", "StudentID", "Student", "StudentID", "INNER"),
         ("ScheduleRoster", "ScheduleFrameworkID", "ScheduleFramework", "ScheduleFrameworkID", "INNER")] + SEC_L
ROS_C = [LIVE, Condition("ScheduleRoster", "WithdrawnDate", "blank"),
         Condition("Student", "EnrollmentStatus", "in", "{{ENROLLED_STATUS_CODES}}")]

TCH_T = SEC_T + ["Employee"]
TCH_L = SEC_L + [("ScheduleFramework", "TeacherID", "Employee", "EmployeeID", "INNER")]

CLASS_TITLE = C("title", P("Course", "LongName", Fmt("trim")), X(" - Period "), P("ScheduleFramework", "Period"),
                X(" - "), P("ScheduleFramework", "SectionNumber"))


def class_title(heading):
    c = json.loads(json.dumps(CLASS_TITLE.__dict__, default=lambda o: o.__dict__))
    out = C(heading, *[Part(p["kind"], p["alias"], p["column"], p["value"], [Fmt(**f) for f in p["formats"]])
                       for p in c["parts"]])
    return out


# ================================================================= CLEVER
def clever():
    schools = query(
        "Clever - schools.csv",
        ["SchoolDef", ("Employee", "Employee")],
        [("SchoolDef", "SchoolPrincipalID", "Employee", "EmployeeID", "LEFT")],
        [F("SchoolDef", "SchoolID", "School_id"), F("SchoolDef", "SchoolName", "School_name", Fmt("trim")),
         F("SchoolDef", "SchoolCode", "School_number"),
         F("SchoolDef", "LowestGradeTaught", "Low_grade", Fmt("map", GRADE_CLEVER)),
         F("SchoolDef", "HighestGradeTaught", "High_grade", Fmt("map", GRADE_CLEVER)),
         C("Principal", *NAME("Employee")), C("Principal_email", EMAIL("Employee", "staff"))],
        [Condition("SchoolDef", "ActiveFlag", "eq", "1")], sort=["School_name"])
    students = query(
        "Clever - students.csv", STU_T, STU_L,
        [F("stuSchool", "SchoolID", "School_id"), F("Student", "StudentCode", "Student_id", Fmt("trim")),
         F("Student", "StudentCode", "Student_number", Fmt("trim")), F("Student", "StateCode", "State_id"),
         F("Student", "LastName", "Last_name", Fmt("trim")), F("Student", "MiddleName", "Middle_name", Fmt("trim")),
         F("Student", "FirstName", "First_name", Fmt("trim")),
         F("Student", "ADAGrade", "Grade", Fmt("map", GRADE_CLEVER)),
         F("Student", "GenderCode", "Gender"), F("Student", "DOB", "DOB", Fmt("date_us")),
         C("Student_email", EMAIL("Student", "student")), C("Username", USER("Student", "student"))],
        STU_C, sort=["Last_name", "First_name"])
    teachers = query(
        "Clever - teachers.csv", EMP_T, EMP_L,
        [F("empSchool", "SchoolID", "School_id"), F("Employee", "EmployeeID", "Teacher_id"),
         F("Employee", "EmployeeNumber", "Teacher_number", Fmt("trim")),
         C("Teacher_email", EMAIL("Employee", "staff")),
         F("Employee", "FirstName", "First_name", Fmt("trim")), F("Employee", "LastName", "Last_name", Fmt("trim")),
         C("Username", USER("Employee", "staff"))],
        EMP_C, distinct=True, sort=["Last_name", "First_name"])
    sections = query(
        "Clever - sections.csv", SEC_T, SEC_L,
        [F("Schedule", "SchoolID", "School_id"), F("ScheduleFramework", "ScheduleFrameworkID", "Section_id"),
         F("ScheduleFramework", "TeacherID", "Teacher_id"), class_title("Name"),
         F("ScheduleFramework", "SectionNumber", "Section_number"),
         F("Course", "LongName", "Course_name", Fmt("trim")), F("Course", "CourseCode", "Course_number"),
         F("ScheduleFramework", "Period", "Period"), F("Schedule", "ScheduleCode", "Term_name"),
         F("Schedule", "BeginDate", "Term_start", Fmt("date_us")), F("Schedule", "EndDate", "Term_end", Fmt("date_us"))],
        [LIVE, Condition("ScheduleFramework", "TeacherID", "not_blank")], sort=["School_id", "Name"])
    enrollments = query(
        "Clever - enrollments.csv", ROS_T, ROS_L,
        [F("Schedule", "SchoolID", "School_id"), F("ScheduleRoster", "ScheduleFrameworkID", "Section_id"),
         F("Student", "StudentCode", "Student_id", Fmt("trim"))],
        ROS_C, distinct=True)
    return {
        "id": "clever", "name": "Clever",
        "works_with": "Clever and the apps rostered through it (i-Ready, IXL, Renaissance, Khan Academy, Amplify, Lexia, Zearn and many more)",
        "description": "Clever's SFTP/CSV roster format: schools, students, teachers, sections and enrollments. "
                       "Upload the five files to your Clever SFTP folder (or Clever's manual upload).",
        "spec_url": "https://schools.clever.com/files/clever-sftp.pdf",
        "delivery": "Clever SFTP (sftp.clever.com) or Clever Dashboard > Sync > Upload",
        "files": [f("schools.csv", schools), f("students.csv", students), f("teachers.csv", teachers),
                  f("sections.csv", sections), f("enrollments.csv", enrollments)],
    }


def f(file, q, note=""):
    q.name = q.name or file
    return {"file": file, "note": note, "query": q.to_dict()}


# ================================================================= OneRoster 1.1
def oneroster():
    B = [T("status"), T("dateLastModified")]  # bulk files: present but blank
    orgs = query(
        "OneRoster - orgs.csv", ["DistrictDef"], [],
        [T("sourcedId", "district")] + B + [F("DistrictDef", "DistrictName", "name", Fmt("trim")), T("type", "district"),
                                            F("DistrictDef", "DistrictCode", "identifier"), T("parentSourcedId")],
        parts=[query("Schools", ["SchoolDef"], [],
                     [F("SchoolDef", "SchoolID", "sourcedId")] + B +
                     [F("SchoolDef", "SchoolName", "name", Fmt("trim")), T("type", "school"),
                      F("SchoolDef", "SchoolCode", "identifier"), T("parentSourcedId", "district")],
                     [Condition("SchoolDef", "ActiveFlag", "eq", "1")])])
    orgs.name = "OneRoster - orgs.csv"
    sessions = query(
        "OneRoster - academicSessions.csv", ["Schedule"], [],
        [F("Schedule", "ScheduleID", "sourcedId")] + B +
        [F("Schedule", "ScheduleCode", "title"), T("type", "schoolYear"), F("Schedule", "BeginDate", "startDate", Fmt("date_iso")),
         F("Schedule", "EndDate", "endDate", Fmt("date_iso")), T("parentSourcedId"),
         F("Schedule", "EndDate", "schoolYear", Fmt("year"))],
        [LIVE])
    courses = query(
        "OneRoster - courses.csv", ["ScheduleCourse", "Course", "Schedule"],
        [("ScheduleCourse", "CourseID", "Course", "CourseID", "INNER"),
         ("ScheduleCourse", "ScheduleID", "Schedule", "ScheduleID", "INNER")],
        [F("Course", "CourseID", "sourcedId")] + B +
        [T("schoolYearSourcedId"), F("Course", "LongName", "title", Fmt("trim")), F("Course", "CourseCode", "courseCode"),
         T("grades"), T("orgSourcedId", "district"), T("subjects"), T("subjectCodes")],
        [LIVE], distinct=True)
    classes = query(
        "OneRoster - classes.csv", SEC_T, SEC_L,
        [F("ScheduleFramework", "ScheduleFrameworkID", "sourcedId")] + B +
        [class_title("title"), T("grades"), F("Course", "CourseID", "courseSourcedId"),
         F("ScheduleFramework", "SectionNumber", "classCode"), T("classType", "scheduled"),
         F("ScheduleFramework", "Room", "location"), F("Schedule", "SchoolID", "schoolSourcedId"),
         F("Schedule", "ScheduleID", "termSourcedIds"), T("subjects"), T("subjectCodes"),
         F("ScheduleFramework", "Period", "periods")],
        [LIVE])
    stu_user = [F("Student", "StudentCode", "sourcedId", Fmt("trim"))] + B + [
        T("enabledUser", "true"), F("stuSchool", "SchoolID", "orgSourcedIds"), T("role", "student"),
        C("username", EMAIL("Student", "student")), T("userIds"), F("Student", "FirstName", "givenName", Fmt("trim")),
        F("Student", "LastName", "familyName", Fmt("trim")), F("Student", "MiddleName", "middleName", Fmt("trim")),
        F("Student", "StudentCode", "identifier", Fmt("trim")), C("email", EMAIL("Student", "student")),
        T("sms"), T("phone"), T("agentSourcedIds"), F("Student", "ADAGrade", "grades"), T("password")]
    tch_user = [C("sourcedId", X("T"), P("Employee", "EmployeeID"))] + B + [
        T("enabledUser", "true"), F("empSchool", "SchoolID", "orgSourcedIds"), T("role", "teacher"),
        C("username", EMAIL("Employee", "staff")), T("userIds"), F("Employee", "FirstName", "givenName", Fmt("trim")),
        F("Employee", "LastName", "familyName", Fmt("trim")), F("Employee", "MiddleName", "middleName", Fmt("trim")),
        F("Employee", "EmployeeNumber", "identifier", Fmt("trim")), C("email", EMAIL("Employee", "staff")),
        T("sms"), T("phone"), T("agentSourcedIds"), T("grades"), T("password")]
    users = query("OneRoster - users.csv", STU_T, STU_L, stu_user, STU_C,
                  parts=[query("Teachers", EMP_T, EMP_L, tch_user, EMP_C, distinct=True)])
    enr = query(
        "OneRoster - enrollments.csv", ROS_T, ROS_L,
        [C("sourcedId", X("S"), P("ScheduleRoster", "ScheduleRosterID"))] + B +
        [F("ScheduleRoster", "ScheduleFrameworkID", "classSourcedId"), F("Schedule", "SchoolID", "schoolSourcedId"),
         F("Student", "StudentCode", "userSourcedId", Fmt("trim")), T("role", "student"), T("primary", "false"),
         T("beginDate"), T("endDate")],
        ROS_C,
        parts=[query("Teachers", TCH_T, TCH_L,
                     [C("sourcedId", X("T"), P("ScheduleFramework", "ScheduleFrameworkID"))] + B +
                     [F("ScheduleFramework", "ScheduleFrameworkID", "classSourcedId"),
                      F("Schedule", "SchoolID", "schoolSourcedId"),
                      C("userSourcedId", X("T"), P("Employee", "EmployeeID")), T("role", "teacher"),
                      T("primary", "true"), T("beginDate"), T("endDate")],
                     [LIVE])])
    demo = query(
        "OneRoster - demographics.csv", STU_T, STU_L,
        [F("Student", "StudentCode", "sourcedId", Fmt("trim"))] + B +
        [F("Student", "DOB", "birthDate", Fmt("date_iso")), F("Student", "GenderCode", "sex", Fmt("map", SEX_ONEROSTER))] +
        [T(h) for h in ("americanIndianOrAlaskaNative", "asian", "blackOrAfricanAmerican",
                        "nativeHawaiianOrOtherPacificIslander", "white", "demographicRaceTwoOrMoreRaces",
                        "hispanicOrLatinoEthnicity", "countryOfBirthCode", "stateOfBirthAbbreviation",
                        "cityOfBirth", "publicSchoolResidenceStatus")],
        STU_C)
    manifest = ("propertyName,value\nmanifest.version,1.0\noneroster.version,1.1\n"
                "file.academicSessions,bulk\nfile.categories,absent\nfile.classes,bulk\nfile.classResources,absent\n"
                "file.courses,bulk\nfile.courseResources,absent\nfile.demographics,bulk\nfile.enrollments,bulk\n"
                "file.lineItems,absent\nfile.orgs,bulk\nfile.resources,absent\nfile.results,absent\nfile.users,bulk\n"
                "source.systemName,SAM\n")
    return {
        "id": "oneroster11", "name": "OneRoster 1.1 (CSV)",
        "works_with": "ClassLink, Schoology, Canvas, Google Classroom via ClassLink, Microsoft SDS, McGraw Hill, Savvas, HMH, Great Minds and most other OneRoster-certified apps",
        "description": "The 1EdTech OneRoster 1.1 bulk CSV set. Zip the CSV files together with manifest.csv "
                       "(created for you when you save the package) and upload to the vendor or to ClassLink Roster Server.",
        "spec_url": "https://www.imsglobal.org/oneroster-v11-final-csv-tables",
        "delivery": "Zip all files (including manifest.csv) and upload by SFTP or the vendor's import page",
        "static_files": {"manifest.csv": manifest},
        "files": [f("orgs.csv", orgs), f("academicSessions.csv", sessions), f("courses.csv", courses),
                  f("classes.csv", classes), f("users.csv", users), f("enrollments.csv", enr),
                  f("demographics.csv", demo)],
    }


# ================================================================= Microsoft SDS v2.1
def sds():
    orgs = query("SDS - orgs.csv", ["DistrictDef"], [],
                 [T("sourcedId", "district"), F("DistrictDef", "DistrictName", "name", Fmt("trim")),
                  T("type", "district"), T("parentSourcedId")],
                 parts=[query("Schools", ["SchoolDef"], [],
                              [F("SchoolDef", "SchoolID", "sourcedId"), F("SchoolDef", "SchoolName", "name", Fmt("trim")),
                               T("type", "school"), T("parentSourcedId", "district")],
                              [Condition("SchoolDef", "ActiveFlag", "eq", "1")])])
    users = query("SDS - users.csv", STU_T, STU_L,
                  [F("Student", "StudentCode", "sourcedId", Fmt("trim")), C("username", EMAIL("Student", "student")),
                   F("Student", "LastName", "familyName", Fmt("trim")), F("Student", "FirstName", "givenName", Fmt("trim")),
                   C("email", EMAIL("Student", "student")), F("Student", "StudentCode", "userNumber", Fmt("trim"))],
                  STU_C,
                  parts=[query("Teachers", EMP_T, EMP_L,
                               [C("sourcedId", X("T"), P("Employee", "EmployeeID")), C("username", EMAIL("Employee", "staff")),
                                F("Employee", "LastName", "familyName", Fmt("trim")),
                                F("Employee", "FirstName", "givenName", Fmt("trim")),
                                C("email", EMAIL("Employee", "staff")), F("Employee", "EmployeeNumber", "userNumber")],
                               EMP_C, distinct=True)])
    roles = query("SDS - roles.csv", STU_T, STU_L,
                  [F("Student", "StudentCode", "userSourcedId", Fmt("trim")), F("stuSchool", "SchoolID", "orgSourcedId"),
                   T("role", "student"), T("sessionSourcedId"), F("Student", "ADAGrade", "grade"), T("isPrimary", "true")],
                  STU_C,
                  parts=[query("Teachers", EMP_T, EMP_L,
                               [C("userSourcedId", X("T"), P("Employee", "EmployeeID")),
                                F("empSchool", "SchoolID", "orgSourcedId"), T("role", "teacher"), T("sessionSourcedId"),
                                T("grade"), T("isPrimary", "true")],
                               EMP_C, distinct=True)])
    sessions = query("SDS - academicSessions.csv", ["Schedule"], [],
                     [F("Schedule", "ScheduleID", "sourcedId"), F("Schedule", "ScheduleCode", "title"),
                      T("type", "schoolYear"), F("Schedule", "EndDate", "schoolYear", Fmt("year")),
                      F("Schedule", "BeginDate", "startDate", Fmt("date_iso")),
                      F("Schedule", "EndDate", "endDate", Fmt("date_iso"))], [LIVE])
    classes = query("SDS - classes.csv", SEC_T, SEC_L,
                    [F("ScheduleFramework", "ScheduleFrameworkID", "sourcedId"), F("Schedule", "SchoolID", "orgSourcedId"),
                     class_title("title"), F("Schedule", "ScheduleID", "sessionSourcedIds"),
                     F("Course", "CourseID", "courseSourcedId"), F("Course", "CourseCode", "code")], [LIVE])
    courses = query("SDS - courses.csv", ["ScheduleCourse", "Course", "Schedule"],
                    [("ScheduleCourse", "CourseID", "Course", "CourseID", "INNER"),
                     ("ScheduleCourse", "ScheduleID", "Schedule", "ScheduleID", "INNER")],
                    [F("Course", "CourseID", "sourcedId"), T("orgSourcedId", "district"),
                     F("Course", "LongName", "title", Fmt("trim")), F("Course", "CourseCode", "code")],
                    [LIVE], distinct=True)
    enr = query("SDS - enrollments.csv", ROS_T, ROS_L,
                [F("ScheduleRoster", "ScheduleFrameworkID", "classSourcedId"),
                 F("Student", "StudentCode", "userSourcedId", Fmt("trim")), T("role", "student")],
                ROS_C, distinct=True,
                parts=[query("Teachers", TCH_T, TCH_L,
                             [F("ScheduleFramework", "ScheduleFrameworkID", "classSourcedId"),
                              C("userSourcedId", X("T"), P("Employee", "EmployeeID")), T("role", "teacher")],
                             [LIVE])])
    return {
        "id": "sds21", "name": "Microsoft School Data Sync (SDS v2.1)",
        "works_with": "Microsoft 365 / Teams for Education class teams, Microsoft Entra ID accounts and Education Insights",
        "description": "School Data Sync v2.1 CSV format. Usernames must match the users' Microsoft 365 sign-in (UPN), "
                       "so check the email domains and username patterns in District Settings first.",
        "spec_url": "https://learn.microsoft.com/en-us/schooldatasync/sds-v2.1-csv-file-format",
        "delivery": "SDS > Data sync > Upload CSV files (or the SDS SFTP option); send the same set of files every time",
        "files": [f("orgs.csv", orgs), f("users.csv", users), f("roles.csv", roles),
                  f("academicSessions.csv", sessions), f("courses.csv", courses), f("classes.csv", classes),
                  f("enrollments.csv", enr)],
    }


# ================================================================= Google Workspace
def google():
    hdr = ["First Name [Required]", "Last Name [Required]", "Email Address [Required]", "Password [Required]",
           "Org Unit Path [Required]", "Employee ID"]
    students = query("Google - student accounts.csv", STU_T + ["SchoolDef"],
                     STU_L + [("stuSchool", "SchoolID", "SchoolDef", "SchoolID", "INNER")],
                     [F("Student", "FirstName", hdr[0], Fmt("trim")), F("Student", "LastName", hdr[1], Fmt("trim")),
                      C(hdr[2], EMAIL("Student", "student")), T(hdr[3], "{{DEFAULT_PASSWORD}}"),
                      T(hdr[4], "{{GOOGLE_STUDENT_OU}}"), F("Student", "StudentCode", hdr[5], Fmt("trim"))],
                     STU_C, sort=[hdr[1], hdr[0]])
    staff = query("Google - staff accounts.csv", EMP_T, EMP_L,
                  [F("Employee", "FirstName", hdr[0], Fmt("trim")), F("Employee", "LastName", hdr[1], Fmt("trim")),
                   C(hdr[2], EMAIL("Employee", "staff")), T(hdr[3], "{{DEFAULT_PASSWORD}}"),
                   T(hdr[4], "{{GOOGLE_STAFF_OU}}"), F("Employee", "EmployeeNumber", hdr[5], Fmt("trim"))],
                  [Condition("Employee", "TerminationDate", "blank"),
                   Condition("empSchool", "PrimarySchoolFlag", "eq", "1")], distinct=True, sort=[hdr[1], hdr[0]])
    return {
        "id": "google", "name": "Google Workspace for Education (user accounts)",
        "works_with": "Google Admin console bulk user upload (also GoGuardian, Securly and other tools that read Google accounts)",
        "description": "Bulk add/update user CSV for the Google Admin console. **** in the Password column keeps "
                       "existing passwords unchanged; set a starting password in District Settings for new accounts. "
                       "Edit the Org Unit Path column in Step 3 if you use per-school or per-grade OUs.",
        "spec_url": "https://support.google.com/a/answer/40057",
        "delivery": "Google Admin console > Directory > Users > Bulk update users > Attach CSV",
        "files": [f("google_students.csv", students), f("google_staff.csv", staff)],
    }


# ================================================================= Canvas
def canvas():
    users = query("Canvas - users.csv", STU_T, STU_L,
                  [F("Student", "StudentCode", "user_id", Fmt("trim")), C("login_id", EMAIL("Student", "student")),
                   F("Student", "FirstName", "first_name", Fmt("trim")), F("Student", "LastName", "last_name", Fmt("trim")),
                   C("email", EMAIL("Student", "student")), T("status", "active")],
                  STU_C,
                  parts=[query("Teachers", EMP_T, EMP_L,
                               [C("user_id", X("T"), P("Employee", "EmployeeID")), C("login_id", EMAIL("Employee", "staff")),
                                F("Employee", "FirstName", "first_name", Fmt("trim")),
                                F("Employee", "LastName", "last_name", Fmt("trim")),
                                C("email", EMAIL("Employee", "staff")), T("status", "active")],
                               EMP_C, distinct=True)])
    terms = query("Canvas - terms.csv", ["Schedule"], [],
                  [F("Schedule", "ScheduleID", "term_id"), F("Schedule", "ScheduleCode", "name"), T("status", "active"),
                   F("Schedule", "BeginDate", "start_date", Fmt("date_iso")),
                   F("Schedule", "EndDate", "end_date", Fmt("date_iso"))], [LIVE])
    courses = query("Canvas - courses.csv", SEC_T, SEC_L,
                    [F("ScheduleFramework", "ScheduleFrameworkID", "course_id"),
                     C("short_name", P("Course", "CourseCode", Fmt("trim")), X("-"), P("ScheduleFramework", "SectionNumber")),
                     class_title("long_name"), T("account_id"), F("Schedule", "ScheduleID", "term_id"),
                     T("status", "active")], [LIVE])
    enr = query("Canvas - enrollments.csv", ROS_T, ROS_L,
                [F("ScheduleRoster", "ScheduleFrameworkID", "course_id"), F("Student", "StudentCode", "user_id", Fmt("trim")),
                 T("role", "student"), T("status", "active")], ROS_C, distinct=True,
                parts=[query("Teachers", TCH_T, TCH_L,
                             [F("ScheduleFramework", "ScheduleFrameworkID", "course_id"),
                              C("user_id", X("T"), P("Employee", "EmployeeID")), T("role", "teacher"),
                              T("status", "active")], [LIVE])])
    return {
        "id": "canvas", "name": "Canvas LMS (SIS import)",
        "works_with": "Instructure Canvas",
        "description": "Canvas SIS Import CSVs: users, terms, courses (one per SAM class section) and enrollments. "
                       "account_id is left blank so courses go to the root account - fill it in Step 3 if you use sub-accounts.",
        "spec_url": "https://developerdocs.instructure.com/services/canvas/sis/file.sis_csv",
        "delivery": "Canvas Admin > SIS Import (zip the files) or the SIS Imports API",
        "files": [f("users.csv", users), f("terms.csv", terms), f("courses.csv", courses), f("enrollments.csv", enr)],
    }


# ================================================================= NWEA MAP Growth
def nwea():
    tables = ROS_T + ["Employee", "SchoolDef"]
    links = ROS_L + [("ScheduleFramework", "TeacherID", "Employee", "EmployeeID", "INNER"),
                     ("Schedule", "SchoolID", "SchoolDef", "SchoolID", "INNER")]
    cols = [F("SchoolDef", "SchoolCode", "School State Code"), F("SchoolDef", "SchoolName", "School Name", Fmt("trim")),
            T("Previous Instructor ID"), F("Employee", "EmployeeID", "Instructor ID"),
            T("Instructor State ID"), F("Employee", "LastName", "Instructor Last Name", Fmt("trim")),
            F("Employee", "FirstName", "Instructor First Name", Fmt("trim")),
            F("Employee", "MiddleName", "Instructor Middle Initial", Fmt("left", "1")),
            C("User Name", EMAIL("Employee", "staff")), C("Email Address", EMAIL("Employee", "staff")),
            class_title("Class Name"), T("Previous Student ID"), F("Student", "StudentCode", "Student ID", Fmt("trim")),
            F("Student", "StateCode", "Student State ID"), F("Student", "LastName", "Student Last Name", Fmt("trim")),
            F("Student", "FirstName", "Student First Name", Fmt("trim")),
            F("Student", "MiddleName", "Student Middle Initial", Fmt("left", "1")),
            F("Student", "DOB", "Student Date Of Birth", Fmt("date_us")), F("Student", "GenderCode", "Student Gender"),
            F("Student", "ADAGrade", "Student Grade", Fmt("map", GRADE_NWEA)), T("Student Ethnic Group Name"),
            T("Student User Name"), T("Student Email")]
    roster = query("NWEA MAP Growth - roster", tables, links, cols, ROS_C, distinct=True,
                   sort=["School Name", "Instructor Last Name", "Class Name", "Student Last Name"])
    return {
        "id": "nwea", "name": "NWEA MAP Growth (roster file)",
        "works_with": "NWEA MAP Growth / MAP Reading Fluency",
        "description": "One combined roster file (one row per student per class). NWEA updates its template from time to "
                       "time - compare the headers with the template in MAP Admin > Import Profiles before your first import. "
                       "To limit it to tested subjects, add a filter on Course Code or Course Name in Step 4.",
        "spec_url": "https://teach.mapnwea.org/impl/maphelp/Content/MAPSetup/Roster/PrepareYourRoster.htm",
        "delivery": "MAP Growth > Manage Roster > Import Roster",
        "files": [f("NWEA_roster.csv", roster)],
    }


# ================================================================= contact / address building blocks
OT_STU, OT_CON, OT_EMP = "{{OWNER_TYPE_STUDENT}}", "{{OWNER_TYPE_CONTACT}}", "{{OWNER_TYPE_EMPLOYEE}}"


def contact_chain(sfx="", seq_cond=None, student_alias="Student"):
    """Student -> StudentContact -> ContactInfo -> primary phone + primary email (all LEFT links)."""
    sc, ci, pr, pn, em = (f"StudentContact{sfx}", f"Contact{sfx}", f"ContactPhoneLink{sfx}", f"ContactPhone{sfx}",
                          f"ContactEmail{sfx}")
    tables = [(sc, "StudentContact"), (ci, "ContactInfo"), (pr, "PhoneRelationship"), (pn, "PhoneNumber"),
              (em, "EmailAddress")]
    links = [
        (student_alias, "StudentID", sc, "StudentID", "LEFT",
         [seq_cond or Condition(sc, "PrimaryContact", "eq", "1")]),
        (sc, "ContactID", ci, "ContactID", "LEFT"),
        (ci, "ContactID", pr, "OwnerID", "LEFT",
         [Condition(pr, "OwnerType", "eq", OT_CON), Condition(pr, "PrimaryPhone", "eq", "1")]),
        (pr, "PhoneNumberID", pn, "PhoneNumberID", "LEFT"),
        (ci, "ContactID", em, "OwnerID", "LEFT",
         [Condition(em, "OwnerType", "eq", OT_CON), Condition(em, "PrimaryAddress", "eq", "1")]),
    ]
    return tables, links, (sc, ci, pn, em)


def phone_col(heading, pn):
    return C(heading, P(pn, "AreaCode", Fmt("trim")),
             P(pn, "PhoneNumber", Fmt("replace", "-", ""), Fmt("remove_spaces"), Fmt("replace", "(", ""),
               Fmt("replace", ")", "")))


def address_chain(owner_alias, owner_id_col, owner_type, sfx=""):
    ar, ad = f"AddressLink{sfx}", f"Address{sfx}"
    return ([(ar, "AddressRelationship"), (ad, "Address")],
            [(owner_alias, owner_id_col, ar, "OwnerID", "LEFT",
              [Condition(ar, "OwnerType", "eq", owner_type), Condition(ar, "PrimaryAddress", "eq", "1")]),
             (ar, "AddressID", ad, "AddressID", "LEFT")], ad)


STU_SCH_T = STU_T + ["SchoolDef"]
STU_SCH_L = STU_L + [("stuSchool", "SchoolID", "SchoolDef", "SchoolID", "INNER")]
HR_T = [("stuHRTeacher", "stuHRTeacher"), ("HomeroomTeacher", "Employee")]
HR_L = [("Student", "StudentID", "stuHRTeacher", "StudentID", "LEFT",
         [Condition("stuHRTeacher", "ScheduleID", "raw",
                    "stuHRTeacher.ScheduleID IN (SELECT ScheduleID FROM Schedule WHERE LiveFlag = 1)")]),
        ("stuHRTeacher", "HRTeacherID", "HomeroomTeacher", "EmployeeID", "LEFT")]
CONTACT_REQ = ["OWNER_TYPE_CONTACT"]
CONTACT_NOTE = ("Phones and emails come from each contact's PRIMARY phone and PRIMARY email in SAM, so set "
                "the Owner type codes in District Settings first.")


# ================================================================= ParentSquare
def parentsquare():
    schools = query("ParentSquare - schools.csv", ["SchoolDef", ("Principal", "Employee")],
                    [("SchoolDef", "SchoolPrincipalID", "Principal", "EmployeeID", "LEFT")],
                    [F("SchoolDef", "SchoolID", "school_id"), F("SchoolDef", "SchoolName", "school_name", Fmt("trim")),
                     T("school_zip"), F("Principal", "FirstName", "principal_first_name", Fmt("trim")),
                     F("Principal", "LastName", "principal_last_name", Fmt("trim")),
                     C("principal_email", EMAIL("Principal", "staff")), T("school_address"), T("school_phone")],
                    [Condition("SchoolDef", "ActiveFlag", "eq", "1")])
    students = query("ParentSquare - students.csv", STU_T, STU_L,
                     [F("stuSchool", "SchoolID", "school_id"), F("Student", "StudentCode", "student_id", Fmt("trim")),
                      F("Student", "FirstName", "first_name", Fmt("trim")), F("Student", "LastName", "last_name", Fmt("trim")),
                      F("Student", "ADAGrade", "grade_level"), C("student_email", EMAIL("Student", "student")),
                      T("cellphone"), F("Student", "StateCode", "state_student_id")],
                     STU_C, sort=["last_name", "first_name"])
    ct, cl, (sc, ci, pn, em) = contact_chain(seq_cond=Condition("StudentContact", "NoContact", "ne", "1"))
    at, al, ad = address_chain("Contact", "ContactID", OT_CON)
    parents = query("ParentSquare - parents.csv", STU_T + ct + at, STU_L + cl + al,
                    [F("stuSchool", "SchoolID", "school_id"), F("Student", "StudentCode", "student_id", Fmt("trim")),
                     F(ci, "FirstName", "first_name", Fmt("trim")), F(ci, "LastName", "last_name", Fmt("trim")),
                     F(em, "Address", "email", Fmt("trim"), Fmt("lower")), T("email2"), phone_col("mobile", pn),
                     T("secondary_phone"),
                     C("address", P(ad, "AddrLine1", Fmt("trim")), X(", "), P(ad, "City", Fmt("trim")), X(", "),
                       P(ad, "State"), X(" "), P(ad, "ZipCode")),
                     T("iep"), F(ci, "PrimaryLanguage", "language"), F(sc, "RelationshipCode", "relationship"),
                     F(ci, "ContactID", "parent_id")],
                    STU_C + [Condition(ci, "ContactID", "not_blank")], distinct=True,
                    sort=["student_id", "last_name"])
    staff = query("ParentSquare - staff.csv", EMP_T, EMP_L,
                  [F("empSchool", "SchoolID", "school_id"), F("Employee", "EmployeeID", "staff_id"), T("title"),
                   F("Employee", "FirstName", "first_name", Fmt("trim")), F("Employee", "LastName", "last_name", Fmt("trim")),
                   C("email", EMAIL("Employee", "staff")), T("mobile")],
                  [Condition("empSchool", "PrimarySchoolFlag", "eq", "1"), Condition("Employee", "TerminationDate", "blank")],
                  distinct=True)
    sections = query("ParentSquare - sections.csv", SEC_T, SEC_L,
                     [F("Schedule", "SchoolID", "school_id"), F("ScheduleFramework", "ScheduleFrameworkID", "section_id"),
                      F("ScheduleFramework", "TeacherID", "staff_id"), F("Course", "LongName", "course_name", Fmt("trim")),
                      F("Schedule", "ScheduleID", "term_id"), T("is_primary", "true"),
                      F("ScheduleFramework", "Period", "period_number"),
                      F("ScheduleFramework", "SectionNumber", "section_number")],
                     [LIVE, Condition("ScheduleFramework", "TeacherID", "not_blank")])
    roster = query("ParentSquare - roster.csv", ROS_T, ROS_L,
                   [F("Schedule", "SchoolID", "school_id"), F("ScheduleRoster", "ScheduleFrameworkID", "section_id"),
                    F("Student", "StudentCode", "student_id", Fmt("trim"))], ROS_C, distinct=True)
    return {
        "id": "parentsquare", "name": "ParentSquare",
        "works_with": "ParentSquare / StudentSquare messaging, alerts and attendance notices",
        "description": "The SIS-style CSV set ParentSquare receives by SFTP (schools, students, parents, staff, sections, "
                       "roster). ParentSquare's onboarding team confirms the exact layout for each district - send them "
                       "a sample before going live. " + CONTACT_NOTE,
        "spec_url": "https://support-sis.genesisedu.com/support/solutions/articles/151000094099-parent-square-export",
        "delivery": "SFTP to the folder ParentSquare provides (usually nightly)",
        "requires": CONTACT_REQ,
        "files": [f("schools.csv", schools), f("students.csv", students), f("parents.csv", parents),
                  f("staff.csv", staff), f("sections.csv", sections), f("roster.csv", roster)],
    }


# ================================================================= SchoolMessenger
def schoolmessenger():
    t1, l1, (_, c1, p1, e1) = contact_chain("1", Condition("StudentContact1", "Sequence", "eq", "1"))
    t2, l2, (_, c2, p2, e2) = contact_chain("2", Condition("StudentContact2", "Sequence", "eq", "2"))
    contacts = query("SchoolMessenger - contacts.csv", STU_SCH_T + t1 + t2, STU_SCH_L + l1 + l2,
                     [F("Student", "StudentCode", "ID", Fmt("trim")), F("Student", "FirstName", "First Name", Fmt("trim")),
                      F("Student", "LastName", "Last Name", Fmt("trim")), F("SchoolDef", "SchoolName", "School", Fmt("trim")),
                      F("Student", "ADAGrade", "Grade"), F(c1, "PrimaryLanguage", "Language"),
                      C("Guardian 1", P(c1, "FirstName", Fmt("trim")), X(" "), P(c1, "LastName", Fmt("trim"))),
                      phone_col("Phone 1", p1), F(e1, "Address", "Email 1", Fmt("trim"), Fmt("lower")),
                      C("Guardian 2", P(c2, "FirstName", Fmt("trim")), X(" "), P(c2, "LastName", Fmt("trim"))),
                      phone_col("Phone 2", p2), F(e2, "Address", "Email 2", Fmt("trim"), Fmt("lower"))],
                     STU_C, distinct=True, sort=["Last Name", "First Name"])
    staff = query("SchoolMessenger - staff.csv", EMP_T + ["SchoolDef", ("StaffPhoneLink", "PhoneRelationship"),
                                                          ("StaffPhone", "PhoneNumber")],
                  EMP_L + [("empSchool", "SchoolID", "SchoolDef", "SchoolID", "INNER"),
                           ("Employee", "EmployeeID", "StaffPhoneLink", "OwnerID", "LEFT",
                            [Condition("StaffPhoneLink", "OwnerType", "eq", OT_EMP),
                             Condition("StaffPhoneLink", "PrimaryPhone", "eq", "1")]),
                           ("StaffPhoneLink", "PhoneNumberID", "StaffPhone", "PhoneNumberID", "LEFT")],
                  [C("ID", X("T"), P("Employee", "EmployeeID")), F("Employee", "FirstName", "First Name", Fmt("trim")),
                   F("Employee", "LastName", "Last Name", Fmt("trim")), F("SchoolDef", "SchoolName", "School", Fmt("trim")),
                   phone_col("Phone 1", "StaffPhone"), C("Email 1", EMAIL("Employee", "staff"))],
                  [Condition("empSchool", "PrimarySchoolFlag", "eq", "1"), Condition("Employee", "TerminationDate", "blank")],
                  distinct=True, sort=["Last Name", "First Name"])
    return {
        "id": "schoolmessenger", "name": "SchoolMessenger (contact data)",
        "works_with": "SchoolMessenger broadcasts (also usable for Remind, Blackboard/Finalsite Mass Notification and "
                      "other tools that map CSV columns at upload)",
        "description": "One row per student with the first two guardians' names, primary phones (10 digits) and primary "
                       "emails, plus a staff file. SchoolMessenger lets you map these columns at upload (ID must be "
                       "first). " + CONTACT_NOTE,
        "spec_url": "https://static.schoolmessenger.com/help/SchoolMessenger/html/Lists/Upload_a_List.htm",
        "delivery": "SchoolMessenger > Lists > Upload List, or the scheduled Data Import (SFTP)",
        "requires": CONTACT_REQ + ["OWNER_TYPE_EMPLOYEE"],
        "files": [f("contacts.csv", contacts), f("staff.csv", staff)],
    }


# ================================================================= Follett Destiny
def destiny():
    at, al, ad = address_chain("Student", "StudentID", OT_STU)
    students = query("Destiny - student patrons.csv", STU_SCH_T + HR_T + at, STU_SCH_L + HR_L + al,
                     [F("SchoolDef", "ShortName", "Site Short Name", Fmt("trim")),
                      F("Student", "StudentCode", "Barcode", Fmt("trim")), F("Student", "StudentCode", "District ID", Fmt("trim")),
                      F("Student", "LastName", "Last Name", Fmt("trim")), F("Student", "FirstName", "First Name", Fmt("trim")),
                      F("Student", "MiddleName", "Middle Name", Fmt("trim")), T("Patron Type", "Student"),
                      T("Status", "A"), F("Student", "GenderCode", "Gender"),
                      F("Student", "DOB", "Birth Date", Fmt("date_us")),
                      F("Student", "OriginalGradDate", "Graduation Year", Fmt("year")),
                      F("Student", "ADAGrade", "Grade Level"),
                      F("HomeroomTeacher", "LastName", "Homeroom", Fmt("trim")),
                      C("User Name", USER("Student", "student")), C("Email 1", EMAIL("Student", "student")),
                      T("Is Teacher", "F"), F(ad, "AddrLine1", "Address 1 Line 1", Fmt("trim")),
                      F(ad, "City", "Address 1 City", Fmt("trim")), F(ad, "State", "Address 1 State"),
                      F(ad, "ZipCode", "Address 1 Postal Code")],
                     STU_C, distinct=True, sort=["Site Short Name", "Last Name", "First Name"])
    staff = query("Destiny - staff patrons.csv", EMP_T + ["SchoolDef"],
                  EMP_L + [("empSchool", "SchoolID", "SchoolDef", "SchoolID", "INNER")],
                  [F("SchoolDef", "ShortName", "Site Short Name", Fmt("trim")),
                   F("Employee", "EmployeeNumber", "Barcode", Fmt("trim")),
                   C("District ID", X("T"), P("Employee", "EmployeeID")),
                   F("Employee", "LastName", "Last Name", Fmt("trim")), F("Employee", "FirstName", "First Name", Fmt("trim")),
                   T("Patron Type", "Staff"), T("Status", "A"),
                   C("User Name", USER("Employee", "staff")), C("Email 1", EMAIL("Employee", "staff")),
                   F("Employee", "FacultyFlag", "Is Teacher", Fmt("map", "1=T; 0=F"))],
                  [Condition("empSchool", "PrimarySchoolFlag", "eq", "1"), Condition("Employee", "TerminationDate", "blank")],
                  distinct=True, sort=["Site Short Name", "Last Name"])
    return {
        "id": "destiny", "name": "Follett Destiny (library patrons)",
        "works_with": "Follett Destiny Library / Resource Manager via the Patron Import Converter",
        "description": "Student and staff patron files with Site Short Name, Barcode, District ID and Last Name (the "
                       "required Destiny fields). Site Short Name comes from SchoolDef.ShortName - it must match the "
                       "site short names in Destiny (or use the converter's mapping). Student addresses use the "
                       "Student owner type code.",
        "spec_url": "https://legacyhelp.follettsoftware.com/content/r_PIC_Available_Destiny_fields.htm",
        "delivery": "Patron Import Converter, then Destiny > Back Office > Update Patrons",
        "requires": ["OWNER_TYPE_STUDENT"],
        "files": [f("destiny_students.csv", students), f("destiny_staff.csv", staff)],
    }


# ================================================================= Food service
def foodservice():
    ct, cl, (sc, ci, pn, em) = contact_chain()
    at, al, ad = address_chain("Student", "StudentID", OT_STU)
    students = query("Food service - students.csv", STU_SCH_T + HR_T + ct + at, STU_SCH_L + HR_L + cl + al,
                     [F("Student", "StudentCode", "Student ID", Fmt("trim")), F("Student", "StateCode", "State ID"),
                      F("Student", "LastName", "Last Name", Fmt("trim")), F("Student", "FirstName", "First Name", Fmt("trim")),
                      F("Student", "MiddleName", "Middle Name", Fmt("trim")), F("SchoolDef", "SchoolCode", "School Code"),
                      F("SchoolDef", "SchoolName", "School Name", Fmt("trim")), F("Student", "ADAGrade", "Grade"),
                      F("HomeroomTeacher", "LastName", "Homeroom", Fmt("trim")),
                      F("Student", "DOB", "Birth Date", Fmt("date_us")), F("Student", "GenderCode", "Gender"),
                      F("Student", "LunchNumber", "PIN", Fmt("trim")),
                      F("Student", "FoodServiceCode", "Eligibility Code"),
                      F("Student", "EnrollmentStatus", "Enrollment Status"),
                      C("Guardian Name", P(ci, "FirstName", Fmt("trim")), X(" "), P(ci, "LastName", Fmt("trim"))),
                      F(em, "Address", "Guardian Email", Fmt("trim"), Fmt("lower")), phone_col("Guardian Phone", pn),
                      F(ad, "AddrLine1", "Address", Fmt("trim")), F(ad, "City", "City", Fmt("trim")),
                      F(ad, "State", "State"), F(ad, "ZipCode", "Zip")],
                     STU_C, distinct=True, sort=["School Name", "Last Name", "First Name"])
    staff = query("Food service - staff.csv", EMP_T + ["SchoolDef"],
                  EMP_L + [("empSchool", "SchoolID", "SchoolDef", "SchoolID", "INNER")],
                  [F("Employee", "EmployeeNumber", "Employee ID", Fmt("trim")),
                   F("Employee", "LastName", "Last Name", Fmt("trim")), F("Employee", "FirstName", "First Name", Fmt("trim")),
                   F("SchoolDef", "SchoolCode", "School Code"), F("SchoolDef", "SchoolName", "School Name", Fmt("trim")),
                   C("Email", EMAIL("Employee", "staff"))],
                  [Condition("empSchool", "PrimarySchoolFlag", "eq", "1"), Condition("Employee", "TerminationDate", "blank")],
                  distinct=True, sort=["School Name", "Last Name"])
    return {
        "id": "foodservice", "name": "Food service / point of sale",
        "works_with": "LINQ Nutrition (TITAN), PrimeroEdge, Heartland Mosaic/MCS, Nutrikids, SchoolCafe and other POS "
                      "systems that import a student roster CSV",
        "description": "Student roster with PIN (Student.LunchNumber), eligibility code (Student.FoodServiceCode), "
                       "homeroom, primary guardian and home address, plus a staff file. Column names are generic - "
                       "rename them in Step 3 if your vendor needs specific headers, and use 'Translate values' to "
                       "convert eligibility codes (e.g. F/R/P). This is the classic CAC Agent 'Foodservice' job. "
                       + CONTACT_NOTE,
        "spec_url": "",
        "delivery": "CAC Agent job to a folder the food-service import reads (or the vendor's SFTP)",
        "requires": CONTACT_REQ + ["OWNER_TYPE_STUDENT"],
        "files": [f("foodservice_students.csv", students), f("foodservice_staff.csv", staff)],
    }


# ================================================================= Transportation
def transportation():
    ct, cl, (sc, ci, pn, em) = contact_chain()
    at, al, ad = address_chain("Student", "StudentID", OT_STU)
    students = query("Transportation - students.csv", STU_SCH_T + ct + at, STU_SCH_L + cl + al,
                     [F("Student", "StudentCode", "Student ID", Fmt("trim")),
                      F("Student", "LastName", "Last Name", Fmt("trim")), F("Student", "FirstName", "First Name", Fmt("trim")),
                      F("Student", "MiddleName", "Middle Name", Fmt("trim")), F("Student", "ADAGrade", "Grade"),
                      F("SchoolDef", "SchoolCode", "School Code"), F("SchoolDef", "SchoolName", "School Name", Fmt("trim")),
                      F("Student", "DOB", "Birth Date", Fmt("date_us")), F("Student", "GenderCode", "Gender"),
                      F(ad, "AddrLine1", "Address 1", Fmt("trim")), F(ad, "AddrLine2", "Address 2", Fmt("trim")),
                      F(ad, "City", "City", Fmt("trim")), F(ad, "State", "State"), F(ad, "ZipCode", "Zip"),
                      F(ad, "Latitude", "Latitude"), F(ad, "Longitude", "Longitude"),
                      F("Student", "TransportationCode", "Transportation Code"),
                      F("Student", "AMTransMethod", "AM Method"), F("Student", "PMTransMethod", "PM Method"),
                      F("Student", "BusZone", "Bus Zone"), F("Student", "RouteMiles", "Route Miles"),
                      F("Student", "SPEDStatus", "Special Ed"), F("Student", "Flag504", "504", Fmt("yes_no")),
                      C("Guardian Name", P(ci, "FirstName", Fmt("trim")), X(" "), P(ci, "LastName", Fmt("trim"))),
                      phone_col("Guardian Phone", pn), F(em, "Address", "Guardian Email", Fmt("trim"), Fmt("lower"))],
                     STU_C, distinct=True, sort=["School Name", "Last Name", "First Name"])
    return {
        "id": "transportation", "name": "Transportation / routing",
        "works_with": "Transfinder Routefinder PLUS, Edulog, Tyler Versatrans, BusPlanner and other routing systems",
        "description": "One row per student with home address (and latitude/longitude when SAM has them), "
                       "transportation code, AM/PM method, bus zone, route miles, special-needs flags and the primary "
                       "guardian. Routing systems map columns at import - rename headers in Step 3 if needed. "
                       + CONTACT_NOTE,
        "spec_url": "",
        "delivery": "CAC Agent job to the routing system's import folder (or its SFTP)",
        "requires": CONTACT_REQ + ["OWNER_TYPE_STUDENT"],
        "files": [f("transportation_students.csv", students)],
    }


# ================================================================= helper: find codes
def codes():
    def lk(table, title):
        return query(title, [table], [], [F(table, "Val", "Code"), F(table, "Description", "Description")],
                     sort=["Code"])

    owner = query("Owner type codes", ["OwnerType"], [],
                  [F("OwnerType", "Val", "Code"), F("OwnerType", "Description", "Description"),
                   F("OwnerType", "TableName", "Table")], sort=["Code"])
    return {
        "id": "codes", "name": "Find your SAM codes (helper queries)",
        "works_with": "Use before your first export",
        "description": "Run these in SAM and save each result as a CSV with the file name shown. Then use File > SAM "
                       "Codes & Schools > Import to load them: filters get drop-downs of your real codes, your schools "
                       "become one-click filters, and District Settings fills in owner types and the enrolled code.",
        "spec_url": "",
        "delivery": "Run in SAM's Ad Hoc Query > Run Query",
        "files": [f("enrollment_status_codes.csv", lk("lookupEnrollmentStatus", "Enrollment status codes")),
                  f("grade_codes.csv", lk("lookupADAGrade", "Grade level codes")),
                  f("gender_codes.csv", lk("lookupGenderCode", "Gender codes")),
                  f("race_codes.csv", lk("lookupRaceCode", "Race codes")),
                  f("roster_status_codes.csv", lk("LookupRosterStatus", "Schedule roster status codes")),
                  f("owner_type_codes.csv", owner),
                  f("school_list.csv", query("School list (SchoolID and names)", ["SchoolDef"], [],
                                             [F("SchoolDef", "SchoolID", "SchoolID"),
                                              F("SchoolDef", "SchoolName", "School Name", Fmt("trim")),
                                              F("SchoolDef", "SchoolCode", "School Code"),
                                              F("SchoolDef", "ShortName", "Short Name", Fmt("trim"))],
                                             sort=["School Name"])),
                  f("attendance_codes.csv", query("Attendance codes", ["AttendanceCodes"], [],
                                                  [F("AttendanceCodes", "AttendanceCode", "Code"),
                                                   F("AttendanceCodes", "AttendanceDescription", "Description")],
                                                  distinct=True, sort=["Code"])),
                  f("phone_type_codes.csv", lk("lookupPhoneType", "Phone type codes")),
                  f("relationship_codes.csv", lk("lookupRelationshipType", "Contact relationship codes")),
                  f("registration_codes.csv", query("Registration codes (entry / withdrawal)", ["RegistrationCodes"], [],
                                                    [F("RegistrationCodes", "Code", "Code"),
                                                     F("RegistrationCodes", "Description", "Description"),
                                                     F("RegistrationCodes", "InOutDirection", "In / Out"),
                                                     F("RegistrationCodes", "Active", "Active")],
                                                    sort=["Code"]))],
    }



# ================================================================= validation rules (export file checker)
CLEVER_GRADES = "enum:" + "|".join(["InfantToddler", "Preschool", "PreKindergarten", "TransitionalKindergarten",
                                    "Kindergarten", "PostGraduate", "Ungraded", "Other"] + [str(i) for i in range(1, 14)])
OR_BULK = {"status": "blank", "dateLastModified": "blank"}


def R(required=(), unique=(), formats=None):
    return {"required": list(required), "unique": [list(u) if isinstance(u, (list, tuple)) else [u] for u in unique],
            "formats": formats or {}}


RULES = {
    "clever": {"files": {
        "schools.csv": R(["School_id", "School_name", "School_number"], ["School_id"],
                         {"Principal_email": "email", "Low_grade": CLEVER_GRADES, "High_grade": CLEVER_GRADES}),
        "students.csv": R(["School_id", "Student_id", "Last_name", "First_name"], ["Student_id"],
                          {"DOB": "date_us", "Gender": "enum:M|F|X", "Grade": CLEVER_GRADES, "Student_email": "email"}),
        "teachers.csv": R(["School_id", "Teacher_id", "First_name", "Last_name"], ["Teacher_id"],
                          {"Teacher_email": "email"}),
        "sections.csv": R(["School_id", "Section_id", "Teacher_id"], ["Section_id"],
                          {"Term_start": "date_us", "Term_end": "date_us"}),
        "enrollments.csv": R(["School_id", "Section_id", "Student_id"], [("Section_id", "Student_id")])},
        "refs": [["students.csv", "School_id", "schools.csv", "School_id"],
                 ["teachers.csv", "School_id", "schools.csv", "School_id"],
                 ["sections.csv", "School_id", "schools.csv", "School_id"],
                 ["sections.csv", "Teacher_id", "teachers.csv", "Teacher_id"],
                 ["enrollments.csv", "Section_id", "sections.csv", "Section_id"],
                 ["enrollments.csv", "Student_id", "students.csv", "Student_id"]]},
    "oneroster11": {"files": {
        "orgs.csv": R(["sourcedId", "name", "type"], ["sourcedId"],
                      {**OR_BULK, "type": "enum:department|school|district|local|state|national"}),
        "academicSessions.csv": R(["sourcedId", "title", "type", "startDate", "endDate", "schoolYear"], ["sourcedId"],
                                  {**OR_BULK, "type": "enum:gradingPeriod|semester|schoolYear|term",
                                   "startDate": "date_iso", "endDate": "date_iso", "schoolYear": "year"}),
        "courses.csv": R(["sourcedId", "title", "orgSourcedId"], ["sourcedId"], OR_BULK),
        "classes.csv": R(["sourcedId", "title", "courseSourcedId", "classType", "schoolSourcedId", "termSourcedIds"],
                         ["sourcedId"], {**OR_BULK, "classType": "enum:homeroom|scheduled"}),
        "users.csv": R(["sourcedId", "enabledUser", "orgSourcedIds", "role", "username", "givenName", "familyName"],
                       ["sourcedId"], {**OR_BULK, "enabledUser": "bool", "email": "email",
                                       "role": "enum:administrator|aide|guardian|parent|proctor|relative|student|teacher"}),
        "enrollments.csv": R(["sourcedId", "classSourcedId", "schoolSourcedId", "userSourcedId", "role"], ["sourcedId"],
                             {**OR_BULK, "role": "enum:administrator|proctor|student|teacher", "primary": "bool",
                              "beginDate": "date_iso", "endDate": "date_iso"}),
        "demographics.csv": R(["sourcedId"], ["sourcedId"], {**OR_BULK, "birthDate": "date_iso",
                                                            "sex": "enum:male|female|other|unspecified"})},
        "refs": [["users.csv", "orgSourcedIds", "orgs.csv", "sourcedId"],
                 ["courses.csv", "orgSourcedId", "orgs.csv", "sourcedId"],
                 ["classes.csv", "courseSourcedId", "courses.csv", "sourcedId"],
                 ["classes.csv", "schoolSourcedId", "orgs.csv", "sourcedId"],
                 ["classes.csv", "termSourcedIds", "academicSessions.csv", "sourcedId"],
                 ["enrollments.csv", "classSourcedId", "classes.csv", "sourcedId"],
                 ["enrollments.csv", "userSourcedId", "users.csv", "sourcedId"],
                 ["enrollments.csv", "schoolSourcedId", "orgs.csv", "sourcedId"],
                 ["demographics.csv", "sourcedId", "users.csv", "sourcedId"]]},
    "sds21": {"files": {
        "orgs.csv": R(["sourcedId", "name", "type"], ["sourcedId"]),
        "users.csv": R(["sourcedId", "username"], ["sourcedId", "username"], {"email": "email", "username": "email"}),
        "roles.csv": R(["userSourcedId", "orgSourcedId", "role"], [("userSourcedId", "orgSourcedId", "role")],
                       {"isPrimary": "bool"}),
        "academicSessions.csv": R(["sourcedId", "title", "type", "schoolYear", "startDate", "endDate"], ["sourcedId"],
                                  {"startDate": "date_iso", "endDate": "date_iso", "schoolYear": "year"}),
        "courses.csv": R(["sourcedId", "orgSourcedId", "title"], ["sourcedId"]),
        "classes.csv": R(["sourcedId", "orgSourcedId", "title"], ["sourcedId"]),
        "enrollments.csv": R(["classSourcedId", "userSourcedId", "role"], [("classSourcedId", "userSourcedId")])},
        "refs": [["roles.csv", "userSourcedId", "users.csv", "sourcedId"],
                 ["roles.csv", "orgSourcedId", "orgs.csv", "sourcedId"],
                 ["classes.csv", "orgSourcedId", "orgs.csv", "sourcedId"],
                 ["classes.csv", "sessionSourcedIds", "academicSessions.csv", "sourcedId"],
                 ["classes.csv", "courseSourcedId", "courses.csv", "sourcedId"],
                 ["enrollments.csv", "classSourcedId", "classes.csv", "sourcedId"],
                 ["enrollments.csv", "userSourcedId", "users.csv", "sourcedId"]]},
    "google": {"files": {
        f: R(["First Name [Required]", "Last Name [Required]", "Email Address [Required]", "Password [Required]",
              "Org Unit Path [Required]"], ["Email Address [Required]"], {"Email Address [Required]": "email"})
        for f in ("google_students.csv", "google_staff.csv")}},
    "canvas": {"files": {
        "users.csv": R(["user_id", "login_id", "status"], ["user_id", "login_id"],
                       {"status": "enum:active|suspended|deleted", "email": "email"}),
        "terms.csv": R(["term_id", "name", "status"], ["term_id"], {"status": "enum:active|deleted"}),
        "courses.csv": R(["course_id", "short_name", "long_name", "status"], ["course_id"],
                         {"status": "enum:active|deleted|completed|published"}),
        "enrollments.csv": R(["course_id", "user_id", "role", "status"], [("course_id", "user_id", "role")],
                             {"role": "enum:student|teacher|ta|observer|designer",
                              "status": "enum:active|deleted|completed|inactive"})},
        "refs": [["courses.csv", "term_id", "terms.csv", "term_id"],
                 ["enrollments.csv", "course_id", "courses.csv", "course_id"],
                 ["enrollments.csv", "user_id", "users.csv", "user_id"]]},
    "nwea": {"files": {"NWEA_roster.csv": R(
        ["School Name", "Instructor ID", "Instructor Last Name", "Instructor First Name", "Class Name", "Student ID",
         "Student Last Name", "Student First Name", "Student Date Of Birth", "Student Gender", "Student Grade"],
        [("Class Name", "Student ID")],
        {"Student Date Of Birth": "date_us", "Student Gender": "enum:M|F", "Email Address": "email"})}},
    "parentsquare": {"files": {
        "schools.csv": R(["school_id", "school_name"], ["school_id"]),
        "students.csv": R(["school_id", "student_id", "first_name", "last_name"], ["student_id"],
                          {"student_email": "email"}),
        "parents.csv": R(["school_id", "student_id", "first_name", "last_name"], [], {"email": "email",
                                                                                      "mobile": "phone10"}),
        "staff.csv": R(["school_id", "staff_id", "first_name", "last_name"], ["staff_id"], {"email": "email"}),
        "sections.csv": R(["school_id", "section_id", "staff_id"], ["section_id"]),
        "roster.csv": R(["school_id", "section_id", "student_id"], [("section_id", "student_id")])},
        "refs": [["parents.csv", "student_id", "students.csv", "student_id"],
                 ["sections.csv", "staff_id", "staff.csv", "staff_id"],
                 ["roster.csv", "section_id", "sections.csv", "section_id"],
                 ["roster.csv", "student_id", "students.csv", "student_id"],
                 ["students.csv", "school_id", "schools.csv", "school_id"]]},
    "schoolmessenger": {"files": {
        "contacts.csv": R(["ID", "First Name", "Last Name"], ["ID"],
                          {"Phone 1": "phone10", "Phone 2": "phone10", "Email 1": "email", "Email 2": "email"}),
        "staff.csv": R(["ID", "First Name", "Last Name"], ["ID"], {"Phone 1": "phone10", "Email 1": "email"})}},
    "destiny": {"files": {
        f: R(["Site Short Name", "Barcode", "District ID", "Last Name"], ["District ID", ("Site Short Name", "Barcode")],
             {"Site Short Name": "maxlen:10", "Barcode": "maxlen:14", "Last Name": "maxlen:42",
              "First Name": "maxlen:42", "Gender": "enum:M|F|U", "Status": "enum:A|I|R", "Is Teacher": "tf",
              "Birth Date": "date_us", "Graduation Year": "year", "Email 1": "email"})
        for f in ("destiny_students.csv", "destiny_staff.csv")}},
    "foodservice": {"files": {
        "foodservice_students.csv": R(["Student ID", "Last Name", "First Name"], ["Student ID"],
                                      {"Birth Date": "date_us", "Guardian Email": "email", "Guardian Phone": "phone10"}),
        "foodservice_staff.csv": R(["Employee ID", "Last Name", "First Name"], ["Employee ID"], {"Email": "email"})}},
    "transportation": {"files": {
        "transportation_students.csv": R(["Student ID", "Last Name", "First Name", "Address 1", "Zip"], ["Student ID"],
                                         {"Birth Date": "date_us", "Guardian Phone": "phone10"})}},
}


DELIVERY = {
    "clever": {"host": "sftp.clever.com", "zip": False},
    "oneroster11": {"zip": True, "zip_name": "oneroster.zip"},
    "sds21": {"zip": False},
    "canvas": {"zip": True, "zip_name": "canvas_sis.zip"},
}


# more packages (Raptor, Incident IQ, PSPA photos, Xello, Naviance, SchooLinks, MTSS, Frontline, DragonFly, ACT)
exec(compile((ROOT / "tools" / "exports_more.py").read_text(encoding="utf-8"), "exports_more.py", "exec"))
RULES.update(MORE_RULES)  # noqa: F821
exec(compile((ROOT / "tools" / "exports_vendors.py").read_text(encoding="utf-8"), "exports_vendors.py", "exec"))
RULES.update(VENDOR_RULES)  # noqa: F821
DELIVERY.update(VENDOR_DELIVERY)  # noqa: F821
exec(compile((ROOT / "tools" / "exports_round4.py").read_text(encoding="utf-8"), "exports_round4.py", "exec"))
RULES.update(ROUND4_RULES)  # noqa: F821
exec(compile((ROOT / "tools" / "exports_round5.py").read_text(encoding="utf-8"), "exports_round5.py", "exec"))
exec(compile((ROOT / "tools" / "exports_round6.py").read_text(encoding="utf-8"), "exports_round6.py", "exec"))
RULES.update(ROUND6_RULES)  # noqa: F821
DELIVERY.update(ROUND6_DELIVERY)  # noqa: F821


CATEGORIES = {
    "Rostering & accounts": ["clever", "oneroster11", "sds21", "google", "apple_asm", "active_directory", "entra",
                             "canvas", "nwea", "credit_recovery", "adobe", "zoom"],
    "Family communication": ["parentsquare", "schoolmessenger", "schoolstatus", "filter_parents"],
    "School operations & safety": ["raptor", "emergency", "incidentiq", "destiny", "foodservice", "payments",
                                   "transportation", "bus_apps", "hall_pass", "pspa", "frontline"],
    "Student support & behavior": ["mtss", "pbis_rewards", "behavior", "ellevation"],
    "College, career & athletics": ["xello", "naviance", "schoolinks", "scoir", "dragonfly", "athletics"],
    "Assessment & testing": ["act_sdu"],
    "Tools": ["cleanup", "codes", "samcheck"],
}


def attach_rules(platforms):
    for pid, cat in list(ROUND4_CATEGORIES.items()) + list(ROUND6_CATEGORIES.items()):  # noqa: F821
        if pid not in CATEGORIES.setdefault(cat, []):
            CATEGORIES[cat].append(pid)
    for p in platforms:
        p["category"] = next((c for c, ids in CATEGORIES.items() if p["id"] in ids), "Other")
        if p["category"] == "Tools":
            p["kind"] = "tool"
        if p["id"] in RULES:
            p["rules"] = RULES[p["id"]]
        if p["id"] in DELIVERY:
            p["delivery_defaults"] = DELIVERY[p["id"]]
    return platforms


if __name__ == "__main__":
    out = ROOT / "data" / "exports.json"
    version = None
    try:
        version = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))["data_version"]
    except Exception:
        pass
    data = {"data_version": version or "2026.10.15.1",
            "platforms": attach_rules([clever(), oneroster(), sds(), google(), canvas(), nwea(), parentsquare(),
                          schoolmessenger(), destiny(), foodservice(), transportation()]
                                 + [fn() for fn in MORE_PLATFORMS] + [fn() for fn in VENDOR_PLATFORMS] + [fn() for fn in ROUND4_PLATFORMS]  # noqa: F821
                                 + [fn() for fn in ROUND6_PLATFORMS]  # noqa: F821
                                 + [codes(), samcheck()])}  # noqa: F821  # noqa: F821
    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
    n = sum(len(p["files"]) for p in data["platforms"])
    print(f"Wrote {out}: {len(data['platforms'])} platforms, {n} files")
