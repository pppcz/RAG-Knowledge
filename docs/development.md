# 开发规范

本文约定本项目的目录组织、编码风格、接口与数据库约定，以及提交前的自检项。
新加入的贡献者请先通读一遍。

## 1. 技术栈

| 层 | 选型 |
| --- | --- |
| 后端 | FastAPI、Uvicorn、Pydantic v2、SQLAlchemy 2、Alembic |
| 数据库 | PostgreSQL 16 + pgvector |
| 缓存 | Redis 7（当前预留，后续用于缓存与限流） |
| 对象存储 | MinIO（可切换为本地目录） |
| 鉴权 | JWT + passlib[bcrypt] |
| 文档解析 | pypdf、python-docx、markdown |
| 流式输出 | sse-starlette |
| 前端 | Vue3 + Vite + TypeScript + Element Plus + Axios + Pinia |
| 测试 | pytest、pytest-asyncio、httpx |
| 质量 | ruff（必需）、mypy（可选） |
| 运行时 | Python 3.12，由 uv 管理 |
| 部署 | Docker、Docker Compose、Nginx |

替换任何一项选型前请先在设计文档中说明理由，避免同类能力被引入两份。

## 2. 目录结构

```text
ai-rag-knowledge-py/
├── app/
│   ├── main.py
│   ├── core/          # config / db / security / errors
│   ├── api/           # 路由层
│   ├── models/        # SQLAlchemy ORM
│   ├── schemas/       # Pydantic 模型
│   ├── services/      # 业务逻辑
│   └── workers/       # 后台任务
├── alembic/           # 数据库迁移
├── tests/
├── frontend/
├── docs/
├── scripts/
├── deploy/
└── .github/workflows/
```

约束：

- 后端代码只放 `app/`，不在根目录新增 Python 文件
- 前端代码只放 `frontend/`
- 数据库变更只通过 `alembic/`
- 文档只放 `docs/`
- 运维脚本只放 `scripts/`
- 不要跨层调用：`api/` 不直接访问 `models/`，统一经 `services/`

## 3. 编码规范

### Python

- 目标版本 3.12，全部函数标注参数与返回类型
- Pydantic 使用 v2 语法（`model_config`、`field_validator`）
- SQLAlchemy 使用 2.0 风格（`Mapped`、`mapped_column`）
- API 层一律 `async def`
- 不允许裸 `except:`，捕获后必须记录日志并给出明确错误
- 日志用 `logging`，禁止 `print`
- 配置集中在 `app/core/config.py`，不在业务代码里散落 `os.getenv`

### 命名

| 对象 | 风格 | 示例 |
| --- | --- | --- |
| 表 | `snake_case` 复数 | `knowledge_bases` |
| 字段 | `snake_case` | `chunk_count` |
| 类 | `PascalCase` | `DocumentService` |
| 函数 / 变量 | `snake_case` | `build_embedding` |
| 常量 | `UPPER_SNAKE_CASE` | `DEFAULT_TOP_K` |
| API 路径 | `kebab-case` 或 `snake_case` | `/api/kb`、`/api/docs/upload` |

### 前端

- Vue3 `<script setup>` + TypeScript
- 组件名 `PascalCase`，文件名与组件名一致
- 所有 HTTP 调用封装在 `src/api/`，组件内不直接写 `axios`
- 状态用 Pinia
- 样式优先使用 Element Plus，避免堆叠自定义 CSS

## 4. 数据库约定

- 每张表必须有 `id`、`created_at`、`updated_at`
- 多租户表必须有 `tenant_id`，所有查询显式带该条件
- 软删除统一用可空的 `deleted_at`
- 外键必须建索引
- 迁移只通过 Alembic，不手工改库
- 建表顺序：`tenants` → `users` / `roles` / `permissions` → `knowledge_bases` →
  `documents` → `chunks` → `conversations` → `messages`
- 向量列固定 `vector(1536)`，必须与 `EMBEDDING_DIM` 一致

## 5. API 约定

- 统一前缀 `/api`
- 健康检查 `GET /health`，不鉴权、不依赖任何外部服务
- 鉴权头 `Authorization: Bearer <token>`
- 错误响应统一结构：

```json
{ "code": 40001, "message": "错误说明", "detail": {} }
```

- 分页参数 `page`、`page_size`；分页响应：

```json
{ "items": [], "total": 0, "page": 1, "page_size": 20 }
```

- SSE 接口返回 `text/event-stream`，事件名固定为 `message`、`done`、`error`
- 所有接口必须写 OpenAPI 描述（`summary`、`description`、响应模型）

## 6. 安全约定

- `.env` 永不提交；`.env.example` 只放占位符
- 密码使用 bcrypt 哈希存储
- JWT 密钥从环境变量读取，生产环境必须替换默认值
- API Key 只存在于 `.env` 或系统环境变量
- 上传文件必须校验扩展名与大小
- MinIO 凭据不得硬编码
- 日志不得输出密码、Token、API Key
- 跨租户查询必须显式过滤 `tenant_id`
- 不把公司内部代码、数据、文档复制进本仓库

## 7. 测试

- 每个功能模块配套 pytest 用例，覆盖正常路径与关键异常路径
- 使用 `httpx.AsyncClient` 测 API
- 测试库与开发库分离（`rag_test` vs `rag`）
- 测试不依赖真实外部 LLM / Embedding 接口，统一走 `mock` / `hash`
- 提交前 `uv run pytest` 必须全绿

## 8. 提交前自检

```powershell
uv run ruff check .
uv run pytest
cd frontend; npm run build
```

- 单次提交只做一件事，避免把无关改动混进来
- 提交信息格式 `type(scope): 描述`，`type` 取 `feat` / `fix` / `refactor` / `docs` /
  `test` / `chore`
- 示例：`feat(chat): 支持 SSE 流式输出与引用溯源`
- 不提交 `.env`、密钥、日志、本地数据目录与构建产物
