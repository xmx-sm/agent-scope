# -*- coding: utf-8 -*-
"""Agent 中间件工厂。

全部通过字典构建，``enabled`` 控制是否启用。支持：

- ``tracing``：TracingMiddleware
- ``budget``：ReplyBudgetControlMiddleware
- ``tts``：TTSMiddleware
- ``model_router``：ModelRouterMiddleware
- ``rag``：RAGMiddleware（复用 ``scope.rag``）
- ``agentic_memory``：AgenticMemoryMiddleware
- ``reme``：ReMeMiddleware
- ``mem0``：Mem0Middleware
- ``steering``：SteeringMiddleware
- ``custom``：直接传入 MiddlewareBase 对象，或按类路径导入

字典形状：:

    {
        "middlewares": [
            {"type": "tracing", "enabled": True},
            {"type": "budget", "enabled": True, "token_budget": 10000},
            {
                "type": "tts",
                "enabled": False,
                "tts": {"provider": "dashscope", "model": "qwen3-tts-flash"},
            },
            {
                "type": "rag",
                "enabled": True,
                "knowledge_bases": [...],
                "search_config": {"mode": "agentic"},
            },
        ],
    }

也支持按键名展开::

    {
        "tracing": {"enabled": True},
        "budget": {"enabled": True, "token_budget": 10000},
    }

列表中未写 ``enabled`` 时默认启用；写 ``False`` 则跳过。
"""

from __future__ import annotations

import importlib
import inspect
import os
from typing import Any, Dict, List, Optional

from agentscope.middleware import (
    AgenticMemoryMiddleware,
    ChatModelCandidate,
    MiddlewareBase,
    ModelRouterMiddleware,
    ReMeMiddleware,
    ReplyBudgetControlMiddleware,
    SteeringMiddleware,
    TTSMiddleware,
    TracingMiddleware,
)
from agentscope.tool import Edit, Read, Write

try:
    from ..llm.agent_model import (
        async_get_embedding_model,
        async_get_llm_model,
        async_get_tts_model,
    )
    from ..rag.knowledge import async_create_rag_middleware
except ImportError:
    from llm.agent_model import (
        async_get_embedding_model,
        async_get_llm_model,
        async_get_tts_model,
    )
    from rag.knowledge import async_create_rag_middleware

_BUILTIN_TYPES = {
    "tracing", "budget", "reply_budget", "tts", "model_router", "router",
    "rag", "agentic_memory", "agentic", "reme", "mem0", "steering", "custom",
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


def _specs(data: Any) -> List[Any]:
    if data is None:
        return []
    if isinstance(data, MiddlewareBase):
        return [data]
    if isinstance(data, list):
        return list(data)
    if not isinstance(data, dict):
        raise ValueError("middlewares 必须是列表、字典或 MiddlewareBase")

    if "enabled" in data and not _as_bool(data.get("enabled"), True):
        return []

    if "middlewares" in data:
        raw = data.get("middlewares")
        if raw is None:
            return []
        if isinstance(raw, (list, dict)):
            return _specs(raw)
        raise ValueError("middlewares 必须是列表或字典")
    if "middleware" in data:
        raw = data.get("middleware")
        if raw is None:
            return []
        return _specs(raw) if isinstance(raw, (list, dict)) else [raw]
    if "type" in data or "kind" in data:
        return [data]

    # 按键名展开：{"tracing": {...}, "budget": {...}}
    specs = []
    for key, value in data.items():
        if key in ("enabled", "type", "kind", "name"):
            continue
        if key not in _BUILTIN_TYPES:
            raise ValueError(f"未知 middleware 类型: {key}")
        if value is None or value is False:
            continue
        if value is True:
            specs.append({"type": key, "enabled": True})
        elif isinstance(value, dict):
            specs.append({"type": key, **value})
        else:
            raise ValueError(f"middleware.{key} 必须是字典或 bool")
    return specs


async def _chat_model(value: Any, label: str):
    if value is None:
        raise ValueError(f"缺少 {label}")
    if not isinstance(value, dict):
        return value
    cfg = value.get("llm") if isinstance(value.get("llm"), dict) else value
    r = await async_get_llm_model({"llm": cfg})
    if r.get("code") != 200:
        raise ValueError(f"{label} 构建失败：{r.get('message')}")
    return r["data"]


async def _embedding_model(value: Any, label: str):
    if value is None:
        return None
    if not isinstance(value, dict):
        return value
    cfg = value.get("embedding") if isinstance(value.get("embedding"), dict) else value
    r = await async_get_embedding_model({"embedding": cfg})
    if r.get("code") != 200:
        raise ValueError(f"{label} 构建失败：{r.get('message')}")
    return r["data"]


async def _tts_model(value: Any, label: str):
    if value is None:
        raise ValueError(f"缺少 {label}")
    if not isinstance(value, dict):
        return value
    cfg = value.get("tts") if isinstance(value.get("tts"), dict) else value
    r = await async_get_tts_model({"tts": cfg})
    if r.get("code") != 200:
        raise ValueError(f"{label} 构建失败：{r.get('message')}")
    return r["data"]


async def _build_one(spec: Any) -> Optional[MiddlewareBase]:
    if isinstance(spec, MiddlewareBase):
        return spec
    if not isinstance(spec, dict):
        raise ValueError(
            f"middleware 元素必须是字典或 MiddlewareBase，收到 {type(spec).__name__}")

    if not _as_bool(spec.get("enabled"), True):
        return None

    mw_type = str(spec.get("type") or spec.get("kind") or spec.get("name") or "").strip().lower()
    if not mw_type:
        raise ValueError("middleware 缺少 type")
    cfg = {k: v for k, v in spec.items()
           if k not in ("type", "kind", "name", "enabled")}

    if mw_type == "tracing":
        return TracingMiddleware()

    if mw_type in ("budget", "reply_budget"):
        if "token_budget" not in cfg:
            raise ValueError("budget 缺少 token_budget")
        kwargs = {
            "token_budget": float(cfg["token_budget"]),
            "input_token_weight": float(cfg.get("input_token_weight", 1)),
            "output_token_weight": float(cfg.get("output_token_weight", 1)),
        }
        if cfg.get("hint_message"):
            kwargs["hint_message"] = str(cfg["hint_message"])
        return ReplyBudgetControlMiddleware(**kwargs)

    if mw_type == "tts":
        model = await _tts_model(cfg.get("tts") or cfg.get("tts_model"), "tts")
        return TTSMiddleware(
            model,
            continue_on_error=_as_bool(cfg.get("continue_on_error"), False),
        )

    if mw_type in ("model_router", "router"):
        classifier = await _chat_model(
            cfg.get("classifier_model") or cfg.get("classifier"),
            "model_router.classifier_model",
        )
        raw_candidates = cfg.get("candidates")
        if not isinstance(raw_candidates, list) or not raw_candidates:
            raise ValueError("model_router.candidates 必须是非空列表")
        candidates = []
        for i, item in enumerate(raw_candidates):
            if not isinstance(item, dict):
                raise ValueError(f"candidates[{i}] 必须是字典")
            name = str(item.get("name") or "").strip()
            desc = str(item.get("description") or "").strip()
            if not name or not desc:
                raise ValueError(f"candidates[{i}] 缺少 name / description")
            model = await _chat_model(
                item.get("model") or item.get("llm"),
                f"candidates[{i}].model",
            )
            candidates.append(ChatModelCandidate(
                name=name, model=model, description=desc))
        return ModelRouterMiddleware(
            classifier_model=classifier,
            candidates=candidates,
            instructions=cfg.get("instructions")
            or "Select the most suitable chat model for responding to the user input.",
        )

    if mw_type == "rag":
        rag_cfg = cfg.get("rag") or cfg.get("config") or cfg
        if not isinstance(rag_cfg, dict):
            raise ValueError("rag 配置必须是字典")
        r = await async_create_rag_middleware(rag_cfg)
        if r.get("code") != 200:
            raise ValueError(r.get("message") or "RAGMiddleware 构建失败")
        return r["data"]["middleware"]

    if mw_type in ("agentic_memory", "agentic"):
        workdir = cfg.get("workdir")
        if not workdir:
            raise ValueError("agentic_memory 缺少 workdir")
        if not os.path.isabs(str(workdir)):
            raise ValueError(f"agentic_memory.workdir 必须是绝对路径: {workdir}")
        params = cfg.get("parameters")
        if isinstance(params, dict):
            params = AgenticMemoryMiddleware.Parameters.model_validate(params)
        return AgenticMemoryMiddleware(
            workdir=str(workdir),
            memory_dir=str(cfg.get("memory_dir") or "Memory"),
            parameters=params,
            backend=cfg.get("backend"),
        )

    if mw_type == "reme":
        params = cfg.get("parameters")
        if isinstance(params, dict):
            params = ReMeMiddleware.Parameters.model_validate(params)
        return ReMeMiddleware(
            workspace_dir=str(cfg.get("workspace_dir") or cfg.get("workdir") or ".reme"),
            parameters=params,
        )

    if mw_type == "mem0":
        from agentscope.middleware import Mem0Middleware

        kwargs = dict(cfg)
        if not kwargs.get("user_id"):
            raise ValueError("mem0 缺少 user_id")
        if isinstance(kwargs.get("chat_model"), dict):
            kwargs["chat_model"] = await _chat_model(kwargs["chat_model"], "mem0.chat_model")
        if isinstance(kwargs.get("embedding_model"), dict):
            kwargs["embedding_model"] = await _embedding_model(
                kwargs["embedding_model"], "mem0.embedding_model")
        allowed = set(inspect.signature(Mem0Middleware.__init__).parameters) - {"self"}
        unknown = set(kwargs) - allowed
        if unknown:
            raise ValueError(f"mem0 不支持的参数: {', '.join(sorted(unknown))}")
        return Mem0Middleware(**kwargs)

    if mw_type == "steering":
        source = cfg.get("source")
        if source is None:
            raise ValueError("steering 缺少 source")
        return SteeringMiddleware(
            source,
            hint_source=str(cfg.get("hint_source") or "steering"),
        )

    if mw_type == "custom":
        mw = cfg.get("middleware") or cfg.get("instance")
        if mw is not None:
            if not isinstance(mw, MiddlewareBase):
                raise ValueError("custom.middleware 必须是 MiddlewareBase")
            return mw
        cls_path = cfg.get("class") or cfg.get("class_path")
        if not cls_path:
            raise ValueError("custom 缺少 middleware 或 class")
        module_name, _, attr = str(cls_path).rpartition(".")
        if not module_name:
            raise ValueError("custom.class 必须是完整类路径，如 'pkg.mod.Class'")
        cls = getattr(importlib.import_module(module_name), attr)
        args = cfg.get("args") or []
        kwargs = cfg.get("kwargs") or {}
        if not isinstance(args, list) or not isinstance(kwargs, dict):
            raise ValueError("custom.args 必须是列表，custom.kwargs 必须是字典")
        mw = cls(*args, **kwargs)
        if not isinstance(mw, MiddlewareBase):
            raise ValueError("custom.class 构造结果不是 MiddlewareBase")
        return mw

    raise ValueError(f"不支持的 middleware 类型: {mw_type}")


async def async_get_middlewares(data: Any = None) -> Dict[str, Any]:
    """从字典构建中间件列表，返回统一信封。"""
    fn = "async_get_middlewares"
    try:
        specs = _specs(data)
        result: List[MiddlewareBase] = []
        for i, spec in enumerate(specs):
            try:
                mw = await _build_one(spec)
            except Exception as e:
                raise ValueError(f"middlewares[{i}] 构建失败：{e}") from e
            if mw is not None:
                result.append(mw)
        return _ok(result, f"共创建 {len(result)} 个中间件")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"中间件创建失败：{type(e).__name__}: {e}", fn, 500)


async def async_get_memory(data: Any = None) -> Dict[str, Any]:
    """构建一个长期记忆中间件，并返回它需要的工具。

    支持三种实现：

    - ``agentic`` / ``local`` / ``file``：本地 Markdown 文件记忆
    - ``reme``：ReMe 文件型记忆
    - ``mem0``：mem0 记忆

    本地文件记忆的存放目录必须由字典传入（绝对路径）::

        {
            "type": "agentic",
            "enabled": True,
            "path": "/data/tenants/u1/memory",
            "create_dir": True,
            "memory_dir": "Memory",
            "tools": {"enabled": True},
        }

    返回::

        {
            "type": "agentic",
            "middleware": AgenticMemoryMiddleware,
            "tools": [Read, Write, Edit],
            "closable": False,
        }
    """
    fn = "async_get_memory"
    try:
        if data is None:
            return _ok({
                "type": None,
                "middleware": None,
                "tools": [],
                "closable": False,
            }, "未启用长期记忆")
        if not isinstance(data, dict):
            raise ValueError("memory 必须是字典")
        if not _as_bool(data.get("enabled"), True):
            return _ok({
                "type": None,
                "middleware": None,
                "tools": [],
                "closable": False,
            }, "长期记忆已关闭")

        mw_type = str(
            data.get("type") or data.get("kind") or data.get("backend_type")
            or "agentic"
        ).strip().lower()
        spec = dict(data)
        tools_cfg = spec.get("tools", True)
        if isinstance(tools_cfg, dict):
            tools_enabled = _as_bool(tools_cfg.get("enabled"), True)
        else:
            tools_enabled = _as_bool(tools_cfg, True)

        if mw_type in ("agentic", "agentic_memory", "local", "file", "markdown"):
            path = (
                data.get("path") or data.get("folder") or data.get("dir")
                or data.get("workdir") or data.get("base_dir")
            )
            if not path:
                raise ValueError(
                    "本地文件记忆缺少存放目录：memory.path / workdir / folder")
            path = str(path)
            if not os.path.isabs(os.path.expanduser(path)):
                raise ValueError(f"memory.path 必须是绝对路径: {path}")
            path = os.path.abspath(os.path.expanduser(path))
            if not os.path.isdir(path):
                if _as_bool(data.get("create_dir"), False):
                    os.makedirs(path, exist_ok=True)
                else:
                    raise ValueError(
                        f"memory.path 目录不存在: {path}（可传 create_dir=True）")
            spec["type"] = "agentic_memory"
            spec["workdir"] = path
            spec.pop("path", None)
            spec.pop("folder", None)
            spec.pop("dir", None)
            spec.pop("base_dir", None)
            mw = await _build_one(spec)
            backend = data.get("backend")
            tools = []
            if tools_enabled:
                kwargs = {"backend": backend} if backend is not None else {}
                tools = [Read(**kwargs), Write(**kwargs), Edit(**kwargs)]
            return _ok({
                "type": "agentic",
                "middleware": mw,
                "tools": tools,
                "closable": False,
            }, "本地文件长期记忆创建成功")

        if mw_type == "reme":
            path = (
                data.get("path") or data.get("workspace_dir")
                or data.get("folder") or data.get("dir")
            )
            spec["type"] = "reme"
            if path:
                raw_path = os.path.expanduser(str(path))
                if not os.path.isabs(raw_path):
                    raise ValueError(f"memory.path 必须是绝对路径: {path}")
                spec["workspace_dir"] = os.path.abspath(raw_path)
            mw = await _build_one(spec)
            tools = await collect_middleware_tools([mw]) if tools_enabled else []
            return _ok({
                "type": "reme",
                "middleware": mw,
                "tools": tools,
                "closable": hasattr(mw, "close"),
            }, "ReMe 长期记忆创建成功")

        if mw_type == "mem0":
            spec["type"] = "mem0"
            for key in ("tools", "create_dir", "path", "folder", "dir"):
                spec.pop(key, None)
            mw = await _build_one(spec)
            tools = await collect_middleware_tools([mw]) if tools_enabled else []
            return _ok({
                "type": "mem0",
                "middleware": mw,
                "tools": tools,
                "closable": hasattr(mw, "close"),
            }, "Mem0 长期记忆创建成功")

        raise ValueError(
            f"不支持的 memory.type: {mw_type}（agentic/reme/mem0）")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"长期记忆创建失败：{type(e).__name__}: {e}", fn, 500)


async def collect_middleware_tools(middlewares: List[MiddlewareBase]) -> List[Any]:
    """收集中间件 ``list_tools()`` 贡献的工具。

    Agent 不会自动调用该 hook；需要时可显式把结果加入 Toolkit。
    """
    tools: List[Any] = []
    for middleware in middlewares or []:
        hook = getattr(middleware, "list_tools", None)
        if not callable(hook):
            continue
        try:
            value = hook()
            if inspect.isawaitable(value):
                value = await value
            if value:
                tools.extend(list(value))
        except Exception as e:
            raise ValueError(
                f"中间件 {type(middleware).__name__} 的 list_tools 失败：{e}") from e
    return tools


async def async_collect_middleware_tools(data: Any = None) -> Dict[str, Any]:
    """字典入口 + 统一信封，返回中间件贡献的工具列表。"""
    fn = "async_collect_middleware_tools"
    try:
        built = await async_get_middlewares(data)
        if built.get("code") != 200:
            return built
        tools = await collect_middleware_tools(built["data"])
        return _ok(tools, f"共收集 {len(tools)} 个中间件工具")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"中间件工具收集失败：{type(e).__name__}: {e}", fn, 500)


__all__ = [
    "async_get_middlewares",
    "async_get_memory",
    "async_collect_middleware_tools",
    "collect_middleware_tools",
]
