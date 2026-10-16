"""GitHub-hosted update check driven by a single latest.json file.

latest.json (in the root of the GitHub repo) looks like:

{
  "app_name": "SAM Ad Hoc Query Builder",
  "version": "1.0.1",
  "released": "2026-10-20",
  "notes": "What changed in the app",
  "installer_url": "https://github.com/OWNER/REPO/releases/download/v1.0.1/SAM_AdHoc_Query_Builder_Setup_1.0.1.exe",
  "installer_sha256": "...",
  "mandatory": false,
  "data": {
    "version": "2026.10.20.1",
    "notes": "New tables / templates",
    "files": {
      "catalog.json":   {"url": "https://raw.githubusercontent.com/OWNER/REPO/main/data/catalog.json",   "sha256": "..."},
      "templates.json": {"url": "https://raw.githubusercontent.com/OWNER/REPO/main/data/templates.json", "sha256": "..."}
    }
  }
}

* App update  -> downloads the installer, verifies the hash, runs it and closes the app.
* Data update -> downloads catalog/templates into %APPDATA%, no reinstall needed.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .app_config import APP_NAME, latest_json_url
from .paths import active_data_file, user_data_dir, version_tuple, load_settings
from .version import __version__

UA = f"{APP_NAME.replace(' ', '')}/{__version__}"


def _ctx():
    return ssl.create_default_context()


def http_get(url: str, timeout: int = 15) -> bytes:
    sep = "&" if "?" in url else "?"
    if "raw.githubusercontent.com" in url:
        url = f"{url}{sep}t={int(time.time())}"  # bypass GitHub raw caching
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
        return r.read()


def update_url() -> str:
    return load_settings().get("update_url") or latest_json_url()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def current_data_version() -> str:
    try:
        return json.loads(active_data_file("catalog.json").read_text(encoding="utf-8")).get("data_version", "0")
    except Exception:
        return "0"


@dataclass
class UpdateInfo:
    latest: dict
    app_available: bool
    data_available: bool

    @property
    def app_version(self):
        return self.latest.get("version", "")

    @property
    def data_version(self):
        return (self.latest.get("data") or {}).get("version", "")


def check(url: str | None = None, timeout: int = 15) -> UpdateInfo:
    latest = json.loads(http_get(url or update_url(), timeout).decode("utf-8-sig"))
    app_avail = version_tuple(latest.get("version", "0")) > version_tuple(__version__)
    data = latest.get("data") or {}
    data_avail = bool(data.get("files")) and version_tuple(data.get("version", "0")) > version_tuple(current_data_version())
    return UpdateInfo(latest, app_avail, data_avail)


def apply_data_update(info: UpdateInfo, progress=None) -> list[str]:
    """Download data files, verify, then swap them in atomically. Returns list of updated names."""
    files = (info.latest.get("data") or {}).get("files", {})
    staged = {}
    for i, (name, meta) in enumerate(files.items()):
        if progress:
            progress(f"Downloading {name}...", int(100 * i / max(1, len(files))))
        blob = http_get(meta["url"], 60)
        want = (meta.get("sha256") or "").lower()
        if want and sha256_bytes(blob) != want:
            raise ValueError(f"{name} failed its integrity check (hash mismatch). Update cancelled.")
        json.loads(blob.decode("utf-8-sig"))  # must be valid JSON
        staged[name] = blob
    dest = user_data_dir()
    for name, blob in staged.items():
        tmp = dest / (name + ".tmp")
        tmp.write_bytes(blob)
        os.replace(tmp, dest / name)
    if progress:
        progress("Data update installed.", 100)
    return list(staged)


def download_installer(info: UpdateInfo, progress=None) -> Path:
    url = info.latest["installer_url"]
    name = url.rsplit("/", 1)[-1] or "setup.exe"
    out = Path(tempfile.gettempdir()) / name
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60, context=_ctx()) as r, open(out, "wb") as fh:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(f"Downloading installer... {done // 1024:,} KB", int(100 * done / total))
    want = (info.latest.get("installer_sha256") or "").lower()
    if want and sha256_file(out) != want:
        out.unlink(missing_ok=True)
        raise ValueError("The downloaded installer failed its integrity check (hash mismatch).")
    return out


def run_installer(path: Path):
    """Start the Inno Setup installer and let it close/restart the app."""
    args = [str(path), "/SILENT", "/SP-", "/CLOSEAPPLICATIONS", "/NORESTART"]
    # keep the same install mode as the copy that is running (per-user vs. all users)
    exe = str(Path(sys.executable).resolve()).lower()
    pf = [os.environ.get(k, "").lower() for k in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
    args.append("/ALLUSERS" if any(p and exe.startswith(p) for p in pf) else "/CURRENTUSER")
    if sys.platform == "win32":
        subprocess.Popen(args, close_fds=True, creationflags=0x00000008)  # DETACHED_PROCESS
    else:
        subprocess.Popen(args, close_fds=True)


def reset_downloaded_data():
    shutil.rmtree(user_data_dir(), ignore_errors=True)
