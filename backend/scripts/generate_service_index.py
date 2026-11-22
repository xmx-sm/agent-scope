"""生成《服务函数索引.md》：扫描 services 下全部函数（含嵌套）、入参与 docstring。"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "app" / "services"
OUTPUT = ROOT / "doc" / "服务函数索引.md"


def collect_functions(node: ast.AST, prefix: str = "") -> list[tuple[str, ast.AST, bool]]:
    result = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualified = f"{prefix}{child.name}"
            result.append((qualified, child, not prefix))
            result.extend(collect_functions(child, qualified + "."))
        else:
            result.extend(collect_functions(child, prefix))
    return result


def main() -> None:
    by_domain: dict[str, list[tuple[Path, list]]] = {}
    total = top_public = top_helper = nested = 0
    for path in sorted(SERVICES.rglob("*.py")):
        tree = ast.parse(path.read_text())
        funcs = collect_functions(tree)
        if not funcs:
            continue
        domain = path.relative_to(SERVICES).parts[0]
        by_domain.setdefault(domain, []).append((path, funcs))
        for qualified, node, top in funcs:
            total += 1
            if top:
                if node.name.startswith("_"):
                    top_helper += 1
                else:
                    top_public += 1
            else:
                nested += 1

    lines = [
        "# 服务函数索引",
        "",
        "> 本文件由 `scripts/generate_service_index.py` 自动生成，记录每个函数的路径、入参和功能说明。",
        ">",
        "> 约定：**公开服务入口统一只接收一个 `params: dict`**；以下划线开头的内部辅助函数与嵌套函数允许显式参数。",
        ">",
        "> 重新生成：`../.venv/bin/python scripts/generate_service_index.py`",
        "",
        "## 统计",
        "",
        f"- 函数总数（含嵌套）：**{total}**",
        f"- 顶层公开服务入口：**{top_public}**",
        f"- 顶层内部辅助函数：**{top_helper}**",
        f"- 嵌套函数：**{nested}**",
        "",
    ]

    for domain in sorted(by_domain):
        lines += [f"## {domain}", ""]
        for path, funcs in by_domain[domain]:
            lines += [f"### `{path.relative_to(ROOT)}`", "", "| 函数 | 入参 | 说明 |", "|---|---|---|"]
            for qualified, node, top in funcs:
                doc = ast.get_docstring(node) or ""
                desc = next((x.strip() for x in doc.strip().splitlines() if x.strip()), "")
                param = ""
                if "参数：" in doc:
                    tail = doc.split("参数：", 1)[1]
                    param = tail.split("\n", 1)[0].strip().rstrip("。")
                if not param:
                    args = [a.arg for a in node.args.args if a.arg != "self"]
                    param = " / ".join(args) if args else "无"
                label = qualified
                if node.name.startswith("_") and top:
                    label += "（内部）"
                if not top:
                    label += "（嵌套）"
                lines.append(f"| `{label}` | {param} | {desc} |")
            lines.append("")

    OUTPUT.write_text("\n".join(lines) + "\n")
    print(f"generated {OUTPUT} ({total} functions, {top_public} public entries)")


if __name__ == "__main__":
    main()
