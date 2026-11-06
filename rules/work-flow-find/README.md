# work_flow_find 组队工具件镜像

- **唯一事实源**：`D:\Innostar-ic\Agent\work_flow_find`（git 仓库，截至 2026-11-05 尚无远程，仅本机存在；其 `AGENTS.md` 的规则全文已镜像于 `../notereplica/`）。
- 本目录镜像组队工具件，`fc /b` 逐字节校验一致：
  - `scripts/agent-team-v2-template.json` — 建队接线 v2 模板（DAG/角色/质量任务接线）
  - `scripts/agent-team-metrics.mjs` — 跑完用 `node agent-team-metrics.mjs <团队目录>\team.json` 出性能报告
  - `scripts/agent-console-inject.ps1` — DSH Web 客户端补丁：注入 Agent Console Tab + 浮动入口（待审批徽标/暂停/悬空失败）
  - `scripts/agent-teams-entry-toggle.ps1` — 补丁：面板条目可开可收
  - `scripts/agent-teams-dock-fit.ps1` — 补丁：UI 缩放下浮窗保持视口内
  - `scripts/agent-teams-ui-scale.ps1` — 补丁：面板缩放（注入 `--dsh-at-zoom`，与 dock-fit 配对）
  - `scripts/agent-teams-switch.ps1` — dsh-agent-teams 插件总开关管理（cordis.patch.yml）
  - 四个补丁脚本改 DSH 客户端 bundle（幂等注入，F5 生效），CSS 类名为构建哈希（`.aYQbCq_*`），跨 DSH 版本需重新适配——内网 DSH 版本须与本机一致。
- **同步纪律**：源仓库文件变更后重拷镜像、`fc /b` 校验后提交本仓库；两侧漂移以源仓库为准修复。
- **为何入库**：export 只打包 git 已跟踪文件；不入库则其他机器拿不到工具件，组队规则三节引用的两个脚本路径在本机外无法解析。本机源仓库存在时优先用源，本机无源仓库（公司/内网重建）时用本镜像。
