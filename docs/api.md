# API 文档

- 统一前缀：`/api`（健康检查除外，为 `GET /health`）
- 鉴权：`Authorization: Bearer <token>`
- 交互式文档：`http://localhost:8000/docs`，OpenAPI JSON：`http://localhost:8000/openapi.json`

## 通用约定

### 错误响应

所有错误（业务异常、参数校验、404、500）统一返回：

```json
{
  "code": 40101,
  "message": "用户名或密码错误",
  "detail": {}
}
```

业务错误码前 3 位与 HTTP 状态码对齐：

| HTTP | code | 含义 |
| --- | --- | --- |
| 400 | 40001 | 参数或业务错误（如角色不存在、用户名跨租户歧义） |
| 401 | 40101 | 未认证 / 令牌无效 / 用户名或密码错误 |
| 401 | 40102 | 令牌过期 |
| 403 | 40301 | 权限不足 / 账号停用 |
| 404 | 40401 | 资源不存在 |
| 409 | 40901 | 资源冲突（租户标识、用户名、邮箱重复） |
| 422 | 40001 | 请求体校验失败（`detail.errors` 为字段级错误） |
| 500 | 50001 | 服务器内部错误 |

### 分页

请求参数：`page`（>=1，默认 1）、`page_size`（1-100，默认 20）。

响应：

```json
{"items": [], "total": 0, "page": 1, "page_size": 20}
```

## 鉴权与用户

### POST /api/auth/register

注册新租户，并创建该租户的管理员（`admin` 角色，拥有全部权限）。

请求：

```json
{
  "tenant_name": "示例公司",
  "tenant_slug": "demo",
  "username": "admin",
  "email": "admin@example.com",
  "password": "123456",
  "full_name": "张三"
}
```

- `tenant_slug` 可选；不填则按 `tenant_name` 自动生成（中文名退化为随机标识）
- 用户名规则：`^[A-Za-z0-9_]{3,64}$`；密码 6-72 字符（bcrypt 上限 72 字节）
- 响应 `201`：

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 43200,
  "user": {
    "id": 1,
    "tenant_id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "full_name": "张三",
    "is_active": true,
    "is_superuser": false,
    "created_at": "2026-10-18T02:39:39.550233Z"
  }
}
```

- 冲突：`409 / 40901`（`detail.field` 指明 `tenant_slug` 等字段）

### POST /api/auth/login

```json
{"username": "admin", "password": "123456"}
```

- 用户名在租户内唯一；若同一用户名存在于多个租户，必须附加 `tenant_slug`，否则返回
  `400 / 40001`（`detail.matches` 为匹配数量）
- 成功：`200`，响应结构同注册
- 失败：`401 / 40101`（用户不存在或密码错误，不区分以规避账号枚举）
- 账号停用：`403 / 40301`

### GET /api/auth/me

请求头：`Authorization: Bearer <token>`

```json
{
  "user": {"id": 1, "username": "admin", "tenant_id": 1, "email": "admin@example.com"},
  "roles": ["admin"],
  "permissions": ["chat:ask", "docs:read", "docs:write", "kb:read", "kb:write", "users:read", "users:write"]
}
```

### GET /api/auth/users?page=1&page_size=20

需要权限 `users:read`；返回当前租户用户，**强制 `tenant_id` 隔离**。

```json
{
  "items": [{"id": 1, "username": "admin", "email": "admin@example.com", "is_active": true}],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### POST /api/auth/users

需要权限 `users:write`；在当前租户内创建用户并分配角色。

```json
{
  "username": "member01",
  "email": "member01@example.com",
  "password": "123456",
  "full_name": "普通成员",
  "role_codes": ["member"]
}
```

- `role_codes` 缺省为 `["member"]`；角色不存在返回 `400 / 40001`
- 用户名 / 邮箱在同租户内重复返回 `409 / 40901`
- 成功：`201`，返回用户信息

## 权限模型

权限为全局目录，角色按租户隔离，用户通过角色获得权限。

| 权限码 | 说明 | admin | member |
| --- | --- | --- | --- |
| `users:read` | 查看用户 | ✅ | ❌ |
| `users:write` | 管理用户 | ✅ | ❌ |
| `kb:read` | 查看知识库 | ✅ | ✅ |
| `kb:write` | 管理知识库 | ✅ | ❌ |
| `docs:read` | 查看文档 | ✅ | ✅ |
| `docs:write` | 管理文档 | ✅ | ❌ |
| `chat:ask` | 知识库问答 | ✅ | ✅ |

权限码统一采用 `资源:动作` 形式。内置 `admin` 角色拥有全部权限，`member` 角色拥有 `kb:read`、`docs:read`、`chat:ask`。

## 知识库

### POST /api/kb

创建知识库，需要 `kb:write`；同租户内名称唯一。

```json
{"name": "测试知识库", "description": "报销制度、员工手册"}
```

成功 `201`：

```json
{
  "id": 1,
  "tenant_id": 1,
  "name": "测试知识库",
  "description": "报销制度、员工手册",
  "document_count": 0,
  "created_at": "2026-10-18T02:52:42.837396Z",
  "updated_at": "2026-10-18T02:52:42.837396Z"
}
```

名称重复：`409 / 40901`。

### GET /api/kb?page=1&page_size=20

需要 `kb:read`；返回当前租户知识库及文档数（`document_count` 只统计未删除文档）。

### GET /api/kb/{kb_id}

需要 `kb:read`；不存在或属于其它租户：`404 / 40401`。

### PATCH /api/kb/{kb_id}

需要 `kb:write`；可改 `name`、`description`，改名冲突返回 `409`。

### DELETE /api/kb/{kb_id}

需要 `kb:write`；软删除知识库及其下文档，返回 `204`。

## 文档

### POST /api/docs/upload

`multipart/form-data`，需要 `docs:write`。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | file | 是 | `.pdf` / `.docx` / `.md` / `.txt` |
| `kb_id` | int | 否 | 省略时写入当前租户的「默认知识库」（不存在则自动创建） |
| `title` | str | 否 | 默认取文件名 |

校验规则：

- 扩展名白名单 `pdf` / `docx` / `md` / `txt`，否则 `415 / 41501`（`detail.allowed_extensions`）
- 大小上限 `MAX_UPLOAD_MB`（默认 20 MB），超出 `413 / 41301`
- 空文件 `400 / 40001`
- 目标知识库不属于当前租户：`404 / 40401`
- 对象存储不可用：`502 / 50201`

成功 `201`：

```json
{
  "id": 1,
  "tenant_id": 1,
  "kb_id": 2,
  "title": "sample.pdf",
  "filename": "sample.pdf",
  "file_ext": "pdf",
  "content_type": "application/pdf",
  "size_bytes": 827,
  "checksum": "83e63639971d80...",
  "status": "pending",
  "error_message": null,
  "chunk_count": 0,
  "created_at": "2026-10-18T02:52:43.121362Z",
  "updated_at": "2026-10-18T02:52:43.581719Z"
}
```

`status` 状态机：`pending`（已上传）→ `processing`（解析中）→ `ready` / `failed`（上传后立即执行）。

### GET /api/docs?kb_id=1&page=1&page_size=20

需要 `docs:read`；按 `kb_id` 可选过滤，按 id 倒序，强制租户隔离。

### GET /api/docs/{document_id}

需要 `docs:read`；不存在或跨租户：`404 / 40401`。

### DELETE /api/docs/{document_id}

需要 `docs:write`；软删除文档并删除对象存储文件，返回 `204`。

### 对象存储布局

对象键固定为：

```text
tenants/{tenant_id}/kb/{kb_id}/docs/{document_id}/{filename}
```

后端由 `STORAGE_PROVIDER` 决定：`minio`（默认，桶 `MINIO_BUCKET`）或 `local`
（离线降级，写入 `LOCAL_STORAGE_DIR`）。桶不存在时自动创建。

## 检索与索引

### GET /api/kb/search

在指定知识库内做向量检索（pgvector 余弦相似度），需要 `kb:read`。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `kb_id` | int | 是 | 知识库 id |
| `q` | str | 是 | 查询文本（1-500 字符，**中文需 URL 编码**） |
| `top_k` | int | 否 | 返回条数，默认 `TOP_K`（5），范围 1-50 |

```powershell
# 中文查询必须 URL 编码；--data-urlencode 会自动处理，等价于
# GET /api/kb/search?kb_id=1&q=%E6%8A%A5%E9%94%80%E6%B5%81%E7%A8%8B
curl.exe -s -G "http://localhost:8000/api/kb/search" `
  --data-urlencode "kb_id=1" --data-urlencode "q=报销流程" `
  -H "Authorization: Bearer $TOKEN"
```

响应：

```json
{
  "kb_id": 1,
  "query": "报销流程",
  "top_k": 5,
  "total": 2,
  "items": [
    {
      "chunk_id": 2,
      "document_id": 2,
      "document_title": "sample.md",
      "filename": "sample.md",
      "chunk_index": 0,
      "content": "报销流程说明（样例 Markdown）...",
      "score": 0.229
    }
  ]
}
```

- `score` = `1 - 余弦距离`，越大越相关；`hash` 模式下只反映词汇重叠
- 空知识库返回 `total=0`，不报错
- 跨租户或知识库不存在：`404 / 40401`
- 缺少 `q` 或 `top_k` 越界：`422 / 40001`

### POST /api/docs/{document_id}/reindex

重新解析文档、切片并重建向量，需要 `docs:write`。

- 成功：`200`，`status=ready`，`chunk_count` 为切片数
- 解析失败（损坏文件、扫描件等）：仍返回 `200`，`status=failed`，
  `error_message` 说明原因，`chunk_count=0`
- 文档不存在或跨租户：`404 / 40401`

## 解析、切片与 Embedding

| 格式 | 解析方式 |
| --- | --- |
| `.pdf` | pypdf 逐页 `extract_text`；无文本层（扫描件）返回 42201 |
| `.docx` | python-docx 读取段落与表格（表格行用 `\|` 连接） |
| `.md` | markdown 渲染为 HTML 后去标签，保留正文 |
| `.txt` | 依次尝试 `utf-8-sig` / `utf-8` / `gb18030` / `big5` / `latin-1` |

切片：字符窗口 `CHUNK_SIZE`（默认 800），相邻重叠 `CHUNK_OVERLAP`（默认 120），
优先在段落 / 换行 / 句末标点处断开。

| Embedding Provider | 说明 |
| --- | --- |
| `hash`（默认） | 本地确定性哈希向量（md5 定位维度 + 符号，L2 归一化），无依赖零成本，只捕捉词汇重叠 |
| `openai_compatible` | 调用 `{EMBEDDING_BASE_URL}/embeddings`，需 Key / Model，维度必须等于 `EMBEDDING_DIM` |

`EMBEDDING_PROVIDER=openai_compatible` 但缺少 BASE_URL / API_KEY / MODEL 时自动降级为 `hash` 并告警。

## 问答与历史

### POST /api/chat/ask

`text/event-stream` 流式 RAG 问答，需要 `chat:ask` 权限。

请求：

```json
{"kb_id": 1, "question": "报销流程是什么？", "conversation_id": null, "top_k": 5}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `kb_id` | 是 | 知识库 id（跨租户返回 404） |
| `question` | 是 | 1-1000 字符 |
| `conversation_id` | 否 | 续聊时传入，必须属于当前用户且同一知识库 |
| `top_k` | 否 | 检索条数，默认 `TOP_K`，范围 1-20 |

SSE 事件：

| event | data |
| --- | --- |
| `message` | `{"delta": "增量文本"}` |
| `done` | `{"conversation_id", "message_id", "content_length", "citations": [...]}` |
| `error` | `{"code": 50001, "message": "生成回答失败，请稍后重试"}` |

`done.citations[n]` 字段：`index`（正文 `[n]` 对应）、`document_id`、`document_title`、
`filename`、`chunk_id`、`chunk_index`、`score`（余弦相似度）、`snippet`（片段摘要）。

```powershell
# -N 关闭缓冲，实时看到 SSE 片段
curl.exe -N -X POST http://localhost:8000/api/chat/ask `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer $TOKEN" `
  -d '{"kb_id":1,"question":"报销流程是什么？"}'
```

```text
event: message
data: {"delta": "（mock 模式）根据知识库检索到的 2 条资料"}

event: done
data: {"conversation_id":1,"message_id":2,"content_length":327,"citations":[...]}
```

行为说明：

- 检索结果为空时仍正常回答（`citations: []`，并说明资料不足）
- LLM 在首个 token 前不可用（无 Key / 429 / 网络错误）时自动降级 `mock`，流不中断
- 客户端断开（`Ctrl+C`）时保存已生成的部分回答
- 先落库 user 消息再开始流式，`done` 后再落库 assistant 消息（含 citations JSONB）

### GET /api/chat/history?page=1&page_size=20

分页返回**当前用户**的会话（按 id 倒序，附 `message_count`），需要 `chat:ask`。
严格按 `tenant_id + user_id` 隔离，其它用户 / 租户看不到。

### GET /api/chat/history/{conversation_id}

返回会话详情与全部消息（`role` 为 `user` / `assistant`，assistant 消息带 `citations`）。
会话不存在或不属于当前用户：`404 / 40401`。

## 健康检查

### GET /health

无鉴权、不依赖数据库 / Redis / MinIO / 外部模型：

```json
{"status": "ok"}
```

## curl.exe 示例（PowerShell）

```powershell
# 登录
$login = curl.exe -s -X POST http://localhost:8000/api/auth/login `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","password":"123456"}'
$token = ($login | ConvertFrom-Json).access_token

# 当前用户
curl.exe -s http://localhost:8000/api/auth/me -H "Authorization: Bearer $token"

# 用户列表
curl.exe -s "http://localhost:8000/api/auth/users?page=1&page_size=10" -H "Authorization: Bearer $token"
```
