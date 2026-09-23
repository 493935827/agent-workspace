# Issue tracker: GitHub

规格和任务的权威来源是 `493935827/serial-debug` 的 GitHub Issues。工程技能要求“发布到 issue tracker”时，创建 GitHub issue。

## 操作约定

- 使用 `gh` CLI，显式指定 `--repo 493935827/serial-debug`，避免从其他工作目录操作错误仓库。
- 发布前查询已有 issues，避免创建重复规格；已有对应 issue 时更新原 issue。
- 多行正文先写入 UTF-8 文件，再使用 `--body-file` 创建或更新；保留真实换行。
- 读取任务时同时读取正文、标签和评论；例如 `gh issue view <number> --repo 493935827/serial-debug --comments`。
- 标签角色按 [triage labels](triage-labels.md) 映射；完整可执行规格使用 `ready-for-agent`。
- 发布后核对正文、标签和 issue URL。后续规格变化更新 issue，离线副本应注明是发布快照。

## Pull requests as a triage surface

**PRs as a request surface: no.** 外部 PR 默认不作为需求分拣入口。
