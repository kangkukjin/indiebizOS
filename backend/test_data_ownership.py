"""데이터 소유 선언 레지스트리 배터리 (2026-08-21 신설)

    T1. 선언 매칭 — 디렉토리 프리픽스( /** )·글롭·정확 경로
    T2. 첫 매칭 승리 — 구체 선언이 뒤의 넓은 선언을 이긴다
    T3. 고아 걷기 — 미선언만 깃발, 선언된 디렉토리 내용은 하강 안 함
    T4. 백업 규약 보조 — _backups 30일 초과분만 삭제 후보
    T5. 힌트 분류 — .bak_ 접미=규약 위반 / md·png=산출물 / db=은퇴 후보
    T6. 실저장소 불변식 — 와일드카드 없는 선언은 전부 실존(선언 부패 0)

실행: python3 backend/test_data_ownership.py
"""
import os
import shutil
import sys
import tempfile
import pytest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

import data_ownership as do  # noqa: E402


def test_t1_match_kinds(_):
    assert do._match("data/packages/installed/tools/web/handler.py")[1] == "source"
    assert do._match("data/packages") is not None, "프리픽스 자신도 매칭"
    assert do._match("data/lightweight_ai_config.json")[1] == "state"  # 글롭 *_ai_config
    assert do._match("data/ibl_nodes.yaml")[1] == "derived"            # 정확 경로
    assert do._match("data/no_such_thing.xyz") is None


def test_t2_first_match_wins(_):
    # safe_store 정확 .bak 는 backup, .bak_접미 는 미매칭(고아) — 순서가 의미를 가른다
    assert do._match("data/switches.json.bak")[1] == "backup"
    assert do._match("data/business.db.bak_orphan_cleanup") is None
    # guide_db.json 은 source 선언이 *_flags.json 류 넓은 패턴보다 앞
    assert do._match("data/guide_db.json")[1] == "source"


def test_t3_orphan_walk(tmp_root):
    report = do._walk_flags()
    paths = {o["path"] for o in report["orphans"]}
    assert "data/stray.md" in paths, "미선언 파일이 깃발에 없음"
    assert "data/mystery_dir" in paths, "미선언 디렉토리가 깃발에 없음"
    assert "data/ibl_nodes.yaml" not in paths, "선언된 파일이 깃발됨"
    assert not any(p.startswith("data/packages/") for p in paths), \
        "선언된 디렉토리 안으로 하강함"
    assert report["orphans_total"] == len(paths)


def test_t4_stale_backups(tmp_root):
    report = do._walk_flags()
    stales = {s["path"] for s in report["stale_backups"]}
    assert "data/_backups/2026-01-01_old" in stales, "30일 초과 백업 미검출"
    assert "data/_backups/fresh" not in stales, "신선한 백업을 삭제 후보로 오판"
    assert not any("README" in s for s in stales)


def test_t5_hints(_):
    assert "규약 위반" in do._hint_of("data/x.db.bak_pwscrub", False)
    assert "outputs/" in do._hint_of("data/report.md", False)
    assert "은퇴 후보" in do._hint_of("data/orphan.db", False)
    assert "디렉토리" in do._hint_of("data/somedir", True)


def _writer_of(root: Path, rel: str):
    """이 경로를 **만드는 코드**가 저장소에 있는가 — 있으면 (파일명) 없으면 None.

    ★왜 필요한가 (2026-08-23): 선언은 실체보다 **앞설 수 있다**. `data/ibl_param_sweep_state.json`
      은 주간 카덴스가 처음 돌 때 생긴다 — 파일이 생긴 뒤에 선언하면 그 사이 감사는 그걸
      '미선언 고아'로 신고한다(레지스트리가 막으려던 바로 그 드리프트). 그렇다고 없는 선언을
      전부 봐주면 **은퇴한 가족의 선언이 영원히 남는다**(T6 가 잡으려던 부패).
      가르는 기준은 시간이 아니라 사실이다: *그 파일을 쓰는 코드가 아직 있는가.*
      쓰는 코드가 사라졌으면 파일이 없는 것이 곧 부패다.
    """
    base = rel.rsplit("/", 1)[-1]
    for sub in ("backend", "scripts", "data/packages"):
        for path in (root / sub).rglob("*.py"):
            name = path.name
            if name.startswith("test_") or name == "data_ownership.py":
                continue          # 시험·선언 자신은 '쓰는 코드' 가 아니다(자기 참조 금지)
            try:
                if base in path.read_text(encoding="utf-8", errors="replace"):
                    return str(path.relative_to(root))
            except OSError:
                continue
    return None


def test_t6_real_repo_no_vanished(_):
    """선언은 **실체** 아니면 **실체를 만드는 코드** 를 가리켜야 한다 — 둘 다 없으면 부패."""
    root = Path(__file__).parent.parent
    # ★2026-08-30: 옛 worktree 스킵을 걷어냈다. "gitignore 된 런타임 파일이 없는 사본"이라는
    #   부류를 `.git` 이 파일인가(=worktree)라는 **손으로 고른 표지**로 잡았더니, 같은 부류의
    #   다른 몸인 CI 신선 클론에서 그대로 샜다 — 8/27~8/30 Seam Guards 를 나흘간 빨강으로
    #   묶은 원인. 실체 부재는 애초에 실패 조건이 아니다(_writer_of 가 '만드는 코드'로 판정한다).
    #   실측: 그 클론에서 vanished 로 남은 둘은 환경 탓이 아니라 진짜 부패였고(ibl_examples.db
    #   =0바이트 유령·진짜는 ibl_usage.db, ai_desktop_map.json=만드는 코드가 존재한 적 없음),
    #   은퇴시키자 실체 없는 몸에서도 초록이 된다. 스킵은 그 신고를 나흘간 가려온 셈이다.
    vanished = []
    for pat, owner, _kind in do.DECLARATIONS:
        if any(c in pat for c in "*?[") or (root / pat).exists():
            continue
        if _writer_of(root, pat):
            continue              # 아직 안 생겼을 뿐 — 첫 실행이 만든다
        vanished.append(f"{pat}({owner})")
    assert not vanished, (
        f"실체도 만드는 코드도 없는 선언(선언 부패): {vanished}\n"
        "  → 은퇴한 가족이면 DECLARATIONS 에서 빼고, 살아 있으면 쓰는 코드를 확인할 것.")


def test_t6b_retired_family_is_still_caught(tmp_path):
    """게이트가 무뎌지지 않았는지 — 쓰는 코드가 없는 선언은 여전히 빨강이어야 한다."""
    assert _writer_of(Path(__file__).parent.parent, "data/zzz_retired_family.json") is None, \
        "아무도 안 쓰는 이름에서 '쓰는 코드' 를 찾았다 — 게이트가 전부 통과시킨다"


def _make_tmp_root():
    """미니 저장소: 선언된 가족 + 고아 + 백업 신구."""
    root = Path(tempfile.mkdtemp(prefix="ownership_"))
    (root / "data" / "packages" / "sub").mkdir(parents=True)
    (root / "data" / "packages" / "sub" / "deep.py").write_text("x")
    (root / "data" / "mystery_dir").mkdir()
    (root / "data" / "mystery_dir" / "f.txt").write_text("x")
    (root / "data" / "stray.md").write_text("x")
    (root / "data" / "ibl_nodes.yaml").write_text("x")
    b = root / "data" / "_backups"
    (b / "2026-01-01_old").mkdir(parents=True)
    (b / "fresh").mkdir()
    (b / "README.md").write_text("x")
    old = (datetime.now() - timedelta(days=60)).timestamp()
    os.utime(b / "2026-01-01_old", (old, old))
    return root


def main():
    tmp = _make_tmp_root()
    saved = do._ROOT
    do._ROOT = tmp
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    try:
        for name, fn in tests:
            try:
                if name in ("test_t6_real_repo_no_vanished",):
                    do._ROOT = saved
                fn(tmp)
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
            finally:
                do._ROOT = tmp
    finally:
        do._ROOT = saved
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    sys.exit(1 if failed else 0)


# pytest 수집 호환
try:
    import pytest

    @pytest.fixture(scope="module", name="tmp_root")
    def _tmp_fixture():
        tmp = _make_tmp_root()
        saved = do._ROOT
        do._ROOT = tmp
        yield tmp
        do._ROOT = saved
        shutil.rmtree(tmp, ignore_errors=True)

    @pytest.fixture(name="_")
    def _noop_fixture():
        return None
except ImportError:
    pass


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
