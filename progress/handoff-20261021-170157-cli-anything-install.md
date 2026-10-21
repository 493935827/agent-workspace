# CLI-Anything 调研与装机

- 会话：`session-ce3ae958b0b0`（DSH Web GUI，2026-10-21）
- 主题：调研 HKUDS/CLI-Anything 并把工具链装入本机 agent 环境

## 目标与范围

用户要求「装一个让 agent-workspace 支持」CLI-Anything（https://github.com/HKUDS/CLI-Anything）。范围：装 cli-hub 工具与相关 skill；不改 agent-workspace 仓库代码（本次仅归档与索引由本 handoff 产生）。

## 本次完成（均已验证）

1. **调研**：HKUDS/CLI-Anything —— 55.7k stars、Python、Apache-2.0、arXiv:2606.03854，港大 HKUDS 出品（LightRAG 同门）。两大块：
   - CLI-Hub：现成 agent-native CLI 生态 + 包管理器（`pip install cli-anything-hub`）；
   - 7 阶段生成器：HARNESS.md 方法论，对有源码软件自动生成 Click CLI harness（分析→设计→实现→测试→文档→发布→refine）。
   - 核心设计原则：包装真实软件不重造（生成合法项目文件后调真实后端渲染，无降级 fallback）、全命令 `--json`、REPL+子命令双模式、输出必须验证 magic bytes 而非只看退出码。
2. **cli-hub v0.4.1 装机**：`uv tool install cli-anything-hub`。本机 Python 是 uv 托管（PEP 668 拒绝 `pip install --user`），uv tool 是正确姿势。shim `%USERPROFILE%\.local\bin\cli-hub.exe`，该目录已在用户 PATH（任何终端/会话可用）。验证：`cli-hub list` 成功拉取在线注册表，3D/AI/AUDIO/AUTOMATION 等分类齐全（blender、freecad、ollama、n8n、audacity…60+）。
3. **cli-hub-meta-skill 装机**：`C:\Users\E0465\.agents\skills\cli-hub-meta-skill\SKILL.md`（5477B）。skill-installer 脚本对 GitHub 下载超时，改为 Invoke-WebRequest 直接抓 raw.githubusercontent.com 落盘。会话技能目录已刷新生效（当轮即出现在 available_skills）。
4. **确认 skill 清单**：仓库 `skills/` 目录共 68 个 per-software skill（cli-anything-blender/gimp/lldb/eez-studio…）+ cli-hub-meta-skill，逐个按需安装，本次未装。与嵌入式背景相关的：`cli-anything-lldb`（原生调试，唯一沾调试器）、`cli-anything-eez-studio`（LVGL UI + SCPI 仪器）、nsight-graphics/renderdoc（GPU）。
5. **生成器 skill `cli-anything` 装机**（用户选定）：浅克隆仓库到 `%TEMP%\CLI-Anything-installer`，运行官方 `codex-skill/scripts/install.ps1`，以 `$env:CODEX_HOME = "C:\Users\E0465\.agents"` 重定向安装目标到 `C:\Users\E0465\.agents\skills\cli-anything`。组装结果 24 个文件：SKILL.md、`references/HARNESS.md`（方法论 SOP）、`references/commands/` 5 个命令规范、`references/guides/` 8 份指南、`scripts/{repl_skin,skill_generator,preview_bundle}.py` + `templates/`、`references/docs/PREVIEW_PROTOCOL.md`。注意本机 shell 里 `pwsh` 不在 PATH，脚本用 `powershell.exe -ExecutionPolicy Bypass -File` 跑通。会话技能目录已出现 `cli-anything`。
6. **清理**：临时克隆已删除；agent-workspace 工作区未留任何临时文件。

## 已实现未验证

- 生成器从未实际跑过一次 harness 生成。README 交代的前提：需要强模型（Opus/Sonnet/GPT-5 级）、目标软件**有源码可分析**、常需多轮 `/refine` 迭代。
- `cli-hub install / launch` 未实测装任何具体 CLI。注意：不少 CLI 只是 agent 接口，本机还需装有上游软件本体（如 GIMP、Blender）。
- codex-skill 的 SKILL.md 按 Codex 约定书写（引用 `references/HARNESS.md` 相对路径），在本 DSH 环境指令通用但未经实战校准。

## 剩余工作 / 下一步

等用户指定目标软件后实战，二选一：
- **现成路线**：`cli-hub search <关键词>` → `cli-hub info <name>`（看依赖）→ `cli-hub install <name>` → `cli-hub launch <name>`。
- **生成路线**：对有源码的软件加载 skill `cli-anything` 跑 7 阶段生成（可对软件本地路径或 GitHub 仓库）。
- 若某软件高频使用，可从仓库 `skills/<name>/` 装 per-software skill：单 SKILL.md 文件直接抓 raw 落盘即可（参照 meta-skill 的做法）。

## 关键决策与拒绝路径（避免重蹈）

- **不用 `pip install --break-system-packages`**：uv 托管 Python 禁改；改用 `uv tool install`（隔离环境 + PATH shim）。
- **skill 安装不走 skill-installer 脚本**（本次实测其 GitHub 下载超时，且默认装 `~/.codex/skills`）；meta-skill 单文件直接抓 raw。生成器**必须**用官方 install.ps1（它从 `cli-anything-plugin/` 组装 references，手工拷 SKILL.md 会缺 HARNESS.md），用 `CODEX_HOME` 重定向落到 `C:\Users\E0465\.agents\skills`——因为 DSH 会话技能目录读 `.agents\skills`（已实证：cli-hub-meta-skill 放进去当轮即出现在目录）。
- **不全量安装 68 个 per-software skill**，避免技能目录膨胀；用到哪个装哪个。

## 环境/文件清单

- 本机工具：cli-hub 0.4.1（uv tool 管理，`uv tool list` 可查，升级 `uv tool upgrade cli-anything-hub`）。
- 本机 skill：`C:\Users\E0465\.agents\skills\cli-hub-meta-skill\`、`C:\Users\E0465\.agents\skills\cli-anything\`。
- 仓库引用：HKUDS/CLI-Anything（README、HARNESS.md、skills/、codex-skill/scripts/install.ps1）。
- agent-workspace 仓库：本次任务未改任何代码；仅本 handoff 与 progress.md 索引。

## 建议技能

- 使用 CLI-Hub / 生成器时：会话技能目录已有 `cli-hub-meta-skill` 与 `cli-anything`，按其 SKILL.md 指引执行即可。
- 目标软件的背景调研仍走 `agent-reach`。
