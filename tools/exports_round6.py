# Vendor packages, round 6 - executed inside tools/make_exports.py after exports_round5.py (shares all helpers).
# SEAS Education, UniteGPS, Level All, Canopy Anywhere, DRC BEACON, NAEP, YellowFolder, Parchment,
# Glimpse K12 and Summit K12.

import copy as _copy

NO_COMMA = Fmt("replace", ",", "")          # DRC BEACON allows no commas in any field
BEACON_GRADES = "02,03,04,05,06,07,08"
NAEP_GRADES = "04,08,12"
SEC_6_12 = "06,07,08,09,10,11,12"


def _rename(platform: dict, pid: str, name: str, prefix_from: str, prefix_to: str, file_map: dict) -> dict:
    """Copy a built package under a new id / name with new file names."""
    p = _copy.deepcopy(platform)
    p["id"], p["name"] = pid, name
    for fe in p["files"]:
        new = file_map.get(fe["file"], fe["file"])
        fe["query"]["name"] = fe["query"].get("name", "").replace(prefix_from, prefix_to).replace(fe["file"], new)
        fe["file"] = new
    return p


def _rename_rules(pid_from: str, file_map: dict) -> dict:
    src = RULES.get(pid_from) or ROUND4_RULES.get(pid_from) or {}  # noqa: F821
    out = {"files": {file_map.get(k, k): v for k, v in (src.get("files") or {}).items()}}
    if src.get("refs"):
        out["refs"] = [[file_map.get(a, a), b, file_map.get(c, c), d] for a, b, c, d in src["refs"]]
    return out


# ================================================================= SEAS Education (Attain IEP, CLASS, Medicaid)
SEAS_FILES = {"sped_students.csv": "seas_students.csv", "sped_schedules.csv": "seas_schedules.csv",
              "sped_staff.csv": "seas_staff.csv"}


def seas():
    p = _rename(sped_case(), "seas", "SEAS Education (Attain IEP, CLASS, Medicaid claiming)", "SPED - ",  # noqa: F821
                "SEAS - ", SEAS_FILES)
    p["works_with"] = "SEAS Attain / SEAS IEP, CLASS assessments, Behavior Plus and school-based Medicaid claiming"
    p["description"] = ("The nightly SIS feed SEAS uses: every enrolled student (referrals start in general "
                        "education) with demographics, State ID (MSIS), SAM SPED status, homeroom, address and "
                        "primary guardian; live class schedules (so teachers can open their students' plans); and "
                        "active staff with emails (SEAS user names). SEAS doesn't publish a fixed layout - their "
                        "implementation team maps these columns. Contains protected special-education data: send "
                        "only under your SEAS data agreement. " + CONTACT_NOTE)
    p["spec_url"] = "https://www.seaseducation.com/"
    p["delivery"] = "SEAS-provided SFTP, nightly (ask your SEAS implementation contact for the host and folder)"
    p["confirm_with_vendor"] = ("SEAS maps the columns during implementation. Send them one night's files and ask "
                                "whether they also want Medicaid IDs or service providers from another system.")
    return p


# ================================================================= UniteGPS (transportation)
UNITE_FILES = {"transportation_students.csv": "unitegps_students.csv"}


def unitegps():
    p = _rename(transportation(), "unitegps", "UniteGPS (bus routing, driver app, parent notifications)",  # noqa: F821
                "Transportation - ", "UniteGPS - ", UNITE_FILES)
    schools = query("UniteGPS - schools.csv", ["SchoolDef"], [],
                    [F("SchoolDef", "SchoolCode", "School Code"), F("SchoolDef", "SchoolName", "School Name", Fmt("trim")),
                     F("SchoolDef", "LowestGradeTaught", "Low Grade"), F("SchoolDef", "HighestGradeTaught", "High Grade")],
                    [Condition("SchoolDef", "ActiveFlag", "eq", "1")], sort=["School Name"])
    p["files"].append(f("unitegps_schools.csv", schools))
    p["works_with"] = "UniteGPS route planning, driver navigation app and parent bus notifications"
    p["description"] = ("UniteGPS's daily roster sync: one row per enrolled student with home address (and "
                        "latitude/longitude when SAM has them), grade, school, transportation code, AM/PM method, "
                        "bus zone, special-needs flags and the primary guardian's name, phone and email (for parent "
                        "notifications), plus the school list. Students who leave drop out of the next file, which "
                        "UniteGPS flags as disenrolled. UniteGPS sets up the feed with you - they don't publish a "
                        "fixed layout. " + CONTACT_NOTE)
    p["spec_url"] = "https://unitegps.com/feeds/blog/sis-integration-k-12"
    p["delivery"] = "SFTP or file drop agreed with your UniteGPS implementation contact (daily)"
    p["confirm_with_vendor"] = ("Ask UniteGPS for their field-mapping sheet and how students are matched (Student ID). "
                                "Rename headings in Step 3 to match it.")
    return p


# ================================================================= Level All (college & career readiness)
def levelall():
    students = query("Level All - students.csv", STU_SCH_T + HR_LIVE_T[:1] + COUNSELOR_T,
                     STU_SCH_L + HR_LIVE_L[:1] + COUNSELOR_L,
                     stu_basic() + [F("Student", "StateCode", "State ID (MSIS)"),
                                    C("Email", EMAIL("Student", "student")),
                                    F("Student", "ADAGrade", "Grade"),
                                    F("Student", "OriginalGradDate", "Graduation Year", Fmt("year")),
                                    F("Student", "DOB", "Birth Date", Fmt("date_us")),
                                    F("SchoolDef", "SchoolCode", "School Code"), school_name(),
                                    C("Counselor Email", EMAIL("Counselor", "staff"))],
                     STU_C + [Condition("Student", "ADAGrade", "in", SEC_6_12)], distinct=True,
                     sort=["School", "Last Name", "First Name"])
    staff = staff_q("Level All - staff.csv",
                    [F("Employee", "EmployeeNumber", "Staff ID", Fmt("trim")),
                     F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                     C("Email", EMAIL("Employee", "staff")), F("SchoolDef", "SchoolCode", "School Code"), school_name()],
                    faculty_only=True)
    return {
        "id": "levelall", "name": "Level All (college & career readiness)",
        "works_with": "Level All student app and educator dashboard (MDE-supported college and career readiness tool)",
        "description": "Students in grades 6-12 with ID, MSIS State ID, school email, grade, graduation year, birth "
                       "date, school and counselor email, plus active faculty with emails for educator dashboard "
                       "access. Many districts connect Level All through Clever or ClassLink instead - if yours "
                       "does, you don't need this package.",
        "spec_url": "https://www.levelall.com/",
        "delivery": "Level All onboarding (file upload or SFTP agreed with Level All), or Clever / ClassLink",
        "confirm_with_vendor": "Level All doesn't publish a CSV layout. Ask your Level All contact whether they "
                               "roster through Clever/ClassLink or files, and which columns they need.",
        "files": [f("levelall_students.csv", students, "grades 6-12"), f("levelall_staff.csv", staff)],
    }


# ================================================================= Canopy Anywhere (mental wellness, grades 6-12)
def canopy():
    ct, cl, (sc, ci, pn, em) = contact_chain()
    students = query("Canopy Anywhere - students.csv",
                     STU_SCH_T + HR_LIVE_T[:1] + COUNSELOR_T + ct, STU_SCH_L + HR_LIVE_L[:1] + COUNSELOR_L + cl,
                     stu_basic() + [C("Student Email", EMAIL("Student", "student")), F("Student", "ADAGrade", "Grade"),
                                    F("SchoolDef", "SchoolCode", "School Code"), school_name(),
                                    C("Counselor Name", P("Counselor", "FirstName", Fmt("trim")), X(" "),
                                      P("Counselor", "LastName", Fmt("trim"))),
                                    C("Counselor Email", EMAIL("Counselor", "staff")),
                                    C("Parent Name", P(ci, "FirstName", Fmt("trim")), X(" "), P(ci, "LastName", Fmt("trim"))),
                                    F(em, "Address", "Parent Email", Fmt("trim"), Fmt("lower")),
                                    phone_col("Parent Phone", pn), F(ci, "PrimaryLanguage", "Parent Language")],
                     STU_C + [Condition("Student", "ADAGrade", "in", SEC_6_12)], distinct=True,
                     sort=["School", "Last Name", "First Name"])
    counselors = query("Canopy Anywhere - counselors.csv", EMP_SCH_T + [("stuHRTeacher", "stuHRTeacher")],
                       EMP_SCH_L + [("Employee", "EmployeeID", "stuHRTeacher", "CounselorID", "INNER",
                                     [Condition("stuHRTeacher", "ScheduleID", "raw", LIVE_HR)])],
                       [F("Employee", "EmployeeNumber", "Staff ID", Fmt("trim")),
                        F("Employee", "FirstName", "First Name", Fmt("trim")),
                        F("Employee", "LastName", "Last Name", Fmt("trim")),
                        C("Email", EMAIL("Employee", "staff")), school_name()],
                       STAFF_ACTIVE, distinct=True, sort=["Last Name"])
    return {
        "id": "canopy", "name": "Canopy Anywhere (student mental wellness)",
        "works_with": "Canopy Children's Solutions - Canopy Anywhere weekly wellness lessons and HOPE Scale screener",
        "description": "Students in grades 6-12 with school email (lessons are emailed to students), grade, school, "
                       "assigned counselor (low screener scores prompt a counselor check-in) and the primary "
                       "parent's name, email, phone and language (weekly parent emails), plus the counselor list. "
                       "Participation is optional for families - limit the file to participating schools with the "
                       "Schools: button and follow Canopy's consent process. " + CONTACT_NOTE,
        "spec_url": "https://mycanopy.org/solutions/canopy-anywhere/",
        "delivery": "Secure upload or SFTP arranged with Canopy Children's Solutions",
        "requires": CONTACT_REQ,
        "confirm_with_vendor": "Canopy doesn't publish a file layout. Confirm the columns, the grades taking part "
                               "and how parent opt-outs are handled before the first upload.",
        "files": [f("canopy_students.csv", students, "grades 6-12"), f("canopy_counselors.csv", counselors)],
    }


# ================================================================= DRC BEACON (Mississippi through-year assessment)
def _beacon_cols(teacher_alias, roster_name):
    return [F("Student", "StateCode", "State Student ID", Fmt("trim"), Fmt("left", "15")),
            F("Student", "LastName", "Student Last Name", Fmt("trim"), NO_COMMA, Fmt("left", "35")),
            F("Student", "FirstName", "Student First Name", Fmt("trim"), NO_COMMA, Fmt("left", "35")),
            F(teacher_alias, "FirstName", "Teacher First Name", Fmt("trim"), NO_COMMA, Fmt("left", "35")),
            F(teacher_alias, "LastName", "Teacher Last Name", Fmt("trim"), NO_COMMA, Fmt("left", "35")),
            C("Teacher Email", EMAIL(teacher_alias, "staff")),
            roster_name]


def drc_beacon():
    def clean(n):  # only letters, digits, space, - and ' are allowed; pieces are cut so the name fits 50
        return [Fmt("trim"), Fmt("replace", ",", ""), Fmt("replace", "&", "and"), Fmt("replace", "/", "-"),
                Fmt("replace", ".", ""), Fmt("replace", "#", ""), Fmt("replace", "(", ""), Fmt("replace", ")", ""),
                Fmt("left", str(n))]
    class_name = C("Roster Name", P("Course", "LongName", *clean(30)), X(" P"), P("ScheduleFramework", "Period", *clean(3)),
                   X(" "), P("Teacher", "LastName", *clean(14)))
    classes = query("DRC BEACON - class rosters", ROS_T + [("Teacher", "Employee")],
                    ROS_L + [("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "INNER")],
                    _beacon_cols("Teacher", class_name),
                    ROS_C + [Condition("Student", "ADAGrade", "in", BEACON_GRADES),
                             Condition("Course", "CoreCourse", "in", "1,Y")],
                    distinct=True, sort=["Roster Name", "Student Last Name"])
    hr_name = C("Roster Name", X("Homeroom "), P("HomeroomTeacher", "LastName", *clean(30)), X(" Gr "),
                P("Student", "ADAGrade", *clean(3)))
    homerooms = query("DRC BEACON - homeroom rosters", STU_T + HR_LIVE_T,
                      STU_L + [("Student", "StudentID", "stuHRTeacher", "StudentID", "INNER",
                                [Condition("stuHRTeacher", "ScheduleID", "raw", LIVE_HR)]),
                               ("stuHRTeacher", "HRTeacherID", "HomeroomTeacher", "EmployeeID", "INNER")],
                      _beacon_cols("HomeroomTeacher", hr_name),
                      STU_C + [Condition("Student", "ADAGrade", "in", BEACON_GRADES)],
                      distinct=True, sort=["Roster Name", "Student Last Name"])
    return {
        "id": "drc_beacon", "name": "DRC BEACON (roster import)",
        "works_with": "DRC BEACON / DRC INSIGHT Portal > Student Management > Rosters > Import Rosters",
        "description": "DRC BEACON's Roster Import layout exactly: State Student ID (MSIS), Student Last Name, "
                       "Student First Name, Teacher First Name, Teacher Last Name, Teacher Email, Roster Name - CSV "
                       "with a header row and no commas in any field (removed for you). Two choices: class rosters "
                       "(core courses, grades 2-8, named 'Course P# Teacher') or homeroom rosters (better for "
                       "elementary). Students must already be in the Portal (loaded from MSIS) and each Teacher Email "
                       "must match that teacher's DRC user name - if your DRC user names aren't the staff email "
                       "pattern, fix them in District Settings first. To update a roster, keep the same teacher email "
                       "and roster name.",
        "spec_url": "https://www.drcbeacontraining.com/manage-students/importing-rosters/roster-import-layout-instructions/",
        "delivery": "Upload in the DRC INSIGHT Portal (Import Rosters), then check the error report",
        "confirm_with_vendor": "Check the grades your district tests in BEACON this year and whether teachers "
                               "already exist as Portal users (Upload Multiple Users uses DRC's own layout).",
        "files": [f("beacon_class_rosters.csv", classes, "core classes, grades 2-8"),
                  f("beacon_homeroom_rosters.csv", homerooms, "homerooms, grades 2-8")],
    }


# ================================================================= NAEP (student list / E-File)
def naep():
    at, al, ad = address_chain("Student", "StudentID", OT_STU)  # noqa: F821
    sd = ("CASE WHEN LTRIM(RTRIM(ISNULL(Student.SPEDStatus, ''))) IN ('', '0', 'N') THEN 'No, not SD' "
          "ELSE 'Yes, IEP' END")
    efile = query("NAEP - student list (E-File)", STU_SCH_T + HR_LIVE_T + at, STU_SCH_L + HR_LIVE_L + al,
                  [F("Student", "StateCode", "State unique Student ID", Fmt("trim")),
                   F("Student", "FirstName", "Student First Name", Fmt("trim")),
                   F("Student", "MiddleName", "Student Middle Name", Fmt("trim")),
                   F("Student", "LastName", "Student Last Name", Fmt("trim")),
                   F("Student", "ADAGrade", "Grade in School", Fmt("strip_zeros")),
                   C("Homeroom or other Locator", P("HomeroomTeacher", "LastName", Fmt("trim"))),
                   RAW("Month of Birth", "MONTH(Student.DOB)"), F("Student", "DOB", "Year of Birth", Fmt("year")),
                   F("Student", "GenderCode", "Sex"), F("Student", "RaceCode", "Race/Ethnicity"),
                   F("Student", "FoodServiceCode", "National School Lunch Program (NSLP)"),
                   RAW("Students with Disabilities (SD)", sd),
                   T("English Learner (EL)"), T("On-Break Indicator"),
                   F(ad, "ZipCode", "Student ZIP Code", Fmt("trim"))],
                  STU_C + [Condition("Student", "ADAGrade", "in", NAEP_GRADES)], distinct=True,
                  sort=["Grade in School", "Student Last Name", "Student First Name"])
    return {
        "id": "naep", "name": "NAEP student list (E-File)",
        "works_with": "MyNAEP > Submit Student List (sampled schools only, fall) and the January list update",
        "description": "Every enrolled student in the NAEP grade(s) (4, 8 and 12 - remove the grades your school "
                       "wasn't sampled for in Step 4) in the NAEP E-File one-column race/ethnicity layout: State "
                       "unique Student ID (MSIS), first / middle / last name, Grade in School, homeroom as the "
                       "locator, Month and Year of Birth, Sex, Race/Ethnicity, NSLP, SD (Yes, IEP / No, not SD), EL, "
                       "On-Break Indicator and ZIP. NAEP accepts your school's own codes for Sex, Race/Ethnicity and "
                       "NSLP - you match each SAM code to NAEP's categories when you upload. SAM has no general EL "
                       "flag, so the EL column is blank: fill it from your EL records (Yes, EL / No, not EL / No, "
                       "formerly EL). Save the CSV as Excel (.xlsx) for MyNAEP.",
        "spec_url": "https://nces.ed.gov/nationsreportcard/participating/",
        "delivery": "MyNAEP (mynaep.com) > Submit Student List - upload as Excel",
        "requires": ["OWNER_TYPE_STUDENT"],
        "confirm_with_vendor": "Use this year's E-File template from MyNAEP and check the column order and the "
                               "race/ethnicity version (one, two or six columns) your school was given.",
        "files": [f("naep_student_list.csv", efile, "grades 4, 8, 12 - save as .xlsx")],
    }


# ================================================================= YellowFolder (records management)
def yellowfolder():
    students = query("YellowFolder - students.csv", STU_SCH_T, STU_SCH_L,
                     stu_basic() + [F("Student", "MiddleName", "Middle Name", Fmt("trim")),
                                    F("Student", "StateCode", "State ID (MSIS)"),
                                    F("Student", "DOB", "Birth Date", Fmt("date_us")),
                                    F("Student", "ADAGrade", "Grade"),
                                    F("Student", "OriginalGradDate", "Graduation Year", Fmt("year")),
                                    F("SchoolDef", "SchoolCode", "School Code"), school_name(),
                                    F("Student", "EnrollmentStatus", "Enrollment Status"),
                                    F("Student", "FinalGraduationDate", "Graduation Date", Fmt("date_us"))],
                     [Condition("stuSchool", "PrimarySchoolFlag", "eq", "1")], distinct=True,
                     sort=["School", "Last Name", "First Name"])
    staff = query("YellowFolder - staff.csv", EMP_SCH_T, EMP_SCH_L,
                  [F("Employee", "EmployeeNumber", "Employee ID", Fmt("trim")),
                   F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                   C("Email", EMAIL("Employee", "staff")), school_name(),
                   F("Employee", "HireDate", "Hire Date", Fmt("date_us")),
                   F("Employee", "TerminationDate", "Termination Date", Fmt("date_us"))],
                  [Condition("empSchool", "PrimarySchoolFlag", "eq", "1")], distinct=True, sort=["Last Name"])
    return {
        "id": "yellowfolder", "name": "YellowFolder (digital student & staff records)",
        "works_with": "YellowFolder by Intellinetics - cumulative folders, scanning and records retention",
        "description": "Index files so scanned documents land in the right folder: EVERY student with a primary "
                       "school - current, withdrawn and graduated (records outlive enrollment) - with IDs, MSIS, "
                       "birth date, grade, graduation year, school, enrollment status and graduation date, and every "
                       "employee with hire and termination dates for HR folders. Use the Schools: button or a "
                       "filter in Step 4 if YellowFolder only wants recent years.",
        "spec_url": "https://yellowfolder.com/",
        "delivery": "SFTP or upload agreed with YellowFolder support (often nightly)",
        "confirm_with_vendor": CONFIRM + " Ask whether they want withdrawn and graduated students and how far back.",  # noqa: F821
        "files": [f("yellowfolder_students.csv", students, "all students, also withdrawn"),
                  f("yellowfolder_staff.csv", staff, "all employees")],
    }


# ================================================================= Parchment (transcripts & diplomas)
def parchment():
    at, al, ad = address_chain("Student", "StudentID", OT_STU)  # noqa: F821
    cols = [F("Student", "StudentCode", "Student ID", Fmt("trim")),
            F("Student", "FirstName", "First Name", Fmt("trim")),
            F("Student", "MiddleName", "Middle Name", Fmt("trim")),
            F("Student", "LastName", "Last Name", Fmt("trim")),
            F("Student", "DOB", "Date of Birth", Fmt("date_us")),
            F("Student", "OriginalGradDate", "Graduation Year", Fmt("year")),
            C("Email", EMAIL("Student", "student")),
            F(ad, "AddrLine1", "Address", Fmt("trim")), F(ad, "City", "City", Fmt("trim")),
            F(ad, "State", "State"), F(ad, "ZipCode", "Zip")]
    current = query("Parchment - current students", STU_SCH_T + at, STU_SCH_L + al, cols,
                    STU_C + [Condition("Student", "ADAGrade", "in", HS_GRADES)], distinct=True,  # noqa: F821
                    sort=["Last Name", "First Name"])
    grads = query("Parchment - recent graduates", STU_SCH_T + at, STU_SCH_L + al, cols,
                  [Condition("stuSchool", "PrimarySchoolFlag", "eq", "1"),
                   Condition("Student", "FinalGraduationDate", "last_days", "400")], distinct=True,
                  sort=["Last Name", "First Name"])
    return {
        "id": "parchment", "name": "Parchment (transcripts, diplomas & records requests)",
        "works_with": "Parchment Send K-12 > Students > Roster upload (registration codes)",
        "description": "Parchment's student roster: the five required fields (First Name, Last Name, Date of "
                       "Birth, Student ID, Graduation Year) plus middle name, email (needed to email registration "
                       "codes) and mailing address. One file for students in grades 9-12, one for graduates of "
                       "the last ~13 months (they still order transcripts). Parchment lets you match columns when "
                       "you upload, so the order isn't fixed - tick 'file has a header row' and choose Comma "
                       "Delimited.",
        "spec_url": "https://www.parchment.com/wp-content/uploads/Roster-upload-and-reg-code_Parchment1.pdf",
        "delivery": "Parchment Send K-12 (exchange.parchment.com) > Students > Upload roster",
        "requires": ["OWNER_TYPE_STUDENT"],
        "files": [f("parchment_students.csv", current, "grades 9-12"),
                  f("parchment_graduates.csv", grads, "graduated in the last ~13 months")],
    }


# ================================================================= Glimpse K12 (ed-tech usage & ROI analytics)
def glimpse():
    students = query("Glimpse K12 - students.csv", STU_SCH_T, STU_SCH_L,
                     stu_basic() + [C("Email", EMAIL("Student", "student")), F("Student", "ADAGrade", "Grade"),
                                    F("SchoolDef", "SchoolCode", "School Code"), school_name()] + demographic_cols(),  # noqa: F821
                     STU_C, distinct=True, sort=["School", "Last Name"])
    staff = staff_q("Glimpse K12 - staff.csv",
                    [F("Employee", "EmployeeNumber", "Staff ID", Fmt("trim")),
                     F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                     C("Email", EMAIL("Employee", "staff")), F("SchoolDef", "SchoolCode", "School Code"), school_name(),
                     F("Employee", "FacultyFlag", "Teacher", Fmt("yes_no"))])
    enroll = query("Glimpse K12 - enrollments.csv", ROS_T + [("Teacher", "Employee")],
                   ROS_L + [("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "LEFT")],
                   [F("Student", "StudentCode", "Student ID", Fmt("trim")),
                    F("ScheduleFramework", "ScheduleFrameworkID", "Section ID"),
                    F("Course", "CourseCode", "Course Code"), F("Course", "LongName", "Course Name", Fmt("trim")),
                    F("ScheduleFramework", "Period", "Period"),
                    C("Teacher Email", EMAIL("Teacher", "staff"))], ROS_C, distinct=True)
    return {
        "id": "glimpse", "name": "Glimpse K12 (ed-tech usage & ROI analytics)",
        "works_with": "Glimpse K12 by Level Data - links app usage to students, teachers, classes and outcomes",
        "description": "Who uses each program: enrolled students with school email (matched to app logins), grade, "
                       "school and demographics for equity reports (gender, race, home language, SPED / 504 / gifted "
                       "Y/N, meal status), active staff with emails, and live class enrollments with the teacher. "
                       "If Glimpse can take OneRoster instead, the OneRoster 1.1 package has the same data. Contains "
                       "protected program data - share only under your agreement with Glimpse / Level Data.",
        "spec_url": "https://www.glimpsek12.com/",
        "delivery": "SFTP set up with Glimpse K12 / Level Data (or OneRoster)",
        "confirm_with_vendor": CONFIRM,  # noqa: F821
        "files": [f("glimpse_students.csv", students), f("glimpse_staff.csv", staff),
                  f("glimpse_enrollments.csv", enroll)],
    }


# ================================================================= Summit K12 (ELD / literacy, OneRoster)
def summitk12():
    p = _copy.deepcopy(oneroster())  # noqa: F821
    p["id"], p["name"] = "summitk12", "Summit K12 (OneRoster 1.1 CSV)"
    for fe in p["files"]:
        fe["query"]["name"] = fe["query"].get("name", "").replace("OneRoster - ", "Summit K12 - ")
    p["works_with"] = "Summit K12 (Reach Higher / ELD, literacy and science programs) - OneRoster integration"
    p["description"] = ("Summit K12 rosters through OneRoster: this is the standard OneRoster 1.1 bulk CSV set "
                        "(orgs, academicSessions, courses, classes, users, enrollments, demographics) plus "
                        "manifest.csv, zipped together. Use the Schools: button to send only the schools using "
                        "Summit K12. If you already send OneRoster through ClassLink, connect Summit there instead.")
    p["spec_url"] = "https://support.summitk12.com/s/article/OneRoster-Integration-Admin-Guide"
    p["delivery"] = "Zip all files (with manifest.csv) and send to the SFTP Summit K12 provides, or ClassLink"
    p["confirm_with_vendor"] = ("Follow Summit K12's OneRoster Integration Admin Guide for the SFTP details and "
                                "whether they want only the classes using their program.")
    return p


ROUND6_PLATFORMS = [seas, unitegps, levelall, canopy, drc_beacon, naep, yellowfolder, parchment, glimpse, summitk12]

_BEACON_RULE = R(["State Student ID", "Teacher Email", "Roster Name"], [("State Student ID", "Teacher Email", "Roster Name")],
                 {"State Student ID": "maxlen:15", "Student Last Name": "maxlen:35", "Student First Name": "maxlen:35",
                  "Teacher First Name": "maxlen:35", "Teacher Last Name": "maxlen:35", "Teacher Email": "email",
                  "Roster Name": "maxlen:50"})
ROUND6_RULES = {
    "seas": _rename_rules("sped_case", SEAS_FILES),
    "unitegps": _rename_rules("transportation", UNITE_FILES),
    "levelall": {"files": {
        "levelall_students.csv": R(["Student ID", "First Name", "Last Name", "Grade"], ["Student ID"],
                                   {"Email": "email", "Birth Date": "date_us", "Graduation Year": "year",
                                    "Counselor Email": "email"}),
        "levelall_staff.csv": R(["Staff ID", "First Name", "Last Name", "Email"], ["Email"], {"Email": "email"})}},
    "canopy": {"files": {
        "canopy_students.csv": R(["Student ID", "First Name", "Last Name", "Student Email"], ["Student ID"],
                                 {"Student Email": "email", "Counselor Email": "email", "Parent Email": "email",
                                  "Parent Phone": "phone10"}),
        "canopy_counselors.csv": R(["First Name", "Last Name", "Email"], [], {"Email": "email"})}},
    "drc_beacon": {"files": {"beacon_class_rosters.csv": _BEACON_RULE, "beacon_homeroom_rosters.csv": _BEACON_RULE}},
    "naep": {"files": {"naep_student_list.csv": R(
        ["State unique Student ID", "Student First Name", "Student Last Name", "Grade in School", "Month of Birth",
         "Year of Birth"], ["State unique Student ID"],
        {"Grade in School": "enum:4|8|12", "Month of Birth": "int", "Year of Birth": "year",
         "Students with Disabilities (SD)": "enum:Yes, IEP|No, not SD"})}},
    "yellowfolder": {"files": {
        "yellowfolder_students.csv": R(["Student ID", "First Name", "Last Name"], ["Student ID"],
                                       {"Birth Date": "date_us", "Graduation Date": "date_us"}),
        "yellowfolder_staff.csv": R(["Employee ID", "First Name", "Last Name"], [],
                                    {"Hire Date": "date_us", "Termination Date": "date_us"})}},
    "parchment": {"files": {
        "parchment_students.csv": R(["Student ID", "First Name", "Last Name", "Date of Birth", "Graduation Year"],
                                    ["Student ID"], {"Date of Birth": "date_us", "Graduation Year": "year",
                                                     "Email": "email"}),
        "parchment_graduates.csv": R(["Student ID", "First Name", "Last Name", "Date of Birth", "Graduation Year"],
                                     ["Student ID"], {"Date of Birth": "date_us", "Graduation Year": "year"})}},
    "glimpse": {"files": {
        "glimpse_students.csv": R(["Student ID", "First Name", "Last Name"], ["Student ID"], {"Email": "email"}),
        "glimpse_staff.csv": R(["Staff ID", "First Name", "Last Name"], [], {"Email": "email"}),
        "glimpse_enrollments.csv": R(["Student ID", "Section ID"], [("Student ID", "Section ID")],
                                     {"Teacher Email": "email"})},
        "refs": [["glimpse_enrollments.csv", "Student ID", "glimpse_students.csv", "Student ID"]]},
    "summitk12": RULES.get("oneroster11", {}),
}
ROUND6_DELIVERY = {"summitk12": {"zip": True, "zip_name": "summitk12_oneroster.zip"}}
ROUND6_CATEGORIES = {
    "seas": "Student support & behavior", "canopy": "Student support & behavior",
    "unitegps": "School operations & safety", "yellowfolder": "School operations & safety",
    "levelall": "College, career & athletics", "parchment": "College, career & athletics",
    "drc_beacon": "Assessment & testing", "naep": "Assessment & testing",
    "glimpse": "Rostering & accounts", "summitk12": "Rostering & accounts",
}
