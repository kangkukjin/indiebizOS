"""표면 바인딩 ①(2026-10-05): 앱 템플릿의 치환 폐지 — 원문 + inputs + declared_inputs.

docs/APP_COMMON_FOUNDATION_GAPS_2026_10_05.md §1-①. 계약:
  · declared_inputs 에 있고 inputs 에 없는 이름 = 미지정 — 호출 인자 자리에서는 그 인자가 생략되고(핸들러 기본값이 산다),
    f-문자열 보간에서는 빈 문자열, 그 밖의 자리는 UNSPECIFIED_INPUT 으로 거절.
  · 빈 문자열 입력은 표면이 미지정으로 보낸다(구형 "빈 입력=인자 삭제"와 같은 뜻). 명시 null 은 값이다.
  · 판본 1 요청은 declared_inputs 를 받지 않는다.
  · 검증기: edition 선언 필수, 1 은 legacy_reason 필수, 2 는 구형 {필드}·@노드 지정·파이프 축약 거절, $item 허용.
  · 포털 게이트: 판본 2 요청은 선언 원문과 글자 그대로 일치 + 입력 이름 ⊆ 템플릿 참조.
  · 회원 앱: edition 2 선언은 치환 없이 inputs 로 해소, 구형은 종전 치환.
"""
import importlib.util
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _appview():
    spec = importlib.util.spec_from_file_location("iblbuild_appview", ROOT / "scripts/iblbuild_appview.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "scripts"))
    spec.loader.exec_module(module)
    return module


def _run(request):
    from ibl_v2_entry import handle_request
    return handle_request({"edition": 2, **request}, str(ROOT), None)


# ── 컴파일러·런타임 ─────────────────────────────────────────────────────────

def test_unspecified_argument_is_omitted_and_provided_value_keeps_type():
    code = '[table:sort]{items: $rows, by: "a", descending: $desc}'
    rows = [{"a": 2}, {"a": 1}]
    omitted = _run({"code": code, "inputs": {"rows": rows}, "declared_inputs": ["rows", "desc"]})
    assert omitted["success"] and omitted["value"] == [{"a": 1}, {"a": 2}], omitted.get("error")
    given = _run({"code": code, "inputs": {"rows": rows, "desc": True}, "declared_inputs": ["rows", "desc"]})
    assert given["success"] and given["value"] == [{"a": 2}, {"a": 1}]


def test_unspecified_in_format_is_empty_text():
    r = _run({"code": 'f"x${q}y"', "inputs": {}, "declared_inputs": ["q"]})
    assert r["success"] and r["value"] == "xy"


def test_unspecified_elsewhere_is_rejected_with_hint():
    r = _run({"code": "$x = $q\n$x", "inputs": {}, "declared_inputs": ["q"]})
    assert r["success"] is False
    codes = [i["code"] for i in r.get("issues", [])]
    assert codes == ["UNSPECIFIED_INPUT"], codes
    assert "default" in (r["issues"][0].get("hint") or "")


def test_required_argument_omitted_is_an_honest_compile_issue():
    r = _run({"code": "[table:take]{items: $rows, n: $n}", "inputs": {"rows": [1, 2]}, "declared_inputs": ["rows", "n"], "check": True})
    assert r["ok"] is False and [i["code"] for i in r["issues"]] == ["MISSING_ARGUMENT"]
    assert r["unspecified_inputs"] == ["n"]


def test_item_record_and_explicit_null_are_values():
    r = _run({"code": '[table:take]{items: $item.rows, n: $n}', "inputs": {"item": {"rows": [1, 2, 3]}, "n": 2},
              "declared_inputs": ["n", "item"]})
    assert r["success"] and r["value"] == [1, 2]
    null = _run({"code": "$q", "inputs": {"q": None}, "declared_inputs": ["q"]})
    assert null["success"] and null["value"] is None


def test_declared_inputs_rejected_on_edition_1_and_bad_names():
    r = _run({"code": "[table:take]{items: $rows, n: 1}", "edition": 1, "declared_inputs": ["rows"]})
    assert r["success"] is False and "판본 2" in r["error"]
    bad = _run({"code": "$it", "inputs": {}, "declared_inputs": ["it"]})
    assert bad["success"] is False and "declared_inputs" in bad["error"]


# ── 검증기(빌드) ────────────────────────────────────────────────────────────

QUALIFIED = {"sense:search", "self:read", "table:take"}


def _block(action, **extra):
    return {"inputs": [{"key": "q", "type": "text"}], "action": action,
            "view": [{"type": "card_list", "from": "items", "card": {"title": "{title}"}}], **extra}


def test_validator_requires_edition_and_reason_for_legacy():
    av = _appview()
    none = av._validate_app_block("t", _block('[sense:search]{query: $q}'), QUALIFIED)
    assert any("edition 선언 필수" in i for i in none), none
    legacy = av._validate_app_block("t", _block('[sense:search]{query: "$q"}', edition=1), QUALIFIED)
    assert any("legacy_reason" in i for i in legacy), legacy
    ok = av._validate_app_block("t", _block('[sense:search]{query: "$q"}@hub', edition=1, legacy_reason="@hub"), QUALIFIED)
    assert ok == [], ok
    inherited = av._validate_app_block("t", _block('[sense:search]{query: $q}'), QUALIFIED, {"edition": 2})
    assert inherited == [], inherited


def test_validator_edition2_rejects_legacy_syntax_and_allows_item():
    av = _appview()
    row = av._validate_app_block("t", _block('[sense:search]{query: "{title}"}', edition=2), QUALIFIED)
    assert any("$item" in i for i in row), row
    hub = av._validate_app_block("t", _block('[sense:search]{query: $q}@hub', edition=2), QUALIFIED)
    assert hub == [], hub   # @노드 지정은 판본 2 도 받는다(2026-10-05 이월)
    pipe = av._validate_app_block("t", _block('[sense:search]{query: $q} | sort: title desc', edition=2), QUALIFIED)
    assert any("파이프 축약" in i for i in pipe), pipe
    item = av._validate_app_block("t", _block('[self:read]{path: $item.path, q: f"${q}"}', edition=2), QUALIFIED)
    assert item == [], item
    # 템플릿 안에서 묶인 이름(대입·람다 인자)은 입력이 아니다
    bound = av._validate_app_block("t", _block('$s = [self:read]{path: $q}; $s.data.items >> [table:take]{n: 1} >> [table:take]{n: len(($r) => $r.id)}', edition=2), QUALIFIED)
    assert not any("$s" in i or "$r" in i for i in bound), bound
    assert av._template_input_names('$s = [a:b]{x: $q}; ($r, $t) => $r.id != $item.id') == {"q", "item"}
    typo = av._validate_app_block("t", _block('[sense:search]{query: $qury}', edition=2), QUALIFIED)
    assert any("$qury" in i for i in typo), typo


def test_edition2_compile_guard_catches_bad_template_and_warns_on_unregistered_fn():
    av = _appview()
    data = {"nodes": {"sense": {"actions": {"search": {"app": {
        "edition": 2, "icon": "x", "name": "x",
        "modes": [{"name": "a", "action": '[table:take]{items: $rows, n: $n, bogus: 1}', "view": []},
                  {"name": "b", "action": '[fn:없는관용구]{q: $q}', "view": []}]}}}}}}
    issues, warnings = av.check_app_templates_edition2(data, ROOT)
    assert any("UNKNOWN_ARGUMENT" in i and "bogus" in i for i in issues), issues
    assert any("등록된 함수가 없습니다" in w for w in warnings), warnings


# ── 포털 게이트 ─────────────────────────────────────────────────────────────

def _portal_core():
    sys.path.insert(0, str(ROOT / "data/packages/installed/tools/community-portal"))
    spec = importlib.util.spec_from_file_location("_t_portal_core", ROOT / "data/packages/installed/tools/community-portal/portal_core.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_portal_template_allowed_requires_verbatim_template_and_declared_names():
    pc = _portal_core()
    tpls = ['[sense:search]{query: $q, limit: 5}', '[sense:search]{query: $item.title, limit: $n}']
    assert pc.template_allowed('[sense:search]{query: $q, limit: 5}', {"q": "ai"}, ["q"], tpls)[0]
    assert pc.template_allowed('[sense:search]{query: $item.title, limit: $n}', {"item": {"title": "t", "meta": {"k": 1}}}, ["n", "item"], tpls)[0]
    assert not pc.template_allowed('[sense:search]{query: $item.title, limit: $n}', {"item": {"rows": [1]}}, ["n", "item"], tpls)[0]  # 행 값은 스칼라만
    assert not pc.template_allowed('[sense:search]{query: $q, limit: 50}', {"q": "ai"}, ["q"], tpls)[0]   # 고정 인자 변조
    assert not pc.template_allowed('[sense:search]{query: $q, limit: 5}', {"q": "ai", "zz": 1}, ["q"], tpls)[0]  # 미선언 입력
    assert not pc.template_allowed('[sense:search]{query: $q, limit: 5}', {"q": "x" * 500}, ["q"], tpls)[0]      # 길이
    ok, why = pc.template_allowed('[self:read]{path: $p}', {"p": "a"}, ["p"], ['[self:read]{path: $p}'])
    assert not ok and "허용되지 않는 동작" in why


# ── 회원 앱 해소 ────────────────────────────────────────────────────────────

def test_member_resolve_edition2_passes_inputs_without_substitution():
    from member_app_actions import compile_apps, resolve
    source = [{"id": "docs", "edition": 2, "inputs": [{"key": "path"}, {"key": "limit", "default": "5"}],
               "action": '[self:list]{path: $path, limit: $limit}',
               "view": [{"item_click": {"action": '[self:read]{path: $item.path, note: $item.meta.note}'}}]}]
    wire, registry = compile_apps(source)
    assert "[self:" not in __import__("json").dumps(wire)
    r = resolve(registry, "docs", {"path": "a/b.md", "limit": ""})
    assert r["edition"] == 2 and r["code"] == '[self:list]{path: $path, limit: $limit}'
    assert r["inputs"] == {"path": "a/b.md"} and sorted(r["declared_inputs"]) == ["limit", "path"]
    clicked = resolve(registry, "docs:view:0:item_click", {"_row": {"path": "x.md", "meta.note": "n"}})
    assert clicked["inputs"]["item"] == {"path": "x.md", "meta": {"note": "n"}} and "item" in clicked["declared_inputs"]
    with pytest.raises(ValueError):
        resolve(registry, "docs:view:0:item_click", {"_row": {"owner": "private"}})
    hostile = resolve(registry, "docs", {"path": '"} >> [self:config]{}'})
    assert hostile["code"] == '[self:list]{path: $path, limit: $limit}' and hostile["inputs"]["path"].startswith('"}')


def test_member_resolve_legacy_block_still_substitutes():
    from member_app_actions import compile_apps, resolve
    _, registry = compile_apps([{"id": "t", "action": '[sense:search]{query:"$query",limit:$limit}'}])
    r = resolve(registry, "t", {"query": "q", "limit": 3})
    assert "edition" not in r or r.get("edition") is None
    assert "limit:3" in r["code"] and '"q"' in r["code"]


# ── 앱 매니페스트: 잠든 패키지의 앱은 표면에서 빠진다 ───────────────────────────

def test_manifest_hides_apps_of_sleeping_packages(monkeypatch):
    import vocabulary_state as vs
    from api_launcher_web import _derive_instruments
    owner = vs.action_owner("self", "record")
    assert owner, "record-ops 의 self:record 소유 패키지를 찾아야 한다"
    real = vs.is_active

    monkeypatch.setattr(vs, "is_active", lambda pid, root=None, profile=None: False if pid == owner else real(pid, root, profile))
    asleep_ids = {i["id"] for i in _derive_instruments(include_standalone=False)["instruments"]}
    assert "managed_records" not in asleep_ids

    monkeypatch.setattr(vs, "is_active", lambda pid, root=None, profile=None: True if pid == owner else real(pid, root, profile))
    awake = {i["id"]: i for i in _derive_instruments(include_standalone=False)["instruments"]}
    assert "managed_records" in awake and awake["managed_records"].get("edition") == 2


# ── @노드 지정(판본 1 문법의 이월) ───────────────────────────────────────────

def test_node_annotation_parses_compiles_and_reaches_the_engine(monkeypatch):
    from project_manager import ProjectManager
    pp = str(ProjectManager().get_project_path("앱모드"))
    ok = _run({"code": '[self:list]{path: "."}@hub', "inputs": {}, "check": True})
    assert ok["ok"] is True, ok.get("issues")
    bad = _run({"code": "[fn:없음]{}@hub", "inputs": {}, "check": True})
    assert "TARGET_NODE" in [i["code"] for i in bad["issues"]]
    import ibl_engine
    captured = []
    real = ibl_engine.execute_ibl
    def spy(step, project_path, agent_id=None, **kw):
        captured.append(dict(step))
        return real(step, project_path, agent_id=agent_id, **kw)
    monkeypatch.setattr(ibl_engine, "execute_ibl", spy)
    from ibl_v2_entry import handle_request
    r = handle_request({"code": '[self:list]{path: "outputs"}@hub', "edition": 2, "inputs": {}}, pp, None)
    assert r["success"], r.get("error")
    assert [c.get("target_node") for c in captured] == ["hub"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
