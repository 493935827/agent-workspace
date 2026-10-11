# 项目进度

最后更新：2026-10-11（Asia/Hong_Kong）

## 当前概况

- 当前目标：维护可跨个人、公司和内网环境重建的 Agent/Skill 与开发软件；软件安全子集已通过私有 GitHub Release 分发。
- Skill：新增 37 个本机 Skill，项目共 45 个源目录；公共启用 40 个，personal/company/intranet 分别启用 42/42/41，当前 personal 链接 42/42 健康。
- 软件：CopyQ 16.0.0 已加入公司与内网共用清单；公司 51/52、内网 44/45 项介质就绪，唯一缺项为 AndeSight 5.3.1。
- 交付包：本地原始包 1,865 个文件、约 3.201 GiB；安全子集已拆为通用、公司专用、个人专用三个 ZIP，逐包解压并复核内部 SHA-256。
- 开发配套：26 个精确版本 VSIX 和 OneNote MCP 0.1.1 的 115 个 npm 依赖已完成离线准备与验证。
- OneNote：7 个笔记本、39 个分区、142 个页面、970 个资源和 68 个原生备份已归档，按敏感数据保管。
- 分发：私有仓库 `493935827/agent-software-packages` 的 Release `software-2026-10-02` 已发布 4 个附件，远端大小和 SHA-256 均与本地一致。
- CLI：`agentctl --help` 和各子命令 `--help` 已补充中文用途、参数说明、示例与关键限制；个人机用户 PATH 已加入工作区 `scripts/`，`AGENT_WORKSPACE_ROOT` 已指向工作区根目录，`agentctl doctor` 可从任意目录运行。Windows 启动脚本现会保留命令退出码。
- CLI 验证：15 个子命令均已实际调用；写入型命令在临时工作区验证，`update` 和 `bootstrap` 使用 `--dry-run`。普通用户 PATH 下 `snapshot` 可保存基线；Codex 运行时额外提供的 `pnpm` 因自身全局 bin 未配置，会令完整扫描返回 Provider error。
- 安全边界：`user-data/` 与 OneNote 全部排除；MPS Power Manager 机密/NDA 包和企业分发的 GlobalProtect 未上传，公开的代码仓库仍不保存安装介质。
- 阻塞与下一步：仍缺 AndeSight 5.3.1；受限介质需走公司批准渠道；其他环境可从私有 Release 下载对应 ZIP 并按校验文件复核。

## 对话归档

| 日期 / 对话 | 完成内容 | 交接 |
| --- | --- | --- |
| 2026-09-23 / Skill sync and CopyQ | 新增 37 个同步 Skill，并把 CopyQ 16.0.0 加入公司/内网交付包；全部已验证并推送项目记录 | [Skill 同步扩充与 CopyQ 软件补充](handoff-20260923-234327-skill-sync-copyq.md) |
| 2026-09-23 / installer transfer and OneNote | 公司/内网安装介质已本地准备并验证；OneNote 142 页、970 个资源和 68 个原生备份已归档，等待 AndeSight 与传输目的地 | [安装介质与 OneNote 归档](handoff-20260923-173434-installer-transfer-onenote.md) |
| 2026-09-21 / software selection | 用户确认公司 51 项、内网 44 项；改为传安装包，目的地待提供 | [软件选择与安装包传输](handoff-20260921-105807-installer-transfer.md) |
| 2026-09-20 / discovery implementation | 第一版实现并推送；累计 84 项测试覆盖通过，实机与跨平台限制已记录 | [环境发现第一版实施](handoff-20260920-133313-discovery-implementation.md) |
| 2026-09-20 / discovery grilling | 23 项设计决策已接受；功能未实施，等待最终实施确认 | [环境发现与登记方案](handoff-20260920-110828-environment-discovery.md) |
