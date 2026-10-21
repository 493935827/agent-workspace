# Handoff：REA 逆向环境接入 DSH + Ghidra 配置

- 会话：`session-23bc19fc1440`（2026-10-21，DeepSeek Harness Web）
- 主题：把 [morluto/rea](https://github.com/morluto/rea)（rea-agents 6.7.0）接入本机 DeepSeek Harness，并配置 Ghidra 原生分析引擎
- 状态：**安装与配置全部完成并验证**；Ghidra 在 MCP 会话内生效需重启 Harness（见"待办"）

## 目标与范围

让 agent-workspace 的 agent 会话具备逆向工程能力：MCP 工具（`mcp__rea__*`）+ 配套 skill + 原生二进制反编译引擎（Ghidra）。纯环境配置任务，未改工作区任何项目文件。

## 已完成并验证

### 1. REA 本体（npm 全局）

- `rea-agents@6.7.0` 全局安装于 DSH 自带 Node 前缀：`C:\Users\E0465\AppData\Local\dsh-offline\node\node-v24.15.0-win-x64\node_modules\rea-agents`
- `rea --version` → 6.7.0；目录含 153 个 CLI 命令、207 个 MCP 工具、6 个 prompts
- 教训：`npm install -g` 首跑 420s 超时报错，但**实际已装完**——重试前先验证再重装

### 2. DSH 注册（Cordis patch，非普通 mcpServers JSON）

- 注册文件：`C:\Users\E0465\.dsh\cordis.patch.yml`（`DSH_HOME` 本机显式设为 `C:\Users\E0465\.dsh`）
- 条目：`id: rea-mcp` → `@deepseek-ai/dsh-mcp-client`，stdio，命令为本机 node.exe + 全局 `rea.mjs mcp`，`env` 段含 `GHIDRA_INSTALL_DIR`、`JAVA_HOME`（最终 13 行，见文件）
- 旧版备份：`cordis.patch.yml.rea.backup`
- skill：`reverse-engineer-anything` v42 → `C:\Users\E0465\.agents\skills\reverse-engineer-anything`（SKILL.md + 6 份 references），本会话 skill 目录已刷新可见
- **实测**：本会话直接调 `mcp__rea__binary_session` 成功握手（server rea-agents 6.7.0，client dsh-mcp-client），即注册写入后当前会话即已生效

### 3. Ghidra 12.1.4 + JDK 21（`D:\App\tools\`）

| 项 | 位置 | 校验 |
| --- | --- | --- |
| Temurin JDK 21.0.12.1（64 位完整 JDK） | `D:\App\tools\jdk-21` | SHA-256 `f9d6e191…b8b4e` 与 Adoptium 官方一致（TUNA 镜像下载） |
| Ghidra 12.1.4_PUBLIC | `D:\App\tools\ghidra_12.1.4_PUBLIC` | SHA-256 `ddac49f9…d4db` 与 GitHub 官方发布一致（gh-proxy.com 加速下载） |

- 用户级环境变量已设：`JAVA_HOME=D:\App\tools\jdk-21`、`GHIDRA_INSTALL_DIR=D:\App\tools\ghidra_12.1.4_PUBLIC`（CLI 场景用）
- `rea setup --client dsh --yes` 已把两个变量写入注册 env 段（MCP 服务器场景用）
- `rea doctor --provider ghidra --json`：**全绿**——version 12.1.4 / analyzeHeadless.bat / win_x86_64 反编译器 / JDK 21 / Windows 原生管控自检（Job Object、DACL）全过，`available: true`

### 4. 下载渠道经验（本机网络慢）

- GitHub 直连仅 ~60 KB/s（543MB 要 2.5 小时）；官方源 + `gh-proxy.com/` 加速（~4-9 MB/s）+ 官方 SHA-256 兜底是可靠组合
- `ghfast.top` 对大文件回 "Forbidden by black list"；清华 TUNA 有 Adoptium 全量镜像（`mirrors.tuna.tsinghua.edu.cn/Adoptium/`）
- Windows curl（schannel）对 TUNA 报 `CRYPT_E_REVOCATION_OFFLINE` → 加 `--ssl-no-revoke`（最终有 SHA-256 校验兜底）
- 断点续传：`curl -C -` 对加速代理同样有效

## 关键决策（避免重蹈）

- DSH 的 MCP 注册走 **Cordis YAML patch**（home 级，对所有 profile 生效），不是 `mcpServers` JSON——REA 官方文档 `docs/client-configuration.md#deepseek-harness` 有专节
- 环境变量**双写**：用户级（`rea` CLI / 任意终端）+ 注册 env 段（Harness 拉起的 MCP 服务器只认后者）
- REA setup 不装 Ghidra/Java（策略性设计），且 setup 的 dry-run 计划会带自动备份路径，`--yes` 只配显式 scope（`--client dsh`）

## 未验证 / 待办（下一步的活）

1. **重启 Harness 后实测**：本会话的 REA MCP 服务器启动于环境变量设置之前，Ghidra 对它不可见。重启后：新会话调 `mcp__rea__binary_session` 确认 ghidra available → 拿一个 PE（exe/dll）走 `mcp__rea__open_binary` + `analyze_function` 实测反编译。首次冷导入+自动分析可达数分钟（默认 startup deadline 330s，大目标在注册 env 加 `REA_GHIDRA_STARTUP_TIMEOUT_MS`）
2. **Windows P0 通道边界**：仅支持 PE x86/x64/ARMNT(Thumb)/ARM64 + raw 6502；**ELF 不在此通道**，分析 ELF 需 Linux/WSL 跑 REA+Ghidra（未配）
3. 未配置的可选引擎（均按需再装）：JADX（`REA_JADX_MCP_JAR`，APK 反编译）、adb（`REA_ADB_PATH`）、Binwalk/Unblob/sigrok/TShark（Linux-only）
4. `D:\App\tools\downloads\` 留有两个已校验安装包（Ghidra zip + JDK zip，~775MB），可留作重装备份，不需要可删

## 工作区 / 仓库状态

- 本会话未改 `agent-workspace` 内任何文件；本次 handoff 归档 + `progress.md` 索引行是唯一仓库改动
- 仓库内另有**其他会话的未提交改动**（agentctl machine_setup 相关：machine.py、doctor.py 等 + 16:55/17:01 两份他人 handoff 未跟踪文件），已刻意隔离，不纳入本次提交
- skills 建议：`reverse-engineer-anything`（REA 工作流主入口）；如需把这套环境打包去内网机，`pack-to-dts` 适用
