<#
.SYNOPSIS
  Chạy một lệnh dài ở chế độ NỀN, tách khỏi process cha.

.DESCRIPTION
  Vì sao cần: lệnh kiểm thử dài (pytest toàn bộ, docker build) chạy 10+ phút
  không in dòng nào ra — nhìn như treo và bị interrupt. Cách này tách process
  sang chạy độc lập, ghi log ra file, nên mỗi lần gọi đều trả về ngay lập tức.

  Process con KHÔNG bị giết khi process cha kết thúc: mỗi lệnh shell của agent
  là một process PowerShell riêng, nên gọi thẳng `Start-Job` sẽ mất job.

.PARAMETER Name
  Tên job. Dùng lại tên để poll.

.PARAMETER Command
  Lệnh cần chạy (chuỗi, sẽ được nhúng vào runner .ps1).

.EXAMPLE
  .\scripts\run_bg.ps1 -Name t1 -Command "& '.\.venv312\Scripts\python.exe' -m pytest -q"
  .\scripts\poll_bg.ps1 -Name t1
#>
param(
  [Parameter(Mandatory = $true)][string]$Name,
  [Parameter(Mandatory = $true)][string]$Command,
  [string]$WorkDir = (Split-Path -Parent $PSScriptRoot)
)

if ($Name -notmatch '^[A-Za-z0-9_-]+$') {
  throw "Ten job chi duoc chu cai, so, gach duong, gach noi: '$Name'"
}

$jobDir = Join-Path ([System.IO.Path]::GetTempPath()) "opencode-jobs"
New-Item -ItemType Directory -Path $jobDir -Force | Out-Null
$log = Join-Path $jobDir "$Name.log"
$exitFile = Join-Path $jobDir "$Name.exit"
$runner = Join-Path $jobDir "$Name.runner.ps1"
$durations = Join-Path $jobDir "durations.log"
Remove-Item -LiteralPath $log, $exitFile, $runner -Force -ErrorAction SilentlyContinue

# Runner tự ghi thời gian thực tế vào `durations.log` khi kết thúc, và ghi mốc
# bắt đầu vào `$Name.start`. Nhờ vậy lần sau poll KHÔNG phải đoán bao lâu nữa —
# nó biết chính xác job này trước đây mất bao nhiêu, và bao nhiêu đã trôi qua.
$startedAt = (Get-Date).ToString("o")
Set-Content -LiteralPath (Join-Path $jobDir "$Name.start") -Value $startedAt -Encoding ascii

@"
`$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath '$WorkDir'
`$env:PYTHONIOENCODING = 'utf-8'
`$t0 = Get-Date
& { $Command } *>&1 | Out-File -FilePath '$log' -Encoding utf8
# `$LASTEXITCODE CHI duoc dat boi lenh native (python, docker...). Job chi co
# PowerShell thuan (Start-Sleep, doi bien) thi no van `$null — goi
# .ToString() tren null se nem loi va exit file KHONG BAO GIO duoc ghi, lam
# poll cho toi han gio. Fallback sang `$?`.
`$code = if (`$null -ne `$LASTEXITCODE) { `$LASTEXITCODE } elseif (`$?) { 0 } else { 1 }
`$secs = [int][math]::Round(((Get-Date) - `$t0).TotalSeconds)
("`$code `$secs") | Out-File -FilePath '$exitFile' -Encoding ascii
Add-Content -LiteralPath '$durations' -Value "$Name `$secs" -Encoding ascii
"@ | Set-Content -LiteralPath $runner -Encoding UTF8

Start-Process -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $runner) `
  -WindowStyle Hidden | Out-Null

# Ước lượng từ lần chạy gần nhất CÙNG TÊN — không phải số đoán mò.
$known = $null
if (Test-Path -LiteralPath $durations) {
  $hit = Get-Content -LiteralPath $durations -ErrorAction SilentlyContinue |
    Where-Object { $_ -like "$Name *" } | Select-Object -Last 1
  if ($hit) { $known = ($hit -split '\s+')[-1] }
}

Write-Output "STARTED  $Name"
Write-Output "LOG      $log"
Write-Output "EXITFILE $exitFile"
if ($known) {
  Write-Output "LAN TRUOC job nay mat ~${known}s -> poll voi: -WaitAll"
} else {
  Write-Output "Chua co du lieu thoi gian job nay -> poll voi: -WaitAll"
}
Write-Output "Poll: .\scripts\poll_bg.ps1 -Name $Name -WaitAll"