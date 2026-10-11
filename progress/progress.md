# 项目进度

最后更新：2026-10-11 17:54（Asia/Hong_Kong）

## 当前概况

- 当前目标：维护可跨个人、公司和内网环境重建的 Agent/Skill 与开发软件；软件安全子集已通过私有 GitHub Release 分发。
- Skill：项目共 45 个源目录；公共启用 40 个，personal/company/intranet 分别启用 42/42/41，个人机链接 42/42 健康。
- 软件与交付：公司 51/52、内网 44/45 项介质就绪；安全子集已拆为通用、公司专用、个人专用三个 ZIP，逐包校验 SHA-256。
- 开发配套：26 个精确版本 VSIX 与 OneNote MCP 0.1.1 的 115 个 npm 依赖已完成离线准备与验证。
- OneNote：7 个笔记本、39 个分区、142 个页面、970 个资源和 68 个原生备份已归档，按敏感数据保管。
- 分发：私有仓库 `493935827/agent-software-packages` 的 Release `software-2026-10-02` 已发布 4 个附件；另在 `pixpin-3.5.5.1` 发布 PixPin Windows 官方安装包与校验文件，远端大小和 SHA-256 均与本地一致。
- CLI：中文 help 已补齐；用户 PATH 与 `AGENT_WORKSPACE_ROOT` 已配置，可从任意目录运行 `agentctl doctor`；Windows 启动脚本保留退出码。
- CLI 验证：15 个子命令均已实际调用；文件、配置及链接写入只在临时工作区，`update --dry-run` 执行 fetch。普通用户 PATH 下临时 `snapshot` 可保存基线；Codex fallback `pnpm` 会导致完整扫描报错。
- 安全边界：`user-data/`、OneNote 和受限安装介质未上传公开代码仓库。
- 阻塞与下一步：仍缺 AndeSight 5.3.1，需走公司批准渠道；其他环境可按私有 Release ZIP 与校验文件重建，后续按用户新需求推进。

## 对话归档

| 日期 / 对话 | 完成内容 | 交接 |
| --- | --- | --- |
| 2026-10-11 / `01a1294d`（agentctl help 与验证） | 补齐中文 help 和全局入口、修复启动脚本退出码，并验证 15 个子命令 | [agentctl 帮助、全局入口与命令验证](handoff-20261011-175417-agentctl-help-validation.md) |
| 2026-09-23 / Skill sync and CopyQ | 新增 37 个同步 Skill，并把 CopyQ 16.0.0 加入公司/内网交付包；全部已验证并推送项目记录 | [Skill 同步扩充与 CopyQ 软件补充](handoff-20260923-234327-skill-sync-copyq.md) |
| 2026-09-23 / installer transfer and OneNote | 公司/内网安装介质已本地准备并验证；OneNote 142 页、970 个资源和 68 个原生备份已归档，等待 AndeSight 与传输目的地 | [安装介质与 OneNote 归档](handoff-20260923-173434-installer-transfer-onenote.md) |
| 2026-09-21 / software selection | 用户确认公司 51 项、内网 44 项；改为传安装包，目的地待提供 | [软件选择与安装包传输](handoff-20260921-105807-installer-transfer.md) |
| 2026-09-20 / discovery implementation | 第一版实现并推送；累计 84 项测试覆盖通过，实机与跨平台限制已记录 | [环境发现第一版实施](handoff-20260920-133313-discovery-implementation.md) |
| 2026-09-20 / discovery grilling | 23 项设计决策已接受；功能未实施，等待最终实施确认 | [环境发现与登记方案](handoff-20260920-110828-environment-discovery.md) |
