$ErrorActionPreference = 'Continue'
$pub = 'D:\App\CloudMusic_R\orpheus\pub'

# read + unescape \uXXXX so Chinese comments become readable
function Read-Unescaped($path) {
  $x = [System.IO.File]::ReadAllText($path)
  return [regex]::Unescape($x)
}

$v = Read-Unescaped (Join-Path $pub 'hybrid\vendors~app~subApp.chunk.83304b1.js')

'=== [A] OrpheusCommand architecture: 1600 chars around first definition ==='
$i = $v.IndexOf('OrpheusCommand')
if ($i -ge 0) { $v.Substring([Math]::Max(0,$i-100), 1600) } else { 'not found' }

''
'=== [B] native source file references (@see cloudmusic_win32:...) ==='
$see = [regex]::Matches($v, '@see \{?cloudmusic_win32:([^\}\s\n]+)') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
"共 $($see.Count) 个原生源码引用:"
$see

''
'=== [C] command-name candidates ("namespace.method" string literals) ==='
$cmds = [regex]::Matches($v, '"([a-zA-Z]+\.[a-zA-Z][a-zA-Z0-9_.]{1,50})"') |
        ForEach-Object { $_.Groups[1].Value } |
        Where-Object { $_ -notmatch '\.(js|css|png|jpg|webp|svg|com|net|org|html)' } |
        Group-Object | Sort-Object Count -Descending
"distinct: $($cmds.Count), top 80:"
$cmds | Select-Object -First 80 | ForEach-Object { "{0,3}x  {1}" -f $_.Count, $_.Name }
