"""File locations (works both from source and from a PyInstaller build)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .app_config import APP_NAME


def resource_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def bundled_data_dir() -> Path:
    return resource_dir() / "data"


def root_dir() -> Path:
    """%APPDATA%\\SAM Ad Hoc Query Builder - shared by every district on this PC (downloaded data, district list)."""
    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


# ----------------------------------------------------------------------------- districts (multi-district support)
DEFAULT_DISTRICT = "default"


def _districts_file() -> Path:
    return root_dir() / "districts.json"


def load_districts() -> dict:
    try:
        d = json.loads(_districts_file().read_text(encoding="utf-8"))
    except Exception:
        d = {}
    d.setdefault("active", DEFAULT_DISTRICT)
    d.setdefault("list", [])
    if not any(x["id"] == DEFAULT_DISTRICT for x in d["list"]):
        d["list"].insert(0, {"id": DEFAULT_DISTRICT, "name": "My district"})
    return d


def save_districts(d: dict):
    _districts_file().write_text(json.dumps(d, indent=2), encoding="utf-8")


def active_district() -> str:
    """The district this run works with. SAMQB_DISTRICT (set by --district for scheduled runs) wins."""
    env = os.environ.get("SAMQB_DISTRICT", "").strip()
    if env:
        return env
    return load_districts().get("active", DEFAULT_DISTRICT)


def district_name(did: str | None = None) -> str:
    did = did or active_district()
    return next((x["name"] for x in load_districts()["list"] if x["id"] == did), did)


def user_dir() -> Path:
    """Folder for the ACTIVE district's settings, upload history, logs, package versions and change log."""
    did = active_district()
    p = root_dir() if did == DEFAULT_DISTRICT else root_dir() / "districts" / did
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_data_dir() -> Path:
    p = root_dir() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def queries_dir() -> Path:
    docs = Path.home() / "Documents"
    p = (docs if docs.exists() else Path.home()) / APP_NAME / "Queries"
    did = active_district()
    if did != DEFAULT_DISTRICT:
        p = p / "".join(ch for ch in district_name(did) if ch.isalnum() or ch in " -_").strip()
    p.mkdir(parents=True, exist_ok=True)
    return p


def settings_path() -> Path:
    return user_dir() / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(settings_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(s: dict, audit: bool = True):
    try:
        if audit:
            try:
                from .audit import record_settings_change
                record_settings_change(load_settings(), json.loads(json.dumps(s)))
            except Exception:
                pass
        settings_path().write_text(json.dumps(s, indent=2), encoding="utf-8")
    except Exception:
        pass


def version_tuple(v: str) -> tuple:
    out = []
    for p in str(v).replace("v", "").split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def active_data_file(name: str) -> Path:
    """Use a downloaded data file only when its data_version is newer than the bundled one."""
    bundled = bundled_data_dir() / name
    user = user_data_dir() / name
    if user.exists():
        try:
            uv = json.loads(user.read_text(encoding="utf-8")).get("data_version", "0")
            bv = json.loads(bundled.read_text(encoding="utf-8")).get("data_version", "0") if bundled.exists() else "0"
            if version_tuple(uv) >= version_tuple(bv):
                return user
        except Exception:
            pass
    return bundled
