import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { collector } from './ui-compiler.mjs';
import { registerBoundaryMessages, refresh } from './ui-catalog.mjs';
import { createUI } from '../i18n/runtime.mjs';

function fixture() {
  const c = collector(), memory = {};
  const native = JSON.parse(fs.readFileSync(new URL('../i18n/native-messages.json', import.meta.url)));
  const system = JSON.parse(fs.readFileSync(new URL('../i18n/system-messages.json', import.meta.url)));
  registerBoundaryMessages(c, memory, native, system);
  const messages = Object.fromEntries(Object.entries(c.messages).map(([id, entry]) => [id, {
    ...entry, translations: { en: memory.en[id].text }, plurals: { en: memory.en[id].forms },
  }]));
  return { catalog: { languages: { ko: '한국어', en: 'English' }, messages }, memory };
}

test('native labels and system messages preserve unknown text and parameters', () => {
  const { catalog } = fixture();
  const ui = createUI(catalog, {});
  ui.setLocale('en');
  assert.equal(ui.source('native:ui', '문서'), 'Documents');
  assert.equal(ui.source('native:ui', '사용자 문서'), '사용자 문서');
  const param = '<script>한글 $& {0}</script>';
  assert.equal(ui.error({detail:{code:'ui.path.failed',params:[param]}}), `Path access failed (network/drive error): ${param}`);
  assert.equal(ui.error({detail:{code:'external.error',message:param}}), param);
  assert.equal(ui.error({detail:param}), param);
  ui.setLocale('ko');
  assert.equal(ui.source('native:ui', '문서'), '문서');
  assert.equal(ui.error({detail:{code:'ui.path.missing',params:[]}}), '경로를 찾을 수 없습니다');
});

test('plural, number, date, missing translation and invalid placeholders', () => {
  const { catalog } = fixture();
  const ui = createUI(catalog, {});
  ui.setLocale('en');
  assert.equal(ui.text('ui.items.count', [1], 1), '1 item');
  assert.equal(ui.text('ui.items.count', [2], 2), '2 items');
  assert.equal(ui.text('ui.items.count', [0], 0), '0 items');
  assert.equal(ui.number(1234.5), new Intl.NumberFormat('en').format(1234.5));
  assert.equal(ui.date('2026-10-03T12:00:00Z', {timeZone:'UTC'}), new Intl.DateTimeFormat('en', {timeZone:'UTC'}).format(new Date('2026-10-03T12:00:00Z')));
  catalog.messages['ui.path.failed'].translations.en = 'Wrong {1}';
  assert.equal(ui.text('ui.path.failed', ['원문']), '경로 접근 실패 (네트워크/드라이브 오류): 원문');
  delete catalog.messages['ui.path.missing'].translations.en;
  assert.equal(ui.text('ui.path.missing'), '경로를 찾을 수 없습니다');
  ui.setLocale('ko');
  assert.equal(ui.text('ui.items.count', [1], 1), '1개 항목');
  assert.equal(ui.text('ui.items.count', [2], 2), '2개 항목');
});

test('third language registration flows through refresh, lookup and Intl', async () => {
  const c = collector(), memory = {};
  registerBoundaryMessages(c, memory, {'문서':'Documents'}, {});
  const languages = {ko:'한국어', en:'English', de:'Deutsch'};
  const stats = await refresh(c.messages, memory, languages, async (texts, lang) => {
    assert.equal(lang, 'de'); assert.deepEqual(texts, ['문서']); return ['Dokumente'];
  });
  assert.equal(stats.failed, 0); assert.equal(stats.translated, 1);
  for (const [id, entry] of Object.entries(c.messages)) entry.translations = Object.fromEntries(Object.keys(languages).filter(l=>memory[l]?.[id]).map(l=>[l,memory[l][id].text]));
  const ui = createUI({languages, messages:c.messages}, {});
  ui.setLocale('de');
  assert.equal(ui.source('native:ui','문서'),'Dokumente');
  assert.equal(ui.number(1234.5),'1.234,5');
  assert.equal(ui.date('2026-10-03T12:00:00Z',{timeZone:'UTC'}),'3.10.2026');
  c.messages.count = {source:'{0}개 항목',translations:{de:'{0} Elemente'},plurals:{de:{one:'{0} Element',other:'{0} Elemente'}}};
  assert.equal(ui.text('count',[1],1),'1 Element');
  assert.equal(ui.text('count',[2],2),'2 Elemente');
  c.messages.count.plurals.de.one = '{9} Element';
  assert.equal(ui.text('count',[1],1),'1개 항목');
});

test('unsupported and inherited locale names cannot enter runtime or storage', () => {
  const { catalog } = fixture();
  const listeners = {};
  const ui = createUI(catalog, {localStorage:{getItem:()=> 'constructor'},addEventListener:(k,f)=>listeners[k]=f});
  assert.equal(ui.getLocale(),'ko');
  for (const locale of ['toString','__proto__','xx-Invalid']) ui.setLocale(locale);
  assert.equal(ui.getLocale(),'ko');
  ui.setLocale('en');
  listeners.storage({key:'indiebiz.ui.locale',newValue:null});
  assert.equal(ui.getLocale(),'ko');
});

test('Electron event wins over stale initial snapshot without rebroadcast loop', async () => {
  const { catalog } = fixture();
  let callback, resolve, sent = [];
  const ui = createUI(catalog, {electron:{
    onUILocale: fn => callback = fn,
    getUILocale: () => new Promise(fn => resolve = fn),
    setUILocale: value => sent.push(value),
  }});
  callback('en'); resolve('ko'); await Promise.resolve();
  assert.equal(ui.getLocale(),'en'); assert.deepEqual(sent,[]);
  ui.setLocale('ko'); assert.deepEqual(sent,['ko']);
});

test('packaged native runtime and catalog are included', () => {
  const pkg = JSON.parse(fs.readFileSync(new URL('../package.json',import.meta.url)));
  assert.ok(pkg.build.files.includes('i18n/catalog.json'));
  assert.ok(pkg.build.files.includes('i18n/runtime.mjs'));
});
