"""Main application window."""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow,
                               QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QStackedWidget, QTabWidget, QToolBar, QComboBox, QInputDialog,
                               QSizePolicy, QVBoxLayout, QWidget)

from .. import paths
from ..app_config import APP_NAME
from ..catalog import Catalog
from ..query_model import QueryDef, generate_sql
from ..version import __version__
from .dialogs import CheckWorker, HelpDialog, SettingsDialog, UpdateDialog, TaskWorker
from .home import HomePage
from .exports_page import ExportsPage
from .sample_view import SampleResults
from .steps import Ctx, FiltersStep, FormatStep, LinksStep, ReviewStep, SortStep, TablesStep
from .widgets import SqlHighlighter
from .. import updater


def load_templates() -> list[dict]:
    try:
        return json.loads(paths.active_data_file("templates.json").read_text(encoding="utf-8")).get("templates", [])
    except Exception:
        return []


class BuilderPage(QWidget):
    def __init__(self, ctx: Ctx, on_change):
        super().__init__()
        self.ctx = ctx
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("steps")
        self.nav.setFixedWidth(215)
        lay.addWidget(self.nav)

        body = QWidget()
        body.setObjectName("page")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.setContentsMargins(16, 10, 16, 0)
        top.addWidget(QLabel("<b>Query name:</b>"))
        self.name = QLineEdit()
        self.name.textEdited.connect(self._name)
        top.addWidget(self.name, 1)
        self.part_lbl = QLabel("<b>Editing part:</b>")
        self.parts_combo = QComboBox()
        self.parts_combo.setMinimumWidth(200)
        self.parts_combo.setToolTip("This query combines several parts (UNION ALL), e.g. students and teachers "
                                    "in one users.csv. Each part needs the same columns in the same order.")
        self.parts_combo.currentIndexChanged.connect(self._switch_part)
        top.addWidget(self.part_lbl)
        top.addWidget(self.parts_combo)
        self.toggle_preview = QPushButton("Hide preview")
        self.toggle_preview.setCheckable(True)
        self.toggle_preview.toggled.connect(self._toggle_preview)
        top.addWidget(self.toggle_preview)
        bl.addLayout(top)

        split = QSplitter(Qt.Vertical)
        self.stack = QStackedWidget()
        self.steps = [TablesStep(ctx), LinksStep(ctx), FormatStep(ctx), FiltersStep(ctx), SortStep(ctx), ReviewStep(ctx)]
        names = ["1  Tables & Columns", "2  Link Tables", "3  Format Columns", "4  Filters", "5  Sort & Options",
                 "6  Review & Copy SQL"]
        for s, n in zip(self.steps, names):
            self.stack.addWidget(s)
            self.nav.addItem(n)
            s.changed.connect(on_change)
        split.addWidget(self.stack)
        # bottom pane: sample results + SQL
        self.bottom = QTabWidget()
        self.sample = SampleResults(get_settings=lambda: ctx.settings)
        self.bottom.addTab(self.sample, "Results preview")
        self.preview = QPlainTextEdit()
        self.preview.setObjectName("sql")
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.NoWrap)
        SqlHighlighter(self.preview.document())
        self.bottom.addTab(self.preview, "SQL")
        self.bottom.currentChanged.connect(lambda _i: self._refresh_sample())
        split.addWidget(self.bottom)
        split.setSizes([520, 280])
        self._sample_stale = True
        self._sample_timer = QTimer(self)
        self._sample_timer.setSingleShot(True)
        self._sample_timer.setInterval(350)
        self._sample_timer.timeout.connect(self._refresh_sample)
        bl.addWidget(split, 1)

        nav = QHBoxLayout()
        nav.setContentsMargins(16, 6, 16, 10)
        self.back = QPushButton("< Back")
        self.back.clicked.connect(lambda: self.go(self.nav.currentRow() - 1))
        self.next = QPushButton("Next >")
        self.next.setObjectName("primary")
        self.next.clicked.connect(lambda: self.go(self.nav.currentRow() + 1))
        nav.addWidget(self.back)
        nav.addStretch()
        nav.addWidget(self.next)
        bl.addLayout(nav)
        lay.addWidget(body, 1)
        self.nav.currentRowChanged.connect(self._show)
        self.nav.setCurrentRow(0)

    def go(self, i):
        if 0 <= i < len(self.steps):
            self.nav.setCurrentRow(i)

    def _show(self, i):
        # entering the Links step with unconnected tables -> suggest automatically
        if i == 1 and len(self.ctx.query.tables) > 1 and not self.ctx.query.links:
            self.steps[1].suggest(quiet=True)
        self.stack.setCurrentIndex(i)
        self.steps[i].refresh()
        # the review step already shows the full SQL, so show the sample results there
        if i == len(self.steps) - 1:
            self.bottom.setCurrentIndex(0)
        self.bottom.setTabVisible(1, i < len(self.steps) - 1)
        self.bottom.setVisible(not self.toggle_preview.isChecked())
        self._refresh_sample()
        self.back.setEnabled(i > 0)
        self.next.setVisible(i < len(self.steps) - 1)

    def _name(self, t):
        self.ctx.root.name = t
        self.steps[-1].changed.emit()

    def _toggle_preview(self, hidden):
        self.bottom.setVisible(not hidden)
        self.toggle_preview.setText("Show preview" if hidden else "Hide preview")
        self._refresh_sample()

    def _refresh_sample(self):
        """Re-run the sample preview only when it is on screen (it is cheap, but not free)."""
        if not self._sample_stale:
            return
        if self.bottom.isHidden() or self.bottom.currentWidget() is not self.sample:
            return
        self._sample_stale = False
        self.sample.show_query(self.ctx.root, self.ctx.catalog)

    def _fill_parts(self):
        root = self.ctx.root
        self.parts_combo.blockSignals(True)
        self.parts_combo.clear()
        self.parts_combo.addItem("1. Main part")
        for i, p in enumerate(root.union_parts, 2):
            self.parts_combo.addItem(f"{i}. {p.name}")
        idx = 0 if self.ctx.query is root else root.union_parts.index(self.ctx.query) + 1
        self.parts_combo.setCurrentIndex(idx)
        self.parts_combo.blockSignals(False)
        multi = bool(root.union_parts)
        self.part_lbl.setVisible(multi)
        self.parts_combo.setVisible(multi)

    def _switch_part(self, i):
        root = self.ctx.root
        self.ctx.query = root if i <= 0 else root.union_parts[i - 1]
        self.steps[self.nav.currentRow()].refresh()

    def add_part(self):
        from ..query_model import QueryDef as _Q
        root = self.ctx.root
        p = _Q(name=f"Part {len(root.union_parts) + 2}")
        root.union_parts.append(p)
        self.ctx.query = p
        self._fill_parts()
        self.go(0)
        self.steps[0].refresh()

    def remove_part(self):
        root = self.ctx.root
        if self.ctx.query is root:
            return False
        root.union_parts.remove(self.ctx.query)
        self.ctx.query = root
        self._fill_parts()
        self.steps[self.nav.currentRow()].refresh()
        return True

    def load(self):
        self.name.setText(self.ctx.root.name)
        self._fill_parts()
        self.nav.setCurrentRow(0)
        self.steps[0].refresh()
        self.update_preview()

    def update_preview(self):
        self.preview.setPlainText(generate_sql(self.ctx.root, header=False))
        self._sample_stale = True
        self._sample_timer.start()
        if self.name.text() != self.ctx.root.name:
            self.name.setText(self.ctx.root.name)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = paths.load_settings()
        self.catalog = Catalog.load()
        self.ctx = Ctx(self.catalog, QueryDef())
        self.ctx.settings = self.settings
        self.path: str | None = None
        self.dirty = False
        self.setWindowTitle(APP_NAME)
        icon = paths.resource_dir() / "assets" / "app.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1320, 860)

        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        self.banner_text = QLabel("")
        bl.addWidget(self.banner_text, 1)
        self.banner_btn = QPushButton("View update")
        self.banner_btn.setObjectName("primary")
        self.banner_btn.clicked.connect(self.show_update_dialog)
        bl.addWidget(self.banner_btn)
        hide = QPushButton("Dismiss")
        hide.clicked.connect(lambda: self.banner.setVisible(False))
        bl.addWidget(hide)
        self.banner.setVisible(False)
        cl.addWidget(self.banner)

        self.pages = QStackedWidget()
        self.home = HomePage()
        self.home.new_query.connect(self.new_query)
        self.home.open_template.connect(self.open_template)
        self.home.open_file.connect(self.open_path)
        self.home.browse.connect(self.open_dialog)
        self.builder = BuilderPage(self.ctx, self.on_change)
        self.builder.steps[-1].request_save.connect(self.save)
        self.exports_page = ExportsPage(lambda: self.settings)
        self.exports_page.open_query.connect(self.open_export)
        self.exports_page.go_home.connect(self.go_home)
        self.exports_page.edit_district.connect(self.district_settings)
        self.exports_page.upload_setup.connect(self.upload_dialog)
        self.exports_page.cac_setup.connect(lambda p: self.open_tool("cac", p))
        self.exports_page.build_template.connect(self.template_builder)
        self.exports_page.signoff.connect(lambda p: self.open_tool("signoff", p))
        self.home.exports.connect(lambda: self.pages.setCurrentWidget(self.exports_page))
        self.home.assistant.connect(self.open_assistant)
        self.home.import_sql.connect(self.import_sql)
        self.home.open_uploads.connect(lambda: self.upload_dialog(None))
        self.home.open_tool.connect(self.open_tool)
        self.pages.addWidget(self.home)
        self.pages.addWidget(self.builder)
        self.pages.addWidget(self.exports_page)
        cl.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self._build_actions()
        self.home.set_templates(load_templates())
        self.home.refresh_saved()
        self.export_origin = None
        self.refresh_status_board()
        self._status()
        self.update_info = None
        self._checker = None
        if self.settings.get("check_on_start", True):
            QTimer.singleShot(1500, lambda: self.check_updates(silent=True))

    # ------------------------------------------------------------------ actions / menus
    def _build_actions(self):
        def act(text, slot, shortcut=None, tip=None):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            if tip:
                a.setStatusTip(tip)
            return a

        self.a_home = act("Home", self.go_home, tip="Back to the start page")
        self.a_new = act("New", self.new_query, "Ctrl+N")
        self.a_open = act("Open...", self.open_dialog, "Ctrl+O")
        self.a_save = act("Save", self.save, "Ctrl+S")
        self.a_save_as = act("Save As...", self.save_as, "Ctrl+Shift+S")
        self.a_copy = act("Copy SQL", self.copy_sql, "Ctrl+Shift+C")
        self.a_dup = act("Duplicate as new query", self.duplicate)
        self.a_help = act("How to use", lambda: HelpDialog(self).exec(), "F1")
        self.a_update = act("Check for updates", lambda: self.check_updates(silent=False))
        self.a_settings = act("Settings...", self.open_settings)
        self.a_district = act("District Settings...", self.district_settings)
        self.a_codes = act("SAM Codes && Schools...", self.codes_dialog)
        self.a_upload = act("Package && Upload...", lambda: self.upload_dialog(None))
        self.a_import = act("Import existing SQL...", self.import_sql, "Ctrl+I")
        self.a_district_version = act("Save as district version of this export file", self.save_district_version,
                                      tip="Keep your changes to a platform export file; used for packages and "
                                          "survives updates")
        self.a_district_version.setEnabled(False)
        self.a_assist = act("Describe a query...", self.open_assistant, "Ctrl+D",
                            "Describe what you need in plain English and let the assistant build it")
        self.a_exports = act("Export to a platform", lambda: self.pages.setCurrentWidget(self.exports_page))
        self.a_about = act("About", self.about)
        self.a_reset = act("Reset downloaded tables/templates", self.reset_data)
        self.a_exit = act("Exit", self.close, "Alt+F4")

        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        for a in (self.a_home, self.a_new, self.a_open, self.a_save, self.a_copy):
            tb.addAction(a)
        tb.addAction(self.a_assist)
        tb.addAction(self.a_exports)
        tb.addSeparator()
        tb.addAction(self.a_help)
        tb.addAction(self.a_update)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addWidget(QLabel(" District: "))
        self.district_combo = QComboBox()
        self.district_combo.setMinimumWidth(200)
        self.district_combo.setToolTip("Switch between the districts you support on this PC")
        self.district_combo.activated.connect(self._district_picked)
        tb.addWidget(self.district_combo)
        self._fill_districts()
        self.addToolBar(tb)

        mb = self.menuBar()
        m = mb.addMenu("&File")
        for a in (self.a_new, self.a_open, self.a_import, self.a_save, self.a_save_as, self.a_dup):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_exports)
        m.addAction(self.a_district)
        m.addAction(self.a_codes)
        m.addAction(self.a_upload)
        m.addAction(self.a_district_version)
        m.addAction(self.a_settings)
        m.addSeparator()
        m.addAction(act("Back up settings...", self.backup_settings))
        m.addAction(act("Restore settings...", self.restore_settings))
        m.addSeparator()
        m.addAction(self.a_exit)
        m2 = mb.addMenu("&Query")
        m2.addAction(self.a_copy)
        for i, n in enumerate(["Tables & Columns", "Link Tables", "Format Columns", "Filters", "Sort & Options",
                               "Review & Copy SQL"]):
            m2.addAction(act(f"Step {i + 1}: {n}", lambda _=False, i=i: self._goto_step(i), f"Ctrl+{i + 1}"))
        m2.addSeparator()
        m2.addAction(self.a_assist)
        m2.addAction(act("Add a combined part (UNION ALL)...", self.add_part))
        m2.addAction(act("Remove the part being edited", self.remove_part))
        mv = mb.addMenu("&View")
        from PySide6.QtGui import QActionGroup
        from .style import get_pref
        tg = QActionGroup(self)
        mtheme = mv.addMenu("Theme")
        for key, txt in (("light", "Light"), ("dark", "Dark"), ("system", "Match Windows")):
            a = QAction(txt, self, checkable=True)
            a.setChecked(get_pref() == key)
            a.triggered.connect(lambda _=False, k=key: self.set_theme(k))
            tg.addAction(a)
            mtheme.addAction(a)
        mt = mb.addMenu("&Tools")
        for txt, key in (("CAC Agent setup walkthrough...", "cac"), ("Data cleanup reports", "cleanup"),
                         ("Vendor privacy register...", "register"), ("Year-end rollover checklist...", "rollover"),
                         ("Upload alerts...", "alerts")):
            mt.addAction(act(txt, lambda _=False, k=key: self.open_tool(k)))
        mt.addAction(act("Vendor template builder...", lambda: self.template_builder(None)))
        mt.addAction(act("SAM setup check...", lambda: self.open_tool("samcheck")))
        mt.addAction(act("District health report...", lambda: self.open_tool("health")))
        mt.addAction(act("Admin PIN...", lambda: self.open_tool("pin")))
        for txt, key in (("Report emails...", "reports"), ("Compare two export files (what changed?)...", "diff"),
                         ("Change log...", "changelog"), ("SAM database connection (optional)...", "samdb")):
            mt.addAction(act(txt, lambda _=False, k=key: self.open_tool(k)))
        mt.addSeparator()
        mt.addAction(self.a_upload)
        mt.addAction(self.a_codes)
        m3 = mb.addMenu("&Help")
        for a in (self.a_help, self.a_update, self.a_reset, self.a_about):
            m3.addAction(a)
        m3.addSeparator()
        m3.addAction(act("Export assistant feedback...", self.export_feedback))
        m3.addAction(act("Setup wizard...", self.setup_wizard))
        m3.addAction(act("Quick start guide", lambda: self.show_doc("Quick Start Guide.md")))
        m3.addAction(act("CAC Agent setup guide", lambda: self.show_doc("CAC Agent Setup Guide.md")))
        m3.addAction(act("Windows test checklist", lambda: self.show_doc("Windows Test Checklist.md")))
        m3.addAction(act("Pilot plan", lambda: self.show_doc("Pilot Plan.md")))

    def export_feedback(self):
        from ..feedback import export_to, load
        n = len(load())
        if not n:
            QMessageBox.information(self, "Assistant feedback", "No feedback has been saved yet. Use 'Looks right' "
                                    "or 'This isn't right...' in the Query Assistant.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export assistant feedback", "assistant_feedback.jsonl",
                                              "Feedback (*.jsonl)")
        if path:
            export_to(path)
            QMessageBox.information(self, "Assistant feedback", f"Saved {n} feedback item(s) to\n{path}\n\n"
                                    "Send this file to whoever maintains the app so the helper can learn from it.")

    def add_part(self):
        if self.pages.currentWidget() is not self.builder:
            return
        name, ok = QInputDialog.getText(self, "Add combined part",
                                        "Rows from this part are added under the main part (UNION ALL).\n"
                                        "Give it the same columns in the same order.\n\nPart name:", text="Teachers")
        if ok:
            self.builder.add_part()
            self.ctx.query.name = name or self.ctx.query.name
            self.builder._fill_parts()
            self.on_change()

    def remove_part(self):
        if self.pages.currentWidget() is self.builder:
            if not self.builder.remove_part():
                QMessageBox.information(self, APP_NAME, "Choose a combined part (not the main part) to remove it.")
            else:
                self.on_change()

    def _goto_step(self, i):
        if self.pages.currentWidget() is self.builder:
            self.builder.go(i)

    def _status(self):
        self.statusBar().showMessage(
            f"Version {__version__}   |   Tables data {self.catalog.data_version} "
            f"({len(self.catalog.tables)} tables)   |   {'Unsaved changes' if self.dirty else 'Saved'}"
            + (f"   |   {Path(self.path).name}" if self.path else ""))

    # ------------------------------------------------------------------ query lifecycle
    def on_change(self):
        self.dirty = True
        self.builder.update_preview()
        self._status()

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, APP_NAME, "Save changes to the current query first?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def _load_query(self, q: QueryDef, path=None):
        self.export_origin = None
        self.a_district_version.setEnabled(False)
        self.ctx.query = q
        self.ctx.root = q
        self.path = path
        self.dirty = False
        self.pages.setCurrentWidget(self.builder)
        self.builder.load()
        missing = [t.table for t in q.tables if not self.catalog.has_table(t.table)]
        if missing:
            QMessageBox.warning(self, APP_NAME, "These tables are not in the current table list: "
                                + ", ".join(missing) + ". Check for updates or remove them.")
        self.setWindowTitle(f"{q.name} - {APP_NAME}")
        self._status()

    def go_home(self):
        self.home.refresh_saved()
        self.refresh_status_board()
        self.pages.setCurrentWidget(self.home)

    def new_query(self):
        if self._confirm_discard():
            self._load_query(QueryDef())

    def open_template(self, t: dict):
        if not self._confirm_discard():
            return
        q = QueryDef.from_dict(t)
        q.created = q.modified = ""
        self._load_query(q)
        self.dirty = True
        self.builder.go(5)
        self._status()

    def open_dialog(self):
        if not self._confirm_discard():
            return
        p, _ = QFileDialog.getOpenFileName(self, "Open query", str(paths.queries_dir()),
                                           "SAM queries (*.samq);;All files (*)")
        if p:
            self.dirty = False
            self.open_path(p)

    def open_path(self, p: str):
        if not self._confirm_discard():
            return
        try:
            q = QueryDef.from_json(Path(p).read_text(encoding="utf-8"))
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Could not open {p}:\n{e}")
            return
        self._load_query(q, p)

    def save(self) -> bool:
        if not self.path:
            return self.save_as()
        q = self.ctx.root
        q.touch()
        Path(self.path).write_text(q.to_json(), encoding="utf-8")
        self.dirty = False
        self._status()
        self.statusBar().showMessage(f"Saved {self.path}", 4000)
        return True

    def save_as(self) -> bool:
        name = "".join(ch for ch in self.ctx.root.name if ch.isalnum() or ch in " -_").strip() or "query"
        p, _ = QFileDialog.getSaveFileName(self, "Save query", str(paths.queries_dir() / f"{name}.samq"),
                                           "SAM queries (*.samq)")
        if not p:
            return False
        if not p.lower().endswith(".samq"):
            p += ".samq"
        self.path = p
        return self.save()

    def duplicate(self):
        q = self.ctx.root.clone()
        q.name = f"{q.name} (copy)"
        q.created = q.modified = ""
        self._load_query(q)
        self.dirty = True
        self._status()

    def copy_sql(self):
        if self.pages.currentWidget() is not self.builder:
            return
        self.builder.steps[-1].copy()
        self.statusBar().showMessage("SQL copied to the clipboard.", 4000)

    def closeEvent(self, e):
        if self._confirm_discard():
            e.accept()
        else:
            e.ignore()

    # ------------------------------------------------------------------ settings / about
    def open_assistant(self):
        from .assistant_dialog import AssistantDialog
        dlg = AssistantDialog(self.catalog, lambda: self.settings, self)
        dlg.open_settings.connect(self.open_settings)

        def use(q):
            if not self._confirm_discard():
                return
            self._load_query(q)
            self.dirty = True
            self.builder.go(5)
            self._status()
        dlg.use_query.connect(use)
        dlg.exec()

    def import_sql(self):
        from .import_dialog import ImportSqlDialog
        if not self._confirm_discard():
            return
        d = ImportSqlDialog(self.catalog, self)
        if d.exec() and d.result is not None:
            self._load_query(d.result)
            self.dirty = True
            self.builder.go(5 if d.result.sql_override else 0)
            self._status()

    def _admin(self, area) -> bool:
        from ..adminpin import require
        return require(self, self.settings, area)

    def upload_dialog(self, platform=None):
        if not self._admin("uploads"):
            return
        from .upload_dialog import UploadDialog
        UploadDialog(self.settings, platform, self).exec()
        self.refresh_status_board()

    def refresh_status_board(self):
        try:
            from ..uploader import status_rows
            self.home.set_status(status_rows(self.settings))
        except Exception:
            pass

    def save_district_version(self):
        if not self.export_origin:
            QMessageBox.information(self, "District version", "Open a file from Export to a platform first.")
            return
        from ..exports import save_override
        from ..query_model import validate
        platform, fe = self.export_origin
        errors, _ = validate(self.ctx.root, self.catalog)
        if errors and QMessageBox.question(self, "District version", "This query still has problems:\n\n- "
                                           + "\n- ".join(errors[:5]) + "\n\nSave it anyway?") != QMessageBox.Yes:
            return
        save_override(platform, fe, self.ctx.root)
        self.dirty = False
        self.exports_page.reload()
        QMessageBox.information(self, "District version saved",
                                f"Your version of {fe['file']} is now used for {platform['name']}: opening it, "
                                "Save package and the CAC Agent walkthrough. It is kept when the app or packages "
                                "update. Use 'Reset to standard' on the exports page to go back.")

    def open_tool(self, key: str, platform=None):
        from .tools_dialogs import CacWizardDialog, RegisterDialog, RolloverDialog
        if key in ("alerts", "reports", "samdb", "pin") and not self._admin(key):
            return
        if key == "cac":
            pid = platform["id"] if isinstance(platform, dict) else None
            if pid is None and self.pages.currentWidget() is self.exports_page and self.exports_page._cur():
                pid = self.exports_page._cur()["id"]
            CacWizardDialog(self.settings, pid, self).exec()
        elif key == "cleanup":
            self.exports_page.select_platform("cleanup")
            self.pages.setCurrentWidget(self.exports_page)
        elif key == "register":
            RegisterDialog(self.settings, self).exec()
        elif key == "rollover":
            d = RolloverDialog(self.settings, self)
            d.action.connect(lambda a: self._rollover_action(a, d))
            d.exec()
        elif key == "alerts":
            from .alerts_dialog import AlertsDialog
            AlertsDialog(self.settings, self).exec()
        elif key == "reports":
            from .tools_dialogs import ReportsDialog
            ReportsDialog(self.settings, self).exec()
        elif key == "diff":
            from .tools_dialogs import DiffDialog
            DiffDialog(None, self).exec()
        elif key == "changelog":
            from .tools_dialogs import ChangeLogDialog
            ChangeLogDialog(self).exec()
        elif key == "pin":
            self._admin_pin()
        elif key == "signoff":
            from .tools_dialogs import SignoffDialog
            if isinstance(platform, dict):
                SignoffDialog(self.settings, platform, self).exec()
                self.exports_page._show(None)
        elif key == "health":
            from .tools_dialogs import HealthDialog
            HealthDialog(self.settings, self).exec()
        elif key == "samcheck":
            from .tools_dialogs import SamCheckDialog
            SamCheckDialog(self.settings, self).exec()
            self.ctx.settings = self.settings
        elif key == "wizard":
            self.setup_wizard()
        elif key == "samdb":
            from .tools_dialogs import SamConnectionDialog
            SamConnectionDialog(self.settings, self).exec()
            self.builder.sample._update_sam_button()

    def template_builder(self, platform=None):
        from .template_builder_dialog import TemplateBuilderDialog
        d = TemplateBuilderDialog(self.catalog, lambda: self.settings, platform, self)
        d.saved.connect(lambda pid: (self.exports_page.reload(), self.exports_page.select_platform(pid)))
        d.exec()
        self.exports_page.reload()

    # ------------------------------------------------------------------ districts
    def _fill_districts(self):
        from ..districts import list_districts
        cur = paths.active_district()
        self.district_combo.blockSignals(True)
        self.district_combo.clear()
        for d in list_districts():
            self.district_combo.addItem(d["name"], d["id"])
        self.district_combo.addItem("Manage districts...", "__manage__")
        self.district_combo.setCurrentIndex(max(0, self.district_combo.findData(cur)))
        self.district_combo.blockSignals(False)
        many = len(list_districts()) > 1
        self.setWindowTitle(f"{APP_NAME} - {paths.district_name()}" if many else APP_NAME)

    def _district_picked(self, i):
        did = self.district_combo.itemData(i)
        if did == "__manage__":
            if not self._admin("districts"):
                self._fill_districts()
                return
            from .tools_dialogs import DistrictsDialog
            DistrictsDialog(self.settings, self).exec()
            self._fill_districts()
            return
        if did != paths.active_district():
            self.switch_district(did)

    def switch_district(self, did: str):
        from ..districts import switch_to
        if not self._confirm_discard():
            self._fill_districts()
            return
        paths.save_settings(self.settings, audit=False)
        switch_to(did)
        self.settings = paths.load_settings()
        self.ctx.settings = self.settings
        self.dirty = False
        self._load_query(QueryDef())
        self.exports_page.reload()
        self.home.refresh_saved()
        self.refresh_status_board()
        self._fill_districts()
        self.go_home()
        self.statusBar().showMessage(f"Switched to {paths.district_name()}", 6000)

    def _admin_pin(self):
        from ..adminpin import is_set, set_pin, lock
        if is_set(self.settings):
            choice = QMessageBox.question(self, "Admin PIN", "Change the admin PIN?\n\nYes = change it, No = remove "
                                          "it.", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if choice == QMessageBox.Cancel:
                return
            if choice == QMessageBox.No:
                set_pin(self.settings, None)
                paths.save_settings(self.settings)
                QMessageBox.information(self, "Admin PIN", "The admin PIN is removed.")
                return
        from PySide6.QtWidgets import QLineEdit as _LE
        a, ok = QInputDialog.getText(self, "Admin PIN", "New admin PIN (at least 4 characters).\nIt locks Package & "
                                     "Upload, alerts, report emails, the SAM connection, District Settings, restore and "
                                     "managing districts.", _LE.Password)
        if not ok or not a:
            return
        b, ok = QInputDialog.getText(self, "Admin PIN", "Type the PIN again:", _LE.Password)
        if not ok:
            return
        if a != b:
            QMessageBox.warning(self, "Admin PIN", "The two PINs don't match.")
            return
        try:
            set_pin(self.settings, a)
        except ValueError as e:
            QMessageBox.warning(self, "Admin PIN", str(e))
            return
        paths.save_settings(self.settings)
        lock()
        QMessageBox.information(self, "Admin PIN", "Admin PIN set. Locked screens ask for it (once every 15 minutes).")

    def set_theme(self, key: str):
        from .style import get_pref, set_pref
        if key == get_pref():
            return
        set_pref(key)
        if QMessageBox.question(self, "Theme", "The new theme is used after the app restarts. Restart now?\n\n"
                                "(Your query is kept only if it is saved.)") != QMessageBox.Yes:
            return
        if not self._confirm_discard():
            return
        import sys
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QApplication
        args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        QProcess.startDetached(sys.executable, [a for a in args if not a.lower().endswith(".samq")])
        self.dirty = False
        QApplication.instance().quit()

    def show_doc(self, name: str):
        from .docviewer import show_doc
        show_doc(self, name)

    def setup_wizard(self):
        from .setup_wizard import SetupWizard
        w = SetupWizard(self.settings, self, get_settings=lambda: self.settings)
        w.open_codes.connect(self.codes_dialog)
        w.open_alerts.connect(lambda: self.open_tool("alerts"))
        if w.exec():
            self.ctx.settings = self.settings
            paths.save_settings(self.settings)
            self.exports_page.reload()
            self.refresh_status_board()
            if w.open_cac_after():
                self.open_tool("cac")

    def maybe_first_run(self):
        if not self.settings.get("setup_done") and not self.settings.get("district_confirmed"):
            self.setup_wizard()

    def backup_settings(self):
        from ..backup import export_backup
        fn, _ = QFileDialog.getSaveFileName(self, "Back up settings", str(paths.queries_dir().parent /
                                            f"SAM QB backup {datetime.date.today():%Y-%m-%d}.samqb-backup"),
                                            "Backups (*.samqb-backup)")
        if not fn:
            return
        inc = QMessageBox.question(self, "Back up settings", "Include your saved queries (.samq) too?") \
            == QMessageBox.Yes
        try:
            n = export_backup(fn, self.settings, inc)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Back up settings", str(e))
            return
        QMessageBox.information(self, "Back up settings",
                                f"Saved {fn}\n\nDistrict package versions: {n['overrides']}, saved queries: "
                                f"{n['queries']}.\nPasswords are not included - re-enter them after restoring.")

    def restore_settings(self):
        if not self._admin("restore"):
            return
        from ..backup import import_backup, read_manifest
        from .tools_dialogs import RestoreDialog
        fn, _ = QFileDialog.getOpenFileName(self, "Restore settings", str(paths.queries_dir().parent),
                                            "Backups (*.samqb-backup);;All files (*)")
        if not fn:
            return
        try:
            man = read_manifest(fn)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Restore settings", f"Not a backup file: {e}")
            return
        d = RestoreDialog(fn, man, self)
        if not d.exec():
            return
        new, done = import_backup(fn, self.settings, d.parts())
        self.settings.clear()
        self.settings.update(new)
        self.ctx.settings = self.settings
        paths.save_settings(self.settings)
        self.exports_page.reload()
        self.refresh_status_board()
        QMessageBox.information(self, "Restore settings", "Restored:\n- " + "\n- ".join(done) +
                                "\n\nRe-enter upload, email and database passwords, then re-create any Windows "
                                "schedules on this PC (Package & Upload > Schedule).")

    def _rollover_action(self, act, dlg):
        if act == "district":
            self.district_settings()
        elif act == "codes":
            self.codes_dialog()
        elif act == "uploads":
            self.upload_dialog(None)
        elif act == "register":
            self.open_tool("register")
        elif act in ("exports", "cleanup"):
            dlg.accept()
            self.open_tool("cleanup") if act == "cleanup" else self.pages.setCurrentWidget(self.exports_page)

    def codes_dialog(self):
        from .codes_dialog import CodesDialog
        d = CodesDialog(self.settings, self)
        if d.exec():
            self.settings, sugg = d.values()
            self.ctx.settings = self.settings
            paths.save_settings(self.settings)
            if sugg:
                from .. import district
                QMessageBox.information(self, "District Settings updated",
                                        "Filled in from your codes:\n\n" + "\n".join(
                                            f"- {district.LABELS.get(k, k)}: {v}" for k, v in sugg.items())
                                        + "\n\nCheck them in File > District Settings.")
            self.exports_page._show(self.exports_page.list.currentRow())
            if self.pages.currentWidget() is self.builder:
                self.builder.steps[self.builder.nav.currentRow()].refresh()

    def district_settings(self) -> bool:
        if not self._admin("district"):
            return False
        from .dialogs import DistrictDialog
        d = DistrictDialog(self.settings, self)
        if d.exec():
            self.settings = d.values()
            self.ctx.settings = self.settings
            paths.save_settings(self.settings)
            self.exports_page._show(self.exports_page.list.currentRow())
            return True
        return False

    def open_export(self, platform, file_entry):
        from ..exports import build_query
        if not self._confirm_discard():
            return
        if not self.settings.get("district_confirmed"):
            QMessageBox.information(self, "District Settings",
                                    "Before your first export, check the email domains, username patterns and "
                                    "enrolled-student code for your district.")
            if not self.district_settings():
                return
        from ..exports import missing_settings
        missing = missing_settings(platform, self.settings)
        if missing:
            QMessageBox.information(self, "District Settings needed",
                                    f"{platform['name']} needs these District Settings:\n\n- " + "\n- ".join(missing)
                                    + "\n\nRun 'Owner type codes' under 'Find your SAM codes' in SAM to look them up.")
            if not self.district_settings() or missing_settings(platform, self.settings):
                return
        q = build_query(platform, file_entry, self.settings)
        self._load_query(q)
        self.export_origin = (platform, file_entry)
        self.a_district_version.setEnabled(True)
        self.dirty = True
        self.builder.go(5)
        self._status()

    def open_settings(self):
        d = SettingsDialog(self.settings, self)
        if d.exec():
            self.settings = d.values()
            self.ctx.settings = self.settings
            paths.save_settings(self.settings)

    def about(self):
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<h3>{APP_NAME}</h3><p>Version {__version__}<br>Tables data {self.catalog.data_version}</p>"
                          "<p>Builds SQL for SAM's Ad Hoc Query module, CAC Agent jobs and Report Builder-style lists.</p>"
                          f"<p>Update source: {updater.update_url()}</p>")

    def reset_data(self):
        if QMessageBox.question(self, APP_NAME, "Remove downloaded table/template updates and use the "
                                "versions that came with the installer?") == QMessageBox.Yes:
            updater.reset_downloaded_data()
            self.reload_data()

    def reload_data(self):
        self.catalog = Catalog.load()
        self.ctx.catalog = self.catalog
        self.builder.steps[0].fill_tree()
        self.home.set_templates(load_templates())
        self.exports_page.reload()
        self._status()

    # ------------------------------------------------------------------ updates
    def check_updates(self, silent=True):
        if self._checker and self._checker.isRunning():
            return
        self._checker = CheckWorker()
        self._checker.done.connect(lambda info, err: self._checked(info, err, silent))
        self._checker.start()
        if not silent:
            self.statusBar().showMessage("Checking for updates...")

    def _checked(self, info, err, silent):
        if err:
            if not silent:
                QMessageBox.warning(self, "Check for updates", f"Could not reach the update server.\n\n{err}")
            self._status()
            return
        self.update_info = info
        # silent data updates
        if info.data_available and self.settings.get("auto_data_updates", True) and not info.app_available:
            w = TaskWorker(updater.apply_data_update, info)
            w.done.connect(lambda _r, e: self._auto_data_done(e, info))
            self._auto_worker = w
            w.start()
            return
        if info.app_available or info.data_available:
            parts = []
            if info.app_available:
                parts.append(f"Version {info.app_version} of {APP_NAME} is available.")
            if info.data_available:
                parts.append(f"New tables/templates ({info.data_version}) are available.")
            self.banner_text.setText("  ".join(parts))
            self.banner.setVisible(True)
            if not silent or (info.app_available and info.latest.get("mandatory")):
                self.show_update_dialog()
        elif not silent:
            QMessageBox.information(self, "Check for updates",
                                    f"You are up to date.\n\nApp version {__version__}\nTables data {self.catalog.data_version}")
        self._status()

    def _auto_data_done(self, err, info):
        if not err:
            self.reload_data()
            self.banner_text.setText(f"Tables and templates were updated to {info.data_version}.")
            self.banner_btn.setVisible(False)
            self.banner.setVisible(True)

    def show_update_dialog(self):
        if not self.update_info:
            return
        d = UpdateDialog(self.update_info, self)
        d.data_installed.connect(self.reload_data)
        d.exec()
