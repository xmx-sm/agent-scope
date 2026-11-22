# -*- coding: utf-8 -*-
"""TTS 生成服务：文本 → 音频 → 落盘 / base64 / URL。

与模型工厂的分工：

- ``llm.agent_model.async_get_tts_model``：只构造可复用的 TTS 模型对象；
- 本文件：字典入参、输出位置校验、流式拼接、原子落盘。

统一信封 ``{"code": 200|400|500, "data": ..., "message": ...}``。

示例::

    r = await async_generate_tts({
        "tts": {"provider": "dashscope", "model": "qwen3-tts-flash",
                "api_key": "...", "parameters": {"voice": "Cherry"}},
        "text": "你好",
        "output_mode": "file",
        "save_path": "/data/audio/hello.mp3",
    })
    # data = {"path": "/data/audio/hello.mp3", "bytes": N, "media_type": "audio/mpeg"}

    r = await async_generate_tts({
        "tts_model": tts,                 # 也可复用已构造的模型
        "text": "你好",
        "output_mode": "base64",
    })
"""

from __future__ import annotations

import base64
import inspect
import io
import os
import re
import tempfile
import wave
from typing import Any, Dict, Optional, Tuple

from agentscope.message import Base64Source, URLSource

from .fs import check_write_path

try:  # scope.media 包导入
    from ..llm.agent_model import async_get_tts_model
except ImportError:  # 顶层 media 导入（scope/ 在 sys.path）
    from llm.agent_model import async_get_tts_model


def _err(message: str, fn: str = "async_generate_tts", code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": f"{os.path.abspath(__file__)}_{fn}",
            "message": f"错误：{message}"}


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _media_type(source: Any) -> str:
    return str(getattr(source, "media_type", "") or "")


def _pcm_to_wav(pcm: bytes, media_type: str) -> Tuple[bytes, str]:
    """把 audio/pcm 裸流补成 WAV；从 media_type 解析 rate/channels。"""
    rate = 24000
    channels = 1
    m = re.search(r"rate=(\d+)", media_type)
    if m:
        rate = int(m.group(1))
    m = re.search(r"channels=(\d+)", media_type)
    if m:
        channels = int(m.group(1))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)      # 16-bit PCM
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue(), "audio/wav"


async def _collect_audio(tts: Any, text: str) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
    """执行 synthesize 并收集音频。

    返回 (bytes, media_type, url)。流式时把各 chunk 的 base64 增量拼起来；
    若厂商返回 URL，则 bytes 为 None、url 有值。
    """
    result = await tts.synthesize(text)
    responses = []
    if inspect.isasyncgen(result):
        async for item in result:
            responses.append(item)
    else:
        responses.append(result)

    chunks: list[bytes] = []
    urls: list[str] = []
    media_type: Optional[str] = None
    for resp in responses:
        content = getattr(resp, "content", None)
        if content is None:
            continue
        source = getattr(content, "source", None)
        if source is None:
            continue
        media_type = media_type or _media_type(source)
        if isinstance(source, Base64Source):
            try:
                chunks.append(base64.b64decode(source.data))
            except (TypeError, ValueError) as e:
                raise ValueError(f"TTS 返回的 base64 音频无法解码：{e}") from e
        elif isinstance(source, URLSource):
            urls.append(str(source.url))

    if chunks:
        return b"".join(chunks), media_type or "audio/mpeg", None
    if urls:
        return None, media_type or "audio/mpeg", urls[-1]
    raise ValueError("TTS 未返回音频数据（content 为空）")


async def _download(url: str, max_bytes: int = 50 * 1024 * 1024) -> Tuple[bytes, str]:
    try:
        import httpx
    except ImportError as e:
        raise RuntimeError("下载 TTS 音频需要 httpx（pip install httpx）") from e
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            media_type = resp.headers.get("content-type", "application/octet-stream").split(";")[0]
            total = 0
            parts = []
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"音频超过大小上限 {max_bytes} 字节")
                parts.append(chunk)
    return b"".join(parts), media_type


def _write_atomic(path: str, payload: bytes) -> None:
    parent = os.path.dirname(path) or os.getcwd()
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tts-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


async def async_generate_tts(data: dict = None) -> Dict[str, Any]:
    """生成语音并按指定方式输出。

    入参（data 字典）:
        tts_model(对象, 可选)       已构造的 TTS 模型；给了就不再调用模型工厂
        tts(dict, 条件必填)         模型配置（tts_model 未给时），见 async_get_tts_model
        text(str, 必填)             要合成的文本
        output_mode(str, 默认 file) file / base64 / url
        save_path(str, 条件必填)    output_mode=file 时必填；必须是绝对路径
        overwrite(bool, 默认 False) 文件已存在时是否覆盖
        max_bytes(int, 默认 50MB)   URL 下载大小上限

    返回:
        file:   {"path", "bytes", "media_type"}
        base64: {"base64", "bytes", "media_type"}
        url:    {"url", "media_type"}
        或 400/500 错误信封。
    """
    fn = "async_generate_tts"
    try:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return _err(f"data 必须是字典对象，收到 {type(data).__name__}", fn)

        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            return _err("缺少参数 text（要合成的文本）", fn)

        output_mode = str(data.get("output_mode") or "file").strip().lower()
        if output_mode not in ("file", "base64", "url"):
            return _err(f"不支持的 output_mode: {output_mode}（file/base64/url）", fn)

        save_path = data.get("save_path")
        if output_mode == "file":
            if not save_path:
                return _err("缺少参数 save_path（输出文件路径）", fn)
            allowed, reason = check_write_path(save_path)
            if not allowed:
                return _err(f"保存路径被拒：{reason}", fn)
            if os.path.isdir(save_path):
                return _err(f"save_path 是目录，不是文件：{save_path}", fn)
            if os.path.exists(save_path) and not bool(data.get("overwrite", False)):
                return _err(f"文件已存在（如需覆盖请传 overwrite=True）：{save_path}", fn)

        tts = data.get("tts_model")
        if tts is None:
            tts_cfg = data.get("tts")
            if not isinstance(tts_cfg, dict) or not tts_cfg:
                return _err("缺少 tts 配置（或传入已构造的 tts_model）", fn)
            r = await async_get_tts_model({"tts": tts_cfg})
            if r.get("code") != 200:
                return r
            tts = r["data"]

        payload, media_type, url = await _collect_audio(tts, text)

        if output_mode == "url":
            if url:
                return _ok({"url": url, "media_type": media_type}, "语音生成成功")
            return _err("该 provider 返回的是音频字节，不提供 url；请用 file 或 base64", fn)

        if payload is None and url:
            payload, downloaded_type = await _download(
                url, int(data.get("max_bytes") or 50 * 1024 * 1024))
            media_type = downloaded_type or media_type

        if payload is None:
            return _err("TTS 未返回可用音频", fn, code=500)

        if (media_type or "").startswith("audio/pcm"):
            if output_mode == "file" and not str(save_path).lower().endswith(".wav"):
                return _err("PCM 音频请保存为 .wav 文件（或改用支持 mp3 的模型）", fn)
            payload, media_type = _pcm_to_wav(payload, media_type or "audio/pcm;rate=24000")

        if output_mode == "base64":
            return _ok({
                "base64": base64.b64encode(payload).decode("ascii"),
                "bytes": len(payload),
                "media_type": media_type or "audio/mpeg",
            }, "语音生成成功")

        try:
            _write_atomic(str(save_path), payload)
        except OSError as e:
            return _err(f"写入文件失败：{type(e).__name__}: {e}", fn, code=500)

        return _ok({
            "path": os.path.abspath(str(save_path)),
            "bytes": len(payload),
            "media_type": media_type or "audio/mpeg",
        }, "语音生成成功")
    except (TypeError, ValueError, RuntimeError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"语音生成失败：{type(e).__name__}: {e}", fn, code=500)


__all__ = ["async_generate_tts"]
