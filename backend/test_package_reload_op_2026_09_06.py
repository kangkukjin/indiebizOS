"""[self:package]{op:"reload"} — 낱말 없는 HTTP 만 있어 curl 로 우회하던 자리 (2026-09-06, ep2904 ×4)

편집 결과문(live_effect_note)이 `[self:package]{op:"reload"}` 를 약속해 왔는데 낱말엔 그 op 이 없었다.
처방: op 추가 + POST /packages/reload 와 **한 절차**(ibl_routing.invalidate_runtime_caches) + 셸 그림자.

실행: .venv/bin/python -m pytest backend/test_package_reload_op_2026_09_06.py -q
"""
import os
import sys

import yaml

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_reload_op_declared_and_dispatched():
    nodes = yaml.safe_load(open(os.path.join(ROOT, "data", "ibl_nodes.yaml"), encoding="utf-8"))["nodes"]
    ops = nodes["self"]["actions"]["package"]["ops"]
    assert "reload" in ops["values"]
    assert ops["returns"].get("reload") == "effect"
    import ibl_routing as R
    # 의식 리셋은 조립 루트가 부팅 때 주입하는 능력 — 맨 프로세스엔 없으니 시험이 같은 자리에 스텁을 꽂는다.
    calls = []
    prev = dict(R._SYSTEM_CAPS)
    R.register_system_capabilities({"reset_consciousness": lambda: calls.append("reset")})
    try:
        out = R._package_op({"op": "reload"})
    finally:
        R._SYSTEM_CAPS.clear(); R._SYSTEM_CAPS.update(prev)
    assert out.get("success") is True, out
    assert calls == ["reset"], "의식 캐시 단계가 절차에서 빠졌다"
    assert out.get("reloaded") == R.RELOAD_COVERS and out.get("not_reloaded") == R.RELOAD_DOES_NOT_COVER
    # 실패를 삼키지 않는다 — 능력이 없으면 partial 로 말한다(침묵 클램프 금지)
    R._SYSTEM_CAPS.pop("reset_consciousness", None)
    try:
        bad = R._package_op({"op": "reload"})
    finally:
        R._SYSTEM_CAPS.clear(); R._SYSTEM_CAPS.update(prev)
    assert bad.get("success") is False and bad.get("status") == "partial" and "consciousness" in str(bad.get("failed_steps"))


def test_http_reload_and_op_share_one_procedure():
    """두 표면이 같은 함수를 부른다 — 08-24 '동형이라 적고 아니었다' 부류의 재발 방지."""
    src = open(os.path.join(ROOT, "backend", "surface", "api_packages.py"), encoding="utf-8").read()
    body = src[src.index('@router.post("/packages/reload")'):]
    body = body[:body.index("@router.", 10)]
    assert "invalidate_runtime_caches" in body
    assert "reload_nodes" not in body and "invalidate_nodes_cache" not in body


if __name__ == "__main__":                      # 러너는 하나 — pytest
    import sys as _sys
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
