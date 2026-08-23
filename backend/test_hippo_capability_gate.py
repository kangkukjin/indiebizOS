"""해마 능력 게이트 회귀 — **가졌는가**와 **지금 올라와 있는가**는 다른 질문 (2026-08-23).

재현하는 결함(실측): 새 프로세스에서 `search_fts5` 는 3건을 내는데 `search_hybrid` 는
**0건**이었다. 원인은 `_rented_mode()` 가 능력을 `is_semantic_available()` 로 물은 것 —
그 함수는 *준비 상태*를 답한다(`_load_model` 은 모델이 안 올라왔으면 백그라운드
로딩을 시작하고 False). 로컬 인코더를 가진 맥이 모델 로딩 중에 렌트(폰) 몸으로
오인되고, `hippo_disabled()` 가 참이 되어 `search_hybrid` 가 맨 앞에서 [] 를 반환했다.
FTS5 폴백은 코드에 있었지만 **도달하지 못했다** — 에러 없이 회상이 통째로 사라졌다.

증상은 시험만의 일이 아니다: 백엔드는 코드를 고칠 때마다 리로드되고, 그 직후 모델
로딩 창(수십 초~수 분) 동안 모든 턴의 연상 단계가 조용히 빈손이 된다.

처방: 능력 질문은 능력으로 답한다(`_has_local_encoder`). 가졌는데 아직 안 올라왔을
뿐이면 렌트가 아니라 **폴백**이 답이다.

실행: .venv/bin/python -m pytest backend/test_hippo_capability_gate.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401


def _gate(monkeypatch, *, model=None, attempted=False, model_dir=None,
          mac_url="http://mac.example:8765"):
    """능력 게이트만 떼어 재는 시느대 — 라이브 DB·모델 무접촉."""
    from ibl_usage_db import IBLUsageDB
    monkeypatch.setattr(IBLUsageDB, "_model", model, raising=False)
    monkeypatch.setattr(IBLUsageDB, "_model_load_attempted", attempted, raising=False)
    monkeypatch.setattr(IBLUsageDB, "_model_loading", False, raising=False)
    monkeypatch.setattr(IBLUsageDB, "_check_sqlite_vec", classmethod(lambda cls: True))
    monkeypatch.setattr(IBLUsageDB, "_ensure_rented_index", classmethod(lambda cls: True))
    if model_dir is not None:
        monkeypatch.setattr(IBLUsageDB, "_resolve_model_dir", staticmethod(lambda: model_dir))
    if mac_url is None:
        monkeypatch.delenv("INDIEBIZ_MAC_URL", raising=False)
    else:
        monkeypatch.setenv("INDIEBIZ_MAC_URL", mac_url)
    monkeypatch.delenv("INDIEBIZ_HIPPO", raising=False)   # 강제 토글 무력화
    return IBLUsageDB


def _has_model_dir() -> bool:
    from ibl_usage_db import IBLUsageDB
    from pathlib import Path
    d = Path(IBLUsageDB._resolve_model_dir())
    return (d / "model.safetensors").exists() or (d / "config.json").exists()


def test_g1_loading_body_is_not_a_rented_body(monkeypatch, tmp_path):
    """모델을 가졌고 아직 로딩 중인 몸 = 렌트가 아니다 — 이게 이번 결함의 심장."""
    md = tmp_path / "ibl_embedding"
    md.mkdir()
    (md / "config.json").write_text("{}", encoding="utf-8")
    db = _gate(monkeypatch, model=None, attempted=False, model_dir=str(md))

    assert db._has_local_encoder() is True, "모델 폴더가 있는데 '없다'고 판정했다"
    assert db._rented_mode() is False, \
        "로딩 중이라는 이유로 렌트(폰) 몸로 오인했다 — 준비상태를 능력으로 읽은 것"
    assert db.hippo_disabled() is False, \
        "해마가 꺼졌다 — search_hybrid 가 맨 앞에서 [] 를 반환해 FTS 폴백까지 못 간다"


def test_g2_phone_still_rents(monkeypatch, tmp_path):
    """로컬 인코더가 진짜로 없는 몸(폰)은 그대로 렌트 — 수리가 폰의 길을 막지 않는다."""
    empty = tmp_path / "no_model"
    empty.mkdir()
    db = _gate(monkeypatch, model=None, attempted=False, model_dir=str(empty))

    assert db._has_local_encoder() is False
    assert db._rented_mode() is True, "모델이 없는 몸까지 렌트를 막았다"


def test_g3_failed_load_is_really_absent(monkeypatch, tmp_path):
    """로드를 시도했는데 모델이 안 올라왔으면 진짜로 없는 것(미설치·로드 실패) — 렌트 허용."""
    md = tmp_path / "ibl_embedding"
    md.mkdir()
    (md / "config.json").write_text("{}", encoding="utf-8")
    db = _gate(monkeypatch, model=None, attempted=True, model_dir=str(md))

    assert db._has_local_encoder() is False, \
        "시도하고도 없으면 없는 것이다 — 폴더만 보고 '가졌다'고 우기면 렌트가 죽는다"
    assert db._rented_mode() is True


def test_g4_capability_is_not_readiness_in_source():
    """판정이 다시 `is_semantic_available()` 하나로 퇴화하지 않게 — 결함의 모양을 박아둔다."""
    import ibl_usage_db
    src = open(ibl_usage_db.__file__, encoding="utf-8").read()
    assert "_has_local_encoder" in src
    head = src.split("def _rented_mode", 1)[1][:600]
    assert "_has_local_encoder" in head, \
        "_rented_mode 가 능력 질문(_has_local_encoder)을 묻지 않는다 — 준비상태 오독이 부활한다"


def test_g5_fts_fallback_survives_a_cold_model(monkeypatch):
    """끝에서 끝: 모델이 안 올라온 상태에서도 hybrid 가 FTS 폴백으로 회상을 낸다.

    라이브 해마 DB 가 있는 몸에서만 재는다(없으면 스킵) — 이 시험이 재현하는
    것은 사용자가 실제로 겪은 증상(빈 실행기억 30/30) 그 자체다.
    """
    import pytest
    from pathlib import Path
    from ibl_usage_db import IBLUsageDB
    root = Path(__file__).parent.parent
    if not (root / "data" / "ibl_usage.db").exists():
        pytest.skip("해마 DB 없음 (data/ibl_usage.db)")
    if not _has_model_dir():
        pytest.skip("로컬 인코더 없는 몸 — 이 시험은 맥용")

    _gate(monkeypatch, model=None, attempted=False)   # 모델 차가운 상태 재현
    db = IBLUsageDB()
    assert db.hippo_disabled() is False
    fts = db.search_fts5("삼성전자 주가 알려줘", top_k=5)
    hybrid = db.search_hybrid(query="삼성전자 주가 알려줘", top_k=5)
    if not fts:
        pytest.skip("코퍼스에 이 질의에 걸리는 용례가 없다")
    assert hybrid, \
        f"FTS 는 {len(fts)}건인데 hybrid 가 0건 — 폴백에 도달하지 못했다(이번 결함의 증상)"


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
