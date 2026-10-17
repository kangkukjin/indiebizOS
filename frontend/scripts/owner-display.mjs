/** Production display compiler: no React copy, hooks, bridge or transport is shipped. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { transform } from 'esbuild';
import { compile } from '@tailwindcss/node';
import { Scanner } from '@tailwindcss/oxide';
import { compileReact, collector } from './ui-compiler.mjs';
export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const views = ['src/components/chat/ChatDisplayView.tsx','src/components/LauncherDisplayView.tsx'];
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const digest = value => createHash('sha256').update(value).digest('hex');
function files(dir) { return fs.readdirSync(path.join(root,dir),{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(dir+'/'+e.name):[dir+'/'+e.name]); }
export function ownerInputs() {
  return [...files('src').filter(f=>/\.(tsx?|css|json)$/.test(f)), 'package-lock.json', 'scripts/owner-display.mjs', 'scripts/ui-compiler.mjs','scripts/ui-static-values.mjs','i18n/runtime.mjs','electron/preload.js','surfaces/shared/navigation.json','surfaces/shared/conversation.json','surfaces/shared/conversation.js'].sort();
}
export function ownerHost() {
  const contract = ownerInputs().filter(f=>!views.includes(f)&&!f.endsWith('.css')&&!['surfaces/shared/conversation.js','surfaces/shared/conversation.json','surfaces/shared/navigation.json'].includes(f));
  const routes=Object.entries(JSON.parse(read('surfaces/shared/navigation.json'))).map(([id,{route,routeFlag}])=>({id,route,routeFlag}));
  return digest(JSON.stringify([contract.map(f=>[f,digest(read(f))]),routes]));
}
export async function buildOwner() {
  const catalog=collector();let code='';
  for(const file of views){
    let source=compileReact(read(file),'frontend/'+file,catalog);
    source=source.replace(/^import .*;\s*$/gm,'').replace(/^__registerUiSources\(.*\);$/gm,'').replace(/export function /g,'function ');
    source=source.replace(/(function render\w+\(bindings:[^{]+\{)/, '$1\nconst {UiText:__UiText,UiChoice:__UiChoice,UiElement:__UiElement,ui:__ui}=bindings.__uiTools;\nconst React=bindings.React;');
    if(file.includes('LauncherDisplay'))source=source.replace('const React=bindings.React;','const React=bindings.React;\nbindings={...bindings,toolNavigation:'+read('surfaces/shared/navigation.json')+'};');
    code+=(await transform(source,{loader:'tsx',jsxFactory:'React.createElement',jsxFragment:'React.Fragment',target:'es2020'})).code;
  }
  const shared=read('surfaces/shared/conversation.js').split('/* --- ESM export')[0].replace(/^import .*;\s*$/m,'var conversationHeader='+read('surfaces/shared/conversation.json')+';');
  code='(function(){'+shared+'\n'+code+'\nwindow.__indieOwnerCandidate={chat:renderChatDisplay,launcher:renderLauncherDisplay};})();';
  const compiler=await compile(read('src/index.css'),{base:path.join(root,'src'),onDependency(){}});
  const scanner=new Scanner({sources:[{base:path.join(root,'src'),pattern:'**/*.{tsx,ts}',negated:false}]});
  const css=compiler.build(scanner.scan());
  const messages=JSON.parse(read('i18n/catalog.json')).messages;
  const translations=Object.fromEntries(Object.entries(messages).filter(([,m])=>['conversation','navigation'].includes(m.context)));for(const [id,m] of Object.entries(catalog.messages))translations[id]=messages[id]||m;
  const result={format:'indiebiz-owner-display-1',state:1,surface:'owner',host:ownerHost(),code,css,messages:translations};
  return {...result,version:digest(JSON.stringify(result))};
}
export function ownerDisplayPlugin(){
  return {
    name:'owner-display-contract',
    resolveId(id){if(id==='virtual:owner-display')return '\0owner-display';},
    configureServer(server){
      const inputs=new Set([...ownerInputs(),'i18n/catalog.json'].map(file=>path.join(root,file)));
      server.watcher.add([...inputs]);
      const invalidate=file=>{
        file=path.normalize(file);
        if(!inputs.has(file)&&!file.startsWith(path.join(root,'src')+path.sep))return;
        const baseline=server.moduleGraph.getModuleById('\0owner-display');
        if(baseline)server.moduleGraph.invalidateModule(baseline);
      };
      for(const event of ['change','add','unlink'])server.watcher.on(event,invalidate);
      server.httpServer?.once('close',()=>{
        for(const event of ['change','add','unlink'])server.watcher.off(event,invalidate);
      });
    },
    async load(id){
      if(id!=='\0owner-display')return;
      const value=await buildOwner();
      return 'export default '+JSON.stringify({host:value.host,version:value.version})+';';
    },
  };
}
if(process.argv[1]===fileURLToPath(import.meta.url))process.stdout.write(JSON.stringify(process.argv.includes('--inputs')?ownerInputs().map(f=>'frontend/'+f):await buildOwner()));
