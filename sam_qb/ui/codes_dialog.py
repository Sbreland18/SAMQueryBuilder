"""'SAM Codes & Schools' - your schools (SchoolID + name) and real code lists."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView,
                               QLabel, QListWidget, QMessageBox, QPushButton, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget, QApplication)

from .. import codes as C
from .widgets import label


class _Table(QWidget):
    def __init__(self, headers, rows, keys):
        super().__init__()
        self.keys = keys
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.t = QTableWidget(0, len(headers))
        self.t.setHorizontalHeaderLabels(headers)
        self.t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.t.setSelectionBehavior(QAbstractItemView.SelectRows)
        lay.addWidget(self.t, 1)
        row = QHBoxLayout()
        for txt, fn in (("Add row", self.add), ("Remove selected", self.remove), ("Paste from Excel", self.paste),
                        ("Clear", self.clear)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.set_rows(rows)

    def set_rows(self, rows):
        self.t.setRowCount(0)
        for r in rows:
            self.add([str(r.get(k, "")) for k in self.keys])

    def add(self, values=None):
        i = self.t.rowCount()
        self.t.insertRow(i)
        for c in range(len(self.keys)):
            self.t.setItem(i, c, QTableWidgetItem((values or [""] * len(self.keys))[c] if values else ""))
        if not values:
            self.t.editItem(self.t.item(i, 0))

    def remove(self):
        for r in sorted({i.row() for i in self.t.selectedIndexes()}, reverse=True):
            self.t.removeRow(r)

    def clear(self):
        self.t.setRowCount(0)

    def paste(self):
        text = QApplication.clipboard().text()
        for line in text.splitlines():
            parts = [p.strip() for p in (line.split("\t") if "\t" in line else line.split(","))]
            if any(parts) and not parts[0].lower().replace(" ", "") in ("schoolid", "code"):
                self.add((parts + [""] * len(self.keys))[:len(self.keys)])

    def rows(self):
        out = []
        for i in range(self.t.rowCount()):
            vals = [(self.t.item(i, c).text().strip() if self.t.item(i, c) else "") for c in range(len(self.keys))]
            if vals[0]:
                out.append(dict(zip(self.keys, vals)))
        return out


class CodesDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SAM Codes & Schools")
        self.resize(900, 620)
        self.settings = settings
        lay = QVBoxLayout(self)
        lay.addWidget(label("Add your schools (with the SchoolID SAM uses) and load your real code lists. Schools "
                            "become one-click filters, codes become drop-downs in filters, and the Query Assistant "
                            "uses them. Get them by running <b>Export to a platform > Find your SAM codes</b> in SAM, "
                            "saving the results as CSV and clicking <b>Import CSV files</b> - or type / paste them here.",
                            "subtitle"))
        body = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setMaximumWidth(260)
        self.stack = QStackedWidget()
        self.pages = {}
        self.nav.addItem("Schools")
        self.pages["schools"] = _Table(["SchoolID", "School name", "School code", "Short name"],
                                       settings.get("schools", []), ["id", "name", "code", "short"])
        self.stack.addWidget(self.pages["schools"])
        for key, (lbl, _t) in C.CODE_SETS.items():
            self.nav.addItem(lbl)
            self.pages[key] = _Table(["Code", "Description"], settings.get("codes", {}).get(key, []),
                                     ["code", "description"])
            self.stack.addWidget(self.pages[key])
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        self._counts()
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        lay.addLayout(body, 1)
        row = QHBoxLayout()
        imp = QPushButton("Import CSV files...")
        imp.setObjectName("primary")
        imp.clicked.connect(self.import_files)
        row.addWidget(imp)
        row.addWidget(QLabel("<i>Tip: you can select all the helper-query CSVs at once.</i>"))
        row.addStretch()
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _counts(self):
        keys = ["schools"] + list(C.CODE_SETS)
        for i, k in enumerate(keys):
            n = len(self.pages[k].rows())
            base = "Schools" if k == "schools" else C.CODE_SETS[k][0]
            self.nav.item(i).setText(f"{base}  ({n})" if n else base)

    def import_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Import SAM code CSV files", str(Path.home()),
                                                "CSV / text (*.csv *.txt);;All files (*)")
        done, skipped = [], []
        for f in files:
            rows = C._read_csv(f)
            target = C.guess_set(f, rows)
            if target is None:
                from PySide6.QtWidgets import QInputDialog
                names = ["Schools"] + [v[0] for v in C.CODE_SETS.values()]
                pick, ok = QInputDialog.getItem(self, "Which list?", f"What does {Path(f).name} contain?", names, 0,
                                                False)
                if not ok:
                    skipped.append(Path(f).name)
                    continue
                target = "schools" if pick == "Schools" else [k for k, v in C.CODE_SETS.items() if v[0] == pick][0]
            if target == "schools":
                data = C.parse_schools(f)
            else:
                data = C.parse_codes(f)
            if not data:
                skipped.append(Path(f).name)
                continue
            self.pages[target].set_rows(data)
            done.append(f"{Path(f).name} -> {'Schools' if target == 'schools' else C.CODE_SETS[target][0]} "
                        f"({len(data)})")
            if target == "owner_type":
                self._owner_tables = data
        self._counts()
        if done or skipped:
            QMessageBox.information(self, "Import", ("Loaded:\n- " + "\n- ".join(done) if done else "")
                                    + ("\n\nSkipped (no rows found):\n- " + "\n- ".join(skipped) if skipped else ""))

    def values(self) -> tuple[dict, dict]:
        """Returns (new settings, district setting suggestions that were applied)."""
        s = dict(self.settings)
        s["schools"] = self.pages["schools"].rows()
        codes = {}
        for k in C.CODE_SETS:
            rows = self.pages[k].rows()
            if k == "owner_type" and getattr(self, "_owner_tables", None):
                tables = {r["code"]: r.get("table", "") for r in self._owner_tables}
                for r in rows:
                    r["table"] = tables.get(r["code"], "")
            if rows:
                codes[k] = rows
        s["codes"] = codes
        sugg = C.suggest_district_settings(s)
        if sugg:
            d = dict(s.get("district") or {})
            d.update(sugg)
            s["district"] = d
        return s, sugg
