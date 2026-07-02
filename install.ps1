# IndieBiz OS - minimal self-installer (Windows / PowerShell)
#
# One-liner (run in PowerShell):
#   irm https://raw.githubusercontent.com/kangkukjin/indiebizOS/main/install.ps1 | iex
#
# With your key set first (recommended):
#   $env:INDIEBIZ_API_KEY="sk-ant-..."; irm https://raw.githubusercontent.com/kangkukjin/indiebizOS/main/install.ps1 | iex
#
# Re-installing over an existing clone (overwrite with GitHub code):
#   $env:INDIEBIZ_UPDATE="standard"  overwrite tracked code + shipped vocabulary;
#                                    KEEP your .env, personal data, AND learning.
#   $env:INDIEBIZ_UPDATE="full"      also factory-reset learned data & tuning to
#                                    shipped defaults (keeps .env + personal data).
#   $env:INDIEBIZ_UPDATE="off"       (default) just fast-forward pull.
#   If unset and interactive, you are asked which one. Git-ignored files
#   (.env / keys / profile / DBs / projects) are never touched by the overwrite.
#
# This bootstrap does the dumb part: ensure git + python exist, get the code,
# and hand off to the intelligent seed (installer\seed.py), an LLM agent that
# adapts the install to THIS machine.

$ErrorActionPreference = "Stop"

$RepoUrl    = if ($env:INDIEBIZ_REPO)   { $env:INDIEBIZ_REPO }   else { "https://github.com/kangkukjin/indiebizOS.git" }
$InstallDir = if ($env:INDIEBIZ_DIR)    { $env:INDIEBIZ_DIR }    else { Join-Path $env:USERPROFILE "indiebizOS" }
$Branch     = if ($env:INDIEBIZ_BRANCH) { $env:INDIEBIZ_BRANCH } else { "main" }
$UpdateMode = if ($env:INDIEBIZ_UPDATE) { $env:INDIEBIZ_UPDATE } else { "" }

function Say($m) { Write-Host "[indiebiz] $m" -ForegroundColor Cyan }
function Fail($m) { Write-Host "[indiebiz:error] $m" -ForegroundColor Red; exit 1 }

function Find-Python {
  foreach ($c in @("python", "python3", "py")) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) {
      try {
        $v = & $c -c "import sys; print(sys.version_info[0])" 2>$null
        if ($v -eq "3") { return $c }
      } catch {}
    }
  }
  return $null
}

function Ensure-Prereqs {
  $needGit = -not (Get-Command git -ErrorAction SilentlyContinue)
  $py = Find-Python
  $needPy = ($null -eq $py)
  if (-not $needGit -and -not $needPy) { return }

  Say "installing prerequisites (git / python)…"
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($winget) {
    if ($needGit) { winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements }
    if ($needPy)  { winget install --id Python.Python.3.12 -e --source winget --accept-source-agreements --accept-package-agreements }
    # refresh PATH for this session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","User")
  } else {
    Fail "git/python missing and winget not available. Install them from https://git-scm.com and https://python.org , then re-run."
  }
}

# Ask which overwrite mode to use for an existing install. Returns standard|full|off.
function Resolve-UpdateMode {
  switch ($UpdateMode) { "standard" { return "standard" } "full" { return "full" } "off" { return "off" } }
  # unattended or no interactive console → safe default
  if ($env:INDIEBIZ_YES -or -not [Environment]::UserInteractive -or $null -eq $Host.UI.RawUI) {
    return "off"
  }
  Write-Host "[indiebiz] existing install found - overwrite with GitHub code?" -ForegroundColor Cyan
  Write-Host "  [1] standard  overwrite code + shipped vocabulary; KEEP your learning & settings"
  Write-Host "  [2] full      factory reset: also reset learned data & tuning (keeps .env + personal data)"
  Write-Host "  [3] off       just fast-forward pull (default, safest)"
  $ans = Read-Host "  choose [1/2/3] (default 3)"
  switch ($ans) { "1" { return "standard" } "2" { return "full" } default { return "off" } }
}

# Overwrite all tracked files with the fetched GitHub state. git reset --hard
# never touches untracked/ignored files, so .env / keys / personal data survive.
function Overwrite-Tracked {
  Say "overwriting tracked code + vocabulary from origin/$Branch (git-ignored files kept)…"
  git -C $InstallDir fetch --depth 1 origin $Branch
  git -C $InstallDir reset --hard FETCH_HEAD
}

function Main {
  Say "IndieBiz OS installer - bootstrapping on Windows"
  Ensure-Prereqs

  $py = Find-Python
  if ($null -eq $py) { Fail "python 3 still not found on PATH. Open a new terminal and re-run." }
  Say "using python: $py ($(& $py --version 2>&1))"

  if (Test-Path (Join-Path $InstallDir ".git")) {
    $mode = Resolve-UpdateMode
    $script:UpdateMode = $mode
    if ($mode -eq "standard" -or $mode -eq "full") {
      Overwrite-Tracked
      if ($mode -eq "full") {
        Say "full update - factory-resetting learned/tuning state (keys + personal data kept)…"
        try { & $py (Join-Path $InstallDir "scripts\reset_runtime_state.py") --mode full --yes }
        catch { Say "(runtime reset skipped - script missing or errored)" }
      }
    } else {
      Say "found existing clone at $InstallDir - fast-forward pull only"
      git -C $InstallDir pull --ff-only 2>$null | Out-Null
    }
  } else {
    Say "cloning $RepoUrl -> $InstallDir"
    git clone --branch $Branch --depth 1 $RepoUrl $InstallDir
  }

  Set-Location $InstallDir
  Say "handing off to the installer agent…"
  # let the seed know this was an update so it rebuilds vocab / won't clobber .env
  $env:INDIEBIZ_UPDATE = $script:UpdateMode
  & $py (Join-Path $InstallDir "installer\seed.py")
}

Main
