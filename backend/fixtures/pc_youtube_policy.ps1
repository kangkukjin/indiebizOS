param([string]$DriverBase64)
# Compile the production driver and exercise observations without opening or controlling a browser.
$ErrorActionPreference = 'Stop'
$source = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($DriverBase64))
$tokens = $null; $errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$code = [regex]::Match($source, "(?s)-TypeDefinition @'\r?\n(.*?)\r?\n'@").Groups[1].Value
if (-not $code) { throw 'Missing production C# driver' }
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms, WindowsBase
Add-Type -ReferencedAssemblies UIAutomationClient,UIAutomationTypes,System.Windows.Forms,WindowsBase -TypeDefinition $code
function Assert($condition, $message) { if (-not $condition) { throw $message } }
$o = New-Object PCYouTube+Observation
$o.video_id = '0eyvWdgx_gk'; $o.title = 'Original title'; $o.duration = 9125
$o.state = 'playing'; $o.playing = $true
Assert ([PCYouTube]::Matches($o, $o.video_id, $o.title, 9126)) 'One second duration tolerance regressed'
Assert ($null -eq [PCYouTube]::Failure($o, $o.video_id, $o.title, 9126)) 'Valid observation diagnosed as failure'
Assert ([PCYouTube]::Failure($o, $o.video_id, 'Short title', 9126).StartsWith('YOUTUBE_TITLE_MISMATCH:')) 'Short title must fail specifically'
Assert ([PCYouTube]::Failure($o, $o.video_id, $o.title, 100).StartsWith('YOUTUBE_DURATION_MISMATCH:')) 'Wrong duration must fail specifically'
$o.ad = $true
Assert ($null -eq [PCYouTube]::Failure($o, $o.video_id, 'Short title', 100)) 'Ad metadata must not diagnose main video'
Assert (-not [PCYouTube]::Matches($o, $o.video_id, $o.title, 9125)) 'Ad must not verify'
$o.ad = $false; $o.duration = 0
Assert ($null -eq [PCYouTube]::Failure($o, $o.video_id, 'Short title', 100)) 'Loading metadata must not diagnose mismatch'
$o.duration = 9125
Assert ($null -eq [PCYouTube]::Failure($o, 'abcdefghijk', 'Short title', 100)) 'Old video during navigation must not diagnose mismatch'
$o.state = 'error'; $o.player_error = 'Something went wrong'
Assert ([PCYouTube]::Failure($o, $o.video_id, $o.title, 9125).StartsWith('YOUTUBE_PLAYER_ERROR:')) 'Player error must be terminal'
Assert (-not [PCYouTube]::Matches($o, $o.video_id, $o.title, 9125)) 'Error with stale controls must not verify'
Assert ([PCYouTube]::IsPlayerError('Something went wrong. Refresh or try again later.')) 'English error missing'
$korean = -join ([char[]](0xBB38,0xC81C,0xAC00,0x20,0xBC1C,0xC0DD,0xD588,0xC2B5,0xB2C8,0xB2E4))
Assert ([PCYouTube]::IsPlayerError($korean)) 'Korean episode error missing'
Assert (-not [PCYouTube]::IsPlayerError('A song about Something went wrong')) 'Unrelated text misdiagnosed'
Write-Output 'PC_YOUTUBE_POLICY_OK'
