import test from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
import { collector, compileReact, compileHTML, compileRemoteJS, messageId } from './ui-compiler.mjs';
import { refresh, validTranslation, mergeMemoryEdits, maskSource, requireCompleteTranslations } from './ui-catalog.mjs';
import { createUI } from '../i18n/runtime.mjs';

test('provider outage stops queued batches and cannot pass the build boundary', async () => {
  const messages = Object.fromEntries(Array.from({length:265}, (_, i) => [String(i), {source:'미번역 '+i}]));
  let calls = 0;
  const memory = {};
  const stats = await refresh(messages, memory, {ko:'한국어',en:'English'}, async () => {
    calls++; throw new Error('offline');
  });
  assert.equal(calls, 3);
  assert.equal(stats.failed, 265);
  assert.equal(stats.translated, 0);
  assert.deepEqual(memory.en, {});
  assert.throws(() => requireCompleteTranslations(stats), {code:'UI_TRANSLATION_INCOMPLETE'});
  assert.doesNotThrow(() => requireCompleteTranslations({failed:0}));
});

test('API help translation preserves executable examples and named template variables', () => {
  const source = '날씨 조회 [sense:weather]{city:"서울"} · {name} 안내';
  const masked = maskSource(source);
  assert.equal(masked.masked, '날씨 조회 ⟦KEEP0⟧ · ⟦KEEP1⟧ 안내');
  const translated = masked.restore('Weather lookup ⟦KEEP0⟧ · Help for ⟦KEEP1⟧');
  assert.equal(translated, 'Weather lookup [sense:weather]{city:"서울"} · Help for {name}');
  assert.ok(validTranslation(source, translated));
  assert.equal(masked.restore('Weather ⟦KEEP0⟧'), null);
  assert.equal(validTranslation(source, 'Weather {other}'), false);
});

test('manifest translation changes display copies only and restores the Korean source', () => {
  const raw = {id:'weather',name:'날씨',inputs:[{key:'도시',label:'도시 이름',default:'서울'}],
    action:'[sense:weather]{city:$도시}',view:[{label:'현재 {city}',value:'{temperature}'}]};
  const translations = {'날씨':'Weather','도시 이름':'City name','현재 {city}':'Current {city}'};
  const messages = Object.fromEntries(Object.entries(translations).map(([source,en],i)=>[i,{source,context:'system:metadata',translations:{en}}]));
  const fields = [{path:['name'],source:'날씨'},{path:['inputs',0,'label'],source:'도시 이름'},{path:['view',0,'label'],source:'현재 {city}'}];
  const ui = createUI({messages,instruments:{weather:{name:'날씨',fields}}},{localStorage:{getItem:()=> 'en'}});
  const result = ui.instrument(raw);
  assert.equal(result.name,'Weather'); assert.equal(result.inputs[0].label,'City name');
  assert.equal(result.view[0].label,'Current {city}');
  assert.equal(result.action,raw.action); assert.equal(result.inputs[0].key,'도시');
  assert.equal(result.inputs[0].default,'서울'); assert.equal(raw.inputs[0].label,'도시 이름');
  assert.equal(ui.instrument({...raw,id:'custom'}).name,'날씨');
  assert.equal(ui.instrument({...raw,name:'내 날씨'}).name,'내 날씨');
  assert.equal(ui.instrument({...raw,inputs:[{label:'사용자가 고친 제목'}]}).inputs[0].label,'사용자가 고친 제목');
  ui.setLocale('ko'); assert.deepEqual(ui.instrument(raw),raw);
});

test('JSX-valued component slots translate nested labels and attributes without touching data props', () => {
  const {messages, code} = compile(`const App=()=> <Frame title="가이드 파일" actions={<button title="다시 읽기">새로고침</button>} data={{name:'사용자 이름'}} footer={()=><span>닫기</span>} />;`);
  const sources = Object.values(messages).map(m=>m.source);
  for (const value of ['가이드 파일','다시 읽기','새로고침','닫기']) assert.ok(sources.includes(value),value);
  assert.ok(!sources.includes('사용자 이름'));
  assert.ok(code.includes("name:'사용자 이름'"));
});

test('mixed dynamic display attributes translate only literal fallback branches', () => {
  const {messages, code} = compile(`const App=({user,root})=><input title={user.name || '새 항목'} aria-label={root ? '바탕' : user.name + ' contents'} />;`);
  assert.deepEqual(new Set(Object.values(messages).map(m=>m.source)),new Set(['새 항목','바탕']));
  assert.ok(code.includes('resolve:()=>'));
  assert.ok(code.includes('user.name || (__ui.text('));
  assert.ok(code.includes("user.name + ' contents'"));
});

test('reviewed empty translations survive refresh and render without Korean particles', async () => {
  const memory = {en:{particle:{source:'을',text:'',reviewed:true}}};
  const messages = {particle:{source:'을'}};
  const stats = await refresh(messages,memory,{ko:'한국어',en:'English'},()=>{throw Error('must reuse')});
  assert.equal(stats.reused,1);
  const ui = createUI({messages:{particle:{source:'을',translations:{en:''}}}},{localStorage:{getItem:()=> 'en'}});
  assert.equal(ui.text('particle'),'');
});

test('finite metadata is translated at display only, lexical user data and option ids stay raw', () => {
  const source = `const OPTIONS=[{id:'절약',label:'절약 모드'},{id:'최대',label:'최대 모드'}]; const SECRET='비밀';
  const App=({user})=><><select>{OPTIONS.map(o=><option value={o.id}>{o.label}</option>)}</select><p>{user.label}</p><input value={SECRET}/>{OPTIONS.map(({label})=><span title={label}>{label}</span>)}</>;
  const Other=({OPTIONS})=><p>{OPTIONS.label}</p>;`;
  const {messages, code} = compile(source);
  assert.deepEqual(new Set(Object.values(messages).map(m=>m.source)),new Set(['절약 모드','최대 모드']));
  assert.ok(code.includes('value={o.id}'));
  assert.ok(code.includes('{user.label}'));
  assert.ok(code.includes('{OPTIONS.label}'));
  assert.ok(code.includes('value={SECRET}'));
  assert.ok(code.includes('__UiChoice value={label}'));
});
test('dynamic titles, custom component labels and native dialogs have string translations', () => {
  const {messages,code}=compile(`const TITLES={a:'수정하기',b:'저장하기'}; const App=()=> <><button title={TITLES.a}>확인</button><Dialog title="알림" label="안내"/><button onClick={()=>alert('완료했습니다')}>완료</button></>`);
  assert.ok(Object.values(messages).some(m=>m.source==='수정하기'));
  assert.ok(Object.values(messages).some(m=>m.source==='안내'));
  assert.ok(code.includes('alert(__ui.text('));
  assert.ok(code.includes('as={Dialog}'));
  assert.equal(ts.createSourceFile('out.tsx',code,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX).parseDiagnostics.length,0);
});
test('system metadata requires an explicit sink, unknown custom names never use fragments', () => {
  const ui=createUI({messages:{gear:{context:'system:metadata',source:'절약',translations:{en:'Economy'}},desc:{context:'system:metadata',source:'실행 모델 우선',translations:{en:'Execution model first'}}}}, {localStorage:{getItem:()=> 'en'}});
  assert.equal(ui.system('절약'),'Economy');
  assert.equal(ui.system('실행 모델 우선 나의 이름'),'실행 모델 우선 나의 이름');
  assert.equal(ui.system('실행 모델 우선. 원문',true),'Execution model first. 원문');
  assert.equal(ui.system('새 사용자 이름'),'새 사용자 이름');
});
test('source code markers and concurrent human edits survive generation', async () => {
  assert.equal(validTranslation('본문 <turn_context>', 'Body <turn_context>'),true);
  assert.equal(validTranslation('본문 <turn_context>', 'Body <script>'),false);
  const memory={en:{a:{source:'저장',text:'Auto'}}};
  const observed=structuredClone(memory);
  memory.en.b={source:'새것',text:'New'};
  mergeMemoryEdits(memory,observed,{en:{a:{source:'저장',text:'Human edit',reviewed:true}}});
  assert.equal(memory.en.a.text,'Human edit');
  assert.equal(memory.en.b.text,'New');
  const current={en:{}};
  await refresh({a:{source:'저장'}},current,{en:'English'},async()=>{current.en.a={source:'저장',text:'Correction',reviewed:true};return ['Automatic'];});
  assert.equal(current.en.a.text,'Correction');
});
test('fragments, chained static lists, template attributes and dialog values stay safe', () => {
  const {code,messages}=compile('const rows=[{label:"안내"},{label:"설정"}]; const App=({name})=><>도움말 {rows.filter(r=>r.label).map(r=><span>{r.label}</span>)}<button title={`열기 ${name}`} onClick={()=>confirm(`삭제 ${name}?`)}>확인</button></>');
  for(const source of ['도움말 ','안내','설정','열기 {0}','삭제 {0}?']) assert.ok(Object.values(messages).some(m=>m.source===source),source);
  assert.ok(code.includes('values:[name]'));
  assert.ok(code.includes(',[name])'));
  assert.equal(ts.createSourceFile('out.tsx',code,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX).parseDiagnostics.length,0);
});
test('remote split attributes do not hide the following static label', () => {
  const c=collector();
  const js=compileRemoteJS(`h+='<button style="color:'+color+'">설정</button>'; h+='<b style="color:'+color+'">최초 숙고 '+esc(value)+'</b>';`,c);
  assert.ok(js.includes('data-ui-text'));
  assert.ok(Object.values(c.messages).some(m=>m.source==='설정'));
  assert.ok(Object.values(c.messages).some(m=>m.source==='최초 숙고 '));
  assert.ok(js.includes('esc(value)'));
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
