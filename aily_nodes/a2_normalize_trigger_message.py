"""Aily Skill A node: normalize the exact trigger message for later nodes.

The Aily Base record query connector expects ``filter.conditions[].value`` to
be a list. Message APIs return ``chat_id`` as a scalar string, so this adapter
returns both the scalar value and a real ``list[str]`` filter value.
"""

import json
from typing import Any, Dict, List


def _load_json(value: Any) -> Any:
    """Decode JSON strings while leaving decoded values unchanged."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _find_messages(value: Any) -> List[Dict[str, Any]]:
    """Find message objects inside Aily's nested connector wrappers."""
    value = _load_json(value)
    if isinstance(value, list):
        direct = [
            item
            for item in value
            if isinstance(item, dict) and item.get("message_id")
        ]
        if direct:
            return direct
        messages: List[Dict[str, Any]] = []
        for item in value:
            messages.extend(_find_messages(item))
        return messages
    if not isinstance(value, dict):
        return []
    if value.get("message_id"):
        return [value]
    for key in ("items", "data", "result", "output", "return", "response"):
        if key in value:
            messages = _find_messages(value.get(key))
            if messages:
                return messages
    return []


def _base_result() -> Dict[str, Any]:
    """Return a stable Aily output contract for success and failure paths."""
    return {
        "ok": False,
        "error_code": "",
        "error": "",
        "chat_id": "",
        "chat_id_filter_values": [],
        "message_id": "",
        "parent_id": "",
        "root_id": "",
        "sender_id": "",
        "msg_type": "",
        "trigger_message_json": "{}",
    }


def main(
    message_result: Any,
    expected_message_id: str = "",
) -> Dict[str, Any]:
    """Normalize one exact trigger message.

    Args:
        message_result: Complete output of Aily's message query node.
        expected_message_id: Trigger message ID from the Skill A start node.

    Returns:
        Scalar message fields plus ``chat_id_filter_values`` as a real list.
    """
    result = _base_result()
    expected_message_id = str(expected_message_id or "").strip()
    messages = _find_messages(message_result)

    if expected_message_id:
        matches = [
            item
            for item in messages
            if str(item.get("message_id") or "").strip() == expected_message_id
        ]
    else:
        matches = messages

    if not matches:
        result.update(
            {
                "error_code": "TRIGGER_MESSAGE_NOT_FOUND",
                "error": "消息查询结果中没有找到本次触发消息。",
            }
        )
        return result
    if len(matches) != 1:
        result.update(
            {
                "error_code": "TRIGGER_MESSAGE_NOT_UNIQUE",
                "error": "消息查询结果中触发消息不是唯一一条。",
            }
        )
        return result

    message = matches[0]
    message_id = str(message.get("message_id") or "").strip()
    chat_id = str(message.get("chat_id") or "").strip()
    sender = message.get("sender")
    sender_id = (
        str(sender.get("id") or "").strip() if isinstance(sender, dict) else ""
    )
    if not message_id or not chat_id:
        result.update(
            {
                "error_code": "TRIGGER_MESSAGE_INVALID",
                "error": "触发消息缺少 message_id 或 chat_id。",
            }
        )
        return result

    result.update(
        {
            "ok": True,
            "chat_id": chat_id,
            "chat_id_filter_values": [chat_id],
            "message_id": message_id,
            "parent_id": str(message.get("parent_id") or "").strip(),
            "root_id": str(message.get("root_id") or "").strip(),
            "sender_id": sender_id,
            "msg_type": str(message.get("msg_type") or "").strip(),
            "trigger_message_json": json.dumps(
                message,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
    )
    return result
