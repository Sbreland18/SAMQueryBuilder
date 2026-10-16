# Vendor packages, round 4 - executed inside tools/make_exports.py after exports_vendors.py (shares all helpers).
# TalkingPoints, Remind, Renaissance, assessment demographics (i-Ready / mCLASS...), College Board SSOR,
# special education case management, health office, Alexandria, ID cards, substitute systems, 1:1 devices,
# dual enrollment, CTE certification testing, and the account shutoff (deprovisioning) package.

SHUTOFF_DAYS = "{{SHUTOFF_DAYS}}"
SINCE = "DATEADD(DAY, -" + SHUTOFF_DAYS + ", CAST(GETDATE() AS DATE))"
IEP_YN = "CASE WHEN LTRIM(RTRIM(ISNULL(Student.SPEDStatus, ''))) IN ('', '0', 'N') THEN 'N' ELSE 'Y' END"
GIFTED_YN = "CASE WHEN LTRIM(RTRIM(ISNULL(Student.GiftedStatus, ''))) IN ('', '0', 'N') THEN 'N' ELSE 'Y' END"


def staff_phone():
    return ([("StaffPhoneLink", "PhoneRelationship"), ("StaffPhone", "PhoneNumber")],
            [("Employee", "EmployeeID", "StaffPhoneLink", "OwnerID", "LEFT",
              [Condition("StaffPhoneLink", "OwnerType", "eq", OT_EMP),
               Condition("StaffPhoneLink", "PrimaryPhone", "eq", "1")]),
             ("StaffPhoneLink", "PhoneNumberID", "StaffPhone", "PhoneNumberID", "LEFT")])


def demographic_cols():
    return [F("Student", "GenderCode", "Gender"), F("Student", "RaceCode", "Race"),
            F("Student", "LangBackground", "Home Language"), RAW("Special Education", IEP_YN),
            YNcol("Section 504", "Student.Flag504"), RAW("Gifted", GIFTED_YN),
            F("Student", "FoodServiceCode", "Meal Status")]


# ================================================================= TalkingPoints
def talkingpoints():
    classes = query("TalkingPoints - classes.csv", SEC_T, SEC_L,
                    [class_title("Class Name"), F("ScheduleFramework", "ScheduleFrameworkID", "Class ID"),
                     F("Course", "LowGradeLevel", "Grade Level")],
                    [LIVE, Condition("ScheduleFramework", "TeacherID", "not_blank")], distinct=True,
                    sort=["Class Name"])
    class_list = RAW("Classes", "SELECT STRING_AGG(CAST(r.ScheduleFrameworkID AS VARCHAR(20)), ',') "
                                "FROM ScheduleRoster AS r WHERE r.StudentID = Student.StudentID AND "
                                "r.WithdrawnDate IS NULL AND r.ScheduleFrameworkID IN (SELECT f.ScheduleFrameworkID "
                                "FROM ScheduleFramework AS f JOIN ScheduleCourseTerm AS t ON f.ScheduleCourseTermID = "
                                "t.ScheduleCourseTermID JOIN ScheduleCourse AS c ON t.ScheduleCourseID = "
                                "c.ScheduleCourseID JOIN Schedule AS s ON c.ScheduleID = s.ScheduleID WHERE "
                                "s.LiveFlag = 1)")
    ct, cl, (sc, ci, pn, em) = guardian_chain()
    students = query("TalkingPoints - students.csv", STU_SCH_T + ct, STU_SCH_L + cl,
                     [F("Student", "StudentCode", "Student ID", Fmt("trim")),
                      F("Student", "FirstName", "Student First Name", Fmt("trim")),
                      F("Student", "LastName", "Student Last Name", Fmt("trim")),
                      F("Student", "ADAGrade", "Grade"), class_list,
                      F(ci, "FirstName", "Contact First Name", Fmt("trim")),
                      F(ci, "LastName", "Contact Last Name", Fmt("trim")),
                      phone_col("Contact Phone", pn), F(ci, "PrimaryLanguage", "Language"),
                      F(sc, "RelationshipCode", "Relationship"),
                      F(em, "Address", "Contact Email", Fmt("trim"), Fmt("lower")),
                      F("Student", "LangBackground", "ELL Status")],
                     STU_C + [Condition(ci, "ContactID", "not_blank")], distinct=True,
                     sort=["Student Last Name", "Student First Name"])
    staff = query("TalkingPoints - staff.csv", EMP_SCH_T, EMP_SCH_L,
                  [F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                   C("Email", EMAIL("Employee", "staff")),
                   RAW("Classes", "SELECT STRING_AGG(CAST(f.ScheduleFrameworkID AS VARCHAR(20)), ',') FROM "
                                  "ScheduleFramework AS f JOIN ScheduleCourseTerm AS t ON f.ScheduleCourseTermID = "
                                  "t.ScheduleCourseTermID JOIN ScheduleCourse AS c ON t.ScheduleCourseID = "
                                  "c.ScheduleCourseID JOIN Schedule AS s ON c.ScheduleID = s.ScheduleID WHERE "
                                  "s.LiveFlag = 1 AND f.TeacherID = Employee.EmployeeID"),
                   F("Employee", "FacultyFlag", "Non-Rostered Staff", Fmt("map", "1=N; 0=Y"))],
                  STAFF_ACTIVE, distinct=True, sort=["Last Name"])
    admins = query("TalkingPoints - admins.csv", ["SchoolDef", ("Principal", "Employee")],
                   [("SchoolDef", "SchoolPrincipalID", "Principal", "EmployeeID", "INNER")],
                   [F("Principal", "FirstName", "First Name", Fmt("trim")), F("Principal", "LastName", "Last Name", Fmt("trim")),
                    C("Email", EMAIL("Principal", "staff")), school_name()],
                   [Condition("SchoolDef", "ActiveFlag", "eq", "1")], distinct=True)
    return {
        "id": "talkingpoints", "name": "TalkingPoints (family messaging with translation)",
        "works_with": "TalkingPoints self-serve CSV uploader (Classes, Students, Staff, Admins)",
        "description": "TalkingPoints' four files, ONE SET PER SCHOOL - use the Schools: button to pick a school. "
                       "Students have one row per contact (student columns repeat) with the contact's phone and "
                       "language (from ContactInfo.PrimaryLanguage); Classes lists the student's live class IDs "
                       "separated by commas (needs SQL Server 2017 or newer for STRING_AGG). Staff list their class "
                       "IDs; non-faculty staff are Non-Rostered. Admins are the school principals. " + CONTACT_NOTE,
        "spec_url": "https://intercom.help/talkingpoints/en/articles/11139196-self-serve-csv-uploader-guide",
        "delivery": "TalkingPoints > Self-Serve .csv Uploader (or SFTP with your Partner Success Manager)",
        "requires": CONTACT_REQ,
        "confirm_with_vendor": "TalkingPoints publishes the exact columns in its Spreadsheet Template (one tab per "
                               "file). Match these headings to the template; language values must match its "
                               "Language List tab.",
        "files": [f("tp_classes.csv", classes), f("tp_students.csv", students, "one row per contact"),
                  f("tp_staff.csv", staff), f("tp_admins.csv", admins)],
    }


# ================================================================= Remind (CSV 2.0)
def remind():
    LANG = "Preferred_language"
    blank_cp = [T(f"contact_point_{i}") for i in range(3, 6)]
    blank_par = [T(f"parent_id_{i}") for i in range(3, 6)]
    sc_t = [("StudentContact1", "StudentContact"), ("StudentContact2", "StudentContact")]
    sc_l = [("Student", "StudentID", "StudentContact1", "StudentID", "LEFT",
             [Condition("StudentContact1", "Sequence", "eq", "1")]),
            ("Student", "StudentID", "StudentContact2", "StudentID", "LEFT",
             [Condition("StudentContact2", "Sequence", "eq", "2")])]
    stu = query("Remind - users.csv", STU_T + sc_t, STU_L + sc_l,
                [F("Student", "StudentCode", "user_id", Fmt("trim")), F("Student", "FirstName", "first_name", Fmt("trim")),
                 F("Student", "LastName", "last_name", Fmt("trim")), T(LANG),
                 C("contact_point_1", EMAIL("Student", "student")), T("contact_point_2")] + blank_cp +
                [T("role", "student"), F("Student", "DOB", "dob", Fmt("date_us")), F("Student", "ADAGrade", "grade"),
                 F("Student", "StudentCode", "student_number", Fmt("trim")),
                 RAW("parent_id_1", "CASE WHEN StudentContact1.ContactID IS NULL THEN '' ELSE 'P' + "
                                    "CAST(StudentContact1.ContactID AS VARCHAR(20)) END"),
                 RAW("parent_id_2", "CASE WHEN StudentContact2.ContactID IS NULL THEN '' ELSE 'P' + "
                                    "CAST(StudentContact2.ContactID AS VARCHAR(20)) END")] + blank_par,
                STU_C, distinct=True)
    pt, pl, (ps, pc, pp, pe) = contact_chain(
        "P", Condition("StudentContactP", "Sequence", "in", "1,2"))
    par = query("Parents part", STU_T + pt, STU_L + pl,
                [C("user_id", X("P"), P(pc, "ContactID")), F(pc, "FirstName", "first_name", Fmt("trim")),
                 F(pc, "LastName", "last_name", Fmt("trim")), T(LANG),
                 F(pe, "Address", "contact_point_1", Fmt("trim"), Fmt("lower")), phone_col("contact_point_2", pp)]
                + blank_cp + [T("role", "parent"), T("dob"), T("grade"), T("student_number"), T("parent_id_1"),
                              T("parent_id_2")] + blank_par,
                STU_C + [Condition(pc, "ContactID", "not_blank")], distinct=True)
    tch = query("Teachers part", EMP_T, EMP_L,
                [TID("user_id", "Employee"), F("Employee", "FirstName", "first_name", Fmt("trim")),
                 F("Employee", "LastName", "last_name", Fmt("trim")), T(LANG),
                 C("contact_point_1", EMAIL("Employee", "staff")), T("contact_point_2")] + blank_cp +
                [F("Employee", "FacultyFlag", "role", Fmt("map", "1=teacher; 0=staff")), T("dob"), T("grade"),
                 T("student_number"), T("parent_id_1"), T("parent_id_2")] + blank_par,
                STAFF_ACTIVE, distinct=True)
    stu.union_parts = [par, tch]
    schools = query("Remind - schools.csv", ["SchoolDef"], [],
                    [F("SchoolDef", "SchoolID", "school_id"),
                     F("SchoolDef", "SchoolName", "school_name", Fmt("trim"), Fmt("left", "60"))],
                    [Condition("SchoolDef", "ActiveFlag", "eq", "1")])
    classes = query("Remind - classes.csv", SEC_T, SEC_L,
                    [F("ScheduleFramework", "ScheduleFrameworkID", "class_id"), F("Schedule", "SchoolID", "school_id"),
                     class_title("class_name"), F("Schedule", "ScheduleCode", "Semester")],
                    [LIVE, Condition("ScheduleFramework", "TeacherID", "not_blank")], distinct=True)
    enr = query("Remind - enrollments.csv", ROS_T, ROS_L,
                [F("ScheduleRoster", "ScheduleFrameworkID", "class_id"), F("Student", "StudentCode", "user_id", Fmt("trim")),
                 T("class_role", "participant")], ROS_C, distinct=True)
    enr.union_parts = [query("Teachers part", SEC_T, SEC_L,
                             [F("ScheduleFramework", "ScheduleFrameworkID", "class_id"),
                              TID("user_id", "ScheduleFramework", "TeacherID"), T("class_role", "owner")],
                             [LIVE, Condition("ScheduleFramework", "TeacherID", "not_blank")], distinct=True)]
    se = query("Remind - school_enrollments.csv", STU_T, STU_L,
               [F("stuSchool", "SchoolID", "school_id"), F("Student", "StudentCode", "user_id", Fmt("trim")),
                T("school_role", "participant")], STU_C, distinct=True)
    se_par = query("Parents part", STU_T + pt, STU_L + pl,
                   [F("stuSchool", "SchoolID", "school_id"), C("user_id", X("P"), P(pc, "ContactID")),
                    T("school_role", "participant")], STU_C + [Condition(pc, "ContactID", "not_blank")], distinct=True)
    se_tch = query("Staff part", EMP_T, EMP_L,
                   [F("empSchool", "SchoolID", "school_id"), TID("user_id", "Employee"),
                    F("Employee", "FacultyFlag", "school_role", Fmt("map", "1=participant; 0=staff"))],
                   STAFF_ACTIVE, distinct=True)
    se.union_parts = [se_par, se_tch]
    return {
        "id": "remind", "name": "Remind (CSV 2.0 sync)",
        "works_with": "Remind Hub district rostering by SFTP (CSV 2.0)",
        "description": "Remind's five files: schools, classes, enrollments (teachers are owners), users (students, the "
                       "first two contacts as parents with email + phone, and staff) and school_enrollments. Parent "
                       "IDs are P + ContactID, teacher IDs T + EmployeeID; students point to their parents in "
                       "parent_id_1/2. Upload all five every time, at least every 90 days. " + CONTACT_NOTE,
        "spec_url": "https://help.remind.com/hc/en-us/articles/360013836460-Formatting-files-for-a-CSV-2-0-sync",
        "delivery": "SFTP to Remind (Remind Hub > Rostering > CSV sync gives the credentials)",
        "requires": CONTACT_REQ,
        "files": [f("schools.csv", schools), f("classes.csv", classes), f("enrollments.csv", enr, "students + teachers"),
                  f("users.csv", stu, "students + parents + staff"),
                  f("school_enrollments.csv", se, "students + parents + staff")],
    }


# ================================================================= Renaissance
def renaissance():
    roster = query("Renaissance - roster.csv", ROS_T + [("Teacher", "Employee"), "SchoolDef"],
                   ROS_L + [("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "INNER"),
                            ("Schedule", "SchoolID", "SchoolDef", "SchoolID", "INNER")],
                   [F("Student", "StudentCode", "Student ID", Fmt("trim")),
                    F("Student", "LastName", "Student Last Name", Fmt("trim")),
                    F("Student", "FirstName", "Student First Name", Fmt("trim")),
                    F("Student", "MiddleName", "Student Middle Name", Fmt("trim")),
                    F("Student", "ADAGrade", "Grade", Fmt("map", "KG=K")),
                    F("Student", "DOB", "Birthdate", Fmt("date_us")), F("Student", "GenderCode", "Gender"),
                    C("Student Username", USER("Student", "student")),
                    F("Course", "LongName", "Course", Fmt("trim")), class_title("Class"),
                    F("Teacher", "EmployeeNumber", "Teacher ID", Fmt("trim")),
                    F("Teacher", "LastName", "Teacher Last Name", Fmt("trim")),
                    F("Teacher", "FirstName", "Teacher First Name", Fmt("trim")),
                    C("Teacher Email", EMAIL("Teacher", "staff")), school_name()],
                   ROS_C + [Condition("Course", "LongName", "contains", "{{RENAISSANCE_COURSE_KEYWORD}}")],
                   distinct=True, sort=["School", "Class", "Student Last Name"])
    demo = query("Renaissance - demographics.csv", STU_T, STU_L,
                 [F("Student", "StudentCode", "Student ID", Fmt("trim"))] + demographic_cols() +
                 [F("Student", "StateCode", "State ID")], STU_C, distinct=True)
    return {
        "id": "renaissance", "name": "Renaissance (Star, Accelerated Reader, myON)",
        "works_with": "Renaissance single-school file import and demographics upload",
        "description": "A student + class + teacher roster for Renaissance's file import (one row per student per "
                       "class, limited to sections whose course name contains your keyword in District Settings - "
                       "e.g. 'Reading' or 'ELA'; use '%' for every class), plus a demographics file (gender, race, "
                       "home language, SPED / 504 / gifted Y/N, meal status, state ID) for Renaissance's demographic "
                       "reporting. Districts that roster through Clever or ClassLink need only the demographics file.",
        "spec_url": "https://support.renaissance.com/s/article/Upload-Demographics-1752691276019?language=en_US",
        "delivery": "Renaissance > Manage Students > Import (or the demographics upload page)",
        "requires": ["RENAISSANCE_COURSE_KEYWORD"],
        "confirm_with_vendor": "Renaissance maps columns during import - match the headings to its import wizard, "
                               "and translate SAM race / meal codes to Renaissance's values in Step 3.",
        "files": [f("renaissance_roster.csv", roster), f("renaissance_demographics.csv", demo)],
    }


# ================================================================= Assessment demographics (i-Ready, mCLASS...)
def assessment_demographics():
    demo = query("Assessment - student demographics.csv", STU_SCH_T, STU_SCH_L,
                 stu_basic() + [F("Student", "StateCode", "State Student ID"), F("Student", "ADAGrade", "Grade"),
                                F("SchoolDef", "SchoolCode", "School Code"), school_name(),
                                F("Student", "DOB", "Birth Date", Fmt("date_us"))] + demographic_cols() +
                 [C("Student Email", EMAIL("Student", "student"))],
                 STU_C, distinct=True, sort=["School", "Last Name"])
    roster = query("Assessment - class roster.csv", ROS_T + [("Teacher", "Employee")],
                   ROS_L + [("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "INNER")],
                   [F("Student", "StudentCode", "Student ID", Fmt("trim")),
                    F("ScheduleFramework", "ScheduleFrameworkID", "Class ID"), class_title("Class Name"),
                    F("Teacher", "EmployeeNumber", "Teacher ID", Fmt("trim")), C("Teacher Email", EMAIL("Teacher", "staff")),
                    F("Schedule", "SchoolID", "School ID")], ROS_C, distinct=True)
    return {
        "id": "assessment_demographics", "name": "Assessment platforms (i-Ready, Amplify mCLASS, others)",
        "works_with": "Curriculum Associates i-Ready, Amplify mCLASS / DIBELS 8, Istation, MAP Reading Fluency and "
                      "other screeners that take a demographics file for reporting groups",
        "description": "Student demographics for reporting groups (gender, race, home language, SPED / 504 / gifted, "
                       "meal status, state ID) and a class roster. Most of these platforms roster through Clever or "
                       "ClassLink - send them the demographics file when they ask for demographic reporting.",
        "spec_url": "",
        "delivery": "Vendor SFTP or the platform's data upload page",
        "confirm_with_vendor": CONFIRM,
        "files": [f("assessment_demographics.csv", demo), f("assessment_roster.csv", roster)],
    }


# ================================================================= College Board SSOR
def college_board():
    cb = query("College Board - SSOR registration.csv", STU_T, STU_L,
               [T("Testing AI Code", "{{CB_AI_CODE}}"), T("Attending AI Code"),
                F("Student", "FirstName", "First Name", Fmt("trim"), Fmt("replace", ".", ""), Fmt("left", "20")),
                F("Student", "MiddleName", "Middle Initial", Fmt("trim"), Fmt("left", "1")),
                F("Student", "LastName", "Last Name", Fmt("trim"), Fmt("replace", ".", ""), Fmt("left", "35")),
                F("Student", "DOB", "Date of Birth", Fmt("date_us")),
                F("Student", "GenderCode", "Gender", Fmt("map", "M=M; F=F")),
                F("Student", "ADAGrade", "Grade", Fmt("strip_zeros")), T("Test", "{{CB_TEST}}"),
                F("Student", "StudentCode", "School Student ID", Fmt("trim"), Fmt("remove_spaces")),
                F("Student", "StudentCode", "District Student ID", Fmt("trim"), Fmt("remove_spaces")),
                F("Student", "StateCode", "State Student ID", Fmt("trim"), Fmt("remove_spaces"))],
               STU_C + [Condition("Student", "ADAGrade", "in", "08,09,10,11,12")], distinct=True,
               sort=["Grade", "Last Name"])
    return {
        "id": "college_board", "name": "College Board in-school testing (PSAT / SAT School Day)",
        "works_with": "SAT Suite Ordering & Registration (SSOR) student registration upload",
        "description": "SSOR's 12 columns in order: Testing AI Code (District Settings), Attending AI Code, First Name "
                       "(20), Middle Initial, Last Name (35), Date of Birth, Gender (M/F/A), Grade, Test (PNM, P89, "
                       "P10 or SAT - District Settings), School / District / State Student IDs. One file per test: "
                       "filter Grade in Step 4 (e.g. 10 for PSAT 10). Gender codes other than M/F must be changed "
                       "to A in Step 3.",
        "spec_url": "https://satsuite.collegeboard.org/k12-educators/educator-experience/in-school/register/"
                    "uploading-student-registration-data",
        "delivery": "SSOR > Student registration > Upload (use the SSOR template's column order)",
        "requires": ["CB_AI_CODE", "CB_TEST"],
        "files": [f("ssor_registration.csv", cb, "grades 8-12; one test per file")],
    }


# ================================================================= Special education case management
def sped_case():
    ct, cl, (sc, ci, pn, em) = contact_chain()
    at, al, ad = address_chain("Student", "StudentID", OT_STU)
    students = query("SPED - students.csv", STU_SCH_T + HR_LIVE_T + ct + at, STU_SCH_L + HR_LIVE_L + cl + al,
                     stu_basic() + [F("Student", "MiddleName", "Middle Name", Fmt("trim")),
                                    F("Student", "StateCode", "State ID"), F("Student", "DOB", "Birth Date", Fmt("date_us")),
                                    F("Student", "ADAGrade", "Grade"), F("SchoolDef", "SchoolCode", "School Code"),
                                    school_name()] + demographic_cols() +
                     [F("Student", "SPEDStatus", "SPED Status Code"),
                      F("HomeroomTeacher", "LastName", "Homeroom", Fmt("trim")),
                      F(ad, "AddrLine1", "Address", Fmt("trim")), F(ad, "City", "City", Fmt("trim")),
                      F(ad, "State", "State"), F(ad, "ZipCode", "Zip")] + guardian_cols(ci, pn, em),
                     STU_C, distinct=True, sort=["School", "Last Name"])
    sched = query("SPED - schedules.csv", ROS_T + [("Teacher", "Employee")],
                  ROS_L + [("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "LEFT")],
                  [F("Student", "StudentCode", "Student ID", Fmt("trim")), F("ScheduleFramework", "Period", "Period"),
                   F("Course", "CourseCode", "Course Code"), F("Course", "LongName", "Course", Fmt("trim")),
                   C("Teacher", P("Teacher", "FirstName", Fmt("trim")), X(" "), P("Teacher", "LastName", Fmt("trim"))),
                   C("Teacher Email", EMAIL("Teacher", "staff"))], ROS_C, distinct=True)
    staff = staff_q("SPED - staff.csv",
                    [F("Employee", "EmployeeNumber", "Staff ID", Fmt("trim")),
                     F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                     C("Email", EMAIL("Employee", "staff")), school_name()])
    return {
        "id": "sped_case", "name": "Special education case management (IEP systems)",
        "works_with": "Frontline Special Education / IEP, PCG EasyIEP, SpedTrack, Embrace and other IEP systems",
        "description": "The SIS feed IEP systems need: every enrolled student (not only SPED - referrals start in "
                       "general education) with demographics, SAM SPED status, homeroom, address and primary "
                       "guardian, plus class schedules (for teacher access to IEPs) and staff. Contains protected "
                       "program data - share only under the vendor's data-privacy agreement. " + CONTACT_NOTE,
        "spec_url": "",
        "delivery": "Vendor SFTP (usually nightly)",
        "requires": CONTACT_REQ + ["OWNER_TYPE_STUDENT"],
        "confirm_with_vendor": CONFIRM,
        "files": [f("sped_students.csv", students), f("sped_schedules.csv", sched), f("sped_staff.csv", staff)],
    }


# ================================================================= Health office
def health_office():
    ct, cl, (sc, ci, pn, em) = contact_chain()
    med_t = [("MedicalInfo", "MedicalInfo")]
    med_l = [("Student", "StudentID", "MedicalInfo", "OwnerID", "LEFT",
              [Condition("MedicalInfo", "OwnerType", "eq", OT_STU)])]
    students = query("Health - students.csv", STU_SCH_T + HR_LIVE_T + ct + med_t, STU_SCH_L + HR_LIVE_L + cl + med_l,
                     stu_basic() + [F("Student", "DOB", "Birth Date", Fmt("date_us")), F("Student", "GenderCode", "Gender"),
                                    F("Student", "ADAGrade", "Grade"), school_name(),
                                    F("HomeroomTeacher", "LastName", "Homeroom", Fmt("trim"))] +
                     guardian_cols(ci, pn, em) +
                     [F("MedicalInfo", "LastPhysical", "Last Physical", Fmt("date_us")),
                      YNcol("Medicaid", "MedicalInfo.MedicaidFlag"),
                      YNcol("Permission to Transport", "MedicalInfo.PermissiontoTransport")],
                     STU_C, distinct=True, sort=["School", "Last Name"])
    imm = query("Health - immunizations.csv", STU_T + ["ImmunizationDetail", "ImmunizationCodes"],
                STU_L + [("Student", "StudentID", "ImmunizationDetail", "OwnerID", "INNER",
                          [Condition("ImmunizationDetail", "OwnerType", "eq", OT_STU)]),
                         ("ImmunizationDetail", "ImmunizationCodeID", "ImmunizationCodes", "ImmunizationCodeID", "INNER")],
                [F("Student", "StudentCode", "Student ID", Fmt("trim")),
                 F("ImmunizationCodes", "ImmunizationCode", "Vaccine Code"),
                 F("ImmunizationCodes", "Description", "Vaccine", Fmt("trim")),
                 F("ImmunizationDetail", "ImmunizationDate", "Date Given", Fmt("date_us"))],
                STU_C, distinct=True, sort=["Student ID", "Vaccine Code", "Date Given"])
    cond = query("Health - conditions.csv", STU_T + ["MedicalCondition"],
                 STU_L + [("Student", "StudentID", "MedicalCondition", "OwnerID", "INNER",
                           [Condition("MedicalCondition", "OwnerType", "eq", OT_STU)])],
                 [F("Student", "StudentCode", "Student ID", Fmt("trim")),
                  F("MedicalCondition", "MedicalCode", "Condition Code"),
                  F("MedicalCondition", "Notes", "Notes", Fmt("trim"))],
                 STU_C + [Condition("MedicalCondition", "SuppressFlag", "ne", "1")], distinct=True)
    return {
        "id": "health_office", "name": "Health office (SNAP Health Center, Magnus Health...)",
        "works_with": "SNAP Health Center, Magnus Health, Health Office Anywhere, SchoolDoc and other nurse systems",
        "description": "Students with homeroom, primary guardian, last physical, Medicaid and transport permission; "
                       "immunization history (vaccine code and date) and medical conditions (suppressed conditions "
                       "left out). Health data is protected - send it only to the nurse system under a "
                       "data-privacy agreement. " + CONTACT_NOTE,
        "spec_url": "",
        "delivery": "Vendor SFTP (usually nightly)",
        "requires": CONTACT_REQ + ["OWNER_TYPE_STUDENT"],
        "confirm_with_vendor": CONFIRM,
        "files": [f("health_students.csv", students), f("health_immunizations.csv", imm),
                  f("health_conditions.csv", cond)],
    }


# ================================================================= Alexandria library
def alexandria():
    stu = query("Alexandria - patrons.csv", STU_SCH_T + HR_LIVE_T, STU_SCH_L + HR_LIVE_L,
                [F("Student", "StudentCode", "Barcode", Fmt("trim")), F("Student", "LastName", "Last Name", Fmt("trim")),
                 F("Student", "FirstName", "First Name", Fmt("trim")), F("Student", "MiddleName", "Middle Name", Fmt("trim")),
                 T("Patron Policy", "Student"), F("Student", "ADAGrade", "Grade"),
                 F("HomeroomTeacher", "LastName", "Teacher / Homeroom", Fmt("trim")),
                 F("Student", "OriginalGradDate", "Graduation Year", Fmt("year")),
                 F("SchoolDef", "ShortName", "Site", Fmt("trim")), C("Email", EMAIL("Student", "student")),
                 F("Student", "GenderCode", "Gender"), F("Student", "DOB", "Birthdate", Fmt("date_us")), T("Status", "Active")],
                STU_C, distinct=True)
    staff = query("Staff part", EMP_SCH_T, EMP_SCH_L,
                  [C("Barcode", X("T"), P("Employee", "EmployeeNumber", Fmt("trim"))),
                   F("Employee", "LastName", "Last Name", Fmt("trim")), F("Employee", "FirstName", "First Name", Fmt("trim")),
                   F("Employee", "MiddleName", "Middle Name", Fmt("trim")),
                   F("Employee", "FacultyFlag", "Patron Policy", Fmt("map", "1=Teacher; 0=Staff")), T("Grade"),
                   T("Teacher / Homeroom"), T("Graduation Year"), F("SchoolDef", "ShortName", "Site", Fmt("trim")),
                   C("Email", EMAIL("Employee", "staff")), T("Gender"), T("Birthdate"), T("Status", "Active")],
                  STAFF_ACTIVE, distinct=True)
    stu.union_parts = [staff]
    return {
        "id": "alexandria", "name": "Alexandria (library patrons)",
        "works_with": "COMPanion Alexandria patron import",
        "description": "Students and staff in one patron file: Barcode (student ID; staff get a T prefix), names, "
                       "Patron Policy, grade, homeroom, graduation year, Site (SchoolDef.ShortName), email, gender, "
                       "birthdate and status. Map the columns once in Alexandria's import and save the mapping.",
        "spec_url": "",
        "delivery": "Alexandria > Operations > Import > Patrons (or automatic import from a folder)",
        "confirm_with_vendor": CONFIRM,
        "files": [f("alexandria_patrons.csv", stu, "students + staff")],
    }


# ================================================================= ID cards
def id_cards():
    stu = query("ID cards - cards.csv", STU_SCH_T + HR_LIVE_T, STU_SCH_L + HR_LIVE_L,
                [F("Student", "StudentCode", "ID Number", Fmt("trim")), F("Student", "FirstName", "First Name", Fmt("trim")),
                 F("Student", "LastName", "Last Name", Fmt("trim")), T("Role", "Student"),
                 F("Student", "ADAGrade", "Grade"), F("HomeroomTeacher", "LastName", "Homeroom", Fmt("trim")),
                 F("Student", "OriginalGradDate", "Class Of", Fmt("year")),
                 F("Student", "LunchNumber", "Barcode", Fmt("trim")), school_name(),
                 C("Photo File", P("Student", "StudentCode", Fmt("trim")), X(".jpg"))],
                STU_C, distinct=True)
    staff = query("Staff part", EMP_SCH_T, EMP_SCH_L,
                  [F("Employee", "EmployeeNumber", "ID Number", Fmt("trim")),
                   F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                   F("Employee", "FacultyFlag", "Role", Fmt("map", "1=Teacher; 0=Staff")), T("Grade"), T("Homeroom"),
                   T("Class Of"), F("Employee", "EmployeeNumber", "Barcode", Fmt("trim")), school_name(),
                   C("Photo File", P("Employee", "EmployeeNumber", Fmt("trim")), X(".jpg"))],
                  STAFF_ACTIVE, distinct=True)
    stu.union_parts = [staff]
    stu.sort = [SortItem("School"), SortItem("Role"), SortItem("Last Name")]
    return {
        "id": "id_cards", "name": "Student & staff ID cards",
        "works_with": "ID Works, CardExchange, Asure ID, Jolly and photographers' ID card services",
        "description": "One row per card: ID number, names, role, grade, homeroom, class-of year, Barcode (lunch PIN "
                       "for students so the card works in the cafeteria line - change to ID Number in Step 3 if you "
                       "prefer) and the photo file name (ID + .jpg, the way most photographers name images).",
        "spec_url": "",
        "delivery": "Card-printing software import, or send to the photographer",
        "confirm_with_vendor": CONFIRM,
        "files": [f("id_cards.csv", stu, "students + staff")],
    }


# ================================================================= Substitute systems
def substitutes():
    pt, pl = staff_phone()
    staff = staff_q("Substitutes - employees.csv",
                    [F("Employee", "EmployeeNumber", "Employee ID", Fmt("trim")),
                     F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                     C("Email", EMAIL("Employee", "staff")), phone_col("Phone", "StaffPhone"),
                     F("SchoolDef", "SchoolCode", "School Code"), school_name(),
                     F("Employee", "FacultyFlag", "Position", Fmt("map", "1=Teacher; 0=Staff")),
                     F("Employee", "HireDate", "Start Date", Fmt("date_us")), T("Active", "Y")],
                    pt, pl)
    schools = query("Substitutes - schools.csv", ["SchoolDef"], [],
                    [F("SchoolDef", "SchoolCode", "School Code"), F("SchoolDef", "SchoolName", "School Name", Fmt("trim"))],
                    [Condition("SchoolDef", "ActiveFlag", "eq", "1")])
    return {
        "id": "substitutes", "name": "Substitute systems (Red Rover, ESS / Kelly...)",
        "works_with": "Red Rover, ESS / Kelly Education, Swing and other absence & substitute systems",
        "description": "Employees with ID, email, primary phone (10 digits), school, position, start date and Active, "
                       "plus a school list. Use the Frontline package for Frontline Absence Management.",
        "spec_url": "",
        "delivery": "Vendor SFTP or admin import",
        "requires": ["OWNER_TYPE_EMPLOYEE"],
        "confirm_with_vendor": CONFIRM,
        "files": [f("sub_employees.csv", staff), f("sub_schools.csv", schools)],
    }


# ================================================================= 1:1 devices
def devices():
    ct, cl, (sc, ci, pn, em) = contact_chain()
    stu = query("Devices - students.csv", STU_SCH_T + HR_LIVE_T + ct, STU_SCH_L + HR_LIVE_L + cl,
                stu_basic() + [F("Student", "ADAGrade", "Grade"), C("Email", EMAIL("Student", "student")),
                               school_name(), F("HomeroomTeacher", "LastName", "Homeroom", Fmt("trim")),
                               C("Homeroom Teacher Email", EMAIL("HomeroomTeacher", "staff")),
                               C("Guardian Name", P(ci, "FirstName", Fmt("trim")), X(" "), P(ci, "LastName", Fmt("trim"))),
                               F(em, "Address", "Guardian Email", Fmt("trim"), Fmt("lower")),
                               T("Asset Tag"), T("Serial Number")],
                STU_C, distinct=True, sort=["School", "Homeroom", "Last Name"])
    return {
        "id": "devices", "name": "1:1 device checkout",
        "works_with": "Incident IQ, Destiny Resource Manager, Asset Panda, Google Admin device notes and 1:1 "
                      "checkout / insurance forms",
        "description": "Every student with grade, email, homeroom (and homeroom teacher email) and primary guardian, "
                       "with blank Asset Tag and Serial Number columns to fill at checkout or match from the "
                       "asset system. Use the Schools: button for one school's distribution day. " + CONTACT_NOTE,
        "spec_url": "",
        "delivery": "Asset system import or mail merge",
        "requires": CONTACT_REQ,
        "files": [f("device_students.csv", stu)],
    }


# ================================================================= Dual enrollment
def dual_enrollment():
    ct, cl, (sc, ci, pn, em) = contact_chain()
    at, al, ad = address_chain("Student", "StudentID", OT_STU)
    dual = query("Dual enrollment - students.csv", ROS_T + ["SchoolDef", ("Teacher", "Employee")] + ct + at,
                 ROS_L + [("Schedule", "SchoolID", "SchoolDef", "SchoolID", "INNER"),
                          ("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "LEFT")] + cl + al,
                 stu_basic() + [F("Student", "MiddleName", "Middle Name", Fmt("trim")),
                                F("Student", "DOB", "Birth Date", Fmt("date_us")), F("Student", "GenderCode", "Gender"),
                                F("Student", "ADAGrade", "Grade"), F("Student", "StateCode", "State ID"),
                                C("Email", EMAIL("Student", "student")), school_name(),
                                F(ad, "AddrLine1", "Address", Fmt("trim")), F(ad, "City", "City", Fmt("trim")),
                                F(ad, "State", "State"), F(ad, "ZipCode", "Zip"),
                                F("Course", "CourseCode", "Course Code", Fmt("trim")),
                                F("Course", "LongName", "Course", Fmt("trim")), F("ScheduleFramework", "Period", "Period"),
                                C("Instructor", P("Teacher", "FirstName", Fmt("trim")), X(" "),
                                  P("Teacher", "LastName", Fmt("trim")))] + guardian_cols(ci, pn, em),
                 ROS_C + [Condition("Course", "DualCreditReported", "eq", "1")], distinct=True,
                 sort=["Course", "Last Name"])
    return {
        "id": "dual_enrollment", "name": "Dual enrollment / community college",
        "works_with": "Community college dual-credit registration (e.g. Mississippi community colleges) and "
                      "early-college programs",
        "description": "Students scheduled in courses marked Dual Credit in SAM (Course.DualCreditReported), with "
                       "birth date, state ID, address, course, period, instructor and primary guardian - the details "
                       "colleges ask for at registration. Change the course filter in Step 4 if your district marks "
                       "dual-credit sections another way. " + CONTACT_NOTE,
        "spec_url": "",
        "delivery": "Send to the college's dual-enrollment office (secure upload or encrypted email)",
        "requires": CONTACT_REQ + ["OWNER_TYPE_STUDENT"],
        "confirm_with_vendor": CONFIRM,
        "files": [f("dual_enrollment.csv", dual)],
    }


# ================================================================= CTE certification testing
def cte_testing():
    cte = query("CTE - testing roster.csv", ROS_T + ["SchoolDef", ("Teacher", "Employee")],
                ROS_L + [("Schedule", "SchoolID", "SchoolDef", "SchoolID", "INNER"),
                         ("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "LEFT")],
                stu_basic() + [F("Student", "DOB", "Birth Date", Fmt("date_us")), F("Student", "ADAGrade", "Grade"),
                               F("Student", "StateCode", "State ID"), C("Email", EMAIL("Student", "student")),
                               school_name(), F("Course", "CourseCode", "Course Code", Fmt("trim")),
                               F("Course", "StateCourseID", "State Course ID"),
                               F("Course", "LongName", "Course", Fmt("trim")),
                               C("Teacher", P("Teacher", "FirstName", Fmt("trim")), X(" "), P("Teacher", "LastName", Fmt("trim"))),
                               C("Teacher Email", EMAIL("Teacher", "staff")),
                               RAW("IEP", IEP_YN), YNcol("504", "Student.Flag504")],
                ROS_C + [Condition("Course", "CourseCode", "in", "{{CTE_COURSE_CODES}}")], distinct=True,
                sort=["Course", "Last Name"])
    return {
        "id": "cte_testing", "name": "CTE certification testing (Precision Exams / YouScience, NOCTI...)",
        "works_with": "YouScience / Precision Exams, NOCTI, Certiport and state CTE assessment rosters",
        "description": "Students in your CTE courses (course codes listed in District Settings) with birth date, state "
                       "ID, email, course, teacher and IEP / 504 flags for testing accommodations.",
        "spec_url": "",
        "delivery": "Vendor roster upload",
        "requires": ["CTE_COURSE_CODES"],
        "confirm_with_vendor": CONFIRM,
        "files": [f("cte_roster.csv", cte)],
    }


# ================================================================= Account shutoff (deprovisioning)
DISABLE_SCRIPT = r'''<#
  Disable-ADUsers.ps1 - disables Active Directory accounts listed in shutoff_students.csv / shutoff_staff.csv.
      .\Disable-ADUsers.ps1 -CsvPath .\shutoff_students.csv                 # preview only
      .\Disable-ADUsers.ps1 -CsvPath .\shutoff_students.csv -Apply          # disable
      .\Disable-ADUsers.ps1 -CsvPath .\shutoff_staff.csv -Apply -MoveToOU "OU=Disabled,DC=district,DC=local"
  Accounts are matched on the Username column (SamAccountName) and are DISABLED, never deleted.
#>
param([Parameter(Mandatory)][string]$CsvPath, [switch]$Apply, [string]$MoveToOU)
Import-Module ActiveDirectory
$log = Join-Path (Split-Path $CsvPath) ("ad_disable_{0:yyyy-MM-dd_HHmm}.log" -f (Get-Date))
foreach ($u in Import-Csv $CsvPath) {
    if (-not $u.Username) { continue }
    $acct = Get-ADUser -Filter "SamAccountName -eq '$($u.Username)'" -ErrorAction SilentlyContinue
    if (-not $acct) { "NOT FOUND $($u.Username)" | Tee-Object -FilePath $log -Append; continue }
    "DISABLE $($u.Username) ($($u.'Last Name'), $($u.'First Name'))" | Tee-Object -FilePath $log -Append
    if ($Apply) {
        Disable-ADAccount $acct
        Set-ADUser $acct -Description ("Disabled {0:yyyy-MM-dd} by SAM Ad Hoc Query Builder shutoff list" -f (Get-Date))
        if ($MoveToOU) { Move-ADObject $acct -TargetPath $MoveToOU }
    }
}
if (-not $Apply) { "Preview only - run again with -Apply to disable these accounts." }
'''


def account_shutoff():
    last_reg = Condition("StudentRegistration", "StudentRegistrationID", "raw",
                         "StudentRegistration.StudentRegistrationID = (SELECT MAX(x.StudentRegistrationID) FROM "
                         "StudentRegistration AS x WHERE x.StudentID = Student.StudentID)")
    left_cond = Condition("Student", "StudentID", "raw",
                          "Student.StudentID IN (SELECT StudentID FROM StudentRegistration WHERE RegistrationDate >= "
                          + SINCE + ")")
    stu = query("Account shutoff - students.csv",
                ["Student", ("StudentRegistration", "StudentRegistration"), ("LastSchool", "SchoolDef")],
                [("Student", "StudentID", "StudentRegistration", "StudentID", "LEFT", [last_reg]),
                 ("StudentRegistration", "SchoolID", "LastSchool", "SchoolID", "LEFT")],
                [F("Student", "StudentCode", "Student ID", Fmt("trim")), F("Student", "FirstName", "First Name", Fmt("trim")),
                 F("Student", "LastName", "Last Name", Fmt("trim")), C("Email", EMAIL("Student", "student")),
                 C("Username", USER("Student", "student")), F("Student", "EnrollmentStatus", "Enrollment Status"),
                 F("StudentRegistration", "RegistrationCode", "Last Registration Code"),
                 F("StudentRegistration", "RegistrationDate", "Date", Fmt("date_us")),
                 F("StudentRegistration", "WithdrawlReason", "Withdrawal Reason"),
                 F("LastSchool", "SchoolName", "Last School", Fmt("trim")), T("Action", "Disable")],
                [Condition("Student", "EnrollmentStatus", "not_in", "{{ENROLLED_STATUS_CODES}}"), left_cond],
                distinct=True, sort=["Last Name", "First Name"])
    staff = query("Account shutoff - staff.csv", ["Employee"], [],
                  [F("Employee", "EmployeeNumber", "Employee Number", Fmt("trim")),
                   F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                   C("Email", EMAIL("Employee", "staff")), C("Username", USER("Employee", "staff")),
                   F("Employee", "TerminationDate", "Termination Date", Fmt("date_us")), T("Action", "Disable")],
                  [Condition("Employee", "TerminationDate", "raw",
                             "Employee.TerminationDate BETWEEN " + SINCE + " AND CAST(GETDATE() AS DATE)")],
                  sort=["Last Name"])
    gs = query("Account shutoff - Google suspend.csv", ["Student"], [],
               [C("Email Address [Required]", EMAIL("Student", "student")), T("New Status [UPLOAD ONLY]", "Suspended")],
               [Condition("Student", "EnrollmentStatus", "not_in", "{{ENROLLED_STATUS_CODES}}"), left_cond], distinct=True)
    gs.union_parts = [query("Staff part", ["Employee"], [],
                            [C("Email Address [Required]", EMAIL("Employee", "staff")),
                             T("New Status [UPLOAD ONLY]", "Suspended")],
                            [Condition("Employee", "TerminationDate", "raw",
                                       "Employee.TerminationDate BETWEEN " + SINCE + " AND CAST(GETDATE() AS DATE)")],
                            distinct=True)]
    return {
        "id": "account_shutoff", "name": "Account shutoff (students who left, staff who were terminated)",
        "works_with": "Google Workspace (bulk update), Active Directory (Disable-ADUsers.ps1), Microsoft Entra, Apple "
                      "School Manager and any app you remove leavers from",
        "description": "Students who are no longer enrolled and had an enrollment change in the last N days (District "
                       "Settings), with their last registration code, date, withdrawal reason and school, and staff "
                       "whose termination date falls in the last N days. Also a Google Admin bulk-update file that "
                       "suspends those accounts, and Disable-ADUsers.ps1, which previews first and only DISABLES "
                       "accounts (never deletes). Always review the list before acting on it - a student entered "
                       "with the wrong status would be on it.",
        "spec_url": "https://support.google.com/a/answer/40057",
        "delivery": "Review, then Google Admin > Users > Bulk update; run Disable-ADUsers.ps1; remove in other apps",
        "requires": ["ENROLLED_STATUS_CODES", "SHUTOFF_DAYS"],
        "static_files": {"Disable-ADUsers.ps1": DISABLE_SCRIPT},
        "confirm_with_vendor": "Check the Google file against Admin console > Users > Bulk update > Download blank "
                               "CSV template; the status column name has changed before.",
        "files": [f("shutoff_students.csv", stu), f("shutoff_staff.csv", staff),
                  f("shutoff_google_suspend.csv", gs, "students + staff")],
    }


ROUND4_PLATFORMS = [talkingpoints, remind, renaissance, assessment_demographics, college_board, sped_case,
                    health_office, alexandria, id_cards, substitutes, devices, dual_enrollment, cte_testing,
                    account_shutoff]

ROUND4_RULES = {
    "talkingpoints": {"files": {
        "tp_classes.csv": R(["Class Name", "Class ID"], ["Class Name", "Class ID"]),
        "tp_students.csv": R(["Student ID", "Student First Name", "Student Last Name", "Contact First Name",
                              "Language"], [], {"Contact Phone": "phone10", "Contact Email": "email"}),
        "tp_staff.csv": R(["First Name", "Last Name", "Email"], ["Email"],
                          {"Email": "email", "Non-Rostered Staff": "yn"}),
        "tp_admins.csv": R(["First Name", "Last Name", "Email"], ["Email"], {"Email": "email"})}},
    "remind": {"files": {
        "schools.csv": R(["school_id", "school_name"], ["school_id"], {"school_name": "maxlen:60"}),
        "classes.csv": R(["class_id", "school_id", "class_name"], ["class_id"], {"class_name": "maxlen:255"}),
        "enrollments.csv": R(["class_id", "user_id"], [("class_id", "user_id")],
                             {"class_role": "enum:owner|participant"}),
        "users.csv": R(["user_id", "first_name", "last_name"], ["user_id"],
                       {"grade": "enum:PK|KG|01|02|03|04|05|06|07|08|09|10|11|12|Other", "dob": "date_us"}),
        "school_enrollments.csv": R(["school_id", "user_id", "school_role"], [("school_id", "user_id", "school_role")],
                                    {"school_role": "enum:participant|staff|administrator"})},
        "refs": [["classes.csv", "school_id", "schools.csv", "school_id"],
                 ["enrollments.csv", "class_id", "classes.csv", "class_id"],
                 ["enrollments.csv", "user_id", "users.csv", "user_id"],
                 ["users.csv", "parent_id_1", "users.csv", "user_id"],
                 ["users.csv", "parent_id_2", "users.csv", "user_id"],
                 ["school_enrollments.csv", "user_id", "users.csv", "user_id"],
                 ["school_enrollments.csv", "school_id", "schools.csv", "school_id"]]},
    "renaissance": {"files": {
        "renaissance_roster.csv": R(["Student ID", "Student Last Name", "Student First Name", "Grade", "Class",
                                     "Teacher ID"], [("Student ID", "Class")], {"Birthdate": "date_us",
                                                                                "Teacher Email": "email"}),
        "renaissance_demographics.csv": R(["Student ID"], ["Student ID"],
                                          {"Special Education": "yn", "Section 504": "yn", "Gifted": "yn"})}},
    "assessment_demographics": {"files": {
        "assessment_demographics.csv": R(["Student ID", "First Name", "Last Name", "Grade"], ["Student ID"],
                                         {"Birth Date": "date_us", "Special Education": "yn", "Section 504": "yn",
                                          "Gifted": "yn", "Student Email": "email"}),
        "assessment_roster.csv": R(["Student ID", "Class ID"], [("Student ID", "Class ID")])},
        "refs": [["assessment_roster.csv", "Student ID", "assessment_demographics.csv", "Student ID"]]},
    "college_board": {"files": {
        "ssor_registration.csv": R(["Testing AI Code", "First Name", "Last Name", "Date of Birth", "Gender", "Grade",
                                    "Test", "School Student ID"], ["School Student ID"],
                                   {"Testing AI Code": "digits", "First Name": "maxlen:20", "Middle Initial": "maxlen:1",
                                    "Last Name": "maxlen:35", "Date of Birth": "date_us", "Gender": "enum:F|M|A",
                                    "Grade": "enum:6|7|8|9|10|11|12|N|1C|2C", "Test": "enum:PNM|P89|P10|SAT",
                                    "School Student ID": "maxlen:30"})}},
    "sped_case": {"files": {
        "sped_students.csv": R(["Student ID", "First Name", "Last Name", "Birth Date"], ["Student ID"],
                               {"Birth Date": "date_us", "Guardian Email": "email", "Guardian Phone": "phone10"}),
        "sped_schedules.csv": R(["Student ID", "Course Code"]),
        "sped_staff.csv": R(["Staff ID", "First Name", "Last Name"], [], {"Email": "email"})},
        "refs": [["sped_schedules.csv", "Student ID", "sped_students.csv", "Student ID"]]},
    "health_office": {"files": {
        "health_students.csv": R(["Student ID", "First Name", "Last Name", "Birth Date"], ["Student ID"],
                                 {"Birth Date": "date_us", "Last Physical": "date_us", "Guardian Phone": "phone10"}),
        "health_immunizations.csv": R(["Student ID", "Vaccine Code", "Date Given"], [], {"Date Given": "date_us"}),
        "health_conditions.csv": R(["Student ID", "Condition Code"])},
        "refs": [["health_immunizations.csv", "Student ID", "health_students.csv", "Student ID"],
                 ["health_conditions.csv", "Student ID", "health_students.csv", "Student ID"]]},
    "alexandria": {"files": {"alexandria_patrons.csv": R(["Barcode", "Last Name", "First Name", "Site"], ["Barcode"],
                                                         {"Email": "email", "Birthdate": "date_us"})}},
    "id_cards": {"files": {"id_cards.csv": R(["ID Number", "First Name", "Last Name", "Role"], [("ID Number", "Role")])}},
    "substitutes": {"files": {
        "sub_employees.csv": R(["Employee ID", "First Name", "Last Name"], ["Employee ID"],
                               {"Email": "email", "Phone": "phone10", "Start Date": "date_us", "Active": "yn"}),
        "sub_schools.csv": R(["School Code", "School Name"], ["School Code"])},
        "refs": [["sub_employees.csv", "School Code", "sub_schools.csv", "School Code"]]},
    "devices": {"files": {"device_students.csv": R(["Student ID", "First Name", "Last Name"], ["Student ID"],
                                                   {"Email": "email", "Guardian Email": "email"})}},
    "dual_enrollment": {"files": {"dual_enrollment.csv": R(["Student ID", "First Name", "Last Name", "Birth Date",
                                                            "Course Code"], [("Student ID", "Course Code", "Period")],
                                                           {"Birth Date": "date_us", "Guardian Email": "email"})}},
    "cte_testing": {"files": {"cte_roster.csv": R(["Student ID", "First Name", "Last Name", "Course Code"],
                                                  [], {"Email": "email",
                                                                                    "Birth Date": "date_us"})}},
    "account_shutoff": {"files": {
        "shutoff_students.csv": R(["Student ID", "Username"], ["Student ID"], {"Email": "email"}),
        "shutoff_staff.csv": R(["Employee Number", "Username"], [], {"Email": "email"}),
        "shutoff_google_suspend.csv": R(["Email Address [Required]"], ["Email Address [Required]"],
                                        {"Email Address [Required]": "email"})}},
}
ROUND4_CATEGORIES = {
    "talkingpoints": "Family communication", "remind": "Family communication",
    "renaissance": "Assessment & testing", "assessment_demographics": "Assessment & testing",
    "college_board": "Assessment & testing", "cte_testing": "Assessment & testing",
    "sped_case": "Student support & behavior", "health_office": "Student support & behavior",
    "alexandria": "School operations & safety", "id_cards": "School operations & safety",
    "substitutes": "School operations & safety", "devices": "School operations & safety",
    "dual_enrollment": "College, career & athletics", "account_shutoff": "Rostering & accounts",
}
