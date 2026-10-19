"""First-run setup wizard: district basics -> SAM codes and schools -> vendors used -> alerts -> next steps."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWizard, QWizardPage)
from PySide6.QtCore import Qt

from .. import district, paths
from ..app_config import APP_NAME


def _lbl(text):
    l = QLabel(text)
    l.setWordWrap(True)
    l.setTextFormat(Qt.RichText)
    return l


class SetupWizard(QWizard):
    open_codes = Signal()
    open_alerts = Signal()

    def __init__(self, settings: dict, parent=None, get_settings=None):
        super().__init__(parent)
        self.get_settings = get_settings or (lambda: settings)
        self.setWindowTitle(f"{APP_NAME} - setup")
        from .style import is_dark
        self.setWizardStyle(QWizard.ClassicStyle if is_dark() else QWizard.ModernStyle)
        self.resize(760, 600)
        ds = district.get(self.get_settings())

        # 1 welcome
        p1 = QWizardPage()
        p1.setTitle("Welcome")
        l1 = QVBoxLayout(p1)
        l1.addWidget(_lbl(
            f"<p>This sets up <b>{APP_NAME}</b> for <b>{paths.district_name()}</b> in a few minutes:</p><ol>"
            "<li>your district's email domains and username patterns,</li>"
            "<li>your real SAM codes and your schools with their SchoolIDs,</li>"
            "<li>the vendors you send files to,</li><li>failure alerts,</li></ol>"
            "<p>You can change everything later (File &gt; District Settings, File &gt; SAM Codes &amp; Schools, "
            "Tools menu) and run this again from Help &gt; Setup wizard.</p>"))
        self.addPage(p1)

        # 2 district basics
        p2 = QWizardPage()
        p2.setTitle("Your district")
        p2.setSubTitle("Used by every export package to build emails, usernames and term names.")
        f2 = QFormLayout(p2)
        self.d_name = QLineEdit(ds["district_name"])
        f2.addRow("District name:", self.d_name)
        self.d_staff = QLineEdit(ds["staff_email_domain"])
        f2.addRow("Staff email domain:", self.d_staff)
        self.d_stu = QLineEdit(ds["student_email_domain"])
        f2.addRow("Student email domain:", self.d_stu)
        from .widgets import make_pattern_edit
        self.d_spat = make_pattern_edit(ds["student_username_pattern"], staff=False)
        self.d_tpat = make_pattern_edit(ds["staff_username_pattern"], staff=True)
        self.d_semail = make_pattern_edit(ds.get("student_email_pattern", ""), staff=False, allow_blank=True)
        self.d_temail = make_pattern_edit(ds.get("staff_email_pattern", ""), staff=True, allow_blank=True)
        f2.addRow("Student usernames:", self.d_spat)
        f2.addRow("Student email name:", self.d_semail)
        f2.addRow("Staff usernames:", self.d_tpat)
        f2.addRow("Staff email name:", self.d_temail)
        self.d_dups = {}
        for key, lbl in (("student_duplicates", "Duplicate student names:"),
                         ("staff_duplicates", "Duplicate staff names:")):
            cb = QComboBox()
            for val, text in district.DUPLICATE_CHOICES:
                cb.addItem(text, val)
            cb.setCurrentIndex(max(0, cb.findData(str(ds.get(key, "")))))
            self.d_dups[key] = cb
            f2.addRow(lbl, cb)
        self.d_year = QLineEdit(str(ds["school_year"]))
        f2.addRow("School year (end year):", self.d_year)
        self.addPage(p2)

        # 3 codes and schools
        p3 = QWizardPage()
        p3.setTitle("SAM codes and schools")
        p3.setSubTitle("Load your real code lists and your schools (SchoolID + name) so filters and packages use them.")
        l3 = QVBoxLayout(p3)
        from .. import codes as C
        l3.addWidget(_lbl(
            "<ol><li>Click <b>Copy the all-in-one query</b>. In SAM open <i>Ad Hoc Query &gt; Query</i>, paste it, "
            f"<i>Run Query</i> and save the results as <b>{C.ALL_IN_ONE_FILE}</b>.</li>"
            "<li>Click <b>Import codes and schools</b> &gt; <b>Import CSV files</b> and choose that file - or type / "
            "paste your schools there.</li></ol><p>If SAM shows an error, <b>Save all queries</b> gives you one "
            "query per list instead (the read-me lists the file names). This also fills in the enrolled-student "
            "code and owner-type codes that many packages need.</p>"))
        b1 = QPushButton("1. Copy the all-in-one query")
        b1.setObjectName("primary")
        b1.clicked.connect(self._copy_all)
        l3.addWidget(b1)
        b1b = QPushButton("Save all queries to a folder...")
        b1b.clicked.connect(self._save_codes_pkg)
        l3.addWidget(b1b)
        b2 = QPushButton("2. Import codes and schools...")
        b2.clicked.connect(lambda: (self.open_codes.emit(), self._codes_status()))
        l3.addWidget(b2)
        self.codes_status = _lbl("")
        l3.addWidget(self.codes_status)
        l3.addStretch()
        self.addPage(p3)

        # 4 vendors
        p4 = QWizardPage()
        p4.setTitle("Vendors you send files to")
        p4.setSubTitle("Ticked vendors are marked 'in use' in the privacy register; the CAC Agent walkthrough and "
                       "upload setup start from them.")
        l4 = QVBoxLayout(p4)
        self.vendors = QListWidget()
        from ..exports import load_platforms
        from ..register import in_use_ids
        used = in_use_ids(self.get_settings())
        last = None
        for p in load_platforms():
            if p.get("kind") == "tool":
                continue
            if p.get("category") != last:
                h = QListWidgetItem(p.get("category", "").upper())
                h.setFlags(Qt.NoItemFlags)
                self.vendors.addItem(h)
                last = p.get("category")
            it = QListWidgetItem(p["name"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if p["id"] in used else Qt.Unchecked)
            it.setData(Qt.UserRole, p["id"])
            self.vendors.addItem(it)
        l4.addWidget(self.vendors)
        self.addPage(p4)

        # 5 alerts
        p5 = QWizardPage()
        p5.setTitle("Alerts")
        p5.setSubTitle("Nightly uploads run with no window - get an email or Teams message when one fails.")
        l5 = QVBoxLayout(p5)
        l5.addWidget(_lbl("Set up the email server (or a Teams / Google Chat webhook) now, or later from Tools &gt; "
                          "Upload alerts."))
        b5 = QPushButton("Set up alerts...")
        b5.clicked.connect(self.open_alerts)
        l5.addWidget(b5)
        l5.addStretch()
        self.addPage(p5)

        # 6 next steps
        p6 = QWizardPage()
        p6.setTitle("You're ready")
        l6 = QVBoxLayout(p6)
        l6.addWidget(_lbl(
            "<p><b>Next steps</b></p><ol><li>Install the CAC Agent on the computer that will receive the files "
            "(<b>Help &gt; CAC Agent setup guide</b>).</li><li>For each vendor: <b>Export to a platform</b> &gt; pick "
            "it &gt; <b>CAC Agent walkthrough</b> to create the nightly jobs in SAM.</li>"
            "<li><b>Check exported files</b> after the first run, then <b>Upload setup</b> to send them nightly.</li>"
            "<li>Vendor not listed? <b>New package from a vendor template</b>.</li>"
            "<li>Optional: <b>Tools &gt; Admin PIN</b> to lock uploads and settings on a shared PC.</li></ol>"))
        self.cac_after = QCheckBox("Open the CAC Agent walkthrough when I click Finish")
        self.cac_after.setChecked(True)
        l6.addWidget(self.cac_after)
        l6.addStretch()
        self.addPage(p6)
        self.currentIdChanged.connect(lambda _i: self._codes_status())

    def _codes_status(self):
        s = self.get_settings()
        n_sch = len(s.get("schools", []))
        n_codes = sum(len(v) for v in (s.get("codes") or {}).values())
        ds = district.get(s)
        miss = [k for k in ("enrolled_status_codes", "owner_type_student", "owner_type_contact", "owner_type_employee")
                if not str(ds.get(k, "")).strip()]
        self.codes_status.setText(
            f"<b>{n_sch}</b> school(s) and <b>{n_codes}</b> code(s) loaded." +
            (f"<br><span style='color:#9A6700'>Still blank in District Settings: "
             f"{', '.join(district.LABELS.get(k, k) for k in miss)}</span>" if miss else
             "<br><span style='color:#1E7B34'>Enrolled and owner-type codes are set.</span>"))

    def _copy_all(self):
        from PySide6.QtWidgets import QApplication
        from .. import codes as C
        QApplication.clipboard().setText(C.all_in_one_sql())
        self.codes_status.setText(f"Query copied - paste it in SAM and save the results as <b>{C.ALL_IN_ONE_FILE}"
                                  "</b>.")

    def _save_codes_pkg(self):
        from .. import codes as C
        folder = QFileDialog.getExistingDirectory(self, "Folder for the code queries")
        if folder:
            files = C.save_helper_queries(self.get_settings(), folder)
            QMessageBox.information(self, "Code queries", f"Saved {len(files)} files to {files[0].parent}. Open "
                                    "'READ ME.txt' for the file names to use.")

    def validateCurrentPage(self):
        bad = [w for w in (self.d_spat, self.d_tpat, self.d_semail, self.d_temail)
               if hasattr(w, "is_valid") and not w.is_valid()]
        if self.currentId() == 1 and bad:
            QMessageBox.warning(self, "Username patterns", "Fix the pattern(s) shown in red first - an invalid "
                                                          "pattern would be replaced with the default.")
            return False
        return super().validateCurrentPage()

    def accept(self):
        if any(hasattr(w, "is_valid") and not w.is_valid()
               for w in (self.d_spat, self.d_tpat, self.d_semail, self.d_temail)):
            QMessageBox.warning(self, "Username patterns", "A username pattern is invalid - go back to 'Your "
                                                          "district' and fix it.")
            return
        s = self.get_settings()
        d = s.setdefault("district", {})
        d.update(district_name=self.d_name.text().strip(), staff_email_domain=self.d_staff.text().strip(),
                 student_email_domain=self.d_stu.text().strip(), student_username_pattern=self.d_spat.value(),
                 staff_username_pattern=self.d_tpat.value(), student_email_pattern=self.d_semail.value(),
                 staff_email_pattern=self.d_temail.value(), school_year=self.d_year.text().strip(),
                 **{k: cb.currentData() for k, cb in self.d_dups.items()})
        reg = s.setdefault("vendor_register", {})
        for i in range(self.vendors.count()):
            it = self.vendors.item(i)
            pid = it.data(Qt.UserRole)
            if pid:
                e = reg.setdefault(pid, {})
                e["in_use"] = it.checkState() == Qt.Checked
        s["setup_done"] = True
        s["district_confirmed"] = True
        super().accept()

    def open_cac_after(self) -> bool:
        return self.cac_after.isChecked()
