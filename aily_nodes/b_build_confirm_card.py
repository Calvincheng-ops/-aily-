"""Aily Skill B node: build Card 3 variables for final upload confirmation."""

import json
from typing import Any, Dict


def _make_skill_object(
    callback_skill_id: str,
    request_id: str,
    action: str,
    update_card: bool = False,
) -> Dict[str, Any]:
    return {
        "x_aily_forbid_forward_callback": True,
        "aily_action": "trigger_skill",
        "skill_id": callback_skill_id,
        "skill_input": json.dumps(
            {"request_id": request_id, "action": action},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "update_card": update_card,
    }


def _result(error: str = "", error_code: str = "") -> Dict[str, Any]:
    return {
        "ok": not bool(error),
        "error_code": error_code,
        "error": error,
        "request_id_text": "",
        "selected_file_name": "",
        "selected_file_type": "",
        "target_folder_path": "",
        "target_folder_url": "",
        "warning": "",
        "initiator": {},
        "skill_object_confirm": {},
        "skill_object_return": {},
        "skill_object_cancel": {},
    }


def main(
    request_id: str,
    callback_skill_id: str,
    requester_id: str,
    selected_file_name: str,
    selected_file_type: str,
    target_folder_path: str,
    target_folder_url: str,
    warning: str = "",
) -> Dict[str, Any]:
    request_id = str(request_id or "").strip()
    callback_skill_id = str(callback_skill_id or "").strip()
    requester_id = str(requester_id or "").strip()
    selected_file_name = str(selected_file_name or "").strip()
    target_folder_path = str(target_folder_path or "").strip()

    if not request_id:
        return _result("缺少 request_id", "REQUEST_ID_MISSING")
    if not callback_skill_id:
        return _result(
            "缺少 callback_skill_id；请填写已发布技能 B 的 skill_xxx",
            "CALLBACK_SKILL_ID_MISSING",
        )
    if not callback_skill_id.startswith("skill_"):
        return _result(
            "callback_skill_id 必须是已发布技能 B 的 skill_xxx",
            "CALLBACK_SKILL_ID_INVALID",
        )
    if not requester_id:
        return _result("缺少 requester_id", "REQUESTER_ID_MISSING")
    if not selected_file_name:
        return _result(
            "缺少 selected_file_name；必须先完成文件确认",
            "SELECTED_FILE_MISSING",
        )
    if not target_folder_path:
        return _result(
            "缺少 target_folder_path；必须先选择目标目录",
            "TARGET_FOLDER_MISSING",
        )

    return {
        "ok": True,
        "error_code": "",
        "error": "",
        "request_id_text": request_id,
        "selected_file_name": selected_file_name,
        "selected_file_type": str(selected_file_type or "").strip(),
        "target_folder_path": target_folder_path,
        "target_folder_url": str(target_folder_url or "").strip(),
        "warning": str(warning or "").strip(),
        "initiator": {"id": requester_id} if requester_id else {},
        "skill_object_confirm": _make_skill_object(
            callback_skill_id, request_id, "confirm_upload"
        ),
        "skill_object_return": _make_skill_object(
            callback_skill_id, request_id, "return_folder"
        ),
        "skill_object_cancel": _make_skill_object(
            callback_skill_id, request_id, "cancel", update_card=True
        ),
    }
