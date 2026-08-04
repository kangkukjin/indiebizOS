"""pkg_utils.py — 패키지 형제 모듈 로드 주문의 정본 (2026-08-05 감사 부채 ⑥ 복붙 정리).

importlib spec_from_file_location 4줄 주문이 30여 핸들러에 복붙돼 있던 것의 단일 소스.
캐시·sys.modules 등록은 패키지마다 *의도된* 차이가 있으므로 축으로 노출한다 —
특수 변형(browser-action 의 체인 프리로드 등)은 이 함수를 안에서 쓰되 자기 로직 유지.
"""
import importlib.util
import sys
from pathlib import Path


def load_sibling(anchor_file, module_name, *, cache=None, register=False, module_key=None):
    """anchor_file(호출자 __file__)과 같은 디렉토리의 module_name.py 를 동적 로드.

    - cache: dict 를 주면 이름-키 캐시. ★캐시든 아니든 패키지 tool_*.py 는 /packages/reload
      밖(sys.modules·이 캐시 잔존) — 갱신은 백엔드 재시작 또는 touch (메모리
      package-submodule-reload-gap). None(기본)=매 호출 재로드.
    - register: True 면 sys.modules[module_key or module_name] 에 등록
      (형제 모듈이 일반 import 문으로 이 이름을 참조할 때만 필요).
    """
    if cache is not None and module_name in cache:
        return cache[module_name]
    path = Path(anchor_file).resolve().parent / f"{module_name}.py"
    if not path.exists():
        raise FileNotFoundError(f"형제 모듈을 찾을 수 없습니다: {path}")
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    module = importlib.util.module_from_spec(spec)
    if register:
        sys.modules[module_key or module_name] = module
    spec.loader.exec_module(module)
    if cache is not None:
        cache[module_name] = module
    return module
