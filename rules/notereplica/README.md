# NoteReplica 项目规则镜像

- **唯一事实源**：`D:\Innostar-ic\Agent\work_flow_find\AGENTS.md`（NoteReplica 仓库，git 管理，含 AgentTeams 编排规则与上下文同步纪律）。
- 本目录 `AGENTS.md` 是其**逐字节镜像**（`fc /b` 校验一致），随 `agentctl export` 离线包分发到公司/内网机。
- **同步纪律**：源仓库规则变更后重拷镜像、`fc /b` 校验后提交本仓库；两侧漂移以源仓库为准修复。
- **部署**：在目标机做 NoteReplica 项目时，把本 `AGENTS.md` 复制到该项目根目录（AGENTS.md 按目录注入 agent 会话，工作区根规则不覆盖项目级规则）。
- **为何入库**：export 只打包 git 已跟踪文件（`agentctl/bundle.py` `collect_files` → `git ls-files`）；不入库则规则文件进不了离线包。
