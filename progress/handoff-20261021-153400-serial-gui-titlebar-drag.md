# serial-gui 标题栏拖动诊断（session-86feed6014c3）

- 日期：2026-10-21 15:40（Asia/Shanghai）
- 会话：DSH `session-86feed6014c3`（id 取自会话临时目录，若与 GUI 会话列表不符以列表为准）
- 主题：串口工作台（serial-gui Qt 版）"窗口有时候拖不动 / 这段位置拖动无反应"的诊断与复现

## 目标与范围

用户报告工作台窗口有时拖不动，并给出截图圈出"菜单栏右侧那段标题栏"拖动无反应。
本会话只做诊断与复现，**未改任何源码**；修复补丁已备好，等用户确认后实施。

## 结论（三因，均已实测复现）

1. **无边框标题栏死区（用户圈的位置，窗口化时）**：顶栏是自绘 `TitleStrip`（整行按下即 `startSystemMove()`），
   但 `QMenuBar` 以 `MinimumExpanding` 水平策略把"帮助(H)"右侧到标题按钮之间的多余宽度全部占走
   （实测 sizeHint 321px → 实铺 496px；最大化时铺到 1073px）。Qt 的 `QMenuBar::mousePressEvent`
   对空白区的按下**收下但不转发**（不 ignore 不冒泡），`TitleStrip` 永远收不到 → `startSystemMove` 不执行 → 拖不动。
2. **最大化时整条拖不动**：`startSystemMove()` 对最大化窗口是空操作，工作台未实现 Win11 式"拖动先还原"。
   用户截图正是最大化状态。对照：原生标题栏窗口拖最大化会还原再跟手（首轮 P5 实测）。
3. **主线程被占 / 模态（"有时候"的其他来源，第一轮复现）**：
   - `list_ports.comports()` 本机单次 5.2–11.8ms；120 连发阻塞 GUI 线程 638–858ms，期间消息泵
     `SendMessageTimeout(WM_NULL)` 200ms 超时，拖动被吞、松手后窗口迟跳；
   - 主线程卡 >5s 触发 `IsHungAppWindow=true`（"未响应"，整窗冻结期拖不动）；
   - 模态对话框（`exec()`）开着时系统拒绝把前台切回主窗口（实测 `fg_switch_to_main_ok=false`）。
   - 对应代码：`skills/serial-debug/scripts/serial_gui_qt.py` 的 `refresh_devices`(756)、`poll_ports`(803)、
     `save_settings`(2105)、各处 `exec()`（858、946 等）；枚举与写盘都在 GUI 线程同步执行。

## 关键证据

- 事件级（决定性，`tools/serial-gui-drag-repro/drag_repro7.py`）：
  菜单栏空白 press→`QMenuBar` 就地吞掉、位移 +0,+0；标题文字/纯空白 press→`TitleStrip`、位移 +130,+70。
- 布局实测（`drag_repro4.py`）：菜单栏 x=255、宽 496、hint 321、策略 `MinimumExpanding`；childAt 在纯空白段为 None（归属 TitleStrip）。
- 最大化（`drag_repro5.py`）：最大化后拖 brand 与 menu_empty 均位移 0；还原后 brand 恢复可拖。
- 完整判定表与逐脚本说明：`tools/serial-gui-drag-repro/README.md`。

## 已完成

- 三因复现台 7 个脚本（真实 SendInput 注入 + 前台校验 + 消息泵延迟/未响应/childAt/事件监听探针），
  已固化到 `tools/serial-gui-drag-repro/`（临时目录 `C:\Users\E0465\AppData\Local\Temp\drag-repro\` 的副本可弃）。
- 向用户解释了机制与修复方案；用户未答复是否实施即调用 /handoff。

## 未实施（下一步）

1. **应用补丁**（改 `skills/serial-debug/scripts/serial_gui_qt_prototype.py`，正式版 `Workbench` 经 `Preview` 继承自动生效）：
   - `build()` 736 行 `menu = QMenuBar()` 换成子类 `DragMenuBar`：空白处（`actionAt(pos) is None`）左键按下 →
     `self.window().windowHandle().startSystemMove()`；双击 → `self.window().toggle_maximize()`；
   - 可选：`TitleStrip.mousePressEvent`（164 行）在 `isMaximized()` 时先 `showNormal()` 再 `startSystemMove()`（Win11 拖动还原）。
2. **回归**：按 `tools/serial-gui-drag-repro/README.md` 的"修复后回归"跑 7 号与 5 号脚本 + 真窗口手工验收。
3. **可选项**（用户未拍板）：`comports()` 枚举挪后台线程（`port_provider` 注入点已留好）；模态弹窗行为保持现状即可。

## 决策与坑（避免重走）

- 注入只打本进程窗口（EnumWindows + PID 过滤），避免误伤用户正在运行的工作台实例。
- 注入坐标必须在每次窗口位移后重新 dump（早期轮次因 stale 坐标得到假阴性，见 3 号脚本的教训）。
- `QMenuBar` 与 `addStretch()` 共存时的实际宽度以实测为准（Qt 6.12 下 MinimumExpanding 确实抢占多余宽度）。
- 首次注入点击可能被"激活"吃掉，判读基线结果时注意（测试伪影，不作为用户现象结论）。

## 工作区状态

- 仓库 `agent-workspace`（master → origin 同名）：本会话改动 = 本 handoff、`progress/progress.md` 索引行、
  `tools/serial-gui-drag-repro/`（7 脚本 + README）。其余工作树仅 `?? skills/serial-debug.7z`（非本会话产物，保留未动）。
- 概况记录的 3 个待推送提交（956c36c 等）与本会话无关，推送状态见概况阻塞行。
- 本会话未修改 `skills/serial-debug/scripts/` 下任何文件；GUI 源码状态与 10-20 会话提交后一致（未逐 commit 核对）。

## 建议 skills

- 实施修复与收尾提交时：`git-delivery`（按改动验证 + 自动提交推送）。
- 回归运行注入台不需要额外 skill；重新诊断类问题可用 `diagnosing-bugs`。
