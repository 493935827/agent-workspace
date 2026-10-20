# Handoff：全代码审查 + 快修包（2026-10-20 15:35）

- 会话：session-6d2bc002-a131-4efd-b64b-2104e9cb013c（由子代理 send_message 回传的父会话 ID 推断，未在界面二次核验）
- 本地提交：`5bd9670` fix(serial-debug): harden autobaud queueing and passive detection edges（8 文件，+224/−11；**推送待网络恢复**）
- 仓库：D:\App\agent-workspace（单仓多技能），远端 origin = https://github.com/493935827/agent-workspace.git，分支 master

## 目标与范围

用户 `/code-review` 指定**核心代码整体审查**（scripts/ 全部 12 模块 + windows/ 控制器，约 4800 行），随后「修一下」落地审查产出的快修包。只读审查 + 修复，未涉及实机。

## 本对话完成

### 审查（4 路并行子代理 + 本会话逐文件复核）

- 基线：全套 77 项测试复跑全绿（offscreen 342s）。
- 产出口径：4 P1 / 10 P2 / 16 P3；P1 全部由本会话对照源码逐条核实。测试覆盖缺口单独成节。
- 验证为干净的部分：被动默认契约三层实现正确；不自动重发契约全链一致；Qt 线程模型无跨线程控件访问；PS 5.1 配置编码（BOM）修复到位；`serial_gui_qt_prototype.py` **不是死代码**（工作台基类，勿删）。

### 快修包（已提交 `5bd9670`）

| 文件 | 修复 |
| --- | --- |
| scripts/serial_service.py | `serial.autobaud` 请求改锁内赋值；设备丢失（`_disconnect`）与显式释放（`_device_action` releasing 分支）清挂起扫描请求——原 `requested` 卡死致 CLI 假成功 exit 0 且后续扫描 busy |
| scripts/shared_serial_bridge.py | `run_autobaud`：控制连接死亡→exit 4（原先误报 2/裸 traceback）；扫描未启动超时→exit 5（原先假报 unchanged exit 0） |
| windows/detect_serial_baud.py | 被动采样 `rts=False, dtr=False`（开串口不再复位接 DTR 的板子）；`parse_probe` 尾端改 `.encode("latin-1")` 修复非 ASCII 探测串 mojibake |
| windows/serial_console.ps1 | 补 `-Passive` 开关并透传 `Find-SerialBaud`；损坏 bridge.pid try/catch 容错；慢启动存活 PID 持续探测 TCP（≤6s），存活时不删 pid 文件（消除孤儿桥） |
| windows/README.md | 被动检测行为说明补齐（多次开/关串口但 DTR/RTS 为低） |
| tests/test_serial_service.py | +2：`serial.close` 与设备丢失均清挂起扫描请求（transition 守卫 + `_device_action` 直调保证确定性） |
| tests/test_shared_serial_bridge.py | +3：`run_autobaud` 退出码 4/5/0（假 Client 注入 `serial_service_client.Client`）；文件头补 scripts 路径注入使单文件可跑 |
| tests/test_detect_serial_baud.py | +2：parse_probe 非 ASCII；被动采样 rts/dtr 为低（mock pyserial.Serial） |

## 验证证据

- 定向 34 项两轮全绿（8.2s / 7.6s）。
- 全套 100 项通过 + 1 项失败 `test_ui_log_noise::test_keypress_records_follow_the_show_keybytes_switch`——**判定为负载抖动**：全套当时 535s（基线 342s），该测试走 FakeWorker + `poll()` 12ms 事件预算；单跑 3/3 绿（2.2s），与本次改动模块无调用关系。
- ps1：PowerShell 5.1 Parser 校验通过；param 块含 `$Passive`；`AutoBaud` 分支 `-Passive:$Passive`。

## 踩坑记录（避免重复）

- **edit 工具重写 `serial_console.ps1` 会丢 UTF-8 BOM** → PS 5.1 按 ANSI 解析报大量假语法错误。修复：`[System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($true)))`。改完 ps1 必须重新校验 BOM + Parser。
- 本仓库无 conftest；`tests/test_shared_serial_bridge.py` 依赖字母序更前的 `test_detect_serial_baud.py`（其被测脚本自行插入 scripts 路径）才能导桥模块——本次已在文件头显式补 `sys.path.insert`。
- PS 5.1 下 `git push ... 2>&1` 会把 stderr 包成 NativeCommandError 掩盖真实错误；用 `cmd /c "git ... 2>&1"` 或临时文件收 stderr。
- 凭据 helper 双配置（系统 `manager` + 本地 `wincred`）曾致 `'C:\Program Files\Git\cmd\git.exe' is not a git command`；探测/推送用 `git -c credential.helper=`。

## 剩余工作与建议下一步

1. **推送**：`git push origin master`（待推：`5bd9670` + 本 handoff docs 提交）。网络恢复后先 `git -c credential.helper= ls-remote origin refs/heads/master` 探测。
2. **建 GitHub issue**（审查未修项，均在源码核实过）：
   - P1 `serial_gui_qt.py:277-281` ServiceWorker 桥死亡假在线（gaps 无人消费、call socket 仅发送时触碰）→ run 循环加 ~1s `status` 探活或事件线程存活检测，失败 emit error→closed。
   - P1 `serial_gui_qt.py:231-236` 接管失败 emit `'error'` 毒化健康会话（state='error' 但传输活着；发送全拒、接管按钮自禁）→ 改专用非致命事件。
   - P1 `serial_service.py:287-291, 417` `agent.takeover` 绕过 transition 检查且 `_revoke` 无条件清 transition → 扫描中被接管会让 writer 以候选波特率恢复发送；需等待/中止扫描。
   - P2 `serial_service.py:528-537` `_raw_notice` 无锁 pop `raw_clients`，可致 `_reader` KeyError 静默死亡（RX 永久停转发）。
   - P2 `serial_service.py:800-805` raw 客户端首次被拒 send 即断连（agent 租约期间人工终端每键位断连重连）。
   - P2 `serial_service.py:740-748, 344-361` 扫描暂停 check-then-act（≤50ms 窗口，读写线程可触设备）。
   - P2 `serial_service.py:528-537`/README:57 关联：`readability` 固定 UTF-8，GBK 日志设备会误触发自动重扫（P3）。
   - P2 PS 5.1 打包：`2>&1`/`2>$null` × `$ErrorActionPreference='Stop'` 吞原生 stderr（ps1:345, 95）；`Start-Process -ArgumentList` 含空格路径不加引号（ps1:136-138, 392）。
   - P3 择要：`serial_baud_scan.py:173-175` start 未知不恢复波特率；`shared_serial_bridge.py` 非零路径无 `autobaud_result:` 行；`serial_console.ps1:331` 用 `to=(\d+)` 抓人类可读输出；ps1:32 配置以 scriptblock 执行（应 Import-PowerShellDataFile）。
   - 测试缺口打包：ServiceWorker 失败路径、`peer_tx` 渲染、主动探测 UI 真发 `\r` 断言、JSON 持久化 round-trip、`serial_baud_scan` interrupted/SAMPLE_CAP/ambiguous、`detect_serial_port` main 退出码 5/1/130。
3. **实机验收**：按 `docs/test-plan.md` 第 6 节清单（L3-1…L3-7），需 RRAM_TEST 输出板接回（本机当前仅 COM4/5 蓝牙口，按设计被排除；本地配置 COM6/115200 完好）。
4. style token 改动同步上游 serial-gui 仓库（沿用旧待办）。

## 边界与并行会话（重要）

审查与修复期间有一个**并行会话**在同一工作区活动（GUI「打开并识别日志文件」功能），双方提交交错：
- 其功能与文档已作为 `c527d4e`（feat: open and recognize saved log files，serial_gui_qt.py +205、README.md、tests/test_ui_open_log.py 17 项）与 `4a0056f`（docs: test-plan.md + progress 记录）先后入库，均在 `5bd9670` 之后、本 handoff 提交之前；全套 101 项测试通过（其 progress 条目含同负载抖动的复跑说明，与本对话观察一致）。
- 本对话的 progress.md 压缩式改写被该会话的并发编辑覆盖（无冲突损失：其提交版本完整保留了本对话的快修条目与 `_Passive` 等事实），本 handoff 最终**放弃压缩**，仅在 HEAD 版本上追加归档行——后续会话若再做快照压缩，注意与并行会话串行化编辑。
- `../serial-debug.7z`（skills/serial-debug.7z，未跟踪）为历史离线包产物，勿提交。

## 建议技能

- 续接推送/提交：`git-delivery`（已验证流程与网络障碍处理约定）。
- 若继续修复审查项：直接按上表 file:line 动手；`code-review` 不必重复加载。
- 实机验收涉及串口安全（DTR/RTS、波特率切换）时遵守 `references/hardware-safety.md`。
