import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { uiCatalogPlugin, compileRemote, reloadUICatalog, root } from './ui-catalog.mjs';
import { collector } from './ui-compiler.mjs';

test('Windows paths use the same UI transform and exclude runtime and test files', () => {
  const plugin = uiCatalogPlugin();
  const file = `${root}/frontend/src/components/Example.tsx`;
  const source = 'const App = () => <button title="여러\n줄">저장</button>;';
  const expected = plugin.transform(source, file);
  assert.ok(expected.code.includes('__UiText'));
  assert.deepEqual(plugin.transform(source.replaceAll('\n', '\r\n'), file.replaceAll('/', '\\') + '?v=1'), expected);
  for (const suffix of ['i18n/runtime.tsx', 'Example.test.tsx', 'Example.spec.ts']) {
    assert.equal(plugin.transform(source, `${root}/frontend/src/${suffix}`.replaceAll('/', '\\')), null);
  }
  assert.equal(plugin.transform(source, `${root}/frontend/src-other/Example.tsx`), null);
});

test('all current React sources compile identically after CRLF checkout', () => {
  const plugin = uiCatalogPlugin();
  function walk(dir) {
    return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
      const file = path.join(dir, entry.name);
      return entry.isDirectory() ? walk(file) : [file];
    });
  }
  for (const file of walk(path.join(root, 'frontend/src')).filter(file => /\.[jt]sx?$/.test(file))) {
    const lf = fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
    assert.deepEqual(plugin.transform(lf.replaceAll('\n', '\r\n'), file.replaceAll('/', '\\')),
      plugin.transform(lf, file), file);
  }
});

test('remote multiline UI messages keep their IDs after CRLF checkout', () => {
  const html = '<html><body><button title="여러\n줄">저장</button><script>el.textContent = "닫기";</script></body></html>';
  const lf = collector(), crlf = collector();
  assert.equal(compileRemote(html.replaceAll('\n', '\r\n'), crlf), compileRemote(html, lf));
  assert.deepEqual(crlf.messages, lf.messages);
});


test('catalog reload invalidates every cached JSON module before reloading open windows', () => {
  const calls=[],modules=new Set([{id:'catalog'}, {id:'catalog?import'}]);
  reloadUICatalog({moduleGraph:{getModulesByFile(file){assert.equal(file,path.join(root,'frontend/i18n/catalog.json'));return modules;},
    getModuleById(id){assert.equal(id,'\0owner-display');return {id:'owner baseline'};},
    invalidateModule(module){calls.push(module.id);}},ws:{send(event){calls.push(event.type);}}});
  assert.deepEqual(calls,['catalog','catalog?import','owner baseline','full-reload']);
});

test('Vite build with missing shipped translations never calls a provider or writes memory', async t => {
  let requests = 0, writes = 0;
  const server = http.createServer((_req, res) => { requests++; res.writeHead(503); res.end(); });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const previous = process.env.INDIEBIZ_TRANSLATE_URL;
  process.env.INDIEBIZ_TRANSLATE_URL = `http://127.0.0.1:${server.address().port}`;
  t.after(() => {
    server.close();
    if (previous === undefined) delete process.env.INDIEBIZ_TRANSLATE_URL;
    else process.env.INDIEBIZ_TRANSLATE_URL = previous;
  });
  const read = fs.readFileSync;
  t.mock.method(fs, 'readFileSync', function(file, ...args) {
    if (String(file) === path.join(root, 'frontend/i18n/translations.json')) return '{}';
    return read.call(this, file, ...args);
  });
  t.mock.method(fs, 'writeFileSync', () => { writes++; throw Error('Build must not write incomplete bundles or memory'); });
  await assert.rejects(uiCatalogPlugin().buildStart(), error =>
    error.code === 'UI_TRANSLATION_INCOMPLETE' && /no translation was attempted/.test(error.message));
  assert.equal(requests, 0);
  assert.equal(writes, 0);
});
