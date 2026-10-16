# 项目进度

最后更新：2026-10-16 11:00（Asia/Shanghai）

## 当前概况

- 当前目标：维护可跨个人、公司和内网环境重建的 Agent/Skill 与开发软件；软件安全子集已通过私有 GitHub Release 分发。
- Skill 新增（2026-10-16，公司机）：vercel-labs/skills 的 skills CLI v1.7.2 已 npm 全局安装并验收（项目级装删、HOME 沙箱全局、find 搜索全通过；全局装 `~/.agents/skills` 须显式 `-a pi`，remove 不带 `-a`，详见 README §12 与技能内适配节）；自带 find-skills 技能入库 `skills/` 并注册 common；npm 资源因本机 npm 不输出 resolved 来源字段无法 adopt，改为手动登记 `resources.npm.skills` + doctor `tool:skills`；公司机 44/44 健康，新增技能已在本会话目录出现。
- CLI 修复（2026-10-14）：`export` 密钥扫描误报已修——原 OpenAI 正则把 Microsoft Learn URL 词组 task-based-asynchronous-programming（含 sk-based-… 子串）当成 API key，拦截了 ui-ux-pro-max 的 winui/wpf CSV；正则收紧为独立 token + 至多两段短前缀 + 20 位字母数字主体，sk-/sk-proj-/sk-ant-api03-/sk-or-v1- 真实键仍拦截；新增 2 条回归测试（test_bundle.py 9 项过），真实工作区 378 文件扫描通过，实跑导出成功；提交 `4fec1d1` 已随用户串口修复 `e6989e5` 由用户推送至 origin/master；DSH 会话内 git push 被环境拦截（argv 被改写、网络强制直连），handoff 归档提交仍需从用户终端推送，详见当日 handoff。
- Skill 更新（2026-10-14）：handoff 提交策略分区——内网机（agentctl 环境 intranet，network.internet: false）默认不自动 commit，用户在本次对话首次明确要求提交后才恢复默认提交；环境经 AGENTCTL_ENV 或工作区根 local.yaml 判定，无法判定按在线处理，本机（company）行为不变，内网待下次离线包 import 生效。
- Skill 更新（2026-10-13）：`serial-debug` 的 GUI 从 50 行服务薄客户端换成 serial-gui Qt 工作台（内置直连与共享服务两种用法、agent 接管按钮），`tests/test_serial_gui.py` 重写为工作台↔真实 SerialService 契约测试（无 PySide6 自动跳过）；skill 全套 18 项通过，agent-workspace 提交 `6cb72ab`，规范仓库 serial-debug 已同步推送 `c3dc773`。上游 serial-gui 同日完成 Qt 主分支切换（`54829dc`）与服务会话功能（`50fe938`）。
- 仓库整理（2026-10-13）：serial-gui 本地开发克隆 `D:\App\serial_tool\serial-gui` 已删除（删前核实工作树干净、main=`878fe8f` 已推送、skill 内置 5 个 Qt 文件与仓库逐字节一致），Qt 工作台以 skill 内置副本与远程 `493935827/serial-gui` 为准；其 `.venv`（PySide6）随克隆移除，skill GUI 测试需在 workspace `.venv` 补装 PySide6；`D:\App\serial_tool\serial-gui.7z` 为 10-10 旧快照保留（未含最新 4 提交，远端有）。
- Skill 更新（2026-10-12，公司机）：新增社区技能 ui-ux-pro-max（UI/UX 设计智能库，73 文件）入库 `skills/` 并注册 `configs/common.yaml`；源目录 45→46、公共启用 40→41，公司机 junction 实测 43/43 健康，其余环境待各机链接后更新计数；本次即 update 缺陷所述"新增 skill 需手动 link"场景，缺陷本身未动。
- Skill：项目共 47 个源目录；公共启用 42 个，personal/company/intranet 分别启用 44/44/43，公司机链接 44/44 健康，其余环境待各机 update 后生效。
- 软件与交付：公司 51/52、内网 44/45 项介质就绪；安全子集已拆为通用、公司专用、个人专用三个 ZIP，逐包校验 SHA-256。
- 开发配套：26 个精确版本 VSIX 与 OneNote MCP 0.1.1 的 115 个 npm 依赖已完成离线准备与验证。
- OneNote：7 个笔记本、39 个分区、142 个页面、970 个资源和 68 个原生备份已归档，按敏感数据保管。
- 分发：私有仓库 `493935827/agent-software-packages` 的 Release `software-2026-10-02` 已发布 4 个附件；另在 `pixpin-3.5.5.1` 发布 PixPin Windows 官方安装包与校验文件，远端大小和 SHA-256 均与本地一致。
- CLI：中文 help 已补齐；用户 PATH 与 `AGENT_WORKSPACE_ROOT` 已配置，可从任意目录运行 `agentctl doctor`；Windows 启动脚本保留退出码。
- CLI 验证：15 个子命令均已实际调用；文件、配置及链接写入只在临时工作区，`update --dry-run` 执行 fetch。普通用户 PATH 下临时 `snapshot` 可保存基线；Codex fallback `pnpm` 会导致完整扫描报错。
- 已发现待修：`agentctl update` 重链使用 pull 前旧配置（cli.py 先建 cfg、update.py 复用），拉取新增启用的 skill 需手动 `agentctl link`；测试未覆盖此场景，修复待用户决策。
- 已发现待修（2026-10-16）：`tests/test_discovery.py` 4 项失败为存量问题（stash 对照验证与当日改动无关），且失败用例会把 `npm:example` 测试数据写进真实 `configs/personal.yaml`（本次已 checkout 还原），疑似用例工作区隔离缺陷，修复待用户决策。
- 安全边界：`user-data/`、OneNote 和受限安装介质未上传公开代码仓库。
- 阻塞与下一步：仍缺 AndeSight 5.3.1，需走公司批准渠道；其他环境可按私有 Release ZIP 与校验文件重建，后续按用户新需求推进；`2ebb8aa` 与 handoff 提交待用户终端 git push。

## 对话归档

| 日期 / 对话 | 完成内容 | 交接 |
| --- | --- | --- |
| 2026-10-16 / vercel skills CLI 集成 | 安装并验收 skills CLI v1.7.2（全局装 `-a pi`、remove 不带 `-a` 等坑记入 README §12），find-skills 技能入库并注册（提交 `2ebb8aa`；DSH 内推送被拦，待用户终端推送）；发现 test_discovery 存量失败与真实配置污染缺陷（已还原） | [vercel-labs/skills CLI 集成](handoff-20261016-105816-vercel-skills-cli.md) |
| 2026-10-14 / `session-a192d833`（export 扫描修复） | 修复 agentctl export 密钥扫描把 Microsoft Learn URL 词组误判为 OpenAI key 的问题；回归测试、378 文件 dry-run 与真实导出均通过（提交 `4fec1d1`，因会话环境限制未推送） | [export 密钥扫描误报修复](handoff-20261014-140351-export-secret-scan-fix.md) |
| 2026-10-13 / serial-qt promotion & skill sync | serial-gui 切换 Qt 主分支、移植 backspace 修复、新增服务会话与 agent 接管；serial-debug skill 替换为 Qt 工作台并同步规范仓库（三仓库均已推送；真实硬件验收未做） | [serial-gui Qt 主分支切换与 skill 工具同步](handoff-20261013-163203-serial-qt-promotion-skill-sync.md) |
| 2026-10-11 / `01a1294d`（agentctl help 与验证） | 补齐中文 help 和全局入口、修复启动脚本退出码，并验证 15 个子命令 | [agentctl 帮助、全局入口与命令验证](handoff-20261011-175417-agentctl-help-validation.md) |
| 2026-09-24 / agentctl trial & update | agentctl 全流程实测符合文档（84 测试过、42/42 链接）；发现 update 重链用旧配置缺陷（未修）；核实交付包实体不在本机 | [agentctl 实测与拉取](handoff-20260924-111748-agentctl-trial-validation.md) |
| 2026-09-23 / Skill sync and CopyQ | 新增 37 个同步 Skill，并把 CopyQ 16.0.0 加入公司/内网交付包；全部已验证并推送项目记录 | [Skill 同步扩充与 CopyQ 软件补充](handoff-20260923-234327-skill-sync-copyq.md) |
| 2026-09-23 / installer transfer and OneNote | 公司/内网安装介质已本地准备并验证；OneNote 142 页、970 个资源和 68 个原生备份已归档，等待 AndeSight 与传输目的地 | [安装介质与 OneNote 归档](handoff-20260923-173434-installer-transfer-onenote.md) |
| 2026-09-21 / software selection | 用户确认公司 51 项、内网 44 项；改为传安装包，目的地待提供 | [软件选择与安装包传输](handoff-20260921-105807-installer-transfer.md) |
| 2026-09-20 / discovery implementation | 第一版实现并推送；累计 84 项测试覆盖通过，实机与跨平台限制已记录 | [环境发现第一版实施](handoff-20260920-133313-discovery-implementation.md) |
| 2026-09-20 / discovery grilling | 23 项设计决策已接受；功能未实施，等待最终实施确认 | [环境发现与登记方案](handoff-20260920-110828-environment-discovery.md) |
