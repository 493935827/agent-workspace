# 安装介质与 OneNote 归档交接

时间：2026-09-23 17:34（Asia/Shanghai）

## 当前目标与范围

- 按用户已确认的软件选择准备实际安装介质，最终传输到尚未指定的目标位置。
- 公司笔记本和内网环境共用的软件放在 `packages/installer-transfer/shared/`，公司专用软件放在 `company-only/`，个人电脑游戏平台放在 `personal-only/`。
- 不传游戏本体；游戏平台仅用于个人电脑。
- 将 OneNote 笔记作为敏感用户数据单独放在 `user-data/`，不归入任何软件环境，也不提交到 Git。
- 软件选择来源和原始决定见上一份交接：[软件选择与安装包传输](handoff-20260921-105807-installer-transfer.md)。

## 已完成并验证

### 软件安装介质

- 本地交付根目录：`packages/installer-transfer/`。
- 公司笔记本已准备 50/51 个已选项，内网已准备 43/44 个已选项；两个环境唯一缺少的都是 AndeSight 5.3.1。
- 26 个精确版本 VSIX 已下载并在隔离的 VS Code 用户数据/扩展目录中逐个安装验证，全部成功；声明的扩展依赖均包含。
- `@atomiclabs97/onenote-mcp@0.1.1` 主包和 115 个 npm 依赖已缓存，使用独立 prefix 和包内缓存进行的 `npm --offline` 安装验证通过；它要求 Node.js 20 或更高版本，包内含 Node.js LTS 24.19.0。
- 个人电脑游戏平台目录只含 Battle.net、WeGame 和 Xbox 联网引导器。START 云游戏按本机记录由 WeGame 管理；小米游戏盒子按 OEM 恢复渠道处理；没有游戏本体。
- WPS 12.1.0.28505 完整安装包大小为 306,877,256 字节，SHA-256 为 `1C8808F4DC3E4066549D41A5890ED92AFD159D2C475F643C4544196C19C1A994`，与 Winget 清单一致。
- 微信 4.1.15 来自腾讯官方 CDN，腾讯签名有效，但当前文件与当时的旧 Winget 清单哈希不同；文件名和元数据保留 `manifest-mismatch`，不能擅自消除该标记。
- MPS Power Manager 包标为 `confidential`，属于 NDA/保密介质，转存仍需遵循公司访问控制。

### OneNote 笔记归档

- 可直接交付的压缩包：`packages/installer-transfer/user-data/OneNote-notes-20260923.zip`。
- ZIP 大小为 155,167,799 字节，SHA-256 为 `AB96D326063B4968F9C5C77E863FF107DED21E0896F8C9564E9DF6B58FC2063B`，包含 1,363 个 ZIP 条目。
- 展开目录：`packages/installer-transfer/user-data/onenote-notes/`；入口为其中的 `INDEX.md` 和 `README.md`。
- Microsoft Graph 快照包含 7 个笔记本、39 个分区、142 个页面；每页同时保存 HTML 和 Markdown。
- 970 个页面图片/附件资源已下载到对应 `.resources` 目录；HTML 已改写为包内相对路径。
- 最终 `metadata/warnings.json` 为 0 条；142 个 HTML、142 个 Markdown、970 个资源全部被 `metadata/pages.json` 引用；缺失引用为 0，残留的 Graph OneNote 资源链接为 0。
- `native-backups/` 另含本机 OneNote 自动备份中的 68 个原生 `.one` 分区文件，共 88,257,136 字节，覆盖 `ELF 文件分析`、`Emulation`、`Tim_Test`；最新自动备份时间为 2026-09-14 08:33:23。
- 本机 OneNote COM 整包导出返回 `0x80004005`，因此没有 `.onepkg`。采用“当前 Graph 可读快照 + 较早的原生 `.one` 自动备份”双轨方案：前者覆盖全部可读页面，后者用于保留部分 OneNote 专有内容。
- 导出过程中 Graph 曾两次返回 429；最终通过低并发、退避重试和本地断点复用完成，最终结果没有警告。没有修改或删除云端 OneNote 页面。

### 完整性与签名

- 完整交付包当前为 1,863 个文件、3,417,684,272 字节，约 3.183 GiB。
- `packages/installer-transfer/metadata/SHA256SUMS.txt` 和 `files.json` 覆盖除这两个自描述文件之外的 1,861 个内容文件；全部重新计算并二次复核通过。
- 24 个可执行安装介质中 20 个 Authenticode 签名有效。
- AutoHotkey、CC Switch、Flow Launcher 上游文件未签名，但与对应 Winget 清单 SHA-256 一致。
- Windows Terminal 的系统签名检查返回 `UnknownError`，但与 Winget 清单 SHA-256 一致，并包含 Microsoft.UI.Xaml 2.8 离线依赖。
- 选择状态、缺失项、来源、签名和完整哈希分别见：
  - `packages/installer-transfer/metadata/selection-status.csv`
  - `packages/installer-transfer/metadata/missing-items.csv`
  - `packages/installer-transfer/metadata/source-groups.csv`
  - `packages/installer-transfer/metadata/executable-signatures.csv`
  - `packages/installer-transfer/metadata/SHA256SUMS.txt`
  - `packages/installer-transfer/metadata/files.json`

## 未完成、阻塞和下一步

1. 安装包传输目的地仍未提供。代码仓库远程不能视为安装包目的地，不能把约 3.183 GiB 的二进制和敏感笔记推到 GitHub。
2. AndeSight 5.3.1 是唯一软件缺项。本机虽有安装记录，但注册表无 `InstallSource`/`LocalPackage`，系统缓存和下载目录也没有安装介质；下一会话需从公司软件库、Andes 授权门户或原始介质取得，或者由用户明确接受缺项。
3. 用户给出目标位置后，传输整个 `packages/installer-transfer/`。由于 OneNote 内容可能包含个人或公司敏感信息，目标必须是用户明确指定且符合公司政策的移动介质、内网文件服务或受控存储。
4. 若补入 AndeSight 或修改任何交付文件，必须重新生成 `metadata/SHA256SUMS.txt` 和 `files.json`；传输完成后在目标端按 `README.md` 中的 PowerShell 命令复核全部哈希。
5. 除上述两项外没有“已实现但未验证”的工作，也没有后台下载或 BITS 作业在运行。

## 重要决定与未采用方案

- `packages/` 和 `work/` 保持 Git 忽略；Git 仅保存项目进度和交接，不保存安装包或 OneNote 内容。
- OneNote 笔记独立放在 `user-data/`，避免被误认为公司软件或个人游戏平台。
- 未把本机 OneNote 原始缓存目录整体复制进交付包，因为缓存不是稳定的恢复格式且可能携带无关索引；只复制可识别的 `.one` 自动备份。
- 没有把不明来源的小米游戏盒子安装器或 AndeSight 安装器塞入交付包，也没有把 VS Code 扩展依赖的 Python、CMake、clangd 工具本体擅自加入用户选择。
- WPS 最终由精确 Range 分段合并取得，只有在总大小和 Winget SHA-256 均匹配后才纳入交付；旧的 Delivery Optimization/BITS 任务已清理。

## 工作区与临时材料

- 给人的总入口：`packages/installer-transfer/README.md`。
- OneNote 浏览入口：`packages/installer-transfer/user-data/onenote-notes/INDEX.md`。
- OneNote 导出脚本保留在 `work/onenote-export/export-onenote.mjs`；限流探针在同目录的 `probe-throttle.mjs`。两者被 Git 忽略，续跑需要现有 OneNote MCP 登录状态。
- 前几轮限流重跑产生的 200 个未索引旧副本已逐文件移到 `work/onenote-export/orphans/`，不在交付包和 ZIP 中；保留用于追溯，可在确认不再需要后清理。
- WPS 分段和其他下载过程材料位于 `work/installer-transfer/`，被 Git 忽略，不属于最终交付。
- 当前 Git 分支为 `master`，上游为 `origin/master`。本会话前两次已推送提交：
  - `8570869 docs: record prepared installer transfer bundle`
  - `d59cccd docs: record OneNote notes archive`
- handoff 创建前工作区干净，`master` 与 `origin/master` 同步。

## 建议技能

- 用户再次明确调用 `$handoff` 时才更新本交接或创建新的对话归档。
- 若后续需要继续操作 OneNote，使用 `onenote`；它不授权上传笔记到未指定位置。
- 若后续新增、移动或重组交付目录，使用 `project-structure`。
- 修改并验证项目记录后，使用 `git-delivery` 完成提交和已授权远程推送。
- `firmware-mentor` 仍为纯手动调用；只有用户在当前消息明确写出 `$firmware-mentor` 或附上技能链接时才能加载。

## 下一会话建议起点

先读 `AGENTS.md` 和 `progress/progress.md`，核对 `packages/installer-transfer/` 与当前 Git 状态。若用户提供 AndeSight 介质，先验证来源、版本、签名/哈希并补包；若用户提供传输目标，先确认目标容量、权限和敏感数据适用性，再复制整个交付目录并在目标端复核 `metadata/SHA256SUMS.txt`。
