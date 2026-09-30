import json
import os
import sys
from pathlib import Path

args = json.load(sys.stdin)
report = args["분석"]
print('조판 진단: "따옴표" \\ 역슬래시\t한글 ${값}')

def cell(value):
    if value is None:
        return "확인 필요"
    return str(value).replace("|", "\\|").replace("\n", "<br>")

def table(rows, fields):
    lines = ["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    lines.extend("| " + " | ".join(cell(row.get(key)) for key in fields) + " |" for row in rows)
    return "\n".join(lines)

sections = ["# 2025년 9월 학원 운영 점검", "합성 훈련 자료. 지각은 출석으로 계산하며 미응시는 평균에서 제외했습니다.",
    f"재원 {report['재원수']}명 · 퇴원 {report['퇴원수']}명 · 출결 {report['출결행수']:,}행 · 수납 합계 {args['금액표시']}원",
    "## 자료 상태", table(report["파일상태"], ["파일", "상태", "행수", "오류"]),
    "## 반별 현황", table(report["반표"], ["반", "학생수", "출석률", "평균점수"]),
    "## 점검 항목별 건수", table(report["종류별"], ["종류", "건수"]),
    "## 후속 처리 대상", table(report["문제"], ["종류", "대상", "반", "근거", "단서"]),
    "## 상담 메모 유형 (AI 분류)", "확인 필요는 AI 판정이 확정되지 않은 메모입니다. 조치 필요와 함께 아래 확인 대상으로 남깁니다.",
    table(report["유형별"], ["유형", "건수"]), "## 조치·확인 필요 상담 메모",
    table(report["조치메모"], ["학번", "일자", "메모", "유형", "확신"]),
    "## 읽기·해석 한계", report["출결단서"] or "출결 원천을 모두 읽었습니다. 파일별 상태와 해석 오류는 위 점검 내역에 표시했습니다.",
    "태그: " + ", ".join(args["태그"])]
result = {"markdown": "\n\n".join(sections) + "\n", "issues_json": json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)}
path = Path(os.environ["INDIEBIZ_SCRIPT_RESULT"])
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
tmp.replace(path)
