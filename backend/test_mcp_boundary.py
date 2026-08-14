"""MCP 에이전트 경계(클로드 코드 경로) 회귀 테스트 (2026-08-14)

두 결함의 재현 케이스 (두-경로 대칭 감사 1탄 — CC 경로):
  A. 이미지 봉투가 MCP 경계를 텍스트로 건너 base64 가 24k 예산 절단에 걸리던 것
     → mcp_server 가 에이전트 경계에서 수확해 MCP ImageContent 로 승격.
     ★실측 두 계약: ①{"image_data":{"b64",...}} (수확 관문 봉투)
                    ②{"images":[{"base64",...}]} (프로바이더 계약 — limbs:screen 등)
  B. 반복 호출 가드가 CC 경로에 전무하던 것 → (code, path) 연쇄 카운트,
     임계 3/5/8 점증 조언 부록(차단 없음·오류도 카운트·다른 호출 리셋).

실행: python3 backend/test_mcp_boundary.py  (mcp 패키지 필요 — 백엔드 인터프리터)
라이브 종단은 stdio 왕복으로 별도 검증됨(스크린샷 → ImageContent, 3연타 → 조언).
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401
import mcp_server as M


def test_image_harvest():
    b64 = base64.b64encode(b'PNGDATA').decode()

    # 계약 ①: image_data 봉투 — b64 제거·image 메타 잔류
    raw1 = json.dumps({"result": {"image_data": {"b64": b64, "media_type": "image/png",
                                                 "path": "/x.png"}}})
    c1, i1 = M._harvest_images_for_mcp(raw1)
    assert len(i1) == 1 and i1[0]["b64"] == b64
    assert "b64" not in json.dumps(json.loads(c1))
    assert json.loads(c1)["result"]["image"]["path"] == "/x.png"

    # 계약 ②: 프로바이더 형태 (limbs:screen 라이브 실측 모양)
    raw2 = json.dumps({"content": "스크린샷", "images": [{"base64": b64, "media_type": "image/png"}]})
    c2, i2 = M._harvest_images_for_mcp(raw2)
    assert len(i2) == 1 and i2[0]["b64"] == b64 and '"base64"' not in c2

    # 중첩(병렬: JSON문자열-in-리스트-in-문자열) 관통
    inner = json.dumps({"image_data": {"b64": b64, "media_type": "image/jpeg"}})
    c3, i3 = M._harvest_images_for_mcp(json.dumps({"results": [json.dumps([inner, "text"])]}))
    assert len(i3) == 1 and "b64" not in c3

    # 혼합 두 계약 + 상한 4장
    raw4 = json.dumps({"a": {"image_data": {"b64": b64, "media_type": "image/png"}},
                       "b": {"images": [{"base64": b64} for _ in range(5)]}})
    c4, i4 = M._harvest_images_for_mcp(raw4)
    assert len(i4) == 4 and '"base64"' not in c4

    # 무이미지 identity (비용 0 경로)
    raw5 = json.dumps({"result": "텍스트"})
    assert M._harvest_images_for_mcp(raw5) == (raw5, [])
    print("OK image harvest (5)")


def test_repeat_guard():
    # 공용 코어(backend/base/repeat_guard) — 직결 어댑터(execute_tool)와 CC 어댑터가 공유
    import repeat_guard
    repeat_guard.reset_all()
    sig = '[sense:search]{query:"x"}|/p'
    assert M._repeat_advisory("a1", sig) == ""
    assert M._repeat_advisory("a1", sig) == ""
    assert "연속 3회" in M._repeat_advisory("a1", sig)
    assert M._repeat_advisory("a1", sig) == ""          # 4회째 조용
    assert "5회째" in M._repeat_advisory("a1", sig)
    assert M._repeat_advisory("a1", "다른코드|/p") == ""  # 리셋
    assert M._repeat_advisory("a2", sig) == ""          # 신원 분리
    # 두 어댑터가 같은 코어 객체를 쓰는지 (표류 방지의 핵심 단언)
    assert M._repeat_advisory is repeat_guard.advise
    repeat_guard.reset_all()
    print("OK repeat guard (8)")


def test_execute_ibl_shapes():
    """execute_ibl 전체 경로 (백엔드 스텁): 이미지 → [text, Image] / 무이미지 → str."""
    import anyio
    from mcp.server.fastmcp import Image as McpImage
    b64 = base64.b64encode(b'PNGDATA').decode()
    import repeat_guard
    orig = M._post_backend
    try:
        M._post_backend = lambda p, pl, t: json.dumps(
            {"content": "캡처", "images": [{"base64": b64, "media_type": "image/png"}]})
        repeat_guard.reset_all()
        out = anyio.run(M.execute_ibl, '[limbs:screen]{op:"screenshot"}', '/tmp')
        assert isinstance(out, list) and isinstance(out[1], McpImage)
        assert '"base64"' not in out[0]

        M._post_backend = lambda p, pl, t: json.dumps({"result": "그냥 텍스트"})
        repeat_guard.reset_all()
        out2 = anyio.run(M.execute_ibl, '[sense:host]{op:"status"}', '/tmp')
        assert isinstance(out2, str)
    finally:
        M._post_backend = orig
    print("OK execute_ibl shapes (2)")


if __name__ == '__main__':
    test_image_harvest()
    test_repeat_guard()
    test_execute_ibl_shapes()
    print("ALL PASS")
