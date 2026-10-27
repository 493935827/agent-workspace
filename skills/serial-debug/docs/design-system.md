# Serial Workbench 统一风格（Design System）

最后更新：2026-10-27 · 适用于 `scripts/serial_gui_qt.py` 工作台与 `scripts/serial_gui_qt_prototype.py` 视觉外壳

## 一句话定位

**深色优先的开发者终端**：紧凑三栏工作台、单一蓝色强调、等宽日志区、语义化明暗双主题、无装饰动效。

决策依据：产品类型为开发者工具 / 串口控制台，风格库匹配结果为 Dark Mode + Minimalism（明确列出 "Light mode default" 为反模式）。**深色主题以 VS Code Dark Modern 为基准**（chrome `#181818` / 编辑区 `#1F1F1F` / 文本 `#CCCCCC`·`#9D9D9D` / 输入框 `#313131`+边框 `#3C3C3C` / 强调 `#0078D4` / 文本选区 `#264F78`，取自 microsoft/vscode `dark_modern.json`）；浅色主题沿用 Fluent 2 官方 token。语义别名体系不变，代码与 QSS 零改动即可换肤。

## 主题与颜色

- **唯一事实源**：`scripts/qt-preview-tokens.json`。代码与 QSS 只允许使用语义别名（`text_primary`、`brand_background_subtle`…），禁止组件内写裸 hex。
- **深色优先**：首次启动默认深色；用户选择持久化到 `serial_qt_settings.json` 的 `dark` 字段，之后以用户选择为准。
- **对比度红线**：正文级文本对背景 ≥ 4.5:1（WCAG AA）；禁用文本为豁免项，保底 ≥ 2.5:1。守卫测试 `tests/test_ui_tokens.py` 逐对校验，token 改动必须先过它。
- 品牌色：浅色 `brand_background`/`brand_foreground` = Fluent `#0f6cbd`（白字 5.38:1）；深色 `brand_background` = VS Code `#0078d4`（白字 4.53:1），深色 `danger_foreground` = `#f85149`（4.74:1），深色 `warning_foreground` = `#cca700`（7.13:1）。
- 深色层级约定（VS Code 同款）：侧栏/标签栏/状态栏 `#181818` 比日志画布 `#1F1F1F` 更暗；输入类控件 `#313131` 明显浮起；分隔线 `#2B2B2B` 极克制；文本选区 `#264F78` + `#CCCCCC`（编辑器选区，不是按钮蓝）；菜单选中 = 实心 `#0078d4` + 白字。
- 状态语义四色（info/success/warning/danger）各含 background / background_strong / foreground / border 四件套；**状态永远不许只用颜色表达**，必须配文字或图标（如会话状态 = 彩点 + 文字 + 图标三重编码）。

## 字体

| 用途 | 字体 | 基准字号 |
|---|---|---|
| 界面文本 | Microsoft YaHei UI（系统字体，不捆绑分发） | 7pt |
| 次要/说明 | 同上 | 6.75pt |
| 日志、命令、宏 | Consolas（等宽，Windows 系统自带） | 8pt |

- 整体界面缩放 75–200%（Ctrl+= / Ctrl+-），日志字号独立 50–300%（Ctrl+滚轮 / Ctrl+0），全部从 100% 基线换算避免累计漂移。

## 密度与布局

- 三栏结构：设备栏（可折叠至细条，Ctrl+B）/ 主区 / 检查器（Ctrl+Shift+B），分隔线可拖动。
- 紧凑 DevTools 密度：标题栏 30px、日志工具栏 28px、状态栏 23px、主按钮 min-height 16px（均按缩放比例联动）。
- 圆角 4px、边框 1px；用留白和层级区分区域，**不**给每个分组包卡片边框。
- **信息架构（2026-10-27 重组）**：一个动作一个家——高频动作进日志工具栏（清屏/保存/自动滚动/暂停，图标化），配置进检查器「设置」页分区（显示 / 日志文件 / 波特率 / 提醒 / 共享串口桥，heading+1px 分隔线，滚动容器），文件动作归「文件」菜单，「更多」只留会话与界面入口。禁止往「更多」菜单或设置页里继续平铺新功能；新配置先找对应分区，没有分区再建分区。守卫测试 `tests/test_ui_settings_layout.py`。

## 状态与交互

- 每个可交互控件覆盖 rest / hover / pressed / focus / checked / disabled 状态（见生成 QSS）。
- **焦点可见**：`:focus` 使用 `focus_border`（浅色纯黑 / 深色 `#0078d4`，即 VS Code focusBorder），不依赖 hover。
- **无效输入**：对话框校验失败使用行内红色提示（`Workbench.inline_form_error`），保留已输入值、对话框不关闭；错误文本用 `role="danger"` 标签。
- **状态栏错误**：`report_error` 在状态栏以 danger 色保持 8 秒（防止被 30ms 轮询覆盖），同时写入日志 ERROR 记录。
- 键盘优先：Tab 仅在命中宏时用于展开，否则保持焦点遍历；快捷键全集见「查看」菜单。

## 动效

有意保持克制：仅 Qt 原生 hover/pressed 变色，无自定义动画、无发光效果。终端工具的价值在信息密度与响应，不在装饰动效。

## 图标

统一 24-unit 描边 SVG 家族（stroke 1.6、圆角端点），定义于 `serial_gui_qt_prototype.py` 的 `ICON_PATHS`；图标按钮必须带 `accessibleName` 与 tooltip；禁止 emoji 当图标。

## 维护规则

1. 改颜色 → 只改 `qt-preview-tokens.json`，跑 `tests/test_ui_tokens.py`；
2. 改布局/控件 → 改 prototype 的 build 系列方法，跑 `tests/test_ui_style.py` 与全量测试；
3. 新增状态色 → 定义语义角色名（不是颜色名），补全 light/dark 两套值与对比度；
4. 双主题都必须截图验证（`python scripts/serial_gui_qt_prototype.py --capture <目录>`，offscreen 可用）。
