"""Prepare inputs and HTTP envelopes. No execution of the training solution."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import json

HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-23_96회차'


def squad(team, n=20):
    return [{'id': ('R' if team else 'B') + f'{i:02}', 'team': team,
             'x': (744 if team else 120) + (i % 5) * 18,
             'y': 160 + (i // 5) * 18} for i in range(n)]


def scenario(name, kind, units, commands=None, ticks=600, gap=96, walls=True):
    return {'kind': kind, 'scenario': {'name': name, 'width': 960, 'height': 544,
        'walls': [{'x': 460, 'y': 0, 'w': 40, 'h': (544-gap)/2},
                  {'x': 460, 'y': (544+gap)/2, 'w': 40, 'h': (544-gap)/2}] if walls else [],
        'units': units, 'commands': commands or [], 'ticks': ticks, 'seed': 96}}


def cases(variant=False):
    n = 40 if variant else 20
    units = squad(0, n) + squad(1, n)
    attack = [{'tick': 0, 'ids': [u['id'] for u in units if u['team'] == team],
               'kind': 'attackMove', 'x': 760 if team == 0 else 160, 'y': 264}
              for team in (0, 1)]
    solo = squad(0, n)
    duel = [{'id': 'a', 'team': 0, 'x': 100, 'y': 100},
            {'id': 'b', 'team': 1, 'x': 200, 'y': 100}]
    far = [{**duel[0]}, {**duel[1], 'x': 300}]
    base = [scenario('battle_40v40' if variant else 'battle_20v20', 'battle', units,
                      attack, 800, 48 if variant else 96),
            scenario('passage_narrow' if variant else 'passage', 'passage', solo,
                     [{'tick': 0, 'ids': [u['id'] for u in solo], 'kind': 'move', 'x': 760, 'y': 264}],
                     1000, 48 if variant else 96),
            scenario('duel', 'duel', duel, ticks=110, walls=False),
            scenario('out_of_range', 'out_of_range', far, ticks=100, walls=False),
            scenario('stop', 'stop', [{'id': 'a', 'team': 0, 'x': 80, 'y': 104}],
                     [{'tick': 0, 'ids': ['a'], 'kind': 'move', 'x': 700, 'y': 104},
                      {'tick': 20, 'ids': ['a'], 'kind': 'stop'}], 100, walls=False),
            scenario('empty', 'empty', [], ticks=30, walls=False)]
    if variant:
        reverse = json.loads(json.dumps(base[0]))
        reverse['scenario']['name'] = 'battle_reversed'
        reverse['scenario']['units'].reverse()
        base.append(reverse)
    return base


def make(version=0, variant=False):
    label = f'trainer_{"variant" if variant else "base"}_v{version}'
    artifact = OUT / 'trainer' / (('variant' if variant else 'artifacts') + (f'_v{version}' if version>=3 else ''))
    artifact.mkdir(exist_ok=True)
    engine = HERE / f'engine_v{version}.js'
    if not engine.exists():
        engine = HERE / 'engine_v0.js'
    html = HERE / f'index_v{version}.html'
    if not html.exists():
        html = HERE / 'index_v0.html'
    program = HERE / f'main_v{version}.ibl'
    if not program.exists():
        program = HERE / 'main_v0.ibl'
    body = {'code': program.read_text(), 'edition': 2, 'project_id': str(ROOT), 'origin': 'training',
        'budget': {'steps': 300000, 'rows': 20000}, 'inputs': {
            '입력': str(OUT / 'trainer/inputs'), '출력': str(artifact), '판본': 2 if variant else 1,
            '공식수치': {'hp': 40, 'ground_damage': 6, 'range': 4, 'cool': 15, 'armor': 0, 'sight': 7,
                'url': 'https://classic.battle.net/scc/terran/ustats.shtml'},
            '근사규칙': {'pixels_per_range_unit': 32, 'ticks_per_second': 24, 'speed_pixels_per_tick': 2,
                'collision_radius': 6, 'navigation': '16px four-neighbor distance field',
                'firing': 'instantaneous simultaneous damage, cooldown15 interpreted as ticks',
                'targeting': 'nearest visible within224px, id tie-break, rotating movement priority',
                'fog_of_war': 'not rendered', 'original_rules_observed': False},
            '파일': [{'name': 'engine.js', 'content': engine.read_text()},
                    {'name': 'index.html', 'content': html.read_text()},
                    {'name': 'measure.js', 'content': (HERE / 'measure.js').read_text()}],
            '어댑터': (HERE / 'node_adapter.py').read_text(), '사례들': cases(variant)}}
    (OUT / 'runs' / f'{label}_request.json').write_text(json.dumps(body, ensure_ascii=False, indent=2))
    (OUT / 'reference' / f'cases_{"variant" if variant else "base"}.json').write_text(
        json.dumps(cases(variant), ensure_ascii=False, indent=2))
    print(label)


if __name__ == '__main__':
    make(int(sys.argv[1]) if len(sys.argv)>1 else 0, '--variant' in sys.argv)
