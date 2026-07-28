"""Aily Skill B node: convert a Drive listing into folder-card variables.

节点输入建议：
- folder_list_result: “获取文件夹下的清单”节点的完整输出（object 或 JSON string）
- request_id: 技能 B 开始节点自定义参数，并已据此恢复归档请求
- selected_file_name: 归档请求 selected_file_name
- current_folder_token/name/url: 归档请求当前目录
- folder_path_json: 归档请求 folder_path_json
- requester_id: 归档请求 requester_id
- warning: 归档请求 warning_message
- callback_skill_id: 已发布技能 B 的 skill_xxx

重要：先调试 Aily 代码节点，让平台自动解析本文件 main() 的返回对象；再确认
下游可以通过“节点名.folder_options”等路径选择命名输出。旧版界面未自动解析时，
再使用 JSON 示例手动补齐输出结构。
"""

import json
from typing import Any, Dict, List, Optional


def _load_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return default
    return default


def _extract_files(payload: Any) -> List[Dict[str, Any]]:
    """兼容 Aily 外层包装：data.data.files、data.files 或 files。"""
    data = _load_json(payload, {})
    for _ in range(5):
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if not isinstance(data, dict):
            return []
        files = data.get("files")
        if isinstance(files, list):
            return [item for item in files if isinstance(item, dict)]
        if "data" in data:
            data = _load_json(data.get("data"), data.get("data"))
            continue
        if "result" in data:
            data = _load_json(data.get("result"), data.get("result"))
            continue
        break
    return []


def _make_skill_object(
    callback_skill_id: str,
    request_id: str,
    action: str,
    update_card: bool = True,
    success_message: str = "",
) -> Dict[str, Any]:
    result = {
        "x_aily_forbid_forward_callback": True,
        "aily_action": "trigger_skill",
        "skill_id": callback_skill_id,
        # skill_input 必须是 JSON 字符串；表单字段由卡片本身另外回传。
        "skill_input": json.dumps(
            {"request_id": request_id, "action": action},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "update_card": update_card,
    }
    if update_card and success_message:
        result["success_message"] = success_message
    return result


def _empty_result(
    error: str,
    error_code: str = "",
    observed_parent_tokens: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "error_code": error_code,
        "error": error,
        "folder_options": [],
        "folder_options_json": "[]",
        "allowed_child_folders_json": "[]",
        "child_folder_count": 0,
        "has_subfolders": False,
        "show_back": False,
        "disable_folder_browse": True,
        "disable_back": True,
        "breadcrumb": "",
        "initiator": {},
        "selected_file_name": "",
        "current_folder_token": "",
        "current_folder_name": "",
        "current_folder_url": "",
        "warning": "",
        "observed_parent_tokens_json": json.dumps(
            observed_parent_tokens or [], ensure_ascii=False
        ),
        "skill_object_browse": {},
        "skill_object_back": {},
        "skill_object_choose_current": {},
        "skill_object_cancel": {},
    }


def main(
    folder_list_result: Any,
    request_id: str,
    selected_file_name: str,
    current_folder_token: str,
    current_folder_name: str,
    current_folder_url: str,
    folder_path_json: Any,
    requester_id: str = "",
    warning: str = "",
    callback_skill_id: str = "",
) -> Dict[str, Any]:
    request_id = str(request_id or "").strip()
    current_folder_token = str(current_folder_token or "").strip()
    current_folder_name = str(current_folder_name or "").strip()
    current_folder_url = str(current_folder_url or "").strip()
    requester_id = str(requester_id or "").strip()
    callback_skill_id = str(callback_skill_id or "").strip()

    if not request_id:
        return _empty_result("缺少 request_id", "REQUEST_ID_MISSING")
    if not current_folder_token:
        return _empty_result(
            "归档请求缺少 current_folder_token",
            "CURRENT_FOLDER_TOKEN_MISSING",
        )
    if not callback_skill_id:
        return _empty_result(
            "缺少 callback_skill_id；请填写已发布技能 B 的 skill_xxx",
            "CALLBACK_SKILL_ID_MISSING",
        )
    if not callback_skill_id.startswith("skill_"):
        return _empty_result(
            "callback_skill_id 必须是已发布技能 B 的 skill_xxx",
            "CALLBACK_SKILL_ID_INVALID",
        )

    files = _extract_files(folder_list_result)
    observed_parent_tokens = sorted(
        {
            str(item.get("parent_token") or "").strip()
            for item in files
            if str(item.get("parent_token") or "").strip()
        }
    )

    missing_parent_count = sum(
        1 for item in files if not str(item.get("parent_token") or "").strip()
    )
    if missing_parent_count:
        return _empty_result(
            "目录清单存在缺少 parent_token 的返回项，无法验证目录边界",
            "FOLDER_PARENT_MISSING",
            observed_parent_tokens,
        )

    # 有返回项时，每一项都应是当前目录的直属子项。检查失败时禁止把错误目录发到卡片。
    wrong_parents = [token for token in observed_parent_tokens if token != current_folder_token]
    if wrong_parents:
        return _empty_result(
            "清单节点查到的不是当前目录：期望 parent_token="
            + current_folder_token
            + "，实际="
            + ",".join(wrong_parents),
            "FOLDER_OUT_OF_BOUNDARY",
            observed_parent_tokens,
        )

    child_folders: List[Dict[str, str]] = []
    seen_tokens = set()
    for item in files:
        if str(item.get("type") or "").lower() != "folder":
            continue
        token = str(item.get("token") or "").strip()
        name = str(item.get("name") or "未命名文件夹").strip()
        if not token or token in seen_tokens:
            continue
        seen_tokens.add(token)
        child_folders.append(
            {
                "token": token,
                "name": name,
                "url": str(item.get("url") or "").strip(),
                "parent_token": current_folder_token,
            }
        )

    child_folders.sort(key=lambda item: (item["name"].casefold(), item["token"]))

    # 飞书新版卡片“选项数组”的官方结构就是 text/value，可直接绑定下拉组件。
    folder_options = [
        {"text": item["name"], "value": item["token"]} for item in child_folders
    ]

    path = _load_json(folder_path_json, [])
    if not isinstance(path, list):
        path = []
    clean_path = [item for item in path if isinstance(item, dict)]
    if not clean_path:
        clean_path = [
            {
                "token": current_folder_token,
                "name": current_folder_name or "根目录",
                "url": current_folder_url,
            }
        ]
    breadcrumb = " / ".join(
        str(item.get("name") or "未命名目录") for item in clean_path
    )

    return {
        "ok": True,
        "error_code": "",
        "error": "",
        "folder_options": folder_options,
        "folder_options_json": json.dumps(folder_options, ensure_ascii=False),
        "allowed_child_folders_json": json.dumps(child_folders, ensure_ascii=False),
        "child_folder_count": len(child_folders),
        "has_subfolders": bool(child_folders),
        "show_back": len(clean_path) > 1,
        # 新版卡片不支持用变量控制组件显隐，改为绑定“是否禁用”。
        "disable_folder_browse": not bool(child_folders),
        "disable_back": len(clean_path) <= 1,
        "breadcrumb": breadcrumb,
        "initiator": {"id": requester_id} if requester_id else {},
        "selected_file_name": str(selected_file_name or ""),
        "current_folder_token": current_folder_token,
        "current_folder_name": current_folder_name,
        "current_folder_url": current_folder_url,
        "warning": str(warning or ""),
        "observed_parent_tokens_json": json.dumps(
            observed_parent_tokens, ensure_ascii=False
        ),
        "skill_object_browse": _make_skill_object(
            callback_skill_id,
            request_id,
            "browse",
            success_message="正在进入选中的文件夹…",
        ),
        "skill_object_back": _make_skill_object(
            callback_skill_id,
            request_id,
            "back",
            success_message="正在返回上一级目录…",
        ),
        "skill_object_choose_current": _make_skill_object(
            callback_skill_id,
            request_id,
            "choose_current_folder",
            success_message="已选择当前目录，正在生成最终确认…",
        ),
        "skill_object_cancel": _make_skill_object(
            callback_skill_id,
            request_id,
            "cancel",
            update_card=True,
            success_message="已取消本次归档",
        ),
    }
