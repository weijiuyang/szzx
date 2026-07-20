from __future__ import annotations

import logging
import os
import re
import threading
from datetime import date, datetime
from typing import Any

from .database import Database


LOGGER = logging.getLogger("szzx.dingtalk-requirement")
FIELD_RE = re.compile(r"^\s*(需求提出人|期望上线时间|需求描述)\s*[：:]\s*(.*?)\s*$")


def _value(obj: object, *names: str, default: Any = "") -> Any:
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return default


def parse_requirement_text(text: str) -> dict[str, object] | None:
    fields: dict[str, str] = {}
    current = ""
    for raw_line in text.replace("【", "").replace("】", "").splitlines():
        match = FIELD_RE.match(raw_line)
        if match:
            current = match.group(1)
            fields[current] = match.group(2).strip()
        elif current == "需求描述" and raw_line.strip():
            fields[current] = f"{fields[current]}\n{raw_line.strip()}".strip()
    if not fields.get("需求提出人") or not fields.get("需求描述"):
        return None
    raw_date = fields.get("期望上线时间", "").strip().replace("年", "/").replace("月", "/").replace("日", "")
    expected: date | None = None
    if raw_date:
        for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d"):
            try:
                expected = datetime.strptime(raw_date, fmt).date()
                break
            except ValueError:
                continue
    return {"requester": fields["需求提出人"], "expected_at": expected, "description": fields["需求描述"]}


def _mentioned_users(message: object) -> list[tuple[str, str]]:
    users = _value(message, "at_users", "atUsers", default=[])
    result: list[tuple[str, str]] = []
    for user in users if isinstance(users, list) else []:
        name = str(_value(user, "dingtalk_nick", "dingtalkNick", "staff_name", "staffName", default="")).strip()
        user_id = str(_value(
            user, "staff_id", "staffId", "dingtalk_id", "dingtalkId", "user_id", "userId", default=""
        )).strip()
        result.append((name, user_id))
    return result


def _recipient(db: Database, message: object, text: str, bot_name: str) -> tuple[str, str] | None:
    mentions = _mentioned_users(message)
    visible_names = [
        match.group(1).split("(", 1)[0].split("（", 1)[0].strip()
        for match in re.finditer(r"@\s*([^@\s]+)", text)
    ]
    visible_names = [name for name in visible_names if name and name.casefold() != bot_name.casefold()]
    if not visible_names:
        return None
    # 正文中的最后一个非机器人 @ 才是承接人。AtUser 数组的顺序与正文顺序
    # 并无保证，不能再将两边的“最后一项”硬拼，否则会把别人的 ID 配给承接人。
    recipient_name = visible_names[-1]
    recipient_id = db.dingtalk_id_for_name(recipient_name)
    if not recipient_id:
        target = recipient_name.casefold()
        recipient_id = next((user_id for name, user_id in mentions if name.casefold() == target and user_id), "")
    return recipient_name, recipient_id


def start_requirement_bot(db: Database) -> threading.Thread | None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    client_id = os.environ.get("DINGTALK_CLIENT_ID", "").strip()
    client_secret = os.environ.get("DINGTALK_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        LOGGER.info("未配置钉钉机器人，跳过需求 Stream")
        return None

    def run() -> None:
        try:
            import dingtalk_stream
        except ImportError:
            LOGGER.exception("缺少 dingtalk-stream 依赖")
            return

        bot_name = os.environ.get("DINGTALK_BOT_NAME", "需求搜集机器人").strip()

        class Handler(dingtalk_stream.ChatbotHandler):
            async def process(self, callback: object):
                try:
                    message = dingtalk_stream.ChatbotMessage.from_dict(_value(callback, "data", default={}))
                    text_obj = _value(message, "text", default=None)
                    text = str(_value(text_obj, "content", default="")).strip()
                    LOGGER.info(
                        "收到钉钉群消息 message_id=%s at_users=%d text=%r",
                        _value(message, "message_id", "msg_id", "msgId"),
                        len(_mentioned_users(message)),
                        text,
                    )
                    parsed = parse_requirement_text(text)
                    recipient = _recipient(db, message, text, bot_name)
                    if parsed is None:
                        self.reply_text("需求格式不完整，请填写需求提出人、期望上线时间和需求描述。", message)
                    elif recipient is None:
                        self.reply_text("没有识别到实际承接人，请先 @承接人，再 @需求搜集机器人。", message)
                    else:
                        recipient_name, recipient_id = recipient
                        # 需求方是发送这条群消息的人；@ 到的人只是承接人。
                        requester = str(_value(message, "sender_nick", "senderNick", default="")).strip()
                        if not requester:
                            requester = str(parsed["requester"])
                        requirement = db.add_requirement(
                            requester=requester, description=str(parsed["description"]),
                            expected_at=parsed["expected_at"], recipient_name=recipient_name,
                            recipient_dingtalk_id=recipient_id,
                            source_conversation_id=str(_value(message, "conversation_id", "conversationId")),
                            source_message_id=str(_value(message, "message_id", "msg_id", "msgId")),
                        )
                        LOGGER.info(
                            "需求已登记 requirement_id=%s recipient=%s recipient_id=%s",
                            requirement.id,
                            recipient_name,
                            recipient_id,
                        )
                        deadline = requirement.expected_at.isoformat() if requirement.expected_at else "未填写"
                        self.reply_text(f"需求已登记并交给 @{recipient_name} 对接，期望上线时间：{deadline}。", message)
                    return dingtalk_stream.AckMessage.STATUS_OK, "OK"
                except Exception:
                    LOGGER.exception("处理钉钉需求失败")
                    return dingtalk_stream.AckMessage.STATUS_SYSTEM_EXCEPTION, "processing failed"

        credential = dingtalk_stream.Credential(client_id, client_secret)
        client = dingtalk_stream.DingTalkStreamClient(credential)
        client.register_callback_handler(dingtalk_stream.chatbot.ChatbotMessage.TOPIC, Handler())
        LOGGER.info("正在启动钉钉需求 Stream")
        client.start_forever()

    thread = threading.Thread(target=run, name="dingtalk-requirement-stream", daemon=True)
    thread.start()
    return thread
