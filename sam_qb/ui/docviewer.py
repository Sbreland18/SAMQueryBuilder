"""Shows the guides in docs/ (bundled with the app) inside a window."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QMessageBox, QPushButton, QTextBrowser,
                               QVBoxLayout)

from .. import paths


def show_doc(parent, name: str):
    p = paths.resource_dir() / "docs" / name
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        QMessageBox.information(parent, "Guide", f"{name} was not found.")
        return
    d = QDialog(parent)
    d.setWindowTitle(name.rsplit(".", 1)[0])
    d.resize(900, 780)
    lay = QVBoxLayout(d)
    tb = QTextBrowser()
    tb.setOpenExternalLinks(True)
    tb.setMarkdown(text)
    lay.addWidget(tb)
    row = QHBoxLayout()
    sv = QPushButton("Save a copy...")

    def save():
        fn, _ = QFileDialog.getSaveFileName(d, "Save a copy", p.name, "Markdown (*.md);;Text (*.txt)")
        if fn:
            Path(fn).write_text(text, encoding="utf-8")
    sv.clicked.connect(save)
    row.addWidget(sv)
    row.addStretch()
    cl = QPushButton("Close")
    cl.clicked.connect(d.accept)
    row.addWidget(cl)
    lay.addLayout(row)
    d.exec()
