# Ouroboros 文档

Ouroboros 是业务无关的 Agent Runtime 框架。它提供 Plan → Decide → Execute → Observe 运行循环、
Plugin/Skill/Tool 机制、记忆和评测等能力，并在 `ouroboros.ports` 定义宿主契约。

## 文档

- [版本规划](./版本规划.md)：框架独立 SemVer 路线。
- [架构总结](./架构总结.md)：总体架构图、运行链路与继承/扩展关系。
- [Agent 框架层详细设计](./Agent框架层详细设计.md)
- [Agent 框架使用文档](./Agent框架使用文档.md)
- [Plugin / Tool / Skill UML（Markdown）](./plugins-tools-skills-uml.md)
- [Plugin / Tool / Skill UML（HTML）](./plugins-tools-skills-uml.html)
- [框架 README 与安装示例](../../application/ouroboros/README.md)
- [框架 Changelog](../../application/ouroboros/CHANGELOG.md)

框架不导入宿主的 HTTP、数据库、租户或配置实现。PlatformAgent 的集成边界见
[业务层详细设计](../platformagent/业务层详细设计.md)。
