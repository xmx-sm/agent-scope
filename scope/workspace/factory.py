# -*- coding: utf-8 -*-
"""工作区字典工厂。

支持 AgentScope 官方的全部工作区实现：

- ``local``：本机文件系统
- ``bubblewrap``：Linux bubblewrap 沙箱
- ``docker``：Docker 容器
- ``e2b``：E2B 云沙箱
- ``daytona``：Daytona 沙箱
- ``k8s``：Kubernetes Pod + PVC
- ``opensandbox``：OpenSandbox 沙箱
- ``applecontainer``：Apple Container

所有实现共享同一接口；本层只负责：

- 字典 → 工作区实例
- ``enabled`` / ``initialize`` 开关
- 本地/容器的目录参数归一化
- 统一返回内置工具、MCP、技能与系统提示片段

不复制官方工作区的资源管理、卸载或沙箱逻辑。
"""

from __future__ import annotations

import inspect
import os
from typing import Any, Dict, List, Optional

from agentscope.workspace import (
    AppleContainerWorkspace,
    BubblewrapWorkspace,
    DaytonaWorkspace,
    DockerWorkspace,
    E2BWorkspace,
    K8sWorkspace,
    LocalWorkspace,
    OpenSandboxWorkspace,
    WorkspaceBase,
)

_WORKSPACES = {
    "local": LocalWorkspace,
    "bubblewrap": BubblewrapWorkspace,
    "bwrap": BubblewrapWorkspace,
    "docker": DockerWorkspace,
    "e2b": E2BWorkspace,
    "daytona": DaytonaWorkspace,
    "k8s": K8sWorkspace,
    "kubernetes": K8sWorkspace,
    "opensandbox": OpenSandboxWorkspace,
    "applecontainer": AppleContainerWorkspace,
    "apple_container": AppleContainerWorkspace,
}

_CONTROL_KEYS = {
    "type", "kind", "name", "enabled", "initialize", "create_dir",
    "agent_id", "session_id", "kwargs",
}


def _where(fn: str) -> str:
    return f"{os.path.abspath(__file__)}_{fn}"


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": _where(fn), "message": f"错误：{message}"}


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "y")
    return bool(value)


def _workspace_spec(data: Any) -> Optional[dict]:
    if data is None:
        return None
    if isinstance(data, WorkspaceBase):
        return {"workspace": data, "type": type(data).__name__}
    if not isinstance(data, dict):
        raise ValueError("workspace 必须是字典或 WorkspaceBase")
    if "workspace" in data:
        nested = data.get("workspace")
        if nested is None:
            return None
        if isinstance(nested, WorkspaceBase):
            return {"workspace": nested, "type": type(nested).__name__}
        if not isinstance(nested, dict):
            raise ValueError("workspace 必须是字典或 WorkspaceBase")
        merged = dict(nested)
        for key in ("agent_id", "session_id"):
            if key in data and key not in merged:
                merged[key] = data[key]
        return merged
    return dict(data)


async def async_get_workspace(data: Any = None) -> Dict[str, Any]:
    """构建工作区并返回其资源。

    本地示例::

        {
            "type": "local",
            "enabled": True,
            "workdir": "/data/tenants/u1/workspace",
            "skill_paths": ["/data/skills"],
            "agent_id": "assistant",
            "session_id": "session-1",
        }

    返回::

        {
            "workspace": WorkspaceBase,
            "tools": [...],
            "mcps": [...],
            "skills": [...],
            "instructions": "...",
            "closable": True,
        }
    """
    fn = "async_get_workspace"
    try:
        spec = _workspace_spec(data)
        if spec is None:
            return _ok({
                "workspace": None,
                "tools": [],
                "mcps": [],
                "skills": [],
                "instructions": "",
                "closable": False,
            }, "未启用工作区")

        if "workspace" in spec and isinstance(spec["workspace"], WorkspaceBase):
            workspace = spec["workspace"]
            initialized = True
        else:
            if not _as_bool(spec.get("enabled"), True):
                return _ok({
                    "workspace": None,
                    "tools": [],
                    "mcps": [],
                    "skills": [],
                    "instructions": "",
                    "closable": False,
                }, "工作区已关闭")

            wtype = str(spec.get("type") or spec.get("kind") or "local").strip().lower()
            cls = _WORKSPACES.get(wtype)
            if cls is None:
                raise ValueError(
                    f"不支持的 workspace.type: {wtype}"
                    f"（{', '.join(sorted(_WORKSPACES))}）")

            cfg = {
                k: v for k, v in spec.items()
                if k not in _CONTROL_KEYS
            }
            for key in ("path", "folder", "dir"):
                cfg.pop(key, None)
            nested_kwargs = spec.get("kwargs")
            if nested_kwargs is not None:
                if not isinstance(nested_kwargs, dict):
                    raise ValueError("workspace.kwargs 必须是字典")
                cfg.update(nested_kwargs)

            # 目录参数归一化
            path = (
                spec.get("path") or spec.get("folder") or spec.get("dir")
                or spec.get("workdir") or spec.get("host_workdir")
            )
            if wtype == "local":
                if not path:
                    raise ValueError("local workspace 必须提供 workdir / path")
                path = os.path.expanduser(str(path))
                if not os.path.isabs(path):
                    raise ValueError(f"workspace.workdir 必须是绝对路径: {path}")
                cfg["workdir"] = os.path.abspath(path)
                cfg.pop("host_workdir", None)
            elif wtype in ("bubblewrap", "bwrap", "docker"):
                if path:
                    path = os.path.expanduser(str(path))
                    if not os.path.isabs(path):
                        raise ValueError(
                            f"workspace.host_workdir 必须是绝对路径: {path}")
                    cfg["host_workdir"] = os.path.abspath(path)
                cfg.pop("workdir", None)
            else:
                # 远程沙箱没有主机 workdir；如果误传，交给签名过滤前先移除
                cfg.pop("workdir", None)
                cfg.pop("host_workdir", None)

            allowed = set(inspect.signature(cls.__init__).parameters) - {"self"}
            unknown = set(cfg) - allowed
            if unknown:
                raise ValueError(
                    f"workspace.type={wtype} 不支持参数: "
                    f"{', '.join(sorted(unknown))}")

            workspace = cls(**cfg)
            initialized = False
            if _as_bool(spec.get("initialize"), True):
                await workspace.initialize()
                initialized = True

        tools = await workspace.list_tools() if initialized else []
        instructions = await workspace.get_instructions() if initialized else ""
        agent_id = str(spec.get("agent_id") or "")
        session_id = str(spec.get("session_id") or "")
        mcps = []
        skills = []
        if initialized:
            try:
                mcps = await workspace.list_mcps(
                    agent_id=agent_id or None,
                    session_id=session_id or None,
                )
            except TypeError:
                mcps = await workspace.list_mcps()
            try:
                skills = await workspace.list_skills(agent_id=agent_id or None)
            except TypeError:
                skills = await workspace.list_skills()

        return _ok({
            "workspace": workspace,
            "type": type(workspace).__name__,
            "initialized": initialized,
            "tools": tools,
            "mcps": mcps,
            "skills": skills,
            "instructions": instructions,
            "closable": hasattr(workspace, "close"),
        }, "工作区创建成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"工作区创建失败：{type(e).__name__}: {e}", fn, 500)


__all__ = ["async_get_workspace"]
