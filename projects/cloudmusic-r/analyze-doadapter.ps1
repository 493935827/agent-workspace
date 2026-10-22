$ErrorActionPreference = 'Continue'
$pub = 'D:\App\CloudMusic_R\orpheus\pub'

function Read-Unescaped($path) {
  $x = [System.IO.File]::ReadAllText($path)
  return [regex]::Replace($x, '\\u([0-9a-fA-F]{4})', { param($m) [string][char][Convert]::ToInt32($m.Groups[1].Value, 16) })
}

$v = Read-Unescaped (Join-Path $pub 'hybrid\vendors~app~subApp.chunk.83304b1.js')

'=== doAdapter definition contexts ==='
$m = [regex]::Matches($v, '.{100}doAdapter.{700}')
"windows: $($m.Count)"
$m | Select-Object -First 3 | ForEach-Object { $_.Value; '---' }
