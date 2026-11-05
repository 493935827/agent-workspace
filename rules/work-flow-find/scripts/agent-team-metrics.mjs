#!/usr/bin/env node
/**
 * agent-team-metrics.mjs — AgentTeams 运行性能统一指标（跟踪用）
 *
 * 用法：node scripts/agent-team-metrics.mjs <team.json> [more.json ...]
 * 输出：逐任务 等待/活跃 窗口、总量与利用率、并发直方图、规则违规启发式检查
 *       （质量门降级、单人长尾、串行头部、评审绑全局门）。
 *
 * 指标口径：start = max(createdAt, 依赖完成时刻)；active = updatedAt - start；
 *           wait  = start - createdAt。时间单位分钟。基线：nr-parallel-trial
 *           96.5m 墙钟 / 159.6 活跃人·分 / 15% 利用率（2026-11-03）。
 */
import { readFileSync } from "node:fs";

const files = process.argv.slice(2);
if (files.length === 0) {
  console.error("usage: node scripts/agent-team-metrics.mjs <team.json> [...]");
  process.exit(1);
}

for (const file of files) {
  const t = JSON.parse(readFileSync(file, "utf8"));
  const name = file.split(/[\\/]/).slice(-2, -1)[0] || file;
  const tasks = t.tasks ?? [];
  const byId = Object.fromEntries(tasks.map((k) => [k.id, k]));
  const t0 = Math.min(...tasks.map((k) => k.createdAt));

  const rows = tasks.map((k) => {
    const depReady =
      k.dependencies?.length > 0
        ? Math.max(...k.dependencies.map((d) => byId[d]?.updatedAt ?? 0))
        : t0;
    const start = Math.max(k.createdAt, depReady);
    return {
      id: k.id,
      who: k.assignee ?? "-",
      kind: k.kind ?? "(none)",
      start: (start - t0) / 60000,
      end: (k.updatedAt - t0) / 60000,
      wait: (start - k.createdAt) / 60000,
      active: (k.updatedAt - start) / 60000,
      deps: (k.dependencies ?? []).join(","),
      subject: k.subject ?? "",
    };
  });
  rows.sort((a, b) => a.start - b.start);

  const wall = Math.max(...rows.map((r) => r.end)) - Math.min(...rows.map((r) => r.start));
  const activeMin = rows.reduce((s, r) => s + r.active, 0);
  const waitMin = rows.reduce((s, r) => s + r.wait, 0);
  const nMembers = (t.members ?? []).length || new Set(rows.map((r) => r.who)).size;
  const util = (activeMin / (nMembers * wall)) * 100;

  console.log(`\n=== ${name} ===`);
  console.log(
    `wall=${wall.toFixed(1)}m  tasks=${tasks.length}  members=${nMembers}  active=${activeMin.toFixed(1)} 人·分  wait=${waitMin.toFixed(1)} 人·分  utilization=${util.toFixed(1)}%  (基线 96.5m/159.6/15%)`
  );
  if (wall > 600)
    console.log(
      `  [caveat] wall=${wall.toFixed(0)}m 异常长：updatedAt-createdAt 口径含跨会话/人工等待，utilization 仅作参考，看逐任务窗口`
    );
  console.log("id   who         kind            start+   end+  wait  active  deps");
  for (const r of rows) {
    console.log(
      r.id.padEnd(4) +
        String(r.who).padEnd(11) +
        r.kind.padEnd(15) +
        r.start.toFixed(1).padStart(7) +
        r.end.toFixed(1).padStart(7) +
        r.wait.toFixed(1).padStart(6) +
        r.active.toFixed(1).padStart(7) +
        "  " +
        r.deps
    );
  }

  console.log("fleet concurrency per 5-min bucket (按任务窗口计，桶边界短任务可能高估，逐任务表为准):");
  for (let b = 0; b < Math.ceil(wall / 5) * 5; b += 5) {
    const n = rows.filter((r) => r.start < b + 5 && r.end > b).length;
    if (n > 0) console.log(`${String(b).padStart(3)}-${String(b + 5).padStart(3)}m: ${n} active  ${"#".repeat(n)}`);
  }

  // ---- 规则违规启发式 ----
  console.log("rule checks:");
  const gateWords = /(评审|review|验证|verification|核查|复核)/i;
  const downgraded = rows.filter((r) => r.kind === "(none)" && gateWords.test(r.subject));
  for (const r of downgraded)
    console.log(`  [gate-downgrade] ${r.id} "${r.subject.slice(0, 30)}" kind 缺失——验证/评审必须 kind+objective+acceptance，否则无质量门`);
  const tail = rows.filter((r) => r.kind === "implementation" && r.end >= wall - 20 && r.active >= 15);
  for (const r of tail)
    console.log(`  [tail] ${r.id} 单人实现长尾 ${r.active.toFixed(1)}m 收口（检查是否应拆片并行）`);
  const firstByMember = {};
  for (const r of rows) {
    if (!(r.who in firstByMember) || r.start < firstByMember[r.who].start) firstByMember[r.who] = r;
  }
  const coldLanes = Object.entries(firstByMember)
    .filter(([, r]) => /^(implementation|verification)$/.test(r.kind) && r.start > 10);
  for (const [, r] of coldLanes)
    console.log(`  [head] ${r.who} 首个 ${r.kind} 任务 +${r.start.toFixed(1)}m 才开工——该轨未派 warmup 预热（>10m 阈值；架构师/评审/集成晚开工属设计）`);
  const globalGates = new Set(
    rows
      .filter((r) => r.kind === "verification" && r.deps.split(",").filter(Boolean).length >= 3)
      .map((r) => r.id)
  );
  const reviewsOnGlobalGate = rows.filter((r) =>
    r.kind === "review" && r.deps.split(",").some((d) => globalGates.has(d))
  );
  for (const r of reviewsOnGlobalGate)
    console.log(`  [review-global-gate] ${r.id} review 依赖全局验证门 ${r.deps}——应绑定单轨即完即评`);
  if (downgraded.length === 0 && tail.length === 0 && reviewsOnGlobalGate.length === 0)
    console.log("  ok - 未命中启发式违规");
}
