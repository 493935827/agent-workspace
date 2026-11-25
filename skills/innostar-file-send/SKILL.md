---
name: innostar-file-send
description: Automate the innostar-ic 文件收发 system at https://172.16.15.88 with agent-browser — log in with env-var credentials, submit 发送文件申请 (目标保护区默认开发网), download files from 我收到的 (never click 删除), and pack arbitrary resources to 7z offline archives (pack-to-dts merged — pip/npm/URL/本地目录/VSIX) then upload them to 开发网. Use when the user asks to send/transfer files via the innostar-ic system, log into 172.16.15.88, download from 我收到的, or says 打包到DTS/下到DTS/放到DTS/离线包/离线安装/打包传上去, or says 发布aws to export the agent-workspace offline package and distribute it to both 安全桌面 and 开发网.
---

# Innostar 文件收发 + 打包上传自动化（agent-browser）

用 agent-browser 驱动本机系统 Chrome，在 innostar-ic 内网文件系统完成三件事：

1. **发送**：登录 +「发送文件申请」提交（**默认双区：安全桌面 + 开发网各一 TICKET**，2026-11-24 用户规则；仅当用户明确点名单区/其他接收人才减改）
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

**首选 = 一键脚本 `scripts/send-file.ps1`（2026-11-25 实测：小文件双区 15.4s；64MB 级约 40s，瓶颈是内网上传 3–5MB/s）**：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <skill目录>\scripts\send-file.ps1 -File "D:\path\to\file.exe" [-Description "描述"] [-Zones 安全桌面,开发网]
```

- 默认双区各一 TICKET；自动登录恢复、自动起/停 CORS 服务、XHR 补丁捕获 ticket/submit 响应拿工单号（全程免刷新）
- 脚本报出的工单号**要和「我发送的」列表核对一次**（双区两单应为相邻号；响应里其它 id 字段曾致误抓，实测脚本报 14213 而列表真号 14385/14386）
- **agent 调用姿势（重要）**：分离启动 + 日志轮询（`Start-Process -RedirectStandardOutput out.log ... -PassThru` 后轮询日志出现 `TOTAL`），**不要在工具会话里管道捕获嵌套 powershell 的输出**——孙进程（agent-browser/node）继承 stdout 句柄不释放，`| Out-String` 会永久挂死（实测两次 240s 超时无输出）；`-ArgumentList` 里带空格的参数必须显式加引号，否则碎片会串位绑进 `-Zones`
- **改脚本前必读**：PS5.1 下 `$ErrorActionPreference='Stop'` 会被 agent-browser 的 stderr 噪声（`[agent-browser] launched browser` 等）炸掉或挂住 → 保持 EAP=Continue + 显式校验；agent-browser eval 对返回值再 JSON 编码一层（引号变 `\"`）→ 断言一律用无引号纯字符串协议（`ses=true` / `armed=true` / `modal=false up=false` / `id:14361`）

**手动 eval 路径**（调试/脚本失效时用）= 全程主文档 eval 钻同源 iframe（2026-11-24 实测 TICKET 14336，完整模板见 [flow.md §9](references/flow.md)）。不要整页 `snapshot -i`——它会 dump 整个列表表格（几十 KB），是流程最大耗时源；refs/键盘路径仅作 fallback。

1. **启动 + 登录**（幂等；会话丢失也用它恢复。脚本先 `close` 再带证书放行参数启动，登录页在主文档，用 CSS 选择器）：

   ```powershell
   & "$PSHOME\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File <skill目录>/scripts/login.ps1
   ```

   脚本为 UTF-8 BOM，Windows PowerShell 5.1 与 pwsh 7 均可执行（含中文字符串，勿转存为无 BOM）。登录后通常直接落在 `#/zxfile`；若不在再执行下一步跳转。

2. **打开弹窗**：eval 按 innerText 找「发送文件申请」按钮 native click（React 有效），700ms 后回读 `.ant-modal` 存在性。**进入文件页**若需要：`agent-browser open https://172.16.15.88/#/zxfile`
3. **目标保护区 → 开发网**：eval 派发 `mousedown/mouseup/click` 展开 Ant Select → 点 `title==='开发网'` 的 option → 回读三个 select 值确认；期望 `["目标保护区=开发网","审批流程=终端区-开发网","文件来源=本地文件"]`。接收用户默认当前账号
4. **注入文件**：≤1MB 可用 inject-upload.ps1（base64 argv 上限 ~30K 字符）；更大**直接** serve-cors.py + 页面 fetch 注入（67MB 实测约 3 秒，不要先试直注入浪费时间）。**注入目标是页面级 `input.upload-input`，不在 `.ant-modal` 内**；回读 `submitDisabled:false` 即按钮已亮
5. **描述 + 提交**：React 受控 textarea 用原生 setter + input 事件填描述 → eval 点「上传提交」→ **每 6s 轮询「弹窗关闭 + 无『上传中』字样」直至完成（绝不马上 reload——提前刷新会掐断在途 upload-file-aj 分块，工单永不入列）** → 完成后 reload 一次读「我发送的」顶部行拿申请号

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

## 打包 → 上传管线（默认双区）

用户说「打包传上去 / 打包到开发网 / 下到 DTS」时：`pack-*.py` 出包 → 走上面发送流程，**默认双区：安全桌面 + 开发网各一 TICKET，都要报给用户**（2026-11-24 用户规则，与发布aws一致）；接收用户默认当前账号；仅当用户明确点名单区或其他接收人才减改。安全桌面区工单入列滞后 5–7 分钟，别因列表暂无新行而重发。

## 发布 agent-workspace（触发词「发布aws」）

用户说「发布aws / 发布 agent-workspace 版本」时，**先 export、再分发**，顺序固定。**agent-workspace 离线包默认双区（安全桌面 + 开发网）各一 TICKET——用户说「传一份 / 传到 dts」也不减区，仅当明确点名只发某区才单区**（2026-11-18 用户规则）：

1. **先 export 出包**：`agentctl export`（可选 `--with-wheels`/`--with-npm`）重打 agent-workspace 离线包，默认产物 `dist/agent-workspace-v<版本>-offline.zip`（自动排除 .env/local.yaml 机密、生成清单与 SHA-256 校验）。先看 dist/ 实际产物名与时间戳，必要时 `--dry-run` 预演。
2. **再双区分发**：对导出的 zip 连走两遍「发送流程」，**两个区各一个 TICKET，都要报给用户**：
   - 目标保护区=**安全桌面**：下拉默认项，`focus` → `ArrowDown` 展开 → 直接 `Enter`
   - 目标保护区=**开发网**：展开后 `ArrowDown` 一次再 `Enter`
   - 描述注明「agent-workspace 离线包 <版本/commit>」
   - 包体 7 MB 级超出 inject-upload 命令行上限（~30K 字符）→ 直接走 serve-cors.py + 页面 fetch 注入分支（见发送流程第 5 步），不要先试直注入浪费时间

## 硬性坑位（实测结论）

- **iframe 边界**：`eval` 和 CSS 选择器只作用于主文档；只有 `@ref` 穿透 iframe。操作 iframe 内元素一律先 `snapshot -i` 拿 ref。
- **Ant Select 点击遮挡**：combobox 值文本和下拉选项的内层元素都会盖住点击点，click 被拒；一律 `focus` + 方向键 + `Enter`。
- **文件注入**：借主文档 eval 钻进同源 iframe，用 `iframe.contentWindow` 的 realm 构造 `File`/`DataTransfer` 再赋值（脚本已封装）；change 派发后应用会立刻清空 input（设计如此），以列表 UI 为准判断成败。
- **eval 的 JS 不写双引号**：经 PowerShell→exe 传参会（间歇性）被剥掉，属性匹配一律 `.find(el => el.title === '...')`。
- **同名去重**：弹窗按文件名去重，重复注入同名文件报「已存在，请勿重复上传」；换文件名或先删列表行（行尾垃圾桶图标）。
- **证书**：站点自签证书；`--ignore-https-errors` 只在浏览器启动时生效，切换参数前先 `agent-browser close`。
- **守护进程**：headless 默认 1 小时空闲自动退出，过期后任何命令都会失败，重跑 login.ps1 即可；需人工介入时加 `--headed`。

逐条命令、实测 ref 示例与排错表见 [references/flow.md](references/flow.md)。
