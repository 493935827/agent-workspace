# Handoff：共享连接空闲后发不出数据（30 秒通道超时）修复

- 日期：2026-10-20 10:45（Asia/Shanghai）
- 会话：session-47a22eeb520c（DSH Web GUI，model glm-5.3-flash）
- 仓库：`D:\App\agent-workspace`（GitHub `493935827/agent-workspace`，分支 `master`）
- 本 skill 子目录：`skills/serial-debug`

## 目标与范围

用户报障：「共享连接有时候需要点下断开，然后再点连接才能正常发数据」。定位 Qt 工作台「连接共享服务」会话的发送失效根因并修复，配套回归测试。

## 本对话完成的工作

按 diagnosing-bugs 流程走完：先搭复现回路（拒绝先读代码下结论的路径），31 秒空闲复现脚本修复前红、修复后绿，再落修复与回归测试。

1. **复现回路**（一次性脚本，已删除）：`tests/debug_shared_send.py` 三场景——S0 无空闲 sanity（绿，证明回路健康）；S1 服务级「call→空闲 31s→call」（修复前红）；S2 GUI 端到端完整用户故事（连接→边看 RX 日志边空闲 31s→发送→设备收不到且会话仍显示 connected→断开重连后恢复）。修复前 S1/S2 全红，S2 完整复刻用户描述。
2. **根因**：`SerialService._connection` 给所有控制端口连接统一 `settimeout(30)`。GUI 的 `Client` 有两条连接：呼叫（call）通道只在自己发送时收发请求；订阅（subscribe）通道收事件/RX。空闲超 30 秒后服务端把呼叫通道超时关闭，订阅通道不受影响 → 会话看起来一直在线（RX 还在滚、状态 connected、worker 存活），之后每次 `client.call('send')` 都在死通道上失败，`ServiceWorker.drain_commands` 逐条捕获只发一条 WARN（`发送被拒绝：[WinError 10053]`），会话永远不会进入 error/disconnected——只有点断开再点连接（重建两条连接）才恢复。「有时候」= 用户盯着日志停留超过 30 秒再发送；连续快速操作不触发。
3. **修复**（两层，已提交为 `c6c3afa` 并推送）：
   - 服务端 `scripts/serial_service.py`：`_connection` 不再统一设 30 秒；call 连接在 `_control` 里设 `CONTROL_READ_TIMEOUT = None`（模块常量，人类操作之间的空闲不该杀通道；订阅/raw 各自保留 1 秒超时）。
   - 客户端自愈 `scripts/serial_client.py` + `scripts/serial_service_client.py`（两个近重复实现同步改）：`Client.call` 遇传输层死亡（`OSError/EOFError/ValueError`）→ `_rebuild_channel()` 只换呼叫通道（订阅通道不动）→ 原样抛出本次错误；响应 ID 不匹配（通道错位）同样重建。本次发送结果未知，**不自动重发**（符合项目既有约定「发送结果未知时不得自动重发」）。
4. **回归测试**（2 项，已在 `c6c3afa`）：`tests/test_serial_service.py::test_call_channel_rebuilds_after_transport_death`（服务级：通道外死后一次失败、自愈、订阅存活）；`tests/test_serial_gui.py::test_service_session_recovers_call_channel_after_transport_death`（GUI 端到端：经 `service_client_factory` 捕获 worker 的 client，杀呼叫通道后第一次发送 WARN 且设备收不到，第二次直接恢复）。
5. 全套测试通过（本对话时点 72 项 / 203 秒；并行会话后续合并后为 77 项）。

## 关键决策与拒绝的方案（避免重复踩坑）

- **拒绝自动重发**：通道死亡时本次 send 结果未知，只能报错一次并自愈通道，不能静默重发。
- **两层修复都做**：只修服务端超时不够——服务端还有其他会关呼叫通道的路径（如 `too_large` 应答后 `return`），客户端自愈兜住所有来源；只修客户端自愈则用户每次空闲后仍会看到一次发送失败 WARN，体验不对。
- **测试细节坑**：模拟通道死亡必须 `socket.shutdown(SHUT_RDWR)` + `close()`。直接 `socket.close()` 无效——Python 的 close 在还有 `makefile()` 流引用时不真正关 fd（`io_refs` 计数），第一次调用甚至能成功，测试会假绿。
- **未加空闲超时旋钮**：修复后 call 通道没有可配超时（默认 None）。如未来要加，注意别把 30 秒默认带回来。
- 曾怀疑但排除的方向：服务端订阅背压丢事件（需要 GUI 停顿 + 巨量 RX 突发，制造条件苛刻）；agent 租约占用（GUI 连接时会直接报 occupied，不是假在线）；波特率扫描 transition busy（连接会显式失败）。

## Git / 工作区状态（截至本归档）

- `c6c3afa fix(serial-debug): rebuild the service call channel after transport death` —— 本对话的全部修复（5 个文件 + progress.md），**已推送**。由并行会话（同一用户的另一个对话）代为提交。
- `67255ca`（GUI 在线波特率检测，已推送）、`4695a90`（共享串口桥分组 + 一键停止，**未推送**，当前 `master` 领先 origin 1 个提交）—— 均为并行会话的工作，与本对话无关；`4695a90` 的推送留给用户或对应会话决定。
- 工作树当前只剩未跟踪的 `skills/serial-debug.7z`（无关产物，勿提交）。
- 注意：修复条目在 progress.md 第 13 行末尾的「未提交，待用户决定提交切分」已由本归档更正为已提交。

## 剩余工作 / 下一步

1. **实机验收**：接回 USB 串口板后验证「连接共享服务 → 停留 30 秒以上 → 发送」直接生效，不再需要断开重连；同时确认 WARN 行不再出现。
2. 原有待办（见 progress.md 下一步条目）：RRAM_TEST 板设备级 RX 应答往返补验；在线波特率检测（中途换波特率）人工验收；style token 同步上游 serial-gui 仓库。
3. **DTS 离线包**（`D:\trash\Work\Innostar-ic\DTS\serial-debug-offline-py310-win_amd64.7z`）仍是旧行为，若现场用包部署需重打才能带上本修复。
4. 可选：把「共享连接假在线」的教训推广——事件订阅通道死亡目前也是静默的（`client.gaps` 只增不报），可考虑后续给订阅通道加自愈/提示（未被要求，备忘）。

## 阻塞

无。

## 临时产物 / 后台任务

- `tests/debug_shared_send.py` 已删除，无遗留调试代码；无运行中的后台任务。

## 技能建议（不构成调用授权）

- `diagnosing-bugs`：本对话使用的诊断流程，同类报障先搭复现回路。
- `git-delivery`：如需按修复单位提交/推送（本对话修复已被并行会话提交，无需重复）。
- `handoff`：保持手动调用约定。
