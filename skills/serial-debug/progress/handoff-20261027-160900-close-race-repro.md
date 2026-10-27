# 关窗竞态（板机 COM6 桥自退）无硬件复现 — 2026-10-27

会话标识：DSH Web GUI 本地对话（无对外可引 ID），完成于 2026-10-27 16:09 前后。

- 来源：用户转述板机（另一台电脑）会话的事故报告截图：COM6 桥（TCP 8888 / 控制 8889）起桥约 1 分钟后自退，stdout 留证 `_reader thread died: TypeError("'byref() argument must be a ctypes instance, not NoneType'")`，5s 后看门狗整桥退出。板机会话已修复（`serial_service.py` 新增 `_parked_reader()` 停车握手接入三个关窗路径 + 读写线程补捕 TypeError/AttributeError），**修复未回流本仓库**。
- 本会话目标：在无硬件的开发机复现该竞态并验证修复机制（用户指令「尝试复现这个」）。

## 复现结论（全部成立）

- 机制（pyserial 3.5 `serialwin32.py`；仓库 `.venv` 与全局 uv 两份文件 hash 一致）：`close()`:245-249 先 `_close()`（:237 置 `_overlapped_read=None`、:243 置 `_port_handle=None`）**后** `is_open=False`（:249）；`read()` :268 检查 `is_open` → :271 `self._overlapped_read.hEvent`（AttributeError 崩点）/ :285、:290 `ctypes.byref(self._overlapped_read)`（TypeError 崩点，与板机日志一字不差；截图里的 `"b'ref()"` 即 `byref()` 被引号渲染吃字）。
- 桥侧放大（`scripts/serial_service.py`，HEAD 状态）：`_reader` 只捕 `(OSError, serial.SerialException)`（:934），意外异常逃逸 → `_thread` 记 `thread died` + `status.error` → `_maintenance` 5s 看门狗 `_panic` 整桥退出（:634-637）。三个关窗路径均无停车握手：`_device_action`:563（serial.close/reconnect/open/stop）、`_disconnect`:601（错误断连）、`close()`:210（桥停机）。
- 红证据：本仓库 HEAD 代码 + COM4（蓝牙 SPP，无板、不发数据）+ 2 个控制连接连打 `serial.reconnect` → **6/6 复现**（1+5 轮），两种异常都出现；每轮序列 = `thread died` 行 → 5s → `reader thread stalled or died (no progress for 5s); stopping the bridge` → 桥退出。锐化仅一处：子进程 `sys.setswitchinterval(1e-4)`（生产默认 5ms、关串口偶发 → 分钟级一遇，与事故观察一致）。
- 绿证据：按报告描述移植的最小修复副本（`_park_reader` 事件握手：`_reader_park_requested` 置位 → 读线程停驻 `device.read()` 之外 → 等待 `_reader_parked`；接入上述三路径；读写线程 catch 增 TypeError/AttributeError 降级为断开+1s 自动重连）→ 同压力 **30s / 6030 轮 reconnect 全 ok**、`connected=True`、无错误。

## 验证证据（实测输出摘要）

- RED 单轮：`{'outcome': 'RED_HIT', 'death_line': '…TypeError("byref() argument must be a ctypes instance, not \'NoneType\'")', 'panic_line': '[串口桥] reader thread stalled or died (no progress for 5s); stopping the bridge', 'seconds_to_death': 0.02, 'bridge_exited': True, 'reconnect_ok': 1495}`
- RED 循环（red_loop.py）：5/5 hits；异常类型 AttributeError×3 / TypeError×2；t=0.00–0.03s。
- GREEN：`{'outcome': 'GREEN_SURVIVED', 'seconds': 30.34, 'reconnect_attempts': 6030, 'reconnect_ok': 6030, 'final_status': {'connected': True, 'error': None}}`

## 复现套件（`%TEMP%\serial_repro\close_race\`，仓库外，保留作回归基准）

- `run_repro.py`：红/绿对照主脚本（make_fixed 生成补丁副本 → 起真桥子进程 → 校准：设备在线 + 读循环 >5s 不触发看门狗，防假红 → reconnect 连打 → 断言死亡行/看门狗/退出；绿相断言存活）。
- `red_loop.py`：RED 5 轮重复（复现率 + 异常类型收集）。
- `make_fixed.py`：从仓库 `scripts/serial_service.py` 用精确锚点生成 `serial_service_fixed.py`（9 个补丁，锚点唯一性强制校验）——**回流修复时可对照的移植清单**。
- `bridge_child.py`：桥子进程宿主（真 SerialService，可选加载补丁副本）；`debug_probe.py`：蓝牙口/控制协议诊断。
- 运行解释器：仓库 `.venv`（pyserial 3.5）。

## 关键决策与坑

- 未用 socket:// 假设备：其 read/close 无 win32 OVERLAPPED 语义，复现不了这两种异常（socket:// 只适合业务层 bug，此前两次调查的用法不通用）。
- 蓝牙 COM4/COM5 当真实 win32 comm 设备：反复开关稳定、read ~63ms/次（50ms 超时+开销）、无数据也走完整 ReadFile/GetOverlappedResult 路径；只开不发送，对用户无扰。
- 桥控制协议坑：每个请求必须带 `version: 1`（serial_service.py:293），否则 `ActionError('version')`、result 为空——首轮复现因此空转，靠校准守卫拦住。
- 红的判据必须是 `thread died` 行：单纯桥退出可能是读循环 wedge 触发看门狗（假阳性），校准阶段即排除。

## 工作区与推送状态

- 本会话对仓库的唯一实质改动（progress.md 概况三处）已被并行会话随 `a60480c`（proc:// 功能，已推送）一并提交，其提交说明明确标注「progress.md also carries two completed records from a parallel session (dual-bridge lag diagnosis, close-race repro) per repo convention」。
- 工作区遗留：untracked `skills/serial-debug.7z`（离线包产物，非本会话，勿动）。
- 板机侧修复文件本机不可得（不同机器）；本会话未见过板机原始 diff，绿对照基于截图描述的移植。

## 剩余工作 / 下一步

1. **把板机 `_parked_reader` 修复回流本仓库 `scripts/serial_service.py`**：若能拿到板机 diff 优先对照；否则按 `make_fixed.py` 的 9 补丁移植。先红（HEAD 上 `red_loop.py` 应 5/5）后绿（回流后应 0/5 且 `run_repro.py` 绿相存活），再跑全套 pytest 回归（`a60480c` 后基线 157 项，GUI 风格类占时 ~16min，可按需选子集）。
2. 回流后更新 progress 概况关窗竞态行的「待板机回流」状态。
3. 真机验收（待板子在线）：按板机报告方式 `serial.reconnect` 连打 5 轮 + 盯 `rx_bytes_total`；注意 COM23 桥与用户 GUI 重启后才带修复。
4. 并行线（他人负责）：GUI rerender/find 卡顿修复（先红后绿：全缓冲切换冻结阈值断言 + find 触发次数上限）。

## 建议技能

- 实机验收时用 `serial-debug`（共享串口桥工作流）。
- 若回流后复现率异常（红相不再 5/5），按 `diagnosing-bugs` Phase 1 收紧回路再定位，不要直接改判据。
