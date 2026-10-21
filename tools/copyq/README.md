# copyq — 设置模板（不含剪贴板历史）

CopyQ 16.0.0 的**设置类配置模板**，来源为本机 `%APPDATA%\copyq` 抓取：

| 文件 | 内容 |
|---|---|
| `copyq.ini` | 主设置：行为开关、快捷键、标签页（`&Clipboard` / `agent`）、内嵌主题 `[Theme]`、条目列表最多显示 20 行（`itemtext\max_lines=20`，超出部分用预览/F7 查看） |
| `copyq-commands.ini` | 8 个自定义命令：固定/取消固定、标签（重要）、`alt+c` 全局显示/隐藏 |

## 边界

- **不含任何剪贴板历史**（`copyq_tab_*.dat` 是个人数据，只经私有渠道分发，
  见私有仓库 `agent-software-packages` 的 user-data Release）。
- 不含 `%APPDATA%\copyq` 下的 `.bak*`、`.log` 等临时文件。

## 使用

```bash
# 新机器上恢复设置（历史数据用私有 Release 下载的 ZIP 一并恢复）
agentctl appconfig deploy copyq --from tools/copyq --dry-run
agentctl appconfig deploy copyq --from tools/copyq

# 本机配置变更后刷新模板（人工确认 diff 后复制）
agentctl appconfig status copyq
```

恢复后建议重启 CopyQ 使设置生效。
