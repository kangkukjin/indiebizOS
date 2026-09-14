"""감사된 패키지의 회원 변환. 경로·원문은 턴 안에서만 존재한다."""
import importlib.util
import re
import uuid

import member_runtime
from member_profile import fingerprint_ok, _package_dir


def transform(entry, params, command, exchange):
    name = entry.get("member_transform", "")
    if not re.fullmatch(r"[a-z_][a-z_0-9]*:[a-z_][a-z_0-9]*", name) or not fingerprint_ok(entry):
        return {"success": False, "error_type": "permission", "error": "회원 변환 재감사가 필요합니다"}
    state = member_runtime.current()
    if not state or state["cancel"].is_set():
        return {"success": False, "error_type": "cancelled", "error": "종료된 회원 턴"}
    try:
        module, function = name.split(":")
        source = _package_dir(entry["package"]) / (module + ".py")
        spec = importlib.util.spec_from_file_location("_member_" + module, source)
        implementation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(implementation)
        workspace = member_runtime.private_path("transfers/" + uuid.uuid4().hex + "/input").parent
        result = getattr(implementation, function)(params, command, exchange, workspace)
        if isinstance(result, dict) and result.get("success") is True:
            for file in result.get("files", []):
                if file.get("on") == "body" and isinstance(file.get("path"), str):
                    ref = "member-file:" + uuid.uuid4().hex
                    with state["lock"]:
                        state.setdefault("files", {})[ref] = file["path"]
                    file["ref"] = ref
        return result
    except Exception:
        # 라이브러리 예외에는 허브 절대경로가 들어간다. 회원에게 경로를 노출하지 않는다.
        return {"success": False, "error_type": "conversion", "error": "파일 형식·입력 범위 또는 변환 결과를 확인하세요"}


def resolve_references(params):
    """파일 경로 슬롯의 불투명 참조만 해소. 본문·산문·URL은 그대로 둔다."""
    result = dict(params)
    state = member_runtime.current() or {}
    files = state.get('files', {})
    for key in ('path', 'src', 'dest', 'output'):
        value = result.get(key)
        if isinstance(value, str) and value.startswith('member-file:'):
            if value not in files:
                raise ValueError('현재 턴에서 확인한 파일 참조가 아닙니다')
            result[key] = files[value]
    return result
