"""몸-명사 관문(memory_db.body_noun_leak)의 예외 집합 = 세계의 산물 보관소(runtime_utils.WORLD_PRODUCT_DIRS).

2026-09-05 ep2828: 관문이 "outputs" 리터럴만 알아, 정기 산출물의 공개면 사본이 사는 공유창고
경로를 문 작업기록("부동산 발굴 보고서 28호 작성 완료 …html")을 통째로 버렸다(같은 거부 12회).
예외 집합은 코드 한 곳이 정본이고, 관문·창고 라우트가 같은 이름을 읽는다.

실행: .venv/bin/python -m pytest -q backend/test_body_noun_world_products.py
"""
import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401

_REPO = Path(__file__).resolve().parent.parent
_MEM = _REPO / "data" / "packages" / "installed" / "tools" / "memory" / "memory_db.py"


def _memory_db():
    spec = importlib.util.spec_from_file_location("memory_db_under_test", str(_MEM))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_world_product_dirs_pass_the_gate(monkeypatch):
    import runtime_utils as ru
    monkeypatch.delenv("INDIEBIZ_BASE_PATH", raising=False)
    base = Path(ru.get_base_path()).resolve()
    md = _memory_db()
    assert "outputs" in ru.WORLD_PRODUCT_DIRS and ru.WAREHOUSE_DIRNAME in ru.WORLD_PRODUCT_DIRS
    # 세계의 산물 보관소 — 두 칸 다 통과
    for d in ru.WORLD_PRODUCT_DIRS:
        txt = f"보고서 작성 완료, 파일: {base}/{d}/0/부동산 보고서/부동산 보고서 2026-09-05 x.html"
        assert md.body_noun_leak(txt) is None, (d, txt)
    # 몸의 살 — 종전대로 거부
    leak = md.body_noun_leak(f"대화 DB 경로: {base}/backend/api.py")
    assert leak and leak.endswith("backend/api.py")
    # URL 은 세계의 명사
    assert md.body_noun_leak("https://example.com/outputs/x.html 참조") is None


def test_warehouse_route_reads_the_same_name():
    """창고 라우트의 폴더 이름이 관문의 예외 집합과 한 정본을 읽는다(리터럴 분기 금지)."""
    src = (_REPO / "backend" / "surface" / "portal_warehouse.py").read_text(encoding="utf-8")
    assert "WAREHOUSE_DIRNAME" in src and '_ROOT / "공유창고"' not in src
    gate = _MEM.read_text(encoding="utf-8")
    assert "WORLD_PRODUCT_DIRS" in gate and '"outputs" in rel_parts' not in gate

if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
