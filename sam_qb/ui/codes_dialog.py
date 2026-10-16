"""'SAM Codes & Schools' - your schools (SchoolID + name) and real code lists."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QListWidget, QMessageBox, QPlainTextEdit, QPushButton,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QApplication)

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


def _csv_text(res: dict) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(res["headings"])
    for r in res["rows"]:
        w.writerow(["" if v is None else str(v) for v in r])
    return buf.getvalue()


class _GetFromSam(QFrame):
    """'Get this list from SAM' strip shown above each table: copy / view the query, import its CSV."""

    def __init__(self, dlg, key: str, helper: dict | None):
        super().__init__()
        self.dlg, self.key, self.helper = dlg, key, helper
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        if not helper:
            lay.addWidget(label("Type or paste this list."))
            return
        lay.addWidget(label(
            f"<b>Get this list from SAM:</b> 1. <b>Copy query</b> 2. in SAM open <i>Ad Hoc Query &gt; Query</i>, "
            f"paste and <i>Run Query</i> 3. save the results as <b>{helper['file']}</b> 4. <b>Import this list</b>."))
        row = QHBoxLayout()
        b = QPushButton("Copy query")
        b.setObjectName("primary")
        b.clicked.connect(self.copy)
        row.addWidget(b)
        self.view_btn = QPushButton("Show query")
        self.view_btn.setCheckable(True)
        self.view_btn.toggled.connect(self.toggle)
        row.addWidget(self.view_btn)
        b = QPushButton("Import this list...")
        b.clicked.connect(lambda: dlg.import_one(key))
        row.addWidget(b)
        if dlg.samdb_on:
            b = QPushButton("Load from SAM")
            b.setToolTip("Runs the query through the read-only SAM connection")
            b.clicked.connect(lambda: dlg.load_from_sam([key]))
            row.addWidget(b)
        self.status = QLabel("")
        row.addWidget(self.status)
        row.addStretch()
        lay.addLayout(row)
        self.sql = QPlainTextEdit(helper["sql"])
        self.sql.setReadOnly(True)
        self.sql.setMaximumHeight(150)
        self.sql.setVisible(False)
        lay.addWidget(self.sql)

    def copy(self):
        QApplication.clipboard().setText(self.helper["sql"])
        self.status.setText(f"Copied - save the SAM results as {self.helper['file']}")

    def toggle(self, on):
        self.sql.setVisible(on)
        self.view_btn.setText("Hide query" if on else "Show query")


class CodesDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SAM Codes & Schools")
        self.resize(960, 700)
        self.settings = settings
        lay = QVBoxLayout(self)
        from .. import samdb
        self.samdb_on = samdb.enabled(settings)
        try:
            self.helpers = C.helper_queries(settings)
        except Exception:
            self.helpers = {}
        lay.addWidget(label("Add your schools (with the SchoolID SAM uses) and load your real code lists. Schools "
                            "become one-click filters, codes become drop-downs in filters, and the Query Assistant "
                            "uses them.", "subtitle"))
        quick = QFrame()
        quick.setObjectName("infobar")
        ql = QVBoxLayout(quick)
        ql.setContentsMargins(10, 8, 10, 8)
        ql.addWidget(label(
            "<b>Fastest - everything with one query:</b> 1. <b>Copy the all-in-one query</b> 2. in SAM open "
            "<i>Ad Hoc Query &gt; Query</i>, paste and <i>Run Query</i> 3. save the results as "
            f"<b>{C.ALL_IN_ONE_FILE}</b> 4. <b>Import CSV files</b>. If SAM shows an error, use the separate query "
            "on each list instead."))
        qr = QHBoxLayout()
        b = QPushButton("Copy the all-in-one query")
        b.setObjectName("primary")
        b.clicked.connect(self.copy_all)
        qr.addWidget(b)
        b = QPushButton("Save all queries to a folder...")
        b.clicked.connect(self.save_all)
        qr.addWidget(b)
        if self.samdb_on:
            b = QPushButton("Load everything from SAM")
            b.setToolTip("Runs the all-in-one query through the read-only SAM connection")
            b.clicked.connect(lambda: self.load_from_sam(None))
            qr.addWidget(b)
        self.quick_status = QLabel("")
        qr.addWidget(self.quick_status)
        qr.addStretch()
        ql.addLayout(qr)
        lay.addWidget(quick)
        body = QHBoxLayout()
        self.nav = QListWidget()
        self.nav.setFixedWidth(300)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.stack = QStackedWidget()
        self.pages = {}
        self.nav.addItem("Schools")
        self.pages["schools"] = _Table(["SchoolID", "School name", "School code", "Short name"],
                                       settings.get("schools", []), ["id", "name", "code", "short"])
        self.stack.addWidget(self._page("schools"))
        for key, (lbl, _t) in C.CODE_SETS.items():
            self.nav.addItem(lbl)
            extra = C.EXTRA_COLUMNS.get(key, [])
            self.pages[key] = _Table(["Code", "Description"] + [h for _k, h in extra],
                                     settings.get("codes", {}).get(key, []),
                                     ["code", "description"] + [k for k, _h in extra])
            self.stack.addWidget(self._page(key))
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
        row.addWidget(QLabel("<i>Tip: select the all-in-one CSV, or all the separate CSVs at once.</i>"))
        row.addStretch()
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _page(self, key):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(_GetFromSam(self, key, self.helpers.get(key)))
        v.addWidget(self.pages[key], 1)
        return w

    def _name(self, key):
        return "Schools" if key == "schools" else C.CODE_SETS[key][0]

    def copy_all(self):
        QApplication.clipboard().setText(C.all_in_one_sql())
        self.quick_status.setText(f"Copied - save the SAM results as {C.ALL_IN_ONE_FILE}")

    def save_all(self):
        folder = QFileDialog.getExistingDirectory(self, "Folder for the SAM code queries", str(Path.home()))
        if not folder:
            return
        files = C.save_helper_queries(self.settings, folder)
        QMessageBox.information(self, "Queries saved", f"Saved {len(files)} files to\n{files[0].parent}\n\n"
                                "Open 'READ ME.txt' for the file name to use for each result.")

    def _apply(self, key, data):
        if key == "owner_type":
            self._owner_tables = data
        self.pages[key].set_rows(data)

    def _apply_all_in_one(self, src) -> list[str]:
        done = []
        for key, data in C.parse_all_in_one(src).items():
            self._apply(key, data)
            done.append(f"{self._name(key)} ({len(data)})")
        return done

    def import_one(self, key):
        f, _ = QFileDialog.getOpenFileName(self, f"Import {self._name(key)}", str(Path.home()),
                                           "CSV / text (*.csv *.txt);;All files (*)")
        if not f:
            return
        rows = C._read_csv(f)
        if C.is_all_in_one(rows):
            done = self._apply_all_in_one(f)
            self._counts()
            QMessageBox.information(self, "Import", "That was the all-in-one file. Loaded:\n- " + "\n- ".join(done))
            return
        data = C.parse_schools(f) if key == "schools" else C.parse_codes(f)
        if not data:
            QMessageBox.warning(self, "Import", f"No rows found in {Path(f).name}. Expected columns: "
                                + ("SchoolID, School Name" if key == "schools" else "Code, Description") + ".")
            return
        self._apply(key, data)
        self._counts()

    def load_from_sam(self, keys):
        """keys=None runs the all-in-one query; otherwise the separate query for each key."""
        from .. import samdb
        QApplication.setOverrideCursor(Qt.WaitCursor)
        done, failed = [], []
        try:
            if keys is None:
                try:
                    res = samdb.run(self.settings, C.all_in_one_sql(header=False), max_rows=20000, count=False)
                    done = self._apply_all_in_one(_csv_text(res))
                except Exception as e:  # e.g. a code table this SAM doesn't have - fall back to one query per list
                    failed.append(f"All-in-one query: {e} - trying each list separately")
                    keys = list(self.helpers)
            for key in keys or []:
                try:
                    res = samdb.run(self.settings, self.helpers[key]["sql"], max_rows=20000, count=False)
                    text = _csv_text(res)
                    data = C.parse_schools(text) if key == "schools" else C.parse_codes(text)
                    self._apply(key, data)
                    done.append(f"{self._name(key)} ({len(data)})")
                except Exception as e:
                    failed.append(f"{self._name(key)}: {e}")
        finally:
            QApplication.restoreOverrideCursor()
        self._counts()
        QMessageBox.information(self, "Load from SAM", ("Loaded:\n- " + "\n- ".join(done) if done else "Nothing loaded.")
                                + ("\n\nProblems:\n- " + "\n- ".join(failed) if failed else ""))

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
            if C.is_all_in_one(rows):
                got = self._apply_all_in_one(f)
                done += [f"{Path(f).name} -> {g}" for g in got] or []
                if not got:
                    skipped.append(Path(f).name)
                continue
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
            self._apply(target, data)
            done.append(f"{Path(f).name} -> {self._name(target)} ({len(data)})")
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
