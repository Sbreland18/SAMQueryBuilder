"""District tools: CAC Agent setup walkthrough, vendor privacy register, year-end rollover checklist."""
from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import paths
from ..exports import build_query, load_platforms, missing_settings, override_state
from ..query_model import generate_sql
from .widgets import SqlHighlighter, label


def _copy_row(widget, getter, parent_layout, caption):
    row = QHBoxLayout()
    row.addWidget(widget, 1)
    b = QPushButton("Copy")
    b.clicked.connect(lambda: (QGuiApplication.clipboard().setText(getter()), b.setText("Copied"),))
    row.addWidget(b)
    w = QWidget()
    w.setLayout(row)
    parent_layout.addRow(caption, w)
    return b


# ============================================================================ CAC Agent walkthrough
class CacWizardDialog(QDialog):
    def __init__(self, settings: dict, platform_id: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CAC Agent setup walkthrough")
        self.resize(1100, 760)
        self.settings = settings
        self.platforms = [p for p in load_platforms() if p["id"] != "codes"]
        lay = QVBoxLayout(self)
        intro = QHBoxLayout()
        intro.addWidget(label("Set up each export file in SAM once, step by step. Copy each value straight into SAM "
                              "and tick the file off - your progress is saved. The CAC Agent must be installed on "
                              "the computer that receives the files (once per computer).", "subtitle"), 1)
        gb = QPushButton("CAC Agent setup guide...")
        gb.setToolTip("Installing the CAC Agent, adding queries and jobs, and the Windows Task Scheduler step")
        gb.clicked.connect(lambda: __import__("sam_qb.ui.docviewer", fromlist=["show_doc"]).show_doc(
            self, "CAC Agent Setup Guide.md"))
        intro.addWidget(gb)
        lay.addLayout(intro)
        top = QHBoxLayout()
        top.addWidget(QLabel("Package:"))
        self.pkg = QComboBox()
        for p in self.platforms:
            self.pkg.addItem(p["name"], p["id"])
        self.pkg.currentIndexChanged.connect(self._pkg_changed)
        top.addWidget(self.pkg, 1)
        top.addWidget(QLabel("Folder the jobs save to:"))
        self.folder = QLineEdit()
        self.folder.setPlaceholderText(r"e.g. C:\SAM Exports\Clever")
        self.folder.editingFinished.connect(self._save_folder)
        top.addWidget(self.folder, 1)
        fb = QPushButton("Browse...")
        fb.clicked.connect(self._browse)
        top.addWidget(fb)
        from PySide6.QtCore import QTime
        from PySide6.QtWidgets import QTimeEdit
        top.addWidget(QLabel("Job time:"))
        self.job_time = QTimeEdit(QTime(1, 0))
        self.job_time.setDisplayFormat("h:mm AP")
        self.job_time.setToolTip("The time you give these jobs in SAM's CAC Agent - used by Tools > Nightly schedule "
                                 "timeline to check that uploads run after the files are made")
        self.job_time.timeChanged.connect(self._save_time)
        top.addWidget(self.job_time)
        lay.addLayout(top)
        self.warn = label("", "hint")
        lay.addWidget(self.warn)

        body = QHBoxLayout()
        left = QVBoxLayout()
        self.files = QListWidget()
        self.files.currentRowChanged.connect(self._show)
        self.files.itemChanged.connect(self._ticked)
        left.addWidget(self.files, 1)
        self.progress = QLabel()
        left.addWidget(self.progress)
        body.addLayout(left, 1)

        right = QVBoxLayout()
        g1 = QGroupBox("1. Administration > CAC Agent > Query Maintenance > Add New")
        f1 = QFormLayout(g1)
        self.title = QLineEdit()
        self.title.setReadOnly(True)
        _copy_row(self.title, self.title.text, f1, "Query Title:")
        self.sql = QPlainTextEdit()
        self.sql.setReadOnly(True)
        self.sql.setFont(QFont("Consolas", 9))
        self.sql.setLineWrapMode(QPlainTextEdit.NoWrap)
        SqlHighlighter(self.sql.document())
        self.sql.setMinimumHeight(260)
        _copy_row(self.sql, self.sql.toPlainText, f1, "Query:")
        right.addWidget(g1, 1)
        g2 = QGroupBox("2. Administration > CAC Agent > Agent Maintenance > Add Job")
        f2 = QFormLayout(g2)
        self.job_query = QLineEdit()
        self.job_query.setReadOnly(True)
        f2.addRow("Query:", self.job_query)
        self.agent_name = QLineEdit()
        self.agent_name.setReadOnly(True)
        _copy_row(self.agent_name, self.agent_name.text, f2, "Agent Name:")
        self.fname = QLineEdit()
        self.fname.setReadOnly(True)
        _copy_row(self.fname, self.fname.text, f2, "File Name (exact):")
        self.fpath = QLineEdit()
        self.fpath.setReadOnly(True)
        _copy_row(self.fpath, self.fpath.text, f2, "Folder:")
        f2.addRow("", label("Use the SAME folder and the same time (e.g. 1:00 AM) for every job in this package, "
                            "then click Save Job.", "hint"))
        right.addWidget(g2)
        g3 = QGroupBox("3. Windows Task Scheduler on the agent computer (once per computer)")
        f3 = QFormLayout(g3)
        self.listener = QLineEdit(r"C:\Program Files\Central Access Corp\CAS Agent\CAS Agent Listener")
        self.listener.setReadOnly(True)
        _copy_row(self.listener, self.listener.text, f3, "Program to run:")
        from PySide6.QtCore import QTime as _QT
        from PySide6.QtWidgets import QTimeEdit as _QTE
        self.listener_time = _QTE(_QT.fromString(self.settings.get("cac_listener_time") or "02:00", "HH:mm"))
        self.listener_time.setDisplayFormat("h:mm AP")
        self.listener_time.timeChanged.connect(lambda t: (self.settings.__setitem__("cac_listener_time",
                                                                                    t.toString("HH:mm")),
                                                          paths.save_settings(self.settings)))
        f3.addRow("Listener runs at:", self.listener_time)
        f3.addRow("", label("Create Basic Task > Daily, at least 1 hour after the job time > Start a program > the "
                            "program above. Then Properties: 'Run whether user is logged on or not' and 'Run with "
                            "highest privileges'. Schedule the app's upload at least 1 hour after that.", "hint"))
        right.addWidget(g3)
        nb = QHBoxLayout()
        from .. import samdb as _samdb
        if _samdb.enabled(self.settings):
            cb = QPushButton("Count rows in SAM")
            cb.setToolTip("How many rows this file will have, and how long the query takes")
            cb.clicked.connect(self._count)
            nb.addWidget(cb)
        self.count_lbl = label("", "hint")
        nb.addWidget(self.count_lbl)
        self.done_next = QPushButton("Mark done && next")
        self.done_next.setObjectName("primary")
        self.done_next.clicked.connect(self._done_next)
        nb.addWidget(self.done_next)
        nb.addStretch()
        right.addLayout(nb)
        body.addLayout(right, 3)
        lay.addLayout(body, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close)
        if platform_id:
            self.pkg.setCurrentIndex(max(0, self.pkg.findData(platform_id)))
        self._pkg_changed()

    def _p(self):
        return self.platforms[self.pkg.currentIndex()] if self.platforms else None

    def _progress(self) -> set:
        return set((self.settings.get("cac_progress") or {}).get(self._p()["id"], []))

    def _pkg_changed(self, _i=None):
        p = self._p()
        if not p:
            return
        self.folder.setText((self.settings.get("cac_folders") or {}).get(p["id"], ""))
        from PySide6.QtCore import QTime
        self.job_time.blockSignals(True)
        self.job_time.setTime(QTime.fromString((self.settings.get("cac_times") or {}).get(p["id"], "01:00"), "HH:mm"))
        self.job_time.blockSignals(False)
        need = missing_settings(p, self.settings)
        self.warn.setText("<span style='color:#B42318'><b>Fill in District Settings first:</b> " + ", ".join(need)
                          + "</span>" if need else "")
        done = self._progress()
        self.files.blockSignals(True)
        self.files.clear()
        for fe in p["files"]:
            it = QListWidgetItem(fe["file"] + ("   (district version)" if override_state(p, fe) else ""))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if fe["file"] in done else Qt.Unchecked)
            self.files.addItem(it)
        self.files.blockSignals(False)
        self._update_progress()
        first = next((i for i, fe in enumerate(p["files"]) if fe["file"] not in done), 0)
        self.files.setCurrentRow(first)

    def _show(self, r):
        p = self._p()
        if not p or not (0 <= r < len(p["files"])):
            return
        fe = p["files"][r]
        q = build_query(p, fe, self.settings)
        self.title.setText(q.name[:60])
        self.job_query.setText(q.name[:60])
        self.agent_name.setText(q.name[:60])
        self.sql.setPlainText(generate_sql(q))
        self.fname.setText(fe["file"])
        self.fpath.setText(self.folder.text())

    def _ticked(self, _it=None):
        p = self._p()
        done = [p["files"][i]["file"] for i in range(self.files.count())
                if self.files.item(i).checkState() == Qt.Checked]
        self.settings.setdefault("cac_progress", {})[p["id"]] = done
        self.settings.setdefault("cac_times", {}).setdefault(p["id"], self.job_time.time().toString("HH:mm"))
        paths.save_settings(self.settings)
        self._update_progress()

    def _update_progress(self):
        p = self._p()
        n = sum(1 for i in range(self.files.count()) if self.files.item(i).checkState() == Qt.Checked)
        self.progress.setText(f"<b>{n} of {len(p['files'])}</b> files set up" +
                              (" - all done!" if n == len(p["files"]) else ""))

    def _done_next(self):
        r = self.files.currentRow()
        if r < 0:
            return
        self.files.item(r).setCheckState(Qt.Checked)
        if r + 1 < self.files.count():
            self.files.setCurrentRow(r + 1)

    def _count(self):
        from PySide6.QtWidgets import QApplication
        from .. import samdb
        p, r = self._p(), self.files.currentRow()
        if not p or r < 0:
            return
        q = build_query(p, p["files"][r], self.settings)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.count_lbl.setText(f"{p['files'][r]['file']}: " + samdb.count_text(
                *samdb.count(self.settings, generate_sql(q, header=False))))
        except Exception as e:  # noqa: BLE001
            self.count_lbl.setText(f"Couldn't count: {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _save_time(self, t):
        self.settings.setdefault("cac_times", {})[self._p()["id"]] = t.toString("HH:mm")
        paths.save_settings(self.settings)

    def _save_folder(self):
        self.settings.setdefault("cac_folders", {})[self._p()["id"]] = self.folder.text().strip()
        paths.save_settings(self.settings)
        self.fpath.setText(self.folder.text())

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Folder the CAC Agent jobs save to", self.folder.text())
        if d:
            self.folder.setText(d.replace("/", "\\"))
            self._save_folder()


# ============================================================================ Vendor privacy register
class RegisterDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        from .. import register
        self.reg = register
        self.setWindowTitle("Vendor privacy register")
        self.resize(1180, 700)
        self.settings = settings
        self.platforms = [p for p in load_platforms() if p.get("kind") != "tool"]
        lay = QVBoxLayout(self)
        lay.addWidget(label("Tick the vendors your district uses and record each data-privacy agreement. Data shared "
                            "comes from the export packages. Agreements expiring within 60 days turn orange.",
                            "subtitle"))
        self.only = QCheckBox("Show only vendors in use")
        self.only.toggled.connect(self._fill)
        lay.addWidget(self.only)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["In use", "Vendor", "Data shared", "Agreement", "Signed", "Expires",
                                              "Status", "Contact / notes", "Documents"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)
        from ..register import reminder_settings
        rs = reminder_settings(settings)
        rr = QHBoxLayout()
        self.rem_on = QCheckBox("Email reminders 60 and 30 days before an agreement ends (and when it expires) to:")
        self.rem_on.setChecked(bool(rs.get("enabled")))
        rr.addWidget(self.rem_on)
        self.rem_to = QLineEdit(rs.get("to", ""))
        self.rem_to.setPlaceholderText("blank = the Upload alerts recipients")
        rr.addWidget(self.rem_to, 1)
        rb = QPushButton("Send due reminders now")
        rb.clicked.connect(self._send_reminders)
        rr.addWidget(rb)
        lay.addLayout(rr)
        lay.addWidget(label("Reminders go out from the PC that runs the scheduled uploads or health report (checked "
                            "once a day) - no extra scheduled task is needed.", "hint"))
        br = QHBoxLayout()
        sv = QPushButton("Save")
        sv.setObjectName("primary")
        sv.clicked.connect(self._save)
        br.addWidget(sv)
        rp = QPushButton("Save printable report (HTML)...")
        rp.clicked.connect(self._report)
        br.addWidget(rp)
        br.addStretch()
        cl = QPushButton("Close")
        cl.clicked.connect(self.accept)
        br.addWidget(cl)
        lay.addLayout(br)
        self._widgets = {}
        self._fill()

    def done(self, result):
        try:
            self._save_quiet()     # closing keeps the ticks and dates you entered
        except Exception:
            pass
        super().done(result)

    def _fill(self):
        from ..privacy import LEVELS
        if self._widgets:
            self._collect()
        in_use = self.reg.in_use_ids(self.settings)
        rows = [p for p in self.platforms if not self.only.isChecked() or p["id"] in in_use]
        self.table.setRowCount(len(rows))
        self._widgets = {}
        for r, p in enumerate(rows):
            e = self.reg.entry(self.settings, p["id"])
            cb = QCheckBox()
            cb.setChecked(p["id"] in in_use)
            cw = QWidget()
            cl = QHBoxLayout(cw)
            cl.setContentsMargins(6, 0, 0, 0)
            cl.addWidget(cb)
            self.table.setCellWidget(r, 0, cw)
            self.table.setItem(r, 1, QTableWidgetItem(p["name"]))
            shared = self.reg.data_shared(p)
            txt = "; ".join(f"{LEVELS[l][0]}: {', '.join(shared[l])}" for l in LEVELS if l in shared) or \
                "names, IDs, grades, schools only"
            it = QTableWidgetItem(txt)
            it.setToolTip(txt)
            self.table.setItem(r, 2, it)
            ag = QComboBox()
            for k, t in self.reg.AGREEMENTS.items():
                ag.addItem(t, k)
            ag.setCurrentIndex(max(0, ag.findData(e["agreement"])))
            self.table.setCellWidget(r, 3, ag)
            dates = []
            for c, key in ((4, "signed"), (5, "expires")):
                de = QDateEdit()
                de.setCalendarPopup(True)
                de.setDisplayFormat("MM/dd/yyyy")
                de.setSpecialValueText(" ")
                de.setMinimumDate(QDate(2000, 1, 1))
                de.setDate(QDate.fromString(e[key], "yyyy-MM-dd") if e[key] else de.minimumDate())
                self.table.setCellWidget(r, c, de)
                dates.append(de)
            st, color = self.reg.status(e)
            si = QTableWidgetItem(st)
            si.setForeground(Qt.GlobalColor.black)
            from PySide6.QtGui import QColor
            si.setForeground(QColor(color))
            self.table.setItem(r, 6, si)
            notes = QLineEdit(" | ".join(x for x in (e["contact"], e["notes"]) if x))
            notes.setPlaceholderText("vendor contact | notes")
            self.table.setCellWidget(r, 7, notes)
            self.table.setCellWidget(r, 8, self._docs_cell(p["id"]))
            self._widgets[p["id"]] = (cb, ag, dates[0], dates[1], notes)
        self.table.resizeRowsToContents()

    def _collect(self):
        reg = self.settings.setdefault("vendor_register", {})
        for pid, (cb, ag, signed, expires, notes) in self._widgets.items():
            def d(w):
                return "" if w.date() == w.minimumDate() else w.date().toString("yyyy-MM-dd")
            contact, _, note = notes.text().partition("|")
            reg[pid] = {"in_use": cb.isChecked(), "agreement": ag.currentData(), "signed": d(signed),
                        "expires": d(expires), "contact": contact.strip(), "notes": note.strip()}

    def _save(self):
        self._collect()
        self.settings["agreement_reminders"] = {"enabled": self.rem_on.isChecked(), "to": self.rem_to.text().strip()}
        paths.save_settings(self.settings)
        self._fill()

    def _docs_cell(self, pid):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QMenu, QToolButton
        docs = self.reg.documents(pid)
        b = QToolButton()
        b.setText(f"{len(docs)} file(s)" if docs else "Attach...")
        b.setToolTip("Signed agreement (PDF), vendor privacy policy or other papers for this vendor")
        b.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(b)
        for d in docs:
            m.addAction(f"Open {d.name}", lambda f=str(d): QDesktopServices.openUrl(QUrl.fromLocalFile(f)))
        if docs:
            m.addSeparator()
        m.addAction("Attach a document...", lambda: self._attach(pid))
        m.addAction("Open the folder", lambda: (self.reg.docs_dir(pid).mkdir(parents=True, exist_ok=True),
                                                QDesktopServices.openUrl(QUrl.fromLocalFile(
                                                    str(self.reg.docs_dir(pid))))))
        b.setMenu(m)
        return b

    def _attach(self, pid):
        files, _ = QFileDialog.getOpenFileNames(self, "Attach agreement documents", "",
                                                "Documents (*.pdf *.docx *.doc *.png *.jpg *.txt);;All files (*)")
        for f in files:
            self.reg.attach_document(pid, f)
        if files:
            self._collect()
            self._fill()

    def _send_reminders(self):
        from ..register import send_reminders
        self._save_quiet()
        try:
            QMessageBox.information(self, "Agreement reminders", send_reminders(self.settings))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Agreement reminders", str(e))

    def _save_quiet(self):
        self._collect()
        self.settings["agreement_reminders"] = {"enabled": self.rem_on.isChecked(), "to": self.rem_to.text().strip()}
        paths.save_settings(self.settings)

    def _report(self):
        self._save()
        fn, _ = QFileDialog.getSaveFileName(self, "Save privacy register",
                                            f"Vendor privacy register {dt.date.today():%Y-%m-%d}.html",
                                            "Web page (*.html)")
        if fn:
            with open(fn, "w", encoding="utf-8") as fh:
                fh.write(self.reg.html_report(self.settings, self.platforms))
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(fn))


# ============================================================================ Rollover checklist
class RolloverDialog(QDialog):
    action = Signal(str)

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        from .. import rollover
        self.ro = rollover
        self.setWindowTitle("Year-end rollover checklist")
        self.resize(820, 720)
        self.settings = settings
        lay = QVBoxLayout(self)
        self.head = label("", "subtitle")
        lay.addWidget(self.head)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.il = QVBoxLayout(inner)
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)
        self.checks = {}
        self.auto = {}
        acts = {"district": "Open District Settings", "codes": "Open SAM Codes & Schools",
                "baselines": "Reset baselines now", "uploads": "Open Package & Upload", "exports": "Open exports",
                "cleanup": "Open cleanup reports", "register": "Open privacy register"}
        for key, title, detail, act in rollover.ITEMS:
            box = QGroupBox()
            bl = QVBoxLayout(box)
            cb = QCheckBox(title)
            f = cb.font()
            f.setBold(True)
            cb.setFont(f)
            cb.toggled.connect(lambda v, k=key: self._toggle(k, v))
            bl.addWidget(cb)
            bl.addWidget(label(detail, "hint"))
            a = label("", "hint")
            bl.addWidget(a)
            self.auto[key] = a
            if act:
                b = QPushButton(acts[act])
                b.clicked.connect(lambda _=False, x=act: self._do(x))
                row = QHBoxLayout()
                row.addWidget(b)
                row.addStretch()
                bl.addLayout(row)
            self.il.addWidget(box)
            self.checks[key] = cb
        self.il.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close)
        self.refresh()

    def refresh(self):
        done = self.ro.done(self.settings)
        autos = self.ro.auto_checks(self.settings)
        for k, cb in self.checks.items():
            cb.blockSignals(True)
            cb.setChecked(k in done)
            cb.blockSignals(False)
            ok_msg = autos.get(k)
            if ok_msg:
                ok, msg = ok_msg
                self.auto[k].setText(f"<span style='color:{'#1E7B34' if ok else '#B42318'}'>"
                                     f"{'OK' if ok else 'Check'}: {msg}</span>")
        n = len(done & set(self.checks))
        self.head.setText(f"School year ending {self.ro.year_key(self.settings) or '?'}: <b>{n} of "
                          f"{len(self.checks)}</b> steps done. Work through these each summer before the first "
                          "nightly uploads of the new year.")

    def _toggle(self, key, value):
        self.ro.set_done(self.settings, key, value)
        paths.save_settings(self.settings)
        self.refresh()

    def _do(self, act):
        if act == "baselines":
            n = self.ro.reset_baselines(self.settings)
            QMessageBox.information(self, "Safety net", f"Baselines cleared for {n} upload profile(s). The next "
                                    "successful upload of each becomes the new baseline.")
            self.checks["baselines"].setChecked(True)
            return
        self.action.emit(act)
        self.refresh()


# ============================================================================ What changed? (file diff)
class DiffDialog(QDialog):
    def __init__(self, diffs=None, parent=None, title="What changed?"):
        super().__init__(parent)
        from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
        self._TI = QTreeWidgetItem
        self.setWindowTitle(title)
        self.resize(1000, 680)
        self.diffs = diffs or []
        lay = QVBoxLayout(self)
        lay.addWidget(label("Compare two versions of an export file - for example last night's upload and tonight's "
                            "file - to see exactly which rows were added, removed or changed.", "subtitle"))
        pick = QHBoxLayout()
        self.old = QLineEdit()
        self.old.setPlaceholderText("Older file (e.g. archive\\_last_good_upload\\students.csv)")
        self.new = QLineEdit()
        self.new.setPlaceholderText("Newer file")
        for w, cap in ((self.old, "Older"), (self.new, "Newer")):
            b = QPushButton(f"{cap}...")
            b.clicked.connect(lambda _=False, e=w: self._browse(e))
            pick.addWidget(w, 1)
            pick.addWidget(b)
        cb = QPushButton("Compare")
        cb.setObjectName("primary")
        cb.clicked.connect(self._compare)
        pick.addWidget(cb)
        lay.addLayout(pick)
        self.summary = label("", "")
        self.summary.setTextFormat(Qt.RichText)
        lay.addWidget(self.summary)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Change", "Key / column", "Before", "After"])
        self.tree.setColumnWidth(0, 260)
        self.tree.setColumnWidth(1, 260)
        self.tree.setColumnWidth(2, 200)
        lay.addWidget(self.tree, 1)
        br = QHBoxLayout()
        sv = QPushButton("Save as CSV report...")
        sv.clicked.connect(self._save)
        br.addWidget(sv)
        br.addStretch()
        cl = QPushButton("Close")
        cl.clicked.connect(self.accept)
        br.addWidget(cl)
        lay.addLayout(br)
        self._show()

    def _browse(self, edit):
        fn, _ = QFileDialog.getOpenFileName(self, "Choose a CSV file", edit.text(), "CSV / text (*.csv *.txt)")
        if fn:
            edit.setText(fn)

    def _compare(self):
        from ..filediff import diff_files
        try:
            self.diffs = [diff_files(self.old.text().strip(), self.new.text().strip())]
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Compare", str(e))
            return
        self._show()

    def _show(self):
        self.tree.clear()
        if not self.diffs:
            self.summary.setText("Choose two files and click Compare.")
            return
        lines = []
        for d in self.diffs:
            lines.append(f"<b>{d.file}</b>: {d.old_count:,} &rarr; {d.new_count:,} rows - "
                         f"<span style='color:#1E7B34'>{len(d.added):,} added</span>, "
                         f"<span style='color:#B42318'>{len(d.removed):,} removed</span>, "
                         f"<span style='color:#9A6700'>{len(d.changed):,} changed</span>"
                         + (f" <i>({d.note})</i>" if d.note else "") + f" &nbsp;<small>key: {', '.join(d.key)}</small>")
            top = self._TI([d.file, "", "", ""])
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            self.tree.addTopLevelItem(top)
            for cap, rows in (("Added", d.added), ("Removed", d.removed)):
                g = self._TI([f"{cap} ({len(rows):,})", "", "", ""])
                top.addChild(g)
                for r in rows[:2000]:
                    keyv = " / ".join(r.get(c, "") for c in d.key)
                    desc = ", ".join(f"{k}={v}" for k, v in list(r.items())[:6] if k not in d.key)
                    g.addChild(self._TI(["", keyv, desc if cap == "Removed" else "", desc if cap == "Added" else ""]))
            g = self._TI([f"Changed ({len(d.changed):,})", "", "", ""])
            top.addChild(g)
            for key, ch in d.changed[:2000]:
                k = self._TI(["", key, "", ""])
                g.addChild(k)
                for col, (a, b) in ch.items():
                    k.addChild(self._TI(["", col, a, b]))
            top.setExpanded(True)
        self.summary.setText("<br>".join(lines))

    def _save(self):
        if not self.diffs:
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Save change report", f"changes {dt.date.today():%Y-%m-%d}.csv",
                                            "CSV (*.csv)")
        if fn:
            from ..filediff import write_report
            write_report(self.diffs, fn)


# ============================================================================ Change log
class ChangeLogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        from .. import audit
        self.audit = audit
        self.setWindowTitle("Change log")
        self.resize(1050, 640)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Who changed District Settings, schools and codes, uploads, alerts, report emails, the "
                            "SAM connection, district package versions and the privacy register on this PC.",
                            "subtitle"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter (user, area or text)...")
        self.search.textChanged.connect(self._fill)
        lay.addWidget(self.search)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["When", "User", "Computer", "Area", "Change"])
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table, 1)
        br = QHBoxLayout()
        ex = QPushButton("Export CSV...")
        ex.clicked.connect(self._export)
        br.addWidget(ex)
        br.addStretch()
        cl = QPushButton("Close")
        cl.clicked.connect(self.accept)
        br.addWidget(cl)
        lay.addLayout(br)
        self._fill()

    def _fill(self, _t=None):
        flt = self.search.text().lower()
        rows = []
        for e in reversed(self.audit.load()):
            for c in e.get("changes", []):
                r = [e["when"].replace("T", " "), e.get("user", ""), e.get("computer", ""), e.get("area", ""), c]
                if not flt or flt in " ".join(r).lower():
                    rows.append(r)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows[:5000]):
            for j, v in enumerate(r):
                self.table.setItem(i, j, QTableWidgetItem(v))
        self.table.resizeColumnsToContents()

    def _export(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Export change log", "change log.csv", "CSV (*.csv)")
        if fn:
            self.audit.export_csv(fn)


# ============================================================================ Report emails
class ReportsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QTime
        from PySide6.QtWidgets import QTimeEdit
        from .. import reports, samdb
        self.rep = reports
        self.QTime = QTime
        self.setWindowTitle("Report emails")
        self.resize(980, 640)
        self.settings = settings
        self.jobs = settings.setdefault("report_jobs", [])
        lay = QVBoxLayout(self)
        lay.addWidget(label("Email a report on a schedule - for example the cleanup reports to each principal every "
                            "Monday. The report is a CSV the CAC Agent writes (or, with the SAM connection turned "
                            "on, a query run straight from SAM). Uses the email server from Tools > Upload alerts.",
                            "subtitle"))
        body = QHBoxLayout()
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._load)
        left.addWidget(self.list, 1)
        for txt, fn in (("New report", self._new), ("Delete", self._delete)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            left.addWidget(b)
        body.addLayout(left, 1)
        g = QGroupBox("Report")
        f = QFormLayout(g)
        self.name = QLineEdit()
        f.addRow("Name:", self.name)
        self.source = QComboBox()
        self.source.addItem("A CSV file the CAC Agent writes", "file")
        if samdb.enabled(settings):
            self.source.addItem("A query run in SAM (read-only connection)", "query")
        f.addRow("Data from:", self.source)
        pr = QHBoxLayout()
        self.path = QLineEdit()
        pb = QPushButton("Browse...")
        pb.clicked.connect(self._browse)
        pr.addWidget(self.path, 1)
        pr.addWidget(pb)
        pw = QWidget()
        pw.setLayout(pr)
        f.addRow("CSV file:", pw)
        self.sql = QPlainTextEdit()
        self.sql.setPlaceholderText("SELECT ... (paste the SQL from Step 6, or open a saved query)")
        self.sql.setFont(QFont("Consolas", 9))
        self.sql.setMaximumHeight(110)
        f.addRow("Query:", self.sql)
        self.to = QLineEdit()
        self.to.setPlaceholderText("principal@district.org, clerk@district.org")
        f.addRow("Send to:", self.to)
        self.subject = QLineEdit()
        self.subject.setPlaceholderText("(default: report name + row count)")
        f.addRow("Subject:", self.subject)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Short note at the top of the email, e.g. 'Please fix these in SAM by Friday'")
        f.addRow("Note:", self.note)
        sr = QHBoxLayout()
        self.freq = QComboBox()
        self.freq.addItem("Weekly on", "weekly")
        self.freq.addItem("Every day", "daily")
        self.day = QComboBox()
        for d in reports.DAYS:
            self.day.addItem(d.title(), d)
        self.time = QTimeEdit()
        self.time.setDisplayFormat("HH:mm")
        for w in (self.freq, self.day, QLabel("at"), self.time):
            sr.addWidget(w)
        sr.addStretch()
        sw = QWidget()
        sw.setLayout(sr)
        f.addRow("Schedule:", sw)
        self.skip = QCheckBox("Don't send when the report is empty")
        f.addRow("", self.skip)
        self.attach = QComboBox()
        for k, t in (("csv", "CSV file"), ("xlsx", "Excel file (.xlsx) - frozen header and filters"),
                     ("both", "Both CSV and Excel")):
            self.attach.addItem(t, k)
        f.addRow("Attach as:", self.attach)
        br = QHBoxLayout()
        for txt, fn, prim in (("Save", self._save, False), ("Send now", self._send, True),
                              ("Schedule in Windows", self._schedule, False), ("Remove schedule", self._unschedule, False)):
            b = QPushButton(txt)
            if prim:
                b.setObjectName("primary")
            b.clicked.connect(fn)
            br.addWidget(b)
        br.addStretch()
        right = QVBoxLayout()
        right.addWidget(g)
        right.addLayout(br)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(90)
        right.addWidget(self.log)
        body.addLayout(right, 3)
        lay.addLayout(body, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close)
        self._fill()

    def _fill(self, select=None):
        self._row = None
        self.list.blockSignals(True)
        self.list.clear()
        for j in self.jobs:
            self.list.addItem(j["name"])
        self.list.blockSignals(False)
        if self.jobs:
            self.list.setCurrentRow(select if select is not None else 0)

    def done(self, result):
        try:
            if getattr(self, "_row", None) is not None:
                self._save(quiet=True)
        except Exception:
            pass
        super().done(result)

    def _cur(self):
        r = getattr(self, "_row", None)
        if r is None:
            r = self.list.currentRow()
        return self.jobs[r] if 0 <= r < len(self.jobs) else None

    def _load(self, _r):
        prev = getattr(self, "_row", None)
        if prev is not None and prev != _r and 0 <= prev < len(self.jobs):
            self._save(quiet=True)      # keep edits to the profile you're leaving
        self._row = _r if _r >= 0 else None
        j = self._cur()
        if not j:
            return
        self.name.setText(j["name"])
        self.source.setCurrentIndex(max(0, self.source.findData(j.get("source", "file"))))
        self.path.setText(j.get("csv_path", ""))
        self.sql.setPlainText(j.get("sql", ""))
        self.to.setText(j.get("to", ""))
        self.subject.setText(j.get("subject", ""))
        self.note.setText(j.get("note", ""))
        self.freq.setCurrentIndex(max(0, self.freq.findData(j.get("frequency", "weekly"))))
        self.day.setCurrentIndex(max(0, self.day.findData(j.get("day", "MON"))))
        self.time.setTime(self.QTime.fromString(j.get("time") or "07:00", "HH:mm"))
        self.skip.setChecked(bool(j.get("skip_empty", True)))
        self.attach.setCurrentIndex(max(0, self.attach.findData(j.get("attach", "csv"))))

    def _save(self, quiet=False):
        j = self._cur()
        if not j:
            return None
        old_name = j["name"]
        new_name = self.name.text().strip() or old_name
        if new_name != old_name and any(x is not j and x["name"] == new_name for x in self.jobs):
            QMessageBox.warning(self, "Name in use", "Another report already has that name.")
            new_name = old_name
            self.name.setText(old_name)
        j.update(name=new_name, source=self.source.currentData(),
                 csv_path=self.path.text().strip(), sql=self.sql.toPlainText().strip(), to=self.to.text().strip(),
                 subject=self.subject.text().strip(), note=self.note.text().strip(),
                 frequency=self.freq.currentData(), day=self.day.currentData(),
                 time=self.time.time().toString("HH:mm"), skip_empty=self.skip.isChecked(),
                 attach=self.attach.currentData())
        if new_name != old_name and j.get("task_name"):   # the task runs --report "<name>": re-create it
            from ..scheduler import delete_names, name_variants
            delete_names(name_variants(self.rep.TASK_PREFIX, old_name, [j.get("task_name", "")]))
            j.pop("task_name", None)
            try:
                self.rep.schedule(j)
                self.log.appendPlainText("Re-created the schedule for the new name.")
            except Exception as e:  # noqa: BLE001
                self.log.appendPlainText(f"Couldn't re-create the schedule ({e}) - click Schedule again.")
        paths.save_settings(self.settings)
        row = self._row if getattr(self, "_row", None) is not None else self.list.currentRow()
        if self.list.item(row):
            self.list.item(row).setText(j["name"])
        if not quiet:
            self.log.appendPlainText("Saved.")
        return j

    def _new(self):
        base, n = "New report", 2
        name = base
        while any(x["name"] == name for x in self.jobs):
            name, n = f"{base} {n}", n + 1
        self.jobs.append(self.rep.new_job(name))
        paths.save_settings(self.settings)
        self._fill(len(self.jobs) - 1)

    def _delete(self):
        j = self._cur()
        if j and QMessageBox.question(self, "Delete", f"Delete report '{j['name']}'?") == QMessageBox.Yes:
            try:
                self.rep.unschedule(j)
            except Exception:
                pass
            self.jobs.remove(j)
            paths.save_settings(self.settings)
            self._fill()

    def _browse(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Report CSV file", self.path.text(), "CSV (*.csv *.txt)")
        if fn:
            self.path.setText(fn.replace("/", "\\"))

    def _send(self):
        j = self._save(quiet=True)
        if not j:
            return
        try:
            self.log.appendPlainText(self.rep.run_job(j, self.settings))
        except Exception as e:  # noqa: BLE001
            self.log.appendPlainText(f"ERROR: {e}")

    def _schedule(self):
        j = self._save(quiet=True)
        if not j:
            return
        try:
            self.rep.schedule(j)
            paths.save_settings(self.settings)
            when = "every day" if j["frequency"] == "daily" else f"every {j['day'].title()}"
            self.log.appendPlainText(f"Scheduled {when} at {j['time']}.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Schedule", str(e))

    def _unschedule(self):
        j = self._cur()
        if j:
            self.log.appendPlainText(self.rep.unschedule(j))
            paths.save_settings(self.settings)


# ============================================================================ SAM database connection
class SamConnectionDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QSpinBox
        from .. import samdb
        self.db = samdb
        self.setWindowTitle("SAM database connection (optional)")
        self.resize(640, 560)
        self.settings = settings
        c = samdb.get(settings)
        lay = QVBoxLayout(self)
        lay.addWidget(label(
            "<b>Off by default.</b> The builder normally never touches SAM - you paste its SQL into SAM yourself. If "
            "your district allows it, a read-only SQL login lets the builder show real results and exact row "
            "counts, and email reports straight from SAM. Only single SELECT queries are ever sent; anything that "
            "could change data is refused before it leaves this PC. Ask your SAM / database administrator for a "
            "login that is only in <b>db_datareader</b>, and check with Central Access before using it.", "subtitle"))
        g = QGroupBox("Connection")
        f = QFormLayout(g)
        self.on = QCheckBox("Turn on the read-only SAM connection")
        self.on.setChecked(bool(c["enabled"]))
        f.addRow("", self.on)
        self.server = QLineEdit(c["server"])
        self.server.setPlaceholderText(r"e.g. SAMSQL01\SAMS or samsql.district.local,1433")
        f.addRow("SQL Server:", self.server)
        self.database = QLineEdit(c["database"])
        self.database.setPlaceholderText("SAM database name")
        f.addRow("Database:", self.database)
        self.auth = QComboBox()
        self.auth.addItem("Windows sign-in (this user)", "windows")
        self.auth.addItem("SQL login", "sql")
        self.auth.setCurrentIndex(max(0, self.auth.findData(c["auth"])))
        f.addRow("Sign in with:", self.auth)
        self.user = QLineEdit(c["username"])
        f.addRow("SQL login:", self.user)
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText("(saved)" if c["password"] else "")
        f.addRow("Password:", self.pw)
        self.maxrows = QSpinBox()
        self.maxrows.setRange(10, 5000)
        self.maxrows.setValue(int(c["max_rows"]))
        f.addRow("Rows to show:", self.maxrows)
        self.enc = QCheckBox("Encrypt the connection (trust the server certificate)")
        self.enc.setChecked(bool(c["encrypt"]))
        f.addRow("", self.enc)
        lay.addWidget(g)
        tb = QPushButton("Test connection")
        tb.clicked.connect(self._test)
        lay.addWidget(tb)
        lay.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _collect(self):
        from ..uploader import protect
        c = self.db.get(self.settings)
        c.update(enabled=self.on.isChecked(), server=self.server.text().strip(), database=self.database.text().strip(),
                 auth=self.auth.currentData(), username=self.user.text().strip(), max_rows=self.maxrows.value(),
                 encrypt=self.enc.isChecked(), trust_cert=True)
        if self.pw.text():
            c["password"] = protect(self.pw.text())
        return c

    def _test(self):
        trial = dict(self.settings)
        trial["sam_connection"] = dict(self._collect(), enabled=True)
        try:
            QMessageBox.information(self, "Test connection", self.db.test(trial))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Test connection", f"Could not connect:\n{e}")

    def _save(self):
        self.settings["sam_connection"] = self._collect()
        paths.save_settings(self.settings)
        self.accept()


# ============================================================================ Backup / restore
class RestoreDialog(QDialog):
    def __init__(self, path: str, manifest: dict, parent=None):
        super().__init__(parent)
        from ..backup import PARTS
        self.setWindowTitle("Restore settings")
        lay = QVBoxLayout(self)
        lay.addWidget(label(f"Backup from <b>{manifest.get('computer', '?')}</b>, "
                            f"{manifest.get('created', '').replace('T', ' ')} (app {manifest.get('app_version', '?')})."
                            "<br>Choose what to restore. Passwords are never in a backup - re-enter them afterwards "
                            "(passwords already on this PC are kept for matching profiles).", "subtitle"))
        self.boxes = {}
        for k, (lab, _keys) in PARTS.items():
            cb = QCheckBox(lab)
            cb.setChecked(k != "queries" or manifest.get("include_queries", False))
            cb.setEnabled(k != "queries" or manifest.get("include_queries", False))
            lay.addWidget(cb)
            self.boxes[k] = cb
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Restore")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def parts(self) -> set:
        return {k for k, cb in self.boxes.items() if cb.isChecked()}


# ============================================================================ Districts
class DistrictsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        from .. import districts
        self.ds = districts
        self.settings = settings
        self.setWindowTitle("Manage districts")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Support more than one district from this PC. Each district keeps its own District "
                            "Settings, schools and codes, uploads and schedules, alerts, report emails, privacy "
                            "register, SAM connection, change log and saved queries. Table lists, templates and "
                            "packages are shared. Switch with the District box on the toolbar.", "subtitle"))
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        br = QHBoxLayout()
        for txt, fn in (("Add district...", self._add), ("Rename...", self._rename), ("Remove", self._remove)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            br.addWidget(b)
        br.addStretch()
        lay.addLayout(br)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        lay.addWidget(close)
        self._fill()

    def _fill(self):
        self.list.clear()
        cur = paths.active_district()
        for d in self.ds.list_districts():
            it = QListWidgetItem(d["name"] + ("   (current)" if d["id"] == cur else ""))
            it.setData(Qt.UserRole, d["id"])
            self.list.addItem(it)

    def _sel(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _add(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add district")
        f = QFormLayout(dlg)
        name = QLineEdit()
        name.setPlaceholderText("e.g. Pearl River County School District")
        f.addRow("District name:", name)
        boxes = {}
        for k, t in self.ds.COPYABLE.items():
            cb = QCheckBox(f"Copy {t} from {paths.district_name()}")
            boxes[k] = cb
            f.addRow("", cb)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        if dlg.exec() and name.text().strip():
            self.ds.add_district(name.text().strip(), self.settings, [k for k, b in boxes.items() if b.isChecked()])
            self._fill()

    def _rename(self):
        from PySide6.QtWidgets import QInputDialog
        did = self._sel()
        if not did:
            return
        new, ok = QInputDialog.getText(self, "Rename district", "Name:", text=paths.district_name(did))
        if ok and new.strip():
            self.ds.rename_district(did, new)
            self._fill()

    def _remove(self):
        did = self._sel()
        if not did:
            return
        if did == paths.active_district():
            QMessageBox.information(self, "Remove", "Switch to another district before removing this one.")
            return
        if QMessageBox.question(self, "Remove", f"Remove {paths.district_name(did)}? Its settings are moved to a "
                                "'_removed' folder, not deleted. Remove its Windows schedules first.") \
                == QMessageBox.Yes:
            try:
                self.ds.delete_district(did)
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Remove", str(e))
            self._fill()


# ============================================================================ Vendor sign-off
class SignoffDialog(QDialog):
    def __init__(self, settings: dict, platform: dict, parent=None):
        super().__init__(parent)
        from .. import signoff
        self.so = signoff
        self.settings = settings
        self.pid = platform["id"]
        e = signoff.entry(settings, self.pid)
        self.setWindowTitle(f"Vendor sign-off - {platform['name']}")
        self.resize(520, 380)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Record when you sent the vendor a sample of these files and when they confirmed the "
                            "layout works. It shows on the exports page and in the health report.", "subtitle"))
        f = QFormLayout()
        self.dates = {}
        for key, cap in (("sample_sent", "Sample sent on:"), ("approved", "Vendor approved on:")):
            row = QHBoxLayout()
            on = QCheckBox()
            de = QDateEdit()
            de.setCalendarPopup(True)
            de.setDisplayFormat("MM/dd/yyyy")
            de.setDate(QDate.fromString(e[key], "yyyy-MM-dd") if e[key] else QDate.currentDate())
            on.setChecked(bool(e[key]))
            de.setEnabled(bool(e[key]))
            on.toggled.connect(de.setEnabled)
            row.addWidget(on)
            row.addWidget(de)
            row.addStretch()
            w = QWidget()
            w.setLayout(row)
            f.addRow(cap, w)
            self.dates[key] = (on, de)
        self.contact = QLineEdit(e["contact"])
        self.contact.setPlaceholderText("Vendor contact / ticket number")
        f.addRow("Contact:", self.contact)
        self.notes = QPlainTextEdit(e["notes"])
        self.notes.setPlaceholderText("Changes the vendor asked for (e.g. 'rename Grade to grade_level')")
        f.addRow("Notes:", self.notes)
        lay.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _save(self):
        vals = {k: (de.date().toString("yyyy-MM-dd") if on.isChecked() else "") for k, (on, de) in self.dates.items()}
        self.so.save(self.settings, self.pid, contact=self.contact.text().strip(),
                     notes=self.notes.toPlainText().strip(), **vals)
        paths.save_settings(self.settings)
        self.accept()


# ============================================================================ Health report
class HealthDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QTime
        from PySide6.QtWidgets import QSpinBox, QTextBrowser, QTimeEdit
        from .. import health
        self.hl = health
        self.settings = settings
        h = health.get(settings)
        self.setWindowTitle("District health report")
        self.resize(980, 760)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.to = QLineEdit(h["to"])
        self.to.setPlaceholderText("technology director, data coordinator...")
        f.addRow("Email to:", self.to)
        cr = QHBoxLayout()
        self.folder = QLineEdit(h["cleanup_folder"])
        self.folder.setPlaceholderText("Folder where the CAC Agent saves the Data cleanup reports (optional)")
        fb = QPushButton("Browse...")
        fb.clicked.connect(self._browse)
        cr.addWidget(self.folder, 1)
        cr.addWidget(fb)
        cw = QWidget()
        cw.setLayout(cr)
        f.addRow("Cleanup reports:", cw)
        sr = QHBoxLayout()
        self.day = QSpinBox()
        self.day.setRange(1, 28)
        self.day.setValue(int(h["day"] or 1))
        self.time = QTimeEdit()
        self.time.setDisplayFormat("HH:mm")
        self.time.setTime(QTime.fromString(h["time"] or "07:00", "HH:mm"))
        sr.addWidget(QLabel("Monthly on day"))
        sr.addWidget(self.day)
        sr.addWidget(QLabel("at"))
        sr.addWidget(self.time)
        sr.addStretch()
        sw = QWidget()
        sw.setLayout(sr)
        f.addRow("Schedule:", sw)
        lay.addLayout(f)
        self.view = QTextBrowser()
        lay.addWidget(self.view, 1)
        br = QHBoxLayout()
        for txt, fn in (("Refresh", self._refresh), ("Save as HTML...", self._save_html), ("Email now", self._send),
                        ("Schedule monthly in Windows", self._schedule)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            br.addWidget(b)
        br.addStretch()
        cl = QPushButton("Close")
        cl.clicked.connect(self.accept)
        br.addWidget(cl)
        lay.addLayout(br)
        self._refresh()

    def _store(self):
        self.settings["health"] = {"to": self.to.text().strip(), "day": self.day.value(),
                                   "time": self.time.time().toString("HH:mm"),
                                   "cleanup_folder": self.folder.text().strip()}
        paths.save_settings(self.settings)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Cleanup reports folder", self.folder.text())
        if d:
            self.folder.setText(d.replace("/", "\\"))
            self._refresh()

    def _refresh(self):
        self._store()
        self.view.setHtml(self.hl.html_report(self.settings))

    def _save_html(self):
        self._store()
        fn, _ = QFileDialog.getSaveFileName(self, "Save health report", f"health report {dt.date.today():%Y-%m-%d}.html",
                                            "Web page (*.html)")
        if fn:
            with open(fn, "w", encoding="utf-8") as fh:
                fh.write(self.hl.html_report(self.settings))

    def _send(self):
        self._store()
        try:
            QMessageBox.information(self, "Health report", self.hl.send(self.settings))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Health report", str(e))

    def _schedule(self):
        self._store()
        try:
            self.hl.schedule(self.settings)
            QMessageBox.information(self, "Health report", f"Scheduled monthly on day {self.day.value()} at "
                                    f"{self.time.time().toString('HH:mm')}.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Health report", str(e))


# ============================================================================ SAM setup check
class SamCheckDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QTreeWidget
        from .. import samcheck, samdb
        self.sc = samcheck
        self.settings = settings
        self.result = None
        self.setWindowTitle("SAM setup check")
        self.resize(980, 700)
        lay = QVBoxLayout(self)
        lay.addWidget(label(
            "Checks the things every export package assumes about your SAM data - owner type codes, the enrolled "
            "code, live schedules, primary school and contact flags, roster withdrawals, homerooms, staff flags, "
            "withdrawal codes and the values used in program flags. <b>Step 1:</b> Export to a platform &gt; Tools &gt; "
            "<b>SAM setup check</b> &gt; Save package, run the 7 queries in SAM and save each result as CSV with the "
            "file name shown. <b>Step 2:</b> choose that folder here. The results are codes and counts only.",
            "subtitle"))
        row = QHBoxLayout()
        self.folder = QLineEdit((settings.get("sam_check") or {}).get("folder", ""))
        self.folder.setPlaceholderText("Folder with check_*.csv")
        fb = QPushButton("Browse...")
        fb.clicked.connect(self._browse)
        rb = QPushButton("Read results")
        rb.setObjectName("primary")
        rb.clicked.connect(self._read)
        row.addWidget(self.folder, 1)
        row.addWidget(fb)
        row.addWidget(rb)
        if samdb.enabled(settings):
            lb = QPushButton("Run in SAM (read-only)")
            lb.clicked.connect(self._live)
            row.addWidget(lb)
        lay.addLayout(row)
        self.summary = label("", "")
        self.summary.setTextFormat(Qt.RichText)
        lay.addWidget(self.summary)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Result", "Area", "Finding"])
        self.tree.setColumnWidth(0, 90)
        self.tree.setColumnWidth(1, 130)
        self.tree.setWordWrap(True)
        lay.addWidget(self.tree, 1)
        br = QHBoxLayout()
        self.apply_btn = QPushButton("Apply suggested District Settings")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._apply)
        br.addWidget(self.apply_btn)
        sv = QPushButton("Save report...")
        sv.clicked.connect(self._save)
        br.addWidget(sv)
        br.addStretch()
        cl = QPushButton("Close")
        cl.clicked.connect(self.accept)
        br.addWidget(cl)
        lay.addLayout(br)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Folder with the check results", self.folder.text())
        if d:
            self.folder.setText(d.replace("/", "\\"))

    def _read(self):
        try:
            data = self.sc.load_folder(self.folder.text().strip())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "SAM setup check", str(e))
            return
        if not data:
            QMessageBox.information(self, "SAM setup check", "No check_*.csv files were found in that folder.")
            return
        self._show(data)

    def _live(self):
        try:
            data = self.sc.run_live(self.settings)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "SAM setup check", f"Could not run the checks in SAM:\n{e}")
            return
        self._show(data)

    def _show(self, data):
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QTreeWidgetItem
        from .. import district
        self.result = res = self.sc.analyze(data, self.settings)
        self.sc.store_summary(self.settings, res)
        self.settings["sam_check"]["folder"] = self.folder.text().strip()
        paths.save_settings(self.settings)
        colors = {"ok": "#1E7B34", "info": "#1F5FAD", "warn": "#C2410C", "error": "#B42318"}
        self.tree.clear()
        order = {"error": 0, "warn": 1, "info": 2, "ok": 3}
        for f in sorted(res.findings, key=lambda f: order[f.level]):
            it = QTreeWidgetItem([f.level.upper(), f.area, f.message])
            it.setForeground(0, QColor(colors[f.level]))
            it.setToolTip(2, f.message)
            self.tree.addTopLevelItem(it)
        sug = "; ".join(f"{district.LABELS.get(k, k)} = {v}" for k, v in res.suggest.items())
        self.summary.setText(f"<b>{len(res.errors)}</b> problem(s), <b>{len(res.warnings)}</b> to check, "
                             f"{sum(1 for f in res.findings if f.level == 'ok')} OK." +
                             (f"<br>Suggested settings: {sug}" if sug else ""))
        self.apply_btn.setEnabled(bool(res.suggest))

    def _apply(self):
        if not self.result or not self.result.suggest:
            return
        from ..adminpin import require
        if not require(self, self.settings, "district"):
            return
        self.settings.setdefault("district", {}).update(self.result.suggest)
        paths.save_settings(self.settings)
        QMessageBox.information(self, "SAM setup check", "District Settings updated. Re-open any export files you "
                                "already have open so they pick up the new codes.")
        self.apply_btn.setEnabled(False)

    def _save(self):
        if not self.result:
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Save check report", f"SAM setup check {dt.date.today():%Y-%m-%d}.csv",
                                            "CSV (*.csv)")
        if fn:
            import csv
            with open(fn, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["Result", "Area", "Finding"])
                for f in self.result.findings:
                    w.writerow([f.level, f.area, f.message])
