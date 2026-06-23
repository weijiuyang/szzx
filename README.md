# 数智中心

数智中心是一个本地优先的 Qt 桌面原型，用于周报、AI 摘要、项目协作和桌宠陪伴。

This first version is intentionally simple:

- no login
- local PIN unlock
- local JSON storage
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
In development, local data is stored in `local_data/szzx.json`.
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
  "version": "0.1.45",
  "download_url": "https://example.com/SZZXLocalDesk.exe",
  "notes": "项目进展流取消查看权限限制，所有人都能查看成员配置、项目周报、文档和完成代办。",
  "history": [
    {
      "version": "0.1.45",
      "date": "2026-06-23",
      "notes": "项目进展流取消查看权限限制，所有人都能查看成员配置、项目周报、文档和完成代办。"
    }
  ]
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

GitHub Actions can also build and publish the Windows exe to GitHub Releases.
Open `Actions` -> `Build Windows App` -> `Run workflow`, then fill:

```text
release_version: 0.1.1
release_notes: 本次更新说明
```

The workflow creates release tag `v0.1.1` and uploads `SZZXLocalDesk.exe`.
Pushing a git tag like `v0.1.1` also publishes a release automatically.

For local Windows distribution, build `dist\SZZXLocalDesk.exe` on one Windows
machine, then share that exe inside the LAN. The app shows peer versions in the
LAN page. When a same-OS peer has a newer version and an update package, users
can click `下载更新` to pull the installer from that peer into their Downloads
folder.

By default, Windows packaged builds share the running `SZZXLocalDesk.exe`.
Development builds look for `dist/SZZXLocalDesk.exe` on Windows and
`dist/SZZXLocalDesk-mac.dmg` on macOS. To force a specific package path, start
the app with `SZZX_UPDATE_PACKAGE=/path/to/installer`.

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

数智中心使用 UDP `45454` 端口发现同一局域网内运行中的客户端。
应用没有登录和好友申请系统，局域网内发现的同事会默认显示。
可以在应用内 `PIN` 设置面板修改自己的可见名称。

## Project Shape

```text
szzx_local/
  __main__.py       app entry
  app.py            Qt bootstrap
  ai.py             local AI adapter
  database.py       JSON persistence
  models.py         shared dataclasses
  pet.py            transparent desktop pet
  pin.py            PIN hashing/verification
  ui.py             windows and widgets
```
