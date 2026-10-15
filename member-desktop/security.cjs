const crypto = require('node:crypto');
function hubAddress(raw) {
  const u = new URL(raw);
  if (u.username || u.password || u.search || u.hash || !['', '/'].includes(u.pathname)) throw Error('중앙 주소만 입력하세요.');
  if (u.protocol !== 'https:' && !(u.protocol === 'http:' && ['localhost','127.0.0.1'].includes(u.hostname))) throw Error('중앙 주소는 HTTPS여야 합니다.');
  return u.origin;
}
function installation() {
  const {publicKey, privateKey} = crypto.generateKeyPairSync('ed25519');
  return {installation_id:crypto.randomUUID(), private_key:privateKey.export({format:'der',type:'pkcs8'}).subarray(-32).toString('base64'), public_key:publicKey.export({format:'der',type:'spki'}).subarray(-32).toString('base64')};
}
function signingKey(seed) {return crypto.createPrivateKey({key:Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),Buffer.from(seed,'base64')]),format:'der',type:'pkcs8'});}
function exchangeProof(identity, code, requestId) {
  const text = ['member-enroll-v1',code,requestId,identity.installation_id,identity.public_key].join('\n');
  return crypto.sign(null,Buffer.from(text),signingKey(identity.private_key)).toString('base64');
}
function invitation(raw) {
  const u = new URL(raw);
  if (u.protocol !== 'indiebiz-member:' || u.hostname !== 'enroll') throw Error('회원 등록 링크가 아닙니다.');
  const hub = hubAddress(u.searchParams.get('hub'));
  const code = u.searchParams.get('code') || '';
  if (!/^[A-Z2-7]{16}$/.test(code)) throw Error('등록 코드를 확인하세요.');
  return {hub,code};
}
function safeEndpoint(path, body) {
  if (typeof path !== 'string' || path.length > 300 || /[\\#]/.test(path)) throw Error('잘못된 요청');
  const u=new URL(path,'http://member.local/');
  const get = new Set(['tasks','task','workspace','approvals','history','results','media','changes','connection']);
  const post = new Set(['file','task/start','workspace','approve','close','profile','apps','export','media-claim','media-result','restore','permissions']);
  if (u.origin !== 'http://member.local' || !(body===undefined?get:post).has(u.pathname.slice(1))) throw Error('허용되지 않은 요청');
  if ([...u.searchParams.keys()].some(k=>k!=='id')) throw Error('잘못된 조회');
  if (body !== undefined && (!body || typeof body!=='object' || Array.isArray(body) || JSON.stringify(body).length>46*1024*1024)) throw Error('요청 크기 또는 형식 오류');
  return u.pathname.slice(1)+u.search;
}
module.exports={hubAddress,installation,exchangeProof,invitation,safeEndpoint};
