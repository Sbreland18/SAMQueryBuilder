"""Emailed reports - send a CSV the CAC Agent writes (or, with the optional SAM connection, a query run
straight from SAM) to principals, clerks or the data team on a schedule.

settings["report_jobs"] = [{
    "name": "Weekly cleanup - West High", "source": "file" | "query",
    "csv_path": "C:\\SAM Exports\\Cleanup\\contact_no_phone.csv",  # source = file
    "sql": "SELECT ...",                                             # source = query (needs the SAM connection)
    "to": "principal@x.org, clerk@x.org", "subject": "", "note": "",
    "frequency": "weekly" | "daily", "day": "MON", "time": "07:00",
    "skip_empty": True, "max_body_rows": 25 }]
Run headless (Windows Task Scheduler):  "SAM Ad Hoc Query Builder.exe" --report "Weekly cleanup - West High"
"""
from __future__ import annotations

import csv
import datetime as dt
import html as _html
import io
import subprocess
import sys
from pathlib import Path

from .app_config import APP_NAME

TASK_PREFIX = "SAM Ad Hoc Query Builder - Report "
DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
DEFAULT_JOB = {"name": "", "source": "file", "csv_path": "", "sql": "", "to": "", "subject": "", "note": "",
               "frequency": "weekly", "day": "MON", "time": "07:00", "skip_empty": True, "max_body_rows": 25}


def new_job(name="New report") -> dict:
    j = dict(DEFAULT_JOB)
    j["name"] = name
    return j


def get_data(job: dict, settings: dict) -> tuple[list[str], list[list], str]:
    """(headings, rows, where it came from)."""
    if job.get("source") == "query":
        from . import samdb
        if not samdb.enabled(settings):
            raise RuntimeError("This report runs a query, but the SAM database connection is turned off.")
        res = samdb.run(settings, job.get("sql", ""), max_rows=100000, count=False)
        return res["headings"], res["rows"], "SAM (read-only query)"
    p = Path(job.get("csv_path") or "")
    if not p.is_file():
        raise FileNotFoundError(f"Report file not found: {p}")
    age = dt.datetime.now() - dt.datetime.fromtimestamp(p.stat().st_mtime)
    with open(p, newline="", encoding="utf-8-sig", errors="replace") as fh:
        rows = [r for r in csv.reader(fh)]
    head, body = (rows[0], rows[1:]) if rows else ([], [])
    body = [r for r in body if any(c.strip() for c in r)]
    src = f"{p.name} (updated {age.days} day(s) ago)" if age.days >= 1 else f"{p.name} (updated today)"
    return head, body, src


def build_message(job: dict, head: list, rows: list, src: str) -> tuple[str, str, str, bytes]:
    """(subject, text body, html body, csv bytes)."""
    n = len(rows)
    subject = job.get("subject") or f"{job['name']}: {n:,} row{'s' if n != 1 else ''}"
    shown = rows[: int(job.get("max_body_rows") or 25)]
    note = job.get("note", "")
    text = [note, "", f"{n:,} row(s) from {src}.", ""] if note else [f"{n:,} row(s) from {src}.", ""]
    if shown:
        text.append(" | ".join(head))
        text += [" | ".join("" if v is None else str(v) for v in r) for r in shown]
        if n > len(shown):
            text.append(f"... {n - len(shown):,} more in the attached file.")
    text += ["", f"Sent by {APP_NAME}."]
    cells = "".join(f"<th>{_html.escape(str(h))}</th>" for h in head)
    trs = "".join("<tr>" + "".join(f"<td>{_html.escape('' if v is None else str(v))}</td>" for v in r) + "</tr>"
                  for r in shown)
    html = (f"<div style='font-family:Segoe UI,Arial;font-size:10pt'>"
            f"{'<p>' + _html.escape(note) + '</p>' if note else ''}<p><b>{n:,}</b> row(s) from "
            f"{_html.escape(src)}.</p>"
            f"<table border=1 cellpadding=4 cellspacing=0 style='border-collapse:collapse;font-size:9pt'>"
            f"<tr style='background:#EEF2F7'>{cells}</tr>{trs}</table>"
            + (f"<p>... {n - len(shown):,} more in the attached file.</p>" if n > len(shown) else "")
            + f"<p style='color:#718096'>Sent by {APP_NAME}.</p></div>")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(head)
    w.writerows(rows)
    return subject, "\n".join(text), html, buf.getvalue().encode("utf-8-sig")


def run_job(job: dict, settings: dict) -> str:
    from . import alerts
    from .audit import record
    head, rows, src = get_data(job, settings)
    if not rows and job.get("skip_empty", True):
        return f"'{job['name']}': no rows - nothing sent."
    subject, text, html, data = build_message(job, head, rows, src)
    fname = "".join(ch for ch in job["name"] if ch.isalnum() or ch in " -_").strip() or "report"
    sent = alerts.send_email(alerts.get(settings), subject, text, to=job.get("to", ""),
                             attachments=[(f"{fname} {dt.date.today():%Y-%m-%d}.csv", data, "text/csv")], html=html)
    if not sent:
        raise RuntimeError("Email is not set up - add the SMTP server in Tools > Upload alerts, and recipients.")
    record("Report emails", f"Sent '{job['name']}' ({len(rows):,} rows) to {job.get('to')}")
    return f"'{job['name']}': sent {len(rows):,} row(s) to {job.get('to')}."


# ----------------------------------------------------------------------------- scheduling
def launch_command(job_name: str) -> list[str]:
    from .uploader import launch_args
    return launch_args("--report", job_name)


def schedule(job: dict) -> str:
    if sys.platform != "win32":
        raise RuntimeError("Scheduling uses Windows Task Scheduler (run this on the Windows PC).")
    tr = " ".join(f'"{c}"' for c in launch_command(job["name"]))
    from .districts import task_label
    args = ["schtasks", "/Create", "/F", "/TN", TASK_PREFIX + task_label(job["name"]), "/TR", tr, "/ST",
            job.get("time") or "07:00"]
    if job.get("frequency") == "daily":
        args += ["/SC", "DAILY"]
    else:
        args += ["/SC", "WEEKLY", "/D", job.get("day") or "MON"]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr).strip())
    return (r.stdout + r.stderr).strip()


def unschedule(job: dict) -> str:
    if sys.platform != "win32":
        return "Not on Windows."
    from .districts import task_label
    out = []
    for tn in dict.fromkeys([TASK_PREFIX + task_label(job["name"]), TASK_PREFIX + job["name"]]):
        r = subprocess.run(["schtasks", "/Delete", "/F", "/TN", tn], capture_output=True, text=True)
        if r.returncode == 0:
            out.append((r.stdout + r.stderr).strip())
    return "\n".join(out) or "No schedule found."


def headless(name: str) -> int:
    from .paths import load_settings
    settings = load_settings()
    job = next((j for j in settings.get("report_jobs", []) if j.get("name") == name), None)
    if not job:
        if sys.stdout:
            print(f"No report named {name!r}")
        return 2
    try:
        msg = run_job(job, settings)
        if sys.stdout:
            print(msg)
        return 0
    except Exception as e:  # noqa: BLE001
        try:
            from . import alerts
            alerts.notify(settings, f"[{APP_NAME}] Report '{name}' FAILED", str(e))
        except Exception:
            pass
        if sys.stdout:
            print(f"FAILED: {e}")
        return 1
