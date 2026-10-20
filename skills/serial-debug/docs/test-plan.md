# serial-debug 工作流测试方案

适用对象：本仓库整条共享串口调试工作流（Windows 控制器 → 共享服务/桥 → 控制客户端 / 人工终端 / Qt 工作台 → 物理串口），以及波特率检测与离线交付。

术语与协议约定见 `README.md`、`SKILL.md`、`references/shared-bridge.md`、`windows/README.md`；当前进度见 `progress/progress.md`。

## 1. 目标与范围

- 目标：在改动合入前发现功能回归与协议破坏；在实机验收前用无硬件手段覆盖尽量多的逻辑；把必须真机验证的内容收敛为可打勾的清单。
- 范围内：`scripts/` 全部组件、`windows/` 控制器与配置、离线 7z 交付、帮助/引用文档与实现的一致性。
- 范围外：目标设备固件本身的行为正确性（只验证"工具如实转发与呈现"）；Conserver 路径（未安装时仅保留文档级检查）。

## 2. 被测工作流与组件

```text
[Windows 控制器 serial_console.ps1/.cmd + serial_config(.local).psd1]
        │  菜单 1/2/4/5/6/8/10；Action: Release/DetectConnect/AutoDetect/
        │  AutoBaud[-Passive]/Start/Status/Connect/Send/Ports/Stop
        ▼
[共享服务 serial_service(_cli).py]           [原始桥 shared_serial_bridge.py]
  管理端口 8889（JSON 行协议 v1）               raw TCP 8888（bridge/connect/send/autobaud）
  独占物理 COM 口；agent 租约；事件流；日志        独占物理 COM 口；转发 + 乱码监视
        │                                              │
        ├─ serial_control.py / serial_client.py / serial_service_client.py
        ├─ Qt 工作台 serial_gui_qt.py（直连会话 / 服务会话）
        └─ 人工终端（bridge connect / miniterm via socket://）
```

共用核心：`serial_protocol.py`（VERSION=1，单条消息上限 256 KiB、载荷 64 KiB、二进制 base64）、`serial_commands.py`、`serial_common.py`、`serial_baud_scan.py`（离线/在线共用评分）。

## 3. 测试环境分层

| 层级 | 环境 | 触发时机 | 方式 |
| --- | --- | --- | --- |
| L0 | 无硬件：fake serial、loop://、offscreen Qt | 每次代码改动 | 自动（pytest 全套，约 62 秒） |
| L1 | 无硬件：loop:// 端到端生命周期 | 每次影响服务/桥/客户端的改动 | 自动（套件内含）+ 可选冒烟脚本 |
| L2 | 无硬件：offscreen GUI 行为回归 | 每次影响 GUI 的改动 | 自动（套件内含） |
| L3 | 实机：COM6 RRAM_TEST 输出板 | 实机相关改动、发版前 | 手动清单（第 6 节） |
| L4 | 环境矩阵：PS 5.1 / uv shim / py3.10 离线 venv | 打包或安装链路改动后 | 手动 + 半自动 |
| L5 | 文档与安全默认值 | 文档或参数改动后 | 人工比对（第 4.L 节） |

L0–L2 运行方式（仓库根目录）：

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.venv\Scripts\python.exe -m pytest tests -q
```

当前基线：101 项全部通过（2026-10-20 本机 offscreen 实测约 530 秒；耗时随机器负载变化，只看通过与否。上一记录 77 项已过期——其后并行会话新增了测试，未同步更新基线）。基线变红时禁止推送，先修复或明确降级说明；定时类桥/服务用例（如 `RunAutoBaudExitCodeTests`、`test_serial_close_drops_pending_scan_request`）在整机高负载下偶发超时变红，隔离复跑即绿，复跑通过仍视为绿。

## 4. 测试用例矩阵

优先级：P0 每次改动必须绿；P1 发版前必须绿；P2 尽量覆盖。
"覆盖"列标注现状：`自动` = 已有 pytest 用例；`部分` = 有覆盖但存在缺口；`手动` = L3/L4 执行；`待补` = 尚无覆盖，按需补自动化。

### A. 协议与服务生命周期（serial_service / serial_protocol / serial_common）

| ID | 用例 | 优先级 | 关键步骤与预期 | 覆盖 |
| --- | --- | --- | --- | --- |
| A1 | hello/status/version | P0 | `hello` 带 version 1 通过；version 非 1 报错；`status` 返回设备、会话与日志健康信息 | 自动 |
| A2 | 消息边界 | P0 | 超过 256 KiB 的单条消息被拒绝；载荷超过 64 KiB 拒绝；非 JSON 行不至服务崩溃 | 自动 |
| A3 | 未知动作与非法参数 | P0 | `unknown_action` / `invalid_input` 返回错误而非断链；chardelay 超出 0–1 被拒 | 自动 |
| A4 | 事件订阅 | P0 | `subscribe` 后能收到 RX/TX/base64 事件；慢消费者丢事件能在 `status` 中体现且不影响 RX | 自动 |
| A5 | serial.close 语义 | P1 | 关闭设备后服务和 raw 客户端仍存活，禁用自动重连；`serial.open`/`serial.reconnect` 后恢复 | 自动 |
| A6 | service.stop 身份校验 | P0 | instance 不匹配拒绝；`--expect-pid`/`--expect-script` 不匹配拒绝；匹配则进程退出 | 自动 |
| A7 | 日志有界异步 | P2 | 长时间运行日志有界、落盘可读；日志错误不阻塞 RX | 部分 |

### B. 发送链路（send / send.hex / 编码 / 换行）

| ID | 用例 | 优先级 | 关键步骤与预期 | 覆盖 |
| --- | --- | --- | --- | --- |
| B1 | 文本发送 | P0 | UTF-8/GBK 编码正确；`cr`/`lf`/`crlf` 换行符合参数；订阅端收到同内容 `[TX]` | 自动 |
| B2 | HEX 发送 | P0 | `send.hex` 接受完整字节对（如 `AA 55 01 02 FF`）；半字节/非法字符在写入前被拒 | 自动 |
| B3 | 队列与并发 | P1 | 写阻塞时排队正确；队列满返回 `queue_full` 且不丢已写字节 | 部分 |
| B4 | unknown 语义 | P0 | 传输层死亡/非零退出时报错不自动重发；文档与客户端行为一致（本次结果未知不重发） | 自动 |
| B5 | 空闲呼叫通道自愈（回归） | P0 | 控制通道空闲 31 秒后发送仍成功：服务端 call 连接无空闲超时；`Client.call` 通道死亡自动重建并原样抛出本次错误；ID 错位同样重建 | 自动（2 项回归） |
| B6 | 设备级往返 | P0 | send 后设备应答（RRAM_TEST 板）完整呈现于订阅端与人工端；TX ≠ 设备已执行的语义在提示中可感知 | 手动（L3-1） |

### C. Agent 租约与并发（agent.acquire / heartbeat / takeover）

| ID | 用例 | 优先级 | 关键步骤与预期 | 覆盖 |
| --- | --- | --- | --- | --- |
| C1 | 获取与独占 | P0 | `agent.acquire` 返回凭证与心跳周期；未持 token 的变更动作被拒（`occupied`）；查看类动作（hello/status/autobaud.status/serial.list）不受限 | 自动 |
| C2 | 心跳生命周期 | P0 | 按周期心跳续期；停止心跳过期后旧 token 全部失效（`invalid_token`）；正常 `agent.release` 同样失效 | 自动 |
| C3 | takeover | P0 | `agent.takeover` 收回租约、取消排队任务；活动字节写入停止后才返回人工控制；返回后旧写入必然失败 | 自动 |
| C4 | 获取时序 | P1 | 有未完成发送时 `agent.acquire` 返回 `busy`，完成后可重试 | 自动 |
| C5 | 租约期间自动扫描暂停 | P1 | agent 租约期间乱码监视自动扫描暂停；手动触发不受影响 | 自动 |

### D. 端口互斥与共享

| ID | 用例 | 优先级 | 关键步骤与预期 | 覆盖 |
| --- | --- | --- | --- | --- |
| D1 | 单一持有者 | P0 | 服务已连设备时直连同口失败；直连占用时服务/桥启动失败；提示可指导用户释放 | 自动 |
| D2 | 双端同看 | P0 | 人工终端与 agent 客户端同时接入，双方看到同一份 RX/TX 与命令回显 | 自动 |
| D3 | GUI 关闭不伤服务 | P0 | 关闭工作台只断自身会话；服务、桥与其他客户端不受影响 | 自动 |
| D4 | raw 客户端兼容 | P1 | 旧 `bridge`/`connect`/`send`/`socket://` 用法在服务存在时仍可用 | 自动 |

### E. 桥健壮性与恢复（shared_serial_bridge）

| ID | 用例 | 优先级 | 关键步骤与预期 | 覆盖 |
| --- | --- | --- | --- | --- |
| E1 | 拔插重连 | P0 | 物理口消失后 TCP listener 存活、每秒重试重开；口恢复后恢复广播 | 自动 |
| E2 | 陈旧客户端清理 | P1 | 死连接被清理；interactive `connect` 断线自动重连且无 traceback；断连期间键入丢弃并提示重输 | 自动 |
| E3 | send 断线退出码 | P0 | 桥在响应空闲前断开时 `send` 非零退出，输出按"结果未知"处理 | 自动 |
| E4 | 日志落盘 | P2 | `logs/` 收到原始数据；`.runtime/` 保留启动诊断；loop 日志命名正确 | 自动 |

### F. 波特率检测（serial_baud_scan / autobaud / 乱码监视）

| ID | 用例 | 优先级 | 关键步骤与预期 | 覆盖 |
| --- | --- | --- | --- | --- |
| F1 | 评分核心 | P0 | 多候选下锁定真实波特率；数据不足/多结果过近拒绝猜测并保留原波特率 | 自动 |
| F2 | 离线主动/被动 | P1 | 菜单 10 方式 1/2：主动发回车探测；被动只读不发任何字节；结果写入 local.psd1；候选默认 8 档 + 当前值，离线 3 轮 | 自动 + 手动（L3-2） |
| F3 | 在线检测 | P1 | `autobaud --control 8889`：passive/active 两模式；exit 0/2/3/4/5/6 与语义一致；末行 `autobaud_result:` 可解析；成功后桥即时切换并全端提示 | 自动 + 手动（L3-3） |
| F4 | 中途换波特率（乱码监视） | P1 | 桥运行中设备换速 → 滑窗累计乱码 → 自动重扫 → 切换并提示；`AutoBaudProbe` 默认关；持续二进制流不误触发（可关 `AutoBaudMonitor`） | 自动（DriftSerial） + 手动（L3-3） |
| F5 | GUI 在线检测 | P1 | 直连会话工作线程内 `scan_open_device`，扫描期间收发暂停；服务会话走 `serial.autobaud` + `baud_scan`/`baud_changed` 事件；切换后同步会话波特率字段与 `SYS` 行 | 自动（test_ui_autobaud） + 手动 |
| F6 | 会话级开关持久化 | P1 | 「乱码自动重扫波特率」「允许主动探测」随会话保存于 `options['options']`，重启会话保持 | 自动 |
| F7 | 服务端事件渲染 | P2 | `baud_scan` 进度与 `baud_changed` 结果在服务会话日志区正确呈现，不产生重复提示 | 自动 |

### G. 串口自动检测（detect_serial_port / detect_serial_baud / 菜单 5）

| ID | 用例 | 优先级 | 关键步骤与预期 | 覆盖 |
| --- | --- | --- | --- | --- |
| G1 | USB 优先、蓝牙排除 | P0 | 有 USB VID/PID 的口优先；BTHENUM 等蓝牙虚拟口被排除；多候选给出数量与预选列表 | 自动 |
| G2 | 等待插入 | P1 | 无 USB 口时记录现有列表并等待至多 120 秒；拔插触发选中；Ctrl+C 可取消 | 部分 + 手动 |
| G3 | 检测后动作 | P1 | 菜单 5 保存端口 → 启动桥 → 打开 miniterm；桥运行中且同口直接开终端，异口询问后切换（DetectConnect 不询问） | 自动 + 手动 |
| G4 | local 配置写入 | P0 | 写入 `serial_config.local.psd1` 为 UTF-8 带 BOM；ANSI 编码不会损坏中文注释与 `Port` 行（回归 PS 5.1 编码根因） | 自动 |
| G5 | 释放与检测分离 | P1 | 菜单 4 只停桥释放；菜单 6 只检测保存不启动桥 | 自动 + 手动 |

### H. Qt 工作台（serial_gui_qt）

| ID | 用例 | 优先级 | 关键步骤与预期 | 覆盖 |
| --- | --- | --- | --- | --- |
| H1 | 会话管理 | P0 | 直连/服务两类会话建立、多标签并存、断开只影响自身 | 自动 |
| H2 | 日志显示 | P0 | `[RX]`/`[TX]` 标注、HEX/文本切换、ANSI 渲染、搜索；按键字节默认静默 + 「显示按键字节」开关；空行不渲染 | 自动（test_ui_log_noise） |
| H3 | 发送辅助 | P1 | 逐行宏按行发送；编码与换行按会话设置生效 | 自动 |
| H4 | 自动检测按钮 | P1 | 唯一 USB 口直连；多候选预选列表；无 USB 提示等待；蓝牙口不出现 | 自动（test_ui_detect） |
| H5 | 共享桥分组与一键停止 | P0 | 分组按会话类型显隐；`ServiceStopWorker`：status 取 instance → 必要时 takeover → `service.stop`；成功后桥退出、串口释放、残留 worker 退役（不假在线）；取消不动作；服务不可达写 ERROR 并置状态栏；未连接也能停运行中的桥 | 自动（test_ui_service_controls） + 手动（L3-4） |
| H6 | 错误呈现 | P1 | 发送失败、会话错误在状态栏/Tab 可见，不弹崩溃对话框；行内校验生效 | 自动 |
| H7 | 风格与可访问性 | P2 | Fluent 2 token 对比度 AA 达标；深色默认；风格回归测试通过 | 自动（test_ui_style/test_ui_tokens） |
| H8 | 打开并识别日志文件 | P1 | 文件菜单 Ctrl+O /「更多」/ 设置页入口；行首时间戳四类形态识别、无日期按文件日期补齐；UTF-8/UTF-16(BOM)/GBK 编码探测；无时间戳行并入前条、纯文本逐行成条；超缓冲截断与 SYS 摘要；导入不写入持续日志文件；文件缺失/为空写 ERROR | 自动（test_ui_open_log） |

### I. Windows 控制器（serial_console.ps1 / .cmd / 配置）

| ID | 用例 | 优先级 | 关键步骤与预期 | 覆盖 |
| --- | --- | --- | --- | --- |
| I1 | 菜单全流程 | P1 | 1 启动桥 → 2 开终端 → Ctrl+C 返菜单；关菜单桥不停；4 停桥；再进可查看状态 | 手动 |
| I2 | Send/Status Action | P0 | `-Action Send -Command "help"` 应用配置编码/换行且校验桥在管；`-Action Status` 报端口/波特率/PID/endpoint | 自动 + 手动 |
| I3 | 配置优先级 | P1 | local.psd1 覆盖默认模板；`Python` 字段指向 .venv 生效；`serial_gui.cmd` 优先 .venv | 自动 + 手动 |
| I4 | uv shim | P2 | `externally-managed` 环境按 README 的 uv venv 路径可用 | 手动（L4） |

### J. 硬件安全默认值

| ID | 用例 | 优先级 | 关键步骤与预期 | 覆盖 |
| --- | --- | --- | --- | --- |
| J1 | 控制线默认不动 | P0 | 全工作流默认不切换 DTR/RTS；打开/关闭串口不主动触发复位或 Boot 模式（用可观察复位日志的板验证） | 手动（L3） |
| J2 | 固定串参 | P0 | 8-N-1、无流控；参数不来自猜测 | 自动 |
| J3 | 状态变更宣告 | P1 | 复位/擦除/烧写类命令发送前必须宣告的约定在 SKILL.md/references 中一致，agent 行为可依此约束 | L5 文档检查 |

### K. 环境与交付

| ID | 用例 | 优先级 | 关键步骤与预期 | 覆盖 |
| --- | --- | --- | --- | --- |
| K1 | PS 5.1 JSON 传参 | P1 | `--%` 停止解析符下 `send.hex --params` 内嵌引号存活 | 手动（L4） |
| K2 | 控制口占用 | P1 | 8889 被占时给出明确提示；换端口参数后服务 + 会话成对可用 | 自动 + 手动 |
| K3 | 离线 7z | P1 | PySide6-Essentials + pyserial wheel 离线装进 py3.10 独立 venv；77 项测试在该环境复跑通过 | 手动（L4，每次打包） |
| K4 | 端口检测辅助 | P2 | `python windows/detect_serial_port.py --list-json` 列出真实口且不含蓝牙口误导项 | 自动 |

### L. 文档一致性（L5，文档或参数改动后人工比对）

| ID | 检查点 | 优先级 |
| --- | --- | --- |
| L1 | `references/shared-bridge.md` 的 autobaud exit codes（0/2/3/4/5/6）、默认端口（8888/8889）与实现一致 | P1 |
| L2 | `windows/README.md` 的配置键（AutoBaudMonitor/Probe/Seconds/Rounds、BaudCandidates 等）与 `serial_config.psd1`、脚本读取逻辑一致 | P1 |
| L3 | `SKILL.md` 工作流命令可直接复制执行（含 loop:// 冒烟） | P1 |
| L4 | `references/hardware-safety.md` 与实际控制线行为一致（默认不动 DTR/RTS） | P1 |

## 5. 执行节奏与准入准出

- 每次代码改动（准入）：L0–L2 全套 pytest 绿 → 允许提交；涉及服务/桥/GUI 之一时，额外跑该组件对应的 P0 手动冒烟（无板时用 loop:// 并如实标注"仅桥/客户端验证"）。
- 实机验收（准出）：L3 清单逐项打勾；任何一项不过，修复后从 L3-1 重新执行该组件相关项。
- 发版（打包/推送前）：L3 全清单 + K3 离线环境复验 + L5 文档比对。
- 报告：按 `SKILL.md` Reporting —— 记录共享 endpoint、物理口、波特率、命令、退出码与关键输出摘录；无实机时明确写"仅桥/客户端验证，设备往返待人工"。

## 6. 实机验收清单（COM6 RRAM_TEST 板）

前置：板子已接 USB；`serial_config.local.psd1` 为 COM6/115200；已确认板载测试日志是否需要停止。

- [ ] L3-1 设备级往返：人工终端与 agent 各发 `help`/读内存类命令，双方同屏看到命令与设备应答；`send` 退出码 0。
- [ ] L3-2 被动波特率检测：菜单 10 方式 2（被动），不向设备发任何字节；配合按复位制造日志流，结果写回配置；再验主动方式 1，确认提示"会多次开关串口可能复位"。
- [ ] L3-3 在线检测（中途换波特率）：桥运行中把设备切到另一波特率制造乱码 → 自动重扫切换 + `SYS`/中文提示；再用「在线检测波特率」按钮手动触发被动/主动各一次；GUI 会话波特率字段同步。
- [ ] L3-4 停止桥并释放端口：服务会话一键停止 → 桥进程退出、COM6 可被其他工具打开、工作台无假在线；重复一次"未连接会话时停止仍在运行的桥"。
- [ ] L3-5 Agent 接管：`agent.acquire` 后人工点「终止 Agent 并接管」→ 排队取消、旧凭证失效、人工恢复控制。
- [ ] L3-6 拔插恢复：运行中拔掉 USB → 终端提示、无崩溃 → 重插 → 桥自动重开并恢复输出；期间 agent `send` 得到非零退出并按未知处理。
- [ ] L3-7 控制线与复位：连接/断开/检测各一次，观察板子无意外复位（J1）。

## 7. 缺陷记录与回归

- 缺陷按组件标注（如 `service:` `bridge:` `gui:` `ps1:`），复现步骤引用本方案用例 ID。
- 每个修复必须带回归用例（自动优先；不可自动化的写入第 6 节对应项并注明）。先例：B5（31 秒空闲通道自愈，修复前红/修复后绿的 31 秒复现脚本）。
- 用例矩阵中"待补"项在对应组件下一次改动时优先转自动。

## 8. 当前已知未验收项（与 progress.md 对齐）

1. 设备级 RX 应答往返（B6 / L3-1）——已具备 COM6 板条件。
2. 被动波特率检测实机（F2 / L3-2）。
3. 在线检测·中途换波特率实机（F3/F4 / L3-3）。
4. 停止桥并释放端口实机（H5 / L3-4）。
