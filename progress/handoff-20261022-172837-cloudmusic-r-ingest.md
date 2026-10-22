# CloudMusic_R 工程收录 agent-workspace（handoff）

- 源会话：DSH `session-e5c1492fa74d`（ID 从 DSH 临时目录路径推断，本会话内未见正式会话面板；handoff 回合 ID 不可见）
- 项目根：`D:\App\agent-workspace`；归档时间：2026-10-22 17:28（Asia/Shanghai）
- 任务提交：`d95800a`（feat(projects): add cloudmusic-r reverse-engineering workspace，已推送并核对远程引用一致）

## 本对话目标与完成内容

用户要求「将本工程加进 agent-space 并提交」。“agent-space” 经核实即本仓库 agent-workspace（zoxide 中 agent/space 均映射至此；GitHub 无同名仓库；DSH 源码无该概念）。“本工程” = `D:\App\CloudMusic_R`（网易云 orpheus 客户端逆向分析工作区）。

1. **范围确认**：给出三选项（仅脚本+README / 全量 / 全量减个人数据）后，用户选择「整个工程原样收录」。
2. **落地**：robocopy 整树 4,674 文件 / 330.63 MB → `projects/cloudmusic-r/`（FAILED 0）；提交 1,401 文件约 130 MB（orpheus/pub 全部资产、orpheus.zip 36.5 MB、_analysis 缓存与 dataset.json、analyze-*.ps1 / collect.py、UI-REVERSE-REPORT.md 等）。
3. **提交与推送**：Conventional Commits 英文提交 `d95800a`，经 `git -c alias.push= push origin master` 通道推送成功（`34fee6a..d95800a`），`git ls-remote` 核对远程引用 = 本地 HEAD；zoxide add 新目录。
4. **文档同步**：README 结构表补 `projects/` 一行；progress.md 概况新增「工程收录」行。

## 关键决策与理由（避免重复讨论）

- **放置位置 `projects/`（新顶层目录）**：work/ 被 gitignore 无法提交、agents/skills 语义不符；agentctl 仅扫描固定目录（`agentctl/workspace.py` `STRUCTURE_DIRS`），新顶层目录对 discovery 无影响。
- **强制排除 3 类文件（子树 .gitignore，文件保留在磁盘不入库）**：
  - `_analysis/webdb_copy.dat`（106.1 MiB）：超 GitHub 100 MiB 单文件硬限制，收录会令此后所有 push 被整体拒绝；
  - `_analysis/cookies_copy.db`：会话凭据，按仓库「Secret 永不进入仓库」铁律排除；
  - `_analysis/.venv/`（约 3,275 文件）：Python 环境非工程内容。
- **字节保真**：仓库 core.autocrlf=true，为满足「原样」在子树加 `.gitattributes`（`* -text`）禁用 EOL 转换。
- **隐私已知情同意**：范围问题明确告知 cache_*.json / dataset.json 为个人听歌数据后用户仍选全量收录 → 已随公开仓库上线；collect.py 内含用户本人网易 UID（432395459 / 17856823984）。今后如需撤下涉及改写 git 历史。
- **`git diff --cached --check` 尾随空白告警**：全部来自第三方提取文件（app.html、native-commands.txt 等），按原样原则保留未修，check-exit 2 属预期。

## 验证证据

- robocopy 摘要：4674/4674 文件、330.63 MB、FAILED 0。
- 暂存审计：staged 1,401 文件；staged 清单中无 webdb/cookies/.venv；`git check-ignore -v` 三项命中子树 .gitignore；排除文件保留在磁盘（git status 对其无输出）。
- 非工程区仅 README.md、progress/progress.md 入本提交；未动用户既有 untracked（skills/serial-debug.7z）。
- 推送 exit 0；`git ls-remote origin refs/heads/master` = `d95800af3d3e…` = 本地 HEAD。

## 工作区与 Git 状态（handoff 时点）

- master 与 origin/master 同步（0/0）；工作树仅剩既有 untracked `skills/serial-debug.7z`（非本对话产物，继续隔离不纳入）。
- `D:\App\CloudMusic_R` 原目录未动（未 git init）；workspace 内副本为收录版本。
- 本机 local.yaml environment: **company**（在线区），本归档提交与推送按 handoff 技能规则执行。
- 离线包影响：`agentctl export` 默认 git 模式打包全部 tracked 文件 → projects/ 的 1,401 文件（约 130 MB）会进离线包；walk 模式还会额外带上未 track 的 webdb/cookies 副本（幸而默认不 walk）。近期出离线包前需用户确认体积与内容策略（现有 dist 包仍钉 `da09a49` 未重打）。

## 遗留与下一步

1. 本任务无未完成项；用户下一指令未定。可能的延续：CloudMusic_R 逆向分析继续（工程本体仍在原目录工作，workspace 副本无自动回写机制——原目录后续产生的新文件需决定同步/重收录策略），或 agent-workspace 常规维护。
2. agentctl 两项存量缺陷（update 重链用拉取前旧配置、test_discovery 污染真实 personal.yaml）仍待用户决策，见概况 agentctl 行。

## 建议技能

- 无特别建议；若继续 CloudMusic_R 逆向，可用 reverse-engineer-anything（REA 6.7.0 已注册，Ghidra 12.1.4 就绪于 D:\App\tools，本机 PE 实测仍未做）。
