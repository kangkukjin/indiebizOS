"""Desktop and remote app transports declare the edition and preserve bound inputs."""
import json
from pathlib import Path
import subprocess

import boot_paths  # noqa: F401
import pytest

from ibl_edition import source_edition


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('surface', ['desktop', 'remote', 'portal'])
def test_app_transport_declares_current_source_and_preserves_envelopes(surface):
    script = r'''
const fs = require('fs'), vm = require('vm');
const esbuild = require('./frontend/node_modules/esbuild');
const requests = [];
const sandbox = {
  console, location: {protocol:'file:', origin:''},
  document: {documentElement:{dataset:{}}, addEventListener(){}},
  localStorage: {getItem(){return null;}},
  fetch: async (url, options) => {
    requests.push({url, body:JSON.parse(options.body)});
    return {ok:true, json:async()=>({edition:2, success:true, value:{items:[]}})};
  },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
const surface = process.argv[1];
let run, actionRequest;
if (surface === 'desktop') {
  const bundle = esbuild.buildSync({
    entryPoints:['frontend/src/components/generic/manifest.ts'], bundle:true,
    write:false, platform:'browser', format:'iife', globalName:'app',
    define:{'import.meta.env':'{}'}, logLevel:'silent',
  });
  vm.runInContext(bundle.outputFiles[0].text, sandbox);
  run = sandbox.app.runIBL; actionRequest = sandbox.app.actionRequest;
} else {
  vm.runInContext(fs.readFileSync('backend/static/app_render_core.js','utf8')
    .split('/* --- ESM export')[0], sandbox);
  vm.runInContext(fs.readFileSync('frontend/surfaces/shared/launcher_common_js.js','utf8'), sandbox);
  if (surface === 'portal') sandbox.__PORTAL = {exec:'/portal/execute'};
  run = sandbox.ibl; actionRequest = sandbox.actionRequest;
}
(async()=>{
  await run('[others:feed]{op:"read",hashtag:"indienet",limit:50}');
  const refs = [{name:'example',revision:3}];
  const request = actionRequest({edition:2,function_refs:refs},
    '[self:business]{store:"business",op:"list",level:$level,search:$q}',
    {level:0,q:''});
  const before = JSON.stringify(request);
  await run(request);
  if (JSON.stringify(request) !== before) throw new Error('request mutated');
  await run('#!ibl edition=99\nreturn 1');
  process.stdout.write(JSON.stringify(requests));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    result = subprocess.run(['node', '-e', script, surface], cwd=ROOT,
                            capture_output=True, text=True, timeout=30, check=True)
    feed, business, unsupported = json.loads(result.stdout)
    for request in (feed, business):
        body = request['body']
        assert source_edition(body['code'], body.get('edition')) == 2
        assert request['url'].endswith('/portal/execute' if surface == 'portal' else '/ibl/execute')
    assert business['body']['inputs'] == {'level': 0}
    assert business['body']['declared_inputs'] == ['level', 'q']
    assert business['body']['function_refs'] == [{'name': 'example', 'revision': 3}]
    assert feed['body']['code'] == '[others:feed]{op:"read",hashtag:"indienet",limit:50}'
    with pytest.raises(ValueError, match='EDITION_UNSUPPORTED'):
        source_edition(unsupported['body']['code'], unsupported['body'].get('edition'))
