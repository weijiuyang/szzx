# SZZX Local Desk

A local-first Qt desktop prototype for weekly reports, AI summaries, and a small interactive desktop pet.

This first version is intentionally simple:

- no login
- local PIN unlock
- local SQLite storage
- no HTTP client traffic
- optional local AI command integration
- PySide6 desktop UI for macOS and Windows
- LAN presence discovery without login or friend requests

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m szzx_local
```

On Windows:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m szzx_local
```

The default PIN is `1234`. Change it after first unlock from the app settings panel.
In development, local data is stored in `local_data/szzx.db`.
In packaged builds, it is stored in the user's application data directory.
Override it with `SZZX_LOCAL_DATA_DIR`.

## Build A Desktop App

Build on each target operating system. Use the same source code, but create the
macOS app on macOS and the Windows exe on Windows. Python 3.12 or 3.11 is
recommended for packaging; avoid Python 3.13 preview/rc builds.

macOS:

```bash
./scripts/build_macos.sh
```

Output:

```text
dist/SZZXLocalDesk.app
dist/SZZXLocalDesk-mac.dmg
```

Do not open files under `build/SZZXLocalDesk/` directly. Files such as
`build/SZZXLocalDesk/SZZXLocalDesk.pkg` are PyInstaller intermediate archives,
not macOS installer packages.

## Updates

The app can show its current version and check a remote update manifest.
Set `SZZX_UPDATE_URL` to a JSON file like `update.example.json`:

```json
{
  "version": "0.1.1",
  "download_url": "https://example.com/SZZXLocalDesk.exe",
  "notes": "修复问题并优化项目面板。"
}
```

When a newer version is available, the app opens the download URL. Full silent
self-update is intentionally not enabled yet because replacing a running desktop
app requires platform-specific installer/signing work.

Windows, run on a Windows machine:

```powershell
.\scripts\build_windows.ps1
```

Output:

```text
dist\SZZXLocalDesk.exe
```

## Share With The Department

macOS users can open `dist/SZZXLocalDesk-mac.dmg` and drag the app into Applications.
If macOS blocks the app because it is unsigned, right-click the app and choose Open once.

Windows users should receive the `dist\SZZXLocalDesk.exe` built on a Windows machine.
For a more formal Windows installer later, wrap that exe with Inno Setup or NSIS.

## Optional local AI command

If your internal "小龙虾" service exposes a local CLI, set:

```bash
export XIAOLONGXIA_CMD="/path/to/xiaolongxia summarize"
```

The app sends the weekly report content to the command on stdin and reads the summary from stdout.
If the command is not set, the app uses a local rule-based summary so the prototype stays fully offline.

## LAN Discovery

SZZX uses UDP broadcast on port `45454` to discover other running SZZX clients on the same LAN.
There is no login and no friend request system. Everyone discovered on the LAN is shown by default.
Change your visible name from the in-app `PIN` settings panel.

## Project Shape

```text
szzx_local/
  __main__.py       app entry
  app.py            Qt bootstrap
  ai.py             local AI adapter
  database.py       SQLite persistence
  models.py         shared dataclasses
  pet.py            transparent desktop pet
  pin.py            PIN hashing/verification
  ui.py             windows and widgets
```
