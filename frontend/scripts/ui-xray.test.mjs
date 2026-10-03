import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { compileXray } from './ui-xray.mjs';
import { collector } from './ui-compiler.mjs';
import { createUI } from '../i18n/runtime.mjs';

function compile(source) {
  const catalog = collector();
  const html = compileXray(`<html><head></head><body><script>${source}</script></body></html>`, catalog);
  return { catalog, code: html.match(/<script>([\s\S]*?)<\/script>/)[1] };
}

test('templates translate source UI, preserve expressions, keys and comparisons', () => {
  const {catalog, code} = compile(`
    function escHtml(s){return String(s).replaceAll('<','&lt;').replaceAll('>','&gt;')}
    function render(data){const axes={'분류':'중급'}; const ok=axes['분류']==='중급';
      return \`<div title="조회">새로고침 \${data.name}<span>횟수</span>\${ok}</div>\`;}
    window.result=render(window.input);
  `.replaceAll('\${', '${'));
  const sources = Object.values(catalog.messages).map(m=>m.source);
  assert(!sources.includes('분류'));
  const translations = {'중급':'Mid-tier','새로고침 ':'Refresh ','조회':'Inspect','횟수':'Count'};
  // Data value is deliberately identical to a registered label.
  const host = {input:{name:'새로고침'}, __ui:{text:id=>translations[catalog.messages[id].source]}};
  vm.runInNewContext(code,{window:host});
  assert.equal(host.result,'<div title="Inspect">Refresh 새로고침<span>Count</span>true</div>');
});

test('translated HTML and attributes escape markup; code remains source', () => {
  const {catalog,code}=compile(`
    function escHtml(s){return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;')}
    function render(){return '<div title="조회">새로고침</div><pre>보존</pre>'}
    window.result=render();
  `);
  assert(!Object.values(catalog.messages).some(m=>m.source==='보존'));
  const host={__ui:{text:()=>'<img src=x onerror="bad()">'}};
  vm.runInNewContext(code,{window:host});
  assert(!host.result.includes('<img'));
  assert(host.result.includes('&quot;bad()&quot;'));
  assert(host.result.endsWith('<pre>보존</pre>'));
});

test('additional registered languages and absent translations use common runtime',()=>{
  const {catalog}=compile('function title(){return "새로고침"}');
  const [id]=Object.keys(catalog.messages);
  catalog.messages[id].translations={en:'Refresh',ja:'更新'};
  const ui=createUI({languages:{ko:'한국어',en:'English',ja:'日本語',fr:'Français'},messages:catalog.messages},{});
  ui.setLocale('ja'); assert.equal(ui.text(id),'更新');
  ui.setLocale('fr'); assert.equal(ui.text(id),'새로고침');
  ui.setLocale('ko'); assert.equal(ui.text(id),'새로고침');
});

test('native locale injection checks the destination before and after navigation',()=>{
  const source=fs.readFileSync(new URL('../src/lib/xray-locale.ts',import.meta.url),'utf8');
  const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
  const context={exports:{},URL}; vm.runInNewContext(code,context);
  const {isXrayURL,xrayLocaleURL,xrayLocaleScript}=context.exports;
  const origin='http://127.0.0.1:8765';
  assert.equal(xrayLocaleURL(origin+'/xray/app',origin,'en'),origin+'/xray/app?ui_locale=en');
  assert(!isXrayURL('https://example.com/xray/app',origin));
  assert.equal(xrayLocaleURL('https://example.com',origin,'en'),'https://example.com');
  const seen=[];
  const page={location:{origin,pathname:'/xray/app'},window:{__ui:{setLocale:l=>seen.push(l)}}};
  vm.runInNewContext(xrayLocaleScript(origin,'en'),page);
  page.location.origin='https://example.com';
  vm.runInNewContext(xrayLocaleScript(origin,'ko'),page);
  assert.deepEqual(seen,['en']);
});

test('native tab delivers current locale after readiness and unsubscribes on close',()=>{
  const origin='http://127.0.0.1:8765';
  const helper=fs.readFileSync(new URL('../src/lib/xray-locale.ts',import.meta.url),'utf8');
  const module={exports:{},URL};
  vm.runInNewContext(ts.transpileModule(helper,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,module);
  const source=fs.readFileSync(new URL('../src/components/forage/views.tsx',import.meta.url),'utf8');
  const ast=ts.createSourceFile('views.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  const fn=ast.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text==='NativeBrowserTab').getText(ast);
  const handlers=new Map(), scripts=[], effects=[];
  let url=origin+'/xray/app', refs=0;
  const el={getURL:()=>url, executeJavaScript:s=>{scripts.push(s);return Promise.resolve()},
    addEventListener:(name,fn)=>handlers.set(name,fn),removeEventListener:name=>handlers.delete(name)};
  const ui=createUI({languages:{ko:'Korean',en:'English'},messages:{}},{}); ui.setLocale('en');
  const context={...module.exports,ui,BACKEND_ORIGIN:origin,WebView:'webview',console,
    useRef:value=>({current:refs++===0?el:value}),useEffect:fn=>effects.push(fn),
    React:{createElement:(type,props)=>({type,props})}};
  vm.runInNewContext(ts.transpileModule(fn+'\nglobalThis.component=NativeBrowserTab;',
    {compilerOptions:{jsx:ts.JsxEmit.React}}).outputText,context);
  const result=context.component({tab:{id:'xray',initialUrl:url,url},onUpdate(){},registerRef(){},onOpenTab(){}});
  assert(result.props.src.endsWith('?ui_locale=en'));
  const cleanup=effects[0]();
  ui.setLocale('ko'); assert.equal(scripts.length,0);
  handlers.get('dom-ready')(); assert(scripts.at(-1).includes('"ko"'));
  ui.setLocale('en'); assert(scripts.at(-1).includes('"en"'));
  const count=scripts.length;
  handlers.get('did-start-loading')(); ui.setLocale('ko'); assert.equal(scripts.length,count);
  url='https://example.com/xray/app'; handlers.get('dom-ready')(); assert.equal(scripts.length,count);
  cleanup(); ui.setLocale('en'); assert.equal(scripts.length,count); assert.equal(handlers.size,0);
});

test('built standalone scripts retain dollar syntax without replacement expansion',()=>{
  for(const name of ['xray','remote']) {
    const {html}=JSON.parse(fs.readFileSync(new URL(`../i18n/${name}.json`,import.meta.url),'utf8'));
    const scripts=[...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)];
    assert(scripts.length>=2);
    for(const [,script] of scripts) new vm.Script(script);
  }
});
