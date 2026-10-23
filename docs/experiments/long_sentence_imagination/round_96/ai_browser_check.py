"""Independent UI actions and Chrome/Node trace comparison on the frozen AI T1 artifact."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import json
import hashlib
import subprocess
from playwright.sync_api import sync_playwright

OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-23_96회차'
TAG = sys.argv[1] if len(sys.argv) > 1 else 'T1'
HERE = OUT / ('reference/ai_T1' if TAG == 'T1' else 'ai/artifacts/variant')
PREFIX = 'ai_independent' if TAG == 'T1' else 'ai_T2_independent'
checks = []


def check(name, passed, detail=None):
    checks.append({'name': name, 'passed': bool(passed), 'detail': detail})


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel='chrome')
    page = browser.new_page(viewport={'width': 1320, 'height': 720})
    errors, requests = [], []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('request', lambda r: requests.append(r.url))
    page.goto((HERE / 'index.html').as_uri())
    page.locator('#bPause').click()
    check('load_40_units', page.evaluate('APP.world.units.length') == 40)
    box = page.locator('#cv').bounding_box()
    point = lambda x, y: (box['x']+x, box['y']+y)
    page.mouse.move(*point(80, 200)); page.mouse.down()
    page.mouse.move(*point(200, 345), steps=6); page.mouse.up()
    check('drag_select_20', page.evaluate('Object.keys(APP.selected).length') == 20)
    page.mouse.click(*point(300, 260), button='right')
    check('move_queued', page.evaluate("APP.pending.at(-1).kind") == 'move')
    page.locator('#bPause').click(); page.wait_for_timeout(750); page.locator('#bPause').click()
    check('movement', page.evaluate("APP.world.byId['string:A1'].x") > 100)
    page.keyboard.press('s')
    page.locator('#bPause').click(); page.wait_for_timeout(150)
    a = page.evaluate('APP.world.units.filter(u=>u.team===1).map(u=>[u.x,u.y])')
    page.wait_for_timeout(200); page.locator('#bPause').click()
    b = page.evaluate('APP.world.units.filter(u=>u.team===1).map(u=>[u.x,u.y])')
    check('stop_holds', a == b)
    with page.expect_download() as d:
        page.locator('#bExport').click()
    replay = OUT / 'runs' / f'{PREFIX}_replay.json'; d.value.save_as(replay)
    record = json.loads(replay.read_text())
    scenario = record.get('scenario', record)
    # Public export wrapper is inspected, never inferred from a filename.
    if 'scenario' not in record and 'initial' in record:
        scenario = {**record['initial'], 'commands': record['commands'], 'ticks': record['ticks']}
    node = subprocess.run(['/usr/local/bin/node', '-e',
        'const e=require(process.argv[1]),fs=require("fs");process.stdout.write(JSON.stringify(e.simulate(JSON.parse(fs.readFileSync(0,"utf8")))));',
        str(HERE/'engine.js')], input=json.dumps(scenario), text=True, capture_output=True, timeout=20)
    check('node_replay_executes', node.returncode == 0, node.stderr[-1000:])
    if node.returncode == 0:
        result = json.loads(node.stdout)
        check('ui_to_node_final', result['final'] == page.evaluate('RTS.finalState(APP.world)'))
    page.locator('#fImport').set_input_files(str(replay))
    page.wait_for_function("APP.mode==='replay'&&APP.ended", timeout=10000)
    check('import_finished', page.evaluate('APP.mode') == 'replay')
    check('import_hash_match', '불일치' not in page.locator('#msg').inner_text())
    cases = json.loads((OUT/'reference/cases_variant.json').read_text())
    scenario = cases[0]['scenario']
    serialized = page.evaluate('(s)=>JSON.stringify(RTS.simulate(s))', scenario)
    signature = hashlib.sha256(serialized.encode()).hexdigest()
    expected = json.loads((OUT/'runs'/f'ai_{TAG}_comparison_variant.json').read_text())['results'][0]['trace_sha256']
    check('chrome_node_full_800_tick_trace', signature == expected, {'chrome': signature, 'node': expected})
    page.locator('#bRestart').click();page.locator('#bPause').click()
    check('restart', page.evaluate('APP.world.tick') < 3)
    page.screenshot(path=str(OUT/'runs'/f'{PREFIX}_ui.png'), full_page=True)
    check('offline', all(u.startswith('file:') for u in requests))
    check('no_errors', not errors, errors)
    browser.close()

result = {'checks': checks, 'passed': sum(c['passed'] for c in checks), 'total': len(checks)}
(OUT/'runs'/f'{PREFIX}_ui_checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False))
