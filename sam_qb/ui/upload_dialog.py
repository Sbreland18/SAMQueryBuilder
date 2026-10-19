"""Package & Upload profiles window."""
from __future__ import annotations

import copy
import sys

from PySide6.QtCore import QTime
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
                               QTimeEdit, QVBoxLayout, QWidget, QGroupBox)

from .. import paths, uploader
from ..exports import load_platforms
from .dialogs import TaskWorker
from .widgets import label


class UploadDialog(QDialog):
    def __init__(self, settings: dict, platform: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Package & Upload")
        self.resize(1040, 720)
        self.settings = settings
        self.platforms = [p for p in load_platforms() if p.get("kind") != "tool"]
        self.profiles = copy.deepcopy(settings.get("upload_profiles", []))
        self.worker = None
        lay = QVBoxLayout(self)
        lay.addWidget(label("Each profile takes the CSV files the CAC Agent saves in a folder, checks them, zips them "
                            "if the vendor wants a zip (OneRoster's manifest.csv is added for you), uploads them by "
                            "SFTP / FTPS (or copies them to a folder), keeps a dated archive and holds the upload if a file is "
                            "empty or shrinks a lot. Schedule it nightly after the CAC Agent jobs and turn on Alerts.",
                            "subtitle"))
        body = QHBoxLayout()
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._load)
        left.addWidget(self.list, 1)
        nb = QPushButton("New profile")
        nb.clicked.connect(lambda: self._new(None))
        left.addWidget(nb)
        db = QPushButton("Delete profile")
        db.clicked.connect(self._delete)
        left.addWidget(db)
        body.addLayout(left, 1)

        right = QVBoxLayout()
        g = QGroupBox("Profile")
        f = QFormLayout(g)
        self.name = QLineEdit()
        f.addRow("Name:", self.name)
        self.platform = QComboBox()
        self.platform.addItem("(any CSV files in the folder)", "")
        for p in self.platforms:
            self.platform.addItem(p["name"], p["id"])
        f.addRow("Package:", self.platform)
        fr = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("Folder the CAC Agent jobs save to, e.g. C:\\SAM Exports\\Clever")
        fb = QPushButton("Browse...")
        fb.clicked.connect(self._browse)
        fr.addWidget(self.folder, 1)
        fr.addWidget(fb)
        fw = QWidget()
        fw.setLayout(fr)
        f.addRow("Local folder:", fw)
        self.method = QComboBox()
        self.method.addItem("SFTP (most vendors)", "sftp")
        self.method.addItem("FTPS (FTP over TLS)", "ftps")
        self.method.addItem("Copy to a folder (network share, Google Drive / OneDrive synced folder)", "folder")
        self.method.currentIndexChanged.connect(self._method_changed)
        f.addRow("Send by:", self.method)
        dr = QHBoxLayout()
        self.dest = QLineEdit()
        self.dest.setPlaceholderText("e.g. \\\\server\\imports\\routing   or   G:\\My Drive\\Vendor uploads")
        db_ = QPushButton("Browse...")
        db_.clicked.connect(lambda: self._pick_dir(self.dest))
        dr.addWidget(self.dest, 1)
        dr.addWidget(db_)
        self.dest_w = QWidget()
        self.dest_w.setLayout(dr)
        f.addRow("Destination folder:", self.dest_w)
        self.host = QLineEdit()
        self.host.setPlaceholderText("e.g. sftp.clever.com")
        f.addRow("Host:", self.host)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(22)
        f.addRow("Port:", self.port)
        self.user = QLineEdit()
        f.addRow("Username:", self.user)
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText("(unchanged)")
        f.addRow("Password:", self.pw)
        kr = QHBoxLayout()
        self.key = QLineEdit()
        self.key.setPlaceholderText("optional - private key file for vendors that use SSH keys")
        kb = QPushButton("Browse...")
        kb.clicked.connect(self._pick_key)
        self.key_pw = QLineEdit()
        self.key_pw.setEchoMode(QLineEdit.Password)
        self.key_pw.setPlaceholderText("key passphrase")
        self.key_pw.setMaximumWidth(150)
        kr.addWidget(self.key, 1)
        kr.addWidget(kb)
        kr.addWidget(self.key_pw)
        self.key_w = QWidget()
        self.key_w.setLayout(kr)
        f.addRow("SSH key:", self.key_w)
        self.remote = QLineEdit("/")
        f.addRow("Remote folder:", self.remote)
        zr = QHBoxLayout()
        self.zip = QCheckBox("Zip the files as")
        self.zip_name = QLineEdit()
        self.zip_name.setPlaceholderText("oneroster.zip")
        zr.addWidget(self.zip)
        zr.addWidget(self.zip_name, 1)
        zw = QWidget()
        zw.setLayout(zr)
        f.addRow("", zw)
        pg = QHBoxLayout()
        self.pgp = QLineEdit()
        self.pgp.setPlaceholderText("optional - vendor's PGP PUBLIC key (.asc) if they require encrypted files")
        pgb = QPushButton("Browse...")
        pgb.clicked.connect(self._pick_pgp)
        self.pgp_armor = QCheckBox("ASCII armor (.asc)")
        pg.addWidget(self.pgp, 1)
        pg.addWidget(pgb)
        pg.addWidget(self.pgp_armor)
        pgw = QWidget()
        pgw.setLayout(pg)
        f.addRow("PGP encrypt:", pgw)
        self.check = QCheckBox("Check the files first (export file checker)")
        self.block = QCheckBox("Don't upload if the check finds errors")
        self.archive = QCheckBox("Keep a dated copy in an 'archive' subfolder")
        for w in (self.check, self.block, self.archive):
            f.addRow("", w)
        gr = QHBoxLayout()
        self.guard = QCheckBox("Safety net: hold the upload if a file is empty or has more than")
        self.guard_pct = QSpinBox()
        self.guard_pct.setRange(1, 90)
        self.guard_pct.setSuffix(" %")
        gr.addWidget(self.guard)
        gr.addWidget(self.guard_pct)
        gr.addWidget(QLabel("fewer rows than the last good upload"))
        gr.addStretch()
        gw = QWidget()
        gw.setLayout(gr)
        f.addRow("", gw)
        tr = QHBoxLayout()
        self.time = QTimeEdit()
        self.time.setDisplayFormat("HH:mm")
        tr.addWidget(QLabel("Run daily at"))
        tr.addWidget(self.time)
        sch = QPushButton("Schedule in Windows")
        sch.clicked.connect(self._schedule)
        tr.addWidget(sch)
        uns = QPushButton("Remove schedule")
        uns.clicked.connect(self._unschedule)
        tr.addWidget(uns)
        tr.addStretch()
        tw = QWidget()
        tw.setLayout(tr)
        f.addRow("Schedule:", tw)
        right.addWidget(g)
        br = QHBoxLayout()
        for txt, fn, primary in (("Save profile", self._save_current, False), ("Test connection", self._test, False),
                                 ("Check files", self._check_only, False), ("Run now", self._run, True),
                                 ("Upload anyway once", self._override, False), ("What changed?", self._changes, False),
                                 ("History", self._history, False),
                                 ("Alerts...", self._alerts, False)):
            b = QPushButton(txt)
            if primary:
                b.setObjectName("primary")
            b.clicked.connect(fn)
            br.addWidget(b)
        br.addStretch()
        right.addLayout(br)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        right.addWidget(self.log, 1)
        right.addWidget(label("Passwords are encrypted for this Windows user. Logs: "
                              f"{paths.user_dir() / 'upload_logs'}", "hint"))
        body.addLayout(right, 3)
        lay.addLayout(body, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close)
        self._fill()
        if platform:
            existing = next((i for i, p in enumerate(self.profiles) if p.get("platform_id") == platform["id"]), None)
            if existing is None:
                self._new(platform)
            else:
                self.list.setCurrentRow(existing)
        elif self.profiles:
            self.list.setCurrentRow(0)

    # ------------------------------------------------------------ profile list
    def _fill(self):
        r = self.list.currentRow()
        self._row = None
        self.list.blockSignals(True)
        self.list.clear()
        for p in self.profiles:
            self.list.addItem(p["name"] or "(unnamed)")
        self.list.blockSignals(False)
        if self.profiles:
            self.list.setCurrentRow(max(0, min(r, len(self.profiles) - 1)))

    def done(self, result):
        try:
            if getattr(self, "_row", None) is not None:
                self._save_current(quiet=True)    # closing keeps what was typed
        except Exception:
            pass
        super().done(result)

    def _cur(self):
        r = getattr(self, "_row", None)
        if r is None:
            r = self.list.currentRow()
        return self.profiles[r] if 0 <= r < len(self.profiles) else None

    def _new(self, platform):
        p = uploader.new_profile(platform)
        base, n = p["name"] or "New upload", 2
        p["name"] = base
        while any(x["name"] == p["name"] for x in self.profiles):
            p["name"] = f"{base} {n}"
            n += 1
        self.profiles.append(p)
        self._fill()
        self.list.setCurrentRow(len(self.profiles) - 1)
        self._persist()

    def _delete(self):
        p = self._cur()
        if p and QMessageBox.question(self, "Delete", f"Delete profile '{p['name']}'?") == QMessageBox.Yes:
            try:
                uploader.unschedule(p)
            except Exception:
                pass
            self.profiles.remove(p)
            self._fill()
            self._persist()

    def _load(self, _r):
        prev = getattr(self, "_row", None)
        if prev is not None and prev != _r and 0 <= prev < len(self.profiles):
            self._save_current(quiet=True)      # keep edits to the profile you're leaving
        self._row = _r if _r >= 0 else None
        p = self._cur()
        if not p:
            return
        self.name.setText(p["name"])
        self.platform.setCurrentIndex(max(0, self.platform.findData(p.get("platform_id", ""))))
        self.folder.setText(p.get("local_folder", ""))
        self.host.setText(p.get("host", ""))
        self.port.setValue(int(p.get("port") or 22))
        self.user.setText(p.get("username", ""))
        self.pw.clear()
        self.pw.setPlaceholderText("(saved)" if p.get("password") else "")
        self.remote.setText(p.get("remote_dir", "/"))
        self.method.setCurrentIndex(max(0, self.method.findData(p.get("method") or "sftp")))
        self.dest.setText(p.get("dest_folder", ""))
        self.key.setText(p.get("key_file", ""))
        self.key_pw.clear()
        self.key_pw.setPlaceholderText("(saved)" if p.get("key_passphrase") else "key passphrase")
        self.pgp.setText(p.get("pgp_key_file", ""))
        self.pgp_armor.setChecked(bool(p.get("pgp_armor")))
        self.guard.setChecked(bool(p.get("guard", True)))
        self.guard_pct.setValue(int(p.get("guard_drop_pct") or 10))
        self._method_changed()
        self.zip.setChecked(bool(p.get("zip")))
        self.zip_name.setText(p.get("zip_name", ""))
        self.check.setChecked(bool(p.get("check_first", True)))
        self.block.setChecked(bool(p.get("block_on_errors", True)))
        self.archive.setChecked(bool(p.get("archive", True)))
        self.time.setTime(QTime.fromString(p.get("schedule_time") or "05:00", "HH:mm"))

    def _save_current(self, quiet=False):
        p = self._cur()
        if not p:
            return None
        old_name = p["name"]
        p.update(name=self.name.text().strip() or old_name, platform_id=self.platform.currentData(),
                 local_folder=self.folder.text().strip(), host=self.host.text().strip(), port=self.port.value(),
                 username=self.user.text().strip(), remote_dir=self.remote.text().strip() or "/",
                 zip=self.zip.isChecked(), zip_name=self.zip_name.text().strip(), check_first=self.check.isChecked(),
                 block_on_errors=self.block.isChecked(), archive=self.archive.isChecked(),
                 schedule_time=self.time.time().toString("HH:mm"), method=self.method.currentData(),
                 dest_folder=self.dest.text().strip(), key_file=self.key.text().strip(),
                 guard=self.guard.isChecked(), guard_drop_pct=self.guard_pct.value(),
                 pgp_key_file=self.pgp.text().strip(), pgp_armor=self.pgp_armor.isChecked())
        if self.key_pw.text():
            p["key_passphrase"] = uploader.protect(self.key_pw.text())
            self.key_pw.clear()
        if self.pw.text():
            p["password"] = uploader.protect(self.pw.text())
            self.pw.clear()
            self.pw.setPlaceholderText("(saved)")
        if p["name"] != old_name:
            if any(x is not p and x["name"] == p["name"] for x in self.profiles):
                p["name"] = old_name
                self.name.setText(old_name)
                QMessageBox.warning(self, "Name in use", "Another profile already has that name.")
            else:
                note = uploader.rename_profile(p, old_name)
                if note:
                    self._log(f"Renamed '{old_name}' to '{p['name']}': {note}")
        self._persist()
        row = self._row if getattr(self, "_row", None) is not None else self.list.currentRow()
        if self.list.item(row):
            self.list.item(row).setText(p["name"])
        if not quiet:
            self._log("Profile saved.")
        return p

    def _persist(self):
        self.settings["upload_profiles"] = self.profiles
        paths.save_settings(self.settings)

    def _method_changed(self, _i=None):
        m = self.method.currentData()
        net = m != "folder"
        self.dest_w.setEnabled(m == "folder")
        for w in (self.host, self.port, self.user, self.pw, self.remote):
            w.setEnabled(net)
        self.key_w.setEnabled(m == "sftp")
        if m == "ftps" and self.port.value() == 22:
            self.port.setValue(21)
        elif m == "sftp" and self.port.value() == 21:
            self.port.setValue(22)

    def _pick_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, "Choose the destination folder", edit.text())
        if d:
            edit.setText(d)

    def _pick_key(self):
        fn, _ = QFileDialog.getOpenFileName(self, "SSH private key", self.key.text(), "All files (*)")
        if fn:
            self.key.setText(fn)

    def _pick_pgp(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Vendor's PGP public key", self.pgp.text(),
                                            "PGP keys (*.asc *.gpg *.pub *.key);;All files (*)")
        if not fn:
            return
        from ..pgp import key_info
        try:
            info = key_info(fn)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "PGP key", str(e))
            return
        self.pgp.setText(fn)
        self._log(f"PGP key: {info}")

    def _changes(self):
        p = self._save_current(quiet=True)
        if not p:
            return
        try:
            diffs = uploader.what_changed(p, self.platforms)
        except Exception as e:  # noqa: BLE001
            QMessageBox.information(self, "What changed?", str(e))
            return
        from .tools_dialogs import DiffDialog
        DiffDialog(diffs, self, f"What changed since the last good upload - {p['name']}").exec()

    def _override(self):
        p = self._save_current(quiet=True)
        if not p:
            return
        if QMessageBox.question(self, "Upload anyway once",
                                "Upload even though the safety net found empty files or a big drop?\n\n"
                                "Only do this when the change is real (e.g. summer, a school closed). The safety "
                                "net turns back on after this run.") != QMessageBox.Yes:
            return
        p["override_once"] = True
        self._persist()
        self._run()

    def _history(self):
        p = self._cur()
        if not p:
            return
        runs = uploader.load_history(p["name"]).get("runs", [])
        self._log("-" * 60)
        if not runs:
            self._log("No runs recorded yet.")
        for r in runs[-15:]:
            tot = sum(v for v in (r.get("counts") or {}).values() if v and v > 0)
            self._log(f"{r['when'].replace('T', ' ')}  {r['status'].upper():7} {tot:>8,} rows  {r.get('message', '')}")

    def _alerts(self):
        from .alerts_dialog import AlertsDialog
        AlertsDialog(self.settings, self).exec()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Folder with the exported CSV files", self.folder.text())
        if d:
            self.folder.setText(d)

    def _log(self, line):
        self.log.appendPlainText(line)

    # ------------------------------------------------------------ actions
    def _busy(self, fn, *args, done=None):
        self.worker = TaskWorker(lambda *a, progress=None: fn(*a), *args)
        self.worker.done.connect(lambda res, err: (self._log(f"ERROR: {err}") if err else None,
                                                   done(res) if done and not err else None))
        self.worker.start()

    def _test(self):
        p = self._save_current(quiet=True)
        if p:
            self._log(f"Testing {p['host']}...")
            self._busy(uploader.test_connection, p, done=self._log)

    def _check_only(self):
        p = self._save_current(quiet=True)
        plat = next((x for x in self.platforms if x["id"] == p.get("platform_id")), None) if p else None
        if not plat:
            QMessageBox.information(self, "Check", "Choose a package for this profile first.")
            return
        from ..validator import check_folder
        from .check_dialog import CheckDialog
        CheckDialog(check_folder(plat, p["local_folder"]), self).exec()

    def _run(self):
        p = self._save_current(quiet=True)
        if not p:
            return
        if (p.get("method") or "sftp") != "folder" and not p.get("host"):
            QMessageBox.information(self, "Run", "Enter the host first.")
            return
        if p.get("method") == "folder" and not p.get("dest_folder"):
            QMessageBox.information(self, "Run", "Choose the destination folder first.")
            return
        self._log("-" * 60)
        plats = self.platforms
        self.worker = TaskWorker(lambda prof, progress=None: uploader.run_profile(prof, plats), p)
        self.worker.done.connect(lambda res, err: (self._log(res[1] if res else f"ERROR: {err}"), self._reload_profile()))
        self.worker.start()

    def _reload_profile(self):
        # the run may have cleared 'Upload anyway once'
        fresh = {p["name"]: p for p in paths.load_settings().get("upload_profiles", [])}
        for p in self.profiles:
            if p["name"] in fresh:
                p["override_once"] = fresh[p["name"]].get("override_once", False)

    def _schedule(self):
        p = self._save_current(quiet=True)
        if not p:
            return
        try:
            out = uploader.schedule(p)
            self._persist()
            self._log(f"Scheduled daily at {p['schedule_time']}: {out}")
            QMessageBox.information(self, "Scheduled", f"'{p['name']}' will run every day at {p['schedule_time']}.\n\n"
                                    "Make sure it runs at least an hour after the CAC Agent jobs.\n\nTo run while "
                                    "you're signed out: Task Scheduler > this task > Properties > 'Run whether user "
                                    "is logged on or not' (keep the same Windows user so the saved password works).")
        except Exception as e:
            QMessageBox.warning(self, "Schedule", str(e))

    def _unschedule(self):
        p = self._cur()
        if p:
            self._log(uploader.unschedule(p))
            self._persist()
