# agent-teams-entry-toggle.ps1 - make AgentTeams panel entries toggleable (open AND collapse).
#
# Problem (diagnosis: progress/agent-teams-ui-conflict/diagnosis.md, team
# agent-teams-ui-conflict-fix): every AgentTeams entry (floating badge, team card
# "activity panel" button, session-header entry) can only OPEN the panel.
# - Floating mode: ActivityPanel's OPEN_PANEL_EVENT handler unconditionally does
#   setOpenOwner(activeSession)+setOpen(true) (lib/client.js onOpenPanel).
# - Tab mode: WorkspaceMonitor's OPEN_PANEL_EVENT handler unconditionally does
#   sidebar.openTab(TEAM_TAB_KIND). Re-clicking an entry never collapses anything.
#
# This patch adds toggle semantics inside the plugin's bundled client.js only:
#   A) Floating panel (current deployment default): when the panel is already
#      expanded for the active session and the event carries a teamId, collapse
#      it back to the badge (same setOpen(false)+setOpenOwner(void 0) as the
#      panel's own collapse button) instead of re-opening. Cross-session events
#      and detail-less events keep the original open behavior, so the historic
#      card "summon the panel" semantics are preserved.
#   B) Tab mode (fallback if the sidebar bridge ever activates): when the
#      sidebar is expanded and its active tab already is 'agent-teams', collapse
#      through the host's existing toggleExpanded(); on viewports < 1100px the
#      entry declines to open the grid-participating tab (avoids the <1024
#      left/right mutual-exclusion kick and the 1024-1100 center=400px squeeze).
#
# Pure string splice on the esbuild bundle: reversible, idempotent, re-runnable
# after plugin updates. Does NOT touch the /*dsh-at-scale:* zoom patch, the
# createTeamDiscovery auto-open guard, or any @deepseek-ai host package.
#
# Usage:
#   powershell -File agent-teams-entry-toggle.ps1          # apply
#   powershell -File agent-teams-entry-toggle.ps1 -Reset   # remove the patch
#
# Takes effect after a page refresh (F5). No dsh service restart needed.
param(
  [switch]$Reset,
  [string]$PluginLib = "$env:USERPROFILE\.dsh\profiles\web\node_modules\@nanmicoder\dsh-agent-teams\lib\client.js"
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path $PluginLib)) { throw "plugin client.js not found: $PluginLib" }

$MARKER = '/*dsh-at-entry-toggle:1*/'
$TAB_MARKER = '/*dsh-at-entry-toggle:tab-mode*/'

$c = [System.IO.File]::ReadAllText($PluginLib)
$nl = if ($c.Contains("`r`n")) { "`r`n" } else { "`n" }

# --- Site A: floating ActivityPanel onOpenPanel (unique anchor, see L3214-3238) ---
$anchorA = @(
"`t`t`t(0, react.useEffect)(() => {",
"`t`t`t`tconst onOpenPanel = (event) => {",
"`t`t`t`t`tconst activeSession = currentRef.current;",
"`t`t`t`t`tif (activeSession === void 0) return;",
"`t`t`t`t`tsetOpenOwner(activeSession);",
"`t`t`t`t`tsetOpen(true);"
) -join $nl

$patchA = @(
"/*dsh-at-entry-toggle:1*/ const atOpenMirrorRef = (0, react.useRef)({ open: false, owner: void 0 });",
"`t`t`t(0, react.useLayoutEffect)(() => {",
("`t`t`t`t" + "atOpenMirrorRef.current = { open, owner: openOwner };"),
"`t`t`t}, [open, openOwner]);",
"`t`t`t(0, react.useEffect)(() => {",
"`t`t`t`tconst onOpenPanel = (event) => {",
"`t`t`t`t`tconst activeSession = currentRef.current;",
"`t`t`t`t`tif (activeSession === void 0) return;",
"`t`t`t`t`tconst atToggle = atOpenMirrorRef.current.open && atOpenMirrorRef.current.owner === activeSession && event.detail?.teamId !== void 0;",
"`t`t`t`t`tif (atToggle) {",
"`t`t`t`t`t`tsetOpen(false);",
"`t`t`t`t`t`tsetOpenOwner(void 0);",
"`t`t`t`t`t} else {",
"`t`t`t`t`t`tsetOpenOwner(activeSession);",
"`t`t`t`t`t`tsetOpen(true);",
"`t`t`t`t`t}"
) -join $nl

# --- Site B: WorkspaceMonitor OPEN_PANEL_EVENT handler, Tab mode (unique anchor) ---
$anchorB = @(
"`t`t`t`t`tif (data?.teamId) state.remember(current, data);",
"`t`t`t`t`tsidebar.openTab(TEAM_TAB_KIND);"
) -join $nl

$patchB = @(
"`t`t`t`t`tif (data?.teamId) state.remember(current, data);",
"`t`t`t`t`t/*dsh-at-entry-toggle:tab-mode*/",
"`t`t`t`t`ttry {",
"`t`t`t`t`t`tif (sidebar.isExpanded() && sidebar.active()?.kind === TEAM_TAB_KIND) {",
"`t`t`t`t`t`t`tsidebar.toggleExpanded();",
"`t`t`t`t`t`t`treturn;",
"`t`t`t`t`t`t}",
"`t`t`t`t`t} catch (atToggleError) {}",
"`t`t`t`t`tif (window.innerWidth < 1100) return;",
"`t`t`t`t`tsidebar.openTab(TEAM_TAB_KIND);"
) -join $nl

# 1) strip any previously injected patch (exact inverse of the apply step), so
#    re-running is idempotent and partial states are repaired before applying.
$changed = $false
foreach ($pair in @(@($patchA, $anchorA), @($patchB, $anchorB))) {
  if ($c.Contains($pair[0])) {
    $c = $c.Replace($pair[0], $pair[1])
    $changed = $true
  }
}

if ($Reset) {
  if (-not $changed) { Write-Host '[reset] no entry-toggle patch present - nothing to do' }
  else {
    [System.IO.File]::WriteAllText($PluginLib, $c)
    Write-Host '[reset] entry-toggle patch removed - refresh the page (F5) to apply'
  }
  return
}

# 2) apply both sites, each anchor must occur exactly once
foreach ($site in @(
  @{ name = 'floating ActivityPanel onOpenPanel'; anchor = $anchorA; patch = $patchA },
  @{ name = 'WorkspaceMonitor OPEN_PANEL_EVENT (tab mode)'; anchor = $anchorB; patch = $patchB }
)) {
  $n = ([regex]::Matches($c, [regex]::Escape($site.anchor))).Count
  if ($n -ne 1) { throw "anchor for $($site.name) found $n times (expected 1) - the plugin was updated and this patch needs a review" }
  $c = $c.Replace($site.anchor, $site.patch)
}

# 3) sanity: exactly one marker per site, then write
$markerCount = ([regex]::Matches($c, [regex]::Escape($MARKER))).Count
$tabMarkerCount = ([regex]::Matches($c, [regex]::Escape($TAB_MARKER))).Count
if ($markerCount -ne 1 -or $tabMarkerCount -ne 1) { throw "unexpected marker counts after patch (entry-toggle:$markerCount tab-mode:$tabMarkerCount, expected 1/1); aborting" }
[System.IO.File]::WriteAllText($PluginLib, $c)
Write-Host '[entry-toggle] AgentTeams entries now toggle open/collapse - refresh the page (F5) to see it'
Write-Host '[entry-toggle] undo with -Reset'
