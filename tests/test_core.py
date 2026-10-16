import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sam_qb.catalog import Catalog  # noqa: E402
from sam_qb.query_model import (QueryDef, OutColumn, Fmt, Part, Link, FilterGroup, Condition, SortItem,  # noqa: E402
                                generate_sql, validate, condition_sql, apply_formats)

CAT = Catalog.load(ROOT / "data" / "catalog.json")


def test_catalog_loaded():
    assert CAT.has_table("Student")
    assert "StudentID" in CAT.columns("Student")
    assert len(CAT.tables) > 900


def test_student_to_course_uses_schedule_roster():
    q = QueryDef()
    q.add_table("Student")
    q.add_table("Course")
    _, added, problems = CAT.suggest_links(q)
    assert not problems
    assert "ScheduleRoster" in added and "ScheduleFramework" in added
    errors, _ = validate(q, CAT)
    assert not any("not linked" in e for e in errors)


def test_homeroom_link():
    q = QueryDef()
    q.add_table("Student")
    q.add_table("Employee")
    CAT.suggest_links(q)
    sql = generate_sql(q)
    assert "stuHRTeacher.HRTeacherID = Employee.EmployeeID" in sql or "Employee.EmployeeID = stuHRTeacher.HRTeacherID" in sql


def test_unlinked_is_error():
    q = QueryDef()
    q.add_table("Student")
    q.add_table("Employee")
    q.columns.append(OutColumn("field", "Student", "LastName", "Last"))
    errors, _ = validate(q, CAT)
    assert any("not linked" in e for e in errors)


def test_quotes_escaped():
    c = Condition("Student", "LastName", "eq", "O'Neal")
    assert condition_sql(c) == "Student.LastName = 'O''Neal'"
    c = Condition("Student", "LastName", "starts", "50%_")
    assert "LIKE '50[%][_]%'" in condition_sql(c)


def test_in_list_and_between():
    assert condition_sql(Condition("Student", "ADAGrade", "in", "09, 10,11")) == \
        "Student.ADAGrade IN ('09', '10', '11')"
    assert "BETWEEN '2026-08-01' AND '2026-12-31'" in condition_sql(
        Condition("AttendanceDaily", "AttendanceDate", "between", "2026-08-01", "2026-12-31"))


def test_email_custom_column():
    col = OutColumn("custom", heading="Email", parts=[
        Part("field", "Student", "FirstName", formats=[Fmt("left", "1"), Fmt("lower")]),
        Part("field", "Student", "LastName", formats=[Fmt("lower"), Fmt("remove_spaces")]),
        Part("text", value="@x.k12.ms.us")])
    q = QueryDef(columns=[col])
    q.add_table("Student")
    sql = generate_sql(q, header=False)
    assert "CONCAT(LOWER(LEFT(Student.FirstName, 1)), REPLACE(LOWER(Student.LastName), ' ', ''), '@x.k12.ms.us')" in sql


def test_left_join_flips_when_needed():
    q = QueryDef()
    q.add_table("Student")
    q.add_table("lookupADAGrade")
    # link written "backwards": lookup on the left, student not yet placed on the right
    q.links.append(Link("lookupADAGrade", "Val", "Student", "ADAGrade", "RIGHT"))
    q.columns.append(OutColumn("field", "Student", "LastName", "Last"))
    sql = generate_sql(q, header=False)
    assert "LEFT JOIN lookupADAGrade" in sql


def test_filter_groups_and_or():
    q = QueryDef()
    q.add_table("Student")
    q.columns.append(OutColumn("field", "Student", "LastName", "Last"))
    q.filters = [FilterGroup("ANY", [Condition("Student", "LastName", "starts", "A"),
                                     Condition("Student", "LastName", "starts", "B")]),
                 FilterGroup("ALL", [Condition("Student", "GenderCode", "eq", "M")])]
    sql = generate_sql(q, header=False)
    assert "WHERE (Student.LastName LIKE 'A%' OR Student.LastName LIKE 'B%')\n  AND Student.GenderCode = 'M'" in sql


def test_roundtrip_and_templates_valid():
    data = json.loads((ROOT / "data" / "templates.json").read_text())
    assert data["templates"]
    for t in data["templates"]:
        q = QueryDef.from_dict(t)
        q2 = QueryDef.from_json(q.to_json())
        assert generate_sql(q) .split("\n", 3)[3] == generate_sql(q2).split("\n", 3)[3]
        errors, _ = validate(q, CAT)
        assert not errors, (q.name, errors)


def test_sort_distinct_top():
    q = QueryDef(distinct=True, top=50)
    q.add_table("Student")
    q.columns.append(OutColumn("field", "Student", "LastName", "Last Name"))
    q.sort = [SortItem("Last Name", True)]
    sql = generate_sql(q, header=False)
    assert sql.startswith("SELECT DISTINCT TOP 50")
    assert "ORDER BY [Last Name] DESC" in sql


def test_strip_zeros_format():
    assert "PATINDEX('%[^0]%'" in apply_formats("Student.StateCode", [Fmt("strip_zeros")])


def test_sample_preview_all_templates():
    from sam_qb.preview import run_preview
    data = json.loads((ROOT / "data" / "templates.json").read_text())
    for t in data["templates"]:
        r = run_preview(QueryDef.from_dict(t), CAT)
        assert not r.error, (t["name"], r.error)
        assert r.rows, t["name"]
        assert r.headings == [c["heading"] for c in t["columns"]]


def test_sample_preview_filters_and_formats():
    from sam_qb.preview import run_preview
    q = QueryDef()
    q.add_table("Student")
    q.columns = [OutColumn("field", "Student", "LastName", "Last"),
                 OutColumn("field", "Student", "StateCode", "SC", [Fmt("strip_zeros")])]
    q.filters = [FilterGroup("ALL", [Condition("Student", "LastName", "starts", "B")])]
    q.sort = [SortItem("Last")]
    r = run_preview(q, CAT)
    assert not r.error and r.rows
    assert all(row[0].startswith("B") for row in r.rows)
    assert all(not row[1].startswith("0") for row in r.rows)
    q.sql_override = "SELECT 1"
    assert run_preview(q, CAT).error


def test_export_packages_valid_sql_and_preview():
    from sam_qb.district import expand
    from sam_qb.preview import run_preview
    data = json.loads((ROOT / "data" / "exports.json").read_text())
    assert {p["id"] for p in data["platforms"]} >= {"clever", "oneroster11", "sds21", "google", "canvas", "nwea"}
    owner = {"district": {"owner_type_student": "1", "owner_type_contact": "2", "owner_type_employee": "3",
                          "act_org_code": "250000", "account_password_prefix": "X#", "ad_student_ou": "OU=S", "ad_staff_ou": "OU=T", "online_course_keyword": "Online",
                          "cb_ai_code": "250000", "renaissance_course_keyword": "English", "cte_course_codes": "C1"}}
    for p in data["platforms"]:
        for fe in p["files"]:
            q = expand(fe["query"], owner)
            errors, _ = validate(q, CAT)
            assert not errors, (p["id"], fe["file"], errors)
            r = run_preview(q, CAT)
            assert not r.error, (p["id"], fe["file"], r.error)
            assert r.headings == [c["heading"] for c in fe["query"]["columns"]]


def test_district_username_patterns():
    from sam_qb.district import expand
    from sam_qb.preview import run_preview
    data = json.loads((ROOT / "data" / "exports.json").read_text())
    google = next(p for p in data["platforms"] if p["id"] == "google")
    q = expand(google["files"][1]["query"], {"district": {"staff_username_pattern": "flast", "staff_email_domain": "x.org"}})
    r = run_preview(q, CAT)
    emails = [row[2] for row in r.rows]
    assert emails and all(e.endswith("@x.org") and "." not in e.split("@")[0] for e in emails)


def test_union_sql():
    q = QueryDef()
    q.add_table("Student")
    q.columns = [OutColumn("field", "Student", "StudentCode", "id")]
    p2 = QueryDef(name="Teachers")
    p2.add_table("Employee")
    p2.columns = [OutColumn("field", "Employee", "EmployeeNumber", "id")]
    q.union_parts = [p2]
    q.sort = [SortItem("id")]
    sql = generate_sql(q, header=False)
    assert "UNION ALL" in sql and sql.strip().endswith("ORDER BY [id]")
    p2.columns.append(OutColumn("field", "Employee", "LastName", "x"))
    errors, _ = validate(q, CAT)
    assert any("same number of columns" in e for e in errors)


def test_owner_type_required():
    from sam_qb.district import expand
    data = json.loads((ROOT / "data" / "exports.json").read_text())
    ps = next(p for p in data["platforms"] if p["id"] == "parentsquare")
    fe = next(f for f in ps["files"] if f["file"] == "parents.csv")
    errors, _ = validate(expand(fe["query"], {}), CAT)
    assert any("Owner type code - Contact" in e for e in errors)
    q = expand(fe["query"], {"district": {"owner_type_contact": "C"}})
    sql = generate_sql(q)
    assert "OwnerType = 'C'" in sql and "{{" not in sql


def test_assistant_examples_build_valid_queries():
    from sam_qb.assistant import build_from_text, EXAMPLES
    from sam_qb.preview import run_preview
    s = {"district": {"owner_type_student": "1", "owner_type_contact": "2", "owner_type_employee": "3",
                      "enrolled_status_codes": "E"}}
    for ex in EXAMPLES:
        p = build_from_text(ex, CAT, s)
        errors, _ = validate(p.query, CAT)
        assert not errors, (ex, errors)
        assert not run_preview(p.query, CAT).error, ex


def test_assistant_understands_filters():
    from sam_qb.assistant import build_from_text
    p = build_from_text("girls in 3rd and 4th grade at Westside Elementary with homeroom teacher sorted by teacher", CAT, {})
    conds = {(c.column, c.op, c.value) for g in p.query.filters for c in g.conditions}
    assert ("ADAGrade", "in", "03, 04") in conds
    assert ("GenderCode", "eq", "F") in conds
    assert ("SchoolName", "contains", "Westside Elementary") in conds
    assert any(c.heading == "Homeroom Teacher" for c in p.query.columns)
    assert p.query.sort[0].heading == "Homeroom Teacher"
    # owner type missing -> flagged, not silently wrong
    p2 = build_from_text("students with parent phone numbers", CAT, {})
    assert any("Owner type" in u for u in p2.unsure)


def test_assistant_explicit_column_list_from_user_example():
    from sam_qb.assistant import build_from_text
    p = build_from_text("I would like a query of all 9th - 12th grade students with their homeroom, first name, "
                        "last name, studentID and email.", CAT, {})
    assert [c.heading for c in p.query.columns] == ["Homeroom Teacher", "First Name", "Last Name", "Student ID", "Email"]
    conds = {(c.column, c.op, c.value) for g in p.query.filters for c in g.conditions}
    assert ("ADAGrade", "in", "09, 10, 11, 12") in conds
    # homeroom limited to the live schedule (no duplicate rows from old years)
    assert "LiveFlag = 1" in generate_sql(p.query)


def test_assistant_conversation_and_counts():
    from sam_qb.assistant import build_conversation, build_from_text
    p = build_conversation(["seniors with their email", "also add birth date", "remove email", "only 11th grade"], CAT, {})
    heads = [c.heading for c in p.query.columns]
    assert "Birth Date" in heads and "Email" not in heads
    assert any(c.column == "ADAGrade" and c.value == "11" for g in p.query.filters for c in g.conditions)
    p = build_from_text("how many students are in each grade at each school", CAT, {})
    assert [c.heading for c in p.query.columns][:2] == ["Grade", "School"] and p.query.columns[-1].agg == "count"
    assert "GROUP BY" in generate_sql(p.query)
    p = build_from_text("students whose last name is Smith in Mrs. Jones's homeroom with emial", CAT, {})
    conds = {(c.alias, c.column, c.value) for g in p.query.filters for c in g.conditions}
    assert ("Student", "LastName", "Smith") in conds and ("HomeroomTeacher", "LastName", "Jones") in conds
    assert any(c.heading == "Email" for c in p.query.columns)


def test_validator_catches_problems(tmp_path):
    from sam_qb.validator import check_folder
    data = json.loads((ROOT / "data" / "exports.json").read_text())
    clever = next(p for p in data["platforms"] if p["id"] == "clever")
    hdr = {fe["file"]: [c["heading"] for c in fe["query"]["columns"]] for fe in clever["files"]}

    def write(name, rows):
        import csv
        with open(tmp_path / name, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(hdr[name])
            for r in rows:
                w.writerow([r.get(h, "") for h in hdr[name]])
    write("schools.csv", [{"School_id": "1", "School_name": "A", "School_number": "010"}])
    write("students.csv", [{"School_id": "1", "Student_id": "5", "Last_name": "X", "First_name": "Y", "DOB": "01/02/2015",
                            "Grade": "3", "Gender": "M"},
                           {"School_id": "1", "Student_id": "5", "Last_name": "", "First_name": "Z", "DOB": "2015-01-02",
                            "Grade": "03", "Gender": "M"}])
    write("teachers.csv", [{"School_id": "1", "Teacher_id": "9", "First_name": "T", "Last_name": "R"}])
    write("sections.csv", [{"School_id": "1", "Section_id": "77", "Teacher_id": "9"}])
    write("enrollments.csv", [{"School_id": "1", "Section_id": "77", "Student_id": "5"},
                              {"School_id": "1", "Section_id": "88", "Student_id": "5"}])
    rep = check_folder(clever, tmp_path)
    msgs = " | ".join(i.message for i in rep.errors)
    assert "Duplicate Student_id" in msgs
    assert "Required column 'Last_name' is blank" in msgs
    assert "'DOB' should be MM/DD/YYYY" in msgs
    assert "'Grade' should be one of" in msgs
    assert "Section_id values not found in sections.csv" in msgs
    # a clean set passes
    write("students.csv", [{"School_id": "1", "Student_id": "5", "Last_name": "X", "First_name": "Y",
                            "DOB": "01/02/2015", "Grade": "3", "Gender": "M"}])
    write("enrollments.csv", [{"School_id": "1", "Section_id": "77", "Student_id": "5"}])
    assert check_folder(clever, tmp_path).ok


def test_sql_import_round_trip_all_templates_and_exports():
    from sam_qb.sql_import import import_sql
    from sam_qb.district import expand
    s = {"district": {"owner_type_student": "1", "owner_type_contact": "2", "owner_type_employee": "3",
                      "online_course_keyword": "Online", "account_password_prefix": "X#", "ad_student_ou": "OU=S",
                      "ad_staff_ou": "OU=T", "act_org_code": "1", "cb_ai_code": "250000",
                      "renaissance_course_keyword": "English", "cte_course_codes": "C1"}}
    qs = [QueryDef.from_dict(t) for t in json.loads((ROOT / "data" / "templates.json").read_text())["templates"]]
    qs += [expand(fe["query"], s) for p in json.loads((ROOT / "data" / "exports.json").read_text())["platforms"]
           for fe in p["files"]]
    for q in qs:
        sql = generate_sql(q, header=False)
        q2, _ = import_sql(sql, CAT)
        assert generate_sql(q2, header=False) == sql, q.name


def test_sql_import_legacy_query():
    from sam_qb.sql_import import import_sql
    q, notes = import_sql("SELECT s.StudentCode, s.LastName + ', ' + s.FirstName AS Name, "
                          "CASE WHEN s.GenderCode='M' THEN 'Boy' ELSE 'Girl' END AS G FROM dbo.student s "
                          "JOIN stuSchool ss ON ss.StudentID = s.StudentID WHERE s.ADAGrade IN ('09','10') "
                          "AND s.LastName LIKE 'A%' ORDER BY Name", CAT)
    assert [t.table for t in q.tables] == ["Student", "stuSchool"]
    assert [c.kind for c in q.columns] == ["field", "custom", "raw"]
    conds = {(c.column, c.op, c.value) for g in q.filters for c in g.conditions}
    assert ("ADAGrade", "in", "09, 10") in conds and ("LastName", "starts", "A") in conds
    assert q.sort[0].heading == "Name"
    q, notes = import_sql("WITH x AS (SELECT 1 a) SELECT * FROM x", CAT)
    assert q.sql_override and notes


def test_new_export_packages_present_and_checked():
    data = json.loads((ROOT / "data" / "exports.json").read_text())
    ids = {p["id"] for p in data["platforms"]}
    assert {"raptor", "incidentiq", "pspa", "xello", "naviance", "schoolinks", "mtss", "frontline", "dragonfly",
            "act_sdu"} <= ids
    for p in data["platforms"]:
        if p.get("kind") != "tool":
            assert p.get("rules"), p["id"]


def test_privacy_levels():
    from sam_qb import privacy
    assert privacy.classify("Student", "SSN") == "restricted"
    assert privacy.classify("Student", "SPEDStatus") == "protected"
    assert privacy.classify("DisciplineIncident", "IncidentDate") == "protected"
    assert privacy.classify("DisciplineIncident", "DisciplineIncidentID") is None
    assert privacy.classify("Student", "DOB") == "personal"
    assert privacy.classify("Student", "LastName") is None
    q = QueryDef()
    q.add_table("Student")
    q.columns = [OutColumn("field", "Student", "SSN", "SSN"), OutColumn("field", "Student", "LastName", "Last")]
    _, warnings = validate(q, CAT)
    assert any("restricted" in w for w in warnings)
    assert "Restricted" in privacy.html(q)


def test_assistant_feedback_roundtrip(tmp_path, monkeypatch):
    from sam_qb import feedback
    from sam_qb.assistant import build_from_text
    monkeypatch.setattr(feedback, "feedback_file", lambda: tmp_path / "fb.jsonl")
    plan = build_from_text("students in 9th grade with birth date", CAT, {})
    feedback.record(["students in 9th grade"], plan, False, "wanted 9-12")
    rows = feedback.load()
    assert rows and rows[0]["expected"] == "wanted 9-12" and not rows[0]["good"]
    out = tmp_path / "export.jsonl"
    assert feedback.export_to(out) == 1 and out.read_text().strip()


def test_export_school_filter():
    from sam_qb.exports import build_query, load_platforms
    plats = {p["id"]: p for p in json.loads((ROOT / "data" / "exports.json").read_text())["platforms"]}
    s = {"district": {"owner_type_student": "1", "owner_type_contact": "2", "owner_type_employee": "3"},
         "schools": [{"id": "12", "name": "West High"}], "export_schools": {"pspa": ["12"], "clever": ["12", "14"]}}
    q = build_query(plats["pspa"], plats["pspa"]["files"][0], s)
    sql = generate_sql(q, header=False)
    assert "stuSchool.SchoolID IN ('12')" in sql and "empSchool.SchoolID IN ('12')" in sql
    assert "West High" in q.description
    secs = next(f for f in plats["clever"]["files"] if f["file"] == "sections.csv")
    assert "Schedule.SchoolID IN ('12', '14')" in generate_sql(build_query(plats["clever"], secs, s), header=False)
    assert "SchoolID IN" not in generate_sql(build_query(plats["nwea"], plats["nwea"]["files"][0], s), header=False)


def _fake_platform():
    return {"id": "fake", "name": "Fake", "files": [{"file": "students.csv", "query": {}}], "rules": {}}


def test_safety_net_and_folder_delivery(tmp_path, monkeypatch):
    from sam_qb import uploader, alerts
    monkeypatch.setattr(uploader, "user_dir", lambda: tmp_path / "user")
    monkeypatch.setattr(alerts, "notify_run", lambda *a, **k: None)
    monkeypatch.setattr(uploader, "_clear_override", lambda name: None)
    src, dest = tmp_path / "src", tmp_path / "dest"
    src.mkdir()
    dest.mkdir()
    prof = uploader.new_profile()
    prof.update(name="T", platform_id="fake", local_folder=str(src), method="folder", dest_folder=str(dest),
                check_first=False, archive=False)
    plats = [_fake_platform()]
    (src / "students.csv").write_text("id\n" + "\n".join(str(i) for i in range(100)) + "\n")
    ok, _ = uploader.run_profile(prof, plats)
    assert ok and (dest / "students.csv").exists()
    assert uploader.load_history("T")["last_good_counts"]["students.csv"] == 100
    (src / "students.csv").write_text("id\n" + "\n".join(str(i) for i in range(50)) + "\n")
    ok, text = uploader.run_profile(prof, plats)
    assert not ok and "SAFETY NET" in text and "dropped from 100 to 50" in text
    assert uploader.load_history("T")["runs"][-1]["status"] == "held"
    (src / "students.csv").write_text("id\n")
    ok, text = uploader.run_profile(prof, plats)
    assert not ok and "has no rows" in text
    (src / "students.csv").write_text("id\n" + "\n".join(str(i) for i in range(50)) + "\n")
    prof["override_once"] = True
    ok, _ = uploader.run_profile(prof, plats)
    assert ok and not prof["override_once"]
    assert uploader.load_history("T")["last_good_counts"]["students.csv"] == 50
    rows = uploader.status_rows({"upload_profiles": [prof]})
    assert rows[0]["last"]["status"] == "ok"


def test_alert_webhook_payloads_and_rules():
    from sam_qb import alerts
    teams = alerts.webhook_payload("https://prod-12.westus.logic.azure.com/workflows/x", "S", "body")
    assert teams["attachments"][0]["content"]["type"] == "AdaptiveCard"
    assert "text" in alerts.webhook_payload("https://hooks.slack.com/services/x", "S", "body")
    assert alerts.should_notify({"notify_on": "failure"}, "held")
    assert not alerts.should_notify({"notify_on": "failure"}, "ok")
    assert alerts.should_notify({"notify_on": "always"}, "ok")
    assert not alerts.should_notify({"notify_on": "never"}, "failed")


def test_district_override_roundtrip(tmp_path, monkeypatch):
    import sam_qb.paths as P
    from sam_qb import exports
    monkeypatch.setattr(P, "user_dir", lambda: tmp_path)
    plats = {p["id"]: p for p in json.loads((ROOT / "data" / "exports.json").read_text())["platforms"]}
    p = plats["pbis_rewards"]
    fe = p["files"][0]
    s = {"district": {"owner_type_contact": "2"}}
    q = exports.build_query(p, fe, s)
    q.columns[0].heading = "Given Name"
    exports.save_override(p, fe, q)
    assert exports.override_state(p, fe) == "custom"
    assert exports.build_query(p, fe, s).columns[0].heading == "Given Name"
    changed = dict(fe, query=dict(fe["query"], distinct=not fe["query"].get("distinct")))
    assert exports.override_state(p, changed) == "custom-outdated"
    assert exports.remove_override(p, fe) and exports.override_state(p, fe) == ""


def test_register_and_rollover():
    import datetime as dt
    from sam_qb import register, rollover
    plats = json.loads((ROOT / "data" / "exports.json").read_text())["platforms"]
    s = {"vendor_register": {"clever": {"in_use": True, "agreement": "signed", "expires": "2026-11-01"}},
         "upload_profiles": [{"name": "x", "platform_id": "mtss"}], "district": {"school_year": "2027"}}
    assert register.in_use_ids(s) == {"clever", "mtss"}
    assert "Expires in" in register.status(register.entry(s, "clever"), dt.date(2026, 10, 16))[0]
    assert register.status({"agreement": "signed", "expires": "2026-01-01"}, dt.date(2026, 10, 16))[0].startswith("EXPIRED")
    html = register.html_report(s, plats)
    assert "Clever" in html and "Protected program data" in html
    rollover.set_done(s, "codes", True)
    assert "codes" in rollover.done(s)
    assert rollover.expected_year(dt.date(2026, 8, 1)) == 2027


def test_cleanup_and_categories():
    plats = {p["id"]: p for p in json.loads((ROOT / "data" / "exports.json").read_text())["platforms"]}
    assert plats["cleanup"]["kind"] == "tool" and len(plats["cleanup"]["files"]) >= 10
    assert all(p.get("category") and p["category"] != "Other" for p in plats.values())
    for pid in ("apple_asm", "schoolstatus", "active_directory", "entra", "pbis_rewards", "ellevation", "emergency"):
        assert plats[pid].get("rules"), pid
    assert "Import-ADUsers.ps1" in plats["active_directory"]["static_files"]


def test_samdb_read_only_guard():
    from sam_qb.samdb import is_read_only, strip_order_by
    from sam_qb.district import expand
    s = {"district": {"owner_type_student": "1", "owner_type_contact": "2", "owner_type_employee": "3",
                      "enrolled_status_codes": "E"}}
    for p in json.loads((ROOT / "data" / "exports.json").read_text())["platforms"]:
        for fe in p["files"]:
            ok, why = is_read_only(generate_sql(expand(fe["query"], s)))
            assert ok, (p["id"], fe["file"], why)
    for bad in ("DELETE FROM Student", "SELECT 1; DROP TABLE Student", "SELECT * INTO x FROM Student",
                "WITH a AS (SELECT 1 AS x) UPDATE Student SET LastName = 'x'", "EXEC sp_who",
                "SELECT * FROM OPENROWSET('x','y','z')", "  ", "SELECT 1 WAITFOR DELAY '00:01'",
                "select xp_cmdshell('dir')"):
        assert not is_read_only(bad)[0], bad
    assert is_read_only("SELECT [Delete Date], 'update; drop' AS note FROM Student -- delete")[0]
    assert strip_order_by("SELECT a FROM t ORDER BY a") == "SELECT a FROM t"
    assert strip_order_by("SELECT TOP 5 a FROM (SELECT TOP 5 a FROM t ORDER BY a) q") .endswith("q")


def test_file_diff(tmp_path):
    from sam_qb.filediff import diff_files, write_report
    a, b = tmp_path / "old.csv", tmp_path / "new.csv"
    a.write_text("Student ID,Name,Grade\n1,Ann,09\n2,Bob,10\n3,Cy,11\n")
    b.write_text("Student ID,Name,Grade\n1,Ann,10\n3,Cy,11\n4,Dee,09\n")
    d = diff_files(a, b)
    assert d.key == ["Student ID"]
    assert [r["Student ID"] for r in d.added] == ["4"] and [r["Student ID"] for r in d.removed] == ["2"]
    assert d.changed == [("1", {"Grade": ("09", "10")})]
    write_report([d], tmp_path / "r.csv")
    assert "removed" in (tmp_path / "r.csv").read_text()


def test_change_log_and_backup(tmp_path, monkeypatch):
    import sam_qb.paths as P
    from sam_qb import audit, backup
    monkeypatch.setattr(P, "user_dir", lambda: tmp_path / "u")
    monkeypatch.setattr(P, "settings_path", lambda: tmp_path / "u" / "settings.json")
    monkeypatch.setattr(P, "queries_dir", lambda: tmp_path / "q")
    (tmp_path / "u").mkdir()
    (tmp_path / "q").mkdir()
    s = {"district": {"school_year": "2026"}, "upload_profiles": [{"name": "Clever", "password": "dpapi:xyz",
                                                                    "host": "a"}]}
    P.save_settings(s)
    s["district"]["school_year"] = "2027"
    s["upload_profiles"][0]["password"] = "dpapi:new"
    P.save_settings(s)
    changes = [c for e in audit.load() for c in e["changes"]]
    assert "district.school_year: '2026' -> '2027'" in changes
    assert any("password: (secret changed)" in c for c in changes) and not any("dpapi:new" in c for c in changes)
    (tmp_path / "q" / "My query.samq").write_text("{}")
    out = tmp_path / "b.samqb-backup"
    backup.export_backup(out, s, include_queries=True)
    import zipfile
    data = json.loads(zipfile.ZipFile(out).read("settings.json"))
    assert data["upload_profiles"][0]["password"] == ""
    here = {"upload_profiles": [{"name": "Clever", "password": "dpapi:local", "host": "old"}]}
    new, done = backup.import_backup(out, here, {"district", "uploads", "queries"})
    assert new["district"]["school_year"] == "2027"
    assert new["upload_profiles"][0]["password"] == "dpapi:local" and new["upload_profiles"][0]["host"] == "a"
    assert (tmp_path / "q" / "My query (restored).samq").exists()


def test_report_email(tmp_path, monkeypatch):
    from sam_qb import reports, alerts
    f = tmp_path / "contact_no_phone.csv"
    f.write_text("Student ID,Name\n1,Ann\n2,Bob\n")
    sent = {}
    monkeypatch.setattr(alerts, "send_email", lambda a, subj, body, to=None, attachments=(), html="": sent.update(
        subj=subj, to=to, att=attachments, html=html) or True)
    job = dict(reports.new_job("Cleanup"), csv_path=str(f), to="p@x.org")
    msg = reports.run_job(job, {})
    assert "2 row(s)" in msg and sent["to"] == "p@x.org" and sent["att"][0][2] == "text/csv"
    assert "<td>Ann</td>" in sent["html"]
    f.write_text("Student ID,Name\n")
    assert "nothing sent" in reports.run_job(job, {})


def test_round4_packages():
    plats = {p["id"]: p for p in json.loads((ROOT / "data" / "exports.json").read_text())["platforms"]}
    for pid in ("talkingpoints", "remind", "renaissance", "assessment_demographics", "college_board", "sped_case",
                "health_office", "alexandria", "id_cards", "substitutes", "devices", "dual_enrollment",
                "cte_testing", "account_shutoff"):
        assert plats[pid].get("rules") and plats[pid]["category"] != "Other", pid
    assert [f["file"] for f in plats["remind"]["files"]] == ["schools.csv", "classes.csv", "enrollments.csv",
                                                              "users.csv", "school_enrollments.csv"]
    heads = [c["heading"] for c in plats["college_board"]["files"][0]["query"]["columns"]]
    assert heads == ["Testing AI Code", "Attending AI Code", "First Name", "Middle Initial", "Last Name",
                     "Date of Birth", "Gender", "Grade", "Test", "School Student ID", "District Student ID",
                     "State Student ID"]
    assert "Disable-ADUsers.ps1" in plats["account_shutoff"]["static_files"]


def test_samdb_run_with_fake_driver(monkeypatch):
    """Exercise samdb.run end to end with a stand-in pyodbc backed by SQLite."""
    import sqlite3
    import sys
    import types
    from sam_qb import samdb
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE Student (StudentCode TEXT, LastName TEXT)")
    db.executemany("INSERT INTO Student VALUES (?, ?)", [(str(i), f"L{i}") for i in range(30)])
    seen = []

    class Cur:
        def execute(self, sql):
            seen.append(sql)
            self._c = db.execute(sql) if not sql.startswith("SET ") else None
            self.description = self._c.description if self._c else None
            return self

        def fetchmany(self, n):
            return self._c.fetchmany(n)

        def fetchone(self):
            return self._c.fetchone()

    class Con:
        timeout = 0

        def cursor(self):
            return Cur()

        def close(self):
            pass

    fake = types.SimpleNamespace(connect=lambda cs, **k: (seen.append(("connect", cs, k)), Con())[1],
                                 drivers=lambda: ["ODBC Driver 18 for SQL Server"])
    monkeypatch.setitem(sys.modules, "pyodbc", fake)
    s = {"sam_connection": {"enabled": True, "server": "x", "database": "SAMS", "max_rows": 10}}
    res = samdb.run(s, "SELECT StudentCode, LastName FROM Student ORDER BY LastName")
    assert res["headings"] == ["StudentCode", "LastName"] and len(res["rows"]) == 10
    assert res["truncated"] and res["total"] == 30
    con = next(x for x in seen if isinstance(x, tuple))
    assert "ApplicationIntent=ReadOnly" in con[1] and con[2]["readonly"] is True
    assert "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED" in seen
    import pytest
    with pytest.raises(ValueError):
        samdb.run(s, "DELETE FROM Student")


def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("SAMQB_DISTRICT", raising=False)


def test_districts_are_separate(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    import sam_qb.paths as P
    from sam_qb import districts
    P.save_settings({"district": {"district_name": "Hancock", "staff_email_domain": "h.org"}, "ai_api_key": "k"},
                    audit=False)
    did = districts.add_district("Pearl River", P.load_settings(), ["district"])
    assert P.user_dir() == P.root_dir()
    districts.switch_to(did)
    assert P.user_dir() == P.root_dir() / "districts" / did
    s = P.load_settings()
    assert s["district"]["district_name"] == "Pearl River" and s["district"]["staff_email_domain"] == "h.org"
    assert s["ai_api_key"] == "k" and "upload_profiles" not in s
    from sam_qb.uploader import launch_args
    assert launch_args("--upload", "Clever")[-4:] == ["--district", did, "--upload", "Clever"]
    assert districts.task_label("Clever") == "Pearl River - Clever"
    monkeypatch.setenv("SAMQB_DISTRICT", "default")
    assert P.load_settings()["district"]["district_name"] == "Hancock"
    monkeypatch.delenv("SAMQB_DISTRICT")
    districts.switch_to("default")
    districts.delete_district(did)
    assert [d["id"] for d in districts.list_districts()] == ["default"]


def test_template_builder_package(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    from sam_qb import template_builder as tb
    from sam_qb.district import expand
    from sam_qb.exports import build_query, load_platforms
    from sam_qb.preview import run_preview
    heads, samples = tb.read_template("StudentID|FirstName|LastName|Grade|BirthDate|ParentEmail|School\n"
                                      "123|Ann|Lee|3|2015-04-01|a@b.org|West\n")
    assert tb.suggest_base(heads) == "students"
    m = tb.auto_map(heads, "students", samples)
    assert [x["field"] for x in m] == ["stu_id", "stu_first", "stu_last", "stu_grade_num", "stu_dob_iso", "pg_email",
                                       "sch_name"]
    m.append({"heading": "Vendor Code", "field": "__text__", "text": "HCSD", "required": False, "unique": False})
    plat = tb.make_package({"id": tb.slug("Acme Reading"), "name": "Acme Reading",
                            "files": [{"file": "acme_students.csv", "base": "students", "mapping": m}]})
    assert plat["requires"] == ["OWNER_TYPE_CONTACT"]
    assert plat["rules"]["files"]["acme_students.csv"]["unique"] == [["StudentID"]]
    assert plat["rules"]["files"]["acme_students.csv"]["formats"]["BirthDate"] == "date_iso"
    tb.save_custom(plat)
    plats = load_platforms()
    assert plats[0]["id"] == "custom-acme-reading" and plats[0]["category"] == "My packages"
    s = {"district": {"owner_type_contact": "2", "enrolled_status_codes": "E"}}
    q = build_query(plats[0], plats[0]["files"][0], s)
    errors, _ = validate(q, CAT)
    assert not errors and [c.heading for c in q.columns][-1] == "Vendor Code"
    assert not run_preview(q, CAT).error
    out = tmp_path / "acme.samqb-package"
    tb.export_package(plat, out)
    again = tb.import_package(out)
    assert again["id"] == "custom-acme-reading-2"
    assert tb.delete_custom("custom-acme-reading") and tb.delete_custom(again["id"])
    for base in tb.BASES:
        maps = [{"heading": f.label, "field": f.key} for f in tb.fields_for(base)]
        q = expand(tb.build_query_dict(base, maps, base), {"district": {"owner_type_student": "1",
                                                                        "owner_type_contact": "2",
                                                                        "owner_type_employee": "3"}})
        assert not validate(q, CAT)[0], base
        assert not run_preview(q, CAT).error, base


def test_admin_pin_signoff_health(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    from sam_qb import adminpin, signoff, health
    s = {}
    adminpin.set_pin(s, "2468")
    assert adminpin.is_set(s) and adminpin.check(s, "2468") and not adminpin.check(s, "1111")
    assert "2468" not in json.dumps(s)
    adminpin.set_pin(s, None)
    assert not adminpin.is_set(s)
    signoff.save(s, "clever", sample_sent="2026-09-01")
    assert "waiting" in signoff.status(s, "clever")[0]
    signoff.save(s, "clever", approved="2026-09-15", contact="Clever support")
    assert "approved" in signoff.status(s, "clever")[0]
    s["vendor_register"] = {"clever": {"in_use": True, "agreement": "signed", "expires": "2020-01-01"}}
    d = health.collect(s)
    assert d["agreements"][0]["vendor"] == "Clever" and d["problems"] >= 1
    assert "District health report" in health.html_report(s)


def test_signing_command():
    import sys as _s
    _s.path.insert(0, str(ROOT))
    from tools.signing import mask, sign_command
    a = sign_command({"signtool": "signtool.exe", "mode": "store", "thumbprint": "AB CD"}, "app.exe")
    assert a[:2] == ["signtool.exe", "sign"] and ["/sha1", "ABCD"] == a[a.index("/sha1"):a.index("/sha1") + 2]
    b = sign_command({"signtool": "signtool.exe", "mode": "pfx", "pfx": "c.pfx"}, "setup.exe", "pw")
    assert "pw" not in mask(b) and b[-1] == "setup.exe"


def test_username_patterns_tokens():
    from sam_qb import district as d
    assert d.example("{f}.{last}", staff=True) == "j.smith"
    assert d.example("{f}{last5}{id3}") == "jsmith234" and d.example("{first}.{last}{grad2}") == "jane.smith27"
    assert d.normalize_pattern("flast+id4") == "{f}{last}{id4}"
    assert d.pattern_errors("{x}{last}") and d.pattern_errors("jsmith") and not d.pattern_errors("s{id}")
    data = json.loads((ROOT / "data" / "exports.json").read_text())
    google = next(p for p in data["platforms"] if p["id"] == "google")
    s = {"district": {"staff_username_pattern": "{f}.{last}", "staff_email_domain": "hancockschools.net",
                      "student_username_pattern": "{first}.{last}{grad2}", "student_email_domain": "stu.org",
                      "staff_email_pattern": "{first}.{last}"}}
    from sam_qb.district import expand
    from sam_qb.preview import run_preview
    staff_q = expand(google["files"][1]["query"], s)
    stu_q = expand(google["files"][0]["query"], s)
    r = run_preview(staff_q, CAT)
    email_i = r.headings.index("Email Address [Required]")
    assert all("." in row[email_i] and row[email_i].endswith("@hancockschools.net") for row in r.rows)
    sql = generate_sql(stu_q)
    assert "OriginalGradDate" in sql and "RIGHT(CAST(YEAR(" in sql


def test_samcheck_analyzer():
    import datetime as dt
    from sam_qb import samcheck
    data = {
        "check_owner_types.csv": [{"Code": "1", "Description": "Student", "Table": "Student"},
                                  {"Code": "2", "Description": "Contact", "Table": "ContactInfo"},
                                  {"Code": "3", "Description": "Employee", "Table": "Employee"}],
        "check_owner_type_usage.csv": [{"Table": "PhoneRelationship", "OwnerType": "2", "Rows": "900"},
                                       {"Table": "EmailAddress", "OwnerType": "2", "Rows": "700"},
                                       {"Table": "AddressRelationship", "OwnerType": "1", "Rows": "800"}],
        "check_enrollment_status.csv": [{"EnrollmentStatus": "E", "Students": "800"},
                                        {"EnrollmentStatus": "W", "Students": "200"}],
        "check_live_schedules.csv": [{"SchoolID": "1", "School": "West", "SchoolActive": "1", "ScheduleCode": "2526",
                                      "BeginDate": "2025-08-01", "EndDate": "2026-05-25"}],
        "check_data_summary.csv": [{"Students": "1000", "StudentsNoPrimarySchool": "0",
                                    "StudentsSeveralPrimarySchools": "3", "StudentsWithPrimaryContact": "0",
                                    "StudentsSeveralPrimaryContacts": "0", "StudentsWithContacts": "950",
                                    "RosterRowsLive": "5000", "RosterRowsLiveWithdrawn": "0", "HomeroomRowsLive": "800",
                                    "HomeroomRowsWithCounselor": "0", "StaffActive": "90", "StaffActiveFaculty": "60",
                                    "StaffActiveNoPrimarySchool": "0", "SectionsLiveNoTeacher": "2",
                                    "RegistrationRowsLast60Days": "40", "StudentsWithEmailInSAM": "0"}],
        "check_code_values.csv": [{"Field": "Student.ADAGrade", "Value": "9", "Rows": "100"},
                                  {"Field": "Student.Flag504", "Value": "X", "Rows": "4"}],
    }
    r = samcheck.analyze(data, {"district": {"owner_type_contact": "1"}}, today=dt.date(2026, 10, 16))
    assert r.suggest["owner_type_student"] == "1" and r.suggest["owner_type_employee"] == "3"
    assert r.suggest["owner_type_contact"] == "2" and r.suggest["enrolled_status_codes"] == "E"
    text = " | ".join(f.message for f in r.findings)
    assert "last year's schedule is still live" in text and "more than one primary school" in text
    assert "No contact is marked Primary" in text and "Grade codes 9" in text and "Student.Flag504 uses X" in text
    assert "check_registration_codes.csv" in r.missing


def test_shared_library_and_learning(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    import sam_qb.paths as P
    from sam_qb import shared_library as sl, template_builder as tb
    from sam_qb.exports import load_platforms
    m = tb.auto_map(["Learner Ref", "First Name"], "students")
    assert m[0]["field"] == "__blank__"
    m[0]["field"] = "stu_id"
    assert tb.learn("students", m, {"Learner Ref": "__blank__", "First Name": "stu_first"}) == 1
    assert tb.auto_map(["Learner Ref"], "students")[0]["field"] == "stu_id"
    plat = tb.make_package({"id": "custom-acme", "name": "Acme", "files": [{"file": "a.csv", "base": "students",
                                                                             "mapping": m}]})
    pkg = tmp_path / "acme.samqb-package"
    tb.export_package(plat, pkg)
    lib = tmp_path / "shared_packages.json"
    lib.write_text(json.dumps({"data_version": "9999.1.1.1", "packages": []}))
    added = sl.add_package_file(lib, str(pkg))
    assert added["id"] == "shared-acme"
    dd = P.user_data_dir()
    (dd / "shared_packages.json").write_text(lib.read_text())
    monkeypatch.setattr(P, "bundled_data_dir", lambda: tmp_path / "nobundle")
    plats = load_platforms()
    shared = next(p for p in plats if p["id"] == "shared-acme")
    assert shared["shared"] and shared["category"] == "Shared packages"
    mine = sl.copy_to_mine(shared)
    assert mine["id"].startswith("custom-") and any(p["id"] == mine["id"] for p in load_platforms())
    sl.remove_package(lib, "shared-acme")
    assert not json.loads(lib.read_text())["packages"]


def test_ui_modules_import():
    import importlib
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    for m in ("main_window", "dialogs", "tools_dialogs", "template_builder_dialog", "setup_wizard", "upload_dialog",
              "exports_page", "sample_view", "alerts_dialog", "assistant_dialog", "codes_dialog", "home"):
        importlib.import_module(f"sam_qb.ui.{m}")
    for doc in ("Quick Start Guide.md", "Windows Test Checklist.md", "Pilot Plan.md", "CAC Agent Setup Guide.md"):
        assert (ROOT / "docs" / doc).exists()


def test_dark_mode_colors_readable():
    import re as _re
    from sam_qb.ui import style
    # every text / status color used anywhere in the app has a dark-mode translation
    used = set()
    for p in list((ROOT / "sam_qb").rglob("*.py")):
        if p.name == "style.py":
            continue
        used |= {h.upper() for h in _re.findall(r"#[0-9A-Fa-f]{6}\b", p.read_text(encoding="utf-8"))}
    keep = {"#DCE3EC", "#273A57", "#5AA3F0"}            # the dark step navigation, already dark
    missing = used - set(style.DARK_MAP) - keep
    assert not missing, missing
    # translated text colors are readable on the dark backgrounds (WCAG AA 4.5:1)
    texts = ["#B42318", "#A3302A", "#1E7B34", "#3B7A3B", "#1B2A41", "#4A5568", "#718096", "#C2410C", "#9A6700",
             "#1F5FAD", "#0B4FA0", "#6B3FA0"]
    for fg in texts:
        for bg in (style.DARK["card"], style.DARK["bg"], style.DARK["alt"]):
            assert style.contrast(style.DARK_MAP[fg], bg) >= 4.5, (fg, bg)
    for theme in (style.LIGHT, style.DARK):
        for bg in ("card", "bg", "alt", "header", "tab"):
            assert style.contrast(theme["text"], theme[bg]) >= 7, (bg,)
            assert style.contrast(theme["sub"], theme[bg]) >= 4.5, (bg,)
        assert style.contrast(theme["accent_text"], theme["accent"]) >= 4.5
    assert style.contrast(style.DARK_MAP["#1B2A41"], style.DARK_MAP["#E8F1FB"]) >= 7   # assistant summary box
    assert style.contrast(style.DARK_MAP["#C2410C"], style.DARK_MAP["#FFFBEA"]) >= 4.5  # privacy panel


def test_dark_mode_applies(tmp_path, monkeypatch):
    _isolated(tmp_path, monkeypatch)
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QLabel, QTreeWidgetItem
    from PySide6.QtGui import QColor
    from sam_qb.ui import style
    app = QApplication.instance() or QApplication([])
    style.set_pref("dark")
    assert style.apply_theme(app) == "dark"
    lb = QLabel()
    lb.setText("<span style='color:#B42318'>x</span>")
    assert "#FF8A80" in lb.text()
    it = QTreeWidgetItem(["a"])
    it.setForeground(0, QColor("#1E7B34"))
    assert it.foreground(0).color().name().upper() == "#6FD08C"
    assert style.apply_theme(app, "light") == "light"
    lb.setText("<span style='color:#B42318'>x</span>")
    assert "#B42318" in lb.text()


def test_codes_all_in_one_query_and_import(tmp_path):
    import sqlglot
    from sam_qb import codes as C, samdb
    sql = C.all_in_one_sql()
    assert samdb.is_read_only(sql)[0]
    tree = sqlglot.parse_one(C.all_in_one_sql(header=False), read="tsql")
    assert tree is not None and sql.count("UNION ALL") == len(C.ALL_LISTS) - 1
    for name, table, *_ in C._ALL_PARTS:
        assert C.ALL_LISTS[name] and f"FROM {table}" in sql
    csv = ("List,Code,Description,Extra1,Extra2\nSchools,12,Hancock High,010,HHS\nOwner types,2,Contact,Contact,\n"
           "Enrollment status,E,Enrolled,,\nAttendance codes,A,Absent,,\nAttendance codes,A,Absent,,\n")
    assert C.is_all_in_one(C._read_csv(csv))
    got = C.parse_all_in_one(csv)
    assert got["schools"] == [{"id": "12", "name": "Hancock High", "code": "010", "short": "HHS"}]
    assert got["owner_type"][0]["table"] == "Contact" and len(got["attendance"]) == 1
    h = C.helper_queries({})
    assert set(h) == set(C.HELPER_FILES) and all(samdb.is_read_only(x["sql"])[0] for x in h.values())
    files = C.save_helper_queries({}, tmp_path)
    assert files[0].name == "00 All codes in one.sql" and (tmp_path / "SAM codes queries" / "READ ME.txt").exists()
    assert len(files) == len(C.HELPER_FILES) + 2
