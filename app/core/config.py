"""应用配置：统一从环境变量 / .env 读取，业务代码禁止散落 os.getenv。"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["mock", "openai_compatible"]
EmbeddingProvider = Literal["hash", "openai_compatible"]
StorageProvider = Literal["minio", "local"]


class Settings(BaseSettings):
    """全部运行期配置项，默认值保证无 .env 时也能启动。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # 应用
    APP_NAME: str = "ai-rag-knowledge-py"
    APP_ENV: str = "dev"
    API_PREFIX: str = "/api"
    # 鉴权
    SECRET_KEY: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    # 基础设施
    DATABASE_URL: str = "postgresql+psycopg://rag:rag@localhost:5433/rag"
    REDIS_URL: str = "redis://localhost:6379/0"
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "rag-docs"
    MINIO_SECURE: bool = False

    # 文件存储：minio 为默认；local 为离线降级（写入 LOCAL_STORAGE_DIR）
    STORAGE_PROVIDER: StorageProvider = "minio"
    LOCAL_STORAGE_DIR: str = "data/uploads"
    MAX_UPLOAD_MB: int = 20
    MAX_UPLOAD_BYTES: int = 0  # 留空时由 MAX_UPLOAD_MB 计算

    @property
    def upload_limit_bytes(self) -> int:
        """单个上传文件的大小上限（字节）。"""
        return self.MAX_UPLOAD_BYTES or self.MAX_UPLOAD_MB * 1024 * 1024

    # LLM（无 Key 或限流时降级为 mock）
    LLM_PROVIDER: LLMProvider = "mock"
    LLM_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "deepseek/deepseek-v4-flash:free"
    LLM_TIMEOUT: float = 60.0

    # Embedding（默认 hash 降级）
    EMBEDDING_PROVIDER: EmbeddingProvider = "hash"
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = ""
    EMBEDDING_DIM: int = 1536
    EMBEDDING_TIMEOUT: float = 60.0
    EMBEDDING_BATCH_SIZE: int = 32

    # RAG 参数
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 120
    TOP_K: int = 5


@lru_cache
def get_settings() -> Settings:
    """进程内单例配置。"""
    return Settings()


settings = get_settings()
