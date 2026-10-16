# Additional platform packages - executed inside tools/make_exports.py (shares its helpers).
# Kept in its own file so the original package list stays readable.

GRADE_XELLO = ("PK=-1; KG=0; K=0; 01=1; 02=2; 03=3; 04=4; 05=5; 06=6; 07=7; 08=8; 09=9")
GRADE_NUM = "KG=K; 01=1; 02=2; 03=3; 04=4; 05=5; 06=6; 07=7; 08=8; 09=9"
SEC_GRADES = "06,07,08,09,10,11,12"
HS_GRADES = "09,10,11,12"
LIVE_HR = "stuHRTeacher.ScheduleID IN (SELECT ScheduleID FROM Schedule WHERE LiveFlag = 1)"
THIS_YEAR = "(SELECT MIN(BeginDate) FROM Schedule WHERE LiveFlag = 1)"
CONFIRM = ("This vendor does not publish a fixed file layout - columns are mapped when the file is uploaded. "
           "Send the vendor a sample before going live and rename headings in Step 3 if they ask.")

HR_LIVE_T = [("stuHRTeacher", "stuHRTeacher"), ("HomeroomTeacher", "Employee")]
HR_LIVE_L = [("Student", "StudentID", "stuHRTeacher", "StudentID", "LEFT",
              [Condition("stuHRTeacher", "ScheduleID", "raw", LIVE_HR)]),
             ("stuHRTeacher", "HRTeacherID", "HomeroomTeacher", "EmployeeID", "LEFT")]
COUNSELOR_T = [("Counselor", "Employee")]
COUNSELOR_L = [("stuHRTeacher", "CounselorID", "Counselor", "EmployeeID", "LEFT")]
STAFF_ACTIVE = [Condition("empSchool", "PrimarySchoolFlag", "eq", "1"), Condition("Employee", "TerminationDate", "blank")]
EMP_SCH_T = EMP_T + ["SchoolDef"]
EMP_SCH_L = EMP_L + [("empSchool", "SchoolID", "SchoolDef", "SchoolID", "INNER")]

# transcript (history) chain
TRN_T = ["historyStudentSessions", "historyStudentCourses", "historyStudentCourseGrades"]
TRN_L = [("Student", "StudentID", "historyStudentSessions", "StudentID", "INNER"),
         ("historyStudentSessions", "HistSessionID", "historyStudentCourses", "HistSessionID", "INNER"),
         ("historyStudentCourses", "HistStuCourseID", "historyStudentCourseGrades", "histStuCourseID", "INNER")]
TRN_C = [Condition("historyStudentCourseGrades", "IsFinalGrade", "eq", "1"),
         Condition("historyStudentCourses", "IncludeInTranscript", "eq", "1")]

# current-year term grades chain
TG_T = ["stuTermGrade", "GR_Gradebook", "ReportingPeriod"] + SEC_T + [("GradeTeacher", "Employee")]
TG_L = [("Student", "StudentID", "stuTermGrade", "StudentID", "INNER"),
        ("stuTermGrade", "GradebookID", "GR_Gradebook", "GradebookID", "INNER"),
        ("stuTermGrade", "ReportingPeriodID", "ReportingPeriod", "ReportingPeriodID", "INNER"),
        ("GR_Gradebook", "ScheduleFrameworkID", "ScheduleFramework", "ScheduleFrameworkID", "INNER")] + SEC_L + [
        ("ScheduleFramework", "TeacherID", "GradeTeacher", "EmployeeID", "LEFT")]


def RAW(heading, sql):
    return OutColumn("raw", column=sql, heading=heading)


def guardian_chain():
    """Every contact who may be contacted (NoContact <> 1), with primary phone + email."""
    return contact_chain(seq_cond=Condition("StudentContact", "NoContact", "ne", "1"))


# ================================================================= Raptor visitor management
def raptor():
    students = query("Raptor - students.csv", STU_SCH_T, STU_SCH_L,
                     [F("Student", "FirstName", "First Name", Fmt("trim")),
                      F("Student", "LastName", "Last Name", Fmt("trim")),
                      F("Student", "MiddleName", "Middle Name", Fmt("trim")),
                      F("Student", "DOB", "Date of Birth", Fmt("date_us")),
                      F("Student", "StudentCode", "ID Number", Fmt("trim")),
                      F("Student", "GenderCode", "Gender"), F("Student", "ADAGrade", "Grade"),
                      T("Self Sign Out", "false"),
                      F("SchoolDef", "SchoolName", "Building", Fmt("trim"))],
                     STU_C, distinct=True, sort=["Building", "Last Name", "First Name"])
    ct, cl, (sc, ci, pn, em) = guardian_chain()
    guardians = query("Raptor - guardians.csv", STU_SCH_T + ct, STU_SCH_L + cl,
                      [F("Student", "StudentCode", "Student ID Number", Fmt("trim")),
                       F("Student", "FirstName", "Student First Name", Fmt("trim")),
                       F("Student", "LastName", "Student Last Name", Fmt("trim")),
                       F("Student", "DOB", "Student Date of Birth", Fmt("date_us")),
                       F(ci, "FirstName", "Guardian First Name", Fmt("trim")),
                       F(ci, "LastName", "Guardian Last Name", Fmt("trim")),
                       F(sc, "RelationshipCode", "Relationship"),
                       phone_col("Guardian Phone", pn), F(em, "Address", "Guardian Email", Fmt("trim"), Fmt("lower")),
                       F(sc, "CheckInOut", "Can Check Out", Fmt("map", "1=true; 0=false")),
                       F("SchoolDef", "SchoolName", "Building", Fmt("trim"))],
                      STU_C + [Condition(ci, "ContactID", "not_blank")], distinct=True,
                      sort=["Building", "Student Last Name", "Guardian Last Name"])
    staff = query("Raptor - staff.csv", EMP_SCH_T, EMP_SCH_L,
                  [F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                   F("Employee", "EmployeeNumber", "ID Number", Fmt("trim")), C("Email", EMAIL("Employee", "staff")),
                   F("Employee", "FacultyFlag", "Title", Fmt("map", "1=Teacher; 0=Staff")),
                   F("SchoolDef", "SchoolName", "Building", Fmt("trim"))],
                  STAFF_ACTIVE, distinct=True, sort=["Building", "Last Name"])
    return {
        "id": "raptor", "name": "Raptor Technologies (visitor management)",
        "works_with": "Raptor Visitor Management / Raptor Alert student, guardian and staff imports",
        "description": "Student roster with the fields Raptor's student import uses (First Name, Last Name and ID "
                       "Number are required; Date of Birth, Gender, Grade and Self Sign Out are optional), a "
                       "guardian list (Raptor matches guardians by name + birth date or email) and a staff list. "
                       "Raptor imports one building at a time - filter on Building in Step 4, or use the 'Schools...' "
                       "quick filter, to make one file per school. " + CONTACT_NOTE,
        "spec_url": "https://raptortech.com/",
        "delivery": "Raptor > Setup > Student / Staff import (CSV) or Raptor's SIS sync folder",
        "requires": CONTACT_REQ,
        "confirm_with_vendor": "Raptor maps guardian and staff columns during import; confirm the layout with "
                               "Raptor support before the first upload.",
        "files": [f("raptor_students.csv", students), f("raptor_guardians.csv", guardians, CONFIRM),
                  f("raptor_staff.csv", staff, CONFIRM)],
    }


# ================================================================= Incident IQ
def incidentiq():
    stu = query("Incident IQ - users.csv", STU_SCH_T + HR_LIVE_T, STU_SCH_L + HR_LIVE_L,
                [F("Student", "StudentCode", "SIS ID", Fmt("trim")), C("Email", EMAIL("Student", "student")),
                 C("Username", USER("Student", "student")),
                 F("Student", "FirstName", "First Name", Fmt("trim")), F("Student", "LastName", "Last Name", Fmt("trim")),
                 T("Role", "Student"), F("Student", "ADAGrade", "Grade"),
                 F("SchoolDef", "SchoolName", "Location", Fmt("trim")), F("SchoolDef", "SchoolCode", "Location Code"),
                 C("Homeroom", P("HomeroomTeacher", "LastName", Fmt("trim")))],
                STU_C, distinct=True)
    staff = query("Staff part", EMP_SCH_T, EMP_SCH_L,
                  [F("Employee", "EmployeeNumber", "SIS ID", Fmt("trim")), C("Email", EMAIL("Employee", "staff")),
                   C("Username", USER("Employee", "staff")),
                   F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                   F("Employee", "FacultyFlag", "Role", Fmt("map", "1=Faculty; 0=Staff")), T("Grade"),
                   F("SchoolDef", "SchoolName", "Location", Fmt("trim")), F("SchoolDef", "SchoolCode", "Location Code"),
                   T("Homeroom")],
                  STAFF_ACTIVE, distinct=True)
    stu.union_parts = [staff]
    locations = query("Incident IQ - locations.csv", ["SchoolDef"], [],
                      [F("SchoolDef", "SchoolCode", "Location Code"), F("SchoolDef", "SchoolName", "Location Name", Fmt("trim")),
                       F("SchoolDef", "ShortName", "Abbreviation", Fmt("trim")), F("SchoolDef", "SchoolID", "SIS School ID")],
                      [Condition("SchoolDef", "ActiveFlag", "eq", "1")], sort=["Location Name"])
    return {
        "id": "incidentiq", "name": "Incident IQ",
        "works_with": "Incident IQ help desk / asset management (user and location import)",
        "description": "One users file with students and staff (SIS ID, email, username, names, role, grade, "
                       "location and homeroom) plus a locations file. Incident IQ maps columns during the import "
                       "and matches existing users on SIS ID or email - pick one and keep it consistent. "
                       "Many districts sync users from Google/Microsoft instead and only use this for homerooms "
                       "and grades.",
        "spec_url": "https://www.incidentiq.com/",
        "delivery": "Incident IQ > Admin > Users > Import (CSV) or the SFTP sync Incident IQ sets up",
        "confirm_with_vendor": CONFIRM,
        "files": [f("iiq_users.csv", stu, "students + staff in one file"), f("iiq_locations.csv", locations)],
    }


# ================================================================= School photos / yearbook (PSPA)
def pspa():
    stu = query("Photo roster - photo_roster.csv", STU_SCH_T + HR_LIVE_T, STU_SCH_L + HR_LIVE_L,
                [T("Volume Name"), T("Image Folder"), T("Image File Name"),
                 F("Student", "ADAGrade", "Grade", Fmt("map", GRADE_NUM)),
                 F("Student", "LastName", "Last Name", Fmt("trim")), F("Student", "FirstName", "First Name", Fmt("trim")),
                 F("HomeroomTeacher", "LastName", "Home Room", Fmt("trim")), T("Period"),
                 C("Teacher Name", P("HomeroomTeacher", "FirstName", Fmt("trim")), X(" "),
                   P("HomeroomTeacher", "LastName", Fmt("trim"))),
                 T("Track"), T("Department", "Student"),
                 F("Student", "StudentCode", "Student ID", Fmt("trim")),
                 F("SchoolDef", "SchoolName", "School", Fmt("trim"))],
                STU_C, distinct=True)
    staff = query("Staff part", EMP_SCH_T, EMP_SCH_L,
                  [T("Volume Name"), T("Image Folder"), T("Image File Name"), T("Grade"),
                   F("Employee", "LastName", "Last Name", Fmt("trim")), F("Employee", "FirstName", "First Name", Fmt("trim")),
                   T("Home Room"), T("Period"), T("Teacher Name"), T("Track"),
                   F("Employee", "FacultyFlag", "Department", Fmt("map", "1=Teacher; 0=Support Staff")),
                   F("Employee", "EmployeeNumber", "Student ID", Fmt("trim")),
                   F("SchoolDef", "SchoolName", "School", Fmt("trim"))],
                  STAFF_ACTIVE, distinct=True)
    stu.union_parts = [staff]
    stu.sort = [SortItem("School"), SortItem("Department"), SortItem("Grade"), SortItem("Last Name")]
    return {
        "id": "pspa", "name": "School photos / yearbook (PSPA roster)",
        "works_with": "Lifetouch, Jostens, Strawbridge, Herff Jones and other photographers that use the PSPA "
                      "(Professional School Photographers Association) index layout",
        "description": "Students and staff in PSPA column order (Grade, Last Name, First Name, Home Room, Teacher Name, "
                       "Department...). The photographer fills in Volume Name, Image Folder and Image File Name when "
                       "they send the pictures back. Make one file per school with the 'Schools...' quick filter. "
                       "Some photographers want it tab-delimited (INDEX.TXT) - open the CSV in Excel and Save As "
                       "'Text (Tab delimited)'.",
        "spec_url": "https://pspa.com/",
        "delivery": "Send to the photographer before picture day (their upload portal)",
        "confirm_with_vendor": "Photographers add their own columns (packages, camera card...). Ask yours whether "
                               "they want Student ID / School added (included here) or the plain PSPA layout.",
        "files": [f("photo_roster.csv", stu, "students + staff")],
    }


# ================================================================= Xello
def xello():
    school_type = RAW("SchoolType", "CASE WHEN SchoolDef.HighestGradeTaught IN ('09', '10', '11', '12') THEN 1 "
                                    "WHEN SchoolDef.HighestGradeTaught IS NULL THEN 3 ELSE 2 END")
    schools = query("Xello - School.csv", ["SchoolDef"], [],
                    [F("SchoolDef", "SchoolCode", "SchoolCode"), F("SchoolDef", "SchoolName", "Name", Fmt("trim")),
                     school_type], [Condition("SchoolDef", "ActiveFlag", "eq", "1")], sort=["Name"])
    students = query("Xello - Student.csv", STU_SCH_T, STU_SCH_L,
                     [F("Student", "StudentCode", "StudentID", Fmt("trim")),
                      F("Student", "FirstName", "FirstName", Fmt("trim")), F("Student", "LastName", "LastName", Fmt("trim")),
                      F("Student", "GenderCode", "Gender", Fmt("map", "M=M; F=F")),
                      F("Student", "ADAGrade", "CurrentGrade", Fmt("map", GRADE_XELLO)),
                      F("SchoolDef", "SchoolCode", "CurrentSchoolCode"), T("PreRegSchoolCode"),
                      F("Student", "DOB", "DateOfBirth", Fmt("date_iso")),
                      F("Student", "StateCode", "StateProvNumber"), C("Email", EMAIL("Student", "student"))],
                     STU_C, distinct=True, sort=["LastName", "FirstName"])
    ct, cl, (sc, ci, pn, em) = guardian_chain()
    parents = query("Xello - Parent.csv", STU_T + ct, STU_L + cl,
                    [F(ci, "FirstName", "FirstName", Fmt("trim")), F(ci, "LastName", "LastName", Fmt("trim")),
                     F(em, "Address", "Email", Fmt("trim"), Fmt("lower")),
                     F("Student", "StudentCode", "StudentId", Fmt("trim")),
                     F(ci, "ContactID", "SourceParentId"), phone_col("Phone", pn)],
                    STU_C + [Condition(em, "Address", "not_blank")], distinct=True)
    educators = query("Xello - Educator.csv", EMP_SCH_T, EMP_SCH_L,
                      [F("Employee", "FirstName", "FirstName", Fmt("trim")), F("Employee", "LastName", "LastName", Fmt("trim")),
                       C("Email", EMAIL("Employee", "staff")), F("SchoolDef", "SchoolCode", "SchoolCode"),
                       T("Permissions", "User"), F("Employee", "EmployeeID", "EducatorSISId"), T("JobTitle")],
                      STAFF_ACTIVE, distinct=True, sort=["LastName"])
    ed_stu = query("Xello - EducatorStudent.csv", STU_T + HR_LIVE_T[:1] + COUNSELOR_T,
                   STU_L + HR_LIVE_L[:1] + COUNSELOR_L,
                   [C("EducatorEmail", EMAIL("Counselor", "staff")),
                    F("Student", "StudentCode", "StudentId", Fmt("trim"))],
                   STU_C + [Condition("stuHRTeacher", "CounselorID", "not_blank")], distinct=True)
    courses = query("Xello - StudentCourses.csv", STU_T + TRN_T, STU_L + TRN_L,
                    [F("Student", "StudentCode", "StudentID", Fmt("trim")),
                     F("historyStudentCourses", "CourseCode_Local", "CourseCode", Fmt("trim")),
                     F("historyStudentCourses", "LongName_Local", "CourseName", Fmt("trim")),
                     F("historyStudentSessions", "GradeLevel", "GradeLevel", Fmt("map", GRADE_XELLO)),
                     F("historyStudentCourseGrades", "GradeAlpha", "GradeMark", Fmt("trim")),
                     F("historyStudentCourseGrades", "CreditHoursEarned", "CreditValue"),
                     F("historyStudentSessions", "EndDate", "DateCourseComplete", Fmt("date_iso")),
                     T("HSCourse"), T("CoursePart")],
                    STU_C + TRN_C + [Condition("Student", "ADAGrade", "in", SEC_GRADES)], distinct=True)
    catalog_q = query("Xello - CourseCodes.csv", ["Course", "ScheduleCourse", "Schedule", "SchoolDef"],
                      [("Course", "CourseID", "ScheduleCourse", "CourseID", "INNER"),
                       ("ScheduleCourse", "ScheduleID", "Schedule", "ScheduleID", "INNER"),
                       ("Schedule", "SchoolID", "SchoolDef", "SchoolID", "INNER")],
                      [F("SchoolDef", "SchoolCode", "SchoolCode"), F("Course", "CourseCode", "CourseCode", Fmt("trim")),
                       F("Course", "LongName", "CourseName", Fmt("trim")), F("Course", "CreditHours", "CreditValue"),
                       F("Course", "LowGradeLevel", "GradeLower", Fmt("map", GRADE_XELLO)),
                       F("Course", "HighGradeLevel", "GradeUpper", Fmt("map", GRADE_XELLO))],
                      [LIVE], distinct=True, sort=["SchoolCode", "CourseCode"])
    return {
        "id": "xello", "name": "Xello (college & career readiness)",
        "works_with": "Xello K-12 (and Xello's course planner / graduation requirements)",
        "description": "Xello's data feed: School, Student, Parent, Educator, EducatorStudent (counselor caseloads "
                       "from SAM's homeroom counselor), StudentCourses (transcript history, grades 6-12) and "
                       "CourseCodes. Dates are yyyy-mm-dd, kindergarten is 0 and Permissions is User - change "
                       "counselors/admins to Administrator in Xello. Xello prefers pipe ( | ) delimited files but "
                       "accepts CSV; ask your Xello implementation contact. " + CONTACT_NOTE,
        "spec_url": "https://help.xello.world/",
        "delivery": "Nightly SFTP to the Xello server and folder Xello provides",
        "requires": CONTACT_REQ,
        "files": [f("School.csv", schools), f("Student.csv", students), f("Parent.csv", parents),
                  f("Educator.csv", educators), f("EducatorStudent.csv", ed_stu, "counselor caseloads"),
                  f("StudentCourses.csv", courses, "transcript (history) grades"), f("CourseCodes.csv", catalog_q)],
    }


# ================================================================= Naviance
def naviance():
    at, al, ad = address_chain("Student", "StudentID", OT_STU)
    students = query("Naviance - student.csv",
                     STU_SCH_T + HR_LIVE_T + COUNSELOR_T + at + [("ClassRank", "ClassRank")],
                     STU_SCH_L + HR_LIVE_L + COUNSELOR_L + al +
                     [("Student", "StudentID", "ClassRank", "StudentID", "LEFT")],
                     [F("Student", "StudentCode", "Student ID", Fmt("trim")),
                      F("Student", "OriginalGradDate", "Class Year", Fmt("year")),
                      F("Student", "LastName", "Last Name", Fmt("trim")),
                      F("SchoolDef", "SchoolCode", "School ID"),
                      F("Student", "FirstName", "First Name", Fmt("trim")),
                      F("Student", "MiddleName", "Middle Name", Fmt("trim")),
                      F("Student", "PreferredName", "Nickname", Fmt("trim")),
                      F("Student", "DOB", "Date of Birth", Fmt("date_us")),
                      C("Student Email", EMAIL("Student", "student")),
                      F("Student", "StateCode", "State Student ID"),
                      F("Student", "GenderCode", "Gender"),
                      F("Counselor", "EmployeeID", "Counselor ID"),
                      F("HomeroomTeacher", "LastName", "Homeroom", Fmt("trim")),
                      F(ad, "AddrLine1", "Street Address 1", Fmt("trim")), F(ad, "AddrLine2", "Street Address 2", Fmt("trim")),
                      F(ad, "City", "City", Fmt("trim")), F(ad, "State", "State"), F(ad, "ZipCode", "Zip Code"),
                      F("Student", "CumulativeGPA", "GPA"), F("ClassRank", "ClassRank", "Rank")],
                     STU_C + [Condition("Student", "ADAGrade", "in", SEC_GRADES)], distinct=True,
                     sort=["Class Year", "Last Name"])
    ct, cl, (sc, ci, pn, em) = guardian_chain()
    pat, pal, pad = address_chain(ci, "ContactID", OT_CON, "P")
    parents = query("Naviance - parent.csv", STU_T + ct + pat, STU_L + cl + pal,
                    [F("Student", "StudentCode", "Student ID", Fmt("trim")), F(ci, "ContactID", "Parent ID"),
                     F(ci, "FirstName", "First Name", Fmt("trim")), F(ci, "LastName", "Last Name", Fmt("trim")),
                     F(pad, "AddrLine1", "Street Address 1", Fmt("trim")), F(pad, "City", "City", Fmt("trim")),
                     F(pad, "State", "State"), F(pad, "ZipCode", "Zip Code"),
                     F(ci, "Occupation", "Occupation", Fmt("trim")),
                     F(em, "Address", "Parent Email", Fmt("trim"), Fmt("lower")), phone_col("Home Phone", pn),
                     F(sc, "Custodial", "Custodial", Fmt("yes_no"))],
                    STU_C + [Condition("Student", "ADAGrade", "in", SEC_GRADES),
                             Condition(ci, "ContactID", "not_blank")], distinct=True)
    teachers = query("Naviance - teacher.csv", EMP_T, EMP_L,
                     [F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                      C("Email", EMAIL("Employee", "staff"))], EMP_C, distinct=True, sort=["Last Name"])
    courses = query("Naviance - student_course.csv", STU_T + TRN_T, STU_L + TRN_L,
                    [F("Student", "StudentCode", "Student ID", Fmt("trim")),
                     F("historyStudentCourses", "CourseCode_Local", "Course ID", Fmt("trim")),
                     F("historyStudentSessions", "GradeLevel", "Grade Level Taken", Fmt("map", GRADE_NUM)),
                     F("historyStudentCourseGrades", "ReportingCode", "Term", Fmt("trim")),
                     T("Course Status", "Completed"),
                     F("historyStudentCourses", "LongName_Local", "Course Name", Fmt("trim")),
                     F("historyStudentCourses", "TeacherName", "Teacher", Fmt("trim")),
                     F("historyStudentCourseGrades", "CreditHoursAttempted", "Credits Attempted"),
                     F("historyStudentCourseGrades", "CreditHoursEarned", "Credits Earned"),
                     F("historyStudentCourseGrades", "GradeAlpha", "Letter Grade", Fmt("trim")),
                     F("historyStudentCourseGrades", "GradeNumeric", "Score")],
                    STU_C + TRN_C + [Condition("Student", "ADAGrade", "in", HS_GRADES)], distinct=True)
    return {
        "id": "naviance", "name": "Naviance (college & career readiness)",
        "works_with": "PowerSchool Naviance data import (student, parent, teacher and course history)",
        "description": "Naviance's data-import files for grades 6-12. Student ID, Class Year (4-digit graduation year "
                       "from Student.OriginalGradDate) and Last Name are required. School ID is SAM's school code - "
                       "Naviance maps it to its own school during import. Course history comes from transcript "
                       "(history) grades for grades 9-12. " + CONTACT_NOTE,
        "spec_url": "https://help.naviance.com/",
        "delivery": "Naviance > Setup > Data Import (CSV upload) or Naviance's SFTP data sync",
        "requires": CONTACT_REQ + ["OWNER_TYPE_STUDENT"],
        "files": [f("student.csv", students), f("parent.csv", parents), f("teacher.csv", teachers),
                  f("student_course.csv", courses, "transcript (history) grades")],
    }


# ================================================================= SchooLinks
def schoolinks():
    cm = query("SchooLinks - CourseMaster.csv", ["Course", "ScheduleCourse", "Schedule", "SchoolDef"],
               [("Course", "CourseID", "ScheduleCourse", "CourseID", "INNER"),
                ("ScheduleCourse", "ScheduleID", "Schedule", "ScheduleID", "INNER"),
                ("Schedule", "SchoolID", "SchoolDef", "SchoolID", "INNER")],
               [F("SchoolDef", "SchoolCode", "school_sis_id_list"), F("Course", "CourseCode", "course_id", Fmt("trim")),
                F("Course", "LongName", "name", Fmt("trim")), F("Course", "Classification", "subject"),
                F("Course", "Description", "description", Fmt("trim")), F("Course", "CreditHours", "credits"),
                T("length"), F("Course", "LowGradeLevel", "grade_lower", Fmt("map", GRADE_XELLO)),
                F("Course", "HighGradeLevel", "grade_upper", Fmt("map", GRADE_XELLO)),
                T("terms_available"), T("tags"), T("enrollment_notes"), T("elective_eligibility"),
                T("alternate_eligibility"), T("max_completions_for_credit"), T("equivalent_course_ids"),
                T("part_of_sequence"), T("other_courses_in_sequence"), T("term_in_sequence"),
                T("requestable_by_student", "true"), F("Course", "StateCourseID", "state_course_id"), T("credit_group")],
               [LIVE], distinct=True, sort=["school_sis_id_list", "course_id"])
    sc = query("SchooLinks - StudentCourses.csv", STU_T + TRN_T + [("TranscriptSchool", "SchoolDef")],
               STU_L + TRN_L + [("historyStudentSessions", "SchoolID", "TranscriptSchool", "SchoolID", "LEFT")],
               [F("TranscriptSchool", "SchoolCode", "school_sis_id_list"),
                F("Student", "StudentCode", "student_sis_id", Fmt("trim")),
                F("historyStudentCourses", "CourseCode_Local", "course_id", Fmt("trim")),
                F("historyStudentCourses", "LongName_Local", "course_name", Fmt("trim")),
                F("historyStudentCourses", "SubjectAreaDesc", "course_subject", Fmt("trim")),
                F("historyStudentSessions", "EndDate", "school_year", Fmt("year")),
                F("historyStudentSessions", "GradeLevel", "grade_year", Fmt("map", GRADE_XELLO)),
                F("historyStudentCourseGrades", "ReportingCode", "academic_term", Fmt("trim")),
                F("historyStudentCourseGrades", "CreditHoursEarned", "credit_awarded"),
                T("credit_remaining_possible"),
                F("historyStudentCourseGrades", "GradeAlpha", "grade_achieved", Fmt("trim")),
                T("outside_credit_type")],
               STU_C + TRN_C + [Condition("Student", "ADAGrade", "in", SEC_GRADES)], distinct=True)
    caseload = query("SchooLinks - Caseload.csv", STU_SCH_T + HR_LIVE_T[:1] + COUNSELOR_T,
                     STU_SCH_L + HR_LIVE_L[:1] + COUNSELOR_L,
                     [F("SchoolDef", "SchoolCode", "school_sis_id_list"), F("Counselor", "EmployeeID", "staff_id"),
                      C("caseload_name", P("Counselor", "LastName", Fmt("trim")), X(" caseload")),
                      T("caseload_category", "Counselor"), F("Student", "StudentCode", "student_sis_id", Fmt("trim"))],
                     STU_C + [Condition("stuHRTeacher", "CounselorID", "not_blank")], distinct=True)
    return {
        "id": "schoolinks", "name": "SchooLinks (college & career readiness)",
        "works_with": "SchooLinks course planner, transcripts and counselor caseloads",
        "description": "CourseMaster (course catalog from the live schedule), StudentCourses (transcript history, grades "
                       "6-12) and Caseload (counselor caseloads from SAM's homeroom counselor). SchooLinks usually "
                       "takes students, staff and enrollments from your OneRoster/Clever feed - use those packages for "
                       "the roster.",
        "spec_url": "https://www.schoolinks.com/",
        "delivery": "SFTP to the SchooLinks folder set up during onboarding",
        "confirm_with_vendor": "SchooLinks shared these column names with SIS partners; confirm the student ID "
                               "column (student_sis_id) and delimiter with your SchooLinks onboarding contact.",
        "files": [f("CourseMaster.csv", cm), f("StudentCourses.csv", sc, "transcript (history) grades"),
                  f("Caseload.csv", caseload, "counselor caseloads")],
    }


# ================================================================= MTSS / early warning (Panorama, Branching Minds...)
def mtss():
    students = query("MTSS - students.csv", STU_SCH_T + HR_LIVE_T, STU_SCH_L + HR_LIVE_L,
                     [F("Student", "StudentCode", "Student ID", Fmt("trim")), F("Student", "StateCode", "State ID"),
                      F("Student", "FirstName", "First Name", Fmt("trim")), F("Student", "LastName", "Last Name", Fmt("trim")),
                      F("Student", "ADAGrade", "Grade"), F("SchoolDef", "SchoolCode", "School ID"),
                      F("SchoolDef", "SchoolName", "School Name", Fmt("trim")),
                      F("Student", "GenderCode", "Gender"), F("Student", "RaceCode", "Race"),
                      F("Student", "DOB", "Birth Date", Fmt("date_us")),
                      F("Student", "LangBackground", "Home Language"),
                      F("Student", "SPEDStatus", "Special Education"), F("Student", "Flag504", "Section 504", Fmt("yes_no")),
                      F("Student", "GiftedStatus", "Gifted"), F("Student", "FoodServiceCode", "Meal Status"),
                      F("HomeroomTeacher", "LastName", "Homeroom Teacher", Fmt("trim")),
                      C("Student Email", EMAIL("Student", "student"))],
                     STU_C, distinct=True, sort=["School Name", "Last Name"])
    attendance = query("MTSS - attendance.csv", STU_T + ["AttendanceDaily", "AttendanceCodes"],
                       STU_L + [("Student", "StudentID", "AttendanceDaily", "StudentID", "INNER"),
                                ("AttendanceDaily", "AttendanceCode", "AttendanceCodes", "AttendanceCode", "LEFT")],
                       [F("Student", "StudentCode", "Student ID", Fmt("trim")),
                        F("AttendanceDaily", "SchoolID", "School ID"),
                        F("AttendanceDaily", "AttendanceDate", "Date", Fmt("date_us")),
                        F("AttendanceDaily", "AttendanceCode", "Attendance Code"),
                        F("AttendanceCodes", "AttendanceDescription", "Description", Fmt("trim")),
                        F("AttendanceDaily", "PercentPresent", "Percent Present")],
                       STU_C + [Condition("AttendanceDaily", "AttendanceDate", "raw",
                                          f"AttendanceDaily.AttendanceDate >= {THIS_YEAR}")],
                       distinct=True, sort=["Student ID", "Date"])
    discipline = query("MTSS - discipline.csv",
                       STU_T + ["IncidentParticipant", "DisciplineIncident", ("IncidentAction", "IncidentAction")],
                       STU_L + [("Student", "StudentID", "IncidentParticipant", "ParticipantID", "INNER"),
                                ("IncidentParticipant", "IncidentID", "DisciplineIncident", "DisciplineIncidentID", "INNER"),
                                ("IncidentParticipant", "IncidentParticipantID", "IncidentAction", "IncidentParticipantID",
                                 "LEFT")],
                       [F("DisciplineIncident", "DisciplineIncidentID", "Incident ID"),
                        F("Student", "StudentCode", "Student ID", Fmt("trim")),
                        F("DisciplineIncident", "SchoolID", "School ID"),
                        F("DisciplineIncident", "IncidentDate", "Incident Date", Fmt("date_us")),
                        F("DisciplineIncident", "IncidentType", "Incident Type"),
                        F("DisciplineIncident", "Location", "Location"),
                        F("IncidentParticipant", "InfractionCode", "Infraction Code"),
                        F("IncidentAction", "ActionTaken", "Action Code"),
                        F("IncidentAction", "DaysToServe", "Days Assigned"),
                        F("IncidentAction", "BeginDate", "Action Start", Fmt("date_us")),
                        F("IncidentAction", "EndDate", "Action End", Fmt("date_us"))],
                       STU_C + [Condition("DisciplineIncident", "IncidentDate", "raw",
                                          f"DisciplineIncident.IncidentDate >= {THIS_YEAR}")],
                       distinct=True, sort=["Incident Date"])
    grades = query("MTSS - grades.csv", STU_T + TG_T, STU_L + TG_L,
                   [F("Student", "StudentCode", "Student ID", Fmt("trim")), F("Schedule", "SchoolID", "School ID"),
                    F("ScheduleFramework", "ScheduleFrameworkID", "Section ID"),
                    F("Course", "CourseCode", "Course Code"), F("Course", "LongName", "Course Name", Fmt("trim")),
                    C("Teacher", P("GradeTeacher", "FirstName", Fmt("trim")), X(" "), P("GradeTeacher", "LastName", Fmt("trim"))),
                    F("ReportingPeriod", "ReportingCode", "Grading Period", Fmt("trim")),
                    F("stuTermGrade", "TermAvgNumeric", "Grade Numeric"),
                    F("stuTermGrade", "TermAvgAlpha", "Grade Letter", Fmt("trim"))],
                   STU_C + [LIVE, Condition("stuTermGrade", "TermAvgNumeric", "not_blank")], distinct=True)
    return {
        "id": "mtss", "name": "MTSS / early warning (Panorama, Branching Minds...)",
        "works_with": "Panorama Student Success, Branching Minds, Otus, Edulastic dashboards and other MTSS / "
                      "early-warning tools that take SIS extracts",
        "description": "The four extracts MTSS tools ask for: student demographics and program flags, daily "
                       "attendance for this school year, discipline incidents and actions for this school year, and "
                       "current term grades. Most of these vendors also take rosters from OneRoster/Clever - use "
                       "this package for the data those feeds don't carry. Contains protected program data "
                       "(special education, 504, meal status, discipline); share only under a data-privacy "
                       "agreement that covers it.",
        "spec_url": "",
        "delivery": "SFTP to the vendor's folder (usually nightly)",
        "confirm_with_vendor": CONFIRM + " Discipline participants are matched to students by ID; if your district "
                               "records staff or visitors as participants, add a filter on "
                               "IncidentParticipant.ParticipantType.",
        "files": [f("mtss_students.csv", students), f("mtss_attendance.csv", attendance, "this school year"),
                  f("mtss_discipline.csv", discipline, "this school year"), f("mtss_grades.csv", grades, "current term grades")],
    }


# ================================================================= Frontline Absence Management
def frontline():
    staff = query("Frontline - employees.csv",
                  EMP_SCH_T + [("StaffPhoneLink", "PhoneRelationship"), ("StaffPhone", "PhoneNumber")],
                  EMP_SCH_L + [("Employee", "EmployeeID", "StaffPhoneLink", "OwnerID", "LEFT",
                                [Condition("StaffPhoneLink", "OwnerType", "eq", OT_EMP),
                                 Condition("StaffPhoneLink", "PrimaryPhone", "eq", "1")]),
                               ("StaffPhoneLink", "PhoneNumberID", "StaffPhone", "PhoneNumberID", "LEFT")],
                  [F("Employee", "EmployeeNumber", "Identifier", Fmt("trim")),
                   F("Employee", "LastName", "Last Name", Fmt("trim")), F("Employee", "FirstName", "First Name", Fmt("trim")),
                   F("Employee", "MiddleName", "Middle Name", Fmt("trim")), F("Employee", "NamePrefix", "Title", Fmt("trim")),
                   phone_col("Phone", "StaffPhone"), T("Pin"),
                   F("SchoolDef", "SchoolCode", "School External ID"),
                   F("Employee", "FacultyFlag", "Employee Type Description", Fmt("map", "1=Teacher; 0=Staff")),
                   C("Email", EMAIL("Employee", "staff")), F("Employee", "EmployeeID", "External ID"),
                   T("Active", "Y"), F("Employee", "HireDate", "Start Date", Fmt("date_us"))],
                  STAFF_ACTIVE, distinct=True, sort=["Last Name", "First Name"])
    schools = query("Frontline - schools.csv", ["SchoolDef"], [],
                    [F("SchoolDef", "SchoolCode", "School External ID"), F("SchoolDef", "SchoolName", "School Name", Fmt("trim"))],
                    [Condition("SchoolDef", "ActiveFlag", "eq", "1")], sort=["School Name"])
    return {
        "id": "frontline", "name": "Frontline Absence Management (Aesop)",
        "works_with": "Frontline Absence & Time (formerly Aesop) employee import",
        "description": "Employee file in Frontline's import order: Identifier (required - SAM EmployeeNumber), names, "
                       "Phone (10 digits, primary phone), Pin (left blank so Frontline assigns one), School External "
                       "ID (SAM school code - must match the school IDs set up in Frontline), employee type, email, "
                       "Active and Start Date. Plus a school list to set up the School External IDs.",
        "spec_url": "https://www.frontlineeducation.com/",
        "delivery": "Frontline > Data import (CSV) or the Frontline SFTP integration",
        "requires": ["OWNER_TYPE_EMPLOYEE"],
        "files": [f("frontline_employees.csv", staff), f("frontline_schools.csv", schools)],
    }


# ================================================================= DragonFly athletic eligibility
def dragonfly():
    grades = query("DragonFly - grades.csv", STU_T + TG_T + [("GradeSchool", "SchoolDef")],
                   STU_L + TG_L + [("Schedule", "SchoolID", "GradeSchool", "SchoolID", "INNER")],
                   [F("Student", "StudentCode", "Student ID", Fmt("trim")),
                    F("Student", "FirstName", "First Name", Fmt("trim")), F("Student", "LastName", "Last Name", Fmt("trim")),
                    F("Student", "DOB", "Date of Birth", Fmt("date_us")),
                    F("Student", "ADAGrade", "Grade Level", Fmt("map", GRADE_NUM)),
                    F("GradeSchool", "SchoolName", "School", Fmt("trim")),
                    F("Schedule", "EndDate", "Academic Year", Fmt("year")),
                    F("ReportingPeriod", "ReportingCode", "Grading Period Name", Fmt("trim")),
                    F("Course", "CourseCode", "Course ID", Fmt("trim")),
                    F("Course", "LongName", "Course Name", Fmt("trim")),
                    F("stuTermGrade", "TermAvgNumeric", "Grade"),
                    F("stuTermGrade", "TermAvgAlpha", "Letter Grade", Fmt("trim")),
                    RAW("Is Core", "CASE WHEN Course.CoreCourse IN (1, '1', 'Y', 'T') THEN 'Y' ELSE 'N' END"),
                    F("Course", "CreditHours", "Attempted Credit")],
                   STU_C + [LIVE, Condition("Student", "ADAGrade", "in", "07,08,09,10,11,12"),
                            Condition("stuTermGrade", "TermAvgNumeric", "not_blank")], distinct=True,
                   sort=["Last Name", "First Name", "Course Name"])
    return {
        "id": "dragonfly", "name": "DragonFly (athletic eligibility)",
        "works_with": "DragonFly MAX / DragonFly athletics academic eligibility",
        "description": "Current-year term grades for students in grades 7-12 with Academic Year (the year the "
                       "school year ends), Grading Period Name (your SAM reporting codes - DragonFly expects names "
                       "like Q1-Q4, S1/S2, Y1; translate them in Step 3 if yours differ), Is Core Y/N and credit. "
                       "DragonFly also offers a native SAM Spectra integration - ask them first; use this file if the "
                       "integration isn't available for your district.",
        "spec_url": "https://www.dragonfly.com/",
        "delivery": "SFTP to DragonFly (they provide the host and folder)",
        "confirm_with_vendor": "DragonFly provides its CSV template during setup; match the headings to it.",
        "files": [f("dragonfly_grades.csv", grades, "grades 7-12, current year")],
    }


# ================================================================= ACT / WorkKeys State and District testing (SDU)
def act_sdu():
    sdu = query("ACT - student data upload.csv", STU_T + at_placeholder()[0], STU_L + at_placeholder()[1],
                [T("Student Code"), T("Organization Code", "{{ACT_ORG_CODE}}"),
                 F("Student", "LastName", "Last Name", Fmt("trim")), F("Student", "FirstName", "First Name", Fmt("trim")),
                 F("Student", "MiddleName", "Middle Initial", Fmt("trim"), Fmt("left", "1")),
                 F("Student", "ADAGrade", "Grade", Fmt("strip_zeros")),
                 F("Student", "DOB", "Date of Birth", Fmt("date_us")),
                 F("Student", "StateCode", "State Student ID"), F("Student", "StudentCode", "Local Student ID", Fmt("trim")),
                 F("Student", "GenderCode", "Gender"),
                 F(at_placeholder()[2], "AddrLine1", "Address", Fmt("trim")),
                 F(at_placeholder()[2], "City", "City", Fmt("trim")), F(at_placeholder()[2], "State", "State"),
                 F(at_placeholder()[2], "ZipCode", "Zip Code"),
                 T("Test Code"), T("Delivery Format")],
                STU_C + [Condition("Student", "ADAGrade", "in", "10,11,12")], distinct=True,
                sort=["Grade", "Last Name", "First Name"])
    return {
        "id": "act_sdu", "name": "ACT / WorkKeys state testing (student data upload)",
        "works_with": "ACT State & District Testing student data upload (PAN); MAAP pre-ID is handled by MDE/DRC",
        "description": "Students in grades 10-12 in the ACT student data upload column order: Student Code (blank), "
                       "Organization Code (your ACT high school code - set it in District Settings), names, Grade, "
                       "Date of Birth (MM/DD/YYYY), State Student ID (MSIS), local ID, gender, address, then Test Code "
                       "and Delivery Format, which your test coordinator fills in. ACT revises this layout most years "
                       "- download the current template from PAN and match the headings before uploading. For MAAP, "
                       "pre-ID comes from MSIS through MDE/DRC; confirm with your District Test Coordinator.",
        "spec_url": "https://www.act.org/content/act/en/products-and-services/state-and-district-solutions.html",
        "delivery": "ACT PAN (Program Administration Network) > Student data upload",
        "requires": ["ACT_ORG_CODE", "OWNER_TYPE_STUDENT"],
        "confirm_with_vendor": "Check the column order against this year's ACT template in PAN - it changes "
                               "between testing years.",
        "files": [f("act_student_data_upload.csv", sdu, "grades 10-12")],
    }


_AT = None


def at_placeholder():
    global _AT
    if _AT is None:
        _AT = address_chain("Student", "StudentID", OT_STU)
    return _AT


MORE_PLATFORMS = [raptor, incidentiq, pspa, xello, naviance, schoolinks, mtss, frontline, dragonfly, act_sdu]

MORE_RULES = {
    "raptor": {"files": {
        "raptor_students.csv": R(["First Name", "Last Name", "ID Number"], ["ID Number"],
                                 {"Date of Birth": "date_us", "Self Sign Out": "bool"}),
        "raptor_guardians.csv": R(["Student ID Number", "Guardian First Name", "Guardian Last Name"], [],
                                  {"Guardian Email": "email", "Guardian Phone": "phone10"}),
        "raptor_staff.csv": R(["First Name", "Last Name", "ID Number"], ["ID Number"], {"Email": "email"})},
        "refs": [["raptor_guardians.csv", "Student ID Number", "raptor_students.csv", "ID Number"]]},
    "incidentiq": {"files": {
        "iiq_users.csv": R(["SIS ID", "Email", "First Name", "Last Name", "Role"], ["SIS ID", "Email"],
                           {"Email": "email"}),
        "iiq_locations.csv": R(["Location Code", "Location Name"], ["Location Code"])},
        "refs": [["iiq_users.csv", "Location Code", "iiq_locations.csv", "Location Code"]]},
    "pspa": {"files": {
        "photo_roster.csv": R(["Last Name", "First Name", "Department"], [],
                              {"Department": "enum:Student|Teacher|Faculty|Administration|Support Staff"})}},
    "xello": {"files": {
        "School.csv": R(["SchoolCode", "Name", "SchoolType"], ["SchoolCode"], {"SchoolType": "enum:1|2|3"}),
        "Student.csv": R(["StudentID", "FirstName", "LastName", "Gender", "CurrentGrade", "CurrentSchoolCode",
                          "DateOfBirth"], ["StudentID"],
                         {"Gender": "enum:M|F|N", "DateOfBirth": "date_iso", "Email": "email",
                          "CurrentGrade": "enum:-1|0|1|2|3|4|5|6|7|8|9|10|11|12"}),
        "Parent.csv": R(["FirstName", "LastName", "Email", "StudentId"], [("Email", "StudentId")], {"Email": "email"}),
        "Educator.csv": R(["FirstName", "LastName", "Email", "SchoolCode", "Permissions"], [("Email", "SchoolCode")],
                          {"Email": "email",
                           "Permissions": "enum:Administrator|User|LimitedAccess|1|2|3"}),
        "EducatorStudent.csv": R(["EducatorEmail", "StudentId"], [("EducatorEmail", "StudentId")],
                                 {"EducatorEmail": "email"}),
        "StudentCourses.csv": R(["StudentID", "CourseCode", "CourseName", "GradeLevel", "GradeMark", "CreditValue"],
                                [], {"DateCourseComplete": "date_iso"}),
        "CourseCodes.csv": R(["SchoolCode", "CourseCode", "CourseName"], [("SchoolCode", "CourseCode")])},
        "refs": [["Student.csv", "CurrentSchoolCode", "School.csv", "SchoolCode"],
                 ["Parent.csv", "StudentId", "Student.csv", "StudentID"],
                 ["Educator.csv", "SchoolCode", "School.csv", "SchoolCode"],
                 ["EducatorStudent.csv", "EducatorEmail", "Educator.csv", "Email"],
                 ["EducatorStudent.csv", "StudentId", "Student.csv", "StudentID"],
                 ["StudentCourses.csv", "StudentID", "Student.csv", "StudentID"]]},
    "naviance": {"files": {
        "student.csv": R(["Student ID", "Class Year", "Last Name", "School ID"], ["Student ID"],
                         {"Class Year": "year", "Date of Birth": "date_us", "Student Email": "email",
                          "Gender": "enum:M|F|X"}),
        "parent.csv": R(["Student ID", "Parent ID", "Last Name"], [("Student ID", "Parent ID")],
                        {"Parent Email": "email", "Home Phone": "phone10"}),
        "teacher.csv": R(["First Name", "Last Name", "Email"], ["Email"], {"Email": "email"}),
        "student_course.csv": R(["Student ID", "Course ID", "Course Status"], [],
                                {"Course Status": "enum:Completed|In Progress"})},
        "refs": [["parent.csv", "Student ID", "student.csv", "Student ID"],
                 ["student_course.csv", "Student ID", "student.csv", "Student ID"]]},
    "schoolinks": {"files": {
        "CourseMaster.csv": R(["school_sis_id_list", "course_id", "name"], [("school_sis_id_list", "course_id")],
                              {"requestable_by_student": "bool"}),
        "StudentCourses.csv": R(["student_sis_id", "course_id", "school_year"], [], {"school_year": "year"}),
        "Caseload.csv": R(["staff_id", "caseload_name", "student_sis_id"], [("staff_id", "student_sis_id")])}},
    "mtss": {"files": {
        "mtss_students.csv": R(["Student ID", "First Name", "Last Name", "Grade"], ["Student ID"],
                               {"Birth Date": "date_us", "Student Email": "email"}),
        "mtss_attendance.csv": R(["Student ID", "Date", "Attendance Code"], [("Student ID", "Date")],
                                 {"Date": "date_us"}),
        "mtss_discipline.csv": R(["Incident ID", "Student ID", "Incident Date"], [],
                                 {"Incident Date": "date_us"}),
        "mtss_grades.csv": R(["Student ID", "Section ID", "Grading Period"],
                             [("Student ID", "Section ID", "Grading Period")])},
        "refs": [["mtss_attendance.csv", "Student ID", "mtss_students.csv", "Student ID"],
                 ["mtss_discipline.csv", "Student ID", "mtss_students.csv", "Student ID"],
                 ["mtss_grades.csv", "Student ID", "mtss_students.csv", "Student ID"]]},
    "frontline": {"files": {
        "frontline_employees.csv": R(["Identifier", "Last Name", "First Name"], ["Identifier"],
                                     {"Phone": "phone10", "Email": "email", "Active": "yn", "Start Date": "date_us",
                                      "Pin": "digits"}),
        "frontline_schools.csv": R(["School External ID", "School Name"], ["School External ID"])},
        "refs": [["frontline_employees.csv", "School External ID", "frontline_schools.csv", "School External ID"]]},
    "dragonfly": {"files": {
        "dragonfly_grades.csv": R(["Student ID", "Academic Year", "Grading Period Name", "Course ID"],
                                  [("Student ID", "Course ID", "Grading Period Name")],
                                  {"Academic Year": "year", "Is Core": "yn", "Date of Birth": "date_us"})}},
    "act_sdu": {"files": {
        "act_student_data_upload.csv": R(["Organization Code", "Last Name", "First Name", "Grade", "Date of Birth",
                                          "State Student ID"], ["State Student ID"],
                                         {"Grade": "enum:10|11|12", "Date of Birth": "date_us",
                                          "Middle Initial": "maxlen:1"})}},
}
