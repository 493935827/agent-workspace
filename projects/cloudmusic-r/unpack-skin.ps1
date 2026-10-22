$ErrorActionPreference = 'Continue'
Add-Type -AssemblyName System.IO.Compression

'=== NTPK skin unpack attempt (chunked zlib scan) ==='
foreach ($name in @('common.skin','dark.skin')) {
  $p = "D:\App\CloudMusic\package\$name"
  $bytes = [System.IO.File]::ReadAllBytes($p)
  "--- $name : $($bytes.Length) bytes ---"
  $out = "D:\App\CloudMusic_R\skin-$($name -replace '\.skin$','')"
  if (Test-Path $out) { Remove-Item $out -Recurse -Force }
  New-Item -ItemType Directory -Path $out -Force | Out-Null
  $count = 0; $offset = 16
  $ms = New-Object System.IO.MemoryStream
  while ($offset -lt $bytes.Length - 10) {
    # find zlib header 78 xx (xx in 01,9C,DA,5E)
    $found = $false
    while ($offset -lt $bytes.Length - 2) {
      $b0 = $bytes[$offset]
      if ($b0 -eq 0x78) {
        $b1 = $bytes[$offset+1]
        if ($b1 -in 0x01,0x5E,0x9C,0xDA) { $found = $true; break }
      }
      $offset++
    }
    if (-not $found) { break }
    try {
      $ms2 = New-Object System.IO.MemoryStream(,$bytes[$offset..($bytes.Length-1)])
      $zs = New-Object System.IO.Compression.DeflateStream($ms2, [System.IO.Compression.CompressionMode]::Decompress)
      # use ZLibStream-like approach: DeflateStream skips the 2-byte zlib header
      $outMs = New-Object System.IO.MemoryStream
      $zs.CopyTo($outMs)
      $raw = $outMs.ToArray()
      if ($raw.Length -gt 4) {
        $file = Join-Path $out ("chunk_{0,4}.bin" -f $count)
        [System.IO.File]::WriteAllBytes($file, $raw)
        $count++
        # advance offset past consumed compressed data
        $consumed = $ms2.Position + 2 + 4   # zlib header (2) + adler (4) approximated by stream position
        $offset = [int]($offset + $ms2.Position + 6)
      } else { $offset += 2 }
      $zs.Dispose(); $outMs.Dispose(); $ms2.Dispose()
    } catch {
      $offset += 1
    }
  }
  "$name -> $count chunks extracted to $out"
  if ($count -gt 0) {
    Get-ChildItem $out | Select-Object -First 6 | ForEach-Object {
      $h = ([System.IO.File]::ReadAllBytes($_.FullName)[0..7] | ForEach-Object { $_.ToString('X2') }) -join ' '
      "{0,10} bytes  {1}  magic: {2}" -f $_.Length, $_.Name, $h
    }
  }
}
