r"""[sense:crawl] 실패 신고의 정직성 회귀 (2026-08-22)

ep1394(AI 동향 보고서, 08-22 04:00)에서 z.ai 블로그가 두 번 연속 실패했다.
신고는 "본문을 충분히 추출하지 못했습니다 (정적·브라우저 렌더링 모두 시도)" 였는데
바로 옆 methods_tried 는 ["curl_cffi"] 하나뿐이었다 — **브라우저 단계는 돌지도
않았다.** 읽은 AI 는 "이 페이지는 못 읽는다"로 닫고 Bash curl 로 우회했다.
실제로는 나중에 다시 부르면 되는 일이었다(같은 URL 이 뒤에 정상 크롤됨).

크롤 능력의 결함이 아니라 **신고의 결함**이다. 하지 않은 일을 했다고 말하면
읽는 쪽이 다음 수를 잃는다.

    C1. 브라우저 단계가 안 돈 실패는 "모두 시도"라고 말하지 않는다
    C2. 단계 내역(stages)이 무엇이 왜 안 돌았는지 나른다
    C3. Playwright 가 실행 중 죽으면 그 사유가 사라지지 않는다 (옛 except: pass)
    C4. 성공 경로는 그대로

실행: python3 backend/test_crawl_stage_honesty.py
"""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

_PKG = (Path(__file__).resolve().parent.parent
        / "data/packages/installed/tools/web/tool_webcrawl.py")


def _load():
    spec = importlib.util.spec_from_file_location("tw_test", _PKG)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _stub_static(m, **over):
    base = {"success": True, "url": "u", "title": "", "text": "", "length": 0,
            "method": "curl_cffi", "reason": "insufficient_content"}
    base.update(over)
    m._crawl_static = lambda url, ml: dict(base)          # noqa: E731


def test_c1_no_false_claim_when_browser_never_ran():
    m = _load()
    _stub_static(m)
    m._get_chrome_driver = lambda: None                    # noqa: E731
    m._get_browser_session = lambda: None                  # noqa: E731

    r = m.crawl_website("https://예시/js페이지")
    assert r["success"] is False
    assert "모두 시도" not in r["error"], "하지 않은 일을 했다고 말한다: %s" % r["error"]
    assert "브라우저 렌더링 단계가 실행되지 못했습니다" in r["error"], r["error"]
    # 다음 수를 알려주는가
    assert "limbs:browser" in r["error"] or "재시도" in r["error"], r["error"]


def test_c2_stages_carry_why():
    m = _load()
    _stub_static(m)
    m._get_chrome_driver = lambda: None                    # noqa: E731
    m._get_browser_session = lambda: None                  # noqa: E731

    r = m.crawl_website("https://예시/js페이지")
    stages = {st["stage"]: st for st in r["stages"]}
    assert "정적(curl_cffi)" in stages and stages["정적(curl_cffi)"]["ran"] is True
    for name in ("Chrome MCP", "Playwright"):
        assert name in stages, "단계가 내역에서 통째로 빠졌다: %s" % name
        assert stages[name]["ran"] is False
        assert "건너뜀" in stages[name]["detail"], stages[name]

    # methods_tried 와 stages 가 서로 모순되지 않아야 한다
    ran = {st["stage"] for st in r["stages"] if st["ran"]}
    assert len(ran) == len(r["methods_tried"]), (ran, r["methods_tried"])


def test_c3_playwright_crash_reason_survives():
    """C3: 예전 `except Exception: pass` 는 죽은 이유를 통째로 지웠다."""
    m = _load()
    _stub_static(m)
    m._get_chrome_driver = lambda: None                    # noqa: E731
    m._get_browser_session = lambda: object()              # noqa: E731

    def boom(*a, **k):
        raise RuntimeError("Executable doesn't exist at .../chromium-1208")
    m._run_async = boom
    m._crawl_playwright_async = lambda *a, **k: None       # noqa: E731 (코루틴 경고 회피)

    r = m.crawl_website("https://예시/js페이지")
    blob = r["error"] + str(r["stages"])
    assert "Executable doesn't exist" in blob, "죽은 이유가 사라졌다: %r" % blob
    assert "모두 시도" not in r["error"], r["error"]


def test_c4_success_path_unchanged():
    m = _load()
    _stub_static(m, text="본문입니다", length=5, reason=None, title="제목")
    r = m.crawl_website("https://예시/정적페이지")
    assert r["success"] is True and r["text"] == "본문입니다", r
    assert "stages" not in r, "성공 경로에 진단 잡음이 끼었다"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for fn in fns:
        try:
            fn()
            print("  ✓ %s" % fn.__name__)
        except Exception as e:
            fails += 1
            print("  ✗ %s — %s" % (fn.__name__, e))
    print("\n%d/%d 통과" % (len(fns) - fails, len(fns)))
    sys.exit(1 if fails else 0)
