# Ouroboros 文档

Ouroboros 是业务无关的 Agent Runtime 框架。它提供 Plan → Decide → Execute → Observe 运行循环、
Plugin/Skill/Tool 机制、记忆和评测等能力，并在 `ouroboros.ports` 定义宿主契约。

## 文档

- [版本规划](./版本规划.md)：框架独立 SemVer 路线。
- [架构总结](./架构总结.md)：总体架构图、运行链路与继承/扩展关系。
- [多任务依赖调度与新架构设计](./多任务依赖调度与新架构设计.md)：当前架构基线、已知缺点、DAG 目标架构与实施改动清单（提案，尚未实现）。
- [上下文管理设计方案](./上下文管理设计方案.md)：请求前 token 预算、历史压缩、记忆/工具 schema 选择与 MCP 输出限制（提案，尚未实现）。
- [多 Agent 上下文管理设计方案](./多Agent上下文管理设计方案.md)：父子上下文隔离、最小委派包、结构化结果、树级预算/取消与显式共享（提案，尚未实现）。
- [沙盒执行系统设计方案](./沙盒执行系统设计方案.md)：按任务风险选择隔离 Profile，定义控制面/Worker、权限网络边界、阿里云部署拓扑与分阶段实施（提案，尚未实现）。
- [Agent 框架层详细设计](./Agent框架层详细设计.md)
- [Agent 框架使用文档](./Agent框架使用文档.md)
- [Plugin / Tool / Skill UML（Markdown）](./plugins-tools-skills-uml.md)
- [Plugin / Tool / Skill UML（HTML）](./plugins-tools-skills-uml.html)
- [框架 README 与安装示例](../../application/ouroboros/README.md)
- [框架 Changelog](../../application/ouroboros/CHANGELOG.md)

框架不导入宿主的 HTTP、数据库、租户或配置实现。PlatformAgent 的集成边界见
[业务层详细设计](../platformagent/业务层详细设计.md)。
