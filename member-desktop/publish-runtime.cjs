/* Offline release authoring. The private signing key is read, never copied to an artifact. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {verify,digest,SHELL_VERSION}=require('./updates.cjs');
function publish({source,helper,out,base,version,sequence,platform,arch,key,expires}){
 const privateKey=crypto.createPrivateKey(fs.readFileSync(key));if(privateKey.asymmetricKeyType!=='ed25519')throw Error('Ed25519 서명 키가 필요합니다.');
 const origin=new URL(base);if(origin.protocol!=='https:'||origin.search||origin.hash||origin.username||origin.password)throw Error('공개 HTTPS 디렉터리가 필요합니다.');
 const prefix=origin.href.replace(/\/?$/,'/');
 const names=['workspace.html','workspace.cjs','indiebiz-member'+(platform==='win32'?'.exe':'')];
 const sources=[path.join(source,'workspace.html'),path.join(source,'workspace.cjs'),helper];
 const files=names.map((name,i)=>{const data=fs.readFileSync(sources[i]);return {name,url:prefix+sequence+'/'+name,size:data.length,sha256:digest(data)}});
 const manifest={format:'indiebiz-member-runtime',version,sequence,platform,arch,protocol:2,shell:SHELL_VERSION,expires,files};
 const raw=Buffer.from(JSON.stringify(manifest));const envelope={manifest:raw.toString('base64'),signature:crypto.sign(null,raw,privateKey).toString('base64')};
 const publicKey=crypto.createPublicKey(privateKey).export({type:'spki',format:'pem'});
 verify(envelope,{publicKey,feed:prefix+'current.json'},{platform,arch});
 fs.mkdirSync(out,{recursive:true});const dir=path.join(out,String(sequence));fs.mkdirSync(dir); // Never overwrite a published sequence.
 names.forEach((name,i)=>fs.copyFileSync(sources[i],path.join(dir,name)));
 fs.writeFileSync(path.join(out,'current.json'),JSON.stringify(envelope,null,2));
 return {feed:prefix+'current.json',publicKey,sequence};
}
if(require.main===module){const args={};for(let i=2;i<process.argv.length;i+=2){if(!process.argv[i].startsWith('--')||!process.argv[i+1])throw Error('모든 --옵션에 값이 필요합니다.');args[process.argv[i].slice(2)]=process.argv[i+1];}for(const key of ['source','helper','out','base','version','sequence','platform','arch','key'])if(!args[key])throw Error('--'+key+' 필요');args.sequence=Number(args.sequence);args.expires=args.expires?Number(args.expires):Math.floor(Date.now()/1000)+30*86400;const result=publish(args);console.log(JSON.stringify({feed:result.feed,sequence:result.sequence}));}
module.exports={publish};
