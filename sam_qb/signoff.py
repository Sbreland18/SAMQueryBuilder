"""Vendor sign-off - when a sample was sent to the vendor and when they approved the files.

settings["vendor_signoff"][platform_id] = {"sample_sent": "YYYY-MM-DD", "approved": "YYYY-MM-DD",
                                           "contact": "", "notes": ""}
"""
from __future__ import annotations

import datetime as dt


def entry(settings: dict, pid: str) -> dict:
    e = {"sample_sent": "", "approved": "", "contact": "", "notes": ""}
    e.update((settings.get("vendor_signoff") or {}).get(pid, {}))
    return e


def status(settings: dict, pid: str) -> tuple[str, str]:
    e = entry(settings, pid)

    def fmt(d):
        try:
            return dt.date.fromisoformat(d).strftime("%m/%d/%Y")
        except ValueError:
            return d
    if e["approved"]:
        return f"approved by the vendor on {fmt(e['approved'])}" + (f" ({e['contact']})" if e["contact"] else ""), \
            "#1E7B34"
    if e["sample_sent"]:
        return f"sample sent {fmt(e['sample_sent'])} - waiting for the vendor", "#C2410C"
    return "not confirmed with the vendor yet", "#9A6700"


def save(settings: dict, pid: str, **values):
    settings.setdefault("vendor_signoff", {})[pid] = {**entry(settings, pid), **values}
