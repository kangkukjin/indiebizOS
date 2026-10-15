const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {MemberSession}=require('../session.cjs');const {installation}=require('../security.cjs');
const encryptionKey=crypto.randomBytes(32);
const safeStorage={isEncryptionAvailable:()=>true,encryptString(value){const iv=crypto.randomBytes(12),cipher=crypto.createCipheriv('aes-256-gcm',encryptionKey,iv);const b=Buffer.concat([cipher.update(value),cipher.final()]);return Buffer.concat([iv,cipher.getAuthTag(),b]);},decryptString(data){const decipher=crypto.createDecipheriv('aes-256-gcm',encryptionKey,data.subarray(0,12));decipher.setAuthTag(data.subarray(12,28));return Buffer.concat([decipher.update(data.subarray(28)),decipher.final()]).toString();}};
test('credential persistence stays encrypted and public state excludes secrets',()=>{const root=fs.mkdtempSync(path.join(os.tmpdir(),'member-session-'));try{const session=new MemberSession({root,safeStorage,executable:'unused'});const config={key:'synthetic-secret',private_key:'synthetic-private',base:'https://hub.test'};session.save(config);assert.deepEqual(session.read(),config);assert(!fs.readFileSync(session.file()).includes(Buffer.from('synthetic-secret')));session.config=config;assert(!JSON.stringify(session.publicState()).includes('synthetic'));}finally{fs.rmSync(root,{recursive:true,force:true});}});
test('plaintext keyring is rejected',()=>{const root=fs.mkdtempSync(path.join(os.tmpdir(),'member-keyring-'));try{const session=new MemberSession({root,safeStorage:{...safeStorage,getSelectedStorageBackend:()=> 'basic_text'}});assert.throws(()=>session.save({key:'secret'}));assert(!fs.existsSync(session.file()));}finally{fs.rmSync(root,{recursive:true,force:true});}});
test('real helper parent pipe, local files and shutdown', {skip:!process.env.MEMBER_DESKTOP_TEST_BINARY},async()=>{const root=fs.mkdtempSync(path.join(os.tmpdir(),'member-pipe-'));const session=new MemberSession({root,safeStorage,executable:process.env.MEMBER_DESKTOP_TEST_BINARY});try{const config={base:'http://127.0.0.1:9',key:'test-only',hub_id:'test-hub',device_id:'test-pc',...installation()};session.save(config);assert(await session.start());const child=session.child;const result=await session.request('file',{op:'write',path:'test.txt',content:'real local',expected_hash:'missing'});assert.equal(result.success,true);const read=await session.request('file',{op:'read',path:'test.txt'});assert.equal(read.content,'real local');assert.equal(read.sha256,crypto.createHash('sha256').update('real local').digest('hex'));await session.stop();assert.equal(child.exitCode,0);assert.equal(session.bridge,null);}finally{await session.stop();fs.rmSync(root,{recursive:true,force:true});}});

test('real executor update failure restores SQLite snapshot before restarting old binary', {skip:!process.env.MEMBER_DESKTOP_TEST_BINARY},async()=>{
 const {RuntimeUpdates,digest}=require('../updates.cjs');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'member-real-update-'));
 const session=new MemberSession({root,safeStorage,executable:process.env.MEMBER_DESKTOP_TEST_BINARY});
 try{
  session.save({base:'http://127.0.0.1:9',key:'test-only',hub_id:'test-hub',device_id:'test-pc',...installation()});
  await session.start();
  await session.request('file',{op:'write',path:'keep.txt',content:'user file',expected_hash:'missing'});
  const pair=crypto.generateKeyPairSync('ed25519'),feed='https://release.example/current.json';
  const binaryName='indiebiz-member'+(process.platform==='win32'?'.exe':'');
  const files=new Map([['workspace.html',Buffer.from('<html></html>')],['workspace.cjs',Buffer.from('void 0;')],[binaryName,fs.readFileSync(process.env.MEMBER_DESKTOP_TEST_BINARY)]]);
  const manifest={format:'indiebiz-member-runtime',sequence:1,version:'0.1.1',shell:1,protocol:2,platform:process.platform,arch:process.arch,expires:Date.now()/1000+60,files:[...files].map(([name,b])=>({name,size:b.length,sha256:digest(b),url:'https://release.example/'+name}))};
  const raw=Buffer.from(JSON.stringify(manifest)),envelope={manifest:raw.toString('base64'),signature:crypto.sign(null,raw,pair.privateKey).toString('base64')};
  const u=new RuntimeUpdates({root,session,trust:{feed,publicKey:pair.publicKey.export({type:'spki',format:'pem'})},baseline:{executable:session.executable,workspace:'old',version:'0.1.0'},fetcher:async(url)=>new Response(url===feed?JSON.stringify(envelope):files.get(new URL(url).pathname.slice(1))),show:async(file,trial)=>{if(trial){
   assert.equal((await session.internalRequest('maintenance',{pause:true})).idle,true);
   assert.equal((await session.internalRequest('task/start',{message:'must not start'})).error,'updating');
   await session.internalRequest('permissions',{screen:true});throw Error('failed UI health');
  }}});
  await u.check();const result=await u.apply();assert.equal(result.state,'rolled_back');
  assert.equal((await session.request('connection')).screen,false);
  assert.equal((await session.request('file',{op:'read',path:'keep.txt'})).content,'user file');
  assert.equal((await session.internalRequest('health')).success,true);
 }finally{await session.stop();fs.rmSync(root,{recursive:true,force:true});}
});
