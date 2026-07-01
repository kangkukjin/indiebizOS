/**
 * 포식 브라우저 비밀번호 금고 (Electron main 전용)
 *
 * 크롬의 "비밀번호 채우기"를 포식 브라우저(<webview>)로 가져온 것. 두 가지를 한다:
 *   1) 자체 금고  — origin(host)별 {username, password} 를 OS 키체인(safeStorage)으로 암호화 저장.
 *   2) 크롬 임포트 — macOS 크롬의 Login Data(SQLite)를 읽어 키체인 키로 복호화 후 금고로 흡수.
 *
 * ★설계: 비밀번호 평문은 *절대 HTTP/백엔드로 나가지 않는다*. main↔renderer IPC 안에서만 흐른다.
 *   - 저장: safeStorage.encryptString (macOS Keychain 백엔드). 평문 파일 없음.
 *   - 채움: renderer 가 fill 시점에만 평문을 받아 <webview> DOM 에 주입(executeJavaScript).
 *   - 크롬 복호화: Node crypto(AES-128-CBC) + node:sqlite. 외부 의존성 0.
 *
 * 자동채움 UX 는 augmentation-over-autonomy — 채우기만 하고 자동 제출(로그인)은 절대 안 한다.
 */
import { app, safeStorage } from 'electron';
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import { execFileSync } from 'child_process';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);

function vaultPath() {
  return path.join(app.getPath('userData'), 'forage_passwords.json');
}

function loadVault() {
  try {
    return JSON.parse(fs.readFileSync(vaultPath(), 'utf-8'));
  } catch {
    return [];
  }
}

function saveVault(entries) {
  // 0600 — 소유자만 읽기/쓰기 (enc 는 키체인 키 없이는 무의미하지만, 한 겹 더).
  fs.writeFileSync(vaultPath(), JSON.stringify(entries), { mode: 0o600 });
}

function encPw(pw) {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('OS 키체인 암호화를 사용할 수 없습니다');
  }
  return safeStorage.encryptString(pw).toString('base64');
}

function decPw(enc) {
  return safeStorage.decryptString(Buffer.from(enc, 'base64'));
}

// URL 이든 host 든 받아 host(포트 포함, 소문자)로 정규화. 매칭 단위는 host.
function hostOf(urlOrHost) {
  const s = String(urlOrHost || '').trim();
  try {
    return new URL(s).host.toLowerCase();
  } catch {
    return s.toLowerCase();
  }
}

// 현재 host 에 저장된 계정 목록 (비밀번호 없이 username 만 — 메뉴 표시용)
export function listForHost(urlOrHost) {
  const host = hostOf(urlOrHost);
  return loadVault()
    .filter((e) => e.host === host)
    .map((e) => ({ username: e.username }));
}

// 채움용 — host(+선택 username) 에 맞는 {username, password} 평문 반환
export function getCredential(urlOrHost, username) {
  const host = hostOf(urlOrHost);
  const match = loadVault().find(
    (e) => e.host === host && (username == null || e.username === username)
  );
  if (!match) return null;
  return { username: match.username, password: decPw(match.enc) };
}

// 저장/갱신 (host + username 이 키)
export function upsert(originOrUrl, username, password) {
  const host = hostOf(originOrUrl);
  const v = loadVault();
  const user = username || '';
  const entry = { host, origin: originOrUrl, username: user, enc: encPw(password) };
  const idx = v.findIndex((e) => e.host === host && e.username === user);
  if (idx >= 0) v[idx] = entry;
  else v.push(entry);
  saveVault(v);
  return true;
}

export function remove(originOrUrl, username) {
  const host = hostOf(originOrUrl);
  const user = username || '';
  const v = loadVault().filter((e) => !(e.host === host && e.username === user));
  saveVault(v);
  return true;
}

// 전체 목록 (비밀번호 없이 — 관리 화면용)
export function listAll() {
  return loadVault().map((e) => ({ host: e.host, origin: e.origin, username: e.username }));
}

// ─── 크롬 임포트 (macOS) ───
// 크롬 Safe Storage 키 → PBKDF2(salt='saltysalt', 1003회, SHA1, 16바이트)로 AES 키 유도.
function chromeAesKey() {
  let secret;
  try {
    // timeout 넉넉히(2분) — 키체인 잠금 해제 암호를 사람이 입력하는 시간을 기다려야 함.
    // (예전 15초는 암호 입력 도중 명령이 강제 종료돼 "가져오기 실패"의 주범이었음.)
    secret = execFileSync(
      'security',
      ['find-generic-password', '-s', 'Chrome Safe Storage', '-a', 'Chrome', '-w'],
      { encoding: 'utf-8', timeout: 120000 }
    ).trim();
  } catch (e) {
    if (e.killed || e.signal === 'SIGTERM') {
      throw new Error('키체인 응답 대기 시간 초과 — 암호 입력 후 다시 시도해 주세요');
    }
    // security 비정상 종료(키 없음/접근 거부 등). stderr 를 그대로 노출해 진단 가능하게.
    const detail = (e.stderr || e.message || '').toString().trim();
    throw new Error(`키체인에서 Chrome Safe Storage 키 접근 실패: ${detail || '알 수 없음'}`);
  }
  if (!secret) throw new Error('키체인에서 Chrome Safe Storage 키를 찾지 못했습니다');
  return crypto.pbkdf2Sync(secret, 'saltysalt', 1003, 16, 'sha1');
}

// password_value BLOB 복호화. macOS: 'v10' 접두 후 AES-128-CBC, IV=공백 16바이트.
function decryptChromePassword(blob, key) {
  if (!blob || blob.length === 0) return '';
  let buf = Buffer.from(blob);
  const prefix = buf.slice(0, 3).toString('latin1');
  if (prefix === 'v10' || prefix === 'v11') buf = buf.slice(3);
  const iv = Buffer.alloc(16, ' ');
  try {
    const decipher = crypto.createDecipheriv('aes-128-cbc', key, iv);
    return Buffer.concat([decipher.update(buf), decipher.final()]).toString('utf-8');
  } catch {
    return '';
  }
}

// 크롬 프로필 전수의 Login Data 를 읽어 금고로 흡수. {imported, total} 반환.
export function importFromChrome() {
  if (process.platform !== 'darwin') {
    throw new Error('크롬 비밀번호 가져오기는 현재 macOS만 지원합니다');
  }
  let DatabaseSync;
  try {
    ({ DatabaseSync } = require('node:sqlite'));
  } catch {
    throw new Error('이 Electron 버전에서 SQLite 읽기(node:sqlite)를 지원하지 않습니다');
  }

  const base = path.join(
    app.getPath('home'),
    'Library',
    'Application Support',
    'Google',
    'Chrome'
  );
  if (!fs.existsSync(base)) throw new Error('크롬 데이터 폴더를 찾지 못했습니다');

  const profiles = ['Default'];
  try {
    for (const name of fs.readdirSync(base)) {
      if (/^Profile \d+$/.test(name)) profiles.push(name);
    }
  } catch {
    /* 프로필 스캔 실패 무시 — Default 만 */
  }

  const key = chromeAesKey(); // 키체인 접근 — 첫 실행 시 macOS 가 허용을 물을 수 있음
  let imported = 0;
  let total = 0;

  for (const prof of profiles) {
    const dbPath = path.join(base, prof, 'Login Data');
    if (!fs.existsSync(dbPath)) continue;

    // 크롬 실행 중엔 DB 가 잠겨 있으므로 temp 로 복사 후 읽기.
    const tmp = path.join(app.getPath('temp'), `forage_login_${prof.replace(/\s/g, '_')}.db`);
    let db = null;
    try {
      fs.copyFileSync(dbPath, tmp);
      db = new DatabaseSync(tmp, { readOnly: true });
      const rows = db
        .prepare('SELECT origin_url, username_value, password_value FROM logins')
        .all();
      for (const r of rows) {
        total++;
        const pw = decryptChromePassword(r.password_value, key);
        if (!pw) continue;
        try {
          upsert(r.origin_url, r.username_value || '', pw);
          imported++;
        } catch {
          /* 개별 항목 실패 무시 */
        }
      }
    } catch {
      /* 프로필 단위 실패는 건너뛰고 계속 */
    } finally {
      try {
        if (db) db.close();
      } catch {}
      try {
        fs.unlinkSync(tmp);
      } catch {}
    }
  }

  return { imported, total };
}
