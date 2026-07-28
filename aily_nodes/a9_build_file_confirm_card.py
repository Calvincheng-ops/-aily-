"""Build the single-file confirmation card variables for Skill A."""

import json
from typing import Any, Dict, List


def _load_candidates(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _make_skill_object(
    callback_skill_id: str,
    request_id: str,
    action: str,
    selected_file_id: str = "",
    update_card: bool = True,
    success_message: str = "",
) -> Dict[str, Any]:
    skill_input = {"request_id": request_id, "action": action}
    if selected_file_id:
        skill_input["selected_file_id"] = selected_file_id
    result = {
        "x_aily_forbid_forward_callback": True,
        "aily_action": "trigger_skill",
        "skill_id": callback_skill_id,
        "skill_input": json.dumps(
            skill_input,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "update_card": update_card,
    }
    if update_card and success_message:
        result["success_message"] = success_message
    return result


def _result(error: str = "", error_code: str = "") -> Dict[str, Any]:
    return {
        "ok": not bool(error),
        "error_code": error_code,
        "error": error,
        "request_id_text": "",
        "file_name": "",
        "file_type": "",
        "root_folder_name": "",
        "initiator": {},
        "skill_object_choose_file": {},
        "skill_object_cancel": {},
    }


def main(
    candidate_files_json: Any,
    request_id: str,
    callback_skill_id: str,
    requester_id: str = "",
    root_folder_name: str = "",
) -> Dict[str, Any]:
    request_id = str(request_id or "").strip()
    callback_skill_id = str(callback_skill_id or "").strip()
    requester_id = str(requester_id or "").strip()
    root_folder_name = str(root_folder_name or "").strip()

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
    if not root_folder_name:
        return _result("缺少 root_folder_name", "ROOT_FOLDER_NAME_MISSING")

    candidates = _load_candidates(candidate_files_json)
    if len(candidates) != 1:
        return _result(
            "单文件确认卡片要求 candidate_files_json 恰好包含一个文件",
            "INVALID_CANDIDATE_COUNT",
        )

    candidate = candidates[0]
    file_id = str(candidate.get("id") or "").strip()
    file_name = str(candidate.get("file_name") or "").strip()
    file_type = str(candidate.get("file_type") or "").strip().lower().lstrip(".")
    if not file_id or not file_name or not file_type:
        return _result(
            "候选文件缺少内部 ID、文件名或扩展名",
            "INVALID_CANDIDATE_FILE",
        )

    return {
        "ok": True,
        "error_code": "",
        "error": "",
        "request_id_text": request_id,
        "file_name": file_name,
        "file_type": file_type,
        "root_folder_name": root_folder_name,
        "initiator": {"id": requester_id} if requester_id else {},
        "skill_object_choose_file": _make_skill_object(
            callback_skill_id,
            request_id,
            "choose_file",
            selected_file_id=file_id,
            success_message="已确认文件，正在加载归档目录…",
        ),
        "skill_object_cancel": _make_skill_object(
            callback_skill_id,
            request_id,
            "cancel",
            update_card=True,
            success_message="已取消本次归档",
        ),
    }
