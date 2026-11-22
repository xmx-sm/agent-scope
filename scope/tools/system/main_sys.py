

"""
system 工具统一入口与 function 路由。

原 async_sys_tools.py 拆分而来：本文件只保留调度，功能与辅助各归其模块。
新增功能：写一个 <function>.py，并在本文件路由里加一个 if function == "..." 分支。

模块布局:
    main_sys.py    本文件，async_sys_tools 入口与路由
    _common.py     subprocess 可选参数归一化（多功能共用的无状态辅助）
    cmd_run.py     function="cmd_run" 执行 Shell 命令（高风险，需人工审批）
"""


import asyncio
from typing import Dict, Any

from ._common import _err

from .cmd_run import async_cmd_run



async def async_sys_tools(data: dict) -> Dict[str, Any]:
    """
    系统工具统一入口（异步）。data["function"] 决定执行哪个功能，其余字段为该功能的业务参数。

    参数 (data 字典):
        data: {"function": 要执行的功能名称, # 必填
               ...功能业务参数见下方各功能说明}

    支持的功能与业务参数:
        ① function="cmd_run" — 在服务器终端执行 Shell 命令（高风险工具，执行前需人工审批）
            业务参数: command(str, 必填) 需要执行的命令字符串，如 "ls -la"
                     timeout(int/float, 可选) 超时秒数，默认 30
                     shell(bool, 可选) 默认 True | capture_output(bool, 可选) 默认 True
                     text(bool, 可选) 默认 True | encoding(str, 可选) 默认 "utf-8"
                     errors(str, 可选) 默认 "ignore"
            返回: {"code":200, "data": {"stdout":..., "stderr":..., "return_code":..., "os_type":...}, "message":"success"}

    调用示例:
        async_sys_tools({"function":"cmd_run", "command":"pwd"})

    返回:
        {"code": 200, "data": ..., "message": "success"}
        或 {"code": 400/500, "data": 文件位置, "message": 错误描述}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_sys_tools")
    raw_fn = data.get("function", "")
    if isinstance(raw_fn, (dict, list, tuple, set)):
        return _err(f"function 必须是字符串，收到 {type(raw_fn).__name__}", "async_sys_tools")
    function = str(raw_fn or "").strip()
    if not function:
        return _err("data 中缺少 function 字段", "async_sys_tools")
    if function == "cmd_run":
        return await async_cmd_run(data)
    return _err(f"暂不支持的 function: {function}，支持: cmd_run ", "async_sys_tools",
                prefix=False)



if __name__ == "__main__":
    # 系统工具测试：执行命令 + 参数校验
    import asyncio

    async def main():
        print("== cmd_run ==")
        print(await async_sys_tools({"function": "cmd_run", "command": "pwd && echo done"}))
        print("== 自定义参数 ==")
        print(await async_sys_tools({"function": "cmd_run", "command": "echo hi", "timeout": 10, "encoding": "utf-8"}))
        print("== output_limit 截断 ==")
        long_cmd = "for i in $(seq 1 50); do echo 'line number '$i; done"
        print("head:", await async_sys_tools({"function": "cmd_run", "command": long_cmd, "output_limit": 60, "output_part": "head"}))
        print("tail:", await async_sys_tools({"function": "cmd_run", "command": long_cmd, "output_limit": 60, "output_part": "tail"}))
        print("middle:", await async_sys_tools({"function": "cmd_run", "command": long_cmd, "output_limit": 60, "output_part": "middle"}))
        print("== output_limit 校验 ==")
        print(await async_sys_tools({"function": "cmd_run", "command": "echo x", "output_limit": "abc"}))
        print(await async_sys_tools({"function": "cmd_run", "command": "echo x", "output_part": "bad"}))
        print("== 参数校验 ==")
        print(await async_sys_tools({"function": "cmd_run"}))
        print(await async_sys_tools({"function": "cmd_run", "command": "echo x", "timeout": "abc"}))
        print(await async_sys_tools({"function": "cmd_run", "command": "echo x", "shell": "notbool"}))
        print(await async_sys_tools({"function": "bad"}))

    asyncio.run(main())
