"""공용 렌더 코어(backend/static/app_render_core.js)를 런처 <script> 안에 인라인.

앱 표면 렌더 어휘의 *순수 로직*은 표면이 둘이어도 하나여야 한다 — 정본은 그 .js 파일이고
데스크탑은 Vite 로 import, 원격·폰 표면은 여기서 읽어 붙인다.

원격 셸은 고전 <script>(모듈 아님)라 `export` 문이 들어가면 SyntaxError 다 → 파일 **맨 끝의
export 블록만** 떼고 나머지를 그대로 쓴다. 함수 선언은 스크립트 전체에서 호이스팅되므로
조립 순서와 무관하게 다른 조각들이 부를 수 있다.

★손복사 금지: 여기서 하는 일은 '읽어서 한 블록 제거'뿐이다. 로직을 파이썬 문자열로 다시
  적는 순간 우리가 없애려던 이중 구현이 돌아온다(scripts/check_render_core.py 가 감시).
"""

from surface_assets import read_asset



# 파일 맨 끝 ESM export 블록의 시작 마커 — 코어 .js 의 마지막 블록이며 그 위엔 export 가 없다.
EXPORT_MARKER = "/* --- ESM export"


def strip_esm_export(text: str) -> str:
    """코어 .js 본문에서 맨 끝 ESM export 블록을 떼어 고전 스크립트용 본문을 만든다.

    마커가 없으면 원문 그대로(방어) — 대신 load_core_js 가 export 잔재를 검사한다.
    """
    idx = text.rfind(EXPORT_MARKER)
    if idx < 0:
        return text
    return text[:idx].rstrip() + "\n"


def load_core_js() -> str:
    """선택된 화면 판본의 코어를 고전 스크립트로 읽는다."""
    body = strip_esm_export(read_asset('static/app_render_core.js'))
    if "\nexport " in body or body.startswith("export "):
        raise RuntimeError(
            "app_render_core.js 에 맨 끝 블록 밖의 `export` 가 있습니다 — 고전 <script> 에서 "
            "SyntaxError 가 됩니다. export 는 파일 마지막 블록 하나로만."
        )
    return "\n/* ===== 공용 렌더 코어 (backend/static/app_render_core.js — 데스크탑과 단일 소스) ===== */\n" + body


def __getattr__(name):
    if name != "LAUNCHER_CORE_JS":
        raise AttributeError(name)
    return load_core_js()


def load_conversation_js():
    """JSON 구성과 순수 동작을 React와 동일한 정본에서 고전 스크립트로 조립."""
    source = strip_esm_export(read_asset('shared/conversation.js'))
    return source.replace("import conversationHeader from './conversation.json';",
                          'var conversationHeader=' + read_asset('shared/conversation.json') + ';', 1)
