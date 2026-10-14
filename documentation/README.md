# SmartAgent 文档中心

本目录集中维护仓库文档，按“总体项目文档 + 子项目文档”组织：

```text
documentation/
├── README.md                  文档导航与目录约定
├── 技术方案设计.md             全仓总体方案与系统架构
├── 核心设计图.md               跨层记忆设计与运行跟踪交互稿
├── 版本规划.md                 项目版本轴总览
├── platformagent/              业务平台（后端 + Console）
├── ouroboros/                  Agent 框架
└── capability/                 Capability Registry
```

## 总体项目文档

- [技术方案设计](./技术方案设计.md)：全仓架构、分层边界、部署现状及生产目标。
- [核心设计图](./核心设计图.md)：Brain 和记忆、运行跟踪界面的设计图；未实现部分在文内标注。
- [版本规划](./版本规划.md)：三个子项目的版本基线、交付状态与跨项目关系。

## 子项目文档

- [PlatformAgent 业务平台](./platformagent/README.md)：业务 API、数据与 IAM、运行装配、路线图及 0.4.0 知识图谱设计。
- [Ouroboros Agent 框架](./ouroboros/README.md)：框架公开契约、使用入口、UML 与独立版本路线。
- [Capability Registry](./capability/README.md)：Registry 的边界、架构、产品章程及版本路线。

## 归档与事实来源

- `documentation/<子项目>/` 是对应子项目的设计、接口、版本和使用文档目录。
- 项目代码内的 `README.md` 保留项目启动、开发和部署操作说明；细节设计统一链接到本目录。
- 路线图描述计划，README 与代码描述已实现行为。版本号的唯一真源是仓库根 [VERSIONS.md](../VERSIONS.md)。
- `application/` 下旧的项目内文档不再作为文档维护入口；若引用过时，应链接到本目录对应文档。
