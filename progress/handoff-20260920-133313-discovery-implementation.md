# Environment Discovery 第一版实施交接

日期：2026-09-20 13:33（Asia/Shanghai）。未取得可验证的对话 ID 或分享链接；本文件归档本次“继续下一步”实施对话。

## 目标与授权

项目是 agent-workspace，Python CLI 为 agentctl。长期目标为 AI 开发环境重建，本轮实现 Discover → Compare → Explicit Adopt，不包含系统软件安装器或后台服务。

用户本轮要求“继续下一步”，已按上次接受的 23 项决策完成实施；旧归档中的“等待最终实施确认”是当时状态，现已解除，不要再次要求确认开始实施。原设计和决策按需参阅 [设计交接](handoff-20260920-110828-environment-discovery.md)。本次显式调用 handoff 只进行归档交付，不继续排查或扩展功能。

功能提交：`e23cd3a`（`feat: discover compare and explicitly adopt environment resources`），已成功推送 `origin/master`。归档开始时工作区和暂存区干净，HEAD 与 origin/master 一致。

## 已完成的实现与入口

- [commands.py](../agentctl/discovery/commands.py)：scan、diff、snapshot、adopt、ignore 参数与编排，固定类别错误输出，JSON stdout 不混入正常提示。入口注册在 [cli.py](../agentctl/cli.py)。
- [model.py](../agentctl/discovery/model.py)：校验过的资源、Provider 结果、resources 声明；身份为 `(provider, id)`，Python 包名和扩展 ID 规范化。
- [providers.py](../agentctl/discovery/providers.py)：Winget、uv、pipx、npm、pnpm、VS Code 查询与解析；超时/退出/解析失败隔离，命令不存在为 unavailable；原始输出不持久化、不回显。
- [compare.py](../agentctl/discovery/compare.py)：当前 NEW/MATCH/DRIFT/MISSING/UNKNOWN/INDETERMINATE/ABSENT 与历史变化分开，检查模式使用 0/1/2 退出码。
- [storage.py](../agentctl/discovery/storage.py)：最近快照、精确忽略项、保留 YAML 注释和顺序的登记；整体校验、写锁、并发内容检查、备份、原子替换。
- [pyproject.toml](../pyproject.toml) 和 uv.lock 增加 `ruamel.yaml>=0.18,<0.19`；[workspace.py](../agentctl/workspace.py) 同步 Python 3.10 等情况下的依赖回退清单，离线包测试同步新依赖。
- `.agentctl/` 已加入 .gitignore 和 [bundle.py](../agentctl/bundle.py) 的 DENY_DIRS，覆盖 Git 文件清单与遍历回退两条路径。
- [README.md](../README.md) 已补充完整命令、状态、退出码、写回与恢复说明，并修正 bootstrap 能力边界、旧 adopt 的 Skill 迁移命名冲突。

## 不应重复讨论或改变的语义

- quick（默认）扫描 uv/pipx/npm/pnpm/VS Code，full 加 Winget；`--provider` 限定单一管理器。quick 未扫描的已声明资源为 INDETERMINATE，不能通过 `--check`。
- scan/diff 不主动写配置或本机状态；只有显式 snapshot 更新 `.agentctl/state/current.json`。任一已尝试 Provider error 时整次快照不替换；unavailable 可以保存为未覆盖。第三方管理器自身仍可能写缓存、日志或访问配置源。
- 历史比较只在前后成功且范围指纹一致时成立。指纹包含主机、用户、可执行文件和管理器目录等信息，输出哈希而非原始路径。
- adopt 每次必选 `--profile`，支持 configs 下现有自定义 profile；无单项且无 `--all` 时只展示候选。批量仅登记未声明、未忽略且来源明确的资源。
- 目标层查重：common 只看 common；其他 profile 看 common + 目标层。local 和其他 profile 不阻止登记。已有声明和锁定不被 adopt 改写；local 覆盖效果在输出中提示。
- 默认 `version: null` 只要求存在；显式 `--pin-version` 才锁定可靠精确版本，批量任一候选缺少版本则整批拒绝。下层 null 可解除上层版本锁定，不支持取消继承资源。
- ignore 仅隐藏未登记提醒，不隐藏已声明资源的异常；支持 list/remove/dry-run。
- 同一 `(provider, id)` 的多个安装实例合并存在性；版本不同则版本未知。Winget 的近似版本（如 `> 1.0`）也为未知，不能作为精确锁定依据。
- 配置备份在 `.agentctl/backups/`，手工复制恢复；现有 restore 仍只处理 ZIP。外部编辑器不遵守 agentctl 写锁，不能承诺跨任意外部程序的严格事务隔离。强制终止可能留下 write.lock，需确认无运行中写操作后手工移除。

## 验证证据与边界

新增 [test_discovery.py](../tests/test_discovery.py)，所有管理器响应在自动测试中 mock，写入只使用 pytest 临时工作区。

验证过程：

1. 原有 31 项测试通过。
2. 功能和补充测试完成后，`uv run --with pytest python -m pytest -q`：83 passed。
3. 实机发现 Winget 同一软件多个安装实例后，增加归一化处理及一项测试；`uv run --with pytest python -m pytest tests/test_discovery.py -q`：53 passed。
4. 累计 84 项测试已覆盖通过，但没有在最后一项新增后重新运行全部 84 项；复用未受该局部改动影响的原有回归结果。
5. 最终 staged diff 的 `git diff --cached --check` 通过；本次归档只修改文档，不需要重新跑项目回归。

覆盖：NEW → adopt → MATCH → 模拟另一机 MISSING；Provider 不可用不误报缺失；历史/范围变化；快照失败保留旧基线；注释、备份、并发冲突、替换失败；目标层与 local 覆盖；批量 pin 失败；ignore；异常及恶意来源中的 Secret canary；离线导出双路径排除；旧配置兼容。

Windows 本机查询事实（本次实施时观测，不保证未来机器状态不变）：

| Provider | 实际结果 |
| --- | --- |
| Winget | success，200 行安装实例归一化为 187 个资源身份，20 个版本未知 |
| uv | success，工具列表为空 |
| npm | success，4 项；清单缺少可验证来源字段，因此均为 UNKNOWN |
| VS Code | success，27 个扩展 |
| pipx | unavailable，本机未找到命令 |
| pnpm | error，查询返回非零退出码；原因尚未诊断 |

正常 pipx/pnpm 解析只通过 mock 验证，未实机验证成功路径；Linux/macOS 未实机验证。没有未提交功能代码，也没有已知失败的自动测试；这些实机/跨平台限制不等于已验证成功。

## 下一步和已知限制

1. 先读 progress.md 并核对 Git 状态；若用户要求继续，优先诊断本机 pnpm 的 scope 查询或 list 查询哪一步返回非零。当前 PATH 找到的 pnpm 是 Codex runtime 的 fallback 包装命令，不能仅凭路径断言根因。现有错误保护不回显原始 stderr；诊断也应避免输出凭据。
2. npm 的 `list --global --depth=0 --long --json --offline` 本机输出没有 resolved/_resolved。已只读检查当前全局 root 下 `.package-lock.json`，该文件不存在。不要凭包名猜测 registry 来源，也不要把 UNKNOWN 自动改成可重建资源。人工来源补录尚未设计实施，属于后续产品范围。
3. 按需要增加其他真实管理器版本/系统的格式覆盖。Winget 依赖文本表格，支持中英文宽字符列；截断或无法完整解析时失败关闭。VS Code 清单证明编辑器管理的扩展身份，不证明原始来源为 Marketplace。
4. 安装执行器、后台服务、多 Node 环境/编辑器实例穷举继续留待后续明确范围。bootstrap 当前不会安装 resources 声明中的软件。

真实机器的全量 snapshot 会被当前 pnpm error 阻止，这是既定原子提交规则；其他 Provider 的扫描结果仍可显示。实现期间未把本机资源 adopt 到共享配置，也未保存真实机器快照。

## 工作区、运行任务与交付

归档前：分支 master，上游 origin/master；功能提交 e23cd3a 已推送，工作区干净。本轮未新增需要保留的临时脚本或独立后台服务；测试临时目录由 pytest 管理，不属于项目持久记录。只读查询进程已完成，无需恢复后台任务。

本次新增交接文档并更新现有进度索引；根 AGENTS.md 已有正确导航及手动调用约定，无需重复修改。归档提交及推送结果以 Git 实际返回和本次回复为准，不预先记为成功。

## 建议技能

- 排查 pnpm：`diagnosing-bugs`；核对互联网命令资料时按 `agent-reach` 路由读取官方资料。
- 新增模块归属或更新进度：`project-structure`；修改验证与提交推送：`git-delivery`。
- handoff 保持显式手动调用；本列表不授权调用其他手动技能。
- `firmware-mentor` 只有用户在当前消息明确写 `$firmware-mentor` 或附技能链接时才能加载，不能因 C/Python/嵌入式背景自动调用。
