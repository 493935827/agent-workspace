# 交接记录：progress 管理改版为渐进式披露三层

## 对话识别

- 来源对话：DeepSeek Harness Web GUI，起于「当前的管理项目progress.md的是哪个skill」（本环境未暴露可复制的会话 ID/链接；以本文件与 `progress/progress.md` 归档行识别本对话）
- 本对话本地提交：`2a5dba6`（渐进式披露改造，5 文件）、`e7e66f1`（handoff 边界澄清，AGENTS.md）——已提交未推送；本归档提交为第 3 个待推提交

## 目标与范围

实际使用中 `progress/progress.md` 的概况区被各对话按日期/对话堆成流水账（提交号、测试数字、命令输出、证据细节），违背「概况只回答现状」的定位。用户要求：整体按渐进式披露改版；随后澄清三个设计问题——progress 何时更新、handoff 何时调用、任务完成是否自动 handoff。

## 已完成并验证

1. **三层契约**（权威定义：`skills/handoff/SKILL.md` §Maintain `progress/progress.md`）：概况 = 白板（≤10 简短行、每主题一行、只写主题当前状态与下一步；原位改写不追加，细节/证据下沉 handoff 或权威文档并链接化，超标时先压缩再下沉）；归档行 = 每对话一句定位；handoff = 全部细节。每层只指向下一层、不吸收；含发现超标文件时就地向预算压缩的补救规则。
2. **project-structure SKILL.md**（§3 读取规则、§4 更新规则）：非 handoff 的日常进度更新遵守同一契约。
3. **documents.md**（project-structure references）：创建条件边界列与初始进度模板说明对齐新格式。
4. **根 AGENTS.md**：读取/更新约定改为渐进式披露版；handoff 保持手动调用并明确边界——对话将结束或上下文将尽而工作未完时提醒用户调用，**任务完成本身不构成调用理由**。
5. **progress/progress.md 重写为示范**：概况 18 条日期流水账 → 9 主题行（目标/里程碑/Skills/agentctl/软件交付/开发配套/安全边界/阻塞/下一步）；压缩时逐条核对细节落点，无信息丢失。
6. **设计结论**（已入约定）：progress 更新与 handoff 解耦（实质进度变化即原位改写概况，小步不更新）；handoff 看对话边界不看任务边界；任务完成的可恢复性由概况原位改写 + git-delivery 提交双兜底，不自动 handoff（否决理由见下）。

### 验证证据

- 概况 9 行（≤10 预算，脚本核对）；10 个归档链接全部可解析；`git diff --check` 干净；两次提交 staged 范围均与任务文件一致（5 文件 +1 文件）。
- 纯文档改动，无代码回归需求；`git diff --cached --check` 每次提交前通过。

## 阻塞与未完成

- **推送被网络阻断**：走本机代理推送时 SSL 握手失败（`schannel: failed to receive handshake`），`ls-remote` 同样失败——代理到 github.com 链路当前不可达，非配方失效。本地 `master` 领先 `origin/master` 3 个提交（含本归档提交）。
- 未验证项：无。工作区遗留未跟踪文件 `skills/serial-debug.7z`（本对话之前已存在，来源不明，未处理、未入提交）。

## 关键决策与否决方案

- **否决「任务完成自动 handoff」**：可恢复性已由概况原位改写（工作状态）+ git-delivery 提交（代码状态）保证；handoff 的增量只有对话级上下文（决策与否决方案、证据位置）；自动触发含 commit/push 副作用越过授权边界，且会让归档行/handoff 文件按任务数膨胀成薄噪声（正是本次治理的沉淀问题换个位置复发）。
- **契约权威定义放 handoff SKILL.md，project-structure 内联操作摘要**：handoff 仅手动加载，日常任务读不到它，跨文件指针会失效；两技能触发场景不同，各自携带必要规则。
- **概况压缩落点核对**：skills CLI 参数坑 → README §12；PySide6 venv 注意 → handoff-20261013；2026-10-12 ui-ux-pro-max（无独立 handoff）→ 折叠进里程碑行；并修正两处过时状态——`4fec1d1` 实际已由用户推送、旧推送积压已清空（核实 `origin/master` 已到 `6fc6126`）。
- **dist/ 副本不同步**：`dist/agent-workspace-v0.1.0-offline/workspace/skills/` 是冻结的 v0.1.0 打包产物，本次改版未同步，属预期，勿误认为漏改。

## 推送配方（网络恢复后执行，来源：`../skills/serial-debug/progress/progress.md` 阻塞行）

```powershell
$env:NO_PROXY=""; $env:HTTPS_PROXY="http://127.0.0.1:7897"; $env:HTTP_PROXY="http://127.0.0.1:7897"; $env:GCM_INTERACTIVE="never"
git -c credential.helper= -c credential.helper=manager -C . push origin master
```

（`git -C .` 形态绕过会损坏 argv 的拦截器；裸 `git push` 会报 `git: '<自身路径>' is not a git command`。）

## 建议技能

- `git-delivery`：推送恢复后的交付核验。
- `handoff`：继续由用户手动调用，不自动触发。

## 下一步

1. 网络恢复后按上方配方推送 `master` 领先的 3 个提交。
2. 按用户新需求推进项目；progress 概况按新契约维护（每主题一行、原位改写）。
