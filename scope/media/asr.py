# -*- coding: utf-8 -*-
"""ASR 服务：音频文件 → 文本。

输入可以是：

- ``audio_path``：本地音频路径（会过读取闸门）
- ``audio_bytes``：内存中的音频字节
- ``audio_base64``：base64 音频

可选 ``save_text_path`` 把转写文本落盘（同样过写入闸门）。ASR 本身不生成
音频文件，只产生文本。
"""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional, Tuple

from agentscope.message import TextBlock

from .fs import check_read_path, check_write_path
from .tts import _write_atomic

try:  # scope.media 包导入
    from ..llm.agent_model import async_get_asr_model
except ImportError:  # 顶层 media 导入（scope/ 在 sys.path）
    from llm.agent_model import async_get_asr_model


def _err(message: str, fn: str = "async_transcribe_asr", code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": f"{os.path.abspath(__file__)}_{fn}",
            "message": f"错误：{message}"}


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _read_audio(data: dict, max_bytes: int) -> Tuple[bytes, str]:
    """返回 (audio_bytes, filename)。audio_path / audio_bytes / audio_base64 三选一。"""
    audio_path = data.get("audio_path")
    audio_bytes = data.get("audio_bytes")
    audio_b64 = data.get("audio_base64")

    provided = int(bool(audio_path)) + int(audio_bytes is not None) + int(bool(audio_b64))
    if provided > 1:
        raise ValueError("audio_path / audio_bytes / audio_base64 只能三选一")

    if audio_path:
        allowed, reason = check_read_path(audio_path)
        if not allowed:
            raise ValueError(f"读取路径被拒：{reason}")
        if not os.path.isfile(audio_path):
            raise ValueError(f"音频文件不存在：{audio_path}")
        if os.path.getsize(audio_path) > max_bytes:
            raise ValueError(f"音频超过大小上限 {max_bytes} 字节")
        with open(audio_path, "rb") as f:
            return f.read(), os.path.basename(audio_path)

    if audio_bytes is not None:
        if not isinstance(audio_bytes, (bytes, bytearray)):
            raise TypeError("audio_bytes 必须是 bytes")
        if len(audio_bytes) > max_bytes:
            raise ValueError(f"音频超过大小上限 {max_bytes} 字节")
        return bytes(audio_bytes), str(data.get("filename") or "audio.wav")

    if audio_b64:
        try:
            raw = base64.b64decode(audio_b64, validate=True)
        except (TypeError, ValueError) as e:
            raise ValueError(f"audio_base64 解码失败：{e}") from e
        if len(raw) > max_bytes:
            raise ValueError(f"音频超过大小上限 {max_bytes} 字节")
        return raw, str(data.get("filename") or "audio.wav")

    raise ValueError("缺少音频输入：audio_path / audio_bytes / audio_base64 三选一")


async def async_transcribe_asr(data: dict = None) -> Dict[str, Any]:
    """把音频转写为文本。

    入参（data 字典）:
        asr_model(对象, 可选)       已构造的 ASR 模型
        asr(dict, 条件必填)         模型配置，见 async_get_asr_model
        audio_path(str, 三选一)     本地音频路径
        audio_bytes(bytes, 三选一)  音频字节
        audio_base64(str, 三选一)   base64 音频
        filename(str, 可选)         内存音频的文件名（决定 multipart 格式），默认 audio.wav
        max_bytes(int, 默认 50MB)
        save_text_path(str, 可选)   转写文本落盘路径（绝对路径）
        overwrite(bool, 默认 False)

    返回:
        {"code":200, "data":{"text", "filename", "bytes", "text_path"?}, "message":"转写成功"}
        或 400/500 错误信封。
    """
    fn = "async_transcribe_asr"
    try:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return _err(f"data 必须是字典对象，收到 {type(data).__name__}", fn)

        max_bytes = int(data.get("max_bytes") or 50 * 1024 * 1024)
        try:
            payload, filename = _read_audio(data, max_bytes)
        except (TypeError, ValueError) as e:
            return _err(str(e), fn)

        save_text_path = data.get("save_text_path")
        if save_text_path:
            allowed, reason = check_write_path(save_text_path)
            if not allowed:
                return _err(f"转写文本保存路径被拒：{reason}", fn)
            if os.path.exists(save_text_path) and not bool(data.get("overwrite", False)):
                return _err(f"文件已存在（如需覆盖请传 overwrite=True）：{save_text_path}", fn)

        model = data.get("asr_model")
        if model is None:
            cfg = data.get("asr")
            if not isinstance(cfg, dict) or not cfg:
                return _err("缺少 asr 配置（或传入已构造的 asr_model）", fn)
            r = await async_get_asr_model({"asr": cfg})
            if r.get("code") != 200:
                return r
            model = r["data"]

        resp = await model.transcribe(audio=payload, filename=filename)
        content = getattr(resp, "content", None)
        text = content.text if isinstance(content, TextBlock) else (
            getattr(content, "text", None) if content is not None else None)
        if text is None:
            return _err("ASR 未返回文本", fn, code=500)

        out: Dict[str, Any] = {
            "text": text,
            "filename": filename,
            "bytes": len(payload),
        }
        if save_text_path:
            try:
                _write_atomic(str(save_text_path), text.encode("utf-8"))
            except OSError as e:
                return _err(f"写入转写文本失败：{type(e).__name__}: {e}", fn, code=500)
            out["text_path"] = os.path.abspath(str(save_text_path))

        return _ok(out, "转写成功")
    except (TypeError, ValueError, RuntimeError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"转写失败：{type(e).__name__}: {e}", fn, code=500)


__all__ = ["async_transcribe_asr"]
