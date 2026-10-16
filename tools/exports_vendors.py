# Vendor packages, round 3 - executed inside tools/make_exports.py after exports_more.py (shares all helpers).
# Apple School Manager, SchoolStatus, Active Directory, Microsoft Entra, PBIS Rewards, behavior apps (Hero /
# LiveSchool), Ellevation, payments, bus apps, web-filter parent reports, emergency / reunification, athletics,
# hall pass / ID kiosks, credit recovery, Scoir / MajorClarity, Adobe Admin Console, Zoom.

GRADE_PBIS = "KG=0; K=0; 01=1; 02=2; 03=3; 04=4; 05=5; 06=6; 07=7; 08=8; 09=9"
YN = "CASE WHEN {x} IN (1, '1', 'Y', 'T') THEN 'Y' ELSE 'N' END"


def TID(heading, alias, col="EmployeeID"):
    return C(heading, X("T"), P(alias, col))


def YNcol(heading, expr):
    return RAW(heading, YN.format(x=expr))


def PASSWORD(heading, alias, id_col):
    """District prefix + last 6 of the ID (users must change it at first sign-in)."""
    return C(heading, X("{{ACCOUNT_PASSWORD_PREFIX}}"), P(alias, id_col, Fmt("trim"), Fmt("right", "6")))


def school_name(alias="SchoolDef"):
    return F(alias, "SchoolName", "School", Fmt("trim"))


def stu_basic(prefix="Student"):
    return [F("Student", "StudentCode", f"{prefix} ID", Fmt("trim")),
            F("Student", "FirstName", "First Name", Fmt("trim")), F("Student", "LastName", "Last Name", Fmt("trim"))]


def guardian_cols(ci, pn, em):
    return [C("Guardian Name", P(ci, "FirstName", Fmt("trim")), X(" "), P(ci, "LastName", Fmt("trim"))),
            phone_col("Guardian Phone", pn), F(em, "Address", "Guardian Email", Fmt("trim"), Fmt("lower"))]


def staff_q(name, cols, extra_t=(), extra_l=(), faculty_only=False):
    return query(name, EMP_SCH_T + list(extra_t), EMP_SCH_L + list(extra_l), cols,
                 EMP_C if faculty_only else STAFF_ACTIVE, distinct=True, sort=["Last Name"] if any(
                     c.heading == "Last Name" for c in cols) else ())


# ================================================================= Apple School Manager
def apple_school_manager():
    locations = query("ASM - locations.csv", ["SchoolDef"], [],
                      [F("SchoolDef", "SchoolID", "location_id"), F("SchoolDef", "SchoolName", "location_name", Fmt("trim"))],
                      [Condition("SchoolDef", "ActiveFlag", "eq", "1")], sort=["location_name"])
    students = query("ASM - students.csv", STU_T, STU_L,
                     [F("Student", "StudentCode", "person_id", Fmt("trim")),
                      F("Student", "StudentCode", "person_number", Fmt("trim")),
                      F("Student", "FirstName", "first_name", Fmt("trim")), F("Student", "MiddleName", "middle_name", Fmt("trim")),
                      F("Student", "LastName", "last_name", Fmt("trim")), F("Student", "ADAGrade", "grade_level"),
                      C("email_address", EMAIL("Student", "student")), C("sis_username", USER("Student", "student")),
                      T("password_policy"), F("stuSchool", "SchoolID", "location_id")],
                     STU_C, distinct=True)
    staff = query("ASM - staff.csv", EMP_T, EMP_L,
                  [TID("person_id", "Employee"), F("Employee", "EmployeeNumber", "person_number", Fmt("trim")),
                   F("Employee", "FirstName", "first_name", Fmt("trim")), F("Employee", "MiddleName", "middle_name", Fmt("trim")),
                   F("Employee", "LastName", "last_name", Fmt("trim")), C("email_address", EMAIL("Employee", "staff")),
                   C("sis_username", USER("Employee", "staff")), F("empSchool", "SchoolID", "location_id")],
                  STAFF_ACTIVE, distinct=True)
    course_id = C("course_id", P("Schedule", "SchoolID"), X("-"), P("Course", "CourseCode", Fmt("trim")))
    courses = query("ASM - courses.csv", ["Course", "ScheduleCourse", "Schedule"],
                    [("Course", "CourseID", "ScheduleCourse", "CourseID", "INNER"),
                     ("ScheduleCourse", "ScheduleID", "Schedule", "ScheduleID", "INNER")],
                    [course_id, F("Course", "CourseCode", "course_number", Fmt("trim")),
                     F("Course", "LongName", "course_name", Fmt("trim")), F("Schedule", "SchoolID", "location_id")],
                    [LIVE], distinct=True)
    classes = query("ASM - classes.csv", SEC_T, SEC_L,
                    [F("ScheduleFramework", "ScheduleFrameworkID", "class_id"), class_title("class_number"),
                     C("course_id", P("Schedule", "SchoolID"), X("-"), P("Course", "CourseCode", Fmt("trim"))),
                     TID("instructor_id", "ScheduleFramework", "TeacherID"), T("instructor_id_2"), T("instructor_id_3"),
                     F("Schedule", "SchoolID", "location_id")],
                    [LIVE, Condition("ScheduleFramework", "TeacherID", "not_blank")], distinct=True)
    rosters = query("ASM - rosters.csv", ROS_T, ROS_L,
                    [C("roster_id", P("ScheduleRoster", "ScheduleFrameworkID"), X("-"),
                       P("Student", "StudentCode", Fmt("trim"))),
                     F("ScheduleRoster", "ScheduleFrameworkID", "class_id"),
                     F("Student", "StudentCode", "student_id", Fmt("trim"))],
                    ROS_C, distinct=True)
    return {
        "id": "apple_asm", "name": "Apple School Manager",
        "works_with": "Apple School Manager rostering (Managed Apple Accounts, Apple Classroom, Schoolwork) and the "
                      "MDMs that read it (Jamf School, Jamf Pro, Mosyle, Kandji)",
        "description": "Apple's six template files - locations, students, staff, courses, classes, rosters - zipped "
                       "together with no folders inside. Staff person_id has a T prefix so it never collides with a "
                       "student ID. password_policy is blank (Apple's default); put 4, 6 or 8 in Step 3 for "
                       "4-digit / 6-digit / 8-character passwords. Every upload must include all six files. "
                       "Apple School Manager also accepts OneRoster 1.1 - the OneRoster package works too.",
        "spec_url": "https://support.apple.com/guide/apple-school-manager/template-information-for-importing-data-axm46d50f6bf/web",
        "delivery": "Apple School Manager SFTP (Preferences > Directory sync gives the host, user and password); "
                    "put the zip in the Dropbox folder",
        "confirm_with_vendor": "Compare the header row with the templates you download from Apple School Manager "
                               "before the first upload - Apple requires the exact column names.",
        "files": [f("locations.csv", locations), f("students.csv", students), f("staff.csv", staff),
                  f("courses.csv", courses), f("classes.csv", classes), f("rosters.csv", rosters)],
    }


# ================================================================= SchoolStatus
def schoolstatus():
    users = query("SchoolStatus - users.csv", STU_T, STU_L,
                  [F("Student", "StudentCode", "sourcedId", Fmt("trim")), F("stuSchool", "SchoolID", "orgSourcedIds"),
                   T("role", "student"), F("Student", "FirstName", "givenName", Fmt("trim")),
                   F("Student", "LastName", "familyName", Fmt("trim")), C("email", EMAIL("Student", "student")),
                   T("sms"), T("phone"), T("agentSourcedIds"), F("Student", "ADAGrade", "grades"),
                   F("Student", "LangBackground", "language")],
                  STU_C, distinct=True)
    teachers = query("Teachers part", EMP_T, EMP_L,
                     [TID("sourcedId", "Employee"), F("empSchool", "SchoolID", "orgSourcedIds"), T("role", "teacher"),
                      F("Employee", "FirstName", "givenName", Fmt("trim")), F("Employee", "LastName", "familyName", Fmt("trim")),
                      C("email", EMAIL("Employee", "staff")), T("sms"), T("phone"), T("agentSourcedIds"), T("grades"),
                      T("language")], EMP_C, distinct=True)
    users.union_parts = [teachers]
    classes = query("SchoolStatus - classes.csv", SEC_T, SEC_L,
                    [F("ScheduleFramework", "ScheduleFrameworkID", "sourcedId"), class_title("title"),
                     F("Course", "LowGradeLevel", "grades"), T("location"), F("Schedule", "SchoolID", "schoolSourcedId"),
                     F("ScheduleFramework", "Period", "periods")],
                    [LIVE, Condition("ScheduleFramework", "TeacherID", "not_blank")], distinct=True)
    stu_enr = query("SchoolStatus - enrollments.csv", ROS_T, ROS_L,
                    [F("ScheduleRoster", "ScheduleFrameworkID", "classSourcedId"), F("Schedule", "SchoolID", "schoolSourcedId"),
                     F("Student", "StudentCode", "userSourcedId", Fmt("trim")), T("role", "student")],
                    ROS_C, distinct=True)
    tch_enr = query("Teachers part", SEC_T, SEC_L,
                    [F("ScheduleFramework", "ScheduleFrameworkID", "classSourcedId"),
                     F("Schedule", "SchoolID", "schoolSourcedId"), TID("userSourcedId", "ScheduleFramework", "TeacherID"),
                     T("role", "teacher")],
                    [LIVE, Condition("ScheduleFramework", "TeacherID", "not_blank")], distinct=True)
    stu_enr.union_parts = [tch_enr]
    ct, cl, (sc, ci, pn, em) = guardian_chain()
    guardians = query("SchoolStatus - guardians.csv", STU_T + ct, STU_L + cl,
                      [F("Student", "StudentCode", "studentSisId", Fmt("trim")), F(ci, "ContactID", "guardianSisId"),
                       F(ci, "FirstName", "guardianFirstName", Fmt("trim")), F(ci, "LastName", "guardianLastName", Fmt("trim")),
                       F(em, "Address", "guardianEmail", Fmt("trim"), Fmt("lower")), phone_col("guardianPhone", pn),
                       T("guardianHomePhone"), F(ci, "PrimaryLanguage", "guardianLanguage")],
                      STU_C + [Condition(ci, "ContactID", "not_blank")], distinct=True)
    return {
        "id": "schoolstatus", "name": "SchoolStatus (attendance & family communication)",
        "works_with": "SchoolStatus Connect messaging, SchoolStatus Attend attendance outreach (Mississippi SB 2103)",
        "description": "SchoolStatus' SFTP roster files: users (students + teachers), classes, enrollments and the "
                       "guardians file that links each guardian's email/phone to the student. Teachers use a T "
                       "prefix in both users and enrollments. Files are lowercase; you may zip them. " + CONTACT_NOTE,
        "spec_url": "https://help.connect.schoolstatus.com/hc/en-us/articles/24410014470164-Connect-SFTP-Connection-for-SIS",
        "delivery": "SFTP fileupload-ct-sftp.schoolstatus.com port 2222 (credentials from your Customer Success Manager)",
        "requires": CONTACT_REQ,
        "confirm_with_vendor": "SchoolStatus attendance products may also want daily attendance and a "
                               "studentAttributes.csv - ask your Implementation Engineer for those layouts.",
        "files": [f("users.csv", users, "students + teachers"), f("classes.csv", classes),
                  f("enrollments.csv", stu_enr, "students + teachers"), f("guardians.csv", guardians)],
    }


# ================================================================= Active Directory
AD_SCRIPT = r'''<#
  Import-ADUsers.ps1 - creates or updates Active Directory accounts from the SAM Ad Hoc Query Builder files.
  Run on a domain controller or a PC with RSAT (ActiveDirectory module) as a domain admin:
      .\Import-ADUsers.ps1 -CsvPath .\ad_students.csv            # preview only (no changes)
      .\Import-ADUsers.ps1 -CsvPath .\ad_students.csv -Apply     # make the changes
  New accounts get the Password column and must change it at first sign-in. Existing accounts (matched on
  SamAccountName) get names, email, school, title and employee ID updated - passwords are NOT changed.
  Accounts are never deleted or disabled by this script.
#>
param([Parameter(Mandatory)][string]$CsvPath, [switch]$Apply)
Import-Module ActiveDirectory
$log = Join-Path (Split-Path $CsvPath) ("ad_import_{0:yyyy-MM-dd_HHmm}.log" -f (Get-Date))
foreach ($u in Import-Csv $CsvPath) {
    if (-not $u.SamAccountName) { continue }
    $props = @{ GivenName = $u.GivenName; Surname = $u.Surname; DisplayName = $u.DisplayName;
                EmailAddress = $u.EmailAddress; UserPrincipalName = $u.UserPrincipalName;
                Department = $u.Department; Title = $u.Title; EmployeeID = $u.EmployeeID; Company = $u.Company }
    $existing = Get-ADUser -Filter "SamAccountName -eq '$($u.SamAccountName)'" -ErrorAction SilentlyContinue
    if ($existing) {
        "UPDATE $($u.SamAccountName)" | Tee-Object -FilePath $log -Append
        if ($Apply) { Set-ADUser $existing @props }
    } else {
        "CREATE $($u.SamAccountName) in $($u.Path)" | Tee-Object -FilePath $log -Append
        if ($Apply) {
            New-ADUser -Name $u.DisplayName -SamAccountName $u.SamAccountName -Path $u.Path @props `
                -AccountPassword (ConvertTo-SecureString $u.Password -AsPlainText -Force) `
                -ChangePasswordAtLogon $true -Enabled $true
        }
    }
}
if (-not $Apply) { "Preview only - run again with -Apply to make these changes." }
'''


def active_directory():
    def ad_cols(alias, role, id_col, dept_alias, title, ou_var):
        return [C("SamAccountName", USER(alias, role)), C("UserPrincipalName", EMAIL(alias, role)),
                F(alias, "FirstName", "GivenName", Fmt("trim")), F(alias, "LastName", "Surname", Fmt("trim")),
                C("DisplayName", P(alias, "FirstName", Fmt("trim")), X(" "), P(alias, "LastName", Fmt("trim"))),
                C("EmailAddress", EMAIL(alias, role)), F(dept_alias, "SchoolName", "Department", Fmt("trim")),
                title, F(alias, id_col, "EmployeeID", Fmt("trim")), T("Company", "{{DISTRICT_NAME}}"),
                T("Path", ou_var), PASSWORD("Password", alias, id_col)]
    students = query("AD - students.csv", STU_SCH_T, STU_SCH_L,
                     ad_cols("Student", "student", "StudentCode", "SchoolDef",
                             C("Title", X("Grade "), P("Student", "ADAGrade")), "{{AD_STUDENT_OU}}"),
                     STU_C, distinct=True, sort=["Surname", "GivenName"])
    staff = query("AD - staff.csv", EMP_SCH_T, EMP_SCH_L,
                  ad_cols("Employee", "staff", "EmployeeNumber", "SchoolDef",
                          F("Employee", "FacultyFlag", "Title", Fmt("map", "1=Teacher; 0=Staff")), "{{AD_STAFF_OU}}"),
                  STAFF_ACTIVE, distinct=True, sort=["Surname", "GivenName"])
    return {
        "id": "active_directory", "name": "Active Directory accounts (on-premises)",
        "works_with": "Windows Active Directory (and Entra Connect / Google Cloud Directory Sync that copy from it)",
        "description": "One row per student and staff member with SamAccountName and email from your username "
                       "pattern, names, school (Department), grade/title, ID, the OU to create them in and a starting "
                       "password (District Settings prefix + last 6 of the ID). The package includes "
                       "Import-ADUsers.ps1, which previews first and only creates or updates accounts - it never "
                       "deletes or disables. Keep these files in a secured folder: they contain starting passwords.",
        "spec_url": "https://learn.microsoft.com/en-us/powershell/module/activedirectory/new-aduser",
        "delivery": "Run Import-ADUsers.ps1 on a domain-joined PC with RSAT (schedule it after the CAC Agent job)",
        "requires": ["ACCOUNT_PASSWORD_PREFIX", "AD_STUDENT_OU", "AD_STAFF_OU"],
        "static_files": {"Import-ADUsers.ps1": AD_SCRIPT},
        "files": [f("ad_students.csv", students), f("ad_staff.csv", staff)],
    }


# ================================================================= Microsoft Entra ID
def entra():
    hdr = ["Name [displayName] Required", "User name [userPrincipalName] Required",
           "Initial password [passwordProfile] Required", "First name [givenName]", "Last name [surname]",
           "Job title [jobTitle]", "Department [department]"]
    students = query("Entra - students.csv", STU_SCH_T, STU_SCH_L,
                     [C(hdr[0], P("Student", "FirstName", Fmt("trim")), X(" "), P("Student", "LastName", Fmt("trim"))),
                      C(hdr[1], EMAIL("Student", "student")), PASSWORD(hdr[2], "Student", "StudentCode"),
                      F("Student", "FirstName", hdr[3], Fmt("trim")), F("Student", "LastName", hdr[4], Fmt("trim")),
                      C(hdr[5], X("Student - Grade "), P("Student", "ADAGrade")),
                      F("SchoolDef", "SchoolName", hdr[6], Fmt("trim"))],
                     STU_C, distinct=True)
    staff = query("Entra - staff.csv", EMP_SCH_T, EMP_SCH_L,
                  [C(hdr[0], P("Employee", "FirstName", Fmt("trim")), X(" "), P("Employee", "LastName", Fmt("trim"))),
                   C(hdr[1], EMAIL("Employee", "staff")), PASSWORD(hdr[2], "Employee", "EmployeeNumber"),
                   F("Employee", "FirstName", hdr[3], Fmt("trim")), F("Employee", "LastName", hdr[4], Fmt("trim")),
                   F("Employee", "FacultyFlag", hdr[5], Fmt("map", "1=Teacher; 0=Staff")),
                   F("SchoolDef", "SchoolName", hdr[6], Fmt("trim"))],
                  STAFF_ACTIVE, distinct=True)
    return {
        "id": "entra", "name": "Microsoft Entra ID accounts (bulk create)",
        "works_with": "Microsoft Entra ID / Microsoft 365 cloud-only accounts (Entra admin center > Users > Bulk create)",
        "description": "Entra's bulk-create template columns: display name, user principal name (your email pattern), "
                       "initial password (District Settings prefix + last 6 of the ID, changed at first sign-in), "
                       "first/last name, job title and department (school). Bulk create only adds NEW users - "
                       "filter to new students (e.g. enrolled in the last 7 days) for nightly use, or use School "
                       "Data Sync for ongoing sync. Keep these files secured: they contain starting passwords.",
        "spec_url": "https://learn.microsoft.com/en-us/entra/identity/users/users-bulk-add",
        "delivery": "Entra admin center > Users > Bulk operations > Bulk create > upload the CSV",
        "requires": ["ACCOUNT_PASSWORD_PREFIX"],
        "confirm_with_vendor": "Download the current template from Entra (Bulk create) - if it starts with a "
                               "version row, paste that line above the header before uploading.",
        "files": [f("entra_students.csv", students), f("entra_staff.csv", staff)],
    }


# ================================================================= PBIS Rewards
def pbis_rewards():
    students = query("PBIS Rewards - students.csv", STU_T, STU_L,
                     [F("Student", "FirstName", "First Name", Fmt("trim")), F("Student", "LastName", "Last Name", Fmt("trim")),
                      F("Student", "StudentCode", "Student ID", Fmt("trim")),
                      F("Student", "ADAGrade", "Grade", Fmt("map", GRADE_PBIS)),
                      F("Student", "GenderCode", "Gender"), F("Student", "RaceCode", "Ethnicity", Fmt("map", "I=N; P=O; M=O; T=O")),
                      C("Email", EMAIL("Student", "student"))],
                     STU_C, distinct=True, sort=["Last Name", "First Name"])
    staff = staff_q("PBIS Rewards - staff.csv",
                    [F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                     C("Email", EMAIL("Employee", "staff")), F("Employee", "EmployeeNumber", "Staff ID", Fmt("trim")),
                     school_name()])
    ct, cl, (sc, ci, pn, em) = guardian_chain()
    family = query("PBIS Rewards - family members.csv", STU_T + ct, STU_L + cl,
                   [F("Student", "StudentCode", "Student ID", Fmt("trim")),
                    F(ci, "FirstName", "First Name", Fmt("trim")), F(ci, "LastName", "Last Name", Fmt("trim")),
                    F(em, "Address", "Email", Fmt("trim"), Fmt("lower")), phone_col("Phone", pn),
                    F(sc, "RelationshipCode", "Relationship")],
                   STU_C + [Condition(em, "Address", "not_blank")], distinct=True)
    return {
        "id": "pbis_rewards", "name": "PBIS Rewards (Navigate360)",
        "works_with": "PBIS Rewards student, staff and family-member imports",
        "description": "Student Import Template order: First Name, Last Name, Student ID, Grade (PK, 0 for "
                       "kindergarten, 1-12), Gender (M/F/X/N), Ethnicity (A/B/H/N/W/O - SAM race codes I, P and M are translated to N, O and O; adjust "
                       "in Step 3) and Email (needed for Google sign-in). Plus staff and a family-member "
                       "file. Schools that sync PBIS Rewards with Clever or ClassLink only need the family file. "
                       + CONTACT_NOTE,
        "spec_url": "https://support.pbisrewards.com/article/how-do-i-add-a-new-student/",
        "delivery": "PBIS Rewards > Students > Add Additional/All Students, or Settings > Secure Transfer",
        "requires": CONTACT_REQ,
        "confirm_with_vendor": "The staff and family-member layouts come from templates inside PBIS Rewards "
                               "(Settings > Family Member Importer) - match the headings to them.",
        "files": [f("pbis_students.csv", students), f("pbis_staff.csv", staff, CONFIRM),
                  f("pbis_family_members.csv", family, CONFIRM)],
    }


# ================================================================= Behavior apps (Hero, LiveSchool...)
def behavior():
    students = query("Behavior - students.csv", STU_SCH_T + HR_LIVE_T, STU_SCH_L + HR_LIVE_L,
                     stu_basic() + [F("Student", "ADAGrade", "Grade"), F("SchoolDef", "SchoolCode", "School ID"),
                                    school_name(), F("HomeroomTeacher", "LastName", "Homeroom", Fmt("trim")),
                                    C("Student Email", EMAIL("Student", "student")),
                                    F("Student", "LunchNumber", "Barcode / PIN", Fmt("trim"))],
                     STU_C, distinct=True, sort=["School", "Last Name"])
    staff = staff_q("Behavior - staff.csv",
                    [F("Employee", "EmployeeNumber", "Staff ID", Fmt("trim")),
                     F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                     C("Email", EMAIL("Employee", "staff")), F("SchoolDef", "SchoolCode", "School ID"), school_name()])
    roster = query("Behavior - class roster.csv", ROS_T + [("Teacher", "Employee")],
                   ROS_L + [("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "INNER")],
                   [F("Student", "StudentCode", "Student ID", Fmt("trim")), F("Teacher", "EmployeeNumber", "Staff ID", Fmt("trim")),
                    class_title("Class Name"), F("ScheduleFramework", "Period", "Period"),
                    F("Schedule", "SchoolID", "School ID")], ROS_C, distinct=True)
    ct, cl, (sc, ci, pn, em) = guardian_chain()
    parents = query("Behavior - parents.csv", STU_T + ct, STU_L + cl,
                    [F("Student", "StudentCode", "Student ID", Fmt("trim"))] + guardian_cols(ci, pn, em),
                    STU_C + [Condition(ci, "ContactID", "not_blank")], distinct=True)
    return {
        "id": "behavior", "name": "Behavior / PBIS apps (SchoolMint Hero, LiveSchool...)",
        "works_with": "SchoolMint Hero, LiveSchool, Kickboard-style behavior and tardy-kiosk systems",
        "description": "Students (with homeroom and the lunch PIN for kiosk/badge scanning), staff, class rosters "
                       "and parents. These vendors map columns during setup and many also sync rosters from "
                       "Clever/ClassLink - use this when they ask for SIS files. " + CONTACT_NOTE,
        "spec_url": "",
        "delivery": "SFTP or upload in the vendor's admin site",
        "requires": CONTACT_REQ,
        "confirm_with_vendor": CONFIRM,
        "files": [f("behavior_students.csv", students), f("behavior_staff.csv", staff),
                  f("behavior_roster.csv", roster), f("behavior_parents.csv", parents)],
    }


# ================================================================= Ellevation
def ellevation():
    ct, cl, (sc, ci, pn, em) = contact_chain()
    at, al, ad = address_chain("Student", "StudentID", OT_STU)
    imm_t = [("Immigrant", "Immigrant")]
    imm_l = [("Student", "StudentID", "Immigrant", "StudentID", "LEFT", [Condition("Immigrant", "Active", "eq", "1")])]
    n = lambda h: T(h)  # noqa: E731
    cols = [F("Student", "FirstName", "First Name", Fmt("trim")), F("Student", "MiddleName", "Middle Name", Fmt("trim")),
            F("Student", "LastName", "Last Name", Fmt("trim")), F("Student", "StateCode", "State Student Test ID #"),
            F("Student", "StudentCode", "Local Student ID #", Fmt("trim")),
            F("SchoolDef", "SchoolName", "LEA Code/School Name", Fmt("trim")),
            F("Student", "ADAGrade", "Grade Level"), F("Student", "GenderCode", "Gender"),
            F("Student", "DOB", "Date of Birth", Fmt("date_us")), n("City/Town of Birth"), n("Birth Country"),
            n("Ethnicity"), F("Student", "RaceCode", "Race"), F("Student", "LangBackground", "Native Language"),
            F(ci, "PrimaryLanguage", "Home Language"), n("Receiving ESL Services?"),
            n("Parent Refused ELL Services/Programs (y/n)"),
            RAW("IEP", "CASE WHEN LTRIM(RTRIM(ISNULL(Student.SPEDStatus, ''))) IN ('', '0', 'N') THEN 'N' ELSE 'Y' END"),
            YNcol("504 Plan", "Student.Flag504"), n("SIFE"),
            RAW("Immigrant", "CASE WHEN Immigrant.ImmigrantID IS NULL THEN 'N' ELSE 'Y' END"),
            n("Migrant"), n("Homebound"), n("Homeless"),
            RAW("Gifted and Talented", "CASE WHEN LTRIM(RTRIM(ISNULL(Student.GiftedStatus, ''))) IN ('', '0', 'N') "
                                       "THEN 'N' ELSE 'Y' END"),
            n("Receiving ESL Services"),
            F(ad, "AddrLine1", "Address Line 1", Fmt("trim")), F(ad, "AddrLine2", "Address Line 2", Fmt("trim")),
            F(ad, "City", "City", Fmt("trim")), F(ad, "State", "State"), F(ad, "ZipCode", "Zip"),
            phone_col("Home Phone Number", pn), n("Cell Phone Number")]
    cols += [n(h) for h in ("Father Name", "Father Phone", "Father Email", "Father Workplace",
                            "Father Needs Interpreting (Y/N)", "Mother Name", "Mother Phone", "Mother Email",
                            "Mother Workplace", "Mother Needs Interpreting (Y/N)", "Emergency Contact Name",
                            "Emergency Contact Phone", "Emergency Contact Email",
                            "Emergency Contact Needs Interpreting (Y/N)")]
    cols += [C("Guardian Name", P(ci, "FirstName", Fmt("trim")), X(" "), P(ci, "LastName", Fmt("trim"))),
             phone_col("Guardian Phone", pn), F(em, "Address", "Guardian Email", Fmt("trim"), Fmt("lower")),
             n("Guardian Needs Interpreting (Y/N)"), T("Active (enrolled in district y/n)", "y"),
             T("Withdrawn", "n"), T("Graduated", "n"), T("Deceased", "n")]
    cols += [n(h) for h in ("Entered LEP Date", "Exited LEP Date", "Monitored Since Date", "Date Entered US",
                            "Date Enrolled in US", "Date Enrolled in the District", "Date Withdrawn (from district)",
                            "Date Graduated (from district)", "Date Dropped Out (from district)")]
    students = query("Ellevation - students.csv", STU_SCH_T + ct + at + imm_t, STU_SCH_L + cl + al + imm_l, cols,
                     STU_C, distinct=True, sort=["Last Name", "First Name"])
    sched = query("Ellevation - student schedule courses.csv", ROS_T + [("Teacher", "Employee")],
                  ROS_L + [("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "LEFT")],
                  [F("Course", "Classification", "Subject Area"),
                   C("Teacher Name", P("Teacher", "FirstName", Fmt("trim")), X(" "), P("Teacher", "LastName", Fmt("trim"))),
                   F("Course", "CourseCode", "Course Code", Fmt("trim")), F("ScheduleFramework", "TeacherID", "Staff ID"),
                   F("Student", "StudentCode", "Student ID", Fmt("trim"))], ROS_C, distinct=True)
    return {
        "id": "ellevation", "name": "Ellevation (English learners)",
        "works_with": "Ellevation Platform / Ellevation Strategies EL program management",
        "description": "Ellevation's 64-column student file (in their order) plus the student schedule courses file. "
                       "Filled from SAM: names, IDs, school, grade, gender, birth date, race, native/home language, "
                       "IEP / 504 / gifted (Y/N), immigrant, address and the primary guardian. EL program columns "
                       "(ESL services, LEP entry/exit dates, SIFE, father/mother/emergency contacts) are left "
                       "blank for you to fill from your EL records or map with Ellevation. Contains protected "
                       "program data. " + CONTACT_NOTE,
        "spec_url": "https://support-sis.genesisedu.com/support/solutions/articles/151000094043-ellevation-export",
        "delivery": "SFTP to Ellevation (nightly); your Ellevation data team sets up the folder",
        "requires": CONTACT_REQ + ["OWNER_TYPE_STUDENT"],
        "confirm_with_vendor": "Layout taken from an SIS partner's Ellevation export - confirm with Ellevation's "
                               "data team and tell them which EL fields you'll send.",
        "files": [f("ellevation_students.csv", students), f("ellevation_schedules.csv", sched)],
    }


# ================================================================= Payments
def payments():
    ct, cl, (sc, ci, pn, em) = contact_chain()
    students = query("Payments - students.csv", STU_SCH_T + HR_LIVE_T + ct, STU_SCH_L + HR_LIVE_L + cl,
                     stu_basic() + [F("Student", "ADAGrade", "Grade"), F("SchoolDef", "SchoolCode", "School Code"),
                                    school_name(), F("HomeroomTeacher", "LastName", "Homeroom", Fmt("trim")),
                                    F("Student", "LunchNumber", "Meal PIN", Fmt("trim")),
                                    F("Student", "DOB", "Birth Date", Fmt("date_us")),
                                    F(em, "Address", "Guardian Email", Fmt("trim"), Fmt("lower")),
                                    T("Status", "Active")],
                     STU_C, distinct=True, sort=["School", "Last Name"])
    return {
        "id": "payments", "name": "School payments (MySchoolBucks, SchoolCash Online, PaySchools...)",
        "works_with": "MySchoolBucks, SchoolCash Online, PaySchools Central, RevTrak and other fee / lunch payment portals",
        "description": "Student roster for fee and meal payment portals: ID, names, grade, school, homeroom, meal PIN "
                       "and the primary guardian's email (parents match their account to the student ID). "
                       "Meal eligibility is not included - send it only to the food-service system. " + CONTACT_NOTE,
        "spec_url": "",
        "delivery": "Vendor SFTP or the portal's student upload page",
        "requires": CONTACT_REQ,
        "confirm_with_vendor": CONFIRM,
        "files": [f("payments_students.csv", students)],
    }


# ================================================================= Bus apps
def bus_apps():
    ct, cl, (sc, ci, pn, em) = contact_chain()
    at, al, ad = address_chain("Student", "StudentID", OT_STU)
    bus_t = [("stuBusInformation", "stuBusInformation")]
    bus_l = [("Student", "StudentID", "stuBusInformation", "StudentID", "LEFT")]
    students = query("Bus app - riders.csv", STU_SCH_T + bus_t + ct + at, STU_SCH_L + bus_l + cl + al,
                     stu_basic() + [F("Student", "ADAGrade", "Grade"), F("SchoolDef", "SchoolCode", "School Code"),
                                    school_name(), F("stuBusInformation", "AMBusNumber", "AM Bus"),
                                    F("stuBusInformation", "PMBusNumber", "PM Bus"),
                                    F("stuBusInformation", "AMBusRoute", "AM Route"),
                                    F("stuBusInformation", "PMBusRoute", "PM Route"),
                                    F("stuBusInformation", "BusStop", "Bus Stop", Fmt("trim")),
                                    F(ad, "AddrLine1", "Address", Fmt("trim")), F(ad, "City", "City", Fmt("trim")),
                                    F(ad, "ZipCode", "Zip")] + guardian_cols(ci, pn, em) +
                     [T("Rider Card Number")],
                     STU_C + [Condition("Student", "TransportationCode", "not_blank")], distinct=True,
                     sort=["AM Bus", "Last Name"])
    return {
        "id": "bus_apps", "name": "Bus apps & ridership (Here Comes the Bus, Zonar, Edulog Parent Portal...)",
        "works_with": "Here Comes the Bus, Zonar MyView / Z Pass, Edulog Parent Portal, Tyler Traversa Ride 360",
        "description": "Bus riders (students with a transportation code) with AM/PM bus and route, stop, home address "
                       "and the primary guardian - parents sign up with the student ID and school code. Rider card "
                       "numbers are assigned by the vendor; leave that column blank or fill it from their file. "
                       "Use the Transportation / routing package for the routing system itself. " + CONTACT_NOTE,
        "spec_url": "",
        "delivery": "Vendor SFTP or the routing system's import folder",
        "requires": CONTACT_REQ + ["OWNER_TYPE_STUDENT"],
        "confirm_with_vendor": CONFIRM,
        "files": [f("bus_riders.csv", students)],
    }


# ================================================================= Web filter parent reports
def filter_parents():
    ct, cl, (sc, ci, pn, em) = guardian_chain()
    parents = query("Filter - parent emails.csv", STU_SCH_T + ct, STU_SCH_L + cl,
                    [C("Student Email", EMAIL("Student", "student")),
                     F(em, "Address", "Parent Email", Fmt("trim"), Fmt("lower")),
                     F(ci, "FirstName", "Parent First Name", Fmt("trim")), F(ci, "LastName", "Parent Last Name", Fmt("trim")),
                     F("Student", "StudentCode", "Student ID", Fmt("trim")), school_name()],
                    STU_C + [Condition(em, "Address", "not_blank")], distinct=True)
    return {
        "id": "filter_parents", "name": "Web filter parent reports (Securly, Lightspeed, GoGuardian)",
        "works_with": "Securly Home / Parent App, Lightspeed Parent Portal, GoGuardian Parent App",
        "description": "Student email + parent email pairs (one row per parent) so parents receive device activity "
                       "reports. The student email must match the student's Google/Microsoft account exactly - "
                       "check it against the Google package. " + CONTACT_NOTE,
        "spec_url": "https://support.securly.com/hc/en-us/articles/228390168-Home-How-to-minimize-upload-failures-for-parent-CSV-files",
        "delivery": "Filter admin console (parent CSV upload) or the vendor's SFTP",
        "requires": CONTACT_REQ,
        "confirm_with_vendor": "Securly expects only the two email columns in a set order; Lightspeed and GoGuardian "
                               "map columns. Remove the extra columns in Step 3 if your vendor asks.",
        "files": [f("filter_parent_emails.csv", parents)],
    }


# ================================================================= Emergency / reunification
def emergency():
    staff_phone_t = [("StaffPhoneLink", "PhoneRelationship"), ("StaffPhone", "PhoneNumber")]
    staff_phone_l = [("Employee", "EmployeeID", "StaffPhoneLink", "OwnerID", "LEFT",
                      [Condition("StaffPhoneLink", "OwnerType", "eq", OT_EMP),
                       Condition("StaffPhoneLink", "PrimaryPhone", "eq", "1")]),
                     ("StaffPhoneLink", "PhoneNumberID", "StaffPhone", "PhoneNumberID", "LEFT")]
    staff = staff_q("Emergency - staff.csv",
                    [F("Employee", "EmployeeNumber", "Staff ID", Fmt("trim")),
                     F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                     C("Email", EMAIL("Employee", "staff")), phone_col("Mobile Phone", "StaffPhone"),
                     F("Employee", "FacultyFlag", "Role", Fmt("map", "1=Teacher; 0=Staff")), school_name()],
                    staff_phone_t, staff_phone_l)
    ct, cl, (sc, ci, pn, em) = guardian_chain()
    students = query("Emergency - students and guardians.csv", STU_SCH_T + HR_LIVE_T + ct, STU_SCH_L + HR_LIVE_L + cl,
                     stu_basic() + [F("Student", "ADAGrade", "Grade"), school_name(),
                                    F("HomeroomTeacher", "LastName", "Homeroom", Fmt("trim"))] +
                     guardian_cols(ci, pn, em) +
                     [F(sc, "RelationshipCode", "Relationship"),
                      YNcol("Can Pick Up", f"{sc}.CheckInOut"), YNcol("No Contact", f"{sc}.NoContact")],
                     STU_C + [Condition(ci, "ContactID", "not_blank")], distinct=True,
                     sort=["School", "Last Name"])
    return {
        "id": "emergency", "name": "Emergency alerts & reunification (Centegix, CrisisGo, Rave...)",
        "works_with": "Centegix CrisisAlert, CrisisGo, Rave Panic Button / Mobile Safety, Navigate360 and "
                      "Standard Reunification Method rosters",
        "description": "Staff with mobile phone and building (for alert enrollment) and every student with homeroom "
                       "and each guardian who may be contacted - Can Pick Up and No Contact come from "
                       "StudentContact.CheckInOut / NoContact so reunification staff see who may take a child. "
                       "Make one file per building with the Schools: button. " + CONTACT_NOTE,
        "spec_url": "",
        "delivery": "Vendor SFTP or admin-site upload",
        "requires": CONTACT_REQ + ["OWNER_TYPE_EMPLOYEE"],
        "confirm_with_vendor": CONFIRM,
        "files": [f("emergency_staff.csv", staff), f("emergency_students_guardians.csv", students)],
    }


# ================================================================= Athletics registration
def athletics():
    ct, cl, (sc, ci, pn, em) = contact_chain()
    at, al, ad = address_chain("Student", "StudentID", OT_STU)
    med_t = [("MedicalInfo", "MedicalInfo")]
    med_l = [("Student", "StudentID", "MedicalInfo", "OwnerID", "LEFT",
              [Condition("MedicalInfo", "OwnerType", "eq", OT_STU)])]
    students = query("Athletics - students.csv", STU_SCH_T + ct + at + med_t, STU_SCH_L + cl + al + med_l,
                     stu_basic() + [F("Student", "DOB", "Birth Date", Fmt("date_us")), F("Student", "GenderCode", "Gender"),
                                    F("Student", "ADAGrade", "Grade"),
                                    F("Student", "OriginalGradDate", "Graduation Year", Fmt("year")),
                                    school_name(), C("Student Email", EMAIL("Student", "student")),
                                    F(ad, "AddrLine1", "Address", Fmt("trim")), F(ad, "City", "City", Fmt("trim")),
                                    F(ad, "State", "State"), F(ad, "ZipCode", "Zip")] + guardian_cols(ci, pn, em) +
                     [F("MedicalInfo", "LastPhysical", "Last Physical", Fmt("date_us"))],
                     STU_C + [Condition("Student", "ADAGrade", "in", "06,07,08,09,10,11,12")], distinct=True,
                     sort=["School", "Last Name"])
    return {
        "id": "athletics", "name": "Athletics registration (Rank One, FinalForms...)",
        "works_with": "Rank One Sport, FinalForms, ArbiterSports registration and physical tracking",
        "description": "Students in grades 6-12 with birth date, gender, grade, graduation year, address, primary "
                       "guardian and the last physical date from SAM's medical info, so the athletics system "
                       "pre-fills registration. Use the DragonFly package for academic eligibility grades. "
                       + CONTACT_NOTE,
        "spec_url": "",
        "delivery": "Vendor SFTP or admin import",
        "requires": CONTACT_REQ + ["OWNER_TYPE_STUDENT"],
        "confirm_with_vendor": CONFIRM,
        "files": [f("athletics_students.csv", students)],
    }


# ================================================================= Hall pass / ID kiosks
def hall_pass():
    students = query("Hall pass - students.csv", STU_SCH_T + HR_LIVE_T, STU_SCH_L + HR_LIVE_L,
                     stu_basic() + [F("Student", "ADAGrade", "Grade"), C("Email", EMAIL("Student", "student")),
                                    school_name(), F("HomeroomTeacher", "LastName", "Homeroom Teacher", Fmt("trim")),
                                    C("Homeroom Teacher Email", EMAIL("HomeroomTeacher", "staff")),
                                    F("Student", "LunchNumber", "Barcode", Fmt("trim"))],
                     STU_C, distinct=True, sort=["School", "Last Name"])
    staff = staff_q("Hall pass - staff.csv",
                    [F("Employee", "EmployeeNumber", "Staff ID", Fmt("trim")),
                     F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                     C("Email", EMAIL("Employee", "staff")), school_name()])
    schedule = query("Hall pass - schedules.csv", ROS_T + [("Teacher", "Employee")],
                     ROS_L + [("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "INNER")],
                     [F("Student", "StudentCode", "Student ID", Fmt("trim")), F("ScheduleFramework", "Period", "Period"),
                      F("Course", "LongName", "Course", Fmt("trim")), C("Teacher Email", EMAIL("Teacher", "staff")),
                      F("Schedule", "SchoolID", "School ID")], ROS_C, distinct=True)
    return {
        "id": "hall_pass", "name": "Hall pass & ID kiosks (5-Star Students, SmartPass...)",
        "works_with": "5-Star Students, SmartPass, Minga, e-hallpass and badge/kiosk systems",
        "description": "Students with email, homeroom teacher and the lunch PIN as a barcode, staff, and each "
                       "student's class schedule by period so passes show the right teacher.",
        "spec_url": "",
        "delivery": "Vendor SFTP or admin upload (many also sync from Clever/ClassLink)",
        "confirm_with_vendor": CONFIRM,
        "files": [f("hallpass_students.csv", students), f("hallpass_staff.csv", staff),
                  f("hallpass_schedules.csv", schedule)],
    }


# ================================================================= Credit recovery / online courses
def credit_recovery():
    students = query("Online courses - students.csv", STU_SCH_T, STU_SCH_L,
                     stu_basic() + [F("Student", "MiddleName", "Middle Name", Fmt("trim")), F("Student", "ADAGrade", "Grade"),
                                    C("Email", EMAIL("Student", "student")), C("Username", USER("Student", "student")),
                                    F("SchoolDef", "SchoolCode", "School Code"), school_name(),
                                    YNcol("504", "Student.Flag504"),
                                    RAW("IEP", "CASE WHEN LTRIM(RTRIM(ISNULL(Student.SPEDStatus, ''))) IN ('', '0', 'N') "
                                               "THEN 'N' ELSE 'Y' END")],
                     STU_C + [Condition("Student", "ADAGrade", "in", "06,07,08,09,10,11,12")], distinct=True)
    teachers = staff_q("Online courses - teachers.csv",
                       [F("Employee", "EmployeeNumber", "Teacher ID", Fmt("trim")),
                        F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                        C("Email", EMAIL("Employee", "staff")), F("SchoolDef", "SchoolCode", "School Code")])
    enroll = query("Online courses - enrollments.csv", ROS_T + [("Teacher", "Employee")],
                   ROS_L + [("ScheduleFramework", "TeacherID", "Teacher", "EmployeeID", "INNER")],
                   [F("Student", "StudentCode", "Student ID", Fmt("trim")), F("Teacher", "EmployeeNumber", "Teacher ID", Fmt("trim")),
                    F("ScheduleFramework", "ScheduleFrameworkID", "Class ID"), class_title("Class Name"),
                    F("Course", "CourseCode", "Course Code", Fmt("trim")), F("Course", "StateCourseID", "State Course ID")],
                   ROS_C + [Condition("Course", "LongName", "contains", "{{ONLINE_COURSE_KEYWORD}}"),
                            Condition("Student", "ADAGrade", "in", "06,07,08,09,10,11,12")], distinct=True)
    return {
        "id": "credit_recovery", "name": "Credit recovery & online courses (Edmentum, Imagine Edgenuity...)",
        "works_with": "Edmentum Courseware / Exact Path, Imagine Edgenuity, Apex Learning, Odysseyware",
        "description": "Students (grades 6-12, with 504/IEP flags for accommodations), teachers and enrollments in "
                       "the SAM sections whose course name contains your online-course keyword (District Settings, "
                       "e.g. 'Edgenuity' or 'Credit Recovery'). Most of these vendors also take OneRoster - use "
                       "this when they ask for CSV files.",
        "spec_url": "",
        "delivery": "Vendor SFTP or admin upload",
        "requires": ["ONLINE_COURSE_KEYWORD"],
        "confirm_with_vendor": CONFIRM,
        "files": [f("online_students.csv", students), f("online_teachers.csv", teachers),
                  f("online_enrollments.csv", enroll)],
    }


# ================================================================= Scoir / MajorClarity
def scoir():
    students = query("Scoir - students.csv", STU_SCH_T + HR_LIVE_T[:1] + COUNSELOR_T,
                     STU_SCH_L + HR_LIVE_L[:1] + COUNSELOR_L,
                     stu_basic() + [F("Student", "MiddleName", "Middle Name", Fmt("trim")),
                                    F("Student", "OriginalGradDate", "Graduation Year", Fmt("year")),
                                    F("Student", "ADAGrade", "Grade"), F("Student", "DOB", "Birth Date", Fmt("date_us")),
                                    C("Email", EMAIL("Student", "student")), F("SchoolDef", "SchoolCode", "School Code"),
                                    C("Counselor Email", EMAIL("Counselor", "staff")),
                                    F("Student", "CumulativeGPA", "GPA")],
                     STU_C + [Condition("Student", "ADAGrade", "in", "08,09,10,11,12")], distinct=True)
    ct, cl, (sc, ci, pn, em) = guardian_chain()
    parents = query("Scoir - parents.csv", STU_T + ct, STU_L + cl,
                    [F("Student", "StudentCode", "Student ID", Fmt("trim")),
                     F(ci, "FirstName", "Parent First Name", Fmt("trim")), F(ci, "LastName", "Parent Last Name", Fmt("trim")),
                     F(em, "Address", "Parent Email", Fmt("trim"), Fmt("lower"))],
                    STU_C + [Condition("Student", "ADAGrade", "in", "08,09,10,11,12"), Condition(em, "Address", "not_blank")],
                    distinct=True)
    staff = staff_q("Scoir - staff.csv",
                    [F("Employee", "FirstName", "First Name", Fmt("trim")), F("Employee", "LastName", "Last Name", Fmt("trim")),
                     C("Email", EMAIL("Employee", "staff")), F("SchoolDef", "SchoolCode", "School Code")],
                    faculty_only=True)
    return {
        "id": "scoir", "name": "Scoir / MajorClarity (college & career)",
        "works_with": "Scoir, MajorClarity, Kuder Navigator and other college & career platforms",
        "description": "Students in grades 8-12 with graduation year, counselor email and GPA, parents (email) and "
                       "staff. Use the Naviance, Xello or SchooLinks packages for those platforms. " + CONTACT_NOTE,
        "spec_url": "",
        "delivery": "Vendor SFTP or admin upload",
        "requires": CONTACT_REQ,
        "confirm_with_vendor": CONFIRM,
        "files": [f("scoir_students.csv", students), f("scoir_parents.csv", parents), f("scoir_staff.csv", staff)],
    }


# ================================================================= Adobe Admin Console
def adobe():
    def cols(alias, role):
        return [T("Identity Type", "{{ADOBE_IDENTITY_TYPE}}"), C("Username", EMAIL(alias, role)),
                T("Domain"), C("Email", EMAIL(alias, role)),
                F(alias, "FirstName", "First Name", Fmt("trim")), F(alias, "LastName", "Last Name", Fmt("trim")),
                T("Country Code", "US"), T("ID"), T("Product Configurations")]
    students = query("Adobe - students.csv", STU_T, STU_L, cols("Student", "student"),
                     STU_C + [Condition("Student", "ADAGrade", "in", "06,07,08,09,10,11,12")], distinct=True)
    staff = query("Adobe - staff.csv", EMP_T, EMP_L, cols("Employee", "staff"), STAFF_ACTIVE, distinct=True)
    return {
        "id": "adobe", "name": "Adobe Admin Console (Adobe Express / Creative Cloud)",
        "works_with": "Adobe Admin Console bulk user upload",
        "description": "Users CSV in Adobe's column order: Identity Type (District Settings - usually Federated ID "
                       "for Google/Microsoft sign-in), Username and Email (your email pattern), names, Country Code "
                       "and Product Configurations (type the product profile name in Step 3, e.g. 'Adobe Express "
                       "- Students'). Students are grades 6-12; change the grade filter if needed.",
        "spec_url": "https://helpx.adobe.com/enterprise/using/bulk-upload-users.html",
        "delivery": "Adobe Admin Console > Users > Add users by CSV",
        "requires": ["ADOBE_IDENTITY_TYPE"],
        "confirm_with_vendor": "Download the CSV template from the Admin Console and compare the header row - Adobe "
                               "may add columns after Product Configurations.",
        "files": [f("adobe_students.csv", students), f("adobe_staff.csv", staff)],
    }


# ================================================================= Zoom
def zoom():
    staff = query("Zoom - users.csv", EMP_SCH_T, EMP_SCH_L,
                  [C("Email", EMAIL("Employee", "staff")), F("Employee", "FirstName", "First Name", Fmt("trim")),
                   F("Employee", "LastName", "Last Name", Fmt("trim")), F("SchoolDef", "SchoolName", "Department", Fmt("trim")),
                   T("User Type", "Licensed")],
                  STAFF_ACTIVE, distinct=True, sort=["Last Name"])
    return {
        "id": "zoom", "name": "Zoom (staff accounts)",
        "works_with": "Zoom web portal > User Management > Users > Import",
        "description": "Staff email, names, school (Department) and user type for Zoom's user import. Student "
                       "accounts are usually created by SSO instead.",
        "spec_url": "https://support.zoom.com/",
        "delivery": "Zoom admin portal > Users > Import (CSV)",
        "confirm_with_vendor": "Download Zoom's sample CSV from the Import window and match the headings.",
        "files": [f("zoom_users.csv", staff)],
    }


VENDOR_PLATFORMS = [apple_school_manager, schoolstatus, active_directory, entra, pbis_rewards, behavior, ellevation,
                    payments, bus_apps, filter_parents, emergency, athletics, hall_pass, credit_recovery, scoir,
                    adobe, zoom]

VENDOR_RULES = {
    "apple_asm": {"files": {
        "locations.csv": R(["location_id", "location_name"], ["location_id"], {"location_name": "maxlen:256"}),
        "students.csv": R(["person_id", "first_name", "last_name", "location_id"], ["person_id"],
                          {"first_name": "maxlen:32", "middle_name": "maxlen:32", "last_name": "maxlen:64",
                           "email_address": "email", "password_policy": "enum:4|6|8", "grade_level": "maxlen:64"}),
        "staff.csv": R(["person_id", "first_name", "last_name", "location_id"], ["person_id"],
                       {"first_name": "maxlen:32", "middle_name": "maxlen:32", "last_name": "maxlen:64",
                        "email_address": "email"}),
        "courses.csv": R(["course_id", "course_name", "location_id"], ["course_id"], {"course_name": "maxlen:128"}),
        "classes.csv": R(["class_id", "course_id", "location_id"], ["class_id"], {"class_number": "maxlen:64"}),
        "rosters.csv": R(["roster_id", "class_id", "student_id"], ["roster_id"])},
        "refs": [["students.csv", "location_id", "locations.csv", "location_id"],
                 ["staff.csv", "location_id", "locations.csv", "location_id"],
                 ["classes.csv", "course_id", "courses.csv", "course_id"],
                 ["classes.csv", "instructor_id", "staff.csv", "person_id"],
                 ["rosters.csv", "class_id", "classes.csv", "class_id"],
                 ["rosters.csv", "student_id", "students.csv", "person_id"]]},
    "schoolstatus": {"files": {
        "users.csv": R(["sourcedId", "role"], ["sourcedId"], {"role": "enum:student|teacher", "email": "email"}),
        "classes.csv": R(["sourcedId", "title", "grades"], ["sourcedId"]),
        "enrollments.csv": R(["classSourcedId", "userSourcedId", "role"], [("classSourcedId", "userSourcedId")],
                             {"role": "enum:student|teacher"}),
        "guardians.csv": R(["studentSisId", "guardianSisId"], [("studentSisId", "guardianSisId")],
                           {"guardianEmail": "email", "guardianPhone": "phone10"})},
        "refs": [["enrollments.csv", "classSourcedId", "classes.csv", "sourcedId"],
                 ["enrollments.csv", "userSourcedId", "users.csv", "sourcedId"],
                 ["guardians.csv", "studentSisId", "users.csv", "sourcedId"]]},
    "active_directory": {"files": {
        fn: R(["SamAccountName", "UserPrincipalName", "GivenName", "Surname", "Path", "Password"],
              ["SamAccountName", "UserPrincipalName"], {"UserPrincipalName": "email", "EmailAddress": "email",
                                                         "SamAccountName": "maxlen:20"})
        for fn in ("ad_students.csv", "ad_staff.csv")}},
    "entra": {"files": {
        fn: R(["Name [displayName] Required", "User name [userPrincipalName] Required",
               "Initial password [passwordProfile] Required"], ["User name [userPrincipalName] Required"],
              {"User name [userPrincipalName] Required": "email"})
        for fn in ("entra_students.csv", "entra_staff.csv")}},
    "pbis_rewards": {"files": {
        "pbis_students.csv": R(["First Name", "Last Name", "Student ID", "Grade"], ["Student ID"],
                               {"Grade": "enum:PK|TK|0|1|2|3|4|5|6|7|8|9|10|11|12|13|NA", "Gender": "enum:M|F|X|N",
                                "Ethnicity": "enum:A|B|H|N|W|O", "Email": "email"}),
        "pbis_staff.csv": R(["First Name", "Last Name", "Email"], ["Email"], {"Email": "email"}),
        "pbis_family_members.csv": R(["Student ID", "Email"], [("Student ID", "Email")], {"Email": "email",
                                                                                          "Phone": "phone10"})},
        "refs": [["pbis_family_members.csv", "Student ID", "pbis_students.csv", "Student ID"]]},
    "behavior": {"files": {
        "behavior_students.csv": R(["Student ID", "First Name", "Last Name"], ["Student ID"], {"Student Email": "email"}),
        "behavior_staff.csv": R(["Staff ID", "First Name", "Last Name"], [], {"Email": "email"}),
        "behavior_roster.csv": R(["Student ID", "Staff ID", "Class Name"]),
        "behavior_parents.csv": R(["Student ID", "Guardian Name"], [], {"Guardian Email": "email",
                                                                        "Guardian Phone": "phone10"})},
        "refs": [["behavior_roster.csv", "Student ID", "behavior_students.csv", "Student ID"],
                 ["behavior_parents.csv", "Student ID", "behavior_students.csv", "Student ID"]]},
    "ellevation": {"files": {
        "ellevation_students.csv": R(["First Name", "Last Name", "Local Student ID #", "Grade Level"],
                                     ["Local Student ID #"],
                                     {"Date of Birth": "date_us", "IEP": "enum:Y|N", "504 Plan": "enum:Y|N",
                                      "Immigrant": "enum:Y|N", "Gifted and Talented": "enum:Y|N",
                                      "Guardian Email": "email", "Home Phone Number": "phone10"}),
        "ellevation_schedules.csv": R(["Course Code", "Student ID"])},
        "refs": [["ellevation_schedules.csv", "Student ID", "ellevation_students.csv", "Local Student ID #"]]},
    "payments": {"files": {"payments_students.csv": R(["Student ID", "First Name", "Last Name", "School Code"],
                                                      ["Student ID"], {"Guardian Email": "email",
                                                                       "Birth Date": "date_us"})}},
    "bus_apps": {"files": {"bus_riders.csv": R(["Student ID", "First Name", "Last Name", "School Code"], ["Student ID"],
                                               {"Guardian Email": "email", "Guardian Phone": "phone10"})}},
    "filter_parents": {"files": {"filter_parent_emails.csv": R(["Student Email", "Parent Email"],
                                                               [("Student Email", "Parent Email")],
                                                               {"Student Email": "email", "Parent Email": "email"})}},
    "emergency": {"files": {
        "emergency_staff.csv": R(["First Name", "Last Name", "School"], [], {"Email": "email", "Mobile Phone": "phone10"}),
        "emergency_students_guardians.csv": R(["Student ID", "First Name", "Last Name", "Guardian Name"], [],
                                              {"Guardian Email": "email", "Guardian Phone": "phone10",
                                               "Can Pick Up": "yn", "No Contact": "yn"})}},
    "athletics": {"files": {"athletics_students.csv": R(["Student ID", "First Name", "Last Name", "Birth Date"],
                                                        ["Student ID"], {"Birth Date": "date_us",
                                                                         "Graduation Year": "year",
                                                                         "Guardian Email": "email",
                                                                         "Last Physical": "date_us"})}},
    "hall_pass": {"files": {
        "hallpass_students.csv": R(["Student ID", "First Name", "Last Name"], ["Student ID"], {"Email": "email"}),
        "hallpass_staff.csv": R(["First Name", "Last Name", "Email"], [], {"Email": "email"}),
        "hallpass_schedules.csv": R(["Student ID", "Period", "Teacher Email"], [], {"Teacher Email": "email"})},
        "refs": [["hallpass_schedules.csv", "Student ID", "hallpass_students.csv", "Student ID"]]},
    "credit_recovery": {"files": {
        "online_students.csv": R(["Student ID", "First Name", "Last Name"], ["Student ID"], {"Email": "email"}),
        "online_teachers.csv": R(["Teacher ID", "First Name", "Last Name"], ["Teacher ID"], {"Email": "email"}),
        "online_enrollments.csv": R(["Student ID", "Class ID"], [("Student ID", "Class ID")])},
        "refs": [["online_enrollments.csv", "Student ID", "online_students.csv", "Student ID"],
                 ["online_enrollments.csv", "Teacher ID", "online_teachers.csv", "Teacher ID"]]},
    "scoir": {"files": {
        "scoir_students.csv": R(["Student ID", "First Name", "Last Name", "Graduation Year"], ["Student ID"],
                                {"Graduation Year": "year", "Email": "email", "Birth Date": "date_us"}),
        "scoir_parents.csv": R(["Student ID", "Parent Email"], [("Student ID", "Parent Email")], {"Parent Email": "email"}),
        "scoir_staff.csv": R(["First Name", "Last Name", "Email"], [], {"Email": "email"})},
        "refs": [["scoir_parents.csv", "Student ID", "scoir_students.csv", "Student ID"]]},
    "adobe": {"files": {fn: R(["Identity Type", "Username", "Email"], ["Email"],
                              {"Email": "email", "Identity Type": "enum:Federated ID|Enterprise ID|Adobe ID"})
                        for fn in ("adobe_students.csv", "adobe_staff.csv")}},
    "zoom": {"files": {"zoom_users.csv": R(["Email", "First Name", "Last Name"], ["Email"], {"Email": "email"})}},
}
VENDOR_DELIVERY = {
    "apple_asm": {"zip": True, "zip_name": "asm_upload.zip", "remote_dir": "Dropbox"},
    "schoolstatus": {"host": "fileupload-ct-sftp.schoolstatus.com", "port": 2222},
}


# ================================================================= Data cleanup reports (tool, not a vendor)
def cleanup():
    LIVE_SQL = "(SELECT ScheduleID FROM Schedule WHERE LiveFlag = 1)"
    base = stu_basic() + [F("Student", "ADAGrade", "Grade"), school_name()]

    def stu_report(title, extra_t, extra_l, extra_cols, conds, note):
        q = query(title, STU_SCH_T + list(extra_t), STU_SCH_L + list(extra_l), base + list(extra_cols),
                  STU_C + list(conds), distinct=True, sort=["School", "Last Name", "First Name"])
        q.description = note
        return q

    ct, cl, (sc, ci, pn, em) = contact_chain()
    at, al, ad = address_chain("Student", "StudentID", OT_STU)
    reports = [
        ("no_primary_contact.csv", stu_report(
            "Students with no primary contact", [("StudentContact", "StudentContact")],
            [("Student", "StudentID", "StudentContact", "StudentID", "LEFT",
              [Condition("StudentContact", "PrimaryContact", "eq", "1")])], [],
            [Condition("StudentContact", "StudentContactID", "blank")],
            "Enrolled students with no contact marked Primary - parent messages and many vendor files skip them.")),
        ("contact_no_phone.csv", stu_report(
            "Primary contacts without a primary phone", ct, cl,
            [C("Contact", P(ci, "FirstName", Fmt("trim")), X(" "), P(ci, "LastName", Fmt("trim")))],
            [Condition(ci, "ContactID", "not_blank"), Condition(pn, "PhoneNumberID", "blank")],
            "Primary contact has no phone marked Primary (or the Contact owner type code is wrong).")),
        ("contact_no_email.csv", stu_report(
            "Primary contacts without a primary email", ct, cl,
            [C("Contact", P(ci, "FirstName", Fmt("trim")), X(" "), P(ci, "LastName", Fmt("trim")))],
            [Condition(ci, "ContactID", "not_blank"), Condition(em, "EMailAddressID", "blank")],
            "Primary contact has no email marked Primary - they can't get parent-portal or app invitations.")),
        ("no_home_address.csv", stu_report(
            "Students without a primary home address", at, al, [], [Condition(ad, "AddressID", "blank")],
            "No primary address - transportation, food service and mailing files will be blank.")),
        ("no_state_id.csv", stu_report(
            "Students missing a state (MSIS) ID", [], [], [], [Condition("Student", "StateCode", "blank")],
            "State ID is required by OneRoster demographics, testing and most college & career platforms.")),
        ("no_student_email.csv", stu_report(
            "Students without an email in SAM", [], [], [], [Condition("Student", "EmailAddress", "blank")],
            "Only matters when District Settings uses SAM's Student.EmailAddress instead of the username pattern.")),
        ("duplicate_student_ids.csv", stu_report(
            "Duplicate student IDs", [], [], [F("Student", "StudentID", "Internal ID")],
            [Condition("Student", "StudentCode", "raw",
                       "Student.StudentCode IN (SELECT StudentCode FROM Student GROUP BY StudentCode "
                       "HAVING COUNT(*) > 1)")],
            "Two students share a Student ID - vendors will merge or reject them.")),
        ("no_homeroom.csv", stu_report(
            "Students without a homeroom this year", HR_LIVE_T[:1], HR_LIVE_L[:1], [],
            [Condition("stuHRTeacher", "HRTeacherID", "blank")],
            "No homeroom teacher on the live schedule - photo, food service and hall-pass files show it blank.")),
        ("no_classes.csv", stu_report(
            "Enrolled students with no classes on the live schedule", [], [], [],
            [Condition("Student", "StudentID", "raw",
                       "NOT Student.StudentID IN (SELECT r.StudentID FROM ScheduleRoster AS r JOIN ScheduleFramework "
                       "AS f ON r.ScheduleFrameworkID = f.ScheduleFrameworkID JOIN ScheduleCourseTerm AS t ON "
                       "f.ScheduleCourseTermID = t.ScheduleCourseTermID JOIN ScheduleCourse AS c ON "
                       f"t.ScheduleCourseID = c.ScheduleCourseID WHERE c.ScheduleID IN {LIVE_SQL} AND "
                       "(r.WithdrawnDate IS NULL))")],
            "Enrolled but not scheduled - these students get no LMS / app classes.")),
    ]
    no_teacher = query("Live sections without a teacher", SEC_T, SEC_L,
                       [F("Schedule", "SchoolID", "School ID"), F("ScheduleFramework", "ScheduleFrameworkID", "Section ID"),
                        class_title("Class"), F("Course", "CourseCode", "Course Code")],
                       [LIVE, Condition("ScheduleFramework", "TeacherID", "blank")], distinct=True)
    no_teacher.description = "Sections with no teacher are dropped by Clever, OneRoster, SDS and most LMS feeds."
    staff_no_school = query("Active staff without a primary school", ["Employee", ("PrimarySchool", "empSchool")],
                            [("Employee", "EmployeeID", "PrimarySchool", "EmployeeID", "LEFT",
                              [Condition("PrimarySchool", "PrimarySchoolFlag", "eq", "1")])],
                            [F("Employee", "EmployeeNumber", "Employee Number"),
                             F("Employee", "FirstName", "First Name", Fmt("trim")),
                             F("Employee", "LastName", "Last Name", Fmt("trim")),
                             F("Employee", "FacultyFlag", "Faculty", Fmt("yes_no"))],
                            [Condition("Employee", "TerminationDate", "blank"),
                             Condition("PrimarySchool", "empSchoolID", "blank")], sort=["Last Name"])
    staff_no_school.description = "Staff with no primary school are left out of every staff file."
    staff_no_number = query("Active staff without an employee number", ["Employee"], [],
                            [F("Employee", "EmployeeID", "Employee ID"), F("Employee", "FirstName", "First Name", Fmt("trim")),
                             F("Employee", "LastName", "Last Name", Fmt("trim"))],
                            [Condition("Employee", "TerminationDate", "blank"),
                             Condition("Employee", "EmployeeNumber", "blank")], sort=["Last Name"])
    staff_no_number.description = "Several packages use EmployeeNumber as the staff ID (Frontline, Destiny, AD)."
    reports += [("sections_no_teacher.csv", no_teacher), ("staff_no_school.csv", staff_no_school),
                ("staff_no_employee_number.csv", staff_no_number)]
    return {
        "id": "cleanup", "name": "Data cleanup reports", "kind": "tool",
        "works_with": "Fix problems in SAM before they reach vendor files",
        "description": "Run these in SAM (open one and copy the SQL, or save the package) to find the records that "
                       "cause most export-checker errors: missing primary contacts, phones, emails, addresses, "
                       "state IDs and homerooms, duplicate IDs, unscheduled students, sections without teachers "
                       "and staff without a school or employee number. Fix them in SAM, not in the CSV.",
        "spec_url": "",
        "delivery": "Run in SAM's Ad Hoc Query (or schedule as CAC Agent jobs and email the results)",
        "requires": CONTACT_REQ + ["OWNER_TYPE_STUDENT"],
        "files": [f(fn, q, q.description) for fn, q in reports],
    }


VENDOR_PLATFORMS.append(cleanup)
