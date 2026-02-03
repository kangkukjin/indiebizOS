/**
 * Windows용 Node.js 환경 준비 스크립트
 *
 * 이 스크립트는 Windows 빌드 전에 실행해야 합니다.
 * macOS/Linux에서도 실행 가능 (크로스 빌드 준비용)
 *
 * 사용법: npm run prepare:node:win
 */

import { execSync } from 'child_process';
import { createWriteStream, existsSync, mkdirSync, rmSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import https from 'https';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// 설정 - LTS 버전 사용
const NODE_VERSION = '20.18.1';
const NODE_URL = `https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-win-x64.zip`;

// 경로
const ROOT_DIR = join(__dirname, '..', '..');
const BUILD_DIR = join(ROOT_DIR, 'build');
const NODE_WIN_DIR = join(BUILD_DIR, 'node-win');

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

    const request = https.get(url, (response) => {
      // 리다이렉트 처리
      if (response.statusCode === 302 || response.statusCode === 301) {
        file.close();
        downloadFile(response.headers.location, dest).then(resolve).catch(reject);
        return;
      }

      if (response.statusCode !== 200) {
        file.close();
        reject(new Error(`다운로드 실패: HTTP ${response.statusCode}`));
        return;
      }

      const totalBytes = parseInt(response.headers['content-length'], 10);
      let downloadedBytes = 0;
      let lastPercent = 0;

      response.on('data', (chunk) => {
        downloadedBytes += chunk.length;
        const percent = Math.floor((downloadedBytes / totalBytes) * 100);
        if (percent !== lastPercent && percent % 10 === 0) {
          process.stdout.write(`  진행률: ${percent}%\r`);
          lastPercent = percent;
        }
      });

      response.pipe(file);
      file.on('finish', () => {
        console.log('  다운로드 완료!          ');
        file.close();
        resolve();
      });
    });

    request.on('error', (err) => {
      file.close();
      reject(err);
    });
  });
}

/**
 * ZIP 압축 해제
 */
async function extractZip(zipPath, destDir) {
  console.log(`  압축 해제: ${zipPath} -> ${destDir}`);

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
 * Node.js 디렉토리 구조 정리
 * node-v20.18.1-win-x64/ 폴더 내용을 node-win/ 루트로 이동
 */
function reorganizeNodeDir(nodeWinDir, nodeVersion) {
  const extractedDir = join(nodeWinDir, `node-v${nodeVersion}-win-x64`);

  if (existsSync(extractedDir)) {
    console.log('  디렉토리 구조 정리...');

    if (process.platform === 'win32') {
      // Windows: robocopy 사용
      execSync(`robocopy "${extractedDir}" "${nodeWinDir}" /E /MOVE /NFL /NDL /NJH /NJS`, {
        stdio: 'pipe',
        // robocopy는 성공해도 0이 아닌 exit code를 반환할 수 있음
      });
    } else {
      // macOS/Linux: mv 사용
      execSync(`mv "${extractedDir}"/* "${nodeWinDir}"/`, { stdio: 'inherit', shell: true });
      rmSync(extractedDir, { recursive: true, force: true });
    }

    console.log('  구조 정리 완료');
  }
}

/**
 * 메인 실행
 */
async function main() {
  console.log('========================================');
  console.log('IndieBiz OS - Windows Node.js 준비');
  console.log(`Node.js 버전: v${NODE_VERSION}`);
  console.log('========================================\n');

  // 1. 디렉토리 준비
  console.log('[1/3] 디렉토리 준비...');
  ensureDir(BUILD_DIR);

  // 기존 node-win 삭제
  if (existsSync(NODE_WIN_DIR)) {
    console.log('  기존 node-win 삭제...');
    rmSync(NODE_WIN_DIR, { recursive: true, force: true });
  }
  ensureDir(NODE_WIN_DIR);

  // 2. Node.js 다운로드
  console.log('\n[2/3] Node.js 다운로드...');
  const nodeZipPath = join(BUILD_DIR, `node-v${NODE_VERSION}-win-x64.zip`);

  if (!existsSync(nodeZipPath)) {
    await downloadFile(NODE_URL, nodeZipPath);
  } else {
    console.log('  이미 다운로드됨, 건너뜀');
  }

  // 3. 압축 해제 및 정리
  console.log('\n[3/3] 압축 해제 및 정리...');
  await extractZip(nodeZipPath, NODE_WIN_DIR);
  reorganizeNodeDir(NODE_WIN_DIR, NODE_VERSION);

  // 결과 확인
  const nodeExe = join(NODE_WIN_DIR, 'node.exe');
  const npmCmd = join(NODE_WIN_DIR, 'npm.cmd');
  const npxCmd = join(NODE_WIN_DIR, 'npx.cmd');
  const npmCliJs = join(NODE_WIN_DIR, 'node_modules', 'npm', 'bin', 'npm-cli.js');

  console.log('\n========================================');
  console.log('완료!');
  console.log(`Node.js 위치: ${NODE_WIN_DIR}`);
  console.log('');
  console.log('포함된 파일:');
  console.log(`  - node.exe: ${existsSync(nodeExe) ? '있음' : '없음!'}`);
  console.log(`  - npm.cmd: ${existsSync(npmCmd) ? '있음' : '없음!'}`);
  console.log(`  - npx.cmd: ${existsSync(npxCmd) ? '있음' : '없음!'}`);
  console.log(`  - npm-cli.js: ${existsSync(npmCliJs) ? '있음' : '없음!'}`);
  console.log('========================================');

  // 필수 파일 확인
  if (!existsSync(nodeExe) || !existsSync(npmCliJs)) {
    console.error('\n[오류] 필수 파일이 누락되었습니다!');
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('오류 발생:', err);
  process.exit(1);
});
