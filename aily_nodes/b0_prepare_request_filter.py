"""Aily Skill B node: adapt a scalar request ID for Base record filters."""

from typing import Any, Dict


def main(request_id: str) -> Dict[str, Any]:
    """Return both scalar and list forms of a card callback request ID.

    Args:
        request_id: Scalar request ID from Skill B's start node.

    Returns:
        A stable result containing ``request_id_filter_values`` as a real list.
    """
    request_id = str(request_id or "").strip()
    if not request_id:
        return {
            "ok": False,
            "error_code": "REQUEST_ID_MISSING",
            "error": "技能 B 开始节点缺少 request_id。",
            "request_id": "",
            "request_id_filter_values": [],
        }
    return {
        "ok": True,
        "error_code": "",
        "error": "",
        "request_id": request_id,
        "request_id_filter_values": [request_id],
    }
