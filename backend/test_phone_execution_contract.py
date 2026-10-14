"""App-UID execution wire contract: unsupported semantics never silently disappear."""
import boot_paths  # noqa: F401
import pytest
from phone_execution_contract import validate


@pytest.mark.parametrize('command', [
    {'op': 'shell', 'cmd': 'id', 'timeout': True},
    {'op': 'shell', 'cmd': 'id', 'timeout': 3601},
    {'op': 'shell', 'cmd': 'id', 'shell': 'powershell'},
    {'op': 'shell', 'cmd': 'id', 'elevate': True},
    {'op': 'shell', 'cmd': 'id', 'mode': 'observe'},
    {'op': 'shell', 'cmd': 'id', 'env': {'A': 1}},
    {'op': 'shell', 'cmd': 'id', 'env': {'A=B': 'c'}},
    {'op': 'python', 'code': 'result = 1', 'stdin': ''},
    {'op': 'python', 'code': 'result = 1', 'env': {}},
    {'op': 'python', 'code': 'result = 1', 'reset': False},
    {'op': 'python', 'code': 'result = 1', 'inputs': []},
    {'op': 'python', 'code': 'x' * 65537},
    {'op': 'python', 'code': 'result = inputs', 'inputs': {'x': float('nan')}},
])
def test_invalid_contract(command):
    with pytest.raises(ValueError):
        validate(command)


def test_unicode_default_and_no_mutation():
    request = {'op': 'python', 'code': 'result = inputs["이름"]', 'inputs': {'이름': '삼성1'}}
    assert validate(request) == {**request, 'timeout': 120}
    assert 'timeout' not in request


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
