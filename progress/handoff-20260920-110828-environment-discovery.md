# Environment Discovery 设计交接

日期：2026-09-20 11:08（Asia/Shanghai）。未取得可验证的对话 ID 或分享链接。

## 目标、授权与当前阶段

项目是 agent-workspace，Python CLI 名称 agentctl。长期目标为 AI Development Environment as Code；本轮限定 Discover → Normalize → Compare → Adopt，不一次实现整机安装恢复。

用户提供长篇实现需求，并显式调用 grill-me（该技能转入 grilling）。两轮共 23 项问题，用户均回答“全按推荐”。随后已输出汇总方案，并依据 grilling 要求请用户最终确认共同理解 / 开始实施；用户下一条是显式调用 handoff，没有给出最终实施确认。本次 handoff 仅授权归档及相应 Git 交付，不能将其解释为已经开始功能实现。下一次用户若明确要求按方案实施，即满足继续条件，不要再询问已经接受的逐项决策。

原始需求附件位于当前主机的 `C:/Users/49393/.codex/attachments/9b71424e-d801-4030-b55b-8c7c3d811224/pasted-text.txt`。该路径不便跨机器使用；本归档保留接续必需的范围、决策、约束和验收。已确认决策优先于原始附件中冲突示例。

## 已完成及验证边界

- 只读子代理完成仓库架构核查；主代理完成两轮设计审问与方案汇总。
- 功能代码、配置、依赖、README 和测试尚未修改；不存在“已实现但未验证”的功能。
- 未运行 pytest，未实测 winget、uv、pipx、npm、pnpm、code 的输出格式或可用性。下述架构结论来自静态阅读，不等于行为测试通过。
- 本次 handoff 新增根 AGENTS.md、本归档及 progress.md；只对这些文档进行内容、引用和 Git 差异验证。
- 没有需要保留的后台进程、临时脚本或正在运行的子任务。

## 现有架构事实与风险

- [pyproject.toml](../pyproject.toml)：Python 3.10+，现有运行依赖仅 PyYAML；入口 `agentctl.cli:main`。
- [cli.py](../agentctl/cli.py)：argparse + HANDLERS 分派，可直接新增子命令。
- [bootstrap.py](../agentctl/bootstrap.py)：建立工作区、环境标记、env 模板、Python 项目依赖、Skill 链接并运行 doctor；没有系统包、Node 全局工具或扩展的安装能力。
- [doctor.py](../agentctl/doctor.py)：`tools` 主要作为可执行文件检查名单，不是可重建的软件安装声明。
- [config.py](../agentctl/config.py)：common + profile + local.yaml；字典递归合并，普通列表按完整元素相等去重，名为 targets 的列表整体替换。`.env` 是独立的 Secret 名称/存在性通道，不参与 YAML merge。
- [environment.py](../agentctl/environment.py)：profile 可以是 configs 下现有的任意合法名称，不能硬编码成三种。现有 YAML dump 不保留注释。
- [utils.py](../agentctl/utils.py)、[bundle.py](../agentctl/bundle.py)：有链接备份与导入前整包备份，但没有通用配置原子写回事务；dry-run 由各操作传递 bool。
- subprocess 目前分散；新增查询执行器应局部引入，不为此大规模重构历史调用。
- `.agentctl/` 目前既未加入 .gitignore，也未加入 bundle.DENY_DIRS。导出存在非 Git/无提交仓库的遍历回退，仅修改 gitignore 不足以排除本机状态。
- export Secret Scanner 是正则检查，不能充当任意输出的通用脱敏器；历史错误路径存在输出原文的情况，本轮不能声称整个项目已经无泄漏。
- [test_bundle.py](../tests/test_bundle.py) 的假 Secret 使用行内 `# agentctl-canary` 标记；遵守既有约定并保持导出扫描器兼容。
- [README.md](../README.md) 的 ROADMAP 曾将 adopt 用于迁入存量 Skill，需消除与新增命令的语义冲突。

## 已接受的产品决策（Q1–Q23）

### 范围与状态（Q1–Q6）

1. 本轮允许登记后尚不能自动安装；文档清楚说明 bootstrap 的能力边界，已有行为兼容。
2. NEW / scan --new 表示未登记，不代表刚安装；安装时间不能凭空推断。
3. 当前符合情况与历史变化分开。当前为 NEW、MATCH、DRIFT、MISSING、UNKNOWN 或无法判断；历史可表示出现、消失、版本变化、恢复、未变化、不可比较。MATCH 可同时附带 RESTORED。
4. scan 与 diff 不写文件，只有 snapshot 保存历史基线。Previous 是上次显式保存的成功快照，不是上次 scan。
5. Provider 状态区别 success、unavailable 与 error。命令不存在为 unavailable，执行/解析失败为 error；两者不阻止其他 Provider。只有完整成功覆盖的范围才允许判 MISSING。UNKNOWN 特指资源来源/管理方式不明确，不兼作扫描失败。
6. 按 `(provider, id)` 识别资源，不跨管理器去重。第一版仅扫描当前命令对应的管理器环境和编辑器实例；记录必要扫描范围，范围不同的快照不可直接作历史比较。多 Node 环境、多编辑器实例扩展留待后续。

### 登记、安全与自动化（Q7–Q13）

7. 默认只要求资源存在，Observed 版本留在快照；显式参数才锁精确版本。第一版不实现复杂版本区间。
8. 每次 adopt 必须显式指定 --profile，common 也不例外，不默写当前环境。
9. --all 仅收录未登记、未忽略、来源足够明确的候选；命令本身视为确认，不重复交互；不借 adopt 更新既有声明或 DRIFT。支持 dry-run。
10. 来源不明的资源可以显示，但不直接登记为可重建资源；人工补录来源流程暂缓。
11. ignore 默认本机、按精确身份匹配，只隐藏未登记提醒，不隐藏已声明资源的 MISSING/DRIFT；提供查看及移除操作，不加通配符。
12. 输出只允许经过校验的必要字段，不持久化任意 metadata，不回显原始 stdout/stderr；错误用 Provider、退出码、超时/解析类别表示。凭据来源拒绝写入。接受诊断信息减少的代价。
13. 默认差异不导致失败；另提供脚本检查模式。退出码细化见 Q22。

### 配置与命令语义（Q14–Q17）

14. 新增 resources 映射，复用字典合并；旧 tools 保留原义。示例：

```yaml
resources:
  npm:
    "@openai/codex":
      version: null
  winget:
    BurntSushi.ripgrep.MSVC:
      version: "14.1.1"
```

`null` 表示不限定版本；profile 可覆盖 common，local 可再覆盖，显式 null 解除上层锁定。第一版不支持下层取消继承资源。

15. adopt 按目标共享声明查重：personal 检查 common + personal；common 只查 common。local 和其他 profile 不阻止写入目标共享层。继承到的资源不重复登记，已有锁定不被 adopt 改写；提示 local 覆盖产生的最终效果。
16. `adopt --provider npm --profile personal` 只展示候选；`adopt --all --provider npm --profile personal` 才批量写入。无资源且无 --all 时只展示候选。明确单项资源可以直接登记。
17. `--pin-version` 仅锁定可靠观测的精确版本；单项未知则拒绝，批量任一候选无法满足则整批不写。Desired 锁定而 Observed 版本未知时为无法判断，不是 MATCH/DRIFT；不提供通过 adopt 更新旧锁定的功能。

### 快照、写回与检查（Q18–Q23）

18. snapshot 整次提交：任一已尝试 Provider 执行/解析失败，不替换旧快照。正常 unavailable 可保存并标未覆盖；历史比较需前后成功覆盖同一范围。首次无基线不报告恢复。
19. scan 只读指 agentctl 不主动改变安装资源、环境配置和本机状态；不保证第三方管理器内部缓存/日志零写入。只用查询命令，尽可能禁网络更新和交互；不更新源、不登录、不自动接受协议，必要时报告无法完成。
20. YAML 写回保留注释与顺序，允许增加必要的小范围往返编辑依赖（具体库尚未选定）。写入前重新解析校验、检查并发修改，备份原文件并原子替换；发现并发修改则停止，不覆盖。
21. `.agentctl/state/current.json` 只保留最近成功基线；`.agentctl/ignore.yaml` 保存当前忽略规则；配置备份放 `.agentctl/backups/`，不自动清理，说明手工恢复，不承诺现有 restore 已支持。整个目录排除 Git 和离线包。snapshot 也支持 dry-run；备份路径不是采集 Secret 的例外，不额外复制 Secret 文件。
22. 退出码：0 正常（检查模式要求已声明资源满足）；1 仅用于检查模式发现 MISSING/DRIFT；2 执行、解析、配置错误，或检查模式下已声明资源覆盖/版本不足。NEW 不阻止通过；无相关声明的 Provider 不可用不阻止通过。JSON stdout 不混入提示。
23. 本轮不新增 `.env`、SSH 或凭据存储扫描。安全测试覆盖新增外部结果、来源、配置错误及异常路径，确保 canary 不出现在 stdout/stderr、快照、日志或新声明中；不用任意自由文本或原始响应填充 metadata。

## 已汇总的接口方向

- `scan` 与 `--quick` 等价；`--full` 执行六种 Provider；`--new` 仅显示未忽略的未登记资源；`--all` 可查看忽略项；提供 `--json`。
- `diff` 重新扫描对照有效声明，MATCH 默认只汇总；保持 scan、diff、adopt、bootstrap、doctor 职责独立。
- snapshot 完整扫描并保存基线，支持 --json 和 dry-run。
- adopt 支持明确资源、--all、--provider、必选 --profile、--pin-version、dry-run。
- ignore 支持资源参数、--list、--remove、dry-run。
- JSON 设计带 schema 版本、环境上下文、Provider 状态及范围、资源对照、历史变化、汇总。具体字段名与检查模式参数名尚未编码，可按这些已定语义合理实现，不必重新问产品决策。
- Provider 负责事实发现与规范化；Manifest 表达期望；Adopt 负责显式写入。资源模型需要支持未来 MCP、Docker、Git config、runtime、shell、dotfiles，不为六种 Provider 硬编码整个架构。
- 第一版 Provider：Winget、UvTool、Pipx、NpmGlobal、PnpmGlobal、VSCodeExtension。Windows 优先；Linux/macOS 对不支持部分 graceful degradation。
- 无后台 daemon、无 LLM 检测、无自动 adopt/删除/卸载。调度及自动安装留待未来。

## 接续实施步骤与验收

1. 先读根 AGENTS 与 progress 当前概况，核对工作区。用户若尚未明确要求开始，简短确认实施；不要重复已接受的 23 项问题。
2. 阅读 README、pyproject、agentctl 各模块、配置 merge、CLI、现有 tests，核实 dry-run/backup/export scanner/链接策略；复用已有基础设施。
3. 实施前给出 CURRENT ARCHITECTURE、IMPLEMENTATION PLAN、FILES TO CHANGE、NEW FILES、COMPATIBILITY RISKS。原始需求要求先说明再实施，不要求再次批准每个内部设计选择。
4. 小步实现资源与 Provider 结果模型、安全查询执行器、六个适配器、比较器、快照/ignore 存储、保留 YAML 注释的 adopt、CLI；不大规模重构旧模块。具体新增文件名尚未定。
5. 修改 .gitignore 和 bundle 导出过滤，README 增加 Environment Discovery 与真实能力边界，替换旧 adopt 冲突说明。
6. 新增 pytest，外部命令全部 mock：Provider 命令缺失、正常/空/损坏输出、非零码、超时、版本解析；NEW/MATCH/MISSING/DRIFT/UNKNOWN/无法判断；ignored；快照二次比较、首次无基线、失败不替换、范围变化；adopt 目标层/查重/覆盖/dry-run/批量校验；ignore 移除；Secret 所有输出路径；旧配置无新字段兼容及相关旧功能回归。
7. 验收：未登记工具 scan --new 出现 → 显式 adopt → 本机 diff MATCH；模拟另一机 Provider 成功但无资源 → MISSING；Provider 不可用不能误报 MISSING。不宣称 bootstrap 已可安装新增声明。

## 工作区与交付状态

归档前工作区和暂存区均干净。分支 master，上游 origin/master，remote 为 https://github.com/493935827/agent-workspace.git；归档前 HEAD 为 d9af13d，`git log origin/master..HEAD` 为空。本次仅提交 AGENTS.md 和 progress 下两份文档，不修改功能。提交及推送结果以本次回复和 Git 实际状态为准，不在归档中预先宣称成功。

## 可用技能提示

- 项目结构与新增文件归属可用 project-structure；修改 AGENTS 用 writing-for-agents；验证提交交付用 git-delivery。
- grilling 已完成决策审问，剩余只是最后的实施确认；不自动重开新一轮问题。
- handoff 保持显式手动调用。上述建议不代替技能调用条件。
- firmware-mentor 仅在用户当前消息显式写 `$firmware-mentor` 或附该技能链接时加载；嵌入式/C/Python 主题不构成授权。
