# Enterprise Knowledge Hub
## 企业统一知识中心：总体架构、技术选型与版本规划

> 文档版本：V1.0  
> 定位：企业级、可私有化部署、可扩展、Agent 原生的统一知识基础设施

---

# 1. 产品定位

Enterprise Knowledge Hub（企业统一知识中心）不是简单的 RAG 知识库，而是一套统一管理企业知识来源、文档、结构化知识、知识关系和检索能力的基础设施。

核心目标：

- 私有化部署
- 支持多种知识来源
- 支持各种常见文档
- 支持扫描件与 OCR
- 支持知识上传、同步、增量更新
- 支持 Vector + Keyword + Metadata Hybrid Retrieval
- 支持知识图谱
- 支持 Graph RAG
- 支持 Agentic Retrieval
- 支持 API / SDK / MCP
- 支持企业权限与审计
- 可以作为 Agent Runtime 的统一知识基础设施

核心定位：

> Capability Registry 管“Agent 能做什么”
>
> Knowledge Hub 管“Agent 知道什么”
>
> Agent Runtime 管“Agent 如何思考、决策和执行”
>
> Brain 管“Agent 当前记住什么”

---

# 2. 与 Enterprise Agent Platform 的整体关系

```text
┌──────────────────────────────────────────────────────────────────────┐
│                     Enterprise AI Platform                           │
│                                                                      │
│   ┌──────────────────────┐       ┌──────────────────────────────┐   │
│   │   Capability Registry │       │      Knowledge Hub           │   │
│   │                      │       │                              │   │
│   │  Tool                │       │  Knowledge Base              │   │
│   │  Skill               │       │  Document                    │   │
│   │  MCP                 │       │  Knowledge Source             │   │
│   │  Permission          │       │  Knowledge Graph              │   │
│   └──────────┬───────────┘       └──────────────┬───────────────┘   │
│              │                                  │                   │
│              └────────────────┬─────────────────┘                   │
│                               ↓                                     │
│                    ┌────────────────────┐                           │
│                    │    Agent Runtime   │                           │
│                    │                    │                           │
│                    │ Agent / Workflow   │                           │
│                    │ Planning / Memory  │                           │
│                    └─────────┬──────────┘                           │
│                              │                                      │
└──────────────────────────────┼──────────────────────────────────────┘
                               ↓
                        LLM / MCP / Tools
```

---

# 3. Knowledge Hub 总体架构

```text
┌───────────────────────────────────────────────────────────────┐
│                       Knowledge Hub                           │
├───────────────────────────────────────────────────────────────┤
│ ① Access Layer                                                │
│                                                               │
│ Web UI │ OpenAPI │ SDK │ MCP │ Agent API                    │
├───────────────────────────────────────────────────────────────┤
│ ② Knowledge Management                                        │
│                                                               │
│ Workspace │ Knowledge Base │ Folder │ Document │ Permission │
├───────────────────────────────────────────────────────────────┤
│ ③ Knowledge Source                                             │
│                                                               │
│ File │ Folder │ NAS │ S3 │ Web │ Git │ DB │ API │ MCP       │
├───────────────────────────────────────────────────────────────┤
│ ④ Document Intelligence                                        │
│                                                               │
│ Parser │ OCR │ Layout │ Table │ Image │ Structure │ Clean   │
├───────────────────────────────────────────────────────────────┤
│ ⑤ Knowledge Processing                                         │
│                                                               │
│ Chunk │ Metadata │ Entity │ Relation │ Summary │ Embedding  │
├───────────────────────────────────────────────────────────────┤
│ ⑥ Knowledge Index                                              │
│                                                               │
│ Vector │ BM25 │ Graph │ Metadata │ Full Text                │
├───────────────────────────────────────────────────────────────┤
│ ⑦ Retrieval Engine                                             │
│                                                               │
│ Query Analysis → Hybrid Search → Graph Search → Rerank       │
│ → Context Builder → Result                                   │
└───────────────────────────────────────────────────────────────┘
```

---

# 4. 核心设计原则

## 4.1 Knowledge Source 与 Knowledge Base 解耦

不要设计成：

```text
Knowledge Base
    ↓
Upload File
```

应该设计成：

```text
Knowledge Source
       ↓
Ingestion Pipeline
       ↓
Knowledge Base
```

一个 Knowledge Base 可以组合多个数据源。

例如：

```text
Sales Knowledge Base
│
├── Local Folder
├── NAS
├── S3
├── CRM Database
├── Git Repository
├── Web
└── DingTalk / MCP
```

---

# 5. Knowledge Source 架构

统一抽象：

```python
class KnowledgeSource:

    connect()

    validate()

    discover()

    fetch()

    sync()

    delete()

    close()
```

实现：

```text
LocalFileSource
FolderSource
NASSource
S3Source
WebSource
GitSource
DatabaseSource
APISource
DingTalkSource
ConfluenceSource
NotionSource
MCPSource
```

数据同步模式：

```text
Manual Sync
Scheduled Sync
Incremental Sync
Delete Sync
```

---

# 6. 文档处理架构

文档处理是 Knowledge Hub 的核心能力之一。

```text
                    Document
                       │
                       ↓
                File Detection
                       │
          ┌────────────┼────────────┐
          ↓            ↓            ↓
       Text PDF     Scanned PDF    Image
          │            │            │
          ↓            ↓            ↓
       Parser         OCR        OCR/VLM
          │            │            │
          └────────────┼────────────┘
                       ↓
                  Layout Analysis
                       │
          ┌────────────┼────────────┐
          ↓            ↓            ↓
        Text         Table        Image
          │            │            │
          └────────────┼────────────┘
                       ↓
                 Structure Parser
                       ↓
                  Clean / Normalize
                       ↓
                   Markdown
                       ↓
                 Chunk Generator
                       ↓
              ┌────────┴────────┐
              ↓                 ↓
         Embedding         Entity Extraction
              ↓                 ↓
         Vector Index       Graph Builder
```

原则：

> 不从零开发 OCR、PDF、Excel、PPT 解析器，采用统一 Parser Interface + 多解析器策略。

建议组件：

- Apache Tika
- Docling
- MinerU
- PaddleOCR
- Unstructured
- 自定义 Parser

---

# 7. Markdown 中间层

不要直接：

```text
PDF → Chunk → Vector
```

建议：

```text
Original File
      ↓
Parser / OCR
      ↓
Structured Document
      ↓
Markdown
      ↓
Chunk
      ↓
Embedding
```

原始文件、Markdown、Chunk、Embedding 分层保存。

这样以后：

- Chunk 策略变化
- Embedding 模型变化
- Reranker 变化
- Graph Extraction 策略变化

都可以从 Markdown 重新构建，而不需要重新 OCR。

---

# 8. 数据存储架构

推荐：

```text
                         Knowledge Hub
                              │
              ┌───────────────┼────────────────┐
              ↓               ↓                ↓
        PostgreSQL       Object Storage      Qdrant
              │               │                │
       Metadata/ACL       Original Files     Vector
       Document           Images             BM25
       Source             Markdown           Hybrid
       Version                                 │
              │                                │
              └───────────────┬────────────────┘
                              ↓
                           Neo4j
                              │
                       Entity / Relation
                         Knowledge Graph
```

## PostgreSQL

作为业务事实数据库，保存：

- Tenant
- Workspace
- User
- KnowledgeBase
- Folder
- Document
- DocumentVersion
- KnowledgeSource
- Chunk
- Entity
- Relation
- Permission
- ProcessingJob
- ParserConfig
- EmbeddingConfig

## MinIO

用于对象存储：

```text
original/
parsed/
images/
tables/
```

例如：

```text
original/xxx.pdf
parsed/xxx.md
images/xxx/page_001.png
tables/xxx/table_001.json
```

## Qdrant

负责：

- Dense Vector
- Sparse Vector
- Hybrid Search
- Metadata Filter

## Neo4j

负责：

- Entity
- Relation
- Graph Traversal
- Multi-hop Knowledge

原则：

> PostgreSQL 是系统事实数据库，Qdrant 是检索索引，Neo4j 是关系知识索引，MinIO 是原始内容存储。

---

# 9. Retrieval Architecture

```text
                         User Query
                              │
                              ↓
                     ┌─────────────────┐
                     │ Query Analyzer  │
                     └────────┬────────┘
                              │
              ┌───────────────┼────────────────┐
              ↓               ↓                ↓
        Semantic Search   Keyword Search   Graph Search
              │               │                │
           Qdrant          Qdrant           Neo4j
              │               │                │
              └───────────────┼────────────────┘
                              ↓
                       Result Fusion
                              │
                              ↓
                           Reranker
                              │
                              ↓
                      Permission Filter
                              │
                              ↓
                      Context Builder
                              │
                              ↓
                         Final Context
                              │
                              ↓
                            Agent
```

推荐 Retrieval：

1. Semantic Search
2. Keyword / BM25
3. Metadata Filter
4. Graph Search
5. Result Fusion
6. Reranker
7. Context Builder

---

# 10. 权限模型

权限必须进入 Retrieval Pipeline。

不要：

```text
Search
 ↓
Result
 ↓
Permission Check
```

应该：

```text
Query
 ↓
Permission Context
 ↓
Permission Filter
 ↓
Search
 ↓
Rerank
 ↓
Context
```

建议权限层级：

```text
Tenant
 ↓
Workspace
 ↓
Knowledge Base
 ↓
Folder
 ↓
Document
 ↓
Chunk
```

角色：

```text
Owner
Admin
Editor
Viewer
```

---

# 11. Knowledge Graph 架构

知识图谱不是底层唯一存储，而是派生关系索引。

```text
Document
   ↓
Document Understanding
   ↓
Entity Extraction
   ↓
Entity Resolution
   ↓
Relation Extraction
   ↓
Relation Validation
   ↓
Graph Builder
   ↓
Neo4j
```

例如：

```text
张三
 │
 └── VISIT → ABC公司

张三
 │
 └── MET → 李总

ABC公司
 │
 └── HAS_PROJECT → ERP项目

ERP项目
 │
 └── EXPECTED_RELEASE → 2027 Q1
```

每条关系必须保存证据：

```text
source_document
source_chunk
confidence
extracted_at
model_version
```

这样可以追溯知识来源。

---

# 12. 为什么不建议一开始就做全量知识图谱

不要强制：

```text
所有文档
 ↓
全部实体化
 ↓
全部关系化
```

原因：

- NLP/LLM 抽取成本高
- 抽取可能存在错误
- 图谱维护复杂
- 很多知识不需要关系查询
- 业务需求尚未收敛时容易过度设计

原则：

> Document 是 Source of Truth，Graph 是 Derived Index。

---

# 13. Graph RAG

Graph RAG 是 V0.6 之后的重要能力。

```text
                User Query
                     │
                     ↓
              Query Analyzer
                     │
            ┌────────┴────────┐
            ↓                 ↓
        Vector Search     Graph Search
            │                 │
            └────────┬────────┘
                     ↓
                  Fusion
                     ↓
                  Rerank
                     ↓
              Context Builder
                     ↓
                   LLM
```

典型问题：

> ABC 公司有哪些项目？哪些项目存在延期风险？

Graph：

```text
ABC公司 → Project
```

Vector：

```text
Project → Meeting Notes
```

Keyword：

```text
延期 / 风险 / 阻塞
```

最终由 LLM 综合判断。

---

# 14. Agentic Retrieval

最终让 Agent 自己判断是否需要图谱。

例如：

```text
问题：
“ERP合同里面付款比例是多少？”

→ Vector Search
```

```text
问题：
“ABC公司有哪些项目？”

→ Graph Search
```

```text
问题：
“ABC公司哪些项目存在风险？为什么？”

→ Graph
→ Vector
→ Keyword
→ Document Read
→ LLM Reasoning
```

目标：

> 不是所有问题都查图谱，而是让系统根据问题选择最合适的检索策略。

---

# 15. Knowledge MCP

Knowledge Hub 最终应该作为独立 MCP Server 对外提供能力。

建议工具：

```text
search_knowledge()
search_entity()
search_relation()
get_document()
get_chunk()
get_entity_context()
list_knowledge_sources()
```

架构：

```text
Claude Code / Agent
        ↓
   Knowledge MCP
        ↓
   Knowledge Hub
        ↓
┌───────┼────────┐
↓       ↓        ↓
Qdrant Neo4j PostgreSQL
```

这样 Knowledge Hub 可以独立服务于：

- Agent Runtime
- Claude Code
- Workflow
- 企业应用
- 外部 AI 应用

---

# 16. 技术选型

| 模块 | 推荐技术 |
|---|---|
| Backend | Python + FastAPI |
| ORM | SQLAlchemy |
| Database | PostgreSQL |
| Migration | Alembic |
| Object Storage | MinIO |
| Vector DB | Qdrant |
| Graph DB | Neo4j |
| Cache | Redis |
| Queue | Redis Streams / Celery |
| Workflow | Temporal / Celery |
| Document Parse | Docling + Tika |
| Complex PDF | MinerU |
| OCR | PaddleOCR |
| Embedding | BGE-M3 / Qwen Embedding 等 |
| Sparse Search | BM25 / Qdrant Sparse |
| Reranker | BGE Reranker / Cross Encoder |
| LLM | 可插拔 |
| Auth | Keycloak |
| API | REST + MCP |
| Frontend | React + TypeScript |
| UI | Ant Design |
| Monitoring | Prometheus + Grafana |
| Logs | Loki / ELK |
| Trace | OpenTelemetry |
| Container | Docker |
| Deployment | Docker Compose → Kubernetes |

---

# 17. 第一阶段为什么不建议 Elasticsearch

第一阶段不建议同时使用：

```text
PostgreSQL
+
Elasticsearch
+
Qdrant
+
Neo4j
+
Redis
```

会显著增加复杂度。

MVP 建议：

```text
PostgreSQL
MinIO
Qdrant
Redis
```

后续真正需要复杂全文搜索、超大规模数据搜索时，再考虑：

- OpenSearch
- Elasticsearch

---

# 18. 服务模块设计

考虑系统未来需要独立运行和组合，建议模块化：

```text
knowledge-hub/
│
├── knowledge-api
├── source-service
├── document-service
├── parser-service
├── ingestion-worker
├── indexing-service
├── retrieval-service
├── graph-service
├── permission-service
├── knowledge-mcp
└── knowledge-web
```

但是：

> 第一阶段不要直接拆成大量微服务。

建议：

```text
Monorepo
    ↓
Modular Architecture
    ↓
Docker Compose
    ↓
业务稳定后再拆 Service
```

---

# 19. 推荐项目目录

```text
knowledge-hub/
│
├── apps/
│   ├── api/
│   ├── worker/
│   └── web/
│
├── modules/
│   ├── knowledge/
│   ├── source/
│   ├── document/
│   ├── parser/
│   ├── ingestion/
│   ├── chunking/
│   ├── embedding/
│   ├── retrieval/
│   ├── graph/
│   ├── permission/
│   └── audit/
│
├── infrastructure/
│   ├── postgres/
│   ├── qdrant/
│   ├── redis/
│   ├── minio/
│   └── neo4j/
│
├── plugins/
│   ├── sources/
│   ├── parsers/
│   ├── embeddings/
│   └── rerankers/
│
└── deploy/
    ├── docker-compose/
    └── kubernetes/
```

---

# 20. 版本规划

> **可执行路线图**（按交付顺序编号、与平台 / Capability 对齐）见
> [version-roadmap.md](./version-roadmap.md)。下文保留原文 V 号树状图，供对照；
> 实施以 `version-roadmap.md` 为准——其中原 V0.4 Hybrid Retrieval 提前为 v0.2.0，
> 原 V0.2 Multi Source 延后为 v0.3.0；**原 V0.3 租户/用户权限挪到 v0.7，最后设计**，
> 不插入文档管道与 Agent 接入之间。

整体路线：

```text
V0.1
│
├── 文档知识库
├── OCR
├── 多格式
├── Chunk
└── Vector Search
        ↓
V0.2
│
├── 多知识源
├── Folder
├── NAS
├── S3
├── Git
└── Web
        ↓
V0.3
│
├── 企业权限
├── Workspace
├── Version
└── Audit
        ↓
V0.4
│
├── Hybrid Search
├── BM25
├── Reranker
└── Metadata Filter
        ↓
V0.5
│
├── Entity
├── Relation
├── Entity Resolution
└── Knowledge Graph
        ↓
V0.6
│
├── Graph RAG
├── Vector + Graph
└── Multi-hop Retrieval
        ↓
V0.7
│
├── Agentic Retrieval
├── Knowledge MCP
└── Knowledge API
        ↓
V1
│
└── Enterprise Knowledge Infrastructure
```

---

# 21. V0.1 — Document Knowledge Base

目标：

> 先把“上传文件 → 搜索”完整跑通。

支持：

- PDF
- Word
- Excel
- PPT
- TXT
- Markdown
- JPG/PNG
- 扫描 PDF
- OCR
- 文档解析
- Chunk
- Vector Search
- BM25
- 基础 RAG

流程：

```text
File
 ↓
Validation
 ↓
Parser / OCR
 ↓
Markdown
 ↓
Chunk
 ↓
Embedding
 ↓
Qdrant
 ↓
Search
```

这是第一个可 Demo 版本。

---

# 22. V0.2 — Multi Source

目标：

> 从“文件知识库”升级为“企业统一知识入口”。

增加：

- Local Folder
- NAS
- S3
- Git
- Web
- Database
- API
- MCP

同步：

- Manual Sync
- Scheduled Sync
- Incremental Sync
- Delete Sync

统一：

```text
Source
  ↓
Connector
  ↓
Ingestion Pipeline
  ↓
Document
  ↓
Index
```

---

# 23. V0.3 — Enterprise

增加：

- Tenant
- Workspace
- User
- Department
- Role
- Permission
- Audit
- Version

权限：

```text
Tenant
 ↓
Workspace
 ↓
Knowledge Base
 ↓
Folder
 ↓
Document
```

实现企业级数据隔离。

---

# 24. V0.4 — Advanced Retrieval

增加：

```text
Vector Search
+
BM25
+
Metadata Filter
+
Reranker
```

检索：

```text
Query Analyzer
       ↓
Search Strategy
       ↓
Hybrid Retrieval
       ↓
Rerank
       ↓
Context Builder
```

这是第一个明显具有技术竞争力的版本。

---

# 25. V0.5 — Knowledge Graph

正式加入：

- Entity
- Relation
- Entity Resolution
- Graph Search
- Graph Visualization

流程：

```text
Document
 ↓
Entity Extraction
 ↓
Entity Resolution
 ↓
Relation Extraction
 ↓
Relation Validation
 ↓
Neo4j
```

所有关系可追溯到：

```text
source_document
source_chunk
confidence
model_version
```

---

# 26. V0.6 — Graph RAG

实现：

```text
Vector Search
        +
Graph Search
        +
Keyword Search
        ↓
Result Fusion
        ↓
Rerank
        ↓
Context Builder
        ↓
LLM
```

目标：

> 解决单纯 Vector RAG 难以回答复杂关系、多跳问题的场景。

---

# 27. V0.7 — Agentic Knowledge

增加：

- Agentic Retrieval
- Knowledge API
- Knowledge MCP
- Dynamic Retrieval Strategy
- Document Read
- Entity Context
- Multi-step Retrieval

最终：

```text
Agent
 ↓
Knowledge MCP
 ↓
Knowledge Hub
 ↓
Query Planning
 ↓
Vector / Keyword / Graph
 ↓
Rerank
 ↓
Context
 ↓
Agent
```

---

# 28. V1 — Enterprise Knowledge Infrastructure

V1 完整能力：

```text
                         Knowledge Hub
                              │
        ┌─────────────────────┼──────────────────────┐
        ↓                     ↓                      ↓
 Knowledge Management   Knowledge Processing   Knowledge Retrieval
        │                     │                      │
        ↓                     ↓                      ↓
 Sources               OCR / Parser             Vector
 Documents             Chunk                    BM25
 Permissions            Entity                   Graph
 Version                Relation                 Rerank
 Audit                  Summary                  Agentic
        │                     │                      │
        └─────────────────────┼──────────────────────┘
                              ↓
                       Knowledge API
                              │
                    ┌─────────┼─────────┐
                    ↓         ↓         ↓
                  Agent      MCP      External App
```

---

# 29. 推荐 MVP 范围

如果项目同时用于：

- 简历
- 技术作品
- 客户 Demo
- 后续商业化

第一阶段不要直接做 V1。

推荐 MVP：

```text
                Knowledge Hub MVP
                       │
        ┌──────────────┼──────────────┐
        ↓              ↓              ↓
      Source         Document       Retrieval
        │              │              │
     Upload          Parser         Vector
     Folder           OCR           BM25
                      Chunk          Rerank
                       │              │
                       └──────┬───────┘
                              ↓
                         Knowledge API
                              ↓
                             MCP
```

技术：

```text
FastAPI
PostgreSQL
MinIO
Redis
Qdrant
Docling
MinerU
PaddleOCR
BGE / Qwen Embedding
BGE Reranker
React
Docker Compose
```

暂时不引入 Neo4j。

---

# 30. 推荐开发顺序

> 可执行编号见 [version-roadmap.md](./version-roadmap.md)。与下文差异：混合检索先于多源；
> **企业权限不放在阶段 4**，挪到图谱 / Graph RAG / Agentic 全部完成之后（v0.7）。

最推荐：

```text
阶段 1
文档上传
 ↓
Parser / OCR
 ↓
Markdown
 ↓
Chunk
 ↓
Embedding
 ↓
Qdrant
 ↓
Search
```

↓

```text
阶段 2
Hybrid Retrieval
 ↓
BM25
 ↓
Metadata
 ↓
Reranker
```

↓

```text
阶段 3
多知识源
 ↓
Folder
 ↓
NAS
 ↓
S3
 ↓
Web
 ↓
Git
```

↓

```text
阶段 4
企业权限
 ↓
Tenant
 ↓
Workspace
 ↓
RBAC
 ↓
Audit
```

↓

```text
阶段 5
Knowledge Graph
 ↓
Entity
 ↓
Relation
 ↓
Entity Resolution
 ↓
Neo4j
```

↓

```text
阶段 6
Graph RAG
 ↓
Vector + Graph
 ↓
Multi-hop
```

↓

```text
阶段 7
Agentic Retrieval
 ↓
Knowledge MCP
 ↓
Agent Runtime
```

---

# 31. 最终产品形态

最终可以形成：

```text
                  Enterprise Agent Platform
                           │
         ┌─────────────────┴──────────────────┐
         │                                    │
         ↓                                    ↓
 Capability Registry                    Knowledge Hub
         │                                    │
         │                                    │
  ┌──────┼──────┐                     ┌───────┼────────┐
  ↓      ↓      ↓                     ↓       ↓        ↓
 Tool   Skill   MCP                Document  Graph    Search
  │      │      │                     │       │        │
  └──────┼──────┘                     └───────┼────────┘
         │                                    │
         └────────────────┬───────────────────┘
                          ↓
                    Agent Runtime
                          │
                 ┌────────┴────────┐
                 ↓                 ↓
              Brain             Workflow
             Redis              LangGraph
                 │                 │
                 └────────┬────────┘
                          ↓
                         Agent
```

最终产品定位：

> **企业级可私有化部署的 Knowledge Infrastructure，支持多数据源接入、多格式文档解析与 OCR、Hybrid Retrieval、Knowledge Graph、Graph RAG、Agentic Retrieval，并通过 API/MCP 为 Agent Runtime 提供统一知识服务。**

---

# 32. 最终设计原则总结

### 原则 1：文档是事实源

```text
Document = Source of Truth
Graph = Derived Index
Vector = Retrieval Index
```

### 原则 2：知识来源与知识库解耦

```text
Source → Ingestion → Knowledge Base
```

### 原则 3：不要 Vector Only

```text
Vector
+
Keyword
+
Metadata
+
Graph
+
Rerank
```

### 原则 4：不要一开始就做 Graph

```text
V0.1 Document
 ↓
V0.4 Hybrid Retrieval
 ↓
V0.5 Graph
 ↓
V0.6 Graph RAG
```

### 原则 5：Agent 自主选择检索策略

```text
简单问题 → Vector
关系问题 → Graph
精确编号 → Keyword
复杂问题 → Hybrid
多跳问题 → Graph + Vector
```

### 原则 6：Knowledge Hub 独立于 Agent Runtime

Knowledge Hub 本身不负责 Agent 推理。

它负责：

> “提供高质量、可追溯、可授权的知识。”

### 原则 7：所有知识都必须可追溯

Graph / Chunk / Entity / Relation 都应该能够追溯：

```text
Answer
 ↓
Entity / Chunk
 ↓
Document
 ↓
Original File
```

---

# 33. 项目最终目标

这个项目最终不是：

> “一个 RAG Demo”

而是：

> **一个可以被企业 Agent、Workflow、Claude Code 和其他 AI 应用共同使用的企业级知识基础设施。**

核心能力：

```text
多知识源
   +
文档理解
   +
OCR
   +
结构化知识
   +
Hybrid Retrieval
   +
Knowledge Graph
   +
Graph RAG
   +
Agentic Retrieval
   +
权限
   +
MCP
   =
Enterprise Knowledge Infrastructure
```
