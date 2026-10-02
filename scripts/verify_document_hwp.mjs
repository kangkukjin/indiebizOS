// Read actual saved bytes with the pinned WASM parser (no browser state).
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../backend/static/rhwp');
const { default: init, HwpDocument } = await import(pathToFileURL(path.join(root, 'core/rhwp.mjs')));
const wasm = fs.readdirSync(path.join(root, 'assets')).find(name => /^rhwp_bg-.*\.wasm$/.test(name));
await init({ module_or_path: fs.readFileSync(path.join(root, 'assets', wasm)) });
const doc = new HwpDocument(fs.readFileSync(process.argv[2]));
console.log(JSON.stringify({ text: JSON.parse(doc.getTextFileText()), info: JSON.parse(doc.getDocumentInfo()), pages: doc.pageCount() }));
doc.free();
