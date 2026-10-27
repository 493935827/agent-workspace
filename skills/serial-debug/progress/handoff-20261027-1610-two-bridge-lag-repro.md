# Handoff：双桥/重数据流卡顿——复现与根因定位（修复未实施）

- 日期：2026-10-27 16:10（Asia/Shanghai）
- 仓库：monorepo `D:\App\agent-workspace`，分支 `master`（归档时 `origin/master` 同步至 `a60480c`）
- 会话目标：用户报告「当有两个桥在跑时，会变得很卡」，要求复现；随后追加「在收到大量串口数据的情况下做其他操作，看下」
- 结论速览：**双桥本身无罪；真正的卡 = 线速数据流下 GUI 主线程被 `rerender()`/`find()` 全量同步操作冻结（每次切标签 2.6s、带搜索 10.7s），冻结期间事件队列爆满丢数据**。修复未动代码，待用户确认后实施。

## 复现环境（无硬件，可随时重跑）

全部脚本在 `%TEMP%\serial_repro\two_bridge_lag\`（临时目录，Git 外；成为正式回归前需迁入 `tests/`）：

| 文件 | 作用 |
| --- | --- |
| `fake_device.py` | 假串口设备（TCP 端点）：按 `--rate` 行/s 持续输出 RRAM_TEST 日志 + 回显按键（沿用 2026-10-20 `socket://` 假设备方案） |
| `probe.py` | 击键→回显 RTT 探针（原始 TCP 直连桥） |
| `control_probe.py` | 控制通道延迟探针（`status` / `serial.list`） |
| `gui_harness.py` | 仪器化离屏 Qt 工作台：挂 N 个服务会话，测量 poll/switch/rerender/find 耗时、10ms 心跳抖动、事件队列积压、GUI 发送延迟；`--ops` 启用操作调度（load→switch→search→sends→settle 五相位） |
| `run_two_bridge_lag.py` | 驱动：A 单桥→B 双桥→C 双桥+GUI 三阶段 RTT/CPU 对比 |
| `run_heavy_ops.py` | 驱动：双桥线速流 + GUI 操作调度 + 并发 RTT/控制探针 + 全进程 CPU |
| `micro_rerender.py` | 纯 GUI 微基准：合成 N 条记录测 `rerender()`/`find()` 伸缩律 |
| `ab_scrollbar.py` | A/B 归因：shipped `render_record` vs 去掉滚动条同步的逐字副本 |

测量结果 JSON 在 `%TEMP%\serial_repro\two_bridge_lag\logs\<tag>\`（`ops280`、`rate100`、`rate280fix`、`micro_rerender.json`、`ab_scrollbar.json`）。

## 关键测量证据

### ① 双桥无进程级劣化（排除了"两个桥"本身）

线速（每口 ~11.2KB/s ≈ 115200 饱和，双口）下：

| 场景 | RTT p50 | 桥/GUI CPU | GUI poll p95 | GUI 事件队列峰值 |
| --- | --- | --- | --- | --- |
| A 单桥 | 47.5-50.7ms | ≈0 | – | – |
| B 双桥 | 64.0-70.6ms（n=24 噪声） | ≈0/≈0 | – | – |
| C 双桥+GUI | 50.7-63.9ms | ≈0×3 | 13.2ms | 3 |

控制通道：`status` p50 1.3ms / p95 ≤2.4ms；`serial.list` p50 ~11ms（本机 `list_ports.comports()` 12.7ms，持锁影响小）。GUI 从不通过桥调 `serial.list`（已核实）。

附带发现（与桥数量无关的固有底噪）：单桥打字回显 p50≈50-65ms。来源：桥 reader `device.read(4096)`+`timeout=0.05`，pyserial win32 只设 `ReadTotalTimeoutConstant=50`、`ReadIntervalTimeout=0` → 凑不满 4096 字节必等满 50ms 才转发；writer 另有 `changed.wait(.02)` 20ms 轮询。**真实 COM 口同样如此**（已读 `.venv` 内 pyserial 3.5 源码确认），`socket://` 复现不代表失真。

### ② 重数据流 + 其他操作 = 秒级主线程冻结（决定性复现）

`run_heavy_ops.py --rate 280 --window 40`（双桥线速 + GUI 双会话 + 操作调度）：

| 相位 | 主线程表现 |
| --- | --- |
| load（纯数据流 8s） | 心跳 p50 10.05ms / p95 18.9ms，正常 |
| switch（每 2s 切标签） | 每次 switch **2587.6ms**（其中 rerender 1726.96ms），8s 窗口只采样到 4 次（应 ~40 次） |
| search（搜索框含 "seq"） | 每次 switch **10671ms**（rerender 7165ms + find 191ms/次×6） |
| sends | 心跳最长 gap **15840.67ms**（跨相位连续冻结） |

冻结连锁：`poll()` 停摆 → GUI `events` 队列钉死 512 → `ServiceWorker.emit` 背压 → 桥侧订阅队列（1024）溢出 `gaps++` **丢数据**（40s 窗口 GUI 仅收 181KB / 约 800KB 可用；RTT 探针同窗收满 400KB 证明桥侧转发正常）。

### ③ 根因：GUI 主线程的同步全量操作

1. **`rerender()` 全量重画**（`scripts/serial_gui_qt.py:1479`）：清空视图 + 逐条 `render_record`。触发路径：切会话标签（`switch`→`rerender`）、换行/过滤/暂停恢复等设置。微基准（`micro_rerender.py`，纯 GUI 无数据流）：成本随文档块数线性但常数巨大——单行记录 100 条 69µs/条 → 5000 条 164µs/条（总 O(N²) 倾向）；多行块记录 5000 块 ≈ 0.5-3s/次。
2. **`find()` 全文档扫描**（`scripts/serial_gui_qt.py:1833`）：逐匹配建 ExtraSelection + `setExtraSelections`；5000 块 + 每行命中关键字 ≈ 0.4s。且**搜索框有内容时每条 RX 记录都触发一次**（`add_record` 末尾 `if self.search.text(): self.find()`）。
3. **A/B 已排除**滚动条同步单变量（`ab_scrollbar.py`：nobar 与 base 同量级，偶有反向）——成本在逐条 insertText + 文档排版本身。实机联跑 11ms/条 vs 微基准 164µs/条的差距来自实机记录是多行块（同记录数下文档大 10 倍）。

### ④ 为什么用户感知"两个桥才卡"

单桥满缓冲切换同样冻 2.6s；单桥时人通常停在同一个标签不切。两块板来回看 → 每次点击都是全缓冲重画；两路数据让每次冻结后的追赶丢数翻倍。

## 已排除的方向（勿重复）

- 双桥 CPU/GIL/锁竞争：独立进程，实测 CPU≈0。
- `serial.list` 持锁慢：GUI 不调用；本机 comports() 12.7ms。
- ps1 菜单轮询：`Read-Host` 阻塞式，无轮询。
- GUI 服务客户端忙轮询：阻塞式收包；`poll_ports` 仅"检测串口"模式下运行。
- 桥侧 `--autobaud`/乱码误触发扫描：GUI 服务会话不向桥下发自动重扫（`serial.autobaud.configure` 无人调用），桥 CLI 默认关；仅直连会话有 `_feed_suspect`，且非本症状形态。
- 滚动条同步 O(N²)：A/B 排除为主因。

## 修复方向（未动代码，下一步）

按"先红后绿"实施，回归断言建议：

1. `rerender` 批量化/增量化：合并重建文档（一次 bulk insert 代替逐条 format+insert，预估 10-50×）或分帧渲染（QTimer/idle 分批，保持响应）。断言：全缓冲（~5000 块）rerender ≤ 阈值（如 200ms）。
2. `find` 防抖（~200ms 内合并为一次）+ 命中数上限（如 500 条后停止收集）。断言：重数据流 + 搜索激活时，单位时间 find 执行次数 ≤ 上限。
3. 冻结期合并 rx 事件再渲染（poll 排空时按会话合并 chunk 后一次渲染），减少放大丢数。
4. （可选，独立项）桥 reader 50ms 批量延迟优化：`timeout` 调小或读后立即转发——影响所有终端打字回显，收益 ~25ms 均值，注意 CPU 代价权衡。

实机验收（修复后）：真机双板线速流 + 来回切标签，人工确认不再冻滞；`docs/test-plan.md` 相关清单。

## 阻塞 / 待确认

- 无硬阻塞。修复实施前建议向用户确认方案取舍（bulk 重建 vs 分帧；find 上限数值）。
- 真机双板场景未验证（无硬件）；`socket://` 复现对 GUI 侧完全有效（GUI 路径不区分端口类型），桥侧 50ms 底噪已在 pyserial 源码层面确认对真 COM 同样成立。

## 工作区状态

- 本会话对仓库的唯一改动：`skills/serial-debug/progress/progress.md`（概况行）——已被并行会话的提交 `a60480c` 连带入库并推送（该提交同时含并行会话的 proc:// feature 与 close_race 线索，见其"下一步"行）。本 handoff + 归档表行为本 handoff 提交的新增内容。
- 工作树剩余：未跟踪 `D:\App\agent-workspace\serial-debug.7z`（他物，勿动）。
- 无残留后台进程（已清理全部 fake_device/bridge/gui/probe 进程）。
- 环境注意：本机有 COM4/COM5（主板串口，无板卡）；venv Python：`skills\serial-debug\.venv\Scripts\python.exe`。

## 建议技能（不构成调用授权）

- 继续修复时：`diagnosing-bugs`（Phase 5 修复+回归流程已进行到 Phase 5 前夜）、`serial-debug`（领域上下文）。
- 修复完成收尾时：`git-delivery`（提交推送配方见 progress.md 概况"推送配方"行）。
