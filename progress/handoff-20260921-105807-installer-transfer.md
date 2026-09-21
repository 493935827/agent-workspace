# 本机软件选择与安装包传输交接

日期：2026-09-21（Asia/Shanghai）
对话标识：01a0bd75-e323-7861-a7bf-29d55160ebeb（本线程产物目录标识）

## 当前目标与最新决定

- 项目长期目标仍是跨环境重建开发环境；本轮下一步改为准备并传输实际安装包。
- 用户原话：“算了，直接传安装包吧”。不要再次将仅推送软件清单作为本轮交付，也不要先扩展通用安装执行器。
- 用户已亲自填写 Excel：公司笔记本 51 项，内网 44 项，无待定或无效选择。以下表格是交接时重新读取的完整选中记录，后续以用户选择为准。
- 公司/内网不需要游戏。个人环境“游戏本体不传，只传游戏平台”；本机游戏平台候选为暴雪战网、WeGame、Xbox、START 云游戏、小米游戏盒子。它们在用户填写的公司和内网列均为否，不能擅自改成是。个人平台具体取舍未逐项填写。
- 阻塞：安装包上传目标未提供，已询问网盘、共享目录、文件服务器或本地目标文件夹。Git origin 仅是代码/交接记录的已授权目标，不等于安装包目标。

## 本轮完成与验证

- 实际运行项目虚拟环境下的 agentctl 完整扫描：218 项＝Winget 187 + npm 4 + VS Code 27；uv 成功为空、pipx 不可用、pnpm 查询失败。20 项精确版本未知。系统 PATH 的 Python 首次运行返回 configuration-or-state-error；改用 .venv 后得到上述扫描结果，未诊断系统解释器问题。
- 初始扫描状态 NEW 92、UNKNOWN 126。未执行 adopt/snapshot，没有修改 resources 配置或保存机器扫描基线。
- 创建带筛选、下拉选项、统计和备注的 Excel；再次读取 Winget 清单，为 187 项 Windows 条目补全名称。对初选 Excel 执行过视觉检查，验证 218 行、表格范围和两列数据验证、公式无错误。用户随后自行修改选择，交接时重新读取确认 51/44，无待定。
- 公司选中来源：Winget 已识别 15、编辑器扩展 26、unknown 10；内网分别为 12、26、6。未知来源不等于不需要，也不能把 unmanaged 编号当作可下载安装的软件 ID。
- 公司独有 7 项：飞书、GlobalProtect、Node.js、Omnissa Horizon Client、RealVNC、微信、OneNote MCP；其余 44 项两个环境均选中。
- 未下载、归集、打包或上传任何本轮软件安装包；没有实现安装执行器，也没有安装/卸载软件。
- 项目代码的既有验证见上一条 implementation 交接（累计 84 项测试）；本轮是扫描、表格与文档工作，未重新运行全量回归。

## 选中软件（用户填写结果快照）

此表只保存选中的 51 项用于恢复，不记录未选中的完整个人软件清单。版本以 Excel 为观察值，尚未要求锁定安装版本。

| 软件 / 扩展 | 观察版本 | 公司笔记本 | 内网 | 渠道与资源 ID | 来源 |
| --- | --- | --- | --- | --- | --- |
| 飞书 | 7.76.21 | 是 | 否 | winget:ByteDance.Feishu | winget |
| AndeSight_STD_v531 | 5.3.1.0 | 是 | 是 | winget:unmanaged-07780ab7df1420e1ccda27d2 | unknown |
| Arm GNU Toolchain 12.2.mpacbti-rel1 arm-none-eabi (remove only) | 版本未知 | 是 | 是 | winget:Arm.GnuArmEmbeddedToolchain | winget |
| AutoHotkey | 2.0.26 | 是 | 是 | winget:AutoHotkey.AutoHotkey | winget |
| CC Switch | 3.16.1 | 是 | 是 | winget:farion1231.CC-Switch | winget |
| draw.io 30.0.0 | 30.0.0 | 是 | 是 | winget:JGraph.Draw | winget |
| Everything 1.4.1.1032 (x64) | 1.4.1.1032 | 是 | 是 | winget:voidtools.Everything | winget |
| ezwinports: make | 4.4.1 | 是 | 是 | winget:ezwinports.make | winget |
| Flow Launcher | 2.1.3 | 是 | 是 | winget:Flow-Launcher.Flow-Launcher | winget |
| Git | 2.54.0 | 是 | 是 | winget:Git.Git | winget |
| GlobalProtect | 6.2.8 | 是 | 否 | winget:unmanaged-d3a4002c986e3f1ecc3ee1ee | unknown |
| Google Chrome | 153.0.8010.48 | 是 | 是 | winget:unmanaged-c4354279f61113874e858779 | unknown |
| KingstVIS | 3.6.5 | 是 | 是 | winget:unmanaged-7318fc34078f8aac8d5eefec | unknown |
| Microsoft Visual Studio Code (User) | 1.137.0 | 是 | 是 | winget:Microsoft.VisualStudioCode | winget |
| MobaXterm | 26.0.0.5436 | 是 | 是 | winget:Mobatek.MobaXterm | winget |
| MPS Power Manager | 2.0.35.235 | 是 | 是 | winget:unmanaged-50aaf5fe1a92627c97027a9e | unknown |
| Node.js | 24.15.0 | 是 | 否 | winget:OpenJS.NodeJS.LTS | winget |
| Omnissa Horizon Client | 8.18.0.51429 | 是 | 否 | winget:Omnissa.HorizonClient | winget |
| PixPin 版本 3.5.5.1 | 3.5.5.1 | 是 | 是 | winget:unmanaged-b82832f1f0ad83804bc6ad52 | unknown |
| RealVNC Connect 8.4.2 | 8.4.2.19 | 是 | 否 | winget:unmanaged-355c7b53b2e01c08743ad690 | unknown |
| Weixin | 1.0.0.0 | 是 | 否 | winget:unmanaged-eecebf38532425e709953c92 | unknown |
| Windows 终端 | 1.24.11911.0 | 是 | 是 | winget:Microsoft.WindowsTerminal | winget |
| WPS Office (12.1.0.28505) | 12.1.0.28505 | 是 | 是 | winget:unmanaged-062f3d14b044ab997c0602b1 | unknown |
| X-Mouse Button Control 2.20.5 | 2.20.5 | 是 | 是 | winget:Highresolution.X-MouseButtonControl | winget |
| @atomiclabs97/onenote-mcp | 0.1.1 | 是 | 否 | npm:@atomiclabs97/onenote-mcp | unknown |
| Ruff | 2026.80.0 | 是 | 是 | vscode:charliermarsh.ruff | editor |
| GitLens | 19.1.0 | 是 | 是 | vscode:eamodio.gitlens | editor |
| EditorConfig | 0.18.2 | 是 | 是 | vscode:editorconfig.editorconfig | editor |
| clangd | 0.6.0 | 是 | 是 | vscode:llvm-vs-code-extensions.vscode-clangd | editor |
| Cortex-Debug | 1.12.1 | 是 | 是 | vscode:marus25.cortex-debug | editor |
| Debug Tracker | 0.0.15 | 是 | 是 | vscode:mcu-debug.debug-tracker-vscode | editor |
| Memory View | 0.0.29 | 是 | 是 | vscode:mcu-debug.memory-view | editor |
| Peripheral Viewer | 1.6.4 | 是 | 是 | vscode:mcu-debug.peripheral-viewer | editor |
| RTOS Views | 0.0.16 | 是 | 是 | vscode:mcu-debug.rtos-views | editor |
| Git Graph | 1.30.0 | 是 | 是 | vscode:mhutchie.git-graph | editor |
| 中文语言包 | 1.131.2026090407 | 是 | 是 | vscode:ms-ceintl.vscode-language-pack-zh-hans | editor |
| Python Debugger | 2026.6.0 | 是 | 是 | vscode:ms-python.debugpy | editor |
| Python | 2026.4.0 | 是 | 是 | vscode:ms-python.python | editor |
| Pylance | 2026.3.1 | 是 | 是 | vscode:ms-python.vscode-pylance | editor |
| Python Environments | 1.36.0 | 是 | 是 | vscode:ms-python.vscode-python-envs | editor |
| Remote SSH | 0.128.0 | 是 | 是 | vscode:ms-vscode-remote.remote-ssh | editor |
| Remote SSH 配置编辑 | 0.87.0 | 是 | 是 | vscode:ms-vscode-remote.remote-ssh-edit | editor |
| CMake Tools | 1.24.42 | 是 | 是 | vscode:ms-vscode.cmake-tools | editor |
| C++ DevTools | 0.6.18 | 是 | 是 | vscode:ms-vscode.cpp-devtools | editor |
| C/C++ | 1.34.4 | 是 | 是 | vscode:ms-vscode.cpptools | editor |
| Hex Editor | 1.11.1 | 是 | 是 | vscode:ms-vscode.hexeditor | editor |
| Makefile Tools | 0.12.17 | 是 | 是 | vscode:ms-vscode.makefile-tools | editor |
| Remote Explorer | 0.5.0 | 是 | 是 | vscode:ms-vscode.remote-explorer | editor |
| CMake | 0.0.17 | 是 | 是 | vscode:twxs.cmake | editor |
| Error Lens | 3.28.0 | 是 | 是 | vscode:usernamehw.errorlens | editor |
| Markdown All in One | 3.6.3 | 是 | 是 | vscode:yzhang.markdown-all-in-one | editor |

## 具体下一步

1. 读取当前概况，核对工作区和用户是否已回复安装包目的地；未回复则询问具体位置，不猜测 Git 仓库或网盘。
2. 按本表准备实际安装包：公司 51 项、内网 44 项，共用包可复用；个人游戏平台另组。保留用户选择，不重新用自动分类覆盖。
3. 先检查用户指定目录或常见下载目录是否已有可用安装包，再按需核实官方来源。专用/公司工具如 AndeSight、GlobalProtect、MPS Power Manager 等可能需要用户提供安装介质或访问方式。不能把已安装目录当成完整安装包。
4. 内网需准备 VSIX 和必要依赖；VS Code 的 Python/CMake/clangd 扩展不能替代解释器、CMake、编译器及语言服务本体。当前扫描不覆盖所有本体，下载前核对目标系统/架构及额外依赖。不要擅自扩展为安装未选中软件。
5. 为收集的文件记录实际版本、来源、SHA-256、适用环境及缺失项；区分完整离线包和联网引导安装器。按目的地传输后验证结果，不把“已安装”或“有下载链接”当成安装包已准备完成。

## 文件与工作区

- 项目：agentctl/、configs/{common,company,intranet,personal}.yaml，进度入口 progress/progress.md。
- 用户填写的 Excel（唯一现有人工选择文件）：C:/Users/49393/.codex/visualizations/2026/09/20/01a0bd75-e323-7861-a7bf-29d55160ebeb/outputs/software-selection/工作环境软件初选.xlsx
- 同目录的“本地软件上传选择清单.xlsx”是旧版全待定表，不能拿它覆盖用户选择。
- 本线程产物目录中的 scan.json、names.json、build.mjs、classify.mjs、预览图片等保留为可追溯中间产物；不要重新运行 classify.mjs，它会覆盖用户填写的初选文件。
- 工作开始时 Git 干净，分支 master，上游 origin/master，无待推送提交。仅交接文档和索引进入本轮提交；Excel 与中间产物在仓库外。
- packages/ 当前未列出本轮安装包；dist/ 已有 agent-workspace-v0.1.0-offline.zip、intranet-sim/、link-sandbox/，它们是既有产物，未验证包含目标软件，不得当作本轮安装包。
- 没有已知需继续等待的后台下载或上传任务。本次提交/推送结果由最终回复报告，不在交接中提前宣称成功。

## 建议技能

- spreadsheets：继续读取/修改用户 Excel；修改时保留用户选择。
- agent-reach：需要网上核实或下载安装来源时按规则使用。
- project-structure、git-delivery：涉及项目内新增工具或持久记录时使用。
- handoff 只在用户手动调用时使用；firmware-mentor 仍须当前消息显式调用，背景和主题不构成授权。
