"""47회차 상상훈련 — 연구자 구조 통화와 flatten 교재 계약 회귀."""

import importlib.util
from pathlib import Path

import pytest
import yaml


_ROOT = Path(__file__).resolve().parent.parent
_HANDLER = (_ROOT / "data" / "packages" / "installed" / "tools" /
            "study" / "handler.py")


def _load_handler():
    spec = importlib.util.spec_from_file_location("round47_study", _HANDLER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_researcher_find_keeps_identity_fields_as_columns(monkeypatch):
    study = _load_handler()
    monkeypatch.setattr(study, "_nanet_call", lambda *_args, **_kwargs: {
        "result": [[{
            "name_ko": "정은정",
            "name_en": "Jung Eunjeong",
            "orgName_ko": "서울대학교",
            "birthday": "19760101",
            "position": "교수",
            "lodID": "17382",
        }]]
    })

    result = study._nanet_author_find({"name": "정은정"})
    row = result["items"][0]

    assert row["name"] == "정은정"
    assert row["org"] == "서울대학교"
    assert row["birth_year"] == "1976"
    assert row["position"] == "교수"
    assert row["lodID"] == "17382"
    assert row["name_en"] == "Jung Eunjeong"
    # 검색계 공통 표면도 보존해 기존 소비자를 깨뜨리지 않는다.
    assert row["title"] == "정은정" and row["meta"] and row["summary"]


def test_researcher_coauthor_keeps_name_and_identity_fields(monkeypatch):
    study = _load_handler()
    monkeypatch.setattr(study, "_nanet_call", lambda *_args, **_kwargs: {
        "result": [{"authorList": [{
            "name": "차용준",
            "lodAuthorID": "3621",
            "inst": "한국대학교",
            "birth": "1980",
        }]}]
    })

    result = study._nanet_coauthor({"name": "정은정"})
    row = result["items"][0]

    assert row["name"] == "차용준"
    assert row["org"] == "한국대학교"
    assert row["birth_year"] == "1980"
    assert row["lodID"] == "3621"
    assert row["title"] == "차용준"


def test_catalog_teaches_current_researcher_and_flatten_contracts():
    nodes = yaml.safe_load((_ROOT / "data" / "ibl_nodes.yaml").read_text())
    researcher = nodes["nodes"]["sense"]["actions"]["researcher"]
    flatten = nodes["nodes"]["table"]["actions"]["flatten"]

    assert "name·org·birth_year·position·lodID" in researcher["target_description"]
    assert "name(연구자 이름" in researcher["target_description"]
    assert "each 결과" not in flatten["description"]
    assert "_result" not in flatten["target_description"]
    assert "flatten 없이" in flatten["target_description"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
