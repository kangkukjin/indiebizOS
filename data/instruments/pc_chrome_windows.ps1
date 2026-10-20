# Windows Chrome 창·탭 드라이버 — 조작면 app:com.google.Chrome, 통로 = CDP(DevTools 프로토콜) **전용 프로필**.
# CONTROL_DRIVER_DESIGN_2026_10_20 §18. 맥 Chrome제어(AppleScript)와 같은 계약(status/open/switch/close·expected 판본·verified 재조회).
# Chrome 136+ 는 기본 프로필의 원격 디버깅을 거부하므로 %LOCALAPPDATA%\IndieBiz\ChromeProfile 을 전용 프로필로 쓰고
# 포트는 Chrome 이 쓰는 DevToolsActivePort 파일에서 읽는다(--remote-debugging-port=0). 다른 프로필 크롬(사용자가 띄운 것)은 보지 않는다.
# 탭 신원 = CDP targetId(영구). 탭 순서는 CDP 가 주지 않으므로 tabs 는 id 순이고 tab 인수는 위치가 아니라 targetId 다.
# 현재 탭 = 그 창에서 document.visibilityState 가 visible 인 탭(최소화 창은 전부 hidden → current_tab null).
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$result = @{ protocol='pc-control/1'; platform='windows'; action=$PcRequest.action; request_id=$PcRequest.request_id;
             success=$false; verified=$false; surface='app:com.google.Chrome'; driver='cdp_dedicated_profile'; page_loaded=$null }
$ProfileDir = Join-Path $env:LOCALAPPDATA 'IndieBiz\ChromeProfile'
$PortFile = Join-Path $ProfileDir 'DevToolsActivePort'
$script:Ws = $null; $script:Seq = 0; $script:EffectStarted = $false

function Fail($code, $message, $next, $state) {
    $result.failure = @{ code=$code; message=$message; next=$next }
    if ($null -ne $state) { $result.failure.state = $state }
    throw ("{0}: {1}" -f $code, $message)
}

# ---------------------------------------------------------------- CDP 클라이언트 (ClientWebSocket, Origin 헤더 없음)
function Connect-Cdp {
    if (-not (Test-Path $PortFile)) { return $null }
    $lines = @(Get-Content $PortFile)
    if ($lines.Count -lt 2) { return $null }
    $port = [int]$lines[0]; $path = $lines[1]
    try { $ver = Invoke-RestMethod -Uri "http://127.0.0.1:$port/json/version" -TimeoutSec 3 } catch { return $null }
    $ws = New-Object System.Net.WebSockets.ClientWebSocket
    $cts = New-Object System.Threading.CancellationTokenSource(5000)
    # PS 5.1 은 void Task 의 GetResult() 도 VoidTaskResult 를 출력으로 흘린다 — [void] 가 없으면 함수 반환이 배열이 된다(TV1 실측).
    [void]$ws.ConnectAsync([Uri]("ws://127.0.0.1:{0}{1}" -f $port, $path), $cts.Token).GetAwaiter().GetResult()
    $script:Ws = $ws
    return @{ port=$port; browser=$ver.Browser; protocol_version=$ver.'Protocol-Version' }
}
function Send-Cdp($method, $params, $sessionId, $timeoutMs = 10000) {
    $script:Seq++; $id = $script:Seq
    $msg = @{ id=$id; method=$method; params=$(if ($params) { $params } else { @{} }) }
    if ($sessionId) { $msg.sessionId = $sessionId }
    $bytes = [Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $msg -Depth 6 -Compress))
    $cts = New-Object System.Threading.CancellationTokenSource($timeoutMs)
    [void]$script:Ws.SendAsync([ArraySegment[byte]]::new($bytes), [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $cts.Token).GetAwaiter().GetResult()
    $buf = New-Object byte[] 65536
    $deadline = [DateTime]::UtcNow.AddMilliseconds($timeoutMs)
    while ($true) {
        $ms = New-Object System.IO.MemoryStream
        do {
            $left = [int][Math]::Max(1, ($deadline - [DateTime]::UtcNow).TotalMilliseconds)
            $rcts = New-Object System.Threading.CancellationTokenSource($left)
            $r = $script:Ws.ReceiveAsync([ArraySegment[byte]]::new($buf), $rcts.Token).GetAwaiter().GetResult()
            $ms.Write($buf, 0, $r.Count)
        } while (-not $r.EndOfMessage)
        $o = [Text.Encoding]::UTF8.GetString($ms.ToArray()) | ConvertFrom-Json
        if ($o.id -eq $id) {
            if ($o.error) { throw ("CDP {0}: {1}" -f $method, $o.error.message) }
            return $o.result
        }
        if ([DateTime]::UtcNow -gt $deadline) { throw ("CDP {0}: 응답 대기 시간 초과" -f $method) }
    }
}
function Get-Pages { @((Send-Cdp 'Target.getTargets').targetInfos | Where-Object { $_.type -eq 'page' }) }
function Get-Visibility($tid) {
    $s = (Send-Cdp 'Target.attachToTarget' @{ targetId=$tid; flatten=$true }).sessionId
    try { return (Send-Cdp 'Runtime.evaluate' @{ expression='document.visibilityState'; returnByValue=$true } $s 5000).result.value }
    finally { try { [void](Send-Cdp 'Target.detachFromTarget' @{ sessionId=$s } $null 3000) } catch {} }
}
function Get-Revision($w) {
    $text = '{0}|{1}|{2}' -f $w.window_id, $w.current_tab, (@($w.tabs | ForEach-Object { $_.tab_id }) -join ',')
    $sha = [Security.Cryptography.SHA256]::Create()
    return (($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text)) | ForEach-Object { $_.ToString('x2') }) -join '')
}
function Get-Snapshot($windowId) {
    $wins = @{}
    foreach ($t in Get-Pages) {
        try { $w = Send-Cdp 'Browser.getWindowForTarget' @{ targetId=$t.targetId } } catch { continue }   # 그 사이 사라진 탭
        $wid = [int64]$w.windowId
        if ($null -ne $windowId -and $wid -ne [int64]$windowId) { continue }
        if (-not $wins.ContainsKey($wid)) { $wins[$wid] = @{ window_id=$wid; state=$w.bounds.windowState; tabs=@(); current_tab=$null } }
        $vis = $null
        try { $vis = Get-Visibility $t.targetId } catch { $vis = $null }
        $wins[$wid].tabs += ,@{ tab_id=$t.targetId; url=$t.url; name=$t.title }
        if ($vis -eq 'visible') { $wins[$wid].current_tab = $t.targetId }
    }
    $out = @()
    foreach ($wid in ($wins.Keys | Sort-Object)) {
        $w = $wins[$wid]
        $w.tabs = @($w.tabs | Sort-Object { $_.tab_id })
        $w.tab_count = $w.tabs.Count
        $w.revision = Get-Revision $w
        $out += ,$w
    }
    return $out   # 열거로 내보낸다 — 호출부는 반드시 @( ) 로 받는다(빈 결과·단일 결과·중첩 배열 함정, TV1 실측)
}
function Find-Window($wins, $windowId) {
    if ($null -eq $windowId) { if ($wins.Count -eq 0) { return $null }; return $wins[0] }
    foreach ($w in $wins) { if ($w.window_id -eq [int64]$windowId) { return $w } }
    Fail 'TARGET_MISSING' ("창 {0} 이 없습니다." -f $windowId) 'chrome_status 의 window_id 를 쓰세요.'
}
function Select-Target {
    $wins = @(Get-Snapshot $PcRequest.window_id)
    $target = Find-Window $wins $PcRequest.window_id
    if ($PcRequest.expected -and ($null -eq $target -or $PcRequest.expected -ne $target.revision)) {
        Fail 'STATE_CHANGED' '관측 이후 창의 탭 구성(탭 id 집합) 또는 현재 탭이 바뀌었습니다.' '새 상태에서 대상을 다시 선택하세요.' $target
    }
    return @{ wins=$wins; target=$target }
}
function Set-Result($fields) { foreach ($k in $fields.Keys) { $result[$k] = $fields[$k] } }
function Target-Of($w, $tab) {
    if ($null -eq $w) { return $null }
    $id = $(if ($tab) { $tab } else { $w.current_tab })
    if (-not $id -or -not @($w.tabs | Where-Object { $_.tab_id -eq $id })) { return $null }
    return @{ window_id=$w.window_id; tab=$id; expected=$w.revision }
}
function Before-Of($w) { if ($null -eq $w) { return $null }; return @{ window_id=$w.window_id; current_tab=$w.current_tab; tab_count=$w.tab_count; revision=$w.revision } }
function Ids($w) { @($w.tabs | ForEach-Object { $_.tab_id }) }

# ---------------------------------------------------------------- 기동(전용 프로필)
function Find-Chrome {
    foreach ($p in @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
                     "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")) { if (Test-Path $p) { return $p } }
    Fail 'TARGET_MISSING' 'chrome.exe 를 찾지 못했습니다.' 'Chrome 설치 경로를 확인하세요.'
}
function Start-ChromeProfile($url) {
    $exe = Find-Chrome
    New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
    if (Test-Path $PortFile) { Remove-Item $PortFile -Force }
    $args = @(('--user-data-dir="{0}"' -f $ProfileDir), '--remote-debugging-port=0', '--no-first-run', '--no-default-browser-check',
              '--disable-session-crashed-bubble', $(if ($url) { '"{0}"' -f $url } else { 'about:blank' }))
    $script:EffectStarted = $true
    $proc = Start-Process -FilePath $exe -ArgumentList $args -WindowStyle Minimized -PassThru
    $info = $null
    for ($i = 0; $i -lt 80; $i++) { Start-Sleep -Milliseconds 250; $info = Connect-Cdp; if ($info) { break } }
    if (-not $info) { Fail 'UNKNOWN' 'Chrome 을 띄웠지만 20초 안에 DevTools 포트가 열리지 않았습니다.' 'chrome_status 로 다시 확인하세요. 재전송하지 마세요.' }
    $info.pid = $proc.Id; $info.profile_dir = $ProfileDir
    return $info
}
function New-DesktopShortcut {
    $exe = Find-Chrome
    $lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'IndieBiz Chrome.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $s = $shell.CreateShortcut($lnk)
    $s.TargetPath = $exe
    $s.Arguments = ('--user-data-dir="{0}" --remote-debugging-port=0 --no-first-run --no-default-browser-check' -f $ProfileDir)
    $s.WorkingDirectory = Split-Path $exe
    $s.Description = 'IndieBiz 가 제어하는 전용 프로필 Chrome'
    $s.Save()
    return $lnk
}
function Other-Chrome-Count {
    try { return @(Get-CimInstance Win32_Process -Filter "name='chrome.exe'" | Where-Object { $_.CommandLine -notmatch '--type=' -and $_.CommandLine -notmatch 'IndieBiz\\ChromeProfile' }).Count } catch { return $null }
}

# ---------------------------------------------------------------- 동작
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Windows 전용 실행 파일입니다.' }
    $action = $PcRequest.action
    $result.condition = @{ needs_front=$false; shared_state=($action -in @('chrome_launch','chrome_switch','chrome_close')); isolated_resources=@('profile:IndieBiz\ChromeProfile') }
    $result.verification_scope = $(if ($action -eq 'chrome_status') { 'cdp_target_readback' } elseif ($action -eq 'chrome_launch') { 'devtools_port_readback' } else { 'cdp_target_readback' })
    $info = Connect-Cdp
    $result.running = [bool]$info
    $result.other_chrome_instances = Other-Chrome-Count

    if ($action -eq 'chrome_launch') {
        if ($info) { Set-Result @{ already_running=$true; verified=$true; browser=$info.browser; port=$info.port; profile_dir=$ProfileDir } }
        else {
            $info = Start-ChromeProfile $PcRequest.url
            Set-Result @{ already_running=$false; verified=$true; browser=$info.browser; port=$info.port; pid=$info.pid; profile_dir=$ProfileDir; running=$true }
        }
        if ($PcRequest.shortcut -eq $true) { $result.shortcut = New-DesktopShortcut }
        $result.windows = @(Get-Snapshot $null)
        $result.window_count = $result.windows.Count
        $result.message = '전용 프로필 Chrome 의 DevTools 포트를 확인했습니다. 창은 최소화로 요청했습니다.'
    }
    elseif ($action -eq 'chrome_status') {
        $wins = @($(if ($info) { Get-Snapshot $PcRequest.window_id } else { @() }))   # $() 는 빈 배열을 null 로 푼다(TV1 실측)
        $state = $(if ($PcRequest.window_id) { Find-Window $wins $PcRequest.window_id } else { $null })
        Set-Result @{ verified=$true; windows=$wins; window_count=$wins.Count; scope=$(if ($PcRequest.window_id) { 'window' } else { 'all' }); browser=$(if ($info) { $info.browser } else { $null });
                      before=$null; state=$state; target=(Target-Of $state $null) }
    }
    elseif ($action -eq 'chrome_open') {
        if (-not $info) {
            if ($PcRequest.launch -ne $true) { Fail 'TARGET_MISSING' '전용 프로필 Chrome 이 실행 중이 아닙니다.' 'chrome_launch 를 먼저 보내거나 chrome_open 에 launch:true 를 지정하세요.' }
            $info = Start-ChromeProfile $PcRequest.url
            $wins = @(Get-Snapshot $null)
            $created = $(if ($wins.Count -ge 1) { $wins[0] } else { $null })
            $tab = $(if ($created -and $created.tab_count -eq 1) { $created.tabs[0] } else { $null })
            $ok = [bool]($tab -and $tab.url -eq $PcRequest.url)
            Set-Result @{ verified=$ok; window_created=$true; launched=$true; window_id=$(if ($created) { $created.window_id } else { $null }); tab=$(if ($tab) { $tab.tab_id } else { $null }); tab_id=$(if ($tab) { $tab.tab_id } else { $null });
                          requested_url=$PcRequest.url; observed_url=$(if ($tab) { $tab.url } else { $null }); before=$null; state=$created; target=(Target-Of $created $(if ($tab) { $tab.tab_id } else { $null }));
                          checks=@{ created_tab_identified=$ok; existing_state_preserved=$ok; requested_url_observed=$ok; background_created=$false } }
            if (-not $ok) { Fail 'POSTCONDITION_FAILED' 'Chrome 을 띄웠지만 요청 주소의 탭을 확인하지 못했습니다.' '반환된 상태를 확인하세요. 재전송하지 마세요.' $created }
        } else {
            $sel = Select-Target; $target = $sel.target
            $script:EffectStarted = $true
            $params = @{ url=$PcRequest.url; background=$true }
            if ($null -eq $target) { $params.newWindow = $true }
            $newId = $null; $lost = $false
            try { $newId = (Send-Cdp 'Target.createTarget' $params $null 15000).targetId } catch { $lost = $true }
            Start-Sleep -Milliseconds 300
            $after = @(Get-Snapshot $(if ($target) { $target.window_id } else { $null }))
            if ($null -eq $target) {
                $created = $(if ($after.Count -eq 1) { $after[0] } else { $null })
                $added = $(if ($created -and $created.tab_count -eq 1) { @($created.tabs) } else { @() })
                $preserved = [bool]($created -and $added.Count -eq 1)
            } else {
                $created = $(if ($after.Count -eq 1) { $after[0] } else { $null })
                $beforeIds = Ids $target
                $added = @($(if ($created) { $created.tabs | Where-Object { $beforeIds -notcontains $_.tab_id } } else { @() }))
                $preserved = [bool]($created -and $created.tab_count -eq $target.tab_count + 1 -and
                                    (Compare-Object $beforeIds @($(Ids $created) | Where-Object { $beforeIds -contains $_ })).Count -eq 0 -and
                                    $created.current_tab -eq $target.current_tab)
            }
            $tab = $(if ($added.Count -eq 1) { $added[0] } else { $null })
            $identified = [bool]($tab -and (($newId -and $tab.tab_id -eq $newId) -or (-not $newId -and $tab.url -eq $PcRequest.url)))
            Set-Result @{ response_lost=$lost; window_created=($null -eq $target); requested_url=$PcRequest.url; observed_url=$(if ($tab) { $tab.url } else { $null });
                          window_id=$(if ($created) { $created.window_id } else { $null }); tab=$(if ($tab) { $tab.tab_id } else { $null }); tab_id=$(if ($tab) { $tab.tab_id } else { $null });
                          current_tab=$(if ($created) { $created.current_tab } else { $null }); current_tab_unchanged=$(if ($target -and $created) { $created.current_tab -eq $target.current_tab } else { $null });
                          before=(Before-Of $target); state=$created; target=(Target-Of $created $(if ($tab) { $tab.tab_id } else { $null }));
                          checks=@{ created_tab_identified=$identified; existing_state_preserved=$preserved; requested_url_observed=[bool]($tab -and $tab.url -eq $PcRequest.url); creation_receipt=[bool]($newId -and $tab -and $tab.tab_id -eq $newId); background_created=[bool]($target -and $created -and $created.current_tab -eq $target.current_tab) } }
            if ($preserved -and $identified) { $result.verified = $true }
            elseif ($lost) { Fail 'UNKNOWN' '열기 응답이 유실됐고 탭 생성·기존 상태 보존을 확인하지 못했습니다.' '재전송하지 말고 chrome_status 로 판별하세요.' $created }
            else { Fail 'POSTCONDITION_FAILED' '탭 생성 또는 기존 탭·현재 탭 보존을 확인하지 못했습니다.' '반환된 상태를 확인하세요. 재전송하지 마세요.' $created }
        }
    }
    elseif ($action -in @('chrome_switch', 'chrome_close')) {
        if (-not $info) { Fail 'TARGET_MISSING' '전용 프로필 Chrome 이 실행 중이 아닙니다.' 'chrome_status 로 확인하세요.' }
        $sel = Select-Target; $target = $sel.target
        $victim = @($target.tabs | Where-Object { $_.tab_id -eq $PcRequest.tab })
        if ($victim.Count -ne 1) { Fail 'TARGET_MISSING' ("창 {0} 에 탭 {1} 이 없습니다." -f $target.window_id, $PcRequest.tab) 'chrome_status 로 다시 선택하세요.' }
        if ($action -eq 'chrome_switch' -and $target.current_tab -eq $PcRequest.tab) {
            Set-Result @{ verified=$true; changed=$false; window_id=$target.window_id; current_tab=$target.current_tab; previous_tab=$target.current_tab; response_lost=$false;
                          checks=@{ current_tab_matches=$true; tab_set_preserved=$true }; before=(Before-Of $target); state=$target; target=(Target-Of $target $PcRequest.tab) }
        } else {
            $script:EffectStarted = $true; $lost = $false
            try { [void](Send-Cdp $(if ($action -eq 'chrome_switch') { 'Target.activateTarget' } else { 'Target.closeTarget' }) @{ targetId=$PcRequest.tab }) } catch { $lost = $true }
            Start-Sleep -Milliseconds 300
            $browserExited = $false
            try { $after = @(Get-Snapshot $target.window_id) }
            catch {
                # Windows Chrome 은 마지막 창이 닫히면 프로세스가 끝나 소켓이 끊긴다(TV1 실측). 포트가 죽었으면 창 소멸로 판별한다.
                $alive = $false
                try { $lines = @(Get-Content $PortFile); [void](Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/json/version" -f [int]$lines[0]) -TimeoutSec 3); $alive = $true } catch { $alive = $false }
                if ($action -eq 'chrome_close' -and $target.tab_count -eq 1 -and -not $alive) { $after = @(); $browserExited = $true }
                else { Fail 'UNKNOWN' ('변경 후 재조회에 실패했습니다: ' + $_.Exception.Message) '재전송하지 말고 chrome_status 로 판별하세요.' }
            }
            $afterW = $(if ($after.Count -eq 1) { $after[0] } else { $null })
            if ($browserExited) { $result.browser_exited = $true; $result.running = $false }
            if ($action -eq 'chrome_switch') {
                $same = [bool]($afterW -and (Compare-Object (Ids $target) (Ids $afterW)).Count -eq 0)
                $matches = [bool]($afterW -and $afterW.current_tab -eq $PcRequest.tab)
                Set-Result @{ changed=$true; window_id=$target.window_id; previous_tab=$target.current_tab; current_tab=$(if ($afterW) { $afterW.current_tab } else { $null }); response_lost=$lost;
                              window_state=$(if ($afterW) { $afterW.state } else { $null }); checks=@{ current_tab_matches=$matches; tab_set_preserved=$same }; before=(Before-Of $target); state=$afterW; target=(Target-Of $afterW $PcRequest.tab) }
                if ($matches -and $same) { $result.verified = $true }
                elseif ($lost) { Fail 'UNKNOWN' '전환 응답이 유실됐고 재조회한 상태가 요청과 다릅니다.' '재전송하지 말고 chrome_status 로 판별하세요.' $afterW }
                elseif ($afterW -and $afterW.state -eq 'minimized' -and $same) { Fail 'POSTCONDITION_FAILED' '창이 최소화 상태라 활성 탭을 화면 표시로 확인할 수 없습니다.' '창을 복원한 뒤 chrome_status 로 확인하세요. 재전송하지 마세요.' $afterW }
                else { Fail 'POSTCONDITION_FAILED' '전환 뒤 요청 탭과 기존 탭 집합 보존을 확인하지 못했습니다.' '반환된 상태를 확인하세요. 재전송하지 마세요.' $afterW }
            } else {
                $expectedIds = @((Ids $target) | Where-Object { $_ -ne $PcRequest.tab })
                $windowClosed = ($null -eq $afterW)
                $gone = [bool](($windowClosed -and $target.tab_count -eq 1) -or ($afterW -and (Compare-Object $expectedIds (Ids $afterW)).Count -eq 0))
                Set-Result @{ window_id=$target.window_id; closed_tab=$victim[0]; window_closed=$windowClosed; tab_count=$(if ($afterW) { $afterW.tab_count } else { 0 }); response_lost=$lost;
                              checks=@{ requested_removal_only=$gone }; before=(Before-Of $target); state=$afterW; target=(Target-Of $afterW $null) }
                if ($gone) { $result.verified = $true }
                elseif ($lost) { Fail 'UNKNOWN' '닫기 응답이 유실됐고 요청한 탭만 제거됐는지 확인하지 못했습니다.' '재전송하지 말고 chrome_status 로 판별하세요.' $afterW }
                else { Fail 'POSTCONDITION_FAILED' '닫기 뒤 남은 창·탭 상태가 요청과 다릅니다.' '반환된 상태를 확인하세요. 재전송하지 마세요.' $afterW }
            }
        }
    }
    else { throw '지원하지 않는 동작입니다.' }
    $result.success = $true
} catch {
    $result.error = $_.Exception.Message
    if (-not $result.failure) {
        $code = $(if ($script:EffectStarted) { 'UNKNOWN' } else { 'OBSERVATION_FAILED' })
        $result.failure = @{ code=$code; message=$_.Exception.Message; next=$(if ($code -eq 'UNKNOWN') { '재전송하지 말고 chrome_status 로 판별하세요.' } else { '관측 실패를 보존하고 chrome_status 로 새 조회를 요청하세요.' }) }
        $result.error = ('{0}: {1}' -f $code, $_.Exception.Message)
    }
    $result.error_code = $result.failure.code
} finally {
    if ($script:Ws) { try { $cts = New-Object System.Threading.CancellationTokenSource(1000); [void]$script:Ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, 'done', $cts.Token).GetAwaiter().GetResult() } catch {}; $script:Ws.Dispose() }
}
Write-Output ('INDIEBIZ_PC_RESULT:' + (ConvertTo-Json -InputObject $result -Depth 8 -Compress))
