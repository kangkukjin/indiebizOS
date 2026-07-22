"""폰네이티브 표면 조립 — 독립된 몸의 자기 UI (자율주행·조종실·앱 3탭).

표면 정의(어떤 탭이 존재하는가=정체)의 거처 — 원격런처(launcher_surface_remote)와 짝.
원격런처는 PC 몸의 얼굴·리모컨이고, 이 표면은 폰 몸 자신의 것 — 라이브러리
(launcher_web_shell/app 조각·launcher_web_render = 기질)는 공유하되 정체는 여기서 조립한다.
2026-07-22 표면 분리 2단계 — docs/SURFACE_SPLIT_HANDOFF.md.

빠진 것(의도):
- 공유창고: 창고=숙주(맥) 몸의 살림+네트워크 얼굴 — 폰에서 창고를 만지려면 원격런처(기능 완비).
- 포식(검색브라우저): 맥 디스크 중심 — 패널도, 홈 그리드 타일도 없다(PHONE_APPHOME_JS).
  launcher_web_render 의 fg* 함수들은 공유 기질에 실려 오지만 진입점이 없어 잠든 코드다.
남은 IS_PHONE 런타임 분기(공통 조각의 부트·클립보드 경로·자율주행 스위치 숨김)는 폰 config
(host=phone-local)로 스스로 참이 되어 그대로 작동한다 — 정적 흡수는 후속 후보.
"""

from launcher_web_shell import (
    SHELL_HEAD_HTML,
    SHELL_PANEL_AUTOPILOT_HTML,
    SHELL_PANEL_MANUAL_HTML,
    SHELL_PANEL_APP_HTML,
    SHELL_TAIL_HTML,
)
from launcher_app_common import LAUNCHER_COMMON_JS
from launcher_app_autopilot import LAUNCHER_AUTOPILOT_JS
from launcher_app_manual import LAUNCHER_MANUAL_JS
from launcher_app_appmode import LAUNCHER_APPMODE_HEAD_JS, LAUNCHER_APPMODE_REST_JS
from launcher_web_render import LAUNCHER_RENDER_JS

# 표면 탭줄 — 폰 3탭 (원격런처 SHELL_SURFACES_HTML 의 부분집합, 창고 버튼 없음)
PHONE_SURFACES_HTML = """  <div class="surfaces">
    <button class="surf-tab on" id="t-autopilot" onclick="setSurface('autopilot')">
      <span class="em">🛰️</span><span>자율주행</span><span class="hint">속도·표현력</span></button>
    <button class="surf-tab" id="t-manual" onclick="setSurface('manual')">
      <span class="em">⚙️</span><span>조종실</span><span class="hint">표현력·주권</span></button>
    <button class="surf-tab" id="t-app" onclick="setSurface('app')">
      <span class="em">📱</span><span>앱</span><span class="hint">속도·주권</span></button>
  </div>
"""

# 표면 토글 — 폰 3탭 변형 (원격런처 LAUNCHER_SETSURFACE_JS 의 짝). 창고·포식 분기 없음.
PHONE_SETSURFACE_JS = """/* ===== 표면 토글 (폰: 3탭 — 창고·포식 없음, launcher_surface_phone 조립) ===== */
function setSurface(s){
  surface=s;
  ['autopilot','manual','app'].forEach(k=>{
    const t=document.getElementById('t-'+k); if(t) t.classList.toggle('on',k===s);
    document.getElementById('p-'+k).classList.toggle('on',k===s);
  });
  if(s==='app' && !appHomeRendered) renderAppHome();
}

"""

# 앱 홈 그리드 — 폰 변형 (원격런처 LAUNCHER_APPHOME_JS 의 짝). 검색브라우저 타일·openForage 없음.
PHONE_APPHOME_JS = """async function renderAppHome(force){
  const home=document.getElementById('appHome');
  home.innerHTML='<div class="center"><div class="spin"></div></div>';
  await loadInstruments(force);
  if(!INSTRUMENTS.length){ home.innerHTML='<p class="muted">계기 매니페스트를 불러오지 못했습니다</p>'; return; }
  home.innerHTML=
    '<p class="muted" style="margin-bottom:12px">직접 조작 — 아이콘을 눌러 바로 실행 (0 토큰)</p>'+
    '<div class="grid">'+INSTRUMENTS.map((inst,ix)=>
      '<button class="tile" onclick="openInstrument('+ix+')"><span class="em">'+esc(inst.icon||'🔧')+'</span><span class="nm">'+esc(inst.name)+'</span></button>'
    ).join('')+
    '</div>';
  appHomeRendered=true;
}
"""


def phone_html() -> str:
    """폰네이티브 표면 HTML — 3탭 마크업 + 3탭 JS 조립."""
    return (
        SHELL_HEAD_HTML
        + PHONE_SURFACES_HTML
        + SHELL_PANEL_AUTOPILOT_HTML
        + SHELL_PANEL_MANUAL_HTML
        + SHELL_PANEL_APP_HTML
        + SHELL_TAIL_HTML
        + LAUNCHER_COMMON_JS
        + PHONE_SETSURFACE_JS
        + LAUNCHER_AUTOPILOT_JS
        + LAUNCHER_MANUAL_JS
        + LAUNCHER_APPMODE_HEAD_JS
        + PHONE_APPHOME_JS
        + LAUNCHER_APPMODE_REST_JS
        + LAUNCHER_RENDER_JS
    )
