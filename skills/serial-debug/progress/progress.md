# 项目进度

最后更新：2026-10-13 19:40（Asia/Shanghai）

## 当前概况

- 目标 / 当前阶段：Issue #1 共享串口工具已完成 Phase 1 服务端；2026-10-13 人工 GUI 升级为 Qt 工作台；同日完成统一风格改造（详见 docs/design-system.md）。
- 统一风格（2026-10-13）：定为「Fluent 2 深色优先开发者终端」，规范文档在 `docs/design-system.md`，token 唯一事实源仍为 `scripts/qt-preview-tokens.json`。
- 风格改造内容：token 对比度修复（浅色 text_secondary/brand 系、深色 danger_foreground，全部达 WCAG AA 4.5:1，品牌色回归 Fluent 官方 #0f6cbd）；首次启动默认深色；Tab 键仅在命中宏时消费（否则正常焦点遍历）；搜索框加宽至 220px；状态栏错误以 danger 色保持 8 秒（修复 30ms 内被轮询覆盖的 bug）；四个对话框改为行内校验错误（不再弹模态警告框、失败不关窗）。
- 新增测试：`tests/test_ui_tokens.py`（token 对比度守卫，无需 Qt）、`tests/test_ui_style.py`（深色默认/持久化、Tab、状态栏错误、行内错误、搜索宽度，8 项）。
- 测试基建修复：`tests/test_shared_serial_bridge.py` 的 FakePort 增加 park()（bridge 守护线程泄漏的 service reader 热循环会饿死同进程后续测试，全量套件 287s→27s）；test_ui_style 的窗口清理用 deleteLater+冲刷 DeferredDelete（PySide6 信号连接滞留导致 setStyleSheet 二次方变慢）。
- 全套 28 项测试通过（PySide6 6.12 offscreen 环境，约 27 秒）；双主题截图像素采样验证（浅/深主题 chrome 与 canvas 颜色正确）。
- 跨仓库契约测试：`tests/test_serial_gui.py` 保持「Qt 工作台 ↔ 真实 SerialService」集成测试不变；服务端、协议、桥、`serial_control.py` 均未改动。
- Qt 工作台自身的完整测试（含 FakeService、backspace 回显、服务会话）在 serial-gui 仓库维护（github.com/493935827/serial-gui）。
- 下一步：真实硬件验收仍待人工确认；style token 改动需同步上游 serial-gui 仓库（本次未同步）。

## 对话归档

| 日期 / 对话 | 完成内容 | 交接 |
| --- | --- | --- |
| 2026-10-13 / 统一风格与可访问性改造 | 定档 Fluent 2 深色优先；token AA 修复、深色默认、Tab/状态栏错误/对话框行内校验修复；新增对比度与风格回归测试；测试基建提速 287s→27s | （本次对话，未单独归档） |
| 2026-10-13 / Qt 工作台替换薄客户端 | Qt 工作台加入服务会话与 agent 接管；skill 内置并重写集成测试；18 项测试通过 | （本次对话，未单独归档） |
| 2026-09-09 / Serial Phase 1 implementation | 完成服务、CLI、GUI、中文说明并推送；GUI 接管冒烟仍未完全通过 | [Serial Phase 1](handoff-20260909-160606-serial-phase1.md) |
