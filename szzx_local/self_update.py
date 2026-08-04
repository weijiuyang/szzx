from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


def update_cache_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Caches"
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    target = root / "SZZXLocalDesk" / "updates"
    target.mkdir(parents=True, exist_ok=True)
    return target


def clear_old_update_packages(keep: Path | None = None) -> None:
    keep_resolved = keep.resolve() if keep else None
    for path in update_cache_dir().iterdir():
        try:
            if keep_resolved is not None and path.resolve() == keep_resolved:
                continue
            if path.is_file():
                path.unlink()
        except OSError:
            continue


def installed_app_path() -> Path | None:
    executable = Path(sys.executable).resolve()
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        return executable
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        for parent in executable.parents:
            if parent.suffix == ".app":
                return parent
    return None


def start_in_place_update(package: Path) -> bool:
    """Launch a detached helper that waits, replaces this app, and reopens it."""
    installed = installed_app_path()
    if installed is None:
        return False
    package = package.resolve()
    if sys.platform == "win32" and package.suffix.lower() == ".exe":
        return _start_windows_update(package, installed)
    if sys.platform == "darwin" and (
        package.name.lower().endswith(".app.zip") or package.suffix.lower() == ".dmg"
    ):
        return _start_macos_update(package, installed)
    return False


def _start_windows_update(package: Path, installed: Path) -> bool:
    script = update_cache_dir() / "apply-update.ps1"
    log = update_cache_dir() / "apply-update.log"
    script.write_text(
        """
param([int]$OldPid, [string]$Package, [string]$Installed, [string]$Script, [string]$Log)
$ErrorActionPreference = "Stop"
try {
  "$(Get-Date -Format o) Starting update from $Package to $Installed" | Set-Content -LiteralPath $Log -Encoding UTF8
  Wait-Process -Id $OldPid -Timeout 30 -ErrorAction SilentlyContinue
  $deadline = (Get-Date).AddSeconds(30)
  do {
    try {
      Copy-Item -LiteralPath $Package -Destination $Installed -Force
      $copied = $true
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } until ($copied -or (Get-Date) -ge $deadline)
  if (-not $copied) { throw "无法替换旧程序" }
  Start-Process -FilePath $Installed -ArgumentList "--update-restart"
  "$(Get-Date -Format o) Update completed" | Add-Content -LiteralPath $Log -Encoding UTF8
  Start-Sleep -Seconds 2
  Remove-Item -LiteralPath $Package -Force -ErrorAction SilentlyContinue
} catch {
  "$(Get-Date -Format o) Update failed: $($_.Exception.Message)" | Add-Content -LiteralPath $Log -Encoding UTF8
  if (Test-Path -LiteralPath $Installed) {
    Start-Process -FilePath $Installed -ArgumentList "--update-restart" -ErrorAction SilentlyContinue
  }
} finally {
  Remove-Item -LiteralPath $Script -Force -ErrorAction SilentlyContinue
}
""".lstrip(),
        encoding="utf-8-sig",
    )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-OldPid",
                str(os.getpid()),
                "-Package",
                str(package),
                "-Installed",
                str(installed),
                "-Script",
                str(script),
                "-Log",
                str(log),
            ],
            creationflags=flags,
            close_fds=True,
        )
        return True
    except OSError:
        return False


def _start_macos_update(package: Path, installed: Path) -> bool:
    script = update_cache_dir() / "apply-update.sh"
    package_q = shlex.quote(str(package))
    installed_q = shlex.quote(str(installed))
    script_q = shlex.quote(str(script))
    script.write_text(
        f"""#!/bin/sh
set -u
old_pid={os.getpid()}
package={package_q}
installed={installed_q}
script={script_q}
while kill -0 "$old_pid" 2>/dev/null; do sleep 0.25; done
work="$(mktemp -d "${{TMPDIR:-/tmp}}/szzx-update.XXXXXX")" || exit 1
mount_point=""
cleanup() {{
  [ -n "$mount_point" ] && hdiutil detach "$mount_point" -quiet >/dev/null 2>&1
  rm -rf "$work"
  rm -f "$package" "$script"
}}
trap cleanup EXIT
case "$package" in
  *.dmg)
    mount_point="$work/mount"
    mkdir -p "$mount_point"
    hdiutil attach "$package" -nobrowse -readonly -mountpoint "$mount_point" -quiet || exit 1
    source_app="$(find "$mount_point" -maxdepth 2 -name '*.app' -type d | head -1)"
    ;;
  *.app.zip)
    ditto -x -k "$package" "$work/unpacked" || exit 1
    source_app="$(find "$work/unpacked" -maxdepth 2 -name '*.app' -type d | head -1)"
    ;;
  *) exit 1 ;;
esac
[ -n "$source_app" ] || exit 1
replacement="$work/replacement.app"
ditto "$source_app" "$replacement" || exit 1
backup="$work/previous.app"
mv "$installed" "$backup" || exit 1
if ! mv "$replacement" "$installed"; then
  mv "$backup" "$installed"
  exit 1
fi
open "$installed" --args --update-restart
""",
        encoding="utf-8",
    )
    script.chmod(0o700)
    try:
        subprocess.Popen(
            ["/bin/sh", str(script)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        return True
    except OSError:
        return False
