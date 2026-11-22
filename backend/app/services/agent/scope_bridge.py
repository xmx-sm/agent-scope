"""scope 框架路径桥接。"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCOPE_DIR = ROOT / "scope"
WORKSPACE_ROOT = ROOT / "backend" / "uploads" / "agents"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCOPE_DIR) not in sys.path:
    sys.path.insert(0, str(SCOPE_DIR))


def user_workspace(user_id: str) -> str:
    path = WORKSPACE_ROOT / f"user_{user_id}" / "workspace"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)
