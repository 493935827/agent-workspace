$ErrorActionPreference = 'Continue'
$chunk = 'D:\App\CloudMusic_R\orpheus\pub\hybrid\app.chunk.83304b1.js'
$sub   = 'D:\App\CloudMusic_R\orpheus\pub\hybrid\subApp.chunk.83304b1.js'
$rudio = 'D:\App\CloudMusic_R\orpheus\pub\vendor\@cloudmusic-desktop\vendors-rudio@0.1.x\vendors-rudio.pc-new.production.js'

'=== React 路由表 (app.chunk + subApp.chunk) ==='
$m = Select-String -Path $chunk,$sub -Pattern 'path:"(/[a-zA-Z0-9/_:\-]+)"' -AllMatches |
  ForEach-Object { $_.Matches } | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
"共 $($m.Count) 条路由:"
$m

''
'=== rudio 桥接库开头 400 字符 ==='
$fs=[System.IO.File]::OpenRead($rudio); $b=New-Object byte[] 400; [void]$fs.Read($b,0,400); $fs.Close()
(-join ($b|%{if($_ -ge 32 -and $_ -le 126){[char]$_}else{' '}}))
