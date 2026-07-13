from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class SummaryResult:
    summary: str
    mood: str


class LocalSummarizer:
    def __init__(self, command: str | None = None) -> None:
        self.command = command or os.environ.get("XIAOLONGXIA_CMD")

    def summarize(self, content: str) -> SummaryResult:
        content = content.strip()
        if not content:
            return SummaryResult("还没有写内容。先写一点，本地小助手再帮你归纳。", "sleepy")

        if self.command:
            external = self._try_external_summary(content)
            if external:
                return SummaryResult(external, self._infer_mood(content, external))

        return SummaryResult(self._fallback_summary(content), self._infer_mood(content, content))

    def infer_mood(self, content: str) -> str:
        return self._infer_mood(content, content)

    def _try_external_summary(self, content: str) -> str | None:
        try:
            result = subprocess.run(
                self.command,
                input=content,
                text=True,
                shell=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        output = result.stdout.strip()
        return output if result.returncode == 0 and output else None

    def _fallback_summary(self, content: str) -> str:
        lines = [line.strip(" -\t") for line in content.splitlines() if line.strip()]
        highlights = lines[:3]
        word_count = len(content)

        if highlights:
            bullets = "\n".join(f"- {item}" for item in highlights)
        else:
            bullets = f"- {content[:80]}"

        return (
            f"本周记录约 {word_count} 个字符。\n\n"
            "重点摘取：\n"
            f"{bullets}\n\n"
            "成长观察：这周已经留下了可追踪的工作记录，后续可以继续补充结果、困难和下一步计划。"
        )

    def _infer_mood(self, content: str, summary: str) -> str:
        text = f"{content}\n{summary}"
        happy_words = ("表扬", "完成", "上线", "突破", "获奖", "升职", "优秀", "顺利")
        tired_words = ("迟到", "延期", "阻塞", "失败", "加班", "疲惫", "困难", "卡住")

        happy_score = sum(1 for word in happy_words if word in text)
        tired_score = sum(1 for word in tired_words if word in text)

        if tired_score > happy_score:
            return "tired"
        if happy_score > 0:
            return "happy"
        return "calm"
