"""Version history for saved queries (.samq) and district versions of export files.

Before a file is overwritten (or a district version is reset), the old copy goes to a '.history' folder next to
it: <folder>/.history/<file name>/<YYYYMMDD-HHMMSS>.<ext>. The newest KEEP copies are kept."""
from __future__ import annotations

import datetime as dt
import difflib
import json
import shutil
from pathlib import Path

KEEP = 30


def _hist_dir(path: Path) -> Path:
    path = Path(path)
    return path.parent / ".history" / path.name


def snapshot(path, note: str = "") -> Path | None:
    """Copy the current file into its history (skipped when identical to the newest copy)."""
    path = Path(path)
    if not path.is_file():
        return None
    d = _hist_dir(path)
    d.mkdir(parents=True, exist_ok=True)
    newest = versions(path)
    data = path.read_bytes()
    if newest and Path(newest[0]["path"]).read_bytes() == data:
        return None
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    out = d / f"{stamp}{path.suffix}"
    out.write_bytes(data)
    if note:
        (d / f"{stamp}.note").write_text(note, encoding="utf-8")
    for old in versions(path)[KEEP:]:
        for f in (Path(old["path"]), Path(old["path"]).with_suffix(".note")):
            try:
                f.unlink()
            except OSError:
                pass
    return out


def versions(path) -> list[dict]:
    """Newest first: [{'path', 'when' (datetime), 'note'}]"""
    path = Path(path)
    d = _hist_dir(path)
    if not d.is_dir():
        return []
    out = []
    for f in d.glob(f"*{path.suffix}"):
        try:
            when = dt.datetime.strptime(f.stem[:15], "%Y%m%d-%H%M%S")
        except ValueError:
            continue
        note = f.with_suffix(".note")
        out.append({"path": str(f), "when": when, "stem": f.stem,
                    "note": note.read_text(encoding="utf-8") if note.exists() else ""})
    return sorted(out, key=lambda v: v["stem"], reverse=True)


def restore(path, version_path) -> None:
    """Put an old copy back (the current file is kept in the history first)."""
    path = Path(path)
    data = Path(version_path).read_bytes()      # read first: the snapshot below may prune this very copy
    snapshot(path, "before restoring an older version")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _query_of(path) -> "object | None":
    from .query_model import QueryDef
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    if "query" in d and "tables" not in d:     # district version wrapper
        d = d["query"]
    try:
        return QueryDef.from_dict(d)
    except Exception:
        return None


def describe_changes(old_path, new_path) -> list[str]:
    """Plain-English list of what differs between two saved versions."""
    a, b = _query_of(old_path), _query_of(new_path)
    if a is None or b is None:
        return ["One of the versions couldn't be read."]
    out = []
    ha, hb = [c.heading for c in a.columns], [c.heading for c in b.columns]
    added = [h for h in hb if h not in ha]
    removed = [h for h in ha if h not in hb]
    if added:
        out.append("Columns added: " + ", ".join(added))
    if removed:
        out.append("Columns removed: " + ", ".join(removed))
    if not added and not removed and ha != hb:
        out.append("Column order changed")
    from .query_model import generate_sql
    for h in set(ha) & set(hb):
        ca = next(c for c in a.columns if c.heading == h)
        cb = next(c for c in b.columns if c.heading == h)
        if json.dumps(ca.__dict__, default=lambda o: o.__dict__, sort_keys=True) != \
                json.dumps(cb.__dict__, default=lambda o: o.__dict__, sort_keys=True):
            out.append(f"Column '{h}' changed (source or format)")
    ta, tb = {t.alias for t in a.tables}, {t.alias for t in b.tables}
    if ta != tb:
        out.append("Tables: " + ", ".join(f"+{x}" for x in sorted(tb - ta)) + " " +
                   ", ".join(f"-{x}" for x in sorted(ta - tb)))
    fa = [(c.alias, c.column, c.op, c.value, c.value2) for g in a.filters for c in g.conditions]
    fb = [(c.alias, c.column, c.op, c.value, c.value2) for g in b.filters for c in g.conditions]
    if fa != fb:
        out.append("Filters changed")
    if [s.heading for s in a.sort] != [s.heading for s in b.sort] or a.distinct != b.distinct or a.top != b.top:
        out.append("Sort / options changed")
    if a.name != b.name:
        out.append(f"Renamed from '{a.name}' to '{b.name}'")
    if generate_sql(a, header=False) == generate_sql(b, header=False) and not out:
        out.append("No change to the SQL (only the description or save time differs)")
    return out


def sql_diff(old_path, new_path) -> str:
    from .query_model import generate_sql
    a, b = _query_of(old_path), _query_of(new_path)
    if a is None or b is None:
        return ""
    return "\n".join(difflib.unified_diff(generate_sql(a, header=False).splitlines(),
                                          generate_sql(b, header=False).splitlines(),
                                          "older version", "newer version", lineterm="", n=1))
