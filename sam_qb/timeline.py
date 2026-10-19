"""Nightly schedule timeline: SAM CAC Agent job times, the CAS Agent Listener, uploads, report emails and other
scheduled jobs on one 24-hour line, with warnings for uploads that run before their files are ready.

settings["cac_times"][platform_id] = "01:00"     (set in the CAC Agent walkthrough)
settings["cac_listener_time"] = "02:00"           (when the CAS Agent Listener task runs on the agent PC)"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

GAP_AFTER_JOB = 60       # minutes between the SAM job time and the upload
GAP_AFTER_LISTENER = 30  # minutes between the listener and the upload


def minutes(t: str) -> int | None:
    try:
        h, m = str(t).strip().split(":")[:2]
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def hhmm(m: int) -> str:
    m %= 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def events(settings: dict, platforms: list[dict] | None = None) -> list[dict]:
    """[{'time': 'HH:MM', 'min': int, 'kind': 'cac'|'listener'|'upload'|'report'|'health'|'backup'|'dq',
         'label', 'platform_id', 'when': 'daily'|'weekly MON'|...}] sorted by time."""
    if platforms is None:
        from .exports import load_platforms
        platforms = load_platforms()
    names = {p["id"]: p["name"] for p in platforms}
    ev = []
    for pid, t in (settings.get("cac_times") or {}).items():
        if minutes(t) is not None:
            ev.append({"time": t, "kind": "cac", "label": f"SAM CAC Agent jobs - {names.get(pid, pid)}",
                       "platform_id": pid, "when": "daily"})
    lt = settings.get("cac_listener_time")
    if minutes(lt) is not None:
        ev.append({"time": lt, "kind": "listener", "label": "CAS Agent Listener collects the files", "platform_id": "",
                   "when": "daily"})
    for p in settings.get("upload_profiles", []):
        t = p.get("schedule_time")
        if minutes(t) is not None:
            ev.append({"time": t, "kind": "upload", "label": f"Upload - {p['name']}",
                       "platform_id": p.get("platform_id", ""), "when": "daily", "profile": p["name"],
                       "folder": p.get("local_folder", "")})
    for j in settings.get("report_jobs", []):
        if minutes(j.get("time")) is not None:
            ev.append({"time": j["time"], "kind": "report", "label": f"Report email - {j['name']}", "platform_id": "",
                       "when": "daily" if j.get("frequency") == "daily" else f"weekly {j.get('day', 'MON')}",
                       "folder": str(Path(j.get("csv_path") or "").parent) if j.get("source") == "file" else ""})
    h = settings.get("health") or {}
    if h.get("to") and minutes(h.get("time")) is not None:
        ev.append({"time": h["time"], "kind": "health", "label": "District health report", "platform_id": "",
                   "when": f"monthly day {h.get('day', 1)}"})
    b = settings.get("auto_backup") or {}
    if b.get("folder") and minutes(b.get("time")) is not None:
        ev.append({"time": b["time"], "kind": "backup", "label": "Automatic settings backup", "platform_id": "",
                   "when": f"weekly {b.get('day', 'SUN')}"})
    d = settings.get("dq_schedule") or {}
    if d.get("enabled") and minutes(d.get("time")) is not None:
        ev.append({"time": d["time"], "kind": "dq", "label": "Data quality snapshot", "platform_id": "",
                   "when": f"weekly {d.get('day', 'MON')}"})
    for e in ev:
        e["min"] = minutes(e["time"])
    return sorted(ev, key=lambda e: e["min"])


def _newest(folder: str) -> dt.datetime | None:
    try:
        files = [f for f in Path(folder).glob("*.csv") if f.is_file()]
    except OSError:
        return None
    return dt.datetime.fromtimestamp(max(f.stat().st_mtime for f in files)) if files else None


def problems(settings: dict, platforms: list[dict] | None = None, now: dt.datetime | None = None) -> list[tuple]:
    """[(level 'error'|'warn'|'info', message)]"""
    now = now or dt.datetime.now()
    ev = events(settings, platforms)
    cac = {e["platform_id"]: e["min"] for e in ev if e["kind"] == "cac"}
    listener = next((e["min"] for e in ev if e["kind"] == "listener"), None)
    out = []
    for e in ev:
        if e["kind"] != "upload":
            continue
        pid, m = e["platform_id"], e["min"]
        if pid in cac:
            gap = (m - cac[pid]) % 1440
            if gap < GAP_AFTER_JOB:
                out.append(("error", f"{e['label']} runs at {e['time']}, only {gap} min after its SAM CAC jobs "
                                     f"({hhmm(cac[pid])}) - move it to {hhmm(cac[pid] + GAP_AFTER_JOB)} or later."))
        else:
            out.append(("warn", f"{e['label']}: no SAM CAC job time recorded for this package - add it in the CAC "
                                f"Agent walkthrough so the timeline can check it."))
        if listener is not None:
            gap = (m - listener) % 1440
            if gap < GAP_AFTER_LISTENER:
                out.append(("error", f"{e['label']} runs {gap} min after the CAS Agent Listener ({hhmm(listener)}) "
                                     f"- leave at least {GAP_AFTER_LISTENER} minutes."))
        newest = _newest(e.get("folder", ""))
        if newest is not None:
            age = now - newest
            if age > dt.timedelta(hours=36):
                out.append(("error", f"{e['label']}: the newest file in {e['folder']} is from "
                                     f"{newest:%m/%d %I:%M %p} - the CAC Agent jobs may have stopped."))
            else:
                ran = now.replace(hour=m // 60, minute=m % 60, second=0, microsecond=0)
                if ran > now:
                    ran -= dt.timedelta(days=1)
                if newest > ran and (newest - ran) < dt.timedelta(hours=20):
                    out.append(("warn", f"{e['label']}: files arrived at {newest:%I:%M %p}, AFTER the upload "
                                        f"ran at {e['time']} - the vendor got the previous day's files."))
    if listener is not None:
        for pid, m in cac.items():
            if (listener - m) % 1440 < 30:
                name = next((e["label"] for e in ev if e["kind"] == "cac" and e["platform_id"] == pid), pid)
                out.append(("warn", f"The CAS Agent Listener ({hhmm(listener)}) runs less than 30 min after "
                                    f"'{name}' ({hhmm(m)}) - SAM may not have finished the files."))
    else:
        if cac:
            out.append(("info", "Add the time the CAS Agent Listener task runs (Windows Task Scheduler on the agent "
                                "PC) to check it too."))
    times = {}
    for e in ev:
        if e["kind"] == "upload":
            times.setdefault(e["min"], []).append(e["label"])
    for m, labels in times.items():
        if len(labels) > 2:
            out.append(("info", f"{len(labels)} uploads start at {hhmm(m)} - spreading them a few minutes apart "
                                f"makes problems easier to trace."))
    return out
