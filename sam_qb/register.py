"""Vendor privacy register - which vendors get which student/staff data, and the data-privacy agreement status.

settings["vendor_register"][platform_id] = {
    "in_use": bool, "agreement": "signed" | "pending" | "none" | "not needed",
    "signed": "YYYY-MM-DD", "expires": "YYYY-MM-DD", "contact": "", "notes": "" }
"""
from __future__ import annotations

import datetime as dt
import html as _html

from .app_config import APP_NAME
from .privacy import LEVELS, report
from .query_model import QueryDef

AGREEMENTS = {"signed": "Signed", "pending": "Pending", "none": "None on file", "not needed": "Not needed"}


def entry(settings: dict, pid: str) -> dict:
    e = {"in_use": False, "agreement": "none", "signed": "", "expires": "", "contact": "", "notes": ""}
    e.update((settings.get("vendor_register") or {}).get(pid, {}))
    return e


def in_use_ids(settings: dict) -> set[str]:
    """Packages marked in use, plus any with an upload profile."""
    ids = {pid for pid, e in (settings.get("vendor_register") or {}).items() if e.get("in_use")}
    ids |= {p.get("platform_id") for p in settings.get("upload_profiles", []) if p.get("platform_id")}
    return ids


def data_shared(platform: dict) -> dict[str, list[str]]:
    """{level: [headings]} across all files of a package."""
    out: dict[str, list[str]] = {}
    for fe in platform.get("files", []):
        try:
            r = report(QueryDef.from_dict(fe["query"]))
        except Exception:
            continue
        for lvl, heading, _src in r["shown"]:
            if heading not in out.setdefault(lvl, []):
                out[lvl].append(heading)
    return out


def status(e: dict, today: dt.date | None = None) -> tuple[str, str]:
    """(short status, color) for the register table."""
    today = today or dt.date.today()
    if e.get("agreement") == "not needed":
        return "Not needed", "#4A5568"
    if e.get("agreement") != "signed":
        return AGREEMENTS.get(e.get("agreement"), "None on file"), "#B42318"
    try:
        exp = dt.date.fromisoformat(e.get("expires") or "")
    except ValueError:
        return "Signed (no end date)", "#1E7B34"
    days = (exp - today).days
    if days < 0:
        return f"EXPIRED {exp:%m/%d/%Y}", "#B42318"
    if days <= 60:
        return f"Expires in {days} days", "#C2410C"
    return f"Signed - expires {exp:%m/%d/%Y}", "#1E7B34"


def html_report(settings: dict, platforms: list[dict]) -> str:
    ids = in_use_ids(settings)
    district = (settings.get("district") or {}).get("district_name", "")
    rows = []
    for p in platforms:
        if p.get("kind") == "tool" or p["id"] not in ids:
            continue
        e = entry(settings, p["id"])
        st, color = status(e)
        shared = data_shared(p)
        cells = "".join(
            f"<div><b style='color:{LEVELS[l][1]}'>{LEVELS[l][0]}:</b> {_html.escape(', '.join(shared[l]))}</div>"
            for l in LEVELS if l in shared) or "Names, IDs, grades and schools only"
        rows.append(f"<tr><td><b>{_html.escape(p['name'])}</b><br><small>{_html.escape(p.get('works_with', ''))}"
                    f"</small></td><td>{', '.join(_html.escape(f['file']) for f in p['files'])}</td><td>{cells}</td>"
                    f"<td style='color:{color}'><b>{_html.escape(st)}</b><br><small>"
                    f"{_html.escape(e.get('signed') and 'Signed ' + e['signed'] or '')}</small></td>"
                    f"<td>{_html.escape(e.get('contact', ''))}<br><small>{_html.escape(e.get('notes', ''))}</small></td>"
                    "</tr>")
    body = "".join(rows) or "<tr><td colspan=5>No vendors are marked in use yet.</td></tr>"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Vendor privacy register</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;font-size:10pt;margin:24px;color:#1B2A41}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #CBD5E1;padding:6px;vertical-align:top;text-align:left}}
th{{background:#EEF2F7}}small{{color:#4A5568}}h1{{font-size:16pt;margin-bottom:2px}}</style></head><body>
<h1>Vendor privacy register{' - ' + _html.escape(district) if district else ''}</h1>
<div><small>Created {dt.datetime.now():%m/%d/%Y %I:%M %p} with {APP_NAME}. Data shared is taken from the export
package columns; check any district changes.</small></div><br>
<table><tr><th>Vendor</th><th>Files</th><th>Data shared</th><th>Data-privacy agreement</th><th>Contact / notes</th></tr>
{body}</table></body></html>"""
