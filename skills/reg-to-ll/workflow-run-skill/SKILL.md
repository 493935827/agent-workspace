---
name: workflow-run
description: 通过稳定的可执行 runner，将本地 Excel 或离线飞书快照依次转换为 SVD、ae350.h 和 LL Driver，并返回机器可读结果。
prerequisites:
  - python >= 3.8
  - pip install openpyxl
  - 已验证的 SVDConv 可执行文件
  - 已固定的 regtool Oracle manifest 与容器环境
language: zh-CN
---

# Workflow Run

当用户要从本地 Excel 或已经获取的飞书离线快照生成完整产物链时使用本 Skill。若用户只想检查已有文件，请使用对应的 check Skill。

## 唯一执行边界

必须调用 `workflow-run-skill/run_workflow.py`。不得在对话中逐阶段调用其他 Skill，不得解析面向人的 stdout、日志关键字或自然语言来判断成功与否。

本地 Excel：

```powershell
python workflow-run-skill/run_workflow.py `
  --source local `
  --workbook <registers.xlsx> `
  --output-dir <output-directory> `
  --oracle-manifest <manifest.json> `
  --svdconv <SVDConv.exe> `
  --peripheral <optional-peripheral-name> `
  --evidence <workflow-result.json>
```

飞书输入：先由 `feishu-fetch` 获得重建 Excel 和原始 JSON 快照，然后调用同一 runner：

```powershell
python workflow-run-skill/run_workflow.py `
  --source feishu `
  --workbook <rebuilt.xlsx> `
  --feishu-snapshot <raw-snapshot.json> `
  --output-dir <output-directory> `
  --oracle-manifest <manifest.json> `
  --svdconv <SVDConv.exe> `
  --peripheral <optional-peripheral-name> `
  --evidence <workflow-result.json>
```

`--peripheral` 仅在工作簿包含多个外设时必需。`--timeout` 可覆盖每个外部工具阶段默认的 30 秒上限。
默认增量状态写入 `<output-directory>/.workflow-state.json`；可用 `--state` 指定其他安全路径。`--force`（等价于 `--full-rebuild`）忽略已有缓存并重跑全部阶段。

## 稳定结果契约

执行结束后读取 `--evidence` 指定的 UTF-8 JSON 文件。该文件是唯一状态来源；stdout 只是同一 JSON 的便捷副本。

- 退出码 `0` 且 `valid=true`、`can_continue=true`：全部必需阶段成功。
- 非零退出码或 `valid=false`：工作流失败。
- `stages` 始终按 `input-convergence`、`svd-generation`、`svd-parity`、`svd-validation`、`header-generation`、`ll-generation` 排序。
- 每个阶段统一包含 `name`、`status`、`errors`、`warnings`、`outputs` 和 `evidence`。
- `generated_this_run` 仅表示本次执行了该阶段；`available` 表示产物当前存在且内容哈希匹配；`validated` 表示该产物对当前输入、配置和工具版本有效；`cache_hit` 表示本次复用了可信状态。这四个事实不可互相替代。
- `status` 仅为 `success`、`failed` 或 `not-run`。首个必需阶段失败后，所有下游阶段必须为 `not-run`，不得描述为成功。
- `errors` 是致命诊断；`warnings` 是非致命诊断，不能仅因存在 warning 把成功结果改成失败。
- 顶层 `errors`、`warnings` 和 `outputs` 是阶段结果的稳定聚合；诊断使用 `code`、`message`、`location`。

向用户汇报时可以把 JSON 内容翻译成易读说明，但不能用翻译后的文字反推或覆盖 JSON 状态。接口和字段示例见 `reference.md`。
