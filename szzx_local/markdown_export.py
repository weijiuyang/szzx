from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any


def _inline(value: object) -> str:
    return " ".join(str(value).strip().split()).replace("\\", "\\\\").replace("|", "\\|")


def write_owned_projects_weekly_markdown(
    path: Path,
    owner: str,
    start_day: date,
    end_day: date,
    projects: list[dict[str, Any]],
) -> None:
    lines = [
        "# 负责项目近一周进展汇总",
        "",
        f"> 负责人：{_inline(owner)}  ",
        f"> 时间范围：{start_day:%Y-%m-%d} 至 {end_day:%Y-%m-%d}  ",
        f"> 共 {len(projects)} 个负责项目，按项目汇总最近 7 天的日报、记录和项目进展流。",
        "",
    ]

    if not projects:
        lines.extend(["这段时间没有可导出的负责项目记录。", ""])

    for project in projects:
        activities = project["activities"]
        lines.extend([
            f"## {_inline(project['name'])}",
            "",
            f"- 状态：{_inline(project['status'])}",
            f"- 负责人：{_inline(project['owner'])}",
            f"- 近一周记录：{len(activities)} 条",
        ])
        description = _inline(project.get("description", ""))
        if description:
            lines.append(f"- 项目说明：{description}")
        lines.append("")

        if not activities:
            lines.extend(["本周暂无日报或项目进展记录。", ""])
            continue

        current_day = ""
        for item in activities:
            if item["day"] != current_day:
                current_day = item["day"]
                lines.extend([f"### {_inline(current_day)}", ""])
            lines.extend([
                f"**{_inline(item['time'])} · {_inline(item['type'])} · {_inline(item['actor'])}**",
                "",
                _inline(item["content"]),
                "",
            ])

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
