$ErrorActionPreference = 'Continue'
$pub = 'D:\App\CloudMusic_R\orpheus\pub'

'=== contexts around "orpheus" in app.chunk (first 4, 260 chars each) ==='
$x = [System.IO.File]::ReadAllText((Join-Path $pub 'hybrid\app.chunk.83304b1.js'))
$ms = [regex]::Matches($x, '.{110}orpheus.{150}')
"total context windows: $($ms.Count)"
$ms | Select-Object -First 4 | ForEach-Object { $_.Value; '---' }

''
'=== same for vendors~app~subApp (first 3) ==='
$v = [System.IO.File]::ReadAllText((Join-Path $pub 'hybrid\vendors~app~subApp.chunk.83304b1.js'))
$mv = [regex]::Matches($v, '.{110}orpheus.{150}')
"total: $($mv.Count)"
$mv | Select-Object -First 3 | ForEach-Object { $_.Value; '---' }

''
'=== same for 73.chunk (20 hits, first 3) ==='
$c73 = [System.IO.File]::ReadAllText((Join-Path $pub 'hybrid\73.chunk.83304b1.js'))
$m73 = [regex]::Matches($c73, '.{110}orpheus.{150}')
"total: $($m73.Count)"
$m73 | Select-Object -First 3 | ForEach-Object { $_.Value; '---' }
