"""Aily utility node: return the current Unix timestamp in milliseconds."""

import time
from typing import Dict


def main() -> Dict[str, int]:
    return {"now_ms": int(time.time() * 1000)}
