"""Release helpers shared by the Build GUI (no Qt here)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "sam_qb" / "version.py"
CONFIG_FILE = ROOT / "sam_qb" / "app_config.py"
LATEST = ROOT / "latest.json"
DATA_FILES = ("catalog.json", "templates.json", "exports.json", "assistant_vocab.json", "shared_packages.json")


def installer_name(version: str) -> str:
    return f"SAM_AdHoc_Query_Builder_Setup_{version}.exe"


def read_version() -> str:
    m = re.search(r'__version__\s*=\s*"([^"]+)"', VERSION_FILE.read_text(encoding="utf-8"))
    return m.group(1) if m else "0.0.0"


def write_version(v: str):
    txt = VERSION_FILE.read_text(encoding="utf-8")
    VERSION_FILE.write_text(re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{v}"', txt), encoding="utf-8")


def bump(v: str, part: str) -> str:
    nums = [int(x) if x.isdigit() else 0 for x in v.split(".")] + [0, 0, 0]
    ma, mi, pa = nums[:3]
    if part == "major":
        return f"{ma + 1}.0.0"
    if part == "minor":
        return f"{ma}.{mi + 1}.0"
    return f"{ma}.{mi}.{pa + 1}"


def read_repo() -> tuple[str, str]:
    txt = CONFIG_FILE.read_text(encoding="utf-8")
    repo = re.search(r'GITHUB_REPO\s*=\s*"([^"]*)"', txt).group(1)
    branch = re.search(r'GITHUB_BRANCH\s*=\s*"([^"]*)"', txt).group(1)
    return repo, branch


def write_repo(repo: str, branch: str):
    txt = CONFIG_FILE.read_text(encoding="utf-8")
    txt = re.sub(r'GITHUB_REPO\s*=\s*"[^"]*"', f'GITHUB_REPO = "{repo}"', txt)
    txt = re.sub(r'GITHUB_BRANCH\s*=\s*"[^"]*"', f'GITHUB_BRANCH = "{branch}"', txt)
    CONFIG_FILE.write_text(txt, encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_data_version() -> str:
    try:
        return json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8")).get("data_version", "")
    except Exception:
        return ""


def next_data_version(current: str) -> str:
    today = date.today().strftime("%Y.%m.%d")
    if current.startswith(today + "."):
        n = int(current.rsplit(".", 1)[1]) + 1
        return f"{today}.{n}"
    return f"{today}.1"


def set_data_version(v: str):
    """Stamp both data files with the same data_version."""
    for name in DATA_FILES:
        p = ROOT / "data" / name
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            d["data_version"] = v
            p.write_text(json.dumps(d, indent=1), encoding="utf-8")


def load_latest() -> dict:
    try:
        return json.loads(LATEST.read_text(encoding="utf-8"))
    except Exception:
        return {}


def make_latest(repo: str, branch: str, app_version: str | None, app_notes: str | None,
                installer: Path | None, data_notes: str | None, mandatory: bool = False,
                base_url: str | None = None) -> dict:
    """Rewrite latest.json.

    app_version None  -> keep the app section that is already published (data-only release).
    installer None    -> keep the existing installer hash.
    base_url          -> override for testing (defaults to GitHub raw/releases URLs).
    """
    old = load_latest()
    raw = base_url or f"https://raw.githubusercontent.com/{repo}/{branch}"
    out = {
        "app_name": "SAM Ad Hoc Query Builder",
        "version": old.get("version", read_version()),
        "released": old.get("released", date.today().isoformat()),
        "notes": old.get("notes", ""),
        "installer_url": old.get("installer_url", ""),
        "installer_sha256": old.get("installer_sha256", ""),
        "mandatory": old.get("mandatory", False),
    }
    if app_version:
        out["version"] = app_version
        out["released"] = date.today().isoformat()
        out["notes"] = app_notes or ""
        out["mandatory"] = mandatory
        rel = base_url or f"https://github.com/{repo}/releases/download/v{app_version}"
        out["installer_url"] = f"{rel}/{installer_name(app_version)}"
        if installer and Path(installer).exists():
            out["installer_sha256"] = sha256(Path(installer))
        else:
            out["installer_sha256"] = ""
    files = {}
    for name in DATA_FILES:
        p = ROOT / "data" / name
        if p.exists():
            files[name] = {"url": f"{raw}/data/{name}", "sha256": sha256(p)}
    old_data = old.get("data", {})
    out["data"] = {
        "version": read_data_version(),
        "notes": data_notes if data_notes is not None else old_data.get("notes", ""),
        "files": files,
    }
    LATEST.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out
