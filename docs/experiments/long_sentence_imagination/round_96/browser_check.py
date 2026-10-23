"""Exercise the trainer artifact's actual controls in an isolated browser."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import json
from playwright.sync_api import sync_playwright

OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-23_96회차'
LABEL = sys.argv[1] if len(sys.argv) > 1 else 'artifacts'
PREFIX = 'trainer_ui' if LABEL == 'artifacts' else 'trainer_v4_ui'
checks = []


def check(name, value):
    checks.append({'name': name, 'passed': bool(value)})


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel='chrome')
    page = browser.new_page(viewport={'width': 1180, 'height': 950}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto((OUT / 'trainer' / LABEL / 'index.html').as_uri())
    check('initial_40_units', page.evaluate('lab.world.state().length') == 40)
    canvas = page.locator('#field').bounding_box()

    def point(x, y):
        return (canvas['x'] + x / 960 * canvas['width'], canvas['y'] + y / 544 * canvas['height'])

    page.mouse.move(*point(100, 170))
    page.mouse.down()
    page.mouse.move(*point(210, 270), steps=10)
    page.mouse.up()
    check('drag_selection_20', page.evaluate('lab.selected.length') == 20)
    page.locator('#attackMove').click()
    page.mouse.click(*point(760, 272))
    check('attack_move_queued', page.evaluate("lab.world.scenario.commands.at(-1).kind") == 'attackMove')
    page.locator('#pause').click()
    page.wait_for_timeout(1400)
    page.locator('#pause').click()
    tick = page.evaluate('lab.world.tick')
    check('animation_advanced', tick > 10)
    check('movement_visible', page.evaluate('lab.world.state().some(u=>u.team===0&&u.x>200)'))
    page.locator('#stop').click()
    check('stop_queued', page.evaluate("lab.world.scenario.commands.at(-1).kind") == 'stop')
    # Real resume/pause tests that stop actually holds the selected squad.
    page.locator('#pause').click()
    page.wait_for_timeout(100)
    a = page.evaluate('lab.world.state().filter(u=>u.team===0).map(u=>[u.id,u.x,u.y])')
    page.wait_for_timeout(350)
    page.locator('#pause').click()
    b = page.evaluate('lab.world.state().filter(u=>u.team===0).map(u=>[u.id,u.x,u.y])')
    check('stop_holds_positions', a == b)
    with page.expect_download() as d:
        page.locator('#export').click()
    replay = OUT / 'runs' / f'{PREFIX}_replay.json'
    d.value.save_as(replay)
    checkpoint = page.evaluate('lab.world.state()')
    reproduced = page.evaluate('(s)=>RTS.simulate(s).final', json.loads(replay.read_text()))
    check('export_exact_replay', checkpoint == reproduced)
    page.locator('#reset').click()
    check('reset_tick_zero', page.evaluate('lab.world.tick') == 0)
    page.locator('#import').set_input_files(str(replay))
    page.wait_for_timeout(250)
    check('import_replays', page.evaluate('lab.world.tick') > 0)
    page.locator('#pause').click()
    page.screenshot(path=str(OUT / 'runs' / f'{PREFIX}.png'), full_page=True)
    check('no_browser_errors', not errors)
    browser.close()

result = {'checks': checks, 'errors': errors, 'passed': all(c['passed'] for c in checks)}
(OUT / 'runs' / f'{PREFIX}_checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False))
