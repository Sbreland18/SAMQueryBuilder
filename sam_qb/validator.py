"""Export file checker - validates the CSV files SAM / the CAC Agent produced before they are uploaded.

Rules come from each platform in exports.json:
  "rules": {
     "files": {"students.csv": {"required": [...], "unique": [[...]], "formats": {"DOB": "date_us"}}},
     "refs":  [["enrollments.csv", "Student_id", "students.csv", "Student_id"]],
     "delimiter": ","
  }
The expected headers are the query's column headings.

Format names: date_us (MM/DD/YYYY), date_iso (YYYY-MM-DD), email, bool (true/false), yn (Y/N), tf (T/F),
int, digits, phone10, year, blank, enum:A|B|C, maxlen:N.
"""
from __future__ import annotations

import csv
import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

MAX_EXAMPLES = 25


@dataclass
class Issue:
    level: str          # error | warning | info
    file: str
    message: str
    rows: list = field(default_factory=list)     # example row numbers (1 = first data row)
    count: int = 1


@dataclass
class Report:
    platform: str
    folder: str
    issues: list = field(default_factory=list)
    files: dict = field(default_factory=dict)    # file -> row count (None = missing)

    @property
    def errors(self):
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self):
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self):
        return not self.errors

    def text(self) -> str:
        lines = [f"{self.platform} - export check of {self.folder}", f"Checked {datetime.now():%m/%d/%Y %I:%M %p}", "",
                 ("PASSED" if self.ok else "FAILED") + f": {len(self.errors)} error(s), {len(self.warnings)} warning(s)",
                 ""]
        for f, n in self.files.items():
            lines.append(f"  {f}: " + ("MISSING" if n is None else f"{n} rows"))
        lines.append("")
        for i in self.issues:
            where = f" (rows {', '.join(map(str, i.rows[:10]))}{'...' if len(i.rows) > 10 else ''})" if i.rows else ""
            cnt = f" x{i.count}" if i.count > 1 else ""
            lines.append(f"[{i.level.upper()}] {i.file}: {i.message}{cnt}{where}")
        return "\n".join(lines) + "\n"


_DATE_US = re.compile(r"^(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])/\d{4}$")
_DATE_ISO = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[A-Za-z]{2,}$")


def check_value(fmt: str, v: str) -> bool:
    if v == "":
        return True
    if fmt == "date_us":
        return bool(_DATE_US.match(v))
    if fmt == "date_iso":
        return bool(_DATE_ISO.match(v))
    if fmt == "email":
        return bool(_EMAIL.match(v))
    if fmt == "bool":
        return v in ("true", "false")
    if fmt == "yn":
        return v.upper() in ("Y", "N", "YES", "NO")
    if fmt == "tf":
        return v.upper() in ("T", "F", "Y", "N")
    if fmt == "int":
        return bool(re.fullmatch(r"-?\d+", v))
    if fmt == "digits":
        return v.isdigit()
    if fmt == "phone10":
        return len(re.sub(r"\D", "", v)) == 10
    if fmt == "year":
        return bool(re.fullmatch(r"(19|20)\d\d", v))
    if fmt == "blank":
        return v == ""
    if fmt.startswith("enum:"):
        return v in fmt[5:].split("|")
    if fmt.startswith("maxlen:"):
        return len(v) <= int(fmt[7:])
    return True


FORMAT_TEXT = {"date_us": "MM/DD/YYYY dates", "date_iso": "YYYY-MM-DD dates", "email": "an email address",
               "bool": "true or false", "yn": "Y or N", "tf": "T or F", "int": "a whole number", "digits": "digits only",
               "phone10": "a 10-digit phone number", "year": "a 4-digit year", "blank": "blank (bulk files)"}
WARN_ONLY = {"email", "phone10"}


def read_csv(path: Path, delimiter: str = ","):
    raw = path.read_bytes()
    issues = []
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
        issues.append(("warning", "File is not UTF-8 (special characters like accents may be garbled). Save as UTF-8."))
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    return rows, issues


def check_folder(platform: dict, folder: str | Path, file_overrides: dict | None = None) -> Report:
    folder = Path(folder)
    rules = platform.get("rules", {})
    frules = rules.get("files", {})
    delim = rules.get("delimiter", ",")
    rep = Report(platform["name"], str(folder))
    data: dict[str, tuple[list, list[dict]]] = {}

    for fe in platform["files"]:
        fname = fe["file"]
        path = Path((file_overrides or {}).get(fname, folder / fname))
        if not path.exists():
            # case-insensitive match (Windows users rename files)
            alt = next((p for p in folder.glob("*") if p.name.lower() == fname.lower()), None) if folder.exists() else None
            if alt:
                path = alt
                if alt.name != fname:
                    rep.issues.append(Issue("warning", fname, f"File is named '{alt.name}' - the platform expects "
                                                              f"exactly '{fname}'."))
        if not path.exists():
            rep.files[fname] = None
            rep.issues.append(Issue("error", fname, "File not found in the folder."))
            continue
        rows, enc = read_csv(path, delim)
        for lvl, msg in enc:
            rep.issues.append(Issue(lvl, fname, msg))
        if not rows:
            rep.files[fname] = 0
            rep.issues.append(Issue("error", fname, "File is empty (no header row)."))
            continue
        header = [h.strip() for h in rows[0]]
        body = [r for r in rows[1:] if any(c.strip() for c in r)]
        rep.files[fname] = len(body)
        expected = [c["heading"] for c in fe["query"].get("columns", [])]
        _check_header(rep, fname, header, expected)
        recs = []
        bad_len = []
        for n, r in enumerate(body, 1):
            if len(r) != len(header):
                bad_len.append(n)
            recs.append({header[i]: (r[i].strip() if i < len(r) else "") for i in range(len(header))})
        if bad_len:
            rep.issues.append(Issue("error", fname, f"Rows have a different number of values than the header "
                                                    f"(usually an unquoted comma inside a value)",
                                    bad_len[:MAX_EXAMPLES], len(bad_len)))
        if not body:
            rep.issues.append(Issue("warning", fname, "File has a header but no data rows."))
        fr = frules.get(fname, {})
        _check_rows(rep, fname, header, recs, fr)
        data[fname] = (header, recs)

    for a_file, a_col, b_file, b_col in rules.get("refs", []):
        if a_file not in data or b_file not in data:
            continue
        b_vals = {r.get(b_col, "") for r in data[b_file][1]}
        missing = []
        for n, r in enumerate(data[a_file][1], 1):
            vals = [x.strip() for x in r.get(a_col, "").split(",")] if a_col.endswith("Ids") else [r.get(a_col, "")]
            if any(v and v not in b_vals for v in vals):
                missing.append(n)
        if missing:
            rep.issues.append(Issue("error", a_file, f"{a_col} values not found in {b_file} ({b_col}) - the platform "
                                                     f"will reject or skip these rows", missing[:MAX_EXAMPLES],
                                    len(missing)))
    if not rep.issues:
        rep.issues.append(Issue("info", "-", "Everything checks out."))
    return rep


def _check_header(rep, fname, header, expected):
    if not expected:
        return
    if header == expected:
        return
    lower = {h.lower(): h for h in header}
    missing = [e for e in expected if e not in header]
    case = [e for e in missing if e.lower() in lower]
    missing = [e for e in missing if e not in case]
    extra = [h for h in header if h not in expected and h.lower() not in {e.lower() for e in expected}]
    if missing:
        rep.issues.append(Issue("error", fname, "Missing column(s): " + ", ".join(missing)))
    if case:
        rep.issues.append(Issue("error", fname, "Column name capitalisation differs: " +
                                ", ".join(f"'{lower[c.lower()]}' should be '{c}'" for c in case)))
    if extra:
        rep.issues.append(Issue("warning", fname, "Extra column(s) the platform may not expect: " + ", ".join(extra)))
    if not missing and not case and not extra and header != expected:
        rep.issues.append(Issue("warning", fname, "Columns are in a different order than the template."))


def _check_rows(rep, fname, header, recs, fr):
    for col in fr.get("required", []):
        if col not in header:
            continue
        blank = [n for n, r in enumerate(recs, 1) if not r.get(col)]
        if blank:
            rep.issues.append(Issue("error", fname, f"Required column '{col}' is blank", blank[:MAX_EXAMPLES],
                                    len(blank)))
    for key in fr.get("unique", []):
        key = [key] if isinstance(key, str) else key
        if any(k not in header for k in key):
            continue
        seen = defaultdict(list)
        for n, r in enumerate(recs, 1):
            v = tuple(r.get(k, "") for k in key)
            if any(v):
                seen[v].append(n)
        dups = [rows for rows in seen.values() if len(rows) > 1]
        if dups:
            flat = [n for rows in dups for n in rows]
            examples = ", ".join("/".join(v) for v, rows in list(seen.items()) if len(rows) > 1)[:200]
            rep.issues.append(Issue("error", fname, f"Duplicate {' + '.join(key)} (e.g. {examples})",
                                    flat[:MAX_EXAMPLES], len(dups)))
    for col, fmt in fr.get("formats", {}).items():
        if col not in header:
            continue
        bad = [n for n, r in enumerate(recs, 1) if not check_value(fmt, r.get(col, ""))]
        if bad:
            what = FORMAT_TEXT.get(fmt) or (("one of " + ", ".join(fmt[5:].split("|"))) if fmt.startswith("enum:")
                                            else f"at most {fmt[7:]} characters" if fmt.startswith("maxlen:") else fmt)
            sample = Counter(recs[n - 1].get(col, "") for n in bad).most_common(3)
            rep.issues.append(Issue("warning" if fmt in WARN_ONLY else "error", fname,
                                    f"'{col}' should be {what} (found e.g. {', '.join(repr(s) for s, _ in sample)})",
                                    bad[:MAX_EXAMPLES], len(bad)))
