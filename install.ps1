# IndieBiz OS - minimal self-installer (Windows / PowerShell)
#
# One-liner (run in PowerShell):
#   irm https://raw.githubusercontent.com/kangkukjin/indiebizOS/main/install.ps1 | iex
#
# With your key set first (recommended):
#   $env:INDIEBIZ_API_KEY="sk-ant-..."; irm https://raw.githubusercontent.com/kangkukjin/indiebizOS/main/install.ps1 | iex
#
# This bootstrap does the dumb part: ensure git + python exist, get the code,
# and hand off to the intelligent seed (installer\seed.py), an LLM agent that
# adapts the install to THIS machine.

$ErrorActionPreference = "Stop"

$RepoUrl    = if ($env:INDIEBIZ_REPO)   { $env:INDIEBIZ_REPO }   else { "https://github.com/kangkukjin/indiebizOS.git" }
$InstallDir = if ($env:INDIEBIZ_DIR)    { $env:INDIEBIZ_DIR }    else { Join-Path $env:USERPROFILE "indiebizOS" }
$Branch     = if ($env:INDIEBIZ_BRANCH) { $env:INDIEBIZ_BRANCH } else { "main" }

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

function Main {
  Say "IndieBiz OS installer - bootstrapping on Windows"
  Ensure-Prereqs

  $py = Find-Python
  if ($null -eq $py) { Fail "python 3 still not found on PATH. Open a new terminal and re-run." }
  Say "using python: $py ($(& $py --version 2>&1))"

  if (Test-Path (Join-Path $InstallDir ".git")) {
    Say "found existing clone at $InstallDir - updating"
    git -C $InstallDir pull --ff-only 2>$null | Out-Null
  } else {
    Say "cloning $RepoUrl -> $InstallDir"
    git clone --branch $Branch --depth 1 $RepoUrl $InstallDir
  }

  Set-Location $InstallDir
  Say "handing off to the installer agent…"
  & $py (Join-Path $InstallDir "installer\seed.py")
}

Main
