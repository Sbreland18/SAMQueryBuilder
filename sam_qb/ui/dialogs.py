"""Help, settings, about and update dialogs + background workers."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                               QMessageBox, QProgressBar, QTextBrowser, QVBoxLayout, QPushButton, QHBoxLayout)

from .. import updater
from ..app_config import APP_NAME, latest_json_url
from ..version import __version__

HELP_HTML = f"""
<h2>{APP_NAME}</h2>
<p>This tool builds SQL for SAM's <b>Ad Hoc Query</b> module without writing SQL by hand.
It follows the same steps as SAM's Report Builder.</p>
<h3>The steps</h3>
<ol>
<li><b>Tables and columns</b> - search for a table or a column name and double-click columns to add them.
Start with <i>Most used tables</i>; Student, Employee and SchoolDef cover most needs.</li>
<li><b>Links</b> - every table must be connected. <i>Suggest links</i> finds the normal SAM path, e.g.
Student &rarr; Schedule Roster &rarr; Course/Section. Students are <u>not</u> linked directly to courses.</li>
<li><b>Format columns</b> - rename headings, remove leading zeros, change case, format dates, or build
custom columns (e.g. first initial + last name + @district.k12.ms.us).</li>
<li><b>Filters</b> - limit rows. Group conditions with ALL (AND) or ANY (OR).</li>
<li><b>Sort and options</b> - order by, distinct rows, row limit, query name.</li>
<li><b>Review</b> - fix any problems listed, then <b>Copy SQL</b> and paste it in SAM.</li>
</ol>
<h3>Query Assistant</h3>
<p><b>Describe a query</b> (Ctrl+D) builds a starting query from plain English, e.g. <i>"seniors with a GPA above
3.5 and their birth dates"</i>. Review the <i>Please check</i> list and the sample results, then open it in the builder. Use <b>Looks right</b> / <b>This isn't right...</b> to save feedback (Help &gt; Export assistant feedback).
The optional AI helper (File &gt; Settings) sends only your description and table/column names to Claude.</p>
<h3>Export to a platform</h3>
<p>Use <b>Export to a platform</b> (toolbar or start page) for ready-made Clever, OneRoster/ClassLink, Microsoft SDS,
Google Workspace, Canvas and NWEA files. Set your email domains and username patterns in <b>File &gt; District Settings</b>
first. <b>Save package</b> writes every query as a .sql file plus a setup guide with the exact CAC Agent file names.
Files that list students and teachers together use <b>combined parts</b>; choose the part to edit from
<i>Editing part</i> at the top of the builder (Query &gt; Add a combined part to make your own).</p>
<p>More packages: ParentSquare, SchoolMessenger, Destiny, food service, transportation, Raptor, Incident IQ, school
photos (PSPA), Xello, Naviance, SchooLinks, MTSS (Panorama / Branching Minds), Frontline Absence, DragonFly and ACT
testing. Use the <b>Schools:</b> button to limit a package to some schools, <b>Check exported files</b> to test the CSVs
SAM wrote, and <b>Upload setup</b> to zip, upload by SFTP and schedule it nightly.</p>
<p>Also: Apple School Manager, SchoolStatus, Active Directory, Microsoft Entra, PBIS Rewards, Hero/LiveSchool, Ellevation,
payments, bus apps, web-filter parent reports, emergency/reunification, athletics, hall pass, credit recovery, Scoir, Adobe
and Zoom. Search the platform list or browse by category. To change a file for your district, open it, edit it and use
<b>File &gt; Save as district version</b> - it survives updates.</p>
<h3>Nightly uploads</h3>
<p><b>Package &amp; Upload</b> sends files by SFTP (password or SSH key), FTPS or to a folder. The <b>safety net</b> holds an
upload when a file is empty or much smaller than last time; <b>Upload anyway once</b> overrides it. Turn on
<b>Tools &gt; Upload alerts</b> (email or Teams/Google Chat/Slack) and watch the <b>Nightly uploads</b> board on the start
page.</p>
<h3>District tools</h3>
<p><b>Tools</b> menu: CAC Agent setup walkthrough (copy buttons for every job), data cleanup reports, vendor privacy
register (agreements and expiry dates, printable report) and the year-end rollover checklist.</p>
<h3>More tools</h3>
<p><b>Account shutoff</b> package: students who left and staff who were terminated, with a Google suspend file and an
AD disable script (preview first). <b>What changed?</b> compares tonight's files with the last good upload.
Upload profiles can <b>PGP-encrypt</b> files. <b>File &gt; Back up / Restore settings</b> moves your setup to another
PC (passwords are never included). <b>Tools &gt; Report emails</b> sends reports on a schedule. The
<b>Results preview</b> tab can show your own CSV file, or real SAM rows when the optional read-only
<b>SAM database connection</b> is turned on. <b>Tools &gt; Change log</b> shows who changed what.</p>
<h3>Dark mode</h3>
<p><b>View &gt; Theme</b> switches between Light, Dark and Match Windows (the app restarts to apply it).</p>
<h3>Usernames and setup check</h3>
<p>District Settings offer many username / email patterns (for example first initial.last = j.smith) or your own
pattern with tokens like <code>{{f}}.{{last}}</code>. <b>Tools &gt; SAM setup check</b> confirms your owner types, enrolled
code and live schedules from 7 small queries and fixes District Settings for you. <b>Help &gt; Quick start guide</b> has
the whole process on one page.</p>
<h3>Your own vendor packages</h3>
<p>Vendor not listed? <b>Export to a platform &gt; New package from a vendor template</b>: open the vendor's template or
paste its header row, check the suggested SAM field for each column and save. It appears under <b>My packages</b> and
works like the built-in ones. Share it with <b>Export package file</b> / <b>Import package file</b>.</p>
<h3>Several districts, setup and the health report</h3>
<p>Use the <b>District</b> box on the toolbar to switch districts (each has its own settings, uploads and schedules).
<b>Help &gt; Setup wizard</b> walks a new district through setup. <b>Vendor sign-off</b> records when a vendor approved
your files. <b>Tools &gt; Admin PIN</b> locks uploads and settings on a shared PC. <b>Tools &gt; District health
report</b> summarizes uploads, data problems, agreements and rollover - email it monthly.</p>
<h3>SAM Codes &amp; Schools</h3>
<p><b>File &gt; SAM Codes &amp; Schools</b> holds your schools (SchoolID + name) and your real code lists. Type them,
paste from Excel, or run the <i>Find your SAM codes</i> package in SAM and import the CSVs. Then Step 4 gets
<b>Schools...</b>, <b>Grades...</b> and <b>Enrolled only</b> quick filters and a <b>Choose...</b> list on coded
columns, and the Query Assistant understands your school names.</p>
<h3>Import a query you already have</h3>
<p><b>Query &gt; Import existing SQL</b> (Ctrl+I) turns SQL from SAM back into the builder steps so you can change it
here. The <i>Check</i> button lists anything kept as exact SQL.</p>
<h3>Privacy check</h3>
<p>Step 6 lists restricted, protected and personal columns in your query. Only share them with vendors whose
data-privacy agreement covers them.</p>
<h3>Sample results</h3>
<p>The <b>Sample results</b> tab at the bottom runs your query against made-up data so you can see the columns, formats, sort order and the effect of filters as you build. The names and values are fake; the real query in SAM may return more, fewer or different rows.</p>
<h3>Link types</h3>
<ul>
<li><b>Inner Link</b> - only rows that match on both sides (most common).</li>
<li><b>Left Link</b> - all rows from the left table, matching rows from the right.</li>
<li><b>Right Link</b> - all rows from the right table, matching rows from the left.</li>
<li><b>Full Outer Link</b> - all rows from both, matched when possible.</li>
</ul>
<h3>Tips</h3>
<ul>
<li>Filter values are the codes stored in SAM (e.g. grade <i>09</i>, not "Ninth Grade"). Add a lookup table
such as <i>lookupADAGrade</i> to show descriptions.</li>
<li>Address and phone link tables hold rows for students, contacts <i>and</i> employees - filter on OwnerType.</li>
<li>Sensitive columns (SSN, DOB) are flagged. Field-level security in SAM still applies when the query runs.</li>
<li>Saved queries (.samq) can be emailed to colleagues and opened with File &gt; Open.</li>
</ul>
<h3>Updates</h3>
<p>The app checks GitHub for a newer version and for new tables/templates at start-up
(Help &gt; Check for updates). Table/template updates install instantly; app updates run the installer.</p>
"""


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("How to use " + APP_NAME)
        self.resize(720, 640)
        lay = QVBoxLayout(self)
        tb = QTextBrowser()
        tb.setHtml(HELP_HTML)
        lay.addWidget(tb)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = settings
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.check = QCheckBox("Check for updates when the app starts")
        self.check.setChecked(settings.get("check_on_start", True))
        form.addRow(self.check)
        self.auto_data = QCheckBox("Install table/template updates automatically")
        self.auto_data.setChecked(settings.get("auto_data_updates", True))
        form.addRow(self.auto_data)
        self.url = QLineEdit(settings.get("update_url", ""))
        self.url.setPlaceholderText(latest_json_url())
        form.addRow("Update URL (latest.json):", self.url)
        from PySide6.QtWidgets import QComboBox
        from ..ai_helper import MODELS
        form.addRow(QLabel("<b>AI Query Assistant (optional)</b>"))
        self.ai_key = QLineEdit(settings.get("ai_api_key", ""))
        self.ai_key.setEchoMode(QLineEdit.Password)
        self.ai_key.setPlaceholderText("sk-ant-...  (from console.anthropic.com)")
        form.addRow("Anthropic API key:", self.ai_key)
        self.ai_model = QComboBox()
        self.ai_model.setEditable(True)
        self.ai_model.addItems(MODELS)
        self.ai_model.setCurrentText(settings.get("ai_model") or MODELS[0])
        form.addRow("Claude model:", self.ai_model)
        self.ai_default = QCheckBox("Use the AI helper by default when a key is set")
        self.ai_default.setChecked(settings.get("ai_default", True))
        form.addRow(self.ai_default)
        lay.addLayout(form)
        lay.addWidget(QLabel("<i>Leave the URL blank to use the default GitHub repository. The API key is stored "
                             "only on this computer; usage is billed to that Anthropic account.</i>"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def values(self):
        s = dict(self.settings)
        s["check_on_start"] = self.check.isChecked()
        s["auto_data_updates"] = self.auto_data.isChecked()
        s["update_url"] = self.url.text().strip()
        s["ai_api_key"] = self.ai_key.text().strip()
        s["ai_model"] = self.ai_model.currentText().strip()
        s["ai_default"] = self.ai_default.isChecked()
        return s


class CheckWorker(QThread):
    done = Signal(object, str)

    def run(self):
        try:
            self.done.emit(updater.check(), "")
        except Exception as e:  # network errors etc.
            self.done.emit(None, str(e))


class TaskWorker(QThread):
    progress = Signal(str, int)
    done = Signal(object, str)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            res = self.fn(*self.args, progress=lambda m, p: self.progress.emit(m, p))
            self.done.emit(res, "")
        except Exception as e:
            self.done.emit(None, str(e))


class UpdateDialog(QDialog):
    """Shows what is new and installs the app and/or data update."""
    data_installed = Signal()

    def __init__(self, info: updater.UpdateInfo, parent=None):
        super().__init__(parent)
        self.info = info
        self.setWindowTitle("Updates available")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        latest = info.latest
        html = ""
        if info.app_available:
            html += (f"<h3>New version {latest.get('version')} (you have {__version__})</h3>"
                     f"<p>{(latest.get('notes') or '').replace(chr(10), '<br>')}</p>")
        if info.data_available:
            d = latest.get("data", {})
            html += (f"<h3>New tables and templates ({d.get('version')})</h3>"
                     f"<p>{(d.get('notes') or '').replace(chr(10), '<br>')}</p>")
        tb = QTextBrowser()
        tb.setHtml(html or "<p>You are up to date.</p>")
        lay.addWidget(tb)
        self.msg = QLabel("")
        lay.addWidget(self.msg)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        row.addStretch()
        if info.data_available:
            b = QPushButton("Get new tables/templates")
            b.clicked.connect(self.install_data)
            row.addWidget(b)
            self.data_btn = b
        if info.app_available and latest.get("installer_url"):
            b2 = QPushButton(f"Install version {latest.get('version')}")
            b2.setObjectName("primary")
            b2.clicked.connect(self.install_app)
            row.addWidget(b2)
            self.app_btn = b2
        close = QPushButton("Later")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        lay.addLayout(row)
        self.worker = None

    def _progress(self, m, p):
        self.msg.setText(m)
        self.bar.setVisible(True)
        self.bar.setValue(p)

    def install_data(self):
        self.worker = TaskWorker(updater.apply_data_update, self.info)
        self.worker.progress.connect(self._progress)
        self.worker.done.connect(self._data_done)
        self.worker.start()

    def _data_done(self, res, err):
        if err:
            self.msg.setText("Data update failed: " + err)
            return
        self.msg.setText("New tables and templates installed.")
        if hasattr(self, "data_btn"):
            self.data_btn.setEnabled(False)
        self.data_installed.emit()

    def install_app(self):
        self.worker = TaskWorker(updater.download_installer, self.info)
        self.worker.progress.connect(self._progress)
        self.worker.done.connect(self._app_done)
        self.worker.start()

    def _app_done(self, path, err):
        if err:
            self.msg.setText("Download failed: " + err)
            return
        self.msg.setText("Starting installer...")
        updater.run_installer(path)
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()


class DistrictDialog(QDialog):
    """District settings used by the platform export queries."""

    def __init__(self, settings: dict, parent=None):
        from PySide6.QtWidgets import QComboBox
        from .. import district
        super().__init__(parent)
        self.setWindowTitle("District Settings")
        self.resize(720, 760)
        self.settings = settings
        ds = district.get(settings)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("These values are filled into the platform export queries when you open them "
                             "(email addresses, usernames, Google OUs, enrolled-student filter)."))
        form = QFormLayout()
        self.w = {}
        for key, label in district.LABELS.items():
            if key.endswith("_pattern"):
                from .widgets import make_pattern_edit
                self.w[key] = make_pattern_edit(ds[key], staff=key.startswith("staff"),
                                                allow_blank=key.endswith("email_pattern"))
            elif key == "student_email_source":
                cb = QComboBox()
                cb.addItem("Build from the student username pattern + domain", "pattern")
                cb.addItem("Use the Email Address stored on the student in SAM", "sam")
                cb.setCurrentIndex(max(0, cb.findData(ds[key])))
                self.w[key] = cb
            elif key.startswith("owner_type_") and settings.get("codes", {}).get("owner_type"):
                cb = QComboBox()
                cb.setEditable(True)
                cb.addItem("")
                for c in settings["codes"]["owner_type"]:
                    cb.addItem(f"{c['code']}  -  {c.get('description', '')} {c.get('table', '')}".strip())
                cur = str(ds[key])
                idx = next((i for i in range(cb.count()) if cb.itemText(i).split("  -  ")[0] == cur), -1)
                if idx >= 0:
                    cb.setCurrentIndex(idx)
                else:
                    cb.setEditText(cur)
                self.w[key] = cb
            else:
                self.w[key] = QLineEdit(str(ds[key]))
            form.addRow(label + ":", self.w[key])
        self.w["enrolled_status_codes"].setPlaceholderText("e.g. E   (run 'Find your SAM codes' to look it up)")
        self.w["district_id"].setPlaceholderText("optional")
        for k in ("owner_type_student", "owner_type_contact", "owner_type_employee"):
            self.w[k].setPlaceholderText("from the OwnerType table - run 'Owner type codes' in Find your SAM codes")
        lay.addLayout(form)
        lay.addWidget(QLabel("<i>Leave 'Enrolled status code(s)' blank to include every student. Separate several "
                             "codes with commas. Changes apply to export queries you open after saving.</i>"))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _ok(self):
        bad = [district_label for district_label, w in self.w.items() if hasattr(w, "is_valid") and not w.is_valid()]
        if bad:
            QMessageBox.warning(self, "District Settings", "Fix the pattern(s) shown in red first.")
            return
        self.accept()

    def values(self):
        s = dict(self.settings)
        d = {}
        for k, w in self.w.items():
            if hasattr(w, "value"):
                d[k] = w.value()
            elif isinstance(w, QLineEdit):
                d[k] = w.text().strip()
            elif w.isEditable():
                d[k] = w.currentText().split("  -  ")[0].strip()
            else:
                d[k] = w.currentData()
        s["district"] = d
        s["district_confirmed"] = True
        return s
