# skill-audit 修复日志（fix-log）

记录按 `skill-audit/skill-audit-report.md` P1/P2 建议执行的修复（修复轮日期 2026-11-02）。范围限于 `skills/` 下被点名的技能文件与本日志；不改动 `dist\`，不推送远程。本文件由 t5（目录卫生）创建初版，t6 扩写为覆盖 t1–t6 全轮的修复日志。

## t1 — run-tickets / ui-ux-pro-max / define-bounded-goal（B2/B3/B4/B5/B11）

| 编号 | 文件 | 改动摘要 | 验证结果 | 双副本同步 |
|---|---|---|---|---|
| B4 | `skills/run-tickets/SKILL.md` L18 | `docs/agents/issue-tracker.md` 引用改条件式：存在则读；否则先运行 `/setup-matt-pocock-skills` 或回退 `references/github-tracker.md` | L18 原文含 "if that file exists … fall back"；`docs/agents/issue-tracker.md` 当前不存在（预期，setup 未运行，属 D1 配置项非缺陷）；`references/github-tracker.md`、`references/local-tracker.md` Test-Path 存在 | ✓ 已同步 |
| B4 旁注 | `skills/run-tickets/references/github-tracker.md` L8 | 同一引用同步改条件式（"If docs/agents/issue-tracker.md exists, read it …"） | 已核对原文 | ✓ 已同步 |
| B5 | `skills/run-tickets/SKILL.md` L27 起 | helper 命令改为 `<skill-root>/scripts/ticket_graph.py` 并新增 `<skill-root>` 解析说明与双副本同步要求 | 全文件 `USERPROFILE` 出现 0 次；`scripts/ticket_graph.py` 存在 | ✓ 已同步 |
| B2 | `skills/ui-ux-pro-max/README.md`（新建）+ `SKILL.md` L45 | 新增含 Python 安装指引/用法/flags/目录结构的 README；SKILL.md 空引用改为真实链接 `[README.md](./README.md)` | `./README.md` Test-Path 存在，链接 grep 1 次 | ✓ 已同步（.agents 亦新建） |
| B3 | `skills/ui-ux-pro-max/SKILL.md`（12 处） | `${CLAUDE_PLUGIN_ROOT}/.claude/skills/ui-ux-pro-max/scripts/search.py` 全部改为 `<skill-root>/scripts/search.py`，并注明按技能根目录解析 | `CLAUDE_PLUGIN_ROOT` 出现 0 次；`scripts/search.py` 存在 | ✓ 已同步 |
| B11 | `skills/define-bounded-goal/SKILL.md` L3/L60/L134 | 删除 `token_budget` 参数指引，改为仅 `objective`/`max_goal_rounds`；停止原因改 `goal_rounds_exhausted`；description 追加 `$define-bounded-goal` 显式调用要求 | `token_budget` 出现 0 次；`goal_rounds_exhausted` 出现 1 次；frontmatter 校验通过 | ✓ 已同步 |

## t2 — reg-to-ll 嵌套技能系（B1/C1/C2）

| 编号 | 文件 | 改动摘要 | 验证结果 | 双副本同步 |
|---|---|---|---|---|
| B1 | `skills/reg-to-ll/workflow-run-skill/SKILL.md` 飞书输入段 | 注明需先具备 `feishu-fetch` 技能且当前环境缺失；替代方式 = 手动导出 Excel 走 `--source local`（本地链路完整）；保留环境具备后的原始指引 | 与实际一致（三处技能目录均无 feishu-fetch） | ✓ 已同步 |
| C1 | `skills/reg-to-ll/workflow-run-skill/SKILL.md` + `reference.md` + `.reg-to-ll-install.json` | frontmatter `name: workflow-run` → `workflow-run-skill`（目录名不动）；reference.md 标题同步；清单中两个被改文件 SHA-256 重算 | frontmatter name=目录名 校验通过；清单 14 个 files 键逐一 Test-Path 全部存在（14/14） | ✓ 已同步 |
| C2 | `skills/reg-to-ll/workflow-run-skill/SKILL.md` L14 | 悬空 check Skill 引用改为"当前环境未安装；可手动核对寄存器定义与 SVD 的一致性" | 已核对原文 | ✓ 已同步 |

## t3 — 文档-实现对齐（C5/C8/C9/C12/C13）

| 编号 | 文件 | 改动摘要 | 验证结果 | 双副本同步 |
|---|---|---|---|---|
| C5 | `skills/pack-to-dts/SKILL.md` L67 | `--output-dir` 参数表改"必填，无默认值，由用户指定目标位置"（脚本零改动） | "必填" grep 1 次；5 个 `scripts/pack-*.py` Test-Path 存在 | ✓ 已同步 |
| C8 | `skills/reverse-engineer-anything/SKILL.md` L37-40 | 客户端清单 15 → 23（补 qwen_code/trae/pi/hermes/qoder/droid/zcode/dsh），顺序与 `references/connection-and-recovery.md` 一致 | 23 客户端原文核对；`references/connection-and-recovery.md` Test-Path 存在 | ✓ 已同步（并入 C21 合并） |
| C9 | `skills/andes-aice-bringup/SKILL.md` L32 | 措辞改为 `start_aice.ps1` 不校验端口占用、由 `scripts/diagnose_aice.ps1` 只读列出 2354/4444/6666/9901（脚本零改动） | `diagnose_aice.ps1` grep 2 次；`scripts/diagnose_aice.ps1`、`scripts/start_aice.ps1`、两个 references/ 文件 Test-Path 存在 | ✓ 已同步 |
| C12 | `skills/qt-ui-design/README.md` | Files 表补列 `LICENSE.txt` \| License terms | `LICENSE.txt` Test-Path 存在 | ✓ 已同步 |
| C13 | `skills/teach/SKILL.md` | 词汇表段落补 `[GLOSSARY-FORMAT.md](./GLOSSARY-FORMAT.md)` 链接 | `./GLOSSARY-FORMAT.md` Test-Path 存在；同目录其余三个 `*-FORMAT.md` 链接亦存在 | ✓ 已同步 |

## t4 — 占位/空壳六技能处置（A 组 + B6/B7/B8）

t4 任务输出未落库，本节由 t6 对 `git diff` 逐文件复核归纳。六文件均为"占位声明删除 + 实质内容扩写/骨架化"，`Placeholder content|Example skill` 字样 grep 全部为 0 次。

| 编号 | 文件 | 改动摘要 | 验证结果 | 双副本同步 |
|---|---|---|---|---|
| B6 | `skills/code-review/SKILL.md` | description 重写为含触发场景的完整描述；正文扩写为面向嵌入式/C/Python 的审查清单（正确性/边界/错误处理/并发与资源/测试覆盖/风格）+ blocker/major/minor/nit 严重级别表 + 逐文件输出格式与三档结论 | 占位字样 0 次；正文非空 | ✓ 已同步 |
| B7 | `skills/git-helper/SKILL.md` | 分支卫生（命名/rebase 时机/清理）、Conventional Commits 类型表、三层安全撤销表、reflog 兜底、事故恢复表；删除残留测试痕迹标题 "Update note (simulated edit on personal machine)" | 占位字样 0 次 | ✓ 已同步 |
| B8 | `skills/python-helper/SKILL.md` | C 习惯→Python 习语对照表、Gotchas、venv/pip freeze/packaging、断点与 logging、异常↔C 直觉表、ctypes 最小互操作示例 | 占位字样 0 次 | ✓ 已同步 |
| A | `skills/document-helper/SKILL.md` | 空壳改为公司环境骨架模板：Draft/Format/Review 工作流 + 最小内容骨架，公司特定事实全部标注 `TODO(公司环境)`（装配层明确"示例/待填"定位） | 占位字样 0 次；`configs/company.yaml` Test-Path 存在 | ✓ 已同步 |
| A | `skills/internal-doc-search/SKILL.md` | 空壳改为内网检索骨架：前提（`INTERNAL_DOC_URL`，未设置即停止且不回退公网）、查询工作流、结果引用格式、离线更新约定，公司事实标注 `TODO(公司环境)` | 占位字样 0 次；`configs/intranet.yaml`、`.env.example` Test-Path 存在 | ✓ 已同步（.agents 新增该技能副本，见 t6 说明） |
| A | `skills/jira-helper/SKILL.md` | 空壳改为公司 Jira 骨架：REST API v3 查票/流转（先列 transitions 再用返回 ID）/评论（ADF 格式）curl 示例 + JQL 起步模板 + 安全约定，实例事实标注 `TODO(公司环境)` | 占位字样 0 次；`configs/company.yaml`、`.env.example` Test-Path 存在 | ✓ 已同步 |

## t5 — 目录卫生（C3/C4/C7/C10/C11/C17）

- **C17**：`skills/serial-debug.7z`（166,776,691 字节）移动到 `archive/serial-debug.7z`（新建 `archive/` 目录，未删除）。移动前后 SHA256 一致（`35240C5693340F402979E398D14BB2173830913650770EAD6C6BFA05346CEAAB`），`skills/` 根目录已无该文件。
- **C10**：删除 `skills/pyside6-fluent-ui` 内 3 个 `__pycache__`（`scripts/`、`templates/pyside6_fluent_ui/`、`tests/`，共 20 个 .pyc）。
- **C11**：删除 `skills/ui-ux-pro-max` 内 2 个 `__pycache__`（`scripts/`、`scripts/tests/`，共 17 个 .pyc）。
- **C7**：删除 `skills/pack-to-dts/scripts/__pycache__`（含 `common.cpython-312.pyc`）。
- **C10/C11/C7（serial-debug 部分）**：删除 `skills/serial-debug` 内 3 个 `__pycache__`（`scripts/`、`tests/`、`windows/`，共 38 个 .pyc）。清理只覆盖技能自身代码的缓存；`serial-debug/.venv` 内文件未做任何改动。
- **C3（有意保留，本轮不动）**：`skills/serial-debug/` 下的 `.venv/`、`build/`、`dist/`、`progress/` 按任务约定保留——`windows/README` 有意引用 `.venv` 作为运行时，移出会破坏本地运行；`build/SerialWorkbench/localpycs/` 内的 PyInstaller 构建缓存 .pyc 因此一并保留，待后续轮次（移出或加入忽略清单）再处理。
- **C4**：`references/mcp.md` 保留未删，在 `skills/serial-debug/SKILL.md` References 小节新增一行引用（说明 MCP 仅在用户已配置 serial MCP 客户端或明确要求时使用，共享控制台 Conserver 工作流仍为默认）。

t5 验证：四个技能目录内（排除 `.venv`/`build`）剩余 `__pycache__` 与 `*.pyc` 均为 0；`archive/serial-debug.7z` 完整存在。t6 复核：`serial-debug/SKILL.md` 中 `references/mcp.md` 等 10 个本地引用 Test-Path 全部存在。

## t6 — C21 漂移合并 + 双副本同步 + 全量验证

### C21 合并

- 以工作区版 `skills/reverse-engineer-anything/SKILL.md`（较新：23 客户端清单、`rea-agents@latest`）为基底，frontmatter `metadata`（`version: "42"` 之下）补入 `tool_count: 207` 键。
- 两处副本（工作区 + `C:\Users\E0465\.agents\skills\`）重写为逐字节相同内容：SHA-256 一致（`E73748F732D1…`），两处 `tool_count: 207` 各 grep 到 1 次。

### 双副本同步

- 同步清单：本轮 19 个修改文件 + 1 个新建文件（`ui-ux-pro-max/README.md`），用 `Copy-Item` 复制到 `C:\Users\E0465\.agents\skills\` 对应位置：reverse-engineer-anything、run-tickets（SKILL.md + references/github-tracker.md）、ui-ux-pro-max（SKILL.md + README.md）、define-bounded-goal、reg-to-ll（.reg-to-ll-install.json + workflow-run-skill/SKILL.md + workflow-run-skill/reference.md）、pack-to-dts、andes-aice-bringup、qt-ui-design（README.md）、teach、code-review、git-helper、python-helper、document-helper、jira-helper、internal-doc-search、serial-debug。
- 结果：**20/20 SHA-256 逐字节一致**；复制后约 2 分钟二次复核仍 **20/20 一致**（稳定）。
- 说明：18 个既有目标文件在 `Copy-Item` 时报告过一次瞬时 "file in use"（技能加载器/观察进程持有读取句柄），以哈希比对为准的最终结果不受影响。
- `reg-to-ll` 嵌套目录名未改（t2 选择了改 frontmatter name），无需改名同步；未删除 `.agents` 任何独有技能；`~\.agents\skills\pyside6-fluent-ui` 无内容改动文件、亦无 `__pycache__`（已核查），无需同步动作。
- **副本格局变化**：`internal-doc-search` 原为"仅工作区"技能，本轮按任务清单同步后在 `.agents` 新增副本，双副本格局由 45 → 46（其余 3 个仅工作区技能 game-dev/image-tools 未动，是否双向同步属 P3-11 待决策项）。

### 全量验证

- **frontmatter**：15 个被改 SKILL.md 全部通过（`---` 成对闭合、`name` 与目录名一致，含嵌套 `workflow-run-skill`）：15/15 PASS。
- **本地引用 Test-Path**：20 个被改文件逐一扫描（markdown 链接 + 反引号路径 + 斜杠路径），技能内引用全部存在：reverse-engineer-anything 6 个 references/、run-tickets 2 个 references/、ui-ux-pro-max `scripts/search.py`、reg-to-ll `reference.md` + `run_workflow.py`（按 reg-to-ll 根解析）、pack-to-dts 5 个 `scripts/pack-*.py`、andes-aice-bringup 2 脚本 + 2 references、teach 4 个 `*-FORMAT.md`、serial-debug 6 references + 2 scripts + `windows/` 2 文件、qt-ui-design `LICENSE.txt`、ui-ux-pro-max `README.md` 均存在。
- **有意缺失/条件式引用（非缺陷）**：`docs/agents/issue-tracker.md`、`docs/agents/triage-labels.md`（均已改条件式，"when present"）；run-tickets L20 的 `CLAUDE.md` 属"检查以下文件是否存在于仓库"的扫描清单（工作区有 AGENTS.md）；ui-ux-pro-max 的 `design-system/<slug>/MASTER.md` 与 teach 的 `MISSION.md` 等为运行时生成物；andes-aice-bringup 的 `atom_die_ll_cmd.py`/`ICEman.exe`/`interface/jtagkey.cfg`/`libusb-AICE-driver/*.inf` 属用户侧 Andes ICE 工具包文件；其余 MISSING 命中为扩展名示例（`.i64`、`.c` 等）与 JSON 路径表达式，非文件引用。
- **修复标记 grep 电池**：`CLAUDE_PLUGIN_ROOT`=0、`token_budget`=0、`USERPROFILE`=0、六文件 `Placeholder content|Example skill`=0，全部符合预期。
- **观察（遗留机制项）**：`skills/ui-ux-pro-max/scripts/__pycache__`（core/design_system/reasoning_contract 三个 .pyc）于本轮同步后约 18:27:30 被外部进程重新生成——t5 清理会被运行时重新触发，建议后续轮次把 `__pycache__` 纳入忽略清单（同 C3 已登记的 build 缓存处理），避免反复手删。

### 范围与遗留

- 本轮未修改 `dist\`，未推送远程，未做 git 提交（git 本地提交属统一提交任务）。
- 未处理项（不在 t1–t6 范围）：C6/C14（触发策略确认）、C15/C16（机器特定/跨 harness 措辞）、C18（裸 SKILL.md 技能的支撑文件，A/B 组占位已部分覆盖）、C19/C20（description 规范化）、D1（运行 `/setup-matt-pocock-skills`，需用户侧操作）、D2/D3（环境/网络依赖）、D5（范围外登记）。

## 总体结论

审计 P1 五项中 4 项完成（占位/空壳六技能、reg-to-ll 飞书链路说明、run-tickets 路径与配置、ui-ux-pro-max 指引），第 5 项（运行 `/setup-matt-pocock-skills`）属用户侧配置操作，本轮以条件式引用兜底保证不阻塞使用；P2 五项中 4 项完成（嵌套技能名与悬空引用、define-bounded-goal 参数修订、目录卫生——C3 按约定登记保留、文档-实现对齐），第 5 项触发策略确认（C6/C14）未动。P3 的 C21 本轮完成合并并将本轮全部改动同步至 `~\.agents\skills\`（20/20 逐字节一致），长期同步机制与仅单侧技能的双向同步仍为待决策项。全部被改 SKILL.md frontmatter 15/15 通过、本地引用核验无真实悬空（缺失项均为条件式/运行时/外部文件）。工作区 `skills/` 与 `~\.agents\skills\` 就本轮改动而言已恢复一致。

## ׷�ǣ��û�ָʾ�ļ���ɾ����2026-11-02��commit 0444c69 ֮��

- ���û�ȷ�ϣ�8 ��ȫɾ / ˫����ͬɾ / ���ύ git������ȫɾ������ 8 �����ܵ�˫������workspace skills/ �� ~\.agents\skills �� 8 ��Ŀ¼���� 16 ������
  code-review��git-helper��python-helper��document-helper��jira-helper��internal-doc-search��define-bounded-goal��reg-to-ll����Ƕ�� workflow-run-skill����
- ɾ��ǰ״̬���� 8 �������ڱ��� t1�Ct6 ��������޸�/��д/ģ�廯���� commit 0444c69 �ύ��ɾ���� commit 0444c69 ����Щ�ļ��ڹ�������δ�ύ�� deletion ״̬��
- ɾ���������workspace skills/ 40 ������Ŀ¼��~\.agents\skills 41 ������ t6 ����ͬ���� internal-doc-search ��һ��ɾ������
- Ӱ�죺reg-to-ll �� Excel��SVD/CMSIS/LL Driver ת����·�����б��ؼ��ܳ��أ�dist ���߰������Ժ���Щ���ܵľɸ�������Ӱ�����У�������־δ��ɾ���ύ git�����û�ѡ�񣩡�
