/* Offline release authoring. The private signing key is read, never copied to an artifact. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {verify,digest,SHELL_VERSION}=require('./updates.cjs');
function publish({source,helper,out,base,version,sequence,platform,arch,key,expires,kind='runtime'}){
 if(!['runtime','ui'].includes(kind))throw Error('알 수 없는 릴리스 종류');
 const privateKey=crypto.createPrivateKey(fs.readFileSync(key));if(privateKey.asymmetricKeyType!=='ed25519')throw Error('Ed25519 서명 키가 필요합니다.');
 const origin=new URL(base);if(origin.protocol!=='https:'||origin.search||origin.hash||origin.username||origin.password)throw Error('공개 HTTPS 디렉터리가 필요합니다.');
 const prefix=origin.href.replace(/\/?$/,'/');
 const names=kind==='ui'?['display.json']:['workspace.html','workspace.cjs','indiebiz-member'+(platform==='win32'?'.exe':'')];
 const sources=kind==='ui'?[path.join(source,'display.json')]:[path.join(source,'workspace.html'),path.join(source,'workspace.cjs'),helper];
 const display=kind==='ui'?JSON.parse(fs.readFileSync(sources[0],'utf8')):null;
 if(display&&(display.format!=='indiebiz-display-1'||!['desktop','member','phone'].includes(display.surface)))throw Error('배포할 화면 모듈 형식 오류');
 const contents=sources.map(file=>fs.readFileSync(file));
 const files=names.map((name,i)=>{const data=contents[i];return {name,url:prefix+(kind==='ui'?'ui/':'')+sequence+'/'+name,size:data.length,sha256:digest(data)}});
 const manifest={format:'indiebiz-member-runtime',...(kind==='ui'?{kind,host:display.host,state:display.state}:{}),version,sequence,platform,arch,protocol:2,shell:SHELL_VERSION,expires,files};
 const raw=Buffer.from(JSON.stringify(manifest));const envelope={manifest:raw.toString('base64'),signature:crypto.sign(null,raw,privateKey).toString('base64')};
 const publicKey=crypto.createPublicKey(privateKey).export({type:'spki',format:'pem'});
 verify(envelope,{publicKey,feed:prefix+'current.json'},{platform,arch});
 fs.mkdirSync(out,{recursive:true});const dir=path.join(out,...(kind==='ui'?['ui']:[]),String(sequence));if(kind==='ui')fs.mkdirSync(path.join(out,'ui'),{recursive:true});fs.mkdirSync(dir); // Never overwrite a published sequence.
 names.forEach((name,i)=>fs.writeFileSync(path.join(dir,name),contents[i]));
 const pointer=path.join(out,'current.json'),temporary=pointer+'.'+crypto.randomUUID()+'.tmp';
 fs.writeFileSync(temporary,JSON.stringify(envelope,null,2));fs.renameSync(temporary,pointer);
 return {feed:prefix+'current.json',publicKey,sequence};
}
if(require.main===module){const args={};for(let i=2;i<process.argv.length;i+=2){if(!process.argv[i].startsWith('--')||!process.argv[i+1])throw Error('모든 --옵션에 값이 필요합니다.');args[process.argv[i].slice(2)]=process.argv[i+1];}for(const key of ['source','out','base','version','sequence','platform','arch','key'])if(!args[key])throw Error('--'+key+' 필요');if(args.kind!=='ui'&&!args.helper)throw Error('--helper 필요');args.sequence=Number(args.sequence);args.expires=args.expires?Number(args.expires):Math.floor(Date.now()/1000)+30*86400;const result=publish(args);console.log(JSON.stringify({feed:result.feed,sequence:result.sequence}));}
module.exports={publish};
