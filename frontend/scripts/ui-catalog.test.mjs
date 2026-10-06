import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { uiCatalogPlugin, compileRemote, root } from './ui-catalog.mjs';
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
