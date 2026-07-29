from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .database import Database
from .dingtalk_config import bot_credentials


LOGGER = logging.getLogger("szzx.dingtalk-daily")
CONVERSATION_SETTING = "dingtalk_daily_open_conversation_id"
SESSION_WEBHOOK_SETTING = "dingtalk_daily_session_webhook"
SESSION_WEBHOOK_EXPIRES_SETTING = "dingtalk_daily_session_webhook_expires_at"


class DingTalkDailyBot:
    def __init__(self, db: Database, client_id: str, client_secret: str, robot_code: str = "") -> None:
        self.db = db
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.robot_code = robot_code.strip() or self.client_id
        self._access_token = ""
        self._access_token_expires_at = 0.0
        self._token_lock = threading.Lock()

    @classmethod
    def from_config(cls, db: Database) -> DingTalkDailyBot | None:
        credentials = bot_credentials(db, "daily_report_bot")
        client_id = credentials["app_key"]
        client_secret = credentials["app_secret"]
        if not client_id or not client_secret:
            LOGGER.info("未配置钉钉日报机器人，跳过日报 Stream")
            return None
        return cls(
            db,
            client_id,
            client_secret,
            credentials["robot_code"],
        )

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self._run_stream, name="dingtalk-daily-stream", daemon=True)
        thread.start()
        return thread

    def _run_stream(self) -> None:
        try:
            import dingtalk_stream
        except ImportError:
            LOGGER.exception("缺少 dingtalk-stream 依赖")
            return

        bot = self

        class Handler(dingtalk_stream.ChatbotHandler):
            async def process(self, callback: object):
                try:
                    message = dingtalk_stream.ChatbotMessage.from_dict(
                        getattr(callback, "data", {}) if not isinstance(callback, dict) else callback.get("data", {})
                    )
                    conversation_id = str(
                        getattr(message, "conversation_id", "")
                        or getattr(message, "conversationId", "")
                    ).strip()
                    text_obj = getattr(message, "text", None)
                    text = str(getattr(text_obj, "content", "") or "").strip()
                    sender_name = str(
                        getattr(message, "sender_nick", "")
                        or getattr(message, "senderNick", "")
                    ).strip()
                    sender_staff_id = str(
                        getattr(message, "sender_staff_id", "")
                        or getattr(message, "senderStaffId", "")
                    ).strip()
                    bot.db.remember_dingtalk_staff_id(sender_name, sender_staff_id)
                    session_webhook = str(
                        getattr(message, "session_webhook", "")
                        or getattr(message, "sessionWebhook", "")
                    ).strip()
                    session_webhook_expires_at = str(
                        getattr(message, "session_webhook_expired_time", "")
                        or getattr(message, "sessionWebhookExpiredTime", "")
                    ).strip()
                    if session_webhook:
                        bot.db.set_setting(SESSION_WEBHOOK_SETTING, session_webhook)
                        bot.db.set_setting(
                            SESSION_WEBHOOK_EXPIRES_SETTING,
                            session_webhook_expires_at,
                        )
                    if not conversation_id:
                        self.reply_text("没有识别到群会话，绑定日报群失败。", message)
                    elif text == "绑定日报群" or not bot.conversation_id():
                        bot.db.set_setting(CONVERSATION_SETTING, conversation_id)
                        self.reply_text("日报群已绑定。之后可由数智中心服务器发送昨天的全员项目日报。", message)
                        LOGGER.info("钉钉日报群已绑定 conversation_id=%s", conversation_id)
                    else:
                        self.reply_text("如需将日报发送到本群，请发送：绑定日报群", message)
                    return dingtalk_stream.AckMessage.STATUS_OK, "OK"
                except Exception:
                    LOGGER.exception("处理钉钉日报机器人消息失败")
                    return dingtalk_stream.AckMessage.STATUS_SYSTEM_EXCEPTION, "processing failed"

        credential = dingtalk_stream.Credential(self.client_id, self.client_secret)
        client = dingtalk_stream.DingTalkStreamClient(credential)
        client.register_callback_handler(dingtalk_stream.chatbot.ChatbotMessage.TOPIC, Handler())
        LOGGER.info("正在启动钉钉日报机器人 Stream")
        client.start_forever()

    def conversation_id(self) -> str:
        return (self.db.get_setting(CONVERSATION_SETTING) or "").strip()

    def send_daily_reports(self, report_day: date) -> dict[str, int]:
        conversation_id = self.conversation_id()
        if not conversation_id:
            raise RuntimeError("日报群尚未绑定。请在目标钉钉群里 @日报机器人 发送“绑定日报群”。")
        reports = self.db.daily_reports_between(report_day, report_day, mine_only=False)
        is_departed = getattr(self.db, "is_departed_colleague", lambda name: False)
        reports = [
            report for report in reports
            if not is_departed(str(report.get("member_name", "")))
        ]
        expected_members = self._expected_daily_report_members(report_day)
        if not reports and not expected_members:
            raise ValueError(f"{report_day:%Y-%m-%d} 没有日报，也没有需要提交日报的项目成员。")
        messages = self._markdown_messages(report_day, reports, expected_members)
        for index, markdown in enumerate(messages, start=1):
            title = f"{report_day:%m月%d日}全员项目日报"
            if len(messages) > 1:
                title += f"（{index}/{len(messages)}）"
            mentioned_user_ids = [
                str(member.get("dingtalk_id", "")).strip()
                for member in expected_members.values()
                if (
                    str(member.get("dingtalk_id", "")).strip()
                    and f"@{str(member.get('dingtalk_id', '')).strip()}" in markdown
                )
            ]
            self._send_group_markdown(
                conversation_id,
                title,
                markdown,
                mentioned_user_ids=mentioned_user_ids,
            )
        return {"report_count": len(reports), "message_count": len(messages)}

    def _expected_daily_report_members(self, report_day: date) -> dict[str, dict[str, Any]]:
        members: dict[str, dict[str, Any]] = {}
        resting_member_keys = {
            " ".join(str(rest_day.author).strip().split()).casefold()
            for rest_day in self.db.list_rest_days(mine_only=False)
            if rest_day.day == report_day
        }

        def remember(name: str, project_name: str) -> None:
            display_name = " ".join(name.strip().split())
            key = display_name.casefold()
            is_departed = getattr(self.db, "is_departed_colleague", lambda value: False)
            if not key or key in resting_member_keys or is_departed(display_name):
                return
            member = members.setdefault(
                key,
                {
                    "name": display_name,
                    "projects": [],
                    "dingtalk_id": self.db.dingtalk_staff_id_for_name(display_name),
                },
            )
            projects = member["projects"]
            if project_name and project_name not in projects:
                projects.append(project_name)

        for project in self.db.list_projects():
            if project.status == "已删除":
                continue
            remember(project.owner, project.name)
            for member in self.db.list_project_members(project.id):
                remember(member.name, project.name)
        return members

    def _send_group_markdown(
        self,
        conversation_id: str,
        title: str,
        text: str,
        mentioned_user_ids: list[str] | None = None,
    ) -> None:
        if mentioned_user_ids:
            session_webhook = (self.db.get_setting(SESSION_WEBHOOK_SETTING) or "").strip()
            expires_text = (self.db.get_setting(SESSION_WEBHOOK_EXPIRES_SETTING) or "").strip()
            try:
                expires_at = int(expires_text or "0")
            except ValueError:
                expires_at = 0
            now = time.time()
            # DingTalk currently returns this value in milliseconds, while
            # retaining compatibility if it ever returns epoch seconds.
            expires_at_seconds = expires_at / 1000 if expires_at > 10_000_000_000 else expires_at
            if session_webhook and not (expires_at_seconds and expires_at_seconds <= now + 30):
                self._request_json(
                    session_webhook,
                    {
                        "msgtype": "markdown",
                        "markdown": {"title": title, "text": text},
                        "at": {
                            "atUserIds": list(dict.fromkeys(mentioned_user_ids)),
                            "isAtAll": False,
                        },
                    },
                )
                return
            LOGGER.warning("日报群的 @ 通道已过期，改用企业机器人发送（本次不触发 @ 提醒）")
        payload = {
            "robotCode": self.robot_code,
            "openConversationId": conversation_id,
            "msgKey": "sampleMarkdown",
            "msgParam": json.dumps({"title": title, "text": text}, ensure_ascii=False),
        }
        self._request_json(
            "https://api.dingtalk.com/v1.0/robot/groupMessages/send",
            payload,
            headers={"x-acs-dingtalk-access-token": self._get_access_token()},
        )

    def _get_access_token(self) -> str:
        with self._token_lock:
            if self._access_token and time.monotonic() < self._access_token_expires_at:
                return self._access_token
            payload = self._request_json(
                "https://api.dingtalk.com/v1.0/oauth2/accessToken",
                {"appKey": self.client_id, "appSecret": self.client_secret},
            )
            token = str(payload.get("accessToken", "")).strip()
            if not token:
                raise RuntimeError("钉钉没有返回 accessToken。")
            try:
                expires_in = int(payload.get("expireIn", payload.get("expiresIn", 7200)) or 7200)
            except (TypeError, ValueError):
                expires_in = 7200
            self._access_token = token
            self._access_token_expires_at = time.monotonic() + max(60, expires_in - 300)
            return token

    def _request_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                result = json.loads(response.read(1024 * 1024).decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read(1024 * 1024).decode("utf-8", errors="replace")
            try:
                payload = json.loads(detail)
                message = str(payload.get("message", payload.get("errmsg", detail)))
            except (TypeError, ValueError):
                message = detail or str(exc)
            raise RuntimeError(f"钉钉接口调用失败：{message}") from exc
        except (URLError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"连接钉钉接口失败：{exc}") from exc
        if not isinstance(result, dict):
            raise RuntimeError("钉钉接口返回了无效数据。")
        return result

    def _markdown_messages(
        self,
        report_day: date,
        reports: list[dict[str, Any]],
        expected_members: dict[str, dict[str, Any]] | None = None,
    ) -> list[str]:
        expected_members = expected_members or {}
        heading = "\n".join([
            f"**{report_day:%Y-%m-%d} 全员项目日报**",
            "",
            f"> 共 {len(reports)} 篇，来自数智中心服务器的所有项目。",
            "",
        ])
        reports_by_member: dict[str, list[dict[str, Any]]] = {}
        for report in reports:
            member_name = str(report.get("member_name", "")).strip() or "未记录人员"
            reports_by_member.setdefault(member_name, []).append(report)

        messages: list[str] = []
        written_heading = f"## ✅ 已写日报（{len(reports_by_member)} 人）\n"
        current = f"{heading}\n{written_heading}"
        for member_name, member_reports in reports_by_member.items():
            member_heading = f"# {member_name}（{len(member_reports)} 篇）\n"
            member_started_in_current = False
            for report in member_reports:
                created_at = report.get("created_at")
                time_text = created_at.strftime("%H:%M") if isinstance(created_at, datetime) else ""
                meta = " · ".join(
                    str(value).strip()
                    for value in (
                        report.get("project_name", "未知项目"),
                        report.get("role", ""),
                        time_text,
                    )
                    if str(value).strip()
                )
                content = str(report.get("content", "")).strip() or "无内容"
                report_section = "\n".join([f"### {meta}", "", content, ""])
                prefix = "" if member_started_in_current else member_heading
                section = f"{prefix}\n{report_section}"
                if len(current) + len(section) + 2 > 15000 and current != heading:
                    messages.append(current)
                    current = f"{heading}\n{written_heading}"
                    member_started_in_current = False
                    section = f"{member_heading}\n{report_section}"
                if len(section) > 14500:
                    section = section[:14480] + "\n\n> 日报内容过长，已截断。"
                current = f"{current}\n{section}"
                member_started_in_current = True
            if current != heading:
                current += "\n"

        written_keys = {" ".join(name.strip().split()).casefold() for name in reports_by_member}
        missing_members = [
            member
            for key, member in expected_members.items()
            if key not in written_keys
        ]
        missing_members.sort(key=lambda member: str(member.get("name", "")).casefold())
        missing_heading = f"## ⚠️ 未写日报（{len(missing_members)} 人）\n"
        if len(current) + len(missing_heading) > 15000:
            messages.append(current)
            current = heading
        current = f"{current}\n{missing_heading}"
        for member in missing_members:
            name = str(member.get("name", "")).strip() or "未记录人员"
            dingtalk_id = str(member.get("dingtalk_id", "")).strip()
            member_lines = [
                f"# @{dingtalk_id}（{name}）" if dingtalk_id else f"# {name}",
                "",
                "> 昨日未提交日报。",
                "",
            ]
            section = "\n".join(member_lines)
            if len(current) + len(section) + 2 > 15000 and current != heading:
                messages.append(current)
                current = f"{heading}\n{missing_heading}"
            current = f"{current}\n{section}"

        if current != heading:
            messages.append(current)
        if not messages:
            messages.append(heading)
        return messages
