"""SAM Ad Hoc Query Builder - Build & Release GUI.

Run from the project folder on your Windows build PC:
    python tools\\build_gui.py        (or double-click "Build GUI.bat")

Tabs
  1. Build & Release   version bump -> tests -> EXE (PyInstaller) -> installer (Inno Setup)
                       -> GitHub release upload -> latest.json -> git push
  2. Tables & Templates  rebuild the table catalog from a new Object Browser CSV, manage templates,
                       and publish a data-only update (no reinstall for users)
  3. GitHub Setup      check git / gh, sign in, connect this folder to the repository
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QProcess, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QTextCursor  # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,  # noqa: E402
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTabWidget,
                               QVBoxLayout, QWidget)

from sam_qb import release  # noqa: E402
from sam_qb.catalog_builder import write_catalog  # noqa: E402
from sam_qb.ui.style import QSS, apply_theme  # noqa: E402

APP_DIST = ROOT / "dist" / "SAM Ad Hoc Query Builder"
INSTALLER_DIR = ROOT / "dist" / "installer"
SETTINGS = ROOT / "tools" / "build_settings.json"


def find_iscc() -> str:
    cands = [shutil.which("ISCC.exe") or "", shutil.which("iscc") or ""]
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands += [os.path.join(base, "Inno Setup 6", "ISCC.exe"),
                      os.path.join(base, "Programs", "Inno Setup 6", "ISCC.exe")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return ""


def find_gh() -> str:
    """GitHub CLI path. Looks beyond PATH because a fresh install isn't on PATH until the GUI is restarted."""
    cands = [shutil.which("gh") or "", shutil.which("gh.exe") or ""]
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands += [os.path.join(base, "GitHub CLI", "gh.exe"),
                      os.path.join(base, "Programs", "GitHub CLI", "gh.exe"),
                      os.path.join(base, "Microsoft", "WinGet", "Links", "gh.exe")]
    home = os.path.expanduser("~")
    cands += [os.path.join(home, "scoop", "shims", "gh.exe"), r"C:\ProgramData\chocolatey\bin\gh.exe"]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return ""


GH_DOWNLOAD = "https://cli.github.com/"


def _console(command: str, extra_path: str = ""):
    """Open a new console window that runs `command` and stays open (Windows)."""
    env = os.environ.copy()
    if extra_path:
        env["PATH"] = extra_path + os.pathsep + env.get("PATH", "")
    subprocess.Popen(["cmd", "/k", command], cwd=ROOT, env=env,
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


class Runner:
    """Runs a queue of steps. A step is (label, list-of-args) for a process or (label, callable)."""

    def __init__(self, log, on_done):
        self.log, self.on_done = log, on_done
        self.queue = []
        self.proc = None
        self.ok = True

    def start(self, steps):
        self.queue = list(steps)
        self.ok = True
        self._next()

    def busy(self):
        return bool(self.queue) or (self.proc is not None)

    def _next(self):
        if not self.queue:
            self.proc = None
            self.on_done(self.ok)
            return
        label, action = self.queue.pop(0)
        self.log(f"\n=== {label} ===", "#1F5FAD")
        if callable(action):
            try:
                res = action()
                if res is False:
                    raise RuntimeError("step reported failure")
                if isinstance(res, str) and res:
                    self.log(res)
            except Exception as e:
                self.log(f"FAILED: {e}", "#B42318")
                self._fail()
                return
            self._next()
            return
        from tools.signing import mask
        self.log("> " + " ".join(f'"{a}"' if " " in a else a for a in mask(action)), "#666")
        self.proc = QProcess()
        self.proc.setWorkingDirectory(str(ROOT))
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(
            lambda: self.log(bytes(self.proc.readAllStandardOutput()).decode(errors="replace").rstrip()))
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(lambda e: self.log(f"Could not start process: {e}", "#B42318"))
        self.proc.start(action[0], action[1:])

    def _finished(self, code, _status):
        if code != 0:
            self.log(f"FAILED (exit code {code})", "#B42318")
            self._fail()
            return
        self.proc = None
        self._next()

    def _fail(self):
        self.ok = False
        self.queue = []
        self.proc = None
        self.on_done(False)


class BuildWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SAM Ad Hoc Query Builder - Build & Release")
        ico = ROOT / "assets" / "app.ico"
        if ico.exists():
            self.setWindowIcon(QIcon(str(ico)))
        self.resize(1100, 860)
        self.cfg = self._load_cfg()
        self.runner = Runner(self.log, self._done)

        split = QSplitter(Qt.Vertical)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._release_tab(), "1. Build && Release App")
        self.tabs.addTab(self._data_tab(), "2. Tables && Templates (data update)")
        self.tabs.addTab(self._github_tab(), "3. GitHub Setup")
        split.addWidget(self.tabs)
        logbox = QWidget()
        ll = QVBoxLayout(logbox)
        ll.setContentsMargins(8, 0, 8, 8)
        top = QHBoxLayout()
        top.addWidget(QLabel("<b>Log</b>"))
        top.addStretch()
        cb = QPushButton("Clear log")
        cb.clicked.connect(lambda: self.logview.clear())
        top.addWidget(cb)
        ll.addLayout(top)
        self.logview = QPlainTextEdit()
        self.logview.setReadOnly(True)
        self.logview.setFont(QFont("Consolas", 9))
        ll.addWidget(self.logview)
        split.addWidget(logbox)
        split.setSizes([560, 300])
        self.setCentralWidget(split)
        self.refresh_versions()

    # ------------------------------------------------------------------ settings
    def _load_cfg(self):
        try:
            return json.loads(SETTINGS.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _sign_cfg(self) -> dict:
        return {"enabled": self.c_sign.isChecked(), "signtool": self.signtool.text().strip(),
                "mode": self.sign_mode.currentData(), "thumbprint": self.thumb.text().strip(),
                "pfx": self.pfx.text().strip(), "timestamp": self.tsa.text().strip(),
                "desc": "SAM Ad Hoc Query Builder"}

    def _save_cfg(self):
        self.cfg.update({"iscc": self.iscc.text(), "python": self.py.text(),
                         "csv": self.csv.text() if hasattr(self, "csv") else ""})
        if hasattr(self, "c_sign"):
            self.cfg["signing"] = {k: v for k, v in self._sign_cfg().items() if k != "desc"}
        try:
            SETTINGS.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")
        except Exception:
            pass

    def log(self, text, color=None):
        if not text:
            return
        cur = self.logview.textCursor()
        cur.movePosition(QTextCursor.End)
        if color:
            safe = text.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>")
            from sam_qb.ui.style import color as theme_color
            cur.insertHtml(f"<span style='color:{theme_color(color)}'>{safe}</span><br>")
        else:
            cur.insertText(text + "\n")
        self.logview.setTextCursor(cur)
        self.logview.ensureCursorVisible()

    # ------------------------------------------------------------------ tab 1
    def _release_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox("Repository and tools")
        f = QFormLayout(g)
        repo, branch = release.read_repo()
        self.repo = QLineEdit(repo)
        self.branch = QLineEdit(branch)
        f.addRow("GitHub repo (owner/name):", self.repo)
        f.addRow("Branch:", self.branch)
        self.py = QLineEdit(self.cfg.get("python") or sys.executable)
        f.addRow("Python:", self._browse_row(self.py, "Python (python.exe)"))
        self.iscc = QLineEdit(self.cfg.get("iscc") or find_iscc())
        self.iscc.setPlaceholderText("C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe")
        f.addRow("Inno Setup ISCC.exe:", self._browse_row(self.iscc, "ISCC.exe"))
        lay.addWidget(g)

        gs = QGroupBox("Code signing (removes the Windows SmartScreen 'unknown publisher' warning)")
        fs = QFormLayout(gs)
        sc = self.cfg.get("signing", {})
        self.c_sign = QCheckBox("Sign the EXE and the installer")
        self.c_sign.setChecked(bool(sc.get("enabled")))
        fs.addRow("", self.c_sign)
        from tools.signing import DEFAULT_TIMESTAMP, find_signtool
        self.signtool = QLineEdit(sc.get("signtool") or find_signtool())
        self.signtool.setPlaceholderText("signtool.exe from the Windows SDK")
        fs.addRow("signtool.exe:", self._browse_row(self.signtool, "signtool.exe"))
        self.sign_mode = QComboBox()
        self.sign_mode.addItem("Certificate in the Windows store / USB token (thumbprint)", "store")
        self.sign_mode.addItem("Certificate file (.pfx)", "pfx")
        self.sign_mode.setCurrentIndex(max(0, self.sign_mode.findData(sc.get("mode", "store"))))
        fs.addRow("Certificate:", self.sign_mode)
        self.thumb = QLineEdit(sc.get("thumbprint", ""))
        self.thumb.setPlaceholderText("SHA-1 thumbprint (blank = best certificate in the store)")
        fs.addRow("Thumbprint:", self.thumb)
        self.pfx = QLineEdit(sc.get("pfx", ""))
        fs.addRow(".pfx file:", self._browse_row(self.pfx, "certificate (.pfx)"))
        self.tsa = QLineEdit(sc.get("timestamp") or DEFAULT_TIMESTAMP)
        fs.addRow("Timestamp server:", self.tsa)
        lay.addWidget(gs)

        g2 = QGroupBox("Version")
        v = QHBoxLayout(g2)
        self.cur_ver = QLabel()
        v.addWidget(self.cur_ver)
        v.addWidget(QLabel("   New version:"))
        self.new_ver = QLineEdit()
        self.new_ver.setMaximumWidth(120)
        v.addWidget(self.new_ver)
        for part in ("patch", "minor", "major"):
            b = QPushButton(f"+ {part}")
            b.clicked.connect(lambda _=False, p=part: self.new_ver.setText(release.bump(release.read_version(), p)))
            v.addWidget(b)
        v.addStretch()
        lay.addWidget(g2)

        g3 = QGroupBox("What's new in this version (shown to users in the update window)")
        n = QVBoxLayout(g3)
        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(90)
        n.addWidget(self.notes)
        self.mandatory = QCheckBox("Mark as important update")
        n.addWidget(self.mandatory)
        lay.addWidget(g3)

        g4 = QGroupBox("Steps to run")
        s = QVBoxLayout(g4)
        self.c_tests = QCheckBox("Run unit tests")
        self.c_exe = QCheckBox("Build the EXE with PyInstaller")
        self.c_inst = QCheckBox("Build the installer with Inno Setup")
        self.c_latest = QCheckBox("Update latest.json (version, installer link and SHA-256 hashes)")
        self.c_gh = QCheckBox("Publish: push code, create GitHub release v<version> with the installer, then push latest.json")
        for c in (self.c_tests, self.c_exe, self.c_inst, self.c_latest):
            c.setChecked(True)
            s.addWidget(c)
        s.addWidget(self.c_gh)
        s.addWidget(QLabel("<i>Users only see the new version after latest.json is pushed, which happens last "
                           "so the installer is always downloadable first.</i>"))
        lay.addWidget(g4)

        row = QHBoxLayout()
        self.go_btn = QPushButton("Build")
        self.go_btn.setObjectName("primary")
        self.go_btn.setMinimumHeight(36)
        self.go_btn.clicked.connect(self.build_release)
        row.addWidget(self.go_btn)
        ob = QPushButton("Open output folder")
        ob.clicked.connect(lambda: self._open(INSTALLER_DIR if INSTALLER_DIR.exists() else ROOT / "dist"))
        row.addWidget(ob)
        rb = QPushButton("Run app from source")
        rb.clicked.connect(lambda: QProcess.startDetached(self.py.text(), [str(ROOT / "main.py")], str(ROOT)))
        row.addWidget(rb)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        self.c_gh.toggled.connect(lambda on: self.go_btn.setText("Build && Publish" if on else "Build"))
        return w

    def _browse_row(self, edit, what):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit, 1)
        b = QPushButton("Browse...")
        b.clicked.connect(lambda: self._pick(edit, what))
        h.addWidget(b)
        return box

    def _pick(self, edit, what):
        p, _ = QFileDialog.getOpenFileName(self, f"Locate {what}", edit.text() or str(ROOT))
        if p:
            edit.setText(p)
            self._save_cfg()

    def refresh_versions(self):
        v = release.read_version()
        self.cur_ver.setText(f"Current version: <b>{v}</b>")
        if not self.new_ver.text():
            self.new_ver.setText(release.bump(v, "patch"))
        dv = release.read_data_version()
        self.cur_data.setText(f"Current data version: <b>{dv}</b>  ({self._count_tables()} tables, "
                              f"{len(self._templates())} templates)")
        self.fill_templates()

    def _count_tables(self):
        try:
            return len(json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))["tables"])
        except Exception:
            return 0

    def _repo(self):
        return self.repo.text().strip(), self.branch.text().strip() or "main"

    def _precheck(self, need_git=False):
        if self.runner.busy():
            QMessageBox.information(self, "Busy", "A build is already running.")
            return False
        repo, _ = self._repo()
        if "/" not in repo:
            QMessageBox.warning(self, "Repo", "Enter the GitHub repo as owner/name, e.g. Sbreland18/SAMQueryBuilder.")
            return False
        if need_git:
            if not shutil.which("git"):
                QMessageBox.warning(self, "Missing tool", "'git' was not found. See the GitHub Setup tab.")
                return False
            if not find_gh():
                QMessageBox.warning(self, "Missing tool", "GitHub CLI (gh) was not found. Open the GitHub Setup tab "
                                    "and click 'Install GitHub CLI', or untick Publish to build only.")
                return False
        self._save_cfg()
        return True

    def build_release(self):
        publish = self.c_gh.isChecked()
        if not self._precheck(need_git=publish):
            return
        ver = self.new_ver.text().strip()
        if not ver or ver.count(".") != 2:
            QMessageBox.warning(self, "Version", "Enter a version like 1.0.1")
            return
        if self.c_inst.isChecked() and not os.path.exists(self.iscc.text()):
            QMessageBox.warning(self, "Inno Setup", "ISCC.exe not found. Install Inno Setup 6 (jrsoftware.org) "
                                                    "or browse to ISCC.exe.")
            return
        if publish and QMessageBox.question(
                self, "Publish", f"Publish version {ver} to {self._repo()[0]}?\n\nEveryone using the app will be "
                                 "offered this update.") != QMessageBox.Yes:
            return
        repo, branch = self._repo()
        py = self.py.text()
        installer = INSTALLER_DIR / release.installer_name(ver)
        notes = self.notes.toPlainText().strip()
        steps = [("Save repo settings and version", lambda: (release.write_repo(repo, branch),
                                                              release.write_version(ver), f"Version set to {ver}")[2])]
        if self.c_tests.isChecked():
            steps.append(("Unit tests", [py, "-m", "pytest", "-q", "tests"]))
        if self.c_exe.isChecked():
            sep = os.pathsep
            steps.append(("PyInstaller", [
                py, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
                "--name", "SAM Ad Hoc Query Builder", "--icon", str(ROOT / "assets" / "app.ico"),
                "--add-data", f"{ROOT / 'data' / 'catalog.json'}{sep}data",
                "--add-data", f"{ROOT / 'data' / 'templates.json'}{sep}data",
                "--add-data", f"{ROOT / 'data' / 'exports.json'}{sep}data",
                "--add-data", f"{ROOT / 'data' / 'assistant_vocab.json'}{sep}data",
                "--add-data", f"{ROOT / 'data' / 'shared_packages.json'}{sep}data",
                "--add-data", f"{ROOT / 'assets'}{sep}assets",
                "--add-data", f"{ROOT / 'docs'}{sep}docs",
                "--collect-submodules", "sqlglot", "--hidden-import", "paramiko",
                "--hidden-import", "pyodbc", "--hidden-import", "pgpy",
                "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"),
                "--specpath", str(ROOT / "build"),
                str(ROOT / "main.py")]))
        sign = self.c_sign.isChecked()
        pfx_pw = ""
        if sign:
            from tools.signing import sign_command, verify_command
            scfg = self._sign_cfg()
            if scfg["mode"] == "pfx":
                pfx_pw, ok = QInputDialog.getText(self, "Code signing", "Password for the .pfx certificate:",
                                                  QLineEdit.Password)
                if not ok:
                    return
            try:
                exe = str(ROOT / "dist" / "SAM Ad Hoc Query Builder" / "SAM Ad Hoc Query Builder.exe")
                if self.c_exe.isChecked():
                    steps.append(("Sign the EXE", sign_command(scfg, exe, pfx_pw)))
                    steps.append(("Verify the EXE signature", verify_command(scfg, exe)))
            except RuntimeError as e:
                QMessageBox.warning(self, "Code signing", str(e))
                return
        if self.c_inst.isChecked():
            steps.append(("Inno Setup installer", [self.iscc.text(), f"/DMyAppVersion={ver}",
                                                   str(ROOT / "installer" / "SAMQueryBuilder.iss")]))
            if sign:
                steps.append(("Sign the installer", sign_command(scfg, str(installer), pfx_pw)))
                steps.append(("Verify the installer signature", verify_command(scfg, str(installer))))
        if publish:
            steps += [
                ("Commit code", lambda: self._git_commit(f"Version {ver}", exclude_latest=True)),
                ("Push code", ["git", "push", "origin", branch]),
                ("Create GitHub release", lambda: self._gh_release(ver, notes, installer, repo, branch)),
            ]
        if self.c_latest.isChecked():
            steps.append(("Write latest.json", lambda: self._write_latest(repo, branch, ver, notes, installer)))
        if publish:
            steps += [
                ("Commit latest.json", lambda: self._git_commit(f"Publish latest.json for v{ver}", only_latest=True)),
                ("Push latest.json", ["git", "push", "origin", branch]),
            ]
        self._set_busy(True)
        self.runner.start(steps)

    def _write_latest(self, repo, branch, ver, notes, installer):
        if not installer.exists():
            self.log(f"Note: {installer.name} not found - latest.json will have no installer hash.", "#9A6700")
        d = release.make_latest(repo, branch, ver, notes, installer if installer.exists() else None,
                                None, self.mandatory.isChecked())
        return json.dumps(d, indent=2)

    def _git(self, *args, check=True):
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip()
        if out:
            self.log(out)
        if check and r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed")
        return r

    def _git_commit(self, msg, exclude_latest=False, only_latest=False):
        if only_latest:
            self._git("add", "latest.json")
        else:
            self._git("add", "-A")
            if exclude_latest:
                self._git("reset", "-q", "latest.json", check=False)
        if self._git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return "Nothing to commit."
        self._git("commit", "-m", msg)
        return "Committed."

    def _gh_release(self, ver, notes, installer, repo, branch):
        if not installer.exists():
            raise RuntimeError(f"Installer {installer} not found - build it first.")
        tag = f"v{ver}"
        gh = find_gh() or "gh"
        exists = subprocess.run([gh, "release", "view", tag, "--repo", repo], cwd=ROOT,
                                capture_output=True, text=True).returncode == 0
        if exists:
            cmd = [gh, "release", "upload", tag, str(installer), "--clobber", "--repo", repo]
        else:
            cmd = [gh, "release", "create", tag, str(installer), "--repo", repo, "--target", branch,
                   "--title", f"SAM Ad Hoc Query Builder {ver}", "--notes", notes or f"Version {ver}"]
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        self.log((r.stdout + r.stderr).strip())
        if r.returncode != 0:
            raise RuntimeError("gh release failed")
        return f"Release {tag} has the installer."

    # ------------------------------------------------------------------ tab 2
    def _data_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Use this tab when SAM adds/changes tables or you want to share new templates. "
                             "Users get these updates automatically without reinstalling."))
        self.cur_data = QLabel()
        lay.addWidget(self.cur_data)

        g = QGroupBox("Table catalog (from SAMS Database Object Browser export)")
        f = QVBoxLayout(g)
        row = QHBoxLayout()
        self.csv = QLineEdit(self.cfg.get("csv") or str(ROOT / "data" / "SAMS Database Object Browser - Tables.csv"))
        row.addWidget(QLabel("Tables CSV:"))
        row.addWidget(self.csv, 1)
        b = QPushButton("Browse...")
        b.clicked.connect(self._pick_csv)
        row.addWidget(b)
        f.addLayout(row)
        row2 = QHBoxLayout()
        rb = QPushButton("Rebuild catalog from CSV")
        rb.clicked.connect(self.rebuild_catalog)
        row2.addWidget(rb)
        xb = QPushButton("Rebuild platform export packages")
        xb.setToolTip("Re-runs tools/make_exports.py (Clever, OneRoster, SDS, Google, Canvas, NWEA)")
        xb.clicked.connect(lambda: (self._set_busy(True), self.runner.start(
            [("Platform exports", [self.py.text(), str(ROOT / "tools" / "make_exports.py")])])))
        row2.addWidget(xb)
        eb = QPushButton("Edit descriptions / links (catalog_overrides.json)")
        eb.clicked.connect(lambda: self._open(ROOT / "data" / "catalog_overrides.json"))
        row2.addWidget(eb)
        row2.addStretch()
        f.addLayout(row2)
        lay.addWidget(g)

        g2 = QGroupBox("Templates shown on the start page")
        t = QHBoxLayout(g2)
        self.tlist = QListWidget()
        t.addWidget(self.tlist, 1)
        col = QVBoxLayout()
        for txt, fn in (("Add from saved query (.samq)...", self.add_templates), ("Set category...", self.set_category),
                        ("Move up", lambda: self.move_template(-1)), ("Move down", lambda: self.move_template(1)),
                        ("Remove", self.remove_template)):
            bb = QPushButton(txt)
            bb.clicked.connect(fn)
            col.addWidget(bb)
        col.addStretch()
        t.addLayout(col)
        lay.addWidget(g2, 1)

        gsp = QGroupBox("Shared package library (vendor-template packages every district receives)")
        sp = QHBoxLayout(gsp)
        self.splist = QListWidget()
        sp.addWidget(self.splist, 1)
        spc = QVBoxLayout()
        for txt, fn in (("Add package file(s) (.samqb-package)...", self.add_shared),
                        ("Remove", self.remove_shared)):
            bb = QPushButton(txt)
            bb.clicked.connect(fn)
            spc.addWidget(bb)
        spc.addWidget(QLabel("<i>Districts send you a package with\n'Share: export package file'.\nCheck it, add "
                             "it here,\nthen Publish data update.</i>"))
        spc.addStretch()
        sp.addLayout(spc)
        lay.addWidget(gsp)
        self.fill_shared()

        g3 = QGroupBox("Publish data update")
        p = QVBoxLayout(g3)
        p.addWidget(QLabel("What changed (shown to users):"))
        self.data_notes = QPlainTextEdit()
        self.data_notes.setMaximumHeight(70)
        p.addWidget(self.data_notes)
        self.c_data_push = QCheckBox("Commit and push to GitHub (otherwise only latest.json is updated locally)")
        self.c_data_push.setChecked(True)
        p.addWidget(self.c_data_push)
        pb = QPushButton("Publish data update")
        pb.setObjectName("primary")
        pb.clicked.connect(self.publish_data)
        p.addWidget(pb, 0, Qt.AlignLeft)
        lay.addWidget(g3)
        return w

    # ------------------------------------------------------------------ shared packages
    def fill_shared(self):
        from sam_qb.shared_library import read_library
        self.splist.clear()
        for p in read_library(ROOT / "data" / "shared_packages.json").get("packages", []):
            it = QListWidgetItem(f"{p['name']}  ({len(p['files'])} file(s))  [{p['id']}]")
            it.setData(Qt.UserRole, p["id"])
            self.splist.addItem(it)

    def add_shared(self):
        from sam_qb.shared_library import add_package_file
        files, _ = QFileDialog.getOpenFileNames(self, "Package files", "", "Package files (*.samqb-package *.json)")
        for f in files:
            try:
                p = add_package_file(ROOT / "data" / "shared_packages.json", f)
                self.log(f"Added shared package {p['name']} ({p['id']})")
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Shared package", str(e))
        self.fill_shared()

    def remove_shared(self):
        from sam_qb.shared_library import remove_package
        it = self.splist.currentItem()
        if it and QMessageBox.question(self, "Shared package", f"Remove {it.text()} from the library?") \
                == QMessageBox.Yes:
            remove_package(ROOT / "data" / "shared_packages.json", it.data(Qt.UserRole))
            self.fill_shared()

    def _pick_csv(self):
        p, _ = QFileDialog.getOpenFileName(self, "SAMS tables CSV", str(ROOT / "data"), "CSV (*.csv)")
        if p:
            self.csv.setText(p)
            self._save_cfg()

    def rebuild_catalog(self):
        src = Path(self.csv.text())
        if not src.exists():
            QMessageBox.warning(self, "CSV", "CSV file not found.")
            return
        dest_csv = ROOT / "data" / "SAMS Database Object Browser - Tables.csv"
        try:
            old = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
            old_tables = set(old.get("tables", {}))
        except Exception:
            old_tables = set()
        if src.resolve() != dest_csv.resolve():
            shutil.copyfile(src, dest_csv)
        cat = write_catalog(dest_csv, ROOT / "data" / "catalog_overrides.json", ROOT / "data" / "catalog.json",
                            release.read_data_version() or None)
        new_tables = set(cat["tables"])
        added, removed = sorted(new_tables - old_tables), sorted(old_tables - new_tables)
        self.log(f"Catalog rebuilt: {len(new_tables)} tables, {len(cat['relationships'])} links.", "#1E7B34")
        if added:
            self.log("New tables: " + ", ".join(added))
        if removed:
            self.log("Removed tables: " + ", ".join(removed))
        if (added or removed) and not self.data_notes.toPlainText().strip():
            parts = []
            if added:
                parts.append(f"Added {len(added)} table(s): " + ", ".join(added[:15]) + ("..." if len(added) > 15 else ""))
            if removed:
                parts.append(f"Removed {len(removed)} table(s).")
            self.data_notes.setPlainText(" ".join(parts))
        self.refresh_versions()

    def _templates(self):
        try:
            return json.loads((ROOT / "data" / "templates.json").read_text(encoding="utf-8")).get("templates", [])
        except Exception:
            return []

    def _save_templates(self, templates):
        p = ROOT / "data" / "templates.json"
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"data_version": release.read_data_version()}
        d["templates"] = templates
        p.write_text(json.dumps(d, indent=1), encoding="utf-8")
        self.refresh_versions()

    def fill_templates(self):
        if not hasattr(self, "tlist"):
            return
        r = self.tlist.currentRow()
        self.tlist.clear()
        for t in self._templates():
            it = QListWidgetItem(f"[{t.get('category') or 'General'}]  {t.get('name')}")
            it.setToolTip(t.get("description", ""))
            self.tlist.addItem(it)
        self.tlist.setCurrentRow(r)

    def add_templates(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add saved queries as templates",
                                                str(Path.home() / "Documents" / "SAM Ad Hoc Query Builder" / "Queries"),
                                                "SAM queries (*.samq)")
        if not files:
            return
        ts = self._templates()
        names = {t["name"]: i for i, t in enumerate(ts)}
        for f in files:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
            d["sql_override"] = d.get("sql_override", "")
            if not d.get("category"):
                cat, ok = QInputDialog.getText(self, "Category", f"Category for '{d.get('name')}':", text="General")
                d["category"] = cat if ok and cat else "General"
            if d["name"] in names:
                ts[names[d["name"]]] = d
                self.log(f"Replaced template {d['name']}")
            else:
                ts.append(d)
                self.log(f"Added template {d['name']}")
        self._save_templates(ts)

    def set_category(self):
        r = self.tlist.currentRow()
        ts = self._templates()
        if 0 <= r < len(ts):
            cat, ok = QInputDialog.getText(self, "Category", "Category:", text=ts[r].get("category", ""))
            if ok:
                ts[r]["category"] = cat
                self._save_templates(ts)

    def move_template(self, d):
        r = self.tlist.currentRow()
        ts = self._templates()
        n = r + d
        if 0 <= r < len(ts) and 0 <= n < len(ts):
            ts[r], ts[n] = ts[n], ts[r]
            self._save_templates(ts)
            self.tlist.setCurrentRow(n)

    def remove_template(self):
        r = self.tlist.currentRow()
        ts = self._templates()
        if 0 <= r < len(ts) and QMessageBox.question(self, "Remove", f"Remove template '{ts[r]['name']}'?") == QMessageBox.Yes:
            del ts[r]
            self._save_templates(ts)

    def publish_data(self):
        push = self.c_data_push.isChecked()
        if not self._precheck(need_git=False):
            return
        if push and not shutil.which("git"):
            QMessageBox.warning(self, "git", "git was not found. See the GitHub Setup tab.")
            return
        repo, branch = self._repo()
        new_dv = release.next_data_version(release.read_data_version())
        notes = self.data_notes.toPlainText().strip()
        if QMessageBox.question(self, "Publish data update",
                                f"Publish tables/templates version {new_dv}?") != QMessageBox.Yes:
            return
        steps = [
            ("Stamp data version", lambda: (release.set_data_version(new_dv), f"Data version {new_dv}")[1]),
            ("Write latest.json", lambda: json.dumps(release.make_latest(repo, branch, None, None, None, notes), indent=2)),
        ]
        if push:
            steps += [
                ("Commit", lambda: self._git_commit(f"Data update {new_dv}")),
                ("Push", ["git", "push", "origin", branch]),
            ]
        self._set_busy(True)
        self.runner.start(steps)

    # ------------------------------------------------------------------ tab 3
    def _github_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(
            "<b>One-time setup on the build PC</b><ol>"
            "<li>Install <b>Python 3.11+</b>, <b>Git for Windows</b> and <b>Inno Setup 6</b>. "
            "Click <b>Install GitHub CLI</b> if Check tools says gh is NOT FOUND (only publishing needs it).</li>"
            "<li>Click <b>Install Python packages</b> (PySide6, PyInstaller, pytest).</li>"
            "<li>Click <b>Sign in to GitHub</b> (opens the gh login in a console window).</li>"
            "<li>Click <b>Connect this folder to the repo</b>. The repository must exist on GitHub "
            "(it can be empty) and must be <b>public</b> so the app can read latest.json without a login.</li>"
            "</ol>"))
        row = QHBoxLayout()
        for txt, fn in (("Check tools", self.check_tools), ("Install Python packages", self.install_packages),
                        ("Install GitHub CLI", self.install_gh), ("Sign in to GitHub", self.gh_login), ("Connect this folder to the repo", self.connect_repo)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        return w

    def check_tools(self):
        gh = find_gh()
        for name, p in (("git", shutil.which("git")), ("gh", gh),
                        (Path(self.py.text()).name, shutil.which(self.py.text()) or
                         (self.py.text() if os.path.exists(self.py.text()) else None))):
            self.log(f"{name:12} {'OK  ' + p if p else 'NOT FOUND'}", "#1E7B34" if p else "#B42318")
        iscc = self.iscc.text()
        self.log(f"{'ISCC.exe':12} {'OK  ' + iscc if iscc and os.path.exists(iscc) else 'NOT FOUND'}")
        if gh:
            r = subprocess.run([gh, "auth", "status"], capture_output=True, text=True)
            self.log((r.stdout + r.stderr).strip())
        else:
            self.log("GitHub CLI is only needed to publish releases. Click 'Install GitHub CLI', then "
                     "'Check tools' again.", "#9A6700")
        if shutil.which("git"):
            r = subprocess.run(["git", "remote", "-v"], cwd=ROOT, capture_output=True, text=True)
            self.log("git remote: " + ((r.stdout + r.stderr).strip() or "(none)"))

    def install_packages(self):
        if self.runner.busy():
            return
        self._set_busy(True)
        self.runner.start([("pip install", [self.py.text(), "-m", "pip", "install", "-r",
                                            str(ROOT / "requirements-dev.txt")])])

    def install_gh(self):
        if find_gh():
            self.log("GitHub CLI is already installed: " + find_gh(), "#1E7B34")
            return
        if sys.platform != "win32":
            self.log("Install GitHub CLI from " + GH_DOWNLOAD)
            return
        if shutil.which("winget"):
            self.log("Installing GitHub CLI with winget in a console window. When it finishes, click "
                     "'Check tools', then 'Sign in to GitHub'.")
            _console("title Install GitHub CLI && winget install --id GitHub.cli -e --accept-source-agreements "
                     "--accept-package-agreements && echo. && echo Done - close this window and click "
                     "Check tools in the Build GUI.")
        else:
            QMessageBox.information(self, "GitHub CLI", "winget isn't available on this PC. The download page will "
                                    "open - run the Windows installer (.msi), then click Check tools.")
            QDesktopServices.openUrl(QUrl(GH_DOWNLOAD))

    def gh_login(self):
        gh = find_gh()
        if not gh:
            if QMessageBox.question(self, "GitHub CLI not found",
                                    "GitHub CLI (gh) isn't installed on this PC, so you can't sign in yet.\n\n"
                                    "Install it now?") == QMessageBox.Yes:
                self.install_gh()
            return
        if sys.platform == "win32":
            # put gh's folder first on PATH so a just-installed gh works without restarting the GUI
            _console("title Sign in to GitHub && gh auth login --web", extra_path=os.path.dirname(gh))
        else:
            self.log(f"Run '{gh} auth login' in a terminal.")

    def connect_repo(self):
        if not shutil.which("git"):
            QMessageBox.warning(self, "git", "Install Git for Windows first.")
            return
        repo, branch = self._repo()
        url = f"https://github.com/{repo}.git"
        steps = []
        if not (ROOT / ".git").exists():
            steps.append(("git init", ["git", "init"]))
        steps.append(("Set branch", ["git", "checkout", "-B", branch]))
        has_origin = (ROOT / ".git").exists() and subprocess.run(
            ["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True).returncode == 0
        steps.append(("Set remote", ["git", "remote", "set-url" if has_origin else "add", "origin", url]))
        steps.append(("Save repo in app config", lambda: (release.write_repo(repo, branch), f"App points to {repo}")[1]))
        steps.append(("First commit", lambda: self._git_commit("SAM Ad Hoc Query Builder project")))
        steps.append(("Push", ["git", "push", "-u", "origin", branch]))
        self._set_busy(True)
        self.runner.start(steps)

    # ------------------------------------------------------------------ misc
    def _open(self, p: Path):
        p.mkdir(parents=True, exist_ok=True) if not p.suffix else None
        if sys.platform == "win32":
            os.startfile(str(p))  # noqa
        else:
            subprocess.Popen(["xdg-open", str(p)])

    def _set_busy(self, busy):
        self.tabs.setEnabled(not busy)

    def _done(self, ok):
        self._set_busy(False)
        self.log("\nFINISHED SUCCESSFULLY" if ok else "\nSTOPPED - fix the error above and try again.",
                 "#1E7B34" if ok else "#B42318")
        self.new_ver.setText("")
        self.refresh_versions()


def main():
    app = QApplication(sys.argv)
    apply_theme(app)
    w = BuildWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
