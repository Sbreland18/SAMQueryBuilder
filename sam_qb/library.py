"""Saved-query library: favorites, tags (used like folders) and search.
Metadata lives next to the queries in _library.json, so a team folder shares it too."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

FILE = "_library.json"


def _path() -> Path:
    from .paths import queries_dir
    return queries_dir() / FILE


def load() -> dict:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(meta: dict):
    _path().write_text(json.dumps(meta, indent=1, sort_keys=True), encoding="utf-8")


def entry(meta: dict, name: str) -> dict:
    return {"favorite": False, "tags": [], **(meta.get(name) or {})}


def set_favorite(file_name: str, on: bool):
    meta = load()
    e = entry(meta, file_name)
    e["favorite"] = bool(on)
    meta[file_name] = e
    save(meta)


def set_tags(file_name: str, tags: list[str]):
    meta = load()
    e = entry(meta, file_name)
    e["tags"] = sorted({t.strip() for t in tags if t.strip()}, key=str.lower)
    meta[file_name] = e
    save(meta)


def rename(old: str, new: str):
    meta = load()
    if old in meta:
        meta[new] = meta.pop(old)
        save(meta)


def all_tags(meta: dict | None = None) -> list[str]:
    meta = load() if meta is None else meta
    return sorted({t for e in meta.values() for t in e.get("tags", [])}, key=str.lower)


def queries(search: str = "", tag: str = "", favorites_only: bool = False) -> list[dict]:
    """[{'path', 'file', 'name', 'description', 'modified', 'favorite', 'tags'}] - favorites first, then newest."""
    from .paths import queries_dir
    meta = load()
    words = [w for w in search.lower().split() if w]
    out = []
    for p in queries_dir().glob("*.samq"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        e = entry(meta, p.name)
        if favorites_only and not e["favorite"]:
            continue
        if tag and tag not in e["tags"]:
            continue
        hay = " ".join([d.get("name", ""), d.get("description", ""), p.stem, " ".join(e["tags"])] +
                       [t.get("table", "") for t in d.get("tables", [])] +
                       [c.get("heading", "") for c in d.get("columns", [])]).lower()
        if words and not all(w in hay for w in words):
            continue
        out.append({"path": str(p), "file": p.name, "name": d.get("name") or p.stem,
                    "description": d.get("description", ""), "modified": datetime.fromtimestamp(p.stat().st_mtime),
                    "favorite": e["favorite"], "tags": e["tags"]})
    out.sort(key=lambda x: (not x["favorite"], -x["modified"].timestamp()))
    return out
