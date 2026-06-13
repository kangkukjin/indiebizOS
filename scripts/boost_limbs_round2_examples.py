#!/usr/bin/env python3
"""limbs 라운드 2 학습 예시 보강 (2026-05-27).

마이그레이션 후 부족한 패턴을 채운다:
- default-op 폼 (op 생략 시 핸들러가 가장 흔한 동작으로 폴백)
- 비-기본 op의 의도 표현 다양성
- 합성 흐름 (snapshot → click 등) 일부

JSON·DB 양쪽에 동일 예시를 추가한다.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "training" / "ibl_training_balanced_20260516.json"
DB_PATH = ROOT / "data" / "ibl_usage.db"

# (intent, ibl_code) 쌍. 카테고리·태그는 단순화.
NEW_EXAMPLES = [
    # ─── click (default single) ───
    ("버튼 눌러줘", '[limbs:snapshot] >> [limbs:click]{ref: "submit_btn"}'),
    ("e3 클릭", '[limbs:click]{ref: "e3"}'),
    ("로그인 버튼 클릭", '[limbs:click]{ref: "login"}'),
    # click double
    ("이 파일 더블클릭으로 열어", '[limbs:click]{op: "double", ref: "file_item"}'),
    ("표 셀 더블클릭해서 편집", '[limbs:click]{op: "double", ref: "cell_a3"}'),
    # click right
    ("이 링크 우클릭", '[limbs:click]{op: "right", ref: "link_target"}'),
    ("컨텍스트 메뉴 열어", '[limbs:click]{op: "right", ref: "item"}'),

    # ─── navigate (default goto) ───
    ("naver.com 열어", '[limbs:navigate]{url: "https://naver.com"}'),
    ("이 URL로 이동", '[limbs:navigate]{url: "https://example.com/path"}'),
    ("구글 검색 페이지 가", '[limbs:navigate]{url: "https://google.com"}'),
    # navigate back
    ("뒤로", '[limbs:navigate]{op: "back"}'),
    ("이전 페이지", '[limbs:navigate]{op: "back"}'),
    ("히스토리 뒤로 가", '[limbs:navigate]{op: "back"}'),
    # navigate forward
    ("앞으로 가", '[limbs:navigate]{op: "forward"}'),
    ("다음 페이지로", '[limbs:navigate]{op: "forward"}'),

    # ─── content (default text) ───
    ("페이지 본문 가져와", "[limbs:content]"),
    ("이 페이지 텍스트", "[limbs:content]"),
    ("기사 내용 추출", "[limbs:content]"),
    # content html
    ("페이지 HTML 통째로", '[limbs:content]{op: "html"}'),
    ("DOM 소스 줘", '[limbs:content]{op: "html"}'),
    ("렌더링된 HTML", '[limbs:content]{op: "html"}'),

    # ─── logs (default console) ───
    ("브라우저 로그 보여", "[limbs:logs]"),
    ("페이지 JS 오류 확인", "[limbs:logs]"),
    ("콘솔 메시지 누적", '[limbs:logs]{op: "console"}'),
    # logs network
    ("API 호출 로그", '[limbs:logs]{op: "network"}'),
    ("리소스 요청 분석", '[limbs:logs]{op: "network"}'),
    ("XHR 요청 모니터", '[limbs:logs]{op: "network"}'),

    # ─── music (default play) ───
    ("아이유 좋은날", '[limbs:music]{query: "아이유 좋은날"}'),
    ("클래식 음악 좀", '[limbs:music]{query: "베토벤 교향곡 9번"}'),
    ("재즈 분위기", '[limbs:music]{query: "smooth jazz"}'),
    # music add
    ("BTS Butter 대기열에", '[limbs:music]{op: "add", query: "BTS Butter"}'),
    ("이 곡 다음에 틀어", '[limbs:music]{op: "add", query: "newjeans hype boy"}'),
    # music skip
    ("다음 곡", '[limbs:music]{op: "skip"}'),
    ("이 노래 패스", '[limbs:music]{op: "skip"}'),
    # music queue
    ("재생 목록 보여", '[limbs:music]{op: "queue"}'),
    ("뭐 들어가 있어", '[limbs:music]{op: "queue"}'),
    # music stop
    ("음악 멈춰", '[limbs:music]{op: "stop"}'),
    ("끄자", '[limbs:music]{op: "stop"}'),
    # music download
    ("이 노래 MP3로 저장", '[limbs:music]{op: "download", url: "https://www.youtube.com/watch?v=abc123"}'),
    ("유튜브 오디오 다운", '[limbs:music]{op: "download", url: "https://www.youtube.com/watch?v=xyz"}'),

    # ─── radio (default play) ───
    ("KBS Cool FM 틀어", '[limbs:radio]{station_id: "kbs_coolfm"}'),
    ("재즈 라디오", '[limbs:radio]{stream_url: "https://example.com/jazz.m3u8"}'),
    ("MBC FM4U 켜", '[limbs:radio]{station_id: "mbc_fm4u"}'),
    # radio stop
    ("라디오 그만", '[limbs:radio]{op: "stop"}'),
    ("FM 꺼", '[limbs:radio]{op: "stop"}'),

    # ─── cctv (default open) ───
    ("강남대로 CCTV", '[limbs:cctv]{name: "강남대로"}'),
    ("부산 해운대 카메라", '[limbs:cctv]{name: "해운대"}'),
    ("이 URL 실시간 영상", '[limbs:cctv]{url: "https://cctv.example.com/stream.m3u8"}'),
    # cctv capture
    ("이 CCTV 화면 캡처", '[limbs:cctv]{op: "capture", name: "남산"}'),
    ("거리 CCTV 사진 저장", '[limbs:cctv]{op: "capture", name: "광화문", save_path: "/tmp/cctv.png"}'),

    # ─── 합성 흐름 예시 ───
    ("뉴스 페이지 본문 추출", '[limbs:navigate]{url: "https://news.example.com"} >> [limbs:content]'),
    ("로그인 페이지에서 ID 입력하고 클릭", '[limbs:snapshot] >> [limbs:type]{ref: "email", text: "user@example.com"} >> [limbs:click]{ref: "login_btn"}'),
    ("이 페이지 콘솔 에러 분석", '[limbs:logs] >> [limbs:content]{op: "html"}'),
]


def main() -> int:
    # ── JSON 추가 ─────────────────────────────────────
    if not JSON_PATH.exists():
        print(f"[boost] JSON 없음: {JSON_PATH}")
        return 2

    with JSON_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    existing_codes = {(ex.get("intent", ""), ex.get("ibl_code", "")) for ex in data}
    added = 0
    for intent, code in NEW_EXAMPLES:
        key = (intent, code)
        if key in existing_codes:
            continue
        data.append({"intent": intent, "ibl_code": code})
        existing_codes.add(key)
        added += 1

    JSON_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[boost] JSON: {added}개 추가 (전체 {len(data)})")

    # ── DB 추가 ─────────────────────────────────────
    if not DB_PATH.exists():
        print(f"[boost] DB 없음, 건너뜀: {DB_PATH}")
        return 0

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    db_added = 0
    for intent, code in NEW_EXAMPLES:
        # 중복 확인 (intent + ibl_code)
        cur.execute(
            "SELECT 1 FROM ibl_examples WHERE intent = ? AND ibl_code = ? LIMIT 1",
            (intent, code),
        )
        if cur.fetchone():
            continue
        cur.execute(
            """INSERT INTO ibl_examples
               (intent, ibl_code, nodes, category, difficulty, source, success_count, fail_count, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (intent, code, "limbs", "round2_boost", 1, "boost_limbs_round2", 0, 0, ""),
        )
        db_added += 1
    con.commit()
    con.close()
    print(f"[boost] DB: {db_added}개 추가")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
