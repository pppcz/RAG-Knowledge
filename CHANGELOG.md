# 变更记录

本文件记录各版本的对外可见变化。提交粒度与规范见
[docs/development.md](docs/development.md)。

## 1.0.0 - 2026-10-22

首个可用版本。

### 新增

- **账号体系**：租户注册、用户登录、JWT 鉴权、刷新与登出；基于角色与权限码的 RBAC，
  多租户数据隔离
- **知识库**：创建、编辑、删除、列表；按租户隔离，支持默认知识库
- **文档管理**：上传 PDF / Word / Markdown / TXT，扩展名与大小校验，checksum 去重；
  自动解析、切片、向量化并写入 pgvector，支持重建索引与失败重试
- **检索**：pgvector 余弦相似度检索，HNSW 索引，按租户与知识库过滤，软删除隔离
- **RAG 问答**：检索 top_k 切片拼装上下文，SSE 流式输出，回答附带引用来源
  （文档名、切片序号、片段内容），会话与消息持久化
- **模型接入**：LLM 支持 `mock` 与 OpenAI 兼容接口；Embedding 支持 `hash` 与
  OpenAI 兼容接口，两者均可通过 `.env` 切换
- **前端**：登录、知识库、文档、问答、历史五个页面，Vue3 + TypeScript + Element Plus，
  问答页支持流式渲染与引用展开
- **部署**：多阶段 Dockerfile，compose 编排 postgres / redis / minio / backend / frontend，
  Nginx 托管静态资源并反代 API（SSE 不缓冲），全部服务配置健康检查
- **工程化**：Alembic 迁移（0001 baseline → 0005 chat）、pytest 测试套件、
  ruff 静态检查、GitHub Actions CI（后端检查 + 前端构建 + compose 校验）、
  `scripts/bootstrap.ps1` / `verify.ps1` / `start-docker.ps1` 运维脚本

### 说明

- 默认 `LLM_PROVIDER=mock`、`EMBEDDING_PROVIDER=hash`，无需任何 API Key 即可跑通全流程
- `hash` 模式只反映词汇重叠，语义检索质量需切换真实 Embedding 模型并重建向量
- PostgreSQL 映射到宿主 5433，原因见 [docs/env.md](docs/env.md)

### 已知限制

- Redis 目前仅接入，未用于缓存与限流
- 文档上传后同步索引，超大文件会拉长接口耗时，尚未引入任务队列
- 向量维度固定 1536，更换 Embedding 模型需新增迁移重建列与索引
- 前端未做组件级单元测试
