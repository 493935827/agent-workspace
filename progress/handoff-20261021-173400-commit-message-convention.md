# handoff 提交信息规范成文（handoff）

- 源会话：DSH `session-d857c331-229e-4a9f-853b-31985fbbd329`（本 handoff 之前的完整对话）
- 项目根：`D:\App\agent-workspace`；归档时间：2026-10-21 17:34（Asia/Shanghai）
- 任务提交：`e92221d`（docs(handoff): codify commit message convention，本对话唯一代码库改动，已提交）

## 本对话目标与完成内容

用户要求「给当前 handoff 流程加一个 git commit 信息规范，先看下网上有没有类似的需求和实现」。已完成：调研 → 设计 → 成文 → 按新规范自举提交。

1. **调研结论**（细节见对话；来源均为官方一手文档）：
   - [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)：业界事实标准——`<type>(scope): <主题>` + 正文 + 页脚；`feat/fix` 关联 SemVer；`!`/`BREAKING CHANGE:` 标破坏性变更。
   - [Aider](https://aider.chat/docs/git.html)：agent 自动提交默认生成 Conventional Commits；归属元数据走 git trailer（`Co-authored-by`）或 author/committer 标记。Claude Code 同类（`🤖 Generated with` + Co-Authored-By trailer）。通行模式 = **规范主体 + git trailer 承载机器可读元数据**。
   - [git interpret-trailers](https://git-scm.com/docs/git-interpret-trailers)：trailer 官方格式（`Key: value`、key 限 ASCII 字母数字连字符），`git log --grep` 可机器解析。
   - 会话归档/交接类提交无独立业界规范；本仓库历史（`docs(progress): archive XXX handoff` 等）已在**无成文状态**下实践 Conventional Commits——故本次定位为「把既有实践成文」，不发明新体系。
   - 调研过程备注：agent-reach CLI（mcporter/gh）与内置 web_search（缺 DeepSeek API key）在本 DSH 环境均不可用，实际用 harness 的 web_fetch 直抓官方页面完成。

2. **落地改动**（均为技能文档，无代码）：
   - `skills/handoff/SKILL.md`：新增 `## Commit message format` 章节（权威定义），Verify-and-upload 规则 5 由 "meaningful message" 改为引用该格式。要点：type 词表（feat/fix/docs/refactor/test/chore/build/ci/perf/style，归档提交固定 `docs`）；scope=受影响区域（根目录归档 `progress`、组件内归档用组件名如 `serial-debug`）；主题行祈使、无句号、约 50 字符上限 72；纯归档提交用 `archive <topic> handoff` 模式；正文每条改动一个 `- ` 要点、72 字符换行、如实标注未验证项；携带归档的提交末尾加 `Handoff: <归档相对路径>` trailer（`git log --grep='^Handoff:'` 可定位，commit↔归档互链）；语言跟随仓库既有提交（本仓库英文）。含让位条款：仓库已有其他成熟风格则跟随，不强制 CC。
   - `skills/git-delivery/SKILL.md`：提交一节内联同格式中文摘要，任务提交与 handoff 提交不分叉。
   - 规范已生效验证：本次 `/handoff` 调用时，全局技能目录 `C:\Users\E0465\.agents\skills\handoff\SKILL.md`（经 agentctl 链接指向工作区副本）加载的内容已含新章节。

## 决策与理由（避免下次重复讨论）

- **成文而非新发明**：仓库 30 条近期提交已一致实践 CC，规范只是把它固定下来并补齐空白（trailer、语言、长度预算）。
- **`Handoff:` trailer 为本工作区新增设计**：借鉴 aider/Claude 用 trailer 放机器可读元数据，但内容功能化为归档路径指针，契合渐进式披露哲学（commit 只留指针，细节在归档）。本归档提交为首个实践样本。
- **git-delivery 用内联摘要而非指针**：沿用 2026-10-21 渐进式披露改版的设计结论——handoff 技能仅手动加载，日常任务读不到它，跨文件指针会失效，各技能自带必要规则。
- **不让 git-helper 承载**：它是 MVP 占位技能（"Placeholder content"），未启用真实规范职责。

## 验证证据

- 两个技能文件改动后回读核验；`skills/handoff/SKILL.md` 围栏标记 4 个（2 对配对）；`git diff --check` 与 `git diff --cached --check` 干净；frontmatter 未动。
- 纯技能文档改动，按 git-delivery 验证表（文档/技能说明行）做内容一致性 + 引用检查，未跑全量回归（无代码路径变化）。
- 本对话提交 `e92221d` 按新规范自身写成（46 字符主题、bullet 正文、无多余 trailer），提交身份与仓库历史一致（黎权锋(Quanfeng Li) <E0465@innostar-ic.com>，自动推断）。

## 工作区与 Git 状态（handoff 时点）

- 本对话仓库改动：`skills/handoff/SKILL.md` + `skills/git-delivery/SKILL.md`（已入 `e92221d`）+ 本归档 + `progress/progress.md` 索引行/概况微调（随本 handoff 提交）。
- 未跟踪 `skills/serial-debug.7z` 非本对话产物，已隔离、不纳入提交。
- master 领先 `origin/master`：既有 3 个 handoff 归档提交（`229e0cb`/`7a92d19`/`9d55512`）+ `e92221d` + 本次归档提交 = **5 个待推**。
- DSH 会话内 `git push` 被 argv 改写拦截（报 `git: 'C:\Program Files\Git\cmd\git.exe' is not a git command`，与 2026-10-16 handoff 记录一致）——需用户在自己终端推送（历史推送正常，本地代理 127.0.0.1:7897）。

## 遗留与下一步

1. **用户在自有终端 `git push`**（5 个待推提交，含本次归档）。
2. 后续所有 handoff/任务提交按新规范执行；既有历史提交不回溯改写。
3. 无其他未尽事项；agentctl 两项待修缺陷（update 重链旧配置、test_discovery 污染）仍待用户决策，见概况 agentctl 行。

## 建议技能

- 无特别建议；`handoff` 保持用户手动调用，本文件即其产物。
