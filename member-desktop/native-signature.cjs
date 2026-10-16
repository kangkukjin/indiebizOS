/* The update manifest authenticates bytes; macOS privacy permissions need stable code identity too. */
const {execFileSync}=require('node:child_process');
function codesign(args){
 try{return execFileSync('/usr/bin/codesign',args,{encoding:'utf8',stdio:['ignore','pipe','pipe'],timeout:15000});}
 catch(error){throw Error('macOS 실행부 서명 검증 실패: '+String(error.stderr||error.message).trim());}
}
function requirement(file){
 const value=codesign(['--display','--requirements','-',file]);
 const match=value.match(/^designated => (.+)$/m);
 if(!match||/\bcdhash\b/.test(match[1])||!match[1].includes('identifier ')||!/(?:certificate|anchor) /.test(match[1])){
  throw Error('실행부에 지속 가능한 macOS 코드 서명이 없습니다. 정식 서명 설치물로 먼저 갱신하세요.');
 }
 codesign(['--verify','--strict',file]);
 return match[1];
}
function validateExecutable(candidate,baseline,platform=process.platform){
 if(platform!=='darwin')return;
 const expected=requirement(baseline);
 // Compare both identities so subsequent updates cannot silently broaden the requirement.
 if(requirement(candidate)!==expected)throw Error('새 실행부의 macOS 코드 신원이 설치물과 다릅니다. 전체 설치물 갱신이 필요합니다.');
 codesign(['--verify','--strict','--test-requirement','='+expected,candidate]);
}
module.exports={requirement,validateExecutable};
