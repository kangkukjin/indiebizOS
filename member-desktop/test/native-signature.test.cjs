const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {execFileSync}=require('node:child_process');
const {requirement,validateExecutable}=require('../native-signature.cjs');
const mac={skip:process.platform!=='darwin'};
test('real macOS signature accepts matching stable identity and rejects another signer identity',mac,()=>{
 assert.match(requirement('/usr/bin/true'),/identifier/);
 assert.doesNotThrow(()=>validateExecutable('/usr/bin/true','/usr/bin/true'));
 assert.throws(()=>validateExecutable('/bin/ls','/usr/bin/true'),/신원/);
});
test('ad-hoc replacement and damaged executable are rejected without touching private signing keys',mac,t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'member-native-signature-'));
 t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const copy=path.join(root,'candidate');fs.copyFileSync('/usr/bin/true',copy);
 execFileSync('/usr/bin/codesign',['--force','--sign','-',copy],{stdio:'pipe'});
 assert.throws(()=>requirement(copy),/지속 가능한/);
 fs.copyFileSync('/usr/bin/true',copy);
 const bytes=fs.readFileSync(copy);bytes[4096]^=1;fs.writeFileSync(copy,bytes);
 assert.throws(()=>validateExecutable(copy,'/usr/bin/true'),/검증 실패/);
});
