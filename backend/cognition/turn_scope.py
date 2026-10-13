"""대화 분류의 실행 지침. 도구 접근 권한과 분리한다."""

import json


def classification_message(message, history=None, images=None):
    """분류에 필요한 최근 대화만 전달한다. 첨부 바이트·도구 원문·연상은 제외한다."""
    recent = []
    for item in reversed(history or []):
        if item.get("role") not in {"user", "assistant"}:
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        recent.append({"role": item["role"], "content": content[-1500:]})
        if len(recent) == 2:
            break
    if not recent and not images:
        return message
    return json.dumps({"recent_dialogue": list(reversed(recent)),
                       "attached_images": len(images or []),
                       "current_message": message}, ensure_ascii=False)

CONTEXT_UPDATE = """<turn_scope kind="context_update">
사용자는 새 사실을 통보했다. 현재 사건의 관련 기억을 확인하고 통보한 사실·정정만 반영한다.
이 분류는 도구 권한을 바꾸지 않는다. 현재 대화의 기록 갱신과 제공된 자료 판독은 새 조사가 아니다.
답에 필요한 모순 해소는 하되 요청하지 않은 경로·날씨·상품 등의 새 조사를 시작하지 않는다.
다른 사건의 과거 정보나 AI 권고를 현재 사용자의 결정으로 적용하지 않는다.
저장·예약했다고 말할 때는 실제 성공 영수증이 있어야 한다. 후속 작업도 등록 전에는 약속하지 않는다.
</turn_scope>"""
