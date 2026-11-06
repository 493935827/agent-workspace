# 整机离线交付（新机装机总纲）

目标：**agent-workspace 目录整体可搬运**——本文件随 export 包走，`packages/` 三件介质随物理拷贝走；两者齐了，任何新 Windows 机器都能完整重建 Agent 开发环境（workspace + DSH + AgentTeams 插件 + 团队 UI）。

## 四件套清单（2026-11-06 构建）

| # | 文件 | 大小 | SHA-256 | 作用 |
| --- | --- | --- | --- | --- |
| 1 | `dist/agent-workspace-v0.1.0-offline.zip` | 6.7 MB | 见包内 `SHA256SUMS`（export 自动生成） | workspace 本体：44 技能源、rules 双镜像、configs、agentctl、本文件 |
| 2 | `packages/dsh-offline-0.1.5-rc.2-20261106.7z` | 355 MB | `76DF8593…93A2DE` | DSH 本体 0.1.5-rc.2（node v24.15.0 + desktop 0.4.1 + pnpm + rea-agents；**不含** web profile 插件） |
| 3 | `packages/agent-teams-ui-pack-0.1.28-20261106.7z` | 99 MB | `929B652F…0F47DE` | AgentTeams 插件 0.1.28（profiles/web 整目录，junction 已实体化）+ 双启动器 + versions.txt 取证 |
| 4 | `packages/agent-dashboard-20261106.7z` | 2.6 MB | `BB753B9D…5D9102C` | Agent Console 后端（port 5731） |

完整字节值以构建机 `manifests/*.json` 为准；传输后先哈希比对再安装。

## 装机顺序（新机器 6 步）

1. **恢复 workspace**：`agentctl import agent-workspace-v0.1.0-offline.zip --env <personal|company|intranet>`（见 README 第 8 节）。
2. **装 DSH 本体**：解包 2 → `%LOCALAPPDATA%\dsh-offline`，按包内 `INSTALL.md` 改 `cordis.patch.yml` 路径、设 `INNOSTAR_API_KEY` 环境变量。
3. **装 AgentTeams 插件**：解包 3 → 与 `%USERPROFILE%\.dsh\profiles\web` 覆盖合并（插件 0.1.28 + pnpm 依赖 + 启动器）。
4. **装 Console 后端**：解包 4 → `%USERPROFILE%\.dsh\agent-dashboard`，`start-dashboard.ps1` 启动（5731）。
5. **打 UI 补丁**：按 `rules/work-flow-find/README.md` 依次执行 `agent-console-inject` / `agent-teams-entry-toggle` / `agent-teams-dock-fit` / `agent-teams-ui-scale`（`agent-teams-switch` 管总开关），F5 生效。
6. **验证**：DSH 面板出现 AgentTeams 入口、面板可开可收、缩放后不出视口、Console Tab 轮询 5731 正常。

## 版本耦合（硬约束）

- UI 补丁的 CSS 类名是 DSH 构建哈希（`.aYQbCq_*`），**DSH 必须保持 0.1.5-rc.2**；升级 DSH 需在源机重新适配四补丁并重打包 3。
- 包 3 内 `versions.txt` 是外网基准（插件版本、profile 依赖、cordis.patch.yml 配置），装机前后各核对一次。

## 分发路径

- **内网/离线机**：物理介质。`packages/` 与 `dist/` 都在 `.gitignore`，不进 git，直接拷文件；本文件（随 export）即介质清单。
- **公网新机**：待发布到私有 GitHub Release（沿用 agent-software-packages / user-data 模式），发布后在本文件补 Release 坐标。
- **更新纪律**：任何包重打后，原位更新本表 SHA-256 与 `manifests/`，再重新 `agentctl export`。
