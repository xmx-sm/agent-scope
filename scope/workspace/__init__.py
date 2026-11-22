# -*- coding: utf-8 -*-
"""工作区层：官方 WorkspaceBase 的字典构建与资源发现。

官方工作区负责沙箱、工具绑定、MCP、技能和上下文卸载；本层只做：

- 字典 → Local / Bubblewrap / Docker / E2B / Daytona / K8s /
  OpenSandbox / AppleContainer
- 目录参数归一化
- 初始化后返回 `list_tools` / `list_mcps` / `list_skills` / instructions

不复制官方工作区实现。
"""

from .factory import async_get_workspace

__all__ = ["async_get_workspace"]
