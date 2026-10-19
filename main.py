"""SAM Ad Hoc Query Builder - entry point."""
import sys

from PySide6.QtWidgets import QApplication

from sam_qb.app_config import APP_NAME
from sam_qb.ui.main_window import MainWindow
from sam_qb.ui.style import QSS, apply_theme
from sam_qb.version import __version__


def _install_error_handler(window):
    """Unexpected errors are written to error_log.txt and offer Help > Report a bug instead of closing."""
    from sam_qb import bugreport

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        text = bugreport.log_exception(exc_type, exc, tb)
        if issubclass(exc_type, OSError):   # a file or folder problem (in use, no permission, share offline)
            try:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(window, APP_NAME, f"Couldn't read or write a file:\n\n{exc}\n\nCheck that the "
                                                      "file isn't open in another program and that the folder is "
                                                      "available, then try again.")
            except Exception:
                pass
            return
        try:
            from PySide6.QtWidgets import QMessageBox
            box = QMessageBox(window)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Something went wrong")
            box.setText(f"{APP_NAME} hit an unexpected error:\n\n{exc_type.__name__}: {exc}\n\n"
                        "Your work is still open. Would you like to report it?")
            box.setDetailedText(text)
            rep = box.addButton("Report a bug...", QMessageBox.AcceptRole)
            box.addButton("Close", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is rep:
                window.report_bug(f"Error: {exc_type.__name__}: {str(exc)[:80]}",
                                  "I was ... when this error appeared.")
        except Exception:
            pass
    sys.excepthook = hook


def main():
    # scheduled runs for a second district:  --district <id> --upload "Profile"
    if "--district" in sys.argv:
        import os
        i = sys.argv.index("--district")
        if i + 1 < len(sys.argv):
            os.environ["SAMQB_DISTRICT"] = sys.argv[i + 1]
            del sys.argv[i:i + 2]
    # headless upload for Windows Task Scheduler:  --upload "Profile name"
    if "--upload" in sys.argv:
        from sam_qb.uploader import headless
        i = sys.argv.index("--upload")
        sys.exit(headless(sys.argv[i + 1] if i + 1 < len(sys.argv) else ""))
    # headless monthly health report email:  --health
    if "--health" in sys.argv:
        from sam_qb.health import headless as health_headless
        sys.exit(health_headless())
    # headless automatic settings backup:  --backup
    if "--backup" in sys.argv:
        from sam_qb.backup import headless_auto
        sys.exit(headless_auto())
    # headless weekly data-quality snapshot:  --dqsnapshot
    if "--dqsnapshot" in sys.argv:
        from sam_qb.dqtrend import headless as dq_headless
        sys.exit(dq_headless())
    # headless report email:  --report "Report name"
    if "--report" in sys.argv:
        from sam_qb.reports import headless as report_headless
        i = sys.argv.index("--report")
        sys.exit(report_headless(sys.argv[i + 1] if i + 1 < len(sys.argv) else ""))
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SAMAdHocQueryBuilder")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    apply_theme(app)

    def _early_hook(t, e, tb):   # errors while the window is being built: log them and say so
        from sam_qb import bugreport
        bugreport.log_exception(t, e, tb)
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, APP_NAME, f"{APP_NAME} could not start:\n\n{t.__name__}: {e}\n\nThe details "
                                                 f"are in error_log.txt in %APPDATA%\\{APP_NAME}.")
        except Exception:
            pass
    sys.excepthook = _early_hook
    try:
        w = MainWindow()
    except Exception:
        _early_hook(*sys.exc_info())
        sys.exit(1)
    _install_error_handler(w)
    w.show()
    from PySide6.QtCore import QTimer
    QTimer.singleShot(400, w.maybe_first_run)
    # allow "open with" a .samq file
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".samq"):
        w.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
