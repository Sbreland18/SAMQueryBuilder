"""Upload alerts settings (email + Teams / Google Chat / Slack webhook)."""
from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLineEdit, QMessageBox,
                               QPushButton, QSpinBox, QVBoxLayout)

from .. import alerts, paths, uploader
from .widgets import label


class AlertsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Upload alerts")
        self.resize(620, 560)
        self.settings = settings
        a = alerts.get(settings)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Scheduled uploads run with no window, so turn on an alert to hear about failures and "
                            "uploads held by the safety net. Alerts come from the PC that runs the schedule.",
                            "subtitle"))
        self.when = QComboBox()
        for k, t in (("failure", "When an upload fails or is held"), ("always", "After every upload"),
                     ("never", "Never")):
            self.when.addItem(t, k)
        self.when.setCurrentIndex(max(0, self.when.findData(a["notify_on"])))
        f0 = QFormLayout()
        f0.addRow("Send an alert:", self.when)
        lay.addLayout(f0)

        g = QGroupBox("Email")
        f = QFormLayout(g)
        self.to = QLineEdit(a["email_to"])
        self.to.setPlaceholderText("tech@district.org, data@district.org")
        f.addRow("Send to:", self.to)
        self.frm = QLineEdit(a["email_from"])
        f.addRow("From:", self.frm)
        self.host = QLineEdit(a["smtp_host"])
        self.host.setPlaceholderText("smtp.office365.com, smtp-relay.gmail.com or your relay")
        f.addRow("SMTP server:", self.host)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(a["smtp_port"] or 587))
        f.addRow("Port:", self.port)
        self.sec = QComboBox()
        for k, t in (("starttls", "STARTTLS (587)"), ("ssl", "SSL/TLS (465)"), ("none", "None (internal relay, 25)")):
            self.sec.addItem(t, k)
        self.sec.setCurrentIndex(max(0, self.sec.findData(a["smtp_security"])))
        f.addRow("Security:", self.sec)
        self.user = QLineEdit(a["smtp_user"])
        self.user.setPlaceholderText("leave blank for a relay that doesn't need a login")
        f.addRow("User name:", self.user)
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText("(saved)" if a["smtp_password"] else "")
        f.addRow("Password / app password:", self.pw)
        lay.addWidget(g)

        g2 = QGroupBox("Chat webhook")
        f2 = QFormLayout(g2)
        self.hook = QLineEdit(a["webhook_url"])
        self.hook.setPlaceholderText("Teams Workflows 'post to a channel when a webhook request is received' URL, "
                                     "or a Google Chat / Slack webhook")
        f2.addRow("Webhook URL:", self.hook)
        lay.addWidget(g2)

        tb = QPushButton("Send a test alert")
        tb.clicked.connect(self._test)
        lay.addWidget(tb)
        lay.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _collect(self):
        a = alerts.get(self.settings)
        a.update(notify_on=self.when.currentData(), email_to=self.to.text().strip(), email_from=self.frm.text().strip(),
                 smtp_host=self.host.text().strip(), smtp_port=self.port.value(), smtp_security=self.sec.currentData(),
                 smtp_user=self.user.text().strip(), webhook_url=self.hook.text().strip())
        if self.pw.text():
            a["smtp_password"] = uploader.protect(self.pw.text())
        return a

    def _test(self):
        trial = dict(self.settings)
        trial["alerts"] = self._collect()
        try:
            QMessageBox.information(self, "Test alert", alerts.send_test(trial))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Test alert", f"Could not send:\n{e}")

    def _save(self):
        self.settings["alerts"] = self._collect()
        paths.save_settings(self.settings)
        self.accept()
