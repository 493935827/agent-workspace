# Handoff：全代码审查遗留 P1/P2 修复（2026-10-20 17:01）

- 会话 / 回合 ID：本环境不可见（界面未提供源会话链接；以本归档 + progress.md 归档行为准）
- 仓库：D:\App\agent-workspace（单仓多技能），分支 master；HEAD = origin/master = `12d759e`，工作区干净（仅 `skills/serial-debug.7z` 未跟踪，历史离线包产物，勿提交）
- 远端：origin = https://github.com/493935827/agent-workspace.git；推送命令 `git -c credential.helper= -c credential.helper=manager push origin master`（先清空 helper 列表再仅用系统 manager，绕开本地损坏的 wincred helper；裸 push 与 `credential.helper=` 全清两种都会失败——前者 helper 启动报 "The system cannot execute the specified program"，后者无人提供凭据）

## 目标与范围

用户「继续修bug」：修复 2026-10-20 全代码审查遗留的 3 个 P1 与可顺手修的 2 个 P2（清单见 [Code review quickfix](handoff-20261020-153500-code-review-quickfix.md)）。按 diagnosing-bugs 纪律：诊断沿用审查结论（已核实 file:line），本对话为每个缺陷先建红色回归测试、看红再修、复绿收尾。

## 本对话完成（提交 `367aed4`，已推送）

| # | 缺陷 | 修复 |
| --- | --- | --- |
| P1 | 服务端 takeover×波特率扫描竞态（原 serial_service.py:287-291/417） | `scan_open_device` 增加协作式中止参数 `should_abort`（候选间 + 每次读前检查；中止走 `'interrupted'` 路径恢复原波特率）；服务端新增 `scan_abort` 事件与 `_abort_scan_and_wait()`（≤3s 超时回 busy），`_revoke` 开头与 `_device_action` 持 transition 后调用；扫描收尾 finally 只清自己的 `'baud_scan'` transition |
| P1 | GUI ServiceWorker 桥死亡假在线（原 serial_gui_qt.py:277-281） | run 循环加 `status` 探活：`probe_interval`（默认 1s，构造参数可注入）；订阅 gaps 跳变只作加速信号；连续两次失败才判死 → raise OSError『共享串口桥已失联：…』→ 既有 error→closed 链路 |
| P1 | 接管失败毒化健康会话（原 serial_gui_qt.py:231-236） | `takeover` 失败改发非致命 `'takeover_failed'` 事件；GUI 事件泵渲染为 WARN 行，会话保持 connected、接管按钮可重试；`emit` 停机放行清单加入该事件 |
| P2 | `_raw_notice` 无锁 pop raw_clients 与 `_reader` 的 `del` 竞态 → reader 线程 KeyError 死亡、RX 永久停转 | raw_clients 全部变更持 `self.lock`；reader 满载丢弃改 `pop(sock, None)` + 仅在确有弹出时计数/关 socket |
| P2 | raw 终端首次被拒 send 即断连 | `_raw` 对 `ActionError` 不再 return：发 `raw_rejected` 事件 + 向本连接 outgoing 注入 `[串口桥] 发送被拒绝：…`，继续监听 |

配套：README.md §5 补接管/探活行为（扫描中接管先中止扫描、接管失败仅提示、1s 探活）；windows/README.md 交互终端节补拒发提示说明；既有契约测试 `test_exclusive_blocks_mutations_and_raw_writes_but_allows_observation` 的 raw 断连断言改写为新契约（拒发保持连接 + 收到提示）。

## 验证证据

- 新增 10 项回归：tests/test_serial_baud_scan.py +2（should_abort 中止契约×2）、tests/test_serial_service.py +4（takeover×扫描、设备动作扫描期 busy 契约钉、raw 拒发保持连接、reader 竞态 40 轮压测）、tests/test_ui_service_worker.py 新文件 4 项（探活判死、健康桥存活、takeover_failed 非致命、GUI 端到端会话不毒化）。
- 红绿验证：takeover-during-scan、reader 竞态压测、raw 拒发、takeover_failed 均在修复前确认红（竞态压测修复前 reader 死亡：`b'AFTER' not in b''`）；修复后全部绿。
- 全套 111 项通过（offscreen 597s；此前偶发抖动的 test_ui_log_noise 本次全绿）。三个目标文件单独跑也全绿。
- 无残留调试产物：临时脚本 tests/_debug_gui_connect.py 已删除；未使用 [DEBUG-] 标记日志。

## 关键决策与拒绝方案（避免重复踩坑）

- **扫描中止走协作式 should_abort，而非强杀线程**：中止延迟 ≈ 一次设备读超时（服务端真设备 .05s / FakeSerial .02s），远小于 3s 等待上限，与 scan_open_device「总是恢复起始波特率」契约兼容。
- **设备动作在扫描期间维持既有 busy 契约**（dispatch 的 transition 守卫拒绝，takeover 是唯一放行者）；`_device_action` 里的 abort+wait 属防御（直接调用入口，如既有 test_serial_close_drops_pending_scan_request 直调场景）。
- **扫描收尾 finally 只清自己的 `'baud_scan'`**：中止握手后 takeover/device action 可能已持 `'revoking'`/动作 transition，无条件清会把竞态反向重演（writer 在他人 transition 期间恢复）。
- **探活死亡判据 = 连续两次 `status` 失败**，gaps 只作加速（沿用 stop-group 会话「gaps 不可靠」结论，见 [GUI bridge stop group](handoff-20261020-105711-gui-bridge-stop-group.md)）；第一次失败可能是 call 通道瞬断（Client 会自重建），第二次在新通道上失败才判死。
- **raw 拒发对所有 ActionError 保持连接**（含 occupied/queue_full/disconnected），提示注入自己的 outgoing 队列；连接关闭仍只由 OSError/EOF/服务停止触发。
- **GUI 测试假客户端契约**：`FakeServiceClient.next_event` 必须像真 Client 一样让 `queue.Empty` 传播——返回 None 会让 `ServiceWorker.pump_events` 在 `event.get` 上崩、worker 立刻 error+closed，掩盖被测行为（本次实际踩到）。

## 测试基建踩坑（本次新增）

- pytest 输出重定向到文件跑（`cmd /c "... > %TEMP%\x.txt 2>&1"`）；PS 5.1 下 `2>&1 |` 管道包 NativeCommandError 且可能挂死——沿用既有约定。
- 压测线程的 cleanup 是 LIFO：`addCleanup(join)` 必须先注册、`addCleanup(stop.set)` 后注册，否则 join 永不返回（挂死 240s 的根因）。
- 服务端 `_accept` 有 32 连接上限：压测每轮要显式 `raw.close()` 释放槽位，否则最终客户端被拒收、表现为"零字节"假象。
- 压测锤线程收尾前必须停掉：它会持续灌满最终客户端的 1024 深队列并把客户端挤掉线（满载丢弃），导致收尾断言误红。
- 本仓库 git 操作以 `D:\App\agent-workspace` 为仓库根；在技能目录里 `git add skills/serial-debug/...` 会 pathspec 失败，需用技能目录相对路径。
- 并行会话仍可能活动：本对话中 progress.md 被并行会话改过一次（edit 因 mtime 拒绝，重读后成功）；HEAD 也被并行推进过（`8bddd81`）。编辑 progress.md 前务必重读。

## 剩余工作与建议下一步

1. **P2 PS 5.1 健壮性**（windows/serial_console.ps1：345/95 的 `2>&1`/`2>$null` × `$ErrorActionPreference='Stop'` 吞原生 stderr；136-138/392 `Start-Process -ArgumentList` 含空格路径不加引号）。改 ps1 必须重验 UTF-8 BOM + Parser（快修 handoff 有 BOM 丢失踩坑）。
2. **P2 readability 固定 UTF-8**（`serial_baud_scan.py` 的 `readability`/`score_sample`）：GBK 日志设备会误触发自动重扫（windows/README:57 关联说明）；需设计编码感知或二进制占比判据，注意离线/在线共契。
3. **P3 择要与测试缺口打包**（start 未知不恢复波特率、非零路径无 `autobaud_result:` 行、ps1:331 正则抓人类可读输出、ps1:32 配置 scriptblock 执行应改 Import-PowerShellDataFile；测试缺口：ServiceWorker 失败路径、peer_tx 渲染、主动探测真发 `\r`、JSON round-trip、baud_scan interrupted/SAMPLE_CAP/ambiguous、detect_serial_port 退出码）——完整 file:line 清单见快修 handoff 第 2 节。
4. **实机人工验收**（需 RRAM_TEST 输出板接回；本机当前仅 COM4/5 蓝牙口，按设计被排除；本地配置 COM6/115200 完好）：按 `docs/test-plan.md` 第 6 节 L3-1…L3-7，含设备级 RX 应答往返、被动检测、在线检测中途换波特率、「停止桥并释放端口」；先确认是否停板上的测试。
5. style token 改动同步上游 serial-gui 仓库（旧待办）。
6. 审查 handoff 曾建议为未修项开 GitHub issue——P1 已全部修完，剩余 P2/P3 是否开 issue 由用户定（网络当前可用）。

## 建议技能

- 续接推送/提交：`git-delivery`（推送用上文 helper 组合命令）。
- 改 ps1 / 修 P2 时：按需重读快修 handoff 的 BOM 与 PS 5.1 踩坑；`code-review` 不必重复加载。
- 实机验收涉及串口安全（DTR/RTS、波特率切换）时遵守 `references/hardware-safety.md`。
