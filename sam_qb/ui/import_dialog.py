"""File > Import SQL - turn an existing query back into editable steps."""
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
                               QPlainTextEdit, QPushButton, QVBoxLayout)

from ..sql_import import import_sql
from .widgets import SqlHighlighter, label


class ImportSqlDialog(QDialog):
    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.result = None
        self.setWindowTitle("Import existing SQL")
        self.resize(900, 640)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Paste a query you already use in SAM (Ad Hoc Query > Query Maintenance, or a CAC Agent "
                            "query) and the builder turns it back into steps you can edit. Anything it can't show as "
                            "a step is kept exactly as written.", "subtitle"))
        self.text = QPlainTextEdit()
        self.text.setObjectName("sql")
        self.text.setPlaceholderText("SELECT s.StudentCode, s.LastName, s.FirstName FROM Student s WHERE ...")
        SqlHighlighter(self.text.document())
        lay.addWidget(self.text, 2)
        row = QHBoxLayout()
        fb = QPushButton("Open .sql file...")
        fb.clicked.connect(self._file)
        row.addWidget(fb)
        tb = QPushButton("Check")
        tb.clicked.connect(self._check)
        row.addWidget(tb)
        row.addStretch()
        lay.addLayout(row)
        lay.addWidget(QLabel("<b>Notes</b>"))
        self.notes = QListWidget()
        lay.addWidget(self.notes, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Open in the builder")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _file(self):
        p, _ = QFileDialog.getOpenFileName(self, "Open SQL", "", "SQL (*.sql *.txt);;All files (*)")
        if p:
            with open(p, encoding="utf-8-sig", errors="replace") as fh:
                self.text.setPlainText(fh.read())
            self._check()

    def _check(self):
        q, notes = import_sql(self.text.toPlainText(), self.catalog)
        self.notes.clear()
        self.notes.addItem(f"{len(q.tables)} table(s), {len(q.links)} link(s), {len(q.columns)} column(s), "
                           f"{sum(len(g.conditions) for g in q.filters)} filter(s)"
                           + (f", {len(q.union_parts)} combined part(s)" if q.union_parts else ""))
        for n in notes or ["Everything was converted into steps."]:
            self.notes.addItem("- " + n)
        self.result = q
        return q

    def _accept(self):
        if not self.text.toPlainText().strip():
            return
        self._check()
        self.accept()
