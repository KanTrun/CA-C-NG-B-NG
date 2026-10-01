<#
.SYNOPSIS
  Poll một lệnh đang chạy nền (khởi động bởi run_bg.ps1).

.DESCRIPTION
  Mặc định trả lời trong <1s nên không bao giờ bị coi là treo. In trạng thái kèm
  vài dòng cuối của log; exit file chỉ xuất hiện khi lệnh đã kết thúc.

  Với `-WaitSeconds` thì vòng lặp chờ có hạn (mặc định 0 = không chờ) — thay cho
  `Start-Sleep <số đoán>` rồi poll, vốn lệch với thực tế và lãng phí thời gian.

.PARAMETER WaitSeconds
  Chờ tối đa N giây cho job kết thúc, polling 1.5s/lần, rồi báo cáo. 0 = không
  chờ (mặc định, trả về ngay). Dùng thay cho `Start-Sleep` đoán mò: job xong
  sớm thì về sau ~1.5s, job chạy lâu thì hết hạn vẫn báo DANG CHAY.

.EXAMPLE
  .\scripts\poll_bg.ps1 -Name t1
  .\scripts\poll_bg.ps1 -Name t1 -Tail 40
  .\scripts\poll_bg.ps1 -Name t1 -WaitSeconds 240
#>
param(
  [Parameter(Mandatory = $true)][string]$Name,
  [int]$Tail = 25,
  [int]$WaitSeconds = 0
)

$jobDir = Join-Path ([System.IO.Path]::GetTempPath()) "opencode-jobs"
$log = Join-Path $jobDir "$Name.log"
$exitFile = Join-Path $jobDir "$Name.exit"

if ($WaitSeconds -gt 0) {
  $deadline = (Get-Date).AddSeconds($WaitSeconds)
  while (-not (Test-Path -LiteralPath $exitFile)) {
    if ((Get-Date) -ge $deadline) { break }
    Start-Sleep -Milliseconds 1500
  }
}

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