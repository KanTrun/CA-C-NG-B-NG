<#
.SYNOPSIS
  Poll một lệnh đang chạy nền (khởi động bởi run_bg.ps1).

.DESCRIPTION
  Luôn trả lời trong <1s nên không bao giờ bị coi là treo. In trạng thái kèm
  vài dòng cuối của log; exit file chỉ xuất hiện khi lệnh đã kết thúc.

.EXAMPLE
  .\scripts\poll_bg.ps1 -Name t1
  .\scripts\poll_bg.ps1 -Name t1 -Tail 40
#>
param(
  [Parameter(Mandatory = $true)][string]$Name,
  [int]$Tail = 25
)

$jobDir = Join-Path ([System.IO.Path]::GetTempPath()) "opencode-jobs"
$log = Join-Path $jobDir "$Name.log"
$exitFile = Join-Path $jobDir "$Name.exit"

if (Test-Path -LiteralPath $exitFile) {
  $code = (Get-Content -LiteralPath $exitFile -Raw).Trim()
  Write-Output "=== DONE (exit=$code) ==="
  if (Test-Path -LiteralPath $log) {
    Get-Content -LiteralPath $log -Tail $Tail
  } else {
    Write-Output "(khong co dong nao trong log)"
  }
  return
}

Write-Output "=== DANG CHAY ==="
if (Test-Path -LiteralPath $log) {
  Write-Output "log bytes: $((Get-Item -LiteralPath $log).Length)"
  Get-Content -LiteralPath $log -Tail 5
} else {
  Write-Output "(chua co dong nao)"
}