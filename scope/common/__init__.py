# -*- coding: utf-8 -*-
"""scope.common — 跨层基础设施。"""

from .fs import check_read_path, check_write_path, configure_fs_policy

__all__ = ["configure_fs_policy", "check_write_path", "check_read_path"]
