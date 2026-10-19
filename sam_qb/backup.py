"""Back up and restore the app's district setup (to move to a new PC or share with a coworker).

A backup (.samqb-backup, a zip) holds settings.json with every password removed, the district versions of
package files, and optionally the saved queries. Passwords are encrypted for one Windows user, so they never
travel - re-enter them after restoring (secrets already on the target PC are kept for matching profiles).
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import socket
import zipfile
from pathlib import Path

from .version import __version__

SECRET_WORDS = ("password", "passphrase", "api_key", "secret", "token")
PARTS = {
    "district": ("District Settings, schools and codes", ["district", "district_confirmed", "schools", "codes"]),
    "uploads": ("Upload profiles and alerts (no passwords)", ["upload_profiles", "alerts"]),
    "packages": ("Package school limits, CAC walkthrough progress and district package versions",
                 ["export_schools", "cac_progress", "cac_folders"]),
    "register": ("Vendor privacy register and rollover checklist", ["vendor_register", "rollover"]),
    "reports": ("Report email jobs and SAM connection (no passwords)", ["report_jobs", "sam_connection"]),
    "queries": ("Saved queries (.samq)", []),
}


def _strip(v):
    if isinstance(v, dict):
        return {k: ("" if any(w in k.lower() for w in SECRET_WORDS) else _strip(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [_strip(x) for x in v]
    return v


def export_backup(path, settings: dict, include_queries: bool = True) -> dict:
    from .paths import queries_dir, user_dir
    path = Path(path)
    clean = _strip(copy.deepcopy(settings))
    clean.pop("ai_api_key", None)
    clean.pop("_team_base", None)
    counts = {"overrides": 0, "queries": 0}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps({"app_version": __version__, "created": dt.datetime.now().isoformat(
            timespec="seconds"), "computer": socket.gethostname(), "include_queries": include_queries}, indent=1))
        z.writestr("settings.json", json.dumps(clean, indent=1))
        from .paths import shared_dir
        ov = shared_dir("package_overrides", user_dir() / "package_overrides")
        if ov.is_dir():
            for f in (x for x in ov.rglob("*.json") if ".history" not in x.parts):
                z.write(f, "package_overrides/" + f.relative_to(ov).as_posix())
                counts["overrides"] += 1
        if include_queries:
            for f in queries_dir().glob("*.samq"):
                z.write(f, "queries/" + f.name)
                counts["queries"] += 1
    return counts


def read_manifest(path) -> dict:
    with zipfile.ZipFile(path) as z:
        return json.loads(z.read("manifest.json"))


def import_backup(path, current: dict, parts: set[str]) -> tuple[dict, list[str]]:
    """Returns (new settings, summary lines). Files (package versions, queries) are written immediately."""
    from .paths import queries_dir, user_dir
    new = copy.deepcopy(current)
    done = []
    with zipfile.ZipFile(path) as z:
        data = json.loads(z.read("settings.json"))
        for part, (label, keys) in PARTS.items():
            if part not in parts:
                continue
            for k in keys:
                if k in data:
                    new[k] = _keep_secrets(current.get(k), data[k])
            if keys:
                done.append(label)
        if "packages" in parts:
            n = 0
            from .paths import shared_dir
            base = shared_dir("package_overrides", user_dir() / "package_overrides")
            for name in z.namelist():
                if name.startswith("package_overrides/") and name.endswith(".json"):
                    target = _inside(base, name[len("package_overrides/"):])
                    if target is None:
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(name))
                    n += 1
            done.append(f"{n} district package version(s)")
        if "queries" in parts:
            n = 0
            for name in z.namelist():
                if name.startswith("queries/") and name.endswith(".samq"):
                    target = _inside(queries_dir(), name[8:])
                    if target is None or target.parent != queries_dir().resolve():
                        continue
                    if target.exists():
                        target = target.with_name(target.stem + " (restored).samq")
                    target.write_bytes(z.read(name))
                    n += 1
            done.append(f"{n} saved quer{'y' if n == 1 else 'ies'}")
    from .audit import record
    record("Backup restore", [f"Restored from {Path(path).name}: " + "; ".join(done)])
    return new, done


def _inside(base: Path, rel: str) -> Path | None:
    """The path for a backup entry, or None when it would land outside `base` (\\, .., drive letters...)."""
    if not rel or ":" in rel or "\\" in rel or rel.startswith("/"):
        return None
    parts = [x for x in rel.split("/") if x]
    if not parts or any(x in (".", "..") for x in parts):
        return None
    target = (Path(base) / Path(*parts)).resolve()
    try:
        target.relative_to(Path(base).resolve())
    except ValueError:
        return None
    return target


def _keep_secrets(old, incoming):
    """Restore values but keep secrets that already exist here (matching profiles by name)."""
    if isinstance(incoming, dict):
        old = old if isinstance(old, dict) else {}
        return {k: (old.get(k, "") if any(w in k.lower() for w in SECRET_WORDS) and not v else
                    _keep_secrets(old.get(k), v)) for k, v in incoming.items()}
    if isinstance(incoming, list) and incoming and all(isinstance(x, dict) for x in incoming):
        olds = {(x.get("name") or x.get("id")): x for x in (old or []) if isinstance(x, dict)}
        return [_keep_secrets(olds.get(x.get("name") or x.get("id")), x) for x in incoming]
    return incoming


# ----------------------------------------------------------------------------- automatic backups
# settings["auto_backup"] = {"folder": r"\\server\backups\SAM QB", "day": "SUN", "time": "06:00", "keep": 8,
#                            "include_queries": True, "last": "", "last_result": ""}
AUTO_DEFAULTS = {"folder": "", "day": "SUN", "time": "06:00", "keep": 8, "include_queries": True}


def auto_settings(settings: dict) -> dict:
    a = dict(AUTO_DEFAULTS)
    a.update(settings.get("auto_backup") or {})
    return a


def run_auto(settings: dict, now: dt.datetime | None = None) -> str:
    """Write a dated backup to the backup folder and keep only the newest `keep` files for this district."""
    from .paths import district_name, save_settings
    a = auto_settings(settings)
    folder = Path(a["folder"] or "")
    if not a["folder"]:
        raise RuntimeError("No backup folder is set (File > Automatic backups).")
    folder.mkdir(parents=True, exist_ok=True)
    now = now or dt.datetime.now()
    tag = "".join(ch for ch in district_name() if ch.isalnum() or ch in " -_").strip() or "district"
    path = folder / f"{tag} settings {now:%Y-%m-%d %H%M}.samqb-backup"
    counts = export_backup(path, settings, bool(a.get("include_queries", True)))
    olds = sorted(folder.glob(f"{tag} settings *.samqb-backup"), key=lambda p: p.name, reverse=True)
    removed = 0
    for old in olds[max(1, int(a.get("keep") or 8)):]:
        try:
            old.unlink()
            removed += 1
        except OSError:
            pass
    msg = (f"Backed up to {path.name} ({counts['overrides']} district versions, {counts['queries']} queries)"
           + (f"; removed {removed} older backup(s)" if removed else ""))
    settings.setdefault("auto_backup", {}).update(last=now.isoformat(timespec="seconds"), last_result=msg)
    save_settings(settings, audit=False)
    return msg


def schedule_auto(settings: dict) -> str:
    from .scheduler import create
    a = auto_settings(settings)
    return create("Settings backup", "--backup", "WEEKLY", a["time"], a["day"])


def headless_auto() -> int:
    import sys
    from .paths import load_settings
    settings = load_settings()
    if not auto_settings(settings).get("folder"):
        if sys.stdout:
            print("Automatic backups are turned off (no folder set) - nothing to do.")
        return 0
    try:
        msg = run_auto(settings)
        if sys.stdout:
            print(msg)
        return 0
    except Exception as e:  # noqa: BLE001
        try:
            from . import alerts
            alerts.notify(settings, "[SAM Ad Hoc Query Builder] Automatic backup FAILED", str(e))
        except Exception:
            pass
        if sys.stdout:
            print(f"FAILED: {e}")
        return 1
