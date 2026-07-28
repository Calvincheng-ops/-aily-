"""Aily Skill B node: validate mapping policy against downloaded file size."""

import json
from typing import Any, Dict, List


SINGLE_UPLOAD_MAX_MB = 20


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


def _extensions(value: Any) -> List[str]:
    value = _load_json(value, value)
    if not isinstance(value, list):
        value = [value]
    extensions: List[str] = []
    for item in value:
        normalized = str(_first(item, "") or "").strip().lower().lstrip(".")
        if normalized and normalized not in extensions:
            extensions.append(normalized)
    return extensions


def _boolean(value: Any) -> bool:
    value = _first(value, value)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "是"}


def _base_result() -> Dict[str, Any]:
    return {
        "ok": False,
        "error_code": "",
        "error": "",
        "actual_size": 0,
        "max_file_size_mb": 0,
        "max_bytes": 0,
    }


def _fail(result: Dict[str, Any], code: str, message: str) -> Dict[str, Any]:
    result["error_code"] = code
    result["error"] = message
    return result


def main(
    mapping_result: Any,
    chat_id: str,
    selected_file_type: str,
    actual_size: Any,
) -> Dict[str, Any]:
    """Validate current group mapping and actual downloaded byte count."""
    result = _base_result()
    chat_id = str(chat_id or "").strip()
    selected_file_type = (
        str(selected_file_type or "").strip().lower().lstrip(".")
    )
    actual_size_int = _integer(actual_size, 0)
    result["actual_size"] = actual_size_int

    records = _find_items(mapping_result)
    if not records:
        return _fail(result, "MAPPING_NOT_FOUND", "上传前找不到群目录映射。")
    if len(records) != 1:
        return _fail(result, "MAPPING_DUPLICATED", "上传前群目录映射不是唯一一条。")

    fields = records[0].get("fields") or records[0]
    mapping_chat_id = str(_first(fields.get("chat_id"), "") or "").strip()
    enabled = _boolean(fields.get("enabled"))
    allowed_types = _extensions(fields.get("allowed_file_types"))
    max_mb = _integer(_first(fields.get("max_file_size_mb"), 0), 0)
    max_bytes = min(max_mb, SINGLE_UPLOAD_MAX_MB) * 1024 * 1024
    result.update(
        {
            "max_file_size_mb": max_mb,
            "max_bytes": max_bytes,
        }
    )

    if not chat_id or mapping_chat_id != chat_id:
        return _fail(result, "MAPPING_CHAT_MISMATCH", "上传前群映射与请求群不一致。")
    if not enabled:
        return _fail(result, "MAPPING_DISABLED", "上传前群归档映射已停用。")
    if max_mb <= 0 or max_mb > SINGLE_UPLOAD_MAX_MB:
        return _fail(result, "FILE_SIZE_CONFIG_INVALID", "群文件大小限制必须在 1..20 MB。")
    if selected_file_type not in allowed_types:
        return _fail(result, "FILE_TYPE_NOT_ALLOWED", "上传前文件类型已不在允许列表中。")
    if actual_size_int <= 0:
        return _fail(result, "FILE_EMPTY", "下载后的文件大小必须大于 0。")
    if actual_size_int > max_bytes:
        return _fail(result, "FILE_TOO_LARGE", "下载后的文件超过当前群归档大小限制。")

    result["ok"] = True
    return result
