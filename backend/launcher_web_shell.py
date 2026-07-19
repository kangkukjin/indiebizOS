"""원격 런처 웹앱 — 문서 셸(head·CSS·body 골격). launcher_web_app/render 와 연결돼 한 문서.

api_launcher_web.get_launcher_webapp_html() 이 세 조각을 그대로 이어붙인다(바이트 동일 조립).
2026-07-18 모듈화(1500줄 규칙) — api_launcher_web.py 의 단일 문자열에서 verbatim 이동.
"""

LAUNCHER_SHELL_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>IndieBiz OS — Remote Launcher</title>
<!-- 폰 라디오 재생용: 한국 방송은 HLS(.m3u8)라 Android WebView 직접재생에 hls.js 필요 -->
<script src="https://cdn.jsdelivr.net/npm/hls.js@1"></script>
<!-- 지도 render 프리미티브(길찾기·부동산·상권·CCTV): leaflet -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
/* 데스크탑 런처(Launcher.tsx)와 같은 크림 라이트 테마 — bg #F5F1EB·텍스트 #4A4035·앰버 강조 */
:root{
  --bg:#F5F1EB; --bg2:#FFFFFF; --bg3:#EAE4DA; --line:#E5DFD5;
  --txt:#4A4035; --dim:#8A7B6C; --acc:#D97706; --acc2:#B45309;
  --acc-soft:rgba(217,119,6,.12); --acc-grad:linear-gradient(135deg,#F59E0B,#D97706);
  --ok:#059669; --warn:#B45309; --unknown:#A8A29E; --info:#2563EB;
  --up:#DC2626; --down:#2563EB;
  --shadow:0 1px 2px rgba(74,64,53,.05), 0 4px 14px rgba(74,64,53,.06);
}
body{ font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Pretendard','Noto Sans KR','Segoe UI',Roboto,sans-serif; background:var(--bg); color:var(--txt); min-height:100vh; -webkit-font-smoothing:antialiased; letter-spacing:-.011em; line-height:1.5; }
button{ font-family:inherit; cursor:pointer; transition:background .15s,border-color .15s,color .15s,transform .08s; }
button:active{ transform:scale(.97); }
input,textarea,select{ font-family:inherit; }
::-webkit-scrollbar{ width:6px; height:6px; }
::-webkit-scrollbar-thumb{ background:#D8D1C3; border-radius:4px; }

/* 로그인 */
.login{ display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:100vh; padding:20px; background:radial-gradient(120% 90% at 50% 0%, #FDFAF5 0%, var(--bg) 60%); }
.login-box{ background:var(--bg2); border:1px solid var(--line); padding:38px 30px; border-radius:20px; width:100%; max-width:380px; box-shadow:0 20px 60px rgba(74,64,53,.14); }
.login-box h1{ font-size:24px; text-align:center; letter-spacing:-.02em; }
.login-box p.sub{ color:var(--dim); text-align:center; font-size:13px; margin:6px 0 26px; }
.inp{ width:100%; padding:14px 16px; border:1px solid var(--line); border-radius:12px; background:var(--bg); color:var(--txt); font-size:16px; transition:border-color .15s, box-shadow .15s; }
.inp:focus{ outline:none; border-color:var(--acc); box-shadow:0 0 0 3px var(--acc-soft); }
.btn{ width:100%; padding:14px; background:var(--acc-grad); color:#fff; border:none; border-radius:12px; font-size:16px; font-weight:700; margin-top:14px; box-shadow:0 4px 14px rgba(217,119,6,.25); }
.btn:hover{ filter:brightness(1.08); }
.btn:disabled{ background:var(--line); cursor:not-allowed; }
.err{ color:var(--acc); text-align:center; margin-top:14px; font-size:13px; min-height:18px; }

/* 앱 셸 */
.app{ display:none; flex-direction:column; height:100vh; }
.app.on{ display:flex; }
.top{ display:flex; align-items:center; justify-content:space-between; padding:calc(10px + env(safe-area-inset-top)) 16px 10px; background:var(--bg2); border-bottom:1px solid var(--line); flex-shrink:0; }
.top .brand{ display:flex; align-items:center; gap:8px; font-weight:700; font-size:15px; letter-spacing:-.01em; }
.top .badge{ background:var(--acc-soft); color:var(--acc2); font-size:10px; font-weight:700; padding:3px 8px; border-radius:999px; letter-spacing:.6px; }
.iconbtn{ background:var(--bg3); border:1px solid transparent; color:var(--txt); width:34px; height:34px; border-radius:10px; font-size:15px; }
.iconbtn:hover{ border-color:var(--acc); color:var(--acc2); }

/* 표면 토글 */
.surfaces{ display:flex; gap:5px; padding:8px 12px; background:var(--bg2); border-bottom:1px solid var(--line); flex-shrink:0; }
.surf-tab{ flex:1; padding:9px 4px; background:transparent; border:1px solid transparent; border-radius:11px; color:var(--dim); font-size:12.5px; font-weight:600; display:flex; flex-direction:column; align-items:center; gap:3px; transition:all .15s; }
.surf-tab .em{ font-size:19px; filter:grayscale(.35) brightness(.9); transition:filter .15s; }
.surf-tab.on{ background:var(--acc-soft); border-color:rgba(217,119,6,.4); color:#92400E; }
.surf-tab.on .em{ filter:none; }
.surf-tab .hint{ font-size:9px; font-weight:400; opacity:.65; }

.panel{ flex:1; overflow-y:auto; display:none; }
.panel.on{ display:flex; flex-direction:column; }
.wrap{ max-width:720px; width:100%; margin:0 auto; padding:16px; }

/* 공통 */
.row{ display:flex; gap:8px; }
.field{ flex:1; padding:12px 14px; border:1px solid var(--line); border-radius:12px; background:var(--bg2); color:var(--txt); font-size:15px; transition:border-color .15s, box-shadow .15s; }
.field:focus{ outline:none; border-color:var(--acc); box-shadow:0 0 0 3px var(--acc-soft); }
.go{ padding:12px 18px; background:var(--acc-grad); color:#fff; border:none; border-radius:12px; font-weight:700; white-space:nowrap; box-shadow:0 3px 10px rgba(217,119,6,.22); }
.go:hover{ filter:brightness(1.08); }
.go:disabled{ background:var(--bg3); box-shadow:none; color:var(--dim); }
.muted{ color:var(--dim); font-size:13px; }
.card{ background:var(--bg2); border:1px solid var(--line); border-radius:14px; padding:15px; margin-bottom:10px; box-shadow:var(--shadow); }
.spin{ width:22px; height:22px; border:2px solid var(--line); border-top-color:var(--acc); border-radius:50%; animation:sp 1s linear infinite; }
@keyframes sp{ to{ transform:rotate(360deg); } }
.center{ display:flex; align-items:center; justify-content:center; gap:10px; padding:30px; color:var(--dim); }
.pill{ display:inline-block; padding:2px 8px; border-radius:8px; font-size:11px; font-weight:600; }

/* === 자율주행 (드릴다운: 대상 선택 → 대화, 전체 폭) === */
.ap-browse{ flex:1; overflow-y:auto; padding:14px; }
.ap-browse>div{ max-width:720px; margin-left:auto; margin-right:auto; }
.ap-browse h3{ font-size:11px; text-transform:uppercase; color:var(--dim); margin:16px 4px 8px; letter-spacing:.5px; }
.ap-browse h3:first-child{ margin-top:2px; }
.ap-bhead{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }
.ap-bhead h2{ font-size:18px; }
.ap-card{ display:flex; align-items:center; gap:13px; padding:13px 15px; background:var(--bg2); border:1px solid var(--line); border-radius:14px; margin-bottom:8px; box-shadow:var(--shadow); transition:border-color .15s, transform .08s; }
.ap-card:hover{ border-color:var(--acc); }
.ap-card:active{ transform:scale(.985); }
.ap-card .ic{ font-size:20px; width:42px; height:42px; display:flex; align-items:center; justify-content:center; background:var(--bg3); border-radius:12px; flex-shrink:0; }
.ap-card .tx{ flex:1; min-width:0; display:flex; flex-direction:column; }
.ap-card .tx .nm{ font-weight:600; font-size:15px; }
.ap-card .tx .ds{ font-size:12px; color:var(--dim); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ap-card .chev{ color:var(--dim); font-size:20px; flex-shrink:0; }
.ap-chat{ flex:1; display:flex; flex-direction:column; min-height:0; }
.ap-head{ padding:11px 14px; background:var(--bg2); border-bottom:1px solid var(--line); display:flex; align-items:center; gap:10px; }
.ap-head .ap-head-t{ min-width:0; flex:1; }
.ap-head h2{ font-size:16px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ap-head p{ font-size:11px; color:var(--dim); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.msgs{ flex:1; overflow-y:auto; padding:16px; }
.msgs .empty{ color:var(--dim); text-align:center; padding:40px 20px; font-size:14px; line-height:1.6; }
.msg{ margin-bottom:14px; display:flex; gap:10px; }
.msg.user{ flex-direction:row-reverse; }
.av{ width:30px; height:30px; border-radius:50%; background:var(--bg3); display:flex; align-items:center; justify-content:center; flex-shrink:0; font-size:15px; }
.bub{ max-width:82%; background:var(--bg2); border:1px solid var(--line); padding:10px 14px; border-radius:16px; border-top-left-radius:5px; font-size:14px; line-height:1.6; white-space:pre-wrap; word-break:break-word; box-shadow:var(--shadow); }
.msg.user .bub{ background:var(--acc-grad); border-color:transparent; border-radius:16px; border-top-right-radius:5px; color:#fff; }
/* 버블 안 마크다운(경량 렌더) */
.bub .mdh{ display:inline; font-weight:700; color:#292524; }
.msg.user .bub .mdh{ color:#fff; }
.bub .mdq{ color:var(--dim); }
.bub code{ font-family:'SF Mono',Menlo,monospace; font-size:.88em; background:rgba(120,95,60,.1); padding:1px 5px; border-radius:5px; }
.msg.user .bub code{ background:rgba(255,255,255,.22); }
.bub pre{ background:#F1ECE2; border:1px solid var(--line); border-radius:10px; padding:10px 12px; margin:4px 0; font-size:12px; line-height:1.5; overflow-x:auto; white-space:pre; font-family:'SF Mono',Menlo,monospace; color:#3F3A33; }
.bub a{ color:var(--info); word-break:break-all; }
.msg.user .bub a{ color:#FFF3D6; }
.ap-hist-sep{ text-align:center; color:var(--dim); font-size:12px; margin:14px 0 4px; opacity:.7; }
.composer{ padding:12px 16px calc(12px + env(safe-area-inset-bottom)); background:var(--bg2); border-top:1px solid var(--line); display:flex; gap:8px; }
.composer textarea{ flex:1; padding:11px 15px; border:1px solid var(--line); border-radius:18px; background:var(--bg); color:var(--txt); font-size:14px; resize:none; max-height:120px; transition:border-color .15s, box-shadow .15s; }
.composer textarea:focus{ outline:none; border-color:var(--acc); box-shadow:0 0 0 3px var(--acc-soft); }
.sw-item{ display:flex; align-items:center; gap:12px; }
.sw-item .nm{ flex:1; font-weight:600; font-size:14px; }
.sw-item .pr{ font-size:11px; color:var(--dim); }

/* === 수동 === */
.step{ margin-bottom:16px; }
.step-label{ font-size:11px; color:var(--dim); text-transform:uppercase; letter-spacing:.5px; margin-bottom:7px; font-weight:600; }
.codebox{ width:100%; min-height:64px; padding:13px; border:1px solid var(--line); border-radius:10px; background:#FAF7F0; color:#7C2D12; font-family:'SF Mono',Menlo,monospace; font-size:13px; line-height:1.5; resize:vertical; }
.eff{ background:var(--bg2); border:1px solid var(--line); border-left-width:3px; border-radius:8px; padding:11px 13px; margin-bottom:8px; }
.eff.read{ border-left-color:var(--ok); }
.eff.write{ border-left-color:var(--warn); }
.eff.unknown{ border-left-color:var(--unknown); }
.eff .h{ display:flex; align-items:center; gap:8px; font-size:13px; font-weight:600; }
.eff .e{ font-size:13px; color:var(--dim); margin-top:5px; line-height:1.45; }
.s-read{ background:rgba(5,150,105,.1); color:#047857; }
.s-write{ background:rgba(180,83,9,.1); color:#92400E; }
.s-unknown{ background:rgba(120,113,108,.12); color:var(--dim); }
.warnbox{ background:rgba(217,119,6,.07); border:1px solid rgba(180,83,9,.4); border-radius:10px; padding:12px; margin-bottom:12px; font-size:13px; display:flex; align-items:flex-start; gap:9px; }
.warnbox input{ margin-top:2px; width:17px; height:17px; accent-color:var(--warn); }
.result{ background:#FAF7F0; border:1px solid var(--line); border-radius:10px; padding:13px; font-family:'SF Mono',Menlo,monospace; font-size:12px; line-height:1.5; white-space:pre-wrap; word-break:break-word; max-height:340px; overflow:auto; color:#3F3A33; }
.refbox{ font-size:12px; color:var(--dim); background:var(--bg); border:1px dashed var(--line); border-radius:8px; padding:10px; margin-top:8px; white-space:pre-wrap; max-height:160px; overflow:auto; display:none; }
.linkbtn{ background:none; border:none; color:var(--info); font-size:12px; padding:4px 0; text-decoration:underline; }
.btnrow{ display:flex; gap:8px; flex-wrap:wrap; }
.btn2{ padding:11px 16px; border:1px solid var(--line); background:var(--bg3); color:var(--txt); border-radius:12px; font-weight:600; font-size:14px; }
.btn2:hover{ border-color:var(--acc); }
.btn2.danger{ color:#e5484d; padding:11px 12px; background:transparent; border-color:transparent; opacity:.55; }
.btn2.danger:hover{ opacity:1; }
/* 조종실 헤더 + IBL이란 설명 */
.dash-head{ display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.dash-titles{ min-width:0; }
.dash-title{ font-size:17px; font-weight:700; color:var(--txt); }
.dash-sub{ font-size:11px; color:var(--dim); margin-top:2px; }
.dash-btns{ display:flex; gap:7px; flex-shrink:0; }
.dash-btn{ padding:7px 13px; border:1px solid var(--line); background:var(--bg2); color:var(--dim); border-radius:999px; font-size:12.5px; font-weight:600; transition:all .15s; }
.dash-btn:hover{ border-color:var(--acc); color:var(--txt); }
.dash-btn.on{ background:var(--acc); border-color:var(--acc); color:#fff; }
.about{ background:var(--bg2); border:1px solid var(--line); border-radius:12px; padding:15px 16px; margin-bottom:14px; font-size:13px; line-height:1.6; color:var(--txt); }
.about p{ margin:0 0 8px; }
.about b{ color:#292524; font-weight:700; }
.about .about-h{ font-size:15px; font-weight:700; color:var(--acc2); margin-bottom:8px; }
.about .about-sec{ font-size:12.5px; font-weight:700; color:var(--txt); margin:14px 0 6px; padding-top:11px; border-top:1px solid var(--line); }
.about ul{ margin:6px 0 8px; padding-left:18px; }
.about li{ margin-bottom:3px; }
.about code{ font-family:'SF Mono',Menlo,monospace; font-size:11.5px; background:var(--bg); color:#9A3412; padding:1px 5px; border-radius:5px; }
.about .about-dim{ color:var(--dim); font-size:12px; }
.about .about-code{ font-family:'SF Mono',Menlo,monospace; font-size:12px; background:var(--bg); color:#9A3412; border:1px solid var(--line); border-radius:8px; padding:9px 11px; margin:6px 0 4px; word-break:break-all; }
.btn2.danger:hover{ border-color:#e5484d; }
.ap-newbtn{ width:100%; padding:13px; margin:2px 0 6px; border:1px dashed var(--line); background:transparent; color:var(--acc); border-radius:11px; font-weight:600; font-size:14px; cursor:pointer; }
.ap-newbtn:hover{ border-color:var(--acc); background:var(--bg2); }
.ap-form{ display:flex; flex-direction:column; gap:6px; padding:4px; }
.ap-form label{ font-size:12px; color:var(--dim); margin-top:8px; }
.ap-form input,.ap-form textarea,.ap-form select{ padding:11px 12px; border:1px solid var(--line); background:var(--bg2); color:var(--txt); border-radius:10px; font-size:14px; font-family:inherit; }
.ap-form-row{ display:flex; gap:8px; margin-top:14px; }
.ap-form-row .btn2,.ap-form-row .go{ flex:1; }
.btn2.prim{ background:var(--acc-grad); border-color:transparent; color:#fff; box-shadow:0 3px 10px rgba(233,69,96,.25); }
.btn2.prim:hover{ filter:brightness(1.08); }
.btn2:disabled{ opacity:.5; }
/* 둘러보기 팔레트 */
.palette{ margin-top:18px; border-top:1px solid var(--line); padding-top:14px; }
.cat-node{ margin-bottom:10px; }
.cat-node h4{ font-size:12px; color:var(--acc2); margin-bottom:5px; }
.act-chip{ display:inline-block; margin:3px 4px 0 0; padding:5px 10px; background:var(--bg3); border:1px solid var(--line); border-radius:8px; font-size:12px; }
.act-chip:hover{ border-color:var(--acc); }

/* === 앱 === */
.grid{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
.tile{ background:var(--bg2); color:var(--txt); border:1px solid var(--line); border-radius:16px; padding:16px 8px 13px; display:flex; flex-direction:column; align-items:center; gap:7px; box-shadow:var(--shadow); transition:border-color .15s, transform .1s; }
.tile:hover{ border-color:var(--acc); transform:translateY(-2px); }
.tile:active{ transform:scale(.96); }
.tile .em{ font-size:28px; }
.tile .nm{ font-size:12.5px; font-weight:600; color:var(--dim); }
.tile:hover .nm{ color:var(--txt); }
.fileov{ position:fixed; inset:0; z-index:1000; background:var(--bg); display:flex; flex-direction:column; }
.fileov-bar{ display:flex; align-items:center; justify-content:space-between; gap:10px; padding:8px 12px; background:var(--bg2); border-bottom:1px solid var(--line); color:var(--txt); font-size:13px; flex-shrink:0; }
.fileov iframe{ flex:1; border:none; width:100%; background:#fff; }
.inst-head{ display:flex; align-items:center; gap:10px; margin-bottom:14px; }
.back{ background:var(--bg3); border:1px solid transparent; color:var(--txt); width:34px; height:34px; border-radius:10px; font-size:16px; }
.back:hover{ border-color:var(--acc); color:var(--acc2); }
.inst-head h2{ font-size:17px; }
.tabs{ display:flex; gap:6px; margin-bottom:12px; flex-wrap:wrap; }
.tab{ padding:8px 15px; background:var(--bg2); border:1px solid var(--line); border-radius:999px; font-size:13px; font-weight:600; color:var(--dim); }
.tab.on{ background:var(--acc-soft); border-color:rgba(217,119,6,.45); color:#92400E; }
.calgrid{ display:grid; grid-template-columns:repeat(7,1fr); gap:3px; margin-top:10px; }
.calwd{ text-align:center; font-size:11px; color:var(--dim); padding:4px 0; }
.calday{ position:relative; aspect-ratio:1; display:flex; align-items:center; justify-content:center; font-size:14px; border-radius:8px; background:var(--bg2); cursor:pointer; }
.calday.calhas{ font-weight:700; }
.calday.calsel{ background:var(--acc); color:#fff; }
.caldot{ position:absolute; bottom:5px; left:50%; transform:translateX(-50%); width:5px; height:5px; border-radius:50%; background:var(--acc); }
.calday.calsel .caldot{ background:#fff; }
.calpanel{ margin-top:12px; border-top:1px solid var(--line); padding-top:10px; }
.lmaptoggle{ position:absolute; top:10px; right:10px; z-index:500; background:rgba(255,255,255,.92); color:var(--txt); border:1px solid var(--line); border-radius:18px; padding:7px 14px; font-size:13px; font-weight:600; box-shadow:0 2px 8px rgba(74,64,53,.15); }
.lmaptoggle.on{ background:var(--acc); border-color:var(--acc); }
.lmapsearch{ position:absolute; top:10px; left:50%; transform:translateX(-50%); z-index:500; background:#fff; color:#333; border:1px solid var(--line); border-radius:18px; padding:7px 14px; font-size:13px; font-weight:600; box-shadow:0 2px 8px rgba(0,0,0,.25); cursor:pointer; }
.chips{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:12px; }
.chip{ padding:6px 12px; background:var(--bg2); border:1px solid var(--line); border-radius:20px; font-size:12px; }
.filters{ display:flex; gap:6px; flex-wrap:wrap; }
.fchip{ padding:5px 12px; background:var(--bg2); border:1px solid var(--line); border-radius:8px; font-size:12px; color:var(--dim); }
.fchip.on{ background:var(--acc); border-color:var(--acc); color:#fff; }
.chip:hover{ border-color:var(--acc); }
.bookcard{ display:flex; gap:12px; }
.bookcard img{ width:56px; height:80px; object-fit:cover; border-radius:6px; background:var(--bg3); flex-shrink:0; }
.card .t{ font-weight:600; font-size:14px; margin-bottom:3px; }
.card .m{ font-size:12px; color:var(--dim); line-height:1.5; }
.posters{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
.poster{ min-width:0; }
.poster img{ width:100%; aspect-ratio:3/4; object-fit:cover; border-radius:8px; background:var(--bg3); cursor:pointer; }
.poster .t{ font-size:13px; font-weight:600; margin-top:6px; }
.poster .m{ font-size:11px; color:var(--dim); margin-top:2px; }
.kv{ display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid var(--line); font-size:13px; }
.kv .k{ color:var(--dim); }
.big{ font-size:30px; font-weight:700; }
.note{ font-size:11px; color:#92400E; background:rgba(217,119,6,.08); border-radius:8px; padding:8px 10px; margin-bottom:12px; }
/* 메신저/커뮤니티: 대화 버블(thread) + 작성바(compose) */
.thread{ display:flex; flex-direction:column; gap:6px; padding:4px 0 2px; }
.tmsg{ display:flex; flex-direction:column; align-items:flex-start; }
.tmsg.me{ align-items:flex-end; }
.tbub{ max-width:78%; padding:9px 13px; border-radius:14px; border-bottom-left-radius:4px; font-size:14px; line-height:1.5; white-space:pre-wrap; word-break:break-word; background:var(--bg2); border:1px solid var(--line); }
.tmsg.me .tbub{ background:var(--acc); border-color:var(--acc); color:#fff; border-bottom-left-radius:14px; border-bottom-right-radius:4px; }
.tfoot{ font-size:10px; color:var(--dim); margin-top:2px; padding:0 5px; }
/* blocks: 문서 IR 렌더(.docv) — heading/list/table/quote/code/divider/image */
.docv{ line-height:1.65; }
.docv .dh{ font-weight:700; margin:14px 0 6px; }
.docv .dh1{ font-size:20px; }
.docv .dh2{ font-size:17px; border-bottom:1px solid var(--line); padding-bottom:4px; }
.docv .dh3{ font-size:15px; }
.docv .dh4,.docv .dh5,.docv .dh6{ font-size:13.5px; }
.docv .dp,.docv li{ font-size:13.5px; white-space:pre-wrap; word-break:break-word; margin:6px 0; }
.docv ul,.docv ol{ padding-left:20px; margin:6px 0; }
.docv .dq{ border-left:3px solid var(--line); margin:8px 0; padding:2px 10px; color:var(--dim); white-space:pre-wrap; }
.docv .dq cite{ display:block; font-size:11px; margin-top:4px; }
.docv .dcode{ background:var(--bg3); border-radius:8px; padding:10px; font-size:12px; overflow-x:auto; }
.docv .dhr{ border:none; border-top:1px solid var(--line); margin:12px 0; }
.docv table.dtab{ border-collapse:collapse; font-size:13px; }
.docv table.dtab th,.docv table.dtab td{ border:1px solid var(--line); padding:5px 9px; text-align:left; }
.docv .dfig img{ max-width:100%; border-radius:8px; }
.docv .dfig figcaption{ font-size:11px; color:var(--dim); text-align:center; margin-top:4px; }
.docv code{ background:var(--bg3); padding:1px 4px; border-radius:4px; font-size:0.9em; }
.docv a{ color:var(--acc); }
.composebar{ position:sticky; bottom:0; display:flex; gap:8px; padding:10px 0 6px; margin-top:8px; background:linear-gradient(transparent,var(--bg) 35%); }
.composebar .field{ border-radius:22px; }
.composebar .go{ border-radius:22px; }
/* master-detail 반응형(메신저): 넓으면 2분할(리스트+상세), 좁으면 드릴(리스트↔상세 토글) */
.mdsplit{ display:flex; flex-direction:column; gap:10px; }
.mddetail{ display:flex; flex-direction:column; min-width:0; }
.mdph{ flex:1; display:flex; align-items:center; justify-content:center; color:var(--dim); font-size:13px; padding:40px 0; }
@media(min-width:760px){
  .mdsplit{ flex-direction:row; height:calc(100vh - 250px); }
  .mdlist{ width:258px; flex-shrink:0; overflow-y:auto; padding-right:6px; }
  .mddetail{ flex:1; border-left:1px solid var(--line); padding-left:14px; overflow-y:auto; }
  .mdback{ display:none; }
}
@media(max-width:759px){
  .mdsplit.has-detail .mdlist{ display:none; }
  .mdsplit:not(.has-detail) .mddetail{ display:none; }
}
a{ color:var(--info); }
@media(max-width:560px){
  .grid{ grid-template-columns:repeat(3,1fr); }
  .surf-tab .hint{ display:none; }
}
/* === 포식(검색) 브라우저 — 폰/원격 표면. 데스크탑 Electron ForageBrowser 의 검색→판→진입 루프를
      네이티브 코드 없이 재현: 후보 진입은 시스템 브라우저로 위임(런처 WebView 는 판을 든 채 뒤에 남음).
      그리드/썸네일은 생략(리스트만) — 폰 스코프. === */
.fg-wrap{ padding:12px 14px; display:flex; flex-direction:column; gap:10px; height:100%; box-sizing:border-box; }
.fg-search{ display:flex; gap:6px; }
.fg-search input{ flex:1; padding:11px 13px; background:var(--bg2); border:1px solid var(--line); border-radius:10px; color:var(--txt); font-size:14px; }
.fg-search button{ padding:0 16px; background:var(--acc); border:none; border-radius:10px; color:#fff; font-weight:600; font-size:14px; }
.fg-search button:disabled{ opacity:.5; }
.fg-subnav{ display:flex; gap:6px; }
.fg-subnav button{ flex:1; padding:7px; background:var(--bg2); border:1px solid var(--line); border-radius:8px; color:var(--dim); font-size:12px; font-weight:600; }
.fg-subnav button.on{ background:var(--acc); border-color:var(--acc); color:#fff; }
.fg-list{ flex:1; overflow-y:auto; display:flex; flex-direction:column; gap:8px; padding-bottom:8px; }
.fg-intro{ font-size:12px; color:var(--dim); line-height:1.5; padding:2px 2px 4px; }
.fg-card{ background:var(--bg2); border:1px solid var(--line); border-radius:11px; padding:11px 12px; display:flex; flex-direction:column; gap:4px; }
.fg-card.pinned{ border-color:var(--acc); }
.fg-card.excluded{ opacity:.4; }
.fg-card .t{ font-size:14px; font-weight:600; color:var(--info); }
.fg-card .r{ font-size:12px; color:var(--dim); line-height:1.45; }
.fg-card .u{ font-size:10px; color:var(--dim); opacity:.55; word-break:break-all; }
.fg-card .acts{ display:flex; gap:6px; margin-top:5px; }
.fg-card .acts button{ padding:6px 10px; background:var(--bg); border:1px solid var(--line); border-radius:7px; color:var(--dim); font-size:12px; }
.fg-card .acts .go{ flex:1; color:var(--info); font-weight:600; }
.fg-card .acts .pin.on{ color:var(--acc); border-color:var(--acc); }
.fg-more{ padding:11px; background:var(--bg2); border:1px dashed var(--line); border-radius:10px; color:var(--dim); font-size:13px; text-align:center; }
.fg-empty{ padding:34px 14px; text-align:center; color:var(--dim); font-size:13px; line-height:1.7; }
.fg-row{ display:flex; align-items:center; gap:8px; padding:9px 11px; background:var(--bg2); border:1px solid var(--line); border-radius:9px; }
.fg-row .rx{ flex:1; min-width:0; }
.fg-row .rx .rt{ font-size:13px; color:var(--info); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.fg-row .rx .ru{ font-size:10px; color:var(--dim); opacity:.6; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.fg-row .rd{ color:var(--dim); font-size:16px; padding:2px 8px; }
.fg-row .rprev{ font-size:11px; color:var(--dim); }

/* === 공유창고 (레벨별 폴더 관리 — 원격 리모컨) === */
.wh-head{ display:flex; align-items:center; flex-wrap:wrap; gap:8px; padding:11px 14px; background:var(--bg2); border-bottom:1px solid var(--line); flex-shrink:0; }
.wh-title{ font-weight:700; font-size:15px; white-space:nowrap; }
.wh-url{ font-size:11px; color:var(--dim); text-decoration:none; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:180px; }
.wh-url:hover{ color:var(--acc); }
.wh-busy{ font-size:12px; color:var(--dim); }
.wh-add{ display:inline-flex; align-items:center; padding:8px 13px; background:var(--acc-grad); color:#fff; border-radius:10px; font-size:13px; font-weight:600; cursor:pointer; white-space:nowrap; }
.wh-add:hover{ filter:brightness(1.08); }
.wh-levels{ display:flex; gap:6px; flex-wrap:wrap; padding:10px 14px; background:var(--bg2); border-bottom:1px solid var(--line); flex-shrink:0; }
.wh-lv{ display:flex; align-items:center; gap:6px; padding:7px 12px; background:var(--bg); border:1px solid var(--line); border-radius:999px; color:var(--dim); font-size:12px; font-weight:600; }
.wh-lv.on{ background:var(--acc); border-color:var(--acc); color:#fff; }
.wh-lv .cnt{ padding:1px 7px; border-radius:999px; background:var(--bg3); color:var(--dim); font-size:11px; }
.wh-lv.on .cnt{ background:rgba(255,255,255,.25); color:#fff; }
.wh-err{ margin:10px 14px 0; padding:9px 12px; background:rgba(220,38,38,.07); border:1px solid rgba(220,38,38,.3); border-radius:9px; color:#B91C1C; font-size:12px; }
.wh-list{ flex:1; overflow-y:auto; padding:12px 14px; display:flex; flex-direction:column; gap:8px; }
.wh-item{ display:flex; align-items:center; gap:11px; padding:9px 11px; background:var(--bg2); border:1px solid var(--line); border-radius:11px; }
.wh-item img,.wh-item .ic{ width:42px; height:42px; border-radius:8px; flex-shrink:0; object-fit:cover; background:var(--bg3); display:flex; align-items:center; justify-content:center; font-size:20px; }
.wh-item .op{ text-decoration:none; color:inherit; display:block; flex-shrink:0; }
.wh-item .op:hover .nm{ color:var(--info); text-decoration:underline; }
.wh-item .tx{ flex:1; min-width:0; }
.wh-item .tx .nm{ font-size:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.wh-item .tx .mt{ font-size:11px; color:var(--dim); margin-top:2px; }
.wh-item .dl{ color:var(--dim); text-decoration:none; font-size:16px; padding:4px 8px; flex-shrink:0; }
.wh-item .dl:hover{ color:var(--info); }
.wh-item .rm{ background:none; border:none; color:var(--dim); font-size:16px; padding:4px 8px; flex-shrink:0; }
.wh-item .rm:hover{ color:var(--acc); }
/* 폴더 = 접이식. 창고 안 상대경로를 트리로 되접어 보여준다(데스크탑 WarehouseView 와 같은 모양). */
.wh-fd{ background:var(--bg2); border:1px solid var(--line); border-radius:11px; }
.wh-fd>summary{ display:flex; align-items:center; gap:11px; padding:9px 11px; cursor:pointer; list-style:none; }
.wh-fd>summary::-webkit-details-marker{ display:none; }
.wh-fd>summary .tw{ color:var(--dim); font-size:11px; flex-shrink:0; transition:transform .12s; }
.wh-fd[open]>summary .tw{ transform:rotate(90deg); }
.wh-fd>summary .ic{ width:42px; height:42px; border-radius:8px; flex-shrink:0; background:var(--bg3); display:flex; align-items:center; justify-content:center; font-size:20px; }
.wh-fd>summary .tx{ flex:1; min-width:0; }
.wh-fd>summary .tx .nm{ font-size:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.wh-fd>summary .tx .mt{ font-size:11px; color:var(--dim); margin-top:2px; }
.wh-fd>.kids{ display:flex; flex-direction:column; gap:8px; padding:0 10px 10px 22px; margin-left:20px; border-left:1px solid var(--line); }
.wh-fd .wf-more{ font-size:11px; color:var(--dim); padding:2px 4px; }
.wh-empty{ padding:44px 14px; text-align:center; color:var(--dim); font-size:13px; line-height:1.7; }
/* 공유창고 — 이웃 탭 (창고 피드) */
.wh-tabs{ display:flex; gap:3px; background:var(--bg3); border-radius:9px; padding:3px; margin-left:6px; }
.wh-tabs button{ border:none; background:transparent; color:var(--dim); font-size:12px; font-weight:600; padding:6px 12px; border-radius:7px; }
.wh-tabs button.on{ background:var(--bg2); color:var(--acc); }
.wh-nb-bar{ display:flex; gap:6px; flex-wrap:wrap; align-items:center; padding:10px 14px; background:var(--bg2); border-bottom:1px solid var(--line); }
.wh-chip{ display:inline-flex; align-items:center; gap:6px; padding:6px 10px; background:var(--bg); border:1px solid var(--line); border-radius:999px; font-size:12px; }
.wh-chip a{ color:var(--txt); text-decoration:none; font-weight:600; }
.wh-chip a:hover{ color:var(--info); text-decoration:underline; }
.wh-chip .cnt{ color:var(--dim); font-size:11px; }
.wh-chip .err{ color:#B91C1C; font-size:11px; }
.wh-chip button{ background:none; border:none; color:var(--dim); font-size:11px; padding:0 2px; }
.wf-go{ background:var(--acc); color:#fff; border:none; border-radius:8px; font-size:12px; font-weight:600; padding:7px 12px; }
.wf-row{ display:flex; gap:6px; padding:8px 14px; background:var(--bg2); border-bottom:1px solid var(--line); flex-wrap:wrap; }
.wf-row input,.wf-row select{ background:var(--bg); border:1px solid var(--line); border-radius:8px; color:var(--txt); font-size:12px; padding:7px 9px; }
.wf-row input.grow{ flex:1; min-width:180px; }
.wf-kind{ font-size:10px; padding:1px 5px; border-radius:5px; background:var(--bg3); color:var(--acc); margin-right:5px; }
</style>
</head>
<body>

<!-- 로그인 -->
<div class="login" id="login">
  <div class="login-box">
    <h1>IndieBiz OS</h1>
    <p class="sub">Remote Launcher</p>
    <input type="password" class="inp" id="pw" placeholder="비밀번호" autocomplete="current-password">
    <button class="btn" id="loginBtn" onclick="doLogin()">로그인</button>
    <p class="err" id="loginErr"></p>
  </div>
</div>

<!-- 앱 -->
<div class="app" id="app">
  <div class="top">
    <div class="brand"><span>IndieBiz OS</span><span class="badge" id="surfBadge">REMOTE</span></div>
    <div style="display:flex; gap:8px;" id="headerActions">
      <button class="iconbtn" onclick="refreshSurface()" title="새로고침">↻</button>
      <button class="iconbtn" onclick="doLogout()" title="로그아웃">⏻</button>
    </div>
  </div>
  <div class="surfaces">
    <button class="surf-tab on" id="t-autopilot" onclick="setSurface('autopilot')">
      <span class="em">🛰️</span><span>자율주행</span><span class="hint">속도·표현력</span></button>
    <button class="surf-tab" id="t-manual" onclick="setSurface('manual')">
      <span class="em">⚙️</span><span>조종실</span><span class="hint">표현력·주권</span></button>
    <button class="surf-tab" id="t-app" onclick="setSurface('app')">
      <span class="em">📱</span><span>앱</span><span class="hint">속도·주권</span></button>
    <button class="surf-tab" id="t-warehouse" onclick="setSurface('warehouse')">
      <span class="em">📦</span><span>공유창고</span><span class="hint">레벨·공개</span></button>
  </div>

  <!-- 자율주행 — 드릴다운: ① 대상 선택(시스템AI/스위치/프로젝트→에이전트) → ② 대화/결과 -->
  <div class="panel on" id="p-autopilot">
    <!-- ① 대상 브라우저 (루트 ↔ 프로젝트 에이전트 드릴) -->
    <div class="ap-browse" id="ap-browse">
      <div class="ap-bhead" id="ap-bhead" style="display:none">
        <button class="back" onclick="apBrowseRoot()">←</button>
        <h2 id="apBrowseTitle"></h2>
      </div>
      <div id="apBrowse"></div>
    </div>
    <!-- ② 대화 / 결과 (전체 폭) -->
    <div class="ap-chat" id="ap-chat" style="display:none">
      <div class="ap-head">
        <button class="back" onclick="apExitChat()">←</button>
        <div class="ap-head-t"><h2 id="apTitle">시스템 AI</h2><p id="apSub"></p></div>
      </div>
      <div class="msgs" id="apMsgs"></div>
      <div class="composer" id="apComposer">
        <textarea id="apInput" rows="1" placeholder="메시지..." onkeydown="apKey(event)"></textarea>
        <button class="go" id="apSend" onclick="apSend()">전송</button>
      </div>
    </div>
  </div>

  <!-- 조종실 (구 계기판) -->
  <div class="panel" id="p-manual">
    <div class="wrap">
      <!-- 조종실 헤더 — IBL 사전 / IBL이란? -->
      <div class="dash-head">
        <div class="dash-titles">
          <div class="dash-title">조종실</div>
          <div class="dash-sub">자연어를 IBL로 번역·검수해 실행합니다</div>
        </div>
        <div class="dash-btns">
          <button class="dash-btn" id="btnDict" onclick="togglePalette()">📖 IBL 사전</button>
          <button class="dash-btn" id="btnAbout" onclick="toggleAbout()">❔ IBL이란?</button>
        </div>
      </div>
      <!-- IBL이란? 설명 -->
      <div id="mAbout" class="about" style="display:none">
        <div class="about-h">IBL (IndieBiz Logic)</div>
        <p>indiebizOS의 <b>신경계 역할을 하는 언어</b>. 세 가지로 이루어집니다 — <b>어휘</b>(조합 가능한 액션) · <b>문법</b>(쓰고 잇는 규칙) · <b>통화</b>(흐르는 데이터).</p>
        <div class="about-sec">어휘 — 무엇을 할 수 있나</div>
        <p>액션 하나가 IBL이 할 수 있는 일 하나. 예: <code>[sense:weather]</code>. 대상에 따라 <b>6개 노드</b>로 나뉩니다.</p>
        <ul>
          <li><code>sense</code> 감각 — 바깥 정보 수집·검색 (날씨·주가·뉴스·웹)</li>
          <li><code>self</code> 자기 — 내 기억·파일·설정·일정</li>
          <li><code>limbs</code> 손발 — 기기·도구 조작 (브라우저·화면·음악·폰)</li>
          <li><code>others</code> 관계 — 이웃·위임·메시징</li>
          <li><code>engines</code> 엔진 — 미디어 생성 (문서·슬라이드·영상·이미지)</li>
          <li><code>table</code> 표 — 통화 변환 문법 (필터·정렬·집계·조인·차트)</li>
        </ul>
        <p class="about-dim">액션은 셋 중 하나를 합니다 — <b>생성</b>(통화를 낸다) · <b>변환</b>(통화를 바꾼다) · <b>행동</b>(세상에 작용).</p>
        <div class="about-sec">문법 — 어떻게 쓰고 잇나</div>
        <div class="about-code">[node:action]{params}</div>
        <ul>
          <li>값은 <code>{key: 값}</code>. 예: <code>[sense:weather]{city:"수원"}</code></li>
          <li>한 액션 안의 변형은 <code>op</code> 로: <code>{op:"query"}</code></li>
          <li>잇기 — <code>&gt;&gt;</code> 순차(앞 결과를 뒤로) · <code>&amp;</code> 병렬 · <code>??</code> 폴백</li>
        </ul>
        <div class="about-sec">통화 — 무엇이 흐르나</div>
        <p>통화는 단 하나, <b>items</b> — 열린 항목들의 목록. 한 액션의 결과가 다음으로 <code>&gt;&gt;</code> 흐릅니다. 이게 IBL을 낱말이 아니라 <b>문장</b>으로 만듭니다.</p>
        <p class="about-dim"><b>변환자</b>(통화를 받아 통화를 냄): <code>filter · sort · take · select · dedup · groupby · join · union · merge</code></p>
        <div class="about-code">[sense:realty]{region:"강남구"} &gt;&gt; sort &gt;&gt; take{n:3}</div>
      </div>
      <!-- IBL 사전(액션 팔레트) -->
      <div id="palette" class="palette" style="display:none"></div>
      <!-- 다른 몸(피어) 연결상태 — 폰이면 맥, 맥-원격이면 폰 -->
      <div id="peerStatus" style="display:none"></div>
      <!-- 모델 기어 — 계기판 변속 레버 (절약/균형/최대) + 설정(프리셋·핀) -->
      <div id="gearLever" class="card" style="display:none"></div>
      <div class="step">
        <div class="step-label">① 의도 (자연어)</div>
        <div class="row">
          <input class="field" id="mIntent" placeholder='예: 서울 날씨 알려줘 / 강남구 아파트 실거래가' onkeydown="if(event.key==='Enter')mTranslate()">
          <button class="go" id="mTransBtn" onclick="mTranslate()">번역</button>
        </div>
      </div>
      <div id="mAfterTranslate" style="display:none">
        <div class="step">
          <div class="step-label">② IBL 코드 (수정 가능)</div>
          <textarea class="codebox" id="mCode"></textarea>
          <button class="linkbtn" onclick="toggleRefs()">참고 용례 보기/숨기기</button>
          <div class="refbox" id="mRefs"></div>
        </div>
        <div class="btnrow">
          <button class="btn2 prim" id="mValBtn" onclick="mValidate()">검수 (dry-run)</button>
        </div>
      </div>
      <div id="mAfterValidate" style="display:none">
        <div class="step" style="margin-top:16px">
          <div class="step-label">③ 효과 검수 — 코드가 아니라 무슨 일이 일어나는지</div>
          <div id="mSteps"></div>
        </div>
        <div id="mSideWarn"></div>
        <div class="btnrow">
          <button class="btn2 prim" id="mExecBtn" onclick="mExecute()">실행</button>
        </div>
      </div>
      <div id="mAfterExecute" style="display:none">
        <div class="step" style="margin-top:16px">
          <div class="step-label">④ 결과</div>
          <div class="result" id="mResult"></div>
          <div class="btnrow" style="margin-top:10px">
            <button class="btn2" id="mDistillBtn" onclick="mDistill()">✓ 이 결과 학습 (해마 증류)</button>
          </div>
          <p class="muted" id="mDistillMsg" style="margin-top:8px"></p>
        </div>
      </div>
    </div>
  </div>

  <!-- 앱 -->
  <div class="panel" id="p-app">
    <div class="wrap" id="appHome"></div>
    <div class="wrap" id="appInst" style="display:none"></div>
  </div>

  <!-- 포식(검색) 브라우저 — 앱모드의 앱(표면 탭 아님, 홈 그리드 타일로 진입).
       검색 → 후보판 → 진입(시스템 브라우저) → 판 유지 + ✕제외/📌담기 -->
  <div class="panel" id="p-forage">
    <div class="fg-wrap">
      <div class="inst-head" style="margin-bottom:0">
        <button class="back" onclick="history.back()">←</button>
        <h2>🔍 검색 브라우저</h2>
      </div>
      <div class="fg-search">
        <input id="fgQ" type="text" placeholder="무엇을 찾을까요?" autocomplete="off"
          onkeydown="if(event.key==='Enter')fgSearch()">
        <button id="fgGo" onclick="fgSearch()">포식</button>
      </div>
      <div class="fg-subnav">
        <button id="fgnav-board" class="on" onclick="fgNav('board')">판</button>
        <button id="fgnav-history" onclick="fgNav('history')">방문기록</button>
        <button id="fgnav-library" onclick="fgNav('library')">도서관</button>
      </div>
      <div class="fg-list" id="fgList"></div>
    </div>
  </div>

  <!-- 공유창고 — 레벨(0 손님~4 가족)별 폴더. 원격은 파일을 업로드로 넣고(맥은 드롭/선택),
       빼기=휴지통 이동(가역). 소유자 리모컨: 로그인 세션으로 warehouse-admin 도달. -->
  <div class="panel" id="p-warehouse">
    <div class="wh-head">
      <span class="wh-title" id="whTitle">공유창고</span>
      <a class="wh-url" id="whUrl" href="#" target="_blank" rel="noopener" style="display:none"></a>
      <span class="wh-tabs">
        <button id="whTabMine" class="on" onclick="whTab('mine')">내 창고</button>
        <button id="whTabNb" onclick="whTab('nb')">이웃</button>
      </span>
      <span style="flex:1"></span>
      <span class="wh-busy" id="whBusy"></span>
      <label class="wh-add" id="whAddBtn">
        <input type="file" id="whFile" multiple style="display:none" onchange="whUpload(this.files)">＋ 파일 올리기</label>
      <!-- 브라우저는 폴더를 통째로 못 보낸다 — webkitdirectory 로 안의 파일을 전부 받아
           각 파일의 webkitRelativePath(하위 경로)를 붙여 올린다(맥은 add 가 통째 복사). -->
      <label class="wh-add" id="whAddDirBtn">
        <input type="file" id="whDir" webkitdirectory directory multiple style="display:none" onchange="whUpload(this.files)">＋ 폴더 올리기</label>
      <button class="iconbtn" title="새로고침" onclick="whRefresh()">↻</button>
    </div>
    <div id="whMine">
      <div class="wh-levels" id="whLevels"></div>
      <div class="wh-err" id="whErr" style="display:none"></div>
      <div class="wh-list" id="whList"></div>
    </div>
    <div id="whNb" style="display:none">
      <div class="wh-nb-bar" id="wfNeighbors"></div>
      <div class="wf-row" id="wfAddRow" style="display:none">
        <select id="wfCand"><option value="">새 이웃으로…</option></select>
        <input id="wfName" placeholder="이웃 이름 (비우면 창고 제목)">
        <input id="wfUrl" class="grow" placeholder="창고 주소 (https://…)">
        <button class="wf-go" onclick="wfAdd()">등록</button>
      </div>
      <div class="wf-row">
        <input id="wfQ" class="grow" placeholder="🔍 이웃 창고 전체에서 파일 이름으로 찾기" oninput="wfSearch(this.value)">
      </div>
      <div class="wh-err" id="wfErr" style="display:none"></div>
      <div class="wh-list" id="wfFeed"></div>
    </div>
  </div>
</div>

"""
