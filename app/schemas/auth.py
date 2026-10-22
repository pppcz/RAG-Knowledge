"""鉴权相关 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

USERNAME_PATTERN = r"^[A-Za-z0-9_]{3,64}$"
TENANT_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{1,63}$"


class _PasswordMixin(BaseModel):
    """密码长度校验：bcrypt 上限 72 字节。"""

    password: str = Field(..., min_length=6, max_length=72, description="密码，6-72 字符")

    @field_validator("password")
    @classmethod
    def _check_bcrypt_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("密码不能超过 72 字节")
        return value


class RegisterRequest(_PasswordMixin):
    """注册：同时创建租户与租户管理员。"""

    tenant_name: str = Field(..., min_length=1, max_length=128, description="租户/组织名称")
    tenant_slug: str | None = Field(
        None,
        pattern=TENANT_SLUG_PATTERN,
        description="租户标识（小写字母/数字/短横线），不填则自动生成",
        examples=["acme"],
    )
    username: str = Field(..., pattern=USERNAME_PATTERN, description="登录名")
    email: EmailStr = Field(..., description="邮箱")
    full_name: str | None = Field(None, max_length=128, description="显示名")


class LoginRequest(BaseModel):
    """登录：用户名为租户内唯一，跨租户重名时需提供 tenant_slug。"""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=72)
    tenant_slug: str | None = Field(None, description="租户标识，同用户名存在于多个租户时必填")


class UserOut(BaseModel):
    """用户信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    username: str
    email: EmailStr
    full_name: str | None = None
    is_active: bool
    is_superuser: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """登录 / 注册成功返回。"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="有效期（秒）")
    user: UserOut


class MeResponse(BaseModel):
    """当前用户及其角色、权限。"""

    user: UserOut
    roles: list[str]
    permissions: list[str]


class UserCreateRequest(_PasswordMixin):
    """租户管理员创建用户。"""

    username: str = Field(..., pattern=USERNAME_PATTERN)
    email: EmailStr
    full_name: str | None = Field(None, max_length=128)
    role_codes: list[str] = Field(default_factory=list, description="角色编码，默认 member")
