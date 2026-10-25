"""ep3176 실제 실패의 축소 재현과 대입·회상·파일 통화 불변식."""
import json
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ibl_boundary_probe import probe
from ibl_boundary_cases import literal as q
from idiom_experiment_worker import load
from test_names_first_recall_2026_09_05 import env, _add  # noqa: F401






def test_user_object_value_is_not_an_assignment_envelope():
    from common.currency import value_result_payload
    obj = {'value': [1], 'assigned': 'user', 'success': True}
    assert value_result_payload(obj) == (False, obj)




def test_recall_exposes_parent_functions_as_currency_without_bodies(env):
    tree, db = env
    child = '보고서/부동산 발굴'
    _add(db, '지역별 기록', '[self:time]{}', child)
    pid = _add(db, '최신 보고서 읽기', '$return=[self:read]{path:$파일}', '보고서', category='phrase', alias='공통읽기', ok=2)
    _add(db, '관계없는 함수', '[self:time]{}', '오디오', category='phrase', alias='관계없음')
    out = tree.recall(child, db)
    entry = next(r for r in out['items'] if r['id'] == pid)
    assert entry['topic'] == '보고서' and entry['success_rate'] == 1.0
    assert entry['call'].startswith('[fn:공통읽기]') and '[self:read]' not in entry['ibl_code']
    assert out['count'] == 2 and out['inherited_function_count'] == 1
    assert '상위 가지 보고서' in out['text'] and '관계없음' not in out['text']
    assert '[self:read]' in tree.recall(child, db, expand='공통읽기')['text']
    assert all('success_rate' in r for r in out['items'])
    dataops = load('_ep3176_dataops', Path(__file__).parents[1] / 'data/packages/installed/tools/data-ops/handler.py')
    from types import SimpleNamespace
    result = dataops.execute({'items': out['items'], 'columns': ['alias', 'intent', 'signature', 'returns', 'success_rate', 'bypass_count']}, SimpleNamespace(tool_name='data_select'))
    assert result['success'], result


def test_empty_recall_does_not_promise_automatic_naming(env):
    tree, db = env
    _add(db, '기록', '[self:time]{}', '기록')
    text = tree.recall('기록', db)['text']
    assert '자동 작명은 중단' in text
    assert '증류가 이름을 붙인다' not in text


@pytest.mark.parametrize('name', ['note.txt', '한글.json', 'subdir'])
def test_list_and_find_share_file_fields(tmp_path, name):
    from tool_context import ToolContext
    root = Path(__file__).parents[1]
    fs = load('_ep3176_fs', root / 'data/packages/installed/tools/system_essentials/handler.py')
    p = tmp_path / name
    p.mkdir() if name == 'subdir' else p.write_text('value')
    outputs = [json.loads(fs.execute({'path': str(tmp_path), 'pattern': name}, ToolContext(str(tmp_path), tool)))
               for tool in ['list_directory', 'glob_files']]
    fields = ['name', 'path', 'size', 'mtime', 'dir', 'is_dir']
    assert {k: outputs[0]['items'][0][k] for k in fields} == {k: outputs[1]['items'][0][k] for k in fields}
    dataops = load('_ep3176_list_projection', root / 'data/packages/installed/tools/data-ops/handler.py')
    from types import SimpleNamespace
    result = dataops.execute({'_prev_result': outputs[0], 'columns': ['name']}, SimpleNamespace(tool_name='data_select'))
    assert result['success'] and result['items'] == [{'name': name}]




if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
