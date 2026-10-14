# PlatformAgent 文档

PlatformAgent 是 SmartAgent 的业务层，包括 FastAPI 后端和 React Console。后端负责租户、身份与权限、
Agent 配置、Run 持久化、评测、实验及成本；Console 通过 HTTP/SSE 调用后端。

## 文档

- [业务层详细设计](./业务层详细设计.md)：模块边界、运行装配和需要遵循的运行时契约。
- [API 文档](./API文档.md)：路由分组、行为约束和 API 文档入口。
- [业务层版本规划](./版本规划.md)：0.1.0–1.0.0 交付现状与后续范围。
- [0.4.0 知识图谱与知识检索设计](./知识图谱与知识检索设计.md)：业务知识图谱、租户文档 RAG、来源证据及 Runtime 接线方案。
- [后端开发说明](../../application/platformagent/backend/README.md)：安装、配置、迁移、启动和测试。
- [Console 开发说明](../../application/platformagent/frontend/README.md)：前端运行、代理及登录说明。

## 当前基线

- 平台功能线：0.3.0；Python 后端和 Console 共同组成 PlatformAgent。
- Console 是轻量 HTTP 客户端，不持有平台业务数据库；`package.json` 的 0.1.0 不是单独发布版本。
- 框架依赖：Ouroboros 2.0.0；Tool Catalog / 调用可通过 HTTP 集成 Capability Registry 0.3.0。
- 当前没有平台级 Knowledge/RAG 摄取服务或业务知识图谱；0.4.0 设计见[知识图谱与知识检索设计](./知识图谱与知识检索设计.md)。
- 运行 DAG 控制台和 Playground 也尚未实现；个人对话 Memory Graph 不属于 0.4.0 范围。

版本号的最终依据见仓库根 [VERSIONS.md](../../VERSIONS.md)。
