"""PGP encryption of export files for vendors that require it.

Uses GnuPG (gpg / Gpg4win) when it is installed, otherwise the pure-Python PGPy library. Only the vendor's
PUBLIC key is needed; files are encrypted to it and get a .pgp (binary) or .asc (armored) extension.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _import_pgpy():
    """PGPy still imports the 'imghdr' module, which Python 3.13 removed - provide a tiny stand-in."""
    if "imghdr" not in sys.modules:
        try:
            import imghdr  # noqa: F401
        except ImportError:
            import types
            stub = types.ModuleType("imghdr")
            stub.what = lambda *a, **k: None
            stub.tests = []
            sys.modules["imghdr"] = stub
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import pgpy
    return pgpy


def find_gpg() -> str | None:
    exe = shutil.which("gpg")
    if exe:
        return exe
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.environ.get("ProgramFiles", r"C:\Program Files")):
            p = Path(base) / "GnuPG" / "bin" / "gpg.exe"
            if p.exists():
                return str(p)
    return None


def key_info(key_file: str) -> str:
    """Short description of a public key (user id + fingerprint) for the UI."""
    try:
        pgpy = _import_pgpy()
        key, _ = pgpy.PGPKey.from_file(key_file)
        uid = key.userids[0] if key.userids else None
        return f"{uid.name if uid else 'key'} <{uid.email if uid else ''}>  fingerprint {key.fingerprint}"
    except ImportError:
        return Path(key_file).name
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Not a usable PGP public key: {e}") from e


def encrypt_file(src: Path, key_file: str, armor: bool = False, log=None) -> Path:
    src = Path(src)
    out = src.with_name(src.name + (".asc" if armor else ".pgp"))
    gpg = find_gpg()
    if gpg:
        args = [gpg, "--batch", "--yes", "--trust-model", "always", "--recipient-file", key_file, "--output",
                str(out)] + (["--armor"] if armor else []) + ["--encrypt", str(src)]
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode == 0:
            if log:
                log(f"Encrypted {src.name} -> {out.name} (GnuPG)")
            return out
        if log:
            log(f"GnuPG could not encrypt ({r.stderr.strip()[:200]}); trying PGPy")
    try:
        pgpy = _import_pgpy()
    except ImportError as e:
        raise RuntimeError("PGP encryption needs GnuPG (Gpg4win) or the PGPy package.") from e
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        key, _ = pgpy.PGPKey.from_file(key_file)
        if key.is_public is False:
            key = key.pubkey
        msg = pgpy.PGPMessage.new(src.read_bytes(), file=True, filename=src.name)
        enc = key.encrypt(msg)
    if armor:
        out.write_text(str(enc), encoding="ascii")
    else:
        out.write_bytes(bytes(enc))
    if log:
        log(f"Encrypted {src.name} -> {out.name} (PGPy)")
    return out
