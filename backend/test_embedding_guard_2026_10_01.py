"""임베딩 추론은 프로세스에서 한 줄로 — 직렬화 계약과 "모든 적재 자리가 이 길을 지난다"는 관문.

2026-10-01: 예약 위임 세 건이 동시에 첫 인코딩을 돌려 MPS 셰이더 캐시 경합으로 백엔드가 죽었다(09-28·09-30).
"""
import re
import threading
import time
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

import embedding_guard

ROOT = Path(__file__).resolve().parents[1]


class _Model:
    """겹침을 프로세스 전체에서 센다 — 모델이 달라도 잠금은 하나여야 한다."""
    inside = 0
    overlap = 0
    calls = 0

    def encode(self, texts, **kwargs):
        cls = _Model
        cls.inside += 1
        cls.overlap = max(cls.overlap, cls.inside)
        time.sleep(0.005)
        cls.inside -= 1
        cls.calls += 1
        return [len(t) for t in texts]


def test_encode_calls_never_overlap_across_models_and_threads():
    _Model.inside = _Model.overlap = _Model.calls = 0
    a, b = embedding_guard.load(_Model), embedding_guard.load(_Model)
    seen = []

    def work(model):
        for _ in range(5):
            seen.append(model.encode(["가나다"], normalize_embeddings=True))

    threads = [threading.Thread(target=work, args=(m,)) for m in (a, b, a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert _Model.calls == 20 and seen == [[3]] * 20
    assert _Model.overlap == 1


def test_unguarded_fake_does_overlap():
    """위 시험이 뜻이 있으려면 잠금 없는 같은 모형은 겹쳐야 한다."""
    _Model.inside = _Model.overlap = _Model.calls = 0
    a, b = _Model(), _Model()
    threads = [threading.Thread(target=lambda m=m: [m.encode(["x"]) for _ in range(5)]) for m in (a, b, a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert _Model.overlap > 1


def test_serialize_is_idempotent_and_keeps_the_object():
    model = _Model()
    once = embedding_guard.serialize(model)
    wrapped = once.encode
    assert embedding_guard.serialize(once) is model and model.encode is wrapped


def test_every_embedding_model_is_loaded_through_the_guard():
    """새 적재 자리가 잠금 밖에 생기면 여기서 걸린다 — 손으로 고른 목록이 아니라 전수."""
    offenders = []
    for base in (ROOT / "backend", ROOT / "data" / "packages" / "installed", ROOT / "data" / "scripts"):
        for path in base.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if "/test_" in "/" + rel or path.name == "ibl_embedding_trainer.py":   # 학습기는 따로 도는 단일 스레드 스크립트
                continue
            text = path.read_text(errors="ignore")
            for line in text.splitlines():
                if re.search(r"\bSentenceTransformer\(", line) and "embedding_guard.load" not in line:
                    offenders.append(f"{rel}: {line.strip()[:100]}")
    assert not offenders, offenders


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
