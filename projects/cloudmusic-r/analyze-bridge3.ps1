$ErrorActionPreference = 'Continue'
$pub = 'D:\App\CloudMusic_R\orpheus\pub'

'=== [A] where does "orpheus" appear (per-file hit counts, JS only) ==='
$files = Get-ChildItem $pub -Recurse -File -Include *.js | Where-Object { $_.Length -lt 6MB }
foreach ($f in $files) {
  $x = [System.IO.File]::ReadAllText($f.FullName)
  $h = ([regex]::Matches($x,'orpheus')).Count
  if ($h -gt 0) { "{0,5} hits  {1}" -f $h, $f.FullName.Replace("$pub\",'') }
}

''
'=== [B] scheme-based API call wrapper: search "orpheus://" near fetch/XHR in top files ==='
foreach ($name in @('0.chunk.83304b1.js','7.chunk.83304b1.js','app.chunk.83304b1.js','subApp.chunk.83304b1.js')) {
  $p = Join-Path $hybrid $name
  if (-not (Test-Path $p)) { continue }
  $x = [System.IO.File]::ReadAllText($p)
  $ms = [regex]::Matches($x, '.{120}orpheus://.{120}')
  "### $name : $($ms.Count) contexts, first 2:"
  $ms | Select-Object -First 2 | ForEach-Object { $_.Value; '---' }
}
