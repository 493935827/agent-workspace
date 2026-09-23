---
name: pack-to-dts
description: 下载任意类型的文件/包并打包为 7z 离线压缩包。当用户提到下载、打包、离线安装、内网部署，或提及 "打包到DTS"、"下到DTS"、"放到DTS"、"离线包"、"离线安装" 等短语时触发。覆盖 Python pip 包、npm 包、任意 URL 文件、GitHub Release、本地目录归档、固件/工具链/安装包等场景。只要涉及 "获取某个资源 → 打包成压缩包 → 放到指定位置" 这个模式，就使用本 skill。
---

# pack-to-dts — 通用下载打包 Skill

## 核心能力

将任意来源的资源（包、文件、目录）下载/归档并打包为 7z 压缩包，附带使用说明。

## 意图识别

当用户说"下/下载/打包/拉取/放到/保存到 XX"时，按以下规则判断场景：

### 场景判断树

```
用户说"下载/打包 XXX 到/到 DTS/到某目录"
│
├─ XXX 是 pip 包名 (pandas, numpy, flask...)
│  → Python 包场景 → pack-pip.py
│
├─ XXX 是 npm 包名 (react, lodash, vue...)
│  → npm 包场景 → pack-npm.py
│
├─ XXX 是 URL / GitHub Release / 文件链接
│  → 文件下载场景 → pack-url.py
│
├─ XXX 是本地路径 (目录或文件)
│  → 本地归档场景 → pack-local.py
│
├─ XXX 是安装包/工具链/固件等 (exe/msi/bin/hex)
│  → 文件下载场景 → pack-url.py (需先找下载链接)
│
├─ XXX 是 VS Code 扩展 (pylance, python, debugpy...)
│  → VS Code 扩展场景 → pack-vsix.py
│
├─ XXX 是 git 仓库地址
│  → git clone → 本地归档场景 → pack-local.py
│
└─ 不确定时 → 询问用户具体要下载什么、从哪里下载
```

### 常见触发短语

| 用户说 | 识别场景 |
|--------|----------|
| "帮我把 pandas 打包到 DTS" | Python 包 |
| "把 flask 和 requests 下到 DTS" | Python 包 |
| "把 react 打包到 DTS" | npm 包 |
| "帮我下这个链接到 DTS" + URL | URL 下载 |
| "把 node v20 的 msi 下载到 DTS" | URL 下载 |
| "把 config 目录压缩到 DTS" | 本地归档 |
| "把 d:\logs 打包" | 本地归档 |
| "把这个 git 仓库拉到 DTS" | git clone + 归档 |
| "下载固件包到 DTS" | URL 下载（需找下载地址） |
| "帮我下 pylance 扩展到 DTS" | VS Code 扩展 |
| "打包 python 扩展" | VS Code 扩展 |

## 统一参数

所有脚本共享以下参数规范：

| 参数 | 说明 |
|------|------|
| `output-dir` | 输出目录（默认 `D:\trash\Work\Innostar-ic\DTS` 或用户指定） |
| `output-name` | 7z 文件名（自动生成） |
| `--help` | 查看帮助 |

## 工作流

### 第1步：理解用户意图

解析用户说的话，判断属于哪个场景：
- 用户说的是包名 → 判断是 pip 还是 npm (常见 npm 包如 react、lodash 等可硬识别，不确定时问用户)
- 用户给的是 URL → 走文件下载
- 用户给的是本地路径 → 走本地归档
- 用户说"打包到DTS"但没具体说 → 追问"你要打包什么？"

### 第2步：选择合适的脚本并执行

```powershell
# Python 包
python scripts/pack-pip.py --packages "pandas" --output-dir "D:\trash\Work\Innostar-ic\DTS"

# npm 包
python scripts/pack-npm.py --packages "react" --output-dir "D:\trash\Work\Innostar-ic\DTS"

# URL 下载
python scripts/pack-url.py --urls "https://example.com/file.zip" --output-dir "D:\trash\Work\Innostar-ic\DTS"

# 本地目录归档
python scripts/pack-local.py --paths "D:\config" --output-dir "D:\trash\Work\Innostar-ic\DTS"

# VS Code 扩展 (多个用 | 分隔)
python scripts/pack-vsix.py --extensions "ms-python.python|ms-python.vscode-pylance" --output-dir "D:\trash\Work\Innostar-ic\DTS"
```

### 第3步：呈现结果

向用户展示：
- 压缩包位置
- 包含的文件列表
- 使用方法

## 各脚本输出格式

每个 7z 包统一包含：
```
<包名>.7z
├── <根文件夹名>/
│   ├── <下载的文件1>
│   ├── <下载的文件2>
│   └── 使用说明.txt
```
解压后拖出根文件夹即可。

## 注意事项

1. 不确定包是 Python 还是 npm 时，优先问用户
2. URL 下载时注意文件可能很大，提前告知用户
3. 本地归档保留原目录结构
4. Git 仓库先 `git clone` 再打包
5. **Python 包默认目标版本 3.10 + win_amd64**，可在 `pack-pip.py` 的 `--python-version` 参数中覆盖
6. **VS Code 扩展**输入扩展 ID，格式 `publisher.extension`（如 `ms-python.python`），多个用 `|` 分隔
