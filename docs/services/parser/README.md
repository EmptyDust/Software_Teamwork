# Parser Runtime Service

Parser 是内部文档解析运行时服务，由 Knowledge ingestion 调用，不通过
public gateway API 暴露给前端。

## 职责边界

Parser 只负责把原始文档 bytes 转成规范化解析结果。首个目标后端是
Python + PaddleOCR，用于扫描 PDF、图片、表格、印章和 OCR-heavy 版式。

Knowledge 仍然负责：

- 知识库文档资源、processing job 和公开文档状态。
- 从 File Service 获取原始文件引用和做业务可见性校验。
- 切片、chunk 持久化、embedding 生成、Qdrant 写入和检索 hydrate。
- 管理端 parser runtime configuration 的公开 gateway 契约。

Parser 不保存知识库、文档、chunk、embedding、Qdrant point 或权限事实；也不得返回
object key、bucket、内部 URL、签名 URL、provider body、API key、prompt 或完整调试日志。

## 内部 API

Parser 的服务间契约是：

```text
POST /internal/v1/parsed-documents
```

机器可读契约分为两份：

- [`api/public.openapi.yaml`](api/public.openapi.yaml)：Parser 没有 Gateway 公开路径，前端、管理端和 MCP 调用方不得直连 Parser。
- [`api/internal.openapi.yaml`](api/internal.openapi.yaml)：Parser 服务间内部契约，当前只供 Knowledge ingestion 调用。

Knowledge 调用 Parser 时必须传递 `X-Request-Id`、`X-Caller-Service: knowledge`
和必要的内部 service token。`X-User-Id` 只作为审计上下文，不作为 Parser 里的授权事实。

## 运行时方向

Parser 目标实现是 Python/PaddleOCR。Go 服务只通过 HTTP 调用 Parser，不应在
Knowledge 进程中引入 PaddleOCR、PaddlePaddle、OpenCV、CUDA 或模型加载依赖。

## 当前状态

本文档和 OpenAPI 只定义服务边界与契约。Parser runtime、Python packaging、
Docker image、PaddleOCR 模型加载、GPU/CPU 调度和部署 wiring 仍待后续实现任务落地。
