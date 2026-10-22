$ErrorActionPreference = 'Continue'
$pub = 'D:\App\CloudMusic_R\orpheus\pub'

function Read-Unescaped($path) {
  $x = [System.IO.File]::ReadAllText($path)
  return [regex]::Replace($x, '\\u([0-9a-fA-F]{4})', { param($m) [string][char][Convert]::ToInt32($m.Groups[1].Value, 16) })
}

$v = Read-Unescaped (Join-Path $pub 'hybrid\vendors~app~subApp.chunk.83304b1.js')

'=== isWinCEF usage contexts ==='
$m = [regex]::Matches($v, '.{80}isWinCEF.{240}')
"windows: $($m.Count)"
$m | Select-Object -First 4 | ForEach-Object { $_.Value; '---' }

''
'=== window.XXX global injections in vendors bundle (candidate native bridges) ==='
$g = [regex]::Matches($v, 'window\.([A-Za-z_$][A-Za-z0-9_$]{2,30})\s*=') |
     ForEach-Object { $_.Groups[1].Value } |
     Where-Object { $_ -notin @('webpackJsonp') } |
     Group-Object | Sort-Object Count -Descending
$g | Select-Object -First 30 | ForEach-Object { "{0,3}x  window.{1}" -f $_.Count, $_.Name }
