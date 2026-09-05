"""
workflow_store.py - 워크플로 원장(data/workflows/*.yaml)의 저장·조회·삭제 + 등록 시점 문법 관문

2026-09-05 workflow_engine 에서 분리(1500줄 규칙 — 연쇄 실패 뿌리 진단이 더해져 넘쳤다).
저장소는 실행기가 아니다: 여기엔 파이프 실행 코드가 없고, 실행기(workflow_engine)가
이 모듈을 재수출하므로 기존 `from workflow_engine import list_workflows` 경로는 그대로다.
실행기 쪽 의존(preflight_sentence)은 함수 안에서 늦게 가져온다(순환 import 회피).
"""
import os
import re
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


def _get_workflows_path() -> Path:
    """워크플로우 저장 디렉토리"""
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        base = Path(env_path)
    else:
        base = Path(__file__).parent.parent.parent
    wf_path = base / "data" / "workflows"
    wf_path.mkdir(parents=True, exist_ok=True)
    return wf_path


def list_workflows() -> List[Dict]:
    """저장된 워크플로우 목록 (문장 pre-flight 동반 — preflight_sentence 참조)"""
    from workflow_engine import preflight_sentence
    from workflow_contract import _signature_of
    wf_path = _get_workflows_path()
    workflows = []
    for f in sorted(wf_path.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception as e:
            # ★깨진 원장 항목을 조용히 감추지 않는다 — 목록에서 사라지면 "없는 것"이 된다.
            workflows.append({
                "id": f.stem, "name": f.stem, "description": "", "steps_count": 0,
                "file": str(f), "runnable": False,
                "problem": f"워크플로 파일을 읽을 수 없습니다: {e}",
            })
            continue
        steps = data.get("steps") or data.get("do") or data.get("pipeline") or []
        # ★B1 동형: steps 가 문자열(저장 원문)이면 len()이 글자 수가 된다 — 목록에서
        # "스텝 121개"로 보이는 오표시 방지. 문장 하나 = 스텝 하나로 센다.
        if isinstance(steps, str):
            steps = [steps] if steps.strip() else []
        raw_steps = data.get("steps") or data.get("do") or []
        if isinstance(raw_steps, str):
            raw_steps = [raw_steps] if raw_steps.strip() else []
        pf = preflight_sentence(steps)
        entry = {
            "id": f.stem,
            "name": data.get("name", f.stem),
            "description": data.get("description", ""),
            "steps_count": len(raw_steps),
            "file": str(f),
            "runnable": pf["runnable"],
        }
        # 시그니처 — 목록에서 "이 워크플로우가 무엇을 요구하는지"가 보여야 부를 수 있다.
        sig = data.get("params_required")
        if not isinstance(sig, list):
            sig = _signature_of(data.get("steps") or data.get("do") or data.get("pipeline"))
        if sig:
            entry["params_required"] = sig
        if isinstance(data.get("params_default"), dict) and data["params_default"]:
            entry["params_default"] = data["params_default"]
        if pf["problem"]:
            entry["problem"] = pf["problem"]
            if pf["dead_vocab"]:
                entry["dead_vocab"] = pf["dead_vocab"]
        workflows.append(entry)
    return workflows


def _resolve_workflow_id(name: str) -> str:
    """name(또는 id)을 저장된 워크플로우 id로 해소. 코퍼스/사용자가 이름으로 호출해도
    run/get/delete가 동작하도록 — id 정확일치 → 이름 일치 → slugify 순. 못 찾으면 입력 그대로."""
    name = str(name).strip()
    if not name:
        return ""
    wfs = list_workflows()
    ids = {w["id"] for w in wfs}
    if name in ids:
        return name
    for w in wfs:
        if w.get("name") == name:
            return w["id"]
    slug = _slugify(name)
    if slug in ids:
        return slug
    return name


def get_workflow(workflow_id: str) -> Optional[Dict]:
    """워크플로우 조회"""
    wf_path = _get_workflows_path() / f"{workflow_id}.yaml"
    if not wf_path.exists():
        return None
    try:
        data = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    except Exception as e:
        # ★파일이 있는데 못 읽은 것을 None(=없음)으로 눙치지 않는다 — 바로 위
        # list_workflows 가 이미 세운 계약과 같은 어휘로 신고한다(2026-08-22).
        return {"id": workflow_id, "name": workflow_id, "runnable": False,
                "problem": f"워크플로 파일을 읽을 수 없습니다: {e}"}
    if not isinstance(data, dict):
        return {"id": workflow_id, "name": workflow_id, "runnable": False,
                "problem": f"워크플로 파일이 매핑이 아닙니다(빈 파일?): {type(data).__name__}"}
    data["id"] = workflow_id
    return data


# === 등록 시점 문법 관문 (2026-08-17) ===
# save 가 do 를 검증 없이 저장해 "저장은 됐는데 돌리면 깨지는" 지연 실패를 냈다
# (실측: 따옴표가 잘린 do — `[self:read]{path: "` — 가 success:true 로 저장되고
# run 에서야 엉뚱하게 실행됐다). [self:script]{op:"register"} 의 pre-flight 선례를
# 문장에 적용한다: 등록=문법 관문, 실행 가능성은 런타임 몫이라 파싱만 하고 실행 안 함.
#
# ★파서만으로는 못 잡는다(실측): 파서는 닫히지 않은 따옴표·중괄호를 관대하게 흡수해
#   위 잘린 문장을 query:"" 로 통과시킨다(_extract_bracket 의 "닫는 bracket 못 찾으면
#   원본 반환"). 그 관대함은 실행 경로의 기존 계약이라 건드리지 않고, 등록 관문에서만
#   균형을 따로 본다.

_SENTENCE_KEYS = ("steps", "pipeline", "do")


def _unclosed_reason(code: str) -> Optional[str]:
    """따옴표·중괄호 균형 검사. 반환: 오류 사유|None.

    문자열 상태를 줄 경계 너머로 승계하는 파서의 스캐너를 그대로 쓴다
    (주석 줄을 스캔에서 빼는 규칙도 _preprocess 와 동일 — 주석 속 따옴표가
    상태를 오염시키지 않게)."""
    from ibl_parser import _scan_line_state
    depth, in_string, string_char = 0, False, None
    for line in str(code).split('\n'):
        stripped = line.strip()
        if not in_string and (not stripped or stripped.startswith('#')):
            continue
        d, in_string, string_char = _scan_line_state(stripped, in_string, string_char)
        depth += d
    if in_string:
        return f"따옴표({string_char})가 닫히지 않았습니다"
    if depth > 0:
        return "중괄호 {가 닫히지 않았습니다"
    if depth < 0:
        return "여는 중괄호 없이 }가 있습니다"
    return None


def _validate_sentence(raw) -> Optional[str]:
    """저장 전 do(문장 또는 문장 배열) 문법 검사. 반환: 오류문|None.

    미할당 $변수는 합법(호출자 params 주입 자리)이라 파서가 리터럴로 통과시킨다.
    이미 파싱된 dict step 은 파서를 지나온 값이므로 통과."""
    from ibl_parser import parse as ibl_parse, IBLSyntaxError
    sentences = raw if isinstance(raw, list) else [raw]
    if not sentences:
        return "do 가 비어 있습니다 — 저장할 IBL 문장이 필요합니다."
    for one in sentences:
        if isinstance(one, dict):
            continue
        if not isinstance(one, str) or not one.strip():
            return "do 에 빈 문장이 있습니다 — 저장할 IBL 문장이 필요합니다."
        reason = _unclosed_reason(one)
        if reason:
            return f"do 문법 오류 — {reason}: {one[:120]}"
        try:
            ibl_parse(one)
        except IBLSyntaxError as e:
            return f"do 문법 오류 — {e}"
    return None


def save_workflow(workflow: dict) -> str:
    """
    워크플로우 저장

    Args:
        workflow: {name, description?, steps: [...], id?}

    Returns:
        워크플로우 ID
    """
    wf_id = workflow.get("id") or _slugify(workflow.get("name", "workflow"))
    wf_path = _get_workflows_path() / f"{wf_id}.yaml"

    # id 필드는 YAML에 저장하지 않음 (파일명이 ID)
    save_data = {k: v for k, v in workflow.items() if k != "id"}
    save_data["updated"] = datetime.now().isoformat()

    wf_path.write_text(
        yaml.dump(save_data, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return wf_id


def delete_workflow(workflow_id: str) -> bool:
    """워크플로우 삭제"""
    wf_path = _get_workflows_path() / f"{workflow_id}.yaml"
    if wf_path.exists():
        wf_path.unlink()
        return True
    return False


# === 유틸리티 ===

def _slugify(text: str) -> str:
    """텍스트를 파일명에 적합한 slug로 변환"""
    # 한글은 유지, 특수문자 제거
    slug = re.sub(r'[^\w가-힣\s-]', '', text)
    slug = re.sub(r'[\s]+', '_', slug).strip('_')
    return slug or "workflow"
