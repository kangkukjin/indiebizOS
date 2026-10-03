import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createUI } from '../i18n/runtime.mjs';
import { validTranslation } from './ui-catalog.mjs';
const read = name => JSON.parse(fs.readFileSync(new URL(`../i18n/${name}.json`, import.meta.url)));
const catalog = read('catalog');

test('Japanese release covers every registered source and preserves protected tokens', () => {
  assert.equal(read('languages').ja, '日本語');
  assert.deepEqual(catalog.languages, read('languages'));
  assert.ok(Object.keys(catalog.messages).length > 5000);
  const memory = read('translations');
  for (const [id, message] of Object.entries(catalog.messages)) {
    for (const locale of ['en', 'ja']) {
      assert.equal(memory[locale][id].source, message.source, id);
      assert.equal(message.translations[locale], memory[locale][id].text, id);
      assert.ok(validTranslation(message.source, message.translations[locale], memory[locale][id].reviewed === true, message.context), `${locale}: ${message.source}`);
    }
  }
});

test('Japanese selection persists, propagates to sibling windows and preserves dynamic data', () => {
  const storage = new Map();
  const events = new Map();
  const host = {localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
    document:{documentElement:{}},addEventListener:(name,fn)=>events.set(name,fn)};
  const ui = createUI(catalog,host);
  ui.setLocale('ja');
  assert.equal(host.document.documentElement.lang,'ja');
  assert.equal(createUI(catalog,host).getLocale(),'ja');
  const [id, message] = Object.entries(catalog.messages).find(([,m])=>m.context==='system:status' && m.source==='ibl_health_check 실행 실패: {0}');
  const user = '사용자 $& <raw>.py';
  assert.equal(ui.text(id,[user]),message.translations.ja.replace('{0}',()=>user));
  assert.equal(ui.system('ibl_health_check 실행 실패: '+user),ui.text(id,[user]));
  for (const locale of ['en','ko','ja']) {
    events.get('storage')({key:'indiebiz.ui.locale',newValue:locale});
    assert.equal(host.document.documentElement.lang,locale);
  }
});

test('remote and X-Ray generated shells ship the Japanese registry and translations', () => {
  for (const name of ['remote','xray']) {
    const html = read(name).html;
    assert.ok(html.includes('"ja":"日本語"'),name);
    assert.ok(html.includes('"ja":'),name);
    assert.ok(html.includes('indiebiz.ui.locale'),name);
  }
});
