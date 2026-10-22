$ErrorActionPreference = 'Continue'
$pub = 'D:\App\CloudMusic_R\orpheus\pub'

function Read-Unescaped($path) {
  $x = [System.IO.File]::ReadAllText($path)
  return [regex]::Replace($x, '\\u([0-9a-fA-F]{4})', { param($m) [string][char][Convert]::ToInt32($m.Groups[1].Value, 16) })
}

$v = Read-Unescaped (Join-Path $pub 'hybrid\vendors~app~subApp.chunk.83304b1.js')

$i = $v.IndexOf('EnvAdapter.prototype.doAdapter = function')
if ($i -ge 0) {
  # dump 4500 chars covering the full method incl. win32 branch
  $v.Substring($i, 4500)
}
