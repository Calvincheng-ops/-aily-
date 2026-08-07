"""Aily Skill B node: download the replied message file and upload it to Drive.

v1 单节点实现：当前租户的官方连接器没有「下载消息附件」和「上传文件」操作，
自定义连接器编辑器又不支持 multipart 文件字段，因此下载和上传合并为
一个 Python 节点完成。文件全程为字节流，不经过文本序列化。

凭证使用约定（2026-08-07 用户确认）：真实 APP_ID / APP_SECRET 只填在
Aily 画布的节点代码里；仓库中的本文件保持占位符，不得提交真实值。
"""

import json
import uuid
from typing import Any, Dict, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# === 在 Aily 画布中填写，仓库保持为空 ===
APP_ID = ""
APP_SECRET = ""
# === 在 Aily 画布中填写，仓库保持为空 ===

API_BASE = "https://open.feishu.cn/open-apis"
FILE_URL_PREFIX = "https://westoeast.feishu.cn/file/"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _base_result() -> Dict[str, Any]:
    return {
        "ok": False,
        "error_code": "",
        "error": "",
        "file_token": "",
        "file_url": "",
        "actual_size": 0,
    }


def _fail(result: Dict[str, Any], code: str, message: str) -> Dict[str, Any]:
    result["error_code"] = code
    result["error"] = message
    return result


def _http(
    url: str,
    method: str = "GET",
    headers: Dict[str, str] = None,
    body: bytes = None,
    timeout: int = 60,
) -> Tuple[int, bytes]:
    req = Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return getattr(resp, "status", 200), resp.read()
    except HTTPError as exc:
        try:
            return exc.code, exc.read()
        except Exception:
            return exc.code, b""
    except (URLError, OSError) as exc:
        return 0, str(exc).encode("utf-8", errors="replace")


def _json(payload: bytes) -> Dict[str, Any]:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _tenant_token(app_id: str, app_secret: str) -> Tuple[str, str]:
    status, payload = _http(
        f"{API_BASE}/auth/v3/tenant_access_token/internal",
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
        body=json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8"),
    )
    data = _json(payload)
    token = str(data.get("tenant_access_token") or "")
    if status != 200 or not token:
        return "", f"获取 tenant_access_token 失败：HTTP {status}，{payload[:200]!r}"
    return token, ""


def _download(message_id: str, file_key: str, token: str) -> Tuple[bytes, str]:
    url = f"{API_BASE}/im/v1/messages/{message_id}/resources/{file_key}?type=file"
    status, payload = _http(url, headers={"Authorization": f"Bearer {token}"})
    if status != 200:
        return b"", f"下载消息文件失败：HTTP {status}，{payload[:200]!r}"
    data = _json(payload)
    if isinstance(data.get("code"), int) and data["code"] != 0:
        return b"", f"下载消息文件失败：{data.get('msg') or payload[:200]!r}"
    return payload, ""


def _upload(
    file_name: str,
    parent_node: str,
    content: bytes,
    token: str,
) -> Tuple[str, str]:
    boundary = "----AilyForm" + uuid.uuid4().hex

    def _field(name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")

    body = b"".join(
        [
            _field("file_name", file_name),
            _field("parent_type", "explorer"),
            _field("parent_node", parent_node),
            _field("size", str(len(content))),
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; '
                f'filename="{file_name}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode("utf-8")
            + content
            + b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    status, payload = _http(
        f"{API_BASE}/drive/v1/files/upload_all",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body=body,
        timeout=120,
    )
    data = _json(payload)
    if status != 200:
        return "", f"上传失败：HTTP {status}，{payload[:200]!r}"
    if not data:
        return "", f"上传失败：响应无法解析，{payload[:200]!r}"
    if data.get("code") != 0:
        return "", f"上传失败：{data.get('msg') or payload[:200]!r}"
    file_token = str((data.get("data") or {}).get("file_token") or "")
    if not file_token:
        return "", f"上传响应缺少 file_token：{payload[:200]!r}"
    return file_token, ""


def main(
    message_id: str,
    file_key: str,
    file_name: str,
    parent_node: str,
    app_id: str = "",
    app_secret: str = "",
) -> Dict[str, Any]:
    """Download a message resource and upload it to a Drive folder."""
    result = _base_result()
    message_id = str(message_id or "").strip()
    file_key = str(file_key or "").strip()
    file_name = str(file_name or "").strip()
    parent_node = str(parent_node or "").strip()
    app_id = str(app_id or APP_ID).strip()
    app_secret = str(app_secret or APP_SECRET).strip()

    if not app_id or not app_secret:
        return _fail(
            result,
            "CREDENTIALS_MISSING",
            "节点缺少应用凭证：请在代码顶部填入 APP_ID 和 APP_SECRET。",
        )
    missing = [
        label
        for label, value in (
            ("message_id", message_id),
            ("file_key", file_key),
            ("file_name", file_name),
            ("parent_node", parent_node),
        )
        if not value
    ]
    if missing:
        return _fail(
            result,
            "PARAM_MISSING",
            "下载上传缺少参数：" + ", ".join(missing),
        )

    token, err = _tenant_token(app_id, app_secret)
    if err:
        return _fail(result, "TOKEN_FAILED", err)

    content, err = _download(message_id, file_key, token)
    if err:
        return _fail(result, "DOWNLOAD_FAILED", err)

    size = len(content)
    result["actual_size"] = size
    if size <= 0:
        return _fail(result, "FILE_EMPTY", "下载后的文件大小必须大于 0。")
    if size > MAX_UPLOAD_BYTES:
        return _fail(
            result,
            "FILE_TOO_LARGE",
            "文件超过 20 MB 普通上传上限，请使用分片上传流程。",
        )

    file_token, err = _upload(file_name, parent_node, content, token)
    if err:
        return _fail(result, "UPLOAD_FAILED", err)

    result.update(
        {
            "ok": True,
            "file_token": file_token,
            "file_url": FILE_URL_PREFIX + file_token,
        }
    )
    return result
