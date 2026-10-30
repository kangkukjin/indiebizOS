"""등록된 순수 변환 부품: 고정 입력/소스, 제한 자식 실행, 세대와 연결된 활성 판본."""
import json
from pathlib import Path
import sys
import tempfile

from file_script import strict_json
from component_registry import (sha, registry, home, active, object_path, store_object,
                                publish, active_source, covers_changes, atomic_json)
from script_process import run_process, check_invocation

MAX_BYTES = 4 * 1024 * 1024


def sandbox(command, directory):
    from coding_process import available
    if not available():
        raise RuntimeError('이 몸은 순수 부품의 제한 실행을 지원하지 않습니다(macOS 필요)')
    quote = lambda x: json.dumps(str(Path(x).resolve()))
    interpreter = Path(command[0]).resolve()
    reads = [Path(sys.base_prefix), Path('/System/Library'), Path('/usr/lib'), Path('/usr/share'),
             Path(directory)]
    policy = ['(version 1)', '(allow default)', '(deny network*)', '(deny file-read-data)',
              '(deny file-write*)', '(deny appleevent-send)', '(deny signal)', '(deny mach-lookup)',
              '(deny process-fork)', '(deny process-exec)',
              f'(allow process-exec (literal {quote(interpreter)}))',
              '(allow file-read-data ' + ' '.join(f'(subpath {quote(p)})' for p in reads) + ')',
              f'(allow file-write* (subpath {quote(directory)}))',
              '(allow file-read-data file-write-data (literal "/dev/null"))',
              '(allow file-read-data (literal "/"))',
              '(allow file-read-data (literal "/dev/urandom"))']
    return ['/usr/bin/sandbox-exec', '-p', '\n'.join(policy), *command]


def run(source, value, *, check=None):
    """인증·환경·호스트 import 없이 순수 transform(value)만 실행한다."""
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    if len(source) > MAX_BYTES or len(encoded) > MAX_BYTES:
        raise ValueError('부품 소스/입력 크기 한도 초과')
    with tempfile.TemporaryDirectory(prefix='indiebiz-component-') as tmp:
        root = Path(tmp).resolve()
        (root / 'implementation.py').write_bytes(source)
        bootstrap = (
            "import json,resource,sys; "
            "resource.setrlimit(resource.RLIMIT_FSIZE,(4194304,4194304)); "
            "resource.setrlimit(resource.RLIMIT_CPU,(5,5)); "
            "scope={}; exec(compile(open('implementation.py','rb').read(),'implementation.py','exec'),scope); "
            "value=scope['transform'](json.load(sys.stdin)); "
            "open('result.json','w').write(json.dumps(value,ensure_ascii=False,allow_nan=False))")
        app_python = Path(sys.base_prefix) / 'Resources/Python.app/Contents/MacOS/Python'
        interpreter = str((app_python if app_python.is_file() else
                           Path(getattr(sys, '_base_executable', sys.executable))).resolve())
        command = sandbox([interpreter, '-I', '-S', '-c', bootstrap], root)
        result = run_process(command, encoded, cwd=str(root),
                             env={'PATH': '/usr/bin:/bin', 'TMPDIR': str(root),
                                  'INDIEBIZ_REPAIR_CHILD': '1'},
                             timeout=10, check=check or check_invocation, terminate_descendants=True)
        output = root / 'result.json'
        if result['exit_code'] or result['timed_out'] or not output.is_file():
            raise ValueError(f'부품 실행 실패(exit={result["exit_code"]}): ' + result.get('stderr', '')[-3000:])
        if output.is_symlink() or output.stat().st_size > MAX_BYTES:
            raise ValueError('부품 반환 파일이 유효하지 않습니다')
        return strict_json(output.read_bytes())


def validate_output(spec, value):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError('부품 반환은 항목 목록이어야 합니다')
    for row in value:
        for key in spec['text_fields']:
            if not isinstance(row.get(key), str):
                raise ValueError('부품 반환 필드 오류: ' + key)
    return value


def verify(spec, source, *, check=None):
    if not spec.get('fixtures'):
        raise ValueError('보호된 부품 인수 검사가 없습니다')
    for fixture in spec['fixtures']:
        actual = validate_output(spec, run(source, fixture['input'], check=check))
        if actual != fixture['expected']:
            raise ValueError('기존 부품 인수 계약 불일치')
    return {'gate': 'component_contract', 'passed': True, 'version': sha(source),
            'cases': len(spec['fixtures']), 'contract_hash': spec['contract_hash']}


def call(component_id, value):
    from runtime_utils import get_source_root, get_code_root
    repo, code = get_source_root(), get_code_root()
    spec = registry(code)[component_id]
    source = active_source(repo, code, spec)
    try:
        return validate_output(spec, run(source, value))
    except (ValueError, RuntimeError) as exc:
        # 요청 원문은 인증 헤더가 없는 변환 입력뿐이다. 실패를 빈 항목으로 바꾸지 않는다.
        from uuid import uuid4
        ref = Path(repo) / 'data/script_runs' / ('component-' + uuid4().hex) / 'input.json'
        ref.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(ref, value)
        raise ValueError(f'{exc}; component={component_id}; source={Path(repo) / spec["source"]}; '
                         f'input_ref={ref}; source_version={sha(source)}') from exc
