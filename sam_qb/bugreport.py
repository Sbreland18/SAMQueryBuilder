"""Help > Report a bug: diagnostics, error log, and the GitHub issue / email routes.

Nothing is sent automatically. The person sees (and can edit) the full report before it leaves the PC,
and diagnostics never include student data, passwords or the settings file."""
from __future__ import annotations

import platform
import re
import sys
import traceback
import urllib.parse
from datetime import datetime

from . import paths
from .app_config import APP_NAME, GITHUB_REPO, SUPPORT_EMAIL
from .version import __version__

ERROR_LOG = "error_log.txt"
MAX_URL = 7500           # GitHub rejects very long issue URLs
MAX_MAILTO = 1800        # mail programs cut long mailto: links


def error_log_path():
    return paths.root_dir() / ERROR_LOG


def log_exception(exc_type, exc, tb) -> str:
    """Append an unexpected error to error_log.txt; returns the formatted text."""
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        p = error_log_path()
        old = p.read_text(encoding="utf-8")[-200_000:] if p.exists() else ""
        p.write_text(old + f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S}  v{__version__}\n{text}", encoding="utf-8")
    except Exception:
        pass
    return text


def recent_errors(max_chars: int = 3000) -> str:
    try:
        text = error_log_path().read_text(encoding="utf-8")
    except Exception:
        return ""
    blocks = text.split("\n=== ")
    out = "\n=== ".join(blocks[-3:]).strip()
    return mask(out[-max_chars:])


_SECRETS = [(re.compile(r"(?i)(password|pwd|passphrase|secret|token|key)(\s*[=:]\s*)\S+"), r"\1\2********"),
            (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "<email>"),
            (re.compile(r"(?i)(C:\\Users\\)[^\\\s]+"), r"\1<user>")]


def mask(text: str) -> str:
    for rx, rep in _SECRETS:
        text = rx.sub(rep, text)
    return text


def diagnostics(settings: dict) -> str:
    """Plain-text facts that help reproduce a problem - no student data, names, passwords or addresses."""
    try:
        from .updater import current_data_version
        data_v = current_data_version()
    except Exception:
        data_v = "?"
    try:
        from .ui.style import get_pref
        theme = get_pref()
    except Exception:
        theme = "?"
    try:
        n_districts = len(paths.load_districts().get("list", [])) or 1
    except Exception:
        n_districts = 1
    lines = [f"{APP_NAME} {__version__} (data {data_v})",
             f"Windows: {platform.platform()}",
             f"Python {platform.python_version()}{' (installed app)' if getattr(sys, 'frozen', False) else ' (source)'}",
             f"Theme: {theme}; districts on this PC: {n_districts}",
             f"Upload profiles: {len(settings.get('upload_profiles', []))}; "
             f"SAM connection: {'on' if (settings.get('sam_connection') or {}).get('enabled') else 'off'}; "
             f"schools loaded: {len(settings.get('schools', []))}; setup wizard done: {bool(settings.get('setup_done'))}"]
    try:
        from .uploader import status_rows
        for r in status_rows(settings)[:10]:
            last = r.get("last") or {}
            msg = mask(str(last.get("message", ""))[:160]).replace("\n", " ")
            lines.append(f"Upload '{r['name']}': {last.get('status', 'never run')} {last.get('when', '')} {msg}".rstrip())
    except Exception:
        pass
    errs = recent_errors()
    if errs:
        lines += ["", "Recent errors:", errs]
    return "\n".join(lines)


def compose(summary: str, details: str, steps: str, contact: str, diag: str) -> tuple[str, str]:
    title = f"[Bug] {summary.strip()}"[:120]
    parts = ["**What happened**", details.strip() or "-", "", "**Steps to make it happen**", steps.strip() or "-"]
    if contact.strip():
        parts += ["", f"**Reported by:** {contact.strip()}"]
    if diag.strip():
        parts += ["", "**Diagnostics**", "```", diag.strip(), "```"]
    return title, "\n".join(parts)


def github_issue_url(title: str, body: str, repo: str = GITHUB_REPO) -> str:
    base = f"https://github.com/{repo}/issues/new?labels=bug&title={urllib.parse.quote(title)}&body="
    room = MAX_URL - len(base)
    enc = urllib.parse.quote(body)
    if len(enc) > room:  # cut the diagnostics end, keep the description
        note = "\n...(cut - use Copy report and paste the rest)\n```"
        lo, hi = 0, len(body)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(urllib.parse.quote(body[:mid] + note)) <= room:
                lo = mid
            else:
                hi = mid - 1
        enc = urllib.parse.quote(body[:lo] + note)
    return base + enc


def mailto_url(title: str, body: str, to: str = SUPPORT_EMAIL) -> str:
    short = body if len(body) <= MAX_MAILTO else body[:MAX_MAILTO] + "\n...(cut - the full report is attached " \
                                                                        "or on your clipboard)"
    return f"mailto:{urllib.parse.quote(to)}?subject={urllib.parse.quote(title)}&body={urllib.parse.quote(short)}"


def send_email(settings: dict, title: str, body: str, to: str = SUPPORT_EMAIL) -> bool:
    """Send through the district's alert email settings (Tools > Upload alerts). False if those aren't set up."""
    from . import alerts
    a = alerts.get(settings)
    if not to or not a.get("smtp_host"):
        return False
    return alerts.send_email(a, f"[{APP_NAME}] {title}", body, to=to,
                             attachments=[("bug_report.txt", body.encode("utf-8"), "text/plain")])
