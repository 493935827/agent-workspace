# Handoff：XERJ 本地搜索引擎装机实测 + 上游仓库同步

- 会话：session ID 不可见（2026-10-26，DeepSeek Harness Web）
- 主题：安装 [xerj-org/xerj](https://github.com/xerj-org/xerj)（本地优先搜索引擎 + MCP server，Rust 单文件）并实测检索效果；把上游源码克隆进工作区并配置后续同步
- 状态：**安装、实测、克隆与同步配置全部完成**；MCP 接入 dsh 未做（待用户决策，见"待办"）

## 目标与范围

给 agent 工作区配一个本地代码/文档搜索引擎（xerj：BM25 + 向量 + 混合检索、Elasticsearch 兼容 API、MCP server、Corpus Hub 预索引语料），用 agentctl 工作区真实文件实测效果，并把上游仓库放进 `projects/xerj` 供参考与同步。纯环境配置任务，未改任何项目代码。

## 已完成并验证

### 1. 安装（v1.0.0-rc.99）

- 下载渠道：GitHub release 直连 ~50 KB/s 且 120s 超时 → `gh-proxy.com` 镜像断点续传（~290 KB/s），zip 以**官方 .sha256 校验通过**（`6e3e4b89…d47e`）
- 安装位置：`C:\Users\E0465\AppData\Local\Programs\xerj\xerj.exe`（135 MB 单文件，无依赖）；zip 内含一层版本子目录，已扁平化对齐官方安装器布局
- 用户 PATH 已追加该目录（**仅新开终端生效**，已开会话需手动补）；`xerj -V` → `xerj v1.0.0-rc.99`
- 官方一键安装器 `irm https://xerj.org/get.ps1 | iex` 同样从 GitHub releases 下载，本机网络直连不可用；镜像 + 官方校验兜底是可靠组合（与 REA handoff 的下载经验一致）

### 2. 服务启动配置（一个本机坑）

- 默认 gRPC 端口 8081 被本机 McAfee 服务 `macmnsvc`（pid 5616）占用 → 启动即失败（os error 10013，报错信息自带排查指引）
- 解决：写 `C:\Users\E0465\xerj-data\xerj.toml`，仅设 `[server] grpc_port = 9202`（不动 McAfee）；ES 兼容端口保持默认 9200，native REST 9201
- 启动命令：

  ```powershell
  xerj --insecure --config "$env:USERPROFILE\xerj-data\xerj.toml" --data-dir "$env:USERPROFILE\xerj-data"
  ```

- `--insecure` 关 TLS+API-key 认证，仅绑 127.0.0.1，适合单人开发机（官方安全模型：能连上端口即 superuser）
- 数据目录 `~\xerj-data` 在工作区外，符合官方「数据目录勿放进被索引树」要求（否则节点会索引自己的存储）

### 3. 实测结果（索引 agentctl 工作区 6 个源码目录）

| 测试 | 结果 |
| --- | --- |
| `--dry-run` 零配置发现 | 3.5s 扫 1014 文件，自动忽略 813 垃圾文件/30 目录，推断 32 个数据集 |
| `autoindex` 正式索引 | 6 目录（agentctl/tests/configs/scripts/progress/tools，各独立 `--prefix`）共 ~700 记录；tree-sitter 抽出 185 个符号带行号；代码为「整文件记录 + 符号数组 + def 级段落」混合粒度 |
| `xerj def capture` | **精确命中** `appconfig.py:168`，带函数签名与全文件符号表 |
| BM25 `search "atomic write"` | 正常返回 file:line+评分；真身 `discovery/storage.py:75` 只排第 4（纯词法） |
| 语义查询（ES `semantic`） | 默认 embedder 为**离线词法哈希**，区分度弱（分数 0.59–0.62 挤在一起），同样第 4 |
| bool 混合（match+semantic should） | `storage.py` 升至第 2，实用解法 |
| ES API 兼容 | `_cat/indices`、`_search`、terms 聚合、`q=` 全通；**RRF `retriever` 语法不支持**（兼容是 ES 子集） |
| `batch-search` | 3/3 命中；identifier 精确查询（`name=capture`）直接给出 def；hit 含 `citation.ax_locator`（如 `code:101:_reg_write`） |
| Corpus Hub | `hub sync` 拉目录（502 语料）；`ask --corpus lz4 --def LZ4_MAX_INPUT_SIZE` 答出 `lz4/lib/lz4.h:214` + `value: 0x7E000000`，与官方文档逐字一致 |
| MCP stdio | `tools/list` 返回 22 工具（19 核心+3 hub）；`tools/call xerj_def` 全链路通，返回 ES JSON 带 `_passage` |

- **多仓库注意**：同一 prefix 下每个目录都推断成同名数据集 `ax-docs` 互相覆盖，引擎会拒写并给 remedy——每仓库独立 `--prefix` 即可
- 首次冲突遗留的重复索引 `ax-docs` 已 `DELETE` 清理

### 4. Corpus Hub 离线搬运技巧（慢网可用）

- `hub pull` 无镜像/本地文件参数，直连 releases 超时
- 变通：手动经镜像下载 `.hubpack.tar.zst` → 放入 `~\.xerj\hub\packs\<slug>\`（文件名 `<slug>-<pin8>.hubpack.tar.zst`，删除同目录 `<pin8>.lock`）→ 再 `xerj hub pull <slug>`，走本地文件并完整校验 sha256+签名（lz4 包 4,623,814 字节、sha256 `85446a51…89a2`，恢复为 4 索引 1702 定义）
- 语料目录（catalogue）本身 `xerj hub sync` 可正常拉取（1.7 MB）

### 5. 上游仓库克隆与同步（projects/xerj）

- 位置 `D:\App\agent-workspace\projects\xerj`，经 `ghfast.top` 镜像克隆（gh-proxy.com 首次尝试传输中途卡死，杀掉重试；`ls-remote` 实测两镜像 git 协议均可用）
- origin 保持官方 `https://github.com/xerj-org/xerj.git`；**仓库级 insteadOf** 把 GitHub 流量透明转到 `ghfast.top`（fetch/pull 提速；git 对象哈希校验兜底，不怕镜像篡改）。还原：`git config --local --unset url.https://ghfast.top/https://github.com/.insteadOf`
- 同步命令：`git -C D:\App\agent-workspace\projects\xerj pull`
- 克隆 HEAD：`4949bbd5f86aa2b97788a94d26a9d0c4ba80e4a3`（克隆时 main HEAD）
- 已入根 `.gitignore`（"# Upstream reference clones" 段）——**不入 agent-workspace 仓库**：170 MB 外部历史不该进工作区仓库（区别于 cloudmusic-r「整体入库」决策，那是用户自有工程）
- 尚未索引进 xerj 服务。可选参考编码：`xerj autoindex --prefix xerj projects/xerj`（服务运行时执行）

## 未验证 / 待办（下一步的活）

1. **MCP 接入 dsh**：官方 CLI 文档有现成 `cordis.patch.yml` 片段（`id: mcp-xerj`、stdio、`command: xerj`、`args: [mcp]`、`env.XERJ_URL`）。接入流程与 REA 同款（写 `C:\Users\E0465\.dsh\cordis.patch.yml`）。MCP host 可能不吃 PATH，建议 command 用绝对路径。待用户决策
2. **神经语义模式**：`--embed-mode neural` 需下载 ~90 MB 模型才启用真向量；内网/慢网用官方 air-gapped recipe 预置
3. **field report / feedback 自动提交**：CLI 反复建议自动提交 field report（发 GitHub PR）与 corpus feedback（发 hub.xerj.org）——本会话**一律未执行**；是否参与社区由用户决定（`xerj feedback` 手动）
4. **服务生命周期**：当前服务跑在会话后台任务里，会话结束即停；长期使用建议开机自启（任务计划）或按需手动启动（第 2 节命令）
5. **文档与二进制不一致小发现**：xerj.org CLI 参考页称「不存在 `xerj hub find`」，实际 rc.99 构建有该命令——以 `xerj hub pull --help` 实测输出为准

## 工作区 / 仓库状态

- 本任务仓库改动：`.gitignore`（+`projects/xerj/`）、`progress/progress.md`（概况「环境装机」行追加 XERJ、归档表新增行、最后更新时间）、本 handoff 文件
- 仓库内其他未提交改动**刻意隔离不碰**：`agentctl/bundle.py`（M）、`skills/serial-debug.7z`（未跟踪）
- xerj 克隆本体与 `~\xerj-data`、`~\.xerj` 均不入库
