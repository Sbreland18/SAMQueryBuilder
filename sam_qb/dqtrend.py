"""Data quality trends: keep a weekly count of every Data cleanup report (missing MSIS IDs, bad emails, no
primary contact...) so you can see whether the data is getting better before state reporting deadlines.

Counts come from the cleanup CSVs the CAC Agent saves (the folder set in Tools > District health report) or,
with the optional SAM connection, from running the cleanup queries directly. Only counts are stored.
History: <district folder>/dq_history.json = [{"date": "2026-10-16", "source": "files"|"sam", "counts": {...}}]
Run headless:  "SAM Ad Hoc Query Builder.exe" --dqsnapshot"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

KEEP = 156  # about three years of weekly snapshots


def _path() -> Path:
    from .paths import user_dir
    return user_dir() / "dq_history.json"


def history() -> list[dict]:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(h: list[dict]):
    _path().write_text(json.dumps(h[-KEEP:], indent=1), encoding="utf-8")


def _cleanup():
    from .exports import load_platforms
    return next((p for p in load_platforms() if p["id"] == "cleanup"), None)


def report_names() -> dict[str, str]:
    """{file name: report title}"""
    p = _cleanup()
    return {fe["file"]: (fe["query"].get("name") or fe["file"]).replace("Cleanup - ", "") for fe in (p or {}).get(
        "files", [])}


def counts_from_folder(folder) -> dict[str, int]:
    from .uploader import count_rows
    out = {}
    folder = Path(folder or "")
    if not folder.is_dir():
        return out
    for fname in report_names():
        f = folder / fname
        if f.exists():
            out[fname] = max(0, count_rows(f))
    return out


def counts_from_sam(settings: dict) -> dict[str, int]:
    from . import samdb
    from .exports import build_query
    from .query_model import generate_sql
    p = _cleanup()
    out = {}
    for fe in (p or {}).get("files", []):
        sql = generate_sql(build_query(p, fe, settings), header=False)
        try:
            cur = samdb.run(settings, f"SELECT COUNT(*) AS n FROM ({samdb.strip_order_by(sql)}) AS q", max_rows=1,
                            count=False)
            out[fe["file"]] = int(cur["rows"][0][0])
        except Exception:
            continue
    return out


def take_snapshot(settings: dict, source: str | None = None, today: dt.date | None = None) -> dict:
    """Record today's counts (replaces an earlier snapshot from the same day). Returns the snapshot."""
    from . import samdb
    from .health import get as health_get
    today = today or dt.date.today()
    if source is None:
        source = "sam" if samdb.enabled(settings) else "files"
    counts = counts_from_sam(settings) if source == "sam" else counts_from_folder(health_get(settings)["cleanup_folder"])
    if not counts:
        raise RuntimeError("No cleanup results found. Save the Data cleanup reports' CSV files in the folder set in "
                           "Tools > District health report (or turn on the SAM connection).")
    snap = {"date": today.isoformat(), "source": source, "counts": counts}
    h = [x for x in history() if x.get("date") != snap["date"]] + [snap]
    h.sort(key=lambda x: x["date"])
    _save(h)
    return snap


def maybe_snapshot(settings: dict, min_days: int = 6):
    """Take a snapshot when the newest one is older than min_days (called by the health report)."""
    h = history()
    if h:
        try:
            if (dt.date.today() - dt.date.fromisoformat(h[-1]["date"])).days < min_days:
                return None
        except ValueError:
            pass
    try:
        return take_snapshot(settings)
    except Exception:
        return None


def table(h: list[dict] | None = None) -> list[dict]:
    """One row per report: {'file', 'name', 'values': [(date, n)], 'latest', 'change', 'trend'}"""
    h = history() if h is None else h
    names = report_names()
    files = list(names) + sorted({f for s in h for f in s["counts"] if f not in names})
    out = []
    for f in files:
        vals = [(s["date"], s["counts"][f]) for s in h if f in s["counts"]]
        if not vals:
            continue
        latest = vals[-1][1]
        prev = vals[-2][1] if len(vals) > 1 else None
        change = None if prev is None else latest - prev
        first = vals[0][1]
        trend = "new" if prev is None else ("better" if latest < first else "worse" if latest > first else "same")
        out.append({"file": f, "name": names.get(f, f), "values": vals, "latest": latest, "change": change,
                    "trend": trend})
    return out


def schedule(settings: dict) -> str:
    from .scheduler import create
    d = settings.get("dq_schedule") or {}
    return create("Data quality snapshot", "--dqsnapshot", "WEEKLY", d.get("time") or "06:30", d.get("day") or "MON")


def headless() -> int:
    from .paths import load_settings
    settings = load_settings()
    if not (settings.get("dq_schedule") or {}).get("enabled", True):
        return 0
    try:
        snap = take_snapshot(settings)
        if sys.stdout:
            print(f"Snapshot {snap['date']}: {sum(snap['counts'].values()):,} rows in {len(snap['counts'])} reports")
        return 0
    except Exception as e:  # noqa: BLE001
        if sys.stdout:
            print(f"FAILED: {e}")
        return 1
