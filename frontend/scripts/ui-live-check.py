"""Verify owner UI against real API handlers after deferred apply (no interception)."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-url', required=True)
    parser.add_argument('--read-only', action='store_true',
                        help='Pre-activation render check; selection remains pending')
    args = parser.parse_args()
    origin = args.live_url.rstrip('/')
    catalog = json.loads((ROOT / 'frontend/i18n/catalog.json').read_text())

    def tr(source):
        return next(m['translations']['en'] for m in catalog['messages'].values()
                    if m['source'] == source and m.get('translations', {}).get('en'))

    reports = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        writes = []
        page.on('request', lambda request: writes.append({
            'method': request.method, 'url': request.url})
            if request.method not in {'GET', 'HEAD', 'OPTIONS'} else None)
        page.goto(origin + '/launcher/app')
        picker = page.get_by_label('Language / 언어').filter(visible=True).first
        picker.select_option('en')
        page.locator('#t-manual').click()
        panel = page.locator('#gearLever')
        labels = {'절약': 'Economy', '균형': 'Balanced', '최대': 'Maximum'}
        for source, label in labels.items():
            panel.locator('[data-act="gear"]').get_by_text(label, exact=True).wait_for()
            assert panel.locator('[data-act="gear"]').get_by_text(source, exact=True).count() == 0
        # Re-select the current gear: exercise real persistence without changing
        # the model used by any concurrently running work.
        before_response = context.request.get(origin + '/model-gear')
        assert before_response.ok
        before = before_response.json()
        current = before['current_gear']
        if not args.read_only:
            with page.expect_response(lambda r: r.url.endswith('/model-gear')
                                      and r.request.method == 'PUT') as response:
                panel.locator('[data-act="gear"]').get_by_text(labels[current], exact=True).click()
            result = response.value
            assert result.ok, {'status': result.status, 'body': result.text()}
            assert result.request.post_data_json == {'gear': current}
            assert result.json()['current_gear'] == current
            assert context.request.get(origin + '/model-gear').json()['current_gear'] == current
        panel.locator('[data-act="toggle"]').click()
        panel.get_by_text(tr('기어 프리셋 — 인지 축별 AI 모델 등급'), exact=True).wait_for()
        panel.locator('select').nth(11).wait_for()
        page.screenshot(path='/tmp/indiebiz-ui-live-remote-en.png')
        picker.select_option('ko')
        for source in labels:
            panel.locator('[data-act="gear"]').get_by_text(source, exact=True).wait_for()
        picker.select_option('en')
        page.reload()
        assert picker.input_value() == 'en'
        page.locator('#t-manual').click()
        for label in labels.values():
            panel.locator('[data-act="gear"]').get_by_text(label, exact=True).wait_for()
        if args.read_only:
            assert not writes, {'unexpectedWriteRequests': writes}
        reports.append({'phase': 'pre-activation' if args.read_only else 'active',
                        'selectionVerified': not args.read_only,
                        'pending': ['real gear selection'] if args.read_only else [],
                        'writeRequests': writes,
                        'surface': 'live remote', 'url': origin + '/launcher/app',
                        'gearButtons': list(labels.values()),
                        'realSelection': None if args.read_only else current,
                        'originalGearPreserved': context.request.get(origin + '/model-gear').json()['current_gear'] == current,
                        'languagePersistence': True, 'koreanReturn': True,
                        'dynamicSettings': True, 'apiInterception': False})
        browser.close()
    print(json.dumps(reports, ensure_ascii=False))


if __name__ == '__main__':
    main()
