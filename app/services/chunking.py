"""文本切片：按字符窗口切分，优先在段落 / 句子边界断开，保留重叠。"""

import re

from app.core.errors import AppError

# 切分优先级：段落 > 换行 > 句末标点 > 分号/逗号
SEPARATORS = ("\n\n", "\n", "。", "！", "？", "；", ". ", "! ", "? ", "; ", "，", ", ")
MAX_BOUNDARY_LOOKBACK = 240


def _find_boundary(text: str, start: int, end: int) -> int:
    """在 [end - LOOKBACK, end) 内寻找最后一个分隔符位置（返回切分点）。"""
    lookback_start = max(start + 1, end - MAX_BOUNDARY_LOOKBACK)
    best = -1
    for separator in SEPARATORS:
        index = text.rfind(separator, lookback_start, end)
        if index > best:
            best = index + len(separator) - 1
    return best if best > start else -1


def split_text(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """把文本切成不超过 chunk_size 的片段，相邻片段重叠 chunk_overlap 个字符。"""
    if chunk_size <= 0:
        raise AppError(50001, "CHUNK_SIZE 必须大于 0", 500)

    cleaned = text.strip()
    if not cleaned:
        return []

    overlap = max(0, min(chunk_overlap, chunk_size - 1))
    chunks: list[str] = []
    start = 0
    length = len(cleaned)

    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            boundary = _find_boundary(cleaned, start, end)
            if boundary > start:
                end = boundary + 1

        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)

        if end >= length:
            break

        next_start = end - overlap
        start = next_start if next_start > start else end

        # 跳过下一片段起始处的空白，避免切片以空白开头
        while start < length and cleaned[start] in (" ", "\t", "\n"):
            start += 1

    return chunks


def chunk_statistics(chunks: list[str]) -> dict[str, int]:
    """切片统计，供日志与测试使用。"""
    if not chunks:
        return {"count": 0, "total_chars": 0, "max_chars": 0, "min_chars": 0}
    lengths = [len(chunk) for chunk in chunks]
    return {
        "count": len(chunks),
        "total_chars": sum(lengths),
        "max_chars": max(lengths),
        "min_chars": min(lengths),
    }


def strip_whitespace(text: str) -> str:
    """压缩多余空白（解析后常用）。"""
    return re.sub(r"[ \t]{2,}", " ", text)
