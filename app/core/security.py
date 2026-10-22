"""密码哈希与 JWT 签发 / 校验。"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt 只取前 72 字节，超出部分必须显式拒绝，避免静默截断
BCRYPT_MAX_BYTES = 72


class TokenExpiredError(Exception):
    """Token 已过期。"""


class TokenInvalidError(Exception):
    """Token 无效（签名错误 / 格式错误 / 声明缺失）。"""


def hash_password(plain_password: str) -> str:
    """bcrypt 哈希。"""
    if len(plain_password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"密码不能超过 {BCRYPT_MAX_BYTES} 字节")
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """校验密码，哈希格式异常时返回 False 而不是抛错。"""
    try:
        return pwd_context.verify(plain_password, password_hash)
    except ValueError:
        return False


def create_access_token(
    *,
    subject: str,
    tenant_id: int,
    roles: list[str],
    expires_minutes: int | None = None,
) -> str:
    """签发 HS256 访问令牌，sub=用户 id，tid=租户 id，roles=角色编码。"""
    minutes = (
        expires_minutes if expires_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "tid": tenant_id,
        "roles": roles,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """解析并校验 Token；过期与非法分别抛出不同异常。"""
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("访问令牌已过期") from exc
    except jwt.PyJWTError as exc:
        raise TokenInvalidError("访问令牌无效") from exc
