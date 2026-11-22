# -*- coding: utf-8 -*-
"""`data > sqlite > None` 的合并辅助。

为什么需要它：现有各域用 `a or b or c` 链取默认值，但 `or` 对 falsy 的处理
在不同字段上语义**相反**——

    verify=False / max_size=0 / shell=False / save_attachments=False
        → 是**有效值**，不能被 or 吞成"未传"（否则关不掉校验、0 变默认）
    host="" / user="" / 未传的可选字段
        → 是"未传"，应继续往 sqlite 找，找不到给空串让原校验报错

故拆成两个函数，各域按字段语义选用，不能一刀切。
"""

from typing import Any

from .store import get as _get


def pick(passed: Any, key: str, default: Any = None) -> Any:
    """标量/布尔字段：调用传入（非 None）> sqlite > default。

    **0 / False / 空列表都算有效传入**，不被跳过。适用于 verify、shell、
    save_attachments、max_size、output_limit、count、offset 等有"零/假"语义的字段。

    passed 为 None 表示"调用方没给这个字段"，才去 sqlite 取。
    """
    if passed is not None:
        return passed
    v = _get(key, None)
    return default if v is None else v


def pick_str(passed: Any, key: str, default: str = "") -> str:
    """字符串字段：传入非空串 > sqlite 非空 > default。

    空串/纯空白视为"未传"，继续往 sqlite 找。适用于 host、encoding、
    output_part、mailbox、db_type 等——空 host 必须落到 default（通常是 ""），
    好让下游 check_email_config / _resolve 按原逻辑报"缺少 xxx"，
    而不是把 None 变成字符串 "None"。

    default 缺省 ""（而非 None）：保证返回恒为 str，避免 str(None)=="None" 陷阱。
    """
    if passed is not None and str(passed).strip():
        return str(passed)
    v = _get(key, None)
    if v is not None and str(v).strip():
        return str(v)
    return default


def pick_int(passed: Any, key: str, default: Any = None) -> Any:
    """整数字段：传入非 None 且能转 int > sqlite > default。0 算有效传入。

    传入是空串/None → 去 sqlite；sqlite 也没有 → 返回 default（可以是 None，
    由调用方决定报错还是回落）。转换失败（如 "abc"）不吞，交给调用方的原校验，
    这里只在传入本身是坏类型时返回 passed 原值让下游报错。
    """
    if passed is not None and passed != "":
        return passed                       # 原样交回，坏类型由下游 int() 校验报错
    v = _get(key, None)
    return default if v is None else v
