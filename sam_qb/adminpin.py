"""Admin PIN - locks the screens that can change what leaves the district (uploads and schedules, alerts,
report emails, the SAM connection, District Settings, restoring a backup, managing districts).

This prevents accidental changes on a shared PC; it is not a security boundary against someone who can edit
files in %APPDATA%. Every unlock and PIN change is written to the change log.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time

UNLOCK_MINUTES = 15
_unlocked_until = 0.0

LOCKED = {"uploads": "Package & Upload", "alerts": "Upload alerts", "reports": "Report emails",
          "samdb": "SAM database connection", "district": "District Settings", "restore": "Restore settings",
          "districts": "Manage districts", "pin": "Admin PIN"}


def _hash(pin: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 200_000).hex()


def is_set(settings: dict) -> bool:
    return bool((settings.get("admin_pin") or {}).get("hash"))


def set_pin(settings: dict, pin: str | None):
    """pin None / '' removes it."""
    from .audit import record
    if not pin:
        settings.pop("admin_pin", None)
        record("Admin PIN", "PIN removed")
        return
    if len(pin) < 4:
        raise ValueError("Use at least 4 digits or characters.")
    salt = os.urandom(16)
    settings["admin_pin"] = {"salt": salt.hex(), "hash": _hash(pin, salt)}
    record("Admin PIN", "PIN set or changed")


def check(settings: dict, pin: str) -> bool:
    p = settings.get("admin_pin") or {}
    if not p.get("hash"):
        return True
    ok = hmac.compare_digest(_hash(pin or "", bytes.fromhex(p["salt"])), p["hash"])
    from .audit import record
    record("Admin PIN", "Unlocked" if ok else "Wrong PIN entered")
    return ok


def unlocked() -> bool:
    return time.time() < _unlocked_until


def unlock():
    global _unlocked_until
    _unlocked_until = time.time() + UNLOCK_MINUTES * 60


def lock():
    global _unlocked_until
    _unlocked_until = 0.0


def require(parent, settings: dict, area: str) -> bool:
    """Ask for the PIN (UI) when one is set and the session isn't unlocked. Returns True when allowed."""
    if not is_set(settings) or unlocked():
        return True
    from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox
    pin, ok = QInputDialog.getText(parent, "Admin PIN", f"{LOCKED.get(area, area)} is locked.\nEnter the admin PIN:",
                                   QLineEdit.Password)
    if not ok:
        return False
    if check(settings, pin):
        unlock()
        return True
    QMessageBox.warning(parent, "Admin PIN", "That PIN is not right.")
    return False
