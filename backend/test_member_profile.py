"""하나의 대상 안에서 op별 실행 위치와 기존 비공개 경계를 보존한다."""
import boot_paths  # noqa: F401
from copy import deepcopy
from pathlib import Path
import sys

import pytest
import yaml
import member_profile as mp
import principal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))


@pytest.fixture
def radio(monkeypatch):
    cfg = yaml.safe_load((ROOT/'data/packages/installed/tools/radio/ibl_actions.yaml').read_text())['nodes']['limbs']['actions']['radio']
    monkeypatch.setattr(mp, '_package_open', lambda *a, **kw: True)
    monkeypatch.setattr(mp, 'fingerprint_ok', lambda *a, **kw: True)
    return cfg


def test_hub_search_needs_no_playback_device_but_play_does(radio):
    with principal.narrow(principal.member('7',4,''),'media-test'):
        for op in ('search','stations'):
            assert mp.gate('limbs','radio',radio,params={'op':op}) is None
            e = mp.entry('limbs','radio',op=op)
            assert e['lands_on'] == 'hub' and 'member_transform' not in e
        assert mp.gate('limbs','radio',radio,params={'op':'play'})['error_type'] == 'no_body'
        for op in ('favorite_list','favorite_add','favorite_remove'):
            assert mp.gate('limbs','radio',radio,params={'op':op})['error_type'] == 'permission'
        assert mp.entry('limbs','radio',op='play')['member_transform'] == 'radio_member:control'


def test_hub_override_requires_fresh_audit(radio, monkeypatch):
    monkeypatch.setattr(mp,'fingerprint_ok',lambda *a,**kw:False)
    with principal.narrow(principal.member('7',4,''),'media-test'):
        assert mp.gate('limbs','radio',radio,params={'op':'search'})['error_type']=='permission'


def test_builder_rejects_effectful_or_unknown_hub_override(radio):
    from iblbuild_lands_on import validate_lands_on
    for op in ('play','typo'):
        cfg = deepcopy(radio)
        cfg['ops']['lands_on'][op] = 'hub'
        issues = validate_lands_on({'nodes':{'limbs':{'actions':{'radio':cfg}}}},ROOT)
        assert issues and any(op in issue for issue in issues)


def test_member_ibl_search_executes_on_hub_without_body(radio, monkeypatch):
    import ibl_engine
    calls=[]
    monkeypatch.setattr(ibl_engine,'_route_handler',lambda *a, **kw: calls.append((a,kw)) or {'items':[{'station_id':'s'}]})
    with principal.narrow(principal.member('7',4,''),'media-test'):
        result = ibl_engine.execute_ibl({'_node':'limbs','action':'radio','params':{'op':'search','query':'jazz'}}, str(ROOT))
    assert result.get('items') == [{'station_id':'s'}], result
    assert len(calls)==1


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
