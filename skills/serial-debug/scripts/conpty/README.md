# conpty/

共享终端桥（`proc://`）的 ConPTY 真终端后端二进制：

- `conpty.dll` — Windows Terminal 项目的 ConPTY 承载库（MIT 许可）。
- `OpenConsole.exe` — 配套控制台宿主，`conpty.dll` 会从同目录拉起它。

两个文件镜像自 pywinpty 官方 wheel（`pywinpty`，MIT）。为什么捆绑而不直接用系统
`kernel32.CreatePseudoConsole`：部分 Windows 11 24H2 环境下 in-box conhost 的 ConPTY
传输对非控制台调用方表现不稳定（conhost 与子进程都能拉起，但管道数据不通）；捆绑
OpenConsole 版本经过验证且与 Windows Terminal 同源，行为可预期。

`process_terminal.py` 的选择顺序：捆绑 `conpty.dll`（`conpty-local` 后端）→
系统 `kernel32.CreatePseudoConsole`（`kernel32` 后端）→ `--proc-conpty off` /
auto 回退管道模式。桥启动时会打印实际使用的后端。

x64 Windows 专用；其他架构下自动跳过捆绑后端（kernel32 可用则用，否则管道模式）。
