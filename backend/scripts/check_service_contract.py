"""检查服务层契约：公开入口 params 字典 + 所有函数有 docstring。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "app" / "services"


def main() -> int:
    errors: list[str] = []
    for path in sorted(SERVICES.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not (ast.get_docstring(node) or "").strip():
                errors.append(f"{path}:{node.name}@{node.lineno} 缺少 docstring")
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = [arg.arg for arg in node.args.args]
            if not node.name.startswith("_") and args != ["params"]:
                errors.append(f"{path}:{node.name} 公开函数必须只接收 params: dict，当前 {args}")
    if errors:
        print("服务契约检查失败：")
        for item in errors:
            print(" -", item)
        return 1
    print("服务契约检查通过：公开入口全部字典传参，全部函数（含嵌套）均有说明。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
