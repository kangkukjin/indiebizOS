"""회원 앱은 원격 런처 렌더러 그대로, 로컬 승인 토큰이 없는 별도 프레임에서 그린다."""
from launcher_app_common import LAUNCHER_COMMON_JS
from launcher_render_core import LAUNCHER_CORE_JS
from launcher_app_appmode import LAUNCHER_APPMODE_HEAD_JS, LAUNCHER_APPMODE_REST_JS
from launcher_web_render import LAUNCHER_RENDER_JS


def frame_html():
    head = '''<!doctype html><html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'"><style>
:root{--bg:#f6f5f1;--bg2:white;--txt:#20372d;--dim:#65766e;--line:#d7dfda;--acc:#245644;--info:#256b95;--up:#23754a;--down:#b43737}body{font:15px system-ui;color:var(--txt);margin:12px}button,input,select,textarea{font:inherit;padding:10px;border-radius:8px;border:1px solid var(--line);background:white}button{cursor:pointer}button.go,.on{background:var(--acc);color:white}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px}.tile{min-height:110px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px}.em{font-size:28px}.row,.tabs,.btnrow{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}.inst-head{display:flex;align-items:center;gap:12px}.muted{color:var(--dim)}table{border-collapse:collapse;width:100%}td,th{padding:12px;text-align:left;border-bottom:1px solid var(--line)}pre{white-space:pre-wrap;overflow-wrap:anywhere}.card{padding:15px;background:white;margin:10px 0;border-radius:10px}a{color:var(--info)}#instOut{overflow:auto}
</style><div id="appHome"></div><div id="appInst" style="display:none"></div><script>window.__MEMBER=true;</script>'''
    bridge = r'''
let seq=0;const pending=new Map();
function memberBoot(){parent.postMessage({memberFrame:'ready'},'*')}
window.addEventListener('message',e=>{if(e.source!==parent)return;const m=e.data||{};if(m.memberFrame==='apps'){INSTRUMENTS=m.instruments||[];renderAppHome()}if(m.memberFrame==='result'){const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(m.error)):p.resolve(memberAppResult(m.result))}}});
function memberAppResult(value){const v=unwrapFinalResult(value);return typeof v==='string'?{text:v}:v&&v.message&&!v.text?{...v,text:v.message}:v}
function ibl(code){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});parent.postMessage({memberFrame:'execute',id,code},'*')})}
function jfetch(){return Promise.reject(Error('회원 앱에서 이 네트워크 경로는 사용할 수 없습니다'))}
async function loadInstruments(){}
function renderAppHome(){document.getElementById('appInst').style.display='none';const h=document.getElementById('appHome');h.style.display='block';h.innerHTML='<div class="grid">'+INSTRUMENTS.map((i,n)=>'<button class="tile" onclick="openInstrument('+n+')"><span class="em">'+esc(i.icon||'◻')+'</span><span>'+esc(i.name)+'</span></button>').join('')+'</div>'}
function _upFileObj(){alert('자율주행의 내 파일 화면에서 파일을 가져오고 그 경로를 입력하세요')}
window.addEventListener('popstate',appBackHome);
'''
    return head + LAUNCHER_COMMON_JS + LAUNCHER_CORE_JS + LAUNCHER_APPMODE_HEAD_JS + LAUNCHER_APPMODE_REST_JS + LAUNCHER_RENDER_JS.split('</script>')[0] + bridge + '</script></html>'
