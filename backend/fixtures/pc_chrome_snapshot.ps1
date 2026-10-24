param([string]$DriverBase64)
# Run production snapshot functions against deterministic CDP responses. No browser actions.
$ErrorActionPreference = 'Stop'
$source = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($DriverBase64))
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($name in @('Get-Snapshot', 'Get-Revision')) {
    $fn = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name }, $true)
    if (-not $fn) { throw ('Missing function: ' + $name) }
    . ([ScriptBlock]::Create($fn.Extent.Text))
}
function Assert($condition, $message) { if (-not $condition) { throw $message } }
$script:State = 'minimized'; $script:VisibilityCalls = 0; $script:WindowCalls = 0
function Get-Pages { @(@{targetId='A';url='https://www.youtube.com/';title='YouTube'}, @{targetId='B';url='https://example.org/';title='Other'}) }
function Send-Cdp($method, $params) {
    Assert ($method -eq 'Browser.getWindowForTarget') 'Unexpected CDP operation'
    $script:WindowCalls++
    return @{windowId=1;bounds=@{windowState=$script:State}}
}
function Get-Visibility($tid) {
    $script:VisibilityCalls++
    if ($tid -eq 'A') { return 'visible' }; return 'hidden'
}
$wins = @(Get-Snapshot $null)
Assert ($wins.Count -eq 1 -and $wins[0].tab_count -eq 2) 'Minimized tab inventory lost'
Assert ($null -eq $wins[0].current_tab) 'Minimized window must have no visible tab'
Assert ($script:VisibilityCalls -eq 0 -and $script:WindowCalls -eq 2) 'Minimized pages must skip visibility round trips only'
Assert ($wins[0].tabs[0].url -eq 'https://www.youtube.com/') 'URL readback lost'
$before = $wins[0].revision
$script:State = 'normal'
$wins = @(Get-Snapshot 1)
Assert ($wins[0].current_tab -eq 'A' -and $script:VisibilityCalls -eq 2) 'Visible window must still inspect each page'
Assert ($wins[0].revision -ne $before) 'Visible tab must affect revision'
$script:VisibilityCalls = 0
$wins = @(Get-Snapshot 2)
Assert ($wins.Count -eq 0 -and $script:VisibilityCalls -eq 0) 'Window filter regressed'
Write-Output 'PC_CHROME_SNAPSHOT_OK'
