# 项目进度

最后更新：2026-10-21 17:01（Asia/Shanghai）

## 当前概况

- 当前目标：维护可跨个人、公司、内网环境重建的 Agent/Skill 与开发软件；安全子集经私有 GitHub Release 分发。
- 近期里程碑：progress/交接约定改版为渐进式披露三层；agentctl 第一版全流程验收；serial-debug skill 换 Qt 工作台并同步上游；export 扫描误报修复；skills CLI 与 ui-ux-pro-max 入库。serial-gui 本地开发克隆已删，以 skill 内置副本与上游 493935827/serial-gui 为准（细节见归档行）。
- Skills：源 47、公共启用 42；personal/company/intranet 启用 44/44/43，公司机链接 44/44 健康，其余环境待 update 生效。
- serial-gui：标题栏「拖不动」三因已事件级复现（模态锁窗、GUI 线程枚举阻塞、QMenuBar 死区+最大化 startSystemMove 失效）；修复补丁已备待用户确认，证据与注入台见归档行。
- agentctl：中文 help、全局入口与 16 个子命令已验证（README；appconfig：应用配置 capture/deploy，CopyQ 已纳管，设置模板 tools/copyq；machine_setup：bootstrap 自动配置机器级环境——AGENT_WORKSPACE_ROOT/用户 PATH/PowerShell 执行策略与 profile 标记块，doctor machine:* 查漂移，本机部署验证）；待修：update 重链用拉取前旧配置（新增启用 skill 需手动 link）、test_discovery 4 项存量失败且污染真实 personal.yaml（已还原；2026-10-21 全量 pytest 再次复现并还原）——均待用户决策。
- 软件交付：公司 51/52、内网 44/45 项介质就绪；安全子集拆三 ZIP 逐包 SHA-256 校验，PixPin 安装包同发布于私有 Release；CopyQ 配置+剪贴板历史已发布于私有 user-data-2026-10-21 Release（agent-software-packages，SHA-256 校验通过，可用 agentctl appconfig deploy 恢复）；本机实装 CopyQ 3.12.0（交付包内为 16.0.0 安装器，升级未做），条目 20 行截断已配置生效。
- 开发配套：26 个精确版本 VSIX 与 OneNote MCP 的 npm 依赖离线就绪；OneNote 7 笔记本全量归档，按敏感数据保管；zoxide v0.10.0 已装入用户 PATH 并接入工作区（目录库已种子，用法约定见 AGENTS.md）。
- 安全边界：`user-data/`、OneNote 归档与受限安装介质不入公开仓库。
- 阻塞：仍缺 AndeSight 5.3.1（走公司批准渠道）。（2026-10-21 16:26 核实：原 3 个推送积压提交已由用户推送，origin/master 已到 b117334。）
- 下一步：按用户新需求推进；各环境 update 后刷新启用计数。

## 对话归档

| 日期 / 对话 | 完成内容 | 交接 |
| --- | --- | --- |
| 2026-10-21 / serial-gui 拖动诊断（`session-86feed6014c3`） | 鼠标注入台把「窗口有时拖不动」复现到事件级：菜单栏 MinimumExpanding 死区、最大化 startSystemMove 失效、模态锁窗与 comports 阻塞；修复未实施 | [serial-gui 标题栏拖动诊断](handoff-20261021-153400-serial-gui-titlebar-drag.md) |
| 2026-10-21 / progress 渐进式披露改版 | 概况改为每主题一行三层披露，handoff/project-structure/AGENTS.md 约定同步，progress.md 压缩为 9 行示范；提交未推送 | [progress 约定渐进式披露改版](handoff-20261021-105633-progressive-disclosure-progress-rules.md) |
| 2026-10-16 / vercel skills CLI 集成 | 安装验收 skills CLI v1.7.2 并入库 find-skills 技能；发现 test_discovery 存量失败与真实配置污染缺陷（已还原） | [vercel-labs/skills CLI 集成](handoff-20261016-105816-vercel-skills-cli.md) |
| 2026-10-14 / `session-a192d833`（export 扫描修复） | 修复 agentctl export 密钥扫描把 URL 词组误判为 OpenAI key 的问题，回归与真实导出验证通过（提交已由用户推送） | [export 密钥扫描误报修复](handoff-20261014-140351-export-secret-scan-fix.md) |
| 2026-10-13 / serial-qt promotion & skill sync | serial-gui 切换 Qt 主分支、移植 backspace 修复、新增服务会话与 agent 接管；serial-debug skill 替换为 Qt 工作台并同步规范仓库（三仓库均已推送；真实硬件验收未做） | [serial-gui Qt 主分支切换与 skill 工具同步](handoff-20261013-163203-serial-qt-promotion-skill-sync.md) |
| 2026-10-11 / `01a1294d`（agentctl help 与验证） | 补齐中文 help 和全局入口、修复启动脚本退出码，并验证 15 个子命令 | [agentctl 帮助、全局入口与命令验证](handoff-20261011-175417-agentctl-help-validation.md) |
| 2026-09-24 / agentctl trial & update | agentctl 全流程实测符合文档（84 测试过、42/42 链接）；发现 update 重链用旧配置缺陷（未修）；核实交付包实体不在本机 | [agentctl 实测与拉取](handoff-20260924-111748-agentctl-trial-validation.md) |
| 2026-09-23 / Skill sync and CopyQ | 新增 37 个同步 Skill，并把 CopyQ 16.0.0 加入公司/内网交付包；全部已验证并推送项目记录 | [Skill 同步扩充与 CopyQ 软件补充](handoff-20260923-234327-skill-sync-copyq.md) |
| 2026-09-23 / installer transfer and OneNote | 公司/内网安装介质已本地准备并验证；OneNote 142 页、970 个资源和 68 个原生备份已归档，等待 AndeSight 与传输目的地 | [安装介质与 OneNote 归档](handoff-20260923-173434-installer-transfer-onenote.md) |
| 2026-09-21 / software selection | 用户确认公司 51 项、内网 44 项；改为传安装包，目的地待提供 | [软件选择与安装包传输](handoff-20260921-105807-installer-transfer.md) |
| 2026-09-20 / discovery implementation | 第一版实现并推送；累计 84 项测试覆盖通过，实机与跨平台限制已记录 | [环境发现第一版实施](handoff-20260920-133313-discovery-implementation.md) |
| 2026-09-20 / discovery grilling | 23 项设计决策已接受；功能未实施，等待最终实施确认 | [环境发现与登记方案](handoff-20260920-110828-environment-discovery.md) |
