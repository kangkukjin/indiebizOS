"""copy_ops.py — 파이프 통화를 파일로 내리는 자리 ([self:copy] 의 src 생략 경로).

handler.py 에서 분리(2026-08-22, 1500줄 규칙). "몇 장을 어디에 저장" 은 새 동사가 아니라
*조합*이다 — 고르는 일은 앞 액션과 table 변환자가 하고(take/filter/sort), copy 는 받은 것을
그대로 옮긴다:

    [self:photo]{source:"usb"} >> [table:take]{n:10} >> [self:copy]{dest:"~/Desktop/폰사진"}

경로 게이트(`_validate_path_in_scope`)는 handler 가 소유하므로 **넘겨받는다**(office_ops
선례) — 두 벌로 만들면 한쪽만 조여지는 드리프트가 생긴다.
"""
import json
import os

try:   # 통화 되읽기 정본(B19-2) — 모든 소비자가 같은 눈으로 읽는다
    from common.currency import coerce_items_payload as _coerce_items, currency_shape_note as _shape_note
except ImportError:      # 백엔드 공용 모듈이 없는 환경(패키지 단독 시험) — 옛 관용 유지
    def _coerce_items(v):
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            rows = v.get("items")
            return rows if isinstance(rows, list) else None
        return None

    def _shape_note(v):
        return type(v).__name__


def piped_items(prev_result):
    """파이프로 온 결과에서 행 목록 — **통화 없음(None)과 0행([])을 가른다**.

    ★F20-3 후속 (2026-08-22): 옛 코드는 둘을 똑같이 `[]` 로 접었고, 호출자는 그 하나의
    빈 목록을 보고 "복사할 항목이 없습니다"라고만 말했다. 그래서 *앞 액션이 통화를 안 내는
    액션이었다*(진짜 오류)와 *앞 액션이 정상적으로 0행을 냈다*(정당한 빈손)가 같은 문장으로
    보고됐다 — 0행 계약(통화 없음=에러 / 0행=성공)을 이 자리에선 지킬 수가 없었다.

    걸러내기는 호출자 몫이다. "행이 있는데 레코드(dict)가 아니다"는 0행과 또 다른 사실이라
    여기서 접으면 같은 병이 한 겹 더 생긴다.

    반환: 행 목록(0행 포함) 또는 None(통화 없음 — 평문·스칼라·items 자리가 목록이 아님).
    """
    rows = _coerce_items(prev_result)      # 정본: list · {items:[…]} 봉투 · 그 둘의 JSON 문자열
    if rows is None:
        data = prev_result                 # 옛 records 봉투 (생산자 0 — 잔존 데이터 관용)
        if isinstance(data, str) and data.strip().startswith("{"):
            try:
                data = json.loads(data)
            except (ValueError, TypeError):
                data = None
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            rows = data["records"]
    return rows


def copy_piped_items(tool_input: dict, dest: str, project_path: str, path_guard) -> str:
    """파이프로 온 items 의 파일들을 dest *폴더* 로 복사 (실제 복사는 file_index 단일 소스)."""
    prev = tool_input.get("_prev_result")
    rows = piped_items(prev)
    if rows is None:
        return ("Error: 복사할 항목이 없습니다 — 앞 단계에 items 통화가 없습니다. "
                "src(원본 경로)를 주거나, items 를 내는 액션의 결과를 >> 로 넘기세요. "
                f"받은 봉투: {_shape_note(prev)}")
    items = [it for it in rows if isinstance(it, dict)]
    if rows and not items:
        return (f"Error: 앞 단계가 {len(rows)}행을 냈지만 레코드(dict)가 하나도 없습니다 "
                f"— 복사는 path 필드를 가진 항목이 필요합니다. 첫 행: {str(rows[0])[:60]}")
    if not items:
        # ★0행은 고장이 아니라 정당한 빈손 — 감시자·필터 문형의 정상 결과다(F20-3 계약).
        # "Error:" 로 시작하지 않아야 파이프가 성공으로 읽는다(_is_error_result 규약).
        return "입력 0행 — 복사할 파일이 없습니다 (0개 저장, 빈손). 앞 단계가 0행을 냈습니다."

    dst_dir = os.path.join(project_path, os.path.expanduser(dest))
    scope_err = path_guard(dst_dir, project_path)
    if scope_err:
        return scope_err

    import file_index
    res = file_index.save_media_files(items, dst_dir)
    saved, failed = res.get("saved") or [], res.get("failed") or []
    if res.get("error"):
        return f"Error: {res['error']}"
    if not saved and not failed:
        return "Error: 항목에 파일 경로가 없습니다 (path 필드 필요)."
    msg = f"{len(saved)}개 파일을 저장했습니다: {res.get('dest')}"
    if saved:
        msg += "\n  " + ", ".join(saved[:5]) + (f" 외 {len(saved) - 5}개" if len(saved) > 5 else "")
    if failed:
        msg += f"\n실패 {len(failed)}개: " + "; ".join(failed[:3])
    return msg
