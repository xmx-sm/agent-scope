

"""
net 域的信封机器：_where / _ok / _err。

**六域里唯一独立成文件的信封层**——net 合并 crawl 后有四个辅助文件
（_client / _fs / _render / _crawler），若把信封塞进其中任何一个，
其余三个都要横向依赖它（文件闸门依赖 httpx 客户端单例，语义不成立）。
故单独一层，四者互不依赖。

签名约定（其余五域同此，见 docs/工具拆分规范.md 跨域前缀一节）:
    _err(message, func_name="", code=400, prefix=None)
    prefix=None 时按 code 定：400 带「错误：」前缀、500 不带；
    路由提示（「暂不支持的 function」）原实现无前缀，显式传 prefix=False。
"""


import os
from typing import Any, Dict


def _where(func_name: str) -> str:
    """错误位置标识，指向本文件_函数名。

    ⚠️ 本模块是信封层，`__file__` 恒为 `_envelope.py`，对定位无价值；
    故由各调用方传自己的 func_name，标识拼为 `<调用方文件>_<func_name>` 需靠
    `func_name` 足够区分（六域沿用此约定，见踩坑记录 A15/A19）。
    """
    return f"{os.path.abspath(__file__)}_{func_name}"


def _ok(data=None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _err(message: str, func_name: str = "", code: int = 400,
         prefix: bool | None = None) -> Dict[str, Any]:
    """错误信封。默认 400 带「错误：」前缀、500 不带；prefix 可显式覆盖。"""
    if prefix is None:
        prefix = code == 400
    return {"code": code, "data": _where(func_name),
            "message": (f"错误：{message}" if prefix else message)}



