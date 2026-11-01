"""Parsed content reuse must preserve freshness, safety and reader isolation."""
import os

import boot_paths  # noqa: F401
import pytest
import yaml

import yaml_content


@pytest.fixture(autouse=True)
def empty_cache():
    yaml_content._parsed.cache_clear()
    yield
    yaml_content._parsed.cache_clear()


def test_readers_share_parsing_but_never_mutable_values(monkeypatch):
    original = yaml.safe_load
    reads = []

    def parse(text):
        reads.append(text)
        return original(text)

    monkeypatch.setattr(yaml, 'safe_load', parse)
    text = 'first: &row {values: [1, 2]}\nsecond: *row\n'
    first = yaml_content.load_yaml(text)
    first['first']['values'].append(3)
    second = yaml_content.load_yaml(text)
    assert second == {'first': {'values': [1, 2]}, 'second': {'values': [1, 2]}}
    assert second['first'] is second['second']
    assert first['first'] is not second['first']
    assert reads == [text]


def test_rewritten_file_is_fresh_even_with_same_size_and_mtime(tmp_path):
    path = tmp_path / 'catalog.yaml'
    path.write_text('value: 1\n')
    before = path.stat()
    assert yaml_content.load_yaml(path.read_text()) == {'value': 1}
    path.write_text('value: 2\n')
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert yaml_content.load_yaml(path.read_text()) == {'value': 2}
    path.write_text('value: [\n')
    with pytest.raises(yaml.YAMLError):
        yaml_content.load_yaml(path.read_text())
    path.unlink()
    with pytest.raises(FileNotFoundError):
        yaml_content.load_yaml(path.read_text())


def test_unsafe_tag_is_rejected_even_after_cached_valid_document():
    assert yaml_content.load_yaml('value: 1') == {'value': 1}
    with pytest.raises(yaml.constructor.ConstructorError):
        yaml_content.load_yaml('!!python/object:builtins.object {}')


@pytest.mark.parametrize('text', ['', 'null', 'true', '42', '2026-11-02', '&self [*self]'])
def test_safe_loader_value_types_and_recursive_aliases_are_preserved(text):
    first = yaml_content.load_yaml(text)
    second = yaml_content.load_yaml(text)
    if text.startswith('&self'):
        assert first is first[0] and second is second[0] and first is not second
    else:
        expected = yaml.safe_load(text)
        assert type(first) is type(expected) and first == second == expected


def test_large_source_is_not_retained_and_entry_count_is_bounded(monkeypatch):
    monkeypatch.setattr(yaml_content, '_MAX_SOURCE_CHARS', 8)
    assert yaml_content.load_yaml('long: [1,2,3]') == {'long': [1, 2, 3]}
    assert yaml_content._parsed.cache_info().currsize == 0
    for value in range(40):
        yaml_content.load_yaml(str(value))
    assert yaml_content._parsed.cache_info().currsize == 32


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
