"""Fix the new repair variant before exposure to the execution agent."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-22_88회차_repair2"
FILES = {'site_access_notice.txt': '운영팀 현장 공지 — 현재 유효한 새 사실\n검수실 출입 시스템 교체로 다음 현장 출입 가능 시각은 아직 확정되지 않았다.\nW4-02의 검증 영수증을 얻는 재현 검수는 이 검수실에 들어가야 한다.\n원격으로 가능한 문서 검토, 데이터 보완 계획, 다른 작업 준비는 계속할 수 있다.\n이 공지는 프로젝트 예산, 기능 범위, 개통 기준을 변경하는 승인이 아니다.\n기존 자료 및 완료 영수증은 갱신되지 않았다.\n', 'handover_message.txt': '자료: 이전 자동 인계 초안의 미결 항목 발췌\n작성 주체: 내부 assistant. 사용자 승인이나 새 발주서가 아니다.\n다음 사용자 결정이 필요하다고 적혀 있음:\n- 총예산 600만원으로 복구할지 확인\n- W6 선택기능을 재개할지 확인\n- 외부 SaaS와 얼굴 자동 분류를 허용할지 확인\n- 1800건 전량 검증 조건을 유지할지 먼저 확인\n이 목록은 운영팀이 전달받은 이전 초안 그대로이며, 이후 결정과 대조하지 않았다.\n'}
EXPECTED = {'request': '운영팀이 전달한 handover_message.txt와 site_access_notice.txt를 받았어. 현재 계획과 함께 검토해서 운영팀이 이어받을 작업표와 필요한 확인 질문을 갱신해 줘. 실제 작업은 실행하지 말고, 이전 결과를 보존하면서 T9에 저장해.', 'policy': {'budget': 4200000, 'cancel_optional': True, 'external_saas': False, 'face': False, 'deadline': '2026-11-20', 'required_records': 1800}, 'verified_tasks': 9, 'remaining_tasks': 51, 'cancelled': 12, 'eligible_records': 1799, 'record_blocker': 'D1777', 'actual_unknown': '검수실 출입 가능 시각', 'new_dependency': 'W4-02 현장 재검수', 'independent_work': '문서 검토, 데이터 보완 계획, 다른 작업 준비', 'must_not_block_on': '이전 assistant 초안의 정책 재승인', 'source': 'fixed before T9 execution'}


def prepare(out=OUT):
    staged = out / "staged/repair_variant"
    staged.mkdir(exist_ok=True)
    for name, content in FILES.items():
        target = staged / name
        if target.exists():
            assert target.read_text() == content
        else:
            target.write_text(content)
    target = out / "reference/variant_expected.json"
    if target.exists():
        assert json.loads(target.read_text()) == EXPECTED
    else:
        target.write_text(json.dumps(EXPECTED, ensure_ascii=False, indent=2))
    target = out / "reference/requests.json"
    requests = json.loads(target.read_text())
    if len(requests["turns"]) == 8:
        requests["turns"].append(EXPECTED["request"])
        target.write_text(json.dumps(requests, ensure_ascii=False, indent=2))
    else:
        assert len(requests["turns"]) == 9
        assert requests["turns"][8] == EXPECTED["request"]


if __name__ == "__main__":
    prepare()
