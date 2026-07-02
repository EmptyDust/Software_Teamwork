# 项目文档索引

本文档作为 `docs/` 目录的阅读入口，用于区分需求说明、架构契约和协作维护文档。

## 推荐阅读顺序

1. 先读 [整体需求分析](requirements-analysis/overall-requirements-analysis.md)，了解完整业务范围。
2. 再读 [服务边界矩阵](architecture/service-boundaries.md) 和 [当前能力矩阵](architecture/current-capability-matrix.md)，确认各服务职责归属和已落地能力。
3. 实现服务或前端工程能力前，阅读 [技术选型基线](architecture/technology-decisions.md)。
4. 开始前后端联调前，阅读 [前后端集成契约](architecture/frontend-backend-contract.md)、[本地联调运行手册](runbooks/local-integration.md) 和 [Gateway OpenAPI 契约](services/gateway/api/public.openapi.yaml)。
5. 提 PR 前，阅读 [测试策略](testing/strategy.md)，选择与改动范围匹配的检查。
6. 需要生产或准生产单机 Compose 基线时，阅读 [生产/准生产部署基线](../deploy/production-baseline.md)。
7. 本地 Docker 构建变慢、镜像源异常或 Compose 启动卡住时，阅读 [Docker 构建环境与镜像源](runbooks/docker-build-environment.md)。中国大陆网络优先从 `deploy/.env.china.example` 和 `python3 scripts/check_docker_environment.py --profile all --clean-env` 开始。
8. 需要实现具体后端服务时，阅读对应服务接口文档。
9. 新增或调整文档时，先读 [文档维护工作流](collaboration/documentation-workflow.md)，确认内容应落在架构、协作还是服务细则中。
10. 创建或认领 GitHub Issue 任务、参与协作、分支、PR 或仓库维护时，阅读协作维护文档。

## 架构与接口契约

| 文档 | 内容 |
| --- | --- |
| [整体需求分析](requirements-analysis/overall-requirements-analysis.md) | 智能知识管理与报告生成系统的业务范围、用户角色、核心模块、非功能要求和分期范围。 |
| [Discussion #48 决策同步清单](requirements-analysis/decision-sync-checklist.md) | 整体需求分析和 API 契约中原先未定稿问题的确认结果。 |
| [服务边界矩阵](architecture/service-boundaries.md) | `gateway`、`auth`、`file`、`knowledge`、`qa`、`document`、`ai-gateway` 的职责边界、公开契约状态和缺失契约登记。 |
| [当前能力矩阵](architecture/current-capability-matrix.md) | 根据当前 `develop`、今日 issue/PR 和实现说明汇总已实现、部分实现、占位和缺失能力。 |
| [系统链路条件覆盖文档](architecture/system-link-condition-coverage.md) | 按主要用户、管理员和系统后台链路记录跨服务参与方、正常路径、条件分支、状态输出和当前实现缺口。 |
| [技术选型基线](architecture/technology-decisions.md) | 后端数据库访问、迁移、日志、HTTP、配置、队列、认证、前端 API client、测试、CI、观测和 DOCX/MCP 等工程技术选型。 |
| [Gateway 服务规划](services/gateway/README.md) | Gateway 的设计原则、公开 API、认证上下文、响应约定和后续扩展。 |
| [Gateway 权限矩阵](services/gateway/docs/permission-matrix.md) | Gateway 公开入口、认证缓存、角色权限透传和 owner service 复核边界。 |
| [Gateway 实现说明](services/gateway/docs/implementation.md) | `services/gateway/` 当前实现状态、契约对齐、缺口和最近检查记录。 |
| [Auth 服务接口文档](services/auth/README.md) | 用户、会话、权限上下文和 auth 内部服务接口草案。 |
| [Auth 权限矩阵](services/auth/docs/permission-matrix.md) | Auth 角色、权限字符串、内部 API 授权和会话权限刷新口径。 |
| [Auth 实现说明](services/auth/docs/implementation.md) | `services/auth/` 当前实现状态、契约对齐、缺口和最近检查记录。 |
| [File 服务接口文档](services/file/README.md) | 后端内部基础文件对象、元数据、原文件内容读取和 file 内部服务接口草案。 |
| [File 权限矩阵](services/file/docs/permission-matrix.md) | File 内部服务认证、owner service 授权责任和公开资源复用边界。 |
| [File 数据模型文档](services/file/docs/data-models.md) | File 模块基础文件对象元数据、对象存储引用、删除清理和服务间 `file_ref` 约束。 |
| [File 实现说明](services/file/docs/implementation.md) | `services/file/` 当前实现状态、契约对齐、缺口和最近检查记录。 |
| [Knowledge 服务接口文档](services/knowledge/README.md) | 知识库、文档处理状态、切片、向量索引和检索接口契约。 |
| [Knowledge 权限矩阵](services/knowledge/docs/permission-matrix.md) | 知识库、文档、检索和 parser config 的角色/权限矩阵。 |
| [Knowledge 数据模型文档](services/knowledge/docs/data-models.md) | Knowledge 模块知识库、文档、处理任务、切片、Qdrant payload 和运行时配置逻辑模型。 |
| [Knowledge 实现说明](services/knowledge/docs/implementation.md) | `services/knowledge/` 当前实现状态、契约对齐、缺口和最近检查记录。 |
| [Parser Runtime 服务文档](services/parser/README.md) | 内部文档解析运行时、Python/PaddleOCR 边界和 `/internal/v1/parsed-documents` 契约入口。 |
| [Parser Runtime 权限矩阵](services/parser/docs/permission-matrix.md) | Parser 内部服务认证、调用方白名单和 Knowledge 授权责任。 |
| [Parser Runtime 实现说明](services/parser/docs/implementation.md) | `services/parser/` 当前实现状态、契约对齐、缺口和最近检查记录。 |
| [QA 服务接口文档](services/qa/README.md) | 智能问答 Agent Host、会话、消息、ReAct 循环、MCP 工具调用、SSE、引用、配置、检索测试和统计接口说明。 |
| [QA 权限矩阵](services/qa/docs/permission-matrix.md) | QA 会话、消息、回答运行、引用、配置、检索测试、指标和工具调用的权限边界。 |
| [QA 数据模型文档](services/qa/docs/data-models.md) | QA 模块逻辑数据模型、核心关系、写入流程、索引和安全约束。 |
| [QA 实现说明](services/qa/docs/implementation.md) | `services/qa/` 当前实现状态、契约对齐、缺口和最近检查记录。 |
| [AI Gateway 服务接口文档](services/ai-gateway/README.md) | 内部模型配置、OpenAI-compatible chat/function calling/embedding、rerank 和 provider 错误归一化接口草案。 |
| [AI Gateway 权限矩阵](services/ai-gateway/docs/permission-matrix.md) | 管理端 model profile 权限、内部模型调用服务认证和 provider 凭据保护边界。 |
| [AI Gateway 数据模型文档](services/ai-gateway/docs/data-models.md) | AI Gateway 模型 profile、provider 凭据、配置审计和脱敏调用日志数据模型。 |
| [AI Gateway Provider Adapter 说明](services/ai-gateway/docs/provider-adapters.md) | Chat、embedding、rerank provider adapter 的 profile 解析、响应校验、脱敏和 usage aggregate 约束。 |
| [AI Gateway 实现说明](services/ai-gateway/docs/implementation.md) | `services/ai-gateway/` 当前实现状态、契约对齐、缺口和最近检查记录。 |
| [Document 服务接口文档](services/document/README.md) | 报告模板、素材、报告记录、大纲、章节、生成任务、报告文件、配置、统计和 MCP 工具边界说明。 |
| [Document 权限矩阵](services/document/docs/permission-matrix.md) | 报告模板、素材、报告、任务、文件、settings、统计和日志的权限矩阵。 |
| [Document 数据模型文档](services/document/docs/data-models.md) | 报告生成逻辑数据模型、实体关系、字段约定和存储约束。 |
| [Document 生成工作流](services/document/docs/generation-workflow.md) | 报告 job、attempt、event、worker、AI Gateway、File Service 和 DOCX 创建的目标流程与当前缺口。 |
| [Document 实现说明](services/document/docs/implementation.md) | `services/document/` 当前实现状态、契约对齐、缺口和最近检查记录。 |
| [前后端集成契约](architecture/frontend-backend-contract.md) | 前端调用 gateway 的入口、认证、请求/响应、错误、分页、SSE 和 mock 约定。 |
| [Gateway OpenAPI 契约](services/gateway/api/public.openapi.yaml) | 当前稳定的 gateway 公开 API 机器可读契约。 |
| [Gateway Active API Owner Map](services/gateway/docs/active-api-owner-map.md) | 从 Gateway OpenAPI 审计得到的 active API 清单、owner service、tag、operationId 和认证要求。 |
| [AI Gateway OpenAPI 契约](services/ai-gateway/api/internal.openapi.yaml) | AI Gateway 内部服务机器可读契约；前端不得直接调用。 |
| [Parser Runtime 公开契约](services/parser/api/public.openapi.yaml) | Parser 无 Gateway 公开 API 的机器可读声明。 |
| [Parser Runtime 内部契约](services/parser/api/internal.openapi.yaml) | Parser 内部服务机器可读契约；供 Knowledge ingestion、QA 会话附件解析等后端服务调用。 |

## 运行与测试

| 文档 | 内容 |
| --- | --- |
| [本地联调运行手册](runbooks/local-integration.md) | 根级本地/演示 Compose、服务级 Compose、host-run 依赖、冒烟顺序、已知缺口和 PR 前联调判断。 |
| [生产/准生产部署基线](../deploy/production-baseline.md) | 单机 Compose 生产/准生产基线、环境变量模板、持久化卷、secret 注入、启动顺序、健康检查、升级和回滚说明。 |
| [Docker 构建环境与镜像源](runbooks/docker-build-environment.md) | Docker build 优先级、镜像源、Go sumdb、BuildKit cache、Compose 镜像覆盖和 Docker daemon mirror 排障。 |
| [测试策略](testing/strategy.md) | Go、migration、Gateway contract、前端、env-gated integration tests 和跨服务 smoke 的当前测试策略。 |

## 协作与维护

| 文档 | 内容 |
| --- | --- |
| [任务 Issue 与 Project 流程](collaboration/task-issue-project-workflow.md) | 从任务缺口到 GitHub Issue / Project 的完整发布流程，包括模板入口、编号、依赖、Project 同步和 View 归属。 |
| [前端协作工作流](collaboration/frontend-workflow.md) | 前端目录、Bun 命令、检查、PR 和 CI 建议。 |
| [仓库维护设置](collaboration/repository-settings.md) | GitHub label、分支保护、PR Guard、Auto Label 和 Commitlint 设置。 |
| [文档维护工作流](collaboration/documentation-workflow.md) | `docs/` 内容归属、接口文档更新顺序、文档/代码出入判定和服务文档检查清单。 |

仓库级分支、PR、提交和合并策略以根目录 [CONTRIBUTING.md](../CONTRIBUTING.md) 为准。

## 契约状态

当前已稳定的公开契约和已形成草案的内部契约包括：

- Gateway 健康检查。
- Auth 相关用户与会话接口。
- File 内部基础文件对象、元数据和原文件内容读取接口。
- Knowledge-owned 知识库、文档上传、文档处理状态、原文件内容、切片详情和知识检索接口。
- Parser 内部文档解析运行时接口草案。
- Document-owned 报告模板、素材、报告记录、大纲、章节、生成任务、报告文件、配置、统计和日志接口。
- QA-owned 会话、消息、非流式/流式回答、SSE 事件回放、引用、配置、检索体验测试和统计接口。
- AI Gateway 内部模型配置、OpenAI-compatible chat/function calling/embedding 和 OpenAI-style rerank 接口草案。

所有 planed public API 已转为 active contracts，无待补齐契约。

新增或调整公开接口或内部模型接口时，需要同步更新：

- [Gateway OpenAPI 契约](services/gateway/api/public.openapi.yaml)
- [前后端集成契约](architecture/frontend-backend-contract.md)
- [服务边界矩阵](architecture/service-boundaries.md)
- 对应服务接口文档
- 对应服务 `docs/services/<service>/api/public.openapi.yaml` 或 `internal.openapi.yaml`：`public` 记录该服务拥有的 public/Gateway-facing 设计面，可通过 `servers: /api/v1` 加相对资源 path 表达服务本地 public 草案；只有已经进入 [Gateway OpenAPI 契约](services/gateway/api/public.openapi.yaml) active paths 的内容才是前端稳定公开契约，未进入 Gateway active paths 的内容必须在服务级 public 文件或 Markdown 中标为 candidate/draft；`internal` 只记录服务间 `/internal/v1/**`、服务本地运行路径和健康检查契约。没有公开路径的内部服务应提供空 `public.openapi.yaml` 明确声明。
- 涉及内部模型调用、provider 配置或调用记录时，同步更新 [AI Gateway 服务接口文档](services/ai-gateway/README.md)、[AI Gateway 数据模型文档](services/ai-gateway/docs/data-models.md) 和 [AI Gateway OpenAPI 契约](services/ai-gateway/api/internal.openapi.yaml)
- 涉及 provider adapter、embedding、rerank 或模型调用摘要时，同步更新 [AI Gateway Provider Adapter 说明](services/ai-gateway/docs/provider-adapters.md)
- 涉及本地 Compose、环境变量、跨服务 smoke 或 PR 前检查策略时，同步更新 [本地联调运行手册](runbooks/local-integration.md) 和 [测试策略](testing/strategy.md)

契约语义变更必须先交管理组决策。实现 PR 可以更新 implementation 文档记录当前事实，但不能用“代码已经这样写了”直接覆盖 Gateway OpenAPI、服务边界、数据模型或已确认需求。

跨服务编写标准不要放进单个服务细则：技术选型归 [技术选型基线](architecture/technology-decisions.md)，REST/OpenAPI/响应错误/SSE/上传归 [前后端集成契约](architecture/frontend-backend-contract.md)，服务边界归 [服务边界矩阵](architecture/service-boundaries.md)，协作流程归 [文档维护工作流](collaboration/documentation-workflow.md) 和其他协作文档。

实现状态、代码与契约出入、临时 memory/mock 后端和最近检查记录统一写入各服务的 `docs/implementation.md`。README 和架构文档只保留契约、边界、稳定规则和入口链接，避免重复维护实现缺口。
