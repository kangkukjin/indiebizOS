# IndieBiz OS - Windows Build Script
# PowerShell 스크립트: Windows 배포 패키지 빌드

param(
    [switch]$SkipPython,
    [switch]$SkipFrontend,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

# 경로 설정
$ROOT_DIR = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ROOT_DIR) { $ROOT_DIR = (Get-Location).Path }
$SCRIPTS_DIR = Join-Path $ROOT_DIR "scripts"
$FRONTEND_DIR = Join-Path $ROOT_DIR "frontend"
$BACKEND_DIR = Join-Path $ROOT_DIR "backend"
$BUILD_DIR = Join-Path $ROOT_DIR "build"
$DIST_DIR = Join-Path $BUILD_DIR "dist-win"

# Python 임베디드 버전
$PYTHON_VERSION = "3.11.9"
$PYTHON_EMBED_URL = "https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION-embed-amd64.zip"
$GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "IndieBiz OS - Windows Build" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 클린 빌드
if ($Clean) {
    Write-Host "[1/6] 이전 빌드 정리 중..." -ForegroundColor Yellow
    if (Test-Path $DIST_DIR) {
        Remove-Item -Recurse -Force $DIST_DIR
    }
}

# 디렉토리 생성
Write-Host "[1/6] 빌드 디렉토리 생성..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $DIST_DIR | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DIST_DIR "python") | Out-Null

# Python 임베디드 다운로드 및 설치
if (-not $SkipPython) {
    Write-Host "[2/6] Python 임베디드 다운로드 중..." -ForegroundColor Yellow
    $pythonZip = Join-Path $BUILD_DIR "python-embed.zip"
    $pythonDir = Join-Path $DIST_DIR "python"

    if (-not (Test-Path $pythonZip)) {
        Invoke-WebRequest -Uri $PYTHON_EMBED_URL -OutFile $pythonZip
    }

    Write-Host "[2/6] Python 압축 해제 중..." -ForegroundColor Yellow
    Expand-Archive -Path $pythonZip -DestinationPath $pythonDir -Force

    # python311._pth 수정 (site-packages 활성화)
    $pthFile = Join-Path $pythonDir "python311._pth"
    $pthContent = @"
python311.zip
.
Lib\site-packages
import site
"@
    Set-Content -Path $pthFile -Value $pthContent

    # pip 설치
    Write-Host "[2/6] pip 설치 중..." -ForegroundColor Yellow
    $getPipPath = Join-Path $BUILD_DIR "get-pip.py"
    if (-not (Test-Path $getPipPath)) {
        Invoke-WebRequest -Uri $GET_PIP_URL -OutFile $getPipPath
    }

    $pythonExe = Join-Path $pythonDir "python.exe"
    & $pythonExe $getPipPath --no-warn-script-location

    # 필요한 패키지 설치
    Write-Host "[2/6] Python 패키지 설치 중..." -ForegroundColor Yellow
    $requirementsPath = Join-Path $BACKEND_DIR "requirements-core.txt"
    & $pythonExe -m pip install -r $requirementsPath --no-warn-script-location --target (Join-Path $pythonDir "Lib\site-packages")
} else {
    Write-Host "[2/6] Python 설치 건너뜀" -ForegroundColor Gray
}

# 백엔드 복사
Write-Host "[3/6] 백엔드 복사 중..." -ForegroundColor Yellow
$backendDist = Join-Path $DIST_DIR "backend"
New-Item -ItemType Directory -Force -Path $backendDist | Out-Null
Copy-Item -Path (Join-Path $BACKEND_DIR "*") -Destination $backendDist -Recurse -Force -Exclude @("__pycache__", "*.pyc", "venv", ".DS_Store")

# data, projects, templates, tokens 복사
Write-Host "[3/6] 데이터 디렉토리 복사 중..." -ForegroundColor Yellow
$dataDirs = @("data", "projects", "templates", "tokens")
foreach ($dir in $dataDirs) {
    $srcDir = Join-Path $ROOT_DIR $dir
    $dstDir = Join-Path $DIST_DIR $dir
    if (Test-Path $srcDir) {
        Copy-Item -Path $srcDir -Destination $dstDir -Recurse -Force
    }
}

# 프론트엔드 빌드
if (-not $SkipFrontend) {
    Write-Host "[4/6] 프론트엔드 빌드 중..." -ForegroundColor Yellow
    Push-Location $FRONTEND_DIR
    npm install
    npm run build
    Pop-Location
} else {
    Write-Host "[4/6] 프론트엔드 빌드 건너뜀" -ForegroundColor Gray
}

# Electron 빌드
Write-Host "[5/6] Electron 빌드 중..." -ForegroundColor Yellow
Push-Location $FRONTEND_DIR

# package.json의 build 설정에 python 디렉토리 추가
$packageJson = Get-Content (Join-Path $FRONTEND_DIR "package.json") | ConvertFrom-Json
$packageJson.build.extraResources += @{
    from = "../build/dist-win/python"
    to = "python"
}
$packageJson | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $FRONTEND_DIR "package.json.tmp")

# electron-builder 실행
npm run electron:build -- --win

Pop-Location

# 완료
Write-Host "[6/6] 빌드 완료!" -ForegroundColor Green
Write-Host ""
Write-Host "출력 위치: $FRONTEND_DIR\release" -ForegroundColor Cyan
Write-Host ""

# 빌드 크기 확인
$releaseDir = Join-Path $FRONTEND_DIR "release"
if (Test-Path $releaseDir) {
    $size = (Get-ChildItem -Path $releaseDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Host "빌드 크기: $([math]::Round($size, 2)) MB" -ForegroundColor Cyan
}
