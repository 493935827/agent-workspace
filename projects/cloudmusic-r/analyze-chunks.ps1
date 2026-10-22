$ErrorActionPreference = 'Continue'
$hybrid = 'D:\App\CloudMusic_R\orpheus\pub\hybrid'
$rudio  = 'D:\App\CloudMusic_R\orpheus\pub\vendor\@cloudmusic-desktop\vendors-rudio@0.1.x\vendors-rudio.pc-new.production.js'

'=== [1] chunk -> feature mapping (first unique Chinese strings per chunk) ==='
$chunks = Get-ChildItem $hybrid -Filter '*.js' | Sort-Object { [int]($_.Name -replace '\D.*$','') }
foreach ($c in $chunks) {
  $text = [System.IO.File]::ReadAllText($c.FullName)
  $cn = [regex]::Matches($text, '[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9 ]{1,18}') |
        ForEach-Object { $_.Value } | Select-Object -Unique -First 4
  $kb = [math]::Round($c.Length/1KB,0)
  if ($cn) { "{0,-28} {1,6}KB  {2}" -f $c.Name, $kb, ($cn -join ' | ') }
  else     { "{0,-28} {1,6}KB  (no CJK)" -f $c.Name, $kb }
}

''
'=== [2] rudio bridge: top string literals (candidate native API names) ==='
$rt = [System.IO.File]::ReadAllText($rudio)
$lits = [regex]::Matches($rt, '"([a-zA-Z][a-zA-Z0-9_\-]{2,40})"') |
        ForEach-Object { $_.Groups[1].Value } |
        Group-Object | Sort-Object Count -Descending
"total distinct: $($lits.Count)"
$lits | Select-Object -First 50 | ForEach-Object { "{0,4}x  {1}" -f $_.Count, $_.Name }

''
'=== [3] bridge invocation patterns in app.chunk ==='
$at = [System.IO.File]::ReadAllText('D:\App\CloudMusic_R\orpheus\pub\hybrid\app.chunk.83304b1.js')
$st = [System.IO.File]::ReadAllText('D:\App\CloudMusic_R\orpheus\pub\hybrid\subApp.chunk.83304b1.js')
foreach ($pat in @('CMRudio[.\[]\w*','callNative\w*','invokeNative\w*','postMessage\(','window\.external\w*','webkit\.messageHandlers\.\w+','NcWebViewBridge\.\w+')) {
  $hits = ([regex]::Matches($at + $st, $pat)).Count
  "{0,-40} {1} hits" -f $pat, $hits
}
