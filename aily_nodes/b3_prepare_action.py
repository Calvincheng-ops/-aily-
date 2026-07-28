"""Aily Skill B node: prepare deterministic Base updates for card actions.

This node runs after ``b2_validate_callback.py``. It converts the validated
request snapshot and the validated selected item into flat outputs that can be
bound directly to Aily Base update nodes.

``confirm_upload`` is intentionally not handled here. That action must use the
separate processing -> re-query -> download -> upload sequence described in the
build guide.
"""

import json
import time
from typing import Any, Dict, List


SUPPORTED_ACTIONS = {
    "choose_file",
    "browse",
    "back",
    "choose_current_folder",
    "return_folder",
    "cancel",
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
        "next_step": "",
        "status": "",
        "source_message_id": "",
        "source_type": "",
        "selected_file_id": "",
        "selected_file_key": "",
        "selected_file_name": "",
        "selected_file_type": "",
        "selected_file_size": 0,
        "warning_message": "",
        "current_folder_token": "",
        "current_folder_name": "",
        "current_folder_url": "",
        "current_folder_url_object": {},
        "folder_path_json": "[]",
        "allowed_child_folders_json": "[]",
        "target_folder_token": "",
        "target_folder_name": "",
        "target_folder_url": "",
        "target_folder_url_object": {},
        "target_folder_path": "",
        "completed_at_ms": 0,
    }


def _fail(result: Dict[str, Any], code: str, message: str) -> Dict[str, Any]:
    result["error_code"] = code
    result["error"] = message
    return result


def _clean_path(value: Any) -> List[Dict[str, str]]:
    raw_path = _load_json(value, [])
    if not isinstance(raw_path, list):
        return []
    path: List[Dict[str, str]] = []
    for item in raw_path:
        if not isinstance(item, dict):
            continue
        token = str(item.get("token") or "").strip()
        if not token:
            continue
        path.append(
            {
                "token": token,
                "name": str(item.get("name") or "未命名目录").strip(),
                "url": str(item.get("url") or "").strip(),
            }
        )
    return path


def _path_text(path: List[Dict[str, str]]) -> str:
    return " / ".join(item["name"] for item in path)


def _link_object(url: str, text: str) -> Dict[str, str]:
    """Build a Base URL cell object while keeping card URLs as strings."""
    url = str(url or "").strip()
    if not url:
        return {}
    return {
        "text": str(text or url).strip(),
        "link": url,
    }


def main(
    action: str,
    request_json: Any,
    selected_candidate_json: Any = "{}",
    selected_folder_json: Any = "{}",
    now_ms: Any = 0,
) -> Dict[str, Any]:
    result = _base_result()
    action = str(action or "").strip()
    request = _load_json(request_json, {})
    if action not in SUPPORTED_ACTIONS:
        return _fail(result, "INVALID_ACTION", "B4 不支持当前 action。")
    if not isinstance(request, dict) or not request:
        return _fail(result, "REQUEST_JSON_INVALID", "B4 缺少有效的 request_json。")

    path = _clean_path(request.get("folder_path_json"))
    root_token = str(request.get("root_folder_token_snapshot") or "").strip()
    if not path or not root_token or path[0]["token"] != root_token:
        return _fail(result, "FOLDER_PATH_INVALID", "目录路径缺失或已越过归档根目录。")

    current = path[-1]
    result.update(
        {
            "source_message_id": str(
                request.get("source_message_id") or ""
            ).strip(),
            "source_type": str(request.get("source_type") or "").strip(),
            "selected_file_id": str(
                request.get("selected_file_id") or ""
            ).strip(),
            "selected_file_key": str(
                request.get("selected_file_key") or ""
            ).strip(),
            "selected_file_name": str(
                request.get("selected_file_name") or ""
            ).strip(),
            "selected_file_type": str(
                request.get("selected_file_type") or ""
            ).strip(),
            "selected_file_size": max(
                0, _integer(request.get("selected_file_size"), 0)
            ),
            "warning_message": str(
                request.get("warning_message") or ""
            ).strip(),
            "current_folder_token": current["token"],
            "current_folder_name": current["name"],
            "current_folder_url": current["url"],
            "current_folder_url_object": _link_object(
                current["url"],
                current["name"],
            ),
            "folder_path_json": json.dumps(path, ensure_ascii=False),
            "target_folder_path": _path_text(path),
        }
    )

    if action == "choose_file":
        candidate = _load_json(selected_candidate_json, {})
        if not isinstance(candidate, dict):
            candidate = {}
        required = ("id", "file_key", "file_name", "file_type", "message_id")
        if any(not str(candidate.get(key) or "").strip() for key in required):
            return _fail(
                result,
                "INVALID_CANDIDATE_FILE",
                "已校验候选文件缺少 ID、file_key、文件名、扩展名或消息 ID。",
            )
        result.update(
            {
                "ok": True,
                "next_step": "list_folder",
                "status": "selecting_folder",
                "source_message_id": str(candidate["message_id"]).strip(),
                "source_type": "message_file",
                "selected_file_id": str(candidate["id"]).strip(),
                "selected_file_key": str(candidate["file_key"]).strip(),
                "selected_file_name": str(candidate["file_name"]).strip(),
                "selected_file_type": str(candidate["file_type"])
                .strip()
                .lower()
                .lstrip("."),
                "selected_file_size": max(
                    0, _integer(candidate.get("file_size"), 0)
                ),
                "allowed_child_folders_json": "[]",
            }
        )
        return result

    if action == "browse":
        folder = _load_json(selected_folder_json, {})
        if not isinstance(folder, dict):
            folder = {}
        token = str(folder.get("token") or "").strip()
        parent_token = str(folder.get("parent_token") or "").strip()
        if not token or parent_token != current["token"]:
            return _fail(
                result,
                "INVALID_FOLDER_SELECTION",
                "已校验目录为空或不是当前目录的直属子目录。",
            )
        path.append(
            {
                "token": token,
                "name": str(folder.get("name") or "未命名目录").strip(),
                "url": str(folder.get("url") or "").strip(),
            }
        )
        current = path[-1]
        result.update(
            {
                "ok": True,
                "next_step": "list_folder",
                "status": "selecting_folder",
                "current_folder_token": current["token"],
                "current_folder_name": current["name"],
                "current_folder_url": current["url"],
                "current_folder_url_object": _link_object(
                    current["url"],
                    current["name"],
                ),
                "folder_path_json": json.dumps(path, ensure_ascii=False),
                "allowed_child_folders_json": "[]",
                "target_folder_path": _path_text(path),
            }
        )
        return result

    if action == "back":
        if len(path) <= 1:
            return _fail(result, "ALREADY_AT_ROOT", "当前已经是群归档根目录。")
        path.pop()
        current = path[-1]
        result.update(
            {
                "ok": True,
                "next_step": "list_folder",
                "status": "selecting_folder",
                "current_folder_token": current["token"],
                "current_folder_name": current["name"],
                "current_folder_url": current["url"],
                "current_folder_url_object": _link_object(
                    current["url"],
                    current["name"],
                ),
                "folder_path_json": json.dumps(path, ensure_ascii=False),
                "allowed_child_folders_json": "[]",
                "target_folder_path": _path_text(path),
            }
        )
        return result

    if action == "choose_current_folder":
        result.update(
            {
                "ok": True,
                "next_step": "send_confirm_card",
                "status": "waiting_confirm",
                "target_folder_token": current["token"],
                "target_folder_name": current["name"],
                "target_folder_url": current["url"],
                "target_folder_url_object": _link_object(
                    current["url"],
                    current["name"],
                ),
            }
        )
        return result

    if action == "return_folder":
        result.update(
            {
                "ok": True,
                "next_step": "list_folder",
                "status": "selecting_folder",
            }
        )
        return result

    result.update(
        {
            "ok": True,
            "next_step": "end",
            "status": "cancelled",
            "completed_at_ms": _integer(now_ms, 0) or int(time.time() * 1000),
        }
    )
    return result
