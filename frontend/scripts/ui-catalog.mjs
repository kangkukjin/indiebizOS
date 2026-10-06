import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createHash } from 'node:crypto';
import { collector, compileReact, compileHTML, compileRemoteJS, korean } from './ui-compiler.mjs';
import { createUI, mountRemote } from '../i18n/runtime.mjs';
import { compileXray } from './ui-xray.mjs';
import { pythonCommand, pythonEnv } from './build-python.mjs';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const i18n = path.join(root, 'frontend/i18n');
const portablePath = file => file.replaceAll('\\', '/');
const sourceText = text => text.replace(/\r\n?/g, '\n');
function reactFile(file) {
  file = portablePath(file);
  const prefix = portablePath(root) + '/frontend/src/';
  if (!file.startsWith(prefix) || !/\.[jt]sx?$/.test(file) || file.includes('/i18n/') || /\.(test|spec)\./.test(file)) return null;
  return file.slice(portablePath(root).length + 1);
}
function readJSON(file, fallback = {}) { return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : fallback; }
function writeJSON(file, value) {
  const text = JSON.stringify(value) + '\n';
  if (fs.existsSync(file) && fs.readFileSync(file, 'utf8') === text) return;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = file + `.${process.pid}.${Date.now()}.tmp`; fs.writeFileSync(temp, text); fs.renameSync(temp, file);
}
function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? files(path.join(dir, e.name)) : [path.join(dir, e.name)]).sort();
}
const markup = text => (text.match(/<[^>]*>/g) || []).sort().join('|');
// Never translate executable examples, markup or template expressions inside UI prose.
const protectedPattern = () => /read_guide\([^()\n]*\)|\b(?:store|expand|category|node|source|query|op)\s*:\s*"[^"\n]*"|`[^`\n]+`|\[[a-z_]+:[^\]\n]+\](?:\{[^{}]*\})?|\{[^{}\n]+\}|<[^>\n]+>/g;
const codePattern = context => context === 'system:metadata' ? new RegExp('"[^"\\n]*"|' + protectedPattern().source, 'g') : protectedPattern();
function protectedParts(text, context) {
  const pattern = codePattern(context), parts = [];
  let match;
  while ((match = pattern.exec(text))) {
    let end = pattern.lastIndex;
    if (match[0].startsWith('[')) {
      const brace = text.indexOf(']', match.index) + 1;
      if (text[brace] === '{') {
        let depth = 0, quote = '', escaped = false;
        for (let i = brace; i < text.length; i++) {
          const c = text[i];
          if (quote) {
            if (escaped) escaped = false;
            else if (c === '\\') escaped = true;
            else if (c === quote) quote = '';
          } else if (c === '"' || c === "'") quote = c;
          else if (c === '{') depth++;
          else if (c === '}' && --depth === 0) { end = i + 1; break; }
        }
      }
    }
    parts.push({start:match.index,end,value:text.slice(match.index,end)});
    pattern.lastIndex = end;
  }
  return parts;
}
const signature = (text, context) => protectedParts(text, context).map(p=>p.value).sort().join('|');
export function maskSource(source, context = '') {
  const tokens = [];
  let masked = '', cursor = 0;
  for (const part of protectedParts(source, context)) {
    masked += source.slice(cursor, part.start) + `⟦KEEP${tokens.length}⟧`;
    tokens.push(part.value); cursor = part.end;
  }
  masked += source.slice(cursor);
  return { masked, restore(value) {
    const expected = tokens.map((_, i) => `⟦KEEP${i}⟧`).sort().join('|');
    if (typeof value !== 'string' || (value.match(/⟦KEEP\d+⟧/g) || []).sort().join('|') !== expected) return null;
    return value.replace(/⟦KEEP(\d+)⟧/g, (_, i) => tokens[Number(i)]);
  } };
}
export function validTranslation(source, text, reviewed = false, context = '') {
  return typeof text === 'string' && (reviewed || !!text.trim()) && signature(source, context) === signature(text, context) && markup(source) === markup(text) && !korean(maskSource(text, context).masked);
}
export async function translateBatch(texts, target, contexts = []) {
  const protectedTexts = texts.map((source, i) => maskSource(source, contexts[i]));
  const result = await translateProvider(protectedTexts.map(item => item.masked), target, contexts);
  return result.map((value, i) => protectedTexts[i].restore(value));
}
async function translateProvider(texts, target, contexts = []) {
  if (!process.env.INDIEBIZ_TRANSLATE_URL) {
    const [python, ...prefix] = pythonCommand();
    const child = promisify(execFile)(python, [...prefix, path.join(root, 'frontend/scripts/ui-translate.py')], {cwd:root, env:pythonEnv(), timeout:120000,maxBuffer:2*1024*1024});
    child.child.stdin.end(JSON.stringify({texts,target,contexts}));
    const {stdout} = await child;
    const result = JSON.parse(stdout);
    if (!Array.isArray(result) || result.length !== texts.length) throw new Error('model translation count mismatch');
    return result;
  }
  const endpoint = process.env.INDIEBIZ_TRANSLATE_URL || 'http://127.0.0.1:8765/forage/translate';
  const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texts, target }), signal: AbortSignal.timeout(45000) });
  if (!response.ok) throw new Error(`translation HTTP ${response.status}`);
  const data = await response.json();
  if (!Array.isArray(data.translations) || data.translations.length !== texts.length) throw new Error('translation count mismatch');
  return data.translations;
}
export function mergeMemoryEdits(memory, observed, disk) {
  // A correction made while the provider was running wins over this build's snapshot.
  for (const language of new Set([...Object.keys(observed), ...Object.keys(disk)])) {
    memory[language] ||= {};
    for (const id of new Set([...Object.keys(observed[language] || {}), ...Object.keys(disk[language] || {})])) {
      if (JSON.stringify(observed[language]?.[id]) === JSON.stringify(disk[language]?.[id])) continue;
      if (disk[language]?.[id] === undefined) delete memory[language][id];
      else memory[language][id] = disk[language][id];
    }
  }
  return memory;
}
export async function refresh(messages, memory, languages, translate = translateBatch, checkpoint = () => {}) {
  const stats = { requested: 0, translated: 0, reused: 0, failed: 0 };
  for (const language of Object.keys(languages).filter(l => l !== 'ko')) {
    memory[language] ||= {};
    const pending = [];
    for (const [id, entry] of Object.entries(messages)) {
      const previous = memory[language][id];
      if (previous?.source === entry.source && validTranslation(entry.source, previous.text, previous.reviewed === true, entry.context)) { stats.reused++; continue; }
      pending.push([id, entry]);
    }
    // Bound provider traffic; static source UI only. Failures are not cached as successful translations.
    let cursor = 0, providerFailed = false;
    await Promise.all(Array.from({ length: 3 }, async () => {
      while (cursor < pending.length && !providerFailed) {
        const batch = pending.slice(cursor, cursor += 20);
        stats.requested += batch.length;
        try {
          const result = await translate(batch.map(([, e]) => e.source), language, batch.map(([, e]) => e.context));
          for (let i = 0; i < batch.length; i++) {
            const [id, entry] = batch[i];
            const current = memory[language][id];
            if (current?.source === entry.source && validTranslation(entry.source, current.text, current.reviewed === true, entry.context)) { stats.reused++; continue; }
            if (validTranslation(entry.source, result[i], false, entry.context)) {
              memory[language][id] = { source: entry.source, text: result[i] }; stats.translated++;
            } else stats.failed++;
          }
        } catch (error) {
          providerFailed = true;
          stats.failed += batch.length;
          // 공급자 장애는 최대 3개 진행 중 요청까지만 회수한다. 미번역 전체를 재호출하지 않는다.
          console.warn(`[ui-i18n] ${language}: translation provider failed (${error.code || error.name}); remaining batches stopped`);
        }
        checkpoint(memory);
        console.log('[ui-i18n progress]', JSON.stringify(stats));
      }
    }));
    stats.failed += Math.max(0, pending.length - cursor);
  }
  return stats;
}
function rawRemote() {
  const [python, ...prefix] = pythonCommand();
  return execFileSync(python, [...prefix, '-c', 'import sys; sys.path.insert(0,"backend"); import boot_paths; from launcher_web_shell import LAUNCHER_SHELL_HTML; from launcher_web_app import LAUNCHER_APP_JS; from launcher_web_render import LAUNCHER_RENDER_JS; sys.stdout.write(LAUNCHER_SHELL_HTML+LAUNCHER_APP_JS+LAUNCHER_RENDER_JS)'], { cwd: root, env: pythonEnv(), encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 });
}
export function compileRemote(html, catalog) {
  html = sourceText(html);
  const scripts = [];
  let body = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, block => {
    const start = block.indexOf('>') + 1;
    scripts.push(block.slice(0, start) + compileRemoteJS(block.slice(start, -9), catalog) + '</script>');
    return `<!--UI_SCRIPT_${scripts.length - 1}-->`;
  });
  body = compileHTML(body, 'remote:shell', catalog);
  return body.replace(/<!--UI_SCRIPT_(\d+)-->/g, (_, index) => scripts[Number(index)]);
}
export function registerBoundaryMessages(catalog, memory, native, system) {
  memory.en ||= {};
  for (const [source, english] of Object.entries(native)) {
    const id = catalog.add('native:ui', source);
    memory.en[id] ||= { source, text: english };
  }
  for (const [id, entry] of Object.entries(system)) {
    catalog.messages[id] = { source: entry.source, context: entry.context, plural: !!entry.plurals };
    memory.en[id] ||= { source: entry.source, text: entry.en, forms: entry.plurals?.en };
  }
}
export async function buildCatalog({ translate = translateBatch } = {}) {
  const catalog = collector();
  for (const file of files(path.join(root, 'frontend/src'))) {
    const relative = reactFile(file);
    if (!relative) continue;
    compileReact(sourceText(fs.readFileSync(file, 'utf8')), relative, catalog);
  }
  const [python, ...prefix] = pythonCommand();
  const systemSources = JSON.parse(execFileSync(python, [...prefix, path.join(root, 'frontend/scripts/ui-system-sources.py')], {env:pythonEnv(), encoding:'utf8'}));
  for (const source of systemSources.messages) catalog.add('system:metadata', source);
  for (const source of systemSources.status_messages) catalog.add('system:status', source);
  const raw = sourceText(rawRemote());
  const remote = compileRemote(raw, catalog);
  const xrayRaw = sourceText(fs.readFileSync(path.join(root, 'data/xray/index.html'), 'utf8'));
  const xray = compileXray(xrayRaw, catalog);
  const languages = readJSON(path.join(i18n, 'languages.json'));
  if (languages.ko !== '한국어' || !languages.en) throw new Error('UI language registry requires ko and en');
  for (const language of Object.keys(languages)) Intl.getCanonicalLocales(language);
  const memory = readJSON(path.join(i18n, 'translations.json'));
  let observed = structuredClone(memory);
  registerBoundaryMessages(catalog, memory, readJSON(path.join(i18n, 'native-messages.json')), readJSON(path.join(i18n, 'system-messages.json')));
  const saveMemory = () => {
    mergeMemoryEdits(memory, observed, readJSON(path.join(i18n, 'translations.json')));
    writeJSON(path.join(i18n, 'translations.json'), memory);
    observed = structuredClone(memory);
  };
  const stats = await refresh(catalog.messages, memory, languages, translate, saveMemory);
  saveMemory();
  requireCompleteTranslations(stats);
  for (const [id, entry] of Object.entries(catalog.messages)) {
    entry.translations = {};
    for (const lang of Object.keys(languages)) {
      const item = memory[lang]?.[id];
      // 복수 범주가 other 하나뿐인 언어(일본어·중국어 등)는 번역문 자체가 유일한 형태다 — 그 밖의 언어만 forms 를 요구한다.
      const categories = lang === 'ko' ? [] : new Intl.PluralRules(lang).resolvedOptions().pluralCategories;
      if (entry.plural && item && !item.forms && categories.length === 1) item.forms = { other: item.text };
      if (entry.plural && lang !== 'ko' && !item?.forms) throw new Error(`Missing plural forms: ${lang}/${id}`);
      if (item?.source === entry.source && validTranslation(entry.source, item.text, item.reviewed === true, entry.context)) {
        entry.translations[lang] = item.text;
        if (item.forms) {
          if (!item.forms.other || categories.some(category => !Object.hasOwn(item.forms, category)) ||
              Object.values(item.forms).some(form => !validTranslation(entry.source, form, false, entry.context))) {
            throw new Error(`Invalid plural forms: ${lang}/${id}`);
          }
          (entry.plurals ||= {})[lang] = item.forms;
        }
      }
    }
  }
  const bundle = { sourceLocale: 'ko', languages, messages: catalog.messages, instruments: systemSources.instruments };
  writeJSON(path.join(i18n, 'catalog.json'), bundle);
  // Only remote messages are embedded in the remote shell. Escape the script boundary independently of HTML.
  const remoteBundle = { languages, instruments: bundle.instruments, messages: Object.fromEntries(Object.entries(bundle.messages).filter(([, m]) => m.context.startsWith('remote:') || m.context === 'system:metadata' || m.context === 'system:message')) };
  const encoded = JSON.stringify(remoteBundle).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
  const bootstrap = `<script>window.__ui=(${createUI.toString()})(${encoded},window);\nwindow.__uiContent=function(value){if(value&&typeof value==='object'&&value.ui){const span=document.createElement('span');span.dataset.uiText=value.ui;span.textContent=window.__ui.text(value.ui);return span.outerHTML;}const span=document.createElement('span');span.textContent=String(value==null?'':value);return span.innerHTML;};window.__uiSetText=function(el,id){const span=document.createElement('span');span.setAttribute('data-ui-text',id);span.textContent=window.__ui.text(id);el.replaceChildren(span);};\ndocument.addEventListener('DOMContentLoaded',function(){(${mountRemote.toString()})(window.__ui,document);});</script>`;
  const html = remote.replace('</head>', () => bootstrap + '</head>');
  writeJSON(path.join(i18n, 'remote.json'), { source_hash: createHash('sha256').update(raw).digest('hex'), html });
  const xrayBundle = { languages, messages: Object.fromEntries(Object.entries(bundle.messages).filter(([, m]) => m.context.startsWith('xray:') || m.context.startsWith('system:'))) };
  const xrayEncoded = JSON.stringify(xrayBundle).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
  const xrayBootstrap = `<script>window.__ui=(${createUI.toString()})(${xrayEncoded},window);
const requestedLocale=new URL(location.href).searchParams.get('ui_locale');
if(requestedLocale){window.__ui.setLocale(requestedLocale);const url=new URL(location.href);url.searchParams.delete('ui_locale');history.replaceState(null,'',url);}
window.addEventListener('message',event=>{if(event.source===parent && parent!==window && event.data?.type==='indiebiz:ui-locale' && document.referrer && event.origin===new URL(document.referrer).origin)window.__ui.setLocale(event.data.locale);});
document.addEventListener('DOMContentLoaded',()=>(${mountRemote.toString()})(window.__ui,document));</script>`;
  writeJSON(path.join(i18n, 'xray.json'), { source_hash: createHash('sha256').update(xrayRaw).digest('hex'), html: xray.replace('</head>', () => xrayBootstrap + '</head>') });
  console.log('[ui-i18n]', JSON.stringify({ messages: Object.keys(bundle.messages).length, ...stats }));
  return { ...stats, count: Object.keys(bundle.messages).length };
}
export function uiCatalogPlugin() {
  let running, dirty = false;
  const build = () => {
    dirty = true;
    return running ||= (async () => { while (dirty) { dirty = false; await buildCatalog(); } })().finally(() => { running = undefined; });
  };
  return {
    name: 'indiebiz-ui-catalog', enforce: 'pre',
    async buildStart() { await build(); },
    transform(source, id) {
      const file = reactFile(id.split('?')[0]);
      if (!file) return null;
      return { code: compileReact(sourceText(source), file, collector()), map: null };
    },
    configureServer(server) {
      server.watcher.add([path.join(root, 'data/xray/index.html'), path.join(root, 'data/ibl_nodes.yaml'), path.join(root, 'data/instruments'), path.join(root, 'backend/services/model_settings_view.py'), path.join(root, 'backend/base/model_resolver.py'), path.join(root, 'backend/cognition/world_pulse_health.py'), path.join(root, 'backend/cognition/ibl_description_audit.py'), ...files(path.join(root, 'backend/surface')).filter(file => /launcher_[^/]+\.py$/.test(file)), path.join(i18n, 'languages.json'), path.join(i18n, 'native-messages.json'), path.join(i18n, 'system-messages.json'), path.join(i18n, 'translations.json')]);
      let timer;
      const queue = file => {
        file = portablePath(file);
        if (!(file.includes('/frontend/src/') || file.endsWith('/data/xray/index.html') || file.endsWith('/ibl_nodes.yaml') || file.includes('/data/instruments/') || /launcher_[^/]+\.py$/.test(file) || file.endsWith('/languages.json') || file.endsWith('/native-messages.json') || file.endsWith('/system-messages.json') || file.endsWith('/model_settings_view.py') || file.endsWith('/model_resolver.py') || file.endsWith('/world_pulse_health.py') || file.endsWith('/ibl_description_audit.py') || (file.endsWith('/translations.json') && !running))) return;
        clearTimeout(timer); timer = setTimeout(async () => {
          try { await build(); server.ws.send({ type: 'full-reload' }); }
          catch (error) { server.config.logger.error(error.message); }
        }, 250);
      };
      server.watcher.on('change', queue); server.watcher.on('add', queue); server.watcher.on('unlink', queue);
      server.httpServer?.once('close', () => clearTimeout(timer));
    },
  };
}
export function requireCompleteTranslations(stats) {
  if (!stats.failed) return;
  const error = new Error(`[ui-i18n] build failed: ${stats.failed} untranslated messages; last successful bundles preserved. Check translation provider access and retry.`);
  error.code = 'UI_TRANSLATION_INCOMPLETE'; error.stats = stats;
  throw error;
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { await buildCatalog(); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
