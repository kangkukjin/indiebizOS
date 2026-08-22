r"""빌드 파생물 원자 쓰기 회귀 (2026-08-22)

빌드가 write_text 로 직접 쓰면 라이브 백엔드가 부분 파일을 읽는다.
ibl_nodes.yaml 이 그렇게 읽히면 어휘가 조용히 반쪽이 되는데, yaml 은 줄 단위라
예외조차 안 나서 낱말 일부가 사라진 채 정상처럼 돈다.

    A1. 권한 보존 (ibl_nodes.yaml = 0755 — mkstemp 기본 0600 이 새면 안 된다)
    A2. 동시 읽기가 부분 파일을 절대 못 본다 (옛 판 아니면 새 판, 그 사이는 없다)
    A3. 쓰기 실패 시 원본 보존 + 임시파일 잔여 0
    A4. 새 파일 생성 경로

실행: python3 scripts/test_atomic_write.py
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from iblbuild_common import atomic_write_text  # noqa: E402

OLD = "옛판\n" * 2000
NEW = "새판\n" * 2000


def test_a1_preserves_mode():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ibl_nodes.yaml"
        p.write_text(OLD, encoding="utf-8")
        os.chmod(p, 0o755)
        atomic_write_text(p, NEW)
        mode = p.stat().st_mode & 0o777
        assert mode == 0o755, "권한이 %s 로 바뀌었다(mkstemp 0600 누출?)" % oct(mode)
        assert p.read_text(encoding="utf-8") == NEW


def test_a2_no_partial_read_under_concurrency():
    """읽는 쪽이 본 내용은 언제나 옛판 또는 새판 — 그 사이는 없어야 한다."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "big.yaml"
        p.write_text(OLD, encoding="utf-8")
        seen, stop = [], threading.Event()

        def reader():
            while not stop.is_set():
                try:
                    seen.append(p.read_text(encoding="utf-8"))
                except FileNotFoundError:
                    seen.append("<사라짐>")
                except Exception as e:
                    seen.append("<오류:%s>" % type(e).__name__)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        for i in range(60):
            atomic_write_text(p, NEW if i % 2 else OLD)
        stop.set()
        t.join(timeout=5)

        assert seen, "읽기가 한 번도 안 돌았다 — 시험이 무의미"
        bad = [s[:20] for s in seen if s not in (OLD, NEW)]
        assert not bad, "부분/사라진 파일을 %d번 봤다: %r" % (len(bad), bad[:3])


def test_a3_failure_keeps_original():
    """쓰기 실패·갈아끼우기 실패 둘 다 — 원본 보존 + 임시파일 잔여 0."""
    import iblbuild_common as C

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "keep.yaml"
        p.write_text(OLD, encoding="utf-8")

        # (a) 쓰기 도중 실패 (문자열이 아닌 값)
        try:
            atomic_write_text(p, object())  # type: ignore[arg-type]
        except Exception:
            pass
        else:
            raise AssertionError("잘못된 payload 가 조용히 통과했다")
        assert p.read_text(encoding="utf-8") == OLD, "쓰기 실패가 원본을 훼손했다"
        assert not list(p.parent.glob(".keep.yaml.*")), "임시파일 잔여(쓰기 실패)"

        # (b) 갈아끼우기 자체가 실패
        real_replace = C.os.replace
        C.os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("의도된 실패"))
        try:
            atomic_write_text(p, NEW)
        except OSError:
            pass
        else:
            raise AssertionError("replace 실패가 조용히 통과했다")
        finally:
            C.os.replace = real_replace
        assert p.read_text(encoding="utf-8") == OLD, "replace 실패가 원본을 훼손했다"
        assert not list(p.parent.glob(".keep.yaml.*")), "임시파일 잔여(replace 실패)"


def test_a4_creates_new_file():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "하위" / "새파일.json"
        atomic_write_text(p, NEW)
        assert p.read_text(encoding="utf-8") == NEW
        assert p.stat().st_mode & 0o777 == 0o644, oct(p.stat().st_mode & 0o777)


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
