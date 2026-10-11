# agentctl 帮助、全局入口与命令验证交接

- 源对话 ID：`01a1294d-70ce-7251-93c0-c86c0d10292f`
- 归档时间：2026-10-11 17:54（Asia/Hong_Kong）
- 项目根目录：`C:\Users\bottle\Documents\ChatGPT\agent_workspace`

## 目标与本次完成

用户先要求为命令行工具写详细 help，再要求从任意目录运行 `agentctl`，指出 `agentctl --doctor` 的报错，最后要求把所有命令实际试一遍。本次完成：

1. 在 [CLI 入口](../agentctl/cli.py) 和 [发现类命令](../agentctl/discovery/commands.py) 补齐中文用途、选项说明、示例及重要限制；[README](../README.md) 写明帮助入口和任意目录运行条件。`doctor` 是子命令，正确写法是 `agentctl doctor`，`agentctl --doctor` 仍为无效语法。
2. 本机**用户级** PATH 已加入工作区 `scripts/`，用户级 `AGENT_WORKSPACE_ROOT` 已设为项目根目录。从 `C:\Users\bottle` 运行 `agentctl doctor`，全部检查 PASS，退出码 0。现有终端若未读取更新后的环境变量，需要重新打开。
3. 修复 [Windows 启动脚本](../scripts/agentctl.cmd) 吞掉子进程错误码的问题；[回归测试](../tests/test_cli_wrapper.py) 先以错误返回码 0 失败，修复后通过，无效的 `--doctor` 返回码 2。
4. 15 个子命令全部实际调用：`status`、`version`、`doctor` 在真实工作区通过；`update --dry-run`、`bootstrap --env personal --dry-run` 通过；`scan`、`diff` 指定 `uv` Provider 通过。`link`、`unlink`、`export`、`import`、`restore`、`snapshot`、`adopt`、`ignore` 在自动清理的临时工作区验证，导入与恢复后的文件内容均已核对。`--version` 也通过。

## 验证边界与环境发现

- `update --dry-run` 会执行 Git fetch，但不 pull 或改动工作树。首次遇到 GitHub TLS 握手失败，重试后返回“Already up to date”。
- `bootstrap` 仅运行 `--dry-run`；不会在真实工作区重新安装依赖或改链接。其他写入型命令的实际写入仅发生于临时工作区，未保留临时文件。
- Codex 命令运行环境的 PATH 额外带有一个 fallback `pnpm.CMD`。它因自身全局 bin 目录未进入 PATH 而退出 1，导致完整 `snapshot` 报 Provider error。用系统 Machine+User PATH 模拟普通用户终端时，`pnpm` 为 unavailable；临时工作区中的 `snapshot --dry-run` 和实际保存都返回 0，后者成功写入基线。该基线不覆盖 unavailable 的 `pnpm`、`pipx`。这不是已在用户机器上保存的真实快照。
- 当前真实工作区无未提交改动；本次命令验证没有改动真实 Skill 链接、离线包或发现基线。`update --dry-run` 的 fetch 可能更新 `.git` 中的远端跟踪信息。

## Git 交付

- `1b7a527`：扩展中文 help。
- `dbb2021`：记录用户 PATH 设置。
- `e0c4c89`：修复 Windows 启动脚本退出码并记录工作区根目录配置。
- `0c8e171`：记录 15 个子命令的验证结果。
- 上述提交均已推送 `origin/master`。本次 handoff 将另行提交和推送，以本回合最终结果为准。

## 仍需关注与下一步

- 整体项目仍缺 AndeSight 5.3.1；受限软件需经公司批准渠道。此前的软件 Release 与 OneNote 归档状态见 [进度概况](progress.md) 和对应旧归档。
- 当前没有未完成的 agentctl 修改。下一段对话先核对本 handoff 的索引行与实际仓库状态，再按用户的新需求推进；若要在 Codex 运行环境执行完整 `snapshot`，先核对 PATH 中的 fallback `pnpm`，不要把该环境错误误判为用户终端的故障。

## 可考虑的技能

- 修改项目文件时可按 `git-delivery` 做范围内验证和交付；出现真实运行故障时可用 `diagnosing-bugs`。仅在用户当前消息显式写出 `$firmware-mentor` 或附上技能链接时才加载该技能。
