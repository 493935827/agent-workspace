# Handoff — serial-debug 离线包（Qt 工作台依赖一起打包）

- 日期：2026-10-14 14:52（Asia/Shanghai）
- 会话：DSH Web 会话（无对话 ID/链接可记录）
- 项目位置：`D:\App\agent-workspace\skills\serial-debug`（`C:\Users\E0465\.agents\skills\serial-debug` 为指向此处的 junction）

## 本次目标

把 serial-debug skill 打包为离线 7z（pack-to-dts 流程，输出 `D:\trash\Work\Innostar-ic\DTS`），Qt 工作台要求的 Python 库依赖一起打进包里。

## 已完成并验证

- 产出：`D:\trash\Work\Innostar-ic\DTS\serial-debug-offline-py310-win_amd64.7z`（78.3 MB，54 文件），解压出单层 `serial-debug-offline-py310\`：
  - `serial-debug\`：skill 完整源码 49 文件，按 .gitignore 排除（`.venv`、`__pycache__`、`windows/.runtime`、`windows/logs`、`serial_config.local.psd1`、`scripts/serial_qt_settings*.json`）
  - `wheels\`：`pyserial-3.5`、`PySide6_Essentials-6.12.0`、`shiboken6-6.12.0`（标签 cp310-abi3 / win_amd64 → Python 3.10–3.13 通用）
  - `setup_offline.cmd`：`python -m venv serial-debug\.venv` + `pip install --no-index --find-links wheels pyserial PySide6-Essentials`（含 Python 版本/位数前置校验）
  - `使用说明.txt`：安装步骤、常用入口、uv 环境替代命令、agent skill 安装路径
- 验证（uv 拉真 CPython 3.10.21 建独立 venv，仅用包内 wheel 离线安装）：
  - `--no-index` 离线安装成功，依赖闭环完整
  - offscreen 冒烟：Workbench 创建/显示/关闭 ×2 正常（QT_QPA_PLATFORM=offscreen）
  - 全量测试 51/51 通过（59.6s，对 staged 拷贝跑，与开发机一致）
  - 7z 解压回读：54 文件、中文文件名（使用说明.txt）完好

## 关键决策（避免重复推导）

- skill 内 `.venv` 不可直接搬：uv 管理，`pyvenv.cfg` 的 `home` 指向 `C:\Users\E0465\AppData\Roaming\uv\python\...`，换机即失效 → 依赖改用 wheel 方案，目标机自建 venv（`serial_gui.cmd` 已优先使用 `.venv`，装好即可双击启动）。
- 只打 PySide6-Essentials：GUI 仅 import QtCore/QtGui/QtWidgets/QtSvg，QtSvg 已核对属于 Essentials wheel（RECORD），不打 Addons/WebEngine，省约 580MB。`windows/requirements.txt` 的 `PySide6>=6.6,<7` 是在线元包写法，离线用 `PySide6-Essentials` 等效替代，差异已写进包内使用说明。
- 目标 Python 由用户选定为 3.10（与既有 `pyserial_py310_win_amd64.7z` 一致）；实际 wheel 为 cp310-abi3，不锁死 3.10。
- PySide6 6.12.0 与开发 `.venv` 版本一致。
- 本次未改动 skill 源码 → 不涉及同步独立 GitHub 仓库 493935827/serial-debug；推送目标为工程仓库 agent-workspace。

## 复现要点（staging 已清理，setup_offline.cmd/使用说明.txt 只存在于 7z 内）

```powershell
# wheels 下载
python -m pip download "PySide6-Essentials==6.12.0" "pyserial" -d wheels --only-binary ":all:" --platform win_amd64 --python-version 3.10 --implementation cp --abi cp310
# staging（排除清单对齐 .gitignore）
robocopy <skill-dir> <stage>\serial-debug /E /XD .venv __pycache__ .runtime logs .pytest_cache /XF *.pyc serial_config.local.psd1 "serial_qt_settings*.json"
# 验证
uv venv --python 3.10 --seed <verify-venv>
<verify-venv>\Scripts\python.exe -m pip install --no-index --find-links wheels pyserial PySide6-Essentials
# 需另装 pytest pytest-qt 后：QT_QPA_PLATFORM=offscreen python -m pytest tests -q
```

## 遗留 / 下一步

- 项目原有下一步不变：用 RRAM_TEST 输出板补设备级 RX 往返与被动波特率检测人工验收（先确认是否停板上的测试）；style token 改动同步上游 serial-gui 仓库。
- `skills/serial-debug.7z`（159.1MB，2026-10-14 13:38，仓库内未跟踪）是本会话开始前已存在的旧打包产物（疑似含完整 .venv 的早期尝试），已被 78.3MB Essentials 版取代；是否删除由用户决定，勿提交进 git。
- DTS 目录旧的 `pyserial_py310_win_amd64.7z`（仅 pyserial）仍在，可按需清理。
- 未被要求：把离线包安装脚本模板化进仓库（若要做，注意 serial-debug 的 Source Maintenance 约定需同步独立 GitHub 仓库）。

## 工作区 / git 状态（截至本 handoff）

- 工作树干净，除上述未跟踪 `skills/serial-debug.7z`。
- master 领先 origin/master：`cd2c676`（用户 2026-10-14 14:43 提交，handoff skill 的 intranet 提交规则改动，非本会话产物）+ 本次 handoff 提交，一并推送。
- 机器环境 `company`（在线区）；工程 remote：`https://github.com/493935827/agent-workspace.git`。

## 建议技能（不构成调用授权）

- `pack-to-dts`：再次打包/更新离线包时。
- `serial-debug`：继续串口调试工作流时。
