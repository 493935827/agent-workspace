# Handoff:桥读侧静默死亡——静态定位与修复

- 日期:2026-10-23 14:42(Asia/Shanghai)
- 来源对话:session `80b8704ba30e`(DSH Web GUI)
- 交付提交:`403cb92`(fix)+ `080692c`(progress 记录),均已推送 `origin/master`(493935827/agent-workspace monorepo,经 `ls-remote` 核实)
- 触发:用户转交另一台电脑上的自包含 bug 报告(截图):serial-debug 共享串口桥 RX 方向(串口→TCP/日志)自启动起完全死亡,TX 正常,`status` 全绿(`connected:true`/`error:null`),排障误导约 1.5 小时。板子被占用,要求先静态定位。

## 本次完成

### 1. 静态定位(证据链 → 根因)

- **事实钉死**:日志冻结 1080B + `log_dropped:0` ⇒ `_logger` 活着但 `log_queue` 零进账 ⇒ reader 线程对 `device.read` 零产出(死或卡死);`error:null` 恒成立是因为 `last_error` 的 4 个赋值点都不覆盖线程死亡。
- **主嫌(当前构建就存在)**:被动扫描线程(`_auto_baud_loop` → `scan_open_device`)与 `_reader` 并发调用同一 pyserial 对象的 `device.read()`。pyserial win32 每个串口对象共享**一个** `_overlapped_read` OVERLAPPED 结构,两个在飞重叠读未定义行为,可致 reader 永久卡死(GIL 释放、无超时、无异常、status 全绿)。原有 `scan_active` 门是无锁读 + 无"reader 已停车"握手,且 reader 生命周期几乎 100% 在 50ms 读内 ⇒ 扫描启动瞬间几乎必然重叠。探针实证:未修复代码 `max_active=2`,重叠约 400ms。
- **触发时序自洽**:开 COM6 → DTR 复位/驱动残留脏字节 → 开局乱码 ≥48B/3s → `_auto_baud_feed` 触发被动扫描 → 相撞 → RX 永久死。完美解释 `--autobaud` 相关性(健康实例无此开关)。
- **次嫌**:旧构建(<`367aed4`,10-20)reader `del raw_clients[sock]` KeyError 静默死亡(git diff + 注释自述吻合);触发需客户端队列积压+并发 drop,条件更多。报告机构建版本未核对。
- **混淆变量澄清**:菜单 ps1 默认 `Python="python"`(系统 Python310)+ `AutoBaudMonitor=$true` ⇒ "菜单拉起 = 系统 python + autobaud,agent 手工 = venv + 无 autobaud"——两个变量同源,一个开关翻两个。
- **静态排除**:扫描切错波特率(会留乱码字节+last_change 非空,与零字节矛盾)、logger 死(会 log_dropped>0)、锁死锁(长等待全走 Condition.wait)、read 永久阻塞(pyserial 3.x timeout=0.05 封顶)、**seed 代码(repo 内不存在,1080B 种子必为外部写入,报告疑点 #4 撤销)**。
- **取证判别**:菜单拉桥 stderr 落 `windows/.runtime/bridge_error.log`(ps1:152-153)但 ps1:128 每次 Start 会先删它;有 traceback ⇒ 线程异常死,为空 ⇒ 更可能卡死型(本修复前 pyserial read() 所有抛错路径均为 SerialException,reader 兜得住,异常死需罕见双故障)。

### 2. 修复实现(`scripts/serial_service.py`)

- 扫描握手:reader 增 `_reader_parked` 事件(停车 set、读前 clear、clear 后复检);`_auto_baud_loop` 置 `scan_active` 后先 `wait(READER_PAUSE_TIMEOUT=1.5s)`,超时以 `reason=reader_unavailable` 放弃并完整清理。
- 线程死亡上浮:`_thread` 包 `except BaseException` → `last_error` + `_emit('state')` + stderr;工作线程命名(`_reader`/`_logger`/…)。
- 看门狗:`_maintenance` 检查 `_reader_beat`(reader 每循环顶刷新)超过 `READER_STALL_SECONDS=5s` → `_panic`(last_error + emit + stderr + `stop.set()`)整桥大声退出。
- 数据面计数:`status` 增 `rx_bytes_total`/`tx_bytes_total`/`last_rx_timestamp`(epoch 秒或 None)。
- 日志会话头:`_logger` 开文件即写 `=== bridge session start <ts> pid=<pid> ===`。
- `close_socket` 的 `sock.close()` 收进 try/except OSError。
- 设备动作路径不需要同类握手:pyserial win32 `close()` 对在飞读执行 `CancelIoEx`(serialwin32.py:461),已安全。

### 3. 测试(`tests/test_serial_service.py` +ReaderRobustnessTests 5 项)

- 扫描互斥回归:**先红**(旧代码 `max_active=2`)**后绿**——注意第一版测试误绿,原因是断言时机早于扫描启动 + 未命名线程污染计数;改为等 `autobaud.status` scanning/requested 归零后再断言。
- 线程死亡上浮+看门狗、读停摆看门狗(假卡死 read)、rx/tx 计数、日志会话头。
- 全套 **123 项通过**(10m49s,offscreen),零回归。
- 教训:测试用 FakeSerial/loop://,win32 真驱动交错结构性不可测,`docs/test-plan.md` 的实机清单仍是必要关卡。

### 4. 文档与进度

- `references/shared-bridge.md` 增 "Bridge Health (data-plane status fields)" 节;`references/troubleshooting.md` 增 "TCP Alive But No Device Output (silent RX death)" 判别节。
- `progress/progress.md` 概况已改写(修复行 + 下一步)。

## 已实现未验证

- 真机 `--autobaud` 路径验收(报告机按其报告第 1 节:自环/任意有输出串口源复现 + 二分;菜单路径 + `--autobaud` + 系统 python 起桥,盯 `rx_bytes_total`)。
- win32 卡死语义的动态确认(哪种 OVERLAPPED 交错必现;可用 py-spy dump 抓卡死现场)。
- 报告机旧构建是否含 `367aed4`(`git log -1` 核对,判定 KeyError 次嫌是否在场)。

## 剩余工作 / 下一步

1. **报告机取证**(不需要板子):`windows/.runtime/bridge_error.log`(可能已被换桥重启删除)、死实例日志是否冻结 1080B、`git log -1`、系统 python `pip show pyserial`、`serial_config.local.psd1`。
2. **实机验收**:报告第 3 节三条(菜单路径起桥 RX 流;人为弄死 reader 数秒内 status 出 error 或进程退出;日志带头部)。注意新行为:reader 死亡后桥会**自行退出**,菜单 Status 会显示桥不在,重启即恢复——这是设计而非新 bug。
3. **跟进项**:菜单 ps1:128 的 `bridge_error.log`/`bridge_diagnostic.log` 改时间戳轮转(防换桥销毁物证);ps1 为 CRLF+UTF-8 BOM,编辑需保编码。
4. **同步评估**:本次推送目标是 monorepo `agent-workspace`;报告的 canonical 独立仓 `493935827/serial-debug` 本机无配置,若维护需单独同步。
5. GUI 侧(直连会话扫描在 reader 线程内串行执行,天然安全,无需改);`serial_gui_qt.py` 是否要展示新 status 字段,待用户定。

## 阻塞

- 板子(报告机)被占用:实机验收与 `--autobaud` 复现推迟;其余工作不依赖板子。

## 关键决策与已否决方案

- **采用** reader 停车握手 + 看门狗整桥退出(报告允许"自愈重启或大声退出"二选一,选了退出:重启会与卡死的旧 reader 在同一句柄上造出双 reader,恰是我们要消灭的形态)。
- **否决** "扫描期间 reader 独占读、喂扫描收集器" 的单读者重构:更彻底但改动面大,留作后续架构演进选项。
- **否决** 仅为种子日志实现 seed 机制:repo 无 seed 代码,会话头已达成判别目标。
- pyserial 版本差异(系统 python)降级为混淆变量:2.x 会在扫描里 AttributeError 响亮失败(last_reason 可见),不构成静默死;3.x 共享 OVERLAPPED 竞态与版本无关。
- 修复前定位讨论见本对话;`handoff-20261020-170100-review-p1p2-bugfix.md` 的 KeyError 修复(`367aed4`)是次嫌背景。

## 工作区状态

- 工作树干净(仅无关未跟踪 `D:\App\agent-workspace\serial-debug.7z`,勿动)。
- 本次涉及文件:`scripts/serial_service.py`、`tests/test_serial_service.py`、`references/shared-bridge.md`、`references/troubleshooting.md`、`progress/progress.md`(均已随 `403cb92`/`080692c` 推送)。
- 推送配方(本机有效):`$env:NO_PROXY=""; $env:HTTPS_PROXY="http://127.0.0.1:7897"; $env:GCM_INTERACTIVE="never"` + `git -c credential.helper= -c credential.helper=manager -c alias.push= push origin master`;git commit 传多行消息用 `-F <文件>`(here-string 内嵌双引号会被参数解析拆散)。

## 建议技能(不构成调用授权)

- 实机验收时:`serial-debug`(串口操作流程)、`git-delivery`(后续修复交付)。
- 深排障:`diagnosing-bugs`(本次已按其流程:红→绿回归锁死根因)。
