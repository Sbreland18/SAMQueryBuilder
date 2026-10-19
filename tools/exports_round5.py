# SAM setup check - executed inside tools/make_exports.py (shares its helpers).
# Queries that show how THIS district's SAM data is actually used, so the analyzer (sam_qb/samcheck.py) can
# confirm or correct the assumptions every package makes (owner types, enrolled code, live schedules, flags...).


def _count(heading="Rows"):
    c = C(heading)
    c.agg = "count"
    return c


def _sub(heading, sql):
    return RAW(heading, sql)


def samcheck():
    owner = query("Check - owner types", ["OwnerType"], [],
                  [F("OwnerType", "Val", "Code"), F("OwnerType", "Description", "Description", Fmt("trim")),
                   F("OwnerType", "TableName", "Table")], sort=["Code"])
    usage_parts = []
    for tbl in ("PhoneRelationship", "EmailAddress", "AddressRelationship"):
        q = query("Check - owner type usage" if not usage_parts else f"{tbl} part", [tbl], [],
                  [T("Table", tbl), F(tbl, "OwnerType", "OwnerType"), _count()])
        usage_parts.append(q)
    usage = usage_parts[0]
    usage.union_parts = usage_parts[1:]
    enroll = query("Check - enrollment status", ["Student"], [],
                   [F("Student", "EnrollmentStatus", "EnrollmentStatus"), _count("Students")], sort=["EnrollmentStatus"])
    live = query("Check - live schedules", ["Schedule", "SchoolDef"],
                 [("Schedule", "SchoolID", "SchoolDef", "SchoolID", "INNER")],
                 [F("SchoolDef", "SchoolID", "SchoolID"), F("SchoolDef", "SchoolName", "School", Fmt("trim")),
                  F("SchoolDef", "ActiveFlag", "SchoolActive"), F("Schedule", "ScheduleID", "ScheduleID"),
                  F("Schedule", "ScheduleCode", "ScheduleCode"), F("Schedule", "BeginDate", "BeginDate", Fmt("date_iso")),
                  F("Schedule", "EndDate", "EndDate", Fmt("date_iso"))],
                 [Condition("Schedule", "LiveFlag", "eq", "1")], sort=["School"])
    checks = [
        ("Students", "SELECT COUNT(*) FROM Student"),
        ("StudentsNoPrimarySchool", "SELECT COUNT(*) FROM Student AS s WHERE NOT EXISTS(SELECT 1 FROM stuSchool AS x "
                                    "WHERE x.StudentID = s.StudentID AND x.PrimarySchoolFlag = 1)"),
        ("StudentsSeveralPrimarySchools", "SELECT COUNT(*) FROM (SELECT StudentID FROM stuSchool WHERE "
                                          "PrimarySchoolFlag = 1 GROUP BY StudentID HAVING COUNT(*) > 1) AS d"),
        ("StudentsWithPrimaryContact", "SELECT COUNT(DISTINCT StudentID) FROM StudentContact WHERE PrimaryContact = 1"),
        ("StudentsSeveralPrimaryContacts", "SELECT COUNT(*) FROM (SELECT StudentID FROM StudentContact WHERE "
                                           "PrimaryContact = 1 GROUP BY StudentID HAVING COUNT(*) > 1) AS d"),
        ("StudentsWithContacts", "SELECT COUNT(DISTINCT StudentID) FROM StudentContact"),
        ("RosterRowsLive", "SELECT COUNT(*) FROM ScheduleRoster AS r JOIN ScheduleFramework AS f ON "
                           "r.ScheduleFrameworkID = f.ScheduleFrameworkID JOIN ScheduleCourseTerm AS t ON "
                           "f.ScheduleCourseTermID = t.ScheduleCourseTermID JOIN ScheduleCourse AS c ON "
                           "t.ScheduleCourseID = c.ScheduleCourseID JOIN Schedule AS s ON c.ScheduleID = s.ScheduleID "
                           "WHERE s.LiveFlag = 1"),
        ("RosterRowsLiveWithdrawn", "SELECT COUNT(*) FROM ScheduleRoster AS r JOIN ScheduleFramework AS f ON "
                                    "r.ScheduleFrameworkID = f.ScheduleFrameworkID JOIN ScheduleCourseTerm AS t ON "
                                    "f.ScheduleCourseTermID = t.ScheduleCourseTermID JOIN ScheduleCourse AS c ON "
                                    "t.ScheduleCourseID = c.ScheduleCourseID JOIN Schedule AS s ON c.ScheduleID = "
                                    "s.ScheduleID WHERE s.LiveFlag = 1 AND NOT r.WithdrawnDate IS NULL"),
        ("HomeroomRowsLive", "SELECT COUNT(*) FROM stuHRTeacher WHERE ScheduleID IN (SELECT ScheduleID FROM Schedule "
                             "WHERE LiveFlag = 1)"),
        ("HomeroomRowsWithCounselor", "SELECT COUNT(*) FROM stuHRTeacher WHERE ScheduleID IN (SELECT ScheduleID FROM "
                                      "Schedule WHERE LiveFlag = 1) AND NOT CounselorID IS NULL"),
        ("StaffActive", "SELECT COUNT(*) FROM Employee WHERE TerminationDate IS NULL"),
        ("StaffActiveFaculty", "SELECT COUNT(*) FROM Employee WHERE TerminationDate IS NULL AND FacultyFlag = 1"),
        ("StaffActiveNoPrimarySchool", "SELECT COUNT(*) FROM Employee AS e WHERE e.TerminationDate IS NULL AND NOT "
                                       "EXISTS(SELECT 1 FROM empSchool AS x WHERE x.EmployeeID = e.EmployeeID AND "
                                       "x.PrimarySchoolFlag = 1)"),
        ("SectionsLiveNoTeacher", "SELECT COUNT(*) FROM ScheduleFramework AS f JOIN ScheduleCourseTerm AS t ON "
                                  "f.ScheduleCourseTermID = t.ScheduleCourseTermID JOIN ScheduleCourse AS c ON "
                                  "t.ScheduleCourseID = c.ScheduleCourseID JOIN Schedule AS s ON c.ScheduleID = "
                                  "s.ScheduleID WHERE s.LiveFlag = 1 AND f.TeacherID IS NULL"),
        ("RegistrationRowsLast60Days", "SELECT COUNT(*) FROM StudentRegistration WHERE RegistrationDate >= "
                                       "DATEADD(DAY, -60, CAST(GETDATE() AS DATE))"),
        ("StudentsWithEmailInSAM", "SELECT COUNT(*) FROM Student WHERE NOT EmailAddress IS NULL AND "
                                   "LTRIM(RTRIM(EmailAddress)) <> ''"),
    ]
    summary = query("Check - data summary", ["SchoolDef"], [], [_sub(h, sql) for h, sql in checks])
    summary.top = 1
    summary.distinct = False
    regs = query("Check - registration codes", ["StudentRegistration"], [],
                 [F("StudentRegistration", "RegistrationCode", "RegistrationCode"),
                  F("StudentRegistration", "WithdrawlReason", "WithdrawalReason"), _count(),
                  F("StudentRegistration", "RegistrationDate", "LastUsed", Fmt("date_iso"))],
                 [Condition("StudentRegistration", "RegistrationDate", "last_days", "365")], sort=["RegistrationCode"])
    regs.columns[-1].agg = "max"
    vals = []
    for tbl, col in (("Student", "SPEDStatus"), ("Student", "GiftedStatus"), ("Student", "Flag504"),
                     ("Student", "FoodServiceCode"), ("Student", "LangBackground"), ("Student", "GenderCode"),
                     ("Student", "ADAGrade"), ("Course", "CoreCourse"), ("Course", "DualCreditReported"),
                     ("StudentContact", "CheckInOut"), ("StudentContact", "NoContact"), ("Employee", "FacultyFlag")):
        q = query("Check - code values" if not vals else f"{tbl}.{col}", [tbl], [],
                  [T("Field", f"{tbl}.{col}"), F(tbl, col, "Value"), _count()])
        vals.append(q)
    values = vals[0]
    values.union_parts = vals[1:]
    return {
        "id": "samcheck", "name": "SAM setup check", "kind": "tool",
        "works_with": "Confirms how your SAM data is set up before you rely on the export packages",
        "description": "Run these seven queries in SAM once (save each result as CSV with the file name shown), then "
                       "use Tools > SAM setup check to read the folder. It checks your owner type codes, enrolled "
                       "code, live schedules, primary school / contact flags, roster withdrawals, homerooms, staff "
                       "flags, registration (withdrawal) codes and the values used in program flags - and offers to "
                       "fix District Settings. With the optional SAM connection it runs them for you. No student "
                       "names leave SAM: the results are codes and counts only.",
        "spec_url": "",
        "delivery": "Run in SAM's Ad Hoc Query > Run Query and save as CSV",
        "files": [f("check_owner_types.csv", owner), f("check_owner_type_usage.csv", usage, "counts by table"),
                  f("check_enrollment_status.csv", enroll), f("check_live_schedules.csv", live),
                  f("check_data_summary.csv", summary, "one row of counts"),
                  f("check_registration_codes.csv", regs, "last 365 days"),
                  f("check_code_values.csv", values, "values used in flags and codes")],
    }
