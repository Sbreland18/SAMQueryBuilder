"""Platform export packages (Clever, OneRoster, SDS, Google, Canvas, NWEA...)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from . import district
from .paths import active_data_file
from .query_model import generate_sql


def load_platforms(include_custom: bool = True) -> list[dict]:
    """Packages from data/exports.json, with the district's own vendor-template packages first."""
    try:
        std = json.loads(active_data_file("exports.json").read_text(encoding="utf-8")).get("platforms", [])
    except Exception:
        std = []
    if not include_custom:
        return std
    try:
        from .template_builder import load_custom
        custom = load_custom()
    except Exception:
        custom = []
    try:
        from .shared_library import load_shared
        shared = load_shared()
    except Exception:
        shared = []
    ids = {p["id"] for p in std}
    custom = [c for c in custom if c["id"] not in ids]
    ids |= {c["id"] for c in custom}
    return custom + [s for s in shared if s["id"] not in ids] + std


def safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "_", name).strip() or "file"


def missing_settings(platform: dict, settings: dict) -> list[str]:
    """District settings this package needs that are still blank (e.g. owner type codes)."""
    ds = district.get(settings)
    out = []
    for var in platform.get("requires", []):
        key = var.lower()
        if not str(ds.get(key, "")).strip():
            out.append(district.LABELS.get(key, var))
    return out


# tables that carry a SchoolID, in the order a school filter should prefer them
SCHOOL_ALIASES = ("stuSchool", "empSchool", "SchoolDef", "Schedule", "GradeSchool", "TranscriptSchool",
                  "AttendanceDaily", "DisciplineIncident", "historyStudentSessions")


def school_ids(platform: dict, settings: dict) -> list[str]:
    """SchoolIDs this package is limited to (empty = all schools)."""
    return [str(x) for x in (settings.get("export_schools") or {}).get(platform.get("id", ""), []) if str(x).strip()]


def apply_school_filter(q, ids: list[str]) -> bool:
    """Add 'SchoolID is one of ...' to the query and each combined part. Returns True if it could."""
    from .query_model import Condition, FilterGroup
    if not ids:
        return False
    done = False
    for part in [q] + list(q.union_parts):
        aliases = {t.alias for t in part.tables}
        alias = next((a for a in SCHOOL_ALIASES if a in aliases), None)
        if not alias:
            continue
        cond = Condition(alias, "SchoolID", "in", ", ".join(ids))
        grp = next((g for g in part.filters if g.match == "ALL"), None)
        if grp is None:
            grp = FilterGroup("ALL", [])
            part.filters.append(grp)
        grp.conditions = [c for c in grp.conditions if not (c.alias == alias and c.column == "SchoolID")]
        grp.conditions.append(cond)
        done = True
    return done


# ----------------------------------------------------------------------------- district versions (overrides)
def _std_hash(file_entry: dict) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(file_entry["query"], sort_keys=True).encode("utf-8")).hexdigest()[:16]


def override_path(platform_id: str, file_name: str) -> Path:
    from .paths import user_dir
    return user_dir() / "package_overrides" / safe(platform_id) / (safe(file_name) + ".json")


def get_override(platform: dict, file_entry: dict) -> dict | None:
    p = override_path(platform["id"], file_entry["file"])
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def override_state(platform: dict, file_entry: dict) -> str:
    """'' (standard), 'custom', or 'custom-outdated' (the standard file changed in an update since)."""
    ov = get_override(platform, file_entry)
    if not ov:
        return ""
    return "custom" if ov.get("standard_hash") == _std_hash(file_entry) else "custom-outdated"


def save_override(platform: dict, file_entry: dict, q) -> Path:
    p = override_path(platform["id"], file_entry["file"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"platform": platform["id"], "file": file_entry["file"], "saved": datetime.now().isoformat(
        timespec="seconds"), "standard_hash": _std_hash(file_entry), "query": q.to_dict()}, indent=1), encoding="utf-8")
    from .audit import record
    record("District package versions", f"{platform['name']} / {file_entry['file']}: saved district version")
    return p


def remove_override(platform: dict, file_entry: dict) -> bool:
    p = override_path(platform["id"], file_entry["file"])
    if p.exists():
        p.unlink()
        from .audit import record
        record("District package versions", f"{platform['name']} / {file_entry['file']}: reset to standard")
        return True
    return False


def build_query(platform: dict, file_entry: dict, settings: dict, use_override: bool = True):
    from .query_model import QueryDef
    ov = get_override(platform, file_entry) if use_override else None
    if ov:
        q = QueryDef.from_dict(ov["query"])
        q.description = q.description or f"Creates {file_entry['file']} for {platform['name']} (district version)."
        ids = school_ids(platform, settings)
        if ids:
            apply_school_filter(q, ids)
        return q
    q = district.expand(file_entry["query"], settings)
    q.name = f"{platform['name'].split(' (')[0]} - {file_entry['file']}"
    if not q.description:
        q.description = f"Creates {file_entry['file']} for {platform['name']}."
    ids = school_ids(platform, settings)
    if ids and apply_school_filter(q, ids):
        names = {str(s.get("id")): s.get("name", "") for s in settings.get("schools", [])}
        q.description += " Limited to: " + ", ".join(names.get(i) or f"SchoolID {i}" for i in ids) + "."
    return q


def save_package(platform: dict, settings: dict, folder: str | Path) -> list[Path]:
    """Write one .sql per CSV file, any static files (e.g. manifest.csv) and a setup guide."""
    out = Path(folder) / safe(platform["name"])
    out.mkdir(parents=True, exist_ok=True)
    written = []
    rows = []
    priv = []
    from .privacy import summary_lines
    for i, fe in enumerate(platform["files"], 1):
        q = build_query(platform, fe, settings)
        p = out / f"{i:02d} {safe(Path(fe['file']).stem)}.sql"
        p.write_text(generate_sql(q), encoding="utf-8")
        written.append(p)
        rows.append((i, q.name, fe["file"]))
        priv.append((fe["file"], summary_lines(q)))
    for name, text in (platform.get("static_files") or {}).items():
        p = out / name
        p.write_text(text, encoding="utf-8", newline="\n")
        written.append(p)
    guide = [f"{platform['name']} export - created {datetime.now():%m/%d/%Y %I:%M %p}",
             "=" * 70, "", f"Works with: {platform.get('works_with', '')}", "",
             platform.get("description", ""), "",
             f"Specification: {platform.get('spec_url', '')}",
             f"Deliver files by: {platform.get('delivery', '')}", "",
             "ONE-TIME SETUP IN SAM (CAC Agent, runs automatically every night)",
             "-" * 70,
             "1. Administration > CAC Agent > Query Maintenance > Add New, once for each .sql file below:",
             "   paste the file's contents into the Query box and use the Query Title shown.",
             "2. Administration > CAC Agent > Agent Maintenance > Add Job for each query:",
             "   put every job in the SAME folder and use the exact File Name shown (vendors require these names).",
             "3. Schedule the Windows task 'CAS Agent Listener' at least 1 hour after the job time.",
             "4. Upload/sync the folder to the platform (see 'Deliver files by' above).", "",
             f"{'#':<4}{'Query title':<48}File name", "-" * 70]
    guide += [f"{i:<4}{t:<48}{f}" for i, t, f in rows]
    if platform.get("static_files"):
        guide += ["", "Also include these files with the upload (already saved in this folder): "
                  + ", ".join(platform["static_files"])]
    guide += ["", "Or run a query once by hand: Ad Hoc Query > Query > paste > Save, then Run Query and save the "
              "result as CSV with the file name shown above."]
    guide += ["", "DATA SHARED WITH THIS VENDOR (check it against your data-privacy agreement)", "-" * 70]
    for f, lines in priv:
        guide.append(f"{f}: " + ("names, IDs, grades and schools only" if not lines else ""))
        guide += [f"    {ln}" for ln in lines]
    if platform.get("confirm_with_vendor"):
        guide += ["", "NOTE: " + platform["confirm_with_vendor"]]
    gp = out / "SETUP - read me.txt"
    gp.write_text("\n".join(guide) + "\n", encoding="utf-8")
    written.append(gp)
    return written
