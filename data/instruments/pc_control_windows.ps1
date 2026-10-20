# Shared Windows PC controls. Windows PowerShell 5.1 + built-in Core Audio COM + user32/WinRT.
# 본체 OS 조작면 Windows 동형(2026-10-20, 설계 §18). 맥 실행 파일(pc_control_mac.py)과 같은 결과 모양을 돌려준다.
# 관리자 권한을 요구하지 않는다 — 관리자여야만 읽히는 값은 null 과 basis 로 정직하게 남긴다.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$result = @{ protocol='pc-control/1'; platform='windows'; action=$PcRequest.action; request_id=$PcRequest.request_id; success=$false; verified=$false }
$KeepAwakeFile = Join-Path $env:APPDATA 'IndieBiz\pc_keep_awake.json'

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
namespace IndieBizPC {
 public static class Native {
  [StructLayout(LayoutKind.Sequential)] public struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
  [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO info);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  [DllImport("user32.dll", SetLastError=true)] static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint access);
  [DllImport("user32.dll")] static extern bool CloseDesktop(IntPtr handle);
  [DllImport("user32.dll", SetLastError=true)] [return: MarshalAs(UnmanagedType.Bool)] public static extern bool LockWorkStation();
  [DllImport("kernel32.dll")] public static extern uint WTSGetActiveConsoleSessionId();
  public static double IdleSeconds() {
   LASTINPUTINFO info = new LASTINPUTINFO(); info.cbSize = (uint)Marshal.SizeOf(info);
   if (!GetLastInputInfo(ref info)) return -1;
   return unchecked((uint)Environment.TickCount - info.dwTime) / 1000.0;
  }
  public static string WindowTitle(IntPtr hWnd) { StringBuilder sb = new StringBuilder(512); GetWindowText(hWnd, sb, 512); return sb.ToString(); }
  // 입력 데스크톱을 열 수 없으면(접근 거부) 잠금·보안 데스크톱이다. 열리면 잠기지 않은 것.
  public static int InputDesktopState() {
   IntPtr h = OpenInputDesktop(0, false, 0x0001);
   if (h == IntPtr.Zero) { return Marshal.GetLastWin32Error() == 5 ? 1 : -1; }
   CloseDesktop(h); return 0;
  }
 }
}
'@
Add-Type -AssemblyName System.Windows.Forms

function Test-Admin {
    try { ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) } catch { $false }
}

# ---------------------------------------------------------------- 세션·화면
function Get-SessionState {
    $state = [IndieBizPC.Native]::InputDesktopState()
    $logon = @(Get-Process -Name LogonUI -ErrorAction SilentlyContinue).Count -gt 0
    $locked = $null
    if ($state -eq 1 -or $logon) { $locked = $true } elseif ($state -eq 0) { $locked = $false }
    $console = $null
    try { $console = ([System.Diagnostics.Process]::GetCurrentProcess().SessionId -eq [IndieBizPC.Native]::WTSGetActiveConsoleSessionId()) } catch { $console = $null }
    @{ screen_locked = $locked; on_console = $console; session_basis = 'open_input_desktop+logonui_process' }
}

function Get-WmiBrightness {
    try { @(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness -ErrorAction Stop | Where-Object { $_.Active }) } catch { @() }
}

function Get-Displays {
    $wmi = @(Get-WmiBrightness)
    $rows = @()
    $index = 0
    foreach ($screen in [System.Windows.Forms.Screen]::AllScreens) {
        $id = 0
        if ($screen.DeviceName -match '(\d+)$') { $id = [int]$Matches[1] }
        $level = $null; $can = $false
        # WMI 밝기 인스턴스(보통 내장 화면 하나)를 순서대로 화면에 붙인다. 외부 모니터는 인스턴스가 없다.
        if ($index -lt $wmi.Count) { $level = [int]$wmi[$index].CurrentBrightness; $can = $true }
        $rows += @{ id = $id; main = [bool]$screen.Primary; builtin = $(if ($can) { $true } else { $null }); active = $true; asleep = $null
                    width = [int]$screen.Bounds.Width; height = [int]$screen.Bounds.Height; name = $screen.DeviceName
                    brightness = $level; can_set_brightness = $can
                    brightness_basis = $(if ($wmi.Count -gt 0) { 'wmi_monitor_brightness' } else { 'unavailable(wmi_monitor_brightness 인스턴스 없음 — 외부 모니터)' }) }
        $index++
    }
    ,$rows
}

function Set-Brightness($request) {
    $rows = Get-Displays
    $target = $null
    if ($null -ne $request.display_id) {
        $target = $rows | Where-Object { $_.id -eq [int]$request.display_id } | Select-Object -First 1
        if (-not $target) { throw '지정한 화면이 없습니다. display 로 목록을 조회하세요.' }
    } else { $target = $rows | Where-Object { $_.main } | Select-Object -First 1 }
    if (-not $target.can_set_brightness) { throw '이 화면은 밝기 변경을 지원하지 않습니다(외부 모니터 등). display 의 can_set_brightness 를 보세요.' }
    $methods = @(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop | Where-Object { $_.Active })
    if ($methods.Count -eq 0) { throw '이 Windows 에서 밝기 제어 WMI 를 열지 못했습니다.' }
    $null = Invoke-CimMethod -InputObject $methods[0] -MethodName WmiSetBrightness -Arguments @{ Timeout = [uint32]1; Brightness = [byte]$request.value }
    Start-Sleep -Milliseconds 300
    $after = (Get-Displays) | Where-Object { $_.id -eq $target.id } | Select-Object -First 1
    if ($null -eq $after.brightness -or [Math]::Abs($after.brightness - [int]$request.value) -gt 2) { throw '변경 뒤 읽은 밝기가 요청과 다릅니다.' }
    @{ display = $after; verified = $true; message = '화면 밝기를 바꾸고 재조회로 확인했습니다.' }
}

# ---------------------------------------------------------------- 전원
function Get-KeepAwakeRecord {
    if (-not (Test-Path $KeepAwakeFile)) { return $null }
    try { $rec = Get-Content -Path $KeepAwakeFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return $null }
    $alive = $false
    try { if ($rec.pid) { $alive = $null -ne (Get-Process -Id ([int]$rec.pid) -ErrorAction SilentlyContinue) } } catch { $alive = $false }
    @{ pid = [int]$rec.pid; seconds = [int]$rec.seconds; display = [bool]$rec.display; started_at = [string]$rec.started_at; until = [string]$rec.until; alive = $alive }
}

function Get-PowerRequests($admin) {
    # powercfg /requests 는 관리자만 읽힌다. 아니면 null 로 남긴다(거짓 0 금지).
    if (-not $admin) { return @{ flags = $null; sleep_holders = $null; requests_basis = 'powercfg_requests_requires_admin' } }
    $text = ''
    try { $text = (& powercfg.exe /requests 2>&1 | Out-String) } catch { return @{ flags = $null; sleep_holders = $null; requests_basis = 'powercfg_requests_failed' } }
    $holders = @(); $kind = $null
    foreach ($line in ($text -split "`r?`n")) {
        if ($line -match '^([A-Z]+):\s*$') { $kind = $Matches[1]; continue }
        if ($line -match '^\[(PROCESS|DRIVER|SERVICE)\]\s+(.+)$' -and $kind) { $holders += @{ kind = $kind; type = $Matches[1]; process = $Matches[2].Trim(); name = '' }; continue }
        if ($line -match '^\s+(\S.*)$' -and $holders.Count -gt 0 -and $kind) { $holders[$holders.Count - 1].name = $Matches[1].Trim() }
    }
    @{ flags = @{ PreventUserIdleDisplaySleep = @($holders | Where-Object { $_.kind -eq 'DISPLAY' }).Count; PreventUserIdleSystemSleep = @($holders | Where-Object { $_.kind -eq 'SYSTEM' }).Count; Execution = @($holders | Where-Object { $_.kind -eq 'EXECUTION' }).Count }
       sleep_holders = $holders; requests_basis = 'powercfg_requests' }
}

function Get-PowerStatus {
    $status = [System.Windows.Forms.SystemInformation]::PowerStatus
    $battery = $null
    if (-not ($status.BatteryChargeStatus -band [System.Windows.Forms.BatteryChargeStatus]::NoSystemBattery)) {
        $battery = @{ percent = [int][Math]::Round($status.BatteryLifePercent * 100); state = $status.BatteryChargeStatus.ToString()
                      remaining = $(if ($status.BatteryLifeRemaining -ge 0) { "$([int]($status.BatteryLifeRemaining / 60)) min" } else { 'unknown' }) }
    }
    $admin = Test-Admin
    $out = @{ power_source = $(if ($status.PowerLineStatus -eq 'Online') { 'AC Power' } elseif ($status.PowerLineStatus -eq 'Offline') { 'Battery Power' } else { $null })
              battery = $battery; lid_closed = $null; admin = $admin; keep_awake = (Get-KeepAwakeRecord) }
    $requests = Get-PowerRequests $admin
    foreach ($k in $requests.Keys) { $out[$k] = $requests[$k] }
    $out
}

function Start-KeepAwake($request) {
    $current = Get-KeepAwakeRecord
    if ($current -and $current.alive) { throw "이미 잠들지 않기가 켜져 있습니다(pid $($current.pid), until $($current.until)). 먼저 allow_sleep 하세요." }
    $flags = 0x80000001
    if ([bool]$request.display) { $flags = 0x80000003 }
    $seconds = [int]$request.seconds
    $child = "Add-Type -Name K -Namespace W -MemberDefinition '[DllImport(""kernel32.dll"")] public static extern uint SetThreadExecutionState(uint f);'; [W.K]::SetThreadExecutionState([uint32]$flags) | Out-Null; Start-Sleep -Seconds $seconds"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($child))
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-EncodedCommand', $encoded) -WindowStyle Hidden -PassThru
    $now = [DateTime]::UtcNow
    $rec = @{ pid = [int]$proc.Id; seconds = $seconds; display = [bool]$request.display; started_at = $now.ToString('o'); until = $now.AddSeconds($seconds).ToString('o') }
    $dir = Split-Path $KeepAwakeFile
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [IO.File]::WriteAllText($KeepAwakeFile, (ConvertTo-Json -InputObject $rec -Compress), (New-Object System.Text.UTF8Encoding($false)))
    Start-Sleep -Milliseconds 800
    $after = Get-KeepAwakeRecord
    if (-not $after -or -not $after.alive) { throw '잠들지 않기 프로세스가 살아 있지 않습니다.' }
    @{ keep_awake = $after; verified = $true; readback_basis = 'process_readback(powercfg /requests 는 관리자만)'; message = '잠들지 않기를 켜고 프로세스 생존을 확인했습니다.' }
}

function Stop-KeepAwake {
    $current = Get-KeepAwakeRecord
    if (-not $current) { return @{ keep_awake = $null; verified = $true; message = '켜 둔 잠들지 않기가 없습니다.' } }
    if ($current.alive) {
        Stop-Process -Id $current.pid -Force -ErrorAction Stop
        $gone = $false
        for ($i = 0; $i -lt 20; $i++) { if ($null -eq (Get-Process -Id $current.pid -ErrorAction SilentlyContinue)) { $gone = $true; break }; Start-Sleep -Milliseconds 100 }
        if (-not $gone) { throw '잠들지 않기 프로세스가 종료되지 않았습니다.' }
    }
    Remove-Item -Path $KeepAwakeFile -Force -ErrorAction SilentlyContinue
    @{ keep_awake = $null; verified = $true; message = '잠들지 않기를 끄고 프로세스 종료를 확인했습니다.' }
}

# ---------------------------------------------------------------- 앱
function Get-AppRows {
    $rows = @()
    foreach ($p in (Get-Process | Where-Object { $_.MainWindowHandle -ne 0 })) {
        $path = $null; $desc = $null; $product = $null
        try { $path = $p.Path } catch { $path = $null }
        try { $desc = $p.Description; $product = $p.Product } catch { }
        $rows += @{ name = $p.ProcessName; pid = [int]$p.Id; title = $p.MainWindowTitle; path = $path; description = $desc; product = $product; type = 'Window' }
    }
    ,$rows
}

function Get-AppKeys($row) {
    $keys = @(([string]$row.name).ToLower(), (([string]$row.name).ToLower() + '.exe'))
    if ($row.path) { $base = [IO.Path]::GetFileName($row.path).ToLower(); $keys += $base; $keys += [IO.Path]::GetFileNameWithoutExtension($base) }
    if ($row.description) { $keys += ([string]$row.description).ToLower() }
    if ($row.product) { $keys += ([string]$row.product).ToLower() }
    $keys | Where-Object { $_ }
}

function Match-App($rows, $wanted) {
    $want = @($wanted | ForEach-Object { ([string]$_).ToLower() } | Where-Object { $_ })
    @($rows | Where-Object { $rk = @(Get-AppKeys $_); @($want | Where-Object { $rk -contains $_ }).Count -gt 0 })
}

function Get-FrontApp {
    $h = [IndieBizPC.Native]::GetForegroundWindow()
    if ($h -eq [IntPtr]::Zero) { return $null }
    [uint32]$procId = 0
    [IndieBizPC.Native]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
    $p = Get-Process -Id ([int]$procId) -ErrorAction SilentlyContinue
    @{ pid = [int]$procId; name = $(if ($p) { $p.ProcessName } else { $null }); title = [IndieBizPC.Native]::WindowTitle($h) }
}

function Find-StartMenuShortcut($name) {
    $roots = @((Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'), (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs'))
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $hit = Get-ChildItem -Path $root -Recurse -Filter '*.lnk' -ErrorAction SilentlyContinue | Where-Object { $_.BaseName -ieq $name } | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    $null
}

function Start-App($request) {
    $name = [string]$request.app
    $wanted = @($name)
    if ($name -match '\.exe$') { $wanted += ($name -replace '\.exe$', '') }
    $before = @(Match-App (Get-AppRows) $wanted)
    $beforePids = @(Get-Process | ForEach-Object { $_.Id })
    $how = $null
    if ($name -match '!') {
        Start-Process -FilePath "shell:AppsFolder\$name"; $how = 'appsfolder'
    } else {
        $lnk = Find-StartMenuShortcut $name
        if ($lnk) {
            try { $target = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk).TargetPath; if ($target) { $wanted += [IO.Path]::GetFileName($target); $wanted += [IO.Path]::GetFileNameWithoutExtension($target) } } catch { }
            Start-Process -FilePath $lnk -WindowStyle Minimized; $how = 'start_menu_shortcut'
        } else {
            try { Start-Process -FilePath $name -WindowStyle Minimized; $how = 'start_process' }
            catch { throw ('앱을 찾지 못했거나 실행이 거절됐습니다: ' + $_.Exception.Message) }
        }
    }
    $found = @(); $matched = 'name'
    for ($i = 0; $i -lt 20; $i++) {
        $rows = Get-AppRows
        $found = @(Match-App $rows $wanted)
        if ($found.Count -eq 0 -and -not $before) {
            $new = @($rows | Where-Object { $beforePids -notcontains $_.pid })
            if ($new.Count -gt 0) { $found = $new; $matched = 'new_window_process' }
        }
        if ($found.Count -gt 0) { break }
        Start-Sleep -Milliseconds 250
    }
    if ($found.Count -eq 0) { throw '실행 요청 뒤 5초 안에 창을 가진 앱 목록에 나타나지 않았습니다.' }
    $row = $found[0]
    @{ app = @{ name = $row.name; pid = $row.pid; title = $row.title; path = $row.path; running = $true; already_running = ($before.Count -gt 0); launched_by = $how; matched_by = $matched }
       verified = $true
       message = $(if ($before.Count -gt 0) { '앱이 이미 실행 중이었습니다(앞으로 가져오지 않음).' } else { '앱이 실행 중임을 창 목록 재조회로 확인했습니다(최소화로 열기 요청, 앱이 무시할 수 있음).' }) }
}

function Stop-App($request) {
    $name = [string]$request.app
    $wanted = @($name)
    if ($name -match '\.exe$') { $wanted += ($name -replace '\.exe$', '') }
    $rows = @(Match-App (Get-AppRows) $wanted)
    if ($rows.Count -eq 0) { return @{ app = @{ name = $name; running = $false; already_stopped = $true }; verified = $true; message = '앱이 실행 중이 아니었습니다.' } }
    $asked = 0
    foreach ($row in $rows) {
        $p = Get-Process -Id $row.pid -ErrorAction SilentlyContinue
        if ($p -and $p.CloseMainWindow()) { $asked++ }
    }
    if ($asked -eq 0) { throw '앱 창에 닫기 요청을 보내지 못했습니다(창이 없거나 응답하지 않음). 강제 종료는 하지 않습니다.' }
    for ($i = 0; $i -lt 32; $i++) {
        if (@(Match-App (Get-AppRows) $wanted).Count -eq 0) {
            return @{ app = @{ name = $rows[0].name; path = $rows[0].path; running = $false }; verified = $true; message = '앱 종료를 창 목록 재조회로 확인했습니다.' }
        }
        Start-Sleep -Milliseconds 250
    }
    throw '닫기 요청을 보냈지만 8초 안에 앱이 사라지지 않았습니다(저장 확인 창이 떠 있을 수 있음).'
}

# ---------------------------------------------------------------- 클립보드
function Read-ClipboardText {
    $text = $null
    try { $text = Get-Clipboard -Raw -ErrorAction Stop } catch { $text = $null }
    if ($null -eq $text) { $text = '' }
    [string]$text
}

function Write-ClipboardText($request) {
    $text = [string]$request.text
    if ($text.Length -eq 0) { [System.Windows.Forms.Clipboard]::Clear() } else { Set-Clipboard -Value $text }
    $after = Read-ClipboardText
    if ($after -ne $text) { throw '클립보드에 쓴 뒤 읽은 내용이 다릅니다.' }
    @{ length = $text.Length; verified = $true; message = '클립보드에 쓰고 재조회로 확인했습니다.' }
}

# ---------------------------------------------------------------- 네트워크 (WinRT Radios: 관리자 없이 전원 전환)
$script:WinRtReady = $false
function Initialize-WinRt {
    if ($script:WinRtReady) { return $true }
    try {
        Add-Type -AssemblyName System.Runtime.WindowsRuntime -ErrorAction Stop
        $null = [Windows.Devices.Radios.Radio, Windows.System.Devices, ContentType = WindowsRuntime]
        $null = [Windows.Devices.Radios.RadioState, Windows.System.Devices, ContentType = WindowsRuntime]
        $null = [Windows.Devices.Enumeration.DeviceInformation, Windows.Devices.Enumeration, ContentType = WindowsRuntime]
        $null = [Windows.Devices.Bluetooth.BluetoothDevice, Windows.Devices.Bluetooth, ContentType = WindowsRuntime]
        $null = [Windows.Devices.Bluetooth.BluetoothLEDevice, Windows.Devices.Bluetooth, ContentType = WindowsRuntime]
        $script:AsTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
        $script:WinRtReady = $true
    } catch { $script:WinRtReady = $false }
    $script:WinRtReady
}
function Wait-WinRt($operation, $type, $timeoutMs = 8000) {
    $task = $script:AsTask.MakeGenericMethod($type).Invoke($null, @($operation))
    if (-not $task.Wait($timeoutMs)) { try { $operation.Cancel() } catch { }; throw "WinRT 호출이 $($timeoutMs)ms 안에 끝나지 않았습니다." }
    $task.Result
}
function Get-Radios {
    if (-not (Initialize-WinRt)) { return $null }
    $access = Wait-WinRt ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus])
    if ("$access" -ne 'Allowed') { throw "라디오 접근이 허용되지 않았습니다($access)." }
    @(Wait-WinRt ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]]))
}

function Get-WifiStatus($radios) {
    $text = ''
    try { $text = (& netsh.exe wlan show interfaces 2>&1 | Out-String) } catch { $text = '' }
    $port = $null; $ssid = $null; $state = $null; $software = $null
    if ($text -match '(?m)^\s*Name\s*:\s*(.+?)\s*$') { $port = $Matches[1] }
    if ($text -match '(?m)^\s*State\s*:\s*(.+?)\s*$') { $state = $Matches[1] }
    if ($text -match '(?m)^\s*SSID\s*:\s*(.+?)\s*$') { $ssid = $Matches[1] }
    if ($text -match '(?m)^\s*Radio status\s*:\s*Hardware (\w+)\s*\r?\n\s*Software (\w+)') { $software = ($Matches[1] -eq 'On') -and ($Matches[2] -eq 'On') }
    $enabled = $null; $basis = 'netsh_wlan_radio_status'
    $radio = $null
    if ($radios) { $radio = $radios | Where-Object { "$($_.Kind)" -eq 'WiFi' } | Select-Object -First 1 }
    if ($radio) { $enabled = ("$($radio.State)" -eq 'On'); $basis = 'winrt_radio_state'; if (-not $port) { $port = $radio.Name } }
    elseif ($null -ne $software) { $enabled = $software }
    if (-not $port -and -not $radio) { return @{ port = $null; enabled = $null; ssid = $null; message = 'Wi-Fi 장치가 없습니다.' } }
    @{ port = $port; enabled = $enabled; ssid = $(if ($state -eq 'connected') { $ssid } else { $null }); state = $state; enabled_basis = $basis; ssid_basis = 'netsh_wlan_show_interfaces' }
}

function Get-BluetoothStatus($radios) {
    $enabled = $null
    if ($radios) { $radio = $radios | Where-Object { "$($_.Kind)" -eq 'Bluetooth' } | Select-Object -First 1; if ($radio) { $enabled = ("$($radio.State)" -eq 'On') } }
    $connected = @(); $basis = 'unavailable'
    if ($script:WinRtReady) {
        # 공식 연결 상태 선택자(0.6초 실측). Aep AQS 3인자 열거는 tv1 실측에서 8초 넘게 멈춰 쓰지 않는다.
        try {
            $status = [Windows.Devices.Bluetooth.BluetoothConnectionStatus]::Connected
            $selectors = @(@{ type = 'Classic'; aqs = [Windows.Devices.Bluetooth.BluetoothDevice]::GetDeviceSelectorFromConnectionStatus($status) },
                           @{ type = 'LE'; aqs = [Windows.Devices.Bluetooth.BluetoothLEDevice]::GetDeviceSelectorFromConnectionStatus($status) })
            foreach ($sel in $selectors) {
                $found = Wait-WinRt ([Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync([string]$sel.aqs)) ([Windows.Devices.Enumeration.DeviceInformationCollection]) 6000
                foreach ($d in $found) { $connected += @{ name = $d.Name; address = $d.Id; type = $sel.type; battery = $null } }
            }
            $basis = 'winrt_bluetooth_connection_status_selector'
        } catch { $connected = $null; $basis = 'winrt_enumeration_failed: ' + $_.Exception.Message }
    }
    @{ enabled = $enabled; connected = $connected; connected_basis = $basis }
}

function Get-NetworkStatus {
    $radios = $null
    try { $radios = Get-Radios } catch { $radios = $null }
    @{ wifi = (Get-WifiStatus $radios); bluetooth = (Get-BluetoothStatus $radios); verified = $true
       message = 'Wi-Fi 전원·연결 이름과 블루투스 연결 기기를 읽었습니다. 블루투스 연결·해제는 지원하지 않습니다.' }
}

function Set-Wifi($request) {
    $radios = Get-Radios
    if ($null -eq $radios) { throw '이 Windows 에서 라디오 제어(WinRT) 를 열지 못했습니다.' }
    $radio = $radios | Where-Object { "$($_.Kind)" -eq 'WiFi' } | Select-Object -First 1
    if (-not $radio) { throw 'Wi-Fi 장치가 없습니다.' }
    $want = $(if ([bool]$request.enabled) { [Windows.Devices.Radios.RadioState]::On } else { [Windows.Devices.Radios.RadioState]::Off })
    $status = Wait-WinRt ($radio.SetStateAsync($want)) ([Windows.Devices.Radios.RadioAccessStatus])
    if ("$status" -ne 'Allowed') { throw "Wi-Fi 전원 변경이 거절됐습니다($status)." }
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Milliseconds 300
        $after = Get-WifiStatus (Get-Radios)
        if ($after.enabled -eq [bool]$request.enabled) { return @{ wifi = $after; verified = $true; message = 'Wi-Fi 전원을 바꾸고 재조회로 확인했습니다.' } }
    }
    throw '변경 뒤 읽은 Wi-Fi 전원 상태가 요청과 다릅니다.'
}

# ---------------------------------------------------------------- 단축어 = 작업 스케줄러 루트 폴더의 작업(사용자가 이름 붙인 자동화)
function Get-ShortcutTasks { @(Get-ScheduledTask -TaskPath '\' -ErrorAction SilentlyContinue) }
function Get-ShortcutList {
    $tasks = @(Get-ShortcutTasks)
    $names = @($tasks | ForEach-Object { $_.TaskName })
    @{ shortcuts = $names; count = $names.Count; verified = $true
       shortcuts_basis = 'task_scheduler_root_folder'
       message = '작업 스케줄러 루트 폴더의 작업 이름 목록(Windows 의 단축어 자리). 작업 스케줄러에서 만든 작업을 이름으로 부른다.' }
}
function Invoke-Shortcut($request) {
    $task = Get-ShortcutTasks | Where-Object { $_.TaskName -eq [string]$request.name } | Select-Object -First 1
    if (-not $task) { throw '그 이름의 작업이 없습니다. shortcuts 로 목록을 조회하세요.' }
    if ($task.State -eq 'Disabled') { throw '그 작업은 사용 안 함 상태입니다.' }
    Start-ScheduledTask -InputObject $task -ErrorAction Stop
    $finished = $false
    for ($i = 0; $i -lt 160; $i++) {
        Start-Sleep -Milliseconds 500
        $now = Get-ScheduledTask -TaskName $task.TaskName -TaskPath '\' -ErrorAction SilentlyContinue
        if ($now -and $now.State -ne 'Running') { $finished = $true; break }
    }
    if (-not $finished) { throw '작업이 80초 안에 끝나지 않았습니다(계속 실행 중일 수 있음).' }
    $info = Get-ScheduledTaskInfo -TaskName $task.TaskName -TaskPath '\'
    $code = [int]$info.LastTaskResult
    if ($code -ne 0) { throw "작업이 오류로 끝났습니다($code)." }
    @{ name = $task.TaskName; output = ''; exit = 0; last_run = $(if ($info.LastRunTime) { $info.LastRunTime.ToUniversalTime().ToString('o') } else { $null }); verified = $false
       message = '작업이 정상 종료했습니다(LastTaskResult 0). 작업 안의 효과는 확인 범위 밖입니다.' }
}

# ---------------------------------------------------------------- 입회
function Get-Presence {
    $session = Get-SessionState
    $idle = [IndieBizPC.Native]::IdleSeconds()
    @{ idle_seconds = $(if ($idle -ge 0) { [Math]::Round($idle, 1) } else { $null }); front = (Get-FrontApp); screen_locked = $session.screen_locked; on_console = $session.on_console
       session_basis = $session.session_basis; display_asleep = $null; verified = $true
       message = '마지막 입력 뒤 경과 초·앞 창·화면 잠금. 화면 꺼짐은 Windows 공개 API 로 읽지 못해 null. 사용자가 보고 있는지의 판단 재료이지 판정이 아닙니다.' }
}

function Invoke-HostAction($request) {
    switch ($request.action) {
        'display' { $s = Get-SessionState; return @{ displays = (Get-Displays); screen_locked = $s.screen_locked; on_console = $s.on_console; session_basis = $s.session_basis; verified = $true; message = '화면 목록과 세션 상태를 읽었습니다.' } }
        'brightness' { return Set-Brightness $request }
        'power' { $p = Get-PowerStatus; $p.verified = $true; $p.message = '전원·배터리·잠 방지 상태를 읽었습니다.'; return $p }
        'presence' { return Get-Presence }
        'apps' { $rows = Get-AppRows; return @{ front = (Get-FrontApp); apps = @($rows | ForEach-Object { @{ name = $_.name; pid = $_.pid; title = $_.title; path = $_.path; type = $_.type } }); background_count = (@(Get-Process).Count - $rows.Count); verified = $true; message = '앞 창과 창을 가진 앱 목록(창 없는 프로세스는 개수만).' } }
        'launch' { return Start-App $request }
        'quit' { return Stop-App $request }
        'clipboard' { $t = Read-ClipboardText; $limit = 100000; return @{ text = $t.Substring(0, [Math]::Min($t.Length, $limit)); length = $t.Length; truncated = ($t.Length -gt $limit); verified = $true; message = '클립보드 글을 읽었습니다(글 아닌 내용은 비어 보일 수 있음).' } }
        'clipboard_write' { return Write-ClipboardText $request }
        'network' { return Get-NetworkStatus }
        'wifi' { return Set-Wifi $request }
        'shortcuts' { return Get-ShortcutList }
        'shortcut' { return Invoke-Shortcut $request }
        'keep_awake' { return Start-KeepAwake $request }
        'allow_sleep' { return Stop-KeepAwake }
        'sleep' { [System.Windows.Forms.Application]::SetSuspendState([System.Windows.Forms.PowerState]::Suspend, $false, $false) | Out-Null; return @{ verified = $false; message = '잠자기를 요청했습니다. 실제로 잠들었는지는 확인 범위 밖입니다.' } }
    }
    $null
}

try {
    if ($env:OS -ne 'Windows_NT') { throw 'Windows 전용 실행 파일입니다.' }
    $result.hostname = $env:COMPUTERNAME
    $result.os_version = [Environment]::OSVersion.Version.ToString()
    $result.observed_at = [DateTime]::UtcNow.ToString('o')
    $result.can_lock = $true
    if ($PcRequest.action -in @('status','volume','mute')) {
        Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
namespace IndieBizPC {
 [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class Enumerator {}
 [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IEnum {
  [PreserveSig] int EnumAudioEndpoints(int flow, uint mask, out ICollection devices);
  [PreserveSig] int GetDefaultAudioEndpoint(int flow, int role, out IDevice device);
  [PreserveSig] int GetDevice([MarshalAs(UnmanagedType.LPWStr)] string id, out IDevice device);
 }
 [ComImport, Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface ICollection {
  [PreserveSig] int GetCount(out uint count);
  [PreserveSig] int Item(uint index, out IDevice device);
 }
 [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IDevice {
  [PreserveSig] int Activate(ref Guid iid, uint context, IntPtr parameters, [MarshalAs(UnmanagedType.IUnknown)] out object value);
  [PreserveSig] int OpenPropertyStore(uint access, out IProperties properties);
  [PreserveSig] int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
  [PreserveSig] int GetState(out uint state);
 }
 [StructLayout(LayoutKind.Sequential)] struct Key { public Guid guid; public uint id; }
 [StructLayout(LayoutKind.Explicit, Size=24)] struct Variant {
  [FieldOffset(0)] public ushort type;
  [FieldOffset(8)] public IntPtr pointer;
 }
 [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IProperties {
  [PreserveSig] int GetCount(out uint count);
  [PreserveSig] int GetAt(uint index, out Key key);
  [PreserveSig] int GetValue(ref Key key, out Variant value);
 }
 [ComImport, Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
 interface IVolume {
  [PreserveSig] int RegisterControlChangeNotify(IntPtr notify);
  [PreserveSig] int UnregisterControlChangeNotify(IntPtr notify);
  [PreserveSig] int GetChannelCount(out uint channels);
  [PreserveSig] int SetMasterVolumeLevel(float db, ref Guid context);
  [PreserveSig] int SetMasterVolumeLevelScalar(float level, ref Guid context);
  [PreserveSig] int GetMasterVolumeLevel(out float db);
  [PreserveSig] int GetMasterVolumeLevelScalar(out float level);
  [PreserveSig] int SetChannelVolumeLevel(uint channel, float db, ref Guid context);
  [PreserveSig] int SetChannelVolumeLevelScalar(uint channel, float level, ref Guid context);
  [PreserveSig] int GetChannelVolumeLevel(uint channel, out float db);
  [PreserveSig] int GetChannelVolumeLevelScalar(uint channel, out float level);
  [PreserveSig] int SetMute([MarshalAs(UnmanagedType.Bool)] bool mute, ref Guid context);
  [PreserveSig] int GetMute([MarshalAs(UnmanagedType.Bool)] out bool mute);
 }
 public class Output {
  public string id, name, capability_basis;
  public int volume;
  public bool muted, is_default, can_set_volume, can_mute;
 }
 public static class Audio {
  [DllImport("ole32.dll")] static extern int PropVariantClear(ref Variant value);
  static void Check(int status) { Marshal.ThrowExceptionForHR(status); }
  static void Release(object value) { if(value != null && Marshal.IsComObject(value)) Marshal.ReleaseComObject(value); }
  static string Id(IDevice device) { string id; Check(device.GetId(out id)); return id; }
  static IVolume Volume(IDevice device) {
   Guid iid=typeof(IVolume).GUID; object value; Check(device.Activate(ref iid,23,IntPtr.Zero,out value)); return (IVolume)value;
  }
  static string Name(IDevice device) {
   IProperties store=null;
   try {
    Check(device.OpenPropertyStore(0,out store));
    Key key=new Key { guid=new Guid("a45c254e-df1c-4efd-8020-67d146a850e0"), id=14 };
    Variant value; Check(store.GetValue(ref key,out value));
    try { return value.type==31 ? Marshal.PtrToStringUni(value.pointer) : Id(device); }
    finally { PropVariantClear(ref value); }
   } finally { Release(store); }
  }
  static Output Read(IDevice device, string defaultId) {
   IVolume audio=null;
   try {
    uint state; Check(device.GetState(out state)); if(state!=1) throw new InvalidOperationException("출력 장치가 연결되지 않았습니다.");
    audio=Volume(device); float level; bool mute; Check(audio.GetMasterVolumeLevelScalar(out level)); Check(audio.GetMute(out mute));
    string id=Id(device);
    // EndpointVolume provides OS controls, including software fallback. No setter is called by status.
    return new Output {id=id, name=Name(device), volume=(int)Math.Round(level*100), muted=mute, is_default=id==defaultId,
                       can_set_volume=true, can_mute=true, capability_basis="wasapi_endpoint_volume_interface"};
   } finally { Release(audio); }
  }
  public static Output[] List() {
   IEnum enumerator=null; ICollection collection=null; IDevice defaultDevice=null;
   try {
    enumerator=(IEnum)new Enumerator(); string defaultId=null;
    if(enumerator.GetDefaultAudioEndpoint(0,1,out defaultDevice)>=0) defaultId=Id(defaultDevice);
    Check(enumerator.EnumAudioEndpoints(0,1,out collection)); uint count; Check(collection.GetCount(out count));
    var rows=new List<Output>();
    for(uint i=0;i<count;i++) { IDevice device=null; try { Check(collection.Item(i,out device)); rows.Add(Read(device,defaultId)); } finally { Release(device); } }
    return rows.ToArray();
   } finally { Release(defaultDevice); Release(collection); Release(enumerator); }
  }
  public static Output Change(string id, string action, int level, bool muted) {
   IEnum enumerator=null; IDevice device=null; IVolume audio=null;
   try {
    if(String.IsNullOrWhiteSpace(id)) throw new ArgumentException("출력 장치를 지정하세요.");
    if(action!="volume" && action!="mute") throw new ArgumentException("알 수 없는 동작입니다.");
    if(level<0 || level>100) throw new ArgumentException("음량 범위는 0~100입니다.");
    enumerator=(IEnum)new Enumerator(); Check(enumerator.GetDevice(id,out device));
    Read(device,null); audio=Volume(device); Guid context=Guid.Empty;
    if(action=="volume") Check(audio.SetMasterVolumeLevelScalar(level/100f,ref context));
    else Check(audio.SetMute(muted,ref context));
    Output after=Read(device,null);
    if(action=="volume" ? Math.Abs(after.volume-level)>1 : after.muted!=muted) throw new InvalidOperationException("설정값을 확인하지 못했습니다.");
    return after;
   } finally { Release(audio); Release(device); Release(enumerator); }
  }
 }
}
'@
        if ($PcRequest.action -eq 'status') {
            try { $result.devices = @([IndieBizPC.Audio]::List()) }
            catch { $result.devices = @(); $result.audio_error = $_.Exception.Message }
            $result.message = 'Windows PC 상태를 조회했습니다.'
        } else {
            $result.device = [IndieBizPC.Audio]::Change([string]$PcRequest.device_id, [string]$PcRequest.action, [int]$PcRequest.value, [bool]$PcRequest.enabled)
            $result.devices = @([IndieBizPC.Audio]::List())
            $result.message = '출력 장치의 실제 설정값을 확인했습니다.'
        }
        $result.verified = $true
    } elseif ($PcRequest.action -eq 'open_url') {
        $uri = [Uri]$PcRequest.url
        if ($uri.Scheme -notin @('http','https') -or $uri.UserInfo) { throw '허용하지 않는 웹 주소입니다.' }
        Start-Process -FilePath $uri.AbsoluteUri
        $result.message = '기본 브라우저에 주소 열기를 요청했습니다. 로딩·재생은 확인하지 않았습니다.'
    } elseif ($PcRequest.action -eq 'lock') {
        if (-not [IndieBizPC.Native]::LockWorkStation()) { throw '화면 잠금 요청이 거절됐습니다.' }
        $locked = $null
        for ($i = 0; $i -lt 12; $i++) { Start-Sleep -Milliseconds 250; $locked = (Get-SessionState).screen_locked; if ($locked) { break } }
        $result.screen_locked = $locked
        $result.verified = ($locked -eq $true)
        $result.message = $(if ($locked -eq $true) { '화면 잠금을 세션 상태 재조회로 확인했습니다.' } else { '화면 잠금을 요청했지만 3초 안에 잠금 상태를 읽지 못했습니다.' })
    } else {
        $host_ = Invoke-HostAction $PcRequest
        if ($null -eq $host_) { throw '지원하지 않는 동작입니다.' }
        foreach ($k in $host_.Keys) { $result[$k] = $host_[$k] }
    }
    $result.success = $true
} catch {
    $result.error = $_.Exception.Message
}
Write-Output ('INDIEBIZ_PC_RESULT:' + (ConvertTo-Json -InputObject $result -Depth 7 -Compress))
