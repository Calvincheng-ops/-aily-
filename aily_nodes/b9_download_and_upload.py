"""Aily Skill B node: download the replied message file and upload it to Drive.

v1 单节点实现：当前租户的官方连接器没有「下载消息附件」和「上传文件」操作，
自定义连接器编辑器又不支持 multipart 文件字段，因此下载和上传合并为
一个 Python 节点完成。文件全程为字节流，不经过文本序列化。

上传策略：不超过 20 MB 走 upload_all 普通上传；超过 20 MB 自动切换
upload_prepare / upload_part / upload_finish 分片上传。硬上限
MAX_UPLOAD_BYTES = 100 MB——飞书消息资源下载接口本身的限制
（错误码 234037），超过 100 MB 的消息文件无法通过 OpenAPI 下载。

凭证使用约定（2026-08-07 用户确认）：真实 APP_ID / APP_SECRET 只填在
Aily 画布的节点代码里；仓库中的本文件保持占位符，不得提交真实值。
"""

import json
import uuid
import zlib
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# === 在 Aily 画布中填写，仓库保持为空 ===
APP_ID = ""
APP_SECRET = ""
# === 在 Aily 画布中填写，仓库保持为空 ===

API_BASE = "https://open.feishu.cn/open-apis"
FILE_URL_PREFIX = "https://westoeast.feishu.cn/file/"
SINGLE_UPLOAD_MAX_BYTES = 20 * 1024 * 1024
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


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


def _post_json(
    path: str, body_obj: Dict[str, Any], token: str
) -> Tuple[int, Dict[str, Any], bytes]:
    status, payload = _http(
        f"{API_BASE}{path}",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        body=json.dumps(body_obj).encode("utf-8"),
    )
    return status, _json(payload), payload


def _form_field(boundary: str, name: str, value: str) -> bytes:
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
        f"{value}\r\n"
    ).encode("utf-8")


def _form_file(boundary: str, file_name: str, content: bytes) -> bytes:
    return (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; '
            f'filename="{file_name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
        + content
        + b"\r\n"
    )


def _post_form(
    path: str,
    fields: List[Tuple[str, str]],
    file_name: str,
    content: bytes,
    token: str,
    timeout: int = 120,
) -> Tuple[int, Dict[str, Any], bytes]:
    boundary = "----AilyForm" + uuid.uuid4().hex
    parts = [_form_field(boundary, name, value) for name, value in fields]
    parts.append(_form_file(boundary, file_name, content))
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    status, payload = _http(
        f"{API_BASE}{path}",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body=b"".join(parts),
        timeout=timeout,
    )
    return status, _json(payload), payload


def _extract_file_token(
    status: int, data: Dict[str, Any], payload: bytes, stage: str
) -> Tuple[str, str]:
    if status != 200:
        return "", f"{stage}失败：HTTP {status}，{payload[:200]!r}"
    if not data:
        return "", f"{stage}失败：响应无法解析，{payload[:200]!r}"
    if data.get("code") != 0:
        return "", f"{stage}失败：{data.get('msg') or payload[:200]!r}"
    file_token = str((data.get("data") or {}).get("file_token") or "")
    if not file_token:
        return "", f"{stage}响应缺少 file_token：{payload[:200]!r}"
    return file_token, ""


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


def _download(message_id: str, file_key: str, token: str) -> Tuple[bytes, str, str]:
    url = f"{API_BASE}/im/v1/messages/{message_id}/resources/{file_key}?type=file"
    status, payload = _http(url, headers={"Authorization": f"Bearer {token}"})
    data = _json(payload)
    api_code = data.get("code")
    if status != 200 or (isinstance(api_code, int) and api_code != 0):
        if api_code == 234037:
            return (
                b"",
                "FILE_TOO_LARGE",
                "文件超过 100 MB：飞书消息资源下载接口的硬限制，"
                "无法通过机器人归档，请直接上传到云盘目标目录。",
            )
        msg = data.get("msg") or payload[:200]
        return b"", "DOWNLOAD_FAILED", f"下载消息文件失败：HTTP {status}，{msg}"
    return payload, "", ""


def _upload_all(
    file_name: str, parent_node: str, content: bytes, token: str
) -> Tuple[str, str]:
    status, data, payload = _post_form(
        "/drive/v1/files/upload_all",
        [
            ("file_name", file_name),
            ("parent_type", "explorer"),
            ("parent_node", parent_node),
            ("size", str(len(content))),
        ],
        file_name,
        content,
        token,
    )
    return _extract_file_token(status, data, payload, "上传")


def _upload_chunked(
    file_name: str, parent_node: str, content: bytes, token: str
) -> Tuple[str, str]:
    size = len(content)
    status, data, payload = _post_json(
        "/drive/v1/files/upload_prepare",
        {
            "file_name": file_name,
            "parent_type": "explorer",
            "parent_node": parent_node,
            "size": size,
        },
        token,
    )
    if status != 200 or data.get("code") != 0:
        return "", (
            f"分片预上传失败：HTTP {status}，{data.get('msg') or payload[:200]!r}"
        )
    prepare = data.get("data") or {}
    upload_id = str(prepare.get("upload_id") or "")
    block_size = int(prepare.get("block_size") or 0)
    block_num = int(prepare.get("block_num") or 0)
    if not upload_id or block_size <= 0 or block_num <= 0:
        return "", f"分片预上传响应无效：{payload[:200]!r}"

    for seq in range(block_num):
        chunk = content[seq * block_size : (seq + 1) * block_size]
        if not chunk:
            break
        status, data, payload = _post_form(
            "/drive/v1/files/upload_part",
            [
                ("upload_id", upload_id),
                ("seq", str(seq)),
                ("size", str(len(chunk))),
                ("checksum", str(zlib.adler32(chunk))),
            ],
            file_name,
            chunk,
            token,
        )
        if status != 200 or data.get("code") != 0:
            return "", (
                f"分片上传失败（第 {seq + 1}/{block_num} 片）：HTTP {status}，"
                f"{data.get('msg') or payload[:200]!r}"
            )

    status, data, payload = _post_json(
        "/drive/v1/files/upload_finish",
        {"upload_id": upload_id, "block_num": block_num},
        token,
    )
    return _extract_file_token(status, data, payload, "分片完成")


def _upload(
    file_name: str, parent_node: str, content: bytes, token: str
) -> Tuple[str, str]:
    if len(content) <= SINGLE_UPLOAD_MAX_BYTES:
        return _upload_all(file_name, parent_node, content, token)
    return _upload_chunked(file_name, parent_node, content, token)


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

    content, err_code, err = _download(message_id, file_key, token)
    if err:
        return _fail(result, err_code, err)

    size = len(content)
    result["actual_size"] = size
    if size <= 0:
        return _fail(result, "FILE_EMPTY", "下载后的文件大小必须大于 0。")
    if size > MAX_UPLOAD_BYTES:
        return _fail(
            result,
            "FILE_TOO_LARGE",
            "文件超过 "
            f"{MAX_UPLOAD_BYTES // 1024 // 1024} MB 上传上限，请先拆分或压缩。",
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
