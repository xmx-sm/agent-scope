# -*- coding: utf-8 -*-
"""视频输入 formatter（补齐 agentscope 2.0.12 未覆盖的 OpenAI 兼容端点）。

背景（2.0.12 实测）:
- DashScopeChatFormatter 原生支持 video/*，并把 DataBlock.model_extra（如 fps/snippet）
  合并到 video_url 内容项顶层；
- OpenAIChatFormatter 只放行 text/image/audio/pdf，video/* 会被 warn + 跳过；
- GeminiChatFormatter 原生支持 video/*。

本模块只做两件事:
1. OpenAIVideoChatFormatter：让 openai-chat / openai-compatible 也能发 video_url；
2. DashScopeVideoChatFormatter：给 DashScope 视频块补一个全局默认 fps
   （逐块 fps 仍以 DataBlock.model_extra 优先）。

视频块格式严格使用::

    {"type": "video_url", "video_url": {"url": "<URL 或 data:video/mp4;base64,...>"}}

不要使用 {"type": "video"}（部分兼容端点报 400/1214），也不要把视频塞进
image_url（报 400/1210）。
"""

from __future__ import annotations

import base64
from fnmatch import fnmatch
from typing import Any, Optional
from urllib.request import url2pathname

from pydantic import Field

from agentscope.formatter import DashScopeChatFormatter, OpenAIChatFormatter
from agentscope.message import Base64Source, DataBlock, URLSource


def _source_to_url(source: URLSource | Base64Source) -> str:
    """把视频源转成 URL 或 data URI。

    - Base64Source -> ``data:<media_type>;base64,<data>``
    - URLSource（file://）-> 读本地文件并转 base64
    - URLSource（http/https 等）-> 原样透传，是否可达由服务端决定
    """
    if isinstance(source, Base64Source):
        return f"data:{source.media_type};base64,{source.data}"
    if isinstance(source, URLSource):
        url_str = str(source.url)
        if url_str.startswith("file://"):
            local_path = url2pathname(url_str.removeprefix("file://"))
            with open(local_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
            return f"data:{source.media_type};base64,{encoded}"
        return url_str
    raise ValueError(f"不支持的视频源类型: {type(source).__name__}")


class OpenAIVideoChatFormatter(OpenAIChatFormatter):
    """OpenAI Chat Completions 兼容端点的视频增强 formatter。

    仅在 model factory 的 ``video_support=True`` 且 provider 为
    ``openai-chat`` / ``openai-compatible`` 时启用；其他厂商不一定认识
    ``video_url`` 块。
    """

    input_types: list[str] = Field(
        default_factory=lambda: [
            "text/plain",
            "image/*",
            "audio/*",
            "video/*",
            "application/pdf",
        ],
        description="在基类四类之上追加 video/*。",
    )

    video_fps: Optional[float] = Field(
        default=None,
        description=(
            "抽帧率，附加到 video_url 内容项顶层的 \"fps\" 字段；"
            "None=不注入。仅服务端明确支持时配置。"
        ),
    )

    def _format_video_source(
        self,
        source: URLSource | Base64Source,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        block: dict[str, Any] = {
            "type": "video_url",
            "video_url": {"url": _source_to_url(source)},
        }
        if extra:
            block.update(extra)
        if self.video_fps is not None and "fps" not in block:
            block["fps"] = float(self.video_fps)
        return block

    def _format_openai_data_block(self, block: DataBlock) -> dict[str, Any] | None:
        media_type = block.source.media_type
        if media_type.split("/")[0] == "video" and any(
            fnmatch(media_type, pattern)
            for pattern in self.supported_input_media_types
        ):
            return self._format_video_source(block.source, block.model_extra)
        return super()._format_openai_data_block(block)


class DashScopeVideoChatFormatter(DashScopeChatFormatter):
    """DashScope formatter 的视频默认 fps 增强。

    DashScope 2.0.12 已原生支持视频；本类只负责在 DataBlock 未显式提供
    ``fps`` 时补一个全局默认值，未配置时行为与基类完全一致。
    """

    video_fps: Optional[float] = Field(
        default=None,
        description="视频块默认抽帧率；逐块 DataBlock.model_extra.fps 优先。",
    )

    def _format_video_source(
        self,
        source: URLSource | Base64Source,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged = dict(extra or {})
        if self.video_fps is not None:
            merged.setdefault("fps", float(self.video_fps))
        return DashScopeChatFormatter._format_video_source(source, merged)


__all__ = ["OpenAIVideoChatFormatter", "DashScopeVideoChatFormatter"]
