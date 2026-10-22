$ErrorActionPreference = 'Continue'
$pub = 'D:\App\CloudMusic_R\orpheus\pub'

function Read-Unescaped($path) {
  $x = [System.IO.File]::ReadAllText($path)
  return [regex]::Replace($x, '\\u([0-9a-fA-F]{4})', { param($m) [string][char][Convert]::ToInt32($m.Groups[1].Value, 16) })
}

$v = Read-Unescaped (Join-Path $pub 'hybrid\vendors~app~subApp.chunk.83304b1.js')

'=== [A] OrpheusCommand context ==='
$i = $v.IndexOf('OrpheusCommand')
if ($i -ge 0) { $v.Substring([Math]::Max(0,$i-150), 1800) } else { 'OrpheusCommand: not found' }

''
'=== [B] native source file references (@see cloudmusic_win32:...) ==='
$see = [regex]::Matches($v, 'cloudmusic_win32:([^\}\s"\x27]+)') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
"count: $($see.Count)"
$see

''
'=== [C] namespace.method command candidates ==='
$cmds = [regex]::Matches($v, '"([a-zA-Z]+\.[a-zA-Z][a-zA-Z0-9_.]{1,50})"') |
        ForEach-Object { $_.Groups[1].Value } |
        Where-Object { $_ -notmatch '\.(js|css|png|jpg|webp|svg|gif|ico|com|net|org|html|mp3|mp4|json|wav)$' -and $_ -notmatch '^(window|document|console|process|module|exports|require)\.' } |
        Group-Object | Sort-Object Count -Descending
"distinct: $($cmds.Count), top 100:"
$cmds | Select-Object -First 100 | ForEach-Object { "{0,3}x  {1}" -f $_.Count, $_.Name }
