# 往 innostar-ic「发送文件申请」弹窗的 upload input 注入本地文件
# 原理：主文档 eval → 钻进同源 iframe → 用 iframe.contentWindow 的 realm 构造
#       File/DataTransfer → 赋值 input.files → 派发 input/change 事件。
# agent-browser 自带 upload 命令对该 iframe 内 input 无效（返回 Done 但 files 为空），勿用。
param(
    [Parameter(Mandatory = $true)][string]$File,
    [string]$Selector = '.upload-input'
)
$ErrorActionPreference = 'Stop'

if (-not (Test-Path $File)) { throw "文件不存在: $File" }
$bytes = [IO.File]::ReadAllBytes($File)
$b64 = [Convert]::ToBase64String($bytes)
$name = [IO.Path]::GetFileName($File) -replace '\\', '\\\\' -replace "'", "\'"
$mime = if ([IO.Path]::GetExtension($File) -match '^\.(txt|log|md|json|xml|csv)$') { 'text/plain' } else { 'application/octet-stream' }

$js = @"
(() => {
  const fr = document.querySelector('iframe');
  if (!fr) return JSON.stringify({ error: 'main document has no iframe' });
  const w = fr.contentWindow, d = fr.contentDocument;
  const el = d.querySelector('$Selector');
  if (!el) return JSON.stringify({ error: 'input not found in iframe: $Selector' });
  const bin = atob('$b64');
  const bytes = new w.Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const file = new w.File([bytes], '$name', { type: '$mime' });
  const dt = new w.DataTransfer();
  dt.items.add(file);
  el.files = dt.files;
  const injected = Array.from(el.files).map(f => f.name + ':' + f.size);
  el.dispatchEvent(new w.Event('input', { bubbles: true }));
  el.dispatchEvent(new w.Event('change', { bubbles: true }));
  return JSON.stringify({ injected, note: 'app clears the input after change; verify via file list UI' });
})()
"@

agent-browser eval $js
Write-Host 'next: agent-browser snapshot -i / screenshot 确认文件出现在弹窗列表、上传提交按钮已启用'
