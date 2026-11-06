# agent-teams-ui-scale.ps1 - scale up the AgentTeams activity panel UI.
#
# The plugin ships no UI-scale setting and its panel fonts are fixed at 8-12px.
# This patch injects a CSS `zoom` rule for the panel + badge into the plugin's
# bundled client.js (the CSS lives inline in that file). Pure string splice:
# reversible, and re-runnable after plugin updates.
#
# Since the dock-fit patch (agent-teams-dock-fit.ps1), the injected block also
# declares `html{--dsh-at-zoom:<scale>}`: the machine-readable mirror of the
# zoom value that the dock-fit JS patch reads at runtime to compensate the
# panel's translate3d/width/height by 1/Z (so the panel's *visual* box stays at
# its designed docked/compact position instead of overflowing the viewport).
# The zoom rule itself stays a literal (not var()) so the visual scaling cannot
# depend on custom-property support; the literal and the variable are emitted
# from the same $Scale so they can never drift apart.
#
# Usage:
#   powershell -File agent-teams-ui-scale.ps1                # apply 1.35x
#   powershell -File agent-teams-ui-scale.ps1 -Scale 1.6     # apply custom scale
#   powershell -File agent-teams-ui-scale.ps1 -Reset         # remove the patch
#
# After changing the scale: refresh the page (F5). If nothing changes,
# hard-refresh (Ctrl+F5); worst case restart the web profile:
#   powershell -File C:\Users\E0465\.dsh\dsh-web-restart.ps1
param(
  [double]$Scale = 1.35,
  [switch]$Reset,
  [string]$PluginLib = "$env:USERPROFILE\.dsh\profiles\web\node_modules\@nanmicoder\dsh-agent-teams\lib\client.js"
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path $PluginLib)) { throw "plugin client.js not found: $PluginLib" }

$scaleStr = $Scale.ToString([System.Globalization.CultureInfo]::InvariantCulture)

$c = [System.IO.File]::ReadAllText($PluginLib)

# 1) strip any previously injected scale rule - legacy format (zoom literal only)
#    and current format (with the html{--dsh-at-zoom:...} variable declaration).
#    Non-greedy to the marker; both variants end at /*dsh-at-scale:<n>*/
$before = $c
$c = [regex]::Replace($c, '@media screen\{(?:html\{--dsh-at-zoom:[0-9.]+\})?\.aYQbCq_panel.*?/\*dsh-at-scale:[0-9.]+\*/', '', [System.Text.RegularExpressions.RegexOptions]::Singleline)

if ($Reset) {
  if ($c -eq $before) { Write-Host '[reset] no patch present - nothing to do' }
  else {
    [System.IO.File]::WriteAllText($PluginLib, $c)
    Write-Host '[reset] scale patch removed - refresh the page (F5) to apply'
  }
  return
}

# 2) inject after the unique ActivityPanel CSS anchor:
#    - --dsh-at-zoom: machine-readable zoom for the dock-fit JS compensation
#    - zoom scales panel + badge
#    - cap the panel to the viewport (divided by zoom, because lengths inside a
#      zoomed subtree render scaled) and scroll internally so nothing is cut off
$anchor = 'html{--agent-teams-panel-shift:420px}'
if (-not $c.Contains($anchor)) { throw "anchor not found - the plugin was updated and its CSS layout changed; this patch needs a review" }
$replacement = "$anchor" +
  "@media screen{html{--dsh-at-zoom:$scaleStr}.aYQbCq_panel,.aYQbCq_badge{zoom:$scaleStr}" +
  ".aYQbCq_panel{max-height:calc((100vh - 140px)/$scaleStr)!important;overflow-y:auto}}" +
  "/*dsh-at-scale:$scaleStr*/"
$c = $c.Replace($anchor, $replacement)

# 3) sanity: exactly one injection present (and the zoom variable with it), then write
$markerCount = [regex]::Matches($c, '/\*dsh-at-scale:[0-9.]+\*/').Count
if ($markerCount -ne 1) { throw "unexpected: $markerCount injections present after patch; aborting" }
if (-not $c.Contains("html{--dsh-at-zoom:$scaleStr}")) { throw "unexpected: --dsh-at-zoom variable missing after patch; aborting" }
[System.IO.File]::WriteAllText($PluginLib, $c)
Write-Host "[scale] panel UI scaled to ${scaleStr}x (zoom var --dsh-at-zoom declared for dock-fit) - refresh the page (F5) to see it"
Write-Host "[scale] change anytime with -Scale <n> ; undo with -Reset"
