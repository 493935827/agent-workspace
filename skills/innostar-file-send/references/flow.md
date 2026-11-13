# 发送文件申请 — 实测全流程与排错

以下 ref 编号来自 2026-11 实测会话，**每次会话都会变**，执行时必须以当次 `snapshot -i` 的输出为准；命令形态和顺序是稳定的。

## 0. 环境准备（新机器一次性）

```powershell
# agent-browser（官方源慢就加镜像）
npm install -g agent-browser --registry=https://registry.npmmirror.com
agent-browser --version          # 实测 v0.42.0

# 凭据环境变量（用户级，注册表明文存储，防的是命令行/脚本/历史散落）
[Environment]::SetEnvironmentVariable('INNOSTAR_IC_USER','E0465','User')
[Environment]::SetEnvironmentVariable('INNOSTAR_IC_PASS','<密码>','User')
```

浏览器内核不用额外下载：agent-browser 会按固定顺序发现本机 Chrome
（`C:\Program Files\Google\Chrome\Application\chrome.exe` 在列表内），`agent-browser install` 可跳过。

## 1. 启动 + 登录

```powershell
& "$PSHOME\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File <skill>/scripts/login.ps1
```

等价手工命令（登录页在**主文档**，CSS 可用）：

```powershell
agent-browser close                                        # 旧会话必须关（证书参数只在启动时生效）
agent-browser --ignore-https-errors open https://172.16.15.88/#/login
agent-browser type 'input[placeholder="请输入用户名"]' --clear -- $env:INNOSTAR_IC_USER
agent-browser type 'input[placeholder="请输入密码"]' --clear -- $env:INNOSTAR_IC_PASS
agent-browser find role button click --name '登录'
```

实测（ref 形态，登录页主文档）：textbox「请输入用户名」e6、textbox「请输入密码」e4、button「登录」e2。

登录页会先被 Chrome 证书警告页拦住（`NET::ERR_CERT_COMMON_NAME_INVALID`，自签证书 IP 不匹配）——
这是正常的，带 `--ignore-https-errors`（或 `--args "--ignore-certificate-errors"`）启动即可，不要去点「高级→继续」。

## 2. 进入文件页

```powershell
agent-browser open https://172.16.15.88/#/zxfile
agent-browser snapshot -i
```

应用是 SPA + 主文档套一层 iframe（src 带 `isp-token`，会话过期会失效）。确认 iframe 下出现
heading「文件收发」和 button「 发送文件申请」。

## 3. 打开「发送文件申请」弹窗

snapshot 找 button「发送文件申请」的 ref，实测为 e20：

```powershell
agent-browser click '@e20'
agent-browser snapshot -i
```

弹窗内元素（实测 ref）：目标保护区 combobox e245、审批流程 e246、接收用户 e247、
描述 textbox e244（填字后重渲染会漂移成 e251）、隐藏 file input e239（a11y 显示为
button「选择文件: 未选择任何文件」）、上传提交 e243（初始 disabled）。

## 4. 目标保护区 → 开发网

**不要 click combobox**：会被 `span.ant-select-selection-item` 盖住，报
"Element is covered ... input would land on that element instead"。
下拉选项也一样会被 `div.ant-select-item` 盖住。这个 Select 不可搜索（type 打字无效），走键盘：

```powershell
agent-browser focus '@e245'        # combobox ref
agent-browser press ArrowDown      # 展开，snapshot 出现 listbox：option 安全桌面 [selected] / option 开发网
agent-browser press ArrowDown      # 焦点从「安全桌面」移到「开发网」
agent-browser press Enter          # 选中
```

选中后审批流程自动联动为「终端区-开发网」。截图或 snapshot 确认。

## 5. 注入本地文件（关键步骤）

先试过 `agent-browser upload @e239 <file>`：返回 ✓ Done 但 iframe 里的
`input.upload-input`（webkitdirectory，随模式切换）files 始终为空——upload 命令对
iframe 内 input 无效。CSS 选择器（`.upload-input`）也只在主文档找，报 Element not found。

唯一可靠路径 = 同源 eval + iframe realm 注入，已封装成脚本：

```powershell
& "$PSHOME\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File <skill>/scripts/inject-upload.ps1 -File D:\path\to\file.zip
```

成功后弹窗出现文件列表行（文件名 + 大小 + 删除图标），「上传提交」由灰变蓝。
注意：

- change 事件被应用处理后 **input 会被立刻清空**（上传组件惯例），`input.files` 读回空是正常的，以列表 UI 为准；
- 同一弹窗内按文件名去重，重复注入同名文件报 toast「文件名xxx已存在，请勿重复上传」——换名或点行尾垃圾桶删除后再注入；
- iframe 未加载完时 eval 查不到元素，等 1–2 秒重试。

## 6. 描述 + 提交

```powershell
agent-browser fill '@e251' 'agent-browser 自动化流程验证：本地测试文件自发自收（开发网）'
agent-browser snapshot -i          # 确认「上传提交」已 enabled，ref 以当次为准
agent-browser click '@e243'
Start-Sleep 3
agent-browser screenshot after-submit.png
```

成功标志：绿色 toast **「TICKET <id> 提交成功」**，弹窗自动关闭回到「我发送的」列表，
列表顶部新增一行（申请号 = toast 里的 id）。实测 TICKET 14045。

## 7. 收尾

```powershell
agent-browser close    # 杀掉 headless Chrome；守护进程闲置 1h 也会自动退出
```

## 8. 「我收到的」下载（实测 2026-11-12）

操作图标是**行悬停时 React 注入**的：`<div class="operation-group">` 内
`i.op-icon.far.fa-arrow-to-bottom[title=下载]` 与 `i.op-icon.far.fa-trash-alt[title=删除]`。
`<i>` 无 a11y role → snapshot 拿不到 ref；CSS 选择器不穿 iframe → 只能主文档 eval 钻进去 JS 点击。
**只按 `title === '下载'` 匹配，永不匹配/点击 `title === '删除'` 或 `fa-trash-alt`**：

```js
const link = Array.from(d.querySelectorAll('.ant-table-tbody a')).find(a => a.title === '<文件名>');
const icon = Array.from(link.closest('tr').querySelectorAll('i.op-icon')).find(i => i.title === '下载');
icon.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true, view: w }));
```

两条落盘路径（均存到 Chrome 默认下载目录 `C:\Users\<user>\Downloads`）：

- **文件行**：GET `/zxfile/lib/<repo>/file/<名>?dl=1` → 302 → `/zxfile/fs/files/<uuid>/<名>`，原文件名直接落盘。
- **文件夹行**：POST `/zxfile/api/v2.1/repos/<repo>/zip-task/` → 轮询 `query-zip-progress/?token=...` → GET `/zxfile/fs/zip/<uuid>`；落盘名为时间戳 `yyyyMMddHHmmss.zip`（**不是**文件夹名），zip 内带 `<文件夹名>/` 前缀。
- eval 的 JS 里不要写双引号（经 PowerShell→exe 传参会被剥掉），属性匹配一律 `.find(el => el.title === '...')`。

## 排错表

| 症状 | 原因 | 处理 |
| --- | --- | --- |
| 证书警告页 / `net::ERR_CERT_COMMON_NAME_INVALID` | 启动没带证书放行 | `agent-browser close` 后带 `--ignore-https-errors` 重开 |
| 命令报 browser not running / 连接失败 | 守护进程闲置 1h 自动退出 | 重跑 login.ps1 |
| 登录后操作被弹回登录页 | isp-token 会话过期 | 重跑 login.ps1 |
| click 报 "Element is covered" | Ant 组件内层元素盖住点击点 | 换键盘路径（focus/press），或点未被盖的相邻元素 |
| eval 返回 `[]` / CSS 报 not found | 目标在 iframe 里，eval/CSS 只看主文档 | 用 `document.querySelector('iframe').contentDocument` 钻进去，或改用 ref |
| upload 命令 Done 但文件没进列表 | upload 对 iframe 内 input 无效 | 用 scripts/inject-upload.ps1 |
| inject-upload.ps1 报 `The filename or extension is too long` | 脚本把文件 base64 塞进 eval 命令行，Windows argv 上限约 32K 字符——实测 98.4MB 文件必炸（TICKET 14045 的小文件没事） | 大文件走「本地 CORS 服务 + 页面 fetch 注入」：后台起 `python <skill目录>/scripts/serve-cors.py <文件目录> 18731`（http.server + CORS + `Access-Control-Allow-Private-Network: true`，2026-11-12 起脚本随 skill 分发；当时用的 `_serve_packages.py` 是临时件未留存），再主文档 eval：(async)→`fetch('http://127.0.0.1:18731/<file>')`→`new w.File([new w.Uint8Array(buf)], name)`→DataTransfer→`el.files=dt.files`→派发 input/change。eval 脚本本身 ~1.4KB，字节走浏览器网络栈不进命令行；inject 后快照核对列表行文件名+大小 |
| toast「文件名xxx已存在」 | 弹窗内按文件名去重 | 换文件名，或删列表行后重注入 |
| 「上传提交」一直灰 | 文件未进列表或有必填项没填 | snapshot 检查弹窗各字段 |
