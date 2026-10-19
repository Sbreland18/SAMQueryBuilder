"""'Export to a platform' page."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..exports import load_platforms, missing_settings, override_state, remove_override, save_package
from .widgets import label


class ExportsPage(QWidget):
    open_query = Signal(object, object)     # platform dict, file entry dict
    go_home = Signal()
    edit_district = Signal()
    upload_setup = Signal(object)
    cac_setup = Signal(object)
    build_template = Signal(object)
    signoff = Signal(object)      # platform dict to edit, or None for a new package

    def __init__(self, get_settings):
        super().__init__()
        self.setObjectName("page")
        self.get_settings = get_settings
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 20, 30, 20)
        top = QHBoxLayout()
        top.addWidget(label("Export to a platform", "title"))
        top.addStretch()
        nb = QPushButton("New package from a vendor template...")
        nb.setObjectName("primary")
        nb.setToolTip("Build an export package from any vendor's file layout")
        nb.clicked.connect(lambda: self.build_template.emit(None))
        top.addWidget(nb)
        ib = QPushButton("Import package file...")
        ib.clicked.connect(self._import_pkg)
        top.addWidget(ib)
        ds = QPushButton("District Settings...")
        ds.clicked.connect(self.edit_district)
        top.addWidget(ds)
        hb = QPushButton("Back to start")
        hb.clicked.connect(self.go_home)
        top.addWidget(hb)
        lay.addLayout(top)
        lay.addWidget(label("Ready-made queries that create the exact CSV files each platform expects. Open a file to "
                            "review it with sample data, or save the whole package as SQL files plus step-by-step "
                            "CAC Agent instructions.", "subtitle"))
        row = QHBoxLayout()
        lay.addLayout(row, 1)

        left = QFrame()
        left.setObjectName("card")
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("<b>Platforms</b>"))
        from PySide6.QtWidgets import QLineEdit
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search platforms (e.g. Apple, bus, parents)...")
        self.search.textChanged.connect(lambda _t: self._fill_list())
        ll.addWidget(self.search)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setMinimumWidth(320)
        self.list.currentRowChanged.connect(self._show)
        ll.addWidget(self.list)
        row.addWidget(left, 1)

        right = QFrame()
        right.setObjectName("card")
        rl = QVBoxLayout(right)
        self.title = QLabel()
        self.title.setStyleSheet("font-size:14pt;font-weight:600")
        rl.addWidget(self.title)
        self.info = label("")
        self.info.setTextFormat(Qt.RichText)
        self.info.setOpenExternalLinks(True)
        rl.addWidget(self.info)
        self.files = QTableWidget(0, 3)
        self.files.setHorizontalHeaderLabels(["File", "Columns", "Notes"])
        self.files.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.files.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.files.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.files.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.files.setSelectionMode(QAbstractItemView.SingleSelection)
        self.files.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.files.verticalHeader().setVisible(False)
        self.files.cellDoubleClicked.connect(lambda r, _c: self._open(r))
        rl.addWidget(self.files, 1)
        br = QHBoxLayout()
        ob = QPushButton("Open selected file query")
        ob.clicked.connect(lambda: self._open(self.files.currentRow()))
        br.addWidget(ob)
        sb = QPushButton("Save package (SQL files + setup guide)...")
        sb.setObjectName("primary")
        sb.clicked.connect(self._save)
        br.addWidget(sb)
        cb = QPushButton("Check exported files...")
        cb.setToolTip("Point at the folder where SAM / the CAC Agent saved this platform's CSV files and check them "
                      "before uploading")
        cb.clicked.connect(self._check)
        br.addWidget(cb)
        wb = QPushButton("CAC Agent walkthrough...")
        wb.setToolTip("Step-by-step setup of every file in SAM's CAC Agent, with copy buttons")
        wb.clicked.connect(lambda: self.cac_setup.emit(self._cur()))
        br.addWidget(wb)
        ub = QPushButton("Upload setup...")
        ub.setToolTip("Zip + upload these files to the vendor's SFTP automatically")
        ub.clicked.connect(lambda: self.upload_setup.emit(self._cur()))
        br.addWidget(ub)
        br.addStretch()
        rl.addLayout(br)
        br = QHBoxLayout()
        so = QPushButton("Vendor sign-off...")
        so.setToolTip("Record when you sent the vendor a sample and when they approved the files")
        so.clicked.connect(lambda: self.signoff.emit(self._cur()))
        br.addWidget(so)
        self.edit_pkg = QPushButton("Edit my package...")
        self.edit_pkg.clicked.connect(lambda: self.build_template.emit(self._cur()))
        br.addWidget(self.edit_pkg)
        self.copy_pkg = QPushButton("Copy to My packages")
        self.copy_pkg.setToolTip("Shared packages are read-only - copy one to change it for your district")
        self.copy_pkg.clicked.connect(self._copy_shared)
        br.addWidget(self.copy_pkg)
        self.del_pkg = QPushButton("Delete my package")
        self.del_pkg.clicked.connect(self._delete_pkg)
        br.addWidget(self.del_pkg)
        rb = QPushButton("Reset to standard")
        rb.setToolTip("Delete your district version of the selected file and use the standard one again")
        rb.clicked.connect(self._reset_override)
        br.addWidget(rb)
        hb2 = QPushButton("History...")
        hb2.setToolTip("Earlier district versions of the selected file - compare and restore")
        hb2.clicked.connect(self._history)
        br.addWidget(hb2)
        mb = QPushButton("Data minimization...")
        mb.setToolTip("Which sensitive columns this vendor gets and whether its layout needs them - blank the "
                      "optional ones for your district")
        mb.clicked.connect(self._minimize)
        br.addWidget(mb)
        self.school_btn = QPushButton("Schools: all")
        self.school_btn.setToolTip("Limit every file in this package to some schools (load your school list under "
                                   "File > SAM Codes & Schools)")
        self.school_btn.clicked.connect(self._schools)
        br.addWidget(self.school_btn)
        self.spec_btn = QPushButton("Open vendor specification")
        self.spec_btn.clicked.connect(self._spec)
        br.addWidget(self.spec_btn)
        br.addStretch()
        rl.addLayout(br)
        rl.addWidget(label("IDs are consistent inside each package (e.g. the section id in sections.csv matches "
                           "enrollments.csv). To change a file for your district, open it, edit it and use File > Save as district "
                           "version - your version survives updates.", "hint"))
        row.addWidget(right, 3)
        self.platforms = []
        self.reload()

    def reload(self):
        cur = self._cur() if getattr(self, "platforms", None) else None
        self.platforms = load_platforms()
        self._fill_list(cur["id"] if cur else None)

    def _fill_list(self, select_id: str | None = None):
        from PySide6.QtGui import QFont
        flt = self.search.text().lower().strip() if hasattr(self, "search") else ""
        self.list.blockSignals(True)
        self.list.clear()
        cats: dict[str, list[int]] = {}
        for i, p in enumerate(self.platforms):
            text = (p["name"] + " " + p.get("works_with", "") + " " + p.get("category", "")).lower()
            if flt and flt not in text:
                continue
            cats.setdefault(p.get("category") or "Other", []).append(i)
        first = None
        for cat, idxs in cats.items():
            h = QListWidgetItem(cat.upper())
            f = QFont()
            f.setBold(True)
            f.setPointSize(8)
            h.setFont(f)
            h.setFlags(Qt.NoItemFlags)
            h.setForeground(Qt.darkGray)
            self.list.addItem(h)
            for i in idxs:
                p = self.platforms[i]
                it = QListWidgetItem(f"{p['name']}\n   {len(p['files'])} file(s)")
                it.setToolTip(p.get("works_with", ""))
                it.setData(Qt.UserRole, i)
                self.list.addItem(it)
                if first is None or p["id"] == select_id:
                    first = self.list.count() - 1
        self.list.blockSignals(False)
        if first is not None:
            self.list.setCurrentRow(first)
        else:   # nothing matches the search: don't leave the previous package on screen
            self.title.setText("No packages match your search")
            self.info.setText("")
            self.files.setRowCount(0)

    def select_platform(self, pid: str):
        if hasattr(self, "search"):
            self.search.clear()
        self._fill_list(pid)

    def _cur(self):
        it = self.list.currentItem()
        i = it.data(Qt.UserRole) if it else None
        return self.platforms[i] if i is not None and 0 <= i < len(self.platforms) else None

    def _show(self, _r):
        p = self._cur()
        if not p:
            return
        self.title.setText(p["name"])
        html = (f"<p><b>Works with:</b> {p.get('works_with', '')}</p><p>{p.get('description', '')}</p>"
                f"<p><b>Deliver by:</b> {p.get('delivery', '')}</p>")
        need = missing_settings(p, self.get_settings())
        if need:
            html += ("<p style='color:#9A6700'><b>Needs District Settings:</b> " + ", ".join(need) + "</p>")
        if p.get("confirm_with_vendor"):
            html += f"<p style='color:#B42318'><b>Confirm with the vendor:</b> {p['confirm_with_vendor']}</p>"
        html += self._signoff_html(p)
        html += self._privacy_html(p)
        self.info.setText(html)
        self.spec_btn.setEnabled(bool(p.get("spec_url")))
        self.edit_pkg.setVisible(bool(p.get("custom")))
        self.del_pkg.setVisible(bool(p.get("custom")))
        self.copy_pkg.setVisible(bool(p.get("shared")))
        self._school_label()
        self.files.setRowCount(0)
        for i, fe in enumerate(p["files"]):
            q = fe["query"]
            heads = [c.get("heading", "") for c in q.get("columns", [])]
            self.files.insertRow(i)
            self.files.setItem(i, 0, QTableWidgetItem(fe["file"]))
            it = QTableWidgetItem(", ".join(heads))
            it.setToolTip("\n".join(heads))
            self.files.setItem(i, 1, it)
            parts = q.get("union_parts", [])
            note = fe.get("note") or (f"combines {1 + len(parts)} parts" if parts else "")
            st = override_state(p, fe)
            if st:
                note = ("DISTRICT VERSION" if st == "custom" else "DISTRICT VERSION - standard updated, review") + (
                    f" - {note}" if note else "")
            ni = QTableWidgetItem(note)
            if st:
                ni.setForeground(Qt.darkBlue if st == "custom" else Qt.darkRed)
                ni.setToolTip("You saved your own version of this file. It is used for opening, saving the package "
                              "and the CAC Agent walkthrough. Use 'Reset to standard' to go back.")
            self.files.setItem(i, 2, ni)
        if p["files"]:
            self.files.selectRow(0)

    def _signoff_html(self, p) -> str:
        from ..signoff import status
        txt, color = status(self.get_settings(), p["id"])
        return f"<p><b>Vendor sign-off:</b> <span style='color:{color}'>{txt}</span></p>"

    def _privacy_html(self, p) -> str:
        from ..privacy import LEVELS, report
        from ..query_model import QueryDef
        found: dict[str, set] = {}
        for fe in p["files"]:
            try:
                r = report(QueryDef.from_dict(fe["query"]))
            except Exception:
                continue
            for lvl, _h, _s in r["shown"]:
                found.setdefault(lvl, set()).add(fe["file"])
        if not found:
            return "<p style='color:#1E7B34'><b>Data shared:</b> names, IDs, grades and schools only.</p>"
        out = "<p><b>Data shared:</b><br>"
        for lvl, (name, color, _tip) in LEVELS.items():
            if lvl in found:
                out += f"<span style='color:{color}'>{name}</span> in {', '.join(sorted(found[lvl]))}<br>"
        return out + "</p>"

    def _open(self, r):
        p = self._cur()
        if p and 0 <= r < len(p["files"]):
            self.open_query.emit(p, p["files"][r])

    def _import_pkg(self):
        from ..template_builder import import_package
        fn, _ = QFileDialog.getOpenFileName(self, "Import package file", "", "Package files (*.samqb-package *.json)")
        if not fn:
            return
        try:
            plat = import_package(fn)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Import package", str(e))
            return
        self.reload()
        self.select_platform(plat["id"])
        QMessageBox.information(self, "Import package", f"Imported '{plat['name']}' into My packages.")

    def _copy_shared(self):
        from ..shared_library import copy_to_mine
        p = self._cur()
        if p and p.get("shared"):
            mine = copy_to_mine(p)
            self.reload()
            self.select_platform(mine["id"])
            QMessageBox.information(self, "Copy to My packages", f"Copied to My packages as '{mine['name']}'. "
                                    "Use Edit my package to change it.")

    def _delete_pkg(self):
        from ..template_builder import delete_custom
        p = self._cur()
        if p and p.get("custom") and QMessageBox.question(
                self, "Delete package", f"Delete your package '{p['name']}'? (Export it first if you may need it.)") \
                == QMessageBox.Yes:
            delete_custom(p["id"])
            self.reload()

    def _history(self):
        from ..exports import override_path
        from .more_tools import HistoryDialog
        p = self._cur()
        r = self.files.currentRow()
        if not p or not (0 <= r < len(p["files"])):
            QMessageBox.information(self, "History", "Select a file first.")
            return
        fe = p["files"][r]
        HistoryDialog(str(override_path(p["id"], fe["file"])), f"{p['name']} - {fe['file']}", self).exec()
        self._show(None)

    def _minimize(self):
        from .more_tools import MinimizeDialog
        p = self._cur()
        if p:
            MinimizeDialog(p, self.get_settings(), self).exec()
            self._show(None)

    def _reset_override(self):
        p = self._cur()
        r = self.files.currentRow()
        if not p or not (0 <= r < len(p["files"])):
            return
        fe = p["files"][r]
        if not override_state(p, fe):
            QMessageBox.information(self, "Reset to standard", f"{fe['file']} is already the standard version.")
            return
        if QMessageBox.question(self, "Reset to standard",
                                f"Delete your district version of {fe['file']} and use the standard file?") \
                == QMessageBox.Yes:
            remove_override(p, fe)
            self._show(None)

    def _school_label(self):
        from ..exports import school_ids
        p = self._cur()
        ids = school_ids(p, self.get_settings()) if p else []
        names = {str(s.get("id")): s.get("name", "") for s in self.get_settings().get("schools", [])}
        if not ids:
            self.school_btn.setText("Schools: all")
        elif len(ids) == 1:
            self.school_btn.setText(f"School: {names.get(ids[0]) or ids[0]}")
        else:
            self.school_btn.setText(f"Schools: {len(ids)} chosen")

    def _schools(self):
        from .. import paths
        from ..codes import options
        from ..exports import school_ids
        from .widgets import choose_codes
        p = self._cur()
        if not p:
            return
        settings = self.get_settings()
        opts = options(settings, "schools")
        if not opts:
            QMessageBox.information(self, "Schools", "Load your school list first: File > SAM Codes & Schools "
                                    "(type them in, paste from Excel, or import school_list.csv from 'Find your "
                                    "SAM codes').")
            return
        chosen = choose_codes(self, f"Limit {p['name']} to these schools (none = all schools)", opts,
                              school_ids(p, settings), multi=True)
        if chosen is None:
            return
        settings.setdefault("export_schools", {})[p["id"]] = list(chosen)
        paths.save_settings(settings)
        self._school_label()

    def _check(self):
        p = self._cur()
        if not p:
            return
        if not p.get("rules"):
            QMessageBox.information(self, "Check files", "There are no checking rules for this package yet.")
            return
        folder = QFileDialog.getExistingDirectory(self, f"Folder with the {p['name']} CSV files")
        if not folder:
            return
        from ..validator import check_folder
        from .check_dialog import CheckDialog
        CheckDialog(check_folder(p, folder), self).exec()

    def _spec(self):
        p = self._cur()
        if p and p.get("spec_url"):
            QDesktopServices.openUrl(QUrl(p["spec_url"]))

    def _save(self):
        p = self._cur()
        if not p:
            return
        missing = missing_settings(p, self.get_settings())
        if missing:
            QMessageBox.information(self, "District Settings needed",
                                    "Fill in these District Settings first:\n\n- " + "\n- ".join(missing))
            self.edit_district.emit()
            if missing_settings(p, self.get_settings()):
                return
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for the export package")
        if not folder:
            return
        try:
            files = save_package(p, self.get_settings(), folder)
        except Exception as e:
            QMessageBox.critical(self, "Save package", f"Could not save the package:\n{e}")
            return
        QMessageBox.information(self, "Package saved",
                                f"Saved {len(files)} files to:\n{files[0].parent}\n\n"
                                "Open 'SETUP - read me.txt' for the CAC Agent steps.")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(files[0].parent)))
