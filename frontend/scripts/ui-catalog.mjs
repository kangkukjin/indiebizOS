import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createHash } from 'node:crypto';
import { collector, compileReact, compileHTML, compileRemoteJS, korean } from './ui-compiler.mjs';
import { createUI, mountRemote } from '../i18n/runtime.mjs';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const i18n = path.join(root, 'frontend/i18n');
function readJSON(file, fallback = {}) { return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : fallback; }
function writeJSON(file, value) {
  const text = JSON.stringify(value) + '\n';
  if (fs.existsSync(file) && fs.readFileSync(file, 'utf8') === text) return;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = file + '.tmp'; fs.writeFileSync(temp, text); fs.renameSync(temp, file);
}
function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? files(path.join(dir, e.name)) : [path.join(dir, e.name)]).sort();
}
const signature = text => [...text.matchAll(/\{\d+\}/g)].map(m => m[0]).sort().join('|');
export function validTranslation(source, text, reviewed = false) {
  return typeof text === 'string' && (reviewed || !!text.trim()) && signature(source) === signature(text) && !/[<>]/.test(text) && (!korean(source) || !korean(text));
}
export async function translateBatch(texts, target, contexts = []) {
  if (!process.env.INDIEBIZ_TRANSLATE_URL) {
    const python = process.env.INDIEBIZ_PYTHON || (fs.existsSync(path.join(root, '.venv/bin/python3')) ? path.join(root, '.venv/bin/python3') : 'python3');
    const child = promisify(execFile)(python, [path.join(root, 'frontend/scripts/ui-translate.py')], {cwd:root, timeout:120000,maxBuffer:2*1024*1024});
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
export async function refresh(messages, memory, languages, translate = translateBatch, checkpoint = () => {}) {
  const stats = { requested: 0, translated: 0, reused: 0, failed: 0 };
  for (const language of Object.keys(languages).filter(l => l !== 'ko')) {
    memory[language] ||= {};
    const pending = [];
    for (const [id, entry] of Object.entries(messages)) {
      const previous = memory[language][id];
      if (previous?.source === entry.source && validTranslation(entry.source, previous.text, previous.reviewed === true)) { stats.reused++; continue; }
      pending.push([id, entry]);
    }
    // Bound provider traffic; static source UI only. Failures are not cached as successful translations.
    let cursor = 0;
    await Promise.all(Array.from({ length: 3 }, async () => {
      while (cursor < pending.length) {
        const batch = pending.slice(cursor, cursor += 20);
        stats.requested += batch.length;
        try {
          const result = await translate(batch.map(([, e]) => e.source), language, batch.map(([, e]) => e.context));
          for (let i = 0; i < batch.length; i++) {
            const [id, entry] = batch[i];
            if (validTranslation(entry.source, result[i])) {
              memory[language][id] = { source: entry.source, text: result[i] }; stats.translated++;
            } else stats.failed++;
          }
        } catch (error) { stats.failed += batch.length; console.warn(`[ui-i18n] ${language}: translation batch failed (${error.code || error.name})`); }
        checkpoint(memory);
        console.log('[ui-i18n progress]', JSON.stringify(stats));
      }
    }));
  }
  return stats;
}
function rawRemote() {
  const python = process.env.INDIEBIZ_PYTHON || (fs.existsSync(path.join(root, '.venv/bin/python3')) ? path.join(root, '.venv/bin/python3') : 'python3');
  return execFileSync(python, ['-c', 'import sys; sys.path.insert(0,"backend"); import boot_paths; from launcher_web_shell import LAUNCHER_SHELL_HTML; from launcher_web_app import LAUNCHER_APP_JS; from launcher_web_render import LAUNCHER_RENDER_JS; sys.stdout.write(LAUNCHER_SHELL_HTML+LAUNCHER_APP_JS+LAUNCHER_RENDER_JS)'], { cwd: root, encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 });
}
export function compileRemote(html, catalog) {
  const scripts = [];
  let body = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, block => {
    const start = block.indexOf('>') + 1;
    scripts.push(block.slice(0, start) + compileRemoteJS(block.slice(start, -9), catalog) + '</script>');
    return `<!--UI_SCRIPT_${scripts.length - 1}-->`;
  });
  body = compileHTML(body, 'remote:shell', catalog);
  return body.replace(/<!--UI_SCRIPT_(\d+)-->/g, (_, index) => scripts[Number(index)]);
}
export async function buildCatalog({ translate = translateBatch } = {}) {
  const catalog = collector();
  for (const file of files(path.join(root, 'frontend/src'))) {
    if (!/\.[jt]sx$/.test(file) || /\/i18n\//.test(file) || /\.(test|spec)\./.test(file)) continue;
    compileReact(fs.readFileSync(file, 'utf8'), path.relative(root, file).replaceAll(path.sep, '/'), catalog);
  }
  const raw = rawRemote();
  const remote = compileRemote(raw, catalog);
  const languages = readJSON(path.join(i18n, 'languages.json'));
  if (languages.ko !== '한국어' || !languages.en) throw new Error('UI language registry requires ko and en');
  const memory = readJSON(path.join(i18n, 'translations.json'));
  const stats = await refresh(catalog.messages, memory, languages, translate, value => writeJSON(path.join(i18n, 'translations.json'), value));
  for (const [id, entry] of Object.entries(catalog.messages)) {
    entry.translations = {};
    for (const lang of Object.keys(languages)) {
      const item = memory[lang]?.[id];
      if (item?.source === entry.source && validTranslation(entry.source, item.text, item.reviewed === true)) entry.translations[lang] = item.text;
    }
  }
  const bundle = { languages, messages: catalog.messages };
  writeJSON(path.join(i18n, 'translations.json'), memory);
  writeJSON(path.join(i18n, 'catalog.json'), bundle);
  // Only remote messages are embedded in the remote shell. Escape the script boundary independently of HTML.
  const remoteBundle = { languages, messages: Object.fromEntries(Object.entries(bundle.messages).filter(([, m]) => m.context.startsWith('remote:'))) };
  const encoded = JSON.stringify(remoteBundle).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
  const bootstrap = `<script>window.__ui=(${createUI.toString()})(${encoded},window);\nwindow.__uiContent=function(value){if(value&&typeof value==='object'&&value.ui){const span=document.createElement('span');span.dataset.uiText=value.ui;span.textContent=window.__ui.text(value.ui);return span.outerHTML;}const span=document.createElement('span');span.textContent=String(value==null?'':value);return span.innerHTML;};window.__uiSetText=function(el,id){const span=document.createElement('span');span.setAttribute('data-ui-text',id);span.textContent=window.__ui.text(id);el.replaceChildren(span);};\ndocument.addEventListener('DOMContentLoaded',function(){(${mountRemote.toString()})(window.__ui,document);});</script>`;
  const html = remote.replace('</head>', bootstrap + '</head>');
  writeJSON(path.join(i18n, 'remote.json'), { source_hash: createHash('sha256').update(raw).digest('hex'), html });
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
      const file = id.split('?')[0];
      if (!file.startsWith(path.join(root, 'frontend/src/')) || !/\.[jt]sx$/.test(file) || file.includes('/i18n/')) return null;
      return { code: compileReact(source, path.relative(root, file).replaceAll(path.sep, '/'), collector()), map: null };
    },
    configureServer(server) {
      server.watcher.add([...files(path.join(root, 'backend/surface')).filter(file => /launcher_[^/]+\.py$/.test(file)), path.join(i18n, 'languages.json'), path.join(i18n, 'translations.json')]);
      let timer;
      const queue = file => {
        if (!(file.includes('/frontend/src/') || /launcher_[^/]+\.py$/.test(file) || file.endsWith('/languages.json') || (file.endsWith('/translations.json') && !running))) return;
        clearTimeout(timer); timer = setTimeout(async () => { await build(); server.ws.send({ type: 'full-reload' }); }, 250);
      };
      server.watcher.on('change', queue); server.watcher.on('add', queue); server.watcher.on('unlink', queue);
      server.httpServer?.once('close', () => clearTimeout(timer));
    },
  };
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await buildCatalog();
