# Innostar 文件收发 - agent-browser 登录脚本
# 凭据取自用户级环境变量 INNOSTAR_IC_USER / INNOSTAR_IC_PASS（含注册表回退），不落命令行明文
param(
    [string]$BaseUrl = 'https://172.16.15.88'
)
$ErrorActionPreference = 'Stop'

function Get-UserEnv([string]$Name) {
    $v = [Environment]::GetEnvironmentVariable($Name)
    if (-not $v) { $v = [Environment]::GetEnvironmentVariable($Name, 'User') }
    if (-not $v) {
        throw "缺少环境变量 $Name。先执行: [Environment]::SetEnvironmentVariable('$Name','<值>','User')"
    }
    return $v
}

$user = Get-UserEnv 'INNOSTAR_IC_USER'
$pass = Get-UserEnv 'INNOSTAR_IC_PASS'

# --ignore-https-errors 只在浏览器启动时生效，先关掉旧会话
agent-browser close 2>$null | Out-Null

agent-browser --ignore-https-errors open "$BaseUrl/#/login" | Out-Null
Start-Sleep 1

# 登录页在主文档，CSS 选择器可用
agent-browser type 'input[placeholder="请输入用户名"]' --clear -- $user
agent-browser type 'input[placeholder="请输入密码"]' --clear -- $pass
agent-browser find role button click --name '登录'

Start-Sleep 2
$url = agent-browser get url
"logged in, current url: $url"
