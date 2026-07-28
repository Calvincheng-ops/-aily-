"""Aily helper node: convert a URL string into a Base URL cell object."""

from typing import Any, Dict


def main(url: str, text: str = "") -> Dict[str, Any]:
    """Build the object required when writing a Base URL field."""
    url = str(url or "").strip()
    text = str(text or "").strip()
    if not url:
        return {
            "ok": False,
            "error_code": "URL_MISSING",
            "error": "缺少需要写入 Base 的 URL。",
            "url": "",
            "url_object": {},
        }
    return {
        "ok": True,
        "error_code": "",
        "error": "",
        "url": url,
        "url_object": {
            "text": text or url,
            "link": url,
        },
    }
