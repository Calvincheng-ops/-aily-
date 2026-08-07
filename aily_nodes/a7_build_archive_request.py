"""Build one archive request from an explicitly replied file for Skill A.

Inputs are the complete outputs of:
- the Base mapping query;
- the "get trigger message" node;
- the "get replied message" node;
- normalized trusted values from Skill A's start node.

This node never reads group history and never asks an LLM to choose a file.
"""

import json
import os
import re
import time
import uuid
from typing import Any, Dict, List


REQUEST_TTL_MS = 30 * 60 * 1000
SINGLE_UPLOAD_MAX_MB = 20
MAX_UPLOAD_MB = 100


def _load_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default
    return default


def _find_items(value: Any) -> List[Dict[str, Any]]:
    """Unwrap common Aily/OpenAPI layers until an items list is found."""
    value = _load_json(value, {})
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []

    items = value.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]

    for key in ("data", "result", "output", "return"):
        if value.get(key) is not None:
            nested = _find_items(value.get(key))
            if nested:
                return nested
    return []


def _find_messages(value: Any) -> List[Dict[str, Any]]:
    """Return message objects from a direct object or wrapped items response."""
    value = _load_json(value, {})
    if isinstance(value, dict) and value.get("message_id"):
        return [value]

    items = _find_items(value)
    messages = [item for item in items if item.get("message_id")]
    if messages:
        return messages

    if isinstance(value, dict):
        for key in ("data", "result", "output", "return"):
            nested_value = value.get(key)
            nested_value = _load_json(nested_value, nested_value)
            if isinstance(nested_value, dict) and nested_value.get("message_id"):
                return [nested_value]
    return []


def _find_exact_message(value: Any, message_id: str) -> Dict[str, Any]:
    messages = _find_messages(value)
    for message in messages:
        if str(message.get("message_id") or "") == message_id:
            return message
    return messages[0] if len(messages) == 1 else {}


def _cell(value: Any, default: Any = "") -> Any:
    """Convert common Base cell values to plain Python values."""
    if value is None:
        return default
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        converted = [_cell(item, "") for item in value]
        return [item for item in converted if item not in ("", None)]
    if isinstance(value, dict):
        for key in ("link", "url", "text", "name", "value"):
            if value.get(key) not in (None, ""):
                return value.get(key)
    return default


def _first(value: Any, default: Any = "") -> Any:
    value = _cell(value, default)
    if isinstance(value, list):
        return value[0] if value else default
    return value


def _extension_list(value: Any) -> List[str]:
    value = _cell(value, [])
    if value in (None, ""):
        return []
    values = value if isinstance(value, list) else [value]
    return sorted(
        {
            str(item).strip().lower().lstrip(".")
            for item in values
            if str(item or "").strip()
        }
    )


def _content_object(message: Dict[str, Any]) -> Dict[str, Any]:
    body = message.get("body") or {}
    content = _load_json(body.get("content"), {})
    return content if isinstance(content, dict) else {}


def _sender_id(message: Dict[str, Any]) -> str:
    return str((message.get("sender") or {}).get("id") or "").strip()


def _clean_folder_token(value: Any) -> str:
    raw = str(value or "").strip()
    if "/drive/folder/" in raw:
        raw = raw.split("/drive/folder/", 1)[1]
    return raw.split("?", 1)[0].split("#", 1)[0].strip().strip("/")


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default


def _boolean(value: Any, default: bool = False) -> bool:
    value = _first(value, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1", "yes", "y", "是", "已勾选"):
            return True
        if normalized in ("false", "0", "no", "n", "否", "未勾选", ""):
            return False
    return default


def _base_result() -> Dict[str, Any]:
    return {
        "ok": False,
        "error_code": "",
        "error": "",
        "warning": "",
        "request_id": "",
        "mapping_record_id": "",
        "chat_id": "",
        "chat_name": "",
        "requester_id": "",
        "initiator": {},
        "trigger_message_id": "",
        "trigger_text": "",
        "file_message_id": "",
        "file_key": "",
        "file_name": "",
        "file_type": "",
        "file_size": 0,
        "file_sender_id": "",
        "candidate_file_id": "",
        "candidate_count": 0,
        "candidate_files_json": "[]",
        "selected_file_id": "",
        "selected_file_key": "",
        "selected_file_name": "",
        "selected_file_message_id": "",
        "selected_file_type": "",
        "root_folder_token": "",
        "root_folder_name": "",
        "root_folder_url": "",
        "root_folder_url_object": {},
        "current_folder_url_object": {},
        "max_file_size_mb": 0,
        "single_upload_max_mb": SINGLE_UPLOAD_MAX_MB,
        "only_file_sender_can_archive": False,
        "allowed_file_types_json": "[]",
        "initial_status": "",
        "folder_path_json": "[]",
        "expires_at_ms": 0,
    }


def _fail(result: Dict[str, Any], code: str, message: str) -> Dict[str, Any]:
    result["error_code"] = code
    result["error"] = message
    return result


def main(
    mapping_result: Any,
    trigger_message_result: Any,
    replied_message_result: Any,
    chat_id: str,
    requester_id: str,
    trigger_message_id: str,
    trigger_text: str = "",
    now_ms: Any = 0,
) -> Dict[str, Any]:
    result = _base_result()
    chat_id = str(chat_id or "").strip()
    requester_id = str(requester_id or "").strip()
    trigger_message_id = str(trigger_message_id or "").strip()
    trigger_text = str(trigger_text or "").strip()
    result.update(
        {
            "chat_id": chat_id,
            "requester_id": requester_id,
            "initiator": {"id": requester_id} if requester_id else {},
            "trigger_message_id": trigger_message_id,
            "trigger_text": trigger_text,
        }
    )

    if not chat_id or not trigger_message_id or not requester_id:
        return _fail(
            result,
            "INVALID_TRIGGER",
            "当前群、触发消息或发起人参数不完整，请重新 @机器人发起归档。",
        )

    trigger = _find_exact_message(trigger_message_result, trigger_message_id)
    if not trigger:
        return _fail(result, "TRIGGER_MESSAGE_NOT_FOUND", "未能读取当前归档指令消息。")
    if str(trigger.get("message_id") or "") != trigger_message_id:
        return _fail(result, "TRIGGER_MESSAGE_MISMATCH", "返回的消息不是当前归档指令消息。")
    if str(trigger.get("chat_id") or "") != chat_id:
        return _fail(result, "TRIGGER_CHAT_MISMATCH", "触发消息不属于当前群聊。")
    if _sender_id(trigger) != requester_id:
        return _fail(result, "TRIGGER_SENDER_MISMATCH", "触发消息发起人与当前用户不一致。")

    parent_id = str(trigger.get("parent_id") or "").strip()
    if not parent_id:
        return _fail(
            result,
            "NOT_REPLY_TO_MESSAGE",
            "请回复需要归档的文件消息，并 @机器人发送“归档”。",
        )

    replied = _find_exact_message(replied_message_result, parent_id)
    if not replied:
        return _fail(result, "REPLIED_MESSAGE_NOT_FOUND", "未能读取被回复的消息。")
    if str(replied.get("message_id") or "") != parent_id:
        return _fail(result, "REPLIED_MESSAGE_MISMATCH", "返回的消息不是本次直接回复的消息。")
    if str(replied.get("chat_id") or "") != chat_id:
        return _fail(result, "REPLIED_MESSAGE_CHAT_MISMATCH", "被回复消息不属于当前群聊。")
    if replied.get("deleted") is True:
        return _fail(result, "FILE_MESSAGE_DELETED", "被回复的文件消息已删除或撤回。")
    if str(replied.get("msg_type") or "").lower() != "file":
        return _fail(
            result,
            "REPLIED_MESSAGE_NOT_FILE",
            "被回复的内容不是文件，请直接回复需要归档的文件消息。",
        )

    file_sender_id = _sender_id(replied)

    content = _content_object(replied)
    file_key = str(content.get("file_key") or content.get("fileKey") or "").strip()
    file_name = str(content.get("file_name") or content.get("fileName") or "").strip()
    if not file_key or not file_name:
        return _fail(result, "FILE_INFO_MISSING", "文件消息缺少 file_key 或文件名。")

    file_type = os.path.splitext(file_name)[1].lower().lstrip(".")
    if not file_type:
        return _fail(result, "FILE_TYPE_MISSING", "文件名没有扩展名，无法校验归档类型。")

    file_size = max(
        0,
        _integer(
            content.get("file_size")
            or content.get("fileSize")
            or replied.get("file_size"),
            0,
        ),
    )
    file_message_id = str(replied.get("message_id") or "")
    candidate_file_id = (
        "file_" + re.sub(r"[^a-zA-Z0-9]", "", file_message_id)[-12:]
    )
    result.update(
        {
            "file_message_id": file_message_id,
            "file_key": file_key,
            "file_name": file_name,
            "file_type": file_type,
            "file_size": file_size,
            "file_sender_id": file_sender_id,
            "candidate_file_id": candidate_file_id,
        }
    )

    mappings = _find_items(mapping_result)
    if not mappings:
        return _fail(result, "MAPPING_NOT_FOUND", "当前群未配置归档目录。")
    if len(mappings) > 1:
        return _fail(result, "MAPPING_DUPLICATED", "当前群存在重复映射，请管理员处理。")

    mapping = mappings[0]
    fields = mapping.get("fields") or mapping
    mapping_chat_id = str(_first(fields.get("chat_id"), "") or "").strip()
    raw_root_token = str(_first(fields.get("root_folder_token"), "") or "").strip()
    root_token = _clean_folder_token(raw_root_token)
    root_name = str(_first(fields.get("root_folder_name"), "") or "").strip()
    root_url = str(_first(fields.get("root_folder_url"), "") or "").strip()
    allowed_types = _extension_list(fields.get("allowed_file_types"))
    max_size_mb = _integer(_first(fields.get("max_file_size_mb"), 0), 0)
    enabled = _boolean(fields.get("enabled"), False)
    only_file_sender_can_archive = _boolean(
        fields.get("only_file_sender_can_archive"),
        False,
    )

    result.update(
        {
            "mapping_record_id": str(mapping.get("record_id") or ""),
            "chat_name": str(_first(fields.get("chat_name"), "") or "").strip(),
            "root_folder_token": root_token,
            "root_folder_name": root_name,
            "root_folder_url": root_url,
            "max_file_size_mb": max_size_mb,
            "only_file_sender_can_archive": only_file_sender_can_archive,
            "allowed_file_types_json": json.dumps(allowed_types, ensure_ascii=False),
        }
    )

    if mapping_chat_id != chat_id:
        return _fail(result, "MAPPING_CHAT_MISMATCH", "映射记录与当前群聊不一致。")
    if not enabled:
        return _fail(result, "MAPPING_DISABLED", "当前群归档功能未启用。")
    if only_file_sender_can_archive and file_sender_id != requester_id:
        return _fail(
            result,
            "FILE_SENDER_NOT_ALLOWED",
            "当前群只允许归档由发起人本人发送的文件。",
        )
    if not root_token:
        return _fail(result, "ROOT_FOLDER_MISSING", "群目录映射缺少根目录 token。")
    if not root_name:
        return _fail(result, "ROOT_FOLDER_NAME_MISSING", "群目录映射缺少根目录名称。")
    if not root_url:
        return _fail(result, "ROOT_FOLDER_URL_MISSING", "群目录映射缺少根目录链接。")
    if not allowed_types:
        return _fail(
            result,
            "FILE_TYPE_CONFIG_EMPTY",
            "群目录映射未配置允许的文件类型。",
        )
    if file_type not in allowed_types:
        return _fail(
            result,
            "FILE_TYPE_NOT_ALLOWED",
            f"当前文件类型 .{file_type} 不在本群允许归档的类型中。",
        )
    if max_size_mb <= 0:
        return _fail(
            result,
            "FILE_SIZE_CONFIG_INVALID",
            "群目录映射的最大文件大小配置无效。",
        )
    if max_size_mb > MAX_UPLOAD_MB:
        return _fail(
            result,
            "FILE_SIZE_CONFIG_UNSUPPORTED",
            f"max_file_size_mb 不能超过 {MAX_UPLOAD_MB}（飞书消息资源下载接口限制 100 MB）。",
        )
    if file_size and file_size > max_size_mb * 1024 * 1024:
        return _fail(
            result,
            "FILE_TOO_LARGE",
            f"当前文件超过本群 {max_size_mb} MB 的归档限制。",
        )

    warning = ""
    if raw_root_token != root_token:
        warning = "映射表 root_folder_token 含链接或参数，本次已自动清洗；请修正表格配置。"

    candidate = {
        "id": candidate_file_id,
        "file_key": file_key,
        "file_name": file_name,
        "file_type": file_type,
        "message_id": file_message_id,
        "sender_id": file_sender_id,
        "file_size": file_size,
        "source_type": "replied_message_file",
    }
    folder_path = [{"token": root_token, "name": root_name, "url": root_url}]
    current_ms = _integer(now_ms, 0) or int(time.time() * 1000)

    result.update(
        {
            "ok": True,
            "error_code": "",
            "error": "",
            "warning": warning,
            "request_id": "archive_" + uuid.uuid4().hex,
            "candidate_count": 1,
            "candidate_files_json": json.dumps([candidate], ensure_ascii=False),
            "initial_status": "selecting_file",
            "folder_path_json": json.dumps(folder_path, ensure_ascii=False),
            "expires_at_ms": current_ms + REQUEST_TTL_MS,
            "root_folder_url_object": {
                "text": root_name,
                "link": root_url,
            },
            "current_folder_url_object": {
                "text": root_name,
                "link": root_url,
            },
        }
    )
    return result
