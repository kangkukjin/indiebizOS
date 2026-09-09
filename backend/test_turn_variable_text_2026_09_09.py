"""숫자 턴 변수 재사용 및 파일 산문에 컴파일러 슬롯이 새던 현장 보고 회귀."""
import json
import uuid

import boot_paths  # noqa: F401
import pytest

from ibl_code_ir import Literal, Template, bind_template, link_template, pack, unpack
from system_tools import _execute_ibl_unified
from thread_context import actor_context


@pytest.fixture
def run(tmp_path, monkeypatch):
    import ibl_turn_vars

    monkeypatch.setattr(ibl_turn_vars, "store_path", lambda key: str(tmp_path / f"{key}.json"))
    task = f"task_test_{uuid.uuid4().hex}"

    def execute(code, **extra):
        with actor_context(agent_id="probe", task_id=task):
            result = _execute_ibl_unified({"code": code, **extra}, str(tmp_path), agent_id="probe")
        try:
            return json.loads(result)
        except (TypeError, ValueError):
            return result

    return execute


@pytest.mark.parametrize("reference", ["$1차", "${1차}", "${ 1차 }"])
def test_numeric_turn_variable_reuses_each_result(run, reference):
    first = run('$1차 = [table:each]{items:[{v:1}], do:"[table:take]{items:[$it], n:1}"}')
    assert first.get("success") is True, first
    assert first["turn_vars"]["live"] == ["1차"]
    second = run(reference + ' >> [table:take]{n:1}')
    assert second.get("success") is True, second
    assert second["turn_vars"]["injected"] == ["1차"]
    result = second["final_result"]
    if isinstance(result, str):
        result = json.loads(result)
    assert result["items"] == [{"v": 1}]


def test_partial_binding_updates_text_and_preserves_data_after_transport():
    template = link_template(Template('알려진 $일차 / 남은 $unknown', quoted=True), {"일차": 2_000_000})
    data = '$unknown {{_step_2000000_result}}'
    bound = bind_template(template, lambda name, path: (True, data), namespace="step")
    assert str(bound) == f'알려진 {data} / 남은 $unknown'
    restored = unpack(json.loads(json.dumps(pack(bound))))
    final = bind_template(restored, lambda name, path: (True, "끝"))
    assert isinstance(final, Literal)
    assert final == f'알려진 {data} / 남은 끝'


def test_self_edit_partial_interpolation_does_not_write_compiler_slot(run, tmp_path):
    run('$일차 = [table:take]{items:[{v:1}], n:1}')
    path = tmp_path / "note.md"
    path.write_text("old", encoding="utf-8")
    prose = '기록: `$미할당`은 그대로, `$일차`는 값.'
    result = run('[self:edit]' + json.dumps({
        "path": str(path), "old_string": "old", "new_string": prose,
    }, ensure_ascii=False))
    assert result.get("success") is True, result
    content = path.read_text(encoding="utf-8")
    assert '$미할당' in content and '"v": 1' in content
    assert '{{_step_' not in content and '$일차' not in content


@pytest.mark.parametrize("prefix", ["", '[table:take]{items:[{v:9}], n:1} >> '])
def test_files_keep_prose_literal_in_direct_and_pipeline_edit(run, tmp_path, prefix):
    run('$일차 = [table:take]{items:[{v:1}], n:1}')
    path = tmp_path / "literal.md"
    old = '기존 $일차 $items {{_step_0_result}}'
    prose = '기록: `$1차` → `${일차}`; $items; {{_step_0_result}}; $file:1'
    path.write_text(old, encoding="utf-8")
    result = run(prefix + '[self:edit]' + json.dumps({
        "path": str(path), "old_string": "$file:0", "new_string": "$file:1",
    }), files=[old, prose])
    assert path.read_text(encoding="utf-8") == prose, result


def test_inline_refs_still_bind_around_literal_file_data(run, tmp_path):
    run('$일차 = [table:take]{items:[{v:1}], n:1}')
    path = tmp_path / "mixed.md"
    path.write_text("old", encoding="utf-8")
    data = '$일차 $items {{_step_2000000_result}} $file:0'
    code = '[table:take]{items:[{v:9}], n:1} >> [self:edit]' + json.dumps({
        "path": str(path), "old_string": "old",
        "new_string": '첨부=$file:0 / 값=${일차.items.0.v} / 열=$items.v',
    }, ensure_ascii=False)
    result = run(code, files=[data])
    assert result.get("success") is True, result
    assert path.read_text(encoding="utf-8") == f'첨부={data} / 값=1 / 열=[9]'


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
