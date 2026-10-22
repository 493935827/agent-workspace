$ErrorActionPreference = 'Continue'
$pub = 'D:\App\CloudMusic_R\orpheus\pub'

function Read-Unescaped($path) {
  $x = [System.IO.File]::ReadAllText($path)
  return [regex]::Replace($x, '\\u([0-9a-fA-F]{4})', { param($m) [string][char][Convert]::ToInt32($m.Groups[1].Value, 16) })
}

$v = Read-Unescaped (Join-Path $pub 'hybrid\vendors~app~subApp.chunk.83304b1.js')

'=== win32-cef invocation mechanism: search cefQuery / Query / execute in bridge region ==='
foreach ($pat in @('cefQuery','window\.query','cefRequest','MessageRouter','native-intf')) {
  $hits = [regex]::Matches($v, $pat)
  "{0,-22} {1} hits" -f $pat, $hits.Count
}

''
'=== MAGIC usage context (native-intf) ==='
$m1 = [regex]::Matches($v, '.{200}native-intf.{300}')
"windows: $($m1.Count)"
$m1 | Select-Object -First 2 | ForEach-Object { $_.Value; '---' }

''
'=== isWinCEF dispatch: 1400 chars after "var isOSX" ==='
$i = $v.IndexOf('var isOSX')
if ($i -ge 0) { $v.Substring($i, 2200) }
