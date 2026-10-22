$ErrorActionPreference = 'Continue'
$pub = 'D:\App\CloudMusic_R\orpheus\pub'

function Read-Unescaped($path) {
  $x = [System.IO.File]::ReadAllText($path)
  return [regex]::Replace($x, '\\u([0-9a-fA-F]{4})', { param($m) [string][char][Convert]::ToInt32($m.Groups[1].Value, 16) })
}

$v = Read-Unescaped (Join-Path $pub 'hybrid\vendors~app~subApp.chunk.83304b1.js')

'=== OrpheusCommand methods (prototype or class body, before "return OrpheusCommand") ==='
$i = $v.IndexOf('return OrpheusCommand')
if ($i -ge 0) {
  $s = [Math]::Max(0, $i - 3200)
  $v.Substring($s, 3200)
}

''
''
'=== call sites: nativeCmder.call / legacyNativeCmder.call in app.chunk ==='
$a = Read-Unescaped (Join-Path $pub 'hybrid\app.chunk.83304b1.js')
$mc = [regex]::Matches($a, '.{80}(nativeCmder|legacyNativeCmder)\.(call|invoke)\(.{220}')
"windows: $($mc.Count)"
$mc | Select-Object -First 3 | ForEach-Object { $_.Value; '---' }
