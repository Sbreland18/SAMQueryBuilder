"""SAM Ad Hoc Query Builder - entry point."""
import sys

from PySide6.QtWidgets import QApplication

from sam_qb.app_config import APP_NAME
from sam_qb.ui.main_window import MainWindow
from sam_qb.ui.style import QSS, apply_theme
from sam_qb.version import __version__


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
    w = MainWindow()
    w.show()
    from PySide6.QtCore import QTimer
    QTimer.singleShot(400, w.maybe_first_run)
    # allow "open with" a .samq file
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".samq"):
        w.open_path(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
