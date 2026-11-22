"""scope 框架路径桥接。"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCOPE_DIR = ROOT / "scope"
WORKSPACE_ROOT = ROOT / "backend" / "uploads" / "agents"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCOPE_DIR) not in sys.path:
    sys.path.insert(0, str(SCOPE_DIR))


def user_workspace(params: dict) -> str:
    """确保并返回用户工作目录。参数：user_id。"""
    path = WORKSPACE_ROOT / f"user_{params['user_id']}" / "workspace"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)
