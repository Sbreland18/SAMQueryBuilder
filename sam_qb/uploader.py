"""Package & upload: check the CSVs the CAC Agent wrote, zip them (with any static files such as
OneRoster's manifest.csv), upload by SFTP and keep a dated archive + log.

Profiles live in settings["upload_profiles"]. Passwords are encrypted with Windows DPAPI
(only the same Windows user on the same PC can decrypt them).

Run headless (for Windows Task Scheduler):
    "SAM Ad Hoc Query Builder.exe" --upload "Clever nightly"
"""
from __future__ import annotations

import base64
import datetime as dt
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from .paths import user_dir

TASK_PREFIX = "SAM Ad Hoc Query Builder - Upload "


# ----------------------------------------------------------------------------- password protection
def protect(secret: str) -> str:
    if not secret:
        return ""
    if sys.platform == "win32":
        try:
            return "dpapi:" + base64.b64encode(_dpapi(secret.encode("utf-8"), True)).decode()
        except Exception:
            pass
    return "plain:" + base64.b64encode(secret.encode("utf-8")).decode()


def unprotect(blob: str) -> str:
    if not blob:
        return ""
    kind, _, data = blob.partition(":")
    raw = base64.b64decode(data)
    if kind == "dpapi":
        return _dpapi(raw, False).decode("utf-8")
    return raw.decode("utf-8")


def _dpapi(data: bytes, encrypt: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if encrypt else ctypes.windll.crypt32.CryptUnprotectData
    if encrypt:
        ok = fn(ctypes.byref(blob_in), "SAMQB", None, None, None, 0, ctypes.byref(blob_out))
    else:
        ok = fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        raise OSError("DPAPI call failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


# ----------------------------------------------------------------------------- profiles
DEFAULT_PROFILE = {
    "name": "", "platform_id": "", "local_folder": "", "host": "", "port": 22, "username": "", "password": "",
    "remote_dir": "/", "zip": False, "zip_name": "", "check_first": True, "block_on_errors": True,
    "archive": True, "schedule_time": "05:00",
    # delivery method: sftp | ftps | folder (network share, or a Google Drive / OneDrive synced folder)
    "method": "sftp", "key_file": "", "key_passphrase": "", "dest_folder": "",
    # safety net: hold the upload when a file is empty or shrinks a lot compared with the last good upload
    "guard": True, "guard_drop_pct": 10, "override_once": False,
    # PGP: encrypt every file sent with the vendor's public key (.asc / .gpg file)
    "pgp_key_file": "", "pgp_armor": False,
}


def new_profile(platform: dict | None = None) -> dict:
    p = dict(DEFAULT_PROFILE)
    if platform:
        p["platform_id"] = platform["id"]
        p["name"] = platform["name"].split(" (")[0]
        p.update({k: v for k, v in (platform.get("delivery_defaults") or {}).items()})
    return p


class Log:
    def __init__(self, sink=None):
        self.lines = []
        self.sink = sink

    def __call__(self, msg):
        line = f"{dt.datetime.now():%H:%M:%S}  {msg}"
        self.lines.append(line)
        if self.sink:
            self.sink(line)


def _log_file(profile) -> Path:
    d = user_dir() / "upload_logs"
    d.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(profile["name"])
    return d / f"{dt.date.today():%Y-%m-%d} {safe}.log"


def collect_files(profile: dict, platform: dict | None, log: Log) -> list[Path]:
    folder = Path(profile["local_folder"])
    if not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder}")
    files = []
    names = [fe["file"] for fe in platform["files"]] if platform else []
    if names:
        for n in names:
            p = folder / n
            if not p.exists():
                alt = next((x for x in folder.iterdir() if x.name.lower() == n.lower()), None)
                p = alt or p
            if p.exists():
                files.append(p)
            else:
                log(f"WARNING: {n} not found in {folder}")
        for name, text in (platform.get("static_files") or {}).items():
            p = folder / name
            if not p.exists():
                p.write_text(text, encoding="utf-8", newline="\n")
                log(f"Created {name}")
            files.append(p)
    else:
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".csv", ".txt"))
    return files


def make_zip(profile: dict, files: list[Path], log: Log) -> Path:
    name = profile.get("zip_name") or f"{profile['name'] or 'export'}.zip"
    out = Path(profile["local_folder"]) / name
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.name)
    log(f"Zipped {len(files)} file(s) into {out.name} ({out.stat().st_size // 1024:,} KB)")
    return out


def sftp_connect(profile: dict, log: Log):
    import paramiko
    client = paramiko.SSHClient()
    kh = user_dir() / "known_hosts"
    kh.touch(exist_ok=True)
    client.load_host_keys(str(kh))
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    log(f"Connecting to {profile['host']}:{profile.get('port', 22)} as {profile['username']}...")
    key = None
    if profile.get("key_file"):
        key = _load_key(profile["key_file"], unprotect(profile.get("key_passphrase", "")) or None)
        log(f"Using SSH key {Path(profile['key_file']).name}")
    client.connect(profile["host"], port=int(profile.get("port") or 22), username=profile["username"],
                   password=unprotect(profile.get("password", "")) or None, pkey=key, timeout=30, banner_timeout=30,
                   auth_timeout=30, look_for_keys=key is None, allow_agent=False)
    client.save_host_keys(str(kh))
    return client, client.open_sftp()


def _load_key(path: str, passphrase: str | None):
    import paramiko
    errors = []
    for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return cls.from_private_key_file(path, password=passphrase)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{cls.__name__}: {e}")
    raise ValueError(f"Could not read the SSH key {path} (" + "; ".join(errors) + ")")


def ftps_connect(profile: dict, log: Log):
    import ftplib
    log(f"Connecting (FTPS) to {profile['host']}:{profile.get('port', 21)} as {profile['username']}...")
    ftp = ftplib.FTP_TLS(timeout=60)
    ftp.connect(profile["host"], int(profile.get("port") or 21))
    ftp.login(profile["username"], unprotect(profile.get("password", "")))
    ftp.prot_p()
    rd = profile.get("remote_dir") or ""
    if rd and rd != "/":
        ftp.cwd(rd)
    return ftp


def test_connection(profile: dict, log: Log | None = None) -> str:
    log = log or Log()
    method = profile.get("method") or "sftp"
    if method == "folder":
        d = Path(profile.get("dest_folder") or "")
        if not d.is_dir():
            raise FileNotFoundError(f"Destination folder not found: {d}")
        probe = d / ".samqb_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return f"Folder is reachable and writable: {d}"
    if method == "ftps":
        ftp = ftps_connect(profile, log)
        try:
            return f"Connected (FTPS). {len(ftp.nlst())} item(s) in {ftp.pwd()}"
        finally:
            ftp.quit()
    client, sftp = sftp_connect(profile, log)
    try:
        listing = sftp.listdir(profile.get("remote_dir") or ".")
        return f"Connected. {len(listing)} item(s) in {profile.get('remote_dir') or '.'}"
    finally:
        sftp.close()
        client.close()


# ----------------------------------------------------------------------------- history + safety net
def _safe_name(name: str) -> str:
    return "".join(ch for ch in name if ch.isalnum() or ch in " -_").strip() or "upload"


def history_file(profile_name: str) -> Path:
    d = user_dir() / "upload_history"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_safe_name(profile_name)}.json"


def load_history(profile_name: str) -> dict:
    import json
    try:
        return json.loads(history_file(profile_name).read_text(encoding="utf-8"))
    except Exception:
        return {"runs": [], "last_good_counts": {}}


def save_history(profile_name: str, hist: dict):
    import json
    hist["runs"] = hist.get("runs", [])[-60:]
    history_file(profile_name).write_text(json.dumps(hist, indent=1), encoding="utf-8")


def count_rows(path: Path) -> int:
    """Data rows in a CSV/TXT file (header excluded, blank lines ignored)."""
    import csv
    if path.suffix.lower() not in (".csv", ".txt"):
        return -1
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        rows = sum(1 for r in csv.reader(fh) if any(c.strip() for c in r))
    return max(0, rows - 1)


def last_good_dir(profile: dict) -> Path:
    return Path(profile["local_folder"]) / "archive" / "_last_good_upload"


def keep_last_good(profile: dict, files: list[Path]):
    """Keep a copy of the files from the last successful upload for 'What changed?'."""
    d = last_good_dir(profile)
    try:
        d.mkdir(parents=True, exist_ok=True)
        for f in files:
            shutil.copy2(f, d / f.name)
    except Exception:
        pass


def what_changed(profile: dict, platforms: list[dict]):
    """Diff the files in the folder now against the last successful upload."""
    from .filediff import diff_folders
    platform = next((p for p in platforms if p["id"] == profile.get("platform_id")), None)
    names = [fe["file"] for fe in platform["files"]] if platform else None
    if not last_good_dir(profile).is_dir():
        raise FileNotFoundError("No successful upload has been recorded for this profile yet.")
    return diff_folders(last_good_dir(profile), profile["local_folder"], names, (platform or {}).get("rules"))


def guard_check(profile: dict, counts: dict, last: dict) -> list[str]:
    """Problems that should hold the upload: empty files and big drops versus the last good upload."""
    problems = []
    pct = float(profile.get("guard_drop_pct") or 10)
    for name, n in counts.items():
        if n < 0 or name.lower() == "manifest.csv":
            continue
        before = last.get(name)
        if n == 0:
            problems.append(f"{name} has no rows" + (f" (last good upload had {before:,})" if before else ""))
        elif before and before >= 20 and n < before * (1 - pct / 100):
            drop = 100 * (before - n) / before
            problems.append(f"{name} dropped from {before:,} to {n:,} rows ({drop:.0f}% fewer)")
    return problems


def run_profile(profile: dict, platforms: list[dict], sink=None, dry_run: bool = False) -> tuple[bool, str]:
    """Check -> zip -> upload -> archive. Returns (success, log text). Always writes a log file."""
    log = Log(sink)
    ok = False
    held = False
    counts = {}
    hist = load_history(profile["name"])
    started = dt.datetime.now()
    try:
        platform = next((p for p in platforms if p["id"] == profile.get("platform_id")), None)
        log(f"Profile '{profile['name']}' ({platform['name'] if platform else 'any CSV files'})")
        files = collect_files(profile, platform, log)
        if not files:
            raise RuntimeError("No files to upload.")
        if profile.get("check_first") and platform and platform.get("rules"):
            from .validator import check_folder
            rep = check_folder(platform, profile["local_folder"])
            log(f"Check: {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
            for i in rep.issues:
                if i.level != "info":
                    log(f"  [{i.level}] {i.file}: {i.message} x{i.count}")
            (Path(profile["local_folder"]) / "last_check.txt").write_text(rep.text(), encoding="utf-8")
            if rep.errors and profile.get("block_on_errors"):
                raise RuntimeError("Upload stopped because the check found errors (see last_check.txt).")
        counts = {f.name: count_rows(f) for f in files}
        log("Rows: " + ", ".join(f"{k} {v:,}" for k, v in counts.items() if v >= 0))
        if profile.get("guard", True):
            problems = guard_check(profile, counts, hist.get("last_good_counts", {}))
            if problems and profile.get("override_once"):
                log("Safety net: " + "; ".join(problems) + " - uploading anyway (override for this run).")
                problems = []
            if problems:
                for p_ in problems:
                    log(f"SAFETY NET: {p_}")
                held = True
                raise RuntimeError("Upload held by the safety net so the vendor doesn't deactivate users. Check the "
                                   "CAC Agent job / SAM data, or use 'Upload anyway once' if the change is real.")
        to_send = [make_zip(profile, files, log)] if profile.get("zip") else files
        if profile.get("pgp_key_file"):
            from .pgp import encrypt_file
            to_send = [encrypt_file(f, profile["pgp_key_file"], bool(profile.get("pgp_armor")), log) for f in to_send]
        if dry_run:
            log("Dry run - nothing uploaded.")
            ok = True
        else:
            deliver(profile, to_send, log)
            ok = True
            hist["last_good_counts"] = counts
            keep_last_good(profile, files)
        if ok and profile.get("archive"):
            arch = Path(profile["local_folder"]) / "archive" / f"{dt.datetime.now():%Y-%m-%d_%H%M}"
            arch.mkdir(parents=True, exist_ok=True)
            for f in to_send:
                shutil.copy2(f, arch / f.name)
            log(f"Archived a copy to {arch}")
        log("FINISHED OK" if ok else "FINISHED")
    except Exception as e:  # noqa: BLE001
        log(f"FAILED: {e}")
        ok = False
    text = "\n".join(log.lines) + "\n"
    try:
        with open(_log_file(profile), "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    except Exception:
        pass
    if not dry_run:
        status = "ok" if ok else ("held" if held else "failed")
        hist.setdefault("runs", []).append({
            "when": started.isoformat(timespec="seconds"), "status": status, "counts": counts,
            "message": next((ln.split("  ", 1)[-1] for ln in reversed(log.lines)
                             if "FAILED" in ln or "SAFETY NET" in ln), "")})
        try:
            save_history(profile["name"], hist)
        except Exception:
            pass
        if profile.get("override_once") and ok:
            profile["override_once"] = False
            _clear_override(profile["name"])
        try:
            from .alerts import notify_run
            notify_run(profile, status, text)
        except Exception as e:  # noqa: BLE001
            log(f"Alert could not be sent: {e}")
    return ok, text


def _clear_override(name: str):
    from .paths import load_settings, save_settings
    s = load_settings()
    for p in s.get("upload_profiles", []):
        if p.get("name") == name:
            p["override_once"] = False
    save_settings(s)


def deliver(profile: dict, to_send: list[Path], log: Log):
    method = profile.get("method") or "sftp"
    if method == "folder":
        dest = Path(profile.get("dest_folder") or "")
        if not dest.is_dir():
            raise FileNotFoundError(f"Destination folder not found: {dest}")
        for f in to_send:
            shutil.copy2(f, dest / f.name)
            log(f"Copied {f.name} -> {dest}")
        return
    if method == "ftps":
        ftp = ftps_connect(profile, log)
        try:
            for f in to_send:
                with open(f, "rb") as fh:
                    ftp.storbinary(f"STOR {f.name}", fh)
                log(f"Uploaded {f.name} (FTPS, {f.stat().st_size // 1024:,} KB)")
        finally:
            try:
                ftp.quit()
            except Exception:
                pass
        return
    client, sftp = sftp_connect(profile, log)
    try:
        rd = (profile.get("remote_dir") or "").rstrip("/")
        for f in to_send:
            target = f"{rd}/{f.name}" if rd else f.name
            sftp.put(str(f), target)
            log(f"Uploaded {f.name} -> {target} ({f.stat().st_size // 1024:,} KB)")
    finally:
        sftp.close()
        client.close()


def status_rows(settings: dict) -> list[dict]:
    """For the start-page status board: one row per profile with its last run."""
    out = []
    for p in settings.get("upload_profiles", []):
        runs = load_history(p["name"]).get("runs", [])
        last = runs[-1] if runs else None
        out.append({"name": p["name"], "scheduled": p.get("schedule_time", ""), "last": last,
                    "last_ok": next((r["when"] for r in reversed(runs) if r["status"] == "ok"), "")})
    return out


# ----------------------------------------------------------------------------- Windows Task Scheduler
def launch_args(flag: str, name: str) -> list[str]:
    """Command line that runs the app headless, e.g. --upload "Clever nightly" or --report "Weekly cleanup"."""
    from .paths import DEFAULT_DISTRICT, active_district
    did = active_district()
    extra = ["--district", did] if did != DEFAULT_DISTRICT else []
    if getattr(sys, "frozen", False):
        return [sys.executable, *extra, flag, name]
    main = Path(__file__).resolve().parents[1] / "main.py"
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    return [str(pyw if pyw.exists() else py), str(main), *extra, flag, name]


def launch_command(profile_name: str) -> list[str]:
    return launch_args("--upload", profile_name)


def schedule(profile: dict) -> str:
    if sys.platform != "win32":
        raise RuntimeError("Scheduling uses Windows Task Scheduler (run this on the Windows PC).")
    cmd = launch_command(profile["name"])
    tr = " ".join(f'"{c}"' for c in cmd)
    from .districts import task_label
    args = ["schtasks", "/Create", "/F", "/TN", TASK_PREFIX + task_label(profile["name"]), "/TR", tr, "/SC", "DAILY",
            "/ST", profile.get("schedule_time") or "05:00"]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr).strip())
    return (r.stdout + r.stderr).strip()


def unschedule(profile: dict) -> str:
    if sys.platform != "win32":
        return "Not on Windows."
    from .districts import task_label
    out = []
    for tn in dict.fromkeys([TASK_PREFIX + task_label(profile["name"]), TASK_PREFIX + profile["name"]]):
        r = subprocess.run(["schtasks", "/Delete", "/F", "/TN", tn], capture_output=True, text=True)
        if r.returncode == 0:
            out.append((r.stdout + r.stderr).strip())
    return "\n".join(out) or "No schedule found."


def headless(profile_name: str) -> int:
    """Entry point for the scheduled task (no window)."""
    from .exports import load_platforms
    from .paths import load_settings
    settings = load_settings()
    prof = next((p for p in settings.get("upload_profiles", []) if p["name"] == profile_name), None)
    if not prof:
        print(f"No upload profile named {profile_name!r}")
        return 2
    ok, text = run_profile(prof, load_platforms(), sink=print if sys.stdout else None)
    return 0 if ok else 1
