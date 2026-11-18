# Knowledge Hub — Version Roadmap

> 本文档是 Knowledge Hub 的版本规划真源。总体架构与技术选型见
> [enterprise-knowledge-hub-architecture-version-plan.md](./enterprise-knowledge-hub-architecture-version-plan.md)。
> 跨项目版本号与依赖边界见仓库根 [VERSIONS.md](../../VERSIONS.md)。

**Project:** Enterprise Knowledge Hub

**Current Version:** v0.2.0（MVP：文档知识库 + 混合检索）

**Next Target:** v0.3.0 Multi Source

**Architecture:** 独立知识基础设施（与 Capability Registry 同级：HTTP / MCP 接入 Agent Runtime）

---

# 1. 规划原则

架构原文第 20 节的版本号与第 30 节「推荐开发顺序」不一致。本路线图**按交付顺序编号**，
原文 V 号保留为里程碑别名。

| 原则 | 落地 |
|---|---|
| 文档是事实源 | 先跑通 Document → Markdown → Chunk → 检索；图是派生索引 |
| 不要一开始做 Graph | Neo4j / Graph RAG 不早于 v0.4.0 |
| 不要 Vector Only | v0.2.0 补齐 BM25 + Metadata + Rerank，这才是第一个有竞争力的检索版本 |
| Source 与 Base 解耦 | v0.1 只做 Upload（加可选本地 Folder）；多源 Connector 放到 v0.3 |
| Hub 独立于 Runtime | 不把知识处理塞进 `platformagent`；平台只做 adapter |
| 所有知识可追溯 | 从 v0.1 起 chunk 必须带回 `document_id` / 页码或段落偏移 |
| **租户 / 用户权限最后设计** | v0.1–v0.6 **不做** Tenant、User、RBAC、Grant、按身份过滤检索。资源模型先按 Knowledge Base → Folder → Document 长出来；鉴权放到 v0.7 |

前期与 Capability Registry 现状类似：管理 API 可先无用户鉴权，内部 Retrieve 用共享密钥即可。表结构不要过早铺 `tenant_id` 强制过滤——v0.7 再决定是 Hub 自建 IAM，还是信任平台 JWT。

**与 Platform 0.4.0 的关系**：平台现有提案是「进程内、纯文本/Markdown、pgvector、PostgreSQL 邻接表」。那是验证 Runtime `Knowledge`/`Retriever` 端口的薄闭环，**不是**本路线图的 Knowledge Hub。Hub 按 Capability 模式独立发版；平台通过 HTTP 消费。二者不要做成两套互相分叉的完整知识库。

---

# 2. Roadmap

| Version | Milestone | 原文别名 | Status |
|----------|-----------|----------|--------|
| v0.1.0 | Document Knowledge Base | 原 V0.1（去掉把 BM25 当产品能力） | ✅ 已交付 · MVP 上半 |
| v0.2.0 | Hybrid Retrieval | 原 V0.4 | ✅ 已交付 · MVP 下半 |
| v0.3.0 | Multi Source | 原 V0.2 | ⏳ Planned |
| v0.4.0 | Knowledge Graph | 原 V0.5 | ⏳ Planned |
| v0.5.0 | Graph RAG | 原 V0.6 | ⏳ Planned |
| v0.6.0 | Agentic Knowledge | 原 V0.7 | ⏳ Planned |
| v0.7.0 | Access Control | 原 V0.3 Enterprise | ⏳ Planned · **最后设计** |
| v1.0.0 | Enterprise Knowledge Infrastructure | 原 V1 | 🎯 Target |

```text
v0.1 Document KB     上传 / 解析 / OCR / Chunk / Vector Search / 薄 Retrieve API
        ↓
v0.2 Hybrid Retrieval     BM25 + Metadata Filter + Reranker   ← 第一个有竞争力的检索
        ↓
v0.3 Multi Source     Folder / NAS / S3 / Git / Web + 增量同步
        ↓
v0.4 Knowledge Graph     Entity / Relation / Resolution / Neo4j
        ↓
v0.5 Graph RAG     Vector + Graph 融合与多跳
        ↓
v0.6 Agentic Knowledge     动态检索策略 / Knowledge MCP / Runtime 集成
        ↓
v0.7 Access Control     Tenant / User / RBAC / 检索鉴权   ← 最后设计
        ↓
v1.0 Enterprise KI     API 冻结 + 私有化验收
```

---

# 3. MVP（v0.1 + v0.2）

面向简历 / Demo / 后续商业化的第一阶段，对齐原文第 29 节，但收紧以免把 MVP 做成 V1：

- **做**：Upload、可选本地 Folder、Parser、OCR、Markdown 中间层、Chunk、Embedding、Vector、BM25、Rerank、带出处的 Retrieve API。
- **不做**：NAS / S3 / Git / 全量 Web 爬取、Neo4j、Agentic Retrieval、完整 MCP Server、租户/用户权限、Keycloak、ES。
- **MCP**：原文 MVP 图里有 MCP；本规划把它放到 v0.6。v0.1 只提供 REST Retrieve，足够平台 adapter 联调。

技术基线（第一阶段不引入 Elasticsearch / Neo4j）：

```text
FastAPI + PostgreSQL + MinIO + Redis + Qdrant
Docling / MinerU / PaddleOCR
BGE 或 Qwen Embedding + BGE Reranker
React + Docker Compose
```

---

# 4. v0.1.0 — Document Knowledge Base

## Goal

把「上传文件 → 可搜索、可引用」完整跑通。这是第一个可 Demo 版本。

## In

- Knowledge Base / Folder / Document CRUD（无账号体系；单机管理即可）
- 格式：PDF / Word / Excel / PPT / TXT / Markdown / JPG / PNG / 扫描 PDF
- Parser + OCR → Markdown 中间层
- Chunk + Embedding → Qdrant
- Vector Search，结果带回 document / chunk 出处
- 内部 Retrieve API：`search(query, kb_ids, top_k)` → chunks + evidence
- 对象存储（MinIO）保存原文；PostgreSQL 保存元数据与作业状态
- 文档替换可重建索引（作业状态机）；不必上多租户版本权限

## Out

- 多知识源 Connector、租户/用户/RBAC、Reranker 产品化、知识图谱、MCP

## 验收

1. 上传一份扫描 PDF 与一份 Word，均可检索到原文片段。
2. 每条命中都能追溯到文件与 chunk 偏移。
3. `docker compose up` 后可本地 Demo，无需外部 SaaS（LLM / Embedding 可配置本地或云）。

---

# 5. v0.2.0 — Hybrid Retrieval

## Goal

第一个明显具有技术竞争力的检索版本。

## In

- Query Analyzer（简单意图：关键词 / 语义 / 过滤条件）
- Vector + BM25（Qdrant sparse 或等价，不引入 ES）
- Metadata Filter（kb / folder / 文件类型 / 时间）——**按资源属性过滤，不按用户身份过滤**
- Reranker（BGE / Cross-Encoder）
- Context Builder：去重、截断、出处拼装

## Out

- Graph Search、多跳、Agent 自选策略、按角色裁剪检索结果

## 验收

同一查询在「纯向量」与「Hybrid + Rerank」下可对比；编号、专有名词、扫描件文字三类样例至少各 1 条 hybrid 明显优于纯向量。

---

# 6. v0.3.0 — Multi Source

## Goal

从文件知识库升级为企业统一知识入口。Source 与 Base 解耦：一个 Knowledge Base 可挂多个 Source。

## In

- Connector 协议：`connect / validate / discover / fetch / sync / delete / close`
- Folder、NAS、S3、Git、Web（受控 URL，不做全网爬虫）
- 同步：Manual / Scheduled / Incremental / Delete Sync
- 连接凭据可加密存放（这是 Source 的密钥，不是用户权限模型）
- Database / API / MCP Source **不在本期**（过宽，放到 v0.6 或 v1 补丁）

## 验收

同一 KB 同时挂 Upload + Folder + S3；远端删除文件后增量同步能下线对应 chunk，检索不再命中。

---

# 7. v0.4.0 — Knowledge Graph

## Goal

正式引入图。图是派生索引，不是事实源。

## In

- Entity / Relation 抽取与校验
- Entity Resolution
- Neo4j 写入；每条边可追溯 `source_document` / `source_chunk` / `confidence` / `model_version`
- Graph Search API + 只读可视化

## Out

- 不把 LLM 抽取结果当真理；矛盾来源并存
- Agent 不写图

## 验收

给定两份文档中的同一实体别名能合并；任意图边能点回原文 chunk。

---

# 8. v0.5.0 — Graph RAG

## Goal

解决纯 Vector RAG 难以回答关系与多跳问题。

## In

- Vector + Keyword + Graph 三路召回
- Result Fusion → Rerank → Context Builder
- 有界多跳（建议默认 2 跳，限制节点/边数）

## 验收

准备一套「A 的上级是谁 / A 与 B 通过什么项目关联」类问题；Graph RAG 能给出带出处的答案，纯向量不能或明显更差。

---

# 9. v0.6.0 — Agentic Knowledge

## Goal

Agent 按问题类型选择检索策略，Knowledge Hub 成为 Runtime 的统一知识后端。

## In

- Agentic Retrieval：简单→Vector，精确编号→Keyword，关系→Graph，复杂→Hybrid，多跳→Graph+Vector
- Knowledge MCP（search / read document / entity context）
- 完整 Knowledge API / SDK
- Platform adapter：实现 Ouroboros `Knowledge`/`Retriever`，经共享密钥调 Hub；与 Capability 的集成方式对称
- Database / API / MCP Source 可在本期补（若 v0.3 未做）

本期检索范围仍由调用方传入 `kb_ids`，Hub **不**按用户身份裁剪。

## 验收

平台一次 Run 能绑定若干 KB 并完成检索；MCP 可被外部 Agent 只读使用。

---

# 10. v0.7.0 — Access Control（最后设计）

## Goal

在文档管道、检索、图谱、Agent 接入都跑通之后，再设计租户与用户权限。避免前期 schema 被 IAM 绑死。

## In（本期才定案，前期不预支）

- Tenant / Workspace / User / Department / Role
- RBAC + 资源 Grant；检索管道按身份过滤
- 审计：谁导入、谁检索、谁改权限
- 与平台 IAM 对齐：独立账号或信任平台 JWT，二选一写进本期设计，禁止两套互斥用户体系长期并存
- 跨租户资源返回 404 不返回 403（若采用多租户）

## Out

- 不回溯改 v0.1–v0.6 的检索语义，只加授权层
- Keycloak 可作为可选项，不是硬依赖

## 验收

同一 KB 对未授权调用方不可检索；授权调用方结果与 v0.6 一致（权限是开关，不改变排序与出处）。

---

# 11. v1.0.0 — Enterprise Knowledge Infrastructure

## Goal

对外契约冻结，可私有化验收。

## In

- API / MCP 兼容性承诺
- 观测（OTel / 指标 / 检索质量抽样）
- Compose → Kubernetes 部署文档
- 安全：凭据、PII 脱敏、审计导出

## 产品形态

Capability Registry 管「Agent 能做什么」；Knowledge Hub 管「Agent 知道什么」；
Agent Runtime 管「如何思考与执行」；Brain 管「当前记住什么」。

---

# 12. 明确不做（全线默认）

| 不做 | 原因 |
|---|---|
| 第一阶段上 Elasticsearch | 与 PG + Qdrant + Redis 叠四套搜索/存储，运维过重 |
| 把知识处理做进 `platformagent` | 与 Capability 已验证的独立服务边界冲突 |
| v0.4 之前上 Neo4j | 图必须建立在稳定文档管道上 |
| v0.7 之前做租户 / 用户 / RBAC | 权限最后设计，避免绑死资源模型 |
| 全网爬虫 / 任意 URL | SSRF 与版权；Web Source 只允许白名单 |
| Agent 写知识图谱 | 图是索引，写入走导入作业 |
| 用对话记忆冒充业务知识 | `vector_memories` 仍是 Brain，不与 Hub 混表 |

---

# 13. 建议的平台对齐

| 平台动作 | 时机 |
|---|---|
| 若只为打通 Runtime 端口：保留 Platform 0.4.0 的**薄**文本知识闭环，并写明「将被 Hub 替换」 | 与 Hub v0.1 并行时 |
| 若 Hub v0.1 能赶上平台下一迭代：Platform 0.4.0 改为 adapter，**不要**再做第二套解析/索引 | 推荐 |
| 平台侧知识授权 | 等 Hub v0.7；此前 Run 只绑定 `kb_ids` |
| Console 知识库页面 | 随 Hub 管理端或平台代理 API，不单独发版 |
| git tag | 开工后使用 `knowledge-v0.1.0`，与 `capability-v0.3.0` 同级 |
