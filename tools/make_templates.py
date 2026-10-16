"""Generates the starter data/templates.json.  Re-running overwrites starter templates
but keeps any extra templates already in the file (matched by name)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sam_qb.query_model import (QueryDef, OutColumn, Fmt, Part, Link, FilterGroup,  # noqa: E402
                                Condition, SortItem)


def field(alias, col, heading, *fmts):
    return OutColumn("field", alias, col, heading, list(fmts))


def name_col(alias, heading, last="LastName", first="FirstName"):
    return OutColumn("custom", heading=heading, parts=[
        Part("field", alias, last), Part("text", value=", "), Part("field", alias, first)])


def q(name, cat, desc, tables, links, cols, filters=None, sort=None, distinct=False):
    qd = QueryDef(name=name, description=desc, category=cat, distinct=distinct)
    for t in tables:
        qd.add_table(t)
    qd.links = [Link(*l) for l in links]
    qd.columns = cols
    qd.filters = filters or []
    qd.sort = [SortItem(*s) if isinstance(s, tuple) else SortItem(s) for s in (sort or [])]
    return qd


SCHED_LINKS = [
    ("Student", "StudentID", "ScheduleRoster", "StudentID", "INNER"),
    ("ScheduleRoster", "ScheduleFrameworkID", "ScheduleFramework", "ScheduleFrameworkID", "INNER"),
    ("ScheduleFramework", "ScheduleCourseTermID", "ScheduleCourseTerm", "ScheduleCourseTermID", "INNER"),
    ("ScheduleCourseTerm", "ScheduleCourseID", "ScheduleCourse", "ScheduleCourseID", "INNER"),
    ("ScheduleCourse", "CourseID", "Course", "CourseID", "INNER"),
    ("ScheduleCourse", "ScheduleID", "Schedule", "ScheduleID", "INNER"),
]

LIVE = FilterGroup("ALL", [Condition("Schedule", "LiveFlag", "eq", "1")])

templates = [
    q("Homeroom Roster", "Students",
      "Students with their homeroom teacher, grade, state code and a generated email address "
      "(matches the Report Builder 'Homeroom Roster' example). Change the email domain in Step 3.",
      ["Student", "stuHRTeacher", "Employee"],
      [("Student", "StudentID", "stuHRTeacher", "StudentID", "INNER"),
       ("stuHRTeacher", "HRTeacherID", "Employee", "EmployeeID", "INNER")],
      [name_col("Employee", "Homeroom Teacher"),
       field("Student", "ADAGrade", "Grade"),
       name_col("Student", "Student"),
       field("Student", "StateCode", "State Code", Fmt("strip_zeros")),
       OutColumn("custom", heading="New Email", parts=[
           Part("field", "Student", "FirstName", formats=[Fmt("left", "1"), Fmt("lower")]),
           Part("field", "Student", "LastName", formats=[Fmt("lower"), Fmt("remove_spaces")]),
           Part("text", value="@yourdistrict.k12.ms.us")])],
      sort=["Homeroom Teacher", "Grade", "Student"]),

    q("Student Schedule", "Scheduling",
      "Each student's classes from the live schedule: period, course, section, teacher and room "
      "(matches the Report Builder 'Student Schedule' example: Student -> Schedule Roster -> Course/Section).",
      ["Student", "ScheduleRoster", "ScheduleFramework", "ScheduleCourseTerm", "ScheduleCourse", "Course",
       "Schedule", "Employee"],
      SCHED_LINKS + [("ScheduleFramework", "TeacherID", "Employee", "EmployeeID", "LEFT")],
      [field("Student", "ADAGrade", "Grade"),
       name_col("Student", "Student"),
       field("ScheduleFramework", "Period", "Period"),
       field("Course", "CourseCode", "Course Code"),
       field("Course", "LongName", "Course Name"),
       field("ScheduleFramework", "SectionNumber", "Section"),
       name_col("Employee", "Teacher"),
       field("ScheduleFramework", "Room", "Room")],
      filters=[LIVE], sort=["Grade", "Student", "Period"]),

    q("Teacher Class List", "Scheduling",
      "Every section in the live schedule with its teacher, school, period, course and room.",
      ["ScheduleFramework", "ScheduleCourseTerm", "ScheduleCourse", "Course", "Schedule", "SchoolDef", "Employee"],
      [("ScheduleFramework", "ScheduleCourseTermID", "ScheduleCourseTerm", "ScheduleCourseTermID", "INNER"),
       ("ScheduleCourseTerm", "ScheduleCourseID", "ScheduleCourse", "ScheduleCourseID", "INNER"),
       ("ScheduleCourse", "CourseID", "Course", "CourseID", "INNER"),
       ("ScheduleCourse", "ScheduleID", "Schedule", "ScheduleID", "INNER"),
       ("Schedule", "SchoolID", "SchoolDef", "SchoolID", "INNER"),
       ("ScheduleFramework", "TeacherID", "Employee", "EmployeeID", "LEFT")],
      [field("SchoolDef", "SchoolName", "School"),
       name_col("Employee", "Teacher"),
       field("ScheduleFramework", "Period", "Period"),
       field("Course", "CourseCode", "Course Code"),
       field("Course", "LongName", "Course Name"),
       field("ScheduleFramework", "SectionNumber", "Section"),
       field("ScheduleFramework", "Room", "Room")],
      filters=[LIVE], sort=["School", "Teacher", "Period"]),

    q("Students by School", "Students",
      "Basic student list with school, IDs, grade, birth date and gender. Add a filter on School or Enrollment Status in Step 4.",
      ["Student", "stuSchool", "SchoolDef"],
      [("Student", "StudentID", "stuSchool", "StudentID", "INNER"),
       ("stuSchool", "SchoolID", "SchoolDef", "SchoolID", "INNER")],
      [field("SchoolDef", "SchoolName", "School"),
       field("Student", "StudentCode", "Student ID"),
       field("Student", "StateCode", "State Code", Fmt("strip_zeros")),
       field("Student", "LastName", "Last Name"),
       field("Student", "FirstName", "First Name"),
       field("Student", "ADAGrade", "Grade"),
       field("Student", "DOB", "Birth Date", Fmt("date_us")),
       field("Student", "GenderCode", "Gender"),
       field("Student", "EnrollmentStatus", "Enrollment Status")],
      sort=["School", "Grade", "Last Name", "First Name"]),

    q("Student Contacts (Parents/Guardians)", "Students",
      "Each student's contacts in sequence order with relationship and primary/emergency flags.",
      ["Student", "StudentContact", "ContactInfo"],
      [("Student", "StudentID", "StudentContact", "StudentID", "INNER"),
       ("StudentContact", "ContactID", "ContactInfo", "ContactID", "INNER")],
      [field("Student", "StudentCode", "Student ID"),
       name_col("Student", "Student"),
       field("StudentContact", "Sequence", "Seq"),
       name_col("ContactInfo", "Contact"),
       field("StudentContact", "RelationshipCode", "Relationship"),
       field("StudentContact", "PrimaryContact", "Primary", Fmt("yes_no")),
       field("StudentContact", "EmergencyFlag", "Emergency", Fmt("yes_no")),
       field("StudentContact", "ResidesWith", "Resides With", Fmt("yes_no"))],
      sort=["Student", "Seq"]),

    q("Student Addresses", "Students",
      "Student mailing addresses. IMPORTANT: AddressRelationship holds addresses for students, contacts and "
      "employees; add a Step 4 filter on AddressRelationship.OwnerType for the student owner type used in your district.",
      ["Student", "AddressRelationship", "Address"],
      [("Student", "StudentID", "AddressRelationship", "OwnerID", "INNER"),
       ("AddressRelationship", "AddressID", "Address", "AddressID", "INNER")],
      [field("Student", "StudentCode", "Student ID"),
       name_col("Student", "Student"),
       field("AddressRelationship", "OwnerType", "Owner Type"),
       field("AddressRelationship", "PrimaryAddress", "Primary", Fmt("yes_no")),
       field("Address", "AddrLine1", "Address 1"),
       field("Address", "AddrLine2", "Address 2"),
       field("Address", "City", "City"),
       field("Address", "State", "State"),
       field("Address", "ZipCode", "ZIP")],
      sort=["Student"]),

    q("Daily Attendance - Last 30 Days", "Attendance",
      "Daily attendance records from the last 30 days with code descriptions.",
      ["AttendanceDaily", "Student", "AttendanceCodes"],
      [("AttendanceDaily", "StudentID", "Student", "StudentID", "INNER"),
       ("AttendanceDaily", "AttendanceCode", "AttendanceCodes", "AttendanceCode", "LEFT")],
      [field("AttendanceDaily", "AttendanceDate", "Date", Fmt("date_us")),
       field("Student", "StudentCode", "Student ID"),
       name_col("Student", "Student"),
       field("AttendanceDaily", "AttendanceCode", "Code"),
       field("AttendanceCodes", "AttendanceDescription", "Description")],
      filters=[FilterGroup("ALL", [Condition("AttendanceDaily", "AttendanceDate", "last_days", "30")])],
      sort=[("Date", True), "Student"]),

    q("Staff by School", "Employees",
      "Employees assigned to each school with employee number and hire date.",
      ["Employee", "empSchool", "SchoolDef"],
      [("Employee", "EmployeeID", "empSchool", "EmployeeID", "INNER"),
       ("empSchool", "SchoolID", "SchoolDef", "SchoolID", "INNER")],
      [field("SchoolDef", "SchoolName", "School"),
       field("Employee", "EmployeeNumber", "Employee #"),
       field("Employee", "LastName", "Last Name"),
       field("Employee", "FirstName", "First Name"),
       field("Employee", "FacultyFlag", "Faculty", Fmt("yes_no")),
       field("Employee", "HireDate", "Hire Date", Fmt("date_us"))],
      sort=["School", "Last Name", "First Name"]),

    q("Transcript Courses and Grades", "Grades",
      "Historical transcript: session, course, final grade and credits for each student.",
      ["Student", "historyStudentSessions", "historyStudentCourses", "historyStudentCourseGrades"],
      [("Student", "StudentID", "historyStudentSessions", "StudentID", "INNER"),
       ("historyStudentSessions", "HistSessionID", "historyStudentCourses", "HistSessionID", "INNER"),
       ("historyStudentCourses", "HistStuCourseID", "historyStudentCourseGrades", "histStuCourseID", "INNER")],
      [field("Student", "StudentCode", "Student ID"),
       name_col("Student", "Student"),
       field("historyStudentSessions", "Descr", "Session"),
       field("historyStudentSessions", "GradeLevel", "Grade Level"),
       field("historyStudentCourses", "CourseCode_Local", "Course Code"),
       field("historyStudentCourses", "LongName_Local", "Course Name"),
       field("historyStudentCourseGrades", "ReportingDescription", "Grading Period"),
       field("historyStudentCourseGrades", "GradeNumeric", "Grade"),
       field("historyStudentCourseGrades", "CreditHoursEarned", "Credits Earned")],
      filters=[FilterGroup("ALL", [Condition("historyStudentCourseGrades", "IsFinalGrade", "eq", "1")])],
      sort=["Student", "Session", "Course Code"]),
]

if __name__ == "__main__":
    out = ROOT / "data" / "templates.json"
    version = sys.argv[1] if len(sys.argv) > 1 else None
    existing = {}
    if out.exists():
        old = json.loads(out.read_text(encoding="utf-8"))
        existing = {t["name"]: t for t in old.get("templates", [])}
        version = version or old.get("data_version")
    starter = [t.to_dict() for t in templates]
    names = {t["name"] for t in starter}
    extra = [t for n, t in existing.items() if n not in names]
    data = {"data_version": version or "2026.10.15.1", "templates": starter + extra}
    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"Wrote {out} with {len(data['templates'])} templates")
