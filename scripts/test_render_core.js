/**
 * 원격 렌더러 회귀 하네스 — 조립된 런처 <script> 를 최소 DOM 셰임 위에서 실행하고
 * 각 프리미티브의 렌더 결과를 확인한다. 실행은 backend/test_render_core.py(pytest)가 한다.
 *
 * 왜: 렌더 로직의 정본이 backend/static/app_render_core.js 로 모인 뒤(2026-08-05 감사 ④),
 * 그 코어가 두 표면에서 *실제로 같은 것을 그리는지*를 재는 자리가 필요하다. 선언 대조가
 * 아니라 실행 검증 — 감사 ⑤가 IBL 액션에 세운 규율의 렌더러판.
 *
 * 사용: node scripts/test_render_core.js <조립된-스크립트.js>
 */
const fs = require('fs');
const vm = require('vm');
const src = fs.readFileSync(process.argv[2], 'utf8');

// --- 최소 DOM 셰임 (렌더는 순수 문자열 생성이라 esc + 몇몇 조회만 필요) ---
const mkEl = () => {
  const el = { _t: '', style: {}, classList: { toggle(){}, add(){}, remove(){} },
    appendChild(){}, addEventListener(){}, querySelectorAll: () => [], setAttribute(){}, getAttribute(){return null;} };
  Object.defineProperty(el, 'textContent', { get(){ return el._t; }, set(v){ el._t = String(v); } });
  Object.defineProperty(el, 'innerHTML', {
    get(){ return String(el._t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); },
    set(v){ el._t = v; } });
  return el;
};
const sandbox = {
  console,
  document: { createElement: mkEl, getElementById: () => null, querySelectorAll: () => [], body: mkEl(), addEventListener(){} },
  window: {}, navigator: { connection: undefined }, location: { search: '', href: '' },
  localStorage: { getItem: () => null, setItem(){}, removeItem(){} },
  fetch: async () => ({ ok: true, json: async () => ({}) }),
  setTimeout: () => 0, clearTimeout(){}, MutationObserver: function(){ this.observe = () => {}; },
  Date, Math, JSON, String, Number, Array, Object, RegExp, isNaN, parseInt, parseFloat, encodeURIComponent, alert(){},
};
sandbox.addEventListener = () => {};
sandbox.window = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: 'remote.js' });

const R = (view, data) => sandbox.renderView(view, data);
let fails = 0;
const check = (name, cond, extra) => { console.log((cond ? '  ok   ' : '  FAIL ') + name + (cond ? '' : ' :: ' + extra)); if (!cond) fails++; };

console.log('== 원격 렌더러 인프로세스 검증 ==');

// 1) 템플릿 엔진 + 이스케이프
check('tpl 필터 체인', sandbox.tpl('{a.b|round}·{n|num}·{d|arrow}', {a:{b:2.6}, n:12345, d:-1}) === '3·12,345·▼',
  sandbox.tpl('{a.b|round}·{n|num}·{d|arrow}', {a:{b:2.6}, n:12345, d:-1}));
check('tpl 이 값을 HTML 이스케이프', sandbox.tpl('{t}', {t:'<b>&'}) === '&lt;b&gt;&amp;', sandbox.tpl('{t}', {t:'<b>&'}));
check('buildAction 빈 파라미터 제거 + 백슬래시 보존',
  sandbox.buildAction('[n:a]{p:"$k", q:"$none"}', {k:'C:\\Users'}) === '[n:a]{p:"C:\\\\Users"}',
  sandbox.buildAction('[n:a]{p:"$k", q:"$none"}', {k:'C:\\Users'}));

// 2) 프리미티브 렌더
const metric = R([{type:'metric', label:'현재가', big:'{price|num}', unit:'원', sub:'{chg}', trend:'chg'}], {price:71500, chg:-2.1});
check('metric 값·추세색', metric.includes('71,500') && metric.includes('var(--down)'), metric.slice(0,160));

const kv = R([{type:'kv', title:'상태', rows:[{k:'이름', v:'{name}'}]}], {name:'a<b'});
check('kv 값 단일 이스케이프', kv.includes('a&lt;b') && !kv.includes('a&amp;lt;b'), kv);
const kvu = R([{type:'kv', rows:[{k:'주소', v:'{u}'}]}], {u:'https://x.io/?a=1&b=2'});
check('kv URL href 가 &amp;lt 로 안 망가짐', kvu.includes('href="https://x.io/?a=1&amp;b=2"') && !kvu.includes('&amp;amp;'), kvu);

const cards = R([{type:'card_list', from:'items', card:{title:'{t}', lines:['{s}'], wide:true}}], {items:[{t:'가',s:'나'},{t:'다',s:'라'}]});
check('card_list wide 그리드', cards.includes('auto-fill') && cards.includes('가') && cards.includes('다'), cards.slice(0,120));

const empty = R([{type:'card_list', from:'items', empty:'없어요', card:{title:'{t}'}}], {items:[]});
check('빈 결과 문구', empty.includes('없어요'), empty);

const grp = R([{type:'group', from:'items', by:'{sec}', view:[{type:'kv_list', from:'items', k:'{t}', v:'{v}'}]}],
  {items:[{sec:'A&B', t:'x', v:'1'}, {sec:'A&B', t:'y', v:'2'}, {sec:'C', t:'z', v:'3'}]});
check('group 파티션 2개', (grp.match(/<h3/g)||[]).length === 2, grp.slice(0,200));
check('group 헤더 단일 이스케이프(이중 이스케이프 회귀)', grp.includes('A&amp;B') && !grp.includes('A&amp;amp;B'), grp.slice(0,200));

const spark = R([{type:'sparkline', from:'items', y:'v'}], {items:[{v:1},{v:5},{v:3}]});
check('sparkline polyline', spark.includes('<polyline') && spark.includes('points="0.0,50.0'), spark.slice(0,200));
check('sparkline 점 1개면 안 그림', R([{type:'sparkline', from:'items', y:'v'}], {items:[{v:1}]}) === '', 'expected empty');

const thread = R([{type:'thread', from:'items', text:'{t}', mine:'me', status:'st'}], {items:[{t:'안녕', me:true, st:'sent'}]});
check('thread 버블 + 상태 글리프', thread.includes('안녕') && thread.includes('✓'), thread);

const media = R([{type:'media_player', from:'items', src:'{u}', title:'{t}', lazy:true}], {items:[{u:'/music/stream?p=1', t:'곡'}]});
check('media_player lazy preload=none', media.includes('preload="none"') && media.includes('/music/stream?p=1'), media);

const vid = R([{type:'media_player', from:'items', src:'{u}', video:'{isv}'}], {items:[{u:'/v.mp4', isv:'true'}]});
check('media_player video 분기', vid.includes('<video'), vid);

// --- 소스 해소: '/' 로 시작한다고 site-relative 가 아니다 (파일시스템 절대경로도 '/' 로 시작) ---
// 회귀: 오디오 브리핑(self:file_find 의 url = /Users/…/x.mp3)이 <audio src="/Users/…"> 로 박혀 404.
const FILE = '/Users/k/Desktop/AI/indiebizOS/projects/앱모드/outputs/audio_briefing_current.mp3';
const fileMedia = R([{type:'media_player', from:'items', src:'{u}'}], {items:[{u:FILE}]});
check('파일 절대경로 → /launcher/file 서빙',
  fileMedia.includes('/launcher/file?path=' + encodeURIComponent(FILE)) && !fileMedia.includes('src="/Users/'),
  fileMedia);
check('백엔드 라우트는 그대로(음악 계기 회귀)',
  sandbox.resolveMediaUrl('/music/stream?path=%2Fa%2Fb.mp3', '') === '/music/stream?path=%2Fa%2Fb.mp3',
  sandbox.resolveMediaUrl('/music/stream?path=%2Fa%2Fb.mp3', ''));
check('데스크탑 base 부착', sandbox.resolveMediaUrl('/yt/hls/abc/master.m3u8', 'http://127.0.0.1:8765')
  === 'http://127.0.0.1:8765/yt/hls/abc/master.m3u8', sandbox.resolveMediaUrl('/yt/hls/abc/master.m3u8', 'http://127.0.0.1:8765'));
check('절대 URL 은 손대지 않음', sandbox.resolveMediaUrl('https://cdn/x.mp4', 'http://b') === 'https://cdn/x.mp4',
  sandbox.resolveMediaUrl('https://cdn/x.mp4', 'http://b'));
check('빈 소스 → 빈 문자열', sandbox.resolveMediaUrl('', 'http://b') === '', sandbox.resolveMediaUrl('', 'http://b'));
check('해소는 멱등(이미 푼 URL 재투입)',
  sandbox.resolveMediaUrl(sandbox.resolveMediaUrl(FILE, ''), '') === sandbox.resolveMediaUrl(FILE, ''),
  sandbox.resolveMediaUrl(sandbox.resolveMediaUrl(FILE, ''), ''));
// 세그먼트 경계 — /music 은 /music/… 에만 맞고 /musicbox(있을 법한 폴더)엔 안 맞는다
check('라우트 판정은 세그먼트 경계',
  sandbox.isBackendRoute('/music/stream?p=1') && sandbox.isBackendRoute('/photo') &&
  !sandbox.isBackendRoute('/musicbox/a.mp3') && !sandbox.isBackendRoute('/Users/k/photo/a.jpg') &&
  !sandbox.isBackendRoute('rel/path.mp3'),
  [sandbox.isBackendRoute('/musicbox/a.mp3'), sandbox.isBackendRoute('/Users/k/photo/a.jpg')].join(','));
// poster·HLS 도 같은 규칙(플레이어 안에서 소스가 셋)
const pv = R([{type:'media_player', from:'items', src:'{u}', poster:'{p}', video:true}],
  {items:[{u:'/yt/relay/v1', p:'/Users/k/thumb.jpg'}]});
check('poster 도 같은 해소', pv.includes('poster="/launcher/file?path=') && pv.includes('src="/yt/relay/v1"'), pv);

const form = R([{type:'form', title:'정보', fields:[{key:'name', label:'이름', type:'text', value:'{name}'},
  {key:'when', label:'날짜', type:'datetime'}, {key:'rep', label:'반복', type:'recurrence'}], action:'[n:a]{}'}], {name:'홍길동'});
check('form 값·datetime-local·recurrence', form.includes('홍길동') && form.includes('datetime-local') && form.includes('매주'), form.slice(0,300));

const imgs = R([{type:'form', fields:[{key:'a', type:'images', value:'["p1.jpg","p2.jpg"]', remove_action:'[n:a]{}'}], action:'[n:a]{}'}], {});
check('images 필드 2장 파싱', (imgs.match(/\/image\?path=/g)||[]).length === 2, imgs.slice(0,240));

const grid = R([{type:'image_grid', from:'items', image:'{img}', title:'{t}', button:{label:'빼기', action:'[n:a]{}'}}], {items:[{img:'/t.jpg', t:'사진'}]});
check('image_grid 행 버튼', grid.includes('빼기') && grid.includes('rowBtn('), grid.slice(0,200));

const la = R([{type:'list_action', from:'items', title:'{t}', sub:'{s}', button:{label:'▶'}, item_click:{action:'[n:a]{}'}}], {items:[{t:'가',s:'나'}]});
check('list_action 드릴+버튼', la.includes('rowDrill(') && la.includes('rowBtn('), la.slice(0,200));

const blocks = R([{type:'blocks', from:'items'}], {items:[{type:'heading', level:2, text:'제목'}, {type:'paragraph', text:'**굵게** 본문'}]});
check('blocks 문서 IR', blocks.includes('제목') && blocks.includes('<strong>굵게</strong>'), blocks.slice(0,240));

const el = R([{type:'editable_list', from:'items', display:'{t}', delete_action:'[n:a]{}', add:{fields:[{key:'t',type:'text'}], action:'[n:a]{}'}}], {items:[{t:'항목'}]});
check('editable_list 행+추가', el.includes('항목') && el.includes('elAdd('), el.slice(0,200));

// 3) 달력 — 월 산식이 코어로 이동한 뒤에도 그리드가 그려지는가
sandbox._calSetup({from:'items'}, {items:[{date:'2026-08-15', title:'약속'}, {repeat:'weekly', title:'주간보고'}]});
check('_calSetup 이벤트 적재', sandbox._calCur && sandbox._calCur.events.length === 2, JSON.stringify(sandbox._calCur && sandbox._calCur.events));
const cm = sandbox.calendarModel([{date:'2026-01-31', repeat:'monthly'}, {date:'2026-02-10'}, {repeat:'daily'}], 2026, 2);
check('calendarModel: 2월에 31일 반복 안 샘', !cm.byDay[31] && !!cm.byDay[10], JSON.stringify(cm.byDay));
check('calendarModel: 정기 분리', cm.recurring.length === 1, JSON.stringify(cm.recurring));
const sh = sandbox.calShift(2026, 1, -1);
check('calShift 연도 넘김', sh.year === 2025 && sh.month === 12, JSON.stringify(sh));

// 4) 모드 레벨 결정
check('hasMasterDetail', sandbox.hasMasterDetail([{type:'card_list', master_detail:true}]) === true, '');
check('dynFilterCats distinct', JSON.stringify(sandbox.dynFilterCats({items:[{c:'A'},{c:'B'},{c:'A'}]}, 'items', 'c')) === '["A","B"]', '');
check('applyDynFilter 거르기', sandbox.applyDynFilter({items:[{c:'A'},{c:'B'}]}, 'items', 'c', 'A').items.length === 1, '');
check('unwrapFinalResult JSON 문자열', sandbox.unwrapFinalResult({final_result:'{"a":1}'}).a === 1, '');
check('unwrapFinalResult 비-JSON 문자열 → message', sandbox.unwrapFinalResult({final_result:'끝'}).message === '끝', '');

// 5) compose 채널
const opts = sandbox.composeChannelOptions({channels:{from:'contacts', type:'ct', value:'cv', sendable:['gmail','nostr']}},
  {channel:'nostr', contacts:[{ct:'gmail', cv:'a@b.c'}, {ct:'nostr', cv:'npub1'}, {ct:'phone', cv:'010'}]});
check('compose 채널 화이트리스트 + primary 우선', opts.length === 2 && opts[0].channel_type === 'nostr', JSON.stringify(opts));

// 6) 에러 통화
check('error 통화 표시', R([{type:'kv', rows:[]}], {error:'문제 발생'}).includes('문제 발생'), '');
check('success:false 통화 표시', R([{type:'kv', rows:[]}], {success:false, message:'실패함'}).includes('실패함'), '');

console.log(fails ? `\n실패 ${fails}건` : '\n전부 통과');
process.exit(fails ? 1 : 0);
