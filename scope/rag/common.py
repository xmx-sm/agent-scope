# -*- coding: utf-8 -*-
"""RAG 文档解析、切片、向量化辅助。

从 ``agent_study/scope/rag/common.py`` 迁移，按新框架整理：

- 解析器使用官方 ``agentscope.rag``（Text/PDF/PPT/Word/Excel/Image）
- 切片使用 ``ApproxTokenChunker``
- embedding 使用 ``llm.agent_model.async_get_embedding_model``
- 默认 ``require_file=True``：路径写错时直接 400，避免把路径字符串当正文入库

统一信封 ``{"code": 200|400|500, "data": ..., "message": ...}``。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from agentscope.rag import (
    ApproxTokenChunker,
    ExcelParser,
    ImageParser,
    PDFParser,
    PPTParser,
    TextParser,
    WordParser,
)

try:  # scope.rag 包导入
    from ..llm.agent_model import async_get_embedding_model
except ImportError:  # 顶层 rag 导入（scope/ 在 sys.path）
    from llm.agent_model import async_get_embedding_model

try:
    from ..common.fs import check_read_path
except ImportError:
    from common.fs import check_read_path


EMBED_BATCH_LIMIT = 64

TEXT_EXTS = [".txt", ".text", ".md", ".markdown", ".csv", ".html", ".htm",
             ".rst", ".json", ".xml", ".yaml", ".yml"]
PDF_EXTS = [".pdf"]
PPT_EXTS = [".pptx"]
WORD_EXTS = [".docx"]
EXCEL_EXTS = [".xlsx", ".xls"]
IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]


def _where(fn: str) -> str:
    return f"{os.path.abspath(__file__)}_{fn}"


def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _err(message: str, fn: str, code: int = 400) -> Dict[str, Any]:
    return {"code": code, "data": _where(fn), "message": f"错误：{message}"}


def _parser_for_ext(ext: str, cfg: dict) -> Any:
    if ext in TEXT_EXTS:
        return TextParser()
    if ext in PDF_EXTS:
        return PDFParser()
    if ext in PPT_EXTS:
        return PPTParser(
            include_image=cfg.get("include_image", True),
            separate_table=cfg.get("separate_table", False),
            table_format=cfg.get("table_format", "json"),
            slide_prefix=cfg.get("slide_prefix"),
            slide_suffix=cfg.get("slide_suffix"),
        )
    if ext in WORD_EXTS:
        return WordParser(
            include_image=cfg.get("include_image", True),
            separate_table=cfg.get("separate_table", False),
            table_format=cfg.get("table_format", "json"),
        )
    if ext in EXCEL_EXTS:
        return ExcelParser(
            include_image=cfg.get("include_image", True),
            separate_sheet=cfg.get("separate_sheet", False),
            table_format=cfg.get("table_format", "json"),
            include_sheet_names=cfg.get("include_sheet_names", True),
            include_cell_coordinates=cfg.get("include_cell_coordinates", False),
        )
    if ext in IMAGE_EXTS:
        return ImageParser()
    raise ValueError(f"暂不支持的文件类型: {ext}")


async def async_file_parser(data: dict = None) -> Dict[str, Any]:
    """按后缀解析文件为 sections。

    ``data["file_config"]``:
        file_path(str, 条件必填)  本地路径；is_bytes=True 时可省
        file_name(str, 可选)      展示名/默认取 basename
        file_extension(str, 可选) 不带点；缺省按 file_path 推断
        is_bytes(bool, 默认 False)
        bytes(bytes, 条件必填)    is_bytes=True 时使用
        require_file(bool, 默认 True) 非二进制时必须存在真实文件

    其他 PPT/Word/Excel/图片参数见 ``_parser_for_ext``。
    """
    fn = "async_file_parser"
    try:
        if not isinstance(data, dict):
            return _err("data 必须是字典对象", fn)
        cfg = data.get("file_config")
        if not isinstance(cfg, dict):
            return _err("缺少 file_config 配置段", fn)

        is_bytes = bool(cfg.get("is_bytes", False))
        file_name = cfg.get("file_name")
        if is_bytes:
            raw = cfg.get("bytes")
            if not isinstance(raw, (bytes, bytearray)):
                return _err("is_bytes=True 时 bytes 必须是 bytes", fn)
            ext = cfg.get("file_extension")
            if not ext:
                return _err("二进制解析必须提供 file_extension", fn)
            file_arg: Any = bytes(raw)
        else:
            path = cfg.get("file_path")
            if not path:
                return _err("缺少 file_config.file_path", fn)
            allowed, reason = check_read_path(str(path))
            if not allowed:
                return _err(f"读取路径被拒：{reason}", fn)
            if cfg.get("require_file", True) and not os.path.isfile(str(path)):
                return _err(f"文件不存在或不是文件：{path}", fn)
            file_arg = str(path)
            file_name = file_name or os.path.basename(str(path))
            ext = cfg.get("file_extension") or os.path.splitext(str(path))[1]

        ext = str(ext).lower()
        if not ext.startswith("."):
            ext = "." + ext
        parser = _parser_for_ext(ext, cfg)
        sections = await parser.parse(file=file_arg, filename=file_name)
        return _ok(sections, f"文件解析成功（{ext}）")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except ImportError as e:
        return _err(f"缺少文件解析依赖：{e}（pip install 对应包）", fn)
    except Exception as e:
        return _err(f"文件解析失败：{type(e).__name__}: {e}", fn, code=500)


async def async_file_chunker(data: dict = None) -> Dict[str, Any]:
    """解析文件并切块。

    ``data["file_chunker"]``:
        chunk_size(int, 默认 256)
        overlap(int, 默认 0)
    """
    fn = "async_file_chunker"
    try:
        if not isinstance(data, dict):
            return _err("data 必须是字典对象", fn)
        cfg = data.get("file_chunker")
        if not isinstance(cfg, dict):
            return _err("缺少 file_chunker 配置段", fn)
        try:
            chunk_size = int(cfg.get("chunk_size", 256))
            overlap = int(cfg.get("overlap", 0) or 0)
        except (TypeError, ValueError):
            return _err("chunk_size / overlap 必须是整数", fn)
        if chunk_size <= 0:
            return _err("chunk_size 必须大于 0", fn)
        if overlap < 0 or overlap >= chunk_size:
            return _err("overlap 必须 >=0 且小于 chunk_size", fn)

        parsed = await async_file_parser(data)
        if parsed.get("code") != 200:
            return parsed
        chunker = ApproxTokenChunker(
            ApproxTokenChunker.Parameters(chunk_size=chunk_size, overlap=overlap)
        )
        chunks = await chunker.chunk(parsed["data"])
        return _ok(chunks, "文件切片成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"文件切片失败：{type(e).__name__}: {e}", fn, code=500)


async def async_get_chunks(data: dict = None) -> Dict[str, Any]:
    """解析 + 切片，返回 Chunk 列表。"""
    return await async_file_chunker(data)


def get_chunk_text(chunk: Any) -> str:
    """提取 chunk 的文本内容。"""
    content = getattr(chunk, "content", None)
    if content is None:
        return ""
    text = getattr(content, "text", None)
    if isinstance(text, str):
        return text
    source = getattr(content, "source", None)
    if isinstance(source, str):
        return source
    return str(content)


def get_chunk_metadata(chunk: Any) -> Dict[str, Any]:
    """提取 metadata，并补 doc_id / chunk_index / total_chunks。"""
    metadata = dict(getattr(chunk, "metadata", None) or {})
    metadata["doc_id"] = getattr(chunk, "source", None) or metadata.get("source", "")
    metadata["chunk_index"] = getattr(chunk, "chunk_index", 0)
    metadata["total_chunks"] = getattr(chunk, "total_chunks", 0)
    return metadata


async def _ensure_embedding_model(data: dict) -> Dict[str, Any]:
    injected = data.get("embedding_model")
    if injected is not None:
        return _ok(injected)
    cfg = data.get("embedding")
    if not isinstance(cfg, dict) or not cfg:
        return _err("缺少 embedding 配置（或传入 embedding_model 对象）",
                    "async_get_embeddings")
    return await async_get_embedding_model({"embedding": cfg})


async def async_get_embeddings(data: dict = None) -> Dict[str, Any]:
    """解析、切片并批量向量化。

    返回 ``{"chunks", "texts", "embeddings"}``。
    可通过 ``data["embedding_model"]`` 注入已构造的 embedding 模型。
    """
    fn = "async_get_embeddings"
    try:
        if not isinstance(data, dict):
            return _err("data 必须是字典对象", fn)
        chunk_data = await async_get_chunks(data)
        if chunk_data.get("code") != 200:
            return chunk_data
        chunks = chunk_data.get("data") or []
        if not chunks:
            return _err("文件切片结果为空", fn)
        texts = [get_chunk_text(c) for c in chunks]
        if not all(texts):
            return _err("切片中存在空文本", fn)

        model_r = await _ensure_embedding_model(data)
        if model_r.get("code") != 200:
            return model_r
        model = model_r["data"]

        try:
            batch_size = int((data.get("embedding") or {}).get("batch_size", EMBED_BATCH_LIMIT))
        except (TypeError, ValueError):
            batch_size = EMBED_BATCH_LIMIT
        batch_size = max(1, batch_size)

        embeddings: List[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = await model(batch)
            batch_embeddings = getattr(response, "embeddings", response)
            embeddings.extend(list(x) for x in batch_embeddings)

        if len(embeddings) != len(texts):
            return _err("embedding 返回数量与切片数量不一致", fn, code=500)
        return _ok({"chunks": chunks, "texts": texts, "embeddings": embeddings},
                   "文本向量化成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"文本向量化失败：{type(e).__name__}: {e}", fn, code=500)


async def async_get_query_vector(data: dict = None) -> Dict[str, Any]:
    """把 ``data["search_config"]["query"]`` 向量化。"""
    fn = "async_get_query_vector"
    try:
        if not isinstance(data, dict):
            return _err("data 必须是字典对象", fn)
        query = (data.get("search_config") or {}).get("query")
        if not isinstance(query, str) or not query.strip():
            return _err("缺少 search_config.query", fn)
        model_r = await _ensure_embedding_model(data)
        if model_r.get("code") != 200:
            return model_r
        response = await model_r["data"]([query])
        vectors = getattr(response, "embeddings", response)
        try:
            vector = list(vectors[0])
        except (IndexError, TypeError):
            return _err("embedding 未返回查询向量", fn, code=500)
        return _ok(vector, "检索向量化成功")
    except (TypeError, ValueError) as e:
        return _err(str(e), fn)
    except Exception as e:
        return _err(f"查询向量化失败：{type(e).__name__}: {e}", fn, code=500)


__all__ = [
    "async_file_parser",
    "async_file_chunker",
    "async_get_chunks",
    "async_get_embeddings",
    "async_get_query_vector",
    "get_chunk_text",
    "get_chunk_metadata",
]
