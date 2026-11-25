# innostar 文件收发一键双区发送（send-file.ps1）
# 用法:
#   powershell -NoProfile -ExecutionPolicy Bypass -File send-file.ps1 -File "D:\path\to\file.exe" [-Description "描述"] [-Zones 安全桌面,开发网] [-Port 18731]
# 默认双区（安全桌面 + 开发网）各一 TICKET，接收用户默认当前账号。
# 流程: 会话保障(丢失自动重登,内联) -> CORS 服务 -> [开弹窗 -> 选区 -> 注入 -> 描述 -> 提交 -> 轮询完成 -> XHR 捕获工单号] x N 区
# 完成判据: 弹窗关闭 + 无「上传中」(绝不提前 reload, 防止掐断 upload-file-aj 分块)
# 工单号来源: 给 iframe 的 XHR/fetch 打补丁捕获 ticket/submit 响应, 免刷新; 捕获失败才回退 reload 读列表
# 注意: EAP=Continue + 显式校验。PS5.1 下 EAP=Stop 会把 agent-browser 的 stderr 噪声
#       ([agent-browser] launched browser 等)当终止错误, 管道场景还会挂住 —— 禁止改回 Stop。
param(
    [Parameter(Mandatory = $true)][string]$File,
    [string]$Description = '',
    [string[]]$Zones = @('安全桌面', '开发网'),
    [int]$Port = 18731,
    [switch]$KeepServer
)
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$resolved = (Resolve-Path -LiteralPath $File).Path
$fileName = [System.IO.Path]::GetFileName($resolved)
$fileDir  = [System.IO.Path]::GetDirectoryName($resolved)
if (-not $Description) { $Description = $fileName }
$sw = [System.Diagnostics.Stopwatch]::StartNew()

function NB { # run agent-browser, merge stdout+stderr, never throw on stderr noise
    param([string[]]$AgentArgs)
    $out = (& agent-browser @AgentArgs 2>&1 | Out-String).Trim()
    return $out
}
function EB([string]$js) { return NB @('eval', $js) }

function Get-UserEnv([string]$Name) {
    $v = [Environment]::GetEnvironmentVariable($Name)
    if (-not $v) { $v = [Environment]::GetEnvironmentVariable($Name, 'User') }
    if (-not $v) { throw "缺少环境变量 $Name" }
    return $v
}

function Session-Ok {
    try {
        # 纯字符串协议, 不含引号 —— agent-browser 会把结果再 JSON 编码一层, 带引号的匹配会被转义破坏
        $r = EB "var ok=!!document.querySelector('iframe');'ses='+ok"
        return ($r -match 'ses=true')
    } catch { return $false }
}

function Login-Inline {
    Write-Output ('STEP login @ {0:n1}s' -f $sw.Elapsed.TotalSeconds)
    NB @('close') | Out-Null
    $null = NB @('--ignore-https-errors', 'open', 'https://172.16.15.88/#/login')
    Start-Sleep -Seconds 1
    $u = Get-UserEnv 'INNOSTAR_IC_USER'
    $p = Get-UserEnv 'INNOSTAR_IC_PASS'
    $null = NB @('type', 'input[placeholder="请输入用户名"]', '--clear', '--', $u)
    $null = NB @('type', 'input[placeholder="请输入密码"]', '--clear', '--', $p)
    $null = NB @('find', 'role', 'button', 'click', '--name', '登录')
    Start-Sleep -Seconds 2
}

function Ensure-Session {
    for ($k = 0; $k -lt 3; $k++) {
        if (Session-Ok) { return $true }
        Login-Inline
        for ($w = 0; $w -lt 5; $w++) {
            Start-Sleep -Seconds 2
            if (Session-Ok) { return $true }
        }
    }
    return $false
}

function Open-Dialog {
    for ($k = 0; $k -lt 2; $k++) {
        $r = EB "var d=document.querySelector('iframe').contentDocument;var btn=[].slice.call(d.querySelectorAll('button')).find(function(b){return b.innerText.indexOf('发送文件申请')>=0});if(!btn){'NO-BUTTON'}else{btn.click();new Promise(function(res){setTimeout(function(){res('modal='+!!d.querySelector('.ant-modal'));},400);})}"
        if ($r -match 'modal=true') { return $true }
        Ensure-Session | Out-Null
    }
    return $false
}

function Select-Zone([string]$zone) {
    $r = EB "var d=document.querySelector('iframe').contentDocument;var fi=[].slice.call(d.querySelectorAll('.ant-modal .ant-form-item')).find(function(x){var l=x.querySelector('.ant-form-item-label label');return l&&l.innerText.indexOf('目标保护区')>=0});var sel=fi.querySelector('.ant-select');var se=sel.querySelector('.ant-select-selector');se.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));se.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));se.click();new Promise(function(res){setTimeout(function(){var hit=[].slice.call(d.querySelectorAll('.ant-select-dropdown .ant-select-item-option')).find(function(o){return o.getAttribute('title')==='$zone'});if(!hit){res('NO-OPTION');return;}hit.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));hit.click();setTimeout(function(){var v=(sel.querySelector('.ant-select-selection-item')||{innerText:''}).innerText;res('SEL='+v);},300);},300);})"
    return ($r -match ('SEL=' + $zone))
}

function Inject-And-Arm([string]$descZone) {
    # 补丁捕获 ticket/submit 响应 + 注入文件; Promise 全程带 20s 超时护栏, eval 不可能挂住
    $js = @"
var fr=document.querySelector('iframe');var w=fr.contentWindow;var d=w.document;
if(!w.__igcap){w.__igcap=[];var ox=w.XMLHttpRequest.prototype.open,os=w.XMLHttpRequest.prototype.send;w.XMLHttpRequest.prototype.open=function(m,u){this.__u=u;return ox.apply(this,arguments)};w.XMLHttpRequest.prototype.send=function(){var s=this;this.addEventListener('load',function(){try{if(s.__u&&s.__u.indexOf('ticket/submit')>=0){w.__igcap.push(String(s.responseText||'').slice(0,400));}}catch(e){}});return os.apply(this,arguments);};var of=w.fetch;w.fetch=function(){var uu=String(arguments[0]||'');var pp=of.apply(this,arguments);try{if(uu.indexOf('ticket/submit')>=0){pp.then(function(r){try{r.clone().text().then(function(t){w.__igcap.push(t.slice(0,400));},function(){});}catch(e){}});}}catch(e){}return pp;};}
w.__igcap.length=0;
new Promise(function(res){
  var arm=setTimeout(function(){res('INJECT-TIMEOUT');},20000);
  fetch(encodeURI('http://127.0.0.1:$Port/$fileName')).then(function(r){return r.arrayBuffer()}).then(function(buf){
    var f=new w.File([new w.Uint8Array(buf)],'$fileName');
    var dt=new w.DataTransfer();dt.items.add(f);
    var inp=d.querySelector('input.upload-input');
    inp.files=dt.files;
    inp.dispatchEvent(new w.Event('input',{bubbles:true}));
    inp.dispatchEvent(new w.Event('change',{bubbles:true}));
    setTimeout(function(){clearTimeout(arm);var sb=[].slice.call(d.querySelectorAll('.ant-modal button')).find(function(b){return b.innerText.indexOf('上传提交')>=0});var ok=sb&&(!sb.disabled);res('armed='+ok);},800);
  }).catch(function(e){clearTimeout(arm);res('INJECT-ERR:'+e);});
})
"@
    $js = ($js -replace "`r`n", ' ' -replace "`n", ' ')
    $r = EB $js
    if ($r -notmatch 'armed=true') { throw "inject failed: $r" }
    $js2 = "var fr=document.querySelector('iframe');var w=fr.contentWindow;var d=w.document;var ta=d.querySelector('.ant-modal textarea');var setter=Object.getOwnPropertyDescriptor(w.HTMLTextAreaElement.prototype,'value').set;setter.call(ta,'$descZone');ta.dispatchEvent(new w.Event('input',{bubbles:true}));var sb=[].slice.call(d.querySelectorAll('.ant-modal button')).find(function(b){return b.innerText.indexOf('上传提交')>=0});sb.click();'submitted'"
    $r2 = EB $js2
    if ($r2 -notmatch 'submitted') { throw "submit failed: $r2" }
}

function Wait-Done {
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 2
        $r = EB "var d=document.querySelector('iframe').contentDocument;var t=(d.body.innerText||'');var m=!!d.querySelector('.ant-modal');var u=(t.indexOf('上传中')>=0||t.indexOf('上传进度')>=0);'modal='+m+' up='+u"
        if ($r -match 'modal=false' -and $r -match 'up=false') { return $true }
    }
    return $false
}

function Get-Ticket {
    # 捕获的响应里引号会被多层转义, 干脆在 JS 里用 String.fromCharCode(34) 剥掉所有引号再返回
    $cap = EB "var w=document.querySelector('iframe').contentWindow;var c=(w.__igcap||[]).join('|||');'CAP='+c.split(String.fromCharCode(34)).join('')"
    if ($cap -match 'id:\s*(1[0-9]{4})' -or $cap -match '(1[0-9]{4})') {
        return @{ id = $Matches[1]; how = 'capture'; raw = $cap }
    }
    $null = EB "location.reload();'reloading'"
    Start-Sleep -Seconds 4
    $r = EB "var d=document.querySelector('iframe').contentDocument;JSON.stringify([].slice.call(d.querySelectorAll('td')).slice(0,10).map(function(c){return c.innerText.replace(/\s+/g,' ').trim()}))"
    if ($r -match '(1[0-9]{4})') { return @{ id = $Matches[1]; how = 'list'; raw = $r } }
    return @{ id = '?'; how = 'none'; raw = ($cap + ' | ' + $r) }
}

# ===== main =====
$validZones = @('安全桌面', '开发网')
$bad = @($Zones | Where-Object { $validZones -notcontains $_ })
if ($bad.Count -gt 0) { throw "invalid zone(s): $($bad -join ',') — valid: 安全桌面,开发网 (检查参数是否因空格串位)" }
if (-not (Ensure-Session)) { throw 'cannot establish session' }

$serverProc = $null
if (-not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
    $serverProc = Start-Process -FilePath 'python' -ArgumentList @('"' + (Join-Path $PSScriptRoot 'serve-cors.py') + '"', '"' + $fileDir + '"', "$Port") -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 800
    Write-Output ('STEP cors-server @ {0:n1}s' -f $sw.Elapsed.TotalSeconds)
}

$results = @()
try {
    foreach ($zone in $Zones) {
        $t0 = $sw.Elapsed.TotalSeconds
        if (-not (Open-Dialog)) { throw "dialog open failed ($zone)" }
        if (-not (Select-Zone $zone)) { throw "zone select failed ($zone)" }
        $descZone = "$Description（$zone）"
        Inject-And-Arm $descZone
        Write-Output ('STEP submitted [{0}] @ {1:n1}s' -f $zone, $sw.Elapsed.TotalSeconds)
        if (-not (Wait-Done)) { throw "upload not confirmed ($zone)" }
        $tk = Get-Ticket
        $dt = [int]($sw.Elapsed.TotalSeconds - $t0)
        $line = "TICKET $($tk.id) [$zone] ($($tk.how), ${dt}s)"
        $results += $line
        Write-Output $line
        if ($tk.how -eq 'none') { Write-Output ("  raw: " + $tk.raw.Substring(0, [Math]::Min(300, $tk.raw.Length))) }
    }
}
catch {
    Write-Output ("FAILED {0:n1}s: {1}" -f $sw.Elapsed.TotalSeconds, $_.Exception.Message)
}
finally {
    if ($serverProc -and -not $KeepServer) {
        try { Stop-Process -Id $serverProc.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
}
$sw.Stop()
Write-Output ("TOTAL {0:n1}s for {1} zone(s), file={2}" -f $sw.Elapsed.TotalSeconds, $Zones.Count, $fileName)
