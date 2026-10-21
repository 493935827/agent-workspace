# CopyQ 配置纳管与 20 行截断交接

日期：2026-10-21 16:55（Asia/Shanghai）
对话标识：`session-0c3bbc348b06`（DSH 会话工作目录标识）

## 当前目标与范围

- 项目长期目标不变：跨个人/公司/内网重建 Agent/Skill 与开发软件；安全数据走私有 GitHub Release。
- 本会话两段任务：① 把 CopyQ 配置目录上传私有 Release 并让 agentctl 支持配置化恢复；② 配置 CopyQ 条目显示上限 20 行 + 预览策略。
- 本机为 company 环境（公网，`local.yaml: environment: company`）；工作区 `D:\App\agent-workspace`。

## 本次完成并验证

### agentctl appconfig（第 16 个子命令，提交 `b117334` 已推送）

- 新模块 `agentctl/appconfig.py`：`list/status/capture/deploy`；deploy 备份优先（同名文件先移入 `backups/appconfig/<应用名>/<时间戳>/`），支持目录与 ZIP 源，ZIP 解压有路径穿越校验（复用 `utils.safe_zip_parts`）；capture 输出到 gitignored 的 `user-data/` 并生成 manifest.json + SHA256SUMS.txt；capture/deploy 检测应用进程运行会告警（Windows tasklist / POSIX pgrep，声明于 `process:` 字段）。
- 配置声明：`configs/common.yaml` 新增 `app_configs.copyq`（target `%APPDATA%/copyq`、include 6 类文件、exclude `*.bak*`/`*.log`）；`EffectiveConfig.app_configs` 属性；dict 递归合并天然支持跨层。
- 设置模板入库：`tools/copyq/`（copyq.ini + copyq-commands.ini，**不含**剪贴板历史；历史只走私有渠道）。
- 测试：`tests/test_appconfig.py` 20 项全过；全量 `pytest tests` 103 passed（4 个失败为 test_discovery 存量问题，与本任务无关）。
- README「命令参考」新增 appconfig 命令与 CopyQ 迁移完整流程；`.gitignore` 增加 `user-data/`。

### 私有 Release（仓库 `agent-software-packages`，tag `user-data-2026-10-21`，release id 419309959）

- 资产：`copyq-config-20261021.zip`（2,415,343 字节，SHA-256 `a90b2b0723cd2ba1186e526d2b64d8efdbda93f390fbf30ac234cf346059d980`）+ `SHA256SUMS.txt`；GitHub 端 digest 与本地双向校验通过（VERIFY-PASS）。
- 内容：copyq.ini、copyq-commands.ini、copyq_tabs.ini、copyq-filter.ini、copyq_geometry.ini、两个剪贴板历史 tab（`&Clipboard` 2.56MB + `agent` 41KB）；排除 `.bak*`/`*.log`/空 themes 目录。
- Release body 已更正：来源实为 CopyQ 3.12.0（初版误写 16.0.0）；含恢复方法与安全边界声明。
- 上传脚本：`work/upload_copyq_release.py`（gitignored）——token 经 `git credential fill` 现取现用不落盘，带重试，支持资产替换与 PATCH release body；**可复用于后续 user-data 刷新**。
- 隐私验证：未认证访问 Release 页面返回 404。

### CopyQ 实机配置（模板增量提交 `7cb1a7f` 已推送）

- **条目 20 行截断已生效**：`copyq.ini [Plugins] itemtext\max_lines=20`，截图实测列表显示 line-1…line-20 + `…`。
- **预览默认关闭**：`preview()`=false 并落盘（`copyq_geometry.ini` MainWindow_state）；F7 开启底部预览面板显示完整内容（截图实测 30 行全显），再按 F7 关闭。
- 选项定位证据：20 行上限在 **itemtext 插件**（libitemtext.dll 字符串 `max_lines`="Maximum number of lines to display (0 to show all)"、`max_height`=像素上限，保持 0）；核心 `copyq config` 不暴露插件选项 → 必须走「退出 CopyQ → 改 ini → 启动」。
- 发现**本机实装 CopyQ 3.12.0**（32 位，Qt 5.13.2，`copyq version` 实证）；交付包里的 16.0.0 安装器从未在本机执行——升级决策留给用户（max_lines 选项名上游延续，配置可平移）。
- 测试残留已清理：`__cfgtest` 临时标签页（`removetab` + ini `tabs=` 行手工修正），close_on_unfocus 已恢复 true，临时截图/探针文件已删。

## 关键决策与拒绝方案（避免重走弯路）

1. **「按条目行数自动开关预览」在 3.12 不可行**：扫描 copyq.exe 全部 `Scriptable`/`ScriptableProxy` 符号，无选中变化事件（只有 `currentItem`/`selectedItems` 等查询）；命令类型只有 menu/global-shortcut/script。已向用户说明，给出 F7 等价用法，并**提出半自动方案待确认**：自动命令在剪贴板变化时按新条目行数 `preview(lines>20)`（浏览历史仍需 F7）。
2. **CLI 捕获 GUI 程序 stdout**：pwsh 直捕 `copyq.exe` 输出会得到空（GUI 子系统），必须 `cmd /c "... > file 2>&1"` 重定向后读文件。
3. **CopyQ 窗口截图**：`close_on_unfocus=true` 会在控制台抢焦点时自动藏窗导致截到下层窗口——截图前临时置 false，截完恢复。预览 dock 曾因 MainWindow_state 存了 0 尺寸而不可见：修复 = 保留 `MainWindow_geometry`、删除 `MainWindow_state` 行重置布局，再用 F7（应用自身动作）以默认尺寸重建 dock。
4. **剪贴板历史是个人数据**：绝不入 Git/离线包/公开仓库；agentctl 模板只含设置文件，历史只走私有 Release。

## 未完成与下一步

1. **半自动预览方案**（用户尚未确认）：如确认，在 copyq-commands.ini 增加自动命令（脚本判行数切 `preview()`），同步模板与私有 Release；注意 `isClipboard()` 防自触发、非文本数据守卫。
2. **CopyQ 3.12.0 → 16.0.0 升级决策**：安装器在 `packages/installer-transfer/shared/apps/CopyQ_16.0.0_*.exe`；升级后需重新验证 max_lines/preview 行为并刷新备份。
3. 并行会话正在开发 **machine_setup**（agentctl/bootstrap.py、cli.py、config.py、doctor.py、machine.py、tests/test_machine.py、configs/common.yaml、README.md 均为对方未提交工作）——**不要动、不要提交、不要还原**；progress.md 中对方的 zoxide 行（行13）与阻塞行改动同样待对方提交。
4. （既有待修，非本会话引入）agentctl update 重链用拉取前旧配置；test_discovery 4 项存量失败且全量 pytest 会污染真实 configs/personal.yaml（本会话复现一次并 `git checkout --` 还原）。

## 相关文件与状态

- 本会话提交：`b117334`（appconfig 全套）、`7cb1a7f`（max_lines 模板），均已推送 `origin/master`；`c22a725`（zoxide 约定）为并行会话所提交。
- 工作树遗留（对方所有）：README.md、agentctl/bootstrap.py、agentctl/cli.py、agentctl/config.py、agentctl/doctor.py、agentctl/machine.py、configs/common.yaml、tests/test_machine.py、progress/progress.md 部分行；`skills/serial-debug.7z` 为更早遗留未跟踪文件。
- 本会话产物：`user-data/copyq/`（抓取+manifest+SHA256SUMS，gitignored）、`user-data/copyq.zip`、`user-data/release-stage/`（上传素材）、`work/upload_copyq_release.py`（复用脚本）。
- 实机配置：`%APPDATA%\copyq\copyq.ini`（max_lines=20）、`copyq_geometry.ini`（预览关）。
- progress.md 中本会话的快照更新（时间戳、软件交付行、归档行）在工作树，随本 handoff 提交（见下）。

## 验证证据索引

- 截图（已删临时文件，结论记录于此）：列表 20 行+`…`；预览面板完整显示 30 行条目。
- `pytest tests/test_appconfig.py`：20 passed；`pytest tests`：103 passed / 4 failed（存量）。
- Release API 验证输出：`VERIFY-PASS`（asset digest 与本地一致）；未认证 Release 页 404。

## 建议技能

- `git-delivery`：后续模板/配置修改的验证与提交推送。
- `handoff`：保持手动调用，本文件即其产物。
- 无固件/嵌入式议题，`firmware-mentor` 不涉及。
