# work_flow_find 组队工具件镜像

- **唯一事实源**：`D:\Innostar-ic\Agent\work_flow_find`（git 仓库，截至 2026-11-05 尚无远程，仅本机存在；其 `AGENTS.md` 的规则全文已镜像于 `../notereplica/`）。
- 本目录镜像组队接线工具件，`fc /b` 逐字节校验一致：
  - `scripts/agent-team-v2-template.json` — 建队接线 v2 模板（DAG/角色/质量任务接线）
  - `scripts/agent-team-metrics.mjs` — 跑完用 `node agent-team-metrics.mjs <团队目录>\team.json` 出性能报告
- **同步纪律**：源仓库文件变更后重拷镜像、`fc /b` 校验后提交本仓库；两侧漂移以源仓库为准修复。
- **为何入库**：export 只打包 git 已跟踪文件；不入库则其他机器拿不到工具件，组队规则三节引用的两个脚本路径在本机外无法解析。本机源仓库存在时优先用源，本机无源仓库（公司/内网重建）时用本镜像。
