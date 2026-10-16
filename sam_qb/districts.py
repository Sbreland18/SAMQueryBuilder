"""Several districts on one PC (for technology coordinators and consultants who support more than one).

Each district has its own settings (District Settings, codes and schools, upload profiles, alerts, report jobs,
privacy register, SAM connection), upload history and logs, district package versions, change log and saved
queries. The downloaded table catalog, templates, packages and your own vendor-template packages are shared.
"""
from __future__ import annotations

import json
import re
import shutil

from . import paths

APP_LEVEL_KEYS = ("ai_api_key", "ai_model", "ai_default", "check_updates")
COPYABLE = {"district": "District Settings (domains, username patterns, owner types...)",
            "codes": "SAM code lists", "alerts": "Alert email settings (no password)"}


def list_districts() -> list[dict]:
    return paths.load_districts()["list"]


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "district"
    ids = {x["id"] for x in list_districts()}
    base, n = s, 2
    while s in ids or s == paths.DEFAULT_DISTRICT:
        s, n = f"{base}-{n}", n + 1
    return s


def add_district(name: str, copy_from: dict | None = None, copy_parts=()) -> str:
    """Create a district (empty, or copying selected parts of `copy_from` settings). Returns its id."""
    d = paths.load_districts()
    did = _slug(name)
    d["list"].append({"id": did, "name": name.strip() or did})
    paths.save_districts(d)
    folder = paths.root_dir() / "districts" / did
    folder.mkdir(parents=True, exist_ok=True)
    new = {k: copy_from[k] for k in APP_LEVEL_KEYS if copy_from and k in copy_from}
    for part in copy_parts:
        if copy_from and part in copy_from:
            new[part] = json.loads(json.dumps(copy_from[part]))
    if "alerts" in new:
        new["alerts"]["smtp_password"] = ""
    if "district" in new:
        new["district"]["district_name"] = name.strip()
    (folder / "settings.json").write_text(json.dumps(new, indent=2), encoding="utf-8")
    return did


def rename_district(did: str, name: str):
    d = paths.load_districts()
    for x in d["list"]:
        if x["id"] == did:
            x["name"] = name.strip() or x["name"]
    paths.save_districts(d)


def delete_district(did: str) -> str:
    """Remove from the list; the folder is moved to districts\\_removed so nothing is lost."""
    if did == paths.DEFAULT_DISTRICT:
        raise ValueError("The first district can be renamed but not removed.")
    d = paths.load_districts()
    d["list"] = [x for x in d["list"] if x["id"] != did]
    if d.get("active") == did:
        d["active"] = paths.DEFAULT_DISTRICT
    paths.save_districts(d)
    src = paths.root_dir() / "districts" / did
    dest = paths.root_dir() / "districts" / "_removed" / did
    if src.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(src), str(dest))
    return str(dest)


def switch_to(did: str):
    d = paths.load_districts()
    if not any(x["id"] == did for x in d["list"]):
        raise ValueError(f"Unknown district {did}")
    d["active"] = did
    paths.save_districts(d)


def task_label(name: str) -> str:
    """Windows task names include the district when more than one is set up."""
    did = paths.active_district()
    if did == paths.DEFAULT_DISTRICT and len(list_districts()) <= 1:
        return name
    return f"{paths.district_name(did)} - {name}"
