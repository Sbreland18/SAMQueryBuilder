"""Query Assistant feedback - saved locally as JSON lines so a district can send them in to improve the
built-in helper's vocabulary (data/assistant_vocab.json) in a future update."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .paths import user_dir
from .version import __version__


def feedback_file() -> Path:
    from .paths import root_dir
    return root_dir() / "assistant_feedback.jsonl"


def record(messages: list[str], plan, good: bool, comment: str = "", sql: str = "") -> Path:
    entry = {
        "when": dt.datetime.now().isoformat(timespec="seconds"),
        "app_version": __version__,
        "good": bool(good),
        "messages": list(messages or []),
        "source": getattr(plan, "source", ""),
        "understood": list(getattr(plan, "understood", []) or []),
        "unsure": list(getattr(plan, "unsure", []) or []),
        "tables": [t.table for t in plan.query.tables] if plan else [],
        "columns": [c.heading for c in plan.query.columns] if plan else [],
        "expected": comment,
        "sql": sql,
    }
    p = feedback_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return p


def load() -> list[dict]:
    p = feedback_file()
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out


def export_to(path: str | Path) -> int:
    rows = load()
    Path(path).write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""), encoding="utf-8")
    return len(rows)
