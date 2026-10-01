import test from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
import { collector, compileReact, compileHTML, compileRemoteJS, messageId } from './ui-compiler.mjs';
import { refresh, validTranslation } from './ui-catalog.mjs';
import { createUI } from '../i18n/runtime.mjs';

test('reviewed empty translations survive refresh and render without Korean particles', async () => {
  const memory = {en:{particle:{source:'을',text:'',reviewed:true}}};
  const messages = {particle:{source:'을'}};
  const stats = await refresh(messages,memory,{ko:'한국어',en:'English'},()=>{throw Error('must reuse')});
  assert.equal(stats.reused,1);
  const ui = createUI({messages:{particle:{source:'을',translations:{en:''}}}},{localStorage:{getItem:()=> 'en'}});
  assert.equal(ui.text('particle'),'');
});

const compile = source => { const catalog = collector(); return { code: compileReact(source, 'ui.tsx', catalog), messages: catalog.messages }; };
test('UI positions only: runtime content, identifiers, values, examples and secrets stay untouched', () => {
  const source = `const secret='비밀키'; const filename='개인문서.txt'; const App=()=> <div><button title="열기">열기</button><p>{chat}</p><input value={secret} placeholder="검색"/><code>한국어 코드</code><pre>사용자 예시</pre><div translate="no">개인 콘텐츠</div><textarea value={draft}/></div>`;
  const { code, messages } = compile(source);
  assert.deepEqual(new Set(Object.values(messages).map(m => m.source)), new Set(['열기', '검색']));
  for (const preserved of ["const secret='비밀키'", "const filename='개인문서.txt'", '{chat}', 'value={secret}', '한국어 코드', '개인 콘텐츠', 'value={draft}']) assert.ok(code.includes(preserved), preserved);
  assert.equal(ts.createSourceFile('out.tsx', code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX).parseDiagnostics.length, 0);
});
test('stable context keys change on source edits; interpolation expressions never sent', () => {
  const { messages, code } = compile('const App=()=> <span>{`항목 ${user.name}개`}</span>');
  assert.deepEqual(Object.values(messages).map(m => m.source), ['항목 {0}개']);
  assert.ok(code.includes('values={[user.name]}'));
  assert.equal(messageId('button', '저장'), messageId('button', '저장'));
  assert.notEqual(messageId('button', '저장'), messageId('button', '보관'));
  assert.notEqual(messageId('button', '저장'), messageId('noun', '저장'));
});
test('remote shell and later-rendered HTML are marked, data paths remain untouched', () => {
  const c = collector();
  const html = compileHTML('<button title="닫기">닫기</button><textarea>비공개 초안</textarea><div translate="no"><span>비밀 자료</span></div><div class="about-code">[sense:realty]{region:&quot;강남구&quot;}</div><script>const secret="비밀"</script>', 'remote:shell', c);
  assert.ok(html.includes('data-ui-text'));
  assert.deepEqual(new Set(Object.values(c.messages).map(m => m.source)), new Set(['닫기']));
  const js = compileRemoteJS(`el.innerHTML='<button>추가</button>'+esc(user.name); el.textContent='실패'; other.textContent=chat;`, c);
  assert.ok(js.includes('data-ui-text'));
  assert.ok(js.includes('window.__uiSetText(el,'));
  assert.ok(js.includes('esc(user.name)'));
  assert.ok(js.includes('other.textContent=chat'));
  assert.equal(ts.createSourceFile('remote.js', js, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS).parseDiagnostics.length, 0);
});
test('translation memory reuses human edits, requests only new source, failures stay retryable', async () => {
  const messages = { a: { source: '저장' }, b: { source: '항목 {0}개' }, c: { source: '실패' } };
  const memory = { en: { a: { source: '저장', text: 'Keep my correction' } } };
  let sent;
  const stats = await refresh(messages, memory, { ko: '한국어', en: 'English' }, async texts => { sent = texts; return ['Items {0}', '실패']; });
  assert.deepEqual(sent, ['항목 {0}개', '실패']);
  assert.equal(memory.en.a.text, 'Keep my correction'); assert.equal(stats.reused, 1);
  assert.equal(stats.failed, 1); assert.ok(!memory.en.c);
  assert.equal(memory.en.b.text, 'Items {0}');
  assert.equal(validTranslation('항목 {0}개', 'Items'), false);
  assert.equal(validTranslation('열기', '<script>alert(1)</script>'), false);
  const failed = await refresh({ x: { source: '닫기' } }, memory, { en: 'English' }, async () => { throw new Error('offline'); });
  assert.equal(failed.failed, 1); assert.ok(!memory.en.x);
});
test('locale persists, storage unavailable falls back, variables remain literal text', () => {
  const storage = new Map(); const host = { localStorage: { getItem: k => storage.get(k), setItem: (k, v) => storage.set(k, v) }, addEventListener() {} };
  const catalog = { languages: { ko: '한국어', en: 'English', ja: '日本語' }, messages: { a: { source: '항목 {0}개', translations: { en: 'Items {0}' } }, b: { source: '실패', translations: {} } } };
  const ui = createUI(catalog, host); ui.setLocale('en');
  assert.equal(ui.text('a', ['<b>$&</b>']), 'Items <b>$&</b>');
  assert.equal(ui.text('b'), '실패');
  assert.equal(createUI(catalog, host).getLocale(), 'en');
  ui.setLocale('ko'); assert.equal(ui.text('a', [3]), '항목 3개');
  ui.setLocale('ja'); assert.equal(ui.text('a', [3]), '항목 3개');
  assert.equal(createUI(catalog, { get localStorage() { throw new Error('disabled'); } }).getLocale(), 'ko');
});
