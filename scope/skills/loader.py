# -*- coding: utf-8 -*-
"""Skills 加载器。

支持用户/租户自定义技能目录：

    {
        "skills": {
            "enabled": True,
            "dirs": ["/data/tenants/u1/skills", "/shared/skills"],
            "ignore_missing": False,
        }
    }

也支持简写：

    "skills": ["/data/tenants/u1/skills"]
    "skills": "/data/tenants/u1/skills"

每个目录下含 ``SKILL.md`` 的子目录即一个 skill（``scan_subdir=True``）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from agentscope.skill import LocalSkillLoader, Skill

try:
    from config import get as _cfg_get
except ImportError:
    from scope.config import get as _cfg_get


def _err(message: str, fn: str) -> Dict[str, Any]:
    return {"code": 400, "data": f"{os.path.abspath(__file__)}_{fn}",
            "message": f"错误：{message}"}


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _skill_cfg(data: dict) -> dict:
    data = data or {}
    agent = data.get("agent") if isinstance(data.get("agent"), dict) else {}
    raw = agent.get("skills", data.get("skills"))
    if raw is None:
        raw = {}
    if isinstance(raw, str):
        raw = {"dirs": [raw]}
    elif isinstance(raw, list):
        raw = {"dirs": raw}
    if not isinstance(raw, dict):
        raise ValueError("skills 必须是字符串 / 列表 / 字典")
    return raw


async def build_skills(data: dict = None) -> Dict[str, Any]:
    """按配置加载 Skill 对象列表。

    返回 ``{"code":200,"data":[Skill,...]}`` 或 400。
    """
    fn = "build_skills"
    try:
        cfg = _skill_cfg(data)
        enabled = cfg.get("enabled")
        if enabled is None:
            enabled = _cfg_get("agent.skills.enabled", False)
        dirs = cfg.get("dirs")
        if dirs is None:
            dirs = _cfg_get("agent.skills.dirs", None) or []
        if isinstance(dirs, str):
            dirs = [dirs]
        if not isinstance(dirs, list):
            return _err("skills.dirs 必须是目录列表", fn)
        if not enabled and not dirs:
            return _ok([], "skills 未启用")
        if not enabled:
            return _ok([], "skills 已关闭")
        if not dirs:
            return _err("skills.enabled=True 时必须提供 skills.dirs", fn)

        ignore_missing = bool(cfg.get("ignore_missing", False))
        skills: List[Skill] = []
        loaded_dirs = []
        for path in dirs:
            p = str(path or "").strip()
            if not p:
                continue
            if not os.path.isabs(p):
                return _err(f"skills 目录必须是绝对路径: {p}", fn)
            if not os.path.isdir(p):
                if ignore_missing:
                    continue
                return _err(f"skills 目录不存在: {p}", fn)
            loader = LocalSkillLoader(directory=p, scan_subdir=True)
            try:
                skills.extend(await loader.list_skills())
                loaded_dirs.append(p)
            except Exception as e:
                return _err(f"skills 目录加载失败 {p}：{type(e).__name__}: {e}", fn)
        return _ok(skills, f"共加载 {len(skills)} 个技能")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"skills 加载失败：{type(e).__name__}: {e}", fn)


__all__ = ["build_skills"]
