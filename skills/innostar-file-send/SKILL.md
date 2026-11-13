---
name: innostar-file-send
description: Automate the innostar-ic 文件收发 system at https://172.16.15.88 with agent-browser — log in with env-var credentials, submit 发送文件申请 (目标保护区默认开发网), download files from 我收到的 (never click 删除), and pack arbitrary resources to 7z offline archives (pack-to-dts merged — pip/npm/URL/本地目录/VSIX) then upload them to 开发网. Use when the user asks to send/transfer files via the innostar-ic system, log into 172.16.15.88, download from 我收到的, or says 打包到DTS/下到DTS/放到DTS/离线包/离线安装/打包传上去.
---

# Innostar 文件收发 + 打包上传自动化（agent-browser）

用 agent-browser 驱动本机系统 Chrome，在 innostar-ic 内网文件系统完成三件事：

1. **发送**：登录 +「发送文件申请」提交（目标保护区默认「开发网」，用户点名其他保护区才改）
2. **接收**：从「我收到的」列表下载文件/文件夹（服务端打 zip），**绝不触碰删除按钮**
3. **打包上传管线**（pack-to-dts 已于 2026-11-12 合并入本 skill）：任意资源 → 7z 离线包 → 直接传上开发网

实测记录：发送 TICKET 14045/14048（2026-11）；下载两条落盘路径 2026-11-12 走通。

## 前提

- `agent-browser` 全局可用（`npm i -g agent-browser`，官方源超时可加 `--registry=https://registry.npmmirror.com`）；本机装有系统版 Chrome（agent-browser 自动发现，无需 `agent-browser install`）
- 用户级环境变量已配好凭据（凭据永不进命令行/脚本/历史）：

  ```powershell
  [Environment]::SetEnvironmentVariable('INNOSTAR_IC_USER','<账号>','User')
  [Environment]::SetEnvironmentVariable('INNOSTAR_IC_PASS','<密码>','User')
  ```

- 打包脚本需 Python 3 与 7-Zip（`C:\Program Files\7-Zip\7z.exe`）

## 发送流程（摘要）

1. **启动 + 登录**（脚本先 `close` 再带证书放行参数启动，登录页在主文档，用 CSS 选择器）：

   ```powershell
   & "$PSHOME\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File <skill目录>/scripts/login.ps1
   ```

   脚本为 UTF-8 BOM，Windows PowerShell 5.1 与 pwsh 7 均可执行（含中文字符串，勿转存为无 BOM）。登录后通常直接落在 `#/zxfile`；若不在再执行下一步跳转。

2. **进入文件页**：`agent-browser open https://172.16.15.88/#/zxfile`，然后 `agent-browser snapshot -i` 确认 iframe 里出现「文件收发」
3. **打开弹窗**：snapshot 找到 button「发送文件申请」的 ref 并 `agent-browser click @ref`
4. **选下拉**（Ant Design Select，直接 click 会被自身值文本遮挡 → 走键盘）：
   - 目标保护区：`agent-browser focus @ref` → `agent-browser press ArrowDown` 展开 → snapshot 读 listbox 选项 ref → `press ArrowDown` 移到「开发网」→ `press Enter`
   - 审批流程自动联动（开发网 → 终端区-开发网）；接收用户默认当前账号；文件来源默认本地文件
5. **注入文件**（`upload` 命令对 iframe 内的 input 无效，必须用脚本）：

   ```powershell
   & "$PSHOME\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File <skill目录>/scripts/inject-upload.ps1 -File <本地文件路径>
   ```

   snapshot/截图确认文件出现在弹窗列表、「上传提交」按钮变亮。**文件 base64 后超出 ~30K 字符（argv 上限）会报 `filename or extension is too long`** → 改走本地 CORS 服务 + 页面 fetch 注入：`python <skill目录>/scripts/serve-cors.py <文件所在目录> 18731` 后台起服务，再按 [flow.md 排错表](references/flow.md) 的 eval 手法注入。
6. **描述 + 提交**：`agent-browser fill @描述框ref '<描述>'` → `agent-browser click @上传提交ref` → 等待绿色提示 `TICKET <id> 提交成功`，弹窗关闭回到「我发送的」列表

## 接收下载流程（摘要，实测 2026-11-12）

- 操作图标是**行悬停时 React 注入**的 `<i class="op-icon">`，snapshot 拿不到 ref、CSS 不穿 iframe → 唯一路径是主文档 eval 钻 iframe JS 点击
- **只匹配 `title === '下载'`（fa-arrow-to-bottom），永不匹配/点击 `title === '删除'`（fa-trash-alt）**
- 文件行：GET `/zxfile/lib/<repo>/file/<名>?dl=1` → 302 → `/zxfile/fs/files/<uuid>/<名>`，**原文件名**落盘
- 文件夹行：POST `zip-task/` → 轮询 `query-zip-progress` → GET `/zxfile/fs/zip/<uuid>`，落盘名是**时间戳 `yyyyMMddHHmmss.zip`**（不是文件夹名），zip 内带 `<文件夹名>/` 前缀
- 落盘目录：Chrome 默认 `C:\Users\<user>\Downloads`

逐条命令与 eval 模板见 [flow.md §8](references/flow.md)。

## 通用打包（pack-to-dts 合并，脚本在 scripts/pack/）

场景判断：pip 包 → `pack-pip.py`；npm 包 → `pack-npm.py`；URL/GitHub Release/安装包 → `pack-url.py`；本地路径/git clone → `pack-local.py`；VS Code 扩展 → `pack-vsix.py`。不确定时先问用户。

```powershell
python <skill目录>/scripts/pack/pack-pip.py  --packages "pandas"        --output-dir <目标目录>
python <skill目录>/scripts/pack/pack-npm.py  --packages "react"        --output-dir <目标目录>
python <skill目录>/scripts/pack/pack-url.py  --urls "https://..."      --output-dir <目标目录>
python <skill目录>/scripts/pack/pack-local.py --paths "D:\config"      --output-dir <目标目录>
python <skill目录>/scripts/pack/pack-vsix.py --extensions "ms-python.python" --output-dir <目标目录>
```

统一约定：7z 根目录包一层 `<包名>/`，内含下载物 + `使用说明.txt`；**Python 包默认目标 3.10 + win_amd64**（`--python-version` 可覆盖）；VSIX 输入 `publisher.extension`，多个用 `|` 分隔。

## 打包 → 上传管线（默认开发网）

用户说「打包传上去 / 打包到开发网 / 下到 DTS」时：`pack-*.py` 出包 → 走上面发送流程，**目标保护区默认「开发网」**、接收用户默认当前账号；仅当用户明确点名其他保护区（如安全桌面、其他接收人）才改下拉选择。

## 硬性坑位（实测结论）

- **iframe 边界**：`eval` 和 CSS 选择器只作用于主文档；只有 `@ref` 穿透 iframe。操作 iframe 内元素一律先 `snapshot -i` 拿 ref。
- **Ant Select 点击遮挡**：combobox 值文本和下拉选项的内层元素都会盖住点击点，click 被拒；一律 `focus` + 方向键 + `Enter`。
- **文件注入**：借主文档 eval 钻进同源 iframe，用 `iframe.contentWindow` 的 realm 构造 `File`/`DataTransfer` 再赋值（脚本已封装）；change 派发后应用会立刻清空 input（设计如此），以列表 UI 为准判断成败。
- **eval 的 JS 不写双引号**：经 PowerShell→exe 传参会（间歇性）被剥掉，属性匹配一律 `.find(el => el.title === '...')`。
- **同名去重**：弹窗按文件名去重，重复注入同名文件报「已存在，请勿重复上传」；换文件名或先删列表行（行尾垃圾桶图标）。
- **证书**：站点自签证书；`--ignore-https-errors` 只在浏览器启动时生效，切换参数前先 `agent-browser close`。
- **守护进程**：headless 默认 1 小时空闲自动退出，过期后任何命令都会失败，重跑 login.ps1 即可；需人工介入时加 `--headed`。

逐条命令、实测 ref 示例与排错表见 [references/flow.md](references/flow.md)。
