/**
 * macOS용 Python 환경 준비 스크립트
 *
 * 이 스크립트는 macOS 빌드 전에 실행해야 합니다.
 * Homebrew나 pyenv의 Python을 사용하여 standalone 환경을 만듭니다.
 *
 * 사용법: npm run prepare:python:mac
 */

import { execSync } from 'child_process';
import { existsSync, mkdirSync, rmSync, copyFileSync, readdirSync, statSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// 경로
const ROOT_DIR = join(__dirname, '..', '..');
const BUILD_DIR = join(ROOT_DIR, 'build');
const PYTHON_MAC_DIR = join(BUILD_DIR, 'python-mac');
const BACKEND_DIR = join(ROOT_DIR, 'backend');

/**
 * 디렉토리 생성
 */
function ensureDir(dir) {
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
}

/**
 * 디렉토리 복사 (재귀)
 */
function copyDir(src, dest) {
  ensureDir(dest);
  const entries = readdirSync(src);

  for (const entry of entries) {
    const srcPath = join(src, entry);
    const destPath = join(dest, entry);
    const stat = statSync(srcPath);

    if (stat.isDirectory()) {
      copyDir(srcPath, destPath);
    } else {
      copyFileSync(srcPath, destPath);
    }
  }
}

/**
 * Python 경로 찾기
 */
function findPython() {
  const candidates = [
    '/opt/homebrew/bin/python3',           // Apple Silicon Homebrew
    '/usr/local/bin/python3',              // Intel Homebrew
    '/usr/bin/python3',                    // System Python
  ];

  for (const path of candidates) {
    if (existsSync(path)) {
      return path;
    }
  }

  // which로 찾기
  try {
    return execSync('which python3', { encoding: 'utf8' }).trim();
  } catch {
    throw new Error('Python3를 찾을 수 없습니다. Homebrew로 설치하세요: brew install python');
  }
}

/**
 * Python 버전 확인
 */
function getPythonVersion(pythonPath) {
  const version = execSync(`"${pythonPath}" --version`, { encoding: 'utf8' }).trim();
  return version.replace('Python ', '');
}

/**
 * venv 생성 및 패키지 설치
 */
function createVenv(pythonPath) {
  console.log('  venv 생성 중...');
  execSync(`"${pythonPath}" -m venv "${PYTHON_MAC_DIR}"`, { stdio: 'inherit' });

  const venvPython = join(PYTHON_MAC_DIR, 'bin', 'python3');

  // pip 업그레이드
  console.log('  pip 업그레이드...');
  execSync(`"${venvPython}" -m pip install --upgrade pip`, { stdio: 'inherit' });

  // 패키지 설치
  const requirementsPath = join(BACKEND_DIR, 'requirements-core.txt');
  if (existsSync(requirementsPath)) {
    console.log('  Python 패키지 설치 중...');
    execSync(`"${venvPython}" -m pip install -r "${requirementsPath}"`, { stdio: 'inherit' });
  } else {
    console.log('  [경고] requirements-core.txt 없음, 기본 패키지만 설치');
    execSync(`"${venvPython}" -m pip install fastapi uvicorn httpx aiofiles python-multipart`, { stdio: 'inherit' });
  }
}

/**
 * 메인 실행
 */
async function main() {
  console.log('========================================');
  console.log('IndieBiz OS - macOS Python 준비');
  console.log('========================================\n');

  // 1. Python 찾기
  console.log('[1/4] Python 찾기...');
  const pythonPath = findPython();
  const pythonVersion = getPythonVersion(pythonPath);
  console.log(`  발견: ${pythonPath}`);
  console.log(`  버전: ${pythonVersion}`);

  // 2. 디렉토리 준비
  console.log('\n[2/4] 디렉토리 준비...');
  ensureDir(BUILD_DIR);

  if (existsSync(PYTHON_MAC_DIR)) {
    console.log('  기존 python-mac 삭제...');
    rmSync(PYTHON_MAC_DIR, { recursive: true, force: true });
  }

  // 3. venv 생성
  console.log('\n[3/4] Python venv 생성...');
  createVenv(pythonPath);

  // 4. 완료
  console.log('\n[4/4] 정리...');

  // 불필요한 파일 삭제 (용량 줄이기)
  const toRemove = [
    join(PYTHON_MAC_DIR, 'include'),
    join(PYTHON_MAC_DIR, 'share'),
  ];

  for (const path of toRemove) {
    if (existsSync(path)) {
      rmSync(path, { recursive: true, force: true });
    }
  }

  console.log('\n========================================');
  console.log('완료!');
  console.log(`Python 위치: ${PYTHON_MAC_DIR}`);
  console.log('========================================');
}

main().catch(console.error);
