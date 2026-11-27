# 项目工作约定

- 接续项目工作时，先读 `progress/progress.md` 的当前概况并核对相关工作区状态；概况按渐进式披露刻意精简（每主题一行），细节按需搜索对话索引、打开关联 handoff，不批量加载历史归档，也不因概况简短而扩写它。实质进度变化时原位改写概况中受影响的行，细节与证据留在 handoff 或权威文档；用户请求 handoff 时保存对话归档并更新对应索引行。handoff 保持手动调用：对话将结束或上下文将尽而工作未完时提醒用户调用，任务完成本身不构成调用理由；`progress/` 是持久项目记录，不属于临时清理范围。
- `agentctl/` 保存 Python CLI 实现，`configs/` 保存分层环境配置，`tests/` 保存测试；给人的使用入口是 `README.md`。跑测试用 `.venv\Scripts\python.exe -m pytest`（root 已收敛 testpaths；conftest 隔离宿主环境变量，全量运行不会污染真实 configs/`.agentctl/`）。
- 目录跳转/找路径用 zoxide（已在用户 PATH，工作区目录已种子入库）：agent 的 pwsh 会话不带 profile、没有 `z` 函数，用 `zoxide query <词>` 拿路径再 cd；交互终端可用 `z <词>`。常用新目录顺手 `zoxide add <路径>`。
- 用户主要使用 C 和 Python，具有嵌入式软件背景；解释陌生技术时使用浅显语言。
- `firmware-mentor` 仅在用户当前消息明确写出 `$firmware-mentor` 或附上该技能链接时加载。固件、嵌入式、C、Python、芯片及职业成长等主题本身不构成调用授权。
- `rules/` 保存跨机分发的项目规则与工具件镜像（当前含 NoteReplica 规则、work_flow_find 组队工具件）：唯一事实源在源仓库，源变更后重拷镜像并 `fc /b` 校验再提交本仓库；部署到目标机时复制该镜像到项目根目录 `AGENTS.md`。
- `rules/` 亦承载组队规则引用（本工作区组队前必读）：编队规则唯一事实源在 `D:\Innostar-ic\Agent\work_flow_find\AGENTS.md` 的「标准组织架构与分工」「上下文同步纪律」「多智能体团队并发预算」三节（并行预热 warmup、契约落盘 `docs/batches/<批次id>/contract.md`、评审绑定单轨、质量任务必须显式 `kind=verification/review`）；建队接线实例化 `D:\Innostar-ic\Agent\work_flow_find\scripts\agent-team-v2-template.json`，跑完用 `node D:\Innostar-ic\Agent\work_flow_find\scripts\agent-team-metrics.mjs <团队目录>\team.json` 出性能报告；两件工具件镜像于 `rules/work-flow-find/`（本机无源仓库时改用镜像，源变更后重拷并 `fc /b` 校验）。
- **AgentTeams 自动启用（用户长期指令，2026-11-27）**：无需用户显式 `/agent-teams` 或点名组队，agent 按任务规模自判是否建队、是否多线程并发及并发轨数/团队规模：满足任一判据（≥3 互不依赖工作流 / 预计 ≥8 文件或 ≥5 独立子任务 / 完整质量链 requirements→实现→验证→评审→集成 / 用户措辞出现组队意图词）即自动组队，并在回复首行注明「已自动启用 AgentTeams：<原因>」；单文件修改、单一 bug、问答/简单调研、纯配置或文档微调不组队；边界情形默认组队（宁并行不串行）。建队一律 `approval="automatic"`，仅用户明确要求先审计划/分工时用 `required`。判据细则与按时间窗口的并发预算同源仓库 `D:\Innostar-ic\Agent\work_flow_find\AGENTS.md` 的「自动启用策略」「组队启动方式」「多智能体团队并发预算」节（本机无源仓库时读全文镜像 `rules/notereplica/AGENTS.md`）。
