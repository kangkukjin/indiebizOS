"""Driver discovery briefs use current guide sections, not duplicated contracts."""
import json

import boot_paths  # noqa: F401
import guide_registry as guides
import pytest

pytestmark = pytest.mark.usefixtures("installed_functions")


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    directory = tmp_path / "guides"
    directory.mkdir()
    monkeypatch.setattr(guides, "DATA_PATH", tmp_path)
    monkeypatch.setattr(guides, "GUIDES_DIR", directory)

    def write(entries, files):
        (tmp_path / "guide_db.json").write_text(json.dumps({"guides": entries}))
        for name, content in files.items():
            (directory / name).write_text(content)
    return write


def test_briefs_are_opt_in_selected_deduplicated_and_live(catalog):
    entries = [{"file": "robot.md", "control_brief_section": "Call"},
               {"file": "other.md", "control_brief_section": "Call"},
               {"file": "plain.md"}]
    files = {"robot.md": "# Robot\n## Call\nDo & verify.\n## Details\nPRIVATE LONG DETAILS",
             "other.md": "## Call\nUnrelated driver", "plain.md": "## Call\nNot opted in"}
    catalog(entries, files)
    first = guides.control_briefs(["robot.md", "robot.md", "plain.md"])
    assert len(first) == 1 and first[0]["text"] == "## Call\nDo & verify."
    assert first[0]["section"] == "Call" and len(first[0]["content_hash"]) == 64
    files["robot.md"] = files["robot.md"].replace("Do & verify.", "New contract; verify.")
    catalog(entries, files)
    second = guides.control_briefs(["robot.md"])[0]
    assert "New contract" in second["text"]
    assert second["content_hash"] != first[0]["content_hash"]
    assert guides.control_briefs([]) == []


@pytest.mark.parametrize("content", [
    "## Different\nNo exact match", "## Call\nA\n## Call\nB",
    "## Call\n" + "x" * 1800,
])
def test_invalid_or_oversize_brief_is_omitted_whole(catalog, content):
    catalog([{"file": "robot.md", "control_brief_section": "Call"}], {"robot.md": content})
    assert guides.control_briefs(["robot.md"]) == []


def test_briefs_refuse_catalog_conflicts_and_unsafe_paths(catalog):
    catalog([{"file": "robot.md", "control_brief_section": "Call"}] * 2 + [
        {"file": "../outside.md", "control_brief_section": "Call"},
        {"file": "missing.md", "control_brief_section": "Call"}],
        {"robot.md": "## Call\nDo & verify."})
    assert guides.control_briefs(["robot.md", "../outside.md", "missing.md"]) == []


@pytest.mark.parametrize("modern", [False, True])
def test_driver_catalog_preserves_legacy_guide_without_inventing_installation(catalog, modern):
    legacy = {"file": "robot.md", "control_platforms": ["robot-os"],
              "control_callables": ["script:robot"], "control_brief_section": "Call"}
    catalog([legacy], {"robot.md": "## Call\nCall and verify."})
    result = guides.device_drivers("robot-os", "any-adapter")
    assert result["components"] == result["conflicts"] == []
    assert result["items"][0]["id"] == "robot"
    assert result["items"][0]["callables"] == ["script:robot"]
    second = ({"file": "other.md", "driver": {"id": "other", "platforms": ["robot-os"], "primary": True}}
              if modern else {"file": "other.md", "control_platforms": ["robot-os"]})
    catalog([legacy, second], {"other.md": "## Call\nDifferent contract."})
    result = guides.device_drivers("robot-os", "any-adapter")
    assert result["items"] == []
    assert set(result["conflicts"]) == {"legacy_platform_conflict:robot:robot-os",
                                       "legacy_platform_conflict:other:robot-os"}


def test_briefs_bound_total_without_cutting_a_contract(catalog):
    files = {f"{i}.md": "## Call\n" + "x" * 1490 for i in range(4)}
    catalog([{"file": name, "control_brief_section": "Call"} for name in files], files)
    result = guides.control_briefs(files)
    assert len(result) == 2
    assert all(b["text"] == files[b["file"]] for b in result)


@pytest.mark.parametrize('filename', ['android_control.md', 'pc_control.md', 'tv_control.md',
                                     'safari_control.md', 'chrome_control.md', 'browser_action.md',
                                     'folder_survey.md'])
def test_published_brief_fits_budget_and_compiles_call_examples(filename):
    import re
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_store import installed_definitions
    briefs = guides.control_briefs([filename])
    assert len(briefs) == 1
    calls = re.findall(r'`(\[(?:fn|limbs|self):[^`]+\]\{[^`]+)`', briefs[0]["text"])
    assert calls
    for call in calls:
        plan = compile_program("#!ibl edition=2\nreturn " + call,
                               load_registry(str(guides.DATA_PATH.parent)),
                               inputs={"폰": "selected-device", "원결과": {}, "PC": "__local__",
                                       "출력": "output-device", "TV": "selected-tv", "폴더": "selected-folder"},
                               definitions=installed_definitions())
        assert not plan.issues, plan.report()


def test_callable_briefs_only_use_exact_selected_unambiguous_bindings(catalog):
    catalog([
        {"file": "one.md", "control_brief_section": "Call",
         "control_callables": ["script:one", "fn:alias", "script:conflict"]},
        {"file": "two.md", "control_brief_section": "Call",
         "control_callables": ["script:two", "script:conflict"]},
    ], {"one.md": "## Call\nOne: verify and recover", "two.md": "## Call\nTwo"})
    assert guides.callable_control_briefs(['script:one', 'fn:alias']) == guides.control_briefs(['one.md'])
    assert guides.callable_control_briefs(['one', 'script:conflict', 'script:missing']) == []
    assert guides.callable_control_briefs([]) == []


@pytest.mark.parametrize('kind,identifier,surface', [
    ('app', 'com.test.App', 'app:com.test.app'), ('site', 'm.example.com', 'site:example.com')])
def test_surface_and_callable_discovery_share_live_brief_and_keep_pointer_on_omission(
        catalog, kind, identifier, surface):
    entry = {"file": "driver.md", "control_brief_section": "Call",
             "control_callables": ["script:driver"], "control_surfaces": [surface]}
    catalog([entry], {"driver.md": "## Call\nVerify; never resend unknown writes."})
    found = guides.surface_control_guide(kind, identifier)
    assert found['control_brief'] == guides.callable_control_briefs(['script:driver'])[0]
    catalog([entry], {"driver.md": "## Call\n" + 'x' * 1800})
    found = guides.surface_control_guide(kind, identifier)
    assert found['control_guide'] == 'driver.md' and 'control_brief' not in found


def test_published_device_briefs_fit_together_and_every_callable_maps_back():
    filenames = ['android_control.md', 'pc_control.md', 'tv_control.md']
    assert {b['file'] for b in guides.control_briefs(filenames)} == set(filenames)
    entries = json.loads((guides.DATA_PATH / 'guide_db.json').read_text())['guides']
    for entry in entries:
        for name in entry.get('control_callables', []):
            assert [b['file'] for b in guides.callable_control_briefs([name])] == [entry['file']]


def test_general_script_brief_reaches_discovery_and_matches_check_ack_semantics(tmp_path, monkeypatch):
    """요약의 초기 0건·부분 결과·상태 쓰기·ack 의미를 실제 부품으로 대조한다."""
    import importlib.util
    from reusable_catalog import discovery_payload
    path = guides.DATA_PATH / 'scripts' / '폴더변화.py'
    spec = importlib.util.spec_from_file_location('folder_watch_brief_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'STATE_DIR', tmp_path / 'state')
    folder = tmp_path / 'folder'
    folder.mkdir()
    (folder / 'old.txt').write_text('old')
    args = {'path': str(folder), 'commit': False, 'limit': 1}
    first = module.main(args)
    assert first['first_check'] and first['count'] == 0
    assert list(module.STATE_DIR.glob('*.json'))  # commit:false도 초기 기준을 기록한다.
    for name in ('new1.txt', 'new2.txt'):
        (folder / name).write_text(name)
    changed = module.main(args)
    assert changed['count'] == 2 and changed['omitted'] == 1 and len(changed['items']) == 1
    assert changed['awaiting_ack'] and not changed['committed']
    complete = module.main({**args, 'limit': 60})
    assert complete['count'] == len(complete['items']) == 2 and complete['omitted'] == 0
    assert module.main({'op': 'ack', 'path': str(folder)})['acked']
    assert module.main(args)['count'] == 0
    assert not module.main({'op': 'ack', 'path': str(folder)})['acked']

    payload = discovery_payload([{'id': 'script:폴더변화', 'contract_known': False}])
    brief, = payload['control_briefs']
    assert brief == guides.callable_control_briefs(['script:폴더변화'])[0]
    assert brief['file'] == 'folder_survey.md'
    for fact in ('commit:false', 'first_check:true,count:0', 'omitted>0', 'acked:false', '순수 읽기가 아니다'):
        assert fact in brief['text']
    assert payload['candidates'][0]['contract_known'] is False  # 가이드가 선언 계약을 꾸며내지 않는다.


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


def test_driver_ownership_shares_installation_but_separates_machine_and_phone():
    user = guides.device_drivers('windows', 'resident-v1', 'user_login')
    unit, = [c for c in user['components'] if c['location'] == 'device']
    assert unit['id'] == 'resident-helper'
    assert set(unit['drivers']) == {'pc_control', 'remote_pc_execution', 'remote_pc_installation'}
    machine = guides.device_drivers('windows', 'resident-v1', 'machine')
    assert {c['id'] for c in machine['components']} == {'managed-helper'}
    assert 'pc_control' not in {d['id'] for d in machine['items']}
    phone = guides.device_drivers('android', 'indiebiz-v1')
    assert [c['id'] for c in phone['components']] == ['phone-apk']
    assert set(phone['components'][0]['drivers']) == {'android_control', 'remote_phone'}
    tv = guides.device_drivers('tizen', 'network-api')
    assert all(c['location'] == 'hub' and c.get('updater') is None for c in tv['components'])
    assert not guides.device_drivers('unobserved', 'resident-v1')['items']
    # Discovery before enrollment is metadata only; no live registry is needed.
    before = guides.device_drivers('windows', 'resident-v1', surface='installation')
    assert [d['file'] for d in before['items']] == ['remote_pc_installation.md']


def test_driver_legacy_conflict_is_visible_and_not_chosen(catalog):
    catalog([{'file': 'one.md', 'control_platforms': ['windows'],
              'driver': {'id': 'one', 'platforms': ['darwin'], 'primary': True}}],
            {'one.md': '# One'})
    assert guides.driver_catalog()['conflicts'] == ['mapping_conflict:one:control_platforms']
    assert guides.device_drivers('darwin', 'local')['items'] == []
    assert guides.device_control_guides() == {}


def test_driver_mapping_change_invalidates_catalog_revision(catalog):
    catalog([{'file': 'one.md'}], {'one.md': '# One'})
    old = guides.catalog_revision()
    catalog([{'file': 'one.md', 'delivery': 'brief'}], {'one.md': '# One'})
    assert guides.catalog_revision() != old


def test_all_published_driver_calls_resolve_to_current_owned_brief():
    for driver in guides.driver_catalog()['drivers']:
        assert len(guides.control_briefs([driver['file']])) == 1
        for name in driver.get('callables', []):
            assert [b['file'] for b in guides.callable_control_briefs([name])] == [driver['file']]


@pytest.mark.parametrize('fence', ['```', '~~~'])
def test_section_read_preserves_code_comments_and_following_conditions(fence):
    source = f'# Guide\n## Transfer\n{fence}ibl\n# comment\n## Also code\nreturn 1\n{fence}\nRequired recovery\n## Next\nOther'
    result = guides.guide_read_view({'file': 'driver.md', 'content': source}, {'section': 'Transfer'})
    assert result['sections'] == ['Guide', 'Transfer', 'Next']
    assert 'Required recovery' in result['content'] and 'Other' not in result['content']
    assert f'\n{fence}\n' in result['content']


def test_only_complete_current_brief_can_replace_primary_summary(catalog):
    from xml.sax.saxutils import escape
    catalog([{'file': 'one.md', 'control_brief_section': 'Call'}], {'one.md': '## Call\nCall then verify'})
    brief = guides.control_briefs(['one.md'])[0]
    text = '<control_brief file="one.md" section="Call" content_hash="' + brief['content_hash'] + '">' + escape(brief['text']) + '</control_brief>'
    assert guides.has_current_brief('one.md', text)
    assert not guides.has_current_brief('one.md', text.replace('Call then verify', 'Call'))
    assert not guides.has_current_brief('one.md', text.replace(brief['content_hash'], 'old'))
