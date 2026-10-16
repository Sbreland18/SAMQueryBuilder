"""Shared package library - packages built with the vendor template builder, published centrally in
data/shared_packages.json so every district gets them through latest.json (no app update needed).

Districts see them under "Shared packages" (read-only) and can copy one to My packages to change it.
The maintainer adds .samqb-package files on the Build GUI's Data tab and publishes a data update.
"""
from __future__ import annotations

import json
from pathlib import Path

FILE = "shared_packages.json"


def load_shared() -> list[dict]:
    from .paths import active_data_file
    try:
        d = json.loads(active_data_file(FILE).read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for p in d.get("packages", []):
        if p.get("files"):
            p = dict(p, shared=True, custom=False, category="Shared packages")
            out.append(p)
    return out


def copy_to_mine(platform: dict) -> dict:
    """Copy a shared package into My packages so it can be edited."""
    from . import template_builder as tb
    from .exports import load_platforms
    ids = {p["id"] for p in load_platforms()}
    pid, n = tb.slug(platform["name"]), 2
    while pid in ids:
        pid, n = f"{tb.slug(platform['name'])}-{n}", n + 1
    mine = json.loads(json.dumps(platform))
    mine.update(id=pid, custom=True, shared=False, category="My packages", copied_from=platform["id"])
    tb.save_custom(mine)
    return mine


# ----------------------------------------------------------------------------- maintainer side (Build GUI)
def read_library(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"data_version": "", "packages": []}


def add_package_file(path: Path, package_file: str) -> dict:
    """Add (or replace by id) a .samqb-package in data/shared_packages.json. Returns the platform added."""
    from .query_model import QueryDef
    lib = read_library(path)
    d = json.loads(Path(package_file).read_text(encoding="utf-8"))
    plat = d.get("platform") if isinstance(d, dict) and "platform" in d else d
    if not isinstance(plat, dict) or not plat.get("files"):
        raise ValueError(f"{package_file} is not a package file.")
    for fe in plat["files"]:
        QueryDef.from_dict(fe["query"])
    sid = "shared-" + str(plat["id"]).removeprefix("custom-").removeprefix("shared-")
    plat = dict(plat, id=sid, custom=False, shared=True, category="Shared packages")
    lib["packages"] = [p for p in lib.get("packages", []) if p["id"] != sid] + [plat]
    path.write_text(json.dumps(lib, indent=1), encoding="utf-8")
    return plat


def remove_package(path: Path, pid: str):
    lib = read_library(path)
    lib["packages"] = [p for p in lib.get("packages", []) if p["id"] != pid]
    path.write_text(json.dumps(lib, indent=1), encoding="utf-8")
