"""Shows an export check report."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout)

from ..validator import Report

COLORS = {"error": "#B42318", "warning": "#9A6700", "info": "#1E7B34"}


class CheckDialog(QDialog):
    def __init__(self, report: Report, parent=None):
        super().__init__(parent)
        self.report = report
        self.setWindowTitle(f"Export check - {report.platform}")
        self.resize(920, 600)
        lay = QVBoxLayout(self)
        ok = report.ok
        head = QLabel(f"<span style='font-size:15pt;font-weight:600;color:{'#1E7B34' if ok else '#B42318'}'>"
                      f"{'Ready to upload' if ok else 'Fix these before uploading'}</span><br>"
                      f"{len(report.errors)} error(s), {len(report.warnings)} warning(s) in {report.folder}")
        lay.addWidget(head)
        files = "  |  ".join(f"{f}: {'MISSING' if n is None else f'{n} rows'}" for f, n in report.files.items())
        fl = QLabel(files)
        fl.setWordWrap(True)
        fl.setObjectName("hint")
        lay.addWidget(fl)
        tree = QTreeWidget()
        tree.setHeaderLabels(["File", "Problem", "Rows (first data row = 1)", "Count"])
        tree.setColumnWidth(0, 190)
        tree.setColumnWidth(1, 470)
        by_file = {}
        for i in report.issues:
            parent_item = by_file.get(i.file)
            if parent_item is None:
                parent_item = QTreeWidgetItem([i.file, "", "", ""])
                f = parent_item.font(0)
                f.setBold(True)
                parent_item.setFont(0, f)
                tree.addTopLevelItem(parent_item)
                parent_item.setExpanded(True)
                by_file[i.file] = parent_item
            it = QTreeWidgetItem([i.level.upper(), i.message, ", ".join(map(str, i.rows[:12])) +
                                  ("..." if len(i.rows) > 12 else ""), str(i.count)])
            it.setForeground(0, QColor(COLORS.get(i.level, "#1B2A41")))
            it.setToolTip(1, i.message)
            parent_item.addChild(it)
        lay.addWidget(tree, 1)
        tips = QLabel("<i>Most problems come from the data in SAM (blank names, duplicate IDs, students in sections "
                      "whose teacher isn't in the teacher file). Fix the record in SAM or adjust the query's filters, "
                      "then run the export again.</i>")
        tips.setWordWrap(True)
        lay.addWidget(tips)
        row = QHBoxLayout()
        save = QPushButton("Save report...")
        save.clicked.connect(self.save)
        row.addWidget(save)
        row.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        lay.addLayout(row)

    def save(self):
        p, _ = QFileDialog.getSaveFileName(self, "Save report", "export_check.txt", "Text (*.txt)")
        if p:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(self.report.text())
