"""Aily Skill B node: compute the byte size of downloaded file content.

下载消息资源的自定义连接器只返回 ``code``/``data``/``message``，文件内容在
``data`` 里，没有大小字段。本节点计算真实字节数，供
``b6_validate_upload_policy.py`` 校验和上传节点填写大小使用。

只负责测量，不做策略判断：空内容返回 ``actual_size=0``，由 B17 统一拒绝。
"""

from typing import Any, Dict


def main(file_content: Any) -> Dict[str, Any]:
    """Return the byte length of the downloaded content."""
    if file_content is None:
        return {
            "ok": False,
            "error_code": "FILE_CONTENT_MISSING",
            "error": "下载节点没有返回文件内容，请检查 B15 的 data 绑定。",
            "actual_size": 0,
        }
    if isinstance(file_content, (bytes, bytearray)):
        size = len(file_content)
    else:
        size = len(str(file_content).encode("utf-8"))
    return {
        "ok": True,
        "error_code": "",
        "error": "",
        "actual_size": size,
    }
