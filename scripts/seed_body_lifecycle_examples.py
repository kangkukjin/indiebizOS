#!/usr/bin/env python3
"""⑩ 몸의 명사 생애주기 어휘 용례 시딩 (2026-10-05) — 해마 합성 용례 + 훈련 코퍼스. 단일 경로 add_examples_batch, 멱등."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
from ibl_usage_db import IBLUsageDB, DB_PATH  # noqa: E402

EXAMPLES = [
    {"intent": "런처에 있는 프로젝트 목록 보여줘", "ibl_code": '[self:project]{op: "list"}'},
    {"intent": "'시장조사' 라는 새 프로젝트를 만들어줘", "ibl_code": '[self:project]{op: "create", name: "시장조사"}'},
    {"intent": "프로젝트 '시장조사' 를 휴지통으로 보내줘", "ibl_code": '[self:project]{op: "trash", project_id: "시장조사"}'},
    {"intent": "런처 폴더 '업무' 를 만들고 프로젝트 '시장조사' 를 그 안에 넣어줘",
     "ibl_code": '#!ibl edition=2\n$f = [self:folder]{op: "create", name: "업무"}\n[self:project]{op: "move", project_id: "시장조사", folder_id: $f.folder.id}'},
    {"intent": "휴지통에 뭐가 있는지 보여줘", "ibl_code": '[self:trash]{op: "list"}'},
    {"intent": "휴지통의 스위치 '아침' 을 복구해줘", "ibl_code": '[self:trash]{op: "restore", item_id: "아침", item_type: "switch"}'},
    {"intent": "프로젝트 '시장조사' 의 비서 에이전트로 '뉴스 요약' 스위치를 만들어줘",
     "ibl_code": '[self:switch]{op: "create", name: "뉴스 요약", command: "오늘 뉴스를 요약해줘", project_id: "시장조사", agent_name: "비서"}'},
    {"intent": "스위치 '아침' 을 실행하고 끝날 때까지 기다려줘",
     "ibl_code": '#!ibl edition=2\n$r = [self:switch]{op: "run", switch_id: "아침"}\nreturn [self:task]{op: "wait", ref: $r.task_ref, timeout: 240}'},
    {"intent": "프로젝트 '시장조사' 에 조사원 에이전트를 만들어줘 (검색만 쓰게)",
     "ibl_code": '[others:agents]{op: "create", project_id: "시장조사", name: "조사원", role: "시장 자료를 찾아 정리한다", allowed_nodes: ["sense"]}'},
    {"intent": "조사원 에이전트의 역할문을 읽어줘", "ibl_code": '[others:agents]{op: "role", agent_id: "시장조사/agent_1234abcd"}'},
    {"intent": "조사원 에이전트를 시작해줘", "ibl_code": '[others:agents]{op: "start", agent_id: "시장조사/agent_1234abcd"}'},
    {"intent": "채팅방 목록 보여줘", "ibl_code": '[others:chat_room]{op: "list"}'},
    {"intent": "'기획 회의' 채팅방을 만들고 시장조사 프로젝트의 조사원을 초대해줘",
     "ibl_code": '#!ibl edition=2\n$room = [others:chat_room]{op: "create", name: "기획 회의"}\n[others:chat_room]{op: "add", room_id: $room.room.id, agent_id: "시장조사/agent_1234abcd"}'},
    {"intent": "기획 회의 방에서 조사원에게 이번 주 결론을 물어봐", "ibl_code": '[others:chat_room]{op: "say", room_id: "room_1", message: "@조사원 이번 주 결론은?"}'},
    {"intent": "이웃 창고에 새로 올라온 것 보여줘", "ibl_code": '[others:warehouse]{op: "feed", limit: 20}'},
    {"intent": "이웃 창고에서 '사진' 검색해줘", "ibl_code": '[others:warehouse]{op: "search", query: "사진"}'},
    {"intent": "이 파일을 내 창고 1레벨에 소개(리트윗)해줘", "ibl_code": '[others:warehouse]{op: "retweet", url: "https://neighbor.example/f?p=report.pdf", name: "report.pdf", level: 1}'},
    {"intent": "내 창고 0레벨에 뭐가 있는지 보여줘", "ibl_code": '[self:warehouse]{op: "list", level: 0}'},
    {"intent": "이 보고서 파일을 내 창고 2레벨 '보고서' 폴더에 넣어줘", "ibl_code": '[self:warehouse]{op: "add", level: 2, paths: ["~/Documents/report.pdf"], dest: "보고서"}'},
    {"intent": "창고 휴지통에서 report.pdf 를 복구해줘", "ibl_code": '[self:warehouse]{op: "restore", level: 2, name: "report.pdf"}'},
    {"intent": "메일 채널 설정이 어떻게 돼 있어?", "ibl_code": '[others:channel]{op: "detail", channel_type: "gmail"}'},
    {"intent": "채널 폴러가 돌고 있는지 확인해줘", "ibl_code": '[others:channel]{op: "status"}'},
    {"intent": "지메일을 지금 바로 수신해줘", "ibl_code": '[others:channel]{op: "poll", channel_type: "gmail"}'},
    {"intent": "이 동영상 코덱이 브라우저에서 바로 재생되는지 봐줘", "ibl_code": '[self:media]{op: "probe", path: "~/Movies/clip.mkv"}'},
    {"intent": "이 동영상을 브라우저용 mp4 로 변환하고 끝나면 알려줘",
     "ibl_code": '#!ibl edition=2\n$r = [self:media]{op: "transcode", path: "~/Movies/clip.mkv"}\nreturn [self:task]{op: "wait", ref: $r.task_ref, timeout: 240}'},
    {"intent": "이 동영상에 자막 파일이 있는지 보여줘", "ibl_code": '[self:media]{op: "subtitles", path: "~/Movies/clip.mkv"}'},
    {"intent": "즐겨찾기에 네이버 뉴스를 등록해줘", "ibl_code": '[limbs:launch]{op: "add", name: "네이버 뉴스", url: "https://news.naver.com"}'},
    {"intent": "즐겨찾기에서 네이버 뉴스를 빼줘", "ibl_code": '[limbs:launch]{op: "remove", name: "네이버 뉴스"}'},
]


def main():
    import sqlite3
    with sqlite3.connect(DB_PATH) as conn:
        present = set(conn.execute("SELECT intent, ibl_code FROM ibl_examples").fetchall())
    fresh = [e for e in EXAMPLES if (e["intent"], e["ibl_code"]) not in present]
    node = lambda code: "others" if "[others:" in code.split("]")[0] else ("limbs" if "[limbs:" in code.split("]")[0] else "self")
    count = IBLUsageDB().add_examples_batch([
        dict(e, nodes=node(e["ibl_code"]), source="synthetic", tags="body_lifecycle,2026-10-05") for e in fresh
    ]) if fresh else 0
    path = ROOT / "data/training/ibl_distilled.json"
    rows = json.loads(path.read_text())
    known = {(r.get("intent"), r.get("ibl_code")) for r in rows}
    additions = [r for r in EXAMPLES if (r["intent"], r["ibl_code"]) not in known]
    if additions:
        path.write_text(json.dumps(rows + additions, ensure_ascii=False, indent=2) + "\n")
    print(f"body lifecycle examples: DB added {count}; training added {len(additions)}")


if __name__ == "__main__":
    main()
