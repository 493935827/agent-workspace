---
name: pack-to-dts
description: 下载任意类型的文件/包并打包为 7z 离线压缩包。当用户提到下载、打包、离线安装、内网部署，或提及 "打包到DTS"、"下到DTS"、"放到DTS"、"离线包"、"离线安装" 等短语时触发。覆盖 Python pip 包、npm 包、任意 URL 文件、GitHub Release、本地目录归档、固件/工具链/安装包等场景。只要涉及 "获取某个资源 → 打包成压缩包 → 放到指定位置" 这个模式，就使用本 skill。
---

# pack-to-dts — 已合并进 innostar-file-send（2026-11-12）

本 skill 的场景判断树、五个打包脚本与统一约定已合并进 `~/.dsh/skills/innostar-file-send`（统一 skill：innostar 文件收发**发送** + 「我收到的」**下载** + 通用 7z **打包上传管线**，上传目标保护区默认「开发网」）。

- **触发短语不变**：「打包到DTS / 下到DTS / 放到DTS / 离线包 / 离线安装」等命中后，按 innostar-file-send 的 SKILL.md「通用打包」+「打包 → 上传管线」两节执行；脚本在 `~/.dsh/skills/innostar-file-send/scripts/pack/`（pip/npm/url/local/vsix 五件套 + common.py），场景判断树也收录在该节。
- 本目录 `scripts/` 保留一份镜像便于独立使用（`--output-dir` 仍由用户指定目标位置，如 `D:\trash\Work\Innostar-ic\DTS`）；**唯一事实源以 innostar-file-send 为准**，改动后需重拷镜像并 `fc /b` 逐字节校验。
- 「DTS」目录用法不变：仅打包落盘；要顺手上传内网时在 innostar-file-send 的发送流程里继续（目标保护区默认开发网，用户点名其他保护区才改）。
