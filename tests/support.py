"""Shared helpers: load the extension-less program as a module and locate rclone."""
import importlib.machinery
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "icloud-sync"
sys.dont_write_bytecode = True


def load_program():
    """Import ./icloud-sync. XDG_* must already point at a sandbox: paths are computed at import time."""
    loader = importlib.machinery.SourceFileLoader("icloud_sync_program", str(SCRIPT))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


def find_rclone():
    """Path of an rclone new enough for bisync as we use it, or None."""
    for cand in (shutil.which("rclone"), os.path.expanduser("~/.local/bin/rclone")):
        if cand and os.access(cand, os.X_OK):
            out = subprocess.run([cand, "version"], capture_output=True, text=True).stdout
            m = re.search(r"rclone v(\d+)\.(\d+)", out)
            if m and (int(m.group(1)), int(m.group(2))) >= (1, 69):
                return cand
    return None
