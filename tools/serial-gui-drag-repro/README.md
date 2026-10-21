# serial-gui 标题栏拖动复现台

诊断 2026-10-21 会话（serial-gui「窗口有时拖不动」）留下的真实鼠标注入复现脚本，
全部只针对**本进程自建窗口**注入（EnumWindows + PID 过滤），不会误伤用户正开着的串口工作台。

## 运行方式

```powershell
& 'D:\App\agent-workspace\skills\serial-debug\.venv\Scripts\python.exe' -X utf8 <脚本>
```

- 需要交互桌面（脚本会真的移动鼠标、短暂抢前台，单轮约 10–30 秒，运行期间别动鼠标）。
- 4/5/7 号脚本会拉起真实 Workbench 外壳（`persist=False`、空端口源），不写配置、不枚举串口、不碰硬件。

## 脚本清单（按轮次）

| 脚本 | 用途 | 关键结论 |
| --- | --- | --- |
| `drag_repro.py` | 首轮：基线/模态/真实 comports 风暴/主线程卡 600ms/5.6s/最大化 | comports 单次 5.2–11.8ms，120 连发阻塞 638–858ms；泵超时 200ms |
| `drag_repro2.py` | 复验：首次注入点击被吞、模态拒前台、未响应阈值 | 卡 5.6s 后 `IsHungAppWindow=true` |
| `drag_repro3.py` | A/B：TitleStrip + QMenuBar 仿制条 | 基线注入法校准 |
| `drag_repro4.py` | 真外壳探测：childAt/widgetAt + 布局实测 | QMenuBar `MinimumExpanding`：hint 321 → 实铺 496px |
| `drag_repro5.py` | 真外壳：菜单栏空白 / 纯空白 / 最大化分状态拖动 | 最大化时整条拖不动（startSystemMove 无效） |
| `drag_repro6.py` | 归属桩（monkey-patch 计数谁收到按下） | 菜单栏空白 press_menubar=1、press_strip=0 |
| `drag_repro7.py` | **决定性**：全局 MouseButtonPress 监听 + 分状态拖动 | 见下表 |

## drag_repro7 判定表（2026-10-21 实测）

| 拖的位置 | 按下事件接收者 | 位移 |
| --- | --- | --- |
| 标题文字区 | QLabel → TitleStrip | +130,+70 ✓ |
| 菜单栏与按钮之间纯空白 | TitleStrip | +130,+70 ✓ |
| QMenuBar 铺出的空白区 | QMenuBar（就地吞掉，不转发） | +0,+0 ✗ |

## 修复后回归

对 `skills/serial-debug/scripts/serial_gui_qt_prototype.py` 应用 DragMenuBar 补丁后：

1. `drag_repro7.py`：窗口化下 menu_empty 期望 `moved ≠ [0,0]` 且接收者为 TitleStrip/新子类；
2. `drag_repro5.py`：最大化后拖 brand 期望窗口先还原再跟手（若实施了还原逻辑）；
3. 手工验收：真窗口（用户日常那份）最大化/窗口化各拖一次菜单栏右侧。
