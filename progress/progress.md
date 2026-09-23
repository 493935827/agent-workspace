# 项目进度

最后更新：2026-09-23 23:43（Asia/Shanghai）

## 当前概况

- 当前目标：维护可跨个人、公司和内网环境重建的 Agent/Skill 与开发软件；等待下一批常用软件确认和实际传输。
- Skill：新增 37 个本机 Skill，项目共 45 个源目录；公共启用 40 个，personal/company/intranet 分别启用 42/42/41，当前 personal 链接 42/42 健康。
- 软件：CopyQ 16.0.0 已加入公司与内网共用清单；公司 51/52、内网 44/45 项介质就绪，唯一缺项为 AndeSight 5.3.1。
- 交付包：1,865 个文件、约 3.201 GiB；1,863 条 SHA-256 已复核，25 个可执行介质中 20 个签名有效、4 个未签名但官方哈希匹配。
- 开发配套：26 个精确版本 VSIX 和 OneNote MCP 0.1.1 的 115 个 npm 依赖已完成离线准备与验证。
- OneNote：7 个笔记本、39 个分区、142 个页面、970 个资源和 68 个原生备份已归档，按敏感数据保管。
- 边界：安装介质、OneNote 数据和 Excel 不进 Git；安装包尚未传输，代码远程不是软件目的地。
- 阻塞：需取得 AndeSight 5.3.1，并由用户提供安装包传输目的地。
- 下一步：确认 Listary、Quicker 等候选；补齐 AndeSight；传输后按 `metadata/SHA256SUMS.txt` 在目标端复核。

## 对话归档

| 日期 / 对话 | 完成内容 | 交接 |
| --- | --- | --- |
| 2026-09-23 / Skill sync and CopyQ | 新增 37 个同步 Skill，并把 CopyQ 16.0.0 加入公司/内网交付包；全部已验证并推送项目记录 | [Skill 同步扩充与 CopyQ 软件补充](handoff-20260923-234327-skill-sync-copyq.md) |
| 2026-09-23 / installer transfer and OneNote | 公司/内网安装介质已本地准备并验证；OneNote 142 页、970 个资源和 68 个原生备份已归档，等待 AndeSight 与传输目的地 | [安装介质与 OneNote 归档](handoff-20260923-173434-installer-transfer-onenote.md) |
| 2026-09-21 / software selection | 用户确认公司 51 项、内网 44 项；改为传安装包，目的地待提供 | [软件选择与安装包传输](handoff-20260921-105807-installer-transfer.md) |
| 2026-09-20 / discovery implementation | 第一版实现并推送；累计 84 项测试覆盖通过，实机与跨平台限制已记录 | [环境发现第一版实施](handoff-20260920-133313-discovery-implementation.md) |
| 2026-09-20 / discovery grilling | 23 项设计决策已接受；功能未实施，等待最终实施确认 | [环境发现与登记方案](handoff-20260920-110828-environment-discovery.md) |
