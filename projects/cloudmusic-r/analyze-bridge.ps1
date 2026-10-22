$ErrorActionPreference = 'Continue'
$hybrid = 'D:\App\CloudMusic_R\orpheus\pub\hybrid'

'=== [A] escaped unicode test: \\u4e00-\\u9fff occurrences in a sample chunk ==='
$t = [System.IO.File]::ReadAllText((Join-Path $hybrid '21.chunk.83304b1.js'))
$esc = [regex]::Matches($t, '\\u[4-9][0-9a-f]{2}').Count
"escaped-unicode hits in 21.chunk: $esc"
$raw = [regex]::Matches($t, '[\u4e00-\u9fff]').Count
"raw CJK chars in 21.chunk: $raw"
'first 300 chars of 21.chunk:'
$t.Substring(0, [Math]::Min(300, $t.Length))

''
'=== [B] native bridge patterns across main chunks ==='
foreach ($f in @('app.chunk.83304b1.js','subApp.chunk.83304b1.js','vendors~app~subApp.chunk.83304b1.js')) {
  $x = [System.IO.File]::ReadAllText((Join-Path $hybrid $f))
  foreach ($pat in @('cefQuery','window\.orpheus','orpheusBridge','nativeCall','\.callHandler\(','registerHandler\(','removeHandler\(','window\.chrome\.webview','postMessage\(')) {
    $hits = ([regex]::Matches($x, $pat)).Count
    if ($hits -gt 0) { "{0,-36} {1,-42} {2} hits" -f $f, $pat, $hits }
  }
}

''
'=== [C] cefQuery context in app.chunk (400 chars around first hit) ==='
$x = [System.IO.File]::ReadAllText((Join-Path $hybrid 'app.chunk.83304b1.js'))
$i = $x.IndexOf('cefQuery')
if ($i -ge 0) { $s=[Math]::Max(0,$i-200); $x.Substring($s, 400) } else { 'cefQuery not found in app.chunk' }
