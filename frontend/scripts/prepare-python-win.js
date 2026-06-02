/**
 * Windows용 Python 임베디드 환경 준비 스크립트
 *
 * 이 스크립트는 Windows 빌드 전에 실행해야 합니다.
 * macOS/Linux에서도 실행 가능 (크로스 빌드 준비용)
 *
 * 사용법: npm run prepare:python:win
 */

import { execSync } from 'child_process';
import { createWriteStream, existsSync, mkdirSync, readFileSync, writeFileSync, rmSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import https from 'https';
import { createUnzip } from 'zlib';
import { pipeline } from 'stream/promises';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// 설정
const PYTHON_VERSION = '3.11.9';
const PYTHON_EMBED_URL = `https://www.python.org/ftp/python/${PYTHON_VERSION}/python-${PYTHON_VERSION}-embed-amd64.zip`;
const GET_PIP_URL = 'https://bootstrap.pypa.io/get-pip.py';

// 경로
const ROOT_DIR = join(__dirname, '..', '..');
const BUILD_DIR = join(ROOT_DIR, 'build');
const PYTHON_WIN_DIR = join(BUILD_DIR, 'python-win');
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
 * 파일 다운로드
 */
function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    console.log(`  다운로드: ${url}`);
    const file = createWriteStream(dest);

    https.get(url, (response) => {
      // 리다이렉트 처리
      if (response.statusCode === 302 || response.statusCode === 301) {
        file.close();
        downloadFile(response.headers.location, dest).then(resolve).catch(reject);
        return;
      }

      response.pipe(file);
      file.on('finish', () => {
        file.close();
        resolve();
      });
    }).on('error', (err) => {
      file.close();
      reject(err);
    });
  });
}

/**
 * ZIP 압축 해제 (unzipper 사용)
 */
async function extractZip(zipPath, destDir) {
  console.log(`  압축 해제: ${zipPath} -> ${destDir}`);

  // Node.js 18+에서는 native unzip이 없으므로 외부 명령 사용
  try {
    if (process.platform === 'win32') {
      execSync(`powershell -Command "Expand-Archive -Path '${zipPath}' -DestinationPath '${destDir}' -Force"`, { stdio: 'inherit' });
    } else {
      execSync(`unzip -o "${zipPath}" -d "${destDir}"`, { stdio: 'inherit' });
    }
  } catch (e) {
    console.error('압축 해제 실패:', e.message);
    throw e;
  }
}

/**
 * Python ._pth 파일 수정 (site-packages 활성화)
 */
function configurePythonPth(pythonDir) {
  const pthFile = join(pythonDir, 'python311._pth');
  const content = `python311.zip
.
Lib\\site-packages
import site
`;
  writeFileSync(pthFile, content);
  console.log('  python311._pth 설정 완료');
}

/**
 * pip 설치
 */
async function installPip(pythonDir) {
  const getPipPath = join(BUILD_DIR, 'get-pip.py');

  if (!existsSync(getPipPath)) {
    await downloadFile(GET_PIP_URL, getPipPath);
  }

  const pythonExe = join(pythonDir, 'python.exe');

  // Windows에서만 직접 실행 가능
  if (process.platform === 'win32') {
    console.log('  pip 설치 중...');
    execSync(`"${pythonExe}" "${getPipPath}" --no-warn-script-location`, { stdio: 'inherit' });
  } else {
    console.log('  [주의] Windows가 아니므로 pip 설치를 건너뜁니다.');
    console.log('  Windows에서 빌드할 때 수동으로 pip를 설치해야 합니다.');
  }
}

/**
 * Python 패키지 설치
 */
function installPackages(pythonDir) {
  const requirementsCore = join(BACKEND_DIR, 'requirements-core.txt');
  const requirementsTools = join(BACKEND_DIR, 'requirements-tools.txt');
  const pythonExe = join(pythonDir, 'python.exe');
  const sitePackages = join(pythonDir, 'Lib', 'site-packages');

  ensureDir(sitePackages);

  if (process.platform === 'win32') {
    // 코어 패키지 설치
    console.log('  [Core] Python 핵심 패키지 설치 중...');
    execSync(
      `"${pythonExe}" -m pip install -r "${requirementsCore}" --target "${sitePackages}" --no-warn-script-location`,
      { stdio: 'inherit' }
    );

    // 도구 패키지 의존성 설치
    if (existsSync(requirementsTools)) {
      console.log('  [Tools] 도구 패키지 의존성 설치 중...');
      execSync(
        `"${pythonExe}" -m pip install -r "${requirementsTools}" --target "${sitePackages}" --no-warn-script-location`,
        { stdio: 'inherit' }
      );
    }
  } else {
    console.log('  [주의] Windows가 아니므로 패키지 설치를 건너뜁니다.');
  }
}

/**
 * 메인 실행
 */
async function main() {
  console.log('========================================');
  console.log('IndieBiz OS - Windows Python 준비');
  console.log('========================================\n');

  // 1. 디렉토리 준비
  console.log('[1/5] 디렉토리 준비...');
  ensureDir(BUILD_DIR);

  // 기존 python-win 삭제
  if (existsSync(PYTHON_WIN_DIR)) {
    console.log('  기존 python-win 삭제...');
    rmSync(PYTHON_WIN_DIR, { recursive: true, force: true });
  }
  ensureDir(PYTHON_WIN_DIR);

  // 2. Python 임베디드 다운로드
  console.log('\n[2/5] Python 임베디드 다운로드...');
  const pythonZipPath = join(BUILD_DIR, `python-${PYTHON_VERSION}-embed-amd64.zip`);

  if (!existsSync(pythonZipPath)) {
    await downloadFile(PYTHON_EMBED_URL, pythonZipPath);
  } else {
    console.log('  이미 다운로드됨, 건너뜀');
  }

  // 3. 압축 해제
  console.log('\n[3/5] 압축 해제...');
  await extractZip(pythonZipPath, PYTHON_WIN_DIR);

  // 4. Python 설정
  console.log('\n[4/5] Python 설정...');
  configurePythonPth(PYTHON_WIN_DIR);
  await installPip(PYTHON_WIN_DIR);

  // 5. 패키지 설치
  console.log('\n[5/5] Python 패키지 설치...');
  installPackages(PYTHON_WIN_DIR);

  console.log('\n========================================');
  console.log('완료!');
  console.log(`Python 위치: ${PYTHON_WIN_DIR}`);
  console.log('========================================');

  if (process.platform !== 'win32') {
    console.log('\n[주의] macOS/Linux에서 실행됨');
    console.log('Windows에서 다음 명령을 실행하여 패키지를 설치하세요:');
    console.log(`  cd ${PYTHON_WIN_DIR}`);
    console.log(`  python.exe -m pip install -r ${join(BACKEND_DIR, 'requirements-core.txt')} --target Lib\\site-packages`);
    console.log(`  python.exe -m pip install -r ${join(BACKEND_DIR, 'requirements-tools.txt')} --target Lib\\site-packages`);
  }
}

main().catch(console.error);
