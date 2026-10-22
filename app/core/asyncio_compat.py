"""Windows 事件循环兼容。

psycopg 的异步驱动不支持 Windows 默认的 ProactorEventLoop，
需要使用 SelectorEventLoop。生产环境（Linux 容器）不受影响。
"""

import asyncio
import selectors
import sys
from collections.abc import Coroutine
from typing import Any


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """构造 SelectorEventLoop。"""
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """运行协程：Windows 强制 Selector，其它平台保持默认。"""
    if sys.platform == "win32":
        return asyncio.run(coro, loop_factory=selector_loop_factory)
    return asyncio.run(coro)


def unsupported_loop_message(loop: asyncio.AbstractEventLoop) -> str | None:
    """若当前事件循环与 psycopg 异步驱动不兼容，返回排查提示。"""
    if sys.platform != "win32":
        return None
    if loop.__class__.__name__ != "ProactorEventLoop":
        return None
    return (
        "检测到 Windows ProactorEventLoop：psycopg 异步驱动不支持该事件循环，"
        "数据库操作会失败。请使用 `uv run uvicorn app.main:app --reload`"
        "（reload/多 worker 模式会启用 SelectorEventLoop），"
        "或设置 PYTHONASYNCIODEBUG 前先切换事件循环策略。"
    )
