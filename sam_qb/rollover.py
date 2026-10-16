"""Year-end / new-year rollover checklist. Progress lives in settings["rollover"][school_year] = [done keys]."""
from __future__ import annotations

import datetime as dt

from . import district

ITEMS = [
    # key, title, detail, action (handled by the dialog) or ""
    ("school_year", "Set the new school year in District Settings",
     "School year is the END year (2027 for 2026-27). OneRoster, SDS and term names use it.", "district"),
    ("live_schedule", "Mark the new year's schedules Live in SAM",
     "Every package reads the Live schedule (Schedule.LiveFlag = 1) for classes, homerooms and counselors. "
     "Until the new schedules are live, class files still show last year.", ""),
    ("codes", "Re-run 'Find your SAM codes' and import them",
     "New schools, grade or enrollment codes show up here. File > SAM Codes & Schools > Import.", "codes"),
    ("schools", "Check the school list (SchoolIDs and names)",
     "Add new schools, remove closed ones, and check the Schools: limits on each export package.", "codes"),
    ("seniors", "Withdraw / graduate last year's seniors in SAM",
     "Otherwise they stay in every roster and account file.", ""),
    ("baselines", "Reset the upload safety-net baselines",
     "Summer and the first days of school change row counts a lot. Resetting stops the safety net from holding "
     "the first uploads of the year.", "baselines"),
    ("pause", "Pause or re-time nightly uploads over the summer",
     "Some vendors archive students who disappear; check each vendor's summer guidance.", "uploads"),
    ("checker", "Run the export checker on every package",
     "Check exported files... on each package after the first new-year CAC Agent run.", "exports"),
    ("cleanup", "Run the data cleanup reports",
     "New students without contacts, phones, emails or homerooms are most common in August.", "cleanup"),
    ("register", "Review vendor agreements in the privacy register",
     "Renew agreements that expire this year and remove vendors you no longer use.", "register"),
    ("accounts", "Create new accounts (Google / AD / Entra / Apple)",
     "Run the account packages for new students and staff; disable accounts for leavers.", "exports"),
    ("archive", "Archive last year's upload folders",
     "Move each profile's 'archive' subfolder somewhere safe and clear old CSVs.", ""),
]


def year_key(settings: dict) -> str:
    return str(district.get(settings).get("school_year") or "")


def expected_year(today: dt.date | None = None) -> int:
    t = today or dt.date.today()
    return t.year + 1 if t.month >= 7 else t.year


def done(settings: dict) -> set[str]:
    return set((settings.get("rollover") or {}).get(year_key(settings), []))


def set_done(settings: dict, key: str, value: bool):
    roll = settings.setdefault("rollover", {})
    cur = set(roll.get(year_key(settings), []))
    (cur.add if value else cur.discard)(key)
    roll[year_key(settings)] = sorted(cur)


def auto_checks(settings: dict) -> dict[str, tuple[bool, str]]:
    """Checks the app can verify itself: {key: (ok, message)}."""
    out = {}
    yr = year_key(settings)
    exp = expected_year()
    out["school_year"] = (yr == str(exp), f"District Settings school year is {yr or 'blank'}; "
                                          f"today's school year ends in {exp}.")
    n = len(settings.get("schools", []))
    out["schools"] = (n > 0, f"{n} school(s) loaded." if n else "No schools loaded yet.")
    return out


def reset_baselines(settings: dict) -> int:
    from .uploader import load_history, save_history
    n = 0
    for p in settings.get("upload_profiles", []):
        h = load_history(p["name"])
        if h.get("last_good_counts"):
            h["last_good_counts"] = {}
            save_history(p["name"], h)
            n += 1
    return n
