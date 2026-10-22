# Handoff：serial-gui 标题栏拖拽死区修复（2026-10-22）

- 会话：DSH Web GUI（本地 `http://127.0.0.1:5719`；本 harness 未暴露会话 ID，索引行以「标题栏拖拽死区修复」标识）。
- 前序对话：`session-86feed6014c3`（2026-10-21 拖动诊断，归档于根仓库 `progress/handoff-20261021-153400-serial-gui-titlebar-drag.md`；注入台在 `tools/serial-gui-drag-repro/`）。
- 状态：修复已提交并推送；**实机人工验收未做**。

## 目标与范围

用户报告工作台标题栏红框区域（菜单右侧 + 下方会话标签行空白）仍拖不动窗口，要求查因并修复。范围仅限 `skills/serial-debug/scripts/serial_gui_qt_prototype.py` 的标题区交互；不改布局几何、主题与业务行为。

## 根因（红框 = 两个相邻死区）

1. **菜单栏铺宽死区（标题行内）**：`QMenuBar` 默认水平尺寸策略 `MinimumExpanding`，布局把它从可见菜单项（hint 321px）铺到 496px；这块不可见区域把鼠标按下就地吞掉、不转发 `TitleStrip`，`startSystemMove()` 不触发。红框右缘 ≈724 逻辑像素与铺宽右边界重合（诊断台 4/6/7 号脚本实测）。
2. **会话标签行空白（红框下半部）**：`tab_row` 是普通 `QWidget` 容器，空白处按下无人处理，本就不是拖拽区。
3. 附带确认：最大化状态下整条标题区 `startSystemMove` 均无效（诊断台 5 号结论），原生行为应是「先还原再跟手」。

## 修复（`998c023`，主工作台 `serial_gui_qt.py` 经继承自动生效）

- 新增模块级 `begin_window_move(widget, event)`：最大化时按 `normalGeometry()` 水平比例定位还原窗口、抓取点保持在光标下，再交给系统移动循环；未最大化直接 `startSystemMove()`。
- `TitleStrip` 泛化为 `DragStrip(QWidget)`（空白区左键拖动、双击切换最大化），`TitleStrip(DragStrip)` 保留原名兼容 `w.title_strip` 引用与诊断脚本。
- 新增 `DragMenuBar(QMenuBar)`：`actionAt(pos) is None` 的空白区按下/双击走拖动/最大化切换，菜单项本身行为不变。
- `row()` 帮助函数加 `host=QWidget` 参数，会话标签行改 `host=DragStrip` 承载。
- 明确未采用：改 QMenuBar 尺寸策略压缩铺宽（会失去 VS Code 式「菜单栏空白可拖」手感，且接管按下后死区自然消失，不必动布局）。

## 验证证据

- **决定性**：`drag_repro7.py` 真鼠标注入（真实桌面，本机 125% 缩放）——`C_menu_empty_noalt` moved=[130,70] ✓、按下接收者 `DragMenuBar`；A/B/D（stretch 带 Alt/不带 Alt、brand 标签）保持 [130,70] ✓。实测菜单栏 x=255、宽 496、hint 321，与诊断一致。
- 离屏冒烟 `tools/serial-gui-drag-repro/smoke_after_fix.py`（新增并入库，offscreen）：类型接线、菜单栏/标签行空白按下、菜单项不受影响、最大化按下先还原（isMaximized→False）全过，EXIT=0。
- 全套 118 项测试 OK（offscreen 1063s，`python -m unittest discover -s tests`）。
- QSS 兼容性核对：`QMenuBar` 类选择器覆盖子类，`#top`/`#tabs` objectName 未变。

## 已实现未验证 / 待人工验收

1. **实机三步**（用户日常那份 GUI，需重启加载新代码）：① 菜单右侧红框区拖动；② 标签行空白拖动；③ 最大化后拖标题区 → 应先还原、抓取点跟手。
2. **最大化还原跟手仅离屏验证**：`drag_repro5.py` 未复跑（需真鼠标注入）；离屏只验证了状态切换与几何计算路径。
3. 标签行空白未单独做真鼠标注入（与菜单栏同一 `begin_window_move` 机制，离屏已验证接收者）。

## 剩余工作与下一步

- 若人工验收发现新死区：回到 `tools/serial-gui-drag-repro/`（README 已更新修复后回归判定表；7 号脚本 `dump_points` 可直接定位覆盖者），按 `childAt`/PressSpy 归属排查。
- 随后按 `progress/progress.md` 概况「下一步」推进：P2 PS 5.1 健壮性（ps1 `2>&1` 吞 stderr、空格路径加引号）、P2 readability 固定 UTF-8、P3/测试缺口打包；用 RRAM_TEST 板按 `docs/test-plan.md` 第 6 节补实机清单（先确认是否停板上的测试）。
- 遗留注意：style token 改动需同步上游 serial-gui 仓库（根概况既有约定）。

## 文件与提交

- 修改：`skills/serial-debug/scripts/serial_gui_qt_prototype.py`（+69/−14）、`skills/serial-debug/progress/progress.md`、`tools/serial-gui-drag-repro/README.md`、新增 `tools/serial-gui-drag-repro/smoke_after_fix.py`。
- 提交：`998c023 fix(serial-debug): drag window from menu bar and session tab blank areas`（2026-10-22 11:12），已推送 `origin/master`（0a51cbd..998c023），本地与远程同步（ahead 0）。
- 工作区遗留：未跟踪 `skills/serial-debug.7z`（非本任务产物，未动）；诊断台临时输出在 `%TEMP%\repro7_out.json`、`%TEMP%\smoke_out.txt`（临时文件，不持久）。

## 决策记录（避免重复踩坑）

- QMenuBar 空白区「接管按下」而非「改尺寸策略」：保留原生手感、不动布局，且诊断证明事件级接管可行。
- 最大化还原用 `normalGeometry()` + 光标水平比例，未引入计时器/事件重放；`showNormal()` 后同步 `move()`，随后 `startSystemMove()` 进入系统移动循环。
- 未动 `WindowsSnapLayoutAdapter`（HTMAXBUTTON 仅归属最大化按钮，与拖拽互不干扰）。
- QSS 全部按 objectName/类选择器命中，未新增样式；`row()` 其他 18 处调用点默认行为不变。

## 建议技能（不构成调用授权）

- `pyside6-fluent-ui`：标题栏契约（frameless 剖面、Snap Layout、原生行为保留）。
- `git-delivery` / `handoff`：按项目约定收尾与归档。
