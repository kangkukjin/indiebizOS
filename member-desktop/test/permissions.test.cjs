const test=require('node:test'),assert=require('node:assert/strict');
const {createPermissions}=require('../permissions.cjs');
function fixture(){
 const calls=[],state={screen:'denied',accessibility:false};
 const electron={systemPreferences:{getMediaAccessStatus:()=>state.screen,isTrustedAccessibilityClient:prompt=>{if(prompt)calls.push('accessibility-request');return state.accessibility}},desktopCapturer:{getSources:async options=>{calls.push(options);return [{thumbnail:'private probe'}]}},shell:{openExternal:async url=>calls.push(url)}};
 return {calls,state,electron,p:createPermissions(electron,'darwin')};
}
test('status reads do not prompt or capture; unsupported systems do not call macOS APIs',async()=>{
 const f=fixture();assert.equal((await f.p.request()).screen,'denied');assert.deepEqual(f.calls,[]);
 assert.equal((await createPermissions({},'win32').request('screen')).screen,'system-managed');
 await assert.rejects(f.p.request('arbitrary-url'),/지원하지/);assert.deepEqual(f.calls,[]);
});
test('screen request registers this app, opens denied permission settings and never returns images',async()=>{
 const f=fixture(),r=await f.p.request('screen');assert.equal(r.screen,'denied');assert.equal(r.thumbnail,undefined);
 assert.deepEqual(f.calls,[{types:['screen'],thumbnailSize:{width:1,height:1}},'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture']);
 f.state.screen='granted';f.calls.length=0;await f.p.request('screen');assert.deepEqual(f.calls,[]);
});
test('a failed screen probe still gives the user the OS settings path',async()=>{
 const f=fixture();f.electron.desktopCapturer.getSources=async()=>{throw Error('capture denied')};
 const r=await f.p.request('screen');assert.equal(r.screen,'denied');assert.equal(r.error,'capture denied');assert.match(f.calls[0],/Privacy_ScreenCapture$/);
});
test('accessibility is requested separately and rechecked after the user changes it',async()=>{
 const f=fixture();await f.p.request('accessibility');assert.deepEqual(f.calls,['accessibility-request','x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility']);
 f.state.accessibility=true;f.calls.length=0;assert.equal((await f.p.request()).accessibility,true);await f.p.request('accessibility');assert.deepEqual(f.calls,[]);
});
