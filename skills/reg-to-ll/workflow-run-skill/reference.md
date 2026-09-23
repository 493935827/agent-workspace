# workflow-run 稳定接口参考

## 命令接口

```text
run_workflow.py
  --source local|feishu
  --workbook PATH
  [--feishu-snapshot PATH]
  --output-dir PATH
  --oracle-manifest PATH
  --svdconv PATH
  [--peripheral NAME]
  [--timeout SECONDS]
  [--state PATH]
  [--force|--full-rebuild]
  --evidence PATH
```

`source=feishu` 时必须同时提供原始 JSON 快照和由该快照重建的 Excel。两种来源在 `input-convergence` 后都产生相同的 `WorkbookModel`，后续使用同一条执行链。

## 阶段顺序

```text
input-convergence
→ svd-generation
→ svd-parity
→ svd-validation
→ header-generation
→ ll-generation
```

这些名称及顺序是公开契约。首个失败阶段之后不会再调用任何下游动作；结果仍保留所有阶段，并把下游状态记为 `not-run`，其 `evidence.reason` 指向阻塞阶段。

## JSON 结果

顶层固定包含：

```json
{
  "valid": true,
  "can_continue": true,
  "errors": [],
  "warnings": [],
  "outputs": {},
  "evidence": {},
  "stages": []
}
```

每个 `stages` 元素固定包含：

```json
{
  "name": "svd-validation",
  "status": "success",
  "errors": [],
  "warnings": [],
  "outputs": {},
  "evidence": {},
  "generated_this_run": false,
  "available": true,
  "validated": true,
  "cache_hit": true
}
```

缓存状态以原子替换方式写入 JSON。缓存键由上游键、当前输入内容哈希、相关配置、阶段实现版本和工具内容版本组成，并绑定输出内容哈希；修改时间不参与可信判断。任一阶段未命中时，该阶段和全部下游阶段在本次运行中重算。

诊断对象固定使用 `code`、`message`、`location`。warning 不改变成功状态；error 会使当前阶段为 `failed`，并使顶层 `valid` 与 `can_continue` 为 `false`。顶层 `evidence.stage_evidence` 按阶段名聚合各阶段证据。

调用方只读取 `--evidence` 文件判断状态，不解析日志行或面向人的说明文字。runner 以原子替换方式发布该证据文件。
