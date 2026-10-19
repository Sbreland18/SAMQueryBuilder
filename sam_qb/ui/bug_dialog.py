"""Help > Report a bug."""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout)

from .. import bugreport
from ..app_config import APP_NAME, GITHUB_REPO, SUPPORT_EMAIL
from .widgets import label


class BugReportDialog(QDialog):
    def __init__(self, settings: dict, parent=None, summary: str = "", details: str = ""):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Report a bug")
        self.resize(760, 720)
        lay = QVBoxLayout(self)
        lay.addWidget(label(
            f"Tell us what went wrong in {APP_NAME}. You'll see the whole report before it's sent. "
            "<b>Don't include student names, IDs, screenshots of student data or passwords</b> - GitHub "
            "reports are public.", "subtitle"))
        f = QFormLayout()
        self.summary = QLineEdit(summary)
        self.summary.setPlaceholderText("One line, e.g. 'Check exported files says students.csv is missing'")
        f.addRow("Summary:", self.summary)
        self.details = QPlainTextEdit(details)
        self.details.setPlaceholderText("What happened, and what did you expect? Copy any error message here.")
        self.details.setMaximumHeight(130)
        f.addRow("What happened:", self.details)
        self.steps = QPlainTextEdit()
        self.steps.setPlaceholderText("1. Export to a platform > Clever\n2. Check exported files\n3. ...")
        self.steps.setMaximumHeight(100)
        f.addRow("Steps:", self.steps)
        self.contact = QLineEdit()
        self.contact.setPlaceholderText("optional - your name, district and email so we can reply")
        f.addRow("Your contact:", self.contact)
        lay.addLayout(f)
        self.inc = QCheckBox("Include diagnostic details (app and data version, Windows version, upload results, "
                             "recent errors - you can edit them below)")
        self.inc.setChecked(True)
        lay.addWidget(self.inc)
        self.diag = QPlainTextEdit(bugreport.diagnostics(settings))
        self.diag.setMinimumHeight(150)
        self.inc.toggled.connect(self.diag.setEnabled)
        lay.addWidget(self.diag, 1)
        row = QHBoxLayout()
        b = QPushButton("Open on GitHub")
        b.setObjectName("primary")
        b.setToolTip(f"Opens a new issue on github.com/{GITHUB_REPO} with the report filled in (free GitHub "
                     "account needed)")
        b.clicked.connect(self.github)
        row.addWidget(b)
        self.email_btn = QPushButton("Send by email")
        self.email_btn.setEnabled(bool(SUPPORT_EMAIL))
        self.email_btn.setToolTip(f"Sends to {SUPPORT_EMAIL}" if SUPPORT_EMAIL else
                                  "No support email address is set in this version")
        self.email_btn.clicked.connect(self.email)
        row.addWidget(self.email_btn)
        for txt, fn in (("Copy report", self.copy), ("Save report...", self.save)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        b = QPushButton("Close")
        b.clicked.connect(self.reject)
        row.addWidget(b)
        lay.addLayout(row)
        self.status = QLabel("")
        lay.addWidget(self.status)

    def _report(self):
        if not self.summary.text().strip():
            QMessageBox.information(self, "Report a bug", "Add a one-line summary first.")
            self.summary.setFocus()
            return None
        return bugreport.compose(self.summary.text(), self.details.toPlainText(), self.steps.toPlainText(),
                                 self.contact.text(), self.diag.toPlainText() if self.inc.isChecked() else "")

    def github(self):
        r = self._report()
        if r:
            QApplication.clipboard().setText(r[1])
            QDesktopServices.openUrl(QUrl(bugreport.github_issue_url(*r)))
            self.status.setText("Opened GitHub in your browser - sign in and click 'Submit new issue'. The report is "
                                "also on your clipboard.")

    def email(self):
        r = self._report()
        if not r:
            return
        try:
            if bugreport.send_email(self.settings, *r):
                self.status.setText(f"Sent to {SUPPORT_EMAIL}. Thank you!")
                return
        except Exception as e:
            self.status.setText(f"Couldn't send with your alert email settings ({e}) - opening your mail program.")
        QApplication.clipboard().setText(r[1])
        QDesktopServices.openUrl(QUrl(bugreport.mailto_url(*r)))
        if not self.status.text():
            self.status.setText("Opened your mail program. If the message is cut short, paste the full report "
                                "(it's on your clipboard).")

    def copy(self):
        r = self._report()
        if r:
            QApplication.clipboard().setText(f"{r[0]}\n\n{r[1]}")
            self.status.setText("Report copied.")

    def save(self):
        r = self._report()
        if not r:
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Save bug report", "bug_report.txt", "Text (*.txt)")
        if fn:
            with open(fn, "w", encoding="utf-8") as fh:
                fh.write(f"{r[0]}\n\n{r[1]}\n")
            self.status.setText(f"Saved {fn}")
