"""embedding_guard — 임베딩 추론을 프로세스 안에서 한 줄로 세운다.

PyTorch 의 MPS 백엔드는 여러 스레드가 동시에 연산하면 안전하지 않다. 셰이더 캐시
(`MetalShaderLibrary`)에 잠금이 없어, 아직 컴파일되지 않은 커널을 두 스레드가 함께 처음 부르면
프로세스가 SIGSEGV/SIGBUS 로 죽거나 멈춘다.

2026-10-01 실측: 03:30 에 예약 위임 세 건이 같은 순간에 시작해 각자 연상 회상(인코딩)을 돌렸고,
재기동 직후라 첫 호출이 겹친 09-28·09-30 두 날 백엔드가 죽었다(충돌 보고서의 스택이 같다 —
`mps::copy_cast_kernel_mps → MetalShaderLibrary::exec_unary_kernel`). 격리 재현: 잠금 없이 6스레드
첫 인코딩 5회 중 4회 충돌·1회 멈춤, 잠금을 걸면 6회 모두 정상.

모델이 달라도 캐시는 프로세스에 하나라, 잠금도 프로세스에 하나다. 적재(가중치를 장치로 옮기는 것)도
같은 연산이므로 같은 잠금 안에서 한다. 이 모듈은 torch 를 import 하지 않는다.
"""
import threading

_LOCK = threading.RLock()


def serialize(model):
    """모델의 encode 를 프로세스 잠금으로 감싼다(이미 감쌌으면 그대로). 돌려주는 것은 같은 객체다."""
    inner = getattr(model, "encode", None)
    if inner is None or getattr(model, "_encode_serialized", False):
        return model          # 감쌀 encode 가 없으면(모델 아닌 것) 손대지 않는다 — 적재를 이 모듈이 실패시키지 않는다

    def encode(*args, **kwargs):
        with _LOCK:
            return inner(*args, **kwargs)

    model.encode = encode
    model._encode_serialized = True
    return model


def load(factory):
    """`factory()` 로 모델을 적재하고 encode 를 직렬화해 돌려준다 — 임베딩 모델을 만드는 유일한 길."""
    with _LOCK:
        return serialize(factory())
