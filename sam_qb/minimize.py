"""Data minimization: for each vendor package, the sensitive columns it sends and whether the vendor's layout
needs them. Optional ones can be blanked for your district - the column stays (so the file layout doesn't change)
but is sent empty. Blanking saves a district version of the file (File > Reset to standard undoes it)."""
from __future__ import annotations

import copy

from .privacy import LEVELS, report
from .query_model import OutColumn, Part

ORDER = {"restricted": 0, "protected": 1, "personal": 2}


def _needed(platform: dict, file_name: str) -> set[str]:
    rules = (platform.get("rules") or {})
    fr = (rules.get("files") or {}).get(file_name) or {}
    need = set(fr.get("required") or [])
    for u in fr.get("unique") or []:
        need |= set(u if isinstance(u, list) else [u])
    for a, b, c, d in rules.get("refs") or []:
        if a == file_name:
            need.add(b)
        if c == file_name:
            need.add(d)
    return need


def review(platform: dict, settings: dict) -> list[dict]:
    """[{'file', 'heading', 'level', 'source', 'needed', 'blanked'}] sorted most sensitive first."""
    from .exports import build_query
    out = []
    for fe in platform.get("files", []):
        q = build_query(platform, fe, settings)
        need = _needed(platform, fe["file"])
        blanked = {c.heading for c in q.columns if is_blank(c)}
        seen = set()
        for lvl, heading, src in report(q)["shown"]:
            if heading in seen:
                continue
            seen.add(heading)
            out.append({"file": fe["file"], "heading": heading, "level": lvl, "level_name": LEVELS[lvl][0],
                        "source": src, "needed": heading in need, "blanked": heading in blanked})
        for h in blanked - seen:
            out.append({"file": fe["file"], "heading": h, "level": "personal", "level_name": "Blanked",
                        "source": "", "needed": False, "blanked": True})
    out.sort(key=lambda r: (r["needed"], ORDER.get(r["level"], 9), r["file"], r["heading"]))
    return out


def is_blank(c: OutColumn) -> bool:
    return c.kind == "custom" and len(c.parts) == 1 and c.parts[0].kind == "text" and c.parts[0].value == "" \
        and not c.agg


def blank_columns(platform: dict, settings: dict, file_name: str, headings: set[str]) -> int:
    """Save a district version of the file with these columns sent empty. Returns how many were blanked."""
    from .exports import build_query, save_override
    fe = next(f for f in platform["files"] if f["file"] == file_name)
    q = copy.deepcopy(build_query(platform, fe, settings))
    n = 0
    for qq in [q] + list(q.union_parts):
        for i, c in enumerate(qq.columns):
            if c.heading in headings and not is_blank(c):
                qq.columns[i] = OutColumn("custom", heading=c.heading, parts=[Part("text", value="")])
                n += 1
    if n:
        save_override(platform, fe, q)
    return n
