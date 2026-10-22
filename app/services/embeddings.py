"""Embedding Provider：hash（离线降级）与 openai_compatible（真实模型）。"""

import hashlib
import logging
import math
import re
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

ASCII_WORD = re.compile(r"[a-z0-9_]+")
CJK_BLOCK = re.compile(r"[\u4e00-\u9fff]+")


class EmbeddingProvider(Protocol):
    """向量化接口。"""

    name: str
    dim: int

    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


def tokenize(text: str) -> list[str]:
    """分词：ASCII 词 + 中文字符与二元组（够用于词汇重叠检索）。"""
    tokens = ASCII_WORD.findall(text.lower())
    for match in CJK_BLOCK.finditer(text):
        block = match.group(0)
        tokens.extend(block)
        tokens.extend(block[i : i + 2] for i in range(len(block) - 1))
    return tokens


class HashEmbeddingProvider:
    """确定性哈希向量：零依赖、零成本，只捕捉词汇重叠。

    使用带符号的 hashing trick：每个 token 由 md5 决定维度与符号，
    再做 L2 归一化，因此同一文本在任何进程/机器上都得到相同向量。
    """

    name = "hash"

    def __init__(self, dim: int) -> None:
        self.dim = dim

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量向量化。"""
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = tokenize(text)
        if not tokens:
            vector[0] = 1.0
            return vector

        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], "big") % self.dim
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:  # 符号相互抵消，退化为基础向量
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]


class OpenAICompatibleEmbeddingProvider:
    """OpenAI 兼容 /embeddings 接口。"""

    name = "openai_compatible"

    def __init__(self) -> None:
        self.dim = settings.EMBEDDING_DIM
        self._base_url = settings.EMBEDDING_BASE_URL.rstrip("/")
        self._model = settings.EMBEDDING_MODEL
        self._api_key = settings.EMBEDDING_API_KEY
        self._timeout = settings.EMBEDDING_TIMEOUT

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """调用远端 Embedding；失败抛出 50201。"""
        if not texts:
            return []

        payload = {"model": self._model, "input": texts}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/embeddings", json=payload, headers=headers
                )
                response.raise_for_status()
                data = response.json()["data"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("Embedding 服务调用失败: %s", exc)
            raise AppError(50201, "Embedding 服务不可用", 502) from exc

        ordered = sorted(data, key=lambda item: item.get("index", 0))
        vectors = [[float(value) for value in item["embedding"]] for item in ordered]
        self._validate_dim(vectors)
        return vectors

    def _validate_dim(self, vectors: list[list[float]]) -> None:
        """维度必须与 EMBEDDING_DIM（pgvector 列宽）一致。"""
        for vector in vectors:
            if len(vector) != self.dim:
                raise AppError(
                    50201,
                    f"Embedding 维度不匹配：期望 {self.dim}，实际 {len(vector)}",
                    502,
                )


def get_embedder() -> EmbeddingProvider:
    """按配置返回 Provider；openai_compatible 配置不全时降级为 hash。"""
    if settings.EMBEDDING_PROVIDER == "openai_compatible":
        if settings.EMBEDDING_BASE_URL and settings.EMBEDDING_API_KEY and settings.EMBEDDING_MODEL:
            return OpenAICompatibleEmbeddingProvider()
        logger.warning(
            "EMBEDDING_PROVIDER=openai_compatible 但缺少 BASE_URL/API_KEY/MODEL，降级为 hash"
        )
    return HashEmbeddingProvider(settings.EMBEDDING_DIM)
