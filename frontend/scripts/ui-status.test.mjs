import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import { collector } from './ui-compiler.mjs';
import { refresh } from './ui-catalog.mjs';
import { createUI } from '../i18n/runtime.mjs';

const catalog = JSON.parse(fs.readFileSync(new URL('../i18n/catalog.json', import.meta.url)));
const status = Object.entries(catalog.messages).filter(([, m]) => m.context === 'system:status');

test('health source definitions are cataloged with complete templates and English translations', () => {
  const sources = JSON.parse(execFileSync('../.venv/bin/python3', ['-c', 'import runpy,json; print(json.dumps(runpy.run_path("scripts/ui-system-sources.py")["status_sources"]()))'], {encoding:'utf8'}));
  assert.equal(status.length, sources.length);
  for (const source of sources) {
    const message = status.find(([, m]) => m.source === source)?.[1];
    assert.ok(message?.translations.en, source);
    assert.ok(!/[가-힣]/.test(message.translations.en), source);
  }
  assert.ok(sources.includes('ibl_health_check 실행 실패: {0}'));
  assert.ok(!sources.includes('ibl_health_check 실행 실패: '));
});

test('registered Japanese resources work through refresh and preserve opaque diagnostics', async () => {
  const c = collector();
  const label = c.add('system:status', '점검 실행 — 검사기 자체');
  const error = c.add('system:status', 'ibl_health_check 실행 실패: {0}');
  const missing = c.add('system:status', '미번역 테스트');
  const languages = {...catalog.languages, ja:'日本語'};
  const memory = {ja:{
    [label]:{source:c.messages[label].source,text:'検査の実行 — 検査プログラム'},
    [error]:{source:c.messages[error].source,text:'ibl_health_check の実行に失敗: {0}'},
  }};
  await refresh(c.messages, memory, {ko:languages.ko,ja:languages.ja}, async () => { throw new Error('intentional missing translation'); });
  for (const [id, m] of Object.entries(c.messages)) m.translations = {ja:memory.ja[id]?.text};
  const ui = createUI({languages,messages:c.messages}, {});
  ui.setLocale('ja');
  assert.equal(ui.system(c.messages[label].source), '検査の実行 — 検査プログラム');
  const raw = '사용자파일 $& <raw>.py\n설명 정합 — 어휘 설명 최신성';
  assert.equal(ui.system('ibl_health_check 실행 실패: ' + raw), 'ibl_health_check の実行に失敗: ' + raw);
  assert.equal(ui.system(c.messages[missing].source), c.messages[missing].source);
  assert.equal(ui.system('사용자가 쓴 점검 실행 — 검사기 자체'), '사용자가 쓴 점검 실행 — 검사기 자체');
  ui.setLocale('ko');
  assert.equal(ui.system('ibl_health_check 실행 실패: ' + raw), 'ibl_health_check 실행 실패: ' + raw);
});

test('every English status template retains punctuation, identifiers and values', () => {
  const ui = createUI(catalog, {});
  ui.setLocale('en');
  for (const [, m] of status) {
    const value = m.source.replace(/\{(\d+)\}/g, (_, n) => `RAW_${n}_사용자$&<file>`);
    const expected = m.translations.en.replace(/\{(\d+)\}/g, (_, n) => `RAW_${n}_사용자$&<file>`);
    assert.equal(ui.system(value), expected, m.source);
  }
});
