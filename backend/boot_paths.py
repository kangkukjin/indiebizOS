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
