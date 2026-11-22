

"""
function="cmd_run" — 在服务器终端执行 Shell 命令。

asyncio.create_subprocess 原生异步子进程（不占线程池），自动适配 Linux/macOS/Windows；
超时后仍返回已收集的部分输出；输出按 output_limit/output_part 精确截断。
高风险工具，调用前应经权限闸门人工审批。
"""


import asyncio
import platform
from typing import Dict, Any

from ._common import _err, _ok, get_common_args



async def async_cmd_run(data: dict) -> Dict[str, Any]:
    """
    在服务器终端执行 Shell 命令（异步，asyncio.create_subprocess 原生异步子进程）。
    （高风险工具，执行前需人工审批）。

    自动适配当前操作系统（Linux/macOS/Windows），30 秒超时保护。
    该工具被标记为敏感工具，LLM 调用时会触发 human_review 审批节点。

    非流式：等命令执行完成后一次返回完整 stdout/stderr，返回格式干净、可精确截断。
    长命令（构建/批量）超时后也会返回已收集的部分输出，不会白等。

    参数 (data 字典):
        data: {command: 需要执行的命令字符串,
               timeout(int/float, 可选, 默认30) 执行总超时秒数,
               shell(bool, 可选, 默认True) 是否用 shell 执行,
               capture_output(bool, 可选, 默认True) 是否捕获输出,
               text(bool, 可选, 默认True) 以文本模式返回,
               encoding(str, 可选, 默认"utf-8") 输出编码,
               errors(str, 可选, 默认"ignore") 编码错误处理,
               output_limit(int, 可选, 默认0) 返回 stdout 最大字符数，0=不限制,
               output_part(str, 可选, 默认"tail") 超限时保留哪部分:
                   "head"   保留开头 output_limit 字符
                   "tail"   保留结尾 output_limit 字符（构建/错误结果常在末尾）
                   "middle" 保留开头+结尾各一半，中间省略}

    返回:
        {"code": 200, "data": {"stdout": ..., "stderr": ..., "return_code": ...,
                               "os_type": ..., "truncated": bool, "skipped": int,
                               "timed_out": bool}, "message": "success"}
        或 {"code": 400/500, "data": 文件位置, "message": 错误描述}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "cmd_run")
    command = data.get("command", "")
    if command is None or (isinstance(command, str) and not command.strip()):
        return _err("data 中缺少 command 字段", "cmd_run")
    if isinstance(command, (dict, list, tuple, set)):
        return _err(f"command 必须是字符串，收到 {type(command).__name__}", "cmd_run")
    command = str(command or "")
    if not command.strip():
        return _err("data 中缺少 command 字段", "cmd_run")
    args_r = get_common_args({"data": data, "func_name": "cmd_run"})
    if args_r.get("code") != 200:
        return args_r
    raw_limit = data.get("output_limit", 0)
    if raw_limit in (None, ""):
        raw_limit = 0
    if isinstance(raw_limit, (dict, list, tuple, set)):
        return _err(f"output_limit 必须是整数，收到 {type(raw_limit).__name__}", "cmd_run")
    try:
        output_limit = int(raw_limit)
    except (TypeError, ValueError):
        return _err("output_limit 必须是整数", "cmd_run")
    if output_limit < 0:
        output_limit = 0
    raw_part = data.get("output_part", "tail")
    if isinstance(raw_part, (dict, list, tuple, set)):
        return _err(f"output_part 必须是字符串，收到 {type(raw_part).__name__}", "cmd_run")
    output_part = str(raw_part or "tail").strip().lower()
    if output_part not in ("head", "tail", "middle"):
        return _err("output_part 仅支持 head / tail / middle", "cmd_run")

    try:
        # system_name: str — 当前操作系统类型，用于适配不同的 shell 环境
        system_name = platform.system()
        # common_args: dict — 统一的参数配置（已由 get_common_args 校验）
        common_args = args_r["data"]["value"]
        timeout = float(common_args.get("timeout", 30) or 30)
        shell = bool(common_args.get("shell", True))
        capture = bool(common_args.get("capture_output", True))
        text = bool(common_args.get("text", True))
        encoding = str(common_args.get("encoding", "utf-8") or "utf-8")
        errors = str(common_args.get("errors", "ignore") or "ignore")

        # 子进程参数：按需捕获 stdout/stderr
        kwargs = {}
        if capture:
            kwargs["stdout"] = asyncio.subprocess.PIPE
            kwargs["stderr"] = asyncio.subprocess.PIPE
        if system_name == "Windows":
            kwargs["executable"] = "C:\\Windows\\System32\\cmd.exe"

        # proc: asyncio.subprocess.Process — 原生异步子进程（不占线程池）
        if shell:
            proc = await asyncio.create_subprocess_shell(command, **kwargs)
        else:
            import shlex
            proc = await asyncio.create_subprocess_exec(*shlex.split(command), **kwargs)

        stdout_lines = []
        stderr_all = b""
        timed_out = False
        rc = None
        try:
            # 总超时保护：逐行收集（不流式），超时后仍返回已收集的部分输出
            async with asyncio.timeout(timeout):
                if capture:
                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        stdout_lines.append(line)
                    stderr_all = await proc.stderr.read()
                rc = await proc.wait()
        except TimeoutError:
            timed_out = True
            proc.kill()
            try:
                rc = await proc.wait()
            except Exception:
                rc = -1
            try:
                stderr_all += await proc.stderr.read()
            except Exception:
                pass

        def _to_text(b):
            if b is None:
                return ""
            return b.decode(encoding, errors=errors) if text else b

        stdout_text = _to_text(b"".join(stdout_lines))
        stderr_text = _to_text(stderr_all)

        # 截断：按 output_part 保留 head / tail / middle 之一，并给出省略提示
        truncated = False
        skipped = 0
        if output_limit > 0 and len(stdout_text) > output_limit:
            total = len(stdout_text)
            skipped = total - output_limit
            truncated = True
            note = f"...(输出已截断，省略 {skipped} 字符)..."
            if output_part == "head":
                stdout_text = stdout_text[:output_limit] + "\n" + note
            elif output_part == "tail":
                stdout_text = note + "\n" + stdout_text[-output_limit:]
            else:  # middle：开头 + 结尾各一半，中间省略
                head_len = output_limit // 2
                tail_len = output_limit - head_len
                stdout_text = (
                    stdout_text[:head_len]
                    + "\n" + note + "\n"
                    + stdout_text[-tail_len:]
                )

        result_data = {
            "stdout": stdout_text,
            "stderr": stderr_text,
            "return_code": rc,
            "os_type": system_name,
            "truncated": truncated,
            "skipped": skipped,
            "timed_out": timed_out,
        }
        message = "success" if not timed_out else "命令执行超时，已返回部分输出"
        return _ok(result_data, message)

    except Exception as e:
        return _err(f"处理失败：{str(e)}", "cmd_run", code=500)
