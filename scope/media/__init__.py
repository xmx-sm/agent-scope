# -*- coding: utf-8 -*-
"""scope.media — 生成类模型的 I/O 服务。

- 模型构造：``scope.llm.agent_model``
- 本层：字典入参、输出位置校验、流式拼接、原子落盘、读取闸门

公共入口::

    from scope.media import async_generate_tts, async_transcribe_asr
    from scope.media.fs import configure_fs_policy
"""

from .asr import async_transcribe_asr
from .fs import check_read_path, check_write_path, configure_fs_policy
from .tts import async_generate_tts

__all__ = [
    "async_generate_tts",
    "async_transcribe_asr",
    "configure_fs_policy",
    "check_write_path",
    "check_read_path",
]
