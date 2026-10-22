$ErrorActionPreference = 'Continue'
$pub = 'D:\App\CloudMusic_R\orpheus\pub'
$R = 'D:\App\CloudMusic_R'

function Read-Unescaped($path) {
  $x = [System.IO.File]::ReadAllText($path)
  return [regex]::Replace($x, '\\u([0-9a-fA-F]{4})', { param($m) [string][char][Convert]::ToInt32($m.Groups[1].Value, 16) })
}

# 1) API endpoints (all hybrid chunks + _next)
$api = @()
foreach ($f in (Get-ChildItem $pub -Recurse -File -Include *.js)) {
  $x = [System.IO.File]::ReadAllText($f.FullName)
  $api += [regex]::Matches($x, '"(/api/[a-zA-Z0-9/_\-\.]+)"') | ForEach-Object { $_.Groups[1].Value }
  $api += [regex]::Matches($x, "'(/api/[a-zA-Z0-9/_\-\.]+)'") | ForEach-Object { $_.Groups[1].Value }
}
$api = $api | Sort-Object -Unique
[System.IO.File]::WriteAllLines("$R\api-endpoints.txt", $api)
"api-endpoints.txt: $($api.Count) endpoints"

# 2) native command namespace.method (vendors bundle, unescaped)
$v = Read-Unescaped (Join-Path $pub 'hybrid\vendors~app~subApp.chunk.83304b1.js')
$cmds = [regex]::Matches($v, '"([a-zA-Z]+\.[a-zA-Z][a-zA-Z0-9_.]{1,50})"') |
        ForEach-Object { $_.Groups[1].Value } |
        Where-Object { $_ -notmatch '\.(js|css|png|jpg|webp|svg|gif|ico|com|net|org|html|mp3|mp4|json|wav|ts|cpp)$' -and $_ -notmatch '^(window|document|console|process|module|exports|require|Array|Object|String|Number|Error|Math|JSON|Promise|Symbol)\.' } |
        Sort-Object -Unique
[System.IO.File]::WriteAllLines("$R\native-commands.txt", $cmds)
"native-commands.txt: $($cmds.Count) candidate commands"

# 3) orpheus:// protocol endpoints
$proto = @()
foreach ($f in (Get-ChildItem $pub -Recurse -File -Include *.js)) {
  $x = [System.IO.File]::ReadAllText($f.FullName)
  $proto += [regex]::Matches($x, 'orpheus://[a-zA-Z0-9/_\-\.]+') | ForEach-Object { $_.Value }
}
$proto = $proto | Sort-Object -Unique
[System.IO.File]::WriteAllLines("$R\orpheus-protocol-endpoints.txt", $proto)
"orpheus-protocol-endpoints.txt: $($proto.Count) endpoints"

# 4) css inventory
$css = Get-ChildItem $pub -Recurse -File -Filter *.css | Sort-Object Length -Descending |
       ForEach-Object { "{0,8}  {1}" -f $_.Length, $_.FullName.Replace("$pub\",'') }
[System.IO.File]::WriteAllLines("$R\css-inventory.txt", $css)
"css-inventory.txt: $($css.Count) files"
