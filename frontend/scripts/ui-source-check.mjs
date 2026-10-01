import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { root } from './ui-catalog.mjs';
import { collector, compileReact } from './ui-compiler.mjs';
const files = dir => fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? files(path.join(dir, e.name)) : [path.join(dir, e.name)]);
const catalog = collector();
let count = 0;
for (const file of files(path.join(root, 'frontend/src')).filter(f => f.endsWith('.tsx') && !f.includes('/i18n/'))) {
  const compiled = compileReact(fs.readFileSync(file, 'utf8'), path.relative(root, file), catalog);
  const diagnostics = ts.createSourceFile(file, compiled, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX).parseDiagnostics;
  assert.equal(diagnostics.length, 0, file + ': ' + diagnostics.map(d => d.messageText).join('\n'));
  count++;
}
const bundle = JSON.parse(fs.readFileSync(path.join(root, 'frontend/i18n/remote.json'), 'utf8'));
if (bundle.html) {
  for (const match of bundle.html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) new vm.Script(match[1]);
}
console.log(JSON.stringify({ parsedReactFiles: count, messages: Object.keys(catalog.messages).length, remoteScriptSyntax: !!bundle.html }));
