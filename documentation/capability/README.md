# Capability Registry 文档

Capability Registry 是独立部署的 Tool 管理与执行服务。PlatformAgent 通过内部 HTTP API 获取启用的
API/MCP Tool 描述并代理执行；不共享 Python 包或数据库。

## 文档

- [产品章程](./product-charter.md)
- [系统架构](./system-architecture.md)
- [版本路线图](./version-roadmap.md)
- [Workflow 设计（规划）](./workflow-design.md)
- [v0.1.0 Tool Registry](./version/v0.1.0-tool-registry.md)
- [v0.2.0 MCP Provider](./version/v0.2.0-mcp-provider.md)
- [v0.5.0 Discovery & Permission（规划）](./version/v0.5.0-discovery-permission.md)
- [v1.0.0 Capability Registry（规划）](./version/v1.0.0-capability-registry.md)
- [部署与开发 README](../../application/capability/README.md)

## 当前状态提示

项目当前为 0.3.0：除工具目录和 MCP Provider 同步外，已实现 API Service/API Tool、凭据加密、HTTP/API 与 MCP
Tool 调用，以及受共享密钥保护的 Platform Runtime 集成。管理 API 本身尚无用户身份鉴权；
部署时必须按[项目 README](../../application/capability/README.md)配置网络和密钥。
