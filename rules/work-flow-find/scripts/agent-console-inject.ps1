<#
.SYNOPSIS
  Agent Console 注入补丁：在 @nanmicoder/dsh-agent-teams 的客户端 bundle 里
  1) 注册右侧栏 "Agent Console" Tab（iframe 内嵌 http://127.0.0.1:5731 仪表盘）
  2) 注册会话头 "Agent Console" 按钮（点击打开该 Tab）
  3) 监听 postMessage 实现点击会话卡跳转到 DSH 对应对话
     （普通会话 sessions.open；子代理走 openMember 父子导航；GUI 存在
      "session-xxx" 与裸 uuid 两种 id 格式，失败自动换格式重试）
  4) 全局浮动入口（不依赖会话）：右下角常驻圆形按钮 #agent-console-fab
     + 徽标 #agent-console-fab-badge（15s 轮询 5731/api/snapshot，
     待审批(≤72h)+暂停/需介入+悬空失败（未读不计）——与面板 computeAttention 逐条镜像）
     + 点击开右侧滑出面板 #agent-console-overlay
     （内嵌同源 iframe，标题栏"关闭"按钮，Esc 关闭）
.DESCRIPTION
  - 幂等：重复运行标记恰好 1 处（先剥离自身旧注入再注入）
  - 只改客户端 bundle，F5 刷新即生效，不重启任何 dsh/node 服务
  - HMR watcher（dsh-client-hmr）会在 ~500ms 内自动发现文件变更并更新服务端
    bundle rev，随后刷新页面即可加载新字节
  - 注意：若有其他 agent 并发修改同一 bundle，可能发生读改写竞态；被覆盖时重跑
    本脚本即可。首次运行自动备份原始文件（*.pre-console.bak）
.EXAMPLE
  .\agent-console-inject.ps1          # 注入
  .\agent-console-inject.ps1 -Reset   # 还原（从 .pre-console.bak 恢复）
#>
param(
  [switch]$Reset,
  [string]$Target = "C:\Users\E0465\.dsh\profiles\web\node_modules\@nanmicoder\dsh-agent-teams\lib\client.js"
)
$ErrorActionPreference = 'Stop'

$MARK_START = '/*dsh-agent-console:v1*/'
$MARK_END = '/*dsh-agent-console:end*/'
$ANCHOR = '}, AgentTeamsCard));'
$BACKUP = "$Target.pre-console.bak"

if (-not (Test-Path $Target)) { Write-Error "target not found: $Target"; exit 1 }
$raw = [System.IO.File]::ReadAllText($Target)

# 1) 剥离旧注入（非贪心 + 贪心双保险，处理历史嵌套残留）
$stripped = [regex]::Replace($raw, '(?s)' + [regex]::Escape($MARK_START) + '.*?' + [regex]::Escape($MARK_END), '')
$stripped = [regex]::Replace($stripped, '(?s)' + [regex]::Escape($MARK_START) + '.*' + [regex]::Escape($MARK_END), '')

if ($Reset) {
  if (-not (Test-Path $BACKUP)) { Write-Host 'no backup found; cannot reset'; exit 1 }
  [System.IO.File]::WriteAllText($Target, ([System.IO.File]::ReadAllText($BACKUP)), [System.Text.UTF8Encoding]::new($false))
  Write-Host '[agent-console] restored from backup. F5 to apply.'
  exit 0
}

# 2) 首次打补丁前备份
if (-not (Test-Path $BACKUP)) {
  [System.IO.File]::WriteAllText($BACKUP, $raw, [System.Text.UTF8Encoding]::new($false))
  Write-Host "[agent-console] backup saved: $BACKUP"
}

# 3) 注入块（字面量）
$inject = @'
/*dsh-agent-console:v1*/
			try {
				window.__agentConsoleCtx = ctx;
				const AC_TAB_ID = "@agent-console/pane";
				const AC_TAB_KIND = "agent-console";
				const AC_IFRAME_SRC = "http://127.0.0.1:5731/?embed=1";
				const AC_ORIGIN_RE = /^https?:\/\/(127\.0\.0\.1|localhost):5731$/;
				const AgentConsoleIcon = () => (0, react_jsx_runtime.jsxs)("svg", {
					width: "16", height: "16", viewBox: "0 0 24 24", "aria-hidden": true,
					fill: "none", stroke: "currentColor", strokeWidth: 1.8,
					strokeLinecap: "round", strokeLinejoin: "round",
					children: [
						(0, react_jsx_runtime.jsx)("rect", { x: "3", y: "4", width: "18", height: "14", rx: "2" }),
						(0, react_jsx_runtime.jsx)("path", { d: "M7 9l3 3-3 3" }),
						(0, react_jsx_runtime.jsx)("path", { d: "M13 15h4" })
					]
				});
				const acNavigate = (payload) => {
					try {
						const child = String((payload && payload.sessionId) || "");
						if (!child) return;
						const parent = payload.parentSessionId ? String(payload.parentSessionId) : "";
						if (parent && typeof openMember === "function") {
							openMember(parent, child);
						} else if (ctx.sessions && typeof ctx.sessions.open === "function") {
							try {
								ctx.sessions.open(child);
							} catch (errFormat) {
								/* GUI 会话列表存在两种 id 格式（session-xxx 与裸 uuid），换格式重试 */
								const bare = child.startsWith("session-") ? child.slice(8) : "session-" + child;
								ctx.sessions.open(bare);
							}
							try { if (ctx.layout && typeof ctx.layout.selectPanel === "function") ctx.layout.selectPanel(null); } catch (_) {}
						} else {
							console.warn("agent-console: no session navigation service available for", child);
							return;
						}
						/* 用户指令：跳转后不自动收起右栏（原 isExpanded/toggleExpanded 收起逻辑整段删除），面板保持打开由用户自行关闭 */
					} catch (error) { console.warn("agent-console: navigate failed", error); }
				};
				const acMessageHandler = (event) => {
					if (!AC_ORIGIN_RE.test(String(event.origin || ""))) return;
					const data = event.data;
					if (!data || data.source !== "agent-console" || data.type !== "open-session") return;
					acNavigate(data);
				};
				if (window.__agentConsoleNavigate) window.removeEventListener("message", window.__agentConsoleNavigate);
				window.__agentConsoleNavigate = acMessageHandler;
				window.addEventListener("message", acMessageHandler);
				/* 全局浮动入口：不依赖会话，主页/会话内常驻；徽标 = 注意力规则紧凑版（待审批≤72h + halted/escalated + 悬空失败；未读不计），与面板 computeAttention 互为镜像 */
				if (!document.getElementById("agent-console-fab")) {
					const acFab = document.createElement("button");
					acFab.id = "agent-console-fab";
					acFab.title = "Agent Console";
					acFab.setAttribute("aria-label", "Agent Console");
					acFab.style.cssText = "position:fixed;right:14px;bottom:18px;z-index:2147483000;width:38px;height:38px;border-radius:50%;border:1px solid #334155;background:rgba(15,23,42,.85);color:#22C55E;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 16px rgba(0,0,0,.45);padding:0;";
					acFab.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="14" rx="2"></rect><path d="M7 9l3 3-3 3"></path><path d="M13 15h4"></path></svg><span id="agent-console-fab-badge" style="position:absolute;top:-4px;right:-4px;min-width:16px;height:16px;border-radius:8px;background:#DC2626;color:#fff;font:600 10px/16px Consolas,monospace;text-align:center;padding:0 4px;display:none;box-sizing:border-box;"></span>';
					document.body.appendChild(acFab);
					const acBadge = acFab.querySelector("#agent-console-fab-badge");
					const acRefreshBadge = () => {
						try {
							fetch("http://127.0.0.1:5731/api/snapshot").then((r) => r.json()).then((s) => {
								/* 徽标 = 注意力项计数，与面板 app.js computeAttention 逐条镜像（R1/F-1 对齐）。
								① 待审批：awaiting_review 且 !(createdAt && now-createdAt>72h)（超时沉底）
								②③ halted / escalated（archived / phase==='ended' 团队外层排除）
								④ 悬空失败充要条件 = !hasSuccessor(任意状态任务依赖它) && !superseded(创建序在其后的任务存在 completed)
								   —— 忙团队（in_progress/pending）不再整体跳过：面板仅降级 warn，计数口径一致；未读不计。
								每类各计 1 项，同团队多类可叠加（与面板 items 计数一致；面板 dismissFilter 手动忽略为
								用户本地态，FAB 不感知）。 */
								const now = Date.now();
								const teams = (s && Array.isArray(s.teams)) ? s.teams : [];
								let n = 0;
								for (const t of teams) {
									if (!t || t.archived || t.phase === "ended") continue;
									if (t.planReviewState === "awaiting_review" && !(t.createdAt && now - Number(t.createdAt) > 259200000)) n++;
									if (t.phase === "halted") n++;
									if (t.phase === "escalated") n++;
									const tasks = Array.isArray(t.tasks) ? t.tasks : [];
									let dangling = 0;
									for (let fi = 0; fi < tasks.length; fi++) {
										const f = tasks[fi];
										if (!f || f.status !== "failed") continue;
										let hasSuccessor = false;
										for (const k of tasks) { if (k && k !== f && Array.isArray(k.dependencies) && k.dependencies.indexOf(f.id) !== -1) { hasSuccessor = true; break; } }
										if (hasSuccessor) continue;
										let superseded = false;
										for (let ki = fi + 1; ki < tasks.length; ki++) { if (tasks[ki] && tasks[ki].status === "completed") { superseded = true; break; } }
										if (!superseded) dangling++;
									}
									if (dangling > 0) n++;
								}
								acBadge.textContent = n > 0 ? String(n) : "";
								acBadge.style.display = n > 0 ? "block" : "none";
							}).catch(() => {});
						} catch (_) {}
					};
					acRefreshBadge();
					if (window.__agentConsoleFabTimer) clearInterval(window.__agentConsoleFabTimer);
					window.__agentConsoleFabTimer = setInterval(acRefreshBadge, 15000);
					let acOverlay = null;
					const acOpenOverlay = () => {
						if (acOverlay) return;
						acOverlay = document.createElement("div");
						acOverlay.id = "agent-console-overlay";
						acOverlay.style.cssText = "position:fixed;top:0;right:0;bottom:0;width:min(640px,94vw);z-index:2147483001;background:#0F172A;border-left:1px solid #334155;box-shadow:-12px 0 40px rgba(0,0,0,.5);display:flex;flex-direction:column;";
						const acBar = document.createElement("div");
						acBar.style.cssText = "display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid #334155;color:#F8FAFC;font:600 13px/1.4 'Segoe UI','Microsoft YaHei',sans-serif;box-sizing:border-box;";
						const acTitle = document.createElement("span");
						acTitle.textContent = "Agent Console";
						acTitle.style.cssText = "flex:1;";
						const acClose = document.createElement("button");
						acClose.textContent = "关闭";
						acClose.setAttribute("aria-label", "关闭 Agent Console");
						acClose.style.cssText = "background:transparent;border:1px solid #334155;border-radius:6px;color:#CBD5E1;cursor:pointer;font:12px 'Segoe UI','Microsoft YaHei',sans-serif;padding:3px 10px;";
						acClose.addEventListener("click", () => { if (acOverlay) { acOverlay.remove(); acOverlay = null; } });
						acBar.appendChild(acTitle);
						acBar.appendChild(acClose);
						const acFrame = document.createElement("iframe");
						acFrame.src = AC_IFRAME_SRC;
						acFrame.title = "Agent Console Overlay";
						acFrame.style.cssText = "flex:1 1 auto;width:100%;border:0;display:block;background:#0F172A;";
						acOverlay.appendChild(acBar);
						acOverlay.appendChild(acFrame);
						document.body.appendChild(acOverlay);
					};
					acFab.addEventListener("click", () => { if (acOverlay) { acOverlay.remove(); acOverlay = null; } else { acOpenOverlay(); } });
					if (window.__agentConsoleEscHandler) window.removeEventListener("keydown", window.__agentConsoleEscHandler);
					window.__agentConsoleEscHandler = (e) => { if (e.key === "Escape") { const ov = document.getElementById("agent-console-overlay"); if (ov) ov.remove(); } };
					window.addEventListener("keydown", window.__agentConsoleEscHandler);
				}
				ctx.inject(["sidebarRight", "sidebarRightTabs"], (native) => {
					try {
						acSidebar = native.sidebarRight || acSidebar;
						native.effect(() => native.sidebarRightTabs.register({
							id: AC_TAB_ID, kind: AC_TAB_KIND,
							title: () => "Agent Console", icon: AgentConsoleIcon
						}));
						native.slots.inject("sidebar.right.pane.tab", () => {
							const dispose = native.slots.register({
								name: "sidebar.right.pane.tab",
								key: AC_TAB_ID,
								inject: () => ({})
							}, function AgentConsolePane() {
								return (0, react_jsx_runtime.jsx)("div", {
									style: { height: "100%", minHeight: "420px", display: "flex", flexDirection: "column", background: "#0F172A" },
									children: (0, react_jsx_runtime.jsx)("iframe", {
										src: AC_IFRAME_SRC, title: "Agent Console",
										style: { flex: "1 1 auto", width: "100%", border: "0", display: "block" }
									})
								});
							});
							return () => { try { dispose(); } catch (_) {} };
						});
						native.effect(() => native.slots.inject("conversation.session.header.actions", () => native.slots.register({
							name: "conversation.session.header.actions",
							id: "agent-console-entry",
							order: 60,
							inject: () => ({})
						}, function AgentConsoleEntry() {
							return (0, react_jsx_runtime.jsx)("button", {
								title: "Agent Console",
								"aria-label": "Agent Console",
								style: { background: "transparent", border: "0", cursor: "pointer", color: "inherit", display: "inline-flex", alignItems: "center", justifyContent: "center", padding: "4px", borderRadius: "6px" },
								onClick: () => {
									try {
										if (acSidebar && typeof acSidebar.openTab === "function") acSidebar.openTab(AC_TAB_KIND);
										else if (acSidebar && typeof acSidebar.toggleExpanded === "function") acSidebar.toggleExpanded();
									} catch (e) { console.warn("agent-console: openTab failed", e); }
								},
								children: AgentConsoleIcon()
							});
						})));
					} catch (error) { console.warn("agent-console: register failed", error); }
				});
			} catch (error) { console.warn("agent-console bootstrap failed", error); }
			/*dsh-agent-console:end*/
'@

# 4) 插入到锚点之后（apply 函数体尾部）；锚点在文件尾部，并发写入时可能撕裂读，重试 3 次
if (-not (Test-Path $BACKUP)) { Write-Error 'backup missing'; exit 1 }
$lf = [char]10
$block = ($inject -replace "`r`n", $lf).TrimEnd() + $lf
$patched = $null
for ($attempt = 1; $attempt -le 3; $attempt++) {
  if ($stripped.Contains($ANCHOR)) { break }
  Write-Host "[agent-console] anchor missing (attempt $attempt) — file may be mid-write by another writer; retrying read..."
  Start-Sleep -Milliseconds 800
  $fresh = [System.IO.File]::ReadAllText($Target)
  $fresh = [regex]::Replace($fresh, '(?s)' + [regex]::Escape($MARK_START) + '.*?' + [regex]::Escape($MARK_END), '')
  $fresh = [regex]::Replace($fresh, '(?s)' + [regex]::Escape($MARK_START) + '.*' + [regex]::Escape($MARK_END), '')
  $stripped = $fresh
}
if (-not $stripped.Contains($ANCHOR)) { Write-Error 'anchor not found after retries; plugin bundle layout changed?'; exit 1 }
$patched = $stripped.Replace($ANCHOR, $ANCHOR + $lf + $block)

# 5) 写回（无 BOM UTF-8 + LF）
[System.IO.File]::WriteAllText($Target, $patched, [System.Text.UTF8Encoding]::new($false))

# 6) 真实磁盘校验/同步 + 语法门
#    说明：agent 会话的 .NET 文件 I/O 可能被执行沙箱虚拟化成会话私有副本（对 client.js 的
#    写入不落真实盘、读到的也可能是过期副本），而 node 子进程始终读写真实磁盘。因此最终
#    以 node 复核实盘 marker；若实盘 marker != 1 或实盘内容与本脚本的 $block 不一致，则在
#    实盘上重放同一套「剥离 + 锚点插入」逻辑（同一 $block 字节、幂等），保证 ps1 与磁盘一致。
$acSyncCjs = Join-Path $env:TEMP ("agent-console-sync-{0}.cjs" -f $PID)
$acBlockJs = Join-Path $env:TEMP ("agent-console-block-{0}.js" -f $PID)
$acSyncSrc = @'
const fs = require("fs");
const target = process.argv[2];
const blockPath = process.argv[3];
const MARK_START = "/*dsh-agent-console:v1*/";
const MARK_END = "/*dsh-agent-console:end*/";
const ANCHOR = "}, AgentTeamsCard));";
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const reNonGreedy = new RegExp(esc(MARK_START) + "[\\s\\S]*?" + esc(MARK_END) + "[\\s]*");
const reGreedy = new RegExp(esc(MARK_START) + "[\\s\\S]*" + esc(MARK_END) + "[\\s]*");
const stripAll = (s) => s.replace(reNonGreedy, "").replace(reGreedy, "");
const countMarkers = (s) => s.split(MARK_START).length - 1;
const sleep = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
const result = { applied: false, markers: 0, markersBefore: 0, retried: false, error: null };
try {
  let raw = fs.readFileSync(target, "utf8");
  result.markersBefore = countMarkers(raw);
  let stripped = stripAll(raw);
  for (let attempt = 1; attempt <= 3 && !stripped.includes(ANCHOR); attempt++) {
    result.retried = true;
    sleep(300);
    raw = fs.readFileSync(target, "utf8");
    stripped = stripAll(raw);
  }
  if (!stripped.includes(ANCHOR)) throw new Error("anchor not found on real disk after retries");
  if (countMarkers(stripped) !== 0) throw new Error("strip left markers on real disk");
  const block = fs.readFileSync(blockPath, "utf8").replace(/\r\n/g, "\n").trimEnd() + "\n";
  const patched = stripped.replace(ANCHOR, () => ANCHOR + "\n" + block);
  if (patched !== raw) {
    fs.writeFileSync(target, patched, "utf8");
    result.applied = true;
  }
  result.markers = countMarkers(fs.readFileSync(target, "utf8"));
} catch (e) {
  result.error = String((e && e.message) || e);
  try { result.markers = countMarkers(fs.readFileSync(target, "utf8")); } catch (_) { result.markers = -1; }
}
console.log(JSON.stringify(result));
'@
[System.IO.File]::WriteAllText($acSyncCjs, $acSyncSrc, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($acBlockJs, $block, [System.Text.UTF8Encoding]::new($false))
$acSyncJson = node $acSyncCjs $Target $acBlockJs
Remove-Item $acBlockJs -ErrorAction SilentlyContinue
$acSync = $acSyncJson | ConvertFrom-Json
$markerCount = [int]$acSync.markers
node --check $Target
if ($LASTEXITCODE -ne 0) { Write-Error 'node --check failed on patched bundle!'; exit 1 }
Write-Host "[agent-console] patch applied OK (marker on disk x$markerCount, node real-disk sync applied=$($acSync.applied) before=$($acSync.markersBefore)). F5 the DSH page to load."
if ($markerCount -ne 1) { Write-Warning "expected exactly 1 marker on real disk — re-run this script if a concurrent writer clobbered it." }
