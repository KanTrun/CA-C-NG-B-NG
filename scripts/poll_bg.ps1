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
  [int]$WaitSeconds = 0,
  [switch]$WaitAll,
  [int]$HeartbeatSeconds = 30
)

$jobDir = Join-Path ([System.IO.Path]::GetTempPath()) "opencode-jobs"
$log = Join-Path $jobDir "$Name.log"
$exitFile = Join-Path $jobDir "$Name.exit"
$startFile = Join-Path $jobDir "$Name.start"

function Get-JobExitCode {
  # Trả $null khi job CHƯA xong. Runner tạo file exit rồi mới ghi nội dung,
  # nên đọc file tồn tại nhưng rỗng = đang chạy (race), không phải DONE.
  if (-not (Test-Path -LiteralPath $exitFile)) { return $null }
  $raw = Get-Content -LiteralPath $exitFile -Raw -ErrorAction SilentlyContinue
  if ($null -eq $raw -or $raw.Trim() -eq '') { return $null }
  return $raw.Trim()
}

function Get-ElapsedSeconds {
  if (-not (Test-Path -LiteralPath $startFile)) { return $null }
  $t0 = Get-Content -LiteralPath $startFile -Raw -ErrorAction SilentlyContinue
  if ([string]::IsNullOrWhiteSpace($t0)) { return $null }
  try {
    return [int][math]::Round(((Get-Date) - [datetime]::Parse($t0.Trim())).TotalSeconds)
  } catch { return $null }
}

# `-WaitAll`: chờ tới khi job kết thúc, KHÔNG đặt hạn giờ đoán. Nhịp heartbeat
# để thấy tiến triển thay vì im lặng. Vẫn có trần cứng để không treo vô hạn.
$deadline = $null
if ($WaitAll) {
  $deadline = (Get-Date).AddSeconds(3600)
} elseif ($WaitSeconds -gt 0) {
  $deadline = (Get-Date).AddSeconds($WaitSeconds)
}

$code = Get-JobExitCode
$lastBeat = Get-Date
while ($null -eq $code -and $null -ne $deadline -and (Get-Date) -lt $deadline) {
  Start-Sleep -Milliseconds 1500
  $code = Get-JobExitCode
  if ($null -ne $deadline -and ((Get-Date) - $lastBeat).TotalSeconds -ge $HeartbeatSeconds) {
    $lastBeat = Get-Date
    # Chỉ báo thời gian + kích thước log. KHÔNG nhét nội dung log vào định
    # dạng: dòng của pytest là hàng chục dấu chấm, vừa không phải thông tin
    # tiến triển vừa làm `-f` vỡ. Muốn đọc log thì dùng -Tail.
    $el = Get-ElapsedSeconds
    $bytes = if (Test-Path -LiteralPath $log) { (Get-Item -LiteralPath $log).Length } else { 0 }
    Write-Output "--- con chay ${el}s | log $bytes bytes"
  }
}

if ($null -ne $code) {
  $el = Get-ElapsedSeconds
  Write-Output "=== DONE (exit=$code) | thoi gian thuc: ${el}s ==="
  # Runner ghi exit file NGAY sau khi `Out-File` đóng, nhưng trên đĩa đôi khi
  # nội dung log chưa flush xong — đọc ra rỗng. Chờ tối đa ~2s cho log có dòng.
  $logDeadline = (Get-Date).AddSeconds(2)
  while ((Get-Date) -lt $logDeadline) {
    if ((Test-Path -LiteralPath $log) -and (Get-Item -LiteralPath $log).Length -gt 0) { break }
    Start-Sleep -Milliseconds 200
  }
  if (Test-Path -LiteralPath $log) {
    Get-Content -LiteralPath $log -Tail $Tail
  } else {
    Write-Output "(khong co dong nao trong log)"
  }
  return
}

Write-Output "=== DANG CHAY ==="
$elapsed = Get-ElapsedSeconds
if ($null -ne $elapsed) { Write-Output "da troi qua: ${elapsed}s" }
if (Test-Path -LiteralPath $log) {
  Write-Output "log bytes: $((Get-Item -LiteralPath $log).Length)"
  Get-Content -LiteralPath $log -Tail 5
} else {
  Write-Output "(chua co dong nao)"
}