"""Aily Skill B node: normalize upload outcome into Card 4 variables."""

import json
from typing import Any, Dict


def _size_text(value: Any) -> str:
    try:
        size = max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return "未知"
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.1f} KB"
    if size < 1024**3:
        return f"{size / 1024**2:.1f} MB"
    return f"{size / 1024**3:.1f} GB"


def _path_text(value: Any) -> str:
    if isinstance(value, list):
        path = value
    elif isinstance(value, str):
        text = value.strip()
        try:
            path = json.loads(text)
        except (TypeError, ValueError):
            return text
    else:
        return str(value or "").strip()
    if not isinstance(path, list):
        return ""
    return " / ".join(
        str(item.get("name") or "未命名目录")
        for item in path
        if isinstance(item, dict)
    )


def _result(error: str = "", error_code: str = "") -> Dict[str, Any]:
    return {
        "ok": not bool(error),
        "error_code": error_code,
        "error": error,
        "is_success": False,
        "result_title": "",
        "result_summary": "",
        "request_id_text": "",
        "selected_file_name": "",
        "selected_file_type": "",
        "target_folder_name": "",
        "target_folder_path": "",
        "target_folder_url": "",
        "result_file_url": "",
        "result_size_text": "",
        "completed_at_text": "",
        "error_message": "",
        "initiator": {},
    }


def main(
    status: str,
    request_id: str,
    requester_id: str,
    selected_file_name: str,
    selected_file_type: str,
    target_folder_name: str,
    target_folder_path: str,
    target_folder_url: str,
    result_file_url: str = "",
    result_size: Any = 0,
    completed_at: Any = "",
    error_message: str = "",
) -> Dict[str, Any]:
    status = str(status or "").strip().lower()
    request_id = str(request_id or "").strip()
    selected_file_name = str(selected_file_name or "").strip()
    target_folder_path = _path_text(target_folder_path)

    if status not in ("success", "failed"):
        return _result("status 必须是 success 或 failed", "INVALID_RESULT_STATUS")
    if not request_id:
        return _result("缺少 request_id", "REQUEST_ID_MISSING")
    if not selected_file_name:
        return _result("缺少 selected_file_name", "SELECTED_FILE_MISSING")
    if not target_folder_path:
        return _result("缺少 target_folder_path", "TARGET_FOLDER_MISSING")

    is_success = status == "success"
    readable_error = str(error_message or "").strip()
    if not is_success and not readable_error:
        readable_error = "上传未完成，请重新发起归档或联系管理员排查。"

    return {
        "ok": True,
        "error_code": "",
        "error": "",
        "is_success": is_success,
        "result_title": "归档成功" if is_success else "归档失败",
        "result_summary": (
            "文件已上传到选定的云盘目录。"
            if is_success
            else "文件未能完成归档，请根据失败原因处理。"
        ),
        "request_id_text": request_id,
        "selected_file_name": selected_file_name,
        "selected_file_type": str(selected_file_type or "").strip(),
        "target_folder_name": str(target_folder_name or "").strip(),
        "target_folder_path": target_folder_path,
        "target_folder_url": str(target_folder_url or "").strip(),
        "result_file_url": str(result_file_url or "").strip() if is_success else "",
        "result_size_text": _size_text(result_size) if is_success else "-",
        "completed_at_text": str(completed_at or "").strip(),
        "error_message": "" if is_success else readable_error,
        "initiator": (
            {"id": str(requester_id).strip()} if str(requester_id or "").strip() else {}
        ),
    }
