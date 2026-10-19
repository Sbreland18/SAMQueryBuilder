"""Vendor template builder window - make an export package from any vendor's file layout."""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QVBoxLayout, QWidget)

from .. import template_builder as tb
from .widgets import label


class TemplateBuilderDialog(QDialog):
    saved = Signal(str)       # package id

    def __init__(self, catalog, get_settings, platform: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vendor template builder")
        self.resize(1250, 820)
        self.catalog = catalog
        self.get_settings = get_settings
        self.pkg = self._from_platform(platform) if platform else {"id": "", "name": "", "works_with": "",
                                                                   "delivery": "", "files": []}
        lay = QVBoxLayout(self)
        lay.addWidget(label("Make an export package from any vendor's layout: open the vendor's template (or paste its "
                            "header row), check the SAM field suggested for each column, preview it with sample data "
                            "and save. Your package then works like the built-in ones - checker, Save package, CAC "
                            "Agent walkthrough, uploads and school limits.", "subtitle"))
        top = QFormLayout()
        self.name = QLineEdit(self.pkg["name"])
        self.name.setPlaceholderText("Vendor / package name, e.g. 'Acme Reading'")
        top.addRow("Package name:", self.name)
        self.works = QLineEdit(self.pkg.get("works_with", ""))
        self.works.setPlaceholderText("What it's for (optional)")
        top.addRow("Works with:", self.works)
        self.delivery = QLineEdit(self.pkg.get("delivery", ""))
        self.delivery.setPlaceholderText("How the vendor receives files, e.g. SFTP to sftp.vendor.com")
        top.addRow("Deliver by:", self.delivery)
        lay.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("<b>Files in this package</b>"))
        self.files = QListWidget()
        self.files.currentRowChanged.connect(self._load_file)
        ll.addWidget(self.files, 1)
        for txt, fn in (("Add file...", self._add_file), ("Rename file...", self._rename_file),
                        ("Remove file", self._remove_file)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            ll.addWidget(b)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        g = QGroupBox("1. The vendor's layout")
        gl = QVBoxLayout(g)
        row = QHBoxLayout()
        row.addWidget(QLabel("One row is:"))
        self.base = QComboBox()
        for k, (lab, _f) in tb.BASES.items():
            self.base.addItem(lab, k)
        self.base.currentIndexChanged.connect(self._base_changed)
        row.addWidget(self.base, 1)
        ob = QPushButton("Open vendor template...")
        ob.clicked.connect(self._open_template)
        row.addWidget(ob)
        gl.addLayout(row)
        self.paste = QPlainTextEdit()
        self.paste.setPlaceholderText("...or paste the vendor's header row here (comma, tab or pipe separated), "
                                      "optionally with a sample row under it, then click Read columns")
        self.paste.setMaximumHeight(64)
        gl.addWidget(self.paste)
        rb = QPushButton("Read columns && suggest fields")
        rb.clicked.connect(self._read_paste)
        gl.addWidget(rb)
        rl.addWidget(g)
        g2 = QGroupBox("2. Match each vendor column to SAM")
        g2l = QVBoxLayout(g2)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Vendor column", "SAM field", "Fixed text", "Required", "Unique key",
                                              "Sample from vendor"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(2, 130)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        g2l.addWidget(self.table, 1)
        mr = QHBoxLayout()
        for txt, fn in (("Add column", self._add_col), ("Remove column", self._del_col), ("Move up", lambda: self._move(-1)),
                        ("Move down", lambda: self._move(1)), ("Suggest again", self._resuggest)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            mr.addWidget(b)
        mr.addStretch()
        g2l.addLayout(mr)
        g2l.addWidget(label("Green = confident match, orange = please check, red = not matched (left blank). Fields "
                            "only appear when they fit what one row is.", "hint"))
        rl.addWidget(g2, 1)
        from .sample_view import SampleResults
        g3 = QGroupBox("3. Preview with sample data")
        g3l = QVBoxLayout(g3)
        self.sample = SampleResults()
        g3l.addWidget(self.sample)
        pv = QPushButton("Refresh preview")
        pv.clicked.connect(self._preview)
        g3l.addWidget(pv)
        rl.addWidget(g3, 1)
        split.addWidget(right)
        split.setSizes([230, 1000])
        lay.addWidget(split, 1)

        br = QHBoxLayout()
        sv = QPushButton("Save package")
        sv.setObjectName("primary")
        sv.clicked.connect(self._save)
        br.addWidget(sv)
        ex = QPushButton("Share: export package file...")
        ex.clicked.connect(self._export)
        br.addWidget(ex)
        br.addStretch()
        cl = QPushButton("Close")
        cl.clicked.connect(self.accept)
        br.addWidget(cl)
        lay.addLayout(br)
        self._samples: dict[str, list] = {}
        self._cur_index = -1
        self._fill_files()
        if not self.pkg["files"]:
            self._add_file(default="export.csv")

    # ------------------------------------------------------------------ package <-> UI
    @staticmethod
    def _from_platform(p):
        return {"id": p["id"], "name": p["name"], "works_with": p.get("works_with", ""),
                "delivery": p.get("delivery", ""), "description": p.get("description", ""),
                "files": [{"file": fe["file"], "base": fe.get("base", "students"),
                           "mapping": copy.deepcopy(fe.get("mapping", [])), "note": fe.get("note", "")}
                          for fe in p["files"]]}

    def _fill_files(self, select=0):
        self.files.blockSignals(True)
        self.files.clear()
        for fe in self.pkg["files"]:
            self.files.addItem(fe["file"])
        self.files.blockSignals(False)
        self._cur_index = -1
        if self.pkg["files"]:
            self.files.setCurrentRow(min(select, len(self.pkg["files"]) - 1))

    def _cur(self):
        r = self.files.currentRow()
        return self.pkg["files"][r] if 0 <= r < len(self.pkg["files"]) else None

    def _load_file(self, r):
        if 0 <= self._cur_index < len(self.pkg["files"]):
            self._collect(self.pkg["files"][self._cur_index])
        self._cur_index = r
        fe = self._cur()
        if not fe:
            return
        self.base.blockSignals(True)
        self.base.setCurrentIndex(max(0, self.base.findData(fe.get("base", "students"))))
        self.base.blockSignals(False)
        self._fill_table(fe["mapping"])
        self._preview()

    def _fill_table(self, mapping):
        base = self.base.currentData()
        self.table.setRowCount(0)
        for m in mapping:
            self._insert_row(self.table.rowCount(), m, base)

    def _insert_row(self, r, m, base):
        from PySide6.QtWidgets import QTableWidgetItem
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(m["heading"]))
        cb = QComboBox()
        cb.addItem(tb.SPECIAL["__blank__"], "__blank__")
        cb.addItem(tb.SPECIAL["__text__"], "__text__")
        last_group = None
        for f in tb.fields_for(base):
            if f.group != last_group:
                cb.insertSeparator(cb.count())
                last_group = f.group
            cb.addItem(f"{f.group}: {f.label}", f.key)
        cb.setCurrentIndex(max(0, cb.findData(m.get("field", "__blank__"))))
        conf = m.get("confidence")
        if conf is not None:
            color = "#1E7B34" if conf >= 0.92 else ("#C2410C" if conf >= 0.72 else "#B42318")
            cb.setStyleSheet(f"QComboBox {{ border: 2px solid {color}; }}")
        self.table.setCellWidget(r, 1, cb)
        tx = QLineEdit(m.get("text", ""))
        tx.setPlaceholderText("value for Fixed text")
        self.table.setCellWidget(r, 2, tx)
        for c, key in ((3, "required"), (4, "unique")):
            chk = QCheckBox()
            chk.setChecked(bool(m.get(key)))
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(8, 0, 0, 0)
            hl.addWidget(chk)
            self.table.setCellWidget(r, c, w)
        smp = QTableWidgetItem(", ".join(dict.fromkeys(self._samples.get(m["heading"], []))) if self._samples else "")
        smp.setForeground(QColor("#4A5568"))
        self.table.setItem(r, 5, smp)

    def _row_mapping(self, r) -> dict:
        def chk(c):
            return self.table.cellWidget(r, c).findChild(QCheckBox).isChecked()
        it = self.table.item(r, 0)
        return {"heading": (it.text() if it else "").strip(), "field": self.table.cellWidget(r, 1).currentData(),
                "text": self.table.cellWidget(r, 2).text(), "required": chk(3), "unique": chk(4)}

    def _collect(self, fe):
        fe["base"] = self.base.currentData()
        fe["mapping"] = [self._row_mapping(r) for r in range(self.table.rowCount()) if self._row_mapping(r)["heading"]]

    # ------------------------------------------------------------------ actions
    def _base_changed(self, _i):
        fe = self._cur()
        if not fe:
            return
        self._collect(fe)
        self._resuggest()

    def _apply_headers(self, heads, samples):
        fe = self._cur()
        if not fe or not heads:
            return
        self._samples = {h: [r[i] for r in samples if i < len(r) and r[i].strip()][:3] for i, h in enumerate(heads)}
        base = tb.suggest_base(heads)
        self.base.blockSignals(True)
        self.base.setCurrentIndex(max(0, self.base.findData(base)))
        self.base.blockSignals(False)
        fe["base"] = base
        fe["mapping"] = tb.auto_map(heads, base, samples)
        fe["suggested"] = {m["heading"]: m["field"] for m in fe["mapping"]}
        self._fill_table(fe["mapping"])
        self._preview()
        n = sum(1 for m in fe["mapping"] if m["field"] != "__blank__")
        QMessageBox.information(self, "Columns read", f"{len(heads)} columns read, {n} matched to SAM fields. "
                                f"One row looks like: {tb.BASES[base][0]}.\n\nCheck the orange and red ones.")

    def _open_template(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Vendor template or sample file", "",
                                            "CSV / text (*.csv *.txt *.tsv);;All files (*)")
        if not fn:
            return
        try:
            heads, samples = tb.read_template(path=fn)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Open template", str(e))
            return
        fe = self._cur()
        if fe and fe["file"] in ("export.csv", "") and fn:
            from pathlib import Path
            fe["file"] = Path(fn).name if Path(fn).suffix.lower() in (".csv", ".txt") else Path(fn).stem + ".csv"
            self.files.currentItem().setText(fe["file"])
        self._apply_headers(heads, samples)

    def _read_paste(self):
        heads, samples = tb.read_template(self.paste.toPlainText())
        self._apply_headers(heads, samples)

    def _resuggest(self):
        fe = self._cur()
        if not fe:
            return
        self._collect(fe)
        heads = [m["heading"] for m in fe["mapping"]]
        samples = [[(self._samples.get(h) or [""])[0] for h in heads]] if self._samples else []
        keep = {m["heading"]: m for m in fe["mapping"]}
        fe["mapping"] = tb.auto_map(heads, fe["base"], samples)
        for m in fe["mapping"]:
            old = keep.get(m["heading"], {})
            m["required"] = old.get("required", m["required"])
            m["unique"] = old.get("unique", m["unique"])
        self._fill_table(fe["mapping"])
        self._preview()

    def _add_col(self):
        name, ok = QInputDialog.getText(self, "Add column", "Vendor column heading:")
        if ok and name.strip():
            self._insert_row(self.table.rowCount(), {"heading": name.strip(), "field": "__blank__"},
                             self.base.currentData())

    def _del_col(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def _move(self, d):
        r = self.table.currentRow()
        fe = self._cur()
        if not fe or r < 0 or not (0 <= r + d < self.table.rowCount()):
            return
        self._collect(fe)
        fe["mapping"][r], fe["mapping"][r + d] = fe["mapping"][r + d], fe["mapping"][r]
        self._fill_table(fe["mapping"])
        self.table.selectRow(r + d)

    def _add_file(self, _=False, default=None):
        name = default
        if not name:
            name, ok = QInputDialog.getText(self, "Add file", "File name the vendor expects:", text="students.csv")
            if not ok or not name.strip():
                return
        if self.pkg["files"] and self._cur():
            self._collect(self._cur())
        self.pkg["files"].append({"file": name.strip(), "base": "students", "mapping": []})
        self._fill_files(len(self.pkg["files"]) - 1)

    def _rename_file(self):
        fe = self._cur()
        if not fe:
            return
        name, ok = QInputDialog.getText(self, "Rename file", "File name:", text=fe["file"])
        if ok and name.strip():
            fe["file"] = name.strip()
            self.files.currentItem().setText(fe["file"])

    def _remove_file(self):
        r = self.files.currentRow()
        if r >= 0 and len(self.pkg["files"]) > 1:
            self.pkg["files"].pop(r)
            self._fill_files(max(0, r - 1))

    def _preview(self):
        fe = self._cur()
        if not fe:
            return
        self._collect(fe)
        if not fe["mapping"]:
            self.sample._error("Open the vendor's template or paste its header row to start.")
            return
        from ..district import expand
        qd = tb.build_query_dict(fe["base"], fe["mapping"], fe["file"])
        self.sample.show_query(expand(qd, self.get_settings()), self.catalog)

    def _package(self):
        fe = self._cur()
        if fe:
            self._collect(fe)
        name = self.name.text().strip()
        if not name:
            raise ValueError("Give the package a name.")
        if not any(m for f in self.pkg["files"] for m in f["mapping"]):
            raise ValueError("Add the vendor's columns first.")
        dupes = [f["file"] for f in self.pkg["files"] if [f2["file"] for f2 in self.pkg["files"]].count(f["file"]) > 1]
        if dupes:
            raise ValueError(f"Two files are named {dupes[0]}.")
        self.pkg.update(name=name, works_with=self.works.text().strip(), delivery=self.delivery.text().strip())
        if not self.pkg.get("id"):
            from ..exports import load_platforms
            ids = {p["id"] for p in load_platforms()}
            pid, n = tb.slug(name), 2
            while pid in ids:
                pid, n = f"{tb.slug(name)}-{n}", n + 1
            self.pkg["id"] = pid
        return tb.make_package(self.pkg)

    def _save(self):
        try:
            plat = self._package()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Save package", str(e))
            return
        tb.save_custom(plat)
        learned = sum(tb.learn(fe["base"], fe["mapping"], fe.get("suggested")) for fe in self.pkg["files"])
        self.saved.emit(plat["id"])
        if learned:
            self.setWindowTitle(f"Vendor template builder - remembered {learned} correction(s) for next time")
        QMessageBox.information(self, "Package saved", f"'{plat['name']}' is saved under My packages on the "
                                "Export to a platform page.")

    def _export(self):
        try:
            plat = self._package()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Export package", str(e))
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Export package file", f"{plat['name']}.samqb-package",
                                            "Package files (*.samqb-package)")
        if fn:
            tb.export_package(plat, fn)
            QMessageBox.information(self, "Export package", "Saved. Another district can load it with "
                                    "Export to a platform > Import package file.")
