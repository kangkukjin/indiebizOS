"""pkg_utils.py — 패키지 형제 모듈 로드 주문의 정본 (2026-08-05 감사 부채 ⑥ 복붙 정리).

importlib spec_from_file_location 4줄 주문이 30여 핸들러에 복붙돼 있던 것의 단일 소스.
캐시·sys.modules 등록은 패키지마다 *의도된* 차이가 있으므로 축으로 노출한다 —
특수 변형(browser-action 의 체인 프리로드 등)은 이 함수를 안에서 쓰되 자기 로직 유지.

## 싱글턴 로더의 import 레이스 (2026-08-05 감사 ⑤ 실측)

`sys.modules[key] = module` 을 `exec_module` **앞**에 두는 주문이 4개 핸들러에 복붙돼
있었다(youtube·radio·cctv·browser-action). 그 순서는 순환 import 를 견디려는 표준
관용구지만, 싱글턴 조회가 `if key in sys.modules: return` 이면 **동시 호출자가 반쯤
만들어진 모듈을 받는다**.

실측: op fixture 를 6-way 병렬로 돌리자 `[sense:video]{op:"history"}` 가
`module 'tool_watch_singleton' has no attribute 'history'` 로 죽었다(같은 순간의 `feed`
는 성공 — 모듈이 feed 까지만 실행된 상태였다). 단독 재실행은 정상이라 **재현이 어려운
부류**다. IBL 은 `&` 병렬 연산자를 1급으로 가지므로 이건 이론적 레이스가 아니다.

→ `load_singleton()` 이 잠금 안에서 이중검사 하고, **완주 표식**(`__ib_loaded__`)이
붙기 전에는 캐시 적중으로 치지 않는다. 실행 중 예외가 나면 sys.modules 에서 지운다
(반쪽 모듈이 프로세스 수명 내내 남아 매 호출을 죽이던 두 번째 함정).
"""
import importlib.util
import sys
import threading
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


# 싱글턴 로드 직렬화. RLock — 모듈 top-level 이 또 다른 형제를 당기는 경우(같은 스레드
# 재진입)를 막지 않기 위해서다.
_SINGLETON_LOCK = threading.RLock()
_LOADED_FLAG = "__ib_loaded__"


def load_singleton(anchor_file, module_name, *, module_key=None):
    """형제 모듈을 **프로세스 1회만** 로드해 sys.modules 에 눌러앉힌다 (재생 프로세스·
    큐 같은 전역 상태를 tool_loader 의 반복 exec_module 너머로 유지하려는 용도).

    옛 복붙 주문과 다른 점 둘 — 둘 다 실측 결함의 수리다(모듈 독스트링 참조):
      ① 조회·생성이 잠금 안이고, **완주 표식이 붙은 모듈만** 캐시 적중으로 친다
         (반쯤 실행된 모듈을 다른 스레드에 넘기지 않는다)
      ② exec 중 예외면 sys.modules 에서 제거 — 반쪽 모듈이 눌러앉지 않는다
    """
    key = module_key or module_name
    mod = sys.modules.get(key)
    if mod is not None and getattr(mod, _LOADED_FLAG, False):
        return mod
    with _SINGLETON_LOCK:
        mod = sys.modules.get(key)
        if mod is not None and getattr(mod, _LOADED_FLAG, False):
            return mod
        path = Path(anchor_file).resolve().parent / f"{module_name}.py"
        if not path.exists():
            raise FileNotFoundError(f"형제 모듈을 찾을 수 없습니다: {path}")
        spec = importlib.util.spec_from_file_location(key, str(path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module      # 순환 import 를 견디려면 exec 앞에 있어야 한다
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(key, None)  # ② 반쪽 모듈을 남기지 않는다
            raise
        setattr(module, _LOADED_FLAG, True)
        return module
