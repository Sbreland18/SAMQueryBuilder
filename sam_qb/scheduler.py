"""Small wrapper around Windows Task Scheduler for the newer headless jobs (backups, data-quality snapshots)."""
from __future__ import annotations

import subprocess
import sys

PREFIX = "SAM Ad Hoc Query Builder - "


def name_variants(prefix: str, name: str, extra=()) -> list[str]:
    """Every name this job's task may have had: with/without the district (the district part is added only once a
    second district exists) plus any name recorded when it was scheduled."""
    from .districts import task_label
    from .paths import active_district, district_name
    out = [prefix + task_label(name), prefix + name, f"{prefix}{district_name(active_district())} - {name}"]
    out += [x for x in extra if x]
    return list(dict.fromkeys(out))


def delete_names(names) -> list[str]:
    """Remove scheduled tasks by name (missing ones are ignored). Returns the names removed."""
    if sys.platform != "win32":
        return []
    done = []
    for tn in names:
        r = subprocess.run(["schtasks", "/Delete", "/F", "/TN", tn], capture_output=True, text=True)
        if r.returncode == 0:
            done.append(tn)
    return done


def task_name(label: str) -> str:
    from .districts import task_label
    return PREFIX + task_label(label)


def create(label: str, flag: str, sc: str = "WEEKLY", time: str = "06:00", day: str = "SUN") -> str:
    """sc: DAILY | WEEKLY (day MON..SUN) | MONTHLY (day 1..28)."""
    if sys.platform != "win32":
        raise RuntimeError("Scheduling uses Windows Task Scheduler (run this on the Windows PC).")
    from .uploader import launch_args
    cmd = launch_args(flag, "")[:-1]
    delete_names(name_variants(PREFIX, label))      # never leave an older copy of the same job running
    args = ["schtasks", "/Create", "/F", "/TN", task_name(label), "/TR", " ".join(f'"{c}"' for c in cmd),
            "/SC", sc, "/ST", time or "06:00"]
    if sc == "WEEKLY":
        args += ["/D", day or "SUN"]
    elif sc == "MONTHLY":
        args += ["/D", str(day or 1)]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr).strip())
    return (r.stdout + r.stderr).strip()


def delete(label: str) -> str:
    if sys.platform != "win32":
        return "Not on Windows."
    done = delete_names(name_variants(PREFIX, label))
    return "Removed the scheduled task." if done else "No scheduled task was found."
