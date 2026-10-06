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
for (const file of files(path.join(root, 'frontend/src')).filter(f => /\.[jt]sx?$/.test(f) && !f.includes('/i18n/'))) {
  const compiled = compileReact(fs.readFileSync(file, 'utf8'), path.relative(root, file), catalog);
  const diagnostics = ts.createSourceFile(file, compiled, ts.ScriptTarget.Latest, true, /\.[jt]sx$/.test(file) ? ts.ScriptKind.TSX : ts.ScriptKind.TS).parseDiagnostics;
  assert.equal(diagnostics.length, 0, file + ': ' + diagnostics.map(d => d.messageText).join('\n'));
  count++;
}
const built = JSON.parse(fs.readFileSync(path.join(root, 'frontend/i18n/catalog.json'), 'utf8'));
for (const id of Object.keys(catalog.messages)) assert.ok(built.messages[id], `source message absent from built catalog: ${id}`);
const missing = Object.entries(built.messages).flatMap(([id, message]) =>
  Object.keys(built.languages).filter(language => language !== (built.sourceLocale || 'ko') && !Object.hasOwn(message.translations, language)).map(language => ({ id, language })));
assert.equal(missing.length,0,JSON.stringify(missing));
const bundle = JSON.parse(fs.readFileSync(path.join(root, 'frontend/i18n/remote.json'), 'utf8'));
if (bundle.html) {
  for (const match of bundle.html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)) new vm.Script(match[1]);
}
console.log(JSON.stringify({ parsedReactFiles: count, messages: Object.keys(built.messages).length, untranslatedRegisteredMessages: missing.length, remoteScriptSyntax: !!bundle.html }));
