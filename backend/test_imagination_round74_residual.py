"""상상훈련 74회차 잔여 수리 회귀 (2026-09-29). 라이브 서비스 없음.

1b9a4932 가 개별 자리(B74-1~6·F74-1~2)를 닫은 뒤 재탐침·재검토에서 남은 것:
  · 도구 봉투의 source_complete:false 가 실행 전체에선 '완전'으로 통과(저장소 요약·시세 이력 공통)
  · 완전성 기록 이전의 옛 스캔이 보호 폴더 아래 요약을 0건·완전으로 답함
  · 하위 경로 요약·메모: NFD 폴더·조상 실패·하위 범위 필터·상대 경로 기준
  · 판본 2 legacy-envelope 의 평문 `Error:` 가 ADAPTER_SHAPE(봉투 파손)로 분류
  · sorted 다중 키 안내가 판본 2 에서 거절되는 형태를 권함
  · 밭 이관 관문: 사용자 경로 효과(읽기 op 의 사용자 위치 쓰기 · delete 밖 사용자 위치 삭제)
"""
import importlib.util
import json
import os
import sys
import unicodedata
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

from common.expression_ir import Fault
from ibl_v2_adapters import decode_envelope

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'data/packages/installed/tools'
SCRIPTS = ROOT / 'scripts'
LEGACY = {"protocol": "legacy-envelope", "value_path": ""}


def module(package, name):
    path = TOOLS / package / (name + '.py')
    spec = importlib.util.spec_from_file_location(f'r74_{package.replace("-", "_")}_{name}', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fault_of(raw, adapter=LEGACY):
    with pytest.raises(Fault) as info:
        decode_envelope(raw, adapter)
    return info.value


# ── B74-5 평문 실패는 legacy-envelope 프로토콜의 규약 ─────────────────────────

def test_legacy_plain_error_is_tool_failure_not_adapter_shape():
    fault = fault_of("Error: 원본과 대상 경로가 필요합니다.")
    assert fault.code == "TOOL" and "원본과 대상" in str(fault)


def test_plain_text_outside_the_convention_stays_adapter_shape():
    assert fault_of("그냥 문장").code == "ADAPTER_SHAPE"
    assert fault_of("Error: x", {"protocol": "document-value/1", "value_path": ""}).code == "ADAPTER_SHAPE"
    value, _ = decode_envelope("Successfully edited a.txt",
                               {**LEGACY, "text_success_prefix": "Successfully edited "})
    assert value["success"] is True


# ── 도구가 스스로 말한 원천 불완전은 경계 증거 ─────────────────────────────────

def test_tool_declared_incomplete_source_is_partial():
    raw = {"success": True, "items": [{"extension": "txt"}], "source_complete": False,
           "errors": [{"path": "/x/locked", "error": "Permission denied"}], "message": "접근 못 한 항목 1건"}
    fault = fault_of(json.dumps(raw))
    assert fault.code == "PARTIAL_SOURCE" and "접근 못 한 항목" in str(fault)
    assert fault.details["completion"][0]["source_complete"] is False


def test_user_rows_named_source_complete_stay_data():
    raw = {"success": True, "items": [{"source_complete": False}], "source_complete": True}
    value, _ = decode_envelope(json.dumps(raw), LEGACY)
    assert value["items"] == [{"source_complete": False}]


# ── F74-1 다중 키 정렬 안내는 판본 2 에서 서는 형태만 ─────────────────────────

_CB = object()   # 콜백 키 자리(실행기는 Callable 값을 넘긴다)

@pytest.mark.parametrize('rows,key,expect', [
    ([{"d": True, "n": "b"}, {"d": False, "n": "a"}], lambda r: [not r["d"], r["n"]], "뒤 키부터"),
    ([{"d": True}, {"d": False}], lambda r: r["d"], "조건 값"),
])
def test_unordered_sort_key_names_the_working_form(rows, key, expect):
    from common.expression_functions import call
    with pytest.raises(Fault) as info:
        call('sorted', [rows, _CB], lambda: None, callback=lambda _k, row: key(row))
    assert info.value.code == 'UNORDERED' and expect in str(info.value)


def test_callable_hint_no_longer_recommends_rejected_forms():
    from common.expression_functions import call
    with pytest.raises(Fault) as info:
        call('sorted', [[{"a": 1}], 3], lambda: None)
    assert '뒤 키부터' in str(info.value) and 'by 목록' not in str(info.value)


def test_two_pass_stable_sort_gives_folders_first_then_name():
    from common.expression_functions import call
    rows = [{"n": "b", "d": False}, {"n": "c", "d": True}, {"n": "a", "d": False}, {"n": "a2", "d": True}]
    by_name = call('sorted', [rows, "n"], lambda: None)
    out = call('sorted', [by_name, _CB], lambda: None, callback=lambda _k, r: 0 if r["d"] else 1)
    assert [r["n"] for r in out] == ["a2", "c", "a", "b"]


# ── B74-3·B74-4 저장소 요약·폴더 메모의 잔여 경계 ─────────────────────────────

@pytest.fixture
def storage(tmp_path, monkeypatch):
    mod = module('pc-manager', 'storage_db')
    monkeypatch.setattr(mod, 'SCANS_DIR', str(tmp_path / 'index'))
    monkeypatch.setattr(mod, 'SCANS_JSON', str(tmp_path / 'index/scans.json'))
    return mod


def test_legacy_scan_without_completeness_record_is_not_complete(storage, tmp_path):
    root = tmp_path / 'v'; (root / 'Downloads').mkdir(parents=True)
    assert storage.scan_directory(str(root))['success']
    scans = storage._load_scans_json()
    for s in scans:                               # 오류 기록 도입 이전 스캔 원장의 모양
        s.pop('source_complete', None); s.pop('scan_errors', None)
    storage._save_scans_json(scans)
    sub = storage.get_summary(str(root / 'Downloads'))
    assert sub['success'] and sub['file_count'] == 0 and sub['source_complete'] is False
    assert '다시 스캔' in sub['message']
    assert storage.get_summary_all()['source_complete'] is False


def test_subtree_completeness_counts_only_failures_that_touch_it(storage, tmp_path):
    root = tmp_path / 'v'; (root / 'ok').mkdir(parents=True); (root / 'locked' / 'inner').mkdir(parents=True)
    (root / 'ok' / 'a.txt').write_text('1')
    os.chmod(root / 'locked', 0o000)
    try:
        result = storage.scan_directory(str(root))
    finally:
        os.chmod(root / 'locked', 0o755)
    assert result['success'] and result['error_count'] == 1
    assert storage.get_summary(str(root / 'ok'))['source_complete'] is True       # 형제 실패는 무관
    assert storage.get_summary(str(root / 'locked' / 'inner'))['source_complete'] is False  # 조상 실패
    assert storage.get_summary(str(root))['source_complete'] is False


def test_broken_link_is_a_link_not_an_access_failure(storage, tmp_path):
    root = tmp_path / 'v'; root.mkdir()
    (root / 'good.txt').write_text('good')
    (root / 'broken.txt').symlink_to(root / 'missing.txt')
    result = storage.scan_directory(str(root))
    assert result['success'] and result['source_complete'] is True and result['file_count'] == 2


def test_nfd_named_subfolder_summary(storage, tmp_path):
    root = tmp_path / 'v'
    nfd = root / unicodedata.normalize('NFD', '강의자료')
    nfd.mkdir(parents=True); (nfd / 'a.pdf').write_text('x' * 10)
    assert storage.scan_directory(str(root))['success']
    summary = storage.get_summary(str(root / unicodedata.normalize('NFC', '강의자료')))
    assert summary['file_count'] == 1 and summary['total_size_mb'] == 0.0
    top = storage.get_summary(str(root))
    assert [f['folder'] for f in top['folders']] == [unicodedata.normalize('NFC', '강의자료')]


def test_notes_resolve_relative_to_project_and_detail_is_scoped(storage, tmp_path):
    project = tmp_path / 'proj'; (project / 'a').mkdir(parents=True); (project / 'b').mkdir()
    assert storage.scan_directory('.', base=str(project))['success']
    assert storage.add_annotation('a', 'a', '에이', base=str(project))['success']      # path 한 칸 형태
    assert storage.add_annotation(str(project), 'b', '비', base=str(project))['folder_path'] == str(project / 'b')
    only_a = storage.get_annotations('a', base=str(project))['items']
    assert [(x['folder_path'], x['note']) for x in only_a] == [(str(project / 'a'), '에이')]
    assert len(storage.get_annotations(str(project))['items']) == 2


def test_folder_note_set_without_root_path(tmp_path, monkeypatch):
    storage = module('pc-manager', 'storage_db')
    monkeypatch.setattr(storage, 'SCANS_DIR', str(tmp_path / 'index'))
    monkeypatch.setattr(storage, 'SCANS_JSON', str(tmp_path / 'index/scans.json'))
    monkeypatch.setitem(sys.modules, 'storage_db', storage)
    handler = module('pc-manager', 'handler')
    root = tmp_path / 'v'; (root / 'assets').mkdir(parents=True)
    assert storage.scan_directory(str(root))['success']
    out = json.loads(handler._annotate_folder({'folder_path': str(root / 'assets'), 'note': '로고'}))
    assert out['success'] and out['folder_path'] == str(root / 'assets') and '~' not in out['message']


# ── 밭 이관 관문: 사용자 경로 효과 ────────────────────────────────────────────

def _gate():
    sys.path.insert(0, str(SCRIPTS))
    import iblbuild_user_path_effects
    return iblbuild_user_path_effects


@pytest.mark.system  # 2026-10-04: 전체 재생·전수 스캔은 system 묶음(docs/REGRESSION_TESTING.md 표)
def test_user_path_effects_gate_is_clean_on_live_tree():
    import yaml
    gate = _gate()
    data = yaml.safe_load((ROOT / 'data/ibl_nodes.yaml').read_text(encoding='utf-8'))
    issues, unresolved = gate.validate_user_path_effects(data, ROOT)
    assert issues == []


def _flow_hits(source, fn):
    import ast
    gate = _gate()
    pkg = gate._Package({'handler': ast.parse(source)})
    found = []
    flow = gate._Flow(pkg, lambda kind, site, prim, line: found.append((kind, site, prim)))
    node = pkg.funcs['handler'][fn]
    flow.run('handler', fn, node.body, {node.args.args[0].arg: gate.DICT})
    return found


def test_gate_sees_target_first_delete_and_read_side_writes():
    source = '''
import os, shutil
from pathlib import Path
CACHE = Path("/tmp/cache")
def _dst(ti):
    return os.path.join("/p", ti.get("dest"))
def copy(ti):
    dst = _dst(ti)
    if os.path.exists(dst):
        shutil.rmtree(dst)
def read_pptx(ti):
    path = Path(ti.get("path"))
    images = path.parent / f"{path.stem}_images"
    images.mkdir(exist_ok=True)
def read_cached(ti):
    path = Path(ti.get("path"))
    doc = open(path).read()
    out = CACHE / path.name
    out.write_text(doc)
def by_id(ti):
    folder = CACHE / ti.get("slide_id")
    shutil.rmtree(folder)
'''
    assert ('delete', 'handler.copy', 'shutil.rmtree') in _flow_hits(source, 'copy')
    assert ('write', 'handler.read_pptx', '.mkdir()') in _flow_hits(source, 'read_pptx')
    assert _flow_hits(source, 'read_cached') == []      # 이름 조각만 캐시 안으로 — 사용자 위치 아님
    assert _flow_hits(source, 'by_id') == []            # 경로 키가 아닌 입력(id)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
