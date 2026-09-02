/**
 * userdata_sync.js — 설치본(resources) → 사용자 폴더(userData) 동기화, 트랜잭션 판
 * (2026-09-02, docs/FIRST_SUCCESS_AND_UPGRADE_GATE_HANDOFF.md ② C·D)
 *
 * bootstrap.js 에서 분리한 이유 둘:
 *  1. electron 을 import 하지 않는다 — 업그레이드 스모크(scripts/ci_upgrade_smoke.py)가 node 로
 *     직접 불러 노후 설치본 위에서 돌려 볼 수 있어야 관문이 선다.
 *  2. 직접 copyFileSync 였던 동기화를 **저널 트랜잭션**으로 만든다:
 *       - 덮어쓰기 전에 원본을 data/_backups/<날짜>_upgrade/ 로 뜨고 저널(JSONL)에 한 줄 적는다
 *       - 시작 전 data/.upgrade_pending 표식(저널 경로) → 끝나면 지운다
 *       - 다음 기동에 표식이 남아 있으면 = 지난 동기화가 도중에 죽음 → 저널로 원상복구 뒤 다시 동기화
 *       - 내용이 같은 파일은 건드리지 않는다(같은 버전 재기동 = 저널 0줄, 백업 폴더 안 생김)
 *     왜 스테이징 폴더 스왑이 아닌가: userData 에는 사용자 DB(해마·포식 수백 MB)가 산다 — 통째 복사는
 *     무겁고, 동기화가 건드리는 건 코어 소유 파일뿐이라 저널이 정확히 그 범위를 덮는다
 *     (red_watchdog 의 {path→backup|null} 형식과 같은 꼴 — 자기수리와 같은 규율).
 *  3. 매니페스트의 은퇴 목록(retired)을 **격리 이동**한다(실삭제 아님 — 사용자 판정 2026-09-02).
 *
 * 사용자 소유물(DB·설정 json·미추적 패키지·자작 앱)은 여기서 순회조차 하지 않는다 — 종전 규칙 그대로.
 */
import path from 'path';
import fs from 'fs';
import crypto from 'crypto';

const OVERWRITE_EXTENSIONS = new Set(['.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.scss', '.md']);
const ALWAYS_OVERWRITE_FILES = new Set(['tool.json', 'requirements.txt', 'package.json']);
const SKIP_DIRS = new Set(['node_modules', '__pycache__', '.git', '_temp_']);

function fileHash(p) {
  const h = crypto.createHash('sha1');
  h.update(fs.readFileSync(p));
  return h.digest('hex');
}

function sameContent(a, b) {
  try {
    const sa = fs.statSync(a), sb = fs.statSync(b);
    if (sa.size !== sb.size) return false;
    return fileHash(a) === fileHash(b);
  } catch { return false; }
}

function stamp(d = new Date()) {
  const z = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
}

/**
 * 트랜잭션 — 저널은 JSONL(한 파일 한 줄, append). 매 줄을 파일 조작 *전에* 적는다.
 *   {op:'overwrite', path, backup}   backup=null 이면 신규 파일(롤백=삭제)
 *   {op:'move', path, backup}        격리 이동(롤백=되돌리기)
 */
class Tx {
  constructor(userDataPath, log, failAfterEntries = 0) {
    this.userDataPath = userDataPath;
    this.log = log;
    this.failAfterEntries = failAfterEntries;   // 시험 전용 — N줄 뒤 죽는 동기화를 재현
    this.backupDir = path.join(userDataPath, 'data', '_backups', `${stamp()}_upgrade`);
    this.journalPath = path.join(this.backupDir, 'journal.jsonl');
    this.markerPath = path.join(userDataPath, 'data', '.upgrade_pending');
    this.lines = 0;
    this._opened = false;
  }
  _open() {
    if (this._opened) return;
    fs.mkdirSync(this.backupDir, { recursive: true });
    fs.mkdirSync(path.dirname(this.markerPath), { recursive: true });
    fs.writeFileSync(this.markerPath, this.journalPath, 'utf-8');
    this._opened = true;
  }
  _backupPathFor(dest) {
    const rel = path.relative(this.userDataPath, dest).split(path.sep).join('/');
    return path.join(this.backupDir, 'files', rel);
  }
  _append(entry) {
    this._open();
    fs.appendFileSync(this.journalPath, JSON.stringify(entry) + '\n', 'utf-8');
    this.lines += 1;
    if (this.failAfterEntries && this.lines >= this.failAfterEntries) {
      throw new Error(`[test] 동기화 도중 죽음 재현 (${this.lines}줄 뒤)`);
    }
  }
  /** dest 를 src 로 덮어쓴다(내용이 같으면 no-op). */
  overwrite(src, dest) {
    if (fs.existsSync(dest)) {
      if (sameContent(src, dest)) return false;
      const backup = this._backupPathFor(dest);
      fs.mkdirSync(path.dirname(backup), { recursive: true });
      fs.copyFileSync(dest, backup);
      this._append({ op: 'overwrite', path: dest, backup });
    } else {
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      this._append({ op: 'overwrite', path: dest, backup: null });
    }
    fs.copyFileSync(src, dest);
    return true;
  }
  /** 파일/폴더를 격리 폴더로 옮긴다. */
  quarantine(target) {
    if (!fs.existsSync(target)) return false;
    const rel = path.relative(this.userDataPath, target).split(path.sep).join('/');
    const backup = path.join(this.backupDir, 'retired', rel);
    fs.mkdirSync(path.dirname(backup), { recursive: true });
    this._append({ op: 'move', path: target, backup });
    fs.renameSync(target, backup);
    return true;
  }
  finish(meta) {
    if (!this._opened) return { changed: 0 };
    fs.writeFileSync(path.join(this.backupDir, 'manifest.json'),
      JSON.stringify({ ...meta, journal: this.journalPath, entries: this.lines, finished_at: new Date().toISOString() }, null, 2));
    fs.rmSync(this.markerPath, { force: true });
    return { changed: this.lines, backupDir: this.backupDir };
  }
}

/** 지난 동기화가 도중에 죽었을 때 — 표식이 가리키는 저널을 거꾸로 되감는다. */
function rollbackPending(userDataPath, log) {
  const marker = path.join(userDataPath, 'data', '.upgrade_pending');
  if (!fs.existsSync(marker)) return null;
  const journalPath = fs.readFileSync(marker, 'utf-8').trim();
  const restored = [];
  if (fs.existsSync(journalPath)) {
    const lines = fs.readFileSync(journalPath, 'utf-8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
    for (const e of lines.reverse()) {
      try {
        if (e.op === 'overwrite') {
          if (e.backup && fs.existsSync(e.backup)) fs.copyFileSync(e.backup, e.path);
          else if (e.backup === null) fs.rmSync(e.path, { force: true });
        } else if (e.op === 'move') {
          if (fs.existsSync(e.backup)) { fs.mkdirSync(path.dirname(e.path), { recursive: true }); fs.renameSync(e.backup, e.path); }
        }
        restored.push(e.path);
      } catch (err) {
        log(`[Init] 롤백 실패 ${e.path}: ${err}`);
      }
    }
  }
  fs.rmSync(marker, { force: true });
  log(`[Init] ★지난 업그레이드가 도중에 죽어 있었다 — 저널로 ${restored.length}건 원상복구 후 다시 동기화`);
  return restored;
}

function syncDir(tx, srcDir, destDir, forceOverwrite, skipPaths) {
  if (!fs.existsSync(destDir)) fs.mkdirSync(destDir, { recursive: true });
  for (const entry of fs.readdirSync(srcDir, { withFileTypes: true })) {
    const srcPath = path.join(srcDir, entry.name);
    const destPath = path.join(destDir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      if (skipPaths && skipPaths.has(srcPath)) continue;
      syncDir(tx, srcPath, destPath, forceOverwrite, skipPaths);
    } else if (entry.isFile()) {
      if (!fs.existsSync(destPath)) { tx.overwrite(srcPath, destPath); continue; }
      const ext = path.extname(entry.name).toLowerCase();
      const isCore = forceOverwrite ? forceOverwrite(destPath) : false;
      if (isCore || OVERWRITE_EXTENSIONS.has(ext) || ALWAYS_OVERWRITE_FILES.has(entry.name)) tx.overwrite(srcPath, destPath);
    }
  }
}

function loadManifest(resourcesPath, log, manifestPath = null) {
  try {
    const p = manifestPath || path.join(resourcesPath, 'data', 'core_manifest.json');
    if (!fs.existsSync(p)) return null;
    return JSON.parse(fs.readFileSync(p, 'utf-8'));
  } catch (e) {
    log(`[Init] core_manifest 로드 실패 (보수적 동기화 유지): ${e}`);
    return null;
  }
}

/** 코어 소유 어휘 산출물 판정 술어 (종전 makeCoreForceOverwrite 와 동일 의미). */
function makeCoreForceOverwrite(manifest) {
  if (!manifest) return null;
  const core = manifest.core || {};
  const vocabArtifacts = new Set(core.vocab_artifacts || []);
  const coreInstruments = new Set(core.instruments || []);
  const corePackages = new Set([...((core.packages || {}).tools || []), ...((core.packages || {}).extensions || [])]);
  return (destPath) => {
    const norm = destPath.split(path.sep).join('/');
    const base = path.basename(norm);
    if (vocabArtifacts.has(base)) return true;
    const instMatch = norm.match(/\/data\/instruments\/([^/]+)\.yaml$/);
    if (instMatch && coreInstruments.has(instMatch[1])) return true;
    if (base === 'ibl_actions.yaml') {
      const pkgMatch = norm.match(/\/packages\/(?:installed|not_installed)\/(?:tools|extensions)\/([^/]+)\//);
      if (pkgMatch && corePackages.has(pkgMatch[1])) return true;
    }
    return false;
  };
}

/** 패키지 — 설치 상태(installed/not_installed 배치 = 사용자 선택) 보존 동기화 (종전 의미 그대로). */
function syncPackages(tx, resourcesPath, userDataPath, forceOverwrite, log) {
  for (const kind of ['tools', 'extensions']) {
    for (const bundleState of ['installed', 'not_installed']) {
      const bundleDir = path.join(resourcesPath, 'data', 'packages', bundleState, kind);
      if (!fs.existsSync(bundleDir)) continue;
      for (const pkg of fs.readdirSync(bundleDir)) {
        const pkgSrc = path.join(bundleDir, pkg);
        if (!fs.statSync(pkgSrc).isDirectory()) continue;
        const userInstalled = path.join(userDataPath, 'data', 'packages', 'installed', kind, pkg);
        const userNotInstalled = path.join(userDataPath, 'data', 'packages', 'not_installed', kind, pkg);
        let pkgDest;
        if (fs.existsSync(userInstalled)) pkgDest = userInstalled;
        else if (fs.existsSync(userNotInstalled)) pkgDest = userNotInstalled;
        else pkgDest = path.join(userDataPath, 'data', 'packages', bundleState, kind, pkg);
        syncDir(tx, pkgSrc, pkgDest, forceOverwrite, null);
      }
    }
  }
}

/** 은퇴 목록 격리 — 매니페스트가 "코어였다"고 기억하는 이름만. 사용자 것은 애초에 core 에 없었다. */
function quarantineRetired(tx, manifest, userDataPath, log) {
  const retired = (manifest && manifest.retired) || {};
  const moved = [];
  const tryMove = (p) => { if (tx.quarantine(p)) moved.push(p); };
  for (const kind of ['tools', 'extensions']) {
    for (const name of retired[`packages.${kind}`] || []) {
      for (const state of ['installed', 'not_installed']) tryMove(path.join(userDataPath, 'data', 'packages', state, kind, name));
    }
  }
  for (const name of retired.instruments || []) tryMove(path.join(userDataPath, 'data', 'instruments', `${name}.yaml`));
  for (const name of retired.vocab_fragments || []) tryMove(path.join(userDataPath, 'data', 'ibl_nodes_src', name));
  if (moved.length) log(`[Init] 은퇴 코어 ${moved.length}건 격리 이동 → ${tx.backupDir}/retired`);
  return moved;
}

/**
 * 진입점. 반환 {changed, backupDir?, rolledBack?, retired}.
 * 실패는 던진다 — 표식이 남으므로 다음 기동이 되감는다(자기 죽음 뒤 단계를 여기서 계획하지 않는다).
 */
export function syncUserData({ resourcesPath, userDataPath, version = '', log = console.log,
                               manifestPath = null, failAfterEntries = 0 }) {
  const rolledBack = rollbackPending(userDataPath, log);
  const manifest = loadManifest(resourcesPath, log, manifestPath);
  const forceOverwrite = makeCoreForceOverwrite(manifest);
  const tx = new Tx(userDataPath, log, failAfterEntries);

  // 1. 기본 폴더 (packages 하위트리 제외 — 2 에서 상태 보존 동기화)
  const skipPaths = new Set([path.join(resourcesPath, 'data', 'packages')]);
  for (const dir of ['data', 'projects', 'templates', 'tokens']) {
    const src = path.join(resourcesPath, dir);
    if (fs.existsSync(src)) syncDir(tx, src, path.join(userDataPath, dir), forceOverwrite, skipPaths);
  }
  // 2. 패키지 (설치 상태 보존)
  syncPackages(tx, resourcesPath, userDataPath, forceOverwrite, log);
  // 3. common_prompts — 종전 rm+cp 대신 파일 단위 덮어쓰기(저널에 남는다) + 번들에 없는 파일 격리
  const promptsSrc = path.join(resourcesPath, 'data', 'common_prompts');
  const promptsDest = path.join(userDataPath, 'data', 'common_prompts');
  if (fs.existsSync(promptsSrc)) {
    syncDir(tx, promptsSrc, promptsDest, () => true, null);
    if (fs.existsSync(promptsDest)) {
      for (const f of fs.readdirSync(promptsDest)) {
        if (!fs.existsSync(path.join(promptsSrc, f))) tx.quarantine(path.join(promptsDest, f));
      }
    }
  }
  // 4. .env (없으면 시드)
  const envSrc = path.join(resourcesPath, 'backend', '.env');
  const envDest = path.join(userDataPath, '.env');
  if (!fs.existsSync(envDest) && fs.existsSync(envSrc)) fs.copyFileSync(envSrc, envDest);
  // 5. 은퇴 코어 격리
  const retired = quarantineRetired(tx, manifest, userDataPath, log);

  const done = tx.finish({ version, resourcesPath, rolled_back: rolledBack ? rolledBack.length : 0 });
  if (done.changed) log(`[Init] 동기화 ${done.changed}건 (백업·저널: ${done.backupDir})`);
  else log('[Init] 동기화: 변경 없음');
  return { ...done, rolledBack, retired };
}

export { rollbackPending, makeCoreForceOverwrite };
