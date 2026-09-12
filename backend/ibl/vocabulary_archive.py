""".iblpack 컨테이너. 읽기·포장은 코드를 import하거나 실행하지 않는다."""
import ast
import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

import yaml

from vocabulary_state import package_path, valid_id

MAX_ARCHIVE = 20 * 1024 * 1024
MAX_EXPANDED = 100 * 1024 * 1024
MAX_FILES = 512
REQUIRED_FILES = {"handler.py", "ibl_actions.yaml", "examples.json"}


def safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or "\\" in name or ":" in name
            or any(p in {"", ".", ".."} or p.startswith(".") for p in name.split("/"))
            or any(ord(c) < 32 for c in name)):
        raise ValueError(f"허용하지 않는 묶음 경로: {name}")
    if path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".f32"}:
        raise ValueError(f"개인 데이터/키 파일은 배포할 수 없습니다: {name}")
    if path.name.lower() in {"credentials.json", "secrets.json", "activation.json", "agents.yaml"}:
        raise ValueError(f"개인 설정은 배포할 수 없습니다: {name}")
    return name


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def fragment_actions(content: bytes) -> dict:
    data = yaml.safe_load(content) or {}
    nodes = data.get("nodes") or {data.get("node"): {"actions": data.get("actions", {})}}
    return {f"{node}:{action}": cfg for node, group in nodes.items()
            for action, cfg in (group or {}).get("actions", {}).items()}


def validate_payload(manifest: dict, files: dict) -> list:
    if manifest.get("format") != "iblpack" or manifest.get("format_version") != 1:
        raise ValueError("지원하지 않는 .iblpack 형식 버전입니다")
    valid_id(manifest.get("id"))
    from packaging.version import Version
    Version(manifest.get("version", ""))
    if not REQUIRED_FILES <= files.keys():
        raise ValueError("필수 파일 누락: " + ", ".join(sorted(REQUIRED_FILES - files.keys())))
    declared = manifest.get("files")
    if not isinstance(declared, dict) or set(declared) != set(files):
        raise ValueError("manifest 파일 목록과 실제 내용이 다릅니다")
    for name, content in files.items():
        safe_name(name)
        if declared[name] != digest(content):
            raise ValueError(f"파일 지문 불일치: {name}")
    deps = manifest.get("dependencies", {})
    if not isinstance(deps, dict):
        raise ValueError("dependencies는 ID: 버전조건 객체여야 합니다")
    from packaging.specifiers import SpecifierSet
    for dep, spec in deps.items():
        valid_id(dep)
        SpecifierSet(spec)
        if dep == manifest["id"]:
            raise ValueError("자기 묶음에 의존할 수 없습니다")
    for key in ("requires_env", "requires_modules"):
        if not isinstance(manifest.get(key, []), list) or not all(
                isinstance(v, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v)
                for v in manifest.get(key, [])):
            raise ValueError(f"{key} 형식이 잘못되었습니다")
    for name, content in files.items():
        if name.endswith('.py'):
            try:
                ast.parse(content.decode('utf-8'), filename=name)
            except SyntaxError as exc:
                raise ValueError(f'{name} 구문 오류: {exc.msg}') from exc
    handler = ast.parse(files['handler.py'].decode('utf-8'))
    entries = [n for n in handler.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'execute']
    if not entries or len(entries[0].args.args) != 2:
        raise ValueError("handler.py에는 execute(tool_input, context)가 필요합니다")
    actions = fragment_actions(files['ibl_actions.yaml'])
    if not actions:
        raise ValueError("사용할 IBL 어휘 정의가 없습니다")
    # 외부 묶음이 backend-native 실행 함수를 새 어휘로 가장하지 못하게 한다.
    if any(not isinstance(cfg, dict) or cfg.get('router') != 'handler' for cfg in actions.values()):
        raise ValueError("공유 묶음의 어휘는 동봉한 handler로 실행해야 합니다")
    examples = json.loads(files['examples.json'])
    if not isinstance(examples, list) or not examples:
        raise ValueError("시딩 용례가 하나 이상 필요합니다")
    from ibl_parser import parse
    for example in examples:
        if not isinstance(example, dict) or not isinstance(example.get('intent'), str) or not example['intent'].strip():
            raise ValueError("용례에는 자연어 intent가 필요합니다")
        code = example.get('ibl_code')
        if not isinstance(code, str) or not parse(code):
            raise ValueError("용례의 IBL 문장이 올바르지 않습니다")
        if not set(re.findall(r"\[([a-z_]+:[a-z_0-9]+)\]", code)) & actions.keys():
            raise ValueError("용례는 동봉한 묶음의 어휘를 사용해야 합니다")
    return examples


def unpack(content: bytes) -> tuple:
    try:
        return _unpack(content)
    except (zipfile.BadZipFile, yaml.YAMLError, TypeError, AttributeError, KeyError) as exc:
        raise ValueError(f"어휘 파일 형식 오류: {exc}") from exc


def _unpack(content: bytes) -> tuple:
    if len(content) > MAX_ARCHIVE:
        raise ValueError("어휘 파일은 최대 20MB입니다")
    files = {}
    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise ValueError("올바른 .iblpack ZIP 파일이 아닙니다")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_EXPANDED:
            raise ValueError("어휘 파일의 압축 해제 한도를 초과합니다")
        for entry in infos:
            safe_name(entry.filename)
            mode = entry.external_attr >> 16
            if entry.is_dir() or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                raise ValueError("묶음에는 일반 파일만 담을 수 있습니다")
            if entry.filename in files:
                raise ValueError("중복된 파일 경로가 있습니다")
            files[entry.filename] = archive.read(entry)
    manifest = json.loads(files.pop('manifest.json', b'{}'))
    if not isinstance(manifest, dict):
        raise ValueError("manifest는 객체여야 합니다")
    examples = validate_payload(manifest, files)
    return manifest, files, examples


def pack(manifest: dict, files: dict) -> bytes:
    manifest = {k: v for k, v in manifest.items() if k not in {'archive_sha256', 'content_sha256'}}
    manifest = {**manifest, 'format': 'iblpack', 'format_version': 1,
                'files': {n: digest(v) for n, v in sorted(files.items())}}
    validate_payload(manifest, files)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        all_files = {**files, 'manifest.json': json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()}
        for name, content in sorted(all_files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, content)
    result = output.getvalue()
    unpack(result)
    return result


def export_package(package_id: str) -> bytes:
    return export_directory(package_path(package_id), package_id)


def export_directory(path: Path, package_id: str) -> bytes:
    """제작 폴더도 같은 파일 계약으로 포장한다."""
    manifest_path = path / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if manifest.get('format') == 'iblpack':
        names = list(manifest.get('files', {}))
    else:
        td = json.loads((path / 'tool.json').read_text())
        manifest = {'id': package_id, 'version': td.get('version', '1.0.0'),
                    'name': td.get('name', package_id), 'description': td.get('description', '')}
        # 옛 묶음은 코드·루트 설명만 자동 포장한다. 추가 정적 자원은 제작자가 manifest에 선언한다.
        excluded = {'data', 'outputs', 'logs', 'node_modules', '__pycache__', 'venv', '_archive'}
        names = [str(p.relative_to(path)) for p in path.rglob('*.py')
                 if not any(part.startswith('.') or part in excluded for part in p.relative_to(path).parts)]
        names += [n for n in ('ibl_actions.yaml', 'README.md', 'requirements.txt', 'package.json', 'examples.json') if (path / n).is_file()]
    files = {}
    for name in names:
        safe_name(name)
        target = path / name
        if target.is_symlink() or not target.resolve().is_relative_to(path.resolve()):
            raise ValueError(f"외부 파일 참조: {name}")
        files[name] = target.read_bytes()
    if 'examples.json' not in files and 'ibl_actions.yaml' in files:
        examples = []
        for key, cfg in fragment_actions(files['ibl_actions.yaml']).items():
            fixture = cfg.get('fixture')
            if fixture:
                examples.append({'intent': cfg.get('description', key), 'ibl_code': fixture,
                                 'nodes': key.split(':')[0], 'category': 'single'})
        files['examples.json'] = json.dumps(examples, ensure_ascii=False).encode()
    return pack(manifest, files)


def convert_legacy(text: str) -> bytes:
    """텍스트 v1은 메모리에서 변환만 한다. 옛 파일을 직접 설치하지 않는다."""
    match = re.search(r"===PACKAGE_START===(.*?)===PACKAGE_END===", text, re.S)
    if not match:
        raise ValueError("옛 패키지 경계가 없습니다")
    body = match.group(1)
    pid = re.search(r"^id:\s*(.+)$", body, re.M)
    if not pid:
        raise ValueError("옛 패키지 ID가 없습니다")
    files = {}
    for item in re.finditer(r"^===FILE:(.*?)===\s*\n(.*?)(?=^===FILE:|\Z)", body, re.M | re.S):
        name = safe_name(item.group(1))
        if name in files:
            raise ValueError("옛 파일 경로가 중복됩니다")
        files[name] = item.group(2).strip().encode()
    if 'examples.json' not in files:
        raise ValueError("변환에 배포 용례 examples.json이 필요합니다. 제작자가 보완해 주세요")
    files.pop('manifest.json', None)  # 옛 메타데이터는 새 manifest의 정본이 아니다.
    td = json.loads(files.get('tool.json', b'{}'))
    return pack({'id': valid_id(pid.group(1).strip()), 'version': td.get('version', '1.0.0'),
                 'name': td.get('name', pid.group(1).strip())}, files)
