---
name: reg-to-ll
description: 将本地 Excel 或离线飞书快照经过强制验证，生成可追溯的 SVD、CMSIS 头文件和 LL Driver。
---

# Reg to LL

使用安装包内的 `workflow-run-skill/run_workflow.py`；入口根据自身包位置解析代码与资源。完整命令、阶段名和结果字段以 [工作流契约](workflow-run-skill/SKILL.md) 为唯一事实源。

完成条件是入口退出码为 `0`，且 evidence JSON 同时满足 `valid=true`、`can_continue=true`；每个必需阶段均为 `success`、`available=true`、`validated=true`。否则报告结构化诊断并停止。
