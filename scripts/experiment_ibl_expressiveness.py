"""같은 입력·결과로 언어 개정의 소스 길이와 실제 실행을 비교한다(AI 0)."""
import boot_paths  # noqa: F401
import argparse
import json
from pathlib import Path

from ibl_boundary_probe import probe
from ibl_typecheck import typecheck_code

ROOT = Path(__file__).resolve().parents[1]


def q(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def comparisons():
    seed = '[table:take]{items:[{id:"a",name:"A",price:3}],n:1}'
    yield 'projection', seed + ' >> [table:each]{do:' + q(
        '[table:take]{items:[{label:$it.name,source:{id:$it.id},prices:[$it.price]}],n:1}') + '}', (
        seed + ' >> [table:select]{columns:{label:"name",source:{id:"id"},prices:["price"]}}'), [
            {'label': 'A', 'source': {'id': 'a'}, 'prices': [3]}]
    seed = ('$a=[table:take]{items:[{id:"a"},{id:"b"},{id:"c"}],n:3};'
            '$b=[table:take]{items:[{id:"a",n:2},{id:"c",n:1}],n:2};')
    old = ('$yes=$a & $b >> [table:join]{on:"id"};'
           '$no=$a >> [table:filter]{where:{field:"id",op:"not_in",value:"${b.items.*.id}"}}'
           ' >> [table:compute]{set:{n:"0"}};'
           '$yes & $no >> [table:union] >> [table:sort]{by:"id"}')
    new = '$a & $b >> [table:join]{on:"id",how:"left",defaults:{n:0}} >> [table:sort]{by:"id"}'
    yield 'left_join', seed + old, seed + new, [{'id': 'a', 'n': 2}, {'id': 'b', 'n': 0}, {'id': 'c', 'n': 1}]
    body = ('$x=[table:take]{items:[$it],n:1};'
            '[if:count($x.items)>0]{$x >> [table:compute]{set:{label:"\'item \' + str(id)"}}}')
    head = '[table:each]{items:[{id:1},{id:2}],parallel:2'
    yield 'code_block', head + ',do:' + q(body) + '}', head + '} {' + body + '}', [
        {'id': 1, 'label': 'item 1'}, {'id': 2, 'label': 'item 2'}]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, old, new, expected in comparisons():
        row = {'name': name, 'expected': expected}
        for label, code in [('before', old), ('after', new)]:
            result = probe(dict(id=name, code=code, expected=expected, error=False, contains=None))
            check = typecheck_code(code)
            row[label] = {'chars': len(code), 'ok': result['ok'], 'preflight': check['ok'],
                          'actual': result.get('actual'), 'error': result.get('error_text')}
            (args.out / f'{name}.{label}.ibl').write_text(code + '\n')
        row['saved_chars'] = len(old) - len(new)
        row['saved_percent'] = round((1 - len(new) / len(old)) * 100, 1)
        rows.append(row)
    report = {'ai_calls': 0, 'scope': '동일 입력의 결정론 변환; 전체 보고서·모델 품질/비용 측정 아님', 'cases': rows}
    (args.out / 'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not all(r[label]['ok'] and r[label]['preflight'] for r in rows for label in ['before', 'after']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
