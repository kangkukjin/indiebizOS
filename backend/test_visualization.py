"""Chart coordinate, output and receipt contracts (long-sentence round 41)."""
import boot_paths  # noqa: F401
from pathlib import Path
from types import SimpleNamespace

import pytest
from common.pkg_utils import load_sibling
from ibl_run_journal import Journal, reusable_receipts
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]
HANDLER = ROOT / 'data/packages/installed/tools/visualization/handler.py'


@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))


def execute(registry, code, inputs=None, **kw):
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.report()
    return Runtime(plan, inputs, **kw).run()


@pytest.mark.parametrize('kind,args', [
    ('bar', 'x:["a","b"],y:[1,2]'),
    ('line', 'x:[1,2],y:[3,4]'),
    ('scatter', 'x:[1,2],y:[3,4]'),
    ('pie', 'labels:["a","b"],values:[1,2]'),
    ('bar', 'items:[{month:"a",v:1},{month:"b",v:2}],x:"month",y:"v"'),
    ('line', 'items:[{month:"a",v:1,w:2},{month:"b",v:2,w:3}],x:"month",y:["v","w"]'),
])
def test_chart_lists_and_column_selectors(registry, tmp_path, kind, args):
    path = tmp_path / f'{kind}.html'
    result = execute(registry, '[table:chart]{title:"test",chart_type:$kind,' + args + ',output_path:$path}',
                     {'kind': kind, 'path': str(path)})
    assert result['success'], result
    assert Path(result['value']['path']) == path
    assert 'Plotly.newPlot' in path.read_text()


@pytest.mark.parametrize('args', ['x:["a","b"],y:[1]', 'x:[],y:[]',
                                  'labels:["a"],values:[1,2]'])
def test_coordinate_mismatch_never_silently_truncates(registry, tmp_path, args):
    result = execute(registry, '[table:chart]{title:"test",chart_type:$kind,' + args + ',output_path:$path}',
                     {'kind': 'pie' if 'labels' in args else 'bar', 'path': str(tmp_path / 'bad.html')})
    assert not result['success'] and '같은 길이' in result['error']
    assert not (tmp_path / 'bad.html').exists()


def test_both_png_writers_honor_format_and_exact_stem_path(tmp_path):
    common = load_sibling(str(HANDLER), 'tool_common')
    captured = []
    class Figure:
        layout = SimpleNamespace()
        data = []
        def write_image(self, path, **kw):
            captured.append((path, kw))
            Path(path).write_bytes(b'png-renderer-double')
    path = tmp_path / 'stem'
    result = common.save_plotly_figure(Figure(), str(path), 'png')
    assert captured == [(str(path), {'format': 'png', 'scale': 2})]
    assert result['path'] == str(path) and path.exists()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.plot([1, 2])
    result = common.save_figure(fig, str(path), 'png')
    assert path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    assert not path.with_suffix('.png').exists()
    assert result['path'] == str(path)


def test_chart_preserves_unrelated_reads_but_invalidates_its_output(registry, tmp_path):
    source = tmp_path / 'input.txt'
    chart = tmp_path / 'chart.html'
    source.write_text('source')
    chart.write_text('old chart')
    code = '''$source=[self:read]{path:$source}
$old=[self:read]{path:$chart}
[table:chart]{title:"test",x:["a","b"],y:[1,2],chart_type:"bar",path:$chart}
return $source'''
    with Journal(tmp_path / 'journal', 'first') as journal:
        first = execute(registry, code, {'source': str(source), 'chart': str(chart)}, journal=journal)
        run_id = journal.run_id
    assert first['success'], first
    summary = first['continuation']
    assert summary['read_calls'] == 1
    exclusion = summary['read_exclusions'][0]
    assert exclusion['reason'] == 'overlapping_write'
    assert exclusion['action'] == 'table:chart' and exclusion['location']['line'] == 3
    assert exclusion['excluded_calls'] == 1
    receipts = reusable_receipts(tmp_path / 'journal', run_id)
    second = execute(registry, code.replace('$old=[self:read]{path:$chart}', ''), {'source': str(source), 'chart': str(chart)},
                     reusable=receipts, reuse_run=run_id)
    assert second['success'] and second['reuse']['reused_calls'] == 1, second


@pytest.mark.system
@pytest.mark.parametrize('payload', ['spec:{data:[{type:"bar",x:["a","b"],y:[1,2]}]}',
                                    'chart_type:"bar",table:{columns:["x","y"],rows:[["a",1],["b",2]]}'])
def test_png_renderer_accepts_extensionless_path(registry, tmp_path, payload):
    path = tmp_path / 'stem'
    result = execute(registry, '[table:chart]{title:"test",output_format:"png",output_path:$path,' + payload + '}',
                     {'path': str(path)})
    assert result['success'], result
    assert result['value']['path'] == str(path)
    assert path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    assert not path.with_suffix('.png').exists()


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
