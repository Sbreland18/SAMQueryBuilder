"""District health report - one page for the technology director: uploads, export-checker results, data cleanup
counts, vendor agreements and sign-off, rollover progress and recent changes. Saved as HTML or emailed monthly.

settings["health"] = {"to": "director@x.org", "day": 1, "time": "07:00", "cleanup_folder": "C:\\SAM Exports\\Cleanup"}
Run headless (Windows Task Scheduler):  "SAM Ad Hoc Query Builder.exe" --health
"""
from __future__ import annotations

import datetime as dt
import html as _h
import subprocess
import sys
from pathlib import Path

from .app_config import APP_NAME

TASK_NAME = "SAM Ad Hoc Query Builder - Health report"
DEFAULTS = {"to": "", "day": 1, "time": "07:00", "cleanup_folder": ""}


def get(settings: dict) -> dict:
    h = dict(DEFAULTS)
    h.update(settings.get("health") or {})
    return h


def _badge(text, color):
    return f"<span style='color:{color};font-weight:600'>{_h.escape(text)}</span>"


def collect(settings: dict) -> dict:
    """Plain data for the report (also used by tests)."""
    from . import register, rollover, signoff
    from .exports import load_platforms
    from .uploader import load_history
    from .validator import check_folder
    plats = {p["id"]: p for p in load_platforms()}
    out = {"uploads": [], "cleanup": [], "agreements": [], "rollover": {}, "changes": 0, "problems": 0}
    for prof in settings.get("upload_profiles", []):
        runs = load_history(prof["name"]).get("runs", [])
        last = runs[-1] if runs else {}
        p = plats.get(prof.get("platform_id"))
        errors = warnings = None
        if p and p.get("rules") and Path(prof.get("local_folder") or "").is_dir():
            try:
                rep = check_folder(p, prof["local_folder"])
                errors, warnings = len(rep.errors), len(rep.warnings)
            except Exception:
                pass
        fails = sum(1 for r in runs[-30:] if r.get("status") != "ok")
        out["uploads"].append({"name": prof["name"], "vendor": p["name"] if p else "", "last": last.get("when", ""),
                               "status": last.get("status", "never"), "fails30": fails,
                               "errors": errors, "warnings": warnings,
                               "rows": sum(v for v in (last.get("counts") or {}).values() if v and v > 0)})
        if last.get("status") in ("failed", "held") or errors:
            out["problems"] += 1
    folder = Path(get(settings)["cleanup_folder"] or "")
    cleanup = plats.get("cleanup")
    if cleanup and folder.is_dir():
        from .uploader import count_rows
        for fe in cleanup["files"]:
            f = folder / fe["file"]
            if f.exists():
                n = count_rows(f)
                out["cleanup"].append({"report": fe["query"].get("name") or fe["file"], "rows": n,
                                       "updated": dt.datetime.fromtimestamp(f.stat().st_mtime).strftime("%m/%d/%Y")})
    in_use = register.in_use_ids(settings)
    for pid in sorted(in_use):
        p = plats.get(pid)
        if not p:
            continue
        st, color = register.status(register.entry(settings, pid))
        so, so_color = signoff.status(settings, pid)
        out["agreements"].append({"vendor": p["name"], "agreement": st, "agreement_color": color, "signoff": so,
                                  "signoff_color": so_color})
        if color in ("#B42318", "#C2410C"):
            out["problems"] += 1
    done = rollover.done(settings)
    out["rollover"] = {"year": rollover.year_key(settings), "done": len(done & {k for k, *_ in rollover.ITEMS}),
                       "total": len(rollover.ITEMS)}
    try:
        from .audit import load
        since = (dt.datetime.now() - dt.timedelta(days=30)).isoformat()
        out["changes"] = sum(len(e.get("changes", [])) for e in load() if e.get("when", "") >= since)
    except Exception:
        pass
    return out


def html_report(settings: dict) -> str:
    from .paths import district_name
    d = collect(settings)
    name = (settings.get("district") or {}).get("district_name") or district_name()
    colors = {"ok": "#1E7B34", "held": "#C2410C", "failed": "#B42318", "never": "#4A5568"}
    up = "".join(
        f"<tr><td>{_h.escape(u['name'])}<br><small>{_h.escape(u['vendor'])}</small></td>"
        f"<td>{_h.escape(u['last'].replace('T', ' ')) or '-'}</td>"
        f"<td>{_badge(u['status'].upper(), colors.get(u['status'], '#4A5568'))}</td><td>{u['rows']:,}</td>"
        f"<td>{u['fails30']}</td><td>{'' if u['errors'] is None else _badge(str(u['errors']), '#B42318' if u['errors'] else '#1E7B34')}"
        f"{'' if u['warnings'] is None else ' / ' + str(u['warnings'])}</td></tr>" for u in d["uploads"]) \
        or "<tr><td colspan=6>No upload profiles.</td></tr>"
    cl = "".join("<tr><td>" + _h.escape(c["report"]) + "</td><td>" +
                 _badge(format(c["rows"], ","), "#B42318" if c["rows"] else "#1E7B34") +
                 f"</td><td>{c['updated']}</td></tr>" for c in d["cleanup"]) or \
        "<tr><td colspan=3>Set a cleanup folder (where the CAC Agent saves the Data cleanup reports) to include counts.</td></tr>"
    ag = "".join(f"<tr><td>{_h.escape(a['vendor'])}</td><td>{_badge(a['agreement'], a['agreement_color'])}</td>"
                 f"<td>{_badge(a['signoff'], a['signoff_color'])}</td></tr>" for a in d["agreements"]) or \
        "<tr><td colspan=3>No vendors marked in use in the privacy register.</td></tr>"
    r = d["rollover"]
    head = (_badge(f"{d['problems']} item(s) need attention", "#B42318") if d["problems"]
            else _badge("Everything looks healthy", "#1E7B34"))
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>District health report</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;font-size:10pt;margin:24px;color:#1B2A41}}
table{{border-collapse:collapse;width:100%;margin-bottom:18px}}td,th{{border:1px solid #CBD5E1;padding:5px;text-align:left;
vertical-align:top}}th{{background:#EEF2F7}}small{{color:#4A5568}}h1{{font-size:16pt;margin:0}}h2{{font-size:12pt;margin:18px 0 6px}}</style>
</head><body><h1>District health report - {_h.escape(name)}</h1>
<p><small>{dt.datetime.now():%m/%d/%Y %I:%M %p} - {APP_NAME}</small></p><p>{head}</p>
<h2>Nightly uploads</h2><table><tr><th>Upload</th><th>Last run</th><th>Result</th><th>Rows</th>
<th>Problems (last 30 runs)</th><th>Checker errors / warnings now</th></tr>{up}</table>
<h2>Data cleanup</h2><table><tr><th>Report</th><th>Records to fix</th><th>File updated</th></tr>{cl}</table>
<h2>Vendors in use</h2><table><tr><th>Vendor</th><th>Data-privacy agreement</th><th>File sign-off</th></tr>{ag}</table>
<h2>Year-end rollover (school year ending {_h.escape(str(r.get('year') or '?'))})</h2>
<p>{r.get('done', 0)} of {r.get('total', 0)} steps done.</p>
<h2>SAM setup check</h2><p>{_samcheck_line(settings)}</p>
<h2>Changes</h2><p>{d['changes']} setting change(s) in the last 30 days (Tools &gt; Change log).</p>
</body></html>"""


def _samcheck_line(settings: dict) -> str:
    c = settings.get("sam_check") or {}
    if not c.get("when"):
        return "Not run yet - Tools &gt; SAM setup check confirms your owner types, enrolled code and live schedules."
    color = "#B42318" if c.get("errors") else ("#C2410C" if c.get("warnings") else "#1E7B34")
    return (f"Last run {c['when'][:10]}: " + _badge(f"{c.get('errors', 0)} problem(s), {c.get('warnings', 0)} to "
            "check", color))


def send(settings: dict) -> str:
    from . import alerts
    h = get(settings)
    if not h["to"]:
        raise RuntimeError("Add who receives the health report first.")
    body = html_report(settings)
    d = collect(settings)
    subject = f"[{APP_NAME}] District health report - " + (f"{d['problems']} item(s) need attention"
                                                             if d["problems"] else "all healthy")
    ok = alerts.send_email(alerts.get(settings), subject, "Open the attached report (HTML).", to=h["to"],
                           attachments=[(f"health report {dt.date.today():%Y-%m-%d}.html", body.encode("utf-8"),
                                         "text/html")], html=body)
    if not ok:
        raise RuntimeError("Email is not set up - add the SMTP server in Tools > Upload alerts.")
    return f"Health report sent to {h['to']}."


def schedule(settings: dict) -> str:
    if sys.platform != "win32":
        raise RuntimeError("Scheduling uses Windows Task Scheduler (run this on the Windows PC).")
    from .districts import task_label
    from .uploader import launch_args
    h = get(settings)
    cmd = launch_args("--health", "")[:-1]
    tr = " ".join(f'"{c}"' for c in cmd)
    from .paths import district_name
    tn = TASK_NAME if task_label("x") == "x" else f"{TASK_NAME} - {district_name()}"
    r = subprocess.run(["schtasks", "/Create", "/F", "/TN", tn, "/TR", tr,
                        "/SC", "MONTHLY", "/D", str(int(h["day"] or 1)), "/ST", h["time"] or "07:00"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr).strip())
    return (r.stdout + r.stderr).strip()


def headless() -> int:
    from .paths import load_settings
    try:
        msg = send(load_settings())
        if sys.stdout:
            print(msg)
        return 0
    except Exception as e:  # noqa: BLE001
        if sys.stdout:
            print(f"FAILED: {e}")
        return 1
