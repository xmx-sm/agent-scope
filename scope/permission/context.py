# -*- coding: utf-8 -*-
"""从字典构建官方 ``PermissionContext``。

AgentScope 的权限系统由三部分组成：

- ``PermissionMode``：全局策略（default / accept_edits / explore / bypass / dont_ask）
- ``PermissionRule``：针对工具与调用的 allow / deny / ask 规则
- 工具自身的 ``check_read_only`` / ``check_permissions``：只读与危险路径检查

本文件只负责把业务侧字典翻译成官方对象，决策仍由官方
``PermissionEngine`` 执行。

支持的字典形状::

    {
        "mode": "default",
        "source": "projectSettings",
        "allow": {
            "Bash": ["npm run:*", "git status:*"],
            "async_db_tools": [null],          # null = 工具名级规则
        },
        "deny": {
            "Bash": ["rm:*"],
            "Write": ["**/.ssh/**"],
        },
        "ask": {
            "async_sys_tools": [null],
        },
        "working_directories": [
            "/data/project",
            {"path": "/data/shared", "source": "session"},
        ],
    }

同时兼容官方形状（``allow_rules`` / ``deny_rules`` / ``ask_rules``）与
逐条规则列表::

    {
        "mode": "dont_ask",
        "rules": [
            {"tool_name": "Bash", "rule_content": "git commit:*",
             "behavior": "allow", "source": "projectSettings"},
        ],
    }
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

from agentscope.permission import (
    AdditionalWorkingDirectory,
    PermissionBehavior,
    PermissionContext,
    PermissionMode,
    PermissionRule,
)

_MODE_ALIASES = {
    "default": PermissionMode.DEFAULT,
    "accept_edits": PermissionMode.ACCEPT_EDITS,
    "acceptedits": PermissionMode.ACCEPT_EDITS,
    "accept-edits": PermissionMode.ACCEPT_EDITS,
    "explore": PermissionMode.EXPLORE,
    "bypass": PermissionMode.BYPASS,
    "dont_ask": PermissionMode.DONT_ASK,
    "dontask": PermissionMode.DONT_ASK,
    "dont-ask": PermissionMode.DONT_ASK,
}

_BEHAVIOR_ALIASES = {
    "allow": PermissionBehavior.ALLOW,
    "deny": PermissionBehavior.DENY,
    "ask": PermissionBehavior.ASK,
}

_BUCKETS = (
    (PermissionBehavior.ALLOW, ("allow", "allow_rules")),
    (PermissionBehavior.DENY, ("deny", "deny_rules")),
    (PermissionBehavior.ASK, ("ask", "ask_rules")),
)


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": f"{os.path.abspath(__file__)}_{fn}",
            "message": f"错误：{message}"}


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def parse_permission_mode(value: Any) -> PermissionMode:
    """把字符串 / 枚举规范化为 PermissionMode。"""
    if isinstance(value, PermissionMode):
        return value
    if value is None:
        return PermissionMode.DEFAULT
    key = str(value).strip().lower().replace(" ", "_")
    mode = _MODE_ALIASES.get(key)
    if mode is None:
        raise ValueError(
            "permission mode 不支持: "
            f"{value}（default/accept_edits/explore/bypass/dont_ask）")
    return mode


def _parse_behavior(value: Any) -> PermissionBehavior:
    if isinstance(value, PermissionBehavior):
        return value
    key = str(value or "").strip().lower()
    behavior = _BEHAVIOR_ALIASES.get(key)
    if behavior is None:
        raise ValueError(f"permission rule behavior 不支持: {value}（allow/deny/ask）")
    return behavior


def _source(value: Any, default: str) -> str:
    text = str(value or default or "").strip()
    if not text:
        raise ValueError("permission rule source 不能为空")
    return text


def _rule_from_item(
    item: Any,
    *,
    tool_name: Optional[str],
    behavior: PermissionBehavior,
    default_source: str,
) -> PermissionRule:
    if isinstance(item, PermissionRule):
        return PermissionRule(
            tool_name=item.tool_name or tool_name or "",
            rule_content=item.rule_content,
            behavior=behavior,
            source=_source(item.source, default_source),
        )

    if item is None:
        content = None
        source = default_source
    elif isinstance(item, str):
        content = item
        source = default_source
    elif isinstance(item, dict):
        tool_name = str(item.get("tool_name") or tool_name or "").strip()
        content = item.get("rule_content")
        if content is None and "content" in item:
            content = item.get("content")
        if content is None and "pattern" in item:
            content = item.get("pattern")
        if content is not None and not isinstance(content, str):
            raise ValueError("permission rule_content 必须是字符串或 None")
        source = _source(item.get("source"), default_source)
    else:
        raise ValueError(
            "权限规则必须是字符串、None、字典或 PermissionRule，"
            f"收到 {type(item).__name__}")

    if not tool_name:
        raise ValueError("权限规则缺少 tool_name")
    return PermissionRule(
        tool_name=tool_name,
        rule_content=content,
        behavior=behavior,
        source=_source(source, default_source),
    )


def _iter_bucket_rules(
    raw: Any,
    *,
    behavior: PermissionBehavior,
    default_source: str,
) -> Iterable[PermissionRule]:
    if raw is None:
        return
    if not isinstance(raw, (dict, list)):
        raise ValueError("allow / deny / ask 必须是字典或列表")

    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict) or not item.get("tool_name"):
                raise ValueError("规则列表元素必须是带 tool_name 的字典")
            yield _rule_from_item(
                item, tool_name=None, behavior=behavior,
                default_source=default_source)
        return

    # 单条规则字典
    if "tool_name" in raw:
        yield _rule_from_item(
            raw, tool_name=None, behavior=behavior,
            default_source=default_source)
        return

    # {tool_name: spec}
    for tool_name, spec in raw.items():
        tool = str(tool_name or "").strip()
        if not tool:
            raise ValueError("权限规则的工具名不能为空")
        items = spec if isinstance(spec, list) else [spec]
        for item in items:
            yield _rule_from_item(
                item, tool_name=tool, behavior=behavior,
                default_source=default_source)


def _parse_standalone_rules(raw: Any, default_source: str) -> List[PermissionRule]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("rules 必须是列表")
    result: List[PermissionRule] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"rules[{i}] 必须是字典")
        behavior = _parse_behavior(item.get("behavior"))
        tool_name = str(item.get("tool_name") or "").strip()
        if not tool_name:
            raise ValueError(f"rules[{i}] 缺少 tool_name")
        result.append(_rule_from_item(
            item, tool_name=tool_name, behavior=behavior,
            default_source=default_source))
    return result


def _add_rule(context: PermissionContext, rule: PermissionRule) -> None:
    target = {
        PermissionBehavior.ALLOW: context.allow_rules,
        PermissionBehavior.DENY: context.deny_rules,
        PermissionBehavior.ASK: context.ask_rules,
    }[rule.behavior]
    target.setdefault(rule.tool_name, []).append(rule)


def _parse_working_directories(
    raw: Any,
    default_source: str,
) -> Dict[str, AdditionalWorkingDirectory]:
    if raw is None:
        return {}
    if not isinstance(raw, (dict, list, str)):
        raise ValueError("working_directories 必须是字典、列表或字符串")

    result: Dict[str, AdditionalWorkingDirectory] = {}

    def _add(path: Any, source: Any = None) -> None:
        text = str(path or "").strip()
        if not text:
            raise ValueError("working_directories 的路径不能为空")
        if not os.path.isabs(text):
            raise ValueError(f"working_directories 必须是绝对路径: {text}")
        result[text] = AdditionalWorkingDirectory(
            path=text,
            source=_source(source, default_source),
        )

    if isinstance(raw, str):
        _add(raw)
        return result
    if isinstance(raw, list):
        for i, item in enumerate(raw):
            if isinstance(item, str):
                _add(item)
            elif isinstance(item, dict):
                _add(item.get("path"), item.get("source"))
            else:
                raise ValueError(
                    f"working_directories[{i}] 必须是字符串或字典")
        return result

    for path, item in raw.items():
        if isinstance(item, AdditionalWorkingDirectory):
            _add(item.path or path, item.source)
        elif isinstance(item, dict):
            _add(item.get("path") or path, item.get("source"))
        elif isinstance(item, str):
            _add(path, item)
        else:
            raise ValueError(f"working_directories[{path}] 配置非法")
    return result


def build_permission_context(data: Any = None) -> PermissionContext:
    """把字典、官方对象或 None 转成 PermissionContext。

    非字典输入若不是 PermissionContext，会抛 ``ValueError``，
    由上层统一转成 400 信封。
    """
    if data is None:
        return PermissionContext()
    if isinstance(data, PermissionContext):
        return data
    if not isinstance(data, dict):
        raise ValueError(
            "permission_context 必须是字典或 PermissionContext，"
            f"收到 {type(data).__name__}")

    default_source = _source(
        data.get("source") or data.get("rule_source"),
        "projectSettings",
    )
    context = PermissionContext(
        mode=parse_permission_mode(data.get("mode") or data.get("permission_mode")),
        working_directories=_parse_working_directories(
            data.get("working_directories") or data.get("working_dirs"),
            default_source,
        ),
    )

    for behavior, keys in _BUCKETS:
        for key in keys:
            if key in data:
                for rule in _iter_bucket_rules(
                        data.get(key), behavior=behavior,
                        default_source=default_source):
                    _add_rule(context, rule)

    for rule in _parse_standalone_rules(data.get("rules"), default_source):
        _add_rule(context, rule)

    return context


def permission_context_to_dict(context: PermissionContext) -> Dict[str, Any]:
    """转成可 JSON 序列化的友好字典，供 UI / API 返回。"""
    if not isinstance(context, PermissionContext):
        raise ValueError("context 必须是 PermissionContext")

    def _rules(bucket: Dict[str, List[PermissionRule]]) -> Dict[str, list]:
        return {
            tool: [
                {
                    "tool_name": rule.tool_name,
                    "rule_content": rule.rule_content,
                    "source": rule.source,
                }
                for rule in rules
            ]
            for tool, rules in bucket.items()
        }

    return {
        "mode": context.mode.value,
        "allow": _rules(context.allow_rules),
        "deny": _rules(context.deny_rules),
        "ask": _rules(context.ask_rules),
        "working_directories": [
            {"path": item.path, "source": item.source}
            for item in context.working_directories.values()
        ],
    }


def set_permission_mode(context: PermissionContext, mode: Any) -> PermissionMode:
    """运行时切换权限模式，返回切换后的枚举。"""
    if not isinstance(context, PermissionContext):
        raise ValueError("context 必须是 PermissionContext")
    parsed = parse_permission_mode(mode)
    context.mode = parsed
    return parsed


def add_permission_rule(context: PermissionContext, rule: Any) -> PermissionRule:
    """向现有上下文追加一条规则，返回规范化后的 PermissionRule。"""
    if not isinstance(context, PermissionContext):
        raise ValueError("context 必须是 PermissionContext")
    if isinstance(rule, PermissionRule):
        parsed = rule
    elif isinstance(rule, dict):
        behavior = _parse_behavior(rule.get("behavior"))
        parsed = _rule_from_item(
            rule,
            tool_name=rule.get("tool_name"),
            behavior=behavior,
            default_source=str(rule.get("source") or "projectSettings"),
        )
    else:
        raise ValueError("rule 必须是 PermissionRule 或字典")
    _add_rule(context, parsed)
    return parsed


def merge_permission_context(
    base: PermissionContext,
    extra: Any,
) -> PermissionContext:
    """把另一份字典 / 上下文中的规则与工作目录合并到 base。"""
    if not isinstance(base, PermissionContext):
        raise ValueError("base 必须是 PermissionContext")
    other = build_permission_context(extra)
    for behavior, bucket in (
        (PermissionBehavior.ALLOW, base.allow_rules),
        (PermissionBehavior.DENY, base.deny_rules),
        (PermissionBehavior.ASK, base.ask_rules),
    ):
        source = {
            PermissionBehavior.ALLOW: other.allow_rules,
            PermissionBehavior.DENY: other.deny_rules,
            PermissionBehavior.ASK: other.ask_rules,
        }[behavior]
        for tool_name, rules in source.items():
            bucket.setdefault(tool_name, []).extend(rules)
    base.working_directories.update(other.working_directories)
    return base


async def async_build_permission_context(data: Any = None) -> PermissionContext:
    """异步构建权限上下文；可选从 SQLite 合并持久化规则。

    字典中带 ``sqlite`` 时::

        {
            "mode": "default",
            "allow": {"Bash": ["git status:*"]},   # 内联规则
            "sqlite": {
                "path": "/data/permission.db",
                "create_dir": True,
                "tenant_id": "u1",
                "agent_id": "a1",
            },
        }

    数据库中的规则会合并到内联规则之后，工作目录只取内联配置。
    """
    if not isinstance(data, dict):
        return build_permission_context(data)

    store_cfg = data.get("sqlite") or data.get("store")
    if store_cfg is None:
        return build_permission_context(data)

    if isinstance(store_cfg, str):
        store_cfg = {"path": store_cfg}
    if not isinstance(store_cfg, dict):
        raise ValueError("permission_context.sqlite 必须是字典或路径")

    from .store import PermissionStore

    store = PermissionStore(
        store_cfg.get("path"),
        create_dir=bool(store_cfg.get("create_dir", False)),
    )
    await store.initialize()
    base = build_permission_context({
        key: value for key, value in data.items()
        if key not in ("sqlite", "store")
    })
    return await store.load_context(
        str(store_cfg.get("tenant_id") or data.get("tenant_id") or ""),
        str(store_cfg.get("agent_id") or data.get("agent_id") or ""),
        base,
    )


async def async_get_permission_context(data: dict = None) -> Dict[str, Any]:
    """构建权限上下文的字典入口，返回统一信封。"""
    fn = "async_get_permission_context"
    try:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return _err(f"data 必须是字典对象，收到 {type(data).__name__}", fn)
        raw = data.get("permission_context", data)
        context = await async_build_permission_context(raw)
        return _ok({
            "permission_context": context,
            "config": permission_context_to_dict(context),
        }, "PermissionContext 创建成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(
            f"权限上下文创建失败：{type(e).__name__}: {e}", fn, 500)


__all__ = [
    "build_permission_context",
    "permission_context_to_dict",
    "parse_permission_mode",
    "set_permission_mode",
    "add_permission_rule",
    "merge_permission_context",
    "async_build_permission_context",
    "async_get_permission_context",
]
