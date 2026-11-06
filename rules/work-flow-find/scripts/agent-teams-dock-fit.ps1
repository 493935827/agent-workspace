# agent-teams-dock-fit.ps1 - keep the AgentTeams floating panel inside the viewport
# when a UI zoom (agent-teams-ui-scale.ps1) is active.
#
# Problem (T3 verification.md section 4, finding 2): the panel is positioned in
# design pixels (dock: translate3d(x,64) with right edge at viewport-18;
# compact: 12px inset), but the injected `.aYQbCq_panel{zoom:Z}` scales the
# element's layout box AND its transform offsets by Z from the viewport origin,
# so the *visual* box is (x+w)*Z wide - at 1280 with Z=1.35 only ~100px of the
# docked panel stayed on screen (title clipped); the 960 compact panel (936
# logical px) overflowed the same way.
#
# Fix: divide the panel's applied style (translate3d x/y, width, height,
# max-height) by Z at the single DOM-apply point (panelStyle), so the browser's
# zoom multiplies it back to exactly the designed visual box. Everything else
# that consumes `geometry` (notably the --agent-teams-panel-shift conversation
# concession and gesture layout math) keeps design pixels on purpose.
#
# Z is read at runtime from the CSS variable `--dsh-at-zoom` (declared by the
# extended agent-teams-ui-scale.ps1); it is never hardcoded here. When the
# variable is absent (scale patch not applied), Z=1 and the division is a no-op:
# zero behavior change.
#
# Pure string splice on the esbuild bundle: reversible, idempotent, re-runnable
# after plugin updates. Does NOT touch any @deepseek-ai host package, the
# /*dsh-at-scale:* block, the /*dsh-at-entry-toggle:* patches, or the
# createTeamDiscovery guard.
#
# Usage:
#   powershell -File agent-teams-dock-fit.ps1          # apply
#   powershell -File agent-teams-dock-fit.ps1 -Reset   # remove the patch
#
# Takes effect after a page refresh (F5). No dsh service restart needed.
param(
  [switch]$Reset,
  [string]$PluginLib = "$env:USERPROFILE\.dsh\profiles\web\node_modules\@nanmicoder\dsh-agent-teams\lib\client.js"
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path $PluginLib)) { throw "plugin client.js not found: $PluginLib" }

$MARKER = '/*dsh-at-dock-fit:1*/'
$STYLE_MARKER = '/*dsh-at-dock-fit:style*/'

$c = [System.IO.File]::ReadAllText($PluginLib)
$nl = if ($c.Contains("`r`n")) { "`r`n" } else { "`n" }

# --- Site 1: runtime zoom reader, inserted right before the ActivityPanel component ---
$anchorHelper = @(
("`t`t" + 'function ActivityPanel({ sessionsList, modelDirectories, openMember, t, conversationVisible = true }) {')
) -join $nl

$patchHelper = @(
("`t`t" + '/*dsh-at-dock-fit:1*/ function atPanelZoomFactor() {'),
("`t`t`t" + 'try {'),
("`t`t`t`t" + 'const raw = getComputedStyle(document.documentElement).getPropertyValue("--dsh-at-zoom").trim();'),
("`t`t`t`t" + 'const parsed = Number.parseFloat(raw);'),
("`t`t`t`t" + 'return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;'),
("`t`t`t" + '} catch (atZoomError) {'),
("`t`t`t`t" + 'return 1;'),
("`t`t`t" + '}'),
("`t`t" + '}'),
("`t`t" + 'function ActivityPanel({ sessionsList, modelDirectories, openMember, t, conversationVisible = true }) {')
) -join $nl

# --- Site 2: panelStyle - the single point where geometry reaches the DOM ---
$anchorStyle = @(
("`t`t`t" + 'const autoHeight = panelUsesAutoHeight(geometry, bounds);'),
("`t`t`t" + 'const panelStyle = {'),
("`t`t`t`t" + 'width: geometry.width,'),
("`t`t`t`t" + 'height: autoHeight ? "auto" : geometry.height,'),
("`t`t`t`t" + 'maxHeight: panelMaximumHeight(geometry, bounds),'),
("`t`t`t`t" + 'transform: `translate3d(${geometry.x}px, ${geometry.y}px, 0)`'),
("`t`t`t" + '};')
) -join $nl

$patchStyle = @(
("`t`t`t" + 'const autoHeight = panelUsesAutoHeight(geometry, bounds);'),
("`t`t`t" + '/*dsh-at-dock-fit:style*/ const atZoom = atPanelZoomFactor();'),
("`t`t`t" + 'const panelStyle = {'),
("`t`t`t`t" + 'width: geometry.width / atZoom,'),
("`t`t`t`t" + 'height: autoHeight ? "auto" : geometry.height / atZoom,'),
("`t`t`t`t" + 'maxHeight: panelMaximumHeight(geometry, bounds) / atZoom,'),
("`t`t`t`t" + 'transform: `translate3d(${geometry.x / atZoom}px, ${geometry.y / atZoom}px, 0)`'),
("`t`t`t" + '};')
) -join $nl

# 1) strip any previously injected patch (exact inverse of the apply step), so
#    re-running is idempotent and partial states are repaired before applying.
$changed = $false
foreach ($pair in @(@($patchHelper, $anchorHelper), @($patchStyle, $anchorStyle))) {
  if ($c.Contains($pair[0])) {
    $c = $c.Replace($pair[0], $pair[1])
    $changed = $true
  }
}

if ($Reset) {
  if (-not $changed) { Write-Host '[reset] no dock-fit patch present - nothing to do' }
  else {
    [System.IO.File]::WriteAllText($PluginLib, $c)
    Write-Host '[reset] dock-fit patch removed - refresh the page (F5) to apply'
  }
  return
}

# 2) apply both sites, each anchor must occur exactly once
foreach ($site in @(
  @{ name = 'atPanelZoomFactor helper (before ActivityPanel)'; anchor = $anchorHelper; patch = $patchHelper },
  @{ name = 'ActivityPanel panelStyle'; anchor = $anchorStyle; patch = $patchStyle }
)) {
  $n = ([regex]::Matches($c, [regex]::Escape($site.anchor))).Count
  if ($n -ne 1) { throw "anchor for $($site.name) found $n times (expected 1) - the plugin was updated and this patch needs a review" }
  $c = $c.Replace($site.anchor, $site.patch)
}

# 3) sanity: exactly one marker per site, then write
$markerCount = ([regex]::Matches($c, [regex]::Escape($MARKER))).Count
$styleMarkerCount = ([regex]::Matches($c, [regex]::Escape($STYLE_MARKER))).Count
if ($markerCount -ne 1 -or $styleMarkerCount -ne 1) { throw "unexpected marker counts after patch (dock-fit:$markerCount style:$styleMarkerCount, expected 1/1); aborting" }
[System.IO.File]::WriteAllText($PluginLib, $c)
Write-Host '[dock-fit] panel geometry now compensated by 1/zoom - refresh the page (F5) to see it'
Write-Host '[dock-fit] needs agent-teams-ui-scale.ps1 applied for a zoom > 1; without it this patch is a no-op (Z=1). undo with -Reset'
