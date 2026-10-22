"""LLM Provider：mock（离线降级）与 openai_compatible（OpenAI 兼容流式接口）。"""

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BLOCK_PATTERN = re.compile(
    r"\[(\d+)\]\s*来源：([^\n]+)\n(.*?)(?=\n\n\[\d+\]\s*来源：|\n\n【问题】|\Z)",
    re.S,
)
QUESTION_PATTERN = re.compile(r"【问题】\n?(.*)", re.S)
STREAM_PIECE_SIZE = 24


class LLMUnavailableError(Exception):
    """模型服务不可用（无 Key、限流、网络错误等），可降级为 mock。"""


class LLMProvider(Protocol):
    """LLM 流式接口。"""

    name: str

    def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...


def _split_pieces(text: str, size: int = STREAM_PIECE_SIZE) -> list[str]:
    """把答案切成小片段，模拟流式输出。"""
    return [text[index : index + size] for index in range(0, len(text), size)] or [""]


class MockLLMProvider:
    """完全离线的占位模型：回显检索到的资料片段，不发起任何网络请求。"""

    name = "mock"

    def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        answer = self._compose(messages)
        return self._stream(answer)

    async def _stream(self, answer: str) -> AsyncIterator[str]:
        for piece in _split_pieces(answer):
            yield piece

    def _compose(self, messages: list[dict[str, str]]) -> str:
        """从 user 消息里取出问题与资料块，拼出可引用的 mock 回答。"""
        user_content = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user_content = message.get("content", "")
                break

        question_match = QUESTION_PATTERN.search(user_content)
        question = (question_match.group(1) if question_match else user_content).strip()

        blocks = BLOCK_PATTERN.findall(user_content)
        if not blocks:
            return (
                f"（mock 模式）没有检索到与「{question}」相关的资料，"
                "请先上传文档并完成索引，或换一种问法。"
            )

        index, source, text = blocks[0]
        snippet = " ".join(text.split())[:160]
        return (
            f"（mock 模式）根据知识库检索到的 {len(blocks)} 条资料回答「{question}」：\n\n"
            f"{snippet}……（引用 [{index}]，来源 {source}）\n\n"
            "当前为离线 mock 模型，只回显检索到的原文片段；"
            "配置 LLM_PROVIDER=openai_compatible 与 LLM_API_KEY 后可获得真实模型生成的答案。"
        )


class OpenAICompatibleLLMProvider:
    """OpenAI 兼容 /chat/completions 流式接口。"""

    name = "openai_compatible"

    def __init__(self) -> None:
        self._base_url = settings.LLM_BASE_URL.rstrip("/")
        self._model = settings.LLM_MODEL
        self._api_key = settings.LLM_API_KEY
        self._timeout = settings.LLM_TIMEOUT

    async def stream_chat(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """逐 token 产出；首个 token 之前失败抛出 LLMUnavailableError。"""
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(self._timeout, connect=10.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", "replace")[:300]
                        raise LLMUnavailableError(f"LLM 返回 {response.status_code}: {body}")

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            yield content
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise LLMUnavailableError(f"LLM 调用失败: {exc}") from exc


def get_llm() -> LLMProvider:
    """按配置返回 Provider；openai_compatible 缺 Key 时降级为 mock。"""
    if settings.LLM_PROVIDER == "openai_compatible":
        if settings.LLM_API_KEY:
            return OpenAICompatibleLLMProvider()
        logger.warning("LLM_PROVIDER=openai_compatible 但 LLM_API_KEY 为空，降级为 mock")
    return MockLLMProvider()
