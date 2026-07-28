"""Aily Skill B node: validate callback globals and restore request state.

Skill B is stateless between clicks. This node accepts only Skill B start-node
globals plus the complete Base query output for request_id.
"""

import json
import time
from typing import Any, Dict, List


ALLOWED_STATES = {
    "choose_file": {"selecting_file"},
    "browse": {"selecting_folder"},
    "back": {"selecting_folder"},
    "choose_current_folder": {"selecting_folder"},
    "return_folder": {"waiting_confirm"},
    "confirm_upload": {"waiting_confirm"},
    "cancel": {"selecting_file", "selecting_folder", "waiting_confirm"},
}


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
        if value.get(key) is not None:
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
        "request_record_id": "",
        "request_id": "",
        "action": "",
        "status": "",
        "chat_id": "",
        "requester_id": "",
        "operator_id": "",
        "selected_file_id": "",
        "selected_folder_token": "",
        "selected_candidate_json": "{}",
        "selected_folder_json": "{}",
        "request_json": "{}",
    }


def _fail(result: Dict[str, Any], code: str, message: str) -> Dict[str, Any]:
    result["error_code"] = code
    result["error"] = message
    return result


def main(
    request_result: Any,
    request_id: str,
    action: str,
    operator_id: str,
    selected_file_id: str = "",
    selected_folder_token: str = "",
    now_ms: Any = 0,
) -> Dict[str, Any]:
    result = _base_result()
    request_id = str(request_id or "").strip()
    action = str(action or "").strip()
    operator_id = str(operator_id or "").strip()
    selected_file_id = str(selected_file_id or "").strip()
    selected_folder_token = str(selected_folder_token or "").strip()
    result.update(
        {
            "request_id": request_id,
            "action": action,
            "operator_id": operator_id,
            "selected_file_id": selected_file_id,
            "selected_folder_token": selected_folder_token,
        }
    )

    if not request_id:
        return _fail(result, "REQUEST_ID_MISSING", "技能 B 开始节点缺少 request_id。")
    if action not in ALLOWED_STATES:
        return _fail(result, "INVALID_ACTION", "技能 B 收到了不支持的 action。")
    if not operator_id:
        return _fail(result, "OPERATOR_ID_MISSING", "未能取得本次点击人的可信 open_id。")

    records = _find_items(request_result)
    if not records:
        return _fail(result, "REQUEST_NOT_FOUND", "没有找到对应的归档请求。")
    if len(records) > 1:
        return _fail(result, "REQUEST_DUPLICATED", "request_id 命中了多条归档请求。")

    record = records[0]
    fields = record.get("fields") or record
    normalized = {key: _first(value, "") for key, value in fields.items()}
    stored_request_id = str(normalized.get("request_id") or "").strip()
    requester_id = str(normalized.get("requester_id") or "").strip()
    status = str(normalized.get("status") or "").strip()
    chat_id = str(normalized.get("chat_id") or "").strip()
    root_token = str(normalized.get("root_folder_token_snapshot") or "").strip()
    result.update(
        {
            "request_record_id": str(record.get("record_id") or ""),
            "status": status,
            "chat_id": chat_id,
            "requester_id": requester_id,
        }
    )

    if stored_request_id != request_id:
        return _fail(result, "REQUEST_ID_MISMATCH", "请求记录的 request_id 与回调不一致。")
    if requester_id != operator_id:
        return _fail(result, "OPERATOR_NOT_ALLOWED", "只有原归档发起人可以继续操作。")

    current_ms = _integer(now_ms, 0) or int(time.time() * 1000)
    expires_at = _integer(normalized.get("expires_at"), 0)
    if expires_at and current_ms > expires_at:
        return _fail(result, "REQUEST_EXPIRED", "本次归档请求已过期，请重新发起。")
    if status not in ALLOWED_STATES[action]:
        return _fail(
            result,
            "INVALID_STATUS",
            f"当前状态 {status or '空'} 不允许执行 {action}。",
        )

    path = _load_json(normalized.get("folder_path_json"), [])
    if not isinstance(path, list) or not path:
        return _fail(result, "FOLDER_PATH_INVALID", "归档请求缺少有效的目录路径。")
    first_token = str((path[0] if isinstance(path[0], dict) else {}).get("token") or "")
    if not root_token or first_token != root_token:
        return _fail(result, "FOLDER_OUT_OF_BOUNDARY", "当前目录路径已越过群归档根目录。")

    selected_candidate: Dict[str, Any] = {}
    if action == "choose_file":
        if not selected_file_id:
            return _fail(result, "INVALID_FILE_SELECTION", "未收到 selected_file_id。")
        candidates = _load_json(normalized.get("candidate_files_json"), [])
        matches = [
            item
            for item in candidates
            if isinstance(item, dict) and str(item.get("id") or "") == selected_file_id
        ]
        if len(matches) != 1:
            return _fail(
                result,
                "INVALID_FILE_SELECTION",
                "selected_file_id 不在本次候选快照中。",
            )
        selected_candidate = matches[0]

    selected_folder: Dict[str, Any] = {}
    if action == "browse":
        if not selected_folder_token:
            return _fail(result, "INVALID_FOLDER_SELECTION", "未收到 selected_folder_token。")
        folders = _load_json(normalized.get("allowed_child_folders_json"), [])
        matches = [
            item
            for item in folders
            if isinstance(item, dict)
            and str(item.get("token") or "") == selected_folder_token
        ]
        if len(matches) != 1:
            return _fail(
                result,
                "INVALID_FOLDER_SELECTION",
                "selected_folder_token 不在当前子目录白名单中。",
            )
        selected_folder = matches[0]

    result.update(
        {
            "ok": True,
            "error_code": "",
            "error": "",
            "selected_candidate_json": json.dumps(
                selected_candidate, ensure_ascii=False
            ),
            "selected_folder_json": json.dumps(selected_folder, ensure_ascii=False),
            "request_json": json.dumps(normalized, ensure_ascii=False),
        }
    )
    return result
