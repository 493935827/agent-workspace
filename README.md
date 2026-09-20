# agent-workspace

多环境 Agent Workspace 管理系统：一处维护，多环境部署；公网 Git 同步，内网离线发布；配置可追踪，环境可重建，**Secret 永不进入仓库**。

管理三类机器上的 Agents / Skills / 脚本 / 配置模板：

| 环境 | 网络 | 更新方式 |
|---|---|---|
| `personal` 个人电脑 | 公网 | `agentctl update`（git pull） |
| `company` 公司笔记本 | 公司网络 | `agentctl update`（git pull，远程可为公司 Git） |
| `intranet` 内网电脑 | 无公网 | `agentctl import <bundle.zip>`（离线包） |

## 1. 项目目标

- **Single Source of Truth**：所有公共 Agent / Skill / 脚本 / 配置模板只在一个 Git 仓库里维护。
- **环境分层**：`Effective Config = common + <profile> + local.yaml + .env(secrets)`。
- **Secret 隔离**：`.env` 与 `local.yaml` 永远 gitignore，永远不进离线包。
- **内网离线部署**：一条命令导出带校验和的 zip，内网一条命令导入。
- **可重复准备工作区**：`agentctl bootstrap` 准备项目依赖、配置模板与 Skill 链接；系统软件、全局工具和编辑器扩展的自动安装尚未实现。
- **跨平台**：Windows 优先（junction 降级链），兼容 Linux/macOS。

## 2. 架构说明

```
                 ┌────────────────────────────┐
   git remote    │  agent-workspace (SSOT)    │   个人机 / 公司机 clone
   (GitHub 等)   │  agents/ skills/ configs/  │◄─ agentctl update (git pull)
                 │  scripts/ tools/           │
                 └──────────┬─────────────────┘
                            │ agentctl export --with-wheels
                            ▼
                 agent-workspace-vX.Y.Z-offline.zip
                 (workspace/ wheels/ manifest.json SHA256SUMS)
                            │  USB / 允许的通道（人工审查后）
                            ▼
                 ┌────────────────────────────┐
                 │ 内网机                      │◄─ agentctl import (校验→备份→
                 │ packages/wheels 离线装依赖  │   安装→重链→doctor→可回滚)
                 └────────────────────────────┘

  每台机器本地:  local.yaml(环境标记+覆盖) + .env(Secret)  ← 永不进 Git / Bundle
```

- **配置合并**（`agentctl/config.py`）：dict 递归合并；列表取并集（`skills` 跨层叠加），但 `links.targets` 这类机器路径**整表替换**；标量高层覆盖。
- **Skill 链接**（`agentctl/links.py`）：`skills/` 是唯一事实源，Agent 工具目录里放链接。策略 `auto` = symlink → junction(Windows) → copy，可显式指定。copy 模式带 `.agentctl-copy` 内容哈希标记，源变更后自动检测 stale 并重同步。** чужой（不属于本工具管理的）目录只会先备份到 `backups/`，绝不直接删除。**
- **环境判定**：`--env` 参数 > `AGENTCTL_ENV` 环境变量 > `local.yaml` 的 `environment:` 字段。

## 3. 目录结构

```
agent-workspace/
├── agents/            # Agent prompt/配置模板          [Git: 是]
├── skills/            # Skill 唯一事实源                [Git: 是]
├── configs/           # common/personal/company/intranet [Git: 是]
├── scripts/           # agentctl.cmd / agentctl.sh 包装  [Git: 是]
├── tools/             # CLI/MCP 配置模板                 [Git: 是]
├── agentctl/          # CLI 工具源码 (Python)           [Git: 是]
├── tests/             # pytest 测试                     [Git: 是]
├── .env.example       # Secret schema（只有名字）       [Git: 是]
├── VERSION            # 语义化版本，如 0.1.0            [Git: 是]
├── pyproject.toml     # 运行依赖: PyYAML、ruamel.yaml    [Git: 是]
├── .env               # 真实 Secret                     [Git: 否，机器本地]
├── local.yaml         # 环境标记 + 机器覆盖             [Git: 否，机器本地]
├── .agentctl/         # 发现快照、忽略规则、配置备份     [Git: 否，不进离线包]
├── packages/          # wheels/npm 离线缓存（import 后） [Git: 否，生成]
├── backups/           # import/替换前自动备份           [Git: 否，生成]
├── manifests/         # 每次 export/import 的审计副本   [Git: 否，生成]
└── dist/              # 导出的离线包 zip                 [Git: 否，生成]
```

## 4. 第一次安装

前置要求：Python 3.10+（内网机也要有，见 FAQ）、git。

```bash
git clone <你的仓库地址> agent-workspace
cd agent-workspace
uv sync                      # 有 uv 的机器；没有 uv 见下
# 没有 uv:  python -m venv .venv && .venv/Scripts/pip install -e .
uv run agentctl --version    # 或 .venv/Scripts/python -m agentctl --version
```

验证安装：`uv run agentctl doctor`。

## 5. 三种环境初始化

```bash
# 个人电脑
uv run agentctl bootstrap --env personal

# 公司笔记本（链接目标/工具差异写进 configs/company.yaml 或 local.yaml）
uv run agentctl bootstrap --env company

# 内网电脑（先拿到离线包，见第 8 节）
python -m venv .venv
.venv/Scripts/pip install --no-index --find-links packages/wheels pyyaml "ruamel.yaml>=0.18,<0.19"
.venv/Scripts/python -m agentctl bootstrap --env intranet --offline
```

`bootstrap` 做的事（全部幂等，重复执行安全）：git init（如缺）→ 写 `local.yaml` 环境标记 → 建本地目录 → 从 `.env.example` 生成 `.env`（已存在则跳过）→ 装依赖（online 用 uv，offline 从 `packages/wheels` 装）→ 按 profile 链接 skill → 跑 doctor。

先预览不落盘：`agentctl bootstrap --env personal --dry-run`。

## 6. 更新方法（公网环境）

```bash
agentctl update              # git fetch + pull --ff-only + 重链 skill + 依赖检查
agentctl update --dry-run    # 只 fetch（只读），显示将要拉取的提交
```

`intranet` profile 配置了 `network.internet: false`，在这类机器上执行 update 不会碰网络，会提示改用 import。

## 7. 离线导出方法

```bash
agentctl export                      # dist/agent-workspace-v0.1.0-offline.zip
agentctl export --with-wheels        # 附带 pip download 的 Python wheels
agentctl export --with-npm           # 附带 npm pack 的包（有 package.json 时）
agentctl export --dry-run            # 预览文件清单，不落盘
```

导出规则：优先取 **git 已跟踪文件**（自动尊重 .gitignore）；`.env` / `local.yaml` / 生成目录双重排除；所有文本文件做 secret 模式扫描，命中即**拒绝导出**（只报文件:行号，不打印内容）；生成 `manifest.json` + `SHA256SUMS`（覆盖包内每个文件）。

## 8. 内网导入方法

```bash
agentctl import agent-workspace-v0.1.0-offline.zip --env intranet
agentctl import <zip> --dry-run      # 校验+预览，不落盘
```

导入流程：校验 SHA256SUMS（不符即拒）→ 读 manifest 对比版本（降级需 `--force`）→ **备份当前 workspace 到 `backups/`** → 安装文件（wheels 进 `packages/wheels`）→ 重建链接 → doctor。写入阶段中途失败会自动回滚。

然后做一次离线 bootstrap 装依赖（见第 5 节内网部分）。

## 9. Secret 管理

- `.env.example` 进 Git（只有变量名），`.env` 永远 gitignore。
- `agentctl doctor` 只报 `SET / MISSING`，任何命令都不会打印值。
- 导出的 bundle 经 secret 扫描且不含 `.env`；`manifest.json` + `SHA256SUMS` 使包**可人工审查、可验证完整性**。
- 公司凭据只放公司机的 `.env`，不随仓库/包流动。

## 10. 常见问题

**Q: Windows 符号链接报权限错误？**
A: `auto` 策略会自动降级 junction（目录、免权限），再降级 copy。也可在 profile 里写 `links.strategy: junction`。

**Q: 内网机没有 Python 怎么办？**
A: 当前版本要求 Python 3.10+。完全锁死的机器需要 Windows embeddable Python 方案（规划中，见 ROADMAP）。

**Q: 想让某台机器链接到别的 Agent 目录？**
A: 在该机 `local.yaml` 里覆盖（整表替换语义）：
```yaml
links:
  targets:
    - ~/.claude/skills
    - D:/agents/skills
```

**Q: doctor 里 `tool:node` 是 WARN？**
A: WARN 不阻断。profile `tools:` 里声明的工具缺失只提醒；只有 git/python/pyyaml 缺失才是 FAIL。

**Q: 公司机不能用 GitHub？**
A: 远程随便指：`git remote set-url origin <公司GitLab地址>`，`agentctl update` 只做 `git pull`，不关心 origin 是谁。

## 11. 回滚方法

```bash
agentctl restore backups/workspace-v0.1.0-20260915-120000.zip   # 恢复文件
agentctl link                                                    # 重建链接
agentctl doctor                                                  # 验证
```

import 时如果 doctor 失败，提示里会给出对应的 restore 命令；被链接替换过的原目录都在 `backups/` 里带时间戳保存。

## 命令参考

### 环境发现、比较与登记

这组命令解决“机器上实际有什么、配置里期望有什么、哪些需要登记”。`resources` 是期望清单，旧 `tools` 仍是 doctor 的可执行文件检查名单。**登记不会安装软件，bootstrap 目前也不会执行 resources 中的安装声明。**

```bash
agentctl scan                             # 默认与 --quick 相同
agentctl scan --full --new                 # 六个 Provider，只看未登记提醒
agentctl scan --provider npm --json        # 一个 JSON 对象，stdout 不混入提示
agentctl --env personal diff --full        # 当前机器与三层有效配置对比
agentctl --env personal diff --full --check # 用退出码做自动检查
agentctl snapshot --dry-run                # 完整扫描，预览保存基线
agentctl snapshot                         # 保存最近一次成功的显式基线

agentctl adopt --provider npm --profile personal             # 只列候选
agentctl adopt npm:example --profile personal --dry-run       # 单项预览
agentctl adopt npm:example --profile personal                 # 单项登记
agentctl adopt --all --provider npm --profile personal        # 登记合格候选
agentctl adopt vscode:ms-python.python --profile common --pin-version

agentctl ignore npm:example                # 只忽略本机未登记提醒
agentctl ignore --list
agentctl ignore npm:example --remove
```

`--profile` 每次 adopt 都必填，支持 `configs/` 中现有的任意合法 profile（包括 common）。`--env` 是读取有效配置的全局参数，放在子命令前；没有环境标记时读取 common + local。adopt 查重只看目标共享层：personal 看 common + personal，common 只看 common；local 和其他 profile 不阻止登记。已有声明和版本锁定不会被 adopt 改写。输出中的 `local_overrides` 提示本机覆盖导致的最终版本要求。

```yaml
resources:
  npm:
    "@openai/codex":
      version: null       # 只要求存在；观测版本只保存到快照
  winget:
    BurntSushi.ripgrep.MSVC:
      version: "14.1.1"   # 精确版本，不支持版本区间
```

映射继续按 common → profile → local 合并，显式 `version: null` 可以解除上层版本锁定；第一版不支持取消继承某个资源。身份是 `(provider, id)`，npm 与 pnpm 的同名包不会合并。uv/pipx 名称按 Python 包名规则统一，VS Code 扩展 ID 统一小写。

| 当前状态 | 含义 |
|---|---|
| NEW | 未登记且来源足够明确；**不表示刚安装** |
| UNKNOWN | 可发现，但来源不明确，不进入批量登记 |
| MATCH | 已满足存在性或精确版本要求 |
| DRIFT | 观测版本与锁定版本不同 |
| MISSING | 对应 Provider 成功完整扫描，但没有找到已声明资源 |
| INDETERMINATE | 未扫描、不可用、执行/解析失败，或精确版本证据不足 |
| ABSENT | 上次快照有、现在没有，且没有对应声明 |

历史变化单独保存在 `history`：首次为 NO_BASELINE，范围不可比较为 INCOMPARABLE，其余包括 APPEARED、DISAPPEARED、VERSION_CHANGED、RESTORED、UNCHANGED。MATCH 可以同时显示 RESTORED。`diff` 默认只汇总 MATCH，`--all` 显示全部；`scan --new` 隐藏已登记和已忽略项目。ignore 只按精确身份匹配，不隐藏已声明资源的异常。

**扫描范围与失败处理：**

- quick 查询 uv、pipx、npm、pnpm、VS Code；full 额外查询 Windows Winget。只读当前 PATH 对应的管理器环境和默认编辑器实例，不穷举所有 Node 环境或编辑器 profile。
- Provider 独立报告 success / unavailable / error。命令不存在属于 unavailable；执行失败、超时、输出无法完整解析属于 error。不会用失败结果推断 MISSING。
- `--provider` 将比较范围限制到一个管理器；quick 未扫描的已声明资源仍为 INDETERMINATE，`--check` 不会静默放行。没有相关声明的 unavailable 不影响检查通过。
- npm/pnpm 只有清单提供可验证的 registry 来源时才允许登记；没有来源字段、本地链接、带凭据或未知 URL 均为 UNKNOWN。部分 npm 版本不输出来源字段，此时需要后续的人工来源补录功能，当前不会猜测来源。
- Winget 使用文本表格，支持中英文列宽；截断 ID 或无法识别的行会使整个 Provider 失败。近似版本（如 `> 1.0`）视为版本未知。同一身份存在多个实例时合并存在性，版本不一致则标记版本未知。VS Code 记录编辑器管理的扩展身份，不保证其原始安装渠道是 Marketplace。
- 只执行查询命令，不安装、不更新源、不登录、不自动接受协议；尽可能关闭更新检查和交互。第三方工具可能自行写缓存、日志或访问已配置源，因此 scan 的只读承诺针对 agentctl 主动写入的配置、状态及安装资源。

**状态、写回与退出码：**

- scan、diff 不写状态。只有 snapshot 更新 `.agentctl/state/current.json`；它完整扫描六个 Provider，任一个 error 都保留旧基线，unavailable 可以保存为未覆盖。历史比较只在前后成功且扫描范围指纹一致时成立；指纹包含主机、用户、可执行文件和管理器目录，原始路径不输出。
- ignore 写 `.agentctl/ignore.yaml`。adopt 保留 YAML 注释和顺序，先整体校验，再检查文件是否被并发修改，备份目标共享配置并原子替换。agentctl 写进程之间用锁互斥；外部编辑器不遵守该锁，写入前再次检查内容，无法承诺任意外部程序与替换操作之间的严格事务隔离。
- 配置备份在 `.agentctl/backups/`，不自动清理。需要恢复时手工将对应 YAML 复制回 `configs/<profile>.yaml`；现有 `restore` 只接受离线导入备份 ZIP。若进程被强制终止留下 `.agentctl/write.lock`，先确认没有运行中的写操作，再手工移除锁文件。
- snapshot、adopt、ignore 支持 `--dry-run`，不创建 `.agentctl`。`--pin-version` 遇到未知版本拒绝写入，批量中任一候选不满足则整批不写。
- 退出码 **0**：正常完成；**1**：仅 `--check` 发现 MISSING/DRIFT；**2**：执行、解析、配置或状态错误，或 `--check` 下已声明资源缺少覆盖/版本证据。NEW 不导致检查失败。
- JSON `schema_version` 当前为 1，包含环境、Provider 状态和范围指纹、资源比较、历史变化及汇总。过滤只影响显示的资源，汇总保留完整比较结果。错误只包含固定类别，不回显外部 stdout/stderr 或 YAML 错误原文；不扫描 `.env`、SSH 或凭据存储。

```
agentctl status                  # 版本/环境/commit/skill 数/链接健康度
agentctl version                 # agentctl + workspace + commit
agentctl doctor                  # PASS/WARN/FAIL 健康检查
agentctl update [--dry-run]      # 在线更新（内网环境自动拒绝联网）
agentctl bootstrap --env ENV [--dry-run] [--offline]
agentctl link [--skill NAME] [--dry-run]
agentctl unlink [--skill NAME]
agentctl export [-o ZIP] [--with-wheels] [--with-npm] [--dry-run]
agentctl import ZIP [--env ENV] [--dry-run] [--force]
agentctl restore BACKUP_ZIP
```

## 安全设计要点

- 不绕过公司安全机制、不做隐蔽传输；bundle 是明文 zip，可人工审查。
- 所有网络操作显式：`update`=git fetch/pull，`export --with-wheels`=pip download，`import` 本身零网络。
- 覆盖文件前先备份；对未知目录（foreign）只备份不动刀；zip 路径穿越校验。
- 关键操作支持 `--dry-run`：bootstrap / link / export / import / update。
- 日志与 doctor 输出经 secret 安全设计，不出现任何 `.env` 值。

## ROADMAP（未实现）

- 存量 Skill 迁入工具（命令名另定，adopt 已用于资源登记）
- resources 声明对应的安装/恢复执行器、人工来源补录和多管理器实例扫描
- Windows embeddable Python 打包，给完全锁死的内网机
- npm 依赖的完整离线生命周期（当前只有清单 + npm pack 缓存）
- MCP server 的安装与配置管理（当前只有 registry 模板 + JSON 校验）
- 多 profile 叠加（如 company+intranet 组合）
