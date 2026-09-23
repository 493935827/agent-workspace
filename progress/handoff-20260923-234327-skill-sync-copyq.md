# Skill 同步扩充与 CopyQ 软件补充交接

日期：2026-09-23 23:43（Asia/Shanghai）
对话标识：`01a0cd9d-877c-73b1-ad7e-f593dfce8574`

## 当前目标与范围

- 项目长期目标是维护可跨个人电脑、公司笔记本和内网机器重建的 Agent/Skill 与开发软件环境。
- 本次先核对项目同步目标与本机实际软件、Skill 的差异；随后按用户要求把本机两处个人 Skill 纳入项目，并把 CopyQ 作为公司与内网共用软件加入安装介质。
- 软件安装执行仍未自动化；`packages/installer-transfer/` 是待人工传输的安装介质目录，不进入 Git 或 agentctl Workspace Bundle。

## 本次完成并验证

### Skill 同步

- 从 `~/.agents/skills` 的 27 项和 `~/.codex/skills` 的 11 个条目中去重 `handoff`，新增 37 个唯一 Skill；项目现有 45 个 Skill 源目录。
- `~/.codex/skills/handoff` 没有 `SKILL.md`，采用完整的 `~/.agents/skills/handoff`。现有项目版 `code-review` 保持不变。
- 37 个新目录逐文件与来源做过 SHA-256 对比；所有 `SKILL.md` 的 frontmatter 名称与目录一致。`firmware-mentor` 保持 `disable-model-invocation: true`，项目根规则也继续要求当前消息显式调用。
- `pack-to-dts` 与 `serial-debug` 的来源本身是独立 Git 仓库；复制件中的内部 `.git` 已移出，使主仓库提交真实文件而不是 gitlink。内部元数据备份留在忽略目录 `work/skill-sync-git-metadata/`。
- `configs/common.yaml` 现有 40 个公共 Skill；合并环境层后 personal 42、company 42、intranet 41，所有配置引用都有源目录。当前 personal 的 `dist/link-sandbox` 为 42/42 健康，没有覆盖真实 `~/.agents/skills` 或 `~/.codex/skills`。
- 验证：项目正式测试 `84 passed`；PySide6 Fluent 静态校验通过，无依赖测试 `7 passed`；serial-debug 无依赖测试 `2 passed`；agentctl doctor 全部通过；离线 Workspace Bundle 含 45 个 Skill、291 个文件。
- 无范围限制的根目录 `pytest` 会额外收集新 Skill 自带测试和旧 `work/` 中第三方测试，因未安装 PySide6、pyserial、第三方 debugpy 测试依赖而在收集阶段报错。这不是项目 `tests/` 的回归失败，本次未擅自增加这些依赖。
- Skill 扩充提交：`ff0fc90e2e9b357934bddf811d05cca46f9c1151`，已推送 `origin/master`。

### CopyQ 与软件交付包

- 用户要求把 CopyQ 这类常用软件加入；为避免覆盖此前人工选择，没有把其余本机软件批量纳入，只直接加入明确点名的 CopyQ。
- CopyQ 16.0.0 已作为 `company;intranet` 共用项加入。官方安装器位于 `packages/installer-transfer/shared/apps/CopyQ_16.0.0_User_X64_inno_en-US.exe`，Winget YAML 同目录保存。
- 安装器大小 19,241,128 字节，SHA-256 为 `F271A1467589CA55CD56D1FAF727A4BC34E686B4965AC742854A93BE4B186F82`；上游文件未签名，但实测哈希与 Winget `hluk.CopyQ` 16.0.0 清单一致，属于完整离线安装器。
- 已更新 `README.md`、`metadata/{selection-status.csv,source-groups.csv,executable-signatures.csv,files.json,SHA256SUMS.txt}`。交付目录现有 1,865 个文件、3,436,929,388 字节；独立复核 1,863 条 SHA-256 全部通过。
- 软件选择现为公司 52 项、51 项介质就绪；内网 45 项、44 项介质就绪。两边唯一缺项仍是 AndeSight 5.3.1。
- 原 Excel 被其他程序锁定，未原地覆盖；新版保存在 `C:/Users/49393/.codex/visualizations/2026/09/20/01a0bd75-e323-7861-a7bf-29d55160ebeb/outputs/software-selection/工作环境软件初选-含CopyQ.xlsx`。新版新增第 219 行 CopyQ，统计更新为公司 52、内网 45，保存后重新导入、错误扫描和视觉检查通过。
- 本机另外发现 Listary 6.3、Quicker 1.44.55.0 两个可能的常用工具；它们与 Everything/Flow Launcher 或公司策略存在重叠，尚未加入，需用户确认。
- CopyQ 进度提交：`cfd4f40477e6982b0b371e8bef52a6e5f7adbd8c`，已推送 `origin/master`。

## 关键决策与边界

- Git 只同步项目源码、配置和 Skill；`packages/`、`dist/`、`work/` 与可视化输出均按既有忽略/外部路径保留，不通过代码远程传软件安装包或敏感 OneNote 数据。
- 未把“本机已安装”当成安装介质，也未把未签名直接当成不可信；CopyQ 通过官方 URL和 Winget InstallerSha256 交叉验证。
- `agent-reach` 的 Exa 命令因本机没有 `mcporter` 不可用；CopyQ 核实改用本机 Winget 官方源与 CopyQ 官方 GitHub Release，没有阻塞下载。
- 个人效率工具是否进入公司或内网必须逐项确认，不能根据“常用”自动扩展到所有本机软件。

## 未完成、阻塞与下一步

1. 询问用户是否加入 Listary、Quicker，或先生成“必备 / 推荐 / 个人专用”候选清单；未经确认不要下载或加入。
2. 从公司软件库、Andes 授权门户或原始介质取得 AndeSight 5.3.1；本机已安装目录不能代替安装包。
3. 用户仍需提供软件交付目的地（共享目录、网盘、文件服务器或目标文件夹）。Git origin 不是安装包目的地。
4. 传输后在目标端按 `packages/installer-transfer/metadata/SHA256SUMS.txt` 复核，并区分完整离线安装器与联网引导器。
5. 如需在目标机启用新增 Skill，公网环境执行 `agentctl update`；内网重新导出并导入 Workspace Bundle，然后运行 `agentctl doctor`。

## 相关文件与状态

- 当前总览：`progress/progress.md`
- Skill 公共配置：`configs/common.yaml`
- Skill 源目录：`skills/`
- 软件交付说明：`packages/installer-transfer/README.md`
- 软件选择元数据：`packages/installer-transfer/metadata/selection-status.csv`
- 软件哈希：`packages/installer-transfer/metadata/SHA256SUMS.txt`
- Skill 验证包：`dist/skill-sync-validation.zip`（忽略文件，manifest 对应 `ff0fc90`）
- 本次 handoff 前 Git 状态：`master` 与 `origin/master` 同步，工作区干净；CopyQ 安装介质和 Excel 位于 Git 外。

## 建议技能

- `agent-reach`：继续核实、下载软件时使用；若 Exa 后端仍不可用，按技能回退链使用官方源。
- `spreadsheets`：继续更新或合并人工软件选择 Excel 时使用，保留既有格式、筛选和数据验证。
- `git-delivery`：完成项目记录、配置或 Skill 修改后的验证、提交与推送。
- `handoff` 和 `firmware-mentor` 都保持手动调用；此处仅作建议，不构成后续调用授权。
