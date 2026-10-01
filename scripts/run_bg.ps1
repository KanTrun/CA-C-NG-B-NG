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
Remove-Item -LiteralPath $log, $exitFile, $runner -Force -ErrorAction SilentlyContinue

@"
`$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath '$WorkDir'
`$env:PYTHONIOENCODING = 'utf-8'
& { $Command } *>&1 | Out-File -FilePath '$log' -Encoding utf8
`$LASTEXITCODE | Out-File -FilePath '$exitFile' -Encoding ascii
"@ | Set-Content -LiteralPath $runner -Encoding UTF8

Start-Process -FilePath "powershell.exe" `
  -ArgumentList @("-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $runner) `
  -WindowStyle Hidden | Out-Null

Write-Output "STARTED  $Name"
Write-Output "LOG      $log"
Write-Output "EXITFILE $exitFile"
Write-Output "Poll voi: .\scripts\poll_bg.ps1 -Name $Name"