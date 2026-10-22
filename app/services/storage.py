"""对象存储抽象：MinIO 与本地目录两种后端（降级策略由配置开关控制）。"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

UNSAFE_KEY_CHARS = re.compile(r"[^A-Za-z0-9._/-]")


class StorageBackend(Protocol):
    """存储后端接口。"""

    async def put_object(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get_object(self, key: str) -> bytes: ...

    async def delete_object(self, key: str) -> None: ...


def sanitize_key(key: str) -> str:
    """清理对象键，禁止路径穿越。"""
    cleaned = UNSAFE_KEY_CHARS.sub("_", key.strip("/"))
    parts = [part for part in cleaned.split("/") if part not in ("", ".", "..")]
    return "/".join(parts)


def build_storage_key(
    tenant_id: int,
    kb_id: int,
    document_id: int,
    filename: str,
) -> str:
    """生成对象键：tenants/{tid}/kb/{kid}/docs/{did}/{filename}。"""
    safe_name = sanitize_key(filename) or "file"
    return f"tenants/{tenant_id}/kb/{kb_id}/docs/{document_id}/{safe_name}"


class MinioStorage:
    """MinIO 后端（minio-py 为同步库，放入线程池执行）。"""

    def __init__(self) -> None:
        self._client = None
        self._lock = asyncio.Lock()
        self._bucket = settings.MINIO_BUCKET

    def _get_client(self):
        """惰性创建客户端，避免应用启动依赖 MinIO 可用。"""
        if self._client is None:
            from minio import Minio

            self._client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE,
            )
        return self._client

    async def _ensure_bucket(self) -> None:
        """确保桶存在（幂等）。"""

        def _ensure() -> None:
            client = self._get_client()
            if not client.bucket_exists(self._bucket):
                client.make_bucket(self._bucket)

        try:
            await asyncio.to_thread(_ensure)
        except Exception as exc:  # MinIO 不可用
            logger.warning("MinIO 桶检查失败: %s", exc)
            raise AppError(50201, "对象存储不可用，请检查 MinIO 服务", 502) from exc

    async def put_object(self, key: str, data: bytes, content_type: str) -> None:
        """上传对象。"""
        import io

        await self._ensure_bucket()

        def _put() -> None:
            self._get_client().put_object(
                self._bucket,
                key,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )

        try:
            await asyncio.to_thread(_put)
        except Exception as exc:
            logger.exception("MinIO 上传失败 key=%s", key)
            raise AppError(50201, "文件上传到对象存储失败", 502) from exc

    async def get_object(self, key: str) -> bytes:
        """下载对象。"""

        def _get() -> bytes:
            response = self._get_client().get_object(self._bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:
            logger.exception("MinIO 读取失败 key=%s", key)
            raise AppError(50201, "读取对象存储失败", 502) from exc

    async def delete_object(self, key: str) -> None:
        """删除对象（不存在时忽略）。"""

        def _remove() -> None:
            self._get_client().remove_object(self._bucket, key)

        try:
            await asyncio.to_thread(_remove)
        except Exception as exc:  # 删除失败不影响业务主流程
            logger.warning("MinIO 删除失败 key=%s: %s", key, exc)


class LocalStorage:
    """本地目录后端：离线降级，写入 LOCAL_STORAGE_DIR。"""

    def __init__(self) -> None:
        self._base = Path(settings.LOCAL_STORAGE_DIR).resolve()

    def _path_for(self, key: str) -> Path:
        path = (self._base / sanitize_key(key)).resolve()
        if not str(path).startswith(str(self._base)):
            raise AppError(40001, "非法的存储路径", 400)
        return path

    async def put_object(self, key: str, data: bytes, content_type: str) -> None:
        """写入本地文件。"""
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    async def get_object(self, key: str) -> bytes:
        """读取本地文件。"""
        path = self._path_for(key)
        if not path.exists():
            raise AppError(40401, "文件不存在", 404)
        return path.read_bytes()

    async def delete_object(self, key: str) -> None:
        """删除本地文件（不存在时忽略）。"""
        path = self._path_for(key)
        if path.exists():
            path.unlink()


def get_storage() -> StorageBackend:
    """按配置返回存储后端。"""
    if settings.STORAGE_PROVIDER == "local":
        return LocalStorage()
    return MinioStorage()
