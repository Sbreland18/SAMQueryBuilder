"""'Who changed?' - compare two versions of an export CSV (e.g. last night's upload and tonight's file)."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

ID_HINTS = ("sourcedid", "user_id", "student id", "student_id", "studentid", "id number", "person_id", "id",
            "school_id", "class_id", "section_id", "employee id", "staff id", "barcode", "identifier")


@dataclass
class Diff:
    file: str
    key: list
    headers: list
    added: list = field(default_factory=list)      # rows (dicts)
    removed: list = field(default_factory=list)
    changed: list = field(default_factory=list)    # (key, {col: (old, new)})
    old_count: int = 0
    new_count: int = 0
    note: str = ""

    def summary(self) -> str:
        return (f"{self.file}: {self.old_count:,} -> {self.new_count:,} rows; {len(self.added):,} added, "
                f"{len(self.removed):,} removed, {len(self.changed):,} changed" + (f" ({self.note})" if self.note else ""))


def read_csv(path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        delim = "|" if sample.count("|") > sample.count(",") else ("\t" if sample.count("\t") > sample.count(",")
                                                                   else ",")
        rd = csv.DictReader(fh, delimiter=delim)
        rows = [r for r in rd if any((v or "").strip() for v in r.values())]
        return list(rd.fieldnames or []), rows


def guess_key(headers: list[str], rows: list[dict], rules: dict | None = None) -> list[str]:
    """Rules' first unique key, else a well-known ID column that is unique, else the whole row."""
    for u in (rules or {}).get("unique", []):
        cols = u if isinstance(u, list) else [u]
        if all(c in headers for c in cols):
            return cols
    low = {h.lower(): h for h in headers}
    for hint in ID_HINTS:
        h = low.get(hint)
        if h and len({r.get(h) for r in rows}) == len(rows):
            return [h]
    for h in headers:
        if "id" in h.lower() and len({r.get(h) for r in rows}) == len(rows) and rows:
            return [h]
    return list(headers)


def diff_files(old_path, new_path, key: list[str] | None = None, rules: dict | None = None) -> Diff:
    oh, old = read_csv(old_path)
    nh, new = read_csv(new_path)
    headers = nh or oh
    note = ""
    if oh and nh and oh != nh:
        changed = ", ".join([f"+{h}" for h in nh if h not in oh] + [f"-{h}" for h in oh if h not in nh])
        note = ("columns changed: " + changed) if changed else "column order changed"
    key = key or guess_key(headers, new or old, rules)
    k = lambda r: tuple((r.get(c) or "").strip() for c in key)  # noqa: E731
    om, nm = {}, {}
    for r in old:
        om.setdefault(k(r), r)
    for r in new:
        nm.setdefault(k(r), r)
    d = Diff(Path(new_path).name, key, headers, old_count=len(old), new_count=len(new), note=note)
    d.added = [nm[x] for x in nm if x not in om]
    d.removed = [om[x] for x in om if x not in nm]
    shared = [h for h in headers if h in oh]
    for x in nm:
        if x in om:
            ch = {h: (om[x].get(h, ""), nm[x].get(h, "")) for h in shared
                  if (om[x].get(h) or "").strip() != (nm[x].get(h) or "").strip()}
            if ch:
                d.changed.append((" / ".join(x), ch))
    return d


def diff_folders(old_dir, new_dir, names: list[str] | None = None, rules: dict | None = None) -> list[Diff]:
    old_dir, new_dir = Path(old_dir), Path(new_dir)
    names = names or sorted(p.name for p in new_dir.iterdir() if p.suffix.lower() in (".csv", ".txt"))
    out = []
    for n in names:
        o, nw = old_dir / n, new_dir / n
        if o.exists() and nw.exists():
            out.append(diff_files(o, nw, rules=((rules or {}).get("files") or {}).get(n)))
    return out


def write_report(diffs: list[Diff], path):
    """One CSV listing every added / removed / changed row across files."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["File", "Change", "Key", "Column", "Before", "After"])
        for d in diffs:
            for r in d.added:
                w.writerow([d.file, "added", " / ".join(r.get(c, "") for c in d.key), "", "", ""])
            for r in d.removed:
                w.writerow([d.file, "removed", " / ".join(r.get(c, "") for c in d.key), "", "", ""])
            for key, ch in d.changed:
                for col, (a, b) in ch.items():
                    w.writerow([d.file, "changed", key, col, a, b])
