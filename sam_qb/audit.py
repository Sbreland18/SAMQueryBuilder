"""Change log - who changed what, and when (District Settings, codes and schools, upload profiles, alerts,
privacy register, report jobs, database connection, district package versions, restores).

Settings changes are found automatically by comparing the settings file before and after each save.
Entries are JSON lines in %APPDATA%\\SAM Ad Hoc Query Builder\\change_log.jsonl.
"""
from __future__ import annotations

import csv
import datetime as dt
import getpass
import json
import socket

SECRET_WORDS = ("password", "passphrase", "api_key", "secret", "token")
IGNORE_TOP = {"window", "geometry", "last_update_check", "recent", "splitter", "last_tab"}
AREAS = {"district": "District Settings", "codes": "SAM codes", "schools": "Schools", "upload_profiles": "Uploads",
         "alerts": "Alerts", "vendor_register": "Privacy register", "report_jobs": "Report emails",
         "sam_connection": "SAM connection", "export_schools": "Package school limits", "rollover": "Rollover",
         "cac_progress": "CAC walkthrough", "cac_folders": "CAC walkthrough"}


def log_path():
    from .paths import user_dir
    return user_dir() / "change_log.jsonl"


def _flat(v, prefix=""):
    out = {}
    if isinstance(v, dict):
        for k, x in v.items():
            out.update(_flat(x, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
        for i, x in enumerate(v):
            name = x.get("name") or x.get("id") or x.get("code") or str(i)
            out.update(_flat(x, f"{prefix}[{name}]"))
    else:
        out[prefix] = v
    return out


def _secret(path: str) -> bool:
    return any(w in path.lower() for w in SECRET_WORDS)


def diff_settings(old: dict, new: dict) -> list[str]:
    changes = []
    for top in sorted(set(old) | set(new)):
        if top in IGNORE_TOP:
            continue
        a, b = _flat(old.get(top), top), _flat(new.get(top), top)
        for k in sorted(set(a) | set(b)):
            if a.get(k) == b.get(k):
                continue
            if _secret(k):
                changes.append(f"{k}: (secret changed)")
            elif k not in a:
                changes.append(f"{k}: added {b[k]!r}")
            elif k not in b:
                changes.append(f"{k}: removed (was {a[k]!r})")
            else:
                changes.append(f"{k}: {a[k]!r} -> {b[k]!r}")
    return changes


def record(area: str, changes: list[str] | str):
    if isinstance(changes, str):
        changes = [changes]
    if not changes:
        return
    entry = {"when": dt.datetime.now().isoformat(timespec="seconds"), "user": _user(),
             "computer": socket.gethostname(), "area": area, "changes": changes[:200]}
    if len(changes) > 200:
        entry["changes"].append(f"... and {len(changes) - 200} more")
    try:
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def record_settings_change(old: dict, new: dict):
    by_area: dict[str, list[str]] = {}
    for c in diff_settings(old, new):
        top = c.split(".")[0].split("[")[0].split(":")[0]
        by_area.setdefault(AREAS.get(top, top), []).append(c)
    for area, ch in by_area.items():
        record(area, ch)


def load(limit: int = 2000) -> list[dict]:
    try:
        lines = log_path().read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out


def export_csv(path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["When", "User", "Computer", "Area", "Change"])
        for e in load(100000):
            for c in e.get("changes", []):
                w.writerow([e["when"], e.get("user", ""), e.get("computer", ""), e.get("area", ""), c])


def _user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"
