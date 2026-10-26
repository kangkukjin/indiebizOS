import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { collector, compileReact, compileRemoteJS } from './ui-compiler.mjs';
import { createUI } from '../i18n/runtime.mjs';

const read = file => fs.readFileSync(new URL(file, import.meta.url), 'utf8');
const labels = ['검수 승인', '기준 미충족', '검수 미완료', '미검수', '목표 달성', '목표 미달', '목표 미확정'];
const memory = JSON.parse(read('../i18n/translations.json'));

test('journal review and goal labels are collected and translated on both surfaces', () => {
  for (const surface of ['react', 'remote']) {
    const catalog = collector();
    if (surface === 'react') {
      compileReact(read('../src/components/EpisodeJournal.tsx'), 'frontend/src/components/EpisodeJournal.tsx', catalog);
    } else {
      compileRemoteJS(read('../surfaces/remote/launcher_manual_js.js'), catalog);
    }
    for (const source of labels) {
      const entry = Object.entries(catalog.messages).find(([, message]) => message.source === source);
      assert.ok(entry, `${surface}: ${source} must enter the catalog`);
      const [id, message] = entry;
      message.translations = Object.fromEntries(['en', 'ja'].map(lang => {
        assert.equal(memory[lang][id]?.source, source);
        assert.ok(memory[lang][id].text);
        return [lang, memory[lang][id].text];
      }));
    }
    const ui = createUI({ languages: {ko: '한국어', en: 'English', ja: '日本語'}, messages: catalog.messages }, {});
    for (const locale of ['en', 'ja', 'ko']) {
      ui.setLocale(locale);
      for (const source of labels) {
        const [id] = Object.entries(catalog.messages).find(([, message]) => message.source === source);
        assert.equal(ui.text(id), locale === 'ko' ? source : memory[locale][id].text);
      }
    }
  }
});

function declarations(file, names) {
  const source = read(file);
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
  return ast.statements.filter(node => ts.isFunctionDeclaration(node) && names.includes(node.name?.text))
    .map(node => node.getText(ast)).join('\n');
}

test('remote journal marks only source labels and escapes dynamic metadata', () => {
  const code = declarations('../surfaces/remote/launcher_manual_js.js', ['jRel', 'jMeta']) + '\n' +
    declarations('../surfaces/shared/launcher_common_js.js', ['esc', 'systemText']);
  const context = vm.createContext({document: {createElement: () => ({
    textContent: '',
    get innerHTML() { return String(this.textContent).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'); },
  })}});
  vm.runInContext(code, context);
  const ep = {agent: '<img src=x onerror=alert(1)>', review_status: 'APPROVED', goal_status: 'NOT_ACHIEVED'};
  const html = context.jMeta(ep);
  assert.ok(html.includes('data-ui-system="검수 승인"'));
  assert.ok(html.includes('data-ui-system="목표 미달"'));
  assert.ok(html.includes('&lt;img'));
  assert.ok(!html.includes('<img'));
  const unknown = context.jMeta({...ep, review_status: '<unknown>', agent: '검수 승인'});
  assert.ok(unknown.includes('&lt;unknown&gt;'));
  assert.equal((unknown.match(/data-ui-system=/g) || []).length, 1);
  assert.ok(unknown.startsWith('검수 승인 · '));
  assert.ok(!unknown.includes('data-ui-system="검수 승인"'));
});
