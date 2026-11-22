# -*- coding: utf-8 -*-
"""媒体层文件闸门（兼容入口）。

实现已上移到 ``scope/common/fs.py``，媒体与 RAG 共用同一套策略。
本文件保留原导入路径，避免已有调用方改代码。
"""

try:  # scope.media 包导入
    from ..common.fs import (  # noqa: F401
        check_read_path,
        check_write_path,
        configure_fs_policy,
    )
except ImportError:  # 顶层 media 导入（scope/ 在 sys.path）
    from common.fs import (  # noqa: F401
        check_read_path,
        check_write_path,
        configure_fs_policy,
    )

__all__ = ["configure_fs_policy", "check_write_path", "check_read_path"]
