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


def get_ui_pref(key: str, default=None):
    """Per-PC preferences shared by every district (ui_prefs.json): theme, text size, update channel."""
    try:
        return json.loads((root_dir() / "ui_prefs.json").read_text(encoding="utf-8")).get(key, default)
    except Exception:
        return default


def set_ui_pref(key: str, value):
    p = root_dir() / "ui_prefs.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        d = {}
    d[key] = value
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")


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


# ----------------------------------------------------------------------------- team folder (shared by a tech team)
# Optional, per district: settings["team_folder"] = r"\\server\share\SAM Query Builder". When it is set and
# reachable, these settings and folders are shared by everyone who points at it. Passwords, upload profiles,
# alerts, the SAM connection and the admin PIN always stay on each PC.
TEAM_KEYS = ("district", "codes", "schools", "vendor_register", "vendor_signoff", "export_schools", "cac_folders",
             "cac_times", "cac_listener_time", "cac_progress", "rollover", "health", "dq_schedule", "ask_values")
TEAM_FILE = "team_settings.json"
TEAM_BASE = "_team_base"
_tf_cache: dict = {}


def team_folder(settings: dict | None = None) -> Path | None:
    """The team folder when one is set AND reachable (a network share can be offline)."""
    if settings is None:
        try:
            sp = settings_path()
            key = (str(sp), sp.stat().st_mtime_ns)
            if _tf_cache.get("key") != key:
                _tf_cache.update(key=key, value=json.loads(sp.read_text(encoding="utf-8")).get("team_folder", ""))
            settings = {"team_folder": _tf_cache["value"]}
        except Exception:
            return None
    tf = (settings or {}).get("team_folder") or ""
    if not tf:
        return None
    p = Path(tf)
    try:
        return p if p.is_dir() else None
    except OSError:
        return None


def shared_dir(name: str, default: Path) -> Path:
    """`name` inside the team folder when one is in use, else `default`."""
    tf = team_folder()
    p = (tf / name) if tf else default
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        p = default
        p.mkdir(parents=True, exist_ok=True)
    return p


def _read_team(tf: Path) -> dict:
    try:
        return json.loads((tf / TEAM_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}


def join_team(settings: dict, folder: str, copy_mine: bool):
    """Point this district at a team folder. copy_mine=True pushes this PC's shared settings into it (first PC);
    otherwise this PC takes the team's copy. Saves the settings."""
    settings["team_folder"] = folder
    base = {}                       # empty baseline = every shared key counts as changed (pushed)
    tf = team_folder(settings)
    if tf and not copy_mine:
        shared = _read_team(tf).get("settings") or {}
        for k in TEAM_KEYS:
            if k in shared:
                settings[k] = shared[k]
                base[k] = json.dumps(shared[k], sort_keys=True)
            elif k in settings:
                base[k] = json.dumps(settings[k], sort_keys=True)   # team has none: keep it local only
    settings[TEAM_BASE] = base
    _tf_cache.clear()
    save_settings(settings)


def team_info(settings: dict | None = None) -> dict:
    tf = team_folder(settings)
    if not tf:
        return {}
    d = _read_team(tf)
    return {"folder": str(tf), "updated": d.get("updated", ""), "updated_by": d.get("updated_by", ""),
            "keys": sorted((d.get("settings") or {}).keys())}


def queries_dir() -> Path:
    tf = team_folder()
    if tf:
        p = tf / "Queries"
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except OSError:
            pass
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
    sp = settings_path()
    try:
        s = json.loads(sp.read_text(encoding="utf-8"))
    except FileNotFoundError:
        s = {}
    except Exception:
        # damaged file: keep a copy and fall back to the last good backup instead of silently starting empty
        try:
            import shutil
            shutil.copy2(sp, sp.with_name(sp.name + ".bad"))
            s = json.loads(sp.with_name(sp.name + ".bak").read_text(encoding="utf-8"))
        except Exception:
            s = {}
    tf = team_folder(s)
    if tf:
        shared = _read_team(tf).get("settings") or {}
        base = {}
        for k in TEAM_KEYS:
            if k in shared:
                s[k] = shared[k]
            base[k] = json.dumps(shared.get(k), sort_keys=True)
        # each settings dict carries what it last saw of the team file, so a later save only writes keys
        # changed on this PC (another read of the settings can't make stale values look "changed")
        s[TEAM_BASE] = base
    return s


def _save_team(s: dict):
    """Write the shared keys this PC changed (others keep the team file's newer value)."""
    tf = team_folder(s)
    if not tf:
        return
    import datetime as _dt
    import getpass
    import socket
    d = _read_team(tf)
    shared = d.get("settings") or {}
    base = s.setdefault(TEAM_BASE, {})
    changed = False
    for k in TEAM_KEYS:
        if k not in s:          # never remove the team's value just because this PC doesn't have it
            continue
        mine = json.dumps(s.get(k), sort_keys=True)
        if k not in base or mine != base[k]:
            shared[k] = s[k]
            base[k] = mine
            changed = True
    if not changed and d:
        return
    try:
        who = f"{getpass.getuser()} on {socket.gethostname()}"
    except Exception:
        who = ""
    d.update(settings=shared, updated=_dt.datetime.now().isoformat(timespec="seconds"), updated_by=who)
    tmp = tf / (TEAM_FILE + ".tmp")
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    os.replace(tmp, tf / TEAM_FILE)


def save_settings(s: dict, audit: bool = True):
    """Atomic write (temp file + replace) so a scheduled run reading at the same moment never sees half a file."""
    clean = {k: v for k, v in s.items() if k != TEAM_BASE}
    try:
        if audit:
            try:
                from .audit import record_settings_change
                old = load_settings()
                old.pop(TEAM_BASE, None)
                record_settings_change(old, json.loads(json.dumps(clean)))
            except Exception:
                pass
        sp = settings_path()
        tmp = sp.with_name(sp.name + ".tmp")
        tmp.write_text(json.dumps(clean, indent=2), encoding="utf-8")
        if sp.exists():
            try:
                import shutil
                shutil.copy2(sp, sp.with_name(sp.name + ".bak"))
            except OSError:
                pass
        os.replace(tmp, sp)
    except Exception:
        pass
    try:
        _save_team(s)
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
            if version_tuple(uv) > version_tuple(bv):
                return user
        except Exception:
            pass
    return bundled
