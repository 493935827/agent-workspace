#requires -Version 5.1
<#
.SYNOPSIS
  AgentTeams (dsh-agent-teams) switch for the DeepSeek Harness "web" profile.

.DESCRIPTION
  Manages the plugin's master switch in the profile's cordis.patch.yml and can
  fully uninstall the plugin later.

.USAGE
  pwsh/powershell -File agent-teams-switch.ps1 status            # show current state
  pwsh/powershell -File agent-teams-switch.ps1 on                # enable plugin
  pwsh/powershell -File agent-teams-switch.ps1 off               # disable plugin (runtime off)
  pwsh/powershell -File agent-teams-switch.ps1 uninstall         # complete removal
  pwsh/powershell -File agent-teams-switch.ps1 uninstall -PurgeState
                                                                 # also delete .agent-teams state in current workspace

  After on / off / uninstall, RESTART the web profile to apply:
    close the DeepSeek Harness window, then re-run C:\Users\E0465\.dsh\dsh-desktop-app.ps1
    (or double-click the desktop shortcut again).
#>
param(
  [Parameter(Position = 0)]
  [ValidateSet('status', 'on', 'off', 'uninstall')]
  [string]$Action = 'status',

  [switch]$PurgeState,
  [string]$DshHome = "$env:USERPROFILE\.dsh",
  [string]$ProfileName = 'web',
  [string]$PackageName = '@nanmicoder/dsh-agent-teams',
  [string]$PluginId = 'agent-teams'
)

$ErrorActionPreference = 'Stop'
$profileDir = Join-Path $DshHome "profiles\$ProfileName"
$patchFile  = Join-Path $profileDir 'cordis.patch.yml'
$pkgFile    = Join-Path $profileDir 'package.json'

if (-not (Test-Path $patchFile)) { throw "profile patch file not found: $patchFile" }

function Get-PluginBlockRange([string[]]$lines) {
  # Returns @(startIndex, endIndex) of the "- id: <PluginId>" yaml block, or $null.
  $start = -1
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s*-\s*id:\s*' + [regex]::Escape($PluginId) + '\s*$') { $start = $i; break }
  }
  if ($start -lt 0) { return $null }
  $end = $lines.Count - 1
  for ($i = $start + 1; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s*-\s*id:') { $end = $i - 1; break }
  }
  return @($start, $end)
}

function Get-DisabledValue([string[]]$lines) {
  $range = Get-PluginBlockRange $lines
  if (-not $range) { return $null }   # no patch entry at all
  for ($i = $range[0]; $i -le $range[1]; $i++) {
    if ($lines[$i] -match '^\s*disabled:\s*(\S+)') { return ($Matches[1] -eq 'true') }
  }
  return $false   # entry exists without explicit flag -> enabled
}

function Save-PatchFile([string[]]$lines) {
  # Preserve file as UTF-8 (no BOM), LF endings as-is.
  [System.IO.File]::WriteAllText($patchFile, (($lines -join "`n") + "`n"), [System.Text.UTF8Encoding]::new($false))
}

$lines = [System.IO.File]::ReadAllLines($patchFile)
$pkg = Get-Content $pkgFile -Raw | ConvertFrom-Json
$installed = [bool]($pkg.dependencies.PSObject.Properties.Name -contains $PackageName)
$inBundles = [bool]($pkg.dsh.profile.bundles -contains $PackageName)
$disabled  = Get-DisabledValue $lines
$stateDir  = Join-Path (Get-Location) '.agent-teams'
$ver = $null
try { $ver = (Get-Content (Join-Path $profileDir "node_modules\$PackageName\package.json") -Raw | ConvertFrom-Json).version } catch {}

switch ($Action) {

  'status' {
    Write-Host "== AgentTeams switch status ($ProfileName profile) =="
    Write-Host ("  package installed : {0}{1}" -f $installed, $(if ($installed) { " (v$ver)" } else { '' }))
    Write-Host ("  in bundle stack   : {0}" -f $inBundles)
    Write-Host ("  patch entry       : {0}" -f $(if ($null -ne $disabled) { "present" } else { "MISSING (treat as off)" }))
    Write-Host ("  master switch     : {0}" -f $(if ($disabled) { 'OFF (disabled: true)' } elseif ($null -eq $disabled) { 'OFF (no entry)' } else { 'ON (disabled: false)' }))
    Write-Host ("  team state dir    : {0} ({1})" -f $stateDir, $(if (Test-Path $stateDir) { 'exists' } else { 'not created yet' }))
    Write-Host "  note: switch changes need a web-profile restart to take effect"
  }

  'on' {
    if (-not $installed) { throw "plugin is not installed; install it first (dsh plugin --profile $ProfileName add --save-exact $PackageName@0.1.28 --ignore-scripts)" }
    $range = Get-PluginBlockRange $lines
    if (-not $range) {
      $lines += "- id: $PluginId"
      $lines += '  disabled: false'
      Save-PatchFile $lines
      Write-Host "[on] added patch entry (disabled: false)"
    } else {
      for ($i = $range[0]; $i -le $range[1]; $i++) {
        if ($lines[$i] -match '^(\s*)disabled:\s*\S+') { $lines[$i] = "$($Matches[1])disabled: false" }
      }
      Save-PatchFile $lines
      Write-Host "[on] master switch set to disabled: false"
    }
    Write-Host "[on] restart the web profile to apply (see header comment)"
  }

  'off' {
    $range = Get-PluginBlockRange $lines
    if (-not $range) { Write-Host "[off] no patch entry found - plugin is already fully off (config-wise)"; return }
    for ($i = $range[0]; $i -le $range[1]; $i++) {
      if ($lines[$i] -match '^(\s*)disabled:\s*\S+') { $lines[$i] = "$($Matches[1])disabled: true" }
    }
    Save-PatchFile $lines
    Write-Host "[off] master switch set to disabled: true - plugin code stays installed but never loads"
    Write-Host "[off] restart the web profile to apply (see header comment)"
  }

  'uninstall' {
    # 1) remove the patch entry (config off first, so a failed pnpm step still disables it)
    $range = Get-PluginBlockRange $lines
    if ($range) {
      $newLines = @()
      if ($range[0] -gt 0) { $newLines += $lines[0..($range[0] - 1)] }
      if ($range[1] + 1 -le $lines.Count - 1) { $newLines += $lines[($range[1] + 1)..($lines.Count - 1)] }
      Save-PatchFile $newLines
      Write-Host "[uninstall] removed patch entry from cordis.patch.yml"
    } else {
      Write-Host "[uninstall] no patch entry found (already removed)"
    }

    # 2) remove the package + bundle entry via the official wrapper (reconciles bundles list)
    if ($installed) {
      Write-Host "[uninstall] removing package via: dsh plugin --profile $ProfileName remove $PackageName"
      & dsh plugin --profile $ProfileName remove $PackageName
      if ($LASTEXITCODE -ne 0) { throw "dsh plugin remove failed (exit $LASTEXITCODE); run it manually to finish" }
    } else {
      Write-Host "[uninstall] package not present in dependencies (already removed)"
      # still make sure the bundles list is clean
      $pkg2 = Get-Content $pkgFile -Raw | ConvertFrom-Json
      if ($pkg2.dsh.profile.bundles -contains $PackageName) {
        $pkg2.dsh.profile.bundles = @($pkg2.dsh.profile.bundles | Where-Object { $_ -ne $PackageName })
        $pkg2 | ConvertTo-Json -Depth 10 | Set-Content $pkgFile -Encoding UTF8
        Write-Host "[uninstall] removed stale bundle entry from package.json"
      }
    }

    # 3) optional: purge team state under the current workspace
    if ($PurgeState) {
      if (Test-Path $stateDir) {
        Remove-Item $stateDir -Recurse -Force
        Write-Host "[uninstall] purged team state: $stateDir"
      } else {
        Write-Host "[uninstall] no team state found at $stateDir"
      }
    } else {
      Write-Host "[uninstall] team state (if any) kept at <workspace>\.agent-teams ; delete manually or rerun with -PurgeState"
    }

    Write-Host "[uninstall] done - plugin fully removed. Restart the web profile to apply."
  }
}
