/* Uses the repository's pinned Electron and builder, no second dependency tree. */
const {execFileSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const platform=process.argv.includes('--win')?'win32':'darwin';
const arch=process.argv.includes('--x64')||platform==='win32'?'x64':'arm64';
const release=process.argv.includes('--release');
function run(bin,args,options={}){execFileSync(bin,args,{cwd:root,stdio:'inherit',...options});}
if(release&&(!process.env.CSC_LINK&&!process.env.CSC_NAME))throw Error('릴리스에는 배포자 서명 자격(CSC_LINK 또는 CSC_NAME)이 필요합니다.');
const publicKeyFile=process.env.MEMBER_UPDATE_PUBLIC_KEY;
const feed=process.env.MEMBER_UPDATE_FEED;
if(release&&(!publicKeyFile||!feed))throw Error('릴리스에는 MEMBER_UPDATE_PUBLIC_KEY(공개키 파일)와 MEMBER_UPDATE_FEED(HTTPS)가 필요합니다.');
let trust={};
if(publicKeyFile||feed){
 const crypto=require('node:crypto');const key=crypto.createPublicKey(fs.readFileSync(publicKeyFile));
 if(key.asymmetricKeyType!=='ed25519')throw Error('업데이트 키는 Ed25519 공개키여야 합니다.');
 const url=new URL(feed);if(url.protocol!=='https:'||url.username||url.password||url.hash)throw Error('업데이트 피드는 HTTPS여야 합니다.');
 trust={publicKey:key.export({type:'spki',format:'pem'}),feed:url.href};
}
fs.writeFileSync(path.join(__dirname,'update-trust.json'),JSON.stringify(trust));
run('python3',['scripts/build_member_desktop.py']);
run('python3',['scripts/build_member_shell.py']);
fs.mkdirSync(path.join(__dirname,'resources'),{recursive:true});
run('go',['build','-trimpath','-ldflags=-s -w -X main.memberVersion='+require('./package.json').version,'-o',path.join(__dirname,'resources','indiebiz-member'+(platform==='win32'?'.exe':'')),'.'],{cwd:path.join(root,'helper'),env:{...process.env,GOOS:platform==='darwin'?'darwin':'windows',GOARCH:arch==='arm64'?'arm64':'amd64',CGO_ENABLED:'0'}});
const electron=path.join(root,'frontend/node_modules/electron');
const version=require(path.join(electron,'package.json')).version;
const config=JSON.parse(JSON.stringify(require('./package.json').build));
config.extraResources=[{from:path.join(__dirname,'resources','indiebiz-member'+(platform==='win32'?'.exe':'')),to:'member/indiebiz-member'+(platform==='win32'?'.exe':'')}];
if(release)delete config.mac.identity;
fs.mkdirSync(path.join(__dirname,'dist'),{recursive:true});const configFile=path.join(__dirname,'dist','builder-'+platform+'-'+arch+'.json');fs.writeFileSync(configFile,JSON.stringify(config));
const args=[path.join(root,'frontend/node_modules/electron-builder/cli.js'),'--config='+configFile,'--projectDir',__dirname,platform==='darwin'?'--mac':'--win','--'+arch,'--config.electronVersion='+version];
if(!release){args.push('--config.mac.identity=null');if(platform==='darwin'){args.push('--dir');if(arch===process.arch)args.push('--config.electronDist='+path.join(electron,'dist'));}}
else{args.push('--config.forceCodeSigning=true');if(platform==='darwin')args.push('--config.mac.notarize=true');}
run(process.execPath,args,{env:{...process.env,CSC_IDENTITY_AUTO_DISCOVERY:release?'true':'false'}});
if(platform==='darwin'&&!release){const folder=path.join(__dirname,'dist',arch==='arm64'?'mac-arm64':'mac');const destination=path.join(__dirname,'dist','IndieBizMember-mac-'+arch+'.zip');run('ditto',['-c','-k','--sequesterRsrc','--keepParent',path.join(folder,'IndieBiz Member.app'),destination]);console.log(destination);}
