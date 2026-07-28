"""Aily Skill B node: validate the latest request before downloading a file."""

import json
from typing import Any, Dict, List


TERMINAL_STATES = {"success", "failed", "cancelled", "expired"}


def _load_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default
    return default


def _find_items(value: Any) -> List[Dict[str, Any]]:
    value = _load_json(value, {})
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    if isinstance(value.get("items"), list):
        return [item for item in value["items"] if isinstance(item, dict)]
    for key in ("data", "result", "output", "return"):
        nested = _find_items(value.get(key))
        if nested:
            return nested
    return []


def _cell(value: Any, default: Any = "") -> Any:
    if value is None:
        return default
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        values = [_cell(item, "") for item in value]
        return [item for item in values if item not in ("", None)]
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


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default


def _base_result() -> Dict[str, Any]:
    return {
        "ok": False,
        "error_code": "",
        "error": "",
        "should_upload": False,
        "already_finished": False,
        "request_record_id": "",
        "request_id": "",
        "status": "",
        "chat_id": "",
        "chat_id_filter_values": [],
        "source_message_id": "",
        "selected_file_key": "",
        "selected_file_name": "",
        "selected_file_type": "",
        "selected_file_size": 0,
        "target_folder_token": "",
        "target_folder_name": "",
        "target_folder_url": "",
        "target_folder_path": "",
        "result_file_token": "",
        "result_file_url": "",
    }


def _fail(result: Dict[str, Any], code: str, message: str) -> Dict[str, Any]:
    result["error_code"] = code
    result["error"] = message
    return result


def main(request_result: Any, request_id: str) -> Dict[str, Any]:
    """Validate the re-queried request after it was moved to processing."""
    result = _base_result()
    request_id = str(request_id or "").strip()
    result["request_id"] = request_id
    if not request_id:
        return _fail(result, "REQUEST_ID_MISSING", "上传前缺少 request_id。")

    records = _find_items(request_result)
    if not records:
        return _fail(result, "REQUEST_NOT_FOUND", "上传前重新查询不到归档请求。")
    if len(records) != 1:
        return _fail(result, "REQUEST_DUPLICATED", "上传前 request_id 命中多条请求。")

    record = records[0]
    fields = record.get("fields") or record
    normalized = {key: _first(value, "") for key, value in fields.items()}
    stored_request_id = str(normalized.get("request_id") or "").strip()
    status = str(normalized.get("status") or "").strip()
    chat_id = str(normalized.get("chat_id") or "").strip()
    result.update(
        {
            "request_record_id": str(record.get("record_id") or ""),
            "status": status,
            "chat_id": chat_id,
            "chat_id_filter_values": [chat_id] if chat_id else [],
            "source_message_id": str(
                normalized.get("source_message_id") or ""
            ).strip(),
            "selected_file_key": str(
                normalized.get("selected_file_key") or ""
            ).strip(),
            "selected_file_name": str(
                normalized.get("selected_file_name") or ""
            ).strip(),
            "selected_file_type": str(
                normalized.get("selected_file_type") or ""
            )
            .strip()
            .lower()
            .lstrip("."),
            "selected_file_size": max(
                0,
                _integer(normalized.get("selected_file_size"), 0),
            ),
            "target_folder_token": str(
                normalized.get("target_folder_token") or ""
            ).strip(),
            "target_folder_name": str(
                normalized.get("target_folder_name") or ""
            ).strip(),
            "target_folder_url": str(
                normalized.get("target_folder_url") or ""
            ).strip(),
            "result_file_token": str(
                normalized.get("result_file_token") or ""
            ).strip(),
            "result_file_url": str(
                normalized.get("result_file_url") or ""
            ).strip(),
        }
    )

    if stored_request_id != request_id:
        return _fail(result, "REQUEST_ID_MISMATCH", "上传前请求 ID 不一致。")
    if status in TERMINAL_STATES or result["result_file_token"]:
        result.update(
            {
                "ok": True,
                "should_upload": False,
                "already_finished": True,
            }
        )
        return result
    if status != "processing":
        return _fail(
            result,
            "INVALID_STATUS",
            f"上传前请求状态必须是 processing，当前为 {status or '空'}。",
        )

    required = {
        "chat_id": chat_id,
        "source_message_id": result["source_message_id"],
        "selected_file_key": result["selected_file_key"],
        "selected_file_name": result["selected_file_name"],
        "selected_file_type": result["selected_file_type"],
        "target_folder_token": result["target_folder_token"],
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        return _fail(
            result,
            "PROCESSING_FIELDS_MISSING",
            "上传前请求缺少字段：" + ", ".join(missing),
        )

    path = _load_json(normalized.get("folder_path_json"), [])
    root_token = str(
        normalized.get("root_folder_token_snapshot") or ""
    ).strip()
    if not isinstance(path, list) or not path or not root_token:
        return _fail(result, "FOLDER_PATH_INVALID", "上传前目录路径无效。")
    first = path[0] if isinstance(path[0], dict) else {}
    last = path[-1] if isinstance(path[-1], dict) else {}
    if (
        str(first.get("token") or "") != root_token
        or str(last.get("token") or "") != result["target_folder_token"]
    ):
        return _fail(
            result,
            "FOLDER_OUT_OF_BOUNDARY",
            "上传目标目录不在本次群归档路径内。",
        )

    result.update(
        {
            "ok": True,
            "should_upload": True,
            "target_folder_path": " / ".join(
                str(item.get("name") or "未命名目录")
                for item in path
                if isinstance(item, dict)
            ),
        }
    )
    return result
