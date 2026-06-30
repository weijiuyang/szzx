from __future__ import annotations

import os
import plistlib
import sys
from pathlib import Path


LAUNCH_AGENT_LABEL = "com.szzx.localdesk"


def is_supported() -> bool:
    return sys.platform in {"darwin", "win32"}


def _current_executable() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    executable = Path(sys.executable)
    return executable if executable.exists() else None


def set_autostart(enabled: bool) -> None:
    if sys.platform == "darwin":
        _set_macos_autostart(enabled)
    elif sys.platform == "win32":
        _set_windows_autostart(enabled)


def autostart_registered() -> bool:
    if sys.platform == "darwin":
        return _macos_autostart_registered()
    if sys.platform == "win32":
        return _windows_autostart_registered()
    return False


def _launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def _set_macos_autostart(enabled: bool) -> None:
    path = _launch_agent_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return

    executable = _current_executable()
    if executable is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [str(executable)],
        "RunAtLoad": True,
        "KeepAlive": False,
    }
    with path.open("wb") as file:
        plistlib.dump(payload, file)


def _macos_autostart_registered() -> bool:
    path = _launch_agent_path()
    if not path.exists():
        return False
    executable = _current_executable()
    try:
        with path.open("rb") as file:
            payload = plistlib.load(file)
    except (OSError, plistlib.InvalidFileException):
        return False
    args = payload.get("ProgramArguments")
    if not isinstance(args, list) or not args:
        return False
    if executable is None:
        return bool(payload.get("RunAtLoad"))
    return bool(payload.get("RunAtLoad")) and Path(str(args[0])) == executable


def _set_windows_autostart(enabled: bool) -> None:
    try:
        import winreg
    except ImportError:
        return
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if not enabled:
            try:
                winreg.DeleteValue(key, LAUNCH_AGENT_LABEL)
            except FileNotFoundError:
                pass
            return
        executable = _current_executable()
        if executable is None:
            return
        winreg.SetValueEx(key, LAUNCH_AGENT_LABEL, 0, winreg.REG_SZ, f'"{executable}"')


def _windows_autostart_registered() -> bool:
    try:
        import winreg
    except ImportError:
        return False
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, LAUNCH_AGENT_LABEL)
    except OSError:
        return False
    executable = _current_executable()
    normalized = str(value).strip().strip('"')
    return bool(normalized) if executable is None else os.path.normcase(normalized) == os.path.normcase(str(executable))
