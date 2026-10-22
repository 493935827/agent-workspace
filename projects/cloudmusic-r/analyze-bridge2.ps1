$ErrorActionPreference = 'Continue'
$hybrid = 'D:\App\CloudMusic_R\orpheus\pub\hybrid'
$rudio  = 'D:\App\CloudMusic_R\orpheus\pub\vendor\@cloudmusic-desktop\vendors-rudio@0.1.x\vendors-rudio.pc-new.production.js'

'=== [A] customrequest usage (API-over-custom-scheme) ==='
foreach ($f in @('app.chunk.83304b1.js','subApp.chunk.83304b1.js','vendors~app~subApp.chunk.83304b1.js')) {
  $x = [System.IO.File]::ReadAllText((Join-Path $hybrid $f))
  $i = $x.IndexOf('customrequest')
  "{0}: customrequest hits = {1}" -f $f, ([regex]::Matches($x,'customrequest')).Count
  if ($i -ge 0) {
    $s=[Math]::Max(0,$i-300)
    '--- context ---'
    $x.Substring($s, 600)
    break
  }
}

''
'=== [B] orpheus string in rudio ==='
$rt = [System.IO.File]::ReadAllText($rudio)
"orpheus hits in rudio: $(([regex]::Matches($rt,'orpheus','IgnoreCase')).Count)"
$ri = $rt.IndexOf('orpheus')
if ($ri -ge 0) { $rt.Substring([Math]::Max(0,$ri-200), 500) }

''
'=== [C] i18n / translation mechanism ==='
foreach ($f in @('app.chunk.83304b1.js','vendors~app~subApp.chunk.83304b1.js')) {
  $x = [System.IO.File]::ReadAllText((Join-Path $hybrid $f))
  foreach ($pat in @('translation','getIntl','FormattedMessage','i18n','locale')) {
    $hits = ([regex]::Matches($x,$pat)).Count
    if ($hits -gt 0) { "{0,-36} {1,-18} {2} hits" -f $f, $pat, $hits }
  }
}
