"""boot_paths.py — 층 디렉토리 sys.path 부트스트랩 (2026-08-05 감사 ⑦ 물리 이동).

backend 모듈은 층 디렉토리(base/datastore/ibl/cognition/services/surface)에 물리적으로
살지만, **모듈 이름은 평면을 유지**한다(`import ibl_engine` 그대로) — 41개 패키지의
bare import·폰 번들(zip 안 평면)·해마 코퍼스가 평면 이름을 전제하기 때문. 디렉토리는
층 선언(check_backend_layers 가 위치=선언 일치를 검사)이고, import 해석은 이 모듈이
층 디렉토리를 sys.path 에 올려 해결한다.

사용: backend 를 sys.path 에 넣는 진입점(api.py·스크립트·conftest)이 곧바로
`import boot_paths` — import 자체가 설치(멱등).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# 층 디렉토리 (아래→위). ★"data" 는 런타임 데이터 폴더(backend/data)와 충돌해 datastore.
LAYER_DIRS = ["base", "datastore", "ibl", "cognition", "services", "surface"]


def install() -> None:
    """층 디렉토리를 sys.path 에 등록 (멱등)."""
    for d in LAYER_DIRS:
        p = os.path.join(_HERE, d)
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)


install()


def wire_ledger_syntax_gate() -> None:
    """해마 원장 문(ibl_usage_db)에 구문 검증자를 꽂는다 — 조립 뿌리(composition root)의 배선.

    왜 여기인가(2026-09-02): 원장(datastore)은 파서(ibl 층)를 import 할 수 없고(상향 간선),
    파서 쪽 자기등록은 '누군가 ibl_param_vocab 을 먼저 import 했는가'에 매달려 진입점마다
    한 줄씩 손으로 심어야 했다 — 스크립트 32개에 전개하고도 패키지 설치 경로·프로비전·
    수리 스크립트가 샜다(실측). 규칙은 파생본에 전개하지 않는다: 모든 진입점이 이미
    지나는 이 모듈 한 곳이 배선처다. 층 가드는 boot_paths 를 부트스트랩으로 면제한다.

    지연 배선: 검증자 본체(ibl_param_vocab)는 첫 원장 쓰기 때 import 된다 — 부트 비용 0.
    파서가 없는 몸이면 검증자가 예외를 내고 원장이 쓰기를 거절한다(fail-closed 유지).
    """
    try:
        import ibl_usage_db
    except Exception:
        return  # 원장이 없는 몸이면 꽂을 문도 없다

    def _validator(ibl_code: str):
        from ibl_param_vocab import code_syntax_error
        return code_syntax_error(ibl_code)

    ibl_usage_db.set_code_validator(_validator)


def wire_ledger_signature() -> None:
    """해마 원장 문에 *서명 계산자* 를 꽂는다 — 구문 검증자와 같은 배선처, 같은 이유(2026-09-06).

    이름 붙은 프로그램의 서명은 실행기(`[fn:]` 의 인자 누락 판정)가 정본이다. 표시 쪽이
    `${…}` 정규식으로 따로 세면 갈라지고, 갈라진 서명을 가르치면 가르친 대로 부른 호출이
    거절된다(09-06 실측 10/45). 문에서 한 번 계산해 저장하면 모든 표면이 같은 것을 읽는다.
    """
    try:
        import ibl_usage_db
    except Exception:
        return

    def _signature(ibl_code: str):
        from workflow_contract import call_signature
        return call_signature(ibl_code)

    ibl_usage_db.set_signature_computer(_signature)


wire_ledger_syntax_gate()
wire_ledger_signature()
