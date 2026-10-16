# Handoff：vercel-labs/skills CLI 集成（2026-10-16）

会话：DeepSeek Harness Web GUI（http://127.0.0.1:5719），2026-10-16 上午；无可用会话 ID/链接。
用户请求：「https://github.com/vercel-labs/skills 帮我装这个，验收后适配并传到 agent-workspace」。

## 目标与范围

- 安装 vercel-labs/skills（实为 npm 包 `skills`——开放技能生态的 CLI 安装器，非技能集合；仓库自带唯一技能 find-skills）。
- 验收后在 agent-workspace 适配入库并推送。

## 本次完成（已验证）

**安装**：`npm install -g skills` → v1.7.2。Node v24.15.0 满足 ≥22.20；装在 DSH 离线 node 前缀（`C:\Users\E0465\AppData\Local\dsh-offline\node\node-v24.15.0-win-x64`），用户终端同一 PATH 可用。

**验收**（全部在临时目录/HOME 沙箱，真实技能目录未触碰）：

- `--version` / `--help` / `add -l` / `find <keyword>`（skills.sh 搜索）正常。
- 项目级：`skills add vercel-labs/skills -s find-skills -a universal -y` → `<项目>/.agents/skills/` + `skills-lock.json`（含 source/computedHash）；`remove <name> -y` 干净移除。
- 全局：HOME/APPDATA 重定向沙箱中 `add -g -a pi -y` **精确落入 `~/.agents/skills/find-skills`**，全局锁为隐藏文件 `~/.agents/.skill-lock.json`。
- 坑 1：全局装不带 `-a` 会自动探测 agent 并强制附加全部 universal agent，喷洒到所有 agent 目录（沙箱中 PromptScript 报错）；文件仍会落到 `~/.agents/skills`。
- 坑 2：`remove` 带单个 `-a` 时，若检测到其它 agent 共用 canonical 拷贝会故意保留文件（上游 #287 保护）。

**适配入库**（提交 `2ebb8aa`，4 文件 +194/−2）：

- `skills/find-skills/SKILL.md`：上游 v1.7.2 原样（SHA256 一致）+「本环境适配」节（`-a pi` 装法、remove 不带 `-a`、与 agentctl junction 共存规则、内网限制、遥测开关）。
- `configs/common.yaml`：skills 列表 +`find-skills`（源目录 46→47；common 42 / personal 44 / company 44 / intranet 43）；`tools` +`skills`（doctor `tool:skills` PASS）；`resources.npm.skills: version: null` 手动登记。
- `README.md` 新增 §12「skills CLI（社区技能生态）」；`progress/progress.md` 概况更新。

**登记方式说明**：本机 `npm ls -g --json` 不输出 `resolved` 来源字段，`agentctl adopt npm:skills` 按设计报 `adopt-insufficient-evidence` 拒猜，故手动登记（来源已知：公网 npm registry 亲自安装）。

**验证**：`agentctl link` 44/44 healthy；doctor `tool:skills` PASS、skills 44/44（secrets FAIL=COMPANY_TOKEN MISSING 为本机既有状态，非本次引入）；`agentctl diff --provider npm` 中 skills 为 MATCH；find-skills 已出现在本会话技能目录。

## 未完成 / 待办

1. **推送**：提交 `2ebb8aa` 未推送——DSH 会话内 `git push` 被 argv 改写拦截（报 `git: 'C:\Program Files\Git\cmd\git.exe' is not a git command`，与 2026-10-14 handoff 记录一致）。**需用户在自己终端 `git push`**（连同本次 handoff 提交）。
2. 其余环境未接入：个人机/内网机待各自 `agentctl update`；注意已知缺陷——update 重链用 pull 前旧配置，新增启用的 skill 需手动 `agentctl link`。
3. 内网机 skills CLI 未安装（需 npm registry；无资源声明会显示 MISSING，符合预期）。

## 既有问题（本次发现，未修，与本次改动无关）

- `tests/test_discovery.py` 4 项失败（stash 对照验证为存量）：`test_snapshot_commit_and_failure_preserves_baseline`、`test_scan_adopt_diff_then_missing_acceptance`、`test_custom_profile_batch_pin_and_ignore_dry_run`、`test_quick_does_not_check_unscanned_declarations_as_satisfied`。且失败用例会把 `resources: npm: example` 测试数据**写进真实 `configs/personal.yaml`**（本次已 `git checkout` 还原）——疑似用例工作区隔离缺陷，待修。
- 工作树遗留未跟踪文件 `skills/serial-debug.7z`（上次会话产物，未纳入本次提交）。

## 关键决策与被拒方案

- **全局装法定为 `-a pi`**：pi/dexto/fx/kimi-code-cli/loaf 的 `globalSkillsDir` 恰为 `~/.agents/skills`；DSH 读 `~/.agents/skills` 与 `~/.dsh/skills`，**不读** `~/.codex/skills`（`~/.codex/skills` 里的 hatch-pet 不在会话目录，反证）。`universal` agent 的全局目录是 xdg config（Windows 上非 `~/.agents`），不采用。
- **CLI 装在 DSH node 前缀**：用户 PATH 即此 node（无独立 node 安装）；接受 DSH 换 node 版本后重装的成本，由 resources/doctor MISSING 提示。
- **遥测不擅动**：不默认改用户环境变量；文档写明 CLI 向 skills.sh 发事件参数（版本/来源/技能名，无机器标识），`DISABLE_TELEMETRY=1` 可关。
- **SKILL.md 保持上游原样 + 追加适配节**：便于跟上游更新（同 ui-ux-pro-max 入库惯例）。

## 相关文件 / 状态

- 提交 `2ebb8aa`（`feat(skills): integrate vercel-labs skills CLI and find-skills skill`）；origin/master 在 `41005cb`，本地领先。
- 工作树：仅 `?? skills/serial-debug.7z`（非本会话产物）。
- 验收临时目录已清理；无运行中作业。

## 建议技能

- 无必须。后续若修 test_discovery 隔离缺陷，可考虑 `tdd` / `diagnosing-bugs`；`firmware-mentor` 仍按 AGENTS.md 仅显式调用。
