"""Authenticode code signing for the EXE and installer (removes Windows SmartScreen 'unknown publisher').

Needs a code-signing certificate (OV or EV) and signtool.exe from the Windows SDK. The certificate can be in the
Windows certificate store / on a USB token (use its SHA-1 thumbprint) or a .pfx file (password asked at build
time - never saved).
"""
from __future__ import annotations

import glob
import os
import shutil

DEFAULT_TIMESTAMP = "http://timestamp.digicert.com"


def find_signtool() -> str:
    exe = shutil.which("signtool.exe") or shutil.which("signtool")
    if exe:
        return exe
    for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.environ.get("ProgramFiles", r"C:\Program Files")):
        hits = sorted(glob.glob(os.path.join(base, "Windows Kits", "10", "bin", "*", "x64", "signtool.exe")),
                      reverse=True)
        if hits:
            return hits[0]
    return ""


def sign_command(cfg: dict, target: str, pfx_password: str = "") -> list[str]:
    """signtool arguments for one file. cfg: signtool, mode ('store'|'pfx'), thumbprint, pfx, timestamp, desc."""
    st = cfg.get("signtool") or find_signtool()
    if not st:
        raise RuntimeError("signtool.exe not found - install the Windows SDK (Signing Tools) or browse to it.")
    args = [st, "sign", "/fd", "SHA256", "/tr", cfg.get("timestamp") or DEFAULT_TIMESTAMP, "/td", "SHA256"]
    if cfg.get("desc"):
        args += ["/d", cfg["desc"]]
    if cfg.get("mode") == "pfx":
        if not cfg.get("pfx"):
            raise RuntimeError("Choose the .pfx certificate file.")
        args += ["/f", cfg["pfx"]]
        if pfx_password:
            args += ["/p", pfx_password]
    else:
        tp = (cfg.get("thumbprint") or "").replace(" ", "")
        if tp:
            args += ["/sha1", tp]
        else:
            args += ["/a"]           # best certificate in the store
    return args + [target]


def verify_command(cfg: dict, target: str) -> list[str]:
    st = cfg.get("signtool") or find_signtool()
    return [st, "verify", "/pa", "/v", target]


def mask(args: list[str]) -> list[str]:
    """For the build log - hide the PFX password."""
    out, hide = [], False
    for a in args:
        out.append("********" if hide else a)
        hide = a == "/p"
    return out
