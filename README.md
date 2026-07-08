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
  "version": "0.1.124",
  "download_url": "https://example.com/SZZXLocalDesk.exe",
  "notes": "Windows 打包也会携带共享数据种子，并与 macOS 共用种子生成逻辑，避免安装包只同步到旧项目数量。",
  "history": [
    {
      "version": "0.1.124",
      "date": "2026-07-08",
      "notes": "Windows 打包也会携带共享数据种子，并与 macOS 共用种子生成逻辑，避免安装包只同步到旧项目数量。"
    },
    {
      "version": "0.1.123",
      "date": "2026-07-08",
      "notes": "项目成员配置按同项目、同姓名和同角色去重，避免成员镜像、统计卡和成员列表重复显示同一个人。"
    },
    {
      "version": "0.1.122",
      "date": "2026-07-08",
      "notes": "macOS 安装包会携带共享数据种子，启动时自动补齐旧库缺失项目；局域网页同版本安装包也可直接下载。"
    },
    {
      "version": "0.1.121",
      "date": "2026-07-08",
      "notes": "macOS 安装包找不到 DMG 时会自动把当前 App 打成 zip 并在局域网共享，避免高版本显示无安装包。"
    },
    {
      "version": "0.1.120",
      "date": "2026-07-08",
      "notes": "局域网同步会比较项目记录内容并更新负责人、简介和链接；自动同步会根据记录数量判断是否补缺，避免项目停留在旧负责人。"
    },
    {
      "version": "0.1.119",
      "date": "2026-07-08",
      "notes": "项目链接图标略微放大，并在鼠标悬停时显示浅色圆形反馈。"
    },
    {
      "version": "0.1.118",
      "date": "2026-07-08",
      "notes": "项目链接入口统一改为小号无边框图标，并在项目列表和个人主页参与项目卡片中补充跳转链接。"
    },
    {
      "version": "0.1.117",
      "date": "2026-07-08",
      "notes": "我的面板参与项目卡片新增项目链接入口，可从项目名旁直接打开主要或备用项目地址。"
    },
    {
      "version": "0.1.116",
      "date": "2026-07-08",
      "notes": "修复启动时项目进展排序可能崩溃的问题，并在分配代办给低版本在线成员时提示先升级。"
    },
    {
      "version": "0.1.115",
      "date": "2026-07-06",
      "notes": "项目长流程新增可选 UI/设计环节：有 UI 时先流转给唯一 UI，支持提交开发、跳过 UI、记录链接和上传设计图。"
    },
    {
      "version": "0.1.114",
      "date": "2026-07-06",
      "notes": "项目分配代办新增开发-测试-产品验收长流程，支持待开发、开发中、待测试、待验收状态和完整流转详情。"
    },
    {
      "version": "0.1.113",
      "date": "2026-07-04",
      "notes": "测试角色可在项目页上传测试文档，文档上传权限与负责人周报权限分离。"
    },
    {
      "version": "0.1.112",
      "date": "2026-07-04",
      "notes": "徽章墙更换为浅绿灰收藏墙背景，并为徽章卡片增加柔和纸感底色和边框。"
    },
    {
      "version": "0.1.111",
      "date": "2026-07-04",
      "notes": "项目页负责人周报/文档控件改为上下排布，减少侧栏里的横向挤压。"
    },
    {
      "version": "0.1.110",
      "date": "2026-07-04",
      "notes": "项目页日报流和右侧日报/周报文档区域加高，缓解表单拥挤。"
    },
    {
      "version": "0.1.109",
      "date": "2026-07-04",
      "notes": "项目页右侧日报和周报/文档合并为紧凑下半区，并与日报流高度对齐。"
    },
    {
      "version": "0.1.108",
      "date": "2026-07-04",
      "notes": "项目页改为分段对齐：代办面板对齐项目进展流，日报表单对齐日报流。"
    },
    {
      "version": "0.1.107",
      "date": "2026-07-04",
      "notes": "个人主页项目日志中关联代办的日报支持点击打开代办详情。"
    },
    {
      "version": "0.1.106",
      "date": "2026-07-04",
      "notes": "移除代办卡片中的详情按钮，保留整张卡片点击查看详情，减少操作区占用。"
    },
    {
      "version": "0.1.105",
      "date": "2026-07-04",
      "notes": "代办卡片支持整卡点击和详情按钮查看完整详情，列表中的进展记录改为短摘要展示。"
    },
    {
      "version": "0.1.104",
      "date": "2026-07-04",
      "notes": "桌宠新增代办提醒：收到分配、分配出去的代办被完成或新增记录时会弹出提示；双击桌宠可隐藏。"
    },
    {
      "version": "0.1.103",
      "date": "2026-07-04",
      "notes": "优化项目代办明细弹窗，代办分配、截止和开始信息改为多行展示，并为每条代办增加详情入口。"
    },
    {
      "version": "0.1.102",
      "date": "2026-07-04",
      "notes": "修复项目顶部代办统计卡打开报错的问题，代办明细弹窗可正常展示截止、开始和关联日报信息。"
    },
    {
      "version": "0.1.101",
      "date": "2026-07-04",
      "notes": "分配代办开始后按钮切换为记录，可弹窗填写进展日报并自动关联到该代办。"
    },
    {
      "version": "0.1.100",
      "date": "2026-07-04",
      "notes": "优化项目代办展示和分配表单：代办卡片信息拆成多行，期限改为可取消选择的快捷按钮。"
    },
    {
      "version": "0.1.99",
      "date": "2026-07-04",
      "notes": "完成代办生成的日报会关联原代办，日报流和消息提醒支持点击查看代办详情、开始完成时间和关联日报。"
    },
    {
      "version": "0.1.98",
      "date": "2026-07-04",
      "notes": "优化我的面板代办卡片排版，分配信息和时间保持一行，截止时间有值时单独换行展示。"
    },
    {
      "version": "0.1.97",
      "date": "2026-07-04",
      "notes": "修复我的面板中代办分栏内容垂直居中的问题，少量代办时标题和卡片保持靠上展示。"
    },
    {
      "version": "0.1.96",
      "date": "2026-07-04",
      "notes": "左侧文档库下新增功能介绍独立看板，集中说明各模块用途、常用操作和版本日志入口。"
    },
    {
      "version": "0.1.95",
      "date": "2026-07-03",
      "notes": "未设置本人钉钉号时，桌宠会每日提醒一次，并提示到左下角名字/PIN中填写。"
    },
    {
      "version": "0.1.94",
      "date": "2026-07-03",
      "notes": "局域网在线同事和日志视角姓名支持点击个人主页，并显示可用的钉钉聊天入口。"
    },
    {
      "version": "0.1.93",
      "date": "2026-07-03",
      "notes": "项目顶部成员、代办、日报、周报和文档统计卡支持点击查看明细。"
    },
    {
      "version": "0.1.92",
      "date": "2026-07-03",
      "notes": "个人主页参与项目卡片支持点击跳转到项目面板对应项目。"
    },
    {
      "version": "0.1.91",
      "date": "2026-07-03",
      "notes": "压缩个人主页参与项目卡片和列表留白，卡片不再展示项目简介。"
    },
    {
      "version": "0.1.90",
      "date": "2026-07-03",
      "notes": "个人主页参与项目改为偏正方形卡片，并支持横向滑动浏览。"
    },
    {
      "version": "0.1.89",
      "date": "2026-07-03",
      "notes": "优化我的任务卡片排版，分配对象、时间和已分配天数保持单行显示。"
    },
    {
      "version": "0.1.88",
      "date": "2026-07-03",
      "notes": "项目成员列表新增成员日报入口，可查看成员在当前项目内的全部日报。"
    },
    {
      "version": "0.1.87",
      "date": "2026-07-03",
      "notes": "手动刷新改为后台同步同事数据，点击刷新不再等待网络连接完成。"
    },
    {
      "version": "0.1.86",
      "date": "2026-07-03",
      "notes": "新增共享记录删除同步，文档、日报、周报、待办等由控制人删除后不会再被其他电脑旧数据恢复。"
    },
    {
      "version": "0.1.85",
      "date": "2026-07-03",
      "notes": "局域网自动同步改为后台拉取，避免连接同事电脑或读取快照时卡住主界面。"
    },
    {
      "version": "0.1.84",
      "date": "2026-07-03",
      "notes": "修复消息提醒中项目名和完成提示被拆行的问题，保持紧凑单行展示。"
    },
    {
      "version": "0.1.83",
      "date": "2026-07-03",
      "notes": "压缩可点击姓名的行高，日报流和消息提醒恢复紧凑布局。"
    },
    {
      "version": "0.1.82",
      "date": "2026-07-03",
      "notes": "人名链接改为普通正文大小，更多姓名展示支持点击进入个人主页。"
    },
    {
      "version": "0.1.81",
      "date": "2026-07-03",
      "notes": "姓名主页新增参与项目卡片，点击姓名可同时查看该成员参与项目和项目日志。"
    },
    {
      "version": "0.1.80",
      "date": "2026-07-03",
      "notes": "钉钉聊天图标去掉外圈和按钮底色，缩小为更轻量的姓名旁图标。"
    },
    {
      "version": "0.1.79",
      "date": "2026-07-03",
      "notes": "钉钉聊天入口由文字“聊”改为钉钉图标按钮，尺寸随姓名行适配。"
    },
    {
      "version": "0.1.78",
      "date": "2026-07-03",
      "notes": "钉钉聊天按钮在 macOS 上打开联系人后自动尝试进入发消息界面，减少手动再点一次。"
    },
    {
      "version": "0.1.77",
      "date": "2026-07-03",
      "notes": "修复分配任务完成后同步不到分配人面板的问题，并自动修复历史重复的已完成任务记录。"
    },
    {
      "version": "0.1.76",
      "date": "2026-07-03",
      "notes": "姓名点击改为查看系统内项目日志；配置钉钉号的人名旁显示聊天按钮；修复日报流姓名行被裁切的问题。"
    },
    {
      "version": "0.1.75",
      "date": "2026-07-03",
      "notes": "钉钉号改为每个人在名字/PIN 中自行配置并随姓名同步，项目成员配置不再填写他人钉钉号。"
    },
    {
      "version": "0.1.74",
      "date": "2026-07-03",
      "notes": "成员配置新增钉钉号；项目成员、负责人和日报作者姓名可点击打开钉钉聊天。"
    },
    {
      "version": "0.1.73",
      "date": "2026-07-03",
      "notes": "项目日报流卡片高度按日报内容自适应，短日报更紧凑，长日报完整展开。"
    },
    {
      "version": "0.1.72",
      "date": "2026-07-02",
      "notes": "上传文档支持 zip、rar、7z 等压缩包，并自动归类为压缩包。"
    },
    {
      "version": "0.1.71",
      "date": "2026-07-02",
      "notes": "文档卡片取消下载按钮，只保留打开和删除操作。"
    },
    {
      "version": "0.1.70",
      "date": "2026-07-01",
      "notes": "项目面板左侧项目列表加高，默认可看到更多项目卡，并将新建项目区域下移。"
    },
    {
      "version": "0.1.69",
      "date": "2026-06-30",
      "notes": "新增开机自动启动：默认开启，可在名字/PIN 设置里勾选或取消。"
    },
    {
      "version": "0.1.68",
      "date": "2026-06-30",
      "notes": "桌宠启动默认隐藏；提醒时临时出现，提醒结束或点击桌宠后自动隐藏。"
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
