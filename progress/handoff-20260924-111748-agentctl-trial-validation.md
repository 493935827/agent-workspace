# agentctl 实测验证与拉取更新

时间：2026-09-24 11:17（Asia/Shanghai）

## 当前目标与范围

- 按用户要求实测 `agentctl` CLI 是否符合 README/项目文档预期（全流程真实使用，非仅跑测试）。
- 拉取远端更新并核查机器软件状态（用户问"软件装了吗，copy 有没有"）。
- 不涉及：update 缺陷修复的实施（已提出方案，等用户确认）；安装包传输（实体不在本机）。

## 已完成并验证

### agentctl 全流程实测（结论：符合文档预期，无功能性缺陷）

- 安装：`uv sync` 装齐 10 个依赖（当时沙箱限制需 `UV_CACHE_DIR` 指向工作区内 `.uv-cache`，后沙箱解除不再需要）。
- `bootstrap --env company --dry-run` 预览准确 → 真实 bootstrap：local.yaml 标记、目录、`.env` 生成、5/5 junction 链接；重跑幂等。
- `doctor`/`status`/`version`/`--version` 输出与退出码语义符合文档（required secret 缺失 → FAIL exit 1；不打印值）。
- `scan`/`diff --full`：Provider 独立上报，失败不上报为 MISSING，错误 → exit 2。曾出现的 uv/pnpm error 已定位为环境因素：uv 是沙箱缓存权限（解除后 success），pnpm 是本机全局 bin 目录不在 PATH（`ERR_PNPM_GLOBAL_BIN_DIR_NOT_IN_PATH`，需 `pnpm setup`）。
- `export --dry-run`：57 个 git 跟踪文件清单，exit 0。`update --dry-run`：只 fetch 不写入。
- `snapshot`：任一 Provider error → 拒绝保存基线且不创建 `.agentctl`，与文档一致（当前被 pnpm PATH 问题阻塞）。
- pytest **84/84 通过**（2.31s）。
- `.env.example` schema 与 company profile 要求一致（COMPANY_TOKEN 在列）。

### 拉取更新

- `agentctl update`：`d59cccd → cfd4f40`，3 个提交、236 文件（+26,918 行），主体是 skill 全量同步（`skills/` 8 → 45，common 启用 40，company 合并后启用 42）。
- 本地 progress.md 未提交改动曾挡住 `pull --ff-only`（update 正确拒绝覆盖，行为符合预期）；stash → pull → pop 自动合并成功，两侧内容均保留。

### 缺陷发现（未修）：update 重链使用 pull 前旧配置

- 现象：update 拉取把启用清单从 5 扩到 42，但重链零输出，doctor 显示 5/42，37 个新技能缺失。
- 根因：`agentctl/cli.py` `cmd_update`（约 L166-169）在 pull **之前** `build_effective`；`agentctl/update.py`（L77-79）拉取后直接复用该 cfg 调 `LinkManager.apply(plan(cfg.enabled_skills))` → 旧清单全 no-op。违反 README 第 6 节"update = pull + 重链"。
- 84 项测试无一覆盖"pull 改变启用清单后 update 重链"场景。
- 现场已用 `agentctl link` 补齐至 42/42（junction，`C:\Users\E0465\.agents\skills\`，本会话技能目录实际加载验证通过）。
- 提出修法（未实施）：`run_update` 在 `pull_ff_only` 之后用已持有的 `env` 重新 `build_effective(root, env)` 再重链；并补回归测试。

### 本机软件状态核实

- 本机未装 CopyQ（命令/进程/HKLM+HKCU 卸载注册表均无）。
- **上一轮 installer-transfer 交付包（1,863 文件 / ~3.2 GiB）与 `work/` 均不在本机**：`packages/installer-transfer/` 为空（`packages/` 是本次 bootstrap 新建）；C:\Users\E0465 与 D:\ 深度 ≤5 搜索无 `installer-transfer` 目录、无 `OneNote-notes-20260923.zip`；全盘仅当前一个 agent-workspace 克隆。
- 判别性证据：handoff 称 AndeSight 在收集机有安装记录，而本机注册表无任何 Andes/AndeSight/AICE 记录 → **上一轮软件收集 + OneNote 归档是在另一台机器的会话完成的**，本机只有 Git 记录（`packages/` 按 design gitignore，不进仓库）。

## 机器本地状态（本机 = 公司笔记本，company 环境）

- `local.yaml`：`environment: company`；`.env`：由 example 生成，**值全空**（COMPANY_TOKEN 待填）。
- 42/42 junction 链接健康；`.agentctl/` 未创建（snapshot 拒绝保存）；`dist/`、`manifests/`、`backups/` 空壳；`.venv` 由 uv 创建。
- doctor 当前：除 COMPANY_TOKEN MISSING（FAIL，预期）与 progress.md 未提交（WARN）外全绿。

## 未完成、阻塞和下一步

1. **update 缺陷修复待用户决策**：pull 后重建 cfg + 回归测试；用户尚未确认是否实施。
2. `.env` 填 `COMPANY_TOKEN` → doctor 全绿；`pnpm setup` 后 `agentctl snapshot` 保存资源基线。
3. 到上一轮会话所在机器核对 `packages/installer-transfer/` 实体（含 CopyQ 16.0.0 安装器）；本机如需 CopyQ 可 `winget install` 或从包内取。
4. AndeSight 5.3.1 与传输目的地仍是交付包层面的既有阻塞（见上一份交接），与本机无关。

## 重要事实与易重复踩坑

- 本机 scan 中 pnpm error 属实（PATH 缺全局 bin 目录），不是 agentctl 缺陷；uv 需要 `--offline` 参数但其缓存权限问题曾伪装成工具故障，先手工复现再定责。
- `Select-Object -First/-Last` 截断管道会把原生命令退出码变成 -1，判断退出码时不要截断输出。
- `packages/`、`work/`、`.env`、`local.yaml` 均 gitignore；Git 只存记录不存包。`firmware-mentor` 保持手动调用。

## 建议技能

- 修复 update 缺陷并验证后收尾提交：`git-delivery`。
- 拉取再遇冲突：`resolving-merge-conflicts`。
- 继续追查 update 缺陷或 pnpm 环境：`diagnosing-bugs`。
- 以上均为建议，不构成调用授权。

## 工作区与 Git 状态（handoff 创建时）

- 分支 `master` 与 `origin/master` 同步；工作树仅 `progress/progress.md` 修改（本机验证记录行）。
- 本次 handoff 与索引更新将一并提交推送。
